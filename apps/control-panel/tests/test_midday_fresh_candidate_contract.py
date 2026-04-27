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


if __name__ == "__main__":
    unittest.main()
