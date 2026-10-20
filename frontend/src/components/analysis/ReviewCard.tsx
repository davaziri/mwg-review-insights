import { useState } from "react";

import type { Mention, TaggedReview } from "../../api/types";
import { Badge, OVERALL_STYLE, OVERALL_WORD, SENTIMENT_STYLE } from "../ui";

type Span = { start: number; end: number };
type Segment = { text: string; marks: Mention[]; overall: boolean };

/** Split the review text into runs, each covered by the same set of verified quotes. */
function segments(text: string, mentions: Mention[], overall: Span | null): Segment[] {
  const spans = mentions.filter((m) => m.quote_status === "ok" && m.quote_start !== null && m.quote_end !== null);
  const cuts = new Set<number>([0, text.length]);
  spans.forEach((m) => {
    cuts.add(m.quote_start!);
    cuts.add(m.quote_end!);
  });
  if (overall) {
    cuts.add(overall.start);
    cuts.add(overall.end);
  }
  const points = [...cuts].sort((a, b) => a - b);
  const out: Segment[] = [];
  for (let i = 0; i < points.length - 1; i++) {
    const [a, b] = [points[i], points[i + 1]];
    if (a === b) continue;
    out.push({
      text: text.slice(a, b),
      marks: spans.filter((m) => m.quote_start! <= a && m.quote_end! >= b),
      overall: overall !== null && overall.start <= a && overall.end >= b,
    });
  }
  return out;
}

const SENTIMENT_WORD = { positive: "positive", negative: "negative", mixed: "mixed" } as const;

const LONG_REVIEW = 1200;

export function ReviewCard({ review }: { review: TaggedReview }) {
  const o = review.overall;
  const overallSpan = o.quote_status === "ok" && o.quote_start !== null && o.quote_end !== null ? { start: o.quote_start, end: o.quote_end } : null;
  const parts = segments(review.text, review.mentions, overallSpan);
  const long = review.text.length > LONG_REVIEW || review.text.split("\n").length > 16;
  const [expanded, setExpanded] = useState(false);
  return (
    <article className="rounded-lg border border-slate-200 bg-white p-4">
      <header className="mb-2 flex flex-wrap items-center gap-2 text-xs text-slate-500">
        <Badge tone={review.voted_up ? "green" : "red"}>{review.voted_up ? "Recommended" : "Not recommended"}</Badge>
        {review.date && <span>{review.date}</span>}
        {review.playtime_at_review_hours !== null && <span>{review.playtime_at_review_hours}h at review</span>}
        <span>{review.language}</span>
        {review.early_access && <span>Early Access</span>}
        {review.steam_deck && <span>Steam Deck</span>}
        <a className="ml-auto font-medium text-brand hover:underline" href={review.url} target="_blank" rel="noreferrer">
          Open on Steam
        </a>
      </header>

      <p className={`whitespace-pre-wrap text-sm leading-relaxed text-slate-800 ${long && !expanded ? "max-h-64 overflow-hidden" : ""}`}>
        {parts.map((p, i) => {
          if (!p.marks.length && !p.overall) return <span key={i}>{p.text}</span>;
          const themeClass = p.marks.length ? `underline decoration-2 underline-offset-2 ${SENTIMENT_STYLE[p.marks[0].sentiment].mark}` : "";
          const overallClass = p.overall ? `font-semibold ring-1 box-decoration-clone ${OVERALL_STYLE[o.sentiment].outline}` : "";
          const label = [
            ...(p.overall ? [`Overall impression (${OVERALL_WORD[o.sentiment]})`] : []),
            ...p.marks.map((m) => `${m.theme_name} (${SENTIMENT_WORD[m.sentiment]})`),
          ].join(", ");
          return (
            <mark key={i} className={`rounded-sm bg-transparent px-0.5 text-inherit ${themeClass} ${overallClass}`} title={label}>
              {p.text}
            </mark>
          );
        })}
      </p>
      {long && (
        <button type="button" className="mt-1 text-xs font-medium text-brand hover:underline" onClick={() => setExpanded(!expanded)}>
          {expanded ? "Show less" : "Show full review"}
        </button>
      )}

      {review.gist_en && (
        <p className="mt-2 rounded bg-slate-50 px-3 py-2 text-xs text-slate-600">
          <span className="font-medium">English gist (machine-written, not a quote):</span> {review.gist_en}
        </p>
      )}

      <footer className="mt-3 flex flex-wrap items-center gap-1.5">
        <span
          className={`rounded border px-1.5 py-0.5 text-xs font-medium ${OVERALL_STYLE[o.sentiment].chip}`}
          title={
            o.quote_status === "dropped"
              ? "The model's quote did not match the review text, so it is not shown."
              : "The reviewer's view of the game as a whole. Counted separately from the themes."
          }
        >
          Overall: {OVERALL_WORD[o.sentiment]}
          {o.sentiment !== "none" && o.quote_status !== "ok" && <span className="opacity-80"> (no quote)</span>}
        </span>
        <span className="mx-1 h-4 w-px bg-slate-200" aria-hidden />
        {review.mentions.length === 0 && <span className="text-xs text-slate-500">No themes tagged</span>}
        {review.mentions.map((m) => (
          <span
            key={m.theme_key}
            className={`rounded border px-1.5 py-0.5 text-xs ${SENTIMENT_STYLE[m.sentiment].chip}`}
            title={m.quote_status === "dropped" ? "The model's quote did not match the review text, so it is not shown." : undefined}
          >
            {m.theme_name}: {SENTIMENT_WORD[m.sentiment]}
            {m.quote_status !== "ok" && <span className="opacity-70"> (no quote)</span>}
          </span>
        ))}
        {review.other_flag && (
          <span className="rounded border border-slate-300 bg-slate-50 px-1.5 py-0.5 text-xs text-slate-700" title={review.other_note ?? ""}>
            Other: {review.other_note}
          </span>
        )}
      </footer>
    </article>
  );
}
