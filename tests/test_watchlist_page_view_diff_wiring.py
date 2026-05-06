"""Watchlist page view embeds the day-over-day diff.

build_watchlist_page_view loads the current snapshot and renders the
priority/follow/observe groups for the page. To answer "what changed
since yesterday", the page also needs the diff payload alongside.

These tests pin the contract:

- the page view always carries a ``diff`` field
- when a previous snapshot exists, the diff field is populated by
  :func:`diff_watchlist_snapshots`
- when no previous snapshot exists, the diff field is the well-formed
  empty shape, NOT missing or None
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROL_PANEL_ROOT = REPO_ROOT / "apps" / "control-panel"
APPS_SCRIPTS = REPO_ROOT / "apps" / "scripts"

for path in (REPO_ROOT, CONTROL_PANEL_ROOT, APPS_SCRIPTS):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)


def _stock(code: str, **overrides: Any) -> dict[str, Any]:
    base = {
        "code": code,
        "name": code,
        "action": "观望",
        "position": "0-0.5成",
        "rule_snapshot": {"signal": "中性（评分10）"},
        "trade_levels": {"support": 10.0, "resistance": 11.0, "stop_loss": 9.5},
        "hard_flags": [],
    }
    base.update(overrides)
    return base


def _normalized_payload(trade_date: str, stocks: list[dict[str, Any]]) -> dict[str, Any]:
    from prism_canonical import watchlist_group  # type: ignore

    priority = [s["code"] for s in stocks if watchlist_group(s) == "priority"]
    follow = [s["code"] for s in stocks if watchlist_group(s) == "follow"]
    observe = [s["code"] for s in stocks if watchlist_group(s) == "observe"]
    return {
        "trade_date": trade_date,
        "snapshot_path": f"/tmp/{trade_date}.json",
        "stocks": stocks,
        "stock_count": len(stocks),
        "priority_codes": priority,
        "follow_codes": follow,
        "observe_codes": observe,
    }


def test_build_watchlist_diff_returns_empty_shape_when_no_previous_snapshot(
    monkeypatch: pytest.MonkeyPatch,
):
    from dashboard_data import build_watchlist_day_over_day_diff
    from prism_canonical import resolve_previous_watchlist_snapshot_path  # noqa: F401

    today = _normalized_payload("2026-04-22", [_stock("600001")])

    # No previous snapshot file resolves.
    import dashboard_data
    monkeypatch.setattr(
        dashboard_data, "resolve_previous_watchlist_snapshot_path", lambda *_a, **_k: None
    )

    diff = build_watchlist_day_over_day_diff(today)
    assert diff["previous_trade_date"] is None
    assert diff["today_trade_date"] == "2026-04-22"
    assert diff["added"] == []
    assert diff["removed"] == []
    assert diff["action_changes"] == []


def test_build_watchlist_diff_calls_diff_function_with_loaded_previous(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
):
    from dashboard_data import build_watchlist_day_over_day_diff
    import dashboard_data

    today = _normalized_payload(
        "2026-04-22",
        [_stock("600001", action="减仓观望")],
    )
    previous = _normalized_payload(
        "2026-04-21",
        [_stock("600001", action="观望")],
    )

    fake_previous_path = tmp_path / "2026-04-21.json"
    fake_previous_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        dashboard_data,
        "resolve_previous_watchlist_snapshot_path",
        lambda _ref: fake_previous_path,
    )
    monkeypatch.setattr(
        dashboard_data,
        "load_watchlist_snapshot",
        lambda path=None: previous if str(path) == str(fake_previous_path) else None,
    )

    diff = build_watchlist_day_over_day_diff(today)
    assert diff["previous_trade_date"] == "2026-04-21"
    assert diff["today_trade_date"] == "2026-04-22"
    assert len(diff["action_changes"]) == 1
    assert diff["action_changes"][0]["code"] == "600001"


def test_build_watchlist_diff_handles_missing_today_snapshot_path(
    monkeypatch: pytest.MonkeyPatch,
):
    """A bare today payload without snapshot_path should still produce a well-formed diff."""
    from dashboard_data import build_watchlist_day_over_day_diff
    import dashboard_data

    today = {"trade_date": "2026-04-22", "stocks": [_stock("600001")]}
    monkeypatch.setattr(
        dashboard_data, "resolve_previous_watchlist_snapshot_path", lambda *_a, **_k: None
    )

    diff = build_watchlist_day_over_day_diff(today)
    assert diff["today_trade_date"] == "2026-04-22"
    assert diff["previous_trade_date"] is None


def test_build_watchlist_diff_swallows_load_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
):
    """If the previous snapshot resolves but loading it raises, the diff falls back to empty."""
    from dashboard_data import build_watchlist_day_over_day_diff
    import dashboard_data

    today = _normalized_payload("2026-04-22", [_stock("600001")])
    fake_path = tmp_path / "2026-04-21.json"
    fake_path.write_text("{}", encoding="utf-8")

    def _raise(*_a, **_k):
        raise FileNotFoundError("vanished between resolve and load")

    monkeypatch.setattr(
        dashboard_data, "resolve_previous_watchlist_snapshot_path", lambda _ref: fake_path
    )
    monkeypatch.setattr(dashboard_data, "load_watchlist_snapshot", _raise)

    diff = build_watchlist_day_over_day_diff(today)
    assert diff["previous_trade_date"] is None
    assert diff["added"] == []
    # Output must still be JSON-serializable.
    json.dumps(diff, ensure_ascii=False)
