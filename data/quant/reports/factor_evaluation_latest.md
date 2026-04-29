# Prism Quant Sprint 2 Factor Evaluation

Generated at: 2026-04-29T21:40:27+08:00

Scope: report-only factor evaluation. This report does not change production sorting, A/B/C tiers, pages, Prism Edge, or any trading action.

## Dataset

- Joined available research-only label rows: 10818.
- Hardened labels input: `/Users/yangbishang/Projects/prism/data/quant/labels/forward_return_labels_hardened.jsonl`.
- Hardened labels count: 11064.
- Hardened formal_label_ready count: 0.
- Hardened formal_execution_eligible count: 0.
- Samples by source lane: {'research_backfill_ai_history': 4150, 'research_backfill_scan_history': 6668}.
- Excess returns are not computed because benchmark data is not frozen.
- `final_score` and `strategy_bucket` are excluded from formal evaluation.

## Hardened Label Status

- Benchmark status distribution: {'market_benchmark_unavailable': 216, 'market_benchmark_unavailable_internal_research_only_available': 10848}.
- Excess return status distribution: {'unavailable_market_benchmark_not_frozen': 11064}.
- Internal benchmark status distribution: {'research_only_internal_available': 10848, 'unavailable': 216}.
- Price adjustment status distribution: {'unknown': 11064}.
- Formal adjusted return status distribution: {'unavailable_adjustment_policy_missing_not_ready': 11064}.
- Execution realism status distribution: {'not_ready_research_only_simulation_execution_data_missing': 11064}.
- Research-only reason distribution: {'adjustment_policy_missing': 11064, 'execution_data_missing': 11064, 'execution_not_formal': 11064, 'execution_realism_not_ready': 11064, 'formal_adjusted_return_unavailable': 11064, 'internal_benchmark_research_only_not_formal': 10848, 'internal_benchmark_unavailable_for_window': 216, 'market_benchmark_unavailable': 11064, 'raw_return_unavailable': 246, 'source_label_unavailable': 246}.
- Positive-looking raw/net metrics remain `research_only`; no formal excess, adjusted, or execution-realistic return is emitted.

## Formal Numeric Factors

| Field | Samples | Status | Best visible 5D next_open net mean | Notes |
| --- | ---: | --- | ---: | --- |
| `ai_priority_score` | 4038 | research_only | -0.24% | AI lane ranking score; formal only within AI lane. |
| `ai_best_score` | 4150 | research_only | -0.26% | AI lane best underlying strategy score. |
| `scan_capital_score` | 6668 | research_only | -0.02% | Raw scan `scores.capital` adapter field. |
| `scan_technical_score` | 6668 | research_only | -0.02% | Raw scan `scores.technical` adapter field. |

## Group Factors

| Field | Samples | Status | Notes |
| --- | ---: | --- | --- |
| `tier` | 4150 | research_only | AI lane A/B/C only; not a replacement for production tiers. |
| `execution_gate_status` | 10818 | research_only | Batch/context join; not candidate-native. |
| `setup_type` | 4150 | research_only | AI setup grouping; weak buckets are insufficient_sample. |
| `theme` | 10818 | research_only | Coverage/grouping only; no strong conclusion. |

## Group Bucket Sample Guardrails

| Field | Insufficient bucket combos | Examples |
| --- | ---: | --- |
| `tier` | 16 | next_close/1D `A` n=14; next_close/1D `B` n=20; next_close/3D `A` n=14; next_close/3D `B` n=20; next_close/5D `A` n=14; ... +11 more |
| `execution_gate_status` | 0 | none |
| `setup_type` | 16 | next_close/1D `missing` n=14; next_close/1D `watch_only` n=11; next_close/3D `missing` n=14; next_close/3D `watch_only` n=11; next_close/5D `missing` n=14; ... +11 more |
| `theme` | 40 | next_close/1D `AI硬件链` n=23; next_close/1D `建材链` n=12; next_close/1D `新能源链` n=11; next_close/1D `消费电子链` n=7; next_close/1D `电网设备链` n=7; ... +35 more |

## Tier Monotonicity

