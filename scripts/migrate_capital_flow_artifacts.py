#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_ROOT = REPO_ROOT / "packages"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(PACKAGES_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGES_ROOT))

from screener.capital_flow_contract import (  # noqa: E402
    UNIT_WAN_YUAN,
    UNIT_YUAN,
    normalize_capital_flow_payload,
    resolve_amount_wan,
    wan_to_yi,
)


STOCK_SCREENER_DATA_DIR = REPO_ROOT / "stock-screener" / "data"
STOCK_ANALYZER_DATA_DIR = REPO_ROOT / "stock-analyzer" / "data"
WATCHLIST_FLOW_FIELDS = ("main_net", "super_net", "mid_large_net", "retail_net", "small_net")


@dataclass
class MigrationStats:
    checked: int = 0
    changed: int = 0


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def normalize_nested_capital_flow(payload: Any, *, legacy_source_unit: str) -> Any:
    if isinstance(payload, list):
        return [normalize_nested_capital_flow(item, legacy_source_unit=legacy_source_unit) for item in payload]

    if not isinstance(payload, dict):
        return payload

    updated = {
        key: normalize_nested_capital_flow(value, legacy_source_unit=legacy_source_unit)
        for key, value in payload.items()
    }
    capital_flow = updated.get("capital_flow")
    if isinstance(capital_flow, Mapping):
        updated["capital_flow"] = normalize_capital_flow_payload(
            capital_flow,
            legacy_source_unit=legacy_source_unit,
        )
    return updated


def normalize_watchlist_flow_row(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    data = row or {}
    if not isinstance(data, Mapping):
        return None

    date = data.get("date")
    if not date:
        return None

    normalized = {"date": date, "unit": UNIT_WAN_YUAN}
    for field in WATCHLIST_FLOW_FIELDS:
        amount_wan = resolve_amount_wan(
            data,
            wan_keys=(f"{field}_wan",),
            yi_keys=(f"{field}_yi",),
            legacy_keys=(field,),
            source_unit=UNIT_WAN_YUAN,
        )
        normalized[field] = amount_wan
        normalized[f"{field}_wan"] = amount_wan
        normalized[f"{field}_yi"] = wan_to_yi(amount_wan)
    return normalized


def migrate_watchlist_flow_cache(payload: Any) -> Any:
    if not isinstance(payload, list):
        return payload

    migrated = []
    for row in payload:
        normalized_row = normalize_watchlist_flow_row(row)
        if normalized_row:
            migrated.append(normalized_row)
    return migrated


def migrate_watchlist_snapshot(payload: Any) -> Any:
    return normalize_nested_capital_flow(payload, legacy_source_unit=UNIT_WAN_YUAN)


def migrate_screener_artifact(payload: Any) -> Any:
    return normalize_nested_capital_flow(payload, legacy_source_unit=UNIT_YUAN)


def transform_payload(path: Path, payload: Any) -> Any:
    path_text = str(path)
    if "fund_flow_cache" in path_text:
        return migrate_watchlist_flow_cache(payload)
    if "daily_snapshots" in path_text:
        return migrate_watchlist_snapshot(payload)
    return migrate_screener_artifact(payload)


def iter_default_targets(*, include_backfill: bool = False) -> list[Path]:
    targets: list[Path] = []

    targets.extend(
        [
            STOCK_SCREENER_DATA_DIR / "scan_result.json",
            STOCK_SCREENER_DATA_DIR / "ai_screening_result.json",
            STOCK_SCREENER_DATA_DIR / "midday_verification_result.json",
        ]
    )
    targets.extend(sorted((STOCK_SCREENER_DATA_DIR / "ai_history").glob("ai_screening_*.json")))
    targets.extend(sorted((STOCK_SCREENER_DATA_DIR / "stale_outputs").glob("scan_result_previous*.json")))
    targets.extend(sorted((STOCK_ANALYZER_DATA_DIR / "fund_flow_cache").glob("*.json")))
    targets.extend(sorted((STOCK_ANALYZER_DATA_DIR / "daily_snapshots").glob("*.json")))

    if include_backfill:
        targets.extend(sorted((STOCK_SCREENER_DATA_DIR / "research_backfill" / "ai_history").glob("ai_screening_*.json")))

    return [path for path in targets if path.exists()]


def migrate_file(path: Path, *, apply: bool) -> bool:
    original = load_json(path)
    migrated = transform_payload(path, original)
    changed = migrated != original
    if changed and apply:
        path.write_text(dump_json(migrated), encoding="utf-8")
    return changed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize stock capital-flow artifacts to the shared contract.")
    parser.add_argument("--apply", action="store_true", help="write migrated JSON back to disk")
    parser.add_argument(
        "--include-backfill",
        action="store_true",
        help="also rewrite research_backfill ai_history artifacts",
    )
    parser.add_argument(
        "--path",
        action="append",
        default=[],
        help="migrate specific file(s) or directory roots; may be passed multiple times",
    )
    return parser.parse_args()


def expand_paths(values: list[str], *, include_backfill: bool) -> list[Path]:
    if not values:
        return iter_default_targets(include_backfill=include_backfill)

    resolved: list[Path] = []
    for raw in values:
        path = Path(raw).expanduser()
        if path.is_dir():
            resolved.extend(sorted(path.rglob("*.json")))
        elif path.exists():
            resolved.append(path)
    return resolved


def main() -> None:
    args = parse_args()
    stats = MigrationStats()
    targets = expand_paths(args.path, include_backfill=args.include_backfill)

    for path in targets:
        try:
            changed = migrate_file(path, apply=args.apply)
        except Exception as exc:  # pragma: no cover - CLI error reporting
            print(f"[skip] {path}: {exc}", file=sys.stderr)
            continue

        stats.checked += 1
        if changed:
            stats.changed += 1
            mode = "updated" if args.apply else "would update"
            print(f"[{mode}] {path}")

    mode = "apply" if args.apply else "dry-run"
    print(f"capital-flow migration {mode}: checked={stats.checked} changed={stats.changed}")


if __name__ == "__main__":
    main()
