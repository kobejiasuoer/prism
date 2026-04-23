# Prism Stock Analysis Evaluation Implementation Spec

Date: 2026-04-23
Owner: Prism research system
Status: approved direction, ready to split into execution plans

## 1. Purpose

This document turns the internal stock-analysis evaluation benchmark into an executable acceptance program for Prism.

The goal is not to immediately improve stock-picking performance.
The goal is to make every future Prism stock-analysis change measurable, repeatable, and safe.

After this program is in place, any change to watchlist rules, screener scoring, midday confirmation, command brief output, data ingestion, or product presentation should answer five questions before it is accepted:

- Did the change preserve data freshness and source traceability?
- Did the change preserve or improve risk discipline?
- Did the change preserve or improve output clarity?
- Did the change improve historical behavior, or at least avoid making it worse?
- Can the result be reproduced from fixed inputs?

## 2. Current Prism Capability Assumption

This spec assumes Prism is currently a short-swing A-share tactical research and execution-assistance system.

It should not be evaluated as a mature quantitative asset-management platform yet.

Current core lanes:

- `stock-analyzer`: fixed watchlist and holding-style decision support.
- `packages/screener`: aggressive opportunity discovery, AI secondary screening, and midday confirmation.
- `apps/scripts/prism_canonical.py`: canonical loading and normalization for watchlist, screening, confirmation, brief, quality, and lifecycle objects.
- `apps/scripts/run_command_brief.sh`: command brief orchestration.
- `data/history/reports`: historical reports, quality gates, and backtest reviews.

Current strengths to protect:

- Market environment gating through `execution_gate`.
- Separation between watchlist decisions and discovery candidates.
- Setup classification such as leader continuation, breakout follow, pullback continuation, and low reversal.
- Structured trigger, invalidation, sizing, and risk language.
- Midday confirmation and downgrade logic.
- Quality-gate artifacts for watchlist, screener, and midday lanes.

Current weaknesses to address:

- Evaluation standards are not yet enforced as a repeatable acceptance suite.
- Parameter thresholds are still mostly experience-driven.
- Historical replay exists but is not yet a mandatory regression gate.
- Schema and source traceability are improving but not yet strong enough to support product-grade acceptance.
- Product output quality is judged manually rather than through a stable rubric.

## 3. Program Principles

### 3.1 Safety Before Alpha

Prism should first prove that it does not produce unsafe or misleading recommendations.

Performance improvement is valuable only after the system reliably avoids:

- stale data presented as live confirmation
- weak-market aggressive recommendations
- missing invalidation levels
- contradictory action language
- untraceable stock recommendations
- broken midday baseline comparisons

### 3.2 Fixed Baseline Before Refactor

Before changing scoring, thresholds, or product language, Prism needs a frozen baseline report.

The baseline must capture current behavior for fixed samples so later changes can be compared against the same inputs.

### 3.3 Evaluation Must Be Lane-Aware

Watchlist, discovery, midday, and command brief are different lanes.
They should share quality rules, but they should not be judged by the same success metric.

Watchlist success means disciplined handling of already-followed stocks.
Discovery success means finding candidates with controlled execution risk.
Midday success means confirming or downgrading morning ideas correctly.
Command Center success means producing one coherent daily operating view.

### 3.4 No Recommendation Without Invalidation

Any actionable recommendation must include the condition under which it stops being valid.

This applies to:

- watchlist `action`
- screener `approved` or high-priority `caution`
- analyzer handoff candidates
- midday `confirmed`
- command brief opportunity focus

### 3.5 Every Acceptance Result Must Be Reproducible

An accepted change must identify:

- input artifacts
- source timestamps
- generated artifacts
- scoring or gate version
- command used to evaluate
- pass/fail result
- observed metric deltas

## 4. Evaluation Architecture

The acceptance program should be implemented as five layers.

### 4.1 Benchmark Definition Layer

Responsibility:

- Define scoring dimensions.
- Define hard rejection gates.
- Define maturity tiers.
- Define per-lane required fields.

Expected artifact:

- A versioned benchmark definition, initially represented by this spec and later by machine-readable config.

### 4.2 Fixture And Sample Layer

Responsibility:

- Select fixed historical and current-like samples.
- Preserve sample metadata.
- Make abnormal cases explicit.

Expected artifact:

- A sample manifest that names every fixture and explains why it exists.

### 4.3 Evaluation Runner Layer

Responsibility:

- Load Prism artifacts through canonical loaders where possible.
- Validate schema, timestamps, required fields, gate behavior, and output consistency.
- Produce scorecards and hard-gate failures.

Expected artifact:

- A machine-readable evaluation result and a human-readable acceptance report.

### 4.4 Historical Replay Layer

Responsibility:

- Compare baseline and candidate behavior across fixed historical windows.
- Report friction-adjusted returns, win rate, ranking behavior, and risk metrics.
- Segment results by gate status, setup type, tier, and midday status.

Expected artifact:

- A replay comparison report for each material scoring or rule change.

### 4.5 Product Gate Layer

Responsibility:

- Decide whether a change is internal-only, professionally usable, or product-ready.
- Block release when hard rejection gates fail.
- Keep a history of accepted benchmark results.

Expected artifact:

- A release decision record for every significant stock-analysis change.

## 5. Scoring Model

The internal evaluation score is 100 points.

| Dimension | Weight | What It Measures |
|---|---:|---|
| Data and governance | 20 | Freshness, completeness, timestamp hygiene, missing-data behavior, source traceability |
| Analysis and rule quality | 20 | Market gate, theme, stock factors, setup classification, score decomposition |
| Execution and risk control | 20 | Trigger, invalidation, sizing, downgrade logic, anti-chase discipline |
| Output usability | 15 | Clear action language, coherent priority, explainable risk, command brief usefulness |
| Historical validation | 15 | Friction-adjusted performance, segmented behavior, baseline comparison |
| Stability and productization | 10 | Automation, quality gates, reproducibility, failure handling, release record |

### 5.1 Minimum Tier Scores

| Tier | Total Score | Extra Requirement |
|---|---:|---|
| Basic usable | >= 70 | No hard rejection gate fails |
| Professional usable | >= 82 | Data, risk, and historical dimensions each >= 75% of their dimension weight |
| Product ready | >= 90 | Every core dimension >= 85% of its dimension weight and stability evidence exists |

### 5.2 Score Interpretation

`Basic usable` means Prism is acceptable for internal personal research support.

`Professional usable` means Prism is acceptable as a repeatable research workflow with documented evidence.

`Product ready` means Prism is acceptable for stable product exposure, subject to legal, compliance, and user-safety framing outside this technical benchmark.

## 6. Hard Rejection Gates

A change fails acceptance immediately if any hard rejection gate is triggered.

### 6.1 Cross-Lane Gates

- A required artifact is missing or cannot be parsed as JSON when JSON is expected.
- A generated artifact has no usable timestamp.
- A derived artifact references a source timestamp from a different trade date without being marked invalid.
- A recommendation cannot be traced to a source artifact.
- Output contains contradictory top-level action language for the same stock.
- Missing data is silently treated as confirmed positive evidence.

### 6.2 Watchlist Gates

- Active watchlist stocks are missing from the watchlist snapshot without an explicit exclusion reason.
- A positive action lacks `support`, `stop_loss`, or equivalent invalidation language.
- `flow_unconfirmed` or stale flow data is used as a strong positive confirmation.
- Hard negative flags are present but the stock is still promoted without a written override reason.

### 6.3 Screener Gates

- `execution_gate.status = off` while new positions or analyzer handoff are allowed.
- `execution_gate.status = limited` while leader continuation or breakout chasing is promoted as an executable action.
- `approved` candidates lack `main_risk`, `watch_condition`, or `entry_plan`.
- Duplicate stock codes appear in the final shortlist.
- A stock with missing critical capital-flow data receives no penalty or warning.

### 6.4 Midday Gates

- Morning shortlist and current scan are from different dates but the result is `ok`.
- Current scan timestamp is earlier than the morning source scan timestamp.
- A downgraded item is still promoted in the command brief without a fresh-candidate reason.
- `validation_status != ok` while command brief presents midday output as confirmed.

### 6.5 Command Brief Gates

- The brief does not answer whether new positions are allowed.
- The brief does not include a position cap when opportunities are mentioned.
- The brief promotes opportunities while omitting avoid points or risk boundaries.
- The brief references stale mutable aliases without preserving stable artifact paths when stable paths are available.

## 7. Required Sample Suites

Every material change should be evaluated on four sample suites.

### 7.1 Latest Trading-Day Suite

Purpose:

- Verify that the current operational path still runs.
- Catch fresh schema or timestamp breakage.

Required inputs:

- latest watchlist snapshot
- latest screener result
- latest midday confirmation result when available
- latest command brief
- latest quality-gate artifacts

Pass condition:

- All relevant artifacts parse.
- Quality gates are either `ok` or clearly explain why they are not usable.
- No hard rejection gate fails.

### 7.2 Fixed Historical Normal Suite

Purpose:

- Preserve current expected behavior on known normal days.
- Prevent accidental regressions from refactors.

Required inputs:

