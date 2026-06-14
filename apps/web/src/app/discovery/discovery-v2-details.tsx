"use client";

import { useMemo } from "react";

import { Badge } from "@/components/badge";
import type { CardGroup, StockListCard } from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  hasV2,
  uniqueTexts,
  v2AiDelta,
  v2AiStatus,
  v2AiSummary,
  v2AiTone,
  v2CalibrationMeta,
  v2HardReason,
  v2MissingText,
} from "./discovery-v2-utils";

export type DiscoveryOpportunityEvidenceDetailsProps = {
  stock: StockListCard;
  group?: CardGroup<StockListCard>;
  className?: string;
};

export type DiscoveryV2AiTelemetryProps = {
  groups: CardGroup<StockListCard>[];
  loading: boolean;
};

function factorRankExplanation(stock: StockListCard) {
  if (stock.factor_explanation?.entry_reason) {
    return stock.factor_explanation.entry_reason;
  }
  if (typeof stock.tushare_score === "number") {
    const tags =
      (stock.factor_tags || []).slice(0, 2).join(" / ") || "因子证据可用";
    const risk = (stock.factor_risk_flags || [])[0];
    return `因子 ${Math.round(stock.tushare_score)}：${tags}${risk ? `；主要风险 ${risk}` : ""}`;
  }
  return "";
}

function v2CalibrationReason(stock: StockListCard) {
  return v2CalibrationMeta(stock)?.detail || "";
}

function v2AiTitle(stock: StockListCard) {
  const status = v2AiStatus(stock);
  const summary = v2AiSummary(stock);
  const label = String(summary.label || stock.ai_status_label || "").trim();
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
  return uniqueTexts([
    stock.ai_provider,
    summary.provider,
    stock.ai_model,
    summary.model,
  ])
    .slice(0, 2)
    .join(" / ");
}

