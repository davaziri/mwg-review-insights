import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { api } from "../api/client";
import type { AppStats, Title } from "../api/types";
import { STATUS_LABELS } from "../api/types";
import { TitleFormDialog } from "../components/TitleFormDialog";
import { Badge, Button } from "../components/ui";
import { dateTime, number, percent, timeAgo } from "../lib/format";

const hasActiveRun = (titles: Title[] | undefined) =>
  !!titles?.some((t) => t.apps.some((a) => a.active_run));

export function TitlesPage() {
  const queryClient = useQueryClient();
  const [showArchived, setShowArchived] = useState(false);
  const [editing, setEditing] = useState<Title | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const titles = useQuery({
    queryKey: ["titles", showArchived],
    queryFn: () => api.listTitles(showArchived),
    refetchInterval: (q) => (hasActiveRun(q.state.data) ? 2000 : 30000),
  });

  const run = useMutation({
    mutationFn: (fn: () => Promise<unknown>) => fn(),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["titles"] });
      queryClient.invalidateQueries({ queryKey: ["sync-runs"] });
    },
    onError: (e: Error) => setError(e.message),
  });

  const act = (fn: () => Promise<unknown>) => run.mutate(fn);

  return (
    <div>
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <div className="mr-auto">
          <h1 className="text-xl font-semibold">Titles</h1>
          <p className="text-sm text-slate-500">Every tracked Steam title and its review sync status.</p>
        </div>
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />
          Show archived
        </label>
        <Button onClick={() => act(api.syncAll)}>Sync all</Button>
        <Button variant="primary" onClick={() => setEditing("new")}>
          Add title
        </Button>
      </div>

      {error && (
        <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>
      )}

      {titles.isPending && <p className="text-sm text-slate-500">Loading titles...</p>}
      {titles.isError && <p className="text-sm text-red-700">Could not load titles: {titles.error.message}</p>}

      <div className="divide-y divide-slate-200 overflow-hidden rounded-lg border border-slate-200 bg-white">
        {titles.data?.map((t) => (
          <TitleRow key={t.id} title={t} act={act} onEdit={() => setEditing(t)} />
        ))}
        {titles.data?.length === 0 && <p className="p-6 text-sm text-slate-500">No titles yet. Add one to start syncing.</p>}
      </div>

      {editing && (
        <TitleFormDialog
          title={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            queryClient.invalidateQueries({ queryKey: ["titles"] });
          }}
        />
      )}
    </div>
  );
}

function TitleRow({ title, act, onEdit }: { title: Title; act: (fn: () => Promise<unknown>) => void; onEdit: () => void }) {
  const main = title.apps.find((a) => !a.is_demo);
  const demo = title.apps.find((a) => a.is_demo);
  const busy = title.apps.some((a) => a.active_run);
  const running = title.apps.some((a) => a.active_run?.status === "running");
  const archived = !!title.archived_at;
  const details = [title.developers?.join(", "), title.release_date_text].filter(Boolean).join(" · ");

  return (
    <div className={`flex flex-col gap-4 p-4 md:flex-row md:items-center ${archived ? "opacity-60" : ""}`}>
      <div className="flex min-w-0 flex-1 items-center gap-4">
        <HeaderImage url={title.header_image_url} />
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate font-semibold">{title.name}</span>
            <Badge tone={title.status === "released" ? "green" : "blue"}>{STATUS_LABELS[title.status]}</Badge>
            {archived && <Badge>Archived</Badge>}
          </div>
          <div className="mt-0.5 truncate text-sm text-slate-500">
            {details && <span>{details} · </span>}
            <a
              className="hover:underline"
              href={`https://store.steampowered.com/app/${title.steam_app_id}/`}
              target="_blank"
              rel="noreferrer"
            >
              App {title.steam_app_id}
            </a>
          </div>
        </div>
      </div>

      <div className="w-full md:w-56">
        {main && <ReviewStats stats={main} />}
        {demo && (
          <div className="mt-1 text-xs text-slate-500">
            Demo ({demo.app_id}): {demo.stored_reviews ? `${number(demo.stored_reviews)} reviews` : "no reviews yet"}
          </div>
        )}
      </div>

      <div className="w-full text-sm md:w-48">
        {title.apps.map((a) => (
          <SyncStatus key={a.app_id} stats={a} showApp={title.apps.length > 1} />
        ))}
      </div>

      <div className="flex items-center gap-2 md:w-36 md:justify-end">
        <Button variant="primary" disabled={busy || archived} onClick={() => act(() => api.syncTitle(title.id))}>
          {running ? "Syncing" : busy ? "Queued" : "Sync now"}
        </Button>
        <MoreMenu
          items={[
            !archived && { label: "Full re-sync", disabled: busy, onClick: () => act(() => api.syncTitle(title.id, "full")) },
            { label: "Edit", onClick: onEdit },
            archived
              ? { label: "Unarchive", onClick: () => act(() => api.unarchiveTitle(title.id)) }
              : { label: "Archive", onClick: () => act(() => api.archiveTitle(title.id)) },
            {
              label: "Remove",
              danger: true,
              onClick: () => {
                if (
                  window.confirm(
                    `Remove ${title.name} and every review stored for it? This can't be undone. Archive instead to keep the history.`,
                  )
                )
                  act(() => api.deleteTitle(title.id));
              },
            },
          ]}
        />
      </div>
    </div>
  );
}

