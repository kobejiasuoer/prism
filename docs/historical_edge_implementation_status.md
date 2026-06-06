# Historical Edge Engine - Implementation Status

**Last Updated:** 2026-06-04
**Status:** ✅ Core Complete + decision_ledger Integration Done, Ready for Sample Pool Construction

## Summary

The Historical Edge Engine is a research-only component (阶段3) that matches current candidates to historically similar market scenarios and computes empirical win rates, average returns, and failure attribution. Core implementation and decision_ledger integration are complete. Next step: build sample pool and validate on real data.

---

## ✅ Completed Work (2026-06-04)

### 1. Design Document ✅
- **File:** [docs/historical_edge_engine_design.md](./historical_edge_engine_design.md)
- **Content:** 400+ line comprehensive design covering architecture, features, outcomes, similarity matching, integration points, and Stage 3 guardrails

### 2. Core Engine Modules ✅ (Production Code: ~1,400 lines)

#### [packages/screener/historical_edge/feature_builder.py](../packages/screener/historical_edge/feature_builder.py) (~650 lines)
- ✅ `extract_features(code, trade_date)` - Extracts 28 features from 8 datasets
- ✅ `bucketize_features(features, quintiles)` - Converts to Q1-Q5 buckets
- ✅ Handles both series-style and snapshot-style datasets
- ✅ Uses T-1 data to prevent lookahead bias
- ✅ Respects `PRISM_DATASET_REPOSITORY_ROOT` for test isolation

#### [packages/screener/historical_edge/label_builder.py](../packages/screener/historical_edge/label_builder.py) (~350 lines)
- ✅ `compute_labels(code, trade_date)` - Computes 5d/10d/20d outcome labels
- ✅ `nth_trading_day_after(trade_date, n)` - Trade calendar navigation with caching
- ✅ Labels: "validated" (≥5%), "invalidated" (≤-5%), "inconclusive", "data_issue"
- ✅ Constraint flags: limit_hit_t1, suspension_t1_to_t5, st_flagged, extreme_vol_surge

#### [packages/screener/historical_edge/sample_matcher.py](../packages/screener/historical_edge/sample_matcher.py) (~180 lines)
- ✅ `compute_similarity(candidate, sample)` - Bucket-based similarity (within-1-bucket = match)
- ✅ `match_similar_samples(candidate, pool)` - Finds top matches above threshold
- ✅ `filter_by_coarse_buckets()` - Performance optimization for large pools
- ✅ `assess_coverage_quality()` - "good" (≥20), "sparse" (5-19), "insufficient" (<5)

#### [packages/screener/historical_edge/edge_analyzer.py](../packages/screener/historical_edge/edge_analyzer.py) (~220 lines)
- ✅ `aggregate_edge_stats(matches, ...)` - Computes win rates, returns, failure cases
- ✅ `format_edge_summary_text(snapshot)` - Human-readable summary with emoji
- ✅ Statistics: win_rate, loss_rate, avg/median/p10/p90 returns for all windows
- ✅ Failure analysis: Top 10 worst outcomes with constraint tags
- ✅ Uses `datetime.now(UTC)` (fixed deprecation warning)

#### [packages/screener/historical_edge/__init__.py](../packages/screener/historical_edge/__init__.py) (~170 lines)
- ✅ `build_historical_edge_snapshot(code, date, sample_pool)` - Main API entry point
- ✅ `build_sample_pool_for_universe(universe, date_range)` - Pre-compute sample pool
- ✅ `DEFAULT_QUINTILES` - 26 feature thresholds (placeholder for MVP)

### 3. Test Suite ✅ (25 tests, ~720 lines, 100% passing)

#### [packages/screener/historical_edge/tests/test_feature_builder.py](../packages/screener/historical_edge/tests/test_feature_builder.py) (6 tests)
- ✅ test_extract_features_valuation_momentum
- ✅ test_extract_features_missing_data_graceful
- ✅ test_extract_features_risk_flags
- ✅ test_extract_features_liquidity_capital_flow
- ✅ test_bucketize_features_quintiles
- ✅ test_bucketize_features_edge_cases

#### [packages/screener/historical_edge/tests/test_label_builder.py](../packages/screener/historical_edge/tests/test_label_builder.py) (4 tests)
- ✅ test_compute_labels_5d_validated
- ✅ test_compute_labels_5d_invalidated
- ✅ test_compute_labels_constraint_violations (fixed snapshot date issue)
- ✅ test_nth_trading_day_after (fixed expected value for T+5)

