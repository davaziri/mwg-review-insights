from types import SimpleNamespace

import pytest

from app.analysis.aggregate import ReviewRow, compute
from app.analysis.pricing import Usage, UnknownModelPrice, price_for, request_cost
from app.analysis.qa import agreement, kappa, qa_count
from app.analysis.sampling import stratified_sample
from app.config import Settings

THEMES = [SimpleNamespace(id=1, key="combat", name="Combat", definition="d"), SimpleNamespace(id=2, key="price", name="Price", definition="d")]
JAN, FEB = 1_767_225_600, 1_769_904_000  # 2026-01-01, 2026-02-01 (UTC)


def row(i, created, *, tag=True, up=True, band="2to10h", lang="english", ea=False, deck=False, refunded=False, content=True, dev=None, other=False, overall="none"):
    tagged = tag and content
    return ReviewRow(
        id=i, created=created, voted_up=up, playtime_band=band, language=lang, early_access=ea, steam_deck=deck,
        refunded=refunded, has_content=content, dev_responded_at=dev, has_dev_response=dev is not None,
        tag_id=(100 + i) if tagged else None, other_flag=other, overall=overall if tagged else None,
    )


def test_aggregation_math():
    rows = [
        row(1, JAN, band="lt2h", dev=JAN + 3600 * 10, overall="positive"),
        row(2, JAN, up=False, lang="german", dev=JAN + 3600 * 30, overall="negative"),
        row(3, FEB, ea=True, other=True, overall="positive"),
        row(4, FEB, deck=True, refunded=True),
        row(5, FEB, content=False),  # no text: counted, never analyzed
        row(6, FEB, tag=False),  # has text, not tagged yet
    ]
    mentions = {
        101: [(1, "positive"), (2, "negative")],
        102: [(1, "negative")],
        103: [(1, "mixed")],
        104: [(2, "negative")],
    }
    out = compute(rows, mentions, THEMES)

    assert out["counts"] == {"reviews": 6, "with_content": 5, "no_content": 1, "analyzed": 4, "pending": 1, "positive_votes": 5}
    combat, price = out["themes"]
    assert combat["key"] == "combat"  # sorted by mentions
    assert (combat["mentions"], combat["share"]) == (3, 0.75)
    assert (combat["positive"], combat["negative"], combat["mixed"]) == (1, 1, 1)
    assert combat["net"] == 0.0
    assert (price["mentions"], price["share"], price["net"]) == (2, 0.5, -1.0)

    jan, feb = combat["monthly"]
    assert (jan["month"], jan["mentions"], jan["share"]) == ("2026-01", 2, 1.0)
    assert (feb["month"], feb["mentions"], feb["share"]) == ("2026-02", 1, 0.5)
    feb_month = out["months"][1]
    assert {k: feb_month[k] for k in ("month", "reviews", "analyzed", "positive_votes")} == {"month": "2026-02", "reviews": 4, "analyzed": 2, "positive_votes": 4}
    assert {k: v["count"] for k, v in feb_month["overall"].items()} == {"positive": 1, "mixed": 0, "negative": 0, "none": 1}

    # Overall impression: counted over analyzed reviews only, separately from the themes.
    assert {k: v["count"] for k, v in out["overall"].items()} == {"positive": 2, "mixed": 0, "negative": 1, "none": 1}
    assert out["overall"]["positive"]["share"] == 0.5

    bands = {s["segment"]: s for s in out["splits"]["playtime_band"]}
    assert bands["lt2h"]["analyzed"] == 1 and bands["lt2h"]["themes"]["combat"]["share"] == 1.0
    ea = {s["segment"]: s for s in out["splits"]["early_access"]}
    assert ea["true"]["themes"]["combat"]["mentions"] == 1 and ea["true"]["label"] == "Yes"
    langs = {s["segment"]: s for s in out["splits"]["language"]}
    assert langs["german"]["themes"]["combat"]["net"] == -1.0
    assert {s["segment"] for s in out["splits"]["refunded"]} == {"true", "false"}

    assert out["developer_response"] == {"responded": 2, "rate": 2 / 6, "median_hours": 20.0}
    assert out["other"] == {"count": 1, "share": 0.25}


