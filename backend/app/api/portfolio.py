"""The portfolio overview across titles, and the compare view for 2 to 4 titles."""

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.analysis.aggregate import Filters, current_tag_join, theme_stats
from app.analysis.codebooks import approved_codebook, themes_for
from app.analysis.llm import LLMClient
from app.analysis.theme_match import MAX_TITLES, ThemeMatchError, sides_for, stored_match
from app.analysis.theme_match import estimate as estimate_match
from app.analysis.theme_match import run as run_match
from app.api.analysis import get_llm
from app.config import get_settings
from app.db import get_session
from app.models import Review, ReviewSnapshot, ReviewTag, Theme, ThemeMatch, ThemeMention, Title
from app.models.sync import ACTIVE_STATUSES
from app.steam.sync import latest_run
from app.timeutil import utcnow

router = APIRouter(prefix="/api", tags=["portfolio"])

TREND_DAYS = 30
WEEKS = 12


def _ts(dt: datetime) -> int:
    return int(dt.replace(tzinfo=UTC).timestamp())


def _share(part: int, whole: int) -> float | None:
    return part / whole if whole else None


def _votes(session: Session, title_id: int, app_id: int, since: int | None = None, until: int | None = None) -> tuple[int, int]:
    """(reviews, positive reviews) for one app, optionally written in [since, until)."""
    clauses = [Review.title_id == title_id, Review.app_id == app_id, Review.deleted_at.is_(None)]
    if since is not None:
        clauses.append(Review.timestamp_created >= since)
    if until is not None:
        clauses.append(Review.timestamp_created < until)
    total, positive = session.execute(
        select(func.count(), func.sum(case((Review.voted_up.is_(True), 1), else_=0))).where(*clauses)
    ).one()
    return total or 0, positive or 0


def _trend(session: Session, title_id: int, app_id: int, now: datetime) -> dict:
    """Reviews written in the last 30 days against the 30 days before."""
    cut = now - timedelta(days=TREND_DAYS)
    last, last_pos = _votes(session, title_id, app_id, since=_ts(cut))
    prev, prev_pos = _votes(session, title_id, app_id, since=_ts(cut - timedelta(days=TREND_DAYS)), until=_ts(cut))
    return {
        "days": TREND_DAYS,
        "last": {"reviews": last, "positive_share": _share(last_pos, last)},
        "previous": {"reviews": prev, "positive_share": _share(prev_pos, prev)},
    }


