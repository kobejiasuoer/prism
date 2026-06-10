"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./api";
import { normalizeTaskName } from "./task-utils";
import type {
  DecisionValue,
  OverviewData,
  ParametersResponse,
  PortfolioAccountResponse,
  PortfolioHoldingReviewsResponse,
  RunItem,
  TaskRunResponse,
  TodayActionsData,
} from "./types";

export const queryKeys = {
  shellStatus: ["shell-status"] as const,
  todaySummary: ["today", "summary"] as const,
  todayActions: ["today", "actions"] as const,
  todayActionContracts: ["today", "action-contracts"] as const,
  todayCommandBriefDetail: ["today", "command-brief-detail"] as const,
  overview: (compact = true) => ["overview", compact ? "compact" : "full"] as const,
  watchlist: ["watchlist"] as const,
  watchlistManager: ["watchlist-manager"] as const,
  opportunities: ["opportunities"] as const,
  opportunitiesContext: ["opportunities", "context"] as const,
  opportunitiesSourceCards: ["opportunities", "source-cards"] as const,
  review: (params: { baseline?: string; window?: string } = {}) =>
    ["review", params.baseline || "", params.window || ""] as const,
  reviewEvidence: (params: { baseline?: string; window?: string } = {}) =>
    ["review", "evidence", params.baseline || "", params.window || ""] as const,
  reviewShadowReplay: ["review", "shadow-replay"] as const,
  ask: (query: string) => ["ask", query] as const,
  refreshStatus: (page: string, auto = false, compact = false) =>
    ["refresh-status", page, auto ? "auto" : "passive", compact ? "compact" : "full"] as const,
  stockProfileSummary: (code: string) => ["stock-profile", code, "summary"] as const,
  stockProfileDetail: (code: string) => ["stock-profile", code, "detail"] as const,
  stockProfileEvidence: (code: string) => ["stock-profile", code, "evidence"] as const,
  stockProfileSecondary: (code: string) => ["stock-profile", code, "secondary"] as const,
  stockProfileFormalData: (code: string) => ["stock-profile", code, "formal-data"] as const,
  stockProfileFormalDataSection: (code: string, section: string) => ["stock-profile", code, "formal-data", section] as const,
  stockProfileTodayAction: (code: string) => ["stock-profile", code, "today-action"] as const,
  stockProfileLearningScorecard: (code: string) => ["stock-profile", code, "learning-scorecard"] as const,
  parameters: ["parameters"] as const,
  runs: ["runs"] as const,
  health: ["health"] as const,
  formalData: (compact = true) => ["formal-data", compact ? "compact" : "full"] as const,
  dataAssets: (compact = true) => ["data-assets", compact ? "compact" : "full"] as const,
  portfolioAccount: ["portfolio-account"] as const,
  portfolioAccountHistory: ["portfolio-account", "history"] as const,
  portfolioHoldingReviews: ["portfolio-account", "holding-reviews"] as const,
  decisionLedger: ["decision-ledger"] as const,
  decisionLedgerRecent: (params: DecisionLedgerRecentParams = {}) => {
    const codes = (params.codes || [])
      .map((code) => String(code || "").trim().toLowerCase())
      .filter(Boolean)
      .sort();
    return [
      "decision-ledger",
      "recent",
      params.limit || "",
      codes.join(","),
      params.latestPerCode ? "latest-per-code" : "all",
    ] as const;
  },
  decisionLedgerCalibration: (params: { window?: string; as_of?: string; limit?: number } = {}) =>
    ["decision-ledger", "calibration", params.window || "", params.as_of || "", params.limit || ""] as const,
  decisionLedgerCalibrationDetail: (params: { window?: string; as_of?: string; limit?: number } = {}) =>
    ["decision-ledger", "calibration-detail", params.window || "", params.as_of || "", params.limit || ""] as const,
  decisionLedgerLearningLoop: (params: { as_of?: string } = {}) =>
    ["decision-ledger", "learning-loop", params.as_of || ""] as const,
  decisionLedgerShadowCalibration: ["decision-ledger", "shadow-calibration"] as const,
  decisionLedgerReviewCase: (decisionId: string) => ["decision-ledger", "review-case", decisionId] as const,
  decisionLedgerStock: (code: string) => ["decision-ledger", "stock", code] as const,
  decisionLedgerHealth: ["decision-ledger", "health"] as const,
};

type DecisionLedgerRecentParams = {
  limit?: number;
  codes?: string[];
  latestPerCode?: boolean;
};

