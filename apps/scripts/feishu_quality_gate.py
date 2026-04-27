#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate generated Feishu/report artifacts before delivery")
    parser.add_argument("--mode", default="screener")
    parser.add_argument("--generator", required=True)
    parser.add_argument("--scan-input")
    parser.add_argument("--ai-input")
    parser.add_argument("--midday-input")
    parser.add_argument("--message", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report-output", required=True)
    parser.add_argument("--lifecycle-input")
    return parser.parse_args()


def load_json(path_value: str | None) -> dict[str, Any]:
    if not path_value:
        return {}
    path = Path(path_value).expanduser()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def file_has_text(path_value: str | None) -> bool:
    if not path_value:
        return False
    path = Path(path_value).expanduser()
    try:
        return path.is_file() and bool(path.read_text(encoding="utf-8", errors="ignore").strip())
    except OSError:
        return False


def build_result(args: argparse.Namespace) -> dict[str, Any]:
    ai_payload = load_json(args.ai_input)
    scan_payload = load_json(args.scan_input)
    midday_payload = load_json(args.midday_input)
    lifecycle_payload = load_json(args.lifecycle_input)
    errors: list[str] = []
    warnings: list[str] = []

    if args.ai_input and not ai_payload:
        errors.append(f"AI 输入不可读或为空：{args.ai_input}")
    if args.scan_input and not scan_payload:
        warnings.append(f"scan 输入不可读或为空：{args.scan_input}")
    if args.midday_input and not midday_payload:
        errors.append(f"午盘输入不可读或为空：{args.midday_input}")
    if not file_has_text(args.message):
        errors.append(f"消息正文为空：{args.message}")
    if not file_has_text(args.report):
        errors.append(f"Markdown 报告为空：{args.report}")
    if not Path(args.generator).expanduser().exists():
        errors.append(f"生成器不存在：{args.generator}")

    expected_timestamp = (
        midday_payload.get("timestamp")
        or ai_payload.get("timestamp")
        or ai_payload.get("source_scan_timestamp")
        or scan_payload.get("timestamp")
        or ""
    )
    stats = {
        "shortlist_count": len(ai_payload.get("shortlist") or []),
        "has_lifecycle": bool(lifecycle_payload),
    }
    if midday_payload:
        stats.update(
            {
                "confirmed_count": len(midday_payload.get("confirmed") or []),
                "downgraded_count": len(midday_payload.get("downgraded") or []),
                "fresh_candidates_count": len(midday_payload.get("fresh_candidates") or []),
            }
        )

    return {
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": args.mode,
        "validation_status": "ok" if not errors else "failed",
        "errors": errors,
        "warnings": warnings,
        "paths": {
            "message": args.message,
            "report": args.report,
            "generator": args.generator,
        },
        "expected_timestamp": expected_timestamp,
        "stats": stats,
    }


def render_report(result: dict[str, Any]) -> str:
    ok = result.get("validation_status") == "ok"
    stats = result.get("stats") or {}
    lines = [
        f"# 飞书质检结果 | {result.get('mode')}",
        "",
        f"- 状态：{'通过' if ok else '失败'}",
        f"- 检查时间：{result.get('checked_at')}",
        f"- 目标时间：{result.get('expected_timestamp') or '-'}",
        "- 统计："
        + " | ".join(f"{key}: {value}" for key, value in stats.items()),
    ]
    errors = result.get("errors") or []
    warnings = result.get("warnings") or []
    if errors:
        lines.append("- 错误：" + "；".join(str(item) for item in errors))
    if warnings:
        lines.append("- 提醒：" + "；".join(str(item) for item in warnings))
    paths = result.get("paths") or {}
    lines.extend(["- 路径：", *[f"  - {key}: {value}" for key, value in paths.items()]])
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    result = build_result(args)
    output = Path(args.output).expanduser()
    report_output = Path(args.report_output).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    report_output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_output.write_text(render_report(result), encoding="utf-8")
    return 0 if result["validation_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
