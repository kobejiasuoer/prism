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
  review: ["review"] as const,
  ask: (query: string) => ["ask", query] as const,
  askSuggest: (query: string) => ["ask-suggest", query] as const,
  refreshStatus: (page: string) => ["refresh-status", page] as const,
  stockProfiles: ["stock-profile"] as const,
  stockProfile: (code: string) => ["stock-profile", code] as const,
  parameters: ["parameters"] as const,
  runs: ["runs"] as const,
  health: ["health"] as const,
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

export function useReview() {
  return useQuery({
    queryKey: queryKeys.review,
    queryFn: api.getReview,
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

export function useAsk(query: string) {
  return useQuery({
    queryKey: queryKeys.ask(query),
    queryFn: () => api.ask(query),
    enabled: Boolean(query),
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

export function useRefreshStatus(page: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.refreshStatus(page),
    queryFn: () => api.getRefreshStatus(page),
    enabled: Boolean(page) && enabled,
    staleTime: 20_000,
    refetchInterval: 60_000,
  });
}

export function useUpdateTodayActionDecision() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: { trade_date: string; key: string; decision: DecisionValue }) =>
      api.updateTodayActionDecision(payload),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.today });
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
    mutationFn: (payload: { raw: string } | { value: Record<string, unknown> }) => api.saveParameters(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.parameters });
    },
  });
}

export function useTriggerRefresh(page: string, options: { stockCode?: string } = {}) {
  const queryClient = useQueryClient();
  const stockCode = options.stockCode?.trim();

  return useMutation({
    mutationFn: (payload?: { task_name?: string; force?: boolean }) =>
      api.triggerRefresh({ page, ...(payload || {}) }),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.refreshStatus(page) });
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
