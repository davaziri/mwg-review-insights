"""Alerts: tell the team when something needs attention, by Slack and/or email.

The worker checks every few minutes for:
- a sync or analysis run that failed,
- a nightly analysis or automatic language check waiting for an admin (its estimate was over
  its limit),
- a title whose % recommended fell by more than ALERT_DROP_POINTS over ALERT_DROP_DAYS.

Each alert is stored once (by its dedupe key) and listed in the run log, whether or not Slack or
email is set up. A failed delivery is recorded on the alert and never stops the worker.
"""

import logging
import smtplib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

import httpx
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Alert, AnalysisRun, Review, SyncRun, Title
from app.timeutil import utcnow

log = logging.getLogger(__name__)

LOOKBACK = timedelta(days=2)


@dataclass
class Notice:
    kind: str
    title_id: int | None
    dedupe_key: str
    subject: str
    body: str


def _link(settings: Settings, path: str) -> str:
    return f"\n\n{settings.public_url.rstrip('/')}{path}" if settings.public_url else ""


def _app_label(title: Title, app_id: int) -> str:
    return title.name if app_id == title.steam_app_id else f"{title.name} (demo)"


def _share(session: Session, title_id: int, app_id: int, until_ts: int | None = None) -> tuple[int, float | None]:
    clauses = [Review.title_id == title_id, Review.app_id == app_id, Review.deleted_at.is_(None)]
    if until_ts is not None:
        clauses.append(Review.timestamp_created <= until_ts)
    total, positive = session.execute(select(func.count(), func.sum(case((Review.voted_up.is_(True), 1), else_=0))).where(*clauses)).one()
    return total or 0, (positive or 0) / total if total else None


def positive_drop(session: Session, settings: Settings, title: Title, app_id: int, now: datetime) -> tuple[float, float, float] | None:
    """(share then, share now, drop in points) when % recommended fell by more than the alert
    threshold over the alert window, counting only titles with enough reviews to be steady."""
    then = int((now - timedelta(days=settings.alert_drop_days)).replace(tzinfo=UTC).timestamp())
    before_total, before = _share(session, title.id, app_id, then)
    _, current = _share(session, title.id, app_id)
    if before is None or current is None or before_total < settings.alert_min_reviews:
        return None
    drop = (before - current) * 100
    return (before, current, drop) if drop > settings.alert_drop_points else None


def find_notices(session: Session, settings: Settings, now: datetime) -> list[Notice]:
    since = now - LOOKBACK
    titles = {t.id: t for t in session.scalars(select(Title))}
    notices: list[Notice] = []

    for run in session.scalars(select(SyncRun).where(SyncRun.status == "failed", SyncRun.finished_at >= since)):
        title = titles[run.title_id]
        notices.append(
            Notice(
                "sync_failed",
                title.id,
                f"sync_failed:{run.id}",
                f"Review sync failed: {_app_label(title, run.app_id)}",
                f"The {run.mode} sync of {_app_label(title, run.app_id)} stopped with this error: {run.error or 'no details'}. "
                "The next sync picks up from where this one stopped." + _link(settings, "/runs"),
            )
        )

    failed = select(AnalysisRun).where(AnalysisRun.status == "failed", AnalysisRun.confirmed_at.is_not(None), AnalysisRun.finished_at >= since)
    for run in session.scalars(failed):
        title = titles[run.title_id]
        notices.append(
            Notice(
                "analysis_failed",
                title.id,
                f"analysis_failed:{run.id}",
                f"Analysis failed: {_app_label(title, run.app_id)}",
                f"The {run.kind} run for {_app_label(title, run.app_id)} stopped with this error: {run.error or 'no details'}. "
                f"It had cost ${run.actual_cost_usd:.2f}." + _link(settings, f"/titles/{title.id}/analysis"),
            )
        )

    waiting = select(AnalysisRun).where(
        AnalysisRun.status == "estimated", AnalysisRun.trigger.in_(("nightly", "auto")), AnalysisRun.created_at >= since
    )
    for run in session.scalars(waiting):
        title = titles[run.title_id]
        if run.kind == "translation":
            notices.append(
                Notice(
                    "needs_confirmation",
                    title.id,
                    f"needs_confirmation:{run.id}",
                    f"Language check needs an admin: {_app_label(title, run.app_id)}",
                    f"Checking the language of {run.reviews_in_scope} reviews of {_app_label(title, run.app_id)} and translating them is "
                    f"estimated at ${run.est_cost_usd:.2f}, over the automatic limit of ${settings.translation_max_usd:.2f}, so it did not "
                    "start. An admin can start it from the title's Reviews tab." + _link(settings, f"/titles/{title.id}/reviews"),
                )
            )
            continue
        notices.append(
            Notice(
                "needs_confirmation",
                title.id,
                f"needs_confirmation:{run.id}",
                f"Nightly analysis needs an admin: {_app_label(title, run.app_id)}",
                f"Tonight's analysis of {run.reviews_in_scope} new reviews for {_app_label(title, run.app_id)} is estimated at "
                f"${run.est_cost_usd:.2f}, over the nightly limit of ${settings.nightly_analysis_max_usd:.2f}, so it did not start. "
                "An admin can start it from Themes setup." + _link(settings, f"/titles/{title.id}/analysis"),
            )
        )

    year, week, _ = now.isocalendar()
    for title in titles.values():
        if title.archived_at is not None:
            continue
        for app_id in title.app_ids:
            found = positive_drop(session, settings, title, app_id, now)
            if found is None:
                continue
            before, current, drop = found
            notices.append(
                Notice(
                    "positive_drop",
                    title.id,
                    f"positive_drop:{title.id}:{app_id}:{year}-W{week:02d}",
                    f"{_app_label(title, app_id)}: recommended fell {drop:.0f} points in {settings.alert_drop_days} days",
                    f"{_app_label(title, app_id)} went from {before:.0%} to {current:.0%} recommended over the last "
                    f"{settings.alert_drop_days} days. The newest reviews are on the title's Reviews page."
                    + _link(settings, f"/titles/{title.id}/reviews?sort=newest"),
                )
            )
    return notices


