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
import { useAddWatchlistStock, useOpportunities, useTodayData, useUpdateTodayActionDecision } from "@/lib/hooks";
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
  if (text.includes("早盘进入")) {
    return "早盘进入";
  }
  if (text.includes("午盘新增")) {
    return "午盘新增";
  }
  if (text.includes("仍可跟踪") || text.includes("可升级")) {
    return "可升级";
  }
  if (text.includes("淘汰") || text.includes("剔除") || text.includes("降级")) {
    return "已淘汰";
  }
  return text;
}

function stockInstruction(stock: StockListCard) {
  if (stock.observation_instruction) {
    return stock.observation_instruction;
  }
  return [
    stock.name ? `${stock.name}：只观察，不追` : "只观察，不追",
    stock.upgrade_condition ? `升级：${stock.upgrade_condition}` : stock.setup_label ? `升级：${stock.setup_label}` : "",
    stock.invalid_condition ? `失效：${stock.invalid_condition}` : stock.foot ? `失效：${stock.foot}` : "",
  ]
    .filter(Boolean)
    .join("；")
    .replace(/。；/g, "；");
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
  const findCount = (keywords: string[]) =>
    groups
      .filter((group) => keywords.some((keyword) => group.title.includes(keyword) || displayGroupTitle(group.title).includes(keyword)))
      .reduce((sum, group) => sum + groupCount(group), 0);
  const watching = findCount(["继续观察"]);
  const midday = findCount(["午盘新增"]);
  const upgrade = findCount(["可升级", "仍可跟踪"]);
  const eliminated = findCount(["已淘汰", "剔除", "降级"]);
  return [
    { label: "必须复核", value: watching + midday + upgrade, detail: "今天需要看完的观察任务" },
    { label: "午盘新增", value: midday, detail: "午盘新进入观察视野" },
    { label: "可升级", value: upgrade, detail: "承接仍成立，等待阀门" },
    { label: "应剔除", value: eliminated, detail: "失效或降级的观察项" },
  ];
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

  return (
    <Panel title={displayGroupTitle(group?.title) || "观察工作台"} eyebrow="Workbench" action={<Badge tone="watch">{groupCount(group)} 只</Badge>}>
      {loading ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 5 }).map((_, index) => <SkeletonBlock key={index} className="h-20 w-full" />)}
        </div>
      ) : cards.length ? (
        <>
          <div className="hidden overflow-x-auto lg:block">
            <table className="w-full min-w-[1080px] text-left text-[12px]">
              <thead className="border-b border-[var(--border-subtle)] text-[11px] uppercase text-[var(--text-tertiary)]">
                <tr>
                  <th className="px-3 py-2 font-medium">股票 / 主题</th>
                  <th className="px-3 py-2 font-medium">当前阶段</th>
                  <th className="px-3 py-2 font-medium">观察指令</th>
                  <th className="px-3 py-2 font-medium">为什么入池</th>
                  <th className="px-3 py-2 font-medium">触发升级条件</th>
                  <th className="px-3 py-2 font-medium">失效条件</th>
                  <th className="px-3 py-2 font-medium">风险 / 优先级</th>
                  <th className="px-3 py-2 font-medium">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border-subtle)]">
                {cards.map((stock) => (
                  <tr key={`${group?.title}-${stock.code}`} className="align-top hover:bg-[var(--bg-secondary)]">
                    <td className="px-3 py-3">
                      <div className="font-medium text-[var(--text-primary)]">{stock.name || "未知股票"}</div>
                      <div className="mono mt-1 text-[11px] text-[var(--text-tertiary)]">{stock.code}</div>
                      {stock.theme ? <div className="mt-2 text-[11px] text-[var(--text-tertiary)]">{stock.theme}</div> : null}
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex max-w-[160px] flex-wrap gap-1.5">
                        <Badge tone={stock.tone}>{stock.status || stock.action || group?.title || "观察"}</Badge>
                        {persistenceLabel(stock) ? <Badge tone={persistenceTone(stock)}>{persistenceLabel(stock)}</Badge> : null}
                      </div>
                    </td>
                    <td className="max-w-[260px] px-3 py-3 leading-5 text-[var(--text-primary)]">{stockInstruction(stock)}</td>
                    <td className="max-w-[180px] px-3 py-3 leading-5 text-[var(--text-secondary)]">
                      {stock.reason || stock.detail || "等待更多确认"}
                    </td>
                    <td className="max-w-[180px] px-3 py-3 leading-5 text-[var(--text-secondary)]">
                      {stock.upgrade_condition || stock.setup_label || "等待触发条件"}
                    </td>
                    <td className="max-w-[180px] px-3 py-3 leading-5 text-[var(--text-secondary)]">
                      {stock.invalid_condition || stock.foot || stock.risk || "触发失效则剔除"}
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex max-w-[180px] flex-wrap gap-1.5">
                        {(stock.risk_tags?.length ? stock.risk_tags : [stock.foot || stock.risk].filter(Boolean)).slice(0, 3).map((item) => (
                          <Badge key={String(item)} tone="risk">{String(item)}</Badge>
                        ))}
                        {stock.priority_label ? <Badge tone="info">{stock.priority_label}</Badge> : null}
                        {persistenceLabel(stock) ? <Badge tone={persistenceTone(stock)}>{persistenceLabel(stock)}</Badge> : null}
                        {stock.score !== undefined ? <Badge tone="positive">{stock.score} 分</Badge> : null}
                        {stock.change_pct !== undefined ? <Badge tone="watch">涨幅 {formatChange(stock.change_pct)}</Badge> : null}
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
                    <Badge tone={stock.tone}>{stock.status || group?.title || "观察"}</Badge>
                    {persistenceLabel(stock) ? <Badge tone={persistenceTone(stock)}>{persistenceLabel(stock)}</Badge> : null}
                  </div>
                </div>
                <p className="text-[12px] leading-5 text-[var(--text-primary)]">{stockInstruction(stock)}</p>
                <div className="mt-3 grid grid-cols-1 gap-2 text-[12px] leading-5 text-[var(--text-secondary)]">
                  <div><span className="text-[var(--text-tertiary)]">入池：</span>{stock.reason || stock.detail || "等待更多确认"}</div>
                  <div><span className="text-[var(--text-tertiary)]">升级：</span>{stock.upgrade_condition || stock.setup_label || "等待触发条件"}</div>
                  <div><span className="text-[var(--text-tertiary)]">失效：</span>{stock.invalid_condition || stock.foot || stock.risk || "触发失效则剔除"}</div>
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
  const today = useTodayData();
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
