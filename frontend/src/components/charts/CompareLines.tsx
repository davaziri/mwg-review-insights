import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { ChartFrame } from "./ChartFrame";
import { Legend, TooltipBox, useChartTheme } from "./parts";

export interface SeriesDef {
  key: string;
  label: string;
  color: string;
}

/** One line per title on a shared time axis. Missing values are gaps, not zeros. */
export function CompareLines({
  label,
  rows,
  series,
  xLabel,
  format,
  domain,
  note,
  dots = false,
}: {
  label: string;
  rows: ({ x: string } & Record<string, number | null | string>)[];
  series: SeriesDef[];
  xLabel: (x: string, short?: boolean) => string;
  format: (v: number) => string;
  domain?: [number, number];
  note?: (row: Record<string, unknown>) => string | undefined;
  /** Mark every point, for sparse series where a lone point would otherwise be invisible. */
  dots?: boolean;
}) {
  const { p, grid, axis, tick, surface } = useChartTheme();
  return (
    <ChartFrame
      label={label}
      legend={<Legend shape="line" items={series.map((s) => ({ color: s.color, label: s.label }))} />}
      table={{
        columns: ["Period", ...series.map((s) => s.label)],
        rows: rows.map((r) => [xLabel(r.x), ...series.map((s) => (typeof r[s.key] === "number" ? format(r[s.key] as number) : ""))]),
      }}
    >
      <div className="h-60">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
            <CartesianGrid vertical={false} stroke={grid} />
            <XAxis dataKey="x" tickFormatter={(x: string) => xLabel(x, true)} tick={tick} tickLine={false} axisLine={{ stroke: axis }} minTickGap={16} />
            <YAxis tick={tick} tickLine={false} axisLine={false} tickFormatter={format} domain={domain ?? [0, "auto"]} allowDecimals={false} />
            <Tooltip
              cursor={{ stroke: p.lineStrong, strokeWidth: 1 }}
              content={({ active, payload, label: x }) => {
                if (!active || !payload?.length) return null;
                const row = payload[0].payload as Record<string, unknown>;
                return (
                  <TooltipBox
                    title={xLabel(String(x))}
                    rows={series.map((s) => ({
                      color: s.color,
                      label: s.label,
                      value: typeof row[s.key] === "number" ? format(row[s.key] as number) : "no data",
                    }))}
                    note={note?.(row)}
                  />
                );
              }}
            />
            {series.map((s) => (
              <Line
                key={s.key}
                type="linear"
                dataKey={s.key}
                name={s.label}
                stroke={s.color}
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
                dot={dots ? { r: 3.5, fill: s.color, stroke: surface, strokeWidth: 2 } : false}
                activeDot={{ r: 4, fill: s.color, stroke: surface, strokeWidth: 2 }}
                connectNulls={false}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </ChartFrame>
  );
}
