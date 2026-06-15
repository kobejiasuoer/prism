export function normalizeTaskName(value?: string) {
  const normalized = String(value || "").trim().toLowerCase();
  return normalized === "watchlist" ? "watchlist_refresh" : normalized;
}
