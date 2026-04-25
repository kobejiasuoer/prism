"use client";

import { BarChart3, RefreshCw } from "lucide-react";

import { Badge } from "@/components/badge";
import { DataCard, EmptyState, ErrorState, Panel, SkeletonBlock } from "@/components/data-card";
import { EvidencePanel } from "@/components/evidence-panel";
import { MetricCard, MetricSkeleton } from "@/components/metric-card";
import { PageTitle } from "@/components/page-title";
import { RiskAlert } from "@/components/risk-alert";
import { useReview } from "@/lib/hooks";

export default function ReviewPage() {
  const review = useReview();
  const data = review.data;

  return (
    <main className="flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
      <div className="mx-auto max-w-7xl">
        <PageTitle
          eyebrow="Review"
          title={data?.topline?.verdict_title || data?.hero?.title || "复盘"}
          summary={data?.topline?.verdict_summary || data?.hero?.summary || "环境仪表、校准规则、基准对比和变化回放。"}
          icon={BarChart3}
          badge={data?.topline?.verdict_badge || "环境结论"}
          actions={
            <button
              type="button"
              className="focus-ring inline-flex items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)]"
              onClick={() => void review.refetch()}
            >
              <RefreshCw size={14} className={review.isFetching ? "animate-spin" : ""} />
              刷新
            </button>
          }
        />

        {review.isError ? <ErrorState message="复盘数据暂不可用" onRetry={() => void review.refetch()} /> : null}

        {data?.topline?.meta_pills?.length ? (
          <section className="mb-7 flex flex-wrap gap-2">
            {data.topline.meta_pills.map((pill) => (
              <Badge key={`${pill.label}-${pill.value}`} tone={String(pill.value).startsWith("-") ? "risk" : "positive"}>
                {pill.label} {pill.value}
              </Badge>
            ))}
          </section>
        ) : null}

        <section className="mb-7 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {review.isLoading && !data
            ? Array.from({ length: 4 }).map((_, index) => <MetricSkeleton key={index} />)
            : (data?.summary_cards || []).slice(0, 4).map((card, index) => (
                <MetricCard key={`${card.label}-${index}`} {...card} tone={String(card.value).startsWith("-") ? "risk" : index === 0 ? "info" : "positive"} />
              ))}
        </section>

        <section className="mb-7 grid grid-cols-1 gap-3 xl:grid-cols-4">
          {review.isLoading && !data
            ? Array.from({ length: 4 }).map((_, index) => <SkeletonBlock key={index} className="h-44 w-full" />)
            : (data?.verdict_cards || []).slice(0, 4).map((card, index) => (
                <DataCard key={`${card.title}-${index}`} card={card} href={card.detail_url} />
              ))}
        </section>

        <section className="mb-7 grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_400px]">
          <Panel title="校准规则" eyebrow="Rules">
            <div className="flex flex-col gap-2">
              {(data?.action_rules || []).length ? (
                data?.action_rules?.slice(0, 5).map((row, index) => <RiskAlert key={`${row.title}-${index}`} row={row} />)
              ) : (
                <EmptyState>暂无校准规则。</EmptyState>
              )}
            </div>
          </Panel>

          <Panel title="变化回放" eyebrow="Lifecycle">
            <div className="surface-card p-4">
              {data?.lifecycle_note ? <p className="mb-4 text-[12px] leading-5 text-[var(--text-secondary)]">{data.lifecycle_note}</p> : null}
              <div className="grid grid-cols-1 gap-2">
                {(data?.lifecycle_cards || []).slice(0, 4).map((card, index) => (
                  <MetricCard key={`${card.label}-${index}`} {...card} tone="info" />
                ))}
                {!data?.lifecycle_cards?.length ? <EmptyState>暂无变化回放。</EmptyState> : null}
              </div>
            </div>
          </Panel>
        </section>

        <section className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <Panel title="基准 vs 最新切片" eyebrow="Compare">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {(data?.comparison_cards || []).slice(0, 4).map((card, index) => (
                <MetricCard key={`${card.label}-${index}`} {...card} tone={String(card.value).startsWith("-") ? "risk" : "positive"} />
              ))}
              {!data?.comparison_cards?.length ? <EmptyState>暂无对比数据。</EmptyState> : null}
            </div>
          </Panel>

          <EvidencePanel page="review" sources={data?.source_cards} title="来源校验" eyebrow="Freshness" />
        </section>
      </div>
    </main>
  );
}
