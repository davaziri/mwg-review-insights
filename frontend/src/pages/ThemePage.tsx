import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Link, useParams, useSearchParams } from "react-router";

import { api } from "../api/client";
import { SentimentBar } from "../components/analysis/ThemesTable";
import { SentimentOverTime } from "../components/charts/SentimentOverTime";
import { ReviewList } from "../components/ReviewList";
import { useTitle } from "../components/TitleShell";
import { Card, StatTile } from "../components/ui";
import { filterQuery } from "../lib/filters";
import { pct } from "../lib/format";

const TABS = [
  { value: "", label: "All" },
  { value: "positive", label: "Positive" },
  { value: "mixed", label: "Mixed" },
  { value: "negative", label: "Negative" },
] as const;

/** One theme: what it covers, how its sentiment moved over time, and the reviews behind it. */
export function ThemePage() {
  const { title, appId, filters, search } = useTitle();
  const key = useParams().key!;
  const [params, setParams] = useSearchParams();
  const sentiment = params.get("sentiment") ?? "";

  const stats = useQuery({
    queryKey: ["stats", title.id, filterQuery(filters)],
    queryFn: () => api.stats(title.id, filters),
    placeholderData: keepPreviousData,
  });
  const overview = useQuery({ queryKey: ["analysis", title.id, appId], queryFn: () => api.analysis(title.id, appId) });

  if (stats.isPending) return <p className="text-sm text-muted">Loading...</p>;
  if (stats.isError) return <p className="text-sm text-negative-ink">Could not load: {stats.error.message}</p>;
  const theme = stats.data.themes.find((t) => t.key === key);
  const notes = overview.data?.approved_codebook?.themes?.find((t) => t.key === key);
  const back = (
    <Link to={{ pathname: `/titles/${title.id}`, search }} className="text-sm text-muted hover:underline">
      All themes
    </Link>
  );
  if (!theme) {
    return (
      <Card>
        {back}
        <p className="mt-2 text-sm text-ink-2">This theme is not in the approved codebook any more.</p>
      </Card>
    );
  }
  const analyzedByMonth = Object.fromEntries(stats.data.months.map((m) => [m.month, m.analyzed]));
  const setSentiment = (value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set("sentiment", value);
    else next.delete("sentiment");
    next.delete("page");
    setParams(next, { replace: true });
  };

  return (
    <div className={stats.isPlaceholderData ? "opacity-60 transition-opacity" : "transition-opacity"}>
      {back}
      <h2 className="mt-1 text-lg font-semibold">{theme.name}</h2>
      <p className="mt-1 max-w-3xl text-sm text-ink-2">{theme.definition}</p>
      {notes && (notes.include_notes || notes.exclude_notes) && (
        <details className="mt-2 max-w-3xl text-sm">
          <summary className="cursor-pointer text-link">What counts and what doesn't</summary>
          {notes.include_notes && (
            <p className="mt-1 text-ink-2">
              <span className="font-medium">Counts:</span> {notes.include_notes}
            </p>
          )}
          {notes.exclude_notes && (
            <p className="mt-1 text-ink-2">
              <span className="font-medium">Doesn't count:</span> {notes.exclude_notes}
            </p>
          )}
        </details>
      )}

      <div className="my-5 grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatTile label="Share of reviews" value={pct(theme.share)} detail={`${theme.mentions} of ${stats.data.counts.analyzed} analyzed reviews`} />
        <StatTile
          label="Net sentiment"
          value={theme.net === null ? "n/a" : `${theme.net > 0 ? "+" : ""}${Math.round(theme.net * 100)}`}
          detail="From -100 (all negative) to +100 (all positive)"
        />
        <div className="col-span-2 rounded-lg border border-line bg-surface px-4 py-3">
          <div className="mb-2 text-xs font-medium text-muted">Sentiment of mentions</div>
          <SentimentBar t={theme} />
        </div>
      </div>

      <Card title="Mentions per month">
        <SentimentOverTime monthly={theme.monthly} analyzedByMonth={analyzedByMonth} />
      </Card>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h3 className="mr-2 text-base font-semibold">Reviews</h3>
        <div className="flex rounded-md border border-line p-0.5 text-sm" role="radiogroup" aria-label="Sentiment">
          {TABS.map((t) => (
            <button
              key={t.value}
              type="button"
              role="radio"
              aria-checked={sentiment === t.value}
              onClick={() => setSentiment(t.value)}
              className={`rounded px-3 py-1 ${sentiment === t.value ? "bg-soft font-medium text-ink" : "text-ink-2 hover:text-ink"}`}
            >
              {t.label}
              {t.value && <span className="ml-1 text-muted">({theme[t.value]})</span>}
            </button>
          ))}
        </div>
      </div>
      <ReviewList
        titleId={title.id}
        filters={filters}
        query={{ theme: key, sentiment: sentiment || undefined }}
        focusTheme={key}
        empty="No reviews mention this theme with these filters."
      />
    </div>
  );
}
