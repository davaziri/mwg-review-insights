import type { SyncMode, SyncRun, SyncRunWithTitle, Title, TitleCreate, TitleUpdate } from "./types";

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
};
