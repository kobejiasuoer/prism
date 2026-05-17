"""Phase 5 -- read-only Decision Ledger query API tests.

Covers the four new endpoints in ``app.py``:

* ``GET /api/decision-ledger/summary?window=7d`` -- aggregate counts
  over a trailing window.
* ``GET /api/decision-ledger/recent?limit=20`` -- most recent
  decisions plus their latest execution / outcome events.
* ``GET /api/decision-ledger/stock/{code}`` -- decision history for
  one stock; ``code`` accepts ``600690``, ``sh600690`` or
  ``sz000001`` forms.
* ``GET /api/decision-ledger/decision/{decision_id}`` -- raw
  DecisionRecord.

All four are read-only.  Corrupt ledger files surface either via an
``errors`` field (for scan-style endpoints) or via a 5xx response
(for the targeted detail endpoint), but they never silently disappear.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


CONTROL_PANEL_ROOT = Path(__file__).resolve().parents[1]
if str(CONTROL_PANEL_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROL_PANEL_ROOT))


def _sample_decision_inputs(**overrides):
    base = {
        "trade_date": "2026-05-15",
        "code": "sh600690",
        "name": "海尔智家",
        "lane": "watchlist",
        "surface": "today_action_queue",
        "action_key": "watchlist:600690",
        "source_label": "自选股链路",
        "action": "trial_buy",
        "action_label": "轻仓试错",
        "main_conclusion": "形态确认，轻仓试错",
        "expected_trade_date": "2026-05-15",
        "data_trade_date": "2026-05-15",
        "readiness_mode": "live_ready",
        "readiness_ready": True,
    }
    base.update(overrides)
    return base


class _LedgerApiTestBase(unittest.TestCase):
    """Shared setup: temp ledger root + reloaded modules + TestClient."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ledger_root = Path(self._tmp.name) / "decision_ledger"
        self.account_book_path = Path(self._tmp.name) / "account_book.json"
        self.scheduler_state_path = Path(self._tmp.name) / "scheduler_state.json"
        self.db_path = Path(self._tmp.name) / "prism.db"

        self._env = mock.patch.dict(
            os.environ,
            {
                "PRISM_DECISION_LEDGER_PATH": str(self.ledger_root),
                "PRISM_ACCOUNT_BOOK_PATH": str(self.account_book_path),
                "PRISM_REPO_ROOT": str(self._tmp.name),
                "PRISM_DB_PATH": str(self.db_path),
                "PRISM_SCHEDULER_STATE_PATH": str(self.scheduler_state_path),
            },
        )
        self._env.start()
        self.addCleanup(self._env.stop)

        # Force reload of modules that hold path config at import time.
        for mod_name in (
            "decision_ledger",
            "decision_ledger_providers",
            "app",
            "dashboard_data",
            "control_panel.dashboard_data",
        ):
            sys.modules.pop(mod_name, None)

        import decision_ledger  # type: ignore
        self.ledger = decision_ledger

        import app  # type: ignore
        from fastapi.testclient import TestClient  # type: ignore

        self.app_module = app
        self.client = TestClient(app.app)

    def _capture(self, **overrides) -> dict:
        record = self.ledger.build_decision_record(**_sample_decision_inputs(**overrides))
        return self.ledger.upsert_decision(record)

    def _attach_outcome(self, decision_id: str, *, window: str, label: str,
                       return_pct: float = 0.0, tone: str = "watch") -> None:
        self.ledger.append_outcome_event(
            decision_id,
            {
                "window": window,
                "as_of_trade_date": "2026-05-22",
                "market_data": {"return_pct": return_pct},
                "classification": {"label": label, "tone": tone},
                "quality": {"usable_for_decision_quality": label not in
                            {"data_issue", "inconclusive"}},
            },
        )


# ===========================================================================
# /api/decision-ledger/summary
# ===========================================================================


