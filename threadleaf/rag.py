import tomllib
import json
from pathlib import Path

import chromadb
import ollama
from . import retrieval, grounded_answers, conversation, document_layout
from .paths import ROOT
from pypdf import PdfReader

CFG = tomllib.loads((ROOT / "config.toml").read_text(encoding="utf-8"))
SYSTEM_PROMPT = (ROOT / "system_prompt.txt").read_text(encoding="utf-8").strip()

_client = chromadb.PersistentClient(path=str(ROOT / CFG["rag"]["db_dir"]))


def _collection():
    return _client.get_or_create_collection(CFG["rag"]["collection"])


def _clean_text(text: str) -> str:
    return text.encode("utf-8", errors="replace").decode("utf-8")


def _embed(texts: list[str]) -> list[list[float]]:
    safe_texts = [_clean_text(text) for text in texts]
    return ollama.embed(model=CFG["models"]["embedding"], input=safe_texts)["embeddings"]


def _read(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        text = "\n".join(p.extract_text() or "" for p in PdfReader(path).pages)
    else:
        text = path.read_text(encoding="utf-8", errors="replace")
    return _clean_text(text)


def _chunks(text: str) -> list[str]:
    size, overlap = CFG["rag"]["chunk_size"], CFG["rag"]["chunk_overlap"]
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError("chunk_size must be positive and chunk_overlap must be between 0 and chunk_size - 1")
    step = size - overlap
    return [c for i in range(0, len(text), step) if (c := text[i:i + size].strip())]


def _document_chunks(path: Path, source: str, progress=None) -> list[dict]:
    document = document_layout.extract(path, source, CFG.get("layout", {}), progress)
    return document_layout.chunks(document, CFG["rag"]["chunk_size"], CFG["rag"]["chunk_overlap"])


def ingest(progress=None, sources: list[str] | None = None) -> int:
    
    batch_size = CFG["rag"].get("batch_size", 32)
    if not isinstance(batch_size, int) or isinstance(batch_size, bool) or batch_size <= 0:
        raise ValueError("rag.batch_size must be a positive integer")
    # Validate chunk settings before deleting the existing collection.
    _chunks("")
    if sources is not None:
        # Prepare embeddings before changing the index, preserving existing data on failure.
        col = _collection()
        docs_dir = (ROOT / CFG["rag"]["docs_dir"]).resolve()
        total = 0
        for source in sources:
            path = (docs_dir / source).resolve()
            if not path.is_relative_to(docs_dir) or not path.is_file():
                raise ValueError("Invalid document path")
            if progress:
                progress("reading", 0, 0)
            name = str(path.relative_to(docs_dir))
            records = _document_chunks(path, name, progress)
            chunks = [_clean_text(record["text"]) for record in records]
            if not chunks:
                raise ValueError("Document contains no extractable text")
            embeddings = []
            for start in range(0, len(chunks), batch_size):
                batch = chunks[start:start + batch_size]
                vectors = _embed(batch)
                if len(vectors) != len(batch):
                    raise ValueError("Unexpected embedding count")
                embeddings.extend(vectors)
                if progress:
                    progress("indexing", len(embeddings), len(chunks))
            previous = col.get(where={"source": name}, include=[])["ids"]
            retrieval.invalidate()
            for start in range(0, len(chunks), batch_size):
                batch = chunks[start:start + batch_size]
                col.upsert(ids=[f"{name}:{i}" for i in range(start, start + len(batch))],
                           documents=batch, embeddings=embeddings[start:start + len(batch)],
                           metadatas=[{"source": name, **record["metadata"]} for record in records[start:start + len(batch)]])
            obsolete = set(previous) - {f"{name}:{i}" for i in range(len(chunks))}
            if obsolete:
                col.delete(ids=sorted(obsolete))
            total += len(chunks)
        return total
    try:
        _client.delete_collection(CFG["rag"]["collection"])
    except chromadb.errors.NotFoundError:
        pass
    col = _collection()
    docs_dir = ROOT / CFG["rag"]["docs_dir"]
    total = 0
    for path in sorted(docs_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".pdf", ".txt", ".md"}:
            continue
        name = str(path.relative_to(docs_dir))
        records = _document_chunks(path, name, progress)
        chunks = [_clean_text(record["text"]) for record in records]
        if not chunks:
            continue
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start:start + batch_size]
            embeddings = _embed(batch)
            if len(embeddings) != len(batch):
                raise ValueError(f"{name}: expected {len(batch)} embeddings, got {len(embeddings)}")
            col.add(
                ids=[f"{name}:{i}" for i in range(start, start + len(batch))],
                documents=batch,
                embeddings=embeddings,
                metadatas=[{"source": name, **record["metadata"]} for record in records[start:start + len(batch)]],
            )
            print(f"{name}: indexed {start + len(batch)}/{len(chunks)} chunks")
        total += len(chunks)
        print(f"{name}: {len(chunks)} chunks")
    return total


