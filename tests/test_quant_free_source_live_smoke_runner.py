from __future__ import annotations

import ast
from pathlib import Path

import pytest

from quant.free_sources import live_smoke_runner


RUNNER_SOURCE = Path("packages/quant/free_sources/live_smoke_runner.py")

FORBIDDEN_IMPORT_ROOTS = {
    "akshare",
    "baostock",
    "curl_cffi",
    "httpx",
    "requests",
    "socket",
    "urllib",
}

FORBIDDEN_PRODUCTION_IMPORTS = {
    "apps",
    "stock_analyzer",
    "stock_screener",
}


def test_default_run_is_dry_metadata_only(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_provider_load(provider: str) -> object:
        raise AssertionError(f"provider load should not happen in dry-run: {provider}")

    monkeypatch.setattr(live_smoke_runner, "_load_provider_module", fail_provider_load)

    result = live_smoke_runner.run_smoke(live=False, run_id="fs4b-test-dry")

    assert result.live is False
    assert result.run_id == "fs4b-test-dry"
    assert len(result.endpoint_summaries) == len(live_smoke_runner.SMOKE_ENDPOINTS)
    assert {item["status"] for item in result.endpoint_summaries} == {"blocked"}
    assert {item["package_version"] for item in result.endpoint_summaries} == {"not_loaded_dry_run"}
    assert "Mode: `dry_run`" in result.markdown
    assert "Default mode does not call BaoStock or AKShare" in result.markdown
    assert "/Users/" not in result.markdown
    assert "formal-ready" not in result.markdown.lower()


def test_live_mode_requires_explicit_flag_and_can_be_synthetic(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    def fake_live_smoke(**kwargs: object) -> list[dict]:
        calls.append(dict(kwargs))
        return [
            {
                "provider": "baostock",
                "endpoint": "query_trade_dates",
                "adapter_layer": "calendar",
                "params_summary": {"date_window": "2024-01-02..2024-01-10"},
                "status": "available",
                "row_count": 9,
                "field_list": ["calendar_date", "is_trading_day"],
                "expected_field_list": ["calendar_date", "is_trading_day"],
                "missing_field_list": [],
                "non_null_summary": {"calendar_date": 9, "is_trading_day": 9},
                "response_hash_sha256": "a" * 64,
                "retrieved_at": "2026-05-01T00:00:00+00:00",
                "package_version": "synthetic",
                "error_summary": "",
                "raw_archive_pointer": "fs4b-live-smoke:test:baostock:query_trade_dates:aaaaaaaa",
                "research_only_notes": ["calendar metadata remains research-only"],
                "blocker_notes": ["formal labels remain blocked"],
            }
        ]

    monkeypatch.setattr(live_smoke_runner, "_run_live_smoke", fake_live_smoke)

    result = live_smoke_runner.run_smoke(
        live=True,
        scratch_root=str(Path.home() / ".prism-private/free-data-poc/synthetic-test"),
        run_id="fs4b-test-live",
    )

    assert len(calls) == 1
    assert result.live is True
    assert "Mode: `live`" in result.markdown
    assert "fs4b-live-smoke:test:baostock:query_trade_dates:aaaaaaaa" in result.markdown


def test_cli_defaults_to_dry_run() -> None:
    parser = live_smoke_runner.build_arg_parser()

    assert parser.parse_args([]).live is False
    assert parser.parse_args(["--live"]).live is True


def test_scratch_root_must_be_repo_external_and_approved() -> None:
    repo_root = Path.cwd()
    approved = live_smoke_runner.assert_repo_external_scratch(
        str(Path.home() / ".prism-private/free-data-poc/fs4b-test"),
        repo_root=repo_root,
    )
    assert str(approved).endswith(".prism-private/free-data-poc/fs4b-test")

    with pytest.raises(ValueError):
        live_smoke_runner.assert_repo_external_scratch(
            str(repo_root / "data/quant"),
            repo_root=repo_root,
        )

    with pytest.raises(ValueError):
        live_smoke_runner.assert_repo_external_scratch(
            "/tmp/free-data-poc",
            repo_root=repo_root,
        )


@pytest.mark.parametrize(
    "bad_key,bad_value",
    [
        ("rows", [{"date": "2024-01-02"}]),
        ("raw_response", {"vendor": "payload"}),
        ("payload", {"vendor": "payload"}),
        ("token", "secret"),
    ],
)
def test_renderer_rejects_raw_or_secret_like_metadata(bad_key: str, bad_value: object) -> None:
    record = dict(live_smoke_runner.run_smoke(live=False, run_id="fs4b-test-dry").endpoint_summaries[0])
    record[bad_key] = bad_value

    with pytest.raises(ValueError):
        live_smoke_runner.render_smoke_markdown([record], run_id="fs4b-test-dry", live=False)


def test_renderer_rejects_unsafe_raw_archive_pointer() -> None:
    record = dict(live_smoke_runner.run_smoke(live=False, run_id="fs4b-test-dry").endpoint_summaries[0])
    record["raw_archive_pointer"] = "/Users/example/raw.json"

    with pytest.raises(ValueError):
        live_smoke_runner.render_smoke_markdown([record], run_id="fs4b-test-dry", live=False)


def test_runner_has_no_top_level_provider_network_or_production_imports() -> None:
    tree = ast.parse(RUNNER_SOURCE.read_text(encoding="utf-8"))
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])

    assert imported_roots.isdisjoint(FORBIDDEN_IMPORT_ROOTS)
    assert imported_roots.isdisjoint(FORBIDDEN_PRODUCTION_IMPORTS)


def test_dry_run_does_not_write_data_quant() -> None:
    data_quant = Path("data/quant")
    before = sorted(path.relative_to(data_quant) for path in data_quant.rglob("*")) if data_quant.exists() else []
    result = live_smoke_runner.run_smoke(live=False, run_id="fs4b-test-dry")
    assert result.endpoint_summaries
    after = sorted(path.relative_to(data_quant) for path in data_quant.rglob("*")) if data_quant.exists() else []
    assert after == before

