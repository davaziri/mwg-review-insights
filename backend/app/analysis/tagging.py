"""Tagging: the tagging model reads groups of reviews and returns themes, sentiment and quotes."""

from collections.abc import Sequence

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.analysis import prompts
from app.analysis.aggregate import current_tag_join
from app.analysis.formatting import codebook_block, reviews_block
from app.analysis.llm import LLMRequest, LLMResult
from app.analysis.quotes import locate_quote
from app.analysis.text_rules import strip_em_dashes
from app.models import AnalysisRun, Review, ReviewTag, Theme, ThemeMention, Title

SENTIMENTS = {"positive", "negative", "mixed"}


def pending_reviews(session: Session, title_id: int, app_id: int, codebook_id: int) -> list[Review]:
    """Reviews with text that have no tag for their current version under this codebook.
    This is how unchanged reviews are never re-tagged."""
    tagged = exists().where(current_tag_join(codebook_id))
    return list(
        session.scalars(
            select(Review)
            .where(
                Review.title_id == title_id,
                Review.app_id == app_id,
                Review.deleted_at.is_(None),
                Review.content_status == "ok",
                ~tagged,
            )
            .order_by(Review.id)
        )
    )


def remaining(session: Session, codebook_id: int, review_ids: Sequence[int]) -> list[Review]:
    """Of the planned reviews, those still without a current tag."""
    out = []
    for i in range(0, len(review_ids), 900):
        chunk = review_ids[i : i + 900]
        tagged = exists().where(current_tag_join(codebook_id))
        out.extend(session.scalars(select(Review).where(Review.id.in_(chunk), ~tagged)))
    return sorted(out, key=lambda r: r.id)


def tagging_request(title: Title, themes: Sequence[Theme], reviews: Sequence[Review], *, model: str, effort: str | None) -> LLMRequest:
    return LLMRequest(
        model=model,
        system=prompts.render("tagging_system", game=title.name, codebook=codebook_block(themes)),
        user="Tag each of these reviews.\n\n<reviews>\n" + reviews_block(reviews, details=False) + "\n</reviews>",
        schema=prompts.tagging_schema([t.key for t in themes]),
        max_tokens=32_000,
        effort=effort,
    )


def parse_entries(result: LLMResult) -> dict[str, dict]:
    if not result.ok:
        return {}
    return {str(e.get("review_id")): e for e in result.data.get("reviews", []) if isinstance(e, dict)}


def mentions_by_key(entry: dict, theme_keys: set[str]) -> dict[str, dict]:
    """The entry's mentions keyed by theme, first mention of a theme wins, unknown themes dropped."""
    out: dict[str, dict] = {}
    for m in entry.get("mentions", []):
        key = m.get("theme_id")
        if key in theme_keys and key not in out and m.get("sentiment") in SENTIMENTS:
            out[key] = m
    return out


def ingest(
    session: Session,
    run: AnalysisRun,
    codebook_id: int,
    themes: Sequence[Theme],
    reviews: Sequence[Review],
    result: LLMResult,
) -> list[Review]:
    """Store tags for the reviews the model answered for. Returns the reviews still untagged."""
    entries = parse_entries(result)
    themes_by_key = {t.key: t for t in themes}
    failed: list[Review] = []
    for review in reviews:
        entry = entries.get(review.recommendation_id)
        if entry is None:
            failed.append(review)
            continue
        already = session.scalar(
            select(ReviewTag.id).where(
                ReviewTag.review_id == review.id,
                ReviewTag.codebook_id == codebook_id,
                ReviewTag.review_timestamp_updated == review.timestamp_updated,
            )
        )
        if already:
            continue
        other_flag = bool(entry.get("other_flag"))
        tag = ReviewTag(
            review_id=review.id,
            codebook_id=codebook_id,
            analysis_run_id=run.id,
            review_timestamp_updated=review.timestamp_updated,
            model=result.model or "",
            gist_en=strip_em_dashes(entry.get("gist_en", "").strip()) or None,
            other_flag=other_flag,
            other_note=(strip_em_dashes(entry.get("other_note", "").strip()) or None) if other_flag else None,
            raw_output=entry,
        )
        session.add(tag)
        session.flush()
        for key, m in mentions_by_key(entry, set(themes_by_key)).items():
            quote = (m.get("quote") or "").strip()
            span = locate_quote(review.display_text or "", quote) if quote else None
            if quote:
                run.quotes_checked += 1
                if span is None:
                    run.quotes_dropped += 1
            session.add(
                ThemeMention(
                    review_tag_id=tag.id,
                    theme_id=themes_by_key[key].id,
                    sentiment=m["sentiment"],
                    quote_start=span[0] if span else None,
                    quote_end=span[1] if span else None,
                    quote_status="ok" if span else ("dropped" if quote else "none"),
                    raw_quote=quote or None,
                )
            )
        run.reviews_tagged += 1
    return failed
