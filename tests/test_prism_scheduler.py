from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROL_PANEL_ROOT = REPO_ROOT / "apps" / "control-panel"
SCRIPTS_ROOT = REPO_ROOT / "apps" / "scripts"
PACKAGES_ROOT = REPO_ROOT / "packages"
for import_path in (str(REPO_ROOT), str(CONTROL_PANEL_ROOT), str(SCRIPTS_ROOT), str(PACKAGES_ROOT)):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)


def _load_script(module_name: str, path: Path) -> ModuleType:
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _reset_scheduler_modules() -> None:
    yield
    for name in (
        "prism_scheduler_test",
        "prism_scheduler_startup_test",
        "prism_scheduler_fire_start_test",
        "prism_scheduler_catchup_once_test",
        "prism_scheduler_formal_catchup_test",
        "prism_scheduler_retry_test",
        "prism_scheduler_recovery_window_test",
        "prism_scheduler_ledger_outcome_test",
        "prism_scheduler_freshness_guardian_test",
        "prism_scheduler_freshness_cooldown_test",
        "prism_scheduler_freshness_holiday_test",
        "prism_scheduled_job_test",
        "control_panel_task_runner_test",
    ):
        sys.modules.pop(name, None)


def test_internal_scheduler_skips_exchange_holiday_before_launching_job(tmp_path: Path) -> None:
    scheduler = _load_script("prism_scheduler_test", REPO_ROOT / "apps" / "scripts" / "prism_scheduler.py")
    scheduler.RUN_ROOT = tmp_path
    scheduler.STATE_PATH = tmp_path / "scheduler_state.json"
    scheduler.EVENT_LOG_PATH = tmp_path / "scheduler_events.jsonl"

    policy = scheduler.CRON_POLICIES[0]
    children = {}
    args = argparse.Namespace(
        send_to_feishu="0",
        allow_non_trading_day=False,
        dry_run=False,
        started_minute="2026-05-01T09:24",
        fire_on_start=False,
    )

    with mock.patch.object(scheduler, "CRON_POLICIES", (policy,)), mock.patch.object(
        scheduler,
        "datetime",
        wraps=scheduler.datetime,
    ) as fake_datetime, mock.patch.object(scheduler, "launch_job") as fake_launch:
        fake_datetime.now.return_value = datetime(2026, 5, 1, 9, 25, 0)
        scheduler.tick(args=args, children=children)

    assert fake_launch.call_count == 0
    assert children == {}
    state = scheduler.load_json(scheduler.STATE_PATH)
    assert state["calendar"]["status"] == "holiday"
    assert state["last_fired"][policy.task_name] == "2026-05-01T09:25"
    events = scheduler.EVENT_LOG_PATH.read_text(encoding="utf-8").splitlines()
    assert '"event": "job_skipped_non_trading_day"' in events[0]


def test_internal_scheduler_does_not_fire_due_job_on_startup_minute(tmp_path: Path) -> None:
    scheduler = _load_script("prism_scheduler_startup_test", REPO_ROOT / "apps" / "scripts" / "prism_scheduler.py")
    scheduler.RUN_ROOT = tmp_path
    scheduler.STATE_PATH = tmp_path / "scheduler_state.json"
    scheduler.EVENT_LOG_PATH = tmp_path / "scheduler_events.jsonl"

    policy = scheduler.CRON_POLICIES[0]
    args = argparse.Namespace(
        send_to_feishu="0",
        allow_non_trading_day=False,
        dry_run=False,
        started_minute="2026-05-08T09:25",
        fire_on_start=False,
    )

    with mock.patch.object(scheduler, "CRON_POLICIES", (policy,)), mock.patch.object(
        scheduler,
        "datetime",
        wraps=scheduler.datetime,
    ) as fake_datetime, mock.patch.object(scheduler, "launch_job") as fake_launch:
        fake_datetime.now.return_value = datetime(2026, 5, 8, 9, 25, 0)
        scheduler.tick(args=args, children={})

    assert fake_launch.call_count == 0
    state = scheduler.load_json(scheduler.STATE_PATH)
    assert state["last_fired"][policy.task_name] == "2026-05-08T09:25"
    events = scheduler.EVENT_LOG_PATH.read_text(encoding="utf-8").splitlines()
    assert '"event": "job_skipped_startup_minute"' in events[0]


