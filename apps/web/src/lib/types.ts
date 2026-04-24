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
  label: string;
  value: string;
  detail?: string;
  available?: boolean;
  stale?: boolean;
  age_label?: string;
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

export interface OverviewData {
  generated_at: string;
  workspace_root: string;
  kpis?: MetricCardData[];
  lanes?: unknown[];
  tasks?: unknown[];
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
  canonical_decision?: Record<string, string | number | null | undefined>;
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
  triggers?: Array<{ label?: string; value?: string; detail?: string }>;
  source_cards?: SourceCardData[];
  artifacts?: BasicCard[];
  links?: LinkMap;
}

export interface StockProfileData {
  code: string;
  watchlist?: StockDetailData;
  opportunity?: StockDetailData;
}

export interface RunItem {
  run_id?: string;
  task_name?: string;
  title?: string;
  status?: string;
  started_at?: string;
  finished_at?: string;
  summary?: string;
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

export interface HealthResponse {
  ok: boolean;
  workspace?: string;
}
