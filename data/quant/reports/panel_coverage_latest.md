# Prism Quant Sprint 1 Panel Coverage

Generated at: 2026-04-28T21:53:59+08:00

Scope: Sprint 1 research panel only. No production sorting, no A/B/C replacement, no factor conclusion, and no backtest conclusion.

## Outputs

- Daily signal panel rows: 3896.
- Eligible universe snapshot rows: 2958.
- Pipeline stage ledger rows: 3896.

## Lane Coverage

| Source lane | Rows |
| --- | ---: |
| `screener_scan_stale_outputs` | 1005 |
| `research_backfill_scan_history` | 854 |
| `screener_ai_history` | 692 |
| `research_backfill_ai_history` | 529 |
| `screener_ai_stale_outputs` | 405 |
| `command_brief_json` | 265 |
| `watchlist_daily_snapshots` | 58 |
| `midday_verification_stale_outputs` | 46 |
| `screener_scan_current` | 26 |
| `screener_ai_current` | 13 |
| `midday_verification_current` | 3 |

## Pipeline Stage Coverage

| Stage | Rows |
| --- | ---: |
| `scan_candidate` | 1885 |
| `ai_screened` | 1512 |
| `command_brief_screener` | 192 |
| `shortlisted` | 127 |
| `command_brief_watchlist` | 67 |
| `watchlist` | 58 |
| `midday_checked` | 17 |
| `fresh_candidate` | 15 |
| `downgraded` | 13 |
| `command_brief_midday_fresh` | 6 |
| `confirmed` | 4 |

## Field Coverage

| Field | Non-null rows | Coverage | Notes |
| --- | ---: | ---: | --- |
| `score` | 1998/3896 | 51.3% | lane-scoped; do not merge across lanes |
| `score_kind` | 1998/3896 | 51.3% | lane-scoped; do not merge across lanes |
| `ai_priority_score` | 1704/3896 | 43.7% |  |
| `ai_best_score` | 1831/3896 | 47.0% |  |
| `scan_capital_score` | 1885/3896 | 48.4% | mapped from raw scan `scores.*` |
| `scan_technical_score` | 1885/3896 | 48.4% | mapped from raw scan `scores.*` |
| `execution_gate_status` | 3472/3896 | 89.1% | batch/context join; not candidate-native |
| `theme` | 3737/3896 | 95.9% |  |
| `setup_type` | 1611/3896 | 41.4% |  |

## PIT And Quality

- PIT status: {'pass': 3896}.
- Top data quality flags: {'final_score_not_used_sprint1': 3896, 'execution_gate_context_missing': 244, 'watchlist_no_formal_forward_label': 58, 'midday_no_formal_forward_label': 49}.
- Every row carries `source_artifact`, `source_hash`, `source_lane`, `signal_timestamp`, `available_timestamp`, and `decision_timestamp`.
- `final_score` is intentionally absent from panel rows. AI lane uses `ai_priority_score` / `ai_best_score`; raw scan uses namespaced scan scores.

## Sprint 1 Guardrails

- `score` is retained only with `source_lane` and `score_kind`.
- `execution_gate_status` is joined as `execution_gate_scope=batch_context`.
- 2026 artifacts are included for panel coverage only; they are excluded from formal forward label generation.
