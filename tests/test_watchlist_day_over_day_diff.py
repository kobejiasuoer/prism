"""Watchlist day-over-day diff and previous-snapshot resolver.

The watchlist page already classifies stocks into priority/follow/observe
lanes from a normalized snapshot. What it does *not* do is answer the
operator's most common morning question: "what changed since yesterday,
and why?".

These tests pin two new pieces in prism_canonical:

- ``resolve_previous_watchlist_snapshot_path(reference_path)`` — given a
  dated snapshot file, return the dated snapshot whose date is strictly
  earlier (the largest such date that exists).
- ``diff_watchlist_snapshots(today, previous)`` — a pure function over
  two normalized snapshot payloads (the shape ``load_watchlist_snapshot``
  returns) that emits an auditable change report covering action,
  group (priority/follow/observe), trade-level boundaries, signal text,
  and presence (added/removed).

Determinism note: orderings are alphabetical by code so two callers
asking for the same diff always get the same JSON.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

for path in (REPO_ROOT, REPO_ROOT / "apps" / "scripts"):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)


def _normalized_stock(
    code: str,
    *,
    name: str | None = None,
    action: str = "观望",
    position: str = "0-0.5成",
    signal: str = "中性（评分10）",
    support: float = 10.0,
    resistance: float = 11.0,
    stop_loss: float = 9.5,
    hard_flags: list[str] | None = None,
) -> dict[str, Any]:
    """Shape that mirrors normalize_watchlist_stock output."""
    return {
        "code": code,
        "name": name or code,
        "action": action,
        "position": position,
        "rule_snapshot": {"signal": signal},
        "trade_levels": {
            "support": support,
            "resistance": resistance,
            "stop_loss": stop_loss,
        },
        "hard_flags": hard_flags or [],
    }


def _normalized_payload(
    *,
    trade_date: str,
    stocks: list[dict[str, Any]],
) -> dict[str, Any]:
    priority, follow, observe = [], [], []
    from prism_canonical import watchlist_group  # type: ignore

    for s in stocks:
        g = watchlist_group(s)
        if g == "priority":
            priority.append(s["code"])
        elif g == "follow":
            follow.append(s["code"])
        else:
            observe.append(s["code"])
    return {
        "trade_date": trade_date,
        "stocks": stocks,
        "priority_codes": priority,
        "follow_codes": follow,
        "observe_codes": observe,
    }


# --- Block 1: previous-snapshot resolver ----


def test_resolver_returns_largest_strictly_earlier_date(tmp_path: Path):
    from prism_canonical import resolve_previous_watchlist_snapshot_path

    for d in ("2026-04-13", "2026-04-15", "2026-04-21", "2026-04-22"):
        (tmp_path / f"{d}.json").write_text("{}", encoding="utf-8")

    reference = tmp_path / "2026-04-22.json"
    result = resolve_previous_watchlist_snapshot_path(reference)
    assert result is not None
    assert result.name == "2026-04-21.json"


def test_resolver_returns_none_when_no_earlier_snapshot_exists(tmp_path: Path):
    from prism_canonical import resolve_previous_watchlist_snapshot_path

    (tmp_path / "2026-04-22.json").write_text("{}", encoding="utf-8")
    reference = tmp_path / "2026-04-22.json"
    assert resolve_previous_watchlist_snapshot_path(reference) is None


def test_resolver_skips_non_dated_files(tmp_path: Path):
    from prism_canonical import resolve_previous_watchlist_snapshot_path

    (tmp_path / "2026-04-20.json").write_text("{}", encoding="utf-8")
    (tmp_path / "latest.json").write_text("{}", encoding="utf-8")  # garbage
    (tmp_path / "2026-04-22.json").write_text("{}", encoding="utf-8")

    reference = tmp_path / "2026-04-22.json"
    result = resolve_previous_watchlist_snapshot_path(reference)
    assert result is not None
    assert result.name == "2026-04-20.json"


def test_resolver_returns_none_when_reference_itself_missing(tmp_path: Path):
    from prism_canonical import resolve_previous_watchlist_snapshot_path

    reference = tmp_path / "2026-04-22.json"  # never created
    assert resolve_previous_watchlist_snapshot_path(reference) is None


# --- Block 2: diff_watchlist_snapshots ----


def test_diff_with_no_previous_returns_empty_change_buckets():
    from prism_canonical import diff_watchlist_snapshots

    today = _normalized_payload(trade_date="2026-04-22", stocks=[_normalized_stock("600000")])
    result = diff_watchlist_snapshots(today, previous=None)
    assert result["added"] == []
    assert result["removed"] == []
    assert result["action_changes"] == []
    assert result["group_changes"] == []
    assert result["boundary_changes"] == []
    assert result["signal_changes"] == []
    assert result["previous_trade_date"] is None
    assert result["today_trade_date"] == "2026-04-22"


def test_diff_detects_added_and_removed_stocks():
    from prism_canonical import diff_watchlist_snapshots

    previous = _normalized_payload(
        trade_date="2026-04-21",
        stocks=[
            _normalized_stock("600001", name="A"),
            _normalized_stock("600002", name="B"),
        ],
    )
    today = _normalized_payload(
        trade_date="2026-04-22",
        stocks=[
            _normalized_stock("600002", name="B"),
            _normalized_stock("600003", name="C"),
        ],
    )
    result = diff_watchlist_snapshots(today, previous=previous)
    assert [s["code"] for s in result["added"]] == ["600003"]
    assert [s["code"] for s in result["removed"]] == ["600001"]


def test_diff_detects_action_change():
    from prism_canonical import diff_watchlist_snapshots

    previous = _normalized_payload(
        trade_date="2026-04-21",
        stocks=[_normalized_stock("600001", action="观望")],
    )
    today = _normalized_payload(
        trade_date="2026-04-22",
        stocks=[_normalized_stock("600001", action="减仓观望")],
    )
    result = diff_watchlist_snapshots(today, previous=previous)
    assert len(result["action_changes"]) == 1
    change = result["action_changes"][0]
    assert change["code"] == "600001"
    assert change["before"] == "观望"
    assert change["after"] == "减仓观望"


def test_diff_detects_group_change_when_action_class_shifts():
    from prism_canonical import diff_watchlist_snapshots

    previous = _normalized_payload(
        trade_date="2026-04-21",
        stocks=[_normalized_stock("600001", action="观望")],  # observe
    )
    today = _normalized_payload(
        trade_date="2026-04-22",
        stocks=[_normalized_stock("600001", action="减仓观望")],  # priority
    )
    result = diff_watchlist_snapshots(today, previous=previous)
    groups = result["group_changes"]
    assert len(groups) == 1
    assert groups[0]["code"] == "600001"
    assert groups[0]["before"] == "observe"
    assert groups[0]["after"] == "priority"


def test_diff_detects_trade_level_boundary_changes():
    from prism_canonical import diff_watchlist_snapshots

    previous = _normalized_payload(
        trade_date="2026-04-21",
        stocks=[_normalized_stock("600001", support=10.0, resistance=12.0, stop_loss=9.5)],
    )
    today = _normalized_payload(
        trade_date="2026-04-22",
        stocks=[_normalized_stock("600001", support=10.5, resistance=12.0, stop_loss=10.0)],
    )
    result = diff_watchlist_snapshots(today, previous=previous)
    fields = sorted(c["field"] for c in result["boundary_changes"])
    assert fields == ["stop_loss", "support"]
    for change in result["boundary_changes"]:
        assert change["code"] == "600001"
        assert change["before"] != change["after"]


def test_diff_does_not_emit_boundary_change_for_unchanged_levels():
    from prism_canonical import diff_watchlist_snapshots

    previous = _normalized_payload(
        trade_date="2026-04-21",
        stocks=[_normalized_stock("600001", support=10.0)],
    )
    today = _normalized_payload(
        trade_date="2026-04-22",
        stocks=[_normalized_stock("600001", support=10.0)],
    )
    result = diff_watchlist_snapshots(today, previous=previous)
    assert result["boundary_changes"] == []


def test_diff_detects_signal_text_change():
    from prism_canonical import diff_watchlist_snapshots

    previous = _normalized_payload(
        trade_date="2026-04-21",
        stocks=[_normalized_stock("600001", signal="中性（评分10）")],
    )
    today = _normalized_payload(
        trade_date="2026-04-22",
        stocks=[_normalized_stock("600001", signal="看空（评分0）")],
    )
    result = diff_watchlist_snapshots(today, previous=previous)
    assert len(result["signal_changes"]) == 1
    assert result["signal_changes"][0]["before"] == "中性（评分10）"
    assert result["signal_changes"][0]["after"] == "看空（评分0）"


def test_diff_unchanged_count_excludes_changed_stocks():
    from prism_canonical import diff_watchlist_snapshots

    previous = _normalized_payload(
        trade_date="2026-04-21",
        stocks=[
            _normalized_stock("600001", action="观望"),
            _normalized_stock("600002", action="观望"),
            _normalized_stock("600003", action="观望"),
        ],
    )
    today = _normalized_payload(
        trade_date="2026-04-22",
        stocks=[
            _normalized_stock("600001", action="减仓观望"),  # changed
            _normalized_stock("600002", action="观望"),      # same
            _normalized_stock("600003", action="观望"),      # same
        ],
    )
    result = diff_watchlist_snapshots(today, previous=previous)
    assert result["unchanged_count"] == 2


def test_diff_results_are_sorted_deterministically_by_code():
    from prism_canonical import diff_watchlist_snapshots

    previous = _normalized_payload(
        trade_date="2026-04-21",
        stocks=[
            _normalized_stock("600003", action="观望"),
            _normalized_stock("600001", action="观望"),
        ],
    )
    today = _normalized_payload(
        trade_date="2026-04-22",
        stocks=[
            _normalized_stock("600003", action="减仓观望"),
            _normalized_stock("600001", action="减仓观望"),
        ],
    )
    result = diff_watchlist_snapshots(today, previous=previous)
    codes = [c["code"] for c in result["action_changes"]]
    assert codes == sorted(codes)


def test_diff_payload_is_json_serializable():
    """The page view will embed the diff into a JSON response — guard against datetime/Path leakage."""
    from prism_canonical import diff_watchlist_snapshots

    today = _normalized_payload(
        trade_date="2026-04-22",
        stocks=[_normalized_stock("600001", action="减仓观望")],
    )
    previous = _normalized_payload(
        trade_date="2026-04-21",
        stocks=[_normalized_stock("600001", action="观望")],
    )
    result = diff_watchlist_snapshots(today, previous=previous)
    # Should not raise.
    json.dumps(result, ensure_ascii=False)


def test_diff_treats_missing_trade_levels_as_unchanged_not_as_zero():
    """If both today and previous lack a trade level, that's not a 0→0 change — it's 'no data'."""
    from prism_canonical import diff_watchlist_snapshots

    no_levels = _normalized_stock("600001")
    no_levels["trade_levels"] = {"support": 0.0, "resistance": 0.0, "stop_loss": 0.0}

    previous = _normalized_payload(trade_date="2026-04-21", stocks=[no_levels])
    today = _normalized_payload(trade_date="2026-04-22", stocks=[dict(no_levels)])
    result = diff_watchlist_snapshots(today, previous=previous)
    assert result["boundary_changes"] == []
