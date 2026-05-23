"""Inventory local inputs for a historical shadow-replay sample build.

This is deliberately read-mostly: it inspects local Prism artifacts and
reports what is already available for a requested historical window.  It
does not fetch market data, run the screener, or write Decision Ledger
records.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_PANEL_ROOT = REPO_ROOT / "apps" / "control-panel"
if str(CONTROL_PANEL_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROL_PANEL_ROOT))

from trading_calendar import calendar_status  # type: ignore  # noqa: E402


DEFAULT_START_DATE = "2025-05-01"
DEFAULT_END_DATE = "2025-12-31"
DEFAULT_OUTPUT_JSON = REPO_ROOT / "data" / "quant" / "reports" / "shadow_replay_inventory_2025_latest.json"
DEFAULT_OUTPUT_MD = REPO_ROOT / "data" / "quant" / "reports" / "shadow_replay_inventory_2025_latest.md"

PRISM_DATASETS = (
    "bars.daily",
    "index.constituents",
    "quotes.pool",
    "quotes.batch",
    "capital_flow.daily",
    "fundamentals.batch",
    "fundamentals.snapshot",
    "announcements.latest",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inventory local data readiness for historical shadow replay samples.",
    )
    parser.add_argument("--start-date", default=DEFAULT_START_DATE, help="Inclusive YYYY-MM-DD start date.")
    parser.add_argument("--end-date", default=DEFAULT_END_DATE, help="Inclusive YYYY-MM-DD end date.")
    parser.add_argument(
        "--output-json",
        default=str(DEFAULT_OUTPUT_JSON),
        help="Where to write the machine-readable inventory report.",
    )
    parser.add_argument(
        "--output-md",
        default=str(DEFAULT_OUTPUT_MD),
        help="Where to write the human-readable inventory report.",
    )
    return parser.parse_args()


def parse_date(value: str) -> date:
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def day_range(start: date, end: date) -> Iterable[date]:
    cursor = start
    while cursor <= end:
        yield cursor
        cursor += timedelta(days=1)


def trading_days(start: date, end: date) -> list[str]:
    out: list[str] = []
    for day in day_range(start, end):
        text = day.strftime("%Y-%m-%d")
        if calendar_status(text).get("status") == "trading":
            out.append(text)
    return out


def safe_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def payload_trade_date(path: Path) -> str | None:
    raw = safe_json(path)
    if isinstance(raw, dict):
        replay_meta = raw.get("replay_meta") if isinstance(raw.get("replay_meta"), dict) else {}
        summary = raw.get("summary") if isinstance(raw.get("summary"), dict) else {}
        value = (
            raw.get("trade_date")
            or raw.get("date")
            or raw.get("timestamp")
            or raw.get("source_scan_timestamp")
            or replay_meta.get("trade_date")
            or summary.get("trade_date")
        )
        if value:
            return str(value)[:10]
    stem = path.stem
    for chunk in stem.replace("_", "-").split("-"):
        # Keep the filename fallback conservative; most relevant files
        # already expose a trade_date in payload metadata.
        if len(chunk) == 8 and chunk.isdigit():
            return f"{chunk[:4]}-{chunk[4:6]}-{chunk[6:]}"
    parts = stem.split("_")
    for part in parts:
        if len(part) == 10 and part[4] == "-" and part[7] == "-":
            return part
    return None


def count_shortlist(path: Path) -> int:
    raw = safe_json(path)
    if not isinstance(raw, dict):
        return 0
    shortlist = raw.get("shortlist")
    if isinstance(shortlist, list):
        return len(shortlist)
    return 0


def artifact_inventory(root: Path, pattern: str, *, start: str, end: str) -> dict[str, Any]:
    files = sorted(root.glob(pattern)) if root.exists() else []
    in_range: list[Path] = []
    by_year: Counter[str] = Counter()
    shortlist_total = 0
    for path in files:
        trade_date = payload_trade_date(path)
        if trade_date:
            by_year[trade_date[:4]] += 1
            if start <= trade_date <= end:
                in_range.append(path)
                shortlist_total += count_shortlist(path)
    return {
        "root": workspace_relative(root),
        "pattern": pattern,
        "total_files": len(files),
        "files_in_requested_window": len(in_range),
        "shortlist_rows_in_requested_window": shortlist_total,
        "years": dict(sorted(by_year.items())),
        "first_in_window": workspace_relative(in_range[0]) if in_range else None,
        "last_in_window": workspace_relative(in_range[-1]) if in_range else None,
    }


def dataset_inventory(dataset: str, *, start: str, end: str) -> dict[str, Any]:
    root = REPO_ROOT / "data" / "prism_data" / "datasets" / dataset
    date_dirs = sorted(path for path in root.iterdir() if root.exists() and path.is_dir())
    dates = [path.name for path in date_dirs if len(path.name) == 10]
    in_range = [value for value in dates if start <= value <= end]
    latest = max(dates) if dates else None
    years = Counter(value[:4] for value in dates)

    sample_files: list[str] = []
    payload_counts: dict[str, int] = {}
    for value in in_range[:5]:
        payloads = [
            p
            for p in (root / value).glob("*.json")
            if not p.name.endswith(".manifest.json")
        ]
        payload_counts[value] = len(payloads)
        sample_files.extend(workspace_relative(p) for p in payloads[:5])

    latest_payload_count = 0
    latest_payload_names: list[str] = []
    if latest:
        latest_payloads = [
            p
            for p in (root / latest).glob("*.json")
            if not p.name.endswith(".manifest.json")
        ]
        latest_payload_count = len(latest_payloads)
        latest_payload_names = [p.name for p in latest_payloads[:12]]

    return {
        "dataset": dataset,
        "root": workspace_relative(root),
        "date_dirs_total": len(dates),
        "date_dirs_in_requested_window": len(in_range),
        "years": dict(sorted(years.items())),
        "earliest_date": min(dates) if dates else None,
        "latest_date": latest,
        "latest_payload_count": latest_payload_count,
        "latest_payload_names": latest_payload_names,
        "sample_payload_counts_in_window": payload_counts,
        "sample_files_in_window": sample_files,
    }


def research_price_cache_inventory(*, start: str, end: str) -> dict[str, Any]:
    root = REPO_ROOT / "stock-screener" / "data" / "research_backfill" / "cache" / "price_kline"
    files = sorted(root.glob("*.json")) if root.exists() else []
    ranges: list[tuple[str, str, str]] = []
    overlapping = 0
    codes: set[str] = set()
    for path in files:
        stem = path.stem
        parts = stem.split("_")
        if len(parts) < 3:
            continue
        code, start_raw, end_raw = parts[0], parts[-2], parts[-1]
        if not (start_raw.isdigit() and end_raw.isdigit() and len(start_raw) == 8 and len(end_raw) == 8):
            continue
        range_start = f"{start_raw[:4]}-{start_raw[4:6]}-{start_raw[6:]}"
        range_end = f"{end_raw[:4]}-{end_raw[4:6]}-{end_raw[6:]}"
        ranges.append((code, range_start, range_end))
        codes.add(code)
        if range_start <= end and range_end >= start:
            overlapping += 1
    return {
        "root": workspace_relative(root),
        "files_total": len(files),
        "unique_codes": len(codes),
        "ranges_total": len(ranges),
        "overlapping_requested_window": overlapping,
        "earliest_range_start": min((item[1] for item in ranges), default=None),
        "latest_range_end": max((item[2] for item in ranges), default=None),
    }


def jsonl_year_inventory(path: Path, *, date_field_candidates: tuple[str, ...]) -> dict[str, Any]:
    years: Counter[str] = Counter()
    rows = 0
    source_lanes: Counter[str] = Counter()
    if path.exists():
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rows += 1
                value = ""
                for field in date_field_candidates:
                    if row.get(field):
                        value = str(row.get(field))[:10]
                        break
                if value:
                    years[value[:4]] += 1
                lane = str(row.get("source_lane") or row.get("label_scope") or "")
                source_lanes[lane] += 1
    return {
        "path": workspace_relative(path),
        "rows": rows,
        "years": dict(sorted(years.items())),
        "top_source_lanes": dict(source_lanes.most_common(10)),
    }


def shadow_replay_inventory(*, start: str, end: str) -> dict[str, Any]:
    root = REPO_ROOT / "data" / "quant" / "shadow_replay"
    manifests = sorted(root.glob("*/manifest.json")) if root.exists() else []
    runs: list[dict[str, Any]] = []
    total_price_files = 0
    total_price_rows = 0
    max_universe_codes = 0
    provider_counts: Counter[str] = Counter()

    for path in manifests:
        raw = safe_json(path)
        if not isinstance(raw, dict):
            continue
        args = raw.get("args") if isinstance(raw.get("args"), dict) else {}
        summary = raw.get("summary") if isinstance(raw.get("summary"), dict) else {}
        run_start = str(args.get("start_date") or "")[:10]
        run_end = str(args.get("end_date") or "")[:10]
        if run_start and run_start > end:
            continue
        if run_end and run_end < start:
            continue
        price_files = int(
            summary.get("price_files_available")
            or (int(summary.get("price_files_written") or 0) + int(summary.get("price_files_skipped_existing") or 0))
        )
        price_rows = int(summary.get("price_rows_available") or summary.get("price_rows_written") or 0)
        universe_codes = int(summary.get("unique_universe_codes") or 0)
        total_price_files += price_files
        total_price_rows += price_rows
        max_universe_codes = max(max_universe_codes, universe_codes)
        for provider, count in (summary.get("price_provider_counts") or {}).items():
            provider_counts[str(provider)] += int(count or 0)
        runs.append(
            {
                "path": workspace_relative(path),
                "status": summary.get("status"),
                "start_date": run_start,
                "end_date": run_end,
                "fetch_start": summary.get("fetch_start"),
                "fetch_end": summary.get("fetch_end"),
                "universe_policy": summary.get("universe_policy"),
                "unique_universe_codes": universe_codes,
                "price_files": price_files,
                "price_rows": price_rows,
                "price_fetch_failures": int(summary.get("price_fetch_failures") or 0),
                "provider_counts": dict(summary.get("price_provider_counts") or {}),
                "report": workspace_relative(path.with_name("report.md")),
            }
        )
    return {
        "root": workspace_relative(root),
        "matching_runs": len(runs),
        "max_universe_codes": max_universe_codes,
        "price_files_total": total_price_files,
        "price_rows_total": total_price_rows,
        "provider_counts": dict(provider_counts),
        "runs": runs,
    }


def shadow_signal_inventory(*, start: str, end: str) -> dict[str, Any]:
    root = REPO_ROOT / "data" / "quant" / "shadow_replay"
    manifests = sorted(root.glob("*/shadow_signal_manifest.json")) if root.exists() else []
    runs: list[dict[str, Any]] = []
    total_panel_rows = 0
    total_label_rows = 0
    total_available_labels = 0
    for path in manifests:
        raw = safe_json(path)
        if not isinstance(raw, dict):
            continue
        args = raw.get("args") if isinstance(raw.get("args"), dict) else {}
        summary = raw.get("summary") if isinstance(raw.get("summary"), dict) else {}
        run_start = str(args.get("start_date") or summary.get("start_date") or "")[:10]
        run_end = str(args.get("end_date") or summary.get("end_date") or "")[:10]
        if run_start and run_start > end:
            continue
        if run_end and run_end < start:
            continue
        panel_rows = int(summary.get("panel_rows") or 0)
        label_rows = int(summary.get("label_rows") or 0)
        available_labels = int(summary.get("available_labels") or 0)
        total_panel_rows += panel_rows
        total_label_rows += label_rows
        total_available_labels += available_labels
        outputs = raw.get("outputs") if isinstance(raw.get("outputs"), dict) else {}
        runs.append(
            {
                "path": workspace_relative(path),
                "status": summary.get("status"),
                "start_date": run_start,
                "end_date": run_end,
                "panel_rows": panel_rows,
                "label_rows": label_rows,
                "available_labels": available_labels,
                "bucket_counts": dict(summary.get("bucket_counts") or {}),
                "classification_counts": dict(summary.get("classification_counts") or {}),
                "panel": outputs.get("panel"),
                "labels": outputs.get("labels"),
                "report": outputs.get("report"),
            }
        )
    return {
        "root": workspace_relative(root),
        "matching_runs": len(runs),
        "panel_rows_total": total_panel_rows,
        "label_rows_total": total_label_rows,
        "available_labels_total": total_available_labels,
        "runs": runs,
    }


def import_capabilities() -> dict[str, Any]:
    capabilities: dict[str, Any] = {}
    for module in ("akshare", "baostock", "pandas"):
        try:
            __import__(module)
        except Exception as exc:
            capabilities[module] = {"importable": False, "error": str(exc)}
        else:
            capabilities[module] = {"importable": True, "error": None}
    return capabilities


def workspace_relative(path: str | Path) -> str:
    target = Path(path)
    try:
        return str(target.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(target)


def build_inventory(start_text: str, end_text: str) -> dict[str, Any]:
    start = parse_date(start_text)
    end = parse_date(end_text)
    if end < start:
        raise ValueError("--end-date must be on or after --start-date")

    start_s = start.strftime("%Y-%m-%d")
    end_s = end.strftime("%Y-%m-%d")
    requested_trading_days = trading_days(start, end)
    all_calendar_days = list(day_range(start, end))

    datasets = {
        dataset: dataset_inventory(dataset, start=start_s, end=end_s)
        for dataset in PRISM_DATASETS
    }
    shadow_replay = shadow_replay_inventory(start=start_s, end=end_s)
    shadow_signal = shadow_signal_inventory(start=start_s, end=end_s)
    local_2025_signal_rows = jsonl_year_inventory(
        REPO_ROOT / "data" / "quant" / "panels" / "daily_signal_panel.jsonl",
        date_field_candidates=("trade_date", "signal_trade_date"),
    )
    local_2025_label_rows = jsonl_year_inventory(
        REPO_ROOT / "data" / "quant" / "labels" / "forward_return_labels_hardened.jsonl",
        date_field_candidates=("trade_date", "signal_trade_date"),
    )

    date_count = len(requested_trading_days)
    estimates = {
        "lean_top10_only": date_count * 10,
        "useful_top10_near20_reject10": date_count * 40,
        "richer_top10_near30_reject20": date_count * 60,
    }

    blockers: list[str] = []
    warnings: list[str] = []
    if not datasets["bars.daily"]["date_dirs_in_requested_window"] and not shadow_replay["price_files_total"]:
        blockers.append("No local 2025 bars.daily or shadow_replay price cache found for the requested window.")
    elif shadow_replay["price_files_total"] and shadow_replay["max_universe_codes"] < 700:
        blockers.append(
            f"Only partial shadow_replay price cache is present ({shadow_replay['max_universe_codes']} codes); run the backfill job without --limit-codes for the full HS300+CSI500 universe."
        )
    if not datasets["index.constituents"]["date_dirs_in_requested_window"] and not shadow_replay["max_universe_codes"]:
        blockers.append("No local 2025 index.constituents snapshots found; historical HS300/CSI500 membership must be fetched or explicitly approximated.")
    elif shadow_replay["max_universe_codes"]:
        warnings.append("Shadow replay universe uses current_constituents_approx; keep it separate from point-in-time constituent samples.")
    if not artifact_inventory(
        REPO_ROOT / "stock-screener" / "data" / "research_backfill" / "ai_history",
        "ai_screening_*.json",
        start=start_s,
        end=end_s,
    )["files_in_requested_window"] and not shadow_signal["panel_rows_total"]:
        blockers.append("No local 2025 screener/AI backfill artifacts found; the replay generator must be run before importing shadow decisions.")
    elif shadow_signal["panel_rows_total"]:
        warnings.append("Price-signal shadow samples exist; they are useful for sample volume but are not production Prism AI replay artifacts.")

    inventory = {
        "schema_version": 1,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "requested_window": {
            "start_date": start_s,
            "end_date": end_s,
            "calendar_days": len(all_calendar_days),
            "trading_days": date_count,
            "first_trading_day": requested_trading_days[0] if requested_trading_days else None,
            "last_trading_day": requested_trading_days[-1] if requested_trading_days else None,
        },
        "target_scope": {
            "sample_origin": "historical_shadow",
            "desired_universe": ["HS300", "CSI500"],
            "recommended_universe_policy": "prefer point-in-time constituents; otherwise mark approx_current_universe and keep separate from live samples",
            "recommended_horizons": ["T+1", "T+3", "T+5"],
        },
        "sample_estimates": estimates,
        "local_artifacts": {
            "research_backfill_ai_history": artifact_inventory(
                REPO_ROOT / "stock-screener" / "data" / "research_backfill" / "ai_history",
                "ai_screening_*.json",
                start=start_s,
                end=end_s,
            ),
            "research_backfill_scan_history": artifact_inventory(
                REPO_ROOT / "stock-screener" / "data" / "research_backfill" / "history",
                "aggressive_all_*.json",
                start=start_s,
                end=end_s,
            ),
            "current_screener_ai_history": artifact_inventory(
                REPO_ROOT / "stock-screener" / "data" / "ai_history",
                "ai_screening_*.json",
                start=start_s,
                end=end_s,
            ),
            "research_price_kline_cache": research_price_cache_inventory(start=start_s, end=end_s),
            "shadow_replay": shadow_replay,
            "shadow_signal": shadow_signal,
            "quant_daily_signal_panel": local_2025_signal_rows,
            "quant_forward_return_labels_hardened": local_2025_label_rows,
        },
        "prism_data_cache": datasets,
        "local_provider_imports": import_capabilities(),
        "readiness": {
            "status": "needs_backfill" if blockers else "local_inputs_present",
            "blockers": blockers,
            "warnings": warnings,
            "recommended_next_step": (
                "Build a 2025 replay data fetch + screener backfill job, then re-run this inventory before importing shadow samples."
                if blockers
                else "Proceed to historical_shadow import/evaluation in a separate ledger namespace."
            ),
        },
    }
    return inventory


def pct(value: int, total: int) -> str:
    if total <= 0:
        return "0.0%"
    return f"{value / total * 100:.1f}%"


def render_markdown(inventory: dict[str, Any]) -> str:
    window = inventory["requested_window"]
    local = inventory["local_artifacts"]
    datasets = inventory["prism_data_cache"]
    readiness = inventory["readiness"]
    trading_days_total = int(window["trading_days"])

    lines = [
        "# 2025 Historical Shadow Replay Inventory",
        "",
        f"Generated at: `{inventory['generated_at']}`",
        "",
        "## Window",
        "",
        f"- Requested: `{window['start_date']}` to `{window['end_date']}`",
        f"- Trading days: `{trading_days_total}` (`{window['first_trading_day']}` to `{window['last_trading_day']}`)",
        f"- Target universe: `{', '.join(inventory['target_scope']['desired_universe'])}`",
        f"- Sample origin: `{inventory['target_scope']['sample_origin']}`",
        "",
        "## Current Readiness",
        "",
        f"- Status: `{readiness['status']}`",
    ]
    for blocker in readiness["blockers"]:
        lines.append(f"- Blocker: {blocker}")
    for warning in readiness.get("warnings") or []:
        lines.append(f"- Warning: {warning}")
    lines.extend(
        [
            f"- Recommended next step: {readiness['recommended_next_step']}",
            "",
            "## Sample Size Estimate",
            "",
        ]
    )
    for key, value in inventory["sample_estimates"].items():
        lines.append(f"- `{key}`: about `{value}` rows")

    lines.extend(
        [
            "",
            "## Local Signal Artifacts",
            "",
            "| Artifact | In requested window | Notes |",
            "|---|---:|---|",
        ]
    )
    for key in (
        "research_backfill_ai_history",
        "research_backfill_scan_history",
        "current_screener_ai_history",
    ):
        item = local[key]
        note = f"total files {item['total_files']}; years {item['years']}"
        if item.get("shortlist_rows_in_requested_window"):
            note += f"; shortlist rows {item['shortlist_rows_in_requested_window']}"
        lines.append(f"| `{key}` | {item['files_in_requested_window']} | {note} |")

    price = local["research_price_kline_cache"]
    shadow = local["shadow_replay"]
    shadow_signal = local["shadow_signal"]
    lines.extend(
        [
            "",
            "## Local Price Cache",
            "",
            f"- Research price cache files: `{price['files_total']}`",
            f"- Unique cached codes: `{price['unique_codes']}`",
            f"- Range: `{price['earliest_range_start']}` to `{price['latest_range_end']}`",
            f"- Files overlapping requested window: `{price['overlapping_requested_window']}`",
            "",
            "## Shadow Replay Cache",
            "",
            f"- Matching runs: `{shadow['matching_runs']}`",
            f"- Max universe codes in a run: `{shadow['max_universe_codes']}`",
            f"- Price files total: `{shadow['price_files_total']}`",
            f"- Price rows total: `{shadow['price_rows_total']}`",
            f"- Provider counts: `{shadow['provider_counts']}`",
            "",
            "## Shadow Signal Samples",
            "",
            f"- Matching runs: `{shadow_signal['matching_runs']}`",
            f"- Panel rows: `{shadow_signal['panel_rows_total']}`",
            f"- Label rows: `{shadow_signal['label_rows_total']}`",
            f"- Available labels: `{shadow_signal['available_labels_total']}`",
            "",
            "## Prism Data Cache By Dataset",
            "",
            "| Dataset | 2025 window date dirs | Coverage | Latest local date | Latest payload count |",
            "|---|---:|---:|---|---:|",
        ]
    )
    for dataset, item in datasets.items():
        count = int(item["date_dirs_in_requested_window"])
        lines.append(
            f"| `{dataset}` | {count} | {pct(count, trading_days_total)} | "
            f"`{item['latest_date']}` | {item['latest_payload_count']} |"
        )

    panel = local["quant_daily_signal_panel"]
    labels = local["quant_forward_return_labels_hardened"]
    lines.extend(
        [
            "",
            "## Existing Quant Panel/Labels",
            "",
            f"- Daily signal panel rows by year: `{panel['years']}`",
            f"- Hardened forward labels by year: `{labels['years']}`",
            "",
            "## Interpretation",
            "",
        ]
    )
    if readiness["status"] == "local_inputs_present":
        lines.extend(
            [
                "- The 2025 window now has local shadow replay inputs and price-signal samples.",
                "- The samples are usable for research-only calibration, not as production Prism AI replay.",
                "- Keep any current-universe approximation explicitly separate from point-in-time constituent samples.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "- The 2025 window is not locally replay-ready yet.",
                "- The next useful task is a data backfill/replay job, not a Decision Ledger import.",
                "- Keep any current-universe approximation explicitly separate from point-in-time constituent samples.",
                "",
            ]
        )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    inventory = build_inventory(args.start_date, args.end_date)

    output_json = Path(args.output_json).expanduser()
    output_md = Path(args.output_md).expanduser()
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md.write_text(render_markdown(inventory), encoding="utf-8")

    print(json.dumps({
        "status": inventory["readiness"]["status"],
        "trading_days": inventory["requested_window"]["trading_days"],
        "output_json": workspace_relative(output_json),
        "output_md": workspace_relative(output_md),
        "blockers": inventory["readiness"]["blockers"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
