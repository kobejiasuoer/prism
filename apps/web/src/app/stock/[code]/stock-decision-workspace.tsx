"use client";

import Link from "next/link";
import { ClipboardList } from "lucide-react";
import dynamic from "next/dynamic";

import { Badge } from "@/components/badge";
import {
  DataCard,
  EmptyState,
  Panel,
  SkeletonBlock,
} from "@/components/data-card";
import { MetricCard } from "@/components/metric-card";
import type {
  AskCaseData,
  StockDetailData,
  StockLearningScorecard,
  StockProfileData,
} from "@/lib/types";
import {
  StockDecisionCanonicalSummary,
  StockDecisionSupportPanels,
} from "./stock-decision-support";
import { displayText } from "./stock-display-utils";

type StockDecisionWorkspaceContext = {
  canonical_decision?: StockDetailData["canonical_decision"];
  decision_cards?: StockDetailData["decision_cards"];
  metric_cards?: AskCaseData["metric_cards"];
  level_cards?: StockDetailData["level_cards"];
  plan_levels?: StockDetailData["plan_levels"];
  execution_loop?: StockDetailData["execution_loop"];
  insight_groups?: StockDetailData["insight_groups"];
  tone?: StockDetailData["tone"];
};

export type StockDecisionHeroPanelsProps = {
  code: string;
  stockName: string;
  detail?: StockDecisionWorkspaceContext;
  askCase?: AskCaseData;
  decisionLocked: boolean;
  readiness?: StockProfileData["readiness"];
  sourceLabel: string;
  sourceTradeDate?: string;
  displayTradeDate?: string;
  sourceGeneratedAt?: string;
  todayAction?: StockProfileData["today_action"] | null;
  executionHref: string;
  learningScorecard?: StockLearningScorecard;
  learningScorecardLoading: boolean;
  onViewEvidence: () => void;
};

export type StockDecisionTabWorkspaceProps = {
  detail?: StockDecisionWorkspaceContext;
  askCase?: AskCaseData;
  sourceLabel: string;
  sourceGeneratedAt?: string;
  todayAction?: StockProfileData["today_action"] | null;
  executionHref: string;
  learningScorecard?: StockLearningScorecard;
  learningScorecardLoading: boolean;
  deferredInsightsEnabled: boolean;
  onLoadDeferredInsights: () => void;
  onContinueAsk: () => void;
};

type StockLearningScorecardPanelProps = {
  scorecard?: StockLearningScorecard;
  loading?: boolean;
  compact?: boolean;
};

const StockLearningScorecardPanel = dynamic<StockLearningScorecardPanelProps>(
  () =>
    import("./stock-learning-panels").then(
      (module) => module.StockLearningScorecardPanel,
    ),
  {
    ssr: false,
    loading: () => <SkeletonBlock className="h-40 w-full" />,
  },
);

const todayActionStatusCopy: Record<string, string> = {
  pending: "今日待处理",
  done: "今日已处理：已完成",
  watch: "今日已处理：继续观察中",
  skip: "今日已处理：已放弃",
  no_fill: "今日已处理：未成交，已记录",
};

function rowValueByLabel(
  rows: Array<{ label?: string; value?: unknown }> | undefined,
  labels: string[],
) {
  const match = (rows || []).find((row) => {
    const label = String(row.label || "");
    return labels.some((item) => label.includes(item));
  });
  return match?.value;
}

function todayActionStatusLabel(
  todayAction?: StockProfileData["today_action"] | null,
) {
  if (todayAction?.actionable === false) {
    return "今日动作不可执行";
  }
  const value = String(
    todayAction?.display_state?.value ||
      todayAction?.decision?.value ||
      "pending",
  );
  return todayActionStatusCopy[value] || todayActionStatusCopy.pending;
}

function todayActionTone(
  todayAction?: StockProfileData["today_action"] | null,
) {
  if (todayAction?.actionable === false) {
    return "risk";
  }
  return (
    todayAction?.display_state?.tone || todayAction?.decision?.tone || "watch"
  );
}

function todayActionIsProcessed(
  todayAction?: StockProfileData["today_action"] | null,
) {
  const value = String(
    todayAction?.display_state?.value ||
      todayAction?.decision?.value ||
      "pending",
  );
  return ["done", "watch", "skip", "no_fill"].includes(value);
}

