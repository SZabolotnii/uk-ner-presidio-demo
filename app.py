import gradio as gr
import spacy
from huggingface_hub import snapshot_download
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

MODEL_REPO = "dchaplinsky/uk_ner_web_trf_13class"


def _load_spacy_model() -> "spacy.language.Language":
    # snapshot_download ensures we have a local copy (cached across runs).
    local_model_dir = snapshot_download(repo_id=MODEL_REPO)
    return spacy.load(local_model_dir)


nlp = _load_spacy_model()

# Presidio Anonymizer
anonymizer = AnonymizerEngine()

SUPPORTED = [
    "PERS","ORG","LOC","DATE","TIME","JOB","MON","PCT",
    "PERIOD","DOC","QUANT","ART","MISC"
]

def analyze_and_anonymize(text):
    doc = nlp(text)
    presidio_results = []
    operators = {}

    for ent in doc.ents:
        ent_type = ent.label_
        if ent_type not in SUPPORTED:
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

    anonymized = anonymizer.anonymize(text, presidio_results, operators)

    ents_str = "\n".join(
        [f"{r.entity_type}: '{text[r.start:r.end]}' (score={r.score:.2f})"
         for r in presidio_results]
    )
    return ents_str, anonymized.text

demo = gr.Interface(
    fn=analyze_and_anonymize,
    inputs=gr.Textbox(label="Український текст", lines=20, placeholder="Введіть текст"),
    outputs=[
        gr.Textbox(label="Знайдені сутності", lines=10),
        gr.Textbox(label="Анонімізований текст", lines=20)
    ],
    title="Український NER + Presidio анонімізація",
    # description="Модель dchaplinsky/uk_ner_web_trf_13class інтегрована з Presidio Anonymizer."
)

if __name__ == "__main__":
    demo.launch()
