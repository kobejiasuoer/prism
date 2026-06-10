import type { StockDetailData } from "@/lib/types";

export { uniqueTexts } from "@/lib/text-utils";

export function canonicalText(
  canonical: StockDetailData["canonical_decision"] | undefined,
  key: string,
  fallback = "-",
) {
  const value = canonical?.[key];
  if (value === null || value === undefined || value === "") {
    return fallback;
  }
  return String(value);
}

export function hasDisplayValue(value: unknown) {
  if (value === null || value === undefined) {
    return false;
  }
  const text = String(value).trim();
  return Boolean(text && text !== "-");
}

export function displayText(value: unknown, fallback = "暂未给出") {
  return hasDisplayValue(value) ? String(value) : fallback;
}
