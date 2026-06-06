# packages/screener/historical_edge/tests/test_label_builder.py
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "packages"))

from screener.historical_edge.label_builder import compute_labels, nth_trading_day_after


def _seed(root, dataset, date, key, payload):
    """Helper to seed a dataset file for testing."""
    d = root / dataset / date
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{key}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_compute_labels_5d_validated(tmp_path, monkeypatch):
    """Test label computation for a 5d validated outcome."""
    root = tmp_path / "datasets"
    root.mkdir()
    monkeypatch.setenv("PRISM_DATASET_REPOSITORY_ROOT", str(root))

    # Seed trade calendar
    calendar = []
    for i in range(30):
        calendar.append({
            "cal_date": f"2023-05-{i+1:02d}",
            "trade_date": f"2023-05-{i+1:02d}",
            "is_open": "true",
        })
    _seed(root, "trade_calendar", "2023-05-30", "SSE", calendar)

    # Seed bars: T=2023-05-10, close=100, T+5=2023-05-15, close=108 → +8% (validated)
    bars = [
        {"trade_date": "2023-05-10", "close": 100.0, "high": 101.0, "low": 99.0, "volume": 1000000.0},
        {"trade_date": "2023-05-11", "close": 102.0, "high": 103.0, "low": 100.0, "volume": 1100000.0},
        {"trade_date": "2023-05-12", "close": 104.0, "high": 105.0, "low": 101.0, "volume": 1200000.0},
        {"trade_date": "2023-05-13", "close": 106.0, "high": 107.0, "low": 103.0, "volume": 1150000.0},
        {"trade_date": "2023-05-14", "close": 107.0, "high": 108.0, "low": 105.0, "volume": 1050000.0},
        {"trade_date": "2023-05-15", "close": 108.0, "high": 109.0, "low": 106.0, "volume": 1000000.0},
    ]
    _seed(root, "bars.daily", "2023-05-15", "000001", bars)

    labels = compute_labels("000001", "2023-05-10")

    # Check 5d outcome
    assert labels["5d"]["return_pct"] == pytest.approx(8.0, abs=0.1)
    assert labels["5d"]["label"] == "validated"  # ≥5% threshold
    assert labels["5d"]["high_return_pct"] == pytest.approx(9.0, abs=0.1)  # (109-100)/100
    assert labels["5d"]["low_return_pct"] is not None


def test_compute_labels_5d_invalidated(tmp_path, monkeypatch):
    """Test label computation for a 5d invalidated outcome."""
    root = tmp_path / "datasets"
    root.mkdir()
    monkeypatch.setenv("PRISM_DATASET_REPOSITORY_ROOT", str(root))

    # Seed trade calendar
    calendar = []
    for i in range(30):
        calendar.append({
            "cal_date": f"2023-05-{i+1:02d}",
            "trade_date": f"2023-05-{i+1:02d}",
            "is_open": "true",
        })
    _seed(root, "trade_calendar", "2023-05-30", "SSE", calendar)

    # Seed bars: T=2023-05-10, close=100, T+5=2023-05-15, close=92 → -8% (invalidated)
    bars = [
        {"trade_date": "2023-05-10", "close": 100.0, "high": 101.0, "low": 99.0, "volume": 1000000.0},
        {"trade_date": "2023-05-11", "close": 98.0, "high": 100.0, "low": 97.0, "volume": 1100000.0},
        {"trade_date": "2023-05-12", "close": 95.0, "high": 98.0, "low": 94.0, "volume": 1200000.0},
        {"trade_date": "2023-05-13", "close": 93.0, "high": 96.0, "low": 92.0, "volume": 1150000.0},
        {"trade_date": "2023-05-14", "close": 91.0, "high": 94.0, "low": 90.0, "volume": 1050000.0},
        {"trade_date": "2023-05-15", "close": 92.0, "high": 93.0, "low": 89.0, "volume": 1000000.0},
    ]
    _seed(root, "bars.daily", "2023-05-15", "000001", bars)

    labels = compute_labels("000001", "2023-05-10")

    # Check 5d outcome
    assert labels["5d"]["return_pct"] == pytest.approx(-8.0, abs=0.1)
    assert labels["5d"]["label"] == "invalidated"  # ≤-5% threshold
    assert labels["5d"]["low_return_pct"] == pytest.approx(-11.0, abs=0.5)  # (89-100)/100


