# packages/screener/historical_edge/tests/test_edge_analyzer.py
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "packages"))

from screener.historical_edge.edge_analyzer import (
    aggregate_edge_stats,
    format_edge_summary_text,
)


def test_aggregate_edge_stats_insufficient_matches():
    """Test edge stats with <5 matches returns insufficient."""
    matches = [
        {"code": "000001", "date": "2023-01-05", "similarity": 0.8, "labels": {"5d": {"return_pct": 5.0, "label": "validated"}}},
        {"code": "000002", "date": "2023-01-06", "similarity": 0.75, "labels": {"5d": {"return_pct": 3.0, "label": "inconclusive"}}},
    ]

    snapshot = aggregate_edge_stats(matches, "000099", "2023-05-10", {})

    assert snapshot["coverage_quality"] == "insufficient"
    assert snapshot["similar_count"] == 2
    assert "reason" in snapshot


def test_aggregate_edge_stats_good_coverage():
    """Test edge stats with ≥20 matches."""
    # Create 25 matches: 20 validated, 3 invalidated, 2 inconclusive
    matches = []
    for i in range(20):
        matches.append({
            "code": f"00000{i:02d}",
            "date": "2023-01-05",
            "similarity": 0.9,
            "labels": {
                "5d": {"return_pct": 6.0 + i * 0.5, "label": "validated"},
                "10d": {"return_pct": 8.0 + i * 0.3, "label": "validated"},
                "20d": {"return_pct": 10.0 + i * 0.2, "label": "validated"},
            },
        })
    for i in range(3):
        matches.append({
            "code": f"99900{i}",
            "date": "2023-01-05",
            "similarity": 0.85,
            "labels": {
                "5d": {"return_pct": -7.0 - i, "label": "invalidated"},
                "10d": {"return_pct": -5.0, "label": "inconclusive"},
                "20d": {"return_pct": -3.0, "label": "inconclusive"},
                "limit_hit_t1": True,
                "suspension_t1_to_t5": False,
                "st_flagged": False,
                "extreme_vol_surge": False,
            },
        })
    for i in range(2):
        matches.append({
            "code": f"88800{i}",
            "date": "2023-01-05",
            "similarity": 0.8,
            "labels": {
                "5d": {"return_pct": 2.0, "label": "inconclusive"},
                "10d": {"return_pct": 3.0, "label": "inconclusive"},
                "20d": {"return_pct": 4.0, "label": "inconclusive"},
            },
        })

    snapshot = aggregate_edge_stats(matches, "000099", "2023-05-10", {"pe_ttm": "Q2", "return_5d": "Q4"})

    assert snapshot["coverage_quality"] == "good"
    assert snapshot["similar_count"] == 25
    assert snapshot["win_rate_5d"] == pytest.approx(20 / 25, abs=0.01)
    assert snapshot["loss_rate_5d"] == pytest.approx(3 / 25, abs=0.01)
    assert snapshot["avg_return_5d"] is not None
    assert snapshot["median_return_5d"] is not None

    # Check windows
    assert "5d" in snapshot["windows"]
    assert "10d" in snapshot["windows"]
    assert "20d" in snapshot["windows"]

    # Check failure cases
    assert len(snapshot["failure_cases"]) == 3
    assert all(f["return_5d"] < 0 for f in snapshot["failure_cases"])
    assert snapshot["failure_cases"][0]["limit_hit_t1"] is True


def test_aggregate_edge_stats_sparse_coverage():
    """Test edge stats with 5-19 matches (sparse)."""
    matches = []
    for i in range(10):
        matches.append({
            "code": f"00000{i}",
            "date": "2023-01-05",
            "similarity": 0.9,
            "labels": {
                "5d": {"return_pct": 5.0 + i, "label": "validated"},
                "10d": {"return_pct": 7.0, "label": "validated"},
                "20d": {"return_pct": 9.0, "label": "validated"},
            },
        })

    snapshot = aggregate_edge_stats(matches, "000099", "2023-05-10", {})

    assert snapshot["coverage_quality"] == "sparse"
    assert snapshot["similar_count"] == 10
    assert snapshot["win_rate_5d"] == 1.0  # All validated


def test_format_edge_summary_text_good():
    """Test summary text formatting for good coverage."""
    snapshot = {
        "coverage_quality": "good",
        "similar_count": 22,
        "win_rate_5d": 0.818,
        "avg_return_5d": 6.3,
        "failure_cases": [
            {"code": "000001", "return_5d": -8.2, "limit_hit_t1": True, "suspension_t1_to_t5": False},
            {"code": "000002", "return_5d": -6.1, "limit_hit_t1": False, "suspension_t1_to_t5": True},
        ],
    }

    summary = format_edge_summary_text(snapshot)

    assert "🎯" in summary
    assert "81% edge" in summary
    assert "22 matches" in summary
    assert "good coverage" in summary
    assert "+6.3%" in summary
    assert "2 failures" in summary
    assert "1 limit-hit" in summary
    assert "1 suspended" in summary


def test_format_edge_summary_text_insufficient():
    """Test summary text for insufficient coverage."""
    snapshot = {
        "coverage_quality": "insufficient",
        "similar_count": 2,
        "reason": "Only 2 historical matches found (minimum 5 required)",
    }

    summary = format_edge_summary_text(snapshot)

    assert "⚠️" in summary
    assert "unavailable" in summary.lower()
    assert "Only 2" in summary or "minimum 5" in summary.lower()
