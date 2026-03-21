from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app.extractor import extract_text
from app.exporter import build_excel_bytes, build_json_bytes
from app.metadata_prompt import load_metadata_prompt
from app.models import ExtractionResult
from app.parser import parse_contract


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Contract Analyzer", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/extract")
async def extract_contract(file: UploadFile = File(...)) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="File name is required")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    text, ocr_used = extract_text(file.filename, content)
    if not text.strip():
        raise HTTPException(
            status_code=422,
            detail="Could not extract text. If the file is scanned, install/configure Tesseract OCR.",
        )

    metadata_prompt = load_metadata_prompt()
    result = parse_contract(text, ocr_used=ocr_used, metadata_prompt=metadata_prompt)
    return result.model_dump()


@app.post("/export")
async def export_extraction(payload: ExtractionResult, format: str = "json"):
    fmt = format.strip().lower()

    if fmt == "json":
        content = build_json_bytes(payload)
        headers = {"Content-Disposition": "attachment; filename=contract-analysis.json"}
        return Response(content=content, media_type="application/json", headers=headers)

    if fmt in {"excel", "xlsx"}:
        content = build_excel_bytes(payload)
        headers = {"Content-Disposition": "attachment; filename=contract-analysis.xlsx"}
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=headers,
        )

    raise HTTPException(status_code=400, detail="Unsupported format. Use json or excel.")
