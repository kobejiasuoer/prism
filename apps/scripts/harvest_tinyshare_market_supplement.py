#!/usr/bin/env python3
"""Harvest high-value Tinyshare market context datasets.

This is intentionally separate from the formal-data gate. It spends a short
Tinyshare authorization window on datasets that improve research, review, and
operator visibility: index weights, whole-market daily basics, margin data,
Dragon-Tiger activity, and north/southbound flow context.
"""

from __future__ import annotations

import argparse
import json
import math
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

from prism_data.contracts import DatasetStatus, ProviderRole, ProviderResult  # noqa: E402
from prism_data.env import load_project_env  # noqa: E402
from prism_data.manifest import manifest_from_provider_result  # noqa: E402
from prism_data.repositories import DatasetRepository  # noqa: E402
from prism_data.utils import default_dataset_repository_root, hash_payload  # noqa: E402


load_project_env(root=REPO_ROOT)

TOKEN_ENV_NAMES = (
    "PRISM_TINYSHARE_TOKEN",
    "TINYSHARE_TOKEN",
    "PRISM_TUSHARE_TOKEN",
    "TUSHARE_TOKEN",
)
DEFAULT_SOURCE_RUN = REPO_ROOT / "data" / "prism_data" / "tinyshare_harvest" / "latest_run.json"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data" / "prism_data" / "tinyshare_market_supplement"
TINYSHARE_ENDPOINT = "tinyshare://pro_api/market_supplement"
LICENSE_SCOPE = "authorized_tinyshare_proxy"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Harvest Tinyshare market-context supplement datasets.")
    parser.add_argument("--start-date", default="2022-01-01")
    parser.add_argument("--end-date", default="2026-05-29")
    parser.add_argument("--recent-trade-days", type=int, default=60)
    parser.add_argument("--source-run-json", default=str(DEFAULT_SOURCE_RUN))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--repository-root", default="")
    parser.add_argument("--run-dir", default="", help="Existing run directory to resume/write into.")
    parser.add_argument("--index-codes", default="000300.SH,000905.SH,000852.SH")
    parser.add_argument(
        "--datasets",
        default="index_weight,bak_basic,margin,top_list,top_inst,ggt_daily,moneyflow_hsgt",
    )
    parser.add_argument("--sleep-seconds", type=float, default=0.04)
    parser.add_argument("--refresh-existing", action="store_true")
    return parser.parse_args()


def compact_date(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())[:8]


def dash_date(value: Any) -> str:
    digits = compact_date(value)
    if len(digits) != 8:
        return str(value or "").strip()
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"


def digits_code(value: Any) -> str:
    text = str(value or "").strip().upper()
    if "." in text:
        text = text.split(".", 1)[0]
    return "".join(ch for ch in text if ch.isdigit()).zfill(6)


