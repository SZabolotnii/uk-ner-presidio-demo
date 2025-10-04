"""
Pattern-based recognizers для PII даних (Presidio).

Архітектурна стратегія: Абстракція над Presidio для створення 
language-agnostic pattern recognizers з українською контекстуалізацією.
"""

import logging
from typing import List, Optional

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from presidio_analyzer.nlp_engine import NlpArtifacts, NlpEngine
from presidio_analyzer import RecognizerResult

logger = logging.getLogger(__name__)


class SimpleNoOpNlpEngine(NlpEngine):
    """
    Мінімальний NLP engine stub для Presidio.
    
    Архітектурне рішення: Presidio за замовчуванням вимагає повноцінний
    NLP engine (spaCy). Ми створюємо stub, щоб використовувати тільки
    pattern recognizers без завантаження важких моделей.
    
    Стратегічна перевага: Економія ~500MB RAM та швидший startup.
    """

    def __init__(self, supported_languages: Optional[List[str]] = None):
        self._supported_languages = supported_languages or ["en"]
        self._loaded = True

    def load(self) -> None:
        """Заглушка: нічого не завантажуємо."""
        self._loaded = True

    def is_loaded(self) -> bool:
        return self._loaded

    def process_text(self, text: str, language: str) -> NlpArtifacts:
        """Повертає порожні artifacts - pattern recognizers не потребують NLP."""
        return NlpArtifacts(
            entities=[],
            tokens=[],
            lemmas=[],
            tokens_indices=[],
            nlp_engine=self,
            language=language
        )

    def process_batch(
        self, 
        texts: List[str], 
        language: str, 
        batch_size: int = 1, 
        n_process: int = 1, 
        **kwargs
    ):
        """Batch processing заглушка."""
        for text in texts:
            yield text, self.process_text(text, language)

    def is_stopword(self, word: str, language: str) -> bool:
        return False

    def is_punct(self, word: str, language: str) -> bool:
        return False

    def get_supported_entities(self) -> List[str]:
        return []

    def get_supported_languages(self) -> List[str]:
        return list(self._supported_languages)


class PresidioPatternRecognizer:
    """
    Wrapper над Presidio Analyzer з кастомними українськими recognizers.
    
    Стратегія: Централізована конфігурація всіх pattern-based recognizers
    з можливістю легкого додавання нових patterns.
    """
    
    _instance: Optional['PresidioPatternRecognizer'] = None
    _analyzer: Optional[AnalyzerEngine] = None
    
    def __new__(cls):
        """Singleton для уникнення дублювання recognizers."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Ініціалізація з реєстрацією кастомних recognizers."""
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._setup_analyzer()
            logger.info("PresidioPatternRecognizer initialized")
    
    def _setup_analyzer(self) -> None:
        """
        Налаштування Presidio Analyzer з кастомними recognizers.
        
        Архітектурна відповідальність: Централізація всієї логіки
        створення та реєстрації pattern recognizers.
        """
        # Створюємо analyzer з нашим stub NLP engine
        self._analyzer = AnalyzerEngine(
            nlp_engine=SimpleNoOpNlpEngine(),
            supported_languages=["en"]
        )
        
        # Реєструємо український IBAN recognizer
        self._register_ukrainian_iban()
        
        logger.info("Presidio Analyzer configured with custom recognizers")
    
    def _register_ukrainian_iban(self) -> None:
        """
        Реєструє recognizer для українських IBAN кодів.
        
        Специфікація: UA + 27 цифр
        Приклад: UA213223130000026007233566001
        """
        ukrainian_iban_pattern = Pattern(
            name="ukrainian_iban",
            regex=r"\bUA\d{27}\b",
            score=0.9
        )
        
        ukrainian_iban_recognizer = PatternRecognizer(
            supported_entity="IBAN_CODE",
            patterns=[ukrainian_iban_pattern],
            context=[
                # Українські контекстні слова
                "рахунок", "рахунку", "рахунка",
                "IBAN", "iban",
                "оплата", "оплати",
                "банк", "банку", "банківський",
                "переказ", "перевод",
                # Англійські (для універсальності)
                "account", "payment", "transfer"
            ],
            supported_language="en"  # Language-agnostic patterns
        )
        
        self._analyzer.registry.add_recognizer(ukrainian_iban_recognizer)
        logger.info("Registered Ukrainian IBAN recognizer")
    
    def analyze(
        self, 
        text: str, 
        enabled_entities: Optional[List[str]] = None,
        language: str = "en"
    ) -> List[RecognizerResult]:
        """
        Аналізує текст pattern recognizers.
        
        Args:
            text: Текст для аналізу
            enabled_entities: Список типів для пошуку. None = всі.
            language: Мова для аналізу (за замовчуванням "en" для patterns)
        
        Returns:
            Список знайдених RecognizerResult
            
        Raises:
            ValueError: Якщо text порожній
        """
        if not text or not text.strip():
            raise ValueError("Текст не може бути порожнім")
        
        try:
            results = self._analyzer.analyze(
                text=text,
                entities=enabled_entities,
                language=language
            )
            
            logger.info(f"Found {len(results)} pattern-based entities")
            return results
            
        except Exception as e:
            logger.error(f"Error during pattern analysis: {e}")
            raise RuntimeError(f"Помилка pattern detection: {e}") from e
    
    @property
    def supported_entities(self) -> List[str]:
        """Повертає список підтримуваних типів сутностей."""
        return self._analyzer.get_supported_entities()
    
    def add_custom_recognizer(self, recognizer: PatternRecognizer) -> None:
        """
        Додає новий кастомний recognizer.
        
        Розширюваність: Дозволяє додавати нові patterns runtime.
        
        Args:
            recognizer: Екземпляр PatternRecognizer для реєстрації
        """
        try:
            self._analyzer.registry.add_recognizer(recognizer)
            logger.info(f"Added custom recognizer for {recognizer.supported_entities}")
        except Exception as e:
            logger.error(f"Failed to add recognizer: {e}")
            raise