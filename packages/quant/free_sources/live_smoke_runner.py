from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import importlib
import importlib.metadata
import inspect
import json
from pathlib import Path
import re
from typing import Any

from .report_generator import generate_redacted_report
from .redaction import find_redaction_issues


APPROVED_SCRATCH_ROOT = Path("~/.prism-private/free-data-poc/")
DEFAULT_START_DATE = "2024-01-02"
DEFAULT_END_DATE = "2024-01-10"

STOCK_SAMPLES: Mapping[str, Mapping[str, str]] = {
    "kweichow_moutai": {"baostock": "sh.600519", "akshare": "600519"},
    "catl": {"baostock": "sz.300750", "akshare": "300750"},
    "ping_an_bank": {"baostock": "sz.000001", "akshare": "000001"},
}

INDEX_SAMPLES: Mapping[str, Mapping[str, str]] = {
    "hs300": {"baostock": "sh.000300", "akshare": "000300"},
    "csi500": {"baostock": "sh.000905", "akshare": "000905"},
}

NETWORK_ERROR_MARKERS = (
    "connection",
    "connect",
    "dns",
    "host",
    "network",
    "proxy",
    "remote",
    "ssl",
    "timed out",
    "timeout",
    "tls",
)

URL_RE = re.compile(r"\b(?:https?|file|s3)://\S+", re.IGNORECASE)
LOCAL_PATH_RE = re.compile(r"(^|\s)(/Users/|/tmp/|/var/|/private/|~/|\.?\.?/)\S*")


@dataclass(frozen=True)
class SmokeEndpointSpec:
    provider: str
    endpoint: str
    adapter_layer: str
    params_summary: Mapping[str, str]
    expected_field_list: tuple[str, ...]
    research_only_notes: tuple[str, ...]
    blocker_notes: tuple[str, ...]


@dataclass(frozen=True)
class SmokeRunResult:
    run_id: str
    live: bool
    endpoint_summaries: tuple[Mapping[str, Any], ...]
    markdown: str


SMOKE_ENDPOINTS: tuple[SmokeEndpointSpec, ...] = (
    SmokeEndpointSpec(
        "baostock",
        "query_trade_dates",
        "calendar",
        {"date_window": "sample_window", "sample": "calendar_only"},
        ("calendar_date", "is_trading_day"),
        ("calendar metadata can support non-production field availability review",),
        ("formal labels remain blocked",),
    ),
    SmokeEndpointSpec(
        "baostock",
        "query_stock_basic",
        "stock_basic",
        {"sample_stocks": "3_named_stocks", "code_format": "baostock_exchange_prefixed"},
        ("code", "code_name", "ipoDate", "outDate", "type", "status"),
        ("stock basic metadata can support non-production identity review",),
        ("formal universe construction remains blocked",),
    ),
    SmokeEndpointSpec(
        "baostock",
        "query_history_k_data_plus_raw_daily",
        "raw_daily",
        {"sample_stocks": "3_named_stocks", "date_window": "sample_window", "adjustflag": "3"},
        ("date", "code", "open", "high", "low", "close", "preclose", "volume", "amount", "tradestatus", "isST"),
        ("raw daily metadata can support non-production field availability review",),
        ("execution-realistic backtest remains blocked",),
    ),
    SmokeEndpointSpec(
        "baostock",
        "query_history_k_data_plus_qfq",
        "qfq_candidate",
        {"sample_stocks": "3_named_stocks", "date_window": "sample_window", "adjustflag": "2"},
        ("date", "code", "open", "high", "low", "close", "adjustflag"),
        ("qfq metadata can support research-only comparison",),
        ("formal adjusted return remains blocked",),
    ),
    SmokeEndpointSpec(
        "baostock",
        "query_history_k_data_plus_index_daily",
        "index_daily",
        {"sample_indexes": "HS300_CSI500", "date_window": "sample_window", "adjustflag": "3"},
        ("date", "code", "open", "high", "low", "close", "preclose", "volume", "amount", "pctChg"),
        ("index daily metadata can support research-only benchmark availability review",),
        ("formal excess return remains blocked",),
    ),
    SmokeEndpointSpec(
        "baostock",
        "query_history_k_data_plus_tradestatus_isst",
        "tradestatus_isst",
        {"sample_stocks": "3_named_stocks", "date_window": "sample_window", "fields_subset": "tradestatus_isST"},
        ("date", "code", "tradestatus", "isST"),
        ("tradestatus and isST can support execution candidate review",),
        ("real fills, failed orders, and partial fills remain blocked",),
    ),
    SmokeEndpointSpec(
        "akshare",
        "stock_zh_a_hist_raw_daily",
        "raw_daily",
        {"sample_stocks": "3_named_stocks", "date_window": "sample_window", "adjust": "none"},
        ("日期", "股票代码", "开盘", "收盘", "最高", "最低", "成交量", "成交额"),
        ("AKShare raw daily metadata can support cross-check review if available",),
        ("AKShare does not become the production primary source",),
    ),
    SmokeEndpointSpec(
        "akshare",
        "stock_zh_a_hist_qfq",
        "qfq_candidate",
        {"sample_stocks": "3_named_stocks", "date_window": "sample_window", "adjust": "qfq"},
        ("日期", "股票代码", "开盘", "收盘", "最高", "最低"),
        ("AKShare qfq metadata can support research-only cross-check review if available",),
        ("formal adjusted return remains blocked",),
    ),
    SmokeEndpointSpec(
        "akshare",
        "stock_zh_index_hist_csindex",
        "index_daily",
        {"sample_indexes": "HS300_CSI500", "date_window": "sample_window"},
        ("日期", "指数代码", "开盘", "最高", "最低", "收盘"),
        ("AKShare index metadata can support supplement review",),
        ("formal excess return remains blocked",),
    ),
    SmokeEndpointSpec(
        "akshare",
        "stock_tfp_em",
        "suspend_event",
        {"sample": "event_only_endpoint", "date_arg": "start_date_if_supported"},
        ("代码", "名称", "停牌时间", "停牌截止时间", "停牌原因", "预计复牌时间"),
        ("suspend-event metadata can support event-only review",),
        ("daily execution eligibility, failed orders, and partial fills remain blocked",),
    ),
)


