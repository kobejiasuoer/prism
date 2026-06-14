"use client";

import { ArrowRight, ChevronDown, FileText, RefreshCw } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { Fragment, type ReactNode, useMemo, useState } from "react";

import { Badge } from "@/components/badge";
import { EmptyState, Panel, SkeletonBlock } from "@/components/data-card";
import { MetricCard, MetricSkeleton } from "@/components/metric-card";
import { riskLevelTone } from "@/lib/risk-utils";
import type { CardGroup, StockListCard } from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  cardHref,
  displayGroupTitle,
  groupCount,
  groupHasDeferredCards,
  persistenceLabel,
  persistenceTone,
} from "./discovery-display-utils";
import type { DiscoveryObservationActionsProps } from "./discovery-observation-actions";
import type {
  DiscoveryOpportunityEvidenceDetailsProps,
  DiscoveryV2AiTelemetryProps,
} from "./discovery-v2-details";
import {
  V2_ACTION_LABELS,
  hasV2,
  uniqueTexts,
  v2Action,
  v2ActionLabel,
  v2ActionTone,
  v2AiStatus,
  v2AiTone,
  v2CalibrationMeta,
  v2ConfidenceLabel,
  v2HardBlocks,
  v2HardMax,
  v2HardReason,
  v2MissingItems,
  v2MissingText,
  v2Rank,
} from "./discovery-v2-utils";
import {
  bucketByFunnel,
  FUNNEL_LAYER_LABELS,
  type FunnelBucket,
  type FunnelLayer,
  valveLabel,
  valveTone,
  type ValveStatus,
} from "./discovery-triage-utils";

export type DiscoveryObservationWorkbenchProps = {
  groups: CardGroup<StockListCard>[];
  activeGroup?: CardGroup<StockListCard>;
  activeIndex: number;
  loading: boolean;
  initialLoading: boolean;
  activeGroupLoadError?: string;
  onSelectGroup: (index: number) => void;
  onLoadGroup?: () => void;
  onRetryLoadGroup?: () => void;
  tradeDate?: string;
  onFeedback: (message: string) => void;
  sidePanel: ReactNode;
  valveStatus?: ValveStatus;
};

const DiscoveryObservationActions = dynamic<DiscoveryObservationActionsProps>(
  () =>
    import("./discovery-observation-actions").then(
      (module) => module.DiscoveryObservationActions,
    ),
  {
    ssr: false,
    loading: () => (
      <button
        type="button"
        className="focus-ring inline-flex h-8 items-center justify-center gap-1.5 rounded-md border border-[var(--border-subtle)] px-2.5 text-[12px] text-[var(--text-tertiary)] disabled:cursor-not-allowed disabled:opacity-60"
        disabled
      >
        <RefreshCw size={13} className="animate-spin" />
        操作加载中
      </button>
    ),
  },
);

const DiscoveryOpportunityEvidenceDetails =
  dynamic<DiscoveryOpportunityEvidenceDetailsProps>(
    () =>
      import("./discovery-v2-details").then(
        (module) => module.DiscoveryOpportunityEvidenceDetails,
      ),
    {
      ssr: false,
      loading: () => <SkeletonBlock className="h-28 w-full" />,
    },
  );

const DiscoveryV2AiTelemetry = dynamic<DiscoveryV2AiTelemetryProps>(
  () =>
    import("./discovery-v2-details").then(
      (module) => module.DiscoveryV2AiTelemetry,
    ),
  {
    ssr: false,
    loading: () => <SkeletonBlock className="mb-5 h-28 w-full" />,
  },
);

function clarifyUpgradeCopy(text: string) {
  return text
    .replace(/(^|；)升级：/g, "$1确认：")
    .replace(/观察升级：/g, "还差：");
}

function stockInstruction(stock: StockListCard) {
  if (hasV2(stock)) {
    const missing = v2MissingText(stock);
    return [
      stock.name
        ? `${stock.name}：${v2ActionLabel(stock) || "只观察"}`
        : v2ActionLabel(stock) || "只观察",
      stock.why_now ? `现在：${stock.why_now}` : "",
      missing ? `还差：${missing}` : "",
      stock.invalidation ? `失效：${stock.invalidation}` : "",
    ]
      .filter(Boolean)
      .join("；");
  }
  if (stock.observation_instruction) {
    return clarifyUpgradeCopy(stock.observation_instruction);
  }
  return [
    stock.name ? `${stock.name}：只观察，不追` : "只观察，不追",
    stock.upgrade_condition
      ? `还差：${stock.upgrade_condition}`
      : stock.setup_label
        ? `还差：${stock.setup_label}`
        : "",
    stock.invalid_condition
      ? `失效：${stock.invalid_condition}`
      : stock.foot
        ? `失效：${stock.foot}`
        : "",
  ]
    .filter(Boolean)
    .join("；")
    .replace(/。；/g, "；");
}

function riskLevelLabel(level?: string) {
  if (level === "block") {
    return "硬拦截";
  }
  if (level === "degrade") {
    return "降级";
  }
  if (level === "warn") {
    return "提醒";
  }
  return "";
}

function compactRiskText(value?: string, maxLength = 42) {
  if (!value) {
    return "";
  }
  return value.length > maxLength ? `${value.slice(0, maxLength)}...` : value;
}

function compactInlineText(value?: string, maxLength = 30) {
  if (!value) {
    return "";
  }
  const normalized = value.replace(/\s+/g, " ").trim();
  return normalized.length > maxLength
    ? `${normalized.slice(0, maxLength)}...`
    : normalized;
}

function hasMetricValue(value: unknown) {
  const text = String(value ?? "").trim();
  return Boolean(
    text && text !== "-" && text !== "undefined" && text !== "null",
  );
}

function formatMetric(value: unknown, suffix = "") {
  if (!hasMetricValue(value)) {
    return "";
  }
  const numeric = Number(value);
  if (Number.isFinite(numeric)) {
    const text = numeric.toFixed(2).replace(/\.?0+$/, "");
    return `${text}${suffix}`;
  }
  return `${String(value).trim()}${suffix}`;
}

function includesAny(text: string, tokens: string[]) {
  return tokens.some((token) => text.includes(token));
}

