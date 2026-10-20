"""The portfolio overview across titles, and the compare view for 2 to 4 titles."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.aggregate import Filters, theme_stats
from app.analysis.codebooks import approved_codebook, themes_for
from app.analysis.llm import LLMClient
from app.analysis.theme_match import MAX_TITLES, ThemeMatchError, sides_for, stored_match
from app.analysis.theme_match import estimate as estimate_match
from app.analysis.theme_match import run as run_match
from app.api.analysis import get_llm
from app.auth import actor
from app.config import get_settings
from app.db import get_session
from app.models import ThemeMatch, Title
from app.portfolio import share, snapshot, theme_highlights, title_card, trend
from app.timeutil import utcnow

router = APIRouter(prefix="/api", tags=["portfolio"])


@router.get("/portfolio")
def portfolio(session: Session = Depends(get_session)):
    now = utcnow()
    titles = session.scalars(select(Title).where(Title.archived_at.is_(None)).order_by(Title.id))
    return {"generated_at": now, "titles": [title_card(session, t, now) for t in titles]}


# Compare


def _compare_titles(session: Session, title_ids: list[int]) -> list[Title]:
    ids = list(dict.fromkeys(title_ids))
    if not 2 <= len(ids) <= MAX_TITLES:
        raise HTTPException(400, f"Pick 2 to {MAX_TITLES} titles to compare.")
    titles = {t.id: t for t in session.scalars(select(Title).where(Title.id.in_(ids)))}
    missing = [i for i in ids if i not in titles]
    if missing:
        raise HTTPException(404, f"Title {missing[0]} not found")
    return [titles[i] for i in ids]


def _analyzed_sides(session: Session, titles: list[Title]):
    """Titles that have an approved codebook and at least one analyzed review, with their themes."""
    out = []
    for t in titles:
        top = theme_highlights(session, t, t.steam_app_id)
        if top and top["analyzed"]:
            cb = approved_codebook(session, t.id)
            out.append((t, cb, themes_for(session, cb.id)))
    return sides_for(out)


def _match_out(match: ThemeMatch, sides) -> dict:
    title_of = {s.codebook.id: s.title.id for s in sides}
    return {
        "model": match.model,
        "created_at": match.created_at,
        "cost_usd": match.cost_usd,
        "groups": [
            {"name": g["name"], "themes": {str(title_of[m["codebook_id"]]): m["theme_key"] for m in g["members"]}}
            for g in match.groups
        ],
    }


@router.get("/compare")
def compare(
    title_id: list[int] = Query(...),
    date_from: date | None = None,
    date_to: date | None = None,
    session: Session = Depends(get_session),
):
    """% positive, review volume and themes for 2 to 4 titles, plus which themes match across
    them (once someone has paid for the match)."""
    titles = _compare_titles(session, title_id)
    now = utcnow()
    out = []
    for t in titles:
        cb = approved_codebook(session, t.id)
        themes = themes_for(session, cb.id) if cb else []
        stats = theme_stats(session, t.id, cb.id if cb else None, themes, Filters(app_id=t.steam_app_id, date_from=date_from, date_to=date_to))
        c = stats["counts"]
        out.append(
            {
                "id": t.id,
                "name": t.name,
                "header_image_url": t.header_image_url,
                "app_id": t.steam_app_id,
                "reviews": c["reviews"],
                "positive_share": share(c["positive_votes"], c["reviews"]),
                "analyzed": c["analyzed"],
                "codebook_version": cb.version if cb else None,
                "steam": snapshot(session, t.id, t.steam_app_id),
                "trend": trend(session, t.id, t.steam_app_id, now),
                "months": [{k: m[k] for k in ("month", "reviews", "positive_votes")} for m in stats["months"]],
                "overall": stats["overall"] if c["analyzed"] else None,
                "themes": [
                    {k: th[k] for k in ("key", "name", "definition", "mentions", "share", "positive", "negative", "mixed", "net")}
                    for th in stats["themes"]
                ],
            }
        )
    sides = _analyzed_sides(session, titles)
    match = stored_match(session, sides) if len(sides) >= 2 else None
    return {
        "titles": out,
        "theme_match": {
            "eligible_title_ids": [s.title.id for s in sides],
            "status": "ready" if match else ("not_matched" if len(sides) >= 2 else "not_enough"),
            "match": _match_out(match, sides) if match else None,
        },
    }


class MatchRequest(BaseModel):
    title_ids: list[int] = Field(min_length=2, max_length=MAX_TITLES)


def _eligible(session: Session, title_ids: list[int]):
    sides = _analyzed_sides(session, _compare_titles(session, title_ids))
    if len(sides) < 2:
        raise HTTPException(400, "At least 2 of these titles need analyzed reviews before their themes can be matched.")
    return sides


@router.post("/compare/theme-match/estimate")
def theme_match_estimate(body: MatchRequest, session: Session = Depends(get_session), llm: LLMClient = Depends(get_llm)):
    """What matching would cost. Counting tokens is free; nothing is spent here."""
    sides = _eligible(session, body.title_ids)
    return {**estimate_match(get_settings(), llm, sides), "title_ids": [s.title.id for s in sides]}


@router.post("/compare/theme-match")
def theme_match_run(body: MatchRequest, request: Request, session: Session = Depends(get_session), llm: LLMClient = Depends(get_llm)):
    """Match themes across the titles. The UI shows the estimate and asks first."""
    sides = _eligible(session, body.title_ids)
    try:
        match = run_match(session, get_settings(), llm, sides, requested_by=actor(request))
    except ThemeMatchError as exc:
        raise HTTPException(502, f"Theme matching failed: {exc}") from exc
    return _match_out(match, sides)