def prism_code(ts_code: Any) -> str:
    text = str(ts_code or "").strip().upper()
    code = digits_code(text)
    if not code or len(code) != 6:
        return str(ts_code or "").strip().lower()
    suffix = text.split(".")[-1] if "." in text else ("SH" if code.startswith(("5", "6", "9")) else "BJ" if code.startswith(("4", "8")) else "SZ")
    return f"{'sh' if suffix == 'SH' else 'bj' if suffix == 'BJ' else 'sz'}{code}"


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if value is None or isinstance(value, (str, bool, int, float)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
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


def resolve_token() -> tuple[str, str]:
    load_project_env(root=REPO_ROOT)
    for name in TOKEN_ENV_NAMES:
        value = os.environ.get(name, "").strip()
        if value:
            return value, name
    return "", ""


def load_trade_days(source_run_json: Path, start: str, end: str, recent: int) -> list[str]:
    latest = read_json(source_run_json)
    run_dir = Path(latest["run_dir"])
    calendar_dir = run_dir / "raw" / "trade_calendar"
    calendar_path = calendar_dir / f"{compact_date(start)}_{compact_date(end)}_all.json"
    if not calendar_path.exists():
        candidates = sorted(calendar_dir.glob("*_all.json"))
        if candidates:
            calendar_path = candidates[-1]
    rows = read_json(calendar_path)
    days = [
        compact_date(row.get("cal_date"))
        for row in rows
        if str(row.get("is_open") or "") == "1" and compact_date(row.get("cal_date"))
    ]
    days = sorted({day for day in days if compact_date(start) <= day <= compact_date(end)})
    if recent > 0:
        days = days[-recent:]
    return days


def event(log_path: Path, name: str, **payload: Any) -> None:
    row = {"at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "event": name, **payload}
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def save_dataset(
    repository: DatasetRepository,
    *,
    dataset: str,
    trade_date: str,
    key: str,
    rows: Any,
    source_api: str,
    params: dict[str, Any],
    source_raw_paths: list[Path],
) -> dict[str, Any]:
    result = ProviderResult(
        status=DatasetStatus.OK,
        data=rows,
        provider="tushare",
        provider_role=ProviderRole.PRIMARY,
        dataset=dataset,
        trade_date=trade_date,
        fetched_at=datetime.now(),
        asof=datetime.strptime(trade_date, "%Y-%m-%d"),
        ttl_seconds=86400,
        source_endpoint=TINYSHARE_ENDPOINT,
        params_hash=hash_payload({
            "source_api": source_api,
            "params": params,
            "source_raw_paths": [str(path) for path in source_raw_paths],
            "source_proxy": "tinyshare",
        }),
        payload_hash=hash_payload(rows),
        row_count=len(rows) if isinstance(rows, (list, dict, tuple, set)) else int(rows is not None),
        quality_flags=[],
        license_scope=LICENSE_SCOPE,
        live_small_allowed=False,
        request_key=key,
        extra={
            "source_api": source_api,
            "source_proxy": "tinyshare",
            "authority_provider_override": "tushare",
            "promoted_from_raw": True,
        },
    )
    manifest = manifest_from_provider_result(result, expected_trade_date=trade_date, live_small_allowed=False)
    data_path, manifest_path = repository.save_dataset(dataset, trade_date, key, rows, manifest)
    manifest["data_path"] = str(data_path.resolve())
    manifest["manifest_path"] = str(manifest_path.resolve())
    return manifest


def enrich_stock_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        ts_code = str(item.get("ts_code") or item.get("con_code") or "").strip().upper()
        if ts_code:
            item.setdefault("code", digits_code(ts_code))
            item.setdefault("symbol", prism_code(ts_code))
        if item.get("trade_date"):
            item["trade_date"] = dash_date(item.get("trade_date"))
        enriched.append(item)
    return enriched


def flatten_raw_days(raw_dir: Path, dataset: str, trade_days: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for day in trade_days:
        path = raw_dir / dataset / f"{day}_all.json"
        if path.exists():
            rows.extend(enrich_stock_rows(read_json(path)))
    return rows


def main() -> int:
    args = parse_args()
    start = compact_date(args.start_date)
    end = compact_date(args.end_date)
    datasets = {item.strip() for item in args.datasets.split(",") if item.strip()}
    index_codes = [item.strip().upper() for item in args.index_codes.split(",") if item.strip()]
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.run_dir).expanduser() if args.run_dir else Path(args.output_root) / f"{start}_{end}_{run_id}"
    if args.run_dir:
        run_id = run_dir.name
    raw_dir = run_dir / "raw"
    log_path = run_dir / "events.jsonl"
    report_path = run_dir / "report.json"
    latest_path = Path(args.output_root) / "latest_run.json"
    repository = DatasetRepository(Path(args.repository_root).expanduser() if args.repository_root.strip() else default_dataset_repository_root())

    run_dir.mkdir(parents=True, exist_ok=True)
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(latest_path, {"run_dir": str(run_dir), "report_path": str(report_path), "log_path": str(log_path)})

    token, token_env_name = resolve_token()
    if not token:
        raise SystemExit("Tinyshare/Tushare token is not configured")

    import tinyshare as ts  # type: ignore

    ts.set_token(token)
    pro = ts.pro_api()
    trade_days = load_trade_days(Path(args.source_run_json), start, end, max(args.recent_trade_days, 0))
    trade_date = dash_date(trade_days[-1] if trade_days else end)
    summary: dict[str, Any] = {
        "ok": False,
        "run_id": run_id,
        "start_date": start,
        "end_date": end,
        "recent_trade_days": len(trade_days),
        "trade_date": trade_date,
        "datasets": sorted(datasets),
        "index_codes": index_codes,
        "token_env_name": token_env_name,
        "token_value_visible": False,
        "raw_dir": str(raw_dir),
        "dataset_root": str(repository.base_path.resolve()),
        "events": {},
        "errors": [],
    }
    event(log_path, "start", summary=summary)

    def call(api: str, params: dict[str, Any], output_path: Path) -> list[dict[str, Any]]:
        if output_path.exists() and not args.refresh_existing:
            rows = read_json(output_path)
            return rows if isinstance(rows, list) else []
        frame = getattr(pro, api)(**params)
        rows = records_from_frame(frame)
        write_json(output_path, rows)
        time.sleep(max(args.sleep_seconds, 0.0))
        return rows

    for api in ("bak_basic", "margin", "top_list", "top_inst", "ggt_daily", "moneyflow_hsgt"):
        if api not in datasets:
            continue
        api_days = [trade_days[-1]] if api == "bak_basic" and trade_days else trade_days
        for day in api_days:
            try:
                rows = call(api, {"trade_date": day}, raw_dir / api / f"{day}_all.json")
                summary["events"][f"{api}_rows"] = int(summary["events"].get(f"{api}_rows", 0)) + len(rows)
                event(log_path, api, date=day, rows=len(rows))
            except Exception as exc:  # noqa: BLE001
                error = {"api": api, "date": day, "error": str(exc)}
                summary["errors"].append(error)
                event(log_path, "error", **error)
        write_json(report_path, summary)

    if "index_weight" in datasets:
        for index_code in index_codes:
            try:
                rows = call(
                    "index_weight",
                    {"index_code": index_code, "trade_date": compact_date(trade_date)},
                    raw_dir / "index_weight" / f"{compact_date(trade_date)}_{index_code}.json",
                )
                rows = enrich_stock_rows(rows)
                write_json(raw_dir / "index_weight" / f"{compact_date(trade_date)}_{index_code}.json", rows)
                summary["events"][f"index_weight_{index_code}_rows"] = len(rows)
                event(log_path, "index_weight", index_code=index_code, rows=len(rows))
            except Exception as exc:  # noqa: BLE001
                error = {"api": "index_weight", "index_code": index_code, "error": str(exc)}
                summary["errors"].append(error)
                event(log_path, "error", **error)
        write_json(report_path, summary)

    manifests: list[dict[str, Any]] = []
    if "index_weight" in datasets:
        for index_code in index_codes:
            path = raw_dir / "index_weight" / f"{compact_date(trade_date)}_{index_code}.json"
            if not path.exists():
                continue
            rows = read_json(path)
            manifests.append(save_dataset(
                repository,
                dataset="index.weight",
                trade_date=trade_date,
                key=index_code,
                rows=rows,
                source_api="index_weight",
                params={"index_code": index_code, "trade_date": compact_date(trade_date)},
                source_raw_paths=[path],
            ))

    latest_day = trade_days[-1] if trade_days else compact_date(trade_date)
    dataset_promotions = [
        ("bak_basic", "market.daily_basic_snapshot", "all", [raw_dir / "bak_basic" / f"{latest_day}_all.json"]),
        ("margin", "market.margin", "recent", [raw_dir / "margin"]),
        ("top_list", "market.top_list", "recent", [raw_dir / "top_list"]),
        ("top_inst", "market.top_inst", "recent", [raw_dir / "top_inst"]),
        ("ggt_daily", "market.ggt_daily", "recent", [raw_dir / "ggt_daily"]),
        ("moneyflow_hsgt", "market.hsgt_moneyflow", "recent", [raw_dir / "moneyflow_hsgt"]),
    ]
    for api, dataset, key, source_paths in dataset_promotions:
        if api not in datasets:
            continue
        if api == "bak_basic":
            latest_path_for_api = raw_dir / api / f"{latest_day}_all.json"
            rows = enrich_stock_rows(read_json(latest_path_for_api)) if latest_path_for_api.exists() else []
        else:
            rows = flatten_raw_days(raw_dir, api, trade_days)
        manifests.append(save_dataset(
            repository,
            dataset=dataset,
            trade_date=trade_date,
            key=key,
            rows=rows,
            source_api=api,
            params={"start_date": start, "end_date": end, "recent_trade_days": len(trade_days)},
            source_raw_paths=source_paths,
        ))
        summary["events"][f"promoted_{dataset}_rows"] = len(rows)

    summary["ok"] = True
    summary["written_manifests"] = len(manifests)
    summary["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    write_json(report_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
