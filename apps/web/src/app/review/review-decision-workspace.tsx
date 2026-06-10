"use client";

import {
  ArrowRight,
  BarChart3,
  BookOpenCheck,
  ClipboardCheck,
  Database,
  ExternalLink,
  FileText,
  LoaderCircle,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { Badge } from "@/components/badge";
import {
  EmptyState,
  ErrorState,
  Panel,
  SkeletonBlock,
} from "@/components/data-card";
import { MetricCard } from "@/components/metric-card";
import { PageTitle } from "@/components/page-title";
import { RiskAlert } from "@/components/risk-alert";
import {
  useDecisionLedgerCalibration,
  useDecisionLedgerCalibrationDetail,
  useAutoReviewDecisionLedgerCase,
  queryKeys,
  useReview,
  useReviewEvidence,
  useRunTask,
} from "@/lib/hooks";
import type {
  DecisionLedgerCalibrationResponse,
  DecisionLedgerReviewRecord,
  MetricCardData,
  ReviewData,
  ReviewResearchPanel,
  Tone,
} from "@/lib/types";
import {
  reasonLabel,
  reviewCaseHref,
  reviewStatusMeta,
  sampleGuardrailText,
} from "./review-utils";
import { MiniFact } from "./review-mini-fact";

const PRIORITY_TONE: Record<string, Tone | string> = {
  critical: "risk",
  high: "warning",
  medium: "watch",
  low: "stale",
};

const PRIMARY_ACTION_CLASS = "focus-ring prism-btn prism-btn-primary";
const REVIEW_CALIBRATION_PARAMS = { window: "20d", limit: 12 } as const;

const HistoricalShadowReplay = dynamic(
  () =>
    import("./review-history-panels").then(
      (module) => module.HistoricalShadowReplay,
    ),
  {
    ssr: false,
    loading: () => (
      <div className="border-t border-[var(--border-subtle)] p-4">
        <SkeletonBlock className="h-28 w-full" />
      </div>
    ),
  },
);

const HistoricalDecisionLedger = dynamic(
  () =>
    import("./review-history-panels").then(
      (module) => module.HistoricalDecisionLedger,
    ),
  {
    ssr: false,
    loading: () => (
      <div className="border-t border-[var(--border-subtle)] p-4">
        <SkeletonBlock className="h-28 w-full" />
      </div>
    ),
  },
);

const LearningPatternsChunk = dynamic(
  () =>
    import("./review-learning-patterns").then(
      (module) => module.LearningPatterns,
    ),
  {
    ssr: false,
    loading: () => <SkeletonBlock className="h-28 w-full" />,
  },
);

const ReviewEvidencePanel = dynamic(
  () =>
    import("@/components/evidence-panel").then(
      (module) => module.EvidencePanel,
    ),
  {
    ssr: false,
    loading: () => <SkeletonBlock className="h-64 w-full" />,
  },
);

function priorityTone(label?: string) {
  return PRIORITY_TONE[label || ""] || "stale";
}

function topQueueItem(data?: DecisionLedgerCalibrationResponse) {
  return (data?.review_queue || []).find((item) =>
    ["ready_review", "blocked_data"].includes(String(item.review_status || "")),
  );
}

function SummaryPill({
  label,
  value,
  tone = "info",
}: {
  label: string;
  value: string | number;
  tone?: Tone | string;
}) {
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
  onAutoReview,
  autoReviewingDecisionId,
}: {
  data?: DecisionLedgerCalibrationResponse;
  loading: boolean;
  onRefetch: () => void;
  fetching: boolean;
  onAutoReview: (decisionId?: string) => void;
  autoReviewingDecisionId?: string;
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
            <Badge tone={needsReview ? "warning" : "positive"}>
              {needsReview ? "需要复盘" : "队列清爽"}
            </Badge>
            <Badge tone="info">
              {data?.from_date || "-"} 至 {data?.to_date || "-"}
            </Badge>
            <Badge tone="watch">已归因 {reviewed}</Badge>
          </div>
          <h2 className="text-[clamp(26px,4vw,44px)] font-semibold leading-tight tracking-normal text-[var(--text-primary)]">
            需要复盘 {needsReview} 条
          </h2>
          {top ? (
            <div className="mt-4 max-w-3xl">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-lg font-semibold text-[var(--text-primary)]">
                  {top.name || top.code}
                </span>
                <span className="mono text-sm text-[var(--text-tertiary)]">
                  {top.code}
                </span>
                <Badge tone={priorityTone(top.priority_label)}>
                  P{top.priority_score ?? 0} {top.priority_label || "low"}
                </Badge>
              </div>
              <p className="mt-2 text-[14px] leading-6 text-[var(--text-secondary)]">
                原因：{reasonLabel(top.review_reason_key, top.review_reason)}
                。当前建议：先完成归因，生成“是否过度保守/过度宽松”的可追踪假设，不直接改规则。
              </p>
              <div className="mt-3 rounded-md border border-[color-mix(in_srgb,var(--warning)_24%,transparent)] bg-[color-mix(in_srgb,var(--warning)_8%,transparent)] px-3 py-2 text-[12px] leading-5 text-[var(--text-secondary)]">
                {sampleGuardrailText(null)}
              </div>
              <div className="mt-5 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => onAutoReview(top.decision_id)}
                  disabled={
                    !top.decision_id ||
                    autoReviewingDecisionId === top.decision_id
                  }
                  className={PRIMARY_ACTION_CLASS}
                >
                  {autoReviewingDecisionId === top.decision_id ? (
                    <LoaderCircle size={15} className="animate-spin" />
                  ) : (
                    <Sparkles size={15} />
                  )}
                  AI一键复盘
                </button>
                <Link
                  href={reviewCaseHref(top.decision_id)}
                  className="focus-ring inline-flex min-h-10 items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                >
                  <ClipboardCheck size={15} />
                  人工归因
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
                当前没有必须立即归因的成熟失败样本。可以查看已归因模式、等待
                outcome 成熟，或到底部证据区核对数据状态。
              </p>
              <div className="mt-5 flex flex-wrap gap-2">
                <a href="#learning-patterns" className={PRIMARY_ACTION_CLASS}>
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
              <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">
                Learning State
              </div>
              <div className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
                {workbench?.top_priority_reason || "暂无优先风险"}
              </div>
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
            <SummaryPill
              label="待归因"
              value={needsReview}
              tone={needsReview ? "warning" : "positive"}
            />
            <SummaryPill
              label="数据阻塞"
              value={blocked}
              tone={blocked ? "risk" : "positive"}
            />
            <SummaryPill
              label="待成熟"
              value={pending}
              tone={pending ? "watch" : "positive"}
            />
            <SummaryPill label="已归因" value={reviewed} tone="info" />
          </div>
          <div className="mt-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2 text-[12px] leading-5 text-[var(--text-secondary)]">
            下一步：
            {top
              ? "处理最高优先级样本，保存结构化 Review Case。"
              : workbench?.next_best_action || "继续积累样本。"}
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
  onAutoReview,
  autoReviewingDecisionId,
}: {
  data?: DecisionLedgerCalibrationResponse;
  loading: boolean;
  error: boolean;
  onRetry: () => void;
  onAutoReview: (decisionId?: string) => void;
  autoReviewingDecisionId?: string;
}) {
  const readyItems = (data?.review_queue || []).filter((item) =>
    ["ready_review", "blocked_data"].includes(String(item.review_status || "")),
  );
  const pendingItems = data?.pending_reviews || [];

  return (
    <section id="review-queue" className="mb-7 scroll-mt-6">
      <Panel title="今日复盘队列" eyebrow="Decision Ledger">
        {error ? (
          <ErrorState
            message="Decision Ledger 队列暂不可用"
            onRetry={onRetry}
          />
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
                readyItems.map((item) => (
                  <ReviewQueueCard
                    key={item.decision_id}
                    item={item}
                    onAutoReview={onAutoReview}
                    autoReviewing={autoReviewingDecisionId === item.decision_id}
                  />
                ))
              ) : (
                <EmptyState>没有成熟且必须优先归因的决策样本。</EmptyState>
              )}
            </div>
            <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3">
              <div className="mb-3 flex items-center justify-between gap-3">
                <div>
                  <div className="text-[12px] font-medium text-[var(--text-primary)]">
                    待成熟 / 补证据
                  </div>
                  <div className="mt-1 text-[11px] text-[var(--text-tertiary)]">
                    缺 outcome 或 execution 的样本先不做规则判断。
                  </div>
                </div>
                <Badge tone={pendingItems.length ? "watch" : "positive"}>
                  {pendingItems.length}
                </Badge>
              </div>
              <div className="space-y-2">
                {pendingItems.length ? (
                  pendingItems
                    .slice(0, 5)
                    .map((item) => (
                      <PendingQueueRow key={item.decision_id} item={item} />
                    ))
                ) : (
                  <EmptyState>当前没有待成熟样本。</EmptyState>
                )}
              </div>
            </div>
          </div>
        )}
      </Panel>
    </section>
  );
}

