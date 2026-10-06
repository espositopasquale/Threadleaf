from functools import lru_cache
import logging
from pathlib import Path
from .paths import ROOT
import threading
import time

logger = logging.getLogger("uvicorn.error")
_lock = threading.RLock()
_retry_after = {}


def model_directory(config: dict) -> Path:
    return ROOT / "models" / "reranker" / config["model"].replace("/", "--") / config.get("revision", "main")


@lru_cache(maxsize=2)
def _load(model: str, revision: str, model_file: str, max_length: int, threads: int):
    import onnxruntime as ort
    from tokenizers import Tokenizer

    folder = model_directory({"model": model, "revision": revision})
    weights, tokenizer_path = folder / model_file, folder / "tokenizer.json"
    if not weights.is_file() or not tokenizer_path.is_file():
        raise RuntimeError("Reranker weights are missing. Run: python -m scripts.prepare_reranker")
    tokenizer = Tokenizer.from_file(str(tokenizer_path))
    tokenizer.enable_truncation(max_length=max_length, strategy="only_second")
    tokenizer.enable_padding(pad_id=tokenizer.token_to_id("<pad>"), pad_token="<pad>")
    options = ort.SessionOptions()
    options.intra_op_num_threads = threads
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(weights), sess_options=options, providers=["CPUExecutionProvider"])
    logger.info("Multilingual reranker loaded: %s (%s)", model, model_file)
    return tokenizer, session


@lru_cache(maxsize=128)
def _scores(model: str, revision: str, model_file: str, max_length: int, threads: int,
            batch_size: int, question: str, texts: tuple[str, ...]) -> tuple[float, ...]:
    import numpy as np

    tokenizer, session = _load(model, revision, model_file, max_length, threads)
    # Keep the question intact for typical requests, and leave room for the passage.
    tokenizer.no_truncation()
    question_ids = tokenizer.encode(question, add_special_tokens=False).ids[:min(128, max_length // 2)]
    query = tokenizer.decode(question_ids)
    tokenizer.enable_truncation(max_length=max_length, strategy="only_second")
    scores = []
    for start in range(0, len(texts), batch_size):
        encodings = tokenizer.encode_batch([(query, text) for text in texts[start:start + batch_size]])
        fields = {"input_ids": [item.ids for item in encodings],
                  "attention_mask": [item.attention_mask for item in encodings],
                  "token_type_ids": [item.type_ids for item in encodings]}
        inputs = {item.name: np.asarray(fields[item.name], dtype=np.int32 if item.type == "tensor(int32)" else np.int64)
                  for item in session.get_inputs()}
        logits = np.asarray(session.run(None, inputs)[0]).reshape(-1)
        if len(logits) != len(encodings) or not np.isfinite(logits).all():
            raise ValueError("Reranker returned invalid scores")
        scores.extend(float(score) for score in logits)
    return tuple(scores)


def rerank(question: str, chunks: list[dict], k: int, config: dict) -> list[dict]:
    if not config.get("enabled", False) or not chunks:
        return chunks[:k]
    key = (config["model"], config.get("revision", "main"), config.get("file", "onnx/model_quint8_avx2.onnx"))
    with _lock:
        if time.monotonic() < _retry_after.get(key, 0):
            return chunks[:k]
        try:
            scores = _scores(*key, config.get("max_length", 384), config.get("threads", 2),
                             config.get("batch_size", 4), question, tuple(chunk["text"] for chunk in chunks))
            if len(scores) != len(chunks):
                raise ValueError("Reranker score count does not match candidates")
            ranked = sorted(zip(chunks, scores), key=lambda item: item[1], reverse=True)
            return [{**chunk, "rerank_score": score} for chunk, score in ranked[:k]]
        except Exception:
            _retry_after[key] = time.monotonic() + 30
            logger.warning("Reranker unavailable; using hybrid ranking for now. Run python -m scripts.prepare_reranker if weights are missing.", exc_info=True)
            return chunks[:k]


def warmup(config: dict) -> bool:
    if not config.get("enabled", False):
        return False
    key = (config["model"], config.get("revision", "main"), config.get("file", "onnx/model_quint8_avx2.onnx"))
    with _lock:
        try:
            _load(*key, config.get("max_length", 384), config.get("threads", 2))
            _retry_after.pop(key, None)
            return True
        except Exception as exc:
            _retry_after[key] = time.monotonic() + 30
            logger.warning("Reranker unavailable: %s. Hybrid retrieval remains active.", exc)
            return False
