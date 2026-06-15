import type { PortfolioAccountResponse } from "@/lib/types";

export type WritebackContext = {
  code: string;
  name: string;
  source: string;
  sourceLabel: string;
  tradeDate: string;
  intentKey: string;
  conclusion: string;
  position: string;
  continueCondition: string;
  stopCondition: string;
};

export type NoFillItem =
  PortfolioAccountResponse["account"]["no_fill_intents"][number];

export type WritebackOutcome = {
  intentKey: string;
  tradeDate: string;
  code: string;
  name: string;
  resultLabel: string;
  statusValue: "watch" | "skip" | "no_fill";
  processedAt: string;
  note?: string;
};

export function decisionLabel(value: WritebackOutcome["statusValue"]): string {
  if (value === "watch") return "继续观察";
  if (value === "skip") return "放弃";
  return "未成交";
}

export function decisionStatusText(
  value: WritebackOutcome["statusValue"],
): string {
  if (value === "watch") return "watch";
  if (value === "skip") return "skip";
  return "no_fill";
}

export function outcomeStorageKey(
  intentKey: string,
  tradeDate: string,
): string {
  return `portfolio-writeback-outcome:${tradeDate}:${intentKey}`;
}

export function formatOutcomeTime(value: string): string {
  if (!value) return "-";
  const parsed = new Date(value.replace(" ", "T"));
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString("zh-CN", { hour12: false });
}
