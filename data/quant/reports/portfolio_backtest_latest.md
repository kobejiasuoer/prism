# Prism Quant Sprint 2 Minimal Portfolio Backtest

Generated at: 2026-04-29T21:40:27+08:00

Scope: report-only minimal backtest. This is not an execution-realistic backtest and does not change production sorting.

## Inputs

- Hardened labels input: `/Users/yangbishang/Projects/prism/data/quant/labels/forward_return_labels_hardened.jsonl`.
- Hardened labels count: 11064.
- Hardened formal_label_ready count: 0.
- Hardened formal_execution_eligible count: 0.
- Input scan label rows: 6668.
- Strategies: `top_n_raw_score`, `gate_filtered_top_n`.
- Entry models: `next_open`, `next_close`.
- Holding windows: [1, 3, 5, 10].
- Max positions: 5; max single position: 20.0%.
- Transaction cost config: {'currency': 'CNY', 'buy_commission_bps': 2.5, 'sell_commission_bps': 2.5, 'minimum_commission_cny': 5.0, 'stamp_tax_bps': 5.0, 'slippage_bps': 5.0, 'impact_cost': {'enabled': False, 'placeholder_bps': 0.0, 'notes': 'Sprint 0 records the configuration surface only; impact model calibration is deferred.'}}.
- Gate counts in input rows: {'off': 5028, 'limited': 904, 'on': 736}.
- Portfolio win rate basis: invested rebalance days with positions > 0 and net portfolio return after costs > 0; zero-position gate-off days are excluded.

## Hardened Label Limitations

- Benchmark status distribution: {'market_benchmark_unavailable': 216, 'market_benchmark_unavailable_internal_research_only_available': 10848}.
- Excess return status distribution: {'unavailable_market_benchmark_not_frozen': 11064}.
- Internal benchmark status distribution: {'research_only_internal_available': 10848, 'unavailable': 216}.
- Price adjustment status distribution: {'unknown': 11064}.
- Execution realism status distribution: {'not_ready_research_only_simulation_execution_data_missing': 11064}.
- Research-only reason distribution: {'adjustment_policy_missing': 11064, 'execution_data_missing': 11064, 'execution_not_formal': 11064, 'execution_realism_not_ready': 11064, 'formal_adjusted_return_unavailable': 11064, 'internal_benchmark_research_only_not_formal': 10848, 'internal_benchmark_unavailable_for_window': 216, 'market_benchmark_unavailable': 11064, 'raw_return_unavailable': 246, 'source_label_unavailable': 246}.
- No sample with `formal_label_ready=false` is used to claim a formal or execution-realistic backtest.

## Results