#### [packages/screener/historical_edge/tests/test_sample_matcher.py](../packages/screener/historical_edge/tests/test_sample_matcher.py) (8 tests)
- ✅ test_compute_similarity_exact_match
- ✅ test_compute_similarity_within_one_bucket
- ✅ test_compute_similarity_partial_match
- ✅ test_compute_similarity_no_overlap
- ✅ test_match_similar_samples_filters_by_threshold
- ✅ test_match_similar_samples_respects_max_matches
- ✅ test_filter_by_coarse_buckets
- ✅ test_assess_coverage_quality

#### [packages/screener/historical_edge/tests/test_edge_analyzer.py](../packages/screener/historical_edge/tests/test_edge_analyzer.py) (5 tests)
- ✅ test_aggregate_edge_stats_insufficient_matches
- ✅ test_aggregate_edge_stats_good_coverage
- ✅ test_aggregate_edge_stats_sparse_coverage
- ✅ test_format_edge_summary_text_good
- ✅ test_format_edge_summary_text_insufficient

#### [packages/screener/historical_edge/tests/test_integration.py](../packages/screener/historical_edge/tests/test_integration.py) (2 tests)
- ✅ test_full_pipeline_candidate_to_edge_snapshot
- ✅ test_build_historical_edge_snapshot_no_sample_pool

### 4. Test Execution Result ✅

```bash
$ python -m pytest packages/screener/historical_edge/tests/ -v
======================== 25 passed in 0.09s ========================
```

All tests pass with no warnings.

### 5. Documentation ✅

#### [packages/screener/historical_edge/README.md](../packages/screener/historical_edge/README.md) (~600 lines)
- ✅ Quick Start guide with code examples
- ✅ Feature extraction API documentation
- ✅ Sample pool construction guide
- ✅ Integration points (ai_screening.py, decision_ledger.py)
- ✅ Troubleshooting section
- ✅ Stage 3 discipline reminders
- ✅ Performance considerations and optimization tips
- ✅ Roadmap for future phases

### 6. Pipeline Integration ✅

#### decision_ledger.py Integration ✅
- **File:** [apps/control-panel/decision_ledger.py](../../apps/control-panel/decision_ledger.py)
- **Changes:**
  1. Added `historical_edge` parameter to `build_decision_record()` signature (line 531)
  2. Added `"historical_edge": dict(historical_edge) if historical_edge else None` to return dict (line 598)
- **Verification:** All 45 existing tests pass, manual integration test confirms structure
- **Status:** ✅ Ready for production use

---

## 📋 Next Steps (Estimated: ~4-6 hours)

### Phase 2: Sample Pool Construction & Validation (4-6 hours)

1. **Build Sample Pool Script** (~2 hours)
   - Create `apps/scripts/build_historical_edge_sample_pool.py`
   - Load ZZ500 universe from latest snapshot
   - Extract 4 years of trading days (2022-01-01 to 2026-06-04)
   - Call `build_sample_pool_for_universe()`
   - Save to `data/prism_data/cache/historical_edge_sample_pool.json`
   - **Estimated runtime:** 1-2 hours for ~500k samples

2. **Real Data Validation** (~2 hours)
   - Run on 10 real candidates from `/discovery` page
   - Verify feature extraction works on production datasets
   - Check edge snapshot quality (similar_count, coverage_quality)
   - Validate failure case attribution
   - Document any dataset gaps or issues

3. **Compute Actual Quintiles** (~1 hour)
   - Use sample pool to compute real quintile thresholds
   - Replace `DEFAULT_QUINTILES` placeholder values
   - Re-run validation to verify improved matching

4. **Weekly Refresh Cron Job** (~30 min)
   - Add to `apps/scripts/prism_scheduled_job.py`
   - Schedule for every Monday 6:00 AM (before market open)
   - Monitor first 2-3 runs for errors

### Phase 3: Optional Enhancements (Future)

5. **ai_screening.py Integration** (deferred until sample pool validated)
   - Import `build_historical_edge_snapshot` at module level
   - Load sample pool cache on startup
   - Add `historical_edge` field to `build_stock_entry()` return dict
   - Graceful degradation if pool unavailable or computation fails

6. **UI Display** (frontend work, not in scope)
   - Show edge summary in candidate card
   - Display failure cases in expandable section
   - Add "Historical Edge" tab on stock detail page

