from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select

from app.database import AsyncSessionLocal, Document, init_db, save_document
from app.extractor import extract_text
from app.exporter import build_excel_bytes, build_json_bytes
from app.llm_parser import parse_contract_with_llm
from app.metadata_prompt import load_metadata_prompt
from app.models import ExtractionResult
from app.parser import parse_contract

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

_openai_api_key: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Contract Analyzer", version="0.2.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class SettingsPayload(BaseModel):
    openai_api_key: str = ""


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/settings")
async def update_settings(payload: SettingsPayload) -> dict:
    global _openai_api_key  # noqa: PLW0603
    key = payload.openai_api_key.strip()
    _openai_api_key = key if key else None
    return {"llm_enabled": _openai_api_key is not None}


@app.get("/settings")
async def get_settings() -> dict:
    return {"llm_enabled": _openai_api_key is not None}


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

    extraction_method = "regex"

    if _openai_api_key:
        try:
            result = await parse_contract_with_llm(
                text, api_key=_openai_api_key, ocr_used=ocr_used,
            )
            extraction_method = "llm"
        except Exception:
            logger.exception("LLM extraction failed, falling back to regex parser")
            metadata_prompt = load_metadata_prompt()
            result = parse_contract(text, ocr_used=ocr_used, metadata_prompt=metadata_prompt)
    else:
        metadata_prompt = load_metadata_prompt()
        result = parse_contract(text, ocr_used=ocr_used, metadata_prompt=metadata_prompt)

    doc = await save_document(file.filename, result, extraction_method=extraction_method)
    response_data = result.model_dump()
    response_data["document_id"] = doc.id
    response_data["extraction_method"] = extraction_method
    return response_data


@app.get("/documents")
async def list_documents() -> list[dict]:
    async with AsyncSessionLocal() as session:
        stmt = select(Document).order_by(Document.uploaded_at.desc()).limit(100)
        rows = await session.execute(stmt)
        return [doc.to_summary() for doc in rows.scalars().all()]


@app.get("/documents/{doc_id}")
async def get_document(doc_id: int) -> dict:
    async with AsyncSessionLocal() as session:
        doc = await session.get(Document, doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        return doc.to_full()


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
