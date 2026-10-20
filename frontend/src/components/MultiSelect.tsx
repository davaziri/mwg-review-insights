import { useEffect, useId, useRef, useState } from "react";

export interface Option {
  value: string;
  label: string;
  count?: number;
}

/** A dropdown of checkboxes for filters that take several values. */
export function MultiSelect({
  label,
  options,
  selected,
  onChange,
}: {
  label: string;
  options: Option[];
  selected: string[];
  onChange: (values: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const id = useId();

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

  const toggle = (value: string) =>
    onChange(selected.includes(value) ? selected.filter((v) => v !== value) : [...selected, value]);
  const summary =
    selected.length === 0
      ? `All`
      : selected.length === 1
        ? (options.find((o) => o.value === selected[0])?.label ?? selected[0])
        : `${selected.length} selected`;

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen(!open)}
        className={`flex items-center gap-1.5 rounded-md border px-2 py-1.5 text-sm ${
          selected.length ? "border-link bg-surface text-ink" : "border-line-strong bg-surface text-ink"
        }`}
      >
        <span className="text-muted">{label}:</span>
        <span className="max-w-40 truncate">{summary}</span>
        <svg viewBox="0 0 20 20" className="h-3.5 w-3.5 text-muted" fill="currentColor" aria-hidden>
          <path d="M5.5 7.5 10 12l4.5-4.5" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" />
        </svg>
      </button>
      {open && (
        <div id={id} className="absolute left-0 z-30 mt-1 max-h-72 w-64 overflow-y-auto rounded-md border border-line bg-surface p-1 shadow-lg">
          {options.map((o) => (
            <label key={o.value} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-subtle">
              <input type="checkbox" checked={selected.includes(o.value)} onChange={() => toggle(o.value)} className="accent-brand" />
              <span className="flex-1">{o.label}</span>
              {o.count !== undefined && <span className="text-xs text-muted tabular-nums">{o.count.toLocaleString()}</span>}
            </label>
          ))}
          {selected.length > 0 && (
            <button type="button" onClick={() => onChange([])} className="mt-1 w-full rounded px-2 py-1.5 text-left text-xs text-link hover:bg-subtle">
              Clear
            </button>
          )}
        </div>
      )}
    </div>
  );
}
