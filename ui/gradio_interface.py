"""
Градо інтерфейс для системи деідентифікації.

Архітектурна стратегія: Відокремлення UI від бізнес-логіки.
UI шар тільки відповідає за взаємодію з користувачем та
делегує всю обробку до core.analyzer.

Design Principles:
- Мінімальна логіка в UI (тільки форматування та валідація)
- Чітке розділення відповідальностей
- User-friendly error handling
- File I/O isolation (handlers/exporters)

ENHANCED VERSION: Додано підтримку завантаження файлів (TXT/DOCX) 
та експорту результатів у різних форматах.
"""

import logging
import os
import socket
from typing import Dict, List, Tuple, Optional

import gradio as gr

from core.config import config
from core.analyzer import HybridAnalyzer, AnalysisResult

# NEW: File I/O imports
from utils.file_handlers import FileHandler, FileReadResult, sanitize_text
from utils.file_exporters import FileExporter, ExportFormat, generate_filename

logger = logging.getLogger(__name__)


class GradioInterface:
    """
    Wrapper для Gradio інтерфейсу з підтримкою налаштувань сутностей.
    
    Архітектурний підхід: Stateful UI wrapper над stateless analyzer.
    Зберігає стан вибраних сутностей між викликами.
    
    ENHANCED: Додано file upload/export capabilities з повною ізоляцією
    від core business logic.
    """
    
    def __init__(self):
        """Ініціалізація з глобальною конфігурацією."""
        self.analyzer = HybridAnalyzer()
        self.config = config

        # Початковий стан: всі сутності активовані
        self.enabled_ukrainian = set(self.config.UKRAINIAN_ENTITIES.keys())
        self.enabled_presidio = set(self.config.PRESIDIO_PATTERN_ENTITIES.keys())

        # Gradio 4.14.0 не має DownloadButton, тому використовуємо fallback
        self._has_download_button = hasattr(gr, "DownloadButton")
        if not self._has_download_button:
            logger.warning(
                "Gradio DownloadButton unavailable; falling back to File components for downloads"
            )

        logger.info("GradioInterface initialized with file I/O support")
    
    def _format_error(self, error: Exception) -> Tuple[str, str]:
        """
        Форматує помилку для відображення користувачу.
        
        User Experience: Приховує технічні деталі, показує зрозумілі повідомлення.
        
        Args:
            error: Exception об'єкт
            
        Returns:
            Tuple з повідомленнями для обох панелей виводу
        """
        error_message = f"❌ Помилка: {str(error)}"
        
        # Додаємо підказки для типових помилок
        if "порожній" in str(error).lower():
            error_message += "\n\n💡 Введіть текст для аналізу"
        elif "завеликий" in str(error).lower():
            error_message += f"\n\n💡 Максимальний розмір: {config.MAX_TEXT_LENGTH} символів"
        elif "модель" in str(error).lower():
            error_message += "\n\n💡 Спробуйте перезавантажити сторінку"
        
        return error_message, ""
    
    # ============================================================
    # CORE ANALYSIS METHODS (ORIGINAL + ENHANCED)
    # ============================================================
    
    def analyze_text(self, text: str) -> Tuple[str, str]:
        """
        Обробляє текст через analyzer та форматує результати.
        
        LEGACY METHOD: Збережено для backwards compatibility.
        Для нових features використовуйте analyze_text_with_export().
        
        Workflow:
        1. Перевірка чи хоч якісь сутності активовані
        2. Виклик analyzer з поточними налаштуваннями
        3. Форматування результатів для UI
        
        Args:
            text: Текст від користувача
            
        Returns:
            Tuple: (formatted_entities, anonymized_text)
        """
        try:
            # Перевірка чи є активні сутності
            if not self.enabled_ukrainian and not self.enabled_presidio:
                return (
                    "⚠️ Жодна сутність не активована.\n"
                    "Перейдіть на вкладку 'Налаштування' і виберіть типи даних для деідентифікації.",
                    text
                )
            
            # Виконуємо аналіз
            result: AnalysisResult = self.analyzer.analyze(
                text=text,
                ukrainian_entities=list(self.enabled_ukrainian),
                presidio_entities=list(self.enabled_presidio),
                conflict_strategy="priority"
            )
            
            # Форматуємо результати
            entities_display = self._format_entities_display(result)
            
            return entities_display, result.anonymized_text
            
        except Exception as e:
            logger.error(f"Analysis failed: {e}", exc_info=True)
            return self._format_error(e)
    
    def analyze_text_with_export(
        self, 
        text: str
    ) -> Tuple[str, str, Optional[AnalysisResult]]:
        """
        ENHANCED: Розширена версія analyze_text з state preservation.
        
        Ключова відмінність: Повертає AnalysisResult для подальшого експорту.
        Це дозволяє UI зберігати результат в gr.State без повторного аналізу.
        
        Architecture Pattern: Command Query Responsibility Segregation (CQRS)
        - Query: Форматовані результати для відображення
        - Command: Raw результат для подальших операцій
        
        Args:
            text: Текст від користувача
            
        Returns:
            Tuple: (entities_display, anonymized_text, result_object)
        """
        try:
            # Перевірка чи є активні сутності
            if not self.enabled_ukrainian and not self.enabled_presidio:
                return (
                    "⚠️ Жодна сутність не активована.\n"
                    "Перейдіть на вкладку 'Налаштування' і виберіть типи даних.",
                    text,
                    None
                )
            
            # Виконуємо аналіз
            result: AnalysisResult = self.analyzer.analyze(
                text=text,
                ukrainian_entities=list(self.enabled_ukrainian),
                presidio_entities=list(self.enabled_presidio),
                conflict_strategy="priority"
            )
            
            # Форматуємо для відображення
            entities_display = self._format_entities_display(result)
            
            # КРИТИЧНО: Повертаємо також result для state
            return entities_display, result.anonymized_text, result
            
        except Exception as e:
            logger.error(f"Analysis failed: {e}", exc_info=True)
            error_msg = self._format_error(e)
            return error_msg[0], error_msg[1], None
    
    def _format_entities_display(self, result: AnalysisResult) -> str:
        """
        Форматує знайдені сутності для красивого відображення.
        
        UX Strategy: Структурований, читабельний вивід з метриками.
        
        Args:
            result: Результат аналізу
            
        Returns:
            Форматований текст для відображення
        """
        if result.entities_count == 0:
            return (
                "✅ Сутностей не знайдено\n\n"
                "Текст не містить персональних даних вибраних типів."
            )
        
        # Заголовок з метриками
        header = (
            f"🔍 Знайдено сутностей: {result.entities_count}\n"
            f"{'=' * 60}\n\n"
        )
        
        # Групуємо за типами
        entities_by_type: Dict[str, List] = {}
        for entity in result.entities:
            if entity.entity_type not in entities_by_type:
                entities_by_type[entity.entity_type] = []
            entities_by_type[entity.entity_type].append(entity)
        
        # Форматуємо кожну групу
        sections = []
        for entity_type, entities in sorted(entities_by_type.items()):
            # Отримуємо опис типу з конфігу
            description = self._get_entity_description(entity_type)
            
            section_header = f"📌 {entity_type} ({description})"
            section_items = []
            
            for idx, entity in enumerate(sorted(entities, key=lambda x: x.start), 1):
                entity_text = result.original_text[entity.start:entity.end]
                item = (
                    f"   {idx}. '{entity_text}' "
                    f"[позиція {entity.start}:{entity.end}, "
                    f"впевненість {entity.score:.0%}]"
                )
                section_items.append(item)
            
            sections.append(section_header + "\n" + "\n".join(section_items))
        
        return header + "\n\n".join(sections)
    
    def _get_entity_description(self, entity_type: str) -> str:
        """
        Отримує опис сутності з конфігурації.

        Args:
            entity_type: Тип сутності

        Returns:
            Опис сутності
        """
        if entity_type in self.config.UKRAINIAN_ENTITIES:
            return self.config.UKRAINIAN_ENTITIES[entity_type].description
        elif entity_type in self.config.PRESIDIO_PATTERN_ENTITIES:
            return self.config.PRESIDIO_PATTERN_ENTITIES[entity_type].description
        return "Невідомий тип"

    def _download_response(self, file_path: Optional[str]):
        """
        Формує відповідь для компонентів завантаження з урахуванням версії Gradio.
        """
        if self._has_download_button:
            return file_path

        if file_path:
            return gr.File.update(value=file_path, visible=True)

        return gr.File.update(value=None, visible=False)
    
    # ============================================================
    # FILE I/O METHODS (NEW)
    # ============================================================
    
    def process_file_upload(
        self, 
        file_obj
    ) -> Tuple[str, str]:
        """
        NEW: Обробляє завантажений файл та витягує текст.
        
        Architecture Pattern: Adapter Pattern
        Конвертує Gradio file object → normalized text через FileHandler.
        
        Workflow:
        1. Validation (file exists, supported format)
        2. Delegation to FileHandler (format detection)
        3. Text sanitization (encoding normalization)
        4. UI feedback (status, extracted text)
        
        Args:
            file_obj: File object від gr.File компонента
            
        Returns:
            Tuple: (extracted_text, status_message)
        """
        if file_obj is None:
            return "", "⚠️ Файл не вибрано"
        
        try:
            # Делегуємо читання до FileHandler
            result: FileReadResult = FileHandler.read_file(file_obj.name)
            
            # Санітизуємо текст (encoding, line endings, whitespace)
            clean_text = sanitize_text(result.text)
            
            # Формуємо user-friendly status
            status = (
                f"✅ Файл завантажено успішно!\n\n"
                f"📄 Назва: {result.filename}\n"
                f"📊 Тип: {result.file_type.upper()}\n"
                f"📏 Символів: {result.char_count:,}\n"
            )
            
            if result.encoding:
                status += f"🔤 Кодування: {result.encoding}\n"
            
            logger.info(
                f"File processed successfully: {result.filename}, "
                f"{result.char_count} chars, {result.file_type}"
            )
            
            return clean_text, status
            
        except Exception as e:
            error_msg = (
                f"❌ Помилка завантаження файлу\n\n"
                f"Деталі: {str(e)}\n\n"
                f"💡 Перевірте:\n"
                f"• Формат файлу (підтримуються: TXT, DOCX)\n"
                f"• Розмір файлу (макс. {FileHandler.MAX_FILE_SIZE_MB} MB)\n"
                f"• Кодування файлу (рекомендується UTF-8)"
            )
            
            logger.error(f"File upload failed: {e}", exc_info=True)
            return "", error_msg
    
    def export_anonymized_text(
        self,
        result_state: Optional[AnalysisResult],
        export_format: str
    ) -> Optional[str]:
        """
        NEW: Експортує анонімізований текст у вибраному форматі.
        
        Architecture Pattern: Strategy Pattern через FileExporter.
        UI layer не знає деталей експорту - делегує до exporters.
        
        Args:
            result_state: Збережений результат аналізу з gr.State
            export_format: Формат експорту (txt/docx/md)
            
        Returns:
            Шлях до згенерованого файлу для Gradio download
        """
        if result_state is None:
            logger.warning("Export attempted without analysis results")
            gr.Warning("⚠️ Спочатку виконайте аналіз тексту")
            return self._download_response(None)

        try:
            # Делегуємо експорт до FileExporter
            file_bytes = FileExporter.export_anonymized_text(
                result_state,
                format=export_format,
                include_metadata=True
            )
            
            # Генеруємо filename з timestamp
            filename = generate_filename(
                base_name="deidentified",
                format=export_format,
                include_timestamp=True
            )
            
            # Зберігаємо тимчасово для Gradio download
            temp_path = f"/tmp/{filename}"
            with open(temp_path, 'wb') as f:
                f.write(file_bytes)

            logger.info(f"Exported anonymized text as {export_format}: {filename}")

            return self._download_response(temp_path)

        except Exception as e:
            logger.error(f"Export failed: {e}", exc_info=True)
            gr.Warning(f"❌ Помилка експорту: {str(e)}")
            return self._download_response(None)
    
    def export_entities_report(
        self,
        result_state: Optional[AnalysisResult],
        export_format: str
    ) -> Optional[str]:
        """
        NEW: Експортує звіт про знайдені сутності.
        
        Args:
            result_state: Збережений результат аналізу
            export_format: Формат експорту (json/csv/txt)
            
        Returns:
            Шлях до згенерованого файлу
        """
        if result_state is None:
            logger.warning("Export attempted without analysis results")
            gr.Warning("⚠️ Спочатку виконайте аналіз тексту")
            return self._download_response(None)
        
        try:
            file_bytes = FileExporter.export_entities_report(
                result_state,
                format=export_format
            )
            
            filename = generate_filename(
                base_name="entities_report",
                format=export_format,
                include_timestamp=True
            )
            
            temp_path = f"/tmp/{filename}"
            with open(temp_path, 'wb') as f:
                f.write(file_bytes)

            logger.info(f"Exported entities report as {export_format}: {filename}")

            return self._download_response(temp_path)

        except Exception as e:
            logger.error(f"Export failed: {e}", exc_info=True)
            gr.Warning(f"❌ Помилка експорту: {str(e)}")
            return self._download_response(None)
    
    def export_full_report(
        self,
        result_state: Optional[AnalysisResult],
        export_format: str
    ) -> Optional[str]:
        """
        NEW: Експортує повний звіт (текст + сутності + статистика).
        
        Args:
            result_state: Збережений результат аналізу
            export_format: Формат експорту (docx/md/txt)
            
        Returns:
            Шлях до згенерованого файлу
        """
        if result_state is None:
            logger.warning("Export attempted without analysis results")
            gr.Warning("⚠️ Спочатку виконайте аналіз тексту")
            return self._download_response(None)
        
        try:
            file_bytes = FileExporter.export_full_report(
                result_state,
                format=export_format
            )
            
            filename = generate_filename(
                base_name="full_report",
                format=export_format,
                include_timestamp=True
            )
            
            temp_path = f"/tmp/{filename}"
            with open(temp_path, 'wb') as f:
                f.write(file_bytes)

            logger.info(f"Exported full report as {export_format}: {filename}")

            return self._download_response(temp_path)

        except Exception as e:
            logger.error(f"Export failed: {e}", exc_info=True)
            gr.Warning(f"❌ Помилка експорту: {str(e)}")
            return self._download_response(None)
    
    # ============================================================
    # SETTINGS MANAGEMENT (ORIGINAL - UNCHANGED)
    # ============================================================
    
    def update_settings(
        self,
        ukrainian_checkboxes: List[str],
        presidio_checkboxes: List[str]
    ) -> str:
        """
        Оновлює налаштування активних сутностей.
        
        State Management: Зберігає стан в пам'яті між викликами analyze.
        
        Args:
            ukrainian_checkboxes: Вибрані українські сутності
            presidio_checkboxes: Вибрані Presidio сутності
            
        Returns:
            Повідомлення про успішне оновлення
        """
        self.enabled_ukrainian = set(ukrainian_checkboxes)
        self.enabled_presidio = set(presidio_checkboxes)
        
        # Синхронізуємо з глобальним конфігом
        for entity_type in self.config.UKRAINIAN_ENTITIES:
            self.config.update_entity_state(
                entity_type, 
                entity_type in self.enabled_ukrainian
            )
        
        for entity_type in self.config.PRESIDIO_PATTERN_ENTITIES:
            self.config.update_entity_state(
                entity_type, 
                entity_type in self.enabled_presidio
            )
        
        total_enabled = len(self.enabled_ukrainian) + len(self.enabled_presidio)
        
        logger.info(
            f"Settings updated: {len(self.enabled_ukrainian)} NER, "
            f"{len(self.enabled_presidio)} Presidio"
        )
        
        return (
            f"✅ Налаштування збережено!\n\n"
            f"Активовано типів сутностей: {total_enabled}\n"
            f"• Українських NER: {len(self.enabled_ukrainian)}\n"
            f"• Presidio patterns: {len(self.enabled_presidio)}"
        )
    
    # ============================================================
    # UI CONSTRUCTION (ENHANCED)
    # ============================================================
    
    def build_interface(self) -> gr.Blocks:
        """
        ENHANCED: Створює повний Gradio інтерфейс з file I/O підтримкою.
        
        UI Architecture Evolution:
        - Tab 1: Аналіз тексту (ENHANCED: + file upload/export)
        - Tab 2: Налаштування (ORIGINAL: unchanged)
        
        Design Strategy: Progressive Enhancement
        - Core functionality (manual text input) залишається простою
        - Advanced features (file I/O) доступні через додаткові UI elements
        - Zero impact на існуючий user flow
        
        Returns:
            Gradio Blocks інтерфейс
        """
        with gr.Blocks(
            title="Українська система деідентифікації",
            theme=gr.themes.Soft(),
            css="""
                .entity-checkbox { margin: 5px 0; }
                .settings-column { padding: 10px; }
                .file-upload-section { 
                    border: 2px dashed #ccc; 
                    padding: 20px; 
                    border-radius: 8px;
                    background-color: #f9f9f9;
                    margin-bottom: 20px;
                }
                .export-section {
                    background-color: #f0f7ff;
                    padding: 15px;
                    border-radius: 8px;
                    margin-top: 20px;
                }
            """
        ) as interface:
            
            gr.Markdown(
                """
                # 🛡️ Українська система деідентифікації
                
                **Гібридний підхід:** Трансформерна NER модель + Rule-based Presidio patterns
                
                Автоматично виявляє та анонімізує персональні дані в українському тексті.
                **Новинка:** Підтримка завантаження файлів (TXT/DOCX) та експорту результатів!
                """
            )
            
            # ============ STATE для збереження результатів ============
            # Critical: Зберігає AnalysisResult між викликами для export
            analysis_result_state = gr.State(value=None)
            
            # ============ ВКЛАДКА 1: АНАЛІЗ (ENHANCED) ============
            with gr.Tab("🔍 Аналіз тексту"):
                gr.Markdown(
                    """
                    ### Як використовувати:
                    1. **Завантажте файл** (TXT/DOCX) або **введіть текст** вручну
                    2. Натисніть "Деідентифікувати"
                    3. Перегляньте результати та **завантажте** у потрібному форматі
                    
                    💡 Налаштуйте типи даних на вкладці "Налаштування"
                    """
                )
                
                # ===== СЕКЦІЯ ЗАВАНТАЖЕННЯ ФАЙЛУ (NEW) =====
                with gr.Group(elem_classes="file-upload-section"):
                    gr.Markdown("### 📁 Завантаження файлу (опціонально)")
                    
                    with gr.Row():
                        file_upload = gr.File(
                            label="Виберіть файл",
                            file_types=[".txt", ".docx"],
                            type="filepath"
                        )
                        
                        file_status = gr.Textbox(
                            label="Статус завантаження",
                            interactive=False,
                            lines=5,
                            placeholder="Виберіть TXT або DOCX файл для автоматичного витягування тексту..."
                        )
                
                gr.Markdown("---")
                
                # ===== КНОПКА АНАЛІЗУ =====
                analyze_btn = gr.Button(
                    "🚀 Деідентифікувати",
                    variant="primary",
                    size="lg"
                )
                
                # ===== ПАНЕЛІ РЕЗУЛЬТАТІВ =====
                with gr.Row(equal_height=True):
                    with gr.Column(scale=1):
                        input_text = gr.Textbox(
                            label="Вхідний текст",
                            placeholder=(
                                "Вставте текст або завантажте файл вище...\n\n"
                                "Приклад:\n"
                                "Іван Петренко працює в ТОВ 'Приватбанк'.\n"
                                "Email: ivan.petrenko@example.com\n"
                                "Телефон: +380501234567\n"
                                "IBAN: UA213223130000026007233566001"
                            ),
                            lines=12,
                            max_lines=20
                        )
                    
                    with gr.Column(scale=1):
                        anonymized_output = gr.Textbox(
                            label="🔒 Анонімізований текст",
                            lines=12,
                            show_copy_button=True,
                            interactive=False
                        )
                        
                        entities_output = gr.Textbox(
                            label="📋 Знайдені сутності",
                            lines=12,
                            show_copy_button=True,
                            interactive=False
                        )
                
                # ===== СЕКЦІЯ ЕКСПОРТУ (NEW) =====
                with gr.Group(elem_classes="export-section"):
                    gr.Markdown("### 💾 Завантаження результатів")
                    gr.Markdown(
                        "*Після аналізу тексту ви можете завантажити результати "
                        "у різних форматах. Виберіть тип звіту та формат.*"
                    )

                    with gr.Row():
                        # Експорт анонімізованого тексту
                        with gr.Column():
                            gr.Markdown("**📄 Анонімізований текст**")
                            text_format = gr.Radio(
                                choices=["txt", "docx", "md"],
                                value="txt",
                                label="Формат",
                                info="Тільки анонімізований текст"
                            )
                            if self._has_download_button:
                                download_text_btn = gr.DownloadButton(
                                    "⬇️ Завантажити текст",
                                    variant="secondary",
                                    size="sm"
                                )
                                download_text_output = download_text_btn
                            else:
                                download_text_btn = gr.Button(
                                    "⬇️ Згенерувати файл",
                                    variant="secondary",
                                    size="sm"
                                )
                                download_text_output = gr.File(
                                    label="⬇️ Завантажити текст",
                                    interactive=False,
                                    visible=False
                                )

                        # Експорт звіту про сутності
                        with gr.Column():
                            gr.Markdown("**📊 Звіт про сутності**")
                            entities_format = gr.Radio(
                                choices=["json", "csv", "txt"],
                                value="json",
                                label="Формат",
                                info="Список знайдених PII даних"
                            )
                            if self._has_download_button:
                                download_entities_btn = gr.DownloadButton(
                                    "⬇️ Завантажити звіт",
                                    variant="secondary",
                                    size="sm"
                                )
                                download_entities_output = download_entities_btn
                            else:
                                download_entities_btn = gr.Button(
                                    "⬇️ Згенерувати звіт",
                                    variant="secondary",
                                    size="sm"
                                )
                                download_entities_output = gr.File(
                                    label="⬇️ Завантажити звіт",
                                    interactive=False,
                                    visible=False
                                )

                        # Експорт повного звіту
                        with gr.Column():
                            gr.Markdown("**📑 Повний звіт**")
                            report_format = gr.Radio(
                                choices=["docx", "md", "txt"],
                                value="docx",
                                label="Формат",
                                info="Текст + сутності + статистика"
                            )
                            if self._has_download_button:
                                download_report_btn = gr.DownloadButton(
                                    "⬇️ Завантажити звіт",
                                    variant="primary",
                                    size="sm"
                                )
                                download_report_output = download_report_btn
                            else:
                                download_report_btn = gr.Button(
                                    "⬇️ Згенерувати повний звіт",
                                    variant="primary",
                                    size="sm"
                                )
                                download_report_output = gr.File(
                                    label="⬇️ Завантажити повний звіт",
                                    interactive=False,
                                    visible=False
                                )
                
                # ===== ПРИКЛАДИ =====
                gr.Examples(
                    examples=[
                        [
                            "Іван Петренко (ivan.petrenko@example.com) "
                            "працює в компанії ТОВ 'Приват' на посаді директора. "
                            "Його телефон: +380501234567"
                        ],
                        [
                            "Рахунок для оплати: UA213223130000026007233566001\n"
                            "Картка: 4111111111111111\n"
                            "Сума: 15000 грн"
                        ],
                        [
                            "Зустріч відбудеться 15 березня 2024 року о 14:30 "
                            "за адресою: вул. Хрещатик, 22, Київ"
                        ]
                    ],
                    inputs=input_text,
                    label="📌 Приклади для тестування",
                    cache_examples=False,
                )
                
                # ============ EVENT HANDLERS ============
                
                # File upload → text extraction
                file_upload.change(
                    fn=self.process_file_upload,
                    inputs=[file_upload],
                    outputs=[input_text, file_status]
                )
                
                # Text analysis (ENHANCED: зберігає результат в state)
                analyze_btn.click(
                    fn=self.analyze_text_with_export,
                    inputs=[input_text],
                    outputs=[entities_output, anonymized_output, analysis_result_state]
                )
                
                # Export handlers
                download_text_btn.click(
                    fn=self.export_anonymized_text,
                    inputs=[analysis_result_state, text_format],
                    outputs=[download_text_output]
                )

                download_entities_btn.click(
                    fn=self.export_entities_report,
                    inputs=[analysis_result_state, entities_format],
                    outputs=[download_entities_output]
                )

                download_report_btn.click(
                    fn=self.export_full_report,
                    inputs=[analysis_result_state, report_format],
                    outputs=[download_report_output]
                )
            
            # ============ ВКЛАДКА 2: НАЛАШТУВАННЯ (ORIGINAL - UNCHANGED) ============
            with gr.Tab("⚙️ Налаштування"):
                gr.Markdown(
                    """
                    ### Налаштування типів даних для деідентифікації
                    
                    Виберіть які типи персональних даних система повинна шукати та анонімізувати.
                    Зміни застосовуються відразу після натискання кнопки "Зберегти".
                    """
                )
                
                with gr.Row(equal_height=True):
                    # ===== КОЛОНКА 1: Українська NER =====
                    with gr.Column(scale=1, elem_classes="settings-column"):
                        gr.Markdown("### 🇺🇦 Українська NER модель")
                        gr.Markdown(
                            "*Розпізнавання іменованих сутностей на основі "
                            "глибокого навчання*"
                        )
                        
                        ukrainian_checks = gr.CheckboxGroup(
                            choices=[
                                (f"{key} - {cfg.description}", key)
                                for key, cfg in self.config.UKRAINIAN_ENTITIES.items()
                            ],
                            value=list(self.enabled_ukrainian),
                            label="Виберіть типи сутностей",
                            elem_classes="entity-checkbox"
                        )
                    
                    # ===== КОЛОНКА 2: Presidio Patterns =====
                    with gr.Column(scale=1, elem_classes="settings-column"):
                        gr.Markdown("### 🔍 Presidio Pattern Detection")
                        gr.Markdown(
                            "*Розпізнавання на основі регулярних виразів "
                            "та шаблонів*"
                        )
                        
                        presidio_checks = gr.CheckboxGroup(
                            choices=[
                                (f"{key} - {cfg.description}", key)
                                for key, cfg in self.config.PRESIDIO_PATTERN_ENTITIES.items()
                            ],
                            value=list(self.enabled_presidio),
                            label="Виберіть типи шаблонів",
                            elem_classes="entity-checkbox"
                        )
                
                # Кнопка збереження
                save_settings_btn = gr.Button(
                    "💾 Зберегти налаштування",
                    variant="primary",
                    size="lg"
                )
                
                settings_status = gr.Textbox(
                    label="Статус",
                    interactive=False,
                    lines=4
                )
                
                # Обробка події
                save_settings_btn.click(
                    fn=self.update_settings,
                    inputs=[ukrainian_checks, presidio_checks],
                    outputs=[settings_status]
                )
                
                # Інформація
                gr.Markdown(
                    """
                    ---
                    ### 📖 Пояснення
                    
                    **Українська NER модель** використовує глибоке навчання (трансформери) 
                    для розпізнавання складних патернів у тексті. Працює з контекстом.
                    
                    **Presidio Patterns** використовує регулярні вирази для точного 
                    знаходження формалізованих даних (email, телефони, картки тощо).
                    
                    **Рекомендація:** Активуйте обидва типи для найкращих результатів.
                    """
                )
        
        return interface
    
    # ============================================================
    # LAUNCH INFRASTRUCTURE (ORIGINAL - UNCHANGED)
    # ============================================================
    
    def launch(self, **kwargs) -> None:
        """
        Запускає Gradio інтерфейс.
        
        Args:
            **kwargs: Параметри для demo.launch()
        """
        interface = self.build_interface()
        
        # Налаштування за замовчуванням
        launch_config = {
            "share": False,
            "server_name": "127.0.0.1",
            "server_port": 7860,
            "show_error": True
        }
        launch_config.update(kwargs)

        resolved_port = self._resolve_server_port(
            host=launch_config.get("server_name", "127.0.0.1"),
            requested_port=launch_config.get("server_port")
        )

        launch_config["server_port"] = resolved_port

        logger.info(
            "Launching Gradio interface on %s:%s",
            launch_config.get("server_name", "127.0.0.1"),
            launch_config.get("server_port") or "auto"
        )
        interface.launch(**launch_config)

    def _resolve_server_port(self, host: str, requested_port: int | None) -> int | None:
        """Підбирає доступний порт для запуску Gradio."""
        candidates = []

        env_port = os.getenv("GRADIO_SERVER_PORT")
        if env_port:
            try:
                env_port_int = int(env_port)
                candidates.append(env_port_int)
            except ValueError:
                logger.warning(
                    "GRADIO_SERVER_PORT=%s не є числом — ігноруємо значення",
                    env_port
                )

        if requested_port is not None:
            candidates.append(int(requested_port))

        default_start = 7860
        default_range = range(default_start, default_start + 10)
        for port in default_range:
            candidates.append(port)

        candidates.append(None)  # Дозволяємо Gradio самостійно обрати порт

        seen = set()
        unique_candidates = []
        for candidate in candidates:
            if candidate not in seen:
                unique_candidates.append(candidate)
                seen.add(candidate)

        for candidate in unique_candidates:
            if candidate is None:
                logger.warning(
                    "Не вдалося знайти вільний порт у діапазоні, передаємо управління Gradio"
                )
                return None

            if self._is_port_available(host, candidate):
                if requested_port is not None and candidate != requested_port:
                    logger.warning(
                        "Порт %s зайнятий. Використовуємо %s",
                        requested_port,
                        candidate,
                    )
                return candidate

        raise RuntimeError("Не знайдено вільного порту для запуску Gradio")

    @staticmethod
    def _is_port_available(host: str, port: int) -> bool:
        """Перевіряє, чи вільний вказаний порт."""
        normalized_host = host or "127.0.0.1"
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((normalized_host, port))
            except OSError:
                return False
        return True


def create_interface() -> GradioInterface:
    """
    Factory function для створення інтерфейсу.
    
    Design Pattern: Factory для спрощення створення в app.py
    
    Returns:
        Налаштований GradioInterface з повною підтримкою file I/O
    """
    return GradioInterface()
