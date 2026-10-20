import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { api } from "../api/client";
import { AdminOnly } from "../auth";
import type { CompareTheme, CompareTitle, Comparison } from "../api/types";
import { SentimentBar } from "../components/analysis/ThemesTable";
import { ChartOwner } from "../components/charts/ChartFrame";
import { CompareLines, type SeriesDef } from "../components/charts/CompareLines";
import { monthLabel, monthRange } from "../components/charts/parts";
import { Button, Card, Dialog, selectClass } from "../components/ui";
import { RANGE_LABELS, rangeStart, type RangePreset } from "../lib/filters";
import { dateTime, money, pct, shareFloor } from "../lib/format";
import { usePalette } from "../theme/mode";

const MAX = 4;
const MIN_QUARTER_REVIEWS = 5;

interface Pick {
  id: number;
  /** Which series color the title keeps while it stays picked. */
  slot: number;
}

/** Picks are stored as id.slot so removing a title never repaints the ones that stay. */
function readPicks(params: URLSearchParams): Pick[] {
  const picks: Pick[] = [];
  for (const value of params.getAll("t")) {
    const [id, slot] = value.split(".").map(Number);
    if (!id || picks.some((p) => p.id === id)) continue;
    picks.push({ id, slot: Number.isInteger(slot) && slot >= 0 && slot < MAX ? slot : -1 });
  }
  for (const p of picks) {
    if (p.slot === -1 || picks.filter((q) => q.slot === p.slot).length > 1) {
      p.slot = [0, 1, 2, 3].find((s) => !picks.some((q) => q !== p && q.slot === s)) ?? 0;
    }
  }
  return picks.slice(0, MAX);
}

function writePicks(params: URLSearchParams, picks: Pick[]): URLSearchParams {
  const next = new URLSearchParams(params);
  next.delete("t");
  picks.forEach((p) => next.append("t", `${p.id}.${p.slot}`));
  return next;
}

const quarterOf = (month: string) => `${month.slice(0, 4)}-Q${Math.floor((Number(month.slice(5, 7)) - 1) / 3) + 1}`;
const quarterLabel = (q: string, short = false) => (short ? `${q.slice(5)} '${q.slice(2, 4)}` : `${q.slice(5)} ${q.slice(0, 4)}`);
const net = (n: number | null) => (n === null ? "n/a" : `${n > 0 ? "+" : ""}${Math.round(n * 100)}`);

function Charts({ titles, series }: { titles: CompareTitle[]; series: SeriesDef[] }) {
  const all = titles.flatMap((t) => t.months.map((m) => m.month)).sort();
  if (!all.length) return <p className="text-sm text-muted">No reviews in this range.</p>;
  const months = monthRange(all[0], all[all.length - 1]);
  const byTitle = new Map(titles.map((t) => [t.id, new Map(t.months.map((m) => [m.month, m]))]));

  const volume = months.map((month) => ({
    x: month,
    ...Object.fromEntries(titles.map((t) => [String(t.id), byTitle.get(t.id)!.get(month)?.reviews ?? 0])),
  }));

  const quarters = [...new Set(months.map(quarterOf))];
  const counts: Record<string, Record<string, number>> = {};
  const positive = quarters.map((q) => {
    const row: { x: string } & Record<string, number | null | string> = { x: q };
    counts[q] = {};
    for (const t of titles) {
      const ms = t.months.filter((m) => quarterOf(m.month) === q);
      const n = ms.reduce((a, m) => a + m.reviews, 0);
      const pos = ms.reduce((a, m) => a + m.positive_votes, 0);
      counts[q][String(t.id)] = n;
      row[String(t.id)] = n >= MIN_QUARTER_REVIEWS ? Math.floor((100 * pos) / n) : null;
    }
    return row;
  });

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Card title="Reviews per month">
        <CompareLines label="Reviews per month" rows={volume} series={series} xLabel={monthLabel} format={(v) => String(Math.round(v))} />
      </Card>
      <Card title="Recommended, by quarter">
        <p className="mb-2 text-xs text-muted">Quarters with fewer than {MIN_QUARTER_REVIEWS} reviews are left out, since a handful of reviews swings the percentage.</p>
        <CompareLines
          label="Percent recommended by quarter"
          rows={positive}
          series={series}
          xLabel={quarterLabel}
          format={(v) => `${v}%`}
          domain={[0, 100]}
          dots
          note={(row) =>
            titles.map((t) => `${t.name}: ${counts[String(row.x)]?.[String(t.id)] ?? 0} reviews`).join(", ")
          }
        />
      </Card>
    </div>
  );
}