function entryPlanTexts(stock: StockListCard) {
  const plan = stock.entry_plan || {};
  return uniqueTexts([
    stock.action_intent,
    stock.position_guidance,
    plan.action,
    plan.sizing,
    plan.trigger,
    plan.avoid,
    plan.invalidate,
  ]);
}

function stockStageLabel(
  stock: StockListCard,
  group?: CardGroup<StockListCard>,
) {
  if (hasV2(stock)) {
    return (
      stock.stock_role || stock.playbook || displayGroupTitle(group?.title)
    );
  }
  const text = stock.status || stock.action || group?.title || "观察";
  if (text.includes("仍可跟踪") || text.includes("可升级")) {
    return "待确认观察";
  }
  return displayGroupTitle(text);
}

function buyGateMeta(stock: StockListCard, group?: CardGroup<StockListCard>) {
  const planTexts = entryPlanTexts(stock);
  const stageText = [
    group?.key,
    group?.title,
    stock.status,
    stock.action,
    stock.action_intent,
    stock.position_guidance,
    stock.observation_instruction,
    stock.detail,
    stock.foot,
    stock.risk,
    stock.upgrade_condition,
    stock.invalid_condition,
    ...planTexts,
  ].join(" ");
  const riskReasons = uniqueTexts([
    stock.block_reason,
    stock.degrade_reason,
    stock.avoid_condition,
    stock.risk_tags,
    stock.factor_risk_flags,
    stock.foot,
    stock.risk,
  ]);
  const primaryRisk =
    stock.block_reason || stock.degrade_reason || riskReasons[0] || "";
  const eliminated = includesAny(stageText, [
    "已淘汰",
    "降级",
    "退出",
    "剔除",
    "排除",
    "excluded",
    "downgraded",
    "exited",
  ]);

  if (hasV2(stock)) {
    const action = v2Action(stock) || "observe";
    const label = v2ActionLabel(stock) || V2_ACTION_LABELS[action] || "只观察";
    const hardReason = v2HardReason(stock);
    const hardMax = v2HardMax(stock);
    const missing = v2MissingText(stock);
    const confidence = v2ConfidenceLabel(stock);
    const trigger = stock.entry_plan?.trigger || stock.upgrade_condition || "";
    const hardCap = hardMax
      ? `最大允许：${V2_ACTION_LABELS[hardMax] || hardMax}`
      : "";
    const primaryDetail = uniqueTexts([
      hardReason ? `不能买：${hardReason}` : "",
      missing ? `还差：${missing}` : "",
      trigger && action !== "observe" ? `触发：${trigger}` : "",
      hardCap && action !== "actionable" ? hardCap : "",
      confidence ? `置信 ${confidence}` : "",
    ]).join("；");
    if (eliminated) {
      return {
        label: "不可买入",
        tone: "risk",
        detail: compactRiskText(
          stock.invalidation ||
            stock.invalid_condition ||
            hardReason ||
            primaryRisk ||
            "原假设已被破坏",
        ),
      };
    }
    if (hardReason && v2Rank(action) <= v2Rank("shadow")) {
      return {
        label: "买入未放行",
        tone: "risk",
        detail: compactRiskText(
          primaryDetail || stock.invalidation || "硬闸门限制真实动作",
          64,
        ),
      };
    }
    if (action === "actionable") {
      return {
        label: v2HardBlocks(stock) ? "买入未放行" : label,
        tone: v2HardBlocks(stock) ? "watch" : "positive",
        detail: compactRiskText(
          primaryDetail ||
            stock.why_now ||
            "结构、触发和失效位已相对清楚，仍需人工复核",
          64,
        ),
      };
    }
    if (action === "trial") {
      return {
        label,
        tone: "positive",
        detail: compactRiskText(
          primaryDetail || stock.why_now || "等触发、承接和账户阀门同时满足",
          64,
        ),
      };
    }
    if (action === "shadow") {
      return {
        label,
        tone: "watch",
        detail: compactRiskText(
          primaryDetail ||
            stock.upgrade_reason ||
            stock.why_now ||
            "结构假设可跟踪，但暂不进入买入动作",
          64,
        ),
      };
    }
    if (action === "review") {
      return {
        label,
        tone: "watch",
        detail: compactRiskText(
          primaryDetail || stock.upgrade_reason || "结构有线索，但关键确认不足",
          64,
        ),
      };
    }
    return {
      label: hardReason ? "买入未放行" : label,
      tone: hardReason ? "risk" : "info",
      detail: compactRiskText(
        primaryDetail ||
          stock.invalidation ||
          stock.upgrade_reason ||
          "结构假设仍不完整",
        64,
      ),
    };
  }

  if (eliminated) {
    return {
      label: "不可买入",
      tone: "risk",
      detail: compactRiskText(
        stock.invalid_condition || primaryRisk || "已退出今日观察链路",
      ),
    };
  }
  if (stock.risk_level === "block" || stock.block_reason) {
    return {
      label: "买入拦截",
      tone: "risk",
      detail: compactRiskText(
        stock.block_reason || primaryRisk || "存在硬执行约束",
      ),
    };
  }

  const trialAction =
    stock.action_intent === "trial_buy" ||
    includesAny(stageText, [
      "试错",
      "轻仓",
      "小仓位",
      "开仓",
      "买入",
      "0.3-0.5",
      "0.5-0.8",
      "0.3 成",
      "0.3成",
    ]);

  if (trialAction) {
    const sizing = stock.position_guidance || stock.entry_plan?.sizing || "";
    const trigger = stock.entry_plan?.trigger || stock.upgrade_condition || "";
    const pending =
      uniqueTexts([trigger, primaryRisk || riskReasons[0]]).join("；") ||
      "等待触发、承接和资金确认";
    return {
      label: "试错待触发",
      tone: "positive",
      detail: compactRiskText([sizing, pending].filter(Boolean).join("；"), 54),
    };
  }

  const waitingForGate =
    includesAny(stageText, [
      "只观察",
      "不追",
      "先观察",
      "不急着",
      "等待",
      "先等",
      "未确认",
      "不执行",
      "先不开新仓",
      "不直接升级执行",
    ]) || displayGroupTitle(group?.title).includes("结构验证");

  if (
    stock.risk_level === "degrade" ||
    stock.degrade_reason ||
    stock.avoid_condition ||
    riskReasons.length ||
    waitingForGate
  ) {
    return {
      label: "买入未放行",
      tone: "watch",
      detail: compactRiskText(
        primaryRisk || stock.upgrade_condition || "等待触发、承接和阀门确认",
      ),
    };
  }
  return {
    label: "仅观察",
    tone: "info",
    detail: compactRiskText(stock.upgrade_condition || "尚未形成买入动作"),
  };
}

