"""Automatic language check: every title's reviews get their language checked and, when not in
English, translated, without anyone starting it.

The worker runs this when it starts and after each sync. Like nightly analysis, it has standing
approval only under a limit: a check estimated at or under TRANSLATION_MAX_USD starts on its own;
a bigger one (say, a newly added title with thousands of reviews) waits for an admin on the title's
Reviews tab and raises an alert. AUTO_TRANSLATE=false turns it off.
"""

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.llm import LLMClient
from app.analysis.nightly import sync_busy
from app.analysis.runs import ESTIMATE_TTL, active_run, confirm, estimate_translation
from app.analysis.translation import unchecked_clauses
from app.config import Settings
from app.models import AnalysisRun, Review, Title
from app.timeutil import utcnow

log = logging.getLogger(__name__)

AUTO = "auto"


def _waiting(session: Session, title_id: int, app_id: int) -> bool:
    """An automatic check already waiting for an admin, so another isn't made."""
    return bool(
        session.scalar(
            select(AnalysisRun.id)
            .where(
                AnalysisRun.title_id == title_id,
                AnalysisRun.app_id == app_id,
                AnalysisRun.kind == "translation",
                AnalysisRun.trigger == AUTO,
                AnalysisRun.status == "estimated",
                AnalysisRun.created_at > utcnow() - ESTIMATE_TTL,
            )
            .limit(1)
        )
    )


def auto_translate(session: Session, settings: Settings, llm: LLMClient) -> list[str]:
    """Start a language check for every app with unchecked reviews. Returns one line per app."""
    if not settings.auto_translate:
        return []
    limit = settings.translation_max_usd
    report: list[str] = []
    for title in session.scalars(select(Title).where(Title.archived_at.is_(None)).order_by(Title.id)).all():
        for app_id in title.app_ids:
            label = title.name if app_id == title.steam_app_id else f"{title.name} demo"
            unchecked = session.scalar(select(func.count()).select_from(Review).where(*unchecked_clauses(title.id, app_id)))
            # A running analysis checks languages itself; a sync still adding reviews is waited for.
            if not unchecked or active_run(session, title.id, app_id) or sync_busy(session, title.id, app_id) or _waiting(session, title.id, app_id):
                continue
            run = estimate_translation(session, settings, llm, title, app_id, requested_by=AUTO, trigger=AUTO)
            if run.est_cost_usd <= limit:
                confirm(session, run, confirmed_by=f"automatic (under the ${limit:.2f} limit)")
                report.append(f"{label}: started, {unchecked} reviews, estimate ${run.est_cost_usd:.4f}")
            else:
                run.warning = (
                    f"Needs an admin: the estimate of ${run.est_cost_usd:.2f} is over the automatic limit of ${limit:.2f}. "
                    "Start it from the title's Reviews tab, or raise TRANSLATION_MAX_USD."
                )
                session.commit()
                report.append(f"{label}: waiting for an admin, estimate ${run.est_cost_usd:.2f} is over the ${limit:.2f} limit")
    return report
