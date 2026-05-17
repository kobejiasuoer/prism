"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./api";
import type { DecisionValue } from "./types";

export const queryKeys = {
  today: ["today"] as const,
  overview: ["overview"] as const,
  watchlist: ["watchlist"] as const,
  watchlistManager: ["watchlist-manager"] as const,
  opportunities: ["opportunities"] as const,
  review: (params: { baseline?: string; window?: string } = {}) =>
    ["review", params.baseline || "", params.window || ""] as const,
  reviewDetail: (params: { section?: string; label?: string; baseline?: string; window?: string } = {}) =>
    ["review-detail", params.section || "", params.label || "", params.baseline || "", params.window || ""] as const,
  ask: (query: string) => ["ask", query] as const,
  askSuggest: (query: string) => ["ask-suggest", query] as const,
  refreshStatus: (page: string, auto = false) => ["refresh-status", page, auto ? "auto" : "passive"] as const,
  stockProfiles: ["stock-profile"] as const,
  stockProfile: (code: string) => ["stock-profile", code] as const,
  parameters: ["parameters"] as const,
  runs: ["runs"] as const,
  health: ["health"] as const,
  portfolioAccount: ["portfolio-account"] as const,
  decisionLedger: ["decision-ledger"] as const,
  decisionLedgerSummary: (params: { window?: string; as_of?: string } = {}) =>
    ["decision-ledger", "summary", params.window || "", params.as_of || ""] as const,
  decisionLedgerRecent: (limit: number) => ["decision-ledger", "recent", limit] as const,
  decisionLedgerStock: (code: string) => ["decision-ledger", "stock", code] as const,
  decisionLedgerDetail: (decisionId: string) => ["decision-ledger", "detail", decisionId] as const,
  decisionLedgerHealth: ["decision-ledger", "health"] as const,
};

export function useTodayData() {
  return useQuery({
    queryKey: queryKeys.today,
    queryFn: api.getToday,
    staleTime: 30_000,
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  });
}

export function useOverview() {
  return useQuery({
    queryKey: queryKeys.overview,
    queryFn: api.getOverview,
    staleTime: 60_000,
    refetchInterval: 120_000,
  });
}

export function useWatchlist() {
  return useQuery({
    queryKey: queryKeys.watchlist,
    queryFn: api.getWatchlist,
    staleTime: 60_000,
    refetchInterval: 120_000,
  });
}

export function useWatchlistManager() {
  return useQuery({
    queryKey: queryKeys.watchlistManager,
    queryFn: api.getWatchlistManager,
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}

export function useOpportunities() {
  return useQuery({
    queryKey: queryKeys.opportunities,
    queryFn: api.getOpportunities,
    staleTime: 45_000,
    refetchInterval: 90_000,
  });
}

export function useReview(params: { baseline?: string; window?: string } = {}) {
  return useQuery({
    queryKey: queryKeys.review(params),
    queryFn: () => api.getReview(params),
    staleTime: 300_000,
    refetchInterval: false,
  });
}

export function useReviewDetail(params: { section?: string; label?: string; baseline?: string; window?: string }) {
  return useQuery({
    queryKey: queryKeys.reviewDetail(params),
    queryFn: () =>
      api.getReviewDetail({
        section: params.section || "",
        label: params.label || "",
        baseline: params.baseline,
        window: params.window,
      }),
    enabled: Boolean(params.section && params.label),
    staleTime: 300_000,
    refetchInterval: false,
  });
}

export function useStockProfile(code: string) {
  return useQuery({
    queryKey: queryKeys.stockProfile(code),
    queryFn: () => api.getStockProfile(code),
    enabled: Boolean(code),
    staleTime: 60_000,
    refetchInterval: 120_000,
  });
}

export function useAsk(query: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.ask(query),
    queryFn: () => api.ask(query),
    enabled: Boolean(query) && enabled,
    staleTime: 60_000,
  });
}

export function useParameters() {
  return useQuery({
    queryKey: queryKeys.parameters,
    queryFn: api.getParameters,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });
}

export function useRuns() {
  return useQuery({
    queryKey: queryKeys.runs,
    queryFn: api.getRuns,
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: api.health,
    staleTime: 15_000,
    refetchInterval: 30_000,
  });
}

export function useRefreshStatus(page: string, enabled = true, options: { auto?: boolean } = {}) {
  const auto = Boolean(options.auto);
  return useQuery({
    queryKey: queryKeys.refreshStatus(page, auto),
    queryFn: () => api.getRefreshStatus(page, { auto }),
    enabled: Boolean(page) && enabled,
    staleTime: 20_000,
    refetchInterval: (query) => {
      const suggested = query.state.data?.suggested_poll_seconds;
      return Math.max(30_000, Number(suggested || 60) * 1000);
    },
  });
}

export function useUpdateTodayActionDecision() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: { trade_date: string; key: string; decision: DecisionValue }) =>
      api.updateTodayActionDecision(payload),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.today });
      void queryClient.invalidateQueries({ queryKey: queryKeys.portfolioAccount });
      // Today action "watch"/"skip" decisions attach execution events to
      // the matching ledger record; invalidate ledger views so the next
      // poll surfaces the new event without waiting for refetchInterval.
      void queryClient.invalidateQueries({ queryKey: queryKeys.decisionLedger });
    },
  });
}

