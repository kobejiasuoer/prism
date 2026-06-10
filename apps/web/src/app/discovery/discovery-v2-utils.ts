import type { StockListCard } from "@/lib/types";
import { uniqueTexts as compactUniqueTexts } from "@/lib/text-utils";

export { uniqueTexts } from "@/lib/text-utils";

const V2_ACTION_ORDER: Record<string, number> = {
  observe: 0,
  review: 1,
  shadow: 2,
  trial: 3,
  actionable: 4,
};

export const V2_ACTION_LABELS: Record<string, string> = {
  observe: "只观察",
  review: "人工复核",
  shadow: "影子跟踪",
  trial: "试错待触发",
  actionable: "可执行待复核",
};

function v2Judgment(stock: StockListCard) {
  return stock.opportunity_v2 &&
    typeof stock.opportunity_v2 === "object" &&
    !Array.isArray(stock.opportunity_v2)
    ? (stock.opportunity_v2 as Record<string, unknown>)
    : {};
}

function v2Nested(stock: StockListCard, key: string) {
  const value = v2Judgment(stock)[key];
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function normalizeV2Action(value: unknown) {
  const action = String(value ?? "").trim();
  return action in V2_ACTION_ORDER ? action : "";
}

export function v2Action(stock: StockListCard) {
  return normalizeV2Action(
    stock.suggested_action || v2Judgment(stock).suggested_action,
  );
}

export function hasV2(stock: StockListCard) {
  return Boolean(
    v2Action(stock) ||
      stock.thesis ||
      stock.why_now ||
      Object.keys(v2Judgment(stock)).length,
  );
}

export function v2ActionLabel(stock: StockListCard) {
  const action = v2Action(stock);
  return String(
    stock.suggested_action_label ||
      v2Judgment(stock).action_label ||
      V2_ACTION_LABELS[action] ||
      "",
  ).trim();
}

export function v2Rank(action: unknown) {
  return V2_ACTION_ORDER[normalizeV2Action(action)] ?? -1;
}

export function v2HardMax(stock: StockListCard) {
  return normalizeV2Action(
    stock.hard_gate_max_action ||
      v2Nested(stock, "hard_gate").maximum_allowed_action,
  );
}

export function v2HardReason(stock: StockListCard) {
  const gate = v2Nested(stock, "hard_gate");
  return compactUniqueTexts([
    stock.hard_gate_block_reason,
    gate.block_reasons,
  ]).join("；");
}

export function v2HardBlocks(stock: StockListCard) {
  const action = v2Action(stock);
  const desired = normalizeV2Action(v2Judgment(stock).desired_action);
  const maxAction = v2HardMax(stock);
  return Boolean(
    stock.hard_gate_blocks_action ||
      v2HardReason(stock) ||
      (action && maxAction && v2Rank(maxAction) < v2Rank(desired || action)),
  );
}

export function v2MissingItems(stock: StockListCard) {
  return compactUniqueTexts([
    stock.missing_confirmation,
    v2Judgment(stock).missing_confirmation,
  ]);
}

export function v2MissingText(stock: StockListCard, maxItems = 2) {
  return v2MissingItems(stock).slice(0, maxItems).join("；");
}

export function v2ConfidenceLabel(stock: StockListCard) {
  const raw = stock.confidence ?? v2Judgment(stock).confidence;
  const value = Number(raw);
  if (!Number.isFinite(value)) {
    return "";
  }
  return value <= 1 ? `${Math.round(value * 100)}%` : `${Math.round(value)}%`;
}

function v2CalibrationObject(
  stock: StockListCard,
  key: "calibration" | "mode_guard" | "playbook",
) {
  if (key === "playbook") {
    const flattened = stock.v2_playbook_adjustment;
    if (
      flattened &&
      typeof flattened === "object" &&
      !Array.isArray(flattened)
    ) {
      return flattened;
    }
    return (
      (v2Nested(stock, "calibration").playbook_adjustment as Record<
        string,
        unknown
      >) || {}
    );
  }
  return v2Nested(stock, key);
}

function v2CalibrationStageLabel(stage: string) {
  if (stage === "active_ready") {
    return "校准通过";
  }
  if (stage === "cold_start") {
    return "冷启动收紧";
  }
  if (stage === "needs_recalibration") {
    return "复盘收紧";
  }
  if (stage === "validating_pattern") {
    return "样本验证";
  }
  if (stage === "observation_hypothesis") {
    return "样本观察";
  }
  if (stage === "pending_outcome") {
    return "等待复盘";
  }
  return stage;
}

export function v2CalibrationMeta(stock: StockListCard) {
  const judgment = v2Judgment(stock);
  const calibration = v2CalibrationObject(stock, "calibration");
  const guard = v2CalibrationObject(stock, "mode_guard");
  const playbook = v2CalibrationObject(stock, "playbook");
  const requested = String(
    stock.v2_mode_requested ??
      judgment.mode_requested ??
      guard.requested_mode ??
      "",
  ).trim();
  const effective = String(
    stock.v2_mode_effective ??
      judgment.mode_effective ??
      guard.effective_mode ??
      judgment.mode ??
      "",
  ).trim();
  const stage = String(
    stock.v2_calibration_stage ??
      calibration.sample_stage ??
      guard.sample_stage ??
      "",
  ).trim();
  const reason = String(
    stock.v2_calibration_guard_reason ??
      calibration.guard_reason ??
      guard.guard_reason ??
      playbook.reason ??
      "",
  ).trim();
  const mature =
    stock.v2_calibration_mature_samples ??
    calibration.mature_samples ??
    guard.mature_samples;
  const activeAllowed = Boolean(
    stock.v2_active_allowed ??
      calibration.active_allowed ??
      guard.active_allowed,
  );
  const actionCap = normalizeV2Action(playbook.action_cap);
  const adjustment = Number(playbook.confidence_adjustment);

  if (requested === "active" && effective && effective !== "active") {
    return {
      label: `active→${effective}`,
      tone: "warning",
      detail: reason || "V2 active 尚未通过复盘样本准入。",
    };
  }
  if (actionCap || (Number.isFinite(adjustment) && adjustment < 0)) {
    return {
      label: actionCap
        ? `playbook≤${V2_ACTION_LABELS[actionCap] || actionCap}`
        : "playbook收紧",
      tone: "warning",
      detail: reason || "该 playbook 已按复盘结果降权。",
    };
  }
  if (stage === "cold_start" || stage === "needs_recalibration") {
    return {
      label: v2CalibrationStageLabel(stage),
      tone: "warning",
      detail: reason || "V2 校准层临时收紧动作阈值。",
    };
  }
  if (stage || activeAllowed) {
    const sample =
      mature !== undefined && mature !== null && String(mature).trim() !== ""
        ? ` ${mature}`
        : "";
    return {
      label: activeAllowed
        ? "校准通过"
        : `${v2CalibrationStageLabel(stage)}${sample}`,
      tone: activeAllowed ? "positive" : "info",
      detail: reason,
    };
  }
  return null;
}

export function v2AiSummary(stock: StockListCard) {
  const direct = stock.ai_summary;
  if (direct && typeof direct === "object" && !Array.isArray(direct)) {
    return direct as Record<string, unknown>;
  }
  return v2Nested(stock, "ai_summary");
}

export function v2AiDelta(stock: StockListCard) {
  const direct = stock.ai_delta;
  if (direct && typeof direct === "object" && !Array.isArray(direct)) {
    return direct as Record<string, unknown>;
  }
  return v2Nested(stock, "ai_delta");
}

export function v2AiStatus(stock: StockListCard) {
  return String(
    v2AiSummary(stock).status ||
      stock.ai_status ||
      v2Judgment(stock).ai_status ||
      "",
  ).trim();
}

export function v2AiTone(status: string) {
  if (status === "used") {
    return "positive";
  }
  if (status === "shadow_recorded") {
    return "info";
  }
  if (status === "fallback" || status === "not_configured") {
    return "warning";
  }
  if (status === "disabled" || status === "not_requested") {
    return "watch";
  }
  return "info";
}

export function v2ActionTone(stock: StockListCard) {
  const action = v2Action(stock);
  if (v2HardBlocks(stock) && action === "actionable") {
    return "watch";
  }
  if (action === "actionable" || action === "trial") {
    return "positive";
  }
  if (action === "review" || action === "shadow") {
    return "watch";
  }
  return "info";
}
