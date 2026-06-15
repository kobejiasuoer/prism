#!/usr/bin/env python3
"""Overnight Tinyshare harvest for a broad HS300 + CSI500 universe."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_ROOT = REPO_ROOT / "packages"
CONTROL_PANEL_ROOT = REPO_ROOT / "apps" / "control-panel"
for path in (PACKAGES_ROOT, CONTROL_PANEL_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from prism_data.contracts import DatasetStatus, ProviderRole, ProviderResult  # noqa: E402
from prism_data.env import load_project_env  # noqa: E402
from prism_data.manifest import manifest_from_provider_result  # noqa: E402
from prism_data.repositories import DatasetRepository  # noqa: E402
from prism_data.utils import default_dataset_repository_root, hash_payload  # noqa: E402
from prism_data.providers.tushare import _dash_date, _float_or_none, _prism_stock_code  # noqa: E402


load_project_env(root=REPO_ROOT)

TOKEN_ENV_NAMES = (
    "PRISM_TINYSHARE_TOKEN",
    "TINYSHARE_TOKEN",
    "PRISM_TUSHARE_TOKEN",
    "TUSHARE_TOKEN",
)
DEFAULT_UNIVERSE = REPO_ROOT / "data" / "quant" / "shadow_replay" / "20250501_20251231" / "universe" / "merged_current_constituents_approx.json"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data" / "prism_data" / "tinyshare_harvest"
TINYSHARE_ENDPOINT = "tinyshare://pro_api"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Harvest Tinyshare cross-section data for HS300 + CSI500 overnight.")
    parser.add_argument("--trade-date", default="2026-05-29")
    parser.add_argument("--start-date", default="", help="History start date; defaults to --days lookback.")
    parser.add_argument("--days", type=int, default=730, help="Calendar days to walk when --start-date is omitted.")
    parser.add_argument("--universe-file", default=str(DEFAULT_UNIVERSE))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--datasets", default="daily,adj_factor,price_limit,execution_flags,index_daily")
    parser.add_argument("--indexes", default="000300.SH,000905.SH")
    parser.add_argument("--sleep-seconds", type=float, default=0.15)
    parser.add_argument("--checkpoint-every", type=int, default=10)
    parser.add_argument("--refresh-existing", action="store_true")
    parser.add_argument("--persist-prism", action="store_true", default=True)
    parser.add_argument("--no-persist-prism", action="store_false", dest="persist_prism")
    return parser.parse_args()


def compact_date(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())[:8]


def dash_date(value: str) -> str:
    return _dash_date(value)


def date_range(start: str, end: str) -> list[str]:
    start_dt = datetime.strptime(compact_date(start), "%Y%m%d")
    end_dt = datetime.strptime(compact_date(end), "%Y%m%d")
    out: list[str] = []
    current = start_dt
    while current <= end_dt:
        out.append(current.strftime("%Y%m%d"))
        current += timedelta(days=1)
    return out


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
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
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


def load_universe(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    universe: dict[str, dict[str, Any]] = {}
    pool_counts: dict[str, int] = {}
    for item in rows if isinstance(rows, list) else []:
        code = "".join(ch for ch in str(item.get("code") or "") if ch.isdigit()).zfill(6)
        if len(code) != 6:
            continue
        row = dict(item)
        row["code"] = code
        universe[code] = row
        pool = str(row.get("source_pool") or "").strip() or "+".join(str(x) for x in row.get("source_pools") or [])
        pool_counts[pool] = pool_counts.get(pool, 0) + 1
    return [universe[key] for key in sorted(universe)], {"pool_counts": pool_counts, "source_path": str(path)}


def stock_ts_code(code: str) -> str:
    return f"{code}.{'SH' if code.startswith(('5', '6', '9')) else 'BJ' if code.startswith(('4', '8')) else 'SZ'}"


def raw_path(raw_dir: Path, dataset: str, date: str, key: str = "all") -> Path:
    return raw_dir / dataset / f"{date}_{key}.json"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_daily(rows: list[dict[str, Any]], universe_set: set[str]) -> dict[str, list[dict[str, Any]]]:
    by_code: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        ts_code = str(row.get("ts_code") or "").strip().upper()
        if ts_code not in universe_set:
            continue
        trade_date = dash_date(row.get("trade_date"))
        item = {
            "code": _prism_stock_code(ts_code),
            "ts_code": ts_code,
            "trade_date": trade_date,
            "day": trade_date,
            "open": _float_or_none(row.get("open")),
            "high": _float_or_none(row.get("high")),
            "low": _float_or_none(row.get("low")),
            "close": _float_or_none(row.get("close")),
            "pre_close": _float_or_none(row.get("pre_close")),
            "change": _float_or_none(row.get("change")),
            "pct_chg": _float_or_none(row.get("pct_chg")),
            "volume": _float_or_none(row.get("vol")),
            "amount": _float_or_none(row.get("amount")),
        }
        if trade_date:
            by_code.setdefault(ts_code, []).append(item)
    for items in by_code.values():
        items.sort(key=lambda item: str(item.get("trade_date") or ""))
    return by_code


def normalize_adj(rows: list[dict[str, Any]], universe_set: set[str]) -> dict[str, list[dict[str, Any]]]:
    by_code: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        ts_code = str(row.get("ts_code") or "").strip().upper()
        if ts_code not in universe_set:
            continue
        trade_date = dash_date(row.get("trade_date"))
        item = {
            "code": _prism_stock_code(ts_code),
            "ts_code": ts_code,
            "trade_date": trade_date,
            "adj_factor": _float_or_none(row.get("adj_factor")),
        }
        if trade_date:
            by_code.setdefault(ts_code, []).append(item)
    for items in by_code.values():
        items.sort(key=lambda item: str(item.get("trade_date") or ""))
    return by_code


def save_manifest_dataset(
    repository: DatasetRepository,
    *,
    dataset: str,
    trade_date: str,
    key: str,
    rows: list[dict[str, Any]],
    source_api: str,
    params: dict[str, Any],
    live_small_allowed: bool = True,
    quality_flags: list[str] | None = None,
) -> dict[str, Any]:
    result = ProviderResult(
        status=DatasetStatus.OK,
        data=rows,
        provider="tushare",
        provider_role=ProviderRole.PRIMARY,
        dataset=dataset,
        trade_date=trade_date,
        fetched_at=datetime.now(),
        ttl_seconds=86400,
        source_endpoint=TINYSHARE_ENDPOINT,
        params_hash=hash_payload({"source_api": source_api, "params": params, "source_proxy": "tinyshare"}),
        payload_hash=hash_payload(rows),
        row_count=len(rows),
        quality_flags=list(quality_flags or []),
        license_scope="authorized_tinyshare_proxy",
        live_small_allowed=live_small_allowed,
        request_key=key,
        extra={
            "source_api": source_api,
            "source_proxy": "tinyshare",
            "authority_provider_override": "tushare",
        },
    )
    manifest = manifest_from_provider_result(
        result,
        expected_trade_date=trade_date,
        live_small_allowed=live_small_allowed,
    )
    data_path, manifest_path = repository.save_dataset(dataset, trade_date, key, rows, manifest)
    manifest["data_path"] = str(data_path.resolve())
    manifest["manifest_path"] = str(manifest_path.resolve())
    return manifest


def append_log(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), **event}, ensure_ascii=False) + "\n")


def main() -> int:
    args = parse_args()
    trade_date = dash_date(args.trade_date)
    end = compact_date(trade_date)
    if args.start_date.strip():
        start = compact_date(args.start_date)
    else:
        end_dt = datetime.strptime(end, "%Y%m%d")
        start = (end_dt - timedelta(days=max(args.days, 1))).strftime("%Y%m%d")
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_root = Path(args.output_root)
    run_dir = output_root / f"{start}_{end}_{run_id}"
    raw_dir = run_dir / "raw"
    report_path = run_dir / "report.json"
    log_path = run_dir / "events.jsonl"
    latest_path = output_root / "latest_run.json"

    universe, universe_meta = load_universe(Path(args.universe_file))
    universe_ts_codes = {stock_ts_code(str(item["code"])) for item in universe}
    datasets = {item.strip() for item in args.datasets.split(",") if item.strip()}
    token, token_env_name = resolve_token()
    if not token:
        raise SystemExit("Tinyshare authorization code missing.")
    import tinyshare as ts  # type: ignore

    ts.set_token(token)
    pro = ts.pro_api()
    repository = DatasetRepository(default_dataset_repository_root())
    summary: dict[str, Any] = {
        "ok": False,
        "run_id": run_id,
        "trade_date": trade_date,
        "start_date": dash_date(start),
        "end_date": trade_date,
        "universe_count": len(universe),
        "universe_meta": universe_meta,
        "token_env_name": token_env_name,
        "token_value_visible": False,
        "datasets": sorted(datasets),
        "raw_dir": str(raw_dir),
        "log_path": str(log_path),
        "events": {},
        "errors": [],
    }
    write_json(latest_path, {"run_dir": str(run_dir), "report_path": str(report_path), "log_path": str(log_path)})
    append_log(log_path, {"event": "start", "summary": summary})

    def call_api(api: str, params: dict[str, Any], path: Path) -> list[dict[str, Any]]:
        if path.exists() and not args.refresh_existing:
            return read_json(path)
        rows = records_from_frame(getattr(pro, api)(**params))
        write_json(path, rows)
        time.sleep(max(args.sleep_seconds, 0.0))
        return rows

    def fetch_trade_days() -> list[str]:
        calendar_file = raw_path(raw_dir, "trade_calendar", f"{start}_{end}")
        try:
            calendar_rows = call_api(
                "trade_cal",
                {"exchange": "SSE", "start_date": start, "end_date": end},
                calendar_file,
            )
            open_days = [
                compact_date(row.get("cal_date"))
                for row in calendar_rows
                if str(row.get("is_open") or "").strip() in {"1", "1.0", "True", "true"}
            ]
            open_days = [day for day in open_days if len(day) == 8]
            if open_days:
                return sorted(set(open_days))
        except Exception as exc:
            summary["errors"].append({"date": f"{start}-{end}", "api": "trade_cal", "error": str(exc).replace(token, "[redacted]")})
        return date_range(start, end)

    days = fetch_trade_days()
    summary["calendar_days"] = len(date_range(start, end))
    summary["trade_days"] = len(days)

    daily_by_code: dict[str, list[dict[str, Any]]] = {ts_code: [] for ts_code in universe_ts_codes}
    adj_by_code: dict[str, list[dict[str, Any]]] = {ts_code: [] for ts_code in universe_ts_codes}
    for index, day in enumerate(days, start=1):
        try:
            if "daily" in datasets:
                rows = call_api("daily", {"trade_date": day}, raw_path(raw_dir, "daily", day))
                for ts_code, items in normalize_daily(rows, universe_ts_codes).items():
                    daily_by_code.setdefault(ts_code, []).extend(items)
                append_log(log_path, {"event": "daily", "date": day, "rows": len(rows)})
            if "adj_factor" in datasets:
                rows = call_api("adj_factor", {"trade_date": day}, raw_path(raw_dir, "adj_factor", day))
                for ts_code, items in normalize_adj(rows, universe_ts_codes).items():
                    adj_by_code.setdefault(ts_code, []).extend(items)
                append_log(log_path, {"event": "adj_factor", "date": day, "rows": len(rows)})
        except Exception as exc:
            error = {"date": day, "error": str(exc).replace(token, "[redacted]")}
            summary["errors"].append(error)
            append_log(log_path, {"event": "error", **error})
        if args.checkpoint_every and index % args.checkpoint_every == 0:
            write_json(report_path, {**summary, "checkpoint_day_index": index})

    persisted = {"bars.daily": 0, "adjustment.factor": 0}
    if args.persist_prism:
        if "daily" in datasets:
            for ts_code, rows in sorted(daily_by_code.items()):
                rows = sorted(rows, key=lambda item: str(item.get("trade_date") or ""))
                if not rows:
                    continue
                code = ts_code[:6]
                save_manifest_dataset(
                    repository,
                    dataset="bars.daily",
                    trade_date=trade_date,
                    key=code,
                    rows=rows,
                    source_api="daily",
                    params={"start_date": start, "end_date": end, "mode": "trade_date_cross_sections"},
                )
                persisted["bars.daily"] += 1
        if "adj_factor" in datasets:
            for ts_code, rows in sorted(adj_by_code.items()):
                rows = sorted(rows, key=lambda item: str(item.get("trade_date") or ""))
                if not rows:
                    continue
                code = ts_code[:6]
                save_manifest_dataset(
                    repository,
                    dataset="adjustment.factor",
                    trade_date=trade_date,
                    key=code,
                    rows=rows,
                    source_api="adj_factor",
                    params={"start_date": start, "end_date": end, "mode": "trade_date_cross_sections"},
                )
                persisted["adjustment.factor"] += 1

    if "price_limit" in datasets:
        rows = call_api("stk_limit", {"trade_date": end}, raw_path(raw_dir, "price_limit", end))
        normalized = [
            {
                "code": _prism_stock_code(row.get("ts_code")),
                "ts_code": row.get("ts_code"),
                "trade_date": dash_date(row.get("trade_date")),
                "up_limit": _float_or_none(row.get("up_limit")),
                "down_limit": _float_or_none(row.get("down_limit")),
            }
            for row in rows
            if row.get("ts_code") and row.get("trade_date")
        ]
        save_manifest_dataset(
            repository,
            dataset="price_limit.daily",
            trade_date=trade_date,
            key="formal-price-limit",
            rows=normalized,
            source_api="stk_limit",
            params={"trade_date": end},
        )
        summary["events"]["price_limit_rows"] = len(normalized)

    if "execution_flags" in datasets:
        limit_rows = call_api("stk_limit", {"trade_date": end}, raw_path(raw_dir, "price_limit", end))
        suspend_rows = call_api("suspend_d", {"trade_date": end}, raw_path(raw_dir, "suspend_d", end))
        st_rows = call_api("stock_st", {"trade_date": end}, raw_path(raw_dir, "stock_st", end))
        limit_by_code = {
            str(row.get("ts_code") or "").strip().upper(): row
            for row in limit_rows
            if str(row.get("ts_code") or "").strip().upper() in universe_ts_codes
        }
        suspend_by_code: dict[str, list[dict[str, Any]]] = {}
        for row in suspend_rows:
            ts_code = str(row.get("ts_code") or "").strip().upper()
            if ts_code in universe_ts_codes:
                suspend_by_code.setdefault(ts_code, []).append(row)
        st_by_code: dict[str, list[dict[str, Any]]] = {}
        for row in st_rows:
            ts_code = str(row.get("ts_code") or "").strip().upper()
            if ts_code in universe_ts_codes:
                st_by_code.setdefault(ts_code, []).append(row)
        execution_rows = []
        for ts_code in sorted(universe_ts_codes):
            limit = limit_by_code.get(ts_code, {})
            suspend_items = suspend_by_code.get(ts_code, [])
            st_items = st_by_code.get(ts_code, [])
            is_suspended = any(str(item.get("suspend_type") or "").upper() == "S" for item in suspend_items)
            is_resumed = any(str(item.get("suspend_type") or "").upper() == "R" for item in suspend_items)
            up_limit = _float_or_none(limit.get("up_limit"))
            down_limit = _float_or_none(limit.get("down_limit"))
            execution_rows.append({
                "code": _prism_stock_code(ts_code),
                "ts_code": ts_code,
                "trade_date": trade_date,
                "is_suspended": is_suspended,
                "is_resumed": is_resumed,
                "is_tradable": not is_suspended,
                "trading_status": "suspended" if is_suspended else ("resumed" if is_resumed else "normal"),
                "suspend_timing": ",".join(
                    str(item.get("suspend_timing") or "").strip()
                    for item in suspend_items
                    if str(item.get("suspend_timing") or "").strip()
                ),
                "suspend_events": [
                    {
                        "suspend_type": item.get("suspend_type"),
                        "suspend_timing": item.get("suspend_timing"),
                        "trade_date": dash_date(item.get("trade_date")),
                    }
                    for item in suspend_items
                ],
                "is_st": bool(st_items),
                "st_name": str((st_items[0] if st_items else {}).get("name") or ""),
                "st_type": str((st_items[0] if st_items else {}).get("type") or ""),
                "st_type_name": str((st_items[0] if st_items else {}).get("type_name") or ""),
                "st_events": [
                    {
                        "name": item.get("name"),
                        "type": item.get("type"),
                        "type_name": item.get("type_name"),
                        "trade_date": dash_date(item.get("trade_date")),
                    }
                    for item in st_items
                ],
                "up_limit": up_limit,
                "down_limit": down_limit,
                "price_limit_available": up_limit is not None and down_limit is not None,
                "execution_blockers": [
                    *(["suspended"] if is_suspended else []),
                    *(["price_limit_missing"] if up_limit is None or down_limit is None else []),
                ],
                "source_apis": ["stk_limit", "suspend_d", "stock_st"],
            })
        missing_limit_count = sum(1 for row in execution_rows if not row.get("price_limit_available"))
        quality_flags = ["execution_flags_price_limit_missing"] if missing_limit_count else []
        save_manifest_dataset(
            repository,
            dataset="execution.flags",
            trade_date=trade_date,
            key="universe-hs300-zz500-execution-flags",
            rows=execution_rows,
            source_api="execution_flags",
            params={"trade_date": end, "universe_count": len(universe_ts_codes)},
            live_small_allowed=not quality_flags,
            quality_flags=quality_flags,
        )
        summary["events"]["execution_flags_rows"] = len(execution_rows)
        summary["events"]["execution_flags_price_limit_missing"] = missing_limit_count

    if "index_daily" in datasets:
        for symbol in [item.strip() for item in args.indexes.split(",") if item.strip()]:
            rows = call_api("index_daily", {"ts_code": symbol, "start_date": start, "end_date": end}, raw_path(raw_dir, "index_daily", end, symbol.replace(".", "")))
            normalized = []
            for row in rows:
                item_date = dash_date(row.get("trade_date"))
                normalized.append({
                    "symbol": symbol,
                    "ts_code": row.get("ts_code") or symbol,
                    "trade_date": item_date,
                    "open": _float_or_none(row.get("open")),
                    "high": _float_or_none(row.get("high")),
                    "low": _float_or_none(row.get("low")),
                    "close": _float_or_none(row.get("close")),
                    "pre_close": _float_or_none(row.get("pre_close")),
                    "change": _float_or_none(row.get("change")),
                    "pct_chg": _float_or_none(row.get("pct_chg")),
                    "volume": _float_or_none(row.get("vol")),
                    "amount": _float_or_none(row.get("amount")),
                })
            key = symbol.split(".")[0]
            save_manifest_dataset(
                repository,
                dataset="benchmark.index_daily",
                trade_date=trade_date,
                key=key,
                rows=[item for item in normalized if item.get("trade_date")],
                source_api="index_daily",
                params={"ts_code": symbol, "start_date": start, "end_date": end},
            )

    summary["ok"] = not summary["errors"]
    summary["persisted"] = persisted
    summary["coverage"] = {
        "bars_daily_codes": sum(1 for rows in daily_by_code.values() if rows),
        "adjustment_factor_codes": sum(1 for rows in adj_by_code.values() if rows),
        "daily_rows": sum(len(rows) for rows in daily_by_code.values()),
        "adj_factor_rows": sum(len(rows) for rows in adj_by_code.values()),
    }
    summary["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    write_json(report_path, summary)
    append_log(log_path, {"event": "finish", "summary": summary})
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