function BuyGateCell({
  stock,
  group,
  gate,
  compact = false,
}: {
  stock: StockListCard;
  group?: CardGroup<StockListCard>;
  gate?: ReturnType<typeof buyGateMeta>;
  compact?: boolean;
}) {
  const resolvedGate = gate ?? buyGateMeta(stock, group);
  return (
    <div className="max-w-[190px]">
      <Badge tone={resolvedGate.tone}>{resolvedGate.label}</Badge>
      <div
        className={cn(
          "mt-1 text-[12px] leading-5 text-[var(--text-secondary)]",
          compact ? "prism-clamp-2" : "",
        )}
      >
        {resolvedGate.detail}
      </div>
    </div>
  );
}

function opportunityRowKey(
  group: CardGroup<StockListCard> | undefined,
  stock: StockListCard,
) {
  return `${group?.key || group?.title || "group"}-${stock.code}`;
}

function opportunityEvidenceCopy(
  stock: StockListCard,
  group?: CardGroup<StockListCard>,
  gate?: ReturnType<typeof buyGateMeta>,
) {
  const resolvedGate = gate ?? buyGateMeta(stock, group);
  const poolReason =
    stock.thesis || stock.reason || stock.detail || "等待更多确认";
  const confirmation =
    v2MissingText(stock, 2) ||
    stock.upgrade_reason ||
    stock.upgrade_condition ||
    stock.setup_label ||
    "等待触发条件";
  const invalidation =
    stock.invalidation ||
    stock.invalid_condition ||
    stock.foot ||
    stock.risk ||
    "触发失效则剔除";
  const summary = stock.decision_summary || resolvedGate.detail || poolReason;
  const preview = [
    { label: "还差", tone: "watch", value: confirmation },
    { label: "失效", tone: "risk", value: invalidation },
  ].filter((item) => Boolean(item.value));
  const hiddenCount = [
    stock.market_phase ||
      stock.theme_phase ||
      stock.stock_role ||
      stock.playbook,
    poolReason,
    v2HardReason(stock),
    stock.block_reason || stock.degrade_reason,
    hasV2(stock) ? v2AiStatus(stock) || "baseline" : "",
    v2CalibrationMeta(stock)?.detail,
  ].filter(Boolean).length;
  return { summary, preview, hiddenCount };
}

function riskEvidenceItems(stock: StockListCard) {
  const calibration = v2CalibrationMeta(stock);
  const riskTags = uniqueTexts([
    stock.risk_tags?.slice(0, 2),
    stock.foot || stock.risk,
  ]);
  const items = [
    v2HardReason(stock) ? { label: "硬闸门", tone: "risk" } : null,
    hasV2(stock)
      ? {
          label: v2AiStatus(stock) === "used" ? "AI" : "Baseline",
          tone: v2AiTone(v2AiStatus(stock) || "not_requested"),
        }
      : null,
    calibration ? { label: calibration.label, tone: calibration.tone } : null,
    riskTags.length ? { label: "风险", tone: "risk" } : null,
    stock.priority_label
      ? { label: String(stock.priority_label), tone: "info" }
      : null,
    stock.score !== undefined
      ? { label: `${stock.score} 分`, tone: "positive" }
      : null,
    stock.change_pct !== undefined
      ? { label: `涨幅 ${formatChange(stock.change_pct)}`, tone: "watch" }
      : null,
  ].filter((item): item is { label: string; tone: string } =>
    Boolean(item?.label),
  );
  return items;
}

function RiskEvidenceCell({ stock }: { stock: StockListCard }) {
  const items = riskEvidenceItems(stock);
  if (!items.length) {
    return <span className="text-[11px] text-[var(--text-tertiary)]">-</span>;
  }
  const visible = items.slice(0, 2);
  const hiddenCount = items.length - visible.length;
  return (
    <div className="flex max-w-[140px] flex-wrap gap-1.5">
      {visible.map((item, index) => (
        <Badge
          key={`${stock.code}-risk-${index}-${item.label}`}
          tone={item.tone}
        >
          {compactInlineText(item.label, 14)}
        </Badge>
      ))}
      {hiddenCount > 0 ? <Badge tone="info">+{hiddenCount}</Badge> : null}
    </div>
  );
}

function OpportunityEvidenceCell({
  stock,
  group,
  gate,
  expanded,
  onToggle,
  className,
}: {
  stock: StockListCard;
  group?: CardGroup<StockListCard>;
  gate?: ReturnType<typeof buyGateMeta>;
  expanded: boolean;
  onToggle: () => void;
  className?: string;
}) {
  const evidence = opportunityEvidenceCopy(stock, group, gate);
  return (
    <div className={cn("max-w-[360px]", className)}>
      <p className="prism-clamp-2 text-[12px] leading-5 text-[var(--text-primary)]">
        {evidence.summary}
      </p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {evidence.preview.map((item) => (
          <Badge key={`${stock.code}-${item.label}`} tone={item.tone}>
            {item.label}
          </Badge>
        ))}
        {evidence.hiddenCount > 0 ? (
          <Badge tone="info">+{evidence.hiddenCount} 条依据</Badge>
        ) : null}
      </div>
      <button
        type="button"
        aria-expanded={expanded}
        className="focus-ring mt-2 inline-flex h-7 items-center gap-1.5 rounded-md border border-[var(--border-subtle)] px-2 text-[11px] text-[var(--text-secondary)] hover:border-[var(--border-default)] hover:text-[var(--text-primary)]"
        onClick={onToggle}
      >
        <FileText size={12} />
        {expanded ? "收起依据" : "查看依据"}
        <ChevronDown
          size={12}
          className={cn("transition-transform", expanded ? "rotate-180" : "")}
        />
      </button>
    </div>
  );
}

