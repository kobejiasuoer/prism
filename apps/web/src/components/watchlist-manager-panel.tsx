"use client";

import { Archive, Eye, LoaderCircle, Plus, RotateCcw } from "lucide-react";
import type { FormEvent, ReactNode } from "react";
import { useMemo, useState } from "react";

import { Badge } from "./badge";
import { EmptyState, ErrorState, Panel } from "./data-card";
import { MetricCard } from "./metric-card";
import { PreviewDrawer, type PreviewDrawerState } from "./preview-drawer";
import { api } from "@/lib/api";
import {
  useAddWatchlistStock,
  useArchiveWatchlistStock,
  useRestoreWatchlistStock,
  useWatchlistManager,
} from "@/lib/hooks";
import type { WatchlistManagerItem } from "@/lib/types";

function normalizeCode(value: string) {
  return value.trim().replace(/\D/g, "").slice(0, 6);
}

function ManagerItemRow({
  item,
  actionLabel,
  actionIcon,
  disabled,
  onAction,
}: {
  item: WatchlistManagerItem;
  actionLabel: string;
  actionIcon: ReactNode;
  disabled?: boolean;
  onAction: () => void;
}) {
  return (
    <div className="flex items-center gap-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 items-center gap-2">
          <span className="truncate text-[13px] font-medium text-[var(--text-primary)]">{item.name || item.code}</span>
          <span className="mono shrink-0 text-[11px] text-[var(--text-tertiary)]">{item.code}</span>
          {item.market ? <Badge tone="info">{item.market}</Badge> : null}
        </div>
        <div className="mt-1 line-clamp-2 text-[12px] text-[var(--text-secondary)]">
          {item.state_detail || item.state_label || item.updated_at || "-"}
        </div>
      </div>
      <Badge tone={item.tone}>{item.state_label || "名单"}</Badge>
      <button
        type="button"
        className="focus-ring inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-[var(--border-subtle)] text-[var(--text-tertiary)] hover:text-[var(--text-primary)] disabled:cursor-not-allowed disabled:opacity-50"
        onClick={onAction}
        disabled={disabled}
        aria-label={actionLabel}
      >
        {actionIcon}
      </button>
    </div>
  );
}

