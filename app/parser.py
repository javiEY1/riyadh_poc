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
    "supplier", "vendor", "seller", "contractor", "service provider", "provider", "licensor",
]
DEFAULT_BUYER_ROLE_TERMS = ["buyer", "client", "purchaser", "licensee"]

DEFAULT_PRIMARY_TYPE_KEYWORDS = [
    "service agreement", "consulting agreement", "supply agreement", "software", "saas",
    "license agreement", "fuel supply", "goods",
]
DEFAULT_SUB_TYPE_KEYWORDS = [
    "advisory", "operational", "subscription", "maintenance", "procurement", "leasing",
]
DEFAULT_TITLE_KEYWORDS = [
    "agreement", "contract", "master service agreement", "statement of work", "framework agreement",
]
DEFAULT_EFFECTIVE_DATE_KEYWORDS = [
    "effective date", "commencement date", "start date", "dated as of", "entered into",
]
DEFAULT_TERM_DURATION_KEYWORDS = ["term", "duration", "period of", "months", "years"]
DEFAULT_RENEWAL_KEYWORDS = ["renewal", "auto-renew", "auto renew", "extend", "extension"]
DEFAULT_ESTIMATED_VALUE_KEYWORDS = [
    "total value", "contract value", "estimated value", "aggregate", "consideration", "not to exceed",
]
DEFAULT_PAYMENT_CURRENCY_KEYWORDS = [
    "usd", "eur", "gbp", "aed", "sar", "qar", "kwd", "omr", "bhd", "inr", "currency",
]
DEFAULT_LANGUAGE_KEYWORDS = ["english", "arabic", "language of the agreement"]
DEFAULT_EXPIRATION_DATE_KEYWORDS = [
    "expiration date", "expiry date", "end date", "termination date",
]
DEFAULT_SUPPLIER_JURISDICTION_KEYWORDS = [
    "supplier jurisdiction", "vendor jurisdiction", "incorporated", "organized under",
]
DEFAULT_BUYER_JURISDICTION_KEYWORDS = [
    "buyer jurisdiction", "client jurisdiction", "purchaser jurisdiction",
]
DEFAULT_SERVICE_DELIVERY_KEYWORDS = [
    "place of supply", "service location", "performed at", "delivery location", "delivered in",
]
DEFAULT_DESCRIPTION_KEYWORDS = [
    "scope of services", "nature of supply", "services description", "work description",
]
DEFAULT_VERBATIM_SCOPE_KEYWORDS = [
    "scope of services", "statement of work", "deliverables", "scope of work",
]
DEFAULT_SCOPE_REF_KEYWORDS = ["section", "article", "clause", "schedule", "annex", "exhibit"]

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
    return "Supplier/Vendor"


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
    primary_type_keywords: List[str]
    sub_type_keywords: List[str]
    title_keywords: List[str]
    effective_date_keywords: List[str]
    term_duration_keywords: List[str]
    renewal_keywords: List[str]
    estimated_value_keywords: List[str]
    payment_currency_keywords: List[str]
    language_keywords: List[str]
    expiration_date_keywords: List[str]
    supplier_jurisdiction_field_keywords: List[str]
    buyer_jurisdiction_field_keywords: List[str]
    service_delivery_keywords: List[str]
    description_keywords: List[str]
    verbatim_scope_keywords: List[str]
    scope_ref_keywords: List[str]


