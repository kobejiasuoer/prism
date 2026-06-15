from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGES_ROOT = REPO_ROOT / "packages"
CONTROL_PANEL_ROOT = REPO_ROOT / "apps" / "control-panel"

for path in (REPO_ROOT, PACKAGES_ROOT, CONTROL_PANEL_ROOT):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

from apps.scripts import prism_canonical  # noqa: E402
from screener import midday_verify  # noqa: E402
from screener import parameters  # noqa: E402


class MiddayFreshCandidateContractTest(unittest.TestCase):
    def test_midday_and_canonical_use_shared_intraday_observation_rules(self) -> None:
        self.assertIs(
            midday_verify.build_intraday_observation_contract,
            parameters.build_intraday_observation_contract,
        )
        self.assertIs(
            prism_canonical.build_intraday_observation_contract,
            parameters.build_intraday_observation_contract,
        )

    def fresh_candidate(self) -> dict:
        scan_data = {
            "verification_universe": [
                {
                    "code": "123456",
                    "name": "测试股份",
                    "theme": "机器人",
                    "score": 96.5,
                    "change_pct": 5.2,
                    "amount_yi": 18.4,
                    "capital_flow": {
                        "trend": "由负转正",
                        "today_yi": 1.2,
                    },
                    "trade_note": {
                        "entry_reason": "趋势突破+资金配合",
                        "main_risk": "留意次日承接强度",
                        "watch_condition": "量能别明显萎缩；主力资金别转负",
                    },
                    "technical_state": {
                        "high20": 10.2,
                        "ma5": 9.9,
                        "ma10": 9.5,
                    },
                }
            ],
            "strategies": {},
        }

        candidates = midday_verify.build_fresh_candidates(
            scan_data,
            exclude_codes=set(),
            active_themes=["机器人"],
            limit=1,
        )
        self.assertEqual(len(candidates), 1)
        return candidates[0]

    def test_fresh_candidates_emit_first_screen_execution_fields(self) -> None:
        candidate = self.fresh_candidate()

        for key in ("setup_type", "setup_label", "setup_summary", "entry_plan", "execution_quality"):
            self.assertIn(key, candidate)

        self.assertEqual(candidate["setup_type"], "breakout_follow")
        self.assertEqual(candidate["setup_label"], "突破跟随")
        self.assertTrue(candidate["setup_summary"].strip())

        plan = candidate["entry_plan"]
        for key in ("action", "trigger", "avoid", "invalidate", "sizing", "levels"):
            self.assertIn(key, plan)
            self.assertTrue(plan[key])

        self.assertEqual(plan["levels"]["trigger"], 10.2)
        self.assertEqual(plan["levels"]["pullback"], 9.9)
        self.assertEqual(plan["levels"]["invalidate"], 9.5)

        quality = candidate["execution_quality"]
        for key in ("score", "label", "positives", "warnings"):
            self.assertIn(key, quality)
        self.assertGreaterEqual(quality["score"], 1)
        self.assertTrue(quality["label"].strip())
        self.assertIsInstance(quality["positives"], list)
        self.assertIsInstance(quality["warnings"], list)

    def test_canonical_confirmation_preserves_fresh_candidate_plan(self) -> None:
        candidate = self.fresh_candidate()
        normalized = prism_canonical.normalize_confirmation_item(
            candidate,
            status="fresh_candidate",
            morning_batch_id="screening_batch:morning",
            midday_batch_id="screening_batch:midday",
        )

        self.assertEqual(normalized["entry_plan"], candidate["entry_plan"])
        self.assertEqual(normalized["execution_quality"], candidate["execution_quality"])
        self.assertEqual(normalized["setup_type"], candidate["setup_type"])
        self.assertEqual(normalized["setup_summary"], candidate["setup_summary"])

        original_screening_loader = prism_canonical.load_screening_batch
        original_confirmation_loader = prism_canonical.load_confirmation
        try:
            prism_canonical.load_screening_batch = lambda path=None: {"candidates": []}
            prism_canonical.load_confirmation = lambda: {
                "midday_batch_id": "screening_batch:midday",
                "morning_batch_id": "screening_batch:morning",
                "fresh_candidates": [normalized],
                "confirmed": [],
                "downgraded": [],
            }

            detail = prism_canonical.find_candidate_detail("123456")
        finally:
            prism_canonical.load_screening_batch = original_screening_loader
            prism_canonical.load_confirmation = original_confirmation_loader

        self.assertEqual(detail["entry_plan"], candidate["entry_plan"])
        self.assertEqual(detail["execution_quality"], candidate["execution_quality"])
        self.assertEqual(detail["setup_type"], "breakout_follow")
        self.assertEqual(detail["screening_note"], candidate["setup_summary"])
        self.assertIn("留意次日承接强度", detail["risk_flags"])

    def test_canonical_confirmation_backfills_legacy_fresh_candidate_plan(self) -> None:
        candidate = self.fresh_candidate()
        legacy_candidate = dict(candidate)
        legacy_candidate.pop("entry_plan")
        legacy_candidate.pop("execution_quality")
        legacy_candidate.pop("setup_type")
        legacy_candidate.pop("setup_summary")

        normalized = prism_canonical.normalize_confirmation_item(
            legacy_candidate,
            status="fresh_candidate",
            morning_batch_id="screening_batch:morning",
            midday_batch_id="screening_batch:midday",
        )

        self.assertEqual(normalized["setup_type"], "breakout_follow")
        self.assertTrue(normalized["setup_summary"].strip())
        self.assertEqual(normalized["entry_plan"]["levels"]["trigger"], 10.2)
        self.assertEqual(normalized["entry_plan"]["levels"]["pullback"], 9.9)
        self.assertEqual(normalized["entry_plan"]["levels"]["invalidate"], 9.5)
        self.assertTrue(normalized["entry_plan"]["action"].strip())
        self.assertTrue(normalized["execution_quality"]["label"].strip())
        self.assertIsInstance(normalized["execution_quality"]["positives"], list)
        self.assertIsInstance(normalized["execution_quality"]["warnings"], list)

    def test_canonical_confirmation_backfills_confirmed_snapshot_plan(self) -> None:
        normalized = prism_canonical.normalize_confirmation_item(
            {
                "code": "000063",
                "name": "中兴通讯",
                "status": "confirmed",
                "reason": "涨幅仍保持为正",
                "details": ["短线反转结构仍在", "主题仍在主线内（AI硬件链）"],
                "snapshot": {
                    "setup_type": "low_reversal",
                    "setup_label": "低位反转",
                    "score": 73.75,
                    "change_pct": 2.89,
                    "amount_yi": 64.1,
                    "capital_trend": "由负转正",
                    "flow_today_yi": 22.64,
                    "current_theme": "AI硬件链",
                    "theme_in_play": True,
                    "pullback_level": 36.25,
                    "trigger_level": 40.2,
                    "invalidate_level": 36.07,
                    "ma5": 36.25,
                    "ma10": 36.07,
                    "confirmation_label": "承接良好",
                },
            },
            status="confirmed",
            morning_batch_id="screening_batch:morning",
            midday_batch_id="screening_batch:midday",
        )

        self.assertEqual(normalized["theme"], "AI硬件链")
        self.assertEqual(normalized["setup_type"], "low_reversal")
        self.assertEqual(normalized["setup_label"], "低位反转")
        self.assertEqual(normalized["score"], 73.75)
        self.assertEqual(normalized["flow_today_yi"], 22.64)
        self.assertEqual(normalized["capital_trend"], "由负转正")
        self.assertIn("站回 36.25", normalized["entry_plan"]["trigger"])
        self.assertEqual(normalized["entry_plan"]["sizing"], "触发后小仓位试错")
        self.assertEqual(normalized["entry_plan"]["levels"]["pullback"], 36.25)
        self.assertGreaterEqual(normalized["execution_quality"]["score"], 6)

    def test_midday_verifies_caution_shortlist_when_no_ab_targets(self) -> None:
        morning = {
            "timestamp": "2026-05-28 09:40:57",
            "source_scan_timestamp": "2026-05-28 09:40:57",
            "shortlist": [
                {
                    "code": "123456",
                    "name": "测试股份",
                    "tier": "C",
                    "screening_status": "caution",
                    "best_score": 78,
                    "change_pct": 2.1,
                    "themes": ["机器人"],
                    "setup_type": "breakout_follow",
                    "entry_plan": {"levels": {"trigger": 10.2, "pullback": 9.8, "invalidate": 9.4}},
                }
            ],
        }
        current = {
            "timestamp": "2026-05-28 13:46:28",
            "market_themes": {"themes": [{"theme": "机器人"}]},
            "verification_universe": [
                {
                    "code": "123456",
                    "name": "测试股份",
                    "theme": "机器人",
                    "score": 82,
                    "change_pct": 3.2,
                    "amount_yi": 12,
                    "price": 10.3,
                    "capital_flow": {"trend": "持续流入", "today_yi": 1.1},
                    "technical_state": {"ma5": 10.0, "ma10": 9.7},
                }
            ],
            "strategies": {},
        }

        result = midday_verify.run_verification(morning, current)

        self.assertEqual(result["validation_status"], "ok")
        self.assertEqual(result["target_codes"], ["123456"])
        self.assertEqual(len(result["confirmed"]), 1)
        self.assertEqual(result["confirmed"][0]["code"], "123456")
        self.assertEqual(result["tracking"], [])


if __name__ == "__main__":
    unittest.main()
