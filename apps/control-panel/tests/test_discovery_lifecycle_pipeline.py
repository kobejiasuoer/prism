from __future__ import annotations

import sys
import unittest
from importlib import import_module
from pathlib import Path
from unittest.mock import Mock, patch


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
        self.assertNotIn("secondary_groups", payload)
        self.assertNotIn("secondary_total", payload)

    def test_opportunities_lifecycle_sidebar_payload_is_capped_to_visible_cards(self) -> None:
        dashboard_data = self.dashboard_data()
        lifecycle_payload = {
            "current_timestamp": "2026-05-31 12:30:00",
            "summary": {
                "current_pool_size": 8,
                "previous_pool_size": 8,
            },
            "groups": {
                "continued": [
                    {"code": f"60000{index}", "name": f"延续{index}", "theme": "机器人"}
                    for index in range(5)
                ],
                "upgraded": [{"code": "600101", "name": "升级", "theme": "算力"}],
                "downgraded": [{"code": "600102", "name": "降级", "theme": "算力"}],
                "entered": [{"code": "600103", "name": "新增", "theme": "算力"}],
                "exited": [{"code": "600104", "name": "退出", "theme": "算力"}],
                "handed_off": [{"code": "600105", "name": "交接", "theme": "算力"}],
            },
            "activity_count": 10,
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

        lifecycle_groups = payload.get("lifecycle_groups") or []
        self.assertEqual(len(lifecycle_groups), 4)
        self.assertEqual(lifecycle_groups[0]["key"], "lifecycle_continued")
        self.assertEqual(lifecycle_groups[0]["count"], 5)
        self.assertEqual(len(lifecycle_groups[0]["cards"]), 3)

    def test_opportunities_view_skips_heavy_freshness_diagnostics(self) -> None:
        dashboard_data = self.dashboard_data()
        readiness_mock = Mock(
            return_value={
                "expected_trade_date": "2026-05-31",
                "data_trade_date": "2026-05-31",
                "brief_is_live": False,
            }
        )

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
            return_value={"display_lifecycle": {}, "lifecycle_note": "test"},
        ), patch.object(
            dashboard_data,
            "build_review_learning_memory_index",
            return_value={"cases": [], "patterns": []},
        ), patch.object(
            dashboard_data,
            "compute_readiness",
            readiness_mock,
        ), patch.object(
            dashboard_data,
            "build_dataset_freshness_rows",
            side_effect=AssertionError("Discovery should not build dataset freshness diagnostics"),
        ), patch.object(
            dashboard_data,
            "build_formal_freshness_rows",
            side_effect=AssertionError("Discovery should not build formal freshness diagnostics"),
        ):
            payload = dashboard_data.build_opportunities_view()

        self.assertEqual(payload["trade_date"], "2026-05-31")
        self.assertIn("groups", payload)
        self.assertEqual(readiness_mock.call_args.kwargs["dataset_freshness"], [])
        self.assertEqual(readiness_mock.call_args.kwargs["formal_freshness"], [])


    def test_opportunities_response_includes_valve_status(self) -> None:
        """valve_status is surfaced from the execution gate status field."""
        dashboard_data = self.dashboard_data()
        lifecycle_context = {
            "latest_lifecycle": None,
            "active_lifecycle": None,
            "display_lifecycle": {},
            "lifecycle_note": "",
        }

        for gate_status in ("on", "limited", "off"):
            with self.subTest(gate_status=gate_status):
                screening_batch = {
                    "candidates": [],
                    "market_regime": {
                        "execution_gate": {"status": gate_status, "allow_new_positions": gate_status != "off", "label": "test"},
                    },
                }
                with patch.object(dashboard_data, "expected_trade_date", return_value="2026-06-01"), patch.object(
                    dashboard_data,
                    "load_decision_brief",
                    side_effect=FileNotFoundError,
                ), patch.object(
                    dashboard_data,
                    "load_watchlist_snapshot",
                    side_effect=FileNotFoundError,
                ), patch.object(
                    dashboard_data,
                    "load_screening_batch",
                    return_value=screening_batch,
                ), patch.object(
                    dashboard_data,
                    "load_confirmation",
                    side_effect=FileNotFoundError,
                ), patch.object(
                    dashboard_data,
                    "load_quality_status",
                    side_effect=FileNotFoundError,
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
                        "data_trade_date": "2026-06-01",
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

                self.assertIn("valve_status", payload)
                self.assertEqual(payload["valve_status"], gate_status)

    def test_opportunities_valve_status_defaults_to_off_when_gate_missing(self) -> None:
        """When execution gate is absent, valve_status defaults to 'off'."""
        dashboard_data = self.dashboard_data()
        lifecycle_context = {
            "latest_lifecycle": None,
            "active_lifecycle": None,
            "display_lifecycle": {},
            "lifecycle_note": "",
        }

        with patch.object(dashboard_data, "expected_trade_date", return_value="2026-06-01"), patch.object(
            dashboard_data,
            "load_decision_brief",
            side_effect=FileNotFoundError,
        ), patch.object(
            dashboard_data,
            "load_watchlist_snapshot",
            side_effect=FileNotFoundError,
        ), patch.object(
            dashboard_data,
            "load_screening_batch",
            side_effect=FileNotFoundError,
        ), patch.object(
            dashboard_data,
            "load_confirmation",
            side_effect=FileNotFoundError,
        ), patch.object(
            dashboard_data,
            "load_quality_status",
            side_effect=FileNotFoundError,
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

        self.assertEqual(payload["valve_status"], "off")


    def test_opportunities_cards_carry_triage_fields(self) -> None:
        """Every candidate card carries structured triage fields after A5 stamping."""
        dashboard_data = self.dashboard_data()
        lifecycle_context = {
            "latest_lifecycle": None,
            "active_lifecycle": None,
            "display_lifecycle": {},
            "lifecycle_note": "",
        }

        # Screening batch with: a V2 approved candidate and a legacy approved
        # candidate.
        screening_batch = {
            "candidates": [
                {
                    "code": "600001",
                    "name": "V2候选",
                    "screening_status": "approved",
                    "suggested_action": "actionable",
                    "risk_level": "info",
                    "score": 88,
                },
                {
                    "code": "600002",
                    "name": "旧版候选",
                    "screening_status": "approved",
                    "risk_level": "caution",
                    "score": 72,
                },
            ],
            "market_regime": {
                "execution_gate": {
                    "status": "on",
                    "allow_new_positions": True,
                    "label": "开放",
                },
            },
        }
        confirmation = {
            "confirmed": [],
            "fresh_candidates": [],
            "downgraded": [
                {
                    "code": "600003",
                    "name": "淘汰候选",
                    "suggested_action": "drop",
                    "risk_level": "block",
                },
            ],
        }

        with patch.object(dashboard_data, "expected_trade_date", return_value="2026-06-14"), patch.object(
            dashboard_data,
            "load_decision_brief",
            side_effect=FileNotFoundError,
        ), patch.object(
            dashboard_data,
            "load_watchlist_snapshot",
            side_effect=FileNotFoundError,
        ), patch.object(
            dashboard_data,
            "load_screening_batch",
            return_value=screening_batch,
        ), patch.object(
            dashboard_data,
            "load_confirmation",
            return_value=confirmation,
        ), patch.object(
            dashboard_data,
            "load_quality_status",
            side_effect=FileNotFoundError,
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
                "expected_trade_date": "2026-06-14",
                "data_trade_date": "2026-06-14",
                "brief_is_live": True,
                "trust_level": {
                    "level": "trusted",
                    "can_trade_live": True,
                },
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

        all_cards = [c for g in payload.get("groups") or [] for c in g.get("cards", [])]
        self.assertGreaterEqual(len(all_cards), 2, f"Expected >= 2 cards, got {len(all_cards)}")
        valid_action_states = {"focus", "on_trigger", "watch", "drop"}
        valid_gate_states = {"open", "capped", "closed"}
        for card in all_cards:
            self.assertIn("triage_action_state", card)
            self.assertIn(card["triage_action_state"], valid_action_states, f"Unexpected action_state for {card.get('code')}: {card['triage_action_state']}")
            self.assertIn("triage_gate_state", card)
            self.assertIn(card["triage_gate_state"], valid_gate_states, f"Unexpected gate_state for {card.get('code')}: {card['triage_gate_state']}")
            self.assertIn("triage_gate_blocker", card)
            self.assertIn("triage_legacy", card)

        # V2 card should have triage_legacy=False
        v2_card = next(c for c in all_cards if c.get("code") == "600001")
        self.assertFalse(v2_card["triage_legacy"])

        # Legacy card (no suggested_action) should have triage_legacy=True
        legacy_card = next(c for c in all_cards if c.get("code") == "600002")
        self.assertTrue(legacy_card["triage_legacy"])

        # Eliminated card should have action_state=drop
        eliminated_card = next(c for c in all_cards if c.get("code") == "600003")
        self.assertEqual(eliminated_card["triage_action_state"], "drop")

    def test_opportunities_cards_carry_theme_rank(self) -> None:
        """Every candidate card carries triage_rank_in_theme and triage_theme_in_play (C1a)."""
        dashboard_data = self.dashboard_data()
        lifecycle_context = {
            "latest_lifecycle": None,
            "active_lifecycle": None,
            "display_lifecycle": {},
            "lifecycle_note": "",
        }

        # Two candidates sharing the same theme with distinct priority_scores.
        screening_batch = {
            "candidates": [
                {
                    "code": "700001",
                    "name": "AI龙头",
                    "screening_status": "approved",
                    "suggested_action": "actionable",
                    "risk_level": "info",
                    "score": 92,
                    "priority_score": 92,
                    "themes": ["AI"],
                },
                {
                    "code": "700002",
                    "name": "AI跟随",
                    "screening_status": "approved",
                    "suggested_action": "trial",
                    "risk_level": "info",
                    "score": 65,
                    "priority_score": 65,
                    "themes": ["AI"],
                },
                {
                    "code": "700003",
                    "name": "有色龙头",
                    "screening_status": "approved",
                    "suggested_action": "actionable",
                    "risk_level": "info",
                    "score": 88,
                    "priority_score": 88,
                    "themes": ["有色"],
                },
            ],
            "market_regime": {
                "execution_gate": {
                    "status": "on",
                    "allow_new_positions": True,
                    "label": "开放",
                },
            },
        }
        confirmation = {"confirmed": [], "fresh_candidates": [], "downgraded": []}

        with patch.object(dashboard_data, "expected_trade_date", return_value="2026-06-14"), patch.object(
            dashboard_data,
            "load_decision_brief",
            side_effect=FileNotFoundError,
        ), patch.object(
            dashboard_data,
            "load_watchlist_snapshot",
            side_effect=FileNotFoundError,
        ), patch.object(
            dashboard_data,
            "load_screening_batch",
            return_value=screening_batch,
        ), patch.object(
            dashboard_data,
            "load_confirmation",
            return_value=confirmation,
        ), patch.object(
            dashboard_data,
            "load_quality_status",
            side_effect=FileNotFoundError,
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
                "expected_trade_date": "2026-06-14",
                "data_trade_date": "2026-06-14",
                "brief_is_live": True,
                "trust_level": {
                    "level": "trusted",
                    "can_trade_live": True,
                },
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

        all_cards = [c for g in payload.get("groups") or [] for c in g.get("cards", [])]
        self.assertGreaterEqual(len(all_cards), 3, f"Expected >= 3 cards, got {len(all_cards)}")

        # Every card must carry both new fields.
        for card in all_cards:
            self.assertIn("triage_rank_in_theme", card)
            self.assertIsInstance(card["triage_rank_in_theme"], int)
            self.assertIn("triage_theme_in_play", card)
            self.assertIsInstance(card["triage_theme_in_play"], bool)

        # Verify rank ordering within the shared "AI" theme.
        ai_cards = [c for c in all_cards if c.get("theme") == "AI"]
        self.assertGreaterEqual(len(ai_cards), 2, "Expected >= 2 AI cards for rank check")
        ranks = sorted(c["triage_rank_in_theme"] for c in ai_cards)
        self.assertEqual(ranks, [1, 2])
        # Highest priority_score gets rank 1.
        best = max(ai_cards, key=lambda c: c.get("priority_score") or 0)
        self.assertEqual(best["triage_rank_in_theme"], 1)

        # "有色" theme only has one card, so rank is 1.
        metal_cards = [c for c in all_cards if c.get("theme") == "有色"]
        self.assertEqual(len(metal_cards), 1)
        self.assertEqual(metal_cards[0]["triage_rank_in_theme"], 1)

    def test_build_yesterday_trial_review_pure_function(self) -> None:
        """Pure-function test: identify yesterday's trial candidates from lifecycle deltas."""
        dashboard_data = self.dashboard_data()
        fn = dashboard_data.build_yesterday_trial_review

        # Today's cards keyed by code.
        today_cards = {
            "600001": {"code": "600001", "name": "试错延续", "triage_action_state": "on_trigger"},
            "600002": {"code": "600002", "name": "已淘汰票", "triage_action_state": "drop"},
        }

        # Lifecycle with: one continued trial, one exited trial, one continued observe.
        display_lifecycle = {
            "groups": {
                "continued": [
                    {"code": "600001", "name": "试错延续", "prev_suggested_action": "trial",
                     "curr_suggested_action": "actionable"},
                    {"code": "600003", "name": "观察票", "prev_suggested_action": "observe",
                     "curr_suggested_action": "observe"},
                ],
                "exited": [
                    {"code": "600004", "name": "昨日试错退出", "suggested_action": "trial"},
                    {"code": "600005", "name": "昨日观察退出", "suggested_action": "observe"},
                ],
                "entered": [],
                "upgraded": [],
                "downgraded": [],
                "handed_off": [],
            },
        }

        result = fn(today_cards, display_lifecycle)

        # Should find exactly 2 trial candidates (one continued, one exited).
        self.assertEqual(len(result), 2)
        codes = {r["code"] for r in result}
        self.assertEqual(codes, {"600001", "600004"})

        # Continued trial: still_listed=True, today_action_state from card.
        continued_trial = next(r for r in result if r["code"] == "600001")
        self.assertEqual(continued_trial["yesterday_action"], "trial")
        self.assertTrue(continued_trial["still_listed"])
        self.assertEqual(continued_trial["today_action_state"], "on_trigger")

        # Exited trial: still_listed=False, today_action_state="drop".
        exited_trial = next(r for r in result if r["code"] == "600004")
        self.assertEqual(exited_trial["yesterday_action"], "trial")
        self.assertFalse(exited_trial["still_listed"])
        self.assertEqual(exited_trial["today_action_state"], "drop")

    def test_build_yesterday_trial_review_empty_when_no_lifecycle(self) -> None:
        """Returns empty list when no lifecycle data is available."""
        dashboard_data = self.dashboard_data()
        fn = dashboard_data.build_yesterday_trial_review
        result = fn({}, None)
        self.assertEqual(result, [])

    def test_opportunities_response_includes_yesterday_trial_review(self) -> None:
        """Integration test: build_opportunities_view emits yesterday_trial_review."""
        dashboard_data = self.dashboard_data()

        lifecycle_payload = {
            "current_timestamp": "2026-06-13 14:30:00",
            "summary": {"current_pool_size": 2, "previous_pool_size": 3},
            "groups": {
                "continued": [
                    {
                        "code": "600010",
                        "name": "昨日试错今日仍在",
                        "prev_suggested_action": "trial",
                        "curr_suggested_action": "actionable",
                        "theme": "机器人",
                    },
                ],
                "exited": [
                    {
                        "code": "600011",
                        "name": "昨日试错今日退出",
                        "suggested_action": "trial",
                        "theme": "算力",
                    },
                ],
                "entered": [],
                "upgraded": [],
                "downgraded": [],
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

        # Today's screening has the continued trial candidate (600010) but not the
        # exited one (600011).
        screening_batch = {
            "candidates": [
                {
                    "code": "600010",
                    "name": "昨日试错今日仍在",
                    "screening_status": "approved",
                    "suggested_action": "actionable",
                    "risk_level": "info",
                    "score": 88,
                    "priority_score": 88,
                    "themes": ["机器人"],
                },
            ],
            "market_regime": {
                "execution_gate": {
                    "status": "on",
                    "allow_new_positions": True,
                    "label": "开放",
                },
            },
        }
        confirmation = {"confirmed": [], "fresh_candidates": [], "downgraded": []}

        with patch.object(dashboard_data, "expected_trade_date", return_value="2026-06-14"), patch.object(
            dashboard_data,
            "load_decision_brief",
            side_effect=FileNotFoundError,
        ), patch.object(
            dashboard_data,
            "load_watchlist_snapshot",
            side_effect=FileNotFoundError,
        ), patch.object(
            dashboard_data,
            "load_screening_batch",
            return_value=screening_batch,
        ), patch.object(
            dashboard_data,
            "load_confirmation",
            return_value=confirmation,
        ), patch.object(
            dashboard_data,
            "load_quality_status",
            side_effect=FileNotFoundError,
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
                "expected_trade_date": "2026-06-14",
                "data_trade_date": "2026-06-14",
                "brief_is_live": True,
                "trust_level": {
                    "level": "trusted",
                    "can_trade_live": True,
                },
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

        self.assertIn("yesterday_trial_review", payload)
        review = payload["yesterday_trial_review"]
        self.assertEqual(len(review), 2)

        review_by_code = {r["code"]: r for r in review}

        # 600010: was trial yesterday, still listed today.
        self.assertIn("600010", review_by_code)
        self.assertTrue(review_by_code["600010"]["still_listed"])
        self.assertEqual(review_by_code["600010"]["yesterday_action"], "trial")

        # 600011: was trial yesterday, exited today.
        self.assertIn("600011", review_by_code)
        self.assertFalse(review_by_code["600011"]["still_listed"])
        self.assertEqual(review_by_code["600011"]["today_action_state"], "drop")


if __name__ == "__main__":
    unittest.main()