def list_documents() -> list[dict]:
    
    col = _collection()
    counts: dict[str, int] = {}
    offset = 0
    while True:
        batch = col.get(limit=1000, offset=offset, include=["metadatas"])
        for metadata in batch["metadatas"] or []:
            if metadata and (source := metadata.get("source")):
                counts[source] = counts.get(source, 0) + 1
        fetched = len(batch["ids"])
        if fetched < 1000:
            break
        offset += fetched
    return [{"source": source, "chunks": counts[source]} for source in sorted(counts)]


def ask(question: str, lang: str | None = None, k: int | None = None, model: str | None = None,
        sources: list[str] | None = None, history: list[dict] | None = None) -> dict:
    question = _clean_text(question)
    col = _collection()
    k = k or CFG["rag"]["top_k"]
    chunks: list[dict] = []
    context = "NO_CONTEXT_FOUND"
    query_options = {}
    count = col.count()
    history = (history or [])[-6:]
    if sources is not None:
        selected = set(sources)
        if not selected:
            raise ValueError("Seleziona almeno un documento prima di inviare una domanda.")
        documents = list_documents()
        available = {doc["source"] for doc in documents}
        if selected - available:
            raise ValueError("Alcuni documenti selezionati non sono più nel database. Aggiorna l'elenco.")
        count = sum(doc["chunks"] for doc in documents if doc["source"] in selected)
        query_options["where"] = {"source": {"$in": sorted(selected)}}
    casual = grounded_answers.is_casual(question, CFG["models"]["embedding"], history)
    retrieval_question = question if casual else conversation.standalone_question(question, history, CFG.get("coreference", {}))
    if count and not casual:
        chunks = retrieval.retrieve(
            col, retrieval_question, _embed([retrieval_question])[0], k, count,
            where=query_options.get("where"),
            candidates=CFG["rag"].get("candidate_k", 24),
            lexical_weight=CFG["rag"].get("lexical_weight", 0.6),
            rerank_config=CFG.get("reranker"),
        )
        context = "\n---\n".join(
            f"PASSAGE {i} | {c['source']}" + (f" | page {c['page']}" if c.get("page") else "")
            + (f" | {c['block_type']}" if c.get("block_type") else "") + f"\n{c['text']}"
            for i, c in enumerate(chunks, 1))
    sources = sorted({c["source"] for c in chunks})

    answer_lang = lang or CFG["language"]["answer"]
    system = (
        "You are ThreadLeaf, a friendly assistant. Reply naturally and briefly to the user's message. "
        "Speak to the user directly: do not quote, restate or label their message. "
        "This is social conversation; do not discuss documents or cite sources. "
        "When matching the user's language, follow their latest message even if earlier messages use another language."
        if casual else SYSTEM_PROMPT
    )
    system += "\nThe interface displays source metadata separately. Do not append a source list or citation footer to your answer."
    system += (
        "\nAnswer in the same language as the question. The latest user question determines the answer language, regardless of the language of documents or earlier turns."
        if answer_lang == "auto"
        else f"\nAnswer in this language: {answer_lang}."
    )
    user_msg = question if casual else f"QUESTION: {question}\n\nCONTEXT:\n{context}\n\nQUESTION: {question}\nAnswer only with facts explicitly supported by these passages. Omit unsupported descriptions, qualifications and accomplishments."
    if history and not casual:
        user_msg += f"\nRESOLVED QUESTION: {retrieval_question}"
        system += "\nUse earlier turns only to understand references. Earlier assistant answers are not document evidence."
    extractive = not casual and CFG["llm"].get("answer_mode", "extractive") == "extractive"
    if extractive:
        system += grounded_answers.INSTRUCTIONS
    reply = ollama.chat(
        model=model or CFG["models"]["llm"],
        messages=[
            {"role": "system", "content": system},
            *history,
            {"role": "user", "content": user_msg},
        ],
        options={
            "temperature": CFG["llm"]["temperature"],
            "num_predict": CFG["llm"]["max_tokens"],
            "num_ctx": CFG["llm"].get("context_window", 4096),
        },
        **({"format": grounded_answers.SCHEMA} if extractive else {}),
    )
    content = reply["message"]["content"].strip()
    answer_kind = "casual" if casual else "generated"
    if extractive:
        content, answer_kind = grounded_answers.render(content, chunks, answer_lang, retrieval_question,
                                                       CFG["rag"].get("max_semantic_distance", 0.65))
    if answer_kind in {"casual", "insufficient"}:
        sources = []
    elif answer_kind == "document":
        sources = [chunks[json.loads(reply["message"]["content"])["passage"] - 1]["source"]]
    return {
        "reply": content,
        "answer_kind": answer_kind,
        "reranker_applied": any("rerank_score" in chunk for chunk in chunks),
        "retrieval_question": retrieval_question,
        "sources": sources,
        "chunks": chunks,
        "prompt": f"[system]\n{system}\n\n[user]\n{user_msg}",
    }
