"use client";

import { BarChart3, Database, ShieldAlert, Sparkles, Target } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/badge";
import { EmptyState, ErrorState, SkeletonBlock } from "@/components/data-card";
import { useDecisionLedgerLearningLoop, useDecisionLedgerShadowCalibration } from "@/lib/hooks";
import type {
  DecisionLedgerCalibrationGroup,
  DecisionLedgerCalibrationDetailResponse,
  DecisionLedgerFactorLearningLoop,
  DecisionLedgerFactorStatsRow,
  DecisionLedgerFactorSummaryItem,
  DecisionLedgerReviewCasePattern,
  DecisionLedgerSuggestionCard,
  ShadowCalibrationRow,
  ShadowCalibrationSummary,
} from "@/lib/types";
import {
  countText,
  pct,
  ratePct,
  sampleGuardrailText,
  shadowStatusMeta,
} from "./review-utils";

function factorWindowStats(row?: DecisionLedgerFactorStatsRow, preferred = ["T+10", "T+5", "T+3", "T+1"]) {
  const stats = row?.window_stats || {};
  for (const window of preferred) {
    const item = stats[window];
    if (item && !item.sample_too_small && Number(item.sample_count || 0) > 0) {
      return { window, stats: item };
    }
  }
  for (const window of preferred) {
    const item = stats[window];
    if (item && Number(item.sample_count || 0) > 0) {
      return { window, stats: item };
    }
  }
  return { window: preferred[0], stats: undefined };
}

function ShadowCalibrationPanel({
  shadow,
  loading,
  error,
  fetching,
  onOpen,
  onRetry,
}: {
  shadow?: ShadowCalibrationSummary;
  loading?: boolean;
  error?: boolean;
  fetching?: boolean;
  onOpen: () => void;
  onRetry: () => void;
}) {
  const status = shadowStatusMeta(shadow?.status);
  const cards = shadow?.cards || [];
  const bucketRows = shadow?.bucket_rows || [];

  return (
    <details
      className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)]"
      onToggle={(event) => {
        if (event.currentTarget.open) {
          onOpen();
        }
      }}
    >
      <summary className="focus-ring flex cursor-pointer list-none items-start justify-between gap-2 px-3 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Database size={14} className="shrink-0 text-[var(--text-tertiary)]" />
            <div className="text-[12px] font-medium text-[var(--text-primary)]">
              {shadow?.title || "历史影子校准提示"}
            </div>
          </div>
          <div className="mt-1 line-clamp-2 text-[11px] leading-4 text-[var(--text-tertiary)]">
            {shadow?.summary || "研究样本只辅助提问，不替代真实复盘样本。"}
          </div>
        </div>
        <Badge tone={fetching ? "info" : status.tone}>{fetching ? "读取中" : status.label}</Badge>
      </summary>
      <div className="border-t border-[var(--border-subtle)] p-3">
        {loading && !shadow ? (
          <div className="space-y-2">
            <SkeletonBlock className="h-16 w-full" />
            <SkeletonBlock className="h-16 w-full" />
          </div>
        ) : error ? (
          <ErrorState message="历史影子校准暂不可用" onRetry={onRetry} />
        ) : (
          <>
            {shadow?.warning ? (
              <div className="mb-3 rounded-md border border-[color-mix(in_srgb,var(--warning)_22%,transparent)] bg-[color-mix(in_srgb,var(--warning)_8%,transparent)] px-3 py-2 text-[11px] leading-4 text-[var(--text-secondary)]">
                {shadow.warning}
              </div>
            ) : null}
            {cards.length ? (
              <div className="space-y-2">
                {cards.slice(0, 4).map((card) => <ShadowSuggestionCard key={card.kind} card={card} />)}
              </div>
            ) : (
              <EmptyState>暂无影子校准提示。</EmptyState>
            )}
            {bucketRows.length ? (
              <div className="mt-3 border-t border-[var(--border-subtle)] pt-3">
                <div className="mb-2 text-[11px] font-medium text-[var(--text-tertiary)]">T+5 样本桶</div>
                <div className="space-y-1.5">
                  {bucketRows.slice(0, 3).map((row) => (
                    <ShadowCalibrationRowItem key={`${row.axis}-${row.key}`} row={row} />
                  ))}
                </div>
              </div>
            ) : null}
          </>
        )}
      </div>
    </details>
  );
}