- At least three historical command brief runs.
- At least three historical screener runs.
- At least one watchlist snapshot with all active stocks present.
- At least one midday confirmation run with confirmed, downgraded, or fresh-candidate content.

Pass condition:

- The same input produces stable classification, stable gate status, and explainable score differences.
- Top candidate changes are either absent or explicitly explained by the changed rule.

### 7.3 Weak-Environment Suite

Purpose:

- Verify that Prism becomes more defensive when market conditions are weak.

Required inputs:

- Historical days where `execution_gate.status` is `off` or `limited`.
- Historical days where broad market metrics are weak.
- Samples where candidates look individually strong but the broad environment is weak.

Pass condition:

- `off` blocks new positions.
- `limited` suppresses chasing setups.
- Command brief language remains defensive.
- Historical replay does not hide weak-environment behavior inside aggregate results.

### 7.4 Abnormal Input Suite

Purpose:

- Verify safe degradation.

Required cases:

- missing watchlist snapshot
- missing screener result
- empty shortlist
- duplicate shortlist codes
- stale flow data
- morning and current scan date mismatch
- malformed required field
- missing `entry_plan`

Pass condition:

- The lane either fails closed or downgrades safely.
- No actionable recommendation is produced from invalid input.
- The error is visible in the acceptance report.

## 8. Lane Acceptance Contracts

### 8.1 Watchlist Manager Contract

Input:

- watchlist configuration
- realtime price data
- K-line technical data
- fund-flow data
- fundamentals
- news and announcements

Required output fields:

- `date`
- `generated_at`
- `price_basis`
- `flow_basis`
- `tech_basis`
- `stocks`
- per-stock `code`
- per-stock `name`
- per-stock `action`
- per-stock `position`
- per-stock `score`
- per-stock `signal`
- per-stock `hard_flags`
- per-stock `watch_points`
- per-stock `positives`
- per-stock `support`
- per-stock `resistance`
- per-stock `stop_loss`
- per-stock `intraday_triggers`
- per-stock `price_as_of`
- per-stock `flow_as_of`
- per-stock `flow_unconfirmed`

Acceptance checks:

- Active stock coverage is complete.
- Positive actions include invalidation.
- Hard flags explain downgrades.
- Stale flow is visible and penalized.
- Every stock has a beginner-readable next action.

### 8.2 Discovery Engine Contract

Input:

- aggressive stock pool
- realtime quote data
- market regime data
- capital-flow data
- fundamentals
- theme classification
- scan result

Required output fields:

- `timestamp`
- `source_scan_timestamp`
- `pool`
- `pool_label`
- `market_regime`
- `market_themes`
- `screening_rules_applied`
- `shortlist`
- `screening_summary`
- per-candidate `code`
- per-candidate `name`
- per-candidate `best_score`
- per-candidate `change_pct`
- per-candidate `amount_yi`
- per-candidate `themes`
- per-candidate `setup_type`
- per-candidate `setup_label`
- per-candidate `entry_plan`
- per-candidate `main_risk`
- per-candidate `watch_condition`
- per-candidate `capital_flow`
- per-candidate `fundamentals`
- per-candidate `consistency`
- per-candidate `execution_quality`
- per-candidate `screening_status`
- per-candidate `tier`
- per-candidate `execution_gate`

Acceptance checks:

- Shortlist is deduplicated by code.
- Gate status is consistent with allowed setup types.
- Approved candidates have actionable but bounded plans.
- Caution candidates do not look stronger than approved candidates without an explanation.
- Excluded candidates are not promoted downstream.

### 8.3 Midday Confirmation Contract

Input:

- morning AI screening result
- current scan result

Required output fields:

- `timestamp`
- `validation_status`
- `validation_errors`
- `source_morning_timestamp`
- `source_scan_timestamp`
- `verified_against_scan_timestamp`
- `target_codes`
- `confirmed`
- `downgraded`
- `fresh_candidates`
- `items`

Acceptance checks:

- Date and timestamp validation happens before stock-level confirmation.
- Downgrade reasons are concrete.
- Fresh candidates are clearly labeled as fresh, not as morning confirmations.
- Confirmed items preserve risk and watch conditions.

### 8.4 Command Center Contract

Input:

- normalized watchlist snapshot
- normalized screening batch
- normalized midday confirmation
- quality status

Required output fields:

- `summary.trade_date`
- `summary.generated_at`
- `summary.open_new_positions`
- `summary.position_cap`
- `summary.gate_label`
- `summary.gate_summary`
- `summary.main_theme`
- `summary.holding_focus`
- `summary.opportunity_focus`
- `summary.avoid_points`
- `watchlist`
- `screener`
- `midday`