def test_aggregation_with_nothing_analyzed():
    out = compute([row(1, JAN, tag=False)], {}, THEMES)
    assert out["counts"]["analyzed"] == 0
    assert all(t["share"] == 0 and t["net"] is None for t in out["themes"])


def test_kappa():
    assert kappa(10, 0, 0, 10) == 1.0
    assert kappa(0, 10, 10, 0) == -1.0
    assert kappa(0, 0, 0, 20) is None  # nobody ever tagged it: undefined
    assert kappa(20, 5, 10, 15) == pytest.approx(0.4)


def test_agreement_per_theme_and_overall():
    rows = [
        (1, True, "positive", True, "positive"),
        (1, True, "negative", True, "mixed"),
        (1, False, None, True, "positive"),
        (1, False, None, False, None),
        (2, False, None, False, None),
    ] + [(2, False, None, False, None)] * 3
    out = agreement(THEMES, rows)
    combat = out["themes"]["combat"]
    assert (combat["both"], combat["qa_only"], combat["neither"]) == (2, 1, 1)
    assert combat["presence_agreement"] == 0.75 and combat["sentiment_agreement"] == 0.5
    assert out["themes"]["price"]["kappa"] is None
    assert out["overall"]["presence_agreement"] == 7 / 8


def test_qa_count():
    s = Settings(_env_file=None)
    assert (qa_count(0, s), qa_count(10, s), qa_count(331, s), qa_count(1000, s)) == (0, 10, 20, 50)


def _r(i, up, band, ea=False, lang="english"):
    return SimpleNamespace(id=i, voted_up=up, playtime_band=band, written_during_early_access=ea, language=lang, effective_language=lang)


def test_stratified_sample():
    reviews = (
        [_r(i, True, "2to10h") for i in range(700)]
        + [_r(1000 + i, True, "50h_plus", lang="german") for i in range(100)]
        + [_r(2000 + i, False, "lt2h") for i in range(150)]
        + [_r(3000 + i, False, "10to50h", ea=True) for i in range(50)]
    )
    sample = stratified_sample(reviews, 400, seed=7)

    assert len(sample) == 400 and len({r.id for r in sample}) == 400
    negatives = [r for r in sample if not r.voted_up]
    assert len(negatives) == 120  # 20% of reviews are negative; raised to 30% of the sample
    assert {(r.playtime_band, r.written_during_early_access) for r in negatives} == {("lt2h", False), ("10to50h", True)}
    assert any(r.language == "german" for r in sample)
    assert [r.id for r in stratified_sample(reviews, 400, seed=7)] == [r.id for r in sample]  # deterministic
    assert len(stratified_sample(reviews[:50], 400, seed=7)) == 50  # small titles: everything


def test_pricing():
    usage = Usage(input_tokens=1_000_000, output_tokens=1_000_000, cache_read_tokens=1_000_000, cache_write_tokens=1_000_000)
    # Haiku 5.5 short-prompt rates would be 0.10 + 0.50 + 0.01 + 0.125, but this prompt is over 100K tokens.
    assert request_cost("claude-haiku-5-5", usage, batch=False) == pytest.approx(0.50 + 2.50 + 0.05 + 0.625)
    small = Usage(input_tokens=6_000, output_tokens=5_000)
    assert request_cost("claude-haiku-5-5", small, batch=False) == pytest.approx((6_000 * 0.10 + 5_000 * 0.50) / 1e6)
    assert request_cost("claude-haiku-5-5", small, batch=True) == pytest.approx((6_000 * 0.10 + 5_000 * 0.50) / 2e6)
    assert request_cost("claude-sonnet-5-5", small, batch=False) == pytest.approx((6_000 * 2 + 5_000 * 10) / 1e6)
    with pytest.raises(UnknownModelPrice):
        price_for("claude-unknown", 10)
    s = Settings(_env_file=None, model_prices={"claude-unknown": {"input": 1, "output": 2, "cache_write": 1.25, "cache_read": 0.1}})
    assert price_for("claude-unknown", 10, s).output == 2
