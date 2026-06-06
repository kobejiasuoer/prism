from __future__ import annotations

import sys
import unittest
from importlib import import_module
from pathlib import Path
from unittest.mock import patch


INVEST_FLOW_ROOT = Path(__file__).resolve().parents[2]
if str(INVEST_FLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(INVEST_FLOW_ROOT))


class DiscoveryLifecyclePipelineTest(unittest.TestCase):
    def dashboard_data(self):
        return import_module("control_panel.dashboard_data")

    def test_opportunities_view_falls_back_to_empty_state_when_screening_batch_missing(self) -> None:
        dashboard_data = self.dashboard_data()
        lifecycle_context = {
            "latest_lifecycle": None,
            "active_lifecycle": None,
            "display_lifecycle": {},
            "lifecycle_note": "暂无生命周期快照",
        }

        with patch.object(dashboard_data, "expected_trade_date", return_value="2026-06-01"), patch.object(
            dashboard_data,
            "load_decision_brief",
            side_effect=FileNotFoundError("decision brief not found"),
        ), patch.object(
            dashboard_data,
            "load_watchlist_snapshot",
            side_effect=FileNotFoundError("watchlist snapshot not found"),
        ), patch.object(
            dashboard_data,
            "load_screening_batch",
            side_effect=FileNotFoundError("screening batch not found"),
        ), patch.object(
            dashboard_data,
            "load_confirmation",
            side_effect=FileNotFoundError("confirmation not found"),
        ), patch.object(
            dashboard_data,
            "load_quality_status",
            side_effect=FileNotFoundError("quality status not found"),
        ), patch.object(
            dashboard_data,
            "resolve_lifecycle_context",
            return_value=lifecycle_context,
        ), patch.object(
            dashboard_data,
            "build_review_learning_memory_index",
            return_value={"cases": [], "patterns": []},
        ), patch.object(
            dashboard_data,
            "compute_readiness",
            return_value={
                "expected_trade_date": "2026-06-01",
                "data_trade_date": None,
                "brief_is_live": False,
                "trust_level": {"level": "unavailable"},
            },
        ), patch.object(
            dashboard_data,
            "load_account_book",
            return_value={},
        ), patch.object(
            dashboard_data,
            "load_today_action_decision_store",
            return_value={},
        ), patch.object(
            dashboard_data,
            "build_dataset_freshness_rows",
            return_value=[],
        ), patch.object(
            dashboard_data,
            "build_formal_freshness_rows",
            return_value=[],
        ):
            payload = dashboard_data.build_opportunities_view()

        source_cards = payload.get("source_cards") or []
        self.assertGreaterEqual(len(source_cards), 1)
        self.assertEqual(source_cards[0]["label"], "早盘批次")
        self.assertEqual(source_cards[0]["value"], "-")
        self.assertEqual(source_cards[0]["detail"], "暂无批次")

        hero = payload.get("hero") or {}
        self.assertEqual(hero.get("main_theme"), "暂无主线")

        groups = {group["key"]: group for group in payload.get("groups") or []}
        self.assertEqual(groups["morning"]["count"], 0)
        self.assertEqual(groups["watching"]["count"], 0)
        self.assertEqual(groups["midday_new"]["count"], 0)
        self.assertEqual(groups["upgrade"]["count"], 0)
        self.assertEqual(groups["eliminated"]["count"], 0)

    def test_opportunities_view_surfaces_upgraded_and_exited_in_page_groups(self) -> None:
        dashboard_data = self.dashboard_data()
        lifecycle_payload = {
            "current_timestamp": "2026-05-31 12:30:00",
            "summary": {
                "current_pool_size": 2,
                "previous_pool_size": 2,
            },
            "groups": {
                "entered": [],
                "upgraded": [
                    {
                        "code": "600001",
                        "name": "测试升级",
                        "curr_score": 91,
                        "score_delta": 18,
                        "theme": "机器人",
                        "persistence_label": "非一日脉冲",
                    }
                ],
                "downgraded": [],
                "continued": [],
                "exited": [
                    {
                        "code": "600002",
                        "name": "测试退出",
                        "score": 72,
                        "theme": "算力",
                        "last_seen": "2026-05-30 14:55:00",
                    }
                ],
                "handed_off": [],
            },
            "activity_count": 2,
            "midday_matches_current_ai": True,
        }
        lifecycle_context = {
            "latest_lifecycle": lifecycle_payload,
            "active_lifecycle": lifecycle_payload,
            "display_lifecycle": lifecycle_payload,
            "lifecycle_note": "test lifecycle note",
        }

        with patch.object(dashboard_data, "expected_trade_date", return_value="2026-05-31"), patch.object(
            dashboard_data,
            "safe_canonical_load",
            return_value=None,
        ), patch.object(
            dashboard_data,
            "load_screening_batch",
            return_value={"candidates": [], "market_regime": {"execution_gate": {}}, "screening_summary": {}},
        ), patch.object(
            dashboard_data,
            "resolve_lifecycle_context",
            return_value=lifecycle_context,
        ), patch.object(
            dashboard_data,
            "build_review_learning_memory_index",
            return_value={"cases": [], "patterns": []},
        ), patch.object(
            dashboard_data,
            "compute_readiness",
            return_value={
                "expected_trade_date": "2026-05-31",
                "data_trade_date": "2026-05-31",
                "brief_is_live": False,
                "trust_level": {"level": "trusted"},
            },
        ), patch.object(
            dashboard_data,
            "load_account_book",
            return_value={},
        ), patch.object(
            dashboard_data,
            "load_today_action_decision_store",
            return_value={},
        ), patch.object(
            dashboard_data,
            "build_dataset_freshness_rows",
            return_value=[],
        ), patch.object(
            dashboard_data,
            "build_formal_freshness_rows",
            return_value=[],
        ):
            payload = dashboard_data.build_opportunities_view()

        groups = {group["key"]: group for group in payload.get("groups") or []}
        self.assertEqual(groups["upgrade"]["count"], 1)
        self.assertEqual(groups["eliminated"]["count"], 1)
        self.assertEqual(groups["upgrade"]["cards"][0]["code"], "600001")
        self.assertEqual(groups["eliminated"]["cards"][0]["code"], "600002")

        lifecycle_groups = {group["key"]: group for group in payload.get("lifecycle_groups") or []}
        self.assertIn("lifecycle_upgraded", lifecycle_groups)
        self.assertIn("lifecycle_exited", lifecycle_groups)
        self.assertEqual(lifecycle_groups["lifecycle_upgraded"]["count"], 1)
        self.assertEqual(lifecycle_groups["lifecycle_exited"]["count"], 1)
        self.assertEqual(lifecycle_groups["lifecycle_upgraded"]["cards"][0]["code"], "600001")
        self.assertEqual(lifecycle_groups["lifecycle_exited"]["cards"][0]["code"], "600002")


if __name__ == "__main__":
    unittest.main()
