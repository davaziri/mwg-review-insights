import type { AnalysisRun, EstimateStep } from "../../api/types";
import { money, tokens } from "../../lib/format";
import { Button, Dialog } from "../ui";

export const STEP_LABELS: Record<string, string> = {
  translation: "Check languages and translate",
  discovery: "Find themes",
  tagging: "Tag reviews",
  qa: "Quality check",
  summary: "Executive summary",
};

export const RUN_KIND: Record<AnalysisRun["kind"], string> = {
  discovery: "Find themes",
  analysis: "Analyze reviews",
  translation: "Check languages and translate",
};

export function EstimateDialog({
  run,
  busy,
  error,
  onConfirm,
  onClose,
}: {
  run: AnalysisRun;
  busy: boolean;
  error: string | null;
  onConfirm: () => void;
  onClose: () => void;
}) {
  const steps = run.estimate?.steps ?? [];
  const title = `${RUN_KIND[run.kind]}: cost estimate`;
  return (
    <Dialog title={title} onClose={onClose} wide>
      <p className="mb-3 text-sm text-ink-2">
        Nothing has been sent to the model yet. Check the estimate, then confirm to run it.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-line text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="py-1.5 pr-3">Step</th>
              <th className="py-1.5 pr-3">Model</th>
              <th className="py-1.5 pr-3 text-right">Requests</th>
              <th className="py-1.5 pr-3 text-right">Tokens in</th>
              <th className="py-1.5 pr-3 text-right">Tokens out</th>
              <th className="py-1.5 text-right">Cost</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line-soft">
            {steps.map((s) => (
              <StepRow key={s.step} step={s} />
            ))}
            <tr className="font-semibold">
              <td className="py-2 pr-3" colSpan={3}>
                Total
              </td>
              <td className="py-2 pr-3 text-right tabular-nums">{tokens(run.est_input_tokens)}</td>
              <td className="py-2 pr-3 text-right tabular-nums">{tokens(run.est_output_tokens)}</td>
              <td className="py-2 text-right tabular-nums">{money(run.est_cost_usd)}</td>
            </tr>
          </tbody>
        </table>
      </div>
      {!!run.estimate?.notes.length && (
        <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-muted">
          {run.estimate.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
      {error && <p className="mt-3 text-sm text-negative-ink">{error}</p>}
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose} disabled={busy}>
          Don't run
        </Button>
        <Button variant="primary" onClick={onConfirm} disabled={busy}>
          {busy ? "Starting..." : `Run for about ${money(run.est_cost_usd)}`}
        </Button>
      </div>
    </Dialog>
  );
}

function StepRow({ step }: { step: EstimateStep }) {
  return (
    <tr>
      <td className="py-2 pr-3">
        {STEP_LABELS[step.step] ?? step.step}
        <div className="text-xs text-muted">
          {step.reviews !== undefined && `${step.reviews.toLocaleString()} reviews`}
          {step.batch && (step.reviews !== undefined ? ", " : "") + "batch (half price)"}
        </div>
      </td>
      <td className="py-2 pr-3 text-xs text-ink-2">{step.model}</td>
      <td className="py-2 pr-3 text-right tabular-nums">{step.requests}</td>
      <td className="py-2 pr-3 text-right tabular-nums">{tokens(step.input_tokens)}</td>
      <td className="py-2 pr-3 text-right tabular-nums">{tokens(step.output_tokens)}</td>
      <td className="py-2 text-right tabular-nums">{money(step.cost_usd)}</td>
    </tr>
  );
}
