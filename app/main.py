from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select

from app.database import AsyncSessionLocal, Document, Template, init_db, save_document, save_template
from app.extractor import extract_text
from app.exporter import build_excel_bytes, build_json_bytes
from app.llm_parser import parse_contract_with_llm
from app.metadata_prompt import load_metadata_prompt
from app.models import ExtractionResult
from app.parser import backfill_clauses_with_regex, parse_contract
from app.template_matcher import compare_detailed, rank_templates

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
PROJECT_ROOT = BASE_DIR.parent


def _load_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_env()

_openai_api_key: str | None = os.environ.get("AZURE_OPENAI_KEY") or None
_azure_endpoint: str | None = os.environ.get("AZURE_OPENAI_ENDPOINT") or None
_azure_deployment: str | None = os.environ.get("AZURE_OPENAI_DEPLOYMENT") or None


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Contract Analyzer", version="0.2.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class SettingsPayload(BaseModel):
    openai_api_key: str = ""
    azure_endpoint: str = ""
    azure_deployment: str = ""


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/settings")
async def update_settings(payload: SettingsPayload) -> dict:
    global _openai_api_key, _azure_endpoint, _azure_deployment  # noqa: PLW0603
    key = payload.openai_api_key.strip()
    _openai_api_key = key if key else None
    _azure_endpoint = payload.azure_endpoint.strip() or None
    _azure_deployment = payload.azure_deployment.strip() or None
    is_azure = bool(_openai_api_key and _azure_endpoint)
    return {
        "llm_enabled": _openai_api_key is not None,
        "provider": "azure" if is_azure else "openai" if _openai_api_key else "none",
    }


@app.get("/settings")
async def get_settings() -> dict:
    from app.extractor import _ocr_available
    is_azure = bool(_openai_api_key and _azure_endpoint)
    return {
        "llm_enabled": _openai_api_key is not None,
        "provider": "azure" if is_azure else "openai" if _openai_api_key else "none",
        "ocr_available": _ocr_available(),
    }


@app.post("/extract")
async def extract_contract(file: UploadFile = File(...)) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="File name is required")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    text, ocr_used = extract_text(file.filename, content)
    if not text.strip():
        from app.extractor import _ocr_available
        if not _ocr_available():
            raise HTTPException(
                status_code=422,
                detail="Could not extract text. This file appears to be scanned but Tesseract OCR is not installed. "
                "Run: sudo apt install tesseract-ocr (Linux) or brew install tesseract (macOS). "
                "Or use the provided Dockerfile.",
            )
        raise HTTPException(
            status_code=422,
            detail="Could not extract text from this file.",
        )

    extraction_method = "regex"
    llm_error = ""
    metadata_prompt = load_metadata_prompt()

    if _openai_api_key:
        try:
            result = await parse_contract_with_llm(
                text, api_key=_openai_api_key, ocr_used=ocr_used,
                metadata_prompt=metadata_prompt,
                azure_endpoint=_azure_endpoint,
                azure_deployment=_azure_deployment,
            )
            result = backfill_clauses_with_regex(result, text, metadata_prompt)
            extraction_method = "llm"
        except Exception as exc:
            llm_error = str(exc)
            logger.exception("LLM extraction failed, falling back to regex parser")
            result = parse_contract(text, ocr_used=ocr_used, metadata_prompt=metadata_prompt)
    else:
        result = parse_contract(text, ocr_used=ocr_used, metadata_prompt=metadata_prompt)

    doc = await save_document(file.filename, result, extraction_method=extraction_method)
    response_data = result.model_dump()
    response_data["document_id"] = doc.id
    response_data["extraction_method"] = extraction_method
    if llm_error:
        response_data["llm_error"] = llm_error
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


@app.post("/templates")
async def upload_template(
    file: UploadFile = File(...),
    name: str = Form(""),
) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="File name is required")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    text, ocr_used = extract_text(file.filename, content)
    if not text.strip():
        raise HTTPException(
            status_code=422,
            detail="Could not extract text from template.",
        )

    template_name = name.strip() or file.filename
    extraction_method = "regex"
    llm_error = ""
    metadata_prompt = load_metadata_prompt()

    if _openai_api_key:
        try:
            result = await parse_contract_with_llm(
                text, api_key=_openai_api_key, ocr_used=ocr_used,
                metadata_prompt=metadata_prompt,
                azure_endpoint=_azure_endpoint,
                azure_deployment=_azure_deployment,
            )
            result = backfill_clauses_with_regex(result, text, metadata_prompt)
            extraction_method = "llm"
        except Exception as exc:
            llm_error = str(exc)
            logger.exception("LLM extraction failed for template, falling back to regex")
            result = parse_contract(text, ocr_used=ocr_used, metadata_prompt=metadata_prompt)
    else:
        result = parse_contract(text, ocr_used=ocr_used, metadata_prompt=metadata_prompt)

    tpl = await save_template(template_name, file.filename, result, extraction_method)
    response_data = result.model_dump()
    response_data["template_id"] = tpl.id
    response_data["template_name"] = template_name
    response_data["extraction_method"] = extraction_method
    if llm_error:
        response_data["llm_error"] = llm_error
    return response_data


@app.get("/templates")
async def list_templates() -> list[dict]:
    async with AsyncSessionLocal() as session:
        stmt = select(Template).order_by(Template.uploaded_at.desc()).limit(100)
        rows = await session.execute(stmt)
        return [tpl.to_summary() for tpl in rows.scalars().all()]


@app.get("/templates/{tpl_id}")
async def get_template(tpl_id: int) -> dict:
    async with AsyncSessionLocal() as session:
        tpl = await session.get(Template, tpl_id)
        if not tpl:
            raise HTTPException(status_code=404, detail="Template not found")
        return tpl.to_full()


@app.delete("/templates/{tpl_id}")
async def delete_template(tpl_id: int) -> dict:
    async with AsyncSessionLocal() as session:
        tpl = await session.get(Template, tpl_id)
        if not tpl:
            raise HTTPException(status_code=404, detail="Template not found")
        await session.delete(tpl)
        await session.commit()
    return {"deleted": tpl_id}


@app.post("/templates/match")
async def match_template(contract_result: dict) -> list[dict]:
    async with AsyncSessionLocal() as session:
        stmt = select(Template).order_by(Template.uploaded_at.desc()).limit(100)
        rows = await session.execute(stmt)
        templates = [tpl.to_full() for tpl in rows.scalars().all()]

    if not templates:
        raise HTTPException(status_code=404, detail="No templates available")

    return rank_templates(contract_result, templates)


@app.post("/templates/{tpl_id}/compare")
async def compare_with_template(tpl_id: int, contract_result: dict) -> dict:
    async with AsyncSessionLocal() as session:
        tpl = await session.get(Template, tpl_id)
        if not tpl:
            raise HTTPException(status_code=404, detail="Template not found")

    import json as _json
    tpl_result = _json.loads(tpl.result_json) if isinstance(tpl.result_json, str) else tpl.result_json
    diff = compare_detailed(contract_result, tpl_result)
    diff["template_name"] = tpl.name
    diff["template_id"] = tpl.id
    return diff


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
