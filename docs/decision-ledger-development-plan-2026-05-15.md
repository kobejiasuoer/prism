# Prism Decision Ledger Development Plan

Date: 2026-05-15
Status: planning only, not implemented
Owner: Prism product / engineering

## 1. Goal

Prism should not only produce daily stock actions. It should remember what it said, what the operator actually did, and whether the market later validated the decision logic.

This feature adds a **Decision Ledger** layer for daily decision accountability:

- Capture each actionable recommendation as an immutable decision snapshot.
- Attach operator execution results without rewriting the original recommendation.
- Revisit decisions at fixed T+N windows and classify the outcome.
- Surface decision quality in Command Center, Stock Profile, Portfolio, and Review.
- Preserve separation between system recommendation, human execution, market outcome, and data quality.

The first version is not a full backtesting platform, not an auto-trading system, and not a machine-learning optimizer. It is a disciplined audit layer for Prism's real daily workflow.

## 2. Why This Is The Next Feature

The current system already has the main operator surfaces:

- Command Center for today's actions.
- Portfolio for account state, fills, no-fill intents, cash, and reconciliation.
- Discovery for candidates and themes.
- Stock Profile for unified single-stock decision context and follow-up questions.
- Review for historical research windows and lifecycle views.
- Settings for refresh, tasks, parameter editing, and evaluation guardrails.

The remaining product gap is not another display page. The gap is accountability:

- Did today's recommendation work later?
- Was a bad result caused by the system's logic, stale data, or the operator's execution?
- Which source lane is more reliable: watchlist, discovery, midday, or Ask fallback?
- Which action type fails most often: buy, reduce, hold, observe, skip, or forbid?
- Which parameters or evidence states were active when a decision was made?

Decision Ledger turns Prism from a system that gives advice into a system that accumulates operational memory.

## 3. Non-Goals

The MVP must stay narrow. Do not include these in the first implementation:

- Automatic order placement.
- Full portfolio-level performance attribution.
- Formal execution-realistic backtesting.
- Machine-learning parameter tuning.
- Complex strategy optimizer.
- Broker integration beyond the existing manual account book.
- New vendor data source work.
- Large redesign of existing pages.
- Rewriting `dashboard_data.py` as part of this feature.

## 4. Product Principles

### 4.1 Snapshot, Do Not Recompute

The ledger must store the recommendation as it existed at decision time. Later review must not reconstruct the old decision from today's data.

Minimum snapshot requirements:

- Recommendation text and action.
- Trigger / continue / stop conditions.
- Position guidance.
- Source lane and source detail.
- Data trade date and expected trade date.
- Readiness mode and blockers / warnings.
- Evidence summary.
- Parameter hash.
- Links to source artifacts when available.

### 4.2 Append-Only History

The original decision record should be immutable after creation. Execution results and outcome evaluations should be appended as related records or nested append-only events.

Allowed updates:

- Add execution event.
- Add T+N outcome event.
- Mark superseded by a later decision.
- Add system metadata such as schema migration version.

Disallowed updates:

- Rewriting original recommendation fields.
- Replacing old evidence snapshot with a current one.
- Deleting failed or embarrassing decisions from normal UI paths.

### 4.3 Separate Four Truths

Every review view must keep these separate:

1. System recommendation: what Prism suggested.
2. Human execution: what the operator did or did not do.
3. Market outcome: what happened afterward.
4. Data quality: whether the input state was trustworthy.

This separation prevents the system from blaming execution for bad logic, or blaming logic for stale data.

### 4.4 Honest Labels Over Score Theater

The first outcome labels should be explainable and conservative. Do not introduce a fake precision score before the evidence supports it.

Preferred labels:

- `validated`: decision logic was directionally validated.
- `invalidated`: decision logic failed against its own boundary.
- `early`: direction eventually worked but the signal was too early.
- `late`: direction worked but Prism surfaced it too late.
- `avoided_loss`: skip / reduce / forbid avoided meaningful downside.
- `missed_opportunity`: observe / skip / forbid missed meaningful upside.
- `execution_gap`: system decision was usable but execution diverged materially.
- `data_issue`: stale or incomplete data makes the outcome unfit for quality judgment.
- `inconclusive`: not enough time or price movement to classify.

## 5. MVP Scope

The first release should implement a complete but small loop:

1. Generate ledger records from Today's action queue.
2. Append execution events from existing Portfolio writeback actions.
3. Run a daily follow-up task that evaluates T+1 / T+3 / T+5 windows.
4. Expose ledger data through API endpoints.
5. Add lightweight UI surfaces in existing pages.
6. Add focused tests for idempotency, append-only behavior, and outcome classification.

