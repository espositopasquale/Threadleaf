from collections import Counter, OrderedDict
import math
import re
import threading
import unicodedata
from . import reranker

_cache = OrderedDict()
_lock = threading.RLock()


def tokens(text: str) -> list[str]:
    normalized = "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))
    return re.findall(r"[^\W_]+", normalized)


def invalidate():
    with _lock:
        _cache.clear()


def _index(col):
    key = (str(col.id), col.count())
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
        records = {}
        frequencies = {}
        offset = 0
        while True:
            batch = col.get(limit=1000, offset=offset, include=["documents", "metadatas"])
            for id_, text, metadata in zip(batch["ids"], batch["documents"], batch["metadatas"]):
                terms = Counter(tokens(text or ""))
                headings = re.findall(r"(?m)^[ \t]*(?:\(+([^\n)]{2,100})\)+[. \t]*|\#{1,6}[ \t]+([^\n]{2,100}))[ \t]*$", text or "")
                records[id_] = {"text": text or "", "source": (metadata or {}).get("source", ""), "metadata": metadata or {}, "terms": terms, "length": sum(terms.values()),
                                "headings": [set(tokens(a or b)) for a, b in headings]}
                for term, frequency in terms.items():
                    frequencies.setdefault(term, {})[id_] = frequency
            fetched = len(batch["ids"])
            if fetched < 1000:
                break
            offset += fetched
        _cache[key] = (records, frequencies)
        while len(_cache) > 4:
            _cache.popitem(last=False)
        return records, frequencies


def retrieve(col, question: str, embedding: list[float], k: int, count: int,
             where: dict | None = None, candidates: int = 24, lexical_weight: float = 0.6,
             rerank_config: dict | None = None) -> list[dict]:
    pool_size = max(k, (rerank_config or {}).get("top_n", 24)) if (rerank_config or {}).get("enabled") else k
    limit = min(max(k, candidates), count)
    result = col.query(query_embeddings=[embedding], n_results=limit, **({"where": where} if where else {}))
    semantic = result["ids"][0]
    distances = dict(zip(semantic, result["distances"][0]))
    records, frequencies = _index(col)
    allowed = None
    if where:
        value = where["source"]
        allowed = set(value["$in"]) if isinstance(value, dict) else {value}
    eligible = {id_ for id_, record in records.items() if allowed is None or record["source"] in allowed}
    average_length = sum(records[id_]["length"] for id_ in eligible) / max(len(eligible), 1) or 1
    lexical_scores = Counter()
    for term in set(tokens(question)):
        matches = {id_: frequency for id_, frequency in frequencies.get(term, {}).items() if id_ in eligible}
        if not matches:
            continue
        inverse_frequency = math.log(1 + (len(eligible) - len(matches) + 0.5) / (len(matches) + 0.5))
        for id_, frequency in matches.items():
            denominator = frequency + 1.2 * (0.25 + 0.75 * records[id_]["length"] / average_length)
            lexical_scores[id_] += inverse_frequency * frequency * 2.2 / denominator
    lexical = [id_ for id_, _ in lexical_scores.most_common(limit)]
    query_terms = set(tokens(question))
    heading_scores = {
        id_: max((len(query_terms & heading) / max(len(query_terms), len(heading), 1)
                  for heading in records[id_]["headings"]), default=0)
        for id_ in eligible
    }
    # Generic section headings help locate definitions rather than incidental mentions.
    heading_candidates = sorted((id_ for id_ in eligible if heading_scores[id_] > 0),
                                key=lambda id_: (-heading_scores[id_], id_))[:limit]
    # Rank fusion combines heterogeneous scores without treating them as probabilities.
    fused = Counter()
    for ranking, weight in ((semantic, 1 - lexical_weight if lexical else 1), (lexical, lexical_weight)):
        for rank, id_ in enumerate(ranking, 1):
            fused[id_] += weight / (60 + rank)
    for id_ in heading_candidates:
        fused[id_] += 0.025 * heading_scores[id_]
    chunks = []
    seen = set()
    for id_, score in fused.most_common():
        if id_ not in eligible:
            continue
        record = records[id_]
        normalized = " ".join(record["text"].split())
        if normalized in seen:
            continue
        seen.add(normalized)
        chunks.append({**record["metadata"], "id": id_, "source": record["source"], "text": record["text"],
                       "distance": distances.get(id_), "retrieval_score": score})
        if len(chunks) == pool_size:
            break
    return reranker.rerank(question, chunks, k, rerank_config or {})
