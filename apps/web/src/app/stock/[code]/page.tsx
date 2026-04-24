"use client";

import { FileSearch, RefreshCw } from "lucide-react";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";

import { Badge } from "@/components/badge";
import { DataCard, EmptyState, ErrorState, Panel, SkeletonBlock } from "@/components/data-card";
import { MetricCard, MetricSkeleton } from "@/components/metric-card";
import { PageTitle } from "@/components/page-title";
import { SourceCard } from "@/components/source-card";
import { useStockProfile } from "@/lib/hooks";
import type { StockDetailData } from "@/lib/types";
import { cn } from "@/lib/utils";

const tabs = ["决策", "持仓", "发现", "证据"] as const;

function pickDetail(watchlist?: StockDetailData, opportunity?: StockDetailData, activeTab?: string) {
  if (activeTab === "发现" && opportunity) {
    return opportunity;
  }
  return watchlist || opportunity;
}

export default function StockProfilePage() {
  const params = useParams<{ code: string }>();
  const code = String(params.code || "");
  const profile = useStockProfile(code);
  const [activeTab, setActiveTab] = useState<(typeof tabs)[number]>("决策");
  const detail = pickDetail(profile.data?.watchlist, profile.data?.opportunity, activeTab);
  const allMetricCards = useMemo(() => {
    if (!detail) {
      return [];
    }
    return [
      ...(detail.decision_cards || []),
      ...(detail.metric_cards || []),
      ...(detail.meta_cards || []),
      ...(detail.level_cards || []),
    ];
  }, [detail]);

  return (
    <main className="flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
      <div className="mx-auto max-w-7xl">
        <PageTitle
          eyebrow={detail?.trade_date || code}
          title={detail?.hero?.title || `${detail?.name || "个股档案"} · ${code}`}
          summary={detail?.hero?.summary || detail?.topline?.verdict_summary || "统一查看这只股票的决策、持仓、发现和证据。"}
          icon={FileSearch}
          badge={detail?.hero?.status_label || detail?.topline?.verdict_badge || "个股档案"}
          actions={
            <button
              type="button"
              className="focus-ring inline-flex items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)]"
              onClick={() => void profile.refetch()}
            >
              <RefreshCw size={14} className={profile.isFetching ? "animate-spin" : ""} />
              刷新
            </button>
          }
        />

        {profile.isError ? <ErrorState message="个股详情暂不可用" onRetry={() => void profile.refetch()} /> : null}
        {!profile.isLoading && !detail ? <EmptyState>当前股票不在持仓或观察池详情中。</EmptyState> : null}

        <div className="mb-6 flex gap-2 overflow-x-auto rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-1">
          {tabs.map((tab) => (
            <button
              key={tab}
              type="button"
              className={cn(
                "focus-ring shrink-0 rounded-[6px] px-4 py-2 text-[13px]",
                activeTab === tab ? "bg-[var(--bg-tertiary)] text-[var(--text-primary)]" : "text-[var(--text-tertiary)]",
              )}
              onClick={() => setActiveTab(tab)}
            >
              {tab}
            </button>
          ))}
        </div>

        {profile.isLoading && !detail ? (
          <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {Array.from({ length: 4 }).map((_, index) => <MetricSkeleton key={index} />)}
          </section>
        ) : null}

        {detail && activeTab === "决策" ? (
          <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
            <div className="flex flex-col gap-6">
              <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {(detail.decision_cards || []).slice(0, 4).map((card, index) => (
                  <MetricCard key={`${card.label}-${index}`} {...card} tone={index === 0 ? detail.tone || "info" : index === 2 ? "risk" : "watch"} />
                ))}
              </section>

              <Panel title="执行循环" eyebrow="Loop">
                <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                  {(detail.execution_loop || []).map((card, index) => <DataCard key={`${card.label}-${index}`} card={card} />)}
                  {!detail.execution_loop?.length ? <EmptyState>暂无执行循环。</EmptyState> : null}
                </div>
              </Panel>
            </div>

            <Panel title="决策摘要" eyebrow="Canonical">
              <div className="surface-card p-4">
                {detail.canonical_decision ? (
                  <div className="flex flex-col gap-2">
                    {Object.entries(detail.canonical_decision).slice(0, 10).map(([key, value]) => (
                      <div key={key} className="flex gap-3 border-b border-[var(--border-subtle)] py-2 last:border-b-0">
                        <span className="mono w-36 shrink-0 text-[11px] text-[var(--text-tertiary)]">{key}</span>
                        <span className="min-w-0 flex-1 text-[12px] text-[var(--text-secondary)]">{String(value ?? "-")}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <EmptyState>暂无标准化决策。</EmptyState>
                )}
              </div>
            </Panel>
          </div>
        ) : null}

        {detail && activeTab === "持仓" ? (
          <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
            <Panel title="持仓指标" eyebrow="Holdings">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {[...(detail.meta_cards || []), ...(detail.level_cards || [])].slice(0, 8).map((card, index) => (
                  <MetricCard key={`${card.label}-${index}`} {...card} tone={index >= 4 ? "risk" : "info"} />
                ))}
                {!detail.meta_cards?.length && !detail.level_cards?.length ? <EmptyState>暂无持仓指标。</EmptyState> : null}
              </div>
            </Panel>

            <Panel title="触发条件" eyebrow="Triggers">
              <div className="flex flex-col gap-2">
                {(detail.triggers || []).map((trigger, index) => (
                  <DataCard
                    key={`${trigger.label || index}`}
                    card={{
                      title: trigger.label || `触发 ${index + 1}`,
                      value: trigger.value,
                      detail: trigger.detail,
                      tone: "watch",
                    }}
                  />
                ))}
                {!detail.triggers?.length ? <EmptyState>暂无盘中触发条件。</EmptyState> : null}
              </div>
            </Panel>
          </div>
        ) : null}

        {detail && activeTab === "发现" ? (
          <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
            <Panel title="发现指标" eyebrow="Discovery">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {allMetricCards.slice(0, 8).map((card, index) => (
                  <MetricCard key={`${card.label}-${index}`} {...card} tone={index === 0 ? detail.tone || "watch" : "info"} />
                ))}
                {!allMetricCards.length ? <EmptyState>暂无发现指标。</EmptyState> : null}
              </div>
            </Panel>

            <Panel title="洞察标签" eyebrow="Insights">
              <div className="flex flex-col gap-3">
                {(detail.insight_groups || []).map((group) => (
                  <div key={group.title} className="surface-card p-4">
                    <div className="mb-2 text-sm font-medium text-[var(--text-primary)]">{group.title}</div>
                    <div className="flex flex-wrap gap-2">
                      {group.items?.length ? group.items.map((item) => <Badge key={item} tone="watch">{item}</Badge>) : <span className="text-[12px] text-[var(--text-tertiary)]">{group.empty || "暂无"}</span>}
                    </div>
                  </div>
                ))}
                {!detail.insight_groups?.length ? <EmptyState>暂无洞察标签。</EmptyState> : null}
              </div>
            </Panel>
          </div>
        ) : null}

        {detail && activeTab === "证据" ? (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <Panel title="数据源" eyebrow="Freshness">
              <div className="flex flex-col gap-2">
                {(detail.source_cards || []).map((source, index) => <SourceCard key={`${source.label}-${index}`} source={source} />)}
                {!detail.source_cards?.length ? <EmptyState>暂无数据源状态。</EmptyState> : null}
              </div>
            </Panel>

            <Panel title="原始入口" eyebrow="Artifacts">
              <div className="grid grid-cols-1 gap-2">
                {(detail.artifacts || []).map((card, index) => (
                  <DataCard key={`${card.title || card.label}-${index}`} card={card} href={card.url} />
                ))}
                {!detail.artifacts?.length ? <EmptyState>暂无原始文件入口。</EmptyState> : null}
              </div>
            </Panel>
          </div>
        ) : null}
      </div>
    </main>
  );
}
