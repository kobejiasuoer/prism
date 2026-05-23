"""Phase 5 -- read-only Decision Ledger query API tests.

Covers the four new endpoints in ``app.py``:

* ``GET /api/decision-ledger/summary?window=7d`` -- aggregate counts
  over a trailing window.
* ``GET /api/decision-ledger/recent?limit=20`` -- most recent
  decisions plus their latest execution / outcome events.
* ``GET /api/decision-ledger/stock/{code}`` -- decision history for
  one stock; ``code`` accepts ``600690``, ``sh600690`` or
  ``sz000001`` forms.
* ``GET /api/decision-ledger/decision/{decision_id}`` -- raw
  DecisionRecord.

All four are read-only.  Corrupt ledger files surface either via an
``errors`` field (for scan-style endpoints) or via a 5xx response
(for the targeted detail endpoint), but they never silently disappear.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


CONTROL_PANEL_ROOT = Path(__file__).resolve().parents[1]
if str(CONTROL_PANEL_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROL_PANEL_ROOT))


def _sample_decision_inputs(**overrides):
    base = {
        "trade_date": "2026-05-15",
        "code": "sh600690",
        "name": "海尔智家",
        "lane": "watchlist",
        "surface": "today_action_queue",
        "action_key": "watchlist:600690",
        "source_label": "自选股链路",
        "action": "trial_buy",
        "action_label": "轻仓试错",
        "main_conclusion": "形态确认，轻仓试错",
        "expected_trade_date": "2026-05-15",
        "data_trade_date": "2026-05-15",
        "readiness_mode": "live_ready",
        "readiness_ready": True,
    }
    base.update(overrides)
    return base


class _LedgerApiTestBase(unittest.TestCase):
    """Shared setup: temp ledger root + reloaded modules + TestClient."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ledger_root = Path(self._tmp.name) / "decision_ledger"
        self.account_book_path = Path(self._tmp.name) / "account_book.json"
        self.scheduler_state_path = Path(self._tmp.name) / "scheduler_state.json"
        self.db_path = Path(self._tmp.name) / "prism.db"

        self._env = mock.patch.dict(
            os.environ,
            {
                "PRISM_DECISION_LEDGER_PATH": str(self.ledger_root),
                "PRISM_ACCOUNT_BOOK_PATH": str(self.account_book_path),
                "PRISM_REPO_ROOT": str(self._tmp.name),
                "PRISM_DB_PATH": str(self.db_path),
                "PRISM_SCHEDULER_STATE_PATH": str(self.scheduler_state_path),
            },
        )
        self._env.start()
        self.addCleanup(self._env.stop)

        # Force reload of modules that hold path config at import time.
        for mod_name in (
            "decision_ledger",
            "decision_ledger_providers",
            "app",
            "dashboard_data",
            "control_panel.dashboard_data",
        ):
            sys.modules.pop(mod_name, None)

        import decision_ledger  # type: ignore
        self.ledger = decision_ledger

        import app  # type: ignore
        from fastapi.testclient import TestClient  # type: ignore

        self.app_module = app
        self.client = TestClient(app.app)

    def _capture(self, **overrides) -> dict:
        record = self.ledger.build_decision_record(**_sample_decision_inputs(**overrides))
        return self.ledger.upsert_decision(record)

    def _attach_outcome(self, decision_id: str, *, window: str, label: str,
                       return_pct: float = 0.0, tone: str = "watch") -> None:
        self.ledger.append_outcome_event(
            decision_id,
            {
                "window": window,
                "as_of_trade_date": "2026-05-22",
                "market_data": {"return_pct": return_pct},
                "classification": {"label": label, "tone": tone},
                "quality": {"usable_for_decision_quality": label not in
                            {"data_issue", "inconclusive"}},
            },
        )


# ===========================================================================
# /api/decision-ledger/summary
# ===========================================================================


