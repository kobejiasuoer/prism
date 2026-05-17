#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_PANEL_ROOT = REPO_ROOT / "apps" / "control-panel"
PACKAGES_ROOT = REPO_ROOT / "packages"
for path in (str(REPO_ROOT), str(PACKAGES_ROOT), str(CONTROL_PANEL_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from readiness import expected_trade_date  # noqa: E402
from trading_calendar import calendar_status  # noqa: E402


OUTPUT_ROOT = REPO_ROOT / "data" / "scheduled_runs" / "morning_warmup"
LIGHTWEIGHT_REFRESH = REPO_ROOT / "apps" / "scripts" / "refresh_lightweight_data.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Prism's morning data warmup chain.")
    parser.add_argument("--date", default="", help="Trade date to refresh. Defaults to Prism expected trade date.")
    parser.add_argument("--limit", type=int, default=60, help="Maximum active watchlist symbols for light refreshes.")
    parser.add_argument("--skip-capital-flow", action="store_true", help="Refresh quotes only.")
    parser.add_argument("--allow-non-trading-day", action="store_true")
    return parser.parse_args()


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def run_step(name: str, command: list[str]) -> dict[str, Any]:
    started_at = now_str()
    proc = subprocess.run(
        command,
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    output = proc.stdout or ""
    parsed_output: Any = None
    try:
        parsed_output = json.loads(output)
    except Exception:
        parsed_output = None
    return {
        "name": name,
        "command": command,
        "status": "success" if proc.returncode == 0 else "failed",
        "exit_code": proc.returncode,
        "started_at": started_at,
        "finished_at": now_str(),
        "output": parsed_output if parsed_output is not None else output[-8000:],
    }


def main() -> int:
    args = parse_args()
    current = datetime.now()
    calendar = calendar_status(current)
    trade_date = args.date.strip() or expected_trade_date(current)
    run_stamp = current.strftime("%Y-%m-%d_%H-%M-%S")
    output_path = OUTPUT_ROOT / f"morning_warmup_{run_stamp}.json"
    latest_path = OUTPUT_ROOT / "latest.json"

    payload: dict[str, Any] = {
        "ok": False,
        "trade_date": trade_date,
        "calendar": calendar,
        "started_at": now_str(),
        "finished_at": None,
        "steps": [],
        "skip_reason": "",
    }

    if calendar.get("status") != "trading" and not args.allow_non_trading_day:
        payload.update(
            {
                "ok": True,
                "finished_at": now_str(),
                "skip_reason": f"non_trading_day:{calendar.get('status')}",
            }
        )
    else:
        steps = [
            (
                "quotes_light",
                [sys.executable, str(LIGHTWEIGHT_REFRESH), "--kind", "quotes", "--date", trade_date, "--limit", str(args.limit)],
            )
        ]
        if not args.skip_capital_flow:
            steps.append(
                (
                    "capital_flow_light",
                    [
                        sys.executable,
                        str(LIGHTWEIGHT_REFRESH),
                        "--kind",
                        "capital_flow",
                        "--date",
                        trade_date,
                        "--limit",
                        str(args.limit),
                    ],
                )
            )
        for name, command in steps:
            payload["steps"].append(run_step(name, command))
        payload["finished_at"] = now_str()
        payload["ok"] = all(step.get("exit_code") == 0 for step in payload["steps"])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    latest_path.write_text(json.dumps({**payload, "output_path": str(output_path)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**payload, "output_path": str(output_path)}, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
