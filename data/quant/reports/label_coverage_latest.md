# Prism Quant Sprint 1 Label Coverage

Generated at: 2026-04-28T21:53:59+08:00

Scope: raw/net forward labels for 2024 research backfill only. Excess returns are deferred because benchmark series are not frozen.

## Summary

- Panel rows eligible for first label pass: 1383.
- Label rows written: 11064.
- Available research-only labels: 10818/11064 (97.8%).
- Unavailable label rows: 246/11064 (2.2%).
- 2026/current/non-backfill panel rows excluded from formal label evaluation: 2513.

## Entry Model Coverage

| Entry model | Available | Unavailable |
| --- | ---: | ---: |
| `next_close` | 5409 | 123 |
| `next_open` | 5409 | 123 |

## Holding Window Coverage

| Holding window | Available | Unavailable |
| --- | ---: | ---: |
| 1 | 2766 | 0 |
| 3 | 2766 | 0 |
| 5 | 2766 | 0 |
| 10 | 2520 | 246 |

## Execution Data Missing Flags

- Missing execution data flags on label rows: {'adjustment_policy': 11064, 'suspend_status': 11064, 'limit_up_down_status': 11064, 'failed_order': 11064, 'partial_fill': 11064}.
- Unavailable reasons: {'forward_price_missing': 246}.
- `benchmark_status=benchmark_unavailable` and `excess_return_status=deferred_until_benchmark_frozen` on every label row.
- `formal_execution_eligible=false` on every label row because adjustment, suspend, limit, failed order, and partial fill data are not frozen.

## Supported In First Version

- 2024 research backfill raw and net returns for `next_open` and `next_close` entry models.
- Holding windows from config: 1, 3, 5, and 10 observed trading rows.
- Configured bps costs are deducted into `net_return`; minimum commission is flagged unavailable because notional is absent.

## Not Supported In First Version

- Excess returns, adjusted-return conclusions, benchmark-relative conclusions, and execution-realistic fills.
- 2026 current operational forward labels; those rows remain panel/coverage only.
