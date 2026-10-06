import uvicorn
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from uuid import UUID, uuid4
import threading
import ollama
import logging
from threadleaf.chat_workflow import ChatWorkflow

from threadleaf import rag, document_titles, document_management, reranker

@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(reranker.warmup, rag.CFG.get("reranker", {}))
    app.state.document_titles, app.state.failed_titles = await asyncio.to_thread(document_titles.prepare_titles)
    get_workflow()
    try:
        yield
    finally:
        await asyncio.to_thread(app.state.document_jobs.wait)
        app.state.chat_workflow.close()
        app.state.chat_workflow = None


app = FastAPI(title="RAG Chat API", lifespan=lifespan)
app.state.document_titles = {}
app.state.failed_titles = set()
app.state.document_jobs = document_management.DocumentJobs()
app.state.chat_workflow = None
workflow_lock = threading.Lock()


def get_workflow():
    with workflow_lock:
        if app.state.chat_workflow is None:
            app.state.chat_workflow = ChatWorkflow(rag.ROOT / "state" / "conversations.sqlite3")
        return app.state.chat_workflow
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class ChatRequest(BaseModel):
    model_config = {"extra": "forbid"}
    message: str = Field(min_length=1, max_length=4000)
    lang: str | None = None
    sources: list[str] | None = None
    thread_id: UUID | None = None
    model: str | None = Field(default=None, min_length=1, max_length=200)


@app.get("/models")
def models():
    try:
        # Ollama reports capabilities, so embedding-only models are excluded.
        names = []
        for item in ollama.list().models:
            if not item.model:
                continue
            try:
                capabilities = ollama.show(item.model).capabilities or []
            except Exception:
                logging.getLogger(__name__).warning("Could not inspect installed model %s", item.model)
                continue
            if "completion" in capabilities:
                names.append(item.model)
        return {"models": sorted(names), "default": rag.CFG["models"]["llm"]}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Model list unavailable") from exc


@app.get("/documents")
def documents():
    documents = rag.list_documents()
    for doc in documents:
        if title := app.state.document_titles.get(doc["source"]):
            doc["title"] = title
        if doc["source"] in app.state.failed_titles:
            doc["title_generation_failed"] = True
    return {"documents": documents}


class DocumentTitleRequest(BaseModel):
    source: str


def start_document_job(source: str, operation: str, data: bytes | None = None):
    try:
        return app.state.document_jobs.start(source, operation, app, data)
    except ValueError as exc:
        code = str(exc)
        raise HTTPException(status_code=409 if code in {"busy", "already_exists"} else 404 if code == "not_found" else 400, detail=code) from exc


@app.get("/documents/operations")
def document_operation():
    return app.state.document_jobs.status()


@app.post("/documents/upload", status_code=202)
async def upload_document(source: str, request: Request):
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > document_management.MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="too_large")
    if not data:
        raise HTTPException(status_code=400, detail="empty_upload")
    return start_document_job(source, "upload", bytes(data))


@app.delete("/documents", status_code=202)
def delete_document(req: DocumentTitleRequest):
    return start_document_job(req.source, "delete")


@app.post("/documents/reindex", status_code=202)
def reindex_document(req: DocumentTitleRequest):
    return start_document_job(req.source, "reindex")


@app.post("/documents/title")
def document_title(req: DocumentTitleRequest):
    try:
        return {"source": req.source, "title": document_titles.document_title(req.source)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Documento non presente nel database.") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Generazione del titolo non disponibile.") from exc


@app.post("/chat")
def chat(req: ChatRequest):
    if app.state.document_jobs.status()["state"] == "running":
        raise HTTPException(status_code=409, detail="busy")
    try:
        return get_workflow().ask(str(req.thread_id or uuid4()), req.message, req.lang, req.sources, req.model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/conversations")
def conversations(q: str = Query(default="", max_length=500)):
    return {"conversations": get_workflow().list_conversations(q)}


@app.get("/conversations/{thread_id}")
def conversation_state(thread_id: UUID):
    return get_workflow().read(str(thread_id))


@app.delete("/conversations/{thread_id}", status_code=204)
def delete_conversation(thread_id: UUID):
    get_workflow().delete(str(thread_id))


app.mount("/", StaticFiles(directory=rag.ROOT / "web" / "public", html=True, check_dir=False), name="web")

if __name__ == "__main__":
    uvicorn.run(app, host=rag.CFG["server"]["host"], port=rag.CFG["server"]["port"])
