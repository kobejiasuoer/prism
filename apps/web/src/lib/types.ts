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
export type TodayActionDisplayValue = DecisionValue | "no_fill";

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
  detail_url?: string;
  detail_link_text?: string;
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
  trade_date?: string | null;
  stale_reasons?: string[];
  source_lane?: string;
  decision_scope?: string;
  authority_provider?: string;
  target_authority_provider?: string;
  audit_providers?: string[];
  source_authority_ready?: boolean;
  formal_decision_allowed?: boolean;
  authority_flags?: string[];
}

export type ReadinessMode = "live_ready" | "shadow_only" | "blocked";

export interface ReadinessSession {
  key: string;
  label: string;
  is_trading_day: boolean;
  calendar_status?: "trading" | "weekend" | "holiday" | "unknown" | string;
}

export interface ReadinessIssue {
  code: string;
  label: string;
  message: string;
  recommended_task?: string;
}

export interface ReadinessSourceFreshness {
  dataset?: string;
  key: string;
  label: string;
  value: string;
  detail?: string;
  trade_date?: string | null;
  available: boolean;
  age_seconds: number | null;
  age_label: string;
  stale: boolean;
  stale_after_seconds: number;
  stale_reasons: string[];
  provider?: string;
  provider_role?: string;
  freshness_status?: string;
  fallback_used?: boolean;
  live_small_allowed?: boolean;
  manifest_path?: string;
  source_lane?: string;
  decision_scope?: string;
  authority_provider?: string;
  target_authority_provider?: string;
  audit_providers?: string[];
  source_authority_ready?: boolean;
  formal_decision_allowed?: boolean;
  authority_flags?: string[];
  dataset_manifest?: boolean;
}

export type FreshnessState =
  | "FRESH"
  | "USABLE"
  | "STALE"
  | "DEGRADED"
  | "INVALID"
  | "BLOCKED";

export type CapabilityKey =
  | "observe"
  | "review"
  | "approve"
  | "trade"
  | "notify"
  | "ledger_capture";

export interface CapabilityReason {
  code: string;
  label?: string;
  message?: string;
  source?: string;
}

export interface CapabilityNextAction {
  task?: string;
  label?: string;
  detail?: string;
}

export interface CapabilityReport {
  capability: CapabilityKey | string;
  status: "ok" | "degraded" | "blocked" | string;
  granted: boolean;
  why_not: CapabilityReason[];
  degraded_path: CapabilityReason[];
  next_actions: CapabilityNextAction[];
  blocking_sources: string[];
  last_checked_at: string;
}

export type TrustLevelValue = "trusted" | "observe_only" | "unreliable";

export interface TrustLevel {
  level: TrustLevelValue | string;
  label: string;
  tone: Tone | string;
  headline: string;
  can_observe: boolean;
  can_review: boolean;
  can_approve: boolean;
  can_trade_live: boolean;
  blocking_reasons: string[];
  notice_reasons?: string[];
  next_step: string | null;
  next_step_label: string | null;
  last_checked_at: string;
}

export interface ReadinessQualityFreshness {
  key: string;
  title: string;
  validation_status: string;
  checked_at: string;
  expected_timestamp: string;
  checked_trade_date: string | null;
  expected_trade_date: string;
  age_seconds: number | null;
  age_label: string;
  timely: boolean;
  stale_reasons: string[];
}

export interface ReadinessPayload {
  expected_trade_date: string;
  data_trade_date: string | null;
  display_date: string;
  checked_at: string;
  session: ReadinessSession;
  readiness_mode: ReadinessMode;
  ready: boolean;
  brief_is_live: boolean;
  stale_count: number;
  blockers: ReadinessIssue[];
  warnings: ReadinessIssue[];
  formal_ready?: boolean;
  formal_base_ready?: boolean;
  pipeline_formal_ready?: boolean;
  formal_blockers?: ReadinessIssue[];
  formal_base_blockers?: ReadinessIssue[];
  pipeline_formal_blockers?: ReadinessIssue[];
  source_freshness: ReadinessSourceFreshness[];
  quality_freshness: ReadinessQualityFreshness[];
  recommended_tasks: string[];
  account_state?: AccountReadinessState;
  calendar_horizon?: string;
  source_states?: Record<string, FreshnessState | string>;
  dataset_freshness?: ReadinessSourceFreshness[];
  dataset_states?: Record<string, FreshnessState | string>;
  formal_freshness?: ReadinessSourceFreshness[];
  formal_data_status?: FormalDataStatus;
  capabilities?: Partial<Record<CapabilityKey, CapabilityReport>> & Record<string, CapabilityReport>;
  trust_level?: TrustLevel;
}

export type AccountMode = "research" | "shadow" | "live_small";

export interface AccountReadinessState {
  mode: AccountMode | string;
  mode_label: string;
  mode_tone: string;
  mode_updated_at?: string;
  cash_balance: number;
  equity_at_cost: number;
  positions_count: number;
  fills_count: number;
  reconciliation: {
    count: number;
    age_seconds: number | null;
    age_label?: string;
    fresh_within_seconds?: number;
    fresh: boolean;
    last: Record<string, unknown> | null;
  };
  unreconciled_intents: Array<{
    trade_date: string;
    intent_key: string;
    decision_updated_at: string;
  }>;
  blockers: ReadinessIssue[];
  warnings: ReadinessIssue[];
  recommended_tasks: string[];
  ready_for_live_small: boolean;
}

export interface AccountPosition {
  code: string;
  name: string;
  qty: number;
  avg_cost: number;
  cost_basis: number;
  realized_pnl: number;
  current_price?: number | null;
  market_value?: number | null;
  unrealized_pnl?: number | null;
  unrealized_pnl_pct?: number | null;
  total_pnl?: number | null;
  quote_change_pct?: number | null;
  quote_timestamp?: string;
  quote_trade_date?: string;
  quote_provider?: string;
  last_fill_at: string;
  fills: number;
}

export type HoldingReviewAction =
  | "hold"
  | "clear_exit"
  | "defense_reduce"
  | "profit_take"
  | "time_exit"
  | "loss_warning"
  | "refresh_quote"
  | "review_sell"
  | "reduce_watch"
  | "missing_plan"
  | "missing_analysis"
  | "evidence_blocked";

export interface HoldingReviewDecisionSummary {
  decision_id?: string | null;
  trade_date?: string | null;
  code?: string | null;
  name?: string | null;
  action?: string | null;
  action_label?: string | null;
  lane?: string | null;
  surface?: string | null;
  status?: string | null;
  main_conclusion?: string | null;
  latest_execution?: {
    status?: string | null;
    trade_date?: string | null;
    side?: string | null;
    price?: number | string | null;
    quantity?: number | string | null;
    amount?: number | string | null;
    note?: string | null;
  } | null;
  latest_outcome?: {
    window?: string | null;
    as_of_trade_date?: string | null;
    label?: string | null;
    tone?: Tone | string | null;
    return_pct?: number | string | null;
    relative_return_pct?: number | string | null;
  } | null;
}

