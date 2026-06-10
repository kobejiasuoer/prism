"use client";

import type { ReactNode } from "react";
import { Database } from "lucide-react";

import { Badge } from "@/components/badge";
import { refreshReasonCopy, refreshReasonLabel } from "@/lib/readiness-copy";
import type { ReadinessSourceFreshness, RefreshStatus } from "@/lib/types";

export type SettingsReadinessDetailsProps = {
  status?: RefreshStatus;
  recommendation?: ReactNode;
};

function formatAuthorityLabel(value?: string) {
  const key = String(value || "").trim();
  const copy: Record<string, string> = {
    authoritative_daily: "正式日线",
    disclosure: "公告披露",
    display_only: "仅展示",
    execution: "执行约束",
    formal_candidate: "正式候选",
    live: "盘中快源",
    live_small: "小额实盘",
    news: "新闻",
    pipeline: "工作流",
    reference: "参考源",
  };
  return copy[key] || key || "-";
}

const CAPABILITY_LABELS: Record<string, string> = {
  observe: "观察",
  review: "复盘",
  approve: "审批",
  trade: "交易",
  notify: "通知",
  ledger_capture: "账本回写",
};

const HARD_DATA_REASONS = new Set([
  "manifest_missing",
  "manifest_status_failed",
  "missing",
  "provider_failure",
  "trade_date_mismatch",
  "trade_date_unknown",
  "freshness_unknown",
]);
const STALE_DATA_REASONS = new Set(["freshness_stale", "freshness_expired"]);
const POLICY_ONLY_REASONS = new Set([
  "live_small_not_allowed",
  "fallback_not_allowed",
  "formal_not_allowed",
]);

function datasetReasonSet(row: ReadinessSourceFreshness) {
  return new Set(
    (row.stale_reasons || [])
      .map((reason) => String(reason || "").trim())
      .filter(Boolean),
  );
}

function datasetHasAny(reasons: Set<string>, targets: Set<string>) {
  for (const reason of reasons) {
    if (targets.has(reason)) return true;
  }
  return false;
}

function datasetIsAuxiliary(row: ReadinessSourceFreshness): boolean {
  return (
    row.decision_scope === "display_only" ||
    row.source_lane === "reference" ||
    row.source_lane === "news" ||
    row.source_lane === "disclosure"
  );
}

function datasetIssueKind(
  row: ReadinessSourceFreshness,
  state?: string,
): "hard" | "optional" | "stale" | "policy" | "ok" {
  const normalizedState = String(state || "").toUpperCase();
  const reasons = datasetReasonSet(row);
  if (
    !row.available ||
    normalizedState === "INVALID" ||
    datasetHasAny(reasons, HARD_DATA_REASONS)
  ) {
    if (datasetIsAuxiliary(row)) return "optional";
    return "hard";
  }
  if (
    datasetHasAny(reasons, STALE_DATA_REASONS) ||
    normalizedState === "STALE"
  ) {
    return "stale";
  }
  if (
    normalizedState === "BLOCKED" ||
    normalizedState === "DEGRADED" ||
    datasetHasAny(reasons, POLICY_ONLY_REASONS) ||
    row.fallback_used
  ) {
    return "policy";
  }
  return "ok";
}

function datasetIssueTone(
  row: ReadinessSourceFreshness,
  state?: string,
): "positive" | "info" | "watch" | "warning" | "risk" {
  switch (datasetIssueKind(row, state)) {
    case "hard":
      return "risk";
    case "optional":
      return "warning";
    case "stale":
      return "watch";
    case "policy":
      return "warning";
    default:
      return "positive";
  }
}

function datasetIssueLabel(
  row: ReadinessSourceFreshness,
  state?: string,
): string {
  switch (datasetIssueKind(row, state)) {
    case "hard":
      return "数据不可用";
    case "optional":
      return "辅助受限";
    case "stale":
      return "偏旧/需补刷";
    case "policy":
      return "复盘可用";
    default:
      return "可用";
  }
}

function datasetScopeLabel(row: ReadinessSourceFreshness): string | null {
  if (row.decision_scope === "display_only") return "辅助数据";
  if (row.decision_scope === "live_small")
    return row.live_small_allowed ? "可进实盘链路" : "不进实盘";
  if (row.source_lane === "reference") return "参考数据";
  if (row.source_lane === "authoritative_daily") return "正式日频";
  return null;
}