function stageTone(stock: StockListCard, group?: CardGroup<StockListCard>) {
  if (hasV2(stock)) {
    return v2ActionTone(stock);
  }
  const gate = buyGateMeta(stock, group);
  if (gate.tone === "risk") {
    return "risk";
  }
  if (gate.label === "试错待触发") {
    return "positive";
  }
  if (gate.label === "买入未放行") {
    return "watch";
  }
  return stock.tone;
}

function groupDecisionMeta(group?: CardGroup<StockListCard>) {
  const cards = group?.cards || [];
  if (!cards.length) {
    return null;
  }
  const v2Cards = cards.filter(hasV2);
  if (v2Cards.length) {
    const actionable = v2Cards.filter(
      (stock) => v2Action(stock) === "actionable",
    );
    const realActionable = actionable.filter(
      (stock) => !v2HardBlocks(stock),
    ).length;
    const blockedActionable = actionable.length - realActionable;
    const trial = v2Cards.filter((stock) => v2Action(stock) === "trial").length;
    const shadowReview = v2Cards.filter(
      (stock) => v2Action(stock) === "shadow" || v2Action(stock) === "review",
    ).length;
    const missing = v2Cards
      .flatMap((stock) => v2MissingItems(stock))
      .slice(0, 2)
      .join("；");
    const firstHardReason = v2HardReason(
      v2Cards.find(v2HardBlocks) || v2Cards[0],
    );
    const top = [...v2Cards].sort((left, right) => {
      const actionDelta = v2Rank(v2Action(right)) - v2Rank(v2Action(left));
      if (actionDelta) {
        return actionDelta;
      }
      return Number(right.confidence ?? 0) - Number(left.confidence ?? 0);
    })[0];
    if (realActionable > 0) {
      return {
        label: `本组结论：${realActionable} 只可执行待复核`,
        detail: [
          top ? `先看 ${top.name || top.code} 的结构假设和失效位` : "",
          blockedActionable ? `${blockedActionable} 只被硬闸门压低` : "",
          "真实买入仍以账户、仓位、停牌/ST/涨跌停和午盘状态最终裁决。",
        ]
          .filter(Boolean)
          .join("；"),
        tone: "positive",
      };
    }
    if (actionable.length && blockedActionable === actionable.length) {
      return {
        label: `本组结论：结构够强，但 ${blockedActionable} 只买入未放行`,
        detail: firstHardReason
          ? `不能买：${firstHardReason}`
          : "硬闸门把最大允许动作压低，先影子跟踪。",
        tone: "warning",
      };
    }
    if (trial > 0) {
      return {
        label: `本组结论：${trial} 只条件试错`,
        detail: missing
          ? `还差：${missing}；未满足前不买。`
          : "必须等触发、承接、资金和失效位同时清楚后再复核。",
        tone: "positive",
      };
    }
    if (shadowReview > 0) {
      return {
        label: `本组结论：${shadowReview} 只影子/复核`,
        detail: firstHardReason
          ? `不能买：${firstHardReason}`
          : missing
            ? `还差：${missing}`
            : "假设可看，但尚未形成买入动作。",
        tone: "watch",
      };
    }
    return {
      label: "本组结论：只观察",
      detail: firstHardReason
        ? `不能买：${firstHardReason}`
        : missing
          ? `还差：${missing}`
          : "结构假设仍不完整。",
      tone: "info",
    };
  }
  const gates = cards.map((stock) => buyGateMeta(stock, group));
  const blocked = gates.filter(
    (gate) => gate.label === "不可买入" || gate.label === "买入拦截",
  ).length;
  const trial = gates.filter((gate) => gate.label === "试错待触发").length;
  const waiting = gates.filter((gate) => gate.label === "买入未放行").length;
  const rankedTrialCards = cards
    .filter(
      (stock) =>
        buyGateMeta(stock, group).label === "试错待触发" && stock.decision_rank,
    )
    .sort(
      (left, right) =>
        Number(left.decision_rank || 999) - Number(right.decision_rank || 999),
    );
  if (rankedTrialCards.length) {
    const first = rankedTrialCards[0];
    const backups = rankedTrialCards
      .slice(1, 3)
      .map((stock) => stock.name || stock.code)
      .filter(Boolean);
    const later = rankedTrialCards
      .slice(3)
      .map((stock) => stock.name || stock.code)
      .filter(Boolean);
    return {
      label: `本组选择：先看 ${first.name || first.code}`,
      detail: [
        backups.length ? `候补：${backups.join("、")}` : "",
        later.length ? `${later.join("、")}靠后` : "",
        "只在各自触发位满足后复核；当前不是直接买入。",
      ]
        .filter(Boolean)
        .join("；"),
      tone: "positive",
    };
  }
  if (trial > 0) {
    return {
      label: `本组结论：${trial} 只条件试错`,
      detail:
        "不是直接买入；先等触发、承接、资金和成交额复核，满足后再进买入动作。",
      tone: "positive",
    };
  }
  if (blocked + waiting === cards.length) {
    return {
      label: "本组结论：不买，等确认",
      detail:
        "先看买入闸门，不看观察阶段；触发、承接、资金和成交额未同时确认前不进场。",
      tone: "warning",
    };
  }
  return {
    label: "本组结论：逐只复核闸门",
    detail: "只有买入闸门从未放行切到触发后复核，才进入下一步执行判断。",
    tone: "info",
  };
}

function DecisionMetricStrip({
  stock,
  limit,
}: {
  stock: StockListCard;
  limit?: number;
}) {
  const flow = formatMetric(stock.flow_today_yi, "亿");
  const amount = formatMetric(stock.amount_yi, "亿");
  const priority = formatMetric(stock.priority_score ?? stock.score);
  const consistency =
    stock.consistency_label || formatMetric(stock.consistency_score);
  const items = [
    stock.execution_quality_label
      ? {
          label: "执行",
          value: stock.execution_quality_label,
          tone: "positive",
        }
      : null,
    consistency ? { label: "一致性", value: consistency, tone: "info" } : null,
    stock.capital_trend || flow
      ? {
          label: "资金",
          value: [stock.capital_trend, flow].filter(Boolean).join("/"),
          tone: "watch",
        }
      : null,
    amount ? { label: "成交", value: amount, tone: "info" } : null,
    priority ? { label: "分", value: priority, tone: "positive" } : null,
  ].filter(Boolean) as { label: string; value: string; tone: string }[];
  if (!items.length) {
    return null;
  }
  const visibleItems =
    typeof limit === "number" ? items.slice(0, limit) : items;
  const hiddenCount = items.length - visibleItems.length;
  return (
    <div className="mt-2 flex max-w-[260px] flex-wrap gap-1.5">
      {visibleItems.map((item) => (
        <Badge
          key={`${stock.code}-${item.label}-${item.value}`}
          tone={item.tone}
        >
          {item.label} {item.value}
        </Badge>
      ))}
      {hiddenCount > 0 ? <Badge tone="info">+{hiddenCount}</Badge> : null}
    </div>
  );
}

