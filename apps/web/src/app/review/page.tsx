"use client";

import {
  ArrowRight,
  BarChart3,
  BookOpenCheck,
  CheckCircle2,
  ClipboardCheck,
  Database,
  ExternalLink,
  FileText,
  LoaderCircle,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  Target,
} from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { Badge } from "@/components/badge";
import { EmptyState, ErrorState, Panel, SkeletonBlock } from "@/components/data-card";
import { EvidencePanel } from "@/components/evidence-panel";
import { MetricCard, MetricSkeleton } from "@/components/metric-card";
import { PageTitle } from "@/components/page-title";
import { RiskAlert } from "@/components/risk-alert";
import {
  useDecisionLedgerCalibration,
  useDecisionLedgerRecent,
  useDecisionLedgerReviewCase,
  useGenerateDecisionLedgerAttributionDraft,
  useReview,
  useRunTask,
  useSaveDecisionLedgerReviewCase,
} from "@/lib/hooks";
import type {
  BasicCard,
  DecisionLedgerAttributionDraft,
  DecisionLedgerCaseRef,
  DecisionLedgerCalibrationGroup,
  DecisionLedgerCalibrationResponse,
  DecisionLedgerCompactRecord,
  DecisionLedgerDetailResponse,
  DecisionLedgerOutcomeEvent,
  DecisionLedgerRecentResponse,
  DecisionLedgerReviewCase,
  DecisionLedgerReviewCaseOption,
  DecisionLedgerReviewCasePattern,
  DecisionLedgerReviewCaseSavePayload,
  DecisionLedgerReviewRecord,
  DecisionLedgerSuggestionCard,
  MetricCardData,
  ReviewData,
  ReviewResearchPanel,
  ShadowCalibrationRow,
  ShadowCalibrationSummary,
  SourceCardData,
  Tone,
} from "@/lib/types";
import { cn } from "@/lib/utils";

const REVIEW_STATUS_META: Record<string, { label: string; tone: Tone | string }> = {
  pending_outcome: { label: "等待结果", tone: "watch" },
  pending_execution: { label: "等待执行", tone: "warning" },
  ready_review: { label: "待归因", tone: "warning" },
  reviewed: { label: "已归因", tone: "positive" },
  blocked_data: { label: "数据阻塞", tone: "risk" },
  low_priority: { label: "低信号", tone: "stale" },
};

const REVIEW_REASON_LABELS: Record<string, string> = {
  invalidated: "判断失效",
  execution_gap: "执行落差",
  missed_opportunity: "错过机会",
  data_issue: "数据问题",
  blocked_data: "数据阻塞",
  data_blocked: "数据阻塞",
  superseded: "判断被替代",
  pending_outcome: "等待结果",
  pending_execution: "等待执行",
  reviewed: "已归因",
  low_priority: "低信号",
};

const PRIORITY_TONE: Record<string, Tone | string> = {
  critical: "risk",
  high: "warning",
  medium: "watch",
  low: "stale",
};

const FALLBACK_PRIMARY_CAUSES: DecisionLedgerReviewCaseOption[] = [
  { value: "too_strict", label: "判断过严" },
  { value: "too_loose", label: "判断过松" },
  { value: "signal_distortion", label: "信号失真" },
  { value: "execution_gap", label: "执行未跟上" },
  { value: "data_unavailable", label: "数据不可用" },
  { value: "insufficient_sample", label: "样本不足，暂不改规则" },
  { value: "rule_valid_noise", label: "规则有效，个例噪音" },
];

const FALLBACK_SECONDARY_CAUSES: DecisionLedgerReviewCaseOption[] = [
  { value: "volume_too_conservative", label: "量能判断偏保守" },
  { value: "capital_flow_filter_strict", label: "主力资金过滤过严" },
  { value: "market_regime_gate_strict", label: "环境阀门过严" },
  { value: "fundamental_weight_low", label: "个股基本面权重不足" },
  { value: "open_behavior_misread", label: "开盘行为误判" },
  { value: "risk_condition_not_triggered", label: "风险条件未发生" },
  { value: "followup_event_driven", label: "后续事件驱动" },
  { value: "liquidity_insufficient", label: "流动性不足" },
  { value: "data_delay", label: "数据延迟" },
];

const FALLBACK_CONCLUSION_ACTIONS: DecisionLedgerReviewCaseOption[] = [
  { value: "keep_rule", label: "保持规则" },
  { value: "loosen_filter", label: "调宽过滤条件" },
  { value: "tighten_filter", label: "收紧过滤条件" },
  { value: "add_guardrail", label: "增加护栏" },
  { value: "wait_more_samples", label: "等更多样本" },
  { value: "fix_data_pipeline", label: "修复数据链路" },
  { value: "fix_execution_pipeline", label: "修复执行链路" },
];

const FALLBACK_FOLLOW_UP_STATUSES: DecisionLedgerReviewCaseOption[] = [
  { value: "observing", label: "观察中" },
  { value: "sample_insufficient", label: "样本不足" },
  { value: "preliminary_effective", label: "初步有效" },
  { value: "invalid", label: "无效" },
  { value: "adopted", label: "已采纳" },
  { value: "rolled_back", label: "已回滚" },
];

const DIRECT_RULE_ACTIONS = new Set(["loosen_filter", "tighten_filter", "add_guardrail"]);
const PRIMARY_ACTION_CLASS = "focus-ring prism-btn prism-btn-primary";

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

function cleanParam(value: string | null) {
  return value?.trim() || undefined;
}

function reviewStatusMeta(status?: string) {
  return REVIEW_STATUS_META[status || ""] || { label: status || "未知", tone: "stale" };
}

function priorityTone(label?: string) {
  return PRIORITY_TONE[label || ""] || "stale";
}

function reasonLabel(key?: string, fallback?: string) {
  return REVIEW_REASON_LABELS[key || ""] || fallback || key || "待归因";
}

function reviewCaseHref(decisionId?: string | null) {
  return decisionId ? `/review?case=${encodeURIComponent(decisionId)}` : "/review";
}

function pct(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return `${Number(value).toFixed(2)}%`;
}

function countText(value?: number | string) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return String(value ?? "-");
  }
  return numeric.toLocaleString("zh-CN");
}

function shadowKeyLabel(labels: Record<string, string>, key: string) {
  return labels[key] || key.replace(/_/g, " ");
}

function shadowStatusMeta(status?: string) {
  if (status === "ready") {
    return { label: "样本可用", tone: "positive" };
  }
  if (status === "partial") {
    return { label: "部分可用", tone: "warning" };
  }
  if (status === "missing") {
    return { label: "未生成", tone: "stale" };
  }
  return { label: status || "未知", tone: "info" };
}

function latestOutcomeEvent(decision?: DecisionLedgerDetailResponse): DecisionLedgerOutcomeEvent | undefined {
  const events = decision?.outcome_events || [];
  const rank: Record<string, number> = { "T+5": 3, "T+3": 2, "T+1": 1 };
  return [...events].sort((a, b) => {
    const windowDiff = (rank[b.window || ""] || 0) - (rank[a.window || ""] || 0);
    if (windowDiff) {
      return windowDiff;
    }
    return String(b.evaluated_at || "").localeCompare(String(a.evaluated_at || ""));
  })[0];
}

function topQueueItem(data?: DecisionLedgerCalibrationResponse) {
  return (data?.needs_review || data?.review_queue || []).find((item) =>
    ["ready_review", "blocked_data"].includes(String(item.review_status || "")),
  );
}

function sampleGuardrailText(item?: { sample_count?: number } | null) {
  const count = Number(item?.sample_count || 1);
  if (count >= 10) {
    return "10 条及以上：策略级校准建议，仍需验证状态。";
  }
  if (count >= 5) {
    return "5 条以上：可提出规则调整建议，必须持续验证。";
  }
  if (count >= 2) {
    return "2-4 条：待验证模式，继续观察后续样本。";
  }
  return "1 条：只能生成观察假设，不能直接修改规则。";
}