function ReviewQueueCard({
  item,
  onAutoReview,
  autoReviewing,
}: {
  item: DecisionLedgerReviewRecord;
  onAutoReview: (decisionId?: string) => void;
  autoReviewing: boolean;
}) {
  const status = reviewStatusMeta(item.review_status);
  const outcomeLabel =
    item.latest_outcome?.label || item.outcome_status || "pending";
  return (
    <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-base font-semibold text-[var(--text-primary)]">
              {item.name || item.code}
            </span>
            <span className="mono text-[12px] text-[var(--text-tertiary)]">
              {item.code}
            </span>
            <span className="text-[12px] text-[var(--text-tertiary)]">
              {item.trade_date}
            </span>
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
        <MiniFact
          label="原始动作"
          value={item.action_label || item.action || "-"}
        />
        <MiniFact
          label="最新 outcome"
          value={`${item.latest_outcome?.window || ""} ${reasonLabel(outcomeLabel, outcomeLabel)}`}
          tone={item.outcome_tone || item.latest_outcome?.tone || "watch"}
        />
        <MiniFact
          label="复盘原因"
          value={reasonLabel(item.review_reason_key, item.review_reason)}
          tone="warning"
        />
      </div>
      <div className="mt-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[12px] leading-5 text-[var(--text-secondary)]">
        建议下一步：
        {item.next_action_reason || "开始人工归因，保存结构化 Review Case。"}
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => onAutoReview(item.decision_id)}
          disabled={!item.decision_id || autoReviewing}
          className="focus-ring prism-btn prism-btn-primary prism-btn-sm"
        >
          {autoReviewing ? (
            <LoaderCircle size={14} className="animate-spin" />
          ) : (
            <Sparkles size={14} />
          )}
          AI一键复盘
        </button>
        <Link
          href={reviewCaseHref(item.decision_id)}
          className="focus-ring inline-flex min-h-9 items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
        >
          <ClipboardCheck size={14} />
          人工归因
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
            <span className="mono text-[11px] text-[var(--text-tertiary)]">
              {item.code}
            </span>
            <Badge tone={status.tone}>{status.label}</Badge>
            {item.is_overdue ? <Badge tone="risk">已逾期</Badge> : null}
          </div>
          <div className="mt-1 text-[11px] leading-4 text-[var(--text-tertiary)]">
            {item.maturity_label || "等待 outcome 成熟"}
          </div>
        </div>
        <Badge tone={priorityTone(item.priority_label)}>
          P{item.priority_score ?? 0}
        </Badge>
      </div>
    </div>
  );
}

