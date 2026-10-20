import { useState } from "react";

import type { ThemeStat, ThemeStats } from "../../api/types";
import { pct } from "../../lib/format";
import { Card } from "../ui";

type SortKey = "share" | "net" | "negative";

function SentimentBar({ t }: { t: ThemeStat }) {
  if (!t.mentions) return <span className="text-xs text-slate-400">No mentions</span>;
  const w = (n: number) => `${(100 * n) / t.mentions}%`;
  return (
    <div>
      <div className="flex h-2.5 w-full overflow-hidden rounded bg-slate-100" aria-label={`${t.positive} positive, ${t.mixed} mixed, ${t.negative} negative`}>
        <div className="bg-positive" style={{ width: w(t.positive) }} />
        <div className="bg-mixed" style={{ width: w(t.mixed) }} />
        <div className="bg-negative" style={{ width: w(t.negative) }} />
      </div>
      <div className="mt-0.5 text-xs text-slate-500 tabular-nums">
        {t.positive} positive, {t.mixed} mixed, {t.negative} negative
      </div>
    </div>
  );
}

export function ThemesTable({ stats }: { stats: ThemeStats }) {
  const [sort, setSort] = useState<SortKey>("share");
  const rows = [...stats.themes].sort((a, b) => {
    if (sort === "net") return (a.net ?? 0) - (b.net ?? 0);
    if (sort === "negative") return b.negative - a.negative;
    return b.share - a.share;
  });
  const header = (key: SortKey, label: string) => (
    <button type="button" className={`uppercase tracking-wide ${sort === key ? "text-slate-900" : ""}`} onClick={() => setSort(key)}>
      {label}
      {sort === key ? " ↓" : ""}
    </button>
  );

  return (
    <Card title="Themes">
      <p className="mb-3 text-xs text-slate-500">
        Share is the percent of the {stats.counts.analyzed.toLocaleString()} analyzed reviews that mention the theme. Net runs from -100 (all
        negative) to +100 (all positive). {pct(stats.other.share)} of reviews raised points no theme covers.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead className="border-b border-slate-200 text-xs text-slate-500">
            <tr>
              <th className="py-2 pr-3 uppercase tracking-wide">Theme</th>
              <th className="w-40 py-2 pr-3">{header("share", "Share")}</th>
              <th className="w-64 py-2 pr-3">{header("negative", "Sentiment")}</th>
              <th className="w-20 py-2 text-right">{header("net", "Net")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((t) => (
              <tr key={t.key} className="align-top">
                <td className="py-2 pr-3">
                  <div className="font-medium" title={t.definition}>
                    {t.name}
                  </div>
                  <div className="text-xs text-slate-500">{t.mentions.toLocaleString()} reviews</div>
                </td>
                <td className="py-2 pr-3">
                  <div className="flex items-center gap-2">
                    <div className="h-2.5 flex-1 rounded bg-slate-100">
                      <div className="h-2.5 rounded bg-brand" style={{ width: `${Math.min(100, t.share * 100)}%` }} />
                    </div>
                    <span className="w-10 text-right tabular-nums">{pct(t.share)}</span>
                  </div>
                </td>
                <td className="py-2 pr-3">
                  <SentimentBar t={t} />
                </td>
                <td className={`py-2 text-right font-medium tabular-nums ${t.net === null ? "text-slate-400" : t.net >= 0 ? "text-positive" : "text-negative"}`}>
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
