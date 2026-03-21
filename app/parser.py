from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

from app.models import (
    ClauseExtraction,
    ContractClassification,
    ContractDetails,
    ExtractionResult,
    Jurisdictions,
    NatureOfSupply,
    NOT_FOUND,
    Party,
)


COUNTRIES = [
    "United Arab Emirates",
    "UAE",
    "Saudi Arabia",
    "Qatar",
    "Bahrain",
    "Kuwait",
    "Oman",
    "Jordan",
    "Egypt",
    "United Kingdom",
    "UK",
    "England",
    "Scotland",
    "United States",
    "USA",
    "India",
    "Singapore",
    "Germany",
    "France",
    "Netherlands",
    "Switzerland",
]

CLAUSE_DEFINITIONS: Dict[str, List[Tuple[str, str, List[str]]]] = {
    "Tax-related clauses": [
        ("TAX001", "Tax definitions", ["tax means", "taxes means", "definition of tax", "tax definition"]),
        ("TAX002", "Tax clause / tax provisions", ["tax", "taxation", "fiscal"]),
        ("TAX003", "Withholding tax provisions", ["withholding tax", "withhold", "deduct tax"]),
        ("TAX004", "VAT/GST provisions", ["vat", "gst", "value added tax", "goods and services tax"]),
        ("TAX005", "Gross-up clause", ["gross-up", "gross up", "net of tax"]),
        ("TAX006", "Tax indemnification provisions", ["tax indemn", "indemnify", "tax liability"]),
        (
            "TAX007",
            "Tax representations and warranties",
            ["representation", "warranty", "tax compliance", "tax status"],
        ),
        (
            "TAX008",
            "Tax residency certificate obligations",
            ["tax residency certificate", "residency certificate", "certificate of residence"],
        ),
    ],
    "Payment clauses": [
        ("PAY001", "Payment terms and fee structure", ["payment terms", "fees", "consideration", "price"]),
        (
            "PAY002",
            "Payment currency and exchange rate provisions",
            ["currency", "exchange rate", "conversion", "usd", "eur", "aed"],
        ),
        ("PAY003", "Invoicing requirements", ["invoice", "billing", "tax invoice", "invoicing"]),
    ],
    "Service-related clauses": [
        (
            "SVC001",
            "Scope of services / nature of supply (full description)",
            ["scope of services", "services", "statement of work", "deliverables", "scope"],
        ),
        (
            "SVC002",
            "Service delivery location / place of supply",
            ["place of supply", "service location", "performed at", "delivery location"],
        ),
        (
            "SVC003",
            "Personnel deployment / secondment provisions",
            ["personnel", "secondment", "staff", "employees", "resources"],
        ),
        ("SVC004", "Subcontracting provisions", ["subcontract", "sub-contractor", "outsource"]),
    ],
    "Intellectual Property": [
        (
            "IP001",
            "Intellectual property / licensing terms",
            ["intellectual property", "ip rights", "license", "licence", "ownership"],
        ),
        ("IP002", "Royalty provisions", ["royalty", "royalties"]),
        (
            "IP003",
            "Software licence grant terms",
            ["software license", "software licence", "license grant", "licence grant", "saas"],
        ),
    ],
    "Governing and dispute": [
        (
            "GOV001",
            "Governing law and jurisdiction",
            ["governing law", "jurisdiction", "laws of", "courts of"],
        ),
        (
            "GOV002",
            "Dispute resolution",
            ["dispute", "arbitration", "conciliation", "mediation", "tribunal"],
        ),
    ],
    "Goods-related clauses": [
        (
            "GDS001",
            "Delivery terms / Incoterms (for goods contracts)",
            ["incoterms", "delivery terms", "fob", "cif", "ddp", "shipment"],
        ),
        (
            "GDS002",
            "Title transfer provisions (for goods contracts)",
            ["title passes", "transfer of title", "risk of loss", "ownership transfer"],
        ),
    ],
    "General clauses": [
        (
            "GEN001",
            "Indemnification (general, including tax-related)",
            ["indemn", "hold harmless", "defend"],
        ),
        (
            "GEN002",
            "Limitation of liability",
            ["limitation of liability", "liability cap", "consequential damages"],
        ),
        (
            "GEN003",
            "Confidentiality (if tax-relevant)",
            ["confidentiality", "confidential information", "non-disclosure"],
        ),
        (
            "GEN004",
            "Term, termination, and renewal provisions",
            ["term", "termination", "renewal", "expiry", "expiration"],
        ),
        (
            "GEN005",
            "Treaty references",
            ["treaty", "double taxation", "tax treaty", "dtAA", "multilateral"],
        ),
    ],
}


