# ========================================
# utils/__init__.py
# ========================================
"""
Utilities: допоміжні функції та алгоритми.

Design Pattern: Stateless utility functions для переважування.
"""
from utils.conflict_resolution import (
    remove_overlapping_entities,
    ScoreBasedResolver,
    PriorityBasedResolver
)

__all__ = [
    "remove_overlapping_entities",
    "ScoreBasedResolver",
    "PriorityBasedResolver"
]