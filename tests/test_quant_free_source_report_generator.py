from __future__ import annotations

import ast
from pathlib import Path

import pytest

from quant.free_sources.report_generator import ReportGenerationError, generate_redacted_report


REPORT_GENERATOR = Path("packages/quant/free_sources/report_generator.py")

FORBIDDEN_IMPORT_ROOTS = {
    "akshare",
    "baostock",
    "curl_cffi",
    "httpx",
    "requests",
    "socket",
    "urllib",
}


def redacted_endpoint() -> dict:
    return {
        "provider": "baostock",
        "endpoint": "query_history_k_data_plus",
        "status": "available",
        "row_count": 21,
        "field_list": ["date", "code", "open", "high", "low", "close"],
        "non_null_summary": {
            "date": 21,
            "code": 21,
            "open": 21,
            "close": 21,
        },
        "response_hash_sha256": "a" * 64,
        "retrieved_at": "2026-04-30T15:47:29+00:00",
        "error_summary": "",
        "raw_archive_pointer": "fs4a-synthetic/baostock/raw-daily/aaaaaaaa",
        "research_only_notes": [
            "raw daily metadata can support non-production field availability review",
        ],
        "blocker_notes": [
            "formal labels remain blocked",
            "execution-realistic backtest remains blocked",
        ],
    }


def test_redacted_manifest_generates_markdown() -> None:
    markdown = generate_redacted_report([redacted_endpoint()])

    assert markdown.startswith("# Prism Free-Source Redacted Availability Report")
    assert "| baostock | query_history_k_data_plus | available | 21 |" in markdown
    assert "`date`, `code`, `open`, `high`, `low`, `close`" in markdown
    assert "`close=21`" in markdown
    assert "`aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`" in markdown
    assert "`2026-04-30T15:47:29+00:00`" in markdown
    assert "research-only evidence" in markdown
    assert "remain blocked" in markdown


def test_collection_mapping_generates_markdown() -> None:
    endpoint = redacted_endpoint()
    endpoint["provider"] = "akshare"
    endpoint["endpoint"] = "stock_zh_index_hist_csindex"
    endpoint["response_hash"] = endpoint.pop("response_hash_sha256")

    markdown = generate_redacted_report({"endpoint_summaries": [endpoint]}, title="Synthetic Availability")

    assert markdown.startswith("# Synthetic Availability")
    assert "akshare" in markdown
    assert "stock_zh_index_hist_csindex" in markdown


@pytest.mark.parametrize(
    "bad_key,bad_value",
    [
        ("rows", [{"date": "2024-01-02", "close": "1.0"}]),
        ("ohlcv_rows", [{"open": "1.0"}]),
        ("raw_response", {"vendor": "payload"}),
        ("payload", {"x": "raw"}),
        ("calendar_dates", ["2024-01-02", "2024-01-03"]),
        ("stock_list", ["600519", "300750"]),
        ("suspend_event_rows", [{"code": "600519"}]),
        ("token", "secret"),
        ("cookie", "secret"),
        ("session", "secret"),
        ("authorization", "Bearer secret"),
    ],
)
def test_raw_payload_and_secret_like_content_is_rejected(bad_key: str, bad_value: object) -> None:
    endpoint = redacted_endpoint()
    endpoint[bad_key] = bad_value

    with pytest.raises(ReportGenerationError):
        generate_redacted_report([endpoint])


@pytest.mark.parametrize(
    "pointer",
    [
        "/Users/example/.prism-private/raw.json",
        "file:///tmp/raw.json",
        "https://example.com/raw.json",
        "s3://bucket/raw.json",
        "opaque-pointer?token=abc",
    ],
)
def test_unsafe_raw_archive_pointer_is_rejected(pointer: str) -> None:
    endpoint = redacted_endpoint()
    endpoint["raw_archive_pointer"] = pointer

    with pytest.raises(ReportGenerationError):
        generate_redacted_report([endpoint])


@pytest.mark.parametrize(
    "field,value",
    [
        ("error_summary", "debug file at /Users/example/raw.json"),
        ("error_summary", "see file:///tmp/raw.json"),
        ("research_only_notes", ["approved for production after smoke"]),
        ("blocker_notes", ["formal-ready after qfq"]),
    ],
)
def test_unsafe_paths_urls_and_formal_ready_claims_are_rejected(field: str, value: object) -> None:
    endpoint = redacted_endpoint()
    endpoint[field] = value

    with pytest.raises(ReportGenerationError):
        generate_redacted_report([endpoint])


def test_generated_report_does_not_claim_formal_ready_status() -> None:
    markdown = generate_redacted_report([redacted_endpoint()])
    lowered = markdown.lower()

    assert "formal-ready" not in lowered
    assert "production-ready" not in lowered
    assert "approved for production" not in lowered
    assert "formal labels remain blocked" in lowered
    assert "formal adjusted return" in lowered


def test_report_generator_has_no_provider_or_network_imports() -> None:
    tree = ast.parse(REPORT_GENERATOR.read_text(encoding="utf-8"))
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])

    assert imported_roots.isdisjoint(FORBIDDEN_IMPORT_ROOTS)


def test_report_generation_does_not_write_data_quant() -> None:
    data_quant = Path("data/quant")
    before = sorted(path.relative_to(data_quant) for path in data_quant.rglob("*")) if data_quant.exists() else []
    assert "baostock" in generate_redacted_report([redacted_endpoint()])
    after = sorted(path.relative_to(data_quant) for path in data_quant.rglob("*")) if data_quant.exists() else []
    assert after == before

