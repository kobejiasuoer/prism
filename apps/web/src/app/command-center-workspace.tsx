"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { AlertCircle, ChevronDown, FileDown, RefreshCw } from "lucide-react";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import {
  queryKeys,
  useRefreshStatus,
  useTodayActions,
  useTodayCommandBriefDetail,
  useTodaySummary,
} from "@/lib/hooks";

import {
  CommandHeader,
  JudgementChain,
  ActionLanes,
  MiddayVerify,
  TrustFold,
} from "@/components/command-brief";
import { SkeletonBlock } from "@/components/data-card";
import { DeferredTrustBanner } from "@/components/deferred-trust-banner";

const TodayActionDetails = dynamic(
  () =>
    import("./today-action-details").then(
      (module) => module.TodayActionDetails,
    ),
  {
    ssr: false,
    loading: () => <SkeletonBlock className="h-24 w-full" />,
  },
);

export function CommandCenterWorkspace() {
  const queryClient = useQueryClient();
  const today = useTodaySummary();
  const [actionsEnabled, setActionsEnabled] = useState(false);
  const [briefDetailOpen, setBriefDetailOpen] = useState(false);
  const [trustOpen, setTrustOpen] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const todayActions = useTodayActions({ enabled: actionsEnabled });
  const todayCommandBriefDetail = useTodayCommandBriefDetail({
    enabled: briefDetailOpen,
  });
  const refreshStatus = useRefreshStatus("today", trustOpen, {
    auto: false,
    compact: true,
    poll: false,
  });
  const data = today.data;
  const actionsData = todayActions.data;
  const brief = data?.command_brief;
  const briefDetail = todayCommandBriefDetail.data?.command_brief_detail;
  const forbid = briefDetail?.forbid_today || brief?.forbid_today || [];
  const reclassify =
    briefDetail?.reclassify_when || brief?.reclassify_when || [];
  const judgementChain =
    briefDetail?.judgement_chain || brief?.judgement_chain || [];
  const middayVerify = briefDetail?.midday_verify || brief?.midday_verify;
  const loadingBrief = today.isLoading && !data;
  const trust = data?.readiness?.trust_level;
  const tradeDate =
    brief?.trade_date || data?.expected_trade_date || data?.trade_date || "-";

  async function refreshCommandCenter() {
    setRefreshing(true);
    try {
      const [summaryResult, actionsResult, briefDetailResult] =
        await Promise.allSettled([
          api.getTodaySummary({ fresh: true }),
          actionsEnabled
            ? api.getTodayActions({ fresh: true })
            : Promise.resolve(null),
          briefDetailOpen
            ? api.getTodayCommandBriefDetail({ fresh: true })
            : Promise.resolve(null),
        ]);

      if (summaryResult.status === "fulfilled") {
        queryClient.setQueryData(queryKeys.todaySummary, summaryResult.value);
      }

      if (actionsResult.status === "fulfilled" && actionsResult.value) {
        queryClient.setQueryData(queryKeys.todayActions, actionsResult.value);
        if (actionsResult.value.decision_contracts_deferred) {
          void queryClient.invalidateQueries({
            queryKey: queryKeys.todayActionContracts,
            refetchType: "active",
          });
        }
      }

      if (briefDetailResult.status === "fulfilled" && briefDetailResult.value) {
        queryClient.setQueryData(
          queryKeys.todayCommandBriefDetail,
          briefDetailResult.value,
        );
      }
    } finally {
      setRefreshing(false);
    }
  }

  function loadActionDetails() {
    setActionsEnabled(true);
  }

  return (
    <main className="war-room">
      <div className="war-room-inner">
        <header className="war-topbar">
          <div>
            <div className="war-eyebrow">Daily Command Brief</div>
            <h1>每日交易命令台</h1>
          </div>
          <div className="war-top-actions">
            <button
              type="button"
              className="focus-ring war-tool-btn"
              onClick={() => void refreshCommandCenter()}
              disabled={
                refreshing ||
                today.isFetching ||
                todayActions.isFetching ||
                todayCommandBriefDetail.isFetching
              }
            >
              <RefreshCw
                size={14}
                className={
                  refreshing ||
                  today.isFetching ||
                  todayActions.isFetching ||
                  todayCommandBriefDetail.isFetching
                    ? "animate-spin"
                    : ""
                }
              />
              刷新
            </button>
            <button
              type="button"
              className="focus-ring war-tool-btn"
              onClick={() => window.print()}
            >
              <FileDown size={14} />
              导出简报
            </button>
          </div>
        </header>

        {trust ? (
          <DeferredTrustBanner
            trust={trust}
            readiness={data?.readiness}
            className="mb-4"
          />
        ) : null}

        {today.isError ? (
          <div className="war-error">
            <AlertCircle
              size={17}
              className="mt-0.5 shrink-0 text-[var(--warning)]"
            />
            <div className="min-w-0 flex-1">
              <div className="font-medium text-[var(--text-primary)]">
                后端数据暂不可用
              </div>
              <div className="mt-1">
                命令台骨架已加载，FastAPI 启动后会自动重新获取
                `/api/today/summary`。
              </div>
            </div>
            <button
              type="button"
              className="focus-ring rounded-md border border-[var(--border-subtle)] px-2.5 py-1 text-[12px] text-[var(--text-primary)]"
              onClick={() => void today.refetch()}
            >
              重试
            </button>
          </div>
        ) : null}

        {brief ? (
          <>
            <CommandHeader
              mode={brief.mode}
              permits={brief.permits}
              positionCap={brief.position_cap}
              firstAction={brief.first_action}
              tradeDate={tradeDate}
            />
            <ActionLanes lanes={brief.action_lanes} />
            <details
              className="group"
              open={briefDetailOpen}
              onToggle={(event) =>
                setBriefDetailOpen(event.currentTarget.open)
              }
            >
              <summary className="focus-ring flex cursor-pointer list-none items-center justify-between gap-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-3 marker:hidden">
                <div className="min-w-0">
                  <div className="text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">
                    Command Logic
                  </div>
                  <h2 className="mt-1 text-[15px] font-semibold text-[var(--text-primary)]">
                    判断细节
                  </h2>
                </div>
                <span className="inline-flex items-center gap-2 text-[12px] text-[var(--text-secondary)]">
                  {todayCommandBriefDetail.isFetching ? "读取中" : "展开"}
                  <ChevronDown
                    size={16}
                    className="transition group-open:rotate-180"
                  />
                </span>
              </summary>
              {briefDetailOpen ? (
                <div className="mt-3 space-y-3">
                  {todayCommandBriefDetail.isError &&
                  !todayCommandBriefDetail.data ? (
                    <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
                      判断细节暂不可用
                      <button
                        type="button"
                        className="focus-ring ml-3 inline-flex h-7 items-center rounded-md border border-[var(--border-subtle)] px-2 text-[11px] text-[var(--text-primary)]"
                        onClick={() => void todayCommandBriefDetail.refetch()}
                      >
                        重试
                      </button>
                    </div>
                  ) : todayCommandBriefDetail.isLoading &&
                    !todayCommandBriefDetail.data ? (
                    <SkeletonBlock className="h-28 w-full" />
                  ) : (
                    <>
                      <section
                        className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-4"
                        data-od-id="command-brief-detail"
                      >
                        <div className="grid gap-4 md:grid-cols-2">
                          <div>
                            <div className="text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">
                              今日禁令
                            </div>
                            <ul className="mt-2 space-y-1.5 text-[12px] text-[var(--text-secondary)]">
                              {forbid.length ? (
                                forbid.slice(0, 3).map((item, idx) => (
                                  <li key={`${item.title}-${idx}`}>
                                    <span className="font-medium text-[var(--text-primary)]">
                                      {item.title}
                                    </span>
                                    <span className="ml-2 text-[var(--text-tertiary)]">
                                      {item.reason}
                                    </span>
                                  </li>
                                ))
                              ) : (
                                <li className="text-[var(--text-tertiary)]">
                                  暂无额外禁令
                                </li>
                              )}
                            </ul>
                          </div>
                          <div>
                            <div className="text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">
                              改判条件
                            </div>
                            <ul className="mt-2 space-y-1.5 text-[12px] text-[var(--text-secondary)]">
                              {reclassify.length ? (
                                reclassify.map((rule, idx) => (
                                  <li key={`${rule.label}-${idx}`}>
                                    <span className="font-medium text-[var(--text-primary)]">
                                      {rule.label}
                                    </span>
                                    <span className="ml-2">
                                      {rule.condition}
                                    </span>
                                    {rule.url ? (
                                      <Link
                                        href={rule.url}
                                        className="ml-2 underline"
                                      >
                                        {rule.evidence}
                                      </Link>
                                    ) : (
                                      <span className="ml-2 text-[var(--text-tertiary)]">
                                        {rule.evidence}
                                      </span>
                                    )}
                                  </li>
                                ))
                              ) : (
                                <li className="text-[var(--text-tertiary)]">
                                  暂无改判条件
                                </li>
                              )}
                            </ul>
                          </div>
                        </div>
                      </section>
                      {judgementChain.length ? (
                        <JudgementChain items={judgementChain} />
                      ) : null}
                      {middayVerify ? (
                        <MiddayVerify payload={middayVerify} />
                      ) : null}
                    </>
                  )}
                </div>
              ) : null}
            </details>
            <TrustFold
              trust={brief.trust}
              open={trustOpen}
              onOpenChange={setTrustOpen}
            >
              <div className="text-[12px] text-[var(--text-secondary)]">
                建议刷新 {refreshStatus.data?.recommended_task?.title ?? "-"}
              </div>
            </TrustFold>
            {actionsEnabled ? (
              <TodayActionDetails actions={actionsData} />
            ) : (
              <section className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">
                      Action Details
                    </div>
                    <h2 className="mt-1 text-[15px] font-semibold text-[var(--text-primary)]">
                      动作明细按需加载
                    </h2>
                    <p className="mt-1 text-[12px] text-[var(--text-secondary)]">
                      首屏先固定今日四件事；需要写回口径和动作契约时再读取完整队列。
                    </p>
                  </div>
                  <button
                    type="button"
                    className="focus-ring war-tool-btn"
                    onClick={loadActionDetails}
                  >
                    加载动作明细
                  </button>
                </div>
              </section>
            )}
          </>
        ) : loadingBrief ? (
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-4">
            <div className="mb-3 flex items-center gap-2 text-[13px] text-[var(--text-secondary)]">
              <RefreshCw size={14} className="animate-spin" />
              正在读取今日命令台和数据可信度
            </div>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {Array.from({ length: 4 }).map((_, index) => (
                <SkeletonBlock key={index} className="h-28 w-full" />
              ))}
            </div>
          </div>
        ) : !today.isError ? (
          <div className="war-error">
            <AlertCircle
              size={17}
              className="mt-0.5 shrink-0 text-[var(--warning)]"
            />
            <div className="min-w-0 flex-1">
              <div className="font-medium text-[var(--text-primary)]">
                命令台数据未到位
              </div>
              <div className="mt-1">
                后端尚未返回 `command_brief`；先到 Settings 跑安全刷新。
              </div>
            </div>
          </div>
        ) : null}

        {todayActions.isFetching && !actionsData ? (
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
            正在懒加载可写回动作队列
          </div>
        ) : null}
      </div>
    </main>
  );
}
