"""Edge statistics aggregation for historical edge engine.

Computes win rates, average returns, excess returns, and failure case analysis
from a set of matched historical samples.
"""

from __future__ import annotations

from typing import Any


def aggregate_edge_stats(
    matches: list[dict[str, Any]],
    candidate_code: str,
    candidate_date: str,
    candidate_features: dict[str, str | None],
) -> dict[str, Any]:
    """Aggregate edge statistics from matched historical samples.

    Args:
        matches: List of match dicts from sample_matcher.match_similar_samples()
        candidate_code: The candidate's stock code
        candidate_date: The candidate's trade date
        candidate_features: The candidate's bucketed features (for summary)

    Returns:
        Edge snapshot dict with coverage, win rates, returns, failure cases, etc.
        If insufficient coverage (<5 matches), returns a minimal dict with reason.
    """
    from datetime import datetime, UTC

    similar_count = len(matches)

    # Assess coverage quality
    if similar_count < 5:
        return {
            "stage": "research",
            "feeds_execution": False,
            "generated_at": datetime.now(UTC).isoformat(),
            "candidate": {
                "code": candidate_code,
                "trade_date": candidate_date,
            },
            "similar_count": similar_count,
            "coverage_quality": "insufficient",
            "reason": f"Only {similar_count} historical matches found (minimum 5 required)",
            "windows": {},
            "failure_cases": [],
        }

    coverage_quality = "good" if similar_count >= 20 else "sparse"

    # Aggregate statistics for each window (5d, 10d, 20d)
    windows = {}
    for window in ["5d", "10d", "20d"]:
        outcomes = []
        for match in matches:
            labels = match.get("labels", {})
            window_data = labels.get(window)
            if window_data and isinstance(window_data, dict):
                outcomes.append(window_data)

        if not outcomes:
            windows[window] = {
                "win_rate": None,
                "loss_rate": None,
                "neutral_rate": None,
                "avg_return": None,
                "median_return": None,
                "p10_return": None,
                "p90_return": None,
                "max_return": None,
                "min_return": None,
            }
            continue

        # Count outcomes by label
        win_count = sum(1 for o in outcomes if o.get("label") == "validated")
        loss_count = sum(1 for o in outcomes if o.get("label") == "invalidated")
        neutral_count = len(outcomes) - win_count - loss_count

        # Collect returns
        returns = [o.get("return_pct") for o in outcomes if o.get("return_pct") is not None]
        if not returns:
            windows[window] = {
                "win_rate": win_count / len(outcomes),
                "loss_rate": loss_count / len(outcomes),
                "neutral_rate": neutral_count / len(outcomes),
                "avg_return": None,
                "median_return": None,
                "p10_return": None,
                "p90_return": None,
                "max_return": None,
                "min_return": None,
            }
            continue

        returns_sorted = sorted(returns)
        avg_return = sum(returns) / len(returns)
        median_return = returns_sorted[len(returns) // 2]
        p10_return = returns_sorted[max(0, int(len(returns) * 0.1))]
        p90_return = returns_sorted[min(len(returns) - 1, int(len(returns) * 0.9))]
        max_return = max(returns)
        min_return = min(returns)

        windows[window] = {
            "win_rate": win_count / len(outcomes),
            "loss_rate": loss_count / len(outcomes),
            "neutral_rate": neutral_count / len(outcomes),
            "avg_return": round(avg_return, 2),
            "median_return": round(median_return, 2),
            "p10_return": round(p10_return, 2),
            "p90_return": round(p90_return, 2),
            "max_return": round(max_return, 2),
            "min_return": round(min_return, 2),
        }

    # Compute excess return vs HS300 benchmark (5d window)
    excess_return_vs_hs300 = None
    if "5d" in windows and windows["5d"]["avg_return"] is not None:
        # Extract hs300_return_5d from candidate_features (if available and numeric)
        # This is approximate; ideally we'd pull the actual HS300 return for the candidate's date
        # For now, we compute average hs300 return from matched samples' feature context
        hs300_returns = []
        for match in matches:
            # Attempt to extract benchmark return from match context
            # This requires feature_builder to have stored it; for MVP, we skip this
            pass
        # Simplified: assume no benchmark data available for now
        # In Phase 2, we'd store benchmark returns alongside labels
        excess_return_vs_hs300 = None  # Placeholder

    # Failure case analysis (5d window, invalidated outcomes)
    failure_cases = []
    for match in matches:
        labels = match.get("labels", {})
        window_5d = labels.get("5d", {})
        if window_5d.get("label") == "invalidated":
            failure_cases.append({
                "code": match["code"],
                "date": match["date"],
                "similarity": round(match["similarity"], 3),
                "return_5d": round(window_5d.get("return_pct", 0.0), 2),
                "limit_hit_t1": labels.get("limit_hit_t1", False),
                "suspension_t1_to_t5": labels.get("suspension_t1_to_t5", False),
                "st_flagged": labels.get("st_flagged", False),
                "extreme_vol_surge": labels.get("extreme_vol_surge", False),
            })

    # Sort failure cases by return_5d ascending (worst first), limit to top 10
    failure_cases.sort(key=lambda f: f["return_5d"])
    failure_cases = failure_cases[:10]

    # Feature summary (for interpretability)
    feature_summary = {}
    for key in ["pe_ttm", "return_5d", "return_20d", "turnover_rate_20d_avg", "roe", "is_st"]:
        if key in candidate_features:
            feature_summary[key + "_bucket"] = candidate_features[key]

    # Assemble final snapshot
    snapshot = {
        "stage": "research",
        "feeds_execution": False,
        "generated_at": datetime.now(UTC).isoformat(),
        "candidate": {
            "code": candidate_code,
            "trade_date": candidate_date,
        },
        "similar_count": similar_count,
        "coverage_quality": coverage_quality,
        "win_rate_5d": windows.get("5d", {}).get("win_rate"),
        "loss_rate_5d": windows.get("5d", {}).get("loss_rate"),
        "avg_return_5d": windows.get("5d", {}).get("avg_return"),
        "median_return_5d": windows.get("5d", {}).get("median_return"),
        "excess_return_vs_hs300": excess_return_vs_hs300,
        "windows": windows,
        "failure_cases": failure_cases,
        "feature_summary": feature_summary,
    }

    return snapshot


def format_edge_summary_text(snapshot: dict[str, Any]) -> str:
    """Format edge snapshot as a concise human-readable summary.

    Example output:
    "🎯 82% edge (22 matches, good coverage): avg +6.3%, 4 failures (2 limit-hit)"

    Returns:
        Single-line summary string
    """
    coverage = snapshot.get("coverage_quality")
    if coverage == "insufficient":
        reason = snapshot.get("reason", "insufficient data")
        return f"⚠️  Historical edge unavailable: {reason}"

    count = snapshot.get("similar_count", 0)
    win_rate = snapshot.get("win_rate_5d")
    avg_return = snapshot.get("avg_return_5d")
    failures = snapshot.get("failure_cases", [])
    failure_count = len(failures)

    win_pct = int(win_rate * 100) if win_rate is not None else "?"
    avg_ret_str = f"{avg_return:+.1f}%" if avg_return is not None else "??"

    # Count failure types
    limit_hit_count = sum(1 for f in failures if f.get("limit_hit_t1"))
    suspension_count = sum(1 for f in failures if f.get("suspension_t1_to_t5"))

    failure_detail = []
    if limit_hit_count:
        failure_detail.append(f"{limit_hit_count} limit-hit")
    if suspension_count:
        failure_detail.append(f"{suspension_count} suspended")
    failure_str = ", ".join(failure_detail) if failure_detail else ""

    summary = f"🎯 {win_pct}% edge ({count} matches, {coverage} coverage): avg {avg_ret_str}"
    if failure_count:
        summary += f", {failure_count} failures"
        if failure_str:
            summary += f" ({failure_str})"

    return summary
