#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_ROOT = REPO_ROOT / "packages"
CONTROL_PANEL_ROOT = REPO_ROOT / "apps" / "control-panel"
STOCK_ANALYZER_ROOT = REPO_ROOT / "stock-analyzer"
for path in (PACKAGES_ROOT, CONTROL_PANEL_ROOT, STOCK_ANALYZER_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from prism_data.service import get_data_gateway  # noqa: E402
from prism_data.utils import digits_code, normalize_code  # noqa: E402
from readiness import expected_trade_date  # noqa: E402
from watchlist_registry import list_active_watchlist_stocks  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh lightweight Prism datasets")
    parser.add_argument("--kind", choices=["quotes", "capital_flow", "all"], default="all")
    parser.add_argument("--codes", default="", help="Comma-separated stock codes. Defaults to active watchlist.")
    parser.add_argument("--limit", type=int, default=60)
    parser.add_argument("--date", default="")
    return parser.parse_args()


def resolve_codes(raw: str, limit: int) -> list[str]:
    if raw.strip():
        candidates = [item.strip() for item in raw.split(",") if item.strip()]
    else:
        candidates = [str(item.get("code") or "") for item in list_active_watchlist_stocks()]
    normalized: list[str] = []
    for item in candidates:
        try:
            code = digits_code(item)
        except ValueError:
            continue
        if code not in normalized:
            normalized.append(code)
    return normalized[: max(limit, 1)]


def result_summary(result: Any) -> dict[str, Any]:
    manifest = dict(getattr(result, "manifest", {}) or {})
    return {
        "dataset": getattr(result, "dataset", manifest.get("dataset", "")),
        "request_key": getattr(result, "request_key", manifest.get("request_key", "")),
        "manifest_path": getattr(result, "manifest_path", manifest.get("manifest_path", "")),
        "data_path": getattr(result, "data_path", manifest.get("data_path", "")),
        "provider": manifest.get("provider"),
        "status": manifest.get("status"),
        "freshness_status": manifest.get("freshness_status"),
        "live_small_allowed": bool(manifest.get("live_small_allowed")),
        "fallback_used": bool(manifest.get("fallback_used")),
        "row_count": manifest.get("row_count"),
    }


def main() -> int:
    args = parse_args()
    trade_date = args.date.strip() or expected_trade_date()
    codes = resolve_codes(args.codes, args.limit)
    gateway = get_data_gateway()
    started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    results: list[dict[str, Any]] = []
    errors: list[str] = []

    if not codes:
        errors.append("no_active_codes")
    else:
        if args.kind in {"quotes", "all"}:
            try:
                result = gateway.fetch_quotes_batch(
                    [normalize_code(code) for code in codes],
                    trade_date=trade_date,
                    key="auto-quotes",
                    allow_fallback=True,
                )
                results.append(result_summary(result))
            except Exception as exc:
                errors.append(f"quotes:{exc}")
        if args.kind in {"capital_flow", "all"}:
            try:
                result = gateway.fetch_capital_flow_batch(
                    [normalize_code(code) for code in codes],
                    trade_date=trade_date,
                    key="auto-capital-flow",
                    allow_fallback=False,
                )
                results.append(result_summary(result))
            except Exception as exc:
                errors.append(f"capital_flow:{exc}")

    payload = {
        "ok": not errors,
        "kind": args.kind,
        "trade_date": trade_date,
        "codes": codes,
        "started_at": started_at,
        "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "results": results,
        "errors": errors,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
