"use client";

import { ChevronDown } from "lucide-react";
import dynamic from "next/dynamic";
import { useState } from "react";

import { Badge } from "@/components/badge";
import { EmptyState, ErrorState, SkeletonBlock } from "@/components/data-card";
import { StockCard } from "@/components/stock-card";
import { useWatchlist } from "@/lib/hooks";

const WatchlistManagerPanel = dynamic(
  () =>
    import("@/components/watchlist-manager-panel").then(
      (module) => module.WatchlistManagerPanel,
    ),
  {
    ssr: false,
    loading: () => <SkeletonBlock className="h-64 w-full" />,
  },
);

export function PortfolioResearchUniverse() {
  const watchlist = useWatchlist();
  const [managerOpen, setManagerOpen] = useState(false);

  return (
    <>
      {watchlist.isError ? (
        <ErrorState message="研究自选股暂不可用" onRetry={() => void watchlist.refetch()} />
      ) : null}
      {!watchlist.data && watchlist.isFetching ? (
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <div
              key={index}
              className="h-48 w-full animate-pulse rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)]"
            />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
          {(watchlist.data?.groups || []).map((group) => (
            <div key={group.key || group.title}>
              <div className="mb-2 flex items-center gap-2">
                <span className="text-[13px] font-medium">{group.title}</span>
                <Badge tone={group.key === "priority" ? "risk" : group.key === "follow" ? "info" : "watch"}>
                  {group.count || 0}
                </Badge>
              </div>
              <div className="flex flex-col gap-2">
                {group.cards?.length ? (
                  group.cards.map((stock) => <StockCard key={stock.code} stock={stock} />)
                ) : (
                  <EmptyState>{group.empty || "当前没有股票。"}</EmptyState>
                )}
              </div>
            </div>
          ))}
          {!watchlist.isFetching && !watchlist.data?.groups?.length && !watchlist.isError ? (
            <EmptyState>当前没有研究自选股。</EmptyState>
          ) : null}
        </div>
      )}
      <section id="watchlist-manager" className="mt-7">
        <details
          open={managerOpen}
          className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)]"
          onToggle={(event) => setManagerOpen(event.currentTarget.open)}
        >
          <summary className="focus-ring flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3">
            <div className="min-w-0">
              <div className="text-[13px] font-medium text-[var(--text-primary)]">
                管理研究名单
              </div>
              <div className="mt-1 line-clamp-1 text-[11px] text-[var(--text-tertiary)]">
                默认只读研究自选股；需要新增、归档或恢复时再加载管理工具。
              </div>
            </div>
            <span className="inline-flex shrink-0 items-center gap-2">
              <Badge tone={managerOpen ? "info" : "watch"}>
                {managerOpen ? "已展开" : "按需加载"}
              </Badge>
              <ChevronDown
                size={15}
                className={managerOpen ? "rotate-180 transition" : "transition"}
              />
            </span>
          </summary>
          {managerOpen ? (
            <div className="border-t border-[var(--border-subtle)] p-4">
              <WatchlistManagerPanel />
            </div>
          ) : (
            <div className="border-t border-[var(--border-subtle)] px-4 py-3 text-[12px] leading-5 text-[var(--text-secondary)]">
              展开后才读取名单管理状态，普通查看研究名单不会触发管理接口。
            </div>
          )}
        </details>
      </section>
    </>
  );
}
