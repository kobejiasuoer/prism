export type Tone =
  | "buy"
  | "sell"
  | "watch"
  | "hold"
  | "avoid"
  | "positive"
  | "negative"
  | "warning"
  | "info"
  | "good"
  | "risk"
  | "stale";

export type DecisionValue = "pending" | "done" | "watch" | "skip";

export interface LinkMap {
  today?: string;
  watchlist?: string;
  opportunities?: string;
  review?: string;
  settings?: string;
  [key: string]: string | undefined;
}

export interface MetricCardData {
  label: string;
  value: string | number;
  detail?: string;
  note?: string;
  tone?: Tone | string;
}

export interface SourceCardData {
  key?: string;
  label: string;
  value: string;
  detail?: string;
  available?: boolean;
  stale?: boolean;
  age_label?: string;
  age_seconds?: number;
  stale_after_seconds?: number;
}

export interface BasicCard {
  label?: string;
  title?: string;
  subtitle?: string;
  value?: string | number;
  detail?: string;
  copy?: string;
  status?: string;
  action?: string;
  trigger?: string;
  reason?: string;
  risk?: string;
  freshness?: string;
  foot?: string;
  note?: string;
  tone?: Tone | string;
  metrics?: string[];
  detail_url?: string;
  detail_link_text?: string;
  url?: string;
  path?: string;
}

export interface StockListCard {
  code: string;
  name: string;
  action?: string;
  status?: string;
  position?: string;
  tone?: Tone | string;
  reason?: string;
  detail?: string;
  foot?: string;
  risk?: string;
  setup_label?: string;
  score?: string | number;
  change_pct?: string | number;
  amount_yi?: string | number;
  theme?: string;
  signal?: string;
  support?: string | number;
  resistance?: string | number;
  stop_loss?: string | number;
  snapshot_time?: string;
  updated_at?: string;
  status_line?: string;
  detail_url?: string;
}

export interface CardGroup<T = StockListCard> {
  key?: string;
  title: string;
  subtitle?: string;
  count?: number;
  cards?: T[];
  empty?: string;
  footer_link?: {
    title: string;
    url: string;
  } | null;
}

export interface TodayHero {
  title: string;
  summary: string;
  gate_label?: string;
  position_cap?: string;
  main_theme?: string;
  context_note?: string;
}

export interface TodayCommandHeroAction {
  label: string;
  title: string;
  detail: string;
  tone: Tone | string;
  tier: string;
  url?: string;
}

export interface TodayCommandHero {
  eyebrow: string;
  title: string;
  summary: string;
  trade_date: string;
  context_note?: string;
  source_state?: string;
  actions?: TodayCommandHeroAction[];
}

export interface TodayActionDecision {
  value: DecisionValue;
  label: string;
  tone: Tone | string;
  updated_at?: string;
  updated_at_raw?: string;
}

export interface TodayActionContext {
  value?: string;
  label?: string;
  status?: string;
  tone?: Tone | string;
  note?: string;
}

export interface TodayActionItem {
  key: string;
  title: string;
  source: string;
  status: string;
  tone: Tone | string;
  detail: string;
  foot?: string;
  metrics?: string[];
  url?: string;
  group_key?: string;
  group_title?: string;
  group_index?: number;
  decision: TodayActionDecision;
  freshness?: TodayActionContext;
  confidence?: TodayActionContext;
}

export interface TodayActionQueue {
  title: string;
  subtitle?: string;
  note?: string;
  items: TodayActionItem[];
  hidden_count?: number;
  counts: {
    total: number;
    pending: number;
    done: number;
    watch: number;
    skip: number;
    last_updated?: string;
  };
}

export interface RiskRow {
  title: string;
  action?: string;
  trigger?: string;
  reason?: string;
  risk?: string;
  freshness?: string;
  url?: string;
  tone?: Tone | string;
}

export interface CanonicalDecision {
  stock_id: string;
  stock_name: string;
  trade_date: string;
  source_scope: "holdings" | "opportunity" | "live_fallback" | string;
  main_conclusion: string;
  action_tier: string;
  position_guidance: string;
  risk_boundary: string;
  why_now: string;
  continue_condition: string;
  stop_condition: string;
  next_step: string;
  trigger_condition: string;
  avoid_action: string;
  evidence_entry: string;
  confidence_note: string;
  updated_at: string;
  [key: string]: string | number | null | undefined;
}

export interface StockTrigger {
  label?: string;
  name?: string;
  value?: string;
  condition?: string;
  detail?: string;
  action?: string;
}

export interface TodayCounts {
  watchlist_priority: number;
  watchlist_total: number;
  candidate_total: number;
  confirmed: number;
  downgraded: number;
  fresh_candidates: number;
}

export interface TodayData {
  generated_at: string;
  trade_date: string;
  brief_is_live: boolean;
  hero: TodayHero;
  command_hero?: TodayCommandHero;
  radar_cards?: MetricCardData[];
  action_queue: TodayActionQueue;
  risk_rows?: RiskRow[];
  source_cards: SourceCardData[];
  summary_cards: MetricCardData[];
  links: LinkMap;
  counts: TodayCounts;
}

