"""Charts for the PDF reports, drawn as SVG by hand (the reports need only a few simple shapes)."""

from app.exports.html import esc

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _nice_max(value: int) -> int:
    """A round number at or above value, for the axis."""
    if value <= 5:
        return 5
    for step in (5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 5000):
        if value <= step * 4:
            return -(-value // step) * step
    return value


def month_label(month: str) -> str:
    y, m = month.split("-")
    return f"{MONTHS[int(m) - 1]} {y}"


def volume_chart(rows: list[dict], palette: dict, width: int = 690, height: int = 190) -> str:
    """Reviews per month: recommended above the line, not recommended below it.

    rows: [{"month": "2026-03", "positive": n, "negative": n}] with every month present.
    """
    if not rows:
        return '<p class="muted">No reviews in this range.</p>'
    left, right, top, bottom = 34, 6, 8, 22
    plot_w, plot_h = width - left - right, height - top - bottom
    up_max = _nice_max(max(r["positive"] for r in rows))
    down_max = _nice_max(max(r["negative"] for r in rows)) if any(r["negative"] for r in rows) else 0
    scale = plot_h / (up_max + down_max)
    zero = top + up_max * scale
    slot = plot_w / len(rows)
    bar = min(24.0, max(1.5, slot * 0.7))

    parts = []
    # Gridlines and their labels: hairlines one step off the background.
    for value in (up_max // 2, up_max):
        y = zero - value * scale
        parts.append(f'<line x1="{left}" x2="{width - right}" y1="{y:.1f}" y2="{y:.1f}" stroke="{palette["lineSoft"]}" stroke-width="1"/>')
        parts.append(f'<text x="{left - 4}" y="{y + 3:.1f}" text-anchor="end" font-size="8" fill="{palette["muted"]}">{value}</text>')
    if down_max:
        y = zero + down_max * scale
        parts.append(f'<line x1="{left}" x2="{width - right}" y1="{y:.1f}" y2="{y:.1f}" stroke="{palette["lineSoft"]}" stroke-width="1"/>')
        parts.append(f'<text x="{left - 4}" y="{y + 3:.1f}" text-anchor="end" font-size="8" fill="{palette["muted"]}">{down_max}</text>')

    radius = min(3.0, bar / 2)
    for i, r in enumerate(rows):
        x = left + i * slot + (slot - bar) / 2
        if r["positive"]:
            h = r["positive"] * scale
            parts.append(_bar(x, zero - h, bar, h, radius, palette["positive"], up=True))
        if r["negative"]:
            h = r["negative"] * scale
            parts.append(_bar(x, zero, bar, h, radius, palette["negative"], up=False))
    parts.append(f'<line x1="{left}" x2="{width - right}" y1="{zero:.1f}" y2="{zero:.1f}" stroke="{palette["lineStrong"]}" stroke-width="1"/>')

    # Axis labels: each January's year over long ranges, otherwise about eight months across.
    long_range = len(rows) > 24
    step = max(1, round(len(rows) / 8))
    for i, r in enumerate(rows):
        if long_range and not r["month"].endswith("-01"):
            continue
        if not long_range and i % step:
            continue
        label = r["month"][:4] if long_range else month_label(r["month"])
        x = left + i * slot + slot / 2
        parts.append(f'<text x="{x:.1f}" y="{height - 6}" text-anchor="middle" font-size="8" fill="{palette["muted"]}">{esc(label)}</text>')

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="Reviews per month">{"".join(parts)}</svg>'
    )


def _bar(x: float, y: float, w: float, h: float, r: float, color: str, up: bool) -> str:
    """A bar with rounded corners on its outer end only, square at the baseline."""
    r = min(r, h)
    if up:
        d = f"M{x:.1f},{y + h:.1f} V{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} H{x + w - r:.1f} Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} V{y + h:.1f} Z"
    else:
        d = f"M{x:.1f},{y:.1f} V{y + h - r:.1f} Q{x:.1f},{y + h:.1f} {x + r:.1f},{y + h:.1f} H{x + w - r:.1f} Q{x + w:.1f},{y + h:.1f} {x + w:.1f},{y + h - r:.1f} V{y:.1f} Z"
    return f'<path d="{d}" fill="{color}"/>'


def monthly_rows(months: list[dict]) -> list[dict]:
    """theme_stats months, with empty months filled in, as positive/negative counts."""
    from app.exports.tables import month_range

    if not months:
        return []
    by = {m["month"]: m for m in months}
    out = []
    for month in month_range(months[0]["month"], months[-1]["month"]):
        m = by.get(month)
        pos = m["positive_votes"] if m else 0
        out.append({"month": month, "positive": pos, "negative": (m["reviews"] - pos) if m else 0})
    return out