function ThemeCell({ theme }: { theme: CompareTheme | undefined }) {
  if (!theme) return <span className="text-xs text-faint">Not a theme here</span>;
  return (
    <div className="min-w-0">
      <div className="truncate text-xs text-muted" title={theme.definition}>
        {theme.name}
      </div>
      <div className="flex items-baseline gap-2 text-sm">
        <span className="font-medium tabular-nums">{pct(theme.share)}</span>
        <span className="text-xs text-muted">of reviews, net</span>
        <span className={`text-xs font-medium tabular-nums ${theme.net === null ? "text-faint" : theme.net >= 0 ? "text-positive-ink" : "text-negative-ink"}`}>{net(theme.net)}</span>
      </div>
      <div className="mt-1 max-w-48">
        <SentimentBar t={theme} />
      </div>
    </div>
  );
}

function MatchButton({ titleIds, onDone }: { titleIds: number[]; onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const estimate = useQuery({ queryKey: ["theme-match-estimate", titleIds], queryFn: () => api.estimateThemeMatch(titleIds), enabled: open, staleTime: 60_000 });
  const run = useMutation({
    mutationFn: () => api.runThemeMatch(titleIds),
    onSuccess: () => {
      setOpen(false);
      onDone();
    },
  });
  return (
    <>
      <Button variant="primary" onClick={() => setOpen(true)}>
        Match similar themes
      </Button>
      {open && (
        <Dialog title="Match similar themes" onClose={() => !run.isPending && setOpen(false)}>
          <p className="mb-3 text-sm text-ink-2">
            Each game's themes come from its own reviews, so the same topic can have a different name in each game. The analysis model reads
            the theme names and definitions (not the reviews) and groups the ones that are about the same thing. The result is saved and reused
            until one of these games gets a new codebook.
          </p>
          {estimate.isPending && <p className="text-sm text-muted">Working out the cost...</p>}
          {estimate.isError && <p className="text-sm text-negative-ink">{estimate.error.message}</p>}
          {estimate.data && (
            <p className="mb-3 rounded-md bg-subtle px-3 py-2 text-sm">
              Estimated cost: <span className="font-semibold">{money(estimate.data.cost_usd)}</span> ({estimate.data.model}, about{" "}
              {estimate.data.input_tokens.toLocaleString()} tokens in and {estimate.data.output_tokens.toLocaleString()} out).
            </p>
          )}
          {run.isError && <p className="mb-3 text-sm text-negative-ink">{run.error.message}</p>}
          <div className="flex justify-end gap-2">
            <Button onClick={() => setOpen(false)} disabled={run.isPending}>
              Don't run
            </Button>
            <Button variant="primary" onClick={() => run.mutate()} disabled={!estimate.data || run.isPending}>
              {run.isPending ? "Matching..." : `Run for about ${estimate.data ? money(estimate.data.cost_usd) : "..."}`}
            </Button>
          </div>
        </Dialog>
      )}
    </>
  );
}

function Themes({ data, colorOf, onMatched }: { data: Comparison; colorOf: (id: number) => string; onMatched: () => void }) {
  const tm = data.theme_match;
  const analyzed = data.titles.filter((t) => tm.eligible_title_ids.includes(t.id));
  const others = data.titles.filter((t) => !tm.eligible_title_ids.includes(t.id));
  const swatch = (t: CompareTitle) => <span className="inline-block h-0.5 w-3.5 rounded" style={{ background: colorOf(t.id) }} aria-hidden />;
  const notAnalyzed = others.length > 0 && (
    <p className="mt-3 text-xs text-muted">
      Not analyzed yet, so not in this comparison:{" "}
      {others.map((t, i) => (
        <span key={t.id}>
          {i > 0 && ", "}
          <Link to={`/titles/${t.id}/analysis`} className="text-link hover:underline">
            {t.name}
          </Link>
        </span>
      ))}
      .
    </p>
  );

  if (tm.status === "not_enough") {
    return (
      <Card title="Shared themes">
        <p className="text-sm text-ink-2">
          Comparing themes needs at least two titles with analyzed reviews.{" "}
          {analyzed.length === 1 ? `Only ${analyzed[0].name} has been analyzed so far.` : "None of these has been analyzed yet."}
        </p>
        {notAnalyzed}
      </Card>
    );
  }

  if (tm.status === "not_matched" || !tm.match) {
    return (
      <Card
        title="Shared themes"
        actions={
          <AdminOnly otherwise={<span className="text-xs text-muted">An admin can match the themes</span>}>
            <MatchButton titleIds={analyzed.map((t) => t.id)} onDone={onMatched} />
          </AdminOnly>
        }
      >
        <p className="mb-4 text-sm text-ink-2">
          These themes haven't been matched across games yet. Until then, here are each game's most mentioned themes side by side.
        </p>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {analyzed.map((t) => (
            <div key={t.id}>
              <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
                {swatch(t)}
                {t.name}
              </h3>
              <ul className="space-y-3">
                {[...t.themes].sort((a, b) => b.share - a.share).slice(0, 6).map((th) => (
                  <li key={th.key}>
                    <ThemeCell theme={th} />
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        {notAnalyzed}
      </Card>
    );
  }

  const matched = new Map(analyzed.map((t) => [t.id, new Set(tm.match!.groups.map((g) => g.themes[String(t.id)]).filter(Boolean))]));
  return (
    <Card title="Shared themes">
      <p className="mb-3 text-xs text-muted">
        Themes about the same thing across games, matched by {tm.match.model} on {dateTime(tm.match.created_at)} for {money(tm.match.cost_usd)}. Shares
        use each game's own analyzed reviews and the dates picked above.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead className="border-b border-line text-xs text-muted">
            <tr>
              <th className="py-2 pr-3 font-medium uppercase tracking-wide">Shared theme</th>
              {analyzed.map((t) => (
                <th key={t.id} className="py-2 pr-3 font-medium">
                  <span className="flex items-center gap-2">
                    {swatch(t)}
                    {t.name}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-line-soft">
            {tm.match.groups.map((g) => (
              <tr key={g.name} className="align-top">
                <td className="py-3 pr-3 font-medium">{g.name}</td>
                {analyzed.map((t) => (
                  <td key={t.id} className="py-3 pr-3">
                    <ThemeCell theme={t.themes.find((th) => th.key === g.themes[String(t.id)])} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h3 className="mt-5 mb-2 text-sm font-semibold">Only in one game</h3>
      <div className="grid gap-3 text-sm md:grid-cols-2">
        {analyzed.map((t) => {
          const own = t.themes.filter((th) => !matched.get(t.id)?.has(th.key));
          return (
            <div key={t.id}>
              <div className="mb-1 flex items-center gap-2 text-xs font-medium text-muted">
                {swatch(t)}
                {t.name}
              </div>
              {own.length ? (
                <p className="text-ink-2">{own.map((th) => `${th.name} (${pct(th.share)})`).join(", ")}</p>
              ) : (
                <p className="text-muted">Every theme has a match.</p>
              )}
            </div>
          );
        })}
      </div>
      {notAnalyzed}
    </Card>
  );
}

export function ComparePage() {
  const [params, setParams] = useSearchParams();
  const queryClient = useQueryClient();
  const palette = usePalette();
  const picks = readPicks(params);
  const rangeParam = params.get("range");
  const range = rangeParam && rangeParam in RANGE_LABELS ? (rangeParam as RangePreset) : undefined;

  const portfolio = useQuery({ queryKey: ["portfolio"], queryFn: api.portfolio });
  const ids = picks.map((p) => p.id);
  const comparison = useQuery({
    queryKey: ["compare", ids, range],
    queryFn: () => api.compare(ids, { from: range ? rangeStart(range) : undefined }),
    enabled: ids.length >= 2,
    placeholderData: keepPreviousData,
  });

  // Start with the two titles that have the most reviews.
  useEffect(() => {
    if (params.getAll("t").length || !portfolio.data) return;
    const top = [...portfolio.data.titles].sort((a, b) => b.reviews - a.reviews).slice(0, 2);
    if (top.length === 2) setParams(writePicks(params, top.map((t, i) => ({ id: t.id, slot: i }))), { replace: true });
  }, [portfolio.data, params, setParams]);

  const titles = portfolio.data?.titles ?? [];
  const colorOf = (id: number) => palette.series[picks.find((p) => p.id === id)?.slot ?? 0];
  const add = (id: number) => {
    const slot = [0, 1, 2, 3].find((s) => !picks.some((p) => p.slot === s)) ?? 0;
    setParams(writePicks(params, [...picks, { id, slot }]));
  };
  const remove = (id: number) => setParams(writePicks(params, picks.filter((p) => p.id !== id)));
  const setRange = (value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set("range", value);
    else next.delete("range");
    setParams(next, { replace: true });
  };

  const data = comparison.data;
  const ordered = data ? picks.map((p) => data.titles.find((t) => t.id === p.id)).filter((t): t is CompareTitle => !!t) : [];
  const series: SeriesDef[] = ordered.map((t) => ({ key: String(t.id), label: t.name, color: colorOf(t.id) }));

  return (
    <div>
      <h1 className="text-xl font-semibold">Compare titles</h1>
      <p className="mb-4 text-sm text-muted">Pick 2 to {MAX} titles. Each keeps its color while it stays picked.</p>

      <div className="mb-5 flex flex-wrap items-center gap-2" role="group" aria-label="Titles and dates">
        {picks.map((p) => {
          const t = titles.find((x) => x.id === p.id);
          return (
            <span key={p.id} className="flex items-center gap-2 rounded-md border border-line bg-surface py-1 pr-1 pl-2 text-sm">
              <span className="inline-block h-0.5 w-3.5 rounded" style={{ background: palette.series[p.slot] }} aria-hidden />
              {t?.name ?? `Title ${p.id}`}
              <button type="button" onClick={() => remove(p.id)} className="rounded px-1.5 text-muted hover:bg-soft hover:text-ink" aria-label={`Remove ${t?.name ?? "title"}`}>
                ×
              </button>
            </span>
          );
        })}
        {picks.length < MAX && (
          <select aria-label="Add a title" className={selectClass} value="" onChange={(e) => e.target.value && add(Number(e.target.value))}>
            <option value="">Add a title...</option>
            {titles
              .filter((t) => !picks.some((p) => p.id === t.id))
              .map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} ({t.reviews.toLocaleString()} reviews)
                </option>
              ))}
          </select>
        )}
        <select aria-label="Date range" className={`${selectClass} ml-auto`} value={range ?? ""} onChange={(e) => setRange(e.target.value)}>
          <option value="">All time</option>
          {Object.entries(RANGE_LABELS).map(([k, label]) => (
            <option key={k} value={k}>
              {label}
            </option>
          ))}
        </select>
      </div>

      {picks.length < 2 && <p className="text-sm text-muted">Add at least two titles to compare.</p>}
      {comparison.isError && <p className="text-sm text-negative-ink">Could not compare: {comparison.error.message}</p>}
      {data && picks.length >= 2 && (
        <div className={comparison.isPlaceholderData ? "opacity-60 transition-opacity" : "transition-opacity"}>
          <div className="mb-5 grid gap-3" style={{ gridTemplateColumns: `repeat(auto-fit, minmax(200px, 1fr))` }}>
            {ordered.map((t) => (
              <div key={t.id} className="rounded-lg border border-line bg-surface px-4 py-3">
                <div className="flex items-center gap-2 text-sm font-semibold">
                  <span className="inline-block h-0.5 w-3.5 rounded" style={{ background: colorOf(t.id) }} aria-hidden />
                  <Link to={`/titles/${t.id}`} className="hover:underline">
                    {t.name}
                  </Link>
                </div>
                <div className="mt-2 flex items-baseline gap-4">
                  <div>
                    <div className="text-2xl font-semibold">{t.reviews ? shareFloor(t.positive_share) : "n/a"}</div>
                    <div className="text-xs text-muted">recommended</div>
                  </div>
                  <div>
                    <div className="text-lg font-semibold">{t.reviews.toLocaleString()}</div>
                    <div className="text-xs text-muted">reviews</div>
                  </div>
                </div>
                <div className="mt-2 text-xs text-muted">
                  {t.steam?.review_score_desc && <div>Steam: {t.steam.review_score_desc}</div>}
                  <div>
                    Last {t.trend.days} days: {t.trend.last.reviews} {t.trend.last.reviews === 1 ? "review" : "reviews"}
                    {t.trend.last.reviews ? `, ${shareFloor(t.trend.last.positive_share)} recommended` : ""}
                  </div>
                </div>
              </div>
            ))}
          </div>
          <ChartOwner.Provider value="Compare">
            <Charts titles={ordered} series={series} />
          </ChartOwner.Provider>
          <div className="mt-5">
            <Themes data={data} colorOf={colorOf} onMatched={() => queryClient.invalidateQueries({ queryKey: ["compare"] })} />
          </div>
        </div>
      )}
    </div>
  );
}
