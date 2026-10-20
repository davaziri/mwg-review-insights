import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../../api/client";
import type { AnalysisOverview, AnalysisRun } from "../../api/types";
import { dateTime, money, timeAgo } from "../../lib/format";
import { Badge, Button, Card } from "../ui";
import { EstimateDialog, STEP_LABELS } from "./EstimateDialog";

const KIND = { discovery: "Find themes", analysis: "Analyze reviews" } as const;
const STATUS_TONE = {
  estimated: "slate",
  queued: "blue",
  running: "blue",
  succeeded: "green",
  failed: "red",
  canceled: "slate",
} as const;

export function RunPanel({ overview }: { overview: AnalysisOverview }) {
  const queryClient = useQueryClient();
  const [estimate, setEstimate] = useState<AnalysisRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const titleId = overview.title.id;
  const appId = overview.app_id;
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["analysis", titleId] });

  const estimateMut = useMutation({
    mutationFn: (kind: "discovery" | "analysis") => api.estimate(titleId, kind, appId),
    onSuccess: (run) => {
      setError(null);
      setEstimate(run);
    },
    onError: (e: Error) => setError(e.message),
  });
  const confirmMut = useMutation({
    mutationFn: (id: number) => api.confirmRun(id),
    onSuccess: () => {
      setEstimate(null);
      refresh();
    },
  });
  const cancelMut = useMutation({ mutationFn: (id: number) => api.cancelRun(id), onSuccess: refresh });

  const active = overview.active_run;
  const hasCodebook = !!overview.latest_codebook;
  const approved = !!overview.approved_codebook;
  const enoughReviews = overview.reviews.with_content >= overview.min_reviews_for_discovery;

  return (
    <Card
      title="Analysis"
      actions={
        <>
          <Button
            disabled={!!active || !enoughReviews || estimateMut.isPending}
            onClick={() => estimateMut.mutate("discovery")}
            title={enoughReviews ? undefined : `Needs at least ${overview.min_reviews_for_discovery} reviews with text`}
          >
            {hasCodebook ? "Find themes again" : "Find themes"}
          </Button>
          <Button
            variant="primary"
            disabled={!!active || !approved || estimateMut.isPending}
            onClick={() => estimateMut.mutate("analysis")}
            title={approved ? undefined : "Approve a codebook first"}
          >
            Analyze reviews
          </Button>
        </>
      }
    >
      <div className="flex flex-wrap gap-x-8 gap-y-2 text-sm">
        <Stat label="Reviews" value={overview.reviews.total} />
        <Stat label="With text" value={overview.reviews.with_content} />
        <Stat label="No text (not analyzed)" value={overview.reviews.no_content} />
        {overview.reviews.pending !== null && <Stat label="Waiting for analysis" value={overview.reviews.pending} />}
      </div>
      {!enoughReviews && (
        <p className="mt-3 text-sm text-muted">
          Not enough reviews for themes yet: finding themes needs at least {overview.min_reviews_for_discovery} reviews with text.
        </p>
      )}
      {error && <p className="mt-3 text-sm text-negative-ink">{error}</p>}

      {active && <ActiveRun run={active} onCancel={() => cancelMut.mutate(active.id)} canceling={cancelMut.isPending} />}

      {overview.runs.filter((r) => r.status !== "estimated" && r.id !== active?.id).length > 0 && (
        <div className="mt-4">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Recent runs</h3>
          <ul className="divide-y divide-line-soft text-sm">
            {overview.runs
              .filter((r) => r.status !== "estimated" && r.id !== active?.id)
              .slice(0, 5)
              .map((r) => (
                <li key={r.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
                  <span className="font-medium">{KIND[r.kind]}</span>
                  <Badge tone={STATUS_TONE[r.status]}>{r.status[0].toUpperCase() + r.status.slice(1)}</Badge>
                  <span className="text-muted">{dateTime(r.finished_at ?? r.created_at)}</span>
                  <span className="text-muted">
                    estimated {money(r.est_cost_usd)}, actual {money(r.actual_cost_usd)}
                  </span>
                  {r.kind === "analysis" && r.status === "succeeded" && (
                    <span className="text-muted">{r.reviews_tagged.toLocaleString()} reviews tagged</span>
                  )}
                  {(r.error || r.warning) && (
                    <span className={`w-full text-xs ${r.error ? "text-negative-ink" : "text-muted"}`}>{r.error ?? r.warning}</span>
                  )}
                </li>
              ))}
          </ul>
        </div>
      )}

      {estimate && (
        <EstimateDialog
          run={estimate}
          busy={confirmMut.isPending}
          error={confirmMut.error?.message ?? null}
          onConfirm={() => confirmMut.mutate(estimate.id)}
          onClose={() => {
            api.cancelRun(estimate.id).catch(() => undefined);
            setEstimate(null);
          }}
        />
      )}
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="text-lg font-semibold tabular-nums">{value.toLocaleString()}</div>
      <div className="text-xs text-muted">{label}</div>
    </div>
  );
}

function ActiveRun({ run, onCancel, canceling }: { run: AnalysisRun; onCancel: () => void; canceling: boolean }) {
  const batch = run.step ? run.batches?.[run.step] : undefined;
  const waitingOnBatch = batch && !batch.ingested;
  return (
    <div className="mt-4 rounded-md border border-info-line bg-info-soft p-3 text-sm text-info-ink">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold">{KIND[run.kind]}</span>
        <span>
          {run.status === "queued" ? "is queued and starts within a few seconds." : `is running: ${STEP_LABELS[run.step ?? ""] ?? run.step}.`}
        </span>
        <Button variant="ghost" className="ml-auto" onClick={onCancel} disabled={canceling}>
          Cancel
        </Button>
      </div>
      {waitingOnBatch && (
        <p className="mt-1 text-xs">
          Sent as a batch {timeAgo(batch.submitted_at)} ({batch.requests} requests). Batches usually finish within an hour; this page updates on its own.
        </p>
      )}
      {run.kind === "analysis" && (
        <p className="mt-1 text-xs">
          {run.reviews_tagged.toLocaleString()} of {run.reviews_in_scope.toLocaleString()} reviews tagged. Spent so far{" "}
          {money(run.actual_cost_usd)} of an estimated {money(run.est_cost_usd)}.
        </p>
      )}
    </div>
  );
}
