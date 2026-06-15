"use client";

import { Badge } from "@/components/badge";
import { DataCard, EmptyState, Panel } from "@/components/data-card";
import { MetricCard } from "@/components/metric-card";
import type { StockDetailData } from "@/lib/types";

type StockSecondaryTab = "持仓" | "发现";

export type StockSecondaryTabsProps = {
  activeTab: StockSecondaryTab;
  detail: StockDetailData;
};

function triggerCard(
  trigger: NonNullable<StockDetailData["triggers"]>[number],
  index: number,
) {
  const condition = trigger.condition || trigger.value || trigger.detail || "";
  const action = trigger.action || "";
  return {
    title: trigger.name || trigger.label || `触发 ${index + 1}`,
    detail: [condition, action].filter(Boolean).join(" / "),
    tone: "watch",
  };
}

function HoldingsTab({ detail }: { detail: StockDetailData }) {
  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
      <Panel title="持仓指标" eyebrow="Holdings">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {[...(detail.meta_cards || []), ...(detail.level_cards || [])]
            .slice(0, 8)
            .map((card, index) => (
              <MetricCard
                key={`${card.label}-${index}`}
                {...card}
                tone={index >= 4 ? "risk" : "info"}
              />
            ))}
          {!detail.meta_cards?.length && !detail.level_cards?.length ? (
            <EmptyState>暂无持仓指标。</EmptyState>
          ) : null}
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
          {!detail.triggers?.length ? (
            <EmptyState>暂无盘中触发条件。</EmptyState>
          ) : null}
        </div>
      </Panel>
    </div>
  );
}

function DiscoveryTab({ detail }: { detail: StockDetailData }) {
  const metricCards = [
    ...(detail.metric_cards || []),
    ...(detail.capital_cards || []),
    ...(detail.meta_cards || []),
    ...(detail.level_cards || []),
  ];

  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
      <Panel title="发现指标" eyebrow="Discovery">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {metricCards.slice(0, 8).map((card, index) => (
            <MetricCard
              key={`${card.label}-${index}`}
              {...card}
              tone={index === 0 ? detail.tone || "watch" : "info"}
            />
          ))}
          {!metricCards.length ? <EmptyState>暂无发现指标。</EmptyState> : null}
        </div>
      </Panel>

      <Panel title="洞察标签" eyebrow="Insights">
        <div className="flex flex-col gap-3">
          {(detail.insight_groups || []).map((group) => (
            <div key={group.title} className="surface-card p-4">
              <div className="mb-2 text-sm font-medium text-[var(--text-primary)]">
                {group.title}
              </div>
              <div className="flex flex-wrap gap-2">
                {group.items?.length ? (
                  group.items.map((item) => (
                    <Badge key={item} tone="watch">
                      {item}
                    </Badge>
                  ))
                ) : (
                  <span className="text-[12px] text-[var(--text-tertiary)]">
                    {group.empty || "暂无"}
                  </span>
                )}
              </div>
            </div>
          ))}
          {!detail.insight_groups?.length ? (
            <EmptyState>暂无洞察标签。</EmptyState>
          ) : null}
        </div>
      </Panel>
    </div>
  );
}

export function StockSecondaryTabs({
  activeTab,
  detail,
}: StockSecondaryTabsProps) {
  if (activeTab === "持仓") {
    return <HoldingsTab detail={detail} />;
  }

  return <DiscoveryTab detail={detail} />;
}
