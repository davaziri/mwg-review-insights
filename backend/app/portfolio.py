"""Title-level numbers for the portfolio page, the compare view and the portfolio report:
review counts, the 30-day trend, weekly volume, Steam's rating, and the top themes."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.analysis.aggregate import current_tag_join, highlights
from app.analysis.codebooks import approved_codebook
from app.models import Review, ReviewSnapshot, ReviewTag, Theme, ThemeMention, Title
from app.models.sync import ACTIVE_STATUSES
from app.steam.sync import latest_run

TREND_DAYS = 30
WEEKS = 12


def _ts(dt: datetime) -> int:
    return int(dt.replace(tzinfo=UTC).timestamp())


def share(part: int, whole: int) -> float | None:
    return part / whole if whole else None


def votes(session: Session, title_id: int, app_id: int, since: int | None = None, until: int | None = None) -> tuple[int, int]:
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


def trend(session: Session, title_id: int, app_id: int, now: datetime) -> dict:
    """Reviews written in the last 30 days against the 30 days before."""
    cut = now - timedelta(days=TREND_DAYS)
    last, last_pos = votes(session, title_id, app_id, since=_ts(cut))
    prev, prev_pos = votes(session, title_id, app_id, since=_ts(cut - timedelta(days=TREND_DAYS)), until=_ts(cut))
    return {
        "days": TREND_DAYS,
        "last": {"reviews": last, "positive_share": share(last_pos, last)},
        "previous": {"reviews": prev, "positive_share": share(prev_pos, prev)},
    }


def weekly(session: Session, title_id: int, app_id: int, now: datetime) -> list[dict]:
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


def snapshot(session: Session, title_id: int, app_id: int) -> dict | None:
    s = session.scalar(
        select(ReviewSnapshot)
        .where(ReviewSnapshot.title_id == title_id, ReviewSnapshot.app_id == app_id)
        .order_by(ReviewSnapshot.snapshot_date.desc())
        .limit(1)
    )
    if s is None:
        return None
    return {"total_reviews": s.total_reviews, "review_score_desc": s.review_score_desc, "snapshot_date": s.snapshot_date}


def theme_highlights(session: Session, title: Title, app_id: int) -> dict | None:
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
        c["share"] = share(c["mentions"], analyzed)
    praised, criticized = highlights(list(counts.values()))
    return {
        "codebook_version": cb.version,
        "analyzed": analyzed,
        "top_praised": praised[0] if praised else None,
        "top_criticized": criticized[0] if criticized else None,
    }


def _app_card(session: Session, title: Title, app_id: int, now: datetime) -> dict:
    total, positive = votes(session, title.id, app_id)
    return {
        "app_id": app_id,
        "reviews": total,
        "positive_share": share(positive, total),
        "steam": snapshot(session, title.id, app_id),
        "trend": trend(session, title.id, app_id, now),
        "weekly": weekly(session, title.id, app_id, now),
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
        "themes": theme_highlights(session, title, title.steam_app_id),
        "demo": {**_app_card(session, title, title.demo_app_id, now), "themes": theme_highlights(session, title, title.demo_app_id)}
        if title.demo_app_id
        else None,
        "last_synced_at": last_ok.finished_at if last_ok else None,
        "syncing": syncing,
    }
