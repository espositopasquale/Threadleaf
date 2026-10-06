from functools import lru_cache
import hashlib
import json
import logging
from pathlib import Path
import threading

from pypdf import PdfReader

from .paths import ROOT

logger = logging.getLogger(__name__)
_lock = threading.RLock()
ARCHIVE = ROOT / "state" / "document_layout"


def archive_path(source: str) -> Path:
    return ARCHIVE / (hashlib.sha256(source.replace("\\", "/").encode()).hexdigest() + ".json")


def remove_archive(source: str) -> None:
    archive_path(source).unlink(missing_ok=True)


def model_directory(config: dict) -> Path:
    return ROOT / "models" / "layout" / config.get("model", "PP-DocLayout-M")


@lru_cache(maxsize=2)
def _detector(folder: str, model: str, threads: int):
    # Imports stay optional. Normal ingestion never downloads model weights.
    from paddleocr import LayoutDetection
    return LayoutDetection(
                            model_name=model,
                            model_dir=folder,
                            device="cpu",
                            cpu_threads=threads,
                            enable_mkldnn=False,
                        )

def _regions(pdf, number: int, config: dict) -> list[dict]:
    import numpy as np

    folder = model_directory(config)
    if not (folder / "inference.pdiparams").is_file():
        raise FileNotFoundError("Run python -m scripts.prepare_layout to download the layout model")
    detector = _detector(str(folder), config.get("model", "PP-DocLayout-M"), config.get("threads", 2))
    page = pdf[number]
    try:
        width, height = page.get_size()
        bitmap = page.render(scale=config.get("render_scale", 1.5))
        try:
            image = bitmap.to_pil().convert("RGB")
            try:
                with _lock:
                    results = list(detector.predict(input=np.asarray(image), batch_size=1))
                # JSON is PaddleOCR's public result representation.
                data = results[0].json if results else {}
                if isinstance(data, str):
                    data = json.loads(data)
                boxes = data.get("res", data).get("boxes", [])
                image_width, image_height = image.size
            finally:
                image.close()
        finally:
            bitmap.close()
        textpage = page.get_textpage()
        try:
            blocks = []
            for index, box in enumerate(boxes):
                x0, y0, x1, y1 = map(float, box["coordinate"])
                # Store top-left normalized coordinates; PDFium uses bottom-left units.
                bounds = [max(0, min(1, x0 / image_width)), max(0, min(1, y0 / image_height)),
                          max(0, min(1, x1 / image_width)), max(0, min(1, y1 / image_height))]
                left, top, right, bottom = bounds
                text = textpage.get_text_bounded(left=left * width, bottom=(1 - bottom) * height,
                                                right=right * width, top=(1 - top) * height,
                                                errors="replace").replace("\r\n", "\n").strip()
                blocks.append({"id": f"p{number + 1}-b{index + 1}", "type": box["label"],
                               "bbox": bounds, "score": float(box["score"]), "text": text,
                               "method": "pdfium-native", "needs_ocr": not bool(text)})
            # This is a basic geometric order, not a learned reading-order model.
            return sorted(blocks, key=lambda b: (round(b["bbox"][0] / 0.2), b["bbox"][1]))
        finally:
            textpage.close()
    finally:
        page.close()


def extract(path: Path, source: str, config: dict, progress=None) -> dict:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    settings = json.dumps(config, sort_keys=True)
    key = hashlib.sha256((digest + settings + "layout-v1").encode()).hexdigest()
    destination = archive_path(source)
    if destination.is_file():
        try:
            saved = json.loads(destination.read_text(encoding="utf-8"))
            if saved.get("cache_key") == key:
                return saved
        except (ValueError, OSError):
            pass
    result = {"source": source, "sha256": digest, "cache_key": key,
              "coordinate_system": "normalized top-left", "pages": [], "warnings": []}
    pdf = None
    try:
        if path.suffix.lower() != ".pdf":
            text = path.read_text(encoding="utf-8", errors="replace")
            result["pages"].append({"page": 1, "raw_text": text, "layout_text": text, "blocks": []})
        else:
            reader = PdfReader(path)
            detect = config.get("enabled", False)
            if detect:
                try:
                    import pypdfium2
                    pdf = pypdfium2.PdfDocument(str(path))
                except Exception as exc:
                    detect = False
                    result["warnings"].append(f"Layout unavailable: {exc}")
            for number, page in enumerate(reader.pages):
                raw = page.extract_text() or ""
                try:
                    layout = page.extract_text(extraction_mode="layout") or raw
                except Exception:
                    layout = raw
                entry = {"page": number + 1, "raw_text": raw, "layout_text": layout, "blocks": [],
                         "needs_ocr": not bool(raw.strip())}
                if detect:
                    try:
                        entry["blocks"] = _regions(pdf, number, config)
                    except Exception as exc:
                        detect = False
                        result["warnings"].append(f"Layout unavailable on page {number + 1}: {exc}")
                if entry["needs_ocr"]:
                    result["warnings"].append(f"Page {number + 1} has no native text; OCR is needed")
                result["pages"].append(entry)
                if progress:
                    progress("reading", number + 1, len(reader.pages))
    finally:
        if pdf is not None:
            pdf.close()
    for warning in result["warnings"]:
        logger.warning("%s: %s", source, warning)
    # Do not cache unavailable detection, allowing installation/recovery on the next ingestion.
    result["cache_key"] = key if not any(w.startswith("Layout unavailable") for w in result["warnings"]) else ""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(destination)
    return result


def _split(text: str, size: int, overlap: int):
   
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = text.rfind("\n\n", start + size // 2, end)
            if boundary < 0:
                boundary = text.rfind("\n", start + size // 2, end)
            if boundary >= 0:
                end = boundary + 1
        if text[start:end].strip():
            yield text[start:end].strip()
        if end == len(text):
            break
        start = max(start + 1, end - overlap)


def chunks(document: dict, size: int, overlap: int) -> list[dict]:
    result = []
    for page in document["pages"]:
        for block in page["blocks"]:
            for text in _split(block["text"], size, overlap):
                result.append({"text": text, "metadata": {"page": page["page"], "block_id": block["id"],
                    "block_type": block["type"], "bbox": json.dumps(block["bbox"]), "layout_score": block["score"]}})
        # Keep complete native text searchable even when the detector misses a region.
        seen = set()
        for method, text in (("layout", page["layout_text"]), ("raw", page["raw_text"])):
            for index, part in enumerate(_split(text, size, overlap)):
                if part in seen:
                    continue
                seen.add(part)
                result.append({"text": part, "metadata": {"page": page["page"],
                    "block_id": f"p{page['page']}-{method}-{index}", "block_type": "page_text"}})
    return result
