"""
Unit tests для HybridAnalyzer.

Архітектура тестів:
- Організація: Arrange-Act-Assert pattern
- Ізоляція: Кожен тест незалежний
- Швидкість: Мінімальне завантаження моделі (використовуємо mocks де можливо)

Запуск:
    pytest tests/test_analyzer.py -v
    pytest tests/test_analyzer.py::TestHybridAnalyzer::test_basic_analysis -v
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

# Імпортуємо модулі для тестування
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.analyzer import HybridAnalyzer, AnalysisResult
from core.config import config
from presidio_analyzer import RecognizerResult


class TestHybridAnalyzer:
    """Тести для головного аналізатора."""
    
    @pytest.fixture
    def analyzer(self):
        """Фікстура: створює HybridAnalyzer для кожного тесту."""
        return HybridAnalyzer()
    
    # ============ ТЕСТИ ВАЛІДАЦІЇ ============
    
    def test_empty_text_raises_error(self, analyzer):
        """Тест: порожній текст викликає ValueError."""
        with pytest.raises(ValueError, match="порожній"):
            analyzer.analyze("")
    
    def test_whitespace_only_text_raises_error(self, analyzer):
        """Тест: текст з тільки пробілами викликає ValueError."""
        with pytest.raises(ValueError, match="порожній"):
            analyzer.analyze("   \n\t  ")
    
    def test_text_too_long_raises_error(self, analyzer):
        """Тест: занадто довгий текст викликає ValueError."""
        long_text = "A" * (config.MAX_TEXT_LENGTH + 1)
        
        with pytest.raises(ValueError, match="завеликий"):
            analyzer.analyze(long_text)
    
    def test_max_length_text_accepted(self, analyzer):
        """Тест: текст максимальної довжини приймається."""
        # Використовуємо mock щоб не завантажувати модель
        with patch.object(analyzer.ner_recognizer, 'analyze', return_value=[]):
            with patch.object(analyzer.pattern_recognizer, 'analyze', return_value=[]):
                max_text = "A" * config.MAX_TEXT_LENGTH
                result = analyzer.analyze(max_text)
                
                assert isinstance(result, AnalysisResult)
    
    # ============ ТЕСТИ ФУНКЦІОНАЛЬНОСТІ ============
    
    @patch('recognizers.ukrainian_ner.UkrainianNERRecognizer.analyze')
    @patch('recognizers.presidio_patterns.PresidioPatternRecognizer.analyze')
    def test_basic_analysis(self, mock_presidio, mock_ner, analyzer):
        """Тест: базовий аналіз працює коректно."""
        # Arrange: налаштовуємо mocks
        mock_ner.return_value = [
            RecognizerResult(entity_type="PERS", start=0, end=5, score=0.95)
        ]
        mock_presidio.return_value = [
            RecognizerResult(entity_type="EMAIL_ADDRESS", start=10, end=25, score=1.0)
        ]
        
        # Act: викликаємо аналіз
        text = "Іван ivan@test.com"
        result = analyzer.analyze(text)
        
        # Assert: перевіряємо результати
        assert isinstance(result, AnalysisResult)
        assert result.entities_count == 2
        assert result.original_text == text
        assert len(result.entities) == 2
    
    @patch('recognizers.ukrainian_ner.UkrainianNERRecognizer.analyze')
    @patch('recognizers.presidio_patterns.PresidioPatternRecognizer.analyze')
    def test_no_entities_found(self, mock_presidio, mock_ner, analyzer):
        """Тест: коректна обробка тексту без сутностей."""
        # Arrange
        mock_ner.return_value = []
        mock_presidio.return_value = []
        
        # Act
        result = analyzer.analyze("Звичайний текст без PII")
        
        # Assert
        assert result.entities_count == 0
        assert len(result.entities) == 0
        assert result.anonymized_text == "Звичайний текст без PII"
    
    @patch('recognizers.ukrainian_ner.UkrainianNERRecognizer.analyze')
    @patch('recognizers.presidio_patterns.PresidioPatternRecognizer.analyze')
    def test_selective_entity_types(self, mock_presidio, mock_ner, analyzer):
        """Тест: вибіркова активація типів сутностей."""
        # Arrange
        mock_ner.return_value = []
        mock_presidio.return_value = []
        
        # Act: запит тільки на PERS та EMAIL
        result = analyzer.analyze(
            text="Тестовий текст",
            ukrainian_entities=["PERS"],
            presidio_entities=["EMAIL_ADDRESS"]
        )
        
        # Assert: перевіряємо що викликано з правильними параметрами
        mock_ner.assert_called_once()
        assert mock_ner.call_args[0][1] == ["PERS"]
        
        mock_presidio.assert_called_once()
        assert mock_presidio.call_args[0][1] == ["EMAIL_ADDRESS"]
    
    # ============ ТЕСТИ АНОНІМІЗАЦІЇ ============
    
    @patch('recognizers.ukrainian_ner.UkrainianNERRecognizer.analyze')
    @patch('recognizers.presidio_patterns.PresidioPatternRecognizer.analyze')
    def test_anonymization_format(self, mock_presidio, mock_ner, analyzer):
        """Тест: формат анонімізації коректний."""
        # Arrange
        mock_ner.return_value = [
            RecognizerResult(entity_type="PERS", start=0, end=4, score=0.95)
        ]
        mock_presidio.return_value = []
        
        # Act
        result = analyzer.analyze("Іван працює")
        
        # Assert: перевіряємо що формат [ENTITY_TYPE]
        assert "[PERS]" in result.anonymized_text
        assert "Іван" not in result.anonymized_text
    
    # ============ ТЕСТИ КОНФЛІКТ RESOLUTION ============
    
    @patch('recognizers.ukrainian_ner.UkrainianNERRecognizer.analyze')
    @patch('recognizers.presidio_patterns.PresidioPatternRecognizer.analyze')
    def test_overlapping_entities_resolved(self, mock_presidio, mock_ner, analyzer):
        """Тест: перетинаючі сутності розв'язуються коректно."""
        # Arrange: створюємо перетинаючі сутності
        mock_ner.return_value = [
            RecognizerResult(entity_type="PERS", start=0, end=10, score=0.9)
        ]
        mock_presidio.return_value = [
            RecognizerResult(entity_type="EMAIL_ADDRESS", start=5, end=15, score=0.95)
        ]
        
        # Act
        result = analyzer.analyze("Test overlap text")
        
        # Assert: залишилась тільки одна (з вищим score)
        assert result.entities_count == 1
        assert result.entities[0].entity_type == "EMAIL_ADDRESS"  # Вищий score
    
    # ============ ТЕСТИ ФОРМАТУВАННЯ ============
    
    @patch('recognizers.ukrainian_ner.UkrainianNERRecognizer.analyze')
    @patch('recognizers.presidio_patterns.PresidioPatternRecognizer.analyze')
    def test_format_entities_list(self, mock_presidio, mock_ner, analyzer):
        """Тест: форматування списку сутностей."""
        # Arrange
        mock_ner.return_value = [
            RecognizerResult(entity_type="PERS", start=0, end=4, score=0.95)
        ]
        mock_presidio.return_value = []
        
        # Act
        result = analyzer.analyze("Іван працює")
        formatted = result.format_entities_list()
        
        # Assert
        assert "PERS" in formatted
        assert "Іван" in formatted
        assert "0.95" in formatted or "95%" in formatted
    
    # ============ ТЕСТИ ПОМИЛОК ============
    
    @patch('recognizers.ukrainian_ner.UkrainianNERRecognizer.analyze')
    def test_ner_error_handling(self, mock_ner, analyzer):
        """Тест: обробка помилок NER не ламає весь процес."""
        # Arrange: NER викидає помилку
        mock_ner.side_effect = RuntimeError("NER failed")
        
        # Act & Assert: аналіз продовжується з Presidio
        with patch('recognizers.presidio_patterns.PresidioPatternRecognizer.analyze', return_value=[]):
            # Не викидає помилку, але логує і продовжує
            result = analyzer.analyze("Тестовий текст")
            assert isinstance(result, AnalysisResult)


