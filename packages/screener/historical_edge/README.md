# Historical Edge Engine

**"When this stock looked like this before, what happened next?"**

The Historical Edge Engine matches current candidates to historically similar market scenarios and computes empirical win rates, average returns, and failure attribution from 4+ years of historical data.

---

## Overview

- **Purpose:** Research-only component (阶段3) that surfaces empirical edge alongside existing Tushare factor profiles
- **Input:** Current candidate (code, trade_date) + pre-built sample pool
- **Output:** Edge snapshot with win rates, returns, failure cases, and coverage quality
- **Integration:** Attached to `decision_record["attachments"]["historical_edge"]`, never affects readiness gates or scores

---

## Quick Start

### 1. Extract Features & Labels (Single Sample)

```python
from screener.historical_edge import extract_features, compute_labels, bucketize_features, DEFAULT_QUINTILES

# Extract 28 features for a historical sample
features = extract_features("000001", "2023-05-10")
# {"pe_ttm": 15.2, "return_5d": 3.4, "roe": 12.5, ...}

# Bucketize into quintiles (Q1-Q5)
bucketed = bucketize_features(features, DEFAULT_QUINTILES)
# {"pe_ttm": "Q2", "return_5d": "Q3", "roe": "Q2", ...}

# Compute forward outcome labels (5d/10d/20d)
labels = compute_labels("000001", "2023-05-10")
# {
#   "5d": {"return_pct": 6.3, "label": "validated", ...},
#   "10d": {...},
#   "20d": {...},
#   "limit_hit_t1": False,
#   "st_flagged": False,
#   ...
# }
```

### 2. Build Sample Pool (Batch Pre-computation)

```python
from screener.historical_edge import build_sample_pool_for_universe

# ZZ500 universe
universe = ["000001", "000002", ..., "688999"]

# 4 years of trading days
date_range = ["2022-01-04", "2022-01-05", ..., "2025-12-31"]

# Build pool: ~500 codes × ~1000 days = ~500k samples (takes 1-2 hours)
sample_pool = build_sample_pool_for_universe(universe, date_range)
# Returns: [(code, date, bucketed_features, labels), ...]

# Save for reuse
import json
with open("data/prism_data/cache/historical_edge_sample_pool.json", "w") as f:
    json.dump(sample_pool, f)
```

### 3. Build Edge Snapshot (Query-time)

```python
from screener.historical_edge import build_historical_edge_snapshot

# Load pre-built pool
with open("data/prism_data/cache/historical_edge_sample_pool.json") as f:
    sample_pool = json.load(f)

# Query for a current candidate
snapshot = build_historical_edge_snapshot(
    code="600519",
    trade_date="2026-06-04",
    sample_pool=sample_pool,
    similarity_threshold=0.5,  # default
    max_matches=100,  # default
)

# snapshot:
# {
#   "stage": "research",
#   "feeds_execution": False,
#   "similar_count": 42,
#   "coverage_quality": "good",  # "good" (≥20), "sparse" (5-19), "insufficient" (<5)
#   "win_rate_5d": 0.71,  # 71% of matches had ≥5% return in 5d
#   "loss_rate_5d": 0.12,  # 12% had ≤-5% return
#   "avg_return_5d": 5.8,
#   "median_return_5d": 4.2,
#   "windows": {
#     "5d": {"win_rate": 0.71, "avg_return": 5.8, "p10_return": -2.1, "p90_return": 12.3, ...},
#     "10d": {...},
#     "20d": {...}
#   },
#   "failure_cases": [
#     {"code": "000001", "date": "2023-03-15", "return_5d": -8.2, "limit_hit_t1": True, ...},
#     ...  # top 10 worst outcomes
#   ],
#   "feature_summary": {"pe_ttm_bucket": "Q2", "return_5d_bucket": "Q3", ...}
# }
```

### 4. Human-Readable Summary

```python
from screener.historical_edge import format_edge_summary_text

summary = format_edge_summary_text(snapshot)
# "🎯 71% edge (42 matches, good coverage): avg +5.8%, 5 failures (2 limit-hit)"
```

---

## Features Extracted (28 Total)

### Valuation (4)
- `pe_ttm`, `pb`, `ps_ttm`, `dv_ratio`

### Momentum (6)
- `return_5d`, `return_10d`, `return_20d`, `vol_ratio_5d`, `close_to_high_20d`, `rsi_14d`

### Liquidity (3)
- `turnover_rate_20d_avg`, `float_share_billions`, `volume_surge_ratio`

### Capital Flow (3)
- `net_mf_amount_5d`, `net_mf_ratio`, `large_net_ratio`

### Fundamental (4)
- `roe`, `roa`, `gross_margin`, `debt_ratio`

### Market Context (3)
- `hs300_return_5d`, `zz500_return_5d`, `market_vol_20d`

### Risk Flags (2)
- `is_st`, `is_limit_up_t1`

### Technical (3)
- `macd`, `kdj_k`, `boll_position`