function decisionLedgerRecentParams(
  paramsOrLimit: number | DecisionLedgerRecentParams = 20,
): DecisionLedgerRecentParams {
  if (typeof paramsOrLimit === "number") {
    return { limit: paramsOrLimit };
  }
  return paramsOrLimit;
}

function portfolioHoldingReviewsFromAccount(payload: PortfolioAccountResponse): PortfolioHoldingReviewsResponse {
  const reviews = payload.holding_reviews || [];
  return {
    generated_at: payload.generated_at,
    trade_date: payload.trade_date,
    expected_trade_date: payload.expected_trade_date,
    data_trade_date: payload.data_trade_date,
    readiness_mode: payload.readiness?.readiness_mode,
    market_quotes: payload.market_quotes,
    holding_reviews: reviews,
    holding_action_summary: payload.holding_action_summary || {
      total: reviews.length,
      must_review: reviews.filter((item) => item.must_review).length,
      review_sell: 0,
      reduce_watch: 0,
      evidence_blocked: 0,
      missing_plan: 0,
      missing_analysis: 0,
      hold: 0,
      generated_at: payload.generated_at,
      expected_trade_date: payload.expected_trade_date,
    },
    position_count: payload.account?.open_positions?.length || 0,
  };
}

function compactPortfolioAccountPayload(payload: PortfolioAccountResponse): PortfolioAccountResponse {
  const account = { ...payload.account };
  for (const key of [
    "fills",
    "closed_positions",
    "reconciliations",
    "position_plans",
    "identity_corrections",
    "mode_history",
    "available_modes",
  ] as const) {
    delete account[key];
  }

  const compactPayload: PortfolioAccountResponse = {
    ...payload,
    account,
    holding_reviews_deferred: true,
    account_history_deferred: true,
  };
  delete compactPayload.holding_reviews;
  delete compactPayload.holding_action_summary;
  return compactPayload;
}

function invalidateActiveTodayWorkspace(queryClient: ReturnType<typeof useQueryClient>, scopes: Array<"summary" | "actions" | "contracts">) {
  if (scopes.includes("summary")) {
    void queryClient.invalidateQueries({ queryKey: queryKeys.todaySummary, refetchType: "active" });
    void queryClient.invalidateQueries({ queryKey: queryKeys.todayCommandBriefDetail, refetchType: "active" });
  }
  if (scopes.includes("actions")) {
    void queryClient.invalidateQueries({ queryKey: queryKeys.todayActions, refetchType: "active" });
  }
  if (scopes.includes("contracts")) {
    void queryClient.invalidateQueries({ queryKey: queryKeys.todayActionContracts, refetchType: "active" });
  }
}

function invalidateStockProfileWorkspace(queryClient: ReturnType<typeof useQueryClient>, code?: string) {
  const normalizedCode = code?.trim();
  const queryKey = normalizedCode ? ["stock-profile", normalizedCode] : ["stock-profile"];
  void queryClient.invalidateQueries({ queryKey, refetchType: "active" });
}

function invalidateStockProfileDecisionWorkspace(queryClient: ReturnType<typeof useQueryClient>, code?: string) {
  const normalizedCode = code?.trim();
  if (normalizedCode) {
    void queryClient.invalidateQueries({ queryKey: queryKeys.stockProfileSummary(normalizedCode), refetchType: "active" });
    void queryClient.invalidateQueries({ queryKey: queryKeys.stockProfileDetail(normalizedCode), refetchType: "active" });
    void queryClient.invalidateQueries({ queryKey: queryKeys.stockProfileEvidence(normalizedCode), refetchType: "active" });
    void queryClient.invalidateQueries({ queryKey: queryKeys.stockProfileSecondary(normalizedCode), refetchType: "active" });
    void queryClient.invalidateQueries({ queryKey: queryKeys.stockProfileTodayAction(normalizedCode), refetchType: "active" });
    return;
  }
  void queryClient.invalidateQueries({
    predicate: (query) => {
      const queryKey = query.queryKey;
      return (
        queryKey[0] === "stock-profile" &&
        typeof queryKey[2] === "string" &&
        ["summary", "detail", "evidence", "secondary", "today-action"].includes(queryKey[2])
      );
    },
    refetchType: "active",
  });
}

function invalidateStockProfileTodayAction(queryClient: ReturnType<typeof useQueryClient>, code?: string) {
  const normalizedCode = code?.trim();
  if (!normalizedCode) {
    return;
  }
  void queryClient.invalidateQueries({ queryKey: queryKeys.stockProfileTodayAction(normalizedCode), refetchType: "active" });
}