export interface AskSuggestion {
  code: string;
  name: string;
  tag?: string;
  detail?: string;
  url?: string;
  fill_value?: string;
}

export interface AskSuggestResponse {
  query: string;
  items: AskSuggestion[];
  message?: string;
  recent_queries?: AskSuggestion[];
}

export interface AskCaseData {
  code?: string;
  name?: string;
  trade_date?: string;
  tone?: Tone | string;
  hero?: {
    title?: string;
    summary?: string;
    status_label?: string;
    decision_label?: string;
    position?: string;
    confidence_label?: string;
    confidence_note?: string;
  };
  canonical_decision?: CanonicalDecision;
  decision_cards?: MetricCardData[];
  metric_cards?: MetricCardData[];
  level_cards?: MetricCardData[];
  cross_cards?: MetricCardData[];
  context_tags?: string[];
  evidence_cards?: BasicCard[];
  evidence_layer?: {
    followup?: AskFollowupShell | null;
    [key: string]: unknown;
  };
  execution_loop?: BasicCard[];
  triggers?: StockTrigger[];
  artifacts?: BasicCard[];
  source_cards?: SourceCardData[];
}

export interface AskResponse {
  generated_at?: string;
  query?: string;
  examples?: AskSuggestion[];
  recent_queries?: AskSuggestion[];
  case?: AskCaseData;
  followup?: AskFollowupShell | null;
  message?: string;
}

export interface AskFollowupPreset {
  label?: string;
  question: string;
}

export interface AskFollowupShell {
  api?: string;
  query?: string;
  presets?: AskFollowupPreset[];
  starter?: {
    title?: string;
    summary?: string;
  };
  engine_badge?: {
    label?: string;
    detail?: string;
    tone?: Tone | string;
  };
  hint?: string;
}

export interface AskFollowupAnswer {
  intent?: string;
  title?: string;
  summary?: string;
  bullets?: string[];
  references?: string[];
  tone?: Tone | string;
  followups?: string[];
  engine?: string;
  engine_label?: string;
  engine_note?: string;
  history_used?: number;
}

export interface AskFollowupResponse {
  query: string;
  question: string;
  code?: string;
  name?: string;
  hero_title?: string;
  history_used?: number;
  answer: AskFollowupAnswer;
}

export interface OverviewData {
  generated_at: string;
  workspace_root: string;
  kpis?: MetricCardData[];
  lanes?: unknown[];
  tasks?: TaskDefinition[];
  runs?: RunItem[];
  freshness?: SourceCardData[];
}

export interface WatchlistData {
  generated_at: string;
  trade_date: string;
  brief_is_live?: boolean;
  hero?: {
    title?: string;
    summary?: string;
    context_note?: string;
    snapshot_time?: string;
    stock_count?: number;
    priority_count?: number;
  };
  topline?: {
    verdict_badge?: string;
    verdict_title?: string;
    verdict_summary?: string;
    meta_pills?: Array<{ label: string; value: string }>;
  };
  summary_cards?: MetricCardData[];
  groups?: Array<CardGroup<StockListCard>>;
  source_cards?: SourceCardData[];
  focus_tags?: string[];
  avoid_points?: string[];
  links?: LinkMap;
  manager?: WatchlistManager;
}

export interface WatchlistManagerItem {
  code: string;
  name: string;
  market?: string;
  state_label?: string;
  state_detail?: string;
  tone?: Tone | string;
  updated_at?: string;
}

export interface WatchlistRefreshStep {
  label?: string;
  state?: string;
  detail?: string;
}

export interface WatchlistManager {
  summary?: string;
  feedback_hint?: string;
  active_count?: number;
  archived_count?: number;
  pending_count?: number;
  summary_cards?: MetricCardData[];
  refresh_status?: {
    status?: string;
    label?: string;
    value?: string;
    detail?: string;
    tone?: Tone | string;
    log_path?: string;
    log_url?: string;
    steps?: WatchlistRefreshStep[];
  };
  active_items?: WatchlistManagerItem[];
  archived_items?: WatchlistManagerItem[];
  empty_active?: string;
  empty_archived?: string;
  add_api?: string;
  archive_api?: string;
  restore_api?: string;
}

export interface WatchlistManagerResponse {
  manager: WatchlistManager;
}

export interface WatchlistManageResponse {
  ok: boolean;
  action: "add" | "archive" | "restore";
  message: string;
  operation?: Record<string, unknown>;
  refresh?: {
    started?: boolean;
    run_id?: string;
    task_name?: string;
    title?: string;
    log_path?: string;
  };
  manager: WatchlistManager;
}

export interface OpportunitiesData {
  generated_at: string;
  trade_date: string;
  brief_is_live?: boolean;
  hero?: {
    title?: string;
    summary?: string;
    context_note?: string;
    status_label?: string;
  };
  topline?: {
    verdict_badge?: string;
    verdict_title?: string;
    verdict_summary?: string;
    meta_pills?: Array<{ label: string; value: string }>;
  };
  summary_cards?: MetricCardData[];
  groups?: Array<CardGroup<StockListCard>>;
  secondary_groups?: Array<CardGroup<StockListCard>>;
  top_rows?: RiskRow[];
  theme_cards?: BasicCard[];
  status_strip?: BasicCard[];
  source_cards?: SourceCardData[];
  quality_cards?: BasicCard[];
  focus_tags?: string[];
  avoid_points?: string[];
  links?: LinkMap;
}

