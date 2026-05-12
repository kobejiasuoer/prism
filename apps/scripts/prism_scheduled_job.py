#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(os.environ.get("PRISM_REPO_ROOT") or Path(__file__).resolve().parents[2]).resolve()
CONTROL_PANEL_ROOT = REPO_ROOT / "apps" / "control-panel"
PACKAGES_ROOT = REPO_ROOT / "packages"
for path in (str(REPO_ROOT), str(PACKAGES_ROOT), str(CONTROL_PANEL_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from refresh_policy import CRON_POLICIES, TASK_POLICIES  # noqa: E402
from trading_calendar import calendar_status  # noqa: E402

if os.name == "nt":
    import msvcrt  # type: ignore[import-not-found]
else:
    import fcntl  # type: ignore[import-not-found]


RUN_ROOT = REPO_ROOT / "data" / "scheduled_runs"
DELIVERY_CONFIG_PATH = REPO_ROOT / "data" / "config" / "prism-delivery.local.json"
POLICIES = {item.task_name: item for item in CRON_POLICIES}


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one scheduled Prism task.")
    parser.add_argument("--task-name", required=True, choices=sorted(POLICIES))
    parser.add_argument("--allow-non-trading-day", action="store_true")
    parser.add_argument("--send-to-feishu", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_delivery_config() -> dict[str, Any]:
    if not DELIVERY_CONFIG_PATH.exists():
        return {}
    try:
        payload = json.loads(DELIVERY_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def build_env(*, send_to_feishu: bool, run_id: str) -> dict[str, str]:
    env = os.environ.copy()
    delivery_config = load_delivery_config()
    feishu = delivery_config.get("feishu") if isinstance(delivery_config.get("feishu"), dict) else {}
    default_delivery = feishu.get("default") if isinstance(feishu.get("default"), dict) else {}
    feishu_channel = str(default_delivery.get("channel") or "feishu").strip()
    feishu_target = str(default_delivery.get("target") or default_delivery.get("to") or "").strip()
    path_items = [
        str(REPO_ROOT / ".venv" / "bin"),
        "/opt/homebrew/bin",
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
        "/usr/sbin",
        "/sbin",
        *[item for item in env.get("PATH", "").split(os.pathsep) if item],
    ]
    deduped_path = []
    seen = set()
    for item in path_items:
        if item not in seen:
            deduped_path.append(item)
            seen.add(item)

    pythonpath_items = [
        str(REPO_ROOT),
        str(PACKAGES_ROOT),
        str(CONTROL_PANEL_ROOT),
        *[item for item in env.get("PYTHONPATH", "").split(os.pathsep) if item],
    ]

    env["PATH"] = os.pathsep.join(deduped_path)
    env["PYTHONPATH"] = os.pathsep.join(dict.fromkeys(pythonpath_items))
    env["PRISM_REPO_ROOT"] = str(REPO_ROOT)
    env["PRISM_SCHEDULED_RUN_ID"] = run_id
    env["PRISM_SCHEDULED_VIA"] = env.get("PRISM_SCHEDULED_VIA") or "prism_scheduler"
    env["SEND_TO_FEISHU"] = "1" if send_to_feishu else env.get("SEND_TO_FEISHU", "0")
    env["COMMAND_SEND_TO_FEISHU"] = env.get("COMMAND_SEND_TO_FEISHU", env["SEND_TO_FEISHU"])
    env["WATCHLIST_SEND_TO_FEISHU"] = env.get("WATCHLIST_SEND_TO_FEISHU", "0")
    if send_to_feishu:
        env["FEISHU_CHANNEL"] = env.get("FEISHU_CHANNEL") or feishu_channel
        env["FEISHU_TARGET"] = env.get("FEISHU_TARGET") or feishu_target
    return env


def update_payload(path: Path, latest_path: Path, payload: dict[str, Any]) -> None:
    write_json(path, payload)
    write_json(latest_path, payload)


def should_skip_for_calendar(*, status: dict[str, Any], allow_non_trading_day: bool) -> bool:
    return status.get("status") != "trading" and not allow_non_trading_day


def try_lock(lock_file) -> bool:
    if os.name == "nt":
        try:
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except BlockingIOError:
        return False


def main() -> int:
    args = parse_args()
    policy = POLICIES[args.task_name]
    task_policy = TASK_POLICIES.get(args.task_name)
    run_stamp = stamp()
    run_id = f"{args.task_name}_{run_stamp}"
    log_path = RUN_ROOT / "logs" / f"{run_id}.log"
    meta_path = RUN_ROOT / "runs" / f"{run_id}.json"
    latest_path = RUN_ROOT / "latest" / f"{args.task_name}.json"
    lock_path = RUN_ROOT / "locks" / f"{args.task_name}.lock"

    for path in (log_path.parent, meta_path.parent, latest_path.parent, lock_path.parent):
        path.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {
        "run_id": run_id,
        "task_name": args.task_name,
        "title": task_policy.title if task_policy else policy.name,
        "schedule_name": policy.name,
        "command": list(policy.command),
        "cwd": str(REPO_ROOT),
        "status": "starting",
        "started_at": now_str(),
        "finished_at": None,
        "exit_code": None,
        "pid": os.getpid(),
        "log_path": str(log_path),
        "meta_path": str(meta_path),
        "calendar": None,
        "send_to_feishu": bool(args.send_to_feishu),
    }
    update_payload(meta_path, latest_path, payload)

    with lock_path.open("a+", encoding="utf-8") as lock_file:
        if not try_lock(lock_file):
            payload.update(
                {
                    "status": "skipped",
                    "skip_reason": "already_running",
                    "finished_at": now_str(),
                    "exit_code": 0,
                }
            )
            update_payload(meta_path, latest_path, payload)
            print(f"{run_id}: skipped already_running")
            return 0

        lock_file.seek(0)
        lock_file.truncate()
        lock_file.write(str(os.getpid()))
        lock_file.flush()

        today_status = calendar_status(datetime.now())
        payload["calendar"] = today_status
        if should_skip_for_calendar(status=today_status, allow_non_trading_day=args.allow_non_trading_day):
            payload.update(
                {
                    "status": "skipped",
                    "skip_reason": f"non_trading_day:{today_status.get('status')}",
                    "finished_at": now_str(),
                    "exit_code": 0,
                }
            )
            update_payload(meta_path, latest_path, payload)
            log_path.write_text(
                f"[{now_str()}] skip {policy.name}: {today_status.get('status')} "
                f"({today_status.get('reason')})\n",
                encoding="utf-8",
            )
            print(f"{run_id}: skipped {today_status.get('status')}")
            return 0

        env = build_env(send_to_feishu=args.send_to_feishu, run_id=run_id)
        payload["status"] = "running"
        payload["env"] = {
            "PATH": env.get("PATH", ""),
            "PYTHONPATH": env.get("PYTHONPATH", ""),
            "SEND_TO_FEISHU": env.get("SEND_TO_FEISHU", "0"),
            "COMMAND_SEND_TO_FEISHU": env.get("COMMAND_SEND_TO_FEISHU", "0"),
            "PRISM_SCHEDULED_VIA": env.get("PRISM_SCHEDULED_VIA", ""),
            "FEISHU_CHANNEL": env.get("FEISHU_CHANNEL", ""),
            "FEISHU_TARGET": "<set>" if env.get("FEISHU_TARGET") else "",
        }
        update_payload(meta_path, latest_path, payload)

        with log_path.open("w", encoding="utf-8") as log_file:
            log_file.write(f"[{now_str()}] start {policy.name}\n")
            log_file.write(f"[{now_str()}] run_id: {run_id}\n")
            log_file.write(f"[{now_str()}] command: {' '.join(policy.command)}\n")
            log_file.write(f"[{now_str()}] calendar: {json.dumps(today_status, ensure_ascii=False)}\n")
            log_file.flush()

            if args.dry_run:
                exit_code = 0
                log_file.write(f"[{now_str()}] dry-run, command not executed\n")
            else:
                proc = subprocess.run(
                    list(policy.command),
                    cwd=REPO_ROOT,
                    env=env,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                exit_code = proc.returncode

            log_file.write(f"[{now_str()}] finish exit_code={exit_code}\n")

        payload.update(
            {
                "status": "success" if exit_code == 0 else "failed",
                "finished_at": now_str(),
                "exit_code": exit_code,
            }
        )
        update_payload(meta_path, latest_path, payload)
        print(f"{run_id}: {payload['status']} exit_code={exit_code}")
        return int(exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
