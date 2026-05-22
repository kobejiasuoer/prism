"""Unit tests for the daily command brief aggregator.

Covers mode/permits/position_cap/first_action/forbid_today/reclassify/
judgement_chain/action_lanes/midday_verify/trust derivation rules from
the design at docs/superpowers/specs/2026-05-22-daily-command-brief-design.md.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

INVEST_FLOW_ROOT = Path(__file__).resolve().parents[2]
if str(INVEST_FLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(INVEST_FLOW_ROOT))

from control_panel.command_brief import (  # noqa: E402
    derive_mode,
    derive_permits,
    derive_position_cap,
    derive_first_action,
    derive_forbid_today,
    derive_reclassify_when,
)


def _readiness(mode: str = "live_ready", **extra) -> dict[str, object]:
    base = {
        "readiness_mode": mode,
        "ready": mode == "live_ready",
        "blockers": [],
        "warnings": [],
        "expected_trade_date": "2026-05-22",
        "data_trade_date": "2026-05-22" if mode != "blocked" else None,
        "source_freshness": [],
        "quality_freshness": [],
        "recommended_tasks": [],
    }
    base.update(extra)
    return base


def _gate(allow: bool = False, label: str = "防守试错", summary: str = "弱环境，先观察") -> dict[str, object]:
    return {
        "allow_new_positions": allow,
        "label": label,
        "position_cap": "0-0.3成" if allow else "0成",
        "summary": summary,
    }


def _confirmation(confirmed: int = 0, fresh: int = 0, downgraded: int = 0) -> dict[str, object]:
    return {
        "confirmed": [{"name": f"C{i}", "code": f"60000{i}"} for i in range(confirmed)],
        "fresh_candidates": [{"name": f"F{i}", "code": f"60010{i}"} for i in range(fresh)],
        "downgraded": [{"name": f"D{i}", "code": f"60020{i}"} for i in range(downgraded)],
        "counts": {
            "confirmed": confirmed,
            "fresh_candidates": fresh,
            "downgraded": downgraded,
        },
        "validation_status": "ok",
        "generated_at": "2026-05-22 12:30:00",
    }


class ModeDerivationTest(unittest.TestCase):
    def test_blocked_readiness_forces_defense(self) -> None:
        mode = derive_mode(
            readiness=_readiness("blocked"),
            gate=_gate(allow=True, label="进攻"),
            confirmation=_confirmation(confirmed=3),
            decision_brief=None,
        )
        self.assertEqual(mode["value"], "defense")
        self.assertEqual(mode["label"], "防守")

    def test_shadow_only_is_observe(self) -> None:
        mode = derive_mode(
            readiness=_readiness("shadow_only"),
            gate=_gate(allow=True, label="进攻"),
            confirmation=_confirmation(confirmed=3),
            decision_brief=None,
        )
        self.assertEqual(mode["value"], "observe")

    def test_live_ready_gate_closed_is_observe(self) -> None:
        mode = derive_mode(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=False, label="防守试错"),
            confirmation=_confirmation(),
            decision_brief=None,
        )
        self.assertEqual(mode["value"], "observe")

    def test_live_ready_limited_label_is_probe(self) -> None:
        mode = derive_mode(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="限制进攻"),
            confirmation=_confirmation(confirmed=1),
            decision_brief=None,
        )
        self.assertEqual(mode["value"], "probe")

    def test_live_ready_offense_label_with_confirmed_is_offense(self) -> None:
        mode = derive_mode(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="进攻放开"),
            confirmation=_confirmation(confirmed=2),
            decision_brief=None,
        )
        self.assertEqual(mode["value"], "offense")

    def test_live_ready_offense_label_without_confirmed_stays_probe(self) -> None:
        mode = derive_mode(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="进攻放开"),
            confirmation=_confirmation(),
            decision_brief=None,
        )
        self.assertEqual(mode["value"], "probe")

    def test_decision_brief_override_wins(self) -> None:
        mode = derive_mode(
            readiness=_readiness("blocked"),
            gate=_gate(),
            confirmation=_confirmation(),
            decision_brief={"summary": {"today_mode": "offense"}},
        )
        self.assertEqual(mode["value"], "offense")
        self.assertIn("brief_override", mode["reasons"])


class PermitsTest(unittest.TestCase):
    def test_blocked_readiness_yields_off_off_none(self) -> None:
        permits = derive_permits(
            readiness=_readiness("blocked", blockers=[{"message": "watchlist 数据偏旧"}]),
            gate=_gate(allow=True, label="进攻"),
            confirmation=_confirmation(confirmed=3),
            screening_batch=None,
        )
        self.assertEqual(permits["data"]["value"], "off")
        self.assertEqual(permits["market"]["value"], "off")
        self.assertEqual(permits["opportunity"]["value"], "none")
        self.assertIn("watchlist 数据偏旧", permits["data"]["why"])

    def test_shadow_only_yields_shadow_off_observe(self) -> None:
        permits = derive_permits(
            readiness=_readiness("shadow_only"),
            gate=_gate(allow=True, label="放开"),
            confirmation=_confirmation(confirmed=2),
            screening_batch=None,
        )
        self.assertEqual(permits["data"]["value"], "shadow")
        self.assertEqual(permits["market"]["value"], "off")
        self.assertEqual(permits["opportunity"]["value"], "observe")

    def test_live_ready_limited_label_with_candidates_is_conditional(self) -> None:
        permits = derive_permits(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="限制试错"),
            confirmation=_confirmation(confirmed=1, fresh=2),
            screening_batch=None,
        )
        self.assertEqual(permits["market"]["value"], "limited")
        self.assertEqual(permits["opportunity"]["value"], "conditional")
        self.assertIn("新增", permits["opportunity"]["why"])

    def test_live_ready_offense_label_without_candidates_is_observe(self) -> None:
        permits = derive_permits(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="进攻放开"),
            confirmation=_confirmation(),
            screening_batch=None,
        )
        self.assertEqual(permits["market"]["value"], "on")
        self.assertEqual(permits["opportunity"]["value"], "observe")

    def test_live_ready_offense_with_candidates_is_actionable(self) -> None:
        permits = derive_permits(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="放开"),
            confirmation=_confirmation(confirmed=2),
            screening_batch=None,
        )
        self.assertEqual(permits["opportunity"]["value"], "actionable")


class FirstActionTest(unittest.TestCase):
    def test_defense_returns_recover_data_action(self) -> None:
        action = derive_first_action(
            mode_value="defense",
            action_queue={"items": []},
            readiness=_readiness("blocked"),
        )
        self.assertEqual(action["kind"], "recover_data")
        self.assertEqual(action["url"], "/settings")

    def test_takes_first_pending_stock_action(self) -> None:
        action = derive_first_action(
            mode_value="probe",
            action_queue={
                "items": [
                    {
                        "key": "watchlist:600519",
                        "title": "600519 茅台",
                        "detail": "止损 1620 已破",
                        "tone": "sell",
                        "url": "/stock/600519",
                        "decision": {"value": "pending", "label": "待处理", "tone": "sell"},
                        "display_state": {"value": "pending", "label": "待处理", "tone": "sell"},
                    }
                ]
            },
            readiness=_readiness("live_ready"),
        )
        self.assertEqual(action["kind"], "stock")
        self.assertEqual(action["url"], "/stock/600519")
        self.assertIn("600519", action["title"])

    def test_observe_with_no_pending_falls_back_to_portfolio(self) -> None:
        action = derive_first_action(
            mode_value="observe",
            action_queue={"items": []},
            readiness=_readiness("live_ready"),
        )
        self.assertEqual(action["kind"], "system")
        self.assertEqual(action["url"], "/portfolio")

    def test_probe_with_no_pending_falls_back_to_judgement_chain(self) -> None:
        action = derive_first_action(
            mode_value="probe",
            action_queue={"items": []},
            readiness=_readiness("live_ready"),
        )
        self.assertEqual(action["kind"], "system")
        self.assertEqual(action["url"], "#judgement-chain")
        self.assertIsNone(action["action_key"])


class PositionCapTest(unittest.TestCase):
    def test_takes_gate_position_cap(self) -> None:
        cap = derive_position_cap(
            mode_value="probe",
            gate=_gate(allow=True, label="试错"),
            decision_brief={"summary": {"position_cap": "0-0.3成"}},
        )
        self.assertEqual(cap["value"], "0-0.3成")
        self.assertEqual(cap["raw"], "0-0.3成")

    def test_defense_forces_zero_cap(self) -> None:
        cap = derive_position_cap(
            mode_value="defense",
            gate=_gate(allow=True, label="进攻"),
            decision_brief=None,
        )
        self.assertEqual(cap["value"], "0成")
        self.assertEqual(cap["tone"], "risk")


class ForbidTodayTest(unittest.TestCase):
    def test_defense_injects_no_new_positions(self) -> None:
        forbid = derive_forbid_today(
            mode_value="defense",
            decision_brief=None,
            action_groups=[],
        )
        titles = [item["title"] for item in forbid]
        self.assertTrue(any("不开新仓" in title for title in titles))

    def test_brief_avoid_points_are_included(self) -> None:
        forbid = derive_forbid_today(
            mode_value="probe",
            decision_brief={"focus": {"avoid_points": ["不追涨停板", "不打满仓"]}},
            action_groups=[],
        )
        titles = [item["title"] for item in forbid]
        self.assertIn("不追涨停板", titles)
        self.assertIn("不打满仓", titles)


class ReclassifyWhenTest(unittest.TestCase):
    def test_defense_has_two_paths(self) -> None:
        rules = derive_reclassify_when(
            mode_value="defense",
            readiness=_readiness("blocked"),
            gate=_gate(),
        )
        labels = [item["label"] for item in rules]
        self.assertIn("→ 观察", labels)
        self.assertIn("→ 试探", labels)

    def test_probe_has_progress_and_regression(self) -> None:
        rules = derive_reclassify_when(
            mode_value="probe",
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True),
        )
        labels = [item["label"] for item in rules]
        self.assertIn("→ 进攻", labels)
        self.assertIn("→ 观察", labels)


if __name__ == "__main__":
    unittest.main()
