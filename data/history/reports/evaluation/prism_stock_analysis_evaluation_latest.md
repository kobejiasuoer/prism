# Prism Stock Analysis Evaluation Report

- Generated At: 2026-04-23 23:21:50
- Baseline Label: 2026-04-23-initial-baseline
- Total Score: 97 / 100
- Tier: professional_usable

## Acceptance Verdict

- status: report_only
- required_tier: none
- fail_on_hard_gates: false
- hard_gates_clear: true
- passed: n/a

## Run Context

- manifest_path: data/evaluation/stock_analysis/manifest.json
- required_tier: none
- fail_on_hard_gates: false
- command: apps/scripts/evaluate_stock_analysis.py --manifest data/evaluation/stock_analysis/manifest.json --output-json data/evaluation/stock_analysis/latest_scorecard.json --output-md data/history/reports/evaluation/prism_stock_analysis_evaluation_latest.md

## Dimension Scores

- data_governance: 20 / 20
- analysis_rule_quality: 20 / 20
- execution_risk_control: 20 / 20
- output_usability: 15 / 15
- historical_validation: 12 / 15
- stability_productization: 10 / 10

## Hard Gate Failures

- none

## Expected Abnormal Failures

- abnormal_inputs::missing_midday_case::midday_confirmation: parse_error
- abnormal_inputs::missing_midday_case::midday_confirmation: unavailable

## Historical Validation

- aggressive_backtest_review_2026_04_15: loaded | score 8 | evidence: friction_adjusted, multi_horizon_metrics, gate_segmentation, environment_segmentation, tier_segmentation

## Historical Comparisons

- research_backfill_20240102_20240329_rerun_delta: loaded | score 4 | ai_overall_next_day_net_delta=+0.0700, ai_overall_day3_net_delta=-0.5300, ai_overall_day5_net_delta=-0.8800, weak_regime_ai_next_day_net_delta=+0.3800, weak_regime_ai_day5_net_delta=+0.5700

## Upgrade Gaps

- Next Tier: product_ready
- historical_validation needs 13/15 (current 12) for product_ready.

## Suites

### latest_trading_day

- expected_failures: false
- latest_operational_case: 0 hard-gate failures

### historical_normal

- expected_failures: false
- historical_command_brief_2026_04_16: 0 hard-gate failures
- historical_command_brief_2026_04_20: 0 hard-gate failures
- historical_command_brief_2026_04_21: 0 hard-gate failures

### weak_environment

- expected_failures: false
- weak_environment_2026_04_21_noon: 0 hard-gate failures
- weak_environment_2026_04_15_morning: 0 hard-gate failures

### abnormal_inputs

- expected_failures: true
- missing_midday_case: 2 hard-gate failures
