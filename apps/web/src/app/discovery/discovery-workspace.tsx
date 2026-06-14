"use client";

import { RefreshCw, Telescope } from "lucide-react";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import { Badge } from "@/components/badge";
import { ErrorState, Panel, SkeletonBlock } from "@/components/data-card";
import { DeferredTrustBanner } from "@/components/deferred-trust-banner";
import { PageTitle } from "@/components/page-title";
import {
  queryKeys,
  useOpportunities,
  useOpportunitiesContext,
  useOpportunitiesSourceCards,
} from "@/lib/hooks";
import type { CardGroup, OpportunitiesData, StockListCard } from "@/lib/types";
import { useQueryClient } from "@tanstack/react-query";
import { groupCount, groupHasDeferredCards } from "./discovery-display-utils";
import type { DiscoveryObservationWorkbenchProps } from "./discovery-observation-workbench";

const DiscoveryContextPanels = dynamic(
  () =>
    import("./discovery-context-panels").then(
      (module) => module.DiscoveryContextPanels,
    ),
  {
    ssr: false,
    loading: () => (
      <>
        <SkeletonBlock className="h-32 w-full" />
        <SkeletonBlock className="h-48 w-full" />
      </>
    ),
  },
);

const DiscoveryEvidencePanel = dynamic(
  () =>
    import("@/components/evidence-panel").then(
      (module) => module.EvidencePanel,
    ),
  {
    ssr: false,
    loading: () => <SkeletonBlock className="h-32 w-full" />,
  },
);

const DiscoveryObservationWorkbench =
  dynamic<DiscoveryObservationWorkbenchProps>(
    () =>
      import("./discovery-observation-workbench").then(
        (module) => module.DiscoveryObservationWorkbench,
      ),
    {
      ssr: false,
      loading: () => (
        <>
          <section className="mb-7 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {Array.from({ length: 4 }).map((_, index) => (
              <SkeletonBlock key={index} className="h-24 w-full" />
            ))}
          </section>
          <SkeletonBlock className="h-72 w-full" />
        </>
      ),
    },
  );

function groupKey(group?: CardGroup<StockListCard>) {
  return String(group?.key || group?.title || "").trim();
}

function mergeLoadedOpportunityGroups(
  current: OpportunitiesData | undefined,
  incoming: OpportunitiesData,
): OpportunitiesData {
  if (!current?.groups?.length) {
    return incoming;
  }
  const currentGroups = new Map(
    (current.groups || []).map((group) => [groupKey(group), group]),
  );
  const mergedGroups = (incoming.groups || []).map((incomingGroup) => {
    const key = groupKey(incomingGroup);
    const currentGroup = currentGroups.get(key);
    if (
      !currentGroup ||
      !currentGroup.cards?.length ||
      !groupHasDeferredCards(incomingGroup)
    ) {
      return incomingGroup;
    }
    return {
      ...incomingGroup,
      cards: currentGroup.cards,
      cards_loaded:
        currentGroup.cards_loaded ?? !groupHasDeferredCards(currentGroup),
      deferred_cards: Boolean(currentGroup.deferred_cards),
      cards_preview_limit: currentGroup.cards_preview_limit,
    };
  });
  return { ...current, ...incoming, groups: mergedGroups };
}

function strategyLine(data?: OpportunitiesData) {
  const gate =
    data?.topline?.meta_pills?.find((item) => item.label.includes("阀门"))
      ?.value ||
    data?.hero?.status_label ||
    "";
  if (gate.includes("关闭")) {
    return "今日策略：进攻阀门关闭，只复核观察池，不新增开仓";
  }
  return `今日策略：${data?.topline?.verdict_title || data?.hero?.title || "先复核观察池，再决定下一步"}`;
}