def test_internal_scheduler_can_opt_into_startup_minute_fire(tmp_path: Path) -> None:
    scheduler = _load_script("prism_scheduler_fire_start_test", REPO_ROOT / "apps" / "scripts" / "prism_scheduler.py")
    scheduler.RUN_ROOT = tmp_path
    scheduler.STATE_PATH = tmp_path / "scheduler_state.json"
    scheduler.EVENT_LOG_PATH = tmp_path / "scheduler_events.jsonl"

    policy = scheduler.CRON_POLICIES[0]
    args = argparse.Namespace(
        send_to_feishu="0",
        allow_non_trading_day=False,
        dry_run=False,
        started_minute="2026-05-08T09:25",
        fire_on_start=True,
    )

    with mock.patch.object(scheduler, "CRON_POLICIES", (policy,)), mock.patch.object(
        scheduler,
        "datetime",
        wraps=scheduler.datetime,
    ) as fake_datetime, mock.patch.object(scheduler, "launch_job", return_value=None) as fake_launch:
        fake_datetime.now.return_value = datetime(2026, 5, 8, 9, 25, 0)
        scheduler.tick(args=args, children={})

    assert fake_launch.call_count == 1


def test_internal_scheduler_catchup_fires_once_per_task_day(tmp_path: Path) -> None:
    scheduler = _load_script("prism_scheduler_catchup_once_test", REPO_ROOT / "apps" / "scripts" / "prism_scheduler.py")
    scheduler.RUN_ROOT = tmp_path
    scheduler.STATE_PATH = tmp_path / "scheduler_state.json"
    scheduler.EVENT_LOG_PATH = tmp_path / "scheduler_events.jsonl"

    policy = scheduler.CRON_POLICIES[0]
    args = argparse.Namespace(
        send_to_feishu="0",
        allow_non_trading_day=False,
        dry_run=False,
        started_minute="2026-05-08T09:00",
        fire_on_start=False,
    )

    with mock.patch.object(scheduler, "CRON_POLICIES", (policy,)), mock.patch.object(
        scheduler,
        "datetime",
        wraps=scheduler.datetime,
    ) as fake_datetime, mock.patch.object(scheduler, "launch_job", return_value=None) as fake_launch:
        fake_datetime.now.return_value = datetime(2026, 5, 8, 9, 31, 0)
        scheduler.tick(args=args, children={})
        fake_datetime.now.return_value = datetime(2026, 5, 8, 9, 32, 0)
        scheduler.tick(args=args, children={})

    assert fake_launch.call_count == 1
    state = scheduler.load_json(scheduler.STATE_PATH)
    catchup = state["catchup_fired"][f"2026-05-08:{policy.task_name}"]
    assert catchup["status"] == "launched"


def test_formal_data_refresh_catchup_recovers_after_lunch(tmp_path: Path) -> None:
    scheduler = _load_script("prism_scheduler_formal_catchup_test", REPO_ROOT / "apps" / "scripts" / "prism_scheduler.py")
    scheduler.RUN_ROOT = tmp_path
    scheduler.STATE_PATH = tmp_path / "scheduler_state.json"
    scheduler.EVENT_LOG_PATH = tmp_path / "scheduler_events.jsonl"

    policy = next(item for item in scheduler.CRON_POLICIES if item.task_name == "formal_data_refresh")
    args = argparse.Namespace(
        send_to_feishu="0",
        allow_non_trading_day=False,
        dry_run=False,
        started_minute="2026-05-08T13:00",
        fire_on_start=False,
        freshness_guardian=False,
    )

    with mock.patch.object(scheduler, "CRON_POLICIES", (policy,)), mock.patch.object(
        scheduler,
        "datetime",
        wraps=scheduler.datetime,
    ) as fake_datetime, mock.patch.object(scheduler, "launch_job", return_value=None) as fake_launch:
        fake_datetime.now.return_value = datetime(2026, 5, 8, 13, 15, 0)
        scheduler.tick(args=args, children={})

    assert fake_launch.call_count == 1
    launched_policy = fake_launch.call_args.args[0]
    assert launched_policy.task_name == "formal_data_refresh"
    state = scheduler.load_json(scheduler.STATE_PATH)
    catchup = state["catchup_fired"][f"2026-05-08:{policy.task_name}"]
    assert catchup["status"] == "launched"