export interface HoldingEvidencePack {
  stock?: {
    code?: string | null;
    name?: string | null;
    profile?: string | null;
  };
  position?: {
    qty?: number | null;
    position_pct?: number | null;
    avg_cost?: number | null;
    current_price?: number | null;
    pnl_pct?: number | null;
    pnl_amount?: number | null;
    days_held?: number | null;
    entry_date?: string | null;
    last_action?: string | null;
    last_action_price?: number | null;
  };
  script?: {
    base_action?: string | null;
    base_action_label?: string | null;
    defense_line?: number | null;
    clear_line?: number | null;
    repair_line?: number | null;
    profit_line?: number | null;
    warning_line?: number | null;
    time_fail_line?: number | null;
    suggested_sell_qty?: number | null;
    suggested_sell_pct?: number | null;
    rule_floor_action?: string | null;
  };
  price_action?: {
    change_pct_today?: number | null;
    range_position_20d?: string | null;
    ma5_relation?: string | null;
    ma10_relation?: string | null;
    ma20_relation?: string | null;
    drawdown_from_repair_pct?: number | null;
    break_levels?: string[];
    volatility_profile?: string | null;
  };
  flow?: {
    flow_direction?: string | null;
    flow_persistence_days?: number | null;
    main_signal?: string | null;
    score?: number | string | null;
  };
  market_context?: {
    market_regime?: string | null;
    attack_gate?: string | null;
    hs300_change_pct?: number | null;
    zz500_change_pct?: number | null;
    cyb_change_pct?: number | null;
    market_score?: number | null;
    session?: string | null;
  };
  events?: {
    event_risk?: string | null;
    event_boost?: string | null;
    risk_summary?: string | null;
    positive_flags?: string[];
    risk_flags?: string[];
  };
  prism_history?: Array<{
    date?: string | null;
    action?: string | null;
    action_label?: string | null;
    conclusion?: string | null;
    outcome_label?: string | null;
    outcome_return_pct?: number | null;
  }>;
  evidence?: {
    price?: string[];
    flow?: string[];
    technical?: string[];
    event?: string[];
    risk_flags?: string[];
    positive_flags?: string[];
  };
  constraints?: {
    rule_floor_action?: string | null;
    can_relax_below_rule?: boolean;
    can_suggest_tighten?: boolean;
    manual_execution_only?: boolean;
    max_sell_qty?: number | null;
    recommended_sell_qty?: number | null;
  };
}

export interface HoldingAiReview {
  scene?: string;
  scene_label?: string;
  confidence?: number | null;
  evidence_strength?: "low" | "medium" | "high" | string | null;
  verdict?: "keep" | "tighten" | "loosen" | string | null;
  verdict_label?: string | null;
  action_rewrite?: string | null;
  supporting_evidence?: string[];
  opposing_evidence?: string[];
  script_adjustment?: {
    adjustment?: "keep" | "tighten" | "loosen" | string | null;
    adjustment_label?: string | null;
    defense_line?: string | null;
    clear_line?: string | null;
    time_window?: string | null;
    reason?: string | null;
  } | null;
  next_watch?: string | null;
  risk_summary?: string | null;
  evidence_used?: string[];
  counter_evidence_label?: string | null;
  human_note?: string | null;
  provider?: string | null;
  model?: string | null;
  fallback_reason?: string | null;
  generated_at?: string | null;
  base_action?: string | null;
}

export interface HoldingReview {
  code: string;
  name: string;
  qty: number;
  avg_cost: number;
  cost_basis: number;
  current_price?: number | null;
  market_value?: number | null;
  unrealized_pnl?: number | null;
  unrealized_pnl_pct?: number | null;
  quote_trade_date?: string;
  quote_timestamp?: string;
  last_fill_at?: string;
  today_action: HoldingReviewAction | string;
  action_label: string;
  action_tone: Tone | string;
  action_instruction: string;
  must_review: boolean;
  missing_plan: boolean;
  missing_analysis: boolean;
  decision_is_today: boolean;
  stop_condition: string;
  reduce_condition: string;
  continue_condition: string;
  position_plan?: {
    plan_id?: string;
    status?: string;
    source?: string;
    created_at?: string;
    updated_at?: string;
    code?: string;
    name?: string;
    entry_trade_date?: string;
    entry_price?: number;
    entry_qty?: number;
    current_qty?: number;
    avg_cost_basis?: number;
    rules?: Record<string, number | string>;
    levels?: Record<string, number | string>;
    logic?: {
      entry_reason?: string;
      risk_model?: string;
      [key: string]: unknown;
    };
    [key: string]: unknown;
  };
  holding_decision?: {
    category: string;
    suggested_action: string;
    trigger_rule: string;
    execution_rule: string;
    upgrade_rule: string;
    revoke_rule: string;
    review_tag: string;
    target_sell_qty?: number | null;
    target_sell_pct?: number | null;
    days_held?: number | null;
    price?: number | null;
    avg_cost?: number | null;
    pnl_pct?: number | null;
    trigger_facts?: string[];
    script?: {
      profile_key?: string | null;
      profile_label?: string | null;
      profile_detail?: string | null;
      basis?: string[];
      rule_summary?: string | null;
    };
    evidence?: {
      action?: string | null;
      tech_base?: string | null;
      flow_base?: string | null;
      event_base?: string | null;
      signal?: string | null;
      score?: number | string | null;
      hard_flags?: string[];
      positives?: string[];
      watch_points?: string[];
      support?: number | string | null;
      resistance?: number | string | null;
      stop_loss?: number | string | null;
      [key: string]: unknown;
    };
    levels?: Record<string, number | string>;
    rules?: Record<string, number | string>;
  };
  latest_decision?: HoldingReviewDecisionSummary | null;
  latest_execution?: HoldingReviewDecisionSummary["latest_execution"];
  latest_outcome?: HoldingReviewDecisionSummary["latest_outcome"];
  holding_evidence_pack?: HoldingEvidencePack;
  holding_ai_review?: HoldingAiReview;
  review_reason: string;
}

export interface HoldingActionSummary {
  total: number;
  must_review: number;
  clear_exit?: number;
  defense_reduce?: number;
  profit_take?: number;
  time_exit?: number;
  loss_warning?: number;
  refresh_quote?: number;
  review_sell: number;
  reduce_watch: number;
  evidence_blocked: number;
  missing_plan: number;
  missing_analysis: number;
  hold: number;
  generated_at: string;
  expected_trade_date: string;
  errors?: Array<{ message?: string; [key: string]: unknown }>;
  title?: string;
  tone?: Tone | string;
}

export interface AccountFill {
  fill_id: string;
  ts: string;
  trade_date: string;
  code: string;
  name: string;
  side: "buy" | "sell";
  qty: number;
  price: number;
  fees: number;
  notional: number;
  cash_delta: number;
  balance_after: number;
  broker_ref: string | null;
  intent_key: string | null;
  note: string;
}

export interface AccountReconciliation {
  ts: string;
  trade_date: string;
  broker_cash: number;
  broker_equity: number;
  local_cash: number;
  local_equity_at_cost: number;
  delta_cash: number;
  delta_equity: number;
  note: string;
}

export interface AccountIdentityCorrection {
  ts: string;
  from_code: string;
  to_code: string;
  name: string;
  reason: string;
  affected_fills: number;
  affected_plans: number;
  fill_ids?: string[];
}

export interface AccountView {
  mode: AccountMode | string;
  mode_label: string;
  mode_tone: string;
  mode_updated_at: string;
  unsafe_bypass_active?: boolean;
  unsafe_bypass_note?: string;
  unsafe_bypass_at?: string;
  currency: string;
  starting_cash: number;
  cash_balance: number;
  deposits_total: number;
  equity_at_cost: number;
  book_value: number;
  realized_pnl: number;
  market_value?: number | null;
  unrealized_pnl?: number | null;
  total_pnl?: number | null;
  open_positions: AccountPosition[];
  closed_positions: AccountPosition[];
  fills: AccountFill[];
  fills_count: number;
  last_fill_at: string;
  reconciliations: AccountReconciliation[];
  no_fill_intents: Array<{ ts: string; trade_date: string; intent_key: string; reason: string }>;
  position_plans?: Array<HoldingReview["position_plan"]>;
  identity_corrections?: AccountIdentityCorrection[];
  mode_history?: Array<{
    ts?: string;
    from_mode?: string;
    to_mode?: string;
    starting_cash?: number;
    allow_unsafe?: boolean;
    note?: string;
  }>;
  available_modes: AccountMode[];
  updated_at: string;
}

