from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path


CONTROL_PANEL_ROOT = Path(__file__).resolve().parents[1]
if str(CONTROL_PANEL_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROL_PANEL_ROOT))

import dashboard_data  # noqa: E402


class ReviewSourceFreshnessTests(unittest.TestCase):
    def test_current_lifecycle_is_fresh_while_historical_research_is_flagged(self) -> None:
        now = datetime(2026, 5, 19, 12, 40, 0)
        lifecycle = dashboard_data.build_review_source_card(
            key="lifecycle_latest",
            label="最新回放",
            value="2026-05-19 12:34:17",
            detail="6 条变化",
            stale_after_seconds=dashboard_data.REVIEW_LIFECYCLE_STALE_AFTER_SECONDS,
            stale_reason="lifecycle_snapshot_expired",
            now=now,
        )
        baseline = dashboard_data.build_review_source_card(
            key="review_baseline",
            label="基准研究",
            value="2026-04-15 20:10:05",
            detail="2024-01-02 -> 2024-03-29",
            stale_after_seconds=dashboard_data.REVIEW_RESEARCH_STALE_AFTER_SECONDS,
            stale_reason="research_review_expired",
            now=now,
        )
        latest = dashboard_data.build_review_source_card(
            key="review_latest",
            label="对比窗口",
            value="2026-04-15 20:10:04",
            detail="2024-03-01 -> 2024-03-29",
            stale_after_seconds=dashboard_data.REVIEW_RESEARCH_STALE_AFTER_SECONDS,
            stale_reason="research_review_expired",
            now=now,
        )

        self.assertFalse(lifecycle["stale"])
        self.assertEqual(lifecycle["age_label"], "5 分钟前")
        self.assertTrue(baseline["stale"])
        self.assertIn("research_review_expired", baseline["stale_reasons"])

        alerts = dashboard_data.build_review_freshness_alerts([lifecycle, baseline, latest])
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["title"], "历史 research 回看不是今天的实时环境")
        self.assertIn("2024-01-02 -> 2024-03-29", alerts[0]["trigger"])

    def test_reading_compass_can_name_review_research_as_historical(self) -> None:
        cards = dashboard_data.build_reading_compass_cards(
            conclusion="历史弱环境仍未转正",
            conclusion_detail="只用于复盘校准",
            conclusion_label="历史研究结论",
            action_focus="三条校准规则",
            action_detail="先看规则校准方向",
            risk_boundary="+0.83pct",
            risk_detail="-1.27% -> -0.44%",
            evidence_entry="研究与原始文件",
            evidence_detail="先看窗口和源文件",
        )

        self.assertEqual(cards[0]["label"], "历史研究结论")
        self.assertEqual(cards[0]["detail"], "只用于复盘校准")


if __name__ == "__main__":
    unittest.main()