def test_internal_scheduler_retries_failed_catchup_after_delay(tmp_path: Path) -> None:
    scheduler = _load_script("prism_scheduler_retry_test", REPO_ROOT / "apps" / "scripts" / "prism_scheduler.py")
    scheduler.RUN_ROOT = tmp_path
    scheduler.STATE_PATH = tmp_path / "scheduler_state.json"
    scheduler.EVENT_LOG_PATH = tmp_path / "scheduler_events.jsonl"

    policy = scheduler.CRON_POLICIES[0]
    latest_dir = tmp_path / "latest"
    latest_dir.mkdir(parents=True, exist_ok=True)
    (latest_dir / f"{policy.task_name}.json").write_text(
        '{"status":"failed","trade_date":"2026-05-08","finished_at":"2026-05-08 09:30:00"}',
        encoding="utf-8",
    )
    scheduler.write_json(
        scheduler.STATE_PATH,
        {"catchup_fired": {f"2026-05-08:{policy.task_name}": {"status": "launched", "at": "2026-05-08 09:26:00"}}},
    )
    args = argparse.Namespace(
        send_to_feishu="0",
        allow_non_trading_day=False,
        dry_run=False,
        started_minute="2026-05-08T09:00",
        fire_on_start=False,
    )

    with mock.patch.object(scheduler, "CRON_POLICIES", (policy,)), mock.patch.object(
        scheduler,
        "datetime",
        wraps=scheduler.datetime,
    ) as fake_datetime, mock.patch.object(scheduler, "launch_job", return_value=None) as fake_launch:
        fake_datetime.now.return_value = datetime(2026, 5, 8, 9, 34, 0)
        scheduler.tick(args=args, children={})

    assert fake_launch.call_count == 1
    state = scheduler.load_json(scheduler.STATE_PATH)
    assert state["retry_counts"][f"2026-05-08:{policy.task_name}"] == 1


def test_missed_run_recovery_stops_after_catchup_until() -> None:
    scheduler = _load_script("prism_scheduler_recovery_window_test", REPO_ROOT / "apps" / "scripts" / "prism_scheduler.py")
    policy = next(item for item in scheduler.CRON_POLICIES if item.task_name == "formal_data_refresh_index_morning")

    assert scheduler.missed_run_recovery_open(policy, datetime(2026, 5, 8, 10, 50, 0))
    assert not scheduler.missed_run_recovery_open(policy, datetime(2026, 5, 8, 22, 55, 0))


def test_internal_scheduler_launches_ledger_outcomes_after_postclose_dependency(tmp_path: Path) -> None:
    scheduler = _load_script("prism_scheduler_ledger_outcome_test", REPO_ROOT / "apps" / "scripts" / "prism_scheduler.py")
    scheduler.RUN_ROOT = tmp_path
    scheduler.STATE_PATH = tmp_path / "scheduler_state.json"
    scheduler.EVENT_LOG_PATH = tmp_path / "scheduler_events.jsonl"

    policy = next(item for item in scheduler.CRON_POLICIES if item.task_name == "decision_ledger_outcomes")
    latest_dir = tmp_path / "latest"
    latest_dir.mkdir(parents=True, exist_ok=True)
    (latest_dir / "postclose_command_brief.json").write_text(
        '{"status":"success","calendar":{"trade_date":"2026-05-08"},"finished_at":"2026-05-08 15:12:00"}',
        encoding="utf-8",
    )
    args = argparse.Namespace(
        send_to_feishu="1",
        allow_non_trading_day=False,
        dry_run=False,
        started_minute="2026-05-08T15:00",
        fire_on_start=False,
    )

    with mock.patch.object(scheduler, "CRON_POLICIES", (policy,)), mock.patch.object(
        scheduler,
        "datetime",
        wraps=scheduler.datetime,
    ) as fake_datetime, mock.patch.object(scheduler, "launch_job", return_value=None) as fake_launch:
        fake_datetime.now.return_value = datetime(2026, 5, 8, 15, 35, 0)
        scheduler.tick(args=args, children={})

    assert fake_launch.call_count == 1
    launched_policy = fake_launch.call_args.args[0]
    assert launched_policy.task_name == "decision_ledger_outcomes"
    assert fake_launch.call_args.kwargs["send_to_feishu"] is False
    state = scheduler.load_json(scheduler.STATE_PATH)
    assert state["last_fired"]["decision_ledger_outcomes"] == "2026-05-08T15:35"


def _scheduler_args(*, freshness_guardian: bool = True) -> argparse.Namespace:
    return argparse.Namespace(
        send_to_feishu="0",
        allow_non_trading_day=False,
        dry_run=False,
        started_minute="2026-05-08T09:00",
        fire_on_start=False,
        freshness_guardian=freshness_guardian,
    )


