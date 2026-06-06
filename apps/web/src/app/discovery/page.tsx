"use client";

import { ArrowRight, CheckCircle2, ListPlus, RefreshCw, Telescope } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/badge";
import { EmptyState, ErrorState, Panel, SkeletonBlock } from "@/components/data-card";
import { EvidencePanel } from "@/components/evidence-panel";
import { LearningMemoryPreview } from "@/components/learning-memory";
import { MetricCard, MetricSkeleton } from "@/components/metric-card";
import { PageTitle } from "@/components/page-title";
import { TrustBanner } from "@/components/trust-banner";
import { useAddWatchlistStock, useOpportunities, useTodaySummary, useUpdateTodayActionDecision } from "@/lib/hooks";
import type { BasicCard, CardGroup, OpportunitiesData, StockListCard } from "@/lib/types";
import { cn } from "@/lib/utils";

function groupCount(group?: CardGroup<StockListCard>) {
  return Number(group?.count ?? group?.cards?.length ?? 0);
}

function cardHref(stock: StockListCard) {
  return stock.detail_url || (stock.code ? `/stock/${stock.code}` : "#");
}

function displayGroupTitle(title?: string) {
  const text = title || "观察阶段";
  if (text.includes("结构验证") || text.includes("条件试错")) {
    return "结构验证/条件试错";
  }
  if (text.includes("早盘进入")) {
    return "早盘进入";
  }
  if (text.includes("午盘新增")) {
    return "午盘新增";
  }
  if (text.includes("延续升级")) {
    return "结构改善";
  }
  if (text.includes("仍可跟踪") || text.includes("可升级") || text.includes("待升级") || text.includes("升级")) {
    return "结构验证/条件试错";
  }
  if (text.includes("淘汰") || text.includes("剔除") || text.includes("降级") || text.includes("退出")) {
    return "已淘汰";
  }
  return text;
}

function clarifyUpgradeCopy(text: string) {
  return text.replace(/(^|；)升级：/g, "$1确认：").replace(/观察升级：/g, "还差：");
}

function stockInstruction(stock: StockListCard) {
  if (hasV2(stock)) {
    const missing = v2MissingText(stock);
    return [
      stock.name ? `${stock.name}：${v2ActionLabel(stock) || "只观察"}` : v2ActionLabel(stock) || "只观察",
      stock.why_now ? `现在：${stock.why_now}` : "",
      missing ? `还差：${missing}` : "",
      stock.invalidation ? `失效：${stock.invalidation}` : "",
    ].filter(Boolean).join("；");
  }
  if (stock.observation_instruction) {
    return clarifyUpgradeCopy(stock.observation_instruction);
  }
  return [
    stock.name ? `${stock.name}：只观察，不追` : "只观察，不追",
    stock.upgrade_condition ? `还差：${stock.upgrade_condition}` : stock.setup_label ? `还差：${stock.setup_label}` : "",
    stock.invalid_condition ? `失效：${stock.invalid_condition}` : stock.foot ? `失效：${stock.foot}` : "",
  ]
    .filter(Boolean)
    .join("；")
    .replace(/。；/g, "；");
}

function factorRankExplanation(stock: StockListCard) {
  if (stock.factor_explanation?.entry_reason) {
    return stock.factor_explanation.entry_reason;
  }
  if (typeof stock.tushare_score === "number") {
    const tags = (stock.factor_tags || []).slice(0, 2).join(" / ") || "因子证据可用";
    const risk = (stock.factor_risk_flags || [])[0];
    return `因子 ${Math.round(stock.tushare_score)}：${tags}${risk ? `；主要风险 ${risk}` : ""}`;
  }
  return "";
}

