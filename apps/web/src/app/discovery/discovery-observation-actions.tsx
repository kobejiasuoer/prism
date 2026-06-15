"use client";

import { CheckCircle2, ListPlus, RefreshCw } from "lucide-react";

import {
  useAddWatchlistStock,
  useUpdateTodayActionDecision,
} from "@/lib/hooks";
import type { StockListCard } from "@/lib/types";
import { cn } from "@/lib/utils";

export type DiscoveryObservationActionsProps = {
  stock: StockListCard;
  tradeDate?: string;
  compact?: boolean;
  onFeedback: (message: string) => void;
};

function actionClass(compact?: boolean) {
  return cn(
    "focus-ring inline-flex h-8 items-center justify-center gap-1.5 rounded-md border border-[var(--border-subtle)] text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] disabled:cursor-not-allowed disabled:opacity-50",
    compact ? "w-8 px-0" : "px-2.5",
  );
}

export function DiscoveryObservationActions({
  stock,
  tradeDate,
  compact = false,
  onFeedback,
}: DiscoveryObservationActionsProps) {
  const addStock = useAddWatchlistStock();
  const reviewDecision = useUpdateTodayActionDecision();

  function addToObservationPlan() {
    onFeedback("");
    addStock.mutate(
      { code: stock.code, name: stock.name, trigger_refresh: true },
      {
        onSuccess: (payload) =>
          onFeedback(
            payload.message || `${stock.name || stock.code} 已加入观察计划。`,
          ),
        onError: (error) =>
          onFeedback(
            error instanceof Error ? error.message : "加入观察计划失败",
          ),
      },
    );
  }

  function markReviewed() {
    if (!tradeDate || !stock.action_key) {
      onFeedback("这条观察项暂时没有可回写的复核 key。");
      return;
    }
    onFeedback("");
    reviewDecision.mutate(
      { trade_date: tradeDate, key: stock.action_key, decision: "done" },
      {
        onSuccess: () =>
          onFeedback(`${stock.name || stock.code} 已标记为已复核。`),
        onError: (error) =>
          onFeedback(error instanceof Error ? error.message : "标记已复核失败"),
      },
    );
  }

  return (
    <>
      <button
        type="button"
        className={actionClass(compact)}
        onClick={addToObservationPlan}
        disabled={addStock.isPending}
        title="加入观察计划"
        aria-label="加入观察计划"
      >
        {addStock.isPending ? (
          <RefreshCw size={13} className="animate-spin" />
        ) : (
          <ListPlus size={13} />
        )}
        {compact ? null : "加入观察计划"}
      </button>
      <button
        type="button"
        className={actionClass(compact)}
        onClick={markReviewed}
        disabled={reviewDecision.isPending || !stock.action_key}
        title={stock.action_key ? "标记已复核" : "这条观察项暂无复核 key"}
        aria-label="标记已复核"
      >
        {reviewDecision.isPending ? (
          <RefreshCw size={13} className="animate-spin" />
        ) : (
          <CheckCircle2 size={13} />
        )}
        {compact ? null : "标记已复核"}
      </button>
    </>
  );
}
