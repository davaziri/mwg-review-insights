"""Review sync: decide what to fetch, upsert what Steam returns, and keep enough state to resume.

Modes:
- full: walk every review newest-created first (Steam's Recent sort). Afterwards, reviews not seen
  during the crawl are marked deleted.
- incremental: walk newest-updated first (Steam's Updated sort) and stop once the page reaches
  reviews older than the newest edit already stored. Picks up new and edited reviews only.
"""

import logging
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.analysis.prep import prepare_review
from app.config import Settings
from app.models import Review, ReviewSnapshot, SyncRun, Title
from app.models.sync import ACTIVE_STATUSES
from app.steam.appdetails import appdetails_stale, refresh_appdetails
from app.steam.client import FIRST_CURSOR, SteamClient
from app.timeutil import utcnow

log = logging.getLogger(__name__)


# Field mapping


def _int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool(value) -> bool | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes")
    return bool(value)


def review_fields(raw: dict) -> dict:
    """Map one Steam review object onto Review columns. The full object is kept in raw_json."""
    author = raw.get("author") or {}
    steamid = author.get("steamid")
    return {
        "recommendation_id": str(raw["recommendationid"]),
        "language": raw.get("language"),
        "review_text": raw.get("review") or "",
        "timestamp_created": _int(raw.get("timestamp_created")),
        "timestamp_updated": _int(raw.get("timestamp_updated")),
        "voted_up": _bool(raw.get("voted_up")),
        "votes_up": _int(raw.get("votes_up")),
        "votes_funny": _int(raw.get("votes_funny")),
        "weighted_vote_score": _float(raw.get("weighted_vote_score")),
        "comment_count": _int(raw.get("comment_count")),
        "steam_purchase": _bool(raw.get("steam_purchase")),
        "received_for_free": _bool(raw.get("received_for_free")),
        "written_during_early_access": _bool(raw.get("written_during_early_access")),
        "primarily_steam_deck": _bool(raw.get("primarily_steam_deck")),
        "refunded": _bool(raw.get("refunded")),
        "developer_response": raw.get("developer_response") or None,
        "timestamp_dev_responded": _int(raw.get("timestamp_dev_responded")),
        "author_steamid": str(steamid) if steamid is not None else None,
        "author_num_games_owned": _int(author.get("num_games_owned")),
        "author_num_reviews": _int(author.get("num_reviews")),
        "author_playtime_forever": _int(author.get("playtime_forever")),
        "author_playtime_last_two_weeks": _int(author.get("playtime_last_two_weeks")),
        "author_playtime_at_review": _int(author.get("playtime_at_review")),
        "author_deck_playtime_at_review": _int(author.get("deck_playtime_at_review")),
        "author_last_played": _int(author.get("last_played")),
        "raw_json": raw,
    }


# Writes


@dataclass
class UpsertStats:
    seen: int = 0
    new: int = 0
    updated: int = 0
    restored: int = 0


def upsert_reviews(
    session: Session, title_id: int, app_id: int, raw_reviews: list[dict], seen_at
) -> UpsertStats:
    """Insert new reviews and refresh existing ones. A review counts as updated (and will be
    re-analyzed) only when its timestamp_updated changed; vote counts refresh silently."""
    stats = UpsertStats()
    incoming: dict[str, dict] = {}
    for raw in raw_reviews:
        if raw.get("recommendationid") is None:
            log.warning("Skipping review without recommendationid for app %s", app_id)
            continue
        fields = review_fields(raw)
        incoming[fields["recommendation_id"]] = fields
    if not incoming:
        return stats

    existing = {
        r.recommendation_id: r
        for r in session.scalars(select(Review).where(Review.recommendation_id.in_(incoming)))
    }
    for rec_id, fields in incoming.items():
        stats.seen += 1
        review = existing.get(rec_id)
        if review is None:
            review = Review(title_id=title_id, app_id=app_id, first_seen_at=seen_at, last_seen_at=seen_at, **fields)
            prepare_review(review)
            session.add(review)
            stats.new += 1
            continue
        if (review.title_id, review.app_id) != (title_id, app_id):
            log.warning("Review %s already belongs to app %s; skipping", rec_id, review.app_id)
            continue
        if review.timestamp_updated != fields["timestamp_updated"]:
            stats.updated += 1
        if review.deleted_at is not None:
            review.deleted_at = None
            stats.restored += 1
        for key, value in fields.items():
            setattr(review, key, value)
        prepare_review(review)
        review.last_seen_at = seen_at
    return stats