function DecisionRankBlock({ stock }: { stock: StockListCard }) {
  if (hasV2(stock)) {
    return (
      <div className="flex max-w-[240px] flex-col gap-2">
        <div className="flex flex-wrap gap-1.5">
          {stock.decision_rank_label ? (
            <Badge tone={stock.decision_rank === 1 ? "positive" : "info"}>
              {stock.decision_rank_label}
            </Badge>
          ) : null}
          <Badge tone={v2ActionTone(stock)}>
            {v2ActionLabel(stock) || "只观察"}
          </Badge>
          {v2ConfidenceLabel(stock) ? (
            <Badge tone="info">置信 {v2ConfidenceLabel(stock)}</Badge>
          ) : null}
        </div>
        <div className="prism-clamp-2 text-[12px] leading-5 text-[var(--text-secondary)]">
          {stock.thesis ||
            stock.decision_summary ||
            stock.why_now ||
            "等待结构假设补全"}
        </div>
      </div>
    );
  }
  return (
    <div className="flex max-w-[220px] flex-col gap-2">
      {stock.decision_rank_label ? (
        <Badge tone={stock.decision_rank === 1 ? "positive" : "info"}>
          {stock.decision_rank_label}
        </Badge>
      ) : null}
      {stock.decision_summary ? (
        <div className="prism-clamp-2 text-[12px] leading-5 text-[var(--text-secondary)]">
          {stock.decision_summary}
        </div>
      ) : (
        <div className="prism-clamp-2 text-[12px] leading-5 text-[var(--text-secondary)]">
          {stock.upgrade_condition || "等待触发条件"}
        </div>
      )}
    </div>
  );
}

function V2StructureStrip({ stock }: { stock: StockListCard }) {
  if (!hasV2(stock)) {
    return null;
  }
  const items = uniqueTexts([
    stock.market_phase,
    stock.theme_phase,
    stock.stock_role,
    stock.playbook,
  ]).slice(0, 4);
  const calibration = v2CalibrationMeta(stock);
  if (
    !items.length &&
    !stock.judge_source &&
    !stock.ai_status &&
    !calibration
  ) {
    return null;
  }
  return (
    <div className="mt-2 flex max-w-[260px] flex-wrap gap-1.5">
      {items.map((item) => (
        <Badge key={`${stock.code}-v2-${item}`} tone="info">
          {item}
        </Badge>
      ))}
      {stock.judge_source ? (
        <Badge tone={stock.judge_source === "ai_judge" ? "positive" : "watch"}>
          {stock.judge_source === "ai_judge" ? "AI Judge" : "Baseline"}
        </Badge>
      ) : null}
      {stock.ai_status && stock.ai_status !== "not_requested" ? (
        <Badge tone="watch">AI {stock.ai_status}</Badge>
      ) : null}
      {calibration ? (
        <Badge tone={calibration.tone}>{calibration.label}</Badge>
      ) : null}
    </div>
  );
}

function FactorSignalStrip({ stock }: { stock: StockListCard }) {
  const tags = (stock.factor_tags ?? []).slice(0, 2);
  const risks = (stock.factor_risk_flags ?? []).slice(0, 2);
  const hasScore = typeof stock.tushare_score === "number";
  const riskLabel = riskLevelLabel(stock.risk_level);
  const primaryReason = stock.block_reason || stock.degrade_reason;
  if (
    !hasScore &&
    !tags.length &&
    !risks.length &&
    !riskLabel &&
    !primaryReason &&
    !stock.crowding_risk &&
    !stock.fake_breakout_risk
  ) {
    return null;
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {hasScore ? (
        <Badge tone="info">
          因子 {Math.round(stock.tushare_score as number)}
        </Badge>
      ) : null}
      {riskLabel ? (
        <Badge tone={riskLevelTone(stock.risk_level)}>风险{riskLabel}</Badge>
      ) : null}
      {primaryReason ? (
        <Badge tone={stock.block_reason ? "risk" : "warning"}>
          {compactRiskText(primaryReason)}
        </Badge>
      ) : null}
      {tags.map((tag) => (
        <Badge key={`factor-tag-${stock.code}-${tag}`} tone="positive">
          {tag}
        </Badge>
      ))}
      {risks.map((risk) => (
        <Badge key={`factor-risk-${stock.code}-${risk}`} tone="risk">
          {risk}
        </Badge>
      ))}
      {stock.crowding_risk ? (
        <Badge tone={stock.crowding_risk_level === "high" ? "risk" : "warning"}>
          {compactRiskText(stock.crowding_risk, 24)}
        </Badge>
      ) : null}
      {stock.fake_breakout_risk ? (
        <Badge
          tone={stock.fake_breakout_risk_level === "high" ? "risk" : "warning"}
        >
          {compactRiskText(stock.fake_breakout_risk, 24)}
        </Badge>
      ) : null}
    </div>
  );
}

function formatChange(value: StockListCard["change_pct"]) {
  if (value === undefined || value === null || value === "") {
    return "";
  }
  const text = String(value);
  return text.includes("%") ? text : `${text}%`;
}

