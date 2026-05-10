import type {
  AccountMode,
  AskFollowupResponse,
  AskResponse,
  AskSuggestResponse,
  DecisionValue,
  HealthResponse,
  OpportunitiesData,
  OverviewData,
  ParametersResponse,
  PortfolioAccountResponse,
  PreviewPayload,
  ReadinessPayload,
  RefreshStatus,
  RefreshTriggerResponse,
  ReviewData,
  RunItem,
  StockProfileData,
  TaskRunResponse,
  TodayData,
  WatchlistData,
  WatchlistManageResponse,
  WatchlistManagerResponse,
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

const backendOrigin =
  process.env.NEXT_PUBLIC_PRISM_BACKEND_ORIGIN || process.env.PRISM_BACKEND_ORIGIN || "";

function resolveApiUrl(path: string) {
  if (!backendOrigin) {
    return path;
  }
  return new URL(path, backendOrigin).toString();
}

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

function validationErrorsFromPayload(payload: unknown): string[] {
  if (!payload || typeof payload !== "object") {
    return [];
  }
  const validation = (payload as { validation?: unknown }).validation;
  if (!validation || typeof validation !== "object") {
    return [];
  }
  const errors = (validation as { errors?: unknown }).errors;
  if (!Array.isArray(errors)) {
    return [];
  }
  return errors.map((error) => String(error || "").trim()).filter(Boolean);
}

function errorMessageFromPayload(payload: unknown, fallback: string) {
  const detail =
    payload && typeof payload === "object" && "detail" in payload
      ? String((payload as { detail?: unknown }).detail || "").trim()
      : "";
  const validationErrors = validationErrorsFromPayload(payload);

  if (validationErrors.length) {
    return [detail || fallback, ...validationErrors].filter(Boolean).join("\n");
  }
  return detail || fallback;
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

  const response = await fetch(resolveApiUrl(path), request);
  const payload = await readPayload(response);

  if (!response.ok) {
    throw new ApiError(errorMessageFromPayload(payload, response.statusText || "Request failed"), response.status, payload);
  }

  return payload as T;
}

async function fetchText(path: string): Promise<string> {
  const response = await fetch(resolveApiUrl(path));
  const text = await response.text();

  if (!response.ok) {
    throw new ApiError(text || response.statusText || "Request failed", response.status, text);
  }

  return text;
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
  getWatchlistManager() {
    return fetchJson<WatchlistManagerResponse>("/api/watchlist/manage");
  },
  addWatchlistStock(payload: { code: string; name?: string; trigger_refresh?: boolean }) {
    return fetchJson<WatchlistManageResponse>("/api/watchlist/manage/add", {
      method: "POST",
      json: payload,
    });
  },
  archiveWatchlistStock(payload: { code: string; trigger_refresh?: boolean }) {
    return fetchJson<WatchlistManageResponse>("/api/watchlist/manage/archive", {
      method: "POST",
      json: payload,
    });
  },
  restoreWatchlistStock(payload: { code: string; trigger_refresh?: boolean }) {
    return fetchJson<WatchlistManageResponse>("/api/watchlist/manage/restore", {
      method: "POST",
      json: payload,
    });
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
  getStockProfile(code: string) {
    return fetchJson<StockProfileData>(`/api/stock/${encodeURIComponent(code)}`);
  },
  getReview() {
    return fetchJson<ReviewData>("/api/review");
  },
  ask(query: string) {
    const q = query ? `?q=${encodeURIComponent(query)}` : "";
    return fetchJson<AskResponse>(`/api/ask${q}`);
  },
  askSuggest(query: string) {
    const q = query ? `?q=${encodeURIComponent(query)}` : "";
    return fetchJson<AskSuggestResponse>(`/api/ask/suggest${q}`);
  },
  askFollowup(payload: { query: string; question: string; history?: unknown[] }) {
    return fetchJson<AskFollowupResponse>("/api/ask/followup", {
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
    return fetchJson<ParametersResponse>("/api/parameters");
  },
  saveParameters(payload: { raw: string } | { value: Record<string, unknown> }, unsafeApply = false) {
    const body = { ...payload, ...(unsafeApply ? { unsafe_apply: true } : {}) };
    return fetchJson<ParametersResponse>("/api/parameters", {
      method: "POST",
      json: body,
    });
  },
  runTask(taskName: string, payload: Record<string, unknown> = {}) {
    return fetchJson<TaskRunResponse>(`/api/tasks/${encodeURIComponent(taskName)}/run`, {
      method: "POST",
      json: payload,
    });
  },
  getRuns() {
    return fetchJson<{ runs: RunItem[] }>("/api/runs");
  },
  getRunDetail(runId: string) {
    return fetchJson<RunItem>(`/api/runs/${encodeURIComponent(runId)}`);
  },
  getRunLog(runId: string) {
    return fetchText(`/api/runs/${encodeURIComponent(runId)}/log`);
  },
  preview(path: string) {
    return fetchJson<PreviewPayload>(`/api/preview?path=${encodeURIComponent(path)}`);
  },
  getRefreshStatus(page: string, options: { auto?: boolean } = {}) {
    const auto = options.auto ? "&auto=1" : "";
    return fetchJson<RefreshStatus>(`/api/refresh/status?page=${encodeURIComponent(page)}${auto}`);
  },
  getReadinessLive() {
    return fetchJson<ReadinessPayload & { generated_at?: string; trade_date?: string }>(
      "/api/readiness/live",
    );
  },
  triggerRefresh(payload: { page: string; task_name?: string; force?: boolean; reason?: string }) {
    return fetchJson<RefreshTriggerResponse>("/api/refresh/trigger", {
      method: "POST",
      json: payload,
    });
  },
  health() {
    return fetchJson<HealthResponse>("/healthz");
  },
  getPortfolioAccount() {
    return fetchJson<PortfolioAccountResponse>("/api/portfolio/account");
  },
  setPortfolioMode(payload: {
    mode: AccountMode;
    starting_cash?: number;
    note?: string;
    allow_unsafe?: boolean;
  }) {
    return fetchJson<PortfolioAccountResponse>("/api/portfolio/mode", {
      method: "POST",
      json: payload,
    });
  },
  recordPortfolioCash(payload: { delta: number; reason: string }) {
    return fetchJson<PortfolioAccountResponse>("/api/portfolio/cash", {
      method: "POST",
      json: payload,
    });
  },
  recordPortfolioFill(payload: {
    trade_date: string;
    code: string;
    side: "buy" | "sell";
    qty: number;
    price: number;
    fees?: number;
    name?: string;
    broker_ref?: string;
    intent_key?: string;
    note?: string;
  }) {
    return fetchJson<PortfolioAccountResponse>("/api/portfolio/fills", {
      method: "POST",
      json: payload,
    });
  },
  recordPortfolioNoFill(payload: { trade_date: string; intent_key: string; reason: string }) {
    return fetchJson<PortfolioAccountResponse>("/api/portfolio/intent/no_fill", {
      method: "POST",
      json: payload,
    });
  },
  recordPortfolioReconcile(payload: {
    trade_date: string;
    broker_cash: number;
    broker_equity: number;
    note?: string;
  }) {
    return fetchJson<PortfolioAccountResponse>("/api/portfolio/reconcile", {
      method: "POST",
      json: payload,
    });
  },
};
