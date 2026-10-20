"""House style for everything the app generates: no em dashes.

Applied to model output (theme names, definitions, summaries, gists, notes) before it is stored.
Verbatim review quotes are never passed through this; they are the reviewer's own words.
"""

import re
from typing import Any

EM_DASH = "\u2014"
_EM_DASH_RUN = re.compile("\\s*\u2014+\\s*")


def strip_em_dashes(text: str) -> str:
    if EM_DASH not in text:
        return text
    cleaned = _EM_DASH_RUN.sub(", ", text)
    return cleaned.strip(" ,")


def clean_generated(value: Any) -> Any:
    """Apply strip_em_dashes to every string inside a JSON-like value."""
    if isinstance(value, str):
        return strip_em_dashes(value)
    if isinstance(value, list):
        return [clean_generated(v) for v in value]
    if isinstance(value, dict):
        return {k: clean_generated(v) for k, v in value.items()}
    return value