class SummaryApiTests(_LedgerApiTestBase):

    def test_empty_ledger_returns_zeroed_payload(self) -> None:
        resp = self.client.get("/api/decision-ledger/summary?window=7d")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["decisions"]["total"], 0)
        self.assertEqual(body["outcome_distribution"], {})
        self.assertEqual(body["execution_gap_count"], 0)
        self.assertEqual(body["data_issue_count"], 0)
        self.assertEqual(body["errors"], [])

    def test_summary_counts_decisions_and_outcomes_in_window(self) -> None:
        # Two decisions on 2026-05-15 within the 7d window ending 2026-05-22.
        d1 = self._capture(action="trial_buy", action_key="watchlist:600690", code="sh600690")
        d2 = self._capture(action="skip", action_key="watchlist:000001", code="sz000001")
        self._attach_outcome(d1["decision_id"], window="T+1", label="validated", return_pct=3.0)
        self._attach_outcome(d2["decision_id"], window="T+1", label="avoided_loss", return_pct=-2.5)
        self._attach_outcome(d2["decision_id"], window="T+3", label="avoided_loss", return_pct=-2.8)

        resp = self.client.get("/api/decision-ledger/summary?window=7d&as_of=2026-05-22")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["decisions"]["total"], 2)
        self.assertEqual(body["decisions"]["open"], 2)
        self.assertEqual(body["outcome_distribution"]["validated"], 1)
        self.assertEqual(body["outcome_distribution"]["avoided_loss"], 2)
        self.assertEqual(body["execution_events_total"], 0)
        self.assertEqual(body["outcome_events_total"], 3)

    def test_summary_excludes_decisions_outside_window(self) -> None:
        # 2026-05-01 is outside a 7d window ending 2026-05-22.
        self._capture(trade_date="2026-05-01", action_key="watchlist:600690")
        resp = self.client.get("/api/decision-ledger/summary?window=7d&as_of=2026-05-22")
        body = resp.json()
        self.assertEqual(body["decisions"]["total"], 0)

    def test_summary_counts_execution_gap_and_data_issue_separately(self) -> None:
        d1 = self._capture(action="trial_buy", action_key="watchlist:600690")
        d2 = self._capture(action="trial_buy", action_key="watchlist:000001", code="sz000001")
        self._attach_outcome(d1["decision_id"], window="T+1", label="execution_gap")
        self._attach_outcome(d2["decision_id"], window="T+1", label="data_issue")

        resp = self.client.get("/api/decision-ledger/summary?window=7d&as_of=2026-05-22")
        body = resp.json()
        self.assertEqual(body["execution_gap_count"], 1)
        self.assertEqual(body["data_issue_count"], 1)

    def test_corrupt_file_is_surfaced_under_errors(self) -> None:
        # Write a malformed JSON file directly into the decisions dir.
        decisions_dir = self.ledger_root / "decisions"
        decisions_dir.mkdir(parents=True, exist_ok=True)
        (decisions_dir / "2026-05-20.json").write_text("{not valid", encoding="utf-8")

        resp = self.client.get("/api/decision-ledger/summary?window=7d&as_of=2026-05-22")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["errors"])
        self.assertIn("2026-05-20.json", body["errors"][0]["file"])


# ===========================================================================
# /api/decision-ledger/calibration
# ===========================================================================


