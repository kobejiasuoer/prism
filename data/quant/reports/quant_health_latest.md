# Prism Quant Sprint 2 Quant Health

Generated at: 2026-04-29T21:40:28+08:00

Scope: report-only quant health. This report does not block or alter production.

## Summary

- Overall status: `report_only_hardened_not_production_ready`.
- Production impact: `none`.
- PIT pass rate: 100.00%.
- Panel rows: 3896; label rows: 11064.
- Hardened labels input: `~/Projects/prism/data/quant/labels/forward_return_labels_hardened.jsonl`.
- Hardened labels count: 11064.
- Hardened formal_label_ready count: 0.
- Hardened formal_execution_eligible count: 0.
- Available label rate: 97.78%.

## Availability

- Benchmark availability: {'market_benchmark_unavailable': 216, 'market_benchmark_unavailable_internal_research_only_available': 10848}.
- Source label benchmark availability: {'benchmark_unavailable': 11064}.
- Excess return availability: {'unavailable_market_benchmark_not_frozen': 11064}.
- Adjusted return availability: {'status': 'not_ready', 'formal_adjusted_return_status': {'unavailable_adjustment_policy_missing_not_ready': 11064}, 'price_adjustment_status': {'unknown': 11064}}.
- Execution data availability: missing_for_execution_realistic_backtest.
- Execution realism availability: {'status': 'not_ready', 'execution_realism_status': {'not_ready_research_only_simulation_execution_data_missing': 11064}, 'formal_execution_eligible_count': 0}.
- Execution missing flags: {'adjustment_policy': 11064, 'suspend_status': 11064, 'limit_up_down_status': 11064, 'failed_order': 11064, 'partial_fill': 11064}.

## Hardened Label Status

- Price adjustment status: {'unknown': 11064}.
- Formal adjusted return status: {'unavailable_adjustment_policy_missing_not_ready': 11064}.
- Execution realism status: {'not_ready_research_only_simulation_execution_data_missing': 11064}.
- Research-only reasons: {'adjustment_policy_missing': 11064, 'execution_data_missing': 11064, 'execution_not_formal': 11064, 'execution_realism_not_ready': 11064, 'formal_adjusted_return_unavailable': 11064, 'internal_benchmark_research_only_not_formal': 10848, 'internal_benchmark_unavailable_for_window': 216, 'market_benchmark_unavailable': 11064, 'raw_return_unavailable': 246, 'source_label_unavailable': 246}.

## Evidence Status

- Numeric factor statuses: {'ai_priority_score': 'research_only', 'ai_best_score': 'research_only', 'scan_capital_score': 'research_only', 'scan_technical_score': 'research_only'}.
- Group factor statuses: {'tier': 'research_only', 'execution_gate_status': 'research_only', 'setup_type': 'research_only', 'theme': 'research_only'}.
- Tier monotonicity status: `insufficient_sample`.
- Gate evaluation status: `research_only`.
- Backtest status: `research_only_simulation`.
- Backtest result status counts: {'research_only': 16}.
- Portfolio win-rate status counts: {'research_only': 8, 'insufficient_sample': 8}.

## Report-Only Gates

- Production blocking: false.
- Sorting impact: false.
- A/B/C replacement: false.
- Page requirement: false.

## Guardrails

- No production sorting changes.
- No A/B/C replacement.
- No page, Prism Edge, Expected 5D frontend, theme state machine, or ML work.