function HeaderImage({ url }: { url: string | null }) {
  const [failed, setFailed] = useState(false);
  if (!url || failed) return <div className="h-[60px] w-32 shrink-0 rounded bg-slate-100" />;
  return <img src={url} alt="" onError={() => setFailed(true)} className="h-[60px] w-32 shrink-0 rounded object-cover" />;
}

function ReviewStats({ stats }: { stats: AppStats }) {
  const snap = stats.latest_snapshot;
  const steamTotal = snap?.total_reviews ?? null;
  if (stats.stored_reviews === 0 && !steamTotal) {
    return <div className="text-sm text-slate-500">No reviews yet</div>;
  }
  return (
    <div>
      <div className="flex items-baseline gap-2">
        <span className="text-lg font-semibold">{number(stats.stored_reviews)}</span>
        <span className="text-sm text-slate-500">reviews</span>
        <span className="text-sm font-medium text-positive">
          {percent(stats.stored_positive, stats.stored_reviews)} positive
        </span>
      </div>
      <div className="text-xs text-slate-500">
        {snap?.review_score_desc && <span>{snap.review_score_desc}</span>}
        {steamTotal !== null && steamTotal !== stats.stored_reviews && (
          <span> · Steam reports {number(steamTotal)}</span>
        )}
      </div>
    </div>
  );
}

function SyncStatus({ stats, showApp }: { stats: AppStats; showApp: boolean }) {
  const label = showApp ? (stats.is_demo ? "Demo: " : "Main: ") : "";
  const active = stats.active_run;
  if (active) {
    return (
      <div className="text-blue-800">
        {label}
        {active.status === "queued" ? "Queued" : `Syncing, page ${active.pages_fetched + 1}`}
        {active.mode === "full" && <span className="text-slate-500"> (full)</span>}
      </div>
    );
  }
  const last = stats.last_run;
  if (!last) return <div className="text-slate-500">{label}Never synced</div>;
  if (last.status === "failed") {
    return (
      <div className="text-negative" title={last.error ?? ""}>
        {label}Last sync failed {timeAgo(last.finished_at)}
        <div className="text-xs text-slate-500">Next sync resumes where it stopped</div>
      </div>
    );
  }
  const changes = [
    last.new_count && `${number(last.new_count)} new`,
    last.updated_count && `${number(last.updated_count)} edited`,
    last.deleted_count && `${number(last.deleted_count)} deleted`,
  ].filter(Boolean);
  return (
    <div title={dateTime(last.finished_at)}>
      <span className="text-slate-700">
        {label}Synced {timeAgo(last.finished_at)}
      </span>
      <div className="text-xs text-slate-500">{changes.length ? changes.join(", ") : "No changes"}</div>
      {last.warning && (
        <div className="text-xs text-mixed" title={last.warning}>
          Check sync log
        </div>
      )}
    </div>
  );
}

type MenuItem = { label: string; onClick: () => void; danger?: boolean; disabled?: boolean };

function MoreMenu({ items }: { items: (MenuItem | false)[] }) {
  const ref = useRef<HTMLDetailsElement>(null);
  return (
    <details ref={ref} className="relative">
      <summary className="cursor-pointer list-none rounded-md px-2 py-1.5 text-slate-500 hover:bg-slate-100" aria-label="More actions">
        •••
      </summary>
      <div className="absolute right-0 z-10 mt-1 w-40 rounded-md border border-slate-200 bg-white py-1 shadow-lg">
        {items.filter((i): i is MenuItem => !!i).map((item) => (
          <button
            key={item.label}
            type="button"
            disabled={item.disabled}
            className={`block w-full px-3 py-1.5 text-left text-sm hover:bg-slate-50 disabled:opacity-50 ${
              item.danger ? "text-red-700" : "text-slate-700"
            }`}
            onClick={() => {
              ref.current?.removeAttribute("open");
              item.onClick();
            }}
          >
            {item.label}
          </button>
        ))}
      </div>
    </details>
  );
}
