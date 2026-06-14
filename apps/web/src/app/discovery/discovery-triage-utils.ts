import type { CardGroup, StockListCard } from "@/lib/types";

export type TriageActionState = "focus" | "on_trigger" | "watch" | "drop";
export type TriageGateState = "open" | "capped" | "closed";
export type ValveStatus = "on" | "limited" | "off";

// Funnel layers -- the primary grouping axis (spec S6).
export type FunnelLayer = "focus" | "on_trigger" | "watch" | "drop";

export const FUNNEL_LAYER_LABELS: Record<FunnelLayer, string> = {
  focus: "值得专注",
  on_trigger: "等触发",
  watch: "只观察",
  drop: "丢弃",
};

export function triageActionState(stock: StockListCard): TriageActionState {
  return stock.triage_action_state ?? "watch";
}

export function triageGateState(stock: StockListCard): TriageGateState {
  return stock.triage_gate_state ?? "open";
}

export function triageGateBlocker(stock: StockListCard): string | null {
  return stock.triage_gate_blocker ?? null;
}

export function triageLegacy(stock: StockListCard): boolean {
  return Boolean(stock.triage_legacy);
}

export function funnelLayer(stock: StockListCard): FunnelLayer {
  return triageActionState(stock);
}

export interface FunnelBucket {
  layer: FunnelLayer;
  cards: StockListCard[];
}

export function bucketByFunnel(groups: CardGroup<StockListCard>[]): FunnelBucket[] {
  const order: FunnelLayer[] = ["focus", "on_trigger", "watch", "drop"];
  const buckets: Record<FunnelLayer, StockListCard[]> = {
    focus: [],
    on_trigger: [],
    watch: [],
    drop: [],
  };
  for (const group of groups) {
    for (const card of group.cards ?? []) {
      buckets[funnelLayer(card)].push(card);
    }
  }
  return order.map((layer) => ({ layer, cards: buckets[layer] }));
}

// Valve light copy (spec S7). Status comes straight from the backend payload.
export function valveLabel(status: ValveStatus | undefined): string {
  if (status === "on") return "开";
  if (status === "limited") return "半开";
  return "关闭";
}

export function valveTone(status: ValveStatus | undefined): string {
  if (status === "on") return "positive";
  if (status === "limited") return "watch";
  return "risk";
}
