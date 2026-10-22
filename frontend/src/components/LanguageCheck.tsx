import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { api } from "../api/client";
import type { AnalysisRun } from "../api/types";
import { AdminOnly } from "../auth";
import { EstimateDialog } from "./analysis/EstimateDialog";
import { Button } from "./ui";

/** On the Reviews page: how many reviews still show only their Steam language setting, and for
 * admins, a button to check their languages and translate them (cost shown first). */
export function LanguageCheck({ titleId, appId }: { titleId: number; appId: number }) {
  const queryClient = useQueryClient();
  const [estimate, setEstimate] = useState<AnalysisRun | null>(null);
  const status = useQuery({
    queryKey: ["languages", titleId, appId],
    queryFn: () => api.languageStatus(titleId, appId),
    refetchInterval: (q) => (q.state.data?.active_run ? 5000 : false),
  });

  // When a run finishes, reload the reviews and the language filter to show what changed.
  const running = !!status.data?.active_run;
  const wasRunning = useRef(running);
  useEffect(() => {
    if (wasRunning.current && !running) {
      queryClient.invalidateQueries({ queryKey: ["reviews", titleId] });
      queryClient.invalidateQueries({ queryKey: ["facets", titleId] });
    }
    wasRunning.current = running;
  }, [running, titleId, queryClient]);

  const estimateMut = useMutation({ mutationFn: () => api.estimate(titleId, "translation", appId), onSuccess: setEstimate });
  const confirmMut = useMutation({
    mutationFn: (id: number) => api.confirmRun(id),
    onSuccess: () => {
      setEstimate(null);
      status.refetch();
    },
  });

  const s = status.data;
  const run = s?.active_run;
  if (!s || (!s.unchecked && run?.kind !== "translation")) return null;
  const n = s.unchecked;

  return (
    <div className="mb-4 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-md border border-info-line bg-info-soft px-3 py-2 text-sm text-info-ink">
      {run ? (
        <span>
          {run.kind === "translation" ? "Checking languages and translating" : "An analysis is running, and it checks languages first"}
          {n ? ` (${n.toLocaleString()} left)` : ""}. This page updates when it's done.
        </span>
      ) : (
        <>
          <span className="min-w-60 flex-1">
            {n.toLocaleString()} {n === 1 ? "review hasn't" : "reviews haven't"} had {n === 1 ? "its" : "their"} language checked. Until then{" "}
            {n === 1 ? "it shows" : "they show"} the reviewer's Steam language setting, which isn't always the language the review is written
            in, and no English translation.
          </span>
          <AdminOnly otherwise={<span className="text-xs">An admin can check them from this page.</span>}>
            <Button variant="primary" disabled={estimateMut.isPending} onClick={() => estimateMut.mutate()}>
              {estimateMut.isPending ? "Working out the cost..." : "Check languages and translate"}
            </Button>
          </AdminOnly>
        </>
      )}
      {estimateMut.error && <p className="w-full text-negative-ink">{estimateMut.error.message}</p>}
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
    </div>
  );
}
