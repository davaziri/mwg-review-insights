import { useState, type ReactNode } from "react";

export interface TableView {
  columns: string[];
  rows: (string | number)[][];
}

/** A chart with its legend and a "Show numbers" switch to the same data as a table, so no value
 * depends on hovering or on telling colors apart. */
export function ChartFrame({ label, legend, table, children }: { label: string; legend?: ReactNode; table: TableView; children: ReactNode }) {
  const [asTable, setAsTable] = useState(false);
  return (
    <figure className="m-0" aria-label={label}>
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <div className="mr-auto">{legend}</div>
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
        children
      )}
    </figure>
  );
}
