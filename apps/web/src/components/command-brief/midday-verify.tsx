"use client";

import Link from "next/link";
import { Badge } from "@/components/badge";
import type { CommandBriefMiddayVerify, CommandBriefMiddayCard } from "@/lib/types";

function Card({ card, tone }: { card: CommandBriefMiddayCard; tone: string }) {
  return (
    <li className="rounded-md border border-[var(--border-subtle)] px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[12px] font-medium text-[var(--text-primary)]">{card.name}</span>
        <Badge tone={tone}>{card.code}</Badge>
      </div>
      <p className="mt-1 text-[12px] text-[var(--text-secondary)]">{card.reason || "—"}</p>
      {card.url ? <Link href={card.url} className="text-[12px] underline">打开</Link> : null}
    </li>
  );
}

export function MiddayVerify({ payload }: { payload: CommandBriefMiddayVerify }) {
  if (!payload.available) {
    return (
      <section className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-4">
        <div className="text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">Midday Verify</div>
        <p className="mt-2 text-[14px] text-[var(--text-primary)]">{payload.midday_status}</p>
      </section>
    );
  }
  return (
    <section className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-4" data-od-id="midday-verify">
      <header className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">Midday Verify</span>
        <span className="text-[12px] text-[var(--text-tertiary)]">{payload.verified_at}</span>
      </header>
      <div className="mt-2 grid gap-3 lg:grid-cols-3">
        <div>
          <div className="text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">早盘结论</div>
          <p className="mt-1 text-[12px] text-[var(--text-secondary)]">{payload.morning_takeaway}</p>
          <div className="mt-2 text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">午盘验证</div>
          <p className="mt-1 text-[12px] text-[var(--text-secondary)]">{payload.midday_status}</p>
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">新增 ({payload.fresh_candidates.length})</div>
          <ul className="mt-1 space-y-2">
            {payload.fresh_candidates.map((card, idx) => (
              <Card key={`fresh-${idx}`} card={card} tone="positive" />
            ))}
            {!payload.fresh_candidates.length ? <li className="text-[12px] text-[var(--text-tertiary)]">今日无新增。</li> : null}
          </ul>
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">降级 ({payload.downgraded.length})</div>
          <ul className="mt-1 space-y-2">
            {payload.downgraded.map((card, idx) => (
              <Card key={`down-${idx}`} card={card} tone="risk" />
            ))}
            {!payload.downgraded.length ? <li className="text-[12px] text-[var(--text-tertiary)]">今日无降级。</li> : null}
          </ul>
        </div>
      </div>
      <div className="mt-3 rounded-md border border-dashed border-[var(--border-subtle)] px-3 py-2">
        <div className="text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">明日延续条件</div>
        <p className="mt-1 text-[12px] text-[var(--text-secondary)]">{payload.next_day_condition}</p>
      </div>
    </section>
  );
}