@dataclass
class Section:
    reference: str
    title: str
    text: str


def _clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _looks_like_heading(line: str) -> bool:
    line = line.strip()
    if len(line) < 3 or len(line) > 120:
        return False
    if re.match(r"^\d+(\.\d+)*[\).\-\s]+[A-Za-z].+", line):
        return True
    words = line.split()
    if len(words) <= 10 and line.upper() == line and re.search(r"[A-Z]", line):
        return True
    return False


def _split_sections(text: str) -> List[Section]:
    lines = [line.strip() for line in text.splitlines()]
    sections: List[Section] = []
    cur_title = "Full Contract"
    cur_ref = "FULL"
    buffer: List[str] = []

    for line in lines:
        if not line:
            continue
        if _looks_like_heading(line):
            if buffer:
                sections.append(Section(reference=cur_ref, title=cur_title, text="\n".join(buffer).strip()))
                buffer = []
            cur_title = line
            ref_match = re.match(r"^(\d+(?:\.\d+)*)", line)
            cur_ref = ref_match.group(1) if ref_match else line[:20]
        else:
            buffer.append(line)

    if buffer:
        sections.append(Section(reference=cur_ref, title=cur_title, text="\n".join(buffer).strip()))

    return sections or [Section(reference="FULL", title="Full Contract", text=text)]


def _first_match(patterns: List[str], text: str, group: int = 1) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(group).strip(" .,:;\n")
    return NOT_FOUND


def _extract_country(blob: str) -> str:
    for country in COUNTRIES:
        if re.search(rf"\b{re.escape(country)}\b", blob, flags=re.IGNORECASE):
            return country
    return NOT_FOUND


def _extract_title(text: str) -> str:
    for line in text.splitlines()[:15]:
        candidate = line.strip()
        if not candidate:
            continue
        if re.search(r"contract|agreement|master service|statement of work", candidate, re.IGNORECASE):
            return candidate
    for line in text.splitlines()[:15]:
        candidate = line.strip()
        if candidate:
            return candidate[:180]
    return NOT_FOUND


def _extract_language(text: str) -> str:
    arabic_chars = re.findall(r"[\u0600-\u06FF]", text)
    latin_chars = re.findall(r"[A-Za-z]", text)
    if arabic_chars and len(arabic_chars) > max(20, len(latin_chars) * 0.2):
        return "Arabic"
    if latin_chars:
        return "English"
    return "Other"


def _extract_currency(text: str) -> str:
    currency_patterns = [
        r"\b(USD|EUR|GBP|AED|SAR|QAR|KWD|OMR|BHD|INR|JPY|CNY)\b",
        r"(US\$|\$|€|£|AED|SAR)",
    ]
    for pattern in currency_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).upper()
    return NOT_FOUND


