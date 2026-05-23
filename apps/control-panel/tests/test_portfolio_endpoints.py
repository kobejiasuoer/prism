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
PACKAGES_ROOT = INVEST_FLOW_ROOT.parent / "packages"
if str(INVEST_FLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(INVEST_FLOW_ROOT))
if str(PACKAGES_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGES_ROOT))

from prism_data.contracts import DatasetStatus, ProviderResult, ProviderRole  # noqa: E402


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

    def _seed_two_positions(self) -> None:
        self.client.post("/api/portfolio/cash", json={"delta": 10000.0, "reason": "seed"})
        for code, name, price in (
            ("sh600690", "海尔智家", 27.34),
            ("sz000001", "平安银行", 10.0),
        ):
            response = self.client.post(
                "/api/portfolio/fills",
                json={
                    "trade_date": "2026-05-06",
                    "code": code,
                    "side": "buy",
                    "qty": 100,
                    "price": price,
                    "fees": 0.0,
                    "name": name,
                },
            )
            self.assertEqual(response.status_code, 200)

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

    def test_allow_unsafe_requires_note(self) -> None:
        response = self.client.post(
            "/api/portfolio/mode",
            json={"mode": "live_small", "allow_unsafe": True},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("note", response.json().get("detail", ""))

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

    def test_holding_identity_correction_endpoint(self) -> None:
        self.client.post("/api/portfolio/cash", json={"delta": 10000.0, "reason": "seed"})
        fill = self.client.post(
            "/api/portfolio/fills",
            json={
                "trade_date": "2026-05-06",
                "code": "sh000625",
                "side": "buy",
                "qty": 500,
                "price": 11.21,
                "fees": 0.0,
                "name": "错码记录",
            },
        )
        self.assertEqual(fill.status_code, 200)

        response = self.client.post(
            "/api/portfolio/holding/identity",
            json={
                "from_code": "sh000625",
                "to_code": "sz000625",
                "name": "长安汽车",
                "reason": "录入代码修正",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        position = body["account"]["open_positions"][0]
        self.assertEqual(position["code"], "sz000625")
        self.assertEqual(position["name"], "长安汽车")
        self.assertEqual(body["account"]["identity_corrections"][0]["from_code"], "sh000625")

    def test_quote_refresh_uses_provider_name_for_code_like_position_name(self) -> None:
        self.client.post("/api/portfolio/cash", json={"delta": 10000.0, "reason": "seed"})
        with mock.patch("control_panel.app.fetch_stock_name", return_value=None):
            fill = self.client.post(
                "/api/portfolio/fills",
                json={
                    "trade_date": "2026-05-06",
                    "code": "sh601021",
                    "side": "buy",
                    "qty": 100,
                    "price": 46.84,
                    "fees": 0.0,
                    "name": "sh601021",
                },
            )
        self.assertEqual(fill.status_code, 200)

        class NamedGateway:
            def fetch_quotes_batch(self, codes, **kwargs):  # type: ignore[no-untyped-def]
                from datetime import datetime

                provider_result = ProviderResult(
                    status=DatasetStatus.OK,
                    data=[
                        {
                            "code": "601021",
                            "symbol": "sh601021",
                            "name": "春秋航空",
                            "price": 47.82,
                            "change_pct": 4.89,
                        }
                    ],
                    provider="fake",
                    provider_role=ProviderRole.PRIMARY,
                    dataset="quotes.batch",
                    trade_date="2026-05-06",
                    fetched_at=datetime(2026, 5, 6, 10, 0, 0),
                    asof=datetime(2026, 5, 6, 10, 0, 0),
                )
                return type(
                    "GatewayResult",
                    (),
                    {
                        "data": provider_result.data,
                        "manifest": {
                            "provider": "fake",
                            "trade_date": "2026-05-06",
                            "fetched_at": "2026-05-06 10:00:00",
                            "freshness_status": "fresh",
                            "live_small_allowed": True,
                        },
                        "data_path": "/tmp/quotes.json",
                        "manifest_path": "/tmp/quotes.manifest.json",
                        "provider_result": provider_result,
                    },
                )()

        with mock.patch("control_panel.dashboard_data.get_data_gateway", return_value=NamedGateway()):
            response = self.client.post("/api/portfolio/quotes/refresh")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["account"]["open_positions"][0]["name"], "春秋航空")
        self.assertEqual(body["holding_reviews"][0]["name"], "春秋航空")

    def test_allow_unsafe_mode_stays_risky_in_readiness(self) -> None:
        self.client.post("/api/portfolio/cash", json={"delta": 5000.0, "reason": "seed"})
        response = self.client.post(
            "/api/portfolio/mode",
            json={"mode": "live_small", "allow_unsafe": True, "note": "temporary bypass for audit recovery"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["account"]["unsafe_bypass_active"])
        warning_codes = {item["code"] for item in (body["readiness"].get("warnings") or [])}
        self.assertIn("account_unsafe_bypass_active", warning_codes)
        self.assertNotEqual(body["readiness"]["readiness_mode"], "live_ready")

    def test_quote_refresh_allows_partial_market_data(self) -> None:
        self._seed_two_positions()
        test_case = self

        class PartialGateway:
            def fetch_quotes_batch(self, codes, **kwargs):  # type: ignore[no-untyped-def]
                test_case.assertIn("sh600690", codes)
                test_case.assertIn("sz000001", codes)
                from datetime import datetime

                provider_result = ProviderResult(
                    status=DatasetStatus.PARTIAL,
                    data=[{"code": "sh600690", "price": 30.0, "change_pct": 1.23}],
                    provider="fake",
                    provider_role=ProviderRole.PRIMARY,
                    dataset="quotes.batch",
                    trade_date="2026-05-06",
                    fetched_at=datetime(2026, 5, 6, 10, 0, 0),
                    asof=datetime(2026, 5, 6, 10, 0, 0),
                    error="sz000001 missing",
                    row_count=1,
                )
                return type(
                    "GatewayResult",
                    (),
                    {
                        "data": provider_result.data,
                        "manifest": {
                            "provider": "fake",
                            "trade_date": "2026-05-06",
                            "fetched_at": "2026-05-06 10:00:00",
                            "freshness_status": "fresh",
                            "live_small_allowed": True,
                        },
                        "data_path": "/tmp/quotes.json",
                        "manifest_path": "/tmp/quotes.manifest.json",
                        "provider_result": provider_result,
                    },
                )()

        with mock.patch("control_panel.dashboard_data.get_data_gateway", return_value=PartialGateway()):
            response = self.client.post("/api/portfolio/quotes/refresh")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["market_quotes"]["status"], "partial")
        self.assertEqual(body["market_quotes"]["missing_codes"], ["sz000001"])
        by_code = {item["code"]: item for item in body["account"]["open_positions"]}
        self.assertEqual(by_code["sh600690"]["current_price"], 30.0)
        self.assertAlmostEqual(by_code["sh600690"]["market_value"], 3000.0, places=2)
        self.assertIsNone(by_code["sz000001"]["current_price"])
        self.assertIsNone(by_code["sz000001"]["total_pnl"])
        self.assertIn("部分行情估值，缺 1 只", {card["label"]: card["detail"] for card in body["summary_cards"]}["持仓市值"])

    def test_quote_refresh_failure_returns_portfolio_payload(self) -> None:
        self._seed_two_positions()

        class FailingGateway:
            def fetch_quotes_batch(self, codes, **kwargs):  # type: ignore[no-untyped-def]
                raise RuntimeError("provider unavailable")

        with mock.patch("control_panel.dashboard_data.get_data_gateway", return_value=FailingGateway()):
            response = self.client.post("/api/portfolio/quotes/refresh")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["market_quotes"]["status"], "failed")
        self.assertIn("provider unavailable", body["market_quotes"]["message"])
        self.assertIn("provider unavailable", body["market_quotes"]["errors"])
        self.assertIsNone(body["account"]["market_value"])
        self.assertIsNone(body["account"]["unrealized_pnl"])
        self.assertEqual(body["summary_cards"][2]["value"], f"¥{body['account']['equity_at_cost']:,.2f}")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