function optionLabel(options: DecisionLedgerReviewCaseOption[], value?: string) {
  if (!value) {
    return "-";
  }
  return options.find((option) => option.value === value)?.label || value;
}

function optionLabels(options: DecisionLedgerReviewCaseOption[], values?: string[]) {
  const labels = (values || []).map((value) => optionLabel(options, value)).filter(Boolean);
  return labels.length ? labels.join("、") : "无";
}

function confidenceLabel(value?: string) {
  const labels: Record<string, string> = {
    low: "低",
    medium: "中",
    high: "高",
  };
  return labels[value || ""] || value || "-";
}

function draftStatusLabel(status: string) {
  const labels: Record<string, string> = {
    idle: "未生成",
    generating: "生成中",
    generated: "已生成",
    failed: "生成失败",
    adopted: "已采纳草稿",
    modified: "人工已修改",
  };
  return labels[status] || "未生成";
}

function draftStatusTone(status: string): Tone | string {
  if (status === "failed") {
    return "risk";
  }
  if (status === "modified") {
    return "warning";
  }
  if (status === "adopted" || status === "generated") {
    return "positive";
  }
  if (status === "generating") {
    return "info";
  }
  return "stale";
}

function caseRefLabel(ref: DecisionLedgerCaseRef) {
  const stock = ref.stock_name || ref.stock_code || "历史样本";
  const cause = ref.primary_cause_label || ref.primary_cause || "未归因";
  const date = ref.trade_date ? `${ref.trade_date} · ` : "";
  return `${date}${stock} · ${cause}`;
}

function shadowRefLabel(ref: ShadowCalibrationRow) {
  if (ref.title) {
    return ref.title;
  }
  const label = ref.label || ref.key || "影子样本";
  const windowLabel = ref.window || "T+5";
  return `${windowLabel} ${label} · 样本 ${countText(ref.total)}`;
}

function shadowRefDetail(ref: ShadowCalibrationRow) {
  const hasRejectStats = (ref.avoided_loss || 0) > 0 || (ref.missed_opportunity || 0) > 0;
  const parts = hasRejectStats
    ? [`避亏 ${ref.avoided_loss_rate ?? 0}%`, `错过 ${ref.missed_opportunity_rate ?? 0}%`]
    : [`验证 ${ref.validated_rate ?? 0}%`, `失效 ${ref.invalidated_rate ?? 0}%`];
  parts.push(`均值 ${pct(ref.avg_return_pct)}`);
  return parts.join(" · ");
}

function SummaryPill({ label, value, tone = "info" }: { label: string; value: string | number; tone?: Tone | string }) {
  return (
    <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
      <div className="text-[11px] text-[var(--text-tertiary)]">{label}</div>
      <div className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
        <span style={{ color: `var(--${tone})` }}>{value}</span>
      </div>
    </div>
  );
}

function DecisionLedgerHero({
  data,
  loading,
  onRefetch,
  fetching,
}: {
  data?: DecisionLedgerCalibrationResponse;
  loading: boolean;
  onRefetch: () => void;
  fetching: boolean;
}) {
  const workbench = data?.review_workbench;
  const top = topQueueItem(data);
  const needsReview = data?.needs_review_count ?? 0;
  const reviewed = data?.reviewed_case_count ?? 0;
  const pending = workbench?.pending_count ?? 0;
  const blocked = workbench?.blocked_data_count ?? 0;

  if (loading && !data) {
    return <SkeletonBlock className="h-72 w-full" />;
  }

  return (
    <section className="mb-7 overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)]">
      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.25fr)_360px]">
        <div className="p-5 sm:p-6">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Badge tone={needsReview ? "warning" : "positive"}>{needsReview ? "需要复盘" : "队列清爽"}</Badge>
            <Badge tone="info">{data?.from_date || "-"} 至 {data?.to_date || "-"}</Badge>
            <Badge tone="watch">已归因 {reviewed}</Badge>
          </div>
          <h2 className="text-[clamp(26px,4vw,44px)] font-semibold leading-tight tracking-normal text-[var(--text-primary)]">
            需要复盘 {needsReview} 条
          </h2>
          {top ? (
            <div className="mt-4 max-w-3xl">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-lg font-semibold text-[var(--text-primary)]">{top.name || top.code}</span>
                <span className="mono text-sm text-[var(--text-tertiary)]">{top.code}</span>
                <Badge tone={priorityTone(top.priority_label)}>
                  P{top.priority_score ?? 0} {top.priority_label || "low"}
                </Badge>
              </div>
              <p className="mt-2 text-[14px] leading-6 text-[var(--text-secondary)]">
                原因：{reasonLabel(top.review_reason_key, top.review_reason)}。当前建议：先完成归因，生成“是否过度保守/过度宽松”的可追踪假设，不直接改规则。
              </p>
              <div className="mt-3 rounded-md border border-[color-mix(in_srgb,var(--warning)_24%,transparent)] bg-[color-mix(in_srgb,var(--warning)_8%,transparent)] px-3 py-2 text-[12px] leading-5 text-[var(--text-secondary)]">
                {sampleGuardrailText(null)}
              </div>
              <div className="mt-5 flex flex-wrap gap-2">
                <Link
                  href={reviewCaseHref(top.decision_id)}
                  className={PRIMARY_ACTION_CLASS}
                >
                  <ClipboardCheck size={15} />
                  开始归因
                </Link>
                <a
                  href="#review-queue"
                  className="focus-ring inline-flex min-h-10 items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                >
                  查看队列
                  <ArrowRight size={13} />
                </a>
              </div>
            </div>
          ) : (
            <div className="mt-4 max-w-3xl">
              <p className="text-[14px] leading-6 text-[var(--text-secondary)]">
                当前没有必须立即归因的成熟失败样本。可以查看已归因模式、等待 outcome 成熟，或到底部证据区核对数据状态。
              </p>
              <div className="mt-5 flex flex-wrap gap-2">
                <a
                  href="#learning-patterns"
                  className={PRIMARY_ACTION_CLASS}
                >
                  <Sparkles size={15} />
                  查看学习模式
                </a>
                <a
                  href="#evidence-status"
                  className="focus-ring inline-flex min-h-10 items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                >
                  证据与数据状态
                  <ArrowRight size={13} />
                </a>
              </div>
            </div>
          )}
        </div>
        <div className="border-t border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-5 lg:border-l lg:border-t-0">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">Learning State</div>
              <div className="mt-1 text-sm font-semibold text-[var(--text-primary)]">{workbench?.top_priority_reason || "暂无优先风险"}</div>
            </div>
            <button
              type="button"
              className="focus-ring inline-flex h-9 w-9 items-center justify-center rounded-md border border-[var(--border-subtle)] text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
              onClick={onRefetch}
              title="重读 Decision Ledger"
            >
              <RefreshCw size={15} className={fetching ? "animate-spin" : ""} />
            </button>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <SummaryPill label="待归因" value={needsReview} tone={needsReview ? "warning" : "positive"} />
            <SummaryPill label="数据阻塞" value={blocked} tone={blocked ? "risk" : "positive"} />
            <SummaryPill label="待成熟" value={pending} tone={pending ? "watch" : "positive"} />
            <SummaryPill label="已归因" value={reviewed} tone="info" />
          </div>
          <div className="mt-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2 text-[12px] leading-5 text-[var(--text-secondary)]">
            下一步：{top ? "处理最高优先级样本，保存结构化 Review Case。" : workbench?.next_best_action || "继续积累样本。"}
          </div>
        </div>
      </div>
    </section>
  );
}