class SummaryApiTests(_LedgerApiTestBase):

    def test_empty_ledger_returns_zeroed_payload(self) -> None:
        resp = self.client.get("/api/decision-ledger/summary?window=7d")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["decisions"]["total"], 0)
        self.assertEqual(body["outcome_distribution"], {})
        self.assertEqual(body["execution_gap_count"], 0)
        self.assertEqual(body["data_issue_count"], 0)
        self.assertEqual(body["errors"], [])

    def test_summary_counts_decisions_and_outcomes_in_window(self) -> None:
        # Two decisions on 2026-05-15 within the 7d window ending 2026-05-22.
        d1 = self._capture(action="trial_buy", action_key="watchlist:600690", code="sh600690")
        d2 = self._capture(action="skip", action_key="watchlist:000001", code="sz000001")
        self._attach_outcome(d1["decision_id"], window="T+1", label="validated", return_pct=3.0)
        self._attach_outcome(d2["decision_id"], window="T+1", label="avoided_loss", return_pct=-2.5)
        self._attach_outcome(d2["decision_id"], window="T+3", label="avoided_loss", return_pct=-2.8)

        resp = self.client.get("/api/decision-ledger/summary?window=7d&as_of=2026-05-22")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["decisions"]["total"], 2)
        self.assertEqual(body["decisions"]["open"], 2)
        self.assertEqual(body["outcome_distribution"]["validated"], 1)
        self.assertEqual(body["outcome_distribution"]["avoided_loss"], 2)
        self.assertEqual(body["execution_events_total"], 0)
        self.assertEqual(body["outcome_events_total"], 3)

    def test_summary_excludes_decisions_outside_window(self) -> None:
        # 2026-05-01 is outside a 7d window ending 2026-05-22.
        self._capture(trade_date="2026-05-01", action_key="watchlist:600690")
        resp = self.client.get("/api/decision-ledger/summary?window=7d&as_of=2026-05-22")
        body = resp.json()
        self.assertEqual(body["decisions"]["total"], 0)

    def test_summary_counts_execution_gap_and_data_issue_separately(self) -> None:
        d1 = self._capture(action="trial_buy", action_key="watchlist:600690")
        d2 = self._capture(action="trial_buy", action_key="watchlist:000001", code="sz000001")
        self._attach_outcome(d1["decision_id"], window="T+1", label="execution_gap")
        self._attach_outcome(d2["decision_id"], window="T+1", label="data_issue")

        resp = self.client.get("/api/decision-ledger/summary?window=7d&as_of=2026-05-22")
        body = resp.json()
        self.assertEqual(body["execution_gap_count"], 1)
        self.assertEqual(body["data_issue_count"], 1)

    def test_corrupt_file_is_surfaced_under_errors(self) -> None:
        # Write a malformed JSON file directly into the decisions dir.
        decisions_dir = self.ledger_root / "decisions"
        decisions_dir.mkdir(parents=True, exist_ok=True)
        (decisions_dir / "2026-05-20.json").write_text("{not valid", encoding="utf-8")

        resp = self.client.get("/api/decision-ledger/summary?window=7d&as_of=2026-05-22")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["errors"])
        self.assertIn("2026-05-20.json", body["errors"][0]["file"])


# ===========================================================================
# /api/decision-ledger/recent
# ===========================================================================


class RecentApiTests(_LedgerApiTestBase):

    def test_empty_returns_empty_items(self) -> None:
        resp = self.client.get("/api/decision-ledger/recent")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["items"], [])
        self.assertEqual(body["count"], 0)
        self.assertEqual(body["errors"], [])

    def test_recent_returns_decisions_newest_first(self) -> None:
        self._capture(trade_date="2026-05-08", action_key="watchlist:600690")
        self._capture(trade_date="2026-05-15", action_key="watchlist:000001", code="sz000001")
        resp = self.client.get("/api/decision-ledger/recent?limit=20")
        body = resp.json()
        self.assertEqual(len(body["items"]), 2)
        self.assertEqual(body["items"][0]["trade_date"], "2026-05-15")
        self.assertEqual(body["items"][1]["trade_date"], "2026-05-08")

    def test_recent_includes_latest_outcome_and_execution(self) -> None:
        d = self._capture()
        self.ledger.append_execution_event(
            d["decision_id"],
            {"status": "filled", "side": "buy", "price": 10.5, "quantity": 100,
             "trade_date": "2026-05-15"},
        )
        self._attach_outcome(d["decision_id"], window="T+1", label="validated", return_pct=2.5)
        self._attach_outcome(d["decision_id"], window="T+3", label="validated", return_pct=4.2)

        resp = self.client.get("/api/decision-ledger/recent?limit=5")
        body = resp.json()
        card = body["items"][0]
        self.assertEqual(card["execution_events_count"], 1)
        self.assertEqual(card["outcome_events_count"], 2)
        # T+3 wins over T+1 in the "latest_outcome" pick.
        self.assertEqual(card["latest_outcome"]["window"], "T+3")
        self.assertEqual(card["latest_outcome"]["label"], "validated")
        self.assertEqual(card["latest_execution"]["status"], "filled")
        self.assertEqual(card["latest_execution"]["side"], "buy")

    def test_recent_respects_limit(self) -> None:
        for n in range(5):
            self._capture(
                trade_date=f"2026-05-{10 + n:02d}",
                action_key=f"watchlist:60069{n}",
                code=f"sh60069{n}",
            )
        resp = self.client.get("/api/decision-ledger/recent?limit=2")
        body = resp.json()
        self.assertEqual(len(body["items"]), 2)
        self.assertEqual(body["count"], 2)

    def test_recent_with_corrupt_file_degrades_with_errors(self) -> None:
        self._capture()
        decisions_dir = self.ledger_root / "decisions"
        (decisions_dir / "2026-05-20.json").write_text("garbage", encoding="utf-8")

        resp = self.client.get("/api/decision-ledger/recent?limit=20")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        # The good file still produced a card; the bad one is surfaced.
        self.assertEqual(len(body["items"]), 1)
        self.assertTrue(body["errors"])

    def test_invalid_limit_falls_back_to_safe_default(self) -> None:
        # Negative / zero limit should not 500 -- the API clamps.
        resp = self.client.get("/api/decision-ledger/recent?limit=0")
        self.assertEqual(resp.status_code, 200)


