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
    case "persistent":
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
