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
        <Points title="Top strengths" tone="text-positive-ink" points={content.strengths} cited={cited} themeNames={themeNames} />
        <Points title="Top problems" tone="text-negative-ink" points={content.problems} cited={cited} themeNames={themeNames} />
      </div>
      <div className="mt-4">
        <h3 className="mb-1 text-sm font-semibold">Last 30 days</h3>
        <p className="text-sm text-ink-2">{content.last_30_days.text}</p>
        <Citations ids={content.last_30_days.review_ids} cited={cited} />
      </div>
      <p className="mt-4 text-xs text-muted">
        Written by {summary.data.model} on {dateTime(summary.data.created_at)} from {content.reviews_analyzed.toLocaleString()} analyzed
        reviews (codebook v{content.codebook_version}). It covers all reviews, so the filters above don't change it. Every cited review links to
        Steam.
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
      {points.length === 0 && <p className="text-sm text-muted">None stood out.</p>}
      <ol className="space-y-3">
        {points.map((p, i) => (
          <li key={i}>
            <div className="text-sm font-medium">
              {p.headline} <span className="text-xs font-normal text-muted">({themeNames[p.theme_key] ?? p.theme_key})</span>
            </div>
            <p className="text-sm text-ink-2">{p.detail}</p>
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
            className="rounded border border-line px-1.5 py-0.5 text-xs text-ink-2 hover:border-link hover:text-link"
          >
            Review {id}
          </a>
        ) : null;
      })}
    </div>
  );
}