class TestAnalysisResult:
    """Тести для AnalysisResult dataclass."""
    
    def test_analysis_result_creation(self):
        """Тест: створення AnalysisResult."""
        entities = [
            RecognizerResult(entity_type="PERS", start=0, end=4, score=0.95)
        ]
        
        result = AnalysisResult(
            entities=entities,
            anonymized_text="[PERS] text",
            original_text="Іван text",
            entities_count=1
        )
        
        assert result.entities_count == 1
        assert len(result.entities) == 1
        assert result.original_text == "Іван text"
    
    def test_format_entities_empty(self):
        """Тест: форматування порожнього списку."""
        result = AnalysisResult(
            entities=[],
            anonymized_text="text",
            original_text="text",
            entities_count=0
        )
        
        formatted = result.format_entities_list()
        assert "не знайдено" in formatted.lower()


class TestConfigIntegration:
    """Інтеграційні тести з конфігурацією."""
    
    def test_config_entity_state_toggle(self):
        """Тест: зміна стану сутності в config."""
        # Arrange
        original_state = config.UKRAINIAN_ENTITIES["PERS"].enabled
        
        try:
            # Act
            config.update_entity_state("PERS", False)
            
            # Assert
            assert config.UKRAINIAN_ENTITIES["PERS"].enabled is False
            assert "PERS" not in config.get_enabled_ukrainian_entities()
            
            # Act: відновлюємо
            config.update_entity_state("PERS", True)
            
            # Assert
            assert config.UKRAINIAN_ENTITIES["PERS"].enabled is True
            assert "PERS" in config.get_enabled_ukrainian_entities()
            
        finally:
            # Cleanup: завжди відновлюємо стан
            config.update_entity_state("PERS", original_state)


