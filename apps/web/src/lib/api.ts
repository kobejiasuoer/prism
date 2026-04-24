import type {
  AskSuggestResponse,
  DecisionValue,
  HealthResponse,
  OpportunitiesData,
  OverviewData,
  RefreshStatus,
  ReviewData,
  RunItem,
  StockProfileData,
  TodayData,
  WatchlistData,
} from "./types";

export class ApiError extends Error {
  status: number;
  payload: unknown;

  constructor(message: string, status: number, payload: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

type JsonBody = Record<string, unknown> | unknown[];

async function readPayload(response: Response) {
  const text = await response.text();
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

async function fetchJson<T>(path: string, init?: RequestInit & { json?: JsonBody }): Promise<T> {
  const headers = new Headers(init?.headers);
  const request: RequestInit = {
    ...init,
    headers,
  };

  if (init?.json !== undefined) {
    headers.set("Content-Type", "application/json");
    request.body = JSON.stringify(init.json);
  }

  const response = await fetch(path, request);
  const payload = await readPayload(response);

  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? String((payload as { detail?: unknown }).detail)
        : response.statusText;
    throw new ApiError(detail || "Request failed", response.status, payload);
  }

  return payload as T;
}

export const api = {
  getToday() {
    return fetchJson<TodayData>("/api/today");
  },
  getOverview() {
    return fetchJson<OverviewData>("/api/overview");
  },
  getWatchlist() {
    return fetchJson<WatchlistData>("/api/watchlist");
  },
  getWatchlistDetail(code: string) {
    return fetchJson<StockProfileData["watchlist"]>(`/api/watchlist/${encodeURIComponent(code)}`);
  },
  getOpportunities() {
    return fetchJson<OpportunitiesData>("/api/opportunities");
  },
  getOpportunityDetail(code: string) {
    return fetchJson<StockProfileData["opportunity"]>(`/api/opportunities/${encodeURIComponent(code)}`);
  },
  async getStockProfile(code: string): Promise<StockProfileData> {
    const [watchlist, opportunity] = await Promise.allSettled([
      api.getWatchlistDetail(code),
      api.getOpportunityDetail(code),
    ]);

    return {
      code,
      watchlist: watchlist.status === "fulfilled" ? watchlist.value : undefined,
      opportunity: opportunity.status === "fulfilled" ? opportunity.value : undefined,
    };
  },
  getReview() {
    return fetchJson<ReviewData>("/api/review");
  },
  ask(query: string) {
    const q = query ? `?q=${encodeURIComponent(query)}` : "";
    return fetchJson<unknown>(`/api/ask${q}`);
  },
  askSuggest(query: string) {
    const q = query ? `?q=${encodeURIComponent(query)}` : "";
    return fetchJson<AskSuggestResponse>(`/api/ask/suggest${q}`);
  },
  askFollowup(payload: { query: string; question: string; history?: unknown[] }) {
    return fetchJson<unknown>("/api/ask/followup", {
      method: "POST",
      json: payload,
    });
  },
  updateTodayActionDecision(payload: {
    trade_date: string;
    key: string;
    decision: DecisionValue;
  }) {
    return fetchJson<{
      ok: boolean;
      trade_date: string;
      key: string;
      decision: unknown;
      counts: TodayData["action_queue"]["counts"];
    }>("/api/today/actions/decision", {
      method: "POST",
      json: payload,
    });
  },
  getParameters() {
    return fetchJson<unknown>("/api/parameters");
  },
  saveParameters(payload: JsonBody) {
    return fetchJson<unknown>("/api/parameters", {
      method: "POST",
      json: payload,
    });
  },
  runTask(taskName: string, payload: Record<string, unknown> = {}) {
    return fetchJson<unknown>(`/api/tasks/${encodeURIComponent(taskName)}/run`, {
      method: "POST",
      json: payload,
    });
  },
  getRuns() {
    return fetchJson<{ runs: RunItem[] }>("/api/runs");
  },
  getRefreshStatus(page: string) {
    return fetchJson<RefreshStatus>(`/api/refresh/status?page=${encodeURIComponent(page)}`);
  },
  triggerRefresh(payload: { page: string; task_name?: string; force?: boolean }) {
    return fetchJson<unknown>("/api/refresh/trigger", {
      method: "POST",
      json: payload,
    });
  },
  health() {
    return fetchJson<HealthResponse>("/healthz");
  },
};
