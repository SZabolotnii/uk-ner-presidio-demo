# ========================================
# ui/__init__.py
# ========================================
"""
User Interface: Gradio інтерфейс.

Separation of Concerns: UI знає про core, але core не знає про UI.
"""
from ui.gradio_interface import GradioInterface, create_interface

__all__ = [
    "GradioInterface",
    "create_interface"
]