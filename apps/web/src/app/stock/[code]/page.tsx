"use client";

import { Archive, FileSearch, LoaderCircle, Plus, RefreshCw, RotateCcw, SendHorizontal } from "lucide-react";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { Badge } from "@/components/badge";
import { DataCard, EmptyState, ErrorState, Panel, SkeletonBlock } from "@/components/data-card";
import { EvidencePanel } from "@/components/evidence-panel";
import { MetricCard, MetricSkeleton } from "@/components/metric-card";
import { PageTitle } from "@/components/page-title";
import { api } from "@/lib/api";
import {
  useAddWatchlistStock,
  useArchiveWatchlistStock,
  useAsk,
  useRestoreWatchlistStock,
  useStockProfile,
  useWatchlistManager,
} from "@/lib/hooks";
import type { AskFollowupResponse, StockDetailData, WatchlistManagerItem } from "@/lib/types";
import { cn } from "@/lib/utils";

const tabs = ["决策", "追问", "持仓", "发现", "证据"] as const;
const followupHistoryTurnLimit = 3;

function pickDetail(watchlist?: StockDetailData, opportunity?: StockDetailData, activeTab?: string) {
  if (activeTab === "发现" && opportunity) {
    return opportunity;
  }
  return watchlist || opportunity;
}

function findManagerItem(items: WatchlistManagerItem[] | undefined, code: string) {
  return (items || []).find((item) => item.code === code);
}

function historyPayload(messages: AskFollowupResponse[]) {
  return messages.slice(-followupHistoryTurnLimit).flatMap((item) => [
    {
      role: "user",
      title: "继续追问",
      summary: item.question,
    },
    {
      role: "assistant",
      title: item.answer?.title || "追问回答",
      summary: item.answer?.summary || "",
      bullets: (item.answer?.bullets || []).slice(0, 4),
      references: (item.answer?.references || []).slice(0, 3),
      engine_label: item.answer?.engine_label || "",
    },
  ]);
}

