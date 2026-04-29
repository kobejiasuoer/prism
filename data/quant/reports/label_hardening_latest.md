# Prism Quant P1-A Card 4 Label Hardening

Generated at: 2026-04-29T21:25:55+08:00

Scope: P1-A Card 4 only. This report describes a hardened label sidecar; it does not overwrite original forward labels, generate formal labels, execution-realistic returns, formal excess returns, or rerun factor/backtest/health reports.

## Summary

- Production impact: `none`.
- Source labels: 11064.
- Hardened labels: 11064.
- Formal label ready count: 0.
- Formal execution eligible count: 0.
- All hardened labels remain research-only or unavailable; none are production-ready.

## Status Distributions

- Benchmark status: {'market_benchmark_unavailable_internal_research_only_available': 10848, 'market_benchmark_unavailable': 216}.
- Benchmark return status: {'unavailable_market_benchmark_not_frozen': 11064}.
- Excess return status: {'unavailable_market_benchmark_not_frozen': 11064}.
- Internal benchmark status: {'research_only_internal_available': 10848, 'unavailable': 216}.
- Price adjustment status: {'unknown': 11064}.
- Formal adjusted return status: {'unavailable_adjustment_policy_missing_not_ready': 11064}.
- Execution realism status: {'not_ready_research_only_simulation_execution_data_missing': 11064}.
- Label quality status: {'research_only_hardened_not_formal': 10818, 'unavailable_hardened_not_formal': 246}.

## Research-Only Reasons

| Reason | Rows |
| --- | ---: |
| `adjustment_policy_missing` | 11064 |
| `execution_data_missing` | 11064 |
| `execution_not_formal` | 11064 |
| `execution_realism_not_ready` | 11064 |
| `formal_adjusted_return_unavailable` | 11064 |
| `internal_benchmark_research_only_not_formal` | 10848 |
| `internal_benchmark_unavailable_for_window` | 216 |
| `market_benchmark_unavailable` | 11064 |
| `raw_return_unavailable` | 246 |
| `source_label_unavailable` | 246 |

## Capability Status

| Capability | Status |
| --- | --- |
| `raw_return` | `available_for_research_only_when_source_label_available` |
| `internal_equal_weight_benchmark` | `available_research_only_internal_for_matching_windows` |
| `CSI500_market_benchmark` | `unavailable` |
| `HS300_market_benchmark` | `unavailable` |
| `formal_market_excess_return` | `unavailable` |
| `formal_adjusted_return` | `unavailable` |
| `execution_realistic_return` | `unavailable` |
| `partial_fill` | `deferred` |
| `suspend_status` | `unavailable` |
| `limit_up_down_status` | `unavailable` |
| `failed_order` | `unavailable` |

## Hardening Inputs

| Input | Path | Hash |
| --- | --- | --- |
| `source_labels` | `data/quant/labels/forward_return_labels.jsonl` | `857542478ff8` |
| `benchmark_manifest` | `data/quant/benchmarks/benchmark_manifest.json` | `e8c9533b06e1` |
| `benchmark_returns` | `data/quant/benchmarks/benchmark_returns.jsonl` | `bd83ce968e57` |
| `price_adjustment_manifest` | `data/quant/price/price_adjustment_manifest.json` | `4e119abc9e8b` |
| `execution_flags_manifest` | `data/quant/execution/execution_flags_manifest.json` | `a77fc83fed44` |

## Interpretation

- CSI500 and HS300 remain unavailable, so formal market excess return remains unavailable.
- Eligible universe equal-weight is carried only as `research_only_internal_benchmark`; it is not a formal market benchmark.
- Raw returns are preserved but are not adjusted returns.
- Adjustment policy remains unknown, so formal adjusted return is not ready.
- Execution data remains missing, so execution-realistic return is not ready.
- The hardened sidecar is suitable for a future report-only Sprint 2 rerun, but such rerun must preserve all research-only guardrails until benchmark, adjusted price, and execution data are actually complete.

## Guardrails

- `report_only`
- `research_only_hardened_labels`
- `no_original_label_overwrite`
- `no_formal_label_ready_upgrade`
- `no_formal_excess_return`
- `no_execution_realistic_return`
- `no_internal_benchmark_as_market_benchmark`
- `no_raw_return_as_adjusted_return`
- `no_production_sorting`
- `no_abc_replacement`
- `no_page`
- `no_prism_edge`
- `no_expected_5d_frontend`
- `no_ml`
- `no_factor_backtest_health_rerun`
