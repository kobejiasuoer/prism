"use client";

import {
  AlertTriangle,
  Database,
  Eye,
  FileJson,
  KeyRound,
  LoaderCircle,
  Play,
  RefreshCw,
  RotateCcw,
} from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/badge";
import { EmptyState, ErrorState, Panel } from "@/components/data-card";
import { MetricCard } from "@/components/metric-card";
import type { PreviewDrawerState } from "@/components/preview-drawer";
import { api } from "@/lib/api";
import {
  useDataAssetsStatus,
  useDecisionLedgerHealth,
  useFormalDataStatus,
  useRuns,
  useRunTask,
  useTriggerRefresh,
} from "@/lib/hooks";
import {
  formatCooldown,
  readinessModeCopy,
  refreshReasonCopy,
  refreshReasonLabel,
  refreshTaskCopy,
} from "@/lib/readiness-copy";
import type {
  DataAssetsStatus,
  DecisionLedgerHealthResponse,
  FormalDataStatus,
  FreshnessGuardianDatasetState,
  RefreshStatus,
  RunItem,
  TaskDefinition,
} from "@/lib/types";

import { runIdOf, runTone, taskNameOf } from "./settings-utils";

type PreviewUpdater = (
  state: PreviewDrawerState | ((current: PreviewDrawerState) => PreviewDrawerState),
) => void;

function formatAssetCount(value?: number | null) {
  const number = Number(value || 0);
  if (number >= 10000) {
    return `${(number / 10000).toFixed(number >= 100000 ? 0 : 1)}w`;
  }
  return String(number);
}

function assetTone(row: DataAssetsStatus["datasets"][number]) {
  if (!row.available) {
    return "warning";
  }
  if (row.provider === "tushare" && row.source_authority_ready) {
    return "positive";
  }
  if (row.provider === "tushare") {
    return "info";
  }
  return "watch";
}

function usageLabel(value?: string) {
  const labels: Record<string, string> = {
    formal_guardrail: "正式闸门",
    stock_profile: "个股证据",
    factor: "排序因子",
    risk_event: "风险标签",
    reference: "引用字典",
    review_only: "复盘只读",
    hard_gate: "硬闸门",
    ranking_signal: "参与排序",
    risk_penalty: "风险扣分",
    evidence_only: "只读证据",
    backtest_label: "复盘标签",
    formal_candidate: "真钱闸门可用",
    display_only: "仅展示",
    research_only: "研究/观察",
  };
  return labels[value || ""] || value || "-";
}

function formalSetupTone(state?: string) {
  switch (state) {
    case "ready":
      return "positive";
    case "token_missing":
    case "token_invalid":
    case "provider_error":
      return "risk";
    case "rate_limited":
    case "permission_or_points_blocked":
    case "stale_or_misaligned":
    case "coverage_incomplete":
      return "warning";
    case "manifest_missing":
      return "watch";
    default:
      return "info";
  }
}

function formalSetupLabel(state?: string): string {
  const copy: Record<string, string> = {
    ready: "已接入",
    token_missing: "缺 token",
    token_invalid: "token 无效",
    rate_limited: "流控等待",
    permission_or_points_blocked: "权限/积分阻塞",
    coverage_incomplete: "覆盖不完整",
    manifest_missing: "未刷新",
    provider_error: "接口失败",
    stale_or_misaligned: "过期/错日",
    formal_not_allowed: "未放行",
  };
  return copy[state || ""] || state || "未知";
}

function DataAssetsPanel({
  status,
  loading,
  onRefresh,
  detailOpen,
  onToggleDetail,
}: {
  status?: DataAssetsStatus;
  loading?: boolean;
  onRefresh: () => void;
  detailOpen: boolean;
  onToggleDetail: () => void;
}) {
  const summary = status?.summary;
  const rows = status?.datasets || [];
  const mustShowDatasets = new Set([
    "index.weight",
    "market.daily_basic_snapshot",
    "market.margin",
    "market.top_list",
    "market.top_inst",
    "market.hsgt_moneyflow",
    "market.ggt_daily",
  ]);
  const mustShowRows = rows.filter((row) => mustShowDatasets.has(row.dataset) && row.available);
  const fillerRows = rows
    .filter((row) => !mustShowDatasets.has(row.dataset) && row.available)
    .sort((a, b) => Number(b.key_count || 0) - Number(a.key_count || 0));
  const missingRows = rows.filter((row) => !row.available);
  const priorityRows = [...mustShowRows, ...fillerRows, ...missingRows].filter((row, index, list) => (
    list.findIndex((item) => item.dataset === row.dataset) === index
  ));
  const runs = status?.harvest_runs || [];
  const displayedCount = summary?.displayed_dataset_count || priorityRows.length;

  return (
    <Panel id="data-assets" title="Tushare 数据资产" eyebrow="Data Assets" className="scroll-mt-6">
      <div className="surface-card p-4">
        <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <Badge tone={(summary?.available_count || 0) > 0 ? "positive" : "warning"}>
                {status ? `${summary?.available_count}/${summary?.catalog_count}` : loading ? "检查中" : "等待"}
              </Badge>
              <Badge tone="info">交易日 {status?.expected_trade_date || "-"}</Badge>
              <Badge tone="watch">manifest {formatAssetCount(summary?.manifest_count)}</Badge>
              <Badge tone={detailOpen ? "positive" : "info"}>{detailOpen ? "诊断明细" : `关键资产 ${formatAssetCount(displayedCount)}`}</Badge>
            </div>
            <h3 className="text-[16px] font-semibold text-[var(--text-primary)]">一天授权已经沉淀成可查询资产</h3>
            <p className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
              覆盖 {formatAssetCount(summary?.universe_count)} 只、{formatAssetCount(summary?.trade_days)} 个交易日；每个资产都标明用途、排序权限和真钱闸门边界。
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" className="focus-ring prism-btn prism-btn-secondary" onClick={onToggleDetail}>
              <FileJson size={13} />
              {detailOpen ? "收起明细" : "诊断明细"}
            </button>
            <button type="button" className="focus-ring prism-btn prism-btn-secondary" onClick={onRefresh}>
              <RotateCcw size={13} className={loading ? "animate-spin" : ""} />
              重新检查
            </button>
          </div>
        </div>

        <div className="mb-4 grid grid-cols-2 gap-2 lg:grid-cols-4">
          <MetricCard label="Tushare 资产" value={formatAssetCount(summary?.tushare_ready_count)} detail="已落库数据集" tone="positive" />
          <MetricCard label="覆盖股票" value={formatAssetCount(summary?.universe_count)} detail="沪深300/中证500底池" tone="info" />
          <MetricCard label="交易日" value={formatAssetCount(summary?.trade_days)} detail="历史窗口" tone="watch" />
          <MetricCard label="资产文件" value={formatAssetCount(summary?.manifest_count)} detail={status?.generated_at || "等待扫描"} tone="info" />
        </div>

        {runs.length ? (
          <div className="mb-4 grid grid-cols-1 gap-2 lg:grid-cols-3">
            {runs.map((run) => (
              <div key={`${run.label}-${run.run_dir}`} className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-[12px] font-medium text-[var(--text-primary)]">{run.label}</span>
                  <Badge tone={run.ok ? "positive" : "warning"}>{run.ok ? "ok" : "待确认"}</Badge>
                </div>
                <div className="mt-1 text-[11px] leading-5 text-[var(--text-tertiary)]">
                  {run.start_date || "-"} {"->"} {run.end_date || run.trade_date || "-"}
                </div>
                <div className="mt-1 text-[11px] leading-5 text-[var(--text-secondary)]">
                  {formatAssetCount(run.universe_count)} 只 · {formatAssetCount(run.trade_days)} 天 · {(run.datasets || []).slice(0, 3).join(" / ") || "dataset"}
                </div>
              </div>
            ))}
          </div>
        ) : null}

        <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
          {priorityRows.map((row) => (
            <div key={row.dataset} className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate text-[12px] font-medium text-[var(--text-primary)]">{row.label}</div>
                  <div className="mono mt-0.5 truncate text-[10px] text-[var(--text-tertiary)]">{row.dataset}</div>
                </div>
                <div className="flex shrink-0 flex-wrap justify-end gap-1">
                  <Badge tone={assetTone(row)}>{row.provider || "-"}</Badge>
                  <Badge tone={row.live_permission === "formal_candidate" ? "positive" : row.live_permission === "research_only" ? "watch" : "info"}>
                    {usageLabel(row.live_permission)}
                  </Badge>
                </div>
              </div>
              <div className="mt-2 text-[11px] leading-5 text-[var(--text-secondary)]">
                {row.purpose || "-"} · key {formatAssetCount(row.key_count)} · rows {formatAssetCount(row.latest_row_count)}
              </div>
              <div className="mt-2 flex flex-wrap gap-1">
                <Badge tone="info">{usageLabel(row.feature_group)}</Badge>
                <Badge tone={row.decision_use === "hard_gate" ? "positive" : row.decision_use === "risk_penalty" ? "risk" : row.decision_use === "ranking_signal" ? "watch" : "info"}>
                  {usageLabel(row.decision_use)}
                </Badge>
                {(row.intended_surfaces || []).slice(0, 4).map((surface) => (
                  <Badge key={`${row.dataset}-${surface}`} tone="info">{surface}</Badge>
                ))}
              </div>
              {row.usage_explanation ? (
                <div className="mt-2 text-[11px] leading-5 text-[var(--text-secondary)]">{row.usage_explanation}</div>
              ) : null}
              <div className="mt-1 text-[11px] leading-5 text-[var(--text-tertiary)]">
                {row.trade_date || "-"} · {row.freshness_status || "-"} · {row.decision_scope || "display_only"}
              </div>
            </div>
          ))}
          {!priorityRows.length ? <EmptyState>等待 Tushare 数据资产扫描。</EmptyState> : null}
        </div>
      </div>
    </Panel>
  );
}

