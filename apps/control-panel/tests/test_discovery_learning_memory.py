from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


INVEST_FLOW_ROOT = Path(__file__).resolve().parents[2]
CONTROL_PANEL_ROOT = INVEST_FLOW_ROOT / "control-panel"
if str(INVEST_FLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(INVEST_FLOW_ROOT))
if str(CONTROL_PANEL_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROL_PANEL_ROOT))


class DiscoveryLearningMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.ledger_root = root / "decision_ledger"

        self._env = mock.patch.dict(
            os.environ,
            {
                "PRISM_DECISION_LEDGER_PATH": str(self.ledger_root),
                "PRISM_ACCOUNT_BOOK_PATH": str(root / "account_book.json"),
                "PRISM_REPO_ROOT": str(root),
                "PRISM_DB_PATH": str(root / "prism.db"),
                "PRISM_SCHEDULER_STATE_PATH": str(root / "scheduler_state.json"),
            },
        )
        self._env.start()
        self.addCleanup(self._env.stop)

        for mod_name in (
            "decision_ledger",
            "dashboard_data",
            "control_panel.dashboard_data",
        ):
            sys.modules.pop(mod_name, None)

        import decision_ledger  # type: ignore
        from control_panel import dashboard_data  # type: ignore

        self.ledger = decision_ledger
        self.dashboard_data = dashboard_data

    def _save_missed_opportunity_case(self, *, code: str, name: str, suffix: str) -> dict:
        record = self.ledger.build_decision_record(
            trade_date="2026-05-15",
            code=f"sh{code}",
            name=name,
            lane="midday_confirmation",
            surface="today_action_queue",
            action_key=f"confirmation:{code}:{suffix}",
            source_label="午盘新增",
            action="observe",
            action_label="新增观察",
            action_raw="新增观察",
            main_conclusion="午盘新增观察，先看承接。",
            expected_trade_date="2026-05-15",
            data_trade_date="2026-05-15",
            readiness_mode="live_ready",
            readiness_ready=True,
        )
        saved = self.ledger.upsert_decision(record)
        self.ledger.append_outcome_event(
            saved["decision_id"],
            {
                "window": "T+1",
                "as_of_trade_date": "2026-05-18",
                "market_data": {"return_pct": 6.2},
                "classification": {"label": "missed_opportunity", "tone": "warning"},
                "quality": {"usable_for_decision_quality": True},
            },
        )
        return self.ledger.save_review_case(
            saved["decision_id"],
            {
                "primary_cause": "too_strict",
                "secondary_causes": ["volume_too_conservative"],
                "review_note": "承接没有走坏，量能过滤偏保守。",
                "conclusion_action": "wait_more_samples",
                "rule_hypothesis": "类似放量承接形态后续不应直接排除。",
            },
        )

    def test_confirmation_candidate_card_reuses_review_pattern_memory(self) -> None:
        self._save_missed_opportunity_case(code="603986", name="兆易创新", suffix="first")
        self._save_missed_opportunity_case(code="600584", name="长电科技", suffix="second")

        index = self.dashboard_data.build_review_learning_memory_index()
        card = self.dashboard_data.build_confirmation_candidate_card(
            {
                "code": "688981",
                "name": "中芯国际",
                "status": "fresh_candidate",
                "theme": "半导体",
                "entry_reason": "午盘新增观察，先看承接。",
            },
            learning_index=index,
        )

        memories = card.get("learning_memories") or []
        self.assertTrue(memories)
        self.assertEqual(memories[0]["kind"], "pattern")
        self.assertEqual(memories[0]["primary_cause"], "too_strict")
        self.assertIn("量能判断偏保守", memories[0]["secondary_cause_labels"])
        self.assertIn("不能自动修改交易规则", memories[0]["summary"])

    def test_same_stock_review_case_is_prioritized_before_pattern(self) -> None:
        self._save_missed_opportunity_case(code="603986", name="兆易创新", suffix="first")
        self._save_missed_opportunity_case(code="600584", name="长电科技", suffix="second")

        index = self.dashboard_data.build_review_learning_memory_index()
        card = self.dashboard_data.build_confirmation_candidate_card(
            {
                "code": "603986",
                "name": "兆易创新",
                "status": "fresh_candidate",
                "entry_reason": "午盘新增观察，先看承接。",
            },
            learning_index=index,
        )

        memories = card.get("learning_memories") or []
        self.assertTrue(memories)
        self.assertEqual(memories[0]["kind"], "stock_case")
        self.assertEqual(memories[0]["stock_name"], "兆易创新")


if __name__ == "__main__":
    unittest.main()
