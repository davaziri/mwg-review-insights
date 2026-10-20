"""Alerts: failed runs, nightly runs waiting for an admin, and a drop in % recommended."""

from datetime import timedelta

import httpx
import pytest
import respx

from app.alerts import check_alerts
from app.models import Alert, AnalysisRun, SyncRun, Title
from app.steam.sync import upsert_reviews
from app.timeutil import utcnow
from tests.fakes import make_review

APP = 3308200
HOOK = "https://hooks.slack.test/services/abc"


class FakeSMTP:
    """Stands in for smtplib.SMTP and remembers what it was asked to send."""

    sent: list = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        pass

    def login(self, user, password):
        self.user = user

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


@pytest.fixture
def channels(settings, monkeypatch):
    settings.slack_webhook_url = HOOK
    settings.smtp_host = "smtp.test"
    settings.smtp_user = "alerts@midwestgames.com"
    settings.alert_emails = "team@midwestgames.com, boss@midwestgames.com"
    settings.public_url = "https://insights.example.com"
    FakeSMTP.sent = []
    monkeypatch.setattr("app.alerts.smtplib.SMTP", FakeSMTP)
    return settings


def failed_sync(session, title):
    run = SyncRun(title_id=title.id, app_id=APP, mode="incremental", trigger="schedule", status="failed", error="HTTP 503 from Steam", finished_at=utcnow())
    session.add(run)
    session.commit()
    return run


def test_failed_sync_alerts_once_on_every_channel(session, settings, title, channels):
    run = failed_sync(session, title)
    with respx.mock() as mock:
        hook = mock.post(HOOK).mock(return_value=httpx.Response(200))
        (alert,) = check_alerts(session, settings)
        assert check_alerts(session, settings) == []  # not again
    assert hook.call_count == 1
    assert alert.kind == "sync_failed" and alert.dedupe_key == f"sync_failed:{run.id}"
    assert alert.channels == ["slack", "email"] and alert.error is None
    assert "HTTP 503 from Steam" in alert.body and "https://insights.example.com/runs" in alert.body
    (msg,) = FakeSMTP.sent
    assert msg["To"] == "team@midwestgames.com, boss@midwestgames.com" and "Review sync failed: Tombwater" in msg["Subject"]
    assert "—" not in alert.subject + alert.body


def test_old_failures_and_unconfirmed_estimates_are_left_alone(session, settings, title):
    run = failed_sync(session, title)
    run.finished_at = utcnow() - timedelta(days=5)
    session.add(AnalysisRun(title_id=title.id, app_id=APP, kind="analysis", status="failed", error="boom", finished_at=utcnow()))  # never confirmed
    session.commit()
    assert check_alerts(session, settings) == []


def test_failed_analysis_and_nightly_waiting(session, settings, title):
    session.add_all(
        [
            AnalysisRun(title_id=title.id, app_id=APP, kind="analysis", status="failed", error="RuntimeError: batch expired", confirmed_at=utcnow(), finished_at=utcnow(), actual_cost_usd=0.02),
            AnalysisRun(title_id=title.id, app_id=APP, kind="analysis", status="estimated", trigger="nightly", reviews_in_scope=400, est_cost_usd=0.9),
        ]
    )
    session.commit()
    alerts = check_alerts(session, settings)
    assert sorted(a.kind for a in alerts) == ["analysis_failed", "needs_confirmation"]
    waiting = next(a for a in alerts if a.kind == "needs_confirmation")
    assert "$0.90" in waiting.body and "$0.50" in waiting.body
    assert all(a.channels == [] and a.error is None for a in alerts)  # stored even with no channel set up


def seed_history(session, title, *, old_positive, old_negative, new_negative):
    """Reviews from before the alert window, then a run of recent negative ones."""
    old = int((utcnow() - timedelta(days=20)).timestamp())
    recent = int((utcnow() - timedelta(days=2)).timestamp())
    raws = [make_review(1000 + i, old + i, voted_up=True) for i in range(old_positive)]
    raws += [make_review(2000 + i, old + i, voted_up=False) for i in range(old_negative)]
    raws += [make_review(3000 + i, recent + i, voted_up=False) for i in range(new_negative)]
    upsert_reviews(session, title.id, APP, raws, seen_at=utcnow())
    session.commit()


def test_drop_in_recommended(session, settings, title):
    seed_history(session, title, old_positive=36, old_negative=4, new_negative=6)  # 90% then, 78% now
    (alert,) = check_alerts(session, settings)
    assert alert.kind == "positive_drop" and "fell 12 points in 7 days" in alert.subject
    assert "from 90% to 78%" in alert.body
    assert check_alerts(session, settings) == []  # once a week per title
    assert len(check_alerts(session, settings, now=utcnow() + timedelta(days=7))) <= 1


def test_small_drops_and_small_titles_stay_quiet(session, settings, title):
    seed_history(session, title, old_positive=36, old_negative=4, new_negative=1)  # 90% to 88%
    assert check_alerts(session, settings) == []
    other = Title(name="Tiny", steam_app_id=999, status="released")
    session.add(other)
    session.commit()
    old = int((utcnow() - timedelta(days=20)).timestamp())
    upsert_reviews(session, other.id, 999, [make_review(5000 + i, old + i) for i in range(5)] + [make_review(5100, int(utcnow().timestamp()) - 60, voted_up=False)], seen_at=utcnow())
    session.commit()
    assert check_alerts(session, settings) == []  # 5 reviews is too few to judge


def test_delivery_failure_is_recorded(session, settings, title, channels):
    failed_sync(session, title)
    with respx.mock() as mock:
        mock.post(HOOK).mock(return_value=httpx.Response(500))
        (alert,) = check_alerts(session, settings)
    assert alert.channels == ["email"] and alert.error.startswith("Slack:")
    assert session.get(Alert, alert.id).error


def test_alerts_api(api, session, settings, channels):
    failed_sync(session, session.get(Title, 1))
    with respx.mock() as mock:
        mock.post(HOOK).mock(return_value=httpx.Response(200))
        check_alerts(session, settings)
        test = api.post("/api/alerts/test").json()
    assert test["kind"] == "test" and test["channels"] == ["slack", "email"]
    listed = api.get("/api/alerts").json()
    assert listed["channels"] == {"slack": True, "email": True}
    assert [a["kind"] for a in listed["alerts"]] == ["test", "sync_failed"] and listed["alerts"][1]["title_name"] == "Tombwater"