export interface PortfolioAccountResponse {
  generated_at: string;
  trade_date: string;
  expected_trade_date: string;
  data_trade_date: string | null;
  readiness: ReadinessPayload;
  account: AccountView;
  market_quotes?: {
    enabled: boolean;
    status: string;
    message?: string;
    requested_codes?: string[];
    updated_at?: string;
    trade_date?: string;
    provider?: string;
    freshness_status?: string;
    live_small_allowed?: boolean;
    row_count?: number;
    priced_count?: number;
    missing_codes?: string[];
    data_path?: string;
    manifest_path?: string;
    errors?: string[];
  };
  holding_reviews?: HoldingReview[];
  holding_action_summary?: HoldingActionSummary;
  summary_cards: MetricCardData[];
  recent_fills: AccountFill[];
  unreconciled_intents: AccountReadinessState["unreconciled_intents"];
  reconciliation: AccountReadinessState["reconciliation"];
  ready_for_live_small: boolean;
  links: LinkMap;
}

export interface QualityCardData {
  key?: string;
  title: string;
  status: string;
  tone?: Tone | string;
  checked_at?: string;
  expected_timestamp?: string;
  issue?: string;
  path?: string;
  url?: string;
  timely?: boolean;
  stale_reasons?: string[];
  age_label?: string;
}

export interface BasicCard {
  key?: string;
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
  name?: string;
  mtime?: string;
  mtime_full?: string;
  artifact_path?: string;
  artifact_url?: string;
  score?: string | number;
  leaders?: string[];
}

export interface ReviewSelectorOption {
  label: string;
  url: string;
  active?: boolean;
}

export interface ReviewSelectorGroup {
  title: string;
  subtitle?: string;
  options: ReviewSelectorOption[];
}

export interface ReviewChangeEntry {
  title: string;
  change: string;
  detail: string;
  tone?: Tone | string;
  url?: string | null;
}

export interface ReviewChangeLog {
  note?: string;
  entries?: ReviewChangeEntry[];
  empty?: string;
}

export interface ReviewLifecycleCard {
  name: string;
  code?: string;
  tone?: Tone | string;
  status?: string;
  copy?: string;
  metrics?: string[];
  foot?: string;
}

export interface ReviewLifecycleGroup {
  key: string;
  title: string;
  subtitle?: string;
  count: number;
  cards?: ReviewLifecycleCard[];
  empty?: string;
}

export interface ReviewResearchPanel {
  eyebrow?: string;
  title: string;
  summary?: string;
  metric_cards?: MetricCardData[];
  groups?: Array<{
    title: string;
    entries?: Array<{
      label: string;
      summary?: string;
      detail_url?: string | null;
    }>;
  }>;
  artifact_url?: string;
  artifact_path?: string;
}

export interface ShadowReplayReviewSummary {
  status?: string;
  title?: string;
  summary?: string;
  warning?: string;
  sample_origin?: string;
  source_lane?: string;
  universe_policy?: string;
  start_date?: string;
  end_date?: string;
  cards?: MetricCardData[];
  bucket_counts?: Record<string, number>;
  action_counts?: Record<string, number>;
  classification_counts?: Record<string, number>;
  setup_counts?: Record<string, number>;
  artifacts?: BasicCard[];
  generated_at?: string;
  report_path?: string | null;
  panel_path?: string | null;
  labels_path?: string | null;
}

export interface ReviewComparisonPanel {
  title: string;
  subtitle?: string;
  cards?: MetricCardData[];
  empty?: string;
  artifact_url?: string;
  artifact_path?: string;
}

export interface ReviewDetailData {
  generated_at: string;
  section_key: string;
  label: string;
  hero?: {
    eyebrow?: string;
    title?: string;
    summary?: string;
  };
  selector_groups?: ReviewSelectorGroup[];
  comparison_note?: string;
  missing_note?: string | null;
  source_cards?: MetricCardData[];
  summary_cards?: MetricCardData[];
  comparison_panels?: ReviewComparisonPanel[];
  artifacts?: BasicCard[];
  links?: LinkMap;
}

