"use client";

import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Database,
  Eye,
  FileJson,
  KeyRound,
  LoaderCircle,
  Play,
  RefreshCw,
  RotateCcw,
  Save,
  Settings,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/badge";
import { EmptyState, ErrorState, Panel } from "@/components/data-card";
import { MetricCard } from "@/components/metric-card";
import { PageTitle } from "@/components/page-title";
import { PreviewDrawer, type PreviewDrawerState } from "@/components/preview-drawer";
import { ThemeToggle } from "@/components/theme-toggle";
import { api, ApiError } from "@/lib/api";
import {
  useDecisionLedgerHealth,
  useDataAssetsStatus,
  useFormalDataStatus,
  useHealth,
  useOverview,
  useParameters,
  useRefreshStatus,
  useRunTask,
  useRuns,
  useSaveParameters,
  useTriggerRefresh,
} from "@/lib/hooks";
import {
  formatCooldown,
  normalizeTaskName,
  readinessModeCopy,
  readinessNextStep,
  refreshReasonCopy,
  refreshReasonLabel,
  refreshTaskCopy,
} from "@/lib/readiness-copy";
import type {
  DecisionLedgerHealthResponse,
  DataAssetsStatus,
  FormalDataStatus,
  FreshnessGuardianDatasetState,
  ParametersResponse,
  RefreshStatus,
  ReadinessSourceFreshness,
  RunItem,
  TaskDefinition,
} from "@/lib/types";

function runIdOf(run?: RunItem) {
  return String(run?.run_id || run?.task_id || "").trim();
}

function taskNameOf(task: TaskDefinition) {
  return String(task.task_name || task.name || "").trim();
}

function runTone(status?: string) {
  if (status === "completed" || status === "success") {
    return "positive";
  }
  if (status === "failed" || status === "error") {
    return "risk";
  }
  if (status === "running") {
    return "watch";
  }
  return "info";
}

function taskCategory(task: TaskDefinition) {
  return refreshTaskCopy(taskNameOf(task)).category;
}

function safeTaskList(tasks: TaskDefinition[]) {
  return tasks.filter((task) => taskCategory(task) === "safe");
}

function advancedTaskList(tasks: TaskDefinition[]) {
  return tasks.filter((task) => taskCategory(task) !== "safe");
}

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