def test_compute_labels_constraint_violations(tmp_path, monkeypatch):
    """Test constraint violation flags (limit_hit_t1, suspension, st_flagged)."""
    root = tmp_path / "datasets"
    root.mkdir()
    monkeypatch.setenv("PRISM_DATASET_REPOSITORY_ROOT", str(root))

    # Seed trade calendar
    calendar = []
    for i in range(30):
        calendar.append({
            "cal_date": f"2023-05-{i+1:02d}",
            "trade_date": f"2023-05-{i+1:02d}",
            "is_open": "true",
        })
    _seed(root, "trade_calendar", "2023-05-30", "SSE", calendar)

    # Seed bars with T+1 limit-up (close == high == open)
    bars = [
        {"trade_date": "2023-05-10", "close": 100.0, "high": 101.0, "low": 99.0, "open": 100.0, "volume": 1000000.0},
        {"trade_date": "2023-05-11", "close": 110.0, "high": 110.0, "low": 108.0, "open": 110.0, "volume": 5000000.0},  # limit-up
        {"trade_date": "2023-05-12", "close": 112.0, "high": 113.0, "low": 109.0, "open": 110.0, "volume": 1200000.0},
    ]
    _seed(root, "bars.daily", "2023-05-15", "000001", bars)

    # Seed execution.flags with ST and suspension markers
    # IMPORTANT: snapshot date must be <= trade_date for _load_series_dataset to find it
    exec_flags = [
        {"trade_date": "2023-05-10", "is_st": "true", "is_suspended": "false", "is_limit_up": "false"},
        {"trade_date": "2023-05-11", "is_st": "true", "is_suspended": "false", "is_limit_up": "true"},
        {"trade_date": "2023-05-12", "is_st": "true", "is_suspended": "true", "is_limit_up": "false"},
    ]
    _seed(root, "execution.flags", "2023-05-10", "000001", exec_flags)  # Changed from 2023-05-15 to 2023-05-10

    labels = compute_labels("000001", "2023-05-10")

    # Check constraint flags
    assert labels["limit_hit_t1"] is True  # T+1 has limit-up pattern
    assert labels["st_flagged"] is True  # T has ST flag
    assert labels["suspension_t1_to_t5"] is True  # T+2 has suspension


def test_nth_trading_day_after(tmp_path, monkeypatch):
    """Test trade calendar navigation."""
    root = tmp_path / "datasets"
    root.mkdir()
    monkeypatch.setenv("PRISM_DATASET_REPOSITORY_ROOT", str(root))

    # Seed trade calendar with weekends skipped
    # _load_trade_calendar() only keeps rows where is_open=true, and uses cal_date
    calendar = [
        {"cal_date": "2023-05-08", "is_open": "true"},  # Mon
        {"cal_date": "2023-05-09", "is_open": "true"},  # Tue
        {"cal_date": "2023-05-10", "is_open": "true"},  # Wed
        {"cal_date": "2023-05-11", "is_open": "true"},  # Thu
        {"cal_date": "2023-05-12", "is_open": "true"},  # Fri
        {"cal_date": "2023-05-13", "is_open": "false"}, # Sat - skip
        {"cal_date": "2023-05-14", "is_open": "false"}, # Sun - skip
        {"cal_date": "2023-05-15", "is_open": "true"},  # Mon
        {"cal_date": "2023-05-16", "is_open": "true"},  # Tue
        {"cal_date": "2023-05-17", "is_open": "true"},  # Wed
        {"cal_date": "2023-05-18", "is_open": "true"},  # Thu
    ]
    _seed(root, "trade_calendar", "2023-05-10", "SSE", calendar)  # Snapshot date must be <= query date

    # Clear cache
    from screener.historical_edge import label_builder
    label_builder._TRADE_CALENDAR_CACHE = None

    t1 = nth_trading_day_after("2023-05-10", 1)
    t5 = nth_trading_day_after("2023-05-10", 5)

    assert t1 == "2023-05-11"
    assert t5 == "2023-05-17"  # 10→11(+1)→12(+2)→15(+3)→16(+4)→17(+5), skips weekend
