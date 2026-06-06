from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(os.environ.get("PRISM_REPO_ROOT") or Path(__file__).resolve().parents[2]).resolve()
RUN_ROOT = REPO_ROOT / "data" / "scheduled_runs"
STATE_PATH = RUN_ROOT / "scheduler_state.json"

RUNNING_STATUSES = {"starting", "running"}
SUCCESS_STATUSES = {"success"}
FAILED_STATUSES = {"failed"}
RUNNING_MAX_AGE_SECONDS = 3 * 60 * 60


def parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def today_key(now: datetime | None = None) -> str:
    return (now or datetime.now()).strftime("%Y-%m-%d")


def pid_alive(pid: Any) -> bool:
    try:
        parsed = int(pid)
    except (TypeError, ValueError):
        return False
    if parsed <= 0:
        return False
    try:
        os.kill(parsed, 0)
    except OSError:
        return False
    return True


def run_trade_date(payload: Mapping[str, Any]) -> str:
    calendar = payload.get("calendar") if isinstance(payload.get("calendar"), Mapping) else {}
    for value in (
        calendar.get("trade_date") if isinstance(calendar, Mapping) else None,
        payload.get("trade_date"),
        payload.get("started_at"),
        payload.get("finished_at"),
        payload.get("run_id"),
    ):
        text = str(value or "").strip()
        if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
            return text[:10]
    return ""


def latest_path_for_task(task_name: str, *, run_root: Path = RUN_ROOT) -> Path:
    return run_root / "latest" / f"{task_name}.json"


def run_state_for_task(task_name: str, *, now: datetime | None = None, run_root: Path = RUN_ROOT) -> dict[str, Any]:
    current = now or datetime.now()
    expected_date = today_key(current)
    path = latest_path_for_task(task_name, run_root=run_root)
    payload = load_json(path)
    status = str(payload.get("status") or "missing") if payload else "missing"
    trade_date = run_trade_date(payload)
    same_day = trade_date == expected_date
    started_at = str(payload.get("started_at") or "")
    finished_at = str(payload.get("finished_at") or "")
    started_dt = parse_timestamp(started_at)
    finished_dt = parse_timestamp(finished_at)
    running_age_seconds = max(int((current - started_dt).total_seconds()), 0) if started_dt else None
    pid_is_alive = pid_alive(payload.get("pid")) if payload else False
    running = (
        status in RUNNING_STATUSES
        and same_day
        and pid_is_alive
        and (running_age_seconds is None or running_age_seconds <= RUNNING_MAX_AGE_SECONDS)
    )
    orphaned = bool(status in RUNNING_STATUSES and not running and payload)
    success = status in SUCCESS_STATUSES and same_day
    failed = (status in FAILED_STATUSES and same_day) or (orphaned and same_day)
    return {
        "task_name": task_name,
        "status": status,
        "same_day": same_day,
        "today_success": success,
        "running": running,
        "orphaned": orphaned,
        "pid_alive": pid_is_alive,
        "running_age_seconds": running_age_seconds,
        "failed_today": failed,
        "missing": not payload,
        "stale_latest": bool(payload and not same_day),
        "trade_date": trade_date,
        "expected_trade_date": expected_date,
        "run_id": str(payload.get("run_id") or ""),
        "title": str(payload.get("title") or payload.get("schedule_name") or task_name),
        "started_at": started_at,
        "finished_at": finished_at,
        "started_dt": started_dt,
        "finished_dt": finished_dt,
        "exit_code": payload.get("exit_code"),
        "skip_reason": str(payload.get("skip_reason") or ""),
        "log_path": str(payload.get("log_path") or ""),
        "meta_path": str(payload.get("meta_path") or path),
        "payload": payload,
    }


def task_states(task_names: Sequence[str], *, now: datetime | None = None, run_root: Path = RUN_ROOT) -> dict[str, dict[str, Any]]:
    return {task_name: run_state_for_task(task_name, now=now, run_root=run_root) for task_name in task_names}


def scheduler_alive(state: Mapping[str, Any], *, now: datetime | None = None, max_age_seconds: int = 90) -> bool:
    last_tick = parse_timestamp(state.get("last_tick_at"))
    if not last_tick:
        return False
    return ((now or datetime.now()) - last_tick).total_seconds() <= max_age_seconds


def load_scheduler_state(*, state_path: Path = STATE_PATH) -> dict[str, Any]:
    return load_json(state_path)


__all__ = [
    "RUN_ROOT",
    "STATE_PATH",
    "latest_path_for_task",
    "load_json",
    "load_scheduler_state",
    "pid_alive",
    "parse_timestamp",
    "run_state_for_task",
    "scheduler_alive",
    "task_states",
    "today_key",
    "write_json",
]
