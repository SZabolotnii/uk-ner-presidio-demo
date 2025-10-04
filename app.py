"""
Точка входу для Ukrainian NER + Presidio Demo.

Архітектурна стратегія: Мінімальна точка входу.
Вся бізнес-логіка винесена в окремі модулі.

Design Principle: "app.py повинен бути настільки простим,
щоб його можна було прочитати за 30 секунд"
"""

import logging
import sys

from ui.gradio_interface import create_interface
from recognizers.ukrainian_ner import UkrainianNERRecognizer  # NEW



def setup_logging():
    """
    Конфігурація логування для всієї системи.
    
    Strategy: Централізоване логування для спрощення debugging
    та моніторингу в production.
    """
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            # У production додати FileHandler:
            # logging.FileHandler('app.log')
        ]
    )
    
    # Знижуємо verbosity сторонніх бібліотек
    logging.getLogger("transformers").setLevel(logging.WARNING)
    logging.getLogger("huggingface_hub").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def warmup_models():
    """
    CRITICAL: Завантажуємо модель ДО запуску Gradio server.
    
    Strategy: Eager initialization для синхронізації з HF Spaces health check.
    """
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("WARMUP: Pre-loading Ukrainian NER model...")
    logger.info("=" * 60)
    
    try:
        # Примусово викликаємо завантаження
        recognizer = UkrainianNERRecognizer()
        recognizer._load_model()  # Explicit load
        
        logger.info("✓ Model loaded successfully and cached in memory")
        logger.info("=" * 60)
    except Exception as e:
        logger.error(f"✗ Model warmup failed: {e}", exc_info=True)
        # Продовжуємо, але логуємо

def validate_environment():
    """
    CRITICAL: Pre-flight environment validation.
    
    Catches dependency issues before user interaction.
    """
    logger = logging.getLogger(__name__)
    
    try:
        import gradio as gr
        import spacy
        import presidio_analyzer
        
        # Version reporting
        logger.info(f"Gradio: {gr.__version__}")
        logger.info(f"spaCy: {spacy.__version__}")
        
        # Compatibility checks
        from core.dependencies import GradioCompatibility
        GradioCompatibility.validate_compatibility()
        
        logger.info("✓ Environment validation passed")
        
    except Exception as e:
        logger.error(f"✗ Environment validation failed: {e}")
        # Continue anyway - fail gracefully at runtime        

def main():
    setup_logging()
    validate_environment() 
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 60)
    logger.info("Ukrainian NER + Presidio Demo - Starting")
    logger.info("=" * 60)
    
    try:
        # PHASE 1: Warmup (CRITICAL for HF Spaces)
        warmup_models()
        
        # PHASE 2: Create UI
        interface = create_interface()
        
        # PHASE 3: Launch
        interface.launch()
        
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()