function ShadowSuggestionCard({ card }: { card: DecisionLedgerSuggestionCard }) {
  return (
    <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="line-clamp-1 text-[12px] font-medium text-[var(--text-primary)]">{card.title}</div>
          <div className="mt-1 line-clamp-2 text-[11px] leading-4 text-[var(--text-secondary)]">{card.summary}</div>
        </div>
        <Badge tone={card.tone}>{countText(card.sample_size)}</Badge>
      </div>
      <div className="mt-2 text-[11px] leading-4 text-[var(--text-tertiary)]">{card.action_reason}</div>
    </div>
  );
}

function ShadowCalibrationRowItem({ row }: { row: ShadowCalibrationRow }) {
  const total = Number(row.total || 0);
  const validated = Number(row.validated || 0);
  const support = Number(row.avoided_loss || 0);
  const hasRejectStats = Number(row.avoided_loss || 0) > 0 || Number(row.missed_opportunity || 0) > 0;
  const width = total ? Math.max(4, ((validated + support) / total) * 100) : 0;
  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-3 text-[11px]">
        <span className="truncate text-[var(--text-secondary)]">{row.label || row.key}</span>
        <span className="mono shrink-0 text-[var(--text-tertiary)]">
          {hasRejectStats
            ? `避 ${row.avoided_loss_rate ?? 0}% / 错 ${row.missed_opportunity_rate ?? 0}%`
            : `验 ${row.validated_rate ?? 0}% / 失 ${row.invalidated_rate ?? 0}%`}
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-[var(--bg-tertiary)]">
        <div className="h-full rounded-full bg-[var(--tone-hold)]" style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

function FactorLearningPanel({
  factorLearning,
  loading,
  error,
  onRetry,
}: {
  factorLearning?: DecisionLedgerFactorLearningLoop;
  loading?: boolean;
  error?: boolean;
  onRetry?: () => void;
}) {
  const summary = factorLearning?.learning_summary;
  const best = summary?.best_positive_factors || [];
  const risks = summary?.worst_risk_flags || [];
  const noisy = summary?.noisy_factors || [];
  const buckets = summary?.score_bucket_performance || [];

  return (
    <div className="p-3">
      {loading && !factorLearning ? (
        <div className="space-y-2">
          <SkeletonBlock className="h-16 w-full" />
          <SkeletonBlock className="h-16 w-full" />
        </div>
      ) : error ? (
        <ErrorState message="因子复盘暂不可用" onRetry={onRetry} />
      ) : summary ? (
        <div className="space-y-3">
          <FactorSummaryGroup icon="positive" title="近期有效因子" items={best} empty="暂无达到样本阈值的正向因子。" />
          <FactorSummaryGroup icon="risk" title="伤害收益的风险标签" items={risks} empty="暂无可确认的负向风险标签。" />
          <FactorSummaryGroup icon="noisy" title="样本不足 / 信号混杂" items={noisy} empty="暂无样本不足提示。" />
          <ScoreBucketTable buckets={buckets} />
          <WeightRecommendationList recommendations={summary.recommendations_for_weights || []} />
        </div>
      ) : (
        <EmptyState>暂无因子快照样本。候选捕获后会开始累积。</EmptyState>
      )}
    </div>
  );
}

function FactorLearningDisclosure({
  factorLearning,
  loading,
  fetching,
  error,
  open,
  onOpenChange,
  onRetry,
}: {
  factorLearning?: DecisionLedgerFactorLearningLoop;
  loading?: boolean;
  fetching?: boolean;
  error?: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onRetry?: () => void;
}) {
  const summary = factorLearning?.learning_summary;
  const enoughSamples = Number(summary?.sample_count || 0) >= Number(summary?.min_sample_size || 3);
  const badgeTone = fetching ? "info" : error ? "warning" : summary ? (enoughSamples ? "positive" : "watch") : "stale";
  const badgeText = fetching ? "读取中" : summary ? `样本 ${countText(summary.sample_count)}` : "按需加载";

  return (
    <details
      open={open}
      className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)]"
      onToggle={(event) => onOpenChange(event.currentTarget.open)}
    >
      <summary className="focus-ring flex cursor-pointer list-none items-start justify-between gap-2 px-3 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <BarChart3 size={14} className="shrink-0 text-[var(--text-tertiary)]" />
            <div className="text-[12px] font-medium text-[var(--text-primary)]">因子复盘摘要</div>
          </div>
          <div className="mt-1 line-clamp-2 text-[11px] leading-4 text-[var(--text-tertiary)]">
            {summary?.guardrail?.message || "展开后读取因子表现、Tushare 分桶和人工调权建议。"}
          </div>
        </div>
        <Badge tone={badgeTone}>{badgeText}</Badge>
      </summary>
      <div className="border-t border-[var(--border-subtle)]">
        <FactorLearningPanel factorLearning={factorLearning} loading={loading} error={error} onRetry={onRetry} />
      </div>
    </details>
  );
}

