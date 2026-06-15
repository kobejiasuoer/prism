# Tushare Factor Layer — Deep Usage Design

**Date:** 2026-05-30
**Stage:** "Tushare 数据深度使用" (turn already-ingested Tushare data into decision capability)
**Status:** Approved design, pending spec review → implementation plan

## 1. Problem & Goal

Prism has already ingested and persisted Tushare/tinyshare datasets (22/22 available,
~20 tushare-ready). The data is **not yet feeding the scan / explanation / review-learning
loop** — it is largely display-only. The goal is to turn these datasets into system decision
capability across three directions, **without** loosening any real-money safety gate:

1. **Smarter scanner** — a Tushare factor layer that participates in observe/candidate-pool
   scoring (not just display).
2. **Explainable conclusions** — candidate cards, candidate detail, and the stock page explain
   *why* a stock is observed/avoided, sourced from real data fields.
3. **Learning samples** — persist a Tushare factor snapshot into the Decision Ledger and add a
   per-factor review/learning-loop scaffold.

## 2. Resolved Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Factor influence on pipeline | **Bounded re-rank** | Factors nudge ordering *within* the observe pool and risk_flags deprioritize; they never change `screening_status` (approved/caution/excluded) or any execution gate. |
| Scoring basis | **Hybrid** | Absolute bands for valuation/quality; pool-relative percentiles for ranking signals (capital-flow strength, turnover). Detail page shows absolute always + pool standing when in-pool. |
| `tushare_score` placement | **Separate signal** | Kept out of the existing `final_score` composite so it cannot disturb technical/capital scoring or its centralization test. Influences ranking only via a bounded `priority_score` nudge. |
| Outcome windows | **Reuse T+1/T+3/T+5** | Dragon-Tiger T+10 stat deferred to avoid expanding `OUTCOME_WINDOWS` + evaluator + tests. |
| Decision record schema | **Bump `SCHEMA_VERSION`** | Record grows a `factor_snapshot` key; old records lack it and readers `.get()` defensively. |

## 3. Architecture

One **factor core**, three **consumers**, safety enforced by structure (factor data never enters
the readiness/account/decision-contract code paths).

```
            packages/screener/tushare_factors.py   ← NEW: single source of factor logic
            (reads datasets via prism_data READ path: get_dataset_repository().load_dataset — no network)
                     │
   ┌─────────────────┼──────────────────────┐
   ▼                 ▼                      ▼
 scan.py (Stage2)   data_assets.py         decision_ledger.py
 candidate factors   formal_data           factor_snapshot
 + pool re-rank      factor profile        (capture-time, immutable)
```

- `packages/screener` already depends on `prism_data`.
- `apps/control-panel` already imports `screener` transitively via `apps/scripts/prism_canonical.py`
  (`from screener.capital_flow_contract …`), so `from screener.tushare_factors import …` is the seam.
- **First implementation step:** verify this import path resolves at runtime from both `scan.py`
  and `data_assets.py` before building on it. If it does not, fall back to placing the core under
  `packages/prism_data/` (both layers already import `prism_data` cleanly).

### Public API of the factor core

```python
compute_factor_bundle(code: str, trade_date: str | None, *, pool_stats: PoolStats | None = None) -> FactorBundle
compute_pool_stats(factor_values: list[FactorValues]) -> PoolStats
```

- `compute_factor_bundle` uses absolute bands always; adds pool-relative standing when `pool_stats`
  is supplied. Fully fault-tolerant (see §7). Never raises on missing/NaN data.
- `compute_pool_stats` computes medians/percentiles for the pool-relative dimensions across a pool.

## 4. The `FactorBundle` contract

