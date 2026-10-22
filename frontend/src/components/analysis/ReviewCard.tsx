import { useState } from "react";

import type { Mention, TaggedReview } from "../../api/types";
import { languageName } from "../../lib/languages";
import { Badge, OVERALL_STYLE, OVERALL_WORD, SENTIMENT_STYLE } from "../ui";

type Span = { start: number; end: number };
type Segment = { text: string; marks: Mention[]; overall: boolean; match: boolean };

/** Split the review text into runs, each covered by the same set of quotes and search matches. */
function segments(text: string, mentions: Mention[], overall: Span | null, matches: Span[]): Segment[] {
  const spans = mentions.filter((m) => m.quote_status === "ok" && m.quote_start !== null && m.quote_end !== null);
  const cuts = new Set<number>([0, text.length]);
  spans.forEach((m) => {
    cuts.add(m.quote_start!);
    cuts.add(m.quote_end!);
  });
  for (const s of [...(overall ? [overall] : []), ...matches]) {
    cuts.add(s.start);
    cuts.add(s.end);
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
      match: matches.some((m) => m.start <= a && m.end >= b),
    });
  }
  return out;
}

const SENTIMENT_WORD = { positive: "positive", negative: "negative", mixed: "mixed" } as const;

const LONG_REVIEW = 1200;

/** Where the language label comes from, for its tooltip. */
function languageNote(review: TaggedReview): string {
  const steam = languageName(review.steam_language);
  if (!review.language_checked) {
    return `The reviewer's Steam language setting (${steam}). The text hasn't been checked yet, so the review may be written in another language.`;
  }
  if (review.steam_language && review.steam_language !== review.language) {
    return `Written in ${languageName(review.language)}. The reviewer's Steam language setting is ${steam}.`;
  }
  return "The language the review is written in.";
}

export function ReviewCard({ review, focusTheme }: { review: TaggedReview; focusTheme?: string }) {
  const o = review.overall;
  const overallSpan = o && o.quote_status === "ok" && o.quote_start !== null && o.quote_end !== null ? { start: o.quote_start, end: o.quote_end } : null;
  const matches = (review.matches ?? []).map(([start, end]) => ({ start, end }));
  const parts = segments(review.text, review.mentions, overallSpan, matches);
  const isLong = (text: string) => text.length > LONG_REVIEW || text.split("\n").length > 16;
  const long = isLong(review.text) || (review.text_en !== null && isLong(review.text_en));
  const [expanded, setExpanded] = useState(false);
  const [showReply, setShowReply] = useState(false);
  // In a theme's drill-down, that theme's chip comes first.
  const mentions = focusTheme ? [...review.mentions].sort((a, b) => Number(b.theme_key === focusTheme) - Number(a.theme_key === focusTheme)) : review.mentions;

  return (
    <article className="rounded-lg border border-line bg-surface p-4">
      <header className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
        <Badge tone={review.voted_up ? "green" : "red"}>{review.voted_up ? "Recommended" : "Not recommended"}</Badge>
        {review.date && <span>{review.date}</span>}
        {review.playtime_at_review_hours !== null && <span>{review.playtime_at_review_hours}h at review</span>}
        <span title={languageNote(review)}>{languageName(review.language)}</span>
        {review.early_access && <span>Early Access</span>}
        {review.steam_deck && <span>Steam Deck</span>}
        {review.votes_up ? <span>{review.votes_up} found it helpful</span> : null}
        <a className="ml-auto font-medium text-link hover:underline" href={review.url} target="_blank" rel="noreferrer">
          Open on Steam
        </a>
      </header>

      <p className={`whitespace-pre-wrap text-sm leading-relaxed text-ink ${long && !expanded ? "max-h-64 overflow-hidden" : ""}`}>
        {parts.map((p, i) => {
          if (!p.marks.length && !p.overall && !p.match) return <span key={i}>{p.text}</span>;
          // A theme quote shades its sentiment; a search match outside a quote shades blue; the
          // overall impression quote gets an outline. Matches inside a quote are just bold.
          const background = p.marks.length
            ? `underline decoration-2 underline-offset-2 ${SENTIMENT_STYLE[p.marks[0].sentiment].mark} text-inherit`
            : p.match
              ? "bg-info-soft text-info-ink"
              : "bg-transparent text-inherit";
          const overallClass = p.overall && o ? `font-semibold ring-1 ${OVERALL_STYLE[o.sentiment].outline}` : "";
          const label = [
            ...(p.overall && o ? [`Overall impression (${OVERALL_WORD[o.sentiment]})`] : []),
            ...p.marks.map((m) => `${m.theme_name} (${SENTIMENT_WORD[m.sentiment]})`),
            ...(p.match ? ["Matches your search"] : []),
          ].join(", ");
          return (
            <mark key={i} className={`box-decoration-clone rounded-sm ${background} ${overallClass} ${p.match ? "font-semibold" : ""}`} title={label}>
              {p.text}
            </mark>
          );
        })}
      </p>
      {review.text_en && (
        <div className="mt-3 border-l-2 border-line-strong pl-3">
          <div className="mb-0.5 text-xs font-medium text-muted">English translation (machine-written)</div>
          <p className={`whitespace-pre-wrap text-sm leading-relaxed text-ink-2 ${long && !expanded ? "max-h-40 overflow-hidden" : ""}`}>
            {review.text_en}
          </p>
        </div>
      )}
      {long && (
        <button type="button" className="mt-1 text-xs font-medium text-link hover:underline" onClick={() => setExpanded(!expanded)}>
          {expanded ? "Show less" : "Show full review"}
        </button>
      )}

      {review.gist_en && !review.text_en && (
        <p className="mt-2 rounded bg-subtle px-3 py-2 text-xs text-ink-2">
          <span className="font-medium">English gist (machine-written, not a quote):</span> {review.gist_en}
        </p>
      )}

      {review.developer_response && (
        <div className="mt-2 text-xs">
          <button type="button" className="font-medium text-link hover:underline" onClick={() => setShowReply(!showReply)} aria-expanded={showReply}>
            {showReply ? "Hide developer reply" : "Developer replied"}
          </button>
          {showReply && <p className="mt-1 whitespace-pre-wrap rounded border-l-2 border-line-strong bg-subtle px-3 py-2 text-ink-2">{review.developer_response}</p>}
        </div>
      )}

      <footer className="mt-3 flex flex-wrap items-center gap-1.5">
        {o ? (
          <>
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
            <span className="mx-1 h-4 w-px bg-line" aria-hidden />
            {mentions.length === 0 && <span className="text-xs text-muted">No themes tagged</span>}
          </>
        ) : (
          <span className="text-xs text-muted">{review.content_status === "no_content" ? "Too short to analyze" : "Not analyzed yet"}</span>
        )}
        {mentions.map((m) => (
          <span
            key={m.theme_key}
            className={`rounded border px-1.5 py-0.5 text-xs ${SENTIMENT_STYLE[m.sentiment].chip} ${m.theme_key === focusTheme ? "font-semibold" : ""}`}
            title={m.quote_status === "dropped" ? "The model's quote did not match the review text, so it is not shown." : undefined}
          >
            {m.theme_name}: {SENTIMENT_WORD[m.sentiment]}
            {m.quote_status !== "ok" && <span className="opacity-70"> (no quote)</span>}
          </span>
        ))}
        {review.other_flag && (
          <span className="rounded border border-line-strong bg-subtle px-1.5 py-0.5 text-xs text-ink-2" title={review.other_note ?? ""}>
            Other: {review.other_note}
          </span>
        )}
      </footer>
    </article>
  );
}
