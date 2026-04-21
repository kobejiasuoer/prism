from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import re

from fastapi.testclient import TestClient


INVEST_FLOW_ROOT = Path(__file__).resolve().parents[2]
if str(INVEST_FLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(INVEST_FLOW_ROOT))

from control_panel.app import TEMPLATES, app  # noqa: E402
from control_panel.dashboard_data import (  # noqa: E402
    TODAY_ACTION_STATE_PATH,
    build_ask_followup_view,
    build_opportunities_view,
    build_review_action_rules,
    build_review_view,
    build_today_next_steps,
    compress_today_actions,
    normalize_review_note_text,
    resolve_ask_stock,
    watchlist_refresh_progress,
)

WATCHLIST_CONFIG_PATH = INVEST_FLOW_ROOT.parent / "stock-analyzer" / "config" / "stocks.json"


class ControlPanelSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def _first_opportunity_detail_url(self) -> str:
        response = self.client.get("/api/opportunities")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        for group in payload.get("groups") or []:
            for card in group.get("cards") or []:
                detail_url = str(card.get("detail_url") or "").strip()
                if detail_url.startswith("/opportunities/"):
                    return detail_url
        self.fail("no opportunity detail_url found in /api/opportunities payload")

    def _mock_opportunities_inputs(
        self,
        *,
        allow_new_positions: bool,
        approved: list[dict[str, object]],
        caution: list[dict[str, object]],
        fresh_candidates: list[dict[str, object]] | None = None,
        confirmed: list[dict[str, object]] | None = None,
    ) -> dict[str, dict[str, object]]:
        return {
            "decision_brief": {
                "trade_date": "2026-04-21",
                "generated_at": "2026-04-21 09:20:00",
                "focus": {"opportunity_focus": ["先看节奏"], "avoid_points": ["追高"]},
                "summary": {"gate_summary": "优先看高质量触发"},
            },
            "watchlist": {"trade_date": "2026-04-21", "generated_at": "2026-04-21 09:25:00"},
            "screening_batch": {
                "generated_at": "2026-04-21 09:30:00",
                "path": "/tmp/mock-screening.json",
                "market_regime": {
                    "execution_gate": {
                        "allow_new_positions": allow_new_positions,
                        "label": "进攻阀门关闭" if not allow_new_positions else "进攻阀门开启",
                        "position_cap": "0-0.5成",
                    }
                },
                "screening_summary": {
                    "approved_count": len(approved),
                    "caution_count": len(caution),
                },
                "pool": "aggressive",
                "pool_label": "进攻池",
                "candidates": [*approved, *caution],
                "market_themes": {"top_theme": "算力", "themes": []},
            },
            "confirmation": {
                "generated_at": "2026-04-21 12:05:00",
                "path": "/tmp/mock-confirmation.json",
                "validation_status": "ok",
                "fresh_candidates": list(fresh_candidates or []),
                "confirmed": list(confirmed or []),
                "counts": {
                    "fresh_candidates": len(fresh_candidates or []),
                    "confirmed": len(confirmed or []),
                },
            },
        }

    def test_html_routes_return_200(self) -> None:
        opportunity_detail_url = self._first_opportunity_detail_url()
        paths = [
            "/",
            "/today",
            "/ask",
            "/watchlist",
            "/opportunities",
            "/review",
            "/watchlist/000625",
            opportunity_detail_url,
            "/opportunities/batch/screener",
            "/review/detail?section=ai_regime_rows&label=0-3%20%E5%BC%B1%E7%8E%AF%E5%A2%83",
        ]
        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn("text/html", response.headers.get("content-type", ""))

    def test_review_page_exposes_extended_sections(self) -> None:
        response = self.client.get("/review")
        self.assertEqual(response.status_code, 200)
        self.assertIn("三条动作规则", response.text)
        self.assertIn("最近结论变化", response.text)
        self.assertIn("打开详细研究", response.text)
        self.assertIn("data-preview-path=", response.text)
        self.assertIn("打开原始报告", response.text)
        self.assertNotIn("研究窗口与对比", response.text)
        self.assertNotIn("数据来源</h2>", response.text)
        self.assertNotIn("<built-in method copy", response.text)

    def test_ask_first_paint_is_search_first(self) -> None:
        response = self.client.get("/ask")
        self.assertEqual(response.status_code, 200)
        self.assertIn("先给结论，再给边界", response.text)
        self.assertNotIn("使用方式", response.text)
        self.assertNotIn("你会先看到什么", response.text)
        self.assertNotIn("首版范围", response.text)

    def test_ask_first_paint_keeps_recent_queries_when_available(self) -> None:
        mocked = {
            "query": "",
            "error": "",
            "case": None,
            "examples": [],
            "recent_queries": [
                {
                    "url": "/ask?q=600690",
                    "tag": "最近问过",
                    "name": "海尔智家",
                    "detail": "600690 · 已分析",
                }
            ],
            "followup": None,
            "hero": {
                "title": "问一只股票，直接给结论和边界",
                "summary": "先给结论，再给边界。",
            },
            "manager": {
                "add_api": "/api/watchlist/manage/add",
                "restore_api": "/api/watchlist/manage/restore",
            },
            "links": {
                "suggest_api": "/api/ask/suggest",
                "followup_api": "/api/ask/followup",
                "api_self": "/api/ask",
                "watchlist": "/watchlist",
                "opportunities": "/opportunities",
            },
        }
        with patch("control_panel.app.build_ask_page_view", return_value=mocked):
            response = self.client.get("/ask")
        self.assertEqual(response.status_code, 200)
        self.assertIn("最近问过", response.text)
        self.assertIn("海尔智家", response.text)

    def test_dashboard_is_ops_secondary_surface(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn("系统健康", html)
        self.assertIn("失败或阻塞任务", html)
        self.assertIn("手动触发", html)
        self.assertIn('<details id="ops-lanes"', html)
        self.assertIn('<details id="ops-runs"', html)
        self.assertNotIn('<details id="ops-lanes" class="progressive-section dashboard-ops-fold" open', html)
        self.assertNotIn('<details id="ops-runs" class="progressive-section dashboard-runs-fold" open', html)
        self.assertNotIn("投资系统轻量控制台", html)
        self.assertNotIn("先确认主链路有没有断，再决定要不要手动重跑", html)

    def test_ibm_preview_mode_is_opt_in(self) -> None:
        default_dashboard = self.client.get("/")
        self.assertEqual(default_dashboard.status_code, 200)
        self.assertNotIn("/static/control-panel-ibm-preview.css", default_dashboard.text)
        self.assertNotIn('data-preview-theme="ibm-preview"', default_dashboard.text)

        default_ask = self.client.get("/ask")
        self.assertEqual(default_ask.status_code, 200)
        self.assertNotIn("/static/control-panel-ibm-preview.css", default_ask.text)
        self.assertNotIn('data-preview-theme="ibm-preview"', default_ask.text)

    def test_ibm_preview_mode_adds_preview_contract_to_dashboard_and_ask(self) -> None:
        dashboard_response = self.client.get("/?theme=ibm-preview")
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertIn("/static/control-panel-ibm-preview.css", dashboard_response.text)
        self.assertIn('data-preview-theme="ibm-preview"', dashboard_response.text)
        self.assertIn("IBM 预览", dashboard_response.text)

        ask_response = self.client.get("/ask?q=600690&theme=ibm-preview")
        self.assertEqual(ask_response.status_code, 200)
        self.assertIn("/static/control-panel-ibm-preview.css", ask_response.text)
        self.assertIn('data-preview-theme="ibm-preview"', ask_response.text)
        self.assertIn("IBM 预览", ask_response.text)

    def test_ibm_preview_mode_extends_to_core_product_surfaces(self) -> None:
        for path in ("/today?theme=ibm-preview", "/watchlist?theme=ibm-preview", "/opportunities?theme=ibm-preview", "/review?theme=ibm-preview"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn("/static/control-panel-ibm-preview.css", response.text)
                self.assertIn('data-preview-theme="ibm-preview"', response.text)
                self.assertIn("IBM 预览", response.text)

    def test_ibm_preview_mode_keeps_main_navigation_inside_preview(self) -> None:
        response = self.client.get("/today?theme=ibm-preview")
        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn('href="/today?theme=ibm-preview"', html)
        self.assertIn('href="/ask?theme=ibm-preview"', html)
        self.assertIn('href="/watchlist?theme=ibm-preview"', html)
        self.assertIn('href="/opportunities?theme=ibm-preview"', html)
        self.assertIn('href="/review?theme=ibm-preview"', html)

    def test_ask_and_dashboard_keep_preview_surfaces(self) -> None:
        ask_response = self.client.get("/ask?q=600690")
        self.assertEqual(ask_response.status_code, 200)
        self.assertIn('id="preview-shell"', ask_response.text)
        self.assertIn("data-preview-path=", ask_response.text)

        dashboard_response = self.client.get("/")
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertIn('id="preview-shell"', dashboard_response.text)
        self.assertIn("data-preview-path=", dashboard_response.text)

    def test_review_page_promotes_action_rules_and_real_change_log(self) -> None:
        response = self.client.get("/review")
        self.assertEqual(response.status_code, 200)
        self.assertIn("三条动作规则", response.text)
        self.assertIn("最近结论变化", response.text)
        self.assertIn("打开详细研究", response.text)
        self.assertNotIn("研究窗口与对比", response.text)
        self.assertNotIn("数据来源</h2>", response.text)

    def test_review_page_cta_anchor_contract_supports_open_on_anchor(self) -> None:
        response = self.client.get("/review")
        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn('href="#review-control"', html)
        self.assertIn('href="#review-evidence"', html)
        self.assertRegex(
            html,
            re.compile(r'<details id="review-control"[^>]*data-open-on-anchor[^>]*>'),
        )
        self.assertRegex(
            html,
            re.compile(r'<details id="review-evidence"[^>]*data-open-on-anchor[^>]*>'),
        )
        self.assertIn('target.matches("details[data-open-on-anchor]")', html)
        self.assertIn("window.addEventListener(\"hashchange\", openAnchorFold)", html)

    def test_review_first_paint_order_and_collapsed_layers(self) -> None:
        response = self.client.get("/review")
        self.assertEqual(response.status_code, 200)
        html = response.text

        verdict_index = html.find('class="decision-topline"')
        rules_index = html.find('id="review-action-rules"')
        changes_index = html.find('id="review-changes"')
        compare_index = html.find('id="review-compare"')
        self.assertGreaterEqual(verdict_index, 0)
        self.assertGreaterEqual(rules_index, 0)
        self.assertGreaterEqual(changes_index, 0)
        self.assertGreaterEqual(compare_index, 0)
        self.assertLess(verdict_index, rules_index)
        self.assertLess(rules_index, changes_index)
        self.assertLess(changes_index, compare_index)

        self.assertIn("研究细节", html)
        self.assertIn("原始报告", html)
        self.assertIn('<details id="review-control"', html)
        self.assertIn('<details id="review-evidence"', html)
        self.assertNotIn('<details id="review-control" class="progressive-section review-research-fold" data-open-on-anchor open', html)
        self.assertNotIn('<details id="review-evidence" class="progressive-section review-artifacts-fold" data-open-on-anchor open', html)

    def test_build_review_view_exposes_action_first_contract(self) -> None:
        payload = build_review_view()
        self.assertIn("topline", payload)
        self.assertIn("action_rules", payload)
        self.assertIn("change_log", payload)
        self.assertIn("mini_compare", payload)
        self.assertEqual(len(payload["action_rules"]), 3)
        self.assertIn("entries", payload["change_log"])
        self.assertGreaterEqual(len(payload["mini_compare"]), 3)

    def test_build_review_action_rules_preserves_rule_intensity(self) -> None:
        rules = build_review_action_rules(
            [
                {
                    "title": "弱环境继续回避",
                    "subtitle": "弱环境",
                    "status": "回避",
                    "tone": "risk",
                    "copy": "弱环境继续收手。",
                    "foot": "弱环境没转正前不开新仓。",
                    "metrics": ["Q1 -0.8%", "当前 -0.4%"],
                },
                {
                    "title": "只在试错环境试单",
                    "subtitle": "试错环境",
                    "status": "试错",
                    "tone": "positive",
                    "copy": "试错环境有正反馈。",
                    "foot": "保持轻仓分批。",
                    "metrics": ["Q1 +0.2%", "当前 +0.5%"],
                },
                {
                    "title": "当前切片没有进攻环境样本",
                    "subtitle": "进攻环境",
                    "status": "缺样本",
                    "tone": "watch",
                    "copy": "进攻环境还没稳定。",
                    "foot": "没有样本前不放量。",
                    "metrics": ["Q1 +0.9%", "当前无样本"],
                },
            ],
            freshness="2026-04-21 10:00:00",
        )
        self.assertEqual(rules[0]["action"], "少动，先防守")
        self.assertEqual(rules[1]["action"], "轻仓试错")
        self.assertEqual(rules[2]["action"], "先等确认")

    def test_normalize_review_note_text_only_rewrites_targeted_history_phrase(self) -> None:
        self.assertEqual(
            normalize_review_note_text("避免在线接口回看历史时漂移或超时"),
            "避免远端历史接口回看时漂移或超时",
        )
        self.assertEqual(
            normalize_review_note_text("这份备注不需要改写在线接口这个词"),
            "这份备注不需要改写在线接口这个词",
        )

    def test_product_pages_expose_new_layout_sections(self) -> None:
        cases = [
            ("/today", ["一句总判断", "下一步动作", "Top 3 今日动作", "状态细栏"]),
            ("/ask", ["股票代码或名称", "开始分析", "先输入一只股票"]),
            ("/watchlist", ["持仓总览", "自选股管理", "添加并刷新", "归档只隐藏", "更新快照", "原始数据入口"]),
            (
                "/opportunities",
                [("Top 3 可执行候选", "Top 3 观察/午盘承接候选"), "其余观察与午盘承接", "主线雷达", "质检与原始数据"],
            ),
        ]
        for path, markers in cases:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                for marker in markers:
                    if isinstance(marker, tuple):
                        self.assertTrue(any(option in response.text for option in marker))
                    else:
                        self.assertIn(marker, response.text)

    def test_theme_toggle_present_on_core_pages(self) -> None:
        for path in ["/", "/today", "/ask", "/watchlist", "/opportunities", "/review"]:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn("data-theme-option=\"light\"", response.text)
                self.assertIn("data-theme-option=\"dark\"", response.text)
                self.assertIn("data-theme-option=\"system\"", response.text)
                self.assertIn("/static/control-panel-theme.js", response.text)

    def test_product_pages_expose_confidence_switch(self) -> None:
        for path in ["/watchlist", "/opportunities", "/review"]:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn("可信度总开关", response.text)

    def test_core_pages_do_not_use_retired_status_words(self) -> None:
        retired_words = [
            "在线",
            "可直接用",
            "比较可用",
            "当日有效",
            "可直接看新仓",
            "可直接执行",
            "可直接比较",
        ]
        for path in ["/today", "/ask", "/watchlist", "/opportunities", "/review"]:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                for word in retired_words:
                    with self.subTest(path=path, word=word):
                        self.assertNotIn(word, response.text)

    def test_today_page_uses_investor_dispatch_markers(self) -> None:
        response = self.client.get("/today")
        self.assertEqual(response.status_code, 200)
        self.assertIn("下一步动作", response.text)
        self.assertIn("Top 3 今日动作", response.text)
        self.assertIn("状态细栏", response.text)
        self.assertNotIn("<h1>一句总判断</h1>", response.text)
        self.assertRegex(response.text, re.compile(r'today-next-step-link[\s\S]*?href="/watchlist"'))
        self.assertRegex(response.text, re.compile(r'today-next-step-link[\s\S]*?href="/opportunities"'))
        self.assertRegex(response.text, re.compile(r'today-next-step-link[\s\S]*?href="/review"'))
        self.assertRegex(response.text, re.compile(r'today-next-step-link[\s\S]*?aria-current="step"'))
        self.assertNotIn("今日操作清单", response.text)
        self.assertNotIn("可信度总开关", response.text)

    def test_today_first_paint_order_and_collapsed_layers(self) -> None:
        response = self.client.get("/today")
        self.assertEqual(response.status_code, 200)
        html = response.text

        verdict_index = html.find('class="decision-topline"')
        next_step_index = html.find("下一步动作")
        top3_index = html.find("Top 3 今日动作")
        status_index = html.find("状态细栏")
        self.assertGreaterEqual(verdict_index, 0)
        self.assertGreaterEqual(next_step_index, 0)
        self.assertGreaterEqual(top3_index, 0)
        self.assertGreaterEqual(status_index, 0)
        self.assertLess(verdict_index, next_step_index)
        self.assertLess(next_step_index, top3_index)
        self.assertLess(top3_index, status_index)

        self.assertIn("更多动作/背景", html)
        self.assertIn("来源/质量", html)
        self.assertIn("<details class=\"progressive-section\">", html)
        self.assertNotIn("<details class=\"progressive-section\" open", html)

    def test_watchlist_page_promotes_priority_top3_and_folds_manager(self) -> None:
        response = self.client.get("/watchlist")
        self.assertEqual(response.status_code, 200)
        self.assertIn("优先处理 Top 3", response.text)
        self.assertIn("其余待观察", response.text)
        self.assertIn("打开自选股管理", response.text)
        self.assertNotIn("自选股管理</h2>", response.text)

    def test_opportunities_page_promotes_top_three_candidates(self) -> None:
        response = self.client.get("/opportunities")
        self.assertEqual(response.status_code, 200)
        self.assertTrue("Top 3 可执行候选" in response.text or "Top 3 观察/午盘承接候选" in response.text)
        self.assertIn("其余观察与午盘承接", response.text)
        self.assertNotIn("机会总览", response.text)
        self.assertNotIn("主线雷达</h2>", response.text)

    def test_opportunities_view_gate_closed_prefers_watch_rows_even_with_approved_candidates(self) -> None:
        mocked = self._mock_opportunities_inputs(
            allow_new_positions=False,
            approved=[
                {
                    "code": "600001",
                    "name": "通过标的",
                    "screening_status": "approved",
                    "setup_label": "突破回踩",
                    "entry_reason": "早盘确认通过",
                    "main_risk": "回踩失守",
                    "updated_at": "2026-04-21 09:35:00",
                    "execution_quality": {"label": "高执行"},
                }
            ],
            caution=[
                {
                    "code": "300001",
                    "name": "观察标的",
                    "screening_status": "caution",
                    "setup_label": "承接观察",
                    "entry_reason": "仍需确认",
                    "main_risk": "量能不足",
                    "updated_at": "2026-04-21 09:40:00",
                    "execution_quality": {"label": "待确认"},
                }
            ],
            fresh_candidates=[
                {
                    "code": "300002",
                    "name": "午盘新增",
                    "status": "fresh",
                    "setup_label": "回踩承接",
                    "entry_reason": "午盘新增观察",
                    "main_risk": "冲高回落",
                    "updated_at": "2026-04-21 12:10:00",
                }
            ],
            confirmed=[],
        )
        with patch("control_panel.dashboard_data.load_decision_brief", return_value=mocked["decision_brief"]), patch(
            "control_panel.dashboard_data.load_watchlist_snapshot", return_value=mocked["watchlist"]
        ), patch("control_panel.dashboard_data.load_screening_batch", return_value=mocked["screening_batch"]), patch(
            "control_panel.dashboard_data.load_confirmation", return_value=mocked["confirmation"]
        ), patch(
            "control_panel.dashboard_data.load_quality_status",
            return_value={
                "validation_status": "ok",
                "checked_at": "2026-04-21 12:12:00",
                "expected_timestamp": "2026-04-21 12:10:00",
            },
        ):
            payload = build_opportunities_view()

        self.assertTrue(payload["promote_watch"])
        top_titles = [str(row.get("title") or "") for row in payload["top_rows"]]
        self.assertTrue(any("观察标的 300001" in title for title in top_titles))
        self.assertFalse(any("通过标的 600001" in title for title in top_titles))
        self.assertEqual(payload["topline"]["verdict_title"], "今天没有可执行新仓。")
        self.assertEqual(payload["topline"]["meta_pills"][2]["value"], "0")

    def test_opportunities_page_uses_watch_fallback_copy_when_no_approved_candidates(self) -> None:
        mocked = self._mock_opportunities_inputs(
            allow_new_positions=True,
            approved=[],
            caution=[
                {
                    "code": "300003",
                    "name": "观察回落",
                    "screening_status": "caution",
                    "setup_label": "止跌观察",
                    "entry_reason": "仅观察不追",
                    "main_risk": "反抽失败",
                    "updated_at": "2026-04-21 09:50:00",
                    "execution_quality": {"label": "待确认"},
                }
            ],
            fresh_candidates=[],
            confirmed=[],
        )
        with patch("control_panel.dashboard_data.load_decision_brief", return_value=mocked["decision_brief"]), patch(
            "control_panel.dashboard_data.load_watchlist_snapshot", return_value=mocked["watchlist"]
        ), patch("control_panel.dashboard_data.load_screening_batch", return_value=mocked["screening_batch"]), patch(
            "control_panel.dashboard_data.load_confirmation", return_value=mocked["confirmation"]
        ), patch(
            "control_panel.dashboard_data.load_quality_status",
            return_value={
                "validation_status": "ok",
                "checked_at": "2026-04-21 10:00:00",
                "expected_timestamp": "2026-04-21 09:55:00",
            },
        ):
            response = self.client.get("/opportunities")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Top 3 观察/午盘承接候选", response.text)
        self.assertIn("今天没有可执行新仓。先看 3 只观察名单，再等午盘承接确认。", response.text)
        self.assertNotIn("通过标的 600001", response.text)

    def test_opportunities_page_cta_anchor_contract_supports_open_on_anchor(self) -> None:
        response = self.client.get("/opportunities")
        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn('href="#opportunities-secondary"', html)
        self.assertIn('href="#opportunities-themes"', html)
        self.assertIn('href="#opportunities-support"', html)
        self.assertRegex(
            html,
            re.compile(r'<details id="opportunities-secondary"[^>]*data-open-on-anchor[^>]*>'),
        )
        self.assertRegex(
            html,
            re.compile(r'<details id="opportunities-themes"[^>]*data-open-on-anchor[^>]*>'),
        )
        self.assertRegex(
            html,
            re.compile(r'<details id="opportunities-support"[^>]*data-open-on-anchor[^>]*>'),
        )
        self.assertIn('target.matches("details[data-open-on-anchor]")', html)
        self.assertIn("window.addEventListener(\"hashchange\", openAnchorFold)", html)

    def test_build_today_next_steps_routes_by_urgent_lane(self) -> None:
        links = {
            "watchlist": "/watchlist",
            "opportunities": "/opportunities",
            "review": "/review",
        }

        old_first = build_today_next_steps(
            [
                {
                    "key": "do-now",
                    "items": [
                        {"title": "长安汽车 000625", "source": "持仓优先", "url": "/watchlist/000625"},
                        {"title": "包钢股份 600010", "source": "早盘通过", "url": "/opportunities/600010"},
                    ],
                },
                {"key": "watch", "items": []},
                {"key": "avoid", "items": []},
            ],
            links=links,
        )
        self.assertEqual(old_first["current_key"], "old_positions")
        self.assertEqual(old_first["current_href"], "/watchlist")

        new_first = build_today_next_steps(
            [
                {
                    "key": "do-now",
                    "items": [
                        {"title": "包钢股份 600010", "source": "早盘通过", "url": "/opportunities/600010"},
                        {"title": "华友钴业 603799", "source": "午盘保留", "url": "/opportunities/603799"},
                    ],
                },
                {"key": "watch", "items": []},
                {"key": "avoid", "items": []},
            ],
            links=links,
        )
        self.assertEqual(new_first["current_key"], "new_positions")
        self.assertEqual(new_first["current_href"], "/opportunities")

    def test_compress_today_actions_prefers_actionable_status(self) -> None:
        rows = compress_today_actions(
            {
                "items": [
                    {
                        "title": "长安汽车 000625",
                        "status": "减仓观望",
                        "decision": {"label": "待确认"},
                        "metrics": ["跌破 13.80"],
                        "detail": "主力连续流出",
                        "freshness": {"label": "04-20 14:55:57"},
                    },
                    {
                        "title": "包钢股份 600010",
                        "status": "",
                        "decision": {"label": "继续观察"},
                        "metrics": ["站回 1.30"],
                        "detail": "量能承接一般",
                        "freshness": {"label": "04-20 14:50:00"},
                    },
                ]
            }
        )
        self.assertEqual(rows[0]["action"], "减仓观望")
        self.assertEqual(rows[1]["action"], "继续观察")

    def test_product_pages_expose_refresh_surface(self) -> None:
        checks = [
            ("/today", "data-refresh-page=\"today\""),
            ("/watchlist", "data-refresh-page=\"watchlist\""),
            ("/opportunities", "data-refresh-page=\"opportunities\""),
        ]
        for path, marker in checks:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn(marker, response.text)
                self.assertIn("data-refresh-panel", response.text)
                self.assertIn("data-refresh-trigger", response.text)
                self.assertIn("/static/control-panel-refresh.js", response.text)

    def test_product_pages_expose_stage_flow(self) -> None:
        for path in ["/today", "/ask", "/watchlist", "/opportunities", "/review"]:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn("stage-flow", response.text)
                self.assertIn("当前阶段", response.text)
                self.assertTrue("下一步" in response.text or "上一步" in response.text)

    def test_primary_nav_demotes_ops_and_keeps_five_investor_tabs(self) -> None:
        response = self.client.get("/today")
        self.assertEqual(response.status_code, 200)
        self.assertIn('href="/today"', response.text)
        self.assertIn('href="/ask"', response.text)
        self.assertIn('href="/watchlist"', response.text)
        self.assertIn('href="/opportunities"', response.text)
        self.assertIn('href="/review"', response.text)
        self.assertNotIn('class="nav-chip" href="/"', response.text)

    def test_stage_flow_is_compact_and_action_oriented(self) -> None:
        response = self.client.get("/today")
        self.assertEqual(response.status_code, 200)
        self.assertIn("stage-flow-compact", response.text)
        self.assertIn("上一步", response.text)
        self.assertIn("下一步", response.text)

    def test_active_nav_and_stage_links_expose_aria_current_page(self) -> None:
        today_response = self.client.get("/today")
        self.assertEqual(today_response.status_code, 200)
        self.assertRegex(today_response.text, re.compile(r'<a[^>]*class="[^"]*nav-chip[^"]*"[^>]*href="/today"[^>]*aria-current="page"'))
        self.assertIn("当前阶段", today_response.text)
        self.assertIn("阶段 1/5", today_response.text)
        self.assertIn('class="stage-jump stage-jump-next"', today_response.text)
        self.assertNotIn("stage-step-link", today_response.text)

        page_nav_html = TEMPLATES.env.get_template("_page_nav.html").render(
            nav_active="ops",
            nav_links={
                "today": "/today",
                "ask": "/ask",
                "watchlist": "/watchlist",
                "opportunities": "/opportunities",
                "review": "/review",
                "ops": "/",
            },
            show_api_link=False,
            nav_api_href=None,
        )
        self.assertRegex(page_nav_html, re.compile(r'<a[^>]*class="[^"]*nav-ops-link[^"]*"[^>]*href="/"[^>]*aria-current="page"'))

    def test_shared_partials_expose_generic_decision_shell_contracts(self) -> None:
        status_strip_html = TEMPLATES.env.get_template("_status_strip.html").render(
            status_strip_label="来源/质量/新鲜度",
            status_items=[
                {"label": "来源", "value": "Canonical", "note": "today-brief", "tone": "good"},
                {"label": "质量", "value": "通过", "note": "gate ok", "tone": "good"},
                {"label": "新鲜度", "value": "14:35", "note": "5m", "tone": "warn"},
            ],
        )
        self.assertIn("status-strip-item-label", status_strip_html)
        self.assertIn("Canonical", status_strip_html)
        self.assertIn("today-brief", status_strip_html)
        self.assertIn("status-strip-item-good", status_strip_html)
        self.assertIn("status-strip-item-warn", status_strip_html)

        decision_topline_html = TEMPLATES.env.get_template("_decision_topline.html").render(
            verdict_badge="一句判断",
            verdict_title="先处理持仓风险，再看新增机会",
            verdict_summary="今天先做收缩动作。",
            meta_pills=[{"label": "仓位", "value": "0.3-0.5成"}, {"label": "阀门", "value": "半开"}],
            cta_links=[{"label": "查看证据", "href": "/today"}],
        )
        self.assertIn("decision-topline-title", decision_topline_html)
        self.assertIn("先处理持仓风险，再看新增机会", decision_topline_html)
        self.assertIn("0.3-0.5成", decision_topline_html)
        self.assertIn('href="/today"', decision_topline_html)
        self.assertNotIn("上一步", decision_topline_html)
        self.assertNotIn("下一步", decision_topline_html)

        decision_rows_html = TEMPLATES.env.get_template("_decision_rows.html").render(
            decision_rows=[
                {
                    "title": "海尔智家 600690",
                    "action": "观察",
                    "trigger": "回踩 78.2",
                    "reason": "趋势未坏",
                    "risk": "放量跌破",
                    "freshness": "14:35",
                    "url": "/watchlist/600690",
                    "tone": "positive",
                },
                {
                    "title": "春秋航空 601021",
                    "action": "减仓",
                    "trigger": "跌破 49.8",
                    "reason": "资金承接弱",
                    "risk": "反抽失败",
                    "freshness": "14:30",
                    "url": "",
                    "tone": "risk",
                },
            ]
        )
        self.assertIn("decision-row-action", decision_rows_html)
        self.assertIn("海尔智家 600690", decision_rows_html)
        self.assertIn("回踩 78.2", decision_rows_html)
        self.assertIn("风险：放量跌破", decision_rows_html)
        self.assertIn("14:35", decision_rows_html)
        self.assertIn('href="/watchlist/600690"', decision_rows_html)
        self.assertIn("decision-row-positive", decision_rows_html)
        self.assertIn("decision-row-risk", decision_rows_html)

    def test_stage_flow_template_owns_compact_navigation_markup(self) -> None:
        stage_flow_template = (INVEST_FLOW_ROOT / "control_panel" / "templates" / "_stage_flow.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("stage-progress-strip", stage_flow_template)
        self.assertIn("上一步", stage_flow_template)
        self.assertIn("下一步", stage_flow_template)
        self.assertNotIn('{% include "_status_strip.html" %}', stage_flow_template)
        self.assertNotIn('{% include "_decision_topline.html" %}', stage_flow_template)
        self.assertNotIn('{% include "_decision_rows.html" %}', stage_flow_template)

    def test_today_next_step_link_has_focus_visible_style(self) -> None:
        css_content = (INVEST_FLOW_ROOT / "control_panel" / "static" / "control-panel.css").read_text(encoding="utf-8")
        self.assertIn(".today-next-step-link:focus-visible", css_content)

    def test_progressive_summary_has_focus_visible_style(self) -> None:
        css_content = (INVEST_FLOW_ROOT / "control_panel" / "static" / "control-panel.css").read_text(encoding="utf-8")
        base_match = re.search(r"\.progressive-summary:focus-visible\s*\{([^}]*)\}", css_content, re.DOTALL)
        self.assertIsNotNone(base_match)
        assert base_match is not None
        self.assertRegex(base_match.group(1), re.compile(r"(outline|box-shadow)"))
        self.assertIn('html[data-theme-applied="light"] .progressive-summary:focus-visible', css_content)

    def test_decision_shell_tone_css_contract_is_present(self) -> None:
        css_content = (INVEST_FLOW_ROOT / "control_panel" / "static" / "control-panel.css").read_text(encoding="utf-8")
        required_selectors = [
            ".decision-row.decision-row-positive",
            ".decision-row.decision-row-good",
            ".decision-row.decision-row-watch",
            ".decision-row.decision-row-warn",
            ".decision-row.decision-row-risk",
            ".decision-row.decision-row-neutral",
            ".status-strip-item.status-strip-item-positive",
            ".status-strip-item.status-strip-item-good",
            ".status-strip-item.status-strip-item-watch",
            ".status-strip-item.status-strip-item-warn",
            ".status-strip-item.status-strip-item-risk",
            ".status-strip-item.status-strip-item-neutral",
        ]
        for selector in required_selectors:
            with self.subTest(selector=selector):
                self.assertIn(selector, css_content)

    def test_decision_copy_readability_css_contract_is_present(self) -> None:
        css_content = (INVEST_FLOW_ROOT / "control_panel" / "static" / "control-panel.css").read_text(encoding="utf-8")
        summary_match = re.search(r"\.decision-topline-summary\s*\{([^}]*)\}", css_content, re.DOTALL)
        reason_match = re.search(r"\.decision-row-reason\s*\{([^}]*)\}", css_content, re.DOTALL)
        strip_note_match = re.search(r"\.status-strip-item-note\s*\{([^}]*)\}", css_content, re.DOTALL)
        self.assertIsNotNone(summary_match)
        self.assertIsNotNone(reason_match)
        self.assertIsNotNone(strip_note_match)
        assert summary_match is not None
        assert reason_match is not None
        assert strip_note_match is not None
        self.assertIn("max-width: 64ch", summary_match.group(1))
        self.assertIn("line-height: 1.58", summary_match.group(1))
        self.assertIn("max-width: 62ch", reason_match.group(1))
        self.assertIn("line-height: 1.58", reason_match.group(1))
        self.assertIn("display: block", strip_note_match.group(1))
        self.assertIn("max-width: 24ch", strip_note_match.group(1))

    def test_review_detail_page_exposes_window_switch(self) -> None:
        response = self.client.get(
            "/review/detail?section=ai_bucket_rows&label=AI%20shortlist%28%E9%80%9A%E8%BF%87%29"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("对比窗口", response.text)
        self.assertIn("AI 分桶", response.text)
        self.assertIn("data-preview-path=", response.text)

    def test_detail_pages_expose_productized_sections(self) -> None:
        opportunity_detail_url = self._first_opportunity_detail_url()
        cases = [
            ("/watchlist/000625", ["先看跨层状态", "盘中触发", "data-preview-path="]),
            (opportunity_detail_url, ["先看信号拆解", "执行计划", "资金承接", "data-preview-path="]),
            ("/opportunities/batch/screener", ["候选队列", "主线雷达", "data-preview-path="]),
        ]
        for path, markers in cases:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                for marker in markers:
                    self.assertIn(marker, response.text)

    def test_review_api_contains_selector_groups(self) -> None:
        response = self.client.get("/api/review")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("action_rules", payload)
        self.assertIn("change_log", payload)
        self.assertEqual(len(payload["action_rules"]), 3)
        self.assertTrue(all("action" in item and "trigger" in item for item in payload["action_rules"]))
        self.assertIn("entries", payload["change_log"])
        self.assertIn("verdict_cards", payload)
        self.assertIn("selector_groups", payload)
        self.assertIn("research_panels", payload)
        self.assertTrue(any(item.get("artifact_path") for item in payload["research_panels"]))
        self.assertGreaterEqual(len(payload["verdict_cards"]), 4)
        self.assertGreaterEqual(len(payload["selector_groups"]), 2)

    def test_review_detail_api_contains_detail_fields(self) -> None:
        response = self.client.get(
            "/api/review/detail?section=scan_gate_rows&label=%E8%BF%9B%E6%94%BB%E9%98%80%E9%97%A8%E5%8D%8A%E5%BC%80"
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("selector_groups", payload)
        self.assertIn("comparison_note", payload)
        self.assertIn("comparison_panels", payload)
        self.assertTrue(any(item.get("artifact_path") for item in payload["comparison_panels"]))
        self.assertEqual(payload["hero"]["title"], "扫描阀门 · 进攻阀门半开")

    def test_today_api_contains_action_groups(self) -> None:
        response = self.client.get("/api/today")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("action_groups", payload)
        self.assertIn("action_queue", payload)
        self.assertIn("topline", payload)
        self.assertIn("next_steps", payload)
        self.assertIn("top_rows", payload)
        self.assertIn("status_strip", payload)
        self.assertEqual(len(payload["action_groups"]), 3)
        self.assertEqual(
            [item["title"] for item in payload["action_groups"]],
            ["立即处理", "只观察", "今日回避"],
        )
        self.assertIn("items", payload["action_queue"])
        self.assertIn("counts", payload["action_queue"])
        self.assertTrue(all("decision" in item for item in payload["action_queue"]["items"]))
        self.assertIn("change_view", payload)
        self.assertIn("summary_cards", payload["change_view"])
        self.assertIn("groups", payload["change_view"])

    def test_today_api_change_view_exposes_page_and_snapshot_time_tags(self) -> None:
        response = self.client.get("/api/today")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        tags = payload.get("change_view", {}).get("meta_tags") or []
        self.assertTrue(any(tag.startswith("页面时间 ") for tag in tags))
        self.assertTrue(any(tag.startswith("回放时间 ") for tag in tags))

    def test_today_action_decision_endpoint_updates_state(self) -> None:
        backup = TODAY_ACTION_STATE_PATH.read_text(encoding="utf-8") if TODAY_ACTION_STATE_PATH.exists() else None
        try:
            response = self.client.post(
                "/api/today/actions/decision",
                json={
                    "trade_date": "2099-12-31",
                    "key": "smoke:test-action",
                    "decision": "done",
                },
            )
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["key"], "smoke:test-action")
            self.assertEqual(payload["decision"]["value"], "done")
        finally:
            if backup is None:
                TODAY_ACTION_STATE_PATH.unlink(missing_ok=True)
            else:
                TODAY_ACTION_STATE_PATH.write_text(backup, encoding="utf-8")

    def test_product_apis_contain_confidence_switch(self) -> None:
        for path in ["/api/today", "/api/watchlist", "/api/opportunities", "/api/review"]:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertIn("confidence_switch", payload)
                self.assertIn("label", payload["confidence_switch"])
                self.assertIn("tone", payload["confidence_switch"])

    def test_ask_api_returns_empty_state_without_query(self) -> None:
        response = self.client.get("/api/ask")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("examples", payload)
        self.assertIn("recent_queries", payload)
        self.assertIn("manager", payload)
        self.assertIn("suggest_api", payload["links"])
        self.assertIsNone(payload["case"])

    def test_ask_api_returns_payload_for_query(self) -> None:
        mocked = {
            "query": "600690",
            "case": {
                "hero": {
                    "title": "海尔智家 600690",
                    "decision_label": "减仓观望",
                }
            },
        }
        with patch("control_panel.app.build_ask_page_view", return_value=mocked):
            response = self.client.get("/api/ask?q=600690")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["query"], "600690")
        self.assertEqual(payload["case"]["hero"]["title"], "海尔智家 600690")

    def test_ask_suggest_api_returns_payload(self) -> None:
        mocked = [
            {
                "code": "600690",
                "name": "海尔智家",
                "tag": "自选股",
                "detail": "600690 · 自选股",
                "fill_value": "海尔智家 600690",
            }
        ]
        with patch("control_panel.app.build_ask_suggestions", return_value=mocked):
            response = self.client.get("/api/ask/suggest?q=海尔")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["query"], "海尔")
        self.assertEqual(payload["items"][0]["code"], "600690")
        self.assertIn("message", payload)

    def test_ask_suggest_api_supports_historical_name_lookup(self) -> None:
        response = self.client.get("/api/ask/suggest?q=北新")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(any(item.get("code") == "000786" for item in payload.get("items") or []))

    def test_ask_html_with_query_exposes_followup_surface(self) -> None:
        response = self.client.get("/ask?q=600690")
        self.assertEqual(response.status_code, 200)
        self.assertIn("连续追问", response.text)
        self.assertIn("data-ask-followup", response.text)
        self.assertIn("继续问", response.text)

    def test_ask_followup_api_returns_payload(self) -> None:
        mocked = {
            "query": "600690",
            "question": "为什么当前是这个结论？",
            "code": "600690",
            "name": "海尔智家",
            "answer": {
                "intent": "decision",
                "title": "为什么当前是减仓观望",
                "summary": "核心还是风险和执行边界。",
                "bullets": ["动作与仓位：减仓观望；建议仓位 0-0.5成"],
                "references": ["可信度 高"],
                "tone": "watch",
            },
        }
        with patch("control_panel.app.build_ask_followup_view", return_value=mocked):
            response = self.client.post(
                "/api/ask/followup",
                json={"q": "600690", "question": "为什么当前是这个结论？"},
            )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["query"], "600690")
        self.assertEqual(payload["answer"]["intent"], "decision")

    def test_ask_followup_api_passes_history(self) -> None:
        mocked = {
            "query": "600690",
            "question": "那今天怎么做？",
            "code": "600690",
            "name": "海尔智家",
            "answer": {
                "intent": "plan",
                "title": "今天怎么操作",
                "summary": "先按触发条件执行。",
                "bullets": ["动作：轻仓跟踪"],
                "references": ["建议仓位 0-0.5成"],
                "tone": "watch",
            },
        }
        history = [{"role": "user", "title": "继续追问", "summary": "为什么当前是这个结论？"}]
        with patch("control_panel.app.build_ask_followup_view", return_value=mocked) as builder:
            response = self.client.post(
                "/api/ask/followup",
                json={"q": "600690", "question": "那今天怎么做？", "history": history},
            )
        self.assertEqual(response.status_code, 200)
        builder.assert_called_once_with("那今天怎么做？", "600690", history)

    def test_build_ask_followup_view_marks_hybrid_engine_when_model_enhances(self) -> None:
        cached_case = {
            "code": "600690",
            "name": "海尔智家",
            "tone": "watch",
            "hero": {
                "title": "海尔智家 600690",
                "summary": "当前更适合先观察节奏。",
                "decision_label": "减仓观望",
                "position": "0-0.5成",
                "confidence_label": "高",
                "confidence_note": "已有自选股与实时链路双重证据。",
            },
            "watchlist_action": {"kind": "active", "label": "已在自选股"},
            "plan_rows": [{"label": "动作", "value": "减仓观望"}],
            "plan_levels": [{"label": "触发位", "value": "80.5"}],
            "level_cards": [{"label": "止损位", "value": "76.2", "detail": "纪律边界"}],
            "event_groups": [],
            "cross_cards": [],
            "context_tags": ["已命中自选股"],
            "metric_cards": [{"label": "规则分", "value": "77", "detail": "趋势未坏"}],
            "analysis_groups": [{"title": "风险", "metric": "回落未止", "items": ["回落未止"], "empty": "-"}],
        }
        enhancement = {
            "summary": "今天先别急着扩大仓位，优先守住节奏和失效边界。",
            "bullets": ["动作先按减仓观望执行。", "若盘中转强，再看触发位附近承接。"],
            "references": ["建议仓位 0-0.5成"],
            "followups": ["如果午后转强，需要看哪一个触发条件？"],
        }
        history = [{"role": "user", "title": "继续追问", "summary": "为什么当前是这个结论？"}]
        with patch("control_panel.dashboard_data.load_ask_case_cache", return_value=cached_case):
            with patch("control_panel.dashboard_data.ask_followup_enhancement_from_model", return_value=enhancement):
                payload = build_ask_followup_view("那今天怎么做？", "600690", history)
        self.assertEqual(payload["answer"]["engine"], "hybrid")
        self.assertEqual(payload["history_used"], 1)
        self.assertIn("模型增强", payload["answer"]["engine_label"])
        self.assertEqual(payload["answer"]["summary"], enhancement["summary"])

    def test_resolve_ask_stock_supports_full_market_search_fallback(self) -> None:
        mocked = [
            {
                "code": "600519",
                "name": "贵州茅台",
                "market": "sh",
                "sina": "sh600519",
                "source": "sina_search",
            }
        ]
        with patch("control_panel.dashboard_data.search_sina_stock_suggestions", return_value=mocked):
            result = resolve_ask_stock("贵州茅台", None, None, None)
        self.assertEqual(result["stock"]["code"], "600519")
        self.assertIn("full_market_search", result["stock"]["sources"])

    def test_watchlist_api_contains_manager(self) -> None:
        response = self.client.get("/api/watchlist")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("manager", payload)
        self.assertIn("active_items", payload["manager"])
        self.assertIn("archived_items", payload["manager"])
        self.assertIn("refresh_status", payload["manager"])
        self.assertIn("steps", payload["manager"]["refresh_status"])
        self.assertIn("add_api", payload["manager"])

    def test_watchlist_manage_endpoints_update_config(self) -> None:
        backup = WATCHLIST_CONFIG_PATH.read_text(encoding="utf-8") if WATCHLIST_CONFIG_PATH.exists() else None
        try:
            def _read_watchlist_config() -> dict[str, object]:
                return json.loads(WATCHLIST_CONFIG_PATH.read_text(encoding="utf-8"))

            def _find_target_stock(config_payload: dict[str, object], code: str) -> dict[str, object] | None:
                stocks = config_payload.get("stocks") or []
                if not isinstance(stocks, list):
                    return None
                for item in stocks:
                    if not isinstance(item, dict):
                        continue
                    if str(item.get("code") or "").strip() == code:
                        return item
                return None

            with patch("watchlist_registry.fetch_stock_name", return_value="测试股票"):
                add_response = self.client.post(
                    "/api/watchlist/manage/add",
                    json={
                        "code": "300308",
                        "trigger_refresh": False,
                    },
                )
            self.assertEqual(add_response.status_code, 200)
            add_payload = add_response.json()
            self.assertTrue(add_payload["ok"])
            self.assertIn(add_payload["operation"]["status"], {"added", "updated", "restored", "exists"})
            self.assertFalse(add_payload["refresh"]["started"])
            self.assertEqual(add_payload["operation"]["stock"]["code"], "300308")
            self.assertTrue(str(add_payload["operation"]["stock"]["name"] or "").strip())

            config_after_add = _read_watchlist_config()
            added_stock = _find_target_stock(config_after_add, "300308")
            self.assertIsNotNone(added_stock)
            assert added_stock is not None
            self.assertTrue(bool(added_stock.get("active")))

            archive_response = self.client.post(
                "/api/watchlist/manage/archive",
                json={
                    "code": "300308",
                    "trigger_refresh": False,
                },
            )
            self.assertEqual(archive_response.status_code, 200)
            archive_payload = archive_response.json()
            self.assertTrue(archive_payload["ok"])
            self.assertIn(archive_payload["operation"]["status"], {"archived", "already_archived"})
            self.assertFalse(archive_payload["refresh"]["started"])
            config_after_archive = _read_watchlist_config()
            archived_stock = _find_target_stock(config_after_archive, "300308")
            self.assertIsNotNone(archived_stock)
            assert archived_stock is not None
            self.assertFalse(bool(archived_stock.get("active")))

            restore_response = self.client.post(
                "/api/watchlist/manage/restore",
                json={
                    "code": "300308",
                    "trigger_refresh": False,
                },
            )
            self.assertEqual(restore_response.status_code, 200)
            restore_payload = restore_response.json()
            self.assertTrue(restore_payload["ok"])
            self.assertIn(restore_payload["operation"]["status"], {"restored", "already_active"})
            self.assertFalse(restore_payload["refresh"]["started"])
            config_after_restore = _read_watchlist_config()
            restored_stock = _find_target_stock(config_after_restore, "300308")
            self.assertIsNotNone(restored_stock)
            assert restored_stock is not None
            self.assertTrue(bool(restored_stock.get("active")))
        finally:
            if backup is None:
                WATCHLIST_CONFIG_PATH.unlink(missing_ok=True)
            else:
                WATCHLIST_CONFIG_PATH.write_text(backup, encoding="utf-8")

    def test_watchlist_refresh_progress_translates_stage_markers(self) -> None:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            handle.write("[2026-04-18 21:00:00] [stage] refresh:start 自选股全流程已启动\n")
            handle.write("[2026-04-18 21:00:02] [stage] watchlist:snapshot 正在抓取自选股快照\n")
            handle.write("[2026-04-18 21:00:05] [stage] watchlist:snapshot_done 自选股快照已更新\n")
            handle.write("[2026-04-18 21:00:08] [stage] watchlist:summary 正在生成自选股摘要与完整报告\n")
            log_path = handle.name

        try:
            progress = watchlist_refresh_progress(
                {
                    "task_name": "watchlist_refresh",
                    "status": "running",
                    "log_path": log_path,
                }
            )
            self.assertIn("正在生成自选股摘要与完整报告", progress["summary"])
            self.assertEqual(
                [item["state"] for item in progress["steps"]],
                ["completed", "current", "pending"],
            )
        finally:
            Path(log_path).unlink(missing_ok=True)

    def test_refresh_status_endpoint_returns_payload(self) -> None:
        response = self.client.get("/api/refresh/status?page=today")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["page"], "today")
        self.assertIn(payload["market_mode"], {"trading", "standby", "off"})
        self.assertIn("suggested_poll_seconds", payload)
        self.assertIn("freshness", payload)
        self.assertIn("recommended_task", payload)
        self.assertIn("cooldown", payload)
        self.assertIn("snapshot_signature", payload)
        self.assertIn("running", payload)

    def test_refresh_status_rejects_unknown_page(self) -> None:
        response = self.client.get("/api/refresh/status?page=unknown")
        self.assertEqual(response.status_code, 400)

    def test_refresh_trigger_starts_task(self) -> None:
        mocked = {
            "started": True,
            "run_id": "refresh_smoke_1",
            "task_name": "watchlist_refresh",
            "title": "自选股全流程刷新",
            "send_to_feishu": False,
            "meta_path": "/tmp/refresh_smoke_1.json",
            "log_path": "/tmp/refresh_smoke_1.log",
        }
        with patch("control_panel.app.launch_background_task", return_value=mocked) as launcher:
            response = self.client.post(
                "/api/refresh/trigger",
                json={"page": "watchlist", "force": True},
            )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["page"], "watchlist")
        self.assertEqual(payload["task"]["task_name"], "watchlist_refresh")
        launcher.assert_called_once()

    def test_refresh_trigger_rejects_when_related_task_is_running(self) -> None:
        running = [
            {
                "task_name": "watchlist_refresh",
                "status": "running",
                "started_at": "2026-04-20 10:00:00",
                "title": "自选股全流程刷新",
            }
        ]
        with patch("control_panel.app.list_runs", return_value=running):
            response = self.client.post(
                "/api/refresh/trigger",
                json={"page": "watchlist"},
            )
        self.assertEqual(response.status_code, 409)
        payload = response.json()
        self.assertIn("刷新任务仍在运行", payload.get("detail", ""))


if __name__ == "__main__":
    unittest.main()
