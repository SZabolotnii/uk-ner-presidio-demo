# ========================================
# core/__init__.py
# ========================================
"""
Core functionality: аналіз та конфігурація.

Public API для імпорту з інших модулів.
"""
from core.config import config, AppConfig, EntityConfig
from core.analyzer import HybridAnalyzer, AnalysisResult

__all__ = [
    "config",
    "AppConfig", 
    "EntityConfig",
    "HybridAnalyzer",
    "AnalysisResult"
]