function ReviewQueue({
  data,
  loading,
  error,
  onRetry,
}: {
  data?: DecisionLedgerCalibrationResponse;
  loading: boolean;
  error: boolean;
  onRetry: () => void;
}) {
  const readyItems = (data?.review_queue || []).filter((item) =>
    ["ready_review", "blocked_data"].includes(String(item.review_status || "")),
  );
  const pendingItems = data?.pending_reviews || [];

  return (
    <section id="review-queue" className="mb-7 scroll-mt-6">
      <Panel title="今日复盘队列" eyebrow="Decision Ledger">
        {error ? (
          <ErrorState message="Decision Ledger 队列暂不可用" onRetry={onRetry} />
        ) : loading && !data ? (
          <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
            {Array.from({ length: 2 }).map((_, index) => (
              <SkeletonBlock key={index} className="h-44 w-full" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(340px,0.8fr)]">
            <div className="space-y-3">
              {readyItems.length ? (
                readyItems.map((item) => <ReviewQueueCard key={item.decision_id} item={item} />)
              ) : (
                <EmptyState>没有成熟且必须优先归因的决策样本。</EmptyState>
              )}
            </div>
            <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3">
              <div className="mb-3 flex items-center justify-between gap-3">
                <div>
                  <div className="text-[12px] font-medium text-[var(--text-primary)]">待成熟 / 补证据</div>
                  <div className="mt-1 text-[11px] text-[var(--text-tertiary)]">缺 outcome 或 execution 的样本先不做规则判断。</div>
                </div>
                <Badge tone={pendingItems.length ? "watch" : "positive"}>{pendingItems.length}</Badge>
              </div>
              <div className="space-y-2">
                {pendingItems.length ? pendingItems.slice(0, 5).map((item) => (
                  <PendingQueueRow key={item.decision_id} item={item} />
                )) : <EmptyState>当前没有待成熟样本。</EmptyState>}
              </div>
            </div>
          </div>
        )}
      </Panel>
    </section>
  );
}

function ReviewQueueCard({ item }: { item: DecisionLedgerReviewRecord }) {
  const status = reviewStatusMeta(item.review_status);
  const outcomeLabel = item.latest_outcome?.label || item.outcome_status || "pending";
  return (
    <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-base font-semibold text-[var(--text-primary)]">{item.name || item.code}</span>
            <span className="mono text-[12px] text-[var(--text-tertiary)]">{item.code}</span>
            <span className="text-[12px] text-[var(--text-tertiary)]">{item.trade_date}</span>
            <Badge tone={status.tone}>{status.label}</Badge>
          </div>
          <p className="mt-2 line-clamp-2 text-[13px] leading-5 text-[var(--text-secondary)]">
            {item.main_conclusion || "原始判断摘要缺失。"}
          </p>
        </div>
        <Badge tone={priorityTone(item.priority_label)}>
          P{item.priority_score ?? 0} {item.priority_label || "low"}
        </Badge>
      </div>
      <div className="mt-4 grid grid-cols-1 gap-2 md:grid-cols-3">
        <MiniFact label="原始动作" value={item.action_label || item.action || "-"} />
        <MiniFact label="最新 outcome" value={`${item.latest_outcome?.window || ""} ${reasonLabel(outcomeLabel, outcomeLabel)}`} tone={item.outcome_tone || item.latest_outcome?.tone || "watch"} />
        <MiniFact label="复盘原因" value={reasonLabel(item.review_reason_key, item.review_reason)} tone="warning" />
      </div>
      <div className="mt-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[12px] leading-5 text-[var(--text-secondary)]">
        建议下一步：{item.next_action_reason || "开始人工归因，保存结构化 Review Case。"}
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <Link
          href={reviewCaseHref(item.decision_id)}
          className="focus-ring prism-btn prism-btn-primary prism-btn-sm"
        >
          <ClipboardCheck size={14} />
          开始归因
        </Link>
        {item.code ? (
          <Link
            href={`/stock/${encodeURIComponent(item.code)}?tab=${encodeURIComponent("决策")}`}
            className="focus-ring inline-flex min-h-9 items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
          >
            查看原始决策
            <ArrowRight size={13} />
          </Link>
        ) : null}
        <Link
          href={`${reviewCaseHref(item.decision_id)}#review-case-workbench`}
          className="focus-ring inline-flex min-h-9 items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
        >
          查看后续走势
          <BarChart3 size={13} />
        </Link>
      </div>
    </div>
  );
}

function PendingQueueRow({ item }: { item: DecisionLedgerReviewRecord }) {
  const status = reviewStatusMeta(item.review_status);
  return (
    <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 text-[12px] text-[var(--text-primary)]">
            <span className="font-medium">{item.name || item.code}</span>
            <span className="mono text-[11px] text-[var(--text-tertiary)]">{item.code}</span>
            <Badge tone={status.tone}>{status.label}</Badge>
            {item.is_overdue ? <Badge tone="risk">已逾期</Badge> : null}
          </div>
          <div className="mt-1 text-[11px] leading-4 text-[var(--text-tertiary)]">{item.maturity_label || "等待 outcome 成熟"}</div>
        </div>
        <Badge tone={priorityTone(item.priority_label)}>P{item.priority_score ?? 0}</Badge>
      </div>
    </div>
  );
}

function HistoricalShadowReplay({ review }: { review?: ReviewData }) {
  const shadow = review?.shadow_replay;
  if (!shadow) {
    return null;
  }

  const status = shadowStatusMeta(shadow.status);
  const cards = shadow.cards || [];
  const artifacts = shadow.artifacts || [];
  const report = artifacts.find((item) => String(item.title || "").includes("报告")) || artifacts[0];

  return (
    <section id="historical-shadow-samples" className="mb-7 scroll-mt-6">
      <Panel
        title="历史影子样本"
        eyebrow="Research sample lane"
        action={
          report?.url ? (
            <a
              href={report.url}
              target="_blank"
              rel="noreferrer"
              className="focus-ring inline-flex items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-1.5 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            >
              打开报告
              <ExternalLink size={13} />
            </a>
          ) : null
        }
      >
        <div className="overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)]">
          <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_360px]">
            <div className="p-4 sm:p-5">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <Badge tone={status.tone}>{status.label}</Badge>
                <Badge tone="info">{shadow.start_date || "-"} 至 {shadow.end_date || "-"}</Badge>
                <Badge tone="watch">{shadow.source_lane || "shadow_price_signal_baseline"}</Badge>
              </div>
              <h3 className="text-lg font-semibold text-[var(--text-primary)]">
                {shadow.title || "2025 价格影子样本"}
              </h3>
              <p className="mt-2 max-w-4xl text-[13px] leading-6 text-[var(--text-secondary)]">
                {shadow.summary || "用于快速增加历史样本量，辅助规则复盘和阈值校准。"}
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
                <div className="text-sm font-semibold text-[var(--text-primary)]">样本边界</div>
              </div>
              <div className="space-y-2">
                <MiniFact label="来源" value={shadow.sample_origin || "historical_shadow"} tone="info" />
                <MiniFact label="样本口径" value={shadow.source_lane || "shadow_price_signal_baseline"} tone="watch" />
                <MiniFact label="成分股口径" value={shadow.universe_policy || "current_constituents_approx"} tone="warning" />
              </div>
              <div className="mt-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2 text-[12px] leading-5 text-[var(--text-secondary)]">
                这组样本用来回答“规则在历史价格形态上大概会怎样”，不写入真实 Decision Ledger，也不生成今日可执行动作。
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-3 border-t border-[var(--border-subtle)] p-4 xl:grid-cols-4">
            <ShadowCountPanel title="样本桶" counts={shadow.bucket_counts} labels={SHADOW_BUCKET_LABELS} empty="暂无样本桶。" />
            <ShadowCountPanel title="动作口径" counts={shadow.action_counts} labels={SHADOW_ACTION_LABELS} empty="暂无动作统计。" />
            <ShadowCountPanel title="Outcome" counts={shadow.classification_counts} labels={SHADOW_OUTCOME_LABELS} empty="暂无 outcome。" />
            <ShadowCountPanel title="形态分布" counts={shadow.setup_counts} labels={SHADOW_SETUP_LABELS} empty="暂无形态分布。" />
          </div>
        </div>
      </Panel>
    </section>
  );
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
  const entries = Object.entries(counts || {}).sort(([, left], [, right]) => Number(right) - Number(left));
  const total = entries.reduce((sum, [, value]) => sum + Number(value || 0), 0);

  return (
    <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3">
      <div className="mb-2 text-[12px] font-medium text-[var(--text-primary)]">{title}</div>
      {entries.length ? (
        <div className="space-y-2">
          {entries.slice(0, 5).map(([key, value]) => {
            const width = total ? Math.max(5, (Number(value || 0) / total) * 100) : 0;
            return (
              <div key={key}>
                <div className="mb-1 flex items-center justify-between gap-3 text-[11px]">
                  <span className="truncate text-[var(--text-secondary)]">{shadowKeyLabel(labels, key)}</span>
                  <span className="mono shrink-0 text-[var(--text-tertiary)]">{countText(value)}</span>
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

function MiniFact({ label, value, tone = "info" }: { label: string; value: string; tone?: Tone | string }) {
  return (
    <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
      <div className="text-[11px] text-[var(--text-tertiary)]">{label}</div>
      <div className="mt-1 line-clamp-2 text-[12px] font-medium text-[var(--text-primary)]">
        <Badge tone={tone}>{value}</Badge>
      </div>
    </div>
  );
}

function ReviewCaseWorkspace({ decisionId }: { decisionId: string }) {
  const workbench = useDecisionLedgerReviewCase(decisionId, Boolean(decisionId));
  const saveMutation = useSaveDecisionLedgerReviewCase();
  const draftMutation = useGenerateDecisionLedgerAttributionDraft();
  const data = workbench.data;
  const decision = data?.decision;
  const learning = data?.learning_record;
  const existingCase = data?.review_case || null;
  const outcome = latestOutcomeEvent(decision);
  const [primaryCause, setPrimaryCause] = useState("insufficient_sample");
  const [secondaryCauses, setSecondaryCauses] = useState<string[]>([]);
  const [reviewNote, setReviewNote] = useState("");
  const [conclusionAction, setConclusionAction] = useState("wait_more_samples");
  const [ruleHypothesis, setRuleHypothesis] = useState("");
  const [followUpStatus, setFollowUpStatus] = useState("sample_insufficient");
  const [followUpDueAt, setFollowUpDueAt] = useState("");
  const [feedback, setFeedback] = useState("");
  const [aiDraft, setAiDraft] = useState<DecisionLedgerAttributionDraft | null>(null);
  const [draftStatus, setDraftStatus] = useState("idle");
  const [draftFeedback, setDraftFeedback] = useState("");

  useEffect(() => {
    if (existingCase) {
      setPrimaryCause(existingCase.primary_cause || "insufficient_sample");
      setSecondaryCauses(existingCase.secondary_causes || []);
      setReviewNote(existingCase.review_note || "");
      setConclusionAction(existingCase.conclusion_action || "wait_more_samples");
      setRuleHypothesis(existingCase.rule_hypothesis || "");
      setFollowUpStatus(existingCase.follow_up_status || "sample_insufficient");
      setFollowUpDueAt(existingCase.follow_up_due_at || "");
      setAiDraft(existingCase.ai_draft || null);
      setDraftStatus(existingCase.ai_draft ? (Object.keys(existingCase.human_overrides || {}).length ? "modified" : "adopted") : "idle");
      return;
    }
    const reason = learning?.review_reason_key;
    setPrimaryCause(reason === "execution_gap" ? "execution_gap" : reason === "data_issue" ? "data_unavailable" : "insufficient_sample");
    setSecondaryCauses([]);
    setReviewNote("");
    setConclusionAction("wait_more_samples");
    setRuleHypothesis("");
    setFollowUpStatus("sample_insufficient");
    setFollowUpDueAt("");
    setAiDraft(null);
    setDraftStatus("idle");
  }, [existingCase, learning?.review_reason_key]);

  const options = data?.options || {};
  const primaryOptions = options.primary_causes?.length ? options.primary_causes : FALLBACK_PRIMARY_CAUSES;
  const secondaryOptions = options.secondary_causes?.length ? options.secondary_causes : FALLBACK_SECONDARY_CAUSES;
  const conclusionOptions = options.conclusion_actions?.length ? options.conclusion_actions : FALLBACK_CONCLUSION_ACTIONS;
  const followUpOptions = options.follow_up_statuses?.length ? options.follow_up_statuses : FALLBACK_FOLLOW_UP_STATUSES;
  const sampleCount = existingCase?.sample_count || data?.guardrail?.sample_count || 1;
  const directRuleSelected = DIRECT_RULE_ACTIONS.has(conclusionAction);

  function markHumanEdited() {
    if (aiDraft && ["generated", "adopted"].includes(draftStatus)) {
      setDraftStatus("modified");
    }
  }

  function applyDraft(draft: DecisionLedgerAttributionDraft, status = "adopted") {
    setPrimaryCause(draft.primary_cause || "insufficient_sample");
    setSecondaryCauses(draft.secondary_causes || []);
    setReviewNote(draft.review_note || "");
    setConclusionAction(draft.conclusion_action || "wait_more_samples");
    setRuleHypothesis(draft.rule_hypothesis || "");
    setFollowUpStatus(draft.follow_up_status || "sample_insufficient");
    setAiDraft(draft);
    setDraftStatus(status);
  }

  function generateDraft() {
    setDraftFeedback("");
    setFeedback("");
    setDraftStatus("generating");
    draftMutation.mutate(decisionId, {
      onSuccess: (response) => {
        applyDraft(response.draft, "adopted");
        setDraftFeedback(response.draft.fallback_reason ? "已使用本地启发式草稿预填。" : "已生成并预填人工归因。");
      },
      onError: (error) => {
        setDraftStatus("failed");
        setDraftFeedback(error instanceof Error ? error.message : "AI 预归因生成失败。");
      },
    });
  }

  function toggleSecondary(value: string) {
    markHumanEdited();
    setSecondaryCauses((current) =>
      current.includes(value) ? current.filter((item) => item !== value) : [...current, value],
    );
  }

  function saveCase() {
    setFeedback("");
    const payload: DecisionLedgerReviewCaseSavePayload = {
      primary_cause: primaryCause,
      secondary_causes: secondaryCauses,
      review_note: reviewNote,
      conclusion_action: conclusionAction,
      rule_hypothesis: ruleHypothesis,
      follow_up_status: followUpStatus,
      follow_up_due_at: followUpDueAt || undefined,
      ai_draft: aiDraft || undefined,
      human_final: {
        primary_cause: primaryCause,
        secondary_causes: secondaryCauses,
        review_note: reviewNote,
        conclusion_action: conclusionAction,
        rule_hypothesis: ruleHypothesis,
        follow_up_status: followUpStatus,
        follow_up_due_at: followUpDueAt || undefined,
      },
      attribution_confidence: aiDraft?.confidence,
      evidence_refs: aiDraft?.evidence || [],
      human_check_required: aiDraft?.human_check_required || [],
      similar_case_refs: aiDraft?.similar_case_refs || [],
      shadow_sample_refs: aiDraft?.shadow_sample_refs || [],
    };
    saveMutation.mutate(
      { decisionId, payload },
      {
        onSuccess: (response) => {
          setFeedback(`已保存 Review Case：${response.review_case.evidence_strength_label || "观察假设"}。`);
        },
        onError: (error) => {
          setFeedback(error instanceof Error ? error.message : "保存失败。");
        },
      },
    );
  }

  if (workbench.isLoading && !data) {
    return (
      <section className="mb-7">
        <SkeletonBlock className="h-[520px] w-full" />
      </section>
    );
  }

  if (workbench.isError || !data || !decision) {
    return (
      <section className="mb-7">
        <ErrorState message="Review Case 工作台暂不可用" onRetry={() => void workbench.refetch()} />
      </section>
    );
  }

  return (
    <section className="mb-7 scroll-mt-6" id="review-case-workbench">
      <Panel
        title="单条 Review Case 工作台"
        eyebrow="Attribution"
        action={
          <Link
            href="/review"
            className="focus-ring inline-flex items-center gap-1.5 rounded-md border border-[var(--border-subtle)] px-2.5 py-1.5 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
          >
            返回队列
          </Link>
        }
      >
        <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.15fr)_430px]">
          <div className="space-y-4">
            <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-4">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <Badge tone={reviewStatusMeta(learning?.review_status).tone}>{reviewStatusMeta(learning?.review_status).label}</Badge>
                <Badge tone="info">{decision.trade_date}</Badge>
                <Badge tone={learning?.outcome_tone || "watch"}>{reasonLabel(learning?.review_reason_key, learning?.review_reason)}</Badge>
              </div>
              <h2 className="text-2xl font-semibold leading-tight text-[var(--text-primary)]">
                {decision.stock?.name || learning?.name || decision.stock?.code}
                <span className="mono ml-2 text-base text-[var(--text-tertiary)]">{decision.stock?.code}</span>
              </h2>
              <p className="mt-2 text-[13px] leading-6 text-[var(--text-secondary)]">
                {learning?.next_action_reason || "先完成归因，保存结构化 Review Case，再让同类样本进入模式聚合。"}
              </p>
              <div className="mt-3 rounded-md border border-[color-mix(in_srgb,var(--warning)_24%,transparent)] bg-[color-mix(in_srgb,var(--warning)_8%,transparent)] px-3 py-2 text-[12px] leading-5 text-[var(--text-secondary)]">
                {existingCase?.evidence_strength_detail || data.guardrail?.detail || sampleGuardrailText(existingCase)}
              </div>
            </div>

            <WorkbenchSection icon={Target} title="当时我为什么这么判断">
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <TextFact label="原始结论" value={decision.recommendation?.main_conclusion || "-"} />
                <TextFact label="推荐动作" value={decision.recommendation?.action_label || decision.recommendation?.action || "-"} />
                <TextFact label="触发信号" value={decision.recommendation?.trigger_condition || "-"} />
                <TextFact label="风险条件" value={decision.recommendation?.risk_summary || decision.recommendation?.stop_condition || "-"} />
                <TextFact label="数据新鲜度" value={`${decision.evidence_snapshot?.data_trade_date || "-"} · ${decision.evidence_snapshot?.readiness_mode || "-"}`} />
                <TextFact label="所处链路" value={`${decision.source?.lane || "-"} / ${decision.source?.surface || "-"}`} />
              </div>
            </WorkbenchSection>

            <WorkbenchSection icon={BarChart3} title="后来市场发生了什么">
              <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                {(decision.outcome_events || []).map((event) => (
                  <OutcomeCard key={event.event_id || event.window} event={event} />
                ))}
                {!decision.outcome_events?.length ? <EmptyState>暂无 outcome。</EmptyState> : null}
              </div>
            </WorkbenchSection>

            <WorkbenchSection icon={ShieldAlert} title="差异在哪里">
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <TextFact label="原始担忧是否发生" value={outcome?.boundary_checks ? "查看 boundary_checks；当前以人工核对为准" : "暂无 boundary 证据"} />
                <TextFact label="触发条件是否失效" value={outcome?.classification?.summary || learning?.review_reason || "-"} />
                <TextFact label="风险过滤是否过严" value={learning?.review_reason_key === "missed_opportunity" ? "可能过严，但单样本只能形成观察假设。" : "需要结合归因判断。"} />
                <TextFact label="执行/数据差异" value={learning?.execution_status === "missing" ? "缺执行记录" : outcome?.quality?.data_issue || "未见明确数据阻塞"} />
              </div>
            </WorkbenchSection>
          </div>

          <div className="space-y-4">
            <AttributionDraftCard
              draft={aiDraft}
              status={draftStatus}
              feedback={draftFeedback}
              primaryOptions={primaryOptions}
              secondaryOptions={secondaryOptions}
              conclusionOptions={conclusionOptions}
              onGenerate={generateDraft}
              onAdopt={() => {
                if (aiDraft) {
                  applyDraft(aiDraft, "adopted");
                  setDraftFeedback("已采纳草稿。");
                }
              }}
              onClear={() => {
                setAiDraft(null);
                setDraftStatus("idle");
                setDraftFeedback("已清空草稿。");
              }}
              isGenerating={draftMutation.isPending || draftStatus === "generating"}
            />
            <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-4">
              <div className="mb-3 flex items-center gap-2">
                <ClipboardCheck size={16} className="text-[var(--text-tertiary)]" />
                <h3 className="text-sm font-semibold text-[var(--text-primary)]">人工归因</h3>
              </div>
              <OptionGrid
                label="主归因"
                options={primaryOptions}
                value={primaryCause}
                onChange={(value) => {
                  markHumanEdited();
                  setPrimaryCause(value);
                }}
              />
              <CheckboxGrid
                label="辅助归因"
                options={secondaryOptions}
                values={secondaryCauses}
                onToggle={toggleSecondary}
              />
              <label className="mt-4 block">
                <span className="text-[12px] font-medium text-[var(--text-primary)]">复盘备注</span>
                <textarea
                  value={reviewNote}
                  onChange={(event) => {
                    markHumanEdited();
                    setReviewNote(event.target.value);
                  }}
                  className="focus-ring mt-2 min-h-24 w-full rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[13px] leading-5 text-[var(--text-primary)] outline-none"
                  placeholder="一句话说明这次判断错在哪里，或者为什么暂不改规则。"
                />
              </label>
            </div>

            <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-4">
              <div className="mb-3 flex items-center gap-2">
                <BookOpenCheck size={16} className="text-[var(--text-tertiary)]" />
                <h3 className="text-sm font-semibold text-[var(--text-primary)]">沉淀动作</h3>
              </div>
              <OptionGrid
                label="结论动作"
                options={conclusionOptions}
                value={conclusionAction}
                onChange={(value) => {
                  markHumanEdited();
                  setConclusionAction(value);
                }}
              />
              {directRuleSelected && sampleCount < 5 ? (
                <div className="mt-3 rounded-md border border-[color-mix(in_srgb,var(--warning)_24%,transparent)] bg-[color-mix(in_srgb,var(--warning)_8%,transparent)] px-3 py-2 text-[12px] leading-5 text-[var(--text-secondary)]">
                  当前同类样本少于 5 条；保存后只会生成观察/验证假设，不会生成可执行规则修改。
                </div>
              ) : null}
              <label className="mt-4 block">
                <span className="text-[12px] font-medium text-[var(--text-primary)]">规则假设</span>
                <textarea
                  value={ruleHypothesis}
                  onChange={(event) => {
                    markHumanEdited();
                    setRuleHypothesis(event.target.value);
                  }}
                  className="focus-ring mt-2 min-h-24 w-full rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[13px] leading-5 text-[var(--text-primary)] outline-none"
                  placeholder="例如：类似形态需要承接确认后升级观察，而不是直接排除。"
                />
              </label>
              <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
                <label className="block">
                  <span className="text-[12px] font-medium text-[var(--text-primary)]">验证状态</span>
                  <select
                    value={followUpStatus}
                    onChange={(event) => {
                      markHumanEdited();
                      setFollowUpStatus(event.target.value);
                    }}
                    className="focus-ring mt-2 h-10 w-full rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 text-[13px] text-[var(--text-primary)] outline-none"
                  >
                    {followUpOptions.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </label>
                <label className="block">
                  <span className="text-[12px] font-medium text-[var(--text-primary)]">下次验证日期</span>
                  <input
                    value={followUpDueAt}
                    onChange={(event) => {
                      markHumanEdited();
                      setFollowUpDueAt(event.target.value);
                    }}
                    className="focus-ring mt-2 h-10 w-full rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 text-[13px] text-[var(--text-primary)] outline-none"
                    placeholder="YYYY-MM-DD"
                  />
                </label>
              </div>
              <button
                type="button"
                onClick={saveCase}
                disabled={saveMutation.isPending || !primaryCause || !conclusionAction}
                className="focus-ring prism-btn prism-btn-primary mt-4 w-full"
              >
                {saveMutation.isPending ? <LoaderCircle size={15} className="animate-spin" /> : <CheckCircle2 size={15} />}
                保存 Review Case
              </button>
              {feedback ? (
                <div className="mt-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[12px] leading-5 text-[var(--text-secondary)]">
                  {feedback}
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </Panel>
    </section>
  );
}

function AttributionDraftCard({
  draft,
  status,
  feedback,
  primaryOptions,
  secondaryOptions,
  conclusionOptions,
  onGenerate,
  onAdopt,
  onClear,
  isGenerating,
}: {
  draft: DecisionLedgerAttributionDraft | null;
  status: string;
  feedback: string;
  primaryOptions: DecisionLedgerReviewCaseOption[];
  secondaryOptions: DecisionLedgerReviewCaseOption[];
  conclusionOptions: DecisionLedgerReviewCaseOption[];
  onGenerate: () => void;
  onAdopt: () => void;
  onClear: () => void;
  isGenerating: boolean;
}) {
  const similarRefs = draft?.similar_case_refs || [];
  const patternRefs = draft?.pattern_memory_refs || [];
  const shadowRefs = draft?.shadow_sample_refs || [];

  return (
    <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Sparkles size={16} className="text-[var(--info)]" />
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">AI 预归因</h3>
          <Badge tone={draftStatusTone(status)}>{draftStatusLabel(status)}</Badge>
        </div>
        <button
          type="button"
          onClick={onGenerate}
          disabled={isGenerating}
          className="focus-ring inline-flex h-8 items-center gap-1.5 rounded-md border border-[var(--border-subtle)] px-2.5 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isGenerating ? <LoaderCircle size={14} className="animate-spin" /> : draft ? <RefreshCw size={14} /> : <Sparkles size={14} />}
          {draft ? "重新生成" : "AI 预归因"}
        </button>
      </div>

      {draft ? (
        <div className="space-y-3">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <TextFact label="建议主归因" value={optionLabel(primaryOptions, draft.primary_cause)} />
            <TextFact label="建议结论动作" value={optionLabel(conclusionOptions, draft.conclusion_action)} />
            <TextFact label="样本强度" value={`${draft.evidence_strength_label || "观察假设"} · ${draft.sample_count || 1} 条`} />
            <TextFact label="AI 置信度" value={confidenceLabel(draft.confidence)} />
          </div>
          <TextFact label="建议辅助归因" value={optionLabels(secondaryOptions, draft.secondary_causes)} />
          {draft.rule_hypothesis ? (
            <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[12px] leading-5 text-[var(--text-secondary)]">
              {draft.rule_hypothesis}
            </div>
          ) : null}
          {draft.evidence?.length ? (
            <div>
              <div className="mb-1 text-[11px] font-medium text-[var(--text-tertiary)]">判断依据</div>
              <div className="space-y-1.5">
                {draft.evidence.slice(0, 4).map((item) => (
                  <div key={item} className="rounded-md bg-[var(--bg-secondary)] px-3 py-1.5 text-[11px] leading-4 text-[var(--text-secondary)]">
                    {item}
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          {draft.human_check_required?.length ? (
            <div>
              <div className="mb-1 text-[11px] font-medium text-[var(--text-tertiary)]">需要人工确认</div>
              <div className="space-y-1.5">
                {draft.human_check_required.slice(0, 3).map((item) => (
                  <div key={item} className="rounded-md bg-[color-mix(in_srgb,var(--warning)_8%,transparent)] px-3 py-1.5 text-[11px] leading-4 text-[var(--text-secondary)]">
                    {item}
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          {similarRefs.length || patternRefs.length ? (
            <div>
              <div className="mb-1 text-[11px] font-medium text-[var(--text-tertiary)]">相似历史样本</div>
              <div className="space-y-1.5">
                {similarRefs.slice(0, 3).map((ref) => (
                  <div key={ref.review_case_id || ref.decision_id || caseRefLabel(ref)} className="rounded-md bg-[var(--bg-secondary)] px-3 py-1.5 text-[11px] leading-4 text-[var(--text-secondary)]">
                    {caseRefLabel(ref)}
                  </div>
                ))}
                {patternRefs.slice(0, 2).map((ref) => (
                  <div key={ref.review_case_id || ref.decision_id || ref.learning_hint} className="rounded-md bg-[var(--bg-secondary)] px-3 py-1.5 text-[11px] leading-4 text-[var(--text-secondary)]">
                    {ref.learning_hint || caseRefLabel(ref)}
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          {shadowRefs.length ? (
            <div>
              <div className="mb-1 flex items-center gap-2 text-[11px] font-medium text-[var(--text-tertiary)]">
                <Database size={12} />
                影子样本参考
              </div>
              <div className="space-y-1.5">
                {shadowRefs.slice(0, 3).map((ref) => (
                  <div
                    key={`${ref.axis || "shadow"}-${ref.key || ref.label || shadowRefLabel(ref)}`}
                    className="rounded-md border border-[color-mix(in_srgb,var(--warning)_18%,transparent)] bg-[color-mix(in_srgb,var(--warning)_7%,transparent)] px-3 py-2"
                  >
                    <div className="line-clamp-1 text-[11px] font-medium text-[var(--text-primary)]">
                      {shadowRefLabel(ref)}
                    </div>
                    <div className="mt-1 line-clamp-2 text-[11px] leading-4 text-[var(--text-tertiary)]">
                      {shadowRefDetail(ref)}
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-2 text-[11px] leading-4 text-[var(--text-tertiary)]">
                研究口径参考，不计入真实样本数，也不解锁规则修改。
              </div>
            </div>
          ) : null}
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onAdopt}
              className="focus-ring inline-flex h-8 items-center gap-1.5 rounded-md border border-[var(--border-subtle)] px-2.5 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            >
              <CheckCircle2 size={14} />
              采纳草稿
            </button>
            <button
              type="button"
              onClick={onClear}
              className="focus-ring inline-flex h-8 items-center gap-1.5 rounded-md border border-[var(--border-subtle)] px-2.5 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            >
              清空草稿
            </button>
          </div>
        </div>
      ) : (
        <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3 text-[12px] leading-5 text-[var(--text-secondary)]">
          等待生成结构化草稿。
        </div>
      )}

      {feedback ? (
        <div className="mt-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[12px] leading-5 text-[var(--text-secondary)]">
          {feedback}
        </div>
      ) : null}
    </div>
  );
}

function WorkbenchSection({
  icon: Icon,
  title,
  children,
}: {
  icon: typeof Target;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-4">
      <div className="mb-3 flex items-center gap-2">
        <Icon size={16} className="text-[var(--text-tertiary)]" />
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">{title}</h3>
      </div>
      {children}
    </div>
  );
}

function TextFact({ label, value }: { label: string; value?: string | number | null }) {
  return (
    <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
      <div className="text-[11px] text-[var(--text-tertiary)]">{label}</div>
      <div className="mt-1 text-[12px] leading-5 text-[var(--text-primary)]">{value || "-"}</div>
    </div>
  );
}

function OutcomeCard({ event }: { event: DecisionLedgerOutcomeEvent }) {
  const tone = (event.classification?.tone as Tone | undefined) || "watch";
  return (
    <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="text-[12px] font-medium text-[var(--text-primary)]">{event.window || "Outcome"}</span>
        <Badge tone={tone}>{reasonLabel(event.classification?.label, event.classification?.label)}</Badge>
      </div>
      <div className="grid grid-cols-2 gap-2 text-[11px] text-[var(--text-tertiary)]">
        <span>收益 {pct(event.market_data?.return_pct)}</span>
        <span>相对 {pct(event.market_data?.relative_return_pct)}</span>
        <span>最好 {pct(event.market_data?.max_favorable_pct)}</span>
        <span>最差 {pct(event.market_data?.max_adverse_pct)}</span>
      </div>
      <p className="mt-2 line-clamp-3 text-[11px] leading-4 text-[var(--text-secondary)]">
        {event.classification?.summary || event.classification?.reasons?.[0] || "-"}
      </p>
    </div>
  );
}

function OptionGrid({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: DecisionLedgerReviewCaseOption[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="mt-4 first:mt-0">
      <div className="mb-2 text-[12px] font-medium text-[var(--text-primary)]">{label}</div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className={cn(
              "focus-ring min-h-9 rounded-md border px-3 py-2 text-left text-[12px] transition-colors",
              value === option.value
                ? "border-[var(--info)] bg-[color-mix(in_srgb,var(--info)_12%,transparent)] text-[var(--text-primary)]"
                : "border-[var(--border-subtle)] bg-[var(--bg-secondary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
            )}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function CheckboxGrid({
  label,
  options,
  values,
  onToggle,
}: {
  label: string;
  options: DecisionLedgerReviewCaseOption[];
  values: string[];
  onToggle: (value: string) => void;
}) {
  return (
    <div className="mt-4">
      <div className="mb-2 text-[12px] font-medium text-[var(--text-primary)]">{label}</div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {options.map((option) => {
          const active = values.includes(option.value);
          return (
            <button
              key={option.value}
              type="button"
              onClick={() => onToggle(option.value)}
              className={cn(
                "focus-ring min-h-9 rounded-md border px-3 py-2 text-left text-[12px] transition-colors",
                active
                  ? "border-[var(--info)] bg-[color-mix(in_srgb,var(--info)_12%,transparent)] text-[var(--text-primary)]"
                  : "border-[var(--border-subtle)] bg-[var(--bg-secondary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
              )}
            >
              {option.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function ShadowCalibrationPanel({ shadow }: { shadow?: ShadowCalibrationSummary }) {
  if (!shadow) {
    return null;
  }
  const status = shadowStatusMeta(shadow.status);
  const cards = shadow.cards || [];
  const bucketRows = shadow.bucket_rows || [];

  return (
    <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Database size={14} className="text-[var(--text-tertiary)]" />
            <div className="text-[12px] font-medium text-[var(--text-primary)]">
              {shadow.title || "历史影子校准提示"}
            </div>
          </div>
          <div className="mt-1 line-clamp-2 text-[11px] leading-4 text-[var(--text-tertiary)]">
            {shadow.summary || "研究样本只辅助提问，不替代真实复盘样本。"}
          </div>
        </div>
        <Badge tone={status.tone}>{status.label}</Badge>
      </div>
      {shadow.warning ? (
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
    </div>
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
      <div className="mt-2 text-[11px] leading-4 text-[var(--text-tertiary)]">
        {card.action_reason}
      </div>
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

function LearningPatterns({ data }: { data?: DecisionLedgerCalibrationResponse }) {
  const patterns = data?.review_case_patterns || [];
  const groups = [data?.by_lane || [], data?.by_action || []];
  const shadow = data?.shadow_calibration;
  return (
    <section id="learning-patterns" className="mb-7 scroll-mt-6">
      <Panel title="学习模式与规则假设" eyebrow="Pattern Learning">
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(340px,0.85fr)]">
          <div className="space-y-3">
            {patterns.length ? (
              patterns.map((pattern) => <PatternCard key={pattern.pattern_id} pattern={pattern} />)
            ) : (
              <EmptyState>还没有保存的 Review Case。完成一条归因后，这里会生成同类样本模式。</EmptyState>
            )}
          </div>
          <div className="grid grid-cols-1 gap-3">
            <ShadowCalibrationPanel shadow={shadow} />
            <CalibrationGroupTable title="链路质量分布" groups={groups[0]} />
            <CalibrationGroupTable title="动作质量分布" groups={groups[1]} />
          </div>
        </div>
      </Panel>
    </section>
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

function HistoricalDecisionLedger() {
  const ledger = useDecisionLedgerRecent(10);
  const data = ledger.data as DecisionLedgerRecentResponse | undefined;
  const items = data?.items || [];

  return (
    <section className="mb-7">
      <Panel
        title="历史决策流水"
        eyebrow="Ledger History"
        action={
          <button
            type="button"
            className="focus-ring inline-flex items-center gap-1.5 rounded-md border border-[var(--border-subtle)] px-2 py-1 text-[11px] text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
            onClick={() => void ledger.refetch()}
          >
            <RefreshCw size={12} className={ledger.isFetching ? "animate-spin" : ""} />
            重读
          </button>
        }
      >
        <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-4">
          {ledger.isLoading && !data ? (
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, index) => <SkeletonBlock key={index} className="h-14 w-full" />)}
            </div>
          ) : ledger.isError ? (
            <ErrorState message="历史决策流水暂不可用" onRetry={() => void ledger.refetch()} />
          ) : items.length ? (
            <div className="space-y-2">
              {items.map((item) => <LedgerHistoryRow key={item.decision_id} item={item} />)}
            </div>
          ) : (
            <EmptyState>暂无捕获的决策记录。</EmptyState>
          )}
        </div>
      </Panel>
    </section>
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
          <span className="mono text-[11px] text-[var(--text-tertiary)]">{item.code}</span>
          <span className="text-[11px] text-[var(--text-tertiary)]">{item.trade_date}</span>
        </div>
        {item.main_conclusion ? <div className="mt-1 line-clamp-1 text-[11px] text-[var(--text-tertiary)]">{item.main_conclusion}</div> : null}
      </div>
      <Badge tone="info">{item.lane || "unknown"}</Badge>
      <Badge tone={(item.latest_outcome?.tone as Tone) || "watch"}>{reasonLabel(item.latest_outcome?.label, item.latest_outcome?.label || "待评估")}</Badge>
      <ArrowRight size={14} className="text-[var(--text-tertiary)]" />
    </Link>
  );
}

function EvidenceStatus({ review }: { review?: ReviewData }) {
  const sourceCards = review?.source_cards || [];
  const artifacts = review?.artifacts || [];

  return (
    <section id="evidence-status" className="mb-7 scroll-mt-6">
      <details className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)]">
        <summary className="focus-ring flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3">
          <div className="flex min-w-0 items-center gap-2">
            <Database size={16} className="shrink-0 text-[var(--text-tertiary)]" />
            <div className="min-w-0">
              <div className="text-sm font-semibold text-[var(--text-primary)]">证据与数据状态</div>
              <div className="mt-0.5 line-clamp-1 text-[11px] text-[var(--text-tertiary)]">
                历史 research 只用于校准和解释，不代表今日实时环境，也不触发规则自动修改。
              </div>
            </div>
          </div>
          <Badge tone={review?.freshness_summary?.stale_count ? "warning" : "positive"}>
            {review?.freshness_summary?.stale_count ? `${review.freshness_summary.stale_count} 个过期源` : "来源可读"}
          </Badge>
        </summary>
        <div className="border-t border-[var(--border-subtle)] p-4">
          <div className="mb-4 rounded-md border border-[color-mix(in_srgb,var(--warning)_24%,transparent)] bg-[color-mix(in_srgb,var(--warning)_8%,transparent)] px-3 py-2 text-[12px] leading-5 text-[var(--text-secondary)]">
            历史 research 只用于校准和解释，不代表今日实时环境，也不触发规则自动修改。
          </div>
          {review?.freshness_alerts?.length ? (
            <div className="mb-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
              {review.freshness_alerts.map((row, index) => <RiskAlert key={`${row.title}-${index}`} row={row} />)}
            </div>
          ) : null}
          <div className="mb-5 grid grid-cols-1 gap-3 lg:grid-cols-2">
            <EvidencePanel
              page="review"
              mode="readonly"
              sources={sourceCards as SourceCardData[]}
              artifacts={artifacts as BasicCard[]}
              title="来源、 freshness 与原始报告"
              eyebrow="Evidence"
            />
            <HistoricalResearchSummary review={review} />
          </div>
        </div>
      </details>
    </section>
  );
}

function HistoricalResearchSummary({ review }: { review?: ReviewData }) {
  const comparisonCards = review?.comparison_cards || [];
  const panels = review?.research_panels || [];
  const lifecycleCards = review?.lifecycle_cards || [];
  return (
    <div className="space-y-4">
      <CompactMetricPanel title="基准 / 对比窗口" cards={comparisonCards} empty="暂无窗口对比。" />
      <CompactMetricPanel title="变化回放" cards={lifecycleCards} empty="暂无变化回放。" />
      <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3">
        <div className="mb-2 flex items-center gap-2">
          <FileText size={14} className="text-[var(--text-tertiary)]" />
          <div className="text-[12px] font-medium text-[var(--text-primary)]">研究拆解</div>
        </div>
        {panels.length ? (
          <div className="space-y-2">
            {panels.slice(0, 3).map((panel) => <ResearchPanelMini key={`${panel.eyebrow}-${panel.title}`} panel={panel} />)}
          </div>
        ) : (
          <EmptyState>暂无研究拆解。</EmptyState>
        )}
      </div>
    </div>
  );
}

function CompactMetricPanel({ title, cards, empty }: { title: string; cards: MetricCardData[]; empty: string }) {
  return (
    <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3">
      <div className="mb-2 text-[12px] font-medium text-[var(--text-primary)]">{title}</div>
      {cards.length ? (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {cards.slice(0, 4).map((card, index) => <MetricCard key={`${title}-${card.label}-${index}`} {...card} tone={card.tone || "info"} />)}
        </div>
      ) : (
        <EmptyState>{empty}</EmptyState>
      )}
    </div>
  );
}

function ResearchPanelMini({ panel }: { panel: ReviewResearchPanel }) {
  return (
    <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-[12px] font-medium text-[var(--text-primary)]">{panel.title}</div>
          {panel.summary ? <div className="mt-1 line-clamp-2 text-[11px] text-[var(--text-tertiary)]">{panel.summary}</div> : null}
        </div>
        {panel.artifact_url ? (
          <a
            href={panel.artifact_url}
            target="_blank"
            rel="noreferrer"
            className="focus-ring inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-[var(--border-subtle)] text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
          >
            <ExternalLink size={13} />
          </a>
        ) : null}
      </div>
    </div>
  );
}

function OutcomeEvaluatorAction({ calibration }: { calibration: ReturnType<typeof useDecisionLedgerCalibration> }) {
  const outcomeRun = useRunTask();
  const canRun = Boolean((calibration.data?.review_workbench?.overdue_count || 0) > 0);
  const [feedback, setFeedback] = useState("");

  function runOutcomeEvaluator() {
    setFeedback("");
    outcomeRun.mutate(
      {
        taskName: "decision_ledger_outcomes",
        payload: { send_to_feishu: false, reason: "manual_from_review_decision_ledger" },
      },
      {
        onSuccess: (payload) => {
          setFeedback(`${payload.title || "结果评估"}已启动：${payload.run_id || payload.task_name || "后台任务"}。`);
          window.setTimeout(() => void calibration.refetch(), 5_000);
        },
        onError: (error) => setFeedback(error instanceof Error ? error.message : "启动失败。"),
      },
    );
  }

  if (!canRun && !feedback) {
    return null;
  }

  return (
    <section className="mb-7 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <div className="text-sm font-semibold text-[var(--text-primary)]">有成熟样本缺 outcome</div>
          <div className="mt-1 text-[12px] text-[var(--text-tertiary)]">先补齐结果证据，再进入归因或规则学习。</div>
        </div>
        <button
          type="button"
          onClick={runOutcomeEvaluator}
          disabled={outcomeRun.isPending}
          className={PRIMARY_ACTION_CLASS}
        >
          {outcomeRun.isPending ? <LoaderCircle size={15} className="animate-spin" /> : <RefreshCw size={15} />}
          补跑结果评估
        </button>
      </div>
      {feedback ? <div className="mt-3 text-[12px] text-[var(--text-secondary)]">{feedback}</div> : null}
    </section>
  );
}

function ReviewPageContent() {
  const searchParams = useSearchParams();
  const selectedDecisionId = cleanParam(searchParams.get("case"));
  const review = useReview();
  const calibration = useDecisionLedgerCalibration({ window: "20d", limit: 12 });

  const titleSummary = selectedDecisionId
    ? "围绕一条 Decision Ledger 样本完成归因、备注、结论动作与后续验证。"
    : "先处理待复盘队列；历史 research backfill 只作为底部证据，不再占据主流程。";

  const pageBadge = calibration.data?.needs_review_count
    ? `${calibration.data.needs_review_count} 条待归因`
    : "Decision Ledger";

  return (
    <main className="flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
      <div className="mx-auto max-w-7xl">
        <PageTitle
          eyebrow="Review"
          title={selectedDecisionId ? "Review Case 归因工作台" : "Decision Ledger 学习台"}
          summary={titleSummary}
          icon={BookOpenCheck}
          badge={pageBadge}
          actions={
            <div className="flex flex-wrap gap-2">
              {selectedDecisionId ? (
                <Link
                  href="/review"
                  className="focus-ring inline-flex items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                >
                  回到队列
                </Link>
              ) : null}
              <button
                type="button"
                className="focus-ring inline-flex items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)]"
                onClick={() => {
                  void review.refetch();
                  void calibration.refetch();
                }}
              >
                <RefreshCw size={14} className={review.isFetching || calibration.isFetching ? "animate-spin" : ""} />
                重读数据
              </button>
            </div>
          }
        />

        {selectedDecisionId ? (
          <ReviewCaseWorkspace decisionId={selectedDecisionId} />
        ) : (
          <DecisionLedgerHero
            data={calibration.data}
            loading={calibration.isLoading}
            fetching={calibration.isFetching}
            onRefetch={() => void calibration.refetch()}
          />
        )}
        <OutcomeEvaluatorAction calibration={calibration} />
        <ReviewQueue
          data={calibration.data}
          loading={calibration.isLoading}
          error={calibration.isError}
          onRetry={() => void calibration.refetch()}
        />
        <HistoricalShadowReplay review={review.data} />
        <LearningPatterns data={calibration.data} />
        <HistoricalDecisionLedger />
        <EvidenceStatus review={review.data} />
      </div>
    </main>
  );
}

export default function ReviewPage() {
  return (
    <Suspense
      fallback={
        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
          <div className="mx-auto max-w-7xl">
            <SkeletonBlock className="mb-7 h-28 w-full" />
            <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {Array.from({ length: 4 }).map((_, index) => (
                <MetricSkeleton key={index} />
              ))}
            </section>
          </div>
        </main>
      }
    >
      <ReviewPageContent />
    </Suspense>
  );
}
