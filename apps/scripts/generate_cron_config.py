#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_PANEL_ROOT = REPO_ROOT / "apps" / "control-panel"
if str(CONTROL_PANEL_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROL_PANEL_ROOT))

from refresh_policy import CRON_POLICIES, validate_cron_policies  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate or validate Prism OpenClaw cron config")
    parser.add_argument("--validate", type=str, default="", help="Validate an existing jobs.json instead of generating")
    parser.add_argument("--target", type=str, default="", help="Feishu target used in generated job payloads")
    return parser.parse_args()


def load_jobs(path: str) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    jobs = payload.get("jobs") if isinstance(payload, dict) else None
    return jobs if isinstance(jobs, list) else []


def main() -> int:
    args = parse_args()
    if args.validate:
        result = validate_cron_policies(load_jobs(args.validate))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1

    payload = {
        "version": 1,
        "jobs": [
            {
                "id": f"prism-{item.task_name}",
                **item.as_openclaw_job(target=args.target),
            }
            for item in CRON_POLICIES
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
