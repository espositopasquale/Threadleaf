import json
import re
import ollama
from functools import lru_cache
import numpy as np
from pathlib import Path
from . import retrieval

SCHEMA = {
    "type": "object",
    "properties": {"passage": {"type": "integer", "minimum": 0}},
    "required": ["passage"],
    "additionalProperties": False,
}
INSTRUCTIONS = """
Select the single PASSAGE that directly answers the exact QUESTION.
Return JSON {"passage": NUMBER}. Return {"passage": 0} if no passage answers it.
Do not substitute a different concept, section or number. A related topic is not
necessarily an answer. Do not write a summary: the application shows the original
passage to prevent unsupported paraphrases.
"""


def _unit_vectors(values):
    vectors = np.asarray(values, dtype=float)
    lengths = np.linalg.norm(vectors, axis=1, keepdims=True)
    if not np.isfinite(vectors).all() or np.any(lengths == 0):
        raise ValueError("Invalid intent embeddings")
    return vectors / lengths


@lru_cache(maxsize=2)
def _intent_classifier(model):
    # Learn a boundary on full sentence embeddings. These are labeled training
    # utterances, not phrases matched against a message at runtime.
    dataset = json.loads((Path(__file__).parent / "data" / "intent_training.json").read_text(encoding="utf-8"))
    examples = [(text, 1.0 if intent == "social" else -1.0)
                for intent, texts in dataset.items() for text in texts]
    embeddings = ollama.embed(model=model, input=[text for text, _ in examples])["embeddings"]
    vectors = _unit_vectors(embeddings)
    if len(vectors) != len(examples):
        raise ValueError("Unexpected training embedding count")
    features = np.column_stack((vectors, np.ones(len(vectors))))
    labels = np.array([label for _, label in examples])
    # Dual ridge regression keeps the solve small despite large embedding vectors.
    return features.T @ np.linalg.solve(features @ features.T + 0.05 * np.eye(len(features)), labels)


def is_casual(question: str, model: str, history: list[dict] | None = None) -> bool:
   
    try:
        classifier = _intent_classifier(model)
        message = _unit_vectors(ollama.embed(model=model, input=[question])["embeddings"])[0]
        score = np.append(message, 1.0) @ classifier
        return bool(score > 0)
    except Exception:
        return False


def render(content: str, chunks: list[dict], requested_language: str, question: str = "", max_semantic_distance: float = 0.65) -> tuple[str, str]:
    language = requested_language.lower()
    english = language in {"en", "english"} or (language == "auto" and bool(re.search(r"\b(what|when|how|which|where|define|does|is|are)\b", question.lower())))
    try:
        data = json.loads(content)
        index = data.get("passage") if isinstance(data, dict) else None
    except (ValueError, TypeError):
        index = None
    if isinstance(index, int) and not isinstance(index, bool) and 1 <= index <= len(chunks) and question:
        chosen = chunks[index - 1]
        matches = set(retrieval.tokens(question)) & set(retrieval.tokens(chosen["text"]))
        distance = chosen.get("distance")
        if (distance is not None and distance > max_semantic_distance) or (distance is None and not matches):
            index = None
    if isinstance(index, int) and not isinstance(index, bool) and 1 <= index <= len(chunks):
        original = chunks[index - 1]["text"]
        text = " ".join(original.split())
        terms = set(retrieval.tokens(question))
        headings = [set(retrieval.tokens(title)) for title in re.findall(r"\(([^()\n]{2,100})\)", text)]
        if terms and headings:
            topic = max(headings, key=lambda heading: len(terms & heading) / max(len(heading), len(terms), 1))
            if len(terms & topic) / max(len(terms), 1) >= 0.5:
                terms &= topic
        sentences = []
        for match in re.finditer(r"(?m)(?:^[ \t(]*|(?<=[.!?])[ \t]+)([A-ZÀ-ÖØ-Þ][^.!?]{25,}[.!?])", original):
            part = match[1]
            first_line = part.splitlines()[0]
            if len(re.findall(r"[^\W_]+", part)) >= 6 and first_line != first_line.upper():
                sentences.append(" ".join(part.split()))
        if terms and sentences:
            ranked = [(len(terms & set(retrieval.tokens(sentence))), sentence)
                      for sentence in sentences]
            best = max(ranked, key=lambda item: item[0])
            if best[0] > 0:
                text = best[1]
        label = "From the selected document:" if english else "Dal documento selezionato:"
        return label + "\n\n> " + text, "document"
    return ("The retrieved passages do not provide enough information for a verifiable answer."
            if english else "I passaggi recuperati non forniscono informazioni sufficienti per una risposta verificabile."), "insufficient"
