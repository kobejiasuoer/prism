from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[3]
CONTROL_PANEL_ROOT = REPO_ROOT / "apps" / "control-panel"
PACKAGES_ROOT = REPO_ROOT / "packages"
for import_path in (str(PACKAGES_ROOT), str(CONTROL_PANEL_ROOT)):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

import decision_ledger  # noqa: E402


def make_record(**overrides) -> dict:
    defaults = {
        "trade_date": "2026-05-15",
        "code": "sh600690",
        "name": "海尔智家",
        "lane": "watchlist",
        "surface": "today_action_queue",
        "action_key": "watchlist:600690",
        "source_label": "自选股",
        "action": "trial_buy",
        "action_label": "轻仓试错",
        "main_conclusion": "只做小仓验证。",
        "expected_trade_date": "2026-05-15",
        "data_trade_date": "2026-05-15",
        "readiness_mode": "live_ready",
        "readiness_ready": True,
        "decision_contract": {
            "schema_version": "decision_contract.v0",
            "contract_id": "dc:2026-05-15:test",
            "allowed_for_real_money": True,
        },
    }
    defaults.update(overrides)
    return decision_ledger.build_decision_record(**defaults)


def attach_outcome(record: dict, label: str, *, window: str = "T+1") -> dict:
    updated = dict(record)
    updated["outcome_events"] = [
        {
            "schema_version": decision_ledger.SCHEMA_VERSION,
            "event_id": f"outcome:{record['decision_id']}:{window}",
            "decision_id": record["decision_id"],
            "window": window,
            "as_of_trade_date": "2026-05-18",
            "evaluated_at": "2026-05-18 15:30:00",
            "classification": {"label": label, "tone": "negative"},
            "market_data": {"return_pct": -3.2},
        }
    ]
    return updated


def make_v2_record(
    *,
    code: str = "600001",
    suggested_action: str = "trial",
    opportunity_type: str = "pullback_acceptance",
    judge_source: str = "deterministic_baseline",
) -> dict:
    return decision_ledger.build_decision_record_from_opportunity_v2_record(
        {
            "trade_date": "2026-05-15",
            "code": code,
            "name": f"样本{code[-2:]}",
            "suggested_action": suggested_action,
            "action_label": suggested_action,
            "thesis": "主线回踩后承接重新成立。",
            "trigger": "站回触发位且资金不转负。",
            "invalidation": "跌破承接位取消。",
            "confidence": 0.78,
            "hard_gate_max_action": "actionable",
            "hard_gate_block_reason": "",
            "source_artifact": "/tmp/opportunity_v2_tracking.json",
            "judge_source": judge_source,
            "opportunity_type": opportunity_type,
        }
    )