def _split_csv(value: str) -> List[str]:
    keywords_part = re.split(r"\.\s+[A-Z]", value, maxsplit=1)[0]
    return [item.strip().lower() for item in keywords_part.split(",") if item.strip()]


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
        supplier_role_terms=_cfg_list(
            metadata_prompt, "field.supplier_role.keywords", DEFAULT_SUPPLIER_ROLE_TERMS,
        ),
        buyer_role_terms=_cfg_list(
            metadata_prompt, "field.buyer_role.keywords", DEFAULT_BUYER_ROLE_TERMS,
        ),
        legal_entity_markers=_cfg_list(metadata_prompt, "legal_entity_markers", DEFAULT_LEGAL_ENTITY_MARKERS),
        entity_stop_phrases=_cfg_list(
            metadata_prompt, "entity_stop_phrases", list(DEFAULT_ENTITY_STOP_PHRASES),
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
        primary_type_keywords=_cfg_list(
            metadata_prompt, "field.primary_type.keywords", DEFAULT_PRIMARY_TYPE_KEYWORDS,
        ),
        sub_type_keywords=_cfg_list(
            metadata_prompt, "field.sub_type.keywords", DEFAULT_SUB_TYPE_KEYWORDS,
        ),
        title_keywords=_cfg_list(
            metadata_prompt, "field.title.keywords", DEFAULT_TITLE_KEYWORDS,
        ),
        effective_date_keywords=_cfg_list(
            metadata_prompt, "field.effective_date.keywords", DEFAULT_EFFECTIVE_DATE_KEYWORDS,
        ),
        term_duration_keywords=_cfg_list(
            metadata_prompt, "field.term_duration.keywords", DEFAULT_TERM_DURATION_KEYWORDS,
        ),
        renewal_keywords=_cfg_list(
            metadata_prompt, "field.renewal_provisions.keywords", DEFAULT_RENEWAL_KEYWORDS,
        ),
        estimated_value_keywords=_cfg_list(
            metadata_prompt, "field.estimated_value.keywords", DEFAULT_ESTIMATED_VALUE_KEYWORDS,
        ),
        payment_currency_keywords=_cfg_list(
            metadata_prompt, "field.payment_currency.keywords", DEFAULT_PAYMENT_CURRENCY_KEYWORDS,
        ),
        language_keywords=_cfg_list(
            metadata_prompt, "field.language.keywords", DEFAULT_LANGUAGE_KEYWORDS,
        ),
        expiration_date_keywords=_cfg_list(
            metadata_prompt, "field.expiration_date.keywords", DEFAULT_EXPIRATION_DATE_KEYWORDS,
        ),
        supplier_jurisdiction_field_keywords=_cfg_list(
            metadata_prompt, "field.supplier_jurisdiction.keywords", DEFAULT_SUPPLIER_JURISDICTION_KEYWORDS,
        ),
        buyer_jurisdiction_field_keywords=_cfg_list(
            metadata_prompt, "field.buyer_jurisdiction.keywords", DEFAULT_BUYER_JURISDICTION_KEYWORDS,
        ),
        service_delivery_keywords=_cfg_list(
            metadata_prompt, "field.service_delivery_locations.keywords", DEFAULT_SERVICE_DELIVERY_KEYWORDS,
        ),
        description_keywords=_cfg_list(
            metadata_prompt, "field.description.keywords", DEFAULT_DESCRIPTION_KEYWORDS,
        ),
        verbatim_scope_keywords=_cfg_list(
            metadata_prompt, "field.verbatim_scope.keywords", DEFAULT_VERBATIM_SCOPE_KEYWORDS,
        ),
        scope_ref_keywords=_cfg_list(
            metadata_prompt, "field.scope_section_reference.keywords", DEFAULT_SCOPE_REF_KEYWORDS,
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
    name = re.sub(r"\s*,?\s*(?:with\s+its|having\s+its|whose)\s+(?:registered|principal|head)\b.*$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s*,?\s*(?:P\.?O\.?\s*Box|PO\s*Box)\b.*$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s*,?\s*\d{1,5}\s+[A-Z][a-z]+\s+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Lane|Way|Place)\b.*$", "", name, flags=re.IGNORECASE)
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
    return "Supplier/Vendor"


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
    name_lower = name.lower()
    for p in parties:
        p_lower = p.name.lower()
        if p.role == role and (p_lower == name_lower or name_lower in p_lower or p_lower in name_lower):
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
    flat_intro = re.sub(r"\s+", " ", intro)

    supplier_terms_pattern = "|".join(re.escape(term) for term in config.supplier_role_terms)
    buyer_terms_pattern = "|".join(re.escape(term) for term in config.buyer_role_terms)

    labeled_patterns = [
        (
            rf"(?:{supplier_terms_pattern})\s*(?:name)?\s*[:\-]\s*([^\n;]{{3,200}})",
            "Supplier/Vendor",
        ),
        (
            rf"(?:{buyer_terms_pattern})\s*(?:name)?\s*[:\-]\s*([^\n;]{{3,200}})",
            "Buyer/Client",
        ),
    ]
    for pattern, role in labeled_patterns:
        for hit in re.finditer(pattern, intro, flags=re.IGNORECASE):
            _add_party(parties, hit.group(1), role, config, full_text=text)

    role_terms = config.buyer_role_terms + config.supplier_role_terms
    role_terms_pattern = "|".join(re.escape(term) for term in sorted(role_terms, key=len, reverse=True))
    hereinafter_pat = rf'([A-Z][A-Za-z0-9&.,\'\- ]{{2,200}}?)\s*\((?:hereinafter\s+(?:referred\s+to\s+as\s+)?)?(?:the\s+)?["\u201c\u201d\'\\]*({role_terms_pattern})["\u201c\u201d\'\\]*\)'
    for hit in re.finditer(hereinafter_pat, flat_intro, flags=re.IGNORECASE):
        raw = hit.group(1).strip()
        raw = re.sub(r"^.*?\b(?:between|by and between|by|and)\s+", "", raw, flags=re.IGNORECASE).strip()
        _add_party(parties, raw, _map_role(hit.group(2), config), config, full_text=text)

    if len(parties) >= 2:
        return parties[:4]
    all_role_terms = sorted(
        config.supplier_role_terms + config.buyer_role_terms,
        key=len, reverse=True,
    )
    role_alt = "|".join(re.escape(t) for t in all_role_terms)
    supplier_between_pattern = "|".join(re.escape(term) for term in config.supplier_role_terms)

    role_paren = r"(?:\s*\((?:the\s+)?[\"']?(?:" + role_alt + r")[\"']?\))?"
    between_pat = (
        r"between\s+"
        r"([A-Z][A-Za-z0-9&.,'\-\s]{2,200}?)"
        + role_paren +
        r"\s+and\s+"
        r"([A-Z][A-Za-z0-9&.,'\-\s]{2,200}?)"
        + role_paren +
        r"(?:\.|;|,|\s+(?:for|regarding|dated|effective|whereby|this|hereinafter)|\s*$)"
    )
    for between_match in re.finditer(between_pat, flat_intro, flags=re.IGNORECASE):
        first = between_match.group(1).strip()
        second = between_match.group(2).strip()
        full_first = flat_intro[between_match.start(1):between_match.end(0)]
        first_role = (
            "Supplier/Vendor"
            if re.search(rf"\b({supplier_between_pattern})\b", full_first, re.IGNORECASE)
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


def _extract_contract_classification(text: str, config: ParserRuntimeConfig | None = None) -> ContractClassification:
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


def _extract_contract_details(
    text: str, sections: List[Section], config: ParserRuntimeConfig | None = None,
) -> ContractDetails:
    eff_kw = config.effective_date_keywords if config else DEFAULT_EFFECTIVE_DATE_KEYWORDS
    eff_patterns = [rf"{re.escape(kw)}\s*[:\-]?\s*([A-Za-z0-9,\-\/ ]{{5,40}})" for kw in eff_kw[:4]]
    effective_date = _first_match(eff_patterns, text) if eff_patterns else NOT_FOUND

    exp_kw = config.expiration_date_keywords if config else DEFAULT_EXPIRATION_DATE_KEYWORDS
    exp_patterns = [rf"{re.escape(kw)}\s*[:\-]?\s*([A-Za-z0-9,\-\/ ]{{5,40}})" for kw in exp_kw[:4]]
    expiration_date = _first_match(exp_patterns, text) if exp_patterns else NOT_FOUND

    dur_kw = config.term_duration_keywords if config else DEFAULT_TERM_DURATION_KEYWORDS
    dur_patterns = [rf"{re.escape(kw)}\s*[:\-]?\s*([^.\n]{{5,80}})" for kw in dur_kw[:4]]
    term_duration = _first_match(dur_patterns, text) if dur_patterns else NOT_FOUND

    ren_kw = config.renewal_keywords if config else DEFAULT_RENEWAL_KEYWORDS
    renewal_clause = _match_clause(sections, ren_kw)[0]
    renewal_provisions = _summary_from_scope(renewal_clause)

    val_kw = config.estimated_value_keywords if config else DEFAULT_ESTIMATED_VALUE_KEYWORDS
    val_patterns = [rf"(?:{re.escape(kw)})\s*[:\-]?\s*([^\n.]{{3,80}})" for kw in val_kw[:4]]
    val_patterns.append(
        r"(USD|EUR|GBP|AED|SAR|QAR|KWD|OMR|BHD|INR|US\$|\$|€|£)\s?([0-9][0-9,\.]{2,})"
    )
    estimated_value = _first_match(val_patterns, text)

    pay_kw = config.payment_currency_keywords if config else DEFAULT_PAYMENT_CURRENCY_KEYWORDS
    payment_currency = _extract_currency(
        _match_clause(sections, pay_kw)[0]
    )
    if payment_currency == NOT_FOUND:
        payment_currency = _extract_currency(text)

    title_kw = config.title_keywords if config else DEFAULT_TITLE_KEYWORDS
    title = _extract_title(text)
    if title == NOT_FOUND:
        title_clause = _match_clause(sections, title_kw)[0]
        if title_clause != NOT_FOUND:
            title = title_clause[:180]

    return ContractDetails(
        title=title,
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

    for party in result.parties:
        party_section = "Buyer" if party.role == "Buyer/Client" else "Supplier"
        _add_conf_row(rows, party_section, "Name", party.name, _score_party_name(party.name, config))
        _add_conf_row(rows, party_section, "Role", party.role, 0.95)
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


_RATIONALE_MAP: Dict[str, Dict[str, str]] = {
    "Contract Classification": {
        "Primary Type": "Classified by keyword analysis of service, goods, fuel, SaaS, and advisory terms across the contract text.",
        "Sub Type": "Derived from secondary keyword patterns (consultancy, maintenance, licensing, supply) in contract body.",
    },
    "Buyer": {
        "Name": "Identified using legal entity markers (Ltd, LLC, Inc, etc.) and proximity to buyer/client role indicators.",
        "Role": "Assigned based on contextual role terms (buyer, client, purchaser, customer) near the party name.",
        "Registered Address": "Extracted from address patterns adjacent to the identified buyer entity name.",
        "Jurisdiction": "Inferred from the party's registered address or the governing law clause when not explicitly stated.",
    },
    "Supplier": {
        "Name": "Identified using legal entity markers (Ltd, LLC, Inc, etc.) and proximity to supplier/vendor role indicators.",
        "Role": "Assigned based on contextual role terms (supplier, vendor, provider, contractor) near the party name.",
        "Registered Address": "Extracted from address patterns adjacent to the identified supplier entity name.",
        "Jurisdiction": "Inferred from the party's registered address or the governing law clause when not explicitly stated.",
    },
    "Jurisdictions": {
        "Supplier Jurisdiction": "Derived from the supplier's registered address or inferred from the governing law clause.",
        "Buyer Jurisdiction": "Derived from the buyer's registered address or inferred from the governing law clause.",
        "Service Delivery Locations": "Identified by matching known country names within service delivery and place-of-supply clauses.",
    },
    "Contract Details": {
        "Title": "Extracted from the document heading, subject line, or first prominent text matching title patterns.",
        "Effective Date": "Matched using date patterns (DD/MM/YYYY, Month DD YYYY) near keywords like 'effective', 'dated', 'commencement'.",
        "Term Duration": "Extracted from clauses containing duration keywords (years, months, period, term).",
        "Renewal Provisions": "Matched from renewal/extension clause keywords and adjacent text.",
        "Estimated Value": "Extracted from monetary patterns (currency symbol + amount) near value/consideration/fee keywords.",
        "Payment Currency": "Identified from currency codes (USD, SAR, EUR) or currency names in payment clauses.",
        "Language": "Determined by character-set analysis of the contract text (Latin script = English, Arabic script = Arabic).",
        "Expiration Date": "Matched using date patterns near expiry/expiration/end-date keywords, or calculated from effective date + term.",
    },
    "Nature of Supply": {
        "Description": "Summarised from the scope-of-services clause or the first service description paragraph.",
        "Verbatim Scope": "Extracted as the full text of the scope-of-services or statement-of-work section.",
        "Scope Section Reference": "Taken from the section/clause number reference of the scope-of-services provision.",
    },
}

_CLAUSE_RATIONALE = "Detected by keyword matching ({keywords}) across contract sections. Clause text is extracted verbatim from the matching paragraph."


def _get_rationale(section: str, field: str) -> str:
    section_map = _RATIONALE_MAP.get(section)
    if section_map:
        rationale = section_map.get(field)
        if rationale:
            return rationale
    if ":" in field:
        code = field.split(":")[0].strip()
        for _group_name, items in CLAUSE_DEFINITIONS.items():
            for c_code, _title, keywords in items:
                if c_code == code:
                    return _CLAUSE_RATIONALE.format(keywords=", ".join(keywords[:3]))
    return "Extracted using pattern matching and keyword analysis from the contract text."


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

        rationale = _get_rationale(row.section, row.field) if value != NOT_FOUND else ""

        evidence_rows.append(
            EvidenceRow(
                section=row.section,
                field=row.field,
                value=value,
                snippet=snippet,
                highlight_terms=highlight_terms,
                rationale=rationale,
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
        parties = [
            Party(name=NOT_FOUND, role="Buyer/Client"),
            Party(name=NOT_FOUND, role="Supplier/Vendor"),
        ]

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

    svc_loc_kw = runtime_config.service_delivery_keywords
    svc_location_text = _match_clause(sections, svc_loc_kw)[0]
    if svc_location_text == NOT_FOUND:
        svc_location_text = clause_groups["Service-related clauses"][1].text
    locations = [
        c
        for c in COUNTRIES
        if re.search(rf"\b{re.escape(c)}\b", svc_location_text, flags=re.IGNORECASE)
    ]

    desc_kw = runtime_config.description_keywords
    scope_kw = runtime_config.verbatim_scope_keywords
    scope_clause = clause_groups["Service-related clauses"][0]
    desc_text = _match_clause(sections, desc_kw)[0]
    if desc_text == NOT_FOUND:
        desc_text = scope_clause.text
    verbatim_text = _match_clause(sections, scope_kw)[0]
    if verbatim_text == NOT_FOUND:
        verbatim_text = scope_clause.text
    nature = NatureOfSupply(
        description=_summary_from_scope(desc_text),
        verbatim_scope=verbatim_text,
        scope_section_reference=scope_clause.reference,
    )

    result = ExtractionResult(
        contract_classification=_extract_contract_classification(cleaned, runtime_config),
        parties=parties,
        jurisdictions=Jurisdictions(
            supplier_jurisdiction=supplier_jurisdiction,
            buyer_jurisdiction=buyer_jurisdiction,
            service_delivery_locations=locations,
        ),
        contract_details=_extract_contract_details(cleaned, sections, runtime_config),
        nature_of_supply=nature,
        clause_groups=clause_groups,
        ocr_used=ocr_used,
    )
    confidence_table, overall_confidence = _build_confidence_table(result, runtime_config)
    result.confidence_table = confidence_table
    result.evidence_table = _build_evidence_table(cleaned, confidence_table)
    result.overall_confidence = overall_confidence
    return result


def backfill_clauses_with_regex(
    result: ExtractionResult,
    text: str,
    metadata_prompt: str | None = None,
) -> ExtractionResult:
    """Fill NOT FOUND clauses in an LLM result using regex extraction."""
    cleaned = _clean_text(text)
    sections = _split_sections(cleaned)
    runtime_config = _build_runtime_config(metadata_prompt)
    regex_clauses = _extract_clause_groups(sections, runtime_config)

    filled: set[str] = set()

    for group_name, llm_clauses in result.clause_groups.items():
        regex_group = regex_clauses.get(group_name, [])
        regex_by_code = {c.code: c for c in regex_group}
        for clause in llm_clauses:
            if clause.text == NOT_FOUND:
                regex_match = regex_by_code.get(clause.code)
                if regex_match and regex_match.text != NOT_FOUND:
                    clause.text = regex_match.text
                    clause.reference = regex_match.reference
                    filled.add(f"{group_name}|||{clause.code}: {clause.title}")

    for group_name in regex_clauses:
        if group_name not in result.clause_groups:
            result.clause_groups[group_name] = regex_clauses[group_name]
            for c in regex_clauses[group_name]:
                filled.add(f"{group_name}|||{c.code}: {c.title}")

    if filled:
        _rebuild_clause_rows(result, cleaned, filled)

    return result


def _rebuild_clause_rows(
    result: ExtractionResult, text: str, filled_keys: set[str],
) -> None:
    """Update confidence + evidence rows for backfilled clauses."""
    conf_by_key = {f"{r.section}|||{r.field}": r for r in result.confidence_table}
    ev_by_key = {f"{r.section}|||{r.field}": r for r in result.evidence_table}

    for group_name, clauses in result.clause_groups.items():
        for clause in clauses:
            key = f"{group_name}|||{clause.code}: {clause.title}"
            if key not in filled_keys:
                continue
            score = 0.72
            if clause.text != NOT_FOUND:
                score = 0.72 + (0.08 if clause.reference != NOT_FOUND else 0.0)
                if len(clause.text) > 120:
                    score += 0.06
            level = "High" if score >= 0.75 else "Medium" if score >= 0.5 else "Low"
            if key in conf_by_key:
                row = conf_by_key[key]
                row.value = clause.text
                row.confidence_score = round(score, 2)
                row.confidence_level = level
            else:
                result.confidence_table.append(
                    ConfidenceRow(
                        section=group_name,
                        field=f"{clause.code}: {clause.title}",
                        value=clause.text,
                        confidence_score=round(score, 2),
                        confidence_level=level,
                    )
                )

            snippet = NOT_FOUND
            if clause.text != NOT_FOUND:
                low = text.lower()
                search = clause.text[:200].strip()
                idx = low.find(search.lower())
                if idx == -1:
                    for word in search.split():
                        if len(word) > 4:
                            idx = low.find(word.lower())
                            if idx != -1:
                                break
                if idx >= 0:
                    start = max(0, idx - 80)
                    end = min(len(text), idx + len(search) + 80)
                    snippet = text[start:end].strip()
            terms = clause.text.split()[:3] if clause.text != NOT_FOUND else []
            if key in ev_by_key:
                ev_row = ev_by_key[key]
                ev_row.value = clause.text
                ev_row.snippet = snippet
                ev_row.highlight_terms = terms
            else:
                result.evidence_table.append(
                    EvidenceRow(
                        section=group_name,
                        field=f"{clause.code}: {clause.title}",
                        value=clause.text,
                        snippet=snippet,
                        highlight_terms=terms,
                    )
                )

    total = len(result.confidence_table)
    if total:
        result.overall_confidence = round(
            sum(r.confidence_score for r in result.confidence_table) / total, 2,
        )
