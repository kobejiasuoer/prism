from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient


INVEST_FLOW_ROOT = Path(__file__).resolve().parents[2]
if str(INVEST_FLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(INVEST_FLOW_ROOT))

from control_panel.app import app  # noqa: E402
from control_panel.dashboard_data import (  # noqa: E402
    build_stock_profile_detail_view,
    build_stock_profile_evidence_view,
    build_stock_profile_formal_data_section_view,
    build_stock_profile_formal_data_view,
    build_stock_profile_learning_scorecard,
    build_stock_profile_secondary_view,
    build_stock_profile_summary_view,
    build_stock_profile_today_action_view,
    build_candidate_detail_view,
    build_opportunities_view,
    build_today_action_contracts_view,
    build_today_command_brief_detail_view,
    clear_stock_profile_cache,
    build_today_actions_view,
    build_today_summary_view,
    build_today_view,
    build_watchlist_detail_view,
    normalize_avoid_sentence,
    normalize_trigger_sentence,
)


STOCK_URL_PATTERN = re.compile(r"^/stock/(?P<code>\d{6})$")
STOCK_RESULT_PAGE_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "stock" / "[code]" / "page.tsx"
STOCK_PROFILE_WORKSPACE_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "stock" / "[code]" / "stock-profile-workspace.tsx"
STOCK_DECISION_WORKSPACE_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "stock" / "[code]" / "stock-decision-workspace.tsx"
STOCK_DECISION_SUPPORT_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "stock" / "[code]" / "stock-decision-support.tsx"
STOCK_WATCHLIST_ACTIONS_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "stock" / "[code]" / "stock-watchlist-actions.tsx"
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

        for key in ("generated_at", "display_date", "trade_date", "brief_is_live", "hero", "summary_cards", "action_queue", "source_cards", "counts"):
            self.assertIn(key, payload)

        assert_non_empty_string(self, payload["generated_at"], "generated_at")
        assert_non_empty_string(self, payload["display_date"], "display_date")
        assert_non_empty_string(self, payload["trade_date"], "trade_date")
        self.assertEqual(payload["display_date"], payload["generated_at"].split(" ")[0])
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

    def test_today_summary_is_light_and_actions_are_lazy(self) -> None:
        summary = build_today_summary_view()

        self.assertTrue(summary["summary_only"])
        for key in ("generated_at", "trade_date", "readiness", "command_brief", "links_lazy"):
            self.assertIn(key, summary)
        self.assertNotIn("action_queue", summary)
        self.assertNotIn("decision_contracts", summary)
        self.assertNotIn("action_register", summary)
        self.assertNotIn("hero", summary)
        self.assertNotIn("source_cards", summary)
        self.assertNotIn("summary_cards", summary)
        self.assertNotIn("quality_cards", summary)
        self.assertNotIn("radar_cards", summary)
        self.assertEqual(summary["links_lazy"]["actions"], "/api/today/actions")
        self.assertEqual(summary["links_lazy"]["action_contracts"], "/api/today/action-contracts")
        self.assertEqual(summary["links_lazy"]["command_brief_detail"], "/api/today/command-brief-detail")
        self.assertNotIn("full", summary["links_lazy"])
        command_brief = summary.get("command_brief") or {}
        self.assertTrue(command_brief.get("details_deferred"))
        self.assertEqual(
            command_brief.get("links_lazy", {}).get("details"),
            "/api/today/command-brief-detail",
        )
        for key in ("forbid_today", "reclassify_when", "judgement_chain", "midday_verify"):
            self.assertNotIn(key, command_brief)

        response = self.client.get("/api/today/summary")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["summary_only"])
        self.assertNotIn("action_queue", body)
        self.assertNotIn("action_register", body)
        self.assertNotIn("full", body["links_lazy"])
        self.assertEqual(body["links_lazy"]["command_brief_detail"], "/api/today/command-brief-detail")

        detail = build_today_command_brief_detail_view()
        self.assertFalse(detail["details_deferred"])
        for key in ("forbid_today", "reclassify_when", "judgement_chain", "midday_verify"):
            self.assertIn(key, detail["command_brief_detail"])

        actions = build_today_actions_view()
        self.assertIn("action_queue", actions)
        self.assertTrue(actions["decision_contracts_deferred"])
        self.assertNotIn("decision_contracts", actions)
        self.assertIn("action_register", actions)
        counts = actions["action_register"]["counts"]
        self.assertIn("writable", counts)
        self.assertIn("read_only", counts)
        self.assertIn("stale", counts)

        contracts = build_today_action_contracts_view()
        self.assertIn("decision_contracts", contracts)
        self.assertIn("readiness_mode", contracts)

        actions_response = self.client.get("/api/today/actions")
        self.assertEqual(actions_response.status_code, 200)
        self.assertIn("action_queue", actions_response.json())

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

    def test_stock_profile_detail_prefers_watchlist_then_opportunity(self) -> None:
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

        detail = build_stock_profile_detail_view(code)
        self.assertEqual(detail["code"], code)
        self.assertIn("primary_source", detail)
        self.assertIn("primary_detail", detail)
        self.assertIn("available_sources", detail)
        self.assertIn(detail["primary_source"], {"watchlist", "opportunity"})
        self.assertIn(detail["primary_source"], detail["available_sources"])
        self.assertNotIn("watchlist", detail)
        self.assertNotIn("opportunity", detail)
        self.assertEqual(detail["links"]["api_self"], f"/api/stock/{code}/detail")
        self.assert_renderable_detail_contract(detail["primary_detail"])

    def test_stock_profile_detail_endpoint_returns_same_contract(self) -> None:
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

        response = self.client.get(f"/api/stock/{code}/detail")
        self.assertEqual(response.status_code, 200)
        detail = response.json()
        self.assertEqual(detail["code"], code)
        self.assertIn(detail["primary_source"], {"watchlist", "opportunity"})
        self.assertEqual(detail["links"]["api_self"], f"/api/stock/{code}/detail")
        self.assertEqual(detail["links"]["api_evidence"], f"/api/stock/{code}/evidence")
        self.assertEqual(detail["links"]["api_secondary"], f"/api/stock/{code}/secondary")
        self.assertNotIn("api_full", detail["links"])
        self.assertNotIn("watchlist", detail)
        self.assertNotIn("opportunity", detail)
        self.assert_renderable_detail_contract(detail["primary_detail"])

    def test_stock_profile_split_endpoints_keep_summary_light_and_slices_addressable(self) -> None:
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
        trade_date = today.get("trade_date")

        summary = build_stock_profile_summary_view(code, trade_date=trade_date)
        self.assertTrue(summary["summary_only"])
        self.assertEqual(summary["code"], code)
        self.assertIn("readiness", summary)
        self.assertIn("trust_level", summary["readiness"])
        self.assertNotIn("source_freshness", summary["readiness"])
        self.assertNotIn("formal_blockers", summary["readiness"])
        self.assertNotIn("warnings", summary["readiness"])
        self.assertNotIn("dataset_freshness", summary["readiness"])
        self.assertNotIn("formal_freshness", summary["readiness"])
        self.assertNotIn("capabilities", summary["readiness"])
        self.assertNotIn("formal_data", summary)
        self.assertNotIn("today_action", summary)
        self.assertNotIn("primary_detail", summary)
        self.assertEqual(summary["links"]["api_self"], f"/api/stock/{code}/summary")
        self.assertIn("api_detail", summary["links"])
        self.assertNotIn("api_formal_data", summary["links"])
        self.assertEqual(summary["links"]["api_formal_data_summary"], f"/api/stock/{code}/formal-data/summary")
        self.assertEqual(summary["links"]["api_formal_data_full"], f"/api/stock/{code}/formal-data/full")
        self.assertIn("api_today_action", summary["links"])
        self.assertNotIn("api_full", summary["links"])

        detail = build_stock_profile_detail_view(code, trade_date=trade_date)
        self.assertEqual(detail["code"], code)
        self.assertIn("primary_detail", detail)
        self.assertIn(detail["primary_source"], {"watchlist", "opportunity"})
        self.assertNotIn("watchlist", detail)
        self.assertNotIn("opportunity", detail)
        self.assertIn("trust_level", detail["readiness"])
        self.assertNotIn("source_freshness", detail["readiness"])
        self.assertNotIn("formal_blockers", detail["readiness"])
        self.assertNotIn("warnings", detail["readiness"])
        self.assertNotIn("dataset_freshness", detail["readiness"])
        self.assertNotIn("formal_freshness", detail["readiness"])
        self.assertNotIn("capabilities", detail["readiness"])
        self.assertEqual(detail["links"]["api_self"], f"/api/stock/{code}/detail")
        self.assertEqual(detail["links"]["api_evidence"], f"/api/stock/{code}/evidence")
        self.assertEqual(detail["links"]["api_secondary"], f"/api/stock/{code}/secondary")
        self.assertNotIn("api_formal_data", detail["links"])
        self.assertEqual(detail["links"]["api_formal_data_summary"], f"/api/stock/{code}/formal-data/summary")
        self.assertEqual(detail["links"]["api_formal_data_full"], f"/api/stock/{code}/formal-data/full")
        self.assertNotIn("api_full", detail["links"])
        for deferred_key in (
            "action_tier_legend",
            "artifacts",
            "capital_cards",
            "decision_explanation",
            "learning_memories",
            "links",
            "meta_cards",
            "metric_cards",
            "plan_rows",
            "related_status",
            "source_cards",
            "triggers",
        ):
            self.assertNotIn(deferred_key, detail["primary_detail"])
        self.assert_renderable_detail_contract(detail["primary_detail"])

        evidence = build_stock_profile_evidence_view(code, trade_date=trade_date)
        self.assertEqual(evidence["code"], code)
        self.assertIn(evidence["primary_source"], {"watchlist", "opportunity"})
        self.assertIn("source_cards", evidence)
        self.assertIn("artifacts", evidence)
        self.assertEqual(evidence["links"]["api_self"], f"/api/stock/{code}/evidence")
        self.assertEqual(evidence["links"]["api_detail"], f"/api/stock/{code}/detail")

        secondary = build_stock_profile_secondary_view(code, trade_date=trade_date)
        self.assertEqual(secondary["code"], code)
        self.assertIn(secondary["primary_source"], {"watchlist", "opportunity"})
        self.assertIn("secondary_detail", secondary)
        self.assertIsInstance(secondary["secondary_detail"], dict)
        self.assertEqual(secondary["links"]["api_self"], f"/api/stock/{code}/secondary")
        self.assertEqual(secondary["links"]["api_detail"], f"/api/stock/{code}/detail")

        formal = build_stock_profile_formal_data_view(code, trade_date=trade_date)
        self.assertEqual(formal["code"], code)
        self.assertIn("formal_data", formal)
        self.assertIn("available", formal["formal_data"])

        formal_summary = build_stock_profile_formal_data_section_view(code, "summary", trade_date=trade_date)
        self.assertEqual(formal_summary["code"], code)
        self.assertEqual(formal_summary["section"], "summary")
        self.assertTrue(formal_summary["formal_data"]["summary_only"])
        self.assertIn("source_cards", formal_summary["formal_data"])

        today_action = build_stock_profile_today_action_view(code, trade_date=trade_date)
        self.assertEqual(today_action["code"], code)
        self.assertIn("today_action", today_action)

        scorecard = build_stock_profile_learning_scorecard(code, trade_date=trade_date)
        self.assertEqual(scorecard["code"], code)
        self.assertFalse(scorecard["feeds_execution"])
        self.assertEqual(scorecard["stage"], "research")
        self.assertIn("learning_memories", scorecard)

        for suffix in (
            "summary",
            "detail",
            "evidence",
            "secondary",
            "formal-data/summary",
            "formal-data/full",
            "today-action",
            "learning-scorecard",
        ):
            response = self.client.get(f"/api/stock/{code}/{suffix}?trade_date={trade_date}")
            self.assertEqual(response.status_code, 200, suffix)
            self.assertEqual(response.json()["code"], code)

        formal_full = self.client.get(f"/api/stock/{code}/formal-data/full?trade_date={trade_date}").json()
        self.assertEqual(formal_full["section"], "full")
        self.assertIn("formal_data", formal_full)
        self.assertIn("available", formal_full["formal_data"])
        self.assertEqual(formal_full["links"]["api_self"], f"/api/stock/{code}/formal-data/full")

    def test_legacy_formal_data_default_endpoint_stays_removed(self) -> None:
        code = "600690"
        clear_stock_profile_cache(code)

        with patch(
            "control_panel.dashboard_data.build_stock_formal_data",
            side_effect=AssertionError("removed formal-data default must not build formal-data/full"),
        ) as formal_data:
            response = self.client.get(f"/api/stock/{code}/formal-data?trade_date=2026-06-10")

        self.assertEqual(response.status_code, 404)
        formal_data.assert_not_called()

    def test_legacy_stock_profile_aggregate_endpoints_stay_removed(self) -> None:
        code = "600690"
        clear_stock_profile_cache(code)

        with patch(
            "control_panel.app.build_stock_profile_detail_view",
            side_effect=AssertionError("removed stock aggregate must not build detail"),
        ) as detail_view, patch(
            "control_panel.dashboard_data.build_stock_profile_formal_data_view",
            side_effect=AssertionError("removed stock aggregate must not build formal-data/full"),
        ) as formal_data, patch(
            "control_panel.dashboard_data.build_stock_profile_today_action_view",
            side_effect=AssertionError("removed stock aggregate must not build today-action"),
        ) as today_action, patch(
            "control_panel.app.build_stock_profile_full_view",
            create=True,
            side_effect=AssertionError("removed stock aggregate must not build full profile"),
        ) as full_profile:
            for path in (f"/api/stock/{code}", f"/api/stock/{code}/full"):
                with self.subTest(path=path):
                    self.assertEqual(self.client.get(path).status_code, 404)

        detail_view.assert_not_called()
        formal_data.assert_not_called()
        today_action.assert_not_called()
        full_profile.assert_not_called()

    def test_stock_profile_split_endpoints_return_degradable_empty_profile_for_unknown_stock(self) -> None:
        code = "000000"
        summary = build_stock_profile_summary_view(code)
        detail = build_stock_profile_detail_view(code)

        for payload in (summary, detail):
            self.assertEqual(payload["code"], code)
            self.assertIsNone(payload["primary_source"])
            self.assertEqual(payload["available_sources"], [])

        self.assertIn("watchlist", detail["errors"])
        self.assertIn("opportunity", detail["errors"])
        self.assertIsNone(detail["primary_detail"])
        for path in (f"/api/stock/{code}/summary", f"/api/stock/{code}/detail"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["code"], code)

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

        detail = build_stock_profile_detail_view(code)
        self.assert_renderable_detail_contract(detail["primary_detail"])
        self.assert_no_unsupported_strong_result_surface(detail["primary_detail"])

        evidence = build_stock_profile_evidence_view(code)
        self.assertIn("source_cards", evidence)
        self.assertIn("artifacts", evidence)

    def test_first_opportunity_detail_keeps_degraded_result_copy_contract(self) -> None:
        opportunities = build_opportunities_view()
        opportunity_card = next(
            (
                card
                for group in opportunities.get("groups") or []
                for card in group.get("cards") or []
                if str(card.get("code") or "").strip()
                and not str(card.get("action_key") or "").startswith("lifecycle:")
            ),
            None,
        )
        if not opportunity_card:
            self.skipTest("current opportunities view has no candidate-detail stock item")

        detail = build_candidate_detail_view(str(opportunity_card["code"]))
        self.assert_renderable_detail_contract(detail)
        self.assert_no_unsupported_strong_result_surface(detail)

    def test_next_stock_page_keeps_degraded_result_presentation(self) -> None:
        page_source = STOCK_RESULT_PAGE_PATH.read_text(encoding="utf-8")
        page_compact_source = "".join(page_source.split())
        source = STOCK_PROFILE_WORKSPACE_PATH.read_text(encoding="utf-8")
        workspace_source = STOCK_DECISION_WORKSPACE_PATH.read_text(encoding="utf-8")
        support_source = STOCK_DECISION_SUPPORT_PATH.read_text(encoding="utf-8")
        watchlist_actions = STOCK_WATCHLIST_ACTIONS_PATH.read_text(encoding="utf-8")

        self.assertIn('import("./stock-profile-workspace").then(', page_compact_source)
        self.assertIn("module.StockProfileWorkspace", page_source)
        self.assertIn("return <StockProfileWorkspace />", page_source)
        self.assertNotIn("getStockProfile(", page_source)

        self.assertIn("useStockProfileSummary(code)", source)
        self.assertIn("useStockProfileDetail(code", source)
        self.assertIn("useStockProfileTodayAction(code", source)
        self.assertIn("useStockProfileFormalDataSection(code, \"summary\"", source)
        self.assertIn("useStockProfileFormalDataSection(code, \"profile\"", source)
        self.assertIn("useStockProfileFormalDataSection(code, \"risk\"", source)
        self.assertIn("useStockProfileFormalDataSection(code, \"sources\"", source)
        self.assertIn("useStockProfileEvidence(code", source)
        self.assertIn("useStockProfileSecondary(code", source)
        self.assertIn("useStockProfileLearningScorecard(code", source)
        self.assertIn("StockDecisionHeroPanels", source)
        self.assertIn("StockDecisionTabWorkspace", source)
        self.assertIn("detail={detail}", source)
        self.assertIn("todayAction={todayAction}", source)
        self.assertIn("sources={stockEvidence.data?.source_cards}", source)
        self.assertIn("artifacts={stockEvidence.data?.artifacts}", source)
        self.assertIn("detail={secondaryDetail || detail}", source)
        self.assertIn("const detailEnabled =", source)
        self.assertNotIn("profile.watchlist", source)
        self.assertNotIn("profile.opportunity", source)
        self.assertNotIn("profile.primary_detail", source)
        self.assertNotIn("profile.formal_data", source)
        self.assertNotIn("profile.today_action", source)

        self.assertIn("StockDecisionHeroPanels", workspace_source)
        self.assertIn("StockDecisionTabWorkspace", workspace_source)
        self.assertIn("StockDecisionContext", support_source)
        self.assertIn("canonical_decision", support_source)
        self.assertIn("trigger_condition", support_source)
        self.assertIn("risk_boundary", support_source)
        self.assertIn("avoid_action", support_source)
        self.assertIn("continue_condition", support_source)
        self.assertIn("stop_condition", support_source)
        self.assertIn("confidence_note", support_source)
        self.assertIn("useWatchlistManager({ enabled: true })", watchlist_actions)
        self.assertNotIn("canonical_decision", watchlist_actions)
        self.assertNotIn("强烈买入", workspace_source)
        self.assertNotIn("建议买入", workspace_source)
        self.assertNotIn("开新仓", workspace_source)
        self.assertNotIn("满仓", workspace_source)
        self.assertNotIn("目标价", workspace_source)
        self.assertNotIn("收益预测", workspace_source)

        compact_source = "".join(source.split())
        self.assertIn('activeTab==="追问"', compact_source)
        self.assertIn('activeTab==="持仓"', compact_source)
        self.assertIn('activeTab==="发现"', compact_source)
        self.assertIn('activeTab==="证据"', compact_source)
        self.assertIn("stockSecondary.data?.secondary_detail", compact_source)
        self.assertIn("stockEvidence.data?.source_cards", compact_source)
        self.assertIn("formalSummary", source)
        self.assertIn("formalProfile", source)
        self.assertIn("formalRisk", source)
        self.assertIn("formalSources", source)
        self.assertIn("learningScorecardQuery.data", source)

        self.assertIn('role="tablist"', source)
        self.assertIn('role="tab"', source)
        self.assertIn('aria-selected={activeTab === tab}', source)
        self.assertIn('aria-controls={`stock-panel-${tab}`}', source)
        self.assertIn('role="tabpanel"', source)
        self.assertIn("id={`stock-panel-${activeTab}`}", source)
        self.assertNotIn("href=\"#", source)

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
