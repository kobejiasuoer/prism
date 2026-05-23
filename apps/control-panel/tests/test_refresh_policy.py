from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient


INVEST_FLOW_ROOT = Path(__file__).resolve().parents[2]
if str(INVEST_FLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(INVEST_FLOW_ROOT))

import control_panel.app as app_module  # noqa: E402
from control_panel.app import app  # noqa: E402
from refresh_policy import CRON_POLICIES, current_market_mode, active_auto_windows, evaluate_auto_refresh, task_conflict_is_running, validate_cron_policies  # noqa: E402


LEGACY_APP_MODULE = app_module.__dict__.get("_legacy_module", app_module)


class FakeAppStateRepository:
    def __init__(self) -> None:
        self.payload: dict[str, object] | None = None

    def get(self, key: str, *, legacy_path=None, default=None):
        return self.payload if self.payload is not None else default

    def set(self, key: str, payload, *, legacy_path=None, schema_version: int = 1):
        self.payload = payload
        return payload


def _freshness_row(*, key: str = "watchlist", reasons: list[str] | None = None) -> dict[str, object]:
    return {
        "key": key,
        "label": key,
        "available": True,
        "stale": True,
        "stale_reasons": reasons or ["freshness_expired"],
    }


def _cooldown(remaining: int = 0) -> dict[str, object]:
    return {
        "seconds": 900,
        "remaining_seconds": remaining,
        "ready": remaining == 0,
        "next_allowed_at": "2026-05-08 10:15:00" if remaining else "",
    }


class RefreshPolicyDecisionTests(unittest.TestCase):
    def test_aggressive_cron_generates_lifecycle_snapshot(self) -> None:
        aggressive = next(item for item in CRON_POLICIES if item.task_name == "aggressive")
        self.assertIn("--lifecycle", aggressive.command)

    def test_stale_manifest_recommends_watchlist_refresh(self) -> None:
        payload = LEGACY_APP_MODULE.build_refresh_status_payload("today", now=datetime(2026, 5, 8, 10, 0, 0))
        self.assertIn("recommended_task", payload)
        self.assertIn(payload["recommended_task"]["task_name"], payload.get("recommended_tasks") or [])
        self.assertIn("auto_refresh", payload)
        self.assertIn("cooldown", payload)
        self.assertIn("next_allowed_at", payload["cooldown"])

    def test_cooldown_prevents_auto_trigger(self) -> None:
        decision = evaluate_auto_refresh(
            page="today",
            recommended_task="watchlist_refresh",
            freshness=[_freshness_row()],
            readiness_payload={"ready": False},
            running=[],
            cooldown=_cooldown(remaining=300),
            now=datetime(2026, 5, 8, 10, 0, 0),
        )
        self.assertFalse(decision["should_trigger"])
        self.assertIn("cooldown", decision["blocked_reasons"])

    def test_running_same_family_prevents_auto_trigger(self) -> None:
        decision = evaluate_auto_refresh(
            page="today",
            recommended_task="preclose_risk_refresh",
            freshness=[_freshness_row()],
            readiness_payload={"ready": False},
            running=[{"task_name": "command_brief", "status": "running"}],
            cooldown=_cooldown(),
            force=True,
            now=datetime(2026, 5, 8, 14, 50, 0),
        )
        self.assertFalse(decision["should_trigger"])
        self.assertIn("running", decision["blocked_reasons"])

    def test_watchlist_refresh_blocks_command_brief_overlap(self) -> None:
        running = [{"task_name": "watchlist_refresh", "status": "running"}]

        self.assertTrue(task_conflict_is_running("command_brief", running))
        decision = evaluate_auto_refresh(
            page="today",
            recommended_task="command_brief",
            freshness=[_freshness_row(key="decision_brief", reasons=["trade_date_mismatch"])],
            readiness_payload={"ready": False},
            running=running,
            cooldown=_cooldown(),
            force=True,
            now=datetime(2026, 5, 8, 10, 0, 0),
        )
        self.assertFalse(decision["should_trigger"])
        self.assertIn("running", decision["blocked_reasons"])

    def test_outside_window_prevents_auto_trigger(self) -> None:
        decision = evaluate_auto_refresh(
            page="today",
            recommended_task="watchlist_refresh",
            freshness=[_freshness_row()],
            readiness_payload={"ready": False},
            running=[],
            cooldown=_cooldown(),
            now=datetime(2026, 5, 8, 12, 0, 0),
        )
        self.assertFalse(decision["should_trigger"])
        self.assertIn("outside_auto_window", decision["blocked_reasons"])

    def test_exchange_holiday_is_off_and_blocks_auto_trigger(self) -> None:
        holiday_midmorning = datetime(2026, 5, 1, 10, 0, 0)

        market_mode, market_label = current_market_mode(holiday_midmorning)
        decision = evaluate_auto_refresh(
            page="today",
            recommended_task="watchlist_refresh",
            freshness=[_freshness_row()],
            readiness_payload={"ready": False},
            running=[],
            cooldown=_cooldown(),
            now=holiday_midmorning,
        )

        self.assertEqual(market_mode, "off")
        self.assertEqual(market_label, "交易所休市")
        self.assertEqual(active_auto_windows(holiday_midmorning), [])
        self.assertFalse(decision["should_trigger"])
        self.assertIn("non_trading_day", decision["blocked_reasons"])
        self.assertEqual(decision["calendar_status"]["status"], "holiday")


class RefreshPolicyApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_refresh_status_exposes_cooldown_and_auto_reason_fields(self) -> None:
        response = self.client.get("/api/refresh/status?page=today")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("auto_refresh", payload)
        self.assertIn("blocked_reasons", payload["auto_refresh"])
        self.assertIn("summary", payload["auto_refresh"])
        self.assertIn("next_allowed_at", payload["cooldown"])
        self.assertIn("last_auto_refresh", payload)
        self.assertIn("policy", payload)
        self.assertIn("policy_catalog", payload)
        self.assertIn("scheduler_status", payload)
        self.assertIn("jobs", payload["scheduler_status"])

    def test_scheduler_status_endpoint_exposes_guardrail_fields(self) -> None:
        response = self.client.get("/api/scheduler/status")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("scheduler", payload)
        self.assertIn("summary", payload)
        self.assertIn("jobs", payload)
        self.assertTrue(any(job.get("task_name") == "morning_warmup" for job in payload["jobs"]))
        warmup = next(job for job in payload["jobs"] if job.get("task_name") == "morning_warmup")
        self.assertTrue(warmup.get("catchup_enabled"))
        self.assertEqual(warmup.get("retry_attempts"), 2)

    def test_auto_status_starts_when_policy_allows(self) -> None:
        repository = FakeAppStateRepository()
        with tempfile.TemporaryDirectory() as tmpdir:
            previous_state_path = LEGACY_APP_MODULE.REFRESH_STATE_PATH
            LEGACY_APP_MODULE.REFRESH_STATE_PATH = Path(tmpdir) / "refresh_state.json"
            try:
                with mock.patch.object(LEGACY_APP_MODULE, "APP_STATE_REPOSITORY", repository), mock.patch.object(
                    LEGACY_APP_MODULE,
                    "list_runs",
                    return_value=[],
                ), mock.patch.object(
                    LEGACY_APP_MODULE,
                    "read_page_source_cards",
                    return_value=[],
                ), mock.patch.object(
                    LEGACY_APP_MODULE,
                    "_dataset_manifest_freshness_rows",
                    return_value=[_freshness_row(key="watchlist")],
                ), mock.patch.object(
                    LEGACY_APP_MODULE,
                    "build_today_view",
                    return_value={
                        "readiness": {
                            "ready": False,
                            "readiness_mode": "blocked",
                            "stale_count": 1,
                            "expected_trade_date": "2026-05-08",
                            "recommended_tasks": ["watchlist_refresh"],
                            "source_freshness": [_freshness_row(key="watchlist")],
                            "blockers": [],
                            "warnings": [],
                        }
                    },
                ), mock.patch.object(
                    LEGACY_APP_MODULE,
                    "launch_background_task",
                    return_value={"started": True, "run_id": "auto-run", "task_name": "watchlist_refresh"},
                ):
                    payload = LEGACY_APP_MODULE.build_refresh_status_payload(
                        "today",
                        auto=True,
                        now=datetime(2026, 5, 8, 10, 0, 0),
                    )
                    state = LEGACY_APP_MODULE.load_refresh_state()
                self.assertTrue(payload["auto_refresh"]["triggered"])
                self.assertEqual(state["tasks"]["watchlist_refresh"]["trigger_type"], "auto")
                self.assertEqual(state["audit_events"][-1]["trigger_type"], "auto")
            finally:
                LEGACY_APP_MODULE.REFRESH_STATE_PATH = previous_state_path

    def test_force_refresh_records_audit(self) -> None:
        repository = FakeAppStateRepository()
        with tempfile.TemporaryDirectory() as tmpdir:
            previous_state_path = LEGACY_APP_MODULE.REFRESH_STATE_PATH
            LEGACY_APP_MODULE.REFRESH_STATE_PATH = Path(tmpdir) / "refresh_state.json"
            try:
                with mock.patch.object(LEGACY_APP_MODULE, "APP_STATE_REPOSITORY", repository), mock.patch.object(
                    LEGACY_APP_MODULE,
                    "build_refresh_status_payload",
                ) as fake_status, mock.patch.object(
                    LEGACY_APP_MODULE,
                    "list_runs",
                    return_value=[],
                ), mock.patch.object(
                    LEGACY_APP_MODULE,
                    "launch_background_task",
                    return_value={"started": True, "run_id": "manual-run", "task_name": "watchlist_refresh"},
                ):
                    base_status = {
                        "page": "today",
                        "running": [],
                        "freshness": [_freshness_row(key="watchlist")],
                        "recommended_task": {"task_name": "watchlist_refresh", "title": "自选股全流程刷新"},
                        "cooldown": {
                            "seconds": 900,
                            "remaining_seconds": 800,
                            "ready": False,
                            "next_allowed_at": (datetime.now() + timedelta(seconds=800)).strftime("%Y-%m-%d %H:%M:%S"),
                        },
                        "readiness": {"ready": False},
                    }
                    fake_status.side_effect = [base_status, {**base_status, "cooldown": _cooldown()}]
                    response = self.client.post(
                        "/api/refresh/trigger",
                        json={"page": "today", "task_name": "watchlist_refresh", "force": True, "reason": "test_force"},
                    )
                    state = LEGACY_APP_MODULE.load_refresh_state()
                self.assertEqual(response.status_code, 200)
                event = state["audit_events"][-1]
                self.assertTrue(event["force"])
                self.assertEqual(event["reason"], "test_force")
                self.assertEqual(event["trigger_type"], "manual")
            finally:
                LEGACY_APP_MODULE.REFRESH_STATE_PATH = previous_state_path

    def test_decision_ledger_outcomes_runs_after_postclose_brief(self) -> None:
        policies = {policy.task_name: policy for policy in CRON_POLICIES}
        self.assertIn("decision_ledger_outcomes", policies)
        policy = policies["decision_ledger_outcomes"]
        self.assertEqual(policy.cron_expr, "35 15 * * 1-5")
        self.assertEqual(policy.command, ("python3", "apps/scripts/evaluate_decision_ledger.py"))
        self.assertEqual(policy.depends_on, ("postclose_command_brief",))
        self.assertTrue(policy.catchup_enabled)

    def test_cron_config_contains_preclose_postclose_and_ledger_outcomes(self) -> None:
        payload = json.loads((Path(__file__).resolve().parents[3] / "config" / "openclaw" / "prism_cron_jobs.json").read_text(encoding="utf-8"))
        result = validate_cron_policies(payload.get("jobs") or [])
        self.assertTrue(result["ok"], result)
        expr_by_name = {job["name"]: job["schedule"]["expr"] for job in payload["jobs"]}
        self.assertEqual(expr_by_name["晨间数据预热"], "25 9 * * 1-5")
        self.assertEqual(expr_by_name["收盘前风险刷新"], "50 14 * * 1-5")
        self.assertEqual(expr_by_name["收盘后总控简报"], "5 15 * * 1-5")
        self.assertEqual(expr_by_name["Decision Ledger 结果评估"], "35 15 * * 1-5")

    def test_morning_warmup_resolves_as_safe_manual_task(self) -> None:
        task = LEGACY_APP_MODULE.resolve_refresh_task("morning_warmup")
        self.assertEqual(task["task_name"], "morning_warmup")
        self.assertEqual(task["title"], "晨间数据预热")
        self.assertEqual(task["command"][-1], "apps/scripts/run_morning_warmup.py")


if __name__ == "__main__":
    unittest.main()
