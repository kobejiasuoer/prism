import Link from "next/link";

import { Badge } from "./badge";
import { LearningMemoryPreview } from "./learning-memory";
import type { StockListCard } from "@/lib/types";
import { asText, toneColor } from "@/lib/utils";

export function StockCard({ stock }: { stock: StockListCard }) {
  const color = toneColor(stock.tone);
  const href = stock.detail_url || (stock.code ? `/stock/${stock.code}` : "#");
  const instruction =
    stock.observation_instruction ||
    [
      stock.name ? `${stock.name}：只观察，不追。` : "只观察，不追。",
      stock.upgrade_condition ? `升级：${stock.upgrade_condition}` : "",
      stock.invalid_condition ? `失效：${stock.invalid_condition}` : "",
    ]
      .filter(Boolean)
      .join("；");

  return (
    <Link
      href={href}
      className="focus-ring grid grid-cols-[3px_minmax(0,1fr)_auto] gap-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3 hover:border-[var(--border-default)]"
    >
      <div className="rounded-full" style={{ backgroundColor: color }} />
      <div className="min-w-0">
        <div className="flex min-w-0 items-center gap-2">
          <span className="truncate text-sm font-medium text-[var(--text-primary)]">{asText(stock.name, "未知股票")}</span>
          <span className="mono shrink-0 text-[11px] text-[var(--text-tertiary)]">{stock.code}</span>
        </div>
        <div className="mt-1 line-clamp-2 text-[12px] leading-5 text-[var(--text-secondary)]">
          {stock.reason || stock.detail || stock.risk || stock.foot || stock.status_line || "等待更多确认"}
        </div>
        <div className="mt-2 rounded-md border border-[color-mix(in_srgb,var(--tone-watch)_22%,transparent)] bg-[color-mix(in_srgb,var(--tone-watch)_7%,transparent)] px-2.5 py-2 text-[12px] leading-5 text-[var(--text-primary)]">
          {instruction}
        </div>
        {stock.learning_memories?.length ? (
          <div className="mt-2">
            <LearningMemoryPreview memories={stock.learning_memories} compact />
          </div>
        ) : null}
        <div className="mt-2 flex flex-wrap gap-1.5">
          {stock.position ? <Badge tone="info">{stock.position}</Badge> : null}
          {stock.setup_label ? <Badge tone="watch">{stock.setup_label}</Badge> : null}
          {stock.score !== undefined ? <Badge tone="positive">{stock.score} 分</Badge> : null}
          {stock.stop_loss !== undefined ? <Badge tone="risk">止损 {String(stock.stop_loss)}</Badge> : null}
        </div>
      </div>
      <div className="flex min-w-[72px] flex-col items-end gap-2">
        <Badge tone={stock.tone}>{stock.action || stock.status || "查看"}</Badge>
        {stock.change_pct !== undefined ? (
          <span className="mono text-[11px]" style={{ color }}>
            {String(stock.change_pct)}
          </span>
        ) : null}
      </div>
    </Link>
  );
}
