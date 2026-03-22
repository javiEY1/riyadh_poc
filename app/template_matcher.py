from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from typing import List

from app.models import NOT_FOUND


def _normalise(value: str) -> str:
    if not value or value == NOT_FOUND:
        return ""
    return re.sub(r"\s+", " ", value.strip().lower())


def _field_similarity(a: str, b: str) -> float:
    na, nb = _normalise(a), _normalise(b)
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def _extract_flat_values(result: dict) -> dict[str, str]:
    flat: dict[str, str] = {}

    cc = result.get("contract_classification", {})
    flat["primary_type"] = str(cc.get("primary_type", ""))
    flat["sub_type"] = str(cc.get("sub_type", ""))

    details = result.get("contract_details", {})
    for key in ("title", "effective_date", "term_duration", "renewal_provisions",
                "estimated_value", "payment_currency", "language", "expiration_date"):
        flat[key] = str(details.get(key, ""))

    jur = result.get("jurisdictions", {})
    flat["supplier_jurisdiction"] = str(jur.get("supplier_jurisdiction", ""))
    flat["buyer_jurisdiction"] = str(jur.get("buyer_jurisdiction", ""))
    locs = jur.get("service_delivery_locations", [])
    flat["service_delivery_locations"] = ", ".join(locs) if isinstance(locs, list) else str(locs)

    nature = result.get("nature_of_supply", {})
    flat["description"] = str(nature.get("description", ""))

    for party in result.get("parties", []):
        role = party.get("role", "Supplier/Vendor")
        prefix = "buyer" if role == "Buyer/Client" else "supplier"
        flat[f"{prefix}_name"] = str(party.get("name", ""))
        flat[f"{prefix}_jurisdiction"] = str(party.get("jurisdiction", ""))

    for group_name, clauses in result.get("clause_groups", {}).items():
        for clause in clauses:
            code = clause.get("code", "")
            text = clause.get("text", NOT_FOUND)
            if text and text != NOT_FOUND:
                flat[f"clause_{code}"] = "present"
            else:
                flat[f"clause_{code}"] = ""

    return flat


def _extract_clause_texts(result: dict) -> dict[str, str]:
    texts: dict[str, str] = {}
    for clauses in result.get("clause_groups", {}).values():
        for clause in clauses:
            code = clause.get("code", "")
            text = clause.get("text", NOT_FOUND)
            if code:
                texts[f"clause_{code}"] = text if text and text != NOT_FOUND else ""
    return texts


def _build_evidence_index(result: dict) -> dict[str, dict]:
    idx: dict[str, dict] = {}
    for ev in result.get("evidence_table", []):
        key = f"{ev.get('section', '')}|||{ev.get('field', '')}"
        idx[key] = {
            "snippet": ev.get("snippet", ""),
            "highlight_terms": ev.get("highlight_terms", []),
            "rationale": ev.get("rationale", ""),
        }
    return idx


def _find_evidence(evidence_idx: dict, section: str, field: str) -> dict:
    ev = evidence_idx.get(f"{section}|||{field}")
    if ev:
        has_snippet = ev.get("snippet") and ev["snippet"] != NOT_FOUND
        has_rationale = bool(ev.get("rationale"))
        if has_snippet or has_rationale:
            return ev
    return {"snippet": "", "highlight_terms": [], "rationale": ""}


def compute_similarity(contract_result: dict, template_result: dict) -> float:
    contract_vals = _extract_flat_values(contract_result)
    template_vals = _extract_flat_values(template_result)

    all_keys = set(contract_vals.keys()) | set(template_vals.keys())
    if not all_keys:
        return 0.0

    total = 0.0
    for key in all_keys:
        a = contract_vals.get(key, "")
        b = template_vals.get(key, "")
        total += _field_similarity(a, b)

    return round(total / len(all_keys), 4)


