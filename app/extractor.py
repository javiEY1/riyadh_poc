from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

import fitz
import pytesseract
from docx import Document
from PIL import Image
from pypdf import PdfReader

logger = logging.getLogger(__name__)


def _ocr_available() -> bool:
    try:
        _ = pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _text_quality(text: str) -> float:
    """Return a quality score 0.0-1.0 for extracted text."""
    stripped = text.strip()
    if not stripped:
        return 0.0
    length = len(stripped)
    alpha = sum(1 for c in stripped if c.isalpha())
    ratio = alpha / length
    words = stripped.split()
    avg_word_len = sum(len(w) for w in words) / len(words) if words else 0
    length_score = min(length / 500, 0.4)
    alpha_score = 0.3 if ratio > 0.5 else 0.15 if ratio > 0.3 else 0.0
    word_score = 0.3 if 3 < avg_word_len < 12 else 0.0
    return min(length_score + alpha_score + word_score, 1.0)


def _extract_pdf_text(content: bytes) -> str:
    reader = PdfReader(BytesIO(content))
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts).strip()


def _extract_pdf_text_with_ocr(content: bytes) -> str:
    doc = fitz.open(stream=content, filetype="pdf")
    parts: list[str] = []
    for page in doc:
        pix = page.get_pixmap(dpi=220)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        parts.append(pytesseract.image_to_string(img))
    return "\n".join(parts).strip()


def _extract_docx_text(content: bytes) -> str:
    document = Document(BytesIO(content))
    return "\n".join(p.text for p in document.paragraphs).strip()


def _extract_image_text(content: bytes) -> str:
    image = Image.open(BytesIO(content))
    return pytesseract.image_to_string(image).strip()


def extract_text(filename: str, content: bytes) -> tuple[str, bool]:
    suffix = Path(filename).suffix.lower()

    if suffix in {".txt", ".md"}:
        return content.decode("utf-8", errors="ignore"), False

    if suffix == ".docx":
        return _extract_docx_text(content), False

    if suffix == ".pdf":
        text = ""
        try:
            text = _extract_pdf_text(content)
        except Exception:
            pass
        quality = _text_quality(text)
        logger.info("PDF text extraction: %d chars, quality=%.2f", len(text), quality)
        if _ocr_available() and quality < 0.9:
            try:
                ocr_text = _extract_pdf_text_with_ocr(content)
                ocr_quality = _text_quality(ocr_text)
                logger.info("OCR extraction: %d chars, quality=%.2f", len(ocr_text), ocr_quality)
                if ocr_quality > quality or (quality < 0.7 and len(ocr_text) > len(text)):
                    return ocr_text, True
            except Exception:
                logger.exception("OCR extraction failed")
        elif not _ocr_available() and quality < 0.5:
            logger.warning("Tesseract OCR not available, skipping OCR")
        return text, False

    if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}:
        if _ocr_available():
            try:
                return _extract_image_text(content), True
            except Exception:
                pass
        return "", False

    return content.decode("utf-8", errors="ignore"), False
