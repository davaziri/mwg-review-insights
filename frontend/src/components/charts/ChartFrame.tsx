import { createContext, useContext, useRef, useState, type ReactNode } from "react";

import { chartPng, copyOrSave, type LegendItem } from "../../lib/chartPng";
import { exportName } from "../../lib/download";
import { usePalette } from "../../theme/mode";
import { Legend } from "./parts";

/** The name chart images are saved under (a title's name, or "Compare"). */
export const ChartOwner = createContext("Portfolio");

export interface TableView {
  columns: string[];
  rows: (string | number)[][];
}

/** A chart with its legend, a "Show numbers" switch to the same data as a table (so no value
 * depends on hovering or on telling colors apart), and "Copy as image". */
export function ChartFrame({
  label,
  legend,
  legendShape = "square",
  table,
  children,
}: {
  label: string;
  legend: LegendItem[];
  legendShape?: "square" | "line";
  table: TableView;
  children: ReactNode;
}) {
  const [asTable, setAsTable] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const plot = useRef<HTMLDivElement>(null);
  const palette = usePalette();
  const owner = useContext(ChartOwner);

  const copy = async () => {
    const svg = plot.current?.querySelector<SVGSVGElement>("svg.recharts-surface");
    if (!svg) return;
    setStatus("Copying...");
    try {
      const png = chartPng(svg, { title: `${owner === "Portfolio" ? "" : `${owner}: `}${label}`, legend, legendShape, palette });
      const result = await copyOrSave(png, exportName(owner, label.replace(/[^0-9A-Za-z]+/g, ""), "png"));
      setStatus(result === "copied" ? "Copied" : "Saved as a file");
    } catch {
      setStatus("Couldn't copy");
    }
    setTimeout(() => setStatus(null), 2500);
  };

  return (
    <figure className="m-0" aria-label={label}>
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <div className="mr-auto">
          <Legend items={legend} shape={legendShape} />
        </div>
        {!asTable && (
          <button type="button" onClick={copy} className="text-xs font-medium text-link hover:underline" aria-live="polite">
            {status ?? "Copy as image"}
          </button>
        )}
        <button type="button" onClick={() => setAsTable(!asTable)} className="text-xs font-medium text-link hover:underline" aria-pressed={asTable}>
          {asTable ? "Show chart" : "Show numbers"}
        </button>
      </div>
      {asTable ? (
        <div className="max-h-72 overflow-auto rounded border border-line">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-subtle text-muted">
              <tr>
                {table.columns.map((c, i) => (
                  <th key={c} className={`px-2 py-1.5 font-medium ${i ? "text-right" : ""}`}>
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-line-soft">
              {table.rows.map((row, r) => (
                <tr key={r}>
                  {row.map((cell, i) => (
                    <td key={i} className={`px-2 py-1 ${i ? "text-right tabular-nums" : ""}`}>
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div ref={plot}>{children}</div>
      )}
    </figure>
  );
}
