#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
QUALITY_PATTERNS = (
    REPO_ROOT / "stock-screener" / "data" / "quality_gate*.json",
    REPO_ROOT / "packages" / "data" / "quality_gate*.json",
    REPO_ROOT / "data" / "artifacts" / "screener" / "quality_gates" / "quality_gate*.json",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a compact quality gate dashboard")
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def collect_quality_gates(limit: int = 20) -> list[dict[str, Any]]:
    seen: set[Path] = set()
    rows: list[dict[str, Any]] = []
    for pattern in QUALITY_PATTERNS:
        for path in pattern.parent.glob(pattern.name):
            if path in seen or not path.is_file():
                continue
            seen.add(path)
            payload = load_json(path)
            rows.append(
                {
                    "path": path,
                    "checked_at": payload.get("checked_at") or payload.get("generated_at") or "",
                    "mode": payload.get("mode") or "screener",
                    "status": payload.get("validation_status") or "unknown",
                    "errors": payload.get("errors") or [],
                    "warnings": payload.get("warnings") or [],
                }
            )
    rows.sort(key=lambda item: (str(item.get("checked_at") or ""), str(item["path"])), reverse=True)
    return rows[:limit]


def render(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Prism Quality Gate Dashboard",
        "",
        f"Updated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "| checked_at | mode | status | notes | path |",
        "| --- | --- | --- | --- | --- |",
    ]
    if not rows:
        lines.append("| - | - | unknown | no quality gate records found | - |")
        return "\n".join(lines) + "\n"

    for row in rows:
        notes = "；".join(str(item) for item in [*(row.get("errors") or []), *(row.get("warnings") or [])][:3]) or "-"
        rel_path = row["path"]
        try:
            rel_path = row["path"].relative_to(REPO_ROOT)
        except ValueError:
            pass
        lines.append(
            f"| {row.get('checked_at') or '-'} | {row.get('mode') or '-'} | "
            f"{row.get('status') or '-'} | {notes} | {rel_path} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    output = Path(args.output).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(collect_quality_gates()), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
