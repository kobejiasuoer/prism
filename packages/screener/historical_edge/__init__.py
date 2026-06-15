"""Historical Edge Engine - Main API.

Public interface for computing historical edge snapshots.
"""

from __future__ import annotations

from typing import Any

from .edge_analyzer import aggregate_edge_stats, format_edge_summary_text
from .feature_builder import bucketize_features, extract_features
from .label_builder import compute_labels
from .sample_matcher import assess_coverage_quality, match_similar_samples


# Default quintile thresholds (to be computed from universe statistics)
# For MVP, we use reasonable defaults; Phase 2 would compute these from actual data
DEFAULT_QUINTILES = {
    "pe_ttm": [10.0, 20.0, 30.0, 50.0],
    "pb": [1.0, 2.0, 3.0, 5.0],
    "ps_ttm": [1.0, 2.0, 4.0, 8.0],
    "dv_ratio": [1.0, 2.0, 3.0, 5.0],
    "return_5d": [-5.0, 0.0, 3.0, 8.0],
    "return_10d": [-8.0, 0.0, 5.0, 12.0],
    "return_20d": [-12.0, 0.0, 8.0, 20.0],
    "vol_ratio_5d": [0.5, 0.8, 1.2, 2.0],
    "close_to_high_20d": [-20.0, -10.0, -5.0, -2.0],
    "rsi_14d": [30.0, 45.0, 55.0, 70.0],
    "turnover_rate_20d_avg": [2.0, 4.0, 6.0, 10.0],
    "float_share_billions": [10.0, 30.0, 80.0, 200.0],
    "volume_surge_ratio": [0.5, 0.8, 1.5, 3.0],
    "net_mf_amount_5d": [-100.0, 0.0, 100.0, 500.0],
    "net_mf_ratio": [-5.0, 0.0, 2.0, 8.0],
    "large_net_ratio": [-0.1, 0.0, 0.05, 0.15],
    "roe": [5.0, 10.0, 15.0, 25.0],
    "roa": [2.0, 5.0, 8.0, 15.0],
    "gross_margin": [10.0, 20.0, 30.0, 50.0],
    "debt_ratio": [0.2, 0.4, 0.6, 0.8],
    "hs300_return_5d": [-3.0, 0.0, 1.5, 4.0],
    "zz500_return_5d": [-4.0, 0.0, 2.0, 5.0],
    "market_vol_20d": [0.5, 1.0, 1.5, 2.5],
    "macd": [-0.5, 0.0, 0.5, 1.5],
    "kdj_k": [20.0, 40.0, 60.0, 80.0],
    "boll_position": [0.2, 0.4, 0.6, 0.8],
}


def build_historical_edge_snapshot(
    code: str,
    trade_date: str,
    *,
    sample_pool: list[tuple[str, str, dict[str, Any], dict[str, Any]]] | None = None,
    quintiles: dict[str, list[float]] | None = None,
    similarity_threshold: float = 0.5,
    max_matches: int = 100,
) -> dict[str, Any] | None:
    """Build a historical edge snapshot for a candidate.

    This is the main entry point for the Historical Edge Engine.

    Args:
        code: 6-digit stock code (e.g., "000001")
        trade_date: ISO date string "YYYY-MM-DD"
        sample_pool: Pre-built pool of (code, date, bucketed_features, labels).
                     If None, returns None (caller must provide a pool for MVP).
        quintiles: Feature quintile thresholds for bucketing. If None, uses DEFAULT_QUINTILES.
        similarity_threshold: Minimum similarity score (default 0.5)
        max_matches: Maximum number of matches to return (default 100)

    Returns:
        Edge snapshot dict, or None if extraction fails or insufficient coverage.
        On success, includes win_rate_5d, avg_return_5d, failure_cases, etc.
    """
    # Extract candidate features
    try:
        raw_features = extract_features(code, trade_date)
    except Exception:
        return None

    if not raw_features:
        return None

    # Bucketize features
    quintiles = quintiles or DEFAULT_QUINTILES
    candidate_features = bucketize_features(raw_features, quintiles)

    # If no sample pool provided, return None (MVP requires pre-built pool)
    if sample_pool is None:
        return {
            "stage": "research",
            "feeds_execution": False,
            "candidate": {"code": code, "trade_date": trade_date},
            "similar_count": 0,
            "coverage_quality": "insufficient",
            "reason": "No sample pool provided (engine requires pre-built historical sample pool)",
            "windows": {},
            "failure_cases": [],
        }

    # Match similar samples
    matches = match_similar_samples(
        candidate_features,
        sample_pool,
        threshold=similarity_threshold,
        max_matches=max_matches,
    )

    # Aggregate edge statistics
    snapshot = aggregate_edge_stats(matches, code, trade_date, candidate_features)

    return snapshot


def build_sample_pool_for_universe(
    universe: list[str],
    date_range: list[str],
    *,
    quintiles: dict[str, list[float]] | None = None,
) -> list[tuple[str, str, dict[str, Any], dict[str, Any]]]:
    """Build a sample pool (code, date, features, labels) for a given universe and date range.

    This is a helper for pre-computing the sample pool. In MVP, this would be called
    once per week to build the pool, then cached.

    Args:
        universe: List of stock codes (e.g., ["000001", "000002", ...])
        date_range: List of trade dates in ascending order (e.g., ["2022-01-04", ...])
        quintiles: Feature quintile thresholds. If None, uses DEFAULT_QUINTILES.

    Returns:
        List of (code, date, bucketed_features, labels) tuples.
    """
    quintiles = quintiles or DEFAULT_QUINTILES
    sample_pool = []

    for code in universe:
        for trade_date in date_range:
            # Extract features and labels
            try:
                raw_features = extract_features(code, trade_date)
                if not raw_features:
                    continue

                labels = compute_labels(code, trade_date)
                if not labels:
                    continue

                # Bucketize features
                bucketed_features = bucketize_features(raw_features, quintiles)

                sample_pool.append((code, trade_date, bucketed_features, labels))
            except Exception:
                # Skip samples with missing/corrupt data
                continue

    return sample_pool


__all__ = [
    "build_historical_edge_snapshot",
    "build_sample_pool_for_universe",
    "extract_features",
    "compute_labels",
    "bucketize_features",
    "match_similar_samples",
    "aggregate_edge_stats",
    "format_edge_summary_text",
    "assess_coverage_quality",
    "DEFAULT_QUINTILES",
]
