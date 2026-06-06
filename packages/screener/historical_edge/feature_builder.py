"""Feature extraction for historical edge engine.

Extracts 28 features from Prism datasets for a given (code, trade_date) pair.
All features are lagging indicators (T-1 or earlier) to prevent lookahead bias.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


def _dataset_root() -> Path:
    """Return the dataset repository root, respecting PRISM_DATASET_REPOSITORY_ROOT env var."""
    custom_root = os.environ.get("PRISM_DATASET_REPOSITORY_ROOT")
    if custom_root:
        return Path(custom_root)
    # Default: workspace_root/data/prism_data/datasets
    this_file = Path(__file__).resolve()
    repo_root = this_file.parents[3]  # packages/screener/historical_edge/feature_builder.py → repo
    return repo_root / "data" / "prism_data" / "datasets"


def _read_json(path: Path) -> Any:
    """Read JSON file, return None if missing or corrupt."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_series_dataset(dataset: str, trade_date: str, key: str) -> list[dict[str, Any]]:
    """Load a series-style dataset (valuation.daily, liquidity.daily, etc.).

    Returns the full time series as a list of dicts, or empty list if unavailable.
    """
    root = _dataset_root()
    # Series-style datasets have one snapshot dir (e.g., "2026-05-29/")
    # but we need to find the latest available snapshot ≤ trade_date
    dataset_dir = root / dataset
    if not dataset_dir.exists():
        return []

    # Find the latest snapshot directory ≤ trade_date
    snapshot_dirs = sorted([d.name for d in dataset_dir.iterdir() if d.is_dir()])
    target_snapshot = None
    for sd in reversed(snapshot_dirs):
        if sd <= trade_date:
            target_snapshot = sd
            break

    if not target_snapshot:
        return []

    data_path = dataset_dir / target_snapshot / f"{key}.json"
    payload = _read_json(data_path)
    if isinstance(payload, list):
        return payload
    return []


def _load_snapshot_dataset(dataset: str, trade_date: str, key: str) -> list[dict[str, Any]]:
    """Load a snapshot-window style dataset (bars.daily, capital_flow.daily).

    These datasets have many snapshot dirs, each containing a rolling window.
    We read the file from the exact trade_date snapshot if available.
    """
    root = _dataset_root()
    data_path = root / dataset / trade_date / f"{key}.json"
    payload = _read_json(data_path)
    if isinstance(payload, list):
        return payload
    return []


def _find_row_for_date(rows: list[dict[str, Any]], target_date: str, date_field: str = "trade_date") -> dict[str, Any] | None:
    """Find the row matching target_date, return None if not found."""
    for row in rows:
        if str(row.get(date_field)) == target_date:
            return row
    return None


def _find_rows_before_date(rows: list[dict[str, Any]], target_date: str, date_field: str = "trade_date") -> list[dict[str, Any]]:
    """Return all rows with date < target_date, sorted ascending."""
    filtered = [r for r in rows if str(r.get(date_field)) < target_date]
    return sorted(filtered, key=lambda r: str(r.get(date_field)))


def _safe_float(value: Any) -> float | None:
    """Convert to float, return None on failure."""
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _compute_return_pct(close_start: float | None, close_end: float | None) -> float | None:
    """Compute percentage return, return None if either value is missing."""
    if close_start is None or close_end is None or close_start <= 0:
        return None
    return (close_end - close_start) / close_start * 100.0


def _compute_vol_ratio(vol_recent: float | None, vol_baseline: float | None) -> float | None:
    """Compute volume ratio, return None if either value is missing or baseline is zero."""
    if vol_recent is None or vol_baseline is None or vol_baseline <= 0:
        return None
    return vol_recent / vol_baseline


def _previous_trading_day(trade_date: str, n: int = 1) -> str | None:
    """Approximate the n-th trading day before trade_date.

    This is a simplistic implementation (calendar days - n*1.4) for now.
    A robust version would use the trade_calendar dataset.
    """
    try:
        dt = datetime.strptime(trade_date, "%Y-%m-%d")
        delta = timedelta(days=int(n * 1.4))  # Rough heuristic: ~5 trading days per 7 calendar days
        return (dt - delta).strftime("%Y-%m-%d")
    except Exception:
        return None


