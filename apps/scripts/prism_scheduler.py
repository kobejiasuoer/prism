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


def tick(*, args: argparse.Namespace, children: dict[int, subprocess.Popen[str]]) -> None:
    current = datetime.now()
    current_minute = minute_key(current)
    current_calendar = calendar_status(current)
    startup_minute = str(getattr(args, "started_minute", "") or "")
    state = load_json(STATE_PATH)
    last_fired = state.get("last_fired") if isinstance(state.get("last_fired"), dict) else {}
    send_to_feishu = should_send_to_feishu(args.send_to_feishu)
    fired = False

    for policy in CRON_POLICIES:
        if not cron_matches(policy.cron_expr, current):
            continue
        if last_fired.get(policy.task_name) == current_minute:
            continue
        if current_calendar.get("status") != "trading" and not args.allow_non_trading_day:
            skip_non_trading_day(policy, current)
        elif startup_minute == current_minute and not getattr(args, "fire_on_start", False):
            skip_startup_minute(policy, current)
        else:
            proc = launch_job(policy, args=args, send_to_feishu=send_to_feishu)
            if proc is not None:
                children[proc.pid] = proc
        last_fired[policy.task_name] = current_minute
        fired = True

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
