import type { CardGroup, StockListCard } from "@/lib/types";

export function groupCount(group?: CardGroup<StockListCard>) {
  return Number(group?.count ?? group?.cards?.length ?? 0);
}

export function groupHasDeferredCards(group?: CardGroup<StockListCard>) {
  return Boolean(group?.deferred_cards && groupCount(group) > 0);
}

export function cardHref(stock: StockListCard) {
  return stock.detail_url || (stock.code ? `/stock/${stock.code}` : "#");
}

export function displayGroupTitle(title?: string) {
  const text = title || "观察阶段";
  if (text.includes("结构验证") || text.includes("条件试错")) {
    return "结构验证/条件试错";
  }
  if (text.includes("早盘进入")) {
    return "早盘进入";
  }
  if (text.includes("午盘新增")) {
    return "午盘新增";
  }
  if (text.includes("延续升级")) {
    return "结构改善";
  }
  if (
    text.includes("仍可跟踪") ||
    text.includes("可升级") ||
    text.includes("待升级") ||
    text.includes("升级")
  ) {
    return "结构验证/条件试错";
  }
  if (
    text.includes("淘汰") ||
    text.includes("剔除") ||
    text.includes("降级") ||
    text.includes("退出")
  ) {
    return "已淘汰";
  }
  return text;
}

export function persistenceTone(stock: StockListCard) {
  const text = `${stock.persistence_label || ""} ${stock.priority_label || ""} ${stock.status || ""} ${stock.invalid_condition || ""}`;
  if (text.includes("非一日脉冲") || text.includes("延续升级")) {
    return "persistent";
  }
  if (
    text.includes("一日脉冲") ||
    text.includes("退出") ||
    text.includes("降级")
  ) {
    return "risk";
  }
  if (text.includes("延续")) {
    return "watch";
  }
  return "";
}

export function persistenceLabel(stock: StockListCard) {
  const tone = persistenceTone(stock);
  if (tone === "persistent") {
    return stock.status?.includes("延续升级")
      ? "非一日脉冲·升级"
      : "非一日脉冲";
  }
  if (tone === "risk") {
    return "一日脉冲风险";
  }
  if (tone === "watch") {
    return stock.persistence_label || "延续待确认";
  }
  return "";
}
