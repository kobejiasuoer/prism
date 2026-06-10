"use client";

import { FileSearch, LoaderCircle, RefreshCw } from "lucide-react";
import dynamic from "next/dynamic";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/badge";
import { EmptyState, ErrorState, SkeletonBlock } from "@/components/data-card";
import { MetricSkeleton } from "@/components/metric-card";
import { PageTitle } from "@/components/page-title";
import { DeferredTrustBanner } from "@/components/deferred-trust-banner";
import {
  useAsk,
  useStockProfileDetail,
  useStockProfileEvidence,
  useStockProfileFormalData,
  useStockProfileFormalDataSection,
  useStockProfileLearningScorecard,
  useStockProfileSecondary,
  useStockProfileSummary,
  useStockProfileTodayAction,
} from "@/lib/hooks";
import { readinessHasStaleData } from "@/lib/readiness-copy";
import type { StockProfileData } from "@/lib/types";
import { cn } from "@/lib/utils";
import type {
  StockDecisionHeroPanelsProps,
  StockDecisionTabWorkspaceProps,
} from "./stock-decision-workspace";
import type { FormalSectionKey } from "./stock-formal-panels";
import type { StockSecondaryTabsProps } from "./stock-secondary-tabs";
import type { StockWatchlistActionsProps } from "./stock-watchlist-actions";
import { canonicalText } from "./stock-display-utils";

const tabs = ["决策", "追问", "持仓", "发现", "证据"] as const;
type StockTab = (typeof tabs)[number];
type StockProfileSource = NonNullable<
  StockProfileData["available_sources"]
>[number];
const profileSourceIssueLabels: Record<StockProfileSource, string> = {
  watchlist: "自选股未命中",
  opportunity: "观察池未命中",
};

const FormalDataSummaryPanel = dynamic(
  () =>
    import("./stock-formal-panels").then(
      (module) => module.FormalDataSummaryPanel,
    ),
  {
    ssr: false,
    loading: () => <SkeletonBlock className="h-44 w-full" />,
  },
);

const FormalDataSnapshotPanel = dynamic(
  () =>
    import("./stock-formal-panels").then(
      (module) => module.FormalDataSnapshotPanel,
    ),
  {
    ssr: false,
    loading: () => <SkeletonBlock className="h-64 w-full" />,
  },
);

const StockDecisionTimelinePanel = dynamic(
  () =>
    import("./stock-decision-timeline").then(
      (module) => module.StockDecisionTimelinePanel,
    ),
  {
    ssr: false,
    loading: () => <SkeletonBlock className="h-40 w-full" />,
  },
);

const StockDecisionHeroPanels = dynamic<StockDecisionHeroPanelsProps>(
  () =>
    import("./stock-decision-workspace").then(
      (module) => module.StockDecisionHeroPanels,
    ),
  {
    ssr: false,
    loading: () => <SkeletonBlock className="h-48 w-full" />,
  },
);

const StockDecisionTabWorkspace = dynamic<StockDecisionTabWorkspaceProps>(
  () =>
    import("./stock-decision-workspace").then(
      (module) => module.StockDecisionTabWorkspace,
    ),
  {
    ssr: false,
    loading: () => (
      <div className="grid gap-4">
        <SkeletonBlock className="h-48 w-full" />
        <SkeletonBlock className="h-40 w-full" />
      </div>
    ),
  },
);

const StockAskWorkspace = dynamic(
  () =>
    import("./stock-ask-workspace").then((module) => module.StockAskWorkspace),
  {
    ssr: false,
    loading: () => <SkeletonBlock className="h-[520px] w-full" />,
  },
);

const StockEvidencePanel = dynamic(
  () =>
    import("@/components/evidence-panel").then(
      (module) => module.EvidencePanel,
    ),
  {
    ssr: false,
    loading: () => <SkeletonBlock className="h-64 w-full" />,
  },
);