```jsonc
{
  "tushare_score": 0-100 | null,            // null only if data_completeness == 0
  "data_completeness": 0.0-1.0,             // fraction of dimensions with usable data
  "tushare_score_breakdown": {
    "<dimension>": { "score": num, "weight": num, "contribution": num, "detail": "str", "available": bool }
  },
  "factor_tags": ["低PE", "高ROE", "主力净流入", "沪深300成分", "龙虎榜活跃", "北向偏强", ...],
  "risk_flags": ["短线脉冲风险(龙虎榜机构净买)", "估值偏高", "资金净流出", "流动性偏弱", "数据缺失", ...],
  "explanation": {
    "entry_reason": "str",                  // 入池原因
    "upgrade_condition": "str",             // 升级条件
    "abandon_condition": "str",             // 放弃条件
    "supporting_evidence": ["str", ...],
    "counter_risks": ["str", ...],
    "evidence": {
      "fundamental":      { "values": {...}, "interpretation": "str", "available": bool },
      "capital":          { "values": {...}, "interpretation": "str", "available": bool },
      "trading_anomaly":  { "values": {...}, "interpretation": "str", "available": bool },
      "index_weight":     { "values": {...}, "interpretation": "str", "available": bool }
    }
  },
  "factor_snapshot": {                       // raw factor VALUES, persisted by the ledger
    "valuation":       { "pe_ttm": num|null, "pb": num|null },
    "liquidity":       { "turnover_rate": num|null, "volume_ratio": num|null },
    "capital_flow":    { "main_net_yi": num|null, "five_day_main_net_yi": num|null },
    "fundamentals":    { "roe": num|null, "roe_waa": num|null, "debt_to_assets": num|null, ... },
    "index_membership":[ { "index": "000300.SH", "weight": num } ],
    "top_list_activity":{ "hits_20d": int, "hits_60d": int },
    "top_inst_activity":{ "net_buy": num|null },
    "market_context":  { "north_money": num|null, "margin_balance": num|null }
  },
  "trade_date_used": "YYYY-MM-DD",           // partition actually read (may differ from requested)
  "pool_standing": { "<dimension>": "above_median|below_median|top_quartile|..." } | null
}
```

### Score dimensions (tunable constants in `tushare_factors.py`)

| Dimension | Weight | Basis | Inputs (dataset.column) |
|---|---|---|---|
| Quality | 25 | absolute | `financial.indicator`: roe, roe_waa, debt_to_assets, grossprofit_margin, netprofit_margin |
| Capital flow | 25 | pool-relative + absolute | `capital_flow.daily`: main_net_yi (today) + 5-day cumulative main_net_yi |
| Valuation | 20 | absolute bands | `valuation.daily`: pe_ttm, pb |
| Liquidity | 15 | pool-relative + absolute | `liquidity.daily`: turnover_rate, volume_ratio |
| Index membership | 10 | absolute | `index.weight`: presence + weight in 000300.SH / 000905.SH / 000852.SH |
| Dragon-Tiger activity | 5 | signal | `market.top_list` hits 20/60d + `market.top_inst` net_buy |

Missing dimensions → reweight survivors over available weight, lower `data_completeness`, emit a
`数据缺失` risk note. **Never fabricate** a score for a missing dimension.

**Explanation-only factors** (no hard scoring, per the brief): dividend (`corporate_action.dividend`),
shareholder concentration (`shareholder.top10`). Financial quality contributes to the Quality
dimension and to the `fundamental` evidence block.

## 5. Direction 1 — Smarter scanner (bounded re-rank)

Compute factors for the ~30 Stage-2 candidates inside `stage2_enrich`
([scan.py:1333-1402](packages/screener/scan.py)), two-pass:

1. Compute raw factor values per candidate → `compute_pool_stats` → re-score with pool standing.
2. Attach the `FactorBundle` to each candidate; write top-level `tushare_factor_pool_stats` into
   `scan_result.json`.

Wire the **four field projections** so factors survive end-to-end:

1. `scan.format_output` ([scan.py:2274-2317](packages/screener/scan.py)) — add `tushare_factors`
   per candidate + top-level `tushare_factor_pool_stats`.
2. `ai_screening.build_stock_entry` ([ai_screening.py:777](packages/screener/ai_screening.py)) +
   `aggregate_shortlist` ([ai_screening.py:969](packages/screener/ai_screening.py)) — carry
   `tushare_factors`; apply the **bounded** priority adjustment in `priority_score`
   ([ai_screening.py:1053](packages/screener/ai_screening.py)):
   `priority += clamp((tushare_score - 50) * k, -CAP, +CAP) - risk_flag_penalty`.
   `CAP` is small enough to re-order *within* the surfaced pool. It **does not** touch
   `screening_status` (approved/caution/excluded), so it cannot un-exclude a stock or bypass a gate.
3. `prism_canonical.normalize_candidate`
   ([prism_canonical.py:727](apps/scripts/prism_canonical.py)) — expose `tushare_factors` on the
   canonical candidate entity (also `normalize_confirmation_item`, `normalize_lifecycle_item` as needed).
4. `candidate_lifecycle.extract_shortlist`
   ([candidate_lifecycle.py:64](packages/screener/candidate_lifecycle.py)) — carry a slim summary
   (score + top tags) so lifecycle output keeps factor context.

New scoring constants live **inside `tushare_factors.py`** (self-contained), leaving
`packages/screener/parameters.py` and `tests/test_stock_parameters.py` untouched.

## 6. Direction 2 — Explainable conclusions