def _weekly(session: Session, title_id: int, app_id: int, now: datetime) -> list[dict]:
    """Reviews per week for the last 12 weeks, oldest first. The last week ends now."""
    start = now - timedelta(weeks=WEEKS)
    weeks = [{"week_start": (start + timedelta(weeks=i)).date().isoformat(), "reviews": 0, "positive": 0} for i in range(WEEKS)]
    rows = session.execute(
        select(Review.timestamp_created, Review.voted_up).where(
            Review.title_id == title_id,
            Review.app_id == app_id,
            Review.deleted_at.is_(None),
            Review.timestamp_created >= _ts(start),
        )
    )
    for created, up in rows:
        i = min(WEEKS - 1, int((created - _ts(start)) // (7 * 86_400)))
        weeks[i]["reviews"] += 1
        weeks[i]["positive"] += int(bool(up))
    return weeks


def _snapshot(session: Session, title_id: int, app_id: int) -> dict | None:
    s = session.scalar(
        select(ReviewSnapshot)
        .where(ReviewSnapshot.title_id == title_id, ReviewSnapshot.app_id == app_id)
        .order_by(ReviewSnapshot.snapshot_date.desc())
        .limit(1)
    )
    if s is None:
        return None
    return {"total_reviews": s.total_reviews, "review_score_desc": s.review_score_desc, "snapshot_date": s.snapshot_date}


def _theme_highlights(session: Session, title: Title, app_id: int) -> dict | None:
    """Most praised and most criticized themes under the approved codebook, counting each
    review's current tag."""
    cb = approved_codebook(session, title.id)
    if cb is None:
        return None
    review_scope = and_(Review.title_id == title.id, Review.app_id == app_id, Review.deleted_at.is_(None), Review.content_status == "ok")
    analyzed = session.scalar(select(func.count()).select_from(Review).join(ReviewTag, current_tag_join(cb.id)).where(review_scope))
    counts: dict[str, dict] = {}
    rows = session.execute(
        select(Theme.key, Theme.name, ThemeMention.sentiment, func.count())
        .select_from(Review)
        .join(ReviewTag, current_tag_join(cb.id))
        .join(ThemeMention, ThemeMention.review_tag_id == ReviewTag.id)
        .join(Theme, Theme.id == ThemeMention.theme_id)
        .where(review_scope)
        .group_by(Theme.key, Theme.name, ThemeMention.sentiment)
    )
    for key, name, sentiment, n in rows:
        c = counts.setdefault(key, {"key": key, "name": name, "mentions": 0, "positive": 0, "negative": 0, "mixed": 0})
        c["mentions"] += n
        c[sentiment] += n
    for c in counts.values():
        c["share"] = _share(c["mentions"], analyzed)
    # Ranked by how many more positive than negative mentions (and the reverse), so a theme that
    # is widely discussed but splits players doesn't count as the most praised.
    praised = max((c for c in counts.values() if c["positive"] > c["negative"]), key=lambda c: (c["positive"] - c["negative"], c["mentions"]), default=None)
    criticized = max((c for c in counts.values() if c["negative"] > c["positive"]), key=lambda c: (c["negative"] - c["positive"], c["mentions"]), default=None)
    return {"codebook_version": cb.version, "analyzed": analyzed, "top_praised": praised, "top_criticized": criticized}


def _app_card(session: Session, title: Title, app_id: int, now: datetime) -> dict:
    total, positive = _votes(session, title.id, app_id)
    return {
        "app_id": app_id,
        "reviews": total,
        "positive_share": _share(positive, total),
        "steam": _snapshot(session, title.id, app_id),
        "trend": _trend(session, title.id, app_id, now),
        "weekly": _weekly(session, title.id, app_id, now),
    }


def title_card(session: Session, title: Title, now: datetime) -> dict:
    main = _app_card(session, title, title.steam_app_id, now)
    last_ok = latest_run(session, title.id, title.steam_app_id, status=["succeeded"])
    syncing = any(latest_run(session, title.id, a, status=list(ACTIVE_STATUSES)) for a in title.app_ids)
    return {
        "id": title.id,
        "name": title.name,
        "status": title.status,
        "header_image_url": title.header_image_url,
        "developers": title.developers or [],
        "release_date_text": title.release_date_text,
        **main,
        "themes": _theme_highlights(session, title, title.steam_app_id),
        "demo": {**_app_card(session, title, title.demo_app_id, now), "themes": _theme_highlights(session, title, title.demo_app_id)}
        if title.demo_app_id
        else None,
        "last_synced_at": last_ok.finished_at if last_ok else None,
        "syncing": syncing,
    }


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
        highlights = _theme_highlights(session, t, t.steam_app_id)
        if highlights and highlights["analyzed"]:
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
                "positive_share": _share(c["positive_votes"], c["reviews"]),
                "analyzed": c["analyzed"],
                "codebook_version": cb.version if cb else None,
                "steam": _snapshot(session, t.id, t.steam_app_id),
                "trend": _trend(session, t.id, t.steam_app_id, now),
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
def theme_match_run(body: MatchRequest, session: Session = Depends(get_session), llm: LLMClient = Depends(get_llm)):
    """Match themes across the titles. The UI shows the estimate and asks first."""
    sides = _eligible(session, body.title_ids)
    try:
        match = run_match(session, get_settings(), llm, sides, requested_by="app")
    except ThemeMatchError as exc:
        raise HTTPException(502, f"Theme matching failed: {exc}") from exc
    return _match_out(match, sides)