def test_freshness_guardian_launches_stale_quotes_during_trading(tmp_path: Path) -> None:
    scheduler = _load_script("prism_scheduler_freshness_guardian_test", REPO_ROOT / "apps" / "scripts" / "prism_scheduler.py")
    scheduler.RUN_ROOT = tmp_path
    scheduler.STATE_PATH = tmp_path / "scheduler_state.json"
    scheduler.EVENT_LOG_PATH = tmp_path / "scheduler_events.jsonl"

    fake_proc = mock.Mock(pid=4242)

    def fake_inspect(task_name: str, **_kwargs):
        if task_name == "quotes_light":
            return {
                "task_name": task_name,
                "dataset": "quotes.batch",
                "expected_trade_date": "2026-05-08",
                "stale": True,
                "stale_reasons": ["freshness_stale"],
                "age_seconds": 7200,
                "stale_after_seconds": 60,
                "freshness_status": "stale",
                "trade_date": "2026-05-08",
                "manifest_path": "/tmp/quotes.manifest.json",
            }
        return {
            "task_name": task_name,
            "dataset": "capital_flow.batch",
            "expected_trade_date": "2026-05-08",
            "stale": False,
            "stale_reasons": [],
            "age_seconds": 30,
            "stale_after_seconds": 180,
            "freshness_status": "fresh",
            "trade_date": "2026-05-08",
            "manifest_path": "/tmp/capital.manifest.json",
        }

    with mock.patch.object(scheduler, "CRON_POLICIES", ()), mock.patch.object(
        scheduler,
        "datetime",
        wraps=scheduler.datetime,
    ) as fake_datetime, mock.patch.object(
        scheduler,
        "inspect_lightweight_dataset",
        side_effect=fake_inspect,
    ), mock.patch.object(
        scheduler,
        "launch_lightweight_refresh",
        return_value=fake_proc,
    ) as fake_launch:
        fake_datetime.now.return_value = datetime(2026, 5, 8, 10, 50, 0)
        children = {}
        scheduler.tick(args=_scheduler_args(), children=children)

    assert fake_launch.call_count == 1
    assert fake_launch.call_args.args[0] == "quotes_light"
    assert children[4242] is fake_proc
    state = scheduler.load_json(scheduler.STATE_PATH)
    quotes_state = state["freshness_guardian"]["quotes_light"]
    assert quotes_state["last_decision"] == "launched"
    assert quotes_state["last_trigger_reasons"] == ["freshness_stale"]


def test_freshness_guardian_respects_lightweight_cooldown(tmp_path: Path) -> None:
    scheduler = _load_script("prism_scheduler_freshness_cooldown_test", REPO_ROOT / "apps" / "scripts" / "prism_scheduler.py")
    scheduler.RUN_ROOT = tmp_path
    scheduler.STATE_PATH = tmp_path / "scheduler_state.json"
    scheduler.EVENT_LOG_PATH = tmp_path / "scheduler_events.jsonl"
    scheduler.write_json(
        scheduler.STATE_PATH,
        {"freshness_guardian": {"quotes_light": {"last_triggered_at": "2026-05-08 10:49:30"}}},
    )
    stale_quotes = {
        "task_name": "quotes_light",
        "dataset": "quotes.batch",
        "expected_trade_date": "2026-05-08",
        "stale": True,
        "stale_reasons": ["freshness_stale"],
        "age_seconds": 7200,
        "stale_after_seconds": 60,
        "freshness_status": "stale",
        "trade_date": "2026-05-08",
        "manifest_path": "/tmp/quotes.manifest.json",
    }
    fresh_capital = {
        "task_name": "capital_flow_light",
        "dataset": "capital_flow.batch",
        "expected_trade_date": "2026-05-08",
        "stale": False,
        "stale_reasons": [],
        "age_seconds": 30,
        "stale_after_seconds": 180,
        "freshness_status": "fresh",
        "trade_date": "2026-05-08",
        "manifest_path": "/tmp/capital.manifest.json",
    }

    with mock.patch.object(scheduler, "CRON_POLICIES", ()), mock.patch.object(
        scheduler,
        "datetime",
        wraps=scheduler.datetime,
    ) as fake_datetime, mock.patch.object(
        scheduler,
        "inspect_lightweight_dataset",
        side_effect=lambda task_name, **_kwargs: stale_quotes if task_name == "quotes_light" else fresh_capital,
    ), mock.patch.object(scheduler, "launch_lightweight_refresh") as fake_launch:
        fake_datetime.now.return_value = datetime(2026, 5, 8, 10, 50, 0)
        scheduler.tick(args=_scheduler_args(), children={})

    assert fake_launch.call_count == 0
    state = scheduler.load_json(scheduler.STATE_PATH)
    quotes_state = state["freshness_guardian"]["quotes_light"]
    assert quotes_state["last_decision"] == "skip"
    assert quotes_state["last_skip_reason"] == "cooldown"
    assert quotes_state["cooldown_remaining_seconds"] == 60


