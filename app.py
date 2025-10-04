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


def main():
    """
    Головна функція запуску.
    
    Workflow:
    1. Налаштування logging
    2. Створення UI через factory
    3. Запуск Gradio сервера
    """
    # Налаштовуємо логування
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 60)
    logger.info("Ukrainian NER + Presidio Demo - Starting")
    logger.info("=" * 60)
    
    try:
        # Створюємо інтерфейс через factory function
        interface = create_interface()
        
        # Запускаємо Gradio
        # Для production можна додати параметри:
        # - auth=("username", "password") для аутентифікації
        # - share=True для публічного доступу
        # - server_name="0.0.0.0" для зовнішнього доступу
        interface.launch()
        
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()