function stockCodeKeyFromValue(value?: string) {
  const raw = String(value || "")
    .trim()
    .toLowerCase();
  const match = raw.match(/^(?:sh|sz|bj)?(\d{6})$/);
  return match?.[1] || raw;
}

function stockCodeFromActionKey(key?: string) {
  const match = String(key || "").match(/(?:sh|sz|bj)?(\d{6})(?!\d)/i);
  return match?.[1] || "";
}

function invalidateActiveDecisionLedgerExecutionViews(
  queryClient: ReturnType<typeof useQueryClient>,
  codes: Array<string | undefined> = [],
) {
  const codeSet = new Set(codes.map(stockCodeKeyFromValue).filter(Boolean));
  void queryClient.invalidateQueries({
    predicate: (query) => {
      const queryKey = query.queryKey;
      if (queryKey[0] !== "decision-ledger") {
        return false;
      }
      if (queryKey[1] === "recent") {
        if (!codeSet.size) {
          return true;
        }
        const queryCodes = String(queryKey[3] || "")
          .split(",")
          .map(stockCodeKeyFromValue)
          .filter(Boolean);
        return !queryCodes.length || queryCodes.some((code) => codeSet.has(code));
      }
      if (queryKey[1] === "stock") {
        if (!codeSet.size) {
          return true;
        }
        return codeSet.has(stockCodeKeyFromValue(String(queryKey[2] || "")));
      }
      return false;
    },
    refetchType: "active",
  });
}

function taskNameFromRunPayload(payload: { canonical_task_name?: string; task_name?: string } | undefined, fallback?: string) {
  return normalizeTaskName(payload?.canonical_task_name || payload?.task_name || fallback);
}

function runItemFromTaskStart(payload: TaskRunResponse, taskName: string): RunItem {
  const normalized = normalizeTaskName(taskName);
  return {
    run_id: payload.run_id,
    task_id: payload.run_id,
    task_name: normalized || payload.task_name,
    title: payload.title,
    status: payload.started ? "running" : "started",
    log_path: payload.log_path,
    meta_path: payload.meta_path,
    send_to_feishu: payload.send_to_feishu,
  };
}

function patchOverviewTaskRun(current: OverviewData | undefined, taskName: string, run: RunItem): OverviewData | undefined {
  if (!current?.tasks?.length) {
    return current;
  }
  const normalized = normalizeTaskName(taskName);
  let changed = false;
  const tasks = current.tasks.map((task) => {
    const candidate = normalizeTaskName(task.task_name || task.name);
    if (candidate !== normalized) {
      return task;
    }
    changed = true;
    return {
      ...task,
      last_run: {
        ...(task.last_run || {}),
        ...run,
        title: run.title || task.title || task.last_run?.title,
      },
    };
  });
  return changed ? { ...current, tasks } : current;
}

function patchRunsCache(
  current: { runs: RunItem[]; compact: boolean } | undefined,
  run: RunItem,
): { runs: RunItem[]; compact: boolean } | undefined {
  if (!current?.runs || !run.run_id) {
    return current;
  }
  return {
    ...current,
    runs: [run, ...current.runs.filter((item) => item.run_id !== run.run_id && item.task_id !== run.run_id)],
  };
}

function patchTaskStartCaches(queryClient: ReturnType<typeof useQueryClient>, payload: TaskRunResponse, taskName: string) {
  const normalized = taskNameFromRunPayload(payload, taskName);
  const run = runItemFromTaskStart(payload, normalized);
  queryClient.setQueryData<{ runs: RunItem[]; compact: boolean } | undefined>(queryKeys.runs, (current) =>
    patchRunsCache(current, run),
  );
  for (const compact of [true, false]) {
    queryClient.setQueryData<OverviewData | undefined>(queryKeys.overview(compact), (current) =>
      patchOverviewTaskRun(current, normalized, run),
    );
  }
}

function refreshStatusPagesForTask(taskName: string) {
  const normalized = normalizeTaskName(taskName);
  if (!normalized) {
    return [];
  }
  if (normalized.startsWith("formal_data_refresh")) {
    return ["today"];
  }
  if (["morning_warmup", "quotes_light", "capital_flow_light", "watchlist_refresh"].includes(normalized)) {
    return ["today", "watchlist"];
  }
  if (["aggressive", "midday_refresh", "midday_confirmation"].includes(normalized)) {
    return ["today", "watchlist", "opportunities"];
  }
  if (["command_brief", "preclose_risk_refresh", "postclose_command_brief"].includes(normalized)) {
    return ["today", "watchlist", "review"];
  }
  if (normalized === "decision_ledger_outcomes") {
    return ["review"];
  }
  return [];
}

