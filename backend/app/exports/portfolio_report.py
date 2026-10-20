"""The portfolio PDF: a summary page across all titles, then one page per title with reviews."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.aggregate import Filters, highlights
from app.config import Settings
from app.exports.charts import monthly_rows, volume_chart
from app.exports.common import Brand, describe_filters
from app.exports.html import brandbar, document, esc, floor_pct, legend, net_text, pct, sentiment_bar, tile
from app.exports.report import STATUS_LABELS, quote_html, theme_quotes
from app.exports.tables import ExportContext, build_context
from app.models import Summary, Title
from app.portfolio import snapshot, trend, votes
from app.timeutil import utcnow

TOP = 3


def _app_for(session: Session, title: Title) -> int:
    """The main game, or the demo when every review so far is on the demo (GodsTV before launch)."""
    if title.demo_app_id and not votes(session, title.id, title.steam_app_id)[0] and votes(session, title.id, title.demo_app_id)[0]:
        return title.demo_app_id
    return title.steam_app_id


def _trend_text(t: dict) -> str:
    last, prev = t["last"], t["previous"]
    if not last["reviews"]:
        return "No reviews"
    text = f"{last['reviews']} reviews, {last['positive_share'] * 100:.0f}% recommended"
    if prev["reviews"] and prev["positive_share"] is not None:
        delta = round((last["positive_share"] - prev["positive_share"]) * 100)
        if delta:
            text += f" ({'up' if delta > 0 else 'down'} {abs(delta)} pts)"
    return text


def _title_page(session: Session, ctx: ExportContext, brand: Brand, now) -> str:
    c = ctx.stats["counts"]
    steam = snapshot(session, ctx.title.id, ctx.app_id)
    t30 = trend(session, ctx.title.id, ctx.app_id, now)
    developers = ", ".join(ctx.title.developers or [])
    out = [
        f"""<section class="page">
        <div class="muted small">{esc(developers)}{" &middot; " if developers else ""}{esc(STATUS_LABELS.get(ctx.title.status, ctx.title.status))}</div>
        <h1 style="font-size:18pt">{esc(ctx.subject)}</h1>
        <div class="tiles">
          {tile("Reviews", str(c["reviews"]), f"{c['analyzed']} analyzed")}
          {tile("Recommended", floor_pct(c["positive_votes"], c["reviews"]), f"{c['positive_votes']} of {c['reviews']}")}
          {tile("Steam rating", (steam or {}).get("review_score_desc") or "None yet", "All reviews on Steam")}
          {tile("Last 30 days", str(t30["last"]["reviews"]), _trend_text(t30))}
        </div>
        <h3>Reviews per month</h3>
        {legend([("pos", "Recommended (above the line)"), ("neg", "Not recommended (below)")])}
        {volume_chart(monthly_rows(ctx.stats["months"]), brand.palette, height=130)}"""
    ]
    if ctx.codebook and c["analyzed"]:
        praised, criticized = highlights(ctx.stats["themes"], limit=TOP)
        by_key = {t.key: t for t in ctx.themes}

        def column(rows: list[dict], sentiment: str, tone: str, heading: str, ink: str) -> str:
            items = []
            for i, t in enumerate(rows):
                q = theme_quotes(session, ctx, by_key[t["key"]].id, sentiment, limit=1) if i == 0 else []
                items.append(
                    f'<div class="point"><b>{esc(t["name"])}</b>'
                    f'<span class="muted small">{pct(t["share"])} of reviews, net {net_text(t["net"])}</span>'
                    f'{sentiment_bar(t["positive"], t["mixed"], t["negative"])}{"".join(quote_html(x, tone) for x in q)}</div>'
                )
            return f'<div><h3 class="{ink}">{heading}</h3>{"".join(items) or "<p class=muted>None stood out.</p>"}</div>'

        out.append(
            '<div class="two">'
            + column(praised, "positive", "pos-q", "Most praised", "pos-ink")
            + column(criticized, "negative", "neg-q", "Most criticized", "neg-ink")
            + "</div>"
        )
        s = session.scalar(
            select(Summary).where(Summary.title_id == ctx.title.id, Summary.app_id == ctx.app_id).order_by(Summary.id.desc()).limit(1)
        )
        if s:
            heads = lambda items: "".join(f"<li>{esc(p['headline'])}</li>" for p in items)  # noqa: E731
            out.append(
                f'<div class="keep"><h3>From the executive summary</h3><div class="two small">'
                f'<div><b class="pos-ink">Strengths</b><ul>{heads(s.content.get("strengths", []))}</ul></div>'
                f'<div><b class="neg-ink">Problems</b><ul>{heads(s.content.get("problems", []))}</ul></div></div></div>'
            )
    else:
        out.append('<p class="muted">Themes appear once this game\'s reviews are analyzed.</p>')
    out.append("</section>")
    return "".join(out)


def portfolio_report_html(session: Session, settings: Settings, brand: Brand, date_from: date | None, date_to: date | None) -> str:
    now = utcnow()
    filters = Filters(date_from=date_from, date_to=date_to)
    rows, pages = [], []
    for title in session.scalars(select(Title).where(Title.archived_at.is_(None)).order_by(Title.id)):
        app_id = _app_for(session, title)
        ctx = build_context(session, settings, title, app_id, Filters(date_from=date_from, date_to=date_to))
        c = ctx.stats["counts"]
        steam = snapshot(session, title.id, app_id)
        if not c["reviews"]:
            rows.append(f'<tr><td><b>{esc(ctx.subject)}</b></td><td colspan="6" class="muted">No reviews yet</td></tr>')
            continue
        praised, criticized = highlights(ctx.stats["themes"]) if ctx.codebook and c["analyzed"] else ([], [])
        if not c["analyzed"]:
            top_good, top_bad = '<span class="muted">Not analyzed yet</span>', ""
        else:
            top_good = esc(praised[0]["name"]) if praised else ""
            top_bad = esc(criticized[0]["name"]) if criticized else ""
        rows.append(
            f"""<tr><td><b>{esc(ctx.subject)}</b></td><td class="num">{c["reviews"]}</td>
            <td class="num">{floor_pct(c["positive_votes"], c["reviews"])}</td><td>{esc((steam or {}).get("review_score_desc") or "")}</td>
            <td>{esc(_trend_text(trend(session, title.id, app_id, now)))}</td>
            <td>{top_good}</td><td>{top_bad}</td></tr>"""
        )
        pages.append(_title_page(session, ctx, brand, now))

    described = describe_filters(filters)
    summary = f"""
    <section>
      {brandbar(brand)}
      <div class="cover" style="height:auto"><div class="band"></div></div>
      <div class="kicker muted small" style="text-transform:uppercase;letter-spacing:.08em;font-weight:600">Portfolio report</div>
      <h1>{esc(brand.company_name)} on Steam</h1>
      <p class="muted">{esc(described[0]) if described else "All reviews"}. Made {now:%B %-d, %Y}. Steam ratings and the last 30 days are not
      affected by the date range. Recommended shares are rounded down, the way Steam shows them.</p>
      <table style="margin-top:12pt">
        <thead><tr><th>Title</th><th class="num">Reviews</th><th class="num">Recommended</th><th>Steam rating</th><th>Last 30 days</th>
        <th>Most praised</th><th>Most criticized</th></tr></thead>
        <tbody>{"".join(rows)}</tbody>
      </table>
      <p class="muted small" style="margin-top:10pt">One page follows for each title with reviews. Most praised and most criticized are the themes with the
      most positive (or negative) mentions after taking away the opposite ones.</p>
    </section>"""
    return document(brand, f"{brand.company_name} portfolio report", summary + "".join(pages))
