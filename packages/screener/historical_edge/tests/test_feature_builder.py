# packages/screener/historical_edge/tests/test_feature_builder.py
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "packages"))

from screener.historical_edge.feature_builder import (
    bucketize_features,
    extract_features,
)


def _seed(root, dataset, date, key, payload):
    """Helper to seed a dataset file for testing."""
    d = root / dataset / date
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{key}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_extract_features_valuation_momentum(tmp_path, monkeypatch):
    """Test valuation and momentum feature extraction."""
    root = tmp_path / "datasets"
    root.mkdir()
    monkeypatch.setenv("PRISM_DATASET_REPOSITORY_ROOT", str(root))

    # Seed valuation.daily with 2 days of data
    _seed(
        root,
        "valuation.daily",
        "2023-05-10",
        "000001",
        [
            {"trade_date": "2023-05-08", "pe_ttm": 12.0, "pb": 1.5, "ps_ttm": 2.0, "dv_ratio": 1.2},
            {"trade_date": "2023-05-09", "pe_ttm": 12.5, "pb": 1.6, "ps_ttm": 2.1, "dv_ratio": 1.3},
        ],
    )

    # Seed bars.daily with 20+ days for momentum calculation
    bars = []
    for i in range(25):
        bars.append({
            "trade_date": f"2023-04-{10+i:02d}" if i < 21 else f"2023-05-{i-20:02d}",
            "close": 10.0 + i * 0.5,
            "high": 10.5 + i * 0.5,
            "low": 9.5 + i * 0.5,
            "volume": 1000000.0 * (1.0 + i * 0.1),
        })
    _seed(root, "bars.daily", "2023-05-10", "000001", bars)

    features = extract_features("000001", "2023-05-10")

    # Check valuation features (should use T-1 data = 2023-05-09)
    assert features["pe_ttm"] == pytest.approx(12.5, abs=0.1)
    assert features["pb"] == pytest.approx(1.6, abs=0.1)
    assert features["ps_ttm"] == pytest.approx(2.1, abs=0.1)
    assert features["dv_ratio"] == pytest.approx(1.3, abs=0.1)

    # Check momentum features
    # return_5d: (close at bars[-1] - close at bars[-6]) / close at bars[-6] * 100
    # bars[-1] = index 24 (close 22.0), bars[-6] = index 19 (close 19.5)
    # return_5d = (22.0 - 19.5) / 19.5 * 100 = 12.82%
    assert features["return_5d"] is not None
    assert 10.0 < features["return_5d"] < 15.0  # Rough range check

    # return_10d
    assert features["return_10d"] is not None
    assert 20.0 < features["return_10d"] < 30.0

    # vol_ratio_5d: should be > 1 (volumes are increasing)
    assert features["vol_ratio_5d"] is not None
    assert features["vol_ratio_5d"] > 1.0


def test_extract_features_missing_data_graceful(tmp_path, monkeypatch):
    """Test that missing datasets return None gracefully."""
    root = tmp_path / "datasets"
    root.mkdir()
    monkeypatch.setenv("PRISM_DATASET_REPOSITORY_ROOT", str(root))

    # No datasets seeded
    features = extract_features("000001", "2023-05-10")

    # All features should be None
    assert features["pe_ttm"] is None
    assert features["return_5d"] is None
    assert features["roe"] is None
    assert features["is_st"] is None


def test_extract_features_risk_flags(tmp_path, monkeypatch):
    """Test risk flag extraction (is_st, is_limit_up_t1)."""
    root = tmp_path / "datasets"
    root.mkdir()
    monkeypatch.setenv("PRISM_DATASET_REPOSITORY_ROOT", str(root))

    # Seed execution.flags with ST and limit-up markers
    _seed(
        root,
        "execution.flags",
        "2023-05-10",
        "000001",
        [
            {"trade_date": "2023-05-08", "is_st": "false", "is_limit_up": "false", "is_suspended": "false"},
            {"trade_date": "2023-05-09", "is_st": "true", "is_limit_up": "true", "is_suspended": "false"},
        ],
    )

    features = extract_features("000001", "2023-05-10")

    # Should use T-1 data (2023-05-09)
    assert features["is_st"] == 1.0
    assert features["is_limit_up_t1"] == 1.0


