"use client";

import { AlertTriangle, CheckCircle2, Eye, ShieldAlert } from "lucide-react";
import Link from "next/link";

import type { TrustLevel } from "@/lib/types";
import { cn, toneColor } from "@/lib/utils";

const LEVEL_ICON = {
  trusted: CheckCircle2,
  observe_only: Eye,
  unreliable: ShieldAlert,
} as const;

function levelIcon(level: string) {
  if (level === "trusted" || level === "observe_only" || level === "unreliable") {
    return LEVEL_ICON[level];
  }
  return AlertTriangle;
}

function levelTone(trust?: TrustLevel | null): string {
  return trust?.tone || "warning";
}

export function TrustBanner({
  trust,
  recoveryHref = "/settings#recovery",
  className,
  compact,
}: {
  trust?: TrustLevel | null;
  recoveryHref?: string;
  className?: string;
  compact?: boolean;
}) {
  if (!trust) {
    return null;
  }
  const Icon = levelIcon(trust.level);
  const color = toneColor(levelTone(trust));
  const showCta = trust.level !== "trusted" && Boolean(trust.next_step);

  if (compact) {
    return (
      <span
        className={cn("inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium", className)}
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

  return (
    <section
      className={cn("surface-card flex flex-col gap-3 p-4 lg:flex-row lg:items-start lg:justify-between", className)}
      style={{
        borderColor: `color-mix(in srgb, ${color} 28%, transparent)`,
        backgroundColor: `color-mix(in srgb, ${color} 6%, transparent)`,
      }}
      role="status"
      aria-live="polite"
      data-trust-level={trust.level}
    >
      <div className="flex min-w-0 items-start gap-3">
        <span
          className="mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full"
          style={{ backgroundColor: `color-mix(in srgb, ${color} 16%, transparent)`, color }}
        >
          <Icon size={15} aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className="inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium"
              style={{
                color,
                backgroundColor: `color-mix(in srgb, ${color} 12%, transparent)`,
                borderColor: `color-mix(in srgb, ${color} 24%, transparent)`,
              }}
            >
              今日可信度：{trust.label}
            </span>
            {trust.can_trade_live ? (
              <span className="text-[11px] text-[var(--text-tertiary)]">真钱执行：可</span>
            ) : (
              <span className="text-[11px] text-[var(--text-tertiary)]">真钱执行：暂不可</span>
            )}
          </div>
          <h2 className="mt-1 text-[14px] font-semibold leading-5 text-[var(--text-primary)]">
            {trust.headline}
          </h2>
          {trust.blocking_reasons && trust.blocking_reasons.length > 0 ? (
            <ul className="mt-2 space-y-1 text-[12px] leading-5 text-[var(--text-secondary)]">
              {trust.blocking_reasons.slice(0, 3).map((reason, idx) => (
                <li key={`${idx}-${reason.slice(0, 12)}`} className="flex gap-2">
                  <span className="text-[var(--text-tertiary)]">·</span>
                  <span className="min-w-0 flex-1">{reason}</span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>
      {showCta ? (
        <Link
          href={recoveryHref}
          className="focus-ring inline-flex shrink-0 items-center justify-center rounded-md border border-[var(--border-strong)] bg-[var(--bg-secondary)] px-3 py-2 text-[12px] font-medium text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
        >
          去恢复 · {trust.next_step_label || "刷新数据"}
        </Link>
      ) : null}
    </section>
  );
}
