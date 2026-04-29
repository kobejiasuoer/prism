# Prism Quant Sprint 0 Field Mapping Audit

Generated at: 2026-04-28T18:05:29+08:00

Scope: Sprint 0 audit only. This report does not define production ranking, does not replace A/B/C, and does not promote any new quant field into production decisions.

## Coverage Summary

- Signal artifact files scanned: 299. Evaluation scorecards are referenced in the manifest but excluded from row-level signal coverage.
- Candidate-like signal records scanned: 9429.
- Exact coverage means the audited key exists directly on the candidate row. Semantic coverage also counts known local equivalents such as `scores.capital`, `scores.technical`, `execution_gate.status`, `themes`, and strategy hit lists.

| Field | Artifact key coverage | Record exact coverage | Record semantic coverage | P0 status |
| --- | ---: | ---: | ---: | --- |
| `score` | 294/299 (98.3%) | 7517/9429 (79.7%) | 7517/9429 (79.7%) | candidate, lane-scoped only |
| `priority_score` | 163/299 (54.5%) | 1744/9429 (18.5%) | 1744/9429 (18.5%) | candidate for AI lane only |
| `best_score` | 163/299 (54.5%) | 1871/9429 (19.8%) | 1871/9429 (19.8%) | candidate for AI lane only |
| `final_score` | 0/299 (0.0%) | 0/9429 (0.0%) | 0/9429 (0.0%) | blocked until adapter maps it explicitly |
| `tier` | 170/299 (56.9%) | 1905/9429 (20.2%) | 1905/9429 (20.2%) | research-only; AI lane strongest |
| `execution_gate_status` | 152/299 (50.8%) | 0/9429 (0.0%) | 5390/9429 (57.2%) | candidate as batch-level context, not row field |
| `execution_quality` | 83/299 (27.8%) | 3399/9429 (36.0%) | 3399/9429 (36.0%) | research-only; weak 2024 coverage |
| `capital_score` | 270/299 (90.3%) | 0/9429 (0.0%) | 2958/9429 (31.4%) | candidate only via scores.capital adapter |
| `technical_score` | 0/299 (0.0%) | 0/9429 (0.0%) | 2958/9429 (31.4%) | candidate only via scores.technical adapter |
| `theme` | 275/299 (92.0%) | 7459/9429 (79.1%) | 9203/9429 (97.6%) | research-only grouping after normalization |
| `setup_type` | 158/299 (52.8%) | 5731/9429 (60.8%) | 5731/9429 (60.8%) | research-only; AI/midday lane only |
| `strategy_bucket` | 0/299 (0.0%) | 0/9429 (0.0%) | 6224/9429 (66.0%) | blocked as exact field; derive later from strategy_hits/path |

## Lane Coverage

| Lane | Records | Useful fields observed | Main gaps |
| --- | ---: | --- | --- |
| 2024 backfill AI | 1961 | `score` 73%, `execution_gate_status` 99%, `theme` 100%, `setup_type` 99%, `strategy_bucket` 100% | `final_score`, `execution_quality`, `capital_score`, `technical_score` |
| 2024 backfill scan | 854 | `score` 100%, `capital_score` 100%, `technical_score` 100%, `theme` 100% | `final_score`, `execution_quality`, `strategy_bucket` |
| 2026 AI history | 2469 | `score` 72%, `execution_gate_status` 75%, `execution_quality` 69%, `theme` 100%, `setup_type` 85%, `strategy_bucket` 100% | `final_score`, `capital_score`, `technical_score` |
| 2026 AI stale | 1513 | `score` 73%, `execution_gate_status` 92%, `execution_quality` 93%, `theme` 100%, `setup_type` 92%, `strategy_bucket` 100% | `final_score`, `capital_score`, `technical_score` |
| Current AI | 49 | `score` 73%, `execution_gate_status` 100%, `execution_quality` 100%, `theme` 100%, `setup_type` 100%, `strategy_bucket` 100% | `final_score`, `capital_score`, `technical_score` |
| 2026 scan stale | 2048 | `score` 100%, `capital_score` 100%, `technical_score` 100%, `theme` 100% | `final_score`, `execution_quality`, `strategy_bucket` |
| Current scan | 56 | `score` 100%, `capital_score` 100%, `technical_score` 100%, `theme` 100% | `final_score`, `execution_quality`, `strategy_bucket` |
| Current midday | 3 | `score` 100%, `theme` 100% | `final_score`, `execution_quality`, `capital_score`, `technical_score`, `strategy_bucket` |
| Midday stale | 46 | `tier` 74% | `final_score`, `execution_quality`, `capital_score`, `technical_score`, `strategy_bucket` |
| Watchlist snapshots | 58 | `score` 98% | `final_score`, `execution_quality`, `capital_score`, `technical_score`, `strategy_bucket` |
| Command brief | 372 | `priority_score` 62%, `best_score` 62%, `tier` 62%, `execution_quality` 64%, `theme` 64%, `setup_type` 64%, `strategy_bucket` 62% | `final_score`, `capital_score`, `technical_score` |