function invalidateActiveRefreshStatuses(queryClient: ReturnType<typeof useQueryClient>, pages: string[]) {
  const pageSet = new Set(pages);
  if (!pageSet.size) {
    return;
  }
  void queryClient.invalidateQueries({
    predicate: (query) => query.queryKey[0] === "refresh-status" && pageSet.has(String(query.queryKey[1] || "")),
    refetchType: "active",
  });
}

function invalidateActiveFormalDataStatus(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({
    predicate: (query) => query.queryKey[0] === "formal-data",
    refetchType: "active",
  });
}

function invalidateAfterTaskStart(queryClient: ReturnType<typeof useQueryClient>, taskName: string) {
  const normalized = normalizeTaskName(taskName);
  void queryClient.invalidateQueries({ queryKey: queryKeys.runs, refetchType: "active" });
  invalidateActiveRefreshStatuses(queryClient, refreshStatusPagesForTask(normalized));
  if (normalized.startsWith("formal_data_refresh")) {
    invalidateActiveFormalDataStatus(queryClient);
  }
}

function setPortfolioAccountCache(queryClient: ReturnType<typeof useQueryClient>, payload: PortfolioAccountResponse) {
  if (!payload.account_history_deferred) {
    queryClient.setQueryData(queryKeys.portfolioAccountHistory, payload);
  }
  queryClient.setQueryData(
    queryKeys.portfolioAccount,
    payload.account_history_deferred ? payload : compactPortfolioAccountPayload(payload),
  );
  if (!payload.holding_reviews_deferred && Array.isArray(payload.holding_reviews)) {
    queryClient.setQueryData(queryKeys.portfolioHoldingReviews, portfolioHoldingReviewsFromAccount(payload));
  }
}

function invalidateActivePortfolioHoldingReviews(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: queryKeys.portfolioHoldingReviews, refetchType: "active" });
}

function updateWatchlistManagerCache(
  queryClient: ReturnType<typeof useQueryClient>,
  payload: { manager?: unknown },
) {
  if (payload.manager) {
    queryClient.setQueryData(queryKeys.watchlistManager, { manager: payload.manager });
  }
  void queryClient.invalidateQueries({ queryKey: queryKeys.watchlist, refetchType: "active" });
}

function patchTodayActionDecision(
  payload: TodayActionsData | undefined,
  result: { key: string; decision: TodayActionsData["action_queue"]["items"][number]["decision"]; counts: TodayActionsData["action_queue"]["counts"] },
): TodayActionsData | undefined {
  if (!payload?.action_queue) {
    return payload;
  }
  const patchItem = (item: TodayActionsData["action_queue"]["items"][number]) =>
    item.key === result.key ? { ...item, decision: result.decision } : item;
  return {
    ...payload,
    action_queue: {
      ...payload.action_queue,
      items: payload.action_queue.items.map(patchItem),
      stale_items: payload.action_queue.stale_items?.map(patchItem),
      counts: result.counts,
    },
  };
}

export function useShellStatus(options: { enabled?: boolean } = {}) {
  const enabled = options.enabled ?? true;
  return useQuery({
    queryKey: queryKeys.shellStatus,
    queryFn: api.getShellStatus,
    enabled,
    staleTime: 120_000,
    refetchInterval: 180_000,
    refetchOnWindowFocus: false,
  });
}

export function useTodaySummary() {
  return useQuery({
    queryKey: queryKeys.todaySummary,
    queryFn: () => api.getTodaySummary(),
    staleTime: 45_000,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });
}

export function useTodayActions(options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.todayActions,
    queryFn: () => api.getTodayActions(),
    enabled: options.enabled ?? true,
    staleTime: 45_000,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });
}

export function useTodayActionContracts(options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.todayActionContracts,
    queryFn: () => api.getTodayActionContracts(),
    enabled: options.enabled ?? true,
    staleTime: 45_000,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });
}

export function useTodayCommandBriefDetail(options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.todayCommandBriefDetail,
    queryFn: () => api.getTodayCommandBriefDetail(),
    enabled: options.enabled ?? true,
    staleTime: 45_000,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });
}

export function useOverview(options: { compact?: boolean } = {}) {
  const compact = options.compact ?? true;
  return useQuery({
    queryKey: queryKeys.overview(compact),
    queryFn: () => api.getOverview({ compact }),
    staleTime: 60_000,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });
}

export function useWatchlist(options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.watchlist,
    queryFn: () => api.getWatchlist(),
    enabled: options.enabled ?? true,
    staleTime: 60_000,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });
}

