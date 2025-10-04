"""
Центральний аналізатор - фасад для гібридної системи деідентифікації.

Архітектурний патерн: Facade Pattern
Відповідальність: Координація між Ukrainian NER, Presidio patterns,
conflict resolution та anonymization.

Стратегічна мета: Надати простий, високорівневий API для UI шару,
приховуючи складність внутрішньої оркестрації.
"""

import logging
from typing import Dict, List, Tuple
from dataclasses import dataclass

from presidio_analyzer import RecognizerResult
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

from core.config import config
from recognizers.ukrainian_ner import UkrainianNERRecognizer
from recognizers.presidio_patterns import PresidioPatternRecognizer
from utils.conflict_resolution import remove_overlapping_entities

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """
    Структурований результат аналізу.
    
    Design Principle: Immutable data objects для передачі між шарами.
    """
    entities: List[RecognizerResult]
    anonymized_text: str
    original_text: str
    entities_count: int
    
    def format_entities_list(self) -> str:
        """
        Форматує список знайдених сутностей для відображення.
        
        Returns:
            Текстове представлення сутностей з позиціями та scores
        """
        if not self.entities:
            return "Сутностей не знайдено"
        
        # Сортуємо за позицією в тексті
        sorted_entities = sorted(self.entities, key=lambda x: x.start)
        
        lines = []
        for idx, entity in enumerate(sorted_entities, 1):
            entity_text = self.original_text[entity.start:entity.end]
            line = (
                f"{idx}. {entity.entity_type}: '{entity_text}' "
                f"(позиція {entity.start}-{entity.end}, "
                f"впевненість {entity.score:.2f})"
            )
            lines.append(line)
        
        return "\n".join(lines)


