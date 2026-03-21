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
        role = party.get("role", "Other")
        prefix = "buyer" if role == "Buyer/Client" else "supplier" if role == "Supplier/Vendor" else "other"
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