def extract_features(code: str, trade_date: str) -> dict[str, Any]:
    """Extract feature vector for a (code, trade_date) pair.

    Returns a dict with 28 feature keys. Values are floats or None (missing).
    Uses T-1 data where possible to avoid lookahead bias.

    Args:
        code: 6-digit stock code (e.g., "000001")
        trade_date: ISO date string "YYYY-MM-DD"

    Returns:
        Dict with feature keys:
        - Valuation (4): pe_ttm, pb, ps_ttm, dv_ratio
        - Momentum (6): return_5d, return_10d, return_20d, vol_ratio_5d, close_to_high_20d, rsi_14d
        - Liquidity (3): turnover_rate_20d_avg, float_share_billions, volume_surge_ratio
        - Capital Flow (3): net_mf_amount_5d, net_mf_ratio, large_net_ratio
        - Fundamental (4): roe, roa, gross_margin, debt_ratio
        - Market Context (3): hs300_return_5d, zz500_return_5d, market_vol_20d
        - Risk Flags (2): is_st, is_limit_up_t1
        - Technical (3): macd, kdj_k, boll_position
    """
    features: dict[str, Any] = {}

    # ========== Valuation (4 features) ==========
    valuation_rows = _load_series_dataset("valuation.daily", trade_date, code)
    # Use T-1 valuation to avoid lookahead
    t_minus_1 = _previous_trading_day(trade_date, 1)
    valuation = None
    if t_minus_1:
        valuation = _find_row_for_date(valuation_rows, t_minus_1)
    if not valuation and valuation_rows:
        # Fallback: latest available before trade_date
        past_rows = _find_rows_before_date(valuation_rows, trade_date)
        valuation = past_rows[-1] if past_rows else None

    features["pe_ttm"] = _safe_float(valuation.get("pe_ttm")) if valuation else None
    features["pb"] = _safe_float(valuation.get("pb")) if valuation else None
    features["ps_ttm"] = _safe_float(valuation.get("ps_ttm")) if valuation else None
    features["dv_ratio"] = _safe_float(valuation.get("dv_ratio")) if valuation else None

    # ========== Momentum (6 features) ==========
    bars_rows = _load_snapshot_dataset("bars.daily", trade_date, code)
    if not bars_rows:
        # Fallback: try reading from a nearby snapshot
        bars_rows = _load_series_dataset("bars.daily", trade_date, code)

    bars_before = _find_rows_before_date(bars_rows, trade_date)

    # return_5d: (close_T-1 - close_T-6) / close_T-6 * 100
    if len(bars_before) >= 6:
        close_t1 = _safe_float(bars_before[-1].get("close"))
        close_t6 = _safe_float(bars_before[-6].get("close"))
        features["return_5d"] = _compute_return_pct(close_t6, close_t1)
    else:
        features["return_5d"] = None

    # return_10d
    if len(bars_before) >= 11:
        close_t1 = _safe_float(bars_before[-1].get("close"))
        close_t11 = _safe_float(bars_before[-11].get("close"))
        features["return_10d"] = _compute_return_pct(close_t11, close_t1)
    else:
        features["return_10d"] = None

    # return_20d
    if len(bars_before) >= 21:
        close_t1 = _safe_float(bars_before[-1].get("close"))
        close_t21 = _safe_float(bars_before[-21].get("close"))
        features["return_20d"] = _compute_return_pct(close_t21, close_t1)
    else:
        features["return_20d"] = None

    # vol_ratio_5d: avg(volume_last_5d) / avg(volume_prev_15d)
    if len(bars_before) >= 20:
        vols_recent = [_safe_float(bars_before[i].get("volume")) for i in range(-5, 0)]
        vols_baseline = [_safe_float(bars_before[i].get("volume")) for i in range(-20, -5)]
        vols_recent_clean = [v for v in vols_recent if v is not None]
        vols_baseline_clean = [v for v in vols_baseline if v is not None]
        if vols_recent_clean and vols_baseline_clean:
            avg_recent = sum(vols_recent_clean) / len(vols_recent_clean)
            avg_baseline = sum(vols_baseline_clean) / len(vols_baseline_clean)
            features["vol_ratio_5d"] = _compute_vol_ratio(avg_recent, avg_baseline)
        else:
            features["vol_ratio_5d"] = None
    else:
        features["vol_ratio_5d"] = None

    # close_to_high_20d: (close_T-1 - high_last_20d) / high_last_20d * 100
    if len(bars_before) >= 20:
        close_t1 = _safe_float(bars_before[-1].get("close"))
        highs = [_safe_float(bars_before[i].get("high")) for i in range(-20, 0)]
        highs_clean = [h for h in highs if h is not None]
        if close_t1 is not None and highs_clean:
            high_20d = max(highs_clean)
            features["close_to_high_20d"] = (close_t1 - high_20d) / high_20d * 100.0 if high_20d > 0 else None
        else:
            features["close_to_high_20d"] = None
    else:
        features["close_to_high_20d"] = None

    # rsi_14d: simplified RSI (gains vs losses over 14 days)
    if len(bars_before) >= 15:
        closes = [_safe_float(bars_before[i].get("close")) for i in range(-15, 0)]
        if all(c is not None for c in closes):
            gains = []
            losses = []
            for i in range(1, len(closes)):
                delta = closes[i] - closes[i - 1]
                if delta > 0:
                    gains.append(delta)
                elif delta < 0:
                    losses.append(-delta)
            avg_gain = sum(gains) / 14 if gains else 0
            avg_loss = sum(losses) / 14 if losses else 0
            if avg_loss == 0:
                features["rsi_14d"] = 100.0
            else:
                rs = avg_gain / avg_loss
                features["rsi_14d"] = 100.0 - (100.0 / (1.0 + rs))
        else:
            features["rsi_14d"] = None
    else:
        features["rsi_14d"] = None

    # ========== Liquidity (3 features) ==========
    liquidity_rows = _load_series_dataset("liquidity.daily", trade_date, code)
    liquidity_before = _find_rows_before_date(liquidity_rows, trade_date)

    # turnover_rate_20d_avg
    if len(liquidity_before) >= 20:
        turnover_rates = [_safe_float(liquidity_before[i].get("turnover_rate")) for i in range(-20, 0)]
        turnover_clean = [t for t in turnover_rates if t is not None]
        features["turnover_rate_20d_avg"] = sum(turnover_clean) / len(turnover_clean) if turnover_clean else None
    else:
        features["turnover_rate_20d_avg"] = None

    # float_share_billions (latest available)
    if liquidity_before:
        latest_liq = liquidity_before[-1]
        float_share = _safe_float(latest_liq.get("float_share"))
        features["float_share_billions"] = float_share / 1e8 if float_share is not None else None
    else:
        features["float_share_billions"] = None

    # volume_surge_ratio: volume_T-1 / avg_volume_20d
    if len(bars_before) >= 20:
        vol_t1 = _safe_float(bars_before[-1].get("volume"))
        vols_20d = [_safe_float(bars_before[i].get("volume")) for i in range(-20, 0)]
        vols_clean = [v for v in vols_20d if v is not None]
        if vol_t1 is not None and vols_clean:
            avg_vol = sum(vols_clean) / len(vols_clean)
            features["volume_surge_ratio"] = vol_t1 / avg_vol if avg_vol > 0 else None
        else:
            features["volume_surge_ratio"] = None
    else:
        features["volume_surge_ratio"] = None

    # ========== Capital Flow (3 features) ==========
    capital_rows = _load_snapshot_dataset("capital_flow.daily", trade_date, code)
    if not capital_rows:
        capital_rows = _load_series_dataset("capital_flow.daily", trade_date, code)
    capital_before = _find_rows_before_date(capital_rows, trade_date)

    # net_mf_amount_5d: sum of net_mf_amount over last 5 days
    if len(capital_before) >= 5:
        net_mf_amounts = [_safe_float(capital_before[i].get("net_mf_amount")) for i in range(-5, 0)]
        net_mf_clean = [n for n in net_mf_amounts if n is not None]
        features["net_mf_amount_5d"] = sum(net_mf_clean) if net_mf_clean else None
    else:
        features["net_mf_amount_5d"] = None

    # net_mf_ratio (latest)
    if capital_before:
        latest_cap = capital_before[-1]
        features["net_mf_ratio"] = _safe_float(latest_cap.get("net_mf_ratio"))
    else:
        features["net_mf_ratio"] = None

    # large_net_ratio (latest)
    if capital_before:
        latest_cap = capital_before[-1]
        features["large_net_ratio"] = _safe_float(latest_cap.get("buy_lg_amount", 0)) - _safe_float(latest_cap.get("sell_lg_amount", 0))
        if features["large_net_ratio"] is not None:
            total_amount = _safe_float(latest_cap.get("amount"))
            if total_amount and total_amount > 0:
                features["large_net_ratio"] = features["large_net_ratio"] / total_amount
            else:
                features["large_net_ratio"] = None
    else:
        features["large_net_ratio"] = None

    # ========== Fundamental (4 features) ==========
    indicator_rows = _load_series_dataset("financial.indicator", trade_date, code)
    # Use the latest announced indicator before trade_date
    indicator_before = _find_rows_before_date(indicator_rows, trade_date, date_field="end_date")
    if indicator_before:
        latest_indicator = indicator_before[-1]
        features["roe"] = _safe_float(latest_indicator.get("roe"))
        features["roa"] = _safe_float(latest_indicator.get("roa"))
        features["gross_margin"] = _safe_float(latest_indicator.get("grossprofit_margin"))
        features["debt_ratio"] = _safe_float(latest_indicator.get("debt_to_assets"))
    else:
        features["roe"] = None
        features["roa"] = None
        features["gross_margin"] = None
        features["debt_ratio"] = None

    # ========== Market Context (3 features) ==========
    # HS300 return_5d
    hs300_rows = _load_series_dataset("benchmark.index_daily", trade_date, "000300")
    hs300_before = _find_rows_before_date(hs300_rows, trade_date)
    if len(hs300_before) >= 6:
        hs300_close_t1 = _safe_float(hs300_before[-1].get("close"))
        hs300_close_t6 = _safe_float(hs300_before[-6].get("close"))
        features["hs300_return_5d"] = _compute_return_pct(hs300_close_t6, hs300_close_t1)
    else:
        features["hs300_return_5d"] = None

    # ZZ500 return_5d
    zz500_rows = _load_series_dataset("benchmark.index_daily", trade_date, "000905")
    zz500_before = _find_rows_before_date(zz500_rows, trade_date)
    if len(zz500_before) >= 6:
        zz500_close_t1 = _safe_float(zz500_before[-1].get("close"))
        zz500_close_t6 = _safe_float(zz500_before[-6].get("close"))
        features["zz500_return_5d"] = _compute_return_pct(zz500_close_t6, zz500_close_t1)
    else:
        features["zz500_return_5d"] = None

    # market_vol_20d: stdev of HS300 daily returns over 20 days
    if len(hs300_before) >= 21:
        closes = [_safe_float(hs300_before[i].get("close")) for i in range(-21, 0)]
        if all(c is not None for c in closes):
            returns = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]
            mean_ret = sum(returns) / len(returns)
            variance = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
            features["market_vol_20d"] = variance ** 0.5 * 100.0  # expressed as percentage
        else:
            features["market_vol_20d"] = None
    else:
        features["market_vol_20d"] = None

    # ========== Risk Flags (2 features) ==========
    execution_rows = _load_series_dataset("execution.flags", trade_date, code)
    execution_t1 = None
    if t_minus_1:
        execution_t1 = _find_row_for_date(execution_rows, t_minus_1)
    if not execution_t1 and execution_rows:
        past_exec = _find_rows_before_date(execution_rows, trade_date)
        execution_t1 = past_exec[-1] if past_exec else None

    if execution_t1:
        features["is_st"] = 1.0 if str(execution_t1.get("is_st")).lower() in {"true", "1", "y"} else 0.0
        features["is_limit_up_t1"] = 1.0 if str(execution_t1.get("is_limit_up")).lower() in {"true", "1", "y"} else 0.0
    else:
        features["is_st"] = None
        features["is_limit_up_t1"] = None

    # ========== Technical (3 features) ==========
    stk_factor_rows = _load_series_dataset("technical.stk_factor", trade_date, code)
    stk_factor_before = _find_rows_before_date(stk_factor_rows, trade_date)
    if stk_factor_before:
        latest_factor = stk_factor_before[-1]
        features["macd"] = _safe_float(latest_factor.get("macd"))
        features["kdj_k"] = _safe_float(latest_factor.get("kdj_k"))
        # boll_position: (close - boll_lower) / (boll_upper - boll_lower)
        close = _safe_float(latest_factor.get("close"))
        boll_upper = _safe_float(latest_factor.get("boll_upper"))
        boll_lower = _safe_float(latest_factor.get("boll_lower"))
        if close is not None and boll_upper is not None and boll_lower is not None and boll_upper > boll_lower:
            features["boll_position"] = (close - boll_lower) / (boll_upper - boll_lower)
        else:
            features["boll_position"] = None
    else:
        features["macd"] = None
        features["kdj_k"] = None
        features["boll_position"] = None

    return features


def bucketize_features(features: dict[str, Any], quintiles: dict[str, list[float]]) -> dict[str, str | None]:
    """Convert continuous features into quintile buckets (Q1-Q5).

    Args:
        features: Raw feature dict from extract_features()
        quintiles: Dict mapping feature_name → [p20, p40, p60, p80] thresholds

    Returns:
        Dict mapping feature_name → "Q1"|"Q2"|"Q3"|"Q4"|"Q5"|None
    """
    bucketed = {}
    for key, value in features.items():
        if value is None:
            bucketed[key] = None
            continue

        if key in quintiles:
            thresholds = quintiles[key]
            if value <= thresholds[0]:
                bucketed[key] = "Q1"
            elif value <= thresholds[1]:
                bucketed[key] = "Q2"
            elif value <= thresholds[2]:
                bucketed[key] = "Q3"
            elif value <= thresholds[3]:
                bucketed[key] = "Q4"
            else:
                bucketed[key] = "Q5"
        else:
            # Categorical or non-bucketed feature: keep raw value as string
            bucketed[key] = str(value)

    return bucketed
