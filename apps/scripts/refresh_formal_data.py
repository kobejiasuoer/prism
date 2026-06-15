#!/usr/bin/env python3
"""Refresh formal-source datasets through Prism's data gateway."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_ROOT = REPO_ROOT / "packages"
CONTROL_PANEL_ROOT = REPO_ROOT / "apps" / "control-panel"
for path in (PACKAGES_ROOT, CONTROL_PANEL_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from prism_data.contracts import DatasetStatus, ProviderResult, ProviderRole  # noqa: E402
from prism_data.env import load_project_env  # noqa: E402
from prism_data.service import get_data_gateway  # noqa: E402
from prism_data.utils import digits_code, hash_payload  # noqa: E402
from dataset_manifests import formal_reference_trade_date  # noqa: E402
from readiness import expected_trade_date  # noqa: E402
from watchlist_registry import list_active_watchlist_stocks  # noqa: E402

load_project_env(root=REPO_ROOT)

FORMAL_DATASETS = (
    "trade_calendar",
    "bars.daily",
    "adjustment.factor",
    "benchmark.index_daily",
    "price_limit.daily",
    "execution.flags",
)
DEFAULT_INDEXES = ("000300", "000905")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh formal Tushare-backed Prism datasets")
    parser.add_argument("--date", default="", help="Expected trade date. Defaults to Prism expected trade date.")
    parser.add_argument("--start-date", default="", help="Optional start date for daily windows.")
    parser.add_argument("--codes", default="", help="Comma-separated stock codes. Defaults to active watchlist.")
    parser.add_argument("--indexes", default=",".join(DEFAULT_INDEXES), help="Comma-separated index symbols.")
    parser.add_argument("--datasets", default="all", help="Comma-separated datasets or all.")
    parser.add_argument("--limit", type=int, default=40, help="Maximum stock codes to refresh.")
    parser.add_argument("--bars-count", type=int, default=120)
    parser.add_argument("--provider", default="tushare")
    parser.add_argument(
        "--tushare-min-interval-seconds",
        type=float,
        default=61.0,
        help="Minimum seconds between Tushare calls for known 1/minute APIs.",
    )
    parser.add_argument(
        "--tushare-rate-limit-retry-seconds",
        type=float,
        default=65.0,
        help="Seconds to wait before retrying a Tushare rate-limited response.",
    )
    parser.add_argument(
        "--tushare-request-cache-seconds",
        type=float,
        default=600.0,
        help="In-process cache window for identical Tushare API requests.",
    )
    parser.add_argument(
        "--refresh-existing",
        action="store_true",
        help="Refresh keys even when a ready formal manifest already exists.",
    )
    parser.add_argument(
        "--index-batch-limit",
        type=int,
        default=None,
        help=(
            "Maximum missing benchmark indexes to refresh in this run. "
            "Defaults to 1 for Tushare to respect hourly index_daily quota; "
            "use 0 to refresh all pending indexes."
        ),
    )
    return parser.parse_args()


def _date_digits(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())[:8]


def _dash_date(value: str) -> str:
    digits = _date_digits(value)
    if len(digits) != 8:
        return value
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"


def _default_start_date(trade_date: str, bars_count: int) -> str:
    end = datetime.strptime(_date_digits(trade_date), "%Y%m%d")
    return (end - timedelta(days=max(30, bars_count * 2))).strftime("%Y-%m-%d")


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        value = str(item or "").strip()
        if value and value not in out:
            out.append(value)
    return out


def resolve_codes(raw: str, limit: int) -> list[str]:
    if raw.strip():
        candidates = [item.strip() for item in raw.split(",")]
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
        "dataset": manifest.get("dataset") or getattr(result, "dataset", ""),
        "request_key": manifest.get("request_key") or getattr(result, "request_key", ""),
        "provider": manifest.get("provider"),
        "status": manifest.get("status"),
        "freshness_status": manifest.get("freshness_status"),
        "trade_date": manifest.get("trade_date"),
        "row_count": manifest.get("row_count"),
        "live_small_allowed": bool(manifest.get("live_small_allowed")),
        "source_authority_ready": bool(manifest.get("source_authority_ready")),
        "formal_decision_allowed": bool(manifest.get("formal_decision_allowed")),
        "quality_flags": list(manifest.get("quality_flags") or []),
        "error": manifest.get("error"),
        "manifest_path": manifest.get("manifest_path"),
        "data_path": manifest.get("data_path"),
    }


def _manifest_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "dataset": manifest.get("dataset", ""),
        "request_key": manifest.get("request_key", ""),
        "provider": manifest.get("provider"),
        "status": manifest.get("status"),
        "freshness_status": manifest.get("freshness_status"),
        "trade_date": manifest.get("trade_date"),
        "row_count": manifest.get("row_count"),
        "live_small_allowed": bool(manifest.get("live_small_allowed")),
        "source_authority_ready": bool(manifest.get("source_authority_ready")),
        "formal_decision_allowed": bool(manifest.get("formal_decision_allowed")),
        "quality_flags": list(manifest.get("quality_flags") or []),
        "error": manifest.get("error"),
        "manifest_path": manifest.get("manifest_path"),
        "data_path": manifest.get("data_path"),
    }


def _manifest_formal_ready(manifest: dict[str, Any] | None, trade_date: str) -> bool:
    if not manifest:
        return False
    return (
        str(manifest.get("status") or "").lower() == "ok"
        and str(manifest.get("trade_date") or "") == trade_date
        and bool(manifest.get("source_authority_ready"))
        and bool(manifest.get("formal_decision_allowed"))
        and bool(manifest.get("payload_hash"))
    )


def _effective_index_batch_limit(provider_name: str, requested_limit: int | None, pending_count: int) -> int:
    if pending_count <= 0:
        return 0
    if requested_limit is not None:
        if requested_limit <= 0:
            return pending_count
        return min(int(requested_limit), pending_count)
    if str(provider_name or "").strip().lower() == "tushare":
        return min(1, pending_count)
    return pending_count


def _formal_refresh_outcome(
    *,
    errors: list[str],
    hard_failures: list[dict[str, Any]],
    deferred: list[dict[str, Any]],
) -> dict[str, Any]:
    ok = not errors and not hard_failures
    complete = ok and not deferred
    return {
        "ok": ok,
        "complete": complete,
        "partial_ok": bool(ok and deferred),
        "status": "success" if complete else "partial" if ok else "failed",
    }


def _append_gateway_result_preserving_existing(
    results: list[dict[str, Any]],
    *,
    gateway_result: Any,
    existing: dict[str, Any] | None,
    trade_date: str,
) -> None:
    summary = result_summary(gateway_result)
    if _manifest_formal_ready(existing, trade_date) and (
        summary.get("status") != "ok" or not summary.get("formal_decision_allowed")
    ):
        restored = _manifest_summary(dict(existing or {}))
        restored["reused_existing"] = True
        restored["skip_reason"] = "restored_after_refresh_failure"
        restored["refresh_attempt_error"] = summary.get("error")
        restored["refresh_attempt_quality_flags"] = summary.get("quality_flags") or []
        results.append(restored)
        return
    results.append(summary)


def _run_step(
    results: list[dict[str, Any]],
    errors: list[str],
    name: str,
    callback: Any,
    *,
    repository: Any,
    dataset: str,
    key: str,
    trade_date: str,
    reuse_existing: bool,
) -> None:
    existing = repository.load_manifest(dataset, trade_date, key) if repository is not None else None
    if reuse_existing and _manifest_formal_ready(existing, trade_date):
        summary = _manifest_summary(dict(existing or {}))
        summary["reused_existing"] = True
        summary["skip_reason"] = "existing_formal_ready"
        results.append(summary)
        return
    try:
        summary = result_summary(callback())
        if _manifest_formal_ready(existing, trade_date) and (
            summary.get("status") != "ok" or not summary.get("formal_decision_allowed")
        ):
            repository.save_manifest(dataset, trade_date, key, dict(existing or {}))
            restored = _manifest_summary(dict(existing or {}))
            restored["reused_existing"] = True
            restored["skip_reason"] = "restored_after_refresh_failure"
            restored["refresh_attempt_error"] = summary.get("error")
            restored["refresh_attempt_quality_flags"] = summary.get("quality_flags") or []
            results.append(restored)
            return
        results.append(summary)
    except Exception as exc:
        errors.append(f"{name}:{exc}")


def _configure_tushare_refresh_defaults(args: argparse.Namespace) -> None:
    if str(args.provider or "").strip().lower() != "tushare":
        return
    os.environ.setdefault("PRISM_TUSHARE_MIN_INTERVAL_SECONDS", str(max(args.tushare_min_interval_seconds, 0.0)))
    os.environ.setdefault("PRISM_TUSHARE_RATE_LIMIT_RETRY_SECONDS", str(max(args.tushare_rate_limit_retry_seconds, 0.0)))
    os.environ.setdefault("PRISM_TUSHARE_REQUEST_CACHE_SECONDS", str(max(args.tushare_request_cache_seconds, 0.0)))
    os.environ.setdefault("PRISM_TUSHARE_THROTTLED_APIS", "index_daily,stk_limit,adj_factor")


def _load_existing_dataset(repository: Any, dataset: str, trade_date: str, key: str) -> Any:
    if repository is None:
        return None
    data, manifest = repository.load_dataset(dataset, trade_date, key)
    if not _manifest_formal_ready(manifest, trade_date):
        return None
    return data


def _index_key(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())[:6]


def _stock_ts_code(value: Any) -> str:
    digits = digits_code(value)
    if digits.startswith(("5", "6", "9")):
        suffix = "SH"
    elif digits.startswith(("4", "8")):
        suffix = "BJ"
    else:
        suffix = "SZ"
    return f"{digits}.{suffix}"


def _index_rows_for_symbol(rows: Any, symbol: str) -> list[dict[str, Any]]:
    symbol_key = _index_key(symbol)
    if not symbol_key or not isinstance(rows, list):
        return []
    output = [
        dict(row)
        for row in rows
        if isinstance(row, dict)
        and _index_key(row.get("ts_code") or row.get("symbol")) == symbol_key
    ]
    output.sort(key=lambda item: str(item.get("trade_date") or ""))
    return output


def _missing_index_result(batch_result: ProviderResult, symbol: str, trade_date: str) -> ProviderResult:
    flags = list(batch_result.quality_flags or [])
    if "index_daily_batch_missing_symbol" not in flags:
        flags.append("index_daily_batch_missing_symbol")
    return ProviderResult(
        status=DatasetStatus.UNAVAILABLE,
        data=None,
        provider=batch_result.provider,
        provider_role=batch_result.provider_role,
        dataset="benchmark.index_daily",
        trade_date=trade_date,
        fetched_at=batch_result.fetched_at,
        ttl_seconds=batch_result.ttl_seconds,
        error=f"Tushare index_daily batch missing {symbol}",
        source_endpoint=batch_result.source_endpoint,
        params_hash=batch_result.params_hash,
        payload_hash=batch_result.payload_hash,
        row_count=0,
        quality_flags=flags,
        license_scope=batch_result.license_scope,
        live_small_allowed=False,
        request_key=symbol,
        extra=dict(batch_result.extra or {}),
    )


def _split_index_batch_result(batch_result: ProviderResult, symbol: str, rows: list[dict[str, Any]], trade_date: str) -> ProviderResult:
    if not rows:
        return _missing_index_result(batch_result, symbol, trade_date)
    latest_trade_date = str(rows[-1].get("trade_date") or trade_date)
    quality_flags = [
        flag
        for flag in list(batch_result.quality_flags or [])
        if flag not in {"index_daily_batch_missing_symbols", "index_daily_batch_partial_errors"}
    ]
    return replace(
        batch_result,
        data=rows,
        dataset="benchmark.index_daily",
        trade_date=latest_trade_date,
        row_count=len(rows),
        payload_hash=hash_payload(rows),
        quality_flags=quality_flags,
        live_small_allowed=not quality_flags,
        request_key=symbol,
    )


def _adjustment_rows_for_code(rows: Any, code: str) -> list[dict[str, Any]]:
    target_ts_code = _stock_ts_code(code)
    if not isinstance(rows, list):
        return []
    output = [
        dict(row)
        for row in rows
        if isinstance(row, dict)
        and str(row.get("ts_code") or "").strip().upper() == target_ts_code
    ]
    output.sort(key=lambda item: str(item.get("trade_date") or ""))
    return output


def _missing_adjustment_result(batch_result: ProviderResult, code: str, trade_date: str) -> ProviderResult:
    flags = list(batch_result.quality_flags or [])
    if "adj_factor_cross_section_missing_symbol" not in flags:
        flags.append("adj_factor_cross_section_missing_symbol")
    return ProviderResult(
        status=DatasetStatus.UNAVAILABLE,
        data=None,
        provider=batch_result.provider,
        provider_role=batch_result.provider_role,
        dataset="adjustment.factor",
        trade_date=trade_date,
        fetched_at=batch_result.fetched_at,
        ttl_seconds=batch_result.ttl_seconds,
        error=f"Tushare adj_factor cross section missing {_stock_ts_code(code)}",
        source_endpoint=batch_result.source_endpoint,
        params_hash=batch_result.params_hash,
        payload_hash=batch_result.payload_hash,
        row_count=0,
        quality_flags=flags,
        license_scope=batch_result.license_scope,
        live_small_allowed=False,
        request_key=code,
        extra=dict(batch_result.extra or {}),
    )


def _split_adjustment_cross_section_result(
    batch_result: ProviderResult,
    code: str,
    rows: list[dict[str, Any]],
    trade_date: str,
) -> ProviderResult:
    if not rows:
        return _missing_adjustment_result(batch_result, code, trade_date)
    latest_trade_date = str(rows[-1].get("trade_date") or trade_date)
    return replace(
        batch_result,
        data=rows,
        dataset="adjustment.factor",
        trade_date=latest_trade_date,
        row_count=len(rows),
        payload_hash=hash_payload(rows),
        request_key=code,
    )


def _run_adjustment_factor_batch(
    results: list[dict[str, Any]],
    errors: list[str],
    *,
    gateway: Any,
    repository: Any,
    codes: list[str],
    trade_date: str,
    start_date: str,
    provider_name: str,
    reuse_existing: bool,
) -> None:
    pending: list[str] = []
    existing_by_code: dict[str, dict[str, Any] | None] = {}
    for code in codes:
        existing = repository.load_manifest("adjustment.factor", trade_date, code) if repository is not None else None
        existing_by_code[code] = dict(existing or {}) if existing else None
        if reuse_existing and _manifest_formal_ready(existing, trade_date):
            summary = _manifest_summary(dict(existing or {}))
            summary["reused_existing"] = True
            summary["skip_reason"] = "existing_formal_ready"
            results.append(summary)
            continue
        pending.append(code)

    if not pending:
        return

    provider = gateway.providers.get(provider_name)
    if len(pending) <= 1 or provider is None or not hasattr(provider, "fetch_adjustment_factor_cross_section"):
        for code in pending:
            _run_step(
                results,
                errors,
                f"adjustment.factor:{code}",
                lambda code=code: gateway.fetch_adjustment_factor(
                    code,
                    trade_date=trade_date,
                    start_date=start_date,
                    end_date=trade_date,
                    key=code,
                    allow_fallback=False,
                    provider_name=provider_name,
                ),
                repository=repository,
                dataset="adjustment.factor",
                key=code,
                trade_date=trade_date,
                reuse_existing=False,
            )
        return

    try:
        batch_result = provider.fetch_adjustment_factor_cross_section(trade_date=trade_date)
        batch_result.dataset = "adjustment.factor"
        batch_result.provider = provider_name
        batch_result.provider_role = ProviderRole.PRIMARY
        batch_result.request_key = f"cross-section-{trade_date}"
        if not batch_result.payload_hash:
            batch_result.payload_hash = hash_payload(batch_result.data)
        if not batch_result.row_count:
            batch_result.row_count = len(batch_result.data) if isinstance(batch_result.data, list) else int(batch_result.data is not None)
        batch_result.ttl_seconds = gateway._effective_ttl_seconds(batch_result.dataset, batch_result.ttl_seconds)

        for code in pending:
            if batch_result.status == DatasetStatus.OK:
                code_rows = _adjustment_rows_for_code(batch_result.data, code)
                split_result = _split_adjustment_cross_section_result(batch_result, code, code_rows, trade_date)
            else:
                split_result = replace(batch_result, data=None, row_count=0, request_key=code)
            gateway_result = gateway._finalize(
                request_key=code,
                expected_trade_date=trade_date,
                result=split_result,
                attempt_manifest_paths=[],
            )
            _append_gateway_result_preserving_existing(
                results,
                gateway_result=gateway_result,
                existing=existing_by_code.get(code),
                trade_date=trade_date,
            )
    except Exception as exc:
        errors.append(f"adjustment.factor_cross_section:{exc}")


def _run_index_daily_batch(
    results: list[dict[str, Any]],
    errors: list[str],
    *,
    gateway: Any,
    repository: Any,
    indexes: list[str],
    trade_date: str,
    start_date: str,
    provider_name: str,
    reuse_existing: bool,
    index_batch_limit: int | None,
    deferred: list[dict[str, Any]],
) -> None:
    pending: list[str] = []
    existing_by_symbol: dict[str, dict[str, Any] | None] = {}
    for symbol in indexes:
        existing = repository.load_manifest("benchmark.index_daily", trade_date, symbol) if repository is not None else None
        existing_by_symbol[symbol] = dict(existing or {}) if existing else None
        if reuse_existing and _manifest_formal_ready(existing, trade_date):
            summary = _manifest_summary(dict(existing or {}))
            summary["reused_existing"] = True
            summary["skip_reason"] = "existing_formal_ready"
            results.append(summary)
            continue
        pending.append(symbol)

    if not pending:
        return

    limit = _effective_index_batch_limit(provider_name, index_batch_limit, len(pending))
    refresh_symbols = pending[:limit]
    deferred_symbols = pending[limit:]
    for symbol in deferred_symbols:
        deferred.append({
            "dataset": "benchmark.index_daily",
            "request_key": symbol,
            "trade_date": trade_date,
            "reason": "index_daily_hourly_rate_limit_window",
            "provider": provider_name,
        })

    if not refresh_symbols:
        return

    provider = gateway.providers.get(provider_name)
    if provider is None or not hasattr(provider, "fetch_index_daily_batch"):
        for symbol in refresh_symbols:
            _run_step(
                results,
                errors,
                f"benchmark.index_daily:{symbol}",
                lambda symbol=symbol: gateway.fetch_index_daily(
                    symbol,
                    trade_date=trade_date,
                    start_date=start_date,
                    end_date=trade_date,
                    key=symbol,
                    allow_fallback=False,
                    provider_name=provider_name,
                ),
                repository=repository,
                dataset="benchmark.index_daily",
                key=symbol,
                trade_date=trade_date,
                reuse_existing=False,
            )
        return

    try:
        batch_result = provider.fetch_index_daily_batch(
            refresh_symbols,
            trade_date=trade_date,
            start_date=start_date,
            end_date=trade_date,
        )
        batch_result.dataset = "benchmark.index_daily"
        batch_result.provider = provider_name
        batch_result.provider_role = ProviderRole.PRIMARY
        batch_result.request_key = f"batch-{hash_payload(sorted(refresh_symbols))[:12]}"
        if not batch_result.payload_hash:
            batch_result.payload_hash = hash_payload(batch_result.data)
        if not batch_result.row_count:
            batch_result.row_count = len(batch_result.data) if isinstance(batch_result.data, list) else int(batch_result.data is not None)
        batch_result.ttl_seconds = gateway._effective_ttl_seconds(batch_result.dataset, batch_result.ttl_seconds)

        for symbol in refresh_symbols:
            if batch_result.status == DatasetStatus.OK:
                symbol_rows = _index_rows_for_symbol(batch_result.data, symbol)
                symbol_result = _split_index_batch_result(batch_result, symbol, symbol_rows, trade_date)
            else:
                symbol_result = replace(batch_result, data=None, row_count=0, request_key=symbol)
            gateway_result = gateway._finalize(
                request_key=symbol,
                expected_trade_date=trade_date,
                result=symbol_result,
                attempt_manifest_paths=[],
            )
            _append_gateway_result_preserving_existing(
                results,
                gateway_result=gateway_result,
                existing=existing_by_symbol.get(symbol),
                trade_date=trade_date,
            )
    except Exception as exc:
        errors.append(f"benchmark.index_daily_batch:{exc}")


def main() -> int:
    args = parse_args()
    _configure_tushare_refresh_defaults(args)
    run_now = datetime.now()
    trade_date = _dash_date(args.date.strip() or expected_trade_date())
    start_date = _dash_date(args.start_date.strip()) if args.start_date.strip() else ""
    requested = {item.strip() for item in args.datasets.split(",") if item.strip()} if args.datasets != "all" else set(FORMAL_DATASETS)
    codes = resolve_codes(args.codes, args.limit)
    indexes = _dedupe([item.strip() for item in args.indexes.split(",") if item.strip()])
    gateway = get_data_gateway()
    repository = gateway.repository
    reuse_existing = not args.refresh_existing
    dataset_trade_dates = {
        dataset: formal_reference_trade_date(dataset, expected_date=trade_date, now=run_now)
        for dataset in requested
    }
    dataset_start_dates = {
        dataset: (_dash_date(start_date) if start_date else _default_start_date(dataset_trade_dates[dataset], args.bars_count))
        for dataset in requested
    }
    price_limit_rows = _load_existing_dataset(
        repository,
        "price_limit.daily",
        dataset_trade_dates.get("price_limit.daily", trade_date),
        "formal-price-limit",
    )
    started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    deferred: list[dict[str, Any]] = []

    if "trade_calendar" in requested:
        dataset_trade_date = dataset_trade_dates["trade_calendar"]
        _run_step(
            results,
            errors,
            "trade_calendar",
            lambda: gateway.fetch_trade_calendar(
                trade_date=dataset_trade_date,
                start_date=dataset_trade_date,
                end_date=dataset_trade_date,
                key="formal-calendar",
                allow_fallback=False,
                provider_name=args.provider,
            ),
            repository=repository,
            dataset="trade_calendar",
            key="formal-calendar",
            trade_date=dataset_trade_date,
            reuse_existing=reuse_existing,
        )

    if "bars.daily" in requested:
        dataset_trade_date = dataset_trade_dates["bars.daily"]
        dataset_start_date = dataset_start_dates["bars.daily"]
        for code in codes:
            _run_step(
                results,
                errors,
                f"bars.daily:{code}",
                lambda code=code: gateway.fetch_kline(
                    code,
                    trade_date=dataset_trade_date,
                    start_date=dataset_start_date,
                    end_date=dataset_trade_date,
                    count=args.bars_count,
                    key=code,
                    allow_fallback=False,
                    provider_name=args.provider,
                ),
                repository=repository,
                dataset="bars.daily",
                key=code,
                trade_date=dataset_trade_date,
                reuse_existing=reuse_existing,
            )

    if "adjustment.factor" in requested:
        dataset_trade_date = dataset_trade_dates["adjustment.factor"]
        dataset_start_date = dataset_start_dates["adjustment.factor"]
        _run_adjustment_factor_batch(
            results,
            errors,
            gateway=gateway,
            repository=repository,
            codes=codes,
            trade_date=dataset_trade_date,
            start_date=dataset_start_date,
            provider_name=args.provider,
            reuse_existing=reuse_existing,
        )

    if "benchmark.index_daily" in requested:
        dataset_trade_date = dataset_trade_dates["benchmark.index_daily"]
        dataset_start_date = dataset_start_dates["benchmark.index_daily"]
        _run_index_daily_batch(
            results,
            errors,
            gateway=gateway,
            repository=repository,
            indexes=indexes,
            trade_date=dataset_trade_date,
            start_date=dataset_start_date,
            provider_name=args.provider,
            reuse_existing=reuse_existing,
            index_batch_limit=args.index_batch_limit,
            deferred=deferred,
        )

    if "price_limit.daily" in requested:
        dataset_trade_date = dataset_trade_dates["price_limit.daily"]
        _run_step(
            results,
            errors,
            "price_limit.daily",
            lambda: gateway.fetch_price_limit(
                trade_date=dataset_trade_date,
                key="formal-price-limit",
                allow_fallback=False,
                provider_name=args.provider,
            ),
            repository=repository,
            dataset="price_limit.daily",
            key="formal-price-limit",
            trade_date=dataset_trade_date,
            reuse_existing=reuse_existing,
        )
        price_limit_rows = _load_existing_dataset(
            repository,
            "price_limit.daily",
            dataset_trade_date,
            "formal-price-limit",
        )

    if "execution.flags" in requested:
        dataset_trade_date = dataset_trade_dates["execution.flags"]
        _run_step(
            results,
            errors,
            "execution.flags",
            lambda: gateway.fetch_execution_flags(
                trade_date=dataset_trade_date,
                codes=codes,
                price_limit_rows=price_limit_rows,
                key="formal-execution-flags",
                allow_fallback=False,
                provider_name=args.provider,
            ),
            repository=repository,
            dataset="execution.flags",
            key="formal-execution-flags",
            trade_date=dataset_trade_date,
            reuse_existing=reuse_existing,
        )

    hard_failures = [
        item
        for item in results
        if item.get("status") != "ok" or not item.get("formal_decision_allowed")
    ]
    outcome = _formal_refresh_outcome(errors=errors, hard_failures=hard_failures, deferred=deferred)
    payload = {
        **outcome,
        "provider": args.provider,
        "trade_date": trade_date,
        "start_date": start_date,
        "dataset_trade_dates": dataset_trade_dates,
        "datasets": sorted(requested),
        "codes": codes,
        "indexes": indexes,
        "started_at": started_at,
        "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "results": results,
        "errors": errors,
        "deferred_refreshes": deferred,
        "failed_or_not_formal": hard_failures,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
