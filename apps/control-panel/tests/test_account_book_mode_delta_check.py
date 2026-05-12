"""Tests for set_account_mode live_small reconciliation delta check.

Phase 0 requirement: set_account_mode("live_small") must check that the
most recent reconciliation's cash/equity delta is within thresholds to
avoid UI showing live_small while readiness blocks.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

CONTROL_PANEL_ROOT = Path(__file__).resolve().parents[1]
if str(CONTROL_PANEL_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROL_PANEL_ROOT))


class SetAccountModeLiveSmallTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
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

    def test_live_small_blocks_when_cash_delta_exceeds_threshold(self) -> None:
        ab = self.account_book
        ab.record_cash_adjustment(delta=10000.0, reason="seed")
        ab.record_reconciliation(
            trade_date="2026-05-06",
            broker_cash=10150.0,  # local 10000, delta 150 > 100 threshold
            broker_equity=0.0,
        )

        with self.assertRaises(ab.AccountBookError) as ctx:
            ab.set_account_mode("live_small")
        self.assertIn("reconciliation delta within thresholds", str(ctx.exception))
        self.assertIn("cash delta 150", str(ctx.exception))

    def test_live_small_blocks_when_equity_delta_exceeds_threshold(self) -> None:
        ab = self.account_book
        ab.record_cash_adjustment(delta=10000.0, reason="seed")
        ab.record_reconciliation(
            trade_date="2026-05-06",
            broker_cash=10000.0,
            broker_equity=5300.0,  # local 5000, delta 300 > 200 threshold
        )

        with self.assertRaises(ab.AccountBookError) as ctx:
            ab.set_account_mode("live_small")
        self.assertIn("reconciliation delta within thresholds", str(ctx.exception))
        self.assertIn("equity delta", str(ctx.exception))

    def test_live_small_blocks_when_negative_delta_exceeds_threshold(self) -> None:
        ab = self.account_book
        ab.record_cash_adjustment(delta=10000.0, reason="seed")
        ab.record_reconciliation(
            trade_date="2026-05-06",
            broker_cash=9850.0,  # local 10000, delta -150, abs 150 > 100
            broker_equity=0.0,
        )

        with self.assertRaises(ab.AccountBookError) as ctx:
            ab.set_account_mode("live_small")
        self.assertIn("reconciliation delta within thresholds", str(ctx.exception))

    def test_live_small_succeeds_when_delta_within_threshold(self) -> None:
        ab = self.account_book
        ab.record_cash_adjustment(delta=10000.0, reason="seed")
        ab.record_reconciliation(
            trade_date="2026-05-06",
            broker_cash=10050.0,  # delta 50 < 100
            broker_equity=0.0,
        )

        state = ab.set_account_mode("live_small")
        self.assertEqual(state["mode"], "live_small")

    def test_allow_unsafe_requires_note_and_audits_bypass(self) -> None:
        ab = self.account_book
        ab.record_cash_adjustment(delta=10000.0, reason="seed")
        ab.record_reconciliation(
            trade_date="2026-05-06",
            broker_cash=10200.0,  # delta 200 > 100
            broker_equity=0.0,
        )

        with self.assertRaises(ab.AccountBookError) as ctx:
            ab.set_account_mode("live_small", allow_unsafe=True)
        self.assertIn("note/reason", str(ctx.exception))

        state = ab.set_account_mode("live_small", allow_unsafe=True, note="emergency ledger repair")
        self.assertEqual(state["mode"], "live_small")
        self.assertTrue(state["unsafe_bypass_active"])
        self.assertEqual(state["unsafe_bypass_note"], "emergency ledger repair")
        self.assertTrue(state["mode_history"])
        self.assertTrue(state["mode_history"][-1]["allow_unsafe"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