---

## 🎯 Success Criteria

- [x] Core engine extracts 28 features from 8 datasets
- [x] Outcome labels computed for 5d/10d/20d windows
- [x] Bucket-based similarity matching works
- [x] Edge statistics aggregation produces win rates, returns, failure cases
- [x] 25 comprehensive unit tests pass
- [x] No deprecation warnings
- [x] Integrated into decision_ledger.py (stores in decision record)
- [x] Documentation complete (README + implementation status)
- [ ] Sample pool built for ZZ500 universe (~500k samples)
- [ ] Validated on 10 real candidates
- [ ] Actual quintiles computed from historical data
- [ ] Weekly refresh cron job scheduled

**Progress: 8/12 criteria met (67%)**

---

## 🛡️ Stage 3 Discipline Checklist

- [x] Every edge snapshot has `"stage": "research", "feeds_execution": False`
- [x] Edge data NEVER affects `readiness.trust_level` or `readiness_mode`
- [x] Edge data NEVER affects candidate scoring or priority
- [x] Edge data stored in `decision_record["historical_edge"]` only
- [x] UI should treat as supplementary research insight, not execution signal
- [x] Integration is graceful: failures don't block main pipeline

---

## 📊 Implementation Metrics

| Metric | Value |
|--------|-------|
| Production Code | ~1,400 lines |
| Test Code | ~720 lines |
| Documentation | ~600 lines (README) |
| Test Coverage | 25 tests, 100% passing |
| Features Extracted | 28 |
| Outcome Windows | 3 (5d, 10d, 20d) |
| Constraint Flags | 4 |
| Datasets Used | 8 |
| Integration Points | 2 (decision_ledger ✅, ai_screening 🚧) |

---

## 🔄 Session Timeline (2026-06-04)

1. ✅ **Context Recovery**: Reviewed summary from previous session, identified pending work
2. ✅ **Test Verification**: Fixed 2 test failures (snapshot date issue, T+5 calculation)
3. ✅ **Warning Fixes**: Replaced `datetime.utcnow()` with `datetime.now(UTC)`
4. ✅ **Documentation**: Wrote comprehensive README (~600 lines)
5. ✅ **decision_ledger Integration**: Added `historical_edge` parameter to `build_decision_record()`
6. ✅ **Integration Verification**: Confirmed all 45 decision_ledger tests pass + manual test
7. ✅ **Status Update**: Updated this document with final status

**Total Session Time**: ~2 hours
**Lines Changed**: ~100 (mostly additions)
**Tests Passing**: 70 (25 historical_edge + 45 decision_ledger)

---

## 💡 Key Design Decisions

1. **Bucket-based matching (not Euclidean)**: Quintile bucketing with within-1-bucket tolerance makes the engine robust to small variations and handles missing features gracefully
2. **Conservative labels**: ±5% thresholds, errs toward "inconclusive" rather than false positives
3. **Failure transparency**: Surfaces worst 10 outcomes with constraint tags (limit-hit, suspension, ST)
4. **Lookahead bias prevention**: All features use T-1 data, labels use T+N data
5. **Sample pool pre-computation**: MVP requires a pre-built pool (weekly cron job); on-demand is too slow for query-time
6. **Stage 3 research-only**: Never feeds readiness gates or execution decisions
7. **Graceful integration**: decision_ledger.py accepts optional `historical_edge` parameter; if None, field is omitted from record

---

## 📚 Related Documentation

- [Design Document](./historical_edge_engine_design.md) - Comprehensive architecture and feature specification
- [README](../packages/screener/historical_edge/README.md) - Usage guide and API documentation
- [Decision Ledger Integration](../apps/control-panel/decision_ledger.py) - Storage layer
- [Data Assets](../apps/control-panel/data_assets.py) - Dataset loading patterns
- [Test Stock Formal Data](../apps/control-panel/tests/test_stock_formal_data.py) - Test isolation pattern

---

## 🚀 How to Continue From Here

**Next session priorities:**

1. **Build sample pool** (highest priority)
   ```bash
   # Create the script
   touch apps/scripts/build_historical_edge_sample_pool.py

   # Run it (will take 1-2 hours)
   python apps/scripts/build_historical_edge_sample_pool.py

   # Verify output
   ls -lh data/prism_data/cache/historical_edge_sample_pool.json
   ```

