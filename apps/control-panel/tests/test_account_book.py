"""Tests for the canonical account book module."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

CONTROL_PANEL_ROOT = Path(__file__).resolve().parents[1]
if str(CONTROL_PANEL_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROL_PANEL_ROOT))


def _isolated_storage() -> tempfile.TemporaryDirectory:
    """Spin up a fresh sqlite store + state dir for one test."""

    return tempfile.TemporaryDirectory()


class AccountBookTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        # Force prism_storage to use a workspace under the temp dir so
        # AppStateRepository writes never collide with the live database.
        # PRISM_ACCOUNT_BOOK_PATH points the legacy fallback at the temp dir
        # too — without it, AppStateRepository would still pick up the real
        # apps/data/control_panel_state/account_book.json on every test.
        state_path = Path(self._tmp.name) / "data" / "control_panel_state" / "account_book.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        self._workspace_env = mock.patch.dict(
            os.environ,
            {
                "PRISM_REPO_ROOT": self._tmp.name,
                "PRISM_DB_PATH": str(Path(self._tmp.name) / "prism.db"),
                "PRISM_ACCOUNT_BOOK_PATH": str(state_path),
            },
        )
        self._workspace_env.start()
        self.addCleanup(self._workspace_env.stop)

        # Force-reload the modules so DEFAULT_DB_PATH picks up the env.
        for mod in (
            "prism_storage.paths",
            "prism_storage.sqlite_store",
            "prism_storage.repositories",
            "prism_storage",
            "account_book",
        ):
            sys.modules.pop(mod, None)

        import account_book  # type: ignore

        self.account_book = account_book

    def test_initial_state_is_research_mode(self) -> None:
        state = self.account_book.load_account_book()
        self.assertEqual(state["mode"], "research")
        self.assertEqual(state["cash_balance"], 0.0)
        self.assertEqual(state["fills"], [])

    def test_buy_fill_decreases_cash_and_aggregates_position(self) -> None:
        ab = self.account_book
        ab.record_cash_adjustment(delta=10000.0, reason="seed")
        ab.record_fill(
            trade_date="2026-05-06",
            code="sh600690",
            side="buy",
            qty=100,
            price=27.34,
            fees=5.0,
        )
        view = ab.compute_account_view()
        self.assertEqual(len(view["open_positions"]), 1)
        pos = view["open_positions"][0]
        self.assertEqual(pos["code"], "sh600690")
        self.assertEqual(pos["qty"], 100)
        # cost_basis = 100 * 27.34 + 5.0 = 2739.00
        self.assertAlmostEqual(pos["cost_basis"], 2739.00, places=2)
        self.assertAlmostEqual(pos["avg_cost"], 27.39, places=2)
        # cash = 10000 - 2734 - 5 = 7261
        self.assertAlmostEqual(view["cash_balance"], 7261.00, places=2)

    def test_sell_realizes_pnl_and_returns_cash(self) -> None:
        ab = self.account_book
        ab.record_cash_adjustment(delta=10000.0, reason="seed")
        ab.record_fill(
            trade_date="2026-05-06", code="sh600690", side="buy", qty=100, price=20.0, fees=0.0
        )
        ab.record_fill(
            trade_date="2026-05-07", code="sh600690", side="sell", qty=60, price=25.0, fees=0.0
        )
        view = ab.compute_account_view()
        # Realized = (25 - 20) * 60 = 300
        self.assertAlmostEqual(view["realized_pnl"], 300.0, places=2)
        # Remaining 40 @ 20 = 800 cost basis
        self.assertEqual(view["open_positions"][0]["qty"], 40)
        self.assertAlmostEqual(view["open_positions"][0]["cost_basis"], 800.0, places=2)
        # Cash = 10000 - (100*20) + (60*25) = 9500
        self.assertAlmostEqual(view["cash_balance"], 9500.0, places=2)

    def test_amend_holding_identity_updates_fills_and_position_plan(self) -> None:
        ab = self.account_book
        ab.record_cash_adjustment(delta=10000.0, reason="seed")
        ab.record_fill(
            trade_date="2026-05-06",
            code="sh000625",
            name="sh000625",
            side="buy",
            qty=500,
            price=11.21,
            fees=0.0,
        )

        state = ab.amend_holding_identity(
            from_code="sh000625",
            to_code="sz000625",
            name="长安汽车",
            reason="录入代码修正",
        )
        self.assertEqual(state["fills"][0]["code"], "sz000625")
        self.assertEqual(state["fills"][0]["name"], "长安汽车")
        self.assertEqual(state["position_plans"][0]["code"], "sz000625")
        self.assertEqual(state["position_plans"][0]["name"], "长安汽车")
        self.assertEqual(state["identity_corrections"][0]["from_code"], "sh000625")

        view = ab.compute_account_view()
        self.assertEqual(view["open_positions"][0]["code"], "sz000625")
        self.assertEqual(view["open_positions"][0]["name"], "长安汽车")

    def test_live_small_requires_cash_and_recent_reconciliation(self) -> None:
        ab = self.account_book
        # Empty book -> live_small must fail
        with self.assertRaises(ab.AccountBookError):
            ab.set_account_mode("live_small")

        # Fund the account but skip reconciliation -> still fail
        ab.record_cash_adjustment(delta=5000.0, reason="seed")
        with self.assertRaises(ab.AccountBookError):
            ab.set_account_mode("live_small")

        # Add reconciliation -> succeed
        ab.record_reconciliation(
            trade_date="2026-05-06",
            broker_cash=5000.0,
            broker_equity=0.0,
            note="initial",
        )
        state = ab.set_account_mode("live_small")
        self.assertEqual(state["mode"], "live_small")

    def test_allow_unsafe_bypasses_live_small_gate(self) -> None:
        ab = self.account_book
        state = ab.set_account_mode(
            "live_small",
            starting_cash=0,
            allow_unsafe=True,
            note="bootstrap emergency setup",
        )
        self.assertEqual(state["mode"], "live_small")
        self.assertTrue(state["unsafe_bypass_active"])

    def test_buy_in_live_small_overdrafts_blocked(self) -> None:
        ab = self.account_book
        ab.record_cash_adjustment(delta=1000.0, reason="seed")
        ab.record_reconciliation(trade_date="2026-05-06", broker_cash=1000.0, broker_equity=0.0)
        ab.set_account_mode("live_small")
        with self.assertRaises(ab.AccountBookError):
            ab.record_fill(
                trade_date="2026-05-06",
                code="sh600690",
                side="buy",
                qty=100,
                price=27.34,
                fees=5.0,
            )

    def test_no_fill_marker_replaces_prior_marker(self) -> None:
        ab = self.account_book
        ab.record_no_fill_intent(trade_date="2026-05-06", intent_key="wl-x", reason="first")
        ab.record_no_fill_intent(trade_date="2026-05-06", intent_key="wl-x", reason="second")
        state = ab.load_account_book()
        markers = [m for m in state["no_fill_intents"] if m["intent_key"] == "wl-x"]
        self.assertEqual(len(markers), 1)
        self.assertEqual(markers[0]["reason"], "second")

    def test_unreconciled_intents_finds_done_without_fill(self) -> None:
        ab = self.account_book
        decisions_store = {
            "trade_dates": {
                "2026-05-06": {
                    "wl-priority-sh600690": {"decision": "done", "updated_at": "2026-05-06 10:00:00"},
                    "wl-watch-sh600519": {"decision": "watch", "updated_at": "2026-05-06 10:00:00"},
                },
                "2026-05-07": {
                    "wl-priority-sh000001": {"decision": "done", "updated_at": "2026-05-07 09:00:00"},
                },
            },
        }

        # First call: today is 2026-05-08 -> both 05-06 and 05-07 done items
        # are unreconciled.
        unrec = ab.unreconciled_intents(today_decisions_store=decisions_store, today="2026-05-08")
        self.assertEqual(
            sorted(item["intent_key"] for item in unrec),
            ["wl-priority-sh000001", "wl-priority-sh600690"],
        )

        # Mark one with no_fill -> only one remains.
        ab.record_no_fill_intent(
            trade_date="2026-05-06",
            intent_key="wl-priority-sh600690",
            reason="exited yesterday",
        )
        unrec = ab.unreconciled_intents(today_decisions_store=decisions_store, today="2026-05-08")
        self.assertEqual([item["intent_key"] for item in unrec], ["wl-priority-sh000001"])

        # Record a fill for the other -> all clear.
        ab.record_fill(
            trade_date="2026-05-07",
            code="sh000001",
            side="buy",
            qty=100,
            price=10.0,
            fees=0.0,
            intent_key="wl-priority-sh000001",
        )
        unrec = ab.unreconciled_intents(today_decisions_store=decisions_store, today="2026-05-08")
        self.assertEqual(unrec, [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
