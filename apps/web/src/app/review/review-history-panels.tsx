"use client";

import { ArrowRight, Database, ExternalLink, RefreshCw } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/badge";
import { EmptyState, ErrorState, SkeletonBlock } from "@/components/data-card";
import { MetricCard } from "@/components/metric-card";
import { useDecisionLedgerRecent, useReviewShadowReplay } from "@/lib/hooks";
import type {
  DecisionLedgerCompactRecord,
  DecisionLedgerRecentResponse,
  Tone,
} from "@/lib/types";
import {
  countText,
  reasonLabel,
  reviewCaseHref,
  shadowStatusMeta,
} from "./review-utils";
import { MiniFact } from "./review-mini-fact";

const SHADOW_BUCKET_LABELS: Record<string, string> = {
  top_observe: "重点观察",
  near_miss: "接近入池",
  risk_reject: "风险剔除",
};

const SHADOW_OUTCOME_LABELS: Record<string, string> = {
  validated: "验证有效",
  invalidated: "判断失效",
  inconclusive: "未定",
  avoided_loss: "避开亏损",
  missed_opportunity: "错过机会",
};

const SHADOW_SETUP_LABELS: Record<string, string> = {
  trend_follow: "趋势延续",
  pullback_support: "回踩支撑",
  volume_rebound: "放量反弹",
  mixed_observation: "混合观察",
  overheated_reject: "过热剔除",
};

const SHADOW_ACTION_LABELS: Record<string, string> = {
  observe: "观察",
  skip: "跳过",
};

function shadowKeyLabel(labels: Record<string, string>, key: string) {
  return labels[key] || key.replace(/_/g, " ");
}