function LearningPatternsSection({
  data,
}: {
  data?: DecisionLedgerCalibrationResponse;
}) {
  const [open, setOpen] = useState(false);
  const detail = useDecisionLedgerCalibrationDetail(REVIEW_CALIBRATION_PARAMS, {
    enabled: open,
  });
  const patternCount =
    detail.data?.review_case_patterns?.length ||
    data?.review_case_summary?.patterns ||
    0;
  const groupCount =
    (detail.data?.by_lane?.length || 0) +
    (detail.data?.by_action?.length || 0);

  return (
    <section id="learning-patterns" className="mb-7 scroll-mt-6">
      <details
        className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)]"
        onToggle={(event) => setOpen(event.currentTarget.open)}
      >
        <summary className="focus-ring flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3">
          <div className="flex min-w-0 items-center gap-2">
            <Sparkles
              size={16}
              className="shrink-0 text-[var(--text-tertiary)]"
            />
            <div className="min-w-0">
              <div className="text-sm font-semibold text-[var(--text-primary)]">
                学习模式与规则假设
              </div>
              <div className="mt-0.5 line-clamp-1 text-[11px] text-[var(--text-tertiary)]">
                二级校准工具按需加载，默认先聚焦待复盘队列。
              </div>
            </div>
          </div>
          <Badge tone={patternCount ? "info" : "stale"}>
            {patternCount
              ? `${patternCount} 个模式`
              : groupCount
                ? `${groupCount} 个分组`
                : "按需加载"}
          </Badge>
        </summary>
        {open ? detail.isLoading && !detail.data ? (
          <div className="border-t border-[var(--border-subtle)] p-4">
            <SkeletonBlock className="h-32 w-full" />
          </div>
        ) : detail.isError ? (
          <div className="border-t border-[var(--border-subtle)] p-4">
            <ErrorState
              message="学习模式暂不可用"
              onRetry={() => void detail.refetch()}
            />
          </div>
        ) : (
          <LearningPatternsChunk data={detail.data} />
        ) : (
          <div className="border-t border-[var(--border-subtle)] px-4 py-3 text-[12px] leading-5 text-[var(--text-secondary)]">
            因子复盘、影子校准和分组表格默认不读取；展开后再加载这组研究工具。
          </div>
        )}
      </details>
    </section>
  );
}

