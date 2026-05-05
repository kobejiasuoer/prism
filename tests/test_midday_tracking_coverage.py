from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_ROOT = REPO_ROOT / "packages"

for path in (REPO_ROOT, PACKAGES_ROOT):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

from screener import midday_verify  # noqa: E402


def _morning_item(
    *,
    code: str,
    name: str,
    tier: str,
    score: float = 70.0,
    change_pct: float = 1.5,
    theme: str = "AI",
) -> dict:
    return {
        "code": code,
        "name": name,
        "tier": tier,
        "best_score": score,
        "score": score,
        "change_pct": change_pct,
        "theme": theme,
        "setup_type": "generic",
        "entry_plan": {"levels": {}},
    }


def _scan_item(
    *,
    code: str,
    score: float = 65.0,
    change_pct: float = 1.0,
    price: float = 12.5,
    amount_yi: float = 8.0,
    capital_today_yi: float = 0.5,
    capital_trend: str = "今日流入",
    theme: str = "AI",
) -> dict:
    return {
        "code": code,
        "score": score,
        "change_pct": change_pct,
        "price": price,
        "amount_yi": amount_yi,
        "capital_flow": {
            "trend": capital_trend,
            "today_yi": capital_today_yi,
        },
        "theme": theme,
        "technical_state": {},
    }


class BuildTrackingItemsTest(unittest.TestCase):
    def test_filters_to_non_AB_tiers(self) -> None:
        shortlist = [
            _morning_item(code="600001", name="A股一", tier="A"),
            _morning_item(code="600002", name="B股一", tier="B"),
            _morning_item(code="600003", name="C股一", tier="C"),
            _morning_item(code="600004", name="D股一", tier="D"),
            _morning_item(code="600005", name="无tier", tier=""),
        ]
        scan_index = {
            "600003": _scan_item(code="600003"),
            "600004": _scan_item(code="600004"),
        }

        items = midday_verify.build_tracking_items(
            shortlist,
            scan_index,
            active_themes=["AI"],
        )
        codes = [item["code"] for item in items]
        self.assertNotIn("600001", codes)
        self.assertNotIn("600002", codes)
        self.assertEqual(set(codes), {"600003", "600004"})

    def test_status_is_always_tracking_and_includes_tier(self) -> None:
        shortlist = [_morning_item(code="600003", name="C股一", tier="C")]
        scan_index = {"600003": _scan_item(code="600003")}

        items = midday_verify.build_tracking_items(shortlist, scan_index, active_themes=[])
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["status"], "tracking")
        self.assertEqual(item["tier"], "C")
        self.assertEqual(item["code"], "600003")
        self.assertEqual(item["name"], "C股一")

    def test_snapshot_present_when_scan_data_available(self) -> None:
        shortlist = [_morning_item(code="600003", name="C股一", tier="C", score=70.0, change_pct=2.0)]
        scan_index = {
            "600003": _scan_item(
                code="600003",
                score=68.0,
                change_pct=1.4,
                price=15.6,
                capital_today_yi=0.8,
                capital_trend="转正",
            )
        }

        items = midday_verify.build_tracking_items(shortlist, scan_index, active_themes=[])
        snapshot = items[0]["snapshot"]
        self.assertIsNotNone(snapshot)
        for key in (
            "price",
            "change_pct",
            "score",
            "score_delta",
            "change_delta",
            "capital_trend",
            "flow_today_yi",
        ):
            self.assertIn(key, snapshot)
        self.assertAlmostEqual(snapshot["price"], 15.6)
        self.assertAlmostEqual(snapshot["change_pct"], 1.4)
        self.assertAlmostEqual(snapshot["score"], 68.0)
        # delta = scan - morning = 68 - 70 = -2
        self.assertAlmostEqual(snapshot["score_delta"], -2.0)
        # change delta = 1.4 - 2.0 = -0.6
        self.assertAlmostEqual(snapshot["change_delta"], -0.6)
        self.assertEqual(snapshot["capital_trend"], "转正")

    def test_handles_missing_scan_data_gracefully(self) -> None:
        shortlist = [_morning_item(code="600003", name="C股一", tier="C")]
        # No scan data for this code.
        items = midday_verify.build_tracking_items(shortlist, {}, active_themes=[])
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["status"], "tracking")
        self.assertIsNone(item["snapshot"])
        # Reason and details must always be present so consumers can render.
        self.assertTrue(item["reason"])
        self.assertIsInstance(item["details"], list)
        self.assertTrue(item["details"])

    def test_respects_limit(self) -> None:
        shortlist = [
            _morning_item(code=f"60010{i}", name=f"C股{i}", tier="C")
            for i in range(8)
        ]
        scan_index = {item["code"]: _scan_item(code=item["code"]) for item in shortlist}

        items = midday_verify.build_tracking_items(
            shortlist, scan_index, active_themes=[], limit=3
        )
        self.assertEqual(len(items), 3)


class MainOutputContractTest(unittest.TestCase):
    """Snapshot the full output contract produced by midday_verify.main."""

    def test_run_emits_tracking_bucket_alongside_existing_buckets(self) -> None:
        # Two A-tier (-> confirmed/downgraded), three C-tier (-> tracking).
        shortlist = [
            _morning_item(code="600001", name="A1", tier="A", score=80.0, change_pct=3.0),
            _morning_item(code="600002", name="A2", tier="A", score=78.0, change_pct=2.5),
            _morning_item(code="600003", name="C1", tier="C", score=70.0, change_pct=1.5),
            _morning_item(code="600004", name="C2", tier="C", score=68.0, change_pct=1.2),
            _morning_item(code="600005", name="C3", tier="C", score=66.0, change_pct=1.0),
        ]
        morning_data = {
            "timestamp": "2026-05-05 09:30:00",
            "source_scan_timestamp": "2026-05-05 09:25:00",
            "shortlist": shortlist,
        }
        scan_data = {
            "timestamp": "2026-05-05 11:30:00",
            "verification_universe": [
                _scan_item(code="600001", score=82.0, change_pct=3.5),
                _scan_item(code="600002", score=66.0, change_pct=-1.0),  # weakened
                _scan_item(code="600003"),
                _scan_item(code="600004"),
                _scan_item(code="600005"),
            ],
            "strategies": {},
            "candidates": [],
            "market_themes": {"themes": []},
        }

        output = midday_verify.run_verification(morning_data, scan_data)

        # Existing contract preserved.
        for key in ("confirmed", "downgraded", "fresh_candidates", "items", "target_codes"):
            self.assertIn(key, output)

        # New tracking bucket present.
        self.assertIn("tracking", output)
        tracking_codes = {entry["code"] for entry in output["tracking"]}
        self.assertEqual(tracking_codes, {"600003", "600004", "600005"})

        # Items in tracking must NOT also appear in confirmed/downgraded.
        verified_codes = {entry["code"] for entry in output["items"]}
        self.assertTrue(tracking_codes.isdisjoint(verified_codes))


if __name__ == "__main__":
    unittest.main()
