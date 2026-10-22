"""Language check and translation: a review's language is the one its text is written in, not the
reviewer's Steam setting, and reviews not in English get an English translation."""

import csv
import io

import pytest
from sqlalchemy import select

from app.analysis.runs import RunError, confirm, estimate_translation, process_analysis
from app.analysis.translation import resolve_language, unchecked_reviews
from app.models import Review, Title
from app.steam.sync import upsert_reviews
from app.timeutil import utcnow
from tests.fakes import make_review
from tests.test_api_analysis import drain
from tests.test_pipeline import APP

T0 = 1_760_000_000
DAY = 86_400

REVIEWS = [
    make_review(1, T0, text="friggin love this game, the only bullet hell I know", language="spanish"),  # English; Steam says Spanish
    make_review(2, T0 + DAY, text="El juego es entretenido, pero los controles no", language="english"),  # Spanish; Steam says English
    make_review(3, T0 + 2 * DAY, text="esta mejorado y muy entretenido", language="spanish"),  # Spanish, as Steam says
    make_review(4, T0 + 3 * DAY, text="战斗系统很棒。画面也不错。", language="schinese"),
    make_review(5, T0 + 4 * DAY, text="10/10", language="russian"),  # no language to speak of
    make_review(6, T0 + 5 * DAY, text="", language="german"),  # no text at all
    make_review(7, T0 + 6 * DAY, text="...!!", language="koreana"),  # no words
]


def add(session, reviews):
    upsert_reviews(session, 1, APP, reviews, seen_at=utcnow())
    session.commit()


def check_languages(session, session_factory, settings, llm):
    run = estimate_translation(session, settings, llm, session.get(Title, 1), APP)
    confirm(session, run)
    for _ in range(5):
        process_analysis(session_factory, settings, lambda: llm)
    session.expire_all()
    return session.get(type(run), run.id)


def by_id(api, **params) -> dict[str, dict]:
    return {r["recommendation_id"]: r for r in api.get("/api/titles/1/reviews", params=params).json()["reviews"]}


def test_steam_varieties_are_kept_when_the_text_agrees():
    assert resolve_language("english", "spanish") == "english"
    assert resolve_language("spanish", "english") == "spanish"
    assert resolve_language("latam", "spanish") == "spanish"  # the text can't tell Spain from Mexico
    assert resolve_language("brazilian", "portuguese") == "portuguese"
    assert resolve_language("tchinese", "schinese") == "schinese"
    assert resolve_language("other", "english") == "other"
    assert resolve_language("none", "russian") is None


def test_languages_are_checked_and_translated(api, session, session_factory, settings, fake_llm):
    add(session, REVIEWS)
    status = api.get("/api/titles/1/languages").json()
    assert (status["unchecked"], status["translated"], status["active_run"]) == (6, 0, None)  # the review with no text is skipped

    est = api.post("/api/titles/1/analysis/estimate", json={"kind": "translation"}).json()
    assert [s["step"] for s in est["estimate"]["steps"]] == ["translation"]
    assert est["kind"] == "translation" and est["reviews_in_scope"] == 6 and est["est_cost_usd"] > 0
    assert fake_llm.calls == []  # nothing is sent before an admin confirms
    api.post(f"/api/analysis-runs/{est['id']}/confirm")
    drain(session_factory, settings, fake_llm)

    run = api.get(f"/api/analysis-runs/{est['id']}").json()
    assert run["status"] == "succeeded" and run["reviews_failed"] == 0
    assert run["details"]["translation"] == {"planned": 6, "checked": 6, "translated": 3}
    assert "translate_review_ids" not in run["details"] and run["usage"]["translation"]["cost_usd"] > 0

    reviews = by_id(api)
    assert (reviews["1"]["language"], reviews["1"]["steam_language"], reviews["1"]["text_en"]) == ("english", "spanish", None)
    assert reviews["2"]["language"] == "latam" and reviews["2"]["text_en"].startswith("[English] El juego es entretenido")
    assert "—" not in reviews["2"]["text_en"]  # house style applies to translations too
    assert (reviews["3"]["language"], reviews["3"]["text_en"] is not None) == ("spanish", True)  # Steam's variety kept
    assert (reviews["4"]["language"], reviews["4"]["text_en"] is not None) == ("schinese", True)
    assert (reviews["5"]["language"], reviews["5"]["text_en"]) == ("russian", None)  # nothing to translate; Steam's setting stays
    assert (reviews["7"]["language"], reviews["7"]["text_en"]) == ("koreana", None)  # no words, nothing to translate
    assert all(reviews[k]["language_checked"] for k in "123457") and not reviews["6"]["language_checked"]

    # Filters and the filter bar go by the language the text is written in.
    assert set(by_id(api, language="english")) == {"1"}
    assert set(by_id(api, language="spanish")) == {"3"}
    facets = {f["code"]: f["count"] for f in api.get("/api/titles/1/facets").json()["languages"]}
    assert facets == {"english": 1, "latam": 1, "spanish": 1, "schinese": 1, "russian": 1, "german": 1, "koreana": 1}

    # Exports carry both languages and the translation.
    rows = list(csv.reader(io.StringIO(api.get("/api/titles/1/export.csv").content.decode("utf-8-sig"))))
    header, body = rows[0], {r[0]: r for r in rows[1:]}
    lang, steam, english = header.index("Language"), header.index("Steam language setting"), header.index("English translation (machine-written)")
    assert (body["1"][lang], body["1"][steam], body["1"][english]) == ("English", "Spanish (Spain)", "")
    assert body["2"][lang] == "Spanish (Latin America)" and body["2"][english].startswith("[English] El juego")

    assert api.get("/api/titles/1/languages").json() == {"app_id": APP, "unchecked": 0, "translated": 3, "active_run": None}
    again = api.post("/api/titles/1/analysis/estimate", json={"kind": "translation"})
    assert again.status_code == 400 and "already" in again.json()["detail"]