All features use **T-1 data** (or earlier) to prevent lookahead bias.

---

## Outcome Labels (5d/10d/20d)

Each window computes:
- **return_pct**: Close-to-close return from T to T+N
- **high_return_pct**: Best possible exit (max intraday high in [T+1, T+N])
- **low_return_pct**: Worst drawdown (min intraday low in [T+1, T+N])
- **label**: "validated" (≥5%), "invalidated" (≤-5%), "inconclusive", "data_issue"

Constraint violation flags:
- **limit_hit_t1**: Hit limit up/down on T+1
- **suspension_t1_to_t5**: Suspended during [T+1, T+5]
- **st_flagged**: ST status active on T
- **extreme_vol_surge**: Volume > 5× 20d average on T or T+1

---

## Similarity Matching Algorithm

**Bucket-based matching** (not Euclidean distance):

1. **Bucketize** continuous features into quintiles (Q1-Q5) using `DEFAULT_QUINTILES`
2. **Within-1-bucket = match**: Q2 matches Q1, Q2, Q3 (but not Q4, Q5)
3. **Similarity score** = (# matching features) / (# non-None features in both)
4. **Threshold**: Default 0.5 (≥50% features match)
5. **Max matches**: Default 100 (sorted by similarity descending)

This approach is robust to small variations and handles missing features gracefully (skip in calculation).

---

## Integration Points

### 1. ai_screening.py (Optional, Not Yet Enabled)

**Location:** `build_stock_entry()` at [packages/screener/ai_screening.py:858-903](../ai_screening.py#L858-L903)

**Integration (future):**
```python
# At module level, load sample pool once
_SAMPLE_POOL_CACHE = None

def _load_sample_pool():
    global _SAMPLE_POOL_CACHE
    if _SAMPLE_POOL_CACHE is None:
        pool_path = Path(__file__).parents[1] / "data" / "prism_data" / "cache" / "historical_edge_sample_pool.json"
        if pool_path.exists():
            with pool_path.open() as f:
                _SAMPLE_POOL_CACHE = json.load(f)
        else:
            _SAMPLE_POOL_CACHE = []
    return _SAMPLE_POOL_CACHE

# In build_stock_entry(), after line 903:
def build_stock_entry(stock, strategy_name, decision, market_regime=None, market_themes=None):
    # ... existing code ...

    # Build historical edge snapshot (optional, graceful degradation)
    historical_edge = None
    try:
        from screener.historical_edge import build_historical_edge_snapshot
        sample_pool = _load_sample_pool()
        if sample_pool:
            trade_date = resolve_trade_date_from_stock(stock)  # helper to extract trade_date
            historical_edge = build_historical_edge_snapshot(
                code=stock.get("code"),
                trade_date=trade_date,
                sample_pool=sample_pool,
            )
    except Exception:
        # Graceful degradation: if historical edge fails, continue without it
        pass

    return {
        # ... existing fields ...
        "tushare_factors": stock.get("tushare_factors"),
        "historical_edge": historical_edge,  # NEW: add this line
    }
```

**Status:** 🚧 Not yet enabled (waiting for sample pool construction)

### 2. decision_ledger.py (Ready for Integration)

**Location:** `build_decision_record()` at [apps/control-panel/decision_ledger.py:497-627](../../apps/control-panel/decision_ledger.py#L497-L627)

**Integration:**
```python
def build_decision_record(
    # ... existing parameters ...
    historical_edge: dict | None = None,  # NEW: add this parameter
) -> dict:
    # ... existing logic ...

    # In attachments section (around line 580-600):
    attachments = {}
    if factor_snapshot:
        attachments["factor_snapshot"] = _normalize_factor_snapshot_payload(factor_snapshot)
    if historical_edge:  # NEW: add this block
        attachments["historical_edge"] = historical_edge

    return {
        # ... existing fields ...
        "attachments": attachments,
    }
```

**Status:** ✅ Ready for integration (see below for implementation)

---

## Sample Pool Construction

### Weekly Cron Job (Recommended)

```bash
# prism_scheduled_job.py or standalone script
python -c "
from screener.historical_edge import build_sample_pool_for_universe
from pathlib import Path
import json

# Load ZZ500 universe from latest snapshot
universe = load_zz500_codes()  # your helper

# 4 years of history
date_range = get_trading_days_since('2022-01-01')  # your helper

print(f'Building sample pool: {len(universe)} codes × {len(date_range)} days...')
sample_pool = build_sample_pool_for_universe(universe, date_range)
print(f'Built {len(sample_pool)} samples')

# Save cache
cache_path = Path('data/prism_data/cache/historical_edge_sample_pool.json')
cache_path.parent.mkdir(parents=True, exist_ok=True)
with cache_path.open('w') as f:
    json.dump(sample_pool, f)

print(f'Saved to {cache_path}')
"
```

**Estimated runtime:** 1-2 hours for 500 codes × 1000 days = 500k samples

**Refresh frequency:** Weekly (every Monday before market open)

---

## Testing

Run the full test suite:

```bash
python -m pytest packages/screener/historical_edge/tests/ -v
# 25 tests, should all pass
```

Test individual modules:

```bash
# Feature extraction
python -m pytest packages/screener/historical_edge/tests/test_feature_builder.py -v

# Outcome labels
python -m pytest packages/screener/historical_edge/tests/test_label_builder.py -v

# Similarity matching
python -m pytest packages/screener/historical_edge/tests/test_sample_matcher.py -v

# Edge aggregation
python -m pytest packages/screener/historical_edge/tests/test_edge_analyzer.py -v

# Full pipeline
python -m pytest packages/screener/historical_edge/tests/test_integration.py -v
```

---

## Troubleshooting

### "No sample pool provided"
```json
{
  "coverage_quality": "insufficient",
  "reason": "No sample pool provided (engine requires pre-built historical sample pool)"
}
```
**Solution:** Build and save the sample pool using `build_sample_pool_for_universe()`.

### "Only N historical matches found (minimum 5 required)"
```json
{
  "coverage_quality": "insufficient",
  "similar_count": 3,
  "reason": "Only 3 historical matches found (minimum 5 required)"
}
```
**Causes:**
- Candidate has unusual feature combination (extreme valuation, rare setup)
- Sample pool too small (e.g., only 1 year of history instead of 4)
- Similarity threshold too strict (try lowering from 0.5 to 0.4)

**Solutions:**
- Expand sample pool to more years or broader universe
- Lower `similarity_threshold` parameter
- Accept "sparse" coverage (5-19 matches) as informative

### Missing datasets
Features return `None` if datasets are unavailable. The engine gracefully handles missing features (skips them in similarity calculation). Check:
- `data/prism_data/datasets/valuation.daily/`
- `data/prism_data/datasets/bars.daily/`
- `data/prism_data/datasets/liquidity.daily/`
- `data/prism_data/datasets/capital_flow.daily/`
- `data/prism_data/datasets/financial.indicator/`
- `data/prism_data/datasets/benchmark.index_daily/`
- `data/prism_data/datasets/execution.flags/`
- `data/prism_data/datasets/technical.stk_factor/`
- `data/prism_data/datasets/trade_calendar/`

---

## Stage 3 Discipline (Critical)

⚠️ **Historical Edge is research-only data. It must NEVER:**

- ❌ Affect `readiness.trust_level` or `readiness_mode`
- ❌ Override or adjust candidate scores or priority
- ❌ Gate execution decisions (already gated by existing rules)
- ❌ Be displayed as the "verdict" in UI (use `TrustBanner` for that)

✅ **Historical Edge should:**

- ✅ Be stored in `decision_record["attachments"]["historical_edge"]`
- ✅ Be displayed as supplementary research insight in UI
- ✅ Always include `"stage": "research", "feeds_execution": False` in snapshot
- ✅ Surface empirical evidence alongside factor profiles, not replace them

---

## Performance Considerations

- **Feature extraction:** ~10-50ms per sample (depends on dataset sizes)
- **Label computation:** ~5-20ms per sample (depends on forward window availability)
- **Sample pool construction:** 1-2 hours for 500k samples (run weekly, cache results)
- **Query-time matching:** ~50-200ms for 500k pool (coarse filtering reduces search space)

**Optimization tips:**
- Use `filter_by_coarse_buckets()` before full similarity calculation (10× speedup)
- Cache sample pool in memory (load once at startup)
- Consider chunking pool by market cap or sector for faster queries

---

## Roadmap

### MVP (Current)
- [x] Core engine (28 features, 5d/10d/20d labels, bucket-based matching)
- [x] 25 comprehensive unit tests
- [ ] Sample pool construction script
- [ ] Integration into decision_ledger.py
- [ ] Validation on 10 real candidates

### Phase 2
- [ ] Compute actual quintiles from historical ZZ500 universe (replace DEFAULT_QUINTILES)
- [ ] Add excess return vs HS300 benchmark (currently placeholder)
- [ ] Sector-specific sample pools (match within sector first, then cross-sector)

### Phase 3
- [ ] Real-time quintile updates (weekly refresh)
- [ ] Interactive UI: click failure case → drill into that historical sample's full context
- [ ] "Find similar past winners" query (reverse: given a validated outcome, find setup pattern)
- [ ] Multi-timeframe matching (1m/5m intraday similarity for day-trading setups)

---

## Related Documentation

- [Design Document](../../docs/historical_edge_engine_design.md) - Comprehensive architecture
- [Implementation Status](../../docs/historical_edge_implementation_status.md) - Current progress
- [Decision Ledger Integration](../../apps/control-panel/decision_ledger.py) - Attachment pattern
- [Prism Stage Discipline Memory](../../../.claude/projects/-Users-yangbishang-Projects-prism/memory/prism-stage-discipline.md) - Stage 3 constraints

---

## License

Part of the Prism investment research system. Internal use only.
