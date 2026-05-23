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

from refresh_policy import CRON_POLICIES  # noqa: E402
from scheduled_run_state import run_state_for_task  # noqa: E402
from trading_calendar import calendar_status  # noqa: E402


RUN_ROOT = REPO_ROOT / "data" / "scheduled_runs"
STATE_PATH = RUN_ROOT / "scheduler_state.json"
EVENT_LOG_PATH = RUN_ROOT / "scheduler_events.jsonl"
DELIVERY_CONFIG_PATH = REPO_ROOT / "data" / "config" / "prism-delivery.local.json"
JOB_RUNNER = REPO_ROOT / "apps" / "scripts" / "prism_scheduled_job.py"
STOP = False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Prism internal scheduler.")
    parser.add_argument("--interval-seconds", type=float, default=float(os.environ.get("PRISM_SCHEDULER_INTERVAL_SECONDS", "20")))
    parser.add_argument("--once", action="store_true", help="Check due jobs once and exit.")
    parser.add_argument("--dry-run", action="store_true", help="Record due jobs without launching them.")
    parser.add_argument("--send-to-feishu", choices=["auto", "0", "1"], default=os.environ.get("PRISM_SCHEDULER_SEND_TO_FEISHU", "auto"))
    parser.add_argument("--allow-non-trading-day", action="store_true")
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
    print(f"[prism-scheduler] received signal {signum}; stopping after current tick", flush=True)


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
        append_event(
            {
                "event": "job_exit",
                "pid": pid,
                "exit_code": code,
                "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
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


def tick(*, args: argparse.Namespace, children: dict[int, subprocess.Popen[str]]) -> None:
    current = datetime.now()
    current_minute = minute_key(current)
    current_calendar = calendar_status(current)
    startup_minute = str(getattr(args, "started_minute", "") or "")
    state = load_json(STATE_PATH)
    last_fired = state.get("last_fired") if isinstance(state.get("last_fired"), dict) else {}
    catchup_fired = state.get("catchup_fired") if isinstance(state.get("catchup_fired"), dict) else {}
    send_to_feishu = should_send_to_feishu(args.send_to_feishu)
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
            skip_dependency(policy, blockers, "cron")
        else:
            launch_policy(
                policy,
                args=args,
                children=children,
                send_to_feishu=send_to_feishu and bool(getattr(policy, "delivery_default", True)),
                reason="cron",
            )
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
                skip_dependency(policy, blockers, "catchup")
            else:
                launch_policy(
                    policy,
                    args=args,
                    children=children,
                    send_to_feishu=send_to_feishu and bool(getattr(policy, "delivery_default", True)),
                    reason="catchup",
                )
                catchup_fired[catchup_key] = {
                    "status": "launched",
                    "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
                fired = True

        run_state = run_state_for_task(policy.task_name, now=current, run_root=RUN_ROOT)
        if retry_due(policy, run_state, current, scheduler_state=state):
            if run_state.get("running"):
                continue
            if blockers := dependency_blockers(policy, current=current):
                skip_dependency(policy, blockers, "retry")
                continue
            launch_policy(
                policy,
                args=args,
                children=children,
                send_to_feishu=send_to_feishu and bool(getattr(policy, "delivery_default", True)),
                reason="retry",
            )
            mark_retry_count(state, policy, current)
            fired = True

    state["catchup_fired"] = catchup_fired

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