function isObservationDecision(
  canonical: StockDetailData["canonical_decision"] | undefined,
  sourceLabel: string,
) {
  const text = [
    sourceLabel,
    canonical?.source_scope,
    canonical?.main_conclusion,
    canonical?.position_guidance,
    canonical?.next_step,
  ]
    .filter(Boolean)
    .join(" ");
  return /观察池|opportunity|观察|不新增动作|不建仓|先不新增|只保留/.test(text);
}

function DecisionLayerCard({
  detail,
  todayAction,
  stockName,
  code,
  executionHref,
  sourceLabel,
  observationMode,
}: {
  detail?: StockDecisionWorkspaceContext;
  todayAction?: StockProfileData["today_action"] | null;
  stockName: string;
  code: string;
  executionHref: string;
  sourceLabel: string;
  observationMode: boolean;
}) {
  const canonical = detail?.canonical_decision;
  const action = displayText(
    canonical?.next_step || canonical?.main_conclusion,
    observationMode ? "不建仓，只观察" : "按纪律处理",
  );
  const upgrade = displayText(
    canonical?.trigger_condition || canonical?.continue_condition,
    "等待触发条件明确",
  );
  const invalid = displayText(
    canonical?.stop_condition ||
      canonical?.risk_boundary ||
      canonical?.avoid_action,
    "触发失效条件就停止原计划",
  );
  const lineItems = [
    {
      label: "确认线",
      value: rowValueByLabel(detail?.plan_levels, ["触发位"]) || upgrade,
    },
    {
      label: "失效线",
      value: rowValueByLabel(detail?.plan_levels, ["失效位"]) || invalid,
    },
    {
      label: "支撑位",
      value:
        rowValueByLabel(detail?.plan_levels, ["回踩位"]) ||
        rowValueByLabel(detail?.level_cards, ["支撑"]),
    },
    {
      label: "压力位",
      value:
        rowValueByLabel(detail?.level_cards, ["压力"]) ||
        rowValueByLabel(detail?.plan_levels, ["触发位"]),
    },
  ];
  const processed = todayActionIsProcessed(todayAction);
  const entryLabel = processed
    ? "查看处理结果"
    : observationMode
      ? "记录观察结果"
      : "记录执行结果";

  return (
    <section className="surface-card p-4">
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,0.95fr)_minmax(280px,1fr)_300px]">
        <div>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <Badge tone="info">{sourceLabel}</Badge>
            <Badge tone={observationMode ? "watch" : "info"}>
              {observationMode ? "单票观察卡" : "单票动作卡"}
            </Badge>
          </div>
          <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">
            Current Decision
          </div>
          <h2 className="mt-1 text-2xl font-semibold text-[var(--text-primary)]">
            {stockName}
          </h2>
          <div className="mono mt-1 text-[12px] text-[var(--text-tertiary)]">
            {code}
          </div>
          <div className="mt-4 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
            <div className="text-[11px] text-[var(--text-tertiary)]">
              本票动作
            </div>
            <div className="mt-1 text-[17px] font-semibold leading-6 text-[var(--text-primary)]">
              {action}
            </div>
          </div>
          <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-1">
            <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
              <div className="text-[11px] text-[var(--text-tertiary)]">
                当前判断
              </div>
              <div className="mt-1 text-[13px] font-medium text-[var(--text-primary)]">
                {displayText(canonical?.main_conclusion)}
              </div>
            </div>
            <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
              <div className="text-[11px] text-[var(--text-tertiary)]">
                仓位纪律
              </div>
              <div className="mt-1 text-[13px] font-medium text-[var(--text-primary)]">
                {displayText(canonical?.position_guidance)}
              </div>
            </div>
          </div>
        </div>

        <div>
          <div className="mb-3">
            <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">
              Trigger Map
            </div>
            <h3 className="mt-1 text-base font-semibold text-[var(--text-primary)]">
              关键线与动作触发
            </h3>
          </div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {lineItems.map((item) => (
              <div
                key={item.label}
                className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3"
              >
                <div className="text-[11px] text-[var(--text-tertiary)]">
                  {item.label}
                </div>
                <div className="mt-1 text-[13px] font-semibold leading-5 text-[var(--text-primary)]">
                  {displayText(item.value)}
                </div>
              </div>
            ))}
          </div>
          <div className="mt-3 rounded-md border border-[color-mix(in_srgb,var(--tone-watch)_24%,transparent)] bg-[color-mix(in_srgb,var(--tone-watch)_8%,transparent)] px-3 py-3">
            <div className="text-[11px] text-[var(--text-tertiary)]">
              升级触发
            </div>
            <div className="mt-1 text-[13px] font-medium leading-5 text-[var(--text-primary)]">
              {upgrade}
            </div>
          </div>
          <div className="mt-2 rounded-md border border-[color-mix(in_srgb,var(--negative)_24%,transparent)] bg-[color-mix(in_srgb,var(--negative)_8%,transparent)] px-3 py-3">
            <div className="text-[11px] text-[var(--text-tertiary)]">
              失效条件
            </div>
            <div className="mt-1 text-[13px] font-medium leading-5 text-[var(--text-primary)]">
              {invalid}
            </div>
          </div>
        </div>

        <div>
          <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
            <div>
              <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">
                Today Record
              </div>
              <h3 className="mt-1 text-base font-semibold text-[var(--text-primary)]">
                处理状态
              </h3>
            </div>
            <Badge tone={todayActionTone(todayAction)}>
              {todayActionStatusLabel(todayAction)}
            </Badge>
          </div>
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
            <div className="text-[13px] font-semibold text-[var(--text-primary)]">
              {processed ? "已处理" : "待复核"}
            </div>
            <p className="mt-2 text-[12px] leading-5 text-[var(--text-secondary)]">
              {observationMode
                ? "观察票只记录复核、继续观察或放弃，不默认进入交易执行。"
                : "交易动作仍需外部券商手工完成，页面只做纪律回写。"}
            </p>
            {todayAction?.key ? (
              <div className="mt-3 flex flex-wrap gap-2">
                <Badge tone="info">{todayAction.key}</Badge>
                {todayAction.trade_date ? (
                  <Badge tone="info">交易日 {todayAction.trade_date}</Badge>
                ) : null}
              </div>
            ) : null}
          </div>
          <Link
            href={executionHref}
            className="focus-ring mt-3 inline-flex w-full items-center justify-center gap-2 rounded-md border border-[var(--accent)] bg-[var(--accent-soft)] px-3 py-2 text-[12px] font-medium text-[var(--accent)]"
          >
            <ClipboardList size={14} />
            {entryLabel}
          </Link>
        </div>
      </div>
    </section>
  );
}

