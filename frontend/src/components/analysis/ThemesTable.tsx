import { useState } from "react";
import { Link } from "react-router";

import type { ThemeStat, ThemeStats } from "../../api/types";
import { pct } from "../../lib/format";
import { monthLabel, monthRange } from "../charts/parts";
import { Sparkline, type SparkPoint } from "../charts/Sparkline";
import { Card } from "../ui";

type SortKey = "share" | "net" | "negative" | "name";


export function SentimentBar({ t }: { t: Pick<ThemeStat, "mentions" | "positive" | "mixed" | "negative"> }) {
  if (!t.mentions) return <span className="text-xs text-faint">No mentions</span>;
  const parts = [
    { n: t.positive, cls: "bg-positive" },
    { n: t.mixed, cls: "bg-mixed" },
    { n: t.negative, cls: "bg-negative" },
  ].filter((x) => x.n > 0);
  return (
    <div>
      <div className="flex h-2.5 w-full gap-[2px]" role="img" aria-label={`${t.positive} positive, ${t.mixed} mixed, ${t.negative} negative`}>
        {parts.map((x, i) => (
          <div
            key={x.cls}
            className={`${x.cls} ${i === 0 ? "rounded-l" : ""} ${i === parts.length - 1 ? "rounded-r" : ""}`}
            style={{ width: `${(100 * x.n) / t.mentions}%` }}
          />
        ))}
      </div>
      <div className="mt-0.5 text-xs text-muted tabular-nums">
        {t.positive} positive, {t.mixed} mixed, {t.negative} negative
      </div>
    </div>
  );
}

const TREND_POINTS = 12;
const MIN_PERIOD_REVIEWS = 5;

/** A theme's share over the selected dates in up to 12 equal periods, ending at the latest month.
 * Periods with fewer than 5 analyzed reviews are left out: one or two reviews swing the share. */
function trendPoints(t: ThemeStat, stats: ThemeStats): SparkPoint[] {
  if (!stats.months.length) return [];
  const months = monthRange(stats.months[0].month, stats.months[stats.months.length - 1].month);
  const size = Math.ceil(months.length / TREND_POINTS);
  const analyzed = new Map(stats.months.map((m) => [m.month, m.analyzed]));
  const cells = new Map(t.monthly.map((c) => [c.month, c.mentions]));
  const points: SparkPoint[] = [];
  for (let end = months.length; end > 0; end -= size) {
    const chunk = months.slice(Math.max(0, end - size), end);
    const n = chunk.reduce((a, m) => a + (analyzed.get(m) ?? 0), 0);
    const mentions = chunk.reduce((a, m) => a + (cells.get(m) ?? 0), 0);
    const first = chunk[0];
    const last = chunk[chunk.length - 1];
    const period =
      chunk.length === 1 ? monthLabel(first) : first.slice(0, 4) === last.slice(0, 4) ? `${monthLabel(first).slice(0, 3)} to ${monthLabel(last)}` : `${monthLabel(first)} to ${monthLabel(last)}`;
    points.unshift({ period, analyzed: n, mentions, share: n >= MIN_PERIOD_REVIEWS ? mentions / n : null });
  }
  return points;
}

export function ThemesTable({ stats, titleId, search }: { stats: ThemeStats; titleId: number; search: string }) {
  const [sort, setSort] = useState<SortKey>("share");
  const rows = [...stats.themes].sort((a, b) => {
    if (sort === "net") return (a.net ?? 0) - (b.net ?? 0);
    if (sort === "negative") return b.negative - a.negative;
    if (sort === "name") return a.name.localeCompare(b.name);
    return b.share - a.share;
  });
  const header = (key: SortKey, label: string, hint: string) => (
    <button
      type="button"
      title={hint}
      className={`uppercase tracking-wide ${sort === key ? "text-ink" : ""}`}
      onClick={() => setSort(key)}
      aria-pressed={sort === key}
    >
      {label}
      {sort === key ? " ↓" : ""}
    </button>
  );

  return (
    <Card title="Themes">
      <p className="mb-3 text-xs text-muted">
        Share is the percent of the {stats.counts.analyzed.toLocaleString()} analyzed reviews that mention the theme. Net runs from -100 (all
        negative) to +100 (all positive). The trend line is the share over the selected dates, split into up to 12 equal periods; periods with
        fewer than 5 analyzed reviews are skipped. {pct(stats.other.share)} of reviews raised points no theme covers. Click a theme to read its
        reviews.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="border-b border-line text-xs text-muted">
            <tr>
              <th className="py-2 pr-3">{header("name", "Theme", "Sort by name")}</th>
              <th className="w-40 py-2 pr-3">{header("share", "Share", "Most mentioned first")}</th>
              <th className="w-60 py-2 pr-3">{header("negative", "Sentiment", "Most negative mentions first")}</th>
              <th className="w-32 py-2 pr-3 uppercase tracking-wide">Trend</th>
              <th className="w-16 py-2 text-right">{header("net", "Net", "Lowest net sentiment first")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line-soft">
            {rows.map((t) => (
              <tr key={t.key} className="align-top hover:bg-subtle">
                <td className="py-2 pr-3">
                  <Link to={{ pathname: `/titles/${titleId}/themes/${t.key}`, search }} className="font-medium text-link hover:underline" title={t.definition}>
                    {t.name}
                  </Link>
                  <div className="text-xs text-muted">{t.mentions.toLocaleString()} reviews</div>
                </td>
                <td className="py-2 pr-3">
                  <div className="flex items-center gap-2">
                    <div className="h-2 flex-1 rounded bg-soft">
                      <div className="h-2 rounded bg-brand" style={{ width: `${Math.min(100, t.share * 100)}%` }} />
                    </div>
                    <span className="w-10 text-right tabular-nums">{pct(t.share)}</span>
                  </div>
                </td>
                <td className="py-2 pr-3">
                  <SentimentBar t={t} />
                </td>
                <td className="py-1 pr-3">
                  <Sparkline points={trendPoints(t, stats)} label={`${t.name} share over time`} />
                </td>
                <td className={`py-2 text-right font-medium tabular-nums ${t.net === null ? "text-faint" : t.net >= 0 ? "text-positive-ink" : "text-negative-ink"}`}>
                  {t.net === null ? "n/a" : `${t.net > 0 ? "+" : ""}${Math.round(t.net * 100)}`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
