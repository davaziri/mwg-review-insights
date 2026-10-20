"""Browsing and searching reviews: filters, search in any language, paging, and tags once analyzed."""

from app.models import Title
from app.steam.sync import upsert_reviews
from app.timeutil import utcnow
from tests.fakes import make_review
from tests.test_api_analysis import drain
from tests.test_pipeline import APP, seed_reviews

DAY = 86_400
T0 = 1_760_000_000


def add(session, reviews):
    upsert_reviews(session, 1, APP, reviews, seen_at=utcnow())
    session.commit()


def ids(resp):
    return [r["recommendation_id"] for r in resp["reviews"]]


def test_search_matches_words_phrases_and_any_language(api, session):
    add(
        session,
        [
            make_review(1, T0, text="The COMBAT is tight. Love the [b]boss fights[/b]."),
            make_review(2, T0 + DAY, text="Combat feels floaty and the price is too high."),
            make_review(3, T0 + 2 * DAY, text="战斗系统很棒。画面也不错。", language="schinese"),
            make_review(4, T0 + 3 * DAY, text="good", voted_up=False),
            make_review(5, T0 + 4 * DAY, text="100% worth it, 10/10"),
        ],
    )

    def search(q, **params):
        return api.get("/api/titles/1/reviews", params={"q": q, **params}).json()

    hit = search("combat")
    assert ids(hit) == ["2", "1"]  # newest first, any letter case
    first = next(r for r in hit["reviews"] if r["recommendation_id"] == "1")
    assert first["text"] == "The COMBAT is tight. Love the boss fights."  # markup removed
    assert first["matches"] == [[4, 10]] and first["text"][4:10] == "COMBAT"
    assert ids(search("combat boss")) == ["1"]  # every word must match
    assert ids(search('"the price is"')) == ["2"]  # quoted phrase
    assert ids(search("战斗系统")) == ["3"]  # Chinese, through the index
    assert ids(search("画面")) == ["3"]  # two characters: plain substring match
    assert ids(search("100%")) == ["5"]  # % is not a wildcard
    assert search("nothing like this")["total"] == 0
    assert search("combat", vote="negative")["total"] == 0  # filters still apply

    # Edits are searchable right away.
    add(session, [make_review(2, T0 + DAY, updated=T0 + 9 * DAY, text="Patched. Movement is smooth now.")])
    assert ids(search("combat")) == ["1"] and ids(search("smooth")) == ["2"]


def test_listing_filters_sorts_and_pages(api, session):
    add(session, [make_review(100 + i, T0 + i * DAY, voted_up=i % 3 != 0, text=f"Review number {i} is fun.", votes_up=i) for i in range(25)])

    page1 = api.get("/api/titles/1/reviews", params={"page_size": 10}).json()
    assert page1["total"] == 25 and len(page1["reviews"]) == 10 and ids(page1)[0] == "124"
    page3 = api.get("/api/titles/1/reviews", params={"page_size": 10, "page": 3}).json()
    assert len(page3["reviews"]) == 5
    assert ids(api.get("/api/titles/1/reviews", params={"sort": "oldest", "page_size": 1}).json()) == ["100"]
    assert ids(api.get("/api/titles/1/reviews", params={"sort": "helpful", "page_size": 1}).json()) == ["124"]
    negative = api.get("/api/titles/1/reviews", params={"vote": "negative"}).json()
    assert negative["total"] == 9 and all(not r["voted_up"] for r in negative["reviews"])
    recent = api.get("/api/titles/1/reviews", params={"date_from": "2025-10-20"}).json()
    assert recent["total"] < 25
    one = page1["reviews"][0]
    assert one["tagged"] is False and one["overall"] is None and one["mentions"] == []
    assert api.get("/api/titles/1/reviews", params={"theme": "combat_feel"}).json()["total"] == 0  # no codebook yet


def test_tags_show_once_analyzed(api, session, session_factory, settings, fake_llm):
    seed_reviews(session, session.get(Title, 1))
    est = api.post("/api/titles/1/analysis/estimate", json={"kind": "discovery"}).json()
    api.post(f"/api/analysis-runs/{est['id']}/confirm")
    drain(session_factory, settings, fake_llm)
    cb = api.get("/api/titles/1/codebooks").json()[0]
    api.post(f"/api/codebooks/{cb['id']}/approve")
    est = api.post("/api/titles/1/analysis/estimate", json={"kind": "analysis"}).json()
    api.post(f"/api/analysis-runs/{est['id']}/confirm")
    drain(session_factory, settings, fake_llm)

    everything = api.get("/api/titles/1/reviews", params={"page_size": 100}).json()
    assert everything["total"] == 63
    by_status = {(r["content_status"], r["tagged"]) for r in everything["reviews"]}
    assert by_status == {("ok", True), ("no_content", False)}
    assert api.get("/api/titles/1/reviews", params={"content": "no_content"}).json()["total"] == 9

    combat = api.get("/api/titles/1/reviews", params={"theme": "combat_feel", "sentiment": "negative", "page_size": 100}).json()
    assert combat["total"] > 0
    for r in combat["reviews"]:
        m = next(m for m in r["mentions"] if m["theme_key"] == "combat_feel")
        assert m["sentiment"] == "negative"
        if m["quote_status"] == "ok":
            assert r["text"][m["quote_start"] : m["quote_end"]].strip()
    assert api.get("/api/titles/1/reviews", params={"overall": "positive"}).json()["total"] == 9
    # Search and theme together.
    both = api.get("/api/titles/1/reviews", params={"theme": "price_value", "q": "fair"}).json()
    assert both["total"] == 9 and all("fair" in r["text"] for r in both["reviews"])
