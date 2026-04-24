import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

import type { Tone } from "./types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function asText(value: unknown, fallback = "-") {
  if (value === null || value === undefined || value === "") {
    return fallback;
  }
  return String(value);
}

export function compactText(values: Array<unknown>) {
  return values.map((value) => asText(value, "")).filter(Boolean);
}

export function stockCodeFromTitle(title: string) {
  const match = title.match(/\b\d{6}\b/);
  return match?.[0] ?? "";
}

export function stockNameFromTitle(title: string) {
  return title.replace(/\b\d{6}\b/g, "").trim() || title;
}

export function toneColor(tone?: Tone | string) {
  switch (tone) {
    case "buy":
    case "positive":
    case "good":
      return "var(--tone-buy)";
    case "sell":
    case "negative":
    case "risk":
      return "var(--tone-sell)";
    case "hold":
    case "info":
      return "var(--tone-hold)";
    case "avoid":
    case "stale":
      return "var(--tone-avoid)";
    case "watch":
    case "warning":
    default:
      return "var(--tone-watch)";
  }
}

export function toneLabel(tone?: Tone | string) {
  switch (tone) {
    case "buy":
      return "买入";
    case "sell":
    case "risk":
      return "风险";
    case "hold":
      return "持有";
    case "avoid":
      return "回避";
    case "positive":
    case "good":
      return "就绪";
    case "negative":
      return "负面";
    case "info":
      return "信息";
    case "warning":
    case "watch":
    default:
      return "观察";
  }
}
