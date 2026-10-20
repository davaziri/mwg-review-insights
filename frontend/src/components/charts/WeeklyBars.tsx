import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip } from "recharts";

import type { AppCard } from "../../api/types";
import { pct } from "../../lib/format";
import { TooltipBox, useChartTheme } from "./parts";

const shortDate = (iso: string) => new Date(`${iso}T00:00:00Z`).toLocaleDateString(undefined, { month: "short", day: "numeric", timeZone: "UTC" });

/** Reviews per week for the last 12 weeks; the current week in the accent color. */
export function WeeklyBars({ weekly }: { weekly: AppCard["weekly"] }) {
  const { p } = useChartTheme();
  const total = weekly.reduce((n, w) => n + w.reviews, 0);
  return (
    <div className="h-10 w-full" role="img" aria-label={`${total} reviews in the last 12 weeks`}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={weekly} margin={{ top: 2, right: 0, bottom: 0, left: 0 }} barCategoryGap={2}>
          <Tooltip
            cursor={{ fill: p.soft, opacity: 0.6 }}
            allowEscapeViewBox={{ x: true, y: true }}
            wrapperStyle={{ zIndex: 40 }}
            content={({ active, payload }) => {
              const w = active && payload?.length ? (payload[0].payload as AppCard["weekly"][number]) : null;
              if (!w) return null;
              return (
                <TooltipBox
                  title={`Week of ${shortDate(w.week_start)}`}
                  rows={[{ color: p.link, label: w.reviews === 1 ? "review" : "reviews", value: String(w.reviews) }]}
                  note={w.reviews ? `${pct(w.positive / w.reviews)} recommended` : undefined}
                />
              );
            }}
          />
          <Bar dataKey="reviews" radius={[2, 2, 0, 0]} maxBarSize={24} minPointSize={1} isAnimationActive={false}>
            {weekly.map((w, i) => (
              <Cell key={w.week_start} fill={i === weekly.length - 1 ? p.link : p.lineStrong} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