| Strategy | Entry | Window | Trade days | Positions | Status | Raw mean | Net mean | Portfolio win rate | Drawdown | Avg turnover | Avg cost paid | Flags |
| --- | --- | ---: | ---: | ---: | --- | ---: | ---: | --- | ---: | ---: | ---: | --- |
| `top_n_raw_score` | `next_open` | 1 | 57 | 276 | research_only | 0.45% | 0.26% | 56.14% (n=57, research_only) | -15.32% | 0.4912 | 0.19% | research_only_simulation, benchmark_unavailable, adjustment_policy_unknown |
| `top_n_raw_score` | `next_open` | 3 | 57 | 276 | research_only | 0.81% | 0.61% | 56.14% (n=57, research_only) | -42.78% | 0.4912 | 0.19% | research_only_simulation, benchmark_unavailable, adjustment_policy_unknown |
| `top_n_raw_score` | `next_open` | 5 | 57 | 276 | research_only | 0.54% | 0.35% | 52.63% (n=57, research_only) | -56.98% | 0.4912 | 0.19% | research_only_simulation, benchmark_unavailable, adjustment_policy_unknown |
| `top_n_raw_score` | `next_open` | 10 | 53 | 257 | research_only | 1.38% | 1.19% | 43.40% (n=53, research_only) | -78.24% | 0.5057 | 0.19% | research_only_simulation, benchmark_unavailable, adjustment_policy_unknown |
| `top_n_raw_score` | `next_close` | 1 | 57 | 276 | research_only | 0.00% | -0.19% | 0.00% (n=57, research_only) | -10.46% | 0.4912 | 0.19% | research_only_simulation, benchmark_unavailable, adjustment_policy_unknown |
| `top_n_raw_score` | `next_close` | 3 | 57 | 276 | research_only | 0.37% | 0.17% | 47.37% (n=57, research_only) | -42.00% | 0.4912 | 0.19% | research_only_simulation, benchmark_unavailable, adjustment_policy_unknown |
| `top_n_raw_score` | `next_close` | 5 | 57 | 276 | research_only | 0.08% | -0.11% | 47.37% (n=57, research_only) | -56.60% | 0.4912 | 0.19% | research_only_simulation, benchmark_unavailable, adjustment_policy_unknown |
| `top_n_raw_score` | `next_close` | 10 | 53 | 257 | research_only | 0.75% | 0.55% | 37.74% (n=53, research_only) | -77.62% | 0.5057 | 0.19% | research_only_simulation, benchmark_unavailable, adjustment_policy_unknown |
| `gate_filtered_top_n` | `next_open` | 1 | 57 | 35 | research_only | 0.13% | 0.11% | 50.00% (n=10, insufficient_sample) | -2.54% | 0.0702 | 0.02% | research_only_simulation, benchmark_unavailable, adjustment_policy_unknown |
| `gate_filtered_top_n` | `next_open` | 3 | 57 | 35 | research_only | 0.10% | 0.07% | 50.00% (n=10, insufficient_sample) | -12.19% | 0.0702 | 0.02% | research_only_simulation, benchmark_unavailable, adjustment_policy_unknown |
| `gate_filtered_top_n` | `next_open` | 5 | 57 | 35 | research_only | -0.06% | -0.08% | 50.00% (n=10, insufficient_sample) | -17.89% | 0.0702 | 0.02% | research_only_simulation, benchmark_unavailable, adjustment_policy_unknown |
| `gate_filtered_top_n` | `next_open` | 10 | 53 | 35 | research_only | 0.50% | 0.47% | 60.00% (n=10, insufficient_sample) | -24.12% | 0.0755 | 0.03% | research_only_simulation, benchmark_unavailable, adjustment_policy_unknown |
| `gate_filtered_top_n` | `next_close` | 1 | 57 | 35 | research_only | 0.00% | -0.02% | 0.00% (n=10, insufficient_sample) | -1.39% | 0.0702 | 0.02% | research_only_simulation, benchmark_unavailable, adjustment_policy_unknown |
| `gate_filtered_top_n` | `next_close` | 3 | 57 | 35 | research_only | -0.03% | -0.06% | 40.00% (n=10, insufficient_sample) | -11.97% | 0.0702 | 0.02% | research_only_simulation, benchmark_unavailable, adjustment_policy_unknown |
| `gate_filtered_top_n` | `next_close` | 5 | 57 | 35 | research_only | -0.19% | -0.21% | 40.00% (n=10, insufficient_sample) | -17.70% | 0.0702 | 0.02% | research_only_simulation, benchmark_unavailable, adjustment_policy_unknown |
| `gate_filtered_top_n` | `next_close` | 10 | 53 | 35 | research_only | 0.35% | 0.32% | 50.00% (n=10, insufficient_sample) | -23.95% | 0.0755 | 0.03% | research_only_simulation, benchmark_unavailable, adjustment_policy_unknown |

## Conservative Interpretation

- Every result is `research_only_simulation` because suspend, limit up/down, failed order, partial fill, and adjustment data are unavailable.
- Benchmark data is unavailable, so no excess return is calculated or claimed.
- `gate_filtered_top_n` uses `execution_gate_status` only as batch/context. Gate off opens no new simulated positions; gate limited halves the max positions.
- Turnover is an approximate daily one-way new-weight measure, not a broker execution ledger.

## Guardrails

- Do not use these results to alter production sorting or A/B/C tiers.
- Do not describe this as deployable or execution-realistic.
- Buckets below 30 position observations are `insufficient_sample`.
