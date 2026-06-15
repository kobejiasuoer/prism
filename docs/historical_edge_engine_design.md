# Historical Edge Engine Design

**Status**: Draft for review
**Author**: Claude Code
**Date**: 2026-06-04
**Stage**: 阶段3 - 交易执行与风控 (research-only component, no execution)

---

## 1. Executive Summary

The **Historical Edge Engine** retrieves historically similar market scenarios for a candidate stock from Prism's 4+ years of archived datasets (2022-01-04 → 2026-06-03, ~838 stocks × 1,067 trade dates), computes forward-looking outcome statistics (win rate, excess return, failure attribution), and surfaces this **empirical edge** alongside the existing Tushare factor profile. It answers: *"When this stock looked like this before, what happened next?"*

### Core Value Proposition

- **Empirical grounding**: Replaces "this factor score is high" with "18 of 22 past similar scenarios gained >5% within 5 days"
- **Failure transparency**: Surfaces the 4 losing cases and their common traits (e.g., all 4 hit涨跌停 on T+1)
- **Zero new infrastructure**: Reuses existing datasets, manifest reading, decision_ledger label logic, and test patterns
- **Research-only**: Stage 3 discipline — does NOT feed readiness gates or override factor scores; purely informational

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  Screening Pipeline (scan.py + ai_screening.py)                │
│  ┌─────────────────────┐      ┌───────────────────────────┐   │
│  │ Today's Candidate   │─────▶│ Historical Edge Engine    │   │
│  │ code, trade_date    │      │ (new module)              │   │
│  │ tushare_factors     │      └───────────┬───────────────┘   │
│  └─────────────────────┘                  │                     │
│                                           │                     │
│  ┌─────────────────────────────────────────▼─────────────────┐ │
│  │ Historical Edge Snapshot (dict)                           │ │
│  │ • similar_count: 22                                       │ │
│  │ • win_rate_5d: 81.8%, excess_return_vs_hs300: +3.2%      │ │
│  │ • failure_cases: [{code, date, return_5d, limit_hit}...]│ │
│  │ • coverage_quality: "good" / "sparse" / "insufficient"   │ │
│  └───────────────────────────────────────┬──────────────────┘ │
│                                           │                     │
│  ┌───────────────────────────────────────▼──────────────────┐ │
│  │ Decision Ledger (decision_ledger.py)                     │ │
│  │ build_decision_record(..., historical_edge=edge_snapshot)│ │
│  └──────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘

Data Flow:
1. candidate → extract_features() → feature_vector (20-30 dims)
2. feature_vector → match_similar_samples() → [(code, date), ...]
3. historical (code,date) pairs → compute_labels() → outcomes (5d/10d/20d)
4. outcomes → aggregate_edge_stats() → edge_snapshot
5. edge_snapshot attached to candidate payload & decision_ledger record
```

### Module Breakdown

```
packages/screener/historical_edge/
├── __init__.py
├── feature_builder.py       # extract_features(code, date) → dict
├── label_builder.py         # compute_labels(code, date) → outcomes
├── sample_matcher.py        # match_similar_samples(features) → matches
├── edge_analyzer.py         # aggregate_edge_stats(matches, outcomes) → snapshot
└── tests/
    ├── test_feature_builder.py
    ├── test_label_builder.py
    ├── test_sample_matcher.py
    ├── test_edge_analyzer.py
    └── test_integration.py
