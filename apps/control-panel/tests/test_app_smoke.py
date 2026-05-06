from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from fastapi.testclient import TestClient


INVEST_FLOW_ROOT = Path(__file__).resolve().parents[2]
if str(INVEST_FLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(INVEST_FLOW_ROOT))

from control_panel.app import app  # noqa: E402
from control_panel.dashboard_data import (  # noqa: E402
    ask_page_url,
    batch_detail_url,
    candidate_detail_url,
    review_detail_url,
    today_nav_links,
    watchlist_detail_url,
    watchlist_page_url,
)


UNSUPPORTED_ASK_FOLLOWUP_COPY = {
    "强烈买入",
    "建议买入",
    "可以买入",
    "买入",
    "开新仓",
    "开仓",
    "轻仓试错",
    "满仓",
    "目标价",
    "收益预测",
    "收益承诺",
    "建议仓位",
}


class ControlPanelApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_backend_api_contracts_remain_available_for_next_frontend(self) -> None:
        checks = {
            "/api/overview": ("generated_at", "runs", "tasks"),
            "/api/today": ("generated_at", "display_date", "action_queue", "source_cards"),
            "/api/watchlist": ("display_date", "groups", "manager", "source_cards"),
            "/api/watchlist/manage": ("manager",),
            "/api/opportunities": ("display_date", "groups", "source_cards"),
            "/api/review": ("selector_groups", "source_cards"),
            "/api/parameters": ("value", "validation", "raw"),
            "/api/runs": ("runs",),
            "/healthz": ("ok", "workspace"),
        }

        for path, keys in checks.items():
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                for key in keys:
                    self.assertIn(key, payload)

    def test_legacy_frontend_routes_redirect_to_next_frontend(self) -> None:
        checks = {
            "/": "http://127.0.0.1:8000/",
            "/today": "http://127.0.0.1:8000/",
            "/ask": "http://127.0.0.1:8000/",
            "/ask?q=600690": "http://127.0.0.1:8000/stock/600690",
            "/watchlist": "http://127.0.0.1:8000/portfolio",
            "/opportunities": "http://127.0.0.1:8000/discovery",
            "/parameters": "http://127.0.0.1:8000/settings",
            "/review": "http://127.0.0.1:8000/review",
            "/review/detail?section=ai_regime_rows&label=test": (
                "http://127.0.0.1:8000/review?section=ai_regime_rows&label=test"
            ),
            "/watchlist/600690": "http://127.0.0.1:8000/stock/600690",
            "/today/watchlist/600690": "http://127.0.0.1:8000/stock/600690",
            "/opportunities/600690": "http://127.0.0.1:8000/stock/600690",
            "/today/candidates/600690": "http://127.0.0.1:8000/stock/600690",
            "/opportunities/batch/screener": "http://127.0.0.1:8000/discovery",
            "/today/batch/screener": "http://127.0.0.1:8000/discovery",
        }

        for path, location in checks.items():
            with self.subTest(path=path):
                response = self.client.get(path, follow_redirects=False)
                self.assertEqual(response.status_code, 307)
                self.assertEqual(response.headers["location"], location)

    def test_public_url_builders_target_next_routes(self) -> None:
        links = today_nav_links()

        self.assertEqual(links["today"], "/")
        self.assertEqual(links["watchlist"], "/portfolio")
        self.assertEqual(links["opportunities"], "/discovery")
        self.assertEqual(links["parameters"], "/settings")
        self.assertEqual(watchlist_page_url(), "/portfolio")
        self.assertEqual(ask_page_url(), "/")
        self.assertEqual(ask_page_url("600690"), "/stock/600690")
        self.assertEqual(watchlist_detail_url("600690"), "/stock/600690")
        self.assertEqual(candidate_detail_url("600690"), "/stock/600690")
        self.assertEqual(batch_detail_url("screener"), "/discovery")
        self.assertTrue(review_detail_url("ai_regime_rows", "弱修复").startswith("/review?"))

    def test_ask_api_supports_empty_state_query_and_suggestions(self) -> None:
        empty_response = self.client.get("/api/ask")
        self.assertEqual(empty_response.status_code, 200)
        self.assertIn("search_strip", empty_response.json())

        query_response = self.client.get("/api/ask?q=600690")
        self.assertEqual(query_response.status_code, 200)
        query_payload = query_response.json()
        self.assertIn("case", query_payload)
        self.assertIn("links", query_payload)

        suggest_response = self.client.get("/api/ask/suggest?q=海尔")
        self.assertEqual(suggest_response.status_code, 200)
        suggest_payload = suggest_response.json()
        self.assertIn("items", suggest_payload)
        self.assertIn("message", suggest_payload)

    def test_ask_followup_api_returns_structured_payload(self) -> None:
        response = self.client.post(
            "/api/ask/followup",
            json={"query": "600690", "question": "现在主要风险是什么？", "history": []},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("answer", payload)
        self.assertIn("engine", payload["answer"])

    def test_ask_followup_api_keeps_degraded_action_copy(self) -> None:
        previous = os.environ.get("PRISM_ASK_FOLLOWUP_DISABLE")
        os.environ["PRISM_ASK_FOLLOWUP_DISABLE"] = "1"
        try:
            response = self.client.post(
                "/api/ask/followup",
                json={"query": "600690", "question": "这只现在买还是卖？今天怎么操作？", "history": []},
            )
        finally:
            if previous is None:
                os.environ.pop("PRISM_ASK_FOLLOWUP_DISABLE", None)
            else:
                os.environ["PRISM_ASK_FOLLOWUP_DISABLE"] = previous

        self.assertEqual(response.status_code, 200)
        answer = response.json()["answer"]
        answer_text = json.dumps(answer, ensure_ascii=False)
        for fragment in UNSUPPORTED_ASK_FOLLOWUP_COPY:
            self.assertNotIn(fragment, answer_text)
        self.assertIn("纪律", answer_text)

    def test_parameter_api_save_validates_payload_without_touching_real_config(self) -> None:
        seed = {
            "stocks": [{"code": "600690", "name": "海尔智家", "active": True}],
            "ma_periods": [5, 10, 20],
            "news_count": 5,
            "kline_days": 120,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir) / "stocks.json"
            temp_path.write_text(json.dumps(seed, ensure_ascii=False), encoding="utf-8")

            original_path = app.router.routes  # keep the module imported before patching
            self.assertIsNotNone(original_path)
            import control_panel.app as app_module

            previous = app_module.PARAMETERS_PATH
            app_module.PARAMETERS_PATH = temp_path
            try:
                response = self.client.post(
                    "/api/parameters",
                    json={"raw": json.dumps({**seed, "news_count": 6}, ensure_ascii=False)},
                )
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertTrue(payload["ok"])
                self.assertTrue(payload["saved"])
                self.assertEqual(json.loads(temp_path.read_text(encoding="utf-8"))["news_count"], 6)
            finally:
                app_module.PARAMETERS_PATH = previous

    def test_review_detail_api_stays_available_even_without_html_detail_page(self) -> None:
        review = self.client.get("/api/review").json()
        selector = review.get("selector") or {}
        active_baseline = selector.get("active_baseline_id")
        active_window = selector.get("active_window_id")
        response = self.client.get(
            "/api/review/detail",
            params={
                "section": "ai_regime_rows",
                "label": "弱修复",
                "baseline": active_baseline,
                "window": active_window,
            },
        )

        self.assertIn(response.status_code, {200, 404})

    def test_refresh_status_endpoint_returns_payload(self) -> None:
        response = self.client.get("/api/refresh/status?page=today")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["page"], "today")
        self.assertIn("recommended_task", payload)

    def test_refresh_status_rejects_unknown_page(self) -> None:
        response = self.client.get("/api/refresh/status?page=unknown")
        self.assertEqual(response.status_code, 400)

    def test_watchlist_fetch_load_config_normalizes_market_and_sina(self) -> None:
        fetch_path = INVEST_FLOW_ROOT.parent / "stock-analyzer" / "scripts" / "fetch.py"
        spec = spec_from_file_location("prism_fetch_module", fetch_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        fetch_module = module_from_spec(spec)
        spec.loader.exec_module(fetch_module)

        config = fetch_module.load_config(selected_codes=["600690"])
        self.assertEqual(len(config["stocks"]), 1)
        stock = config["stocks"][0]
        self.assertEqual(stock["market"], "sh")
        self.assertEqual(stock["sina"], "sh600690")


if __name__ == "__main__":
    unittest.main()
