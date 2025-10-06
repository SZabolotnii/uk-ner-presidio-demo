# app_interactive_review.py
"""
Standalone launcher для Interactive Review UI

Architecture Strategy: Parallel deployment pattern
- Existing app.py залишається незмінним (zero risk)
- Новий функціонал тестується окремо
- After validation → merge з основним інтерфейсом

Design Principle: "Make change safe before making change"

Usage:
    python app_interactive_review.py
    # Launches on port 7861 (не конфліктує з основним app)
"""

import logging
import sys
from pathlib import Path

# Ensure imports work
sys.path.insert(0, str(Path(__file__).parent))

from core.analyzer import HybridAnalyzer
from ui.interactive_review import create_interactive_review_interface


def setup_logging():
    """Configure logging for interactive review mode"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    
    # Suppress noisy libraries
    logging.getLogger("transformers").setLevel(logging.WARNING)
    logging.getLogger("huggingface_hub").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def warmup_models():
    """Pre-load models before UI startup"""
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("WARMUP: Pre-loading Ukrainian NER model...")
    logger.info("=" * 60)
    
    try:
        from recognizers.ukrainian_ner import UkrainianNERRecognizer
        recognizer = UkrainianNERRecognizer()
        recognizer._load_model()
        logger.info("✓ Model loaded successfully")
    except Exception as e:
        logger.error(f"✗ Model warmup failed: {e}", exc_info=True)


def main():
    """
    Main entry point for interactive review interface
    
    Architecture Decision: Separate launcher allows:
    - Independent testing
    - Different port configuration
    - Feature flags without touching main app
    """
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 60)
    logger.info("Interactive Review UI - Starting")
    logger.info("=" * 60)
    
    try:
        # Phase 1: Model warmup
        warmup_models()
        
        # Phase 2: Initialize analyzer
        analyzer = HybridAnalyzer()
        
        # Phase 3: Create UI
        interface = create_interactive_review_interface(analyzer)
        
        # Phase 4: Launch with smart port selection
        # Strategy: Try multiple ports, fallback to auto
        import socket
        
        def find_available_port(start_port=7861, max_attempts=10):
            """Find first available port starting from start_port"""
            for port in range(start_port, start_port + max_attempts):
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    try:
                        sock.bind(("0.0.0.0", port))
                        return port
                    except OSError:
                        continue
            return None  # Let Gradio choose
        
        launch_port = find_available_port(7861)
        
        if launch_port:
            logger.info(f"Launching on port {launch_port}")
            interface.launch(
                server_name="0.0.0.0",
                server_port=launch_port,
                share=False,
                show_error=True
            )
        else:
            logger.warning("All ports busy, letting Gradio choose automatically")
            interface.launch(
                server_name="0.0.0.0",
                share=False,
                show_error=True
            )
        
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()