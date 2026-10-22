"""Language check and English translation of reviews.

Steam's `language` field is the reviewer's Steam language setting, not the language the review is
written in: an English review from someone whose Steam is set to Spanish arrives labeled Spanish.
The translation model reads each review with text, says which language it is actually written in
and, when that isn't English, translates it.

The result is stored on the review for its current version, so a review is checked once and again
only if its author edits it. Translations are machine-written and always labeled that way; they
are never used as quotes.
"""

from collections.abc import Sequence
from html import escape

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis import prompts
from app.analysis.llm import LLMRequest, LLMResult
from app.analysis.text_rules import strip_em_dashes
from app.models import Review

# Steam's own language codes, so a checked language reads like the rest of the app's, plus
# "other" (a language Steam doesn't list) and "none" (no language to speak of, like "10/10").
STEAM_LANGUAGES = (
    "english", "schinese", "tchinese", "japanese", "koreana", "russian", "spanish", "latam", "brazilian",
    "portuguese", "german", "french", "italian", "polish", "turkish", "ukrainian", "czech", "dutch",
    "swedish", "danish", "norwegian", "finnish", "hungarian", "thai", "vietnamese", "indonesian",
    "romanian", "greek", "bulgarian", "arabic",
)  # fmt: skip
LANGUAGE_CODES = (*STEAM_LANGUAGES, "other", "none")

# Varieties the text alone often can't tell apart. When the Steam setting is in the same family
# it is kept, so a Mexican player's Spanish stays "Spanish (Latin America)".
_FAMILY = {"spanish": "es", "latam": "es", "portuguese": "pt", "brazilian": "pt", "schinese": "zh", "tchinese": "zh"}

MAX_REVIEWS_PER_REQUEST = 25
MAX_CHARS_PER_REQUEST = 12_000
MAX_OUTPUT_TOKENS = 16_000


def resolve_language(detected: str, steam: str | None) -> str | None:
    """The language to store for the model's answer, or None for text in no particular language."""
    if detected == "none":
        return None
    family = _FAMILY.get(detected)
    if family and steam and _FAMILY.get(steam) == family:
        return steam
    return detected


def _unchecked():
    return func.coalesce(Review.language_checked_for, -1) != func.coalesce(Review.timestamp_updated, 0)


def unchecked_clauses(title_id: int, app_id: int) -> list:
    return [
        Review.title_id == title_id,
        Review.app_id == app_id,
        Review.deleted_at.is_(None),
        func.coalesce(Review.display_text, "") != "",
        _unchecked(),
    ]


def unchecked_reviews(session: Session, title_id: int, app_id: int) -> list[Review]:
    """Reviews with text whose current version hasn't had its language checked."""
    return list(session.scalars(select(Review).where(*unchecked_clauses(title_id, app_id)).order_by(Review.id)))


def still_unchecked(session: Session, review_ids: Sequence[int]) -> list[Review]:
    out: list[Review] = []
    for i in range(0, len(review_ids), 900):
        out.extend(session.scalars(select(Review).where(Review.id.in_(review_ids[i : i + 900]), _unchecked())))
    return sorted(out, key=lambda r: r.id)


def counts(session: Session, review_ids: Sequence[int]) -> dict:
    """How many of these reviews are checked now, and how many of those got a translation."""
    checked = translated = 0
    for i in range(0, len(review_ids), 900):
        rows = session.execute(
            select(func.count(), func.count(Review.text_en)).where(Review.id.in_(review_ids[i : i + 900]), ~_unchecked())
        ).one()
        checked += rows[0]
        translated += rows[1]
    return {"planned": len(review_ids), "checked": checked, "translated": translated}


def groups(reviews: Sequence[Review]) -> list[list[Review]]:
    """Split reviews into requests by count and length, so one request's translations fit."""
    out: list[list[Review]] = []
    current: list[Review] = []
    size = 0
    for review in reviews:
        n = len(review.display_text or "")
        if current and (len(current) >= MAX_REVIEWS_PER_REQUEST or size + n > MAX_CHARS_PER_REQUEST):
            out.append(current)
            current, size = [], 0
        current.append(review)
        size += n
    if current:
        out.append(current)
    return out


def _block(review: Review) -> str:
    text = (review.display_text or "").replace("</review>", "</ review>")
    return f'<review id="{review.recommendation_id}" steam_language="{escape(review.language or "unknown")}">\n{text}\n</review>'


def translation_request(reviews: Sequence[Review], *, model: str, effort: str | None = None) -> LLMRequest:
    return LLMRequest(
        model=model,
        system=prompts.text("translation_system"),
        user="Check the language of each of these reviews and translate the ones not in English.\n\n<reviews>\n"
        + "\n".join(_block(r) for r in reviews)
        + "\n</reviews>",
        schema=prompts.translation_schema(list(LANGUAGE_CODES)),
        max_tokens=MAX_OUTPUT_TOKENS,
        effort=effort,
    )


def _cjk(ch: str) -> bool:
    cp = ord(ch)
    return 0x3040 <= cp <= 0x30FF or 0x3400 <= cp <= 0x9FFF or 0xAC00 <= cp <= 0xD7AF or 0xF900 <= cp <= 0xFAFF


def estimated_output_tokens(review: Review) -> int:
    """A rough guess for the estimate: a short answer for English reviews, and for others a
    translation about as long as the text (a Chinese, Japanese or Korean character is about a
    token of English, other text about four characters a token)."""
    if (review.language or "") == "english":
        return 25
    text = review.display_text or ""
    cjk = sum(1 for ch in text if _cjk(ch))
    return 25 + round((cjk + (len(text) - cjk) / 4) * 1.2)


def ingest(session: Session, reviews: Sequence[Review], result: LLMResult, model: str) -> list[Review]:
    """Store the language and translation for each review answered. Returns the reviews still
    unchecked: left out of the answer, or not in English but with no translation."""
    entries = {}
    if result.ok:
        entries = {str(e.get("review_id")): e for e in result.data.get("reviews", []) if isinstance(e, dict)}
    failed: list[Review] = []
    for review in reviews:
        entry = entries.get(review.recommendation_id)
        detected = entry.get("language") if entry else None
        if detected not in LANGUAGE_CODES:
            failed.append(review)
            continue
        language = resolve_language(detected, review.language)
        english = strip_em_dashes((entry.get("english") or "").strip())
        if language not in (None, "english") and not english:
            failed.append(review)
            continue
        review.text_language = language
        review.text_en = english if language not in (None, "english") else None
        review.language_checked_for = review.timestamp_updated or 0
        review.translation_model = result.model or model
    session.flush()
    return failed
