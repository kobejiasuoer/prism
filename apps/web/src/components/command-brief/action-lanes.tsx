"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { Badge } from "@/components/badge";
import type { CommandBriefLane, CommandBriefLaneItem, CommandBriefForbidItem } from "@/lib/types";

function isLaneItem(item: CommandBriefLaneItem | CommandBriefForbidItem): item is CommandBriefLaneItem {
  return "action_type" in item;
}

function ActionLine({ item }: { item: CommandBriefLaneItem | CommandBriefForbidItem }) {
  if (!isLaneItem(item)) {
    return (
      <li className="rounded-md border border-[var(--border-subtle)] px-3 py-2">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[12px] font-medium text-[var(--text-primary)]">{item.title}</span>
          <Badge tone={item.tone}>禁止</Badge>
        </div>
        <p className="mt-1 text-[12px] text-[var(--text-secondary)]">{item.reason}</p>
      </li>
    );
  }
  return (
    <li className="rounded-md border border-[var(--border-subtle)] px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <span className="text-[12px] font-medium text-[var(--text-primary)]">{item.name || "-"}</span>
          {item.code ? <em className="ml-2 font-mono text-[11px] text-[var(--text-tertiary)] not-italic">{item.code}</em> : null}
        </div>
        <Badge tone={item.tone}>{item.action_type}</Badge>
      </div>
      <p className="mt-1 text-[12px] text-[var(--text-secondary)]">{item.reason || "—"}</p>
      <div className="mt-1 grid gap-1 text-[11px] text-[var(--text-tertiary)] sm:grid-cols-2">
        <span>触发：{item.trigger}</span>
        <span>失效：{item.invalidate_when}</span>
      </div>
      {item.url ? (
        <Link href={item.url} className="mt-2 inline-flex items-center gap-1 text-[12px] underline">
          打开 {item.code || "详情"}
          <ChevronRight size={12} />
        </Link>
      ) : null}
    </li>
  );
}

export function ActionLanes({ lanes }: { lanes: CommandBriefLane[] }) {
  return (
    <section
      id="action-lanes"
      className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-4"
      data-od-id="action-lanes"
    >
      <header>
        <div className="text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">Action Board</div>
        <h2 className="mt-1 text-[16px] font-semibold text-[var(--text-primary)]">今天的动作四件事</h2>
      </header>
      <div className="mt-3 grid gap-3 lg:grid-cols-4">
        {lanes.map((lane) => (
          <div key={lane.key} className="rounded-md border border-[var(--border-subtle)] p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[12px] font-semibold text-[var(--text-primary)]">{lane.title}</span>
              <Badge tone={lane.tone}>{lane.items.length}</Badge>
            </div>
            <p className="mt-1 text-[11px] text-[var(--text-tertiary)]">{lane.subtitle}</p>
            {lane.items.length ? (
              <ul className="mt-2 space-y-2">
                {lane.items.map((item, idx) => (
                  <ActionLine key={`${lane.key}-${idx}`} item={item} />
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-[12px] text-[var(--text-tertiary)]">今天此项为空。</p>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
