import type {
  AnalysisOverview,
  AnalysisRun,
  Codebook,
  Quality,
  SummaryOut,
  SyncMode,
  SyncRun,
  SyncRunWithTitle,
  TaggedReview,
  ThemeDraft,
  ThemeStats,
  Title,
  TitleCreate,
  TitleUpdate,
} from "./types";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!resp.ok) {
    let message = `Request failed (${resp.status})`;
    try {
      const body = await resp.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch {
      // keep the generic message
    }
    throw new ApiError(resp.status, message);
  }
  return resp.status === 204 ? (undefined as T) : resp.json();
}

const json = (body: unknown) => JSON.stringify(body);

export const api = {
  listTitles: (includeArchived: boolean) =>
    request<Title[]>(`/api/titles?include_archived=${includeArchived}`),
  createTitle: (body: TitleCreate) => request<Title>("/api/titles", { method: "POST", body: json(body) }),
  updateTitle: (id: number, body: TitleUpdate) =>
    request<Title>(`/api/titles/${id}`, { method: "PATCH", body: json(body) }),
  archiveTitle: (id: number) => request<Title>(`/api/titles/${id}/archive`, { method: "POST" }),
  unarchiveTitle: (id: number) => request<Title>(`/api/titles/${id}/unarchive`, { method: "POST" }),
  deleteTitle: (id: number) => request<void>(`/api/titles/${id}`, { method: "DELETE" }),
  syncTitle: (id: number, mode?: SyncMode) =>
    request<SyncRun[]>(`/api/titles/${id}/sync`, { method: "POST", body: json({ mode: mode ?? null }) }),
  syncAll: () => request<SyncRun[]>("/api/sync/all", { method: "POST" }),
  syncRuns: (limit = 100) => request<SyncRunWithTitle[]>(`/api/sync-runs?limit=${limit}`),

  analysis: (titleId: number, appId?: number) =>
    request<AnalysisOverview>(`/api/titles/${titleId}/analysis${qs({ app_id: appId })}`),
  codebook: (id: number) => request<Codebook>(`/api/codebooks/${id}`),
  saveCodebook: (titleId: number, body: { parent_id: number | null; note: string; themes: ThemeDraft[]; approve: boolean }) =>
    request<Codebook>(`/api/titles/${titleId}/codebooks`, { method: "POST", body: json(body) }),
  approveCodebook: (id: number) => request<Codebook>(`/api/codebooks/${id}/approve`, { method: "POST" }),
  estimate: (titleId: number, kind: "discovery" | "analysis", appId?: number) =>
    request<AnalysisRun>(`/api/titles/${titleId}/analysis/estimate`, { method: "POST", body: json({ kind, app_id: appId ?? null }) }),
  confirmRun: (id: number) => request<AnalysisRun>(`/api/analysis-runs/${id}/confirm`, { method: "POST" }),
  cancelRun: (id: number) => request<AnalysisRun>(`/api/analysis-runs/${id}/cancel`, { method: "POST" }),
  stats: (titleId: number, appId?: number) => request<ThemeStats>(`/api/titles/${titleId}/themes/stats${qs({ app_id: appId })}`),
  taggedReviews: (
    titleId: number,
    params: { app_id?: number; random?: number; theme?: string; sentiment?: string; overall?: string; page?: number },
  ) =>
    request<{ total: number; reviews: TaggedReview[] }>(`/api/titles/${titleId}/reviews/tagged${qs(params)}`),
  summary: (titleId: number, appId?: number) => request<SummaryOut | null>(`/api/titles/${titleId}/summary${qs({ app_id: appId })}`),
  quality: (titleId: number, appId?: number) => request<Quality>(`/api/titles/${titleId}/quality${qs({ app_id: appId })}`),
};

function qs(params: Record<string, string | number | undefined | null>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "");
  return entries.length ? `?${new URLSearchParams(entries.map(([k, v]) => [k, String(v)])).toString()}` : "";
}
