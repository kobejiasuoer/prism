import { Badge } from "@/components/badge";
import type { StockListCard } from "@/lib/types";

const HEADLINE_TONE: Record<string, "positive" | "watch" | "risk" | "info" | "neutral"> = {
  可开仓: "positive",
  可加仓: "positive",
  等触发: "watch",
  只观察: "info",
  不可开仓: "risk",
};

function fmtPrice(value: number | null | undefined): string | null {
  if (value === null || value === undefined) return null;
  return Number(value).toFixed(2);
}

export function ActionCell({
  stock,
  valveOff = false,
}: {
  stock: StockListCard;
  valveOff?: boolean;
}) {
  const d = stock.action_directive;
  if (!d) {
    return <span className="text-[var(--text-tertiary)]">—</span>;
  }
  // When the offense valve is shut, every candidate collapses to '只观察'
  // regardless of its own gate, so the page stops pretending there is a
  // buyable gradient. The backend emits the valve-open directive; the
  // frontend overrides the headline here so the payload stays cache-stable.
  const headline = valveOff ? "只观察" : d.headline;
  const blocker = valveOff ? (d.blocker || "进攻阀门关闭，今日不开新仓") : d.blocker;
  const tone = HEADLINE_TONE[headline] ?? "neutral";
  const trigger = valveOff ? null : fmtPrice(d.trigger_price);
  const invalidate = valveOff ? null : fmtPrice(d.invalidate_price);
  return (
    <div className="flex flex-col gap-1">
      <Badge tone={tone}>{headline}</Badge>
      {trigger || invalidate ? (
        <div className="mono text-[11px] leading-4 text-[var(--text-secondary)]">
          {trigger ? <div>触发 {trigger}</div> : null}
          {invalidate ? <div className="text-[var(--text-tertiary)]">失效 {invalidate}</div> : null}
        </div>
      ) : null}
      {blocker ? (
        <div className="prism-clamp-2 text-[11px] leading-4 text-[var(--text-tertiary)]">
          {blocker}
        </div>
      ) : null}
    </div>
  );
}
