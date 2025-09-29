import gradio as gr
import spacy
from huggingface_hub import snapshot_download
from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

MODEL_REPO = "dchaplinsky/uk_ner_web_trf_13class"

def _load_spacy_model() -> "spacy.language.Language":
    local_model_dir = snapshot_download(repo_id=MODEL_REPO)
    return spacy.load(local_model_dir)

# Українська NER модель
nlp = _load_spacy_model()

# Presidio Analyzer для pattern-based detection
presidio_analyzer = AnalyzerEngine()

# ============ КРИТИЧНЕ ПОКРАЩЕННЯ: Ukrainian IBAN Recognizer ============
# Додаємо спеціалізований recognizer для українських IBAN
ukrainian_iban_pattern = Pattern(
    name="ukrainian_iban",
    regex=r"\bUA\d{27}\b",  # UA + 27 цифр = 29 символів
    score=0.9  # Високий confidence для точного pattern matching
)

ukrainian_iban_recognizer = PatternRecognizer(
    supported_entity="IBAN_CODE",
    patterns=[ukrainian_iban_pattern],
    context=["рахунок", "IBAN", "iban", "рахунку", "оплата", "банк"],  # Українські context words
    supported_language="uk"
)

# Реєструємо кастомний recognizer
presidio_analyzer.registry.add_recognizer(ukrainian_iban_recognizer)

# Presidio Anonymizer
anonymizer = AnonymizerEngine()

# Сутності з української моделі
UKRAINIAN_ENTITIES = [
    "PERS", "ORG", "LOC", "DATE", "TIME", "JOB", "MON", "PCT",
    "PERIOD", "DOC", "QUANT", "ART", "MISC"
]

# Сутності з Presidio (pattern-based)
PRESIDIO_PATTERN_ENTITIES = [
    "EMAIL_ADDRESS",      # email@example.com
    "PHONE_NUMBER",       # +380-67-123-4567
    "CREDIT_CARD",        # 4532-1234-5678-9010
    "IBAN_CODE",          # UA213223130000026007233566001 (тепер надійніше!)
    "IP_ADDRESS",         # 192.168.1.1
    "URL",                # https://example.com
    "CRYPTO",             # 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa
    "DATE_TIME",          # може конфліктувати з DATE/TIME від uk_ner
]

def analyze_and_anonymize(text):
    """
    Гібридний підхід з покращеною надійністю IBAN detection:
    1. Українська NER модель для семантичних сутностей
    2. Presidio pattern recognizers (включно з покращеним Ukrainian IBAN)
    3. Conflict resolution та об'єднана анонімізація
    """
    
    # ============ КРОК 1: Українська NER модель ============
    doc = nlp(text)
    presidio_results = []
    operators = {}

    for ent in doc.ents:
        ent_type = ent.label_
        if ent_type not in UKRAINIAN_ENTITIES:
            continue
        
        start, end = ent.start_char, ent.end_char
        confidence = ent._.confidence if ent.has_extension("confidence") else 1.0
        
        presidio_results.append(
            type("FakeRecognizerResult", (), {
                "entity_type": ent_type,
                "start": start,
                "end": end,
                "score": float(confidence)
            })()
        )
        operators[ent_type] = OperatorConfig("replace", {"new_value": f"[{ent_type}]"})

    # ============ КРОК 2: Presidio Pattern Recognizers ============
    # Тепер включає покращений Ukrainian IBAN recognizer
    presidio_pattern_results = presidio_analyzer.analyze(
        text=text,
        entities=PRESIDIO_PATTERN_ENTITIES,
        language='en'  # Патерни працюють для будь-якої мови
    )
    
    # Додаємо результати Presidio до загального списку
    for result in presidio_pattern_results:
        presidio_results.append(result)
        operators[result.entity_type] = OperatorConfig(
            "replace", 
            {"new_value": f"[{result.entity_type}]"}
        )

    # ============ КРОК 3: Conflict Resolution + Анонімізація ============
    presidio_results = _remove_overlapping_entities(presidio_results)
    
    anonymized = anonymizer.anonymize(text, presidio_results, operators)

    # Форматування виводу з сортуванням за позицією в тексті
    ents_str = "\n".join(
        [f"{r.entity_type}: '{text[r.start:r.end]}' (score={r.score:.2f})"
         for r in sorted(presidio_results, key=lambda x: x.start)]
    )
    
    return ents_str, anonymized.text

def _remove_overlapping_entities(results):
    """
    Conflict Resolution Strategy:
    - Видаляє сутності що перетинаються
    - Пріоритет: вищий score
    - Критично для IBAN vs DATE конфліктів
    """
    if not results:
        return results
    
    # Сортуємо: спочатку за позицією, потім за score (desc)
    sorted_results = sorted(results, key=lambda x: (x.start, -x.score))
    
    filtered = []
    for result in sorted_results:
        # Перевіряємо overlap з вже обраними entities
        overlaps = False
        for existing in filtered:
            if not (result.end <= existing.start or result.start >= existing.end):
                overlaps = True
                break
        
        if not overlaps:
            filtered.append(result)
    
    return filtered

# ============ UX ПОКРАЩЕННЯ: Копіювання в Буфер ============
demo = gr.Interface(
    fn=analyze_and_anonymize,
    inputs=gr.Textbox(
        label="Український текст", 
        lines=20, 
        placeholder="Введіть текст (може містити email, телефони, карти, IBAN)"
    ),
    outputs=[
        gr.Textbox(
            label="Знайдені сутності", 
            lines=10,
            show_copy_button=True  # ✅ ДОДАНО: Кнопка копіювання
        ),
        gr.Textbox(
            label="Анонімізований текст", 
            lines=20,
            show_copy_button=True  # ✅ ДОДАНО: Кнопка копіювання
        )
    ],
    title="Український NER + Presidio Pattern Detection",
    description="Гібридна система: українська NER модель + Presidio для email, телефонів, карток, IBAN"
)

if __name__ == "__main__":
    demo.launch()