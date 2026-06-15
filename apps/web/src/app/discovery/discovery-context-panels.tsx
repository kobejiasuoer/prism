"use client";

import Link from "next/link";

import { Badge } from "@/components/badge";
import { EmptyState, Panel } from "@/components/data-card";
import { LearningMemoryPreview } from "@/components/learning-memory";
import type { BasicCard, CardGroup, OpportunitiesData, StockListCard } from "@/lib/types";
import {
  cardHref,
  displayGroupTitle,
  groupCount,
  persistenceLabel,
  persistenceTone,
} from "./discovery-display-utils";

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

export function DiscoveryContextPanels({ data }: { data?: OpportunitiesData }) {
  const learningMemories = data?.learning_memories || [];

  return (
    <>
      {learningMemories.length ? (
        <Panel title="历史提醒" eyebrow="Pattern Memory">
          <LearningMemoryPreview memories={learningMemories} limit={3} />
        </Panel>
      ) : null}

      <LifecycleTracker data={data} />
      <ThemeRadar cards={data?.theme_cards} />
    </>
  );
}
