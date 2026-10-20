"""The one-title PDF report, built as an HTML page that Chromium prints.

Sections: cover, headline numbers, reviews per month, overall impression, executive summary, theme
table, the top praised and criticized themes with verbatim quotes, and how the report was made.
Every quote is re-checked against the review text here and dropped if it is not found there.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.aggregate import current_tag_join, highlights, review_filter_clauses
from app.api.common import review_url
from app.exports.charts import monthly_rows, volume_chart
from app.exports.common import Brand, date_range_text, describe_filters, language_name
from app.exports.html import (
    brandbar,
    document,
    esc,
    floor_pct,
    legend,
    net_text,
    pct,
    sentiment_bar,
    share_bar,
    tile,
)
from app.exports.tables import ExportContext, verified_quote
from app.models import Review, ReviewTag, Summary, ThemeMention
from app.portfolio import snapshot

STATUS_LABELS = {"released": "Released", "early_access": "Early Access", "coming_soon": "Coming soon", "unreleased": "Unreleased"}
TOP_THEMES = 3
QUOTES_PER_THEME = 3
MIN_QUOTE, MAX_QUOTE = 12, 420


@dataclass
class Quote:
    text: str
    url: str
    recommended: bool
    date: str
    language: str
    playtime_hours: float | None
    gist: str | None


def theme_quotes(session: Session, ctx: ExportContext, theme_id: int, sentiment: str, limit: int = QUOTES_PER_THEME) -> list[Quote]:
    """Verified quotes for one theme and sentiment within the filters, most helpful first. English
    quotes come first because the reader can check them directly; others carry the English gist."""
    if ctx.codebook is None:
        return []
    rows = session.execute(
        select(Review, ThemeMention.quote_start, ThemeMention.quote_end, ReviewTag.gist_en)
        .join(ReviewTag, current_tag_join(ctx.codebook.id))
        .join(ThemeMention, ThemeMention.review_tag_id == ReviewTag.id)
        .where(
            *review_filter_clauses(ctx.title.id, ctx.filters),
            Review.content_status == "ok",
            ThemeMention.theme_id == theme_id,
            ThemeMention.sentiment == sentiment,
            ThemeMention.quote_status == "ok",
        )
    ).all()
    rows.sort(key=lambda r: (r[0].language != "english", -(r[0].votes_up or 0), -(r[0].timestamp_created or 0)))
    out: list[Quote] = []
    for review, start, end, gist in rows:
        text = verified_quote(review.display_text, start, end)
        if text is None or not MIN_QUOTE <= len(text) <= MAX_QUOTE:
            continue
        out.append(
            Quote(
                text=text,
                url=review_url(review),
                recommended=bool(review.voted_up),
                date=datetime.fromtimestamp(review.timestamp_created or 0, UTC).date().isoformat(),
                language=review.language or "",
                playtime_hours=round(review.author_playtime_at_review / 60, 1) if review.author_playtime_at_review is not None else None,
                gist=gist if review.language != "english" else None,
            )
        )
        if len(out) == limit:
            break
    return out


def quote_html(q: Quote, tone: str) -> str:
    by = [("Recommended" if q.recommended else "Not recommended"), q.date, language_name(q.language)]
    if q.playtime_hours is not None:
        by.append(f"{q.playtime_hours:g} hours at review")
    gist = f'<div class="gist">English gist (machine-written, not a quote): {esc(q.gist)}</div>' if q.gist else ""
    return (
        f'<div class="quote {tone}"><div class="text">&ldquo;{esc(q.text)}&rdquo;</div>{gist}'
        f'<div class="by">{esc(" · ".join(by))} &middot; <a href="{esc(q.url)}">Read on Steam</a></div></div>'
    )


def reviews_date_span(session: Session, ctx: ExportContext) -> tuple[str | None, str | None]:
    first, last = session.execute(
        select(func.min(Review.timestamp_created), func.max(Review.timestamp_created)).where(*review_filter_clauses(ctx.title.id, ctx.filters))
    ).one()
    as_date = lambda ts: datetime.fromtimestamp(ts, UTC).date().isoformat() if ts else None  # noqa: E731
    return as_date(first), as_date(last)


def _summary_section(session: Session, ctx: ExportContext) -> str:
    s = session.scalar(
        select(Summary).where(Summary.title_id == ctx.title.id, Summary.app_id == ctx.app_id).order_by(Summary.id.desc()).limit(1)
    )
    if s is None:
        return ""
    content = s.content
    ids = {i for item in content.get("strengths", []) + content.get("problems", []) for i in item.get("review_ids", [])}
    ids |= set(content.get("last_30_days", {}).get("review_ids", []))
    urls = {r.recommendation_id: review_url(r) for r in session.scalars(select(Review).where(Review.recommendation_id.in_(ids or {"-"})))}
    names = {t.key: t.name for t in ctx.themes}

    def cites(review_ids: list[str]) -> str:
        links = [f'<a href="{esc(urls[i])}">Review {esc(i)}</a>' for i in review_ids if i in urls]
        return f'<div class="cites">{"".join(links)}</div>' if links else ""

    def points(items: list[dict]) -> str:
        if not items:
            return '<p class="muted">None stood out.</p>'
        return "".join(
            f'<div class="point"><b>{esc(p["headline"])}</b><span class="muted small">{esc(names.get(p["theme_key"], p["theme_key"]))}</span>'
            f'<p>{esc(p["detail"])}</p>{cites(p.get("review_ids", []))}</div>'
            for p in items
        )

    last = content.get("last_30_days", {})
    return f"""
    <h2>Executive summary</h2>
    <div class="two">
      <div><h3 class="pos-ink">Top strengths</h3>{points(content.get("strengths", []))}</div>
      <div><h3 class="neg-ink">Top problems</h3>{points(content.get("problems", []))}</div>
    </div>
    <div class="keep"><h3>Last 30 days</h3><p>{esc(last.get("text", ""))}</p>{cites(last.get("review_ids", []))}</div>
    <p class="muted small">Written by {esc(s.model)} on {s.created_at:%B %-d, %Y} from {content.get("reviews_analyzed", 0)} analyzed reviews.
    It covers all of this game's reviews, so the filters on the cover don't change it. Each review number links to the review on Steam.</p>
    """


def _top_themes_section(session: Session, ctx: ExportContext) -> str:
    praised, criticized = highlights(ctx.stats["themes"], limit=TOP_THEMES)
    by_key = {t.key: t for t in ctx.themes}

    def block(rows: list[dict], sentiment: str, tone: str) -> str:
        if not rows:
            return '<p class="muted">No theme leaned this way in these reviews.</p>'
        out = []
        for t in rows:
            quotes = theme_quotes(session, ctx, by_key[t["key"]].id, sentiment)
            body = "".join(quote_html(q, tone) for q in quotes) or '<p class="muted small">No quote under these filters.</p>'
            out.append(
                f'<div class="keep"><h3>{esc(t["name"])}</h3>'
                f'<p class="muted small">{pct(t["share"])} of analyzed reviews mention it: {t["positive"]} positive, {t["mixed"]} mixed, '
                f'{t["negative"]} negative (net {net_text(t["net"])}).</p></div>{body}'
            )
        return "".join(out)

    return f"""
    <h2 class="page">What players praise most</h2>
    <p class="muted small">The themes with the most positive mentions after taking away their negative ones, with quotes copied exactly from reviews.</p>
    {block(praised, "positive", "pos-q")}
    <h2>What players criticize most</h2>
    <p class="muted small">The themes with the most negative mentions after taking away their positive ones.</p>
    {block(criticized, "negative", "neg-q")}
    """


def _theme_table(ctx: ExportContext) -> str:
    rows = sorted(ctx.stats["themes"], key=lambda t: -t["share"])
    body = "".join(
        f"""<tr>
          <td style="width:40%"><b>{esc(t["name"])}</b><div class="muted small">{esc(t["definition"])}</div></td>
          <td style="width:18%"><div style="display:flex;gap:6pt;align-items:center"><div style="flex:1">{share_bar(t["share"])}</div><span>{pct(t["share"])}</span></div>
              <div class="muted small">{t["mentions"]} reviews</div></td>
          <td style="width:32%">{sentiment_bar(t["positive"], t["mixed"], t["negative"])}</td>
          <td class="num" style="width:10%"><b class="{"pos-ink" if (t["net"] or 0) >= 0 else "neg-ink"}">{net_text(t["net"])}</b></td>
        </tr>"""
        for t in rows
    )
    return f"""
    <h2>Themes</h2>
    <p class="muted small">Share is the percent of the {ctx.stats["counts"]["analyzed"]} analyzed reviews that mention the theme. Net runs from -100
    (all negative) to +100 (all positive). {pct(ctx.stats["other"]["share"])} of reviews raised points no theme covers.</p>
    {legend([("pos", "Positive"), ("mix", "Mixed"), ("neg", "Negative")])}
    <table><thead><tr><th>Theme</th><th>Share</th><th>Sentiment</th><th class="num">Net</th></tr></thead><tbody>{body}</tbody></table>
    """


def _overall(ctx: ExportContext) -> str:
    o = ctx.stats["overall"]
    total = sum(v["count"] for v in o.values())
    if not total:
        return ""
    parts = [("positive", "pos", "Positive"), ("mixed", "mix", "Mixed"), ("negative", "neg", "Negative"), ("none", "none", "No overall view")]
    spans = "".join(f'<span class="{cls}" style="width:{100 * o[k]["count"] / total:.1f}%"></span>' for k, cls, _ in parts if o[k]["count"])
    return f"""
    <div class="keep"><h2>Overall impression</h2>
    <p class="muted small">What each analyzed review says about the game as a whole, such as "great game" or "waste of money". It is counted on its
    own, so it never adds to a theme.</p>
    <div class="split" style="height:9pt">{spans}</div>
    {legend([(cls, f"{label} {pct(o[k]['share'])} ({o[k]['count']})") for k, cls, label in parts])}</div>
    """


def _methodology(session: Session, ctx: ExportContext, span: str) -> str:
    c = ctx.stats["counts"]
    filters = describe_filters(ctx.filters)
    items = [
        f"Reviews written {esc(span)}. {c['reviews']} reviews matched the filters, {c['with_content']} had enough text to analyze, and "
        f"{c['analyzed']} were analyzed. Reviews with almost no text (such as \"good\" or \"10/10\") are counted but not analyzed.",
        "Filters: " + (esc("; ".join(filters)) if filters else "none, so every review is included") + ".",
        "Reviews come from Steam's official review API, in every language. Non-English reviews are read in their own language and quoted as written.",
    ]
    if ctx.codebook:
        approved = f", approved {ctx.codebook.approved_at:%B %-d, %Y}" if ctx.codebook.approved_at else ""
        items.append(
            f"Themes: codebook version {ctx.codebook.version}{esc(approved)}, with {len(ctx.themes)} themes. The analysis model proposed them from a sample "
            "of this game's own reviews and the team reviewed them before tagging."
        )
        items.append(
            f"Tagging: {esc(ctx.tagging_model)} read each review and marked the themes it mentions, the sentiment of each, and the reviewer's "
            "overall impression. Shares are of analyzed reviews."
        )
        qa = ((ctx.run.details or {}).get("qa") if ctx.run else None) or {}
        if qa.get("reviews_checked"):
            o = qa.get("overall", {})
            kappa = o.get("mean_kappa")
            items.append(
                f"Quality check: {esc(qa.get('model') or ctx.analysis_model)} tagged {qa['reviews_checked']} random reviews again without seeing the "
                f"first tags. Both agreed on whether a theme was mentioned {pct(o.get('presence_agreement'))} of the time"
                + (f" (average kappa {kappa:.2f})" if kappa is not None else "")
                + "."
            )
    items.append(
        "Quotes are copied exactly from the review, checked against the stored review text when this report was made, and link to the review on Steam. "
        "Quotes that did not match were left out."
    )
    items.append(f"Models: tagging {esc(ctx.tagging_model or 'none')}; theme discovery, quality check and summary {esc(ctx.analysis_model or 'none')}.")
    return '<h2>How this report was made</h2><div class="note"><ul>' + "".join(f"<li>{i}</li>" for i in items) + "</ul></div>"


def title_report_html(session: Session, ctx: ExportContext, brand: Brand) -> str:
    c = ctx.stats["counts"]
    first, last = reviews_date_span(session, ctx)
    span = date_range_text(ctx.filters, first, last)
    filters = describe_filters(ctx.filters)
    steam = snapshot(session, ctx.title.id, ctx.app_id)
    image = (
        f'<img class="header-img" src="{esc(ctx.title.header_image_url)}" alt="" onerror="this.remove()">' if ctx.title.header_image_url else ""
    )
    developers = ", ".join(ctx.title.developers or [])

    cover = f"""
    <section class="cover">
      {brandbar(brand)}
      <div class="band"></div>
      <div class="kicker">Steam review report</div>
      <h1>{esc(ctx.subject)}</h1>
      <div class="muted">{esc(developers)}{" &middot; " if developers else ""}{esc(STATUS_LABELS.get(ctx.title.status, ctx.title.status))}</div>
      {image}
      <div class="meta">
        <div><b>Reviews:</b> {c["reviews"]} written {esc(span)}</div>
        <div><b>Filters:</b> {esc("; ".join(filters)) if filters else "None, every review is included"}</div>
        <div><b>Themes:</b> {f"codebook version {ctx.codebook.version}, {c['analyzed']} reviews analyzed" if ctx.codebook else "not analyzed yet"}</div>
        <div class="muted small">Made {ctx.generated_at:%B %-d, %Y at %H:%M} UTC</div>
      </div>
    </section>"""

    glance = f"""
    <h2 class="page">At a glance</h2>
    <div class="tiles">
      {tile("Reviews", str(c["reviews"]), f"{c['with_content']} with text to analyze")}
      {tile("Recommended", floor_pct(c["positive_votes"], c["reviews"]), f"{c['positive_votes']} of {c['reviews']} reviews")}
      {tile("Steam rating", (steam or {}).get("review_score_desc") or "None yet", f"All {steam['total_reviews']} reviews on Steam, before filters" if steam and steam["total_reviews"] else "")}
      {tile("Analyzed", str(c["analyzed"]), "Read by the tagging model" if ctx.codebook else "No approved codebook yet")}
    </div>
    <div class="keep"><h2>Reviews per month</h2>
    {legend([("pos", "Recommended (above the line)"), ("neg", "Not recommended (below)")])}
    {volume_chart(monthly_rows(ctx.stats["months"]), brand.palette)}</div>
    """

    analyzed = bool(ctx.codebook and c["analyzed"])
    body = cover + glance
    if analyzed:
        body += _overall(ctx) + _summary_section(session, ctx) + _theme_table(ctx) + _top_themes_section(session, ctx)
    else:
        body += '<p class="muted">Themes, quotes and the summary appear once this game\'s reviews are analyzed.</p>'
    body += _methodology(session, ctx, span)
    return document(brand, f"{ctx.subject}: Steam review report", body)
