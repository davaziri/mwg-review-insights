import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "danger" | "ghost";

const variants: Record<Variant, string> = {
  primary: "bg-brand text-on-brand hover:bg-brand-hover",
  secondary: "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50",
  danger: "border border-red-200 bg-white text-red-700 hover:bg-red-50",
  ghost: "text-slate-600 hover:bg-slate-100",
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
    slate: "bg-slate-100 text-slate-700",
    green: "bg-green-50 text-green-800",
    amber: "bg-amber-50 text-amber-800",
    red: "bg-red-50 text-red-700",
    blue: "bg-blue-50 text-blue-800",
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
      className="fixed inset-0 z-20 flex items-start justify-center bg-slate-900/40 p-4 pt-[10vh]"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div role="dialog" aria-label={title} className={`w-full ${wide ? "max-w-2xl" : "max-w-md"} max-h-[85vh] overflow-y-auto rounded-lg bg-white p-5 shadow-xl`}>
        <h2 className="mb-4 text-base font-semibold">{title}</h2>
        {children}
      </div>
    </div>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="mb-3 block">
      <span className="mb-1 block text-sm font-medium text-slate-700">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
    </label>
  );
}

export const inputClass =
  "w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand";

export function Card({ title, actions, children }: { title?: ReactNode; actions?: ReactNode; children: ReactNode }) {
  return (
    <section className="mb-5 rounded-lg border border-slate-200 bg-white">
      {(title || actions) && (
        <div className="flex flex-wrap items-center gap-3 border-b border-slate-100 px-4 py-3">
          {title && <h2 className="mr-auto text-base font-semibold">{title}</h2>}
          {actions}
        </div>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export const SENTIMENT_STYLE = {
  positive: { chip: "bg-green-50 text-green-800 border-green-200", mark: "bg-green-100 decoration-green-600", bar: "bg-positive" },
  mixed: { chip: "bg-amber-50 text-amber-800 border-amber-200", mark: "bg-amber-100 decoration-amber-600", bar: "bg-mixed" },
  negative: { chip: "bg-red-50 text-red-800 border-red-200", mark: "bg-red-100 decoration-red-600", bar: "bg-negative" },
} as const;

/** The overall impression: a solid chip and an outlined quote, so it reads apart from the themes. */
export const OVERALL_STYLE = {
  positive: { chip: "bg-green-700 text-white border-green-700", outline: "ring-green-600" },
  mixed: { chip: "bg-amber-600 text-white border-amber-600", outline: "ring-amber-500" },
  negative: { chip: "bg-red-700 text-white border-red-700", outline: "ring-red-600" },
  none: { chip: "bg-slate-100 text-slate-600 border-slate-300", outline: "ring-slate-400" },
} as const;

export const OVERALL_WORD = { positive: "positive", mixed: "mixed", negative: "negative", none: "no overall view" } as const;
