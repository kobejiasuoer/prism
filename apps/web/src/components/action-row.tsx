"use client";

import { Check, ChevronRight, LoaderCircle } from "lucide-react";
import Link from "next/link";

import { Badge } from "./badge";
import type { DecisionValue, TodayActionItem } from "@/lib/types";
import { asText, cn, stockCodeFromTitle, stockNameFromTitle, toneColor } from "@/lib/utils";

export function ActionRow({
  item,
  disabled,
  onDecision,
}: {
  item: TodayActionItem;
  disabled?: boolean;
  onDecision: (key: string, decision: DecisionValue) => void;
}) {
  const checked = item.decision?.value === "done";
  const color = toneColor(item.tone || item.decision?.tone);
  const code = stockCodeFromTitle(item.title);
  const name = stockNameFromTitle(item.title);
  const href = code ? `/stock/${code}` : item.url || "#";
  const nextDecision: DecisionValue = checked ? "pending" : "done";

  return (
    <div className="grid grid-cols-[auto_3px_minmax(0,1fr)_auto_auto] items-center gap-3 border-b border-[var(--border-subtle)] py-3 last:border-b-0">
      <button
        type="button"
        aria-label={checked ? "标记为待确认" : "标记为已处理"}
        className={cn(
          "focus-ring flex h-5 w-5 items-center justify-center rounded-[6px] border transition-colors",
          checked
            ? "border-[var(--positive)] bg-[var(--positive)] text-white"
            : "border-[var(--border-strong)] bg-transparent text-transparent hover:border-[var(--text-tertiary)]",
        )}
        disabled={disabled}
        onClick={() => onDecision(item.key, nextDecision)}
      >
        {disabled ? <LoaderCircle size={13} className="animate-spin text-white" /> : <Check size={13} />}
      </button>

      <div className="h-9 rounded-full" style={{ backgroundColor: color }} />

      <Link href={href} className="min-w-0">
        <div className="flex min-w-0 items-center gap-2">
          <span
            className={cn(
              "truncate text-sm font-medium",
              checked ? "text-[var(--text-tertiary)] line-through" : "text-[var(--text-primary)]",
            )}
          >
            {name}
          </span>
          {code ? <span className="mono shrink-0 text-[11px] text-[var(--text-tertiary)]">{code}</span> : null}
        </div>
        <div className="mt-0.5 line-clamp-1 text-[12px] text-[var(--text-tertiary)]">
          {asText(item.detail || item.foot || item.status)}
        </div>
      </Link>

      <Badge tone={item.tone} className="hidden max-w-[112px] sm:inline-flex">
        {item.status || item.group_title || item.decision?.label}
      </Badge>

      <Link
        href={href}
        aria-label="打开详情"
        className="focus-ring inline-flex h-8 w-8 items-center justify-center rounded-md text-[var(--text-tertiary)] hover:bg-[var(--bg-secondary)] hover:text-[var(--text-primary)]"
      >
        <ChevronRight size={16} />
      </Link>
    </div>
  );
}

export function ActionRowSkeleton() {
  return (
    <div className="grid grid-cols-[auto_3px_minmax(0,1fr)_auto] items-center gap-3 border-b border-[var(--border-subtle)] py-3 last:border-b-0">
      <div className="h-5 w-5 rounded-[6px] bg-[var(--bg-elevated)]" />
      <div className="h-9 rounded-full bg-[var(--bg-elevated)]" />
      <div>
        <div className="h-4 w-40 rounded bg-[var(--bg-elevated)]" />
        <div className="mt-2 h-3 w-64 max-w-full rounded bg-[var(--bg-elevated)]" />
      </div>
      <div className="h-8 w-8 rounded-md bg-[var(--bg-elevated)]" />
    </div>
  );
}
