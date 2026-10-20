import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router";

import { api } from "../api/client";
import type { AlertRow } from "../api/types";
import { AdminOnly } from "../auth";
import { SyncRunsSection } from "../components/SyncRunsSection";
import { Badge, Button } from "../components/ui";
import { dateTime, money } from "../lib/format";

const TABS = [
  { key: "syncs", label: "Syncs" },
  { key: "analyses", label: "Analyses" },
  { key: "alerts", label: "Alerts" },
] as const;

const RUN_TONE = { estimated: "slate", queued: "slate", running: "blue", succeeded: "green", failed: "red", canceled: "slate" } as const;
const RUN_WORD = { estimated: "Waiting for confirmation", queued: "Queued", running: "Running", succeeded: "Done", failed: "Failed", canceled: "Canceled" } as const;

function AnalysesSection() {
  const runs = useQuery({
    queryKey: ["analysis-runs"],
    queryFn: () => api.analysisRuns(200),
    refetchInterval: (q) => (q.state.data?.some((r) => r.status === "queued" || r.status === "running") ? 5000 : 30000),
  });
  // Estimates nobody confirmed are not runs; nightly ones waiting for an admin are.
  const shown = (runs.data ?? []).filter((r) => r.confirmed_at || r.trigger === "nightly");
  return (
    <div>
      <p className="mb-4 text-sm text-muted">
        Theme discovery and analysis runs, newest first, with what each cost. Nightly runs analyze new reviews for titles where it is switched on
        (in Themes setup).
      </p>
      {runs.isPending && <p className="text-sm text-muted">Loading...</p>}
      {runs.isError && <p className="text-sm text-negative-ink">{runs.error.message}</p>}
      {runs.data && shown.length === 0 && <p className="text-sm text-muted">No analyses yet.</p>}
      {shown.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-line bg-surface">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead className="border-b border-line text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-3 py-2">Started</th>
                <th className="px-3 py-2">Title</th>
                <th className="px-3 py-2">Run</th>
                <th className="px-3 py-2">By</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2 text-right">Reviews</th>
                <th className="px-3 py-2 text-right">Cost</th>
                <th className="px-3 py-2">Notes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line-soft">
              {shown.map((r) => (
                <tr key={r.id} className="align-top">
                  <td className="px-3 py-2 whitespace-nowrap">{dateTime(r.confirmed_at ?? r.created_at)}</td>
                  <td className="px-3 py-2">
                    <Link to={`/titles/${r.title_id}/analysis`} className="text-link hover:underline">
                      {r.title_name}
                    </Link>
                  </td>
                  <td className="px-3 py-2">{r.kind === "discovery" ? "Find themes" : "Analyze reviews"}</td>
                  <td className="px-3 py-2 text-ink-2">{r.trigger === "nightly" ? "Nightly" : (r.confirmed_by ?? r.requested_by ?? "")}</td>
                  <td className="px-3 py-2">
                    <Badge tone={RUN_TONE[r.status]}>{RUN_WORD[r.status]}</Badge>
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{r.kind === "analysis" ? r.reviews_tagged || r.reviews_in_scope : ""}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{r.confirmed_at ? money(r.actual_cost_usd) : `est. ${money(r.est_cost_usd)}`}</td>
                  <td className="max-w-xs px-3 py-2 text-xs text-muted">{r.error ?? r.warning ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

const ALERT_WORD: Record<AlertRow["kind"], { label: string; tone: "red" | "amber" | "blue" | "slate" }> = {
  sync_failed: { label: "Sync failed", tone: "red" },
  analysis_failed: { label: "Analysis failed", tone: "red" },
  needs_confirmation: { label: "Needs an admin", tone: "amber" },
  positive_drop: { label: "Recommended dropped", tone: "amber" },
  test: { label: "Test", tone: "slate" },
};

function delivery(a: AlertRow): string {
  const sent = a.channels.map((c) => (c === "slack" ? "Slack" : "email")).join(" and ");
  if (a.error) return sent ? `Sent to ${sent}. ${a.error}` : `Not sent. ${a.error}`;
  return sent ? `Sent to ${sent}` : "Not sent: no Slack or email set up";
}

function AlertsSection() {
  const queryClient = useQueryClient();
  const alerts = useQuery({ queryKey: ["alerts"], queryFn: api.alerts, refetchInterval: 60_000 });
  const test = useMutation({ mutationFn: api.testAlert, onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts"] }) });
  const ch = alerts.data?.channels;
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-start gap-3">
        <p className="mr-auto max-w-2xl text-sm text-muted">
          The worker checks every few minutes for failed syncs and analyses, nightly analyses waiting for an admin, and titles whose share of
          recommended reviews fell more than 5 points in 7 days. Each alert is sent once.
          {ch && (
            <>
              {" "}
              Slack: <b className="text-ink">{ch.slack ? "on" : "not set up"}</b>. Email: <b className="text-ink">{ch.email ? "on" : "not set up"}</b>.
            </>
          )}
        </p>
        <AdminOnly>
          <Button onClick={() => test.mutate()} disabled={test.isPending || (!!ch && !ch.slack && !ch.email)}>
            {test.isPending ? "Sending..." : "Send a test alert"}
          </Button>
        </AdminOnly>
      </div>
      {test.data && <p className="mb-3 text-sm text-ink-2">Test alert: {delivery(test.data)}.</p>}
      {alerts.isPending && <p className="text-sm text-muted">Loading...</p>}
      {alerts.isError && <p className="text-sm text-negative-ink">{alerts.error.message}</p>}
      {alerts.data?.alerts.length === 0 && <p className="text-sm text-muted">No alerts yet.</p>}
      <div className="space-y-3">
        {alerts.data?.alerts.map((a) => (
          <article key={a.id} className="rounded-lg border border-line bg-surface p-4">
            <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-muted">
              <Badge tone={ALERT_WORD[a.kind].tone}>{ALERT_WORD[a.kind].label}</Badge>
              <span>{dateTime(a.created_at)}</span>
              <span className="ml-auto">{delivery(a)}</span>
            </div>
            <h3 className="text-sm font-semibold">{a.subject}</h3>
            <p className="mt-1 whitespace-pre-wrap text-sm text-ink-2">{a.body}</p>
          </article>
        ))}
      </div>
    </div>
  );
}

export function RunLogPage() {
  const [params, setParams] = useSearchParams();
  const tab = TABS.find((t) => t.key === params.get("tab"))?.key ?? "syncs";
  return (
    <div>
      <h1 className="text-xl font-semibold">Run log</h1>
      <nav className="mt-3 mb-5 flex gap-1 border-b border-line" aria-label="Run log sections">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setParams(t.key === "syncs" ? {} : { tab: t.key })}
            aria-current={tab === t.key ? "page" : undefined}
            className={`border-b-2 px-3 py-2 text-sm font-medium ${tab === t.key ? "border-brand text-ink" : "border-transparent text-ink-2 hover:text-ink"}`}
          >
            {t.label}
          </button>
        ))}
      </nav>
      {tab === "syncs" && <SyncRunsSection />}
      {tab === "analyses" && <AnalysesSection />}
      {tab === "alerts" && <AlertsSection />}
    </div>
  );
}