## 6. Data Model Draft

### 6.1 Storage Location

Start with JSON files under repo runtime data, not a database migration.

Recommended path:

```text
apps/data/decision_ledger/
  decisions/
    2026-05-15.json
  outcomes/
    2026-05-15.json
  indexes/
    by_stock.json
    by_trade_date.json
```

Rationale:

- Matches current Prism artifact style.
- Easy to inspect and test.
- Avoids adding persistence infrastructure before the shape stabilizes.
- Can migrate later to SQLite or another repository abstraction.

Do not commit generated ledger data by default. Add or confirm ignore rules before implementation.

### 6.2 Decision Record

Draft shape:

```json
{
  "schema_version": 1,
  "decision_id": "2026-05-15:600690:today_action:watchlist:abc12345",
  "trade_date": "2026-05-15",
  "created_at": "2026-05-15 09:35:00",
  "source": {
    "lane": "watchlist",
    "surface": "today_action_queue",
    "action_key": "watchlist:600690:2026-05-15",
    "source_label": "自选股链路",
    "artifact_paths": []
  },
  "stock": {
    "code": "600690",
    "name": "海尔智家"
  },
  "recommendation": {
    "action": "hold",
    "action_label": "继续持有",
    "main_conclusion": "继续持有，但不加仓",
    "position_guidance": "半仓以内",
    "trigger_condition": "放量站回关键均线再考虑加仓",
    "continue_condition": "不跌破趋势线则继续观察",
    "stop_condition": "跌破止损线或资金持续流出",
    "risk_summary": "弱市中只按纪律处理"
  },
  "evidence_snapshot": {
    "expected_trade_date": "2026-05-15",
    "data_trade_date": "2026-05-15",
    "readiness_mode": "live_ready",
    "readiness_ready": true,
    "blockers": [],
    "warnings": [],
    "source_cards": [],
    "metric_cards": [],
    "capital_summary": null,
    "technical_summary": null,
    "theme_summary": null
  },
  "parameter_snapshot": {
    "path": "stock-analyzer/config/stocks.json",
    "sha256": "...",
    "summary": {
      "active_stock_count": 10,
      "kline_days": 120,
      "news_count": 20
    }
  },
  "status": {
    "state": "open",
    "superseded_by": null
  }
}
```

### 6.3 Execution Event

Execution must be attached without mutating the original recommendation.

Draft shape:

```json
{
  "schema_version": 1,
  "event_id": "exec:2026-05-15:600690:001",
  "decision_id": "2026-05-15:600690:today_action:watchlist:abc12345",
  "created_at": "2026-05-15 10:02:00",
  "trade_date": "2026-05-15",
  "status": "filled",
  "side": "buy",
  "price": 28.35,
  "quantity": 100,
  "amount": 2835.0,
  "note": "按计划轻仓试错",
  "source": "portfolio_writeback"
}
```

Allowed `status` values:

- `filled`
- `no_fill`
- `watch`
- `skip`
- `manual_note`

### 6.4 Outcome Event

Draft shape:

```json
{
  "schema_version": 1,
  "event_id": "outcome:2026-05-15:600690:t3",
  "decision_id": "2026-05-15:600690:today_action:watchlist:abc12345",
  "window": "T+3",
  "evaluated_at": "2026-05-20 18:10:00",
  "as_of_trade_date": "2026-05-20",
  "market_data": {
    "entry_reference_price": 28.35,
    "close_price": 29.10,
    "return_pct": 2.65,
    "benchmark_code": "000300",
    "benchmark_return_pct": 0.80,
    "relative_return_pct": 1.85,
    "max_favorable_pct": 4.20,
    "max_adverse_pct": -1.10
  },
  "boundary_checks": {
    "trigger_touched": true,
    "stop_touched": false,
    "continue_condition_held": true
  },
  "classification": {
    "label": "validated",
    "tone": "positive",
    "summary": "T+3 相对基准走强，且未触发止损边界。",
    "reasons": [
      "相对沪深300 +1.85%",
      "最大不利波动未触发失效条件"
    ]
  },
  "quality": {
    "usable_for_decision_quality": true,
    "data_issue": null
  }
}
```

## 7. Decision ID And Idempotency

Ledger generation must be idempotent. Re-running the same daily refresh should not create duplicate decisions.

Recommended ID inputs:

