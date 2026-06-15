"use client";

import { Badge } from "@/components/badge";
import { EmptyState, ErrorState, Panel, SkeletonBlock } from "@/components/data-card";
import { useDecisionLedgerStock } from "@/lib/hooks";
import type { DecisionLedgerCompactRecord } from "@/lib/types";

export function StockDecisionTimelinePanel({ code, enabled }: { code: string; enabled: boolean }) {
  const ledger = useDecisionLedgerStock(code, enabled);
  const items = (ledger.data?.items || []) as DecisionLedgerCompactRecord[];
  const errors = ledger.data?.errors || [];

  return (
    <Panel title="Decision Ledger 历史" eyebrow="Ledger Timeline">
      <div className="surface-card p-4">
        {ledger.isLoading && !ledger.data ? (
          <div className="flex flex-col gap-2">
            {Array.from({ length: 3 }).map((_, index) => (
              <SkeletonBlock key={index} className="h-12 w-full" />
            ))}
          </div>
        ) : ledger.isError ? (
          <ErrorState message="Decision Ledger 暂不可用" onRetry={() => void ledger.refetch()} />
        ) : !items.length ? (
          <EmptyState>这只股票暂无 Decision Ledger 记录。</EmptyState>
        ) : (
          <div className="flex flex-col gap-2">
            {items.slice(0, 10).map((item) => (
              <div
                key={item.decision_id}
                className="flex min-h-[56px] flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 text-[12px] text-[var(--text-primary)]">
                    <span className="font-medium">{item.trade_date}</span>
                    <span className="text-[11px] text-[var(--text-tertiary)]">{item.lane || "-"}</span>
                  </div>
                  {item.main_conclusion ? (
                    <div className="mt-1 line-clamp-2 text-[11px] leading-4 text-[var(--text-tertiary)]">{item.main_conclusion}</div>
                  ) : null}
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  {item.action_label || item.action ? (
                    <Badge tone="watch">{item.action_label || item.action}</Badge>
                  ) : null}
                  <Badge tone={item.latest_execution?.status ? "info" : "stale"}>
                    执行 {item.latest_execution?.status || "未记录"}
                  </Badge>
                  <Badge tone={item.latest_outcome?.label ? "info" : "stale"}>
                    结果 {item.latest_outcome?.window || ""} {item.latest_outcome?.label || "待评估"}
                  </Badge>
                  <Badge tone={item.status === "superseded" ? "warning" : "good"}>
                    {item.status === "superseded" ? "已被替代" : "open"}
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        )}
        {errors.length ? (
          <div className="mt-3 rounded-md border border-[var(--border-warn)] bg-[var(--surface-warn)] px-3 py-2 text-[11px] text-[var(--text-warn)]">
            部分 ledger 文件解析失败：{errors[0].file} ({errors[0].error})
          </div>
        ) : null}
      </div>
    </Panel>
  );
}
