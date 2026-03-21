from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

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

DEFAULT_SUPPLIER_ROLE_TERMS = [
    "supplier",
    "vendor",
    "seller",
    "contractor",
    "service provider",
    "provider",
    "licensor",
]

DEFAULT_BUYER_ROLE_TERMS = ["buyer", "client", "purchaser", "licensee"]

DEFAULT_LEGAL_ENTITY_MARKERS = [
    "llc",
    "l.l.c",
    "ltd",
    "limited",
    "inc",
    "corp",
    "corporation",
    "company",
    "plc",
    "llp",
    "lp",
    "pte",
    "pvt",
    "gmbh",
    "pjsc",
    "fzco",
    "fze",
    "ag",
    "nv",
    "bv",
]

DEFAULT_ENTITY_STOP_PHRASES = {
    "this agreement",
    "agreement is made",
    "collectively",
    "effective date",
    "hereinafter",
    "witnesseth",
    "shall",
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


DEFAULT_NAME_KEYWORDS = ["between", "by and between", "party", "parties", "hereinafter"]
DEFAULT_ADDRESS_KEYWORDS = [
    "registered office", "registered address", "principal place of business", "address",
]
DEFAULT_PARTY_JURISDICTION_KEYWORDS = ["incorporated in", "organized under", "laws of", "jurisdiction"]


@dataclass
class ParserRuntimeConfig:
    supplier_role_terms: List[str]
    buyer_role_terms: List[str]
    legal_entity_markers: List[str]
    entity_stop_phrases: List[str]
    clause_overrides: Dict[str, List[str]]
    buyer_name_keywords: List[str]
    supplier_name_keywords: List[str]
    buyer_address_keywords: List[str]
    supplier_address_keywords: List[str]
    buyer_jurisdiction_keywords: List[str]
    supplier_jurisdiction_keywords: List[str]


def _split_csv(value: str) -> List[str]:
    return [item.strip().lower() for item in value.split(",") if item.strip()]


def _cfg_list(metadata_prompt: str | None, key: str, default: List[str]) -> List[str]:
    if not metadata_prompt:
        return default
    match = re.search(rf"^\s*{re.escape(key)}\s*=\s*(.+)$", metadata_prompt, flags=re.IGNORECASE | re.MULTILINE)
    if not match:
        return default
    parsed = _split_csv(match.group(1))
    return parsed or default


def _parse_clause_overrides(metadata_prompt: str | None) -> Dict[str, List[str]]:
    overrides: Dict[str, List[str]] = {}
    if not metadata_prompt:
        return overrides
    for match in re.finditer(
        r"^\s*clause\.([A-Z]{2,4}\d{3})\.keywords\s*=\s*(.+)$",
        metadata_prompt,
        flags=re.IGNORECASE | re.MULTILINE,
    ):
        code = match.group(1).upper()
        keywords = [kw.strip().lower() for kw in match.group(2).split(",") if kw.strip()]
        if keywords:
            overrides[code] = keywords
    return overrides


def _build_runtime_config(metadata_prompt: str | None) -> ParserRuntimeConfig:
    return ParserRuntimeConfig(
        supplier_role_terms=_cfg_list(metadata_prompt, "supplier_role_terms", DEFAULT_SUPPLIER_ROLE_TERMS),
        buyer_role_terms=_cfg_list(metadata_prompt, "buyer_role_terms", DEFAULT_BUYER_ROLE_TERMS),
        legal_entity_markers=_cfg_list(metadata_prompt, "legal_entity_markers", DEFAULT_LEGAL_ENTITY_MARKERS),
        entity_stop_phrases=_cfg_list(
            metadata_prompt,
            "entity_stop_phrases",
            list(DEFAULT_ENTITY_STOP_PHRASES),
        ),
        clause_overrides=_parse_clause_overrides(metadata_prompt),
        buyer_name_keywords=_cfg_list(
            metadata_prompt, "field.buyer_name.keywords", DEFAULT_NAME_KEYWORDS,
        ),
        supplier_name_keywords=_cfg_list(
            metadata_prompt, "field.supplier_name.keywords", DEFAULT_NAME_KEYWORDS,
        ),
        buyer_address_keywords=_cfg_list(
            metadata_prompt, "field.buyer_registered_address.keywords", DEFAULT_ADDRESS_KEYWORDS,
        ),
        supplier_address_keywords=_cfg_list(
            metadata_prompt, "field.supplier_registered_address.keywords", DEFAULT_ADDRESS_KEYWORDS,
        ),
        buyer_jurisdiction_keywords=_cfg_list(
            metadata_prompt, "field.buyer_party_jurisdiction.keywords", DEFAULT_PARTY_JURISDICTION_KEYWORDS,
        ),
        supplier_jurisdiction_keywords=_cfg_list(
            metadata_prompt, "field.supplier_party_jurisdiction.keywords", DEFAULT_PARTY_JURISDICTION_KEYWORDS,
        ),
    )


def _clean_party_name(raw: str) -> str:
    name = re.sub(r"\s+", " ", raw).strip(" \n\t,.;:-\"'")
    name = re.sub(r"^(?:and|between|by and between)\s+", "", name, flags=re.IGNORECASE)
    name = re.sub(
        r"\((?:the\s+)?(?:buyer|client|supplier|vendor|seller|contractor|service provider|provider|purchaser|licensor|licensee)\)",
        "",
        name,
        flags=re.IGNORECASE,
    )
    name = re.sub(r"\s+(?:hereinafter(?:\s+referred\s+to)?\s+as)\b.*$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s*,?\s*(?:a|an)\s+(?:company|corporation|entity)\b.*$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s*,?\s*(?:organized|incorporated|registered)\b.*$", "", name, flags=re.IGNORECASE)
    return name.strip(" ,.;:-")[:160]


def _contains_legal_marker(name: str, config: ParserRuntimeConfig) -> bool:
    for marker in config.legal_entity_markers:
        marker_pattern = r"\b" + re.escape(marker).replace(r"\.", r"\.?") + r"\b"
        if re.search(marker_pattern, name, flags=re.IGNORECASE):
            return True
    return False


def _is_probable_entity_name(name: str, config: ParserRuntimeConfig) -> bool:
    if not name or len(name) < 3:
        return False
    lower = name.lower()
    if any(phrase in lower for phrase in config.entity_stop_phrases):
        return False

    words = re.findall(r"[A-Za-z0-9&'.\-]+", name)
    if len(words) < 2 or len(words) > 16:
        return False

    if _contains_legal_marker(name, config):
        return True

    capitalized = sum(1 for w in words if re.match(r"^[A-Z]", w))
    has_action_verbs = bool(re.search(r"\b(?:shall|agree|agrees|provide|perform|deliver|entered)\b", lower))
    return capitalized >= max(2, int(len(words) * 0.6)) and not has_action_verbs


def _map_role(role_raw: str, config: ParserRuntimeConfig) -> str:
    role = role_raw.strip().lower()
    if role in set(config.buyer_role_terms):
        return "Buyer/Client"
    if role in set(config.supplier_role_terms):
        return "Supplier/Vendor"
    return "Other"


def _extract_address_near(text: str, entity_name: str, keywords: List[str]) -> str:
    if not entity_name or entity_name == NOT_FOUND:
        return NOT_FOUND
    name_idx = text.lower().find(entity_name.lower()[:60])
    if name_idx == -1:
        return NOT_FOUND
    window = text[name_idx : name_idx + 600]
    for kw in keywords:
        pat = rf"{re.escape(kw)}\s*[:\-]?\s*([^\n;]{{5,200}})"
        m = re.search(pat, window, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip(" ,.;:")[:200]
    return NOT_FOUND


def _extract_jurisdiction_near(text: str, entity_name: str, keywords: List[str]) -> str:
    if not entity_name or entity_name == NOT_FOUND:
        return _extract_country(text)
    name_idx = text.lower().find(entity_name.lower()[:60])
    if name_idx == -1:
        return _extract_country(text)
    window = text[name_idx : name_idx + 600]
    for kw in keywords:
        pat = rf"{re.escape(kw)}\s*[:\-]?\s*(?:the\s+)?([^\n;,]{{3,100}})"
        m = re.search(pat, window, flags=re.IGNORECASE)
        if m:
            country = _extract_country(m.group(1))
            if country != NOT_FOUND:
                return country
    return _extract_country(window)


def _add_party(
    parties: List[Party],
    raw_name: str,
    role: str,
    config: ParserRuntimeConfig,
    full_text: str = "",
) -> None:
    name = _clean_party_name(raw_name)
    if not _is_probable_entity_name(name, config):
        return
    if any(p.name.lower() == name.lower() and p.role == role for p in parties):
        return
    if role == "Buyer/Client":
        addr_kw = config.buyer_address_keywords
        jur_kw = config.buyer_jurisdiction_keywords
    else:
        addr_kw = config.supplier_address_keywords
        jur_kw = config.supplier_jurisdiction_keywords
    address = _extract_address_near(full_text, name, addr_kw) if full_text else NOT_FOUND
    jurisdiction = _extract_jurisdiction_near(full_text, name, jur_kw) if full_text else _extract_country(name)
    parties.append(Party(name=name, role=role, registered_address=address, jurisdiction=jurisdiction))


def _extract_parties(text: str, config: ParserRuntimeConfig) -> List[Party]:
    parties: List[Party] = []
    intro = "\n".join(text.splitlines()[:180])

    supplier_terms_pattern = "|".join(re.escape(term) for term in config.supplier_role_terms)
    buyer_terms_pattern = "|".join(re.escape(term) for term in config.buyer_role_terms)

    labeled_patterns = [
        (
            rf"(?:{supplier_terms_pattern})\s*(?:name)?\s*[:\-]\s*([^\n;,]{{3,200}})",
            "Supplier/Vendor",
        ),
        (
            rf"(?:{buyer_terms_pattern})\s*(?:name)?\s*[:\-]\s*([^\n;,]{{3,200}})",
            "Buyer/Client",
        ),
    ]
    for pattern, role in labeled_patterns:
        for hit in re.finditer(pattern, intro, flags=re.IGNORECASE):
            _add_party(parties, hit.group(1), role, config, full_text=text)

    role_terms = config.buyer_role_terms + config.supplier_role_terms
    role_terms_pattern = "|".join(re.escape(term) for term in sorted(role_terms, key=len, reverse=True))
    role_hits = re.finditer(
        rf"([A-Z][A-Za-z0-9&.,'\-\s]{{2,180}}?)\s*\((?:the\s+)?({role_terms_pattern})\)",
        intro,
        flags=re.IGNORECASE,
    )
    for hit in role_hits:
        _add_party(parties, hit.group(1), _map_role(hit.group(2), config), config, full_text=text)

    flat_intro = re.sub(r"\s+", " ", intro)
    supplier_between_pattern = "|".join(re.escape(term) for term in config.supplier_role_terms)
    for between_match in re.finditer(
        r"between\s+(.{3,220}?)\s+and\s+(.{3,220}?)(?:\.|;|$)",
        flat_intro,
        flags=re.IGNORECASE,
    ):
        first = between_match.group(1)
        second = between_match.group(2)
        first_role = (
            "Supplier/Vendor"
            if re.search(rf"\b({supplier_between_pattern})\b", first, re.IGNORECASE)
            else "Buyer/Client"
        )
        second_role = "Supplier/Vendor" if first_role == "Buyer/Client" else "Buyer/Client"
        _add_party(parties, first, first_role, config, full_text=text)
        _add_party(parties, second, second_role, config, full_text=text)

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


def _extract_clause_groups(
    sections: List[Section],
    config: ParserRuntimeConfig | None = None,
) -> Dict[str, List[ClauseExtraction]]:
    overrides = config.clause_overrides if config else {}
    out: Dict[str, List[ClauseExtraction]] = {}
    for group_name, items in CLAUSE_DEFINITIONS.items():
        group_rows: List[ClauseExtraction] = []
        for code, title, default_keywords in items:
            keywords = overrides.get(code, default_keywords)
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


def _confidence_level(score: float) -> str:
    if score >= 0.8:
        return "High"
    if score >= 0.55:
        return "Medium"
    return "Low"


def _clamp_score(value: float) -> float:
    return max(0.0, min(0.99, value))


def _score_basic_value(value: str) -> float:
    if not value or value == NOT_FOUND:
        return 0.0
    score = 0.72
    if len(value) >= 24:
        score += 0.08
    return _clamp_score(score)


def _score_date(value: str) -> float:
    if value == NOT_FOUND:
        return 0.0
    if re.search(r"\b\d{1,2}[\-/ ]\d{1,2}[\-/ ]\d{2,4}\b", value):
        return 0.9
    if re.search(r"\b\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}\b", value):
        return 0.9
    return 0.68


def _score_party_name(value: str, config: ParserRuntimeConfig) -> float:
    if value == NOT_FOUND:
        return 0.0
    if _contains_legal_marker(value, config):
        return 0.92
    return 0.75 if _is_probable_entity_name(value, config) else 0.45


def _add_conf_row(
    rows: List[ConfidenceRow],
    section: str,
    field: str,
    value: str,
    score: float,
) -> None:
    clamped = _clamp_score(score)
    rows.append(
        ConfidenceRow(
            section=section,
            field=field,
            value=value,
            confidence_score=round(clamped, 2),
            confidence_level=_confidence_level(clamped),
        )
    )


def _build_confidence_table(
    result: ExtractionResult,
    config: ParserRuntimeConfig,
) -> tuple[List[ConfidenceRow], float]:
    rows: List[ConfidenceRow] = []

    _add_conf_row(
        rows,
        "Contract Classification",
        "Primary Type",
        result.contract_classification.primary_type,
        0.62 if result.contract_classification.primary_type == "Mixed" else 0.78,
    )
    _add_conf_row(
        rows,
        "Contract Classification",
        "Sub Type",
        result.contract_classification.sub_type,
        _score_basic_value(result.contract_classification.sub_type),
    )

    for idx, party in enumerate(result.parties, start=1):
        party_section = f"Parties [{idx}]"
        _add_conf_row(rows, party_section, "Name", party.name, _score_party_name(party.name, config))
        _add_conf_row(rows, party_section, "Role", party.role, 0.95 if party.role != "Other" else 0.4)
        _add_conf_row(
            rows,
            party_section,
            "Registered Address",
            party.registered_address,
            _score_basic_value(party.registered_address),
        )
        _add_conf_row(
            rows,
            party_section,
            "Jurisdiction",
            party.jurisdiction,
            0.85 if party.jurisdiction != NOT_FOUND else 0.0,
        )

    locations = result.jurisdictions.service_delivery_locations
    _add_conf_row(
        rows,
        "Jurisdictions",
        "Supplier Jurisdiction",
        result.jurisdictions.supplier_jurisdiction,
        0.85 if result.jurisdictions.supplier_jurisdiction != NOT_FOUND else 0.0,
    )
    _add_conf_row(
        rows,
        "Jurisdictions",
        "Buyer Jurisdiction",
        result.jurisdictions.buyer_jurisdiction,
        0.85 if result.jurisdictions.buyer_jurisdiction != NOT_FOUND else 0.0,
    )
    _add_conf_row(
        rows,
        "Jurisdictions",
        "Service Delivery Locations",
        ", ".join(locations) if locations else NOT_FOUND,
        0.84 if locations else 0.0,
    )

    details = result.contract_details
    _add_conf_row(rows, "Contract Details", "Title", details.title, _score_basic_value(details.title))
    _add_conf_row(rows, "Contract Details", "Effective Date", details.effective_date, _score_date(details.effective_date))
    _add_conf_row(rows, "Contract Details", "Term Duration", details.term_duration, _score_basic_value(details.term_duration))
    _add_conf_row(
        rows,
        "Contract Details",
        "Renewal Provisions",
        details.renewal_provisions,
        _score_basic_value(details.renewal_provisions),
    )
    _add_conf_row(
        rows,
        "Contract Details",
        "Estimated Value",
        details.estimated_value,
        0.88 if details.estimated_value != NOT_FOUND else 0.0,
    )
    _add_conf_row(
        rows,
        "Contract Details",
        "Payment Currency",
        details.payment_currency,
        0.9 if details.payment_currency != NOT_FOUND else 0.0,
    )
    _add_conf_row(
        rows,
        "Contract Details",
        "Language",
        details.language,
        0.86 if details.language != "Other" else 0.6,
    )
    _add_conf_row(rows, "Contract Details", "Expiration Date", details.expiration_date, _score_date(details.expiration_date))

    nature = result.nature_of_supply
    _add_conf_row(
        rows,
        "Nature of Supply",
        "Description",
        nature.description,
        _score_basic_value(nature.description),
    )
    _add_conf_row(
        rows,
        "Nature of Supply",
        "Verbatim Scope",
        nature.verbatim_scope,
        0.9 if nature.verbatim_scope != NOT_FOUND and len(nature.verbatim_scope) > 80 else _score_basic_value(nature.verbatim_scope),
    )
    _add_conf_row(
        rows,
        "Nature of Supply",
        "Scope Section Reference",
        nature.scope_section_reference,
        0.88 if nature.scope_section_reference != NOT_FOUND else 0.0,
    )

    for group_name, clauses in result.clause_groups.items():
        for clause in clauses:
            clause_score = 0.0
            if clause.text != NOT_FOUND:
                clause_score = 0.72 + (0.1 if clause.reference != NOT_FOUND else 0.0)
                if len(clause.text) > 120:
                    clause_score += 0.06
            _add_conf_row(
                rows,
                group_name,
                f"{clause.code}: {clause.title}",
                clause.text,
                clause_score,
            )

    if result.ocr_used:
        for row in rows:
            row.confidence_score = round(_clamp_score(row.confidence_score * 0.93), 2)
            row.confidence_level = _confidence_level(row.confidence_score)

    overall = round(sum(row.confidence_score for row in rows) / len(rows), 2) if rows else 0.0
    return rows, overall


def _find_snippet_for_value(text: str, value: str, window: int = 120) -> str:
    if not value or value == NOT_FOUND:
        return NOT_FOUND

    haystack = text.lower()
    probes: List[str] = [value.strip()]
    if len(value) > 120:
        probes.append(value.strip()[:100])

    parts = [p.strip() for p in re.split(r",", value) if p.strip()]
    if 1 < len(parts) <= 4:
        probes.extend(parts)

    words = re.findall(r"[A-Za-z0-9\-/]+", value)
    if len(words) >= 3:
        probes.append(" ".join(words[:3]))

    for probe in probes:
        idx = haystack.find(probe.lower())
        if idx >= 0:
            start = max(0, idx - window)
            end = min(len(text), idx + len(probe) + window)
            return text[start:end].strip() or NOT_FOUND

    return NOT_FOUND


def _build_evidence_table(text: str, confidence_rows: List[ConfidenceRow]) -> List[EvidenceRow]:
    evidence_rows: List[EvidenceRow] = []
    for row in confidence_rows:
        value = row.value
        snippet = _find_snippet_for_value(text, value)
        highlight_terms: List[str] = []
        if value != NOT_FOUND:
            raw_terms = [term.strip() for term in re.split(r",", value) if term.strip()]
            highlight_terms = [term[:80] for term in raw_terms if len(term) <= 200][:4]
            if not highlight_terms:
                highlight_terms = [value[:80]]

        evidence_rows.append(
            EvidenceRow(
                section=row.section,
                field=row.field,
                value=value,
                snippet=snippet,
                highlight_terms=highlight_terms,
            )
        )
    return evidence_rows


def parse_contract(
    text: str,
    ocr_used: bool = False,
    metadata_prompt: str | None = None,
) -> ExtractionResult:
    cleaned = _clean_text(text)
    runtime_config = _build_runtime_config(metadata_prompt)
    sections = _split_sections(cleaned)
    clause_groups = _extract_clause_groups(sections, runtime_config)

    parties = _extract_parties(cleaned, runtime_config)
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

    result = ExtractionResult(
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
    confidence_table, overall_confidence = _build_confidence_table(result, runtime_config)
    result.confidence_table = confidence_table
    result.evidence_table = _build_evidence_table(cleaned, confidence_table)
    result.overall_confidence = overall_confidence
    return result
