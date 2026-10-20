"""Background worker: runs queued syncs, advances confirmed analysis runs, queues the nightly
sync for every active title, starts nightly analysis where it is switched on, and sends alerts.

The worker is the only process that crawls Steam reviews, and it runs one sync at a time, so
the client's request throttle holds across all titles.
"""

import logging
import signal
import sys
import time
from collections.abc import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.alerts import check_alerts
from app.analysis.llm import AnthropicLLM, LLMClient, LLMNotConfigured
from app.analysis.nightly import nightly_analysis
from app.analysis.runs import process_analysis
from app.config import Settings, get_settings
from app.models import SyncRun, Title
from app.steam.client import SteamClient
from app.steam.sync import enqueue_sync, run_sync

log = logging.getLogger(__name__)

ALERT_CHECK_SECONDS = 300


def recover_interrupted(session: Session) -> int:
    """Runs left 'running' by a stopped worker go back to the queue and resume from their cursor."""
    result = session.execute(
        update(SyncRun).where(SyncRun.status == "running").values(status="queued")
    )
    session.commit()
    return result.rowcount or 0


def claim_next(session: Session) -> SyncRun | None:
    # One worker per database. With Postgres and several workers this would use SKIP LOCKED.
    return session.scalar(
        select(SyncRun).where(SyncRun.status == "queued").order_by(SyncRun.queued_at, SyncRun.id).limit(1)
    )


def process_queue(
    session_factory: Callable[[], Session], settings: Settings, client: SteamClient
) -> int:
    """Run queued syncs until the queue is empty. Returns how many ran."""
    ran = 0
    while True:
        with session_factory() as session:
            run = claim_next(session)
            if run is None:
                return ran
            log.info("Sync run %s: app %s, %s", run.id, run.app_id, run.mode)
            run = run_sync(session, settings, client, run)
            log.info(
                "Sync run %s %s: %s pages, %s new, %s edited, %s deleted",
                run.id, run.status, run.pages_fetched, run.new_count, run.updated_count, run.deleted_count,
            )
            ran += 1


def enqueue_all_active(session: Session, settings: Settings, trigger: str = "schedule", requested_by: str | None = None) -> list[SyncRun]:
    """Queue a sync for every title that is not archived, released or not. Unreleased titles
    return no reviews until they have some, then start filling in on their own."""
    runs: list[SyncRun] = []
    titles = session.scalars(select(Title).where(Title.archived_at.is_(None)).order_by(Title.id))
    for title in titles:
        runs.extend(enqueue_sync(session, settings, title, trigger=trigger, requested_by=requested_by))
    return runs


def main() -> None:
    from app.db import SessionLocal

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    client = SteamClient.from_settings(settings)

    with SessionLocal() as session:
        recovered = recover_interrupted(session)
    if recovered:
        log.info("Re-queued %s interrupted sync run(s)", recovered)

    def nightly() -> None:
        with SessionLocal() as session:
            runs = enqueue_all_active(session, settings)
        log.info("Nightly sync: queued %s run(s)", len(runs))

    def nightly_analysis_job() -> None:
        try:
            llm = llm_factory()
        except LLMNotConfigured:
            log.warning("Nightly analysis skipped: no Anthropic API key")
            return
        with SessionLocal() as session:
            for line in nightly_analysis(session, settings, llm):
                log.info("Nightly analysis: %s", line)

    llm: list[LLMClient] = []

    def llm_factory() -> LLMClient:
        # Created on first use, so the worker runs (and syncs) without an API key.
        if not llm:
            llm.append(AnthropicLLM(settings))
        return llm[0]

    # The scheduler only queues work; the main thread drains the queues one run at a time.
    scheduler = BackgroundScheduler(timezone=settings.sync_timezone)
    scheduler.add_job(
        nightly,
        CronTrigger.from_crontab(settings.sync_cron, timezone=settings.sync_timezone),
        id="nightly-sync",
        misfire_grace_time=3600,
        coalesce=True,
    )
    scheduler.add_job(
        nightly_analysis_job,
        CronTrigger.from_crontab(settings.analysis_cron, timezone=settings.sync_timezone),
        id="nightly-analysis",
        misfire_grace_time=3600,
        coalesce=True,
    )
    # docker stop sends SIGTERM; exit through `finally` so the scheduler and client shut down.
    # A run cut off mid-crawl stays 'running' and is re-queued from its cursor on the next start.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    scheduler.start()
    log.info(
        "Worker started. Nightly sync at '%s', nightly analysis at '%s' (%s)", settings.sync_cron, settings.analysis_cron, settings.sync_timezone
    )
    last_alert_check = 0.0
    try:
        while True:
            process_queue(SessionLocal, settings, client)
            process_analysis(SessionLocal, settings, llm_factory)
            if time.monotonic() - last_alert_check >= ALERT_CHECK_SECONDS:
                last_alert_check = time.monotonic()
                try:
                    with SessionLocal() as session:
                        check_alerts(session, settings)
                except Exception:  # alerts must never stop syncing
                    log.exception("Alert check failed")
            time.sleep(settings.worker_poll_seconds)
    except KeyboardInterrupt:
        pass
    finally:
        scheduler.shutdown(wait=False)
        client.close()
