"use client";

import {
  Archive,
  LoaderCircle,
  Plus,
  RefreshCw,
  RotateCcw,
} from "lucide-react";
import { useEffect } from "react";

import {
  useAddWatchlistStock,
  useArchiveWatchlistStock,
  useRestoreWatchlistStock,
  useWatchlistManager,
} from "@/lib/hooks";
import type { WatchlistManagerItem } from "@/lib/types";

export type StockWatchlistActionsProps = {
  code: string;
  stockName: string;
  onFeedback: (message: string) => void;
  onResolvedName: (name: string) => void;
};

function findManagerItem(
  items: WatchlistManagerItem[] | undefined,
  code: string,
) {
  return (items || []).find((item) => item.code === code);
}

function actionButtonClass(extra = "") {
  return [
    "focus-ring inline-flex min-h-9 min-w-[104px] items-center justify-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] disabled:cursor-not-allowed disabled:opacity-50",
    extra,
  ]
    .filter(Boolean)
    .join(" ");
}

export function StockWatchlistActions({
  code,
  stockName,
  onFeedback,
  onResolvedName,
}: StockWatchlistActionsProps) {
  const managerQuery = useWatchlistManager({ enabled: true });
  const addStock = useAddWatchlistStock();
  const archiveStock = useArchiveWatchlistStock();
  const restoreStock = useRestoreWatchlistStock();
  const manager = managerQuery.data?.manager;
  const activeManagerItem = findManagerItem(manager?.active_items, code);
  const archivedManagerItem = findManagerItem(manager?.archived_items, code);
  const busy =
    addStock.isPending || archiveStock.isPending || restoreStock.isPending;
  const managerLoading = managerQuery.isLoading && !manager;

  useEffect(() => {
    const resolvedName = activeManagerItem?.name || archivedManagerItem?.name;
    if (resolvedName && resolvedName !== code) {
      onResolvedName(resolvedName);
    }
  }, [
    activeManagerItem?.name,
    archivedManagerItem?.name,
    code,
    onResolvedName,
  ]);

  function onManage(action: "add" | "archive" | "restore") {
    onFeedback("");
    if (action === "add") {
      addStock.mutate(
        { code, name: stockName, trigger_refresh: true },
        {
          onSuccess: (payload) => onFeedback(payload.message || "已加入持仓。"),
          onError: (error) =>
            onFeedback(error instanceof Error ? error.message : "加入失败"),
        },
      );
      return;
    }

    if (action === "archive") {
      archiveStock.mutate(
        { code, trigger_refresh: true },
        {
          onSuccess: (payload) => onFeedback(payload.message || "已归档。"),
          onError: (error) =>
            onFeedback(error instanceof Error ? error.message : "归档失败"),
        },
      );
      return;
    }

    restoreStock.mutate(
      { code, trigger_refresh: true },
      {
        onSuccess: (payload) => onFeedback(payload.message || "已恢复持仓。"),
        onError: (error) =>
          onFeedback(error instanceof Error ? error.message : "恢复失败"),
      },
    );
  }

  if (managerLoading) {
    return (
      <button type="button" className={actionButtonClass()} disabled>
        <LoaderCircle size={14} className="animate-spin" />
        名单同步中
      </button>
    );
  }

  if (managerQuery.isError) {
    return (
      <button
        type="button"
        className={actionButtonClass()}
        onClick={() => void managerQuery.refetch()}
      >
        <RefreshCw size={14} />
        名单状态待同步
      </button>
    );
  }

  if (activeManagerItem) {
    return (
      <button
        type="button"
        className={actionButtonClass()}
        onClick={() => onManage("archive")}
        disabled={busy}
      >
        {archiveStock.isPending ? (
          <LoaderCircle size={14} className="animate-spin" />
        ) : (
          <Archive size={14} />
        )}
        归档
      </button>
    );
  }

  if (archivedManagerItem) {
    return (
      <button
        type="button"
        className={actionButtonClass()}
        onClick={() => onManage("restore")}
        disabled={busy}
      >
        {restoreStock.isPending ? (
          <LoaderCircle size={14} className="animate-spin" />
        ) : (
          <RotateCcw size={14} />
        )}
        恢复
      </button>
    );
  }

  return (
    <button
      type="button"
      className={actionButtonClass()}
      onClick={() => onManage("add")}
      disabled={busy}
    >
      {addStock.isPending ? (
        <LoaderCircle size={14} className="animate-spin" />
      ) : (
        <Plus size={14} />
      )}
      加入
    </button>
  );
}