- `trade_date`
- `stock.code`
- `source.surface`
- `source.lane`
- `source.action_key`
- normalized recommendation action

If an action changes materially during the same trade date, create a new decision record and mark the previous record as superseded.

Material change examples:

- Action changes from `observe` to `buy`.
- Position guidance changes materially.
- Stop condition changes.
- Readiness changes from `blocked` to `live_ready` and the decision becomes executable.

Non-material change examples:

- Generated timestamp changes.
- Cosmetic wording changes.
- Source card ordering changes.

## 8. Outcome Classification Rules

### 8.1 Initial Windows

Use fixed windows only:

- `T+1`
- `T+3`
- `T+5`

Skip non-trading days using the existing trading calendar helpers.

### 8.2 Initial Market Metrics

For each window, compute:

- Reference price at decision time or nearest available close.
- Window close price.
- Absolute return.
- Benchmark return.
- Relative return.
- Maximum favorable excursion.
- Maximum adverse excursion.
- Whether stop boundary was touched when parseable.

### 8.3 Label Heuristics

Keep first rules simple and transparent.

For buy / add / trial actions:

- `validated`: relative return positive and stop not touched.
- `invalidated`: stop touched or relative return materially negative.
- `early`: T+1 invalid / weak, later T+5 validated.
- `late`: major move already happened before decision, then no favorable window.
- `execution_gap`: decision validated but execution status is `no_fill`, `skip`, or materially worse fill.

For hold / continue actions:

- `validated`: held boundary and did not materially underperform.
- `invalidated`: stop / risk boundary touched.
- `data_issue`: original readiness was blocked or stale.

For reduce / sell / forbid / skip actions:

- `avoided_loss`: subsequent downside or underperformance validates caution.
- `missed_opportunity`: subsequent strong relative upside contradicts caution.
- `inconclusive`: movement too small or data incomplete.

All thresholds should live in one small config section, not scattered across UI code.

## 9. Backend Implementation Plan

### Phase 1: Repository And Schema

Add a small decision ledger repository module.

Likely files:

- `apps/control-panel/decision_ledger.py`
- `apps/control-panel/tests/test_decision_ledger.py`

Responsibilities:

- Load daily decision files.
- Save decision files atomically.
- Append execution events.
- Append outcome events.
- Build indexes by stock and trade date.
- Enforce idempotency.
- Validate basic schema.

Acceptance criteria:

- Re-running decision capture for the same input does not duplicate records.
- Original recommendation fields are not changed by execution or outcome events.
- Corrupt JSON degrades with a clear error instead of silently dropping records.

### Phase 2: Capture Today Action Queue

Use existing Today action data as the first capture source.

Likely integration points:

- `apps/control-panel/dashboard_data.py`
- `build_today_action_queue(...)`
- `build_stock_profile_view(...)`
- `/api/today`

Recommended shape:

- Add a pure builder that converts Today action items into `DecisionRecord` drafts.
- Run capture as part of an explicit task first, not silently on every page read.
- Later consider page-read capture only if it remains idempotent and cheap.

Potential task name:

- `decision_ledger_capture`

Acceptance criteria:

- Today's actionable queue produces ledger records.
- Blocked / shadow-only decisions are captured as non-executable recommendations with readiness context.
- Empty action queue creates no records but returns a successful no-op result.

### Phase 3: Attach Portfolio Writeback

Wire existing execution writebacks into the ledger.

Likely integration points:

- `record_fill(...)`
- `record_no_fill_intent(...)`
- `update_today_action_decision(...)`
- `/api/portfolio/fills`
- `/api/portfolio/intent/no_fill`
- `/api/today/actions/decision`

Rules:

- If request includes `intent_key` or `today_action_key`, attach to matching decision.
- If no matching decision exists, create a manual execution note only if enough context exists.
- Do not block account-book writes if ledger append fails; return a warning and log it.

Acceptance criteria:

- Recording a fill appends an execution event to the matching decision.
- Recording no-fill / watch / skip appends the correct execution event.
- Existing portfolio behavior remains unchanged when ledger is unavailable.

### Phase 4: Outcome Evaluator

Add a scheduled evaluator that runs after close or during the next startup window.

Likely files:

- `apps/scripts/evaluate_decision_ledger.py`
- `apps/control-panel/decision_ledger.py`
- `apps/control-panel/trading_calendar.py`
- `packages/prism_data/service.py` or existing quote / bars accessors if appropriate

Task responsibilities:

- Find decisions due for T+1 / T+3 / T+5 evaluation.
- Fetch or load needed price data.
- Compute metrics.
- Classify outcome.
- Append outcome events idempotently.
- Produce a compact run summary.

Potential task name:

- `decision_followup`

Acceptance criteria:

- Evaluator can be rerun without duplicating outcome events.
- Non-trading days are skipped correctly.
- Missing price data marks `data_issue` or `inconclusive`, not a false failure.
- Outcome events include enough reasons to explain the label.

### Phase 5: API Endpoints

Add narrow API endpoints for existing frontend pages.

Draft endpoints:

```text
GET /api/decision-ledger/summary?window=7d
GET /api/decision-ledger/recent?limit=20
GET /api/decision-ledger/stock/{code}
GET /api/decision-ledger/decision/{decision_id}
POST /api/decision-ledger/capture
POST /api/tasks/decision_followup/run
```

Initial payloads should be read-optimized and compact. Avoid exposing raw giant snapshots everywhere.

Acceptance criteria:

- Summary endpoint powers Command Center and Review widgets.
- Stock endpoint powers Stock Profile history.
- Recent endpoint powers Review detail list.
- Raw detail endpoint remains available for debugging.

## 10. Frontend Implementation Plan

### 10.1 Command Center

Add a compact `Decision Loop` panel.

Content:

- Today's actions captured count.
- Unrecorded execution count.
- Due follow-up count.
- Recent validated / invalidated / inconclusive counts.
- Link to Review decision quality section.

Do not make this panel compete with the primary daily action CTA.

### 10.2 Portfolio

Enhance existing writeback flow.

Content:

- Show whether the writeback is attached to a ledger decision.
- After submission, show `已写入执行账本` or a warning if ledger append failed.
- Keep current account-book workflow intact.

### 10.3 Stock Profile

Add a `决策历史` section or tab content.

Content:

- Last 5 decisions for this stock.
- Action label, trade date, source lane.
- Execution status.
- Latest T+N outcome label.
- Expandable reasons.

The first screen should still prioritize current decision, not history.

### 10.4 Review

Add `决策质量` view.

Content:

- Recent decision list.
- Outcome distribution.
- Breakdown by source lane.
- Breakdown by action type.
- Top execution gaps.
- Top data issues.

Avoid over-claiming performance. The copy should say `决策后验` or `决策质量`, not `收益率排名`.

### 10.5 Settings

Add task visibility only if needed:

- Manual run button for `decision_followup`.
- Last run status.
- Latest error summary.

Do not add complex configuration UI in the MVP.

## 11. Scheduler And Task Integration

Recommended task schedule:

- `decision_ledger_capture`: after morning decision artifacts are ready.
- `decision_followup`: after market close, or during evening maintenance.

Safety rules:

- Never run outcome evaluation against today's incomplete session as a final T+N result.
- Respect trading calendar.
- Treat missing data as incomplete, not failed.
- Do not block core refresh tasks if ledger task fails.

## 12. Tests

### 12.1 Unit Tests

Add tests for:

- Decision ID stability.
- Duplicate capture prevention.
- Append-only execution events.
- Append-only outcome events.
- Schema validation.
- Corrupt file handling.
- T+N trading-day resolution.
- Outcome classification heuristics.

### 12.2 API Tests

Add tests for:

- Summary endpoint empty state.
- Summary endpoint with mixed outcomes.
- Stock endpoint returns only matching code.
- Detail endpoint returns original snapshot and appended events.
- Capture endpoint idempotency.

### 12.3 Integration Tests

Add tests for:

- Today action queue to ledger capture.
- Portfolio fill to execution event.
- No-fill / watch / skip to execution event.
- Outcome evaluator with fixture price data.

### 12.4 Frontend Tests

Minimum:

- Typecheck for new types and hooks.
- Smoke test for empty ledger state.
- Smoke test for stock decision history rendering.
- Smoke test for Review decision-quality section.

## 13. Migration And Backfill

MVP does not need full historical backfill.

Recommended sequence:

1. Start capturing new decisions only.
2. After schema stabilizes, optionally backfill from recent `today_action_decisions.json`, command briefs, and watchlist snapshots.
3. Mark backfilled records with `backfilled: true` and lower confidence.

Backfill records must not pretend to have original evidence snapshots if those snapshots are incomplete.

## 14. Rollout Plan

### Milestone 0: Planning Approval

Deliverables:

- This plan reviewed.
- MVP scope agreed.
- Outcome labels agreed.
- Storage path agreed.

