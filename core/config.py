"""
Централізована конфігурація системи деідентифікації.

Архітектурний принцип: Single Source of Truth для всіх налаштувань.
Це дозволяє легко модифікувати поведінку системи без зміни коду.
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class EntityConfig:
    """Конфігурація для окремої сутності."""
    name: str
    description: str
    enabled: bool = True
    anonymization_format: str = "[{entity_type}]"


@dataclass
class AppConfig:
    """Глобальна конфігурація додатку."""
    
    # Модель
    MODEL_REPO: str = "dchaplinsky/uk_ner_web_trf_13class"
    
    # Обмеження
    MAX_TEXT_LENGTH: int = 100_000
    MAX_BATCH_SIZE: int = 100
    
    # Налаштування анонімізації
    DEFAULT_ANONYMIZATION_FORMAT: str = "[{entity_type}]"
    
    # Українські сутності з описами
    UKRAINIAN_ENTITIES: Dict[str, EntityConfig] = field(default_factory=lambda: {
        "PERS": EntityConfig("PERS", "Імена, прізвища, по-батькові"),
        "ORG": EntityConfig("ORG", "Назви організацій, компаній"),
        "LOC": EntityConfig("LOC", "Географічні назви, адреси"),
        "DATE": EntityConfig("DATE", "Дати (повні та часткові)"),
        "TIME": EntityConfig("TIME", "Час, часові позначки"),
        "JOB": EntityConfig("JOB", "Посади, професії"),
        "MON": EntityConfig("MON", "Грошові суми, валюти"),
        "PCT": EntityConfig("PCT", "Відсотки, процентні значення"),
        "PERIOD": EntityConfig("PERIOD", "Часові періоди"),
        "DOC": EntityConfig("DOC", "Номери документів, посвідчень"),
        "QUANT": EntityConfig("QUANT", "Кількісні показники"),
        "ART": EntityConfig("ART", "Назви творів, артефактів"),
        "MISC": EntityConfig("MISC", "Інші іменовані сутності")
    })
    
    # Presidio pattern сутності з описами
    PRESIDIO_PATTERN_ENTITIES: Dict[str, EntityConfig] = field(default_factory=lambda: {
        "EMAIL_ADDRESS": EntityConfig("EMAIL_ADDRESS", "Email адреси"),
        "PHONE_NUMBER": EntityConfig("PHONE_NUMBER", "Телефонні номери"),
        "CREDIT_CARD": EntityConfig("CREDIT_CARD", "Номери банківських карток"),
        "IBAN_CODE": EntityConfig("IBAN_CODE", "IBAN коди (UA...)"),
        "IP_ADDRESS": EntityConfig("IP_ADDRESS", "IP адреси"),
        "URL": EntityConfig("URL", "Веб-посилання, URL"),
        "CRYPTO": EntityConfig("CRYPTO", "Криптовалютні гаманці"),
        "DATE_TIME": EntityConfig("DATE_TIME", "Дата і час разом")
    })
    
    def get_enabled_ukrainian_entities(self) -> List[str]:
        """Повертає список активних українських сутностей."""
        return [
            name for name, config in self.UKRAINIAN_ENTITIES.items() 
            if config.enabled
        ]
    
    def get_enabled_presidio_entities(self) -> List[str]:
        """Повертає список активних Presidio сутностей."""
        return [
            name for name, config in self.PRESIDIO_PATTERN_ENTITIES.items() 
            if config.enabled
        ]
    
    def update_entity_state(self, entity_type: str, enabled: bool) -> None:
        """Оновлює стан активності сутності."""
        if entity_type in self.UKRAINIAN_ENTITIES:
            self.UKRAINIAN_ENTITIES[entity_type].enabled = enabled
        elif entity_type in self.PRESIDIO_PATTERN_ENTITIES:
            self.PRESIDIO_PATTERN_ENTITIES[entity_type].enabled = enabled
    
    def get_all_enabled_entities(self) -> List[str]:
        """Повертає всі активні сутності (NER + Presidio)."""
        return (
            self.get_enabled_ukrainian_entities() + 
            self.get_enabled_presidio_entities()
        )


# Глобальний екземпляр конфігурації
config = AppConfig()