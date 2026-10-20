"""The analysis pipeline end to end, against a fake LLM: estimate, confirm, discovery, codebook
editing and approval, tagging, QA, aggregation and summary."""

import pytest
from sqlalchemy import func, select

from app.analysis import runs
from app.analysis.codebooks import ThemeInput, approve, approved_codebook, create_version, themes_for
from app.analysis.runs import RunError, confirm, estimate_analysis, estimate_discovery, process_analysis
from app.models import AnalysisRun, Codebook, QAResult, Review, ReviewTag, Summary, ThemeMention
from app.steam.sync import upsert_reviews
from app.timeutil import utcnow
from tests.fake_llm import FakeLLM
from tests.fakes import make_review

APP = 3308200
TEXTS = [
    ("The combat feels tight and fun. Great art style too. Great game, I recommend it.", True, "english"),
    ("Combat is awful and boring. The price is fair though. Amazing idea but do not buy yet.", False, "english"),
    ("Crashes every hour, so many bugs. Not worth the money. Do not buy.", False, "english"),
    ("Love the visuals! The price is right for what you get.", True, "english"),
    ("战斗系统很棒。画面也不错。", True, "schinese"),
    ("good", True, "english"),  # no content
    ("Fights are fun and the art is gorgeous.", True, "english"),
]


def seed_reviews(session, title, count=63, start=10_000):
    raws = []
    for i in range(count):
        text, up, lang = TEXTS[i % len(TEXTS)]
        raws.append(make_review(start + i, 1_760_000_000 + i * 86_400, voted_up=up, text=text, language=lang))
    upsert_reviews(session, title.id, APP, raws, seen_at=utcnow())
    session.commit()
    return raws


@pytest.fixture
def llm():
    return FakeLLM()


@pytest.fixture
def seeded(session, title):
    seed_reviews(session, title)
    return title


def run_until_done(session_factory, settings, llm, max_passes=20):
    for _ in range(max_passes):
        process_analysis(session_factory, settings, lambda: llm)
        with session_factory() as s:
            if not s.scalar(select(func.count()).select_from(AnalysisRun).where(AnalysisRun.status.in_(["queued", "running"]))):
                return
    raise AssertionError("analysis did not finish")


def discover_and_approve(session, session_factory, settings, llm, title) -> Codebook:
    run = estimate_discovery(session, settings, llm, title, APP)
    confirm(session, run)
    run_until_done(session_factory, settings, llm)
    session.refresh(run)
    cb = session.get(Codebook, run.codebook_id)
    return approve(session, cb, "test")


def test_discovery_estimate_then_run_creates_a_draft_codebook(session, session_factory, settings, llm, seeded):
    run = estimate_discovery(session, settings, llm, seeded, APP)

    assert run.status == "estimated" and run.kind == "discovery"
    step = run.estimate["steps"][0]
    assert step["model"] == settings.model_analysis and step["requests"] == 1
    assert step["input_tokens"] == run.est_input_tokens > 0 and run.est_cost_usd > 0
    assert llm.calls == []  # estimating spends nothing

    process_analysis(session_factory, settings, lambda: llm)
    assert llm.calls == []  # still nothing until confirmed

    confirm(session, run)
    run_until_done(session_factory, settings, llm)
    session.refresh(run)

    assert run.status == "succeeded", run.error
    assert run.actual_cost_usd > 0 and run.usage["discovery"]["requests"] == 1
    cb = session.get(Codebook, run.codebook_id)
    assert (cb.version, cb.status) == (1, "draft")
    themes = themes_for(session, cb.id)
    assert [t.key for t in themes] == ["combat_feel", "price_value", "bugs_crashes", "art_style"]
    assert all("—" not in t.definition for t in themes)  # em dashes removed
    assert all("not-a-real-id" not in t.example_review_ids for t in themes)
    assert "proposed 4 themes" in run.warning  # fewer than 8 is flagged for review
    # The sample excluded reviews with no content.
    sampled = set(cb.sample_review_ids)
    assert "10005" not in sampled and len(sampled) == 54


def test_discovery_needs_enough_reviews(session, settings, llm, title):
    seed_reviews(session, title, count=10)
    with pytest.raises(RunError, match="at least 30"):
        estimate_discovery(session, settings, llm, title, APP)


