"use client";

import { AlertCircle, ArrowRight } from "lucide-react";
import Link from "next/link";

import { ActionRow, ActionRowSkeleton } from "@/components/action-row";
import { Badge } from "@/components/badge";
import { EvidencePanel } from "@/components/evidence-panel";
import { MetricCard, MetricSkeleton } from "@/components/metric-card";
import { RiskAlert } from "@/components/risk-alert";
import { useTodayData, useUpdateTodayActionDecision } from "@/lib/hooks";
import type { DecisionValue, MetricCardData, RiskRow } from "@/lib/types";
import { asText } from "@/lib/utils";

function inferMetricTone(card: MetricCardData, index: number) {
  const label = `${card.label} ${card.detail || ""}`;
  if (card.tone) {
    return card.tone;
  }
  if (label.includes("质检") || label.includes("通过")) {
    return "positive";
  }
  if (label.includes("持仓") || index === 0) {
    return "sell";
  }
  if (label.includes("午盘") || label.includes("新增")) {
    return "positive";
  }
  if (label.includes("候选") || label.includes("观察")) {
    return "watch";
  }
  return "info";
}

function HeroSkeleton() {
  return (
    <section className="mb-8 animate-pulse">
      <div className="mb-3 flex items-center gap-2">
        <div className="h-4 w-36 rounded bg-[var(--bg-tertiary)]" />
        <div className="h-5 w-20 rounded-full bg-[var(--bg-tertiary)]" />
      </div>
      <div className="h-9 max-w-xl rounded bg-[var(--bg-tertiary)]" />
      <div className="mt-4 h-4 max-w-2xl rounded bg-[var(--bg-tertiary)]" />
      <div className="mt-5 flex gap-2">
        <div className="h-6 w-24 rounded-full bg-[var(--bg-tertiary)]" />
        <div className="h-6 w-28 rounded-full bg-[var(--bg-tertiary)]" />
        <div className="h-6 w-24 rounded-full bg-[var(--bg-tertiary)]" />
      </div>
    </section>
  );
}

function SectionHeader({
  eyebrow,
  title,
  action,
}: {
  eyebrow: string;
  title: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="mb-4 flex min-w-0 items-end justify-between gap-4">
      <div className="min-w-0">
        <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">{eyebrow}</div>
        <h2 className="mt-1 truncate text-lg font-semibold text-[var(--text-primary)]">{title}</h2>
      </div>
      {action}
    </div>
  );
}

