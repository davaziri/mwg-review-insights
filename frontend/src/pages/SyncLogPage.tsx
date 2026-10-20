import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import type { SyncRunWithTitle } from "../api/types";
import { Badge } from "../components/ui";
import { dateTime, number } from "../lib/format";

const STATUS_TONE = { queued: "slate", running: "blue", succeeded: "green", failed: "red" } as const;

export function SyncLogPage() {
  const runs = useQuery({
    queryKey: ["sync-runs"],
    queryFn: () => api.syncRuns(200),
    refetchInterval: (q) => (q.state.data?.some((r) => r.status === "queued" || r.status === "running") ? 2000 : 30000),
  });

  return (
    <div>
      <h1 className="text-xl font-semibold">Sync log</h1>
      <p className="mb-5 text-sm text-muted">
        Every review sync, newest first. Nightly syncs run automatically; full crawls run weekly and check for deleted reviews.
      </p>

      {runs.isPending && <p className="text-sm text-muted">Loading...</p>}
      {runs.isError && <p className="text-sm text-negative-ink">Could not load the sync log: {runs.error.message}</p>}
      {runs.data?.length === 0 && <p className="text-sm text-muted">No syncs yet.</p>}

      {!!runs.data?.length && (
        <div className="overflow-x-auto rounded-lg border border-line bg-surface">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line bg-subtle text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-3 py-2">Queued</th>
                <th className="px-3 py-2">Title</th>
                <th className="px-3 py-2">Type</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2 text-right">Pages</th>
                <th className="px-3 py-2 text-right">New</th>
                <th className="px-3 py-2 text-right">Edited</th>
                <th className="px-3 py-2 text-right">Deleted</th>
                <th className="px-3 py-2 text-right">Steam total</th>
                <th className="px-3 py-2">Notes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line-soft">
              {runs.data.map((r) => (
                <RunRow key={r.id} run={r} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function RunRow({ run }: { run: SyncRunWithTitle }) {
  const note = run.error ?? run.warning ?? (run.resumed_from_id ? `Resumed run #${run.resumed_from_id}` : "");
  return (
    <tr className="align-top">
      <td className="whitespace-nowrap px-3 py-2 text-ink-2">{dateTime(run.queued_at)}</td>
      <td className="px-3 py-2">
        <div className="font-medium">{run.title_name}</div>
        <div className="text-xs text-muted">App {run.app_id}</div>
      </td>
      <td className="px-3 py-2 text-ink-2">
        {run.mode === "full" ? "Full" : "Incremental"}
        <div className="text-xs text-muted">{run.trigger === "schedule" ? "Nightly" : "Manual"}</div>
      </td>
      <td className="px-3 py-2">
        <Badge tone={STATUS_TONE[run.status]}>{run.status[0].toUpperCase() + run.status.slice(1)}</Badge>
      </td>
      <td className="px-3 py-2 text-right tabular-nums">{number(run.pages_fetched)}</td>
      <td className="px-3 py-2 text-right tabular-nums">{number(run.new_count)}</td>
      <td className="px-3 py-2 text-right tabular-nums">{number(run.updated_count)}</td>
      <td className="px-3 py-2 text-right tabular-nums">{number(run.deleted_count)}</td>
      <td className="px-3 py-2 text-right tabular-nums">{run.steam_total === null ? "" : number(run.steam_total)}</td>
      <td className={`max-w-xs px-3 py-2 text-xs ${run.error ? "text-negative-ink" : "text-muted"}`}>{note}</td>
    </tr>
  );
}