Acceptance checks:

- The brief answers whether new positions are allowed.
- The brief names the position cap.
- The brief separates holding focus from opportunity focus.
- Avoid points are visible when any opportunity is present.
- Midday invalid status blocks confirmed-language output.

## 9. Historical Replay Metrics

Historical replay should report raw and friction-adjusted behavior.

### 9.1 Minimum Performance Metrics

- total sample count
- valid next-day sample count
- valid 3-day sample count
- valid 5-day sample count
- next-day raw return
- next-day net return after friction
- next-day raw win rate
- next-day net win rate
- 3-day raw return
- 3-day net return
- 5-day raw return
- 5-day net return

### 9.2 Risk Metrics

- maximum adverse excursion when available
- maximum favorable excursion when available
- downgrade frequency
- invalidation-hit frequency
- overheat-warning frequency
- missing-data penalty frequency

### 9.3 Segmentation

Replay must segment at least by:

- `execution_gate.status`
- market environment score bucket
- `screening_status`
- `tier`
- `setup_type`
- `execution_quality` bucket
- `consistency` bucket
- midday status
- rank bucket such as Top 1, Top 3, Top 5, and all shortlist

### 9.4 Baseline Comparison Rules

Every rule or parameter change should compare against baseline on:

- candidate count
- approved count
- caution count
- excluded count
- Top 5 overlap
- newly promoted stocks
- newly removed stocks
- net return delta
- net win-rate delta
- weak-environment behavior
- number of hard-gate warnings

Acceptance does not require every return metric to improve.
Acceptance does require any deterioration to be explained and offset by a clear risk-control or product-safety benefit.

## 10. Rollout Phases

### Phase 0: Freeze Baseline

Goal:

- Capture current Prism behavior before changing logic.

Deliverables:

- Baseline artifact manifest.
- Baseline scorecard.
- Baseline command brief sample.
- Baseline historical replay summary.

Acceptance:

- A future worker can rerun the same baseline and identify whether behavior changed.

### Phase 1: Build Evaluation Harness

Goal:

- Convert the benchmark into repeatable checks.

Deliverables:

- Evaluation runner design.
- Machine-readable scorecard shape.
- Human-readable acceptance report shape.
- Initial tests for hard rejection gates.

Acceptance:

- The runner can evaluate existing watchlist, screener, midday, and command brief artifacts without modifying production logic.

### Phase 2: Strengthen Quality Gates

Goal:

- Make unsafe recommendations fail closed.

Deliverables:

- Cross-lane hard-gate checks.
- Lane-specific required-field checks.
- Timestamp and trade-date validation checks.
- Missing-data downgrade checks.

Acceptance:

- Abnormal input suite produces safe failures or safe downgrades.

### Phase 3: Historical Regression And Replay

Goal:

- Make historical behavior mandatory for scoring and rule changes.

Deliverables:

- Fixed replay sample manifest.
- Baseline-vs-candidate comparison report.
- Segmented result tables.

Acceptance:

- A scoring or threshold change cannot be accepted without replay evidence.

### Phase 4: Parameter And Schema Hardening

Goal:

- Move important implicit assumptions into explicit contracts.

Deliverables:

- Parameter dictionary updates.
- Schema version checks.
- Gate and setup compatibility checks.
- Rule-change review template.

Acceptance:

- Any changed threshold or score weight is visible in a versioned artifact and has an evaluation result.

### Phase 5: Product-Readiness Gate

Goal:

- Decide whether Prism can expose stock-analysis output as a stable product surface.

Deliverables:

- Product-readiness scorecard.
- Consecutive-run stability record.
- Failure and rollback policy.
- User-facing explanation checklist.

Acceptance:

- Prism reaches product-ready score thresholds across repeated runs and has no unresolved hard rejection gate.

## 11. First Execution Plan To Write Next

The first implementation plan should be narrow.

Recommended first plan:

`Prism Stock Evaluation Baseline And Scorecard Implementation Plan`

Goal:

- Create a baseline manifest and a non-invasive evaluator that reads existing artifacts and produces a scorecard.

Initial scope:

- Do not change stock-selection logic.
- Do not change scoring thresholds.
- Do not change UI templates.
- Read existing artifacts only.
- Fail closed on hard-gate violations.

Likely files:

- Create `docs/superpowers/plans/2026-04-23-prism-stock-evaluation-baseline-and-scorecard.md`
- Create `data/evaluation/stock_analysis/manifest.json`
- Create `apps/scripts/evaluate_stock_analysis.py`
- Create `tests/test_stock_analysis_evaluation.py`

Initial evaluator responsibilities:

