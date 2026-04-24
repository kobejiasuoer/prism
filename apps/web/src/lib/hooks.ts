"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./api";
import type { DecisionValue } from "./types";

export const queryKeys = {
  today: ["today"] as const,
  overview: ["overview"] as const,
  watchlist: ["watchlist"] as const,
  opportunities: ["opportunities"] as const,
  review: ["review"] as const,
  askSuggest: (query: string) => ["ask-suggest", query] as const,
  refreshStatus: (page: string) => ["refresh-status", page] as const,
  stockProfile: (code: string) => ["stock-profile", code] as const,
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

export function useRefreshStatus(page: string) {
  return useQuery({
    queryKey: queryKeys.refreshStatus(page),
    queryFn: () => api.getRefreshStatus(page),
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
