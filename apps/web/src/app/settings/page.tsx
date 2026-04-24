"use client";

import { Activity, Database, RefreshCw, Settings } from "lucide-react";

import { Badge } from "@/components/badge";
import { DataCard, EmptyState, ErrorState, Panel } from "@/components/data-card";
import { MetricCard } from "@/components/metric-card";
import { PageTitle } from "@/components/page-title";
import { useHealth, useOverview, useRuns } from "@/lib/hooks";

export default function SettingsPage() {
  const overview = useOverview();
  const health = useHealth();
  const runs = useRuns();

  return (
    <main className="flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
      <div className="mx-auto max-w-7xl">
        <PageTitle
          eyebrow="Settings"
          title="设置"
          summary="任务运行、系统健康和最近执行记录。参数编辑接口存在时会在后续继续补上可视化编辑。"
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
          <MetricCard label="最近运行" value={String(runs.data?.runs?.length || overview.data?.runs?.length || 0)} detail="来自 /api/runs" tone="watch" />
          <MetricCard label="刷新源" value={String(overview.data?.freshness?.length || 0)} detail={overview.data?.generated_at || "等待总览"} tone="positive" />
        </section>

        <section className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
          <Panel title="任务管理" eyebrow="Tasks">
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              {(overview.data?.tasks || []).slice(0, 8).map((task, index) => {
                const item = task as Record<string, unknown>;
                return (
                  <DataCard
                    key={`${String(item.title || item.name || index)}`}
                    card={{
                      title: String(item.title || item.name || item.task_name || "任务"),
                      subtitle: String(item.name || item.task_name || "task"),
                      status: String(item.status || "待运行"),
                      detail: String(item.description || item.summary || "可由后端任务接口触发。"),
                      tone: String(item.status || "").includes("running") ? "watch" : "info",
                    }}
                  />
                );
              })}
              {!overview.data?.tasks?.length ? <EmptyState>暂无任务定义。</EmptyState> : null}
            </div>
          </Panel>

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

            <Panel title="最近运行" eyebrow="Runs">
              <div className="flex flex-col gap-2">
                {(runs.data?.runs || overview.data?.runs || []).slice(0, 6).map((run, index) => (
                  <div key={`${run.run_id || index}`} className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
                    <div className="flex items-center justify-between gap-3">
                      <span className="truncate text-[13px] text-[var(--text-primary)]">{run.title || run.task_name || run.run_id}</span>
                      <Badge tone={run.status === "completed" ? "positive" : run.status === "failed" ? "risk" : "watch"}>{run.status || "unknown"}</Badge>
                    </div>
                    <div className="mono mt-1 truncate text-[11px] text-[var(--text-tertiary)]">{run.started_at || run.finished_at || "-"}</div>
                  </div>
                ))}
                {!(runs.data?.runs || overview.data?.runs || []).length ? <EmptyState>暂无运行记录。</EmptyState> : null}
              </div>
            </Panel>

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
  );
}
