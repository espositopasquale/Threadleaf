
from . import coreference


def standalone_question(question: str, history: list[dict], config: dict | None = None) -> str:
    return coreference.resolve(question, history, config or {})