def run_smoke(
    *,
    live: bool = False,
    scratch_root: Path | str = APPROVED_SCRATCH_ROOT,
    run_id: str | None = None,
    start_date: str = DEFAULT_START_DATE,
    end_date: str = DEFAULT_END_DATE,
) -> SmokeRunResult:
    """Run a dry metadata smoke by default, or a live smoke only when live=True."""

    resolved_run_id = run_id or _default_run_id(live=live)
    if live:
        approved_root = assert_repo_external_scratch(scratch_root)
        endpoint_summaries = tuple(
            _run_live_smoke(
                approved_root=approved_root,
                run_id=resolved_run_id,
                start_date=start_date,
                end_date=end_date,
            )
        )
    else:
        endpoint_summaries = tuple(_dry_run_records(resolved_run_id, start_date, end_date))

    markdown = render_smoke_markdown(endpoint_summaries, run_id=resolved_run_id, live=live)
    return SmokeRunResult(resolved_run_id, live, endpoint_summaries, markdown)


def render_smoke_markdown(
    endpoint_summaries: Sequence[Mapping[str, Any]],
    *,
    run_id: str,
    live: bool,
) -> str:
    """Render repo-safe Markdown and include opaque raw pointers."""

    _assert_repo_safe_summaries(endpoint_summaries)
    base = generate_redacted_report(
        endpoint_summaries,
        title="Prism Free-Source Repeatable Live Smoke Report",
    ).rstrip()
    pointer_lines = [
        "",
        "## Repeatable Runner Metadata",
        "",
        f"- Run id: `{_escape_markdown(run_id)}`",
        f"- Mode: `{'live' if live else 'dry_run'}`",
        "- Default mode does not call BaoStock or AKShare; live calls require explicit `--live`.",
        "",
        "## Raw Archive Pointers",
        "",
        "| Provider | Endpoint | Opaque Pointer |",
        "| --- | --- | --- |",
    ]
    for item in endpoint_summaries:
        pointer_lines.append(
            "| "
            + " | ".join(
                [
                    _table_cell(item.get("provider", "n/a")),
                    _table_cell(item.get("endpoint", "n/a")),
                    _table_cell(item.get("raw_archive_pointer", "none")),
                ]
            )
            + " |"
        )
    return base + "\n" + "\n".join(pointer_lines) + "\n"


