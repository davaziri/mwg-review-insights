// Page filters for a title. They live in the URL, so a filtered view can be bookmarked or shared
// and survives moving between a title's tabs. Phase 4 exports read the same parameters.

export type RangePreset = "30d" | "90d" | "12m";

export const RANGE_LABELS: Record<RangePreset, string> = { "30d": "Last 30 days", "90d": "Last 90 days", "12m": "Last 12 months" };

export interface PageFilters {
  app?: number;
  /** A rolling range, worked out from today each time; otherwise from/to are exact dates. */
  range?: RangePreset;
  from?: string;
  to?: string;
  vote?: "positive" | "negative";
  playtime: string[];
  language: string[];
  earlyAccess?: boolean;
  steamDeck?: boolean;
  devResponse?: boolean;
}

/** URL parameter names. Page-specific ones (q, sort, page, sentiment) are kept separately. */
export const FILTER_PARAMS = ["app", "range", "from", "to", "vote", "playtime", "lang", "ea", "deck", "dev"] as const;

const bool = (v: string | null) => (v === "true" ? true : v === "false" ? false : undefined);

export function readFilters(params: URLSearchParams): PageFilters {
  const app = params.get("app");
  const vote = params.get("vote");
  const range = params.get("range");
  const preset = range && range in RANGE_LABELS ? (range as RangePreset) : undefined;
  return {
    app: app ? Number(app) : undefined,
    range: preset,
    from: preset ? undefined : params.get("from") || undefined,
    to: preset ? undefined : params.get("to") || undefined,
    vote: vote === "positive" || vote === "negative" ? vote : undefined,
    playtime: params.getAll("playtime"),
    language: params.getAll("lang"),
    earlyAccess: bool(params.get("ea")),
    steamDeck: bool(params.get("deck")),
    devResponse: bool(params.get("dev")),
  };
}

/** A copy of params with the filters replaced and the page reset; other parameters are kept. */
export function writeFilters(params: URLSearchParams, f: PageFilters): URLSearchParams {
  const next = new URLSearchParams(params);
  for (const key of FILTER_PARAMS) next.delete(key);
  next.delete("page");
  if (f.app !== undefined) next.set("app", String(f.app));
  if (f.range) next.set("range", f.range);
  else {
    if (f.from) next.set("from", f.from);
    if (f.to) next.set("to", f.to);
  }
  if (f.vote) next.set("vote", f.vote);
  f.playtime.forEach((b) => next.append("playtime", b));
  f.language.forEach((l) => next.append("lang", l));
  if (f.earlyAccess !== undefined) next.set("ea", String(f.earlyAccess));
  if (f.steamDeck !== undefined) next.set("deck", String(f.steamDeck));
  if (f.devResponse !== undefined) next.set("dev", String(f.devResponse));
  return next;
}

/** Only the filter parameters, for links between a title's pages. */
export function filterSearch(params: URLSearchParams): string {
  const keep = new URLSearchParams();
  for (const key of FILTER_PARAMS) params.getAll(key).forEach((v) => keep.append(key, v));
  const s = keep.toString();
  return s ? `?${s}` : "";
}

/** How many filters narrow the data (the app choice is not counted). */
export function activeFilterCount(f: PageFilters): number {
  return (
    Number(Boolean(f.range || f.from || f.to)) +
    Number(f.vote !== undefined) +
    Number(f.playtime.length > 0) +
    Number(f.language.length > 0) +
    Number(f.earlyAccess !== undefined) +
    Number(f.steamDeck !== undefined) +
    Number(f.devResponse !== undefined)
  );
}

export type QueryValue = string | number | boolean | undefined | null | (string | number)[];

const isoDate = (d: Date) => d.toISOString().slice(0, 10);

/** The first day a rolling range covers, counting today. */
export function rangeStart(range: RangePreset, today = new Date()): string {
  const d = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate()));
  if (range === "12m") d.setUTCFullYear(d.getUTCFullYear() - 1);
  else d.setUTCDate(d.getUTCDate() - (range === "30d" ? 30 : 90));
  return isoDate(d);
}

/** The API's names for the filters. */
export function filterQuery(f: PageFilters): Record<string, QueryValue> {
  return {
    app_id: f.app,
    date_from: f.range ? rangeStart(f.range) : f.from,
    date_to: f.range ? undefined : f.to,
    vote: f.vote,
    playtime: f.playtime,
    language: f.language,
    early_access: f.earlyAccess,
    steam_deck: f.steamDeck,
    has_dev_response: f.devResponse,
  };
}

export function qs(params: Record<string, QueryValue>): string {
  const out = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((item) => out.append(k, String(item)));
    else out.set(k, String(v));
  }
  const s = out.toString();
  return s ? `?${s}` : "";
}
