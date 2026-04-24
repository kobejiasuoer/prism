import Link from "next/link";

import { Badge } from "./badge";
import type { StockListCard } from "@/lib/types";
import { asText, toneColor } from "@/lib/utils";

export function StockCard({ stock }: { stock: StockListCard }) {
  const color = toneColor(stock.tone);
  const href = stock.code ? `/stock/${stock.code}` : stock.detail_url || "#";

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