function HistoricalShadowReplayGate() {
  const [shadowHistoryOpen, setShadowHistoryOpen] = useState(false);

  return (
    <section
      id="historical-shadow-samples"
      className="mb-7 scroll-mt-6"
      data-testid="review-shadow-history-gate"
    >
      <details
        open={shadowHistoryOpen}
        className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)]"
        onToggle={(event) => setShadowHistoryOpen(event.currentTarget.open)}
      >
        <summary className="focus-ring flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3">
          <div className="flex min-w-0 items-center gap-2">
            <Database
              size={16}
              className="shrink-0 text-[var(--text-tertiary)]"
            />
            <div className="min-w-0">
              <div className="text-sm font-semibold text-[var(--text-primary)]">
                历史影子样本
              </div>
              <div className="mt-0.5 line-clamp-1 text-[11px] text-[var(--text-tertiary)]">
                历史价格样本只用于校准复盘，不进入今日动作。
              </div>
            </div>
          </div>
          <Badge tone={shadowHistoryOpen ? "info" : "watch"}>
            {shadowHistoryOpen ? "已展开" : "按需加载"}
          </Badge>
        </summary>
        {shadowHistoryOpen ? (
          <HistoricalShadowReplay />
        ) : (
          <div className="border-t border-[var(--border-subtle)] px-4 py-3 text-[12px] leading-5 text-[var(--text-secondary)]">
            展开后才加载历史影子样本组件和样本接口，默认先让今日复盘队列保持轻量。
          </div>
        )}
      </details>
    </section>
  );
}

function HistoricalDecisionLedgerGate() {
  const [ledgerHistoryOpen, setLedgerHistoryOpen] = useState(false);

  return (
    <section
      className="mb-7 scroll-mt-6"
      data-testid="review-ledger-history-gate"
    >
      <details
        open={ledgerHistoryOpen}
        className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)]"
        onToggle={(event) => setLedgerHistoryOpen(event.currentTarget.open)}
      >
        <summary className="focus-ring flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3">
          <div className="flex min-w-0 items-center gap-2">
            <ClipboardCheck
              size={16}
              className="shrink-0 text-[var(--text-tertiary)]"
            />
            <div className="min-w-0">
              <div className="text-sm font-semibold text-[var(--text-primary)]">
                历史决策流水
              </div>
              <div className="mt-0.5 line-clamp-1 text-[11px] text-[var(--text-tertiary)]">
                默认不读取历史流水；展开后用于追溯原始判断和 outcome。
              </div>
            </div>
          </div>
          <Badge tone={ledgerHistoryOpen ? "info" : "watch"}>
            {ledgerHistoryOpen ? "已展开" : "按需查看最近 10 条决策"}
          </Badge>
        </summary>
        {ledgerHistoryOpen ? (
          <HistoricalDecisionLedger />
        ) : (
          <div className="border-t border-[var(--border-subtle)] px-4 py-3 text-[12px] leading-5 text-[var(--text-secondary)]">
            历史决策流水只在需要追溯时加载，避免复盘首页反复读取低频数据。
          </div>
        )}
      </details>
    </section>
  );
}