function opportunityEvidenceCopy(
  stock: StockListCard,
) {
  const poolReason =
    stock.thesis || stock.reason || stock.detail || "等待更多确认";
  const whyNow = stock.why_now ? `现在：${stock.why_now}` : "";
  const factorReason = factorRankExplanation(stock);
  const structure = uniqueTexts([
    stock.market_phase,
    stock.theme_phase,
    stock.stock_role,
    stock.playbook,
    stock.opportunity_type,
  ]).join(" / ");
  const confirmation =
    v2MissingText(stock, 3) ||
    stock.upgrade_reason ||
    stock.upgrade_condition ||
    stock.setup_label ||
    "等待触发条件";
  const trigger = stock.entry_plan?.trigger
    ? `触发：${stock.entry_plan.trigger}`
    : "";
  const invalidation =
    stock.invalidation ||
    stock.invalid_condition ||
    stock.foot ||
    stock.risk ||
    "触发失效则剔除";
  const hardGate = v2HardReason(stock);
  const riskEvidence = uniqueTexts([
    stock.block_reason,
    stock.degrade_reason,
    stock.risk_tags,
    stock.factor_risk_flags,
    stock.crowding_risk,
    stock.fake_breakout_risk,
  ]).join("；");
  const aiDetail = hasV2(stock)
    ? uniqueTexts([v2AiTitle(stock), v2AiDetail(stock)]).join("；")
    : "";
  const calibration = v2CalibrationReason(stock);
  const summary = stock.decision_summary || poolReason;
  const fields = [
    structure
      ? {
          label: "结构定位",
          tone: "info",
          value: structure,
        }
      : null,
    {
      label: "为什么入池",
      tone: "info",
      value: uniqueTexts([
        poolReason,
        whyNow,
        !whyNow ? factorReason : "",
      ]).join("；"),
    },
    {
      label: "还差什么确认",
      tone: "watch",
      value: uniqueTexts([confirmation, trigger]).join("；"),
    },
    {
      label: "失效条件",
      tone: "risk",
      value: invalidation,
    },
    hardGate
      ? {
          label: "硬闸门",
          tone: "risk",
          value: hardGate,
        }
      : null,
    riskEvidence
      ? {
          label: "风险证据",
          tone: "risk",
          value: riskEvidence,
        }
      : null,
    factorReason && whyNow
      ? {
          label: "因子补充",
          tone: "positive",
          value: factorReason,
        }
      : null,
    aiDetail
      ? {
          label: "AI / Baseline",
          tone: v2AiTone(v2AiStatus(stock) || "not_requested"),
          value: aiDetail,
        }
      : null,
    calibration
      ? {
          label: "校准说明",
          tone: v2CalibrationMeta(stock)?.tone || "info",
          value: calibration,
        }
      : null,
  ].filter((item): item is { label: string; tone: string; value: string } =>
    Boolean(item?.value),
  );
  return { summary, fields };
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
  const detail = firstWithDetail
    ? v2AiDetail(firstWithDetail)
    : "AI 状态会随每只 V2 候选写入页面、Command Brief 和复盘账本。";
  return {
    total: v2Cards.length,
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

export function DiscoveryOpportunityEvidenceDetails({
  stock,
  className,
}: DiscoveryOpportunityEvidenceDetailsProps) {
  const evidence = opportunityEvidenceCopy(stock);
  return (
    <div
      className={cn(
        "rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3",
        className,
      )}
    >
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        <Badge tone="info">完整依据</Badge>
        {v2AiChangedFields(stock).length ? (
          <Badge tone="info">
            AI 改动 {v2AiChangedFields(stock).join("/")}
          </Badge>
        ) : null}
        {v2AiProviderLabel(stock) ? (
          <Badge tone="watch">{v2AiProviderLabel(stock)}</Badge>
        ) : null}
      </div>
      <div className="grid gap-2 md:grid-cols-3">
        {evidence.fields.map((field) => (
          <div
            key={`${stock.code}-${field.label}`}
            className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2"
          >
            <div className="mb-1 flex items-center gap-1.5">
              <Badge tone={field.tone}>{field.label}</Badge>
            </div>
            <p className="text-[12px] leading-5 text-[var(--text-secondary)]">
              {field.value}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

export function DiscoveryV2AiTelemetry({
  groups,
  loading,
}: DiscoveryV2AiTelemetryProps) {
  const telemetry = useMemo(() => v2AiTelemetry(groups), [groups]);

  if (loading && !groups.length) {
    return (
      <section className="mb-5 h-28 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)]" />
    );
  }
  if (!telemetry.total) {
    return null;
  }

  const statusItems = [
    { label: "采用", value: telemetry.aiUsed, tone: "positive" },
    { label: "影子", value: telemetry.aiShadow, tone: "info" },
    { label: "fallback", value: telemetry.fallback, tone: "warning" },
    {
      label: "未调用",
      value: telemetry.notRequested + telemetry.disabled + telemetry.unknown,
      tone: "watch",
    },
  ];

  return (
    <section className="mb-5 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-3">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <Badge tone={telemetry.tone}>AI Judge</Badge>
            <Badge tone="info">覆盖 {telemetry.total} 只 V2 候选</Badge>
            <Badge tone="watch">硬闸门仍最终裁决</Badge>
            {telemetry.provider ? (
              <Badge tone="watch">{telemetry.provider}</Badge>
            ) : null}
          </div>
          <h2 className="text-base font-semibold text-[var(--text-primary)]">
            {telemetry.headline}
          </h2>
          <p className="mt-1 max-w-3xl text-[12px] leading-5 text-[var(--text-secondary)]">
            {telemetry.detail}
          </p>
          <p className="mt-1 max-w-3xl text-[11px] leading-5 text-[var(--text-tertiary)]">
            AI
            只负责结构判读、风险识别和差异记录；停牌/ST/涨跌停、账户、仓位、午盘失败和数据可信度仍会把最大允许动作压低。
          </p>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:w-[420px] lg:shrink-0">
          {statusItems.map((item) => (
            <div
              key={item.label}
              className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2"
            >
              <div className="text-[11px] text-[var(--text-tertiary)]">
                {item.label}
              </div>
              <div
                className="mono mt-1 text-lg font-semibold"
                style={{ color: "var(--text-primary)" }}
              >
                {item.value}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
