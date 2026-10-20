import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";

import { api } from "../api/client";
import { STATUS_LABELS, type AppCard, type PortfolioCard, type ThemeHighlights } from "../api/types";
import { WeeklyBars } from "../components/charts/WeeklyBars";
import { Badge, Button } from "../components/ui";
import { shareFloor, timeAgo } from "../lib/format";

function TrendLine({ app }: { app: AppCard }) {
  const { last, previous, days } = app.trend;
  if (!last.reviews) return <span>No reviews in the last {days} days</span>;
  const now = last.positive_share ?? 0;
  const delta = previous.reviews && previous.positive_share !== null ? Math.round((now - previous.positive_share) * 100) : null;
  return (
    <span>
      Last {days} days: <span className="font-medium text-ink">{last.reviews}</span> {last.reviews === 1 ? "review" : "reviews"},{" "}
      <span className="font-medium text-ink">{shareFloor(now)}</span> recommended
      {delta !== null && delta !== 0 && (
        <span className={delta > 0 ? "text-positive-ink" : "text-negative-ink"}>
          {" "}
          ({delta > 0 ? "▲ up" : "▼ down"} {Math.abs(delta)} pts vs the {days} days before)
        </span>
      )}
      {delta === 0 && <span> (same as the {days} days before)</span>}
    </span>
  );
}

function Highlights({ themes }: { themes: ThemeHighlights | null }) {
  if (!themes) return <p className="text-xs text-muted">Themes appear once the reviews are analyzed.</p>;
  const row = (label: string, t: ThemeHighlights["top_praised"], kind: "positive" | "negative") => (
    <div className="flex items-baseline gap-2 text-sm">
      <span className="w-28 shrink-0 text-xs text-muted">{label}</span>
      {t ? (
        <span className="min-w-0">
          <span className="font-medium">{t.name}</span>{" "}
          <span className="text-xs text-muted">
            ({t[kind]} {kind} {t[kind] === 1 ? "mention" : "mentions"})
          </span>
        </span>
      ) : (
        <span className="text-xs text-muted">None yet</span>
      )}
    </div>
  );
  return (
    <div className="space-y-1">
      {row("Most praised", themes.top_praised, "positive")}
      {row("Most criticized", themes.top_criticized, "negative")}
    </div>
  );
}

function TitleCard({ t }: { t: PortfolioCard }) {
  // Before launch some titles only have demo reviews; the card then shows the demo.
  const showDemo = !t.reviews && !!t.demo?.reviews;
  const app: AppCard = showDemo && t.demo ? t.demo : t;
  const themes = showDemo ? (t.demo?.themes ?? null) : t.themes;
  const link = { pathname: `/titles/${t.id}`, search: showDemo ? `?app=${t.demo!.app_id}` : "" };

  return (
    <article className="flex flex-col overflow-hidden rounded-lg border border-line bg-surface">
      <Link to={link} className="block aspect-[460/215] bg-soft" tabIndex={-1} aria-hidden>
        {t.header_image_url && (
          <img src={t.header_image_url} alt="" className="h-full w-full object-cover" loading="lazy" onError={(e) => (e.currentTarget.style.visibility = "hidden")} />
        )}
      </Link>
      <div className="flex flex-1 flex-col gap-3 p-4">
        <div>
          <div className="flex items-start gap-2">
            <h2 className="mr-auto text-base font-semibold">
              <Link to={link} className="hover:underline">
                {t.name}
              </Link>
            </h2>
            <Badge>{STATUS_LABELS[t.status]}</Badge>
          </div>
          {t.developers.length > 0 && <div className="text-xs text-muted">{t.developers.join(", ")}</div>}
        </div>

        {app.reviews === 0 ? (
          <p className="text-sm text-ink-2">No reviews yet. Reviews start syncing on their own once the first one is posted.</p>
        ) : (
          <>
            {showDemo && <p className="text-xs text-muted">Showing the demo, where all of this title's reviews are so far.</p>}
            <div className="flex flex-wrap items-baseline gap-x-5 gap-y-1">
              <div>
                <span className="text-2xl font-semibold">{shareFloor(app.positive_share)}</span>{" "}
                <span className="text-xs text-muted">recommended</span>
              </div>
              <div>
                <span className="text-lg font-semibold">{app.reviews.toLocaleString()}</span> <span className="text-xs text-muted">reviews</span>
              </div>
              {app.steam?.review_score_desc && <span className="text-sm text-ink-2">Steam: {app.steam.review_score_desc}</span>}
            </div>
            <div>
              <WeeklyBars weekly={app.weekly} />
              <p className="mt-1 text-xs text-muted">
                <TrendLine app={app} />
              </p>
            </div>
            <Highlights themes={themes} />
          </>
        )}

        <div className="mt-auto flex items-center gap-2 border-t border-line-soft pt-2 text-xs text-muted">
          {t.syncing ? <span>Syncing now...</span> : <span>Synced {timeAgo(t.last_synced_at)}</span>}
          {t.demo && !showDemo && t.demo.reviews > 0 && <span className="ml-auto">Demo: {t.demo.reviews.toLocaleString()} reviews</span>}
        </div>
      </div>
    </article>
  );
}

export function PortfolioPage() {
  const portfolio = useQuery({ queryKey: ["portfolio"], queryFn: api.portfolio, refetchInterval: 60_000 });
  if (portfolio.isPending) return <p className="text-sm text-muted">Loading...</p>;
  if (portfolio.isError) return <p className="text-sm text-negative-ink">Could not load the portfolio: {portfolio.error.message}</p>;
  const titles = portfolio.data.titles;
  const total = titles.reduce((n, t) => n + t.reviews + (t.demo?.reviews ?? 0), 0);

  return (
    <div>
      <div className="mb-5 flex flex-wrap items-end gap-3">
        <div className="mr-auto">
          <h1 className="text-xl font-semibold">Portfolio</h1>
          <p className="text-sm text-muted">
            {titles.length} titles, {total.toLocaleString()} Steam reviews collected. Recommended shares are rounded down, the way Steam shows them.
          </p>
        </div>
        <Link to="/compare">
          <Button>Compare titles</Button>
        </Link>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {titles.map((t) => (
          <TitleCard key={t.id} t={t} />
        ))}
      </div>
    </div>
  );
}
