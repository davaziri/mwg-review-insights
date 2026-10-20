/** The API sends naive UTC timestamps; mark them as UTC before parsing. */
export function parseUtc(value: string): Date {
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(value) ? value : `${value}Z`);
}

const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

export function timeAgo(value: string | null): string {
  if (!value) return "Never";
  const seconds = Math.round((parseUtc(value).getTime() - Date.now()) / 1000);
  const abs = Math.abs(seconds);
  if (abs < 45) return "just now";
  if (abs < 3600) return rtf.format(Math.round(seconds / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(seconds / 3600), "hour");
  return rtf.format(Math.round(seconds / 86400), "day");
}

export function dateTime(value: string | null): string {
  if (!value) return "";
  return parseUtc(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export const number = (n: number) => n.toLocaleString();

export function percent(part: number, whole: number): string {
  // Steam truncates its percentage (283 of 305 is "92%"), so match it.
  return whole > 0 ? `${Math.floor((part / whole) * 100)}%` : "";
}
