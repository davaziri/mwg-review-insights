"""The data behind every export, as plain rows: coded reviews, theme summary, monthly trends."""

from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import null, select
from sqlalchemy.orm import Session

from app.analysis.aggregate import Filters, current_tag_join, review_filter_clauses, theme_stats
from app.analysis.codebooks import approved_codebook, themes_for
from app.api.common import review_url
from app.config import Settings
from app.exports.common import describe_filters, language_name, yes_no
from app.models import AnalysisRun, Codebook, Review, ReviewTag, Theme, ThemeMention, Title
from app.timeutil import utcnow

OVERALL_WORDS = {"positive": "Positive", "mixed": "Mixed", "negative": "Negative", "none": "No overall view"}


@dataclass
class ExportContext:
    title: Title
    app_id: int
    filters: Filters
    codebook: Codebook | None
    themes: list[Theme]
    stats: dict
    tagging_model: str | None
    analysis_model: str | None
    run: AnalysisRun | None
    generated_at: datetime

    @property
    def is_demo(self) -> bool:
        return self.app_id != self.title.steam_app_id

    @property
    def subject(self) -> str:
        return f"{self.title.name} (demo)" if self.is_demo else self.title.name


def latest_analysis(session: Session, title_id: int, app_id: int) -> AnalysisRun | None:
    return session.scalar(
        select(AnalysisRun)
        .where(AnalysisRun.title_id == title_id, AnalysisRun.app_id == app_id, AnalysisRun.kind == "analysis", AnalysisRun.status == "succeeded")
        .order_by(AnalysisRun.id.desc())
        .limit(1)
    )


def build_context(session: Session, settings: Settings, title: Title, app_id: int, filters: Filters) -> ExportContext:
    filters.app_id = app_id
    cb = approved_codebook(session, title.id)
    themes = themes_for(session, cb.id) if cb else []
    stats = theme_stats(session, title.id, cb.id if cb else None, themes, filters)
    run = latest_analysis(session, title.id, app_id)
    usage = (run.usage or {}) if run else {}
    return ExportContext(
        title=title,
        app_id=app_id,
        filters=filters,
        codebook=cb,
        themes=themes,
        stats=stats,
        tagging_model=(usage.get("tagging") or {}).get("model") or (settings.model_tagging if cb else None),
        analysis_model=(usage.get("summary") or usage.get("qa") or {}).get("model") or (settings.model_analysis if cb else None),
        run=run,
        generated_at=utcnow(),
    )


def _date(ts: int | None) -> date | None:
    return datetime.fromtimestamp(ts, UTC).date() if ts else None


def verified_quote(text: str | None, start: int | None, end: int | None) -> str | None:
    """The quote at these offsets, only if it is really there in the review text."""
    if not text or start is None or end is None or not 0 <= start < end <= len(text):
        return None
    quote = text[start:end].strip()
    return quote if quote and quote in text else None


def coded_reviews(session: Session, ctx: ExportContext) -> tuple[list[str], list[list]]:
    """One row per review that passes the filters, newest first, with a column per theme holding
    that theme's sentiment in the review (blank when the theme is not mentioned)."""
    themes = sorted(ctx.themes, key=lambda t: t.sort_order)
    header = [
        "Review ID",
        "Steam link",
        "Date written",
        "Language",
        "Recommended",
        "Playtime at review (hours)",
        "Early access",
        "Steam Deck",
        "Helpful votes",
        "Developer replied",
        "Analyzed",
        "Overall impression",
        "Overall impression quote",
        *[t.name for t in themes],
        "Point no theme covers",
        "English gist (machine-written, not a quote)",
        "Review text",
    ]
    if ctx.codebook:
        query = select(Review, ReviewTag).outerjoin(ReviewTag, current_tag_join(ctx.codebook.id))
    else:
        query = select(Review, null())
    rows = session.execute(
        query.where(*review_filter_clauses(ctx.title.id, ctx.filters)).order_by(Review.timestamp_created.desc(), Review.id.desc())
    ).all()

    tag_ids = [tag.id for _, tag in rows if tag is not None]
    mentions: dict[int, dict[int, str]] = {}
    for i in range(0, len(tag_ids), 900):
        for tag_id, theme_id, sentiment in session.execute(
            select(ThemeMention.review_tag_id, ThemeMention.theme_id, ThemeMention.sentiment).where(ThemeMention.review_tag_id.in_(tag_ids[i : i + 900]))
        ):
            mentions.setdefault(tag_id, {})[theme_id] = sentiment

    out = []
    for review, tag in rows:
        # Only reviews with text can carry a tag; a stale tag on a review now without text is ignored.
        tag = tag if review.content_status == "ok" else None
        if tag is not None:
            analyzed = "Yes"
        elif review.content_status == "no_content":
            analyzed = "No, too short"
        else:
            analyzed = "No, not analyzed yet"
        found = mentions.get(tag.id, {}) if tag else {}
        out.append(
            [
                review.recommendation_id,
                review_url(review),
                _date(review.timestamp_created),
                language_name(review.language),
                yes_no(review.voted_up),
                round(review.author_playtime_at_review / 60, 1) if review.author_playtime_at_review is not None else None,
                yes_no(review.written_during_early_access),
                yes_no(review.primarily_steam_deck),
                review.votes_up or 0,
                yes_no(review.developer_response is not None),
                analyzed,
                OVERALL_WORDS.get(tag.overall_sentiment or "none") if tag else None,
                verified_quote(review.display_text, tag.overall_quote_start, tag.overall_quote_end) if tag and tag.overall_quote_status == "ok" else None,
                *[found.get(t.id, "").capitalize() or None for t in themes],
                (tag.other_note or None) if tag and tag.other_flag else None,
                tag.gist_en or None if tag else None,
                review.display_text or "",
            ]
        )
    return header, out