export interface ReviewLearningMemory {
  key?: string;
  kind?: "stock_case" | "pattern" | string;
  scope?: "stock" | "pattern" | string;
  scope_label?: string;
  match_reason?: string;
  title?: string;
  summary?: string;
  tone?: Tone | string;
  stock_code?: string;
  stock_name?: string;
  trade_date?: string;
  reviewed_at?: string;
  lane?: string;
  action?: string;
  action_label?: string;
  review_reason_key?: string;
  review_reason_label?: string;
  primary_cause?: string;
  primary_cause_label?: string;
  secondary_cause_labels?: string[];
  conclusion_action_label?: string;
  follow_up_status_label?: string;
  sample_count?: number;
  stock_count?: number;
  evidence_strength?: string;
  evidence_strength_label?: string;
  learning_hint?: string;
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
  learning_memories?: ReviewLearningMemory[];
  observation_instruction?: string;
  upgrade_condition?: string;
  invalid_condition?: string;
  avoid_condition?: string;
  risk_tags?: string[];
  priority_label?: string | number;
  persistence_label?: string;
  action_key?: string;
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

export interface TodayActionDisplayState {
  value: TodayActionDisplayValue;
  label: string;
  tone: Tone | string;
  updated_at?: string;
  updated_at_raw?: string;
  reason?: string;
}

export interface TodayActionContext {
  value?: string;
  label?: string;
  status?: string;
  tone?: Tone | string;
  note?: string;
}

export interface DecisionContractConstraint {
  code: string;
  type?: string;
  label?: string;
  message?: string;
  dataset?: string;
  state?: string;
  capabilities?: string[];
  why_not?: Array<{ code?: string; label?: string; message?: string }>;
}

export interface DecisionContractDataRequirement {
  dataset: string;
  label?: string;
  role?: string;
  cost_class?: string;
  cadence?: string;
  critical_for?: string[];
  important_for?: string[];
  relationship?: "critical" | "important" | string;
  state?: string;
  decision_scope?: string;
  failure_impact?: string;
}

export interface DecisionContractEvidenceRef {
  kind: string;
  key?: string;
  label?: string;
  url?: string | null;
  path?: string | null;
  trade_date?: string | null;
  age_label?: string | null;
  stale?: boolean;
}

export interface DecisionContract {
  schema_version: string;
  contract_id: string;
  action_key: string;
  lane?: string;
  trade_date?: string;
  expected_trade_date?: string;
  data_trade_date?: string | null;
  stock?: { code?: string; name?: string; market?: string } | null;
  action?: string;
  action_label?: string;
  decision_scope?: string;
  readiness_mode?: string;
  readiness_ready?: boolean;
  required_capabilities?: string[];
  data_requirements?: DecisionContractDataRequirement[];
  evidence_refs?: DecisionContractEvidenceRef[];
  execution_constraints?: DecisionContractConstraint[];
  requires_real_money?: boolean;
  allowed_for_real_money?: boolean;
  allowed_for_formal_action?: boolean;
  ledger_capture_key?: string;
  ledger_capture?: {
    surface?: string;
    capture_required?: boolean;
    capture_stale_items?: boolean;
  };
  review_obligation?: {
    required?: boolean;
    reason?: string;
    windows?: string[];
    minimum_evidence?: string[];
  };
}

export interface DecisionContractPayload {
  schema_version: string;
  trade_date?: string;
  expected_trade_date?: string;
  data_trade_date?: string | null;
  summary?: {
    total?: number;
    real_money_allowed?: number;
    formal_allowed?: number;
    blocked?: number;
    review_required?: number;
  };
  items?: DecisionContract[];
  by_action_key?: Record<string, DecisionContract>;
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
  display_state?: TodayActionDisplayState;
  freshness?: TodayActionContext;
  confidence?: TodayActionContext;
  actionable?: boolean;
  trust?: {
    trusted?: boolean;
    trade_date?: string;
    expected_trade_date?: string;
    stale_reasons?: string[];
  };
  stale_reasons?: string[];
  decision_contract?: DecisionContract;
  allowed_for_real_money?: boolean;
  execution_constraints?: DecisionContractConstraint[];
}

export interface TodayActionQueue {
  title: string;
  subtitle?: string;
  note?: string;
  items: TodayActionItem[];
  stale_items?: TodayActionItem[];
  hidden_count?: number;
  stale_hidden_count?: number;
  counts: {
    total: number;
    pending: number;
    done: number;
    watch: number;
    skip: number;
    no_fill?: number;
    stale?: number;
    last_updated?: string;
  };
  decision_contracts?: DecisionContractPayload;
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

export type CommandBriefModeValue = "defense" | "observe" | "probe" | "offense";
export type CommandBriefPermitValue =
  | "on" | "off" | "shadow" | "limited" | "none" | "observe" | "conditional" | "actionable";

export interface CommandBriefPermit {
  value: CommandBriefPermitValue;
  label: string;
  tone: string;
  why: string;
}

export interface CommandBriefMode {
  value: CommandBriefModeValue;
  label: string;
  tone: string;
  summary: string;
  reasons: string[];
}

export interface CommandBriefPositionCap {
  value: string;
  raw: string;
  tone: string;
  note: string;
}

export interface CommandBriefFirstAction {
  title: string;
  reason: string;
  url: string;
  action_key?: string | null;
  tone: string;
  kind: "stock" | "system" | "recover_data";
}

export interface CommandBriefForbidItem {
  title: string;
  reason: string;
  tone: string;
  source: string;
}

export interface CommandBriefReclassifyRule {
  label: string;
  condition: string;
  evidence: string;
  url?: string | null;
}

export interface CommandBriefJudgement {
  dim: "market" | "main_theme" | "holdings_pressure" | "new_quality";
  title: string;
  verdict: string;
  tone: string;
  evidence: string[];
  impact: string;
}

export interface CommandBriefLaneItem {
  key: string;
  code: string | null;
  name: string | null;
  action_type: string;
  reason: string;
  trigger: string;
  invalidate_when: string;
  source: string;
  url?: string | null;
  tone: string;
}

export interface CommandBriefLane {
  key: "must" | "conditional" | "observe" | "forbid";
  title: string;
  tone: string;
  subtitle: string;
  items: CommandBriefLaneItem[] | CommandBriefForbidItem[];
}

export interface CommandBriefMiddayCard {
  name: string;
  code: string;
  reason: string;
  url: string;
  tone: string;
}

export interface CommandBriefMiddayVerify {
  available: boolean;
  morning_takeaway: string;
  midday_status: string;
  fresh_candidates: CommandBriefMiddayCard[];
  downgraded: CommandBriefMiddayCard[];
  next_day_condition: string;
  verified_at: string;
}

export interface CommandBriefTrust {
  readiness_mode: string;
  source_summary: string;
  quality_summary: string;
  blockers_count: number;
  warnings_count: number;
  auto_refresh_summary: string;
}

export interface TodayCommandBrief {
  trade_date: string;
  generated_at: string;
  mode: CommandBriefMode;
  permits: {
    data: CommandBriefPermit;
    market: CommandBriefPermit;
    opportunity: CommandBriefPermit;
  };
  position_cap: CommandBriefPositionCap;
  first_action: CommandBriefFirstAction;
  forbid_today: CommandBriefForbidItem[];
  reclassify_when: CommandBriefReclassifyRule[];
  judgement_chain: CommandBriefJudgement[];
  action_lanes: CommandBriefLane[];
  midday_verify: CommandBriefMiddayVerify;
  trust: CommandBriefTrust;
  errors?: Record<string, string>;
}

export interface TodayData {
  generated_at: string;
  display_date?: string;
  trade_date: string;
  expected_trade_date?: string;
  data_trade_date?: string | null;
  brief_is_live: boolean;
  readiness?: ReadinessPayload;
  hero: TodayHero;
  command_hero?: TodayCommandHero;
  radar_cards?: MetricCardData[];
  action_queue: TodayActionQueue;
  risk_rows?: RiskRow[];
  source_cards: SourceCardData[];
  summary_cards: MetricCardData[];
  quality_cards?: QualityCardData[];
  command_brief?: TodayCommandBrief;
  command_brief_error?: string | null;
  decision_contracts?: DecisionContractPayload;
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

export interface WatchlistDayOverDayChange {
  code: string;
  name: string;
  before?: string | number | null;
  after?: string | number | null;
  field?: string;
}

export interface WatchlistDayOverDayPresence {
  code: string;
  name: string;
  action?: string;
  group?: string;
}

export interface WatchlistDayOverDayDiff {
  today_trade_date: string | null;
  previous_trade_date: string | null;
  added: WatchlistDayOverDayPresence[];
  removed: WatchlistDayOverDayPresence[];
  action_changes: WatchlistDayOverDayChange[];
  group_changes: WatchlistDayOverDayChange[];
  boundary_changes: WatchlistDayOverDayChange[];
  signal_changes: WatchlistDayOverDayChange[];
  unchanged_count: number;
}

export interface WatchlistData {
  generated_at: string;
  display_date?: string;
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
    cta_links?: Array<{ label?: string; href?: string }>;
  };
  summary_cards?: MetricCardData[];
  groups?: Array<CardGroup<StockListCard>>;
  source_cards?: SourceCardData[];
  focus_tags?: string[];
  avoid_points?: string[];
  day_over_day_diff?: WatchlistDayOverDayDiff;
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
  display_date?: string;
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
    cta_links?: Array<{ label?: string; href?: string }>;
  };
  summary_cards?: MetricCardData[];
  groups?: Array<CardGroup<StockListCard>>;
  secondary_groups?: Array<CardGroup<StockListCard>>;
  lifecycle_groups?: Array<CardGroup<StockListCard>>;
  lifecycle_cards?: MetricCardData[];
  lifecycle_note?: string;
  top_rows?: RiskRow[];
  theme_cards?: BasicCard[];
  status_strip?: BasicCard[];
  source_cards?: SourceCardData[];
  quality_cards?: BasicCard[];
  learning_memories?: ReviewLearningMemory[];
  learning_memory_summary?: {
    case_count?: number;
    pattern_count?: number;
    error?: string | null;
  };
  focus_tags?: string[];
  avoid_points?: string[];
  links?: LinkMap;
}

export interface ReviewData {
  generated_at: string;
  trade_date?: string;
  shadow_replay?: ShadowReplayReviewSummary;
  freshness_alerts?: RiskRow[];
  freshness_summary?: {
    stale_count?: number;
    research_stale?: boolean;
    lifecycle_stale?: boolean;
  };
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
    cta_links?: Array<{ label?: string; href?: string }>;
  };
  summary_cards?: MetricCardData[];
  verdict_cards?: BasicCard[];
  selector_groups?: ReviewSelectorGroup[];
  reading_compass?: MetricCardData[];
  action_rules?: RiskRow[];
  change_log?: ReviewChangeLog;
  mini_compare?: BasicCard[];
  confidence_switch?: {
    title?: string;
    status?: string;
    label?: string;
    tone?: Tone | string;
    summary?: string;
    note?: string;
    metrics?: MetricCardData[];
    actions?: Array<{ title: string; url?: string; external?: boolean }>;
  };
  comparison_cards?: MetricCardData[];
  lifecycle_cards?: MetricCardData[];
  lifecycle_groups?: ReviewLifecycleGroup[];
  research_panels?: ReviewResearchPanel[];
  source_cards?: SourceCardData[];
  artifacts?: BasicCard[];
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
  learning_memories?: ReviewLearningMemory[];
  source_cards?: SourceCardData[];
  artifacts?: BasicCard[];
  links?: LinkMap;
}

