#!/usr/bin/env python3
"""Promote harvested Tinyshare research raw files into Prism datasets.

The overnight harvest stores a faithful raw archive. This script turns that
archive into queryable Prism datasets with manifests, while keeping the
formal trading gate separate from research/display datasets.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_ROOT = REPO_ROOT / "packages"
CONTROL_PANEL_ROOT = REPO_ROOT / "apps" / "control-panel"
for path in (PACKAGES_ROOT, CONTROL_PANEL_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from prism_data.contracts import DatasetStatus, ProviderRole, ProviderResult  # noqa: E402
from prism_data.manifest import manifest_from_provider_result  # noqa: E402
from prism_data.repositories import DatasetRepository  # noqa: E402
from prism_data.utils import default_dataset_repository_root, hash_payload  # noqa: E402
try:
    from readiness import expected_trade_date  # noqa: E402
except Exception:  # pragma: no cover - CLI fallback.
    expected_trade_date = None  # type: ignore[assignment]


DEFAULT_RESEARCH_LATEST = REPO_ROOT / "data" / "prism_data" / "tinyshare_research_harvest" / "latest_run.json"
TINYSHARE_ENDPOINT = "tinyshare://pro_api/raw_research_harvest"
LICENSE_SCOPE = "authorized_tinyshare_proxy"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Promote Tinyshare raw research harvest into Prism datasets.")
    parser.add_argument("--research-run", default="", help="Research harvest run directory. Defaults to latest_run.json.")
    parser.add_argument("--trade-date", default="")
    parser.add_argument("--repository-root", default="")
    parser.add_argument("--limit-codes", type=int, default=0)
    parser.add_argument("--refresh-existing", action="store_true")
    return parser.parse_args()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_research_run(raw: str) -> Path:
    if raw.strip():
        return Path(raw).expanduser().resolve()
    latest = read_json(DEFAULT_RESEARCH_LATEST)
    return Path(latest["run_dir"]).resolve()


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


def ts_code_for_digits(code: str) -> str:
    return f"{code}.{'SH' if code.startswith(('5', '6', '9')) else 'BJ' if code.startswith(('4', '8')) else 'SZ'}"


def prism_code(ts_code: Any) -> str:
    text = str(ts_code or "").strip().upper()
    code = digits_code(text)
    if not code or len(code) != 6:
        return str(ts_code or "").strip().lower()
    suffix = text.split(".")[-1] if "." in text else ("SH" if code.startswith(("5", "6", "9")) else "BJ" if code.startswith(("4", "8")) else "SZ")
    return f"{'sh' if suffix == 'SH' else 'bj' if suffix == 'BJ' else 'sz'}{code}"


def safe_float(value: Any) -> float | None:
    if value in (None, "", "-", "None"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else number


def round_or_none(value: Any, digits: int = 4) -> float | None:
    number = safe_float(value)
    return None if number is None else round(number, digits)


def latest_by_date(rows: list[dict[str, Any]], *date_fields: str) -> dict[str, Any] | None:
    if not rows:
        return None

    def key(row: dict[str, Any]) -> str:
        for field in date_fields:
            value = compact_date(row.get(field))
            if value:
                return value
        return ""

    ordered = sorted(rows, key=key)
    return dict(ordered[-1]) if ordered else None


def rows_from_dir(raw_dir: Path, dataset: str, suffix: str = "*.json") -> list[Path]:
    path = raw_dir / dataset
    return sorted(path.glob(suffix)) if path.exists() else []


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
    live_small_allowed: bool,
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
        quality_flags=list(quality_flags or []),
        license_scope=LICENSE_SCOPE,
        live_small_allowed=live_small_allowed,
        request_key=key,
        extra={
            "source_api": source_api,
            "source_proxy": "tinyshare",
            "authority_provider_override": "tushare",
            "promoted_from_raw": True,
        },
    )
    manifest = manifest_from_provider_result(result, expected_trade_date=trade_date, live_small_allowed=live_small_allowed)
    data_path, manifest_path = repository.save_dataset(dataset, trade_date, key, rows, manifest)
    manifest["data_path"] = str(data_path.resolve())
    manifest["manifest_path"] = str(manifest_path.resolve())
    return manifest


def normalize_moneyflow_row(row: dict[str, Any]) -> dict[str, Any]:
    ts_code = str(row.get("ts_code") or "").strip().upper()
    trade_date = dash_date(row.get("trade_date"))
    buy_lg = safe_float(row.get("buy_lg_amount")) or 0.0
    sell_lg = safe_float(row.get("sell_lg_amount")) or 0.0
    buy_elg = safe_float(row.get("buy_elg_amount")) or 0.0
    sell_elg = safe_float(row.get("sell_elg_amount")) or 0.0
    buy_sm = safe_float(row.get("buy_sm_amount")) or 0.0
    sell_sm = safe_float(row.get("sell_sm_amount")) or 0.0
    net_mf = safe_float(row.get("net_mf_amount"))
    large_net = buy_lg - sell_lg
    extra_large_net = buy_elg - sell_elg
    main_net = large_net + extra_large_net
    small_net = buy_sm - sell_sm
    return {
        "date": trade_date,
        "trade_date": trade_date,
        "code": digits_code(ts_code),
        "symbol": prism_code(ts_code),
        "ts_code": ts_code,
        "main_net": round(main_net, 2),
        "main_net_wan": round(main_net, 2),
        "main_net_yi": round(main_net / 10000, 4),
        "super_large": round(extra_large_net, 2),
        "super_large_wan": round(extra_large_net, 2),
        "super_large_yi": round(extra_large_net / 10000, 4),
        "mid_large_net": round(large_net, 2),
        "mid_large_net_wan": round(large_net, 2),
        "mid_large_net_yi": round(large_net / 10000, 4),
        "small_net": round(small_net, 2),
        "small_net_wan": round(small_net, 2),
        "small_net_yi": round(small_net / 10000, 4),
        "retail_net": round((net_mf or 0.0) - main_net, 2) if net_mf is not None else None,
        "net_mf_amount": round_or_none(net_mf),
        "unit": "wan_yuan",
    }


def normalize_valuation(row: dict[str, Any]) -> dict[str, Any]:
    ts_code = str(row.get("ts_code") or "").strip().upper()
    trade_date = dash_date(row.get("trade_date"))
    return {
        "date": trade_date,
        "trade_date": trade_date,
        "code": digits_code(ts_code),
        "symbol": prism_code(ts_code),
        "ts_code": ts_code,
        "close": round_or_none(row.get("close")),
        "pe": round_or_none(row.get("pe")),
        "pe_ttm": round_or_none(row.get("pe_ttm")),
        "pb": round_or_none(row.get("pb")),
        "ps": round_or_none(row.get("ps")),
        "ps_ttm": round_or_none(row.get("ps_ttm")),
        "dv_ratio": round_or_none(row.get("dv_ratio")),
        "dv_ttm": round_or_none(row.get("dv_ttm")),
        "total_mv": round_or_none(row.get("total_mv")),
        "total_mv_yi": round_or_none((safe_float(row.get("total_mv")) or 0.0) / 10000),
        "circ_mv": round_or_none(row.get("circ_mv")),
        "circ_mv_yi": round_or_none((safe_float(row.get("circ_mv")) or 0.0) / 10000),
    }


def normalize_liquidity(row: dict[str, Any]) -> dict[str, Any]:
    ts_code = str(row.get("ts_code") or "").strip().upper()
    trade_date = dash_date(row.get("trade_date"))
    return {
        "date": trade_date,
        "trade_date": trade_date,
        "code": digits_code(ts_code),
        "symbol": prism_code(ts_code),
        "ts_code": ts_code,
        "turnover_rate": round_or_none(row.get("turnover_rate")),
        "turnover_rate_f": round_or_none(row.get("turnover_rate_f")),
        "volume_ratio": round_or_none(row.get("volume_ratio")),
        "total_share": round_or_none(row.get("total_share")),
        "float_share": round_or_none(row.get("float_share")),
        "free_share": round_or_none(row.get("free_share")),
    }


def fundamentals_snapshot(
    *,
    ts_code: str,
    daily_basic: dict[str, Any] | None,
    stock_basic: dict[str, Any] | None,
    fina_indicator: dict[str, Any] | None,
    income: dict[str, Any] | None,
    balance: dict[str, Any] | None,
    cashflow: dict[str, Any] | None,
) -> dict[str, Any]:
    code = digits_code(ts_code)
    valuation = normalize_valuation(daily_basic or {"ts_code": ts_code}) if daily_basic else {}
    indicator = fina_indicator or {}
    income_row = income or {}
    balance_row = balance or {}
    cashflow_row = cashflow or {}
    return {
        "code": code,
        "symbol": prism_code(ts_code),
        "ts_code": ts_code,
        "trade_date": dash_date((daily_basic or {}).get("trade_date")),
        "name": (stock_basic or {}).get("name"),
        "area": (stock_basic or {}).get("area"),
        "industry": (stock_basic or {}).get("industry"),
        "market": (stock_basic or {}).get("market"),
        "list_date": dash_date((stock_basic or {}).get("list_date")),
        "price": valuation.get("close"),
        "pe": valuation.get("pe") or valuation.get("pe_ttm"),
        "pe_ttm": valuation.get("pe_ttm") or valuation.get("pe"),
        "pb": valuation.get("pb"),
        "ps": valuation.get("ps"),
        "ps_ttm": valuation.get("ps_ttm"),
        "total_mv": valuation.get("total_mv_yi"),
        "total_mv_yi": valuation.get("total_mv_yi"),
        "circ_mv_yi": valuation.get("circ_mv_yi"),
        "roe": round_or_none(indicator.get("roe")),
        "roe_waa": round_or_none(indicator.get("roe_waa")),
        "roe_yearly": round_or_none(indicator.get("roe_yearly")),
        "roa": round_or_none(indicator.get("roa")),
        "gross_margin": round_or_none(indicator.get("grossprofit_margin")),
        "netprofit_margin": round_or_none(indicator.get("netprofit_margin")),
        "debt_to_assets": round_or_none(indicator.get("debt_to_assets")),
        "current_ratio": round_or_none(indicator.get("current_ratio")),
        "quick_ratio": round_or_none(indicator.get("quick_ratio")),
        "eps": round_or_none(indicator.get("eps")),
        "bps": round_or_none(indicator.get("bps")),
        "net_profit": round_or_none(income_row.get("n_income") or income_row.get("net_profit")),
        "revenue": round_or_none(income_row.get("revenue")),
        "total_revenue": round_or_none(income_row.get("total_revenue")),
        "total_assets": round_or_none(balance_row.get("total_assets")),
        "total_liab": round_or_none(balance_row.get("total_liab")),
        "net_cashflow_oper": round_or_none(cashflow_row.get("n_cashflow_act") or cashflow_row.get("net_cash_flows_oper_act")),
        "latest_report_end_date": dash_date(indicator.get("end_date") or income_row.get("end_date") or balance_row.get("end_date")),
        "latest_announcement_date": dash_date(indicator.get("ann_date") or income_row.get("ann_date") or balance_row.get("ann_date")),
        "source": "tinyshare/tushare",
    }


def promote(research_run: Path, trade_date: str, repository: DatasetRepository, *, limit_codes: int = 0, refresh_existing: bool = False) -> dict[str, Any]:
    raw_dir = research_run / "raw"
    stock_basic_rows = read_json(raw_dir / "stock_basic" / "universe_hs300_zz500.json")
    stock_by_ts = {str(row.get("ts_code") or "").strip().upper(): dict(row) for row in stock_basic_rows}
    ts_codes = sorted(stock_by_ts)
    if limit_codes:
        ts_codes = ts_codes[:limit_codes]
    ts_set = set(ts_codes)
    latest_compact = compact_date(trade_date)

    # Load cross-section rows once so batch and per-code datasets share the same normalization.
    daily_basic_by_code: dict[str, list[dict[str, Any]]] = {ts_code: [] for ts_code in ts_codes}
    moneyflow_by_code: dict[str, list[dict[str, Any]]] = {ts_code: [] for ts_code in ts_codes}
    limit_event_rows: list[dict[str, Any]] = []
    for path in rows_from_dir(raw_dir, "daily_basic"):
        for row in read_json(path):
            ts_code = str(row.get("ts_code") or "").strip().upper()
            if ts_code in ts_set:
                daily_basic_by_code.setdefault(ts_code, []).append(row)
    for path in rows_from_dir(raw_dir, "moneyflow"):
        for row in read_json(path):
            ts_code = str(row.get("ts_code") or "").strip().upper()
            if ts_code in ts_set:
                moneyflow_by_code.setdefault(ts_code, []).append(row)
    for path in rows_from_dir(raw_dir, "limit_list_d"):
        date = dash_date(path.name.split("_", 1)[0])
        for row in read_json(path):
            ts_code = str(row.get("ts_code") or "").strip().upper()
            if ts_code in ts_set:
                item = dict(row)
                item["trade_date"] = dash_date(item.get("trade_date") or date)
                item["code"] = digits_code(ts_code)
                item["symbol"] = prism_code(ts_code)
                limit_event_rows.append(item)

    manifests: list[dict[str, Any]] = []
    counts: dict[str, int] = {}

    latest_valuation_batch: dict[str, dict[str, Any]] = {}
    latest_liquidity_batch: dict[str, dict[str, Any]] = {}
    latest_moneyflow_batch: dict[str, dict[str, Any]] = {}
    fundamentals_batch: dict[str, dict[str, Any]] = {}

    for ts_code in ts_codes:
        code = digits_code(ts_code)
        normalized_valuation = [normalize_valuation(row) for row in daily_basic_by_code.get(ts_code, [])]
        normalized_valuation = [row for row in normalized_valuation if row.get("trade_date")]
        normalized_valuation.sort(key=lambda row: str(row.get("trade_date") or ""))
        normalized_liquidity = [normalize_liquidity(row) for row in daily_basic_by_code.get(ts_code, [])]
        normalized_liquidity = [row for row in normalized_liquidity if row.get("trade_date")]
        normalized_liquidity.sort(key=lambda row: str(row.get("trade_date") or ""))
        normalized_moneyflow = [normalize_moneyflow_row(row) for row in moneyflow_by_code.get(ts_code, [])]
        normalized_moneyflow = [row for row in normalized_moneyflow if row.get("trade_date")]
        normalized_moneyflow.sort(key=lambda row: str(row.get("trade_date") or ""))

        for dataset, rows, api in (
            ("valuation.daily", normalized_valuation, "daily_basic"),
            ("liquidity.daily", normalized_liquidity, "daily_basic"),
            ("capital_flow.daily", normalized_moneyflow, "moneyflow"),
        ):
            existing_manifest = repository.load_manifest(dataset, trade_date, code)
            if refresh_existing or not existing_manifest:
                manifest = save_dataset(
                    repository,
                    dataset=dataset,
                    trade_date=trade_date,
                    key=code,
                    rows=rows,
                    source_api=api,
                    params={"ts_code": ts_code, "end_date": latest_compact},
                    source_raw_paths=[raw_dir / api],
                    live_small_allowed=dataset == "capital_flow.daily",
                )
                manifests.append(manifest)
            counts[dataset] = counts.get(dataset, 0) + 1

        if normalized_valuation:
            latest_valuation_batch[code] = normalized_valuation[-1]
        if normalized_liquidity:
            latest_liquidity_batch[code] = normalized_liquidity[-1]
        if normalized_moneyflow:
            latest_moneyflow_batch[code] = normalized_moneyflow[-1]

        fina_rows = read_json(raw_dir / "fina_indicator" / f"{ts_code}.json")
        income_rows = read_json(raw_dir / "income" / f"{ts_code}.json")
        balance_rows = read_json(raw_dir / "balancesheet" / f"{ts_code}.json")
        cashflow_rows = read_json(raw_dir / "cashflow" / f"{ts_code}.json")
        express_rows = read_json(raw_dir / "express" / f"{ts_code}.json")
        forecast_rows = read_json(raw_dir / "forecast" / f"{ts_code}.json")
        dividend_rows = read_json(raw_dir / "dividend" / f"{ts_code}.json")
        top10_rows = read_json(raw_dir / "top10_holders" / f"{ts_code}.json")
        top10_float_rows = read_json(raw_dir / "top10_floatholders" / f"{ts_code}.json")

        indicator = [dict(row, code=code, symbol=prism_code(ts_code)) for row in fina_rows]
        statement = {
            "code": code,
            "symbol": prism_code(ts_code),
            "ts_code": ts_code,
            "income": income_rows,
            "balancesheet": balance_rows,
            "cashflow": cashflow_rows,
            "express": express_rows,
            "forecast": forecast_rows,
        }
        dividends = [dict(row, code=code, symbol=prism_code(ts_code)) for row in dividend_rows]
        shareholders = {
            "code": code,
            "symbol": prism_code(ts_code),
            "ts_code": ts_code,
            "top10_holders": top10_rows,
            "top10_floatholders": top10_float_rows,
        }
        fundamental = fundamentals_snapshot(
            ts_code=ts_code,
            daily_basic=latest_by_date(daily_basic_by_code.get(ts_code, []), "trade_date"),
            stock_basic=stock_by_ts.get(ts_code),
            fina_indicator=latest_by_date(fina_rows, "end_date", "ann_date"),
            income=latest_by_date(income_rows, "end_date", "ann_date"),
            balance=latest_by_date(balance_rows, "end_date", "ann_date"),
            cashflow=latest_by_date(cashflow_rows, "end_date", "ann_date"),
        )
        fundamentals_batch[code] = fundamental

        for dataset, payload, api in (
            ("financial.indicator", indicator, "fina_indicator"),
            ("financial.statement", statement, "income,balancesheet,cashflow,express,forecast"),
            ("corporate_action.dividend", dividends, "dividend"),
            ("shareholder.top10", shareholders, "top10_holders,top10_floatholders"),
            ("fundamentals.snapshot", fundamental, "daily_basic,fina_indicator,income,balancesheet,cashflow"),
        ):
            existing_manifest = repository.load_manifest(dataset, trade_date, code)
            if refresh_existing or not existing_manifest:
                manifest = save_dataset(
                    repository,
                    dataset=dataset,
                    trade_date=trade_date,
                    key=code,
                    rows=payload,
                    source_api=api,
                    params={"ts_code": ts_code, "end_date": latest_compact},
                    source_raw_paths=[raw_dir],
                    live_small_allowed=dataset == "fundamentals.snapshot",
                )
                manifests.append(manifest)
            counts[dataset] = counts.get(dataset, 0) + 1

    batch_payloads = (
        ("capital_flow.batch", "tinyshare-hs300-zz500", latest_moneyflow_batch, "moneyflow", True),
        ("fundamentals.batch", "tinyshare-hs300-zz500", fundamentals_batch, "daily_basic,fina_indicator,income,balancesheet,cashflow", True),
        ("valuation.daily", "tinyshare-hs300-zz500-latest", latest_valuation_batch, "daily_basic", False),
        ("liquidity.daily", "tinyshare-hs300-zz500-latest", latest_liquidity_batch, "daily_basic", False),
        ("market.limit_events", "tinyshare-hs300-zz500", limit_event_rows, "limit_list_d", False),
    )
    for dataset, key, payload, api, live_allowed in batch_payloads:
        existing_manifest = repository.load_manifest(dataset, trade_date, key)
        if refresh_existing or not existing_manifest:
            manifests.append(save_dataset(
                repository,
                dataset=dataset,
                trade_date=trade_date,
                key=key,
                rows=payload,
                source_api=api,
                params={"universe": "hs300+zz500", "end_date": latest_compact},
                source_raw_paths=[raw_dir],
                live_small_allowed=live_allowed,
            ))
        counts[dataset] = counts.get(dataset, 0) + 1

    summary = {
        "ok": True,
        "trade_date": trade_date,
        "research_run": str(research_run),
        "universe_count": len(ts_codes),
        "counts": counts,
        "written_manifests": len(manifests),
        "dataset_root": str(repository.base_path.resolve()),
        "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    out_path = research_run / "promotion_report.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary["promotion_report_path"] = str(out_path.resolve())
    return summary


def main() -> int:
    args = parse_args()
    research_run = resolve_research_run(args.research_run)
    trade_date = args.trade_date.strip() or (expected_trade_date() if expected_trade_date else "2026-05-29")
    repository = DatasetRepository(Path(args.repository_root).expanduser() if args.repository_root.strip() else default_dataset_repository_root())
    summary = promote(
        research_run,
        trade_date,
        repository,
        limit_codes=max(args.limit_codes, 0),
        refresh_existing=args.refresh_existing,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