def test_extract_features_liquidity_capital_flow(tmp_path, monkeypatch):
    """Test liquidity and capital flow features."""
    root = tmp_path / "datasets"
    root.mkdir()
    monkeypatch.setenv("PRISM_DATASET_REPOSITORY_ROOT", str(root))

    # Seed liquidity.daily
    liquidity_rows = []
    for i in range(25):
        liquidity_rows.append({
            "trade_date": f"2023-04-{10+i:02d}" if i < 21 else f"2023-05-{i-20:02d}",
            "turnover_rate": 3.0 + i * 0.1,
            "float_share": 5000000000.0,  # 50 billion shares
        })
    _seed(root, "liquidity.daily", "2023-05-10", "000001", liquidity_rows)

    # Seed capital_flow.daily
    capital_rows = []
    for i in range(10):
        capital_rows.append({
            "trade_date": f"2023-05-{i+1:02d}",
            "net_mf_amount": 100000.0 * (i - 5),  # Negative first, then positive
            "net_mf_ratio": (i - 5) * 2.0,
            "buy_lg_amount": 500000.0,
            "sell_lg_amount": 400000.0,
            "amount": 10000000.0,
        })
    _seed(root, "capital_flow.daily", "2023-05-10", "000001", capital_rows)

    features = extract_features("000001", "2023-05-10")

    # turnover_rate_20d_avg: should be around 3.0 + average(0..19)*0.1 = ~4.0
    assert features["turnover_rate_20d_avg"] is not None
    assert 3.5 < features["turnover_rate_20d_avg"] < 5.0

    # float_share_billions: 5000000000 / 1e8 = 50
    assert features["float_share_billions"] == pytest.approx(50.0, abs=0.1)

    # net_mf_amount_5d: sum of last 5 net_mf_amounts before T
    # rows before 2023-05-10: i=0..8 (dates 2023-05-01..09)
    # last 5: i=4,5,6,7,8 → amounts = -100k, 0, 100k, 200k, 300k → sum = 500k
    assert features["net_mf_amount_5d"] is not None
    assert 450000.0 < features["net_mf_amount_5d"] < 550000.0


def test_bucketize_features_quintiles():
    """Test feature bucketing into quintiles."""
    features = {
        "pe_ttm": 15.0,  # Falls in [10, 20] → Q2
        "return_5d": 5.0,  # Falls in [3, 8] → Q4
        "is_st": 1.0,  # Categorical, kept as-is
        "missing_feature": None,
    }

    quintiles = {
        "pe_ttm": [10.0, 20.0, 30.0, 50.0],
        "return_5d": [-5.0, 0.0, 3.0, 8.0],
    }

    bucketed = bucketize_features(features, quintiles)

    assert bucketed["pe_ttm"] == "Q2"
    assert bucketed["return_5d"] == "Q4"
    assert bucketed["is_st"] == "1.0"  # Non-quintile, converted to string
    assert bucketed["missing_feature"] is None


def test_bucketize_features_edge_cases():
    """Test bucketing edge cases (below Q1, above Q5)."""
    features = {
        "pe_ttm": 5.0,  # Below Q1 threshold (10.0) → Q1
        "return_5d": 50.0,  # Above Q5 threshold (8.0) → Q5
    }

    quintiles = {
        "pe_ttm": [10.0, 20.0, 30.0, 50.0],
        "return_5d": [-5.0, 0.0, 3.0, 8.0],
    }

    bucketed = bucketize_features(features, quintiles)

    assert bucketed["pe_ttm"] == "Q1"
    assert bucketed["return_5d"] == "Q5"
