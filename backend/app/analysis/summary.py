"""Executive summary: top strengths, top problems and the last 30 days, citing review IDs."""

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis import prompts
from app.analysis.aggregate import Filters, current_tag_join, theme_stats
from app.analysis.llm import LLMRequest, LLMResult
from app.analysis.text_rules import clean_generated
from app.config import Settings
from app.models import AnalysisRun, Codebook, Review, ReviewTag, Summary, Theme, ThemeMention, Title
from app.timeutil import utcnow

SUMMARY_INPUT_ESTIMATE = 15_000
SUMMARY_OUTPUT_ESTIMATE = 6_000
PER_THEME_EXCERPTS = 3  # per sentiment
RECENT_EXCERPTS = 20


def _pct(x: float | None) -> float | None:
    return None if x is None else round(100 * x, 1)


def _theme_payload(stats: dict) -> dict:
    return {
        t["key"]: {
            "mentions": t["mentions"],
            "share_pct": _pct(t["share"]),
            "positive": t["positive"],
            "negative": t["negative"],
            "mixed": t["mixed"],
            "net": None if t["net"] is None else round(t["net"], 2),
        }
        for t in stats["themes"]
    }


def _excerpt(review: Review, mention: ThemeMention, key: str, gist: str | None) -> dict:
    created = datetime.fromtimestamp(review.timestamp_created or 0, UTC).date().isoformat()
    item = {
        "review_id": review.recommendation_id,
        "theme": key,
        "sentiment": mention.sentiment,
        "date": created,
        "language": review.language,
        "quote": (review.display_text or "")[mention.quote_start : mention.quote_end],
    }
    if gist:
        item["english_gist"] = gist
    return item


def build_request(
    session: Session, settings: Settings, title: Title, app_id: int, codebook: Codebook, themes: list[Theme]
) -> tuple[LLMRequest | None, set[str], int]:
    """The summary request, the review IDs it may cite, and how many reviews it rests on."""
    now = utcnow()
    cutoff = (now - timedelta(days=30)).date()
    everything = theme_stats(session, title.id, codebook.id, themes, Filters(app_id=app_id))
    analyzed = everything["counts"]["analyzed"]
    if analyzed == 0:
        return None, set(), 0
    recent = theme_stats(session, title.id, codebook.id, themes, Filters(app_id=app_id, date_from=cutoff))
    before = theme_stats(session, title.id, codebook.id, themes, Filters(app_id=app_id, date_to=cutoff - timedelta(days=1)))

    statistics = {
        "themes": {t.key: {"name": t.name, "definition": t.definition} for t in themes},
        "all_time": {"reviews_analyzed": analyzed, "by_theme": _theme_payload(everything)},
        "last_30_days": {"reviews_analyzed": recent["counts"]["analyzed"], "by_theme": _theme_payload(recent)},
        "before_last_30_days": {"reviews_analyzed": before["counts"]["analyzed"], "by_theme": _theme_payload(before)},
        "positive_vote_pct": _pct(everything["counts"]["positive_votes"] / everything["counts"]["reviews"])
        if everything["counts"]["reviews"]
        else None,
    }

    # Evidence: verified quotes only. Most helpful first per theme and sentiment, plus the newest.
    rows = session.execute(
        select(Review, ThemeMention, Theme.key, ReviewTag.gist_en)
        .join(ReviewTag, current_tag_join(codebook.id))
        .join(ThemeMention, ThemeMention.review_tag_id == ReviewTag.id)
        .join(Theme, Theme.id == ThemeMention.theme_id)
        .where(
            Review.title_id == title.id,
            Review.app_id == app_id,
            Review.deleted_at.is_(None),
            ThemeMention.quote_status == "ok",
        )
    ).all()
    excerpts: dict[tuple[str, int], dict] = {}
    by_group: dict[tuple[str, str], list] = {}
    for review, mention, key, gist in rows:
        by_group.setdefault((key, mention.sentiment), []).append((review, mention, key, gist))
    for group in by_group.values():
        group.sort(key=lambda x: (-(x[0].votes_up or 0), -(x[0].timestamp_created or 0)))
        for review, mention, key, gist in group[:PER_THEME_EXCERPTS]:
            excerpts[(review.recommendation_id, mention.theme_id)] = _excerpt(review, mention, key, gist)
    cutoff_ts = int(datetime(cutoff.year, cutoff.month, cutoff.day, tzinfo=UTC).timestamp())
    newest = sorted((x for x in rows if (x[0].timestamp_created or 0) >= cutoff_ts), key=lambda x: -(x[0].timestamp_created or 0))
    for review, mention, key, gist in newest[:RECENT_EXCERPTS]:
        excerpts[(review.recommendation_id, mention.theme_id)] = _excerpt(review, mention, key, gist)

    evidence = list(excerpts.values())
    user = (
        f"Game: {title.name}\nToday: {now.date().isoformat()}\n\n"
        f"Statistics (JSON):\n{json.dumps(statistics, ensure_ascii=False, indent=1)}\n\n"
        f"Review excerpts (JSON, verbatim):\n{json.dumps(evidence, ensure_ascii=False, indent=1)}\n\n"
        "Write the summary."
    )
    request = LLMRequest(
        model=settings.model_analysis,
        system=prompts.text("summary_system"),
        user=user,
        schema=prompts.summary_schema([t.key for t in themes]),
        max_tokens=32_000,
        effort=settings.analysis_effort,
    )
    return request, {e["review_id"] for e in evidence}, analyzed


def save(
    session: Session,
    run: AnalysisRun,
    codebook: Codebook,
    result: LLMResult,
    allowed_ids: set[str],
    analyzed: int,
) -> tuple[Summary, int]:
    """Store the summary, keeping only citations of reviews it was actually shown.
    Returns the summary and how many citations were removed."""
    data = clean_generated(result.data)
    removed = 0

    def keep(ids: list) -> list[str]:
        nonlocal removed
        good = [str(i) for i in ids if str(i) in allowed_ids]
        removed += len(ids) - len(good)
        return list(dict.fromkeys(good))

    content = {
        "strengths": [{**p, "review_ids": keep(p.get("review_ids", []))} for p in data.get("strengths", [])][:3],
        "problems": [{**p, "review_ids": keep(p.get("review_ids", []))} for p in data.get("problems", [])][:3],
        "last_30_days": {
            "text": data.get("last_30_days", {}).get("text", ""),
            "review_ids": keep(data.get("last_30_days", {}).get("review_ids", [])),
        },
        "reviews_analyzed": analyzed,
        "codebook_version": codebook.version,
    }
    summary = Summary(
        title_id=run.title_id,
        app_id=run.app_id,
        analysis_run_id=run.id,
        codebook_id=codebook.id,
        model=result.model or "",
        content=content,
    )
    session.add(summary)
    return summary, removed