FIELD_LABELS: dict[str, str] = {
    "primary_type": "Primary Type",
    "sub_type": "Sub Type",
    "title": "Title",
    "effective_date": "Effective Date",
    "term_duration": "Term / Duration",
    "renewal_provisions": "Renewal Provisions",
    "estimated_value": "Estimated Value",
    "payment_currency": "Payment Currency",
    "language": "Language",
    "expiration_date": "Expiration Date",
    "supplier_jurisdiction": "Supplier Jurisdiction",
    "buyer_jurisdiction": "Buyer Jurisdiction",
    "service_delivery_locations": "Service Delivery Locations",
    "description": "Nature of Supply",
    "buyer_name": "Buyer Name",
    "supplier_name": "Supplier Name",
}

SECTION_MAP: dict[str, str] = {
    "primary_type": "Contract Classification",
    "sub_type": "Contract Classification",
    "title": "Contract Details",
    "effective_date": "Contract Details",
    "term_duration": "Contract Details",
    "renewal_provisions": "Contract Details",
    "estimated_value": "Contract Details",
    "payment_currency": "Contract Details",
    "language": "Contract Details",
    "expiration_date": "Contract Details",
    "supplier_jurisdiction": "Jurisdictions",
    "buyer_jurisdiction": "Jurisdictions",
    "service_delivery_locations": "Jurisdictions",
    "description": "Nature of Supply",
    "buyer_name": "Buyer",
    "supplier_name": "Supplier",
}


def compare_detailed(
    contract_result: dict,
    template_result: dict,
) -> dict:
    c_vals = _extract_flat_values(contract_result)
    t_vals = _extract_flat_values(template_result)
    c_clause_texts = _extract_clause_texts(contract_result)
    t_clause_texts = _extract_clause_texts(template_result)
    c_evidence = _build_evidence_index(contract_result)
    t_evidence = _build_evidence_index(template_result)
    all_keys = sorted(set(c_vals.keys()) | set(t_vals.keys()))

    rows: list[dict] = []
    total_sim = 0.0
    for key in all_keys:
        c_val = c_vals.get(key, "")
        t_val = t_vals.get(key, "")
        sim = _field_similarity(c_val, t_val)
        total_sim += sim

        c_display = c_val if c_val else NOT_FOUND
        t_display = t_val if t_val else NOT_FOUND

        if key.startswith("clause_"):
            label = key.replace("clause_", "").upper()
            section = "Clauses"
            c_text = c_clause_texts.get(key, "")
            t_text = t_clause_texts.get(key, "")
        else:
            label = FIELD_LABELS.get(key, key.replace("_", " ").title())
            section = SECTION_MAP.get(key, "Contract Details")

        status = "match" if sim == 1.0 else "differ" if sim > 0 else "missing"
        if not c_val and not t_val:
            status = "both_empty"

        row: dict = {
            "section": section,
            "field": label,
            "contract_value": c_display,
            "template_value": t_display,
            "similarity": round(sim, 4),
            "status": status,
        }

        if key.startswith("clause_"):
            if c_text:
                row["contract_clause_text"] = c_text
            if t_text:
                row["template_clause_text"] = t_text

        c_ev = _find_evidence(c_evidence, section, label)
        t_ev = _find_evidence(t_evidence, section, label)
        if c_ev["snippet"]:
            row["contract_snippet"] = c_ev["snippet"]
            row["contract_highlight"] = c_ev["highlight_terms"]
        if c_ev.get("rationale"):
            row["contract_rationale"] = c_ev["rationale"]
        if t_ev["snippet"]:
            row["template_snippet"] = t_ev["snippet"]
            row["template_highlight"] = t_ev["highlight_terms"]
        if t_ev.get("rationale"):
            row["template_rationale"] = t_ev["rationale"]

        rows.append(row)

    overall = round(total_sim / len(all_keys), 4) if all_keys else 0.0
    return {"overall_similarity": overall, "fields": rows}


def rank_templates(
    contract_result: dict,
    templates: List[dict],
) -> List[dict]:
    ranked = []
    for tpl in templates:
        tpl_result = tpl.get("result", {})
        if isinstance(tpl_result, str):
            tpl_result = json.loads(tpl_result)
        score = compute_similarity(contract_result, tpl_result)
        ranked.append({
            "template_id": tpl.get("id"),
            "template_name": tpl.get("name", tpl.get("filename", "")),
            "similarity": score,
        })
    ranked.sort(key=lambda x: x["similarity"], reverse=True)
    return ranked