export interface StockTodayActionContext {
  key: string;
  trade_date?: string;
  source?: string;
  status?: string;
  detail?: string;
  group_title?: string;
  actionable?: boolean;
  trust?: {
    trusted?: boolean;
    trade_date?: string;
    expected_trade_date?: string;
    stale_reasons?: string[];
  } | null;
  confidence?: TodayActionContext | null;
  decision?: TodayActionDecision | null;
  display_state?: TodayActionDisplayState | null;
}

export interface StockProfileData {
  generated_at?: string;
  code: string;
  name?: string | null;
  trade_date?: string;
  expected_trade_date?: string;
  data_trade_date?: string | null;
  readiness?: ReadinessPayload;
  primary_source?: "watchlist" | "opportunity" | null;
  primary_source_label?: string;
  primary_detail?: StockDetailData;
  available_sources?: Array<"watchlist" | "opportunity">;
  watchlist?: StockDetailData;
  opportunity?: StockDetailData;
  formal_data?: StockFormalData;
  today_action?: StockTodayActionContext | null;
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
  checked_started_at?: string;
  checked_finished_at?: string;
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
  manifest_stale_count?: number;
  task_stale_count?: number;
  running: RunItem[];
  recommended_task: {
    task_name: string;
    title: string;
    kind?: string;
    cooldown_seconds?: number;
    manifest_dependencies?: string[];
  };
  recovery_steps?: Array<{
    step?: number;
    task_name?: string;
    title?: string;
    status?: string;
    can_trigger?: boolean;
    cooldown_remaining_seconds?: number;
    next_allowed_at?: string;
    issue_count?: number;
    issues?: ReadinessIssue[];
    purpose?: string;
    writes_to_ledger?: boolean;
    estimated_seconds?: number;
  }>;
  cooldown: {
    seconds: number;
    remaining_seconds: number;
    ready: boolean;
    next_allowed_at?: string;
    last_trigger_at?: string;
    last_task_name?: string;
    last_run_id?: string;
    last_reason?: string;
    last_decision?: Record<string, unknown>;
    page_last_trigger_at?: string;
    page_last_run_id?: string;
  };
  auto_refresh?: RefreshAutoDecision;
  last_auto_refresh?: RefreshAuditEvent | null;
  last_refresh_event?: RefreshAuditEvent | null;
  policy?: {
    page?: RefreshPagePolicy;
    task?: RefreshTaskPolicy;
  };
  policy_catalog?: {
    tasks?: Record<string, RefreshTaskPolicy>;
    pages?: Record<string, RefreshPagePolicy>;
    windows?: Record<string, RefreshWindow>;
    cron?: Array<{
      task_name?: string;
      name?: string;
      cron_expr?: string;
      command?: string[];
      delivery_default?: boolean;
      fixed_window?: boolean;
      catchup_enabled?: boolean;
      catchup_until?: string;
      retry_attempts?: number;
      retry_delay_seconds?: number;
      depends_on?: string[];
    }>;
  };
  scheduler_status?: SchedulerStatus;
  active_auto_windows?: RefreshWindow[];
  readiness?: ReadinessPayload;
  readiness_mode?: ReadinessMode;
  recommended_tasks?: string[];
  snapshot_signature: string;
}

export interface FormalDataRow extends ReadinessSourceFreshness {
  setup_state?: string;
  next_action?: string;
  error?: string | null;
  quality_flags?: string[];
  license_scope?: string;
  source_endpoint?: string;
  source_apis?: string[];
  required_permission?: string;
  docs?: string[];
  required_request_keys?: string[];
  missing_request_keys?: string[];
  blocked_request_keys?: string[];
  key_states?: Array<{
    request_key?: string;
    status?: string;
    trade_date?: string;
    row_count?: number;
    formal_decision_allowed?: boolean;
    source_authority_ready?: boolean;
    quality_flags?: string[];
    error?: string | null;
    manifest_path?: string;
  }>;
}

export interface FormalDataStatus {
  generated_at: string;
  expected_trade_date: string;
  provider: {
    name: string;
    token_configured: boolean;
    token_env_names: string[];
    configured_token_env_names?: string[];
    api_url?: string;
    token_value_visible?: boolean;
    local_env_path?: string;
    local_env_file_exists?: boolean;
  };
  ready: boolean;
  ready_count: number;
  total_count: number;
  blocked_count: number;
  datasets: FormalDataRow[];
  blockers: Array<{
    dataset?: string;
    label?: string;
    state?: string;
    next_action?: string;
    error?: string | null;
    quality_flags?: string[];
    source_apis?: string[];
    required_permission?: string;
    docs?: string[];
    required_request_keys?: string[];
    missing_request_keys?: string[];
    blocked_request_keys?: string[];
  }>;
  source_plan?: Array<{
    dataset?: string;
    provider?: string;
    source_apis?: string[];
    required_permission?: string;
    docs?: string[];
  }>;
  setup_steps?: string[];
  last_run?: RunItem | null;
  running?: boolean;
  recommended_task?: {
    task_name?: string;
    title?: string;
  };
}

export interface DataAssetRow {
  dataset: string;
  label: string;
  purpose?: string;
  available: boolean;
  provider?: string;
  trade_date?: string | null;
  key_count?: number;
  manifest_count?: number;
  latest_row_count?: number | null;
  freshness_status?: string;
  source_lane?: string;
  decision_scope?: string;
  source_authority_ready?: boolean;
  formal_decision_allowed?: boolean;
  source_endpoint?: string;
  manifest_path?: string;
}

export interface DataAssetsStatus {
  generated_at: string;
  expected_trade_date?: string | null;
  dataset_root?: string;
  summary: {
    catalog_count: number;
    available_count: number;
    tushare_ready_count: number;
    manifest_count: number;
    universe_count: number;
    trade_days: number;
  };
  visible_usage: string[];
  datasets: DataAssetRow[];
  harvest_runs: Array<{
    label?: string;
    run_dir?: string;
    report_path?: string;
    ok?: boolean;
    start_date?: string;
    end_date?: string;
    trade_date?: string;
    universe_count?: number;
    trade_days?: number;
    datasets?: string[];
    events?: Record<string, number | string | boolean | null>;
    finished_at?: string;
    token_value_visible?: boolean;
  }>;
  promotion_report?: {
    ok?: boolean;
    trade_date?: string;
    universe_count?: number;
    counts?: Record<string, number>;
    written_manifests?: number;
    finished_at?: string;
  } | null;
}

export interface StockFormalData {
  available: boolean;
  code: string;
  trade_date?: string;
  provider?: string;
  headline?: string;
  summary?: string;
  metric_cards?: MetricCardData[];
  valuation?: Record<string, unknown>;
  liquidity?: Record<string, unknown>;
  capital_flow?: Record<string, unknown>;
  fundamental?: Record<string, unknown>;
  financial_quality?: Record<string, Record<string, unknown>>;
  index_memberships?: Array<Record<string, unknown>>;
  top_list?: Array<Record<string, unknown>>;
  top_inst?: Array<Record<string, unknown>>;
  dividends?: Array<Record<string, unknown>>;
  shareholders?: Array<Record<string, unknown>>;
  source_cards?: SourceCardData[];
}

export interface ScheduledRunState {
  task_name?: string;
  status?: string;
  same_day?: boolean;
  today_success?: boolean;
  running?: boolean;
  orphaned?: boolean;
  pid_alive?: boolean;
  running_age_seconds?: number | null;
  failed_today?: boolean;
  missing?: boolean;
  stale_latest?: boolean;
  trade_date?: string;
  expected_trade_date?: string;
  run_id?: string;
  title?: string;
  started_at?: string;
  finished_at?: string;
  exit_code?: number | null;
  skip_reason?: string;
  log_path?: string;
  meta_path?: string;
}

