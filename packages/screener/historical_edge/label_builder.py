"""Outcome label generation for historical edge engine.

Computes forward-looking returns (5d/10d/20d windows) and constraint violations
for a historical (code, trade_date) pair.
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
    this_file = Path(__file__).resolve()
    repo_root = this_file.parents[3]
    return repo_root / "data" / "prism_data" / "datasets"


def _read_json(path: Path) -> Any:
    """Read JSON file, return None if missing or corrupt."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_series_dataset(dataset: str, trade_date: str, key: str) -> list[dict[str, Any]]:
    """Load a series-style dataset."""
    root = _dataset_root()
    dataset_dir = root / dataset
    if not dataset_dir.exists():
        return []

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
    """Load a snapshot-window style dataset."""
    root = _dataset_root()
    data_path = root / dataset / trade_date / f"{key}.json"
    payload = _read_json(data_path)
    if isinstance(payload, list):
        return payload
    return []


def _find_row_for_date(rows: list[dict[str, Any]], target_date: str, date_field: str = "trade_date") -> dict[str, Any] | None:
    """Find the row matching target_date."""
    for row in rows:
        if str(row.get(date_field)) == target_date:
            return row
    return None


def _find_rows_in_window(rows: list[dict[str, Any]], start_date: str, end_date: str, date_field: str = "trade_date") -> list[dict[str, Any]]:
    """Return all rows with start_date <= date <= end_date, sorted ascending."""
    filtered = [r for r in rows if start_date <= str(r.get(date_field)) <= end_date]
    return sorted(filtered, key=lambda r: str(r.get(date_field)))


def _safe_float(value: Any) -> float | None:
    """Convert to float, return None on failure."""
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _load_trade_calendar() -> list[str]:
    """Load the trade calendar dataset, return list of trade dates in ascending order."""
    root = _dataset_root()
    calendar_dir = root / "trade_calendar"
    if not calendar_dir.exists():
        return []

    # Trade calendar is typically stored as a single file or per-year files
    # Try loading from a snapshot
    snapshot_dirs = sorted([d.name for d in calendar_dir.iterdir() if d.is_dir()])
    if not snapshot_dirs:
        return []

    latest_snapshot = snapshot_dirs[-1]
    data_path = calendar_dir / latest_snapshot / "SSE.json"  # Shanghai Stock Exchange calendar
    if not data_path.exists():
        data_path = calendar_dir / latest_snapshot / "calendar.json"

    payload = _read_json(data_path)
    if isinstance(payload, list):
        # Extract trade dates where is_open is True
        trade_dates = [
            str(row.get("cal_date") or row.get("trade_date"))
            for row in payload
            if str(row.get("is_open")).lower() in {"true", "1", "y"}
        ]
        return sorted(trade_dates)
    return []


_TRADE_CALENDAR_CACHE: list[str] | None = None


def nth_trading_day_after(trade_date: str, n: int) -> str | None:
    """Return the n-th trading day strictly after trade_date.

    Uses the trade_calendar dataset. Returns None if not available.
    """
    global _TRADE_CALENDAR_CACHE

    if n < 1:
        return None

    if _TRADE_CALENDAR_CACHE is None:
        _TRADE_CALENDAR_CACHE = _load_trade_calendar()

    if not _TRADE_CALENDAR_CACHE:
        return None

    try:
        idx = _TRADE_CALENDAR_CACHE.index(trade_date)
    except ValueError:
        return None

    target_idx = idx + n
    if target_idx >= len(_TRADE_CALENDAR_CACHE):
        return None

    return _TRADE_CALENDAR_CACHE[target_idx]


