"""The portfolio overview, filter options, and the compare view with theme matching."""

from datetime import timedelta

import pytest

from app.models import ReviewSnapshot, Title
from app.steam.sync import upsert_reviews
from app.timeutil import utcnow
from tests.fakes import make_review
from tests.test_api_analysis import drain
from tests.test_pipeline import TEXTS

DUCK = 2058150


def seed(session, title_id, app_id, start=10_000, count=63):
    title = session.get(Title, title_id)
    raws = [
        make_review(start + i, 1_760_000_000 + i * 86_400, voted_up=TEXTS[i % 7][1], text=TEXTS[i % 7][0], language=TEXTS[i % 7][2])
        for i in range(count)
    ]
    upsert_reviews(session, title.id, app_id, raws, seen_at=utcnow())
    session.commit()


def analyze(api, session_factory, settings, fake_llm, title_id):
    est = api.post(f"/api/titles/{title_id}/analysis/estimate", json={"kind": "discovery"}).json()
    api.post(f"/api/analysis-runs/{est['id']}/confirm")
    drain(session_factory, settings, fake_llm)
    cb = api.get(f"/api/titles/{title_id}/codebooks").json()[0]
    api.post(f"/api/codebooks/{cb['id']}/approve")
    est = api.post(f"/api/titles/{title_id}/analysis/estimate", json={"kind": "analysis"}).json()
    api.post(f"/api/analysis-runs/{est['id']}/confirm")
    drain(session_factory, settings, fake_llm)
    assert api.get(f"/api/analysis-runs/{est['id']}").json()["status"] == "succeeded"


def test_portfolio_cards(api, session, session_factory, settings, fake_llm):
    seed(session, 1, 3308200)
    analyze(api, session_factory, settings, fake_llm, 1)
    now = utcnow()
    ts = lambda days: int((now - timedelta(days=days)).timestamp())  # noqa: E731
    recent = [
        make_review(500, ts(5), text="Great fun."),
        make_review(501, ts(10), text="Too hard for me.", voted_up=False),
        make_review(502, ts(20), text="Lovely ducks."),
        make_review(503, ts(40), text="Okay I guess.", voted_up=False),
        make_review(504, ts(45), text="Pretty good."),
    ]
    upsert_reviews(session, 2, DUCK, recent, seen_at=now)
    session.add(ReviewSnapshot(title_id=2, app_id=DUCK, snapshot_date=now.date(), total_reviews=5, total_positive=3, total_negative=2, review_score=6, review_score_desc="Mostly Positive"))
    session.commit()

    cards = {c["id"]: c for c in api.get("/api/portfolio").json()["titles"]}
    assert len(cards) == 8

    tomb = cards[1]
    assert tomb["reviews"] == 63 and tomb["positive_share"] == pytest.approx(45 / 63)
    themes = tomb["themes"]
    assert themes["analyzed"] == 54 and themes["codebook_version"] == 1
    assert themes["top_praised"]["positive"] == 27 and themes["top_praised"]["negative"] == 0
    assert themes["top_criticized"]["key"] == "bugs_crashes" and themes["top_criticized"]["negative"] == 9
    assert themes["top_criticized"]["share"] == pytest.approx(9 / 54)

    duck = cards[2]
    assert duck["themes"] is None  # no approved codebook yet
    assert duck["steam"]["review_score_desc"] == "Mostly Positive"
    assert duck["trend"]["last"] == {"reviews": 3, "positive_share": pytest.approx(2 / 3)}
    assert duck["trend"]["previous"] == {"reviews": 2, "positive_share": 0.5}
    assert len(duck["weekly"]) == 12 and sum(w["reviews"] for w in duck["weekly"]) == 5
    assert duck["weekly"][-1]["reviews"] == 1  # the review from 5 days ago

    baboo = cards[7]
    assert baboo["reviews"] == 0 and baboo["positive_share"] is None and baboo["status"] == "unreleased"
    assert cards[6]["demo"]["app_id"] == 3673170  # GodsTV's demo is reported on its own


