"""
Інтелектуальне розв'язання конфліктів між перетинаючимися сутностями.

Архітектурна стратегія: Модульний, розширюваний алгоритм з можливістю
додавання нових стратегій розв'язання конфліктів.
"""

from typing import List, Protocol
from presidio_analyzer import RecognizerResult


class ConflictResolutionStrategy(Protocol):
    """Протокол для стратегій розв'язання конфліктів."""
    
    def resolve(self, results: List[RecognizerResult]) -> List[RecognizerResult]:
        """Розв'язує конфлікти між сутностями."""
        ...


class ScoreBasedResolver:
    """
    Розв'язування на основі score: вибирає сутності з найвищим score.
    
    Стратегія: При перетині двох сутностей залишається та, що має
    вищий score впевненості. Це найпростіший та найнадійніший підхід.
    """
    
    @staticmethod
    def resolve(results: List[RecognizerResult]) -> List[RecognizerResult]:
        """
        Видаляє перетинаючі сутності, зберігаючи ті що мають вищий score.
        
        Args:
            results: Список розпізнаних сутностей
            
        Returns:
            Список сутностей без перетинів
        """
        if not results:
            return results

        # Спочатку беремо найвищий score незалежно від позиції
        sorted_results = sorted(
            results,
            key=lambda x: (-x.score, x.start, x.end)
        )

        filtered = []
        for result in sorted_results:
            has_overlap = any(
                not (result.end <= existing.start or result.start >= existing.end)
                for existing in filtered
            )

            if not has_overlap:
                filtered.append(result)

        # Повертаємо у порядку зростання позиції для стабільності
        return sorted(filtered, key=lambda x: x.start)


class PriorityBasedResolver:
    """
    Розв'язування на основі пріоритетів типів сутностей.
    
    Стратегія: Деякі типи сутностей мають вищий пріоритет.
    Наприклад, IBAN_CODE важливіший за MISC.
    """
    
    # Пріоритети: менше число = вищий пріоритет
    ENTITY_PRIORITIES = {
        # High priority PII
        "CREDIT_CARD": 1,
        "IBAN_CODE": 1,
        "EMAIL_ADDRESS": 2,
        "PHONE_NUMBER": 2,
        "CRYPTO": 2,
        
        # Personal data
        "PERS": 3,
        "DOC": 3,
        
        # Organizations and locations
        "ORG": 4,
        "LOC": 4,
        
        # Other
        "DATE": 5,
        "TIME": 5,
        "MISC": 10
    }
    
    @staticmethod
    def resolve(results: List[RecognizerResult]) -> List[RecognizerResult]:
        """
        Розв'язує конфлікти на основі пріоритетів типів.
        
        При перетині вибирає сутність з вищим пріоритетом (нижчим числом).
        Якщо пріоритети однакові - вибирає з вищим score.
        """
        if not results:
            return results

        def get_priority(result: RecognizerResult) -> int:
            return PriorityBasedResolver.ENTITY_PRIORITIES.get(
                result.entity_type,
                100  # За замовчуванням низький пріоритет
            )

        sorted_results = sorted(
            results,
            key=lambda x: (get_priority(x), -x.score, x.start, x.end)
        )

        filtered = []
        for result in sorted_results:
            has_overlap = any(
                not (result.end <= existing.start or result.start >= existing.end)
                for existing in filtered
            )

            if not has_overlap:
                filtered.append(result)

        return sorted(filtered, key=lambda x: x.start)


def remove_overlapping_entities(
    results: List[RecognizerResult],
    strategy: str = "score"
) -> List[RecognizerResult]:
    """
    Публічний API для розв'язання конфліктів.
    
    Args:
        results: Список розпізнаних сутностей
        strategy: Стратегія розв'язання ("score" або "priority")
        
    Returns:
        Список сутностей без перетинів
        
    Raises:
        ValueError: Якщо strategy невідома
    """
    resolvers = {
        "score": ScoreBasedResolver,
        "priority": PriorityBasedResolver
    }
    
    if strategy not in resolvers:
        raise ValueError(
            f"Unknown strategy '{strategy}'. "
            f"Available: {list(resolvers.keys())}"
        )
    
    resolver = resolvers[strategy]
    return resolver.resolve(results)
