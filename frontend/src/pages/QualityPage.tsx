import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router";

import { api } from "../api/client";
import type { AnalysisRun, Quality } from "../api/types";
import { STEP_LABELS } from "../components/analysis/EstimateDialog";
import { Badge, Card, inputClass } from "../components/ui";
import { dateTime, money, pct, tokens } from "../lib/format";

export function QualityPage() {
  const [params, setParams] = useSearchParams();
  const titles = useQuery({ queryKey: ["titles", false], queryFn: () => api.listTitles(false) });
  const titleId = Number(params.get("title")) || titles.data?.[0]?.id;
  const quality = useQuery({
    queryKey: ["quality", titleId],
    queryFn: () => api.quality(titleId!),
    enabled: !!titleId,
  });

  return (
    <div>
      <div className="mb-5 flex flex-wrap items-end gap-3">
        <div className="mr-auto">
          <h1 className="text-xl font-semibold">Analysis quality</h1>
          <p className="text-sm text-muted">How far to trust the tags, and what each analysis cost.</p>
        </div>
        <select
          className={`${inputClass} w-64`}
          value={titleId ?? ""}
          onChange={(e) => setParams({ title: e.target.value })}
          aria-label="Title"
        >
          {titles.data?.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </select>
      </div>
      {quality.isError && <p className="text-sm text-negative-ink">{quality.error.message}</p>}
      {quality.data && <QualityBody q={quality.data} />}
    </div>
  );
}

function QualityBody({ q }: { q: Quality }) {
  return (
    <>
      <Card title="Agreement check">
        {!q.qa ? (
          <p className="text-sm text-muted">No quality check yet. One runs with every analysis.</p>
        ) : (
          <>
            <p className="mb-3 text-sm text-ink-2">
              The analysis model ({q.qa.model}) re-tagged {q.qa.reviews_checked} random reviews without seeing the original tags. Agreement is
              how often both models made the same call on whether a theme is mentioned; kappa corrects that for chance (above 0.6 is good,
              above 0.8 is very good). Sentiment agreement covers reviews where both found the theme. Overall impression agreement is how often
              both models read the reviewer's view of the whole game the same way.
            </p>
            <div className="mb-3 flex flex-wrap gap-6 text-sm">
              <Big label="Theme agreement" value={pct(q.qa.overall.presence_agreement)} />
              <Big label="Average kappa" value={q.qa.overall.mean_kappa === null ? "n/a" : q.qa.overall.mean_kappa.toFixed(2)} />
              <Big label="Sentiment agreement" value={pct(q.qa.overall.sentiment_agreement)} />
              {q.qa.overall_impression && <Big label="Overall impression agreement" value={pct(q.qa.overall_impression.agreement)} />}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] text-left text-sm">
                <thead className="border-b border-line text-xs uppercase tracking-wide text-muted">
                  <tr>
                    <th className="py-1.5 pr-3">Theme</th>
                    <th className="py-1.5 pr-3 text-right">Both tagged</th>
                    <th className="py-1.5 pr-3 text-right">Only tagger</th>
                    <th className="py-1.5 pr-3 text-right">Only checker</th>
                    <th className="py-1.5 pr-3 text-right">Agreement</th>
                    <th className="py-1.5 pr-3 text-right">Kappa</th>
                    <th className="py-1.5 text-right">Sentiment</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line-soft tabular-nums">
                  {Object.entries(q.qa.themes).map(([key, t]) => (
                    <tr key={key}>
                      <td className="py-1.5 pr-3 font-medium">{t.name}</td>
                      <td className="py-1.5 pr-3 text-right">{t.both}</td>
                      <td className="py-1.5 pr-3 text-right">{t.primary_only}</td>
                      <td className="py-1.5 pr-3 text-right">{t.qa_only}</td>
                      <td className="py-1.5 pr-3 text-right">{pct(t.presence_agreement)}</td>
                      <td className={`py-1.5 pr-3 text-right ${t.kappa !== null && t.kappa < 0.6 ? "text-negative-ink" : ""}`}>
                        {t.kappa === null ? "n/a" : t.kappa.toFixed(2)}
                      </td>
                      <td className="py-1.5 text-right">{pct(t.sentiment_agreement)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Card>

      <div className="grid gap-5 md:grid-cols-2">
        <Card title="Quotes">
          <p className="mb-3 text-sm text-ink-2">
            Every quote is checked against the review's own text. Quotes that don't match exactly are dropped and never shown.
          </p>
          <div className="flex flex-wrap gap-6 text-sm">
            <Big label="Verified" value={q.quotes.verified.toLocaleString()} />
            <Big label="Dropped" value={q.quotes.dropped.toLocaleString()} />
            <Big label="Drop rate" value={pct(q.quotes.dropped / Math.max(1, q.quotes.verified + q.quotes.dropped), 1)} />
          </div>
        </Card>
        <Card title="Points no theme covers">
          <div className="flex flex-wrap gap-6 text-sm">
            <Big label="Reviews flagged" value={q.other.count.toLocaleString()} />
            <Big label="Share" value={pct(q.other.share, 1)} />
            <Big label="Limit" value={pct(q.other.threshold)} />
          </div>
          {q.codebook?.needs_review_reason && <p className="mt-3 text-sm text-mixed-ink">{q.codebook.needs_review_reason}</p>}
        </Card>
      </div>

      {q.other.notes.length > 0 && (
        <Card title="Recent 'other' notes">
          <ul className="divide-y divide-line-soft text-sm">
            {q.other.notes.map((n) => (
              <li key={n.recommendation_id} className="py-2">
                <div>{n.note}</div>
                <a href={n.url} target="_blank" rel="noreferrer" className="text-xs text-muted hover:text-link">
                  Review {n.recommendation_id}, {n.date}
                </a>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card title="Cost log">
        {q.runs.length === 0 ? (
          <p className="text-sm text-muted">No runs yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="border-b border-line text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th className="py-1.5 pr-3">Finished</th>
                  <th className="py-1.5 pr-3">Run</th>
                  <th className="py-1.5 pr-3">Status</th>
                  <th className="py-1.5 pr-3 text-right">Tokens in / out</th>
                  <th className="py-1.5 pr-3 text-right">Estimated</th>
                  <th className="py-1.5 text-right">Actual</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line-soft">
                {q.runs.map((r) => (
                  <CostRow key={r.id} run={r} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}

function CostRow({ run }: { run: AnalysisRun }) {
  const tone = run.status === "succeeded" ? "green" : run.status === "failed" ? "red" : "slate";
  return (
    <tr className="align-top">
      <td className="py-1.5 pr-3 text-ink-2">{dateTime(run.finished_at)}</td>
      <td className="py-1.5 pr-3">
        {run.kind === "discovery" ? "Find themes" : "Analyze reviews"}
        <div className="text-xs text-muted">
          {Object.entries(run.usage ?? {})
            .map(([step, u]) => `${STEP_LABELS[step] ?? step}: ${money(u.cost_usd)}`)
            .join(", ")}
        </div>
      </td>
      <td className="py-1.5 pr-3">
        <Badge tone={tone}>{run.status[0].toUpperCase() + run.status.slice(1)}</Badge>
      </td>
      <td className="py-1.5 pr-3 text-right tabular-nums">
        {tokens(run.input_tokens + run.cache_read_tokens + run.cache_write_tokens)} / {tokens(run.output_tokens)}
      </td>
      <td className="py-1.5 pr-3 text-right tabular-nums">{money(run.est_cost_usd)}</td>
      <td className="py-1.5 text-right font-medium tabular-nums">{money(run.actual_cost_usd)}</td>
    </tr>
  );
}

function Big({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-lg font-semibold tabular-nums">{value}</div>
      <div className="text-xs text-muted">{label}</div>
    </div>
  );
}
