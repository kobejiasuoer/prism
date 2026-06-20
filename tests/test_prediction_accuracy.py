from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "apps" / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from evaluate_stock_analysis import score_prediction_accuracy  # noqa: E402


def _write_store(tmp_path: Path, records: list[dict]) -> Path:
    store = tmp_path / "exit_tracking.jsonl"
    store.parent.mkdir(parents=True, exist_ok=True)
    with store.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return store


def _settled(code, days_ago, outcome):
    from datetime import date, timedelta
    d = (date.today() - timedelta(days=days_ago)).isoformat()
    return {"code": code, "exit_date": d, "status": "settled", "outcome": outcome, "net_return": -0.05}


def test_insufficient_samples_scores_zero(tmp_path):
    """Fewer than min_samples settled records → 0 (don't reward tiny samples)."""
    store = _write_store(tmp_path, [_settled("000001", 2, "true_exit"), _settled("000002", 3, "true_exit")])
    result = score_prediction_accuracy(store=store, days=30, min_samples=5, max_points=10)
    assert result["earned"] == 0
    assert result["samples"] == 2


def test_high_true_exit_ratio_scores_full(tmp_path):
    """true_exit >= 0.7 of settled → full points (predictions accurate)."""
    records = [_settled(f"00000{i}", i, "true_exit") for i in range(7)]
    records += [_settled(f"0000{i}", i + 10, "misjudged") for i in range(3)]  # 3 misjudged
    store = _write_store(tmp_path, records)
    result = score_prediction_accuracy(store=store, days=30, min_samples=5, max_points=10)
    assert result["samples"] == 10
    assert result["true_exit_ratio"] >= 0.7
    assert result["earned"] == 10  # full


def test_high_misjudged_ratio_scores_low(tmp_path):
    """misjudged > true_exit → low score (worse than coin flip)."""
    records = [_settled(f"00000{i}", i, "true_exit") for i in range(2)]
    records += [_settled(f"0000{i}", i + 10, "misjudged") for i in range(8)]  # 8 misjudged
    store = _write_store(tmp_path, records)
    result = score_prediction_accuracy(store=store, days=30, min_samples=5, max_points=10)
    assert result["true_exit_ratio"] < 0.5
    assert result["earned"] <= 3  # low


def test_empty_store_scores_zero(tmp_path):
    store = tmp_path / "exit_tracking.jsonl"  # doesn't exist
    result = score_prediction_accuracy(store=store, days=30, min_samples=5, max_points=10)
    assert result["earned"] == 0
    assert result["samples"] == 0


def test_old_records_excluded(tmp_path):
    """Records older than `days` are excluded from the ratio."""
    records = [_settled(f"old{i}", 45, "true_exit") for i in range(10)]  # 45 days old, excluded
    store = _write_store(tmp_path, records)
    result = score_prediction_accuracy(store=store, days=30, min_samples=5, max_points=10)
    assert result["samples"] == 0
    assert result["earned"] == 0


def test_inconclusive_excluded_from_ratio(tmp_path):
    """inconclusive outcomes don't count toward true_exit or misjudged."""
    records = [_settled(f"t{i}", i, "true_exit") for i in range(5)]
    records += [{"code": f"i{i}", "exit_date": _settled("x", 1, "x")["exit_date"], "status": "settled", "outcome": "inconclusive"} for i in range(5)]
    store = _write_store(tmp_path, records)
    result = score_prediction_accuracy(store=store, days=30, min_samples=5, max_points=10)
    # 5 true_exit, 0 misjudged (5 inconclusive ignored) → ratio 1.0 → full
    assert result["true_exit_ratio"] == 1.0
    assert result["earned"] == 10
