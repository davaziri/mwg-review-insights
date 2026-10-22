import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";

import { LanguageCheck } from "../components/LanguageCheck";
import { ReviewList } from "../components/ReviewList";
import { useTitle } from "../components/TitleShell";
import { inputClass, selectClass } from "../components/ui";

const SORTS = { newest: "Newest first", oldest: "Oldest first", helpful: "Most helpful", playtime: "Most playtime" };
const OVERALL = { positive: "Positive overall", mixed: "Mixed overall", negative: "Negative overall", none: "No overall view" };

/** Every review of the title, searchable. */
export function TitleReviewsPage() {
  const { title, appId, filters } = useTitle();
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const sort = params.get("sort") ?? "newest";
  const overall = params.get("overall") ?? "";
  const [draft, setDraft] = useState(q);

  const update = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete("page");
    setParams(next, { replace: true });
  };

  // Search as you type, after a short pause.
  useEffect(() => {
    if (draft === q) return;
    const timer = setTimeout(() => update("q", draft.trim()), 350);
    return () => clearTimeout(timer);
  }, [draft]);
  useEffect(() => setDraft(q), [q]);

  return (
    <div>
      <LanguageCheck titleId={title.id} appId={appId} />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative min-w-60 flex-1">
          <input
            type="search"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder='Search review text, for example jump or "boss fight"'
            aria-label="Search review text"
            className={inputClass}
          />
        </div>
        <select aria-label="Overall impression" className={selectClass} value={overall} onChange={(e) => update("overall", e.target.value)}>
          <option value="">Any overall impression</option>
          {Object.entries(OVERALL).map(([k, label]) => (
            <option key={k} value={k}>
              {label}
            </option>
          ))}
        </select>
        <select aria-label="Sort" className={selectClass} value={sort} onChange={(e) => update("sort", e.target.value === "newest" ? "" : e.target.value)}>
          {Object.entries(SORTS).map(([k, label]) => (
            <option key={k} value={k}>
              {label}
            </option>
          ))}
        </select>
      </div>
      <p className="mb-3 text-xs text-muted">
        Search finds reviews containing every word (in any language); put a phrase in quotes to match it exactly. Matches are shaded blue.
        Short words of one or two letters are matched anywhere in the text. Search looks at what the reviewer wrote, not the English
        translations.
      </p>
      <ReviewList
        titleId={title.id}
        filters={filters}
        query={{ q: q || undefined, sort: sort === "newest" ? undefined : sort, overall: overall || undefined }}
        empty={q ? `No reviews contain ${q}.` : "No reviews match these filters."}
      />
    </div>
  );
}
