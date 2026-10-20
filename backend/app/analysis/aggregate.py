"""Theme statistics for a title, computed from the current tags under the approved codebook.

Definitions (also shown in the UI):
- A review is "analyzed" when it has text and a tag under the current codebook for its current
  version. Shares use analyzed reviews as the base; reviews with no text are counted separately.
- share: analyzed reviews mentioning the theme / analyzed reviews.
- net sentiment: (positive mentions - negative mentions) / all mentions, from -1 to +1.
- overall impression: each analyzed review's overall view of the game (positive, mixed, negative,
  or none), counted separately from the themes.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from statistics import median

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.analysis.prep import PLAYTIME_BAND_LABELS, PLAYTIME_BANDS
from app.models import Review, ReviewTag, Theme, ThemeMention
from app.models.analysis import CURRENT_TAG_VERSION

TOP_LANGUAGES = 8


@dataclass
class Filters:
    app_id: int | None = None
    date_from: date | None = None
    date_to: date | None = None
    voted_up: bool | None = None
    playtime_bands: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    early_access: bool | None = None
    steam_deck: bool | None = None
    has_dev_response: bool | None = None


@dataclass
class ReviewRow:
    id: int
    created: int
    voted_up: bool
    playtime_band: str
    language: str
    early_access: bool
    steam_deck: bool
    refunded: bool
    has_content: bool
    dev_responded_at: int | None
    has_dev_response: bool
    tag_id: int | None
    other_flag: bool = False
    overall: str | None = None  # positive | negative | mixed | none, from the current tag


def _ts(d: date, end: bool = False) -> int:
    dt = datetime(d.year, d.month, d.day, 23, 59, 59) if end else datetime(d.year, d.month, d.day)
    return int(dt.replace(tzinfo=UTC).timestamp())


def review_filter_clauses(title_id: int, f: Filters) -> list:
    clauses = [Review.title_id == title_id, Review.deleted_at.is_(None)]
    if f.app_id is not None:
        clauses.append(Review.app_id == f.app_id)
    if f.date_from:
        clauses.append(Review.timestamp_created >= _ts(f.date_from))
    if f.date_to:
        clauses.append(Review.timestamp_created <= _ts(f.date_to, end=True))
    if f.voted_up is not None:
        clauses.append(Review.voted_up.is_(f.voted_up))
    if f.playtime_bands:
        clauses.append(Review.playtime_band.in_(f.playtime_bands))
    if f.languages:
        clauses.append(Review.language.in_(f.languages))
    if f.early_access is not None:
        clauses.append(Review.written_during_early_access.is_(f.early_access))
    if f.steam_deck is not None:
        clauses.append(Review.primarily_steam_deck.is_(f.steam_deck))
    if f.has_dev_response is not None:
        clauses.append(Review.developer_response.is_not(None) if f.has_dev_response else Review.developer_response.is_(None))
    return clauses


def current_tag_join(codebook_id: int):
    """Join condition for the current tag of a review: its current text, under this codebook,
    made with the current tag version."""
    return and_(
        ReviewTag.review_id == Review.id,
        ReviewTag.codebook_id == codebook_id,
        ReviewTag.tag_version == CURRENT_TAG_VERSION,
        func.coalesce(ReviewTag.review_timestamp_updated, 0) == func.coalesce(Review.timestamp_updated, 0),
    )


def load_rows(session: Session, title_id: int, codebook_id: int | None, f: Filters) -> list[ReviewRow]:
    columns = [
        Review.id,
        Review.timestamp_created,
        Review.voted_up,
        Review.playtime_band,
        Review.language,
        Review.written_during_early_access,
        Review.primarily_steam_deck,
        Review.refunded,
        Review.content_status,
        Review.timestamp_dev_responded,
        Review.developer_response.is_not(None),
    ]
    if codebook_id:
        columns += [ReviewTag.id, ReviewTag.other_flag, ReviewTag.overall_sentiment]
    query = select(*columns).where(*review_filter_clauses(title_id, f))
    if codebook_id:
        query = query.outerjoin(ReviewTag, current_tag_join(codebook_id))
    rows = []
    for r in session.execute(query):
        has_content = r[8] == "ok"
        tag_id = r[11] if codebook_id and has_content else None
        rows.append(
            ReviewRow(
                id=r[0],
                created=r[1] or 0,
                voted_up=bool(r[2]),
                playtime_band=r[3] or "unknown",
                language=r[4] or "unknown",
                early_access=bool(r[5]),
                steam_deck=bool(r[6]),
                refunded=bool(r[7]),
                has_content=has_content,
                dev_responded_at=r[9],
                has_dev_response=bool(r[10]),
                tag_id=tag_id,
                other_flag=bool(r[12]) if tag_id is not None else False,
                overall=r[13] if tag_id is not None else None,
            )
        )
    return rows


def load_mentions(session: Session, tag_ids: list[int]) -> dict[int, list[tuple[int, str]]]:
    out: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for i in range(0, len(tag_ids), 900):
        chunk = tag_ids[i : i + 900]
        for tag_id, theme_id, sentiment in session.execute(
            select(ThemeMention.review_tag_id, ThemeMention.theme_id, ThemeMention.sentiment).where(
                ThemeMention.review_tag_id.in_(chunk)
            )
        ):
            out[tag_id].append((theme_id, sentiment))
    return out


def _month(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m")


def _theme_counts(rows: list[ReviewRow], mentions: dict[int, list[tuple[int, str]]]) -> dict[int, Counter]:
    counts: dict[int, Counter] = defaultdict(Counter)
    for row in rows:
        if row.tag_id is None:
            continue
        for theme_id, sentiment in mentions.get(row.tag_id, []):
            counts[theme_id]["mentions"] += 1
            counts[theme_id][sentiment] += 1
    return counts


def _cell(c: Counter, analyzed: int) -> dict:
    mentions = c["mentions"]
    return {
        "mentions": mentions,
        "share": mentions / analyzed if analyzed else 0.0,
        "positive": c["positive"],
        "negative": c["negative"],
        "mixed": c["mixed"],
        "net": (c["positive"] - c["negative"]) / mentions if mentions else None,
    }


def _overall(rows: list[ReviewRow]) -> dict:
    """Overall impression across analyzed reviews: counts and shares of each sentiment."""
    analyzed = [r for r in rows if r.tag_id is not None]
    counts = Counter(r.overall or "none" for r in analyzed)
    n = len(analyzed)
    return {
        key: {"count": counts.get(key, 0), "share": counts.get(key, 0) / n if n else 0.0}
        for key in ("positive", "mixed", "negative", "none")
    }


def highlights(themes: list[dict], limit: int = 1) -> tuple[list[dict], list[dict]]:
    """The most praised and most criticized themes, from rows with positive, negative and mentions.

    Ranked by how many more positive than negative mentions a theme has (and the reverse), so a
    theme that is widely discussed but splits players doesn't count as the most praised.
    """
    praised = sorted((t for t in themes if t["positive"] > t["negative"]), key=lambda t: (t["negative"] - t["positive"], -t["mentions"]))
    criticized = sorted((t for t in themes if t["negative"] > t["positive"]), key=lambda t: (t["positive"] - t["negative"], -t["mentions"]))
    return praised[:limit], criticized[:limit]


def _segment_label(dimension: str, value) -> str:
    if dimension == "playtime_band":
        return PLAYTIME_BAND_LABELS.get(value, value)
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def compute(rows: list[ReviewRow], mentions: dict[int, list[tuple[int, str]]], themes: list[Theme]) -> dict:
    analyzed_rows = [r for r in rows if r.tag_id is not None]
    analyzed = len(analyzed_rows)
    overall = _theme_counts(rows, mentions)

    # Monthly trend
    by_month: dict[str, list[ReviewRow]] = defaultdict(list)
    for r in rows:
        by_month[_month(r.created)].append(r)
    months = sorted(by_month)
    month_stats = []
    monthly_theme: dict[int, list[dict]] = defaultdict(list)
    for m in months:
        mrows = by_month[m]
        m_analyzed = sum(1 for r in mrows if r.tag_id is not None)
        month_stats.append(
            {
                "month": m,
                "reviews": len(mrows),
                "analyzed": m_analyzed,
                "positive_votes": sum(1 for r in mrows if r.voted_up),
                "overall": _overall(mrows),
            }
        )
        counts = _theme_counts(mrows, mentions)
        for t in themes:
            monthly_theme[t.id].append({"month": m, **_cell(counts.get(t.id, Counter()), m_analyzed)})

    # Splits
    languages = Counter(r.language for r in analyzed_rows)
    top_langs = {lang for lang, _ in languages.most_common(TOP_LANGUAGES)}
    dimensions = {
        "playtime_band": lambda r: r.playtime_band,
        "early_access": lambda r: r.early_access,
        "language": lambda r: r.language if r.language in top_langs else "other",
        "steam_deck": lambda r: r.steam_deck,
        "refunded": lambda r: r.refunded,
        "vote": lambda r: "positive" if r.voted_up else "negative",
    }
    splits = {}
    for dim, key_fn in dimensions.items():
        groups: dict = defaultdict(list)
        for r in rows:
            groups[key_fn(r)].append(r)
        if dim == "playtime_band":
            order = [b for b in PLAYTIME_BANDS if b in groups]
        else:
            order = sorted(groups, key=lambda v: -len(groups[v]))
        segments = []
        for value in order:
            grows = groups[value]
            g_analyzed = sum(1 for r in grows if r.tag_id is not None)
            counts = _theme_counts(grows, mentions)
            segments.append(
                {
                    "segment": str(value).lower() if isinstance(value, bool) else value,
                    "label": _segment_label(dim, value),
                    "reviews": len(grows),
                    "analyzed": g_analyzed,
                    "themes": {t.key: _cell(counts.get(t.id, Counter()), g_analyzed) for t in themes},
                }
            )
        splits[dim] = segments

    # Developer responses
    responded = [r for r in rows if r.has_dev_response]
    delays = [
        (r.dev_responded_at - r.created) / 3600 for r in responded if r.dev_responded_at and r.dev_responded_at >= r.created
    ]

    theme_rows = []
    for t in themes:
        theme_rows.append(
            {
                "id": t.id,
                "key": t.key,
                "name": t.name,
                "definition": t.definition,
                **_cell(overall.get(t.id, Counter()), analyzed),
                "monthly": monthly_theme[t.id],
            }
        )
    theme_rows.sort(key=lambda x: -x["mentions"])

    other = sum(1 for r in analyzed_rows if r.other_flag)
    return {
        "counts": {
            "reviews": len(rows),
            "with_content": sum(1 for r in rows if r.has_content),
            "no_content": sum(1 for r in rows if not r.has_content),
            "analyzed": analyzed,
            "pending": sum(1 for r in rows if r.has_content and r.tag_id is None),
            "positive_votes": sum(1 for r in rows if r.voted_up),
        },
        "themes": theme_rows,
        "months": month_stats,
        "splits": splits,
        "developer_response": {
            "responded": len(responded),
            "rate": len(responded) / len(rows) if rows else 0.0,
            "median_hours": median(delays) if delays else None,
        },
        "other": {"count": other, "share": other / analyzed if analyzed else 0.0},
        "overall": _overall(rows),
    }


def theme_stats(session: Session, title_id: int, codebook_id: int | None, themes: list[Theme], f: Filters) -> dict:
    rows = load_rows(session, title_id, codebook_id, f)
    mentions = load_mentions(session, [r.tag_id for r in rows if r.tag_id is not None])
    return compute(rows, mentions, themes)