def assert_repo_external_scratch(
    scratch_root: Path | str,
    *,
    approved_root: Path = APPROVED_SCRATCH_ROOT,
    repo_root: Path | None = None,
) -> Path:
    """Return an approved repo-external scratch root or raise ValueError."""

    candidate = Path(scratch_root).expanduser().resolve()
    approved = approved_root.expanduser().resolve()
    if candidate != approved and approved not in candidate.parents:
        raise ValueError("scratch root must be inside the approved repo-external free-data-poc root")
    current_repo = (repo_root or Path.cwd()).resolve()
    if candidate == current_repo or current_repo in candidate.parents:
        raise ValueError("scratch root must not be inside the repo")
    return candidate


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Prism free-source smoke metadata or explicit live smoke.")
    parser.add_argument("--live", action="store_true", help="Explicitly call BaoStock and AKShare.")
    parser.add_argument("--scratch-root", default=str(APPROVED_SCRATCH_ROOT), help="Repo-external scratch root.")
    parser.add_argument("--run-id", default=None, help="Optional opaque run id.")
    parser.add_argument("--start-date", default=DEFAULT_START_DATE, help="YYYY-MM-DD sample start date.")
    parser.add_argument("--end-date", default=DEFAULT_END_DATE, help="YYYY-MM-DD sample end date.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = run_smoke(
        live=args.live,
        scratch_root=args.scratch_root,
        run_id=args.run_id,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    print(result.markdown, end="")
    return 0


def _dry_run_records(run_id: str, start_date: str, end_date: str) -> list[Mapping[str, Any]]:
    records: list[Mapping[str, Any]] = []
    for spec in SMOKE_ENDPOINTS:
        fingerprint = _sha256_hex(
            {
                "mode": "dry_run",
                "run_id": run_id,
                "provider": spec.provider,
                "endpoint": spec.endpoint,
                "start_date": start_date,
                "end_date": end_date,
            }
        )
        records.append(
            _redacted_record(
                spec,
                run_id=run_id,
                status="blocked",
                row_count=0,
                field_list=(),
                non_null_summary={},
                response_hash=fingerprint,
                retrieved_at=_utc_now(),
                package_version="not_loaded_dry_run",
                error_summary="dry-run metadata only; pass --live to call providers",
                raw_archive_pointer=f"fs4b-dry-run:{run_id}:{spec.provider}:{spec.endpoint}:{fingerprint[:16]}",
                start_date=start_date,
                end_date=end_date,
            )
        )
    return records


def _run_live_smoke(
    *,
    approved_root: Path,
    run_id: str,
    start_date: str,
    end_date: str,
) -> list[Mapping[str, Any]]:
    run_root = approved_root / run_id
    raw_dir = run_root / "raw"
    redacted_dir = run_root / "redacted"
    raw_dir.mkdir(parents=True, exist_ok=True)
    redacted_dir.mkdir(parents=True, exist_ok=True)

    archive = _RawArchive(raw_dir=raw_dir, run_id=run_id)
    records: list[Mapping[str, Any]] = []
    records.extend(_run_baostock_live(run_id, archive, start_date, end_date))
    records.extend(_run_akshare_live(run_id, archive, start_date, end_date))

    manifest = {
        "run_id": run_id,
        "generated_at": _utc_now(),
        "mode": "live",
        "endpoint_summaries": records,
    }
    _assert_repo_safe_summaries(records)
    (redacted_dir / "redacted_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return records


def _run_baostock_live(
    run_id: str,
    archive: "_RawArchive",
    start_date: str,
    end_date: str,
) -> list[Mapping[str, Any]]:
    records: list[Mapping[str, Any]] = []
    spec_by_endpoint = {spec.endpoint: spec for spec in SMOKE_ENDPOINTS if spec.provider == "baostock"}
    try:
        bs = _load_provider_module("baostock")
    except Exception as exc:
        return [
            _error_record(spec, run_id, exc, "unknown", start_date, end_date)
            for spec in spec_by_endpoint.values()
        ]

    logged_in = False
    try:
        login = bs.login()
        logged_in = True
        archive.write("baostock", "login", _baostock_login_payload(login))
        if getattr(login, "error_code", "0") != "0":
            raise RuntimeError(_sanitize_error(f"BaoStock login failed: {getattr(login, 'error_code', '')}"))

        records.append(
            _baostock_query_record(
                spec_by_endpoint["query_trade_dates"],
                run_id,
                archive,
                "baostock",
                lambda: bs.query_trade_dates(start_date=start_date, end_date=end_date),
                start_date,
                end_date,
            )
        )
        records.append(
            _baostock_stock_basic_record(spec_by_endpoint["query_stock_basic"], run_id, archive, bs, start_date, end_date)
        )
        records.append(
            _baostock_history_record(
                spec_by_endpoint["query_history_k_data_plus_raw_daily"],
                run_id,
                archive,
                bs,
                start_date,
                end_date,
                adjustflag="3",
                target="stocks",
                fields="date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,isST",
            )
        )
        records.append(
            _baostock_history_record(
                spec_by_endpoint["query_history_k_data_plus_qfq"],
                run_id,
                archive,
                bs,
                start_date,
                end_date,
                adjustflag="2",
                target="stocks",
                fields="date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,isST",
            )
        )
        records.append(
            _baostock_history_record(
                spec_by_endpoint["query_history_k_data_plus_index_daily"],
                run_id,
                archive,
                bs,
                start_date,
                end_date,
                adjustflag="3",
                target="indexes",
                fields="date,code,open,high,low,close,preclose,volume,amount,pctChg",
            )
        )
        records.append(
            _baostock_history_record(
                spec_by_endpoint["query_history_k_data_plus_tradestatus_isst"],
                run_id,
                archive,
                bs,
                start_date,
                end_date,
                adjustflag="3",
                target="stocks",
                fields="date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,isST",
            )
        )
    except Exception as exc:
        seen = {record["endpoint"] for record in records}
        for spec in spec_by_endpoint.values():
            if spec.endpoint not in seen:
                records.append(_error_record(spec, run_id, exc, _package_version("baostock"), start_date, end_date))
    finally:
        if logged_in:
            try:
                bs.logout()
            except Exception:
                pass
    return records


def _run_akshare_live(
    run_id: str,
    archive: "_RawArchive",
    start_date: str,
    end_date: str,
) -> list[Mapping[str, Any]]:
    spec_by_endpoint = {spec.endpoint: spec for spec in SMOKE_ENDPOINTS if spec.provider == "akshare"}
    try:
        ak = _load_provider_module("akshare")
    except Exception as exc:
        return [
            _error_record(spec, run_id, exc, "unknown", start_date, end_date)
            for spec in spec_by_endpoint.values()
        ]
    return [
        _akshare_stock_hist_record(
            spec_by_endpoint["stock_zh_a_hist_raw_daily"],
            run_id,
            archive,
            ak,
            start_date,
            end_date,
            adjust="",
        ),
        _akshare_stock_hist_record(
            spec_by_endpoint["stock_zh_a_hist_qfq"],
            run_id,
            archive,
            ak,
            start_date,
            end_date,
            adjust="qfq",
        ),
        _akshare_index_record(spec_by_endpoint["stock_zh_index_hist_csindex"], run_id, archive, ak, start_date, end_date),
        _akshare_suspend_record(spec_by_endpoint["stock_tfp_em"], run_id, archive, ak, start_date, end_date),
    ]


def _baostock_query_record(
    spec: SmokeEndpointSpec,
    run_id: str,
    archive: "_RawArchive",
    provider_package: str,
    query: Callable[[], Any],
    start_date: str,
    end_date: str,
) -> Mapping[str, Any]:
    try:
        result = query()
        fields, items = _baostock_result_items(result)
        digest, pointer = archive.write(spec.provider, spec.endpoint, _vendor_payload(fields, items, result=result))
        return _record_from_items(spec, run_id, fields, items, digest, pointer, _package_version(provider_package), start_date, end_date)
    except Exception as exc:
        return _error_record(spec, run_id, exc, _package_version(provider_package), start_date, end_date)


def _baostock_stock_basic_record(
    spec: SmokeEndpointSpec,
    run_id: str,
    archive: "_RawArchive",
    bs: Any,
    start_date: str,
    end_date: str,
) -> Mapping[str, Any]:
    return _baostock_sample_aggregate(
        spec,
        run_id,
        archive,
        "baostock",
        STOCK_SAMPLES,
        lambda code: bs.query_stock_basic(code=code),
        "baostock",
        start_date,
        end_date,
    )


def _baostock_history_record(
    spec: SmokeEndpointSpec,
    run_id: str,
    archive: "_RawArchive",
    bs: Any,
    start_date: str,
    end_date: str,
    *,
    adjustflag: str,
    target: str,
    fields: str,
) -> Mapping[str, Any]:
    samples = STOCK_SAMPLES if target == "stocks" else INDEX_SAMPLES
    return _baostock_sample_aggregate(
        spec,
        run_id,
        archive,
        "baostock",
        samples,
        lambda code: bs.query_history_k_data_plus(
            code,
            fields,
            start_date=start_date,
            end_date=end_date,
            frequency="d",
            adjustflag=adjustflag,
        ),
        "baostock",
        start_date,
        end_date,
    )


def _baostock_sample_aggregate(
    spec: SmokeEndpointSpec,
    run_id: str,
    archive: "_RawArchive",
    provider_key: str,
    samples: Mapping[str, Mapping[str, str]],
    query_for_code: Callable[[str], Any],
    provider_package: str,
    start_date: str,
    end_date: str,
) -> Mapping[str, Any]:
    fields: list[str] = []
    items: list[Mapping[str, Any]] = []
    vendor_items: list[Mapping[str, Any]] = []
    errors: list[str] = []
    for sample_key, sample in samples.items():
        try:
            result = query_for_code(sample[provider_key])
            sample_fields, sample_items = _baostock_result_items(result)
            _extend_unique(fields, sample_fields)
            items.extend(sample_items)
            vendor_items.append(_vendor_payload(sample_fields, sample_items, result=result, sample_key=sample_key))
        except Exception as exc:
            errors.append(_sanitize_error(str(exc)))
            vendor_items.append({"sample_key": sample_key, "error_summary": _sanitize_error(str(exc))})
    digest, pointer = archive.write(spec.provider, spec.endpoint, {"items": vendor_items})
    return _record_from_items(
        spec,
        run_id,
        fields,
        items,
        digest,
        pointer,
        _package_version(provider_package),
        start_date,
        end_date,
        errors=errors,
    )


def _akshare_stock_hist_record(
    spec: SmokeEndpointSpec,
    run_id: str,
    archive: "_RawArchive",
    ak: Any,
    start_date: str,
    end_date: str,
    *,
    adjust: str,
) -> Mapping[str, Any]:
    start_ak = start_date.replace("-", "")
    end_ak = end_date.replace("-", "")
    return _akshare_sample_aggregate(
        spec,
        run_id,
        archive,
        STOCK_SAMPLES,
        lambda code: ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start_ak,
            end_date=end_ak,
            adjust=adjust,
        ),
        start_date,
        end_date,
    )


def _akshare_index_record(
    spec: SmokeEndpointSpec,
    run_id: str,
    archive: "_RawArchive",
    ak: Any,
    start_date: str,
    end_date: str,
) -> Mapping[str, Any]:
    start_ak = start_date.replace("-", "")
    end_ak = end_date.replace("-", "")
    return _akshare_sample_aggregate(
        spec,
        run_id,
        archive,
        INDEX_SAMPLES,
        lambda code: ak.stock_zh_index_hist_csindex(symbol=code, start_date=start_ak, end_date=end_ak),
        start_date,
        end_date,
    )


def _akshare_suspend_record(
    spec: SmokeEndpointSpec,
    run_id: str,
    archive: "_RawArchive",
    ak: Any,
    start_date: str,
    end_date: str,
) -> Mapping[str, Any]:
    try:
        kwargs = {}
        if "date" in inspect.signature(ak.stock_tfp_em).parameters:
            kwargs["date"] = start_date.replace("-", "")
        fields, items = _frame_items(ak.stock_tfp_em(**kwargs))
        digest, pointer = archive.write(spec.provider, spec.endpoint, {"fields": fields, "items": items})
        return _record_from_items(spec, run_id, fields, items, digest, pointer, _package_version("akshare"), start_date, end_date)
    except Exception as exc:
        return _error_record(spec, run_id, exc, _package_version("akshare"), start_date, end_date)


def _akshare_sample_aggregate(
    spec: SmokeEndpointSpec,
    run_id: str,
    archive: "_RawArchive",
    samples: Mapping[str, Mapping[str, str]],
    query_for_code: Callable[[str], Any],
    start_date: str,
    end_date: str,
) -> Mapping[str, Any]:
    fields: list[str] = []
    items: list[Mapping[str, Any]] = []
    vendor_items: list[Mapping[str, Any]] = []
    errors: list[str] = []
    for sample_key, sample in samples.items():
        try:
            sample_fields, sample_items = _frame_items(query_for_code(sample["akshare"]))
            _extend_unique(fields, sample_fields)
            items.extend(sample_items)
            vendor_items.append({"sample_key": sample_key, "fields": sample_fields, "items": sample_items})
        except Exception as exc:
            summary = _sanitize_error(str(exc))
            errors.append(summary)
            vendor_items.append({"sample_key": sample_key, "error_summary": summary})
    digest, pointer = archive.write(spec.provider, spec.endpoint, {"items": vendor_items})
    return _record_from_items(
        spec,
        run_id,
        fields,
        items,
        digest,
        pointer,
        _package_version("akshare"),
        start_date,
        end_date,
        errors=errors,
    )


def _record_from_items(
    spec: SmokeEndpointSpec,
    run_id: str,
    field_list: Sequence[str],
    items: Sequence[Mapping[str, Any]],
    response_hash: str,
    raw_archive_pointer: str,
    package_version: str,
    start_date: str,
    end_date: str,
    *,
    errors: Sequence[str] = (),
) -> Mapping[str, Any]:
    row_count = len(items)
    missing = [field for field in spec.expected_field_list if field not in field_list]
    status = _status_for(row_count=row_count, missing=missing, errors=errors)
    return _redacted_record(
        spec,
        run_id=run_id,
        status=status,
        row_count=row_count,
        field_list=field_list,
        non_null_summary=_non_null_summary(items, field_list),
        response_hash=response_hash,
        retrieved_at=_utc_now(),
        package_version=package_version,
        error_summary=_join_errors(errors),
        raw_archive_pointer=raw_archive_pointer,
        start_date=start_date,
        end_date=end_date,
    )


def _error_record(
    spec: SmokeEndpointSpec,
    run_id: str,
    exc: BaseException,
    package_version: str,
    start_date: str,
    end_date: str,
) -> Mapping[str, Any]:
    summary = _sanitize_error(f"{type(exc).__name__}: {exc}")
    response_hash = _sha256_hex({"provider": spec.provider, "endpoint": spec.endpoint, "error": summary})
    return _redacted_record(
        spec,
        run_id=run_id,
        status=_classify_error(summary),
        row_count=0,
        field_list=(),
        non_null_summary={},
        response_hash=response_hash,
        retrieved_at=_utc_now(),
        package_version=package_version,
        error_summary=summary,
        raw_archive_pointer=f"fs4b-live-smoke:{run_id}:{spec.provider}:{spec.endpoint}:{response_hash[:16]}",
        start_date=start_date,
        end_date=end_date,
    )


def _redacted_record(
    spec: SmokeEndpointSpec,
    *,
    run_id: str,
    status: str,
    row_count: int,
    field_list: Sequence[str],
    non_null_summary: Mapping[str, int],
    response_hash: str,
    retrieved_at: str,
    package_version: str,
    error_summary: str,
    raw_archive_pointer: str,
    start_date: str,
    end_date: str,
) -> Mapping[str, Any]:
    return {
        "provider": spec.provider,
        "endpoint": spec.endpoint,
        "adapter_layer": spec.adapter_layer,
        "params_summary": _params_for_window(spec.params_summary, start_date, end_date),
        "status": status,
        "row_count": row_count,
        "field_list": list(field_list),
        "expected_field_list": list(spec.expected_field_list),
        "missing_field_list": [field for field in spec.expected_field_list if field not in field_list],
        "non_null_summary": dict(non_null_summary),
        "response_hash_sha256": response_hash,
        "retrieved_at": retrieved_at,
        "package_version": package_version,
        "error_summary": error_summary,
        "raw_archive_pointer": raw_archive_pointer,
        "research_only_notes": list(spec.research_only_notes),
        "blocker_notes": list(spec.blocker_notes),
    }


def _params_for_window(params: Mapping[str, str], start_date: str, end_date: str) -> Mapping[str, str]:
    return {
        key: (f"{start_date}..{end_date}" if value == "sample_window" else value)
        for key, value in params.items()
    }


def _baostock_result_items(result: Any) -> tuple[list[str], list[Mapping[str, Any]]]:
    fields = [str(field) for field in getattr(result, "fields", [])]
    items: list[Mapping[str, Any]] = []
    while result.next():
        items.append(dict(zip(fields, result.get_row_data())))
    return fields, items


def _frame_items(frame: Any) -> tuple[list[str], list[Mapping[str, Any]]]:
    fields = [str(column) for column in list(frame.columns)]
    payload = frame.to_json(orient="records", force_ascii=False, date_format="iso")
    items = json.loads(payload)
    return fields, items


def _vendor_payload(
    fields: Sequence[str],
    items: Sequence[Mapping[str, Any]],
    *,
    result: Any | None = None,
    sample_key: str | None = None,
) -> Mapping[str, Any]:
    payload: dict[str, Any] = {"fields": list(fields), "items": list(items)}
    if sample_key:
        payload["sample_key"] = sample_key
    if result is not None:
        payload["error_code"] = getattr(result, "error_code", None)
        payload["error_msg"] = getattr(result, "error_msg", None)
    return payload


def _baostock_login_payload(login: Any) -> Mapping[str, Any]:
    return {
        "error_code": getattr(login, "error_code", None),
        "error_msg": getattr(login, "error_msg", None),
    }


def _status_for(*, row_count: int, missing: Sequence[str], errors: Sequence[str]) -> str:
    if row_count > 0 and (missing or errors):
        return "partial"
    if row_count > 0:
        return "available"
    if errors:
        return _classify_error(" ".join(errors))
    return "empty"


def _classify_error(summary: str) -> str:
    lowered = summary.lower()
    if any(marker in lowered for marker in NETWORK_ERROR_MARKERS):
        return "network_error"
    return "provider_error"


def _non_null_summary(items: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> Mapping[str, int]:
    counts = {field: 0 for field in fields}
    for item in items:
        for field in fields:
            value = item.get(field)
            if value is not None and value != "":
                counts[field] += 1
    return counts


def _join_errors(errors: Sequence[str]) -> str:
    if not errors:
        return ""
    unique: list[str] = []
    for error in errors:
        if error not in unique:
            unique.append(error)
    return "; ".join(unique)[:500]


def _sanitize_error(text: str) -> str:
    sanitized = URL_RE.sub("<url-redacted>", text)
    sanitized = LOCAL_PATH_RE.sub(" <path-redacted>", sanitized)
    return sanitized[:500]


def _assert_repo_safe_summaries(endpoint_summaries: Sequence[Mapping[str, Any]]) -> None:
    findings = find_redaction_issues(endpoint_summaries)
    if findings:
        details = "; ".join(f"{finding.path}: {finding.reason}" for finding in findings)
        raise ValueError(f"unsafe redacted smoke summary: {details}")


def _load_provider_module(provider: str) -> Any:
    return importlib.import_module(provider)


def _package_version(package_name: str) -> str:
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _default_run_id(*, live: bool) -> str:
    mode = "live" if live else "dry"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"fs4b-{mode}-smoke-{stamp}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256_hex(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _extend_unique(target: list[str], values: Sequence[str]) -> None:
    for value in values:
        if value not in target:
            target.append(value)


def _table_cell(value: Any) -> str:
    return _escape_markdown(str(value)).replace("\n", " ")


def _escape_markdown(value: str) -> str:
    return value.replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;")


@dataclass(frozen=True)
class _RawArchive:
    raw_dir: Path
    run_id: str

    def write(self, provider: str, endpoint: str, payload: Mapping[str, Any]) -> tuple[str, str]:
        digest = _sha256_hex(payload)
        artifact = f"{provider}_{endpoint}_{digest[:16]}.json"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        (self.raw_dir / artifact).write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str),
            encoding="utf-8",
        )
        pointer = f"fs4b-live-smoke:{self.run_id}:{provider}:{endpoint}:{digest[:16]}"
        return digest, pointer


if __name__ == "__main__":
    raise SystemExit(main())

