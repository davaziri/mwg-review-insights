import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { Link, useParams, useSearchParams } from "react-router";

import { api } from "../api/client";
import { CodebookPanel } from "../components/analysis/CodebookPanel";
import { RunPanel } from "../components/analysis/RunPanel";
import { SpotCheck } from "../components/analysis/SpotCheck";
import { OverallImpression } from "../components/analysis/OverallImpression";
import { SummaryPanel } from "../components/analysis/SummaryPanel";
import { ThemesTable } from "../components/analysis/ThemesTable";
import { Card } from "../components/ui";

export function TitleAnalysisPage() {
  const titleId = Number(useParams().id);
  const [params, setParams] = useSearchParams();
  const appParam = params.get("app");
  const appId = appParam ? Number(appParam) : undefined;
  const queryClient = useQueryClient();

  const overview = useQuery({
    queryKey: ["analysis", titleId, appId],
    queryFn: () => api.analysis(titleId, appId),
    refetchInterval: (q) => (q.state.data?.active_run ? 3000 : 30000),
  });
  const data = overview.data;
  const approved = data?.approved_codebook ?? null;
  const stats = useQuery({
    queryKey: ["stats", titleId, data?.app_id, approved?.id],
    queryFn: () => api.stats(titleId, data!.app_id),
    enabled: !!data && !!approved,
  });

  // When a run finishes, refresh everything that depends on its results.
  const lastActive = useRef<number | null>(null);
  useEffect(() => {
    const current = data?.active_run?.id ?? null;
    if (lastActive.current !== null && current === null) {
      for (const key of ["stats", "summary", "codebook", "spot-check"]) queryClient.invalidateQueries({ queryKey: [key] });
    }
    lastActive.current = current;
  }, [data?.active_run?.id, queryClient]);

  if (overview.isPending) return <p className="text-sm text-slate-500">Loading...</p>;
  if (overview.isError || !data) return <p className="text-sm text-red-700">Could not load: {overview.error?.message}</p>;

  const workingCodebook = data.latest_codebook;
  const themeNames = Object.fromEntries((approved?.themes ?? []).map((t) => [t.key, t.name]));
  const analyzed = stats.data?.counts.analyzed ?? 0;

  return (
    <div>
      <div className="mb-5">
        <Link to="/" className="text-sm text-slate-500 hover:underline">
          Titles
        </Link>
        <h1 className="text-xl font-semibold">{data.title.name}: themes</h1>
        {data.title.demo_app_id && (
          <div className="mt-2 flex gap-1 text-sm">
            {[
              { id: data.title.steam_app_id, label: "Main game" },
              { id: data.title.demo_app_id, label: "Demo" },
            ].map((a) => (
              <button
                key={a.id}
                type="button"
                onClick={() => setParams(a.id === data.title.steam_app_id ? {} : { app: String(a.id) })}
                className={`rounded-md px-3 py-1 ${data.app_id === a.id ? "bg-slate-200 font-medium" : "text-slate-600 hover:bg-slate-100"}`}
              >
                {a.label}
              </button>
            ))}
          </div>
        )}
      </div>

      <RunPanel overview={data} />

      {workingCodebook ? (
        <CodebookPanel titleId={titleId} codebookId={workingCodebook.id} approvedId={approved?.id ?? null} />
      ) : (
        <Card title="Codebook">
          <p className="text-sm text-slate-600">
            No themes yet. Use Find themes: the analysis model reads a sample of up to 400 reviews and proposes 8 to 15 themes for you to
            review and approve.
          </p>
        </Card>
      )}

      {approved && analyzed > 0 && (
        <>
          <SummaryPanel titleId={titleId} appId={data.app_id} themeNames={themeNames} />
          {stats.data && <OverallImpression stats={stats.data} />}
          {stats.data && <ThemesTable stats={stats.data} />}
          <SpotCheck titleId={titleId} appId={data.app_id} />
        </>
      )}
    </div>
  );
}