function taskCards(groups: CardGroup<StockListCard>[]) {
  const allCards = groups.flatMap((group) => group.cards || []);
  const v2Cards = allCards.filter(hasV2);
  const hasDeferredGroups = groups.some(groupHasDeferredCards);
  if (v2Cards.length && !hasDeferredGroups) {
    const actionable = v2Cards.filter(
      (stock) => v2Action(stock) === "actionable" && !v2HardBlocks(stock),
    ).length;
    const trial = v2Cards.filter((stock) => v2Action(stock) === "trial").length;
    const blocked = v2Cards.filter(v2HardBlocks).length;
    const eliminated = groups
      .filter((group) =>
        ["eliminated", "lifecycle_downgraded", "lifecycle_exited"].some(
          (hint) => String(group.key || "").includes(hint),
        ),
      )
      .reduce((sum, group) => sum + groupCount(group), 0);
    return [
      {
        label: "可执行待复核",
        value: actionable,
        detail: "仍需硬闸门和人工复核最终放行",
      },
      {
        label: "条件试错",
        value: trial,
        detail: "触发、承接、失效位同时满足后才买",
      },
      {
        label: "硬闸门封顶",
        value: blocked,
        detail: "结构可以看，但最大动作被风控压低",
      },
      {
        label: "应剔除",
        value: eliminated,
        detail: "原始假设被破坏或确认失败",
      },
    ];
  }
  const findCount = (keywords: string[], keyHints: string[] = []) =>
    groups
      .filter((group) => {
        const title = group.title || "";
        const key = group.key || "";
        return (
          keywords.some(
            (keyword) =>
              title.includes(keyword) ||
              displayGroupTitle(title).includes(keyword),
          ) || keyHints.some((hint) => key.includes(hint))
        );
      })
      .reduce((sum, group) => sum + groupCount(group), 0);
  const watching = findCount(["继续观察"], ["watching"]);
  const midday = findCount(["午盘新增"], ["midday_new"]);
  const upgrade = findCount(
    ["可升级", "仍可跟踪", "升级", "结构验证", "条件试错"],
    ["upgrade", "lifecycle_upgraded"],
  );
  const eliminated = findCount(
    ["已淘汰", "剔除", "降级", "退出"],
    ["eliminated", "lifecycle_downgraded", "lifecycle_exited"],
  );
  return [
    {
      label: "必须复核",
      value: watching + midday + upgrade,
      detail: "今天需要看完的观察任务",
    },
    { label: "午盘新增", value: midday, detail: "午盘新进入观察视野" },
    {
      label: "结构验证",
      value: upgrade,
      detail: "看假设、承接和失效，不等于买入",
    },
    { label: "应剔除", value: eliminated, detail: "失效或降级的观察项" },
  ];
}

