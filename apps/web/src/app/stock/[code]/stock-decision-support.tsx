"use client";

import Link from "next/link";

import { Badge } from "@/components/badge";
import { EmptyState } from "@/components/data-card";
import {
  readinessHasStaleData,
  readinessModeCopy,
  refreshTaskCopy,
} from "@/lib/readiness-copy";
import type { StockDetailData, StockProfileData } from "@/lib/types";
import {
  canonicalText,
  displayText,
  uniqueTexts,
} from "./stock-display-utils";

type StockDecisionContext = {
  canonical_decision?: StockDetailData["canonical_decision"];
  decision_cards?: StockDetailData["decision_cards"];
  level_cards?: StockDetailData["level_cards"];
  plan_levels?: StockDetailData["plan_levels"];
  insight_groups?: StockDetailData["insight_groups"];
};

type StockDecisionSupportPanelsProps = {
  decisionLocked: boolean;
  detail?: StockDecisionContext;
  readiness?: StockProfileData["readiness"];
  sourceLabel: string;
  sourceTradeDate?: string;
  displayTradeDate?: string;
  todayAction?: StockProfileData["today_action"] | null;
  onViewEvidence: () => void;
};

type StockDecisionCanonicalSummaryProps = {
  canonical?: StockDetailData["canonical_decision"];
  sourceLabel: string;
  generatedAt?: string;
  embedded?: boolean;
};

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

function insightItems(
  detail: StockDecisionContext | undefined,
  keywords: string[],
) {
  return (detail?.insight_groups || [])
    .filter((group) =>
      keywords.some((keyword) => String(group.title || "").includes(keyword)),
    )
    .flatMap((group) => group.items || []);
}

function evidenceSourceSummary(sourceLabel: string, todayAction?: StockProfileData["today_action"] | null) {
  const labels = uniqueTexts([
    sourceLabel,
    todayAction ? "今日动作队列" : "",
  ]);
  return labels.length
    ? labels.slice(0, 4).join("、")
    : "自选股快照、持仓链路、今日动作队列";
}

function evidenceSupportItems(detail: StockDecisionContext | undefined) {
  const canonical = detail?.canonical_decision;
  const conclusionCard = (detail?.decision_cards || []).find((card) =>
    String(card.label || "").includes("当前结论"),
  );
  const positives = insightItems(detail, ["正向", "加分", "支持"]);
  return uniqueTexts([
    canonical?.why_now,
    conclusionCard?.detail,
    ...positives,
    canonical?.confidence_note,
  ]).slice(0, 3);
}

function evidenceRiskItems(
  detail: StockDecisionContext | undefined,
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
  const isWeekend =
    session?.key === "weekend" || session?.calendar_status === "weekend";
  const isTradingDay = Boolean(session?.is_trading_day);
  const dataStale = readinessHasStaleData(readiness);
  const allowRealMoney =
    mode === "live_ready" &&
    isTradingDay &&
    !dataStale &&
    Boolean(readiness?.ready);
  return { mode, session, isWeekend, dataStale, allowRealMoney };
}