export function StockDecisionHeroPanels({
  code,
  stockName,
  detail,
  askCase,
  decisionLocked,
  readiness,
  sourceLabel,
  sourceTradeDate,
  displayTradeDate,
  sourceGeneratedAt,
  todayAction,
  executionHref,
  learningScorecard,
  learningScorecardLoading,
  onViewEvidence,
}: StockDecisionHeroPanelsProps) {
  const decisionContext = detail || askCase;
  const observationMode = isObservationDecision(
    decisionContext?.canonical_decision,
    sourceLabel,
  );

  if (!decisionContext && !(decisionLocked && readiness)) {
    return null;
  }

  return (
    <div className="mb-6 flex flex-col gap-4">
      {!decisionLocked && decisionContext ? (
        <DecisionLayerCard
          detail={decisionContext}
          todayAction={todayAction}
          stockName={stockName}
          code={code}
          executionHref={executionHref}
          sourceLabel={sourceLabel}
          observationMode={observationMode}
        />
      ) : null}
      <StockDecisionSupportPanels
        decisionLocked={decisionLocked}
        detail={decisionContext}
        readiness={readiness}
        sourceLabel={sourceLabel}
        sourceTradeDate={sourceTradeDate}
        displayTradeDate={displayTradeDate}
        todayAction={todayAction}
        onViewEvidence={onViewEvidence}
      />
      {decisionLocked ? (
        <StockLearningScorecardPanel
          scorecard={learningScorecard}
          loading={learningScorecardLoading}
          compact
        />
      ) : null}
      {decisionLocked && decisionContext?.canonical_decision ? (
        <Panel title="旧结论只读摘要" eyebrow="Frozen Context">
          <StockDecisionCanonicalSummary
            canonical={decisionContext.canonical_decision}
            sourceLabel={sourceLabel}
            generatedAt={sourceGeneratedAt}
          />
        </Panel>
      ) : null}
    </div>
  );
}