class HybridAnalyzer:
    """
    Гібридний аналізатор об'єднує NER та pattern-based підходи.
    
    Архітектурна стратегія:
    1. Паралельний запуск NER + Presidio (можна оптимізувати async)
    2. Інтелігентне злиття результатів
    3. Розв'язання конфліктів
    4. Централізована анонімізація
    
    Design Pattern: Facade + Strategy (для conflict resolution)
    """
    
    def __init__(self):
        """
        Ініціалізація компонентів системи.
        
        Lazy initialization: recognizers завантажуються при першому виклику.
        """
        self.ner_recognizer = UkrainianNERRecognizer()
        self.pattern_recognizer = PresidioPatternRecognizer()
        self.anonymizer = AnonymizerEngine()
        
        logger.info("HybridAnalyzer initialized")
    
    def analyze(
        self,
        text: str,
        ukrainian_entities: List[str] = None,
        presidio_entities: List[str] = None,
        conflict_strategy: str = "score"
    ) -> AnalysisResult:
        """
        Виконує повний цикл аналізу та анонімізації тексту.
        
        Workflow:
        1. Валідація вхідних даних
        2. NER аналіз (якщо є активні ukrainian entities)
        3. Pattern аналіз (якщо є активні presidio entities)
        4. Злиття результатів
        5. Conflict resolution
        6. Анонімізація
        
        Args:
            text: Текст для аналізу
            ukrainian_entities: Список NER сутностей для пошуку
            presidio_entities: Список Presidio сутностей для пошуку
            conflict_strategy: Стратегія розв'язання конфліктів ("score" або "priority")
        
        Returns:
            AnalysisResult з результатами аналізу
            
        Raises:
            ValueError: Некоректні вхідні дані
            RuntimeError: Помилка під час аналізу
        """
        # === ЕТАП 1: Валідація ===
        self._validate_input(text)
        
        # Використовуємо конфіг за замовчуванням якщо не вказано
        if ukrainian_entities is None:
            ukrainian_entities = config.get_enabled_ukrainian_entities()
        
        if presidio_entities is None:
            presidio_entities = config.get_enabled_presidio_entities()
        
        logger.info(
            f"Starting analysis: {len(ukrainian_entities)} NER types, "
            f"{len(presidio_entities)} pattern types"
        )
        
        # === ЕТАП 2: NER Аналіз ===
        all_results = []
        operators = {}
        
        if ukrainian_entities:
            try:
                ner_results = self.ner_recognizer.analyze(text, ukrainian_entities)
                all_results.extend(ner_results)
                
                # Налаштовуємо operators для NER сутностей
                for entity_type in ukrainian_entities:
                    operators[entity_type] = self._create_operator(entity_type)
                
                logger.info(f"NER found {len(ner_results)} entities")
            except Exception as e:
                logger.error(f"NER analysis failed: {e}")
                # Продовжуємо з pattern analysis навіть якщо NER провалився
        
        # === ЕТАП 3: Pattern Аналіз ===
        if presidio_entities:
            try:
                pattern_results = self.pattern_recognizer.analyze(
                    text, 
                    presidio_entities
                )
                all_results.extend(pattern_results)
                
                # Налаштовуємо operators для Presidio сутностей
                for entity_type in presidio_entities:
                    operators[entity_type] = self._create_operator(entity_type)
                
                logger.info(f"Pattern analysis found {len(pattern_results)} entities")
            except Exception as e:
                logger.error(f"Pattern analysis failed: {e}")
        
        # === ЕТАП 4: Conflict Resolution ===
        sanitized_results = self._sanitize_results(text, all_results)

        if sanitized_results:
            filtered_results = remove_overlapping_entities(
                sanitized_results,
                strategy=conflict_strategy
            )
            logger.info(
                f"After conflict resolution: {len(filtered_results)} entities "
                f"(removed {len(sanitized_results) - len(filtered_results)} overlaps)"
            )
        else:
            filtered_results = []
            logger.info("No entities found")
        
        # === ЕТАП 5: Анонімізація ===
        anonymized_text = self._anonymize(text, filtered_results, operators)
        
        # === ЕТАП 6: Формування результату ===
        return AnalysisResult(
            entities=filtered_results,
            anonymized_text=anonymized_text,
            original_text=text,
            entities_count=len(filtered_results)
        )
    
    def _validate_input(self, text: str) -> None:
        """
        Валідує вхідний текст.
        
        Raises:
            ValueError: Якщо текст невалідний
        """
        if not text:
            raise ValueError("Текст не може бути порожнім — порожній ввід заборонено")

        if not text.strip():
            raise ValueError(
                "Текст не може містити тільки пробіли — порожній ввід заборонено"
            )

        if len(text) > config.MAX_TEXT_LENGTH:
            raise ValueError(
                f"Текст завеликий: {len(text)} символів. "
                f"Максимум: {config.MAX_TEXT_LENGTH}"
            )

    def _sanitize_results(
        self,
        text: str,
        results: List[RecognizerResult]
    ) -> List[RecognizerResult]:
        """Нормалізує координати сутностей відносно довжини тексту."""
        if not results:
            return []

        sanitized: List[RecognizerResult] = []
        text_length = len(text)

        for result in results:
            start = max(0, result.start)
            end = min(text_length, result.end)

            if start >= end:
                logger.warning(
                    "Discarding entity %s з некоректним діапазоном %s-%s для тексту довжиною %s",
                    result.entity_type,
                    result.start,
                    result.end,
                    text_length,
                )
                continue

            if start != result.start or end != result.end:
                logger.warning(
                    "Коригуємо координати сутності %s: %s-%s → %s-%s",
                    result.entity_type,
                    result.start,
                    result.end,
                    start,
                    end,
                )

            sanitized.append(
                RecognizerResult(
                    entity_type=result.entity_type,
                    start=start,
                    end=end,
                    score=result.score,
                    analysis_explanation=result.analysis_explanation,
                    recognition_metadata=result.recognition_metadata,
                )
            )

        return sanitized

    def _create_operator(self, entity_type: str) -> OperatorConfig:
        """
        Створює operator config для анонімізації сутності.

        Extensibility Point: Тут можна додати різні стратегії
        анонімізації (mask, hash, encrypt тощо).
        
        Args:
            entity_type: Тип сутності
            
        Returns:
            OperatorConfig для Presidio Anonymizer
        """
        anonymization_format = config.DEFAULT_ANONYMIZATION_FORMAT
        
        return OperatorConfig(
            "replace",
            {"new_value": anonymization_format.format(entity_type=entity_type)}
        )
    
    def _anonymize(
        self,
        text: str,
        results: List[RecognizerResult],
        operators: Dict[str, OperatorConfig]
    ) -> str:
        """
        Анонімізує текст замінюючи знайдені сутності.
        
        Args:
            text: Оригінальний текст
            results: Знайдені сутності
            operators: Конфігурація анонімізації для кожного типу
            
        Returns:
            Анонімізований текст
        """
        if not results:
            return text
        
        try:
            anonymized = self.anonymizer.anonymize(text, results, operators)
            return anonymized.text
        except Exception as e:
            logger.error(f"Anonymization failed: {e}")
            raise RuntimeError(f"Помилка анонімізації: {e}") from e
    
    def get_system_info(self) -> Dict[str, any]:
        """
        Повертає інформацію про стан системи (для діагностики).
        
        Returns:
            Словник з метаданими системи
        """
        return {
            "ner_model_loaded": self.ner_recognizer.is_loaded,
            "ner_model_repo": config.MODEL_REPO,
            "supported_ukrainian_entities": list(config.UKRAINIAN_ENTITIES.keys()),
            "supported_presidio_entities": list(config.PRESIDIO_PATTERN_ENTITIES.keys()),
            "max_text_length": config.MAX_TEXT_LENGTH
        }