export function useRunTask() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ taskName, payload }: { taskName: string; payload?: Record<string, unknown> }) =>
      api.runTask(taskName, payload || {}),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.overview });
      void queryClient.invalidateQueries({ queryKey: queryKeys.runs });
    },
  });
}

export function useSaveParameters() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (
      args: { payload: { raw: string } | { value: Record<string, unknown> }; unsafeApply?: boolean },
    ) => api.saveParameters(args.payload, args.unsafeApply ?? false),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.parameters });
    },
  });
}

export function useTriggerRefresh(page: string, options: { stockCode?: string } = {}) {
  const queryClient = useQueryClient();
  const stockCode = options.stockCode?.trim();

  return useMutation({
    mutationFn: (payload?: { task_name?: string; force?: boolean; reason?: string }) =>
      api.triggerRefresh({ page, ...(payload || {}) }),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["refresh-status", page] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.overview });
      void queryClient.invalidateQueries({ queryKey: queryKeys.runs });
      if (page === "today") {
        void queryClient.invalidateQueries({ queryKey: queryKeys.today });
      }
      if (page === "watchlist") {
        void queryClient.invalidateQueries({ queryKey: queryKeys.watchlist });
        void queryClient.invalidateQueries({ queryKey: queryKeys.watchlistManager });
        void queryClient.invalidateQueries({ queryKey: queryKeys.stockProfiles });
      }
      if (page === "opportunities") {
        void queryClient.invalidateQueries({ queryKey: queryKeys.opportunities });
        void queryClient.invalidateQueries({ queryKey: queryKeys.stockProfiles });
      }
      if (stockCode) {
        void queryClient.invalidateQueries({ queryKey: queryKeys.stockProfile(stockCode) });
      }
    },
  });
}

export function useAddWatchlistStock() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: { code: string; name?: string; trigger_refresh?: boolean }) =>
      api.addWatchlistStock(payload),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.watchlist });
      void queryClient.invalidateQueries({ queryKey: queryKeys.watchlistManager });
      void queryClient.invalidateQueries({ queryKey: queryKeys.parameters });
    },
  });
}

export function useArchiveWatchlistStock() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: { code: string; trigger_refresh?: boolean }) => api.archiveWatchlistStock(payload),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.watchlist });
      void queryClient.invalidateQueries({ queryKey: queryKeys.watchlistManager });
      void queryClient.invalidateQueries({ queryKey: queryKeys.parameters });
    },
  });
}

export function useRestoreWatchlistStock() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: { code: string; trigger_refresh?: boolean }) => api.restoreWatchlistStock(payload),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.watchlist });
      void queryClient.invalidateQueries({ queryKey: queryKeys.watchlistManager });
      void queryClient.invalidateQueries({ queryKey: queryKeys.parameters });
    },
  });
}

export function usePortfolioAccount() {
  return useQuery({
    queryKey: queryKeys.portfolioAccount,
    queryFn: api.getPortfolioAccount,
    staleTime: 30_000,
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  });
}

export function useSetPortfolioMode() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.setPortfolioMode,
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.portfolioAccount });
      void queryClient.invalidateQueries({ queryKey: queryKeys.today });
    },
  });
}

export function useRefreshPortfolioQuotes() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.refreshPortfolioQuotes,
    onSuccess: (payload) => {
      queryClient.setQueryData(queryKeys.portfolioAccount, payload);
    },
  });
}

export function useRecordPortfolioCash() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.recordPortfolioCash,
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.portfolioAccount });
    },
  });
}

export function useRecordPortfolioFill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.recordPortfolioFill,
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.portfolioAccount });
      void queryClient.invalidateQueries({ queryKey: queryKeys.today });
      void queryClient.invalidateQueries({ queryKey: queryKeys.decisionLedger });
    },
  });
}

export function useRecordPortfolioNoFill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.recordPortfolioNoFill,
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.portfolioAccount });
      void queryClient.invalidateQueries({ queryKey: queryKeys.today });
      void queryClient.invalidateQueries({ queryKey: queryKeys.decisionLedger });
    },
  });
}

export function useRecordPortfolioReconcile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.recordPortfolioReconcile,
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.portfolioAccount });
      void queryClient.invalidateQueries({ queryKey: queryKeys.today });
    },
  });
}

export function useDecisionLedgerSummary(params: { window?: string; as_of?: string } = {}) {
  return useQuery({
    queryKey: queryKeys.decisionLedgerSummary(params),
    queryFn: () => api.getDecisionLedgerSummary(params),
    staleTime: 60_000,
    refetchInterval: 120_000,
  });
}

export function useDecisionLedgerRecent(limit: number = 20) {
  return useQuery({
    queryKey: queryKeys.decisionLedgerRecent(limit),
    queryFn: () => api.getDecisionLedgerRecent({ limit }),
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}

export function useDecisionLedgerStock(code: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.decisionLedgerStock(code),
    queryFn: () => api.getDecisionLedgerStock(code),
    enabled: Boolean(code) && enabled,
    staleTime: 60_000,
  });
}

export function useDecisionLedgerDetail(decisionId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.decisionLedgerDetail(decisionId),
    queryFn: () => api.getDecisionLedgerDetail(decisionId),
    enabled: Boolean(decisionId) && enabled,
    staleTime: 300_000,
  });
}

export function useDecisionLedgerHealth() {
  return useQuery({
    queryKey: queryKeys.decisionLedgerHealth,
    queryFn: api.getDecisionLedgerHealth,
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}
