"use client";

import { Badge } from "@/components/badge";
import type { CommandBriefJudgement } from "@/lib/types";

export function JudgementChain({ items }: { items: CommandBriefJudgement[] }) {
  return (
    <section
      id="judgement-chain"
      className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-4"
      data-od-id="judgement-chain"
    >
      <header>
        <div className="text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">Judgement Chain</div>
        <h2 className="mt-1 text-[16px] font-semibold text-[var(--text-primary)]">今日判断分四件事</h2>
      </header>
      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {items.map((item) => (
          <div key={item.dim} className="rounded-md border border-[var(--border-subtle)] p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[12px] font-medium text-[var(--text-primary)]">{item.title}</span>
              <Badge tone={item.tone}>{item.verdict}</Badge>
            </div>
            <ul className="mt-2 space-y-0.5 text-[11px] text-[var(--text-tertiary)]">
              {item.evidence.slice(0, 3).map((line, idx) => (
                <li key={`${item.dim}-evi-${idx}`}>· {line}</li>
              ))}
            </ul>
            <p className="mt-2 text-[12px] leading-5 text-[var(--text-secondary)]">{item.impact}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
