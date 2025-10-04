"""
Dependency version management and compatibility layer.

Strategic Purpose: Centralize version-specific workarounds and provide
abstraction over external library breaking changes.
"""

import sys
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class GradioCompatibility:
    """
    Gradio version compatibility adapter.
    
    Design Pattern: Adapter for handling API changes across versions.
    """
    
    @staticmethod
    def has_download_button() -> bool:
        """Check if current Gradio version supports DownloadButton."""
        try:
            import gradio as gr
            return hasattr(gr, "DownloadButton")
        except ImportError:
            return False
    
    @staticmethod
    def get_version() -> Optional[str]:
        """Get installed Gradio version."""
        try:
            import gradio
            return gradio.__version__
        except (ImportError, AttributeError):
            return None
    
    @staticmethod
    def validate_compatibility() -> None:
        """
        Validate that installed versions meet requirements.
        
        Raises:
            RuntimeError: If incompatible versions detected
        """
        version = GradioCompatibility.get_version()
        
        if version is None:
            raise RuntimeError("Gradio not installed")
        
        # Example: Enforce minimum version
        if version < "4.26.0":
            logger.warning(
                f"Gradio {version} detected. "
                f"Recommended: 4.26.0 for stability"
            )


# Run validation on import
try:
    GradioCompatibility.validate_compatibility()
except Exception as e:
    logger.error(f"Dependency validation failed: {e}")
    # Don't crash - allow app to attempt startup