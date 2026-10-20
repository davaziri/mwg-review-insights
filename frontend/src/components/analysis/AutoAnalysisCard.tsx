import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import { useAuth } from "../../auth";
import { Card } from "../ui";

const usd = (x: number) => `$${x.toFixed(2)}`;

/** The nightly analysis switch for a title, with what it is expected to cost. */
export function AutoAnalysisCard({ titleId, hasApprovedCodebook }: { titleId: number; hasApprovedCodebook: boolean }) {
  const { isAdmin } = useAuth();
  const queryClient = useQueryClient();
  const info = useQuery({ queryKey: ["auto-analysis", titleId], queryFn: () => api.autoAnalysis(titleId) });
  const toggle = useMutation({
    mutationFn: (on: boolean) => api.updateTitle(titleId, { auto_analyze: on }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["auto-analysis", titleId] });
      queryClient.invalidateQueries({ queryKey: ["title", titleId] });
    },
  });
  const d = info.data;
  if (!d) return null;

  return (
    <Card title="Nightly analysis">
      <div className="flex flex-wrap items-start gap-4">
        <div className="max-w-2xl flex-1 text-sm text-ink-2">
          <p>
            When this is on, the worker analyzes new and edited reviews every night after the sync. It starts on its own when the estimate is at
            or under {usd(d.nightly_limit_usd)}; anything above that waits for an admin and sends an alert. The quality check runs when there are
            at least 20 new reviews, and the executive summary is rewritten at most once a week.
          </p>
          <p className="mt-2">
            Expected cost: about <b className="text-ink">{usd(d.expected_monthly_usd)} a month</b>, based on {d.reviews_last_30_days} reviews in
            the last 30 days{d.reviews_last_30_days ? `, mostly the weekly summary (about ${usd(d.summary_usd)} each)` : ""}.
          </p>
        </div>
        {isAdmin ? (
          <label className={`flex items-center gap-2 text-sm font-medium ${hasApprovedCodebook ? "" : "opacity-60"}`}>
            <input
              type="checkbox"
              className="h-4 w-4 accent-brand"
              checked={d.enabled}
              disabled={toggle.isPending || (!hasApprovedCodebook && !d.enabled)}
              onChange={(e) => toggle.mutate(e.target.checked)}
            />
            Analyze new reviews nightly
          </label>
        ) : (
          <span className="text-sm font-medium">{d.enabled ? "On" : "Off"}</span>
        )}
      </div>
      {!hasApprovedCodebook && <p className="mt-2 text-xs text-muted">Approve a codebook first: nightly runs tag reviews with its themes.</p>}
      {toggle.isError && <p className="mt-2 text-sm text-negative-ink">{toggle.error.message}</p>}
    </Card>
  );
}
