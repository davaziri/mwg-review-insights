import { useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { ReviewBrief, SummaryPoint } from "../../api/types";
import { dateTime } from "../../lib/format";
import { Card } from "../ui";

export function SummaryPanel({ titleId, appId, themeNames }: { titleId: number; appId: number; themeNames: Record<string, string> }) {
  const summary = useQuery({ queryKey: ["summary", titleId, appId], queryFn: () => api.summary(titleId, appId) });
  if (!summary.data) return null;
  const { content, cited_reviews: cited } = summary.data;

  return (
    <Card title="Executive summary">
      <div className="grid gap-4 md:grid-cols-2">
        <Points title="Top strengths" tone="text-positive" points={content.strengths} cited={cited} themeNames={themeNames} />
        <Points title="Top problems" tone="text-negative" points={content.problems} cited={cited} themeNames={themeNames} />
      </div>
      <div className="mt-4">
        <h3 className="mb-1 text-sm font-semibold">Last 30 days</h3>
        <p className="text-sm text-slate-700">{content.last_30_days.text}</p>
        <Citations ids={content.last_30_days.review_ids} cited={cited} />
      </div>
      <p className="mt-4 text-xs text-slate-500">
        Written by {summary.data.model} on {dateTime(summary.data.created_at)} from {content.reviews_analyzed.toLocaleString()} analyzed
        reviews (codebook v{content.codebook_version}). Every cited review links to Steam.
      </p>
    </Card>
  );
}

function Points({
  title,
  tone,
  points,
  cited,
  themeNames,
}: {
  title: string;
  tone: string;
  points: SummaryPoint[];
  cited: Record<string, ReviewBrief>;
  themeNames: Record<string, string>;
}) {
  return (
    <div>
      <h3 className={`mb-2 text-sm font-semibold ${tone}`}>{title}</h3>
      {points.length === 0 && <p className="text-sm text-slate-500">None stood out.</p>}
      <ol className="space-y-3">
        {points.map((p, i) => (
          <li key={i}>
            <div className="text-sm font-medium">
              {p.headline} <span className="text-xs font-normal text-slate-500">({themeNames[p.theme_key] ?? p.theme_key})</span>
            </div>
            <p className="text-sm text-slate-700">{p.detail}</p>
            <Citations ids={p.review_ids} cited={cited} />
          </li>
        ))}
      </ol>
    </div>
  );
}

function Citations({ ids, cited }: { ids: string[]; cited: Record<string, ReviewBrief> }) {
  if (!ids.length) return null;
  return (
    <div className="mt-1 flex flex-wrap gap-1.5">
      {ids.map((id) => {
        const r = cited[id];
        return r ? (
          <a
            key={id}
            href={r.url}
            target="_blank"
            rel="noreferrer"
            title={r.excerpt}
            className="rounded border border-slate-200 px-1.5 py-0.5 text-xs text-slate-600 hover:border-brand hover:text-brand"
          >
            Review {id}
          </a>
        ) : null;
      })}
    </div>
  );
}
