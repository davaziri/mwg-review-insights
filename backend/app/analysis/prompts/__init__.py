"""Prompt files and the JSON schemas the models must answer in.

Bump PROMPT_VERSION whenever a prompt or schema changes; it is recorded on every run.
"""

from functools import cache
from pathlib import Path
from string import Template

PROMPT_VERSION = "2026-10-20.3"
_DIR = Path(__file__).parent


@cache
def _load(name: str) -> str:
    return (_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


def render(name: str, **values: object) -> str:
    return Template(_load(name)).substitute(**{k: str(v) for k, v in values.items()})


def text(name: str) -> str:
    return _load(name)


def _obj(properties: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": required if required is not None else list(properties),
        "properties": properties,
    }


_STR = {"type": "string"}
SENTIMENT = {"type": "string", "enum": ["positive", "negative", "mixed"]}

DISCOVERY_SCHEMA = _obj(
    {
        "themes": {
            "type": "array",
            "items": _obj(
                {
                    "key": _STR,
                    "name": _STR,
                    "definition": _STR,
                    "include": _STR,
                    "exclude": _STR,
                    "example_review_ids": {"type": "array", "items": _STR},
                }
            ),
        }
    }
)


def tagging_schema(theme_keys: list[str]) -> dict:
    """The tagging answer for a group of reviews. theme_id is limited to the codebook's keys."""
    mention = _obj({"theme_id": {"type": "string", "enum": sorted(theme_keys)}, "sentiment": SENTIMENT, "quote": _STR})
    overall = _obj({"sentiment": {"type": "string", "enum": ["positive", "negative", "mixed", "none"]}, "quote": _STR})
    review = _obj(
        {
            "review_id": _STR,
            "mentions": {"type": "array", "items": mention},
            "overall": overall,
            "other_flag": {"type": "boolean"},
            "other_note": _STR,
            "gist_en": _STR,
        }
    )
    return _obj({"reviews": {"type": "array", "items": review}})


def summary_schema(theme_keys: list[str]) -> dict:
    point = _obj(
        {
            "theme_key": {"type": "string", "enum": sorted(theme_keys)},
            "headline": _STR,
            "detail": _STR,
            "review_ids": {"type": "array", "items": _STR},
        }
    )
    return _obj(
        {
            "strengths": {"type": "array", "items": point},
            "problems": {"type": "array", "items": point},
            "last_30_days": _obj({"text": _STR, "review_ids": {"type": "array", "items": _STR}}),
        }
    )
