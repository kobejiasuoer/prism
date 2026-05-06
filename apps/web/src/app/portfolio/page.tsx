"use client";

import { RefreshCw, WalletCards } from "lucide-react";

import { Badge } from "@/components/badge";
import { EmptyState, ErrorState, Panel, SkeletonBlock } from "@/components/data-card";
import { EvidencePanel } from "@/components/evidence-panel";
import { MetricCard, MetricSkeleton } from "@/components/metric-card";
import { PageTitle } from "@/components/page-title";
import { StockCard } from "@/components/stock-card";
import { WatchlistManagerPanel } from "@/components/watchlist-manager-panel";
import { useWatchlist } from "@/lib/hooks";
import type { WatchlistDayOverDayDiff } from "@/lib/types";

function formatDiffValue(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "-";
  return String(value);
}

function DayOverDayDiffPanel({ diff }: { diff?: WatchlistDayOverDayDiff }) {
  if (!diff) return null;
  if (!diff.previous_trade_date) {
    return (
      <Panel title="日间变动" eyebrow="Day-over-day">
        <div className="surface-card p-4">
          <EmptyState>暂无昨日快照可对比。</EmptyState>
        </div>
      </Panel>
    );
  }

  const changeCount =
    diff.added.length +
    diff.removed.length +
    diff.action_changes.length +
    diff.group_changes.length +
    diff.boundary_changes.length +
    diff.signal_changes.length;

  return (
    <Panel
      title="日间变动"
      eyebrow={`${diff.previous_trade_date} → ${diff.today_trade_date ?? "今日"}`}
      action={<Badge tone={changeCount > 0 ? "watch" : "positive"}>{changeCount} 项变化</Badge>}
    >
      <div className="surface-card flex flex-col gap-3 p-4 text-[12px] text-[var(--text-secondary)]">
        {changeCount === 0 ? (
          <EmptyState>持仓维持昨日状态，无动作变更。</EmptyState>
        ) : null}

        {diff.added.length > 0 ? (
          <DiffSection label="新增持仓" tone="info">
            {diff.added.map((s) => (
              <li key={s.code}>
                <strong>{s.code}</strong> {s.name}
                {s.action ? <span className="ml-2 text-[var(--text-tertiary)]">动作：{s.action}</span> : null}
              </li>
            ))}
          </DiffSection>
        ) : null}

        {diff.removed.length > 0 ? (
          <DiffSection label="移出持仓" tone="watch">
            {diff.removed.map((s) => (
              <li key={s.code}>
                <strong>{s.code}</strong> {s.name}
                {s.action ? <span className="ml-2 text-[var(--text-tertiary)]">原动作：{s.action}</span> : null}
              </li>
            ))}
          </DiffSection>
        ) : null}

        {diff.action_changes.length > 0 ? (
          <DiffSection label="动作变更" tone="risk">
            {diff.action_changes.map((c) => (
              <li key={`${c.code}-action`}>
                <strong>{c.code}</strong> {c.name}：{formatDiffValue(c.before)} → {formatDiffValue(c.after)}
              </li>
            ))}
          </DiffSection>
        ) : null}

        {diff.group_changes.length > 0 ? (
          <DiffSection label="分组迁移" tone="risk">
            {diff.group_changes.map((c) => (
              <li key={`${c.code}-group`}>
                <strong>{c.code}</strong> {c.name}：{formatDiffValue(c.before)} → {formatDiffValue(c.after)}
              </li>
            ))}
          </DiffSection>
        ) : null}

        {diff.boundary_changes.length > 0 ? (
          <DiffSection label="止损 / 支撑 / 阻力调整" tone="watch">
            {diff.boundary_changes.map((c) => (
              <li key={`${c.code}-${c.field}`}>
                <strong>{c.code}</strong> {c.name} {c.field}：{formatDiffValue(c.before)} → {formatDiffValue(c.after)}
              </li>
            ))}
          </DiffSection>
        ) : null}

        {diff.signal_changes.length > 0 ? (
          <DiffSection label="信号变化" tone="info">
            {diff.signal_changes.map((c) => (
              <li key={`${c.code}-signal`}>
                <strong>{c.code}</strong> {c.name}：{formatDiffValue(c.before)} → {formatDiffValue(c.after)}
              </li>
            ))}
          </DiffSection>
        ) : null}

        {diff.unchanged_count > 0 ? (
          <div className="text-[11px] text-[var(--text-tertiary)]">
            其余 {diff.unchanged_count} 只维持昨日状态。
          </div>
        ) : null}
      </div>
    </Panel>
  );
}

