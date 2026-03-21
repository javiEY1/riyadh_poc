from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.models import ExtractionResult


ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "data" / "contracts.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

ASYNC_DB_URL = f"sqlite+aiosqlite:///{DB_PATH}"
SYNC_DB_URL = f"sqlite:///{DB_PATH}"

async_engine = create_async_engine(ASYNC_DB_URL, echo=False)
sync_engine = create_engine(SYNC_DB_URL, echo=False)
AsyncSessionLocal = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(512), nullable=False)
    uploaded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    ocr_used = Column(Integer, default=0)
    overall_confidence = Column(Float, default=0.0)
    extraction_method = Column(String(32), default="regex")
    result_json = Column(Text, nullable=False)

    def to_summary(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "uploaded_at": self.uploaded_at.isoformat() if self.uploaded_at else None,
            "ocr_used": bool(self.ocr_used),
            "overall_confidence": self.overall_confidence,
            "extraction_method": self.extraction_method,
        }

    def to_full(self) -> dict:
        summary = self.to_summary()
        summary["result"] = json.loads(self.result_json)
        return summary


async def init_db() -> None:
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def init_db_sync() -> None:
    Base.metadata.create_all(sync_engine)


class Template(Base):
    __tablename__ = "templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(512), nullable=False)
    filename = Column(String(512), nullable=False)
    uploaded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    ocr_used = Column(Integer, default=0)
    overall_confidence = Column(Float, default=0.0)
    extraction_method = Column(String(32), default="regex")
    result_json = Column(Text, nullable=False)

    def to_summary(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "filename": self.filename,
            "uploaded_at": self.uploaded_at.isoformat() if self.uploaded_at else None,
            "ocr_used": bool(self.ocr_used),
            "overall_confidence": self.overall_confidence,
            "extraction_method": self.extraction_method,
        }

    def to_full(self) -> dict:
        summary = self.to_summary()
        summary["result"] = json.loads(self.result_json)
        return summary


async def save_document(
    filename: str,
    result: ExtractionResult,
    extraction_method: str = "regex",
) -> Document:
    doc = Document(
        filename=filename,
        ocr_used=int(result.ocr_used),
        overall_confidence=result.overall_confidence,
        extraction_method=extraction_method,
        result_json=json.dumps(result.model_dump(), ensure_ascii=False),
    )
    async with AsyncSessionLocal() as session:
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
    return doc


async def save_template(
    name: str,
    filename: str,
    result: ExtractionResult,
    extraction_method: str = "regex",
) -> Template:
    tpl = Template(
        name=name,
        filename=filename,
        ocr_used=int(result.ocr_used),
        overall_confidence=result.overall_confidence,
        extraction_method=extraction_method,
        result_json=json.dumps(result.model_dump(), ensure_ascii=False),
    )
    async with AsyncSessionLocal() as session:
        session.add(tpl)
        await session.commit()
        await session.refresh(tpl)
    return tpl