export function DiscoveryWorkspace() {
  const queryClient = useQueryClient();
  const opportunities = useOpportunities();
  const data = opportunities.data;
  const trust = data?.readiness?.trust_level;
  const groups = data?.groups || [];
  const totalGroupCount = useMemo(
    () => groups.reduce((sum, group) => sum + groupCount(group), 0),
    [groups],
  );
  const trustBlocksTopline =
    trust && trust.level !== "trusted" && totalGroupCount === 0;
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const [contextOpen, setContextOpen] = useState(false);
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [loadingGroupKey, setLoadingGroupKey] = useState("");
  const [groupLoadErrors, setGroupLoadErrors] = useState<
    Record<string, string>
  >({});
  const contextQueryEnabled = Boolean(
    data?.context_deferred && contextOpen,
  );
  const contextPanelEnabled = Boolean(
    data && (!data.context_deferred || contextOpen),
  );
  const opportunitiesContext = useOpportunitiesContext({
    enabled: contextQueryEnabled,
  });
  const contextData = data?.context_deferred ? opportunitiesContext.data : data;
  const sourceCardsQueryEnabled = Boolean(
    data?.evidence_deferred && evidenceOpen && !contextData?.source_cards,
  );
  const opportunitiesSourceCards = useOpportunitiesSourceCards({
    enabled: sourceCardsQueryEnabled,
  });
  const evidenceSources =
    opportunitiesSourceCards.data?.source_cards ||
    contextData?.source_cards ||
    data?.source_cards;
  const contextLoading = Boolean(
    data?.context_deferred &&
    contextOpen &&
    opportunitiesContext.isLoading &&
    !opportunitiesContext.data,
  );
  const contextError = Boolean(
    data?.context_deferred &&
    contextOpen &&
    opportunitiesContext.isError &&
    !opportunitiesContext.data,
  );
  const firstNonEmptyIndex = useMemo(() => {
    const index = groups.findIndex((group) => groupCount(group) > 0);
    return index >= 0 ? index : 0;
  }, [groups]);
  const resolvedActiveIndex = Math.min(
    activeIndex ?? firstNonEmptyIndex,
    Math.max(groups.length - 1, 0),
  );
  const activeGroup = groups[resolvedActiveIndex];
  const activeGroupKey = groupKey(activeGroup);
  const activeGroupDeferred = groupHasDeferredCards(activeGroup);
  const activeGroupLoadError = activeGroupKey
    ? groupLoadErrors[activeGroupKey]
    : "";

  useEffect(() => {
    if (!groups.length) {
      return;
    }
    if (activeIndex === null || activeIndex >= groups.length) {
      setActiveIndex(firstNonEmptyIndex);
    }
  }, [activeIndex, firstNonEmptyIndex, groups.length]);

  async function loadOpportunityGroup(requestedGroupKey: string) {
    if (!requestedGroupKey) {
      return;
    }
    setLoadingGroupKey(requestedGroupKey);
    setGroupLoadErrors((current) => {
      const next = { ...current };
      delete next[requestedGroupKey];
      return next;
    });
    try {
      const payload = await api.getOpportunities({ group: requestedGroupKey });
      queryClient.setQueryData(
        queryKeys.opportunities,
        (current: OpportunitiesData | undefined) =>
          mergeLoadedOpportunityGroups(current, payload),
      );
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "阶段数据加载失败";
      setGroupLoadErrors((current) => ({
        ...current,
        [requestedGroupKey]: message,
      }));
      setFeedback(message);
    } finally {
      setLoadingGroupKey((current) =>
        current === requestedGroupKey ? "" : current,
      );
    }
  }

  async function refreshOpportunities() {
    setRefreshing(true);
    try {
      const payload = await api.getOpportunities({
        fresh: true,
        group: activeGroupKey || undefined,
      });
      queryClient.setQueryData(queryKeys.opportunities, payload);
      void queryClient.invalidateQueries({
        queryKey: queryKeys.opportunitiesContext,
      });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.opportunitiesSourceCards,
      });
      setFeedback("观察池已刷新。");
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "观察池刷新失败");
    } finally {
      setRefreshing(false);
    }
  }

  const sidePanel = (
    <>
      {data?.context_deferred && !contextOpen ? (
        <Panel title="历史 / 主线 / 延续" eyebrow="Context">
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
            <div className="text-[13px] font-medium text-[var(--text-primary)]">
              按需加载观察池上下文
            </div>
            <p className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
              首屏先保留观察工作台和阶段流；历史提醒、主线雷达、延续追踪需要时再读取。
            </p>
            <button
              type="button"
              className="focus-ring mt-3 inline-flex min-h-[32px] items-center gap-1.5 rounded-md border border-[var(--border-subtle)] px-2.5 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              onClick={() => setContextOpen(true)}
            >
              <RefreshCw size={13} />
              加载上下文
            </button>
          </div>
        </Panel>
      ) : null}

      {contextPanelEnabled ? (
        <>
          {contextLoading ? (
            <>
              <SkeletonBlock className="h-32 w-full" />
              <SkeletonBlock className="h-48 w-full" />
            </>
          ) : null}

          {contextError ? (
            <ErrorState
              message="观察池上下文暂不可用"
              onRetry={() => void opportunitiesContext.refetch()}
            />
          ) : null}

          {!contextLoading && !contextError ? (
            <DiscoveryContextPanels data={contextData} />
          ) : null}
        </>
      ) : null}

      {evidenceOpen ? (
        <DiscoveryEvidencePanel
          page="opportunities"
          sources={evidenceSources}
          title="数据健康"
          eyebrow="Freshness"
          compact
        />
      ) : (
        <Panel title="数据健康" eyebrow="Freshness">
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
            <div className="text-[13px] font-medium text-[var(--text-primary)]">
              来源证据按需加载
            </div>
            <p className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
              日常先复核候选和买入闸门；需要查来源、刷新状态或原始证据时再加载数据健康面板。
            </p>
            <button
              type="button"
              data-testid="discovery-evidence-gate"
              className="focus-ring mt-3 inline-flex min-h-[32px] items-center gap-1.5 rounded-md border border-[var(--border-subtle)] px-2.5 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              onClick={() => setEvidenceOpen(true)}
            >
              <RefreshCw size={13} />
              加载数据健康
            </button>
          </div>
        </Panel>
      )}
    </>
  );

  return (
    <main className="flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
      <div className="mx-auto max-w-7xl">
        <PageTitle
          eyebrow={
            data?.display_date ||
            data?.generated_at?.slice(0, 10) ||
            data?.trade_date ||
            "Discovery"
          }
          title={
            trustBlocksTopline
              ? "观察池"
              : data?.topline?.verdict_title || data?.hero?.title || "观察池"
          }
          summary={
            trustBlocksTopline
              ? "今日观察池没有产生新名字。先按下方可信度提示完成恢复，再决定要不要复核。"
              : data?.topline?.verdict_summary ||
                data?.hero?.summary ||
                "候选 Pipeline、阀门状态、质检和主线热力。"
          }
          icon={Telescope}
          badge={
            data?.hero?.status_label ||
            (data?.brief_is_live ? "总控同步" : "实时链路")
          }
          actions={
            <button
              type="button"
              className="focus-ring inline-flex items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)]"
              onClick={() => void refreshOpportunities()}
              disabled={refreshing || opportunities.isFetching}
            >
              <RefreshCw
                size={14}
                className={
                  refreshing || opportunities.isFetching ? "animate-spin" : ""
                }
              />
              刷新
            </button>
          }
        />

        {trust && trust.level !== "trusted" ? (
          <DeferredTrustBanner trust={trust} className="mb-4" />
        ) : null}

        {opportunities.isError ? (
          <ErrorState
            message="观察池数据暂不可用"
            onRetry={() => void opportunities.refetch()}
          />
        ) : null}

        <section className="mb-5 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-3">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <Badge tone={data?.brief_is_live ? "positive" : "watch"}>
                  {data?.brief_is_live ? "总控同步" : "实时链路"}
                </Badge>
                {data?.trade_date ? (
                  <Badge tone="info">交易日 {data.trade_date}</Badge>
                ) : null}
              </div>
              <h2 className="text-lg font-semibold text-[var(--text-primary)]">
                {strategyLine(data)}
              </h2>
              <p className="mt-2 text-[12px] leading-5 text-[var(--text-secondary)]">
                {data?.topline?.verdict_summary ||
                  data?.hero?.summary ||
                  "把候选池当作复核队列，而不是可随手挑选的股票列表。"}
              </p>
            </div>
            {feedback ? (
              <div className="rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
                {feedback}
              </div>
            ) : null}
          </div>
        </section>

        <DiscoveryObservationWorkbench
          groups={groups}
          loading={
            (opportunities.isLoading && !data) ||
            loadingGroupKey === activeGroupKey
          }
          initialLoading={opportunities.isLoading && !data}
          activeGroupLoadError={activeGroupLoadError}
          onLoadGroup={
            activeGroupDeferred
              ? () => void loadOpportunityGroup(activeGroupKey)
              : undefined
          }
          onRetryLoadGroup={() => void loadOpportunityGroup(activeGroupKey)}
          tradeDate={data?.trade_date}
          onFeedback={setFeedback}
          sidePanel={sidePanel}
          valveStatus={data?.valve_status}
        />
      </div>
    </main>
  );
}
