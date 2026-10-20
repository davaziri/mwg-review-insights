"""Review preparation: readable text, the "no content" rule, and playtime bands.

Runs on every stored or edited review (from sync) and as a backfill before analysis.
"""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Review

# Steam review markup. Tags are removed and their inner text kept; list items become "- " lines.
_LIST_ITEM = re.compile(r"\[\*\]")
_BBCODE = re.compile(
    r"\[/?(?:b|i|u|s|strike|h1|h2|h3|spoiler|noparse|code|quote|url|list|olist|table|tr|th|td|img|hr)"
    r"(?:=[^\]]*)?\]",
    re.IGNORECASE,
)
_MANY_NEWLINES = re.compile(r"\n{3,}")


def clean_review_text(text: str) -> str:
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    t = _LIST_ITEM.sub("\n- ", t)
    t = _BBCODE.sub("", t)
    t = _MANY_NEWLINES.sub("\n\n", t)
    return t.strip()


def _is_cjk(ch: str) -> bool:
    cp = ord(ch)
    return (
        0x3040 <= cp <= 0x30FF  # Japanese kana
        or 0x3400 <= cp <= 0x4DBF
        or 0x4E00 <= cp <= 0x9FFF  # CJK ideographs
        or 0xAC00 <= cp <= 0xD7AF  # Hangul
        or 0xF900 <= cp <= 0xFAFF
    )


# A review needs at least this much text to be worth tagging. Letters and digits count 1 each;
# a Chinese, Japanese or Korean character counts 3, since one carries about a word.
# So "good", "10/10" and emoji-only reviews are no content; "great game" and "很好玩" are content.
MIN_CONTENT_WEIGHT = 8


def content_status(display_text: str) -> str:
    weight = sum((3 if _is_cjk(ch) else 1) for ch in display_text if ch.isalnum())
    return "ok" if weight >= MIN_CONTENT_WEIGHT else "no_content"


PLAYTIME_BANDS = ("lt2h", "2to10h", "10to50h", "50h_plus", "unknown")
PLAYTIME_BAND_LABELS = {
    "lt2h": "Under 2h",
    "2to10h": "2 to 10h",
    "10to50h": "10 to 50h",
    "50h_plus": "50h+",
    "unknown": "Unknown",
}


def playtime_band(minutes_at_review: int | None, minutes_forever: int | None = None) -> str:
    """Band by playtime when the review was written (falls back to total playtime)."""
    minutes = minutes_at_review if minutes_at_review is not None else minutes_forever
    if minutes is None:
        return "unknown"
    if minutes < 120:
        return "lt2h"
    if minutes < 600:
        return "2to10h"
    if minutes < 3000:
        return "10to50h"
    return "50h_plus"


def prepare_review(review: Review) -> None:
    review.display_text = clean_review_text(review.review_text)
    review.content_status = content_status(review.display_text)
    review.playtime_band = playtime_band(review.author_playtime_at_review, review.author_playtime_forever)


def prepare_missing(session: Session, title_id: int) -> int:
    """Fill derived fields for reviews stored before preparation existed. Returns how many."""
    reviews = session.scalars(
        select(Review).where(Review.title_id == title_id, Review.display_text.is_(None))
    ).all()
    for review in reviews:
        prepare_review(review)
    session.commit()
    return len(reviews)
