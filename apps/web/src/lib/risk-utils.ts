import type { Tone } from "./types";

export function riskLevelTone(level?: string): Tone {
  if (level === "block") {
    return "risk";
  }
  if (level === "degrade") {
    return "warning";
  }
  if (level === "warn") {
    return "watch";
  }
  return "info";
}
