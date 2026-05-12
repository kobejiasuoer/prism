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

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_PANEL_ROOT = REPO_ROOT / "apps" / "control-panel"
PACKAGES_ROOT = REPO_ROOT / "packages"
for path in (str(PACKAGES_ROOT), str(CONTROL_PANEL_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

try:
    from prism_storage import TaskRunRepository
except Exception:  # pragma: no cover - task metadata JSON remains the fallback.
    TaskRunRepository = None  # type: ignore[assignment]

from trading_calendar import calendar_status

DELIVERY_CONFIG_PATH = REPO_ROOT / "data" / "config" / "prism-delivery.local.json"
TRADING_DAY_PROTECTED_TASKS = {
    "aggressive",
    "capital_flow_light",
    "command_brief",
    "midday_confirmation",
    "midday_refresh",
    "postclose_command_brief",
    "preclose_risk_refresh",
    "quotes_light",
    "watchlist",
    "watchlist_refresh",
}
TASK_JOB_NAME_PREFERENCES = {
    "watchlist": ["自选股早盘分析"],
    "aggressive": ["进攻型选股-早盘"],
    "midday_refresh": ["进攻型选股-午盘"],
    "midday_confirmation": ["进攻型选股-午盘确认"],
}


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Control panel background task runner")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--task-name", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--meta", required=True)
    parser.add_argument("--log", required=True)
    parser.add_argument("--send-to-feishu", choices=["0", "1"], default="0")
    parser.add_argument("--allow-non-trading-day", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser.parse_args()


def write_meta(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if TaskRunRepository is None:
        return
    try:
        TaskRunRepository().upsert(payload, legacy_path=path)
    except Exception:
        return


def load_delivery_config() -> dict[str, Any]:
    if not DELIVERY_CONFIG_PATH.exists():
        return {}
    try:
        data = json.loads(DELIVERY_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def resolve_default_feishu_delivery(task_name: str) -> dict[str, str] | None:
    config = load_delivery_config()
    feishu = config.get("feishu") if isinstance(config.get("feishu"), dict) else {}
    tasks = feishu.get("tasks") if isinstance(feishu.get("tasks"), dict) else {}
    task_delivery = tasks.get(task_name) if isinstance(tasks.get(task_name), dict) else {}
    default_delivery = feishu.get("default") if isinstance(feishu.get("default"), dict) else {}
    delivery = {**default_delivery, **task_delivery}
    target = str(delivery.get("target") or delivery.get("to") or "").strip()
    if not target:
        return None

    return {
        "channel": str(delivery.get("channel") or "feishu").strip(),
        "target": target,
        "job_id": "",
        "job_name": ",".join(TASK_JOB_NAME_PREFERENCES.get(task_name, [])),
        "source": str(DELIVERY_CONFIG_PATH),
    }


def sanitize_shell_env(env: dict[str, str]) -> tuple[dict[str, str], bool]:
    sanitized = env.copy()
    current_python = Path(sys.executable).expanduser()
    current_bin = current_python.parent
    current_venv = current_bin.parent
    virtual_env = Path(sanitized.get("VIRTUAL_ENV", "")).expanduser() if sanitized.get("VIRTUAL_ENV") else None
    stripped = False

    if current_venv.name == "control-panel-venv" or (virtual_env and virtual_env.name == "control-panel-venv"):
        path_items = sanitized.get("PATH", "").split(os.pathsep)
        filtered = []
        for item in path_items:
            if not item:
                continue
            item_path = Path(item).expanduser()
            if item_path == current_bin:
                continue
            if virtual_env and item_path == virtual_env / "bin":
                continue
            filtered.append(item)
        sanitized["PATH"] = os.pathsep.join(filtered)
        sanitized.pop("VIRTUAL_ENV", None)
        stripped = True

    return sanitized, stripped


def should_skip_for_calendar(*, task_name: str, status: dict[str, Any], allow_non_trading_day: bool) -> bool:
    return (
        task_name in TRADING_DAY_PROTECTED_TASKS
        and status.get("status") != "trading"
        and not allow_non_trading_day
    )


def main() -> int:
    args = parse_args()
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("missing command")

    meta_path = Path(args.meta).expanduser()
    log_path = Path(args.log).expanduser()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    env, shell_env_sanitized = sanitize_shell_env(os.environ.copy())
    env["SEND_TO_FEISHU"] = args.send_to_feishu
    if args.task_name == "watchlist_refresh":
        env["COMMAND_SEND_TO_FEISHU"] = args.send_to_feishu

    feishu_delivery = {
        "requested": args.send_to_feishu == "1",
        "channel": str(env.get("FEISHU_CHANNEL") or "").strip(),
        "target": str(env.get("FEISHU_TARGET") or "").strip(),
        "source": "environment" if env.get("FEISHU_TARGET") else "",
        "job_id": "",
        "job_name": "",
        "resolved": False,
    }
    if args.send_to_feishu == "1":
        default_delivery = resolve_default_feishu_delivery(args.task_name)
        if default_delivery:
            if not feishu_delivery["channel"]:
                env["FEISHU_CHANNEL"] = default_delivery["channel"]
                feishu_delivery["channel"] = default_delivery["channel"]
            if not feishu_delivery["target"]:
                env["FEISHU_TARGET"] = default_delivery["target"]
                feishu_delivery["target"] = default_delivery["target"]
                feishu_delivery["source"] = default_delivery.get("source") or "delivery_config"
            feishu_delivery["job_id"] = default_delivery["job_id"]
            feishu_delivery["job_name"] = default_delivery["job_name"]
        if not feishu_delivery["channel"]:
            env["FEISHU_CHANNEL"] = "feishu"
            feishu_delivery["channel"] = "feishu"
            if not feishu_delivery["source"]:
                feishu_delivery["source"] = "default"
        feishu_delivery["resolved"] = bool(feishu_delivery["target"])

    payload = {
        "task_id": args.task_id,
        "task_name": args.task_name,
        "title": args.title,
        "command": command,
        "cwd": args.cwd,
        "send_to_feishu": args.send_to_feishu == "1",
        "status": "running",
        "started_at": now_str(),
        "finished_at": None,
        "exit_code": None,
        "pid": os.getpid(),
        "log_path": str(log_path),
        "meta_path": str(meta_path),
        "feishu_delivery": feishu_delivery,
        "shell_env_sanitized": shell_env_sanitized,
        "calendar": calendar_status(datetime.now()),
    }
    write_meta(meta_path, payload)

    if should_skip_for_calendar(
        task_name=args.task_name,
        status=payload["calendar"],
        allow_non_trading_day=args.allow_non_trading_day,
    ):
        payload.update(
            {
                "status": "skipped",
                "skip_reason": f"non_trading_day:{payload['calendar'].get('status')}",
                "finished_at": now_str(),
                "exit_code": 0,
            }
        )
        write_meta(meta_path, payload)
        log_path.write_text(
            f"[{now_str()}] skip {args.title}: {payload['calendar'].get('status')} "
            f"({payload['calendar'].get('reason')})\n",
            encoding="utf-8",
        )
        return 0

    with log_path.open("w", encoding="utf-8") as log_file:
        log_file.write(f"[{now_str()}] start {args.title}\n")
        log_file.write(f"[{now_str()}] command: {' '.join(command)}\n")
        log_file.write(f"[{now_str()}] calendar: {json.dumps(payload['calendar'], ensure_ascii=False)}\n")
        if shell_env_sanitized:
            log_file.write(f"[{now_str()}] shell env sanitized: removed control-panel-venv from PATH\n")
        if args.send_to_feishu == "1":
            if feishu_delivery["resolved"]:
                log_file.write(
                    f"[{now_str()}] feishu: {feishu_delivery['channel']} -> "
                    f"{feishu_delivery['target']} ({feishu_delivery['source'] or 'unknown'})\n"
                )
            else:
                log_file.write(f"[{now_str()}] feishu: requested but no target resolved\n")
        log_file.flush()
        proc = subprocess.run(
            command,
            cwd=args.cwd,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )

    payload["finished_at"] = now_str()
    payload["exit_code"] = proc.returncode
    payload["status"] = "success" if proc.returncode == 0 else "failed"
    write_meta(meta_path, payload)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
