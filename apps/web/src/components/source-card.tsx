import { Circle } from "lucide-react";

import type { SourceCardData } from "@/lib/types";

function sourceTone(source: SourceCardData) {
  if (source.stale || source.value === "-" || source.available === false) {
    return "var(--warning)";
  }
  return "var(--positive)";
}

export function SourceCard({ source }: { source: SourceCardData }) {
  const color = sourceTone(source);

  return (
    <div className="flex items-center gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
      <Circle size={7} fill={color} style={{ color }} className="shrink-0" />
      <span className="min-w-0 flex-1 truncate text-[12px] text-[var(--text-secondary)]">{source.label}</span>
      <span className="mono shrink-0 truncate text-[11px] text-[var(--text-tertiary)]">
        {source.age_label || source.value || "-"}
      </span>
    </div>
  );
}