def record_snapshot(session: Session, title_id: int, app_id: int, summary: dict) -> ReviewSnapshot:
    """Store Steam's query_summary as today's snapshot (UTC), replacing an earlier one from today."""
    today = utcnow().date()
    snap = session.scalar(
        select(ReviewSnapshot).where(
            ReviewSnapshot.title_id == title_id,
            ReviewSnapshot.app_id == app_id,
            ReviewSnapshot.snapshot_date == today,
        )
    )
    if snap is None:
        snap = ReviewSnapshot(title_id=title_id, app_id=app_id, snapshot_date=today)
        session.add(snap)
    snap.total_reviews = _int(summary.get("total_reviews"))
    snap.total_positive = _int(summary.get("total_positive"))
    snap.total_negative = _int(summary.get("total_negative"))
    snap.review_score = _int(summary.get("review_score"))
    snap.review_score_desc = summary.get("review_score_desc")
    snap.raw_json = summary
    snap.captured_at = utcnow()
    return snap


def active_review_count(session: Session, title_id: int, app_id: int) -> int:
    return session.scalar(
        select(func.count())
        .select_from(Review)
        .where(Review.title_id == title_id, Review.app_id == app_id, Review.deleted_at.is_(None))
    )


def mark_deletions(session: Session, settings: Settings, run: SyncRun) -> None:
    """After a complete full crawl, mark reviews that Steam no longer returns as deleted."""
    gone = (
        Review.title_id == run.title_id,
        Review.app_id == run.app_id,
        Review.deleted_at.is_(None),
        Review.last_seen_at < run.crawl_started_at,
    )
    missing = session.scalar(select(func.count()).select_from(Review).where(*gone))
    if not missing:
        return
    total = active_review_count(session, run.title_id, run.app_id)
    if missing > 5 and missing > settings.deletion_guard_ratio * total:
        run.warning = (
            f"Did not mark {missing} of {total} reviews as deleted: that many disappearing in one crawl "
            "usually means Steam returned an incomplete list. The next full sync will check again."
        )
        log.warning("App %s: %s", run.app_id, run.warning)
        return
    session.execute(update(Review).where(*gone).values(deleted_at=utcnow()))
    run.deleted_count = missing


# Planning


def latest_run(session: Session, title_id: int, app_id: int, **filters) -> SyncRun | None:
    query = select(SyncRun).where(SyncRun.title_id == title_id, SyncRun.app_id == app_id)
    if "status" in filters:
        query = query.where(SyncRun.status.in_(filters["status"]))
    if "mode" in filters:
        query = query.where(SyncRun.mode == filters["mode"])
    return session.scalar(query.order_by(SyncRun.id.desc()).limit(1))


def choose_mode(session: Session, settings: Settings, title_id: int, app_id: int) -> str:
    last_full = latest_run(session, title_id, app_id, status=["succeeded"], mode="full")
    if last_full is None or last_full.finished_at is None:
        return "full"
    age = utcnow() - last_full.finished_at
    if age > timedelta(days=settings.full_sync_interval_days):
        return "full"

    # If Steam reports clearly more reviews than we hold, something was missed: re-crawl,
    # but at most once a day so a permanent small gap can't force a full crawl every time.
    snap = session.scalar(
        select(ReviewSnapshot)
        .where(ReviewSnapshot.title_id == title_id, ReviewSnapshot.app_id == app_id)
        .order_by(ReviewSnapshot.snapshot_date.desc())
        .limit(1)
    )
    if snap is not None and snap.total_reviews is not None and age > timedelta(days=1):
        gap = snap.total_reviews - active_review_count(session, title_id, app_id)
        if gap > max(2, settings.count_drift_tolerance * snap.total_reviews):
            return "full"
    return "incremental"