export default function StockProfilePage() {
  const params = useParams<{ code: string }>();
  const code = String(params.code || "");
  const profile = useStockProfile(code);
  const ask = useAsk(code);
  const managerQuery = useWatchlistManager();
  const addStock = useAddWatchlistStock();
  const archiveStock = useArchiveWatchlistStock();
  const restoreStock = useRestoreWatchlistStock();
  const [activeTab, setActiveTab] = useState<(typeof tabs)[number]>("决策");
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<AskFollowupResponse[]>([]);
  const [pendingQuestion, setPendingQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [askError, setAskError] = useState("");
  const [manageFeedback, setManageFeedback] = useState("");
  const threadEndRef = useRef<HTMLDivElement | null>(null);
  const detail = pickDetail(profile.data?.watchlist, profile.data?.opportunity, activeTab);
  const askCase = ask.data?.case;
  const manager = managerQuery.data?.manager;
  const activeManagerItem = findManagerItem(manager?.active_items, code);
  const archivedManagerItem = findManagerItem(manager?.archived_items, code);
  const manageBusy = addStock.isPending || archiveStock.isPending || restoreStock.isPending;
  const stockName = detail?.name || activeManagerItem?.name || archivedManagerItem?.name || askCase?.name || code;
  const followupShell = ask.data?.followup || askCase?.evidence_layer?.followup || null;
  const allMetricCards = useMemo(() => {
    if (!detail) {
      return [];
    }
    return [
      ...(detail.decision_cards || []),
      ...(detail.metric_cards || []),
      ...(detail.meta_cards || []),
      ...(detail.level_cards || []),
    ];
  }, [detail]);
  const askFallbackCards = [
    ...(askCase?.decision_cards || []),
    ...(askCase?.metric_cards || []),
    ...(askCase?.level_cards || []),
  ];
  const latestFollowups = messages.at(-1)?.answer?.followups || [];
  const presetQuestions = (followupShell?.presets || [])
    .map((item) => ({
      label: item.label || item.question,
      value: item.question,
    }))
    .filter((item) => item.value);
  const suggestedQuestions =
    latestFollowups.length
      ? latestFollowups.map((item) => ({ label: item, value: item }))
      : presetQuestions.length
        ? presetQuestions
      : [
          "这只今天要不要动？",
          "仓位和止损怎么设？",
          "最大的反向风险是什么？",
          "结论对应哪些证据？",
        ].map((item) => ({ label: item, value: item }));

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ block: "nearest" });
  }, [messages, pendingQuestion]);

  async function submitFollowup(value?: string) {
    const text = (value ?? question).trim();
    if (!text || asking) {
      return;
    }
    setAsking(true);
    setAskError("");
    setPendingQuestion(text);
    try {
      const payload = await api.askFollowup({
        query: code,
        question: text,
        history: historyPayload(messages),
      });
      setMessages((current) => [...current, payload]);
      setQuestion("");
      setActiveTab("追问");
    } catch (error) {
      setAskError(error instanceof Error ? error.message : "追问失败");
    } finally {
      setPendingQuestion("");
      setAsking(false);
    }
  }

  function onManage(action: "add" | "archive" | "restore") {
    setManageFeedback("");
    if (action === "add") {
      addStock.mutate(
        { code, name: detail?.name, trigger_refresh: true },
        {
          onSuccess: (payload) => setManageFeedback(payload.message || "已加入持仓。"),
          onError: (error) => setManageFeedback(error instanceof Error ? error.message : "加入失败"),
          onSettled: () => void profile.refetch(),
        },
      );
    } else if (action === "archive") {
      archiveStock.mutate(
        { code, trigger_refresh: true },
        {
          onSuccess: (payload) => setManageFeedback(payload.message || "已归档。"),
          onError: (error) => setManageFeedback(error instanceof Error ? error.message : "归档失败"),
          onSettled: () => void profile.refetch(),
        },
      );
    } else {
      restoreStock.mutate(
        { code, trigger_refresh: true },
        {
          onSuccess: (payload) => setManageFeedback(payload.message || "已恢复持仓。"),
          onError: (error) => setManageFeedback(error instanceof Error ? error.message : "恢复失败"),
          onSettled: () => void profile.refetch(),
        },
      );
    }
  }

  return (
    <main className="flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
      <div className="mx-auto max-w-7xl">
        <PageTitle
          eyebrow={detail?.trade_date || askCase?.trade_date || code}
          title={detail?.hero?.title || askCase?.hero?.title || `${stockName || "个股档案"} · ${code}`}
          summary={detail?.hero?.summary || detail?.topline?.verdict_summary || askCase?.hero?.summary || "统一查看这只股票的决策、持仓、发现和证据。"}
          icon={FileSearch}
          badge={detail?.hero?.status_label || detail?.topline?.verdict_badge || askCase?.hero?.status_label || askCase?.hero?.decision_label || "个股档案"}
          actions={
            <div className="flex flex-wrap items-center gap-2">
              {activeManagerItem ? (
                <button
                  type="button"
                  className="focus-ring inline-flex items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] disabled:cursor-not-allowed disabled:opacity-50"
                  onClick={() => onManage("archive")}
                  disabled={manageBusy}
                >
                  {archiveStock.isPending ? <LoaderCircle size={14} className="animate-spin" /> : <Archive size={14} />}
                  归档
                </button>
              ) : archivedManagerItem ? (
                <button
                  type="button"
                  className="focus-ring inline-flex items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] disabled:cursor-not-allowed disabled:opacity-50"
                  onClick={() => onManage("restore")}
                  disabled={manageBusy}
                >
                  {restoreStock.isPending ? <LoaderCircle size={14} className="animate-spin" /> : <RotateCcw size={14} />}
                  恢复
                </button>
              ) : (
                <button
                  type="button"
                  className="focus-ring inline-flex items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] disabled:cursor-not-allowed disabled:opacity-50"
                  onClick={() => onManage("add")}
                  disabled={manageBusy}
                >
                  {addStock.isPending ? <LoaderCircle size={14} className="animate-spin" /> : <Plus size={14} />}
                  加入
                </button>
              )}
              <button
                type="button"
                className="focus-ring inline-flex items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)]"
                onClick={() => void profile.refetch()}
              >
                <RefreshCw size={14} className={profile.isFetching ? "animate-spin" : ""} />
                刷新
              </button>
            </div>
          }
        />

        {profile.isError ? <ErrorState message="个股详情暂不可用" onRetry={() => void profile.refetch()} /> : null}
        {manageFeedback ? (
          <div className="mb-5 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
            {manageFeedback}
          </div>
        ) : null}
        {!profile.isLoading && !ask.isLoading && !detail && !askCase ? <EmptyState>当前股票不在持仓或观察池详情中。</EmptyState> : null}

        <div className="mb-6 flex gap-2 overflow-x-auto rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-1">
          {tabs.map((tab) => (
            <button
              key={tab}
              type="button"
              className={cn(
                "focus-ring shrink-0 rounded-[6px] px-4 py-2 text-[13px]",
                activeTab === tab ? "bg-[var(--bg-tertiary)] text-[var(--text-primary)]" : "text-[var(--text-tertiary)]",
              )}
              onClick={() => setActiveTab(tab)}
            >
              {tab}
            </button>
          ))}
        </div>

        {profile.isLoading && !detail ? (
          <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {Array.from({ length: 4 }).map((_, index) => <MetricSkeleton key={index} />)}
          </section>
        ) : null}

        {activeTab === "追问" ? (
          <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
            <Panel title="当前结论" eyebrow="Ask Context">
              <div className="surface-card p-4">
                {ask.isLoading ? (
                  <SkeletonBlock className="h-32 w-full" />
                ) : askCase ? (
                  <div className="flex flex-col gap-4">
                    <div>
                      <div className="mb-2 flex flex-wrap items-center gap-2">
                        <Badge tone="info">{stockName}</Badge>
                        {askCase.hero?.status_label ? <Badge tone="watch">{askCase.hero.status_label}</Badge> : null}
                      </div>
                      <h2 className="text-lg font-semibold text-[var(--text-primary)]">
                        {askCase.hero?.title || `${stockName} ${code}`}
                      </h2>
                      <p className="mt-2 text-[13px] leading-6 text-[var(--text-secondary)]">
                        {askCase.hero?.summary || "暂无问股摘要，直接输入问题继续追问。"}
                      </p>
                    </div>

                    {(askCase.cross_cards || []).length ? (
                      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                        {askCase.cross_cards?.slice(0, 4).map((card, index) => (
                          <MetricCard key={`${card.label}-${index}`} {...card} tone={card.tone || "info"} />
                        ))}
                      </div>
                    ) : null}

                    {askCase.context_tags?.length ? (
                      <div className="flex flex-wrap gap-2">
                        {askCase.context_tags.map((item) => (
                          <Badge key={item} tone="info">{item}</Badge>
                        ))}
                      </div>
                    ) : null}

                    {askCase.canonical_decision ? (
                      <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3">
                        {Object.entries(askCase.canonical_decision).slice(0, 8).map(([key, value]) => (
                          <div key={key} className="flex gap-3 border-b border-[var(--border-subtle)] py-2 last:border-b-0">
                            <span className="mono w-32 shrink-0 text-[11px] text-[var(--text-tertiary)]">{key}</span>
                            <span className="min-w-0 flex-1 text-[12px] text-[var(--text-secondary)]">{String(value ?? "-")}</span>
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : (
                  <EmptyState>暂无问股上下文，输入问题后会使用规则引擎回答。</EmptyState>
                )}
              </div>
            </Panel>

            <Panel title="连续追问" eyebrow="Follow-up">
              <div className="surface-card flex min-h-[520px] flex-col p-4">
                <div className="min-h-0 flex-1 space-y-3 overflow-auto pr-1">
                  {!messages.length ? (
                    <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3 text-[13px] leading-6 text-[var(--text-secondary)]">
                      {followupShell?.starter?.summary || "可以围绕仓位、买卖点、风险和证据继续问，系统会带着本轮对话上下文回答。"}
                      {followupShell?.engine_badge?.label ? (
                        <span className="mt-2 block text-[12px] text-[var(--text-tertiary)]">
                          {followupShell.engine_badge.label}
                          {followupShell.engine_badge.detail ? `：${followupShell.engine_badge.detail}` : ""}
                        </span>
                      ) : null}
                    </div>
                  ) : null}
                  {messages.map((item, index) => (
                    <div key={`${item.question}-${index}`} className="space-y-2">
                      <div className="ml-auto max-w-[88%] rounded-md bg-[var(--info)] px-3 py-2 text-[13px] leading-6 text-white">
                        {item.question}
                      </div>
                      <div className="max-w-[92%] rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
                        <div className="mb-1 flex flex-wrap items-center gap-2">
                          <span className="text-[13px] font-medium text-[var(--text-primary)]">
                            {item.answer?.title || "追问回答"}
                          </span>
                          {item.answer?.engine_label ? <Badge tone="info">{item.answer.engine_label}</Badge> : null}
                        </div>
                        <p className="text-[13px] leading-6 text-[var(--text-secondary)]">{item.answer?.summary || "-"}</p>
                        {item.answer?.bullets?.length ? (
                          <ul className="mt-2 list-disc space-y-1 pl-4 text-[12px] leading-5 text-[var(--text-secondary)]">
                            {item.answer.bullets.map((bullet) => (
                              <li key={bullet}>{bullet}</li>
                            ))}
                          </ul>
                        ) : null}
                        {item.answer?.references?.length ? (
                          <div className="mt-3 flex flex-wrap gap-1.5">
                            {item.answer.references.map((ref) => (
                              <Badge key={ref} tone="watch">{ref}</Badge>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    </div>
                  ))}
                  {pendingQuestion ? (
                    <div className="space-y-2">
                      <div className="ml-auto max-w-[88%] rounded-md bg-[var(--info)] px-3 py-2 text-[13px] leading-6 text-white">
                        {pendingQuestion}
                      </div>
                      <div className="inline-flex max-w-[92%] items-center gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3 text-[13px] text-[var(--text-secondary)]">
                        <LoaderCircle size={14} className="animate-spin" />
                        正在整理回答
                      </div>
                    </div>
                  ) : null}
                  <div ref={threadEndRef} />
                </div>

                <div className="mt-4 border-t border-[var(--border-subtle)] pt-4">
                  {suggestedQuestions.length ? (
                    <div className="mb-3 flex flex-wrap gap-2">
                      {suggestedQuestions.slice(0, 4).map((item) => (
                        <button
                          key={`${item.label}-${item.value}`}
                          type="button"
                          className="focus-ring rounded-md border border-[var(--border-subtle)] px-2.5 py-1.5 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                          onClick={() => void submitFollowup(item.value)}
                          disabled={asking}
                        >
                          {item.label}
                        </button>
                      ))}
                    </div>
                  ) : null}
                  <form
                    className="flex items-end gap-2"
                    onSubmit={(event) => {
                      event.preventDefault();
                      void submitFollowup();
                    }}
                  >
                    <textarea
                      value={question}
                      onChange={(event) => setQuestion(event.target.value)}
                      onKeyDown={(event) => {
                        if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                          event.preventDefault();
                          void submitFollowup();
                        }
                      }}
                      placeholder="继续问：仓位怎么控？风险在哪？证据是什么？"
                      className="focus-ring min-h-20 flex-1 resize-y rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[13px] leading-6 text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)]"
                    />
                    <button
                      type="submit"
                      className="focus-ring flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-[var(--text-primary)] text-[var(--text-inverse)] disabled:cursor-not-allowed disabled:opacity-50"
                      disabled={asking || !question.trim()}
                      aria-label="发送追问"
                    >
                      {asking ? <LoaderCircle size={16} className="animate-spin" /> : <SendHorizontal size={16} />}
                    </button>
                  </form>
                  {askError ? (
                    <div className="mt-3 rounded-md border border-[color-mix(in_srgb,var(--negative)_20%,transparent)] bg-[color-mix(in_srgb,var(--negative)_8%,transparent)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
                      {askError}
                    </div>
                  ) : null}
                </div>
              </div>
            </Panel>
          </div>
        ) : null}

        {!detail && askCase && activeTab === "决策" ? (
          <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
            <div className="flex flex-col gap-6">
              <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {askFallbackCards.slice(0, 4).map((card, index) => (
                  <MetricCard key={`${card.label}-${index}`} {...card} tone={index === 0 ? askCase.tone || "info" : card.tone || "watch"} />
                ))}
                {!askFallbackCards.length ? <EmptyState>暂无 Ask 指标卡。</EmptyState> : null}
              </section>

              <Panel
                title="Ask 主结论"
                eyebrow="Fallback"
                action={
                  <button
                    type="button"
                    className="focus-ring rounded-md border border-[var(--border-subtle)] px-3 py-1.5 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                    onClick={() => setActiveTab("追问")}
                  >
                    继续追问
                  </button>
                }
              >
                <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                  {(askCase.execution_loop || []).slice(0, 4).map((card, index) => <DataCard key={`${card.label}-${index}`} card={card} />)}
                  {!askCase.execution_loop?.length ? (
                    <DataCard
                      card={{
                        title: askCase.hero?.decision_label || "当前结论",
                        detail: askCase.hero?.summary || "Ask 已返回单股结论，可进入追问继续拆仓位、风险和证据。",
                        status: askCase.hero?.position,
                        tone: askCase.tone || "watch",
                      }}
                    />
                  ) : null}
                </div>
              </Panel>
            </div>

            <Panel title="决策摘要" eyebrow="Ask Canonical">
              <div className="surface-card p-4">
                {askCase.canonical_decision ? (
                  <div className="flex flex-col gap-2">
                    {Object.entries(askCase.canonical_decision).slice(0, 10).map(([key, value]) => (
                      <div key={key} className="flex gap-3 border-b border-[var(--border-subtle)] py-2 last:border-b-0">
                        <span className="mono w-36 shrink-0 text-[11px] text-[var(--text-tertiary)]">{key}</span>
                        <span className="min-w-0 flex-1 text-[12px] text-[var(--text-secondary)]">{String(value ?? "-")}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <EmptyState>暂无标准化决策。</EmptyState>
                )}
              </div>
            </Panel>
          </div>
        ) : null}

        {detail && activeTab === "决策" ? (
          <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
            <div className="flex flex-col gap-6">
              <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {(detail.decision_cards || []).slice(0, 4).map((card, index) => (
                  <MetricCard key={`${card.label}-${index}`} {...card} tone={index === 0 ? detail.tone || "info" : index === 2 ? "risk" : "watch"} />
                ))}
              </section>

              <Panel title="执行循环" eyebrow="Loop">
                <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                  {(detail.execution_loop || []).map((card, index) => <DataCard key={`${card.label}-${index}`} card={card} />)}
                  {!detail.execution_loop?.length ? <EmptyState>暂无执行循环。</EmptyState> : null}
                </div>
              </Panel>
            </div>

            <Panel title="决策摘要" eyebrow="Canonical">
              <div className="surface-card p-4">
                {detail.canonical_decision ? (
                  <div className="flex flex-col gap-2">
                    {Object.entries(detail.canonical_decision).slice(0, 10).map(([key, value]) => (
                      <div key={key} className="flex gap-3 border-b border-[var(--border-subtle)] py-2 last:border-b-0">
                        <span className="mono w-36 shrink-0 text-[11px] text-[var(--text-tertiary)]">{key}</span>
                        <span className="min-w-0 flex-1 text-[12px] text-[var(--text-secondary)]">{String(value ?? "-")}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <EmptyState>暂无标准化决策。</EmptyState>
                )}
              </div>
            </Panel>
          </div>
        ) : null}

        {detail && activeTab === "持仓" ? (
          <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
            <Panel title="持仓指标" eyebrow="Holdings">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {[...(detail.meta_cards || []), ...(detail.level_cards || [])].slice(0, 8).map((card, index) => (
                  <MetricCard key={`${card.label}-${index}`} {...card} tone={index >= 4 ? "risk" : "info"} />
                ))}
                {!detail.meta_cards?.length && !detail.level_cards?.length ? <EmptyState>暂无持仓指标。</EmptyState> : null}
              </div>
            </Panel>

            <Panel title="触发条件" eyebrow="Triggers">
              <div className="flex flex-col gap-2">
                {(detail.triggers || []).map((trigger, index) => (
                  <DataCard
                    key={`${trigger.label || index}`}
                    card={{
                      title: trigger.label || `触发 ${index + 1}`,
                      value: trigger.value,
                      detail: trigger.detail,
                      tone: "watch",
                    }}
                  />
                ))}
                {!detail.triggers?.length ? <EmptyState>暂无盘中触发条件。</EmptyState> : null}
              </div>
            </Panel>
          </div>
        ) : null}

        {detail && activeTab === "发现" ? (
          <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
            <Panel title="发现指标" eyebrow="Discovery">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {allMetricCards.slice(0, 8).map((card, index) => (
                  <MetricCard key={`${card.label}-${index}`} {...card} tone={index === 0 ? detail.tone || "watch" : "info"} />
                ))}
                {!allMetricCards.length ? <EmptyState>暂无发现指标。</EmptyState> : null}
              </div>
            </Panel>

            <Panel title="洞察标签" eyebrow="Insights">
              <div className="flex flex-col gap-3">
                {(detail.insight_groups || []).map((group) => (
                  <div key={group.title} className="surface-card p-4">
                    <div className="mb-2 text-sm font-medium text-[var(--text-primary)]">{group.title}</div>
                    <div className="flex flex-wrap gap-2">
                      {group.items?.length ? group.items.map((item) => <Badge key={item} tone="watch">{item}</Badge>) : <span className="text-[12px] text-[var(--text-tertiary)]">{group.empty || "暂无"}</span>}
                    </div>
                  </div>
                ))}
                {!detail.insight_groups?.length ? <EmptyState>暂无洞察标签。</EmptyState> : null}
              </div>
            </Panel>
          </div>
        ) : null}

        {detail && activeTab === "证据" ? (
          <EvidencePanel
            page={profile.data?.watchlist ? "watchlist" : "opportunities"}
            stockCode={code}
            sources={detail.source_cards}
            artifacts={detail.artifacts}
            title="来源与原始证据"
            eyebrow="Evidence"
          />
        ) : null}

        {!detail && askCase && activeTab === "证据" ? (
          <EvidencePanel
            page="opportunities"
            stockCode={code}
            sources={askCase.source_cards}
            artifacts={askCase.artifacts}
            title="Ask 来源与原始证据"
            eyebrow="Evidence"
          />
        ) : null}

        {!detail && askCase && (activeTab === "持仓" || activeTab === "发现") ? (
          <EmptyState>{activeTab === "持仓" ? "这只股票当前不在持仓名单，可用页面右上角加入。" : "这只股票当前不在观察池，先以 Ask 结论和证据为准。"}</EmptyState>
        ) : null}
      </div>
    </main>
  );
}
