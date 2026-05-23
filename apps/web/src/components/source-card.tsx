import { Circle } from "lucide-react";

import type { SourceCardData } from "@/lib/types";

const STALE_REASON_COPY: Record<string, string> = {
  missing_source: "缺来源",
  unparseable_timestamp: "时间不可解析",
  lifecycle_snapshot_expired: "回放过期",
  research_review_expired: "研究过期",
};

function sourceTone(source: SourceCardData) {
  if (source.stale || source.value === "-" || source.available === false) {
    return "var(--warning)";
  }
  return "var(--positive)";
}

export function SourceCard({ source }: { source: SourceCardData }) {
  const color = sourceTone(source);
  const reasonText = source.stale_reasons?.map((reason) => STALE_REASON_COPY[reason] || reason).join(" / ");
  const detail = source.stale_reasons?.length
    ? `${source.detail || ""}${source.detail ? " · " : ""}${reasonText}`
    : source.detail;

  return (
    <div className="flex items-center gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
      <Circle size={7} fill={color} style={{ color }} className="shrink-0" />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[12px] text-[var(--text-secondary)]">{source.label}</span>
        {detail ? <span className="block truncate text-[10px] text-[var(--text-tertiary)]">{detail}</span> : null}
      </span>
      <span className="mono shrink-0 truncate text-[11px] text-[var(--text-tertiary)]">
        {source.age_label || source.value || "-"}
      </span>
    </div>
  );
}
