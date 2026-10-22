"""Nightly analysis of new reviews, for titles where an admin switched it on.

After the nightly sync, each such title gets an analysis estimate covering its new and edited
reviews (including the language check and translation of any review not checked yet). Standing approval comes from the switch plus a per-night limit: an estimate at or under
NIGHTLY_ANALYSIS_MAX_USD is confirmed automatically; anything above waits for an admin (and
raises an alert). Nightly runs leave out the quality check unless there are enough new reviews
for a real sample, and rewrite the executive summary at most every SUMMARY_REFRESH_DAYS days.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.codebooks import approved_codebook
from app.analysis.llm import LLMClient
from app.analysis.prep import prepare_missing
from app.analysis.runs import active_run, confirm, estimate_analysis
from app.analysis.tagging import pending_reviews
from app.analysis.translation import unchecked_reviews
from app.config import Settings
from app.models import AnalysisRun, Review, ReviewTag, Summary, SyncRun, Title
from app.models.sync import ACTIVE_STATUSES
from app.timeutil import utcnow

log = logging.getLogger(__name__)

NIGHTLY = "nightly"
# Used for the monthly forecast until real runs give averages.
FALLBACK_PER_REVIEW_USD = 0.0002
FALLBACK_PER_NIGHT_USD = 0.001
FALLBACK_SUMMARY_USD = 0.06


def _last_summary(session: Session, title_id: int, app_id: int) -> Summary | None:
    return session.scalar(
        select(Summary).where(Summary.title_id == title_id, Summary.app_id == app_id).order_by(Summary.id.desc()).limit(1)
    )


def summary_due(session: Session, settings: Settings, title: Title, app_id: int, codebook_id: int, now: datetime, pending: int) -> bool:
    """A summary is due when there is none yet, or the last one is old and there is something new
    to say: reviews waiting to be tagged now, or tagged since it was written."""
    last = _last_summary(session, title.id, app_id)
    if last is None:
        return True
    if now - last.created_at < timedelta(days=settings.summary_refresh_days):
        return False
    if pending:
        return True
    tagged_since = session.scalar(
        select(func.count())
        .select_from(ReviewTag)
        .join(Review, Review.id == ReviewTag.review_id)
        .where(Review.title_id == title.id, Review.app_id == app_id, ReviewTag.codebook_id == codebook_id, ReviewTag.created_at > last.created_at)
    )
    return bool(tagged_since)


def sync_busy(session: Session, title_id: int, app_id: int) -> bool:
    return bool(
        session.scalar(
            select(SyncRun.id).where(SyncRun.title_id == title_id, SyncRun.app_id == app_id, SyncRun.status.in_(ACTIVE_STATUSES)).limit(1)
        )
    )


def nightly_analysis(session: Session, settings: Settings, llm: LLMClient, now: datetime | None = None) -> list[str]:
    """Estimate (and, under the limit, start) tonight's runs. Returns one line per title for the log."""
    now = now or utcnow()
    limit = settings.nightly_analysis_max_usd
    report: list[str] = []
    titles = session.scalars(select(Title).where(Title.auto_analyze.is_(True), Title.archived_at.is_(None)).order_by(Title.id)).all()
    for title in titles:
        codebook = approved_codebook(session, title.id)
        if codebook is None:
            report.append(f"{title.name}: skipped, no approved codebook")
            continue
        for app_id in title.app_ids:
            label = title.name if app_id == title.steam_app_id else f"{title.name} demo"
            if sync_busy(session, title.id, app_id):
                report.append(f"{label}: skipped, its sync is still running (tried again tomorrow)")
                continue
            if active_run(session, title.id, app_id):
                report.append(f"{label}: skipped, an analysis is already running")
                continue
            prepare_missing(session, title.id)
            pending = len(pending_reviews(session, title.id, app_id, codebook.id))
            due = summary_due(session, settings, title, app_id, codebook.id, now, pending)
            unchecked = len(unchecked_reviews(session, title.id, app_id))
            if not pending and not due and not unchecked:
                continue
            if not pending and not unchecked and _last_summary(session, title.id, app_id) is None and not session.scalar(
                select(func.count()).select_from(ReviewTag).join(Review).where(Review.title_id == title.id, Review.app_id == app_id)
            ):
                continue  # nothing analyzed and nothing to analyze (a demo with no text reviews)
            run = estimate_analysis(
                session,
                settings,
                llm,
                title,
                app_id,
                requested_by=NIGHTLY,
                qa=pending >= settings.qa_min_reviews,
                summary=due,
                trigger=NIGHTLY,
            )
            if run.est_cost_usd <= limit:
                confirm(session, run, confirmed_by=f"nightly (under the ${limit:.2f} limit)")
                report.append(f"{label}: started, {pending} reviews, estimate ${run.est_cost_usd:.4f}")
            else:
                run.warning = (
                    f"Needs an admin: the estimate of ${run.est_cost_usd:.2f} is over the nightly limit of ${limit:.2f}. "
                    "Start it from Themes setup, or raise NIGHTLY_ANALYSIS_MAX_USD."
                )
                session.commit()
                report.append(f"{label}: waiting for an admin, estimate ${run.est_cost_usd:.2f} is over the ${limit:.2f} limit")
    return report


def expected_monthly_cost(session: Session, settings: Settings, title: Title, now: datetime | None = None) -> dict:
    """A forecast of what nightly analysis would cost this title per month, from its last 30 days
    of reviews and what past runs actually cost."""
    now = now or utcnow()
    since = int((now - timedelta(days=30)).timestamp())
    created = session.scalars(
        select(Review.timestamp_created).where(
            Review.title_id == title.id, Review.deleted_at.is_(None), Review.content_status != "no_content", Review.timestamp_created >= since
        )
    ).all()
    reviews = len(created)
    nights = len({ts // 86_400 for ts in created})

    runs = session.scalars(select(AnalysisRun).where(AnalysisRun.kind == "analysis", AnalysisRun.status == "succeeded")).all()
    tagged = sum(r.reviews_tagged for r in runs)
    # Per review: tagging plus the language check, which every new review also gets.
    tag_cost = sum(((r.usage or {}).get(step) or {}).get("cost_usd", 0.0) for r in runs for step in ("tagging", "translation"))
    summaries = [((r.usage or {}).get("summary") or {}).get("cost_usd") for r in runs]
    summaries = [c for c in summaries if c]
    # Nightly runs are small, so they call the API directly at full price: twice the batch rate.
    per_review = 2 * tag_cost / tagged if tagged and tag_cost else FALLBACK_PER_REVIEW_USD
    summary_cost = sum(summaries) / len(summaries) if summaries else FALLBACK_SUMMARY_USD
    summaries_per_month = min(30 / settings.summary_refresh_days, nights) if reviews else 0
    total = reviews * per_review + nights * FALLBACK_PER_NIGHT_USD + summaries_per_month * summary_cost
    return {
        "enabled": title.auto_analyze,
        "nightly_limit_usd": settings.nightly_analysis_max_usd,
        "reviews_last_30_days": reviews,
        "nights_with_reviews": nights,
        "per_review_usd": round(per_review, 6),
        "summary_usd": round(summary_cost, 4),
        "summaries_per_month": round(summaries_per_month, 1),
        "expected_monthly_usd": round(total, 2),
    }