2. **Validate on real data**
   ```bash
   # Load a real candidate from discovery
   python -c "
   from screener.historical_edge import build_historical_edge_snapshot
   import json

   with open('data/prism_data/cache/historical_edge_sample_pool.json') as f:
       pool = json.load(f)

   snapshot = build_historical_edge_snapshot('600519', '2026-06-04', sample_pool=pool)
   print(json.dumps(snapshot, indent=2, ensure_ascii=False))
   "
   ```

3. **Compute real quintiles**
   ```python
   # Use sample pool to compute actual quintile thresholds
   from screener.historical_edge import extract_features, DEFAULT_QUINTILES
   import numpy as np

   # Extract all feature values from sample pool
   for feature_name in DEFAULT_QUINTILES:
       values = [sample[2][feature_name] for sample in pool if sample[2].get(feature_name) is not None]
       if values:
           quintiles = np.percentile(values, [20, 40, 60, 80])
           print(f'"{feature_name}": {list(quintiles)},')
   ```

**Expected outcomes:**
- Sample pool file ~50-100 MB (500k samples × 200 bytes/sample)
- ~20-50 matches per candidate (good coverage)
- Win rates in 40-70% range (typical for momentum/quality factors)
- Some candidates with sparse/insufficient coverage (extreme valuations, rare setups)


#### [packages/screener/historical_edge/tests/test_feature_builder.py](../packages/screener/historical_edge/tests/test_feature_builder.py) (6 tests)
- ✅ test_extract_features_valuation_momentum
- ✅ test_extract_features_missing_data_graceful
- ✅ test_extract_features_risk_flags
- ✅ test_extract_features_liquidity_capital_flow
- ✅ test_bucketize_features_quintiles
- ✅ test_bucketize_features_edge_cases

#### [packages/screener/historical_edge/tests/test_label_builder.py](../packages/screener/historical_edge/tests/test_label_builder.py) (4 tests)
- ✅ test_compute_labels_5d_validated
- ✅ test_compute_labels_5d_invalidated
- ✅ test_compute_labels_constraint_violations (fixed snapshot date issue)
- ✅ test_nth_trading_day_after (fixed expected value for T+5)

#### [packages/screener/historical_edge/tests/test_sample_matcher.py](../packages/screener/historical_edge/tests/test_sample_matcher.py) (7 tests)
- ✅ test_compute_similarity_exact_match
- ✅ test_compute_similarity_within_one_bucket
- ✅ test_compute_similarity_partial_match
- ✅ test_compute_similarity_no_overlap
- ✅ test_match_similar_samples_filters_by_threshold
- ✅ test_match_similar_samples_respects_max_matches
- ✅ test_filter_by_coarse_buckets
- ✅ test_assess_coverage_quality

#### [packages/screener/historical_edge/tests/test_edge_analyzer.py](../packages/screener/historical_edge/tests/test_edge_analyzer.py) (5 tests)
- ✅ test_aggregate_edge_stats_insufficient_matches
- ✅ test_aggregate_edge_stats_good_coverage
- ✅ test_aggregate_edge_stats_sparse_coverage
- ✅ test_format_edge_summary_text_good
- ✅ test_format_edge_summary_text_insufficient

#### [packages/screener/historical_edge/tests/test_integration.py](../packages/screener/historical_edge/tests/test_integration.py) (2 tests)
- ✅ test_full_pipeline_candidate_to_edge_snapshot
- ✅ test_build_historical_edge_snapshot_no_sample_pool

### 4. Test Execution Result

```bash
$ python -m pytest packages/screener/historical_edge/tests/ -v
======================== 25 passed in 0.09s ========================
```

All tests pass with no warnings.

---

## 📋 Next Steps (Estimated: ~1-2 days)

### Phase 1: Pipeline Integration (3-4 hours)

1. **Add to ai_screening.py** (~1 hour)
   - Import `build_historical_edge_snapshot`
   - Add `historical_edge` field to candidate payload
   - Handle insufficient coverage gracefully (None or minimal dict)

2. **Extend decision_ledger.py** (~1 hour)
   - Add `historical_edge` parameter to `build_decision_record()` signature
   - Store edge snapshot in `decision_record["attachments"]["historical_edge"]`
   - Follow existing pattern from `_normalize_factor_snapshot_payload()`

3. **Sample Pool Cache** (~2 hours)
   - Weekly cron job: Call `build_sample_pool_for_universe()` for full ZZ500 universe
   - Save to `data/prism_data/cache/historical_edge_sample_pool.json`
   - Load in ai_screening.py startup
   - Alternative: On-demand computation for MVP (acceptable for <100 candidates/day)

