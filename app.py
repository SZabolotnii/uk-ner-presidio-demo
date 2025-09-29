import gradio as gr
import spacy
from huggingface_hub import snapshot_download
from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from presidio_analyzer.nlp_engine import NoOpNlpEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

MODEL_REPO = "dchaplinsky/uk_ner_web_trf_13class"

def _load_spacy_model() -> "spacy.language.Language":
    local_model_dir = snapshot_download(repo_id=MODEL_REPO)
    return spacy.load(local_model_dir)

# Українська NER модель
nlp = _load_spacy_model()

# Presidio Analyzer для pattern-based detection без важкої spaCy-моделі
presidio_analyzer = AnalyzerEngine(
    nlp_engine=NoOpNlpEngine(),
    supported_languages=["en"]
)

# ============ ВИПРАВЛЕННЯ: Language-Agnostic IBAN Recognizer ============
ukrainian_iban_pattern = Pattern(
    name="ukrainian_iban",
    regex=r"\bUA\d{27}\b",
    score=0.9
)

ukrainian_iban_recognizer = PatternRecognizer(
    supported_entity="IBAN_CODE",
    patterns=[ukrainian_iban_pattern],
    context=["рахунок", "IBAN", "iban", "рахунку", "оплата", "банк", "account", "payment"],
    # Синхронізуємося з Presidio, який тепер працює в англомовному режимі
    supported_language="en"
)

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
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "CREDIT_CARD",
    "IBAN_CODE",
    "IP_ADDRESS",
    "URL",
    "CRYPTO",
    "DATE_TIME",
]

def analyze_and_anonymize(text):
    """
    Гібридний підхід з виправленим IBAN detection:
    1. Українська NER модель
    2. Presidio patterns (language-agnostic)
    3. Conflict resolution + anonymization
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
    presidio_pattern_results = presidio_analyzer.analyze(
        text=text,
        entities=PRESIDIO_PATTERN_ENTITIES,
        language='en'  # Тепер працює, бо recognizer має supported_language=None
    )
    
    for result in presidio_pattern_results:
        presidio_results.append(result)
        operators[result.entity_type] = OperatorConfig(
            "replace", 
            {"new_value": f"[{result.entity_type}]"}
        )

    # ============ КРОК 3: Conflict Resolution + Anonymization ============
    presidio_results = _remove_overlapping_entities(presidio_results)
    
    anonymized = anonymizer.anonymize(text, presidio_results, operators)

    # Форматування виводу
    ents_str = "\n".join(
        [f"{r.entity_type}: '{text[r.start:r.end]}' (score={r.score:.2f})"
         for r in sorted(presidio_results, key=lambda x: x.start)]
    )
    
    return ents_str, anonymized.text

def _remove_overlapping_entities(results):
    """
    Conflict resolution: видаляє entities що перетинаються,
    зберігаючи ті що мають вищий score.
    """
    if not results:
        return results
    
    sorted_results = sorted(results, key=lambda x: (x.start, -x.score))
    
    filtered = []
    for result in sorted_results:
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
        placeholder="Введіть текст (може містити email, телефони, карти, IBAN)"
    ),
    outputs=[
        gr.Textbox(
            label="Знайдені сутності", 
            lines=10,
            show_copy_button=True
        ),
        gr.Textbox(
            label="Анонімізований текст", 
            lines=20,
            show_copy_button=True
        )
    ],
    title="Український NER + Presidio Pattern Detection",
    description="Гібридна система: українська NER модель + Presidio для email, телефонів, карток, IBAN"
)

if __name__ == "__main__":
    demo.launch()
