# Prism Decision Ledger Product Requirements

Date: 2026-05-16
Status: product requirements
Scope: Decision Ledger closed-loop usability

## 1. Product Positioning

Prism already has the core Decision Ledger implementation in progress. The current system can write decision records, attach execution events, and evaluate T+N outcomes at the module level, but the capability is not yet fully present in the daily operator workflow.

This requirement moves Decision Ledger from a backend audit layer into a daily usable product loop:

> Prism should automatically remember what it recommended, what the operator did, what the market later did, and make that history visible for review.

The goal is not to add another large page or rebuild the product shell. The goal is to close the loop around the capability that already exists.

## 2. Current State

Existing capabilities:

- `apps/control-panel/decision_ledger.py` provides the repository layer for decision records, execution events, outcome events, append-only behavior, deduplication, and corrupt-file failures.
- `POST /api/decision-ledger/capture` can capture Today's action queue into ledger records.
- Portfolio writebacks can attach `filled` and `no_fill` execution events to matching decisions.
- Today action decisions can attach `watch` and `skip` execution events.
- `apps/scripts/evaluate_decision_ledger.py` provides a manual outcome evaluator entry point.
- Tests exist for core ledger behavior, Today action capture, Portfolio writeback attachment, and outcome evaluation.

Known product gaps:

- Capture is not yet wired into the daily fixed workflow.
- Outcome evaluation does not yet use a production price provider.
- Read APIs are missing for summary, recent decisions, stock timeline, and decision detail.
- Frontend visibility is minimal; ledger records are not yet first-class in Review, Portfolio, or Stock Profile.
- Operator-facing health status is missing for capture and outcome evaluation.

## 3. User Value

Decision Ledger closed-loop usability should create four user-visible benefits.

1. Daily recommendations are recorded automatically.

   The operator should not need to manually remember what Prism recommended today. The system should capture the recommendation snapshot as part of the normal daily workflow.

2. Recommendation, execution, market outcome, and data quality stay separate.

   Review must preserve the difference between what Prism suggested, what the operator did, what the market later did, and whether the input data was trustworthy.

3. Review becomes a decision timeline instead of report archaeology.

   The operator should be able to inspect historical decisions by stock, date, action, and outcome without manually searching through generated reports.

4. Prism begins accumulating judgment quality.

   The system should eventually answer which lanes, action types, and evidence states tend to validate, fail, arrive early, arrive late, or remain inconclusive.

## 4. MVP Scope

The MVP should make the existing ledger useful in daily operation.

Must include:

- Automatic capture of Today's action queue.
- Read APIs for ledger summary, recent decisions, stock timeline, and decision detail.
- Basic frontend visibility in existing pages.
- Outcome evaluation using an existing Prism price or market-data layer.
- Capture and evaluation status exposed through health or task status.

Must not include:

- Automatic order placement.
- Broker integration beyond the existing account-book writeback path.
- Full portfolio attribution.
- Formal execution-realistic backtesting.
- Strategy optimization or machine-learning tuning.
- Multi-agent debate visualization.
- Large UI redesign.
- Database migration from JSON to SQLite or another store.

## 5. Core Requirements

### 5.1 Automatic Capture

Prism must automatically capture Today's action queue into the Decision Ledger after important daily workflows complete.

Recommended trigger points:

- After midday confirmation completes.
- After post-close command brief completes, or immediately before it runs.
- Manual capture remains available through the existing API.

Product requirements:

- Same-day repeated capture must be idempotent.
- Original recommendation snapshots must not be overwritten by later runs.
- A material action change for the same stock and source should create a new decision and mark the previous one as superseded.
- Capture failure must not block the core research workflow.
- Capture failure must be visible in task status, health status, or both.

### 5.2 Read APIs

Prism must expose Decision Ledger data through read APIs.

Required endpoints:

```text
GET /api/decision-ledger/summary?window=7d
GET /api/decision-ledger/recent?limit=20
GET /api/decision-ledger/stock/{code}
GET /api/decision-ledger/decision/{decision_id}
```

The APIs should support these product needs:

- Count total decisions in the requested window.
- Count open, superseded, and evaluated decisions.
- Count execution statuses: `filled`, `no_fill`, `watch`, `skip`, and `manual_note`.
- Count outcome status by window: `T+1`, `T+3`, and `T+5`.
- Return recent decisions with enough fields for a compact UI row.
- Return a stock-specific timeline.
- Return full detail for a single decision.
- Include related artifact paths when available.
- Preserve and expose data quality blockers and warnings.

### 5.3 Outcome Evaluation

Prism must evaluate due decisions at T+1, T+3, and T+5.

Product requirements:

- Use an existing Prism quote, price, or market-data layer. Do not add a new vendor just for this feature.
- If price data is unavailable, classify the evaluation as `data_issue` or leave it explicitly pending. Do not silently skip it.
- Outcome events must include:
  - `window`
  - `as_of_trade_date`
  - starting price
  - ending price
  - stock return
  - optional benchmark return
  - outcome label
  - data quality notes
- Re-running evaluation must be idempotent.
- Evaluation failure must not mutate or corrupt the original decision record.

### 5.4 Frontend Visibility

The MVP should add ledger visibility to existing pages instead of creating a large new page.

Preferred surfaces:

- Review: show recent decisions or a small decision review section.
- Portfolio: show the latest Prism decision and execution attachment status for each held stock where available.
- Stock Profile: show the stock's decision timeline.
- Settings or Health: show capture and outcome evaluation status.

Minimum UI fields:

- Stock code and name.
- Decision date.
- Source lane.
- Recommended action.
- Main conclusion.
- Execution status.
- Outcome status.
- Superseded state.
- Data quality state.

The UI should make it clear when no decision exists, when a decision exists but has no execution event, and when an outcome is still pending.

### 5.5 Health And Observability

Prism must make ledger health visible.

Required status fields:

- Last capture time.
- Last capture result.
- Number of decisions created, skipped, superseded, or failed.
- Last outcome evaluation time.
- Number of due outcomes.
- Number of evaluated outcomes.
- Number of pending outcomes.
- Recent failure reason summary.
- Corrupt ledger file error details when detected.

The operator should be able to tell whether Decision Ledger worked today without inspecting raw JSON files.

## 6. Priority

### P0

- Wire automatic capture into the daily workflow.
- Add `summary`, `recent`, and `stock` read APIs.
- Show recent ledger records in Review or Portfolio.
- Expose capture and evaluation status.

### P1

- Connect outcome evaluation to a production price provider.
- Add Stock Profile decision timeline.
- Show superseded decision relationships.
- Display data quality labels.

### P2

- Add aggregation by lane, action, stock, and outcome.
- Add decision quality trend views.
- Add JSON or CSV export.
- Build a fuller Review experience around decision quality.

## 7. Acceptance Criteria

### Functional Acceptance

- Every trading day can produce Decision Ledger records automatically after the configured workflow.
- Repeated capture on the same day does not create duplicate decisions.
- Portfolio filled writeback attaches to a matching decision when one exists.
- Portfolio no-fill writeback attaches to a matching decision when one exists.
- Today action `watch` and `skip` decisions attach execution events when matching decisions exist.
- Review or another core page can display recent ledger decisions.
- A stock-level view can show historical decisions for a stock.
- Due T+N outcomes are evaluated or explicitly marked as pending/data issue.

### Data Acceptance

- Original recommendation snapshots are not overwritten by later capture runs.
- Execution events are appended and deduplicated.
- Outcome events are appended and deduplicated by window.
- Corrupt JSON fails visibly and is not silently treated as an empty ledger.
- Missing price data does not produce fake outcomes.

### Experience Acceptance

The operator can answer these questions in less than 30 seconds:

- What recommendations did Prism record today?
- What was Prism's latest decision for a given stock?
- Did the operator act on the recommendation?
- Has the recommendation been evaluated yet?
- Did Decision Ledger run successfully today?

## 8. Success Definition

The first successful release of this requirement should make Decision Ledger satisfy three product promises:

- Remember: daily recommendations are captured automatically.
- Retrieve: recent, stock-level, and detail views are queryable.
- See: at least one core Prism page exposes ledger history without opening raw files.

This is not a new product direction. It is the productization of the Decision Ledger work already present in Prism.
