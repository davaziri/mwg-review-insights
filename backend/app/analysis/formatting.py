"""How reviews and codebooks are written into prompts."""

from collections.abc import Sequence
from html import escape

from app.models import Review, Theme


def review_block(review: Review, *, max_chars: int | None = None, details: bool = True) -> str:
    text = review.display_text or ""
    if max_chars and len(text) > max_chars:
        text = text[:max_chars].rstrip() + " [review continues]"
    # Keep a review from closing its own tag; the quote check runs against the stored text anyway.
    text = text.replace("</review>", "</ review>")
    attrs = [f'id="{review.recommendation_id}"', f'vote="{"recommended" if review.voted_up else "not recommended"}"']
    if details:
        minutes = review.author_playtime_at_review
        if minutes is not None:
            attrs.append(f'playtime_hours="{minutes / 60:.1f}"')
        attrs.append(f'written_during_early_access="{"yes" if review.written_during_early_access else "no"}"')
    attrs.append(f'language="{escape(review.language or "unknown")}"')
    return f"<review {' '.join(attrs)}>\n{text}\n</review>"


def reviews_block(reviews: Sequence[Review], **kwargs) -> str:
    return "\n".join(review_block(r, **kwargs) for r in reviews)


def codebook_block(themes: Sequence[Theme]) -> str:
    parts = []
    for t in sorted(themes, key=lambda t: (t.sort_order, t.id or 0)):
        lines = [f"### {t.key}: {t.name}", f"Definition: {t.definition}"]
        if t.include_notes:
            lines.append(f"Include: {t.include_notes}")
        if t.exclude_notes:
            lines.append(f"Exclude: {t.exclude_notes}")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)