export function StockDecisionTabWorkspace({
  detail,
  askCase,
  sourceLabel,
  sourceGeneratedAt,
  todayAction,
  executionHref,
  learningScorecard,
  learningScorecardLoading,
  deferredInsightsEnabled,
  onLoadDeferredInsights,
  onContinueAsk,
}: StockDecisionTabWorkspaceProps) {
  if (!detail && askCase) {
    const askFallbackCards = [
      ...(askCase.decision_cards || []),
      ...(askCase.metric_cards || []),
      ...(askCase.level_cards || []),
    ];

    return (
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="flex flex-col gap-6">
          <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {askFallbackCards.slice(0, 4).map((card, index) => (
              <MetricCard
                key={`${card.label}-${index}`}
                {...card}
                tone={
                  index === 0 ? askCase.tone || "info" : card.tone || "watch"
                }
              />
            ))}
            {!askFallbackCards.length ? (
              <EmptyState>暂无 Ask 指标卡。</EmptyState>
            ) : null}
          </section>

          <Panel
            title="Ask 主结论"
            eyebrow="Fallback"
            action={
              <button
                type="button"
                className="focus-ring rounded-md border border-[var(--border-subtle)] px-3 py-1.5 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                onClick={onContinueAsk}
              >
                继续追问
              </button>
            }
          >
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              {(askCase.execution_loop || []).slice(0, 4).map((card, index) => (
                <DataCard key={`${card.label}-${index}`} card={card} />
              ))}
              {!askCase.execution_loop?.length ? (
                <DataCard
                  card={{
                    title: askCase.hero?.decision_label || "当前结论",
                    detail:
                      askCase.hero?.summary ||
                      "Ask 已返回单股结论，可进入追问继续拆仓位、风险和证据。",
                    status: askCase.hero?.position,
                    tone: askCase.tone || "watch",
                  }}
                />
              ) : null}
            </div>
          </Panel>
        </div>

        <Panel title="决策摘要" eyebrow="Ask Canonical">
          <StockDecisionCanonicalSummary
            canonical={askCase.canonical_decision}
            sourceLabel="Ask 临时分析"
            generatedAt={sourceGeneratedAt}
          />
        </Panel>
      </div>
    );
  }

  if (!detail) {
    return null;
  }

  const observationMode = isObservationDecision(
    detail.canonical_decision,
    sourceLabel,
  );
  const executionEntryLabel = todayActionIsProcessed(todayAction)
    ? "查看处理结果"
    : observationMode
      ? "记录观察结果"
      : "记录执行结果";

  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
      <div className="flex flex-col gap-6">
        <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {(detail.decision_cards || []).slice(0, 4).map((card, index) => (
            <MetricCard
              key={`${card.label}-${index}`}
              {...card}
              tone={
                index === 0
                  ? detail.tone || "info"
                  : index === 2
                    ? "risk"
                    : "watch"
              }
            />
          ))}
        </section>

        <Panel title={observationMode ? "观察循环" : "执行循环"} eyebrow="Loop">
          <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-[12px] leading-5 text-[var(--text-tertiary)]">
              {observationMode
                ? "观察票先记录复核结果，不默认进入交易执行。"
                : "记录执行结果不会自动下单，只会进入执行回写区。"}
            </p>
            <Link
              href={executionHref}
              className="focus-ring inline-flex items-center justify-center gap-2 rounded-md border border-[var(--accent)] bg-[var(--accent-soft)] px-3 py-1.5 text-[12px] text-[var(--accent)]"
            >
              {executionEntryLabel}
            </Link>
          </div>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {(detail.execution_loop || []).map((card, index) => (
              <DataCard key={`${card.label}-${index}`} card={card} />
            ))}
            {!detail.execution_loop?.length ? (
              <EmptyState>暂无执行循环。</EmptyState>
            ) : null}
          </div>
        </Panel>
      </div>

      <div className="flex flex-col gap-6">
        <Panel title="决策摘要" eyebrow="Canonical">
          <StockDecisionCanonicalSummary
            canonical={detail.canonical_decision}
            sourceLabel={sourceLabel}
            generatedAt={sourceGeneratedAt}
          />
        </Panel>

        {deferredInsightsEnabled ? (
          <StockLearningScorecardPanel
            scorecard={learningScorecard}
            loading={learningScorecardLoading}
          />
        ) : (
          <Panel title="历史可信度按需加载" eyebrow="Read-only Learning">
            <div className="surface-card p-4">
              <div className="mb-3 text-[12px] leading-5 text-[var(--text-secondary)]">
                首屏先固定当前决策和执行条件；需要核对历史可信度、失败模式和
                Decision Ledger 时再加载。
              </div>
              <button
                type="button"
                className="focus-ring inline-flex h-8 items-center gap-1.5 rounded-md border border-[var(--border-subtle)] px-2.5 text-[11px] text-[var(--text-primary)]"
                onClick={onLoadDeferredInsights}
              >
                <ClipboardList size={12} />
                加载历史洞察
              </button>
            </div>
          </Panel>
        )}
      </div>
    </div>
  );
}
