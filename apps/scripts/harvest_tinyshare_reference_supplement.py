#!/usr/bin/env python3
"""Harvest one-day Tinyshare/Tushare reference supplements into raw archives.

This job is intentionally research/display-only. It spends a short-lived
Tinyshare authorization window on company profiles, industry/concept
memberships, main-business composition, margin detail, block trades, Stock
Connect top lists, corporate actions, audit opinions, and research reports.

The script writes faithful raw archives first. Promotion into Prism datasets is
handled separately by promote_tinyshare_reference_data.py.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from calendar import monthrange
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_ROOT = REPO_ROOT / "packages"
if str(PACKAGES_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGES_ROOT))

from prism_data.env import load_project_env  # noqa: E402


load_project_env(root=REPO_ROOT)

TOKEN_ENV_NAMES = (
    "PRISM_TINYSHARE_TOKEN",
    "TINYSHARE_TOKEN",
    "PRISM_TUSHARE_TOKEN",
    "TUSHARE_TOKEN",
)
DEFAULT_UNIVERSE = REPO_ROOT / "data" / "quant" / "shadow_replay" / "20250501_20251231" / "universe" / "merged_current_constituents_approx.json"
DEFAULT_SOURCE_RUN = REPO_ROOT / "data" / "prism_data" / "tinyshare_harvest" / "latest_run.json"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data" / "prism_data" / "tinyshare_reference_supplement"

P0_DATASETS = {
    "company",
    "concept",
    "industry",
    "ths",
    "dc",
    "main_business",
    "margin_detail",
    "block_trade",
}
P1_DATASETS = {
    "hsgt_top10",
    "corporate_actions",
    "audit",
    "report_rc",
}
P2_DATASETS = {"technical"}
MAINBZ_TYPES = ("P", "D", "I")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Harvest Tinyshare/Tushare reference supplement raw archives.")
    parser.add_argument("--start-date", default="2022-01-01")
    parser.add_argument("--end-date", default="2026-05-29")
    parser.add_argument("--recent-trade-days", type=int, default=60)
    parser.add_argument("--report-months", type=int, default=12)
    parser.add_argument("--report-range-days", type=int, default=0, help="Split report_rc windows into N-day ranges; default keeps monthly ranges.")
    parser.add_argument("--report-ranges-file", default="", help="Optional JSON file of explicit [start_date, end_date] ranges for report_rc.")
    parser.add_argument("--mainbz-period-count", type=int, default=8)
    parser.add_argument("--mainbz-periods", default="", help="Comma-separated report periods, e.g. 20260331,20251231.")
    parser.add_argument("--cyq-chips-trade-days-per-call", type=int, default=20)
    parser.add_argument("--skip-cyq-chips", action="store_true", help="For technical runs, harvest stk_factor/cyq_perf only.")
    parser.add_argument("--corporate-range-days", type=int, default=0, help="Also split share_float/repurchase into N-day ranges.")
    parser.add_argument("--universe-file", default=str(DEFAULT_UNIVERSE))
    parser.add_argument("--source-run-json", default=str(DEFAULT_SOURCE_RUN))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--run-dir", default="", help="Existing run directory to resume/write into.")
    parser.add_argument(
        "--datasets",
        default=",".join(sorted(P0_DATASETS | P1_DATASETS)),
        help="Comma-separated groups: company,concept,industry,ths,dc,main_business,margin_detail,block_trade,hsgt_top10,corporate_actions,audit,report_rc,technical.",
    )
    parser.add_argument("--sleep-seconds", type=float, default=0.04)
    parser.add_argument("--checkpoint-every", type=int, default=50)
    parser.add_argument("--limit-codes", type=int, default=0, help="Debug limiter for per-code APIs.")
    parser.add_argument("--refresh-existing", action="store_true")
    return parser.parse_args()


def compact_date(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())[:8]


def dash_date(value: Any) -> str:
    digits = compact_date(value)
    if len(digits) != 8:
        return str(value or "").strip()
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"


def ymd(value: str) -> tuple[int, int, int]:
    digits = compact_date(value)
    return int(digits[:4]), int(digits[4:6]), int(digits[6:8])


def add_months(year: int, month: int, delta: int) -> tuple[int, int]:
    month_index = year * 12 + (month - 1) + delta
    return month_index // 12, month_index % 12 + 1


def report_month_ranges(end: str, months: int) -> list[tuple[str, str]]:
    end_year, end_month, end_day = ymd(end)
    ranges: list[tuple[str, str]] = []
    for offset in range(max(months, 0) - 1, -1, -1):
        year, month = add_months(end_year, end_month, -offset)
        last_day = monthrange(year, month)[1]
        range_end_day = min(end_day, last_day) if year == end_year and month == end_month else last_day
        ranges.append((f"{year:04d}{month:02d}01", f"{year:04d}{month:02d}{range_end_day:02d}"))
    return ranges


def report_day_ranges(end: str, months: int, days: int) -> list[tuple[str, str]]:
    monthly = report_month_ranges(end, months)
    if not monthly or days <= 0:
        return monthly
    start = datetime.strptime(monthly[0][0], "%Y%m%d").date()
    stop = datetime.strptime(monthly[-1][1], "%Y%m%d").date()
    ranges: list[tuple[str, str]] = []
    current = start
    step = max(days, 1)
    while current <= stop:
        range_end = min(current + timedelta(days=step - 1), stop)
        ranges.append((current.strftime("%Y%m%d"), range_end.strftime("%Y%m%d")))
        current = range_end + timedelta(days=1)
    return ranges


def explicit_ranges(path: str) -> list[tuple[str, str]]:
    if not path.strip():
        return []
    rows = read_json(resolve_path(path))
    ranges: list[tuple[str, str]] = []
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict):
            start = compact_date(row.get("start_date") or row.get("start"))
            end = compact_date(row.get("end_date") or row.get("end"))
        elif isinstance(row, (list, tuple)) and len(row) >= 2:
            start = compact_date(row[0])
            end = compact_date(row[1])
        else:
            continue
        if len(start) == 8 and len(end) == 8 and start <= end:
            ranges.append((start, end))
    return ranges


def date_day_ranges(start_value: str, end_value: str, days: int) -> list[tuple[str, str]]:
    start = datetime.strptime(compact_date(start_value), "%Y%m%d").date()
    stop = datetime.strptime(compact_date(end_value), "%Y%m%d").date()
    if days <= 0 or start > stop:
        return []
    ranges: list[tuple[str, str]] = []
    current = start
    step = max(days, 1)
    while current <= stop:
        range_end = min(current + timedelta(days=step - 1), stop)
        ranges.append((current.strftime("%Y%m%d"), range_end.strftime("%Y%m%d")))
        current = range_end + timedelta(days=1)
    return ranges


def quarter_periods(end: str, count: int) -> list[str]:
    end_digits = compact_date(end)
    end_year, _, _ = ymd(end_digits)
    periods: list[str] = []
    for year in range(end_year, end_year - 5, -1):
        for suffix in ("1231", "0930", "0630", "0331"):
            period = f"{year}{suffix}"
            if period <= end_digits:
                periods.append(period)
            if len(periods) >= count:
                return periods
    return periods


def chunks(values: list[str], size: int) -> list[list[str]]:
    width = max(size, 1)
    return [values[offset : offset + width] for offset in range(0, len(values), width)]


def resolve_path(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path)


def resolve_token() -> tuple[str, str]:
    load_project_env(root=REPO_ROOT)
    for name in TOKEN_ENV_NAMES:
        value = os.environ.get(name, "").strip()
        if value:
            return value, name
    return "", ""


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if hasattr(value, "item"):
        try:
            return json_safe(value.item())
        except Exception:
            pass
    try:
        import pandas as pd  # type: ignore

        if pd.isna(value):
            return None
    except Exception:
        pass
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return str(value)


def records_from_frame(frame: Any) -> list[dict[str, Any]]:
    if frame is None:
        return []
    if isinstance(frame, list):
        return [dict(json_safe(item)) for item in frame if isinstance(item, dict)]
    if hasattr(frame, "to_dict"):
        return [dict(json_safe(item)) for item in frame.to_dict(orient="records") if isinstance(item, dict)]
    if isinstance(frame, dict):
        data = frame.get("data") if "data" in frame else frame
        if isinstance(data, list):
            return [dict(json_safe(item)) for item in data if isinstance(item, dict)]
    return []


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned = json_safe(payload)
    path.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def event(log_path: Path, name: str, **payload: Any) -> None:
    row = {"at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "event": name, **json_safe(payload)}
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")


def exchange_for_digits(code: str) -> str:
    return "SH" if code.startswith(("5", "6", "9")) else "BJ" if code.startswith(("4", "8")) else "SZ"


def ts_code_for_digits(code: str) -> str:
    return f"{code}.{exchange_for_digits(code)}"


def load_universe(path: Path) -> tuple[list[str], dict[str, Any]]:
    rows = read_json(path)
    codes: dict[str, str] = {}
    pool_counts: dict[str, int] = {}
    for item in rows if isinstance(rows, list) else []:
        if not isinstance(item, dict):
            continue
        code = "".join(ch for ch in str(item.get("code") or item.get("symbol") or "") if ch.isdigit()).zfill(6)
        if len(code) != 6:
            continue
        ts_code = ts_code_for_digits(code)
        codes[ts_code] = code
        pool = str(item.get("source_pool") or "").strip() or "+".join(str(x) for x in item.get("source_pools") or [])
        pool_counts[pool] = pool_counts.get(pool, 0) + 1
    return sorted(codes), {"pool_counts": pool_counts, "source_path": str(path)}


def load_trade_days(source_run_json: Path, start: str, end: str, recent: int) -> list[str]:
    latest = read_json(source_run_json)
    run_dir = resolve_path(str(latest["run_dir"]))
    calendar_dir = run_dir / "raw" / "trade_calendar"
    calendar_path = calendar_dir / f"{compact_date(start)}_{compact_date(end)}_all.json"
    if not calendar_path.exists():
        candidates = sorted(calendar_dir.glob("*_all.json"))
        covering: list[Path] = []
        for candidate in candidates:
            parts = candidate.stem.split("_")
            if len(parts) >= 3 and parts[0] <= compact_date(start) and parts[1] >= compact_date(end):
                covering.append(candidate)
        if covering:
            calendar_path = covering[-1]
        elif candidates:
            calendar_path = candidates[-1]
    rows = read_json(calendar_path)
    days = [
        compact_date(row.get("cal_date"))
        for row in rows
        if isinstance(row, dict) and str(row.get("is_open") or "") == "1" and compact_date(row.get("cal_date"))
    ]
    days = sorted({day for day in days if compact_date(start) <= day <= compact_date(end)})
    if recent > 0:
        return days[-recent:]
    return days


def sanitize_filename(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "default"
    return "".join(ch if ch.isalnum() or ch in {"-", "_", ".", "+"} else "_" for ch in text)


def main() -> int:
    args = parse_args()
    start = compact_date(args.start_date)
    end = compact_date(args.end_date)
    datasets = {item.strip() for item in args.datasets.split(",") if item.strip()}
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = resolve_path(args.run_dir).expanduser() if args.run_dir else Path(args.output_root) / f"{start}_{end}_{run_id}"
    if args.run_dir:
        run_id = run_dir.name
    raw_dir = run_dir / "raw"
    log_path = run_dir / "events.jsonl"
    report_path = run_dir / "report.json"
    latest_path = Path(args.output_root) / "latest_run.json"
    run_dir.mkdir(parents=True, exist_ok=True)
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(latest_path, {"run_dir": str(run_dir.resolve()), "report_path": str(report_path.resolve()), "log_path": str(log_path.resolve())})

    token, token_env_name = resolve_token()
    if not token:
        raise SystemExit("Tinyshare/Tushare token is not configured")

    import tinyshare as ts  # type: ignore

    ts.set_token(token)
    pro = ts.pro_api()
    universe, universe_meta = load_universe(resolve_path(args.universe_file))
    if args.limit_codes > 0:
        universe = universe[: args.limit_codes]
    universe_set = set(universe)
    trade_days = load_trade_days(resolve_path(args.source_run_json), start, end, max(args.recent_trade_days, 0))
    mainbz_periods = [compact_date(item) for item in args.mainbz_periods.split(",") if compact_date(item)] or quarter_periods(end, max(args.mainbz_period_count, 0))
    report_ranges = explicit_ranges(args.report_ranges_file) or report_day_ranges(end, max(args.report_months, 0), max(args.report_range_days, 0))

    resume_existing_report = bool(args.run_dir and report_path.exists() and not args.refresh_existing)
    if resume_existing_report:
        loaded = read_json(report_path)
        summary = loaded if isinstance(loaded, dict) else {}
        summary["ok"] = False
        summary["run_id"] = run_id
        summary["start_date"] = start
        summary["end_date"] = end
        summary["recent_trade_days"] = len(trade_days)
        summary["trade_date"] = dash_date(trade_days[-1] if trade_days else end)
        summary["universe_count"] = len(universe)
        summary["universe_meta"] = universe_meta
        summary["datasets"] = sorted(set(summary.get("datasets") or []) | datasets)
        summary["mainbz_periods"] = mainbz_periods
        summary["report_ranges"] = report_ranges
        summary["token_env_name"] = token_env_name
        summary["token_value_visible"] = False
        summary["raw_dir"] = str(raw_dir.resolve())
        summary.setdefault("events", {})
        summary.setdefault("api_rows", {})
        summary.setdefault("api_files", {})
        summary.setdefault("api_skipped_files", {})
        summary.setdefault("errors", [])
        summary["resumed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        event(log_path, "resume", datasets=sorted(datasets), summary_keys=sorted(summary))
    else:
        summary: dict[str, Any] = {
            "ok": False,
            "run_id": run_id,
            "start_date": start,
            "end_date": end,
            "recent_trade_days": len(trade_days),
            "trade_date": dash_date(trade_days[-1] if trade_days else end),
            "universe_count": len(universe),
            "universe_meta": universe_meta,
            "datasets": sorted(datasets),
            "mainbz_periods": mainbz_periods,
            "report_ranges": report_ranges,
            "token_env_name": token_env_name,
            "token_value_visible": False,
            "raw_dir": str(raw_dir.resolve()),
            "events": {},
            "api_rows": {},
            "api_files": {},
            "api_skipped_files": {},
            "errors": [],
        }
        event(log_path, "start", summary=summary)
    write_json(report_path, summary)

    calls = 0

    def checkpoint() -> None:
        if args.checkpoint_every <= 0 or calls % args.checkpoint_every == 0:
            write_json(report_path, summary)

    def record(api: str, rows: int, *, skipped: bool) -> None:
        if skipped:
            summary["api_skipped_files"][api] = int(summary["api_skipped_files"].get(api, 0)) + 1
            return
        summary["api_rows"][api] = int(summary["api_rows"].get(api, 0)) + rows
        summary["api_files"][api] = int(summary["api_files"].get(api, 0)) + 1

    def filter_universe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        filtered: list[dict[str, Any]] = []
        for row in rows:
            ts_code = str(row.get("ts_code") or row.get("con_code") or "").strip().upper()
            if ts_code in universe_set:
                filtered.append(row)
        return filtered

    def call(api: str, params: dict[str, Any], output_path: Path, *, postprocess: Callable[[list[dict[str, Any]]], list[dict[str, Any]]] | None = None) -> list[dict[str, Any]]:
        nonlocal calls
        calls += 1
        if output_path.exists() and not args.refresh_existing:
            rows = read_json(output_path)
            rows = rows if isinstance(rows, list) else []
            record(api, len(rows), skipped=True)
            event(log_path, "skip_existing", api=api, path=str(output_path), rows=len(rows))
            checkpoint()
            return rows
        frame = getattr(pro, api)(**params)
        rows = records_from_frame(frame)
        if postprocess:
            rows = postprocess(rows)
        write_json(output_path, rows)
        record(api, len(rows), skipped=False)
        event(log_path, "api_call", api=api, params=params, path=str(output_path), rows=len(rows))
        if len(rows) in {3000, 5000, 6000, 10000}:
            event(log_path, "possible_limit_hit", api=api, params=params, rows=len(rows))
        time.sleep(max(args.sleep_seconds, 0.0))
        checkpoint()
        return rows

    def safe_call(api: str, params: dict[str, Any], output_path: Path, *, postprocess: Callable[[list[dict[str, Any]]], list[dict[str, Any]]] | None = None) -> list[dict[str, Any]]:
        try:
            return call(api, params, output_path, postprocess=postprocess)
        except Exception as exc:  # noqa: BLE001
            error = {"api": api, "params": params, "path": str(output_path), "error": str(exc)}
            summary["errors"].append(error)
            event(log_path, "error", **error)
            checkpoint()
            return []

    def safe_call_with_fallback(api: str, variants: list[tuple[dict[str, Any], Path]]) -> list[dict[str, Any]]:
        last_error = ""
        for params, output_path in variants:
            try:
                return call(api, params, output_path)
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                event(log_path, "fallback_error", api=api, params=params, path=str(output_path), error=last_error)
        error = {"api": api, "params": variants[-1][0] if variants else {}, "path": str(variants[-1][1]) if variants else "", "error": last_error}
        summary["errors"].append(error)
        event(log_path, "error", **error)
        checkpoint()
        return []

    if "company" in datasets:
        for exchange in ("SSE", "SZSE", "BSE"):
            safe_call("stock_company", {"exchange": exchange}, raw_dir / "stock_company" / f"{exchange}.json")
        safe_call("namechange", {}, raw_dir / "namechange" / "all.json")
        write_json(report_path, summary)

    if "concept" in datasets:
        safe_call("concept", {}, raw_dir / "concept" / "all.json")
        for offset, ts_code in enumerate(universe, 1):
            safe_call("concept_detail", {"ts_code": ts_code}, raw_dir / "concept_detail" / f"{ts_code}.json")
            if offset % max(args.checkpoint_every, 1) == 0:
                event(log_path, "progress", group="concept_detail", completed=offset, total=len(universe))
        write_json(report_path, summary)

    industry_index_codes: list[str] = []
    if "industry" in datasets:
        for level in ("L1", "L2", "L3"):
            rows = safe_call("index_classify", {"src": "SW2021", "level": level}, raw_dir / "index_classify" / f"SW2021_{level}.json")
            for row in rows:
                index_code = str(row.get("index_code") or row.get("ts_code") or "").strip().upper()
                if index_code:
                    industry_index_codes.append(index_code)
        for offset, index_code in enumerate(sorted(set(industry_index_codes)), 1):
            safe_call(
                "index_member",
                {"index_code": index_code, "is_new": "Y"},
                raw_dir / "index_member" / f"SW2021_{sanitize_filename(index_code)}.json",
            )
            if offset % max(args.checkpoint_every, 1) == 0:
                event(log_path, "progress", group="index_member", completed=offset, total=len(set(industry_index_codes)))
        write_json(report_path, summary)

    if "ths" in datasets:
        safe_call("ths_index", {}, raw_dir / "ths_index" / "all.json")
        for offset, ts_code in enumerate(universe, 1):
            safe_call("ths_member", {"con_code": ts_code, "is_new": "Y"}, raw_dir / "ths_member" / f"{ts_code}.json")
            if offset % max(args.checkpoint_every, 1) == 0:
                event(log_path, "progress", group="ths_member", completed=offset, total=len(universe))
        write_json(report_path, summary)

    if "dc" in datasets:
        safe_call("dc_index", {}, raw_dir / "dc_index" / "all.json")
        for offset, ts_code in enumerate(universe, 1):
            safe_call("dc_member", {"con_code": ts_code}, raw_dir / "dc_member" / f"{ts_code}.json")
            if offset % max(args.checkpoint_every, 1) == 0:
                event(log_path, "progress", group="dc_member", completed=offset, total=len(universe))
        write_json(report_path, summary)

    if "main_business" in datasets:
        for period in mainbz_periods:
            for business_type in MAINBZ_TYPES:
                output_path = raw_dir / "fina_mainbz" / f"{period}_{business_type}.json"
                rows = safe_call(
                    "fina_mainbz",
                    {"period": period, "type": business_type},
                    output_path,
                )
                if not rows and business_type == "I" and not output_path.exists():
                    for offset, ts_code in enumerate(universe, 1):
                        safe_call(
                            "fina_mainbz",
                            {"ts_code": ts_code, "period": period, "type": business_type},
                            raw_dir / "fina_mainbz" / f"{period}_{business_type}_{ts_code}.json",
                        )
                        if offset % max(args.checkpoint_every, 1) == 0:
                            event(log_path, "progress", group="fina_mainbz_by_code", period=period, completed=offset, total=len(universe))
        write_json(report_path, summary)

    if "margin_detail" in datasets:
        for day in trade_days:
            safe_call("margin_detail", {"trade_date": day}, raw_dir / "margin_detail" / f"{day}_all.json")
            safe_call("margin_secs", {"trade_date": day}, raw_dir / "margin_secs" / f"{day}_all.json")
        write_json(report_path, summary)

    if "block_trade" in datasets:
        for day in trade_days:
            safe_call("block_trade", {"trade_date": day}, raw_dir / "block_trade" / f"{day}_all.json")
        write_json(report_path, summary)

    if "hsgt_top10" in datasets:
        for day in trade_days:
            for market_type in ("1", "3"):
                safe_call("hsgt_top10", {"trade_date": day, "market_type": market_type}, raw_dir / "hsgt_top10" / f"{day}_{market_type}.json")
            for market_type in ("2", "4"):
                safe_call("ggt_top10", {"trade_date": day, "market_type": market_type}, raw_dir / "ggt_top10" / f"{day}_{market_type}.json")
        write_json(report_path, summary)

    if "corporate_actions" in datasets:
        safe_call("pledge_stat", {}, raw_dir / "pledge_stat" / "all.json")
        safe_call("pledge_detail", {}, raw_dir / "pledge_detail" / "all.json")
        safe_call_with_fallback(
            "share_float",
            [
                ({"start_date": start, "end_date": end}, raw_dir / "share_float" / f"{start}_{end}.json"),
                ({}, raw_dir / "share_float" / "all.json"),
            ],
        )
        safe_call_with_fallback(
            "repurchase",
            [
                ({"start_date": start, "end_date": end}, raw_dir / "repurchase" / f"{start}_{end}.json"),
                ({}, raw_dir / "repurchase" / "all.json"),
            ],
        )
        for range_start, range_end in date_day_ranges(start, end, max(args.corporate_range_days, 0)):
            safe_call("share_float", {"start_date": range_start, "end_date": range_end}, raw_dir / "share_float" / f"{range_start}_{range_end}.json")
            safe_call("repurchase", {"start_date": range_start, "end_date": range_end}, raw_dir / "repurchase" / f"{range_start}_{range_end}.json")
        write_json(report_path, summary)

    if "audit" in datasets:
        for offset, ts_code in enumerate(universe, 1):
            safe_call("fina_audit", {"ts_code": ts_code}, raw_dir / "fina_audit" / f"{ts_code}.json")
            if offset % max(args.checkpoint_every, 1) == 0:
                event(log_path, "progress", group="fina_audit", completed=offset, total=len(universe))
        write_json(report_path, summary)

    if "report_rc" in datasets:
        for range_start, range_end in report_ranges:
            safe_call("report_rc", {"start_date": range_start, "end_date": range_end}, raw_dir / "report_rc" / f"{range_start}_{range_end}_all.json")
        write_json(report_path, summary)

    if "technical" in datasets:
        technical_start = trade_days[0] if trade_days else start
        for day in trade_days:
            safe_call("stk_factor", {"trade_date": day}, raw_dir / "stk_factor" / f"{day}_all.json", postprocess=filter_universe_rows)
            safe_call("cyq_perf", {"trade_date": day}, raw_dir / "cyq_perf" / f"{day}_all.json", postprocess=filter_universe_rows)
        if not args.skip_cyq_chips:
            chip_ranges = chunks(trade_days, max(args.cyq_chips_trade_days_per_call, 1)) if trade_days else [[technical_start, end]]
            for offset, ts_code in enumerate(universe, 1):
                for chip_range in chip_ranges:
                    range_start = chip_range[0]
                    range_end = chip_range[-1]
                    safe_call(
                        "cyq_chips",
                        {"ts_code": ts_code, "start_date": range_start, "end_date": range_end},
                        raw_dir / "cyq_chips" / f"{ts_code}_{range_start}_{range_end}.json",
                    )
                if offset % max(args.checkpoint_every, 1) == 0:
                    event(log_path, "progress", group="technical", completed=offset, total=len(universe))
        write_json(report_path, summary)

    summary["ok"] = True
    summary["calls"] = calls
    summary["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    write_json(report_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
