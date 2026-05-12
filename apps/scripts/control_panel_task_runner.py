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
PACKAGES_ROOT = REPO_ROOT / "packages"
if str(PACKAGES_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGES_ROOT))

try:
    from prism_storage import TaskRunRepository
except Exception:  # pragma: no cover - task metadata JSON remains the fallback.
    TaskRunRepository = None  # type: ignore[assignment]

CRON_JOBS_PATH = Path.home() / ".openclaw" / "cron" / "jobs.json"
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


def load_cron_jobs() -> list[dict]:
    if not CRON_JOBS_PATH.exists():
        return []
    try:
        data = json.loads(CRON_JOBS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    jobs = data.get("jobs")
    return jobs if isinstance(jobs, list) else []


def resolve_default_feishu_delivery(task_name: str) -> dict[str, str] | None:
    jobs = load_cron_jobs()
    if not jobs:
        return None

    preferred_names = TASK_JOB_NAME_PREFERENCES.get(task_name, [])

    def pick(candidates: list[dict]) -> dict[str, str] | None:
        for job in candidates:
            delivery = job.get("delivery") or {}
            channel = str(delivery.get("channel") or "").strip()
            target = str(delivery.get("to") or "").strip()
            if channel != "feishu" or not target:
                continue
            return {
                "channel": channel,
                "target": target,
                "job_id": str(job.get("id") or "").strip(),
                "job_name": str(job.get("name") or "").strip(),
            }
        return None

    named_matches = [job for job in jobs if str(job.get("name") or "") in preferred_names]
    delivery = pick(named_matches)
    if delivery:
        return delivery

    invest_jobs = [job for job in jobs if str(job.get("agentId") or "").strip() == "invest"]
    delivery = pick(invest_jobs)
    if delivery:
        return delivery

    return pick(jobs)


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
                feishu_delivery["source"] = "cron_jobs"
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
    }
    write_meta(meta_path, payload)

    with log_path.open("w", encoding="utf-8") as log_file:
        log_file.write(f"[{now_str()}] start {args.title}\n")
        log_file.write(f"[{now_str()}] command: {' '.join(command)}\n")
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