function EvidenceStatus() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [researchLoading, setResearchLoading] = useState(false);
  const [researchError, setResearchError] = useState("");
  const review = useReview({}, { enabled: open });
  const evidence = useReviewEvidence({}, { enabled: open });
  const reviewData = review.data;

  async function loadReviewResearch() {
    if (
      researchLoading ||
      reviewData?.research_panels?.length ||
      !reviewData?.research_panels_deferred
    ) {
      return;
    }
    setResearchLoading(true);
    setResearchError("");
    try {
      const payload = await api.getReviewResearch();
      queryClient.setQueryData(
        queryKeys.review(),
        (current: ReviewData | undefined) => ({
          ...(current || { generated_at: payload.generated_at }),
          research_panels:
            payload.research_panels || current?.research_panels || [],
          research_panels_deferred: false,
        }),
      );
    } catch (error) {
      setResearchError(
        error instanceof Error ? error.message : "研究拆解加载失败。",
      );
    } finally {
      setResearchLoading(false);
    }
  }

  return (
    <section id="evidence-status" className="mb-7 scroll-mt-6">
      <details
        className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)]"
        open={open}
        onToggle={(event) => setOpen(event.currentTarget.open)}
      >
        <summary className="focus-ring flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3">
          <div className="flex min-w-0 items-center gap-2">
            <Database
              size={16}
              className="shrink-0 text-[var(--text-tertiary)]"
            />
            <div className="min-w-0">
              <div className="text-sm font-semibold text-[var(--text-primary)]">
                证据与数据状态
              </div>
              <div className="mt-0.5 line-clamp-1 text-[11px] text-[var(--text-tertiary)]">
                历史 research
                只用于校准和解释，不代表今日实时环境，也不触发规则自动修改。
              </div>
            </div>
          </div>
          <Badge
            tone={
              !open && !reviewData
                ? "watch"
                : reviewData?.freshness_summary?.stale_count
                ? "warning"
                : "positive"
            }
          >
            {!open && !reviewData
              ? "按需加载"
              : review.isFetching && !reviewData
              ? "按需读取"
              : reviewData?.freshness_summary?.stale_count
                ? `${reviewData.freshness_summary.stale_count} 个过期源`
                : "来源可读"}
          </Badge>
        </summary>
        {open ? (
          <div className="border-t border-[var(--border-subtle)] p-4">
            <div className="mb-4 rounded-md border border-[color-mix(in_srgb,var(--warning)_24%,transparent)] bg-[color-mix(in_srgb,var(--warning)_8%,transparent)] px-3 py-2 text-[12px] leading-5 text-[var(--text-secondary)]">
              历史 research
              只用于校准和解释，不代表今日实时环境，也不触发规则自动修改。
            </div>
            {review.isLoading && !reviewData ? (
              <SkeletonBlock className="mb-4 h-20 w-full" />
            ) : review.isError ? (
              <div className="mb-4">
                <ErrorState
                  message="复盘摘要暂不可用"
                  onRetry={() => void review.refetch()}
                />
              </div>
            ) : null}
            {reviewData?.freshness_alerts?.length ? (
              <div className="mb-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
                {reviewData.freshness_alerts.map((row, index) => (
                  <RiskAlert key={`${row.title}-${index}`} row={row} />
                ))}
              </div>
            ) : null}
            <div className="mb-5 grid grid-cols-1 gap-3 lg:grid-cols-2">
              {evidence.isLoading ? (
                <SkeletonBlock className="h-64 w-full" />
              ) : evidence.isError ? (
                <ErrorState
                  message={
                    evidence.error instanceof Error
                      ? evidence.error.message
                      : "证据状态加载失败。"
                  }
                  onRetry={() => void evidence.refetch()}
                />
              ) : (
                <ReviewEvidencePanel
                  page="review"
                  mode="readonly"
                  sources={evidence.data?.source_cards || []}
                  artifacts={evidence.data?.artifacts || []}
                  title="来源、 freshness 与原始报告"
                  eyebrow="Evidence"
                />
              )}
              <HistoricalResearchSummary
                review={reviewData}
                loading={researchLoading}
                error={researchError}
                onLoadResearch={() => void loadReviewResearch()}
              />
            </div>
          </div>
        ) : (
          <div className="border-t border-[var(--border-subtle)] px-4 py-3 text-[12px] leading-5 text-[var(--text-secondary)]">
            展开后加载 freshness、来源和原始报告预览。
          </div>
        )}
      </details>
    </section>
  );
}

