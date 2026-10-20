import pytest

from app.analysis.prep import clean_review_text, content_status, playtime_band
from app.analysis.quotes import locate_quote
from app.analysis.text_rules import clean_generated, strip_em_dashes


def test_clean_review_text_removes_steam_markup_and_keeps_words():
    raw = "[h1]Pros[/h1][list][*]Tight [b]combat[/b][*]Great [url=https://x.y]soundtrack[/url][/list]\r\n\r\n\r\nCons: none"
    assert clean_review_text(raw) == "Pros\n- Tight combat\n- Great soundtrack\n\nCons: none"


@pytest.mark.parametrize(
    ("text", "status"),
    [
        ("", "no_content"),
        ("👍👍👍", "no_content"),
        ("good", "no_content"),
        ("10/10", "no_content"),
        ("great game", "ok"),
        ("很好玩", "ok"),
        ("The duck physics are hilarious", "ok"),
    ],
)
def test_content_status(text, status):
    assert content_status(text) == status


@pytest.mark.parametrize(
    ("at_review", "forever", "band"),
    [(0, 5, "lt2h"), (119, None, "lt2h"), (120, None, "2to10h"), (599, None, "2to10h"),
     (600, None, "10to50h"), (2999, None, "10to50h"), (3000, None, "50h_plus"), (None, 700, "10to50h"),
     (None, None, "unknown")],
)
def test_playtime_band(at_review, forever, band):
    assert playtime_band(at_review, forever) == band


TEXT = "The combat feels great.\n\nBut the   camera is awful and the Boss Fights drag on."


@pytest.mark.parametrize(
    ("quote", "expected"),
    [
        ("combat feels great", "combat feels great"),
        ('"combat feels great"', "combat feels great"),  # wrapping quote marks are ignored
        ("the camera is awful", "the   camera is awful"),  # whitespace differences are tolerated
        ("boss fights drag on", "Boss Fights drag on"),  # so is letter case
        ("great. But the camera", "great.\n\nBut the   camera"),
    ],
)
def test_locate_quote_returns_the_reviews_own_text(quote, expected):
    span = locate_quote(TEXT, quote)
    assert span is not None
    assert TEXT[span[0] : span[1]] == expected


@pytest.mark.parametrize(
    "quote",
    [
        "combat feels amazing",  # paraphrase
        "combat feels great... camera is awful",  # stitched together
        "the camera is bad",
        "",
        None,
        "Th",  # too short to mean anything
    ],
)
def test_locate_quote_rejects_anything_not_verbatim(quote):
    assert locate_quote(TEXT, quote) is None


def test_locate_quote_works_for_non_latin_text():
    text = "战斗系统很棒，但是镜头太差了"
    span = locate_quote(text, "镜头太差了")
    assert text[span[0] : span[1]] == "镜头太差了"


def test_strip_em_dashes():
    assert strip_em_dashes("Combat feel — how hits land") == "Combat feel, how hits land"
    assert strip_em_dashes("Great—but short") == "Great, but short"
    assert strip_em_dashes("no dashes - here") == "no dashes - here"
    assert clean_generated({"a": ["x — y"], "b": 3}) == {"a": ["x, y"], "b": 3}
