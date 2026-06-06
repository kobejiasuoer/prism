"""Tushare Pro provider adapter.

The adapter uses the public Tushare Pro HTTP shape directly instead of
requiring the optional SDK. Tokens are read only from the process
environment or the local gitignored project ``.env`` file (or an explicit
constructor argument in tests) and are never included in params hashes,
logs, manifests, or raised errors.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import os
import re
import threading
import time
from typing import Any

from prism_data.contracts import DatasetStatus, ProviderResult
from prism_data.env import configured_env_names, load_project_env
from prism_data.providers.common import BaseProvider, redact_endpoint, today_str
from prism_data.repositories import DatasetRepository
from prism_data.utils import default_dataset_repository_root, hash_payload


_DEFAULT_API_URL = "http://api.tushare.pro"
_TOKEN_ENV_NAMES = ("PRISM_TUSHARE_TOKEN", "TUSHARE_TOKEN")
_DEFAULT_THROTTLED_APIS = ("index_daily", "stk_limit")


def _env_float(name: str, fallback: float) -> float:
    value = os.environ.get(name, "").strip()
    if not value:
        return fallback
    try:
        return max(float(value), 0.0)
    except ValueError:
        return fallback


def _csv_env(name: str, fallback: tuple[str, ...]) -> set[str]:
    value = os.environ.get(name, "").strip()
    if not value:
        return set(fallback)
    return {
        item.strip()
        for item in value.split(",")
        if item.strip()
    }


def _compact_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits[:8]


def _dash_date(value: Any) -> str:
    digits = _compact_date(value)
    if len(digits) != 8:
        return str(value or "").strip()
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _window_start(end_date: str, count: int) -> str:
    end_digits = _compact_date(end_date)
    if len(end_digits) != 8:
        return ""
    end = datetime.strptime(end_digits, "%Y%m%d")
    lookback_days = max(30, int(count or 120) * 2)
    return (end - timedelta(days=lookback_days)).strftime("%Y%m%d")


def _stock_ts_code(code: Any) -> str:
    text = str(code or "").strip().upper()
    if re.fullmatch(r"\d{6}\.(SH|SZ|BJ)", text):
        return text
    compact = text.lower()
    if re.fullmatch(r"(sh|sz|bj)\d{6}", compact):
        market = compact[:2].upper()
        return f"{compact[2:]}.{market}"
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) != 6:
        raise ValueError(f"invalid stock code for Tushare: {code!r}")
    if digits.startswith(("5", "6", "9")):
        suffix = "SH"
    elif digits.startswith(("4", "8")):
        suffix = "BJ"
    else:
        suffix = "SZ"
    return f"{digits}.{suffix}"


def _prism_stock_code(ts_code: Any) -> str:
    text = str(ts_code or "").strip().upper()
    match = re.fullmatch(r"(\d{6})\.(SH|SZ|BJ)", text)
    if not match:
        return str(ts_code or "").strip().lower()
    digits, market = match.groups()
    prefix = {"SH": "sh", "SZ": "sz", "BJ": "bj"}[market]
    return f"{prefix}{digits}"


_INDEX_ALIASES: dict[str, str] = {
    "hs300": "000300.SH",
    "csi300": "000300.SH",
    "000300": "000300.SH",
    "zz500": "000905.SH",
    "csi500": "000905.SH",
    "000905": "000905.SH",
    "csi1000": "000852.SH",
    "zz1000": "000852.SH",
    "000852": "000852.SH",
    "sh000001": "000001.SH",
    "000001": "000001.SH",
    "sz399001": "399001.SZ",
    "399001": "399001.SZ",
    "cyb": "399006.SZ",
    "chuangyeban": "399006.SZ",
    "399006": "399006.SZ",
}


def _index_ts_code(symbol: Any) -> str:
    text = str(symbol or "").strip()
    if not text:
        raise ValueError("missing index symbol")
    upper = text.upper()
    if re.fullmatch(r"\d{6}\.(SH|SZ)", upper):
        return upper
    key = text.lower()
    if key in _INDEX_ALIASES:
        return _INDEX_ALIASES[key]
    if re.fullmatch(r"(sh|sz)\d{6}", key):
        digits = key[2:]
        suffix = key[:2].upper()
        return f"{digits}.{suffix}"
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) != 6:
        raise ValueError(f"invalid index symbol for Tushare: {symbol!r}")
    return f"{digits}.{'SZ' if digits.startswith('399') else 'SH'}"


def _unique_stock_ts_codes(codes: list[str] | tuple[str, ...] | None) -> list[str]:
    out: list[str] = []
    for code in codes or []:
        ts_code = _stock_ts_code(code)
        if ts_code not in out:
            out.append(ts_code)
    return out


class TushareProvider(BaseProvider):
    provider_name = "tushare"

    def __init__(
        self,
        *,
        token: str | None = None,
        api_url: str | None = None,
        timeout: int = 15,
        retries: int = 1,
        proxy_url: str | None = None,
        min_interval_seconds: float | None = None,
        rate_limit_retry_seconds: float | None = None,
        request_cache_seconds: float | None = None,
    ) -> None:
        resolved_proxy_url = proxy_url if proxy_url is not None else os.environ.get("PRISM_TUSHARE_PROXY_URL", "").strip()
        super().__init__(timeout=timeout, retries=retries, proxy_url=resolved_proxy_url)
        self.session.trust_env = bool(resolved_proxy_url)
        self._token = token
        self.api_url = (api_url or os.environ.get("PRISM_TUSHARE_API_URL") or _DEFAULT_API_URL).strip()
        self.min_interval_seconds = (
            _env_float("PRISM_TUSHARE_MIN_INTERVAL_SECONDS", 0.0)
            if min_interval_seconds is None
            else max(float(min_interval_seconds), 0.0)
        )
        self.rate_limit_retry_seconds = (
            _env_float("PRISM_TUSHARE_RATE_LIMIT_RETRY_SECONDS", 0.0)
            if rate_limit_retry_seconds is None
            else max(float(rate_limit_retry_seconds), 0.0)
        )
        self.request_cache_seconds = (
            _env_float("PRISM_TUSHARE_REQUEST_CACHE_SECONDS", 0.0)
            if request_cache_seconds is None
            else max(float(request_cache_seconds), 0.0)
        )
        self._throttled_apis = _csv_env("PRISM_TUSHARE_THROTTLED_APIS", _DEFAULT_THROTTLED_APIS)
        self._last_api_call_at: dict[str, float] = {}
        self._rate_lock = threading.Lock()
        self._cache_lock = threading.Lock()
        self._response_cache: dict[str, tuple[float, list[dict[str, Any]], str, str, str]] = {}
        self._local_repository: DatasetRepository | None = None

    @property
    def token_configured(self) -> bool:
        return bool(self._resolve_token())

    @staticmethod
    def token_env_names() -> tuple[str, ...]:
        return _TOKEN_ENV_NAMES

    @staticmethod
    def configured_token_env_names() -> list[str]:
        return configured_env_names(_TOKEN_ENV_NAMES)

    def _resolve_token(self) -> str:
        if self._token is not None:
            return self._token.strip()
        load_project_env()
        for name in _TOKEN_ENV_NAMES:
            value = os.environ.get(name, "").strip()
            if value:
                return value
        return ""

    def _repository(self) -> DatasetRepository:
        if self._local_repository is None:
            root = os.environ.get("PRISM_DATASET_REPOSITORY_ROOT", "").strip()
            self._local_repository = DatasetRepository(root or default_dataset_repository_root())
        return self._local_repository

    def _candidate_dataset_dates(self, dataset: str, trade_date: str) -> list[str]:
        target = _dash_date(trade_date) or today_str()
        candidates = [target]
        dataset_dir = self._repository().base_path / DatasetRepository.sanitize_key(dataset)
        if not dataset_dir.exists():
            return candidates
        target_digits = _compact_date(target)
        previous = sorted(
            child.name
            for child in dataset_dir.iterdir()
            if child.is_dir() and _compact_date(child.name) and _compact_date(child.name) <= target_digits
        )
        for date_value in reversed(previous):
            if date_value not in candidates:
                candidates.append(date_value)
        return candidates

    def _load_local_dataset(
        self,
        dataset: str,
        trade_date: str,
        keys: list[str],
    ) -> tuple[Any, dict[str, Any], str, str] | None:
        repository = self._repository()
        for date_value in self._candidate_dataset_dates(dataset, trade_date):
            for key in keys:
                data, manifest = repository.load_dataset(dataset, date_value, key)
                if data is None or not manifest:
                    continue
                if str(manifest.get("status") or "").lower() != DatasetStatus.OK.value:
                    continue
                return data, manifest, date_value, key
        return None

    @staticmethod
    def _parse_manifest_datetime(manifest: dict[str, Any], trade_date: str) -> datetime | None:
        for value in (manifest.get("asof"), manifest.get("fetched_at"), trade_date):
            text = str(value or "").strip()
            if not text:
                continue
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                try:
                    return datetime.strptime(text, fmt)
                except ValueError:
                    continue
        return None

    def _ok_local_dataset(
        self,
        *,
        dataset: str,
        trade_date: str,
        data: Any,
        manifest: dict[str, Any],
        quality_flags: list[str] | None = None,
        live_small_allowed: bool | None = None,
        result_trade_date: str | None = None,
    ) -> ProviderResult:
        flags = list(manifest.get("quality_flags") or [])
        for flag in quality_flags or []:
            if flag not in flags:
                flags.append(flag)
        final_trade_date = _dash_date(result_trade_date or manifest.get("trade_date") or trade_date)
        return self._ok(
            data=data,
            dataset=dataset,
            trade_date=final_trade_date,
            endpoint=str(manifest.get("source_endpoint") or "prism-local-dataset://tushare"),
            params_hash=hash_payload({
                "dataset": dataset,
                "requested_trade_date": trade_date,
                "result_trade_date": final_trade_date,
                "source_trade_date": manifest.get("trade_date"),
                "source_manifest_path": manifest.get("manifest_path"),
                "source_data_path": manifest.get("data_path"),
            }),
            payload_hash=hash_payload(data),
            ttl_seconds=int(manifest.get("ttl_seconds") or 86400),
            asof=self._parse_manifest_datetime(manifest, final_trade_date),
            quality_flags=flags,
            live_small_allowed=bool(manifest.get("live_small_allowed", True)) if live_small_allowed is None else bool(live_small_allowed),
            license_scope=str(manifest.get("license_scope") or "authorized_tinyshare_proxy"),
            extra={
                "source_api": manifest.get("source_api") or "promoted_local_dataset",
                "authority_provider_override": "tushare",
                "local_dataset_manifest_path": manifest.get("manifest_path"),
                "local_dataset_data_path": manifest.get("data_path"),
            },
        )

    @staticmethod
    def _stock_dataset_keys(code: Any) -> list[str]:
        ts_code = _stock_ts_code(code)
        symbol = _prism_stock_code(ts_code)
        digits = symbol[2:] if len(symbol) == 8 and symbol[:2] in {"sh", "sz", "bj"} else "".join(ch for ch in symbol if ch.isdigit())[:6]
        keys = [digits, symbol, str(code or "").strip(), ts_code]
        return [key for key in dict.fromkeys(keys) if key]

    @staticmethod
    def _filter_rows_to_date(rows: list[dict[str, Any]], trade_date: str) -> list[dict[str, Any]]:
        target_digits = _compact_date(trade_date)
        output: list[dict[str, Any]] = []
        for row in rows:
            row_date = _compact_date(row.get("trade_date") or row.get("date"))
            if row_date and target_digits and row_date > target_digits:
                continue
            output.append(dict(row))
        output.sort(key=lambda item: str(item.get("trade_date") or item.get("date") or ""))
        return output

    @staticmethod
    def _latest_dict_rows(data: Any, requested_codes: list[str]) -> dict[str, dict[str, Any]]:
        if not isinstance(data, dict):
            return {}
        output: dict[str, dict[str, Any]] = {}
        for code in requested_codes:
            item = data.get(code)
            if isinstance(item, dict):
                output[code] = dict(item)
        return output

    @staticmethod
    def _row_trade_dates(data: Any) -> list[str]:
        values: list[Any]
        if isinstance(data, dict):
            values = list(data.values())
        elif isinstance(data, list):
            values = list(data)
        else:
            values = []
        dates = sorted({
            _dash_date(item.get("trade_date") or item.get("date"))
            for item in values
            if isinstance(item, dict) and _dash_date(item.get("trade_date") or item.get("date"))
        })
        return dates

    @staticmethod
    def _lag_quality_flags(row_dates: list[str], target_date: str, label: str) -> list[str]:
        if not row_dates:
            return []
        if all(date == target_date for date in row_dates):
            return []
        if len(row_dates) == 1:
            return [f"{label}_source_trade_date_lag:{row_dates[0]}"]
        return [f"{label}_source_trade_date_mixed:{row_dates[0]}..{row_dates[-1]}"]

    def _latest_capital_flow_from_local(self, code: str, trade_date: str) -> dict[str, Any] | None:
        local = self._load_local_dataset("capital_flow.daily", trade_date, self._stock_dataset_keys(code))
        if not local:
            return None
        data, _manifest, _date_value, _key = local
        if not isinstance(data, list):
            return None
        rows = self._filter_rows_to_date([row for row in data if isinstance(row, dict)], trade_date)
        return rows[-1] if rows else None

    def _fundamental_from_valuation(self, code: str, trade_date: str) -> dict[str, Any] | None:
        local = self._load_local_dataset("valuation.daily", trade_date, self._stock_dataset_keys(code))
        if not local:
            return None
        data, _manifest, _date_value, _key = local
        if not isinstance(data, list):
            return None
        rows = self._filter_rows_to_date([row for row in data if isinstance(row, dict)], trade_date)
        if not rows:
            return None
        return self._normalize_daily_basic_fundamental(rows[-1])

    def fetch_capital_flow(self, code: str, trade_date: str | None = None, count: int = 5, **kwargs: Any) -> ProviderResult:
        target_date = _dash_date(trade_date or kwargs.get("trade_date") or today_str())
        mode = str(kwargs.get("mode") or "history").strip().lower()
        keys = self._stock_dataset_keys(code)
        local = self._load_local_dataset("capital_flow.daily", target_date, keys)
        if local:
            data, manifest, _date_value, _key = local
            rows = data if isinstance(data, list) else []
            output = self._filter_rows_to_date([row for row in rows if isinstance(row, dict)], target_date)
            if mode == "snapshot":
                output = output[-1:] if output else []
            elif count:
                output = output[-int(count):]
            if output:
                row_dates = self._row_trade_dates(output)
                lag_flags = self._lag_quality_flags(row_dates[-1:], target_date, "capital_flow")
                return self._ok_local_dataset(
                    dataset="capital_flow.daily",
                    trade_date=target_date,
                    data=output,
                    manifest=manifest,
                    quality_flags=lag_flags,
                    live_small_allowed=not lag_flags,
                    result_trade_date=row_dates[-1] if row_dates else target_date,
                )

        ts_code = _stock_ts_code(code)
        end = _compact_date(target_date)
        start = _compact_date(kwargs.get("start_date")) or _window_start(end, int(count or 5))
        fields = (
            "ts_code,trade_date,buy_sm_amount,sell_sm_amount,buy_md_amount,sell_md_amount,"
            "buy_lg_amount,sell_lg_amount,buy_elg_amount,sell_elg_amount,net_mf_amount"
        )
        rows, endpoint, params_hash, payload_hash, error = self._call(
            "moneyflow",
            params={"ts_code": ts_code, "start_date": start, "end_date": end},
            fields=fields,
        )
        if error:
            return self._tushare_error(dataset="capital_flow.daily", trade_date=target_date, api_name="moneyflow", endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash, error=error)
        output = [self._normalize_moneyflow_row(row) for row in rows]
        output = self._filter_rows_to_date(output, target_date)
        if mode == "snapshot":
            output = output[-1:] if output else []
        elif count:
            output = output[-int(count):]
        if not output:
            return self._error(dataset="capital_flow.daily", trade_date=target_date, error=f"empty Tushare moneyflow for {ts_code}", endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash)
        return self._ok_tushare(data=output, dataset="capital_flow.daily", trade_date=str(output[-1].get("trade_date") or target_date), endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash, api_name="moneyflow")

    def fetch_capital_flow_batch(self, codes: list[str], **kwargs: Any) -> ProviderResult:
        target_date = _dash_date(kwargs.get("trade_date") or today_str())
        requested_codes = []
        for code in codes:
            digits = self._stock_dataset_keys(code)[0]
            if digits not in requested_codes:
                requested_codes.append(digits)

        local = self._load_local_dataset("capital_flow.batch", target_date, ["tinyshare-hs300-zz500"])
        if local:
            data, manifest, _date_value, _key = local
            output = self._latest_dict_rows(data, requested_codes)
            missing = [code for code in requested_codes if code not in output]
            for missing_code in missing:
                row = self._latest_capital_flow_from_local(missing_code, target_date)
                if row:
                    output[missing_code] = row
            missing = [code for code in requested_codes if code not in output]
            if output:
                row_dates = self._row_trade_dates(output)
                quality_flags = [f"local_batch_missing_codes:{len(missing)}"] if missing else []
                quality_flags.extend(self._lag_quality_flags(row_dates, target_date, "capital_flow"))
                return self._ok_local_dataset(
                    dataset="capital_flow.batch",
                    trade_date=target_date,
                    data=output,
                    manifest=manifest,
                    quality_flags=quality_flags,
                    live_small_allowed=not quality_flags,
                    result_trade_date=row_dates[-1] if row_dates else target_date,
                )

        end = _compact_date(target_date)
        fields = (
            "ts_code,trade_date,buy_sm_amount,sell_sm_amount,buy_md_amount,sell_md_amount,"
            "buy_lg_amount,sell_lg_amount,buy_elg_amount,sell_elg_amount,net_mf_amount"
        )
        rows, endpoint, params_hash, payload_hash, error = self._call(
            "moneyflow",
            params={"trade_date": end},
            fields=fields,
        )
        if error:
            return self._tushare_error(dataset="capital_flow.batch", trade_date=target_date, api_name="moneyflow", endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash, error=error)
        requested_set = set(requested_codes)
        output: dict[str, dict[str, Any]] = {}
        for row in rows:
            item = self._normalize_moneyflow_row(row)
            digits = str(item.get("code") or "")
            if digits in requested_set:
                output[digits] = item
        missing = [code for code in requested_codes if code not in output]
        if not output:
            return self._error(dataset="capital_flow.batch", trade_date=target_date, error="empty Tushare moneyflow batch", endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash)
        return self._ok_tushare(
            data=output,
            dataset="capital_flow.batch",
            trade_date=target_date,
            endpoint=endpoint,
            params_hash=params_hash,
            payload_hash=payload_hash,
            api_name="moneyflow",
            quality_flags=[f"tushare_batch_missing_codes:{len(missing)}"] if missing else [],
            live_small_allowed=not missing,
        )

    def fetch_fundamentals(self, code: str, **kwargs: Any) -> ProviderResult:
        target_date = _dash_date(kwargs.get("trade_date") or today_str())
        local = self._load_local_dataset("fundamentals.snapshot", target_date, self._stock_dataset_keys(code))
        if local:
            data, manifest, _date_value, _key = local
            if isinstance(data, dict) and data:
                return self._ok_local_dataset(
                    dataset="fundamentals.snapshot",
                    trade_date=target_date,
                    data=dict(data),
                    manifest=manifest,
                )

        valuation = self._fundamental_from_valuation(code, target_date)
        if valuation:
            synthetic_manifest = {
                "trade_date": target_date,
                "source_endpoint": "prism-local-dataset://tushare/valuation.daily",
                "ttl_seconds": 86400,
                "asof": target_date,
                "quality_flags": ["fundamentals_from_valuation_daily"],
                "live_small_allowed": True,
                "license_scope": "authorized_tinyshare_proxy",
            }
            return self._ok_local_dataset(
                dataset="fundamentals.snapshot",
                trade_date=target_date,
                data=valuation,
                manifest=synthetic_manifest,
                quality_flags=["fundamentals_from_valuation_daily"],
            )

        ts_code = _stock_ts_code(code)
        end = _compact_date(target_date)
        start = _compact_date(kwargs.get("start_date")) or _window_start(end, 5)
        fields = "ts_code,trade_date,close,pe,pe_ttm,pb,ps,ps_ttm,total_mv,circ_mv"
        rows, endpoint, params_hash, payload_hash, error = self._call(
            "daily_basic",
            params={"ts_code": ts_code, "start_date": start, "end_date": end},
            fields=fields,
        )
        if error:
            return self._tushare_error(dataset="fundamentals.snapshot", trade_date=target_date, api_name="daily_basic", endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash, error=error)
        normalized = [self._normalize_daily_basic_fundamental(row) for row in rows]
        normalized = self._filter_rows_to_date(normalized, target_date)
        if not normalized:
            return self._error(dataset="fundamentals.snapshot", trade_date=target_date, error=f"empty Tushare daily_basic for {ts_code}", endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash)
        return self._ok_tushare(
            data=normalized[-1],
            dataset="fundamentals.snapshot",
            trade_date=str(normalized[-1].get("trade_date") or target_date),
            endpoint=endpoint,
            params_hash=params_hash,
            payload_hash=payload_hash,
            api_name="daily_basic",
        )

    def fetch_fundamentals_batch(self, codes: list[str], **kwargs: Any) -> ProviderResult:
        target_date = _dash_date(kwargs.get("trade_date") or today_str())
        requested_codes = []
        for code in codes:
            digits = self._stock_dataset_keys(code)[0]
            if digits not in requested_codes:
                requested_codes.append(digits)

        local = self._load_local_dataset("fundamentals.batch", target_date, ["tinyshare-hs300-zz500"])
        if local:
            data, manifest, _date_value, _key = local
            output = self._latest_dict_rows(data, requested_codes)
            missing = [code for code in requested_codes if code not in output]
            for missing_code in missing:
                single = self._load_local_dataset("fundamentals.snapshot", target_date, self._stock_dataset_keys(missing_code))
                if single:
                    single_data, _single_manifest, _single_date, _single_key = single
                    if isinstance(single_data, dict) and single_data:
                        output[missing_code] = dict(single_data)
                elif (valuation := self._fundamental_from_valuation(missing_code, target_date)):
                    output[missing_code] = valuation
            missing = [code for code in requested_codes if code not in output]
            if output:
                quality_flags = [f"local_batch_missing_codes:{len(missing)}"] if missing else []
                return self._ok_local_dataset(
                    dataset="fundamentals.batch",
                    trade_date=target_date,
                    data=output,
                    manifest=manifest,
                    quality_flags=quality_flags,
                    live_small_allowed=not missing,
                )

        end = _compact_date(target_date)
        fields = "ts_code,trade_date,close,pe,pe_ttm,pb,ps,ps_ttm,total_mv,circ_mv"
        rows, endpoint, params_hash, payload_hash, error = self._call(
            "daily_basic",
            params={"trade_date": end},
            fields=fields,
        )
        if error:
            return self._tushare_error(dataset="fundamentals.batch", trade_date=target_date, api_name="daily_basic", endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash, error=error)
        requested_set = set(requested_codes)
        output: dict[str, dict[str, Any]] = {}
        for row in rows:
            item = self._normalize_daily_basic_fundamental(row)
            digits = str(item.get("code") or "")
            if digits in requested_set:
                output[digits] = item
        missing = [code for code in requested_codes if code not in output]
        if not output:
            return self._error(dataset="fundamentals.batch", trade_date=target_date, error="empty Tushare daily_basic batch", endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash)
        return self._ok_tushare(
            data=output,
            dataset="fundamentals.batch",
            trade_date=target_date,
            endpoint=endpoint,
            params_hash=params_hash,
            payload_hash=payload_hash,
            api_name="daily_basic",
            quality_flags=[f"tushare_batch_missing_codes:{len(missing)}"] if missing else [],
            live_small_allowed=not missing,
        )

    @staticmethod
    def _normalize_moneyflow_row(row: dict[str, Any]) -> dict[str, Any]:
        ts_code = str(row.get("ts_code") or "").strip().upper()
        trade_date = _dash_date(row.get("trade_date"))
        buy_lg = _float_or_none(row.get("buy_lg_amount")) or 0.0
        sell_lg = _float_or_none(row.get("sell_lg_amount")) or 0.0
        buy_elg = _float_or_none(row.get("buy_elg_amount")) or 0.0
        sell_elg = _float_or_none(row.get("sell_elg_amount")) or 0.0
        buy_sm = _float_or_none(row.get("buy_sm_amount")) or 0.0
        sell_sm = _float_or_none(row.get("sell_sm_amount")) or 0.0
        net_mf = _float_or_none(row.get("net_mf_amount"))
        large_net = buy_lg - sell_lg
        super_large = buy_elg - sell_elg
        main_net = large_net + super_large
        small_net = buy_sm - sell_sm
        return {
            "date": trade_date,
            "trade_date": trade_date,
            "code": _prism_stock_code(ts_code)[2:],
            "symbol": _prism_stock_code(ts_code),
            "ts_code": ts_code,
            "main_net": round(main_net, 2),
            "main_net_wan": round(main_net, 2),
            "main_net_yi": round(main_net / 10000, 4),
            "super_large": round(super_large, 2),
            "super_large_wan": round(super_large, 2),
            "super_large_yi": round(super_large / 10000, 4),
            "mid_large_net": round(large_net, 2),
            "small_net": round(small_net, 2),
            "retail_net": round((net_mf or 0.0) - main_net, 2) if net_mf is not None else None,
            "net_mf_amount": net_mf,
            "unit": "wan_yuan",
        }

    @staticmethod
    def _normalize_daily_basic_fundamental(row: dict[str, Any]) -> dict[str, Any]:
        ts_code = str(row.get("ts_code") or "").strip().upper()
        total_mv = _float_or_none(row.get("total_mv"))
        circ_mv = _float_or_none(row.get("circ_mv"))
        return {
            "code": _prism_stock_code(ts_code)[2:],
            "symbol": _prism_stock_code(ts_code),
            "ts_code": ts_code,
            "trade_date": _dash_date(row.get("trade_date")),
            "price": _float_or_none(row.get("close")),
            "pe": _float_or_none(row.get("pe")) or _float_or_none(row.get("pe_ttm")),
            "pe_ttm": _float_or_none(row.get("pe_ttm")) or _float_or_none(row.get("pe")),
            "pb": _float_or_none(row.get("pb")),
            "ps": _float_or_none(row.get("ps")),
            "ps_ttm": _float_or_none(row.get("ps_ttm")),
            "total_mv": round(total_mv / 10000, 4) if total_mv is not None else None,
            "total_mv_yi": round(total_mv / 10000, 4) if total_mv is not None else None,
            "circ_mv_yi": round(circ_mv / 10000, 4) if circ_mv is not None else None,
        }

    def _should_throttle(self, api_name: str) -> bool:
        return self.min_interval_seconds > 0 and ("*" in self._throttled_apis or api_name in self._throttled_apis)

    def _wait_for_rate_window(self, api_name: str) -> None:
        if not self._should_throttle(api_name):
            return
        with self._rate_lock:
            now = time.monotonic()
            elapsed = now - float(self._last_api_call_at.get(api_name, 0.0))
            wait_seconds = self.min_interval_seconds - elapsed
            if wait_seconds > 0:
                time.sleep(wait_seconds)
            self._last_api_call_at[api_name] = time.monotonic()

    def _cached_call(
        self,
        cache_key: str,
    ) -> tuple[list[dict[str, Any]], str, str, str] | None:
        if self.request_cache_seconds <= 0:
            return None
        with self._cache_lock:
            cached = self._response_cache.get(cache_key)
            if not cached:
                return None
            cached_at, rows, endpoint, params_hash, payload_hash = cached
            if time.monotonic() - cached_at > self.request_cache_seconds:
                self._response_cache.pop(cache_key, None)
                return None
            return [dict(row) for row in rows], endpoint, params_hash, payload_hash

    def _store_cached_call(
        self,
        cache_key: str,
        *,
        rows: list[dict[str, Any]],
        endpoint: str,
        params_hash: str,
        payload_hash: str,
    ) -> None:
        if self.request_cache_seconds <= 0:
            return
        with self._cache_lock:
            self._response_cache[cache_key] = (
                time.monotonic(),
                [dict(row) for row in rows],
                endpoint,
                params_hash,
                payload_hash,
            )

    def _call(self, api_name: str, *, params: dict[str, Any], fields: str) -> tuple[list[dict[str, Any]], str, str, str, dict[str, Any] | None]:
        token = self._resolve_token()
        endpoint = redact_endpoint(self.api_url)
        clean_params = {k: v for k, v in params.items() if v not in (None, "")}
        safe_request = {"api_name": api_name, "params": clean_params, "fields": fields, "token_configured": bool(token)}
        params_hash = hash_payload(safe_request)
        cache_key = hash_payload({"api_name": api_name, "params": clean_params, "fields": fields})
        if not token:
            return [], endpoint, params_hash, "", {
                "message": "Tushare token missing; set PRISM_TUSHARE_TOKEN or TUSHARE_TOKEN in the backend environment",
                "quality_flags": ["provider_token_missing"],
                "status": DatasetStatus.UNAVAILABLE,
            }
        cached = self._cached_call(cache_key)
        if cached is not None:
            rows, cached_endpoint, cached_params_hash, cached_payload_hash = cached
            return rows, cached_endpoint, cached_params_hash, cached_payload_hash, None

        body = {
            "api_name": api_name,
            "token": token,
            "params": clean_params,
            "fields": fields,
        }
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                self._wait_for_rate_window(api_name)
                response = self.session.post(
                    self.api_url,
                    json=body,
                    timeout=self.timeout,
                    proxies=self._proxies(),
                )
                response.raise_for_status()
                payload = response.json()
                payload_hash = hash_payload(payload)
                code = int(payload.get("code") or 0)
                message = str(payload.get("msg") or payload.get("message") or "").strip()
                if code != 0:
                    status, flags = self._classify_tushare_error(message)
                    if (
                        "provider_rate_limited" in flags
                        and "provider_hourly_rate_limited" not in flags
                        and attempt < self.retries
                        and self.rate_limit_retry_seconds > 0
                    ):
                        time.sleep(self.rate_limit_retry_seconds)
                        continue
                    return [], endpoint, params_hash, payload_hash, {
                        "message": message or f"Tushare returned code {code}",
                        "quality_flags": flags,
                        "status": status,
                    }
                data = payload.get("data") or {}
                response_fields = [str(item) for item in (data.get("fields") or [])]
                items = data.get("items") or []
                rows = [
                    {field: item[idx] if idx < len(item) else None for idx, field in enumerate(response_fields)}
                    for item in items
                    if isinstance(item, list)
                ]
                self._store_cached_call(
                    cache_key,
                    rows=rows,
                    endpoint=endpoint,
                    params_hash=params_hash,
                    payload_hash=payload_hash,
                )
                return rows, endpoint, params_hash, payload_hash, None
            except Exception as exc:
                last_error = exc
        return [], endpoint, params_hash, "", {
            "message": str(last_error) if last_error else "Tushare request failed",
            "quality_flags": ["fetch_failed"],
            "status": DatasetStatus.FAILED,
        }

    @staticmethod
    def _classify_tushare_error(message: str) -> tuple[DatasetStatus, list[str]]:
        lowered = message.lower()
        if "token" in lowered:
            return DatasetStatus.UNAVAILABLE, ["provider_token_invalid"]
        rate_limit_tokens = ("频率超限", "调用频次", "次/分钟", "每分钟", "rate limit", "frequency", "too many")
        if any(token in message or token in lowered for token in rate_limit_tokens):
            flags = ["provider_rate_limited"]
            if "次/小时" in message or "每小时" in message or "per hour" in lowered or "hour" in lowered:
                flags.append("provider_hourly_rate_limited")
            return DatasetStatus.UNAVAILABLE, flags
        permission_tokens = ("权限", "积分", "permission", "points", "credits", "没有访问", "无权限")
        if any(token in message or token in lowered for token in permission_tokens):
            return DatasetStatus.UNAVAILABLE, ["provider_permission_or_points_blocked"]
        return DatasetStatus.FAILED, ["fetch_failed"]

    def _tushare_error(
        self,
        *,
        dataset: str,
        trade_date: str,
        api_name: str,
        endpoint: str,
        params_hash: str,
        payload_hash: str,
        error: dict[str, Any],
    ) -> ProviderResult:
        return self._error(
            dataset=dataset,
            trade_date=_dash_date(trade_date) or today_str(),
            error=str(error.get("message") or f"Tushare {api_name} unavailable"),
            endpoint=endpoint,
            params_hash=params_hash,
            payload_hash=payload_hash,
            quality_flags=list(error.get("quality_flags") or ["fetch_failed"]),
            status=error.get("status") if isinstance(error.get("status"), DatasetStatus) else DatasetStatus.FAILED,
            license_scope="authorized_tushare_token_required",
            extra={"source_api": api_name, "token_env_names": list(_TOKEN_ENV_NAMES)},
        )

    def _ok_tushare(
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
    ) -> ProviderResult:
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
            license_scope="authorized_tushare_token",
            extra={
                "source_api": api_name,
                "authority_provider_override": "tushare",
                "token_env_names": list(_TOKEN_ENV_NAMES),
            },
        )

    def fetch_kline(self, code: str, period: str = "daily", count: int = 120, **kwargs: Any) -> ProviderResult:
        if str(period or "daily").lower() not in {"daily", "day", "d"}:
            return self._error(dataset="bars.daily", trade_date=kwargs.get("trade_date") or today_str(), error=f"unsupported Tushare kline period: {period}")
        ts_code = _stock_ts_code(code)
        end_date = _compact_date(kwargs.get("end_date") or kwargs.get("trade_date") or today_str())
        start_date = _compact_date(kwargs.get("start_date")) or _window_start(end_date, count)
        fields = "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount"
        rows, endpoint, params_hash, payload_hash, error = self._call(
            "daily",
            params={"ts_code": ts_code, "start_date": start_date, "end_date": end_date},
            fields=fields,
        )
        if error:
            return self._tushare_error(dataset="bars.daily", trade_date=_dash_date(end_date), api_name="daily", endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash, error=error)

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
            return self._error(dataset="bars.daily", trade_date=_dash_date(end_date), error=f"empty Tushare daily for {ts_code}", endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash)
        return self._ok_tushare(data=output, dataset="bars.daily", trade_date=str(output[-1]["trade_date"]), endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash, api_name="daily", ttl_seconds=86400)

    def fetch_trade_calendar(
        self,
        exchange: str = "SSE",
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: Any,
    ) -> ProviderResult:
        trade_date = _compact_date(kwargs.get("trade_date") or end_date or start_date or today_str())
        start = _compact_date(start_date) or trade_date
        end = _compact_date(end_date) or trade_date
        fields = "exchange,cal_date,is_open,pretrade_date"
        rows, endpoint, params_hash, payload_hash, error = self._call(
            "trade_cal",
            params={"exchange": str(exchange or "SSE").upper(), "start_date": start, "end_date": end},
            fields=fields,
        )
        if error:
            return self._tushare_error(dataset="trade_calendar", trade_date=_dash_date(trade_date), api_name="trade_cal", endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash, error=error)
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
            return self._error(dataset="trade_calendar", trade_date=_dash_date(trade_date), error="empty Tushare trade_cal", endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash)
        return self._ok_tushare(data=output, dataset="trade_calendar", trade_date=_dash_date(trade_date), endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash, api_name="trade_cal")

    def fetch_index_daily(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: Any,
    ) -> ProviderResult:
        ts_code = _index_ts_code(symbol)
        end = _compact_date(end_date or kwargs.get("trade_date") or today_str())
        start = _compact_date(start_date) or _window_start(end, int(kwargs.get("count") or 120))
        fields = "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount"
        rows, endpoint, params_hash, payload_hash, error = self._call(
            "index_daily",
            params={"ts_code": ts_code, "start_date": start, "end_date": end},
            fields=fields,
        )
        if error:
            return self._tushare_error(dataset="benchmark.index_daily", trade_date=_dash_date(end), api_name="index_daily", endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash, error=error)
        output = []
        for row in rows:
            trade_date = _dash_date(row.get("trade_date"))
            output.append({
                "symbol": ts_code,
                "ts_code": row.get("ts_code"),
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
            return self._error(dataset="benchmark.index_daily", trade_date=_dash_date(end), error=f"empty Tushare index_daily for {ts_code}", endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash)
        return self._ok_tushare(data=output, dataset="benchmark.index_daily", trade_date=str(output[-1]["trade_date"]), endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash, api_name="index_daily")

    def fetch_index_daily_batch(
        self,
        symbols: list[str],
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: Any,
    ) -> ProviderResult:
        requested = [_index_ts_code(symbol) for symbol in symbols if str(symbol or "").strip()]
        requested = list(dict.fromkeys(requested))
        end = _compact_date(end_date or kwargs.get("trade_date") or today_str())
        start = _compact_date(start_date) or _window_start(end, int(kwargs.get("count") or 120))
        fields = "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount"
        output = []
        call_errors: list[dict[str, Any]] = []
        endpoints: list[str] = []
        params_hashes: list[str] = []
        payload_hashes: list[str] = []
        for ts_code in requested:
            rows, endpoint, params_hash, payload_hash, error = self._call(
                "index_daily",
                params={"ts_code": ts_code, "start_date": start, "end_date": end},
                fields=fields,
            )
            endpoints.append(endpoint)
            params_hashes.append(params_hash)
            if payload_hash:
                payload_hashes.append(payload_hash)
            if error:
                call_errors.append({"ts_code": ts_code, **error})
                continue
            for row in rows:
                row_ts_code = str(row.get("ts_code") or "").strip().upper()
                if row_ts_code != ts_code:
                    continue
                trade_date = _dash_date(row.get("trade_date"))
                output.append({
                    "symbol": ts_code,
                    "ts_code": row_ts_code,
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
        endpoint = endpoints[-1] if endpoints else redact_endpoint(self.api_url)
        params_hash = hash_payload({
            "api_name": "index_daily",
            "params": {"ts_codes": requested, "start_date": start, "end_date": end},
            "fields": fields,
            "token_configured": bool(self._resolve_token()),
            "per_request_params_hashes": params_hashes,
        })
        payload_hash = hash_payload({"rows": output, "per_request_payload_hashes": payload_hashes})
        if call_errors and not output:
            first_error = call_errors[0]
            return self._tushare_error(
                dataset="benchmark.index_daily",
                trade_date=_dash_date(end),
                api_name="index_daily",
                endpoint=endpoint,
                params_hash=params_hash,
                payload_hash=payload_hash,
                error=first_error,
            )
        output = [item for item in output if item["trade_date"]]
        output.sort(key=lambda item: (str(item.get("ts_code") or ""), str(item.get("trade_date") or "")))
        found = {str(item.get("ts_code") or "").strip().upper() for item in output}
        missing = [symbol for symbol in requested if symbol not in found]
        if not output:
            return self._error(
                dataset="benchmark.index_daily",
                trade_date=_dash_date(end),
                error=f"empty Tushare index_daily batch for {','.join(requested)}",
                endpoint=endpoint,
                params_hash=params_hash,
                payload_hash=payload_hash,
            )
        quality_flags = ["index_daily_batch_missing_symbols"] if missing else []
        if call_errors and "index_daily_batch_partial_errors" not in quality_flags:
            quality_flags.append("index_daily_batch_partial_errors")
        return self._ok_tushare(
            data=output,
            dataset="benchmark.index_daily",
            trade_date=_dash_date(end),
            endpoint=endpoint,
            params_hash=params_hash,
            payload_hash=payload_hash,
            api_name="index_daily",
            quality_flags=quality_flags,
            live_small_allowed=not quality_flags,
        )

    def fetch_adjustment_factor(
        self,
        code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: Any,
    ) -> ProviderResult:
        ts_code = _stock_ts_code(code)
        end = _compact_date(end_date or kwargs.get("trade_date") or today_str())
        start = _compact_date(start_date) or _window_start(end, int(kwargs.get("count") or 120))
        fields = "ts_code,trade_date,adj_factor"
        rows, endpoint, params_hash, payload_hash, error = self._call(
            "adj_factor",
            params={"ts_code": ts_code, "start_date": start, "end_date": end},
            fields=fields,
        )
        if error:
            return self._tushare_error(dataset="adjustment.factor", trade_date=_dash_date(end), api_name="adj_factor", endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash, error=error)
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
            return self._error(dataset="adjustment.factor", trade_date=_dash_date(end), error=f"empty Tushare adj_factor for {ts_code}", endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash)
        return self._ok_tushare(data=output, dataset="adjustment.factor", trade_date=str(output[-1]["trade_date"]), endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash, api_name="adj_factor")

    def fetch_price_limit(self, trade_date: str, code: str | None = None, **kwargs: Any) -> ProviderResult:
        date = _compact_date(trade_date or kwargs.get("trade_date") or today_str())
        ts_code = _stock_ts_code(code) if code else ""
        fields = "ts_code,trade_date,up_limit,down_limit"
        rows, endpoint, params_hash, payload_hash, error = self._call(
            "stk_limit",
            params={"trade_date": date, "ts_code": ts_code},
            fields=fields,
        )
        if error:
            return self._tushare_error(dataset="price_limit.daily", trade_date=_dash_date(date), api_name="stk_limit", endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash, error=error)
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
            return self._error(dataset="price_limit.daily", trade_date=_dash_date(date), error=f"empty Tushare stk_limit{target}", endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash)
        return self._ok_tushare(data=output, dataset="price_limit.daily", trade_date=_dash_date(date), endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash, api_name="stk_limit")

    def fetch_execution_flags(self, trade_date: str, codes: list[str] | None = None, **kwargs: Any) -> ProviderResult:
        date = _compact_date(trade_date or kwargs.get("trade_date") or today_str())
        requested = _unique_stock_ts_codes(codes)
        requested_set = set(requested)
        reused_limit_rows = kwargs.get("price_limit_rows")

        if isinstance(reused_limit_rows, list) and reused_limit_rows:
            limit_rows = [dict(row) for row in reused_limit_rows if isinstance(row, dict)]
            endpoint = redact_endpoint(self.api_url)
            params_hash = hash_payload({
                "api_name": "stk_limit",
                "params": {"trade_date": date},
                "fields": "ts_code,trade_date,up_limit,down_limit",
                "reused_dataset": "price_limit.daily",
            })
            payload_hash = hash_payload(limit_rows)
        else:
            limit_rows, endpoint, params_hash, payload_hash, error = self._call(
                "stk_limit",
                params={"trade_date": date},
                fields="ts_code,trade_date,up_limit,down_limit",
            )
            if error:
                return self._tushare_error(dataset="execution.flags", trade_date=_dash_date(date), api_name="stk_limit", endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash, error=error)

        suspend_rows, suspend_endpoint, suspend_params_hash, suspend_payload_hash, error = self._call(
            "suspend_d",
            params={"trade_date": date},
            fields="ts_code,trade_date,suspend_timing,suspend_type",
        )
        if error:
            return self._tushare_error(dataset="execution.flags", trade_date=_dash_date(date), api_name="suspend_d", endpoint=suspend_endpoint, params_hash=suspend_params_hash, payload_hash=suspend_payload_hash, error=error)

        st_rows, st_endpoint, st_params_hash, st_payload_hash, error = self._call(
            "stock_st",
            params={"trade_date": date},
            fields="ts_code,name,trade_date,type,type_name",
        )
        if error:
            return self._tushare_error(dataset="execution.flags", trade_date=_dash_date(date), api_name="stock_st", endpoint=st_endpoint, params_hash=st_params_hash, payload_hash=st_payload_hash, error=error)

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
                    *(
                        ["suspended"]
                        if is_suspended
                        else []
                    ),
                    *(
                        ["price_limit_missing"]
                        if up_limit is None or down_limit is None
                        else []
                    ),
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
            return self._error(dataset="execution.flags", trade_date=_dash_date(date), error="empty Tushare execution flags", endpoint=endpoint, params_hash=params_hash, payload_hash=payload_hash)

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
        })
        return self._ok_tushare(
            data=output,
            dataset="execution.flags",
            trade_date=_dash_date(date),
            endpoint=endpoint,
            params_hash=combined_params_hash,
            payload_hash=combined_payload_hash,
            api_name="stk_limit+suspend_d+stock_st",
            quality_flags=quality_flags,
            live_small_allowed=not quality_flags,
        )


__all__ = ["TushareProvider"]
