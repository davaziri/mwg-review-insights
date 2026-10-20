"""Shared building blocks for the PDF reports: page styles, number formats and small HTML parts.

Everything from the database (theme names, review text) goes through esc() before it is put in
the page, so a review can never add markup to a report.
"""

from html import escape

from app.exports.common import Brand


def esc(value) -> str:
    return escape("" if value is None else str(value), quote=True)


def pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.0f}%"


def floor_pct(part: int, whole: int) -> str:
    """Rounded down, the way Steam shows its percentages."""
    return f"{int(part * 100 // whole)}%" if whole else "n/a"


def net_text(net: float | None) -> str:
    if net is None:
        return "n/a"
    n = round(net * 100)
    return f"+{n}" if n > 0 else str(n)


def styles(brand: Brand) -> str:
    p = brand.palette
    return f"""
    * {{ box-sizing: border-box; }}
    html {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    body {{ margin: 0; font-family: "Inter", "Segoe UI", "Helvetica Neue", Arial, "Noto Sans", "Noto Sans CJK SC", "WenQuanYi Zen Hei", sans-serif;
           color: {p['ink']}; font-size: 9.5pt; line-height: 1.45; }}
    a {{ color: {p['link']}; text-decoration: none; }}
    h1 {{ font-size: 24pt; margin: 0 0 4pt; line-height: 1.15; }}
    h2 {{ font-size: 13pt; margin: 18pt 0 6pt; }}
    h3 {{ font-size: 10.5pt; margin: 10pt 0 4pt; }}
    p {{ margin: 0 0 6pt; }}
    .muted {{ color: {p['muted']}; }}
    .small {{ font-size: 8pt; }}
    .page {{ break-before: page; }}
    .keep {{ break-inside: avoid; }}
    .brandbar {{ display: flex; align-items: center; gap: 8pt; }}
    .brandbar img {{ width: 26pt; height: 26pt; }}
    .brandbar .name {{ font-weight: 600; font-size: 10pt; line-height: 1.2; }}
    .cover {{ height: 9.3in; display: flex; flex-direction: column; }}
    .cover .band {{ height: 6pt; background: {p['brand']}; border-radius: 3pt; margin: 18pt 0 36pt; }}
    .cover .kicker {{ text-transform: uppercase; letter-spacing: 0.08em; font-size: 8.5pt; color: {p['muted']}; font-weight: 600; }}
    .cover .header-img {{ width: 3.4in; border-radius: 4pt; margin-top: 18pt; }}
    .cover .meta {{ margin-top: auto; border-top: 1px solid {p['line']}; padding-top: 10pt; }}
    .cover .meta div {{ margin-bottom: 3pt; }}
    .tiles {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 8pt; margin: 8pt 0; }}
    .tile {{ border: 1px solid {p['line']}; border-radius: 5pt; padding: 7pt 9pt; }}
    .tile .label {{ font-size: 7.5pt; color: {p['muted']}; font-weight: 600; }}
    .tile .value {{ font-size: 15pt; font-weight: 600; margin-top: 2pt; }}
    .tile .detail {{ font-size: 7.5pt; color: {p['muted']}; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th {{ text-align: left; font-size: 7.5pt; text-transform: uppercase; letter-spacing: 0.05em; color: {p['muted']};
          border-bottom: 1px solid {p['line']}; padding: 4pt 6pt 4pt 0; font-weight: 600; }}
    td {{ border-bottom: 1px solid {p['lineSoft']}; padding: 5pt 6pt 5pt 0; vertical-align: top; }}
    tr {{ break-inside: avoid; }}
    td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .track {{ height: 6pt; background: {p['soft']}; border-radius: 3pt; overflow: hidden; }}
    .fill {{ height: 6pt; background: {p['brand']}; border-radius: 3pt; }}
    .split {{ display: flex; height: 6pt; gap: 1.5pt; }}
    .split span {{ display: block; height: 6pt; }}
    .split span:first-child {{ border-radius: 3pt 0 0 3pt; }}
    .split span:last-child {{ border-radius: 0 3pt 3pt 0; }}
    .split span:only-child {{ border-radius: 3pt; }}
    .pos {{ background: {p['positive']}; }} .mix {{ background: {p['mixed']}; }} .neg {{ background: {p['negative']}; }} .none {{ background: {p['neutral']}; }}
    .pos-ink {{ color: {p['positiveInk']}; }} .neg-ink {{ color: {p['negativeInk']}; }}
    .legend {{ display: flex; gap: 12pt; font-size: 8pt; color: {p['ink2']}; margin: 4pt 0; flex-wrap: wrap; }}
    .legend i {{ display: inline-block; width: 8pt; height: 8pt; border-radius: 2pt; margin-right: 4pt; vertical-align: -1pt; }}
    .two {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16pt; }}
    .point {{ margin-bottom: 8pt; break-inside: avoid; }}
    .point b {{ display: block; }}
    .cites {{ font-size: 7.5pt; }}
    .cites a {{ border: 1px solid {p['line']}; border-radius: 3pt; padding: 0 3pt; margin-right: 3pt; }}
    .quote {{ border-left: 2.5pt solid {p['lineStrong']}; padding: 3pt 0 3pt 8pt; margin: 5pt 0 7pt; break-inside: avoid; }}
    .quote.pos-q {{ border-color: {p['positive']}; }} .quote.neg-q {{ border-color: {p['negative']}; }}
    .quote .text {{ font-size: 9.5pt; }}
    .quote .by {{ font-size: 7.5pt; color: {p['muted']}; margin-top: 2pt; }}
    .quote .gist {{ font-size: 7.5pt; color: {p['ink2']}; margin-top: 2pt; }}
    .note {{ background: {p['subtle']}; border: 1px solid {p['line']}; border-radius: 5pt; padding: 8pt 10pt; }}
    .note li {{ margin-bottom: 3pt; }}
    """


