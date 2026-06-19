from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROL_PANEL_ROOT = REPO_ROOT / "apps" / "control-panel"
if str(CONTROL_PANEL_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROL_PANEL_ROOT))

from dashboard_data import load_recent_exit_tracking  # noqa: E402
import dashboard_data as _dd  # noqa: E402


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def _record(code: str, exit_date: str, outcome: str, **extra) -> dict:
    return {
        "code": code,
        "name": f"测试{code}",
        "exit_date": exit_date,
        "exit_price": 10.0,
        "reason": "x",
        "theme": "y",
        "status": "settled",
        "holding_window_days": 5,
        "daily_prices": [],
        "net_return": -0.05,
        "outcome": outcome,
        "recorded_at": f"{exit_date}T09:40:00",
        **extra,
    }


def test_returns_recent_records_with_flat_fields(tmp_path: Path, monkeypatch):
    store = tmp_path / "exit_tracking.jsonl"
    today = date.today()
    recent = _record("000032", (today - timedelta(days=2)).isoformat(), "true_exit")
    old = _record("000100", (today - timedelta(days=40)).isoformat(), "misjudged")
    _write_jsonl(store, [recent, old])

    monkeypatch.setattr(_dd, "EXIT_TRACKING_STORE", store)
    result = load_recent_exit_tracking(days=30)

    assert len(result) == 1
    rec = result[0]
    assert rec["code"] == "000032"
    assert rec["outcome"] == "true_exit"
    assert rec["net_return"] == -0.05
    # holding_window_days is internal and must not leak; daily_prices is exposed
    # (for the sparkline) as a list of {date, close}.
    assert "holding_window_days" not in rec


def test_daily_prices_exposed_for_sparkline(tmp_path: Path, monkeypatch):
    """daily_prices must flow through (for the sparkline) as a list of {date, close}."""
    store = tmp_path / "exit_tracking.jsonl"
    today = date.today()
    rec = _record("000032", (today - timedelta(days=2)).isoformat(), "true_exit")
    rec["daily_prices"] = [
        {"date": today.isoformat(), "close": 9.5},
        {"date": (today - timedelta(days=1)).isoformat(), "close": 9.2},
    ]
    _write_jsonl(store, [rec])
    monkeypatch.setattr(_dd, "EXIT_TRACKING_STORE", store)
    result = load_recent_exit_tracking(days=30)
    assert len(result) == 1
    prices = result[0]["daily_prices"]
    assert isinstance(prices, list)
    assert len(prices) == 2
    assert prices[0]["close"] == 9.5


def test_missing_store_returns_empty_list(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(_dd, "EXIT_TRACKING_STORE", tmp_path / "nonexistent.jsonl")
    assert load_recent_exit_tracking(days=30) == []


def test_corrupt_jsonl_returns_empty_list(tmp_path: Path, monkeypatch):
    store = tmp_path / "exit_tracking.jsonl"
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text("{not valid json\n", encoding="utf-8")
    monkeypatch.setattr(_dd, "EXIT_TRACKING_STORE", store)
    assert load_recent_exit_tracking(days=30) == []


def test_bad_line_skipped_but_good_records_survive(tmp_path: Path, monkeypatch):
    """A single corrupt line must be skipped, not abort the whole load."""
    store = tmp_path / "exit_tracking.jsonl"
    today = date.today()
    good = _record("000032", today.isoformat(), "true_exit")
    store.parent.mkdir(parents=True, exist_ok=True)
    # good record, then a corrupt line, then another good record
    with store.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(good, ensure_ascii=False) + "\n")
        fh.write("{broken\n")
        fh.write(json.dumps(_record("000100", today.isoformat(), "misjudged"), ensure_ascii=False) + "\n")
    monkeypatch.setattr(_dd, "EXIT_TRACKING_STORE", store)
    result = load_recent_exit_tracking(days=30)
    assert len(result) == 2
    codes = {r["code"] for r in result}
    assert codes == {"000032", "000100"}


def test_sorted_by_exit_date_desc(tmp_path: Path, monkeypatch):
    store = tmp_path / "exit_tracking.jsonl"
    today = date.today()
    older = _record("000032", (today - timedelta(days=10)).isoformat(), "true_exit")
    newer = _record("000100", (today - timedelta(days=2)).isoformat(), "misjudged")
    _write_jsonl(store, [older, newer])
    monkeypatch.setattr(_dd, "EXIT_TRACKING_STORE", store)
    result = load_recent_exit_tracking(days=30)
    assert result[0]["code"] == "000100"
    assert result[1]["code"] == "000032"