export function useWatchlistManager(options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.watchlistManager,
    queryFn: () => api.getWatchlistManager(),
    enabled: options.enabled ?? true,
    staleTime: 30_000,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });
}

export function useOpportunities() {
  return useQuery({
    queryKey: queryKeys.opportunities,
    queryFn: () => api.getOpportunities(),
    staleTime: 45_000,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });
}

export function useOpportunitiesContext(options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.opportunitiesContext,
    queryFn: () => api.getOpportunitiesContext(),
    enabled: options.enabled ?? true,
    staleTime: 45_000,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });
}

export function useOpportunitiesSourceCards(options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.opportunitiesSourceCards,
    queryFn: () => api.getOpportunitiesSourceCards(),
    enabled: options.enabled ?? true,
    staleTime: 45_000,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });
}

export function useReview(
  params: { baseline?: string; window?: string } = {},
  options: { enabled?: boolean } = {},
) {
  return useQuery({
    queryKey: queryKeys.review(params),
    queryFn: () => api.getReview(params),
    enabled: options.enabled ?? true,
    staleTime: 30_000,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });
}

export function useReviewEvidence(
  params: { baseline?: string; window?: string } = {},
  options: { enabled?: boolean } = {},
) {
  return useQuery({
    queryKey: queryKeys.reviewEvidence(params),
    queryFn: () => api.getReviewEvidence(params),
    enabled: options.enabled ?? true,
    staleTime: 30_000,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });
}

export function useReviewShadowReplay(options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.reviewShadowReplay,
    queryFn: () => api.getReviewShadowReplay(),
    enabled: options.enabled ?? true,
    staleTime: 120_000,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });
}

export function useStockProfileSummary(code: string) {
  return useQuery({
    queryKey: queryKeys.stockProfileSummary(code),
    queryFn: () => api.getStockProfileSummary(code),
    enabled: Boolean(code),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });
}

export function useStockProfileDetail(code: string, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.stockProfileDetail(code),
    queryFn: () => api.getStockProfileDetail(code),
    enabled: Boolean(code) && (options.enabled ?? true),
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });
}

export function useStockProfileEvidence(code: string, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.stockProfileEvidence(code),
    queryFn: () => api.getStockProfileEvidence(code),
    enabled: Boolean(code) && (options.enabled ?? true),
    staleTime: 120_000,
    refetchOnWindowFocus: false,
  });
}

export function useStockProfileSecondary(code: string, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.stockProfileSecondary(code),
    queryFn: () => api.getStockProfileSecondary(code),
    enabled: Boolean(code) && (options.enabled ?? true),
    staleTime: 120_000,
    refetchOnWindowFocus: false,
  });
}

export function useStockProfileFormalData(code: string, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.stockProfileFormalData(code),
    queryFn: () => api.getStockProfileFormalData(code),
    enabled: Boolean(code) && (options.enabled ?? true),
    staleTime: 120_000,
    refetchOnWindowFocus: false,
  });
}

export function useStockProfileFormalDataSection(code: string, section: string, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.stockProfileFormalDataSection(code, section),
    queryFn: () => api.getStockProfileFormalDataSection(code, section),
    enabled: Boolean(code && section) && (options.enabled ?? true),
    staleTime: 120_000,
    refetchOnWindowFocus: false,
  });
}

export function useStockProfileTodayAction(code: string, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.stockProfileTodayAction(code),
    queryFn: () => api.getStockProfileTodayAction(code),
    enabled: Boolean(code) && (options.enabled ?? true),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });
}

export function useStockProfileLearningScorecard(code: string, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.stockProfileLearningScorecard(code),
    queryFn: () => api.getStockProfileLearningScorecard(code),
    enabled: Boolean(code) && (options.enabled ?? true),
    staleTime: 120_000,
    refetchOnWindowFocus: false,
  });
}

export function useAsk(query: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.ask(query),
    queryFn: () => api.ask(query),
    enabled: Boolean(query) && enabled,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });
}

export function useParameters(options: { enabled?: boolean } = {}) {
  const enabled = options.enabled ?? true;
  return useQuery({
    queryKey: queryKeys.parameters,
    queryFn: api.getParameters,
    enabled,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });
}

export function useRuns(options: { enabled?: boolean } = {}) {
  const enabled = options.enabled ?? true;
  return useQuery({
    queryKey: queryKeys.runs,
    queryFn: () => api.getRuns(),
    enabled,
    staleTime: 30_000,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });
}

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: api.health,
    staleTime: 15_000,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });
}

