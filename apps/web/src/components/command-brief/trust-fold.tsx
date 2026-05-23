"use client";

import type { ReactNode } from "react";
import { Badge } from "@/components/badge";
import type { CommandBriefTrust } from "@/lib/types";

export function TrustFold({ trust, children }: { trust: CommandBriefTrust; children?: ReactNode }) {
  return (
    <details className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3" data-od-id="trust-fold">
      <summary className="flex cursor-pointer flex-wrap items-center gap-2">
        <span className="text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">Trust</span>
        <Badge tone={trust.readiness_mode === "live_ready" ? "positive" : trust.readiness_mode === "shadow_only" ? "warning" : "negative"}>
          {trust.readiness_mode}
        </Badge>
        <span className="text-[12px] text-[var(--text-secondary)]">数据源 {trust.source_summary}</span>
        <span className="text-[12px] text-[var(--text-secondary)]">质检 {trust.quality_summary}</span>
        {trust.warnings_count ? <span className="text-[12px] text-[var(--warning)]">告警 {trust.warnings_count}</span> : null}
        {trust.blockers_count ? <span className="text-[12px] text-[var(--negative)]">阻塞 {trust.blockers_count}</span> : null}
        {trust.auto_refresh_summary ? <span className="text-[12px] text-[var(--text-tertiary)]">{trust.auto_refresh_summary}</span> : null}
      </summary>
      <div className="mt-3 space-y-3">{children}</div>
    </details>
  );
}