function FunnelHeader({
  funnel,
  activeLayer,
  onSelect,
}: {
  funnel: FunnelBucket[];
  activeLayer: FunnelLayer;
  onSelect: (layer: FunnelLayer) => void;
}) {
  return (
    <section className="mb-6">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div>
          <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">Funnel</div>
          <h2 className="text-base font-semibold text-[var(--text-primary)]">遴选漏斗</h2>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        {funnel.map((bucket) => {
          const active = bucket.layer === activeLayer;
          return (
            <button
              key={bucket.layer}
              type="button"
              className={cn(
                "focus-ring min-w-[120px] rounded-md border px-3 py-2 text-left transition-colors",
                active
                  ? "border-[var(--border-default)] bg-[var(--bg-tertiary)] text-[var(--text-primary)]"
                  : "border-[var(--border-subtle)] bg-[var(--bg-secondary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
              )}
              onClick={() => onSelect(bucket.layer)}
            >
              <span className="block text-[13px] font-medium">{FUNNEL_LAYER_LABELS[bucket.layer]}</span>
              <span className="mono mt-1 block text-[11px] text-[var(--text-tertiary)]">{bucket.cards.length} 只</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}

function V2AiTelemetryGate({ onOpen }: { onOpen: () => void }) {
  return (
    <section className="mb-5 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <Badge tone="info">AI Judge</Badge>
            <Badge tone="watch">诊断按需加载</Badge>
          </div>
          <h2 className="text-base font-semibold text-[var(--text-primary)]">
            AI 诊断已收起，先复核候选和买入闸门
          </h2>
          <p className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
            需要追查 AI / Baseline 覆盖、fallback 或影子判读时再加载诊断明细。
          </p>
        </div>
        <button
          type="button"
          data-testid="discovery-ai-telemetry-gate"
          className="focus-ring inline-flex h-9 shrink-0 items-center gap-1.5 rounded-md border border-[var(--border-subtle)] px-3 text-[12px] text-[var(--text-primary)]"
          onClick={onOpen}
        >
          <RefreshCw size={13} />
          加载 AI 诊断
        </button>
      </div>
    </section>
  );
}

function ObservationActions({
  stock,
  tradeDate,
  onFeedback,
  compact = false,
}: {
  stock: StockListCard;
  tradeDate?: string;
  onFeedback: (message: string) => void;
  compact?: boolean;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <Link
        href={cardHref(stock)}
        className={cn(
          "focus-ring inline-flex h-8 items-center justify-center rounded-md border border-[var(--border-subtle)] text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
          compact ? "w-8 px-0" : "px-2.5",
        )}
        title="详情"
      >
        {compact ? <ArrowRight size={13} /> : "详情"}
      </Link>
      {open ? (
        <DiscoveryObservationActions
          stock={stock}
          tradeDate={tradeDate}
          compact={compact}
          onFeedback={onFeedback}
        />
      ) : (
        <button
          type="button"
          data-testid="discovery-observation-actions-gate"
          className={cn(
            "focus-ring inline-flex h-8 items-center justify-center gap-1.5 rounded-md border border-[var(--border-subtle)] text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
            compact ? "w-8 px-0" : "px-2.5",
          )}
          onClick={() => setOpen(true)}
          title="展开观察操作"
          aria-label="展开观察操作"
        >
          <ChevronDown size={13} />
          {compact ? null : "操作"}
        </button>
      )}
    </div>
  );
}

function ObservationWorkbench({
  group,
  loading,
  onLoadGroup,
  tradeDate,
  onFeedback,
}: {
  group?: CardGroup<StockListCard>;
  loading: boolean;
  onLoadGroup?: () => void;
  tradeDate?: string;
  onFeedback: (message: string) => void;
}) {
  const cards = group?.cards || [];
  const decision = groupDecisionMeta(group);
  const deferredCards = groupHasDeferredCards(group);
  const deferred = deferredCards && !cards.length;
  const hiddenCardCount = Math.max(groupCount(group) - cards.length, 0);
  const [expandedEvidenceKey, setExpandedEvidenceKey] = useState<string | null>(
    null,
  );

  return (
    <Panel
      title={displayGroupTitle(group?.title) || "观察工作台"}
      eyebrow="Workbench"
      action={<Badge tone="watch">{groupCount(group)} 只</Badge>}
    >
      {loading ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 5 }).map((_, index) => (
            <SkeletonBlock key={index} className="h-20 w-full" />
          ))}
        </div>
      ) : deferred ? (
        <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <div className="text-sm font-semibold text-[var(--text-primary)]">
                本阶段候选按需加载
              </div>
              <p className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
                先保留阶段数量和状态流；需要查看{" "}
                {displayGroupTitle(group?.title)}
                的具体股票、买入闸门和证据时再读取完整候选。
              </p>
            </div>
            <button
              type="button"
              className="focus-ring inline-flex h-9 shrink-0 items-center gap-1.5 rounded-md border border-[var(--border-subtle)] px-3 text-[12px] text-[var(--text-primary)]"
              onClick={onLoadGroup}
            >
              <RefreshCw size={13} />
              加载本阶段候选
            </button>
          </div>
        </div>
      ) : cards.length ? (
        <>
          {decision ? (
            <div className="mb-3 flex flex-col gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <div className="text-[13px] font-semibold text-[var(--text-primary)]">
                  {decision.label}
                </div>
                <div className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
                  {decision.detail}
                </div>
              </div>
              <Badge tone={decision.tone}>先看买入闸门</Badge>
            </div>
          ) : null}
          {deferredCards && hiddenCardCount > 0 ? (
            <div className="mb-3 flex flex-col gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
              <div className="text-[12px] leading-5 text-[var(--text-secondary)]">
                已先显示 {cards.length} 只优先候选，还有 {hiddenCardCount} 只待展开。
              </div>
              <button
                type="button"
                className="focus-ring inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md border border-[var(--border-subtle)] px-2.5 text-[12px] text-[var(--text-primary)]"
                onClick={onLoadGroup}
              >
                <RefreshCw size={13} />
                加载其余候选
              </button>
            </div>
          ) : null}
          <div className="hidden overflow-x-auto lg:block">
            <table className="w-full min-w-[780px] table-fixed text-left text-[12px]">
              <colgroup>
                <col className="w-[16%]" />
                <col className="w-[13%]" />
                <col className="w-[10%]" />
                <col className="w-[14%]" />
                <col className="w-[23%]" />
                <col className="w-[10%]" />
                <col className="w-[14%]" />
              </colgroup>
              <thead className="border-b border-[var(--border-subtle)] text-[11px] uppercase text-[var(--text-tertiary)]">
                <tr>
                  <th className="px-3 py-2 font-medium">选择顺序</th>
                  <th className="px-3 py-2 font-medium">股票 / 主题</th>
                  <th className="px-3 py-2 font-medium">观察阶段</th>
                  <th className="px-3 py-2 font-medium">买入闸门</th>
                  <th className="px-3 py-2 font-medium">决策依据</th>
                  <th className="px-3 py-2 font-medium">风险证据</th>
                  <th className="px-3 py-2 font-medium">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border-subtle)]">
                {cards.map((stock) => {
                  const rowKey = opportunityRowKey(group, stock);
                  const expanded = expandedEvidenceKey === rowKey;
                  const gate = buyGateMeta(stock, group);
                  return (
                    <Fragment key={rowKey}>
                      <tr className="align-top hover:bg-[var(--bg-secondary)]">
                        <td className="px-3 py-3">
                          <DecisionRankBlock stock={stock} />
                        </td>
                        <td className="px-3 py-3">
                          <div className="truncate font-medium text-[var(--text-primary)]">
                            {stock.name || "未知股票"}
                          </div>
                          <div className="mono mt-1 truncate text-[11px] text-[var(--text-tertiary)]">
                            {stock.code}
                          </div>
                          {stock.theme || stock.theme_phase_theme ? (
                            <div className="prism-clamp-2 mt-2 text-[11px] text-[var(--text-tertiary)]">
                              {stock.theme_phase_theme || stock.theme}
                            </div>
                          ) : null}
                        </td>
                        <td className="px-3 py-3">
                          <div className="flex max-w-[160px] flex-wrap gap-1.5">
                            <Badge tone={stageTone(stock, group)}>
                              {stockStageLabel(stock, group)}
                            </Badge>
                            {persistenceLabel(stock) ? (
                              <Badge tone={persistenceTone(stock)}>
                                {persistenceLabel(stock)}
                              </Badge>
                            ) : null}
                          </div>
                        </td>
                        <td className="px-3 py-3">
                          <BuyGateCell
                            stock={stock}
                            group={group}
                            gate={gate}
                            compact
                          />
                        </td>
                        <td className="px-3 py-3">
                          <OpportunityEvidenceCell
                            stock={stock}
                            group={group}
                            gate={gate}
                            expanded={expanded}
                            onToggle={() =>
                              setExpandedEvidenceKey(expanded ? null : rowKey)
                            }
                          />
                        </td>
                        <td className="px-3 py-3">
                          <RiskEvidenceCell stock={stock} />
                        </td>
                        <td className="px-3 py-3">
                          <ObservationActions
                            stock={stock}
                            tradeDate={tradeDate}
                            onFeedback={onFeedback}
                            compact
                          />
                        </td>
                      </tr>
                      {expanded ? (
                        <tr className="bg-[var(--bg-secondary)]">
                          <td colSpan={7} className="px-3 pb-3">
                            <DiscoveryOpportunityEvidenceDetails
                              stock={stock}
                              group={group}
                              gate={gate}
                            />
                          </td>
                        </tr>
                      ) : null}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="flex flex-col gap-3 lg:hidden">
            {cards.map((stock) => {
              const rowKey = opportunityRowKey(group, stock);
              const expanded = expandedEvidenceKey === rowKey;
              const gate = buyGateMeta(stock, group);
              return (
                <div
                  key={`${group?.title}-${stock.code}-mobile`}
                  className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3"
                >
                  <div className="mb-2 flex items-start justify-between gap-2">
                    <div>
                      <div className="text-sm font-medium text-[var(--text-primary)]">
                        {stock.name || "未知股票"}
                      </div>
                      <div className="mono mt-0.5 text-[11px] text-[var(--text-tertiary)]">
                        {stock.code}
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      {stock.decision_rank_label ? (
                        <Badge
                          tone={stock.decision_rank === 1 ? "positive" : "info"}
                        >
                          {stock.decision_rank_label}
                        </Badge>
                      ) : null}
                      {hasV2(stock) ? (
                        <Badge tone={v2ActionTone(stock)}>
                          {v2ActionLabel(stock) || "只观察"}
                        </Badge>
                      ) : null}
                      <Badge tone={stageTone(stock, group)}>
                        {stockStageLabel(stock, group)}
                      </Badge>
                      {persistenceLabel(stock) ? (
                        <Badge tone={persistenceTone(stock)}>
                          {persistenceLabel(stock)}
                        </Badge>
                      ) : null}
                    </div>
                  </div>
                  {stock.decision_summary ? (
                    <p className="text-[12px] leading-5 text-[var(--text-primary)]">
                      {stock.decision_summary}
                    </p>
                  ) : (
                    <p className="text-[12px] leading-5 text-[var(--text-primary)]">
                      {stockInstruction(stock)}
                    </p>
                  )}
                  <DecisionMetricStrip stock={stock} />
                  <div className="mt-3 grid grid-cols-1 gap-2 text-[12px] leading-5 text-[var(--text-secondary)]">
                    <div className="flex items-start gap-2">
                      <span className="text-[var(--text-tertiary)]">
                        买入：
                      </span>
                      <BuyGateCell stock={stock} group={group} gate={gate} />
                    </div>
                    <OpportunityEvidenceCell
                      stock={stock}
                      group={group}
                      gate={gate}
                      expanded={expanded}
                      onToggle={() =>
                        setExpandedEvidenceKey(expanded ? null : rowKey)
                      }
                      className="max-w-none"
                    />
                    {expanded ? (
                      <DiscoveryOpportunityEvidenceDetails
                        stock={stock}
                        group={group}
                        gate={gate}
                        className="bg-[var(--bg-primary)]"
                      />
                    ) : null}
                  </div>
                  <V2StructureStrip stock={stock} />
                  <div className="mt-3">
                    <FactorSignalStrip stock={stock} />
                  </div>
                  <div className="mt-3">
                    <ObservationActions
                      stock={stock}
                      tradeDate={tradeDate}
                      onFeedback={onFeedback}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </>
      ) : (
        <EmptyState>{group?.empty || "当前阶段没有候选。"}</EmptyState>
      )}
    </Panel>
  );
}

export function DiscoveryObservationWorkbench({
  groups,
  activeGroup,
  activeIndex,
  loading,
  initialLoading,
  activeGroupLoadError = "",
  onSelectGroup,
  onLoadGroup,
  onRetryLoadGroup,
  tradeDate,
  onFeedback,
  sidePanel,
  valveStatus,
}: DiscoveryObservationWorkbenchProps) {
  // TODO(B5/cleanup): activeGroup/activeIndex/onSelectGroup superseded by funnel layer state
  const [aiTelemetryOpen, setAiTelemetryOpen] = useState(false);
  const cards = useMemo(() => taskCards(groups), [groups]);
  const hasDeferredGroups = useMemo(
    () => groups.some(groupHasDeferredCards),
    [groups],
  );
  const hasV2Cards = useMemo(
    () => groups.some((group) => (group.cards || []).some(hasV2)),
    [groups],
  );

  // Funnel state: bucket all cards by triage_action_state, manage active layer locally
  const funnel = useMemo(() => bucketByFunnel(groups), [groups]);
  const [activeLayer, setActiveLayer] = useState<FunnelLayer>("focus");
  const activeBucket = funnel.find((b) => b.layer === activeLayer) ?? funnel[0];
  const activeFunnelGroup: CardGroup<StockListCard> | undefined = activeBucket
    ? { key: activeBucket.layer, title: FUNNEL_LAYER_LABELS[activeBucket.layer], cards: activeBucket.cards }
    : undefined;

  return (
    <>
      <section className="mb-5 flex flex-wrap items-center gap-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="text-[11px] uppercase text-[var(--text-tertiary)]">进攻阀门</span>
          <Badge tone={valveTone(valveStatus)}>{valveLabel(valveStatus)}</Badge>
        </div>
        <div className="text-[12px] leading-5 text-[var(--text-secondary)]">
          {valveStatus === "on"
            ? "阀门开启，可按仓位上限开新仓"
            : valveStatus === "limited"
              ? "阀门半开，仅小仓位试错"
              : "阀门关闭，今天不开新仓，整页进入观察模式"}
        </div>
      </section>

      <section className="mb-7 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {initialLoading
          ? Array.from({ length: 4 }).map((_, index) => (
              <MetricSkeleton key={index} />
            ))
          : cards.map((card, index) => (
              <MetricCard
                key={`${card.label}-${index}`}
                {...card}
                tone={index === 0 ? "positive" : index === 1 ? "watch" : "info"}
              />
            ))}
      </section>

      {!hasDeferredGroups && aiTelemetryOpen ? (
        <DiscoveryV2AiTelemetry groups={groups} loading={initialLoading} />
      ) : !hasDeferredGroups && hasV2Cards ? (
        <V2AiTelemetryGate onOpen={() => setAiTelemetryOpen(true)} />
      ) : null}

      {groups.length ? (
        <FunnelHeader funnel={funnel} activeLayer={activeLayer} onSelect={setActiveLayer} />
      ) : null}

      {funnel[0].cards.length === 0 ? (
        <div className="mb-4 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-2 text-[12px] text-[var(--text-secondary)]">
          今天没有可执行候选（值得专注为空），整页进入观察模式。
        </div>
      ) : null}

      <section className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="flex min-w-0 flex-col gap-3">
          <ObservationWorkbench
            group={activeFunnelGroup}
            loading={loading}
            onLoadGroup={onLoadGroup}
            tradeDate={tradeDate}
            onFeedback={onFeedback}
          />
          {activeGroupLoadError ? (
            <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
              {activeGroupLoadError}
              {onRetryLoadGroup ? (
                <button
                  type="button"
                  className="focus-ring ml-3 inline-flex h-7 items-center rounded-md border border-[var(--border-subtle)] px-2 text-[11px] text-[var(--text-primary)]"
                  onClick={onRetryLoadGroup}
                >
                  重试
                </button>
              ) : null}
            </div>
          ) : null}
        </div>

        <div className="flex flex-col gap-6">{sidePanel}</div>
      </section>
    </>
  );
}