### Backend
- `build_screening_candidate_card` ([dashboard_data.py:4954](apps/control-panel/dashboard_data.py))
  and `build_confirmation_candidate_card` ([dashboard_data.py:5000](apps/control-panel/dashboard_data.py))
  → surface `tushare_score`, `factor_tags`, `risk_flags`, and a short explanation on the card.
- `build_candidate_detail_view` ([dashboard_data.py:8975](apps/control-panel/dashboard_data.py))
  → full breakdown + structured explanation.
- `build_stock_formal_data` ([data_assets.py:318](apps/control-panel/data_assets.py)) → call the
  factor core, add a `factor_profile` block (score, breakdown, tags, flags, explanation, four
  evidence blocks) into `formal_data`. Show absolute factors always + pool standing when the stock
  is in today's pool (read persisted `tushare_factor_pool_stats`).

### Frontend
- [types.ts](apps/web/src/lib/types.ts): new `TushareFactorProfile` interface; extend `StockListCard`
  (`tushare_score?`, `factor_tags?: string[]`, `risk_flags?: string[]`, `factor_explanation?`) and
  `StockFormalData` (typed `factor_profile?: TushareFactorProfile`).
- [discovery/page.tsx](apps/web/src/app/discovery/page.tsx): factor score chip + factor tags + risk
  flags in the existing badge cell (page.tsx:290-300); explanation near the "为什么入池" column
  (page.tsx:281-283); mirror into the mobile card (page.tsx:316-346).
- [stock/[code]/page.tsx](apps/web/src/app/stock/[code]/page.tsx): extend `FormalDataSnapshotPanel`
  (page.tsx:790-896) with a factor-score header, breakdown, tag/flag rows, and the four evidence
  blocks — reusing existing `Badge` / `MetricCard` / `EmptyState` / `displayText` / `recordField`.
  Missing → `数据缺失/不可用`. Trust still consumed only via `TrustBanner` (do not recompute).

## 7. Direction 3 — Ledger snapshot + per-factor learning scaffold

- `build_decision_record` ([decision_ledger.py:549-607](apps/control-panel/decision_ledger.py)) →
  new top-level `factor_snapshot` key (peer of `parameter_snapshot`). Thread through
  `build_decision_record_from_today_item` ([decision_ledger.py:969-1049](apps/control-panel/decision_ledger.py)).
  Captured **once** at first write (existing first-write-wins immutability in `upsert_decision`).
  Source: the candidate's persisted `tushare_factors` if the today_item carries it, else compute
  from datasets at the decision's trade_date. Bump `SCHEMA_VERSION` ([decision_ledger.py:126](apps/control-panel/decision_ledger.py)).
- New `build_factor_learning_loop(records)` — mirrors `build_rule_learning_loop`
  ([decision_ledger.py:2333-2458](apps/control-panel/decision_ledger.py)) but buckets *matured*
  decisions (those with outcome events) by factor dimension, reusing the **existing T+1/T+3/T+5
  outcomes**:
  - high ROE vs low ROE
  - low PB vs high PB
  - Dragon-Tiger institutional net-buy (yes/no)
  - north-bound strong/weak background (`market.hsgt_moneyflow`)
  - index constituent vs non-constituent

  Output per bucket: `{ sample_count, mature_count, avg_return_by_window, win_rate, label }`.
  A **scaffold** (data structure + simple stats), not a model. Exposed via the existing
  learning-loop endpoint (`api_decision_ledger_learning_loop`, [app.py:2958](apps/control-panel/app.py)).

## 8. Safety invariants (must hold)

- The scan pipeline has **zero** readiness/account gating; factors live only there + in display /
  evidence structures.
- Real-money is gated by `readiness_mode == "live_ready"` (weekend → `shadow_only` at
  [readiness.py:810-830](apps/control-panel/readiness.py)) **and** `decision_contract` constraints
  + `account_book` mode — none of which read factor data.
- `factor_snapshot` and `formal_data.factor_profile` are **never** passed into `compute_readiness`
  or `decision_contract`.
- Today (2026-05-30) is a Saturday — `/api/readiness/live` must remain `shadow_only` after the change.
- **Regression test:** injecting factor data into a profile must not change `readiness_mode`.
- Do **not** revert existing uncommitted working-tree changes on branch `codex/ask-v2`; all work is additive.

## 9. Fault tolerance