class CalibrationApiTests(_LedgerApiTestBase):

    def test_calibration_highlights_review_items_and_groups(self) -> None:
        invalid = self._capture(
            action="trial_buy",
            action_label="轻仓试错",
            action_key="watchlist:600690",
            lane="watchlist",
            code="sh600690",
        )
        data_issue = self._capture(
            action="observe",
            action_label="新增观察",
            action_key="midday:603986",
            lane="midday_confirmation",
            code="sh603986",
        )
        good = self._capture(
            action="hold",
            action_label="继续持有",
            action_key="watchlist:000001",
            lane="watchlist",
            code="sz000001",
        )
        self._attach_outcome(invalid["decision_id"], window="T+1", label="invalidated", tone="risk")
        self._attach_outcome(data_issue["decision_id"], window="T+1", label="data_issue", tone="warning")
        self._attach_outcome(good["decision_id"], window="T+1", label="validated", tone="positive")

        resp = self.client.get("/api/decision-ledger/calibration?window=7d&as_of=2026-05-22")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()

        self.assertEqual(body["overall"]["total"], 3)
        self.assertEqual(body["overall"]["evaluated"], 3)
        self.assertEqual(body["overall"]["validated"], 1)
        self.assertEqual(body["overall"]["invalidated"], 1)
        self.assertEqual(body["overall"]["data_issue"], 1)
        self.assertEqual(body["needs_review_count"], 2)
        self.assertEqual(
            {item["review_reason_key"] for item in body["needs_review"]},
            {"invalidated", "data_issue"},
        )
        lane_keys = {item["key"] for item in body["by_lane"]}
        self.assertEqual(lane_keys, {"watchlist", "midday_confirmation"})
        self.assertTrue(body["suggestion_cards"])
        self.assertIn("review_workbench", body)
        self.assertEqual(body["review_workbench"]["today_queue_count"], 2)
        self.assertEqual(body["review_workbench"]["ready_review_count"], 1)
        self.assertEqual(body["review_workbench"]["blocked_data_count"], 1)

    def test_calibration_tracks_non_overdue_pending_when_outcomes_missing(self) -> None:
        self._capture(action="observe", action_key="watchlist:600690")

        resp = self.client.get("/api/decision-ledger/calibration?window=7d&as_of=2026-05-16")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["overall"]["total"], 1)
        self.assertEqual(body["overall"]["pending"], 1)
        self.assertEqual(body["needs_review"], [])
        self.assertEqual(body["suggestion_cards"][0]["kind"], "pending")
        self.assertEqual(body["suggestion_cards"][0]["calibration_action"], "wait_for_sample")
        self.assertEqual(body["suggestion_cards"][0]["action_label"], "等待样本")
        self.assertEqual(body["review_workbench"]["pending_count"], 1)
        self.assertEqual(body["pending_reviews"][0]["review_status"], "pending_outcome")
        self.assertFalse(body["pending_reviews"][0]["is_overdue"])
        self.assertIn("outcome_events", body["pending_reviews"][0]["missing_fields"])
        self.assertTrue(body["pending_reviews"][0]["next_action_label"])

    def test_calibration_counts_superseded_decisions_as_review_needed(self) -> None:
        original = self._capture(action="observe", action_key="watchlist:600690")
        replacement = self._capture(action="trial_buy", action_key="watchlist:600690:retry")
        self.ledger.mark_decision_superseded(
            original["decision_id"],
            by=replacement["decision_id"],
        )

        resp = self.client.get("/api/decision-ledger/calibration?window=7d&as_of=2026-05-22")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()

        self.assertEqual(body["overall"]["total"], 2)
        self.assertEqual(body["overall"]["pending"], 2)
        self.assertEqual(body["overall"]["superseded"], 1)
        self.assertEqual(body["overall"]["review_needed"], 1)
        self.assertEqual(body["overall"]["review_rate"], 50.0)
        self.assertEqual(body["needs_review_count"], 1)
        self.assertEqual(body["needs_review"][0]["review_reason_key"], "superseded")
        self.assertEqual(body["by_lane"][0]["review_needed"], 1)

    def test_calibration_limit_keeps_total_and_prioritizes_failure_review(self) -> None:
        data_issue = self._capture(action="observe", action_key="watchlist:600690:data")
        invalid = self._capture(action="trial_buy", action_key="watchlist:600690:invalid")
        self._attach_outcome(data_issue["decision_id"], window="T+1", label="data_issue")
        self._attach_outcome(invalid["decision_id"], window="T+1", label="invalidated")

        resp = self.client.get("/api/decision-ledger/calibration?window=7d&as_of=2026-05-22&limit=1")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()

        self.assertEqual(body["needs_review_count"], 2)
        self.assertEqual(len(body["needs_review"]), 1)
        self.assertEqual(body["needs_review"][0]["review_reason_key"], "invalidated")

    def test_calibration_surfaces_corrupt_file_errors(self) -> None:
        decisions_dir = self.ledger_root / "decisions"
        decisions_dir.mkdir(parents=True, exist_ok=True)
        (decisions_dir / "2026-05-20.json").write_text("{not valid", encoding="utf-8")

        resp = self.client.get("/api/decision-ledger/calibration?window=7d&as_of=2026-05-22")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["errors"])
        self.assertIn("2026-05-20.json", body["errors"][0]["file"])

    def test_pending_execution_explains_missing_fields_and_next_action(self) -> None:
        self._capture(action="trial_buy", action_key="watchlist:600690")

        resp = self.client.get("/api/decision-ledger/calibration?window=7d&as_of=2026-05-16")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        pending = body["pending_reviews"][0]

        self.assertEqual(pending["review_status"], "pending_execution")
        self.assertIn("execution_events", pending["missing_fields"])
        self.assertIn("outcome_events", pending["missing_fields"])
        self.assertEqual(pending["calibration_action"], "fix_execution")
        self.assertEqual(pending["quality_axes"]["execution_quality"]["label"], "missing")
        self.assertTrue(pending["maturity_due_at"])
        self.assertTrue(pending["next_action_reason"])

    def test_overdue_pending_increases_priority_and_queue_count(self) -> None:
        self._capture(action="observe", action_key="watchlist:600690")

        resp = self.client.get("/api/decision-ledger/calibration?window=7d&as_of=2026-05-22")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        pending = body["pending_reviews"][0]

        self.assertTrue(pending["is_overdue"])
        self.assertGreaterEqual(pending["priority_score"], 35)
        self.assertIn("pending 已过成熟日", pending["priority_reasons"])
        self.assertEqual(pending["calibration_action"], "run_outcome_evaluator")
        self.assertEqual(pending["next_action_label"], "补跑结果评估")
        self.assertIn("outcome evaluator", pending["next_action_reason"])
        self.assertEqual(body["review_workbench"]["overdue_count"], 1)
        self.assertEqual(body["review_workbench"]["today_queue_count"], 1)
        self.assertEqual(body["review_workbench"]["system_learning_state"], "outcome_overdue")
        self.assertEqual(body["suggestion_cards"][0]["kind"], "outcome_overdue")
        self.assertEqual(body["suggestion_cards"][0]["calibration_action"], "run_outcome_evaluator")
        self.assertEqual(body["suggestion_cards"][0]["action_label"], "补跑结果评估")
        self.assertIn("学习闭环", body["suggestion_cards"][0]["action_reason"])
        self.assertNotIn("等待样本", {card["action_label"] for card in body["suggestion_cards"]})

    def test_execution_gap_enters_ready_review_queue(self) -> None:
        decision = self._capture(action="trial_buy", action_key="watchlist:600690")
        self.ledger.append_execution_event(
            decision["decision_id"],
            {"status": "no_fill", "trade_date": "2026-05-15", "note": "price never touched"},
        )
        self._attach_outcome(decision["decision_id"], window="T+1", label="execution_gap")

        resp = self.client.get("/api/decision-ledger/calibration?window=7d&as_of=2026-05-22")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        item = body["needs_review"][0]

        self.assertEqual(item["review_reason_key"], "execution_gap")
        self.assertEqual(item["review_status"], "ready_review")
        self.assertEqual(item["calibration_action"], "fix_execution")
        self.assertEqual(body["ready_reviews"][0]["decision_id"], decision["decision_id"])

    def test_suggestion_cards_are_action_oriented(self) -> None:
        invalid = self._capture(action="trial_buy", action_key="watchlist:600690")
        self._attach_outcome(invalid["decision_id"], window="T+1", label="invalidated")

        resp = self.client.get("/api/decision-ledger/calibration?window=7d&as_of=2026-05-22")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()

        self.assertTrue(body["suggestion_cards"])
        card = body["suggestion_cards"][0]
        self.assertIn(
            card["calibration_action"],
            {
                "keep_rule",
                "tighten_rule",
                "loosen_rule",
                "add_guardrail",
                "wait_for_sample",
                "run_outcome_evaluator",
                "fix_execution",
                "fix_data",
                "investigate_pattern",
            },
        )
        self.assertIn("evidence_strength", card)
        self.assertIn("insufficient_sample", card)


