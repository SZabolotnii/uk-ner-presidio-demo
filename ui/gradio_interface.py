"""
Градio інтерфейс для системи деідентифікації.

Архітектурна стратегія: Відокремлення UI від бізнес-логіки.
UI шар тільки відповідає за взаємодію з користувачем та
делегує всю обробку до core.analyzer.

Design Principles:
- Мінімальна логіка в UI (тільки форматування та валідація)
- Чітке розділення відповідальностей
- User-friendly error handling
"""

import logging
import os
import socket
from typing import Dict, List, Tuple

import gradio as gr

from core.config import config
from core.analyzer import HybridAnalyzer, AnalysisResult

logger = logging.getLogger(__name__)


class GradioInterface:
    """
    Wrapper для Gradio інтерфейсу з підтримкою налаштувань сутностей.
    
    Архітектурний підхід: Stateful UI wrapper над stateless analyzer.
    Зберігає стан вибраних сутностей між викликами.
    """
    
    def __init__(self):
        """Ініціалізація з глобальною конфігурацією."""
        self.analyzer = HybridAnalyzer()
        self.config = config
        
        # Початковий стан: всі сутності активовані
        self.enabled_ukrainian = set(self.config.UKRAINIAN_ENTITIES.keys())
        self.enabled_presidio = set(self.config.PRESIDIO_PATTERN_ENTITIES.keys())
        
        logger.info("GradioInterface initialized")
    
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
    
    def analyze_text(self, text: str) -> Tuple[str, str]:
        """
        Обробляє текст через analyzer та форматує результати.
        
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
                conflict_strategy="priority"  # Використовуємо priority-based resolution
            )
            
            # Форматуємо результати
            entities_display = self._format_entities_display(result)
            
            return entities_display, result.anonymized_text
            
        except Exception as e:
            logger.error(f"Analysis failed: {e}", exc_info=True)
            return self._format_error(e)
    
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
    
    def build_interface(self) -> gr.Blocks:
        """
        Створює повний Gradio інтерфейс з вкладками.
        
        UI Architecture:
        - Tab 1: Аналіз тексту (основна функція)
        - Tab 2: Налаштування (вибір типів сутностей)
        
        Returns:
            Gradio Blocks інтерфейс
        """
        with gr.Blocks(
            title="Українська система деідентифікації",
            theme=gr.themes.Soft(),
            css="""
                .entity-checkbox { margin: 5px 0; }
                .settings-column { padding: 10px; }
            """
        ) as interface:
            
            gr.Markdown(
                """
                # 🛡️ Українська система деідентифікації
                
                **Гібридний підхід:** Трансформерна NER модель + Rule-based Presidio patterns
                
                Автоматично виявляє та анонімізує персональні дані в українському тексті.
                """
            )
            
            # ============ ВКЛАДКА 1: АНАЛІЗ ============
            with gr.Tab("🔍 Аналіз тексту"):
                gr.Markdown(
                    """
                    ### Як використовувати:
                    1. Вставте текст у поле нижче
                    2. Натисніть "Деідентифікувати"
                    3. Перегляньте знайдені сутності та анонімізований текст
                    
                    💡 Налаштуйте типи даних для пошуку на вкладці "Налаштування"
                    """
                )
                
                analyze_btn = gr.Button(
                    "🚀 Деідентифікувати",
                    variant="primary",
                    size="lg"
                )

                with gr.Row(equal_height=True):
                    with gr.Column(scale=1):
                        input_text = gr.Textbox(
                            label="Вхідний текст",
                            placeholder=(
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
                
                # Приклади
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
                    label="📌 Приклади для тестування"
                )
                
                # Обробка події
                analyze_btn.click(
                    fn=self.analyze_text,
                    inputs=[input_text],
                    outputs=[entities_output, anonymized_output]
                )
            
            # ============ ВКЛАДКА 2: НАЛАШТУВАННЯ ============
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
        Налаштований GradioInterface
    """
    return GradioInterface()