function HistoricalResearchSummary({
  review,
  loading,
  error,
  onLoadResearch,
}: {
  review?: ReviewData;
  loading: boolean;
  error: string;
  onLoadResearch: () => void;
}) {
  const comparisonCards = review?.comparison_cards || [];
  const panels = review?.research_panels || [];
  const lifecycleCards = review?.lifecycle_cards || [];
  const deferred = Boolean(review?.research_panels_deferred);
  return (
    <div className="space-y-4">
      <CompactMetricPanel
        title="基准 / 对比窗口"
        cards={comparisonCards}
        empty="暂无窗口对比。"
      />
      <CompactMetricPanel
        title="变化回放"
        cards={lifecycleCards}
        empty="暂无变化回放。"
      />
      <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3">
        <div className="mb-2 flex items-center gap-2">
          <FileText size={14} className="text-[var(--text-tertiary)]" />
          <div className="text-[12px] font-medium text-[var(--text-primary)]">
            研究拆解
          </div>
        </div>
        {panels.length ? (
          <div className="space-y-2">
            {panels.slice(0, 3).map((panel) => (
              <ResearchPanelMini
                key={`${panel.eyebrow}-${panel.title}`}
                panel={panel}
              />
            ))}
          </div>
        ) : loading ? (
          <div className="space-y-2">
            <SkeletonBlock className="h-16 w-full" />
            <SkeletonBlock className="h-16 w-full" />
          </div>
        ) : error ? (
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2 text-[12px] leading-5 text-[var(--text-secondary)]">
            {error}
            <button
              type="button"
              className="focus-ring ml-3 inline-flex h-7 items-center rounded-md border border-[var(--border-subtle)] px-2 text-[11px] text-[var(--text-primary)]"
              onClick={onLoadResearch}
            >
              重试
            </button>
          </div>
        ) : deferred ? (
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-3">
            <div className="text-[12px] leading-5 text-[var(--text-secondary)]">
              历史 research 拆解较重，默认不随证据状态一起读取。
            </div>
            <button
              type="button"
              className="focus-ring mt-3 inline-flex min-h-8 items-center gap-1.5 rounded-md border border-[var(--border-subtle)] px-2.5 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              onClick={onLoadResearch}
            >
              <RefreshCw size={13} />
              加载研究拆解
            </button>
          </div>
        ) : (
          <EmptyState>暂无研究拆解。</EmptyState>
        )}
      </div>
    </div>
  );
}