export interface SchedulerJobStatus {
  task_name?: string;
  name?: string;
  cron_expr?: string;
  catchup_enabled?: boolean;
  catchup_until?: string;
  catchup_fired?: unknown;
  retry_attempts?: number;
  retry_delay_seconds?: number;
  retry_count_today?: number;
  depends_on?: string[];
  health?: string;
  run?: ScheduledRunState;
}

export interface FreshnessGuardianDatasetState {
  last_checked_at?: string;
  last_decision?: string;
  last_skip_reason?: string;
  last_triggered_at?: string;
  last_trigger_reasons?: string[];
  cooldown_remaining_seconds?: number;
  active_windows?: string[];
  freshness?: {
    dataset?: string;
    age_seconds?: number | null;
    stale_after_seconds?: number | null;
    freshness_status?: string;
    trade_date?: string | null;
    stale_reasons?: string[];
    manifest_path?: string;
  };
}

export interface FreshnessGuardianStatus {
  enabled?: boolean;
  last_checked_at?: string;
  last_skip_reason?: string;
  calendar?: Record<string, unknown>;
  quotes_light?: FreshnessGuardianDatasetState;
  capital_flow_light?: FreshnessGuardianDatasetState;
  [key: string]: unknown;
}

export interface SchedulerStatus {
  server_time?: string;
  calendar?: Record<string, unknown>;
  scheduler?: {
    alive?: boolean;
    pid?: number | string | null;
    started_at?: string;
    last_tick_at?: string;
    state_path?: string;
    send_to_feishu?: boolean;
    fire_on_start?: boolean;
    freshness_guardian?: FreshnessGuardianStatus;
  };
  summary?: {
    total?: number;
    success?: number;
    running?: number;
    failed?: number;
    stale?: number;
    missing?: number;
  };
  jobs?: SchedulerJobStatus[];
}

export interface RefreshWindow {
  key: string;
  label: string;
  start: string;
  end: string;
}

export interface RefreshTaskPolicy {
  task_name?: string;
  title?: string;
  kind?: string;
  cooldown_seconds?: number;
  auto_windows?: string[];
  manifest_dependencies?: string[];
  stale_reasons?: string[];
  auto_enabled?: boolean;
  fixed_cron_only?: boolean;
  same_family?: string;
}

export interface RefreshPagePolicy {
  page?: string;
  allowed_tasks?: string[];
  related_tasks?: string[];
  poll_seconds?: Record<string, number>;
  stale_after_seconds?: Record<string, number>;
  auto_on_open?: boolean;
}

export interface RefreshAutoDecision {
  enabled?: boolean;
  allowed?: boolean;
  should_trigger?: boolean;
  force?: boolean;
  page?: string;
  task_name?: string;
  task_kind?: string;
  reason_codes?: string[];
  blocked_reasons?: string[];
  active_windows?: RefreshWindow[];
  required_windows?: string[];
  manifest_reasons?: string[];
  stale_count?: number;
  cooldown_remaining_seconds?: number;
  next_allowed_at?: string;
  summary?: string;
  triggered?: boolean;
  trigger?: {
    started?: boolean;
    run_id?: string;
    task_name?: string;
    title?: string;
    log_path?: string;
    meta_path?: string;
  } | null;
}

