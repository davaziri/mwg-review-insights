"""Nightly analysis: only titles switched on, only new reviews, under the nightly limit."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.analysis.nightly import expected_monthly_cost, nightly_analysis
from app.analysis.runs import confirm, estimate_analysis
from app.models import AnalysisRun, Summary, SyncRun
from app.steam.sync import upsert_reviews
from app.timeutil import utcnow
from tests.fake_llm import FakeLLM
from tests.fakes import make_review
from tests.test_pipeline import APP, discover_and_approve, run_until_done, seed_reviews


@pytest.fixture
def llm():
    return FakeLLM()


@pytest.fixture
def analyzed(session, session_factory, settings, llm, title):
    seed_reviews(session, title)
    discover_and_approve(session, session_factory, settings, llm, title)
    confirm(session, estimate_analysis(session, settings, llm, title, APP))
    run_until_done(session_factory, settings, llm)
    title.auto_analyze = True
    session.commit()
    return title


def add_new_reviews(session, title, count=2, start=90_000, spacing=3600):
    now = int(utcnow().timestamp())
    raws = [make_review(start + i, now - spacing * (i + 1), text=f"New review {i}: the combat is fun and the art is great.") for i in range(count)]
    upsert_reviews(session, title.id, APP, raws, seen_at=utcnow())
    session.commit()


def runs(session, **where):
    query = select(AnalysisRun).where(AnalysisRun.kind == "analysis")
    for key, value in where.items():
        query = query.where(getattr(AnalysisRun, key) == value)
    return session.scalars(query.order_by(AnalysisRun.id)).all()


def test_nothing_new_means_no_run(session, settings, llm, analyzed):
    assert nightly_analysis(session, settings, llm) == []
    assert runs(session, trigger="nightly") == []


def test_new_reviews_are_tagged_without_qa_or_a_fresh_summary(session, session_factory, settings, llm, analyzed):
    full_qa = runs(session)[-1].details["qa"]
    add_new_reviews(session, analyzed)
    report = nightly_analysis(session, settings, llm)
    assert len(report) == 1 and "started, 2 reviews" in report[0]
    (run,) = runs(session, trigger="nightly")
    assert (run.status, run.requested_by, run.reviews_in_scope) == ("queued", "nightly", 2)
    assert run.confirmed_by.startswith("nightly (under the $0.50 limit)")
    assert [s["step"] for s in run.estimate["steps"]] == ["tagging"]  # no QA for 2 reviews, summary is recent
    summaries = session.scalar(select(func.count()).select_from(Summary))

    run_until_done(session_factory, settings, llm)
    session.refresh(run)
    assert run.status == "succeeded" and run.reviews_tagged == 2
    assert "qa" not in run.details and set(run.usage) == {"tagging"}
    assert session.scalar(select(func.count()).select_from(Summary)) == summaries
    # The quality page keeps showing the last real quality check.
    assert runs(session)[0].details["qa"] == full_qa


def test_summary_is_rewritten_once_it_is_old(session, session_factory, settings, llm, analyzed):
    add_new_reviews(session, analyzed)
    nightly_analysis(session, settings, llm, now=utcnow() + timedelta(days=8))
    (run,) = runs(session, trigger="nightly")
    assert [s["step"] for s in run.estimate["steps"]] == ["tagging", "summary"]
    run_until_done(session_factory, settings, llm)
    assert session.scalar(select(func.count()).select_from(Summary)) == 2


def test_enough_new_reviews_get_a_quality_check(session, settings, llm, analyzed):
    add_new_reviews(session, analyzed, count=settings.qa_min_reviews)
    nightly_analysis(session, settings, llm)
    (run,) = runs(session, trigger="nightly")
    assert [s["step"] for s in run.estimate["steps"]] == ["tagging", "qa"]


def test_over_the_limit_waits_for_an_admin(session, settings, llm, analyzed):
    settings.nightly_analysis_max_usd = 0.0
    add_new_reviews(session, analyzed)
    report = nightly_analysis(session, settings, llm)
    assert "waiting for an admin" in report[0]
    (run,) = runs(session, trigger="nightly")
    assert run.status == "estimated" and run.confirmed_at is None and "Needs an admin" in run.warning


def test_only_titles_switched_on_and_not_while_syncing(session, settings, llm, analyzed):
    add_new_reviews(session, analyzed)
    analyzed.auto_analyze = False
    session.commit()
    assert nightly_analysis(session, settings, llm) == []
    analyzed.auto_analyze = True
    session.add(SyncRun(title_id=analyzed.id, app_id=APP, mode="incremental", trigger="schedule", status="running"))
    session.commit()
    assert "sync is still running" in nightly_analysis(session, settings, llm)[0]
    assert runs(session, trigger="nightly") == []


def test_expected_monthly_cost(session, settings, llm, analyzed, api):
    add_new_reviews(session, analyzed, count=6, spacing=86_400 * 2)  # one review every other day
    forecast = expected_monthly_cost(session, settings, analyzed)
    assert forecast["enabled"] is True and forecast["reviews_last_30_days"] == 6
    assert forecast["summaries_per_month"] == pytest.approx(30 / settings.summary_refresh_days, abs=0.05)
    assert 0 < forecast["expected_monthly_usd"] < 1
    # Through the API, and the switch itself.
    assert api.patch("/api/titles/1", json={"auto_analyze": False}).json()["auto_analyze"] is False
    assert api.get("/api/titles/1/auto-analysis").json()["enabled"] is False
