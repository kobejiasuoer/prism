"""API smoke tests for the new /api/portfolio/* endpoints.

These do not exercise the readiness math (covered separately) — they
focus on:

* the endpoints respond with the expected schema shape,
* validation errors return HTTP 400 with a useful detail message,
* a happy-path flow (mode → cash → fill → reconcile) round-trips through
  the FastAPI app and the canonical view reflects each change.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient


INVEST_FLOW_ROOT = Path(__file__).resolve().parents[2]
if str(INVEST_FLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(INVEST_FLOW_ROOT))


class PortfolioEndpointsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        state_path = Path(self._tmp.name) / "data" / "control_panel_state" / "account_book.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        self._env = mock.patch.dict(
            os.environ,
            {
                "PRISM_REPO_ROOT": self._tmp.name,
                "PRISM_DB_PATH": str(Path(self._tmp.name) / "prism.db"),
                "PRISM_ACCOUNT_BOOK_PATH": str(state_path),
            },
        )
        self._env.start()
        self.addCleanup(self._env.stop)

        # Force-reload all modules whose constants depend on the env vars
        # we just set.  Order matters: prism_storage first, then the
        # control_panel modules that import it.  The legacy compat shim
        # caches the loaded modules under ``_prism_legacy_control_panel_*``
        # names, so we drop those too — otherwise the next setUp re-uses
        # the previous test's _REPOSITORY instance.
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
                "control_panel.dashboard_data",
                "control_panel.app",
            ]
        )
        for mod in modules_to_drop:
            sys.modules.pop(mod, None)

        from control_panel.app import app  # type: ignore  # noqa: E402

        self.client = TestClient(app)

    def test_account_endpoint_returns_research_defaults(self) -> None:
        response = self.client.get("/api/portfolio/account")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("account", body)
        self.assertEqual(body["account"]["mode"], "research")
        self.assertEqual(body["account"]["cash_balance"], 0.0)
        self.assertEqual(body["account"]["open_positions"], [])
        self.assertIn("readiness", body)
        self.assertIn("account_state", body["readiness"])

    def test_invalid_mode_returns_400(self) -> None:
        response = self.client.post("/api/portfolio/mode", json={"mode": "definitely_not_a_mode"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("invalid mode", response.json().get("detail", ""))

    def test_live_small_without_cash_returns_400(self) -> None:
        response = self.client.post("/api/portfolio/mode", json={"mode": "live_small"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("cash", response.json().get("detail", ""))

    def test_happy_path_flow(self) -> None:
        # 1. shadow mode + initial cash
        r1 = self.client.post(
            "/api/portfolio/mode",
            json={"mode": "shadow", "starting_cash": 0},
        )
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r1.json()["account"]["mode"], "shadow")

        # 2. record a deposit
        r2 = self.client.post(
            "/api/portfolio/cash",
            json={"delta": 5000.0, "reason": "initial deposit"},
        )
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["account"]["cash_balance"], 5000.0)

        # 3. record a buy fill
        r3 = self.client.post(
            "/api/portfolio/fills",
            json={
                "trade_date": "2026-05-06",
                "code": "sh600690",
                "side": "buy",
                "qty": 100,
                "price": 27.34,
                "fees": 5.0,
                "intent_key": "wl-priority-sh600690",
                "name": "海尔智家",
            },
        )
        self.assertEqual(r3.status_code, 200)
        body = r3.json()
        self.assertEqual(len(body["account"]["open_positions"]), 1)
        self.assertEqual(body["account"]["open_positions"][0]["code"], "sh600690")
        self.assertAlmostEqual(body["account"]["cash_balance"], 5000.0 - 100 * 27.34 - 5.0, places=2)

        # 4. record reconciliation
        r4 = self.client.post(
            "/api/portfolio/reconcile",
            json={
                "trade_date": "2026-05-06",
                "broker_cash": body["account"]["cash_balance"],
                "broker_equity": body["account"]["equity_at_cost"],
                "note": "first reconcile",
            },
        )
        self.assertEqual(r4.status_code, 200)
        recon = r4.json()["account"]["reconciliations"]
        self.assertEqual(len(recon), 1)
        self.assertAlmostEqual(recon[0]["delta_cash"], 0.0, places=2)

        # 5. switch to live_small now that cash > 0 and recon is fresh
        r5 = self.client.post("/api/portfolio/mode", json={"mode": "live_small"})
        self.assertEqual(r5.status_code, 200)
        self.assertEqual(r5.json()["account"]["mode"], "live_small")

    def test_no_fill_marker_endpoint(self) -> None:
        response = self.client.post(
            "/api/portfolio/intent/no_fill",
            json={
                "trade_date": "2026-05-06",
                "intent_key": "wl-priority-sh600690",
                "reason": "exited yesterday",
            },
        )
        self.assertEqual(response.status_code, 200)
        markers = response.json()["account"]["no_fill_intents"]
        self.assertEqual(len(markers), 1)
        self.assertEqual(markers[0]["intent_key"], "wl-priority-sh600690")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
