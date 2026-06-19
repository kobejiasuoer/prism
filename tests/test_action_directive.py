from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROL_PANEL_ROOT = REPO_ROOT / "apps" / "control-panel"
if str(CONTROL_PANEL_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROL_PANEL_ROOT))

from dashboard_data import build_action_directive  # noqa: E402


def _card(**overrides):
    base = {
        "code": "000032",
        "name": "深桑达A",
        "suggested_action": "review",
        "suggested_action_label": "等触发",
        "hard_gate_max_action": "actionable",
        "hard_gate_block_reason": None,
        "entry_plan": {
            "action": "等待突破 82.89 后回踩不破再介入",
            "trigger": "放量突破 82.89",
            "invalidate": "跌回 67.53 下方",
            "sizing": "半仓",
            "levels": {"trigger": 82.89, "invalidate": 67.53},
        },
    }
    base.update(overrides)
    return base


def test_valve_open_actionable_shows_openable():
    d = build_action_directive(_card(), valve_open=True)
    assert d["headline"] == "可开仓"
    assert d["trigger_price"] == 82.89
    assert d["invalidate_price"] == 67.53
    assert d["sizing"] == "半仓"
    assert d["blocker"] is None


def test_valve_closed_forces_observe_only():
    d = build_action_directive(_card(hard_gate_max_action="actionable"), valve_open=False)
    assert d["headline"] == "只观察"
    assert d["blocker"] is not None  # carries the reason the valve is shut


def test_hard_gate_blocked_shows_cannot_open_even_if_valve_open():
    d = build_action_directive(
        _card(hard_gate_max_action="shadow", hard_gate_block_reason="整体环境偏弱"),
        valve_open=True,
    )
    assert d["headline"] == "不可开仓"
    assert "整体环境偏弱" in d["blocker"]


def test_trial_suggested_action_shows_wait_trigger():
    d = build_action_directive(_card(suggested_action="trial", suggested_action_label="试错"), valve_open=True)
    assert d["headline"] == "等触发"


def test_missing_entry_plan_still_returns_directive():
    d = build_action_directive(_card(entry_plan=None), valve_open=True)
    assert d["headline"] in ("可开仓", "等触发", "只观察", "不可开仓", "可加仓")
    assert d["trigger_price"] is None
    assert d["invalidate_price"] is None


def test_action_text_falls_back_to_suggested_action_label():
    d = build_action_directive(_card(entry_plan=None, suggested_action_label="等触发"), valve_open=True)
    assert d["action_text"] == "等触发"


def test_add_suggested_action_shows_add_position():
    d = build_action_directive(_card(suggested_action="add", suggested_action_label="加仓"), valve_open=True)
    assert d["headline"] == "可加仓"


def test_unknown_suggested_action_falls_back():
    """An unrecognised but non-empty suggested_action (no actionable gate) → 等触发."""
    d_known = build_action_directive(
        _card(suggested_action="hold", hard_gate_max_action=None), valve_open=True
    )
    assert d_known["headline"] == "等触发"


def test_none_suggested_action_falls_to_observe():
    """A card with no suggested_action and no actionable gate → 只观察.

    Note: str(None or "") short-circuits to "" (falsy), so the else-branch's
    '等触发' if suggested' correctly yields '只观察'. This is the production-safe
    fallback for any card missing a suggested_action."""
    d_empty = build_action_directive(
        _card(suggested_action=None, suggested_action_label=None, hard_gate_max_action=None),
        valve_open=True,
    )
    assert d_empty["headline"] == "只观察"
