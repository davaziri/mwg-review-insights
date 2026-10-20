export type TitleStatus = "released" | "early_access" | "coming_soon" | "unreleased";
export type SyncMode = "full" | "incremental";

export interface Snapshot {
  snapshot_date: string;
  total_reviews: number | null;
  total_positive: number | null;
  total_negative: number | null;
  review_score: number | null;
  review_score_desc: string | null;
}

export interface SyncRun {
  id: number;
  title_id: number;
  app_id: number;
  mode: SyncMode;
  trigger: string;
  requested_by: string | null;
  status: "queued" | "running" | "succeeded" | "failed";
  resumed_from_id: number | null;
  pages_fetched: number;
  reviews_seen: number;
  new_count: number;
  updated_count: number;
  deleted_count: number;
  restored_count: number;
  steam_total: number | null;
  warning: string | null;
  error: string | null;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface SyncRunWithTitle extends SyncRun {
  title_name: string;
}

export interface AppStats {
  app_id: number;
  is_demo: boolean;
  stored_reviews: number;
  stored_positive: number;
  latest_snapshot: Snapshot | null;
  last_run: SyncRun | null;
  active_run: SyncRun | null;
}

export interface Title {
  id: number;
  steam_app_id: number;
  demo_app_id: number | null;
  name: string;
  status: TitleStatus;
  notes: string | null;
  archived_at: string | null;
  header_image_url: string | null;
  release_date: string | null;
  release_date_text: string | null;
  coming_soon: boolean | null;
  developers: string[] | null;
  publishers: string[] | null;
  appdetails_fetched_at: string | null;
  created_at: string;
  last_synced_at: string | null;
  apps: AppStats[];
}

export interface TitleCreate {
  steam_app_id: number;
  status: TitleStatus;
  demo_app_id?: number | null;
  name?: string | null;
  notes?: string | null;
}

export type TitleUpdate = Partial<Pick<Title, "name" | "status" | "demo_app_id" | "notes">>;

export const STATUS_LABELS: Record<TitleStatus, string> = {
  released: "Released",
  early_access: "Early Access",
  coming_soon: "Coming soon",
  unreleased: "Unreleased",
};

// Analysis

export interface Theme {
  id: number;
  key: string;
  name: string;
  definition: string;
  include_notes: string;
  exclude_notes: string;
  example_review_ids: string[];
  derived_from: { key?: string; op: string }[];
  sort_order: number;
}

export interface ReviewBrief {
  recommendation_id: string;
  excerpt: string;
  voted_up: boolean | null;
  language: string | null;
  date: string | null;
  url: string;
}

export interface Codebook {
  id: number;
  title_id: number;
  version: number;
  status: "draft" | "approved" | "superseded";
  parent_id: number | null;
  created_by: string;
  note: string | null;
  needs_review_reason: string | null;
  created_at: string;
  approved_at: string | null;
  theme_count: number;
  themes?: Theme[];
  examples?: Record<string, ReviewBrief>;
}

export interface EstimateStep {
  step: "discovery" | "tagging" | "qa" | "summary";
  model: string;
  requests: number;
  input_tokens: number;
  output_tokens: number;
  batch: boolean;
  cost_usd: number;
  reviews?: number;
}

export interface StepUsage {
  model: string;
  requests: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  cost_usd: number;
}

export interface QAThemeResult {
  name: string;
  reviews: number;
  both: number;
  primary_only: number;
  qa_only: number;
  neither: number;
  presence_agreement: number | null;
  kappa: number | null;
  sentiment_agreement: number | null;
}

export interface QAResults {
  model: string;
  reviews_checked: number;
  themes: Record<string, QAThemeResult>;
  overall: {
    cells: number;
    presence_agreement: number | null;
    mean_kappa: number | null;
    sentiment_agreement: number | null;
  };
  /** Missing on runs made before the overall impression existed. */
  overall_impression?: { reviews: number; agreement: number | null; differences: Record<string, number> };
}

export interface AnalysisRun {
  id: number;
  title_id: number;
  app_id: number;
  codebook_id: number | null;
  kind: "discovery" | "analysis";
  status: "estimated" | "queued" | "running" | "succeeded" | "failed" | "canceled";
  step: string | null;
  mode: "direct" | "batch";
  estimate: { steps: EstimateStep[]; notes: string[]; prompt_version: string } | null;
  est_input_tokens: number;
  est_output_tokens: number;
  est_cost_usd: number;
  usage: Record<string, StepUsage> | null;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  actual_cost_usd: number;
  reviews_in_scope: number;
  reviews_tagged: number;
  reviews_failed: number;
  quotes_checked: number;
  quotes_dropped: number;
  batches: Record<string, { id: string; submitted_at: string; requests: number; ingested: boolean }> | null;
  details: { qa?: QAResults; other_rate?: number; prompt_version?: string } | null;
  warning: string | null;
  error: string | null;
  created_at: string;
  confirmed_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  title_name?: string;
}

export interface AnalysisOverview {
  title: { id: number; name: string; steam_app_id: number; demo_app_id: number | null };
  app_id: number;
  reviews: { total: number; with_content: number; no_content: number; not_prepared: number; pending: number | null };
  min_reviews_for_discovery: number;
  approved_codebook: Codebook | null;
  latest_codebook: Codebook | null;
  active_run: AnalysisRun | null;
  runs: AnalysisRun[];
}

export interface ThemeCell {
  mentions: number;
  share: number;
  positive: number;
  negative: number;
  mixed: number;
  net: number | null;
}

export interface ThemeStat extends ThemeCell {
  id: number;
  key: string;
  name: string;
  definition: string;
  monthly: (ThemeCell & { month: string })[];
}

export type OverallSentiment = "positive" | "mixed" | "negative" | "none";

export type OverallSplit = Record<OverallSentiment, { count: number; share: number }>;

export interface ThemeStats {
  counts: { reviews: number; with_content: number; no_content: number; analyzed: number; pending: number; positive_votes: number };
  themes: ThemeStat[];
  developer_response: { responded: number; rate: number; median_hours: number | null };
  other: { count: number; share: number };
  overall: OverallSplit;
  codebook: { id: number; version: number } | null;
}

export interface Mention {
  theme_key: string;
  theme_name: string;
  sentiment: "positive" | "negative" | "mixed";
  quote_start: number | null;
  quote_end: number | null;
  quote_status: "ok" | "dropped" | "none";
}

export interface TaggedReview {
  id: number;
  recommendation_id: string;
  app_id: number;
  text: string;
  voted_up: boolean;
  language: string;
  date: string | null;
  playtime_at_review_hours: number | null;
  playtime_band: string;
  early_access: boolean;
  steam_deck: boolean;
  votes_up: number | null;
  developer_response: string | null;
  url: string;
  gist_en: string | null;
  other_flag: boolean;
  other_note: string | null;
  model: string;
  overall: {
    sentiment: OverallSentiment;
    quote_start: number | null;
    quote_end: number | null;
    quote_status: "ok" | "dropped" | "none";
  };
  mentions: Mention[];
}

export interface SummaryPoint {
  theme_key: string;
  headline: string;
  detail: string;
  review_ids: string[];
}

export interface SummaryOut {
  id: number;
  model: string;
  created_at: string;
  content: {
    strengths: SummaryPoint[];
    problems: SummaryPoint[];
    last_30_days: { text: string; review_ids: string[] };
    reviews_analyzed: number;
    codebook_version: number;
  };
  cited_reviews: Record<string, ReviewBrief>;
}

export interface Quality {
  codebook: Codebook | null;
  analyzed_reviews: number;
  qa: QAResults | null;
  qa_run_id: number | null;
  quotes: { verified: number; dropped: number; no_quote: number };
  other: { count: number; share: number; threshold: number; notes: (ReviewBrief & { note: string | null })[] };
  runs: AnalysisRun[];
}

export interface ThemeDraft {
  key?: string | null;
  name: string;
  definition: string;
  include_notes: string;
  exclude_notes: string;
  example_review_ids: string[];
  derived_from: { key?: string; op: string }[];
}