def test_freshness_guardian_skips_non_trading_day(tmp_path: Path) -> None:
    scheduler = _load_script("prism_scheduler_freshness_holiday_test", REPO_ROOT / "apps" / "scripts" / "prism_scheduler.py")
    scheduler.RUN_ROOT = tmp_path
    scheduler.STATE_PATH = tmp_path / "scheduler_state.json"
    scheduler.EVENT_LOG_PATH = tmp_path / "scheduler_events.jsonl"

    with mock.patch.object(scheduler, "CRON_POLICIES", ()), mock.patch.object(
        scheduler,
        "datetime",
        wraps=scheduler.datetime,
    ) as fake_datetime, mock.patch.object(scheduler, "inspect_lightweight_dataset") as fake_inspect, mock.patch.object(
        scheduler,
        "launch_lightweight_refresh",
    ) as fake_launch:
        fake_datetime.now.return_value = datetime(2026, 5, 9, 10, 50, 0)
        scheduler.tick(args=_scheduler_args(), children={})

    assert fake_inspect.call_count == 0
    assert fake_launch.call_count == 0
    state = scheduler.load_json(scheduler.STATE_PATH)
    assert state["freshness_guardian"]["last_skip_reason"] == "non_trading_day:weekend"


def test_scheduled_job_calendar_guard_defaults_to_skip() -> None:
    job = _load_script("prism_scheduled_job_test", REPO_ROOT / "apps" / "scripts" / "prism_scheduled_job.py")

    assert job.should_skip_for_calendar(
        status={"status": "holiday"},
        allow_non_trading_day=False,
    )
    assert not job.should_skip_for_calendar(
        status={"status": "holiday"},
        allow_non_trading_day=True,
    )
    assert not job.should_skip_for_calendar(
        status={"status": "trading"},
        allow_non_trading_day=False,
    )


def test_scheduled_job_appends_task_args_to_command_and_payload(tmp_path: Path) -> None:
    job = _load_script("prism_scheduled_job_test", REPO_ROOT / "apps" / "scripts" / "prism_scheduled_job.py")
    job.RUN_ROOT = tmp_path
    policy = SimpleNamespace(
        task_name="unit_formal_refresh",
        name="Unit formal refresh",
        command=("python3", "apps/scripts/refresh_formal_data.py"),
    )
    proc = SimpleNamespace(returncode=0)

    with mock.patch.object(job, "POLICIES", {"unit_formal_refresh": policy}), mock.patch.object(
        job,
        "TASK_POLICIES",
        {},
    ), mock.patch.object(
        sys,
        "argv",
        [
            "prism_scheduled_job.py",
            "--task-name",
            "unit_formal_refresh",
            "--allow-non-trading-day",
            "--task-arg=--index-batch-limit",
            "--task-arg",
            "0",
        ],
    ), mock.patch.object(
        job,
        "calendar_status",
        return_value={"status": "weekend", "reason": "weekend"},
    ), mock.patch.object(
        job.subprocess,
        "run",
        return_value=proc,
    ) as fake_run:
        assert job.main() == 0

    expected_command = [
        "python3",
        "apps/scripts/refresh_formal_data.py",
        "--index-batch-limit",
        "0",
    ]
    assert fake_run.call_args.args[0] == expected_command
    latest_payload = json.loads((tmp_path / "latest" / "unit_formal_refresh.json").read_text(encoding="utf-8"))
    assert latest_payload["command"] == expected_command
    assert latest_payload["status"] == "success"
    assert latest_payload["calendar"]["status"] == "weekend"


def test_control_panel_task_runner_calendar_guard_defaults_to_skip_for_refresh_tasks() -> None:
    runner = _load_script(
        "control_panel_task_runner_test",
        REPO_ROOT / "apps" / "scripts" / "control_panel_task_runner.py",
    )

    assert runner.should_skip_for_calendar(
        task_name="watchlist_refresh",
        status={"status": "holiday"},
        allow_non_trading_day=False,
    )
    assert not runner.should_skip_for_calendar(
        task_name="watchlist_refresh",
        status={"status": "holiday"},
        allow_non_trading_day=True,
    )
    assert not runner.should_skip_for_calendar(
        task_name="custom_maintenance",
        status={"status": "holiday"},
        allow_non_trading_day=False,
    )
