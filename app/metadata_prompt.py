from __future__ import annotations

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
METADATA_PROMPT_PATH = ROOT_DIR / "config" / "metadata.cfg"


def load_metadata_prompt() -> str:
    if METADATA_PROMPT_PATH.exists():
        return METADATA_PROMPT_PATH.read_text(encoding="utf-8")
    return ""