### Phase 2: Validation & Iteration (2-3 hours)

4. **Real Data Validation** (~2 hours)
   - Run on 10 real candidates from `/discovery` page
   - Verify feature extraction works on production datasets
   - Check edge snapshot quality (similar_count, coverage_quality)
   - Validate failure case attribution

5. **Iteration on Quintile Thresholds** (~1 hour)
   - Compute actual quintiles from 2022-2025 ZZ500 universe
   - Replace `DEFAULT_QUINTILES` placeholder values
   - Re-run validation to verify improved matching

### Phase 3: Documentation (1-2 hours)

6. **Usage Documentation** (~1 hour)
   - Write `packages/screener/historical_edge/README.md`
   - API usage examples
   - Sample pool pre-computation guide
   - Troubleshooting (missing datasets, insufficient coverage)

7. **Update Project Memory** (~30 min)
   - Add memory: "阶段3 research-only: historical_edge never feeds readiness/scores"
   - Document integration points (ai_screening, decision_ledger)

---

## 🎯 Success Criteria

- [x] Core engine extracts 28 features from 8 datasets
- [x] Outcome labels computed for 5d/10d/20d windows
- [x] Bucket-based similarity matching works
- [x] Edge statistics aggregation produces win rates, returns, failure cases
- [x] 25 comprehensive unit tests pass
- [x] No deprecation warnings
- [ ] Integrated into ai_screening.py (adds `historical_edge` to candidate payload)
- [ ] Integrated into decision_ledger.py (stores in attachments)
- [ ] Sample pool cache built for ZZ500 universe
- [ ] Validated on 10 real candidates
- [ ] Usage documentation written

---

## 🛡️ Stage 3 Discipline Checklist

- [x] Every edge snapshot has `"stage": "research", "feeds_execution": False`
- [x] Edge data NEVER affects `readiness.trust_level` or `readiness_mode`
- [x] Edge data NEVER affects candidate scoring or priority
- [x] Edge data stored in `decision_record["attachments"]["historical_edge"]` only
- [x] UI treats as supplementary research insight, not execution signal

---

## 📊 Implementation Metrics

| Metric | Value |
|--------|-------|
| Production Code | ~1,400 lines |
| Test Code | ~720 lines |
| Test Coverage | 25 tests |
| Test Pass Rate | 100% |
| Features Extracted | 28 |
| Outcome Windows | 3 (5d, 10d, 20d) |
| Constraint Flags | 4 |
| Datasets Used | 8 |

---

## 🔄 Recent Changes (2026-06-04)

1. ✅ Fixed test_compute_labels_constraint_violations: Changed execution.flags snapshot date from 2023-05-15 to 2023-05-10 (must be <= trade_date for _load_series_dataset)
2. ✅ Fixed test_nth_trading_day_after: Corrected expected value for T+5 from "2023-05-16" to "2023-05-17" (count: 10→11→12→15→16→17, skipping weekend)
3. ✅ Fixed deprecation warning: Replaced `datetime.utcnow()` with `datetime.now(UTC)` in edge_analyzer.py
4. ✅ All 25 tests now pass with zero warnings

---

## 💡 Key Design Decisions

1. **Bucket-based matching (not Euclidean)**: Quintile bucketing with within-1-bucket tolerance makes the engine robust to small variations and handles missing features gracefully
2. **Conservative labels**: ±5% thresholds, errs toward "inconclusive" rather than false positives
3. **Failure transparency**: Surfaces worst 10 outcomes with constraint tags (limit-hit, suspension, ST)
4. **Lookahead bias prevention**: All features use T-1 data, labels use T+N data
5. **Sample pool pre-computation**: MVP requires a pre-built pool (weekly cron job); on-demand is acceptable for <100 candidates/day
6. **Stage 3 research-only**: Never feeds readiness gates or execution decisions

---

## 📚 Related Documentation

- [Design Document](./historical_edge_engine_design.md) - Comprehensive architecture and feature specification
- [Decision Ledger Integration](../apps/control-panel/decision_ledger.py) - Existing attachment pattern to follow
- [Data Assets](../apps/control-panel/data_assets.py) - Dataset loading patterns
- [Test Stock Formal Data](../apps/control-panel/tests/test_stock_formal_data.py) - Test isolation pattern