def test_full_analysis_tags_checks_and_summarizes(session, session_factory, settings, llm, seeded):
    cb = discover_and_approve(session, session_factory, settings, llm, seeded)
    llm.paraphrase_ids = {"10001"}
    llm.other_ids = {"10003"}

    run = estimate_analysis(session, settings, llm, seeded, APP)
    names = [s["step"] for s in run.estimate["steps"]]
    assert names == ["tagging", "qa", "summary"]
    assert run.reviews_in_scope == 54 and run.mode == "direct"  # 63 reviews, 9 with no content
    assert run.estimate["steps"][0]["requests"] == 3
    assert run.estimate["steps"][1]["reviews"] == 20  # 5% would be 3; the minimum is 20

    confirm(session, run)
    run_until_done(session_factory, settings, llm)
    session.refresh(run)

    assert run.status == "succeeded", run.error
    assert (run.reviews_tagged, run.reviews_failed) == (54, 0)
    assert set(run.usage) == {"tagging", "qa", "summary"}
    assert run.actual_cost_usd == pytest.approx(sum(s["cost_usd"] for s in run.usage.values()), abs=1e-6)

    # Quotes: the paraphrased one was dropped, every kept quote is the review's own text.
    dropped = session.scalars(select(ThemeMention).where(ThemeMention.quote_status == "dropped")).all()
    dropped_overall = session.scalar(select(func.count()).select_from(ReviewTag).where(ReviewTag.overall_quote_status == "dropped"))
    assert len(dropped) > 0 and dropped_overall == 1
    assert run.quotes_dropped == len(dropped) + dropped_overall
    for m, text in session.execute(
        select(ThemeMention, Review.display_text)
        .join(ReviewTag, ReviewTag.id == ThemeMention.review_tag_id)
        .join(Review, Review.id == ReviewTag.review_id)
        .where(ThemeMention.quote_status == "ok")
    ):
        assert text[m.quote_start : m.quote_end].strip()
    chinese = session.scalar(select(ReviewTag).join(Review).where(Review.recommendation_id == "10004"))
    assert chinese.gist_en and "—" not in (chinese.gist_en or "")

    # Overall impression: stored apart from the themes, its quote checked like theme quotes.
    def tag_of(rec_id):
        return session.execute(select(ReviewTag, Review.display_text).join(Review).where(Review.recommendation_id == rec_id)).one()

    tag, text = tag_of("10000")
    assert (tag.overall_sentiment, tag.overall_quote_status) == ("positive", "ok")
    assert text[tag.overall_quote_start : tag.overall_quote_end] == "Great game, I recommend it."
    tag, _ = tag_of("10001")  # mixed, but its quote was paraphrased, so the quote is dropped
    assert (tag.overall_sentiment, tag.overall_quote_status, tag.overall_quote_start) == ("mixed", "dropped", None)
    assert tag.overall_raw_quote == "a really good game overall"
    tag, text = tag_of("10002")
    assert (tag.overall_sentiment, text[tag.overall_quote_start : tag.overall_quote_end]) == ("negative", "Do not buy.")
    tag, _ = tag_of("10003")
    assert (tag.overall_sentiment, tag.overall_quote_status) == ("none", "none")

    # QA: the analysis model re-tagged 20 reviews and agreement was recorded per theme.
    assert session.scalar(select(func.count(func.distinct(QAResult.review_id)))) == 20
    qa = run.details["qa"]
    assert qa["reviews_checked"] == 20 and set(qa["themes"]) == {"combat_feel", "price_value", "bugs_crashes", "art_style"}
    assert qa["overall"]["presence_agreement"] == 1.0  # the fake is consistent with itself
    assert qa["overall_impression"]["reviews"] == 20 and qa["overall_impression"]["agreement"] == 1.0

    # Theme stats count the overall impression separately from the themes.
    from app.analysis.aggregate import Filters, theme_stats

    stats = theme_stats(session, seeded.id, cb.id, themes_for(session, cb.id), Filters(app_id=APP))
    assert {k: v["count"] for k, v in stats["overall"].items()} == {"positive": 9, "mixed": 9, "negative": 9, "none": 27}
    assert stats["overall"]["positive"]["share"] == pytest.approx(9 / 54)

    # Summary: stored, citations limited to excerpts the model was shown, no em dashes.
    s = session.scalar(select(Summary))
    assert s.app_id == APP and s.content["reviews_analyzed"] == 54
    assert "999999999" not in s.content["strengths"][0]["review_ids"]
    assert "—" not in s.content["strengths"][0]["detail"]
    assert "Removed" in run.warning
    assert '"overall_impression"' in llm.calls[-1].user  # the summary sees the overall split

    # "other" stayed under 10%: no flag on the codebook.
    session.refresh(cb)
    assert cb.needs_review_reason is None


