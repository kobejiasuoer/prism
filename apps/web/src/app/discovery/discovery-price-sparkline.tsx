import type { ExitTrackingRecord } from "@/lib/types";

/**
 * Compact close-price sparkline for an exited stock's post-exit trajectory.
 *
 * Draws the daily close line plus a dashed horizontal baseline at the exit
 * price, so a glance shows whether the stock drifted up (misjudged) or down
 * (true_exit) after leaving the shortlist. Hand-written SVG — no chart
 * library dependency. Scales responsively via viewBox.
 */
export function PriceSparkline({
  prices,
  exitPrice,
  width = 64,
  height = 24,
}: {
  prices?: ExitTrackingRecord["daily_prices"];
  exitPrice?: number | null;
  width?: number;
  height?: number;
}) {
  const closes = (prices || [])
    .map((p) => (typeof p?.close === "number" ? p.close : null))
    .filter((c): c is number => c !== null);

  if (closes.length < 2) {
    return <span className="mono text-[10px] text-[var(--text-tertiary)]">—</span>;
  }

  const all = exitPrice && exitPrice > 0 ? [...closes, exitPrice] : closes;
  const min = Math.min(...all);
  const max = Math.max(...all);
  const span = max - min || 1; // avoid divide-by-zero when flat

  const pad = 2;
  const innerW = width - pad * 2;
  const innerH = height - pad * 2;

  const xAt = (i: number) => pad + (i / (closes.length - 1)) * innerW;
  const yAt = (v: number) => pad + innerH - ((v - min) / span) * innerH;

  const linePoints = closes.map((c, i) => `${xAt(i).toFixed(1)},${yAt(c).toFixed(1)}`).join(" ");
  const up = closes[closes.length - 1] >= (exitPrice ?? closes[0]);
  const lineColor = up ? "var(--tone-positive)" : "var(--tone-risk)";

  // Baseline y for the exit-price reference line (if available and in range).
  const baselineY = exitPrice && exitPrice >= min && exitPrice <= max ? yAt(exitPrice) : null;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`退出后价格轨迹，${closes.length} 个交易日`}
      className="shrink-0"
    >
      {baselineY !== null ? (
        <line
          x1={pad}
          y1={baselineY}
          x2={width - pad}
          y2={baselineY}
          stroke="var(--text-tertiary)"
          strokeWidth={0.75}
          strokeDasharray="2 2"
        />
      ) : null}
      <polyline
        points={linePoints}
        fill="none"
        stroke={lineColor}
        strokeWidth={1.25}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}