const StockSecondaryTabs = dynamic<StockSecondaryTabsProps>(
  () =>
    import("./stock-secondary-tabs").then(
      (module) => module.StockSecondaryTabs,
    ),
  {
    ssr: false,
    loading: () => <SkeletonBlock className="h-72 w-full" />,
  },
);

const StockWatchlistActions = dynamic<StockWatchlistActionsProps>(
  () =>
    import("./stock-watchlist-actions").then(
      (module) => module.StockWatchlistActions,
    ),
  {
    ssr: false,
    loading: () => (
      <button
        type="button"
        className="focus-ring inline-flex min-h-9 min-w-[104px] items-center justify-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-tertiary)] disabled:cursor-not-allowed disabled:opacity-60"
        disabled
      >
        <LoaderCircle size={14} className="animate-spin" />
        名单同步中
      </button>
    ),
  },
);

function pickDetail(profile?: StockProfileData) {
  return profile?.primary_detail;
}

function sourceIssueBadges(profile?: StockProfileData) {
  const errors = profile?.errors || {};
  return (Object.keys(profileSourceIssueLabels) as StockProfileSource[])
    .filter((source) => errors[source])
    .map((source) => ({
      key: source,
      label: profileSourceIssueLabels[source],
    }));
}

function StockProfilePageContent() {
  const params = useParams<{ code: string }>();
  const searchParams = useSearchParams();
  const code = String(params.code || "");
  const queryName = String(searchParams.get("name") || "").trim();
  const profileSummary = useStockProfileSummary(code);
  const [activeTab, setActiveTab] = useState<StockTab>("决策");
  const [formalFullEnabled, setFormalFullEnabled] = useState(false);
  const [formalSectionsEnabled, setFormalSectionsEnabled] = useState<
    Record<FormalSectionKey, boolean>
  >({
    profile: false,
    risk: false,
    sources: false,
  });
  const [deferredInsightsEnabled, setDeferredInsightsEnabled] = useState(false);
  const [watchlistActionsOpen, setWatchlistActionsOpen] = useState(false);
  const [watchlistFeedback, setWatchlistFeedback] = useState("");
  const [watchlistResolvedName, setWatchlistResolvedName] = useState("");
  const detailEnabled =
    Boolean(code) &&
    activeTab !== "追问" &&
    Boolean(profileSummary.data || profileSummary.isError);
  const profileDetail = useStockProfileDetail(code, { enabled: detailEnabled });
  const formalSummaryQuery = useStockProfileFormalDataSection(code, "summary", {
    enabled: activeTab === "证据",
  });
  const formalProfileQuery = useStockProfileFormalDataSection(code, "profile", {
    enabled: activeTab === "证据" && formalSectionsEnabled.profile,
  });
  const formalRiskQuery = useStockProfileFormalDataSection(code, "risk", {
    enabled: activeTab === "证据" && formalSectionsEnabled.risk,
  });
  const formalSourcesQuery = useStockProfileFormalDataSection(code, "sources", {
    enabled: activeTab === "证据" && formalSectionsEnabled.sources,
  });
  const formalDataQuery = useStockProfileFormalData(code, {
    enabled: activeTab === "证据" && formalFullEnabled,
  });
  const profileData = profileDetail.data || profileSummary.data;
  const decisionLocked = Boolean(
    profileData?.readiness &&
      (profileData.readiness.readiness_mode !== "live_ready" ||
        readinessHasStaleData(profileData.readiness)),
  );
  const learningScorecardQuery = useStockProfileLearningScorecard(code, {
    enabled:
      Boolean(code) &&
      (decisionLocked || (activeTab === "决策" && deferredInsightsEnabled)),
  });
  const ask = useAsk(code, activeTab === "追问");
  const profileLoading = !profileData && profileSummary.isLoading;
  const detailLoading = profileDetail.isLoading && detailEnabled;
  const profileHydrating = Boolean(
    profileSummary.data && !profileDetail.data && profileDetail.isFetching,
  );
  const formalSummary = formalSummaryQuery.data?.formal_data;
  const formalProfile = formalProfileQuery.data?.formal_data;
  const formalRisk = formalRiskQuery.data?.formal_data;
  const formalSources = formalSourcesQuery.data?.formal_data;
  const formalData = formalDataQuery.data?.formal_data;
  const learningScorecard = learningScorecardQuery.data;
  const formalColdLoading =
    activeTab === "证据" &&
    !formalSummary &&
    !formalData &&
    (formalSummaryQuery.isFetching ||
      formalProfileQuery.isFetching ||
      formalRiskQuery.isFetching ||
      formalSourcesQuery.isFetching ||
      formalDataQuery.isFetching);
  const formalFullLoading =
    activeTab === "证据" &&
    Boolean(formalSummary) &&
    !formalData &&
    formalDataQuery.isFetching;
  const detail = pickDetail(profileDetail.data);
  const todayActionEnabled = Boolean(code) && Boolean(detail);
  const todayActionQuery = useStockProfileTodayAction(code, {
    enabled: todayActionEnabled,
  });
  const todayAction = todayActionQuery.data?.today_action || null;
  const stockEvidence = useStockProfileEvidence(code, {
    enabled: Boolean(code) && activeTab === "证据" && Boolean(detail),
  });
  const stockSecondary = useStockProfileSecondary(code, {
    enabled:
      Boolean(code) &&
      Boolean(detail) &&
      (activeTab === "持仓" || activeTab === "发现"),
  });
  const secondaryDetail = stockSecondary.data?.secondary_detail;
  const secondaryLoading = stockSecondary.isLoading && !secondaryDetail;
  const askCase = ask.data?.case;
  const availableSources =
    profileDetail.data?.available_sources ||
    profileSummary.data?.available_sources ||
    [];
  const hasWatchlistDetail = availableSources.includes("watchlist");
  const hasOpportunityDetail = availableSources.includes("opportunity");
  const visibleTabs = useMemo<StockTab[]>(() => {
    const items: StockTab[] = ["决策", "追问"];
    if (hasWatchlistDetail) {
      items.push("持仓");
    }
    if (hasOpportunityDetail) {
      items.push("发现");
    }
    items.push("证据");
    return items;
  }, [hasOpportunityDetail, hasWatchlistDetail]);

  useEffect(() => {
    setFormalFullEnabled(false);
    setFormalSectionsEnabled({
      profile: false,
      risk: false,
      sources: false,
    });
    setDeferredInsightsEnabled(false);
    setWatchlistActionsOpen(false);
    setWatchlistFeedback("");
    setWatchlistResolvedName("");
  }, [code]);

  useEffect(() => {
    if (activeTab === "证据") {
      setDeferredInsightsEnabled(true);
    }
  }, [activeTab]);
  const rawStockName =
    detail?.name ||
    profileData?.name ||
    queryName ||
    watchlistResolvedName ||
    askCase?.name ||
    "";
  const stockName = rawStockName && rawStockName !== code ? rawStockName : code;
  const hasResolvedName = Boolean(rawStockName && rawStockName !== code);
  const followupShell =
    ask.data?.followup || askCase?.evidence_layer?.followup || null;
  const sourceLabel =
    profileData?.primary_source_label && activeTab === "决策"
      ? profileData.primary_source_label
      : activeTab === "发现" && hasOpportunityDetail
        ? "观察池链路"
        : hasWatchlistDetail
          ? "自选股链路"
          : hasOpportunityDetail
            ? "观察池链路"
            : askCase
              ? "Ask 临时分析"
              : "待匹配";
  const sourceGeneratedAt =
    detail?.generated_at ||
    ask.data?.generated_at ||
    canonicalText(askCase?.canonical_decision, "updated_at", "");
  const sourceTradeDate =
    detail?.trade_date ||
    askCase?.trade_date ||
    canonicalText(
      detail?.canonical_decision || askCase?.canonical_decision,
      "trade_date",
      "",
    );
  const displayTradeDate =
    sourceTradeDate ||
    profileData?.data_trade_date ||
    profileData?.expected_trade_date ||
    "";
  const sourceIssues = useMemo(
    () => sourceIssueBadges(profileData),
    [profileData],
  );
  const trustLevel = profileData?.readiness?.trust_level;
  const pageTitle = decisionLocked
    ? hasResolvedName
      ? `${stockName} ${code}`
      : code
    : detail?.hero?.title ||
      askCase?.hero?.title ||
      (hasResolvedName ? `${stockName} · ${code}` : code);
  const pageSummary = decisionLocked
    ? "数据新鲜度未通过，旧结论已从首屏移除；当前只允许查看证据和刷新状态。"
    : detail?.hero?.summary ||
      detail?.topline?.verdict_summary ||
      askCase?.hero?.summary ||
      "统一查看这只股票的决策、持仓、发现和证据。";
  const pageBadge = decisionLocked
    ? "交易判断冻结"
    : detail?.hero?.status_label ||
      detail?.topline?.verdict_badge ||
      askCase?.hero?.status_label ||
      askCase?.hero?.decision_label ||
      "个股档案";
  const executionResultHref = useMemo(() => {
    const params = new URLSearchParams();
    const canonical = detail?.canonical_decision || askCase?.canonical_decision;

    params.set("code", code);
    params.set("source", "stock");
    params.set("source_label", sourceLabel);

    if (stockName) {
      params.set("name", stockName);
    }
    if (todayAction?.key) {
      params.set("intent_key", todayAction.key);
      params.set("today_action_key", todayAction.key);
    }
    if (todayAction?.trade_date || sourceTradeDate) {
      params.set("trade_date", todayAction?.trade_date || sourceTradeDate);
    }
    if (canonical?.main_conclusion) {
      params.set("conclusion", canonical.main_conclusion);
    }
    if (canonical?.position_guidance) {
      params.set("position", canonical.position_guidance);
    }
    if (canonical?.continue_condition) {
      params.set("continue_condition", canonical.continue_condition);
    }
    if (canonical?.stop_condition) {
      params.set("stop_condition", canonical.stop_condition);
    }

    return `/portfolio?${params.toString()}#decision-writeback`;
  }, [
    askCase?.canonical_decision,
    code,
    detail?.canonical_decision,
    sourceLabel,
    sourceTradeDate,
    stockName,
    todayAction?.key,
    todayAction?.trade_date,
  ]);
  useEffect(() => {
    if (!visibleTabs.includes(activeTab)) {
      setActiveTab("决策");
    }
  }, [activeTab, visibleTabs]);

  function refetchProfileSurface() {
    void profileSummary.refetch();
    if (activeTab === "追问") {
      void ask.refetch();
    } else if (detailEnabled) {
      void profileDetail.refetch();
    }
    if (todayActionEnabled) {
      void todayActionQuery.refetch();
    }
    if (activeTab === "证据") {
      void formalSummaryQuery.refetch();
      if (formalSectionsEnabled.profile) {
        void formalProfileQuery.refetch();
      }
      if (formalSectionsEnabled.risk) {
        void formalRiskQuery.refetch();
      }
      if (formalSectionsEnabled.sources) {
        void formalSourcesQuery.refetch();
      }
      if (formalFullEnabled) {
        void formalDataQuery.refetch();
      }
      if (detail) {
        void stockEvidence.refetch();
      }
    }
    if (detail && (activeTab === "持仓" || activeTab === "发现")) {
      void stockSecondary.refetch();
    }
    if (decisionLocked || (activeTab === "决策" && deferredInsightsEnabled)) {
      void learningScorecardQuery.refetch();
    }
  }

  function loadDeferredInsights() {
    setDeferredInsightsEnabled(true);
  }

  function loadFormalSection(section: FormalSectionKey) {
    setFormalSectionsEnabled((current) => ({ ...current, [section]: true }));
  }

  function loadFormalFullData() {
    setFormalFullEnabled(true);
    if (formalFullEnabled) {
      void formalDataQuery.refetch();
    }
  }

  return (
    <main className="flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
      <div className="mx-auto max-w-7xl">
        <PageTitle
          eyebrow={displayTradeDate || code}
          title={pageTitle}
          summary={pageSummary}
          icon={FileSearch}
          badge={pageBadge}
          actions={
            <div className="flex flex-wrap items-center gap-2">
              {!watchlistActionsOpen ? (
                <button
                  type="button"
                  data-testid="stock-watchlist-actions-gate"
                  className="focus-ring inline-flex min-h-9 min-w-[104px] items-center justify-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                  onClick={() => setWatchlistActionsOpen(true)}
                  aria-label="同步名单状态"
                >
                  <RefreshCw size={14} />
                  名单状态待同步
                </button>
              ) : (
                <StockWatchlistActions
                  code={code}
                  stockName={stockName}
                  onFeedback={setWatchlistFeedback}
                  onResolvedName={setWatchlistResolvedName}
                />
              )}
              <button
                type="button"
                className="focus-ring inline-flex items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)]"
                onClick={refetchProfileSurface}
              >
                <RefreshCw
                  size={14}
                  className={
                    profileDetail.isFetching ||
                    profileSummary.isFetching ||
                    todayActionQuery.isFetching ||
                    formalSummaryQuery.isFetching ||
                    formalProfileQuery.isFetching ||
                    formalRiskQuery.isFetching ||
                    formalSourcesQuery.isFetching ||
                    formalDataQuery.isFetching ||
                    stockEvidence.isFetching ||
                    stockSecondary.isFetching ||
                    learningScorecardQuery.isFetching
                      ? "animate-spin"
                      : ""
                  }
                />
                刷新
              </button>
            </div>
          }
        />

        {trustLevel && trustLevel.level !== "trusted" ? (
          <DeferredTrustBanner
            trust={trustLevel}
            readiness={profileData?.readiness}
            className="mb-4"
          />
        ) : null}

        {profileDetail.isError && !profileSummary.data ? (
          <ErrorState
            message="个股详情暂不可用"
            onRetry={() => void profileDetail.refetch()}
          />
        ) : null}
        {watchlistFeedback ? (
          <div className="mb-5 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
            {watchlistFeedback}
          </div>
        ) : null}
        {profileLoading ? (
          <div className="mb-6 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-4">
            <div className="mb-3 flex items-center gap-2 text-[13px] text-[var(--text-secondary)]">
              <LoaderCircle size={14} className="animate-spin" />
              正在读取个股档案和数据可信度
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {Array.from({ length: 4 }).map((_, index) => (
                <MetricSkeleton key={index} />
              ))}
            </div>
          </div>
        ) : null}
        {profileHydrating ? (
          <div className="mb-5 flex items-center gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
            <LoaderCircle size={13} className="animate-spin" />
            摘要已就绪，正在补齐当前工作区详情
          </div>
        ) : null}
        {profileDetail.isError &&
        profileSummary.data &&
        activeTab !== "追问" ? (
          <ErrorState
            message="当前工作区详情暂不可用"
            onRetry={() => void profileDetail.refetch()}
          />
        ) : null}
        {!profileLoading &&
        !detailLoading &&
        !ask.isLoading &&
        !detail &&
        !askCase ? (
          <EmptyState>当前股票不在持仓或观察池详情中。</EmptyState>
        ) : null}

        {detail || askCase ? (
          <div className="mb-5 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge
                tone={
                  hasWatchlistDetail
                    ? "positive"
                    : hasOpportunityDetail
                      ? "watch"
                      : "info"
                }
              >
                {sourceLabel}
              </Badge>
              {sourceTradeDate ? (
                <Badge tone="info">交易日 {sourceTradeDate}</Badge>
              ) : null}
              {sourceGeneratedAt ? (
                <Badge tone="info">更新 {sourceGeneratedAt}</Badge>
              ) : null}
              {decisionLocked ? <Badge tone="risk">仅作证据来源</Badge> : null}
              {!detail && askCase ? (
                <Badge tone="warning">临时抓取</Badge>
              ) : null}
              {sourceIssues.map((item) => (
                <Badge key={item.key} tone="watch">
                  {item.label}
                </Badge>
              ))}
            </div>
            <p className="mt-2 text-[12px] leading-5 text-[var(--text-tertiary)]">
              {decisionLocked
                ? "当前链路只作为证据来源保留，不进入今天的交易判断。"
                : "当前页只展示已有链路能回源的纪律参考；目标价、收益预测和完整财报研判暂不进入结果页。"}
            </p>
          </div>
        ) : null}

        {formalColdLoading ? (
          <div className="mb-5 flex items-center gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
            <LoaderCircle size={13} className="animate-spin" />
            正在加载正式数据轻量摘要
          </div>
        ) : null}

        {activeTab === "证据" && formalSummary?.available ? (
          <div className="mb-6">
            <FormalDataSummaryPanel
              data={formalSummary}
              loadingFull={formalFullLoading}
              fullLoaded={Boolean(formalData?.available)}
              sectionStates={{
                profile: {
                  loaded: Boolean(formalProfile?.available),
                  loading: formalProfileQuery.isFetching,
                  available: formalProfile?.available,
                },
                risk: {
                  loaded: Boolean(formalRisk?.available),
                  loading: formalRiskQuery.isFetching,
                  available: formalRisk?.available,
                },
                sources: {
                  loaded: Boolean(formalSources?.available),
                  loading: formalSourcesQuery.isFetching,
                  available: formalSources?.available,
                },
              }}
              onLoadSection={loadFormalSection}
              onLoadFull={loadFormalFullData}
            />
          </div>
        ) : null}

        {activeTab === "证据" && formalProfile?.available ? (
          <div className="mb-6">
            <FormalDataSnapshotPanel data={formalProfile} />
          </div>
        ) : null}

        {activeTab === "证据" && formalRisk?.available ? (
          <div className="mb-6">
            <FormalDataSnapshotPanel data={formalRisk} />
          </div>
        ) : null}

        {activeTab === "证据" && formalSources?.available ? (
          <div className="mb-6">
            <FormalDataSnapshotPanel data={formalSources} />
          </div>
        ) : null}

        {activeTab === "证据" && formalData?.available ? (
          <div className="mb-6">
            <FormalDataSnapshotPanel data={formalData} />
          </div>
        ) : null}

        {detail || askCase || (decisionLocked && profileData?.readiness) ? (
          <StockDecisionHeroPanels
            code={code}
            stockName={stockName}
            detail={detail}
            askCase={askCase}
            decisionLocked={decisionLocked}
            readiness={profileData?.readiness}
            sourceLabel={sourceLabel}
            sourceTradeDate={sourceTradeDate}
            displayTradeDate={displayTradeDate}
            sourceGeneratedAt={sourceGeneratedAt}
            todayAction={todayAction}
            executionHref={executionResultHref}
            learningScorecard={learningScorecard}
            learningScorecardLoading={learningScorecardQuery.isLoading}
            onViewEvidence={() => setActiveTab("证据")}
          />
        ) : null}

        <div
          className="mb-6 flex gap-2 overflow-x-auto rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-1"
          role="tablist"
          aria-label="个股工作区"
        >
          {visibleTabs.map((tab) => (
            <button
              key={tab}
              type="button"
              id={`stock-tab-${tab}`}
              role="tab"
              aria-selected={activeTab === tab}
              aria-controls={`stock-panel-${tab}`}
              className={cn(
                "focus-ring shrink-0 rounded-[6px] px-4 py-2 text-[13px]",
                activeTab === tab
                  ? "bg-[var(--bg-tertiary)] text-[var(--text-primary)]"
                  : "text-[var(--text-tertiary)]",
              )}
              onClick={() => setActiveTab(tab)}
            >
              {tab}
            </button>
          ))}
        </div>

        <section
          id={`stock-panel-${activeTab}`}
          role="tabpanel"
          aria-labelledby={`stock-tab-${activeTab}`}
          className="contents"
        >
        {profileLoading && !detail ? (
          <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {Array.from({ length: 4 }).map((_, index) => (
              <MetricSkeleton key={index} />
            ))}
          </section>
        ) : null}

        {detailLoading && !detail ? (
          <section className="mb-6 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-4">
            <div className="mb-3 flex items-center gap-2 text-[13px] text-[var(--text-secondary)]">
              <LoaderCircle size={14} className="animate-spin" />
              正在加载当前工作区详情
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {Array.from({ length: 4 }).map((_, index) => (
                <MetricSkeleton key={index} />
              ))}
            </div>
          </section>
        ) : null}

        {decisionLocked &&
        (activeTab === "决策" ||
          activeTab === "持仓" ||
          activeTab === "发现") ? (
          <EmptyState>
            数据新鲜度未通过，{activeTab} 内容已冻结。请先去 Settings
            刷新，或切到“证据”只读查看来源。
          </EmptyState>
        ) : null}

        {activeTab === "追问" ? (
          <StockAskWorkspace
            code={code}
            stockName={stockName}
            askCase={askCase}
            followupShell={followupShell}
            isLoading={ask.isLoading}
            sourceGeneratedAt={sourceGeneratedAt}
          />
        ) : null}

        {!decisionLocked && activeTab === "决策" && (detail || askCase) ? (
          <StockDecisionTabWorkspace
            detail={detail}
            askCase={askCase}
            sourceLabel={sourceLabel}
            sourceGeneratedAt={sourceGeneratedAt}
            todayAction={todayAction}
            executionHref={executionResultHref}
            learningScorecard={learningScorecard}
            learningScorecardLoading={learningScorecardQuery.isLoading}
            deferredInsightsEnabled={deferredInsightsEnabled}
            onLoadDeferredInsights={loadDeferredInsights}
            onContinueAsk={() => setActiveTab("追问")}
          />
        ) : null}

        {!decisionLocked &&
        detail &&
        (activeTab === "持仓" || activeTab === "发现") ? (
          secondaryLoading ? (
            <SkeletonBlock className="mb-6 h-72 w-full" />
          ) : (
            <StockSecondaryTabs
              activeTab={activeTab}
              detail={secondaryDetail || detail}
            />
          )
        ) : null}

        {detail && activeTab === "证据" ? (
          <StockEvidencePanel
            page={
              (stockEvidence.data?.primary_source ||
                profileDetail.data?.primary_source) === "watchlist"
                ? "watchlist"
                : "opportunities"
            }
            stockCode={code}
            sources={stockEvidence.data?.source_cards}
            artifacts={stockEvidence.data?.artifacts}
            title="来源与原始证据"
            eyebrow="Evidence"
          />
        ) : null}

        {!detail && askCase && activeTab === "证据" ? (
          <StockEvidencePanel
            mode="ask"
            stockCode={code}
            sources={askCase.source_cards}
            artifacts={askCase.artifacts}
            title="Ask 来源与原始证据"
            eyebrow="Evidence"
          />
        ) : null}

        {!detail &&
        askCase &&
        (activeTab === "持仓" || activeTab === "发现") ? (
          <EmptyState>
            {activeTab === "持仓"
              ? "这只股票当前不在持仓名单，可用页面右上角加入。"
              : "这只股票当前不在观察池，先以 Ask 结论和证据为准。"}
          </EmptyState>
        ) : null}

        {activeTab === "决策" && !profileLoading && deferredInsightsEnabled ? (
          <StockDecisionTimelinePanel
            code={code}
            enabled={deferredInsightsEnabled}
          />
        ) : null}
        </section>
      </div>
    </main>
  );
}

export function StockProfileWorkspace() {
  return (
    <Suspense
      fallback={
        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
          <div className="mx-auto max-w-7xl">
            <SkeletonBlock className="h-72 w-full" />
          </div>
        </main>
      }
    >
      <StockProfilePageContent />
    </Suspense>
  );
}