function riskLevelTone(level?: string) {
  if (level === "block") {
    return "risk";
  }
  if (level === "degrade") {
    return "warning";
  }
  if (level === "warn") {
    return "watch";
  }
  return "info";
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

function hasMetricValue(value: unknown) {
  const text = String(value ?? "").trim();
  return Boolean(text && text !== "-" && text !== "undefined" && text !== "null");
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

function flattenTexts(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.flatMap((item) => flattenTexts(item));
  }
  const text = String(value ?? "").trim();
  if (!text || text === "-" || text === "undefined" || text === "null") {
    return [];
  }
  return [text];
}

function uniqueTexts(values: unknown[]) {
  const seen = new Set<string>();
  const items: string[] = [];
  values.flatMap((value) => flattenTexts(value)).forEach((text) => {
    if (seen.has(text)) {
      return;
    }
    seen.add(text);
    items.push(text);
  });
  return items;
}

function includesAny(text: string, tokens: string[]) {
  return tokens.some((token) => text.includes(token));
}

const V2_ACTION_ORDER: Record<string, number> = {
  observe: 0,
  review: 1,
  shadow: 2,
  trial: 3,
  actionable: 4,
};

const V2_ACTION_LABELS: Record<string, string> = {
  observe: "只观察",
  review: "人工复核",
  shadow: "影子跟踪",
  trial: "试错待触发",
  actionable: "可执行待复核",
};

function v2Judgment(stock: StockListCard) {
  return stock.opportunity_v2 && typeof stock.opportunity_v2 === "object" && !Array.isArray(stock.opportunity_v2)
    ? stock.opportunity_v2 as Record<string, unknown>
    : {};
}

function v2Nested(stock: StockListCard, key: string) {
  const value = v2Judgment(stock)[key];
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function normalizeV2Action(value: unknown) {
  const action = String(value ?? "").trim();
  return action in V2_ACTION_ORDER ? action : "";
}

function v2Action(stock: StockListCard) {
  return normalizeV2Action(stock.suggested_action || v2Judgment(stock).suggested_action);
}

function hasV2(stock: StockListCard) {
  return Boolean(v2Action(stock) || stock.thesis || stock.why_now || Object.keys(v2Judgment(stock)).length);
}

function v2ActionLabel(stock: StockListCard) {
  const action = v2Action(stock);
  return String(stock.suggested_action_label || v2Judgment(stock).action_label || V2_ACTION_LABELS[action] || "").trim();
}

function v2Rank(action: unknown) {
  return V2_ACTION_ORDER[normalizeV2Action(action)] ?? -1;
}

function v2HardMax(stock: StockListCard) {
  return normalizeV2Action(stock.hard_gate_max_action || v2Nested(stock, "hard_gate").maximum_allowed_action);
}

function v2HardReason(stock: StockListCard) {
  const gate = v2Nested(stock, "hard_gate");
  return uniqueTexts([stock.hard_gate_block_reason, gate.block_reasons]).join("；");
}

function v2HardBlocks(stock: StockListCard) {
  const action = v2Action(stock);
  const desired = normalizeV2Action(v2Judgment(stock).desired_action);
  const maxAction = v2HardMax(stock);
  return Boolean(
    stock.hard_gate_blocks_action ||
    v2HardReason(stock) ||
    (action && maxAction && v2Rank(maxAction) < v2Rank(desired || action))
  );
}

function v2MissingItems(stock: StockListCard) {
  return uniqueTexts([stock.missing_confirmation, v2Judgment(stock).missing_confirmation]);
}

function v2MissingText(stock: StockListCard, maxItems = 2) {
  return v2MissingItems(stock).slice(0, maxItems).join("；");
}

function v2ConfidenceLabel(stock: StockListCard) {
  const raw = stock.confidence ?? v2Judgment(stock).confidence;
  const value = Number(raw);
  if (!Number.isFinite(value)) {
    return "";
  }
  return value <= 1 ? `${Math.round(value * 100)}%` : `${Math.round(value)}%`;
}

function v2CalibrationObject(stock: StockListCard, key: "calibration" | "mode_guard" | "playbook") {
  if (key === "playbook") {
    const flattened = stock.v2_playbook_adjustment;
    if (flattened && typeof flattened === "object" && !Array.isArray(flattened)) {
      return flattened;
    }
    return v2Nested(stock, "calibration").playbook_adjustment as Record<string, unknown> || {};
  }
  return v2Nested(stock, key);
}

function v2CalibrationStageLabel(stage: string) {
  if (stage === "active_ready") {
    return "校准通过";
  }
  if (stage === "cold_start") {
    return "冷启动收紧";
  }
  if (stage === "needs_recalibration") {
    return "复盘收紧";
  }
  if (stage === "validating_pattern") {
    return "样本验证";
  }
  if (stage === "observation_hypothesis") {
    return "样本观察";
  }
  if (stage === "pending_outcome") {
    return "等待复盘";
  }
  return stage;
}

function v2CalibrationMeta(stock: StockListCard) {
  const judgment = v2Judgment(stock);
  const calibration = v2CalibrationObject(stock, "calibration");
  const guard = v2CalibrationObject(stock, "mode_guard");
  const playbook = v2CalibrationObject(stock, "playbook");
  const requested = String(stock.v2_mode_requested ?? judgment.mode_requested ?? guard.requested_mode ?? "").trim();
  const effective = String(stock.v2_mode_effective ?? judgment.mode_effective ?? guard.effective_mode ?? judgment.mode ?? "").trim();
  const stage = String(stock.v2_calibration_stage ?? calibration.sample_stage ?? guard.sample_stage ?? "").trim();
  const reason = String(stock.v2_calibration_guard_reason ?? calibration.guard_reason ?? guard.guard_reason ?? playbook.reason ?? "").trim();
  const mature = stock.v2_calibration_mature_samples ?? calibration.mature_samples ?? guard.mature_samples;
  const activeAllowed = Boolean(stock.v2_active_allowed ?? calibration.active_allowed ?? guard.active_allowed);
  const actionCap = normalizeV2Action(playbook.action_cap);
  const adjustment = Number(playbook.confidence_adjustment);

  if (requested === "active" && effective && effective !== "active") {
    return {
      label: `active→${effective}`,
      tone: "warning",
      detail: reason || "V2 active 尚未通过复盘样本准入。",
    };
  }
  if (actionCap || (Number.isFinite(adjustment) && adjustment < 0)) {
    return {
      label: actionCap ? `playbook≤${V2_ACTION_LABELS[actionCap] || actionCap}` : "playbook收紧",
      tone: "warning",
      detail: reason || "该 playbook 已按复盘结果降权。",
    };
  }
  if (stage === "cold_start" || stage === "needs_recalibration") {
    return {
      label: v2CalibrationStageLabel(stage),
      tone: "warning",
      detail: reason || "V2 校准层临时收紧动作阈值。",
    };
  }
  if (stage || activeAllowed) {
    const sample = mature !== undefined && mature !== null && String(mature).trim() !== "" ? ` ${mature}` : "";
    return {
      label: activeAllowed ? "校准通过" : `${v2CalibrationStageLabel(stage)}${sample}`,
      tone: activeAllowed ? "positive" : "info",
      detail: reason,
    };
  }
  return null;
}

function v2CalibrationReason(stock: StockListCard) {
  return v2CalibrationMeta(stock)?.detail || "";
}

function v2AiSummary(stock: StockListCard) {
  const direct = stock.ai_summary;
  if (direct && typeof direct === "object" && !Array.isArray(direct)) {
    return direct as Record<string, unknown>;
  }
  return v2Nested(stock, "ai_summary");
}

function v2AiDelta(stock: StockListCard) {
  const direct = stock.ai_delta;
  if (direct && typeof direct === "object" && !Array.isArray(direct)) {
    return direct as Record<string, unknown>;
  }
  return v2Nested(stock, "ai_delta");
}

function v2AiStatus(stock: StockListCard) {
  return String(stock.ai_status || v2Judgment(stock).ai_status || v2AiSummary(stock).status || "").trim();
}

function v2AiTone(status: string) {
  if (status === "used") {
    return "positive";
  }
  if (status === "shadow_recorded") {
    return "info";
  }
  if (status === "fallback" || status === "not_configured") {
    return "warning";
  }
  if (status === "disabled" || status === "not_requested") {
    return "watch";
  }
  return "info";
}

function v2AiTitle(stock: StockListCard) {
  const status = v2AiStatus(stock);
  const summary = v2AiSummary(stock);
  const label = String(stock.ai_status_label || summary.label || "").trim();
  if (label) {
    return label;
  }
  if (stock.judge_source === "ai_judge" || status === "used") {
    return "AI Judge 已参与结构判读";
  }
  if (status === "shadow_recorded") {
    return "AI 影子判读已记录";
  }
  if (status === "fallback" || status === "not_configured") {
    return "AI fallback 到 Baseline";
  }
  return "Baseline 结构判断";
}

function v2AiDetail(stock: StockListCard) {
  const summary = v2AiSummary(stock);
  const detail = String(summary.detail || "").trim();
  if (detail) {
    return detail;
  }
  const status = v2AiStatus(stock);
  if (status === "used") {
    return "AI 复核结构、风险和动作语义；硬闸门仍最终封顶。";
  }
  if (status === "shadow_recorded") {
    return "AI 只记录影子判断，本次动作仍按 baseline。";
  }
  if (status === "fallback" || status === "not_configured") {
    return "AI 不可用，本次使用 deterministic baseline。";
  }
  if (status === "disabled") {
    return "AI 配置关闭，本次使用 deterministic baseline。";
  }
  return "本轮未消耗 AI 调用预算，使用 deterministic baseline。";
}

function v2AiChangedFields(stock: StockListCard) {
  const delta = v2AiDelta(stock);
  return uniqueTexts([delta.changed_fields]).slice(0, 4);
}

function v2AiProviderLabel(stock: StockListCard) {
  const summary = v2AiSummary(stock);
  return uniqueTexts([stock.ai_provider, summary.provider, stock.ai_model, summary.model]).slice(0, 2).join(" / ");
}

function v2ActionTone(stock: StockListCard) {
  const action = v2Action(stock);
  if (v2HardBlocks(stock) && action === "actionable") {
    return "watch";
  }
  if (action === "actionable" || action === "trial") {
    return "positive";
  }
  if (action === "review" || action === "shadow") {
    return "watch";
  }
  return "info";
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

function stockStageLabel(stock: StockListCard, group?: CardGroup<StockListCard>) {
  if (hasV2(stock)) {
    return stock.stock_role || stock.playbook || displayGroupTitle(group?.title);
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
  const primaryRisk = stock.block_reason || stock.degrade_reason || riskReasons[0] || "";
  const eliminated = includesAny(stageText, ["已淘汰", "降级", "退出", "剔除", "排除", "excluded", "downgraded", "exited"]);

  if (hasV2(stock)) {
    const action = v2Action(stock) || "observe";
    const label = v2ActionLabel(stock) || V2_ACTION_LABELS[action] || "只观察";
    const hardReason = v2HardReason(stock);
    const hardMax = v2HardMax(stock);
    const missing = v2MissingText(stock);
    const confidence = v2ConfidenceLabel(stock);
    const trigger = stock.entry_plan?.trigger || stock.upgrade_condition || "";
    const hardCap = hardMax ? `最大允许：${V2_ACTION_LABELS[hardMax] || hardMax}` : "";
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
        detail: compactRiskText(stock.invalidation || stock.invalid_condition || hardReason || primaryRisk || "原假设已被破坏"),
      };
    }
    if (hardReason && v2Rank(action) <= v2Rank("shadow")) {
      return {
        label: "买入未放行",
        tone: "risk",
        detail: compactRiskText(primaryDetail || stock.invalidation || "硬闸门限制真实动作", 64),
      };
    }
    if (action === "actionable") {
      return {
        label: v2HardBlocks(stock) ? "买入未放行" : label,
        tone: v2HardBlocks(stock) ? "watch" : "positive",
        detail: compactRiskText(primaryDetail || stock.why_now || "结构、触发和失效位已相对清楚，仍需人工复核", 64),
      };
    }
    if (action === "trial") {
      return {
        label,
        tone: "positive",
        detail: compactRiskText(primaryDetail || stock.why_now || "等触发、承接和账户阀门同时满足", 64),
      };
    }
    if (action === "shadow") {
      return {
        label,
        tone: "watch",
        detail: compactRiskText(primaryDetail || stock.upgrade_reason || stock.why_now || "结构假设可跟踪，但暂不进入买入动作", 64),
      };
    }
    if (action === "review") {
      return {
        label,
        tone: "watch",
        detail: compactRiskText(primaryDetail || stock.upgrade_reason || "结构有线索，但关键确认不足", 64),
      };
    }
    return {
      label: hardReason ? "买入未放行" : label,
      tone: hardReason ? "risk" : "info",
      detail: compactRiskText(primaryDetail || stock.invalidation || stock.upgrade_reason || "结构假设仍不完整", 64),
    };
  }

  if (eliminated) {
    return {
      label: "不可买入",
      tone: "risk",
      detail: compactRiskText(stock.invalid_condition || primaryRisk || "已退出今日观察链路"),
    };
  }
  if (stock.risk_level === "block" || stock.block_reason) {
    return {
      label: "买入拦截",
      tone: "risk",
      detail: compactRiskText(stock.block_reason || primaryRisk || "存在硬执行约束"),
    };
  }

  const trialAction =
    stock.action_intent === "trial_buy" ||
    includesAny(stageText, ["试错", "轻仓", "小仓位", "开仓", "买入", "0.3-0.5", "0.5-0.8", "0.3 成", "0.3成"]);

  if (trialAction) {
    const sizing = stock.position_guidance || stock.entry_plan?.sizing || "";
    const trigger = stock.entry_plan?.trigger || stock.upgrade_condition || "";
    const pending = uniqueTexts([trigger, primaryRisk || riskReasons[0]]).join("；") || "等待触发、承接和资金确认";
    return {
      label: "试错待触发",
      tone: "positive",
      detail: compactRiskText([sizing, pending].filter(Boolean).join("；"), 54),
    };
  }

  const waitingForGate = includesAny(stageText, [
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

  if (stock.risk_level === "degrade" || stock.degrade_reason || stock.avoid_condition || riskReasons.length || waitingForGate) {
    return {
      label: "买入未放行",
      tone: "watch",
      detail: compactRiskText(primaryRisk || stock.upgrade_condition || "等待触发、承接和阀门确认"),
    };
  }
  return {
    label: "仅观察",
    tone: "info",
    detail: compactRiskText(stock.upgrade_condition || "尚未形成买入动作"),
  };
}

function BuyGateCell({ stock, group }: { stock: StockListCard; group?: CardGroup<StockListCard> }) {
  const gate = buyGateMeta(stock, group);
  return (
    <div className="max-w-[190px]">
      <Badge tone={gate.tone}>{gate.label}</Badge>
      <div className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">{gate.detail}</div>
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
    const actionable = v2Cards.filter((stock) => v2Action(stock) === "actionable");
    const realActionable = actionable.filter((stock) => !v2HardBlocks(stock)).length;
    const blockedActionable = actionable.length - realActionable;
    const trial = v2Cards.filter((stock) => v2Action(stock) === "trial").length;
    const shadowReview = v2Cards.filter((stock) => v2Action(stock) === "shadow" || v2Action(stock) === "review").length;
    const missing = v2Cards.flatMap((stock) => v2MissingItems(stock)).slice(0, 2).join("；");
    const firstHardReason = v2HardReason(v2Cards.find(v2HardBlocks) || v2Cards[0]);
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
        ].filter(Boolean).join("；"),
        tone: "positive",
      };
    }
    if (actionable.length && blockedActionable === actionable.length) {
      return {
        label: `本组结论：结构够强，但 ${blockedActionable} 只买入未放行`,
        detail: firstHardReason ? `不能买：${firstHardReason}` : "硬闸门把最大允许动作压低，先影子跟踪。",
        tone: "warning",
      };
    }
    if (trial > 0) {
      return {
        label: `本组结论：${trial} 只条件试错`,
        detail: missing ? `还差：${missing}；未满足前不买。` : "必须等触发、承接、资金和失效位同时清楚后再复核。",
        tone: "positive",
      };
    }
    if (shadowReview > 0) {
      return {
        label: `本组结论：${shadowReview} 只影子/复核`,
        detail: firstHardReason ? `不能买：${firstHardReason}` : (missing ? `还差：${missing}` : "假设可看，但尚未形成买入动作。"),
        tone: "watch",
      };
    }
    return {
      label: "本组结论：只观察",
      detail: firstHardReason ? `不能买：${firstHardReason}` : (missing ? `还差：${missing}` : "结构假设仍不完整。"),
      tone: "info",
    };
  }
  const gates = cards.map((stock) => buyGateMeta(stock, group));
  const blocked = gates.filter((gate) => gate.label === "不可买入" || gate.label === "买入拦截").length;
  const trial = gates.filter((gate) => gate.label === "试错待触发").length;
  const waiting = gates.filter((gate) => gate.label === "买入未放行").length;
  const rankedTrialCards = cards
    .filter((stock) => buyGateMeta(stock, group).label === "试错待触发" && stock.decision_rank)
    .sort((left, right) => Number(left.decision_rank || 999) - Number(right.decision_rank || 999));
  if (rankedTrialCards.length) {
    const first = rankedTrialCards[0];
    const backups = rankedTrialCards.slice(1, 3).map((stock) => stock.name || stock.code).filter(Boolean);
    const later = rankedTrialCards.slice(3).map((stock) => stock.name || stock.code).filter(Boolean);
    return {
      label: `本组选择：先看 ${first.name || first.code}`,
      detail: [
        backups.length ? `候补：${backups.join("、")}` : "",
        later.length ? `${later.join("、")}靠后` : "",
        "只在各自触发位满足后复核；当前不是直接买入。",
      ].filter(Boolean).join("；"),
      tone: "positive",
    };
  }
  if (trial > 0) {
    return {
      label: `本组结论：${trial} 只条件试错`,
      detail: "不是直接买入；先等触发、承接、资金和成交额复核，满足后再进买入动作。",
      tone: "positive",
    };
  }
  if (blocked + waiting === cards.length) {
    return {
      label: "本组结论：不买，等确认",
      detail: "先看买入闸门，不看观察阶段；触发、承接、资金和成交额未同时确认前不进场。",
      tone: "warning",
    };
  }
  return {
    label: "本组结论：逐只复核闸门",
    detail: "只有买入闸门从未放行切到触发后复核，才进入下一步执行判断。",
    tone: "info",
  };
}

function DecisionMetricStrip({ stock }: { stock: StockListCard }) {
  const flow = formatMetric(stock.flow_today_yi, "亿");
  const amount = formatMetric(stock.amount_yi, "亿");
  const priority = formatMetric(stock.priority_score ?? stock.score);
  const consistency = stock.consistency_label || formatMetric(stock.consistency_score);
  const items = [
    stock.execution_quality_label ? { label: "执行", value: stock.execution_quality_label, tone: "positive" } : null,
    consistency ? { label: "一致性", value: consistency, tone: "info" } : null,
    stock.capital_trend || flow ? { label: "资金", value: [stock.capital_trend, flow].filter(Boolean).join("/"), tone: "watch" } : null,
    amount ? { label: "成交", value: amount, tone: "info" } : null,
    priority ? { label: "分", value: priority, tone: "positive" } : null,
  ].filter(Boolean) as { label: string; value: string; tone: string }[];
  if (!items.length) {
    return null;
  }
  return (
    <div className="mt-2 flex max-w-[260px] flex-wrap gap-1.5">
      {items.map((item) => (
        <Badge key={`${stock.code}-${item.label}-${item.value}`} tone={item.tone}>
          {item.label} {item.value}
        </Badge>
      ))}
    </div>
  );
}

function DecisionRankBlock({ stock }: { stock: StockListCard }) {
  if (hasV2(stock)) {
    return (
      <div className="flex max-w-[240px] flex-col gap-2">
        <div className="flex flex-wrap gap-1.5">
          {stock.decision_rank_label ? <Badge tone={stock.decision_rank === 1 ? "positive" : "info"}>{stock.decision_rank_label}</Badge> : null}
          <Badge tone={v2ActionTone(stock)}>{v2ActionLabel(stock) || "只观察"}</Badge>
          {v2ConfidenceLabel(stock) ? <Badge tone="info">置信 {v2ConfidenceLabel(stock)}</Badge> : null}
        </div>
        <div className="text-[12px] leading-5 text-[var(--text-secondary)]">
          {stock.thesis || stock.decision_summary || stock.why_now || "等待结构假设补全"}
        </div>
        <DecisionMetricStrip stock={stock} />
      </div>
    );
  }
  return (
    <div className="flex max-w-[220px] flex-col gap-2">
      {stock.decision_rank_label ? <Badge tone={stock.decision_rank === 1 ? "positive" : "info"}>{stock.decision_rank_label}</Badge> : null}
      {stock.decision_summary ? (
        <div className="text-[12px] leading-5 text-[var(--text-secondary)]">{stock.decision_summary}</div>
      ) : (
        <div className="text-[12px] leading-5 text-[var(--text-secondary)]">{stock.upgrade_condition || "等待触发条件"}</div>
      )}
      <DecisionMetricStrip stock={stock} />
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
  if (!items.length && !stock.judge_source && !stock.ai_status && !calibration) {
    return null;
  }
  return (
    <div className="mt-2 flex max-w-[260px] flex-wrap gap-1.5">
      {items.map((item) => (
        <Badge key={`${stock.code}-v2-${item}`} tone="info">{item}</Badge>
      ))}
      {stock.judge_source ? <Badge tone={stock.judge_source === "ai_judge" ? "positive" : "watch"}>{stock.judge_source === "ai_judge" ? "AI Judge" : "Baseline"}</Badge> : null}
      {stock.ai_status && stock.ai_status !== "not_requested" ? <Badge tone="watch">AI {stock.ai_status}</Badge> : null}
      {calibration ? <Badge tone={calibration.tone}>{calibration.label}</Badge> : null}
    </div>
  );
}

function V2AiInsight({ stock, compact = false }: { stock: StockListCard; compact?: boolean }) {
  if (!hasV2(stock)) {
    return null;
  }
  const status = v2AiStatus(stock) || "not_requested";
  const title = v2AiTitle(stock);
  const detail = v2AiDetail(stock);
  const changed = v2AiChangedFields(stock);
  const provider = v2AiProviderLabel(stock);
  return (
    <div
      className={cn(
        "mt-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-2.5 py-2",
        compact ? "text-[12px]" : "max-w-[280px] text-[11px]",
      )}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge tone={v2AiTone(status)}>{title}</Badge>
        {changed.length ? <Badge tone="info">改动 {changed.join("/")}</Badge> : null}
        {provider ? <Badge tone="watch">{provider}</Badge> : null}
      </div>
      <div className="mt-1 leading-5 text-[var(--text-tertiary)]">{compactRiskText(detail, compact ? 120 : 88)}</div>
    </div>
  );
}

function FactorSignalStrip({ stock }: { stock: StockListCard }) {
  const tags = (stock.factor_tags ?? []).slice(0, 2);
  const risks = (stock.factor_risk_flags ?? []).slice(0, 2);
  const hasScore = typeof stock.tushare_score === "number";
  const riskLabel = riskLevelLabel(stock.risk_level);
  const primaryReason = stock.block_reason || stock.degrade_reason;
  if (!hasScore && !tags.length && !risks.length && !riskLabel && !primaryReason && !stock.crowding_risk && !stock.fake_breakout_risk) {
    return null;
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {hasScore ? <Badge tone="info">因子 {Math.round(stock.tushare_score as number)}</Badge> : null}
      {riskLabel ? <Badge tone={riskLevelTone(stock.risk_level)}>风险{riskLabel}</Badge> : null}
      {primaryReason ? <Badge tone={stock.block_reason ? "risk" : "warning"}>{compactRiskText(primaryReason)}</Badge> : null}
      {tags.map((tag) => (
        <Badge key={`factor-tag-${stock.code}-${tag}`} tone="positive">{tag}</Badge>
      ))}
      {risks.map((risk) => (
        <Badge key={`factor-risk-${stock.code}-${risk}`} tone="risk">{risk}</Badge>
      ))}
      {stock.crowding_risk ? <Badge tone={stock.crowding_risk_level === "high" ? "risk" : "warning"}>{compactRiskText(stock.crowding_risk, 24)}</Badge> : null}
      {stock.fake_breakout_risk ? <Badge tone={stock.fake_breakout_risk_level === "high" ? "risk" : "warning"}>{compactRiskText(stock.fake_breakout_risk, 24)}</Badge> : null}
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

function persistenceTone(stock: StockListCard) {
  const text = `${stock.persistence_label || ""} ${stock.priority_label || ""} ${stock.status || ""} ${stock.invalid_condition || ""}`;
  if (text.includes("非一日脉冲") || text.includes("延续升级")) {
    return "persistent";
  }
  if (text.includes("一日脉冲") || text.includes("退出") || text.includes("降级")) {
    return "risk";
  }
  if (text.includes("延续")) {
    return "watch";
  }
  return "";
}

function persistenceLabel(stock: StockListCard) {
  const tone = persistenceTone(stock);
  if (tone === "persistent") {
    return stock.status?.includes("延续升级") ? "非一日脉冲·升级" : "非一日脉冲";
  }
  if (tone === "risk") {
    return "一日脉冲风险";
  }
  if (tone === "watch") {
    return stock.persistence_label || "延续待确认";
  }
  return "";
}

function lifecycleGroupPulseMeta(group: CardGroup<StockListCard>) {
  const text = `${group.title || ""} ${group.key || ""}`;
  if (text.includes("非一日脉冲") || text.includes("upgraded")) {
    return { label: text.includes("upgraded") ? "非一日脉冲·升级" : "非一日脉冲", tone: "persistent" };
  }
  if (text.includes("降级") || text.includes("退出") || text.includes("downgraded") || text.includes("exited")) {
    return { label: "一日脉冲风险", tone: "risk" };
  }
  if (text.includes("新增") || text.includes("entered") || text.includes("交接") || text.includes("handoff")) {
    return { label: "延续待确认", tone: "watch" };
  }
  return null;
}

function strategyLine(data?: OpportunitiesData) {
  const gate =
    data?.topline?.meta_pills?.find((item) => item.label.includes("阀门"))?.value ||
    data?.hero?.status_label ||
    "";
  if (gate.includes("关闭")) {
    return "今日策略：进攻阀门关闭，只复核观察池，不新增开仓";
  }
  return `今日策略：${data?.topline?.verdict_title || data?.hero?.title || "先复核观察池，再决定下一步"}`;
}

function taskCards(groups: CardGroup<StockListCard>[]) {
  const allCards = groups.flatMap((group) => group.cards || []);
  const v2Cards = allCards.filter(hasV2);
  if (v2Cards.length) {
    const actionable = v2Cards.filter((stock) => v2Action(stock) === "actionable" && !v2HardBlocks(stock)).length;
    const trial = v2Cards.filter((stock) => v2Action(stock) === "trial").length;
    const blocked = v2Cards.filter(v2HardBlocks).length;
    const eliminated = groups
      .filter((group) => ["eliminated", "lifecycle_downgraded", "lifecycle_exited"].some((hint) => String(group.key || "").includes(hint)))
      .reduce((sum, group) => sum + groupCount(group), 0);
    return [
      { label: "可执行待复核", value: actionable, detail: "仍需硬闸门和人工复核最终放行" },
      { label: "条件试错", value: trial, detail: "触发、承接、失效位同时满足后才买" },
      { label: "硬闸门封顶", value: blocked, detail: "结构可以看，但最大动作被风控压低" },
      { label: "应剔除", value: eliminated, detail: "原始假设被破坏或确认失败" },
    ];
  }
  const findCount = (keywords: string[], keyHints: string[] = []) =>
    groups
      .filter((group) => {
        const title = group.title || "";
        const key = group.key || "";
        return (
          keywords.some((keyword) => title.includes(keyword) || displayGroupTitle(title).includes(keyword)) ||
          keyHints.some((hint) => key.includes(hint))
        );
      })
      .reduce((sum, group) => sum + groupCount(group), 0);
  const watching = findCount(["继续观察"], ["watching"]);
  const midday = findCount(["午盘新增"], ["midday_new"]);
  const upgrade = findCount(["可升级", "仍可跟踪", "升级", "结构验证", "条件试错"], ["upgrade", "lifecycle_upgraded"]);
  const eliminated = findCount(["已淘汰", "剔除", "降级", "退出"], ["eliminated", "lifecycle_downgraded", "lifecycle_exited"]);
  return [
    { label: "必须复核", value: watching + midday + upgrade, detail: "今天需要看完的观察任务" },
    { label: "午盘新增", value: midday, detail: "午盘新进入观察视野" },
    { label: "结构验证", value: upgrade, detail: "看假设、承接和失效，不等于买入" },
    { label: "应剔除", value: eliminated, detail: "失效或降级的观察项" },
  ];
}

function v2AiTelemetry(groups: CardGroup<StockListCard>[]) {
  const v2Cards = groups.flatMap((group) => group.cards || []).filter(hasV2);
  const counts = v2Cards.reduce<Record<string, number>>((acc, stock) => {
    const status = v2AiStatus(stock) || "not_requested";
    acc[status] = (acc[status] || 0) + 1;
    return acc;
  }, {});
  const aiUsed = counts.used || 0;
  const aiShadow = counts.shadow_recorded || 0;
  const fallback = (counts.fallback || 0) + (counts.not_configured || 0);
  const notRequested = counts.not_requested || 0;
  const disabled = counts.disabled || 0;
  const unknown = Math.max(
    0,
    v2Cards.length - aiUsed - aiShadow - fallback - notRequested - disabled,
  );
  const firstWithDetail =
    v2Cards.find((stock) => v2AiDetail(stock)) ||
    v2Cards.find((stock) => v2AiTitle(stock)) ||
    v2Cards[0];
  const provider = firstWithDetail ? v2AiProviderLabel(firstWithDetail) : "";
  let headline = "AI 尚未接管，本轮使用 Baseline";
  let tone = "watch";
  if (aiUsed > 0) {
    headline = `AI Judge 已参与 ${aiUsed} 只结构判读`;
    tone = "positive";
  } else if (aiShadow > 0) {
    headline = `AI 影子判读已记录 ${aiShadow} 只`;
    tone = "info";
  } else if (fallback > 0) {
    headline = `AI 未配置，${fallback} 只 fallback 到 Baseline`;
    tone = "warning";
  } else if (notRequested > 0 || disabled > 0) {
    headline = "本轮未调用 AI，使用 deterministic baseline";
    tone = "watch";
  }
  const detail =
    firstWithDetail
      ? v2AiDetail(firstWithDetail)
      : "AI 状态会随每只 V2 候选写入页面、Command Brief 和复盘账本。";
  return {
    total: v2Cards.length,
    counts,
    aiUsed,
    aiShadow,
    fallback,
    notRequested,
    disabled,
    unknown,
    headline,
    tone,
    detail,
    provider,
  };
}

function V2AiTelemetry({ groups, loading }: { groups: CardGroup<StockListCard>[]; loading: boolean }) {
  const telemetry = useMemo(() => v2AiTelemetry(groups), [groups]);

  if (loading && !groups.length) {
    return <SkeletonBlock className="mb-5 h-28 w-full" />;
  }
  if (!telemetry.total) {
    return null;
  }

  const statusItems = [
    { label: "采用", value: telemetry.aiUsed, tone: "positive" },
    { label: "影子", value: telemetry.aiShadow, tone: "info" },
    { label: "fallback", value: telemetry.fallback, tone: "warning" },
    { label: "未调用", value: telemetry.notRequested + telemetry.disabled + telemetry.unknown, tone: "watch" },
  ];

  return (
    <section className="mb-5 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-3">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <Badge tone={telemetry.tone}>AI Judge</Badge>
            <Badge tone="info">覆盖 {telemetry.total} 只 V2 候选</Badge>
            <Badge tone="watch">硬闸门仍最终裁决</Badge>
            {telemetry.provider ? <Badge tone="watch">{telemetry.provider}</Badge> : null}
          </div>
          <h2 className="text-base font-semibold text-[var(--text-primary)]">{telemetry.headline}</h2>
          <p className="mt-1 max-w-3xl text-[12px] leading-5 text-[var(--text-secondary)]">
            {telemetry.detail}
          </p>
          <p className="mt-1 max-w-3xl text-[11px] leading-5 text-[var(--text-tertiary)]">
            AI 只负责结构判读、风险识别和差异记录；停牌/ST/涨跌停、账户、仓位、午盘失败和数据可信度仍会把最大允许动作压低。
          </p>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:w-[420px] lg:shrink-0">
          {statusItems.map((item) => (
            <div key={item.label} className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2">
              <div className="text-[11px] text-[var(--text-tertiary)]">{item.label}</div>
              <div className="mono mt-1 text-lg font-semibold" style={{ color: "var(--text-primary)" }}>{item.value}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function PipelineFlow({
  groups,
  activeIndex,
  onSelect,
}: {
  groups: CardGroup<StockListCard>[];
  activeIndex: number;
  onSelect: (index: number) => void;
}) {
  return (
    <section className="mb-6">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div>
          <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">Pipeline</div>
          <h2 className="text-base font-semibold text-[var(--text-primary)]">观察状态流</h2>
        </div>
        <Badge tone="info">空阶段保留为状态说明</Badge>
      </div>
      <div className="flex gap-2 overflow-x-auto pb-1">
        {groups.map((group, index) => {
          const count = groupCount(group);
          const active = index === activeIndex;
          return (
            <div key={`${group.title}-${index}`} className="flex shrink-0 items-center gap-2">
              <button
                type="button"
                className={cn(
                  "focus-ring min-w-[132px] rounded-md border px-3 py-2 text-left transition-colors",
                  active
                    ? "border-[var(--border-default)] bg-[var(--bg-tertiary)] text-[var(--text-primary)]"
                    : count
                      ? "border-[var(--border-subtle)] bg-[var(--bg-secondary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                      : "border-[var(--border-subtle)] bg-[var(--bg-secondary)] text-[var(--text-tertiary)] opacity-75",
                )}
                onClick={() => onSelect(index)}
              >
                <span className="block text-[13px] font-medium">{displayGroupTitle(group.title)}</span>
                <span className="mono mt-1 block text-[11px] text-[var(--text-tertiary)]">{count} 只</span>
              </button>
              {index < groups.length - 1 ? <ArrowRight size={14} className="shrink-0 text-[var(--text-tertiary)]" /> : null}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function ObservationActions({
  stock,
  onAdd,
  onReview,
  addBusy,
  reviewBusy,
}: {
  stock: StockListCard;
  onAdd: (stock: StockListCard) => void;
  onReview: (stock: StockListCard) => void;
  addBusy: boolean;
  reviewBusy: boolean;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <Link
        href={cardHref(stock)}
        className="focus-ring inline-flex h-8 items-center justify-center rounded-md border border-[var(--border-subtle)] px-2.5 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
      >
        详情
      </Link>
      <button
        type="button"
        className="focus-ring inline-flex h-8 items-center gap-1.5 rounded-md border border-[var(--border-subtle)] px-2.5 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] disabled:cursor-not-allowed disabled:opacity-50"
        onClick={() => onAdd(stock)}
        disabled={addBusy}
      >
        <ListPlus size={13} />
        加入观察计划
      </button>
      <button
        type="button"
        className="focus-ring inline-flex h-8 items-center gap-1.5 rounded-md border border-[var(--border-subtle)] px-2.5 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] disabled:cursor-not-allowed disabled:opacity-50"
        onClick={() => onReview(stock)}
        disabled={reviewBusy || !stock.action_key}
        title={stock.action_key ? "标记已复核" : "这条观察项暂无复核 key"}
      >
        <CheckCircle2 size={13} />
        标记已复核
      </button>
    </div>
  );
}

function ObservationWorkbench({
  group,
  loading,
  onAdd,
  onReview,
  addBusy,
  reviewBusy,
}: {
  group?: CardGroup<StockListCard>;
  loading: boolean;
  onAdd: (stock: StockListCard) => void;
  onReview: (stock: StockListCard) => void;
  addBusy: boolean;
  reviewBusy: boolean;
}) {
  const cards = group?.cards || [];
  const decision = groupDecisionMeta(group);

  return (
    <Panel title={displayGroupTitle(group?.title) || "观察工作台"} eyebrow="Workbench" action={<Badge tone="watch">{groupCount(group)} 只</Badge>}>
      {loading ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 5 }).map((_, index) => <SkeletonBlock key={index} className="h-20 w-full" />)}
        </div>
      ) : cards.length ? (
        <>
          {decision ? (
            <div className="mb-3 flex flex-col gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <div className="text-[13px] font-semibold text-[var(--text-primary)]">{decision.label}</div>
                <div className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">{decision.detail}</div>
              </div>
              <Badge tone={decision.tone}>先看买入闸门</Badge>
            </div>
          ) : null}
          <div className="hidden overflow-x-auto lg:block">
            <table className="w-full min-w-[1180px] text-left text-[12px]">
              <thead className="border-b border-[var(--border-subtle)] text-[11px] uppercase text-[var(--text-tertiary)]">
                <tr>
                  <th className="px-3 py-2 font-medium">选择顺序</th>
                  <th className="px-3 py-2 font-medium">股票 / 主题</th>
                  <th className="px-3 py-2 font-medium">观察阶段</th>
                  <th className="px-3 py-2 font-medium">买入闸门</th>
                  <th className="px-3 py-2 font-medium">为什么入池</th>
                  <th className="px-3 py-2 font-medium">还差什么确认</th>
                  <th className="px-3 py-2 font-medium">失效条件</th>
                  <th className="px-3 py-2 font-medium">风险证据</th>
                  <th className="px-3 py-2 font-medium">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border-subtle)]">
                {cards.map((stock) => (
                  <tr key={`${group?.title}-${stock.code}`} className="align-top hover:bg-[var(--bg-secondary)]">
                    <td className="px-3 py-3">
                      <DecisionRankBlock stock={stock} />
                    </td>
                    <td className="px-3 py-3">
                      <div className="font-medium text-[var(--text-primary)]">{stock.name || "未知股票"}</div>
                      <div className="mono mt-1 text-[11px] text-[var(--text-tertiary)]">{stock.code}</div>
                      {stock.theme || stock.theme_phase_theme ? <div className="mt-2 text-[11px] text-[var(--text-tertiary)]">{stock.theme_phase_theme || stock.theme}</div> : null}
                      <V2StructureStrip stock={stock} />
                      <V2AiInsight stock={stock} />
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex max-w-[160px] flex-wrap gap-1.5">
                        <Badge tone={stageTone(stock, group)}>{stockStageLabel(stock, group)}</Badge>
                        {persistenceLabel(stock) ? <Badge tone={persistenceTone(stock)}>{persistenceLabel(stock)}</Badge> : null}
                      </div>
                    </td>
                    <td className="px-3 py-3">
                      <BuyGateCell stock={stock} group={group} />
                    </td>
                    <td className="max-w-[220px] px-3 py-3 leading-5 text-[var(--text-secondary)]">
                      {stock.thesis || stock.reason || stock.detail || "等待更多确认"}
                      {stock.why_now ? (
                        <div className="mt-1 text-[12px] text-[var(--text-tertiary)]">
                          现在：{stock.why_now}
                        </div>
                      ) : factorRankExplanation(stock) ? (
                        <div className="mt-1 text-[12px] text-[var(--text-tertiary)]">
                          {factorRankExplanation(stock)}
                        </div>
                      ) : null}
                    </td>
                    <td className="max-w-[220px] px-3 py-3 leading-5 text-[var(--text-secondary)]">
                      {v2MissingText(stock) || stock.upgrade_reason || stock.upgrade_condition || stock.setup_label || "等待触发条件"}
                      {stock.entry_plan?.trigger ? (
                        <div className="mt-1 text-[12px] text-[var(--text-tertiary)]">
                          触发：{stock.entry_plan.trigger}
                        </div>
                      ) : null}
                    </td>
                    <td className="max-w-[200px] px-3 py-3 leading-5 text-[var(--text-secondary)]">
                      {stock.invalidation || stock.invalid_condition || stock.foot || stock.risk || "触发失效则剔除"}
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex max-w-[180px] flex-wrap gap-1.5">
                        {v2HardReason(stock) ? <Badge tone="risk">{compactRiskText(v2HardReason(stock), 28)}</Badge> : null}
                        {hasV2(stock) ? <Badge tone={v2AiTone(v2AiStatus(stock) || "not_requested")}>{compactRiskText(v2AiTitle(stock), 28)}</Badge> : null}
                        {v2CalibrationMeta(stock) ? <Badge tone={v2CalibrationMeta(stock)?.tone}>{compactRiskText(v2CalibrationMeta(stock)?.label, 28)}</Badge> : null}
                        {(stock.risk_tags?.length ? stock.risk_tags : [stock.foot || stock.risk].filter(Boolean)).slice(0, 3).map((item) => (
                          <Badge key={String(item)} tone="risk">{String(item)}</Badge>
                        ))}
                        {stock.priority_label ? <Badge tone="info">{stock.priority_label}</Badge> : null}
                        {persistenceLabel(stock) ? <Badge tone={persistenceTone(stock)}>{persistenceLabel(stock)}</Badge> : null}
                        {stock.score !== undefined ? <Badge tone="positive">{stock.score} 分</Badge> : null}
                        {stock.change_pct !== undefined ? <Badge tone="watch">涨幅 {formatChange(stock.change_pct)}</Badge> : null}
                        <FactorSignalStrip stock={stock} />
                      </div>
                    </td>
                    <td className="px-3 py-3">
                      <ObservationActions
                        stock={stock}
                        onAdd={onAdd}
                        onReview={onReview}
                        addBusy={addBusy}
                        reviewBusy={reviewBusy}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex flex-col gap-3 lg:hidden">
            {cards.map((stock) => (
              <div key={`${group?.title}-${stock.code}-mobile`} className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3">
                <div className="mb-2 flex items-start justify-between gap-2">
                  <div>
                    <div className="text-sm font-medium text-[var(--text-primary)]">{stock.name || "未知股票"}</div>
                    <div className="mono mt-0.5 text-[11px] text-[var(--text-tertiary)]">{stock.code}</div>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    {stock.decision_rank_label ? <Badge tone={stock.decision_rank === 1 ? "positive" : "info"}>{stock.decision_rank_label}</Badge> : null}
                    {hasV2(stock) ? <Badge tone={v2ActionTone(stock)}>{v2ActionLabel(stock) || "只观察"}</Badge> : null}
                    <Badge tone={stageTone(stock, group)}>{stockStageLabel(stock, group)}</Badge>
                    {persistenceLabel(stock) ? <Badge tone={persistenceTone(stock)}>{persistenceLabel(stock)}</Badge> : null}
                  </div>
                </div>
                {stock.decision_summary ? (
                  <p className="text-[12px] leading-5 text-[var(--text-primary)]">{stock.decision_summary}</p>
                ) : (
                  <p className="text-[12px] leading-5 text-[var(--text-primary)]">{stockInstruction(stock)}</p>
                )}
                <DecisionMetricStrip stock={stock} />
                <div className="mt-3 grid grid-cols-1 gap-2 text-[12px] leading-5 text-[var(--text-secondary)]">
                  <div className="flex items-start gap-2">
                    <span className="text-[var(--text-tertiary)]">买入：</span>
                    <BuyGateCell stock={stock} group={group} />
                  </div>
                  <div><span className="text-[var(--text-tertiary)]">入池：</span>{stock.thesis || stock.reason || stock.detail || "等待更多确认"}</div>
                  {stock.why_now ? <div><span className="text-[var(--text-tertiary)]">现在：</span>{stock.why_now}</div> : null}
                  <div><span className="text-[var(--text-tertiary)]">还差：</span>{v2MissingText(stock) || stock.upgrade_reason || stock.upgrade_condition || stock.setup_label || "等待触发条件"}</div>
                  <div><span className="text-[var(--text-tertiary)]">失效：</span>{stock.invalidation || stock.invalid_condition || stock.foot || stock.risk || "触发失效则剔除"}</div>
                  {v2HardReason(stock) ? <div><span className="text-[var(--text-tertiary)]">硬闸门：</span>{v2HardReason(stock)}</div> : null}
                  {hasV2(stock) ? <div><span className="text-[var(--text-tertiary)]">AI：</span>{v2AiTitle(stock)}；{v2AiDetail(stock)}</div> : null}
                  {v2CalibrationReason(stock) ? <div><span className="text-[var(--text-tertiary)]">校准：</span>{v2CalibrationReason(stock)}</div> : null}
                  {typeof stock.tushare_score === "number" && (
                    <div className="text-[12px] text-[var(--text-secondary)]">
                      {factorRankExplanation(stock)}
                    </div>
                  )}
                </div>
                <V2StructureStrip stock={stock} />
                <V2AiInsight stock={stock} compact />
                <div className="mt-3">
                  <FactorSignalStrip stock={stock} />
                </div>
                <div className="mt-3">
                  <ObservationActions
                    stock={stock}
                    onAdd={onAdd}
                    onReview={onReview}
                    addBusy={addBusy}
                    reviewBusy={reviewBusy}
                  />
                </div>
              </div>
            ))}
          </div>
        </>
      ) : (
        <EmptyState>{group?.empty || "当前阶段没有候选。"}</EmptyState>
      )}
    </Panel>
  );
}

function ThemeRadar({ cards }: { cards?: BasicCard[] }) {
  return (
    <Panel title="主线雷达" eyebrow="Themes">
      <div className="flex flex-col gap-2">
        {cards?.length ? (
          cards.slice(0, 5).map((card, index) => (
            <div key={`${card.title}-${index}`} className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate text-[13px] font-medium text-[var(--text-primary)]">{card.title || "未命名主题"}</div>
                  <p className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">{card.detail || card.copy || "等待主题延续性确认。"}</p>
                </div>
                <Badge tone="watch">{card.score ?? card.value ?? "-"}</Badge>
              </div>
              {card.leaders?.length ? (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {card.leaders.slice(0, 6).map((leader) => <Badge key={leader} tone="info">{leader}</Badge>)}
                </div>
              ) : null}
            </div>
          ))
        ) : (
          <EmptyState>暂无主线热力。</EmptyState>
        )}
      </div>
    </Panel>
  );
}

function LifecycleTracker({ data }: { data?: OpportunitiesData }) {
  const groups = data?.lifecycle_groups || [];
  const activeGroups = groups.filter((group) => groupCount(group) > 0);
  const cards = data?.lifecycle_cards || [];

  return (
    <Panel title="延续追踪" eyebrow="Lifecycle">
      {cards.length ? (
        <div className="mb-3 grid grid-cols-3 gap-2">
          {cards.slice(0, 3).map((card) => (
            <div key={card.label} className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-2.5 py-2">
              <div className="text-[11px] text-[var(--text-tertiary)]">{card.label}</div>
              <div className="mono mt-1 text-sm font-semibold text-[var(--text-primary)]">{card.value}</div>
              <div className="mt-1 truncate text-[10px] text-[var(--text-tertiary)]">{card.detail}</div>
            </div>
          ))}
        </div>
      ) : null}

      {data?.lifecycle_note ? (
        <p className="mb-3 text-[12px] leading-5 text-[var(--text-secondary)]">{data.lifecycle_note}</p>
      ) : null}

      <div className="mb-3 flex flex-wrap gap-1.5">
        <Badge tone="persistent">非一日脉冲</Badge>
        <Badge tone="watch">延续待确认</Badge>
        <Badge tone="risk">一日脉冲风险</Badge>
      </div>

      {activeGroups.length ? (
        <div className="flex flex-col gap-2">
          {activeGroups.slice(0, 4).map((group) => {
            const pulseMeta = lifecycleGroupPulseMeta(group);
            return (
              <div key={group.key || group.title} className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <div className="text-[13px] font-medium text-[var(--text-primary)]">{displayGroupTitle(group.title)}</div>
                  <div className="flex shrink-0 flex-wrap justify-end gap-1.5">
                    {pulseMeta ? <Badge tone={pulseMeta.tone}>{pulseMeta.label}</Badge> : null}
                    <Badge tone="info">{groupCount(group)} 只</Badge>
                  </div>
                </div>
              <div className="flex flex-col gap-2">
                {(group.cards || []).slice(0, 3).map((stock) => (
                  <Link
                    key={`${group.key || group.title}-${stock.code}`}
                    href={cardHref(stock)}
                    className="focus-ring rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2.5 py-2 hover:border-[var(--border-default)]"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="truncate text-[12px] font-medium text-[var(--text-primary)]">{stock.name || stock.code}</div>
                        <div className="mono mt-0.5 text-[10px] text-[var(--text-tertiary)]">{stock.code}</div>
                      </div>
                      <div className="flex shrink-0 flex-col items-end gap-1">
                        <Badge tone={stock.tone}>{stock.status || group.title}</Badge>
                        {persistenceLabel(stock) ? <Badge tone={persistenceTone(stock)}>{persistenceLabel(stock)}</Badge> : null}
                      </div>
                    </div>
                    <p className="mt-2 line-clamp-2 text-[11px] leading-5 text-[var(--text-secondary)]">
                      {stock.detail || stock.observation_instruction || "等待下一轮追踪。"}
                    </p>
                  </Link>
                ))}
              </div>
            </div>
            );
          })}
        </div>
      ) : (
        <EmptyState>暂无跨天变化。今天没有出现，不等于历史观察被删除。</EmptyState>
      )}
    </Panel>
  );
}

export default function DiscoveryPage() {
  const opportunities = useOpportunities();
  const today = useTodaySummary();
  const trust = today.data?.readiness?.trust_level;
  const addStock = useAddWatchlistStock();
  const reviewDecision = useUpdateTodayActionDecision();
  const data = opportunities.data;
  const groups = data?.groups?.length ? data.groups : data?.secondary_groups || [];
  const learningMemories = data?.learning_memories || [];
  const totalGroupCount = useMemo(() => groups.reduce((sum, group) => sum + groupCount(group), 0), [groups]);
  const trustBlocksTopline = trust && trust.level !== "trusted" && totalGroupCount === 0;
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const [feedback, setFeedback] = useState("");
  const firstNonEmptyIndex = useMemo(() => {
    const index = groups.findIndex((group) => groupCount(group) > 0);
    return index >= 0 ? index : 0;
  }, [groups]);
  const resolvedActiveIndex = Math.min(activeIndex ?? firstNonEmptyIndex, Math.max(groups.length - 1, 0));
  const activeGroup = groups[resolvedActiveIndex];
  const cards = useMemo(() => taskCards(groups), [groups]);

  useEffect(() => {
    if (!groups.length) {
      return;
    }
    if (activeIndex === null || activeIndex >= groups.length) {
      setActiveIndex(firstNonEmptyIndex);
    }
  }, [activeIndex, firstNonEmptyIndex, groups.length]);

  function addToObservationPlan(stock: StockListCard) {
    setFeedback("");
    addStock.mutate(
      { code: stock.code, name: stock.name, trigger_refresh: true },
      {
        onSuccess: (payload) => setFeedback(payload.message || `${stock.name || stock.code} 已加入观察计划。`),
        onError: (error) => setFeedback(error instanceof Error ? error.message : "加入观察计划失败"),
      },
    );
  }

  function markReviewed(stock: StockListCard) {
    if (!data?.trade_date || !stock.action_key) {
      setFeedback("这条观察项暂时没有可回写的复核 key。");
      return;
    }
    setFeedback("");
    reviewDecision.mutate(
      { trade_date: data.trade_date, key: stock.action_key, decision: "done" },
      {
        onSuccess: () => setFeedback(`${stock.name || stock.code} 已标记为已复核。`),
        onError: (error) => setFeedback(error instanceof Error ? error.message : "标记已复核失败"),
      },
    );
  }

  return (
    <main className="flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
      <div className="mx-auto max-w-7xl">
        <PageTitle
          eyebrow={data?.display_date || data?.generated_at?.slice(0, 10) || data?.trade_date || "Discovery"}
          title={trustBlocksTopline ? "观察池" : (data?.topline?.verdict_title || data?.hero?.title || "观察池")}
          summary={trustBlocksTopline
            ? "今日观察池没有产生新名字。先按下方可信度提示完成恢复，再决定要不要复核。"
            : data?.topline?.verdict_summary || data?.hero?.summary || "候选 Pipeline、阀门状态、质检和主线热力。"}
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

        {trust && trust.level !== "trusted" ? (
          <TrustBanner trust={trust} readiness={today.data?.readiness} className="mb-4" />
        ) : null}

        {opportunities.isError ? (
          <ErrorState message="观察池数据暂不可用" onRetry={() => void opportunities.refetch()} />
        ) : null}

        <section className="mb-5 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-3">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <Badge tone={data?.brief_is_live ? "positive" : "watch"}>{data?.brief_is_live ? "总控同步" : "实时链路"}</Badge>
                {data?.trade_date ? <Badge tone="info">交易日 {data.trade_date}</Badge> : null}
              </div>
              <h2 className="text-lg font-semibold text-[var(--text-primary)]">{strategyLine(data)}</h2>
              <p className="mt-2 text-[12px] leading-5 text-[var(--text-secondary)]">
                {data?.topline?.verdict_summary || data?.hero?.summary || "把候选池当作复核队列，而不是可随手挑选的股票列表。"}
              </p>
            </div>
            {feedback ? (
              <div className="rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
                {feedback}
              </div>
            ) : null}
          </div>
        </section>

        <section className="mb-7 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {opportunities.isLoading && !data
            ? Array.from({ length: 4 }).map((_, index) => <MetricSkeleton key={index} />)
            : cards.map((card, index) => (
                <MetricCard key={`${card.label}-${index}`} {...card} tone={index === 0 ? "positive" : index === 1 ? "watch" : "info"} />
              ))}
        </section>

        <V2AiTelemetry groups={groups} loading={opportunities.isLoading && !data} />

        {groups.length ? (
          <PipelineFlow groups={groups} activeIndex={resolvedActiveIndex} onSelect={setActiveIndex} />
        ) : null}

        <section className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
          <ObservationWorkbench
            group={activeGroup}
            loading={opportunities.isLoading && !data}
            onAdd={addToObservationPlan}
            onReview={markReviewed}
            addBusy={addStock.isPending}
            reviewBusy={reviewDecision.isPending}
          />

          <div className="flex flex-col gap-6">
            {learningMemories.length ? (
              <Panel title="历史提醒" eyebrow="Pattern Memory">
                <LearningMemoryPreview memories={learningMemories} limit={3} />
              </Panel>
            ) : null}

            <LifecycleTracker data={data} />

            <ThemeRadar cards={data?.theme_cards} />

            <EvidencePanel page="opportunities" sources={data?.source_cards} title="数据健康" eyebrow="Freshness" compact />
          </div>
        </section>
      </div>
    </main>
  );
}
