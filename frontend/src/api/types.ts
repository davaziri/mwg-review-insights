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