export function useFormalDataStatus(options: { compact?: boolean; enabled?: boolean } = {}) {
  const enabled = options.enabled ?? true;
  const compact = options.compact ?? true;
  return useQuery({
    queryKey: queryKeys.formalData(compact),
    queryFn: () => api.getFormalDataStatus({ compact }),
    enabled,
    staleTime: 30_000,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });
}

export function useDataAssetsStatus(options: { compact?: boolean; enabled?: boolean } = {}) {
  const compact = options.compact ?? true;
  const enabled = options.enabled ?? true;
  return useQuery({
    queryKey: queryKeys.dataAssets(compact),
    queryFn: () => api.getDataAssetsStatus({ compact }),
    enabled,
    staleTime: 30_000,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });
}

export function useRefreshStatus(page: string, enabled = true, options: { auto?: boolean; compact?: boolean; poll?: boolean } = {}) {
  const auto = Boolean(options.auto);
  const compact = options.compact ?? true;
  const poll = options.poll ?? false;
  return useQuery({
    queryKey: queryKeys.refreshStatus(page, auto, compact),
    queryFn: () => api.getRefreshStatus(page, { auto, compact }),
    enabled: Boolean(page) && enabled,
    staleTime: 20_000,
    refetchInterval: (query) => {
      if (!poll) {
        return false;
      }
      const suggested = query.state.data?.suggested_poll_seconds;
      return Math.max(10_000, Number(suggested || 60) * 1000);
    },
    refetchOnWindowFocus: false,
  });
}

export function useUpdateTodayActionDecision() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: { trade_date: string; key: string; decision: DecisionValue }) =>
      api.updateTodayActionDecision(payload),
    onSuccess: (result, variables) => {
      queryClient.setQueryData<TodayActionsData | undefined>(queryKeys.todayActions, (current) =>
        patchTodayActionDecision(current, result),
      );
      invalidateStockProfileTodayAction(queryClient, stockCodeFromActionKey(variables.key));
      // Today action "watch"/"skip" decisions attach execution events to
      // the matching ledger record; invalidate ledger views so the next
      // poll surfaces the new event without waiting for refetchInterval.
      if (variables.decision === "watch" || variables.decision === "skip") {
        invalidateActiveDecisionLedgerExecutionViews(queryClient, [stockCodeFromActionKey(variables.key)]);
      }
    },
  });
}

export function useRunTask() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ taskName, payload }: { taskName: string; payload?: Record<string, unknown> }) =>
      api.runTask(taskName, payload || {}),
    onSuccess: (payload, variables) => {
      const taskName = taskNameFromRunPayload(payload, variables.taskName);
      patchTaskStartCaches(queryClient, payload, taskName);
      invalidateAfterTaskStart(queryClient, taskName);
    },
  });
}

export function useSaveParameters() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (
      args: { payload: { raw: string } | { value: Record<string, unknown> }; unsafeApply?: boolean },
    ) => api.saveParameters(args.payload, args.unsafeApply ?? false),
    onSuccess: (payload) => {
      queryClient.setQueryData<ParametersResponse>(queryKeys.parameters, payload);
    },
  });
}

export function useTriggerRefresh(page: string, options: { stockCode?: string } = {}) {
  const queryClient = useQueryClient();
  const stockCode = options.stockCode?.trim();

  return useMutation({
    mutationFn: (payload?: { task_name?: string; force?: boolean; reason?: string }) =>
      api.triggerRefresh({ page, ...(payload || {}) }),
    onSuccess: (payload) => {
      queryClient.setQueryData(queryKeys.refreshStatus(page, false, false), payload.status);
      queryClient.setQueryData(queryKeys.refreshStatus(page, false, true), payload.status);
      queryClient.setQueryData(queryKeys.refreshStatus(page, true, false), payload.status);
      queryClient.setQueryData(queryKeys.refreshStatus(page, true, true), payload.status);
      void queryClient.invalidateQueries({ queryKey: queryKeys.runs, refetchType: "active" });
      if (page === "today") {
        invalidateActiveTodayWorkspace(queryClient, ["summary", "actions"]);
        invalidateActiveFormalDataStatus(queryClient);
      }
      if (page === "watchlist") {
        void queryClient.invalidateQueries({ queryKey: queryKeys.watchlist, refetchType: "active" });
        void queryClient.invalidateQueries({ queryKey: queryKeys.watchlistManager, refetchType: "active" });
      }
      if (page === "opportunities") {
        void queryClient.invalidateQueries({ queryKey: queryKeys.opportunities, refetchType: "active" });
        void queryClient.invalidateQueries({ queryKey: queryKeys.opportunitiesContext, refetchType: "active" });
        void queryClient.invalidateQueries({ queryKey: queryKeys.opportunitiesSourceCards, refetchType: "active" });
      }
      if (page === "review") {
        void queryClient.invalidateQueries({ queryKey: ["review"], refetchType: "active" });
        void queryClient.invalidateQueries({ queryKey: ["review-detail"], refetchType: "active" });
        void queryClient.invalidateQueries({ queryKey: queryKeys.decisionLedger, refetchType: "active" });
      }
      if (stockCode) {
        invalidateStockProfileWorkspace(queryClient, stockCode);
      }
    },
  });
}