function DiffSection({
  label,
  tone,
  children,
}: {
  label: string;
  tone: "info" | "watch" | "risk";
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="mb-1 flex items-center gap-2">
        <Badge tone={tone}>{label}</Badge>
      </div>
      <ul className="ml-3 list-disc space-y-1 text-[12px] leading-5">{children}</ul>
    </div>
  );
}

export default function PortfolioPage() {
  const watchlist = useWatchlist();
  const data = watchlist.data;

  return (
    <main className="flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
      <div className="mx-auto max-w-7xl">
        <PageTitle
          eyebrow={data?.display_date || data?.generated_at?.slice(0, 10) || data?.trade_date || "Portfolio"}
          title={data?.topline?.verdict_title || data?.hero?.title || "持仓管理"}
          summary={data?.topline?.verdict_summary || data?.hero?.summary || "按优先处理、跟踪增强、继续观察分组管理当前自选股。"}
          icon={WalletCards}
          badge={data?.brief_is_live ? "总控同步" : "实时快照"}
          actions={
            <button
              type="button"
              className="focus-ring inline-flex items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)]"
              onClick={() => void watchlist.refetch()}
            >
              <RefreshCw size={14} className={watchlist.isFetching ? "animate-spin" : ""} />
              刷新
            </button>
          }
        />

        {watchlist.isError ? (
          <ErrorState message="持仓数据暂不可用" onRetry={() => void watchlist.refetch()} />
        ) : null}

        <section className="mb-7 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {watchlist.isLoading && !data
            ? Array.from({ length: 4 }).map((_, index) => <MetricSkeleton key={index} />)
            : (data?.summary_cards || []).slice(0, 4).map((card, index) => (
                <MetricCard key={`${card.label}-${index}`} {...card} tone={index === 1 ? "risk" : index === 2 ? "info" : "watch"} />
              ))}
        </section>

        <section className="mb-7 grid grid-cols-1 gap-4 xl:grid-cols-3">
          {watchlist.isLoading && !data
            ? Array.from({ length: 3 }).map((_, index) => (
                <div key={index} className="surface-card p-4">
                  <SkeletonBlock className="h-5 w-24" />
                  <SkeletonBlock className="mt-4 h-24 w-full" />
                  <SkeletonBlock className="mt-3 h-24 w-full" />
                </div>
              ))
            : (data?.groups || []).map((group) => (
                <Panel
                  key={group.key || group.title}
                  title={group.title}
                  eyebrow={group.subtitle}
                  action={<Badge tone={group.key === "priority" ? "risk" : group.key === "follow" ? "info" : "watch"}>{group.count || 0}</Badge>}
                  className="surface-card p-4"
                >
                  <div className="flex flex-col gap-2">
                    {group.cards?.length ? (
                      group.cards.map((stock) => <StockCard key={stock.code} stock={stock} />)
                    ) : (
                      <EmptyState>{group.empty || "当前没有股票。"}</EmptyState>
                    )}
                  </div>
                </Panel>
              ))}
        </section>

        <section className="mb-7">
          <DayOverDayDiffPanel diff={data?.day_over_day_diff} />
        </section>

        <section id="watchlist-manager" className="mb-7">
          <WatchlistManagerPanel />
        </section>

        <section className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <Panel title="总控焦点" eyebrow="Focus">
            <div className="surface-card p-4">
              <div className="mb-3 flex flex-wrap gap-2">
                {(data?.focus_tags || []).length ? (
                  data?.focus_tags?.map((item) => <Badge key={item} tone="info">{item}</Badge>)
                ) : (
                  <span className="text-[13px] text-[var(--text-tertiary)]">暂无额外持仓焦点。</span>
                )}
              </div>
              <div className="flex flex-col gap-2">
                {(data?.avoid_points || []).map((item) => (
                  <div key={item} className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
                    {item}
                  </div>
                ))}
              </div>
            </div>
          </Panel>

          <EvidencePanel page="watchlist" sources={data?.source_cards} title="来源校验" eyebrow="Freshness" />
        </section>
      </div>
    </main>
  );
}