function ShadowCountPanel({
  title,
  counts,
  labels,
  empty,
}: {
  title: string;
  counts?: Record<string, number>;
  labels: Record<string, string>;
  empty: string;
}) {
  const entries = Object.entries(counts || {}).sort(
    ([, left], [, right]) => Number(right) - Number(left),
  );
  const total = entries.reduce((sum, [, value]) => sum + Number(value || 0), 0);

  return (
    <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3">
      <div className="mb-2 text-[12px] font-medium text-[var(--text-primary)]">
        {title}
      </div>
      {entries.length ? (
        <div className="space-y-2">
          {entries.slice(0, 5).map(([key, value]) => {
            const width = total
              ? Math.max(5, (Number(value || 0) / total) * 100)
              : 0;
            return (
              <div key={key}>
                <div className="mb-1 flex items-center justify-between gap-3 text-[11px]">
                  <span className="truncate text-[var(--text-secondary)]">
                    {shadowKeyLabel(labels, key)}
                  </span>
                  <span className="mono shrink-0 text-[var(--text-tertiary)]">
                    {countText(value)}
                  </span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-[var(--bg-tertiary)]">
                  <div
                    className="h-full rounded-full bg-[var(--tone-hold)]"
                    style={{ width: `${width}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <EmptyState>{empty}</EmptyState>
      )}
    </div>
  );
}

export function HistoricalShadowReplay() {
  const shadowReplay = useReviewShadowReplay();
  const shadow = shadowReplay.data;
  const status = shadowStatusMeta(shadow?.status);
  const cards = shadow?.cards || [];
  const artifacts = shadow?.artifacts || [];
  const report =
    artifacts.find((item) => String(item.title || "").includes("报告")) ||
    artifacts[0];

  return (
    <div className="border-t border-[var(--border-subtle)]">
      {shadowReplay.isLoading && !shadow ? (
        <div className="space-y-3 p-4">
          <SkeletonBlock className="h-24 w-full" />
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <SkeletonBlock className="h-24 w-full" />
            <SkeletonBlock className="h-24 w-full" />
            <SkeletonBlock className="h-24 w-full" />
            <SkeletonBlock className="h-24 w-full" />
          </div>
        </div>
      ) : shadowReplay.isError ? (
        <div className="p-4">
          <ErrorState
            message="历史影子样本暂不可用"
            onRetry={() => void shadowReplay.refetch()}
          />
        </div>
      ) : shadow ? (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_360px]">
            <div className="p-4 sm:p-5">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <Badge tone={status.tone}>{status.label}</Badge>
                <Badge tone="info">
                  {shadow.start_date || "-"} 至 {shadow.end_date || "-"}
                </Badge>
                <Badge tone="watch">
                  {shadow.source_lane || "shadow_price_signal_baseline"}
                </Badge>
                {report?.url ? (
                  <a
                    href={report.url}
                    target="_blank"
                    rel="noreferrer"
                    className="focus-ring inline-flex items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-1.5 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                  >
                    打开报告
                    <ExternalLink size={13} />
                  </a>
                ) : null}
              </div>
              <h3 className="text-lg font-semibold text-[var(--text-primary)]">
                {shadow.title || "2025 价格影子样本"}
              </h3>
              <p className="mt-2 max-w-4xl text-[13px] leading-6 text-[var(--text-secondary)]">
                {shadow.summary ||
                  "用于快速增加历史样本量，辅助规则复盘和阈值校准。"}
              </p>
              {shadow.warning ? (
                <div className="mt-3 rounded-md border border-[color-mix(in_srgb,var(--warning)_24%,transparent)] bg-[color-mix(in_srgb,var(--warning)_8%,transparent)] px-3 py-2 text-[12px] leading-5 text-[var(--text-secondary)]">
                  {shadow.warning}
                </div>
              ) : null}
              <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {cards.length ? (
                  cards.map((card, index) => (
                    <MetricCard
                      key={`${card.label}-${index}`}
                      {...card}
                      value={countText(card.value)}
                      tone={card.tone || "info"}
                      className="min-h-[104px]"
                    />
                  ))
                ) : (
                  <EmptyState>暂无影子样本统计。</EmptyState>
                )}
              </div>
            </div>

            <div className="border-t border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-4 lg:border-l lg:border-t-0">
              <div className="mb-3 flex items-center gap-2">
                <Database size={15} className="text-[var(--text-tertiary)]" />
                <div className="text-sm font-semibold text-[var(--text-primary)]">
                  样本边界
                </div>
              </div>
              <div className="space-y-2">
                <MiniFact
                  label="来源"
                  value={shadow.sample_origin || "historical_shadow"}
                  tone="info"
                />
                <MiniFact
                  label="样本口径"
                  value={shadow.source_lane || "shadow_price_signal_baseline"}
                  tone="watch"
                />
                <MiniFact
                  label="成分股口径"
                  value={
                    shadow.universe_policy || "current_constituents_approx"
                  }
                  tone="warning"
                />
              </div>
              <div className="mt-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2 text-[12px] leading-5 text-[var(--text-secondary)]">
                这组样本用来回答“规则在历史价格形态上大概会怎样”，不写入真实
                Decision Ledger，也不生成今日可执行动作。
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-3 border-t border-[var(--border-subtle)] p-4 xl:grid-cols-4">
            <ShadowCountPanel
              title="样本桶"
              counts={shadow.bucket_counts}
              labels={SHADOW_BUCKET_LABELS}
              empty="暂无样本桶。"
            />
            <ShadowCountPanel
              title="动作口径"
              counts={shadow.action_counts}
              labels={SHADOW_ACTION_LABELS}
              empty="暂无动作统计。"
            />
            <ShadowCountPanel
              title="Outcome"
              counts={shadow.classification_counts}
              labels={SHADOW_OUTCOME_LABELS}
              empty="暂无 outcome。"
            />
            <ShadowCountPanel
              title="形态分布"
              counts={shadow.setup_counts}
              labels={SHADOW_SETUP_LABELS}
              empty="暂无形态分布。"
            />
          </div>
        </>
      ) : (
        <div className="p-4">
          <EmptyState>正在准备历史影子样本。</EmptyState>
        </div>
      )}
    </div>
  );
}

function LedgerHistoryRow({ item }: { item: DecisionLedgerCompactRecord }) {
  return (
    <Link
      href={reviewCaseHref(item.decision_id)}
      className="focus-ring flex min-h-[62px] flex-wrap items-center gap-x-4 gap-y-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 transition-colors hover:border-[var(--border-default)]"
    >
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2 text-[12px] text-[var(--text-primary)]">
          <span className="font-medium">{item.name || item.code}</span>
          <span className="mono text-[11px] text-[var(--text-tertiary)]">
            {item.code}
          </span>
          <span className="text-[11px] text-[var(--text-tertiary)]">
            {item.trade_date}
          </span>
        </div>
        {item.main_conclusion ? (
          <div className="mt-1 line-clamp-1 text-[11px] text-[var(--text-tertiary)]">
            {item.main_conclusion}
          </div>
        ) : null}
      </div>
      <Badge tone="info">{item.lane || "unknown"}</Badge>
      <Badge tone={(item.latest_outcome?.tone as Tone) || "watch"}>
        {reasonLabel(
          item.latest_outcome?.label,
          item.latest_outcome?.label || "待评估",
        )}
      </Badge>
      <ArrowRight size={14} className="text-[var(--text-tertiary)]" />
    </Link>
  );
}

export function HistoricalDecisionLedger() {
  const ledger = useDecisionLedgerRecent(10);
  const data = ledger.data as DecisionLedgerRecentResponse | undefined;
  const items = data?.items || [];

  return (
    <div className="border-t border-[var(--border-subtle)] p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[13px] font-medium text-[var(--text-primary)]">
            最近 10 条决策
          </div>
          <div className="mt-1 line-clamp-1 text-[11px] text-[var(--text-tertiary)]">
            用于追溯原始判断和 outcome，不参与今日队列排序。
          </div>
        </div>
        <button
          type="button"
          className="focus-ring inline-flex items-center gap-1.5 rounded-md border border-[var(--border-subtle)] px-2 py-1 text-[11px] text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
          onClick={() => void ledger.refetch()}
        >
          <RefreshCw
            size={12}
            className={ledger.isFetching ? "animate-spin" : ""}
          />
          重读
        </button>
      </div>
      {ledger.isLoading && !data ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, index) => (
            <SkeletonBlock key={index} className="h-14 w-full" />
          ))}
        </div>
      ) : ledger.isError ? (
        <ErrorState
          message="历史决策流水暂不可用"
          onRetry={() => void ledger.refetch()}
        />
      ) : items.length ? (
        <div className="space-y-2">
          {items.map((item) => (
            <LedgerHistoryRow key={item.decision_id} item={item} />
          ))}
        </div>
      ) : (
        <EmptyState>暂无捕获的决策记录。</EmptyState>
      )}
    </div>
  );
}
