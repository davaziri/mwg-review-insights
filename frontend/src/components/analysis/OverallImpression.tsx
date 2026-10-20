import type { OverallSentiment, ThemeStats } from "../../api/types";
import { pct } from "../../lib/format";
import { Card, OVERALL_WORD } from "../ui";

const ORDER: OverallSentiment[] = ["positive", "mixed", "negative", "none"];
const BAR: Record<OverallSentiment, string> = { positive: "bg-positive", mixed: "bg-mixed", negative: "bg-negative", none: "bg-neutral" };

export function OverallImpression({ stats }: { stats: ThemeStats }) {
  const split = stats.overall;
  const counted = ORDER.reduce((n, k) => n + split[k].count, 0);
  if (!counted) return null;
  return (
    <Card title="Overall impression">
      <p className="mb-3 text-xs text-muted">
        What each of the {stats.counts.analyzed.toLocaleString()} analyzed reviews says about the game as a whole, such as "great game" or
        "waste of money". It is counted on its own, so it never adds to a theme. "No overall view" means the review only talks about
        specific things.
      </p>
      <div className="flex h-3 w-full gap-[2px] overflow-hidden rounded" aria-hidden>
        {ORDER.filter((k) => split[k].count > 0).map((k) => (
          <div key={k} className={BAR[k]} style={{ width: `${(100 * split[k].count) / counted}%` }} />
        ))}
      </div>
      <dl className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-sm">
        {ORDER.map((k) => (
          <div key={k} className="flex items-center gap-1.5">
            <span className={`inline-block h-2.5 w-2.5 rounded-sm ${BAR[k]}`} aria-hidden />
            <dt className="text-ink-2">{OVERALL_WORD[k][0].toUpperCase() + OVERALL_WORD[k].slice(1)}</dt>
            <dd className="font-medium tabular-nums">
              {pct(split[k].share)} <span className="font-normal text-muted">({split[k].count.toLocaleString()})</span>
            </dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}