class DecisionLedgerLearningLoopTest(unittest.TestCase):
    def test_decision_record_carries_contract_and_rule_version(self) -> None:
        record = make_record()

        self.assertEqual(record["decision_contract"]["schema_version"], "decision_contract.v0")
        self.assertEqual(record["rule_snapshot"]["ruleset_version"], decision_ledger.DECISION_RULESET_VERSION)
        self.assertEqual(record["rule_snapshot"]["learning_loop_version"], decision_ledger.LEARNING_LOOP_VERSION)
        self.assertEqual(record["rule_snapshot"]["outcome_windows"], ["T+1", "T+3", "T+5", "T+10"])

    def test_learning_loop_groups_by_ruleset_lane_action_and_suggests_review(self) -> None:
        records = [
            attach_outcome(make_record(action_key=f"watchlist:60069{i}", code=f"sh60069{i}"), "invalidated")
            for i in range(3)
        ]

        loop = decision_ledger.build_rule_learning_loop(records, as_of="2026-05-20")

        self.assertEqual(loop["version"], decision_ledger.LEARNING_LOOP_VERSION)
        self.assertEqual(loop["samples_total"], 3)
        self.assertEqual(loop["mature_samples"], 3)
        self.assertEqual(loop["pending_review_count"], 3)
        self.assertEqual(loop["buckets"][0]["ruleset_version"], decision_ledger.DECISION_RULESET_VERSION)
        self.assertEqual(loop["buckets"][0]["outcomes"]["invalidated"], 3)
        self.assertEqual(loop["suggestions"][0]["suggested_action"], "review_rule_threshold")

    def test_runtime_primary_reads_legacy_decisions_and_writes_updates_to_primary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            primary = root / "runtime_ledger"
            legacy = root / "legacy_ledger"
            record = make_record()
            legacy_decisions = legacy / "decisions"
            legacy_decisions.mkdir(parents=True)
            (legacy_decisions / "2026-05-15.json").write_text(
                json.dumps([record], ensure_ascii=False),
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {
                    "PRISM_DECISION_LEDGER_PATH": str(primary),
                    "PRISM_DECISION_LEDGER_LEGACY_PATH": str(legacy),
                },
            ):
                self.assertEqual(decision_ledger.load_decision(record["decision_id"])["decision_id"], record["decision_id"])

                event = decision_ledger.append_execution_event(
                    record["decision_id"],
                    {"status": "watch", "trade_date": "2026-05-15", "source": "test"},
                )
                self.assertEqual(event["status"], "watch")
                primary_file = primary / "decisions" / "2026-05-15.json"
                self.assertTrue(primary_file.exists())
                migrated = json.loads(primary_file.read_text(encoding="utf-8"))
                self.assertEqual(migrated[0]["decision_id"], record["decision_id"])
                self.assertEqual(migrated[0]["execution_events"][0]["status"], "watch")

                storage = decision_ledger.ledger_storage_status()
                self.assertEqual(storage["writes_to"], str(primary))
                self.assertIn(str(legacy), storage["reads_from"])

    def test_opportunity_v2_calibration_keeps_active_closed_with_insufficient_samples(self) -> None:
        records = [
            attach_outcome(make_v2_record(code=f"60000{i}"), "validated")
            for i in range(1, 3)
        ]

        calibration = decision_ledger.build_opportunity_v2_calibration(
            records=records,
            as_of="2026-05-20",
            min_mature_samples=3,
        )

        self.assertFalse(calibration["active_allowed"])
        self.assertEqual(calibration["mature_samples"], 2)
        self.assertEqual(calibration["sample_stage"], "observation_hypothesis")
        self.assertGreater(calibration["threshold_adjustments"]["trial"], 0)
        self.assertIn("active 暂不放开", calibration["guard_reason"])

    def test_opportunity_v2_calibration_allows_active_after_good_mature_samples(self) -> None:
        records = [
            attach_outcome(make_v2_record(code=f"60000{i}"), "validated")
            for i in range(1, 4)
        ]

        calibration = decision_ledger.build_opportunity_v2_calibration(
            records=records,
            as_of="2026-05-20",
            min_mature_samples=3,
        )

        self.assertTrue(calibration["active_allowed"])
        self.assertEqual(calibration["mature_samples"], 3)
        self.assertEqual(calibration["sample_stage"], "active_ready")
        self.assertEqual(calibration["threshold_adjustments"], {})
        self.assertEqual(calibration["playbooks"]["pullback_acceptance"]["action_cap"], "")

    def test_opportunity_v2_calibration_penalizes_weak_playbooks(self) -> None:
        records = [
            attach_outcome(make_v2_record(code=f"60001{i}"), "invalidated")
            for i in range(1, 4)
        ]

        calibration = decision_ledger.build_opportunity_v2_calibration(
            records=records,
            as_of="2026-05-20",
            min_mature_samples=3,
            min_playbook_samples=3,
        )

        playbook = calibration["playbooks"]["pullback_acceptance"]
        self.assertFalse(calibration["active_allowed"])
        self.assertEqual(calibration["sample_stage"], "needs_recalibration")
        self.assertEqual(playbook["action_cap"], "shadow")
        self.assertLess(playbook["confidence_adjustment"], 0)
        self.assertEqual(playbook["review_rate"], 1.0)

    def test_write_opportunity_v2_calibration_persists_snapshot(self) -> None:
        records = [
            attach_outcome(make_v2_record(code=f"60002{i}"), "validated")
            for i in range(1, 4)
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "opportunity_v2_calibration.json"

            payload = decision_ledger.write_opportunity_v2_calibration(
                records=records,
                path=path,
                as_of="2026-05-20",
                min_mature_samples=3,
            )

            self.assertEqual(payload["path"], str(path))
            self.assertTrue(path.exists())
            stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(stored["schema_version"], "opportunity_v2_calibration.1")
            self.assertTrue(stored["active_allowed"])
            self.assertEqual(stored["mature_samples"], 3)


if __name__ == "__main__":
    unittest.main()
