import type { Tone } from "@/lib/types";

const REVIEW_STATUS_META: Record<string, { label: string; tone: Tone | string }> =
  {
    pending_outcome: { label: "等待结果", tone: "watch" },
    pending_execution: { label: "等待执行", tone: "warning" },
    ready_review: { label: "待归因", tone: "warning" },
    reviewed: { label: "已归因", tone: "positive" },
    blocked_data: { label: "数据阻塞", tone: "risk" },
    low_priority: { label: "低信号", tone: "stale" },
  };

const REVIEW_REASON_LABELS: Record<string, string> = {
  invalidated: "判断失效",
  execution_gap: "执行落差",
  missed_opportunity: "错过机会",
  data_issue: "数据问题",
  blocked_data: "数据阻塞",
  data_blocked: "数据阻塞",
  superseded: "判断被替代",
  pending_outcome: "等待结果",
  pending_execution: "等待执行",
  reviewed: "已归因",
  low_priority: "低信号",
};

export function reviewStatusMeta(status?: string) {
  return (
    REVIEW_STATUS_META[status || ""] || {
      label: status || "未知",
      tone: "stale",
    }
  );
}

export function reasonLabel(key?: string, fallback?: string) {
  return REVIEW_REASON_LABELS[key || ""] || fallback || key || "待归因";
}

export function reviewCaseHref(decisionId?: string | null) {
  return decisionId
    ? `/review?case=${encodeURIComponent(decisionId)}`
    : "/review";
}

export function pct(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return `${Number(value).toFixed(2)}%`;
}

export function ratePct(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return `${(Number(value) * 100).toFixed(0)}%`;
}

export function countText(value?: number | string) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return String(value ?? "-");
  }
  return numeric.toLocaleString("zh-CN");
}

export function shadowStatusMeta(status?: string) {
  if (status === "ready") {
    return { label: "样本可用", tone: "positive" };
  }
  if (status === "partial") {
    return { label: "部分可用", tone: "warning" };
  }
  if (status === "missing") {
    return { label: "未生成", tone: "stale" };
  }
  return { label: status || "未知", tone: "info" };
}

export function sampleGuardrailText(
  item?: { sample_count?: number } | null,
) {
  const count = Number(item?.sample_count || 1);
  if (count >= 10) {
    return "10 条及以上：策略级校准建议，仍需验证状态。";
  }
  if (count >= 5) {
    return "5 条以上：可提出规则调整建议，必须持续验证。";
  }
  if (count >= 2) {
    return "2-4 条：待验证模式，继续观察后续样本。";
  }
  return "1 条：只能生成观察假设，不能直接修改规则。";
}
