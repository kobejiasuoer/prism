#!/usr/bin/env python3
"""One-off Tinyshare research-data supplement harvest.

This script deliberately writes raw archives, not formal-decision manifests.
The formal gate is covered by harvest_tinyshare_universe_overnight.py; this
job spends the short-lived Tinyshare authorization window on high-value
research data that Prism can integrate later.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


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
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data" / "prism_data" / "tinyshare_research_harvest"

CROSS_SECTION_APIS = ("daily_basic", "moneyflow", "limit_list_d")
CODE_APIS = (
    "fina_indicator",
    "income",
    "balancesheet",
    "cashflow",
    "express",
    "forecast",
    "dividend",
    "top10_holders",
    "top10_floatholders",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Harvest supplemental Tinyshare research datasets.")
    parser.add_argument("--start-date", default="2022-01-01")
    parser.add_argument("--end-date", default="2026-05-29")
    parser.add_argument("--universe-file", default=str(DEFAULT_UNIVERSE))
    parser.add_argument("--source-run-json", default=str(DEFAULT_SOURCE_RUN))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--run-dir", default="", help="Existing run directory to resume/write into.")
    parser.add_argument("--datasets", default="stock_basic,cross_section,code_financials,stock_st")
    parser.add_argument("--sleep-seconds", type=float, default=0.03)
    parser.add_argument("--checkpoint-every", type=int, default=25)
    parser.add_argument("--code-shards", type=int, default=1, help="Number of stock-code shards for code_financials.")
    parser.add_argument("--code-shard-index", type=int, default=0, help="Zero-based stock-code shard index.")
    parser.add_argument("--refresh-existing", action="store_true")
    return parser.parse_args()


def compact_date(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())[:8]


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
    if value is None or isinstance(value, (str, bool, int, float)):
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
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_universe(path: Path) -> tuple[list[str], dict[str, Any]]:
    rows = read_json(path)
    codes: dict[str, str] = {}
    pool_counts: dict[str, int] = {}
    for item in rows if isinstance(rows, list) else []:
        code = "".join(ch for ch in str(item.get("code") or "") if ch.isdigit()).zfill(6)
        if len(code) != 6:
            continue
        ts_code = f"{code}.{'SH' if code.startswith(('5', '6', '9')) else 'BJ' if code.startswith(('4', '8')) else 'SZ'}"
        codes[ts_code] = code
        pool = str(item.get("source_pool") or "").strip() or "+".join(str(x) for x in item.get("source_pools") or [])
        pool_counts[pool] = pool_counts.get(pool, 0) + 1
    return sorted(codes), {"pool_counts": pool_counts, "source_path": str(path)}


def load_trade_days(source_run_json: Path, start: str, end: str) -> list[str]:
    latest = read_json(source_run_json)
    run_dir = Path(latest["run_dir"])
    calendar_dir = run_dir / "raw" / "trade_calendar"
    calendar_path = calendar_dir / f"{compact_date(start)}_{compact_date(end)}_all.json"
    if not calendar_path.exists():
        candidates = sorted(calendar_dir.glob("*_all.json"))
        covering: list[Path] = []
        for candidate in candidates:
            parts = candidate.stem.split("_")
            if len(parts) >= 3 and parts[0] <= start and parts[1] >= end:
                covering.append(candidate)
        if covering:
            calendar_path = covering[-1]
        elif candidates:
            calendar_path = candidates[-1]
    rows = read_json(calendar_path)
    days = [
        compact_date(row.get("cal_date"))
        for row in rows
        if str(row.get("is_open") or "") == "1" and compact_date(row.get("cal_date"))
    ]
    return [day for day in days if compact_date(start) <= day <= compact_date(end)]


def event(log_path: Path, name: str, **payload: Any) -> None:
    row = {"at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "event": name, **payload}
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    args = parse_args()
    start = compact_date(args.start_date)
    end = compact_date(args.end_date)
    datasets = {item.strip() for item in args.datasets.split(",") if item.strip()}
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.run_dir).expanduser() if args.run_dir else Path(args.output_root) / f"{start}_{end}_{run_id}"
    if args.run_dir:
        run_id = run_dir.name
    raw_dir = run_dir / "raw"
    log_path = run_dir / "events.jsonl"
    report_path = run_dir / "report.json"
    latest_path = Path(args.output_root) / "latest_run.json"
    run_dir.mkdir(parents=True, exist_ok=True)
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(latest_path, {"run_dir": str(run_dir), "report_path": str(report_path), "log_path": str(log_path)})

    token, token_env_name = resolve_token()
    if not token:
        raise SystemExit("Tinyshare/Tushare token is not configured")

    import tinyshare as ts  # type: ignore

    ts.set_token(token)
    pro = ts.pro_api()
    universe, universe_meta = load_universe(Path(args.universe_file))
    if args.code_shards > 1:
        shard_count = max(args.code_shards, 1)
        shard_index = min(max(args.code_shard_index, 0), shard_count - 1)
        code_universe = [code for offset, code in enumerate(universe) if offset % shard_count == shard_index]
    else:
        shard_count = 1
        shard_index = 0
        code_universe = list(universe)
    universe_set = set(universe)
    trade_days = load_trade_days(Path(args.source_run_json), start, end)
    summary: dict[str, Any] = {
        "ok": False,
        "run_id": run_id,
        "start_date": start,
        "end_date": end,
        "universe_count": len(universe),
        "universe_meta": universe_meta,
        "code_financials_shard": {
            "index": shard_index,
            "count": shard_count,
            "codes": len(code_universe),
        },
        "trade_days": len(trade_days),
        "datasets": sorted(datasets),
        "token_env_name": token_env_name,
        "token_value_visible": False,
        "raw_dir": str(raw_dir),
        "events": {},
        "errors": [],
    }
    event(log_path, "start", summary=summary)

    def call(api: str, params: dict[str, Any], output_path: Path, *, filter_universe: bool = False) -> list[dict[str, Any]]:
        if output_path.exists() and not args.refresh_existing:
            rows = read_json(output_path)
            return rows if isinstance(rows, list) else []
        frame = getattr(pro, api)(**params)
        rows = records_from_frame(frame)
        if filter_universe:
            rows = [row for row in rows if str(row.get("ts_code") or "").strip().upper() in universe_set]
        write_json(output_path, rows)
        time.sleep(max(args.sleep_seconds, 0.0))
        return rows

    try:
        if "stock_basic" in datasets:
            rows = call(
                "stock_basic",
                {"exchange": "", "list_status": "L", "fields": "ts_code,symbol,name,area,industry,market,list_date"},
                raw_dir / "stock_basic" / "listed_all.json",
            )
            universe_rows = [row for row in rows if str(row.get("ts_code") or "").strip().upper() in universe_set]
            write_json(raw_dir / "stock_basic" / "universe_hs300_zz500.json", universe_rows)
            summary["events"]["stock_basic_rows"] = len(rows)
            summary["events"]["stock_basic_universe_rows"] = len(universe_rows)
            event(log_path, "stock_basic", rows=len(rows), universe_rows=len(universe_rows))

        if "stock_st" in datasets:
            rows = call(
                "stock_st",
                {"start_date": start, "end_date": end},
                raw_dir / "stock_st" / f"{start}_{end}_all.json",
                filter_universe=True,
            )
            summary["events"]["stock_st_universe_rows"] = len(rows)
            event(log_path, "stock_st", rows=len(rows))

        if "cross_section" in datasets:
            for index, day in enumerate(trade_days, start=1):
                for api in CROSS_SECTION_APIS:
                    try:
                        rows = call(api, {"trade_date": day}, raw_dir / api / f"{day}_universe.json", filter_universe=True)
                        summary["events"][f"{api}_rows"] = int(summary["events"].get(f"{api}_rows", 0)) + len(rows)
                        event(log_path, api, date=day, rows=len(rows))
                    except Exception as exc:  # noqa: BLE001
                        error = {"api": api, "date": day, "error": str(exc)}
                        summary["errors"].append(error)
                        event(log_path, "error", **error)
                if index % max(args.checkpoint_every, 1) == 0:
                    write_json(report_path, summary)

        if "code_financials" in datasets:
            for index, ts_code in enumerate(code_universe, start=1):
                for api in CODE_APIS:
                    params: dict[str, Any] = {"ts_code": ts_code}
                    if api != "dividend":
                        params.update({"start_date": start, "end_date": end})
                    try:
                        rows = call(api, params, raw_dir / api / f"{ts_code}.json")
                        summary["events"][f"{api}_rows"] = int(summary["events"].get(f"{api}_rows", 0)) + len(rows)
                        event(log_path, api, ts_code=ts_code, rows=len(rows))
                    except Exception as exc:  # noqa: BLE001
                        error = {"api": api, "ts_code": ts_code, "error": str(exc)}
                        summary["errors"].append(error)
                        event(log_path, "error", **error)
                if index % max(args.checkpoint_every, 1) == 0:
                    summary["events"]["code_financials_done"] = index
                    write_json(report_path, summary)

        summary["ok"] = True
        summary["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        write_json(report_path, summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except KeyboardInterrupt:
        summary["errors"].append({"error": "interrupted"})
        write_json(report_path, summary)
        raise
    except Exception as exc:  # noqa: BLE001
        summary["errors"].append({"error": str(exc)})
        write_json(report_path, summary)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
