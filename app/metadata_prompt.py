from __future__ import annotations

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
METADATA_PROMPT_PATH = ROOT_DIR / "config" / "metadata.cfg"

DEFAULT_METADATA_PROMPT = """# Editable metadata extraction prompt
# You can modify this file without changing Python code.
#
# supplier_role_terms, buyer_role_terms, legal_entity_markers and entity_stop_phrases
# are consumed by the parser.

supplier_role_terms = supplier,vendor,seller,contractor,service provider,provider,licensor
buyer_role_terms = buyer,client,purchaser,licensee
legal_entity_markers = llc,l.l.c,ltd,limited,inc,corp,corporation,company,plc,llp,lp,pte,pvt,gmbh,pjsc,fzco,fze,ag,nv,bv
entity_stop_phrases = this agreement,agreement is made,collectively,effective date,hereinafter,witnesseth,shall

# Prompt text for metadata extraction policy:
# Extract contract metadata and clauses strictly from contract text.
# Supplier/Vendor and Buyer/Client must be legal entities (company names), not narrative phrases.
# If a value cannot be found, return NOT FOUND IN CONTRACT.
"""


def load_metadata_prompt() -> str:
    if METADATA_PROMPT_PATH.exists():
        return METADATA_PROMPT_PATH.read_text(encoding="utf-8")
    return DEFAULT_METADATA_PROMPT