export default function CommandCenterPage() {
  const today = useTodayData();
  const updateDecision = useUpdateTodayActionDecision();
  const data = today.data;
  const hero = data?.command_hero;
  const displayDate = data?.display_date || data?.generated_at?.slice(0, 10) || data?.trade_date || hero?.trade_date;
  const showTradeDateBadge = Boolean(data?.display_date && data?.trade_date && data.display_date !== data.trade_date);
  const summaryCards = data?.summary_cards?.length ? data.summary_cards : data?.radar_cards ?? [];
  const actionItems = data?.action_queue?.items ?? [];
  const counts = data?.action_queue?.counts;
  const completed = counts?.done ?? 0;
  const total = counts?.total ?? actionItems.length;
  const progress = total > 0 ? Math.round((completed / total) * 100) : 0;
  const risks: RiskRow[] =
    data?.risk_rows?.length
      ? data.risk_rows
      : data?.hero?.context_note
        ? [
            {
              title: data.brief_is_live ? "总控已同步" : "实时链路判断",
              action: data.hero.gate_label,
              reason: data.hero.context_note,
              tone: data.brief_is_live ? "positive" : "warning",
            },
          ]
        : [];

  function handleDecision(key: string, decision: DecisionValue) {
    if (!data) {
      return;
    }
    updateDecision.mutate({
      trade_date: data.trade_date,
      key,
      decision,
    });
  }

  return (
    <main className="flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
      <div className="mx-auto max-w-6xl">
        {today.isError ? (
          <div className="mb-6 flex items-start gap-3 rounded-md border border-[color-mix(in_srgb,var(--warning)_20%,transparent)] bg-[color-mix(in_srgb,var(--warning)_8%,transparent)] px-4 py-3 text-[13px] text-[var(--text-secondary)]">
            <AlertCircle size={17} className="mt-0.5 shrink-0 text-[var(--warning)]" />
            <div className="min-w-0 flex-1">
              <div className="font-medium text-[var(--text-primary)]">后端数据暂不可用</div>
              <div className="mt-1">指挥中心骨架已加载，FastAPI 启动后会自动重新获取 `/api/today`。</div>
            </div>
            <button
              type="button"
              className="focus-ring rounded-md border border-[var(--border-subtle)] px-2.5 py-1 text-[12px] text-[var(--text-primary)]"
              onClick={() => void today.refetch()}
            >
              重试
            </button>
          </div>
        ) : null}

        {today.isLoading && !data ? (
          <HeroSkeleton />
        ) : (
          <section className="mb-8">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <div className="mono text-[11px] font-medium uppercase text-[var(--info)]">
                {asText(displayDate, "日期待同步")}
              </div>
              {showTradeDateBadge ? <Badge tone="watch">数据交易日 {data?.trade_date}</Badge> : null}
              <Badge tone={data?.brief_is_live ? "positive" : "warning"}>
                {data?.hero?.gate_label || hero?.source_state || "实时链路"}
              </Badge>
            </div>
            <h1 className="max-w-4xl text-balance text-[32px] font-bold leading-tight text-[var(--text-primary)]">
              {hero?.title || data?.hero?.title || "先处理旧仓，再决定是否看新仓"}
            </h1>
            <p className="mt-3 max-w-3xl text-[15px] leading-7 text-[var(--text-secondary)]">
              {hero?.summary || data?.hero?.summary || "等待总控数据同步。"}
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <Badge tone="info">仓位上限 {asText(data?.hero?.position_cap)}</Badge>
              <Badge tone="watch">主线 {asText(data?.hero?.main_theme)}</Badge>
              <Badge tone={data?.brief_is_live ? "positive" : "warning"}>
                {data?.brief_is_live ? "总控同步" : "实时判断"}
              </Badge>
            </div>
          </section>
        )}

        <section className="mb-8 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {today.isLoading && !summaryCards.length
            ? Array.from({ length: 4 }).map((_, index) => <MetricSkeleton key={index} />)
            : summaryCards.slice(0, 4).map((card, index) => (
                <MetricCard
                  key={`${card.label}-${index}`}
                  label={card.label}
                  value={String(card.value ?? "-")}
                  detail={card.detail || card.note}
                  tone={inferMetricTone(card, index)}
                />
              ))}
        </section>

        <section className="mb-8">
          <SectionHeader
            eyebrow="今日待办"
            title={data?.action_queue?.title || "Action Queue"}
            action={
              <div className="hidden items-center gap-3 sm:flex">
                <span className="text-[12px] text-[var(--text-tertiary)]">
                  {completed}/{total || 0} 已完成
                </span>
                <div className="h-1 w-24 overflow-hidden rounded-full bg-[var(--bg-tertiary)]">
                  <div className="h-full rounded-full bg-[var(--positive)]" style={{ width: `${progress}%` }} />
                </div>
              </div>
            }
          />

          <div className="surface-card px-4">
            {today.isLoading && !actionItems.length
              ? Array.from({ length: 4 }).map((_, index) => <ActionRowSkeleton key={index} />)
              : actionItems.length
                ? actionItems.map((item) => (
                    <ActionRow
                      key={item.key}
                      item={item}
                      disabled={updateDecision.isPending}
                      onDecision={handleDecision}
                    />
                  ))
                : (
                  <div className="py-8 text-center text-[13px] text-[var(--text-tertiary)]">
                    当前没有必须处理的动作。
                  </div>
                )}
          </div>
          {updateDecision.isError ? (
            <div className="mt-3 rounded-md border border-[color-mix(in_srgb,var(--negative)_20%,transparent)] bg-[color-mix(in_srgb,var(--negative)_8%,transparent)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
              动作状态更新失败：{updateDecision.error?.message || "请确认后端服务可用后重试。"}
            </div>
          ) : null}
          {updateDecision.isSuccess ? (
            <div className="mt-3 rounded-md border border-[color-mix(in_srgb,var(--positive)_20%,transparent)] bg-[color-mix(in_srgb,var(--positive)_8%,transparent)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
              动作状态已同步。
            </div>
          ) : null}
          {data?.action_queue?.hidden_count ? (
            <div className="mt-2 text-right text-[11px] text-[var(--text-tertiary)]">
              还有 {data.action_queue.hidden_count} 条已收起
            </div>
          ) : null}
        </section>

        <section className="mb-8">
          <SectionHeader eyebrow="风险提醒" title="Risk Alerts" />
          <div className="flex flex-col gap-2">
            {risks.length ? (
              risks.slice(0, 3).map((row, index) => <RiskAlert key={`${row.title}-${index}`} row={row} />)
            ) : (
              <div className="surface-panel px-4 py-3 text-[13px] text-[var(--text-tertiary)]">
                风险链路等待数据同步。
              </div>
            )}
          </div>
        </section>

        <section className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div>
            <SectionHeader eyebrow="快速跳转" title="Quick Links" />
            <div className="flex flex-col gap-2">
              {[
                { label: "持仓管理", href: "/portfolio", count: data?.counts?.watchlist_total },
                { label: "观察池候选", href: "/discovery", count: data?.counts?.candidate_total },
                { label: "午盘确认", href: "/discovery", count: data?.counts?.fresh_candidates },
                { label: "复盘仪表盘", href: "/review", count: data?.counts?.confirmed },
              ].map((item) => (
                <Link
                  key={`${item.label}-${item.href}`}
                  href={item.href}
                  className="focus-ring flex items-center justify-between gap-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-3 text-[13px] text-[var(--text-secondary)] hover:border-[var(--border-default)] hover:text-[var(--text-primary)]"
                >
                  <span>{item.label}</span>
                  <span className="flex items-center gap-3">
                    {item.count !== undefined ? <span className="mono text-[var(--text-primary)]">{item.count}</span> : null}
                    <ArrowRight size={14} className="text-[var(--text-tertiary)]" />
                  </span>
                </Link>
              ))}
            </div>
          </div>

          <EvidencePanel page="today" sources={data?.source_cards} title="数据源" eyebrow="Data Sources" />
        </section>
      </div>
    </main>
  );
}