def theme_summary(ctx: ExportContext) -> tuple[list[str], list[list]]:
    header = ["Theme", "Definition", "Reviews mentioning it", "Share of analyzed reviews", "Positive", "Mixed", "Negative", "Net sentiment (-100 to 100)"]
    rows = [
        [
            t["name"],
            t["definition"],
            t["mentions"],
            t["share"],
            t["positive"],
            t["mixed"],
            t["negative"],
            None if t["net"] is None else round(t["net"] * 100),
        ]
        for t in sorted(ctx.stats["themes"], key=lambda t: -t["share"])
    ]
    return header, rows


def month_range(first: str, last: str) -> list[str]:
    y, m = map(int, first.split("-"))
    ly, lm = map(int, last.split("-"))
    out = []
    while (y, m) <= (ly, lm):
        out.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def monthly_trends(ctx: ExportContext) -> tuple[list[str], list[list]]:
    """Reviews, recommended share, overall impression and each theme's share, month by month.
    Months with no reviews are included as zeros so the series has no holes."""
    themes = sorted(ctx.stats["themes"], key=lambda t: -t["share"])
    header = [
        "Month",
        "Reviews",
        "Recommended",
        "Recommended share",
        "Analyzed reviews",
        "Overall: positive",
        "Overall: mixed",
        "Overall: negative",
        *[f"{t['name']} (share)" for t in themes],
    ]
    months = ctx.stats["months"]
    if not months:
        return header, []
    by_month = {m["month"]: m for m in months}
    cells = {t["key"]: {c["month"]: c for c in t["monthly"]} for t in themes}
    rows = []
    for month in month_range(months[0]["month"], months[-1]["month"]):
        m = by_month.get(month)
        reviews = m["reviews"] if m else 0
        positive = m["positive_votes"] if m else 0
        analyzed = m["analyzed"] if m else 0
        overall = m["overall"] if m else {}
        rows.append(
            [
                month,
                reviews,
                positive,
                positive / reviews if reviews else None,
                analyzed,
                (overall.get("positive") or {}).get("count", 0),
                (overall.get("mixed") or {}).get("count", 0),
                (overall.get("negative") or {}).get("count", 0),
                *[(cells[t["key"]].get(month) or {}).get("share") if analyzed else None for t in themes],
            ]
        )
    return header, rows


def about(ctx: ExportContext) -> list[tuple[str, str]]:
    c = ctx.stats["counts"]
    overall = ctx.stats.get("overall") or {}
    lines = [
        ("Title", ctx.subject),
        ("Steam app", str(ctx.app_id)),
        ("Generated", ctx.generated_at.strftime("%Y-%m-%d %H:%M UTC")),
        ("Filters", "; ".join(describe_filters(ctx.filters)) or "None (every review)"),
        ("Reviews", str(c["reviews"])),
        ("Recommended", f"{c['positive_votes']} ({c['positive_votes'] / c['reviews']:.0%})" if c["reviews"] else "0"),
        ("Reviews with text", str(c["with_content"])),
        ("Analyzed reviews", str(c["analyzed"])),
        ("Codebook", f"Version {ctx.codebook.version}, {len(ctx.themes)} themes" if ctx.codebook else "No approved codebook yet"),
        ("Tagging model", ctx.tagging_model or "None"),
        ("Analysis model", ctx.analysis_model or "None"),
    ]
    if c["analyzed"]:
        lines.append(
            (
                "Overall impression",
                ", ".join(f"{OVERALL_WORDS[k].lower()} {v['count']} ({v['share']:.0%})" for k, v in overall.items()),
            )
        )
    lines += [
        (
            "Notes",
            "Shares are of analyzed reviews (reviews with text that the tagging model has read). Quotes are copied exactly from the "
            "review and were checked against its text. English gists are written by the model and are not quotes.",
        ),
    ]
    return lines