```

---

## 3. Feature Engineering

### 3.1 Feature Vector (20-30 dimensions)

Reuse existing Tushare datasets loaded by `data_assets._load_dataset()`. All features are **lagging indicators** (T-1 or earlier) to prevent lookahead bias.

| Feature Group | Dataset | Fields | Explanation |
|---|---|---|---|
| **Valuation** (4) | `valuation.daily` | pe_ttm, pb, ps_ttm, dv_ratio | Relative cheapness |
| **Momentum** (6) | `bars.daily` | return_5d, return_10d, return_20d, vol_ratio_5d, close_to_high_20d, RSI_14d | Price trajectory |
| **Liquidity** (3) | `liquidity.daily` | turnover_rate_20d_avg, float_share_billions, volume_surge_ratio | Tradability |
| **Capital Flow** (3) | `capital_flow.daily` | net_mf_amount_5d, net_mf_ratio, large_net_ratio | Smart money |
| **Fundamental** (4) | `financial.indicator` | roe, roa, gross_margin, debt_ratio | Business quality |
| **Market Context** (3) | `benchmark.index_daily` | hs300_return_5d, zz500_return_5d, market_vol_20d | Regime |
| **Risk Flags** (2) | `execution.flags` | is_st, is_limit_up_t1 | Hard constraints |
| **Technical** (3) | `technical.stk_factor` | macd, kdj_k, boll_position | TA supplements |

Total: **28 features**. Some may be `None` (missing data) — the matcher handles sparsity.

### 3.2 Normalization & Bucketing

- **Continuous features**: bucket into quintiles or deciles (e.g., `pe_ttm` → `"Q1"`, `"Q2"`, ..., `"Q5"`)
- **Categorical features**: direct match (e.g., `is_st=False`)
- **Match threshold**: require ≥50% of non-None features to agree within one bucket

---

## 4. Label Generation (Outcome Windows)

Reuse `decision_ledger.nth_trading_day_after()` and the outcome classification logic.

### 4.1 Forward Return Windows

For each historical (code, date) pair, compute:

```python
{
  "5d": {"return_pct": +6.2, "high_return_pct": +8.1, "low_return_pct": -1.0, "label": "validated"},
  "10d": {"return_pct": +4.1, "high_return_pct": +7.5, "low_return_pct": -2.3, "label": "inconclusive"},
  "20d": {"return_pct": +1.8, "high_return_pct": +5.2, "low_return_pct": -3.5, "label": "invalidated"},
  "limit_hit_t1": False,
  "suspension_t1_to_t5": False,
}
```

- **return_pct**: `(close_T+N - close_T) / close_T * 100`
- **high_return_pct**: `(high_T+1..T+N_max - close_T) / close_T * 100` (intraday best exit)
- **low_return_pct**: `(low_T+1..T+N_min - close_T) / close_T * 100` (worst drawdown)
- **label**: apply `decision_ledger.classify_outcome()` thresholds (e.g., ±5% for 5d window)

### 4.2 Failure Attribution

Tag each outcome with **constraint violations** that would have blocked execution:

- `limit_hit_t1`: 涨停/跌停 on T+1 (from `price_limit.daily` or `bars.daily` open == high/low)
- `suspension_t1_to_t5`: 停牌 during window (from `execution.flags`)
- `st_flagged`: ST status active (from `execution.flags`)
- `extreme_vol_surge`: volume 5× 20d average (liquidity shock)

---

## 5. Sample Matching Algorithm

### 5.1 Candidate Pool Construction

```python
# Pseudocode
all_samples = []
for date in trade_dates[-1064:]:  # 2022-01-04 → today-1
    for code in universe:  # ~800 stocks (HS300 + ZZ500 core)
        if has_sufficient_data(code, date):
            features = extract_features(code, date)
            labels = compute_labels(code, date)
            all_samples.append((code, date, features, labels))
# Result: ~600k–800k (code, date) samples
```

**Pre-computation strategy** (Phase 2 optimization): Build this once per week, cache as Parquet. For now, compute on-demand for the candidate's feature bucket subset.

### 5.2 Similarity Matching

```python
def match_similar_samples(candidate_features, all_samples, threshold=0.5):
    matches = []
    for (code, date, features, labels) in all_samples:
        similarity = compute_similarity(candidate_features, features)
        if similarity >= threshold:
            matches.append({
                "code": code,
                "date": date,
                "similarity": similarity,
                "labels": labels,
            })
    return sorted(matches, key=lambda x: x["similarity"], reverse=True)[:100]