def document(brand: Brand, title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{esc(title)}</title><style>{styles(brand)}</style></head>
<body>{body}</body></html>"""


def brandbar(brand: Brand) -> str:
    logo = f'<img src="{brand.logo_data_uri}" alt="">' if brand.logo_data_uri else ""
    return f'<div class="brandbar">{logo}<div><div class="name">{esc(brand.app_name)}</div><div class="muted small">{esc(brand.company_name)}</div></div></div>'


def footer_template(brand: Brand, label: str) -> str:
    """Chromium draws this at the bottom of every page; it fills in the page numbers."""
    return (
        '<div style="font-family: Arial, sans-serif; font-size: 7.5px; color: #64748b; width: 100%; padding: 0 0.6in; '
        'display: flex; justify-content: space-between;">'
        f"<span>{esc(brand.company_name)} &middot; {esc(label)}</span>"
        '<span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span></div>'
    )


def tile(label: str, value: str, detail: str = "") -> str:
    return f'<div class="tile"><div class="label">{esc(label)}</div><div class="value">{esc(value)}</div><div class="detail">{esc(detail)}</div></div>'


def share_bar(share: float) -> str:
    return f'<div class="track"><div class="fill" style="width:{min(100.0, share * 100):.1f}%"></div></div>'


def sentiment_bar(positive: int, mixed: int, negative: int) -> str:
    total = positive + mixed + negative
    if not total:
        return '<span class="muted small">No mentions</span>'
    parts = [(positive, "pos"), (mixed, "mix"), (negative, "neg")]
    spans = "".join(f'<span class="{cls}" style="width:{100 * n / total:.1f}%"></span>' for n, cls in parts if n)
    return f'<div class="split">{spans}</div><div class="muted small">{positive} positive, {mixed} mixed, {negative} negative</div>'


def legend(items: list[tuple[str, str]]) -> str:
    return '<div class="legend">' + "".join(f'<span><i class="{cls}"></i>{esc(label)}</span>' for cls, label in items) + "</div>"