function ParametersEditor() {
  const parameters = useParameters();
  const saveParameters = useSaveParameters();
  const [raw, setRaw] = useState("");
  const [dirty, setDirty] = useState(false);
  const [localError, setLocalError] = useState("");
  const [success, setSuccess] = useState("");
  const [evaluation, setEvaluation] = useState<ParametersResponse["evaluation"]>(undefined);
  const [editorOpen, setEditorOpen] = useState(false);
  const [unsafeAcknowledged, setUnsafeAcknowledged] = useState(false);
  const [unsafeConfirm, setUnsafeConfirm] = useState("");
  const unsafeReady = unsafeAcknowledged && unsafeConfirm.trim() === "UNSAFE_APPLY";

  useEffect(() => {
    if (parameters.data?.raw && !dirty) {
      setRaw(parameters.data.raw);
    }
  }, [dirty, parameters.data?.raw]);

  const parsedSummary = useMemo(() => {
    try {
      const parsed = JSON.parse(raw || "{}") as Record<string, unknown>;
      return {
        ok: true,
        stocks: Array.isArray(parsed.stocks) ? parsed.stocks.length : 0,
        keys: Object.keys(parsed).length,
      };
    } catch {
      return { ok: false, stocks: 0, keys: 0 };
    }
  }, [raw]);

  function formatJson() {
    setLocalError("");
    setEvaluation(undefined);
    try {
      setRaw(JSON.stringify(JSON.parse(raw), null, 2));
      setDirty(true);
    } catch (error) {
      setLocalError(error instanceof Error ? error.message : "JSON 格式错误");
    }
  }

  function reloadFromDisk() {
    setLocalError("");
    setSuccess("");
    setEvaluation(undefined);
    parameters.refetch().then((result) => {
      if (result.data?.raw) {
        setRaw(result.data.raw);
        setDirty(false);
      }
    });
  }

  function save(unsafeApply = false): void {
    setLocalError("");
    setSuccess("");
    setEvaluation(undefined);
    if (unsafeApply && !unsafeReady) {
      setLocalError("强制保存前需要勾选确认，并输入 UNSAFE_APPLY。");
      return;
    }
    try {
      JSON.parse(raw);
    } catch (error) {
      setLocalError(error instanceof Error ? error.message : "JSON 格式错误");
      return;
    }
    saveParameters.mutate(
      { payload: { raw }, unsafeApply },
      {
        onSuccess: (payload) => {
          if (payload.evaluation) {
            setEvaluation(payload.evaluation);
          }
          setRaw(payload.raw);
          setDirty(false);
          setUnsafeAcknowledged(false);
          setUnsafeConfirm("");
          setSuccess("参数已保存到磁盘。");
        },
        onError: (error) => {
          setLocalError(error instanceof Error ? error.message : "保存失败");
          // The 400 response body still carries `evaluation` — surface it so the
          // user can see the rule that blocked them and use 强制保存 if needed.
          if (error instanceof ApiError && error.payload && typeof error.payload === "object") {
            const payload = error.payload as { evaluation?: ParametersResponse["evaluation"] };
            if (payload.evaluation) {
              setEvaluation(payload.evaluation);
            }
          }
        },
      },
    );
  }

  return (
    <Panel
      title="参数编辑"
      eyebrow="Advanced / Dangerous"
      action={
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="focus-ring prism-btn prism-btn-secondary"
            onClick={reloadFromDisk}
            disabled={parameters.isFetching || !editorOpen}
          >
            <RotateCcw size={13} className={parameters.isFetching ? "animate-spin" : ""} />
            重载
          </button>
          <button
            type="button"
            className="focus-ring prism-btn prism-btn-primary"
            onClick={() => save()}
            disabled={saveParameters.isPending || !raw.trim() || !editorOpen}
          >
            {saveParameters.isPending ? <LoaderCircle size={13} className="animate-spin" /> : <Save size={13} />}
            保存
          </button>
        </div>
      }
    >
      {parameters.isError ? <ErrorState message="参数接口暂不可用" onRetry={() => void parameters.refetch()} /> : null}

      <details
        className="surface-card p-4"
        open={editorOpen}
        onToggle={(event) => setEditorOpen(event.currentTarget.open)}
      >
        <summary className="cursor-pointer list-none">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="mb-1 flex flex-wrap items-center gap-2">
                <Badge tone="risk">危险操作隔离</Badge>
                <Badge tone="warning">写入配置文件</Badge>
              </div>
              <div className="text-[13px] font-medium text-[var(--text-primary)]">参数编辑默认收起</div>
              <p className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
                普通保存会写入自选股参数文件；强制保存会绕过评估硬拦截，可能影响后续刷新产物和 readiness。
              </p>
            </div>
            <span className="focus-ring inline-flex items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-1.5 text-[12px] text-[var(--text-secondary)]">
              {editorOpen ? "收起" : "展开参数编辑"}
              <ChevronRight size={13} className={editorOpen ? "rotate-90" : ""} />
            </span>
          </div>
        </summary>
        <div className="mt-4">
        <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {(parameters.data?.summary_cards || []).map((card) => (
            <MetricCard key={card.label} {...card} tone={card.tone || "info"} />
          ))}
          {!parameters.data?.summary_cards?.length ? (
            <>
              <MetricCard label="JSON" value={parsedSummary.ok ? "有效" : "错误"} detail={`${parsedSummary.keys} 个键`} tone={parsedSummary.ok ? "positive" : "risk"} />
              <MetricCard label="stocks" value={parsedSummary.stocks} detail="本地解析" tone="info" />
            </>
          ) : null}
        </div>

        <div className="mb-4 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3">
          <div className="mb-2 text-[12px] font-medium text-[var(--text-primary)]">读写文件</div>
          <div className="mono break-all text-[11px] leading-5 text-[var(--text-tertiary)]">
            {parameters.data?.path || "等待 /api/parameters"}
          </div>
          {parameters.data?.updated_at ? (
            <div className="mt-2 text-[12px] text-[var(--text-tertiary)]">磁盘更新时间：{parameters.data.updated_at}</div>
          ) : null}
        </div>

        <div className="mb-4 flex flex-wrap gap-2">
          {(parameters.data?.required_groups || []).map((item) => (
            <Badge key={item.key} tone={item.ok ? "positive" : "risk"}>
              {item.label} {item.ok ? "OK" : "缺失"}
            </Badge>
          ))}
        </div>

        <div className="overflow-hidden rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border-subtle)] px-3 py-2">
            <div className="flex items-center gap-2 text-[12px] text-[var(--text-tertiary)]">
              <FileJson size={14} />
              原始 JSON
              {dirty ? <Badge tone="watch">未保存</Badge> : <Badge tone="positive">已同步</Badge>}
            </div>
            <button
              type="button"
              className="focus-ring prism-btn prism-btn-secondary prism-btn-sm"
              onClick={formatJson}
            >
              格式化
            </button>
          </div>
          <textarea
            value={raw}
            onChange={(event) => {
              setRaw(event.target.value);
              setDirty(true);
              setLocalError("");
              setSuccess("");
              // Drop any stale evaluation banner — the user is editing now,
              // and the previous evaluation no longer reflects current input.
              setEvaluation(undefined);
            }}
            spellCheck={false}
            className="mono h-[480px] w-full resize-y bg-transparent px-4 py-3 text-[12px] leading-6 text-[var(--text-secondary)] outline-none placeholder:text-[var(--text-tertiary)]"
            placeholder="等待参数文件加载..."
          />
        </div>

        {localError || saveParameters.isError ? (
          <div className="mt-3 rounded-md border border-[color-mix(in_srgb,var(--negative)_20%,transparent)] bg-[color-mix(in_srgb,var(--negative)_8%,transparent)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
            {localError || saveParameters.error?.message || "保存失败"}
          </div>
        ) : null}
        {success ? (
          <div className="mt-3 rounded-md border border-[color-mix(in_srgb,var(--positive)_20%,transparent)] bg-[color-mix(in_srgb,var(--positive)_8%,transparent)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
            {success}
          </div>
        ) : null}
        {evaluation && evaluation.errors.length > 0 ? (
          <div className="mt-3 rounded-md border border-[color-mix(in_srgb,var(--negative)_20%,transparent)] bg-[color-mix(in_srgb,var(--negative)_8%,transparent)] px-3 py-2">
            <div className="mb-1 flex flex-wrap items-center gap-2 text-[12px] font-medium text-[var(--text-primary)]">
              <AlertTriangle size={14} className="text-[var(--negative)]" />
              评估拦截（硬错误）
              <Badge tone="risk">unsafe_apply</Badge>
            </div>
            <ul className="list-disc space-y-0.5 pl-4 text-[12px] text-[var(--text-secondary)]">
              {evaluation.errors.map((err, i) => <li key={i}>{err}</li>)}
            </ul>
            <div className="mt-3 rounded-md border border-[color-mix(in_srgb,var(--negative)_24%,transparent)] bg-[var(--bg-secondary)] px-3 py-2">
              <div className="text-[12px] font-medium text-[var(--text-primary)]">影响范围</div>
              <p className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
                强制保存会把当前 JSON 写入参数文件，并让后续刷新任务使用这份配置；它不会自动下单、不会写真实账本，但可能让数据链路产物失真。
              </p>
              <label className="mt-3 flex items-start gap-2 text-[12px] leading-5 text-[var(--text-secondary)]">
                <input
                  type="checkbox"
                  checked={unsafeAcknowledged}
                  onChange={(event) => setUnsafeAcknowledged(event.target.checked)}
                  className="mt-0.5 h-4 w-4 accent-[var(--negative)]"
                />
                我确认这是一次有意的危险操作，并已理解它会影响后续刷新结果。
              </label>
              <input
                value={unsafeConfirm}
                onChange={(event) => setUnsafeConfirm(event.target.value)}
                className="focus-ring mono mt-2 w-full rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2 text-[12px] text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)]"
                placeholder="输入 UNSAFE_APPLY 以启用强制保存"
              />
            </div>
            <button
              type="button"
              className="focus-ring prism-btn prism-btn-danger mt-2"
              onClick={() => save(true)}
              disabled={saveParameters.isPending || !unsafeReady}
            >
              强制保存（unsafe apply）
            </button>
          </div>
        ) : null}
        {evaluation && evaluation.warnings.length > 0 ? (
          <div className="mt-3 rounded-md border border-[color-mix(in_srgb,var(--watch-color,var(--warning)_40%,transparent))] bg-[color-mix(in_srgb,var(--watch-color,var(--warning)_8%,transparent))] px-3 py-2">
            <div className="mb-1 text-[12px] font-medium text-[var(--text-primary)]">评估警告</div>
            <ul className="list-disc space-y-0.5 pl-4 text-[12px] text-[var(--text-secondary)]">
              {evaluation.warnings.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
          </div>
        ) : null}
        </div>
      </details>
    </Panel>
  );
}

function readinessStateTone(state?: string): "positive" | "info" | "watch" | "warning" | "risk" {
  switch ((state || "").toUpperCase()) {
    case "FRESH":
      return "positive";
    case "USABLE":
      return "info";
    case "STALE":
      return "watch";
    case "DEGRADED":
      return "warning";
    case "INVALID":
    case "BLOCKED":
      return "risk";
    default:
      return "info";
  }
}

function readinessStateLabel(state?: string): string {
  switch ((state || "").toUpperCase()) {
    case "FRESH":
      return "新鲜";
    case "USABLE":
      return "可用";
    case "STALE":
      return "过期";
    case "DEGRADED":
      return "降级";
    case "INVALID":
      return "无效";
    case "BLOCKED":
      return "阻塞";
    default:
      return state || "-";
  }
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
const POLICY_ONLY_REASONS = new Set(["live_small_not_allowed", "fallback_not_allowed", "formal_not_allowed"]);

function datasetReasonSet(row: ReadinessSourceFreshness) {
  return new Set((row.stale_reasons || []).map((reason) => String(reason || "").trim()).filter(Boolean));
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

function datasetIssueKind(row: ReadinessSourceFreshness, state?: string): "hard" | "optional" | "stale" | "policy" | "ok" {
  const normalizedState = String(state || "").toUpperCase();
  const reasons = datasetReasonSet(row);
  if (!row.available || normalizedState === "INVALID" || datasetHasAny(reasons, HARD_DATA_REASONS)) {
    if (datasetIsAuxiliary(row)) return "optional";
    return "hard";
  }
  if (datasetHasAny(reasons, STALE_DATA_REASONS) || normalizedState === "STALE") {
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

function datasetIssueTone(row: ReadinessSourceFreshness, state?: string): "positive" | "info" | "watch" | "warning" | "risk" {
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

function datasetIssueLabel(row: ReadinessSourceFreshness, state?: string): string {
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
  if (row.decision_scope === "live_small") return row.live_small_allowed ? "可进实盘链路" : "不进实盘";
  if (row.source_lane === "reference") return "参考数据";
  if (row.source_lane === "authoritative_daily") return "正式日频";
  return null;
}

function DatasetFreshnessPanel({ status }: { status?: RefreshStatus }) {
  const readiness = status?.readiness;
  const datasets = readiness?.dataset_freshness || [];
  const datasetStates = readiness?.dataset_states || {};
  const capabilities = readiness?.capabilities || {};
  const [expanded, setExpanded] = useState(false);

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
    const severity = { risk: 0, warning: 1, watch: 2, info: 3, positive: 4 } as const;
    return severity[aTone] - severity[bTone];
  });

  const visible = expanded ? sorted : sorted.slice(0, 4);
  const hardIssueCount = sorted.filter((row) => datasetIssueKind(row, datasetStates[row.key]) === "hard").length;
  const optionalIssueCount = sorted.filter((row) => datasetIssueKind(row, datasetStates[row.key]) === "optional").length;
  const staleIssueCount = sorted.filter((row) => datasetIssueKind(row, datasetStates[row.key]) === "stale").length;
  const policyIssueCount = sorted.filter((row) => datasetIssueKind(row, datasetStates[row.key]) === "policy").length;
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
        <span className="text-[13px] font-medium text-[var(--text-primary)]">能力闸门数据依赖</span>
        <span className="text-[11px] text-[var(--text-tertiary)]">
          {datasets.length} 项 · {hardIssueCount ? `${hardIssueCount} 项真不可用` : "无真故障"}
          {optionalIssueCount ? ` · ${optionalIssueCount} 项辅助受限` : ""}
          {staleIssueCount ? ` · ${staleIssueCount} 项偏旧` : ""}
          {policyIssueCount ? ` · ${policyIssueCount} 项仅限复盘/观察` : ""}
        </span>
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="ml-auto rounded border border-[var(--border-subtle)] px-2 py-0.5 text-[11px] text-[var(--text-secondary)] hover:bg-[var(--bg-primary)]"
        >
          {expanded ? "收起" : "展开全部"}
        </button>
      </div>
      <p className="text-[12px] leading-5 text-[var(--text-secondary)]">
        这里不是“正式数据源是否崩了”的总览，而是能力闸门看到的底层依赖。红色才代表数据本身不可用/错日/缺证明；黄色通常表示可观察、可复盘，但不能直接作为真钱审批或交易依据。
      </p>

      <div className="mt-3 flex flex-wrap gap-1.5">
        <Badge tone={reviewGranted ? "positive" : "risk"}>复盘{reviewGranted ? "可用" : "受限"}</Badge>
        <Badge tone={approveGranted ? "positive" : "warning"}>审批{approveGranted ? "可用" : "未放行"}</Badge>
        <Badge tone={tradeGranted ? "positive" : "warning"}>交易{tradeGranted ? "可用" : "未放行"}</Badge>
      </div>

      {dataBlockedCapabilities.length ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {dataBlockedCapabilities.map(({ key, report }) => (
            <Badge key={key} tone={report.status === "blocked" ? "risk" : "warning"}>
              {CAPABILITY_LABELS[key] || key}: {(report.blocking_sources || []).slice(0, 2).join(", ") || "未知"}
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
              style={isBlocking ? { borderColor: "color-mix(in_srgb,var(--warning) 60%, transparent)" } : undefined}
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[12px] font-medium text-[var(--text-primary)]">{row.label || row.key}</span>
                <Badge tone={tone}>{datasetIssueLabel(row, state)}</Badge>
                {scopeLabel ? <Badge tone="info">{scopeLabel}</Badge> : null}
                {isBlocking ? <Badge tone={tone === "risk" ? "risk" : "warning"}>影响放行</Badge> : null}
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
    </div>
  );
}

function ReadinessStatusPanel({ status }: { status?: RefreshStatus }) {
  const readiness = status?.readiness;
  const copy = readinessModeCopy(readiness?.readiness_mode);
  const next = readinessNextStep(readiness, status);
  const Icon = readiness?.readiness_mode === "live_ready" ? ShieldCheck : ShieldAlert;
  const staleReasons = (readiness?.source_freshness || [])
    .flatMap((source) => (source.stale_reasons || []).map((reason) => ({ reason, source: source.label })))
    .slice(0, 8);
  const formalBlockers = readiness?.formal_blockers || [];
  const formalSources = (readiness?.source_freshness || [])
    .filter((source) => source.manifest_path)
    .slice(0, 4);
  const account = readiness?.account_state;

  return (
    <Panel title="今日数据状态 / 交易可用性" eyebrow="Readiness">
      <div className="surface-card p-4">
        <div className="rounded-md border px-4 py-3" style={{ background: copy.bg, borderColor: copy.border }}>
          <div className="flex flex-wrap items-start gap-3">
            <Icon size={20} style={{ color: copy.iconColor, marginTop: 2 }} />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={copy.tone}>{copy.badge}</Badge>
                <Badge tone={readiness?.ready ? "positive" : "risk"}>{copy.realMoney}</Badge>
                {readiness?.session?.label ? <Badge tone={readiness.session.is_trading_day ? "info" : "warning"}>{readiness.session.label}</Badge> : null}
              </div>
              <h2 className="mt-2 text-[16px] font-semibold text-[var(--text-primary)]">{copy.title}</h2>
              <p className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">{copy.detail}</p>
            </div>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard label="预期交易日" value={readiness?.expected_trade_date || "-"} detail="页面应使用的日期" tone="info" />
          <MetricCard
            label="数据交易日"
            value={readiness?.data_trade_date || "-"}
            detail={readiness?.data_trade_date === readiness?.expected_trade_date ? "已对齐" : "需要复核"}
            tone={readiness?.data_trade_date === readiness?.expected_trade_date ? "positive" : "warning"}
          />
          <MetricCard label="过期源" value={String(readiness?.stale_count ?? status?.stale_count ?? "-")} detail="核心来源 stale 数" tone={(readiness?.stale_count || status?.stale_count) ? "warning" : "positive"} />
          <MetricCard label="账户模式" value={account?.mode_label || "-"} detail={account?.ready_for_live_small ? "live_small 已通过" : "未放行真钱"} tone={account?.ready_for_live_small ? "positive" : "watch"} />
        </div>

        <div className="mt-4 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <Database size={15} className={readiness?.formal_ready ? "text-[var(--positive)]" : "text-[var(--warning)]"} />
            <span className="text-[13px] font-medium text-[var(--text-primary)]">正式数据口径</span>
            <Badge tone={readiness?.formal_ready ? "positive" : "watch"}>
              {readiness?.formal_ready ? "正式口径通过" : "快源可用 / 正式口径未接入"}
            </Badge>
          </div>
          <p className="text-[12px] leading-5 text-[var(--text-secondary)]">
            当前快源用于看盘、复核和影子推演；正式放行需要日线、复权、benchmark 和执行约束等目标源全部通过。
          </p>
          {formalSources.length ? (
            <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
              {formalSources.map((source) => (
                <div key={source.key} className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[12px] font-medium text-[var(--text-primary)]">{source.label}</span>
                    <Badge tone={source.formal_decision_allowed ? "positive" : "watch"}>
                      {source.formal_decision_allowed ? "formal" : formatAuthorityLabel(source.decision_scope)}
                    </Badge>
                  </div>
                  <div className="mt-1 text-[11px] leading-5 text-[var(--text-tertiary)]">
                    {formatAuthorityLabel(source.source_lane)} · 当前 {source.provider || "-"} · 目标 {source.target_authority_provider || source.authority_provider || "-"}
                  </div>
                </div>
              ))}
            </div>
          ) : null}
          {formalBlockers.length ? (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {formalBlockers.slice(0, 6).map((item) => (
                <Badge key={item.code} tone="warning">{item.label}</Badge>
              ))}
            </div>
          ) : null}
        </div>

        <div className="mt-4 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <CheckCircle2 size={15} className="text-[var(--positive)]" />
            <span className="text-[13px] font-medium text-[var(--text-primary)]">推荐下一步</span>
            {next.taskName ? <Badge tone={refreshTaskCopy(next.taskName).category === "safe" ? "info" : "watch"}>{next.taskTitle || next.taskName}</Badge> : null}
          </div>
          <div className="text-[13px] font-medium text-[var(--text-primary)]">{next.title}</div>
          <p className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">{next.detail}</p>
        </div>

        {staleReasons.length ? (
          <div className="mt-4 rounded-md border border-[color-mix(in_srgb,var(--warning)_24%,transparent)] bg-[color-mix(in_srgb,var(--warning)_8%,transparent)] px-3 py-3">
            <div className="mb-2 text-[12px] font-medium text-[var(--text-primary)]">为什么不可作为真钱依据</div>
            <div className="flex flex-wrap gap-1.5">
              {staleReasons.map((item, index) => {
                const reason = refreshReasonCopy(item.reason);
                return (
                  <Badge key={`${item.source}-${item.reason}-${index}`} tone="warning">
                    {item.source}: {reason.label}
                  </Badge>
                );
              })}
            </div>
          </div>
        ) : null}

        <DatasetFreshnessPanel status={status} />
      </div>
    </Panel>
  );
}

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

function DataAssetsPanel({
  status,
  loading,
  onRefresh,
}: {
  status?: DataAssetsStatus;
  loading?: boolean;
  onRefresh: () => void;
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
            </div>
            <h3 className="text-[16px] font-semibold text-[var(--text-primary)]">一天授权已经沉淀成可查询资产</h3>
            <p className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
              覆盖 {formatAssetCount(summary?.universe_count)} 只、{formatAssetCount(summary?.trade_days)} 个交易日；每个资产都标明用途、排序权限和真钱闸门边界。
            </p>
          </div>
          <button type="button" className="focus-ring prism-btn prism-btn-secondary" onClick={onRefresh}>
            <RotateCcw size={13} className={loading ? "animate-spin" : ""} />
            重新检查
          </button>
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
}: {
  status?: FormalDataStatus;
  loading?: boolean;
  onRefresh: () => void;
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

function formatDuration(seconds?: number) {
  const value = Math.max(0, Math.round(Number(seconds || 0)));
  if (!value) {
    return "约 1 分钟";
  }
  if (value < 60) {
    return `约 ${value} 秒`;
  }
  const minutes = Math.round(value / 60);
  return `约 ${minutes} 分钟`;
}

function SafeRefreshPanel({
  status,
  tasks,
}: {
  status?: RefreshStatus;
  tasks: TaskDefinition[];
}) {
  const trigger = useTriggerRefresh("today");
  const [feedback, setFeedback] = useState("");
  const allRecoverySteps = status?.recovery_steps || [];
  const advancedRecoveryCount = allRecoverySteps.filter((step) => refreshTaskCopy(step.task_name).category !== "safe").length;
  const fallbackRows = safeTaskList(tasks).map((task, index) => {
    const taskName = taskNameOf(task);
    const copy = refreshTaskCopy(taskName);
    return {
      step: index + 1,
      task_name: normalizeTaskName(taskName),
      title: task.title || copy.title,
      status: task.last_run?.status === "running" ? "running" : "ready",
      can_trigger: task.last_run?.status !== "running",
      cooldown_remaining_seconds: 0,
      next_allowed_at: "",
      issue_count: 0,
      issues: [],
      purpose: copy.summary,
      writes_to_ledger: false,
      estimated_seconds: 60,
    };
  });
  const rows = allRecoverySteps.length ? allRecoverySteps : fallbackRows;
  const trust = status?.readiness?.trust_level;

  function startRefresh(taskName?: string) {
    const normalized = normalizeTaskName(taskName || status?.recommended_task?.task_name);
    if (!normalized) {
      setFeedback("暂时没有可运行的安全刷新任务。");
      return;
    }
    setFeedback("");
    trigger.mutate(
      { task_name: normalized, reason: "manual_from_settings_safe_refresh" },
      {
        onSuccess: (payload) => {
          setFeedback(`${payload.task.title || payload.task.task_name} 已启动。运行结束后回到 Dashboard 或 Stock 复核 readiness。`);
        },
        onError: (error) => setFeedback(error instanceof Error ? error.message : "刷新启动失败"),
      },
    );
  }

  return (
    <section id="recovery" className="scroll-mt-6">
      <Panel title="数据恢复向导" eyebrow="Recovery Wizard">
        <div className="surface-card p-4">
          <div className="mb-4 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone="positive">安全区</Badge>
              <span className="text-[12px] text-[var(--text-secondary)]">
                按下方顺序逐步恢复今天的数据链路。高级步骤会重算候选池或时段产物；带「写账本」标记的步骤会影响真实账本。
              </span>
            </div>
            {trust ? (
              <div className="mt-2 text-[12px] leading-5 text-[var(--text-secondary)]">
                <span className="font-medium text-[var(--text-primary)]">当前可信度：</span>
                {trust.label} · {trust.headline}
              </div>
            ) : null}
            {feedback ? <div className="mt-2 text-[12px] text-[var(--text-secondary)]">{feedback}</div> : null}
            {advancedRecoveryCount > 0 ? (
              <div className="mt-2 text-[12px] text-[var(--text-tertiary)]">
                其中 {advancedRecoveryCount} 个为高级恢复步骤，已保留在当前链路中，运行前请确认用途。
              </div>
            ) : null}
          </div>

          <ol className="flex flex-col gap-3">
            {rows.map((row, index) => {
              const taskName = normalizeTaskName(row.task_name);
              const copy = refreshTaskCopy(taskName);
              const cooling = Number(row.cooldown_remaining_seconds || 0) > 0;
              const running = row.status === "running";
              const disabled = trigger.isPending || running || cooling || !row.can_trigger;
              const stepNumber = row.step || index + 1;
              const writesToLedger = Boolean(row.writes_to_ledger);
              const isAdvanced = copy.category !== "safe";
              const purpose = row.purpose || copy.summary;
              const passed = !running && !cooling && row.can_trigger && (row.issue_count || 0) === 0;
              return (
                <li
                  key={`${stepNumber}-${taskName}`}
                  className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-4"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="flex min-w-0 items-start gap-3">
                      <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-[var(--border-strong)] bg-[var(--bg-tertiary)] text-[12px] font-medium text-[var(--text-primary)]">
                        {stepNumber}
                      </span>
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-medium text-[var(--text-primary)]">{row.title || copy.title}</span>
                          <Badge tone={running ? "watch" : cooling ? "warning" : passed ? "positive" : "info"}>
                            {running ? "运行中" : cooling ? `冷却 ${formatCooldown(row.cooldown_remaining_seconds)}` : passed ? "当前通过" : "待运行"}
                          </Badge>
                          <Badge tone={isAdvanced ? "warning" : "positive"}>{isAdvanced ? "高级恢复" : "安全恢复"}</Badge>
                          {writesToLedger ? <Badge tone="risk">写账本</Badge> : <Badge tone="info">不写账本</Badge>}
                          <span className="text-[11px] text-[var(--text-tertiary)]">{formatDuration(row.estimated_seconds)}</span>
                        </div>
                        <p className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
                          <span className="text-[var(--text-tertiary)]">为什么：</span>
                          {purpose}
                        </p>
                        <p className="mt-1 text-[11px] leading-4 text-[var(--text-tertiary)]">
                          {copy.impact}
                        </p>
                      </div>
                    </div>
                    <button
                      type="button"
                      className="focus-ring prism-btn prism-btn-primary"
                      onClick={() => startRefresh(taskName)}
                      disabled={disabled}
                    >
                      {trigger.isPending ? <LoaderCircle size={13} className="animate-spin" /> : <RefreshCw size={13} />}
                      运行此步
                    </button>
                  </div>
                  {row.issues?.length ? (
                    <div className="mt-3 space-y-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2">
                      {row.issues.slice(0, 2).map((issue) => (
                        <div key={`${issue.code}-${issue.label}`} className="text-[11px] leading-4 text-[var(--text-tertiary)]">
                          <span className="font-medium text-[var(--text-secondary)]">{issue.label}：</span>
                          {issue.message}
                        </div>
                      ))}
                    </div>
                  ) : null}
                </li>
              );
            })}
            {!rows.length ? <EmptyState>当前没有待恢复的步骤。</EmptyState> : null}
          </ol>
        </div>
      </Panel>
    </section>
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
  onPreview: (state: PreviewDrawerState | ((current: PreviewDrawerState) => PreviewDrawerState)) => void;
  title?: string;
  eyebrow?: string;
}) {
  const runTask = useRunTask();
  const [sendToFeishu, setSendToFeishu] = useState<Record<string, boolean>>({});
  const [feedback, setFeedback] = useState("");

  async function openRunDetail(run?: RunItem) {
    const runId = runIdOf(run);
    if (!runId && !run?.meta_path) {
      return;
    }
    onPreview({
      open: true,
      title: run?.title || run?.task_name || runId || "运行详情",
      subtitle: runId || run?.meta_path,
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
      } else if (run?.meta_path) {
        const payload = await api.preview(run.meta_path);
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
        title: run?.title || runId || "运行详情",
        subtitle: runId || run?.meta_path,
        kind: "run",
        error: error instanceof Error ? error.message : "详情读取失败",
      });
    }
  }

  async function openRunLog(run?: RunItem) {
    const runId = runIdOf(run);
    if (!runId && !run?.log_path) {
      return;
    }
    onPreview({
      open: true,
      title: run?.title || run?.task_name || runId || "运行日志",
      subtitle: runId || run?.log_path,
      loading: true,
      kind: "log",
    });
    try {
      if (runId) {
        const text = await api.getRunLog(runId);
        onPreview({
          open: true,
          title: run?.title || run?.task_name || runId,
          subtitle: runId,
          text,
          kind: "log",
        });
      } else if (run?.log_path) {
        const payload = await api.preview(run.log_path);
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
        title: run?.title || runId || "运行日志",
        subtitle: runId || run?.log_path,
        kind: "log",
        error: error instanceof Error ? error.message : "日志读取失败",
      });
    }
  }

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
                        onClick={() => void openRunDetail(lastRun)}
                      >
                        <Eye size={13} />
                        详情
                      </button>
                      <button
                        type="button"
                        className="focus-ring prism-btn prism-btn-secondary"
                        onClick={() => void openRunLog(lastRun)}
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
  onPreview,
}: {
  runs: RunItem[];
  onPreview: (state: PreviewDrawerState) => void;
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

  async function openLog(run: RunItem) {
    const runId = runIdOf(run);
    onPreview({
      open: true,
      title: run.title || run.task_name || runId || "运行日志",
      subtitle: runId || run.log_path,
      loading: true,
      kind: "log",
    });
    try {
      const text = runId ? await api.getRunLog(runId) : run.log_path ? (await api.preview(run.log_path)).text : "";
      onPreview({
        open: true,
        title: run.title || run.task_name || runId || "运行日志",
        subtitle: runId || run.log_path,
        text,
        kind: "log",
      });
    } catch (error) {
      onPreview({
        open: true,
        title: run.title || run.task_name || runId || "运行日志",
        subtitle: runId || run.log_path,
        kind: "log",
        error: error instanceof Error ? error.message : "日志读取失败",
      });
    }
  }

  return (
    <Panel title="最近运行" eyebrow="Runs">
      <div className="flex flex-col gap-2">
        {runs.slice(0, 8).map((run, index) => {
          const runId = runIdOf(run);
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
                <button
                  type="button"
                  className="focus-ring prism-btn prism-btn-secondary prism-btn-sm"
                  onClick={() => onPreview({
                    open: true,
                    title: run.title || run.task_name || runId || "运行详情",
                    subtitle: runId || run.meta_path,
                    text: JSON.stringify(run, null, 2),
                    kind: "json",
                  })}
                >
                  详情
                </button>
                {(runId || run.log_path) ? (
                  <button
                    type="button"
                    className="focus-ring prism-btn prism-btn-secondary prism-btn-sm"
                    onClick={() => void openLog(run)}
                  >
                    日志
                  </button>
                ) : null}
              </div>
            </div>
          );
        })}
        {!runs.length ? <EmptyState>暂无运行记录。</EmptyState> : null}
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

function learningStageLabel(stage?: string) {
  if (stage === "pattern_formed") {
    return "已形成模式";
  }
  if (stage === "validating_pattern") {
    return "待验证";
  }
  if (stage === "observation_hypothesis") {
    return "观察假设";
  }
  if (stage === "pending_outcome") {
    return "等待 outcome";
  }
  return stage || "-";
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

function DecisionLedgerHealthPanel() {
  const ledger = useDecisionLedgerHealth();
  const data = ledger.data as DecisionLedgerHealthResponse | undefined;

  const capture = data?.last_capture;
  const outcome = data?.last_outcome_evaluation;
  const corrupt = data?.corrupt_files || [];
  const statusErrors = data?.status_errors || [];
  const storage = data?.storage;
  const learning = data?.learning_loop;
  const topBuckets = (learning?.buckets || [])
    .filter((bucket) => bucket.samples > 0)
    .slice()
    .sort((a, b) => (b.needs_review || 0) - (a.needs_review || 0) || (b.mature_samples || 0) - (a.mature_samples || 0))
    .slice(0, 3);
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
              {topBuckets.length ? (
                <div className="mt-2 grid gap-1.5 text-[11px] text-[var(--text-secondary)]">
                  {topBuckets.map((bucket) => (
                    <div
                      key={`${bucket.ruleset_version}-${bucket.lane}-${bucket.action}`}
                      className="flex flex-wrap items-center justify-between gap-2 rounded border border-[var(--border-subtle)] px-2 py-1"
                    >
                      <span className="font-mono text-[var(--text-primary)]">{bucket.lane}/{bucket.action}</span>
                      <span>
                        {learningStageLabel(bucket.sample_stage)} · 成熟 {bucket.mature_samples} · 复盘 {bucket.needs_review}
                      </span>
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

export default function SettingsPage() {
  const overview = useOverview();
  const health = useHealth();
  const runs = useRuns();
  const refreshStatus = useRefreshStatus("today", true, { auto: false });
  const formalData = useFormalDataStatus();
  const dataAssets = useDataAssetsStatus();
  const [preview, setPreview] = useState<PreviewDrawerState>({
    open: false,
    title: "",
  });
  const runRows = runs.data?.runs || overview.data?.runs || [];
  const feishuChannel = health.data?.channels?.feishu;
  const feishuAvailable = Boolean(feishuChannel?.available);
  const feishuDetail = feishuChannel?.detail || "";
  const tasks = overview.data?.tasks || [];
  const safeTasks = safeTaskList(tasks);
  const advancedTasks = advancedTaskList(tasks);
  const readiness = refreshStatus.data?.readiness;
  const readinessCopy = readinessModeCopy(readiness?.readiness_mode);

  return (
    <>
      <main className="flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
        <div className="mx-auto max-w-7xl">
          <PageTitle
            eyebrow="Settings"
            title="设置"
            summary="先看今天数据是否可信，再运行安全刷新；高级任务和危险写入已隔离。"
            icon={Settings}
            badge={readiness ? readinessCopy.title : health.data?.ok ? "系统正常" : "待检查"}
            actions={
              <button
                type="button"
                className="focus-ring prism-btn prism-btn-secondary"
                onClick={() => {
                  void overview.refetch();
                  void health.refetch();
                  void runs.refetch();
                  void formalData.refetch();
                  void dataAssets.refetch();
                }}
              >
                <RefreshCw size={14} className={overview.isFetching || health.isFetching || runs.isFetching ? "animate-spin" : ""} />
                刷新
              </button>
            }
          />

          {overview.isError || health.isError ? <ErrorState message="系统状态暂不可用" /> : null}

          <section className="mb-7 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="后端健康" value={health.data?.ok ? "OK" : "未知"} detail={health.data?.workspace || "等待 /healthz"} tone={health.data?.ok ? "positive" : "watch"} />
            <MetricCard label="交易可用性" value={readinessCopy.realMoney} detail={readiness?.session?.label || "等待 readiness"} tone={readinessCopy.tone} />
            <MetricCard label="安全刷新" value={String(safeTasks.length)} detail="日常可用入口" tone="info" />
            <MetricCard label="最近运行" value={String(runRows.length)} detail="来自 /api/runs" tone="watch" />
            <MetricCard label="刷新源" value={String(overview.data?.freshness?.length || 0)} detail={overview.data?.generated_at || "等待总览"} tone={(readiness?.stale_count || 0) > 0 ? "warning" : "positive"} />
            <MetricCard label="Tushare 资产" value={String(dataAssets.data?.summary?.tushare_ready_count || 0)} detail={dataAssets.data?.generated_at || "等待数据资产"} tone={(dataAssets.data?.summary?.tushare_ready_count || 0) > 0 ? "positive" : "watch"} />
          </section>

          <section className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
            <div className="flex flex-col gap-6">
              <ReadinessStatusPanel status={refreshStatus.data} />
              <DataAssetsPanel
                status={dataAssets.data}
                loading={dataAssets.isLoading || dataAssets.isFetching}
                onRefresh={() => void dataAssets.refetch()}
              />
              <FormalDataPanel
                status={formalData.data}
                loading={formalData.isLoading || formalData.isFetching}
                onRefresh={() => void formalData.refetch()}
              />
              <SafeRefreshPanel status={refreshStatus.data} tasks={safeTasks} />
              <SchedulerStatusPanel status={refreshStatus.data} />
              <RefreshPolicyPanel status={refreshStatus.data} />
              <RecentRunsPanel runs={runRows} onPreview={setPreview} />
            </div>

            <div className="flex flex-col gap-6">
              <Panel title="外观" eyebrow="Display">
                <div className="surface-card p-4">
                  <ThemeToggle />
                </div>
              </Panel>

              <Panel title="服务状态" eyebrow="System">
                <div className="surface-card p-4">
                  <div className="mb-4 flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
                      <Activity size={18} className={health.data?.ok ? "text-[var(--positive)]" : "text-[var(--warning)]"} />
                    </div>
                    <div>
                      <div className="font-medium text-[var(--text-primary)]">{health.data?.ok ? "FastAPI 已连接" : "等待健康检查"}</div>
                      <div className="mt-1 text-[12px] text-[var(--text-tertiary)]">{health.data?.workspace || "http://localhost:8000"}</div>
                    </div>
                  </div>
                  <Badge tone={health.data?.ok ? "positive" : "warning"}>{health.data?.ok ? "online" : "unknown"}</Badge>
                  <div className="mt-3 text-[12px] text-[var(--text-secondary)]">
                    飞书通道：{feishuAvailable ? "可用" : "未就绪"}
                  </div>
                  <div className="mt-1 text-[12px] text-[var(--text-tertiary)]">
                    {feishuDetail || "等待飞书状态检查"}
                  </div>
                </div>
              </Panel>

              <TaskRunnerPanel
                tasks={advancedTasks}
                feishuAvailable={feishuAvailable}
                feishuDetail={feishuDetail}
                onPreview={setPreview}
              />

              <DecisionLedgerHealthPanel />

              <ParametersEditor />

              <Panel title="数据目录" eyebrow="Storage">
                <div className="surface-card flex items-center gap-3 p-4">
                  <Database size={18} className="text-[var(--text-tertiary)]" />
                  <span className="mono min-w-0 truncate text-[12px] text-[var(--text-secondary)]">
                    {overview.data?.workspace_root || "等待 overview"}
                  </span>
                </div>
              </Panel>
            </div>
          </section>
        </div>
      </main>
      <PreviewDrawer state={preview} onClose={() => setPreview((current) => ({ ...current, open: false }))} />
    </>
  );
}