export function WatchlistManagerPanel() {
  const managerQuery = useWatchlistManager();
  const addStock = useAddWatchlistStock();
  const archiveStock = useArchiveWatchlistStock();
  const restoreStock = useRestoreWatchlistStock();
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [triggerRefresh, setTriggerRefresh] = useState(true);
  const [feedback, setFeedback] = useState("");
  const [preview, setPreview] = useState<PreviewDrawerState>({
    open: false,
    title: "",
  });

  const manager = managerQuery.data?.manager;
  const busy = addStock.isPending || archiveStock.isPending || restoreStock.isPending;
  const normalizedCode = useMemo(() => normalizeCode(code), [code]);

  function onAdd(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (normalizedCode.length !== 6) {
      setFeedback("请输入 6 位股票代码。");
      return;
    }
    setFeedback("");
    addStock.mutate(
      {
        code: normalizedCode,
        name: name.trim() || undefined,
        trigger_refresh: triggerRefresh,
      },
      {
        onSuccess: (payload) => {
          setFeedback(payload.message || "已更新持仓名单。");
          setCode("");
          setName("");
        },
        onError: (error) => setFeedback(error instanceof Error ? error.message : "添加失败"),
      },
    );
  }

  function archive(codeToArchive: string) {
    setFeedback("");
    archiveStock.mutate(
      { code: codeToArchive, trigger_refresh: triggerRefresh },
      {
        onSuccess: (payload) => setFeedback(payload.message || "已归档。"),
        onError: (error) => setFeedback(error instanceof Error ? error.message : "归档失败"),
      },
    );
  }

  function restore(codeToRestore: string) {
    setFeedback("");
    restoreStock.mutate(
      { code: codeToRestore, trigger_refresh: triggerRefresh },
      {
        onSuccess: (payload) => setFeedback(payload.message || "已恢复。"),
        onError: (error) => setFeedback(error instanceof Error ? error.message : "恢复失败"),
      },
    );
  }

  async function openRefreshLog() {
    const logPath = manager?.refresh_status?.log_path;
    if (!logPath) {
      return;
    }
    setPreview({
      open: true,
      title: "自选股刷新日志",
      subtitle: logPath,
      loading: true,
      kind: "log",
    });
    try {
      const payload = await api.preview(logPath);
      setPreview({
        open: true,
        title: payload.name || "自选股刷新日志",
        subtitle: payload.path,
        text: payload.text,
        kind: payload.kind,
        truncated: payload.truncated,
      });
    } catch (error) {
      setPreview({
        open: true,
        title: "自选股刷新日志",
        subtitle: logPath,
        kind: "log",
        error: error instanceof Error ? error.message : "日志读取失败",
      });
    }
  }

  return (
    <>
      <Panel
        title="名单管理"
        eyebrow="Watchlist Manager"
        action={
          <button
            type="button"
            className="focus-ring rounded-md border border-[var(--border-subtle)] px-3 py-1.5 text-[12px] text-[var(--text-secondary)]"
            onClick={() => void managerQuery.refetch()}
          >
            刷新名单
          </button>
        }
      >
        {managerQuery.isError ? <ErrorState message="持仓管理接口暂不可用" onRetry={() => void managerQuery.refetch()} /> : null}

        <div className="surface-card p-4">
          <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
            {(manager?.summary_cards || []).map((card) => (
              <MetricCard key={card.label} {...card} tone={card.tone || "info"} />
            ))}
          </div>

          <form className="mb-4 grid grid-cols-1 gap-3 lg:grid-cols-[160px_minmax(0,1fr)_auto]" onSubmit={onAdd}>
            <input
              value={code}
              onChange={(event) => setCode(normalizeCode(event.target.value))}
              placeholder="股票代码"
              className="focus-ring h-10 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 text-[13px] text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)]"
              inputMode="numeric"
            />
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="名称，可选"
              className="focus-ring h-10 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 text-[13px] text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)]"
            />
            <button
              type="submit"
              className="focus-ring inline-flex h-10 items-center justify-center gap-2 rounded-md bg-[var(--text-primary)] px-4 text-[13px] font-medium text-[var(--text-inverse)] disabled:cursor-not-allowed disabled:opacity-50"
              disabled={busy}
            >
              {addStock.isPending ? <LoaderCircle size={15} className="animate-spin" /> : <Plus size={15} />}
              添加
            </button>
          </form>

          <label className="mb-4 flex items-center gap-2 text-[12px] text-[var(--text-secondary)]">
            <input
              type="checkbox"
              checked={triggerRefresh}
              onChange={(event) => setTriggerRefresh(event.target.checked)}
              className="h-4 w-4 accent-[var(--info)]"
            />
            名单变更后自动触发自选股刷新
          </label>

          {feedback ? (
            <div className="mb-4 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
              {feedback}
            </div>
          ) : null}

          <div className="mb-5 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3">
            <div className="mb-2 flex items-center justify-between gap-3">
              <div>
                <div className="text-[12px] font-medium text-[var(--text-primary)]">
                  {manager?.refresh_status?.label || "刷新状态"}
                </div>
                <div className="mt-1 text-[12px] text-[var(--text-tertiary)]">
                  {manager?.refresh_status?.detail || manager?.feedback_hint || "等待刷新状态。"}
                </div>
              </div>
              {manager?.refresh_status?.log_path ? (
                <button
                  type="button"
                  className="focus-ring inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-[var(--border-subtle)] text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
                  onClick={() => void openRefreshLog()}
                  aria-label="查看刷新日志"
                >
                  <Eye size={14} />
                </button>
              ) : null}
            </div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
              {(manager?.refresh_status?.steps || []).map((step, index) => (
                <div key={`${step.label}-${index}`} className="rounded-md border border-[var(--border-subtle)] px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-[12px] text-[var(--text-primary)]">{step.label || `步骤 ${index + 1}`}</span>
                    <Badge tone={step.state === "done" ? "positive" : step.state === "running" ? "watch" : "info"}>
                      {step.state || "pending"}
                    </Badge>
                  </div>
                  {step.detail ? <div className="mt-1 line-clamp-2 text-[11px] text-[var(--text-tertiary)]">{step.detail}</div> : null}
                </div>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
            <div>
              <div className="mb-2 text-[12px] font-medium text-[var(--text-primary)]">活跃持仓池</div>
              <div className="flex flex-col gap-2">
                {(manager?.active_items || []).map((item) => (
                  <ManagerItemRow
                    key={item.code}
                    item={item}
                    actionLabel="归档"
                    actionIcon={archiveStock.isPending ? <LoaderCircle size={14} className="animate-spin" /> : <Archive size={14} />}
                    disabled={busy}
                    onAction={() => archive(item.code)}
                  />
                ))}
                {!manager?.active_items?.length ? <EmptyState>{manager?.empty_active || "暂无活跃自选股。"}</EmptyState> : null}
              </div>
            </div>

            <div>
              <div className="mb-2 text-[12px] font-medium text-[var(--text-primary)]">归档列表</div>
              <div className="flex flex-col gap-2">
                {(manager?.archived_items || []).map((item) => (
                  <ManagerItemRow
                    key={item.code}
                    item={item}
                    actionLabel="恢复"
                    actionIcon={restoreStock.isPending ? <LoaderCircle size={14} className="animate-spin" /> : <RotateCcw size={14} />}
                    disabled={busy}
                    onAction={() => restore(item.code)}
                  />
                ))}
                {!manager?.archived_items?.length ? <EmptyState>{manager?.empty_archived || "暂无归档股票。"}</EmptyState> : null}
              </div>
            </div>
          </div>
        </div>
      </Panel>
      <PreviewDrawer state={preview} onClose={() => setPreview((current) => ({ ...current, open: false }))} />
    </>
  );
}
