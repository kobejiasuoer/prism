"use client";

import { AlertTriangle, CheckCircle2, Eye, ShieldAlert } from "lucide-react";

import type { TrustLevel } from "@/lib/types";
import { cn, toneColor } from "@/lib/utils";

const LEVEL_ICON = {
  trusted: CheckCircle2,
  observe_only: Eye,
  unreliable: ShieldAlert,
} as const;

export function trustLevelIcon(level: string) {
  if (
    level === "trusted" ||
    level === "observe_only" ||
    level === "unreliable"
  ) {
    return LEVEL_ICON[level];
  }
  return AlertTriangle;
}

export function trustLevelTone(trust?: TrustLevel | null): string {
  return trust?.tone || "warning";
}

export function TrustCompactBadge({
  trust,
  className,
}: {
  trust?: TrustLevel | null;
  className?: string;
}) {
  if (!trust) {
    return null;
  }

  const Icon = trustLevelIcon(trust.level);
  const color = toneColor(trustLevelTone(trust));

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium",
        className,
      )}
      style={{
        color,
        backgroundColor: `color-mix(in srgb, ${color} 10%, transparent)`,
        borderColor: `color-mix(in srgb, ${color} 22%, transparent)`,
      }}
      title={trust.headline}
    >
      <Icon size={11} aria-hidden="true" />
      <span className="truncate">{trust.label}</span>
    </span>
  );
}
