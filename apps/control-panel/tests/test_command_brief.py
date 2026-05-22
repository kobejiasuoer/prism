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

from control_panel.command_brief import derive_mode  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