function FactorSummaryGroup({
  title,
  items,
  empty,
  icon,
}: {
  title: string;
  items: DecisionLedgerFactorSummaryItem[];
  empty: string;
  icon: "positive" | "risk" | "noisy";
}) {
  const Icon = icon === "risk" ? ShieldAlert : icon === "positive" ? Sparkles : Target;
  return (
    <div>
      <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-medium text-[var(--text-tertiary)]">
        <Icon size={12} />
        {title}
      </div>
      {items.length ? (
        <div className="space-y-1.5">
          {items.slice(0, 3).map((item) => <FactorSummaryRow key={`${title}-${item.key}-${item.window}`} item={item} />)}
        </div>
      ) : (
        <EmptyState>{empty}</EmptyState>
      )}
    </div>
  );
}

function FactorSummaryRow({ item }: { item: DecisionLedgerFactorSummaryItem }) {
  return (
    <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-[12px] font-medium text-[var(--text-primary)]">{item.label || item.key}</div>
          <div className="mt-1 text-[11px] leading-4 text-[var(--text-tertiary)]">
            {item.window || "-"} · 胜率 {ratePct(item.win_rate)} · 收益 {pct(item.avg_return_pct)} · 超额 {pct(item.avg_excess_return_pct)}
          </div>
        </div>
        <Badge tone={item.sample_too_small ? "warning" : "info"}>{item.sample_too_small ? "小样本" : countText(item.sample_count)}</Badge>
      </div>
    </div>
  );
}