function TradingAvailabilityBar({
  readiness,
}: {
  readiness?: StockProfileData["readiness"];
}) {
  const { mode, session, isWeekend, dataStale, allowRealMoney } =
    readinessFacts(readiness);
  const modeTone =
    mode === "live_ready"
      ? "positive"
      : mode === "blocked"
        ? "risk"
        : "warning";
  const copy = readinessModeCopy(mode);
  const recommendedTask = readiness?.recommended_tasks?.[0];
  const recommendedTaskTitle = recommendedTask
    ? refreshTaskCopy(recommendedTask).title
    : "";
  const statusLines = [
    allowRealMoney
      ? "环境允许手工执行；本票仍按上方动作卡判断。"
      : "环境不允许真钱执行。",
    isWeekend ? "周末休市，仅可影子盘观察" : "",
    dataStale ? "数据偏旧，不可作为真钱依据" : "",
    copy.title,
    recommendedTask && mode !== "live_ready"
      ? `建议下一步：去 Settings 运行 ${recommendedTaskTitle || recommendedTask}`
      : "",
    "真实成交仍需在外部券商完成，本系统不会自动下单。",
  ].filter(Boolean);

  const facts = [
    { label: "当前状态", value: copy.title, tone: modeTone },
    {
      label: "是否周末休市",
      value: isWeekend ? "是" : "否",
      tone: isWeekend ? "warning" : "info",
    },
    {
      label: "是否数据过期",
      value: dataStale ? "是" : "否",
      tone: dataStale ? "warning" : "positive",
    },
    {
      label: "真钱手工执行环境",
      value: allowRealMoney ? "是" : "否",
      tone: allowRealMoney ? "positive" : "risk",
    },
  ];

  return (
    <section className="surface-card border-[var(--border-subtle)] p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">
            System Environment
          </div>
          <h2 className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
            {allowRealMoney
              ? "系统环境：交易链路可用"
              : "系统环境：不可作为真钱依据"}
          </h2>
          <p className="mt-2 text-[12px] leading-5 text-[var(--text-secondary)]">
            {session?.label || "交易状态待确认"}；{copy.title}
            。这是环境状态，不代表本票可动作；本票动作以上方单票卡为准。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge tone={modeTone}>{copy.badge}</Badge>
          <Badge tone={allowRealMoney ? "positive" : "risk"}>
            {allowRealMoney ? "环境允许手工执行" : "环境禁止真钱执行"}
          </Badge>
        </div>
      </div>
      <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-4">
        {facts.map((item) => (
          <div
            key={item.label}
            className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2"
          >
            <div className="text-[11px] text-[var(--text-tertiary)]">
              {item.label}
            </div>
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
  const recommendedTaskTitle = recommendedTask
    ? refreshTaskCopy(recommendedTask).title
    : "";

  return (
    <section className="surface-card border-[color-mix(in_srgb,var(--negative)_32%,transparent)] bg-[color-mix(in_srgb,var(--negative)_8%,transparent)] p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <Badge tone="risk">交易判断冻结</Badge>
            <Badge tone="warning">{copy.title}</Badge>
          </div>
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">
            不使用当前页面内容判断今天是否交易
          </h2>
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
          <div className="text-[11px] text-[var(--text-tertiary)]">
            预期交易日
          </div>
          <div className="mt-1 text-[13px] font-medium text-[var(--text-primary)]">
            {readiness?.expected_trade_date || "-"}
          </div>
        </div>
        <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
          <div className="text-[11px] text-[var(--text-tertiary)]">
            当前数据交易日
          </div>
          <div className="mt-1 text-[13px] font-medium text-[var(--text-primary)]">
            {readiness?.data_trade_date || sourceTradeDate || "-"}
          </div>
        </div>
        <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
          <div className="text-[11px] text-[var(--text-tertiary)]">
            建议刷新
          </div>
          <div className="mt-1 text-[13px] font-medium text-[var(--text-primary)]">
            {recommendedTaskTitle ||
              recommendedTask ||
              "先回 Settings 看推荐任务"}
          </div>
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

function ObservationDecisionBlocks({
  detail,
  readiness,
  sourceLabel,
  sourceTradeDate,
  todayAction,
  onViewEvidence,
}: {
  detail?: StockDecisionContext;
  readiness?: StockProfileData["readiness"];
  sourceLabel: string;
  sourceTradeDate?: string;
  todayAction?: StockProfileData["today_action"] | null;
  onViewEvidence: () => void;
}) {
  const canonical = detail?.canonical_decision;
  const { mode, dataStale } = readinessFacts(readiness);
  const copy = readinessModeCopy(mode);
  const support = evidenceSupportItems(detail);
  const risks = evidenceRiskItems(detail, readiness);
  const dataStatus = [copy.title, dataStale ? "数据偏旧" : "数据新鲜"]
    .filter(Boolean)
    .join(" / ");
  const primaryRisk = (risks[0] || "暂无额外风险摘要").replace(/[。.!！]$/, "");
  const blocks = [
    {
      title: "为什么入池",
      eyebrow: "Reason",
      value: canonical?.why_now || support[0],
      detail:
        support.slice(1).join("；") ||
        canonical?.confidence_note ||
        "先按入池主因判断是否还值得盯。",
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
      detail:
        canonical?.avoid_action || risks[0] || "触发失效条件就先停止原计划。",
      tone: "risk",
    },
  ];

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-4">
      {blocks.map((block) => (
        <section key={block.title} className="surface-card p-4">
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">
              {block.eyebrow}
            </div>
            <Badge tone={block.tone}>{block.title}</Badge>
          </div>
          <div className="text-[14px] font-semibold leading-6 text-[var(--text-primary)]">
            {displayText(block.value)}
          </div>
          <p className="mt-2 text-[12px] leading-5 text-[var(--text-secondary)]">
            {displayText(block.detail, "暂无补充说明")}
          </p>
        </section>
      ))}

      <section className="surface-card p-4">
        <div className="mb-2 flex items-center justify-between gap-2">
          <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">
            Evidence
          </div>
          <Badge tone={dataStale ? "warning" : "positive"}>{dataStatus}</Badge>
        </div>
        <div className="text-[14px] font-semibold leading-6 text-[var(--text-primary)]">
          {evidenceSourceSummary(sourceLabel, todayAction)}
        </div>
        <p className="mt-2 text-[12px] leading-5 text-[var(--text-secondary)]">
          数据交易日{" "}
          {displayText(readiness?.data_trade_date || sourceTradeDate)}；
          {primaryRisk}。
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

export function StockDecisionSupportPanels({
  decisionLocked,
  detail,
  readiness,
  sourceLabel,
  sourceTradeDate,
  displayTradeDate,
  todayAction,
  onViewEvidence,
}: StockDecisionSupportPanelsProps) {
  if (decisionLocked) {
    return (
      <>
        <TradingAvailabilityBar readiness={readiness} />
        <DataFreshnessGate
          readiness={readiness}
          sourceTradeDate={displayTradeDate}
          onViewEvidence={onViewEvidence}
        />
      </>
    );
  }

  return (
    <>
      <TradingAvailabilityBar readiness={readiness} />
      <ObservationDecisionBlocks
        detail={detail}
        readiness={readiness}
        sourceLabel={sourceLabel}
        sourceTradeDate={sourceTradeDate}
        todayAction={todayAction}
        onViewEvidence={onViewEvidence}
      />
    </>
  );
}

export function StockDecisionCanonicalSummary({
  canonical,
  sourceLabel,
  generatedAt,
  embedded = false,
}: StockDecisionCanonicalSummaryProps) {
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
      value: canonicalText(
        canonical,
        "stop_condition",
        canonicalText(canonical, "risk_boundary"),
      ),
      detail: "触发后先停止原计划",
    },
    {
      label: "继续条件",
      value: canonicalText(
        canonical,
        "continue_condition",
        canonicalText(canonical, "trigger_condition"),
      ),
      detail: "满足后再升级动作",
    },
  ];

  return (
    <div className={embedded ? "space-y-3" : "surface-card p-4"}>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Badge tone="info">{sourceLabel}</Badge>
        <Badge tone="watch">弱结论</Badge>
      </div>
      <div className="flex flex-col gap-2">
        {rows.map((row) => (
          <div
            key={row.label}
            className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2"
          >
            <div className="flex min-w-0 items-start justify-between gap-3">
              <span className="shrink-0 text-[11px] text-[var(--text-tertiary)]">
                {row.label}
              </span>
              <span className="min-w-0 text-right text-[12px] font-medium text-[var(--text-primary)]">
                {row.value}
              </span>
            </div>
            <div className="mt-1 text-[11px] leading-4 text-[var(--text-tertiary)]">
              {row.detail}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