# ============ ІНТЕГРАЦІЙНІ ТЕСТИ (ПОТРЕБУЮТЬ МОДЕЛІ) ============

@pytest.mark.integration
class TestRealModelIntegration:
    """
    Інтеграційні тести з реальною моделлю.
    
    Запуск: pytest tests/test_analyzer.py -v -m integration
    
    Примітка: Ці тести завантажують реальну модель (повільні, ~5s startup)
    """
    
    @pytest.fixture(scope="class")
    def real_analyzer(self):
        """Фікстура: реальний аналізатор з моделлю (завантажується один раз)."""
        return HybridAnalyzer()
    
    def test_real_ukrainian_text(self, real_analyzer):
        """Тест: реальний український текст."""
        text = "Іван Петренко працює в компанії ТОВ 'Приват'"
        result = real_analyzer.analyze(text)
        
        # Перевіряємо що хоч щось знайдено
        assert result.entities_count > 0
        
        # Перевіряємо анонімізацію
        assert "Іван Петренко" not in result.anonymized_text or "[PERS]" in result.anonymized_text
    
    def test_real_presidio_patterns(self, real_analyzer):
        """Тест: реальні Presidio patterns."""
        text = "Email: test@example.com, Phone: +380501234567"
        result = real_analyzer.analyze(
            text,
            ukrainian_entities=[],
            presidio_entities=["EMAIL_ADDRESS", "PHONE_NUMBER"]
        )
        
        assert result.entities_count >= 1  # Хоча б email має знайтись
        assert "test@example.com" not in result.anonymized_text


# ============ HELPER FUNCTIONS ============

def create_mock_recognizer_result(entity_type, start, end, score=0.9):
    """Helper: створює mock RecognizerResult для тестів."""
    return RecognizerResult(
        entity_type=entity_type,
        start=start,
        end=end,
        score=score
    )


if __name__ == "__main__":
    # Запуск тестів напряму
    pytest.main([__file__, "-v", "--tb=short"])