# ===========================================================================
# /api/decision-ledger/review-case
# ===========================================================================


class ReviewCaseApiTests(_LedgerApiTestBase):

    def test_attribution_draft_returns_structured_heuristic_without_saving(self) -> None:
        decision = self._capture(
            action="observe",
            action_label="新增观察",
            action_key="midday:603986:draft",
            lane="midday_confirmation",
            code="sh603986",
            name="兆易创新",
        )
        self._attach_outcome(
            decision["decision_id"],
            window="T+1",
            label="missed_opportunity",
            return_pct=6.57,
            tone="warning",
        )

        resp = self.client.post(
            f"/api/decision-ledger/review-case/{decision['decision_id']}/attribution-draft"
        )
        self.assertEqual(resp.status_code, 200)
        draft = resp.json()["draft"]

        self.assertEqual(draft["primary_cause"], "too_strict")
        self.assertEqual(draft["conclusion_action"], "wait_more_samples")
        self.assertEqual(draft["follow_up_status"], "sample_insufficient")
        self.assertEqual(draft["sample_count"], 1)
        self.assertEqual(draft["evidence_strength"], "observation_hypothesis")
        self.assertFalse(draft["rule_action_allowed"])
        self.assertIn("AI provider not configured", draft["fallback_reason"])
        self.assertTrue(draft["evidence"])
        self.assertTrue(draft["human_check_required"])

        workbench = self.client.get(f"/api/decision-ledger/review-case/{decision['decision_id']}")
        self.assertEqual(workbench.status_code, 200)
        self.assertIsNone(workbench.json()["review_case"])

    def test_single_sample_direct_rule_draft_is_downgraded(self) -> None:
        decision = self._capture(
            action="hold",
            action_label="继续持有",
            action_key="watchlist:603986:invalidated",
            lane="watchlist",
            code="sh603986",
            name="兆易创新",
        )
        self._attach_outcome(
            decision["decision_id"],
            window="T+1",
            label="invalidated",
            return_pct=-6.1,
            tone="risk",
        )

        resp = self.client.post(
            f"/api/decision-ledger/review-case/{decision['decision_id']}/attribution-draft"
        )
        self.assertEqual(resp.status_code, 200)
        draft = resp.json()["draft"]

        self.assertEqual(draft["primary_cause"], "too_loose")
        self.assertEqual(draft["conclusion_action"], "wait_more_samples")
        self.assertIn("不生成可执行规则修改", draft["rule_hypothesis"])
        self.assertEqual(draft["evidence_strength"], "observation_hypothesis")

    def test_save_review_case_records_ai_draft_human_final_and_overrides(self) -> None:
        decision = self._capture(
            action="observe",
            action_label="新增观察",
            action_key="midday:600584:override",
            lane="midday_confirmation",
            code="sh600584",
            name="长电科技",
        )
        self._attach_outcome(
            decision["decision_id"],
            window="T+1",
            label="missed_opportunity",
            return_pct=5.8,
            tone="warning",
        )
        draft = self.client.post(
            f"/api/decision-ledger/review-case/{decision['decision_id']}/attribution-draft"
        ).json()["draft"]

        resp = self.client.post(
            f"/api/decision-ledger/review-case/{decision['decision_id']}",
            json={
                "primary_cause": draft["primary_cause"],
                "secondary_causes": ["volume_too_conservative"],
                "review_note": "人工确认后改写备注。",
                "conclusion_action": draft["conclusion_action"],
                "rule_hypothesis": draft["rule_hypothesis"],
                "follow_up_status": draft["follow_up_status"],
                "ai_draft": draft,
                "attribution_confidence": draft["confidence"],
                "evidence_refs": draft["evidence"],
                "human_check_required": draft["human_check_required"],
                "similar_case_refs": draft["similar_case_refs"],
            },
        )
        self.assertEqual(resp.status_code, 200)
        case = resp.json()["review_case"]

        self.assertEqual(case["ai_draft"]["draft_id"], draft["draft_id"])
        self.assertEqual(case["human_final"]["review_note"], "人工确认后改写备注。")
        self.assertIn("review_note", case["human_overrides"])
        self.assertEqual(case["attribution_confidence"], draft["confidence"])
        self.assertEqual(case["evidence_refs"], draft["evidence"])
        self.assertEqual(case["human_check_required"], draft["human_check_required"])

    def test_save_review_case_persists_and_removes_item_from_ready_queue(self) -> None:
        decision = self._capture(
            action="observe",
            action_label="新增观察",
            action_key="midday:603986",
            lane="midday_confirmation",
            code="sh603986",
            name="兆易创新",
        )
        self._attach_outcome(
            decision["decision_id"],
            window="T+1",
            label="missed_opportunity",
            tone="warning",
        )

        before = self.client.get("/api/decision-ledger/calibration?window=7d&as_of=2026-05-22")
        self.assertEqual(before.status_code, 200)
        self.assertEqual(before.json()["needs_review_count"], 1)

        resp = self.client.post(
            f"/api/decision-ledger/review-case/{decision['decision_id']}",
            json={
                "primary_cause": "too_strict",
                "secondary_causes": ["volume_too_conservative", "risk_condition_not_triggered"],
                "review_note": "承接并未走坏，先记录为观察。",
                "conclusion_action": "loosen_filter",
                "rule_hypothesis": "类似放量承接形态后续不应直接排除。",
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        case = body["review_case"]

        self.assertEqual(case["decision_id"], decision["decision_id"])
        self.assertEqual(case["primary_cause"], "too_strict")
        self.assertEqual(case["sample_count"], 1)
        self.assertEqual(case["evidence_strength"], "observation_hypothesis")
        self.assertEqual(case["follow_up_status"], "sample_insufficient")
        self.assertFalse(case["rule_action_allowed"])
        self.assertIn("不生成可执行规则修改", case["rule_hypothesis"])

        after = self.client.get("/api/decision-ledger/calibration?window=7d&as_of=2026-05-22")
        self.assertEqual(after.status_code, 200)
        payload = after.json()
        self.assertEqual(payload["needs_review_count"], 0)
        self.assertEqual(payload["review_workbench"]["ready_review_count"], 0)
        self.assertEqual(payload["reviewed_case_count"], 1)
        self.assertEqual(payload["review_records"][0]["review_status"], "reviewed")
        self.assertEqual(payload["review_records"][0]["review_case"]["primary_cause"], "too_strict")
        self.assertEqual(payload["review_case_patterns"][0]["sample_count"], 1)

        workbench = self.client.get(f"/api/decision-ledger/review-case/{decision['decision_id']}")
        self.assertEqual(workbench.status_code, 200)
        self.assertEqual(workbench.json()["review_case"]["review_case_id"], case["review_case_id"])

    def test_review_case_patterns_move_from_observation_to_validation(self) -> None:
        first = self._capture(
            action="observe",
            action_key="midday:603986:first",
            lane="midday_confirmation",
            code="sh603986",
        )
        second = self._capture(
            action="observe",
            action_key="midday:600584:second",
            lane="midday_confirmation",
            code="sh600584",
            name="长电科技",
        )
        self._attach_outcome(first["decision_id"], window="T+1", label="missed_opportunity")
        self._attach_outcome(second["decision_id"], window="T+1", label="missed_opportunity")

        for decision in (first, second):
            resp = self.client.post(
                f"/api/decision-ledger/review-case/{decision['decision_id']}",
                json={
                    "primary_cause": "too_strict",
                    "secondary_causes": ["capital_flow_filter_strict"],
                    "review_note": "同链路 observe 样本继续观察。",
                    "conclusion_action": "wait_more_samples",
                },
            )
            self.assertEqual(resp.status_code, 200)

        cases = self.client.get("/api/decision-ledger/review-cases")
        self.assertEqual(cases.status_code, 200)
        pattern = cases.json()["patterns"][0]
        self.assertEqual(pattern["sample_count"], 2)
        self.assertEqual(pattern["evidence_strength"], "validating_pattern")
        self.assertEqual(pattern["follow_up_status"], "observing")
        self.assertFalse(pattern["rule_action_allowed"])
        self.assertEqual(pattern["dominant_conclusion_action"], "wait_more_samples")
        self.assertEqual(pattern["stock_count"], 2)
        self.assertEqual(pattern["dominant_secondary_causes"], ["capital_flow_filter_strict"])
        self.assertIn("不能自动修改交易规则", pattern["learning_hint"])

        third = self._capture(
            action="observe",
            action_key="midday:688981:third",
            lane="midday_confirmation",
            code="sh688981",
            name="中芯国际",
        )
        self._attach_outcome(third["decision_id"], window="T+1", label="missed_opportunity")
        draft = self.client.post(
            f"/api/decision-ledger/review-case/{third['decision_id']}/attribution-draft"
        )
        self.assertEqual(draft.status_code, 200)
        body = draft.json()["draft"]
        self.assertTrue(body["similar_case_refs"])
        self.assertTrue(body["pattern_memory_refs"])


# ===========================================================================
# /api/tasks/decision_ledger_outcomes/run
# ===========================================================================


class DecisionLedgerOutcomeTaskTests(_LedgerApiTestBase):

    def test_decision_ledger_outcome_task_can_be_started_from_review(self) -> None:
        with mock.patch.object(
            self.app_module,
            "launch_background_task",
            return_value={
                "started": True,
                "run_id": "decision_ledger_outcomes_manual",
                "task_name": "decision_ledger_outcomes",
                "title": "Decision Ledger 结果评估",
            },
        ) as launch:
            resp = self.client.post(
                "/api/tasks/decision_ledger_outcomes/run",
                json={"reason": "manual_from_review_learning_workbench"},
            )

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["canonical_task_name"], "decision_ledger_outcomes")
        kwargs = launch.call_args.kwargs
        self.assertEqual(kwargs["task_name"], "decision_ledger_outcomes")
        self.assertIn("evaluate_decision_ledger.py", kwargs["command"][-1])


# ===========================================================================
# /api/decision-ledger/recent
# ===========================================================================


class RecentApiTests(_LedgerApiTestBase):

    def test_empty_returns_empty_items(self) -> None:
        resp = self.client.get("/api/decision-ledger/recent")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["items"], [])
        self.assertEqual(body["count"], 0)
        self.assertEqual(body["errors"], [])

    def test_recent_returns_decisions_newest_first(self) -> None:
        self._capture(trade_date="2026-05-08", action_key="watchlist:600690")
        self._capture(trade_date="2026-05-15", action_key="watchlist:000001", code="sz000001")
        resp = self.client.get("/api/decision-ledger/recent?limit=20")
        body = resp.json()
        self.assertEqual(len(body["items"]), 2)
        self.assertEqual(body["items"][0]["trade_date"], "2026-05-15")
        self.assertEqual(body["items"][1]["trade_date"], "2026-05-08")

    def test_recent_includes_latest_outcome_and_execution(self) -> None:
        d = self._capture()
        self.ledger.append_execution_event(
            d["decision_id"],
            {"status": "filled", "side": "buy", "price": 10.5, "quantity": 100,
             "trade_date": "2026-05-15"},
        )
        self._attach_outcome(d["decision_id"], window="T+1", label="validated", return_pct=2.5)
        self._attach_outcome(d["decision_id"], window="T+3", label="validated", return_pct=4.2)

        resp = self.client.get("/api/decision-ledger/recent?limit=5")
        body = resp.json()
        card = body["items"][0]
        self.assertEqual(card["execution_events_count"], 1)
        self.assertEqual(card["outcome_events_count"], 2)
        # T+3 wins over T+1 in the "latest_outcome" pick.
        self.assertEqual(card["latest_outcome"]["window"], "T+3")
        self.assertEqual(card["latest_outcome"]["label"], "validated")
        self.assertEqual(card["latest_execution"]["status"], "filled")
        self.assertEqual(card["latest_execution"]["side"], "buy")

    def test_recent_respects_limit(self) -> None:
        for n in range(5):
            self._capture(
                trade_date=f"2026-05-{10 + n:02d}",
                action_key=f"watchlist:60069{n}",
                code=f"sh60069{n}",
            )
        resp = self.client.get("/api/decision-ledger/recent?limit=2")
        body = resp.json()
        self.assertEqual(len(body["items"]), 2)
        self.assertEqual(body["count"], 2)

    def test_recent_with_corrupt_file_degrades_with_errors(self) -> None:
        self._capture()
        decisions_dir = self.ledger_root / "decisions"
        (decisions_dir / "2026-05-20.json").write_text("garbage", encoding="utf-8")

        resp = self.client.get("/api/decision-ledger/recent?limit=20")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        # The good file still produced a card; the bad one is surfaced.
        self.assertEqual(len(body["items"]), 1)
        self.assertTrue(body["errors"])

    def test_invalid_limit_falls_back_to_safe_default(self) -> None:
        # Negative / zero limit should not 500 -- the API clamps.
        resp = self.client.get("/api/decision-ledger/recent?limit=0")
        self.assertEqual(resp.status_code, 200)


