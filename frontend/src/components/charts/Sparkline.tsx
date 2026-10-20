import { Line, LineChart, ResponsiveContainer, Tooltip, YAxis } from "recharts";

import { pct } from "../../lib/format";
import { TooltipBox, useChartTheme } from "./parts";

export interface SparkPoint {
  /** The period this point covers, such as "Mar 2025" or "Mar to Jul 2025". */
  period: string;
  share: number | null;
  mentions: number;
  analyzed: number;
}

/** A theme's share of reviews period by period. Periods with too few reviews are left out and
 * the line runs straight across them. */
export function Sparkline({ points, label }: { points: SparkPoint[]; label: string }) {
  const { p, surface } = useChartTheme();
  const last = [...points].reverse().find((x) => x.share !== null);
  if (!last) return <span className="text-xs text-faint">No data</span>;
  return (
    <div className="h-8 w-28" role="img" aria-label={`${label}: ${pct(last.share)} of reviews in ${last.period}`}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 5, right: 5, bottom: 5, left: 5 }}>
          <YAxis hide domain={[0, "dataMax"]} />
          <Tooltip
            cursor={{ stroke: p.lineStrong, strokeWidth: 1 }}
            allowEscapeViewBox={{ x: true, y: true }}
            wrapperStyle={{ zIndex: 40 }}
            content={({ active, payload }) => {
              const pt = active && payload?.length ? (payload[0].payload as SparkPoint) : null;
              if (!pt) return null;
              return (
                <TooltipBox
                  title={pt.period}
                  rows={[{ color: p.link, label: "of analyzed reviews", value: pt.share === null ? "n/a" : pct(pt.share) }]}
                  note={`${pt.mentions} of ${pt.analyzed} reviews`}
                />
              );
            }}
          />
          <Line
            type="monotone"
            dataKey="share"
            stroke={p.link}
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
            connectNulls
            isAnimationActive={false}
            dot={(props: { cx?: number; cy?: number; index?: number }) =>
              props.index === points.lastIndexOf(last) && props.cx !== undefined && props.cy !== undefined ? (
                <circle key="end" cx={props.cx} cy={props.cy} r={4} fill={p.link} stroke={surface} strokeWidth={2} />
              ) : (
                <g key={props.index} />
              )
            }
            activeDot={{ r: 4, fill: p.link, stroke: surface, strokeWidth: 2 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