export function useAddWatchlistStock() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: { code: string; name?: string; trigger_refresh?: boolean }) =>
      api.addWatchlistStock(payload),
    onSuccess: (payload, variables) => {
      updateWatchlistManagerCache(queryClient, payload);
      invalidateStockProfileDecisionWorkspace(queryClient, variables.code);
    },
  });
}

export function useArchiveWatchlistStock() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: { code: string; trigger_refresh?: boolean }) => api.archiveWatchlistStock(payload),
    onSuccess: (payload, variables) => {
      updateWatchlistManagerCache(queryClient, payload);
      invalidateStockProfileDecisionWorkspace(queryClient, variables.code);
    },
  });
}

export function useRestoreWatchlistStock() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: { code: string; trigger_refresh?: boolean }) => api.restoreWatchlistStock(payload),
    onSuccess: (payload, variables) => {
      updateWatchlistManagerCache(queryClient, payload);
      invalidateStockProfileDecisionWorkspace(queryClient, variables.code);
    },
  });
}

export function usePortfolioAccount() {
  return useQuery({
    queryKey: queryKeys.portfolioAccount,
    queryFn: () => api.getPortfolioAccount(),
    staleTime: 30_000,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });
}

export function usePortfolioAccountHistory(options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.portfolioAccountHistory,
    queryFn: () => api.getPortfolioAccount({ history: true }),
    enabled: options.enabled ?? true,
    staleTime: 30_000,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });
}

export function usePortfolioHoldingReviews(options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.portfolioHoldingReviews,
    queryFn: () => api.getPortfolioHoldingReviews(),
    enabled: options.enabled ?? true,
    staleTime: 45_000,
    refetchOnWindowFocus: false,
  });
}

export function useSetPortfolioMode() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.setPortfolioMode,
    onSuccess: (payload) => {
      setPortfolioAccountCache(queryClient, payload);
      invalidateActivePortfolioHoldingReviews(queryClient);
      invalidateActiveTodayWorkspace(queryClient, ["summary", "actions"]);
      invalidateStockProfileDecisionWorkspace(queryClient);
    },
  });
}

export function useRefreshPortfolioQuotes() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.refreshPortfolioQuotes,
    onSuccess: (payload) => {
      setPortfolioAccountCache(queryClient, payload);
    },
  });
}

export function useRecordPortfolioCash() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.recordPortfolioCash,
    onSuccess: (payload) => {
      setPortfolioAccountCache(queryClient, payload);
      invalidateActivePortfolioHoldingReviews(queryClient);
      invalidateStockProfileDecisionWorkspace(queryClient);
    },
  });
}

export function useRecordPortfolioFill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.recordPortfolioFill,
    onSuccess: (payload, variables) => {
      setPortfolioAccountCache(queryClient, payload);
      invalidateActivePortfolioHoldingReviews(queryClient);
      invalidateActiveTodayWorkspace(queryClient, ["summary", "actions"]);
      invalidateStockProfileDecisionWorkspace(queryClient, variables.code);
      invalidateActiveDecisionLedgerExecutionViews(queryClient, [variables.code]);
    },
  });
}

export function useAmendPortfolioHoldingIdentity() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.amendPortfolioHoldingIdentity,
    onSuccess: (payload, variables) => {
      setPortfolioAccountCache(queryClient, payload);
      invalidateActivePortfolioHoldingReviews(queryClient);
      invalidateActiveTodayWorkspace(queryClient, ["summary", "actions"]);
      invalidateStockProfileDecisionWorkspace(queryClient, variables.from_code);
      invalidateStockProfileDecisionWorkspace(queryClient, variables.to_code);
      invalidateActiveDecisionLedgerExecutionViews(queryClient, [variables.from_code, variables.to_code]);
    },
  });
}