# ===========================================================================
# /api/decision-ledger/stock/{code}
# ===========================================================================


class StockApiTests(_LedgerApiTestBase):

    def test_plain_code_resolves_to_prefixed_records(self) -> None:
        self._capture(code="sh600690", action_key="watchlist:600690")
        resp = self.client.get("/api/decision-ledger/stock/600690")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["code"], "sh600690")
        self.assertEqual(len(body["items"]), 1)

    def test_prefixed_code_works(self) -> None:
        self._capture(code="sh600690", action_key="watchlist:600690")
        resp = self.client.get("/api/decision-ledger/stock/sh600690")
        body = resp.json()
        self.assertEqual(body["code"], "sh600690")
        self.assertEqual(len(body["items"]), 1)

    def test_shenzhen_code_works(self) -> None:
        self._capture(code="sz000001", action_key="watchlist:000001")
        resp = self.client.get("/api/decision-ledger/stock/sz000001")
        body = resp.json()
        self.assertEqual(body["code"], "sz000001")
        self.assertEqual(len(body["items"]), 1)

    def test_unknown_code_returns_empty_items(self) -> None:
        resp = self.client.get("/api/decision-ledger/stock/sh999999")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["items"], [])
        self.assertEqual(body["count"], 0)

    def test_malformed_code_returns_400(self) -> None:
        resp = self.client.get("/api/decision-ledger/stock/garbage")
        self.assertEqual(resp.status_code, 400)

    def test_stock_includes_outcome_summary(self) -> None:
        d = self._capture(code="sh600690", action_key="watchlist:600690")
        self._attach_outcome(d["decision_id"], window="T+1", label="validated", return_pct=3.5)

        resp = self.client.get("/api/decision-ledger/stock/sh600690")
        body = resp.json()
        card = body["items"][0]
        self.assertEqual(card["latest_outcome"]["label"], "validated")


