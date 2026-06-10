import type { MetricCardData } from "@/lib/types";
import { cn, toneColor } from "@/lib/utils";

export function MetricCard({
  label,
  value,
  detail,
  note,
  tone,
  className,
}: MetricCardData & { className?: string }) {
  const color = tone ? toneColor(tone) : undefined;

  return (
    <div className={cn("surface-card min-h-[116px] p-4", className)}>
      <div className="truncate text-[11px] font-medium uppercase text-[var(--text-tertiary)]">{label}</div>
      <div
        className="mt-2 min-w-0 break-words text-[clamp(20px,2.1vw,28px)] font-bold leading-tight"
        style={{ color: color ?? "var(--text-primary)" }}
      >
        {value}
      </div>
      <div className="mt-2 line-clamp-2 text-[11px] leading-4 text-[var(--text-tertiary)]">
        {detail || note || "-"}
      </div>
    </div>
  );
}

export function MetricSkeleton() {
  return (
    <div className="surface-card min-h-[116px] animate-pulse p-4">
      <div className="h-3 w-20 rounded bg-[var(--bg-elevated)]" />
      <div className="mt-4 h-7 w-14 rounded bg-[var(--bg-elevated)]" />
      <div className="mt-4 h-3 w-28 rounded bg-[var(--bg-elevated)]" />
    </div>
  );
}
