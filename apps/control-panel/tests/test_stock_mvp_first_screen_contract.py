from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient


INVEST_FLOW_ROOT = Path(__file__).resolve().parents[2]
if str(INVEST_FLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(INVEST_FLOW_ROOT))

from control_panel.app import app  # noqa: E402
from control_panel.dashboard_data import (  # noqa: E402
    build_candidate_detail_view,
    build_opportunities_view,
    build_stock_profile_view,
    build_today_view,
    build_watchlist_detail_view,
    normalize_avoid_sentence,
    normalize_trigger_sentence,
)


STOCK_URL_PATTERN = re.compile(r"^/stock/(?P<code>\d{6})$")
STOCK_RESULT_PAGE_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "stock" / "[code]" / "page.tsx"
STOCK_PROFILE_CONTRACT_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "stock_mvp_profile_contract.json"

UNSUPPORTED_STRONG_RESULT_KEY_FRAGMENTS = {
    "analyst_rating",
    "candlestick",
    "chart_data",
    "dcf",
    "expected_return",
    "financial_report",
    "full_financial",
    "institutional_rating",
    "kline",
    "price_target",
    "profit_forecast",
    "return_probability",
    "target_price",
    "valuation",
}

UNSUPPORTED_STRONG_RESULT_TEXT_FRAGMENTS = {
    "强烈买入",
    "建议买入",
    "可以买入",
    "买入",
    "开新仓",
    "开仓",
    "介入",
    "轻仓试错",
    "满仓",
    "目标价",
    "收益预测",
    "收益承诺",
    "DCF",
}

REQUIRED_CANONICAL_DECISION_FIELDS = {
    "stock_id",
    "stock_name",
    "trade_date",
    "source_scope",
    "main_conclusion",
    "action_tier",
    "position_guidance",
    "risk_boundary",
    "why_now",
    "continue_condition",
    "stop_condition",
    "next_step",
    "trigger_condition",
    "avoid_action",
    "evidence_entry",
    "confidence_note",
    "updated_at",
}

REQUIRED_DECISION_CARD_LABELS = {
    "当前结论",
    "仓位建议",
    "风险边界",
    "下一步动作",
}

REQUIRED_EXECUTION_LOOP_LABELS = {
    "现在做什么",
    "为什么先做这一步",
    "触发条件",
    "先不要做什么",
    "去哪看证据",
}


def assert_non_empty_string(testcase: unittest.TestCase, value: Any, field_name: str) -> None:
    testcase.assertIsInstance(value, str, field_name)
    testcase.assertTrue(value.strip(), field_name)


class StockMvpFirstScreenContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_today_first_screen_contract_keeps_stock_routes_and_queue_fields(self) -> None:
        payload = build_today_view()

        for key in ("generated_at", "trade_date", "brief_is_live", "hero", "summary_cards", "action_queue", "source_cards", "counts"):
            self.assertIn(key, payload)

        assert_non_empty_string(self, payload["generated_at"], "generated_at")
        assert_non_empty_string(self, payload["trade_date"], "trade_date")
        self.assertIsInstance(payload["brief_is_live"], bool)

        hero = payload["hero"]
        self.assertIn("title", hero)
        self.assertIn("summary", hero)
        assert_non_empty_string(self, hero["title"], "hero.title")
        assert_non_empty_string(self, hero["summary"], "hero.summary")

        queue = payload["action_queue"]
        for key in ("title", "items", "counts"):
            self.assertIn(key, queue)
        self.assertIsInstance(queue["items"], list)

        counts = queue["counts"]
        for key in ("total", "pending", "done", "watch", "skip"):
            self.assertIn(key, counts)
            self.assertIsInstance(counts[key], int)

        for item in queue["items"]:
            for key in ("key", "title", "source", "status", "tone", "detail", "decision"):
                self.assertIn(key, item)
            assert_non_empty_string(self, item["key"], "action item key")
            assert_non_empty_string(self, item["title"], "action item title")
            assert_non_empty_string(self, item["detail"], "action item detail")

            decision = item["decision"]
            for key in ("value", "label", "tone"):
                self.assertIn(key, decision)
            self.assertIn(decision["value"], {"pending", "done", "watch", "skip"})

            url = item.get("url")
            if url and url.startswith("/stock/"):
                self.assertRegex(url, STOCK_URL_PATTERN)

        top_level_counts = payload["counts"]
        for key in ("watchlist_priority", "watchlist_total", "candidate_total", "confirmed", "downgraded", "fresh_candidates"):
            self.assertIn(key, top_level_counts)
            self.assertIsInstance(top_level_counts[key], int)

    def test_first_stock_route_has_a_renderable_detail_contract(self) -> None:
        today = build_today_view()
        stock_item = next(
            (
                item
                for item in (today.get("action_queue") or {}).get("items") or []
                if STOCK_URL_PATTERN.match(str(item.get("url") or ""))
            ),
            None,
        )
        if not stock_item:
            self.skipTest("current action queue has no stock item")

        match = STOCK_URL_PATTERN.match(str(stock_item["url"]))
        self.assertIsNotNone(match)
        code = match.group("code")

        detail = self.load_any_stock_detail(code)
        self.assertEqual(detail["code"], code)
        self.assert_renderable_detail_contract(detail)

    def test_unified_stock_profile_prefers_watchlist_then_opportunity(self) -> None:
        today = build_today_view()
        stock_item = next(
            (
                item
                for item in (today.get("action_queue") or {}).get("items") or []
                if STOCK_URL_PATTERN.match(str(item.get("url") or ""))
            ),
            None,
        )
        if not stock_item:
            self.skipTest("current action queue has no stock item")

        match = STOCK_URL_PATTERN.match(str(stock_item["url"]))
        self.assertIsNotNone(match)
        code = match.group("code")

        profile = build_stock_profile_view(code)
        self.assertEqual(profile["code"], code)
        self.assertIn("primary_source", profile)
        self.assertIn("primary_detail", profile)
        self.assertIn("available_sources", profile)
        self.assertIn(profile["primary_source"], {"watchlist", "opportunity"})
        self.assertIn(profile["primary_source"], profile["available_sources"])
        self.assertIs(profile["primary_detail"], profile[profile["primary_source"]])
        self.assert_renderable_detail_contract(profile["primary_detail"])

    def test_unified_stock_profile_endpoint_returns_same_contract(self) -> None:
        today = build_today_view()
        stock_item = next(
            (
                item
                for item in (today.get("action_queue") or {}).get("items") or []
                if STOCK_URL_PATTERN.match(str(item.get("url") or ""))
            ),
            None,
        )
        if not stock_item:
            self.skipTest("current action queue has no stock item")

        match = STOCK_URL_PATTERN.match(str(stock_item["url"]))
        self.assertIsNotNone(match)
        code = match.group("code")

        response = self.client.get(f"/api/stock/{code}")
        self.assertEqual(response.status_code, 200)
        profile = response.json()
        self.assertEqual(profile["code"], code)
        self.assertIn(profile["primary_source"], {"watchlist", "opportunity"})
        self.assert_renderable_detail_contract(profile["primary_detail"])

    def test_unified_stock_profile_returns_degradable_empty_profile_for_unknown_stock(self) -> None:
        code = "000000"
        profile = build_stock_profile_view(code)

        self.assertEqual(profile["code"], code)
        self.assertIsNone(profile["primary_source"])
        self.assertIsNone(profile["primary_detail"])
        self.assertEqual(profile["available_sources"], [])
        self.assertIsNone(profile["watchlist"])
        self.assertIsNone(profile["opportunity"])
        self.assertIn("watchlist", profile["errors"])
        self.assertIn("opportunity", profile["errors"])

        response = self.client.get(f"/api/stock/{code}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["code"], code)

    def test_unified_stock_profile_matches_contract_fixture(self) -> None:
        contract = json.loads(STOCK_PROFILE_CONTRACT_FIXTURE_PATH.read_text(encoding="utf-8"))
        response_contract = contract["response"]

        today = build_today_view()
        stock_item = next(
            (
                item
                for item in (today.get("action_queue") or {}).get("items") or []
                if STOCK_URL_PATTERN.match(str(item.get("url") or ""))
            ),
            None,
        )
        if not stock_item:
            self.skipTest("current action queue has no stock item")

        match = STOCK_URL_PATTERN.match(str(stock_item["url"]))
        self.assertIsNotNone(match)
        code = match.group("code")

        profile = build_stock_profile_view(code)
        self.assertTrue(set(response_contract["required"]).issubset(profile.keys()))
        self.assertEqual(profile["code"], code)
        self.assertIsInstance(profile["available_sources"], list)
        self.assertTrue(profile["available_sources"])

        source_priority = response_contract["primary_source_priority"]
        expected_primary = next(source for source in source_priority if profile.get(source))
        self.assertEqual(profile["primary_source"], expected_primary)
        self.assertEqual(profile["primary_detail"], profile[expected_primary])

        detail = profile["primary_detail"]
        self.assertTrue(set(response_contract["detail_required"]).issubset(detail.keys()))
        self.assertTrue(set(response_contract["canonical_decision_required"]).issubset(detail["canonical_decision"].keys()))

        decision_labels = {item.get("label") for item in detail["decision_cards"]}
        self.assertTrue(set(response_contract["decision_card_required_labels"]).issubset(decision_labels))

        execution_labels = {item.get("label") for item in detail["execution_loop"]}
        self.assertTrue(set(response_contract["execution_loop_required_labels"]).issubset(execution_labels))

        source = STOCK_RESULT_PAGE_PATH.read_text(encoding="utf-8")
        for label in response_contract["source_issue_labels"].values():
            self.assertIn(label, source)

    def test_stock_detail_contract_does_not_publish_unsupported_strong_modules(self) -> None:
        today = build_today_view()
        stock_item = next(
            (
                item
                for item in (today.get("action_queue") or {}).get("items") or []
                if STOCK_URL_PATTERN.match(str(item.get("url") or ""))
            ),
            None,
        )
        if not stock_item:
            self.skipTest("current action queue has no stock item")

        match = STOCK_URL_PATTERN.match(str(stock_item["url"]))
        self.assertIsNotNone(match)
        code = match.group("code")

        profile = build_stock_profile_view(code)
        details = [profile[source] for source in profile["available_sources"]]
        self.assertTrue(details)

        for detail in details:
            self.assert_no_unsupported_strong_result_surface(detail)

    def test_first_opportunity_detail_keeps_degraded_result_copy_contract(self) -> None:
        opportunities = build_opportunities_view()
        opportunity_card = next(
            (
                card
                for group in opportunities.get("groups") or []
                for card in group.get("cards") or []
                if str(card.get("code") or "").strip()
            ),
            None,
        )
        if not opportunity_card:
            self.skipTest("current opportunities view has no stock item")

        detail = build_candidate_detail_view(str(opportunity_card["code"]))
        self.assert_renderable_detail_contract(detail)
        self.assert_no_unsupported_strong_result_surface(detail)

    def test_next_stock_page_keeps_degraded_result_presentation(self) -> None:
        source = STOCK_RESULT_PAGE_PATH.read_text(encoding="utf-8")

        self.assertIn("DecisionSummary", source)
        self.assertIn("visibleTabs", source)
        self.assertIn("当前页只展示已有链路能回源的纪律参考", source)
        self.assertIn("目标价、收益预测和完整财报研判暂不进入结果页", source)
        self.assertIn("managerUnavailable", source)
        self.assertIn("名单状态待同步", source)
        self.assertIn("name: stockName", source)
        self.assertIn("sourceIssueBadges", source)
        self.assertIn("自选股未命中", source)
        self.assertIn("观察池未命中", source)
        self.assertIn('mode="ask"', source)
        self.assertNotIn("Object.entries(askCase.canonical_decision)", source)
        self.assertNotIn("Object.entries(detail.canonical_decision)", source)

    def test_degraded_trigger_and_avoid_copy_stays_readable(self) -> None:
        self.assertEqual(
            normalize_trigger_sentence("当前没有单独触发说明"),
            "当前没有单独触发说明",
        )
        self.assertEqual(
            normalize_avoid_sentence("当前没有单独回避提示"),
            "当前没有单独回避提示",
        )
        self.assertEqual(
            normalize_trigger_sentence("等待风控阀门重新打开后再评估。"),
            "等待风控阀门重新打开后再评估。",
        )

    def assert_renderable_detail_contract(self, detail: dict[str, Any]) -> None:
        for key in ("generated_at", "code", "hero", "canonical_decision", "decision_cards", "execution_loop"):
            self.assertIn(key, detail)
        assert_non_empty_string(self, detail["generated_at"], "detail.generated_at")

        hero = detail["hero"]
        self.assertIn("title", hero)
        self.assertIn("summary", hero)
        assert_non_empty_string(self, hero["title"], "detail.hero.title")
        assert_non_empty_string(self, hero["summary"], "detail.hero.summary")

        canonical_decision = detail["canonical_decision"]
        self.assertTrue(REQUIRED_CANONICAL_DECISION_FIELDS.issubset(canonical_decision.keys()))
        for key in REQUIRED_CANONICAL_DECISION_FIELDS:
            assert_non_empty_string(self, canonical_decision[key], f"canonical_decision.{key}")

        decision_labels = {item.get("label") for item in detail["decision_cards"]}
        self.assertTrue(REQUIRED_DECISION_CARD_LABELS.issubset(decision_labels))

        execution_labels = {item.get("label") for item in detail["execution_loop"]}
        self.assertTrue(REQUIRED_EXECUTION_LOOP_LABELS.issubset(execution_labels))

    def assert_no_unsupported_strong_result_surface(self, detail: dict[str, Any]) -> None:
        keys = self.collect_keys(detail)
        unsupported = sorted(
            key
            for key in keys
            if any(fragment in key.lower() for fragment in UNSUPPORTED_STRONG_RESULT_KEY_FRAGMENTS)
        )
        self.assertEqual(unsupported, [], f"unsupported strong result fields leaked: {unsupported}")

        first_screen_surface = {
            "hero": detail.get("hero"),
            "topline": detail.get("topline"),
            "canonical_decision": detail.get("canonical_decision"),
            "decision_cards": detail.get("decision_cards"),
        }
        strings = self.collect_strings(first_screen_surface)
        leaked_copy = sorted(
            text
            for text in strings
            if any(fragment in text for fragment in UNSUPPORTED_STRONG_RESULT_TEXT_FRAGMENTS)
        )
        self.assertEqual(leaked_copy, [], f"unsupported strong result copy leaked: {leaked_copy}")

    def collect_keys(self, value: Any) -> set[str]:
        keys: set[str] = set()
        if isinstance(value, dict):
            for key, nested in value.items():
                keys.add(str(key))
                keys.update(self.collect_keys(nested))
        elif isinstance(value, list):
            for nested in value:
                keys.update(self.collect_keys(nested))
        return keys

    def collect_strings(self, value: Any) -> set[str]:
        strings: set[str] = set()
        if isinstance(value, str):
            if value.strip():
                strings.add(value.strip())
        elif isinstance(value, dict):
            for nested in value.values():
                strings.update(self.collect_strings(nested))
        elif isinstance(value, list):
            for nested in value:
                strings.update(self.collect_strings(nested))
        return strings

    def load_any_stock_detail(self, code: str) -> dict[str, Any]:
        errors: list[str] = []
        for loader in (build_watchlist_detail_view, build_candidate_detail_view):
            try:
                return loader(code)
            except KeyError as exc:
                errors.append(str(exc))
        raise AssertionError(f"stock route /stock/{code} has no watchlist or opportunity detail: {errors}")


if __name__ == "__main__":
    unittest.main()