def test_facets(api, session):
    seed(session, 1, 3308200, count=14)
    f = api.get("/api/titles/1/facets").json()
    assert f["total"] == 14 and f["date_min"] < f["date_max"]
    assert {lang["code"]: lang["count"] for lang in f["languages"]} == {"english": 12, "schinese": 2}
    assert [b["band"] for b in f["playtime_bands"]] == ["lt2h", "2to10h", "10to50h", "50h_plus", "unknown"]
    assert sum(b["count"] for b in f["playtime_bands"]) == 14
    assert api.get("/api/titles/1/facets", params={"app_id": 999}).status_code == 400


def test_compare_and_theme_matching(api, session, session_factory, settings, fake_llm):
    seed(session, 1, 3308200)
    seed(session, 2, DUCK, start=20_000)
    seed(session, 3, 2545740, start=30_000, count=10)
    analyze(api, session_factory, settings, fake_llm, 1)
    analyze(api, session_factory, settings, fake_llm, 2)

    resp = api.get("/api/compare", params={"title_id": [1, 2, 3]}).json()
    assert [t["id"] for t in resp["titles"]] == [1, 2, 3]
    tomb, duck, hive = resp["titles"]
    assert tomb["reviews"] == 63 and tomb["analyzed"] == 54 and len(tomb["themes"]) == 4
    assert hive["analyzed"] == 0 and hive["themes"] == [] and hive["overall"] is None
    assert sum(m["reviews"] for m in tomb["months"]) == 63
    tm = resp["theme_match"]
    assert tm["status"] == "not_matched" and tm["eligible_title_ids"] == [1, 2] and tm["match"] is None

    # Estimating is free: tokens are counted, nothing is sent for an answer.
    calls = len(fake_llm.calls)
    est = api.post("/api/compare/theme-match/estimate", json={"title_ids": [1, 2, 3]}).json()
    assert est["cost_usd"] > 0 and est["title_ids"] == [1, 2] and est["model"] == settings.model_analysis
    assert len(fake_llm.calls) == calls

    match = api.post("/api/compare/theme-match", json={"title_ids": [1, 2, 3]}).json()
    assert len(fake_llm.calls) == calls + 1
    names = [g["name"] for g in match["groups"]]
    assert names == ["Combat, shared", "Price, shared", "Bugs, shared", "Art, shared"]  # em dashes removed
    assert all(set(g["themes"]) == {"1", "2"} for g in match["groups"])  # bad and one-game groups dropped
    assert match["cost_usd"] > 0

    again = api.get("/api/compare", params={"title_id": [2, 1]}).json()["theme_match"]
    assert again["status"] == "ready" and again["match"]["groups"] == match["groups"]

    # A new approved codebook on one title means the match is out of date: first that title
    # needs analyzing under it, then the themes can be matched again.
    cb = api.get("/api/titles/1/codebooks").json()[0]
    full = api.get(f"/api/codebooks/{cb['id']}").json()
    v2 = api.post("/api/titles/1/codebooks", json={"parent_id": cb["id"], "note": "edit", "themes": full["themes"][:3]}).json()
    api.post(f"/api/codebooks/{v2['id']}/approve")
    assert api.get("/api/compare", params={"title_id": [1, 2]}).json()["theme_match"]["status"] == "not_enough"
    est = api.post("/api/titles/1/analysis/estimate", json={"kind": "analysis"}).json()
    api.post(f"/api/analysis-runs/{est['id']}/confirm")
    drain(session_factory, settings, fake_llm)
    assert api.get("/api/compare", params={"title_id": [1, 2]}).json()["theme_match"]["status"] == "not_matched"


def test_compare_needs_two_to_four_titles(api, session):
    assert api.get("/api/compare", params={"title_id": [1]}).status_code == 400
    assert api.get("/api/compare", params={"title_id": [1, 2, 3, 4, 5]}).status_code == 400
    assert api.get("/api/compare", params={"title_id": [1, 99]}).status_code == 404
    resp = api.get("/api/compare", params={"title_id": [1, 2]}).json()
    assert resp["theme_match"]["status"] == "not_enough"
    assert api.post("/api/compare/theme-match/estimate", json={"title_ids": [1, 2]}).status_code == 400