def compute_labels(code: str, trade_date: str) -> dict[str, Any]:
    """Compute outcome labels for a (code, trade_date) pair.

    Args:
        code: 6-digit stock code
        trade_date: ISO date string "YYYY-MM-DD" (the "decision date" T)

    Returns:
        Dict with outcome windows and constraint flags:
        {
            "5d": {"return_pct": ..., "high_return_pct": ..., "low_return_pct": ..., "label": ...},
            "10d": {...},
            "20d": {...},
            "limit_hit_t1": bool,
            "suspension_t1_to_t5": bool,
            "st_flagged": bool,
            "extreme_vol_surge": bool,
        }
    """
    labels: dict[str, Any] = {}

    # Load bars for return computation
    # Try loading from multiple snapshots to cover the full forward window
    bars_rows = _load_snapshot_dataset("bars.daily", trade_date, code)
    if not bars_rows:
        bars_rows = _load_series_dataset("bars.daily", trade_date, code)

    # We need bars from T to T+20
    # Collect bars from T onwards
    bars_from_t = [r for r in bars_rows if str(r.get("trade_date")) >= trade_date]
    bars_from_t = sorted(bars_from_t, key=lambda r: str(r.get("trade_date")))

    # If we don't have enough forward bars, try loading from later snapshots
    if len(bars_from_t) < 25:
        # Attempt to load from a later snapshot (e.g., T+30 days)
        later_date = nth_trading_day_after(trade_date, 30)
        if later_date:
            bars_rows_later = _load_snapshot_dataset("bars.daily", later_date, code)
            if not bars_rows_later:
                bars_rows_later = _load_series_dataset("bars.daily", later_date, code)
            bars_from_t_later = [r for r in bars_rows_later if str(r.get("trade_date")) >= trade_date]
            # Merge and deduplicate
            all_bars = {str(r.get("trade_date")): r for r in bars_from_t + bars_from_t_later}
            bars_from_t = sorted(all_bars.values(), key=lambda r: str(r.get("trade_date")))

    # Compute outcomes for 5d, 10d, 20d windows
    for window, n_days in [("5d", 5), ("10d", 10), ("20d", 20)]:
        end_date = nth_trading_day_after(trade_date, n_days)
        if not end_date:
            labels[window] = {
                "return_pct": None,
                "high_return_pct": None,
                "low_return_pct": None,
                "label": "data_issue",
            }
            continue

        # Find T and T+N bars
        bar_t = _find_row_for_date(bars_from_t, trade_date)
        bar_tn = _find_row_for_date(bars_from_t, end_date)

        if not bar_t or not bar_tn:
            labels[window] = {
                "return_pct": None,
                "high_return_pct": None,
                "low_return_pct": None,
                "label": "data_issue",
            }
            continue

        close_t = _safe_float(bar_t.get("close"))
        close_tn = _safe_float(bar_tn.get("close"))

        if close_t is None or close_t <= 0 or close_tn is None:
            labels[window] = {
                "return_pct": None,
                "high_return_pct": None,
                "low_return_pct": None,
                "label": "data_issue",
            }
            continue

        return_pct = (close_tn - close_t) / close_t * 100.0

        # Compute high_return_pct: max intraday high from T+1 to T+N
        bars_window = _find_rows_in_window(bars_from_t, nth_trading_day_after(trade_date, 1) or trade_date, end_date)
        highs = [_safe_float(r.get("high")) for r in bars_window]
        highs_clean = [h for h in highs if h is not None]
        if highs_clean:
            max_high = max(highs_clean)
            high_return_pct = (max_high - close_t) / close_t * 100.0
        else:
            high_return_pct = return_pct  # Fallback

        # Compute low_return_pct: min intraday low from T+1 to T+N
        lows = [_safe_float(r.get("low")) for r in bars_window]
        lows_clean = [l for l in lows if l is not None]
        if lows_clean:
            min_low = min(lows_clean)
            low_return_pct = (min_low - close_t) / close_t * 100.0
        else:
            low_return_pct = return_pct  # Fallback

        # Classify outcome using simple thresholds (aligned with decision_ledger defaults)
        # For trial_buy/hold actions: validated >= +5%, invalidated <= -5%
        if return_pct >= 5.0:
            label = "validated"
        elif return_pct <= -5.0:
            label = "invalidated"
        else:
            label = "inconclusive"

        labels[window] = {
            "return_pct": return_pct,
            "high_return_pct": high_return_pct,
            "low_return_pct": low_return_pct,
            "label": label,
        }

    # ========== Constraint Violations ==========

    # limit_hit_t1: Did the stock hit limit up/down on T+1?
    t1_date = nth_trading_day_after(trade_date, 1)
    labels["limit_hit_t1"] = False
    if t1_date:
        bar_t1 = _find_row_for_date(bars_from_t, t1_date)
        if bar_t1:
            open_t1 = _safe_float(bar_t1.get("open"))
            high_t1 = _safe_float(bar_t1.get("high"))
            low_t1 = _safe_float(bar_t1.get("low"))
            close_t1 = _safe_float(bar_t1.get("close"))
            # Heuristic: limit-up if close == high and close ~= open, or limit-down if close == low
            if close_t1 and high_t1 and low_t1:
                if abs(close_t1 - high_t1) < 0.01 and abs(close_t1 - open_t1) < 0.01:
                    labels["limit_hit_t1"] = True
                elif abs(close_t1 - low_t1) < 0.01 and abs(close_t1 - open_t1) < 0.01:
                    labels["limit_hit_t1"] = True

    # suspension_t1_to_t5: Was the stock suspended during T+1 to T+5?
    labels["suspension_t1_to_t5"] = False
    execution_rows = _load_series_dataset("execution.flags", trade_date, code)
    if execution_rows:
        t1_date = nth_trading_day_after(trade_date, 1)
        t5_date = nth_trading_day_after(trade_date, 5)
        if t1_date and t5_date:
            exec_window = _find_rows_in_window(execution_rows, t1_date, t5_date)
            for row in exec_window:
                if str(row.get("is_suspended")).lower() in {"true", "1", "y"}:
                    labels["suspension_t1_to_t5"] = True
                    break

    # st_flagged: Was ST status active on T?
    labels["st_flagged"] = False
    if execution_rows:
        exec_t = _find_row_for_date(execution_rows, trade_date)
        if exec_t and str(exec_t.get("is_st")).lower() in {"true", "1", "y"}:
            labels["st_flagged"] = True

    # extreme_vol_surge: Was volume on T or T+1 > 5× the 20d average?
    labels["extreme_vol_surge"] = False
    if len(bars_from_t) >= 21:
        # Compute 20d avg volume ending at T-1
        bars_before_t = [r for r in bars_rows if str(r.get("trade_date")) < trade_date]
        bars_before_t = sorted(bars_before_t, key=lambda r: str(r.get("trade_date")))
        if len(bars_before_t) >= 20:
            vols_20d = [_safe_float(bars_before_t[i].get("volume")) for i in range(-20, 0)]
            vols_clean = [v for v in vols_20d if v is not None]
            if vols_clean:
                avg_vol_20d = sum(vols_clean) / len(vols_clean)
                # Check T and T+1 volume
                bar_t = _find_row_for_date(bars_from_t, trade_date)
                vol_t = _safe_float(bar_t.get("volume")) if bar_t else None
                if vol_t and vol_t > 5 * avg_vol_20d:
                    labels["extreme_vol_surge"] = True
                if t1_date:
                    bar_t1 = _find_row_for_date(bars_from_t, t1_date)
                    vol_t1 = _safe_float(bar_t1.get("volume")) if bar_t1 else None
                    if vol_t1 and vol_t1 > 5 * avg_vol_20d:
                        labels["extreme_vol_surge"] = True

    return labels
