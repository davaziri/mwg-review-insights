"""Browsing and searching a title's reviews, with the page filters and any current tags."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, null, select
from sqlalchemy.orm import Session

from app.analysis.aggregate import Filters, current_tag_join, review_filter_clauses
from app.analysis.codebooks import approved_codebook, themes_for
from app.analysis.prep import PLAYTIME_BAND_LABELS, PLAYTIME_BANDS
from app.api.common import date_str, filters_dep, resolve_app, serialize_reviews, title_or_404
from app.db import get_session
from app.models import Review, ReviewTag, ThemeMention
from app.search import match_spans, parse_terms, search_clauses

router = APIRouter(prefix="/api", tags=["reviews"])

SORTS = {
    "newest": (Review.timestamp_created.desc(),),
    "oldest": (Review.timestamp_created.asc(),),
    "helpful": (Review.votes_up.desc(), Review.weighted_vote_score.desc()),
    "playtime": (Review.author_playtime_at_review.desc(),),
}


@router.get("/titles/{title_id}/reviews")
def list_reviews(
    title_id: int,
    f: Filters = Depends(filters_dep),
    q: str | None = Query(None, max_length=200),
    theme: str | None = None,
    sentiment: Literal["positive", "negative", "mixed"] | None = None,
    overall: Literal["positive", "negative", "mixed", "none"] | None = None,
    content: Literal["all", "ok", "no_content"] = "all",
    sort: Literal["newest", "oldest", "helpful", "playtime"] = "newest",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_session),
):
    """Every stored review that passes the filters, tagged or not. q searches the review text;
    theme, sentiment and overall narrow to analyzed reviews."""
    title = title_or_404(session, title_id)
    f.app_id = resolve_app(title, f.app_id)
    cb = approved_codebook(session, title.id)
    themes = {t.id: t for t in themes_for(session, cb.id)} if cb else {}
    terms = parse_terms(q or "")

    if cb:
        query = select(Review.id, ReviewTag.id).outerjoin(ReviewTag, current_tag_join(cb.id))
    else:
        query = select(Review.id, null())
    query = query.where(*review_filter_clauses(title.id, f), *search_clauses(session, terms))
    if content != "all":
        query = query.where(Review.content_status == content)
    if theme or overall:
        if cb is None:
            return {"total": 0, "page": page, "page_size": page_size, "reviews": [], "codebook": None}
        query = query.where(ReviewTag.id.is_not(None))
    if theme:
        theme_obj = next((t for t in themes.values() if t.key == theme), None)
        if theme_obj is None:
            raise HTTPException(400, f"Unknown theme '{theme}'")
        mention = select(ThemeMention.review_tag_id).where(ThemeMention.theme_id == theme_obj.id)
        if sentiment:
            mention = mention.where(ThemeMention.sentiment == sentiment)
        query = query.where(ReviewTag.id.in_(mention))
    if overall:
        query = query.where(func.coalesce(ReviewTag.overall_sentiment, "none") == overall)

    total = session.scalar(select(func.count()).select_from(query.subquery()))
    pairs = session.execute(
        query.order_by(*SORTS[sort], Review.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    out = serialize_reviews(session, [(p[0], p[1]) for p in pairs], themes)
    if terms:
        for r in out:
            r["matches"] = match_spans(r["text"], terms)
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "terms": terms,
        "reviews": out,
        "codebook": {"id": cb.id, "version": cb.version} if cb else None,
    }


@router.get("/titles/{title_id}/facets")
def facets(title_id: int, app_id: int | None = None, session: Session = Depends(get_session)):
    """What the filter bar can offer for one app: its languages, date range and playtime bands,
    with review counts (unfiltered)."""
    title = title_or_404(session, title_id)
    app = resolve_app(title, app_id)
    scope = [Review.title_id == title.id, Review.app_id == app, Review.deleted_at.is_(None)]
    total, first, last, early, deck, dev = session.execute(
        select(
            func.count(),
            func.min(Review.timestamp_created),
            func.max(Review.timestamp_created),
            func.sum(case((Review.written_during_early_access.is_(True), 1), else_=0)),
            func.sum(case((Review.primarily_steam_deck.is_(True), 1), else_=0)),
            func.sum(case((Review.developer_response.is_not(None), 1), else_=0)),
        ).where(*scope)
    ).one()
    languages = session.execute(
        select(Review.effective_language, func.count())
        .where(*scope)
        .group_by(Review.effective_language)
        .order_by(func.count().desc())
    ).all()
    bands = dict(session.execute(select(Review.playtime_band, func.count()).where(*scope).group_by(Review.playtime_band)).all())
    return {
        "app_id": app,
        "total": total,
        "date_min": date_str(first),
        "date_max": date_str(last),
        "languages": [{"code": code or "unknown", "count": n} for code, n in languages],
        "playtime_bands": [{"band": b, "label": PLAYTIME_BAND_LABELS[b], "count": bands.get(b, 0)} for b in PLAYTIME_BANDS],
        "early_access": early or 0,
        "steam_deck": deck or 0,
        "developer_response": dev or 0,
    }
