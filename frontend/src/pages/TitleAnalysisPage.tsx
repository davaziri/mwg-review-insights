import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { api } from "../api/client";
import { CodebookPanel } from "../components/analysis/CodebookPanel";
import { RunPanel } from "../components/analysis/RunPanel";
import { SpotCheck } from "../components/analysis/SpotCheck";
import { useTitle } from "../components/TitleShell";
import { Card } from "../components/ui";

/** Themes setup: find themes, review the codebook, run analysis, and spot-check the tags. */
export function TitleAnalysisPage() {
  const { title, appId } = useTitle();
  const titleId = title.id;
  const queryClient = useQueryClient();

  const overview = useQuery({
    queryKey: ["analysis", titleId, appId],
    queryFn: () => api.analysis(titleId, appId),
    refetchInterval: (q) => (q.state.data?.active_run ? 3000 : 30000),
  });
  const data = overview.data;
  const approved = data?.approved_codebook ?? null;

  // When a run finishes, refresh everything that depends on its results.
  const lastActive = useRef<number | null>(null);
  useEffect(() => {
    const current = data?.active_run?.id ?? null;
    if (lastActive.current !== null && current === null) {
      for (const key of ["stats", "summary", "codebook", "spot-check", "reviews", "portfolio"]) queryClient.invalidateQueries({ queryKey: [key] });
    }
    lastActive.current = current;
  }, [data?.active_run?.id, queryClient]);

  if (overview.isPending) return <p className="text-sm text-muted">Loading...</p>;
  if (overview.isError || !data) return <p className="text-sm text-negative-ink">Could not load: {overview.error?.message}</p>;

  const workingCodebook = data.latest_codebook;
  const analyzed = data.reviews.with_content - (data.reviews.pending ?? data.reviews.with_content);

  return (
    <div>
      <RunPanel overview={data} />

      {workingCodebook ? (
        <CodebookPanel titleId={titleId} codebookId={workingCodebook.id} approvedId={approved?.id ?? null} />
      ) : (
        <Card title="Codebook">
          <p className="text-sm text-ink-2">
            No themes yet. Use Find themes: the analysis model reads a sample of up to 400 reviews and proposes 8 to 15 themes for you to
            review and approve.
          </p>
        </Card>
      )}

      {approved && analyzed > 0 && <SpotCheck titleId={titleId} appId={data.app_id} />}
    </div>
  );
}
