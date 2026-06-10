import type {
  AccountMode,
  AskFollowupResponse,
  AskResponse,
  AskSuggestResponse,
  DecisionLedgerAttributionDraftResponse,
  DecisionLedgerAutoReviewResponse,
  DecisionLedgerCalibrationDetailResponse,
  DecisionLedgerCalibrationResponse,
  DecisionLedgerHealthResponse,
  DecisionLedgerLearningLoopResponse,
  DecisionLedgerRecentResponse,
  DecisionLedgerReviewCaseSavePayload,
  DecisionLedgerReviewCaseSaveResponse,
  DecisionLedgerReviewCaseWorkbench,
  DecisionLedgerStockResponse,
  DataAssetsStatus,
  DecisionValue,
  FormalDataStatus,
  HealthResponse,
  OpportunitiesData,
  OverviewData,
  ParametersResponse,
  PortfolioAccountResponse,
  PortfolioHoldingReviewsResponse,
  PreviewPayload,
  RefreshStatus,
  RefreshTriggerResponse,
  ReviewData,
  ReviewEvidenceResponse,
  ReviewResearchResponse,
  RunItem,
  ShellStatusResponse,
  ShadowCalibrationSummary,
  ShadowReplayReviewSummary,
  StockProfileDetailData,
  StockProfileEvidenceResponse,
  StockProfileFormalDataResponse,
  StockProfileSecondaryResponse,
  StockLearningScorecard,
  StockProfileSummaryData,
  StockProfileTodayActionResponse,
  TaskRunResponse,
  TodayActionDecision,
  TodayActionContractsData,
  TodayActionsData,
  TodayCommandBriefDetailData,
  TodaySummaryData,
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

  const response = await fetch(path, request);
  const payload = await readPayload(response);

  if (!response.ok) {
    throw new ApiError(errorMessageFromPayload(payload, response.statusText || "Request failed"), response.status, payload);
  }

  return payload as T;
}

async function fetchText(path: string): Promise<string> {
  const response = await fetch(path);
  const text = await response.text();

  if (!response.ok) {
    throw new ApiError(text || response.statusText || "Request failed", response.status, text);
  }

  return text;
}