function CompactMetricPanel({
  title,
  cards,
  empty,
}: {
  title: string;
  cards: MetricCardData[];
  empty: string;
}) {
  return (
    <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3">
      <div className="mb-2 text-[12px] font-medium text-[var(--text-primary)]">
        {title}
      </div>
      {cards.length ? (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {cards.slice(0, 4).map((card, index) => (
            <MetricCard
              key={`${title}-${card.label}-${index}`}
              {...card}
              tone={card.tone || "info"}
            />
          ))}
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
          <div className="truncate text-[12px] font-medium text-[var(--text-primary)]">
            {panel.title}
          </div>
          {panel.summary ? (
            <div className="mt-1 line-clamp-2 text-[11px] text-[var(--text-tertiary)]">
              {panel.summary}
            </div>
          ) : null}
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

function OutcomeEvaluatorAction({
  calibration,
}: {
  calibration: ReturnType<typeof useDecisionLedgerCalibration>;
}) {
  const outcomeRun = useRunTask();
  const queryClient = useQueryClient();
  const canRun = Boolean(
    (calibration.data?.review_workbench?.overdue_count || 0) > 0,
  );
  const [feedback, setFeedback] = useState("");

  function runOutcomeEvaluator() {
    setFeedback("");
    outcomeRun.mutate(
      {
        taskName: "decision_ledger_outcomes",
        payload: {
          send_to_feishu: false,
          reason: "manual_from_review_decision_ledger",
        },
      },
      {
        onSuccess: (payload) => {
          setFeedback(
            `${payload.title || "结果评估"}已启动：${payload.run_id || payload.task_name || "后台任务"}。`,
          );
          window.setTimeout(() => void calibration.refetch(), 5_000);
          void queryClient.invalidateQueries({
            queryKey: queryKeys.decisionLedgerCalibrationDetail(
              REVIEW_CALIBRATION_PARAMS,
            ),
          });
        },
        onError: (error) =>
          setFeedback(error instanceof Error ? error.message : "启动失败。"),
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
          <div className="text-sm font-semibold text-[var(--text-primary)]">
            有成熟样本缺 outcome
          </div>
          <div className="mt-1 text-[12px] text-[var(--text-tertiary)]">
            先补齐结果证据，再进入归因或规则学习。
          </div>
        </div>
        <button
          type="button"
          onClick={runOutcomeEvaluator}
          disabled={outcomeRun.isPending}
          className={PRIMARY_ACTION_CLASS}
        >
          {outcomeRun.isPending ? (
            <LoaderCircle size={15} className="animate-spin" />
          ) : (
            <RefreshCw size={15} />
          )}
          补跑结果评估
        </button>
      </div>
      {feedback ? (
        <div className="mt-3 text-[12px] text-[var(--text-secondary)]">
          {feedback}
        </div>
      ) : null}
    </section>
  );
}

export function ReviewDecisionWorkspace() {
  const queryClient = useQueryClient();
  const calibration = useDecisionLedgerCalibration(REVIEW_CALIBRATION_PARAMS);
  const autoReview = useAutoReviewDecisionLedgerCase();
  const [autoReviewFeedback, setAutoReviewFeedback] = useState("");
  const autoReviewingDecisionId = autoReview.isPending
    ? autoReview.variables
    : undefined;

  function runAutoReview(decisionId?: string) {
    if (!decisionId) {
      return;
    }
    setAutoReviewFeedback("");
    autoReview.mutate(decisionId, {
      onSuccess: (response) => {
        const cause =
          response.review_case.primary_cause_label ||
          response.review_case.primary_cause ||
          "AI归因";
        const strength =
          response.review_case.evidence_strength_label || "观察假设";
        setAutoReviewFeedback(`已完成 AI 一键复盘：${cause}，${strength}。`);
        void calibration.refetch();
        void queryClient.invalidateQueries({
          queryKey: queryKeys.decisionLedgerCalibrationDetail(
            REVIEW_CALIBRATION_PARAMS,
          ),
        });
        void queryClient.invalidateQueries({
          queryKey: queryKeys.review(),
          refetchType: "active",
        });
      },
      onError: (error) => {
        setAutoReviewFeedback(
          error instanceof Error ? error.message : "AI 一键复盘失败。",
        );
      },
    });
  }

  const pageBadge = calibration.data?.needs_review_count
    ? `${calibration.data.needs_review_count} 条待归因`
    : "Decision Ledger";

  return (
    <>
      <PageTitle
        eyebrow="Review"
        title="Decision Ledger 学习台"
        summary="先处理待复盘队列；历史 research backfill 只作为底部证据，不再占据主流程。"
        icon={BookOpenCheck}
        badge={pageBadge}
        actions={
          <button
            type="button"
            className="focus-ring inline-flex items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)]"
            onClick={() => {
              void calibration.refetch();
              void queryClient.invalidateQueries({
                queryKey: queryKeys.decisionLedgerCalibrationDetail(
                  REVIEW_CALIBRATION_PARAMS,
                ),
              });
              void queryClient.invalidateQueries({
                queryKey: queryKeys.review(),
                refetchType: "active",
              });
              void queryClient.invalidateQueries({
                queryKey: queryKeys.reviewEvidence(),
                refetchType: "active",
              });
            }}
          >
            <RefreshCw
              size={14}
              className={calibration.isFetching ? "animate-spin" : ""}
            />
            重读数据
          </button>
        }
      />

      <DecisionLedgerHero
        data={calibration.data}
        loading={calibration.isLoading}
        fetching={calibration.isFetching}
        onRefetch={() => void calibration.refetch()}
        onAutoReview={runAutoReview}
        autoReviewingDecisionId={autoReviewingDecisionId}
      />
      {autoReviewFeedback ? (
        <div className="mb-7 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-4 py-3 text-[12px] leading-5 text-[var(--text-secondary)]">
          {autoReviewFeedback}
        </div>
      ) : null}
      <OutcomeEvaluatorAction calibration={calibration} />
      <ReviewQueue
        data={calibration.data}
        loading={calibration.isLoading}
        error={calibration.isError}
        onRetry={() => void calibration.refetch()}
        onAutoReview={runAutoReview}
        autoReviewingDecisionId={autoReviewingDecisionId}
      />
      <HistoricalShadowReplayGate />
      <LearningPatternsSection data={calibration.data} />
      <HistoricalDecisionLedgerGate />
      <EvidenceStatus />
    </>
  );
}
