import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { MonthStat } from "../../api/types";
import { pct } from "../../lib/format";
import { ChartFrame } from "./ChartFrame";
import { compact, Legend, monthLabel, monthRange, TooltipBox, useChartTheme } from "./parts";

interface Row {
  month: string;
  positive: number;
  negative: number;
  total: number;
}

/** Reviews per month: recommended above the line, not recommended below it. */
export function VolumeChart({ months }: { months: MonthStat[] }) {
  const { p, grid, axis, tick, surface } = useChartTheme();
  if (!months.length) return <p className="text-sm text-muted">No reviews in this range.</p>;
  const byMonth = new Map(months.map((m) => [m.month, m]));
  const rows: Row[] = monthRange(months[0].month, months[months.length - 1].month).map((month) => {
    const m = byMonth.get(month);
    const pos = m?.positive_votes ?? 0;
    const total = m?.reviews ?? 0;
    return { month, positive: pos, negative: -(total - pos), total };
  });
  const short = rows.length > 18;

  return (
    <ChartFrame
      label="Reviews per month"
      legend={
        <Legend
          items={[
            { color: p.positive, label: "Recommended (above the line)" },
            { color: p.negative, label: "Not recommended (below)" },
          ]}
        />
      }
      table={{
        columns: ["Month", "Reviews", "Recommended", "Not recommended", "% positive"],
        rows: rows.map((r) => [monthLabel(r.month), r.total, r.positive, -r.negative, r.total ? pct(r.positive / r.total) : ""]),
      }}
    >
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 4, right: 4, bottom: 0, left: -12 }} stackOffset="sign" barCategoryGap="20%">
            <CartesianGrid vertical={false} stroke={grid} />
            <XAxis
              dataKey="month"
              tickFormatter={(m: string) => monthLabel(m, true)}
              tick={tick}
              tickLine={false}
              axisLine={{ stroke: axis }}
              minTickGap={short ? 24 : 8}
            />
            <YAxis tick={tick} tickLine={false} axisLine={false} tickFormatter={(v: number) => compact(Math.abs(v))} allowDecimals={false} />
            <ReferenceLine y={0} stroke={p.lineStrong} />
            <Tooltip
              cursor={{ fill: p.soft, opacity: 0.6 }}
              content={({ active, payload }) => {
                const r = active && payload?.length ? (payload[0].payload as Row) : null;
                if (!r) return null;
                return (
                  <TooltipBox
                    title={monthLabel(r.month)}
                    rows={[
                      { color: p.positive, label: "recommended", value: String(r.positive) },
                      { color: p.negative, label: "not recommended", value: String(-r.negative) },
                    ]}
                    note={r.total ? `${pct(r.positive / r.total)} positive of ${r.total}` : "No reviews"}
                  />
                );
              }}
            />
            <Bar dataKey="positive" stackId="v" fill={p.positive} maxBarSize={24} radius={[4, 4, 0, 0]} stroke={surface} strokeWidth={1} isAnimationActive={false} />
            <Bar dataKey="negative" stackId="v" fill={p.negative} maxBarSize={24} radius={[4, 4, 0, 0]} stroke={surface} strokeWidth={1} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartFrame>
  );
}
