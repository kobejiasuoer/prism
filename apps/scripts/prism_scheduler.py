#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(os.environ.get("PRISM_REPO_ROOT") or Path(__file__).resolve().parents[2]).resolve()
CONTROL_PANEL_ROOT = REPO_ROOT / "apps" / "control-panel"
PACKAGES_ROOT = REPO_ROOT / "packages"
for path in (str(REPO_ROOT), str(PACKAGES_ROOT), str(CONTROL_PANEL_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from prism_data.env import load_project_env  # noqa: E402

load_project_env(root=REPO_ROOT)

from dataset_manifests import build_dataset_freshness_rows  # noqa: E402
from refresh_policy import CRON_POLICIES, TASK_POLICIES, active_auto_windows, task_family  # noqa: E402
from scheduled_run_state import parse_timestamp, run_state_for_task  # noqa: E402
from trading_calendar import calendar_status  # noqa: E402


RUN_ROOT = REPO_ROOT / "data" / "scheduled_runs"
STATE_PATH = RUN_ROOT / "scheduler_state.json"
EVENT_LOG_PATH = RUN_ROOT / "scheduler_events.jsonl"
DELIVERY_CONFIG_PATH = REPO_ROOT / "data" / "config" / "prism-delivery.local.json"
JOB_RUNNER = REPO_ROOT / "apps" / "scripts" / "prism_scheduled_job.py"
LIGHTWEIGHT_REFRESH = REPO_ROOT / "apps" / "scripts" / "refresh_lightweight_data.py"
DEPENDENCY_RECHECK_SECONDS = 5 * 60
MISSED_RUN_GRACE_MINUTES = 8
LIGHTWEIGHT_REFRESH_TASKS: dict[str, dict[str, Any]] = {
    "quotes_light": {
        "dataset": "quotes.batch",
        "kind": "quotes",
        "limit": 60,
    },
    "capital_flow_light": {
        "dataset": "capital_flow.batch",
        "kind": "capital_flow",
        "limit": 60,
    },
}
LIGHTWEIGHT_CONFLICT_TASKS = ("morning_warmup", *LIGHTWEIGHT_REFRESH_TASKS.keys())
STOP = False
CHILD_RUNS: dict[int, dict[str, Any]] = {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Prism internal scheduler.")
    parser.add_argument("--interval-seconds", type=float, default=float(os.environ.get("PRISM_SCHEDULER_INTERVAL_SECONDS", "20")))
    parser.add_argument("--once", action="store_true", help="Check due jobs once and exit.")
    parser.add_argument("--dry-run", action="store_true", help="Record due jobs without launching them.")
    parser.add_argument("--send-to-feishu", choices=["auto", "0", "1"], default=os.environ.get("PRISM_SCHEDULER_SEND_TO_FEISHU", "auto"))
    parser.add_argument("--allow-non-trading-day", action="store_true")
    freshness_guardian_default = str(os.environ.get("PRISM_SCHEDULER_FRESHNESS_GUARDIAN", "1")).strip().lower() not in {"0", "false", "no", "off"}
    parser.add_argument(
        "--disable-freshness-guardian",
        dest="freshness_guardian",
        action="store_false",
        default=freshness_guardian_default,
        help="Disable continuous freshness checks for lightweight market datasets.",
    )
    parser.add_argument(
        "--enable-freshness-guardian",
        dest="freshness_guardian",
        action="store_true",
        help="Enable continuous freshness checks for lightweight market datasets.",
    )
    parser.add_argument(
        "--fire-on-start",
        action="store_true",
        default=str(os.environ.get("PRISM_SCHEDULER_FIRE_ON_START", "")).strip().lower() in {"1", "true", "yes", "on"},
        help="Allow jobs due in the scheduler startup minute to run.",
    )
    return parser.parse_args()


def handle_stop(signum: int, _frame: object) -> None:
    global STOP
    STOP = True
    try:
        os.write(2, f"[prism-scheduler] received signal {signum}; stopping after current tick\n".encode("utf-8"))
    except OSError:
        pass


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def append_event(payload: dict[str, Any]) -> None:
    EVENT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with EVENT_LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def parse_cron_field(field: str, *, minimum: int, maximum: int) -> set[int] | None:
    field = field.strip()
    if field == "*":
        return None
    values: set[int] = set()
    for chunk in field.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "/" in chunk:
            base, step_text = chunk.split("/", 1)
            step = int(step_text)
            if base == "*":
                start, end = minimum, maximum
            elif "-" in base:
                left, right = base.split("-", 1)
                start, end = int(left), int(right)
            else:
                start = end = int(base)
            values.update(range(start, end + 1, step))
        elif "-" in chunk:
            left, right = chunk.split("-", 1)
            values.update(range(int(left), int(right) + 1))
        else:
            values.add(int(chunk))
    if not all(minimum <= value <= maximum for value in values):
        raise ValueError(f"cron field out of range: {field}")
    return values


def cron_matches(expr: str, current: datetime) -> bool:
    minute_s, hour_s, day_s, month_s, weekday_s = expr.split()
    minute = parse_cron_field(minute_s, minimum=0, maximum=59)
    hour = parse_cron_field(hour_s, minimum=0, maximum=23)
    day = parse_cron_field(day_s, minimum=1, maximum=31)
    month = parse_cron_field(month_s, minimum=1, maximum=12)
    weekday = parse_cron_field(weekday_s, minimum=0, maximum=7)
    cron_weekday = current.isoweekday()
    cron_weekday_values = {7 if value == 0 else value for value in weekday} if weekday is not None else None
    return (
        (minute is None or current.minute in minute)
        and (hour is None or current.hour in hour)
        and (day is None or current.day in day)
        and (month is None or current.month in month)
        and (cron_weekday_values is None or cron_weekday in cron_weekday_values)
    )


def minute_key(current: datetime) -> str:
    return current.strftime("%Y-%m-%dT%H:%M")


def day_key(current: datetime) -> str:
    return current.strftime("%Y-%m-%d")


def clock_minutes(value: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        hour, minute = text.split(":", 1)
        return int(hour) * 60 + int(minute)
    except Exception:
        return None


def cron_daily_minute(expr: str) -> int | None:
    try:
        minute_s, hour_s, day_s, month_s, weekday_s = expr.split()
        if day_s != "*" or month_s != "*":
            return None
        minutes = parse_cron_field(minute_s, minimum=0, maximum=59)
        hours = parse_cron_field(hour_s, minimum=0, maximum=23)
    except Exception:
        return None
    if minutes is None or hours is None or len(minutes) != 1 or len(hours) != 1:
        return None
    return next(iter(hours)) * 60 + next(iter(minutes))


def current_clock_minutes(current: datetime) -> int:
    return current.hour * 60 + current.minute


def catchup_window_open(policy, current: datetime) -> bool:
    if not getattr(policy, "catchup_enabled", False):
        return False
    due = cron_daily_minute(policy.cron_expr)
    until = clock_minutes(getattr(policy, "catchup_until", ""))
    if due is None or until is None:
        return False
    now_minute = current_clock_minutes(current)
    return due < now_minute <= until


def missed_run_recovery_open(policy, current: datetime) -> bool:
    if not getattr(policy, "catchup_enabled", False):
        return False
    due = cron_daily_minute(policy.cron_expr)
    if due is None:
        return False
    until = clock_minutes(getattr(policy, "catchup_until", ""))
    now_minute = current_clock_minutes(current)
    if until is not None and now_minute > until:
        return False
    return now_minute >= due + MISSED_RUN_GRACE_MINUTES


def retry_due(policy, run_state: dict[str, Any], current: datetime, *, scheduler_state: dict[str, Any]) -> bool:
    attempts = int(getattr(policy, "retry_attempts", 0) or 0)
    delay = int(getattr(policy, "retry_delay_seconds", 0) or 0)
    if attempts <= 0 or delay <= 0 or not run_state.get("failed_today"):
        return False
    retry_counts = scheduler_state.get("retry_counts") if isinstance(scheduler_state.get("retry_counts"), dict) else {}
    count_key = f"{day_key(current)}:{policy.task_name}"
    if int(retry_counts.get(count_key) or 0) >= attempts:
        return False
    finished_dt = run_state.get("finished_dt")
    if not finished_dt:
        return False
    return (current - finished_dt).total_seconds() >= delay


def dependency_blockers(policy, *, current: datetime) -> list[str]:
    blockers: list[str] = []
    for dependency in getattr(policy, "depends_on", ()) or ():
        dep_state = run_state_for_task(str(dependency), now=current, run_root=RUN_ROOT)
        if not dep_state.get("today_success"):
            blockers.append(str(dependency))
    return blockers


def should_send_to_feishu(mode: str) -> bool:
    if mode == "1":
        return True
    if mode == "0":
        return False
    delivery_config = load_json(DELIVERY_CONFIG_PATH)
    feishu = delivery_config.get("feishu") if isinstance(delivery_config.get("feishu"), dict) else {}
    default_delivery = feishu.get("default") if isinstance(feishu.get("default"), dict) else {}
    return bool(str(default_delivery.get("target") or default_delivery.get("to") or "").strip())


def reap_children(children: dict[int, subprocess.Popen[str]]) -> None:
    for pid, proc in list(children.items()):
        code = proc.poll()
        if code is None:
            continue
        child_run = CHILD_RUNS.pop(pid, None)
        if child_run:
            payload = load_json(Path(child_run.get("meta_path") or ""))
            payload.update(
                {
                    "status": "success" if code == 0 else "failed",
                    "finished_at": now_str(),
                    "exit_code": code,
                }
            )
            meta_path = Path(str(child_run.get("meta_path") or ""))
            latest_path = Path(str(child_run.get("latest_path") or ""))
            if str(meta_path):
                write_json(meta_path, payload)
            if str(latest_path):
                write_json(latest_path, payload)
        append_event(
            {
                "event": "job_exit",
                "pid": pid,
                "task_name": (child_run or {}).get("task_name"),
                "exit_code": code,
                "finished_at": now_str(),
            }
        )
        children.pop(pid, None)


def launch_job(policy, *, args: argparse.Namespace, send_to_feishu: bool) -> subprocess.Popen[str] | None:
    command = [
        sys.executable,
        str(JOB_RUNNER),
        "--task-name",
        policy.task_name,
    ]
    if send_to_feishu:
        command.append("--send-to-feishu")
    if args.allow_non_trading_day:
        command.append("--allow-non-trading-day")
    if args.dry_run:
        command.append("--dry-run")

    env = os.environ.copy()
    env["PRISM_REPO_ROOT"] = str(REPO_ROOT)
    env["PRISM_SCHEDULED_VIA"] = "prism_scheduler"
    env["PRISM_SCHEDULER_PID"] = str(os.getpid())
    if args.dry_run:
        print(f"[prism-scheduler] dry-run due: {' '.join(command)}", flush=True)
        append_event(
            {
                "event": "job_due_dry_run",
                "task_name": policy.task_name,
                "command": command,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        return None

    proc = subprocess.Popen(command, cwd=REPO_ROOT, env=env, text=True)
    append_event(
        {
            "event": "job_started",
            "task_name": policy.task_name,
            "pid": proc.pid,
            "command": command,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    print(f"[prism-scheduler] started {policy.task_name} pid={proc.pid}", flush=True)
    return proc


def launch_policy(
    policy,
    *,
    args: argparse.Namespace,
    children: dict[int, subprocess.Popen[str]],
    send_to_feishu: bool,
    reason: str,
) -> bool:
    proc = launch_job(policy, args=args, send_to_feishu=send_to_feishu)
    append_event(
        {
            "event": f"job_due_{reason}",
            "task_name": policy.task_name,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    if proc is not None:
        children[proc.pid] = proc
    return True


def skip_non_trading_day(policy, current: datetime) -> None:
    cal = calendar_status(current)
    append_event(
        {
            "event": "job_skipped_non_trading_day",
            "task_name": policy.task_name,
            "calendar": cal,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    print(f"[prism-scheduler] skipped {policy.task_name}: non-trading day ({cal.get('status')})", flush=True)


def skip_startup_minute(policy, current: datetime) -> None:
    append_event(
        {
            "event": "job_skipped_startup_minute",
            "task_name": policy.task_name,
            "minute": minute_key(current),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    print(f"[prism-scheduler] skipped {policy.task_name}: startup minute guard", flush=True)


def skip_dependency(policy, blockers: list[str], reason: str) -> None:
    append_event(
        {
            "event": "job_skipped_dependency",
            "task_name": policy.task_name,
            "reason": reason,
            "blockers": blockers,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    print(f"[prism-scheduler] skipped {policy.task_name}: dependency {', '.join(blockers)}", flush=True)


def record_dependency_wait(
    state: dict[str, Any],
    policy,
    blockers: list[str],
    *,
    reason: str,
    current: datetime,
) -> bool:
    waits = state.get("dependency_waits") if isinstance(state.get("dependency_waits"), dict) else {}
    key = f"{day_key(current)}:{policy.task_name}:{reason}"
    previous = waits.get(key) if isinstance(waits.get(key), dict) else {}
    last_checked = parse_timestamp(previous.get("last_checked_at"))
    same_blockers = list(previous.get("blockers") or []) == blockers
    should_log = not (
        last_checked
        and same_blockers
        and (current - last_checked).total_seconds() < DEPENDENCY_RECHECK_SECONDS
    )
    if should_log:
        waits[key] = {
            "task_name": policy.task_name,
            "reason": reason,
            "blockers": blockers,
            "count": int(previous.get("count") or 0) + 1,
            "last_checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        state["dependency_waits"] = waits
    return should_log


def clear_dependency_waits(state: dict[str, Any], policy, current: datetime) -> None:
    waits = state.get("dependency_waits")
    if not isinstance(waits, dict):
        return
    prefix = f"{day_key(current)}:{policy.task_name}:"
    state["dependency_waits"] = {key: value for key, value in waits.items() if not str(key).startswith(prefix)}


def skip_already_success(policy, reason: str) -> None:
    append_event(
        {
            "event": "job_skipped_already_success",
            "task_name": policy.task_name,
            "reason": reason,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )


def mark_retry_count(state: dict[str, Any], policy, current: datetime) -> None:
    retry_counts = state.get("retry_counts") if isinstance(state.get("retry_counts"), dict) else {}
    key = f"{day_key(current)}:{policy.task_name}"
    retry_counts[key] = int(retry_counts.get(key) or 0) + 1
    state["retry_counts"] = retry_counts


def _same_day_payload(payload: dict[str, Any], current: datetime) -> bool:
    today = day_key(current)
    calendar = payload.get("calendar") if isinstance(payload.get("calendar"), dict) else {}
    for value in (
        calendar.get("trade_date") if isinstance(calendar, dict) else None,
        payload.get("trade_date"),
        payload.get("started_at"),
        payload.get("finished_at"),
        payload.get("run_id"),
        payload.get("task_id"),
    ):
        text = str(value or "")
        if text.startswith(today):
            return True
    return False


def _control_panel_family_running(task_name: str, *, current: datetime) -> bool:
    family = task_family(task_name)
    roots = (
        REPO_ROOT / "data" / "runtime" / "runs" / "control_panel",
        REPO_ROOT / "data" / "control_panel_runs",
    )
    candidates: list[Path] = []
    for root in roots:
        try:
            candidates.extend(root.glob("*.json"))
        except OSError:
            continue
    candidates.sort(key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True)
    for path in candidates[:80]:
        payload = load_json(path)
        if str(payload.get("status") or "") != "running":
            continue
        if not _same_day_payload(payload, current):
            continue
        if task_family(str(payload.get("task_name") or "")) != family:
            continue
        try:
            pid = int(payload.get("pid") or 0)
        except (TypeError, ValueError):
            pid = 0
        if pid > 0:
            try:
                os.kill(pid, 0)
                return True
            except OSError:
                continue
    return False


def lightweight_conflict_running(task_name: str, *, current: datetime, launched_tasks: set[str]) -> str:
    family = task_family(task_name)
    for launched in launched_tasks:
        if task_family(launched) == family:
            return launched
    for candidate in LIGHTWEIGHT_CONFLICT_TASKS:
        if task_family(candidate) != family:
            continue
        run_state = run_state_for_task(candidate, now=current, run_root=RUN_ROOT)
        if run_state.get("running"):
            return candidate
    if _control_panel_family_running(task_name, current=current):
        return "control_panel"
    return ""


def lightweight_cooldown_remaining(task_name: str, guardian_state: dict[str, Any], current: datetime) -> int:
    task_state = guardian_state.get(task_name) if isinstance(guardian_state.get(task_name), dict) else {}
    last_dt = parse_timestamp((task_state or {}).get("last_triggered_at"))
    if not last_dt:
        return 0
    policy = TASK_POLICIES.get(task_name)
    cooldown_seconds = int(getattr(policy, "cooldown_seconds", 300) or 300)
    elapsed = max(int((current - last_dt).total_seconds()), 0)
    return max(cooldown_seconds - elapsed, 0)


def inspect_lightweight_dataset(task_name: str, *, current: datetime, calendar: dict[str, Any]) -> dict[str, Any]:
    config = LIGHTWEIGHT_REFRESH_TASKS[task_name]
    dataset = str(config["dataset"])
    expected_date = str(calendar.get("date") or current.strftime("%Y-%m-%d"))
    rows = build_dataset_freshness_rows(
        expected_date=expected_date,
        now=current,
        datasets=(dataset,),
    )
    row = rows[0] if rows else {
        "dataset": dataset,
        "key": dataset,
        "stale": True,
        "stale_reasons": ["manifest_missing"],
        "age_seconds": None,
        "trade_date": None,
    }
    reasons = [str(item) for item in row.get("stale_reasons") or []]
    return {
        "task_name": task_name,
        "dataset": dataset,
        "expected_trade_date": expected_date,
        "stale": bool(row.get("stale")),
        "stale_reasons": reasons,
        "age_seconds": row.get("age_seconds"),
        "stale_after_seconds": row.get("stale_after_seconds"),
        "freshness_status": row.get("freshness_status"),
        "trade_date": row.get("trade_date"),
        "manifest_path": row.get("manifest_path"),
        "row": row,
    }


def launch_lightweight_refresh(
    task_name: str,
    *,
    args: argparse.Namespace,
    current: datetime,
    calendar: dict[str, Any],
    freshness: dict[str, Any],
) -> subprocess.Popen[str] | None:
    config = LIGHTWEIGHT_REFRESH_TASKS[task_name]
    policy = TASK_POLICIES.get(task_name)
    run_id = f"{task_name}_{stamp()}"
    log_path = RUN_ROOT / "logs" / f"{run_id}.log"
    meta_path = RUN_ROOT / "runs" / f"{run_id}.json"
    latest_path = RUN_ROOT / "latest" / f"{task_name}.json"
    command = [
        sys.executable,
        str(LIGHTWEIGHT_REFRESH),
        "--kind",
        str(config["kind"]),
        "--date",
        str(freshness.get("expected_trade_date") or current.strftime("%Y-%m-%d")),
        "--limit",
        str(int(config.get("limit") or 60)),
    ]
    payload: dict[str, Any] = {
        "run_id": run_id,
        "task_name": task_name,
        "title": policy.title if policy else task_name,
        "schedule_name": "freshness_guardian",
        "command": command,
        "cwd": str(REPO_ROOT),
        "status": "running",
        "started_at": now_str(),
        "finished_at": None,
        "exit_code": None,
        "pid": os.getpid(),
        "log_path": str(log_path),
        "meta_path": str(meta_path),
        "calendar": calendar,
        "trade_date": str(freshness.get("expected_trade_date") or current.strftime("%Y-%m-%d")),
        "send_to_feishu": False,
        "trigger_type": "freshness_guardian",
        "freshness": {
            "dataset": freshness.get("dataset"),
            "age_seconds": freshness.get("age_seconds"),
            "stale_after_seconds": freshness.get("stale_after_seconds"),
            "freshness_status": freshness.get("freshness_status"),
            "trade_date": freshness.get("trade_date"),
            "stale_reasons": freshness.get("stale_reasons") or [],
            "manifest_path": freshness.get("manifest_path"),
        },
    }
    if args.dry_run:
        payload.update(status="skipped", skip_reason="dry_run", finished_at=now_str(), exit_code=0)
        write_json(meta_path, payload)
        write_json(latest_path, payload)
        append_event(
            {
                "event": "freshness_guardian_due_dry_run",
                "task_name": task_name,
                "command": command,
                "freshness": payload["freshness"],
                "created_at": now_str(),
            }
        )
        return None

    env = os.environ.copy()
    env["PRISM_REPO_ROOT"] = str(REPO_ROOT)
    env["PRISM_SCHEDULED_RUN_ID"] = run_id
    env["PRISM_SCHEDULED_VIA"] = "freshness_guardian"
    env["PRISM_SCHEDULER_PID"] = str(os.getpid())
    for path in (log_path.parent, meta_path.parent, latest_path.parent):
        path.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log_file:
        log_file.write(f"[{now_str()}] start {payload['title']}\n")
        log_file.write(f"[{now_str()}] command: {' '.join(command)}\n")
        log_file.write(f"[{now_str()}] freshness: {json.dumps(payload['freshness'], ensure_ascii=False)}\n")
        log_file.flush()
        proc = subprocess.Popen(
            command,
            cwd=REPO_ROOT,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
    payload["pid"] = proc.pid
    write_json(meta_path, payload)
    write_json(latest_path, payload)
    CHILD_RUNS[proc.pid] = {
        "task_name": task_name,
        "meta_path": str(meta_path),
        "latest_path": str(latest_path),
        "log_path": str(log_path),
    }
    append_event(
        {
            "event": "freshness_guardian_started",
            "task_name": task_name,
            "pid": proc.pid,
            "command": command,
            "freshness": payload["freshness"],
            "created_at": now_str(),
        }
    )
    print(f"[prism-scheduler] freshness guardian started {task_name} pid={proc.pid}", flush=True)
    return proc


def run_freshness_guardian(
    *,
    args: argparse.Namespace,
    children: dict[int, subprocess.Popen[str]],
    state: dict[str, Any],
    current: datetime,
    current_calendar: dict[str, Any],
    launched_tasks: set[str],
) -> bool:
    if not getattr(args, "freshness_guardian", False):
        return False
    guardian_state = state.get("freshness_guardian") if isinstance(state.get("freshness_guardian"), dict) else {}
    guardian_state["last_checked_at"] = now_str()
    guardian_state["enabled"] = True
    guardian_state["calendar"] = current_calendar
    guardian_state["last_skip_reason"] = ""
    fired = False
    if current_calendar.get("status") != "trading":
        guardian_state["last_skip_reason"] = f"non_trading_day:{current_calendar.get('status')}"
        state["freshness_guardian"] = guardian_state
        return False

    active_windows = {item["key"] for item in active_auto_windows(current)}
    for task_name in LIGHTWEIGHT_REFRESH_TASKS:
        policy = TASK_POLICIES.get(task_name)
        task_state = guardian_state.get(task_name) if isinstance(guardian_state.get(task_name), dict) else {}
        task_state["last_checked_at"] = now_str()
        task_state["active_windows"] = sorted(active_windows)
        task_state["cooldown_remaining_seconds"] = 0
        freshness = inspect_lightweight_dataset(task_name, current=current, calendar=current_calendar)
        task_state["freshness"] = {
            "dataset": freshness.get("dataset"),
            "age_seconds": freshness.get("age_seconds"),
            "stale_after_seconds": freshness.get("stale_after_seconds"),
            "freshness_status": freshness.get("freshness_status"),
            "trade_date": freshness.get("trade_date"),
            "stale_reasons": freshness.get("stale_reasons") or [],
            "manifest_path": freshness.get("manifest_path"),
        }
        required_windows = set(getattr(policy, "auto_windows", ()) or ())
        if required_windows and not active_windows.intersection(required_windows):
            task_state["last_decision"] = "skip"
            task_state["last_skip_reason"] = "outside_auto_window"
            guardian_state[task_name] = task_state
            continue
        if not freshness.get("stale"):
            task_state["last_decision"] = "fresh"
            task_state["last_skip_reason"] = ""
            guardian_state[task_name] = task_state
            continue
        conflict = lightweight_conflict_running(task_name, current=current, launched_tasks=launched_tasks)
        if conflict:
            task_state["last_decision"] = "skip"
            task_state["last_skip_reason"] = f"running:{conflict}"
            guardian_state[task_name] = task_state
            continue
        remaining = lightweight_cooldown_remaining(task_name, guardian_state, current)
        if remaining > 0:
            task_state["last_decision"] = "skip"
            task_state["last_skip_reason"] = "cooldown"
            task_state["cooldown_remaining_seconds"] = remaining
            guardian_state[task_name] = task_state
            continue

        proc = launch_lightweight_refresh(
            task_name,
            args=args,
            current=current,
            calendar=current_calendar,
            freshness=freshness,
        )
        task_state["last_decision"] = "launched" if proc is not None else "dry_run"
        task_state["last_skip_reason"] = ""
        task_state["last_triggered_at"] = current.strftime("%Y-%m-%d %H:%M:%S")
        task_state["last_trigger_reasons"] = list(freshness.get("stale_reasons") or [])
        guardian_state[task_name] = task_state
        launched_tasks.add(task_name)
        if proc is not None:
            children[proc.pid] = proc
        fired = True

    state["freshness_guardian"] = guardian_state
    return fired


def tick(*, args: argparse.Namespace, children: dict[int, subprocess.Popen[str]]) -> None:
    current = datetime.now()
    current_minute = minute_key(current)
    current_calendar = calendar_status(current)
    startup_minute = str(getattr(args, "started_minute", "") or "")
    state = load_json(STATE_PATH)
    last_fired = state.get("last_fired") if isinstance(state.get("last_fired"), dict) else {}
    catchup_fired = state.get("catchup_fired") if isinstance(state.get("catchup_fired"), dict) else {}
    recovery_fired = state.get("recovery_fired") if isinstance(state.get("recovery_fired"), dict) else {}
    send_to_feishu = should_send_to_feishu(args.send_to_feishu)
    launched_tasks: set[str] = set()
    fired = False

    for policy in CRON_POLICIES:
        run_state = run_state_for_task(policy.task_name, now=current, run_root=RUN_ROOT)
        if not cron_matches(policy.cron_expr, current):
            continue
        if last_fired.get(policy.task_name) == current_minute:
            continue
        if current_calendar.get("status") != "trading" and not args.allow_non_trading_day:
            skip_non_trading_day(policy, current)
        elif startup_minute == current_minute and not getattr(args, "fire_on_start", False):
            skip_startup_minute(policy, current)
        elif run_state.get("running"):
            append_event({"event": "job_skipped_running", "task_name": policy.task_name, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        elif run_state.get("today_success"):
            skip_already_success(policy, "cron")
        elif blockers := dependency_blockers(policy, current=current):
            if record_dependency_wait(state, policy, blockers, reason="cron", current=current):
                skip_dependency(policy, blockers, "cron")
        else:
            clear_dependency_waits(state, policy, current)
            launch_policy(
                policy,
                args=args,
                children=children,
                send_to_feishu=send_to_feishu and bool(getattr(policy, "delivery_default", True)),
                reason="cron",
            )
            launched_tasks.add(policy.task_name)
        last_fired[policy.task_name] = current_minute
        fired = True

    for policy in CRON_POLICIES:
        if current_calendar.get("status") != "trading" and not args.allow_non_trading_day:
            continue
        run_state = run_state_for_task(policy.task_name, now=current, run_root=RUN_ROOT)
        catchup_key = f"{day_key(current)}:{policy.task_name}"
        if catchup_window_open(policy, current) and catchup_key not in catchup_fired:
            if run_state.get("today_success"):
                skip_already_success(policy, "catchup")
                catchup_fired[catchup_key] = {
                    "status": "already_success",
                    "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
                fired = True
            elif run_state.get("running"):
                append_event({"event": "job_skipped_running", "task_name": policy.task_name, "reason": "catchup", "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
                catchup_fired[catchup_key] = {
                    "status": "already_running",
                    "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
                fired = True
            elif blockers := dependency_blockers(policy, current=current):
                if record_dependency_wait(state, policy, blockers, reason="catchup", current=current):
                    skip_dependency(policy, blockers, "catchup")
            else:
                clear_dependency_waits(state, policy, current)
                launch_policy(
                    policy,
                    args=args,
                    children=children,
                    send_to_feishu=send_to_feishu and bool(getattr(policy, "delivery_default", True)),
                    reason="catchup",
                )
                launched_tasks.add(policy.task_name)
                catchup_fired[catchup_key] = {
                    "status": "launched",
                    "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
                fired = True

        run_state = run_state_for_task(policy.task_name, now=current, run_root=RUN_ROOT)
        recovery_key = f"{day_key(current)}:{policy.task_name}"
        if (
            missed_run_recovery_open(policy, current)
            and recovery_key not in recovery_fired
            and not run_state.get("today_success")
            and not run_state.get("failed_today")
            and policy.task_name not in launched_tasks
        ):
            if run_state.get("running"):
                pass
            elif blockers := dependency_blockers(policy, current=current):
                if record_dependency_wait(state, policy, blockers, reason="missed_run", current=current):
                    skip_dependency(policy, blockers, "missed_run")
            else:
                clear_dependency_waits(state, policy, current)
                launch_policy(
                    policy,
                    args=args,
                    children=children,
                    send_to_feishu=send_to_feishu and bool(getattr(policy, "delivery_default", True)),
                    reason="missed_run",
                )
                launched_tasks.add(policy.task_name)
                recovery_fired[recovery_key] = {
                    "status": "launched",
                    "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
                fired = True
        elif missed_run_recovery_open(policy, current) and run_state.get("today_success") and recovery_key not in recovery_fired:
            recovery_fired[recovery_key] = {
                "status": "already_success",
                "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

        run_state = run_state_for_task(policy.task_name, now=current, run_root=RUN_ROOT)
        if retry_due(policy, run_state, current, scheduler_state=state):
            if policy.task_name in launched_tasks:
                continue
            if run_state.get("running"):
                continue
            if blockers := dependency_blockers(policy, current=current):
                if record_dependency_wait(state, policy, blockers, reason="retry", current=current):
                    skip_dependency(policy, blockers, "retry")
                continue
            clear_dependency_waits(state, policy, current)
            launch_policy(
                policy,
                args=args,
                children=children,
                send_to_feishu=send_to_feishu and bool(getattr(policy, "delivery_default", True)),
                reason="retry",
            )
            mark_retry_count(state, policy, current)
            fired = True

    if run_freshness_guardian(
        args=args,
        children=children,
        state=state,
        current=current,
        current_calendar=current_calendar,
        launched_tasks=launched_tasks,
    ):
        fired = True

    state["catchup_fired"] = catchup_fired
    state["recovery_fired"] = recovery_fired

    if fired or state.get("started_at") is None:
        state.update(
            {
                "started_at": state.get("started_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "last_tick_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "pid": os.getpid(),
                "last_fired": last_fired,
                "send_to_feishu": send_to_feishu,
                "calendar": current_calendar,
                "fire_on_start": bool(getattr(args, "fire_on_start", False)),
            }
        )
        write_json(STATE_PATH, state)
    else:
        state["last_tick_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        state["pid"] = os.getpid()
        state["calendar"] = current_calendar
        write_json(STATE_PATH, state)


def main() -> int:
    args = parse_args()
    args.started_minute = minute_key(datetime.now())
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)
    print(
        f"[prism-scheduler] started pid={os.getpid()} interval={args.interval_seconds}s once={args.once}",
        flush=True,
    )
    append_event({"event": "scheduler_started", "pid": os.getpid(), "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    children: dict[int, subprocess.Popen[str]] = {}
    while not STOP:
        reap_children(children)
        tick(args=args, children=children)
        if args.once:
            break
        time.sleep(max(1.0, args.interval_seconds))

    for proc in children.values():
        if proc.poll() is None:
            proc.terminate()
    append_event({"event": "scheduler_stopped", "pid": os.getpid(), "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