No code changes required.

### Milestone 1: Backend Ledger Core

Deliverables:

- Repository module.
- Decision schema.
- Execution and outcome event schema.
- Idempotent file writes.
- Focused unit tests.

Exit criteria:

- Ledger can store and read sample records safely.

### Milestone 2: Capture And Execution Attach

Deliverables:

- Today action capture task.
- Portfolio writeback attaches execution events.
- Minimal API for recent / stock / summary.
- Backend tests.

Exit criteria:

- A normal daily workflow creates decisions and records operator results.

### Milestone 3: Outcome Evaluator

Deliverables:

- T+1 / T+3 / T+5 evaluator.
- Initial classification rules.
- Scheduler task definition.
- Data-missing behavior.

Exit criteria:

- Fixture decisions receive deterministic outcome labels.

### Milestone 4: UI Surfaces

Deliverables:

- Command Center loop panel.
- Stock Profile decision history.
- Review decision-quality section.
- Portfolio writeback feedback.

Exit criteria:

- Operator can see the full loop without using old control-panel pages.

### Milestone 5: Hardening

Deliverables:

- Runtime path ignore checks.
- Failure logging.
- Manual run controls if needed.
- Documentation update.

Exit criteria:

- Ledger failure does not break core trading-day workflow.
- Tests pass.
- Generated ledger data stays out of source commits.

## 15. Open Questions

1. Should decision capture happen automatically during `/api/today`, or only through a scheduled task?

   Recommendation: scheduled task first. Page reads should not create important persistent state until the flow is proven stable.

2. Should blocked / stale decisions be captured?

   Recommendation: yes, but mark them non-executable and exclude from normal decision-quality hit rate.

3. What benchmark should MVP use?

   Recommendation: start with a simple default benchmark from existing available data, then allow source-lane-specific benchmark later.

4. How strict should outcome labels be?

   Recommendation: conservative. Prefer `inconclusive` over pretending precision.

5. Should execution gaps affect system quality metrics?

   Recommendation: report separately. Do not count execution failures as model failures.

6. Should Ask-only temporary analysis enter the ledger?

   Recommendation: not in MVP unless it becomes a Today action or the operator explicitly records it.

## 16. Risks

### Risk: Recomputed History

If old decisions are rebuilt from current artifacts, the ledger becomes untrustworthy.

Mitigation:

- Store original snapshots at capture time.
- Mark backfills explicitly.

### Risk: Duplicate Decisions

Daily tasks and page reloads may generate duplicates.

Mitigation:

- Stable decision IDs.
- Idempotent writes.
- Tests for repeated capture.

### Risk: UI Overload

Decision quality can become another noisy dashboard.

Mitigation:

- Keep first UI compact.
- Put detail in Review and Stock Profile, not the Command Center hero.

### Risk: False Precision

Outcome labels can imply more certainty than the data supports.

Mitigation:

- Use conservative labels.
- Keep reasons visible.
- Mark data issues explicitly.

### Risk: Runtime Data In Git

Ledger files may create large dirty diffs.

Mitigation:

- Store under ignored runtime paths.
- Add source-only staging guidance.

## 17. First Implementation Checklist

When development starts, use this checklist:

- [ ] Confirm storage path and ignore rules.
- [ ] Define `DecisionRecord`, `ExecutionEvent`, and `OutcomeEvent` types.
- [ ] Build repository read / write / append methods.
- [ ] Add stable decision ID function.
- [ ] Add Today action capture conversion.
- [ ] Add capture task or endpoint.
- [ ] Attach Portfolio writeback events.
- [ ] Add T+N due-decision resolver.
- [ ] Add price metric calculator.
- [ ] Add conservative outcome classifier.
- [ ] Add summary / recent / stock API endpoints.
- [ ] Add Command Center summary panel.
- [ ] Add Stock Profile decision history.
- [ ] Add Review decision-quality section.
- [ ] Add tests before broad UI polish.
- [ ] Verify generated data stays uncommitted.

## 18. Recommended MVP Acceptance Criteria

The feature is MVP-complete when:

- A Today action becomes exactly one ledger decision record.
- A Portfolio writeback appends an execution event to that decision.
- A scheduled evaluator appends T+1 / T+3 / T+5 outcomes.
- Stock Profile can show that stock's decision history.
- Review can show recent decision quality and execution gaps.
- Empty / stale / missing-data states are explicit.
- Re-running capture and evaluation is idempotent.
- Existing daily workflow still works when ledger task fails.

