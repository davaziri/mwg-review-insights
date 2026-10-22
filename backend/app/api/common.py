"""Helpers shared by the title-scoped API modules: lookups, page filters and review output."""

from datetime import UTC, date, datetime
from typing import Literal

from fastapi import HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.aggregate import Filters
from app.models import Review, ReviewTag, Theme, ThemeMention, Title


def title_or_404(session: Session, title_id: int) -> Title:
    title = session.get(Title, title_id)
    if title is None:
        raise HTTPException(404, "Title not found")
    return title


def resolve_app(title: Title, app_id: int | None) -> int:
    """The Steam app a request is about: the title's main app unless its demo is asked for."""
    if app_id is None:
        return title.steam_app_id
    if app_id not in title.app_ids:
        raise HTTPException(400, f"App {app_id} does not belong to {title.name}")
    return app_id


def review_url(review: Review) -> str:
    return f"https://steamcommunity.com/profiles/{review.author_steamid}/recommended/{review.app_id}/"


def date_str(ts: int | None) -> str | None:
    return datetime.fromtimestamp(ts, UTC).date().isoformat() if ts else None


def filters_dep(
    app_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    vote: Literal["positive", "negative"] | None = None,
    playtime: list[str] = Query(default=[]),
    language: list[str] = Query(default=[]),
    early_access: bool | None = None,
    steam_deck: bool | None = None,
    has_dev_response: bool | None = None,
) -> Filters:
    """The page filters every title view shares, as query parameters."""
    return Filters(
        app_id=app_id,
        date_from=date_from,
        date_to=date_to,
        voted_up=None if vote is None else vote == "positive",
        playtime_bands=playtime,
        languages=language,
        early_access=early_access,
        steam_deck=steam_deck,
        has_dev_response=has_dev_response,
    )


def review_brief(review: Review, max_chars: int = 400) -> dict:
    text = review.display_text or ""
    return {
        "recommendation_id": review.recommendation_id,
        "excerpt": text if len(text) <= max_chars else text[:max_chars].rstrip() + "...",
        "voted_up": review.voted_up,
        "language": review.effective_language,
        "date": date_str(review.timestamp_created),
        "url": review_url(review),
    }


def serialize_reviews(
    session: Session, pairs: list[tuple[int, int | None]], themes: dict[int, Theme]
) -> list[dict]:
    """Reviews with their current tag (if any), in the order given.

    pairs: (review id, current tag id or None). Quote offsets index into "text".
    """
    reviews = {r.id: r for r in session.scalars(select(Review).where(Review.id.in_([p[0] for p in pairs] or [-1])))}
    tag_ids = [p[1] for p in pairs if p[1] is not None]
    tags = {t.id: t for t in session.scalars(select(ReviewTag).where(ReviewTag.id.in_(tag_ids or [-1])))}
    mentions: dict[int, list[ThemeMention]] = {}
    for m in session.scalars(select(ThemeMention).where(ThemeMention.review_tag_id.in_(list(tags) or [-1]))):
        mentions.setdefault(m.review_tag_id, []).append(m)

    out = []
    for review_id, tag_id in pairs:
        r = reviews[review_id]
        tag = tags.get(tag_id) if tag_id is not None else None
        out.append(
            {
                "id": r.id,
                "recommendation_id": r.recommendation_id,
                "app_id": r.app_id,
                "text": r.display_text or "",
                "content_status": r.content_status,
                "voted_up": r.voted_up,
                # The language the text is written in once checked, else the Steam setting.
                "language": r.effective_language,
                "steam_language": r.language,
                "language_checked": r.language_checked_for is not None and r.language_checked_for == (r.timestamp_updated or 0),
                "text_en": r.text_en,
                "date": date_str(r.timestamp_created),
                "playtime_at_review_hours": round(r.author_playtime_at_review / 60, 1)
                if r.author_playtime_at_review is not None
                else None,
                "playtime_band": r.playtime_band,
                "early_access": r.written_during_early_access,
                "steam_deck": r.primarily_steam_deck,
                "votes_up": r.votes_up,
                "developer_response": r.developer_response,
                "url": review_url(r),
                "tagged": tag is not None,
                "gist_en": tag.gist_en if tag else None,
                "other_flag": tag.other_flag if tag else False,
                "other_note": tag.other_note if tag else None,
                "model": tag.model if tag else None,
                "overall": {
                    "sentiment": tag.overall_sentiment or "none",
                    "quote_start": tag.overall_quote_start,
                    "quote_end": tag.overall_quote_end,
                    "quote_status": tag.overall_quote_status or "none",
                }
                if tag
                else None,
                "mentions": [
                    {
                        "theme_key": themes[m.theme_id].key,
                        "theme_name": themes[m.theme_id].name,
                        "sentiment": m.sentiment,
                        "quote_start": m.quote_start,
                        "quote_end": m.quote_end,
                        "quote_status": m.quote_status,
                    }
                    for m in sorted(mentions.get(tag.id, []), key=lambda m: (m.quote_start is None, m.quote_start or 0))
                    if m.theme_id in themes
                ]
                if tag
                else [],
            }
        )
    return out