def _send_slack(settings: Settings, alert: Alert, http: httpx.Client) -> None:
    resp = http.post(settings.slack_webhook_url, json={"text": f"*{alert.subject}*\n{alert.body}"}, timeout=15)
    resp.raise_for_status()


def _send_email(settings: Settings, alert: Alert) -> None:
    msg = EmailMessage()
    msg["Subject"] = f"[Review Insights] {alert.subject}"
    msg["From"] = settings.smtp_from or settings.smtp_user or "review-insights@localhost"
    msg["To"] = ", ".join(settings.alert_email_list)
    msg.set_content(alert.body)
    smtp_class = smtplib.SMTP_SSL if settings.smtp_port == 465 else smtplib.SMTP
    with smtp_class(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        if settings.smtp_port != 465:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password or "")
        smtp.send_message(msg)


def channels(settings: Settings) -> dict[str, bool]:
    return {"slack": bool(settings.slack_webhook_url), "email": bool(settings.smtp_host and settings.alert_email_list)}


def deliver(settings: Settings, alert: Alert, http: httpx.Client | None = None) -> None:
    """Send to every channel that is set up, recording where it went and what failed."""
    sent, errors = [], []
    on = channels(settings)
    if on["slack"]:
        own = http is None
        client = http or httpx.Client()
        try:
            _send_slack(settings, alert, client)
            sent.append("slack")
        except httpx.HTTPError as exc:
            errors.append(f"Slack: {exc}")
        finally:
            if own:
                client.close()
    if on["email"]:
        try:
            _send_email(settings, alert)
            sent.append("email")
        except (OSError, smtplib.SMTPException) as exc:
            errors.append(f"Email: {exc}")
    alert.channels = sent
    alert.error = "; ".join(errors) or None


def check_alerts(session: Session, settings: Settings, now: datetime | None = None, http: httpx.Client | None = None) -> list[Alert]:
    """Store and send any new alerts. Returns the ones created this time."""
    now = now or utcnow()
    notices = find_notices(session, settings, now)
    if not notices:
        return []
    known = set(session.scalars(select(Alert.dedupe_key).where(Alert.dedupe_key.in_([n.dedupe_key for n in notices]))))
    created = []
    for n in notices:
        if n.dedupe_key in known:
            continue
        alert = Alert(kind=n.kind, title_id=n.title_id, dedupe_key=n.dedupe_key, subject=n.subject, body=n.body, channels=[])
        session.add(alert)
        session.commit()  # stored first, so a crash mid-send never sends it twice
        deliver(settings, alert, http)
        session.commit()
        log.info("Alert %s: %s (sent to %s)", alert.kind, alert.subject, ", ".join(alert.channels) or "nowhere, no channel set up")
        created.append(alert)
    return created


def send_test(session: Session, settings: Settings, who: str, http: httpx.Client | None = None) -> Alert:
    alert = Alert(
        kind="test",
        title_id=None,
        dedupe_key=f"test:{utcnow().isoformat()}",
        subject="Test alert from Review Insights",
        body=f"{who} sent this to check that alerts arrive. Nothing needs doing.",
        channels=[],
    )
    session.add(alert)
    session.commit()
    deliver(settings, alert, http)
    session.commit()
    return alert
