import type { HoldingReview } from "@/lib/types";

export function formatMoney(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "-";
  }
  return `¥${Number(value).toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "-";
  }
  return `${Number(value).toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}%`;
}

export function stockDetailHref(code: string | null | undefined): string {
  const raw = String(code || "")
    .trim()
    .toLowerCase();
  if (!raw) {
    return "#";
  }
  const match = raw.match(/^(sh|sz|bj)(\d{6})$/);
  return `/stock/${match?.[2] || raw}`;
}

export function stockCodeKey(code: string | null | undefined): string {
  const raw = String(code || "")
    .trim()
    .toLowerCase();
  if (!raw) {
    return "";
  }
  const match = raw.match(/^(sh|sz|bj)(\d{6})$/);
  return match?.[2] || raw;
}

export function pnlTone(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "text-[var(--text-tertiary)]";
  }
  return value >= 0
    ? "text-[var(--tone-positive)]"
    : "text-[var(--tone-risk)]";
}

export function numericValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

export function suggestedSellQty(review: HoldingReview): number | null {
  const target = numericValue(review.holding_decision?.target_sell_qty);
  if (target !== null && target > 0) {
    return Math.min(Number(review.qty || 0), Math.round(target));
  }
  if (review.today_action === "clear_exit") {
    return Number(review.qty || 0) || null;
  }
  if (
    ["defense_reduce", "profit_take", "time_exit"].includes(
      String(review.today_action || ""),
    )
  ) {
    const qty = Number(review.qty || 0);
    return qty ? Math.max(1, Math.floor(qty / 2)) : null;
  }
  return null;
}
