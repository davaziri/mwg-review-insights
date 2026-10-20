import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { ThemeCell } from "../../api/types";
import { ChartFrame } from "./ChartFrame";
import { compact, monthLabel, monthRange, TooltipBox, useChartTheme } from "./parts";

type Row = { month: string; positive: number; mixed: number; negative: number; mentions: number; analyzed: number };

/** One theme's mentions per month, split by sentiment. */
export function SentimentOverTime({ monthly, analyzedByMonth }: { monthly: (ThemeCell & { month: string })[]; analyzedByMonth: Record<string, number> }) {
  const { p, grid, axis, tick, surface } = useChartTheme();
  if (!monthly.length) return <p className="text-sm text-muted">No reviews in this range.</p>;
  const byMonth = new Map(monthly.map((m) => [m.month, m]));
  const rows: Row[] = monthRange(monthly[0].month, monthly[monthly.length - 1].month).map((month) => {
    const m = byMonth.get(month);
    return { month, positive: m?.positive ?? 0, mixed: m?.mixed ?? 0, negative: m?.negative ?? 0, mentions: m?.mentions ?? 0, analyzed: analyzedByMonth[month] ?? 0 };
  });
  const series = [
    { key: "positive" as const, color: p.positive, label: "Positive" },
    { key: "mixed" as const, color: p.mixed, label: "Mixed" },
    { key: "negative" as const, color: p.negative, label: "Negative" },
  ];

  return (
    <ChartFrame
      label="Mentions per month by sentiment"
      legend={series.map((s) => ({ color: s.color, label: s.label }))}
      table={{
        columns: ["Month", "Mentions", "Positive", "Mixed", "Negative", "Analyzed reviews"],
        rows: rows.map((r) => [monthLabel(r.month), r.mentions, r.positive, r.mixed, r.negative, r.analyzed]),
      }}
    >
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 4, right: 4, bottom: 0, left: -12 }} barCategoryGap="20%">
            <CartesianGrid vertical={false} stroke={grid} />
            <XAxis dataKey="month" tickFormatter={(m: string) => monthLabel(m, true)} tick={tick} tickLine={false} axisLine={{ stroke: axis }} minTickGap={16} />
            <YAxis tick={tick} tickLine={false} axisLine={false} tickFormatter={compact} allowDecimals={false} />
            <Tooltip
              cursor={{ fill: p.soft, opacity: 0.6 }}
              content={({ active, payload }) => {
                const r = active && payload?.length ? (payload[0].payload as Row) : null;
                if (!r) return null;
                return (
                  <TooltipBox
                    title={monthLabel(r.month)}
                    rows={series.map((s) => ({ color: s.color, label: s.label.toLowerCase(), value: String(r[s.key]) }))}
                    note={`${r.mentions} mentions in ${r.analyzed} analyzed reviews`}
                  />
                );
              }}
            />
            {series.map((s, i) => (
              <Bar
                key={s.key}
                dataKey={s.key}
                stackId="s"
                fill={s.color}
                maxBarSize={24}
                radius={i === series.length - 1 ? [4, 4, 0, 0] : 0}
                stroke={surface}
                strokeWidth={1}
                isAnimationActive={false}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartFrame>
  );
}