function DatasetFreshnessPanel({ status }: { status?: RefreshStatus }) {
  const readiness = status?.readiness;
  const datasets = readiness?.dataset_freshness || [];
  const datasetStates = readiness?.dataset_states || {};
  const capabilities = readiness?.capabilities || {};

  if (!datasets.length) {
    return null;
  }

  const blockingDatasets = new Set<string>();
  Object.values(capabilities).forEach((report) => {
    if (!report || report.granted) return;
    (report.blocking_sources || []).forEach((key) => blockingDatasets.add(key));
  });

  const sorted = [...datasets].sort((a, b) => {
    const aBlocks = blockingDatasets.has(a.key) ? 0 : 1;
    const bBlocks = blockingDatasets.has(b.key) ? 0 : 1;
    if (aBlocks !== bBlocks) return aBlocks - bBlocks;
    const aTone = datasetIssueTone(a, datasetStates[a.key]);
    const bTone = datasetIssueTone(b, datasetStates[b.key]);
    const severity = {
      risk: 0,
      warning: 1,
      watch: 2,
      info: 3,
      positive: 4,
    } as const;
    return severity[aTone] - severity[bTone];
  });

  const visible = sorted.slice(0, 4);
  const hardIssueCount = sorted.filter(
    (row) => datasetIssueKind(row, datasetStates[row.key]) === "hard",
  ).length;
  const optionalIssueCount = sorted.filter(
    (row) => datasetIssueKind(row, datasetStates[row.key]) === "optional",
  ).length;
  const staleIssueCount = sorted.filter(
    (row) => datasetIssueKind(row, datasetStates[row.key]) === "stale",
  ).length;
  const policyIssueCount = sorted.filter(
    (row) => datasetIssueKind(row, datasetStates[row.key]) === "policy",
  ).length;
  const reviewGranted = capabilities.review?.granted !== false;
  const approveGranted = Boolean(capabilities.approve?.granted);
  const tradeGranted = Boolean(capabilities.trade?.granted);
  const dataBlockedCapabilities = Object.entries(capabilities)
    .filter(([, report]) => report && !report.granted)
    .filter(([, report]) => (report.blocking_sources || []).length > 0)
    .map(([key, report]) => ({ key, report }));

  return (
    <div className="mt-4 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Database size={15} className="text-[var(--text-primary)]" />
        <span className="text-[13px] font-medium text-[var(--text-primary)]">
          能力闸门数据依赖
        </span>
        <span className="text-[11px] text-[var(--text-tertiary)]">
          {datasets.length} 项 ·{" "}
          {hardIssueCount ? `${hardIssueCount} 项真不可用` : "无真故障"}
          {optionalIssueCount ? ` · ${optionalIssueCount} 项辅助受限` : ""}
          {staleIssueCount ? ` · ${staleIssueCount} 项偏旧` : ""}
          {policyIssueCount ? ` · ${policyIssueCount} 项仅限复盘/观察` : ""}
        </span>
      </div>
      <p className="text-[12px] leading-5 text-[var(--text-secondary)]">
        这里不是“正式数据源是否崩了”的总览，而是能力闸门看到的底层依赖。红色才代表数据本身不可用/错日/缺证明；黄色通常表示可观察、可复盘，但不能直接作为真钱审批或交易依据。
      </p>

      <div className="mt-3 flex flex-wrap gap-1.5">
        <Badge tone={reviewGranted ? "positive" : "risk"}>
          复盘{reviewGranted ? "可用" : "受限"}
        </Badge>
        <Badge tone={approveGranted ? "positive" : "warning"}>
          审批{approveGranted ? "可用" : "未放行"}
        </Badge>
        <Badge tone={tradeGranted ? "positive" : "warning"}>
          交易{tradeGranted ? "可用" : "未放行"}
        </Badge>
      </div>

      {dataBlockedCapabilities.length ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {dataBlockedCapabilities.map(({ key, report }) => (
            <Badge
              key={key}
              tone={report.status === "blocked" ? "risk" : "warning"}
            >
              {CAPABILITY_LABELS[key] || key}:{" "}
              {(report.blocking_sources || []).slice(0, 2).join(", ") || "未知"}
            </Badge>
          ))}
        </div>
      ) : null}

      <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
        {visible.map((row) => {
          const state = datasetStates[row.key];
          const tone = datasetIssueTone(row, state);
          const isBlocking = blockingDatasets.has(row.key);
          const scopeLabel = datasetScopeLabel(row);
          return (
            <div
              key={row.key}
              className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2"
              style={
                isBlocking
                  ? {
                      borderColor:
                        "color-mix(in_srgb,var(--warning) 60%, transparent)",
                    }
                  : undefined
              }
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[12px] font-medium text-[var(--text-primary)]">
                  {row.label || row.key}
                </span>
                <Badge tone={tone}>{datasetIssueLabel(row, state)}</Badge>
                {scopeLabel ? <Badge tone="info">{scopeLabel}</Badge> : null}
                {isBlocking ? (
                  <Badge tone={tone === "risk" ? "risk" : "warning"}>
                    影响放行
                  </Badge>
                ) : null}
              </div>
              <div className="mt-1 text-[11px] leading-5 text-[var(--text-tertiary)]">
                {row.value || "-"}
                {row.age_label ? ` · ${row.age_label}` : ""}
                {row.provider ? ` · ${row.provider}` : ""}
              </div>
              {row.stale_reasons?.length ? (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {row.stale_reasons.slice(0, 4).map((reason, index) => (
                    <span
                      key={`${row.key}-${reason}-${index}`}
                      className="rounded border border-[var(--border-subtle)] px-1.5 py-0.5 text-[10px] text-[var(--text-secondary)]"
                    >
                      {refreshReasonLabel(reason)}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
      {sorted.length > visible.length ? (
        <div className="mt-3 text-[11px] text-[var(--text-tertiary)]">
          其余 {sorted.length - visible.length} 项在诊断面板中继续查看。
        </div>
      ) : null}
    </div>
  );
}

export function SettingsReadinessDetails({
  status,
  recommendation,
}: SettingsReadinessDetailsProps) {
  const readiness = status?.readiness;

  if (!readiness) {
    return <>{recommendation}</>;
  }

  const formalBlockers = readiness.formal_blockers || [];
  const formalSources = (readiness.source_freshness || [])
    .filter((source) => source.manifest_path)
    .slice(0, 4);
  const staleReasons = (readiness.source_freshness || [])
    .flatMap((source) =>
      (source.stale_reasons || []).map((reason) => ({
        reason,
        source: source.label,
      })),
    )
    .slice(0, 8);

  return (
    <>
      <div className="mt-4 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <Database
            size={15}
            className={
              readiness.formal_ready
                ? "text-[var(--positive)]"
                : "text-[var(--warning)]"
            }
          />
          <span className="text-[13px] font-medium text-[var(--text-primary)]">
            正式数据口径
          </span>
          <Badge tone={readiness.formal_ready ? "positive" : "watch"}>
            {readiness.formal_ready
              ? "正式口径通过"
              : "快源可用 / 正式口径未接入"}
          </Badge>
        </div>
        <p className="text-[12px] leading-5 text-[var(--text-secondary)]">
          当前快源用于看盘、复核和影子推演；正式放行需要日线、复权、benchmark
          和执行约束等目标源全部通过。
        </p>
        {formalSources.length ? (
          <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
            {formalSources.map((source) => (
              <div
                key={source.key}
                className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[12px] font-medium text-[var(--text-primary)]">
                    {source.label}
                  </span>
                  <Badge
                    tone={source.formal_decision_allowed ? "positive" : "watch"}
                  >
                    {source.formal_decision_allowed
                      ? "formal"
                      : formatAuthorityLabel(source.decision_scope)}
                  </Badge>
                </div>
                <div className="mt-1 text-[11px] leading-5 text-[var(--text-tertiary)]">
                  {formatAuthorityLabel(source.source_lane)} · 当前{" "}
                  {source.provider || "-"} · 目标{" "}
                  {source.target_authority_provider ||
                    source.authority_provider ||
                    "-"}
                </div>
              </div>
            ))}
          </div>
        ) : null}
        {formalBlockers.length ? (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {formalBlockers.slice(0, 6).map((item) => (
              <Badge key={item.code} tone="warning">
                {item.label}
              </Badge>
            ))}
          </div>
        ) : null}
      </div>

      {recommendation}

      {staleReasons.length ? (
        <div className="mt-4 rounded-md border border-[color-mix(in_srgb,var(--warning)_24%,transparent)] bg-[color-mix(in_srgb,var(--warning)_8%,transparent)] px-3 py-3">
          <div className="mb-2 text-[12px] font-medium text-[var(--text-primary)]">
            为什么不可作为真钱依据
          </div>
          <div className="flex flex-wrap gap-1.5">
            {staleReasons.map((item, index) => {
              const reason = refreshReasonCopy(item.reason);
              return (
                <Badge
                  key={`${item.source}-${item.reason}-${index}`}
                  tone="warning"
                >
                  {item.source}: {reason.label}
                </Badge>
              );
            })}
          </div>
        </div>
      ) : null}

      <DatasetFreshnessPanel status={status} />
    </>
  );
}