def test_an_edited_review_is_checked_again(session, session_factory, settings, fake_llm, title):
    add(session, REVIEWS)
    check_languages(session, session_factory, settings, fake_llm)
    add(session, [make_review(2, T0 + DAY, updated=T0 + 9 * DAY, text="Patched, now I love it.", language="english")])

    edited = session.scalar(select(Review).where(Review.recommendation_id == "2"))
    assert (edited.text_language, edited.text_en) == (None, None)  # the old translation was of the old text
    assert [r.recommendation_id for r in unchecked_reviews(session, 1, APP)] == ["2"]
    run = check_languages(session, session_factory, settings, fake_llm)
    assert run.reviews_in_scope == 1 and run.status == "succeeded"
    session.refresh(edited)
    assert (edited.effective_language, edited.text_en) == ("english", None)
    with pytest.raises(RunError):
        estimate_translation(session, settings, fake_llm, session.get(Title, 1), APP)


def test_a_review_left_untranslated_is_tried_again_alone_then_left_for_later(session, session_factory, settings, fake_llm, title):
    add(session, REVIEWS)
    fake_llm.untranslated_ids = {"2"}  # the model keeps leaving out this translation
    fake_llm.omit_ids = {"4"}  # left out of its group, fine on its own
    fake_llm.copied_ids = {"3"}  # the original text sent back as its translation, fine on its own
    run = check_languages(session, session_factory, settings, fake_llm)

    assert run.status == "succeeded" and run.reviews_failed == 1
    assert run.details["translation"] == {"planned": 6, "checked": 5, "translated": 2}
    assert len(run.details["retried_translation_ids"]) == 3
    copied = session.scalar(select(Review).where(Review.recommendation_id == "3"))
    assert copied.text_en.startswith("[English] ")  # the copy was refused and the retry stored a real one
    assert [r.recommendation_id for r in unchecked_reviews(session, 1, APP)] == ["2"]  # next run tries again


def test_analysis_checks_languages_first(session, session_factory, settings, fake_llm, title):
    """The tagging model sees the language the review is written in, not the Steam setting."""
    from tests.test_pipeline import discover_and_approve, seed_reviews

    seed_reviews(session, title)
    add(session, [make_review(99, T0, text="El juego es muy bueno, me gusta la musica", language="english")])
    discover_and_approve(session, session_factory, settings, fake_llm, title)

    from app.analysis.runs import estimate_analysis

    run = estimate_analysis(session, settings, fake_llm, title, APP)
    assert [s["step"] for s in run.estimate["steps"]][0] == "translation"
    confirm(session, run)
    for _ in range(10):
        process_analysis(session_factory, settings, lambda: fake_llm)
    session.refresh(run)
    assert run.status == "succeeded", run.error
    tagging = next(c for c in fake_llm.calls if "Tag each of these reviews" in c.user and 'id="99"' in c.user)
    assert 'id="99" vote="recommended" language="latam"' in tagging.user
