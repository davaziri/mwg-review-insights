"""Browsing and searching a title's reviews, with the page filters and any current tags."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, null, select
from sqlalchemy.orm import Session

from app.analysis.aggregate import Filters, current_tag_join, review_filter_clauses
from app.analysis.codebooks import approved_codebook, themes_for
from app.api.common import filters_dep, resolve_app, serialize_reviews, title_or_404
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