```

**Similarity metric**:
```
similarity = (# features matching within 1 bucket) / (# non-None features in both)
```

Require **≥20 matches** to declare "sufficient coverage"; 5–19 → "sparse"; <5 → "insufficient".

---

## 6. Edge Statistics Aggregation

```python
def aggregate_edge_stats(matches):
    if len(matches) < 5:
        return {"coverage_quality": "insufficient", "reason": "too few matches"}

    outcomes_5d = [m["labels"]["5d"] for m in matches]
    win_count = sum(1 for o in outcomes_5d if o["label"] == "validated")
    loss_count = sum(1 for o in outcomes_5d if o["label"] == "invalidated")
    neutral_count = len(outcomes_5d) - win_count - loss_count

    avg_return = mean([o["return_pct"] for o in outcomes_5d])
    median_return = median([o["return_pct"] for o in outcomes_5d])

    # Benchmark comparison (if hs300_return_5d available in features)
    benchmark_returns = [extract_benchmark(m) for m in matches]
    excess_return = avg_return - mean(benchmark_returns) if benchmark_returns else None

    # Failure cases
    failures = [
        {
            "code": m["code"],
            "date": m["date"],
            "return_5d": m["labels"]["5d"]["return_pct"],
            "limit_hit_t1": m["labels"]["limit_hit_t1"],
            "suspension": m["labels"]["suspension_t1_to_t5"],
        }
        for m in matches if m["labels"]["5d"]["label"] == "invalidated"
    ]

    return {
        "similar_count": len(matches),
        "coverage_quality": "good" if len(matches) >= 20 else "sparse",
        "win_rate_5d": win_count / len(matches),
        "loss_rate_5d": loss_count / len(matches),
        "avg_return_5d": avg_return,
        "median_return_5d": median_return,
        "excess_return_vs_hs300": excess_return,
        "failure_cases": failures[:10],  # top 10 worst
        "windows": {
            "5d": {...},
            "10d": {...},
            "20d": {...},
        },
    }
```

---

## 7. Integration Points

### 7.1 Screening Pipeline Hook

**In `ai_screening.py` (or scan.py post-processing)**:

```python
from screener.historical_edge import build_historical_edge_snapshot

def build_stock_entry(candidate, data_trade_date):
    # ... existing code ...
    tushare_snapshot = tushare_factors.build_factor_snapshot(code, data_trade_date)

    # NEW: Historical edge (best-effort, never fatal)
    historical_edge = None
    try:
        historical_edge = build_historical_edge_snapshot(code, data_trade_date)
    except Exception as e:
        logger.warning(f"Historical edge skipped for {code}: {e}")

    return {
        "code": code,
        "name": name,
        "tushare_factors": tushare_snapshot,
        "historical_edge": historical_edge,  # NEW FIELD
        # ... rest of payload ...
    }
```

### 7.2 Decision Ledger Attachment

**In `decision_ledger.build_decision_record()`**:

Add `historical_edge: Mapping[str, Any] | None = None` param, attach to record:

```python
{
  "factor_snapshot": dict(factor_snapshot) if factor_snapshot else None,
  "historical_edge": dict(historical_edge) if historical_edge else None,  # NEW
  "decision_contract": ...,
}
```

### 7.3 Web UI Display (Future)

- **Discovery page**: Badge showing "🎯 82% edge (22 matches)" next to Tushare score
- **Stock detail page**: Dedicated "Historical Edge" card with win rate, failure case drill-down
- **Review page**: Edge stats in outcome audit view

---

## 8. Testing Strategy

### 8.1 Unit Tests

**`test_feature_builder.py`**:
```python
def test_extract_features_from_seeded_data(tmp_path, monkeypatch):
    root = tmp_path / "datasets"; root.mkdir()
    monkeypatch.setenv("PRISM_DATASET_REPOSITORY_ROOT", str(root))
    _seed(root, "valuation.daily", "2026-05-29", "000001", [
        {"trade_date": "2026-05-28", "pe_ttm": 12.0, "pb": 1.5},
        {"trade_date": "2026-05-29", "pe_ttm": 12.5, "pb": 1.6},
    ])
    _seed(root, "bars.daily", "2026-05-29", "000001", [
        {"trade_date": "2026-05-20", "close": 10.0},
        {"trade_date": "2026-05-29", "close": 11.0},
    ])
    features = extract_features("000001", "2026-05-29")
    assert features["pe_ttm"] == 12.5
    assert abs(features["return_5d"] - 10.0) < 0.1  # (11-10)/10*100
```

**`test_label_builder.py`**:
```python
def test_compute_labels_5d_window(tmp_path, monkeypatch):
    # Seed bars for T → T+5
    # Assert return_pct, high_return_pct, label
```

**`test_sample_matcher.py`**:
```python
def test_match_similar_samples_filters_by_threshold():
    candidate = {"pe_ttm_bucket": "Q2", "return_5d_bucket": "Q4"}
    samples = [
        ("000001", "2023-01-05", {"pe_ttm_bucket": "Q2", "return_5d_bucket": "Q4"}, labels),  # exact match
        ("000002", "2023-01-05", {"pe_ttm_bucket": "Q1", "return_5d_bucket": "Q4"}, labels),  # 1 diff
        ("000003", "2023-01-05", {"pe_ttm_bucket": "Q5", "return_5d_bucket": "Q1"}, labels),  # 2 diff
    ]
    matches = match_similar_samples(candidate, samples, threshold=0.5)
    assert len(matches) == 2  # exact + 1diff; 2diff excluded
```

### 8.2 Integration Test

**`test_integration.py`**:
```python
def test_full_pipeline_candidate_to_edge_snapshot(tmp_path, monkeypatch):
    # Seed 30 historical (code, date) samples with known outcomes
    # Extract candidate features → match → aggregate
    # Assert win_rate, failure_cases count, coverage_quality
```

---

## 9. Performance & Scalability

### Current (MVP) Constraints

- **On-demand computation**: No pre-built index; compute features + labels for matching samples at query time
- **Search space**: ~600k–800k (code, date) samples
- **Target latency**: <2s for 1 candidate (acceptable for research-only, non-blocking use)

### Phase 2 Optimizations (if latency becomes a blocker)

1. **Pre-compute feature index**: Build weekly Parquet cache of all (code, date, features, labels) tuples
2. **Coarse filtering**: Bucket by valuation quintile + momentum quintile → reduce search to ~10k subset
3. **Parallel processing**: `concurrent.futures` for multi-candidate batches
4. **Approximate matching**: LSH or FAISS for nearest-neighbor search

---

## 10. Risk Mitigations & Guardrails

### 10.1 Stage 3 Discipline

- **Research-only**: Engine outputs are attached to decision records but **DO NOT**:
  - Override Tushare factor scores
  - Block/unblock candidates via readiness gates
  - Feed into `final_score` or `priority_score` computation
- **Stage 阶段3 marker**: Edge snapshot includes `{"stage": "research", "feeds_execution": false}` metadata

### 10.2 Data Quality Gates

- **Insufficient coverage** (<5 matches): Return `{"coverage_quality": "insufficient", "reason": "..."}` instead of fabricating stats
- **Missing datasets**: If `valuation.daily` or `bars.daily` unavailable, return `None` + log warning
- **Lookahead prevention**: All features use T-1 data; labels use T+N data; assert `feature_date < label_start_date`

### 10.3 Failure Transparency

- **Failure cases included**: Every edge snapshot surfaces the worst outcomes, not just aggregate win rate
- **Attribution tags**: Each failure tagged with constraint violations (limit_hit, suspension, st_flagged)
- **Audit trail**: Full edge snapshot persisted in decision_ledger for post-trade review

---

## 11. Implementation Phases

### Phase 1: Core Engine (2-3 days, ~8 files)

1. **feature_builder.py** (4-6 hours): Extract 28 features from 8 datasets
2. **label_builder.py** (4-6 hours): Compute 5d/10d/20d outcomes + attribution
3. **sample_matcher.py** (3-4 hours): Bucket-based similarity matching
4. **edge_analyzer.py** (2-3 hours): Aggregate stats from matches
5. **Unit tests** (4-6 hours): One test file per module
6. **Integration test** (2-3 hours): End-to-end candidate → edge snapshot

### Phase 2: Pipeline Integration (1 day)

1. **ai_screening.py hook** (1-2 hours): Add `historical_edge` to candidate payload
2. **decision_ledger.py extension** (1 hour): Add `historical_edge` param to `build_decision_record()`
3. **Integration test** (2 hours): Seed datasets → run scan.py → assert edge in ledger

### Phase 3: Validation & Documentation (1 day)

1. **Manual validation** (3-4 hours): Run on 10 real candidates, inspect edge snapshots
2. **Usage documentation** (2 hours): README + code examples
3. **Review & iterate** (2-3 hours): Address feedback, edge case hardening

**Total estimate**: 4-5 days for full MVP.

---

## 12. Open Questions for Review

1. **Feature selection**: Are 28 features too many / too few? Should we include sector (industry) as a categorical feature?
2. **Match threshold**: Is 50% similarity + ≥20 matches the right balance? Too strict?
3. **Outcome thresholds**: Reuse `decision_ledger.OutcomeThresholds` defaults (±5% for 5d), or tune separately?
4. **Benchmark choice**: HS300 for large-caps, ZZ500 for mid-caps — should we auto-select by market cap?
5. **Pre-computation timing**: Should Phase 2 index-building happen immediately, or wait for latency complaints?

---

## 13. Success Metrics

### MVP Acceptance Criteria

- [ ] Engine returns edge snapshot for ≥80% of discovery candidates
- [ ] Coverage quality "good" or "sparse" for ≥60% of cases
- [ ] Latency <2s per candidate (non-blocking)
- [ ] All unit tests + integration test passing
- [ ] Edge snapshot attached to decision_ledger record
- [ ] Zero impact on existing `final_score` / `readiness` / `priority_score` (stage discipline verified)

### Long-Term Validation (阶段4+ outcome review)

- After 3 months: Compare win_rate predictions vs actual trade outcomes
- Calibration check: "82% edge" candidates → actual ≥75% win rate in live trades?
- Failure attribution accuracy: Did limit_hit_t1 tags predict real T+1 limit hits?

---

## 14. Dependencies & Prerequisites

- [x] Datasets present: `bars.daily`, `valuation.daily`, `liquidity.daily`, `capital_flow.daily`, `financial.indicator`, `benchmark.index_daily`, `execution.flags`, `technical.stk_factor`
- [x] Date range: 2022-01-04 → 2026-06-03 confirmed (1,067 trade dates)
- [x] Universe size: ~838 stocks confirmed
- [x] Decision ledger API: `build_decision_record()`, `nth_trading_day_after()`, `classify_outcome()` reviewed
- [x] Test patterns: pytest + `tmp_path` + `_seed()` helper established
- [ ] Data completeness audit: Verify ≥80% of (code, date) samples have all 8 required datasets

---

## Appendix A: Dataset Paths

```
data/prism_data/datasets/
├── bars.daily/2026-06-03/000001.json          # [{"trade_date": "2026-05-06", "close": 10.0}, ...]
├── valuation.daily/2026-05-29/000001.json     # [{"trade_date": "2022-01-04", "pe_ttm": 12.0}, ...]
├── liquidity.daily/2026-05-29/000001.json     # Full series 2022→2026
├── capital_flow.daily/2026-06-03/000001.json  # Rolling window
├── financial.indicator/2026-05-29/000001.json # Full series
├── benchmark.index_daily/2026-05-29/000300.json  # HS300 series
├── execution.flags/2026-05-29/000001.json     # Full series
└── technical.stk_factor/2026-05-29/000001.json # Full series
```

---

## Appendix B: Example Edge Snapshot

```json
{
  "stage": "research",
  "feeds_execution": false,
  "generated_at": "2026-06-04T10:23:15Z",
  "candidate": {
    "code": "000001",
    "trade_date": "2026-06-03"
  },
  "similar_count": 22,
  "coverage_quality": "good",
  "win_rate_5d": 0.818,
  "loss_rate_5d": 0.091,
  "avg_return_5d": 6.3,
  "median_return_5d": 5.8,
  "excess_return_vs_hs300": 3.2,
  "windows": {
    "5d": {
      "win_rate": 0.818,
      "avg_return": 6.3,
      "median_return": 5.8,
      "p10_return": 1.2,
      "p90_return": 11.5
    },
    "10d": {
      "win_rate": 0.727,
      "avg_return": 4.1,
      "median_return": 3.5
    },
    "20d": {
      "win_rate": 0.636,
      "avg_return": 2.8,
      "median_return": 1.9
    }
  },
  "failure_cases": [
    {
      "code": "000001",
      "date": "2023-07-12",
      "return_5d": -8.2,
      "limit_hit_t1": true,
      "suspension_t1_to_t5": false,
      "st_flagged": false
    },
    {
      "code": "000002",
      "date": "2024-03-21",
      "return_5d": -6.1,
      "limit_hit_t1": false,
      "suspension_t1_to_t5": true,
      "st_flagged": false
    }
  ],
  "feature_summary": {
    "pe_ttm_bucket": "Q2",
    "return_5d_bucket": "Q4",
    "turnover_rate_20d_avg_bucket": "Q3"
  }
}
```

---

**End of Design Document**
