from __future__ import annotations

import ast
from pathlib import Path

import pytest

from quant.free_sources.contracts import BLOCKED_CAPABILITIES, FIELD_CONTRACTS, ResearchStatus
from quant.free_sources.manifest import (
    AdapterLayer,
    ManifestStatus,
    ManifestValidationError,
    validate_manifest,
)


ALLOWED_SOURCE_FILES = [
    Path("packages/quant/free_sources/__init__.py"),
    Path("packages/quant/free_sources/manifest.py"),
    Path("packages/quant/free_sources/contracts.py"),
    Path("packages/quant/free_sources/redaction.py"),
]

FORBIDDEN_IMPORT_ROOTS = {
    "akshare",
    "baostock",
    "curl_cffi",
    "httpx",
    "requests",
    "socket",
    "urllib",
}


def valid_manifest() -> dict:
    return {
        "schema_version": "free_source_manifest_v1",
        "run_id": "fs1-synthetic-run",
        "provider": "baostock",
        "provider_role": "primary",
        "source_version": {
            "package": "synthetic",
            "docs_url": "redacted-docs-ref",
        },
        "adapter_layer": "calendar",
        "endpoint": "query_trade_dates",
        "params_fingerprint_sha256": "a" * 64,
        "params_redacted": {
            "date_window": "2024-01-02..2024-01-10",
            "symbol_count": 0,
        },
        "retrieved_at": "2026-04-30T00:00:00+08:00",
        "response_hash_sha256": "b" * 64,
        "hash_method": "canonical_payload_sha256",
        "row_count": 7,
        "field_list": ["calendar_date", "is_trading_day"],
        "expected_field_list": ["calendar_date", "is_trading_day"],
        "missing_field_list": [],
        "non_null_summary": {
            "calendar_date": 7,
            "is_trading_day": 7,
        },
        "duplicate_summary": {
            "key_duplicates": 0,
        },
        "coverage_summary": {
            "date_window": "2024-01-02..2024-01-10",
            "observed_date_count": 7,
        },
        "status": "available",
        "license_usage_note": {
            "raw_archive_allowed": "unknown",
            "redistribution": "not_allowed",
        },
        "pit_asof_status": "as_collected_only",
        "raw_archive_pointer": "fs1-synthetic-run/calendar/f820f40c",
        "repo_safe": True,
    }


def test_valid_synthetic_manifest_passes() -> None:
    assert validate_manifest(valid_manifest()) is True


def test_status_enum_covers_required_values() -> None:
    assert {item.value for item in ManifestStatus} == {
        "available",
        "partial",
        "missing",
        "empty",
        "network_error",
        "provider_error",
        "license_blocked",
        "blocked",
    }


@pytest.mark.parametrize(
    "pointer",
    [
        "/Users/example/.prism-private/raw.json",
        "~/private/raw.json",
        "./raw.json",
        "../raw.json",
        "file:///tmp/raw.json",
        "http://example.com/raw.json",
        "https://example.com/raw.json",
        "s3://access:secret@bucket/raw.json",
        "opaque-pointer?token=abc",
    ],
)
def test_unsafe_raw_archive_pointer_is_rejected(pointer: str) -> None:
    manifest = valid_manifest()
    manifest["raw_archive_pointer"] = pointer
    with pytest.raises(ManifestValidationError):
        validate_manifest(manifest)


@pytest.mark.parametrize(
    "bad_key,bad_value",
    [
        ("rows", [{"open": "1.0"}]),
        ("records", [{"close": "1.0"}]),
        ("ohlcv_rows", [{"date": "2024-01-02"}]),
        ("prices", [1, 2, 3]),
        ("open_values", [1, 2, 3]),
        ("close_values", [1, 2, 3]),
        ("calendar_dates", ["2024-01-02", "2024-01-03"]),
        ("stock_list", ["600519", "300750"]),
        ("suspend_event_rows", [{"code": "600519"}]),
        ("limit_pool_constituents", ["600519"]),
        ("raw_response", "raw"),
        ("payload", {"vendor": "raw"}),
        ("body", "<html></html>"),
        ("html", "<html></html>"),
        ("csv", "a,b"),
        ("dataframe", "not allowed"),
        ("json_rows", [{"x": 1}]),
        ("token", "secret"),
        ("cookie", "secret"),
        ("session", "secret"),
        ("password", "secret"),
        ("secret", "secret"),
        ("authorization", "Bearer secret"),
    ],
)
def test_non_redacted_content_and_secret_like_keys_are_rejected(bad_key: str, bad_value: object) -> None:
    manifest = valid_manifest()
    manifest["params_redacted"] = {bad_key: bad_value}
    with pytest.raises(ManifestValidationError):
        validate_manifest(manifest)


def test_contracts_keep_formal_outputs_blocked() -> None:
    blocked = {item.capability: item.status for item in BLOCKED_CAPABILITIES}
    assert blocked["formal_adjusted_return"] == ResearchStatus.BLOCKED
    assert blocked["formal_excess_return"] == ResearchStatus.BLOCKED
    assert blocked["formal_labels"] == ResearchStatus.BLOCKED
    assert blocked["execution_realistic_backtest"] == ResearchStatus.BLOCKED
    assert blocked["limit_up_down_price"] == ResearchStatus.BLOCKED
    assert blocked["failed_order"] == ResearchStatus.BLOCKED
    assert blocked["partial_fill"] == ResearchStatus.BLOCKED

    by_layer = {}
    for contract in FIELD_CONTRACTS:
        by_layer.setdefault(contract.adapter_layer, set()).add(contract.research_status)

    assert by_layer[AdapterLayer.QFQ_CANDIDATE] <= {ResearchStatus.RESEARCH_ONLY, ResearchStatus.PARTIAL}
    assert by_layer[AdapterLayer.INDEX_DAILY] <= {ResearchStatus.CANDIDATE}
    assert by_layer[AdapterLayer.TRADESTATUS_ISST] <= {ResearchStatus.CANDIDATE}
    assert by_layer[AdapterLayer.SUSPEND_EVENT] <= {ResearchStatus.PARTIAL}
    assert by_layer[AdapterLayer.LIMIT_CANDIDATE] <= {ResearchStatus.BLOCKED}


def test_modules_have_no_provider_or_network_imports() -> None:
    for source_file in ALLOWED_SOURCE_FILES:
        tree = ast.parse(source_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            else:
                continue
            roots = {name.split(".", 1)[0] for name in names}
            assert roots.isdisjoint(FORBIDDEN_IMPORT_ROOTS), f"{source_file} imports {roots & FORBIDDEN_IMPORT_ROOTS}"


def test_manifest_validation_does_not_write_data_quant() -> None:
    data_quant = Path("data/quant")
    before = sorted(path.relative_to(data_quant) for path in data_quant.rglob("*")) if data_quant.exists() else []
    assert validate_manifest(valid_manifest()) is True
    after = sorted(path.relative_to(data_quant) for path in data_quant.rglob("*")) if data_quant.exists() else []
    assert after == before
