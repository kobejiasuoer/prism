# packages/screener/historical_edge/tests/test_integration.py
"""Integration test for the full Historical Edge Engine pipeline."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "packages"))

from screener.historical_edge import (
    build_historical_edge_snapshot,
    build_sample_pool_for_universe,
)


def _seed(root, dataset, date, key, payload):
    """Helper to seed a dataset file for testing."""
    d = root / dataset / date
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{key}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_full_pipeline_candidate_to_edge_snapshot(tmp_path, monkeypatch):
    """Test the full pipeline: extract features → match → aggregate → snapshot."""
    root = tmp_path / "datasets"
    root.mkdir()
    monkeypatch.setenv("PRISM_DATASET_REPOSITORY_ROOT", str(root))

    # Seed trade calendar
    calendar = []
    for i in range(50):
        calendar.append({
            "cal_date": f"2023-05-{i+1:02d}" if i < 31 else f"2023-06-{i-30:02d}",
            "trade_date": f"2023-05-{i+1:02d}" if i < 31 else f"2023-06-{i-30:02d}",
            "is_open": "true",
        })
    _seed(root, "trade_calendar", "2023-06-20", "SSE", calendar)

    # Seed 10 historical samples with similar features
    universe = [f"00000{i}" for i in range(10)]
    historical_dates = [f"2023-05-{5+i:02d}" for i in range(10)]

    for code in universe:
        for date in historical_dates:
            # Valuation
            _seed(
                root,
                "valuation.daily",
                date,
                code,
                [
                    {"trade_date": date, "pe_ttm": 15.0 + hash(code+date) % 10, "pb": 2.0, "ps_ttm": 3.0, "dv_ratio": 1.5},
                ],
            )

            # Bars (for features and labels)
            bars = []
            for day_offset in range(-25, 30):
                # Parse date and compute offset
                base_day = int(date.split("-")[2])
                target_day = base_day + day_offset
                if 1 <= target_day <= 31:
                    bars.append({
                        "trade_date": f"2023-05-{target_day:02d}",
                        "close": 100.0 + day_offset * 0.5 + hash(code) % 5,
                        "high": 101.0 + day_offset * 0.5 + hash(code) % 5,
                        "low": 99.0 + day_offset * 0.5 + hash(code) % 5,
                        "open": 100.0 + day_offset * 0.5 + hash(code) % 5,
                        "volume": 1000000.0 * (1.0 + abs(day_offset) * 0.05),
                    })
            _seed(root, "bars.daily", date, code, bars)

            # Execution flags
            _seed(
                root,
                "execution.flags",
                date,
                code,
                [
                    {"trade_date": date, "is_st": "false", "is_limit_up": "false", "is_suspended": "false"},
                ],
            )

    # Build sample pool from historical data
    sample_pool = build_sample_pool_for_universe(universe, historical_dates)

    # Verify sample pool size (should have ~10 codes × 10 dates = ~100 samples, minus some missing data)
    assert len(sample_pool) > 50  # At least half should succeed

    # Now extract features for a new candidate (not in historical pool)
    candidate_code = "000099"
    candidate_date = "2023-06-10"

    # Seed candidate data
    _seed(
        root,
        "valuation.daily",
        candidate_date,
        candidate_code,
        [
            {"trade_date": candidate_date, "pe_ttm": 18.0, "pb": 2.0, "ps_ttm": 3.0, "dv_ratio": 1.5},
        ],
    )

    bars_candidate = []
    for i in range(-25, 5):
        bars_candidate.append({
            "trade_date": f"2023-06-{5+i:02d}",
            "close": 105.0 + i * 0.3,
            "high": 106.0 + i * 0.3,
            "low": 104.0 + i * 0.3,
            "open": 105.0 + i * 0.3,
            "volume": 1100000.0,
        })
    _seed(root, "bars.daily", candidate_date, candidate_code, bars_candidate)

    _seed(
        root,
        "execution.flags",
        candidate_date,
        candidate_code,
        [
            {"trade_date": candidate_date, "is_st": "false", "is_limit_up": "false", "is_suspended": "false"},
        ],
    )

    # Build edge snapshot
    snapshot = build_historical_edge_snapshot(
        candidate_code,
        candidate_date,
        sample_pool=sample_pool,
        similarity_threshold=0.3,  # Lower threshold to ensure matches
        max_matches=100,
    )

    # Assertions
    assert snapshot is not None
    assert snapshot["candidate"]["code"] == candidate_code
    assert snapshot["candidate"]["trade_date"] == candidate_date
    assert snapshot["similar_count"] > 0  # Should find some matches
    assert snapshot["coverage_quality"] in {"good", "sparse", "insufficient"}
    assert "windows" in snapshot
    assert "5d" in snapshot["windows"]
    assert "10d" in snapshot["windows"]
    assert "20d" in snapshot["windows"]
    assert snapshot["stage"] == "research"
    assert snapshot["feeds_execution"] is False


def test_build_historical_edge_snapshot_no_sample_pool(tmp_path, monkeypatch):
    """Test snapshot returns insufficient when no sample pool provided."""
    root = tmp_path / "datasets"
    root.mkdir()
    monkeypatch.setenv("PRISM_DATASET_REPOSITORY_ROOT", str(root))

    # Seed minimal candidate data
    _seed(
        root,
        "valuation.daily",
        "2023-06-10",
        "000099",
        [{"trade_date": "2023-06-10", "pe_ttm": 18.0, "pb": 2.0}],
    )

    snapshot = build_historical_edge_snapshot("000099", "2023-06-10", sample_pool=None)

    assert snapshot is not None
    assert snapshot["coverage_quality"] == "insufficient"
    assert "No sample pool provided" in snapshot["reason"]
