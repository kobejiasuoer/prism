"use client";

import dynamic from "next/dynamic";
import { useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  CheckCircle2,
  ChevronRight,
  Database,
  LoaderCircle,
  RefreshCw,
  Settings,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/badge";
import { ErrorState, Panel } from "@/components/data-card";
import { MetricCard } from "@/components/metric-card";
import { PageTitle } from "@/components/page-title";
import type { PreviewDrawerState } from "@/components/preview-drawer";
import { ThemeToggle } from "@/components/theme-toggle";
import { api } from "@/lib/api";
import {
  queryKeys,
  useHealth,
  useOverview,
  useRefreshStatus,
} from "@/lib/hooks";
import {
  readinessModeCopy,
  readinessNextStep,
  refreshTaskCopy,
} from "@/lib/readiness-copy";
import type { OverviewData, RefreshStatus } from "@/lib/types";

import type {
  SettingsDiagnosticsAsideProps,
  SettingsDiagnosticsMainProps,
} from "./settings-diagnostics";
import type { SettingsReadinessDetailsProps } from "./settings-readiness-details";
import type { SettingsSafeRefreshPanelProps } from "./settings-safe-refresh";
import { advancedTaskList, safeTaskList } from "./settings-utils";

interface SettingsPreviewDrawerProps {
  state: PreviewDrawerState;
  onClose: () => void;
}

const SettingsDiagnosticsMain = dynamic<SettingsDiagnosticsMainProps>(
  () =>
    import("./settings-diagnostics").then(
      (module) => module.SettingsDiagnosticsMain,
    ),
  {
    ssr: false,
    loading: () => (
      <Panel title="诊断加载中" eyebrow="Diagnostics">
        <div className="surface-card flex items-center gap-2 p-4 text-[12px] text-[var(--text-secondary)]">
          <LoaderCircle size={14} className="animate-spin" />
          加载数据资产、后台守护和运行记录
        </div>
      </Panel>
    ),
  },
);

const SettingsDiagnosticsAside = dynamic<SettingsDiagnosticsAsideProps>(
  () =>
    import("./settings-diagnostics").then(
      (module) => module.SettingsDiagnosticsAside,
    ),
  {
    ssr: false,
    loading: () => (
      <Panel title="诊断加载中" eyebrow="Diagnostics">
        <div className="surface-card flex items-center gap-2 p-4 text-[12px] text-[var(--text-secondary)]">
          <LoaderCircle size={14} className="animate-spin" />
          加载高级任务和账本健康
        </div>
      </Panel>
    ),
  },
);

const SettingsPreviewDrawer = dynamic<SettingsPreviewDrawerProps>(
  () =>
    import("@/components/preview-drawer").then(
      (module) => module.PreviewDrawer,
    ),
  {
    ssr: false,
    loading: () => null,
  },
);

const SettingsParametersEditor = dynamic(
  () =>
    import("./settings-parameters").then((module) => module.ParametersEditor),
  {
    ssr: false,
    loading: () => (
      <Panel title="参数编辑" eyebrow="Advanced / Dangerous">
        <div className="surface-card flex items-center gap-2 p-4 text-[12px] text-[var(--text-secondary)]">
          <LoaderCircle size={14} className="animate-spin" />
          加载参数编辑器
        </div>
      </Panel>
    ),
  },
);

const SettingsReadinessDetails = dynamic<SettingsReadinessDetailsProps>(
  () =>
    import("./settings-readiness-details").then(
      (module) => module.SettingsReadinessDetails,
    ),
  {
    ssr: false,
    loading: () => (
      <div className="mt-4 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3 text-[12px] text-[var(--text-secondary)]">
        <LoaderCircle size={14} className="mr-2 inline animate-spin" />
        加载正式口径和能力闸门
      </div>
    ),
  },
);

const SettingsSafeRefreshPanel = dynamic<SettingsSafeRefreshPanelProps>(
  () =>
    import("./settings-safe-refresh").then(
      (module) => module.SettingsSafeRefreshPanel,
    ),
  {
    ssr: false,
    loading: () => (
      <Panel title="数据恢复向导" eyebrow="Recovery Wizard">
        <div className="surface-card flex items-center gap-2 p-4 text-[12px] text-[var(--text-secondary)]">
          <LoaderCircle size={14} className="animate-spin" />
          加载安全刷新入口
        </div>
      </Panel>
    ),
  },
);

function DeferredParametersPanel() {
  const [open, setOpen] = useState(false);

  if (open) {
    return <SettingsParametersEditor />;
  }

  return (
    <Panel title="参数编辑" eyebrow="Advanced / Dangerous">
      <div className="surface-card p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="text-sm font-medium text-[var(--text-primary)]">
              危险写入已隔离
            </div>
            <div className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
              参数文件编辑器只在展开后加载；日常排障优先使用安全刷新和诊断面板。
            </div>
          </div>
          <button
            type="button"
            className="focus-ring prism-btn prism-btn-secondary"
            onClick={() => setOpen(true)}
          >
            <ChevronRight size={14} />
            展开
          </button>
        </div>
      </div>
    </Panel>
  );
}

function ReadinessStatusPanel({
  status,
  diagnosticsLoading,
  onLoadDiagnostics,
}: {
  status?: RefreshStatus;
  diagnosticsLoading?: boolean;
  onLoadDiagnostics?: () => void;
}) {
  const readiness = status?.readiness;
  const readinessMode = readiness?.readiness_mode || status?.readiness_mode;
  const copy = readinessModeCopy(readinessMode);
  const compactNext =
    !readiness && status
      ? {
          title:
            status.stale_count > 0
              ? "先看轻量状态，再按需加载完整诊断"
              : "轻量状态未发现过期源",
          detail:
            status.stale_count > 0
              ? `轻量状态显示 ${status.stale_count} 个过期源；完整能力闸门和数据依赖需要时再加载。`
              : "首屏已拿到刷新摘要；完整能力闸门、正式口径和数据依赖需要时再加载。",
          taskName: status.recommended_task?.task_name || "",
          taskTitle: status.recommended_task?.title || "",
        }
      : null;
  const next = compactNext || readinessNextStep(readiness, status);
  const Icon = readinessMode === "live_ready" ? ShieldCheck : ShieldAlert;
  const account = readiness?.account_state;
  const recommendation = (
    <div className="mt-4 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <CheckCircle2 size={15} className="text-[var(--positive)]" />
        <span className="text-[13px] font-medium text-[var(--text-primary)]">
          推荐下一步
        </span>
        {next.taskName ? (
          <Badge
            tone={
              refreshTaskCopy(next.taskName).category === "safe"
                ? "info"
                : "watch"
            }
          >
            {next.taskTitle || next.taskName}
          </Badge>
        ) : null}
      </div>
      <div className="text-[13px] font-medium text-[var(--text-primary)]">
        {next.title}
      </div>
      <p className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
        {next.detail}
      </p>
    </div>
  );

  return (
    <Panel title="今日数据状态 / 交易可用性" eyebrow="Readiness">
      <div className="surface-card p-4">
        <div
          className="rounded-md border px-4 py-3"
          style={{ background: copy.bg, borderColor: copy.border }}
        >
          <div className="flex flex-wrap items-start gap-3">
            <Icon size={20} style={{ color: copy.iconColor, marginTop: 2 }} />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={readinessMode ? copy.tone : "watch"}>
                  {readinessMode ? copy.badge : "读取中"}
                </Badge>
                <Badge
                  tone={
                    readiness
                      ? readiness.ready
                        ? "positive"
                        : "risk"
                      : "watch"
                  }
                >
                  {readiness ? copy.realMoney : "完整诊断待加载"}
                </Badge>
                {readiness?.session?.label ? (
                  <Badge
                    tone={readiness.session.is_trading_day ? "info" : "warning"}
                  >
                    {readiness.session.label}
                  </Badge>
                ) : null}
              </div>
              <h2 className="mt-2 text-[16px] font-semibold text-[var(--text-primary)]">
                {readinessMode ? copy.title : "正在读取今日数据状态"}
              </h2>
              <p className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
                {readiness
                  ? copy.detail
                  : "首屏先读取轻量刷新状态；完整能力闸门、正式口径和数据依赖按需加载。"}
              </p>
            </div>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard
            label="预期交易日"
            value={readiness?.expected_trade_date || "-"}
            detail="页面应使用的日期"
            tone="info"
          />
          <MetricCard
            label="数据交易日"
            value={readiness?.data_trade_date || "-"}
            detail={
              readiness?.data_trade_date === readiness?.expected_trade_date
                ? "已对齐"
                : "需要复核"
            }
            tone={
              readiness?.data_trade_date === readiness?.expected_trade_date
                ? "positive"
                : "warning"
            }
          />
          <MetricCard
            label="过期源"
            value={String(readiness?.stale_count ?? status?.stale_count ?? "-")}
            detail="核心来源 stale 数"
            tone={
              readiness?.stale_count || status?.stale_count
                ? "warning"
                : "positive"
            }
          />
          <MetricCard
            label="账户模式"
            value={account?.mode_label || (readiness ? "-" : "诊断待加载")}
            detail={
              account
                ? account.ready_for_live_small
                  ? "live_small 已通过"
                  : "未放行真钱"
                : "完整 readiness 返回后显示"
            }
            tone={account?.ready_for_live_small ? "positive" : "watch"}
          />
        </div>

        {readiness ? null : (
          <div className="mt-4 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="text-[13px] font-medium text-[var(--text-primary)]">
                  完整能力闸门延迟加载
                </div>
                <p className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
                  Settings
                  首屏先保留轻量状态；正式口径、账户模式和底层数据依赖会进入诊断层。
                </p>
              </div>
              <button
                type="button"
                className="focus-ring prism-btn prism-btn-secondary"
                onClick={onLoadDiagnostics}
              >
                <RefreshCw
                  size={13}
                  className={diagnosticsLoading ? "animate-spin" : ""}
                />
                立即加载
              </button>
            </div>
          </div>
        )}

        {readiness ? (
          <SettingsReadinessDetails
            status={status}
            recommendation={recommendation}
          />
        ) : (
          recommendation
        )}
      </div>
    </Panel>
  );
}

export function SettingsWorkspace() {
  const queryClient = useQueryClient();
  const [diagnosticsEnabled, setDiagnosticsEnabled] = useState(false);
  const [advancedTasksOpen, setAdvancedTasksOpen] = useState(false);
  const overviewCompact = !advancedTasksOpen;
  const overview = useOverview({ compact: overviewCompact });
  const health = useHealth();
  const refreshSummary = useRefreshStatus("today", true, {
    auto: false,
    compact: true,
    poll: false,
  });
  const refreshDiagnostics = useRefreshStatus("today", diagnosticsEnabled, {
    auto: false,
    compact: false,
    poll: false,
  });
  const [preview, setPreview] = useState<PreviewDrawerState>({
    open: false,
    title: "",
  });
  const readinessStatus = refreshDiagnostics.data || refreshSummary.data;
  const feishuChannel = health.data?.channels?.feishu;
  const feishuAvailable = Boolean(feishuChannel?.available);
  const feishuDetail = feishuChannel?.detail || "";
  const readiness = readinessStatus?.readiness;
  const readinessMode =
    readiness?.readiness_mode || readinessStatus?.readiness_mode;
  const readinessCopy = readinessModeCopy(readinessMode);
  const diagnosticsLoading =
    diagnosticsEnabled && refreshDiagnostics.isFetching;

  function enableDiagnostics() {
    setDiagnosticsEnabled(true);
  }

  const refreshOverview = () =>
    queryClient.fetchQuery({
      queryKey: queryKeys.overview(overviewCompact),
      queryFn: () => api.getOverview({ fresh: true, compact: overviewCompact }),
      staleTime: 0,
    });
  const refreshFullStatus = () =>
    queryClient.fetchQuery({
      queryKey: queryKeys.refreshStatus("today", false, false),
      queryFn: () =>
        api.getRefreshStatus("today", { auto: false, compact: false }),
      staleTime: 0,
    });
  function refreshVisibleStatus() {
    void refreshOverview();
    void health.refetch();
    void refreshSummary.refetch();
    if (diagnosticsEnabled) {
      void refreshFullStatus();
    }
  }
  const compactOverviewData = queryClient.getQueryData<OverviewData>(
    queryKeys.overview(true),
  );
  const overviewData = overview.data || compactOverviewData;
  const tasks = overviewData?.tasks || [];
  const safeTasks = safeTaskList(tasks);
  const advancedTasks = advancedTaskList(tasks);

  return (
    <>
      <main className="flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
        <div className="mx-auto max-w-7xl">
          <PageTitle
            eyebrow="Settings"
            title="设置"
            summary="先看今天数据是否可信，再运行安全刷新；高级任务和危险写入已隔离。"
            icon={Settings}
            badge={
              readinessMode
                ? readinessCopy.title
                : health.data?.ok
                  ? "系统正常"
                  : "待检查"
            }
            actions={
              <button
                type="button"
                className="focus-ring prism-btn prism-btn-secondary"
                onClick={refreshVisibleStatus}
              >
                <RefreshCw
                  size={14}
                  className={
                    overview.isFetching ||
                    health.isFetching ||
                    refreshSummary.isFetching ||
                    diagnosticsLoading
                      ? "animate-spin"
                      : ""
                  }
                />
                刷新
              </button>
            }
          />

          {overview.isError || health.isError ? (
            <ErrorState message="系统状态暂不可用" />
          ) : null}

          <section className="mb-7 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              label="后端健康"
              value={health.data?.ok ? "OK" : "未知"}
              detail={health.data?.workspace || "等待 /healthz"}
              tone={health.data?.ok ? "positive" : "watch"}
            />
            <MetricCard
              label="交易可用性"
              value={
                readiness
                  ? readinessCopy.realMoney
                  : readinessMode
                    ? "诊断待加载"
                    : "读取中"
              }
              detail={
                readiness?.session?.label ||
                (readinessStatus ? "轻量刷新状态已返回" : "等待 refresh/status")
              }
              tone={readinessMode ? readinessCopy.tone : "watch"}
            />
            <MetricCard
              label="安全刷新"
              value={String(safeTasks.length)}
              detail="日常可用入口"
              tone="info"
            />
            <MetricCard
              label="最近运行"
              value={diagnosticsEnabled ? "诊断中" : "稍后"}
              detail="诊断层按需加载"
              tone="watch"
            />
            <MetricCard
              label="刷新源"
              value={String(overview.data?.freshness?.length || 0)}
              detail={overview.data?.generated_at || "等待总览"}
              tone={
                (readiness?.stale_count || readinessStatus?.stale_count || 0) >
                0
                  ? "warning"
                  : "positive"
              }
            />
            <MetricCard
              label="Tushare 资产"
              value={diagnosticsEnabled ? "诊断中" : "稍后"}
              detail="数据资产面板按需加载"
              tone="watch"
            />
          </section>

          <section className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
            <div className="flex flex-col gap-6">
              <ReadinessStatusPanel
                status={readinessStatus}
                diagnosticsLoading={diagnosticsLoading}
                onLoadDiagnostics={enableDiagnostics}
              />
              <SettingsSafeRefreshPanel
                status={readinessStatus}
                tasks={safeTasks}
              />
              {diagnosticsEnabled ? (
                <SettingsDiagnosticsMain
                  status={refreshDiagnostics.data}
                  onPreview={setPreview}
                />
              ) : null}
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
                      <Activity
                        size={18}
                        className={
                          health.data?.ok
                            ? "text-[var(--positive)]"
                            : "text-[var(--warning)]"
                        }
                      />
                    </div>
                    <div>
                      <div className="font-medium text-[var(--text-primary)]">
                        {health.data?.ok ? "FastAPI 已连接" : "等待健康检查"}
                      </div>
                      <div className="mt-1 text-[12px] text-[var(--text-tertiary)]">
                        {health.data?.workspace || "http://localhost:8000"}
                      </div>
                    </div>
                  </div>
                  <Badge tone={health.data?.ok ? "positive" : "warning"}>
                    {health.data?.ok ? "online" : "unknown"}
                  </Badge>
                  <div className="mt-3 text-[12px] text-[var(--text-secondary)]">
                    飞书通道：{feishuAvailable ? "可用" : "未就绪"}
                  </div>
                  <div className="mt-1 text-[12px] text-[var(--text-tertiary)]">
                    {feishuDetail || "等待飞书状态检查"}
                  </div>
                </div>
              </Panel>

              {advancedTasksOpen ? (
                <SettingsDiagnosticsAside
                  tasks={advancedTasks}
                  feishuAvailable={feishuAvailable}
                  feishuDetail={feishuDetail}
                  onPreview={setPreview}
                  showAdvancedTasks
                  showLedger={diagnosticsEnabled}
                />
              ) : (
                <Panel title="高级任务" eyebrow="Advanced Tasks">
                  <div className="surface-card p-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="text-sm font-medium text-[var(--text-primary)]">
                          {advancedTasks.length
                            ? `${advancedTasks.length} 个高级任务`
                            : "暂无高级任务"}
                        </div>
                        <div className="mt-1 text-[12px] text-[var(--text-tertiary)]">
                          日常刷新优先使用左侧安全入口。
                        </div>
                      </div>
                      <button
                        type="button"
                        className="focus-ring prism-btn prism-btn-secondary"
                        onClick={() => setAdvancedTasksOpen(true)}
                        disabled={!advancedTasks.length}
                      >
                        <ChevronRight size={14} />
                        展开
                      </button>
                    </div>
                  </div>
                </Panel>
              )}

              {diagnosticsEnabled && !advancedTasksOpen ? (
                <SettingsDiagnosticsAside
                  tasks={advancedTasks}
                  feishuAvailable={feishuAvailable}
                  feishuDetail={feishuDetail}
                  onPreview={setPreview}
                  showLedger
                />
              ) : null}

              <DeferredParametersPanel />

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
      {preview.open ? (
        <SettingsPreviewDrawer
          state={preview}
          onClose={() => setPreview((current) => ({ ...current, open: false }))}
        />
      ) : null}
    </>
  );
}
