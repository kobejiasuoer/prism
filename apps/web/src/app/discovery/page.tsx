"use client";

import { RefreshCw, Telescope } from "lucide-react";
import { useMemo, useState } from "react";

import { Badge } from "@/components/badge";
import { DataCard, EmptyState, ErrorState, Panel, SkeletonBlock } from "@/components/data-card";
import { EvidencePanel } from "@/components/evidence-panel";
import { MetricCard, MetricSkeleton } from "@/components/metric-card";
import { PageTitle } from "@/components/page-title";
import { StockCard } from "@/components/stock-card";
import { useOpportunities } from "@/lib/hooks";
import { cn } from "@/lib/utils";

export default function DiscoveryPage() {
  const opportunities = useOpportunities();
  const data = opportunities.data;
  const groups = data?.groups?.length ? data.groups : data?.secondary_groups || [];
  const [activeIndex, setActiveIndex] = useState(0);
  const activeGroup = useMemo(() => groups[Math.min(activeIndex, Math.max(groups.length - 1, 0))], [activeIndex, groups]);

  return (
    <main className="flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
      <div className="mx-auto max-w-7xl">
        <PageTitle
          eyebrow={data?.display_date || data?.generated_at?.slice(0, 10) || data?.trade_date || "Discovery"}
          title={data?.topline?.verdict_title || data?.hero?.title || "观察池"}
          summary={data?.topline?.verdict_summary || data?.hero?.summary || "候选 Pipeline、阀门状态、质检和主线热力。"}
          icon={Telescope}
          badge={data?.hero?.status_label || (data?.brief_is_live ? "总控同步" : "实时链路")}
          actions={
            <button
              type="button"
              className="focus-ring inline-flex items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)]"
              onClick={() => void opportunities.refetch()}
            >
              <RefreshCw size={14} className={opportunities.isFetching ? "animate-spin" : ""} />
              刷新
            </button>
          }
        />

        {opportunities.isError ? (
          <ErrorState message="观察池数据暂不可用" onRetry={() => void opportunities.refetch()} />
        ) : null}

        <section className="mb-7 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {opportunities.isLoading && !data
            ? Array.from({ length: 4 }).map((_, index) => <MetricSkeleton key={index} />)
            : (data?.summary_cards || []).slice(0, 4).map((card, index) => (
                <MetricCard key={`${card.label}-${index}`} {...card} tone={index === 0 ? "positive" : index === 1 ? "watch" : "info"} />
              ))}
        </section>

        <section className="mb-7">
          <div className="mb-3 flex gap-2 overflow-x-auto pb-1">
            {groups.map((group, index) => (
              <button
                key={`${group.title}-${index}`}
                type="button"
                className={cn(
                  "focus-ring shrink-0 rounded-md border px-3 py-2 text-left text-[13px]",
                  index === activeIndex
                    ? "border-[var(--border-default)] bg-[var(--bg-tertiary)] text-[var(--text-primary)]"
                    : "border-[var(--border-subtle)] bg-[var(--bg-secondary)] text-[var(--text-secondary)]",
                )}
                onClick={() => setActiveIndex(index)}
              >
                <span>{group.title}</span>
                <span className="mono ml-2 text-[var(--text-tertiary)]">{group.count ?? group.cards?.length ?? 0}</span>
              </button>
            ))}
          </div>
        </section>

        <section className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
          <Panel title={activeGroup?.title || "候选列表"} eyebrow="Pipeline">
            <div className="flex flex-col gap-2">
              {opportunities.isLoading && !data ? (
                Array.from({ length: 5 }).map((_, index) => <SkeletonBlock key={index} className="h-24 w-full" />)
              ) : activeGroup?.cards?.length ? (
                activeGroup.cards.map((stock) => <StockCard key={`${activeGroup.title}-${stock.code}`} stock={stock} />)
              ) : (
                <EmptyState>{activeGroup?.empty || "当前阶段没有候选。"}</EmptyState>
              )}
            </div>
          </Panel>

          <div className="flex flex-col gap-6">
            <Panel title="主线热力" eyebrow="Themes">
              <div className="grid grid-cols-1 gap-2">
                {(data?.theme_cards || []).length ? (
                  data?.theme_cards?.slice(0, 5).map((card, index) => <DataCard key={`${card.title}-${index}`} card={card} />)
                ) : (
                  <EmptyState>暂无主线热力。</EmptyState>
                )}
              </div>
            </Panel>

            <EvidencePanel page="opportunities" sources={data?.source_cards} title="来源校验" eyebrow="Freshness" />
          </div>
        </section>
      </div>
    </main>
  );
}
