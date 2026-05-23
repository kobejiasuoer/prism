import { Lightbulb } from "lucide-react";

import { Badge } from "./badge";
import type { ReviewLearningMemory } from "@/lib/types";
import { cn } from "@/lib/utils";

export function LearningMemoryPreview({
  memories,
  limit = 1,
  compact = false,
}: {
  memories?: ReviewLearningMemory[];
  limit?: number;
  compact?: boolean;
}) {
  const visible = (memories || []).filter((item) => item?.summary || item?.learning_hint || item?.title).slice(0, limit);
  if (!visible.length) {
    return null;
  }

  return (
    <div className={cn("flex flex-col", compact ? "gap-1.5" : "gap-2")}>
      {visible.map((memory, index) => {
        const summary = memory.summary || memory.learning_hint || "这类样本有历史复盘提醒。";
        const title = memory.title || memory.primary_cause_label || "历史提醒";
        const sampleCopy = memory.sample_count ? `${memory.sample_count} 样本` : memory.evidence_strength_label;

        return (
          <div
            key={memory.key || `${title}-${index}`}
            className={cn(
              "rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)]",
              compact ? "px-2.5 py-2" : "p-3",
            )}
          >
            <div className="mb-1.5 flex min-w-0 items-center gap-2">
              <Lightbulb size={13} className="shrink-0 text-[var(--tone-watch)]" />
              <span className="truncate text-[11px] font-medium text-[var(--text-tertiary)]">
                {memory.scope_label || "Pattern Memory"}
              </span>
              <div className="ml-auto flex shrink-0 items-center gap-1">
                {memory.primary_cause_label ? <Badge tone={memory.tone}>{memory.primary_cause_label}</Badge> : null}
                {sampleCopy ? <Badge tone="info">{sampleCopy}</Badge> : null}
              </div>
            </div>
            <div className={cn("font-medium text-[var(--text-primary)]", compact ? "line-clamp-1 text-[12px]" : "text-sm")}>
              {title}
            </div>
            <p className={cn("mt-1 text-[12px] leading-5 text-[var(--text-secondary)]", compact ? "line-clamp-2" : "line-clamp-3")}>
              {summary}
            </p>
            {memory.secondary_cause_labels?.length ? (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {memory.secondary_cause_labels.slice(0, compact ? 2 : 3).map((label) => (
                  <Badge key={label} tone="watch">
                    {label}
                  </Badge>
                ))}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
