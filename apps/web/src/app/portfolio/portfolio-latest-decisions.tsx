"use client";

import { RefreshCw } from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";

import { Badge } from "@/components/badge";
import { ErrorState, SkeletonBlock } from "@/components/data-card";
import { useDecisionLedgerRecent } from "@/lib/hooks";
import type { DecisionLedgerCompactRecord, PortfolioAccountResponse, Tone } from "@/lib/types";
import { stockCodeKey, stockDetailHref } from "./portfolio-utils";

export function PortfolioLatestDecisions({
  positions,
}: {
  positions: PortfolioAccountResponse["account"]["open_positions"];
}) {
  const positionCodes = useMemo(
    () => [...new Set(positions.map((pos) => stockCodeKey(pos.code)).filter(Boolean))],
    [positions],
  );
  const ledger = useDecisionLedgerRecent(
    {
      limit: Math.max(positionCodes.length, 1),
      codes: positionCodes,
      latestPerCode: true,
    },
    { enabled: Boolean(positionCodes.length) },
  );
  const items = (ledger.data?.items || []) as DecisionLedgerCompactRecord[];

  const latestByCode = useMemo(() => {
    const map = new Map<string, DecisionLedgerCompactRecord>();
    for (const item of items) {
      const key = stockCodeKey(item.code);
      if (!key) continue;
      if (!map.has(key)) {
        map.set(key, item);
      }
    }
    return map;
  }, [items]);

  if (!positions.length) {
    return null;
  }

  return (
    <div data-testid="portfolio-latest-decisions-panel">
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="text-[12px] leading-5 text-[var(--text-tertiary)]">
          已按当前持仓匹配最近 Prism 判断，未命中的持仓会标记为未记录。
        </div>
        <div className="flex items-center gap-2">
          <Badge tone={ledger.isFetching ? "info" : "positive"}>
            {ledger.isFetching ? "读取中" : `${items.length} 条`}
          </Badge>
          <button
            type="button"
            className="focus-ring inline-flex items-center gap-1.5 rounded-md border border-[var(--border-subtle)] px-2 py-1 text-[11px] text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
            onClick={() => void ledger.refetch()}
          >
            <RefreshCw size={12} className={ledger.isFetching ? "animate-spin" : ""} />
            刷新
          </button>
        </div>
      </div>

      {ledger.isLoading && !items.length ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, index) => (
            <SkeletonBlock key={index} className="h-14 w-full" />
          ))}
        </div>
      ) : ledger.isError ? (
        <ErrorState message="Decision Ledger 暂不可用" onRetry={() => void ledger.refetch()} />
      ) : (
        <>
          <div className="flex flex-col gap-2 md:hidden">
            {positions.map((pos) => {
              const decision = latestByCode.get(stockCodeKey(pos.code));
              return (
                <article
                  key={`${pos.code}-decision-mobile`}
                  className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3"
                >
                  <div className="flex items-start justify-between gap-3">
                    <Link href={stockDetailHref(pos.code)} className="focus-ring min-w-0 rounded-[6px]">
                      <div className="truncate text-[13px] font-semibold text-[var(--text-primary)]">
                        {pos.name || pos.code}
                      </div>
                      <div className="mono mt-0.5 text-[11px] text-[var(--text-tertiary)]">{pos.code}</div>
                    </Link>
                    {decision ? (
                      <Badge tone={decision.status === "superseded" ? "warning" : "good"}>
                        {decision.status === "superseded" ? "已被替代" : decision.status || "open"}
                      </Badge>
                    ) : (
                      <Badge tone="stale">未记录</Badge>
                    )}
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-2 text-[12px]">
                    <div>
                      <div className="text-[11px] text-[var(--text-tertiary)]">决策日期</div>
                      <div className="mt-1 text-[var(--text-primary)]">{decision?.trade_date || "-"}</div>
                    </div>
                    <div>
                      <div className="text-[11px] text-[var(--text-tertiary)]">动作</div>
                      <div className="mt-1">
                        {decision ? (
                          <Badge tone="watch">{decision.action_label || decision.action || "-"}</Badge>
                        ) : (
                          <span className="text-[var(--text-tertiary)]">未记录</span>
                        )}
                      </div>
                    </div>
                    <div>
                      <div className="text-[11px] text-[var(--text-tertiary)]">执行</div>
                      <div className="mt-1">
                        {decision ? (
                          <Badge tone={decision.latest_execution?.status ? "info" : "stale"}>
                            {decision.latest_execution?.status || "未记录"}
                          </Badge>
                        ) : (
                          <span className="text-[var(--text-tertiary)]">-</span>
                        )}
                      </div>
                    </div>
                    <div>
                      <div className="text-[11px] text-[var(--text-tertiary)]">结果</div>
                      <div className="mt-1">
                        {decision?.latest_outcome?.label ? (
                          <Badge tone={(decision.latest_outcome.tone as Tone) || "info"}>
                            {decision.latest_outcome.window || ""} {decision.latest_outcome.label}
                          </Badge>
                        ) : (
                          <span className="text-[var(--text-tertiary)]">待评估</span>
                        )}
                      </div>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
          <div className="hidden overflow-x-auto md:block">
            <table className="w-full text-[12px]">
              <thead className="text-[var(--text-tertiary)]">
                <tr>
                  <th className="px-2 py-1 text-left">代码</th>
                  <th className="px-2 py-1 text-left">名称</th>
                  <th className="px-2 py-1 text-left">决策日期</th>
                  <th className="px-2 py-1 text-left">动作</th>
                  <th className="px-2 py-1 text-left">执行</th>
                  <th className="px-2 py-1 text-left">结果</th>
                  <th className="px-2 py-1 text-left">状态</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((pos) => {
                  const decision = latestByCode.get(stockCodeKey(pos.code));
                  return (
                    <tr key={pos.code} className="border-t border-[var(--border-subtle)]">
                      <td className="px-2 py-1 font-mono">{pos.code}</td>
                      <td className="px-2 py-1">{pos.name}</td>
                      <td className="px-2 py-1">{decision?.trade_date || "-"}</td>
                      <td className="px-2 py-1">
                        {decision ? (
                          <Badge tone="watch">{decision.action_label || decision.action || "-"}</Badge>
                        ) : (
                          <span className="text-[var(--text-tertiary)]">未记录</span>
                        )}
                      </td>
                      <td className="px-2 py-1">
                        {decision ? (
                          <Badge tone={decision.latest_execution?.status ? "info" : "stale"}>
                            {decision.latest_execution?.status || "未记录"}
                          </Badge>
                        ) : (
                          <span className="text-[var(--text-tertiary)]">-</span>
                        )}
                      </td>
                      <td className="px-2 py-1">
                        {decision?.latest_outcome?.label ? (
                          <Badge tone={(decision.latest_outcome.tone as Tone) || "info"}>
                            {decision.latest_outcome.window || ""} {decision.latest_outcome.label}
                          </Badge>
                        ) : (
                          <span className="text-[var(--text-tertiary)]">待评估</span>
                        )}
                      </td>
                      <td className="px-2 py-1">
                        {decision ? (
                          <Badge tone={decision.status === "superseded" ? "warning" : "good"}>
                            {decision.status === "superseded" ? "已被替代" : decision.status || "open"}
                          </Badge>
                        ) : (
                          <span className="text-[var(--text-tertiary)]">-</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
