"use client";

import {
  Activity,
  Database,
  Eye,
  FileJson,
  LoaderCircle,
  Play,
  RefreshCw,
  RotateCcw,
  Save,
  Settings,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/badge";
import { EmptyState, ErrorState, Panel } from "@/components/data-card";
import { MetricCard } from "@/components/metric-card";
import { PageTitle } from "@/components/page-title";
import { PreviewDrawer, type PreviewDrawerState } from "@/components/preview-drawer";
import { api } from "@/lib/api";
import { useHealth, useOverview, useParameters, useRunTask, useRuns, useSaveParameters } from "@/lib/hooks";
import type { RunItem, TaskDefinition } from "@/lib/types";

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

function ParametersEditor() {
  const parameters = useParameters();
  const saveParameters = useSaveParameters();
  const [raw, setRaw] = useState("");
  const [dirty, setDirty] = useState(false);
  const [localError, setLocalError] = useState("");
  const [success, setSuccess] = useState("");

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
    parameters.refetch().then((result) => {
      if (result.data?.raw) {
        setRaw(result.data.raw);
        setDirty(false);
      }
    });
  }

  function save() {
    setLocalError("");
    setSuccess("");
    try {
      JSON.parse(raw);
    } catch (error) {
      setLocalError(error instanceof Error ? error.message : "JSON 格式错误");
      return;
    }
    saveParameters.mutate(
      { raw },
      {
        onSuccess: (payload) => {
          setRaw(payload.raw);
          setDirty(false);
          setSuccess(payload.saved ? "参数已保存到磁盘。" : "参数已校验。");
        },
        onError: (error) => setLocalError(error instanceof Error ? error.message : "保存失败"),
      },
    );
  }

  return (
    <Panel
      title="参数编辑"
      eyebrow="Parameters"
      action={
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="focus-ring inline-flex items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-1.5 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            onClick={reloadFromDisk}
            disabled={parameters.isFetching}
          >
            <RotateCcw size={13} className={parameters.isFetching ? "animate-spin" : ""} />
            重载
          </button>
          <button
            type="button"
            className="focus-ring inline-flex items-center gap-2 rounded-md bg-[var(--text-primary)] px-3 py-1.5 text-[12px] font-medium text-[var(--text-inverse)] disabled:cursor-not-allowed disabled:opacity-50"
            onClick={save}
            disabled={saveParameters.isPending || !raw.trim()}
          >
            {saveParameters.isPending ? <LoaderCircle size={13} className="animate-spin" /> : <Save size={13} />}
            保存
          </button>
        </div>
      }
    >
      {parameters.isError ? <ErrorState message="参数接口暂不可用" onRetry={() => void parameters.refetch()} /> : null}

      <div className="surface-card p-4">
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
              className="focus-ring rounded-md border border-[var(--border-subtle)] px-2.5 py-1 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
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
      </div>
    </Panel>
  );
}

function TaskRunnerPanel({
  tasks,
  onPreview,
}: {
  tasks: TaskDefinition[];
  onPreview: (state: PreviewDrawerState | ((current: PreviewDrawerState) => PreviewDrawerState)) => void;
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
        onSuccess: (payload) => setFeedback(`${payload.title || task.title || taskName} 已启动。`),
        onError: (error) => setFeedback(error instanceof Error ? error.message : "任务启动失败"),
      },
    );
  }

  return (
    <Panel title="任务运行" eyebrow="Tasks">
      <div className="surface-card p-4">
        {feedback ? (
          <div className="mb-4 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
            {feedback}
          </div>
        ) : null}

        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {tasks.map((task, index) => {
            const taskName = taskNameOf(task);
            const lastRun = task.last_run;
            return (
              <div key={`${taskName || task.title || index}`} className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-4">
                <div className="mb-3 flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium text-[var(--text-primary)]">{task.title || taskName || "任务"}</div>
                    <div className="mono mt-1 truncate text-[11px] text-[var(--text-tertiary)]">{taskName || task.lane || "task"}</div>
                  </div>
                  <Badge tone={runTone(lastRun?.status)}>{lastRun?.status || "ready"}</Badge>
                </div>
                <p className="mb-4 line-clamp-3 text-[12px] leading-5 text-[var(--text-secondary)]">
                  {task.description || "可由后端任务接口触发。"}
                </p>
                <label className="mb-3 flex items-center gap-2 text-[12px] text-[var(--text-secondary)]">
                  <input
                    type="checkbox"
                    checked={Boolean(sendToFeishu[taskName])}
                    onChange={(event) =>
                      setSendToFeishu((current) => ({ ...current, [taskName]: event.target.checked }))
                    }
                    className="h-4 w-4 accent-[var(--info)]"
                  />
                  允许发送飞书
                </label>
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    className="focus-ring inline-flex items-center gap-2 rounded-md bg-[var(--text-primary)] px-3 py-1.5 text-[12px] font-medium text-[var(--text-inverse)] disabled:cursor-not-allowed disabled:opacity-50"
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
                        className="focus-ring inline-flex items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-1.5 text-[12px] text-[var(--text-secondary)]"
                        onClick={() => void openRunDetail(lastRun)}
                      >
                        <Eye size={13} />
                        详情
                      </button>
                      <button
                        type="button"
                        className="focus-ring inline-flex items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-1.5 text-[12px] text-[var(--text-secondary)]"
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
              <div className="mt-2 flex gap-2">
                <button
                  type="button"
                  className="focus-ring rounded-md border border-[var(--border-subtle)] px-2 py-1 text-[11px] text-[var(--text-secondary)]"
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
                    className="focus-ring rounded-md border border-[var(--border-subtle)] px-2 py-1 text-[11px] text-[var(--text-secondary)]"
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

export default function SettingsPage() {
  const overview = useOverview();
  const health = useHealth();
  const runs = useRuns();
  const [preview, setPreview] = useState<PreviewDrawerState>({
    open: false,
    title: "",
  });
  const runRows = runs.data?.runs || overview.data?.runs || [];

  return (
    <>
      <main className="flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
        <div className="mx-auto max-w-7xl">
          <PageTitle
            eyebrow="Settings"
            title="设置"
            summary="参数编辑、任务启动、运行记录和日志预览。"
            icon={Settings}
            badge={health.data?.ok ? "系统正常" : "待检查"}
            actions={
              <button
                type="button"
                className="focus-ring inline-flex items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)]"
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
            <MetricCard label="任务定义" value={String(overview.data?.tasks?.length || 0)} detail="来自 /api/overview" tone="info" />
            <MetricCard label="最近运行" value={String(runRows.length)} detail="来自 /api/runs" tone="watch" />
            <MetricCard label="刷新源" value={String(overview.data?.freshness?.length || 0)} detail={overview.data?.generated_at || "等待总览"} tone="positive" />
          </section>

          <section className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
            <div className="flex flex-col gap-6">
              <TaskRunnerPanel tasks={overview.data?.tasks || []} onPreview={setPreview} />
              <ParametersEditor />
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
                </div>
              </Panel>

              <RecentRunsPanel runs={runRows} onPreview={setPreview} />

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