export const api = {
  getShellStatus() {
    return fetchJson<ShellStatusResponse>("/api/shell/status");
  },
  getTodaySummary(options: { fresh?: boolean } = {}) {
    return fetchJson<TodaySummaryData>(`/api/today/summary${options.fresh ? "?fresh=1" : ""}`);
  },
  getTodayActions(options: { fresh?: boolean } = {}) {
    return fetchJson<TodayActionsData>(`/api/today/actions${options.fresh ? "?fresh=1" : ""}`);
  },
  getTodayActionContracts(options: { fresh?: boolean } = {}) {
    return fetchJson<TodayActionContractsData>(`/api/today/action-contracts${options.fresh ? "?fresh=1" : ""}`);
  },
  getTodayCommandBriefDetail(options: { fresh?: boolean } = {}) {
    return fetchJson<TodayCommandBriefDetailData>(`/api/today/command-brief-detail${options.fresh ? "?fresh=1" : ""}`);
  },
  getOverview(options: { fresh?: boolean; compact?: boolean } = {}) {
    const params = new URLSearchParams();
    if (options.fresh) {
      params.set("fresh", "1");
    }
    if (options.compact === false) {
      params.set("compact", "0");
    }
    const query = params.toString();
    return fetchJson<OverviewData>(`/api/overview${query ? `?${query}` : ""}`);
  },
  getWatchlist(options: { fresh?: boolean } = {}) {
    const params = new URLSearchParams();
    if (options.fresh) {
      params.set("fresh", "1");
    }
    const query = params.toString();
    return fetchJson<WatchlistData>(`/api/watchlist${query ? `?${query}` : ""}`);
  },
  getWatchlistManager(options: { fresh?: boolean } = {}) {
    return fetchJson<WatchlistManagerResponse>(`/api/watchlist/manage${options.fresh ? "?fresh=1" : ""}`);
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
  getOpportunities(options: { fresh?: boolean; group?: string } = {}) {
    const params = new URLSearchParams();
    if (options.fresh) {
      params.set("fresh", "1");
    }
    if (options.group) {
      params.set("group", options.group);
    }
    const query = params.toString();
    return fetchJson<OpportunitiesData>(`/api/opportunities${query ? `?${query}` : ""}`);
  },
  getOpportunitiesContext(options: { fresh?: boolean } = {}) {
    return fetchJson<OpportunitiesData>(`/api/opportunities/context${options.fresh ? "?fresh=1" : ""}`);
  },
  getOpportunitiesSourceCards(options: { fresh?: boolean } = {}) {
    return fetchJson<OpportunitiesData>(`/api/opportunities/source-cards${options.fresh ? "?fresh=1" : ""}`);
  },
  getStockProfileSummary(code: string) {
    return fetchJson<StockProfileSummaryData>(`/api/stock/${encodeURIComponent(code)}/summary`);
  },
  getStockProfileDetail(code: string) {
    return fetchJson<StockProfileDetailData>(`/api/stock/${encodeURIComponent(code)}/detail`);
  },
  getStockProfileEvidence(code: string) {
    return fetchJson<StockProfileEvidenceResponse>(`/api/stock/${encodeURIComponent(code)}/evidence`);
  },
  getStockProfileSecondary(code: string) {
    return fetchJson<StockProfileSecondaryResponse>(`/api/stock/${encodeURIComponent(code)}/secondary`);
  },
  getStockProfileFormalData(code: string) {
    return fetchJson<StockProfileFormalDataResponse>(`/api/stock/${encodeURIComponent(code)}/formal-data/full`);
  },
  getStockProfileFormalDataSection(code: string, section: string) {
    return fetchJson<StockProfileFormalDataResponse>(
      `/api/stock/${encodeURIComponent(code)}/formal-data/${encodeURIComponent(section)}`,
    );
  },
  getStockProfileTodayAction(code: string) {
    return fetchJson<StockProfileTodayActionResponse>(`/api/stock/${encodeURIComponent(code)}/today-action`);
  },
  getStockProfileLearningScorecard(code: string) {
    return fetchJson<StockLearningScorecard>(`/api/stock/${encodeURIComponent(code)}/learning-scorecard`);
  },
  getReview(params: { baseline?: string; window?: string } = {}) {
    const query = new URLSearchParams();
    if (params.baseline) {
      query.set("baseline", params.baseline);
    }
    if (params.window) {
      query.set("window", params.window);
    }
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return fetchJson<ReviewData>(`/api/review${suffix}`);
  },
  getReviewResearch(params: { baseline?: string; window?: string } = {}) {
    const query = new URLSearchParams();
    if (params.baseline) {
      query.set("baseline", params.baseline);
    }
    if (params.window) {
      query.set("window", params.window);
    }
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return fetchJson<ReviewResearchResponse>(`/api/review/research${suffix}`);
  },
  getReviewEvidence(params: { baseline?: string; window?: string } = {}) {
    const query = new URLSearchParams();
    if (params.baseline) {
      query.set("baseline", params.baseline);
    }
    if (params.window) {
      query.set("window", params.window);
    }
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return fetchJson<ReviewEvidenceResponse>(`/api/review/evidence${suffix}`);
  },
  getReviewShadowReplay() {
    return fetchJson<ShadowReplayReviewSummary>("/api/review/shadow-replay");
  },
  ask(query: string) {
    const q = query ? `?q=${encodeURIComponent(query)}` : "";
    return fetchJson<AskResponse>(`/api/ask${q}`);
  },
  askSuggest(query: string, init?: RequestInit) {
    const q = query ? `?q=${encodeURIComponent(query)}` : "";
    return fetchJson<AskSuggestResponse>(`/api/ask/suggest${q}`, init);
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
      decision: TodayActionDecision;
      counts: TodayActionsData["action_queue"]["counts"];
      ledger?: Record<string, unknown>;
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
  getRuns(options: { fresh?: boolean } = {}) {
    const params = new URLSearchParams();
    if (options.fresh) {
      params.set("fresh", "1");
    }
    const query = params.toString();
    return fetchJson<{ runs: RunItem[]; compact: boolean }>(`/api/runs${query ? `?${query}` : ""}`);
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
  getRefreshStatus(page: string, options: { auto?: boolean; compact?: boolean } = {}) {
    const auto = options.auto ? "&auto=1" : "";
    const compact = options.compact ? "&compact=1" : "";
    return fetchJson<RefreshStatus>(`/api/refresh/status?page=${encodeURIComponent(page)}${auto}${compact}`);
  },
  getFormalDataStatus(options: { fresh?: boolean; compact?: boolean } = {}) {
    const params = new URLSearchParams();
    if (options.fresh) {
      params.set("fresh", "1");
    }
    if (options.compact === false) {
      params.set("compact", "0");
    }
    const query = params.toString();
    return fetchJson<FormalDataStatus>(`/api/formal-data/status${query ? `?${query}` : ""}`);
  },
  getDataAssetsStatus(options: { fresh?: boolean; compact?: boolean } = {}) {
    const params = new URLSearchParams();
    if (options.fresh) {
      params.set("fresh", "1");
    }
    if (options.compact === false) {
      params.set("compact", "0");
    }
    const query = params.toString();
    return fetchJson<DataAssetsStatus>(`/api/data-assets/status${query ? `?${query}` : ""}`);
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
  getPortfolioAccount(options: { fresh?: boolean; compact?: boolean; history?: boolean } = {}) {
    const query = new URLSearchParams();
    if (options.fresh) {
      query.set("fresh", "1");
    }
    if (options.compact === false) {
      query.set("compact", "0");
    }
    if (options.history) {
      query.set("history", "1");
    }
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return fetchJson<PortfolioAccountResponse>(`/api/portfolio/account${suffix}`);
  },
  getPortfolioHoldingReviews(options: { fresh?: boolean } = {}) {
    return fetchJson<PortfolioHoldingReviewsResponse>(
      `/api/portfolio/holding-reviews${options.fresh ? "?fresh=1" : ""}`,
    );
  },
  refreshPortfolioQuotes() {
    return fetchJson<PortfolioAccountResponse>("/api/portfolio/quotes/refresh", {
      method: "POST",
    });
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
  amendPortfolioHoldingIdentity(payload: {
    from_code: string;
    to_code: string;
    name?: string;
    reason: string;
  }) {
    return fetchJson<PortfolioAccountResponse>("/api/portfolio/holding/identity", {
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
  getDecisionLedgerRecent(params: { limit?: number; codes?: string[]; latestPerCode?: boolean } = {}) {
    const query = new URLSearchParams();
    if (params.limit !== undefined) {
      query.set("limit", String(params.limit));
    }
    const codes = (params.codes || []).map((code) => String(code || "").trim()).filter(Boolean);
    if (codes.length) {
      query.set("codes", codes.join(","));
    }
    if (params.latestPerCode) {
      query.set("latest_per_code", "1");
    }
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return fetchJson<DecisionLedgerRecentResponse>(`/api/decision-ledger/recent${suffix}`);
  },
  getDecisionLedgerCalibration(params: { window?: string; as_of?: string; limit?: number } = {}) {
    const query = new URLSearchParams();
    if (params.window) {
      query.set("window", params.window);
    }
    if (params.as_of) {
      query.set("as_of", params.as_of);
    }
    if (params.limit !== undefined) {
      query.set("limit", String(params.limit));
    }
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return fetchJson<DecisionLedgerCalibrationResponse>(`/api/decision-ledger/calibration${suffix}`);
  },
  getDecisionLedgerCalibrationDetail(params: { window?: string; as_of?: string; limit?: number } = {}) {
    const query = new URLSearchParams();
    if (params.window) {
      query.set("window", params.window);
    }
    if (params.as_of) {
      query.set("as_of", params.as_of);
    }
    if (params.limit !== undefined) {
      query.set("limit", String(params.limit));
    }
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return fetchJson<DecisionLedgerCalibrationDetailResponse>(
      `/api/decision-ledger/calibration-detail${suffix}`,
    );
  },
  getDecisionLedgerLearningLoop(params: { as_of?: string } = {}) {
    const query = new URLSearchParams();
    if (params.as_of) {
      query.set("as_of", params.as_of);
    }
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return fetchJson<DecisionLedgerLearningLoopResponse>(`/api/decision-ledger/learning-loop${suffix}`);
  },
  getDecisionLedgerShadowCalibration() {
    return fetchJson<ShadowCalibrationSummary>("/api/decision-ledger/shadow-calibration");
  },
  getDecisionLedgerReviewCase(decisionId: string) {
    return fetchJson<DecisionLedgerReviewCaseWorkbench>(
      `/api/decision-ledger/review-case/${encodeURIComponent(decisionId)}`,
    );
  },
  generateDecisionLedgerAttributionDraft(decisionId: string) {
    return fetchJson<DecisionLedgerAttributionDraftResponse>(
      `/api/decision-ledger/review-case/${encodeURIComponent(decisionId)}/attribution-draft`,
      {
        method: "POST",
      },
    );
  },
  autoReviewDecisionLedgerCase(decisionId: string) {
    return fetchJson<DecisionLedgerAutoReviewResponse>(
      `/api/decision-ledger/review-case/${encodeURIComponent(decisionId)}/auto-review`,
      {
        method: "POST",
      },
    );
  },
  saveDecisionLedgerReviewCase(decisionId: string, payload: DecisionLedgerReviewCaseSavePayload) {
    return fetchJson<DecisionLedgerReviewCaseSaveResponse>(
      `/api/decision-ledger/review-case/${encodeURIComponent(decisionId)}`,
      {
        method: "POST",
        json: payload as unknown as Record<string, unknown>,
      },
    );
  },
  getDecisionLedgerStock(code: string) {
    return fetchJson<DecisionLedgerStockResponse>(
      `/api/decision-ledger/stock/${encodeURIComponent(code)}`,
    );
  },
  getDecisionLedgerHealth() {
    return fetchJson<DecisionLedgerHealthResponse>("/api/decision-ledger/health");
  },
};
