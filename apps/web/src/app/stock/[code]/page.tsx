"use client";

import { Archive, ClipboardList, Database, FileSearch, LoaderCircle, Plus, RefreshCw, RotateCcw, SendHorizontal } from "lucide-react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { Badge } from "@/components/badge";
import { DataCard, EmptyState, ErrorState, Panel, SkeletonBlock } from "@/components/data-card";
import { EvidencePanel } from "@/components/evidence-panel";
import { LearningMemoryPreview } from "@/components/learning-memory";
import { MetricCard, MetricSkeleton } from "@/components/metric-card";
import { PageTitle } from "@/components/page-title";
import { TrustBanner } from "@/components/trust-banner";
import { api } from "@/lib/api";
import {
  useAddWatchlistStock,
  useArchiveWatchlistStock,
  useAsk,
  useDecisionLedgerStock,
  useRestoreWatchlistStock,
  useStockProfile,
  useWatchlistManager,
} from "@/lib/hooks";
import { readinessHasStaleData, readinessModeCopy, refreshTaskCopy } from "@/lib/readiness-copy";
import type {
  AskFollowupResponse,
  DecisionLedgerCompactRecord,
  StockDetailData,
  StockFormalData,
  StockProfileData,
  WatchlistManagerItem,
} from "@/lib/types";
import { cn } from "@/lib/utils";

const tabs = ["决策", "追问", "持仓", "发现", "证据"] as const;
type StockTab = (typeof tabs)[number];
type StockProfileSource = NonNullable<StockProfileData["available_sources"]>[number];
const followupHistoryTurnLimit = 3;
const profileSourceIssueLabels: Record<StockProfileSource, string> = {
  watchlist: "自选股未命中",
  opportunity: "观察池未命中",
};

type DecisionContext = {
  canonical_decision?: StockDetailData["canonical_decision"];
  decision_cards?: StockDetailData["decision_cards"];
  level_cards?: StockDetailData["level_cards"];
  plan_rows?: StockDetailData["plan_rows"];
  plan_levels?: StockDetailData["plan_levels"];
  triggers?: StockDetailData["triggers"];
  insight_groups?: StockDetailData["insight_groups"];
  source_cards?: StockDetailData["source_cards"];
  artifacts?: StockDetailData["artifacts"];
  trade_date?: string;
  generated_at?: string;
};

const todayActionStatusCopy: Record<string, string> = {
  pending: "今日待处理",
  done: "今日已处理：已完成",
  watch: "今日已处理：继续观察中",
  skip: "今日已处理：已放弃",
  no_fill: "今日已处理：未成交，已记录",
};

function pickDetail(profile?: StockProfileData, activeTab?: string) {
  if (activeTab === "发现" && profile?.opportunity) {
    return profile.opportunity;
  }
  return profile?.primary_detail || profile?.watchlist || profile?.opportunity;
}

function sourceIssueBadges(profile?: StockProfileData) {
  const errors = profile?.errors || {};
  return (Object.keys(profileSourceIssueLabels) as StockProfileSource[])
    .filter((source) => errors[source] && !profile?.[source])
    .map((source) => ({
      key: source,
      label: profileSourceIssueLabels[source],
    }));
}

function findManagerItem(items: WatchlistManagerItem[] | undefined, code: string) {
  return (items || []).find((item) => item.code === code);
}

function canonicalText(
  canonical: StockDetailData["canonical_decision"] | undefined,
  key: string,
  fallback = "-",
) {
  const value = canonical?.[key];
  if (value === null || value === undefined || value === "") {
    return fallback;
  }
  return String(value);
}

function hasDisplayValue(value: unknown) {
  if (value === null || value === undefined) {
    return false;
  }
  const text = String(value).trim();
  return Boolean(text && text !== "-");
}

function displayText(value: unknown, fallback = "暂未给出") {
  return hasDisplayValue(value) ? String(value) : fallback;
}

function uniqueTexts(values: unknown[]) {
  const seen = new Set<string>();
  return values
    .map((value) => displayText(value, ""))
    .filter(Boolean)
    .filter((value) => {
      if (seen.has(value)) {
        return false;
      }
      seen.add(value);
      return true;
    });
}

function sourceScopeLabel(value: unknown) {
  switch (String(value || "")) {
    case "holdings":
      return "自选股链路";
    case "opportunity":
      return "观察池链路";
    case "live_fallback":
      return "Ask 临时分析";
    default:
      return String(value || "当前链路");
  }
}

function triggerCard(trigger: NonNullable<StockDetailData["triggers"]>[number], index: number) {
  const condition = trigger.condition || trigger.value || trigger.detail || "";
  const action = trigger.action || "";
  return {
    title: trigger.name || trigger.label || `触发 ${index + 1}`,
    detail: [condition, action].filter(Boolean).join(" / "),
    tone: "watch",
  };
}

function rowValueByLabel(rows: Array<{ label?: string; value?: unknown }> | undefined, labels: string[]) {
  const match = (rows || []).find((row) => {
    const label = String(row.label || "");
    return labels.some((item) => label.includes(item));
  });
  return match?.value;
}

function triggerTextByKeyword(triggers: StockDetailData["triggers"] | undefined, keywords: string[]) {
  const match = (triggers || []).find((trigger) => {
    const text = [trigger.name, trigger.label, trigger.condition, trigger.detail, trigger.action].filter(Boolean).join(" ");
    return keywords.some((keyword) => text.includes(keyword));
  });
  if (!match) {
    return "";
  }
  return [match.condition || match.value || match.detail, match.action].filter(Boolean).join(" / ");
}

function insightItems(detail: DecisionContext | undefined, keywords: string[]) {
  return (detail?.insight_groups || [])
    .filter((group) => keywords.some((keyword) => String(group.title || "").includes(keyword)))
    .flatMap((group) => group.items || []);
}

function todayActionStatusLabel(todayAction?: StockProfileData["today_action"]) {
  if (todayAction?.actionable === false) {
    return "今日动作不可执行";
  }
  const value = String(todayAction?.display_state?.value || todayAction?.decision?.value || "pending");
  return todayActionStatusCopy[value] || todayActionStatusCopy.pending;
}

function todayActionTone(todayAction?: StockProfileData["today_action"]) {
  if (todayAction?.actionable === false) {
    return "risk";
  }
  return todayAction?.display_state?.tone || todayAction?.decision?.tone || "watch";
}

function todayActionIsProcessed(todayAction?: StockProfileData["today_action"]) {
  const value = String(todayAction?.display_state?.value || todayAction?.decision?.value || "pending");
  return ["done", "watch", "skip", "no_fill"].includes(value);
}

