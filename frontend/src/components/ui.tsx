import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "danger" | "ghost";

const variants: Record<Variant, string> = {
  primary: "bg-brand text-on-brand hover:bg-brand-hover",
  secondary: "border border-line-strong bg-surface text-ink-2 hover:bg-subtle",
  danger: "border border-negative-line bg-surface text-negative-ink hover:bg-negative-soft",
  ghost: "text-ink-2 hover:bg-soft",
};

export function Button({
  variant = "secondary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      type="button"
      className={`inline-flex items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${variants[variant]} ${className}`}
      {...props}
    />
  );
}

export function Badge({ children, tone = "slate" }: { children: ReactNode; tone?: "slate" | "green" | "amber" | "red" | "blue" }) {
  const tones = {
    slate: "bg-soft text-ink-2",
    green: "bg-positive-soft text-positive-ink",
    amber: "bg-mixed-soft text-mixed-ink",
    red: "bg-negative-soft text-negative-ink",
    blue: "bg-info-soft text-info-ink",
  };
  return <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ${tones[tone]}`}>{children}</span>;
}

export function Dialog({
  title,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  return (
    <div
      className="fixed inset-0 z-20 flex items-start justify-center bg-black/50 p-4 pt-[10vh]"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div role="dialog" aria-label={title} className={`w-full ${wide ? "max-w-2xl" : "max-w-md"} max-h-[85vh] overflow-y-auto rounded-lg bg-surface p-5 shadow-xl`}>
        <h2 className="mb-4 text-base font-semibold">{title}</h2>
        {children}
      </div>
    </div>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="mb-3 block">
      <span className="mb-1 block text-sm font-medium text-ink-2">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  );
}

export const inputClass =
  "w-full rounded-md border border-line-strong bg-surface px-2.5 py-1.5 text-sm text-ink focus:border-link focus:outline-none focus:ring-1 focus:ring-link";

/** A compact select for filter rows. */
export const selectClass =
  "rounded-md border border-line-strong bg-surface px-2 py-1.5 text-sm text-ink focus:border-link focus:outline-none focus:ring-1 focus:ring-link";

export function Card({ title, actions, children }: { title?: ReactNode; actions?: ReactNode; children: ReactNode }) {
  return (
    <section className="mb-5 rounded-lg border border-line bg-surface">
      {(title || actions) && (
        <div className="flex flex-wrap items-center gap-3 border-b border-line-soft px-4 py-3">
          {title && <h2 className="mr-auto text-base font-semibold">{title}</h2>}
          {actions}
        </div>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export const SENTIMENT_STYLE = {
  positive: { chip: "bg-positive-soft text-positive-ink border-positive-line", mark: "bg-positive-mark decoration-positive", bar: "bg-positive" },
  mixed: { chip: "bg-mixed-soft text-mixed-ink border-mixed-line", mark: "bg-mixed-mark decoration-mixed", bar: "bg-mixed" },
  negative: { chip: "bg-negative-soft text-negative-ink border-negative-line", mark: "bg-negative-mark decoration-negative", bar: "bg-negative" },
} as const;

/** The overall impression: a solid chip and an outlined quote, so it reads apart from the themes. */
export const OVERALL_STYLE = {
  positive: { chip: "bg-positive-solid text-on-solid border-positive-solid", outline: "ring-positive-solid" },
  mixed: { chip: "bg-mixed-solid text-on-solid border-mixed-solid", outline: "ring-mixed-solid" },
  negative: { chip: "bg-negative-solid text-on-solid border-negative-solid", outline: "ring-negative-solid" },
  none: { chip: "bg-soft text-ink-2 border-line-strong", outline: "ring-faint" },
} as const;

export const OVERALL_WORD = { positive: "positive", mixed: "mixed", negative: "negative", none: "no overall view" } as const;

/** A headline number with a label and an optional line of context underneath. */
export function StatTile({ label, value, detail }: { label: string; value: ReactNode; detail?: ReactNode }) {
  return (
    <div className="rounded-lg border border-line bg-surface px-4 py-3">
      <div className="text-xs font-medium text-muted">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-ink">{value}</div>
      {detail && <div className="mt-0.5 text-xs text-muted">{detail}</div>}
    </div>
  );
}
