import type { ReactNode } from "react";

import { usePalette } from "../../theme/mode";

/** Colors and shared props every chart uses, from the current light or dark palette. */
export function useChartTheme() {
  const p = usePalette();
  return {
    p,
    grid: p.lineSoft,
    axis: p.line,
    tick: { fill: p.muted, fontSize: 11 },
    surface: p.surface,
  };
}

export const compact = (n: number) =>
  Math.abs(n) >= 1000 ? `${(n / 1000).toFixed(Math.abs(n) >= 10_000 ? 0 : 1).replace(/\.0$/, "")}K` : String(Math.round(n));

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-03" as "Mar 2026" (or "Mar '26" when short). */
export function monthLabel(month: string, short = false): string {
  const [y, m] = month.split("-").map(Number);
  return short ? `${MONTHS[m - 1]} '${String(y).slice(2)}` : `${MONTHS[m - 1]} ${y}`;
}

/** Every month from first to last, so gaps show as gaps instead of being skipped. */
export function monthRange(first: string, last: string): string[] {
  const out: string[] = [];
  let [y, m] = first.split("-").map(Number);
  const [ly, lm] = last.split("-").map(Number);
  while (y < ly || (y === ly && m <= lm)) {
    out.push(`${y}-${String(m).padStart(2, "0")}`);
    m += 1;
    if (m > 12) {
      m = 1;
      y += 1;
    }
  }
  return out;
}

export interface TooltipRow {
  color: string;
  label: string;
  value: string;
}

/** Tooltip body: the value leads, the series name follows, keyed by a short line in its color. */
export function TooltipBox({ title, rows, note }: { title: string; rows: TooltipRow[]; note?: string }) {
  return (
    <div className="rounded-md border border-line bg-surface px-3 py-2 text-xs shadow-lg">
      <div className="mb-1 font-medium text-ink">{title}</div>
      {rows.map((r) => (
        <div key={r.label} className="flex items-center gap-2 py-0.5">
          <span className="inline-block h-0.5 w-3 rounded" style={{ background: r.color }} aria-hidden />
          <span className="font-semibold text-ink tabular-nums">{r.value}</span>
          <span className="text-muted">{r.label}</span>
        </div>
      ))}
      {note && <div className="mt-1 text-muted">{note}</div>}
    </div>
  );
}

/** A legend in HTML, mirroring the marks: squares for bars, short lines for lines. */
export function Legend({ items, shape = "square" }: { items: { color: string; label: ReactNode }[]; shape?: "square" | "line" }) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
      {items.map((item, i) => (
        <li key={i} className="flex items-center gap-1.5">
          <span
            className={shape === "square" ? "inline-block h-2.5 w-2.5 rounded-sm" : "inline-block h-0.5 w-3.5 rounded"}
            style={{ background: item.color }}
            aria-hidden
          />
          {item.label}
        </li>
      ))}
    </ul>
  );
}