- Load watchlist snapshot.
- Load AI screening result.
- Load midday confirmation result.
- Load command brief result.
- Validate required fields.
- Validate hard gates that can be checked from existing artifacts.
- Produce a scorecard with dimension scores and hard-gate failures.

Out of scope for the first plan:

- Historical return calculation.
- Parameter recalibration.
- UI dashboards.
- New data ingestion.
- Automatic Feishu delivery decisions.

## 12. Change Acceptance Checklist

Every future stock-analysis change should include this checklist in its review.

- The change identifies which lane it affects.
- The change identifies whether it affects data, rules, execution, output, history, or stability.
- The change runs the latest trading-day suite.
- The change runs the fixed historical normal suite.
- The change runs the weak-environment suite if it affects scoring, gates, setup, or command brief language.
- The change runs abnormal input checks if it affects loading, validation, or output rendering.
- The change reports hard-gate status.
- The change reports dimension scores.
- The change explains any Top 5 candidate movement.
- The change explains any approved/caution/excluded count movement.
- The change explains any weaker historical metric.
- The change records source artifact paths and timestamps.

## 13. Open Decisions

These decisions should be made before Phase 2, but they do not block Phase 0 or Phase 1.

- Whether benchmark configuration should live under `data/evaluation` or `configs/evaluation`.
- Whether acceptance reports should be stored under `data/history/reports/evaluation` or `data/evaluation/reports`.
- Whether scorecards should be emitted as JSON only, or both JSON and Markdown from the first pass.
- Whether current historical replay scripts should be wrapped or rewritten when Phase 3 starts.
- Whether quality gates should block Feishu sending immediately or first run in report-only mode.

Recommended defaults:

- Store manifests and machine-readable scorecards under `data/evaluation/stock_analysis`.
- Store human-readable reports under `data/history/reports/evaluation`.
- Emit both JSON and Markdown once the evaluator is stable.
- Keep Feishu blocking in report-only mode until abnormal input checks are proven reliable.

## 14. Success Definition

This program succeeds when Prism can make this statement for every stock-analysis change:

`We know what changed, why it changed, which artifacts prove it, which risks were checked, and whether the change is safer or more useful than the previous baseline.`

Until that is true, Prism should continue to be treated as an internal research assistant, not a product-ready stock-analysis system.

## 15. Operational Usage

The first executable baseline should be used in three modes.

### 15.1 Report-Only Baseline Refresh

Use this when freezing the latest baseline scorecard without enforcing a release threshold.

Preferred one-click command:

```bash
./start_stock_evaluation.sh
```

Equivalent direct command:

```bash
./.venv/bin/python apps/scripts/evaluate_stock_analysis.py \
  --manifest data/evaluation/stock_analysis/manifest.json \
  --output-json data/evaluation/stock_analysis/latest_scorecard.json \
  --output-md data/history/reports/evaluation/prism_stock_analysis_evaluation_latest.md
```

Expected behavior:

- exit code `0`
- refreshed JSON scorecard
- refreshed Markdown report
- explicit `next_tier` and `next_tier_requirements`

### 15.2 Professional-Usable Acceptance Gate

Use this for most near-term Prism changes that alter rules, scoring, loaders, or command-brief output.

Preferred one-click command:

```bash
./start_stock_evaluation.sh professional
```

Equivalent direct command:

```bash
./.venv/bin/python apps/scripts/evaluate_stock_analysis.py \
  --manifest data/evaluation/stock_analysis/manifest.json \
  --output-json /tmp/prism_eval.json \
  --output-md /tmp/prism_eval.md \
  --min-tier professional_usable \
  --fail-on-hard-gates
```

Expected behavior:

- exit code `0` only if the result remains at least `professional_usable`
- exit code `2` if tier regresses below `professional_usable`
- exit code `2` if any non-expected hard gate fails

### 15.3 Product-Ready Stretch Gate

Use this only when evaluating whether Prism is ready for broader product exposure.

Preferred one-click command:

```bash
./start_stock_evaluation.sh product
```

Equivalent direct command:

```bash
./.venv/bin/python apps/scripts/evaluate_stock_analysis.py \
  --manifest data/evaluation/stock_analysis/manifest.json \
  --output-json /tmp/prism_eval_product.json \
  --output-md /tmp/prism_eval_product.md \
  --min-tier product_ready \
  --fail-on-hard-gates
```

Interpretation:

- if this command fails, the JSON and Markdown outputs should still be reviewed
- `next_tier_requirements` should be treated as the minimum remediation list
- passing this command is necessary but still not sufficient for external launch, because legal, compliance, and user-safety framing are outside this benchmark
