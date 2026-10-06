
from functools import lru_cache
import json
import logging
import re
import threading
import time

import numpy as np
from .paths import ROOT

logger = logging.getLogger("uvicorn.error")
_lock = threading.RLock()
_retry_after = 0.0


def model_directory(config):
    return ROOT / "models" / "coreference" / config["model"].replace("/", "--") / config["revision"]


@lru_cache(maxsize=1)
def _load(model, revision, threads):
    import onnxruntime as ort
    from tokenizers import Tokenizer
    from tokenizers.pre_tokenizers import Metaspace
    folder = model_directory({"model": model, "revision": revision})
    if not all((folder / name).is_file() for name in ("model.onnx", "tokenizer.json", "config.json")):
        raise RuntimeError("Coreference files missing. Run python -m scripts.prepare_coreference")
    settings = json.loads((folder / "config.json").read_text(encoding="utf-8"))
    tokenizer = Tokenizer.from_file(str(folder / "tokenizer.json"))
    tokenizer.pre_tokenizer = Metaspace(replacement="▁", prepend_scheme="always", split=True)
    options = ort.SessionOptions()
    options.intra_op_num_threads = threads
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(folder / "model.onnx"), sess_options=options, providers=["CPUExecutionProvider"])
    return session, tokenizer, settings


def _links(words, session, tokenizer, settings):

    encoded = tokenizer.encode(words, is_pretokenized=True)
    if len(encoded.ids) > settings.get("transformer", {}).get("max_position_embeddings", 512):
        return []
    offsets = []
    for word in range(len(words)):
        positions = [i for i, value in enumerate(encoded.word_ids) if value == word]
        if not positions:
            return []
        offsets.append([positions[0], positions[-1]])
    width = settings["max_span_width"]
    spans = [(start, end) for start in range(len(words)) for end in range(start, min(len(words), start + width))]
    capacity = settings["max_spans"]
    # Never drop the final question's spans to make a history window fit.
    if len(spans) > capacity:
        return []
    spans.extend([(-1, -1)] * (capacity - len(spans)))
    inputs = {"token_ids": np.array([encoded.ids], dtype=np.int64),
              "offsets": np.array([offsets], dtype=np.int64),
              "mask": np.ones((1, len(words)), dtype=bool),
              "segment_concat_mask": np.ones((1, len(encoded.ids)), dtype=bool),
              "spans": np.array([spans], dtype=np.int64)}
    top, candidates, selected = session.run(None, inputs)
    links = []
    for index, choice in enumerate(selected[0]):
        if choice < 0:
            continue
        antecedent = int(candidates[0, index, int(choice)])
        if 0 <= antecedent < index:
            links.append((tuple(map(int, top[0, index])), tuple(map(int, top[0, antecedent]))))
    return links


def _replace_mentions(text, question_start, tokens, links):
  
    ancestors = dict(links)
    replacements = []
    for mention, antecedent in links:
        if not (0 <= mention[0] <= mention[1] < len(tokens)):
            continue
        start, end = tokens[mention[0]].start(), tokens[mention[1]].end()
        if start < question_start:
            continue
        visited = {mention}
        while antecedent in ancestors and antecedent not in visited:
            visited.add(antecedent)
            antecedent = ancestors[antecedent]
        if not (0 <= antecedent[0] <= antecedent[1] < len(tokens)):
            continue
        left, right = tokens[antecedent[0]].start(), tokens[antecedent[1]].end()
        if right > question_start or antecedent in visited:
            continue
        replacement = text[left:right]
        if replacement.casefold() != text[start:end].casefold():
            replacements.append((start - question_start, end - question_start, replacement))
    replacements.sort()
    if any(a[1] > b[0] for a, b in zip(replacements, replacements[1:])):
        return text[question_start:]
    question = text[question_start:]
    for start, end, replacement in reversed(replacements):
        question = question[:start] + replacement + question[end:]
    return question


def resolve(question, history, config):
    global _retry_after
    if not history or not config.get("enabled", False):
        return question
    with _lock:
        if time.monotonic() < _retry_after:
            return question
        try:
            session, tokenizer, settings = _load(config["model"], config["revision"], config.get("threads", 2))
            width = settings["max_span_width"]
            budget = settings["max_spans"] // width
            question_tokens = list(re.finditer(r"\w+|[^\w\s]", question))
            remaining = budget - len(question_tokens)
            pieces = []
            for turn in reversed(history[-6:]):
                if remaining <= 0:
                    break
                content = turn["content"][:2000]
                spans = list(re.finditer(r"\w+|[^\w\s]", content))
                keep = min(len(spans), remaining, 24)
                if keep:
                    pieces.append(content[:spans[keep - 1].end()])
                    remaining -= keep
            if not pieces or not question_tokens:
                return question
            prefix = "\n".join(reversed(pieces)) + "\n"
            text = prefix + question
            tokens = list(re.finditer(r"\w+|[^\w\s]", text))
            links = _links([token.group() for token in tokens], session, tokenizer, settings)
            return _replace_mentions(text, len(prefix), tokens, links)
        except Exception:
            _retry_after = time.monotonic() + 30
            logger.warning("Coreference unavailable; keeping the original question. Run python -m scripts.prepare_coreference.", exc_info=True)
            return question