export interface RefreshAuditEvent {
  ts?: string;
  trigger_type?: string;
  page?: string;
  task_name?: string;
  task_family?: string;
  run_id?: string;
  force?: boolean;
  reason?: string;
  manifest_state?: Array<{
    key?: string;
    label?: string;
    stale?: boolean;
    freshness_status?: string;
    trade_date?: string | null;
    stale_reasons?: string[];
  }>;
  cooldown?: {
    remaining_seconds?: number;
    next_allowed_at?: string;
  };
  decision?: RefreshAutoDecision | Record<string, unknown>;
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
  evaluation?: {
    ok: boolean;
    errors: string[];
    warnings: string[];
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
  requested_task_name?: string;
  canonical_task_name?: string;
  title?: string;
  send_to_feishu?: boolean;
  feishu_warning?: string;
  feishu_status?: {
    available?: boolean;
    installed?: boolean;
    configured?: boolean;
    detail?: string;
    reason?: string;
    accounts?: string[];
  };
  meta_path?: string;
  log_path?: string;
}

export interface HealthResponse {
  ok: boolean;
  workspace?: string;
  channels?: {
    feishu?: {
      available?: boolean;
      installed?: boolean;
      configured?: boolean;
      detail?: string;
      reason?: string;
      accounts?: string[];
    };
  };
}

// ===========================================================================
// Decision Ledger -- read-only views returned by /api/decision-ledger/*.
//
// The shapes mirror what ``apps/control-panel/decision_ledger.py`` returns
// from ``_decision_summary_card``, ``summarize_window``, and
// ``build_ledger_health``.  Optional fields are typed as such because the
// backend tolerates missing rows (empty ledger, never-run evaluator) and
// reports ``null`` rather than synthesising fake values.
// ===========================================================================

export interface DecisionLedgerLatestExecution {
  status?: string;
  trade_date?: string;
  side?: string | null;
  price?: number | null;
  quantity?: number | null;
  amount?: number | null;
  note?: string | null;
}

export interface DecisionLedgerLatestOutcome {
  window?: string;
  as_of_trade_date?: string;
  label?: string;
  tone?: string;
  return_pct?: number | null;
  relative_return_pct?: number | null;
}

export interface DecisionLedgerCompactRecord {
  decision_id: string;
  trade_date: string;
  code: string;
  name?: string;
  action?: string;
  action_label?: string;
  lane?: string;
  surface?: string;
  status?: string;
  main_conclusion?: string;
  execution_events_count: number;
  outcome_events_count: number;
  latest_execution?: DecisionLedgerLatestExecution | null;
  latest_outcome?: DecisionLedgerLatestOutcome | null;
}

export interface DecisionLedgerScanError {
  file: string;
  error: string;
}

export interface DecisionLedgerStatusError {
  kind: string;
  file: string;
  error: string;
}

export interface DecisionLedgerRecentResponse {
  items: DecisionLedgerCompactRecord[];
  count: number;
  limit: number;
  errors: DecisionLedgerScanError[];
}

export interface DecisionLedgerStockResponse {
  code: string;
  items: DecisionLedgerCompactRecord[];
  count: number;
  errors: DecisionLedgerScanError[];
}

export interface DecisionLedgerSummaryResponse {
  as_of: string;
  window_days: number;
  from_date: string;
  to_date: string;
  decisions: {
    total: number;
    open: number;
    superseded: number;
  };
  outcome_distribution: Record<string, number>;
  execution_gap_count: number;
  data_issue_count: number;
  execution_events_total: number;
  outcome_events_total: number;
  errors: DecisionLedgerScanError[];
}

export interface DecisionLedgerCalibrationGroup {
  key: string;
  label: string;
  total: number;
  evaluated: number;
  validated: number;
  invalidated: number;
  data_issue: number;
  execution_gap: number;
  missed_opportunity: number;
  superseded: number;
  pending: number;
  review_needed: number;
  validated_rate: number;
  invalidated_rate: number;
  data_issue_rate: number;
  review_rate: number;
}

export interface DecisionLedgerSuggestionCard {
  kind: string;
  tone: Tone | string;
  title: string;
  summary: string;
  calibration_action?: string;
  action_label?: string;
  action_reason?: string;
  evidence_strength?: string;
  sample_size?: number;
  insufficient_sample?: boolean;
  shadow_only?: boolean;
  sample_origin?: string;
  source_lane?: string;
}

export interface ShadowCalibrationRow {
  axis?: string;
  key?: string;
  label?: string;
  window?: string | null;
  total?: number;
  validated?: number;
  invalidated?: number;
  inconclusive?: number;
  avoided_loss?: number;
  missed_opportunity?: number;
  validated_rate?: number;
  invalidated_rate?: number;
  avoided_loss_rate?: number;
  missed_opportunity_rate?: number;
  avg_return_pct?: number;
  title?: string;
  summary?: string;
  sample_origin?: string;
  source_lane?: string;
  universe_policy?: string;
}

export interface ShadowCalibrationSummary {
  status?: string;
  title?: string;
  summary?: string;
  warning?: string;
  sample_origin?: string;
  source_lane?: string;
  universe_policy?: string;
  start_date?: string;
  end_date?: string;
  panel_rows?: number;
  label_rows?: number;
  available_labels?: number;
  trade_dates?: number;
  generated_at?: string;
  manifest_path?: string;
  labels_path?: string;
  cards?: DecisionLedgerSuggestionCard[];
  bucket_rows?: ShadowCalibrationRow[];
  setup_rows?: ShadowCalibrationRow[];
  window_rows?: ShadowCalibrationRow[];
  action_rows?: ShadowCalibrationRow[];
}

export type DecisionLedgerReviewStatus =
  | "pending_outcome"
  | "pending_execution"
  | "ready_review"
  | "reviewed"
  | "blocked_data"
  | "low_priority";

export interface DecisionLedgerMaturity {
  maturity_due_at?: string | null;
  maturity_window?: string;
  maturity_label?: string;
  is_overdue?: boolean;
  is_due?: boolean;
  missing_due_date?: boolean;
}

export interface DecisionLedgerQualityAxis {
  label: string;
  score: number;
  tone: Tone | string;
  reason: string;
}

export interface DecisionLedgerQualityAxes {
  judgment_quality?: DecisionLedgerQualityAxis;
  execution_quality?: DecisionLedgerQualityAxis;
  learning_quality?: DecisionLedgerQualityAxis;
}

export interface DecisionLedgerReviewCase {
  schema_version?: number;
  review_case_id: string;
  decision_id: string;
  stock_code?: string;
  stock_name?: string;
  trade_date?: string;
  reviewed_at?: string;
  created_at?: string;
  review_status?: string;
  review_status_label?: string;
  primary_cause?: string;
  primary_cause_label?: string;
  secondary_causes?: string[];
  secondary_cause_labels?: string[];
  review_note?: string;
  conclusion_action?: string;
  conclusion_action_label?: string;
  evidence_strength?: string;
  evidence_strength_label?: string;
  evidence_strength_detail?: string;
  sample_count?: number;
  rule_hypothesis?: string;
  rule_action_allowed?: boolean;
  follow_up_status?: string;
  follow_up_status_label?: string;
  follow_up_due_at?: string;
  ai_draft?: DecisionLedgerAttributionDraft | null;
  human_final?: DecisionLedgerAttributionFinal | null;
  human_overrides?: Record<string, { from?: unknown; to?: unknown }>;
  attribution_confidence?: string;
  evidence_refs?: unknown[];
  human_check_required?: unknown[];
  similar_case_refs?: DecisionLedgerCaseRef[];
  shadow_sample_refs?: ShadowCalibrationRow[];
  lane?: string;
  action?: string;
  action_label?: string;
  review_reason_key?: string;
  review_reason?: string;
  market_regime?: string | null;
  stock_theme?: unknown;
  evidence_source?: string;
  latest_outcome?: DecisionLedgerLatestOutcome | null;
  latest_execution?: DecisionLedgerLatestExecution | null;
}

export interface DecisionLedgerReviewCasePattern {
  pattern_id: string;
  lane?: string;
  action?: string;
  action_label?: string;
  review_reason_key?: string;
  review_reason_label?: string;
  primary_cause?: string;
  primary_cause_label?: string;
  dominant_primary_cause?: string;
  dominant_primary_cause_label?: string;
  dominant_secondary_causes?: string[];
  dominant_secondary_cause_labels?: string[];
  sample_count: number;
  stock_count?: number;
  evidence_strength?: string;
  evidence_strength_label?: string;
  evidence_strength_detail?: string;
  rule_action_allowed?: boolean;
  rule_candidate_allowed?: boolean;
  stock_theme?: string;
  market_regime?: string;
  evidence_source?: string;
  rule_hypothesis?: string;
  follow_up_status?: string;
  follow_up_status_label?: string;
  dominant_conclusion_action?: string;
  dominant_conclusion_action_label?: string;
  learning_hint?: string;
  learning_memory_scope?: string;
  cases?: DecisionLedgerReviewCase[];
}

export interface DecisionLedgerReviewCaseOption {
  value: string;
  label: string;
}

export interface DecisionLedgerReviewCaseWorkbench {
  decision: DecisionLedgerDetailResponse;
  learning_record: DecisionLedgerReviewRecord;
  review_case?: DecisionLedgerReviewCase | null;
  similar_cases?: DecisionLedgerReviewCase[];
  pattern?: DecisionLedgerReviewCasePattern | null;
  options?: {
    primary_causes?: DecisionLedgerReviewCaseOption[];
    secondary_causes?: DecisionLedgerReviewCaseOption[];
    conclusion_actions?: DecisionLedgerReviewCaseOption[];
    follow_up_statuses?: DecisionLedgerReviewCaseOption[];
  };
  guardrail?: {
    sample_count?: number;
    evidence_strength?: string;
    detail?: string;
  };
}

export interface DecisionLedgerCaseRef {
  review_case_id?: string;
  decision_id?: string;
  stock_code?: string;
  stock_name?: string;
  trade_date?: string;
  lane?: string;
  action?: string;
  review_reason_key?: string;
  primary_cause?: string;
  primary_cause_label?: string;
  conclusion_action?: string;
  conclusion_action_label?: string;
  evidence_strength?: string;
  evidence_strength_label?: string;
  sample_count?: number;
  review_note?: string;
  learning_hint?: string;
}

export interface DecisionLedgerAttributionDraft {
  schema_version?: number;
  draft_id?: string;
  decision_id?: string;
  generated_at?: string;
  draft_source?: string;
  provider?: string;
  model?: string | null;
  fallback_reason?: string;
  primary_cause: string;
  secondary_causes?: string[];
  review_note?: string;
  conclusion_action: string;
  rule_hypothesis?: string;
  follow_up_status?: string;
  confidence?: string;
  evidence?: string[];
  human_check_required?: string[];
  similar_case_refs?: DecisionLedgerCaseRef[];
  pattern_memory_refs?: DecisionLedgerCaseRef[];
  shadow_sample_refs?: ShadowCalibrationRow[];
  sample_count?: number;
  evidence_strength?: string;
  evidence_strength_label?: string;
  evidence_strength_detail?: string;
  rule_action_allowed?: boolean;
}

export interface DecisionLedgerAttributionFinal {
  primary_cause?: string;
  secondary_causes?: string[];
  review_note?: string;
  conclusion_action?: string;
  rule_hypothesis?: string;
  follow_up_status?: string;
  follow_up_due_at?: string;
  evidence_strength?: string;
  sample_count?: number;
  rule_action_allowed?: boolean;
}

export interface DecisionLedgerReviewCaseSavePayload {
  primary_cause: string;
  secondary_causes?: string[];
  review_note?: string;
  conclusion_action: string;
  rule_hypothesis?: string;
  follow_up_status?: string;
  follow_up_due_at?: string;
  ai_draft?: DecisionLedgerAttributionDraft | null;
  human_final?: DecisionLedgerAttributionFinal;
  attribution_confidence?: string;
  evidence_refs?: unknown[];
  human_check_required?: string[];
  similar_case_refs?: DecisionLedgerCaseRef[];
  shadow_sample_refs?: ShadowCalibrationRow[];
}

export interface DecisionLedgerReviewCaseSaveResponse {
  ok: boolean;
  review_case: DecisionLedgerReviewCase;
  workbench: DecisionLedgerReviewCaseWorkbench;
}

export interface DecisionLedgerAttributionDraftResponse {
  ok: boolean;
  draft: DecisionLedgerAttributionDraft;
}

export interface DecisionLedgerReviewCasesResponse {
  items: DecisionLedgerReviewCase[];
  count: number;
  patterns: DecisionLedgerReviewCasePattern[];
}

export interface DecisionLedgerReviewRecord extends DecisionLedgerCompactRecord {
  review_status?: DecisionLedgerReviewStatus | string;
  review_reason?: string;
  review_reason_key?: string;
  maturity_due_at?: string | null;
  maturity_label?: string;
  maturity_window?: string;
  missing_fields?: string[];
  is_overdue?: boolean;
  next_action_label?: string;
  next_action_reason?: string;
  quality_axes?: DecisionLedgerQualityAxes;
  priority_score?: number;
  priority_label?: string;
  priority_reasons?: string[];
  calibration_action?: string;
  calibration_action_label?: string;
  calibration_action_reason?: string;
  outcome_status?: string;
  outcome_tone?: Tone | string;
  execution_status?: string;
  maturity?: DecisionLedgerMaturity;
  review_case?: DecisionLedgerReviewCase;
}

export interface DecisionLedgerReviewWorkbench {
  today_queue_count: number;
  ready_review_count: number;
  blocked_data_count?: number;
  pending_count: number;
  overdue_count: number;
  top_priority_reason: string;
  system_learning_state: string;
  next_best_action: string;
  top_priority_decision_id?: string | null;
}

export interface DecisionLedgerCalibrationResponse {
  as_of: string;
  window_days: number;
  from_date: string;
  to_date: string;
  overall: DecisionLedgerCalibrationGroup;
  by_lane: DecisionLedgerCalibrationGroup[];
  by_action: DecisionLedgerCalibrationGroup[];
  review_workbench: DecisionLedgerReviewWorkbench;
  review_records: DecisionLedgerReviewRecord[];
  review_queue: DecisionLedgerReviewRecord[];
  ready_reviews: DecisionLedgerReviewRecord[];
  pending_reviews: DecisionLedgerReviewRecord[];
  needs_review: DecisionLedgerReviewRecord[];
  needs_review_count: number;
  reviewed_case_count?: number;
  review_case_patterns?: DecisionLedgerReviewCasePattern[];
  review_case_summary?: {
    total?: number;
    attributed?: number;
    patterns?: number;
  };
  shadow_calibration?: ShadowCalibrationSummary;
  suggestion_cards: DecisionLedgerSuggestionCard[];
  errors: DecisionLedgerScanError[];
}

export interface DecisionLedgerExecutionEvent {
  event_id?: string;
  decision_id?: string;
  created_at?: string;
  trade_date?: string;
  status?: string;
  side?: string | null;
  price?: number | null;
  quantity?: number | null;
  amount?: number | null;
  note?: string;
  source?: string;
  intent_key?: string | null;
  today_action_key?: string | null;
}

export interface DecisionLedgerOutcomeEvent {
  event_id?: string;
  decision_id?: string;
  window?: string;
  evaluated_at?: string;
  as_of_trade_date?: string;
  market_data?: {
    entry_reference_price?: number | null;
    close_price?: number | null;
    return_pct?: number | null;
    benchmark_code?: string | null;
    benchmark_return_pct?: number | null;
    relative_return_pct?: number | null;
    max_favorable_pct?: number | null;
    max_adverse_pct?: number | null;
  };
  boundary_checks?: Record<string, unknown>;
  classification?: {
    label?: string;
    tone?: string;
    summary?: string;
    reasons?: string[];
  };
  quality?: {
    usable_for_decision_quality?: boolean;
    data_issue?: string | null;
  };
}

export interface DecisionLedgerDetailResponse {
  schema_version?: number;
  decision_id: string;
  trade_date: string;
  created_at?: string;
  source?: {
    lane?: string;
    surface?: string;
    action_key?: string;
    source_label?: string;
    artifact_paths?: string[];
  };
  stock: {
    code: string;
    name?: string;
  };
  recommendation?: {
    action?: string;
    action_label?: string;
    action_raw?: string;
    main_conclusion?: string;
    position_guidance?: string;
    trigger_condition?: string;
    continue_condition?: string;
    stop_condition?: string;
    risk_summary?: string;
  };
  evidence_snapshot?: {
    expected_trade_date?: string;
    data_trade_date?: string;
    readiness_mode?: string;
    readiness_ready?: boolean;
    blockers?: unknown[];
    warnings?: unknown[];
    source_cards?: unknown[];
    metric_cards?: unknown[];
    capital_summary?: unknown;
    technical_summary?: unknown;
    theme_summary?: unknown;
  };
  parameter_snapshot?: {
    path?: string | null;
    sha256?: string | null;
    summary?: unknown;
  };
  status?: {
    state?: string;
    superseded_by?: string | null;
  };
  execution_events: DecisionLedgerExecutionEvent[];
  outcome_events: DecisionLedgerOutcomeEvent[];
}

export interface DecisionLedgerStorageStatus {
  mode?: string;
  primary_root?: string;
  legacy_root?: string;
  primary_exists?: boolean;
  legacy_exists?: boolean;
  primary_decision_files?: number;
  legacy_decision_files?: number;
  writes_to?: string;
  reads_from?: string[];
}

export interface DecisionLedgerLearningBucket {
  ruleset_version: string;
  lane: string;
  action: string;
  samples: number;
  mature_samples: number;
  outcomes: Record<string, number>;
  execution_events: number;
  pending_outcome: number;
  needs_review: number;
  review_rate?: number;
  sample_stage?: string;
  decision_ids?: string[];
}

export interface DecisionLedgerLearningSuggestion {
  ruleset_version: string;
  lane: string;
  action: string;
  suggested_action: string;
  reason: string;
  mature_samples: number;
  needs_review: number;
  review_rate: number;
}

export interface DecisionLedgerLearningLoopResponse {
  version: string;
  generated_at: string;
  as_of: string;
  ruleset_versions: string[];
  samples_total: number;
  mature_samples: number;
  pending_review_count: number;
  buckets: DecisionLedgerLearningBucket[];
  suggestions: DecisionLedgerLearningSuggestion[];
  errors: DecisionLedgerScanError[];
}

export interface DecisionLedgerCaptureStatus {
  recorded_at?: string;
  task_name?: string;
  status?: "success" | "failed" | string;
  trade_date?: string | null;
  captured?: number;
  already_present?: number;
  skipped?: number;
  superseded?: number;
  decision_ids?: string[];
  error?: string | null;
  status_write_error?: string;
}

export interface DecisionLedgerOutcomeStatus {
  recorded_at?: string;
  status?: "success" | "failed" | "no_provider" | string;
  task_name?: string;
  run_id?: string;
  scheduled_via?: string;
  as_of_date?: string;
  started_at?: string;
  finished_at?: string;
  provider?: string;
  evaluated?: number;
  already_present?: number;
  skipped_no_provider?: number;
  skipped_provider_unavailable?: number;
  data_issue?: number;
  errors?: number;
  events?: Array<{
    decision_id?: string;
    window?: string;
    label?: string;
    detail?: string;
  }>;
  error?: string | null;
}

export interface DecisionLedgerHealthResponse {
  generated_at: string;
  as_of_trade_date: string;
  decisions_total: number;
  decisions_open: number;
  decisions_superseded: number;
  evaluated_outcomes: number;
  pending_outcomes: number;
  last_capture?: DecisionLedgerCaptureStatus | null;
  last_outcome_evaluation?: DecisionLedgerOutcomeStatus | null;
  corrupt_files: DecisionLedgerScanError[];
  status_errors: DecisionLedgerStatusError[];
  storage?: DecisionLedgerStorageStatus;
  learning_loop?: DecisionLedgerLearningLoopResponse;
}
