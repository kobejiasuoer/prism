import { Badge } from "@/components/badge";
import type { Tone } from "@/lib/types";

export function MiniFact({
  label,
  value,
  tone = "info",
}: {
  label: string;
  value: string;
  tone?: Tone | string;
}) {
  return (
    <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
      <div className="text-[11px] text-[var(--text-tertiary)]">{label}</div>
      <div className="mt-1 line-clamp-2 text-[12px] font-medium text-[var(--text-primary)]">
        <Badge tone={tone}>{value}</Badge>
      </div>
    </div>
  );
}
