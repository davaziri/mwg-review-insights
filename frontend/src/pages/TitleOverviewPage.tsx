import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Link } from "react-router";

import { api } from "../api/client";
import { OverallImpression } from "../components/analysis/OverallImpression";
import { SummaryPanel } from "../components/analysis/SummaryPanel";
import { ThemesTable } from "../components/analysis/ThemesTable";
import { VolumeChart } from "../components/charts/VolumeChart";
import { useTitle } from "../components/TitleShell";
import { Card, StatTile } from "../components/ui";
import { activeFilterCount, filterQuery } from "../lib/filters";
import { percent } from "../lib/format";

function replyTime(hours: number | null): string {
  if (hours === null) return "";
  if (hours < 48) return `usually within ${Math.max(1, Math.round(hours))} hours`;
  return `usually after ${Math.round(hours / 24)} days`;
}

function replyRate(responded: number, reviews: number): string {
  if (!reviews) return "n/a";
  if (!responded) return "None";
  return responded / reviews < 0.01 ? "Under 1%" : percent(responded, reviews);
}

export function TitleOverviewPage() {
  const { title, appId, filters, search } = useTitle();
  const stats = useQuery({
    queryKey: ["stats", title.id, filterQuery(filters)],
    queryFn: () => api.stats(title.id, filters),
    placeholderData: keepPreviousData,
  });
  const app = title.apps.find((a) => a.app_id === appId);
  const snapshot = app?.latest_snapshot;

  if (stats.isPending) return <p className="text-sm text-muted">Loading...</p>;
  if (stats.isError) return <p className="text-sm text-negative-ink">Could not load: {stats.error.message}</p>;
  const s = stats.data;
  const c = s.counts;
  const filtered = activeFilterCount(filters) > 0;
  const themeNames = Object.fromEntries(s.themes.map((t) => [t.key, t.name]));

  if (!app?.stored_reviews) {
    return (
      <Card>
        <p className="text-sm text-ink-2">
          No reviews yet. The nightly sync checks Steam every day and starts collecting reviews as soon as the first one is posted.
        </p>
      </Card>
    );
  }

  return (
    <div className={stats.isPlaceholderData ? "opacity-60 transition-opacity" : "transition-opacity"}>
      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatTile label={filtered ? "Reviews (filtered)" : "Reviews"} value={c.reviews.toLocaleString()} detail={`${c.with_content.toLocaleString()} with text to analyze`} />
        <StatTile
          label="Recommended"
          value={c.reviews ? percent(c.positive_votes, c.reviews) : "n/a"}
          detail={`${c.positive_votes.toLocaleString()} of ${c.reviews.toLocaleString()} reviews`}
        />
        <StatTile
          label="Steam rating"
          value={snapshot?.review_score_desc ?? "None yet"}
          detail={snapshot?.total_reviews ? `All ${snapshot.total_reviews.toLocaleString()} reviews on Steam, before filters` : undefined}
        />
        <StatTile
          label="Developer replies"
          value={replyRate(s.developer_response.responded, c.reviews)}
          detail={
            s.developer_response.responded
              ? `${s.developer_response.responded} ${s.developer_response.responded === 1 ? "reply" : "replies"}, ${replyTime(s.developer_response.median_hours)}`
              : "No replies to these reviews"
          }
        />
      </div>

      <Card title="Reviews per month">
        <VolumeChart months={s.months} />
      </Card>

      {s.codebook && c.analyzed > 0 ? (
        <>
          <SummaryPanel titleId={title.id} appId={appId} themeNames={themeNames} />
          <OverallImpression stats={s} />
          <ThemesTable stats={s} titleId={title.id} search={search} />
        </>
      ) : (
        <Card title="Themes">
          <p className="text-sm text-ink-2">
            {s.codebook
              ? filtered
                ? "No analyzed reviews match these filters."
                : "The themes are approved but no reviews have been analyzed yet."
              : "This title's reviews haven't been analyzed yet."}{" "}
            <Link to={{ pathname: `/titles/${title.id}/analysis`, search }} className="text-link hover:underline">
              Go to themes setup
            </Link>
          </p>
        </Card>
      )}
    </div>
  );
}
