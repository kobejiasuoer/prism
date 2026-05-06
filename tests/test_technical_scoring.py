from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_scoring():
    target = Path("stock-analyzer/scripts/technical_scoring.py").resolve()
    spec = importlib.util.spec_from_file_location("technical_scoring_test", target)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# --- Block 1: classify_score and threshold constants ---


def test_thresholds_are_sane_and_bull_above_bear():
    scoring = _load_scoring()
    assert isinstance(scoring.BULL_THRESHOLD, int)
    assert isinstance(scoring.BEAR_THRESHOLD, int)
    assert scoring.BULL_THRESHOLD > 0
    assert scoring.BEAR_THRESHOLD < 0
    assert scoring.BULL_THRESHOLD > scoring.BEAR_THRESHOLD


def test_classify_score_returns_bull_at_or_above_bull_threshold():
    scoring = _load_scoring()
    assert scoring.classify_score(scoring.BULL_THRESHOLD) == "bull"
    assert scoring.classify_score(scoring.BULL_THRESHOLD + 10) == "bull"


def test_classify_score_returns_bear_at_or_below_bear_threshold():
    scoring = _load_scoring()
    assert scoring.classify_score(scoring.BEAR_THRESHOLD) == "bear"
    assert scoring.classify_score(scoring.BEAR_THRESHOLD - 10) == "bear"


def test_classify_score_returns_neutral_in_the_middle():
    scoring = _load_scoring()
    middle = (scoring.BULL_THRESHOLD + scoring.BEAR_THRESHOLD) // 2
    assert scoring.classify_score(middle) == "neutral"
    assert scoring.classify_score(0) == "neutral"


# --- Block 2: indicator functions ---


def _series(n: int, start: float = 10.0, step: float = 0.1) -> list[float]:
    """Deterministic monotonically rising price series for tests."""
    return [round(start + step * i, 4) for i in range(n)]


def test_insufficient_history_is_a_value_error_subclass():
    scoring = _load_scoring()
    assert issubclass(scoring.InsufficientHistory, ValueError)


def test_calc_macd_returns_dif_dea_macd_and_prev_values():
    scoring = _load_scoring()
    closes = _series(60)
    macd = scoring.calc_macd(closes)
    assert set(macd) >= {"dif", "dea", "macd", "prev_dif", "prev_dea"}
    for key in ("dif", "dea", "macd", "prev_dif", "prev_dea"):
        assert isinstance(macd[key], float)


def test_calc_macd_raises_on_insufficient_history():
    scoring = _load_scoring()
    with pytest.raises(scoring.InsufficientHistory):
        scoring.calc_macd(_series(20))


def test_calc_kdj_returns_k_d_j_and_prev_values():
    scoring = _load_scoring()
    closes = _series(40)
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    kdj = scoring.calc_kdj(highs, lows, closes)
    assert set(kdj) >= {"k", "d", "j", "prev_k", "prev_d"}
    for key in ("k", "d", "j", "prev_k", "prev_d"):
        assert isinstance(kdj[key], float)
        # KDJ values typically in [-50, 150] for a calm series
        assert -200 < kdj[key] < 200


def test_calc_kdj_raises_on_insufficient_history():
    scoring = _load_scoring()
    with pytest.raises(scoring.InsufficientHistory):
        scoring.calc_kdj([1.0, 2.0], [0.5, 1.5], [0.8, 1.8])


def test_calc_boll_returns_upper_mid_lower_with_upper_above_lower():
    scoring = _load_scoring()
    closes = _series(40)
    boll = scoring.calc_boll(closes)
    assert set(boll) >= {"upper", "mid", "lower"}
    assert boll["upper"] > boll["mid"] > boll["lower"]


def test_calc_boll_raises_on_insufficient_history():
    scoring = _load_scoring()
    with pytest.raises(scoring.InsufficientHistory):
        scoring.calc_boll(_series(10))


def test_indicators_are_deterministic_for_same_input():
    scoring = _load_scoring()
    closes = _series(60)
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    assert scoring.calc_macd(closes) == scoring.calc_macd(closes)
    assert scoring.calc_kdj(highs, lows, closes) == scoring.calc_kdj(highs, lows, closes)
    assert scoring.calc_boll(closes) == scoring.calc_boll(closes)


# --- Block 3: calc_score_detail ---


def _bullish_inputs():
    """Inputs designed to produce a clearly bullish score."""
    closes = _series(60, start=10.0, step=0.2)  # steadily rising
    highs = [c + 0.4 for c in closes]
    lows = [c - 0.4 for c in closes]
    volumes = [1000.0 + 5.0 * i for i in range(60)]  # rising volume
    return closes, highs, lows, volumes


def _bearish_inputs():
    """Inputs designed to produce a clearly bearish score."""
    closes = _series(60, start=22.0, step=-0.2)  # steadily falling
    highs = [c + 0.4 for c in closes]
    lows = [c - 0.4 for c in closes]
    volumes = [1300.0 - 5.0 * i for i in range(60)]
    return closes, highs, lows, volumes


def test_calc_score_detail_returns_int_score_and_component_list():
    scoring = _load_scoring()
    closes, highs, lows, volumes = _bullish_inputs()
    macd = scoring.calc_macd(closes)
    kdj = scoring.calc_kdj(highs, lows, closes)
    boll = scoring.calc_boll(closes)

    score, components = scoring.calc_score_detail(
        len(closes) - 1, closes, highs, lows, volumes, macd, kdj, boll
    )
    assert isinstance(score, int)
    assert isinstance(components, list)
    assert components, "score breakdown must include at least one component"
    for entry in components:
        assert isinstance(entry, tuple)
        assert len(entry) == 2
        points, reason = entry
        assert isinstance(points, int)
        assert isinstance(reason, str) and reason.strip()


