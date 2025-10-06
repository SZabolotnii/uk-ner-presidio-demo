"""
Hugging Face Spaces Entry Point: Interactive Review Mode

Architecture Strategy: HF Spaces-optimized deployment
- Port management: Delegated to platform
- Resource constraints: Optimized model loading
- User experience: Clear value proposition
"""

import logging
import sys
import os

from core.analyzer import HybridAnalyzer
from ui.interactive_review import create_interactive_review_interface


def setup_logging():
    """HF Spaces logging configuration"""
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
    """
    CRITICAL for HF Spaces: Pre-load before health check
    
    HF Spaces expects fast startup (<60s for health check)
    """
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("WARMUP: Pre-loading Ukrainian NER model...")
    logger.info("=" * 60)
    
    try:
        from recognizers.ukrainian_ner import UkrainianNERRecognizer
        recognizer = UkrainianNERRecognizer()
        recognizer._load_model()
        logger.info("✓ Model loaded successfully")
        logger.info("=" * 60)
    except Exception as e:
        logger.error(f"✗ Model warmup failed: {e}", exc_info=True)


def main():
    """
    Main entry point optimized for HF Spaces
    
    Strategic Decisions:
    - No explicit port configuration (HF manages this)
    - Graceful error handling for platform constraints
    - Clear user-facing messaging
    """
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 60)
    logger.info("Interactive Review UI - Starting on Hugging Face Spaces")
    logger.info("=" * 60)
    
    try:
        # Phase 1: Model warmup
        warmup_models()
        
        # Phase 2: Initialize analyzer
        analyzer = HybridAnalyzer()
        
        # Phase 3: Create UI
        interface = create_interactive_review_interface(analyzer)
        
        # Phase 4: Launch
        # HF Spaces Configuration:
        # - server_name="0.0.0.0" (required for external access)
        # - No server_port (platform manages this)
        # - show_error=True (helpful for debugging)
        
        interface.launch(
            server_name="0.0.0.0",  # Required for HF Spaces
            show_error=True,
            # share=False is default, HF provides public URL automatically
        )
        
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()