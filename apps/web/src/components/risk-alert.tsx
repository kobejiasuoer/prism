import { AlertTriangle } from "lucide-react";

import { Badge } from "./badge";
import type { RiskRow } from "@/lib/types";
import { cn, toneColor } from "@/lib/utils";

export function RiskAlert({ row, className }: { row: RiskRow; className?: string }) {
  const tone = row.tone || "warning";
  const color = toneColor(tone);

  return (
    <div
      className={cn("flex items-start gap-3 rounded-md border px-3.5 py-3", className)}
      style={{
        backgroundColor: `color-mix(in srgb, ${color} 8%, transparent)`,
        borderColor: `color-mix(in srgb, ${color} 20%, transparent)`,
      }}
    >
      <AlertTriangle size={16} className="mt-0.5 shrink-0" style={{ color }} />
      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="truncate text-[13px] font-medium text-[var(--text-primary)]">{row.title}</span>
          {row.action ? <Badge tone={tone}>{row.action}</Badge> : null}
        </div>
        <div className="mt-1 line-clamp-2 text-[12px] leading-5 text-[var(--text-secondary)]">
          {row.reason || row.trigger || row.risk || "继续复核链路状态。"}
        </div>
      </div>
    </div>
  );
}
