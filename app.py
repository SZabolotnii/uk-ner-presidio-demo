import gradio as gr
import spacy
from huggingface_hub import snapshot_download
from presidio_analyzer import AnalyzerEngine
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
    "IBAN_CODE",          # UA213223130000026007233566001
    "IP_ADDRESS",         # 192.168.1.1
    "URL",                # https://example.com
    "CRYPTO",             # 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa
    "DATE_TIME",          # може конфліктувати з DATE/TIME від uk_ner
]

def analyze_and_anonymize(text):
    """
    Гібридний підхід:
    1. Спочатку використовуємо українську NER модель
    2. Потім додаємо Presidio pattern-based recognizers
    3. Об'єднуємо результати і анонімізуємо
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
    # Аналізуємо текст через Presidio для структурованих патернів
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

    # ============ КРОК 3: Об'єднана Анонімізація ============
    # Видаляємо дублікати (якщо сутності перетинаються)
    presidio_results = _remove_overlapping_entities(presidio_results)
    
    anonymized = anonymizer.anonymize(text, presidio_results, operators)

    # Форматування виводу
    ents_str = "\n".join(
        [f"{r.entity_type}: '{text[r.start:r.end]}' (score={r.score:.2f})"
         for r in presidio_results]
    )
    
    return ents_str, anonymized.text

def _remove_overlapping_entities(results):
    """
    Видаляє сутності, що перетинаються, залишаючи ті, що мають вищий score.
    Критично для уникнення конфліктів між українською моделлю і Presidio.
    """
    if not results:
        return results
    
    # Сортуємо за початковою позицією
    sorted_results = sorted(results, key=lambda x: (x.start, -x.score))
    
    filtered = []
    for result in sorted_results:
        # Перевіряємо чи не перетинається з вже доданими
        overlaps = False
        for existing in filtered:
            if not (result.end <= existing.start or result.start >= existing.end):
                overlaps = True
                break
        
        if not overlaps:
            filtered.append(result)
    
    return filtered

demo = gr.Interface(
    fn=analyze_and_anonymize,
    inputs=gr.Textbox(
        label="Український текст", 
        lines=20, 
        placeholder="Введіть текст (може містити email, телефони, карти)"
    ),
    outputs=[
        gr.Textbox(label="Знайдені сутності", lines=10),
        gr.Textbox(label="Анонімізований текст", lines=20)
    ],
    title="Український NER + Presidio Pattern Detection",
    description="Гібридна система: українська NER модель + Presidio для email, телефонів, карток"
)

if __name__ == "__main__":
    demo.launch()