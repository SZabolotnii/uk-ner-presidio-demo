# ui/interactive_review.py
"""
Interactive Review Interface: Human-in-the-Loop DeID

Architecture Strategy: Hybrid approach combining native Gradio
with enhanced user experience for manual entity confirmation.

Design Pattern: Two-Stage Workflow
1. Automatic Detection → Visual Review
2. Manual Confirmation → Selective Anonymization

Extensibility: Foundation for future custom JS components

FIX: Added cache_examples=False to gr.Examples() for Gradio 4.26.0 compatibility
"""

import logging
from typing import List, Tuple, Dict, Optional
import gradio as gr
from dataclasses import dataclass

from core.analyzer import HybridAnalyzer, AnalysisResult
from presidio_analyzer import RecognizerResult

logger = logging.getLogger(__name__)


@dataclass
class EntityReviewItem:
    """
    Structured representation для review UI
    
    Design: Immutable data object для client-server communication
    """
    index: int
    entity_type: str
    text: str
    start: int
    end: int
    confidence: float
    confirmed: bool = True  # За замовчуванням підтверджена


class InteractiveReviewUI:
    """
    Enhanced UI for manual review and confirmation of detected entities
    
    Architecture Principle: Separation of Concerns
    - Detection: Delegated to HybridAnalyzer
    - Review: UI-specific logic (this class)
    - Anonymization: Delegated back to analyzer with filtered entities
    """
    
    # Color scheme для різних станів
    COLOR_MAP = {
        "PERS": "#90EE90",      # Light green
        "ORG": "#87CEEB",       # Sky blue
        "LOC": "#FFB6C1",       # Light pink
        "EMAIL_ADDRESS": "#DDA0DD",  # Plum
        "PHONE_NUMBER": "#F0E68C",   # Khaki
        "IBAN_CODE": "#FFA07A",      # Light salmon
    }
    
    DEFAULT_COLOR = "#B0E0E6"  # Powder blue
    
    def __init__(self, analyzer: HybridAnalyzer):
        self.analyzer = analyzer
    
    def build_interface(self) -> gr.Blocks:
        """
        Constructs full interactive review interface
        
        UX Strategy: Progressive disclosure
        - Step 1: Simple input + detect
        - Step 2: Visual review with controls
        - Step 3: Selective anonymization
        """
        with gr.Blocks(
            title="Інтерактивний редактор деідентифікації",
            theme=gr.themes.Soft()
        ) as interface:
            
            gr.Markdown(
                """
                # 🔍 Інтерактивний редактор деідентифікації
                
                **Human-in-the-Loop підхід**: Ви контролюєте що анонімізувати
                
                ### Як використовувати:
                1. Введіть текст та натисніть **"Знайти сутності"**
                2. Перегляньте знайдені дані з підсвічуванням
                3. **Зніміть галочки** з тих сутностей, які НЕ потрібно анонімізувати
                4. Натисніть **"Анонімізувати вибрані"**
                """
            )
            
            # === STATE MANAGEMENT ===
            detected_entities_state = gr.State([])  # List[RecognizerResult]
            review_items_state = gr.State([])       # List[EntityReviewItem]
            
            # === STEP 1: INPUT ===
            with gr.Group():
                gr.Markdown("### Крок 1: Введіть текст")
                input_text = gr.Textbox(
                    label="Текст для аналізу",
                    placeholder="Іван Петренко (ivan@example.com) працює в ТОВ 'Приват'...",
                    lines=8
                )
                
                detect_btn = gr.Button(
                    "🔎 Знайти сутності",
                    variant="primary",
                    size="lg"
                )
            
            # === STEP 2: REVIEW ===
            with gr.Group(visible=False) as review_section:
                gr.Markdown("### Крок 2: Перегляд знайдених сутностей")
                
                with gr.Row():
                    # Left: Original with highlighting
                    with gr.Column(scale=1):
                        gr.Markdown("**Оригінал з підсвічуванням:**")
                        highlighted_display = gr.HighlightedText(
                            label="",
                            color_map=self.COLOR_MAP,
                            show_legend=True
                        )
                    
                    # Right: Confirmation checklist
                    with gr.Column(scale=1):
                        gr.Markdown(
                            "**Виберіть що анонімізувати:**\n\n"
                            "✅ Галочка = анонімізувати  \n"
                            "❌ Без галочки = залишити як є"
                        )
                        
                        entities_checklist = gr.CheckboxGroup(
                            label="",
                            choices=[],
                            value=[],
                            interactive=True
                        )
                        
                        # Додаткова інформація
                        detection_stats = gr.Markdown("")
                
                anonymize_btn = gr.Button(
                    "✅ Анонімізувати вибрані",
                    variant="primary",
                    size="lg"
                )
            
            # === STEP 3: RESULT ===
            with gr.Group(visible=False) as result_section:
                gr.Markdown("### Крок 3: Результат")
                
                with gr.Row():
                    original_output = gr.Textbox(
                        label="Оригінальний текст",
                        lines=8,
                        interactive=False
                    )
                    
                    anonymized_output = gr.Textbox(
                        label="🔒 Анонімізований текст",
                        lines=8,
                        show_copy_button=True,
                        interactive=False
                    )
                
                anonymization_summary = gr.Markdown("")
            
            # === EVENT HANDLERS ===
            
            # Detection workflow
            detect_btn.click(
                fn=self.detect_entities,
                inputs=[input_text],
                outputs=[
                    highlighted_display,
                    entities_checklist,
                    detection_stats,
                    review_section,
                    detected_entities_state,
                    review_items_state
                ]
            )
            
            # Anonymization workflow
            anonymize_btn.click(
                fn=self.selective_anonymize,
                inputs=[
                    input_text,
                    detected_entities_state,
                    entities_checklist
                ],
                outputs=[
                    original_output,
                    anonymized_output,
                    anonymization_summary,
                    result_section
                ]
            )
            
            # === EXAMPLES ===
            # ✅ FIX: Added cache_examples=False for Gradio 4.26.0 compatibility
            gr.Examples(
                examples=[
                    "Іван Петренко (ivan.petrenko@example.com) працює в ТОВ 'Приватбанк'. Телефон: +380501234567",
                    "Платіжний рахунок: UA213223130000026007233566001. Картка: 4111111111111111",
                    "Зустріч відбудеться 15 березня 2024 о 14:30 в Києві на вул. Хрещатик, 22"
                ],
                inputs=input_text,
                cache_examples=False  # ✅ CRITICAL: Required for Gradio 4.26.0 without fn/outputs
            )
        
        return interface
    
    def detect_entities(
        self,
        text: str
    ) -> Tuple:
        """
        Stage 1: Detect and prepare for review
        
        Returns:
            Tuple with all necessary outputs for UI update
        """
        if not text or not text.strip():
            return (
                [],  # highlighted_display
                gr.update(choices=[], value=[]),  # checklist
                "⚠️ Введіть текст для аналізу",  # stats
                gr.update(visible=False),  # review_section
                [],  # entities_state
                []   # review_items_state
            )
        
        try:
            # Виконуємо аналіз
            result: AnalysisResult = self.analyzer.analyze(text)
            
            if result.entities_count == 0:
                return (
                    [(text, None)],
                    gr.update(choices=[], value=[]),
                    "✅ Персональних даних не знайдено",
                    gr.update(visible=False),
                    [],
                    []
                )
            
            # Prepare highlighted text
            highlighted_data = self._build_highlighted_data(text, result.entities)
            
            # Prepare checklist with detailed info
            checklist_data, review_items = self._build_checklist_data(
                text, 
                result.entities
            )
            
            # Stats
            stats = self._format_detection_stats(result)
            
            # Default: all entities selected
            default_selection = [item.index for item in review_items]
            
            return (
                highlighted_data,
                gr.update(
                    choices=checklist_data,
                    value=default_selection
                ),
                stats,
                gr.update(visible=True),
                result.entities,
                review_items
            )
            
        except Exception as e:
            logger.error(f"Detection failed: {e}", exc_info=True)
            return (
                [],
                gr.update(choices=[], value=[]),
                f"❌ Помилка: {str(e)}",
                gr.update(visible=False),
                [],
                []
            )
    
    def selective_anonymize(
        self,
        original_text: str,
        all_entities: List[RecognizerResult],
        selected_indices: List[int]
    ) -> Tuple:
        """
        Stage 2: Anonymize only confirmed entities
        
        Architecture Pattern: Selective Processing
        """
        if not selected_indices:
            summary = (
                "⚠️ **Жодна сутність не вибрана**\n\n"
                "Текст залишається без змін."
            )
            return (
                original_text,
                original_text,
                summary,
                gr.update(visible=True)
            )
        
        try:
            # Фільтруємо entities
            confirmed_entities = [
                all_entities[idx] for idx in selected_indices
            ]
            
            # Створюємо operators
            operators = {
                entity.entity_type: self.analyzer._create_operator(entity.entity_type)
                for entity in confirmed_entities
            }
            
            # Анонімізуємо
            anonymized = self.analyzer._anonymize(
                original_text,
                confirmed_entities,
                operators
            )
            
            # Summary
            summary = self._format_anonymization_summary(
                len(all_entities),
                len(confirmed_entities),
                confirmed_entities
            )
            
            return (
                original_text,
                anonymized,
                summary,
                gr.update(visible=True)
            )
            
        except Exception as e:
            logger.error(f"Anonymization failed: {e}", exc_info=True)
            return (
                original_text,
                "",
                f"❌ Помилка анонімізації: {str(e)}",
                gr.update(visible=True)
            )
    
    # === HELPER METHODS ===
    
    def _build_highlighted_data(
        self,
        text: str,
        entities: List[RecognizerResult]
    ) -> List[Tuple[str, Optional[str]]]:
        """
        Formats data for gr.HighlightedText
        
        Returns list of (text_chunk, entity_label) tuples
        """
        sorted_entities = sorted(entities, key=lambda x: x.start)
        
        highlighted = []
        last_pos = 0
        
        for entity in sorted_entities:
            # Text before entity
            if entity.start > last_pos:
                highlighted.append((text[last_pos:entity.start], None))
            
            # Entity with label
            entity_text = text[entity.start:entity.end]
            highlighted.append((entity_text, entity.entity_type))
            
            last_pos = entity.end
        
        # Remaining text
        if last_pos < len(text):
            highlighted.append((text[last_pos:], None))
        
        return highlighted
    
    def _build_checklist_data(
        self,
        text: str,
        entities: List[RecognizerResult]
    ) -> Tuple[List[Tuple[str, int]], List[EntityReviewItem]]:
        """
        Prepares data for checkbox group
        
        Returns:
            - choices: List of (label, value) for gr.CheckboxGroup
            - review_items: Structured data for state management
        """
        choices = []
        review_items = []
        
        for idx, entity in enumerate(entities):
            entity_text = text[entity.start:entity.end]
            
            # Human-readable label
            label = (
                f"[{entity.entity_type}] '{entity_text}' "
                f"(поз. {entity.start}-{entity.end}, {entity.score:.0%})"
            )
            
            choices.append((label, idx))
            
            review_items.append(EntityReviewItem(
                index=idx,
                entity_type=entity.entity_type,
                text=entity_text,
                start=entity.start,
                end=entity.end,
                confidence=entity.score
            ))
        
        return choices, review_items
    
    def _format_detection_stats(self, result: AnalysisResult) -> str:
        """Formats detection statistics"""
        # Group by type
        by_type = {}
        for entity in result.entities:
            if entity.entity_type not in by_type:
                by_type[entity.entity_type] = 0
            by_type[entity.entity_type] += 1
        
        stats_lines = [
            f"**Знайдено: {result.entities_count} сутностей**\n",
            "Розподіл по типах:"
        ]
        
        for entity_type, count in sorted(by_type.items()):
            stats_lines.append(f"- {entity_type}: {count}")
        
        return "\n".join(stats_lines)
    
    def _format_anonymization_summary(
        self,
        total: int,
        anonymized: int,
        entities: List[RecognizerResult]
    ) -> str:
        """Formats anonymization summary"""
        kept = total - anonymized
        
        summary = [
            "### ✅ Анонімізація завершена\n",
            f"**Загальна статистика:**",
            f"- Знайдено сутностей: {total}",
            f"- Анонімізовано: {anonymized}",
            f"- Залишено без змін: {kept}",
        ]
        
        if anonymized > 0:
            summary.append("\n**Анонімізовані типи:**")
            by_type = {}
            for entity in entities:
                if entity.entity_type not in by_type:
                    by_type[entity.entity_type] = 0
                by_type[entity.entity_type] += 1
            
            for entity_type, count in sorted(by_type.items()):
                summary.append(f"- {entity_type}: {count}")
        
        return "\n".join(summary)


# === INTEGRATION POINT ===

def create_interactive_review_interface(analyzer: HybridAnalyzer) -> gr.Blocks:
    """
    Factory function for easy integration
    
    Usage in app.py:
        from ui.interactive_review import create_interactive_review_interface
        interface = create_interactive_review_interface(analyzer)
        interface.launch()
    """
    ui = InteractiveReviewUI(analyzer)
    return ui.build_interface()