def _extract_parties(text: str) -> List[Party]:
    parties: List[Party] = []
    intro = "\n".join(text.splitlines()[:120])
    between_match = re.search(
        r"between\s+(.+?)\s+and\s+(.+?)(?:\n|\.|$)",
        intro,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if between_match:
        first = re.sub(r"\s+", " ", between_match.group(1)).strip(" ,")
        second = re.sub(r"\s+", " ", between_match.group(2)).strip(" ,")
        if first:
            parties.append(
                Party(name=first[:160], role="Buyer/Client", jurisdiction=_extract_country(first))
            )
        if second:
            parties.append(
                Party(name=second[:160], role="Supplier/Vendor", jurisdiction=_extract_country(second))
            )

    role_hits = re.finditer(
        r"([A-Z][A-Za-z0-9&.,'\-\s]{2,120})\s*\((?:the\s+)?(Buyer|Client|Supplier|Vendor|Seller)\)",
        intro,
        flags=re.IGNORECASE,
    )
    for hit in role_hits:
        name = re.sub(r"\s+", " ", hit.group(1)).strip(" ,")
        role_raw = hit.group(2).lower()
        role = "Buyer/Client" if role_raw in {"buyer", "client"} else "Supplier/Vendor"
        if name and all(p.name.lower() != name.lower() for p in parties):
            parties.append(Party(name=name, role=role, jurisdiction=_extract_country(name)))

    return parties[:4]


def _summary_from_scope(scope_text: str) -> str:
    if scope_text == NOT_FOUND:
        return NOT_FOUND
    first_sentence = re.split(r"(?<=[.!?])\s+", scope_text.strip())[0]
    return first_sentence[:300] if first_sentence else scope_text[:300]


def _extract_contract_classification(text: str) -> ContractClassification:
    lower = text.lower()
    type_keywords = {
        "Services – Advisory": ["consulting", "advisory", "professional services", "legal", "audit"],
        "Services – Operational": ["maintenance", "operations", "support services", "ground handling"],
        "Goods": ["purchase order", "supply of goods", "delivery", "inventory", "shipment"],
        "Fuel Supply": ["fuel", "aviation fuel", "jet a-1", "bunkering"],
        "Digital – SaaS": ["saas", "software", "subscription", "license", "licence", "cloud service"],
    }
    scores = {name: 0 for name in type_keywords}
    for name, keys in type_keywords.items():
        for key in keys:
            scores[name] += lower.count(key)
    best = max(scores, key=scores.get)
    non_zero = [k for k, v in scores.items() if v > 0]
    primary = "Mixed" if len(non_zero) > 1 and scores[best] <= 3 else best

    subtype_map = [
        ("Legal Consulting", ["legal consulting", "legal advisory"]),
        ("Ground Handling", ["ground handling"]),
        ("Software Licence", ["software license", "software licence", "license grant", "licence grant"]),
        ("SaaS Subscription", ["saas", "subscription"]),
        ("Fuel Supply", ["fuel supply", "jet a-1", "aviation fuel"]),
        ("Goods Supply", ["supply of goods", "purchase and sale", "delivery of goods"]),
    ]
    subtype = NOT_FOUND
    for label, keys in subtype_map:
        if any(k in lower for k in keys):
            subtype = label
            break

    return ContractClassification(primary_type=primary, sub_type=subtype)


def _match_clause(sections: List[Section], keywords: List[str]) -> Tuple[str, str]:
    best_score = 0
    best_section: Section | None = None
    for section in sections:
        haystack = f"{section.title}\n{section.text}".lower()
        score = 0
        for keyword in keywords:
            score += haystack.count(keyword.lower()) * (2 if keyword.lower() in section.title.lower() else 1)
        if score > best_score:
            best_score = score
            best_section = section

    if not best_section or best_score == 0:
        return NOT_FOUND, NOT_FOUND
    excerpt = best_section.text.strip()
    if len(excerpt) > 3000:
        excerpt = excerpt[:3000].rsplit(" ", 1)[0] + " ..."
    return excerpt or NOT_FOUND, best_section.reference


def _extract_clause_groups(sections: List[Section]) -> Dict[str, List[ClauseExtraction]]:
    out: Dict[str, List[ClauseExtraction]] = {}
    for group_name, items in CLAUSE_DEFINITIONS.items():
        group_rows: List[ClauseExtraction] = []
        for code, title, keywords in items:
            text, ref = _match_clause(sections, keywords)
            group_rows.append(ClauseExtraction(code=code, title=title, text=text, reference=ref))
        out[group_name] = group_rows
    return out


def _extract_contract_details(text: str, sections: List[Section]) -> ContractDetails:
    effective_date = _first_match(
        [
            r"effective date\s*[:\-]?\s*([A-Za-z0-9,\-\/ ]{5,40})",
            r"commencement date\s*[:\-]?\s*([A-Za-z0-9,\-\/ ]{5,40})",
        ],
        text,
    )
    expiration_date = _first_match(
        [
            r"expiration date\s*[:\-]?\s*([A-Za-z0-9,\-\/ ]{5,40})",
            r"expires?\s+on\s+([A-Za-z0-9,\-\/ ]{5,40})",
        ],
        text,
    )
    term_duration = _first_match(
        [
            r"term(?:\s+of)?\s+(?:shall be|is|for)?\s*([^.\n]{5,80})",
            r"duration\s*[:\-]?\s*([^.\n]{5,80})",
        ],
        text,
    )

    renewal_clause = _match_clause(sections, ["renewal", "renew", "extension", "auto-renew"])[0]
    renewal_provisions = _summary_from_scope(renewal_clause)

    estimated_value = _first_match(
        [
            r"(?:contract value|total value|estimated value|total fees?)\s*[:\-]?\s*([^\n.]{3,80})",
            r"(USD|EUR|GBP|AED|SAR|QAR|KWD|OMR|BHD|INR|US\$|\$|€|£)\s?([0-9][0-9,\.]{2,})",
        ],
        text,
    )
    payment_currency = _extract_currency(
        _match_clause(sections, ["payment", "invoice", "fee", "currency"])[0]
    )
    if payment_currency == NOT_FOUND:
        payment_currency = _extract_currency(text)

    return ContractDetails(
        title=_extract_title(text),
        effective_date=effective_date,
        term_duration=term_duration,
        renewal_provisions=renewal_provisions,
        estimated_value=estimated_value,
        payment_currency=payment_currency,
        language=_extract_language(text),
        expiration_date=expiration_date,
    )


def parse_contract(text: str, ocr_used: bool = False) -> ExtractionResult:
    cleaned = _clean_text(text)
    sections = _split_sections(cleaned)
    clause_groups = _extract_clause_groups(sections)

    parties = _extract_parties(cleaned)
    if not parties:
        parties = [Party(name=NOT_FOUND, role="Other")]

    gov_clause = clause_groups["Governing and dispute"][0].text
    supplier_jurisdiction = next(
        (p.jurisdiction for p in parties if p.role == "Supplier/Vendor" and p.jurisdiction != NOT_FOUND),
        NOT_FOUND,
    )
    buyer_jurisdiction = next(
        (p.jurisdiction for p in parties if p.role == "Buyer/Client" and p.jurisdiction != NOT_FOUND),
        NOT_FOUND,
    )
    if supplier_jurisdiction == NOT_FOUND:
        supplier_jurisdiction = _extract_country(gov_clause)
    if buyer_jurisdiction == NOT_FOUND:
        buyer_jurisdiction = _extract_country(gov_clause)

    svc_location_clause = clause_groups["Service-related clauses"][1].text
    locations = [
        c
        for c in COUNTRIES
        if re.search(rf"\b{re.escape(c)}\b", svc_location_clause, flags=re.IGNORECASE)
    ]

    scope_clause = clause_groups["Service-related clauses"][0]
    nature = NatureOfSupply(
        description=_summary_from_scope(scope_clause.text),
        verbatim_scope=scope_clause.text,
        scope_section_reference=scope_clause.reference,
    )

    return ExtractionResult(
        contract_classification=_extract_contract_classification(cleaned),
        parties=parties,
        jurisdictions=Jurisdictions(
            supplier_jurisdiction=supplier_jurisdiction,
            buyer_jurisdiction=buyer_jurisdiction,
            service_delivery_locations=locations,
        ),
        contract_details=_extract_contract_details(cleaned, sections),
        nature_of_supply=nature,
        clause_groups=clause_groups,
        ocr_used=ocr_used,
    )