def test_unchanged_reviews_are_never_retagged_but_edits_are(session, session_factory, settings, llm, seeded):
    discover_and_approve(session, session_factory, settings, llm, seeded)
    confirm(session, estimate_analysis(session, settings, llm, seeded, APP))
    run_until_done(session_factory, settings, llm)

    again = estimate_analysis(session, settings, llm, seeded, APP)
    assert again.reviews_in_scope == 0
    assert [s["step"] for s in again.estimate["steps"]] == ["tagging", "summary"]
    assert again.estimate["steps"][0]["cost_usd"] == 0

    # An edited review (new timestamp_updated) is the only one queued for re-tagging.
    edited = make_review(10002, 1_760_000_000 + 2 * 86_400, updated=1_790_000_000, text="Patched: no more crashes. Combat is great now.")
    upsert_reviews(session, seeded.id, APP, [edited], seen_at=utcnow())
    session.commit()
    run = estimate_analysis(session, settings, llm, seeded, APP)
    assert run.reviews_in_scope == 1
    confirm(session, run)
    run_until_done(session_factory, settings, llm)
    review = session.scalar(select(Review).where(Review.recommendation_id == "10002"))
    tags = session.scalars(select(ReviewTag).where(ReviewTag.review_id == review.id)).all()
    assert len(tags) == 2  # the old version's tag is kept for history


def test_tags_from_an_older_tag_version_are_redone(session, session_factory, settings, llm, seeded):
    discover_and_approve(session, session_factory, settings, llm, seeded)
    confirm(session, estimate_analysis(session, settings, llm, seeded, APP))
    run_until_done(session_factory, settings, llm)
    assert estimate_analysis(session, settings, llm, seeded, APP).reviews_in_scope == 0

    # Tags made before the overall impression existed no longer count as current.
    for tag in session.scalars(select(ReviewTag)):
        tag.tag_version, tag.overall_sentiment = 1, None
    session.commit()
    from app.analysis.aggregate import Filters, theme_stats

    stats = theme_stats(session, seeded.id, approved_codebook(session, seeded.id).id, [], Filters(app_id=APP))
    assert (stats["counts"]["analyzed"], stats["counts"]["pending"]) == (0, 54)
    run = estimate_analysis(session, settings, llm, seeded, APP)
    assert run.reviews_in_scope == 54
    confirm(session, run)
    run_until_done(session_factory, settings, llm)
    assert session.scalar(select(func.count()).select_from(ReviewTag).where(ReviewTag.tag_version == 2)) == 54
    assert session.scalar(select(func.count()).select_from(ReviewTag)) == 108  # old tags kept for history


def test_new_codebook_version_means_retagging(session, session_factory, settings, llm, seeded):
    cb = discover_and_approve(session, session_factory, settings, llm, seeded)
    confirm(session, estimate_analysis(session, settings, llm, seeded, APP))
    run_until_done(session_factory, settings, llm)

    old = themes_for(session, cb.id)
    merged = ThemeInput(
        key="gameplay",
        name="Combat and bugs",
        definition="Combat and technical problems.",
        derived_from=[{"key": "combat_feel", "op": "merged"}, {"key": "bugs_crashes", "op": "merged"}],
    )
    keep = [ThemeInput(key=t.key, name=t.name, definition=t.definition, derived_from=[{"key": t.key, "op": "kept"}]) for t in old if t.key in ("price_value", "art_style")]
    v2 = create_version(session, seeded.id, [merged, *keep], created_by="team", parent_id=cb.id, note="Merged two themes")
    assert (v2.version, v2.status) == (2, "draft")
    assert approved_codebook(session, seeded.id).id == cb.id  # drafts don't change what's used

    approve(session, v2, "team")
    session.refresh(cb)
    assert cb.status == "superseded"
    assert estimate_analysis(session, settings, llm, seeded, APP).reviews_in_scope == 54


