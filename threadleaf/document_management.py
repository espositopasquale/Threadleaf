from pathlib import Path, PurePosixPath
import logging
import threading
import uuid

from . import document_titles, rag, document_layout

logger = logging.getLogger("uvicorn.error")
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def document_path(source: str) -> Path:
    normalized = source.replace("\\", "/")
    parts = normalized.split("/")
    if not normalized or PurePosixPath(normalized).is_absolute() or any(
        part in {"", ".", ".."} or any(c in part for c in ':<>"|?*')
        or part.endswith((".", " ")) or any(ord(c) < 32 for c in part)
        or part.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}
        for part in parts
    ):
        raise ValueError("invalid_path")
    root = (rag.ROOT / rag.CFG["rag"]["docs_dir"]).resolve()
    path = root.joinpath(*parts).resolve()
    if not path.is_relative_to(root) or path.suffix.lower() not in {".pdf", ".txt", ".md"}:
        raise ValueError("invalid_path")
    if path.name.lower() in {"readme.txt", "reeadme.txt"}:
        raise ValueError("reserved_document")
    return path


class DocumentJobs:
    def __init__(self):
        self.lock = threading.Lock()
        self.thread = None
        self.job = {"id": None, "state": "idle", "stage": "idle", "done": 0, "total": 0}

    def status(self) -> dict:
        with self.lock:
            return dict(self.job)

    def wait(self):
        if self.thread:
            self.thread.join()

    def start(self, source: str, operation: str, app, data: bytes | None = None) -> dict:
        path = document_path(source)
        root = (rag.ROOT / rag.CFG["rag"]["docs_dir"]).resolve()
        source = str(path.relative_to(root))
        with self.lock:
            if self.job["state"] == "running":
                raise ValueError("busy")
            if operation == "upload" and path.exists():
                raise ValueError("already_exists")
            if operation != "upload" and not path.is_file() and not rag._collection().get(where={"source": source}, limit=1)["ids"]:
                raise ValueError("not_found")
            self.job = {"id": uuid.uuid4().hex, "state": "running", "stage": "saving" if operation == "upload" else "deleting" if operation == "delete" else "reading",
                        "source": source, "operation": operation, "done": 0, "total": 0}
            self.thread = threading.Thread(target=self._run, args=(path, source, operation, app, data), daemon=True)
            self.thread.start()
            return dict(self.job)

    def _progress(self, stage: str, done: int, total: int):
        with self.lock:
            self.job.update(stage=stage, done=done, total=total)

    def _run(self, path: Path, source: str, operation: str, app, data: bytes | None):
        try:
            if operation == "delete":
                if path.is_file():
                    path.unlink()
                col = rag._collection()
                if col.get(where={"source": source}, limit=1)["ids"]:
                    col.delete(where={"source": source})
                rag.retrieval.invalidate()
                document_layout.remove_archive(source)
                app.state.document_titles.pop(source, None)
                app.state.failed_titles.discard(source)
            else:
                if operation == "upload":
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with path.open("xb") as file:
                        file.write(data)
                rag.ingest(progress=self._progress, sources=[source])
                self._progress("titles", self.job["done"], self.job["total"])
                try:
                    app.state.document_titles[source] = document_titles.document_title(source)
                    app.state.failed_titles.discard(source)
                except Exception:
                    app.state.failed_titles.add(source)
                    logger.warning("Title unavailable for %s", source)
            with self.lock:
                self.job.update(state="complete", stage="complete")
        except Exception:
            logger.exception("Document operation failed for %s", source)
            with self.lock:
                self.job.update(state="failed", stage="failed")
