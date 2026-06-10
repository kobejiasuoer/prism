from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient


INVEST_FLOW_ROOT = Path(__file__).resolve().parents[2]
if str(INVEST_FLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(INVEST_FLOW_ROOT))

from control_panel.app import app  # noqa: E402
import control_panel.app as app_module  # noqa: E402
from control_panel.dashboard_data import (  # noqa: E402
    ask_followup_model_config,
    ask_page_url,
    batch_detail_url,
    build_ask_followup_answer,
    candidate_detail_url,
    review_detail_url,
    today_nav_links,
    watchlist_detail_url,
    watchlist_page_url,
)


decision_ledger = app_module.decision_ledger

TODAY_PAGE_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "page.tsx"
COMMAND_CENTER_WORKSPACE_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "command-center-workspace.tsx"
COMMAND_BRIEF_TRUST_FOLD_PATH = INVEST_FLOW_ROOT / "web" / "src" / "components" / "command-brief" / "trust-fold.tsx"
SETTINGS_PAGE_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "settings" / "page.tsx"
SETTINGS_WORKSPACE_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "settings" / "settings-workspace.tsx"
SETTINGS_DIAGNOSTICS_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "settings" / "settings-diagnostics.tsx"
SETTINGS_PARAMETERS_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "settings" / "settings-parameters.tsx"
SETTINGS_READINESS_DETAILS_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "settings" / "settings-readiness-details.tsx"
SETTINGS_SAFE_REFRESH_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "settings" / "settings-safe-refresh.tsx"
TODAY_ACTION_DETAILS_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "today-action-details.tsx"
DISCOVERY_PAGE_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "discovery" / "page.tsx"
DISCOVERY_WORKSPACE_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "discovery" / "discovery-workspace.tsx"
DISCOVERY_CONTEXT_PANELS_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "discovery" / "discovery-context-panels.tsx"
DISCOVERY_OBSERVATION_WORKBENCH_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "discovery" / "discovery-observation-workbench.tsx"
DISCOVERY_OBSERVATION_ACTIONS_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "discovery" / "discovery-observation-actions.tsx"
DISCOVERY_V2_DETAILS_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "discovery" / "discovery-v2-details.tsx"
DISCOVERY_V2_UTILS_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "discovery" / "discovery-v2-utils.ts"
DISCOVERY_DISPLAY_UTILS_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "discovery" / "discovery-display-utils.ts"
REVIEW_PAGE_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "review" / "page.tsx"
REVIEW_DECISION_WORKSPACE_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "review" / "review-decision-workspace.tsx"
REVIEW_HISTORY_PANELS_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "review" / "review-history-panels.tsx"
REVIEW_LEARNING_PATTERNS_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "review" / "review-learning-patterns.tsx"
REVIEW_CASE_WORKSPACE_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "review" / "review-case-workspace.tsx"
REVIEW_UTILS_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "review" / "review-utils.ts"
REVIEW_MINI_FACT_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "review" / "review-mini-fact.tsx"
PORTFOLIO_PAGE_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "portfolio" / "page.tsx"
PORTFOLIO_WORKSPACE_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "portfolio" / "portfolio-workspace.tsx"
PORTFOLIO_ACCOUNT_OVERVIEW_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "portfolio" / "portfolio-account-overview.tsx"
PORTFOLIO_RESEARCH_UNIVERSE_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "portfolio" / "portfolio-research-universe.tsx"
PORTFOLIO_LATEST_DECISIONS_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "portfolio" / "portfolio-latest-decisions.tsx"
PORTFOLIO_HOLDING_WORKBENCH_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "portfolio" / "portfolio-holding-workbench.tsx"
PORTFOLIO_LEDGER_TOOLS_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "portfolio" / "portfolio-ledger-tools.tsx"
PORTFOLIO_MANUAL_WRITE_TOOLS_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "portfolio" / "portfolio-manual-write-tools.tsx"
PORTFOLIO_DECISION_WRITEBACK_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "portfolio" / "portfolio-decision-writeback.tsx"
PORTFOLIO_UTILS_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "portfolio" / "portfolio-utils.ts"
PORTFOLIO_FORM_UTILS_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "portfolio" / "portfolio-form-utils.tsx"
STOCK_PAGE_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "stock" / "[code]" / "page.tsx"
STOCK_PROFILE_WORKSPACE_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "stock" / "[code]" / "stock-profile-workspace.tsx"
STOCK_DECISION_WORKSPACE_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "stock" / "[code]" / "stock-decision-workspace.tsx"
STOCK_DECISION_SUPPORT_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "stock" / "[code]" / "stock-decision-support.tsx"
STOCK_FORMAL_PANELS_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "stock" / "[code]" / "stock-formal-panels.tsx"
STOCK_DECISION_TIMELINE_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "stock" / "[code]" / "stock-decision-timeline.tsx"
STOCK_LEARNING_PANELS_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "stock" / "[code]" / "stock-learning-panels.tsx"
STOCK_ASK_WORKSPACE_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "stock" / "[code]" / "stock-ask-workspace.tsx"
STOCK_SECONDARY_TABS_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "stock" / "[code]" / "stock-secondary-tabs.tsx"
STOCK_WATCHLIST_ACTIONS_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "stock" / "[code]" / "stock-watchlist-actions.tsx"
STOCK_DISPLAY_UTILS_PATH = INVEST_FLOW_ROOT / "web" / "src" / "app" / "stock" / "[code]" / "stock-display-utils.ts"
WEB_API_PATH = INVEST_FLOW_ROOT / "web" / "src" / "lib" / "api.ts"
WEB_HOOKS_PATH = INVEST_FLOW_ROOT / "web" / "src" / "lib" / "hooks.ts"
WEB_TYPES_PATH = INVEST_FLOW_ROOT / "web" / "src" / "lib" / "types.ts"
WEB_TASK_UTILS_PATH = INVEST_FLOW_ROOT / "web" / "src" / "lib" / "task-utils.ts"
WEB_TEXT_UTILS_PATH = INVEST_FLOW_ROOT / "web" / "src" / "lib" / "text-utils.ts"
WEB_RISK_UTILS_PATH = INVEST_FLOW_ROOT / "web" / "src" / "lib" / "risk-utils.ts"
WEB_UTILS_PATH = INVEST_FLOW_ROOT / "web" / "src" / "lib" / "utils.ts"
WEB_READINESS_COPY_PATH = INVEST_FLOW_ROOT / "web" / "src" / "lib" / "readiness-copy.ts"
WEB_COMPONENTS_PATH = INVEST_FLOW_ROOT / "web" / "src" / "components"
WEB_THEME_OPTIONS_PATH = WEB_COMPONENTS_PATH / "theme-options.ts"
EVIDENCE_PANEL_PATH = WEB_COMPONENTS_PATH / "evidence-panel.tsx"
WEB_APP_SHELL_PATH = WEB_COMPONENTS_PATH / "app-shell.tsx"
WEB_DEFERRED_TRUST_BANNER_PATH = WEB_COMPONENTS_PATH / "deferred-trust-banner.tsx"
WEB_GLOBALS_PATH = INVEST_FLOW_ROOT / "web" / "src" / "styles" / "globals.css"
APPS_COMPAT_PACKAGE_PATH = INVEST_FLOW_ROOT / "control_panel"


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
            "/api/overview": ("generated_at", "tasks", "freshness", "workspace_root"),
            "/api/shell/status": ("ok", "generated_at", "readiness", "watchlist_source"),
            "/api/today/summary": ("generated_at", "readiness", "command_brief", "links_lazy"),
            "/api/today/actions": ("generated_at", "action_queue", "decision_contracts_deferred"),
            "/api/today/command-brief-detail": ("generated_at", "command_brief_detail"),
            "/api/watchlist": ("display_date", "groups", "manager_deferred", "source_cards"),
            "/api/watchlist/manage": ("manager",),
            "/api/opportunities": ("display_date", "groups", "readiness", "compact", "context_deferred", "evidence_deferred"),
            "/api/review": ("compact", "freshness_summary", "research_panels_deferred"),
            "/api/review/evidence": ("source_cards", "artifacts"),
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

    def test_underscore_control_panel_import_uses_current_formal_data_sections(self) -> None:
        script = f"""
import json
import sys
from pathlib import Path

apps_dir = Path({str(INVEST_FLOW_ROOT)!r})
repo_root = apps_dir.parent
sys.path[:] = [str(apps_dir), str(repo_root), str(repo_root / "packages")] + [
    item for item in sys.path if item and item not in {{str(apps_dir), str(repo_root)}}
]

import control_panel.app as app_module
from fastapi.testclient import TestClient

client = TestClient(app_module.app)
profile = client.get("/api/stock/600690/formal-data/profile")
risk = client.get("/api/stock/600690/formal-data/risk")
profile.raise_for_status()
risk.raise_for_status()
print(json.dumps({{
    "module_file": str(Path(app_module.__file__).as_posix()),
    "profile": profile.json().get("formal_data") or {{}},
    "risk": risk.json().get("formal_data") or {{}},
}}, ensure_ascii=False))
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=INVEST_FLOW_ROOT.parent,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        payload = json.loads(result.stdout)
        self.assertTrue(payload["module_file"].endswith("apps/control_panel/app.py"))
        self.assertEqual(payload["profile"]["section"], "profile")
        self.assertEqual(payload["risk"]["section"], "risk")
        self.assertTrue(payload["risk"]["factor_profile_deferred"])
        self.assertNotIn("factor_profile", payload["risk"])

    def test_underscore_control_panel_compat_has_no_dead_static_template_links(self) -> None:
        self.assertFalse((APPS_COMPAT_PACKAGE_PATH / "static").is_symlink())
        self.assertFalse((APPS_COMPAT_PACKAGE_PATH / "templates").is_symlink())

    def test_opportunities_api_cache_honors_fresh_bypass(self) -> None:
        route = next(
            route
            for route in app.routes
            if getattr(route, "path", "") == "/api/opportunities" and "GET" in getattr(route, "methods", set())
        )
        endpoint_globals = route.endpoint.__globals__
        original_compact_cache = dict(endpoint_globals["_OPPORTUNITIES_COMPACT_API_CACHE"])
        original_context_cache = endpoint_globals["_OPPORTUNITIES_CONTEXT_API_CACHE"]
        original_source_cards_cache = endpoint_globals["_OPPORTUNITIES_SOURCE_CARDS_API_CACHE"]
        original_ttl = endpoint_globals["OPPORTUNITIES_API_CACHE_TTL_SECONDS"]
        endpoint_globals["_OPPORTUNITIES_COMPACT_API_CACHE"].clear()
        endpoint_globals["_OPPORTUNITIES_CONTEXT_API_CACHE"] = None
        endpoint_globals["_OPPORTUNITIES_SOURCE_CARDS_API_CACHE"] = None
        endpoint_globals["OPPORTUNITIES_API_CACHE_TTL_SECONDS"] = 30
        build_view = Mock(
            side_effect=[
                {"generated_at": "first", "display_date": "d", "groups": [], "source_cards": []},
                {"generated_at": "fresh", "display_date": "d", "groups": [], "source_cards": []},
            ]
        )
        try:
            with patch.dict(endpoint_globals, {"build_opportunities_view": build_view}):
                first = self.client.get("/api/opportunities")
                cached = self.client.get("/api/opportunities")
                fresh = self.client.get("/api/opportunities?fresh=1")
        finally:
            endpoint_globals["_OPPORTUNITIES_COMPACT_API_CACHE"].clear()
            endpoint_globals["_OPPORTUNITIES_COMPACT_API_CACHE"].update(original_compact_cache)
            endpoint_globals["_OPPORTUNITIES_CONTEXT_API_CACHE"] = original_context_cache
            endpoint_globals["_OPPORTUNITIES_SOURCE_CARDS_API_CACHE"] = original_source_cards_cache
            endpoint_globals["OPPORTUNITIES_API_CACHE_TTL_SECONDS"] = original_ttl

        self.assertEqual(first.status_code, 200)
        self.assertEqual(cached.status_code, 200)
        self.assertEqual(fresh.status_code, 200)
        self.assertEqual(first.json()["generated_at"], "first")
        self.assertEqual(cached.json()["generated_at"], "first")
        self.assertEqual(fresh.json()["generated_at"], "fresh")
        self.assertEqual(build_view.call_count, 2)
        self.assertEqual(
            [call.kwargs for call in build_view.call_args_list],
            [
                {"hydrate_all_groups": False, "active_group_key": None, "include_context": False, "include_lifecycle": False},
                {"hydrate_all_groups": False, "active_group_key": None, "include_context": False, "include_lifecycle": False},
            ],
        )

    def test_opportunities_api_defaults_to_single_loaded_group(self) -> None:
        route = next(
            route
            for route in app.routes
            if getattr(route, "path", "") == "/api/opportunities" and "GET" in getattr(route, "methods", set())
        )
        endpoint_globals = route.endpoint.__globals__
        original_compact_cache = dict(endpoint_globals["_OPPORTUNITIES_COMPACT_API_CACHE"])
        original_ttl = endpoint_globals["OPPORTUNITIES_API_CACHE_TTL_SECONDS"]
        endpoint_globals["_OPPORTUNITIES_COMPACT_API_CACHE"].clear()
        endpoint_globals["OPPORTUNITIES_API_CACHE_TTL_SECONDS"] = 30
        payload = {
            "generated_at": "now",
            "display_date": "d",
            "groups": [
                {"key": "empty", "title": "空阶段", "count": 0, "cards": []},
                {
                    "key": "watching",
                    "title": "继续观察",
                    "count": 5,
                    "cards": [{"code": str(index)} for index in range(5)],
                },
                {
                    "key": "upgrade",
                    "title": "结构验证",
                    "count": 4,
                    "cards": [{"code": f"u{index}"} for index in range(4)],
                },
            ],
            "learning_memories": [{"key": str(index), "summary": "m"} for index in range(5)],
            "theme_cards": [{"title": str(index), "leaders": list("ABCDEFG")} for index in range(7)],
            "lifecycle_cards": [{"label": str(index), "value": index} for index in range(5)],
            "lifecycle_groups": [
                {
                    "key": f"life-{index}",
                    "title": f"延续 {index}",
                    "count": 5,
                    "cards": [{"code": f"{index}-{card_index}"} for card_index in range(5)],
                }
                for index in range(6)
            ],
            "source_cards": [{"label": "早盘批次", "value": "now"}],
        }
        build_view = Mock(return_value=payload)
        context_view = Mock(
            return_value={
                "generated_at": "context",
                "display_date": "d",
                "trade_date": "d",
                "source_cards": [{"label": "context-source", "value": "ready"}],
                "learning_memories": [{"key": str(index), "summary": "m"} for index in range(5)],
                "theme_cards": [{"title": str(index), "leaders": list("ABCDEFG")} for index in range(7)],
                "lifecycle_cards": [{"label": str(index), "value": index} for index in range(5)],
                "lifecycle_groups": [
                    {
                        "key": f"life-{index}",
                        "title": f"延续 {index}",
                        "count": 5,
                        "cards": [{"code": f"{index}-{card_index}"} for card_index in range(5)],
                    }
                    for index in range(6)
                ],
            }
        )

        try:
            with patch.dict(
                endpoint_globals,
                {
                    "build_opportunities_view": build_view,
                    "build_opportunities_context_view": context_view,
                },
            ):
                default = self.client.get("/api/opportunities")
                selected = self.client.get("/api/opportunities?group=upgrade")
                context = self.client.get("/api/opportunities/context")
                legacy_full = self.client.get("/api/opportunities?compact=0")
        finally:
            endpoint_globals["_OPPORTUNITIES_COMPACT_API_CACHE"].clear()
            endpoint_globals["_OPPORTUNITIES_COMPACT_API_CACHE"].update(original_compact_cache)
            endpoint_globals["OPPORTUNITIES_API_CACHE_TTL_SECONDS"] = original_ttl

        self.assertEqual(default.status_code, 200)
        self.assertEqual(selected.status_code, 200)
        self.assertEqual(context.status_code, 200)
        self.assertEqual(legacy_full.status_code, 200)

        default_payload = default.json()
        self.assertTrue(default_payload["compact"])
        self.assertTrue(default_payload["context_deferred"])
        self.assertTrue(default_payload["evidence_deferred"])
        self.assertEqual(default_payload["active_group_key"], "watching")
        default_groups = {group["key"]: group for group in default_payload["groups"]}
        self.assertEqual(len(default_groups["watching"]["cards"]), 3)
        self.assertEqual(default_groups["watching"]["cards_preview_limit"], 3)
        self.assertEqual(default_groups["watching"]["cards_loaded"], False)
        self.assertEqual(default_groups["watching"]["deferred_cards"], True)
        self.assertEqual(default_groups["upgrade"]["cards"], [])
        self.assertEqual(default_groups["upgrade"]["deferred_cards"], True)
        self.assertNotIn("learning_memories", default_payload)
        self.assertNotIn("theme_cards", default_payload)
        self.assertNotIn("lifecycle_cards", default_payload)
        self.assertNotIn("lifecycle_groups", default_payload)
        self.assertNotIn("source_cards", default_payload)
        if "readiness" in default_payload:
            self.assertIn("trust_level", default_payload["readiness"])
            self.assertNotIn("source_freshness", default_payload["readiness"])
            self.assertNotIn("account_state", default_payload["readiness"])

        selected_payload = selected.json()
        self.assertTrue(selected_payload["context_deferred"])
        self.assertTrue(selected_payload["evidence_deferred"])
        self.assertEqual(selected_payload["active_group_key"], "upgrade")
        selected_groups = {group["key"]: group for group in selected_payload["groups"]}
        self.assertEqual(selected_groups["watching"]["cards"], [])
        self.assertEqual(len(selected_groups["upgrade"]["cards"]), 4)
        self.assertEqual(selected_groups["upgrade"]["cards_loaded"], True)
        self.assertEqual(selected_groups["upgrade"]["deferred_cards"], False)
        self.assertNotIn("source_cards", selected_payload)

        context_payload = context.json()
        self.assertEqual(context_payload["source_cards"], [{"label": "context-source", "value": "ready"}])
        self.assertEqual(len(context_payload["learning_memories"]), 3)
        self.assertEqual(len(context_payload["theme_cards"]), 5)
        self.assertEqual(len(context_payload["theme_cards"][0]["leaders"]), 6)
        self.assertEqual(len(context_payload["lifecycle_cards"]), 3)
        self.assertEqual(len(context_payload["lifecycle_groups"]), 4)
        self.assertEqual(len(context_payload["lifecycle_groups"][0]["cards"]), 3)

        legacy_full_payload = legacy_full.json()
        self.assertTrue(legacy_full_payload["compact"])
        self.assertTrue(legacy_full_payload["context_deferred"])
        self.assertTrue(legacy_full_payload["evidence_deferred"])
        self.assertNotIn("source_cards", legacy_full_payload)
        self.assertNotIn("learning_memories", legacy_full_payload)
        self.assertNotIn("theme_cards", legacy_full_payload)
        self.assertEqual([len(group["cards"]) for group in legacy_full_payload["groups"]], [0, 3, 0])
        self.assertEqual(
            [call.kwargs for call in build_view.call_args_list],
            [
                {"hydrate_all_groups": False, "active_group_key": None, "include_context": False, "include_lifecycle": False},
                {"hydrate_all_groups": False, "active_group_key": "upgrade", "include_context": False, "include_lifecycle": False},
            ],
        )
        self.assertEqual(context_view.call_count, 1)

    def test_opportunities_context_api_uses_sidebar_context_builder(self) -> None:
        route = next(
            route
            for route in app.routes
            if getattr(route, "path", "") == "/api/opportunities/context" and "GET" in getattr(route, "methods", set())
        )
        endpoint_globals = route.endpoint.__globals__
        original_context_cache = endpoint_globals["_OPPORTUNITIES_CONTEXT_API_CACHE"]
        original_source_cards_cache = endpoint_globals["_OPPORTUNITIES_SOURCE_CARDS_API_CACHE"]
        original_ttl = endpoint_globals["OPPORTUNITIES_API_CACHE_TTL_SECONDS"]
        endpoint_globals["_OPPORTUNITIES_CONTEXT_API_CACHE"] = None
        endpoint_globals["_OPPORTUNITIES_SOURCE_CARDS_API_CACHE"] = None
        endpoint_globals["OPPORTUNITIES_API_CACHE_TTL_SECONDS"] = 30
        context_view = Mock(
            side_effect=[
                {
                    "generated_at": "context",
                    "display_date": "d",
                    "trade_date": "d",
                    "source_cards": [{"label": "context-source", "value": "ready"}],
                    "learning_memories": [{"key": "m1"}],
                    "theme_cards": [{"title": "theme", "leaders": ["A"]}],
                    "lifecycle_cards": [{"label": "追踪变动", "value": "1"}],
                    "lifecycle_groups": [{"key": "life", "count": 1, "cards": [{"code": "600690"}]}],
                },
                {
                    "generated_at": "context-fresh",
                    "display_date": "d",
                    "trade_date": "d",
                    "source_cards": [{"label": "fresh-source", "value": "ready"}],
                    "learning_memories": [{"key": "m2"}],
                    "theme_cards": [{"title": "theme", "leaders": ["B"]}],
                    "lifecycle_cards": [{"label": "追踪变动", "value": "2"}],
                    "lifecycle_groups": [{"key": "life", "count": 1, "cards": [{"code": "600519"}]}],
                },
            ]
        )
        full_view = Mock(side_effect=AssertionError("context must not build full opportunities view"))
        try:
            with patch.dict(
                endpoint_globals,
                {
                    "build_opportunities_context_view": context_view,
                    "build_opportunities_view": full_view,
                },
            ):
                response = self.client.get("/api/opportunities/context")
                cached = self.client.get("/api/opportunities/context")
                fresh = self.client.get("/api/opportunities/context?fresh=1")
        finally:
            endpoint_globals["_OPPORTUNITIES_CONTEXT_API_CACHE"] = original_context_cache
            endpoint_globals["_OPPORTUNITIES_SOURCE_CARDS_API_CACHE"] = original_source_cards_cache
            endpoint_globals["OPPORTUNITIES_API_CACHE_TTL_SECONDS"] = original_ttl

        self.assertEqual(response.status_code, 200)
        self.assertEqual(cached.status_code, 200)
        self.assertEqual(fresh.status_code, 200)
        body = response.json()
        self.assertEqual(body["generated_at"], "context")
        self.assertEqual(body["source_cards"], [{"label": "context-source", "value": "ready"}])
        self.assertEqual(body["learning_memories"], [{"key": "m1"}])
        self.assertEqual(cached.json()["generated_at"], "context")
        self.assertEqual(cached.json()["source_cards"], [{"label": "context-source", "value": "ready"}])
        self.assertEqual(fresh.json()["generated_at"], "context-fresh")
        self.assertEqual(fresh.json()["source_cards"], [{"label": "fresh-source", "value": "ready"}])
        self.assertEqual(context_view.call_count, 2)
        self.assertEqual(full_view.call_count, 0)

    def test_opportunities_source_cards_api_uses_lightweight_builder(self) -> None:
        route = next(
            route
            for route in app.routes
            if getattr(route, "path", "") == "/api/opportunities/source-cards"
            and "GET" in getattr(route, "methods", set())
        )
        endpoint_globals = route.endpoint.__globals__
        original_compact_cache = dict(endpoint_globals["_OPPORTUNITIES_COMPACT_API_CACHE"])
        original_context_cache = endpoint_globals["_OPPORTUNITIES_CONTEXT_API_CACHE"]
        original_source_cards_cache = endpoint_globals["_OPPORTUNITIES_SOURCE_CARDS_API_CACHE"]
        original_ttl = endpoint_globals["OPPORTUNITIES_API_CACHE_TTL_SECONDS"]
        endpoint_globals["_OPPORTUNITIES_COMPACT_API_CACHE"].clear()
        endpoint_globals["_OPPORTUNITIES_CONTEXT_API_CACHE"] = None
        endpoint_globals["_OPPORTUNITIES_SOURCE_CARDS_API_CACHE"] = None
        endpoint_globals["OPPORTUNITIES_API_CACHE_TTL_SECONDS"] = 30
        source_view = Mock(
            side_effect=[
                {
                    "generated_at": "source",
                    "trade_date": "d",
                    "expected_trade_date": "d",
                    "data_trade_date": "d",
                    "readiness_mode": "live",
                    "source_cards": [{"label": "source-only", "value": "ready"}],
                    "learning_memories": [{"key": "should-not-leak"}],
                },
                {
                    "generated_at": "source-fresh",
                    "trade_date": "d",
                    "source_cards": [{"label": "fresh-source", "value": "ready"}],
                    "theme_cards": [{"title": "should-not-leak"}],
                },
            ]
        )
        full_view = Mock(side_effect=AssertionError("source cards must not build full opportunities view"))
        context_view = Mock(side_effect=AssertionError("source cards must not build sidebar context"))
        try:
            with patch.dict(
                endpoint_globals,
                {
                    "build_opportunities_source_cards_view": source_view,
                    "build_opportunities_view": full_view,
                    "build_opportunities_context_view": context_view,
                },
            ):
                response = self.client.get("/api/opportunities/source-cards")
                cached = self.client.get("/api/opportunities/source-cards")
                fresh = self.client.get("/api/opportunities/source-cards?fresh=1")
        finally:
            endpoint_globals["_OPPORTUNITIES_COMPACT_API_CACHE"].clear()
            endpoint_globals["_OPPORTUNITIES_COMPACT_API_CACHE"].update(original_compact_cache)
            endpoint_globals["_OPPORTUNITIES_CONTEXT_API_CACHE"] = original_context_cache
            endpoint_globals["_OPPORTUNITIES_SOURCE_CARDS_API_CACHE"] = original_source_cards_cache
            endpoint_globals["OPPORTUNITIES_API_CACHE_TTL_SECONDS"] = original_ttl

        self.assertEqual(response.status_code, 200)
        self.assertEqual(cached.status_code, 200)
        self.assertEqual(fresh.status_code, 200)
        body = response.json()
        self.assertEqual(body["generated_at"], "source")
        self.assertEqual(body["source_cards"], [{"label": "source-only", "value": "ready"}])
        self.assertEqual(body["readiness_mode"], "live")
        self.assertNotIn("learning_memories", body)
        self.assertNotIn("theme_cards", body)
        self.assertEqual(cached.json()["generated_at"], "source")
        self.assertEqual(fresh.json()["generated_at"], "source-fresh")
        self.assertEqual(fresh.json()["source_cards"], [{"label": "fresh-source", "value": "ready"}])
        self.assertEqual(source_view.call_count, 2)
        self.assertEqual(full_view.call_count, 0)
        self.assertEqual(context_view.call_count, 0)

    def test_review_api_defers_research_panels_by_default(self) -> None:
        default = self.client.get("/api/review")
        research = self.client.get("/api/review/research")

        self.assertEqual(default.status_code, 200)
        self.assertEqual(research.status_code, 200)

        default_payload = default.json()
        self.assertTrue(default_payload["compact"])
        self.assertTrue(default_payload["research_panels_deferred"])
        self.assertNotIn("research_panels", default_payload)
        self.assertNotIn("source_cards", default_payload)
        self.assertNotIn("artifacts", default_payload)

        research_payload = research.json()
        self.assertEqual(research_payload["research_panels_deferred"], False)
        self.assertGreaterEqual(len(research_payload.get("research_panels") or []), 1)
        self.assertNotIn("compact", research_payload)
        self.assertNotIn("source_cards", research_payload)
        self.assertNotIn("comparison_cards", research_payload)
        for panel in research_payload.get("research_panels") or []:
            self.assertNotIn("metric_cards", panel)
            self.assertNotIn("groups", panel)
            self.assertNotIn("artifact_path", panel)

    def test_review_research_api_uses_research_slice_builder(self) -> None:
        route = next(
            route
            for route in app.routes
            if getattr(route, "path", "") == "/api/review/research" and "GET" in getattr(route, "methods", set())
        )
        endpoint_globals = route.endpoint.__globals__
        research_view = Mock(
            return_value={
                "generated_at": "research",
                "active_baseline_id": "base",
                "active_window_id": "window",
                "research_panels": [{"title": "panel"}],
                "research_panels_deferred": False,
                "source_cards": [{"label": "should-not-leak"}],
                "comparison_cards": [{"label": "should-not-leak"}],
            }
        )
        full_view = Mock(side_effect=AssertionError("research slice must not build full review view"))

        with patch.dict(
            endpoint_globals,
            {
                "build_review_research_view": research_view,
                "build_review_view": full_view,
            },
        ):
            response = self.client.get("/api/review/research?baseline=base&window=window")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["generated_at"], "research")
        self.assertEqual(body["research_panels"], [{"title": "panel"}])
        self.assertEqual(body["active_baseline_id"], "base")
        self.assertEqual(body["active_window_id"], "window")
        self.assertFalse(body["research_panels_deferred"])
        self.assertNotIn("source_cards", body)
        self.assertNotIn("comparison_cards", body)
        self.assertEqual(
            research_view.call_args.kwargs,
            {"baseline_id": "base", "window_id": "window"},
        )
        self.assertEqual(full_view.call_count, 0)

    def test_review_evidence_api_uses_evidence_slice_builder(self) -> None:
        route = next(
            route
            for route in app.routes
            if getattr(route, "path", "") == "/api/review/evidence" and "GET" in getattr(route, "methods", set())
        )
        endpoint_globals = route.endpoint.__globals__
        evidence_view = Mock(
            return_value={
                "generated_at": "evidence",
                "active_baseline_id": "base",
                "active_window_id": "window",
                "source_cards": [{"label": "source-only"}],
                "artifacts": [{"title": "artifact-only"}],
                "comparison_cards": [{"label": "should-not-leak"}],
                "research_panels": [{"title": "should-not-leak"}],
            }
        )
        full_view = Mock(side_effect=AssertionError("evidence slice must not build full review view"))

        with patch.dict(
            endpoint_globals,
            {
                "build_review_evidence_view": evidence_view,
                "build_review_view": full_view,
            },
        ):
            response = self.client.get("/api/review/evidence?baseline=base&window=window")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["generated_at"], "evidence")
        self.assertEqual(body["source_cards"], [{"label": "source-only"}])
        self.assertEqual(body["artifacts"], [{"title": "artifact-only"}])
        self.assertEqual(body["active_baseline_id"], "base")
        self.assertEqual(body["active_window_id"], "window")
        self.assertNotIn("comparison_cards", body)
        self.assertNotIn("research_panels", body)
        self.assertEqual(
            evidence_view.call_args.kwargs,
            {"baseline_id": "base", "window_id": "window"},
        )
        self.assertEqual(full_view.call_count, 0)

    def test_review_api_defaults_to_compact_payload(self) -> None:
        compact = self.client.get("/api/review")
        legacy_full = self.client.get("/api/review?compact=0")

        self.assertEqual(compact.status_code, 200)
        self.assertEqual(legacy_full.status_code, 200)

        compact_payload = compact.json()
        self.assertTrue(compact_payload["compact"])
        self.assertNotIn("source_cards", compact_payload)
        self.assertNotIn("artifacts", compact_payload)
        self.assertNotIn("shadow_replay", compact_payload)
        for heavy_key in (
            "selector_groups",
            "hero",
            "topline",
            "summary_cards",
            "verdict_cards",
            "reading_compass",
            "action_rules",
            "change_log",
            "confidence_switch",
            "lifecycle_groups",
            "links",
        ):
            self.assertNotIn(heavy_key, compact_payload)

        legacy_full_payload = legacy_full.json()
        self.assertTrue(legacy_full_payload["compact"])
        self.assertNotIn("selector_groups", legacy_full_payload)
        self.assertNotIn("source_cards", legacy_full_payload)
        self.assertNotIn("artifacts", legacy_full_payload)
        self.assertNotIn("shadow_replay", legacy_full_payload)

    def test_review_shadow_replay_api_is_available_on_demand(self) -> None:
        response = self.client.get("/api/review/shadow-replay")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("status", payload)
        self.assertIn("cards", payload)

    def test_overview_api_cache_honors_fresh_bypass(self) -> None:
        route = next(
            route
            for route in app.routes
            if getattr(route, "path", "") == "/api/overview" and "GET" in getattr(route, "methods", set())
        )
        endpoint_globals = route.endpoint.__globals__
        original_cache = endpoint_globals["_OVERVIEW_API_CACHE"]
        original_ttl = endpoint_globals["OVERVIEW_API_CACHE_TTL_SECONDS"]
        endpoint_globals["_OVERVIEW_API_CACHE"] = None
        endpoint_globals["OVERVIEW_API_CACHE_TTL_SECONDS"] = 30
        build_view = Mock(
            side_effect=[
                {"generated_at": "overview-compact", "tasks": [], "freshness": [], "workspace_root": "/tmp/prism", "compact": True},
                {"generated_at": "overview-full", "tasks": [], "freshness": [], "workspace_root": "/tmp/prism", "compact": False},
                {"generated_at": "overview-fresh", "tasks": [], "freshness": [], "workspace_root": "/tmp/prism", "compact": True},
            ]
        )
        try:
            with patch.dict(endpoint_globals, {"build_overview_summary": build_view, "clear_run_list_cache": Mock()}):
                first = self.client.get("/api/overview")
                cached = self.client.get("/api/overview")
                full = self.client.get("/api/overview?compact=0")
                fresh = self.client.get("/api/overview?fresh=1")
        finally:
            endpoint_globals["_OVERVIEW_API_CACHE"] = original_cache
            endpoint_globals["OVERVIEW_API_CACHE_TTL_SECONDS"] = original_ttl

        self.assertEqual(first.status_code, 200)
        self.assertEqual(cached.status_code, 200)
        self.assertEqual(full.status_code, 200)
        self.assertEqual(fresh.status_code, 200)
        self.assertEqual(first.json()["generated_at"], "overview-compact")
        self.assertEqual(cached.json()["generated_at"], "overview-compact")
        self.assertEqual(full.json()["generated_at"], "overview-full")
        self.assertEqual(fresh.json()["generated_at"], "overview-fresh")
        self.assertEqual([call.kwargs for call in build_view.call_args_list], [{"compact": True}, {"compact": False}, {"compact": True}])

    def test_overview_api_defers_full_task_descriptions(self) -> None:
        compact = self.client.get("/api/overview?fresh=1")
        full = self.client.get("/api/overview?fresh=1&compact=0")

        self.assertEqual(compact.status_code, 200)
        self.assertEqual(full.status_code, 200)
        compact_payload = compact.json()
        full_payload = full.json()
        self.assertTrue(compact_payload.get("compact"))
        self.assertFalse(full_payload.get("compact"))
        self.assertTrue(compact_payload.get("tasks"))
        self.assertTrue(full_payload.get("tasks"))
        for task in compact_payload["tasks"]:
            with self.subTest(task=task.get("task_name")):
                self.assertIn("task_name", task)
                self.assertIn("title", task)
                self.assertIn("lane", task)
                self.assertNotIn("description", task)
        self.assertTrue(any("description" in task for task in full_payload["tasks"]))

    def test_runs_api_forwards_fresh_bypass(self) -> None:
        route = next(
            route
            for route in app.routes
            if getattr(route, "path", "") == "/api/runs" and "GET" in getattr(route, "methods", set())
        )
        endpoint_globals = route.endpoint.__globals__
        list_runs_mock = Mock(side_effect=[[{"run_id": "cached"}], [{"run_id": "fresh"}]])
        with patch.dict(endpoint_globals, {"list_runs": list_runs_mock}):
            cached = self.client.get("/api/runs")
            fresh = self.client.get("/api/runs?fresh=1")

        self.assertEqual(cached.json()["runs"][0]["run_id"], "cached")
        self.assertEqual(fresh.json()["runs"][0]["run_id"], "fresh")
        list_runs_mock.assert_any_call(fresh=False)
        list_runs_mock.assert_any_call(fresh=True)

    def test_runs_api_defaults_to_compact_list(self) -> None:
        route = next(
            route
            for route in app.routes
            if getattr(route, "path", "") == "/api/runs" and "GET" in getattr(route, "methods", set())
        )
        endpoint_globals = route.endpoint.__globals__
        run = {
            "run_id": "run-1",
            "task_name": "refresh",
            "title": "刷新",
            "status": "completed",
            "started_at": "2026-06-01T09:30:00",
            "summary": "完成。",
            "log_path": "/tmp/run.log",
            "meta_path": "/tmp/run.json",
            "command": ["python", "heavy.py"],
            "cwd": "/Users/example/project",
            "shell_env_sanitized": True,
        }
        with patch.dict(endpoint_globals, {"list_runs": Mock(return_value=[run])}):
            compact = self.client.get("/api/runs")
            legacy_full = self.client.get("/api/runs?compact=0")

        self.assertTrue(compact.json()["compact"])
        compact_run = compact.json()["runs"][0]
        self.assertEqual(compact_run["run_id"], "run-1")
        self.assertIn("log_path", compact_run)
        self.assertIn("meta_path", compact_run)
        self.assertNotIn("command", compact_run)
        self.assertNotIn("cwd", compact_run)
        self.assertNotIn("shell_env_sanitized", compact_run)

        self.assertTrue(legacy_full.json()["compact"])
        legacy_full_run = legacy_full.json()["runs"][0]
        self.assertNotIn("command", legacy_full_run)
        self.assertNotIn("cwd", legacy_full_run)
        self.assertNotIn("shell_env_sanitized", legacy_full_run)

    def test_data_assets_status_defaults_to_compact_payload(self) -> None:
        route = next(
            route
            for route in app.routes
            if getattr(route, "path", "") == "/api/data-assets/status" and "GET" in getattr(route, "methods", set())
        )
        endpoint_globals = route.endpoint.__globals__

        def build_status(expected_trade_date: str, *, fresh: bool = False, compact: bool = False) -> dict[str, object]:
            return {
                "generated_at": "test",
                "expected_trade_date": expected_trade_date,
                "fresh": fresh,
                "compact": compact,
                "summary": {},
                "datasets": [],
                "harvest_runs": [],
                "visible_usage": [],
            }

        build_status_mock = Mock(side_effect=build_status)
        with patch.dict(
            endpoint_globals,
            {
                "build_data_assets_status": build_status_mock,
                "readiness_expected_trade_date": Mock(return_value="2026-05-29"),
            },
        ):
            default = self.client.get("/api/data-assets/status")
            full = self.client.get("/api/data-assets/status?compact=0&fresh=1")

        self.assertEqual(default.status_code, 200)
        self.assertEqual(full.status_code, 200)
        self.assertTrue(default.json()["compact"])
        self.assertFalse(full.json()["compact"])
        self.assertTrue(full.json()["fresh"])
        build_status_mock.assert_any_call("2026-05-29", fresh=False, compact=True)
        build_status_mock.assert_any_call("2026-05-29", fresh=True, compact=False)

    def test_today_summary_readiness_uses_compact_payload(self) -> None:
        response = self.client.get("/api/today/summary")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        readiness = payload.get("readiness") or {}

        self.assertTrue(payload["readiness_details_deferred"])
        self.assertIn("trust_level", readiness)
        self.assertIn("formal_data_status", readiness)
        self.assertIn("account_state", readiness)
        self.assertNotIn("blockers", readiness)
        self.assertNotIn("warnings", readiness)
        self.assertNotIn("formal_blockers", readiness)
        self.assertNotIn("source_freshness", readiness)
        self.assertNotIn("dataset_freshness", readiness)
        self.assertNotIn("formal_freshness", readiness)
        self.assertNotIn("quality_freshness", readiness)
        self.assertNotIn("capabilities", readiness)
        self.assertNotIn("datasets", readiness["formal_data_status"])
        self.assertNotIn("source_plan", readiness["formal_data_status"])
        provider = readiness["formal_data_status"].get("provider") or {}
        self.assertNotIn("token_env_names", provider)
        self.assertNotIn("configured_token_env_names", provider)
        for blocker in readiness["formal_data_status"].get("blockers") or []:
            self.assertNotIn("source_apis", blocker)
            self.assertNotIn("required_permission", blocker)
            self.assertNotIn("docs", blocker)

    def test_today_summary_command_brief_uses_homepage_projection(self) -> None:
        response = self.client.get("/api/today/summary?fresh=1")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        command_brief = payload.get("command_brief") or {}
        if not command_brief:
            self.skipTest("current fixture has no command brief")

        self.assertTrue(command_brief.get("details_deferred"))
        self.assertEqual(
            command_brief.get("links_lazy", {}).get("details"),
            "/api/today/command-brief-detail",
        )
        self.assertEqual(
            payload.get("links_lazy", {}).get("command_brief_detail"),
            "/api/today/command-brief-detail",
        )
        for deferred_key in ("forbid_today", "reclassify_when", "judgement_chain", "midday_verify"):
            self.assertNotIn(deferred_key, command_brief)

        forbidden_item_keys = {
            "suggested_action",
            "suggested_action_label",
            "confidence",
            "thesis",
            "why_now",
            "missing_confirmation",
            "hard_gate_max_action",
            "hard_gate_block_reason",
            "decision_summary",
            "judge_source",
            "ai_status",
            "ai_status_label",
            "ai_summary",
        }
        for lane in command_brief.get("action_lanes") or []:
            self.assertLessEqual(
                len(lane.get("items") or []),
                1,
                "homepage action lanes should expose only one representative item; full queue is lazy",
            )
            for item in lane.get("items") or []:
                if "action_type" in item:
                    for key in ("key", "action_type", "reason", "trigger", "invalidate_when", "tone"):
                        self.assertIn(key, item)
                    self.assertLessEqual(len(str(item.get("reason") or "")), 99)
                    self.assertLessEqual(len(str(item.get("trigger") or "")), 75)
                    self.assertLessEqual(len(str(item.get("invalidate_when") or "")), 75)
                else:
                    for key in ("title", "reason", "tone", "source"):
                        self.assertIn(key, item)
                for key in forbidden_item_keys:
                    self.assertNotIn(key, item)
            self.assertIn("total_count", lane)
            self.assertGreaterEqual(lane["total_count"], len(lane.get("items") or []))

        for permit in (command_brief.get("permits") or {}).values():
            self.assertLessEqual(len(str(permit.get("why") or "")), 99)

        detail_response = self.client.get("/api/today/command-brief-detail?fresh=1")
        self.assertEqual(detail_response.status_code, 200)
        detail = detail_response.json().get("command_brief_detail") or {}
        for detail_key in ("forbid_today", "reclassify_when", "judgement_chain", "midday_verify"):
            self.assertIn(detail_key, detail)

    def test_today_summary_and_actions_api_cache_honor_fresh_bypass(self) -> None:
        summary_route = next(
            route
            for route in app.routes
            if getattr(route, "path", "") == "/api/today/summary" and "GET" in getattr(route, "methods", set())
        )
        actions_route = next(
            route
            for route in app.routes
            if getattr(route, "path", "") == "/api/today/actions" and "GET" in getattr(route, "methods", set())
        )
        endpoint_globals = summary_route.endpoint.__globals__
        original_summary_cache = endpoint_globals["_TODAY_SUMMARY_API_CACHE"]
        original_actions_cache = endpoint_globals["_TODAY_ACTIONS_API_CACHE"]
        original_contracts_cache = endpoint_globals["_TODAY_ACTION_CONTRACTS_API_CACHE"]
        original_detail_cache = endpoint_globals["_TODAY_COMMAND_BRIEF_DETAIL_API_CACHE"]
        original_summary_ttl = endpoint_globals["TODAY_SUMMARY_API_CACHE_TTL_SECONDS"]
        original_actions_ttl = endpoint_globals["TODAY_ACTIONS_API_CACHE_TTL_SECONDS"]
        endpoint_globals["_TODAY_SUMMARY_API_CACHE"] = None
        endpoint_globals["_TODAY_ACTIONS_API_CACHE"] = None
        endpoint_globals["_TODAY_ACTION_CONTRACTS_API_CACHE"] = None
        endpoint_globals["_TODAY_COMMAND_BRIEF_DETAIL_API_CACHE"] = None
        endpoint_globals["TODAY_SUMMARY_API_CACHE_TTL_SECONDS"] = 20
        endpoint_globals["TODAY_ACTIONS_API_CACHE_TTL_SECONDS"] = 20
        summary_build = Mock(
            side_effect=[
                {"generated_at": "summary-first", "display_date": "d", "readiness": {"trust_level": {"label": "x"}}},
                {"generated_at": "summary-fresh", "display_date": "d", "readiness": {"trust_level": {"label": "x"}}},
            ]
        )
        formal_status = Mock(return_value={"ready": True, "provider": {}})
        actions_build = Mock(
            side_effect=[
                {"generated_at": "actions-first", "action_queue": {}, "decision_contracts_deferred": True},
                {"generated_at": "actions-fresh", "action_queue": {}, "decision_contracts_deferred": True},
            ]
        )
        contracts_build = Mock(
            side_effect=[
                {"generated_at": "contracts-first", "decision_contracts": {}},
                {"generated_at": "contracts-after-actions-fresh", "decision_contracts": {}},
                {"generated_at": "contracts-fresh", "decision_contracts": {}},
            ]
        )
        detail_build = Mock(
            side_effect=[
                {"generated_at": "detail-first", "command_brief_detail": {}},
                {"generated_at": "detail-fresh", "command_brief_detail": {}},
            ]
        )
        clear_base_inputs_cache = Mock()
        try:
            with patch.dict(
                endpoint_globals,
                {
                    "build_today_summary_view": summary_build,
                    "build_formal_data_status_payload": formal_status,
                    "build_today_actions_view": actions_build,
                    "build_today_action_contracts_view": contracts_build,
                    "build_today_command_brief_detail_view": detail_build,
                    "clear_today_base_inputs_cache": clear_base_inputs_cache,
                },
            ):
                summary_first = self.client.get("/api/today/summary")
                summary_cached = self.client.get("/api/today/summary")
                summary_fresh = self.client.get("/api/today/summary?fresh=1")
                actions_first = self.client.get("/api/today/actions")
                actions_cached = self.client.get("/api/today/actions")
                contracts_first = self.client.get("/api/today/action-contracts")
                contracts_cached = self.client.get("/api/today/action-contracts")
                detail_first = self.client.get("/api/today/command-brief-detail")
                detail_cached = self.client.get("/api/today/command-brief-detail")
                detail_fresh = self.client.get("/api/today/command-brief-detail?fresh=1")
                actions_fresh = self.client.get("/api/today/actions?fresh=1")
                contracts_after_actions_fresh = self.client.get("/api/today/action-contracts")
                contracts_fresh = self.client.get("/api/today/action-contracts?fresh=1")
        finally:
            endpoint_globals["_TODAY_SUMMARY_API_CACHE"] = original_summary_cache
            endpoint_globals["_TODAY_ACTIONS_API_CACHE"] = original_actions_cache
            endpoint_globals["_TODAY_ACTION_CONTRACTS_API_CACHE"] = original_contracts_cache
            endpoint_globals["_TODAY_COMMAND_BRIEF_DETAIL_API_CACHE"] = original_detail_cache
            endpoint_globals["TODAY_SUMMARY_API_CACHE_TTL_SECONDS"] = original_summary_ttl
            endpoint_globals["TODAY_ACTIONS_API_CACHE_TTL_SECONDS"] = original_actions_ttl

        self.assertEqual(summary_first.json()["generated_at"], "summary-first")
        self.assertEqual(summary_cached.json()["generated_at"], "summary-first")
        self.assertEqual(summary_fresh.json()["generated_at"], "summary-fresh")
        self.assertEqual(summary_build.call_count, 2)
        self.assertEqual(actions_first.json()["generated_at"], "actions-first")
        self.assertEqual(actions_cached.json()["generated_at"], "actions-first")
        self.assertEqual(actions_fresh.json()["generated_at"], "actions-fresh")
        self.assertEqual(actions_build.call_count, 2)
        self.assertEqual(contracts_first.json()["generated_at"], "contracts-first")
        self.assertEqual(contracts_cached.json()["generated_at"], "contracts-first")
        self.assertEqual(contracts_after_actions_fresh.json()["generated_at"], "contracts-after-actions-fresh")
        self.assertEqual(contracts_fresh.json()["generated_at"], "contracts-fresh")
        self.assertEqual(contracts_build.call_count, 3)
        self.assertEqual(detail_first.json()["generated_at"], "detail-first")
        self.assertEqual(detail_cached.json()["generated_at"], "detail-first")
        self.assertEqual(detail_fresh.json()["generated_at"], "detail-fresh")
        self.assertEqual(detail_build.call_count, 2)
        self.assertEqual(clear_base_inputs_cache.call_count, 4)

    def test_today_action_decision_writeback_uses_lightweight_actions_view(self) -> None:
        route = next(
            route
            for route in app.routes
            if getattr(route, "path", "") == "/api/today/actions/decision"
            and "POST" in getattr(route, "methods", set())
        )
        endpoint_globals = route.endpoint.__globals__
        update_decision = Mock()
        actions_build = Mock(
            return_value={
                "generated_at": "actions-lite",
                "action_queue": {
                    "items": [],
                    "stale_items": [
                        {
                            "key": "watchlist:600690",
                            "decision": {
                                "value": "done",
                                "label": "已完成",
                                "tone": "positive",
                                "updated_at": "2026-05-15 10:30:00",
                            },
                        }
                    ],
                    "counts": {"total": 1, "stale": 1},
                },
            }
        )
        full_build = Mock(side_effect=AssertionError("writeback must not build full today view"))

        with patch.dict(
            endpoint_globals,
            {
                "update_today_action_decision": update_decision,
                "build_today_actions_view": actions_build,
                "build_today_view": full_build,
                "clear_stock_profile_cache": Mock(),
                "_clear_portfolio_related_api_caches": Mock(),
            },
        ):
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
        self.assertEqual(body.get("decision", {}).get("label"), "已完成")
        self.assertEqual(body.get("counts"), {"total": 1, "stale": 1})
        self.assertEqual(body.get("ledger", {}).get("reason"), "ineligible")
        update_decision.assert_called_once_with("2026-05-15", "watchlist:600690", "done")
        self.assertEqual(actions_build.call_count, 1)
        self.assertEqual(full_build.call_count, 0)

    def test_deprecated_today_api_route_stays_removed(self) -> None:
        route_paths = {
            getattr(route, "path", "")
            for route in app.routes
            if "GET" in getattr(route, "methods", set())
        }
        schema_paths = (self.client.get("/openapi.json").json().get("paths") or {}).keys()

        self.assertNotIn("/api/today", route_paths)
        self.assertNotIn("/api/today", schema_paths)
        self.assertEqual(self.client.get("/api/today").status_code, 404)
        for preferred_path in (
            "/api/today/summary",
            "/api/today/actions",
            "/api/today/action-contracts",
            "/api/today/command-brief-detail",
        ):
            with self.subTest(path=preferred_path):
                self.assertIn(preferred_path, route_paths)

    def test_control_panel_prewarm_builds_readonly_caches(self) -> None:
        build_refresh_status = Mock(return_value={})
        route = next(
            route
            for route in app.routes
            if getattr(route, "path", "") == "/api/refresh/status" and "GET" in getattr(route, "methods", set())
        )
        endpoint_globals = route.endpoint.__globals__

        with patch.dict(
            endpoint_globals,
            {
                "build_refresh_status_payload": build_refresh_status,
                "trigger_refresh_task": Mock(side_effect=AssertionError("prewarm must not start tasks")),
                "launch_background_task": Mock(side_effect=AssertionError("prewarm must not start tasks")),
            },
        ):
            endpoint_globals["_prewarm_control_panel_caches"]()

        build_refresh_status.assert_called_once_with("today", auto=False, skip_auto=True, compact=True)

    def test_today_summary_actions_and_portfolio_share_base_inputs_cache(self) -> None:
        from control_panel import dashboard_data

        dashboard_data.clear_today_base_inputs_cache()
        original_ttl = dashboard_data.TODAY_BASE_INPUTS_CACHE_TTL_SECONDS
        readiness = {
            "expected_trade_date": "2026-05-29",
            "data_trade_date": "2026-05-29",
            "display_date": "2026-05-29",
            "checked_at": "2026-05-29 10:00:00",
            "session": "morning",
            "readiness_mode": "live_ready",
            "ready": True,
            "brief_is_live": True,
            "stale_count": 0,
            "formal_ready": True,
            "formal_base_ready": True,
            "pipeline_formal_ready": True,
            "recommended_tasks": [],
            "trust_level": {"level": "live", "label": "Live"},
            "capabilities": {
                "review": {"granted": True},
                "approve": {"granted": True},
                "trade": {"granted": True},
                "ledger_capture": {"granted": True},
            },
            "source_freshness": [
                {"key": "watchlist", "available": True, "stale": False, "age_label": "刚刚"},
                {"key": "screening", "available": True, "stale": False, "age_label": "刚刚"},
                {"key": "confirmation", "available": True, "stale": False, "age_label": "刚刚"},
                {"key": "decision_brief", "available": True, "stale": False, "age_label": "刚刚"},
            ],
            "quality_freshness": [
                {"key": "watchlist", "timely": True, "age_label": "刚刚"},
                {"key": "aggressive", "timely": True, "age_label": "刚刚"},
                {"key": "midday_confirmation", "timely": True, "age_label": "刚刚"},
            ],
            "account_state": {"mode": "paper", "mode_label": "模拟盘"},
            "blockers": [],
            "warnings": [],
            "formal_blockers": [],
        }

        def fake_canonical_load(loader, **_kwargs):
            name = getattr(loader, "__name__", "")
            if name == "load_decision_brief":
                return {
                    "trade_date": "2026-05-29",
                    "generated_at": "2026-05-29 09:45:00",
                    "summary": {"gate_summary": "测试总控", "main_theme": "测试主线"},
                    "focus": {},
                    "paths": {},
                }
            if name == "load_watchlist_snapshot":
                return {
                    "trade_date": "2026-05-29",
                    "generated_at": "2026-05-29 09:30:00",
                    "stocks": [],
                    "priority_codes": [],
                    "observe_codes": [],
                    "stock_count": 0,
                }
            if name == "load_screening_batch":
                return {
                    "generated_at": "2026-05-29 09:35:00",
                    "candidates": [],
                    "candidate_count": 0,
                    "screening_summary": {},
                    "market_regime": {
                        "execution_gate": {
                            "allow_new_positions": False,
                            "label": "测试阀门",
                            "summary": "先观察",
                            "position_cap": "0成",
                        }
                    },
                }
            if name == "load_confirmation":
                return {
                    "generated_at": "2026-05-29 11:45:00",
                    "validation_status": "ok",
                    "counts": {},
                    "confirmed": [],
                    "fresh_candidates": [],
                    "downgraded": [],
                }
            if name == "load_quality_status":
                return {"lanes": {}}
            return None

        dashboard_data.TODAY_BASE_INPUTS_CACHE_TTL_SECONDS = 30
        compute_readiness = Mock(return_value=readiness)
        try:
            with patch.object(dashboard_data, "expected_trade_date", return_value="2026-05-29"), patch.object(
                dashboard_data,
                "safe_canonical_load",
                side_effect=fake_canonical_load,
            ), patch.object(
                dashboard_data,
                "load_account_book",
                return_value={"updated_at": "account-v1", "fills": []},
            ), patch.object(
                dashboard_data,
                "load_today_action_decision_store",
                return_value={"updated_at": "actions-v1", "trade_dates": {}},
            ), patch.object(
                dashboard_data,
                "get_today_action_decision_map",
                return_value={},
            ), patch.object(
                dashboard_data,
                "build_dataset_freshness_rows",
                return_value=[],
            ), patch.object(
                dashboard_data,
                "build_formal_freshness_rows",
                return_value=[],
            ), patch.object(
                dashboard_data,
                "compute_readiness",
                compute_readiness,
            ):
                summary = dashboard_data.build_today_summary_view()
                actions = dashboard_data.build_today_actions_view()
                portfolio = dashboard_data.build_portfolio_account_view(
                    formal_data_status={"ready": True, "provider": {"name": "tushare"}},
                    include_holding_reviews=False,
                )

            self.assertEqual(summary["readiness"]["readiness_mode"], "live_ready")
            self.assertEqual(actions["readiness_mode"], "live_ready")
            self.assertEqual(portfolio["readiness"]["readiness_mode"], "live_ready")
            self.assertTrue(portfolio.get("holding_reviews_deferred"))
            self.assertEqual(compute_readiness.call_count, 1)
        finally:
            dashboard_data.TODAY_BASE_INPUTS_CACHE_TTL_SECONDS = original_ttl
            dashboard_data.clear_today_base_inputs_cache()

    def test_today_and_stock_profile_slices_share_base_inputs_cache(self) -> None:
        from control_panel import dashboard_data

        dashboard_data.clear_today_base_inputs_cache()
        dashboard_data.clear_stock_profile_cache()
        original_today_ttl = dashboard_data.TODAY_BASE_INPUTS_CACHE_TTL_SECONDS
        original_stock_ttl = dashboard_data.STOCK_PROFILE_CACHE_TTL_SECONDS
        original_stock_base_ttl = dashboard_data.STOCK_PROFILE_BASE_CONTEXT_CACHE_TTL_SECONDS
        readiness = {
            "expected_trade_date": "2026-05-29",
            "data_trade_date": "2026-05-29",
            "display_date": "2026-05-29",
            "checked_at": "2026-05-29 10:00:00",
            "session": "morning",
            "readiness_mode": "live_ready",
            "ready": True,
            "brief_is_live": True,
            "stale_count": 0,
            "formal_ready": True,
            "formal_base_ready": True,
            "pipeline_formal_ready": True,
            "recommended_tasks": [],
            "trust_level": {"level": "live", "label": "Live"},
            "source_freshness": [],
            "quality_freshness": [],
            "account_state": {"mode": "paper", "mode_label": "模拟盘"},
            "blockers": [],
            "warnings": [],
            "formal_blockers": [],
        }
        action_groups = [
            {
                "key": "do-now",
                "title": "持仓先处理",
                "items": [
                    {
                        "key": "watchlist:600519",
                        "code": "600519",
                        "name": "贵州茅台",
                        "title": "贵州茅台",
                        "source": "watchlist",
                        "status": "复核",
                        "tone": "watch",
                        "detail": "测试动作",
                        "url": "/stock/600519",
                    }
                ],
            }
        ]

        def fake_canonical_load(loader, **_kwargs):
            name = getattr(loader, "__name__", "")
            if name == "load_decision_brief":
                return {
                    "trade_date": "2026-05-29",
                    "generated_at": "2026-05-29 09:45:00",
                    "summary": {"gate_summary": "测试总控", "main_theme": "测试主线"},
                    "paths": {},
                }
            if name == "load_watchlist_snapshot":
                return {
                    "trade_date": "2026-05-29",
                    "generated_at": "2026-05-29 09:30:00",
                    "stocks": [{"code": "600519", "name": "贵州茅台"}],
                    "priority_codes": ["600519"],
                    "observe_codes": [],
                    "stock_count": 1,
                }
            if name == "load_screening_batch":
                return {
                    "trade_date": "2026-05-29",
                    "generated_at": "2026-05-29 09:35:00",
                    "candidates": [],
                    "candidate_count": 0,
                    "screening_summary": {},
                    "market_regime": {"execution_gate": {"allow_new_positions": False, "label": "测试阀门"}},
                }
            if name == "load_confirmation":
                return {"trade_date": "2026-05-29", "generated_at": "2026-05-29 11:45:00"}
            if name == "load_quality_status":
                return {"lanes": {}}
            return None

        compute_readiness = Mock(return_value=readiness)
        command_brief = Mock(return_value={"trade_date": "2026-05-29", "trust": "live"})
        build_action_groups = Mock(return_value=action_groups)
        build_catalog = Mock(return_value={"600519": {"code": "600519", "name": "贵州茅台"}})
        load_recent = Mock(return_value={"items": []})
        load_ask_case = Mock(return_value={})
        try:
            dashboard_data.TODAY_BASE_INPUTS_CACHE_TTL_SECONDS = 30
            dashboard_data.STOCK_PROFILE_CACHE_TTL_SECONDS = 0
            dashboard_data.STOCK_PROFILE_BASE_CONTEXT_CACHE_TTL_SECONDS = 30
            with patch.object(dashboard_data, "expected_trade_date", return_value="2026-05-29"), patch.object(
                dashboard_data,
                "safe_canonical_load",
                side_effect=fake_canonical_load,
            ), patch.object(
                dashboard_data,
                "load_account_book",
                return_value={"updated_at": "account-v1", "fills": [], "no_fill_intents": []},
            ), patch.object(
                dashboard_data,
                "load_today_action_decision_store",
                return_value={
                    "updated_at": "actions-v1",
                    "trade_dates": {
                        "2026-05-29": {
                            "watchlist:600519": {
                                "decision": "watch",
                                "updated_at": "2026-05-29 10:05:00",
                            }
                        }
                    },
                },
            ), patch.object(
                dashboard_data,
                "build_dataset_freshness_rows",
                return_value=[],
            ), patch.object(
                dashboard_data,
                "build_formal_freshness_rows",
                return_value=[],
            ), patch.object(
                dashboard_data,
                "compute_readiness",
                compute_readiness,
            ), patch.object(
                dashboard_data,
                "build_today_action_groups",
                build_action_groups,
            ), patch.object(
                dashboard_data,
                "build_today_command_brief",
                command_brief,
            ), patch.object(
                dashboard_data,
                "build_stock_catalog",
                build_catalog,
            ), patch.object(
                dashboard_data,
                "load_ask_recent_store",
                load_recent,
            ), patch.object(
                dashboard_data,
                "load_ask_case_cache",
                load_ask_case,
            ), patch.object(
                dashboard_data,
                "build_watchlist_detail_view",
                return_value={
                    "code": "600519",
                    "name": "贵州茅台",
                    "trade_date": "2026-05-29",
                    "canonical_decision": {"main_conclusion": "测试结论"},
                    "decision_cards": [],
                    "level_cards": [],
                    "plan_rows": [],
                    "plan_levels": [],
                    "triggers": [],
                    "insight_groups": [],
                    "source_cards": [],
                    "artifacts": [],
                },
            ), patch.object(
                dashboard_data,
                "build_candidate_detail_view",
                side_effect=KeyError("no candidate"),
            ), patch.object(
                dashboard_data,
                "build_today_action_queue",
                wraps=dashboard_data.build_today_action_queue,
            ) as build_action_queue, patch.object(
                dashboard_data,
                "build_stock_formal_data_summary",
                return_value={"available": True, "summary_only": True, "source_cards": []},
            ) as build_formal_summary:
                summary = dashboard_data.build_today_summary_view()
                today_action = dashboard_data.build_stock_profile_today_action_view("600519", trade_date="2026-05-29")
                formal_summary = dashboard_data.build_stock_profile_formal_data_section_view(
                    "600519",
                    "summary",
                    trade_date="2026-05-29",
                )
                stock_summary = dashboard_data.build_stock_profile_summary_view("600519", trade_date="2026-05-29")

                self.assertEqual(build_catalog.call_count, 0)
                self.assertEqual(load_recent.call_count, 0)
                self.assertEqual(load_ask_case.call_count, 0)

                stock_detail = dashboard_data.build_stock_profile_detail_view("600519", trade_date="2026-05-29")

                self.assertEqual(build_catalog.call_count, 0)
                self.assertEqual(load_recent.call_count, 0)
                self.assertEqual(load_ask_case.call_count, 0)

            self.assertEqual(summary["readiness"]["readiness_mode"], "live_ready")
            self.assertTrue(formal_summary["formal_data"]["summary_only"])
            self.assertEqual(stock_summary["readiness"]["readiness_mode"], "live_ready")
            self.assertEqual(stock_detail["readiness"]["readiness_mode"], "live_ready")
            self.assertEqual((today_action["today_action"] or {})["display_state"]["value"], "watch")
            self.assertEqual(compute_readiness.call_count, 1)
            self.assertEqual(build_action_queue.call_count, 1)
            self.assertEqual(build_formal_summary.call_count, 1)
            self.assertEqual(build_catalog.call_count, 0)
            self.assertEqual(load_recent.call_count, 0)
            self.assertEqual(load_ask_case.call_count, 0)
            self.assertEqual(dashboard_data.stock_profile_cache_stats()["base_context"]["items"], 1)
        finally:
            dashboard_data.TODAY_BASE_INPUTS_CACHE_TTL_SECONDS = original_today_ttl
            dashboard_data.STOCK_PROFILE_CACHE_TTL_SECONDS = original_stock_ttl
            dashboard_data.STOCK_PROFILE_BASE_CONTEXT_CACHE_TTL_SECONDS = original_stock_base_ttl
            dashboard_data.clear_today_base_inputs_cache()
            dashboard_data.clear_stock_profile_cache()

    def test_stock_profile_cache_can_clear_account_sensitive_sections_only(self) -> None:
        from control_panel import dashboard_data

        dashboard_data.clear_stock_profile_cache()
        original_stock_ttl = dashboard_data.STOCK_PROFILE_CACHE_TTL_SECONDS
        original_stock_base_ttl = dashboard_data.STOCK_PROFILE_BASE_CONTEXT_CACHE_TTL_SECONDS
        try:
            dashboard_data.STOCK_PROFILE_CACHE_TTL_SECONDS = 120
            dashboard_data.STOCK_PROFILE_BASE_CONTEXT_CACHE_TTL_SECONDS = 120
            now = 1.0
            stock_cache = dashboard_data.__dict__["_STOCK_PROFILE_CACHE"]
            base_cache = dashboard_data.__dict__["_STOCK_PROFILE_BASE_CONTEXT_CACHE"]
            stock_cache[("summary", "600690", "2026-05-29")] = (now, {"section": "summary"})
            stock_cache[("today-action", "600690", "2026-05-29")] = (now, {"section": "today-action"})
            stock_cache[("formal-data:summary", "600690", "2026-05-29")] = (now, {"section": "formal-summary"})
            stock_cache[("learning-scorecard", "600690", "2026-05-29")] = (now, {"section": "learning"})
            base_cache[("600690", "2026-05-29")] = (now, {"base": True})

            dashboard_data.clear_stock_profile_cache(
                "sh600690",
                sections=("summary", "today-action"),
            )

            self.assertNotIn(("summary", "600690", "2026-05-29"), stock_cache)
            self.assertNotIn(("today-action", "600690", "2026-05-29"), stock_cache)
            self.assertIn(("formal-data:summary", "600690", "2026-05-29"), stock_cache)
            self.assertIn(("learning-scorecard", "600690", "2026-05-29"), stock_cache)
            self.assertNotIn(("600690", "2026-05-29"), base_cache)
        finally:
            dashboard_data.STOCK_PROFILE_CACHE_TTL_SECONDS = original_stock_ttl
            dashboard_data.STOCK_PROFILE_BASE_CONTEXT_CACHE_TTL_SECONDS = original_stock_base_ttl
            dashboard_data.clear_stock_profile_cache()

    def test_stock_profile_split_views_share_source_detail_cache(self) -> None:
        from control_panel import dashboard_data

        dashboard_data.clear_stock_profile_cache()
        original_stock_ttl = dashboard_data.STOCK_PROFILE_CACHE_TTL_SECONDS
        original_stock_base_ttl = dashboard_data.STOCK_PROFILE_BASE_CONTEXT_CACHE_TTL_SECONDS
        watchlist_detail = {
            "generated_at": "2026-05-29 09:45:00",
            "trade_date": "2026-05-29",
            "code": "600690",
            "name": "海尔智家",
            "hero": {"title": "海尔智家 600690", "summary": "测试摘要"},
            "canonical_decision": {"main_conclusion": "测试结论"},
            "decision_cards": [],
            "execution_loop": [],
            "meta_cards": [{"label": "仓位建议", "value": "观察"}],
            "triggers": [{"label": "触发", "condition": "测试触发"}],
            "source_cards": [{"label": "自选股快照", "value": "ready"}],
            "artifacts": [{"label": "自选股快照 JSON", "path": "snapshot.json"}],
        }
        try:
            dashboard_data.STOCK_PROFILE_CACHE_TTL_SECONDS = 120
            dashboard_data.STOCK_PROFILE_BASE_CONTEXT_CACHE_TTL_SECONDS = 120
            with patch.object(
                dashboard_data,
                "_stock_profile_base_context",
                return_value={
                    "generated_at": "2026-05-29 09:45:00",
                    "readiness": {
                        "expected_trade_date": "2026-05-29",
                        "data_trade_date": "2026-05-29",
                        "readiness_mode": "live_ready",
                        "ready": True,
                    },
                },
            ), patch.object(
                dashboard_data,
                "build_watchlist_detail_view",
                return_value=watchlist_detail,
            ) as build_watchlist_detail, patch.object(
                dashboard_data,
                "build_candidate_detail_view",
                side_effect=KeyError("no candidate"),
            ) as build_candidate_detail:
                detail = dashboard_data.build_stock_profile_detail_view("600690", trade_date="2026-05-29")
                secondary = dashboard_data.build_stock_profile_secondary_view("600690", trade_date="2026-05-29")
                evidence = dashboard_data.build_stock_profile_evidence_view("600690", trade_date="2026-05-29")

            self.assertEqual(detail["primary_detail"]["code"], "600690")
            self.assertIn("secondary_detail", secondary)
            self.assertEqual(secondary["secondary_detail"]["meta_cards"], watchlist_detail["meta_cards"])
            self.assertEqual(evidence["artifacts"], watchlist_detail["artifacts"])
            self.assertEqual(build_watchlist_detail.call_count, 1)
            self.assertEqual(build_candidate_detail.call_count, 1)
            self.assertIn(
                ("source-details", "600690", "2026-05-29"),
                dashboard_data.__dict__["_STOCK_PROFILE_CACHE"],
            )
            self.assertNotIn(
                ("source-details:learning", "600690", "2026-05-29"),
                dashboard_data.__dict__["_STOCK_PROFILE_CACHE"],
            )
        finally:
            dashboard_data.STOCK_PROFILE_CACHE_TTL_SECONDS = original_stock_ttl
            dashboard_data.STOCK_PROFILE_BASE_CONTEXT_CACHE_TTL_SECONDS = original_stock_base_ttl
            dashboard_data.clear_stock_profile_cache()

    def test_stock_profile_api_fresh_clears_stock_cache_before_build(self) -> None:
        with patch("control_panel.app.clear_stock_profile_cache") as clear_cache, patch(
            "control_panel.app.build_stock_profile_summary_view",
            return_value={"code": "600690", "links": {}},
        ) as build_summary:
            response = self.client.get("/api/stock/600690/summary?fresh=1")

        self.assertEqual(response.status_code, 200)
        clear_cache.assert_called_once_with("600690")
        build_summary.assert_called_once_with("600690", trade_date=None)

    def test_stock_profile_identity_fallback_is_only_used_when_primary_name_missing(self) -> None:
        from control_panel import dashboard_data

        dashboard_data.clear_today_base_inputs_cache()
        dashboard_data.clear_stock_profile_cache()
        original_today_ttl = dashboard_data.TODAY_BASE_INPUTS_CACHE_TTL_SECONDS
        original_stock_ttl = dashboard_data.STOCK_PROFILE_CACHE_TTL_SECONDS
        original_stock_base_ttl = dashboard_data.STOCK_PROFILE_BASE_CONTEXT_CACHE_TTL_SECONDS
        readiness = {
            "expected_trade_date": "2026-05-29",
            "data_trade_date": "2026-05-29",
            "readiness_mode": "live_ready",
            "ready": True,
            "brief_is_live": True,
            "stale_count": 0,
            "recommended_tasks": [],
            "trust_level": {"level": "live", "label": "Live"},
            "source_freshness": [],
            "quality_freshness": [],
            "account_state": {"mode": "paper", "mode_label": "模拟盘"},
            "blockers": [],
            "warnings": [],
            "formal_blockers": [],
        }

        def fake_canonical_load(loader, **_kwargs):
            name = getattr(loader, "__name__", "")
            if name == "load_decision_brief":
                return {"trade_date": "2026-05-29", "generated_at": "2026-05-29 09:45:00", "paths": {}}
            if name == "load_watchlist_snapshot":
                return {"trade_date": "2026-05-29", "stocks": []}
            if name == "load_screening_batch":
                return {"trade_date": "2026-05-29", "candidates": [], "market_regime": {"execution_gate": {}}}
            if name == "load_confirmation":
                return {"trade_date": "2026-05-29"}
            if name == "load_quality_status":
                return {"lanes": {}}
            return None

        try:
            dashboard_data.TODAY_BASE_INPUTS_CACHE_TTL_SECONDS = 30
            dashboard_data.STOCK_PROFILE_CACHE_TTL_SECONDS = 0
            dashboard_data.STOCK_PROFILE_BASE_CONTEXT_CACHE_TTL_SECONDS = 30
            with patch.object(dashboard_data, "expected_trade_date", return_value="2026-05-29"), patch.object(
                dashboard_data,
                "safe_canonical_load",
                side_effect=fake_canonical_load,
            ), patch.object(
                dashboard_data,
                "load_account_book",
                return_value={"updated_at": "account-v1", "fills": [], "no_fill_intents": []},
            ), patch.object(
                dashboard_data,
                "load_today_action_decision_store",
                return_value={"updated_at": "actions-v1", "trade_dates": {}},
            ), patch.object(
                dashboard_data,
                "build_dataset_freshness_rows",
                return_value=[],
            ), patch.object(
                dashboard_data,
                "build_formal_freshness_rows",
                return_value=[],
            ), patch.object(
                dashboard_data,
                "compute_readiness",
                return_value=readiness,
            ), patch.object(
                dashboard_data,
                "build_stock_catalog",
                return_value={"600519": {"code": "600519", "name": "贵州茅台"}},
            ) as build_catalog, patch.object(
                dashboard_data,
                "load_ask_recent_store",
                return_value={"items": [{"code": "600519", "name": "最近名称"}]},
            ) as load_recent, patch.object(
                dashboard_data,
                "load_ask_case_cache",
                return_value={"code": "600519", "name": "Ask 名称"},
            ) as load_ask_case:
                stock_summary = dashboard_data.build_stock_profile_summary_view("600519", trade_date="2026-05-29")

            self.assertEqual(stock_summary["name"], "贵州茅台")
            self.assertEqual(build_catalog.call_count, 1)
            self.assertEqual(load_recent.call_count, 1)
            self.assertEqual(load_ask_case.call_count, 1)
        finally:
            dashboard_data.TODAY_BASE_INPUTS_CACHE_TTL_SECONDS = original_today_ttl
            dashboard_data.STOCK_PROFILE_CACHE_TTL_SECONDS = original_stock_ttl
            dashboard_data.STOCK_PROFILE_BASE_CONTEXT_CACHE_TTL_SECONDS = original_stock_base_ttl
            dashboard_data.clear_today_base_inputs_cache()
            dashboard_data.clear_stock_profile_cache()

    def test_today_actions_decision_contracts_are_compact_for_homepage(self) -> None:
        response = self.client.get("/api/today/actions?fresh=1")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body.get("decision_contracts_deferred"))
        self.assertNotIn("decision_contracts", body)
        items = [
            *((body.get("action_queue") or {}).get("items") or []),
            *((body.get("action_queue") or {}).get("stale_items") or []),
        ]
        if items:
            forbidden_item_keys = {
                "allowed_for_real_money",
                "decision_contract",
                "execution_constraints",
                "factor_snapshot",
                "factor_explanation",
                "tushare_score_breakdown",
                "opportunity_v2",
                "ai_summary",
                "ai_delta",
                "risk_source_cards",
                "risk_evidence_refs",
                "v2_calibration_threshold_adjustments",
                "v2_playbook_adjustment",
            }
            for item in items:
                self.assertIn("key", item)
                self.assertIn("title", item)
                self.assertIn("decision", item)
                for key in forbidden_item_keys:
                    self.assertNotIn(key, item)

        contracts_response = self.client.get("/api/today/action-contracts?fresh=1")
        self.assertEqual(contracts_response.status_code, 200)
        contracts_body = contracts_response.json()
        self.assertNotIn("action_queue", contracts_body)
        contracts = ((contracts_body.get("decision_contracts") or {}).get("by_action_key") or {})
        if not contracts:
            self.skipTest("current action queue has no decision contracts")

        for contract in contracts.values():
            self.assertNotIn("capabilities", contract)
            self.assertNotIn("evidence_refs", contract)
            self.assertLessEqual(len(contract.get("data_requirements") or []), 4)
            self.assertLessEqual(len(contract.get("execution_constraints") or []), 3)
            self.assertIn("data_requirements_count", contract)
            self.assertIn("execution_constraints_count", contract)
            for requirement in contract.get("data_requirements") or []:
                self.assertNotIn("primary_provider", requirement)
                self.assertNotIn("fallback_providers", requirement)
                self.assertNotIn("allows_required_capabilities", requirement)
            for constraint in contract.get("execution_constraints") or []:
                self.assertNotIn("why_not", constraint)

    def test_today_split_routes_keep_summary_and_actions_lightweight(self) -> None:
        summary_response = self.client.get("/api/today/summary")
        actions_response = self.client.get("/api/today/actions")
        self.assertEqual(summary_response.status_code, 200)
        self.assertEqual(actions_response.status_code, 200)
        summary = summary_response.json()
        actions = actions_response.json()

        self.assertTrue(summary.get("summary_only"))
        self.assertIn("command_brief", summary)
        self.assertIn("readiness", summary)
        self.assertEqual((summary.get("links_lazy") or {}).get("actions"), "/api/today/actions")
        self.assertEqual((summary.get("links_lazy") or {}).get("action_contracts"), "/api/today/action-contracts")
        self.assertEqual(
            (summary.get("links_lazy") or {}).get("command_brief_detail"),
            "/api/today/command-brief-detail",
        )
        for key in (
            "action_queue",
            "decision_contracts",
            "source_cards",
            "quality_cards",
            "radar_cards",
            "risk_rows",
            "legacy_sections_deferred",
        ):
            self.assertNotIn(key, summary)

        for lane in (summary.get("command_brief") or {}).get("action_lanes") or []:
            self.assertLessEqual(len(lane.get("items") or []), 1)
            self.assertIn("total_count", lane)
            self.assertNotIn("subtitle", lane)

        self.assertIn("action_queue", actions)
        self.assertTrue(actions.get("decision_contracts_deferred"))
        self.assertNotIn("decision_contracts", actions)

        forbidden_item_keys = {
            "decision_contract",
            "execution_constraints",
            "factor_snapshot",
            "factor_explanation",
            "tushare_score_breakdown",
            "opportunity_v2",
            "ai_summary",
            "ai_delta",
            "risk_source_cards",
            "risk_evidence_refs",
            "v2_calibration_threshold_adjustments",
            "v2_playbook_adjustment",
        }
        items = [
            *((actions.get("action_queue") or {}).get("items") or []),
            *((actions.get("action_queue") or {}).get("stale_items") or []),
        ]
        for item in items:
            for key in ("key", "title", "decision"):
                self.assertIn(key, item)
            for key in forbidden_item_keys:
                self.assertNotIn(key, item)
            self.assertNotIn("updated_at", item["decision"])
            self.assertNotIn("updated_at_raw", item["decision"])

    def test_portfolio_account_readiness_uses_compact_payload(self) -> None:
        response = self.client.get("/api/portfolio/account?fresh=1")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        readiness = payload.get("readiness") or {}

        self.assertIn("trust_level", readiness)
        self.assertIn("formal_data_status", readiness)
        self.assertIn("account_state", readiness)
        self.assertNotIn("formal_blockers", readiness)
        self.assertNotIn("source_freshness", readiness)
        self.assertNotIn("dataset_freshness", readiness)
        self.assertNotIn("formal_freshness", readiness)
        self.assertNotIn("quality_freshness", readiness)
        self.assertNotIn("capabilities", readiness)
        self.assertNotIn("datasets", readiness["formal_data_status"])
        self.assertNotIn("source_plan", readiness["formal_data_status"])
        provider = readiness["formal_data_status"].get("provider") or {}
        self.assertNotIn("token_env_names", provider)
        self.assertNotIn("configured_token_env_names", provider)
        for blocker in readiness["formal_data_status"].get("blockers") or []:
            self.assertNotIn("source_apis", blocker)
            self.assertNotIn("required_permission", blocker)
            self.assertNotIn("docs", blocker)
        self.assertTrue(payload.get("holding_reviews_deferred"))
        self.assertTrue(payload.get("account_history_deferred"))
        self.assertNotIn("holding_reviews", payload)
        self.assertNotIn("holding_action_summary", payload)
        self.assertIn("recent_fills", payload)
        account = payload.get("account") or {}
        for key in (
            "fills",
            "closed_positions",
            "reconciliations",
            "position_plans",
            "identity_corrections",
            "mode_history",
            "available_modes",
        ):
            self.assertNotIn(key, account)

    def test_portfolio_holding_reviews_are_loaded_on_demand(self) -> None:
        compact = self.client.get("/api/portfolio/account?fresh=1")
        self.assertEqual(compact.status_code, 200)
        compact_payload = compact.json()
        self.assertTrue(compact_payload.get("holding_reviews_deferred"))
        self.assertTrue(compact_payload.get("account_history_deferred"))
        self.assertNotIn("holding_reviews", compact_payload)

        history = self.client.get("/api/portfolio/account?fresh=1&history=1")
        self.assertEqual(history.status_code, 200)
        history_payload = history.json()
        self.assertTrue(history_payload.get("holding_reviews_deferred"))
        self.assertFalse(history_payload.get("account_history_deferred"))
        self.assertNotIn("holding_reviews", history_payload)
        history_account = history_payload.get("account") or {}
        for key in (
            "fills",
            "closed_positions",
            "reconciliations",
            "position_plans",
            "identity_corrections",
            "mode_history",
            "available_modes",
        ):
            self.assertIn(key, history_account)

        full = self.client.get("/api/portfolio/account?fresh=1&compact=0")
        self.assertEqual(full.status_code, 200)
        full_payload = full.json()
        self.assertFalse(full_payload.get("holding_reviews_deferred"))
        self.assertFalse(full_payload.get("account_history_deferred"))
        self.assertIn("holding_reviews", full_payload)
        self.assertIn("holding_action_summary", full_payload)
        full_account = full_payload.get("account") or {}
        for key in ("fills", "closed_positions", "reconciliations", "mode_history", "available_modes"):
            self.assertIn(key, full_account)

        deferred = self.client.get("/api/portfolio/holding-reviews?fresh=1")
        self.assertEqual(deferred.status_code, 200)
        deferred_payload = deferred.json()
        self.assertIn("holding_reviews", deferred_payload)
        self.assertIn("holding_action_summary", deferred_payload)
        self.assertIn("position_count", deferred_payload)
        self.assertNotIn("readiness", deferred_payload)
        self.assertNotIn("account", deferred_payload)

    def test_watchlist_api_defaults_to_compact_payload(self) -> None:
        response = self.client.get("/api/watchlist?fresh=1")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertIn("groups", payload)
        self.assertIn("source_cards", payload)
        self.assertTrue(payload.get("manager_deferred"))
        self.assertEqual((payload.get("links_lazy") or {}).get("manager"), "/api/watchlist/manage")
        self.assertNotIn("full", payload.get("links_lazy") or {})
        self.assertNotIn("diff_deferred", payload)
        self.assertNotIn("manager", payload)
        self.assertNotIn("day_over_day_diff", payload)
        self.assertNotIn("reading_compass", payload)
        self.assertNotIn("priority_rows", payload)
        self.assertNotIn("confidence_switch", payload)
        self.assertNotIn("artifacts", payload)

        legacy_full = self.client.get("/api/watchlist?fresh=1&compact=0")
        self.assertEqual(legacy_full.status_code, 200)
        legacy_payload = legacy_full.json()
        self.assertTrue(legacy_payload.get("compact"))
        self.assertTrue(legacy_payload.get("manager_deferred"))
        self.assertNotIn("full", legacy_payload.get("links_lazy") or {})
        self.assertNotIn("diff_deferred", legacy_payload)
        self.assertNotIn("manager", legacy_payload)
        self.assertNotIn("day_over_day_diff", legacy_payload)
        self.assertNotIn("reading_compass", legacy_payload)
        self.assertNotIn("priority_rows", legacy_payload)
        self.assertNotIn("confidence_switch", legacy_payload)

    def test_watchlist_manage_api_uses_lightweight_manager_builder(self) -> None:
        route = next(
            route
            for route in app.routes
            if getattr(route, "path", "") == "/api/watchlist/manage" and "GET" in getattr(route, "methods", set())
        )
        endpoint_globals = route.endpoint.__globals__
        manager_build = Mock(return_value={"active_count": 1, "active_items": []})

        with patch.dict(
            endpoint_globals,
            {
                "build_watchlist_manager_api_view": manager_build,
                "_clear_watchlist_api_cache": Mock(),
                "upsert_watchlist_stock": Mock(
                    return_value={
                        "status": "updated",
                        "stock": {"code": "600690", "name": "海尔智家"},
                    }
                ),
                "clear_stock_profile_cache": Mock(),
                "_clear_watchlist_related_api_caches": Mock(),
                "launch_background_task": Mock(side_effect=AssertionError("refresh disabled")),
            },
        ):
            manage = self.client.get("/api/watchlist/manage?fresh=1")
            add = self.client.post(
                "/api/watchlist/manage/add",
                json={"code": "600690", "name": "海尔智家", "trigger_refresh": False},
            )

        self.assertEqual(manage.status_code, 200)
        self.assertEqual(add.status_code, 200)
        self.assertEqual(manage.json()["manager"]["active_count"], 1)
        self.assertEqual(add.json()["manager"]["active_count"], 1)
        self.assertEqual(manager_build.call_count, 2)

    def test_portfolio_and_watchlist_api_cache_honor_fresh_bypass(self) -> None:
        portfolio_route = next(
            route
            for route in app.routes
            if getattr(route, "path", "") == "/api/portfolio/account" and "GET" in getattr(route, "methods", set())
        )
        watchlist_route = next(
            route
            for route in app.routes
            if getattr(route, "path", "") == "/api/watchlist" and "GET" in getattr(route, "methods", set())
        )
        endpoint_globals = portfolio_route.endpoint.__globals__
        original_portfolio_cache = endpoint_globals["_PORTFOLIO_ACCOUNT_API_CACHE"]
        original_watchlist_cache = endpoint_globals["_WATCHLIST_API_CACHE"]
        original_portfolio_ttl = endpoint_globals["PORTFOLIO_ACCOUNT_API_CACHE_TTL_SECONDS"]
        original_watchlist_ttl = endpoint_globals["WATCHLIST_API_CACHE_TTL_SECONDS"]
        endpoint_globals["_PORTFOLIO_ACCOUNT_API_CACHE"] = None
        endpoint_globals["_WATCHLIST_API_CACHE"] = None
        endpoint_globals["PORTFOLIO_ACCOUNT_API_CACHE_TTL_SECONDS"] = 20
        endpoint_globals["WATCHLIST_API_CACHE_TTL_SECONDS"] = 20
        portfolio_build = Mock(
            side_effect=[
                {"generated_at": "portfolio-first", "readiness": {}, "account": {}, "summary_cards": []},
                {"generated_at": "portfolio-fresh", "readiness": {}, "account": {}, "summary_cards": []},
            ]
        )
        watchlist_build = Mock(
            side_effect=[
                {"generated_at": "watchlist-first", "display_date": "d", "groups": [], "manager_deferred": True},
                {"generated_at": "watchlist-fresh", "display_date": "d", "groups": [], "manager_deferred": True},
            ]
        )
        formal_status = Mock(return_value={"ready": True, "provider": {}})
        try:
            with patch.dict(
                endpoint_globals,
                {
                    "build_portfolio_account_view": portfolio_build,
                    "build_watchlist_summary_view": watchlist_build,
                    "build_formal_data_status_payload": formal_status,
                },
            ):
                portfolio_first = self.client.get("/api/portfolio/account")
                portfolio_cached = self.client.get("/api/portfolio/account")
                portfolio_fresh = self.client.get("/api/portfolio/account?fresh=1")
                watchlist_first = self.client.get("/api/watchlist")
                watchlist_cached = self.client.get("/api/watchlist")
                watchlist_fresh = self.client.get("/api/watchlist?fresh=1")
        finally:
            endpoint_globals["_PORTFOLIO_ACCOUNT_API_CACHE"] = original_portfolio_cache
            endpoint_globals["_WATCHLIST_API_CACHE"] = original_watchlist_cache
            endpoint_globals["PORTFOLIO_ACCOUNT_API_CACHE_TTL_SECONDS"] = original_portfolio_ttl
            endpoint_globals["WATCHLIST_API_CACHE_TTL_SECONDS"] = original_watchlist_ttl

        self.assertEqual(portfolio_first.status_code, 200)
        self.assertEqual(portfolio_cached.status_code, 200)
        self.assertEqual(portfolio_fresh.status_code, 200)
        self.assertEqual(portfolio_first.json()["generated_at"], "portfolio-first")
        self.assertEqual(portfolio_cached.json()["generated_at"], "portfolio-first")
        self.assertEqual(portfolio_fresh.json()["generated_at"], "portfolio-fresh")
        self.assertEqual(portfolio_build.call_count, 2)

        self.assertEqual(watchlist_first.status_code, 200)
        self.assertEqual(watchlist_cached.status_code, 200)
        self.assertEqual(watchlist_fresh.status_code, 200)
        self.assertEqual(watchlist_first.json()["generated_at"], "watchlist-first")
        self.assertEqual(watchlist_cached.json()["generated_at"], "watchlist-first")
        self.assertEqual(watchlist_fresh.json()["generated_at"], "watchlist-fresh")
        self.assertEqual(watchlist_build.call_count, 2)

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

    def test_legacy_stock_detail_json_routes_stay_removed(self) -> None:
        route_paths = {
            getattr(route, "path", "")
            for route in app.routes
            if "GET" in getattr(route, "methods", set())
        }
        for path in ("/api/watchlist/{code}", "/api/opportunities/{code}"):
            with self.subTest(route=path):
                self.assertNotIn(path, route_paths)

        with patch.object(
            app_module,
            "build_watchlist_detail_view",
            create=True,
        ) as watchlist_detail, patch.object(
            app_module,
            "build_candidate_detail_view",
            create=True,
        ) as candidate_detail:
            for path in ("/api/watchlist/600690?trade_date=2026-06-10", "/api/opportunities/600690"):
                with self.subTest(path=path):
                    self.assertEqual(self.client.get(path).status_code, 404)

        watchlist_detail.assert_not_called()
        candidate_detail.assert_not_called()

    def test_duplicate_today_detail_json_routes_stay_removed(self) -> None:
        route_paths = {
            getattr(route, "path", "")
            for route in app.routes
            if "GET" in getattr(route, "methods", set())
        }
        for path in ("/api/today/watchlist/{code}", "/api/today/candidates/{code}"):
            with self.subTest(route=path):
                self.assertNotIn(path, route_paths)
        with patch.object(app_module, "build_watchlist_detail_view", create=True) as watchlist_detail, patch.object(
            app_module,
            "build_candidate_detail_view",
            create=True,
        ) as candidate_detail:
            checks = (
                "/api/today/watchlist/600690?trade_date=2026-06-10",
                "/api/today/candidates/600690",
            )
            for path in checks:
                with self.subTest(path=path):
                    self.assertEqual(self.client.get(path).status_code, 404)
        watchlist_detail.assert_not_called()
        candidate_detail.assert_not_called()

    def test_legacy_batch_json_routes_stay_removed(self) -> None:
        route_paths = {
            getattr(route, "path", "")
            for route in app.routes
            if "GET" in getattr(route, "methods", set())
        }
        for path in ("/api/opportunities/batch/{kind}", "/api/today/batch/{kind}"):
            with self.subTest(route=path):
                self.assertNotIn(path, route_paths)
        with patch.object(app_module, "build_candidate_detail_view", create=True) as candidate_detail:
            for path in ("/api/opportunities/batch/confirmation", "/api/today/batch/confirmation"):
                with self.subTest(path=path):
                    response = self.client.get(path)
                    self.assertEqual(response.status_code, 404)
        candidate_detail.assert_not_called()

    def test_legacy_screener_batch_summary_skips_full_candidate_hydration(self) -> None:
        from control_panel import dashboard_data

        dashboard_source = (INVEST_FLOW_ROOT / "control-panel" / "dashboard_data.py").read_text(encoding="utf-8")
        self.assertNotIn("def build_screening_batch_view(", dashboard_source)
        candidates = [
            {
                "code": f"60000{index}",
                "name": f"候选{index}",
                "screening_status": "approved",
                "setup_label": "趋势延续",
                "priority_score": 80 - index,
                "entry_reason": "主线仍在",
                "tier": "A",
                "opportunity_v2": {"suggested_action_label": "继续观察", "thesis": "只取轻量摘要"},
            }
            for index in range(8)
        ]
        screening_batch = {
            "generated_at": "2026-06-10 09:40:00",
            "path": "/tmp/screening.json",
            "pool_label": "早盘池",
            "candidate_count": len(candidates),
            "approved_count": 6,
            "caution_count": 2,
            "excluded_count": 1,
            "screening_summary": {"execution_gate_status": "可观察"},
            "market_regime": {"execution_gate": {"summary": "轻量接口", "label": "观察"}},
            "market_themes": {
                "top_theme": "AI",
                "summary": "主线聚焦",
                "themes": [{"theme": "AI", "score": 91, "leader_codes": ["600000"]}],
            },
            "candidates": candidates,
        }

        with patch.object(dashboard_data, "expected_trade_date", return_value="2026-06-10"), patch.object(
            dashboard_data,
            "load_screening_batch",
            return_value=screening_batch,
        ), patch.object(
            dashboard_data,
            "safe_canonical_load",
            return_value={"path": "/tmp/quality.json", "validation_status": "pass", "checked_at": "now"},
        ), patch.object(
            dashboard_data,
            "build_screening_candidate_card",
            side_effect=AssertionError("compact summary must not hydrate full candidate cards"),
        ):
            payload = dashboard_data.build_screening_batch_summary_view()

        self.assertTrue(payload.get("compact"))
        self.assertEqual(payload.get("kind"), "screener")
        self.assertEqual((payload.get("links_lazy") or {}).get("opportunities"), "/api/opportunities")
        groups = payload.get("candidate_groups") or []
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].get("count"), len(candidates))
        self.assertTrue(groups[0].get("cards_deferred"))
        self.assertEqual(groups[0].get("cards_loaded"), 5)
        self.assertEqual(len(groups[0].get("cards") or []), 5)
        for card in groups[0].get("cards") or []:
            self.assertIn("code", card)
            self.assertIn("name", card)
            self.assertNotIn("opportunity_v2", card)
            self.assertNotIn("factor_snapshot", card)

    def test_backend_dead_dashboard_helpers_stay_removed(self) -> None:
        dashboard_source = (INVEST_FLOW_ROOT / "control-panel" / "dashboard_data.py").read_text(encoding="utf-8")
        app_source = (INVEST_FLOW_ROOT / "control-panel" / "app.py").read_text(encoding="utf-8")

        removed_helpers = (
            "def public_entry_plan_payload(",
            "def public_factor_explanation_payload(",
            "def public_ai_summary_payload(",
            "def public_ai_delta_payload(",
            "def public_playbook_adjustment_payload(",
            "def latest_quality_reports(",
            "QUALITY_PATTERNS =",
            "def _match_quality_files(",
            "def latest_quality_item(",
            "def latest_midday_refresh_status(",
            "def normalize_review_note_text(",
            "def ask_find_cross_card(",
            "def build_overview(",
            "def pick_artifact_for_reference(",
            "def infer_watchlist_report(",
            "def quality_report_artifact(",
            "def reference_dt_for_lane(",
            "def matched_run_for_task(",
            "def build_lane_alignment_warning(",
            "def build_lane_batch(",
            "def build_lane_detail_cards(",
            "def lane_cards(",
            "def kpi_cards(",
            "def build_today_holdings_rows(",
            "def build_today_opportunity_rows(",
            "def compress_opportunity_group(",
            "def build_today_dispatch_topline(",
            "def api_batch_detail_url(",
            "def api_today_batch_detail_url(",
            "def api_today_watchlist_detail_url(",
            "def api_today_candidate_detail_url(",
            "def api_watchlist_detail_url(",
            "def api_candidate_detail_url(",
            "def build_review_detail_view(",
            "def build_stock_profile_view(",
            "def build_stock_profile_full_view(",
            "def _stock_profile_legacy_source_reference(",
            "def _stock_profile_mark_deferred_legacy_slices(",
            "def _stock_profile_legacy_payload(",
            "def _stock_profile_full_payload(",
            "def build_watchlist_page_view(",
            "def build_watchlist_day_over_day_diff(",
            "def compress_watchlist_group(",
            "def watchlist_trigger_price(",
            "def build_watchlist_confidence_switch(",
        )
        for helper in removed_helpers:
            with self.subTest(helper=helper):
                self.assertNotIn(helper, dashboard_source)

        removed_app_helpers = (
            "def _latest_run_for_task_name(",
            "def _legacy_batch_detail_payload(",
            "def api_opportunities_batch_detail(",
            "def api_today_batch_detail(",
            "def api_today_watchlist_detail(",
            "def api_today_candidate_detail(",
            "def api_watchlist_detail(",
            "def api_opportunities_candidate_detail(",
            "def api_review_detail(",
            "def api_stock_profile_formal_data(",
            "def api_stock_profile(",
            "def api_stock_profile_full(",
        )
        for helper in removed_app_helpers:
            with self.subTest(helper=helper):
                self.assertNotIn(helper, app_source)

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

    def test_ask_suggest_empty_query_skips_heavy_builders(self) -> None:
        route = next(
            route
            for route in app.routes
            if getattr(route, "path", "") == "/api/ask/suggest" and "GET" in getattr(route, "methods", set())
        )
        endpoint_globals = route.endpoint.__globals__
        build_ask_page_view = Mock(return_value={"recent_queries": [{"code": "600690"}]})
        build_ask_suggestions = Mock(return_value=[{"code": "600690", "name": "海尔智家"}])

        with patch.dict(
            endpoint_globals,
            {"build_ask_page_view": build_ask_page_view, "build_ask_suggestions": build_ask_suggestions},
        ):
            responses = [
                self.client.get("/api/ask/suggest"),
                self.client.get("/api/ask/suggest?q=海"),
            ]

        for response, query in zip(responses, ("", "海"), strict=True):
            with self.subTest(query=query):
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertEqual(payload["query"], query)
                self.assertEqual(payload["items"], [])
                self.assertEqual(payload["recent_queries"], [])
                self.assertIn("输入至少 2 个字符", payload["message"])
        build_ask_page_view.assert_not_called()
        build_ask_suggestions.assert_not_called()

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

    def test_ask_followup_understands_action_question(self) -> None:
        answer = build_ask_followup_answer(
            {
                "hero": {
                    "decision_label": "继续观察",
                    "position": "0-0.5成",
                    "summary": "ROE偏弱",
                    "confidence_label": "高",
                    "confidence_note": "实时链路和系统上下文都比较完整。",
                },
                "canonical_decision": {
                    "why_now": "ROE偏弱",
                    "trigger_condition": "放量站上压力位 55.0 元",
                    "stop_condition": "盘中跌破止损位 52.0 元",
                    "next_step": "先观望",
                },
                "plan_rows": [
                    {"label": "动作", "value": "观望"},
                    {"label": "触发", "value": "放量站上压力位 55.0 元"},
                    {"label": "回避", "value": "ROE偏弱"},
                    {"label": "失效", "value": "盘中跌破止损位 52.0 元"},
                    {"label": "仓位", "value": "0-0.5成"},
                ],
                "level_cards": [
                    {"label": "支撑位", "value": 52.0, "detail": "MA10"},
                    {"label": "压力位", "value": 55.0, "detail": "MA20"},
                    {"label": "止损位", "value": 52.0, "detail": "MA10"},
                ],
                "metric_cards": [
                    {"label": "最新价", "value": 52.85, "detail": "15:00:03"},
                    {"label": "资金信号", "value": "主力净流出", "detail": "主力 -4573.68 万元"},
                ],
                "analysis_groups": [
                    {"title": "资金面", "metric": "主力净流出", "items": ["主力净流出"]},
                    {"title": "风险", "metric": "ROE偏弱", "items": ["ROE偏弱"]},
                ],
                "cross_cards": [
                    {"label": "自选股", "value": "未进入"},
                    {"label": "观察池", "value": "未进入"},
                    {"label": "今日动作队列", "value": "未进入"},
                ],
                "triggers": [
                    {
                        "name": "确认线",
                        "condition": "回踩不破支撑位 52.0 元，但若主力继续流出则不成立",
                        "action": "没有资金确认前，不把反弹当反转",
                    }
                ],
            },
            "这只今天到底要不要动？",
            [],
        )

        answer_text = json.dumps(answer, ensure_ascii=False)
        self.assertEqual(answer["intent"], "plan")
        self.assertIn("操作追问", answer["intent_label"])
        self.assertIn("先不主动动", answer["summary"])
        self.assertIn("放量站上压力位 55.0 元", answer_text)
        self.assertIn("盘中跌破止损位 52.0 元", answer_text)
        self.assertIn("ROE偏弱", answer_text)

    def test_ask_followup_uses_shared_ai_provider_config(self) -> None:
        keys = [
            "PRISM_ASK_FOLLOWUP_DISABLE",
            "PRISM_ASK_FOLLOWUP_API_KEY",
            "PRISM_ASK_FOLLOWUP_MODEL",
            "PRISM_ASK_FOLLOWUP_BASE_URL",
            "PRISM_ASK_FOLLOWUP_PROVIDER",
            "PRISM_AI_PROVIDER",
            "PRISM_AI_API_KEY",
            "PRISM_AI_MODEL",
            "PRISM_AI_BASE_URL",
            "OPENAI_API_KEY",
            "OPENAI_MODEL",
            "OPENAI_BASE_URL",
            "OPENAI_API_BASE",
        ]
        previous = {key: os.environ.get(key) for key in keys}
        try:
            for key in keys:
                os.environ.pop(key, None)
            os.environ["PRISM_AI_PROVIDER"] = "deepseek"
            os.environ["PRISM_AI_API_KEY"] = "test-key"

            config = ask_followup_model_config()
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.assertIsNotNone(config)
        assert config is not None
        self.assertEqual(config["model"], "deepseek-v4-flash")
        self.assertEqual(config["endpoint"], "https://api.deepseek.com/chat/completions")

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

    def test_legacy_review_detail_json_route_stays_removed(self) -> None:
        route_paths = {
            getattr(route, "path", "")
            for route in app.routes
            if "GET" in getattr(route, "methods", set())
        }
        self.assertNotIn("/api/review/detail", route_paths)

        with patch.object(app_module, "build_review_detail_view", create=True) as review_detail:
            response = self.client.get(
                "/api/review/detail",
                params={"section": "ai_regime_rows", "label": "弱修复"},
            )
        self.assertEqual(response.status_code, 404)
        review_detail.assert_not_called()

    def test_refresh_status_endpoint_returns_payload(self) -> None:
        response = self.client.get("/api/refresh/status?page=today")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["page"], "today")
        self.assertIn("recommended_task", payload)

    def test_refresh_status_rejects_unknown_page(self) -> None:
        response = self.client.get("/api/refresh/status?page=unknown")
        self.assertEqual(response.status_code, 400)

    def test_settings_page_defers_heavy_diagnostics(self) -> None:
        page_source = SETTINGS_PAGE_PATH.read_text(encoding="utf-8")
        page_compact_source = "".join(page_source.split())
        source = SETTINGS_WORKSPACE_PATH.read_text(encoding="utf-8")
        compact_source = "".join(source.split())
        diagnostics = SETTINGS_DIAGNOSTICS_PATH.read_text(encoding="utf-8")
        parameters = SETTINGS_PARAMETERS_PATH.read_text(encoding="utf-8")
        readiness_details = SETTINGS_READINESS_DETAILS_PATH.read_text(encoding="utf-8")
        safe_refresh = SETTINGS_SAFE_REFRESH_PATH.read_text(encoding="utf-8")
        hooks = WEB_HOOKS_PATH.read_text(encoding="utf-8")

        self.assertIn('import("./settings-workspace").then(', page_compact_source)
        self.assertIn("module.SettingsWorkspace", page_source)
        self.assertIn("function SettingsPageFallback()", page_source)
        self.assertIn("return <SettingsWorkspace />", page_source)
        self.assertNotIn("useQueryClient", page_source)
        self.assertNotIn("useOverview", page_source)
        self.assertNotIn("useRefreshStatus", page_source)
        self.assertNotIn("SettingsDiagnosticsMain", page_source)
        self.assertNotIn("SettingsSafeRefreshPanel", page_source)
        self.assertNotIn("SettingsParametersEditor", page_source)

        self.assertIn("export function SettingsWorkspace()", source)
        self.assertIn("const [diagnosticsEnabled, setDiagnosticsEnabled] = useState(false)", source)
        self.assertIn("const [advancedTasksOpen, setAdvancedTasksOpen] = useState(false)", source)
        self.assertIn("const overviewCompact = !advancedTasksOpen", source)
        self.assertIn("useOverview({ compact: overviewCompact })", source)
        self.assertIn("queryKey: queryKeys.overview(overviewCompact)", source)
        self.assertIn("api.getOverview({ fresh: true, compact: overviewCompact })", source)
        self.assertIn("queryClient.getQueryData<OverviewData>(queryKeys.overview(true)", compact_source)
        self.assertIn("const overviewData = overview.data || compactOverviewData", source)
        self.assertIn('useRefreshStatus("today",true,{auto:false,compact:true,poll:false,}', compact_source)
        self.assertIn('useRefreshStatus("today",diagnosticsEnabled,{auto:false,compact:false,poll:false,}', compact_source)
        self.assertIn("function refreshVisibleStatus()", source)
        self.assertIn("onClick={refreshVisibleStatus}", source)
        self.assertIn("if (diagnosticsEnabled) {\n      void refreshFullStatus();\n    }", source)
        self.assertNotIn("enableDiagnostics();\n                  void refreshOverview();", source)
        self.assertIn("dynamic<SettingsDiagnosticsMainProps>", source)
        self.assertIn('import("./settings-diagnostics").then(', compact_source)
        self.assertIn("module.SettingsDiagnosticsMain", source)
        self.assertIn("module.SettingsDiagnosticsAside", source)
        self.assertIn("dynamic<SettingsPreviewDrawerProps>", source)
        self.assertIn('import("@/components/preview-drawer").then(', compact_source)
        self.assertIn("module.PreviewDrawer", source)
        self.assertIn("dynamic<SettingsReadinessDetailsProps>", source)
        self.assertIn('import("./settings-readiness-details").then(', compact_source)
        self.assertIn("module.SettingsReadinessDetails", source)
        self.assertIn("<SettingsReadinessDetails", source)
        self.assertIn("dynamic<SettingsSafeRefreshPanelProps>", source)
        self.assertIn('import("./settings-safe-refresh").then(', compact_source)
        self.assertIn("module.SettingsSafeRefreshPanel", source)
        self.assertIn("<SettingsSafeRefreshPanel", source)
        self.assertIn('import("./settings-parameters").then(', compact_source)
        self.assertIn("module.ParametersEditor", source)
        self.assertIn("function DeferredParametersPanel()", source)
        self.assertIn(
            "<SettingsDiagnosticsMainstatus={refreshDiagnostics.data}onPreview={setPreview}/>",
            compact_source,
        )
        self.assertIn("preview.open?(", compact_source)
        self.assertIn("<SettingsPreviewDrawer", source)
        self.assertIn("advancedTasksOpen ? (", source)
        self.assertIn("onClick={() => setAdvancedTasksOpen(true)}", source)
        self.assertIn("日常刷新优先使用左侧安全入口。", source)
        self.assertIn("完整能力闸门、正式口径和数据依赖按需加载", source)
        self.assertIn("参数文件编辑器只在展开后加载", source)
        self.assertNotIn("window.setTimeout(() => setDiagnosticsEnabled(true)", source)
        self.assertNotIn("window.setTimeout(() => setAdvancedTasksOpen(true)", source)
        self.assertNotIn('useRefreshStatus("today", true, { auto: false, compact: false })', source)
        self.assertNotIn('useRefreshStatus("today", true, { auto: false, compact: true })', source)
        self.assertNotIn("const runs = useRuns();", source)
        self.assertNotIn("useRuns({ enabled: diagnosticsEnabled })", source)
        self.assertNotIn("const formalData = useFormalDataStatus();", source)
        self.assertNotIn("useFormalDataStatus({ enabled: diagnosticsEnabled })", source)
        self.assertNotIn("useDataAssetsStatus({ compact: dataAssetsCompact, enabled: diagnosticsEnabled })", source)
        self.assertNotIn("useTriggerRefresh", source)
        self.assertNotIn("function SafeRefreshPanel", source)
        self.assertNotIn("function formatDuration", source)
        self.assertNotIn("formatCooldown(row.cooldown_remaining_seconds)", source)
        self.assertNotIn("manual_from_settings_safe_refresh", source)
        self.assertNotIn("当前没有待恢复的步骤", source)
        self.assertNotIn("运行此步", source)
        self.assertNotIn("const parameters = useParameters();", source)
        self.assertNotIn("useParameters({ enabled: editorOpen })", source)
        self.assertNotIn("import { PreviewDrawer", source)
        self.assertNotIn("<DecisionLedgerHealthPanel />", source)
        self.assertNotIn("function DataAssetsPanel", source)
        self.assertNotIn("function FormalDataPanel", source)
        self.assertNotIn("function TaskRunnerPanel", source)
        self.assertNotIn("function RecentRunsPanel", source)
        self.assertNotIn("function DatasetFreshnessPanel", source)
        self.assertNotIn("function formatAuthorityLabel", source)
        self.assertNotIn("function datasetIssueKind", source)
        self.assertNotIn("const CAPABILITY_LABELS", source)
        self.assertNotIn("const HARD_DATA_REASONS", source)
        self.assertNotIn("refreshReasonCopy", source)
        self.assertNotIn("refreshReasonLabel", source)

        self.assertIn("export function SettingsDiagnosticsMain", diagnostics)
        self.assertIn("export function SettingsDiagnosticsAside", diagnostics)
        self.assertIn("const [recentRunsOpen, setRecentRunsOpen] = useState(false)", diagnostics)
        self.assertIn("useRuns({ enabled: recentRunsOpen })", diagnostics)
        self.assertIn("查看最近运行", diagnostics)
        self.assertIn("onOpen={() => setRecentRunsOpen(true)}", diagnostics)
        self.assertIn("recentRunsOpen ? (", diagnostics)
        self.assertNotIn("useRuns({ enabled: true })", diagnostics)
        self.assertIn("type PreviewUpdater = (", diagnostics)
        self.assertIn("async function previewRunDetail(", diagnostics)
        self.assertIn("async function previewRunLog(", diagnostics)
        self.assertIn("const hasDetail = Boolean(runId || run.meta_path)", diagnostics)
        self.assertIn("const hasLog = Boolean(runId || run.log_path)", diagnostics)
        self.assertNotIn("async function openRunDetail(", diagnostics)
        self.assertNotIn("async function openRunLog(", diagnostics)
        self.assertNotIn("async function openDetail(", diagnostics)
        self.assertNotIn("async function openLog(", diagnostics)
        self.assertIn("const [formalDataDetailOpen, setFormalDataDetailOpen] = useState(false)", diagnostics)
        self.assertIn("useFormalDataStatus({ compact: !formalDataDetailOpen, enabled: true })", diagnostics)
        self.assertIn("const [dataAssetsDetailOpen, setDataAssetsDetailOpen] = useState(false)", diagnostics)
        self.assertIn("useDataAssetsStatus({ compact: !dataAssetsDetailOpen, enabled: true })", diagnostics)
        self.assertIn("<DecisionLedgerHealthPanel enabled={showLedger} />", diagnostics)
        self.assertIn("function DataAssetsPanel", diagnostics)
        self.assertIn("function FormalDataPanel", diagnostics)
        self.assertIn("function TaskRunnerPanel", diagnostics)
        self.assertIn("function DeferredRecentRunsPanel", diagnostics)
        self.assertIn("function RecentRunsPanel", diagnostics)

        self.assertIn("export function SettingsSafeRefreshPanel", safe_refresh)
        self.assertIn("useTriggerRefresh(\"today\")", safe_refresh)
        self.assertIn("function formatDuration", safe_refresh)
        self.assertIn("formatCooldown(row.cooldown_remaining_seconds)", safe_refresh)
        self.assertIn("manual_from_settings_safe_refresh", safe_refresh)
        self.assertIn("当前没有待恢复的步骤", safe_refresh)
        self.assertIn("运行此步", safe_refresh)
        self.assertIn("safeTaskList(tasks)", safe_refresh)

        self.assertIn("export function ParametersEditor()", parameters)
        self.assertIn("useParameters({ enabled: editorOpen })", parameters)
        save_parameters_start = hooks.index("export function useSaveParameters")
        save_parameters_next = hooks.find("\nexport function ", save_parameters_start + 1)
        save_parameters_source = hooks[
            save_parameters_start:save_parameters_next if save_parameters_next != -1 else len(hooks)
        ]
        self.assertIn(
            "queryClient.setQueryData<ParametersResponse>(queryKeys.parameters, payload)",
            save_parameters_source,
        )
        self.assertNotIn("invalidateQueries", save_parameters_source)

        self.assertIn("export function SettingsReadinessDetails", readiness_details)
        self.assertIn("function DatasetFreshnessPanel", readiness_details)
        self.assertIn("function formatAuthorityLabel", readiness_details)
        self.assertIn("function datasetIssueKind", readiness_details)
        self.assertIn("const CAPABILITY_LABELS", readiness_details)
        self.assertIn("const HARD_DATA_REASONS", readiness_details)
        self.assertIn("refreshReasonCopy", readiness_details)
        self.assertIn("refreshReasonLabel", readiness_details)
        self.assertIn("正式数据口径", readiness_details)
        self.assertIn("能力闸门数据依赖", readiness_details)

    def test_today_page_defers_action_details_and_refresh_status(self) -> None:
        page_source = TODAY_PAGE_PATH.read_text(encoding="utf-8")
        page_compact_source = "".join(page_source.split())
        source = COMMAND_CENTER_WORKSPACE_PATH.read_text(encoding="utf-8")
        compact_source = "".join(source.split())
        details_source = TODAY_ACTION_DETAILS_PATH.read_text(encoding="utf-8")
        trust_fold_source = COMMAND_BRIEF_TRUST_FOLD_PATH.read_text(encoding="utf-8")
        compact_trust_fold = "".join(trust_fold_source.split())
        hooks = WEB_HOOKS_PATH.read_text(encoding="utf-8")

        self.assertIn('import("./command-center-workspace").then(', page_compact_source)
        self.assertIn("module.CommandCenterWorkspace", page_source)
        self.assertIn("function CommandCenterPageFallback()", page_source)
        self.assertIn("return <CommandCenterWorkspace />", page_source)
        self.assertNotIn("useTodaySummary", page_source)
        self.assertNotIn("useTodayActions", page_source)
        self.assertNotIn("useTodayActionContracts", page_source)
        self.assertNotIn("useTodayCommandBriefDetail", page_source)
        self.assertNotIn("useRefreshStatus", page_source)
        self.assertNotIn("DeferredTrustBanner", page_source)
        self.assertNotIn("TodayActionDetails", page_source)

        self.assertIn("export function CommandCenterWorkspace()", source)
        self.assertIn('import dynamic from "next/dynamic"', source)
        self.assertIn('import("./today-action-details").then(', source)
        self.assertIn("(module) => module.TodayActionDetails", source)
        self.assertIn("const TodayActionDetails = dynamic(", source)
        self.assertIn("const [actionsEnabled, setActionsEnabled] = useState(false)", source)
        self.assertIn("const [briefDetailOpen, setBriefDetailOpen] = useState(false)", source)
        self.assertIn("const [trustOpen, setTrustOpen] = useState(false)", source)
        self.assertIn("function loadActionDetails()", source)
        self.assertIn("判断细节", source)
        self.assertIn("动作明细按需加载", source)
        self.assertIn("加载动作明细", source)
        self.assertIn('useTodayActions({ enabled: actionsEnabled })', source)
        self.assertIn("useTodayCommandBriefDetail({", source)
        self.assertIn("enabled: briefDetailOpen", source)
        self.assertIn("api.getTodayCommandBriefDetail({ fresh: true })", source)
        self.assertIn("Promise.allSettled", source)
        self.assertIn('summaryResult.status === "fulfilled"', source)
        self.assertIn('actionsResult.status === "fulfilled" && actionsResult.value', source)
        self.assertIn('briefDetailResult.status === "fulfilled" && briefDetailResult.value', source)
        self.assertNotIn("const [summary, actions, briefDetailPayload] = await Promise.all(", source)
        self.assertIn("queryKeys.todayCommandBriefDetail", source)
        self.assertIn("setBriefDetailOpen(event.currentTarget.open)", source)
        self.assertIn("data-od-id=\"command-brief-detail\"", source)
        self.assertNotIn("<JudgementChain items={brief.judgement_chain} />", source)
        self.assertNotIn("<MiddayVerify payload={brief.midday_verify} />", source)
        self.assertIn('useRefreshStatus("today",trustOpen,{', compact_source)
        self.assertIn("auto:false", compact_source)
        self.assertIn("compact:true", compact_source)
        self.assertIn("poll:false", compact_source)
        self.assertIn("<TrustFold", source)
        self.assertIn("open={trustOpen}", source)
        self.assertIn("onOpenChange={setTrustOpen}", source)
        self.assertIn(
            "<TodayActionDetailsactions={actionsData}/>",
            compact_source,
        )
        self.assertIn("queryKey: queryKeys.todayActionContracts", source)
        self.assertIn('refetchType: "active"', source)
        self.assertNotIn("useTodayActionContracts", source)
        self.assertNotIn("todayActionContracts.isFetching", source)
        self.assertNotIn("contractsData={todayActionContracts.data}", source)
        self.assertNotIn("window.setTimeout(() => setActionsEnabled(true)", source)
        self.assertNotIn("setActionsEnabled(true);\n      }", source)
        self.assertNotIn('useRefreshStatus("today", true', source)
        self.assertNotIn('useRefreshStatus("today", true, { auto: true, compact: true })', source)
        self.assertNotIn("function DecisionContractPanel", source)
        self.assertNotIn("function ActionRegisterStrip", source)
        self.assertNotIn("DecisionContractConstraint", source)
        self.assertNotIn("TodayActionRegister", source)
        self.assertIn("建议刷新{refreshStatus.data?.recommended_task?.title??\"-\"}", compact_source)

        self.assertIn("export function TodayActionDetails", details_source)
        self.assertIn("const [contractsOpen, setContractsOpen] = useState(false)", details_source)
        self.assertIn("useTodayActionContracts({", details_source)
        self.assertIn("enabled: Boolean(contractsOpen && actions?.decision_contracts_deferred && !inlineContracts)", details_source)
        self.assertIn("onToggle={(event) => setContractsOpen(event.currentTarget.open)}", details_source)
        self.assertIn("function DecisionContractPanel", details_source)
        self.assertIn("function ActionRegisterStrip", details_source)
        self.assertIn("动作契约", details_source)
        self.assertIn("按需加载", details_source)
        self.assertIn("今日动作口径", details_source)

        self.assertIn("export function TrustFold(", trust_fold_source)
        self.assertIn("open: boolean", trust_fold_source)
        self.assertIn("onOpenChange: (open: boolean) => void", trust_fold_source)
        self.assertIn("open={open}", trust_fold_source)
        self.assertIn(
            "onToggle={(event)=>onOpenChange(event.currentTarget.open)}",
            compact_trust_fold,
        )
        self.assertIn("{open?<divclassName=\"mt-3space-y-3\">{children}</div>:null}", compact_trust_fold)
        self.assertNotIn("<divclassName=\"mt-3space-y-3\">{children}</div></details>", compact_trust_fold)

        summary_start = hooks.index("export function useTodaySummary")
        summary_next_export = hooks.find("\nexport function ", summary_start + 1)
        summary_source = hooks[summary_start: summary_next_export if summary_next_export != -1 else len(hooks)]
        self.assertIn("staleTime: 45_000", summary_source)
        self.assertIn("refetchInterval: false", summary_source)
        self.assertIn("refetchOnWindowFocus: false", summary_source)
        self.assertNotIn("refetchInterval: 30_000", summary_source)
        self.assertNotIn("refetchOnWindowFocus: true", summary_source)

        for function_name in ("useTodayActions", "useTodayActionContracts", "useTodayCommandBriefDetail"):
            with self.subTest(function_name=function_name):
                start = hooks.index(f"export function {function_name}")
                next_export = hooks.find("\nexport function ", start + 1)
                function_source = hooks[start: next_export if next_export != -1 else len(hooks)]
                self.assertIn("refetchInterval: false", function_source)
                self.assertIn("refetchOnWindowFocus: false", function_source)
                self.assertNotIn("refetchInterval: 30_000", function_source)
                self.assertNotIn("refetchOnWindowFocus: true", function_source)

    def test_today_action_decision_frontend_patches_actions_cache(self) -> None:
        hooks = WEB_HOOKS_PATH.read_text(encoding="utf-8")
        start = hooks.index("export function useUpdateTodayActionDecision")
        next_export = hooks.find("\nexport function ", start + 1)
        function_source = hooks[start: next_export if next_export != -1 else len(hooks)]

        self.assertNotIn("function invalidateTodayWorkspace", hooks)
        self.assertIn("patchTodayActionDecision(current, result)", function_source)
        self.assertIn("queryClient.setQueryData<TodayActionsData | undefined>(queryKeys.todayActions", function_source)
        self.assertIn("invalidateStockProfileTodayAction(queryClient, stockCodeFromActionKey(variables.key))", function_source)
        self.assertIn('variables.decision === "watch" || variables.decision === "skip"', function_source)
        self.assertIn(
            "invalidateActiveDecisionLedgerExecutionViews(queryClient, [stockCodeFromActionKey(variables.key)])",
            function_source,
        )
        self.assertNotIn("invalidateTodayWorkspace(queryClient)", function_source)
        self.assertNotIn("queryKeys.portfolioAccount", function_source)
        self.assertNotIn("queryKeys.decisionLedger", function_source)
        self.assertNotIn("invalidateStockProfileWorkspace(queryClient)", function_source)

    def test_portfolio_writeback_frontend_reuses_returned_account_payload(self) -> None:
        hooks = WEB_HOOKS_PATH.read_text(encoding="utf-8")
        self.assertIn("function setPortfolioAccountCache", hooks)
        self.assertIn("function invalidateActivePortfolioHoldingReviews", hooks)
        self.assertIn("function invalidateStockProfileDecisionWorkspace", hooks)
        self.assertIn("function invalidateActiveDecisionLedgerExecutionViews", hooks)
        self.assertNotIn("void queryClient.invalidateQueries({ queryKey: queryKeys.decisionLedger });", hooks)
        self.assertIn('refetchType: "active"', hooks)

        for function_name in (
            "useSetPortfolioMode",
            "useRecordPortfolioCash",
            "useRecordPortfolioFill",
            "useAmendPortfolioHoldingIdentity",
            "useRecordPortfolioNoFill",
            "useRecordPortfolioReconcile",
        ):
            with self.subTest(function_name=function_name):
                start = hooks.index(f"export function {function_name}")
                next_export = hooks.find("\nexport function ", start + 1)
                function_source = hooks[start: next_export if next_export != -1 else len(hooks)]
                self.assertIn("setPortfolioAccountCache(queryClient, payload)", function_source)
                self.assertIn("invalidateActivePortfolioHoldingReviews(queryClient)", function_source)
                self.assertIn("invalidateStockProfileDecisionWorkspace(queryClient", function_source)
                self.assertNotIn("queryKeys.portfolioAccount", function_source)
                self.assertNotIn("queryKeys.portfolioHoldingReviews", function_source)
                self.assertNotIn("invalidateStockProfileWorkspace(queryClient)", function_source)

        fill_start = hooks.index("export function useRecordPortfolioFill")
        fill_next = hooks.find("\nexport function ", fill_start + 1)
        fill_source = hooks[fill_start: fill_next if fill_next != -1 else len(hooks)]
        self.assertIn("onSuccess: (payload, variables)", fill_source)
        self.assertIn("invalidateStockProfileDecisionWorkspace(queryClient, variables.code)", fill_source)
        self.assertIn("invalidateActiveDecisionLedgerExecutionViews(queryClient, [variables.code])", fill_source)
        self.assertNotIn("queryKeys.decisionLedger", fill_source)
        self.assertNotIn("invalidateStockProfileDecisionWorkspace(queryClient);\n      void queryClient.invalidateQueries", fill_source)

        amend_start = hooks.index("export function useAmendPortfolioHoldingIdentity")
        amend_next = hooks.find("\nexport function ", amend_start + 1)
        amend_source = hooks[amend_start: amend_next if amend_next != -1 else len(hooks)]
        self.assertIn(
            "invalidateActiveDecisionLedgerExecutionViews(queryClient, [variables.from_code, variables.to_code])",
            amend_source,
        )
        self.assertNotIn("queryKeys.decisionLedger", amend_source)

        no_fill_start = hooks.index("export function useRecordPortfolioNoFill")
        no_fill_next = hooks.find("\nexport function ", no_fill_start + 1)
        no_fill_source = hooks[no_fill_start: no_fill_next if no_fill_next != -1 else len(hooks)]
        self.assertIn("onSuccess: (payload, variables)", no_fill_source)
        self.assertIn(
            "invalidateStockProfileDecisionWorkspace(queryClient, stockCodeFromActionKey(variables.intent_key))",
            no_fill_source,
        )
        self.assertIn(
            "invalidateActiveDecisionLedgerExecutionViews(queryClient, [stockCodeFromActionKey(variables.intent_key)])",
            no_fill_source,
        )
        self.assertNotIn("queryKeys.decisionLedger", no_fill_source)
        self.assertNotIn("invalidateStockProfileDecisionWorkspace(queryClient);\n      void queryClient.invalidateQueries", no_fill_source)

        helper_start = hooks.index("function invalidateStockProfileDecisionWorkspace")
        helper_next = hooks.find("\nfunction ", helper_start + 1)
        helper_source = hooks[helper_start:helper_next if helper_next != -1 else len(hooks)]
        self.assertIn("queryKeys.stockProfileSummary(normalizedCode)", helper_source)
        self.assertIn("queryKeys.stockProfileDetail(normalizedCode)", helper_source)
        self.assertIn("queryKeys.stockProfileEvidence(normalizedCode)", helper_source)
        self.assertIn("queryKeys.stockProfileSecondary(normalizedCode)", helper_source)
        self.assertIn("queryKeys.stockProfileTodayAction(normalizedCode)", helper_source)
        self.assertIn('["summary", "detail", "evidence", "secondary", "today-action"].includes(queryKey[2])', helper_source)
        self.assertNotIn("stockProfileFormalData", helper_source)
        self.assertNotIn("stockProfileLearningScorecard", helper_source)

        ledger_helper_start = hooks.index("function invalidateActiveDecisionLedgerExecutionViews")
        ledger_helper_next = hooks.find("\nfunction ", ledger_helper_start + 1)
        ledger_helper_source = hooks[ledger_helper_start:ledger_helper_next if ledger_helper_next != -1 else len(hooks)]
        self.assertIn('queryKey[1] === "recent"', ledger_helper_source)
        self.assertIn('queryKey[1] === "stock"', ledger_helper_source)
        self.assertIn('refetchType: "active"', ledger_helper_source)
        for cold_view in ("calibration", "learning-loop", "shadow-calibration", "health", "review-case"):
            self.assertNotIn(cold_view, ledger_helper_source)

    def test_watchlist_manage_frontend_reuses_returned_manager_payload(self) -> None:
        hooks = WEB_HOOKS_PATH.read_text(encoding="utf-8")
        self.assertIn("function updateWatchlistManagerCache", hooks)
        self.assertIn("queryClient.setQueryData(queryKeys.watchlistManager, { manager: payload.manager })", hooks)

        for function_name in ("useAddWatchlistStock", "useArchiveWatchlistStock", "useRestoreWatchlistStock"):
            with self.subTest(function_name=function_name):
                start = hooks.index(f"export function {function_name}")
                next_export = hooks.find("\nexport function ", start + 1)
                function_source = hooks[start: next_export if next_export != -1 else len(hooks)]
                self.assertIn("updateWatchlistManagerCache(queryClient, payload)", function_source)
                self.assertIn("invalidateStockProfileDecisionWorkspace(queryClient, variables.code)", function_source)
                self.assertNotIn("invalidateStockProfileWorkspace(queryClient, variables.code)", function_source)
                self.assertNotIn("queryKeys.watchlistManager", function_source)
                self.assertNotIn("queryKeys.parameters", function_source)

    def test_trigger_refresh_frontend_reuses_returned_status_payload(self) -> None:
        hooks = WEB_HOOKS_PATH.read_text(encoding="utf-8")
        start = hooks.index("export function useTriggerRefresh")
        next_export = hooks.find("\nexport function ", start + 1)
        function_source = hooks[start:next_export if next_export != -1 else len(hooks)]

        self.assertIn("queryClient.setQueryData(queryKeys.refreshStatus(page, false, false), payload.status)", function_source)
        self.assertIn("queryClient.setQueryData(queryKeys.refreshStatus(page, false, true), payload.status)", function_source)
        self.assertIn("queryClient.setQueryData(queryKeys.refreshStatus(page, true, false), payload.status)", function_source)
        self.assertIn("queryClient.setQueryData(queryKeys.refreshStatus(page, true, true), payload.status)", function_source)
        self.assertIn('queryKey: queryKeys.runs, refetchType: "active"', function_source)
        self.assertIn("invalidateActiveTodayWorkspace(queryClient, [\"summary\", \"actions\"])", function_source)
        self.assertIn('queryKey: queryKeys.watchlist, refetchType: "active"', function_source)
        self.assertIn('queryKey: queryKeys.opportunities, refetchType: "active"', function_source)
        self.assertIn('queryKey: queryKeys.opportunitiesSourceCards, refetchType: "active"', function_source)
        self.assertNotIn('queryKey: ["overview"]', function_source)
        self.assertNotIn("invalidateTodayWorkspace(queryClient)", function_source)
        self.assertNotIn("invalidateStockProfileWorkspace(queryClient);\n      }", function_source)

    def test_run_task_frontend_patches_local_run_state_without_global_refetch(self) -> None:
        hooks = WEB_HOOKS_PATH.read_text(encoding="utf-8")
        helper_start = hooks.index("function invalidateAfterTaskStart")
        helper_next = hooks.find("\nfunction ", helper_start + 1)
        helper_source = hooks[helper_start:helper_next if helper_next != -1 else len(hooks)]

        start = hooks.index("export function useRunTask")
        next_export = hooks.find("\nexport function ", start + 1)
        function_source = hooks[start:next_export if next_export != -1 else len(hooks)]

        self.assertIn("function patchTaskStartCaches", hooks)
        self.assertIn("queryClient.setQueryData<OverviewData | undefined>(queryKeys.overview(compact)", hooks)
        self.assertIn("queryClient.setQueryData<{ runs: RunItem[]; compact: boolean } | undefined>(queryKeys.runs", hooks)
        self.assertIn("patchTaskStartCaches(queryClient, payload, taskName)", function_source)
        self.assertIn("invalidateAfterTaskStart(queryClient, taskName)", function_source)
        self.assertNotIn("onSettled", function_source)
        self.assertIn('queryKey: queryKeys.runs, refetchType: "active"', helper_source)
        self.assertIn("invalidateActiveRefreshStatuses(queryClient, refreshStatusPagesForTask(normalized))", helper_source)
        self.assertNotIn('queryKey: ["overview"]', helper_source)
        self.assertNotIn("queryKeys.decisionLedger", helper_source)

    def test_settings_status_queries_do_not_silent_poll(self) -> None:
        hooks = WEB_HOOKS_PATH.read_text(encoding="utf-8")
        providers = (WEB_COMPONENTS_PATH / "providers.tsx").read_text(encoding="utf-8")
        functions = (
            "useOverview",
            "useRuns",
            "useHealth",
            "useFormalDataStatus",
            "useDataAssetsStatus",
            "useDecisionLedgerHealth",
        )

        for function_name in functions:
            with self.subTest(function_name=function_name):
                start = hooks.index(f"export function {function_name}")
                next_export = hooks.find("\nexport function ", start + 1)
                function_source = hooks[start: next_export if next_export != -1 else len(hooks)]
                self.assertIn("refetchInterval: false", function_source)
                self.assertIn("refetchOnWindowFocus: false", function_source)
                self.assertNotIn("refetchInterval: 30_000", function_source)
                self.assertNotIn("refetchInterval: 60_000", function_source)
                self.assertNotIn("refetchInterval: 120_000", function_source)

        shell_start = hooks.index("export function useShellStatus")
        shell_next_export = hooks.find("\nexport function ", shell_start + 1)
        shell_source = hooks[shell_start: shell_next_export if shell_next_export != -1 else len(hooks)]
        self.assertIn("staleTime: 120_000", shell_source)
        self.assertIn("refetchInterval: 180_000", shell_source)
        self.assertIn("refetchOnWindowFocus: false", shell_source)
        self.assertNotIn("refetchInterval: 60_000", shell_source)
        self.assertNotIn("refetchOnWindowFocus: true", shell_source)
        self.assertIn("refetchOnWindowFocus: false", providers)
        self.assertIn("refetchOnReconnect: false", providers)
        self.assertNotIn("refetchOnReconnect: true", providers)

    def test_discovery_page_defers_context_panels(self) -> None:
        page_source = DISCOVERY_PAGE_PATH.read_text(encoding="utf-8")
        page_compact_source = "".join(page_source.split())
        source = DISCOVERY_WORKSPACE_PATH.read_text(encoding="utf-8")
        compact_source = "".join(source.split())
        context_source = DISCOVERY_CONTEXT_PANELS_PATH.read_text(encoding="utf-8")

        self.assertIn('import("./discovery-workspace").then(', page_compact_source)
        self.assertIn("module.DiscoveryWorkspace", page_source)
        self.assertIn("function DiscoveryPageFallback()", page_source)
        self.assertIn("return <DiscoveryWorkspace />", page_source)
        self.assertNotIn("useOpportunities", page_source)
        self.assertNotIn("useOpportunitiesContext", page_source)
        self.assertNotIn("useShellStatus", page_source)
        self.assertNotIn("DeferredTrustBanner", page_source)
        self.assertNotIn("DiscoveryObservationWorkbench", page_source)

        self.assertIn("export function DiscoveryWorkspace()", source)
        self.assertIn('import dynamic from "next/dynamic"', source)
        self.assertIn('import("./discovery-context-panels").then(', source)
        self.assertIn("(module) => module.DiscoveryContextPanels", source)
        self.assertIn("const DiscoveryContextPanels = dynamic(", source)
        self.assertIn("const trust = data?.readiness?.trust_level", source)
        self.assertNotIn("useShellStatus", source)
        self.assertNotIn("const shellStatus =", source)
        self.assertIn("const [contextOpen, setContextOpen] = useState(false)", source)
        self.assertIn("const [evidenceOpen, setEvidenceOpen] = useState(false)", source)
        self.assertIn(
            "constcontextQueryEnabled=Boolean(data?.context_deferred&&contextOpen,",
            compact_source,
        )
        self.assertIn(
            "constsourceCardsQueryEnabled=Boolean(data?.evidence_deferred&&evidenceOpen&&!contextData?.source_cards,",
            compact_source,
        )
        self.assertIn(
            "useOpportunitiesContext({enabled:contextQueryEnabled,",
            compact_source,
        )
        self.assertIn(
            "useOpportunitiesSourceCards({enabled:sourceCardsQueryEnabled,",
            compact_source,
        )
        self.assertIn("constcontextPanelEnabled=Boolean(data&&(!data.context_deferred||contextOpen),", compact_source)
        self.assertIn("按需加载观察池上下文", source)
        self.assertIn("加载上下文", source)
        self.assertIn("<DiscoveryContextPanelsdata={contextData}/>", compact_source)
        self.assertIn("{contextPanelEnabled?(", compact_source)
        self.assertNotIn("useOpportunitiesContext({ enabled: Boolean(data?.context_deferred) })", source)
        self.assertNotIn("contextOpen||evidenceOpen", compact_source)
        self.assertNotIn("{contextEnabled?(", compact_source)
        self.assertNotIn("const learningMemories = contextData?.learning_memories || []", source)
        self.assertNotIn("function ThemeRadar(", source)
        self.assertNotIn("function LifecycleTracker(", source)
        self.assertNotIn('import { LearningMemoryPreview } from "@/components/learning-memory"', source)

        self.assertIn("export function DiscoveryContextPanels(", context_source)
        self.assertIn("function ThemeRadar(", context_source)
        self.assertIn("function LifecycleTracker(", context_source)
        self.assertIn('import { LearningMemoryPreview } from "@/components/learning-memory"', context_source)
        self.assertIn("主线雷达", context_source)
        self.assertIn("延续追踪", context_source)

    def test_discovery_page_loads_deferred_groups_only_on_click(self) -> None:
        source = DISCOVERY_WORKSPACE_PATH.read_text(encoding="utf-8")
        workbench_source = DISCOVERY_OBSERVATION_WORKBENCH_PATH.read_text(encoding="utf-8")
        compact_source = "".join(source.split())
        compact_workbench = "".join(workbench_source.split())

        self.assertIn("const DiscoveryObservationWorkbench =", source)
        self.assertIn('import("./discovery-observation-workbench").then(', source)
        self.assertIn("(module) => module.DiscoveryObservationWorkbench", source)
        self.assertIn("<DiscoveryObservationWorkbench", source)
        self.assertIn("const activeGroupDeferred = groupHasDeferredCards(activeGroup);", source)
        self.assertIn("activeGroupDeferred", source)
        self.assertIn("() => void loadOpportunityGroup(activeGroupKey)", source)
        self.assertIn("loadingGroupKey===activeGroupKey", compact_source)
        self.assertNotIn("本阶段候选按需加载", source)
        self.assertNotIn("加载本阶段候选", source)
        self.assertNotIn("void loadOpportunityGroup(activeGroupKey);", source)
        self.assertNotIn("activeGroupDeferred,activeGroupKey,activeGroupLoadError,loadingGroupKey", compact_source)
        self.assertNotIn("(activeGroupDeferred && !activeGroupLoadError)", source)

        self.assertIn("export function DiscoveryObservationWorkbench", workbench_source)
        self.assertIn("function ObservationWorkbench(", workbench_source)
        self.assertIn("本阶段候选按需加载", workbench_source)
        self.assertIn("加载本阶段候选", workbench_source)
        self.assertIn("const deferredCards = groupHasDeferredCards(group);", workbench_source)
        self.assertIn("const hiddenCardCount = Math.max(groupCount(group) - cards.length, 0);", workbench_source)
        self.assertIn("deferredCards && hiddenCardCount > 0", workbench_source)
        self.assertIn("已先显示 {cards.length} 只优先候选，还有 {hiddenCardCount} 只待展开。", workbench_source)
        self.assertIn("加载其余候选", workbench_source)
        self.assertIn("onLoadGroup?: () => void", workbench_source)
        self.assertIn("onClick={onLoadGroup}", workbench_source)
        self.assertIn("deferred?(", compact_workbench)
        self.assertIn("deferredCards&&hiddenCardCount>0?(", compact_workbench)

    def test_discovery_page_shares_display_helpers(self) -> None:
        workspace_source = DISCOVERY_WORKSPACE_PATH.read_text(encoding="utf-8")
        context_source = DISCOVERY_CONTEXT_PANELS_PATH.read_text(encoding="utf-8")
        workbench_source = DISCOVERY_OBSERVATION_WORKBENCH_PATH.read_text(encoding="utf-8")
        utils_source = DISCOVERY_DISPLAY_UTILS_PATH.read_text(encoding="utf-8")

        for helper in (
            "groupCount",
            "groupHasDeferredCards",
            "cardHref",
            "displayGroupTitle",
            "persistenceTone",
            "persistenceLabel",
        ):
            self.assertIn(f"export function {helper}(", utils_source)

        for consumer_source in (workspace_source, context_source, workbench_source):
            self.assertIn('from "./discovery-display-utils"', consumer_source)

        for consumer_source in (workspace_source, context_source, workbench_source):
            for helper in (
                "groupCount",
                "groupHasDeferredCards",
                "cardHref",
                "displayGroupTitle",
                "persistenceTone",
                "persistenceLabel",
            ):
                self.assertNotIn(f"function {helper}(", consumer_source)

    def test_discovery_page_defers_evidence_panel_code(self) -> None:
        source = DISCOVERY_WORKSPACE_PATH.read_text(encoding="utf-8")
        compact_source = "".join(source.split())
        evidence_panel = EVIDENCE_PANEL_PATH.read_text(encoding="utf-8")

        self.assertIn("const DiscoveryEvidencePanel = dynamic(", source)
        self.assertIn('import("@/components/evidence-panel").then(', source)
        self.assertIn("(module) => module.EvidencePanel", source)
        self.assertIn("const [evidenceOpen, setEvidenceOpen] = useState(false)", source)
        self.assertIn("data-testid=\"discovery-evidence-gate\"", source)
        self.assertIn("来源证据按需加载", source)
        self.assertIn("加载数据健康", source)
        self.assertIn("<DiscoveryEvidencePanel", source)
        self.assertIn("const evidenceSources =", source)
        self.assertIn("opportunitiesSourceCards.data?.source_cards ||", source)
        self.assertIn("contextData?.source_cards ||", source)
        self.assertIn("evidenceOpen?(", compact_source)
        self.assertIn(
            "evidenceOpen?(<DiscoveryEvidencePanelpage=\"opportunities\"",
            compact_source,
        )
        self.assertIn("sources={evidenceSources}", source)
        self.assertNotIn("sources={data?.source_cards}", source)
        self.assertNotIn('import { EvidencePanel } from "@/components/evidence-panel"', source)
        self.assertNotIn("<EvidencePanel", source)
        self.assertNotIn("useRefreshStatus", source)
        self.assertNotIn("useTriggerRefresh", source)
        self.assertNotIn("PreviewDrawer", source)
        self.assertNotIn('import { SourceCard } from "@/components/source-card"', source)

        self.assertIn("export function EvidencePanel(", evidence_panel)
        self.assertIn("useRefreshStatus(refreshPage, Boolean(refreshPage)", evidence_panel)
        self.assertIn("useTriggerRefresh(refreshPage, { stockCode })", evidence_panel)
        self.assertIn("PreviewDrawer", evidence_panel)
        self.assertIn("SourceCard", evidence_panel)

    def test_discovery_page_defers_observation_write_actions(self) -> None:
        source = DISCOVERY_WORKSPACE_PATH.read_text(encoding="utf-8")
        workbench_source = DISCOVERY_OBSERVATION_WORKBENCH_PATH.read_text(encoding="utf-8")
        action_source = DISCOVERY_OBSERVATION_ACTIONS_PATH.read_text(encoding="utf-8")

        self.assertIn("const DiscoveryObservationActions = dynamic<DiscoveryObservationActionsProps>", workbench_source)
        self.assertIn('import("./discovery-observation-actions").then(', workbench_source)
        self.assertIn("data-testid=\"discovery-observation-actions-gate\"", workbench_source)
        self.assertIn("展开观察操作", workbench_source)
        self.assertIn("<DiscoveryObservationActions", workbench_source)
        self.assertNotIn("const DiscoveryObservationActions = dynamic<DiscoveryObservationActionsProps>", source)
        self.assertNotIn('import("./discovery-observation-actions").then(', source)
        self.assertNotIn("data-testid=\"discovery-observation-actions-gate\"", source)
        self.assertNotIn("展开观察操作", source)
        self.assertNotIn("<DiscoveryObservationActions", source)
        self.assertNotIn("useAddWatchlistStock", source)
        self.assertNotIn("useUpdateTodayActionDecision", source)
        self.assertNotIn("addStock.mutate", source)
        self.assertNotIn("reviewDecision.mutate", source)
        self.assertNotIn("function addToObservationPlan", source)
        self.assertNotIn("function markReviewed", source)

        self.assertIn("export function DiscoveryObservationActions", action_source)
        self.assertIn("useAddWatchlistStock", action_source)
        self.assertIn("useUpdateTodayActionDecision", action_source)
        self.assertIn("加入观察计划", action_source)
        self.assertIn("标记已复核", action_source)

    def test_discovery_page_defers_v2_ai_and_full_evidence_details(self) -> None:
        source = DISCOVERY_WORKSPACE_PATH.read_text(encoding="utf-8")
        workbench_source = DISCOVERY_OBSERVATION_WORKBENCH_PATH.read_text(encoding="utf-8")
        compact_workbench = "".join(workbench_source.split())
        detail_source = DISCOVERY_V2_DETAILS_PATH.read_text(encoding="utf-8")
        utils_source = DISCOVERY_V2_UTILS_PATH.read_text(encoding="utf-8")
        text_utils_source = WEB_TEXT_UTILS_PATH.read_text(encoding="utf-8")

        self.assertIn("const DiscoveryOpportunityEvidenceDetails =", workbench_source)
        self.assertIn("const DiscoveryV2AiTelemetry = dynamic<DiscoveryV2AiTelemetryProps>", workbench_source)
        self.assertIn('import("./discovery-v2-details").then(', workbench_source)
        self.assertIn('from "./discovery-v2-utils"', workbench_source)
        self.assertIn('from "./discovery-v2-utils"', detail_source)
        self.assertIn("(module) => module.DiscoveryOpportunityEvidenceDetails", workbench_source)
        self.assertIn("(module) => module.DiscoveryV2AiTelemetry", workbench_source)
        self.assertIn('const [aiTelemetryOpen, setAiTelemetryOpen] = useState(false)', workbench_source)
        self.assertIn('data-testid="discovery-ai-telemetry-gate"', workbench_source)
        self.assertIn("加载 AI 诊断", workbench_source)
        self.assertIn("expanded?(<DiscoveryOpportunityEvidenceDetails", compact_workbench)
        self.assertIn("gate={gate}", workbench_source)
        self.assertNotIn("const DiscoveryOpportunityEvidenceDetails =", source)
        self.assertNotIn("const DiscoveryV2AiTelemetry = dynamic<DiscoveryV2AiTelemetryProps>", source)
        self.assertNotIn("(module) => module.DiscoveryOpportunityEvidenceDetails", source)
        self.assertNotIn("(module) => module.DiscoveryV2AiTelemetry", source)
        self.assertNotIn('const [aiTelemetryOpen, setAiTelemetryOpen] = useState(false)', source)
        self.assertNotIn('data-testid="discovery-ai-telemetry-gate"', source)
        self.assertNotIn("加载 AI 诊断", source)
        self.assertNotIn("function v2AiTelemetry(", source)
        self.assertNotIn("function v2AiTitle(", source)
        self.assertNotIn("function v2AiDetail(", source)
        self.assertNotIn("function v2AiChangedFields(", source)
        self.assertNotIn("function v2AiProviderLabel(", source)
        self.assertNotIn("function V2AiInsight(", source)

        self.assertIn("export function DiscoveryOpportunityEvidenceDetails", detail_source)
        self.assertIn("export function DiscoveryV2AiTelemetry", detail_source)
        self.assertIn("function v2AiTelemetry(", detail_source)
        self.assertIn("function v2AiTitle(", detail_source)
        self.assertIn("function v2AiDetail(", detail_source)
        self.assertIn("function v2AiProviderLabel(", detail_source)
        self.assertIn("完整依据", detail_source)
        self.assertIn("AI 改动", detail_source)
        self.assertIn("function v2Judgment(", utils_source)
        self.assertIn("export function hasV2(", utils_source)
        self.assertIn("export function v2MissingText(", utils_source)
        self.assertIn("export function v2CalibrationMeta(", utils_source)
        self.assertIn("export function v2AiStatus(", utils_source)
        self.assertIn("export function v2ActionTone(", utils_source)
        self.assertIn('from "@/lib/text-utils"', utils_source)
        self.assertIn('export { uniqueTexts } from "@/lib/text-utils"', utils_source)
        self.assertIn("function flattenTexts(", text_utils_source)
        self.assertIn("export function uniqueTexts(", text_utils_source)
        self.assertNotIn("export function flattenTexts(", text_utils_source)
        self.assertNotIn("function flattenTexts(", utils_source)
        self.assertNotIn("function uniqueTexts(", utils_source)
        self.assertNotIn("function v2Judgment(", workbench_source)
        self.assertNotIn("function v2Judgment(", detail_source)
        self.assertNotIn("function v2MissingText(", workbench_source)
        self.assertNotIn("function v2MissingText(", detail_source)
        self.assertNotIn("function v2CalibrationMeta(", workbench_source)
        self.assertNotIn("function v2CalibrationMeta(", detail_source)
        self.assertNotIn("function buyGateMeta(", detail_source)
        self.assertNotIn("function entryPlanTexts(", detail_source)

    def test_discovery_page_defers_candidate_workbench_logic(self) -> None:
        source = DISCOVERY_WORKSPACE_PATH.read_text(encoding="utf-8")
        workbench_source = DISCOVERY_OBSERVATION_WORKBENCH_PATH.read_text(encoding="utf-8")
        utils_source = DISCOVERY_V2_UTILS_PATH.read_text(encoding="utf-8")

        self.assertIn("const DiscoveryObservationWorkbench =", source)
        self.assertIn("<DiscoveryObservationWorkbench", source)
        self.assertNotIn("function ObservationWorkbench(", source)
        self.assertNotIn("function BuyGateCell(", source)
        self.assertNotIn("function groupDecisionMeta(", source)
        self.assertNotIn("function buyGateMeta(", source)
        self.assertNotIn("function v2Judgment(", source)
        self.assertNotIn("function taskCards(", source)
        self.assertNotIn("function PipelineFlow(", source)
        self.assertNotIn('import { MetricCard, MetricSkeleton } from "@/components/metric-card"', source)
        self.assertNotIn("<MetricCard", source)
        self.assertNotIn("<table", source)

        self.assertIn("export function DiscoveryObservationWorkbench", workbench_source)
        self.assertIn("function ObservationWorkbench(", workbench_source)
        self.assertIn("function BuyGateCell(", workbench_source)
        self.assertIn("function groupDecisionMeta(", workbench_source)
        self.assertIn("function buyGateMeta(", workbench_source)
        self.assertIn('from "./discovery-v2-utils"', workbench_source)
        self.assertIn("function v2Judgment(", utils_source)
        self.assertNotIn("function v2Judgment(", workbench_source)
        self.assertIn("function taskCards(", workbench_source)
        self.assertIn("function PipelineFlow(", workbench_source)
        self.assertIn('import { MetricCard, MetricSkeleton } from "@/components/metric-card"', workbench_source)
        self.assertIn("<MetricCard", workbench_source)
        self.assertIn("<table", workbench_source)
        self.assertIn("买入闸门", workbench_source)

    def test_risk_level_tone_stays_deduplicated(self) -> None:
        workbench_source = DISCOVERY_OBSERVATION_WORKBENCH_PATH.read_text(encoding="utf-8")
        formal_source = STOCK_FORMAL_PANELS_PATH.read_text(encoding="utf-8")
        risk_utils_source = WEB_RISK_UTILS_PATH.read_text(encoding="utf-8")

        self.assertIn("export function riskLevelTone(", risk_utils_source)
        self.assertIn('import type { Tone } from "./types"', risk_utils_source)
        self.assertIn('from "@/lib/risk-utils"', workbench_source)
        self.assertIn('from "@/lib/risk-utils"', formal_source)
        self.assertNotIn("function riskLevelTone(", workbench_source)
        self.assertNotIn("function riskLevelTone(", formal_source)
        self.assertIn("function riskLevelLabel(", workbench_source)
        self.assertIn("function riskLevelLabel(", formal_source)

    def test_watchlist_and_discovery_queries_do_not_silent_poll(self) -> None:
        hooks = WEB_HOOKS_PATH.read_text(encoding="utf-8")
        functions = (
            "useWatchlist",
            "useWatchlistManager",
            "useOpportunities",
        )

        for function_name in functions:
            with self.subTest(function_name=function_name):
                start = hooks.index(f"export function {function_name}")
                next_export = hooks.find("\nexport function ", start + 1)
                function_source = hooks[start: next_export if next_export != -1 else len(hooks)]
                self.assertIn("refetchInterval: false", function_source)
                self.assertIn("refetchOnWindowFocus: false", function_source)
                self.assertNotIn("refetchInterval: 60_000", function_source)
                self.assertNotIn("refetchInterval: 90_000", function_source)
                self.assertNotIn("refetchInterval: 120_000", function_source)

    def test_deferred_companion_queries_do_not_silent_poll(self) -> None:
        hooks = WEB_HOOKS_PATH.read_text(encoding="utf-8")
        functions = (
            "useOpportunitiesContext",
            "useReviewShadowReplay",
            "useDecisionLedgerRecent",
            "useDecisionLedgerLearningLoop",
            "useDecisionLedgerShadowCalibration",
        )

        for function_name in functions:
            with self.subTest(function_name=function_name):
                start = hooks.index(f"export function {function_name}")
                next_export = hooks.find("\nexport function ", start + 1)
                function_source = hooks[start: next_export if next_export != -1 else len(hooks)]
                self.assertIn("refetchInterval: false", function_source)
                self.assertIn("refetchOnWindowFocus: false", function_source)
                self.assertNotIn("refetchInterval: 60_000", function_source)
                self.assertNotIn("refetchInterval: 90_000", function_source)
                self.assertNotIn("refetchInterval: 120_000", function_source)
                self.assertNotIn("refetchOnWindowFocus: true", function_source)
                self.assertNotIn("refetchInterval: 300_000", function_source)

    def test_evidence_panel_refresh_status_is_single_read_by_default(self) -> None:
        hooks = WEB_HOOKS_PATH.read_text(encoding="utf-8")
        evidence_panel = (WEB_COMPONENTS_PATH / "evidence-panel.tsx").read_text(encoding="utf-8")
        compact_evidence_panel = "".join(evidence_panel.split())

        self.assertIn("options: { auto?: boolean; compact?: boolean; poll?: boolean } = {}", hooks)
        self.assertIn("const poll = options.poll ?? false", hooks)
        self.assertIn("if (!poll) {\n        return false;\n      }", hooks)
        self.assertIn(
            "constrefresh=useRefreshStatus(refreshPage,Boolean(refreshPage),{",
            compact_evidence_panel,
        )
        self.assertIn("auto:true", compact_evidence_panel)
        self.assertIn("compact:true", compact_evidence_panel)
        self.assertIn("poll:false", compact_evidence_panel)

    def test_review_page_defers_historical_ledger(self) -> None:
        source = REVIEW_PAGE_PATH.read_text(encoding="utf-8")
        workspace_source = REVIEW_DECISION_WORKSPACE_PATH.read_text(encoding="utf-8")
        compact_workspace_source = "".join(workspace_source.split())
        history_source = REVIEW_HISTORY_PANELS_PATH.read_text(encoding="utf-8")

        self.assertIn('import dynamic from "next/dynamic"', source)
        self.assertIn('import("./review-decision-workspace").then(', source)
        self.assertIn("(module) => module.ReviewDecisionWorkspace", source)
        self.assertNotIn('import("./review-history-panels").then(', source)
        self.assertNotIn("function HistoricalShadowReplayGate()", source)
        self.assertNotIn("function HistoricalDecisionLedgerGate()", source)
        self.assertNotIn("function HistoricalDecisionLedger()", source)
        self.assertNotIn("function HistoricalShadowReplay()", source)
        self.assertNotIn("useDecisionLedgerRecent(", source)
        self.assertNotIn("useReviewShadowReplay(", source)

        self.assertIn('import("./review-history-panels").then(', workspace_source)
        self.assertIn("(module) => module.HistoricalShadowReplay", workspace_source)
        self.assertIn("(module) => module.HistoricalDecisionLedger", workspace_source)
        self.assertIn("function HistoricalShadowReplayGate()", workspace_source)
        self.assertIn("function HistoricalDecisionLedgerGate()", workspace_source)
        self.assertIn("const [shadowHistoryOpen, setShadowHistoryOpen] = useState(false)", workspace_source)
        self.assertIn("const [ledgerHistoryOpen, setLedgerHistoryOpen] = useState(false)", workspace_source)
        self.assertIn('data-testid="review-shadow-history-gate"', workspace_source)
        self.assertIn('data-testid="review-ledger-history-gate"', workspace_source)
        self.assertIn("<HistoricalShadowReplayGate />", workspace_source)
        self.assertIn("<HistoricalDecisionLedgerGate />", workspace_source)
        self.assertIn("shadowHistoryOpen?(<HistoricalShadowReplay/>", compact_workspace_source)
        self.assertIn("ledgerHistoryOpen?(<HistoricalDecisionLedger/>", compact_workspace_source)
        self.assertIn("展开后才加载历史影子样本组件和样本接口", workspace_source)
        self.assertIn("历史决策流水只在需要追溯时加载", workspace_source)
        self.assertNotIn("function HistoricalDecisionLedger()", workspace_source)
        self.assertNotIn("function HistoricalShadowReplay()", workspace_source)
        self.assertNotIn("useDecisionLedgerRecent(", workspace_source)
        self.assertNotIn("useReviewShadowReplay(", workspace_source)

        self.assertIn("export function HistoricalDecisionLedger()", history_source)
        self.assertIn("export function HistoricalShadowReplay()", history_source)
        self.assertIn("useDecisionLedgerRecent(10)", history_source)
        self.assertIn("useReviewShadowReplay()", history_source)
        self.assertIn("最近 10 条决策", history_source)
        self.assertNotIn('from "react"', history_source)
        self.assertNotIn("useDecisionLedgerRecent(10, { enabled: open })", history_source)
        self.assertNotIn("useReviewShadowReplay({ enabled: shadowOpen })", history_source)
        self.assertNotIn("const ledger = useDecisionLedgerRecent(10);", source)
        self.assertNotIn("const ledger = useDecisionLedgerRecent(10);", workspace_source)

    def test_review_shared_display_helpers_stay_deduplicated(self) -> None:
        workspace_source = REVIEW_DECISION_WORKSPACE_PATH.read_text(encoding="utf-8")
        history_source = REVIEW_HISTORY_PANELS_PATH.read_text(encoding="utf-8")
        learning_source = REVIEW_LEARNING_PATTERNS_PATH.read_text(encoding="utf-8")
        case_source = REVIEW_CASE_WORKSPACE_PATH.read_text(encoding="utf-8")
        utils_source = REVIEW_UTILS_PATH.read_text(encoding="utf-8")
        mini_fact_source = REVIEW_MINI_FACT_PATH.read_text(encoding="utf-8")

        for export_name in (
            "reviewStatusMeta",
            "reasonLabel",
            "reviewCaseHref",
            "pct",
            "ratePct",
            "countText",
            "shadowStatusMeta",
            "sampleGuardrailText",
        ):
            with self.subTest(export_name=export_name):
                self.assertIn(f"export function {export_name}(", utils_source)

        for component_source in (
            workspace_source,
            history_source,
            learning_source,
            case_source,
        ):
            with self.subTest(component="review-utils-consumer"):
                self.assertIn('from "./review-utils"', component_source)
                self.assertNotIn("const REVIEW_STATUS_META", component_source)
                self.assertNotIn("const REVIEW_REASON_LABELS", component_source)
                self.assertNotIn("function reviewStatusMeta(", component_source)
                self.assertNotIn("function reasonLabel(", component_source)
                self.assertNotIn("function reviewCaseHref(", component_source)
                self.assertNotIn("function pct(", component_source)
                self.assertNotIn("function ratePct(", component_source)
                self.assertNotIn("function countText(", component_source)
                self.assertNotIn("function shadowStatusMeta(", component_source)
                self.assertNotIn("function sampleGuardrailText(", component_source)

        self.assertIn("export function MiniFact(", mini_fact_source)
        self.assertIn('from "./review-mini-fact"', workspace_source)
        self.assertIn('from "./review-mini-fact"', history_source)
        self.assertNotIn("function MiniFact(", workspace_source)
        self.assertNotIn("function MiniFact(", history_source)

    def test_review_page_defers_learning_patterns_until_open(self) -> None:
        source = REVIEW_PAGE_PATH.read_text(encoding="utf-8")
        workspace_source = REVIEW_DECISION_WORKSPACE_PATH.read_text(encoding="utf-8")
        learning_source = REVIEW_LEARNING_PATTERNS_PATH.read_text(encoding="utf-8")

        self.assertNotIn('import("./review-learning-patterns").then(', source)
        self.assertNotIn("const LearningPatternsChunk = dynamic(", source)
        self.assertNotIn("function LearningPatternsSection(", source)
        self.assertNotIn("useDecisionLedgerLearningLoop", source)
        self.assertNotIn("useDecisionLedgerShadowCalibration", source)
        self.assertNotIn("function FactorLearningPanel(", source)
        self.assertNotIn("function ShadowCalibrationPanel(", source)

        self.assertIn('import("./review-learning-patterns").then(', workspace_source)
        self.assertIn("(module) => module.LearningPatterns", workspace_source)
        self.assertIn("const LearningPatternsChunk = dynamic(", workspace_source)
        self.assertIn("function LearningPatternsSection(", workspace_source)
        self.assertIn("<LearningPatternsSection data={calibration.data} />", workspace_source)
        self.assertIn("useDecisionLedgerCalibrationDetail(REVIEW_CALIBRATION_PARAMS", workspace_source)
        self.assertIn("enabled: open", workspace_source)
        self.assertIn("<LearningPatternsChunk data={detail.data} />", workspace_source)
        self.assertIn("二级校准工具按需加载", workspace_source)
        self.assertNotIn("useDecisionLedgerLearningLoop", workspace_source)
        self.assertNotIn("useDecisionLedgerShadowCalibration", workspace_source)
        self.assertNotIn("function FactorLearningPanel(", workspace_source)
        self.assertNotIn("function ShadowCalibrationPanel(", workspace_source)

        self.assertIn("export function LearningPatterns(", learning_source)
        self.assertIn("useDecisionLedgerLearningLoop({}, { enabled: factorLearningOpen })", learning_source)
        self.assertIn("const [shadowOpen, setShadowOpen] = useState(false)", learning_source)
        self.assertIn("useDecisionLedgerShadowCalibration({ enabled: shadowOpen })", learning_source)
        self.assertNotIn("useState(Boolean(data?.shadow_calibration))", learning_source)
        self.assertIn("function FactorLearningPanel(", learning_source)
        self.assertIn("function ShadowCalibrationPanel(", learning_source)

    def test_review_compact_calibration_defers_review_case_pattern_building(self) -> None:
        with patch.object(
            decision_ledger,
            "build_review_case_patterns",
            side_effect=AssertionError("compact calibration must not build review case pattern cards"),
        ):
            payload = decision_ledger.build_calibration_review(
                window_days=1,
                limit=1,
                include_shadow_calibration=False,
                include_review_case_patterns=False,
            )

        self.assertEqual(payload.get("review_case_patterns"), [])
        self.assertIn("patterns", payload.get("review_case_summary") or {})

    def test_review_calibration_routes_split_learning_pattern_hydration(self) -> None:
        calibration_payload = {
            "as_of": "2026-06-10",
            "window_days": 20,
            "from_date": "2026-05-21",
            "to_date": "2026-06-10",
            "overall": {},
            "review_workbench": {},
            "review_queue": [],
            "pending_reviews": [],
            "needs_review_count": 0,
            "reviewed_case_count": 0,
            "review_case_summary": {"total": 0, "attributed": 0, "patterns": 0},
            "errors": [],
        }
        detail_payload = {
            **calibration_payload,
            "by_lane": [],
            "by_action": [],
            "suggestion_cards": [],
            "review_case_patterns": [{"pattern_id": "p1", "sample_count": 2}],
        }

        with patch.object(
            app_module.decision_ledger,
            "build_calibration_review",
            return_value=calibration_payload,
        ) as build_calibration:
            response = self.client.get("/api/decision-ledger/calibration?compact=0")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(build_calibration.call_args.kwargs["include_shadow_calibration"])
        self.assertFalse(build_calibration.call_args.kwargs["include_review_case_patterns"])
        payload = response.json()
        self.assertTrue(payload.get("learning_patterns_deferred"))
        self.assertNotIn("review_case_patterns", payload)

        with patch.object(
            app_module.decision_ledger,
            "build_calibration_review",
            return_value=detail_payload,
        ) as build_detail:
            response = self.client.get("/api/decision-ledger/calibration-detail")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(build_detail.call_args.kwargs["include_shadow_calibration"])
        self.assertTrue(build_detail.call_args.kwargs["include_review_case_patterns"])
        self.assertEqual(len(response.json().get("review_case_patterns") or []), 1)

    def test_review_page_defers_case_workspace(self) -> None:
        source = REVIEW_PAGE_PATH.read_text(encoding="utf-8")
        workspace_source = REVIEW_CASE_WORKSPACE_PATH.read_text(encoding="utf-8")

        self.assertIn('import("./review-decision-workspace").then(', source)
        self.assertIn("(module) => module.ReviewDecisionWorkspace", source)
        self.assertIn("<ReviewDecisionWorkspace />", source)
        self.assertIn('import("./review-case-workspace").then(', source)
        self.assertIn("(module) => module.ReviewCaseWorkspace", source)
        self.assertIn("const ReviewCaseWorkspace = dynamic(", source)
        self.assertIn("<ReviewCaseWorkspace decisionId={selectedDecisionId} />", source)
        self.assertNotIn("useReview()", source)
        self.assertNotIn("useDecisionLedgerCalibration", source)
        self.assertNotIn("useAutoReviewDecisionLedgerCase", source)
        self.assertNotIn("useRunTask", source)
        self.assertNotIn("function DecisionLedgerHero(", source)
        self.assertNotIn("function ReviewQueue(", source)
        self.assertNotIn("function EvidenceStatus(", source)
        self.assertNotIn("function OutcomeEvaluatorAction(", source)
        self.assertNotIn("<MetricCard", source)
        self.assertNotIn("RiskAlert", source)
        self.assertNotIn("useDecisionLedgerReviewCase", source)
        self.assertNotIn("useGenerateDecisionLedgerAttributionDraft", source)
        self.assertNotIn("useSaveDecisionLedgerReviewCase", source)
        self.assertNotIn("DecisionLedgerAttributionDraft", source)
        self.assertNotIn("DecisionLedgerReviewCaseSavePayload", source)
        self.assertNotIn("const FALLBACK_PRIMARY_CAUSES", source)
        self.assertNotIn("function AttributionDraftCard", source)
        self.assertNotIn("function OptionGrid", source)

        self.assertIn("export function ReviewCaseWorkspace", workspace_source)
        self.assertIn("useDecisionLedgerReviewCase(decisionId, Boolean(decisionId))", workspace_source)
        self.assertIn("useGenerateDecisionLedgerAttributionDraft", workspace_source)
        self.assertIn("useSaveDecisionLedgerReviewCase", workspace_source)
        self.assertIn("function AttributionDraftCard", workspace_source)
        self.assertIn("function OptionGrid", workspace_source)
        self.assertIn("AI 预归因", workspace_source)

    def test_review_workspace_queries_do_not_silent_poll(self) -> None:
        hooks = WEB_HOOKS_PATH.read_text(encoding="utf-8")
        functions = (
            "useReview",
            "useReviewEvidence",
            "useDecisionLedgerCalibration",
            "useDecisionLedgerReviewCase",
        )

        for function_name in functions:
            with self.subTest(function_name=function_name):
                start = hooks.index(f"export function {function_name}")
                next_export = hooks.find("\nexport function ", start + 1)
                function_source = hooks[start: next_export if next_export != -1 else len(hooks)]
                self.assertIn("refetchOnWindowFocus: false", function_source)
                self.assertNotIn("refetchOnWindowFocus: true", function_source)
                self.assertNotIn("refetchInterval: 60_000", function_source)
                self.assertNotIn("refetchInterval: 120_000", function_source)
                if function_name != "useDecisionLedgerReviewCase":
                    self.assertIn("refetchInterval: false", function_source)
                if function_name == "useReview":
                    self.assertIn("options: { enabled?: boolean } = {}", function_source)
                    self.assertIn("enabled: options.enabled ?? true", function_source)

    def test_review_page_defers_research_panels_until_explicit_click(self) -> None:
        source = REVIEW_PAGE_PATH.read_text(encoding="utf-8")
        workspace_source = REVIEW_DECISION_WORKSPACE_PATH.read_text(encoding="utf-8")
        compact_evidence_source = "".join(
            workspace_source[
                workspace_source.index("function EvidenceStatus("):workspace_source.index("function HistoricalResearchSummary(")
            ].split()
        )
        evidence_source = workspace_source[
            workspace_source.index("function EvidenceStatus("):workspace_source.index("function HistoricalResearchSummary(")
        ]
        decision_workspace_source = workspace_source[
            workspace_source.index("export function ReviewDecisionWorkspace("):
        ]
        research_source = workspace_source[
            workspace_source.index("function HistoricalResearchSummary("):workspace_source.index("function CompactMetricPanel(")
        ]

        self.assertNotIn("function EvidenceStatus(", source)
        self.assertNotIn("function HistoricalResearchSummary(", source)
        self.assertNotIn("const review = useReview()", decision_workspace_source)
        self.assertNotIn("void review.refetch()", decision_workspace_source)
        self.assertNotIn("review.isFetching", decision_workspace_source)
        self.assertIn("<EvidenceStatus />", decision_workspace_source)
        self.assertNotIn("<EvidenceStatusreview=", "".join(decision_workspace_source.split()))
        self.assertIn("const review = useReview({}, { enabled: open });", evidence_source)
        self.assertIn("const reviewData = review.data", evidence_source)
        self.assertIn("按需加载", evidence_source)
        self.assertIn("onLoadResearch={() => void loadReviewResearch()}", evidence_source)
        self.assertIn("const payload = await api.getReviewResearch();", workspace_source)
        self.assertNotIn("includeResearch: true", workspace_source)
        self.assertNotIn("...payload", workspace_source)
        self.assertIn("加载研究拆解", research_source)
        self.assertIn("默认不随证据状态一起读取", research_source)
        self.assertIn("onClick={onLoadResearch}", research_source)
        self.assertIn("const [open, setOpen] = useState(false)", evidence_source)
        self.assertIn("const evidence = useReviewEvidence({}, { enabled: open });", evidence_source)
        self.assertIn("open={open}", evidence_source)
        self.assertIn("onToggle={(event) => setOpen(event.currentTarget.open)}", evidence_source)
        self.assertIn("{open ? (", evidence_source)
        self.assertIn("<ReviewEvidencePanel", evidence_source)
        self.assertIn("sources={evidence.data?.source_cards || []}", evidence_source)
        self.assertIn("artifacts={evidence.data?.artifacts || []}", evidence_source)
        self.assertIn("onRetry={() => void evidence.refetch()}", evidence_source)
        self.assertNotIn("review?.source_cards", evidence_source)
        self.assertNotIn("review?.artifacts", evidence_source)
        self.assertIn("{open?(", compact_evidence_source)
        self.assertNotIn("onOpen", evidence_source)
        self.assertNotIn("onLoadResearch()", compact_evidence_source)
        self.assertNotIn("onOpen={() => void loadReviewResearch()}", source)
        self.assertNotIn("onOpen={() => void loadReviewResearch()}", workspace_source)
        self.assertNotIn("onRetry={onOpen}", source)
        self.assertNotIn("onRetry={onOpen}", workspace_source)

    def test_review_page_defers_evidence_panel_code_until_open(self) -> None:
        source = REVIEW_PAGE_PATH.read_text(encoding="utf-8")
        workspace_source = REVIEW_DECISION_WORKSPACE_PATH.read_text(encoding="utf-8")
        evidence_panel = EVIDENCE_PANEL_PATH.read_text(encoding="utf-8")

        self.assertNotIn("const ReviewEvidencePanel = dynamic(", source)
        self.assertNotIn('import("@/components/evidence-panel").then(', source)
        self.assertNotIn("<ReviewEvidencePanel", source)
        self.assertNotIn('import { EvidencePanel } from "@/components/evidence-panel"', source)
        self.assertNotIn("<EvidencePanel", source)
        self.assertNotIn("useRefreshStatus", source)
        self.assertNotIn("useTriggerRefresh", source)
        self.assertNotIn("PreviewDrawer", source)
        self.assertNotIn('import { SourceCard } from "@/components/source-card"', source)

        self.assertIn("const ReviewEvidencePanel = dynamic(", workspace_source)
        self.assertIn('import("@/components/evidence-panel").then(', workspace_source)
        self.assertIn("(module) => module.EvidencePanel", workspace_source)
        self.assertIn("<ReviewEvidencePanel", workspace_source)
        self.assertNotIn('import { EvidencePanel } from "@/components/evidence-panel"', workspace_source)
        self.assertNotIn("<EvidencePanel", workspace_source)
        self.assertNotIn("useRefreshStatus", workspace_source)
        self.assertNotIn("useTriggerRefresh", workspace_source)
        self.assertNotIn("PreviewDrawer", workspace_source)
        self.assertNotIn('import { SourceCard } from "@/components/source-card"', workspace_source)

        self.assertIn("export function EvidencePanel(", evidence_panel)
        self.assertIn("useRefreshStatus(refreshPage, Boolean(refreshPage)", evidence_panel)
        self.assertIn("useTriggerRefresh(refreshPage, { stockCode })", evidence_panel)
        self.assertIn("PreviewDrawer", evidence_panel)
        self.assertIn("SourceCard", evidence_panel)

    def test_portfolio_page_defers_account_overview_tables(self) -> None:
        page_source = PORTFOLIO_PAGE_PATH.read_text(encoding="utf-8")
        page_compact_source = "".join(page_source.split())
        source = PORTFOLIO_WORKSPACE_PATH.read_text(encoding="utf-8")
        overview_source = PORTFOLIO_ACCOUNT_OVERVIEW_PATH.read_text(encoding="utf-8")
        holding_source = PORTFOLIO_HOLDING_WORKBENCH_PATH.read_text(encoding="utf-8")
        latest_source = PORTFOLIO_LATEST_DECISIONS_PATH.read_text(encoding="utf-8")
        ledger_source = PORTFOLIO_LEDGER_TOOLS_PATH.read_text(encoding="utf-8")
        manual_source = PORTFOLIO_MANUAL_WRITE_TOOLS_PATH.read_text(encoding="utf-8")
        utils_source = PORTFOLIO_UTILS_PATH.read_text(encoding="utf-8")

        self.assertIn('import("./portfolio-workspace").then(', page_compact_source)
        self.assertIn("module.PortfolioWorkspace", page_source)
        self.assertIn("function PortfolioPageFallback()", page_source)
        self.assertIn("return <PortfolioWorkspace />", page_source)
        self.assertNotIn("usePortfolioAccount", page_source)
        self.assertNotIn("usePortfolioHoldingReviews", page_source)
        self.assertNotIn("useRefreshPortfolioQuotes", page_source)
        self.assertNotIn("DeferredTrustBanner", page_source)
        self.assertNotIn("PortfolioAccountSummary", page_source)

        self.assertIn("export function PortfolioWorkspace()", source)
        self.assertIn('import("./portfolio-account-overview").then(', source)
        self.assertIn("(module) => module.PortfolioAccountSummary", source)
        self.assertIn("(module) => module.PortfolioAccountPositionTables", source)
        self.assertIn("(module) => module.PortfolioAccountActivityTables", source)
        self.assertIn("<PortfolioAccountSummary", source)
        self.assertIn("<PortfolioAccountPositionTables", source)
        self.assertIn("<PortfolioAccountActivityTables", source)
        self.assertIn("onSelectAction={handleAccountWorkflowAction}", source)
        self.assertIn("data={data}", source)
        self.assertIn("noFillItems={noFillItems}", source)
        self.assertNotIn("function ReadinessBanner(", source)
        self.assertNotIn("function AccountWorkflowCard(", source)
        self.assertNotIn("function PositionsTable(", source)
        self.assertNotIn("function FillsTable(", source)
        self.assertNotIn("function NoFillTable(", source)
        self.assertNotIn("function UnreconciledList(", source)
        self.assertNotIn("function formatMoney(", source)
        self.assertNotIn("function formatPercent(", source)
        self.assertNotIn("function stockDetailHref(", source)
        self.assertNotIn("function pnlTone(", source)
        self.assertNotIn('import { MetricCard, MetricSkeleton } from "@/components/metric-card"', source)
        self.assertNotIn("<MetricCard", source)
        self.assertNotIn("<MetricSkeleton", source)
        self.assertNotIn("<table", source)

        self.assertIn("export function PortfolioAccountSummary", overview_source)
        self.assertIn("export function PortfolioAccountPositionTables", overview_source)
        self.assertIn("export function PortfolioAccountActivityTables", overview_source)
        self.assertIn("function ReadinessBanner(", overview_source)
        self.assertIn("function AccountWorkflowCard(", overview_source)
        self.assertIn("function PositionsTable(", overview_source)
        self.assertIn("function FillsTable(", overview_source)
        self.assertIn("function NoFillTable(", overview_source)
        self.assertIn("function UnreconciledList(", overview_source)
        self.assertIn('from "./portfolio-utils"', overview_source)
        self.assertIn("export function formatMoney(", utils_source)
        self.assertIn("export function formatPercent(", utils_source)
        self.assertIn("export function stockDetailHref(", utils_source)
        self.assertIn("export function pnlTone(", utils_source)
        self.assertIn("export function numericValue(", utils_source)
        self.assertIn("export function suggestedSellQty(", utils_source)
        for component_source in (
            overview_source,
            holding_source,
            latest_source,
            ledger_source,
            manual_source,
            source,
        ):
            with self.subTest(component="portfolio-utils-consumer"):
                self.assertNotIn("function formatMoney(", component_source)
                self.assertNotIn("function formatPercent(", component_source)
                self.assertNotIn("function stockDetailHref(", component_source)
                self.assertNotIn("function pnlTone(", component_source)
                self.assertNotIn("function numericValue(", component_source)
                self.assertNotIn("function suggestedSellQty(", component_source)
        self.assertIn('import { MetricCard, MetricSkeleton } from "@/components/metric-card"', overview_source)
        self.assertIn("<MetricCard", overview_source)
        self.assertIn("<MetricSkeleton", overview_source)
        self.assertIn("<table", overview_source)
        self.assertIn("真实账户执行区", overview_source)
        self.assertIn("近期成交", overview_source)
        self.assertIn("未成交记录", overview_source)

    def test_portfolio_page_defers_latest_decision_ledger(self) -> None:
        source = PORTFOLIO_WORKSPACE_PATH.read_text(encoding="utf-8")
        compact_source = "".join(source.split())
        latest_source = PORTFOLIO_LATEST_DECISIONS_PATH.read_text(encoding="utf-8")

        self.assertIn('import("./portfolio-latest-decisions").then(', source)
        self.assertIn("(module) => module.PortfolioLatestDecisions", source)
        self.assertIn("data-testid=\"portfolio-latest-decisions-gate\"", source)
        self.assertIn("latestDecisionsOpened ? (", source)
        self.assertIn(
            "<PortfolioLatestDecisionspositions={data.account.open_positions}/>",
            compact_source,
        )
        self.assertIn("默认不读取DecisionLedgerrecent", compact_source)
        self.assertNotIn("function PositionLatestDecisionPanel", source)
        self.assertNotIn("useDecisionLedgerRecent(", source)
        self.assertNotIn("DecisionLedgerCompactRecord", source)
        self.assertNotIn("const ledger = useDecisionLedgerRecent(60);", source)

        self.assertIn("export function PortfolioLatestDecisions", latest_source)
        self.assertIn("codes: positionCodes", latest_source)
        self.assertIn("latestPerCode: true", latest_source)
        self.assertIn("{ enabled: Boolean(positionCodes.length) }", latest_source)
        self.assertIn("stockCodeKey(pos.code)", latest_source)
        self.assertIn("data-testid=\"portfolio-latest-decisions-panel\"", latest_source)
        self.assertNotIn("<details", latest_source)
        self.assertNotIn("useState", latest_source)
        self.assertIn("DecisionLedgerCompactRecord", latest_source)
        self.assertNotIn("useDecisionLedgerRecent(60", latest_source)
        self.assertNotIn("const ledger = useDecisionLedgerRecent(60);", latest_source)

    def test_portfolio_page_lazy_loads_research_manager(self) -> None:
        source = PORTFOLIO_WORKSPACE_PATH.read_text(encoding="utf-8")
        compact_source = "".join(source.split())
        research_source = PORTFOLIO_RESEARCH_UNIVERSE_PATH.read_text(encoding="utf-8")

        self.assertIn('import dynamic from "next/dynamic"', source)
        self.assertIn('import("./portfolio-research-universe").then(', source)
        self.assertIn("(module) => module.PortfolioResearchUniverse", source)
        self.assertIn("const [researchUniverseOpened, setResearchUniverseOpened] = useState(false)", source)
        self.assertIn("open={researchUniverseOpened}", source)
        self.assertIn(
            "onToggle={(event)=>setResearchUniverseOpened(event.currentTarget.open)}",
            compact_source,
        )
        self.assertIn("researchUniverseOpened?(<PortfolioResearchUniverse/>", compact_source)
        self.assertIn("按需加载", source)
        self.assertNotIn("if (event.currentTarget.open)", source)
        self.assertNotIn("useWatchlist({ enabled: researchUniverseOpened })", source)
        self.assertNotIn("<WatchlistManagerPanel />", source)
        self.assertNotIn("<StockCard key={stock.code} stock={stock} />", source)
        self.assertNotIn('import("@/components/watchlist-manager-panel")', source)
        self.assertNotIn('import("@/components/stock-card")', source)
        self.assertNotIn('import { WatchlistManagerPanel } from "@/components/watchlist-manager-panel";', source)
        self.assertNotIn('import { StockCard } from "@/components/stock-card";', source)
        self.assertNotIn("useWatchlist()", source)

        self.assertIn("export function PortfolioResearchUniverse", research_source)
        self.assertIn('import dynamic from "next/dynamic"', research_source)
        self.assertIn('import("@/components/watchlist-manager-panel").then(', research_source)
        self.assertIn("(module) => module.WatchlistManagerPanel", research_source)
        self.assertIn("const WatchlistManagerPanel = dynamic(", research_source)
        self.assertIn("useWatchlist()", research_source)
        self.assertIn("const [managerOpen, setManagerOpen] = useState(false)", research_source)
        self.assertIn("open={managerOpen}", research_source)
        self.assertIn("onToggle={(event) => setManagerOpen(event.currentTarget.open)}", research_source)
        self.assertIn("managerOpen ? (", research_source)
        self.assertIn("管理研究名单", research_source)
        self.assertIn("普通查看研究名单不会触发管理接口", research_source)
        self.assertNotIn('import { WatchlistManagerPanel } from "@/components/watchlist-manager-panel";', research_source)
        self.assertIn('import { StockCard } from "@/components/stock-card";', research_source)
        self.assertIn("<WatchlistManagerPanel />", research_source)
        self.assertIn("<StockCard key={stock.code} stock={stock} />", research_source)

    def test_portfolio_page_defers_ledger_tools(self) -> None:
        source = PORTFOLIO_WORKSPACE_PATH.read_text(encoding="utf-8")
        compact_source = "".join(source.split())
        ledger_source = PORTFOLIO_LEDGER_TOOLS_PATH.read_text(encoding="utf-8")
        manual_write_source = PORTFOLIO_MANUAL_WRITE_TOOLS_PATH.read_text(encoding="utf-8")
        decision_writeback_source = PORTFOLIO_DECISION_WRITEBACK_PATH.read_text(encoding="utf-8")
        form_utils_source = PORTFOLIO_FORM_UTILS_PATH.read_text(encoding="utf-8")

        self.assertIn('import("./portfolio-ledger-tools").then(', source)
        self.assertIn("(module) => module.PortfolioLedgerTools", source)
        self.assertIn("const [ledgerToolsOpened, setLedgerToolsOpened] = useState(false)", source)
        self.assertIn("data-testid=\"portfolio-ledger-tools-gate\"", source)
        self.assertIn("账本写入工具按需加载", source)
        self.assertIn("加载账本工具", source)
        self.assertIn("isLedgerToolTarget(hashTarget)", source)
        self.assertIn("setPendingLedgerTarget(hashTarget)", source)
        self.assertIn("function handleAccountWorkflowAction(", source)
        self.assertIn("onSelectAction={handleAccountWorkflowAction}", source)
        self.assertIn("usePortfolioAccountHistory", source)
        self.assertIn("const accountHistory = usePortfolioAccountHistory({", source)
        self.assertIn("enabled: Boolean(ledgerToolsOpened)", source)
        self.assertIn("queryKey: queryKeys.portfolioAccountHistory", source)
        self.assertIn("history: true", source)
        self.assertIn("const [accountRefreshing, setAccountRefreshing] = useState(false)", source)
        self.assertIn("async function refreshAccountBook()", source)
        self.assertIn("const refreshTasks: Array<Promise<unknown>>", source)
        self.assertIn("await Promise.allSettled(refreshTasks)", source)
        self.assertIn("queryFn: () => api.getPortfolioHoldingReviews({ fresh: true })", source)
        self.assertIn("disabled={accountBookRefreshing}", source)
        self.assertIn("className={accountBookRefreshing ? \"animate-spin\" : \"\"}", source)
        self.assertIn("onClick={() => void refreshAccountBook()}", source)
        self.assertIn("正在补齐模式切换和对账历史", source)
        self.assertIn("账本历史暂不可用", source)
        self.assertIn("data&&ledgerToolsOpened?(<>", compact_source)
        self.assertIn(
            "<PortfolioLedgerToolsdata={accountHistory.data||data}defaultTradeDate={defaultTradeDate}/>",
            compact_source,
        )
        self.assertIn("onClick={()=>setLedgerToolsOpened(true)}", compact_source)
        self.assertIn('import("./portfolio-manual-write-tools").then(', source)
        self.assertIn("const [manualWriteToolsOpened, setManualWriteToolsOpened] = useState(false)", source)
        self.assertIn("data-testid=\"portfolio-manual-write-tools-gate\"", source)
        self.assertIn("手动写入工具按需加载", source)
        self.assertIn("<PortfolioFillForm", source)
        self.assertIn("<PortfolioIdentityCorrectionForm", source)
        self.assertIn('import("./portfolio-decision-writeback").then(', source)
        self.assertIn("const [decisionWritebackOpened, setDecisionWritebackOpened] = useState(false)", source)
        self.assertIn("data-testid=\"portfolio-decision-writeback-gate\"", source)
        self.assertIn("决策执行回写按需加载", source)
        self.assertIn("加载回写", source)
        self.assertIn("<PortfolioDecisionWritebackPanel", source)
        self.assertIn("noFillIntents={noFillItems}", source)
        self.assertIn("onWritebackSuccess={({ noFillItem })", source)
        self.assertIn(
            "if (hasOpenPositions && holdingReviewsEnabled) {\n                    void holdingReviews.refetch();\n                  }",
            source,
        )
        self.assertNotIn("void portfolio.refetch();\n                  void holdingReviews.refetch();", source)
        self.assertNotIn("function LedgerForms(", source)
        self.assertNotIn("function ModeSwitch(", source)
        self.assertNotIn("function CashAdjustForm(", source)
        self.assertNotIn("function ReconcileForm(", source)
        self.assertNotIn("function FillForm(", source)
        self.assertNotIn("function IdentityCorrectionForm(", source)
        self.assertNotIn("function DecisionWritebackPanel(", source)
        self.assertNotIn("function WritebackOutcomeCard(", source)
        self.assertNotIn("function FillRiskNotice(", source)
        self.assertNotIn("useSetPortfolioMode", source)
        self.assertNotIn("useRecordPortfolioCash", source)
        self.assertNotIn("useRecordPortfolioReconcile", source)
        self.assertNotIn("useAmendPortfolioHoldingIdentity", source)
        self.assertNotIn("useRecordPortfolioNoFill", source)
        self.assertNotIn("useUpdateTodayActionDecision", source)
        self.assertNotIn("useTodayActions", source)
        self.assertNotIn("new URLSearchParams", source)
        self.assertNotIn("setSearchParams", source)
        self.assertNotIn("outcomeStorageKey", source)
        self.assertNotIn("decisionLabel", source)
        self.assertNotIn("WritebackContext", source)
        self.assertNotIn("WritebackOutcome", source)
        self.assertNotIn("persistedOutcome", source)
        self.assertNotIn("storedOutcome", source)
        self.assertNotIn("const MODE_OPTIONS", source)
        self.assertNotIn("AccountMode", source)

        self.assertIn("export function PortfolioLedgerTools", ledger_source)
        self.assertIn("function ModeSwitch(", ledger_source)
        self.assertIn("function CashAdjustForm(", ledger_source)
        self.assertIn("function ReconcileForm(", ledger_source)
        self.assertIn('from "./portfolio-form-utils"', ledger_source)
        self.assertIn("useSetPortfolioMode", ledger_source)
        self.assertIn("useRecordPortfolioCash", ledger_source)
        self.assertIn("useRecordPortfolioReconcile", ledger_source)
        self.assertIn("const MODE_OPTIONS", ledger_source)
        self.assertNotIn("useRecordPortfolioFill", ledger_source)
        self.assertNotIn("DecisionWritebackPanel", ledger_source)
        self.assertNotIn("function formStatusTone(", ledger_source)

        self.assertIn("export function FillForm", manual_write_source)
        self.assertIn("export function IdentityCorrectionForm", manual_write_source)
        self.assertIn('from "./portfolio-form-utils"', manual_write_source)
        self.assertIn("useRecordPortfolioFill", manual_write_source)
        self.assertIn("useAmendPortfolioHoldingIdentity", manual_write_source)
        self.assertNotIn("function FillRiskNotice(", manual_write_source)
        self.assertNotIn("function formStatusTone(", manual_write_source)

        self.assertIn("export function DecisionWritebackPanel", decision_writeback_source)
        self.assertIn('from "./portfolio-form-utils"', decision_writeback_source)
        self.assertIn("function readWritebackContext", decision_writeback_source)
        self.assertIn("new URLSearchParams(window.location.search)", decision_writeback_source)
        self.assertIn("useTodayActions", decision_writeback_source)
        self.assertIn("enabled: Boolean(context?.intentKey)", decision_writeback_source)
        self.assertIn("outcomeStorageKey", decision_writeback_source)
        self.assertIn("useRecordPortfolioFill", decision_writeback_source)
        self.assertIn("useRecordPortfolioNoFill", decision_writeback_source)
        self.assertIn("useUpdateTodayActionDecision", decision_writeback_source)
        self.assertIn("function WritebackOutcomeCard", decision_writeback_source)
        self.assertNotIn("function FillRiskNotice(", decision_writeback_source)
        self.assertIn("const WRITEBACK_ACTIONS", decision_writeback_source)

        self.assertIn("export function formStatusTone(", form_utils_source)
        self.assertIn("export function FillRiskNotice(", form_utils_source)
        self.assertIn("注意：这里会写入真实账户账本。", form_utils_source)

    def test_portfolio_account_queries_do_not_silent_poll(self) -> None:
        hooks = WEB_HOOKS_PATH.read_text(encoding="utf-8")
        functions = ("usePortfolioAccount", "usePortfolioAccountHistory", "usePortfolioHoldingReviews")

        for function_name in functions:
            with self.subTest(function_name=function_name):
                start = hooks.index(f"export function {function_name}")
                next_export = hooks.find("\nexport function ", start + 1)
                function_source = hooks[start: next_export if next_export != -1 else len(hooks)]
                self.assertIn("refetchOnWindowFocus: false", function_source)
                self.assertNotIn("refetchOnWindowFocus: true", function_source)
                self.assertNotIn("refetchInterval: 60_000", function_source)
                if function_name in {"usePortfolioAccount", "usePortfolioAccountHistory"}:
                    self.assertIn("refetchInterval: false", function_source)
                if function_name == "usePortfolioAccountHistory":
                    self.assertIn("api.getPortfolioAccount({ history: true })", function_source)

    def test_portfolio_page_does_not_auto_refresh_quotes_on_open(self) -> None:
        source = PORTFOLIO_WORKSPACE_PATH.read_text(encoding="utf-8")
        compact_source = "".join(source.split())
        workbench_source = PORTFOLIO_HOLDING_WORKBENCH_PATH.read_text(encoding="utf-8")

        self.assertIn("const refreshQuotes = useRefreshPortfolioQuotes();", source)
        self.assertIn("onClick={() => refreshQuotes.mutate()}", source)
        self.assertIn('import("./portfolio-holding-workbench").then(', source)
        self.assertIn("(module) => module.PortfolioHoldingWorkbench", source)
        self.assertIn("const [holdingReviewsEnabled, setHoldingReviewsEnabled] = useState(false)", source)
        self.assertIn("const hasOpenPositions = Boolean(data?.account.open_positions.length)", source)
        self.assertIn(
            "usePortfolioHoldingReviews({enabled:Boolean(hasOpenPositions&&holdingReviewsEnabled),",
            compact_source,
        )
        self.assertIn("data-testid=\"portfolio-holding-reviews-gate\"", source)
        self.assertIn("持仓复核按需加载", source)
        self.assertIn("加载持仓复核", source)
        self.assertIn("onClick={() => setHoldingReviewsEnabled(true)}", source)
        self.assertIn("data&&(!hasOpenPositions||holdingReviewsEnabled)?(", compact_source)
        self.assertIn("<PortfolioHoldingWorkbench", source)
        self.assertNotIn("enabled: Boolean(data?.account.open_positions.length)", source)
        self.assertNotIn("function HoldingActionWorkbench", source)
        self.assertNotIn("function HoldingPlanCard", source)
        self.assertNotIn("AI 证据归因", source)
        self.assertNotIn("aiVerdictTone", source)
        self.assertNotIn("aiStrengthTone", source)
        self.assertNotIn("aiActionLabel", source)
        self.assertNotIn("positionPlanSourceLabel", source)
        self.assertNotIn("autoQuoteRefreshAttempted", source)
        self.assertNotIn("quoteAutoRefreshCandidate", source)
        self.assertNotIn("shouldDelayHoldingReviews", source)
        self.assertNotIn("refreshQuotesMutate()", source)
        self.assertNotIn("setAutoQuoteRefreshAttempted(true)", source)

        self.assertIn("export function PortfolioHoldingWorkbench", workbench_source)
        self.assertIn("function HoldingPlanCard", workbench_source)
        self.assertIn("Prism 个股剧本", workbench_source)
        self.assertIn("AI 证据归因", workbench_source)
        self.assertIn("持仓动作暂不可用", workbench_source)

    def test_stock_page_defers_watchlist_manager_status(self) -> None:
        page_source = STOCK_PAGE_PATH.read_text(encoding="utf-8")
        page_compact_source = "".join(page_source.split())
        source = STOCK_PROFILE_WORKSPACE_PATH.read_text(encoding="utf-8")
        compact_source = "".join(source.split())
        actions_source = STOCK_WATCHLIST_ACTIONS_PATH.read_text(encoding="utf-8")
        hooks = WEB_HOOKS_PATH.read_text(encoding="utf-8")

        self.assertIn('import("./stock-profile-workspace").then(', page_compact_source)
        self.assertIn("module.StockProfileWorkspace", page_source)
        self.assertIn("function StockProfilePageFallback()", page_source)
        self.assertIn("return <StockProfileWorkspace />", page_source)
        self.assertNotIn("useStockProfileDetail", page_source)
        self.assertNotIn("useStockProfileFormalData", page_source)
        self.assertNotIn("useAsk", page_source)
        self.assertNotIn("DeferredTrustBanner", page_source)
        self.assertNotIn("StockDecisionHeroPanels", page_source)

        self.assertIn("export function StockProfileWorkspace()", source)
        self.assertIn("const StockWatchlistActions = dynamic<StockWatchlistActionsProps>", source)
        self.assertIn('import("./stock-watchlist-actions").then(', source)
        self.assertIn("data-testid=\"stock-watchlist-actions-gate\"", source)
        self.assertIn("const [watchlistActionsOpen, setWatchlistActionsOpen] = useState(false)", source)
        self.assertIn(
            'constdetailEnabled=Boolean(code)&&activeTab!=="追问"&&Boolean(profileSummary.data||profileSummary.isError);',
            compact_source,
        )
        self.assertIn("consttodayActionEnabled=Boolean(code)&&Boolean(detail);", compact_source)
        self.assertIn(
            "useStockProfileTodayAction(code,{enabled:todayActionEnabled,});",
            compact_source,
        )
        self.assertNotIn('const detailEnabled = Boolean(code) && activeTab !== "追问";', source)
        self.assertNotIn(
            "useStockProfileTodayAction(code,{enabled:Boolean(code),});",
            compact_source,
        )
        self.assertIn("onClick={() => setWatchlistActionsOpen(true)}", source)
        self.assertIn("名单状态待同步", source)
        self.assertIn("<StockWatchlistActions", source)
        self.assertNotIn("onSettled={refetchProfileSurface}", source)
        self.assertNotIn("useWatchlistManager", source)
        self.assertNotIn("useAddWatchlistStock", source)
        self.assertNotIn("useArchiveWatchlistStock", source)
        self.assertNotIn("useRestoreWatchlistStock", source)
        self.assertNotIn("managerEnabled", source)
        self.assertNotIn("managerUnavailable", source)

        self.assertIn("export function StockWatchlistActions", actions_source)
        self.assertIn("useWatchlistManager({ enabled: true })", actions_source)
        self.assertIn("useAddWatchlistStock", actions_source)
        self.assertIn("useArchiveWatchlistStock", actions_source)
        self.assertIn("useRestoreWatchlistStock", actions_source)
        self.assertIn("名单同步中", actions_source)
        self.assertNotIn("onSettled:", actions_source)
        self.assertNotIn("onSettled,", actions_source)
        self.assertIn("export function useWatchlistManager(options: { enabled?: boolean } = {})", hooks)
        self.assertIn("enabled: options.enabled ?? true", hooks)
        self.assertIn("refetchInterval: false", hooks[hooks.index("export function useWatchlistManager"):])
        self.assertIn("refetchOnWindowFocus: false", hooks[hooks.index("export function useWatchlistManager"):])
        self.assertNotIn("refetchInterval: (options.enabled ?? true) ? 60_000 : false", hooks)

    def test_stock_page_defers_decision_workspace_presentation(self) -> None:
        source = STOCK_PROFILE_WORKSPACE_PATH.read_text(encoding="utf-8")
        compact_source = "".join(source.split())
        workspace_source = STOCK_DECISION_WORKSPACE_PATH.read_text(encoding="utf-8")

        self.assertIn("const StockDecisionHeroPanels = dynamic<StockDecisionHeroPanelsProps>", source)
        self.assertIn("const StockDecisionTabWorkspace = dynamic<StockDecisionTabWorkspaceProps>", source)
        self.assertIn('import("./stock-decision-workspace").then(', source)
        self.assertIn("(module) => module.StockDecisionHeroPanels", source)
        self.assertIn("(module) => module.StockDecisionTabWorkspace", source)
        self.assertIn("<StockDecisionHeroPanels", source)
        self.assertIn("<StockDecisionTabWorkspace", source)
        self.assertIn("<StockDecisionHeroPanelscode={code}stockName={stockName}", compact_source)
        self.assertIn("<StockDecisionTabWorkspacedetail={detail}askCase={askCase}", compact_source)
        self.assertIn("onLoadDeferredInsights={loadDeferredInsights}", source)
        self.assertIn('onContinueAsk={() => setActiveTab("追问")}', source)
        self.assertNotIn("function DecisionLayerCard(", source)
        self.assertNotIn("function rowValueByLabel(", source)
        self.assertNotIn("function todayActionStatusLabel(", source)
        self.assertNotIn("function isObservationDecision(", source)
        self.assertNotIn("<MetricCard", source)
        self.assertNotIn("<DataCard", source)
        self.assertNotIn("Ask 主结论", source)
        self.assertNotIn("执行循环", source)
        self.assertNotIn("历史可信度按需加载", source)
        self.assertNotIn('import { MetricCard, MetricSkeleton } from "@/components/metric-card"', source)
        self.assertNotIn("ClipboardList", source)

        self.assertIn("export function StockDecisionHeroPanels", workspace_source)
        self.assertIn("export function StockDecisionTabWorkspace", workspace_source)
        self.assertIn("function DecisionLayerCard(", workspace_source)
        self.assertIn("function rowValueByLabel(", workspace_source)
        self.assertIn("function todayActionStatusLabel(", workspace_source)
        self.assertIn("function isObservationDecision(", workspace_source)
        self.assertIn("<MetricCard", workspace_source)
        self.assertIn("<DataCard", workspace_source)
        self.assertIn("Ask 主结论", workspace_source)
        self.assertIn("执行循环", workspace_source)
        self.assertIn("历史可信度按需加载", workspace_source)
        self.assertIn("StockDecisionSupportPanels", workspace_source)
        self.assertIn("StockDecisionCanonicalSummary", workspace_source)
        self.assertIn('import("./stock-learning-panels").then(', workspace_source)
        self.assertIn("StockLearningScorecardPanel", workspace_source)
        self.assertNotIn("StockLearningMemoryPanel", workspace_source)
        self.assertNotIn("detail.learning_memories", workspace_source)
        self.assertNotIn("StockDecisionWorkspaceSkeleton", workspace_source)
        self.assertNotIn('import { LearningMemoryPreview } from "@/components/learning-memory"', workspace_source)

    def test_stock_page_defers_full_formal_data_until_click(self) -> None:
        source = STOCK_PROFILE_WORKSPACE_PATH.read_text(encoding="utf-8")
        compact_source = "".join(source.split())
        formal_source = STOCK_FORMAL_PANELS_PATH.read_text(encoding="utf-8")

        self.assertIn('import dynamic from "next/dynamic"', source)
        self.assertIn('import type { FormalSectionKey } from "./stock-formal-panels"', source)
        self.assertIn('import("./stock-formal-panels").then(', source)
        self.assertIn("(module) => module.FormalDataSummaryPanel", source)
        self.assertIn("(module) => module.FormalDataSnapshotPanel", source)
        self.assertIn("const [formalFullEnabled, setFormalFullEnabled] = useState(false)", source)
        self.assertIn(
            'const[formalSectionsEnabled,setFormalSectionsEnabled]=useState<Record<FormalSectionKey,boolean>>',
            compact_source,
        )
        self.assertIn('const formalSummaryQuery = useStockProfileFormalDataSection(code, "summary"', source)
        self.assertIn('const formalProfileQuery = useStockProfileFormalDataSection(code, "profile"', source)
        self.assertIn('const formalRiskQuery = useStockProfileFormalDataSection(code, "risk"', source)
        self.assertIn('const formalSourcesQuery = useStockProfileFormalDataSection(code, "sources"', source)
        self.assertIn("const formalDataQuery = useStockProfileFormalData(code", source)
        self.assertIn('enabled: activeTab === "证据"', source)
        self.assertIn('enabled: activeTab === "证据" && formalSectionsEnabled.profile', source)
        self.assertIn('enabled: activeTab === "证据" && formalSectionsEnabled.risk', source)
        self.assertIn('enabled: activeTab === "证据" && formalSectionsEnabled.sources', source)
        self.assertIn('enabled: activeTab === "证据" && formalFullEnabled', source)
        self.assertIn("function loadFormalSection(section: FormalSectionKey)", source)
        self.assertIn("function loadFormalFullData()", source)
        self.assertIn("onLoadSection={loadFormalSection}", source)
        self.assertIn("onLoadFull={loadFormalFullData}", source)
        self.assertNotIn("function FormalDataSummaryPanel(", source)
        self.assertNotIn("function FormalDataSnapshotPanel(", source)
        self.assertNotIn("function recordField(", source)
        self.assertNotIn('useStockProfileFormalDataSection(code,"profile",{enabled:activeTab==="证据"})', compact_source)
        self.assertNotIn('useStockProfileFormalDataSection(code,"risk",{enabled:activeTab==="证据"})', compact_source)
        self.assertNotIn('useStockProfileFormalDataSection(code,"sources",{enabled:activeTab==="证据"})', compact_source)
        self.assertNotIn("setFormalFullEnabled(true), 1200", source)

        self.assertIn('export type FormalSectionKey = "profile" | "risk" | "sources"', formal_source)
        self.assertIn("export function FormalDataSummaryPanel(", formal_source)
        self.assertIn("export function FormalDataSnapshotPanel(", formal_source)
        self.assertIn("function recordField(", formal_source)
        self.assertIn("公司画像", formal_source)
        self.assertIn("风险摘要", formal_source)
        self.assertIn("来源索引", formal_source)
        self.assertIn("完整档案", formal_source)

        refresh_start = source.index("function refetchProfileSurface()")
        refresh_end = source.index("function loadDeferredInsights()", refresh_start)
        refresh_source = source[refresh_start:refresh_end]
        self.assertIn('if (activeTab === "证据")', refresh_source)
        self.assertIn("void formalSummaryQuery.refetch();", refresh_source)
        self.assertIn("if (formalSectionsEnabled.profile)", refresh_source)
        self.assertIn("void formalProfileQuery.refetch();", refresh_source)
        self.assertIn("if (formalSectionsEnabled.risk)", refresh_source)
        self.assertIn("void formalRiskQuery.refetch();", refresh_source)
        self.assertIn("if (formalSectionsEnabled.sources)", refresh_source)
        self.assertIn("void formalSourcesQuery.refetch();", refresh_source)
        self.assertIn("if (formalFullEnabled)", refresh_source)
        self.assertIn("void formalDataQuery.refetch();", refresh_source)
        self.assertNotIn("setFormalSectionsEnabled", refresh_source)
        self.assertNotIn("setFormalFullEnabled(true)", refresh_source)

    def test_stock_page_defers_historical_insights_until_click(self) -> None:
        source = STOCK_PROFILE_WORKSPACE_PATH.read_text(encoding="utf-8")
        compact_source = "".join(source.split())
        workspace_source = STOCK_DECISION_WORKSPACE_PATH.read_text(encoding="utf-8")
        compact_workspace_source = "".join(workspace_source.split())
        timeline_source = STOCK_DECISION_TIMELINE_PATH.read_text(encoding="utf-8")
        learning_source = STOCK_LEARNING_PANELS_PATH.read_text(encoding="utf-8")

        self.assertIn("const [deferredInsightsEnabled, setDeferredInsightsEnabled] = useState(false)", source)
        self.assertIn('import("./stock-decision-timeline").then(', source)
        self.assertIn("(module) => module.StockDecisionTimelinePanel", source)
        self.assertIn('decisionLocked||(activeTab==="决策"&&deferredInsightsEnabled)', compact_source)
        self.assertNotIn('activeTab==="证据"||deferredInsightsEnabled', compact_source)
        self.assertIn("function loadDeferredInsights()", source)
        self.assertIn("<StockDecisionTabWorkspace", source)
        self.assertIn("onLoadDeferredInsights={loadDeferredInsights}", source)
        self.assertIn("<StockDecisionTimelinePanelcode={code}enabled={deferredInsightsEnabled}/>", compact_source)
        self.assertNotIn('import("./stock-learning-panels").then(', source)
        self.assertNotIn("(module) => module.StockLearningMemoryPanel", source)
        self.assertNotIn("(module) => module.StockLearningScorecardPanel", source)
        self.assertNotIn("历史可信度按需加载", source)
        self.assertNotIn("加载历史洞察", source)
        self.assertNotIn("<StockLearningMemoryPanel", source)
        self.assertNotIn("setDeferredInsightsEnabled(true), 1400", source)
        self.assertNotIn("function StockDecisionTimelinePanel(", source)
        self.assertNotIn("function LearningScorecardPanel(", source)
        self.assertNotIn('import { LearningMemoryPreview } from "@/components/learning-memory"', source)
        self.assertNotIn("useDecisionLedgerStock", source)
        self.assertNotIn("DecisionLedgerCompactRecord", source)

        self.assertIn('import("./stock-learning-panels").then(', workspace_source)
        self.assertIn("(module) => module.StockLearningScorecardPanel", workspace_source)
        self.assertIn("历史可信度按需加载", workspace_source)
        self.assertIn("加载历史洞察", workspace_source)
        self.assertNotIn("(module) => module.StockLearningMemoryPanel", workspace_source)
        self.assertNotIn("detail.learning_memories", workspace_source)
        self.assertNotIn("<StockLearningMemoryPanel", workspace_source)

        refresh_start = source.index("function refetchProfileSurface()")
        refresh_end = source.index("function loadDeferredInsights()", refresh_start)
        refresh_source = source[refresh_start:refresh_end]
        self.assertIn('if (decisionLocked || (activeTab === "决策" && deferredInsightsEnabled))', refresh_source)
        self.assertNotIn('if (activeTab === "证据" || deferredInsightsEnabled)', refresh_source)
        self.assertNotIn("setDeferredInsightsEnabled(true)", refresh_source)

        self.assertIn("export function StockDecisionTimelinePanel(", timeline_source)
        self.assertIn("useDecisionLedgerStock(code, enabled)", timeline_source)
        self.assertIn("DecisionLedgerCompactRecord", timeline_source)
        self.assertIn("Decision Ledger 历史", timeline_source)

        self.assertNotIn("export function StockLearningMemoryPanel(", learning_source)
        self.assertIn("export function StockLearningScorecardPanel(", learning_source)
        self.assertIn('import { LearningMemoryPreview } from "@/components/learning-memory"', learning_source)
        self.assertIn("历史提醒", learning_source)
        self.assertIn("历史可信度只作学习参考", learning_source)
        self.assertIn("const memories = scorecard.learning_memories || [];", learning_source)
        self.assertNotIn("<StockLearningMemoryPanel", learning_source)
        self.assertIn("<LearningMemoryPreview memories={memories} limit={3} />", learning_source)
        self.assertIn("learning_memories?: ReviewLearningMemory[];", WEB_TYPES_PATH.read_text(encoding="utf-8"))

    def test_stock_page_defers_decision_support_details(self) -> None:
        source = STOCK_PROFILE_WORKSPACE_PATH.read_text(encoding="utf-8")
        workspace_source = STOCK_DECISION_WORKSPACE_PATH.read_text(encoding="utf-8")
        compact_workspace_source = "".join(workspace_source.split())
        support_source = STOCK_DECISION_SUPPORT_PATH.read_text(encoding="utf-8")
        ask_workspace = STOCK_ASK_WORKSPACE_PATH.read_text(encoding="utf-8")

        self.assertIn("const StockDecisionHeroPanels = dynamic<StockDecisionHeroPanelsProps>", source)
        self.assertIn("const StockDecisionTabWorkspace = dynamic<StockDecisionTabWorkspaceProps>", source)
        self.assertIn('import("./stock-decision-workspace").then(', source)
        self.assertIn("(module) => module.StockDecisionHeroPanels", source)
        self.assertIn("(module) => module.StockDecisionTabWorkspace", source)
        self.assertIn("<StockDecisionHeroPanels", source)
        self.assertIn("<StockDecisionTabWorkspace", source)
        self.assertNotIn("const StockDecisionSupportPanels = dynamic<StockDecisionSupportPanelsProps>", source)
        self.assertNotIn("const StockDecisionCanonicalSummary =", source)
        self.assertNotIn('import("./stock-decision-support").then(', source)
        self.assertNotIn("<StockDecisionSupportPanels", source)
        self.assertNotIn("<StockDecisionCanonicalSummary", source)
        self.assertNotIn("function TradingAvailabilityBar(", source)
        self.assertNotIn("function DataFreshnessGate(", source)
        self.assertNotIn("function ObservationDecisionBlocks(", source)
        self.assertNotIn("function DecisionSummary(", source)
        self.assertNotIn("function evidenceSourceSummary(", source)
        self.assertNotIn("function evidenceSupportItems(", source)
        self.assertNotIn("function evidenceRiskItems(", source)
        self.assertNotIn("function uniqueTexts(", source)
        self.assertNotIn("readinessModeCopy", source)
        self.assertNotIn("refreshTaskCopy", source)
        self.assertNotIn("System Environment", source)
        self.assertNotIn("不使用当前页面内容判断今天是否交易", source)
        self.assertNotIn("为什么入池", source)
        self.assertNotIn("弱结论", source)

        self.assertIn("StockDecisionSupportPanels", workspace_source)
        self.assertIn("StockDecisionCanonicalSummary", workspace_source)
        self.assertIn("<StockDecisionSupportPanelsdecisionLocked={decisionLocked}", compact_workspace_source)
        self.assertIn("<StockDecisionCanonicalSummary", workspace_source)
        self.assertNotIn('source_cards?: StockDetailData["source_cards"]', workspace_source)
        self.assertNotIn('artifacts?: StockDetailData["artifacts"]', workspace_source)
        self.assertNotIn("function TradingAvailabilityBar(", workspace_source)
        self.assertNotIn("function DataFreshnessGate(", workspace_source)
        self.assertNotIn("function ObservationDecisionBlocks(", workspace_source)
        self.assertNotIn("function evidenceSourceSummary(", workspace_source)
        self.assertNotIn("readinessModeCopy", workspace_source)

        self.assertIn("export function StockDecisionSupportPanels(", support_source)
        self.assertIn("export function StockDecisionCanonicalSummary(", support_source)
        self.assertIn("function TradingAvailabilityBar(", support_source)
        self.assertIn("function DataFreshnessGate(", support_source)
        self.assertIn("function ObservationDecisionBlocks(", support_source)
        self.assertIn("function evidenceSourceSummary(", support_source)
        self.assertNotIn('source_cards?: StockDetailData["source_cards"]', support_source)
        self.assertNotIn('artifacts?: StockDetailData["artifacts"]', support_source)
        self.assertNotIn("detail?.source_cards", support_source)
        self.assertNotIn("detail?.artifacts", support_source)
        self.assertIn("readinessModeCopy", support_source)
        self.assertIn("refreshTaskCopy", support_source)
        self.assertIn("System Environment", support_source)
        self.assertIn("不使用当前页面内容判断今天是否交易", support_source)
        self.assertIn("为什么入池", support_source)
        self.assertIn("弱结论", support_source)

        self.assertIn('import { StockDecisionCanonicalSummary } from "./stock-decision-support"', ask_workspace)
        self.assertIn("sourceGeneratedAt?: string", ask_workspace)
        self.assertNotIn("canonicalSummary?: ReactNode", ask_workspace)
        self.assertNotIn("type { ReactNode }", ask_workspace)

    def test_stock_display_helpers_stay_deduplicated(self) -> None:
        profile_source = STOCK_PROFILE_WORKSPACE_PATH.read_text(encoding="utf-8")
        workspace_source = STOCK_DECISION_WORKSPACE_PATH.read_text(encoding="utf-8")
        support_source = STOCK_DECISION_SUPPORT_PATH.read_text(encoding="utf-8")
        formal_source = STOCK_FORMAL_PANELS_PATH.read_text(encoding="utf-8")
        utils_source = STOCK_DISPLAY_UTILS_PATH.read_text(encoding="utf-8")
        text_utils_source = WEB_TEXT_UTILS_PATH.read_text(encoding="utf-8")

        for export_name in (
            "canonicalText",
            "hasDisplayValue",
            "displayText",
        ):
            with self.subTest(export_name=export_name):
                self.assertIn(f"export function {export_name}(", utils_source)
        self.assertIn("function flattenTexts(", text_utils_source)
        self.assertIn("export function uniqueTexts(", text_utils_source)
        self.assertNotIn("export function flattenTexts(", text_utils_source)
        self.assertIn('export { uniqueTexts } from "@/lib/text-utils"', utils_source)
        self.assertNotIn("function flattenTexts(", utils_source)
        self.assertNotIn("function uniqueTexts(", utils_source)

        for component_source in (
            profile_source,
            workspace_source,
            support_source,
            formal_source,
        ):
            with self.subTest(component="stock-display-utils-consumer"):
                self.assertIn('from "./stock-display-utils"', component_source)
                self.assertNotIn("function canonicalText(", component_source)
                self.assertNotIn("function hasDisplayValue(", component_source)
                self.assertNotIn("function displayText(", component_source)
                self.assertNotIn("function uniqueTexts(", component_source)

    def test_stock_page_defers_ask_workspace_until_tab_open(self) -> None:
        source = STOCK_PROFILE_WORKSPACE_PATH.read_text(encoding="utf-8")
        compact_source = "".join(source.split())
        ask_workspace = STOCK_ASK_WORKSPACE_PATH.read_text(encoding="utf-8")

        self.assertIn('import("./stock-ask-workspace").then(', source)
        self.assertIn("(module) => module.StockAskWorkspace", source)
        self.assertIn('const ask = useAsk(code, activeTab === "追问")', source)
        self.assertIn('activeTab==="追问"?(', compact_source)
        self.assertIn("<StockAskWorkspace", source)
        self.assertNotIn("api.askFollowup", source)
        self.assertNotIn("function historyPayload(", source)
        self.assertNotIn("const [messages, setMessages]", source)
        self.assertNotIn("const [pendingQuestion, setPendingQuestion]", source)
        self.assertNotIn("const [question, setQuestion]", source)
        self.assertNotIn("SendHorizontal", source)
        self.assertNotIn("AskFollowupResponse", source)

        self.assertIn("export function StockAskWorkspace(", ask_workspace)
        self.assertIn('data-testid="stock-ask-workspace"', ask_workspace)
        self.assertIn("function historyPayload(", ask_workspace)
        self.assertIn("api.askFollowup", ask_workspace)
        self.assertIn("useState<AskFollowupResponse[]>", ask_workspace)
        self.assertIn("SendHorizontal", ask_workspace)
        self.assertIn("连续追问", ask_workspace)

    def test_stock_page_defers_evidence_panel_until_evidence_tab(self) -> None:
        source = STOCK_PROFILE_WORKSPACE_PATH.read_text(encoding="utf-8")
        compact_source = "".join(source.split())
        hooks = WEB_HOOKS_PATH.read_text(encoding="utf-8")
        evidence_panel = EVIDENCE_PANEL_PATH.read_text(encoding="utf-8")

        self.assertIn("const StockEvidencePanel = dynamic(", source)
        self.assertIn('import("@/components/evidence-panel").then(', source)
        self.assertIn("(module) => module.EvidencePanel", source)
        self.assertIn("useStockProfileEvidence", source)
        self.assertIn("export function useStockProfileEvidence", hooks)
        self.assertIn('stockProfileEvidence: (code: string) => ["stock-profile", code, "evidence"] as const', hooks)
        self.assertIn("queryFn: () => api.getStockProfileEvidence(code)", hooks)
        self.assertIn("refetchOnWindowFocus: false", hooks[hooks.index("export function useStockProfileEvidence"):])
        self.assertIn(
            'conststockEvidence=useStockProfileEvidence(code,{enabled:Boolean(code)&&activeTab==="证据"&&Boolean(detail),});',
            compact_source,
        )
        self.assertIn('activeTab==="证据"?(', compact_source)
        self.assertIn("<StockEvidencePanel", source)
        self.assertIn("void stockEvidence.refetch();", source)
        self.assertIn("stockEvidence.isFetching", source)
        self.assertIn("sources={stockEvidence.data?.source_cards}", source)
        self.assertIn("artifacts={stockEvidence.data?.artifacts}", source)
        self.assertIn("profileDetail.data?.primary_source", source)
        self.assertIn("stockEvidence.data?.primary_source", source)
        self.assertNotIn('import { EvidencePanel } from "@/components/evidence-panel"', source)
        self.assertNotIn("<EvidencePanel", source)
        self.assertNotIn("sources={detail.source_cards}", source)
        self.assertNotIn("artifacts={detail.artifacts}", source)
        self.assertNotIn("useRefreshStatus", source)
        self.assertNotIn("useTriggerRefresh", source)
        self.assertNotIn("PreviewDrawer", source)
        self.assertNotIn("SourceCard", source)

        self.assertIn("export function EvidencePanel(", evidence_panel)
        self.assertIn("useRefreshStatus(refreshPage, Boolean(refreshPage)", evidence_panel)
        self.assertIn("useTriggerRefresh(refreshPage, { stockCode })", evidence_panel)
        self.assertIn("PreviewDrawer", evidence_panel)
        self.assertIn("SourceCard", evidence_panel)

    def test_stock_page_defers_secondary_tabs_until_tab_open(self) -> None:
        source = STOCK_PROFILE_WORKSPACE_PATH.read_text(encoding="utf-8")
        compact_source = "".join(source.split())
        hooks = WEB_HOOKS_PATH.read_text(encoding="utf-8")
        api_source = WEB_API_PATH.read_text(encoding="utf-8")
        secondary_source = STOCK_SECONDARY_TABS_PATH.read_text(encoding="utf-8")

        self.assertIn("const StockSecondaryTabs = dynamic<StockSecondaryTabsProps>", source)
        self.assertIn('import("./stock-secondary-tabs").then(', source)
        self.assertIn("(module) => module.StockSecondaryTabs", source)
        self.assertIn("useStockProfileSecondary", source)
        self.assertIn("export function useStockProfileSecondary", hooks)
        self.assertIn('stockProfileSecondary: (code: string) => ["stock-profile", code, "secondary"] as const', hooks)
        self.assertIn("queryFn: () => api.getStockProfileSecondary(code)", hooks)
        self.assertIn("getStockProfileSecondary(code: string)", api_source)
        self.assertIn("/secondary", api_source)
        self.assertIn(
            'conststockSecondary=useStockProfileSecondary(code,{enabled:Boolean(code)&&Boolean(detail)&&(activeTab==="持仓"||activeTab==="发现"),});',
            compact_source,
        )
        self.assertIn('activeTab==="持仓"||activeTab==="发现"', compact_source)
        self.assertIn("stockSecondary.isLoading", source)
        self.assertIn("const secondaryDetail = stockSecondary.data?.secondary_detail", source)
        self.assertIn("const secondaryLoading = stockSecondary.isLoading && !secondaryDetail", source)
        self.assertIn("stockSecondary.data?.secondary_detail", source)
        self.assertIn("void stockSecondary.refetch();", source)
        self.assertIn("<StockSecondaryTabs", source)
        self.assertIn("detail={secondaryDetail || detail}", source)
        self.assertNotIn("function triggerCard(", source)
        self.assertNotIn("const allMetricCards", source)
        self.assertNotIn("<Panel title=\"持仓指标\"", source)
        self.assertNotIn("<Panel title=\"发现指标\"", source)

        self.assertIn("export function StockSecondaryTabs(", secondary_source)
        self.assertIn("function triggerCard(", secondary_source)
        self.assertIn("<Panel title=\"持仓指标\"", secondary_source)
        self.assertIn("<Panel title=\"发现指标\"", secondary_source)
        self.assertIn("<Panel title=\"触发条件\"", secondary_source)
        self.assertIn("<Panel title=\"洞察标签\"", secondary_source)

    def test_stock_page_refreshes_only_current_visible_workspace(self) -> None:
        source = STOCK_PROFILE_WORKSPACE_PATH.read_text(encoding="utf-8")

        refresh_start = source.index("function refetchProfileSurface()")
        refresh_end = source.index("function loadDeferredInsights()", refresh_start)
        refresh_source = source[refresh_start:refresh_end]
        self.assertIn('if (activeTab === "追问")', refresh_source)
        self.assertIn("void ask.refetch();", refresh_source)
        self.assertIn("} else if (detailEnabled) {", refresh_source)
        self.assertIn("void profileDetail.refetch();", refresh_source)
        self.assertIn("if (todayActionEnabled)", refresh_source)
        self.assertIn("void todayActionQuery.refetch();", refresh_source)
        self.assertIn('if (activeTab === "证据")', refresh_source)
        self.assertIn("if (detail) {\n        void stockEvidence.refetch();\n      }", refresh_source)
        self.assertIn('if (detail && (activeTab === "持仓" || activeTab === "发现"))', refresh_source)
        self.assertIn("void stockSecondary.refetch();", refresh_source)
        self.assertIn("if (formalSectionsEnabled.profile)", refresh_source)
        self.assertIn("if (formalSectionsEnabled.risk)", refresh_source)
        self.assertIn("if (formalSectionsEnabled.sources)", refresh_source)
        self.assertIn("if (formalFullEnabled)", refresh_source)
        self.assertNotIn("} else {\n      void profileDetail.refetch();\n    }", refresh_source)
        self.assertNotIn('if (activeTab === "持仓" || activeTab === "发现") {\n      void stockSecondary.refetch();', refresh_source)
        self.assertNotIn("setFormalSectionsEnabled", refresh_source)
        self.assertNotIn("setFormalFullEnabled(true)", refresh_source)

    def test_frontend_task_name_normalization_stays_shared(self) -> None:
        hooks = WEB_HOOKS_PATH.read_text(encoding="utf-8")
        readiness_copy = WEB_READINESS_COPY_PATH.read_text(encoding="utf-8")
        task_utils = WEB_TASK_UTILS_PATH.read_text(encoding="utf-8")

        self.assertIn("export function normalizeTaskName(", task_utils)
        self.assertIn(".trim().toLowerCase()", task_utils)
        self.assertIn('normalized === "watchlist" ? "watchlist_refresh" : normalized', task_utils)
        self.assertIn('import { normalizeTaskName } from "./task-utils"', hooks)
        self.assertIn('import { normalizeTaskName } from "./task-utils"', readiness_copy)
        self.assertIn('export { normalizeTaskName } from "./task-utils"', readiness_copy)
        self.assertNotIn("function normalizeTaskName(", hooks)
        self.assertNotIn("function normalizeTaskName(", readiness_copy)

    def test_frontend_legacy_api_wrappers_stay_removed(self) -> None:
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (WEB_API_PATH, WEB_HOOKS_PATH, WEB_TYPES_PATH)
        )

        removed_symbols = (
            "useReviewDetail",
            "useDecisionLedgerSummary",
            "useDecisionLedgerReviewCases",
            "useDecisionLedgerDetail",
            "getReviewDetail",
            "getSchedulerStatus",
            "getReadinessLive",
            "getDecisionLedgerSummary",
            "getDecisionLedgerReviewCases",
            "getDecisionLedgerDetail",
            "ReviewDetailData",
            "DecisionLedgerSummaryResponse",
            "DecisionLedgerReviewCasesResponse",
            "TodayData",
            "TodayHero",
            "TodayCommandHero",
            "TodayCommandHeroAction",
            "TodayCounts",
            "export interface TodayCommandBrief {",
            "export interface TodayCommandBriefDetail {",
            "QualityCardData",
            "export const READINESS_MODE_COPY",
            "export const REFRESH_TASK_COPY",
            "export const REFRESH_REASON_COPY",
            "getDecisionLedgerCalibration(params: { window?: string; as_of?: string; limit?: number; compact?: boolean }",
            "getDecisionLedgerLearningLoop(params: { as_of?: string; compact?: boolean }",
            "useDecisionLedgerCalibration(params: { window?: string; as_of?: string; limit?: number; compact?: boolean }",
            "params.compact === false ? \"full\" : \"compact\"",
        )
        for symbol in removed_symbols:
            with self.subTest(symbol=symbol):
                self.assertNotIn(symbol, combined)

        removed_exact_wrappers = (
            "export function useStockProfile(",
            "getStockProfile(",
        )
        for symbol in removed_exact_wrappers:
            with self.subTest(symbol=symbol):
                self.assertNotIn(symbol, combined)

    def test_heavy_legacy_json_routes_are_deprecated_in_openapi(self) -> None:
        schema = self.client.get("/openapi.json").json()
        paths = schema.get("paths") or {}

        self.assertNotIn("/api/today", paths)
        self.assertNotIn("/api/watchlist/{code}", paths)
        self.assertNotIn("/api/opportunities/{code}", paths)
        self.assertNotIn("/api/review/detail", paths)
        self.assertNotIn("/api/stock/{code}/formal-data", paths)
        self.assertNotIn("/api/stock/{code}", paths)
        self.assertNotIn("/api/stock/{code}/full", paths)

        preferred_get_paths = (
            "/api/today/summary",
            "/api/today/actions",
            "/api/today/action-contracts",
            "/api/today/command-brief-detail",
            "/api/stock/{code}/summary",
            "/api/stock/{code}/detail",
            "/api/stock/{code}/evidence",
            "/api/stock/{code}/secondary",
            "/api/stock/{code}/formal-data/{section}",
            "/api/opportunities",
            "/api/opportunities/context",
            "/api/opportunities/source-cards",
            "/api/review/research",
            "/api/review/evidence",
            "/api/decision-ledger/calibration-detail",
        )
        for path in preferred_get_paths:
            with self.subTest(path=path):
                operation = (paths.get(path) or {}).get("get") or {}
                self.assertFalse(operation.get("deprecated", False), path)

    def test_frontend_unused_shell_components_stay_removed(self) -> None:
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                WEB_COMPONENTS_PATH / "data-card.tsx",
                WEB_COMPONENTS_PATH / "metric-card.tsx",
            )
        )

        self.assertFalse((WEB_COMPONENTS_PATH / "action-row.tsx").exists())
        for symbol in ("ActionRow", "ActionRowSkeleton", "DetailLink", "MiniMetric"):
            with self.subTest(symbol=symbol):
                self.assertNotIn(symbol, combined)

    def test_frontend_dead_text_title_utilities_stay_removed(self) -> None:
        source = WEB_UTILS_PATH.read_text(encoding="utf-8")

        self.assertIn("export function cn(", source)
        self.assertIn("export function asText(", source)
        self.assertIn("export function toneColor(", source)
        for symbol in (
            "compactText",
            "stockCodeFromTitle",
            "stockNameFromTitle",
            "toneLabel",
        ):
            with self.subTest(symbol=symbol):
                self.assertNotIn(symbol, source)

    def test_frontend_legacy_global_styles_stay_trimmed(self) -> None:
        source = WEB_GLOBALS_PATH.read_text(encoding="utf-8")

        for selector in (
            ".od-main",
            ".od-command-trigger",
            ".od-command-v1",
            ".od-queue-row",
            ".od-headline",
            ".war-brief",
            ".war-action-card",
            ".war-legacy-head",
            ".war-link-grid",
            ".text-balance",
            ".prism-clamp-1",
            ".positive-text",
            ".negative-text",
            ".hold-text",
            ".avoid-text",
        ):
            with self.subTest(selector=selector):
                self.assertNotIn(selector, source)

        for selector in (".od-ghost-btn", ".war-room", ".war-tool-btn", ".war-error", ".prism-clamp-2", ".prism-clamp-3"):
            with self.subTest(selector=selector):
                self.assertIn(selector, source)

    def test_command_bar_uses_native_lightweight_search(self) -> None:
        command_bar = (WEB_COMPONENTS_PATH / "command-bar.tsx").read_text(encoding="utf-8")
        package_json = (INVEST_FLOW_ROOT / "web" / "package.json").read_text(encoding="utf-8")
        lockfile = (INVEST_FLOW_ROOT / "web" / "pnpm-lock.yaml").read_text(encoding="utf-8")
        styles = WEB_GLOBALS_PATH.read_text(encoding="utf-8")

        self.assertIn("prism-command-overlay", command_bar)
        self.assertIn("prism-command-panel", command_bar)
        self.assertIn('role="dialog"', command_bar)
        self.assertIn('aria-label="命令栏"', command_bar)
        self.assertIn("command-group-heading", command_bar)
        self.assertIn("placeholder=\"搜索股票、跳转页面\"", command_bar)
        self.assertIn("onChange={(event) => setQuery(event.target.value)}", command_bar)
        self.assertIn("@keyframes prism-command-enter", styles)
        self.assertIn(".command-group-heading", styles)
        for text in (
            "cmdk",
            'import { Command } from "cmdk";',
            "Command.Input",
            "Command.List",
            "Command.Group",
            "Command.Item",
            "Command.Empty",
            "[cmdk-",
            "@radix-ui/react-dialog",
            "@radix-ui/react-primitive",
            "framer-motion",
            "AnimatePresence",
            "motion.",
            "motion-dom",
            "motion-utils",
        ):
            with self.subTest(text=text):
                self.assertNotIn(text, command_bar)
                self.assertNotIn(text, package_json)
                self.assertNotIn(text, lockfile)
                self.assertNotIn(text, styles)

    def test_command_bar_is_deferred_from_app_shell(self) -> None:
        app_shell = WEB_APP_SHELL_PATH.read_text(encoding="utf-8")

        self.assertIn('import dynamic from "next/dynamic";', app_shell)
        self.assertIn('dynamic(() => import("./command-bar").then((module) => module.CommandBar)', app_shell)
        self.assertIn("function warmCommandBar()", app_shell)
        self.assertIn("onWarmCommand={warmCommandBar}", app_shell)
        self.assertIn("{commandOpen ? <CommandBar open={commandOpen} onOpenChange={setCommandOpen} /> : null}", app_shell)
        self.assertNotIn('import { CommandBar } from "./command-bar";', app_shell)

    def test_shell_status_is_gated_to_visible_desktop_sidebar(self) -> None:
        hooks = WEB_HOOKS_PATH.read_text(encoding="utf-8")
        app_shell = WEB_APP_SHELL_PATH.read_text(encoding="utf-8")
        sidebar = (WEB_COMPONENTS_PATH / "sidebar.tsx").read_text(encoding="utf-8")

        shell_start = hooks.index("export function useShellStatus")
        shell_next_export = hooks.find("\nexport function ", shell_start + 1)
        shell_source = hooks[shell_start: shell_next_export if shell_next_export != -1 else len(hooks)]
        self.assertIn("options: { enabled?: boolean } = {}", shell_source)
        self.assertIn("const enabled = options.enabled ?? true", shell_source)
        self.assertIn("enabled,", shell_source)

        self.assertIn("const [sidebarStatusEnabled, setSidebarStatusEnabled] = useState(false)", app_shell)
        self.assertIn('window.matchMedia("(min-width: 768px)")', app_shell)
        self.assertIn("setSidebarStatusEnabled(mediaQuery.matches)", app_shell)
        self.assertIn("statusEnabled={sidebarStatusEnabled}", app_shell)

        self.assertIn("statusEnabled = true", sidebar)
        self.assertIn("statusEnabled?: boolean", sidebar)
        self.assertIn("useShellStatus({ enabled: statusEnabled })", sidebar)

    def test_theme_options_stay_deduplicated(self) -> None:
        theme_options = WEB_THEME_OPTIONS_PATH.read_text(encoding="utf-8")
        sidebar = (WEB_COMPONENTS_PATH / "sidebar.tsx").read_text(encoding="utf-8")
        theme_toggle = (WEB_COMPONENTS_PATH / "theme-toggle.tsx").read_text(encoding="utf-8")

        self.assertIn("export const THEME_OPTIONS", theme_options)
        self.assertIn("export const THEME_COPY", theme_options)
        self.assertIn("export function resolvedThemeLabel", theme_options)
        self.assertIn('from "@/components/theme-options"', sidebar)
        self.assertIn("THEME_OPTIONS.map", sidebar)
        self.assertIn("THEME_COPY[mode].icon", sidebar)
        self.assertIn("resolvedThemeLabel(mode, resolvedTheme)", sidebar)
        self.assertIn('from "@/components/theme-options"', theme_toggle)
        self.assertIn("THEME_OPTIONS.map", theme_toggle)
        self.assertIn("resolvedThemeLabel(mode, resolvedTheme)", theme_toggle)

        for source in (sidebar, theme_toggle):
            with self.subTest(component="theme-options-consumer"):
                self.assertNotIn("const themeOptions", source)
                self.assertNotIn("const themeCopy", source)
                self.assertNotIn('label: "白天"', source)
                self.assertNotIn('label: "黑夜"', source)
                self.assertNotIn('label: "跟随系统"', source)

    def test_sidebar_uses_lightweight_trust_badge(self) -> None:
        sidebar = (WEB_COMPONENTS_PATH / "sidebar.tsx").read_text(encoding="utf-8")
        trust_banner = (WEB_COMPONENTS_PATH / "trust-banner.tsx").read_text(encoding="utf-8")
        compact_badge = (WEB_COMPONENTS_PATH / "trust-compact-badge.tsx").read_text(encoding="utf-8")
        deferred_banner = WEB_DEFERRED_TRUST_BANNER_PATH.read_text(encoding="utf-8")

        self.assertIn('import { TrustCompactBadge } from "@/components/trust-compact-badge";', sidebar)
        self.assertIn("<TrustCompactBadge trust={trust} />", sidebar)
        self.assertNotIn("TrustBanner", sidebar)
        self.assertNotIn('from "@/components/trust-banner"', sidebar)
        self.assertIn("() => cachedTrustBanner", deferred_banner)
        self.assertIn("setTrustBanner(() => component)", deferred_banner)
        self.assertNotIn("useState<TrustBannerComponent | null>(\n    cachedTrustBanner", deferred_banner)

        self.assertIn("export function TrustCompactBadge", compact_badge)
        self.assertIn("export function trustLevelIcon", compact_badge)
        self.assertNotIn("ReadinessPayload", compact_badge)
        self.assertNotIn("formalGapSummary", compact_badge)
        self.assertNotIn("accountGapSummary", compact_badge)

        self.assertIn("TrustCompactBadge", trust_banner)
        self.assertNotIn("const LEVEL_ICON", trust_banner)

    def test_trust_banner_is_deferred_from_common_pages(self) -> None:
        deferred_banner = WEB_DEFERRED_TRUST_BANNER_PATH.read_text(encoding="utf-8")
        page_paths = ()

        for path in page_paths:
            with self.subTest(path=path):
                source = path.read_text(encoding="utf-8")
                self.assertIn('from "@/components/deferred-trust-banner"', source)
                self.assertIn("<DeferredTrustBanner", source)
                self.assertNotIn('from "@/components/trust-banner"', source)
                self.assertNotIn("<TrustBanner", source)

        discovery_page = DISCOVERY_PAGE_PATH.read_text(encoding="utf-8")
        discovery_workspace = DISCOVERY_WORKSPACE_PATH.read_text(encoding="utf-8")
        self.assertIn('import("./discovery-workspace").then(', "".join(discovery_page.split()))
        self.assertNotIn('from "@/components/deferred-trust-banner"', discovery_page)
        self.assertNotIn("<DeferredTrustBanner", discovery_page)
        self.assertIn('from "@/components/deferred-trust-banner"', discovery_workspace)
        self.assertIn("<DeferredTrustBanner", discovery_workspace)
        self.assertNotIn('from "@/components/trust-banner"', discovery_workspace)
        self.assertNotIn("<TrustBanner", discovery_workspace)

        command_page = TODAY_PAGE_PATH.read_text(encoding="utf-8")
        command_workspace = COMMAND_CENTER_WORKSPACE_PATH.read_text(encoding="utf-8")
        self.assertIn('import("./command-center-workspace").then(', "".join(command_page.split()))
        self.assertNotIn('from "@/components/deferred-trust-banner"', command_page)
        self.assertNotIn("<DeferredTrustBanner", command_page)
        self.assertIn('from "@/components/deferred-trust-banner"', command_workspace)
        self.assertIn("<DeferredTrustBanner", command_workspace)
        self.assertNotIn('from "@/components/trust-banner"', command_workspace)
        self.assertNotIn("<TrustBanner", command_workspace)

        portfolio_page = PORTFOLIO_PAGE_PATH.read_text(encoding="utf-8")
        portfolio_workspace = PORTFOLIO_WORKSPACE_PATH.read_text(encoding="utf-8")
        self.assertIn('import("./portfolio-workspace").then(', "".join(portfolio_page.split()))
        self.assertNotIn('from "@/components/deferred-trust-banner"', portfolio_page)
        self.assertNotIn("<DeferredTrustBanner", portfolio_page)
        self.assertIn('from "@/components/deferred-trust-banner"', portfolio_workspace)
        self.assertIn("<DeferredTrustBanner", portfolio_workspace)
        self.assertNotIn('from "@/components/trust-banner"', portfolio_workspace)
        self.assertNotIn("<TrustBanner", portfolio_workspace)

        stock_page = STOCK_PAGE_PATH.read_text(encoding="utf-8")
        stock_workspace = STOCK_PROFILE_WORKSPACE_PATH.read_text(encoding="utf-8")
        self.assertIn('import("./stock-profile-workspace").then(', "".join(stock_page.split()))
        self.assertNotIn('from "@/components/deferred-trust-banner"', stock_page)
        self.assertNotIn("<DeferredTrustBanner", stock_page)
        self.assertIn('from "@/components/deferred-trust-banner"', stock_workspace)
        self.assertIn("<DeferredTrustBanner", stock_workspace)
        self.assertNotIn('from "@/components/trust-banner"', stock_workspace)
        self.assertNotIn("<TrustBanner", stock_workspace)

        self.assertIn("export function DeferredTrustBanner", deferred_banner)
        self.assertIn('import("./trust-banner").then', deferred_banner)
        self.assertIn("module.TrustBanner", deferred_banner)
        self.assertIn("function expandTrustBanner()", deferred_banner)
        self.assertIn("onClick={onExpand}", deferred_banner)
        self.assertIn("onExpand={expandTrustBanner}", deferred_banner)
        self.assertIn("展开细节", deferred_banner)
        self.assertIn("<DeferredTrustFallback", deferred_banner)
        self.assertIn("<TrustCompactBadge", deferred_banner)
        self.assertIn("真钱执行", deferred_banner)
        self.assertNotIn("useEffect(() => {\n    if (!trust || compact || TrustBanner)", deferred_banner)

    def test_command_bar_suggest_api_is_input_driven(self) -> None:
        command_bar = (WEB_COMPONENTS_PATH / "command-bar.tsx").read_text(encoding="utf-8")
        hooks = WEB_HOOKS_PATH.read_text(encoding="utf-8")

        self.assertIn("const shouldFetchSuggestions = text.length >= 2 && digitText.length !== 6", command_bar)
        self.assertIn("if (!shouldFetchSuggestions)", command_bar)
        self.assertIn("api\n        .askSuggest(text", command_bar)
        self.assertNotIn(".askSuggest(query.trim()", command_bar)
        self.assertNotIn("askSuggest: (query: string)", hooks)
        self.assertNotIn('"ask-suggest"', hooks)

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