## Semantic Findings

- `score`: overloaded. In scan artifacts it is the persisted final scan score built from technical, capital, emotion, fundamental and penalties. In watchlist snapshots it is a technical watchlist score (`score_kind` is `技术分`). In midday fresh candidates it is a lightweight intraday candidate score. It can enter P0 only as lane-scoped factors such as `scan_score` or `watchlist_technical_score`, not as one universal score.
- `priority_score`: AI shortlist ranking score. The code adds `best_score`, strategy count, approved hits, execution quality, and consistency. It is suitable for AI-lane factor evaluation after PIT and label coverage, but coverage is not universal.
- `best_score`: best underlying strategy score after AI deduplication. It is closer to the raw scan score than `priority_score`; it should be evaluated separately from `priority_score`.
- `final_score`: no exact persisted field was found in the scanned signal artifacts. `scan.py` computes `final_score` internally but writes it out as `score` in scan outputs. Formal P0 conclusions must not assume `final_score` exists until the Sprint 1 adapter maps it explicitly.
- `tier`: present mainly in AI shortlist and related command brief/midday downgrade rows. It is not available for raw scan or watchlist rows, so A/B/C monotonicity can only be tested on AI-lane samples unless future adapters add stable lineage.
- `execution_gate_status`: appears as batch-level `screening_summary.execution_gate_status` or candidate-level `execution_gate.status`, not as a direct candidate key. P0 may attach it as run context, but it must not be treated as a row-native field without provenance.
- `execution_quality`: strongest in 2026 AI outputs and command briefs, absent from the 2024 backfill AI shortlist. It is research-only until 2024 backfill parity exists or analysis is explicitly restricted to the 2026 lane.
- `capital_score` / `technical_score`: exact keys are absent on candidate rows. Raw scan rows carry `scores.capital` and `scores.technical`; market theme rows also contain a different `components.capital_score` meaning. These require adapter namespacing before P0 factor work.
- `theme`: high semantic coverage, but values appear as a single `theme`, a `themes` list, and market-level theme tables. `其他` is common and should be treated as a normalized category with dilution risk.
- `setup_type`: mostly AI/midday. Raw scan has technical state and trade notes but no exact setup type. Setup analysis is therefore AI-lane research-only in P0.
- `strategy_bucket`: no exact key exists. AI rows expose `strategy_hits` / `strategy_labels`; raw scan strategy membership can be inferred from the strategy path. This is a later adapter task, not a Sprint 0 field.

## Fields Allowed Into P0 Research

- Can enter P0 after adapter namespacing and PIT checks: `score` as lane-scoped score, `priority_score`, `best_score`, `tier`, `execution_gate_status` as batch context, `capital_score` via `scores.capital`, `technical_score` via `scores.technical`, `theme`, and `setup_type`.
- Research-only until coverage improves: `execution_quality` because 2024 backfill coverage is missing, and `theme` where it is only market-level or list-valued.
- Blocked from formal conclusions in current form: `final_score` and `strategy_bucket` as exact fields. They need an explicit adapter contract before Sprint 1/2 can use them.

## Gaps To Carry Forward

- Build a canonical signal adapter that emits separate `scan_score`, `ai_best_score`, `ai_priority_score`, and optional `canonical_final_score` with source provenance.
- Attach batch-level `execution_gate_status` to each signal row with source artifact hash and available timestamp.
- Namespace `scores.capital` / `scores.technical` separately from market theme component scores.
- Add coverage tests so missing `final_score` does not silently become zero or alias to the wrong field.
