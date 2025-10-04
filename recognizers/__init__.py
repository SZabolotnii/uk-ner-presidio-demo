# ========================================
# recognizers/__init__.py
# ========================================
"""
Recognizers: NER та pattern-based detection.

Архітектурна ізоляція: кожен recognizer є самодостатнім модулем.
"""
from recognizers.ukrainian_ner import UkrainianNERRecognizer
from recognizers.presidio_patterns import PresidioPatternRecognizer

__all__ = [
    "UkrainianNERRecognizer",
    "PresidioPatternRecognizer"
]