def test_calc_score_detail_score_equals_sum_of_component_points():
    scoring = _load_scoring()
    closes, highs, lows, volumes = _bullish_inputs()
    macd = scoring.calc_macd(closes)
    kdj = scoring.calc_kdj(highs, lows, closes)
    boll = scoring.calc_boll(closes)

    score, components = scoring.calc_score_detail(
        len(closes) - 1, closes, highs, lows, volumes, macd, kdj, boll
    )
    assert sum(points for points, _reason in components) == score


def test_calc_score_detail_bullish_inputs_produce_positive_score():
    scoring = _load_scoring()
    closes, highs, lows, volumes = _bullish_inputs()
    macd = scoring.calc_macd(closes)
    kdj = scoring.calc_kdj(highs, lows, closes)
    boll = scoring.calc_boll(closes)

    score, _components = scoring.calc_score_detail(
        len(closes) - 1, closes, highs, lows, volumes, macd, kdj, boll
    )
    assert score > 0
    assert scoring.classify_score(score) in {"bull", "neutral"}


def test_calc_score_detail_bearish_inputs_produce_negative_score():
    scoring = _load_scoring()
    closes, highs, lows, volumes = _bearish_inputs()
    macd = scoring.calc_macd(closes)
    kdj = scoring.calc_kdj(highs, lows, closes)
    boll = scoring.calc_boll(closes)

    score, _components = scoring.calc_score_detail(
        len(closes) - 1, closes, highs, lows, volumes, macd, kdj, boll
    )
    assert score < 0
    assert scoring.classify_score(score) in {"bear", "neutral"}


def test_calc_score_detail_is_deterministic():
    scoring = _load_scoring()
    closes, highs, lows, volumes = _bullish_inputs()
    macd = scoring.calc_macd(closes)
    kdj = scoring.calc_kdj(highs, lows, closes)
    boll = scoring.calc_boll(closes)
    a = scoring.calc_score_detail(len(closes) - 1, closes, highs, lows, volumes, macd, kdj, boll)
    b = scoring.calc_score_detail(len(closes) - 1, closes, highs, lows, volumes, macd, kdj, boll)
    assert a == b


def test_calc_score_detail_raises_when_too_few_closes_for_trend_lookback():
    scoring = _load_scoring()
    closes, highs, lows, volumes = _bullish_inputs()
    macd = scoring.calc_macd(closes)
    kdj = scoring.calc_kdj(highs, lows, closes)
    boll = scoring.calc_boll(closes)

    # Only the first 4 candles are visible — not enough history for the
    # 5-day trend or 20-day average-volume comparison.
    with pytest.raises(scoring.InsufficientHistory):
        scoring.calc_score_detail(3, closes[:4], highs[:4], lows[:4], volumes[:4], macd, kdj, boll)


# --- Block 4: fetch.py integration ---


def _load_fetch_module():
    target = Path("stock-analyzer/scripts/fetch.py").resolve()
    spec = importlib.util.spec_from_file_location("watchlist_fetch_scoring_test", target)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _synthetic_kline(n: int = 60, start: float = 10.0, step: float = 0.2) -> list[dict]:
    """Synthetic rising kline for fetch_technical_indicators."""
    bars: list[dict] = []
    for i in range(n):
        close = round(start + step * i, 4)
        bars.append(
            {
                "date": f"2026-01-{i + 1:02d}",
                "open": round(close - step / 2, 4),
                "close": close,
                "high": round(close + 0.4, 4),
                "low": round(close - 0.4, 4),
                "volume": 1000.0 + 5.0 * i,
            }
        )
    return bars


def test_fetch_technical_indicators_uses_repo_owned_scoring(monkeypatch: pytest.MonkeyPatch):
    fetch = _load_fetch_module()
    monkeypatch.setattr(fetch, "fetch_kline", lambda code, days=60: _synthetic_kline())

    result = fetch.fetch_technical_indicators("sh600519", days=60)

    assert "backtest_score" in result, "scoring branch must populate backtest_score"
    assert isinstance(result["backtest_score"], int)
    assert result["backtest_bias"] in {"bull", "bear", "neutral"}
    assert result["backtest_thresholds"] == {"bull": 30, "bear": -30}
    assert isinstance(result["backtest_components"], list)
    assert all("points" in c and "reason" in c for c in result["backtest_components"])
    assert result["backtest_signal"].startswith(("看多", "看空", "中性"))
    # Failure mode is explicit when degraded — the success path must NOT mark degraded.
    assert "backtest_degraded" not in result


def test_fetch_technical_indicators_degrades_explicitly_on_insufficient_history(
    monkeypatch: pytest.MonkeyPatch,
):
    fetch = _load_fetch_module()
    # 30 candles is enough for fetch.py's local indicators (≥35 needed by MACD,
    # so calc_macd inside the new helper raises InsufficientHistory).
    monkeypatch.setattr(fetch, "fetch_kline", lambda code, days=60: _synthetic_kline(n=30))

    result = fetch.fetch_technical_indicators("sh600519", days=30)

    assert "backtest_score" not in result
    assert result.get("backtest_degraded") is True
    assert isinstance(result.get("backtest_degraded_reason"), str)
    assert result["backtest_degraded_reason"]


def test_fetch_module_no_longer_imports_dynamic_backtest():
    source = Path("stock-analyzer/scripts/fetch.py").read_text(encoding="utf-8")
    # No more `spec_from_file_location("backtest", ...)` or "backtest.py" path-juggling.
    assert "spec_from_file_location(\"backtest\"" not in source
    assert "backtest.py\")" not in source