function FormalDataPanel({
  status,
  loading,
  onRefresh,
  detailOpen,
  onToggleDetail,
}: {
  status?: FormalDataStatus;
  loading?: boolean;
  onRefresh: () => void;
  detailOpen: boolean;
  onToggleDetail: () => void;
}) {
  const trigger = useTriggerRefresh("today");
  const [feedback, setFeedback] = useState("");
  const datasets = status?.datasets || [];
  const blockers = status?.blockers || [];
  const provider = status?.provider;
  const ready = Boolean(status?.ready);
  const lastRun = status?.last_run;
  const setupSteps = status?.setup_steps || [];

  function startRefresh() {
    setFeedback("");
    trigger.mutate(
      { task_name: "formal_data_refresh", reason: "manual_formal_data_setup" },
      {
        onSuccess: (payload) => {
          setFeedback(`${payload.task.title || "正式口径数据刷新"} 已启动。`);
          onRefresh();
        },
        onError: (error) => setFeedback(error instanceof Error ? error.message : "正式口径刷新启动失败"),
      },
    );
  }

  return (
    <Panel id="formal-data" title="正式口径数据源" eyebrow="Formal Sources" className="scroll-mt-6">
      <div className="surface-card p-4">
        <div className="mb-4 grid grid-cols-1 gap-2 sm:grid-cols-3">
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
            <div className="flex items-center gap-2 text-[11px] text-[var(--text-tertiary)]">
              <KeyRound size={13} />
              Tushare Token
            </div>
            <div className="mt-1">
              <Badge tone={provider?.token_configured ? "positive" : "risk"}>
                {provider?.token_configured ? "已配置" : "未配置"}
              </Badge>
            </div>
            <div className="mt-1 truncate text-[11px] text-[var(--text-tertiary)]">
              {(provider?.configured_token_env_names?.length
                ? provider.configured_token_env_names
                : provider?.token_env_names || []
              ).join(" / ") || "PRISM_TUSHARE_TOKEN"}
            </div>
            <div className="mt-0.5 truncate text-[10px] text-[var(--text-tertiary)]">
              {provider?.local_env_file_exists ? ".env 可用" : ".env 未写入"}
            </div>
          </div>
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
            <div className="text-[11px] text-[var(--text-tertiary)]">接入进度</div>
            <div className="mt-1 flex items-center gap-2">
              <Badge tone={ready ? "positive" : "warning"}>
                {status ? `${status.ready_count}/${status.total_count}` : loading ? "检查中" : "-"}
              </Badge>
              <span className="text-[12px] text-[var(--text-secondary)]">{ready ? "全部通过" : `${status?.blocked_count ?? 0} 项待处理`}</span>
            </div>
            <div className="mt-1 text-[11px] text-[var(--text-tertiary)]">{status?.expected_trade_date || "-"}</div>
          </div>
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
            <div className="text-[11px] text-[var(--text-tertiary)]">最近刷新</div>
            <div className="mt-1 flex items-center gap-2">
              <Badge tone={runTone(lastRun?.status)}>{status?.running ? "running" : lastRun?.status || "none"}</Badge>
              <span className="truncate text-[12px] text-[var(--text-secondary)]">{lastRun?.checked_started_at || status?.generated_at || "-"}</span>
            </div>
          </div>
        </div>

        {feedback ? (
          <div className="mb-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
            {feedback}
          </div>
        ) : null}

        <div className="mb-4 flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="focus-ring prism-btn prism-btn-primary"
            onClick={startRefresh}
            disabled={trigger.isPending || Boolean(status?.running)}
          >
            {trigger.isPending || status?.running ? <LoaderCircle size={13} className="animate-spin" /> : <RefreshCw size={13} />}
            刷新正式口径
          </button>
          <button type="button" className="focus-ring prism-btn prism-btn-secondary" onClick={onRefresh}>
            <RotateCcw size={13} />
            重新检查
          </button>
          <button type="button" className="focus-ring prism-btn prism-btn-secondary" onClick={onToggleDetail}>
            <FileJson size={13} className={loading && detailOpen ? "animate-spin" : ""} />
            {detailOpen ? "收起明细" : "诊断明细"}
          </button>
        </div>

        {blockers.length ? (
          <div className="mb-4 rounded-md border border-[color-mix(in_srgb,var(--warning)_24%,transparent)] bg-[color-mix(in_srgb,var(--warning)_8%,transparent)] px-3 py-3">
            <div className="mb-2 text-[12px] font-medium text-[var(--text-primary)]">当前阻塞项</div>
            <div className="grid gap-1.5">
              {blockers.slice(0, 4).map((item) => (
                <div key={`${item.dataset}-${item.state}`} className="text-[12px] leading-5 text-[var(--text-secondary)]">
                  <span className="font-medium text-[var(--text-primary)]">{item.label || item.dataset}</span>
                  ：{formalSetupLabel(item.state)} · {item.next_action || "查看 manifest"}
                  {item.source_apis?.length ? (
                    <span className="ml-1 text-[var(--text-tertiary)]">
                      API: {item.source_apis.join(" / ")}
                    </span>
                  ) : null}
                  {item.blocked_request_keys?.length ? (
                    <span className="ml-1 text-[var(--text-tertiary)]">
                      key: {item.blocked_request_keys.join(" / ")}
                    </span>
                  ) : null}
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {setupSteps.length ? (
          <div className="mb-4 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
            <div className="mb-2 text-[12px] font-medium text-[var(--text-primary)]">接入步骤</div>
            <div className="grid gap-1.5">
              {setupSteps.map((step, index) => (
                <div key={`${index}-${step}`} className="text-[12px] leading-5 text-[var(--text-secondary)]">
                  {index + 1}. {step}
                </div>
              ))}
            </div>
          </div>
        ) : null}

        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {datasets.map((row) => (
            <div key={row.dataset || row.key} className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate text-[12px] font-medium text-[var(--text-primary)]">{row.label || row.dataset}</div>
                  <div className="mono mt-0.5 truncate text-[10px] text-[var(--text-tertiary)]">{row.dataset}</div>
                </div>
                <Badge tone={formalSetupTone(row.setup_state)}>{formalSetupLabel(row.setup_state)}</Badge>
              </div>
              <div className="mt-2 text-[11px] leading-5 text-[var(--text-secondary)]">
                当前 {row.provider || "-"} · 目标 {row.target_authority_provider || row.authority_provider || "-"} · {row.trade_date || "-"}
              </div>
              {row.source_apis?.length ? (
                <div className="mt-1 flex flex-wrap gap-1">
                  {row.source_apis.map((apiName) => (
                    <span key={`${row.dataset}-${apiName}`} className="rounded border border-[var(--border-subtle)] px-1.5 py-0.5 text-[10px] text-[var(--text-secondary)]">
                      {apiName}
                    </span>
                  ))}
                </div>
              ) : null}
              {row.required_permission ? (
                <div className="mt-1 text-[11px] leading-5 text-[var(--text-tertiary)]">{row.required_permission}</div>
              ) : null}
              {row.blocked_request_keys?.length || row.missing_request_keys?.length ? (
                <div className="mt-1 text-[11px] leading-5 text-[var(--text-tertiary)]">
                  待补 key: {[...(row.blocked_request_keys || []), ...(row.missing_request_keys || [])].join(" / ")}
                </div>
              ) : null}
              {row.error ? <div className="mt-1 line-clamp-2 text-[11px] text-[var(--text-warn)]">{row.error}</div> : null}
              <div className="mt-1 text-[11px] leading-5 text-[var(--text-tertiary)]">{row.next_action || "-"}</div>
              {row.docs?.length ? (
                <div className="mt-2 flex flex-wrap gap-2">
                  {row.docs.slice(0, 3).map((href, index) => (
                    <a
                      key={`${row.dataset}-${href}`}
                      href={href}
                      target="_blank"
                      rel="noreferrer"
                      className="text-[11px] text-[var(--accent)] underline-offset-2 hover:underline"
                    >
                      文档 {index + 1}
                    </a>
                  ))}
                </div>
              ) : null}
              {row.quality_flags?.length ? (
                <div className="mt-2 flex flex-wrap gap-1">
                  {row.quality_flags.slice(0, 3).map((flag) => (
                    <span key={`${row.dataset}-${flag}`} className="rounded border border-[var(--border-subtle)] px-1.5 py-0.5 text-[10px] text-[var(--text-secondary)]">
                      {flag}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          ))}
          {!datasets.length ? <EmptyState>等待正式口径状态。</EmptyState> : null}
        </div>
      </div>
    </Panel>
  );
}

function schedulerHealthTone(health?: string) {
  if (health === "success") {
    return "positive";
  }
  if (health === "running") {
    return "watch";
  }
  if (health === "failed") {
    return "risk";
  }
  if (health === "stale") {
    return "warning";
  }
  return "info";
}

function schedulerHealthLabel(health?: string) {
  const labels: Record<string, string> = {
    success: "今日成功",
    running: "运行中",
    failed: "今日失败",
    stale: "旧数据",
    missing: "未运行",
  };
  return labels[String(health || "")] || "待检查";
}

function guardianDecisionTone(state?: FreshnessGuardianDatasetState): "positive" | "info" | "watch" | "warning" | "risk" {
  const decision = String(state?.last_decision || "");
  const skipReason = String(state?.last_skip_reason || "");
  if (decision === "fresh") {
    return "positive";
  }
  if (decision === "launched" || skipReason.startsWith("running:")) {
    return "watch";
  }
  if (skipReason === "cooldown") {
    return "warning";
  }
  if (decision === "skip" || skipReason) {
    return "info";
  }
  const freshness = String(state?.freshness?.freshness_status || "");
  if (freshness === "expired") {
    return "risk";
  }
  if (freshness === "stale") {
    return "warning";
  }
  return "info";
}

function guardianDecisionLabel(state?: FreshnessGuardianDatasetState) {
  const decision = String(state?.last_decision || "");
  const skipReason = String(state?.last_skip_reason || "");
  if (!state?.last_checked_at && !decision) {
    return "等待检查";
  }
  if (decision === "fresh") {
    return "新鲜";
  }
  if (decision === "launched") {
    return "已触发";
  }
  if (decision === "dry_run") {
    return "Dry-run";
  }
  if (skipReason === "cooldown") {
    return "冷却中";
  }
  if (skipReason === "outside_auto_window") {
    return "窗口外";
  }
  if (skipReason.startsWith("running:")) {
    return "同类运行中";
  }
  if (skipReason.startsWith("non_trading_day:")) {
    return "非交易日";
  }
  if (decision === "skip") {
    return "已跳过";
  }
  return decision || "待检查";
}

function formatGuardianSeconds(seconds?: number | null) {
  if (seconds === null || seconds === undefined) {
    return "-";
  }
  const value = Math.max(0, Math.round(Number(seconds || 0)));
  if (value < 60) {
    return `${value}s`;
  }
  if (value < 3600) {
    return `${Math.floor(value / 60)}m`;
  }
  const hours = value / 3600;
  return `${hours < 10 ? hours.toFixed(1) : Math.round(hours)}h`;
}

function GuardianDatasetCard({
  title,
  taskName,
  state,
}: {
  title: string;
  taskName: "quotes_light" | "capital_flow_light";
  state?: FreshnessGuardianDatasetState;
}) {
  const freshness = state?.freshness || {};
  const reasons = freshness.stale_reasons || [];
  const triggerReasons = state?.last_trigger_reasons || [];
  const tone = guardianDecisionTone(state);
  const copy = refreshTaskCopy(taskName);
  const age = formatGuardianSeconds(freshness.age_seconds);
  const budget = formatGuardianSeconds(freshness.stale_after_seconds);
  const cooldown = Number(state?.cooldown_remaining_seconds || 0);

  return (
    <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[13px] font-medium text-[var(--text-primary)]">{title}</span>
            <Badge tone={tone}>{guardianDecisionLabel(state)}</Badge>
          </div>
          <div className="mono mt-1 truncate text-[11px] text-[var(--text-tertiary)]">
            {freshness.dataset || copy.title}
          </div>
        </div>
        <Badge tone={String(freshness.freshness_status || "") === "fresh" ? "positive" : reasons.length ? "warning" : "info"}>
          {freshness.freshness_status || "unknown"}
        </Badge>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2">
        <div className="rounded border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1.5">
          <div className="text-[10px] text-[var(--text-tertiary)]">数据年龄</div>
          <div className="mt-0.5 text-[12px] font-medium text-[var(--text-primary)]">{age}</div>
        </div>
        <div className="rounded border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1.5">
          <div className="text-[10px] text-[var(--text-tertiary)]">预算</div>
          <div className="mt-0.5 text-[12px] font-medium text-[var(--text-primary)]">{budget}</div>
        </div>
      </div>

      <div className="mt-3 space-y-1 text-[11px] leading-5 text-[var(--text-tertiary)]">
        <div>检查 {state?.last_checked_at || "-"}</div>
        <div>触发 {state?.last_triggered_at || "-"}</div>
        <div>数据日 {freshness.trade_date || "-"}</div>
        {cooldown > 0 ? <div>冷却剩余 {formatCooldown(cooldown)}</div> : null}
      </div>

      {state?.active_windows?.length ? (
        <div className="mt-2 flex flex-wrap gap-1">
          {state.active_windows.slice(0, 4).map((window) => (
            <span key={`${taskName}-${window}`} className="rounded border border-[var(--border-subtle)] px-1.5 py-0.5 text-[10px] text-[var(--text-secondary)]">
              {window}
            </span>
          ))}
        </div>
      ) : null}

      {reasons.length || triggerReasons.length ? (
        <div className="mt-2 flex flex-wrap gap-1">
          {[...new Set([...reasons, ...triggerReasons])].slice(0, 4).map((reason) => (
            <span key={`${taskName}-${reason}`} className="rounded border border-[var(--border-subtle)] px-1.5 py-0.5 text-[10px] text-[var(--text-secondary)]">
              {refreshReasonLabel(reason)}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function SchedulerStatusPanel({ status }: { status?: RefreshStatus }) {
  const scheduler = status?.scheduler_status;
  const service = scheduler?.scheduler;
  const summary = scheduler?.summary;
  const jobs = scheduler?.jobs || [];
  const guardian = service?.freshness_guardian;
  const visibleJobs = jobs.filter((job) => job.health !== "success").concat(jobs.filter((job) => job.health === "success")).slice(0, 7);
  const hasIssues = Boolean((summary?.failed || 0) + (summary?.stale || 0) + (summary?.missing || 0));
  const guardianCalendar = guardian?.calendar && typeof guardian.calendar === "object" ? String(guardian.calendar.status || "") : "";
  const guardianHealthy = Boolean(service?.alive && guardian?.enabled && !guardian?.last_skip_reason);

  return (
    <Panel title="后台刷新守护" eyebrow="Scheduler">
      <div className="surface-card p-4">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
              <RefreshCw size={18} className={service?.alive ? "text-[var(--positive)]" : "text-[var(--warning)]"} />
            </div>
            <div className="min-w-0">
              <div className="font-medium text-[var(--text-primary)]">{service?.alive ? "Scheduler 正在心跳" : "Scheduler 未确认在线"}</div>
              <div className="mt-1 truncate text-[12px] text-[var(--text-tertiary)]">
                last tick {service?.last_tick_at || "-"} · pid {service?.pid || "-"}
              </div>
            </div>
          </div>
          <Badge tone={service?.alive && !hasIssues ? "positive" : hasIssues ? "warning" : "info"}>
            {service?.alive && !hasIssues ? "守护正常" : hasIssues ? "需要留意" : "等待状态"}
          </Badge>
        </div>

        <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
            <div className="text-[11px] text-[var(--text-tertiary)]">今日成功</div>
            <div className="mt-1 text-[16px] font-semibold text-[var(--text-primary)]">{summary?.success ?? 0}</div>
          </div>
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
            <div className="text-[11px] text-[var(--text-tertiary)]">运行中</div>
            <div className="mt-1 text-[16px] font-semibold text-[var(--text-primary)]">{summary?.running ?? 0}</div>
          </div>
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
            <div className="text-[11px] text-[var(--text-tertiary)]">失败</div>
            <div className="mt-1 text-[16px] font-semibold text-[var(--text-primary)]">{summary?.failed ?? 0}</div>
          </div>
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
            <div className="text-[11px] text-[var(--text-tertiary)]">旧/缺失</div>
            <div className="mt-1 text-[16px] font-semibold text-[var(--text-primary)]">{(summary?.stale || 0) + (summary?.missing || 0)}</div>
          </div>
        </div>

        <div className="mb-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Database size={15} className={guardianHealthy ? "text-[var(--positive)]" : "text-[var(--warning)]"} />
            <span className="text-[13px] font-medium text-[var(--text-primary)]">轻量数据保鲜</span>
            <Badge tone={guardianHealthy ? "positive" : guardian?.enabled ? "watch" : "warning"}>
              {guardian?.enabled ? "已启用" : "未启用"}
            </Badge>
            {guardianCalendar ? <Badge tone={guardianCalendar === "trading" ? "info" : "warning"}>{guardianCalendar}</Badge> : null}
            <span className="text-[11px] text-[var(--text-tertiary)]">
              checked {guardian?.last_checked_at || "-"}
            </span>
          </div>
          {guardian?.last_skip_reason ? (
            <div className="mb-3 rounded-md border border-[color-mix(in_srgb,var(--warning)_24%,transparent)] bg-[color-mix(in_srgb,var(--warning)_8%,transparent)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
              {guardian.last_skip_reason}
            </div>
          ) : null}
          <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
            <GuardianDatasetCard title="批量行情" taskName="quotes_light" state={guardian?.quotes_light} />
            <GuardianDatasetCard title="批量资金流" taskName="capital_flow_light" state={guardian?.capital_flow_light} />
          </div>
        </div>

        <div className="space-y-2">
          {visibleJobs.map((job) => {
            const run = job.run || {};
            return (
              <div key={job.task_name || job.name} className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-[13px] font-medium text-[var(--text-primary)]">{job.name || run.title || job.task_name}</div>
                    <div className="mono mt-1 text-[11px] text-[var(--text-tertiary)]">
                      {job.cron_expr || "-"}{job.catchup_enabled ? ` · catch-up 至 ${job.catchup_until || "-"}` : ""}
                    </div>
                  </div>
                  <Badge tone={schedulerHealthTone(job.health)}>{schedulerHealthLabel(job.health)}</Badge>
                </div>
                <div className="mt-2 text-[12px] leading-5 text-[var(--text-secondary)]">
                  {run.finished_at || run.started_at || "今日暂无运行记录"}
                  {run.trade_date ? ` · 数据日 ${run.trade_date}` : ""}
                  {run.skip_reason ? ` · ${run.skip_reason}` : ""}
                </div>
                {job.depends_on?.length ? (
                  <div className="mt-1 text-[11px] text-[var(--text-tertiary)]">依赖：{job.depends_on.join(" / ")}</div>
                ) : null}
              </div>
            );
          })}
          {!visibleJobs.length ? <EmptyState>等待 scheduler 状态。</EmptyState> : null}
        </div>
      </div>
    </Panel>
  );
}

async function previewRunDetail(run: RunItem | undefined, onPreview: PreviewUpdater) {
  const runId = runIdOf(run);
  const metaPath = run?.meta_path;
  if (!runId && !metaPath) {
    return;
  }
  const title = run?.title || run?.task_name || runId || "运行详情";
  const subtitle = runId || metaPath;
  onPreview({
    open: true,
    title,
    subtitle,
    loading: true,
    kind: "run",
  });
  try {
    if (runId) {
      const detail = await api.getRunDetail(runId);
      onPreview({
        open: true,
        title: detail.title || detail.task_name || runId,
        subtitle: runId,
        text: JSON.stringify(detail, null, 2),
        kind: "json",
      });
      return;
    }
    if (metaPath) {
      const payload = await api.preview(metaPath);
      onPreview({
        open: true,
        title: payload.name,
        subtitle: payload.path,
        text: payload.text,
        kind: payload.kind,
        truncated: payload.truncated,
      });
    }
  } catch (error) {
    onPreview({
      open: true,
      title,
      subtitle,
      kind: "run",
      error: error instanceof Error ? error.message : "详情读取失败",
    });
  }
}

async function previewRunLog(run: RunItem | undefined, onPreview: PreviewUpdater) {
  const runId = runIdOf(run);
  const logPath = run?.log_path;
  if (!runId && !logPath) {
    return;
  }
  const title = run?.title || run?.task_name || runId || "运行日志";
  const subtitle = runId || logPath;
  onPreview({
    open: true,
    title,
    subtitle,
    loading: true,
    kind: "log",
  });
  try {
    if (runId) {
      const text = await api.getRunLog(runId);
      onPreview({
        open: true,
        title,
        subtitle: runId,
        text,
        kind: "log",
      });
      return;
    }
    if (logPath) {
      const payload = await api.preview(logPath);
      onPreview({
        open: true,
        title: payload.name,
        subtitle: payload.path,
        text: payload.text,
        kind: payload.kind,
        truncated: payload.truncated,
      });
    }
  } catch (error) {
    onPreview({
      open: true,
      title,
      subtitle,
      kind: "log",
      error: error instanceof Error ? error.message : "日志读取失败",
    });
  }
}

function TaskRunnerPanel({
  tasks,
  feishuAvailable,
  feishuDetail,
  onPreview,
  title = "高级任务",
  eyebrow = "Advanced Tasks",
}: {
  tasks: TaskDefinition[];
  feishuAvailable: boolean;
  feishuDetail: string;
  onPreview: PreviewUpdater;
  title?: string;
  eyebrow?: string;
}) {
  const runTask = useRunTask();
  const [sendToFeishu, setSendToFeishu] = useState<Record<string, boolean>>({});
  const [feedback, setFeedback] = useState("");

  function startTask(task: TaskDefinition) {
    const taskName = taskNameOf(task);
    if (!taskName) {
      setFeedback("任务缺少 task_name。");
      return;
    }
    setFeedback("");
    runTask.mutate(
      { taskName, payload: { send_to_feishu: Boolean(sendToFeishu[taskName]) } },
      {
        onSuccess: (payload) => {
          const parts = [`${payload.title || task.title || taskName} 已启动。`];
          if (payload.feishu_warning) {
            parts.push(payload.feishu_warning);
          } else if (payload.send_to_feishu) {
            parts.push("本次会尝试发送飞书。");
          }
          setFeedback(parts.join(" "));
        },
        onError: (error) => setFeedback(error instanceof Error ? error.message : "任务启动失败"),
      },
    );
  }

  return (
    <Panel title={title} eyebrow={eyebrow}>
      <div className="surface-card p-4">
        <div className="mb-4 rounded-md border border-[color-mix(in_srgb,var(--warning)_24%,transparent)] bg-[color-mix(in_srgb,var(--warning)_8%,transparent)] px-3 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <AlertTriangle size={15} className="text-[var(--warning)]" />
            <span className="text-[12px] font-medium text-[var(--text-primary)]">高级任务区</span>
          </div>
          <p className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
            这些任务会重算候选池或特定时段产物。它们不写真实账本，但不应当和日常安全刷新混用。
          </p>
        </div>
        {feedback ? (
          <div className="mb-4 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
            {feedback}
          </div>
        ) : null}

        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {tasks.map((task, index) => {
            const taskName = taskNameOf(task);
            const lastRun = task.last_run;
            const safety = refreshTaskCopy(taskName);
            return (
              <div key={`${taskName || task.title || index}`} className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-4">
                <div className="mb-3 flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium text-[var(--text-primary)]">{task.title || taskName || "任务"}</div>
                    <div className="mono mt-1 truncate text-[11px] text-[var(--text-tertiary)]">{taskName || task.lane || "task"}</div>
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1">
                    <Badge tone={safety.category === "danger" ? "risk" : "watch"}>{safety.category === "danger" ? "危险" : "高级"}</Badge>
                    <Badge tone={runTone(lastRun?.status)}>{lastRun?.status || "ready"}</Badge>
                  </div>
                </div>
                <p className="mb-4 line-clamp-3 text-[12px] leading-5 text-[var(--text-secondary)]">
                  {task.description || safety.summary || "可由后端任务接口触发。"}
                </p>
                <div className="mb-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2 text-[11px] leading-4 text-[var(--text-tertiary)]">
                  影响范围：{safety.impact}
                </div>
                <label className="mb-3 flex items-center gap-2 text-[12px] text-[var(--text-secondary)]">
                  <input
                    type="checkbox"
                    checked={Boolean(sendToFeishu[taskName])}
                    onChange={(event) =>
                      setSendToFeishu((current) => ({ ...current, [taskName]: event.target.checked }))
                    }
                    disabled={!feishuAvailable}
                    className="h-4 w-4 accent-[var(--info)]"
                  />
                  {feishuAvailable ? "允许发送飞书" : "飞书当前不可用"}
                </label>
                {!feishuAvailable ? (
                  <div className="mb-3 rounded-md border border-[color-mix(in_srgb,var(--warning)_20%,transparent)] bg-[color-mix(in_srgb,var(--warning)_8%,transparent)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
                    {feishuDetail || "飞书通道未配置，本次只能执行任务本体。"}
                  </div>
                ) : null}
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    className="focus-ring prism-btn prism-btn-primary"
                    onClick={() => startTask(task)}
                    disabled={runTask.isPending || !taskName}
                  >
                    {runTask.isPending ? <LoaderCircle size={13} className="animate-spin" /> : <Play size={13} />}
                    运行
                  </button>
                  {lastRun ? (
                    <>
                      <button
                        type="button"
                        className="focus-ring prism-btn prism-btn-secondary"
                        onClick={() => void previewRunDetail(lastRun, onPreview)}
                      >
                        <Eye size={13} />
                        详情
                      </button>
                      <button
                        type="button"
                        className="focus-ring prism-btn prism-btn-secondary"
                        onClick={() => void previewRunLog(lastRun, onPreview)}
                      >
                        <FileJson size={13} />
                        日志
                      </button>
                    </>
                  ) : null}
                </div>
              </div>
            );
          })}
          {!tasks.length ? <EmptyState>暂无任务定义。</EmptyState> : null}
        </div>
      </div>
    </Panel>
  );
}

function RecentRunsPanel({
  runs,
  loading,
  onPreview,
  onRefresh,
}: {
  runs: RunItem[];
  loading?: boolean;
  onPreview: PreviewUpdater;
  onRefresh?: () => void;
}) {
  function runReadableSummary(run: RunItem) {
    if (run.status === "failed" || run.status === "error") {
      return run.summary || "任务失败。先打开日志查看最后一段错误，再决定是否重跑安全刷新。";
    }
    if (run.summary) {
      return run.summary;
    }
    if (run.status === "running") {
      return "后台执行中，请等待运行结束后再复核 readiness。";
    }
    return "可打开详情或日志复核本次运行。";
  }

  return (
    <Panel
      title="最近运行"
      eyebrow="Runs"
      action={
        onRefresh ? (
          <button
            type="button"
            className="focus-ring inline-flex items-center gap-1.5 rounded-md border border-[var(--border-subtle)] px-2 py-1 text-[11px] text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
            onClick={onRefresh}
          >
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
            刷新
          </button>
        ) : null
      }
    >
      <div className="flex flex-col gap-2">
        {runs.slice(0, 8).map((run, index) => {
          const runId = runIdOf(run);
          const hasDetail = Boolean(runId || run.meta_path);
          const hasLog = Boolean(runId || run.log_path);
          return (
            <div key={`${runId || index}`} className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
              <div className="flex items-center justify-between gap-3">
                <span className="truncate text-[13px] text-[var(--text-primary)]">{run.title || run.task_name || runId}</span>
                <Badge tone={runTone(run.status)}>{run.status || "unknown"}</Badge>
              </div>
              <div className="mono mt-1 truncate text-[11px] text-[var(--text-tertiary)]">
                {run.started_at || run.finished_at || runId || "-"}
              </div>
              <div className="mt-1 line-clamp-2 text-[12px] leading-5 text-[var(--text-secondary)]">
                {runReadableSummary(run)}
              </div>
              <div className="mt-2 flex gap-2">
                {hasDetail ? (
                  <button
                    type="button"
                    className="focus-ring prism-btn prism-btn-secondary prism-btn-sm"
                    onClick={() => void previewRunDetail(run, onPreview)}
                  >
                    详情
                  </button>
                ) : null}
                {hasLog ? (
                  <button
                    type="button"
                    className="focus-ring prism-btn prism-btn-secondary prism-btn-sm"
                    onClick={() => void previewRunLog(run, onPreview)}
                  >
                    日志
                  </button>
                ) : null}
              </div>
            </div>
          );
        })}
        {!runs.length ? (
          <EmptyState>{loading ? "正在读取最近运行。" : "暂无运行记录。"}</EmptyState>
        ) : null}
      </div>
    </Panel>
  );
}

function DeferredRecentRunsPanel({
  open,
  loading,
  onOpen,
}: {
  open: boolean;
  loading?: boolean;
  onOpen: () => void;
}) {
  if (open) {
    return null;
  }

  return (
    <Panel title="最近运行" eyebrow="Runs">
      <div className="surface-card p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="text-sm font-medium text-[var(--text-primary)]">
              运行列表按需读取
            </div>
            <div className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
              排障需要查看任务详情或日志时再加载最近运行记录。
            </div>
          </div>
          <button
            type="button"
            className="focus-ring prism-btn prism-btn-secondary"
            onClick={onOpen}
          >
            {loading ? <LoaderCircle size={14} className="animate-spin" /> : <Eye size={14} />}
            查看最近运行
          </button>
        </div>
      </div>
    </Panel>
  );
}

function RefreshPolicyPanel({ status }: { status?: RefreshStatus }) {
  const tasks = Object.values(status?.policy_catalog?.tasks || {});
  const pagePolicy = status?.policy?.page;
  const auto = status?.auto_refresh;
  const blocked = auto?.blocked_reasons || [];
  const reasons = auto?.reason_codes || [];
  const readinessCopy = readinessModeCopy(status?.readiness_mode);
  const topReason = (blocked.length ? blocked : reasons)[0];
  const reasonDetail = topReason ? refreshReasonCopy(topReason).detail : "";

  return (
    <Panel title="自动刷新策略" eyebrow="Refresh Policy">
      <div className="surface-card p-4">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Badge tone={readinessCopy.tone}>{readinessCopy.title}</Badge>
          {status?.recommended_task?.task_name ? (
            <Badge tone={status.recommended_task.kind === "lightweight" ? "info" : "watch"}>
              {status.recommended_task.title || status.recommended_task.task_name}
            </Badge>
          ) : null}
          <Badge tone={auto?.allowed ? "positive" : "watch"}>{auto?.allowed ? "允许自动补刷" : "未自动补刷"}</Badge>
        </div>
        <p className="mb-3 text-[12px] leading-5 text-[var(--text-secondary)]">
          Settings 只被动展示自动刷新策略；打开本页不会触发自动刷新，需在“日常安全刷新”里手动运行任务。
        </p>

        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
            <div className="text-[11px] text-[var(--text-tertiary)]">当前 freshness</div>
            <div className="mt-1 text-[13px] font-medium text-[var(--text-primary)]">
              过期源 {status?.stale_count ?? "-"} · manifest {status?.manifest_stale_count ?? "-"}
            </div>
          </div>
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
            <div className="text-[11px] text-[var(--text-tertiary)]">冷却</div>
            <div className="mt-1 text-[13px] font-medium text-[var(--text-primary)]">
              {formatCooldown(status?.cooldown?.remaining_seconds)}
            </div>
            {status?.cooldown?.next_allowed_at ? (
              <div className="mt-1 text-[11px] text-[var(--text-tertiary)]">{status.cooldown.next_allowed_at}</div>
            ) : null}
          </div>
        </div>

        <div className="mt-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
          <div className="text-[12px] font-medium text-[var(--text-primary)]">策略判断</div>
          <div className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
            {auto?.summary || "等待自动刷新策略判断。"}
          </div>
          {reasonDetail ? (
            <div className="mt-1 text-[12px] leading-5 text-[var(--text-tertiary)]">
              建议：{reasonDetail} {status?.recommended_task?.title ? `优先尝试安全刷新「${status.recommended_task.title}」。` : ""}
            </div>
          ) : null}
          <div className="mt-2 flex flex-wrap gap-1.5">
            {(blocked.length ? blocked : reasons).slice(0, 6).map((reason) => (
              <Badge key={reason} tone={blocked.length ? "warning" : "info"}>
                {refreshReasonLabel(reason)}
              </Badge>
            ))}
          </div>
        </div>

        <div className="mt-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
          <div className="text-[12px] font-medium text-[var(--text-primary)]">Today 页策略</div>
          <div className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
            自动打开：{pagePolicy?.auto_on_open ? "开启" : "关闭"} · 轮询 {pagePolicy?.poll_seconds?.trading || "-"}s · 允许任务 {(pagePolicy?.allowed_tasks || []).map((task) => refreshTaskCopy(task).title).join(" / ") || "-"}
          </div>
        </div>

        {status?.last_auto_refresh ? (
          <div className="mt-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
            <div className="text-[12px] font-medium text-[var(--text-primary)]">最近自动刷新原因</div>
            <div className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
              {status.last_auto_refresh.ts || "-"} · {status.last_auto_refresh.task_name || "-"} · {status.last_auto_refresh.reason || "-"}
            </div>
          </div>
        ) : null}

        {tasks.length ? (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {tasks.map((task) => (
              <Badge key={task.task_name || task.title} tone={task.kind === "lightweight" ? "info" : "watch"}>
                {task.title || task.task_name}: {formatCooldown(task.cooldown_seconds)}
              </Badge>
            ))}
          </div>
        ) : null}
      </div>
    </Panel>
  );
}

function captureStatusTone(status?: string) {
  if (status === "success") {
    return "positive" as const;
  }
  if (status === "failed") {
    return "risk" as const;
  }
  return "info" as const;
}

function learningActionLabel(action?: string) {
  if (action === "fix_data_pipeline") {
    return "修数据链路";
  }
  if (action === "fix_execution_pipeline") {
    return "修执行链路";
  }
  if (action === "review_rule_threshold") {
    return "复核规则阈值";
  }
  return action || "复核";
}

function DecisionLedgerHealthPanel({ enabled }: { enabled: boolean }) {
  const ledger = useDecisionLedgerHealth(enabled);
  const data = ledger.data as DecisionLedgerHealthResponse | undefined;

  const capture = data?.last_capture;
  const outcome = data?.last_outcome_evaluation;
  const corrupt = data?.corrupt_files || [];
  const statusErrors = data?.status_errors || [];
  const storage = data?.storage;
  const learning = data?.learning_loop;
  const suggestions = (learning?.suggestions || []).slice(0, 2);

  return (
    <Panel
      title="Decision Ledger 健康"
      eyebrow="Ledger"
      action={
        <button
          type="button"
          className="focus-ring inline-flex items-center gap-1.5 rounded-md border border-[var(--border-subtle)] px-2 py-1 text-[11px] text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
          onClick={() => void ledger.refetch()}
        >
          <RefreshCw size={12} className={ledger.isFetching ? "animate-spin" : ""} />
          刷新
        </button>
      }
    >
      <div className="surface-card p-4">
        {ledger.isError ? (
          <ErrorState message="Decision Ledger 健康暂不可用" onRetry={() => void ledger.refetch()} />
        ) : !data ? (
          <EmptyState>等待 Decision Ledger 健康数据。</EmptyState>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <MetricCard label="决策总数" value={data.decisions_total} tone="info" />
              <MetricCard label="进行中" value={data.decisions_open} tone="info" />
              <MetricCard label="已替代" value={data.decisions_superseded} tone="warning" />
              <MetricCard label="待评估" value={data.pending_outcomes} tone={data.pending_outcomes > 0 ? "warning" : "info"} />
            </div>

            <div className="mt-4 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
              <div className="flex flex-wrap items-center gap-2">
                <div className="text-[12px] font-medium text-[var(--text-primary)]">最近一次 capture</div>
                <Badge tone={captureStatusTone(capture?.status)}>{capture?.status || "未运行"}</Badge>
              </div>
              <div className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
                {capture
                  ? `${capture.recorded_at || "-"} · 任务 ${capture.task_name || "-"} · 新增 ${capture.captured ?? 0} · 已存在 ${capture.already_present ?? 0} · 已替代 ${capture.superseded ?? 0}`
                  : "scheduler 尚未执行 Decision Ledger capture 任务。"}
              </div>
              {capture?.status === "failed" && capture.error ? (
                <div className="mt-1 text-[11px] text-[var(--text-warn)]">{capture.error}</div>
              ) : null}
            </div>

            <div className="mt-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
              <div className="flex flex-wrap items-center gap-2">
                <div className="text-[12px] font-medium text-[var(--text-primary)]">最近一次 outcome 评估</div>
                <Badge tone={captureStatusTone(outcome?.status)}>{outcome?.status || "未运行"}</Badge>
              </div>
              <div className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
                {outcome
                  ? `${outcome.recorded_at || "-"} · provider ${outcome.provider || "-"} · 新增 ${outcome.evaluated ?? 0} · 复用 ${outcome.already_present ?? 0} · 数据缺失 ${outcome.data_issue ?? 0}`
                  : "尚未运行 evaluate_decision_ledger.py。"}
              </div>
              {outcome?.status === "failed" && outcome.error ? (
                <div className="mt-1 text-[11px] text-[var(--text-warn)]">{outcome.error}</div>
              ) : null}
              {outcome && (outcome.skipped_no_provider ?? 0) > 0 ? (
                <div className="mt-1 text-[11px] text-[var(--text-tertiary)]">
                  缺少 price provider 时跳过 {outcome.skipped_no_provider} 项；下次接入 provider 后会重新评估。
                </div>
              ) : null}
            </div>

            <div className="mt-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
              <div className="flex flex-wrap items-center gap-2">
                <div className="text-[12px] font-medium text-[var(--text-primary)]">规则学习闭环</div>
                <Badge tone={(learning?.pending_review_count || 0) > 0 ? "warning" : "positive"}>
                  待复盘 {learning?.pending_review_count ?? 0}
                </Badge>
                <Badge tone="info">成熟样本 {learning?.mature_samples ?? 0}</Badge>
              </div>
              <div className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
                {learning
                  ? `${learning.version || "-"} · 样本 ${learning.samples_total ?? 0} · 规则版本 ${(learning.ruleset_versions || []).join(", ") || "-"}`
                  : "等待 Decision Ledger learning loop 数据。"}
              </div>
              {suggestions.length ? (
                <div className="mt-2 grid gap-2 md:grid-cols-2">
                  {suggestions.map((suggestion) => (
                    <div
                      key={`${suggestion.ruleset_version}-${suggestion.lane}-${suggestion.action}-${suggestion.suggested_action}`}
                      className="rounded border border-[var(--border-warn)] bg-[var(--surface-warn)] px-2 py-1.5 text-[11px]"
                    >
                      <div className="font-medium text-[var(--text-warn)]">
                        {learningActionLabel(suggestion.suggested_action)}
                      </div>
                      <div className="mt-0.5 text-[var(--text-secondary)]">
                        {suggestion.lane}/{suggestion.action} · {suggestion.reason}
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>

            {storage ? (
              <div className="mt-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
                <div className="flex flex-wrap items-center gap-2">
                  <div className="text-[12px] font-medium text-[var(--text-primary)]">Ledger 存储</div>
                  <Badge tone="info">{storage.mode || "runtime_primary_legacy_read"}</Badge>
                  <Badge tone={storage.legacy_exists ? "warning" : "info"}>legacy {storage.legacy_decision_files ?? 0}</Badge>
                </div>
                <div className="mt-1 grid gap-1 text-[11px] text-[var(--text-tertiary)]">
                  <div className="truncate">writes_to: {storage.writes_to || "-"}</div>
                  <div className="truncate">primary: {storage.primary_root || "-"} ({storage.primary_decision_files ?? 0})</div>
                </div>
              </div>
            ) : null}

            {corrupt.length ? (
              <div className="mt-3 rounded-md border border-[var(--border-warn)] bg-[var(--surface-warn)] px-3 py-2 text-[11px] text-[var(--text-warn)]">
                <div className="font-medium">Decisions 文件损坏 ({corrupt.length})</div>
                <ul className="mt-1 space-y-0.5">
                  {corrupt.slice(0, 3).map((err, index) => (
                    <li key={index} className="truncate">
                      {err.file}: {err.error}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {statusErrors.length ? (
              <div className="mt-3 rounded-md border border-[var(--border-warn)] bg-[var(--surface-warn)] px-3 py-2 text-[11px] text-[var(--text-warn)]">
                <div className="font-medium">Status 文件解析失败 ({statusErrors.length})</div>
                <ul className="mt-1 space-y-0.5">
                  {statusErrors.slice(0, 3).map((err, index) => (
                    <li key={index} className="truncate">
                      {err.kind}: {err.error}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </>
        )}
      </div>
    </Panel>
  );
}


export interface SettingsDiagnosticsMainProps {
  status?: RefreshStatus;
  onPreview: PreviewUpdater;
}

export function SettingsDiagnosticsMain({ status, onPreview }: SettingsDiagnosticsMainProps) {
  const [recentRunsOpen, setRecentRunsOpen] = useState(false);
  const runs = useRuns({ enabled: recentRunsOpen });
  const [formalDataDetailOpen, setFormalDataDetailOpen] = useState(false);
  const formalData = useFormalDataStatus({ compact: !formalDataDetailOpen, enabled: true });
  const [dataAssetsDetailOpen, setDataAssetsDetailOpen] = useState(false);
  const dataAssets = useDataAssetsStatus({ compact: !dataAssetsDetailOpen, enabled: true });

  return (
    <>
      <DataAssetsPanel
        status={dataAssets.data}
        loading={dataAssets.isLoading || dataAssets.isFetching}
        onRefresh={() => void dataAssets.refetch()}
        detailOpen={dataAssetsDetailOpen}
        onToggleDetail={() => setDataAssetsDetailOpen((open) => !open)}
      />
      <FormalDataPanel
        status={formalData.data}
        loading={formalData.isLoading || formalData.isFetching}
        onRefresh={() => void formalData.refetch()}
        detailOpen={formalDataDetailOpen}
        onToggleDetail={() => setFormalDataDetailOpen((open) => !open)}
      />
      <SchedulerStatusPanel status={status} />
      <RefreshPolicyPanel status={status} />
      <DeferredRecentRunsPanel
        open={recentRunsOpen}
        loading={runs.isLoading || runs.isFetching}
        onOpen={() => setRecentRunsOpen(true)}
      />
      {recentRunsOpen ? (
        <RecentRunsPanel
          runs={runs.data?.runs || []}
          loading={runs.isLoading || runs.isFetching}
          onPreview={onPreview}
          onRefresh={() => void runs.refetch()}
        />
      ) : null}
    </>
  );
}

export interface SettingsDiagnosticsAsideProps {
  tasks: TaskDefinition[];
  feishuAvailable: boolean;
  feishuDetail: string;
  onPreview: PreviewUpdater;
  showAdvancedTasks?: boolean;
  showLedger?: boolean;
}

export function SettingsDiagnosticsAside({
  tasks,
  feishuAvailable,
  feishuDetail,
  onPreview,
  showAdvancedTasks = false,
  showLedger = false,
}: SettingsDiagnosticsAsideProps) {
  if (!showAdvancedTasks && !showLedger) {
    return null;
  }

  return (
    <>
      {showAdvancedTasks ? (
        <TaskRunnerPanel
          tasks={tasks}
          feishuAvailable={feishuAvailable}
          feishuDetail={feishuDetail}
          onPreview={onPreview}
        />
      ) : null}
      {showLedger ? <DecisionLedgerHealthPanel enabled={showLedger} /> : null}
    </>
  );
}