export function useRecordPortfolioNoFill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.recordPortfolioNoFill,
    onSuccess: (payload, variables) => {
      setPortfolioAccountCache(queryClient, payload);
      invalidateActivePortfolioHoldingReviews(queryClient);
      invalidateActiveTodayWorkspace(queryClient, ["summary", "actions"]);
      invalidateStockProfileDecisionWorkspace(queryClient, stockCodeFromActionKey(variables.intent_key));
      invalidateActiveDecisionLedgerExecutionViews(queryClient, [stockCodeFromActionKey(variables.intent_key)]);
    },
  });
}

export function useRecordPortfolioReconcile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.recordPortfolioReconcile,
    onSuccess: (payload) => {
      setPortfolioAccountCache(queryClient, payload);
      invalidateActivePortfolioHoldingReviews(queryClient);
      invalidateActiveTodayWorkspace(queryClient, ["summary", "actions"]);
      invalidateStockProfileDecisionWorkspace(queryClient);
    },
  });
}

export function useDecisionLedgerRecent(
  paramsOrLimit: number | DecisionLedgerRecentParams = 20,
  options: { enabled?: boolean } = {},
) {
  const params = decisionLedgerRecentParams(paramsOrLimit);
  const enabled = options.enabled ?? true;
  return useQuery({
    queryKey: queryKeys.decisionLedgerRecent(params),
    queryFn: () => api.getDecisionLedgerRecent(params),
    enabled,
    staleTime: 30_000,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });
}

export function useDecisionLedgerCalibration(params: { window?: string; as_of?: string; limit?: number } = {}) {
  return useQuery({
    queryKey: queryKeys.decisionLedgerCalibration(params),
    queryFn: () => api.getDecisionLedgerCalibration(params),
    staleTime: 60_000,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });
}

export function useDecisionLedgerCalibrationDetail(
  params: { window?: string; as_of?: string; limit?: number } = {},
  options: { enabled?: boolean } = {},
) {
  return useQuery({
    queryKey: queryKeys.decisionLedgerCalibrationDetail(params),
    queryFn: () => api.getDecisionLedgerCalibrationDetail(params),
    enabled: options.enabled ?? true,
    staleTime: 60_000,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });
}

export function useDecisionLedgerLearningLoop(
  params: { as_of?: string } = {},
  options: { enabled?: boolean } = {},
) {
  return useQuery({
    queryKey: queryKeys.decisionLedgerLearningLoop(params),
    queryFn: () => api.getDecisionLedgerLearningLoop(params),
    enabled: options.enabled ?? true,
    staleTime: 60_000,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });
}

export function useDecisionLedgerShadowCalibration(options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.decisionLedgerShadowCalibration,
    queryFn: () => api.getDecisionLedgerShadowCalibration(),
    enabled: options.enabled ?? true,
    staleTime: 120_000,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });
}

export function useDecisionLedgerReviewCase(decisionId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.decisionLedgerReviewCase(decisionId),
    queryFn: () => api.getDecisionLedgerReviewCase(decisionId),
    enabled: Boolean(decisionId) && enabled,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });
}

export function useSaveDecisionLedgerReviewCase() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ decisionId, payload }: {
      decisionId: string;
      payload: Parameters<typeof api.saveDecisionLedgerReviewCase>[1];
    }) => api.saveDecisionLedgerReviewCase(decisionId, payload),
    onSuccess: (response, variables) => {
      queryClient.setQueryData(queryKeys.decisionLedgerReviewCase(variables.decisionId), response.workbench);
      void queryClient.invalidateQueries({ queryKey: queryKeys.decisionLedger, refetchType: "active" });
    },
  });
}

export function useGenerateDecisionLedgerAttributionDraft() {
  return useMutation({
    mutationFn: (decisionId: string) => api.generateDecisionLedgerAttributionDraft(decisionId),
  });
}

export function useAutoReviewDecisionLedgerCase() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (decisionId: string) => api.autoReviewDecisionLedgerCase(decisionId),
    onSuccess: (response, decisionId) => {
      queryClient.setQueryData(queryKeys.decisionLedgerReviewCase(decisionId), response.workbench);
      void queryClient.invalidateQueries({ queryKey: queryKeys.decisionLedger, refetchType: "active" });
      void queryClient.invalidateQueries({ queryKey: ["review"], refetchType: "active" });
    },
  });
}

export function useDecisionLedgerStock(code: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.decisionLedgerStock(code),
    queryFn: () => api.getDecisionLedgerStock(code),
    enabled: Boolean(code) && enabled,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });
}

export function useDecisionLedgerHealth(enabled = true) {
  return useQuery({
    queryKey: queryKeys.decisionLedgerHealth,
    queryFn: api.getDecisionLedgerHealth,
    enabled,
    staleTime: 30_000,
    refetchInterval: false,
    refetchOnWindowFocus: false,
  });
}