| Entry | Window | Status | Monotonic status | A n/mean | B n/mean | C n/mean |
| --- | ---: | --- | --- | ---: | ---: | ---: |
| next_close | 1 | insufficient_sample | insufficient_sample | 14/-0.20% | 20/-0.20% | 495/-0.20% |
| next_close | 3 | insufficient_sample | insufficient_sample | 14/-3.73% | 20/0.44% | 495/0.01% |
| next_close | 5 | insufficient_sample | insufficient_sample | 14/-5.57% | 20/-1.65% | 495/-0.09% |
| next_close | 10 | insufficient_sample | insufficient_sample | 14/-2.42% | 20/2.87% | 454/0.21% |
| next_open | 1 | insufficient_sample | insufficient_sample | 14/0.58% | 20/1.08% | 495/-0.22% |
| next_open | 3 | insufficient_sample | insufficient_sample | 14/-2.93% | 20/1.82% | 495/-0.03% |
| next_open | 5 | insufficient_sample | insufficient_sample | 14/-4.82% | 20/-0.29% | 495/-0.13% |
| next_open | 10 | insufficient_sample | insufficient_sample | 14/-1.74% | 20/4.29% | 454/0.28% |

## Execution Gate Evaluation

Execution gate is evaluated only as `execution_gate_scope=batch_context`; it is not treated as a candidate-native field.

Representative combo: `next_open` / 5D.

| Bucket | Samples | Status | Net mean | Win rate |
| --- | ---: | --- | ---: | ---: |
| `limited` | 177 | research_only | 0.03% | 41.24% |
| `off` | 1045 | research_only | -0.09% | 41.24% |
| `on` | 161 | research_only | -0.40% | 37.27% |

## AI Screening Validation

| Entry | Window | Status | Scan n/net mean | AI n/net mean | Same-day code overlap |
| --- | ---: | --- | ---: | ---: | ---: |
| next_close | 1 | research_only | 854/-0.20% | 529/-0.20% | 515 |
| next_close | 3 | research_only | 854/0.01% | 529/-0.08% | 515 |
| next_close | 5 | research_only | 854/-0.08% | 529/-0.29% | 515 |
| next_close | 10 | research_only | 772/0.94% | 488/0.24% | 474 |
| next_open | 1 | research_only | 854/-0.12% | 529/-0.15% | 515 |
| next_open | 3 | research_only | 854/0.07% | 529/-0.03% | 515 |
| next_open | 5 | research_only | 854/-0.02% | 529/-0.26% | 515 |
| next_open | 10 | research_only | 772/1.10% | 488/0.39% | 474 |

- Selection-bias guardrail: comparison is scan-pool anchored where lineage is visible; unmatched AI/scan lineage remains report-only.

## Midday Validation

- Status: insufficient_sample.
- Stage counts with formal labels: {}.
- Confirmed/downgraded/fresh candidates remain coverage-only until enough PIT-clean labeled samples exist.

## Raw/Source Only

- Raw/source fields retained for diagnostics only: `score`, `strategy_hits`, `strategy_labels`, `execution_quality_score`, `watchlist_technical_score`, `midday_score`.
- Excluded fields: `final_score`, `strategy_bucket`, `excess_return`, `execution_realistic_return`.

| Field | Samples | Coverage | Status | Lane / kind guardrail |
| --- | ---: | ---: | --- | --- |
| `score` | 6668 | 61.64% | raw_source_only | lanes={'research_backfill_scan_history': 6668}; score_kinds={'raw_scan_composite_score': 6668} |
| `strategy_hits` | 10706 | 98.96% | raw_source_only | lanes={'research_backfill_ai_history': 4038, 'research_backfill_scan_history': 6668} |
| `strategy_labels` | 4150 | 38.36% | raw_source_only | lanes={'research_backfill_ai_history': 4150} |
| `execution_quality_score` | 0 | 0.00% | raw_source_only | lanes={} |
| `watchlist_technical_score` | 0 | 0.00% | raw_source_only | lanes={} |
| `midday_score` | 0 | 0.00% | raw_source_only | lanes={} |

`score` remains lane-scoped and score-kind-scoped; it is not merged across lanes or promoted to a formal factor.

## Guardrails

- All conclusions are report-only.
- Buckets below 30 samples are `insufficient_sample` and receive no positive conclusion.
- No excess return is calculated or claimed.
- No production sorting, A/B/C replacement, page, Prism Edge, theme state machine, or ML change is made.
