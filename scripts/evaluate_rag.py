import argparse
import json
import time
from pathlib import Path

from threadleaf import rag, retrieval
from threadleaf.paths import ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=ROOT / "tests" / "fixtures" / "rag_eval_cases.json")
    parser.add_argument("--generate", action="store_true", help="Also generate answers with the configured chat model")
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    col = rag._collection()
    report = []
    for case in cases:
        where = {"source": {"$in": case["sources"]}}
        count = sum(doc["chunks"] for doc in rag.list_documents() if doc["source"] in case["sources"])
        if not count:
            report.append({"question": case["question"], "error": "No selected documents indexed"})
            continue
        vector = rag._embed([case["question"]])[0]
        start = time.perf_counter()
        baseline = col.query(query_embeddings=[vector], n_results=min(3, count), where=where)
        baseline_time = time.perf_counter() - start
        start = time.perf_counter()
        hybrid = retrieval.retrieve(col, case["question"], vector, rag.CFG["rag"]["top_k"], count, where,
                                    candidates=rag.CFG["rag"].get("candidate_k", 24),
                                    lexical_weight=rag.CFG["rag"].get("lexical_weight", 0.6))
        hybrid_time = time.perf_counter() - start
        start = time.perf_counter()
        reranked = retrieval.retrieve(col, case["question"], vector, rag.CFG["rag"]["top_k"], count, where,
                                      candidates=rag.CFG["rag"].get("candidate_k", 24),
                                      lexical_weight=rag.CFG["rag"].get("lexical_weight", 0.6),
                                      rerank_config=rag.CFG.get("reranker"))
        reranked_time = time.perf_counter() - start
        target = " ".join(retrieval.tokens(case["support_contains"]))
        def rank(texts):
            return next((i for i, text in enumerate(texts, 1) if target in " ".join(retrieval.tokens(text))), None)
        entry = {"question": case["question"], "semantic_support_rank": rank(baseline["documents"][0]),
                 "hybrid_support_rank": rank([chunk["text"] for chunk in hybrid]),
                 "semantic_ms": round(baseline_time * 1000), "hybrid_ms": round(hybrid_time * 1000)}
        entry.update(reranker_applied=any("rerank_score" in chunk for chunk in reranked),
                     reranked_support_rank=rank([chunk["text"] for chunk in reranked]),
                     reranked_ms=round(reranked_time * 1000))
        if args.generate:
            start = time.perf_counter()
            entry["answer"] = rag.ask(case["question"], sources=case["sources"])["reply"]
            entry["answer_seconds"] = round(time.perf_counter() - start, 2)
        report.append(entry)
        print(json.dumps(entry, ensure_ascii=True), flush=True)
    valid = [item for item in report if "error" not in item]
    summary = {"model": rag.CFG["models"]["llm"], "cases": len(valid),
               "semantic_top1": sum(item["semantic_support_rank"] == 1 for item in valid),
               "hybrid_top1": sum(item["hybrid_support_rank"] == 1 for item in valid),
               "semantic_hits": sum(item["semantic_support_rank"] is not None for item in valid),
               "hybrid_hits": sum(item["hybrid_support_rank"] is not None for item in valid),
               "reranker_applied_cases": sum(item["reranker_applied"] for item in valid),
               "reranked_top1": sum(item["reranker_applied"] and item["reranked_support_rank"] == 1 for item in valid)}
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
