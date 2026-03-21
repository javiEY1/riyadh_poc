from __future__ import annotations

import json
from io import BytesIO

from openpyxl import Workbook

from app.models import ExtractionResult


def build_json_bytes(result: ExtractionResult) -> bytes:
    return json.dumps(result.model_dump(), ensure_ascii=False, indent=2).encode("utf-8")


def build_excel_bytes(result: ExtractionResult) -> bytes:
    workbook = Workbook()

    confidence_sheet = workbook.active
    confidence_sheet.title = "Confidence"
    confidence_sheet.append(["Section", "Field", "Value", "Confidence Score", "Confidence Level"])
    for row in result.confidence_table:
        confidence_sheet.append(
            [
                row.section,
                row.field,
                row.value,
                row.confidence_score,
                row.confidence_level,
            ]
        )

    evidence_sheet = workbook.create_sheet(title="Evidence")
    evidence_sheet.append(["Section", "Field", "Value", "Snippet", "Highlight Terms"])
    for row in result.evidence_table:
        evidence_sheet.append(
            [
                row.section,
                row.field,
                row.value,
                row.snippet,
                ", ".join(row.highlight_terms),
            ]
        )

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
