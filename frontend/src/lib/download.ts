import { ApiError } from "../api/client";

/** The file name the server picked, from its Content-Disposition header. */
function fileName(header: string | null, fallback: string): string {
  if (!header) return fallback;
  const star = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (star) return decodeURIComponent(star[1]);
  const plain = /filename="([^"]+)"/i.exec(header);
  return plain ? plain[1] : fallback;
}

export function saveBlob(blob: Blob, name: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

/** Fetch a file from the API and save it, keeping the server's file name. */
export async function download(path: string, fallback: string): Promise<void> {
  const resp = await fetch(path);
  if (!resp.ok) {
    let message = `Download failed (${resp.status})`;
    try {
      const body = await resp.json();
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      // keep the generic message
    }
    throw new ApiError(resp.status, message);
  }
  saveBlob(await resp.blob(), fileName(resp.headers.get("Content-Disposition"), fallback));
}

/** MWG_<Title>_<Type>_<YYYY-MM-DD>, the same pattern the server uses for its files. */
export function exportName(title: string, type: string, ext: string): string {
  const clean = title.replace(/[^0-9A-Za-z]+/g, "_").replace(/^_+|_+$/g, "") || "Title";
  return `MWG_${clean}_${type}_${new Date().toISOString().slice(0, 10)}.${ext}`;
}
