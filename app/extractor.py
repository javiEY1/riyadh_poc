from __future__ import annotations

from io import BytesIO
from pathlib import Path

import fitz
import pytesseract
from docx import Document
from PIL import Image
from pypdf import PdfReader


def _ocr_available() -> bool:
    try:
        _ = pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _text_looks_valid(text: str, min_chars: int = 200) -> bool:
    """Check if extracted text is substantial and not garbled."""
    stripped = text.strip()
    if len(stripped) < min_chars:
        return False
    alpha = sum(1 for c in stripped if c.isalpha())
    if len(stripped) > 0 and alpha / len(stripped) < 0.3:
        return False
    return True


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
        text = _extract_pdf_text(content)
        if _text_looks_valid(text):
            return text, False
        if _ocr_available():
            ocr_text = _extract_pdf_text_with_ocr(content)
            if len(ocr_text.strip()) > len(text.strip()):
                return ocr_text, True
        return text, False

    if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}:
        if _ocr_available():
            return _extract_image_text(content), True
        return "", False

    return content.decode("utf-8", errors="ignore"), False