Centralized in `tushare_factors.py`, reusing `data_assets` patterns
([data_assets.py:55-299](apps/control-panel/data_assets.py)):
- missing file/manifest → `(None, None)` → factor value `None`;
- `_safe_float` for NaN/Inf/`""`/`"-"`/`"None"` → `None`;
- empty rows → skip dimension;
- trade-date mismatch → walk back to the latest available partition (as
  `_load_index_memberships` / the Tushare provider already do);
- every factor value is `Optional`; a `data_completeness` ratio is reported and surfaced.

## 10. Test plan (≥3 areas + no-regression)

1. **Factor layer** — `tests/test_tushare_factors.py`: score math from known inputs, tag/flag
   thresholds, missing-data (None/NaN/empty/missing file), pool-relative standing, explanation
   structure, no fabrication on missing data, trade-date fallback.
2. **Candidate explanation** — new `apps/control-panel/tests/test_stock_formal_data.py` (fills the
   coverage gap): `formal_data.factor_profile` shape + missing-data rendering; plus an assertion
   that opportunities/candidate-detail carry `tushare_score` / `factor_tags` / `explanation`.
3. **Ledger snapshot** — extend `apps/control-panel/tests/test_decision_ledger_capture.py`:
   `factor_snapshot` is captured, correctly shaped, and immutable on re-save; plus a
   `build_factor_learning_loop` bucketing test.
4. **No regression** — existing readiness (weekend `shadow_only`), parameters-centralization,
   canonical/midday contract tests stay green; `npm run typecheck` passes in `apps/web`.

Commands: `pytest` (from repo root; `testpaths = apps/control-panel/tests, tests`),
`npm run typecheck` (in `apps/web`).

## 11. Phasing

Each phase is independently testable:

1. Factor core + its tests (verify import seam first).
2. Scan / ai_screening / prism_canonical / candidate_lifecycle wiring + re-rank tests.
3. Control-panel API (cards, candidate detail, `formal_data.factor_profile`) + tests.
4. Ledger `factor_snapshot` + `build_factor_learning_loop` + tests.
5. Frontend types + discovery + stock pages + `typecheck`.
6. Full verification (pytest + typecheck + live endpoints + safety checks).

## 12. Datasets used

`valuation.daily`, `liquidity.daily`, `capital_flow.daily`, `fundamentals.snapshot`,
`financial.indicator`, `financial.statement` (evidence), `corporate_action.dividend` (evidence),
`shareholder.top10` (evidence), `index.weight`, `market.daily_basic_snapshot` (fallback for PE/PB),
`market.top_list`, `market.top_inst`, `market.hsgt_moneyflow`, `market.margin`. Read root:
`data/prism_data/datasets/<dataset>/<trade_date>/<key>.json` (per-stock key = bare 6-digit code;
market-wide = `all`/`recent`; index = `000300.SH` etc.).

## 13. New fields catalog

- **Scan candidate (`scan_result.json`)**: `tushare_factors` (FactorBundle); top-level `tushare_factor_pool_stats`.
- **Screening (`ai_screening_result.json`)**: `tushare_factors` on shortlist + selected_stocks; bounded `priority_score` adjustment.
- **Canonical candidate / opportunities API**: `tushare_score`, `tushare_score_breakdown`, `factor_tags`, `risk_flags`, `factor_explanation` (+ full `tushare_factors` on detail).
- **`formal_data`**: `factor_profile` (FactorBundle minus pool internals; includes evidence blocks).
- **Decision record**: top-level `factor_snapshot`; new `build_factor_learning_loop` output.
- **Frontend types**: `TushareFactorProfile`; extended `StockListCard`, `StockFormalData`.

## 14. Acceptance criteria mapping

1. `/api/data-assets/status` still works → unchanged read path; covered by existing tests. ✓
2. `/api/stock/sh600519` shows `formal_data` with `factor_profile`; stock page renders Tushare 档案 with explanation. ✓
3. `/api/opportunities` / candidate detail carry `tushare_score` / `factor_tags` / explanation. ✓
4. `scan_result.json` / `ai_screening_result.json` candidates contain Tushare factor explanation. ✓
5. New Decision Ledger records save `factor_snapshot`. ✓
6. `/api/readiness/live` stays `shadow_only` on weekend; regression test guards it. ✓
7. Tests pass: `npm run typecheck` + relevant pytest, covering factor layer, candidate explanation, ledger snapshot. ✓

## 15. Out of scope / follow-ups

- T+10 outcome window for Dragon-Tiger (would expand `OUTCOME_WINDOWS` + evaluator + tests).
- Predictive / ML factor model (only the explainable scaffold is in scope).
- Any change to readiness / account / decision-contract logic.
- Backfilling `factor_snapshot` onto historical decision records (forward-only; old records `.get()` to `None`).