def _resumable(session: Session, settings: Settings, title_id: int, app_id: int, mode: str) -> SyncRun | None:
    """The most recent run for this app, if it failed partway through a crawl of the same mode."""
    last = latest_run(session, title_id, app_id)
    if last is None or last.status != "failed" or last.mode != mode or not last.cursor:
        return None
    if last.cursor == FIRST_CURSOR or last.finished_at is None:
        return None
    if utcnow() - last.finished_at > timedelta(hours=settings.resume_window_hours):
        return None
    return last


def enqueue_sync(
    session: Session,
    settings: Settings,
    title: Title,
    *,
    trigger: str,
    requested_by: str | None = None,
    mode: str | None = None,
) -> list[SyncRun]:
    """Queue a sync for each of the title's Steam apps. Apps that already have a queued or
    running sync are not queued twice; their existing run is returned instead."""
    runs = []
    for app_id in title.app_ids:
        active = latest_run(session, title.id, app_id, status=list(ACTIVE_STATUSES))
        if active is not None:
            runs.append(active)
            continue
        run_mode = mode or choose_mode(session, settings, title.id, app_id)
        run = SyncRun(
            title_id=title.id,
            app_id=app_id,
            mode=run_mode,
            trigger=trigger,
            requested_by=requested_by,
            status="queued",
            queued_at=utcnow(),
        )
        previous = _resumable(session, settings, title.id, app_id, run_mode)
        if previous is not None:
            run.resumed_from_id = previous.id
            run.cursor = previous.cursor
            run.crawl_started_at = previous.crawl_started_at
            run.high_water_mark = previous.high_water_mark
        session.add(run)
        runs.append(run)
    session.commit()
    return runs


# Execution


def run_sync(session: Session, settings: Settings, client: SteamClient, run: SyncRun) -> SyncRun:
    """Execute one queued run. Progress is committed after every page, so an interrupted run can
    resume from its saved cursor. Failures are recorded on the run, not raised."""
    title = session.get(Title, run.title_id)
    now = utcnow()
    run.status = "running"
    run.started_at = now
    run.error = None
    if run.crawl_started_at is None:
        run.crawl_started_at = now
    if run.mode == "incremental" and run.high_water_mark is None:
        run.high_water_mark = session.scalar(
            select(func.max(Review.timestamp_updated)).where(
                Review.title_id == run.title_id, Review.app_id == run.app_id
            )
        )
    session.commit()

    try:
        if run.app_id == title.steam_app_id and appdetails_stale(title, settings.appdetails_max_age_hours):
            refresh_appdetails(title, client)
            session.commit()

        full = run.mode == "full"
        sort_filter = settings.steam_filter_full if full else settings.steam_filter_incremental
        stop_below = None
        if not full and run.high_water_mark is not None:
            stop_below = run.high_water_mark - settings.incremental_overlap_seconds

        snapshot_taken = False
        pages = client.iter_review_pages(run.app_id, run.cursor or FIRST_CURSOR, sort_filter=sort_filter)
        for _used_cursor, page in pages:
            if page.query_summary and not snapshot_taken:
                record_snapshot(session, run.title_id, run.app_id, page.query_summary)
                run.steam_total = _int(page.query_summary.get("total_reviews"))
                snapshot_taken = True
            run.pages_fetched += 1
            if page.reviews:
                stats = upsert_reviews(session, run.title_id, run.app_id, page.reviews, seen_at=utcnow())
                run.reviews_seen += stats.seen
                run.new_count += stats.new
                run.updated_count += stats.updated
                run.restored_count += stats.restored
                run.cursor = page.cursor
            session.commit()

            if stop_below is not None and page.reviews:
                oldest = min(_int(r.get("timestamp_updated")) or 0 for r in page.reviews)
                if oldest < stop_below:
                    break

        if full:
            mark_deletions(session, settings, run)
        run.status = "succeeded"
        run.finished_at = utcnow()
        session.commit()
    except Exception as exc:
        session.rollback()
        log.exception("Sync run %s failed", run.id)
        run.status = "failed"
        run.error = f"{type(exc).__name__}: {exc}"[:2000]
        run.finished_at = utcnow()
        session.commit()
    return run