export interface ReviewData {
  generated_at: string;
  trade_date?: string;
  hero?: {
    title?: string;
    summary?: string;
    context_note?: string;
  };
  topline?: {
    verdict_badge?: string;
    verdict_title?: string;
    verdict_summary?: string;
    meta_pills?: Array<{ label: string; value: string }>;
  };
  summary_cards?: MetricCardData[];
  verdict_cards?: BasicCard[];
  action_rules?: RiskRow[];
  comparison_cards?: MetricCardData[];
  lifecycle_cards?: MetricCardData[];
  source_cards?: SourceCardData[];
  verdict_note?: string;
  comparison_note?: string;
  lifecycle_note?: string;
  links?: LinkMap;
}

export interface StockDetailData {
  generated_at: string;
  trade_date?: string;
  code: string;
  name?: string;
  tone?: Tone | string;
  hero?: {
    title?: string;
    summary?: string;
    status_label?: string;
    setup_label?: string;
    position?: string;
  };
  canonical_decision?: CanonicalDecision;
  topline?: {
    verdict_badge?: string;
    verdict_title?: string;
    verdict_summary?: string;
    meta_pills?: Array<{ label: string; value: string }>;
  };
  decision_cards?: MetricCardData[];
  metric_cards?: MetricCardData[];
  meta_cards?: MetricCardData[];
  level_cards?: MetricCardData[];
  capital_cards?: MetricCardData[];
  execution_loop?: BasicCard[];
  plan_rows?: Array<{ label: string; value: string }>;
  plan_levels?: Array<{ label: string; value: string }>;
  insight_groups?: Array<{ title: string; items?: string[]; empty?: string }>;
  triggers?: StockTrigger[];
  source_cards?: SourceCardData[];
  artifacts?: BasicCard[];
  links?: LinkMap;
}

export interface StockProfileData {
  generated_at?: string;
  code: string;
  trade_date?: string;
  primary_source?: "watchlist" | "opportunity" | null;
  primary_source_label?: string;
  primary_detail?: StockDetailData;
  available_sources?: Array<"watchlist" | "opportunity">;
  watchlist?: StockDetailData;
  opportunity?: StockDetailData;
  errors?: Partial<Record<"watchlist" | "opportunity", string>>;
  links?: LinkMap;
}

export interface RunItem {
  run_id?: string;
  task_id?: string;
  task_name?: string;
  title?: string;
  status?: string;
  started_at?: string;
  finished_at?: string;
  log_path?: string;
  meta_path?: string;
  summary?: string;
  send_to_feishu?: boolean;
}

export interface TaskDefinition {
  task_name?: string;
  name?: string;
  title?: string;
  description?: string;
  lane?: string;
  command?: string[];
  last_run?: RunItem;
}

export interface RefreshStatus {
  page: string;
  server_time: string;
  market_mode: string;
  market_label: string;
  suggested_poll_seconds: number;
  freshness: SourceCardData[];
  stale_count: number;
  running: RunItem[];
  recommended_task: {
    task_name: string;
    title: string;
  };
  cooldown: {
    seconds: number;
    remaining_seconds: number;
    ready: boolean;
    last_trigger_at?: string;
    last_task_name?: string;
    last_run_id?: string;
  };
  snapshot_signature: string;
}

export interface RefreshTriggerResponse {
  ok: boolean;
  page: string;
  force: boolean;
  task: {
    task_name: string;
    title: string;
  };
  trigger: {
    started?: boolean;
    run_id?: string;
    task_name?: string;
    title?: string;
    log_path?: string;
    meta_path?: string;
  };
  status: RefreshStatus;
}

export interface PreviewPayload {
  path: string;
  name: string;
  kind: "markdown" | "json" | "binary" | "text" | string;
  size_bytes: number;
  mtime: string;
  truncated: boolean;
  text: string;
  preview_bytes?: number;
}

export interface ParameterGroupStatus {
  key: string;
  label: string;
  required?: boolean;
  ok: boolean;
  detail?: string;
}

export interface ParametersResponse {
  ok: boolean;
  saved?: boolean;
  path: string;
  updated_at?: string;
  summary_cards?: MetricCardData[];
  required_groups?: ParameterGroupStatus[];
  validation?: {
    ok: boolean;
    errors?: string[];
  };
  value: Record<string, unknown>;
  raw: string;
  detail?: string;
}

export interface TaskRunResponse {
  ok: boolean;
  started?: boolean;
  run_id?: string;
  task_name?: string;
  title?: string;
  send_to_feishu?: boolean;
  meta_path?: string;
  log_path?: string;
}

export interface HealthResponse {
  ok: boolean;
  workspace?: string;
}
