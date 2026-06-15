"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { Badge } from "@/components/badge";
import type {
  CommandBriefMode,
  CommandBriefPermit,
  CommandBriefPositionCap,
  CommandBriefFirstAction,
} from "@/lib/types";

const MODE_TONE: Record<string, string> = {
  defense: "negative",
  observe: "warning",
  probe: "info",
  offense: "positive",
};

function PermitChip({ permit, label }: { permit: CommandBriefPermit; label: string }) {
  return (
    <div className="rounded-md border border-[var(--border-subtle)] px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">{label}</div>
      <div className="mt-1 flex items-center gap-2">
        <Badge tone={permit.tone}>{permit.label}</Badge>
        <span className="text-[12px] font-mono text-[var(--text-secondary)]">{permit.value}</span>
      </div>
      <p className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">{permit.why}</p>
    </div>
  );
}

export function CommandHeader({
  mode,
  permits,
  positionCap,
  firstAction,
  tradeDate,
}: {
  mode: CommandBriefMode;
  permits: { data: CommandBriefPermit; market: CommandBriefPermit; opportunity: CommandBriefPermit };
  positionCap: CommandBriefPositionCap;
  firstAction: CommandBriefFirstAction;
  tradeDate: string;
}) {
  return (
    <section className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-4" data-od-id="command-header">
      <header className="flex flex-wrap items-center gap-2">
        <Badge tone={MODE_TONE[mode.value] || "info"}>今日模式 · {mode.label}</Badge>
        <span className="text-[12px] text-[var(--text-tertiary)]">交易日 {tradeDate}</span>
      </header>
      <h2 className="mt-2 text-[18px] font-semibold text-[var(--text-primary)]">{mode.summary}</h2>

      <div className="mt-3 grid gap-2 sm:grid-cols-3">
        <PermitChip permit={permits.data} label="数据许可" />
        <PermitChip permit={permits.market} label="市场许可" />
        <PermitChip permit={permits.opportunity} label="机会许可" />
      </div>

      <div className="mt-3 flex flex-wrap items-baseline gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2">
        <span className="text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">新仓上限</span>
        <strong className="font-mono text-[16px] text-[var(--text-primary)]">{positionCap.value}</strong>
        <span className="text-[12px] text-[var(--text-secondary)]">{positionCap.note}</span>
      </div>

      <Link
        href={firstAction.url || "#action-lanes"}
        className="mt-3 flex items-center justify-between rounded-md border border-[var(--border-subtle)] bg-[var(--bg-tertiary)] px-3 py-2 hover:bg-[var(--bg-tertiary-hover)]"
        data-od-id="first-action"
      >
        <div className="min-w-0">
          <div className="text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">第一动作</div>
          <div className="mt-1 text-[14px] font-medium text-[var(--text-primary)]">{firstAction.title}</div>
          <p className="mt-1 text-[12px] text-[var(--text-secondary)]">{firstAction.reason}</p>
        </div>
        <ChevronRight size={16} className="shrink-0 text-[var(--text-tertiary)]" />
      </Link>
    </section>
  );
}
