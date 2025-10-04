"""
Український NER recognizer на базі трансформерної моделі.

Архітектурна відповідальність: Інкапсуляція логіки роботи з українською
NER моделлю. Забезпечує lazy loading та обробку помилок.
"""

import logging
from typing import List, Optional

import spacy
from huggingface_hub import snapshot_download
from presidio_analyzer import RecognizerResult

from core.config import config

logger = logging.getLogger(__name__)


class UkrainianNERRecognizer:
    """
    Recognizer для українських named entities.
    
    Стратегія: Singleton pattern з lazy loading для оптимізації
    використання пам'яті. Модель завантажується тільки при першому виклику.
    """
    
    _instance: Optional['UkrainianNERRecognizer'] = None
    _nlp: Optional[spacy.language.Language] = None
    
    def __new__(cls):
        """Singleton: тільки один екземпляр recognizer на весь застосунок."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Конструктор не завантажує модель - це робить _load_model()."""
        if not hasattr(self, '_initialized'):
            self._initialized = True
            logger.info("UkrainianNERRecognizer initialized (model not loaded yet)")
    
    def _load_model(self) -> spacy.language.Language:
        """
        Lazy loading української NER моделі.
        
        Завантажує модель з Hugging Face Hub при першому виклику.
        Кешує результат для подальшого використання.
        
        Returns:
            Завантажена spaCy модель
            
        Raises:
            RuntimeError: Якщо модель не вдалося завантажити
        """
        if self._nlp is None:
            try:
                logger.info(f"Loading Ukrainian NER model: {config.MODEL_REPO}")
                local_model_dir = snapshot_download(repo_id=config.MODEL_REPO)
                self._nlp = spacy.load(local_model_dir)
                logger.info("Model loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load model: {e}")
                raise RuntimeError(f"Не вдалося завантажити модель: {e}") from e
        
        return self._nlp
    
    def analyze(
        self, 
        text: str, 
        enabled_entities: Optional[List[str]] = None
    ) -> List[RecognizerResult]:
        """
        Аналізує текст та повертає знайдені українські сутності.
        
        Args:
            text: Текст для аналізу
            enabled_entities: Список типів сутностей для пошуку.
                             Якщо None - шукає всі доступні.
        
        Returns:
            Список RecognizerResult з знайденими сутностями
            
        Raises:
            ValueError: Якщо text порожній
            RuntimeError: Якщо модель не завантажилась
        """
        if not text or not text.strip():
            raise ValueError("Текст не може бути порожнім")
        
        if len(text) > config.MAX_TEXT_LENGTH:
            raise ValueError(
                f"Текст завеликий: {len(text)} символів "
                f"(max {config.MAX_TEXT_LENGTH})"
            )
        
        # Lazy loading моделі
        nlp = self._load_model()
        
        # Якщо не вказано які сутності шукати - шукаємо всі
        if enabled_entities is None:
            enabled_entities = list(config.UKRAINIAN_ENTITIES.keys())
        
        # Конвертуємо в set для швидкої перевірки
        enabled_set = set(enabled_entities)
        
        try:
            # Обробка тексту моделлю
            doc = nlp(text)
            
            results = []
            for ent in doc.ents:
                # Пропускаємо якщо тип сутності не активований
                if ent.label_ not in enabled_set:
                    continue
                
                # Витягуємо confidence якщо доступний
                confidence = 1.0
                if ent.has_extension("confidence"):
                    try:
                        confidence = float(ent._.confidence)
                    except (AttributeError, ValueError, TypeError):
                        pass
                
                # Створюємо правильний RecognizerResult
                result = RecognizerResult(
                    entity_type=ent.label_,
                    start=ent.start_char,
                    end=ent.end_char,
                    score=confidence
                )
                results.append(result)
            
            logger.info(f"Found {len(results)} Ukrainian entities")
            return results
            
        except Exception as e:
            logger.error(f"Error during NER analysis: {e}")
            raise RuntimeError(f"Помилка під час аналізу: {e}") from e
    
    @property
    def is_loaded(self) -> bool:
        """Перевіряє чи модель завантажена."""
        return self._nlp is not None
    
    def unload(self) -> None:
        """Вивантажує модель з пам'яті (для економії ресурсів)."""
        if self._nlp is not None:
            logger.info("Unloading Ukrainian NER model")
            self._nlp = None