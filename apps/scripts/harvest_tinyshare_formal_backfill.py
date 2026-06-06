#!/usr/bin/env python3
"""One-off Tinyshare harvest for Prism formal datasets.

Tinyshare is a Tushare-compatible proxy SDK. This script intentionally keeps it
out of the long-lived Prism provider path and uses it only to backfill local
formal manifests while a short-lived authorization code is valid.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_ROOT = REPO_ROOT / "packages"
CONTROL_PANEL_ROOT = REPO_ROOT / "apps" / "control-panel"
for path in (PACKAGES_ROOT, CONTROL_PANEL_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from prism_data.contracts import DatasetStatus  # noqa: E402
from prism_data.env import load_project_env  # noqa: E402
from prism_data.providers.common import BaseProvider, today_str  # noqa: E402
from prism_data.providers.tushare import (  # noqa: E402
    _compact_date,
    _dash_date,
    _float_or_none,
    _index_ts_code,
    _int_or_none,
    _prism_stock_code,
    _stock_ts_code,
    _unique_stock_ts_codes,
    _window_start,
)
from prism_data.service import get_data_gateway  # noqa: E402
from prism_data.utils import digits_code, hash_payload  # noqa: E402
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
TOKEN_ENV_NAMES = (
    "PRISM_TINYSHARE_TOKEN",
    "TINYSHARE_TOKEN",
    "PRISM_TUSHARE_TOKEN",
    "TUSHARE_TOKEN",
)
TINYSHARE_ENDPOINT = "tinyshare://pro_api"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Harvest formal Prism datasets through the Tinyshare SDK")
    parser.add_argument("--date", default="", help="Expected trade date. Defaults to Prism expected trade date.")
    parser.add_argument("--start-date", default="", help="Optional start date for daily windows.")
    parser.add_argument("--end-date", default="", help="Optional end date. Defaults to --date.")
    parser.add_argument("--codes", default="", help="Comma-separated stock codes. Defaults to active watchlist.")
    parser.add_argument("--indexes", default=",".join(DEFAULT_INDEXES), help="Comma-separated index symbols.")
    parser.add_argument("--datasets", default="all", help="Comma-separated datasets or all.")
    parser.add_argument("--execution-key", default="formal-execution-flags", help="Repository key for execution.flags.")
    parser.add_argument(
        "--adj-factor-mode",
        choices=("cross-section", "history"),
        default="cross-section",
        help="Use one trade-date cross-section call or per-code history windows for adjustment.factor.",
    )
    parser.add_argument("--limit", type=int, default=40, help="Maximum stock codes to refresh.")
    parser.add_argument("--bars-count", type=int, default=120)
    parser.add_argument(
        "--refresh-existing",
        action="store_true",
        help="Refresh keys even when a formal-ready manifest already exists.",
    )
    return parser.parse_args()


def _date_digits(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())[:8]


def _default_start_date(end_date: str, bars_count: int) -> str:
    end = datetime.strptime(_date_digits(end_date), "%Y%m%d")
    return (end - timedelta(days=max(30, int(bars_count or 120) * 2))).strftime("%Y-%m-%d")


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        value = str(item or "").strip()
        if value and value not in out:
            out.append(value)
    return out


def _resolve_codes(raw: str, limit: int) -> list[str]:
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
    return normalized[: max(int(limit or 1), 1)]


def _resolve_token() -> tuple[str, str]:
    load_project_env(root=REPO_ROOT)
    for name in TOKEN_ENV_NAMES:
        value = os.environ.get(name, "").strip()
        if value:
            return value, name
    return "", ""


def _redact_secret(message: Any, secret: str) -> str:
    text = str(message or "")
    if secret:
        text = text.replace(secret, "[redacted]")
    return text


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
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


def _records_from_frame(frame: Any) -> list[dict[str, Any]]:
    if frame is None:
        return []
    if isinstance(frame, dict):
        data = frame.get("data") if "data" in frame else frame
        if isinstance(data, list):
            return [dict(_json_safe(item)) for item in data if isinstance(item, dict)]
        if isinstance(data, dict) and isinstance(data.get("items"), list) and isinstance(data.get("fields"), list):
            fields = [str(item) for item in data.get("fields") or []]
            return [
                {
                    field: _json_safe(item[index] if index < len(item) else None)
                    for index, field in enumerate(fields)
                }
                for item in data.get("items") or []
                if isinstance(item, list)
            ]
        return [dict(_json_safe(data))]
    if isinstance(frame, list):
        return [dict(_json_safe(item)) for item in frame if isinstance(item, dict)]
    if hasattr(frame, "to_dict"):
        records = frame.to_dict(orient="records")
        return [dict(_json_safe(item)) for item in records if isinstance(item, dict)]
    return []


def _classify_error(message: str) -> tuple[DatasetStatus, list[str]]:
    lowered = message.lower()
    if "token" in lowered or "授权" in message or "认证" in message:
        return DatasetStatus.UNAVAILABLE, ["provider_token_invalid"]
    rate_tokens = ("频率", "调用频次", "rate limit", "frequency", "too many")
    if any(token in message or token in lowered for token in rate_tokens):
        return DatasetStatus.UNAVAILABLE, ["provider_rate_limited"]
    permission_tokens = ("权限", "积分", "permission", "points", "credits", "无权限")
    if any(token in message or token in lowered for token in permission_tokens):
        return DatasetStatus.UNAVAILABLE, ["provider_permission_or_points_blocked"]
    return DatasetStatus.FAILED, ["tinyshare_fetch_failed"]


class TinyshareBackfillProvider(BaseProvider):
    provider_name = "tushare"

    def __init__(self, *, token: str, token_env_name: str) -> None:
        super().__init__(timeout=30, retries=0)
        self._token = token.strip()
        self._token_env_name = token_env_name
        if not self._token:
            raise RuntimeError(
                "Tinyshare authorization code missing; set PRISM_TINYSHARE_TOKEN "
                "or TINYSHARE_TOKEN. PRISM_TUSHARE_TOKEN is accepted as a fallback."
            )
        try:
            import tinyshare as ts  # type: ignore
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "tinyshare is not installed in this Python environment. "
                "Run: .venv/bin/python -m pip install tinyshare==0.1028.0"
            ) from exc
        ts.set_token(self._token)
        self._pro = ts.pro_api()

    def _call(
        self,
        api_name: str,
        *,
        params: dict[str, Any],
        fields: str,
    ) -> tuple[list[dict[str, Any]], str, str, str, dict[str, Any] | None]:
        clean_params = {key: value for key, value in params.items() if value not in (None, "")}
        params_hash = hash_payload({
            "api_name": api_name,
            "params": clean_params,
            "fields": fields,
            "token_configured": True,
            "source_proxy": "tinyshare",
        })
        try:
            method = getattr(self._pro, api_name)
            frame = method(**clean_params)
            rows = _records_from_frame(frame)
            payload_hash = hash_payload({"api_name": api_name, "rows": rows})
            return rows, TINYSHARE_ENDPOINT, params_hash, payload_hash, None
        except Exception as exc:
            message = _redact_secret(exc, self._token)
            status, flags = _classify_error(message)
            return [], TINYSHARE_ENDPOINT, params_hash, "", {
                "message": message or f"Tinyshare {api_name} request failed",
                "status": status,
                "quality_flags": flags,
            }

    def _tinyshare_error(
        self,
        *,
        dataset: str,
        trade_date: str,
        api_name: str,
        endpoint: str,
        params_hash: str,
        payload_hash: str,
        error: dict[str, Any],
    ):
        return self._error(
            dataset=dataset,
            trade_date=_dash_date(trade_date) or today_str(),
            error=str(error.get("message") or f"Tinyshare {api_name} unavailable"),
            endpoint=endpoint,
            params_hash=params_hash,
            payload_hash=payload_hash,
            quality_flags=list(error.get("quality_flags") or ["tinyshare_fetch_failed"]),
            status=error.get("status") if isinstance(error.get("status"), DatasetStatus) else DatasetStatus.FAILED,
            license_scope="authorized_tinyshare_proxy",
            extra={
                "source_api": api_name,
                "source_proxy": "tinyshare",
                "authority_provider_override": "tushare",
                "token_env_name": self._token_env_name,
            },
        )

    def _ok_tinyshare(
        self,
        *,
        data: list[dict[str, Any]],
        dataset: str,
        trade_date: str,
        endpoint: str,
        params_hash: str,
        payload_hash: str,
        api_name: str,
        ttl_seconds: int = 86400,
        quality_flags: list[str] | None = None,
        live_small_allowed: bool = True,
    ):
        asof = None
        if trade_date:
            try:
                asof = datetime.strptime(_dash_date(trade_date), "%Y-%m-%d")
            except ValueError:
                asof = None
        return self._ok(
            data=data,
            dataset=dataset,
            trade_date=_dash_date(trade_date) or today_str(),
            endpoint=endpoint,
            params_hash=params_hash,
            payload_hash=payload_hash,
            ttl_seconds=ttl_seconds,
            asof=asof,
            quality_flags=quality_flags,
            live_small_allowed=live_small_allowed,
            license_scope="authorized_tinyshare_proxy",
            extra={
                "source_api": api_name,
                "source_proxy": "tinyshare",
                "authority_provider_override": "tushare",
                "token_env_name": self._token_env_name,
            },
        )

    def fetch_kline(self, code: str, period: str = "daily", count: int = 120, **kwargs: Any):
        if str(period or "daily").lower() not in {"daily", "day", "d"}:
            return self._error(
                dataset="bars.daily",
                trade_date=kwargs.get("trade_date") or today_str(),
                error=f"unsupported Tinyshare kline period: {period}",
            )
        ts_code = _stock_ts_code(code)
        end_date = _compact_date(kwargs.get("end_date") or kwargs.get("trade_date") or today_str())
        start_date = _compact_date(kwargs.get("start_date")) or _window_start(end_date, count)
        rows, endpoint, params_hash, payload_hash, error = self._call(
            "daily",
            params={"ts_code": ts_code, "start_date": start_date, "end_date": end_date},
            fields="ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount",
        )
        if error:
            return self._tinyshare_error(
                dataset="bars.daily",
                trade_date=_dash_date(end_date),
                api_name="daily",
                endpoint=endpoint,
                params_hash=params_hash,
                payload_hash=payload_hash,
                error=error,
            )
        output = []
        for row in rows:
            trade_date = _dash_date(row.get("trade_date"))
            output.append({
                "code": _prism_stock_code(row.get("ts_code")),
                "ts_code": row.get("ts_code"),
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
            })
        output = [item for item in output if item["trade_date"]]
        output.sort(key=lambda item: str(item.get("trade_date") or ""))
        if count and len(output) > count:
            output = output[-int(count):]
        if not output:
            return self._error(
                dataset="bars.daily",
                trade_date=_dash_date(end_date),
                error=f"empty Tinyshare daily for {ts_code}",
                endpoint=endpoint,
                params_hash=params_hash,
                payload_hash=payload_hash,
                license_scope="authorized_tinyshare_proxy",
            )
        return self._ok_tinyshare(
            data=output,
            dataset="bars.daily",
            trade_date=str(output[-1]["trade_date"]),
            endpoint=endpoint,
            params_hash=params_hash,
            payload_hash=payload_hash,
            api_name="daily",
        )

    def fetch_trade_calendar(
        self,
        exchange: str = "SSE",
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: Any,
    ):
        trade_date = _compact_date(kwargs.get("trade_date") or end_date or start_date or today_str())
        start = _compact_date(start_date) or trade_date
        end = _compact_date(end_date) or trade_date
        rows, endpoint, params_hash, payload_hash, error = self._call(
            "trade_cal",
            params={"exchange": str(exchange or "SSE").upper(), "start_date": start, "end_date": end},
            fields="exchange,cal_date,is_open,pretrade_date",
        )
        if error:
            return self._tinyshare_error(
                dataset="trade_calendar",
                trade_date=_dash_date(trade_date),
                api_name="trade_cal",
                endpoint=endpoint,
                params_hash=params_hash,
                payload_hash=payload_hash,
                error=error,
            )
        output = [
            {
                "exchange": row.get("exchange"),
                "cal_date": _dash_date(row.get("cal_date")),
                "trade_date": _dash_date(row.get("cal_date")),
                "is_open": bool(_int_or_none(row.get("is_open"))),
                "is_open_raw": _int_or_none(row.get("is_open")),
                "pretrade_date": _dash_date(row.get("pretrade_date")),
            }
            for row in rows
        ]
        output = [item for item in output if item["cal_date"]]
        output.sort(key=lambda item: str(item.get("cal_date") or ""))
        if not output:
            return self._error(
                dataset="trade_calendar",
                trade_date=_dash_date(trade_date),
                error="empty Tinyshare trade_cal",
                endpoint=endpoint,
                params_hash=params_hash,
                payload_hash=payload_hash,
                license_scope="authorized_tinyshare_proxy",
            )
        return self._ok_tinyshare(
            data=output,
            dataset="trade_calendar",
            trade_date=_dash_date(trade_date),
            endpoint=endpoint,
            params_hash=params_hash,
            payload_hash=payload_hash,
            api_name="trade_cal",
        )

    def fetch_index_daily(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: Any,
    ):
        ts_code = _index_ts_code(symbol)
        end = _compact_date(end_date or kwargs.get("trade_date") or today_str())
        start = _compact_date(start_date) or _window_start(end, int(kwargs.get("count") or 120))
        rows, endpoint, params_hash, payload_hash, error = self._call(
            "index_daily",
            params={"ts_code": ts_code, "start_date": start, "end_date": end},
            fields="ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount",
        )
        if error:
            return self._tinyshare_error(
                dataset="benchmark.index_daily",
                trade_date=_dash_date(end),
                api_name="index_daily",
                endpoint=endpoint,
                params_hash=params_hash,
                payload_hash=payload_hash,
                error=error,
            )
        output = []
        for row in rows:
            trade_date = _dash_date(row.get("trade_date"))
            output.append({
                "symbol": ts_code,
                "ts_code": row.get("ts_code") or ts_code,
                "trade_date": trade_date,
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
        output = [item for item in output if item["trade_date"]]
        output.sort(key=lambda item: str(item.get("trade_date") or ""))
        if not output:
            return self._error(
                dataset="benchmark.index_daily",
                trade_date=_dash_date(end),
                error=f"empty Tinyshare index_daily for {ts_code}",
                endpoint=endpoint,
                params_hash=params_hash,
                payload_hash=payload_hash,
                license_scope="authorized_tinyshare_proxy",
            )
        return self._ok_tinyshare(
            data=output,
            dataset="benchmark.index_daily",
            trade_date=str(output[-1]["trade_date"]),
            endpoint=endpoint,
            params_hash=params_hash,
            payload_hash=payload_hash,
            api_name="index_daily",
        )

    def fetch_adjustment_factor(
        self,
        code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: Any,
    ):
        ts_code = _stock_ts_code(code)
        end = _compact_date(end_date or kwargs.get("trade_date") or today_str())
        start = _compact_date(start_date) or _window_start(end, int(kwargs.get("count") or 120))
        rows, endpoint, params_hash, payload_hash, error = self._call(
            "adj_factor",
            params={"ts_code": ts_code, "start_date": start, "end_date": end},
            fields="ts_code,trade_date,adj_factor",
        )
        if error:
            return self._tinyshare_error(
                dataset="adjustment.factor",
                trade_date=_dash_date(end),
                api_name="adj_factor",
                endpoint=endpoint,
                params_hash=params_hash,
                payload_hash=payload_hash,
                error=error,
            )
        output = [
            {
                "code": _prism_stock_code(row.get("ts_code")),
                "ts_code": row.get("ts_code"),
                "trade_date": _dash_date(row.get("trade_date")),
                "adj_factor": _float_or_none(row.get("adj_factor")),
            }
            for row in rows
        ]
        output = [item for item in output if item["trade_date"]]
        output.sort(key=lambda item: str(item.get("trade_date") or ""))
        if not output:
            return self._error(
                dataset="adjustment.factor",
                trade_date=_dash_date(end),
                error=f"empty Tinyshare adj_factor for {ts_code}",
                endpoint=endpoint,
                params_hash=params_hash,
                payload_hash=payload_hash,
                license_scope="authorized_tinyshare_proxy",
            )
        return self._ok_tinyshare(
            data=output,
            dataset="adjustment.factor",
            trade_date=str(output[-1]["trade_date"]),
            endpoint=endpoint,
            params_hash=params_hash,
            payload_hash=payload_hash,
            api_name="adj_factor",
        )

    def fetch_adjustment_factor_cross_section(self, trade_date: str, **kwargs: Any):
        date = _compact_date(trade_date or kwargs.get("trade_date") or today_str())
        rows, endpoint, params_hash, payload_hash, error = self._call(
            "adj_factor",
            params={"trade_date": date},
            fields="ts_code,trade_date,adj_factor",
        )
        if error:
            return self._tinyshare_error(
                dataset="adjustment.factor",
                trade_date=_dash_date(date),
                api_name="adj_factor",
                endpoint=endpoint,
                params_hash=params_hash,
                payload_hash=payload_hash,
                error=error,
            )
        output = [
            {
                "code": _prism_stock_code(row.get("ts_code")),
                "ts_code": row.get("ts_code"),
                "trade_date": _dash_date(row.get("trade_date")),
                "adj_factor": _float_or_none(row.get("adj_factor")),
            }
            for row in rows
        ]
        output = [item for item in output if item["trade_date"] and item.get("ts_code")]
        output.sort(key=lambda item: (str(item.get("trade_date") or ""), str(item.get("ts_code") or "")))
        if not output:
            return self._error(
                dataset="adjustment.factor",
                trade_date=_dash_date(date),
                error="empty Tinyshare adj_factor cross section",
                endpoint=endpoint,
                params_hash=params_hash,
                payload_hash=payload_hash,
                license_scope="authorized_tinyshare_proxy",
                extra={
                    "source_api": "adj_factor",
                    "source_proxy": "tinyshare",
                    "authority_provider_override": "tushare",
                    "token_env_name": self._token_env_name,
                },
            )
        return self._ok_tinyshare(
            data=output,
            dataset="adjustment.factor",
            trade_date=_dash_date(date),
            endpoint=endpoint,
            params_hash=params_hash,
            payload_hash=payload_hash,
            api_name="adj_factor",
        )

    def fetch_price_limit(self, trade_date: str, code: str | None = None, **kwargs: Any):
        date = _compact_date(trade_date or kwargs.get("trade_date") or today_str())
        ts_code = _stock_ts_code(code) if code else ""
        rows, endpoint, params_hash, payload_hash, error = self._call(
            "stk_limit",
            params={"trade_date": date, "ts_code": ts_code},
            fields="ts_code,trade_date,up_limit,down_limit",
        )
        if error:
            return self._tinyshare_error(
                dataset="price_limit.daily",
                trade_date=_dash_date(date),
                api_name="stk_limit",
                endpoint=endpoint,
                params_hash=params_hash,
                payload_hash=payload_hash,
                error=error,
            )
        output = [
            {
                "code": _prism_stock_code(row.get("ts_code")),
                "ts_code": row.get("ts_code"),
                "trade_date": _dash_date(row.get("trade_date")),
                "up_limit": _float_or_none(row.get("up_limit")),
                "down_limit": _float_or_none(row.get("down_limit")),
            }
            for row in rows
        ]
        output = [item for item in output if item["trade_date"]]
        output.sort(key=lambda item: (str(item.get("trade_date") or ""), str(item.get("ts_code") or "")))
        if not output:
            target = f" for {ts_code}" if ts_code else ""
            return self._error(
                dataset="price_limit.daily",
                trade_date=_dash_date(date),
                error=f"empty Tinyshare stk_limit{target}",
                endpoint=endpoint,
                params_hash=params_hash,
                payload_hash=payload_hash,
                license_scope="authorized_tinyshare_proxy",
            )
        return self._ok_tinyshare(
            data=output,
            dataset="price_limit.daily",
            trade_date=_dash_date(date),
            endpoint=endpoint,
            params_hash=params_hash,
            payload_hash=payload_hash,
            api_name="stk_limit",
        )

    def fetch_execution_flags(self, trade_date: str, codes: list[str] | None = None, **kwargs: Any):
        date = _compact_date(trade_date or kwargs.get("trade_date") or today_str())
        requested = _unique_stock_ts_codes(codes)
        requested_set = set(requested)
        reused_limit_rows = kwargs.get("price_limit_rows")

        if isinstance(reused_limit_rows, list) and reused_limit_rows:
            limit_rows = [dict(row) for row in reused_limit_rows if isinstance(row, dict)]
            endpoint = TINYSHARE_ENDPOINT
            params_hash = hash_payload({
                "api_name": "stk_limit",
                "params": {"trade_date": date},
                "fields": "ts_code,trade_date,up_limit,down_limit",
                "reused_dataset": "price_limit.daily",
                "source_proxy": "tinyshare",
            })
            payload_hash = hash_payload(limit_rows)
        else:
            limit_rows, endpoint, params_hash, payload_hash, error = self._call(
                "stk_limit",
                params={"trade_date": date},
                fields="ts_code,trade_date,up_limit,down_limit",
            )
            if error:
                return self._tinyshare_error(
                    dataset="execution.flags",
                    trade_date=_dash_date(date),
                    api_name="stk_limit",
                    endpoint=endpoint,
                    params_hash=params_hash,
                    payload_hash=payload_hash,
                    error=error,
                )

        suspend_rows, suspend_endpoint, suspend_params_hash, suspend_payload_hash, error = self._call(
            "suspend_d",
            params={"trade_date": date},
            fields="ts_code,trade_date,suspend_timing,suspend_type",
        )
        if error:
            return self._tinyshare_error(
                dataset="execution.flags",
                trade_date=_dash_date(date),
                api_name="suspend_d",
                endpoint=suspend_endpoint,
                params_hash=suspend_params_hash,
                payload_hash=suspend_payload_hash,
                error=error,
            )

        st_rows, st_endpoint, st_params_hash, st_payload_hash, error = self._call(
            "stock_st",
            params={"trade_date": date},
            fields="ts_code,name,trade_date,type,type_name",
        )
        if error:
            return self._tinyshare_error(
                dataset="execution.flags",
                trade_date=_dash_date(date),
                api_name="stock_st",
                endpoint=st_endpoint,
                params_hash=st_params_hash,
                payload_hash=st_payload_hash,
                error=error,
            )

        def include(row: dict[str, Any]) -> bool:
            ts_code = str(row.get("ts_code") or "").strip().upper()
            return bool(ts_code) and (not requested_set or ts_code in requested_set)

        limit_by_code: dict[str, dict[str, Any]] = {
            str(row.get("ts_code") or "").strip().upper(): row
            for row in limit_rows
            if include(row)
        }
        suspend_by_code: dict[str, list[dict[str, Any]]] = {}
        for row in suspend_rows:
            if include(row):
                suspend_by_code.setdefault(str(row.get("ts_code") or "").strip().upper(), []).append(row)
        st_by_code: dict[str, list[dict[str, Any]]] = {}
        for row in st_rows:
            if include(row):
                st_by_code.setdefault(str(row.get("ts_code") or "").strip().upper(), []).append(row)

        symbols = requested or sorted(set(limit_by_code) | set(suspend_by_code) | set(st_by_code))
        output: list[dict[str, Any]] = []
        for ts_code in symbols:
            limit = limit_by_code.get(ts_code, {})
            suspend_items = suspend_by_code.get(ts_code, [])
            st_items = st_by_code.get(ts_code, [])
            is_suspended = any(str(item.get("suspend_type") or "").upper() == "S" for item in suspend_items)
            is_resumed = any(str(item.get("suspend_type") or "").upper() == "R" for item in suspend_items)
            up_limit = _float_or_none(limit.get("up_limit"))
            down_limit = _float_or_none(limit.get("down_limit"))
            output.append({
                "code": _prism_stock_code(ts_code),
                "ts_code": ts_code,
                "trade_date": _dash_date(date),
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
                        "trade_date": _dash_date(item.get("trade_date")),
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
                        "trade_date": _dash_date(item.get("trade_date")),
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

        output.sort(key=lambda item: str(item.get("ts_code") or ""))
        missing_limit_codes = [
            ts_code for ts_code in requested
            if ts_code not in limit_by_code and ts_code not in suspend_by_code
        ]
        quality_flags = []
        if missing_limit_codes:
            quality_flags.append("execution_flags_price_limit_missing")
        if requested and len(output) != len(requested):
            quality_flags.append("execution_flags_code_coverage_mismatch")
        if not output:
            return self._error(
                dataset="execution.flags",
                trade_date=_dash_date(date),
                error="empty Tinyshare execution flags",
                endpoint=endpoint,
                params_hash=params_hash,
                payload_hash=payload_hash,
                license_scope="authorized_tinyshare_proxy",
            )

        combined_payload_hash = hash_payload({
            "stk_limit": payload_hash,
            "suspend_d": suspend_payload_hash,
            "stock_st": st_payload_hash,
        })
        combined_params_hash = hash_payload({
            "trade_date": date,
            "codes": requested,
            "apis": ["stk_limit", "suspend_d", "stock_st"],
            "params_hashes": [params_hash, suspend_params_hash, st_params_hash],
            "source_proxy": "tinyshare",
        })
        return self._ok_tinyshare(
            data=output,
            dataset="execution.flags",
            trade_date=_dash_date(date),
            endpoint=st_endpoint or endpoint,
            params_hash=combined_params_hash,
            payload_hash=combined_payload_hash,
            api_name="execution_flags",
            quality_flags=quality_flags,
            live_small_allowed=not quality_flags,
        )


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
        "authority_flags": list(manifest.get("authority_flags") or []),
        "error": manifest.get("error"),
        "manifest_path": manifest.get("manifest_path"),
        "data_path": manifest.get("data_path"),
        "source_endpoint": manifest.get("source_endpoint"),
        "license_scope": manifest.get("license_scope"),
    }


def _result_summary(result: Any) -> dict[str, Any]:
    return _manifest_summary(dict(getattr(result, "manifest", {}) or {}))


def _gateway_result_from_provider_result(
    gateway: Any,
    provider_result: Any,
    *,
    trade_date: str,
    key: str,
) -> Any:
    provider_result.trade_date = str(getattr(provider_result, "trade_date", "") or trade_date)
    provider_result.request_key = key
    provider_result.provider = "tushare"
    if not getattr(provider_result, "payload_hash", ""):
        provider_result.payload_hash = hash_payload(provider_result.data)
    if not getattr(provider_result, "row_count", 0):
        data = provider_result.data
        provider_result.row_count = len(data) if isinstance(data, (list, tuple, set, dict)) else int(data is not None)
    provider_result.ttl_seconds = gateway._effective_ttl_seconds(
        provider_result.dataset,
        provider_result.ttl_seconds,
    )
    return gateway._finalize(
        request_key=key,
        expected_trade_date=trade_date,
        result=provider_result,
        attempt_manifest_paths=[],
    )


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
        summary = _result_summary(callback())
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


def _load_existing_dataset(repository: Any, dataset: str, trade_date: str, key: str) -> Any:
    if repository is None:
        return None
    data, manifest = repository.load_dataset(dataset, trade_date, key)
    if not _manifest_formal_ready(manifest, trade_date):
        return None
    return data


def main() -> int:
    args = parse_args()
    trade_date = _dash_date(args.date.strip() or expected_trade_date())
    end_date = _dash_date(args.end_date.strip()) if args.end_date.strip() else trade_date
    start_date = _dash_date(args.start_date.strip()) if args.start_date.strip() else _default_start_date(end_date, args.bars_count)
    requested = {item.strip() for item in args.datasets.split(",") if item.strip()} if args.datasets != "all" else set(FORMAL_DATASETS)
    unknown = sorted(requested.difference(FORMAL_DATASETS))
    if unknown:
        print(json.dumps({"ok": False, "errors": [f"unknown datasets: {','.join(unknown)}"]}, ensure_ascii=False, indent=2))
        return 2

    token, token_env_name = _resolve_token()
    try:
        provider = TinyshareBackfillProvider(token=token, token_env_name=token_env_name)
    except RuntimeError as exc:
        print(json.dumps({"ok": False, "errors": [_redact_secret(exc, token)]}, ensure_ascii=False, indent=2))
        return 2

    codes = _resolve_codes(args.codes, args.limit)
    indexes = _dedupe([item.strip() for item in args.indexes.split(",") if item.strip()])
    gateway = get_data_gateway()
    gateway.providers["tushare"] = provider
    repository = gateway.repository
    reuse_existing = not args.refresh_existing
    price_limit_rows = _load_existing_dataset(repository, "price_limit.daily", trade_date, "formal-price-limit")
    started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    results: list[dict[str, Any]] = []
    errors: list[str] = []

    if "trade_calendar" in requested:
        _run_step(
            results,
            errors,
            "trade_calendar",
            lambda: gateway.fetch_trade_calendar(
                trade_date=trade_date,
                start_date=trade_date,
                end_date=trade_date,
                key="formal-calendar",
                allow_fallback=False,
                provider_name="tushare",
            ),
            repository=repository,
            dataset="trade_calendar",
            key="formal-calendar",
            trade_date=trade_date,
            reuse_existing=reuse_existing,
        )

    if "bars.daily" in requested:
        for code in codes:
            _run_step(
                results,
                errors,
                f"bars.daily:{code}",
                lambda code=code: gateway.fetch_kline(
                    code,
                    trade_date=trade_date,
                    start_date=start_date,
                    end_date=end_date,
                    count=args.bars_count,
                    key=code,
                    allow_fallback=False,
                    provider_name="tushare",
                ),
                repository=repository,
                dataset="bars.daily",
                key=code,
                trade_date=trade_date,
                reuse_existing=reuse_existing,
            )

    if "adjustment.factor" in requested:
        pending_adj_codes = [
            code for code in codes
            if not (
                reuse_existing
                and _manifest_formal_ready(
                    repository.load_manifest("adjustment.factor", trade_date, code),
                    trade_date,
                )
            )
        ]
        if len(pending_adj_codes) > 1 and args.adj_factor_mode != "history":
            cross_section = provider.fetch_adjustment_factor_cross_section(trade_date=trade_date)
            rows_by_ts_code: dict[str, list[dict[str, Any]]] = {}
            for row in cross_section.data or []:
                ts_code = str(row.get("ts_code") or "").strip().upper()
                if ts_code:
                    rows_by_ts_code.setdefault(ts_code, []).append(dict(row))
            for code in pending_adj_codes:
                ts_code = _stock_ts_code(code)
                rows = rows_by_ts_code.get(ts_code, [])
                if rows:
                    split_result = provider._ok_tinyshare(
                        data=rows,
                        dataset="adjustment.factor",
                        trade_date=str(rows[-1].get("trade_date") or trade_date),
                        endpoint=cross_section.source_endpoint,
                        params_hash=cross_section.params_hash,
                        payload_hash=hash_payload(rows),
                        api_name="adj_factor",
                    )
                else:
                    split_result = provider._error(
                        dataset="adjustment.factor",
                        trade_date=trade_date,
                        error=cross_section.error or f"Tinyshare adj_factor missing {ts_code}",
                        endpoint=cross_section.source_endpoint,
                        params_hash=cross_section.params_hash,
                        payload_hash=cross_section.payload_hash,
                        quality_flags=list(cross_section.quality_flags or ["adj_factor_cross_section_missing_symbol"]),
                        status=cross_section.status,
                        license_scope=cross_section.license_scope,
                        extra=dict(cross_section.extra or {}),
                    )
                summary = _result_summary(
                    _gateway_result_from_provider_result(
                        gateway,
                        split_result,
                        trade_date=trade_date,
                        key=code,
                    )
                )
                results.append(summary)
            if reuse_existing:
                for code in codes:
                    if code in pending_adj_codes:
                        continue
                    manifest = repository.load_manifest("adjustment.factor", trade_date, code)
                    summary = _manifest_summary(dict(manifest or {}))
                    summary["reused_existing"] = True
                    summary["skip_reason"] = "existing_formal_ready"
                    results.append(summary)
        else:
            for code in codes:
                _run_step(
                    results,
                    errors,
                    f"adjustment.factor:{code}",
                    lambda code=code: gateway.fetch_adjustment_factor(
                        code,
                        trade_date=trade_date,
                        start_date=start_date,
                        end_date=end_date,
                        key=code,
                        allow_fallback=False,
                        provider_name="tushare",
                    ),
                    repository=repository,
                    dataset="adjustment.factor",
                    key=code,
                    trade_date=trade_date,
                    reuse_existing=reuse_existing,
                )

    if "benchmark.index_daily" in requested:
        for symbol in indexes:
            _run_step(
                results,
                errors,
                f"benchmark.index_daily:{symbol}",
                lambda symbol=symbol: gateway.fetch_index_daily(
                    symbol,
                    trade_date=trade_date,
                    start_date=start_date,
                    end_date=end_date,
                    key=symbol,
                    allow_fallback=False,
                    provider_name="tushare",
                ),
                repository=repository,
                dataset="benchmark.index_daily",
                key=symbol,
                trade_date=trade_date,
                reuse_existing=reuse_existing,
            )

    if "price_limit.daily" in requested:
        _run_step(
            results,
            errors,
            "price_limit.daily",
            lambda: gateway.fetch_price_limit(
                trade_date=trade_date,
                key="formal-price-limit",
                allow_fallback=False,
                provider_name="tushare",
            ),
            repository=repository,
            dataset="price_limit.daily",
            key="formal-price-limit",
            trade_date=trade_date,
            reuse_existing=reuse_existing,
        )
        price_limit_rows = _load_existing_dataset(repository, "price_limit.daily", trade_date, "formal-price-limit")

    if "execution.flags" in requested:
        _run_step(
            results,
            errors,
            "execution.flags",
            lambda: gateway.fetch_execution_flags(
                trade_date=trade_date,
                codes=codes,
                price_limit_rows=price_limit_rows,
                key=args.execution_key,
                allow_fallback=False,
                provider_name="tushare",
            ),
            repository=repository,
            dataset="execution.flags",
            key=args.execution_key,
            trade_date=trade_date,
            reuse_existing=reuse_existing,
        )

    hard_failures = [
        item
        for item in results
        if item.get("status") != "ok" or not item.get("formal_decision_allowed")
    ]
    payload = {
        "ok": not errors and not hard_failures,
        "provider": "tinyshare-as-tushare",
        "trade_date": trade_date,
        "start_date": start_date,
        "end_date": end_date,
        "datasets": sorted(requested),
        "codes": codes,
        "indexes": indexes,
        "token_env_name": token_env_name,
        "token_value_visible": False,
        "started_at": started_at,
        "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "results": results,
        "errors": errors,
        "failed_or_not_formal": hard_failures,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
