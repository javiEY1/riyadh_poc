from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

from app.models import (
    ClauseExtraction,
    ConfidenceRow,
    ContractClassification,
    ContractDetails,
    EvidenceRow,
    ExtractionResult,
    Jurisdictions,
    NatureOfSupply,
    NOT_FOUND,
    Party,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a contract metadata extraction engine for Riyadh Air.
Given the full text of a contract, extract ALL of the following fields as JSON.
If a value cannot be found, use the exact string "NOT FOUND IN CONTRACT".

Return a single JSON object (no markdown fences) with this exact structure:

{
  "contract_classification": {
    "primary_type": "<one of: Services – Advisory, Services – Operational, Goods, Fuel Supply, Digital – SaaS, Mixed>",
    "sub_type": "<description>"
  },
  "parties": [
    {
      "name": "<legal entity name>",
      "role": "<Buyer/Client or Supplier/Vendor>",
      "registered_address": "<address>",
      "jurisdiction": "<country>"
    }
  ],
  "jurisdictions": {
    "supplier_jurisdiction": "<country>",
    "buyer_jurisdiction": "<country>",
    "service_delivery_locations": ["<country1>", "<country2>"]
  },
  "contract_details": {
    "title": "<contract title>",
    "effective_date": "<date as found>",
    "term_duration": "<duration>",
    "renewal_provisions": "<renewal terms>",
    "estimated_value": "<monetary value>",
    "payment_currency": "<currency code>",
    "language": "<English or Arabic or Other>",
    "expiration_date": "<date>"
  },
  "nature_of_supply": {
    "description": "<brief description>",
    "verbatim_scope": "<exact scope text from contract>",
    "scope_section_reference": "<section reference>"
  },
  "clause_groups": {
    "Tax-related clauses": [
      {"code": "TAX001", "title": "Tax definitions", "text": "<verbatim clause text>", "reference": "<section ref>"},
      {"code": "TAX002", "title": "Tax clause / tax provisions", "text": "...", "reference": "..."},
      {"code": "TAX003", "title": "Withholding tax provisions", "text": "...", "reference": "..."},
      {"code": "TAX004", "title": "VAT/GST provisions", "text": "...", "reference": "..."},
      {"code": "TAX005", "title": "Gross-up clause", "text": "...", "reference": "..."},
      {"code": "TAX006", "title": "Tax indemnification provisions", "text": "...", "reference": "..."},
      {"code": "TAX007", "title": "Tax representations and warranties", "text": "...", "reference": "..."},
      {"code": "TAX008", "title": "Tax residency certificate obligations", "text": "...", "reference": "..."}
    ],
    "Payment clauses": [
      {"code": "PAY001", "title": "Payment terms and fee structure", "text": "...", "reference": "..."},
      {"code": "PAY002", "title": "Payment currency and exchange rate provisions", "text": "...", "reference": "..."},
      {"code": "PAY003", "title": "Invoicing requirements", "text": "...", "reference": "..."}
    ],
    "Service-related clauses": [
      {"code": "SVC001", "title": "Scope of services / nature of supply (full description)", "text": "...", "reference": "..."},
      {"code": "SVC002", "title": "Service delivery location / place of supply", "text": "...", "reference": "..."},
      {"code": "SVC003", "title": "Personnel deployment / secondment provisions", "text": "...", "reference": "..."},
      {"code": "SVC004", "title": "Subcontracting provisions", "text": "...", "reference": "..."}
    ],
    "Intellectual Property": [
      {"code": "IP001", "title": "Intellectual property / licensing terms", "text": "...", "reference": "..."},
      {"code": "IP002", "title": "Royalty provisions", "text": "...", "reference": "..."},
      {"code": "IP003", "title": "Software licence grant terms", "text": "...", "reference": "..."}
    ],
    "Governing and dispute": [
      {"code": "GOV001", "title": "Governing law and jurisdiction", "text": "...", "reference": "..."},
      {"code": "GOV002", "title": "Dispute resolution", "text": "...", "reference": "..."}
    ],
    "Goods-related clauses": [
      {"code": "GDS001", "title": "Delivery terms / Incoterms (for goods contracts)", "text": "...", "reference": "..."},
      {"code": "GDS002", "title": "Title transfer provisions (for goods contracts)", "text": "...", "reference": "..."}
    ],
    "General clauses": [
      {"code": "GEN001", "title": "Indemnification (general, including tax-related)", "text": "...", "reference": "..."},
      {"code": "GEN002", "title": "Limitation of liability", "text": "...", "reference": "..."},
      {"code": "GEN003", "title": "Confidentiality (if tax-relevant)", "text": "...", "reference": "..."},
      {"code": "GEN004", "title": "Term, termination, and renewal provisions", "text": "...", "reference": "..."},
      {"code": "GEN005", "title": "Treaty references", "text": "...", "reference": "..."}
    ]
  }
}

Rules:
- CRITICAL: Clause text MUST be copied verbatim from the contract. Do NOT paraphrase, summarise or generate clause text. Copy-paste the exact words.
- Party names must be legal entity names, not phrases.
- For clause text, quote the exact passage as it appears in the document. Keep it under 500 chars.
- For clause reference, provide the section number or heading.
- If a clause is not found in the contract, set text to "NOT FOUND IN CONTRACT".
- Return ONLY the JSON object, no explanation.
"""


def _safe_get(data: dict, *keys: str, default: Any = NOT_FOUND) -> Any:
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key, default)
        else:
            return default
    return current if current is not None else default


def _parse_llm_json(raw: str) -> dict:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def _build_parties(data: list) -> List[Party]:
    parties = []
    for p in data or []:
        role = p.get("role", "Supplier/Vendor")
        if role not in ("Buyer/Client", "Supplier/Vendor"):
            role = "Supplier/Vendor"
        parties.append(
            Party(
                name=p.get("name", NOT_FOUND),
                role=role,
                registered_address=p.get("registered_address", NOT_FOUND),
                jurisdiction=p.get("jurisdiction", NOT_FOUND),
            )
        )
    return parties or [
        Party(name=NOT_FOUND, role="Buyer/Client"),
        Party(name=NOT_FOUND, role="Supplier/Vendor"),
    ]


def _build_clauses(group_data: list) -> List[ClauseExtraction]:
    clauses = []
    for c in group_data or []:
        clauses.append(
            ClauseExtraction(
                code=c.get("code", ""),
                title=c.get("title", ""),
                text=c.get("text", NOT_FOUND),
                reference=c.get("reference", NOT_FOUND),
            )
        )
    return clauses


def _build_clause_groups(data: dict) -> Dict[str, List[ClauseExtraction]]:
    groups: Dict[str, List[ClauseExtraction]] = {}
    for group_name, clauses_data in (data or {}).items():
        groups[group_name] = _build_clauses(clauses_data)
    return groups


def _validate_clauses_verbatim(
    clause_groups: Dict[str, List[ClauseExtraction]],
    source_text: str,
) -> None:
    """Discard clause text that cannot be found in the source document."""
    haystack = re.sub(r"\s+", " ", source_text.lower())
    for clauses in clause_groups.values():
        for clause in clauses:
            if clause.text == NOT_FOUND or not clause.text:
                continue
            probe = re.sub(r"\s+", " ", clause.text.strip().lower())
            # Try full text, then progressively shorter prefixes
            found = False
            for length in (len(probe), min(120, len(probe)), min(60, len(probe))):
                if length < 15:
                    break
                if probe[:length] in haystack:
                    found = True
                    break
            if not found:
                clause.text = NOT_FOUND


def _confidence_level(score: float) -> str:
    if score >= 0.8:
        return "High"
    if score >= 0.5:
        return "Medium"
    return "Low"


def _build_confidence_from_llm(result: ExtractionResult) -> List[ConfidenceRow]:
    rows: List[ConfidenceRow] = []

    def add(section: str, field: str, value: str, base_score: float = 0.88) -> None:
        score = 0.0 if (not value or value == NOT_FOUND) else min(base_score, 0.99)
        rows.append(
            ConfidenceRow(
                section=section,
                field=field,
                value=value,
                confidence_score=round(score, 2),
                confidence_level=_confidence_level(score),
            )
        )

    add("Contract Classification", "Primary Type", result.contract_classification.primary_type, 0.90)
    add("Contract Classification", "Sub Type", result.contract_classification.sub_type, 0.85)

    for party in result.parties:
        sec = "Buyer" if party.role == "Buyer/Client" else "Supplier"
        add(sec, "Name", party.name, 0.92)
        add(sec, "Role", party.role, 0.95)
        add(sec, "Registered Address", party.registered_address, 0.85)
        add(sec, "Jurisdiction", party.jurisdiction, 0.88)

    j = result.jurisdictions
    add("Jurisdictions", "Supplier Jurisdiction", j.supplier_jurisdiction, 0.88)
    add("Jurisdictions", "Buyer Jurisdiction", j.buyer_jurisdiction, 0.88)
    locs = ", ".join(j.service_delivery_locations) if j.service_delivery_locations else NOT_FOUND
    add("Jurisdictions", "Service Delivery Locations", locs, 0.85)

    d = result.contract_details
    add("Contract Details", "Title", d.title, 0.90)
    add("Contract Details", "Effective Date", d.effective_date, 0.92)
    add("Contract Details", "Term Duration", d.term_duration, 0.88)
    add("Contract Details", "Renewal Provisions", d.renewal_provisions, 0.85)
    add("Contract Details", "Estimated Value", d.estimated_value, 0.90)
    add("Contract Details", "Payment Currency", d.payment_currency, 0.92)
    add("Contract Details", "Language", d.language, 0.88)
    add("Contract Details", "Expiration Date", d.expiration_date, 0.85)

    n = result.nature_of_supply
    add("Nature of Supply", "Description", n.description, 0.88)
    add("Nature of Supply", "Verbatim Scope", n.verbatim_scope, 0.90)
    add("Nature of Supply", "Scope Section Reference", n.scope_section_reference, 0.88)

    for group_name, clauses in result.clause_groups.items():
        for clause in clauses:
            score = 0.0
            if clause.text != NOT_FOUND:
                score = 0.88 + (0.06 if clause.reference != NOT_FOUND else 0.0)
            add(group_name, f"{clause.code}: {clause.title}", clause.text, score)

    if result.ocr_used:
        for row in rows:
            row.confidence_score = round(min(row.confidence_score * 0.93, 0.99), 2)
            row.confidence_level = _confidence_level(row.confidence_score)

    return rows


def _find_snippet(text: str, value: str, window: int = 120) -> str:
    if not value or value == NOT_FOUND:
        return NOT_FOUND
    search_val = value[:120].strip()
    idx = text.lower().find(search_val.lower())
    if idx == -1:
        words = search_val.split()
        for word in words:
            if len(word) > 4:
                idx = text.lower().find(word.lower())
                if idx != -1:
                    break
    if idx == -1:
        return NOT_FOUND
    start = max(0, idx - window)
    end = min(len(text), idx + len(search_val) + window)
    return text[start:end].strip()


def _build_evidence_from_llm(
    text: str, conf_rows: List[ConfidenceRow],
) -> List[EvidenceRow]:
    from app.parser import _get_rationale

    evidence: List[EvidenceRow] = []
    for row in conf_rows:
        snippet = _find_snippet(text, row.value)
        terms: List[str] = []
        if row.value != NOT_FOUND:
            raw = [t.strip() for t in re.split(r",", row.value) if t.strip()]
            terms = [t[:80] for t in raw if len(t) <= 200][:4]
            if not terms:
                terms = [row.value[:80]]
        rationale = ""
        if row.value != NOT_FOUND:
            rationale = _get_rationale(row.section, row.field)
            if not rationale.startswith("Detected by keyword"):
                rationale = "LLM-extracted. " + rationale
        evidence.append(
            EvidenceRow(
                section=row.section,
                field=row.field,
                value=row.value,
                snippet=snippet,
                highlight_terms=terms,
                rationale=rationale,
            )
        )
    return evidence


def _build_field_hints(metadata_prompt: str | None) -> str:
    if not metadata_prompt:
        return ""
    hints: list[str] = []
    for match in re.finditer(
        r"^\s*(field\.[a-z_]+\.keywords)\s*=\s*(.+)$",
        metadata_prompt,
        flags=re.IGNORECASE | re.MULTILINE,
    ):
        key = match.group(1).strip()
        value = match.group(2).strip()
        hints.append(f"- {key}: {value}")
    if not hints:
        return ""
    return (
        "\n\nAdditional field extraction guidance from configuration:\n"
        + "\n".join(hints)
    )


async def parse_contract_with_llm(
    text: str,
    api_key: str,
    ocr_used: bool = False,
    model: str = "gpt-4o-mini",
    metadata_prompt: str | None = None,
    azure_endpoint: str | None = None,
    azure_deployment: str | None = None,
) -> ExtractionResult:
    if azure_endpoint:
        from openai import AsyncAzureOpenAI
        endpoint = azure_endpoint.rstrip("/")
        endpoint = endpoint.removesuffix("/openai/v1").removesuffix("/openai")
        client = AsyncAzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version="2024-06-01",
        )
        deploy = azure_deployment or model
    else:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=api_key)
        deploy = model

    truncated = text[:12000] if len(text) > 12000 else text
    field_hints = _build_field_hints(metadata_prompt)
    system_content = SYSTEM_PROMPT + field_hints

    response = await client.chat.completions.create(
        model=deploy,
        temperature=0.1,
        messages=[
            {"role": "system", "content": system_content},
            {"role": "user", "content": f"Extract metadata from this contract:\n\n{truncated}"},
        ],
    )

    raw_content = response.choices[0].message.content or "{}"
    data = _parse_llm_json(raw_content)

    cc = _safe_get(data, "contract_classification", default={})
    primary = cc.get("primary_type", "Mixed") if isinstance(cc, dict) else "Mixed"
    valid_types = {
        "Services – Advisory", "Services – Operational", "Goods",
        "Fuel Supply", "Digital – SaaS", "Mixed",
    }
    if primary not in valid_types:
        primary = "Mixed"

    details_data = _safe_get(data, "contract_details", default={})
    lang = details_data.get("language", "Other") if isinstance(details_data, dict) else "Other"
    if lang not in ("English", "Arabic", "Other"):
        lang = "Other"

    jur = _safe_get(data, "jurisdictions", default={})
    locations = jur.get("service_delivery_locations", []) if isinstance(jur, dict) else []
    if not isinstance(locations, list):
        locations = []

    nature_data = _safe_get(data, "nature_of_supply", default={})

    result = ExtractionResult(
        contract_classification=ContractClassification(
            primary_type=primary,
            sub_type=cc.get("sub_type", NOT_FOUND) if isinstance(cc, dict) else NOT_FOUND,
        ),
        parties=_build_parties(_safe_get(data, "parties", default=[])),
        jurisdictions=Jurisdictions(
            supplier_jurisdiction=jur.get("supplier_jurisdiction", NOT_FOUND) if isinstance(jur, dict) else NOT_FOUND,
            buyer_jurisdiction=jur.get("buyer_jurisdiction", NOT_FOUND) if isinstance(jur, dict) else NOT_FOUND,
            service_delivery_locations=locations,
        ),
        contract_details=ContractDetails(
            title=details_data.get("title", NOT_FOUND) if isinstance(details_data, dict) else NOT_FOUND,
            effective_date=details_data.get("effective_date", NOT_FOUND) if isinstance(details_data, dict) else NOT_FOUND,
            term_duration=details_data.get("term_duration", NOT_FOUND) if isinstance(details_data, dict) else NOT_FOUND,
            renewal_provisions=details_data.get("renewal_provisions", NOT_FOUND) if isinstance(details_data, dict) else NOT_FOUND,
            estimated_value=details_data.get("estimated_value", NOT_FOUND) if isinstance(details_data, dict) else NOT_FOUND,
            payment_currency=details_data.get("payment_currency", NOT_FOUND) if isinstance(details_data, dict) else NOT_FOUND,
            language=lang,
            expiration_date=details_data.get("expiration_date", NOT_FOUND) if isinstance(details_data, dict) else NOT_FOUND,
        ),
        nature_of_supply=NatureOfSupply(
            description=nature_data.get("description", NOT_FOUND) if isinstance(nature_data, dict) else NOT_FOUND,
            verbatim_scope=nature_data.get("verbatim_scope", NOT_FOUND) if isinstance(nature_data, dict) else NOT_FOUND,
            scope_section_reference=nature_data.get("scope_section_reference", NOT_FOUND) if isinstance(nature_data, dict) else NOT_FOUND,
        ),
        clause_groups=_build_clause_groups(_safe_get(data, "clause_groups", default={})),
        ocr_used=ocr_used,
    )

    _validate_clauses_verbatim(result.clause_groups, text)

    conf_table = _build_confidence_from_llm(result)
    result.confidence_table = conf_table
    result.evidence_table = _build_evidence_from_llm(text, conf_table)
    result.overall_confidence = (
        round(sum(r.confidence_score for r in conf_table) / len(conf_table), 2)
        if conf_table else 0.0
    )
    return result
