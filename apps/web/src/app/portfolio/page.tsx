"use client";

import { RefreshCw, WalletCards } from "lucide-react";

import { Badge } from "@/components/badge";
import { EmptyState, ErrorState, Panel, SkeletonBlock } from "@/components/data-card";
import { EvidencePanel } from "@/components/evidence-panel";
import { MetricCard, MetricSkeleton } from "@/components/metric-card";
import { PageTitle } from "@/components/page-title";
import { StockCard } from "@/components/stock-card";
import { WatchlistManagerPanel } from "@/components/watchlist-manager-panel";
import { useWatchlist } from "@/lib/hooks";

export default function PortfolioPage() {
  const watchlist = useWatchlist();
  const data = watchlist.data;

  return (
    <main className="flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
      <div className="mx-auto max-w-7xl">
        <PageTitle
          eyebrow={data?.trade_date || "Portfolio"}
          title={data?.topline?.verdict_title || data?.hero?.title || "持仓管理"}
          summary={data?.topline?.verdict_summary || data?.hero?.summary || "按优先处理、跟踪增强、继续观察分组管理当前自选股。"}
          icon={WalletCards}
          badge={data?.brief_is_live ? "总控同步" : "实时快照"}
          actions={
            <button
              type="button"
              className="focus-ring inline-flex items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)]"
              onClick={() => void watchlist.refetch()}
            >
              <RefreshCw size={14} className={watchlist.isFetching ? "animate-spin" : ""} />
              刷新
            </button>
          }
        />

        {watchlist.isError ? (
          <ErrorState message="持仓数据暂不可用" onRetry={() => void watchlist.refetch()} />
        ) : null}

        <section className="mb-7 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {watchlist.isLoading && !data
            ? Array.from({ length: 4 }).map((_, index) => <MetricSkeleton key={index} />)
            : (data?.summary_cards || []).slice(0, 4).map((card, index) => (
                <MetricCard key={`${card.label}-${index}`} {...card} tone={index === 1 ? "risk" : index === 2 ? "info" : "watch"} />
              ))}
        </section>

        <section className="mb-7 grid grid-cols-1 gap-4 xl:grid-cols-3">
          {watchlist.isLoading && !data
            ? Array.from({ length: 3 }).map((_, index) => (
                <div key={index} className="surface-card p-4">
                  <SkeletonBlock className="h-5 w-24" />
                  <SkeletonBlock className="mt-4 h-24 w-full" />
                  <SkeletonBlock className="mt-3 h-24 w-full" />
                </div>
              ))
            : (data?.groups || []).map((group) => (
                <Panel
                  key={group.key || group.title}
                  title={group.title}
                  eyebrow={group.subtitle}
                  action={<Badge tone={group.key === "priority" ? "risk" : group.key === "follow" ? "info" : "watch"}>{group.count || 0}</Badge>}
                  className="surface-card p-4"
                >
                  <div className="flex flex-col gap-2">
                    {group.cards?.length ? (
                      group.cards.map((stock) => <StockCard key={stock.code} stock={stock} />)
                    ) : (
                      <EmptyState>{group.empty || "当前没有股票。"}</EmptyState>
                    )}
                  </div>
                </Panel>
              ))}
        </section>

        <section id="watchlist-manager" className="mb-7">
          <WatchlistManagerPanel />
        </section>

        <section className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <Panel title="总控焦点" eyebrow="Focus">
            <div className="surface-card p-4">
              <div className="mb-3 flex flex-wrap gap-2">
                {(data?.focus_tags || []).length ? (
                  data?.focus_tags?.map((item) => <Badge key={item} tone="info">{item}</Badge>)
                ) : (
                  <span className="text-[13px] text-[var(--text-tertiary)]">暂无额外持仓焦点。</span>
                )}
              </div>
              <div className="flex flex-col gap-2">
                {(data?.avoid_points || []).map((item) => (
                  <div key={item} className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
                    {item}
                  </div>
                ))}
              </div>
            </div>
          </Panel>

          <EvidencePanel page="watchlist" sources={data?.source_cards} title="来源校验" eyebrow="Freshness" />
        </section>
      </div>
    </main>
  );
}
