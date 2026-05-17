"use client";

import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Database,
  Eye,
  FileJson,
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
import { api, ApiError } from "@/lib/api";
import {
  useDecisionLedgerHealth,
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
  ParametersResponse,
  RefreshStatus,
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
    authoritative_daily: "权威日线",
    disclosure: "公告披露",
    display_only: "仅展示",
    execution: "执行约束",
    formal_candidate: "Formal 候选",
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
            <span className="text-[13px] font-medium text-[var(--text-primary)]">Formal 数据源闸门</span>
            <Badge tone={readiness?.formal_ready ? "positive" : "watch"}>
              {readiness?.formal_ready ? "Formal Ready" : "Live 快源 / Formal 未放行"}
            </Badge>
          </div>
          <p className="text-[12px] leading-5 text-[var(--text-secondary)]">
            Live-ready 只代表当前控制台数据可按纪律观察/小额执行；formal-ready 需要权威日线、复权、benchmark 和执行约束源全部通过。
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
      </div>
    </Panel>
  );
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
  const recoverySteps = allRecoverySteps.filter((step) => refreshTaskCopy(step.task_name).category === "safe");
  const advancedRecoveryCount = allRecoverySteps.length - recoverySteps.length;
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
    };
  });
  const rows = recoverySteps.length ? recoverySteps : fallbackRows;

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
    <Panel title="日常安全刷新" eyebrow="Safe Refresh">
      <div className="surface-card p-4">
        <div className="mb-4 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="positive">安全区</Badge>
            <span className="text-[12px] text-[var(--text-secondary)]">
              这些入口只触发数据刷新或简报生成；不会写真实账本，不会提交成交，不会自动下单。
            </span>
          </div>
          {feedback ? <div className="mt-2 text-[12px] text-[var(--text-secondary)]">{feedback}</div> : null}
          {advancedRecoveryCount > 0 ? (
            <div className="mt-2 text-[12px] text-[var(--text-tertiary)]">
              另有 {advancedRecoveryCount} 个高级恢复任务已放在右侧高级任务区，避免和日常刷新混用。
            </div>
          ) : null}
        </div>

        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {rows.map((row) => {
            const taskName = normalizeTaskName(row.task_name);
            const copy = refreshTaskCopy(taskName);
            const cooling = Number(row.cooldown_remaining_seconds || 0) > 0;
            const running = row.status === "running";
            const disabled = trigger.isPending || running || cooling || !row.can_trigger;
            return (
              <div key={`${row.step}-${taskName}`} className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-4">
                <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-[var(--text-primary)]">{row.title || copy.title}</div>
                    <div className="mono mt-1 text-[11px] text-[var(--text-tertiary)]">{taskName}</div>
                  </div>
                  <Badge tone={running ? "watch" : cooling ? "warning" : "positive"}>
                    {running ? "运行中" : cooling ? `冷却 ${formatCooldown(row.cooldown_remaining_seconds)}` : "可运行"}
                  </Badge>
                </div>
                <p className="text-[12px] leading-5 text-[var(--text-secondary)]">{copy.summary}</p>
                <p className="mt-1 text-[11px] leading-4 text-[var(--text-tertiary)]">{copy.impact}</p>
                {row.issues?.length ? (
                  <div className="mt-3 space-y-1">
                    {row.issues.slice(0, 2).map((issue) => (
                      <div key={`${issue.code}-${issue.label}`} className="text-[11px] leading-4 text-[var(--text-tertiary)]">
                        <span className="font-medium text-[var(--text-secondary)]">{issue.label}：</span>
                        {issue.message}
                      </div>
                    ))}
                  </div>
                ) : null}
                <button
                  type="button"
                  className="focus-ring prism-btn prism-btn-primary mt-3"
                  onClick={() => startRefresh(taskName)}
                  disabled={disabled}
                >
                  {trigger.isPending ? <LoaderCircle size={13} className="animate-spin" /> : <RefreshCw size={13} />}
                  运行安全刷新
                </button>
              </div>
            );
          })}
          {!rows.length ? <EmptyState>暂无可推荐的安全刷新任务。</EmptyState> : null}
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

function SchedulerStatusPanel({ status }: { status?: RefreshStatus }) {
  const scheduler = status?.scheduler_status;
  const service = scheduler?.scheduler;
  const summary = scheduler?.summary;
  const jobs = scheduler?.jobs || [];
  const visibleJobs = jobs.filter((job) => job.health !== "success").concat(jobs.filter((job) => job.health === "success")).slice(0, 7);
  const hasIssues = Boolean((summary?.failed || 0) + (summary?.stale || 0) + (summary?.missing || 0));

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

function DecisionLedgerHealthPanel() {
  const ledger = useDecisionLedgerHealth();
  const data = ledger.data as DecisionLedgerHealthResponse | undefined;

  const capture = data?.last_capture;
  const outcome = data?.last_outcome_evaluation;
  const corrupt = data?.corrupt_files || [];
  const statusErrors = data?.status_errors || [];

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
          </section>

          <section className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
            <div className="flex flex-col gap-6">
              <ReadinessStatusPanel status={refreshStatus.data} />
              <SafeRefreshPanel status={refreshStatus.data} tasks={safeTasks} />
              <SchedulerStatusPanel status={refreshStatus.data} />
              <RefreshPolicyPanel status={refreshStatus.data} />
              <RecentRunsPanel runs={runRows} onPreview={setPreview} />
            </div>

            <div className="flex flex-col gap-6">
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
