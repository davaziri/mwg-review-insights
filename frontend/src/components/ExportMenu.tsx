import { useEffect, useRef, useState } from "react";

import { activeFilterCount, filterQuery, qs, type PageFilters } from "../lib/filters";
import { download, exportName } from "../lib/download";
import { Button } from "./ui";

/** Downloads for one title, using the filters currently on the page. */
export function ExportMenu({ titleId, subject, filters }: { titleId: number; subject: string; filters: PageFilters }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  const query = qs(filterQuery(filters));
  const items = [
    { key: "pdf", label: "PDF report", hint: "Summary, charts, themes and quotes. Takes a few seconds.", type: "Report", ext: "pdf" },
    { key: "xlsx", label: "Excel workbook", hint: "Theme summary, every coded review and monthly trends. Opens in Google Sheets too.", type: "Data", ext: "xlsx" },
    { key: "csv", label: "CSV of coded reviews", hint: "One row per review, with a column per theme.", type: "CodedReviews", ext: "csv" },
  ];
  const run = async (item: (typeof items)[number]) => {
    setBusy(item.key);
    setError(null);
    try {
      await download(`/api/titles/${titleId}/export.${item.ext}${query}`, exportName(subject, item.type, item.ext));
      setOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Download failed");
    } finally {
      setBusy(null);
    }
  };
  const active = activeFilterCount(filters);

  return (
    <div ref={ref} className="relative">
      <Button onClick={() => setOpen(!open)} aria-expanded={open}>
        {busy ? "Preparing..." : "Export"}
      </Button>
      {open && (
        <div className="absolute right-0 z-30 mt-1 w-72 rounded-md border border-line bg-surface p-1 shadow-lg">
          <p className="px-2 pt-1 pb-2 text-xs text-muted">
            {active ? `Uses the ${active === 1 ? "filter" : `${active} filters`} on this page.` : "Includes every review (no filters set)."}
          </p>
          {items.map((item) => (
            <button
              key={item.key}
              type="button"
              disabled={busy !== null}
              onClick={() => run(item)}
              className="block w-full rounded px-2 py-1.5 text-left hover:bg-subtle disabled:opacity-60"
            >
              <span className="block text-sm font-medium">{busy === item.key ? "Preparing..." : item.label}</span>
              <span className="block text-xs text-muted">{item.hint}</span>
            </button>
          ))}
          {error && <p className="px-2 py-1 text-xs text-negative-ink">{error}</p>}
        </div>
      )}
    </div>
  );
}