# ===========================================================================
# /api/decision-ledger/decision/{decision_id}
# ===========================================================================


class DecisionDetailApiTests(_LedgerApiTestBase):

    def test_returns_full_record(self) -> None:
        d = self._capture()
        resp = self.client.get(f"/api/decision-ledger/decision/{d['decision_id']}")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        # Same shape as the on-disk record (full DecisionRecord).
        self.assertEqual(body["decision_id"], d["decision_id"])
        self.assertEqual(body["stock"]["code"], "sh600690")
        self.assertIn("evidence_snapshot", body)
        self.assertIn("parameter_snapshot", body)
        self.assertEqual(body["execution_events"], [])
        self.assertEqual(body["outcome_events"], [])

    def test_returns_404_for_unknown_id(self) -> None:
        resp = self.client.get(
            "/api/decision-ledger/decision/2026-05-15:sh999999:today_action_queue:watchlist:deadbeef"
        )
        self.assertEqual(resp.status_code, 404)

    def test_returns_400_for_malformed_id(self) -> None:
        # No leading YYYY-MM-DD -> bad id.
        resp = self.client.get("/api/decision-ledger/decision/not-a-real-id")
        self.assertEqual(resp.status_code, 400)

    def test_corrupt_target_file_returns_500_with_detail(self) -> None:
        d = self._capture()
        # Corrupt the file that hosts this decision.
        file_path = self.ledger_root / "decisions" / f"{d['trade_date']}.json"
        file_path.write_text("not json", encoding="utf-8")

        resp = self.client.get(f"/api/decision-ledger/decision/{d['decision_id']}")
        self.assertEqual(resp.status_code, 500)
        body = resp.json()
        # Detail should reference the ledger error so the operator can fix.
        self.assertIn("ledger", body.get("detail", "").lower())


if __name__ == "__main__":
    unittest.main()