def test_batch_mode_submits_then_collects(session, session_factory, settings, llm, seeded):
    settings.direct_max_reviews = 10
    settings.batch_poll_seconds = 0
    llm.polls_until_done = 2
    discover_and_approve(session, session_factory, settings, llm, seeded)
    run = estimate_analysis(session, settings, llm, seeded, APP)
    assert run.mode == "batch" and run.estimate["steps"][0]["batch"] is True
    confirm(session, run)

    process_analysis(session_factory, settings, lambda: llm)  # submits the tagging batch
    session.refresh(run)
    assert (run.status, run.step) == ("running", "tagging")
    assert run.batches["tagging"]["requests"] == 3 and not run.batches["tagging"]["ingested"]
    assert session.scalar(select(func.count()).select_from(ReviewTag)) == 0

    run_until_done(session_factory, settings, llm)
    session.refresh(run)
    assert run.status == "succeeded", run.error
    assert run.reviews_tagged == 54 and run.batches["qa"]["ingested"]
    # Batch requests are billed at half price.
    tagging = run.usage["tagging"]
    from app.analysis.pricing import Usage, request_cost

    full = request_cost(settings.model_tagging, Usage(tagging["input_tokens"], tagging["output_tokens"]), batch=False)
    assert tagging["cost_usd"] == pytest.approx(full / 2, rel=0.05)


def test_omitted_and_declined_reviews_get_one_more_try(session, session_factory, settings, llm, seeded):
    discover_and_approve(session, session_factory, settings, llm, seeded)
    llm.omit_ids = {"10000"}  # left out of its group, fine on its own
    llm.refuse_ids = {"10007"}  # declined in its group and on its own
    run = estimate_analysis(session, settings, llm, seeded, APP)
    confirm(session, run)
    run_until_done(session_factory, settings, llm)
    session.refresh(run)

    assert run.status == "succeeded"
    # The omitted review and the declined group's other reviews succeed on their own;
    # only the review the model keeps declining is left.
    assert (run.reviews_tagged, run.reviews_failed) == (53, 1)
    retried = set(run.details["retried_review_ids"])
    assert {r.id for r in session.scalars(select(Review).where(Review.recommendation_id.in_(["10000", "10007"])))} <= retried
    # The declined review stays pending, so the next run tries it again.
    llm.refuse_ids = set()
    assert estimate_analysis(session, settings, llm, seeded, APP).reviews_in_scope == 1


def test_other_rate_over_threshold_flags_the_codebook(session, session_factory, settings, llm, seeded):
    cb = discover_and_approve(session, session_factory, settings, llm, seeded)
    llm.other_ids = {str(10_000 + i) for i in range(0, 63, 3)}  # about a third
    confirm(session, estimate_analysis(session, settings, llm, seeded, APP))
    run_until_done(session_factory, settings, llm)
    session.refresh(cb)
    assert cb.needs_review_reason and "no theme covers" in cb.needs_review_reason


def test_confirm_rules(session, session_factory, settings, llm, seeded):
    cb = discover_and_approve(session, session_factory, settings, llm, seeded)
    first = estimate_analysis(session, settings, llm, seeded, APP)
    second = estimate_analysis(session, settings, llm, seeded, APP)
    confirm(session, first)
    with pytest.raises(RunError, match="already queued or running"):
        confirm(session, second)
    with pytest.raises(RunError, match="already confirmed"):
        confirm(session, first)
    runs.cancel(session, first, llm)
    assert first.status == "canceled"

    # An estimate made under one codebook can't run after another is approved.
    third = estimate_analysis(session, settings, llm, seeded, APP)
    v2 = create_version(session, seeded.id, [ThemeInput(name="Only", definition="One theme.")], created_by="t", parent_id=cb.id)
    approve(session, v2, "t")
    with pytest.raises(RunError, match="codebook changed"):
        confirm(session, third)


def test_analysis_requires_an_approved_codebook(session, settings, llm, seeded):
    with pytest.raises(RunError, match="Approve a codebook"):
        estimate_analysis(session, settings, llm, seeded, APP)


def test_missing_api_key_fails_the_run_clearly(session, session_factory, settings, llm, seeded):
    from app.analysis.llm import LLMNotConfigured

    run = estimate_discovery(session, settings, llm, seeded, APP)
    confirm(session, run)

    def no_key():
        raise LLMNotConfigured("ANTHROPIC_API_KEY is not set, so analysis can't run.")

    process_analysis(session_factory, settings, no_key)
    session.refresh(run)
    assert run.status == "failed" and "ANTHROPIC_API_KEY" in run.error
