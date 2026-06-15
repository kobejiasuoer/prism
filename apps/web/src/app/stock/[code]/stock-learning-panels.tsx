"use client";

import { Badge } from "@/components/badge";
import { Panel, SkeletonBlock } from "@/components/data-card";
import { LearningMemoryPreview } from "@/components/learning-memory";
import { MetricCard } from "@/components/metric-card";
import type { StockLearningScorecard } from "@/lib/types";

export function StockLearningScorecardPanel({
  scorecard,
  loading,
  compact = false,
}: {
  scorecard?: StockLearningScorecard;
  loading?: boolean;
  compact?: boolean;
}) {
  if (loading && !scorecard) {
    return (
      <Panel title="只读学习摘要" eyebrow="Learning">
        <div className="surface-card p-4">
          <SkeletonBlock className="h-24 w-full" />
        </div>
      </Panel>
    );
  }
  if (!scorecard) {
    return null;
  }

  const metrics = scorecard.scorecards || [];
  const patterns = scorecard.failure_patterns || [];
  const memories = scorecard.learning_memories || [];

  return (
    <div className="flex flex-col gap-4">
      {memories.length ? (
        <Panel title="历史提醒" eyebrow="Learning">
          <LearningMemoryPreview memories={memories} limit={3} />
        </Panel>
      ) : null}
      <Panel
        title={compact ? "冻结页学习摘要" : "历史可信度"}
        eyebrow="Read-only Learning"
        action={
          <div className="flex flex-wrap gap-2">
            <Badge tone="watch">
              {scorecard.confidence_label || scorecard.stage}
            </Badge>
            <Badge tone={scorecard.feeds_execution ? "risk" : "info"}>
              {scorecard.feeds_execution ? "会影响执行" : "不喂执行"}
            </Badge>
          </div>
        }
      >
        <div className="surface-card p-4">
          <div className="mb-3">
            <h2 className="text-[15px] font-semibold text-[var(--text-primary)]">
              {scorecard.headline || "历史可信度只作学习参考"}
            </h2>
            <p className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
              {scorecard.reason ||
                "统计 Prism 自己的历史建议和 outcome，不作为胜率承诺。"}
            </p>
          </div>
          <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
            {metrics.slice(0, 4).map((card) => (
              <MetricCard
                key={card.label}
                label={card.label}
                value={card.value}
                detail={card.detail}
                tone={card.tone || "info"}
              />
            ))}
          </div>
          {patterns.length ? (
            <div className="mt-3 grid gap-2 lg:grid-cols-2">
              {patterns.slice(0, compact ? 2 : 4).map((item) => (
                <div
                  key={item.label}
                  className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2"
                >
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <span className="text-[12px] font-medium text-[var(--text-primary)]">
                      {item.label}
                    </span>
                    <Badge tone={item.tone || "watch"}>学习项</Badge>
                  </div>
                  <div className="text-[12px] leading-5 text-[var(--text-secondary)]">
                    {item.detail}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="mt-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[12px] text-[var(--text-tertiary)]">
              暂无突出失败模式；样本仍需继续积累。
            </div>
          )}
        </div>
      </Panel>
    </div>
  );
}
