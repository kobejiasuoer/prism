"use client";

import { ExternalLink, Eye, FileText, LoaderCircle, RefreshCw } from "lucide-react";
import { useState } from "react";

import { Badge } from "./badge";
import { EmptyState, Panel } from "./data-card";
import { PreviewDrawer, type PreviewDrawerState } from "./preview-drawer";
import { SourceCard } from "./source-card";
import { api } from "@/lib/api";
import { useRefreshStatus, useTriggerRefresh } from "@/lib/hooks";
import { formatCooldown, readinessModeCopy, refreshReasonCopy, refreshReasonLabel } from "@/lib/readiness-copy";
import type { BasicCard, SourceCardData } from "@/lib/types";

type EvidenceRefreshPage = "today" | "watchlist" | "opportunities" | "review";
type EvidenceMode = "standard" | "ask";

function artifactPath(card: BasicCard) {
  if (card.path) {
    return card.path;
  }
  if (!card.url) {
    return "";
  }
  const [, query = ""] = card.url.split("?");
  return new URLSearchParams(query).get("path") || "";
}

function artifactTitle(card: BasicCard) {
  return card.title || card.label || card.detail_link_text || "原始文件";
}

export function EvidencePanel({
  page,
  mode = "standard",
  stockCode,
  sources,
  artifacts,
  title = "证据与刷新",
  eyebrow = "Evidence",
}: {
  page?: EvidenceRefreshPage;
  mode?: EvidenceMode;
  stockCode?: string;
  sources?: SourceCardData[];
  artifacts?: BasicCard[];
  title?: string;
  eyebrow?: string;
}) {
  const refreshPage = mode === "ask" ? "" : page || "";
  const refresh = useRefreshStatus(refreshPage, Boolean(refreshPage), { auto: true });
  const trigger = useTriggerRefresh(refreshPage, { stockCode });
  const [message, setMessage] = useState("");
  const [preview, setPreview] = useState<PreviewDrawerState>({
    open: false,
    title: "",
  });

  const mergedSources = refresh.data?.freshness?.length ? refresh.data.freshness : sources || [];
  const artifactCards = (artifacts || []).filter((card) => artifactPath(card) || card.url);
  const canRefresh = Boolean(refreshPage && refresh.data?.recommended_task?.task_name);
  const isCooling = Boolean(refresh.data && !refresh.data.cooldown?.ready);
  const runningCount = refresh.data?.running?.length || 0;
  const autoDecision = refresh.data?.auto_refresh;
  const blockedReasons = autoDecision?.blocked_reasons || [];
  const autoReasons = autoDecision?.reason_codes || [];
  const lastAuto = refresh.data?.last_auto_refresh;
  const readinessCopy = readinessModeCopy(refresh.data?.readiness_mode);
  const firstReason = (blockedReasons.length ? blockedReasons : autoReasons)[0];
  const firstReasonDetail = firstReason ? refreshReasonCopy(firstReason).detail : "";

  async function openArtifact(card: BasicCard) {
    const path = artifactPath(card);
    if (!path && card.url) {
      window.open(card.url, "_blank", "noopener,noreferrer");
      return;
    }
    setPreview({
      open: true,
      title: artifactTitle(card),
      subtitle: path,
      loading: true,
      kind: "artifact",
    });
    try {
      const payload = await api.preview(path);
      setPreview({
        open: true,
        title: payload.name || artifactTitle(card),
        subtitle: payload.path,
        text: payload.text,
        kind: payload.kind,
        truncated: payload.truncated,
      });
    } catch (error) {
      setPreview({
        open: true,
        title: artifactTitle(card),
        subtitle: path,
        kind: "artifact",
        error: error instanceof Error ? error.message : "预览失败",
      });
    }
  }

  async function openRunLog(runId: string) {
    setPreview({
      open: true,
      title: `运行日志 ${runId}`,
      subtitle: runId,
      loading: true,
      kind: "log",
    });
    try {
      const text = await api.getRunLog(runId);
      setPreview({
        open: true,
        title: `运行日志 ${runId}`,
        subtitle: runId,
        text,
        kind: "log",
      });
    } catch (error) {
      setPreview({
        open: true,
        title: `运行日志 ${runId}`,
        subtitle: runId,
        kind: "log",
        error: error instanceof Error ? error.message : "日志读取失败",
      });
    }
  }

  function startRefresh(force = false) {
    if (!refreshPage) {
      return;
    }
    setMessage("");
    trigger.mutate(
      { force, reason: force ? "manual_force_from_evidence_panel" : "manual_from_evidence_panel" },
      {
        onSuccess: (payload) => {
          setMessage(`${payload.task.title || payload.task.task_name} 已启动`);
        },
        onError: (error) => {
          setMessage(error instanceof Error ? error.message : "刷新启动失败");
        },
      },
    );
  }

  return (
    <>
      <Panel
        title={title}
        eyebrow={eyebrow}
        action={
          canRefresh ? (
            <div className="flex shrink-0 items-center gap-2">
              {isCooling ? (
                <button
                  type="button"
                  className="focus-ring rounded-md border border-[var(--border-subtle)] px-2.5 py-1.5 text-[12px] text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
                  onClick={() => startRefresh(true)}
                  disabled={trigger.isPending}
                >
                  强制
                </button>
              ) : null}
              <button
                type="button"
                className="focus-ring inline-flex items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-1.5 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] disabled:cursor-not-allowed disabled:opacity-50"
                onClick={() => startRefresh(false)}
                disabled={trigger.isPending || runningCount > 0 || isCooling}
              >
                {trigger.isPending ? <LoaderCircle size={13} className="animate-spin" /> : <RefreshCw size={13} />}
                刷新
              </button>
            </div>
          ) : null
        }
      >
        <div className="surface-card p-4">
          <div className="mb-4 flex flex-wrap items-center gap-2">
            {refreshPage && refresh.data ? (
              <>
                <Badge tone={refresh.data.stale_count ? "warning" : "positive"}>
                  {refresh.data.market_label}
                </Badge>
                <Badge tone={refresh.data.stale_count ? "warning" : "positive"}>
                  过期源 {refresh.data.stale_count}
                </Badge>
                {refresh.data.readiness_mode ? <Badge tone={readinessCopy.tone}>{readinessCopy.title}</Badge> : null}
                {refresh.data.recommended_task?.task_name ? (
                  <Badge tone={refresh.data.recommended_task.kind === "lightweight" ? "info" : "watch"}>
                    建议 {refresh.data.recommended_task.title || refresh.data.recommended_task.task_name}
                  </Badge>
                ) : null}
                {runningCount ? <Badge tone="watch">运行中 {runningCount}</Badge> : null}
                {isCooling ? (
                  <Badge tone="watch">冷却 {refresh.data.cooldown.remaining_seconds}s</Badge>
                ) : null}
                {autoDecision?.triggered ? <Badge tone="positive">已自动补刷</Badge> : null}
              </>
            ) : mode === "ask" ? (
              <>
                <Badge tone="warning">Ask 临时证据</Badge>
                <Badge tone="info">仅展示页内来源</Badge>
              </>
            ) : (
              <Badge tone="info">页内证据</Badge>
            )}
            {message ? <span className="text-[12px] text-[var(--text-tertiary)]">{message}</span> : null}
          </div>

          {refreshPage && refresh.data ? (
            <div className="mb-4 grid grid-cols-1 gap-2 lg:grid-cols-2">
              <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
                <div className="flex flex-wrap items-center gap-2 text-[12px] text-[var(--text-secondary)]">
                  <span className="font-medium text-[var(--text-primary)]">自动刷新</span>
                  <Badge tone={autoDecision?.allowed ? "positive" : "watch"}>
                    {autoDecision?.allowed ? "允许自动补刷" : "未自动补刷"}
                  </Badge>
                  <span>冷却 {formatCooldown(refresh.data.cooldown?.remaining_seconds)}</span>
                  {refresh.data.cooldown?.next_allowed_at ? <span>下次 {refresh.data.cooldown.next_allowed_at}</span> : null}
                </div>
                <div className="mt-1 text-[12px] leading-5 text-[var(--text-tertiary)]">
                  {autoDecision?.summary || "等待刷新策略判断。"}
                </div>
                {firstReasonDetail ? (
                  <div className="mt-1 text-[12px] leading-5 text-[var(--text-tertiary)]">
                    {firstReasonDetail}
                  </div>
                ) : null}
                {blockedReasons.length ? (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {blockedReasons.slice(0, 4).map((reason) => (
                      <Badge key={reason} tone="warning">{refreshReasonLabel(reason)}</Badge>
                    ))}
                  </div>
                ) : autoReasons.length ? (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {autoReasons.slice(0, 4).map((reason) => (
                      <Badge key={reason} tone="info">{refreshReasonLabel(reason)}</Badge>
                    ))}
                  </div>
                ) : null}
              </div>

              <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
                <div className="flex flex-wrap items-center gap-2 text-[12px] text-[var(--text-secondary)]">
                  <span className="font-medium text-[var(--text-primary)]">最近自动刷新</span>
                  {lastAuto?.task_name ? <Badge tone="info">{lastAuto.task_name}</Badge> : <Badge tone="watch">暂无</Badge>}
                  {lastAuto?.force ? <Badge tone="warning">force</Badge> : null}
                </div>
                <div className="mt-1 text-[12px] leading-5 text-[var(--text-tertiary)]">
                  {lastAuto ? `${lastAuto.ts || "-"} · ${lastAuto.reason || "-"}` : "还没有自动刷新审计事件。"}
                </div>
                {refresh.data.active_auto_windows?.length ? (
                  <div className="mt-2 text-[11px] text-[var(--text-tertiary)]">
                    当前窗口：{refresh.data.active_auto_windows.map((window) => window.label).join(" / ")}
                  </div>
                ) : (
                  <div className="mt-2 text-[11px] text-[var(--text-tertiary)]">当前不在自动刷新窗口。</div>
                )}
              </div>
            </div>
          ) : null}

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <div>
              <div className="mb-2 text-[12px] font-medium text-[var(--text-primary)]">新鲜度</div>
              <div className="flex flex-col gap-2">
                {mergedSources.map((source, index) => (
                  <SourceCard key={`${source.label}-${index}`} source={source} />
                ))}
                {!mergedSources.length ? <EmptyState>暂无新鲜度状态。</EmptyState> : null}
              </div>
            </div>

            <div>
              <div className="mb-2 text-[12px] font-medium text-[var(--text-primary)]">回源入口</div>
              <div className="flex flex-col gap-2">
                {artifactCards.map((card, index) => (
                  <div
                    key={`${artifactTitle(card)}-${index}`}
                    className="flex items-center gap-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2"
                  >
                    <FileText size={14} className="shrink-0 text-[var(--text-tertiary)]" />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[12px] text-[var(--text-primary)]">{artifactTitle(card)}</div>
                      <div className="mono truncate text-[11px] text-[var(--text-tertiary)]">
                        {artifactPath(card) || card.url}
                      </div>
                    </div>
                    <button
                      type="button"
                      className="focus-ring flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-[var(--text-tertiary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
                      onClick={() => void openArtifact(card)}
                      aria-label="页内预览"
                    >
                      <Eye size={14} />
                    </button>
                    {card.url ? (
                      <a
                        href={card.url}
                        target="_blank"
                        rel="noreferrer"
                        className="focus-ring flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-[var(--text-tertiary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
                        aria-label="打开原始文件"
                      >
                        <ExternalLink size={14} />
                      </a>
                    ) : null}
                  </div>
                ))}
                {refresh.data?.cooldown?.last_run_id ? (
                  <button
                    type="button"
                    className="focus-ring flex items-center gap-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-left hover:border-[var(--border-default)]"
                    onClick={() => void openRunLog(String(refresh.data?.cooldown?.last_run_id))}
                  >
                    <FileText size={14} className="shrink-0 text-[var(--text-tertiary)]" />
                    <span className="min-w-0 flex-1">
                      <span className="block text-[12px] text-[var(--text-primary)]">最近刷新日志</span>
                      <span className="mono block truncate text-[11px] text-[var(--text-tertiary)]">
                        {refresh.data.cooldown.last_run_id}
                      </span>
                    </span>
                    <Eye size={14} className="text-[var(--text-tertiary)]" />
                  </button>
                ) : null}
                {!artifactCards.length && !refresh.data?.cooldown?.last_run_id ? (
                  <EmptyState>暂无 artifacts 或日志入口。</EmptyState>
                ) : null}
              </div>
            </div>
          </div>
        </div>
      </Panel>
      <PreviewDrawer state={preview} onClose={() => setPreview((current) => ({ ...current, open: false }))} />
    </>
  );
}