function isObservationDecision(canonical: StockDetailData["canonical_decision"] | undefined, sourceLabel: string) {
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

function conditionalActionText(canonical?: StockDetailData["canonical_decision"]) {
  const trigger = displayText(canonical?.trigger_condition || canonical?.stop_condition || canonical?.continue_condition);
  const action = displayText(canonical?.next_step || canonical?.avoid_action);
  if (trigger !== "暂未给出" && action !== "暂未给出") {
    return `${trigger} -> ${action}`;
  }
  return trigger !== "暂未给出" ? trigger : action;
}

function keyConditions(detail: DecisionContext | undefined) {
  const canonical = detail?.canonical_decision;
  const levelCards = detail?.level_cards || [];
  const planRows = detail?.plan_rows || [];
  const planLevels = detail?.plan_levels || [];
  return [
    {
      label: "仓位纪律",
      value: canonical?.position_guidance || rowValueByLabel(planRows, ["仓位"]),
    },
    {
      label: "止损 / 失效线",
      value:
        canonical?.stop_condition ||
        canonical?.risk_boundary ||
        rowValueByLabel(levelCards, ["止损", "失效"]) ||
        rowValueByLabel(planRows, ["失效"]) ||
        rowValueByLabel(planLevels, ["失效"]),
    },
    {
      label: "支撑位",
      value: rowValueByLabel(levelCards, ["支撑"]) || rowValueByLabel(planLevels, ["回踩"]),
    },
    {
      label: "压力位",
      value: rowValueByLabel(levelCards, ["压力"]),
    },
    {
      label: "确认线",
      value:
        triggerTextByKeyword(detail?.triggers, ["确认"]) ||
        rowValueByLabel(planLevels, ["触发"]) ||
        canonical?.trigger_condition,
    },
    {
      label: "继续观察条件",
      value: canonical?.continue_condition || canonical?.trigger_condition || rowValueByLabel(planRows, ["触发"]),
    },
    {
      label: "放弃条件",
      value: canonical?.avoid_action || canonical?.stop_condition || canonical?.risk_boundary || rowValueByLabel(planRows, ["回避"]),
    },
  ];
}

function evidenceSourceSummary(detail: DecisionContext | undefined, sourceLabel: string, todayAction?: StockProfileData["today_action"]) {
  const labels = uniqueTexts([
    sourceLabel,
    ...(detail?.source_cards || []).map((item) => item.label),
    ...(detail?.artifacts || []).map((item) => item.label),
    todayAction ? "今日动作队列" : "",
  ]);
  return labels.length ? labels.slice(0, 4).join("、") : "自选股快照、持仓链路、今日动作队列";
}

function evidenceSupportItems(detail: DecisionContext | undefined) {
  const canonical = detail?.canonical_decision;
  const conclusionCard = (detail?.decision_cards || []).find((card) => String(card.label || "").includes("当前结论"));
  const positives = insightItems(detail, ["正向", "加分", "支持"]);
  return uniqueTexts([
    canonical?.why_now,
    conclusionCard?.detail,
    ...positives,
    canonical?.confidence_note,
  ]).slice(0, 3);
}

function evidenceRiskItems(
  detail: DecisionContext | undefined,
  readiness: StockProfileData["readiness"] | undefined,
) {
  const canonical = detail?.canonical_decision;
  const risks = insightItems(detail, ["风险", "警示", "硬风险"]);
  const session = readiness?.session;
  return uniqueTexts([
    canonical?.stop_condition || canonical?.risk_boundary,
    canonical?.avoid_action,
    ...risks,
    readiness?.stale_count ? "数据偏旧" : "",
    session?.key === "weekend" ? "周末休市不可真钱执行" : "",
  ]).slice(0, 4);
}

function readinessFacts(readiness?: StockProfileData["readiness"]) {
  const mode = readiness?.readiness_mode || "blocked";
  const session = readiness?.session;
  const isWeekend = session?.key === "weekend" || session?.calendar_status === "weekend";
  const isTradingDay = Boolean(session?.is_trading_day);
  const dataStale = readinessHasStaleData(readiness);
  const allowRealMoney = mode === "live_ready" && isTradingDay && !dataStale && Boolean(readiness?.ready);
  return { mode, session, isWeekend, isTradingDay, dataStale, allowRealMoney };
}

function TradingAvailabilityBar({ readiness }: { readiness?: StockProfileData["readiness"] }) {
  const { mode, session, isWeekend, dataStale, allowRealMoney } = readinessFacts(readiness);
  const modeTone = mode === "live_ready" ? "positive" : mode === "blocked" ? "risk" : "warning";
  const copy = readinessModeCopy(mode);
  const recommendedTask = readiness?.recommended_tasks?.[0];
  const recommendedTaskTitle = recommendedTask ? refreshTaskCopy(recommendedTask).title : "";
  const statusLines = [
    allowRealMoney ? "环境允许手工执行；本票仍按上方动作卡判断。" : "环境不允许真钱执行。",
    isWeekend ? "周末休市，仅可影子盘观察" : "",
    dataStale ? "数据偏旧，不可作为真钱依据" : "",
    copy.title,
    recommendedTask && mode !== "live_ready" ? `建议下一步：去 Settings 运行 ${recommendedTaskTitle || recommendedTask}` : "",
    "真实成交仍需在外部券商完成，本系统不会自动下单。",
  ].filter(Boolean);

  const facts = [
    { label: "当前状态", value: copy.title, tone: modeTone },
    { label: "是否周末休市", value: isWeekend ? "是" : "否", tone: isWeekend ? "warning" : "info" },
    { label: "是否数据过期", value: dataStale ? "是" : "否", tone: dataStale ? "warning" : "positive" },
    { label: "真钱手工执行环境", value: allowRealMoney ? "是" : "否", tone: allowRealMoney ? "positive" : "risk" },
  ];

  return (
    <section className="surface-card border-[var(--border-subtle)] p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">System Environment</div>
          <h2 className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
            {allowRealMoney ? "系统环境：交易链路可用" : "系统环境：不可作为真钱依据"}
          </h2>
          <p className="mt-2 text-[12px] leading-5 text-[var(--text-secondary)]">
            {session?.label || "交易状态待确认"}；{copy.title}。这是环境状态，不代表本票可动作；本票动作以上方单票卡为准。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge tone={modeTone}>{copy.badge}</Badge>
          <Badge tone={allowRealMoney ? "positive" : "risk"}>{allowRealMoney ? "环境允许手工执行" : "环境禁止真钱执行"}</Badge>
        </div>
      </div>
      <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-4">
        {facts.map((item) => (
          <div key={item.label} className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
            <div className="text-[11px] text-[var(--text-tertiary)]">{item.label}</div>
            <div className="mt-1 flex items-center justify-between gap-2 text-[13px] font-medium text-[var(--text-primary)]">
              <span>{item.value}</span>
              <Badge tone={item.tone}>{item.value}</Badge>
            </div>
          </div>
        ))}
      </div>
      <div className="mt-3 rounded-md border border-[color-mix(in_srgb,var(--tone-watch)_24%,transparent)] bg-[color-mix(in_srgb,var(--tone-watch)_8%,transparent)] px-3 py-2 text-[12px] leading-5 text-[var(--text-secondary)]">
        {statusLines.map((line) => (
          <div key={line}>{line}</div>
        ))}
      </div>
    </section>
  );
}

function DataFreshnessGate({
  readiness,
  sourceTradeDate,
  onViewEvidence,
}: {
  readiness?: StockProfileData["readiness"];
  sourceTradeDate?: string;
  onViewEvidence: () => void;
}) {
  const { mode, dataStale } = readinessFacts(readiness);
  const locked = mode !== "live_ready" || dataStale;
  if (!locked) {
    return null;
  }
  const copy = readinessModeCopy(mode);
  const recommendedTask = readiness?.recommended_tasks?.[0];
  const recommendedTaskTitle = recommendedTask ? refreshTaskCopy(recommendedTask).title : "";

  return (
    <section className="surface-card border-[color-mix(in_srgb,var(--negative)_32%,transparent)] bg-[color-mix(in_srgb,var(--negative)_8%,transparent)] p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <Badge tone="risk">交易判断冻结</Badge>
            <Badge tone="warning">{copy.title}</Badge>
          </div>
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">不使用当前页面内容判断今天是否交易</h2>
          <p className="mt-2 text-[12px] leading-5 text-[var(--text-secondary)]">
            数据新鲜度未通过时，研究结论、仓位纪律、关键条件和执行入口都不作为今天依据。
            当前仅保留只读证据和刷新指引。
          </p>
        </div>
        <Link
          href="/settings"
          className="focus-ring inline-flex shrink-0 items-center justify-center rounded-md border border-[var(--border-strong)] bg-[var(--bg-secondary)] px-3 py-2 text-[12px] font-medium text-[var(--text-primary)]"
        >
          去 Settings 刷新
        </Link>
      </div>
      <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-3">
        <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
          <div className="text-[11px] text-[var(--text-tertiary)]">预期交易日</div>
          <div className="mt-1 text-[13px] font-medium text-[var(--text-primary)]">{readiness?.expected_trade_date || "-"}</div>
        </div>
        <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
          <div className="text-[11px] text-[var(--text-tertiary)]">当前数据交易日</div>
          <div className="mt-1 text-[13px] font-medium text-[var(--text-primary)]">{readiness?.data_trade_date || sourceTradeDate || "-"}</div>
        </div>
        <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
          <div className="text-[11px] text-[var(--text-tertiary)]">建议刷新</div>
          <div className="mt-1 text-[13px] font-medium text-[var(--text-primary)]">{recommendedTaskTitle || recommendedTask || "先回 Settings 看推荐任务"}</div>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          className="focus-ring rounded-md border border-[var(--border-subtle)] px-3 py-1.5 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
          onClick={onViewEvidence}
        >
          只读查看证据
        </button>
      </div>
    </section>
  );
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
  detail?: DecisionContext;
  todayAction?: StockProfileData["today_action"];
  stockName: string;
  code: string;
  executionHref: string;
  sourceLabel: string;
  observationMode: boolean;
}) {
  const canonical = detail?.canonical_decision;
  const action = displayText(canonical?.next_step || canonical?.main_conclusion, observationMode ? "不建仓，只观察" : "按纪律处理");
  const upgrade = displayText(canonical?.trigger_condition || canonical?.continue_condition, "等待触发条件明确");
  const invalid = displayText(canonical?.stop_condition || canonical?.risk_boundary || canonical?.avoid_action, "触发失效条件就停止原计划");
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
      value: rowValueByLabel(detail?.plan_levels, ["回踩位"]) || rowValueByLabel(detail?.level_cards, ["支撑"]),
    },
    {
      label: "压力位",
      value: rowValueByLabel(detail?.level_cards, ["压力"]) || rowValueByLabel(detail?.plan_levels, ["触发位"]),
    },
  ];
  const processed = todayActionIsProcessed(todayAction);
  const entryLabel = processed ? "查看处理结果" : observationMode ? "记录观察结果" : "记录执行结果";

  return (
    <section className="surface-card p-4">
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,0.95fr)_minmax(280px,1fr)_300px]">
        <div>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <Badge tone="info">{sourceLabel}</Badge>
            <Badge tone={observationMode ? "watch" : "info"}>{observationMode ? "单票观察卡" : "单票动作卡"}</Badge>
          </div>
          <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">Current Decision</div>
          <h2 className="mt-1 text-2xl font-semibold text-[var(--text-primary)]">{stockName}</h2>
          <div className="mono mt-1 text-[12px] text-[var(--text-tertiary)]">{code}</div>
          <div className="mt-4 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
            <div className="text-[11px] text-[var(--text-tertiary)]">本票动作</div>
            <div className="mt-1 text-[17px] font-semibold leading-6 text-[var(--text-primary)]">{action}</div>
          </div>
          <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-1">
            <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
              <div className="text-[11px] text-[var(--text-tertiary)]">当前判断</div>
              <div className="mt-1 text-[13px] font-medium text-[var(--text-primary)]">{displayText(canonical?.main_conclusion)}</div>
            </div>
            <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
              <div className="text-[11px] text-[var(--text-tertiary)]">仓位纪律</div>
              <div className="mt-1 text-[13px] font-medium text-[var(--text-primary)]">{displayText(canonical?.position_guidance)}</div>
            </div>
          </div>
        </div>

        <div>
          <div className="mb-3">
            <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">Trigger Map</div>
            <h3 className="mt-1 text-base font-semibold text-[var(--text-primary)]">关键线与动作触发</h3>
          </div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {lineItems.map((item) => (
              <div key={item.label} className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
                <div className="text-[11px] text-[var(--text-tertiary)]">{item.label}</div>
                <div className="mt-1 text-[13px] font-semibold leading-5 text-[var(--text-primary)]">{displayText(item.value)}</div>
              </div>
            ))}
          </div>
          <div className="mt-3 rounded-md border border-[color-mix(in_srgb,var(--tone-watch)_24%,transparent)] bg-[color-mix(in_srgb,var(--tone-watch)_8%,transparent)] px-3 py-3">
            <div className="text-[11px] text-[var(--text-tertiary)]">升级触发</div>
            <div className="mt-1 text-[13px] font-medium leading-5 text-[var(--text-primary)]">{upgrade}</div>
          </div>
          <div className="mt-2 rounded-md border border-[color-mix(in_srgb,var(--negative)_24%,transparent)] bg-[color-mix(in_srgb,var(--negative)_8%,transparent)] px-3 py-3">
            <div className="text-[11px] text-[var(--text-tertiary)]">失效条件</div>
            <div className="mt-1 text-[13px] font-medium leading-5 text-[var(--text-primary)]">{invalid}</div>
          </div>
        </div>

        <div>
          <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
            <div>
              <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">Today Record</div>
              <h3 className="mt-1 text-base font-semibold text-[var(--text-primary)]">处理状态</h3>
            </div>
            <Badge tone={todayActionTone(todayAction)}>{todayActionStatusLabel(todayAction)}</Badge>
          </div>
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
            <div className="text-[13px] font-semibold text-[var(--text-primary)]">{processed ? "已处理" : "待复核"}</div>
            <p className="mt-2 text-[12px] leading-5 text-[var(--text-secondary)]">
              {observationMode ? "观察票只记录复核、继续观察或放弃，不默认进入交易执行。" : "交易动作仍需外部券商手工完成，页面只做纪律回写。"}
            </p>
            {todayAction?.key ? (
              <div className="mt-3 flex flex-wrap gap-2">
                <Badge tone="info">{todayAction.key}</Badge>
                {todayAction.trade_date ? <Badge tone="info">交易日 {todayAction.trade_date}</Badge> : null}
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

function TodayActionStatusCard({
  todayAction,
  executionHref,
}: {
  todayAction?: StockProfileData["today_action"];
  executionHref: string;
}) {
  const status = todayActionStatusLabel(todayAction);
  const processed = todayActionIsProcessed(todayAction);
  const readonlyReason = todayAction?.actionable === false
    ? todayAction.confidence?.note || "readiness 未就绪，这条记录只作为线索复核。"
    : "";
  return (
    <section className="surface-card p-4">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">Today State</div>
          <h2 className="mt-1 text-lg font-semibold text-[var(--text-primary)]">今日处理状态</h2>
        </div>
        <Badge tone={todayActionTone(todayAction)}>{status}</Badge>
      </div>
      <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
        <div className="text-[15px] font-semibold text-[var(--text-primary)]">{status}</div>
        <p className="mt-2 text-[12px] leading-5 text-[var(--text-secondary)]">
          {readonlyReason || "这是用户今天的处理记录，不是系统研究结论。"}
        </p>
        {todayAction?.key ? (
          <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-[var(--text-tertiary)]">
            <Badge tone="info">{todayAction.key}</Badge>
            {todayAction.trade_date ? <Badge tone="info">交易日 {todayAction.trade_date}</Badge> : null}
            {todayAction.actionable === false ? <Badge tone="risk">只读线索</Badge> : null}
            {todayAction.display_state?.updated_at ? <Badge tone={todayActionTone(todayAction)}>更新 {todayAction.display_state.updated_at}</Badge> : null}
          </div>
        ) : null}
      </div>
      <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-[12px] leading-5 text-[var(--text-tertiary)]">记录执行结果不会自动下单，只会进入执行回写区。</p>
        <Link
          href={executionHref}
          className="focus-ring inline-flex shrink-0 items-center justify-center rounded-md border border-[var(--accent)] bg-[var(--accent-soft)] px-3 py-2 text-[12px] font-medium text-[var(--accent)]"
        >
          {processed ? "查看处理结果" : "记录执行结果"}
        </Link>
      </div>
    </section>
  );
}

function KeyConditionsCard({ detail }: { detail?: DecisionContext }) {
  return (
    <section className="surface-card p-4">
      <div className="mb-3">
        <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">Key Conditions</div>
        <h2 className="mt-1 text-lg font-semibold text-[var(--text-primary)]">关键条件</h2>
      </div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {keyConditions(detail).map((item) => (
          <div key={item.label} className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
            <div className="text-[11px] text-[var(--text-tertiary)]">{item.label}</div>
            <div className="mt-1 text-[13px] font-medium leading-5 text-[var(--text-primary)]">{displayText(item.value)}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

function EvidenceCredibilityCard({
  detail,
  readiness,
  sourceLabel,
  sourceTradeDate,
  todayAction,
  onViewEvidence,
}: {
  detail?: DecisionContext;
  readiness?: StockProfileData["readiness"];
  sourceLabel: string;
  sourceTradeDate?: string;
  todayAction?: StockProfileData["today_action"];
  onViewEvidence: () => void;
}) {
  const { mode, dataStale } = readinessFacts(readiness);
  const copy = readinessModeCopy(mode);
  const support = evidenceSupportItems(detail);
  const risks = evidenceRiskItems(detail, readiness);
  const dataStatus = [copy.title, dataStale ? "数据偏旧" : "数据新鲜"].filter(Boolean).join(" / ");

  return (
    <section className="surface-card p-4">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">Evidence</div>
          <h2 className="mt-1 text-lg font-semibold text-[var(--text-primary)]">证据可信度</h2>
        </div>
        <Badge tone={dataStale ? "warning" : "positive"}>{dataStatus}</Badge>
      </div>
      <div className="space-y-3 text-[12px] leading-5 text-[var(--text-secondary)]">
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
            <div className="text-[11px] text-[var(--text-tertiary)]">数据交易日</div>
            <div className="mt-1 font-medium text-[var(--text-primary)]">{displayText(readiness?.data_trade_date || sourceTradeDate)}</div>
          </div>
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
            <div className="text-[11px] text-[var(--text-tertiary)]">证据来源</div>
            <div className="mt-1 font-medium text-[var(--text-primary)]">{evidenceSourceSummary(detail, sourceLabel, todayAction)}</div>
          </div>
        </div>
        <div>
          <div className="mb-1 font-medium text-[var(--text-primary)]">支持当前结论：</div>
          <ul className="list-disc space-y-1 pl-4">
            {(support.length ? support : ["暂无结构化支持摘要"]).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
        <div>
          <div className="mb-1 font-medium text-[var(--text-primary)]">主要风险：</div>
          <ul className="list-disc space-y-1 pl-4">
            {(risks.length ? risks : ["暂无结构化风险摘要"]).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      </div>
      <button
        type="button"
        className="focus-ring mt-3 inline-flex items-center rounded-md border border-[var(--border-subtle)] px-3 py-1.5 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
        onClick={onViewEvidence}
      >
        查看证据 →
      </button>
    </section>
  );
}

function ObservationDecisionBlocks({
  detail,
  readiness,
  sourceLabel,
  sourceTradeDate,
  todayAction,
  onViewEvidence,
}: {
  detail?: DecisionContext;
  readiness?: StockProfileData["readiness"];
  sourceLabel: string;
  sourceTradeDate?: string;
  todayAction?: StockProfileData["today_action"];
  onViewEvidence: () => void;
}) {
  const canonical = detail?.canonical_decision;
  const { mode, dataStale } = readinessFacts(readiness);
  const copy = readinessModeCopy(mode);
  const support = evidenceSupportItems(detail);
  const risks = evidenceRiskItems(detail, readiness);
  const dataStatus = [copy.title, dataStale ? "数据偏旧" : "数据新鲜"].filter(Boolean).join(" / ");
  const primaryRisk = (risks[0] || "暂无额外风险摘要").replace(/[。.!！]$/, "");
  const blocks = [
    {
      title: "为什么入池",
      eyebrow: "Reason",
      value: canonical?.why_now || support[0],
      detail: support.slice(1).join("；") || canonical?.confidence_note || "先按入池主因判断是否还值得盯。",
      tone: "info",
    },
    {
      title: "什么时候升级",
      eyebrow: "Upgrade",
      value: canonical?.trigger_condition || canonical?.continue_condition,
      detail: canonical?.next_step || "满足触发条件后再重新评估动作。",
      tone: "watch",
    },
    {
      title: "什么时候放弃",
      eyebrow: "Invalid",
      value: canonical?.stop_condition || canonical?.risk_boundary,
      detail: canonical?.avoid_action || risks[0] || "触发失效条件就先停止原计划。",
      tone: "risk",
    },
  ];

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-4">
      {blocks.map((block) => (
        <section key={block.title} className="surface-card p-4">
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">{block.eyebrow}</div>
            <Badge tone={block.tone}>{block.title}</Badge>
          </div>
          <div className="text-[14px] font-semibold leading-6 text-[var(--text-primary)]">{displayText(block.value)}</div>
          <p className="mt-2 text-[12px] leading-5 text-[var(--text-secondary)]">{displayText(block.detail, "暂无补充说明")}</p>
        </section>
      ))}

      <section className="surface-card p-4">
        <div className="mb-2 flex items-center justify-between gap-2">
          <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">Evidence</div>
          <Badge tone={dataStale ? "warning" : "positive"}>{dataStatus}</Badge>
        </div>
        <div className="text-[14px] font-semibold leading-6 text-[var(--text-primary)]">
          {evidenceSourceSummary(detail, sourceLabel, todayAction)}
        </div>
        <p className="mt-2 text-[12px] leading-5 text-[var(--text-secondary)]">
          数据交易日 {displayText(readiness?.data_trade_date || sourceTradeDate)}；{primaryRisk}。
        </p>
        <button
          type="button"
          className="focus-ring mt-3 inline-flex items-center rounded-md border border-[var(--border-subtle)] px-3 py-1.5 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
          onClick={onViewEvidence}
        >
          查看证据 →
        </button>
      </section>
    </div>
  );
}

function recordField(row: Record<string, unknown> | undefined, keys: string[], fallback = "-") {
  if (!row) {
    return fallback;
  }
  for (const key of keys) {
    const value = row[key];
    if (hasDisplayValue(value)) {
      return String(value);
    }
  }
  return fallback;
}

function FormalDataSnapshotPanel({ data }: { data?: StockFormalData }) {
  if (!data?.available) {
    return null;
  }
  const cards = data.metric_cards || [];
  const indexRows = data.index_memberships || [];
  const topRows = data.top_list || [];
  const holderRows = data.shareholders || [];
  const dividendRows = data.dividends || [];

  return (
    <Panel
      title="Tushare 档案"
      eyebrow="Formal Data"
      action={
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="positive">{data.provider || "tushare/tinyshare"}</Badge>
          {data.trade_date ? <Badge tone="info">交易日 {data.trade_date}</Badge> : null}
        </div>
      }
    >
      <div className="surface-card p-4">
        <div className="mb-4 flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
            <Database size={17} className="text-[var(--positive)]" />
          </div>
          <div>
            <h2 className="text-[15px] font-semibold text-[var(--text-primary)]">{data.headline || "Tushare 数据已接入个股档案"}</h2>
            <p className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
              {data.summary || "估值、资金流、财务、股东、分红和指数权重以只读研究证据展示。"}
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {cards.slice(0, 8).map((card, index) => (
            <MetricCard key={`${card.label}-${index}`} {...card} tone={card.tone || (index < 2 ? "info" : "watch")} />
          ))}
        </div>

        <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-[12px] font-medium text-[var(--text-primary)]">指数权重</span>
              <Badge tone={indexRows.length ? "positive" : "info"}>{indexRows.length} 个指数</Badge>
            </div>
            <div className="grid gap-1.5">
              {indexRows.slice(0, 4).map((row, index) => (
                <div key={`${recordField(row, ["index_code"])}-${index}`} className="flex items-center justify-between gap-2 text-[12px]">
                  <span className="mono text-[var(--text-secondary)]">{recordField(row, ["index_code"])}</span>
                  <span className="text-[var(--text-primary)]">{recordField(row, ["weight"])}%</span>
                </div>
              ))}
              {!indexRows.length ? <span className="text-[12px] text-[var(--text-tertiary)]">未命中已补采指数。</span> : null}
            </div>
          </div>

          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-[12px] font-medium text-[var(--text-primary)]">龙虎榜</span>
              <Badge tone={topRows.length ? "watch" : "info"}>{topRows.length} 次</Badge>
            </div>
            <div className="grid gap-1.5">
              {topRows.slice(0, 3).map((row, index) => (
                <div key={`${recordField(row, ["trade_date"])}-${index}`} className="text-[12px] leading-5 text-[var(--text-secondary)]">
                  {recordField(row, ["trade_date"])} · 涨跌 {recordField(row, ["pct_change"])} · 净买 {recordField(row, ["net_amount", "net_buy"])}
                </div>
              ))}
              {!topRows.length ? <span className="text-[12px] text-[var(--text-tertiary)]">近窗口没有龙虎榜命中。</span> : null}
            </div>
          </div>

          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-[12px] font-medium text-[var(--text-primary)]">前十大股东</span>
              <Badge tone={holderRows.length ? "info" : "warning"}>{holderRows.length} 条</Badge>
            </div>
            <div className="grid gap-1.5">
              {holderRows.slice(0, 4).map((row, index) => (
                <div key={`${recordField(row, ["holder_name"])}-${index}`} className="flex items-start justify-between gap-2 text-[12px]">
                  <span className="line-clamp-1 text-[var(--text-secondary)]">{recordField(row, ["holder_name"])}</span>
                  <span className="shrink-0 text-[var(--text-primary)]">{recordField(row, ["hold_ratio"])}%</span>
                </div>
              ))}
              {!holderRows.length ? <span className="text-[12px] text-[var(--text-tertiary)]">暂无股东结构命中。</span> : null}
            </div>
          </div>

          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-[12px] font-medium text-[var(--text-primary)]">分红送配</span>
              <Badge tone={dividendRows.length ? "info" : "warning"}>{dividendRows.length} 条</Badge>
            </div>
            <div className="grid gap-1.5">
              {dividendRows.slice(0, 3).map((row, index) => (
                <div key={`${recordField(row, ["end_date", "ann_date"])}-${index}`} className="text-[12px] leading-5 text-[var(--text-secondary)]">
                  {recordField(row, ["end_date", "ann_date"])} · 派息 {recordField(row, ["cash_div_tax", "cash_div"])} · 进度 {recordField(row, ["div_proc"])}
                </div>
              ))}
              {!dividendRows.length ? <span className="text-[12px] text-[var(--text-tertiary)]">暂无分红记录命中。</span> : null}
            </div>
          </div>
        </div>
      </div>
    </Panel>
  );
}

function DecisionSummary({
  canonical,
  sourceLabel,
  generatedAt,
  embedded = false,
}: {
  canonical?: StockDetailData["canonical_decision"];
  sourceLabel: string;
  generatedAt?: string;
  embedded?: boolean;
}) {
  if (!canonical) {
    return <EmptyState>暂无标准化摘要。</EmptyState>;
  }

  const rows = [
    {
      label: "系统位置",
      value: sourceScopeLabel(canonical.source_scope) || sourceLabel,
      detail: canonicalText(canonical, "trade_date", generatedAt || "-"),
    },
    {
      label: "当前口径",
      value: canonicalText(canonical, "main_conclusion"),
      detail: canonicalText(canonical, "action_tier", "仅作纪律参考"),
    },
    {
      label: "仓位纪律",
      value: canonicalText(canonical, "position_guidance", "待定"),
      detail: "不做收益承诺",
    },
    {
      label: "失效条件",
      value: canonicalText(canonical, "stop_condition", canonicalText(canonical, "risk_boundary")),
      detail: "触发后先停止原计划",
    },
    {
      label: "继续条件",
      value: canonicalText(canonical, "continue_condition", canonicalText(canonical, "trigger_condition")),
      detail: "满足后再升级动作",
    },
  ];

  return (
    <div className={cn(embedded ? "space-y-3" : "surface-card p-4")}>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Badge tone="info">{sourceLabel}</Badge>
        <Badge tone="watch">弱结论</Badge>
      </div>
      <div className="flex flex-col gap-2">
        {rows.map((row) => (
          <div key={row.label} className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
            <div className="flex min-w-0 items-start justify-between gap-3">
              <span className="shrink-0 text-[11px] text-[var(--text-tertiary)]">{row.label}</span>
              <span className="min-w-0 text-right text-[12px] font-medium text-[var(--text-primary)]">{row.value}</span>
            </div>
            <div className="mt-1 text-[11px] leading-4 text-[var(--text-tertiary)]">{row.detail}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function historyPayload(messages: AskFollowupResponse[]) {
  return messages.slice(-followupHistoryTurnLimit).flatMap((item) => [
    {
      role: "user",
      title: "继续追问",
      summary: item.question,
    },
    {
      role: "assistant",
      title: item.answer?.title || "追问回答",
      summary: item.answer?.summary || "",
      bullets: (item.answer?.bullets || []).slice(0, 4),
      references: (item.answer?.references || []).slice(0, 3),
      engine_label: item.answer?.engine_label || "",
    },
  ]);
}

export default function StockProfilePage() {
  const params = useParams<{ code: string }>();
  const searchParams = useSearchParams();
  const code = String(params.code || "");
  const queryName = String(searchParams.get("name") || "").trim();
  const profile = useStockProfile(code);
  const addStock = useAddWatchlistStock();
  const archiveStock = useArchiveWatchlistStock();
  const restoreStock = useRestoreWatchlistStock();
  const [activeTab, setActiveTab] = useState<StockTab>("决策");
  const ask = useAsk(code, activeTab === "追问");
  const managerQuery = useWatchlistManager();
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<AskFollowupResponse[]>([]);
  const [pendingQuestion, setPendingQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [askError, setAskError] = useState("");
  const [manageFeedback, setManageFeedback] = useState("");
  const threadEndRef = useRef<HTMLDivElement | null>(null);
  const profileData = profile.data;
  const detail = pickDetail(profileData, activeTab);
  const askCase = ask.data?.case;
  const manager = managerQuery.data?.manager;
  const activeManagerItem = findManagerItem(manager?.active_items, code);
  const archivedManagerItem = findManagerItem(manager?.archived_items, code);
  const manageBusy = addStock.isPending || archiveStock.isPending || restoreStock.isPending;
  const managerUnavailable = managerQuery.isError || (managerQuery.isLoading && !manager);
  const hasWatchlistDetail = Boolean(profileData?.watchlist);
  const hasOpportunityDetail = Boolean(profileData?.opportunity);
  const visibleTabs = useMemo<StockTab[]>(() => {
    const items: StockTab[] = ["决策", "追问"];
    if (hasWatchlistDetail) {
      items.push("持仓");
    }
    if (hasOpportunityDetail) {
      items.push("发现");
    }
    items.push("证据");
    return items;
  }, [hasOpportunityDetail, hasWatchlistDetail]);
  const rawStockName = detail?.name || profileData?.name || queryName || activeManagerItem?.name || archivedManagerItem?.name || askCase?.name || "";
  const stockName = rawStockName && rawStockName !== code ? rawStockName : code;
  const hasResolvedName = Boolean(rawStockName && rawStockName !== code);
  const followupShell = ask.data?.followup || askCase?.evidence_layer?.followup || null;
  const sourceLabel =
    profileData?.primary_source_label && activeTab === "决策"
      ? profileData.primary_source_label
      : activeTab === "发现" && hasOpportunityDetail
      ? "观察池链路"
      : hasWatchlistDetail
        ? "自选股链路"
        : hasOpportunityDetail
          ? "观察池链路"
          : askCase
            ? "Ask 临时分析"
            : "待匹配";
  const sourceGeneratedAt =
    detail?.generated_at ||
    ask.data?.generated_at ||
    canonicalText(askCase?.canonical_decision, "updated_at", "");
  const sourceTradeDate =
    detail?.trade_date ||
    askCase?.trade_date ||
    canonicalText(detail?.canonical_decision || askCase?.canonical_decision, "trade_date", "");
  const displayTradeDate = sourceTradeDate || profileData?.data_trade_date || profileData?.expected_trade_date || "";
  const sourceIssues = useMemo(() => sourceIssueBadges(profileData), [profileData]);
  const allMetricCards = useMemo(() => {
    if (!detail) {
      return [];
    }
    return [
      ...(detail.metric_cards || []),
      ...(detail.capital_cards || []),
      ...(detail.meta_cards || []),
      ...(detail.level_cards || []),
    ];
  }, [detail]);
  const todayAction = profileData?.today_action;
  const decisionContext = (detail || askCase) as DecisionContext | undefined;
  const decisionLocked = Boolean(profileData?.readiness && (profileData.readiness.readiness_mode !== "live_ready" || readinessHasStaleData(profileData.readiness)));
  const trustLevel = profileData?.readiness?.trust_level;
  const pageTitle = decisionLocked
    ? hasResolvedName
      ? `${stockName} ${code}`
      : code
    : detail?.hero?.title
      || askCase?.hero?.title
      || (hasResolvedName ? `${stockName} · ${code}` : code);
  const pageSummary = decisionLocked
    ? "数据新鲜度未通过，旧结论已从首屏移除；当前只允许查看证据和刷新状态。"
    : detail?.hero?.summary || detail?.topline?.verdict_summary || askCase?.hero?.summary || "统一查看这只股票的决策、持仓、发现和证据。";
  const pageBadge = decisionLocked
    ? "交易判断冻结"
    : detail?.hero?.status_label || detail?.topline?.verdict_badge || askCase?.hero?.status_label || askCase?.hero?.decision_label || "个股档案";
  const executionResultHref = useMemo(() => {
    const params = new URLSearchParams();
    const canonical = detail?.canonical_decision || askCase?.canonical_decision;

    params.set("code", code);
    params.set("source", "stock");
    params.set("source_label", sourceLabel);

    if (stockName) {
      params.set("name", stockName);
    }
    if (todayAction?.key) {
      params.set("intent_key", todayAction.key);
      params.set("today_action_key", todayAction.key);
    }
    if (todayAction?.trade_date || sourceTradeDate) {
      params.set("trade_date", todayAction?.trade_date || sourceTradeDate);
    }
    if (canonical?.main_conclusion) {
      params.set("conclusion", canonical.main_conclusion);
    }
    if (canonical?.position_guidance) {
      params.set("position", canonical.position_guidance);
    }
    if (canonical?.continue_condition) {
      params.set("continue_condition", canonical.continue_condition);
    }
    if (canonical?.stop_condition) {
      params.set("stop_condition", canonical.stop_condition);
    }

    return `/portfolio?${params.toString()}#decision-writeback`;
  }, [askCase?.canonical_decision, code, detail?.canonical_decision, sourceLabel, sourceTradeDate, stockName, todayAction?.key, todayAction?.trade_date]);
  const observationMode = isObservationDecision(decisionContext?.canonical_decision, sourceLabel);
  const executionEntryLabel = todayActionIsProcessed(todayAction)
    ? "查看处理结果"
    : observationMode
      ? "记录观察结果"
      : "记录执行结果";
  const askFallbackCards = [
    ...(askCase?.decision_cards || []),
    ...(askCase?.metric_cards || []),
    ...(askCase?.level_cards || []),
  ];
  const latestFollowups = messages.at(-1)?.answer?.followups || [];
  const presetQuestions = (followupShell?.presets || [])
    .map((item) => ({
      label: item.label || item.question,
      value: item.question,
    }))
    .filter((item) => item.value);
  const suggestedQuestions =
    latestFollowups.length
      ? latestFollowups.map((item) => ({ label: item, value: item }))
      : presetQuestions.length
        ? presetQuestions
      : [
          "这只今天要不要动？",
          "仓位和止损怎么设？",
          "最大的反向风险是什么？",
          "结论对应哪些证据？",
        ].map((item) => ({ label: item, value: item }));

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ block: "nearest" });
  }, [messages, pendingQuestion]);

  useEffect(() => {
    if (!visibleTabs.includes(activeTab)) {
      setActiveTab("决策");
    }
  }, [activeTab, visibleTabs]);

  async function submitFollowup(value?: string) {
    const text = (value ?? question).trim();
    if (!text || asking) {
      return;
    }
    setAsking(true);
    setAskError("");
    setPendingQuestion(text);
    try {
      const payload = await api.askFollowup({
        query: code,
        question: text,
        history: historyPayload(messages),
      });
      setMessages((current) => [...current, payload]);
      setQuestion("");
      setActiveTab("追问");
    } catch (error) {
      setAskError(error instanceof Error ? error.message : "追问失败");
    } finally {
      setPendingQuestion("");
      setAsking(false);
    }
  }

  function onManage(action: "add" | "archive" | "restore") {
    setManageFeedback("");
    if (action === "add") {
      addStock.mutate(
        { code, name: stockName, trigger_refresh: true },
        {
          onSuccess: (payload) => setManageFeedback(payload.message || "已加入持仓。"),
          onError: (error) => setManageFeedback(error instanceof Error ? error.message : "加入失败"),
          onSettled: () => void profile.refetch(),
        },
      );
    } else if (action === "archive") {
      archiveStock.mutate(
        { code, trigger_refresh: true },
        {
          onSuccess: (payload) => setManageFeedback(payload.message || "已归档。"),
          onError: (error) => setManageFeedback(error instanceof Error ? error.message : "归档失败"),
          onSettled: () => void profile.refetch(),
        },
      );
    } else {
      restoreStock.mutate(
        { code, trigger_refresh: true },
        {
          onSuccess: (payload) => setManageFeedback(payload.message || "已恢复持仓。"),
          onError: (error) => setManageFeedback(error instanceof Error ? error.message : "恢复失败"),
          onSettled: () => void profile.refetch(),
        },
      );
    }
  }

  return (
    <main className="flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
      <div className="mx-auto max-w-7xl">
        <PageTitle
          eyebrow={displayTradeDate || code}
          title={pageTitle}
          summary={pageSummary}
          icon={FileSearch}
          badge={pageBadge}
          actions={
            <div className="flex flex-wrap items-center gap-2">
              {managerUnavailable ? (
                <button
                  type="button"
                  className="focus-ring inline-flex items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-tertiary)] disabled:cursor-not-allowed disabled:opacity-60"
                  disabled
                >
                  {managerQuery.isLoading ? <LoaderCircle size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                  {managerQuery.isLoading ? "名单同步中" : "名单状态待同步"}
                </button>
              ) : activeManagerItem ? (
                <button
                  type="button"
                  className="focus-ring inline-flex items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] disabled:cursor-not-allowed disabled:opacity-50"
                  onClick={() => onManage("archive")}
                  disabled={manageBusy}
                >
                  {archiveStock.isPending ? <LoaderCircle size={14} className="animate-spin" /> : <Archive size={14} />}
                  归档
                </button>
              ) : archivedManagerItem ? (
                <button
                  type="button"
                  className="focus-ring inline-flex items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] disabled:cursor-not-allowed disabled:opacity-50"
                  onClick={() => onManage("restore")}
                  disabled={manageBusy}
                >
                  {restoreStock.isPending ? <LoaderCircle size={14} className="animate-spin" /> : <RotateCcw size={14} />}
                  恢复
                </button>
              ) : (
                <button
                  type="button"
                  className="focus-ring inline-flex items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] disabled:cursor-not-allowed disabled:opacity-50"
                  onClick={() => onManage("add")}
                  disabled={manageBusy}
                >
                  {addStock.isPending ? <LoaderCircle size={14} className="animate-spin" /> : <Plus size={14} />}
                  加入
                </button>
              )}
              <button
                type="button"
                className="focus-ring inline-flex items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)]"
                onClick={() => void profile.refetch()}
              >
                <RefreshCw size={14} className={profile.isFetching ? "animate-spin" : ""} />
                刷新
              </button>
            </div>
          }
        />

        {trustLevel && trustLevel.level !== "trusted" ? (
          <TrustBanner trust={trustLevel} readiness={profileData?.readiness} className="mb-4" />
        ) : null}

        {profile.isError ? <ErrorState message="个股详情暂不可用" onRetry={() => void profile.refetch()} /> : null}
        {manageFeedback ? (
          <div className="mb-5 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
            {manageFeedback}
          </div>
        ) : null}
        {!profile.isLoading && !ask.isLoading && !detail && !askCase ? <EmptyState>当前股票不在持仓或观察池详情中。</EmptyState> : null}

        {detail || askCase ? (
          <div className="mb-5 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={hasWatchlistDetail ? "positive" : hasOpportunityDetail ? "watch" : "info"}>{sourceLabel}</Badge>
              {sourceTradeDate ? <Badge tone="info">交易日 {sourceTradeDate}</Badge> : null}
              {sourceGeneratedAt ? <Badge tone="info">更新 {sourceGeneratedAt}</Badge> : null}
              {decisionLocked ? <Badge tone="risk">仅作证据来源</Badge> : null}
              {!detail && askCase ? <Badge tone="warning">临时抓取</Badge> : null}
              {sourceIssues.map((item) => <Badge key={item.key} tone="watch">{item.label}</Badge>)}
            </div>
            <p className="mt-2 text-[12px] leading-5 text-[var(--text-tertiary)]">
              {decisionLocked
                ? "当前链路只作为证据来源保留，不进入今天的交易判断。"
                : "当前页只展示已有链路能回源的纪律参考；目标价、收益预测和完整财报研判暂不进入结果页。"}
            </p>
          </div>
        ) : null}

        {profileData?.formal_data?.available ? (
          <div className="mb-6">
            <FormalDataSnapshotPanel data={profileData.formal_data} />
          </div>
        ) : null}

        {detail || askCase || (decisionLocked && profileData?.readiness) ? (
          <div className="mb-6 flex flex-col gap-4">
            {decisionLocked ? (
              <>
                <TradingAvailabilityBar readiness={profileData?.readiness} />
                <DataFreshnessGate
                  readiness={profileData?.readiness}
                  sourceTradeDate={displayTradeDate}
                  onViewEvidence={() => setActiveTab("证据")}
                />
              </>
            ) : (
              <>
                <DecisionLayerCard
                  detail={decisionContext}
                  todayAction={todayAction}
                  stockName={stockName}
                  code={code}
                  executionHref={executionResultHref}
                  sourceLabel={sourceLabel}
                  observationMode={observationMode}
                />
                <TradingAvailabilityBar readiness={profileData?.readiness} />
                <ObservationDecisionBlocks
                  detail={decisionContext}
                  readiness={profileData?.readiness}
                  sourceLabel={sourceLabel}
                  sourceTradeDate={sourceTradeDate}
                  todayAction={todayAction}
                  onViewEvidence={() => setActiveTab("证据")}
                />
              </>
            )}
          </div>
        ) : null}

        <div className="mb-6 flex gap-2 overflow-x-auto rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-1">
          {visibleTabs.map((tab) => (
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

        {decisionLocked && (activeTab === "决策" || activeTab === "持仓" || activeTab === "发现") ? (
          <EmptyState>
            数据新鲜度未通过，{activeTab} 内容已冻结。请先去 Settings 刷新，或切到“证据”只读查看来源。
          </EmptyState>
        ) : null}

        {activeTab === "追问" ? (
          <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
            <Panel title="当前结论" eyebrow="Ask Context">
              <div className="surface-card p-4">
                {ask.isLoading ? (
                  <SkeletonBlock className="h-32 w-full" />
                ) : askCase ? (
                  <div className="flex flex-col gap-4">
                    <div>
                      <div className="mb-2 flex flex-wrap items-center gap-2">
                        <Badge tone="info">{stockName}</Badge>
                        {askCase.hero?.status_label ? <Badge tone="watch">{askCase.hero.status_label}</Badge> : null}
                      </div>
                      <h2 className="text-lg font-semibold text-[var(--text-primary)]">
                        {askCase.hero?.title || `${stockName} ${code}`}
                      </h2>
                      <p className="mt-2 text-[13px] leading-6 text-[var(--text-secondary)]">
                        {askCase.hero?.summary || "暂无问股摘要，直接输入问题继续追问。"}
                      </p>
                    </div>

                    {(askCase.cross_cards || []).length ? (
                      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                        {askCase.cross_cards?.slice(0, 4).map((card, index) => (
                          <MetricCard key={`${card.label}-${index}`} {...card} tone={card.tone || "info"} />
                        ))}
                      </div>
                    ) : null}

                    {askCase.context_tags?.length ? (
                      <div className="flex flex-wrap gap-2">
                        {askCase.context_tags.map((item) => (
                          <Badge key={item} tone="info">{item}</Badge>
                        ))}
                      </div>
                    ) : null}

                    {askCase.canonical_decision ? (
                      <DecisionSummary
                        canonical={askCase.canonical_decision}
                        sourceLabel="Ask 临时分析"
                        generatedAt={sourceGeneratedAt}
                        embedded
                      />
                    ) : null}
                  </div>
                ) : (
                  <EmptyState>暂无问股上下文，输入问题后会使用规则引擎回答。</EmptyState>
                )}
              </div>
            </Panel>

            <Panel title="连续追问" eyebrow="Follow-up">
              <div className="surface-card flex min-h-[520px] flex-col p-4">
                <div className="min-h-0 flex-1 space-y-3 overflow-auto pr-1">
                  {!messages.length ? (
                    <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3 text-[13px] leading-6 text-[var(--text-secondary)]">
                      {followupShell?.starter?.summary || "可以围绕仓位、买卖点、风险和证据继续问，系统会带着本轮对话上下文回答。"}
                      {followupShell?.engine_badge?.label ? (
                        <span className="mt-2 block text-[12px] text-[var(--text-tertiary)]">
                          {followupShell.engine_badge.label}
                          {followupShell.engine_badge.detail ? `：${followupShell.engine_badge.detail}` : ""}
                        </span>
                      ) : null}
                    </div>
                  ) : null}
                  {messages.map((item, index) => (
                    <div key={`${item.question}-${index}`} className="space-y-2">
                      <div className="ml-auto max-w-[88%] rounded-md bg-[var(--info)] px-3 py-2 text-[13px] leading-6 text-white">
                        {item.question}
                      </div>
                      <div className="max-w-[92%] rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
                        <div className="mb-1 flex flex-wrap items-center gap-2">
                          <span className="text-[13px] font-medium text-[var(--text-primary)]">
                            {item.answer?.title || "追问回答"}
                          </span>
                          {item.answer?.engine_label ? <Badge tone="info">{item.answer.engine_label}</Badge> : null}
                        </div>
                        <p className="text-[13px] leading-6 text-[var(--text-secondary)]">{item.answer?.summary || "-"}</p>
                        {item.answer?.bullets?.length ? (
                          <ul className="mt-2 list-disc space-y-1 pl-4 text-[12px] leading-5 text-[var(--text-secondary)]">
                            {item.answer.bullets.map((bullet) => (
                              <li key={bullet}>{bullet}</li>
                            ))}
                          </ul>
                        ) : null}
                        {item.answer?.references?.length ? (
                          <div className="mt-3 flex flex-wrap gap-1.5">
                            {item.answer.references.map((ref) => (
                              <Badge key={ref} tone="watch">{ref}</Badge>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    </div>
                  ))}
                  {pendingQuestion ? (
                    <div className="space-y-2">
                      <div className="ml-auto max-w-[88%] rounded-md bg-[var(--info)] px-3 py-2 text-[13px] leading-6 text-white">
                        {pendingQuestion}
                      </div>
                      <div className="inline-flex max-w-[92%] items-center gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3 text-[13px] text-[var(--text-secondary)]">
                        <LoaderCircle size={14} className="animate-spin" />
                        正在整理回答
                      </div>
                    </div>
                  ) : null}
                  <div ref={threadEndRef} />
                </div>

                <div className="mt-4 border-t border-[var(--border-subtle)] pt-4">
                  {suggestedQuestions.length ? (
                    <div className="mb-3 flex flex-wrap gap-2">
                      {suggestedQuestions.slice(0, 4).map((item) => (
                        <button
                          key={`${item.label}-${item.value}`}
                          type="button"
                          className="focus-ring rounded-md border border-[var(--border-subtle)] px-2.5 py-1.5 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                          onClick={() => void submitFollowup(item.value)}
                          disabled={asking}
                        >
                          {item.label}
                        </button>
                      ))}
                    </div>
                  ) : null}
                  <form
                    className="flex items-end gap-2"
                    onSubmit={(event) => {
                      event.preventDefault();
                      void submitFollowup();
                    }}
                  >
                    <textarea
                      value={question}
                      onChange={(event) => setQuestion(event.target.value)}
                      onKeyDown={(event) => {
                        if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                          event.preventDefault();
                          void submitFollowup();
                        }
                      }}
                      placeholder="继续问：仓位怎么控？风险在哪？证据是什么？"
                      className="focus-ring min-h-20 flex-1 resize-y rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[13px] leading-6 text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)]"
                    />
                    <button
                      type="submit"
                      className="focus-ring flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-[var(--text-primary)] text-[var(--text-inverse)] disabled:cursor-not-allowed disabled:opacity-50"
                      disabled={asking || !question.trim()}
                      aria-label="发送追问"
                    >
                      {asking ? <LoaderCircle size={16} className="animate-spin" /> : <SendHorizontal size={16} />}
                    </button>
                  </form>
                  {askError ? (
                    <div className="mt-3 rounded-md border border-[color-mix(in_srgb,var(--negative)_20%,transparent)] bg-[color-mix(in_srgb,var(--negative)_8%,transparent)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
                      {askError}
                    </div>
                  ) : null}
                </div>
              </div>
            </Panel>
          </div>
        ) : null}

        {!decisionLocked && !detail && askCase && activeTab === "决策" ? (
          <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
            <div className="flex flex-col gap-6">
              <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {askFallbackCards.slice(0, 4).map((card, index) => (
                  <MetricCard key={`${card.label}-${index}`} {...card} tone={index === 0 ? askCase.tone || "info" : card.tone || "watch"} />
                ))}
                {!askFallbackCards.length ? <EmptyState>暂无 Ask 指标卡。</EmptyState> : null}
              </section>

              <Panel
                title="Ask 主结论"
                eyebrow="Fallback"
                action={
                  <button
                    type="button"
                    className="focus-ring rounded-md border border-[var(--border-subtle)] px-3 py-1.5 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                    onClick={() => setActiveTab("追问")}
                  >
                    继续追问
                  </button>
                }
              >
                <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                  {(askCase.execution_loop || []).slice(0, 4).map((card, index) => <DataCard key={`${card.label}-${index}`} card={card} />)}
                  {!askCase.execution_loop?.length ? (
                    <DataCard
                      card={{
                        title: askCase.hero?.decision_label || "当前结论",
                        detail: askCase.hero?.summary || "Ask 已返回单股结论，可进入追问继续拆仓位、风险和证据。",
                        status: askCase.hero?.position,
                        tone: askCase.tone || "watch",
                      }}
                    />
                  ) : null}
                </div>
              </Panel>
            </div>

            <Panel title="决策摘要" eyebrow="Ask Canonical">
              <DecisionSummary canonical={askCase.canonical_decision} sourceLabel="Ask 临时分析" generatedAt={sourceGeneratedAt} />
            </Panel>
          </div>
        ) : null}

        {!decisionLocked && detail && activeTab === "决策" ? (
          <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
            <div className="flex flex-col gap-6">
              <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {(detail.decision_cards || []).slice(0, 4).map((card, index) => (
                  <MetricCard key={`${card.label}-${index}`} {...card} tone={index === 0 ? detail.tone || "info" : index === 2 ? "risk" : "watch"} />
                ))}
              </section>

              <Panel title={observationMode ? "观察循环" : "执行循环"} eyebrow="Loop">
                <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <p className="text-[12px] leading-5 text-[var(--text-tertiary)]">
                    {observationMode ? "观察票先记录复核结果，不默认进入交易执行。" : "记录执行结果不会自动下单，只会进入执行回写区。"}
                  </p>
                  <Link
                    href={executionResultHref}
                    className="focus-ring inline-flex items-center justify-center gap-2 rounded-md border border-[var(--accent)] bg-[var(--accent-soft)] px-3 py-1.5 text-[12px] text-[var(--accent)]"
                  >
                    {executionEntryLabel}
                  </Link>
                </div>
                <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                  {(detail.execution_loop || []).map((card, index) => <DataCard key={`${card.label}-${index}`} card={card} />)}
                  {!detail.execution_loop?.length ? <EmptyState>暂无执行循环。</EmptyState> : null}
                </div>
              </Panel>
            </div>

            <div className="flex flex-col gap-6">
              <Panel title="决策摘要" eyebrow="Canonical">
                <DecisionSummary canonical={detail.canonical_decision} sourceLabel={sourceLabel} generatedAt={sourceGeneratedAt} />
              </Panel>

              {detail.learning_memories?.length ? (
                <Panel title="历史提醒" eyebrow="Learning">
                  <LearningMemoryPreview memories={detail.learning_memories} limit={3} />
                </Panel>
              ) : null}
            </div>
          </div>
        ) : null}

        {!decisionLocked && detail && activeTab === "持仓" ? (
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
                    key={`${trigger.name || trigger.label || index}`}
                    card={triggerCard(trigger, index)}
                  />
                ))}
                {!detail.triggers?.length ? <EmptyState>暂无盘中触发条件。</EmptyState> : null}
              </div>
            </Panel>
          </div>
        ) : null}

        {!decisionLocked && detail && activeTab === "发现" ? (
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
          <EvidencePanel
            page={profile.data?.watchlist ? "watchlist" : "opportunities"}
            stockCode={code}
            sources={detail.source_cards}
            artifacts={detail.artifacts}
            title="来源与原始证据"
            eyebrow="Evidence"
          />
        ) : null}

        {!detail && askCase && activeTab === "证据" ? (
          <EvidencePanel
            mode="ask"
            stockCode={code}
            sources={askCase.source_cards}
            artifacts={askCase.artifacts}
            title="Ask 来源与原始证据"
            eyebrow="Evidence"
          />
        ) : null}

        {!detail && askCase && (activeTab === "持仓" || activeTab === "发现") ? (
          <EmptyState>{activeTab === "持仓" ? "这只股票当前不在持仓名单，可用页面右上角加入。" : "这只股票当前不在观察池，先以 Ask 结论和证据为准。"}</EmptyState>
        ) : null}

        {activeTab === "决策" ? <StockDecisionTimelinePanel code={code} /> : null}
      </div>
    </main>
  );
}

function StockDecisionTimelinePanel({ code }: { code: string }) {
  const ledger = useDecisionLedgerStock(code);
  const items = (ledger.data?.items || []) as DecisionLedgerCompactRecord[];
  const errors = ledger.data?.errors || [];

  return (
    <Panel title="Decision Ledger 历史" eyebrow="Ledger Timeline">
      <div className="surface-card p-4">
        {ledger.isLoading && !ledger.data ? (
          <div className="flex flex-col gap-2">
            {Array.from({ length: 3 }).map((_, index) => (
              <SkeletonBlock key={index} className="h-12 w-full" />
            ))}
          </div>
        ) : ledger.isError ? (
          <ErrorState message="Decision Ledger 暂不可用" onRetry={() => void ledger.refetch()} />
        ) : !items.length ? (
          <EmptyState>这只股票暂无 Decision Ledger 记录。</EmptyState>
        ) : (
          <div className="flex flex-col gap-2">
            {items.slice(0, 10).map((item) => (
              <div
                key={item.decision_id}
                className="flex min-h-[56px] flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 text-[12px] text-[var(--text-primary)]">
                    <span className="font-medium">{item.trade_date}</span>
                    <span className="text-[11px] text-[var(--text-tertiary)]">{item.lane || "-"}</span>
                  </div>
                  {item.main_conclusion ? (
                    <div className="mt-1 line-clamp-2 text-[11px] leading-4 text-[var(--text-tertiary)]">{item.main_conclusion}</div>
                  ) : null}
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  {item.action_label || item.action ? (
                    <Badge tone="watch">{item.action_label || item.action}</Badge>
                  ) : null}
                  <Badge tone={item.latest_execution?.status ? "info" : "stale"}>
                    执行 {item.latest_execution?.status || "未记录"}
                  </Badge>
                  <Badge tone={item.latest_outcome?.label ? "info" : "stale"}>
                    结果 {item.latest_outcome?.window || ""} {item.latest_outcome?.label || "待评估"}
                  </Badge>
                  <Badge tone={item.status === "superseded" ? "warning" : "good"}>
                    {item.status === "superseded" ? "已被替代" : "open"}
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        )}
        {errors.length ? (
          <div className="mt-3 rounded-md border border-[var(--border-warn)] bg-[var(--surface-warn)] px-3 py-2 text-[11px] text-[var(--text-warn)]">
            部分 ledger 文件解析失败：{errors[0].file} ({errors[0].error})
          </div>
        ) : null}
      </div>
    </Panel>
  );
}
