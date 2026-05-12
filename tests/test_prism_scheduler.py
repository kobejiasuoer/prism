from __future__ import annotations

import argparse
import importlib.util
import sys
from datetime import datetime
from pathlib import Path
from types import ModuleType
from unittest import mock

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROL_PANEL_ROOT = REPO_ROOT / "apps" / "control-panel"
PACKAGES_ROOT = REPO_ROOT / "packages"
for import_path in (str(REPO_ROOT), str(CONTROL_PANEL_ROOT), str(PACKAGES_ROOT)):
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
        started_minute="2026-05-01T09:49",
        fire_on_start=False,
    )

    with mock.patch.object(scheduler, "CRON_POLICIES", (policy,)), mock.patch.object(
        scheduler,
        "datetime",
        wraps=scheduler.datetime,
    ) as fake_datetime, mock.patch.object(scheduler, "launch_job") as fake_launch:
        fake_datetime.now.return_value = datetime(2026, 5, 1, 9, 50, 0)
        scheduler.tick(args=args, children=children)

    assert fake_launch.call_count == 0
    assert children == {}
    state = scheduler.load_json(scheduler.STATE_PATH)
    assert state["calendar"]["status"] == "holiday"
    assert state["last_fired"][policy.task_name] == "2026-05-01T09:50"
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
        started_minute="2026-05-08T09:50",
        fire_on_start=False,
    )

    with mock.patch.object(scheduler, "CRON_POLICIES", (policy,)), mock.patch.object(
        scheduler,
        "datetime",
        wraps=scheduler.datetime,
    ) as fake_datetime, mock.patch.object(scheduler, "launch_job") as fake_launch:
        fake_datetime.now.return_value = datetime(2026, 5, 8, 9, 50, 0)
        scheduler.tick(args=args, children={})

    assert fake_launch.call_count == 0
    state = scheduler.load_json(scheduler.STATE_PATH)
    assert state["last_fired"][policy.task_name] == "2026-05-08T09:50"
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
        started_minute="2026-05-08T09:50",
        fire_on_start=True,
    )

    with mock.patch.object(scheduler, "CRON_POLICIES", (policy,)), mock.patch.object(
        scheduler,
        "datetime",
        wraps=scheduler.datetime,
    ) as fake_datetime, mock.patch.object(scheduler, "launch_job", return_value=None) as fake_launch:
        fake_datetime.now.return_value = datetime(2026, 5, 8, 9, 50, 0)
        scheduler.tick(args=args, children={})

    assert fake_launch.call_count == 1


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