function ScoreBucketTable({ buckets }: { buckets: DecisionLedgerFactorStatsRow[] }) {
  const visible = buckets.slice(0, 4);
  if (!visible.length) {
    return null;
  }
  return (
    <div className="border-t border-[var(--border-subtle)] pt-3">
      <div className="mb-2 text-[11px] font-medium text-[var(--text-tertiary)]">Tushare 分桶表现</div>
      <div className="overflow-x-auto">
        <table className="w-full text-[11px]">
          <thead className="text-[var(--text-tertiary)]">
            <tr>
              <th className="px-2 py-1 text-left">分桶</th>
              <th className="px-2 py-1 text-right">窗口</th>
              <th className="px-2 py-1 text-right">样本</th>
              <th className="px-2 py-1 text-right">胜率</th>
              <th className="px-2 py-1 text-right">超额</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((bucket) => {
              const { window, stats } = factorWindowStats(bucket);
              return (
                <tr key={bucket.key} className="border-t border-[var(--border-subtle)]">
                  <td className="px-2 py-1 text-[var(--text-primary)]">{bucket.label || bucket.key}</td>
                  <td className="px-2 py-1 text-right text-[var(--text-tertiary)]">{window}</td>
                  <td className="px-2 py-1 text-right">{countText(stats?.sample_count)}</td>
                  <td className="px-2 py-1 text-right">{ratePct(stats?.win_rate)}</td>
                  <td className="px-2 py-1 text-right">{pct(stats?.avg_excess_return_pct)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function WeightRecommendationList({ recommendations }: { recommendations: Array<{ target?: string; reason?: string; sample_count?: number; auto_apply?: boolean }> }) {
  if (!recommendations.length) {
    return null;
  }
  return (
    <div className="border-t border-[var(--border-subtle)] pt-3">
      <div className="mb-2 text-[11px] font-medium text-[var(--text-tertiary)]">人工调权建议</div>
      <div className="space-y-1.5">
        {recommendations.slice(0, 3).map((item, index) => (
          <div key={`${item.target}-${index}`} className="rounded-md bg-[var(--bg-primary)] px-3 py-2 text-[11px] leading-4 text-[var(--text-secondary)]">
            <span className="font-medium text-[var(--text-primary)]">{item.target || "全部因子"}</span>
            ：{item.reason || "继续观察。"}
          </div>
        ))}
      </div>
    </div>
  );
}

function PatternCard({ pattern }: { pattern: DecisionLedgerReviewCasePattern }) {
  return (
    <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={pattern.rule_action_allowed ? "positive" : "watch"}>{pattern.evidence_strength_label || "观察假设"}</Badge>
            <Badge tone="info">{pattern.follow_up_status_label || "观察中"}</Badge>
            <Badge tone="warning">样本 {pattern.sample_count}</Badge>
            {pattern.stock_count ? <Badge tone="stale">股票 {pattern.stock_count}</Badge> : null}
          </div>
          <h3 className="mt-2 text-sm font-semibold text-[var(--text-primary)]">
            {pattern.lane || "unknown"} / {pattern.action_label || pattern.action || "unknown"} / {pattern.review_reason_label || "复盘"}
          </h3>
        </div>
        <Badge tone={pattern.rule_action_allowed ? "positive" : "warning"}>
          {pattern.dominant_conclusion_action_label || "待结论"}
        </Badge>
      </div>
      <p className="mt-3 text-[12px] leading-5 text-[var(--text-secondary)]">
        {pattern.learning_hint || pattern.rule_hypothesis || sampleGuardrailText(pattern)}
      </p>
      {pattern.dominant_secondary_cause_labels?.length ? (
        <div className="mt-2 text-[11px] leading-4 text-[var(--text-tertiary)]">
          常见辅助归因：{pattern.dominant_secondary_cause_labels.join("、")}
        </div>
      ) : null}
      <div className="mt-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[11px] leading-4 text-[var(--text-tertiary)]">
        样本强度：{pattern.evidence_strength_detail || sampleGuardrailText(pattern)}
      </div>
    </div>
  );
}

function CalibrationGroupTable({ title, groups }: { title: string; groups: DecisionLedgerCalibrationGroup[] }) {
  const visible = groups.slice(0, 5);
  return (
    <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3">
      <div className="mb-2 text-[12px] font-medium text-[var(--text-primary)]">{title}</div>
      {!visible.length ? (
        <EmptyState>暂无分组样本。</EmptyState>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead className="text-[var(--text-tertiary)]">
              <tr>
                <th className="px-2 py-1 text-left">分组</th>
                <th className="px-2 py-1 text-right">样本</th>
                <th className="px-2 py-1 text-right">失败</th>
                <th className="px-2 py-1 text-right">复盘</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((group) => (
                <tr key={group.key} className="border-t border-[var(--border-subtle)]">
                  <td className="max-w-[150px] truncate px-2 py-1 text-[var(--text-primary)]">{group.label}</td>
                  <td className="px-2 py-1 text-right">{group.total}</td>
                  <td className="px-2 py-1 text-right text-[var(--negative)]">{group.invalidated_rate}%</td>
                  <td className="px-2 py-1 text-right">{group.review_needed}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function LearningPatterns({ data }: { data?: DecisionLedgerCalibrationDetailResponse }) {
  const patterns = data?.review_case_patterns || [];
  const groups = [data?.by_lane || [], data?.by_action || []];
  const [factorLearningOpen, setFactorLearningOpen] = useState(false);
  const learningLoop = useDecisionLedgerLearningLoop({}, { enabled: factorLearningOpen });
  const [shadowOpen, setShadowOpen] = useState(false);
  const shadowCalibration = useDecisionLedgerShadowCalibration({ enabled: shadowOpen });
  const shadow = shadowCalibration.data;

  return (
    <div className="border-t border-[var(--border-subtle)] p-4">
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(340px,0.85fr)]">
        <div className="space-y-3">
          {patterns.length ? (
            patterns.map((pattern) => <PatternCard key={pattern.pattern_id} pattern={pattern} />)
          ) : (
            <EmptyState>还没有保存的 Review Case。完成一条归因后，这里会生成同类样本模式。</EmptyState>
          )}
        </div>
        <div className="grid grid-cols-1 gap-3">
          <FactorLearningDisclosure
            factorLearning={learningLoop.data?.factor_learning_loop}
            loading={learningLoop.isLoading}
            fetching={learningLoop.isFetching}
            error={learningLoop.isError}
            open={factorLearningOpen}
            onOpenChange={setFactorLearningOpen}
            onRetry={() => {
              setFactorLearningOpen(true);
              void learningLoop.refetch();
            }}
          />
          <ShadowCalibrationPanel
            shadow={shadow}
            loading={shadowCalibration.isLoading}
            error={shadowCalibration.isError}
            fetching={shadowCalibration.isFetching}
            onOpen={() => setShadowOpen(true)}
            onRetry={() => {
              setShadowOpen(true);
              void shadowCalibration.refetch();
            }}
          />
          <CalibrationGroupTable title="链路质量分布" groups={groups[0]} />
          <CalibrationGroupTable title="动作质量分布" groups={groups[1]} />
        </div>
      </div>
    </div>
  );
}
