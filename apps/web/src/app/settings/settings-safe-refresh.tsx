"use client";

import { LoaderCircle, RefreshCw } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/badge";
import { EmptyState, Panel } from "@/components/data-card";
import { useTriggerRefresh } from "@/lib/hooks";
import {
  formatCooldown,
  normalizeTaskName,
  refreshTaskCopy,
} from "@/lib/readiness-copy";
import type { RefreshStatus, TaskDefinition } from "@/lib/types";

import { safeTaskList, taskNameOf } from "./settings-utils";

export type SettingsSafeRefreshPanelProps = {
  status?: RefreshStatus;
  tasks: TaskDefinition[];
};

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

export function SettingsSafeRefreshPanel({
  status,
  tasks,
}: SettingsSafeRefreshPanelProps) {
  const trigger = useTriggerRefresh("today");
  const [feedback, setFeedback] = useState("");
  const allRecoverySteps = status?.recovery_steps || [];
  const advancedRecoveryCount = allRecoverySteps.filter(
    (step) => refreshTaskCopy(step.task_name).category !== "safe",
  ).length;
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
    const normalized = normalizeTaskName(
      taskName || status?.recommended_task?.task_name,
    );
    if (!normalized) {
      setFeedback("暂时没有可运行的安全刷新任务。");
      return;
    }
    setFeedback("");
    trigger.mutate(
      { task_name: normalized, reason: "manual_from_settings_safe_refresh" },
      {
        onSuccess: (payload) => {
          setFeedback(
            `${payload.task.title || payload.task.task_name} 已启动。运行结束后回到 Dashboard 或 Stock 复核 readiness。`,
          );
        },
        onError: (error) =>
          setFeedback(error instanceof Error ? error.message : "刷新启动失败"),
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
                <span className="font-medium text-[var(--text-primary)]">
                  当前可信度：
                </span>
                {trust.label} · {trust.headline}
              </div>
            ) : null}
            {feedback ? (
              <div className="mt-2 text-[12px] text-[var(--text-secondary)]">
                {feedback}
              </div>
            ) : null}
            {advancedRecoveryCount > 0 ? (
              <div className="mt-2 text-[12px] text-[var(--text-tertiary)]">
                其中 {advancedRecoveryCount}{" "}
                个为高级恢复步骤，已保留在当前链路中，运行前请确认用途。
              </div>
            ) : null}
          </div>

          <ol className="flex flex-col gap-3">
            {rows.map((row, index) => {
              const taskName = normalizeTaskName(row.task_name);
              const copy = refreshTaskCopy(taskName);
              const cooling = Number(row.cooldown_remaining_seconds || 0) > 0;
              const running = row.status === "running";
              const disabled =
                trigger.isPending || running || cooling || !row.can_trigger;
              const stepNumber = row.step || index + 1;
              const writesToLedger = Boolean(row.writes_to_ledger);
              const isAdvanced = copy.category !== "safe";
              const purpose = row.purpose || copy.summary;
              const passed =
                !running &&
                !cooling &&
                row.can_trigger &&
                (row.issue_count || 0) === 0;
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
                          <span className="text-sm font-medium text-[var(--text-primary)]">
                            {row.title || copy.title}
                          </span>
                          <Badge
                            tone={
                              running
                                ? "watch"
                                : cooling
                                  ? "warning"
                                  : passed
                                    ? "positive"
                                    : "info"
                            }
                          >
                            {running
                              ? "运行中"
                              : cooling
                                ? `冷却 ${formatCooldown(row.cooldown_remaining_seconds)}`
                                : passed
                                  ? "当前通过"
                                  : "待运行"}
                          </Badge>
                          <Badge tone={isAdvanced ? "warning" : "positive"}>
                            {isAdvanced ? "高级恢复" : "安全恢复"}
                          </Badge>
                          {writesToLedger ? (
                            <Badge tone="risk">写账本</Badge>
                          ) : (
                            <Badge tone="info">不写账本</Badge>
                          )}
                          <span className="text-[11px] text-[var(--text-tertiary)]">
                            {formatDuration(row.estimated_seconds)}
                          </span>
                        </div>
                        <p className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
                          <span className="text-[var(--text-tertiary)]">
                            为什么：
                          </span>
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
                      {trigger.isPending ? (
                        <LoaderCircle size={13} className="animate-spin" />
                      ) : (
                        <RefreshCw size={13} />
                      )}
                      运行此步
                    </button>
                  </div>
                  {row.issues?.length ? (
                    <div className="mt-3 space-y-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2">
                      {row.issues.slice(0, 2).map((issue) => (
                        <div
                          key={`${issue.code}-${issue.label}`}
                          className="text-[11px] leading-4 text-[var(--text-tertiary)]"
                        >
                          <span className="font-medium text-[var(--text-secondary)]">
                            {issue.label}：
                          </span>
                          {issue.message}
                        </div>
                      ))}
                    </div>
                  ) : null}
                </li>
              );
            })}
            {!rows.length ? (
              <EmptyState>当前没有待恢复的步骤。</EmptyState>
            ) : null}
          </ol>
        </div>
      </Panel>
    </section>
  );
}
