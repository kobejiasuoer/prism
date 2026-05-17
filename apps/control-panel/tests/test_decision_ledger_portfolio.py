"""Phase 3 integration tests: Portfolio / Today writeback -> Ledger.

These tests boot the real FastAPI app with a temp ledger root and
account-book path, capture decisions through the ledger module
directly, then assert that the three writeback endpoints attach
ExecutionEvents idempotently and that ledger failure never blocks the
canonical Portfolio / Today behavior.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient


INVEST_FLOW_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_ROOT = INVEST_FLOW_ROOT.parent / "packages"
if str(INVEST_FLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(INVEST_FLOW_ROOT))
if str(PACKAGES_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGES_ROOT))


def _sample_decision_kwargs(**overrides):
    base = {
        "trade_date": "2026-05-15",
        "code": "sh600690",
        "name": "海尔智家",
        "lane": "watchlist",
        "surface": "today_action_queue",
        "action_key": "watchlist:600690",
        "source_label": "自选股链路",
        "action": "hold",
        "action_label": "继续持有",
        "main_conclusion": "继续持有，但不加仓",
        "position_guidance": "半仓以内",
        "trigger_condition": "放量站回关键均线",
        "continue_condition": "不跌破趋势线",
        "stop_condition": "跌破止损线",
        "risk_summary": "弱市中只按纪律处理",
        "expected_trade_date": "2026-05-15",
        "data_trade_date": "2026-05-15",
        "readiness_mode": "live_ready",
        "readiness_ready": True,
        "blockers": [],
        "warnings": [],
    }
    base.update(overrides)
    return base


class LedgerPortfolioIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

        self.ledger_root = Path(self._tmp.name) / "decision_ledger"
        state_path = Path(self._tmp.name) / "data" / "control_panel_state" / "account_book.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)

        self._env = mock.patch.dict(
            os.environ,
            {
                "PRISM_REPO_ROOT": self._tmp.name,
                "PRISM_DB_PATH": str(Path(self._tmp.name) / "prism.db"),
                "PRISM_ACCOUNT_BOOK_PATH": str(state_path),
                "PRISM_DECISION_LEDGER_PATH": str(self.ledger_root),
            },
        )
        self._env.start()
        self.addCleanup(self._env.stop)

        # Drop everything that caches paths or DB handles so the temp
        # workspace wins.  Same approach as test_portfolio_endpoints.
        modules_to_drop = [
            name
            for name in list(sys.modules)
            if name.startswith("_prism_legacy_control_panel_")
        ]
        modules_to_drop.extend(
            [
                "prism_storage.paths",
                "prism_storage.sqlite_store",
                "prism_storage.repositories",
                "prism_storage",
                "account_book",
                "readiness",
                "trading_calendar",
                "decision_ledger",
                "control_panel.dashboard_data",
                "control_panel.app",
            ]
        )
        for mod in modules_to_drop:
            sys.modules.pop(mod, None)

        from control_panel.app import app  # type: ignore  # noqa: E402
        import decision_ledger  # type: ignore  # noqa: E402

        self.client = TestClient(app)
        self.ledger = decision_ledger

        # Make sure the account book is in shadow mode + seeded so the
        # fills endpoint can land buys without tripping live_small
        # guards.
        self.client.post(
            "/api/portfolio/mode",
            json={"mode": "shadow", "starting_cash": 0.0},
        )
        self.client.post(
            "/api/portfolio/cash",
            json={"delta": 50000.0, "reason": "seed"},
        )

    def _capture_decision(self, **overrides) -> dict:
        kwargs = _sample_decision_kwargs(**overrides)
        record = self.ledger.build_decision_record(**kwargs)
        return self.ledger.upsert_decision(record)

    # ----------------------------------------------- /api/portfolio/fills

    def test_fill_attaches_filled_event_when_decision_matches(self) -> None:
        captured = self._capture_decision()
        response = self.client.post(
            "/api/portfolio/fills",
            json={
                "trade_date": "2026-05-15",
                "code": "sh600690",
                "side": "buy",
                "qty": 100,
                "price": 28.35,
                "fees": 5.0,
                "name": "海尔智家",
                "intent_key": "watchlist:600690",
                "note": "轻仓试错",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        # Original Portfolio response shape must be preserved.
        self.assertIn("account", body)
        # Ledger attachment surfaces at the top level.
        ledger = body.get("ledger") or {}
        self.assertTrue(ledger.get("attached"))
        self.assertEqual(ledger.get("decision_id"), captured["decision_id"])
        self.assertEqual(ledger.get("status"), "filled")

        stored = self.ledger.load_decision(captured["decision_id"])
        self.assertEqual(len(stored["execution_events"]), 1)
        ev = stored["execution_events"][0]
        self.assertEqual(ev["status"], "filled")
        self.assertEqual(ev["price"], 28.35)
        self.assertEqual(ev["quantity"], 100)
        self.assertEqual(ev["intent_key"], "watchlist:600690")

    def test_fill_is_idempotent_for_same_payload(self) -> None:
        captured = self._capture_decision()
        payload = {
            "trade_date": "2026-05-15",
            "code": "sh600690",
            "side": "buy",
            "qty": 100,
            "price": 28.35,
            "fees": 5.0,
            "name": "海尔智家",
            "intent_key": "watchlist:600690",
        }
        self.client.post("/api/portfolio/fills", json=payload)
        # Account book itself does NOT de-dupe a re-posted fill -- but
        # the ledger fingerprint MUST de-dupe the execution event.
        self.client.post("/api/portfolio/fills", json=payload)
        stored = self.ledger.load_decision(captured["decision_id"])
        self.assertEqual(len(stored["execution_events"]), 1)

    def test_fill_with_no_matching_decision_still_succeeds(self) -> None:
        # No capture beforehand -- the Portfolio writeback must still
        # land, and the ledger result reports a non-attached reason.
        response = self.client.post(
            "/api/portfolio/fills",
            json={
                "trade_date": "2026-05-15",
                "code": "sh600690",
                "side": "buy",
                "qty": 100,
                "price": 28.35,
                "fees": 5.0,
                "name": "海尔智家",
                "intent_key": "watchlist:600690",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("account", body)
        self.assertEqual(len(body["account"]["open_positions"]), 1)
        ledger = body.get("ledger") or {}
        self.assertFalse(ledger.get("attached"))
        self.assertEqual(ledger.get("reason"), "no_matching_decision")

    def test_fill_does_not_attach_to_ambiguous_decisions(self) -> None:
        # Two open decisions for the same code on the same date, neither
        # matching the supplied intent_key -- the helper must refuse to
        # bind blindly.
        self._capture_decision(action_key="watchlist:600690", action="hold")
        self._capture_decision(action_key="watchlist:600690:pm", action="reduce")
        response = self.client.post(
            "/api/portfolio/fills",
            json={
                "trade_date": "2026-05-15",
                "code": "sh600690",
                "side": "buy",
                "qty": 100,
                "price": 28.35,
                # No intent_key here, so fallback hits two candidates.
            },
        )
        self.assertEqual(response.status_code, 200)
        ledger = response.json().get("ledger") or {}
        self.assertFalse(ledger.get("attached"))
        self.assertEqual(ledger.get("reason"), "ambiguous_decision")

    def test_fill_survives_corrupt_ledger_file(self) -> None:
        corrupt_path = self.ledger_root / "decisions" / "2026-05-15.json"
        corrupt_path.parent.mkdir(parents=True, exist_ok=True)
        corrupt_path.write_text("{ not valid", encoding="utf-8")

        response = self.client.post(
            "/api/portfolio/fills",
            json={
                "trade_date": "2026-05-15",
                "code": "sh600690",
                "side": "buy",
                "qty": 100,
                "price": 28.35,
                "fees": 5.0,
                "name": "海尔智家",
                "intent_key": "watchlist:600690",
            },
        )
        # Portfolio canonical flow must still succeed.
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["account"]["open_positions"]), 1)
        ledger = body.get("ledger") or {}
        self.assertFalse(ledger.get("attached"))
        self.assertEqual(ledger.get("reason"), "ledger_error")

    # --------------------------------------- /api/portfolio/intent/no_fill

    def test_no_fill_attaches_no_fill_event(self) -> None:
        captured = self._capture_decision()
        response = self.client.post(
            "/api/portfolio/intent/no_fill",
            json={
                "trade_date": "2026-05-15",
                "intent_key": "watchlist:600690",
                "reason": "已经卖出",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("account", body)
        ledger = body.get("ledger") or {}
        self.assertTrue(ledger.get("attached"))
        self.assertEqual(ledger.get("decision_id"), captured["decision_id"])
        self.assertEqual(ledger.get("status"), "no_fill")

        stored = self.ledger.load_decision(captured["decision_id"])
        self.assertEqual(len(stored["execution_events"]), 1)
        ev = stored["execution_events"][0]
        self.assertEqual(ev["status"], "no_fill")
        self.assertEqual(ev["intent_key"], "watchlist:600690")

    def test_no_fill_without_matching_decision_still_succeeds(self) -> None:
        response = self.client.post(
            "/api/portfolio/intent/no_fill",
            json={
                "trade_date": "2026-05-15",
                "intent_key": "watchlist:600690",
                "reason": "已经卖出",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(
            body["account"]["no_fill_intents"][0]["intent_key"],
            "watchlist:600690",
        )
        ledger = body.get("ledger") or {}
        self.assertFalse(ledger.get("attached"))
        self.assertEqual(ledger.get("reason"), "no_matching_decision")

    # ------------------------------------- /api/today/actions/decision

    def test_today_decision_watch_attaches_watch_event(self) -> None:
        captured = self._capture_decision()
        response = self.client.post(
            "/api/today/actions/decision",
            json={
                "trade_date": "2026-05-15",
                "key": "watchlist:600690",
                "decision": "watch",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        # Original endpoint shape must remain.
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("trade_date"), "2026-05-15")
        ledger = body.get("ledger") or {}
        self.assertTrue(ledger.get("attached"))
        self.assertEqual(ledger.get("decision_id"), captured["decision_id"])
        self.assertEqual(ledger.get("status"), "watch")

        stored = self.ledger.load_decision(captured["decision_id"])
        self.assertEqual(len(stored["execution_events"]), 1)
        self.assertEqual(stored["execution_events"][0]["status"], "watch")

    def test_today_decision_skip_attaches_skip_event(self) -> None:
        captured = self._capture_decision()
        response = self.client.post(
            "/api/today/actions/decision",
            json={
                "trade_date": "2026-05-15",
                "key": "watchlist:600690",
                "decision": "skip",
            },
        )
        self.assertEqual(response.status_code, 200)
        ledger = response.json().get("ledger") or {}
        self.assertTrue(ledger.get("attached"))
        self.assertEqual(ledger.get("status"), "skip")
        stored = self.ledger.load_decision(captured["decision_id"])
        self.assertEqual(stored["execution_events"][0]["status"], "skip")

    def test_today_decision_done_does_not_fake_a_fill(self) -> None:
        self._capture_decision()
        response = self.client.post(
            "/api/today/actions/decision",
            json={
                "trade_date": "2026-05-15",
                "key": "watchlist:600690",
                "decision": "done",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body.get("ok"))
        ledger = body.get("ledger") or {}
        # ``done`` has no price / quantity, so we explicitly do NOT
        # synthesize a filled event.  The Portfolio fills endpoint is
        # the source of truth for fills.
        self.assertFalse(ledger.get("attached"))
        self.assertEqual(ledger.get("reason"), "ineligible")

    def test_today_decision_pending_does_not_touch_ledger(self) -> None:
        captured = self._capture_decision()
        # First write a watch decision so we have one stored event.
        self.client.post(
            "/api/today/actions/decision",
            json={
                "trade_date": "2026-05-15",
                "key": "watchlist:600690",
                "decision": "watch",
            },
        )
        # Then revert to pending -- ledger should NOT append another
        # event (pending is an undo of the local action queue state, not
        # a real decision).
        response = self.client.post(
            "/api/today/actions/decision",
            json={
                "trade_date": "2026-05-15",
                "key": "watchlist:600690",
                "decision": "pending",
            },
        )
        self.assertEqual(response.status_code, 200)
        ledger = response.json().get("ledger") or {}
        self.assertFalse(ledger.get("attached"))
        self.assertEqual(ledger.get("reason"), "ineligible")

        stored = self.ledger.load_decision(captured["decision_id"])
        self.assertEqual(len(stored["execution_events"]), 1)
        self.assertEqual(stored["execution_events"][0]["status"], "watch")


if __name__ == "__main__":
    unittest.main()