# ===========================================================================
# /api/decision-ledger/stock/{code}
# ===========================================================================


class StockApiTests(_LedgerApiTestBase):

    def test_plain_code_resolves_to_prefixed_records(self) -> None:
        self._capture(code="sh600690", action_key="watchlist:600690")
        resp = self.client.get("/api/decision-ledger/stock/600690")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["code"], "sh600690")
        self.assertEqual(len(body["items"]), 1)

    def test_prefixed_code_works(self) -> None:
        self._capture(code="sh600690", action_key="watchlist:600690")
        resp = self.client.get("/api/decision-ledger/stock/sh600690")
        body = resp.json()
        self.assertEqual(body["code"], "sh600690")
        self.assertEqual(len(body["items"]), 1)

    def test_shenzhen_code_works(self) -> None:
        self._capture(code="sz000001", action_key="watchlist:000001")
        resp = self.client.get("/api/decision-ledger/stock/sz000001")
        body = resp.json()
        self.assertEqual(body["code"], "sz000001")
        self.assertEqual(len(body["items"]), 1)

    def test_unknown_code_returns_empty_items(self) -> None:
        resp = self.client.get("/api/decision-ledger/stock/sh999999")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["items"], [])
        self.assertEqual(body["count"], 0)

    def test_malformed_code_returns_400(self) -> None:
        resp = self.client.get("/api/decision-ledger/stock/garbage")
        self.assertEqual(resp.status_code, 400)

    def test_stock_includes_outcome_summary(self) -> None:
        d = self._capture(code="sh600690", action_key="watchlist:600690")
        self._attach_outcome(d["decision_id"], window="T+1", label="validated", return_pct=3.5)

        resp = self.client.get("/api/decision-ledger/stock/sh600690")
        body = resp.json()
        card = body["items"][0]
        self.assertEqual(card["latest_outcome"]["label"], "validated")


# ===========================================================================
# /api/decision-ledger/decision/{decision_id}
# ===========================================================================


class DecisionDetailApiTests(_LedgerApiTestBase):

    def test_returns_full_record(self) -> None:
        d = self._capture()
        resp = self.client.get(f"/api/decision-ledger/decision/{d['decision_id']}")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        # Same shape as the on-disk record (full DecisionRecord).
        self.assertEqual(body["decision_id"], d["decision_id"])
        self.assertEqual(body["stock"]["code"], "sh600690")
        self.assertIn("evidence_snapshot", body)
        self.assertIn("parameter_snapshot", body)
        self.assertEqual(body["execution_events"], [])
        self.assertEqual(body["outcome_events"], [])

    def test_returns_404_for_unknown_id(self) -> None:
        resp = self.client.get(
            "/api/decision-ledger/decision/2026-05-15:sh999999:today_action_queue:watchlist:deadbeef"
        )
        self.assertEqual(resp.status_code, 404)

    def test_returns_400_for_malformed_id(self) -> None:
        # No leading YYYY-MM-DD -> bad id.
        resp = self.client.get("/api/decision-ledger/decision/not-a-real-id")
        self.assertEqual(resp.status_code, 400)

    def test_corrupt_target_file_returns_500_with_detail(self) -> None:
        d = self._capture()
        # Corrupt the file that hosts this decision.
        file_path = self.ledger_root / "decisions" / f"{d['trade_date']}.json"
        file_path.write_text("not json", encoding="utf-8")

        resp = self.client.get(f"/api/decision-ledger/decision/{d['decision_id']}")
        self.assertEqual(resp.status_code, 500)
        body = resp.json()
        # Detail should reference the ledger error so the operator can fix.
        self.assertIn("ledger", body.get("detail", "").lower())


if __name__ == "__main__":
    unittest.main()
