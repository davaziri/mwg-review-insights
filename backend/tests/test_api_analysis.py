"""The analysis API as the UI uses it: estimate, confirm, review the codebook, analyze, inspect."""

from app.analysis.runs import process_analysis
from tests.test_pipeline import APP, seed_reviews


def drain(session_factory, settings, fake_llm):
    for _ in range(10):
        process_analysis(session_factory, settings, lambda: fake_llm)


def test_analysis_flow_through_the_api(api, session, session_factory, settings, fake_llm):
    from app.models import Title

    seed_reviews(session, session.get(Title, 1))
    overview = api.get("/api/titles/1/analysis").json()
    assert overview["reviews"] == {"total": 63, "with_content": 54, "no_content": 9, "not_prepared": 0, "pending": None}
    assert overview["approved_codebook"] is None

    # Analysis is refused until a codebook is approved.
    resp = api.post("/api/titles/1/analysis/estimate", json={"kind": "analysis"})
    assert resp.status_code == 400 and "Approve a codebook" in resp.json()["detail"]

    # Discovery: estimate, confirm, run.
    est = api.post("/api/titles/1/analysis/estimate", json={"kind": "discovery"}).json()
    assert est["status"] == "estimated" and est["est_cost_usd"] > 0
    assert "sample_review_ids" not in est["details"]  # large id lists stay server-side
    assert api.post(f"/api/analysis-runs/{est['id']}/confirm").json()["status"] == "queued"
    assert api.post(f"/api/analysis-runs/{est['id']}/confirm").status_code == 409
    drain(session_factory, settings, fake_llm)
    run = api.get(f"/api/analysis-runs/{est['id']}").json()
    assert run["status"] == "succeeded" and run["actual_cost_usd"] > 0

    # Review the proposed codebook: rename one theme, drop another, save as v2 and approve.
    draft = api.get(f"/api/codebooks/{run['codebook_id']}").json()
    assert draft["status"] == "draft" and draft["theme_count"] == 4
    assert draft["examples"]  # example reviews come back with text for the reviewer
    themes = [t for t in draft["themes"] if t["key"] != "art_style"]
    themes[0] = {**themes[0], "name": "How combat feels", "derived_from": [{"key": themes[0]["key"], "op": "renamed"}]}
    v2 = api.post("/api/titles/1/codebooks", json={"parent_id": draft["id"], "note": "Renamed, dropped art", "themes": themes}).json()
    assert (v2["version"], v2["status"], v2["theme_count"]) == (2, "draft", 3)
    assert api.post(f"/api/codebooks/{v2['id']}/approve").json()["status"] == "approved"
    versions = api.get("/api/titles/1/codebooks").json()
    assert [(c["version"], c["status"]) for c in versions] == [(2, "approved"), (1, "draft")]

    # Analysis.
    est = api.post("/api/titles/1/analysis/estimate", json={"kind": "analysis"}).json()
    assert [s["step"] for s in est["estimate"]["steps"]] == ["tagging", "qa", "summary"]
    assert est["reviews_in_scope"] == 54
    api.post(f"/api/analysis-runs/{est['id']}/confirm")
    drain(session_factory, settings, fake_llm)
    assert api.get(f"/api/analysis-runs/{est['id']}").json()["status"] == "succeeded"
    assert api.get("/api/titles/1/analysis").json()["reviews"]["pending"] == 0

    # Stats, with and without filters.
    stats = api.get("/api/titles/1/themes/stats").json()
    assert stats["codebook"]["version"] == 2 and stats["counts"]["analyzed"] == 54
    assert {t["key"] for t in stats["themes"]} == {"combat_feel", "price_value", "bugs_crashes"}
    combat = next(t for t in stats["themes"] if t["key"] == "combat_feel")
    assert combat["name"] == "How combat feels" and combat["mentions"] > 0
    negative = api.get("/api/titles/1/themes/stats", params={"vote": "negative"}).json()
    assert negative["counts"]["reviews"] < stats["counts"]["reviews"]
    german = api.get("/api/titles/1/themes/stats", params={"language": ["schinese"]}).json()
    assert german["counts"]["analyzed"] == 9

    # Spot check: 20 random tagged reviews with quote positions inside the text.
    spot = api.get("/api/titles/1/reviews/tagged", params={"random": 20}).json()
    assert spot["total"] == 54 and len(spot["reviews"]) == 20
    for r in spot["reviews"]:
        assert r["url"].startswith("https://steamcommunity.com/profiles/") and f"/recommended/{APP}/" in r["url"]
        for m in r["mentions"]:
            if m["quote_status"] == "ok":
                assert r["text"][m["quote_start"] : m["quote_end"]].strip()
        o = r["overall"]
        assert o["sentiment"] in ("positive", "negative", "mixed", "none")
        if o["quote_status"] == "ok":
            assert r["text"][o["quote_start"] : o["quote_end"]].strip()
    assert stats["overall"]["positive"]["count"] == 9

    # Drill-down by overall impression.
    positive = api.get("/api/titles/1/reviews/tagged", params={"overall": "positive"}).json()
    assert positive["total"] == 9 and all(r["overall"]["sentiment"] == "positive" for r in positive["reviews"])
    assert api.get("/api/titles/1/reviews/tagged", params={"overall": "none"}).json()["total"] == 27

    # Drill-down: one theme, one sentiment.
    neg_combat = api.get("/api/titles/1/reviews/tagged", params={"theme": "combat_feel", "sentiment": "negative"}).json()
    assert neg_combat["total"] > 0
    assert all(any(m["theme_key"] == "combat_feel" and m["sentiment"] == "negative" for m in r["mentions"]) for r in neg_combat["reviews"])
    assert api.get("/api/titles/1/reviews/tagged", params={"theme": "nope"}).status_code == 400

    # Summary with cited reviews resolved for display.
    summary = api.get("/api/titles/1/summary").json()
    cited = summary["content"]["strengths"][0]["review_ids"]
    assert cited and all(i in summary["cited_reviews"] for i in cited)

    # Quality page.
    quality = api.get("/api/titles/1/quality").json()
    assert quality["qa"]["reviews_checked"] == 20
    assert quality["quotes"]["verified"] > 0 and quality["analyzed_reviews"] == 54
    assert [r["kind"] for r in quality["runs"]] == ["analysis", "discovery"]


def test_cancel_an_estimate(api, session, fake_llm):
    from app.models import Title

    seed_reviews(session, session.get(Title, 1))
    est = api.post("/api/titles/1/analysis/estimate", json={"kind": "discovery"}).json()
    assert api.post(f"/api/analysis-runs/{est['id']}/cancel").json()["status"] == "canceled"
    assert api.post(f"/api/analysis-runs/{est['id']}/confirm").status_code == 409


def test_demo_app_is_its_own_scope(api, session):
    resp = api.post("/api/titles/6/analysis/estimate", json={"kind": "discovery", "app_id": 999})
    assert resp.status_code == 400 and "does not belong" in resp.json()["detail"]
    overview = api.get("/api/titles/6/analysis", params={"app_id": 3673170}).json()
    assert overview["app_id"] == 3673170
