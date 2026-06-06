from __future__ import annotations

import importlib.util
import sys
from datetime import datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROL_PANEL_ROOT = REPO_ROOT / "apps" / "control-panel"
PACKAGES_ROOT = REPO_ROOT / "packages"
for import_path in (str(REPO_ROOT), str(CONTROL_PANEL_ROOT), str(PACKAGES_ROOT)):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)


def _load_script() -> ModuleType:
    module_name = "refresh_formal_data_test"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, REPO_ROOT / "apps" / "scripts" / "refresh_formal_data.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class FakeRepository:
    def __init__(self, manifests: dict[tuple[str, str, str], dict[str, object]] | None = None) -> None:
        self.manifests = manifests or {}

    def load_manifest(self, dataset: str, trade_date: str, key: str) -> dict[str, object] | None:
        manifest = self.manifests.get((dataset, trade_date, key))
        return dict(manifest) if manifest else None


class FakeProvider:
    def __init__(self, result) -> None:
        self.result = result
        self.calls: list[list[str]] = []

    def fetch_index_daily_batch(self, symbols: list[str], **_kwargs):
        self.calls.append(list(symbols))
        return self.result


class FakeGateway:
    def __init__(self, provider: FakeProvider, repository: FakeRepository) -> None:
        self.providers = {"tushare": provider}
        self.repository = repository

    def _effective_ttl_seconds(self, _dataset: str, ttl_seconds: int) -> int:
        return int(ttl_seconds or 86400)

    def _finalize(self, *, request_key: str, expected_trade_date: str, result, attempt_manifest_paths: list[str]):
        ok = str(result.status) == "ok" or getattr(result.status, "value", "") == "ok"
        manifest = {
            "dataset": result.dataset,
            "request_key": request_key,
            "provider": result.provider,
            "status": getattr(result.status, "value", str(result.status)),
            "freshness_status": "fresh" if ok else "expired",
            "trade_date": result.trade_date,
            "row_count": result.row_count,
            "live_small_allowed": bool(result.live_small_allowed),
            "source_authority_ready": bool(ok and result.live_small_allowed),
            "formal_decision_allowed": bool(ok and result.live_small_allowed),
            "quality_flags": list(result.quality_flags or []),
            "error": result.error,
            "payload_hash": result.payload_hash or ("unit-hash" if ok else ""),
        }
        return SimpleNamespace(
            dataset=result.dataset,
            request_key=request_key,
            data=result.data,
            manifest=manifest,
            data_path=None,
            manifest_path="/tmp/unit.manifest.json",
            provider_result=result,
            attempt_manifests=attempt_manifest_paths,
        )


def _provider_result(*, status, data=None, trade_date: str = "2026-05-07", flags: list[str] | None = None, error: str | None = None):
    script = _load_script()
    return script.ProviderResult(
        status=status,
        data=data,
        provider="tushare",
        provider_role=script.ProviderRole.PRIMARY,
        dataset="benchmark.index_daily",
        trade_date=trade_date,
        fetched_at=datetime(2026, 5, 7, 15, 30, 0),
        ttl_seconds=86400,
        error=error,
        payload_hash="unit-payload" if data else "",
        row_count=len(data) if isinstance(data, list) else 0,
        quality_flags=flags or [],
        license_scope="authorized_tushare_token",
        live_small_allowed=status == script.DatasetStatus.OK and not flags,
    )


def _formal_manifest(key: str) -> dict[str, object]:
    return {
        "dataset": "benchmark.index_daily",
        "request_key": key,
        "provider": "tushare",
        "status": "ok",
        "freshness_status": "fresh",
        "trade_date": "2026-05-07",
        "row_count": 1,
        "live_small_allowed": True,
        "source_authority_ready": True,
        "formal_decision_allowed": True,
        "quality_flags": [],
        "payload_hash": "existing-formal-hash",
    }


def test_tushare_index_batch_limit_defaults_to_one_pending_symbol() -> None:
    script = _load_script()
    result = _provider_result(
        status=script.DatasetStatus.OK,
        data=[
            {
                "symbol": "000300.SH",
                "ts_code": "000300.SH",
                "trade_date": "2026-05-07",
                "close": 1.0,
            }
        ],
    )
    repository = FakeRepository()
    provider = FakeProvider(result)
    gateway = FakeGateway(provider, repository)
    results: list[dict[str, object]] = []
    errors: list[str] = []
    deferred: list[dict[str, object]] = []

    script._run_index_daily_batch(
        results,
        errors,
        gateway=gateway,
        repository=repository,
        indexes=["000300", "000905"],
        trade_date="2026-05-07",
        start_date="2026-01-01",
        provider_name="tushare",
        reuse_existing=True,
        index_batch_limit=None,
        deferred=deferred,
    )

    assert errors == []
    assert provider.calls == [["000300"]]
    assert [item["request_key"] for item in results] == ["000300"]
    assert deferred == [
        {
            "dataset": "benchmark.index_daily",
            "request_key": "000905",
            "trade_date": "2026-05-07",
            "reason": "index_daily_hourly_rate_limit_window",
            "provider": "tushare",
        }
    ]


def test_index_batch_limit_zero_refreshes_all_pending_symbols() -> None:
    script = _load_script()
    result = _provider_result(
        status=script.DatasetStatus.OK,
        data=[
            {"symbol": "000300.SH", "ts_code": "000300.SH", "trade_date": "2026-05-07"},
            {"symbol": "000905.SH", "ts_code": "000905.SH", "trade_date": "2026-05-07"},
        ],
    )
    repository = FakeRepository()
    provider = FakeProvider(result)
    gateway = FakeGateway(provider, repository)
    results: list[dict[str, object]] = []
    deferred: list[dict[str, object]] = []

    script._run_index_daily_batch(
        results,
        [],
        gateway=gateway,
        repository=repository,
        indexes=["000300", "000905"],
        trade_date="2026-05-07",
        start_date="2026-01-01",
        provider_name="tushare",
        reuse_existing=True,
        index_batch_limit=0,
        deferred=deferred,
    )

    assert provider.calls == [["000300", "000905"]]
    assert [item["request_key"] for item in results] == ["000300", "000905"]
    assert deferred == []


def test_formal_refresh_outcome_reports_deferred_refreshes_as_partial_success() -> None:
    script = _load_script()

    outcome = script._formal_refresh_outcome(
        errors=[],
        hard_failures=[],
        deferred=[{"dataset": "benchmark.index_daily", "request_key": "000905"}],
    )

    assert outcome == {
        "ok": True,
        "complete": False,
        "partial_ok": True,
        "status": "partial",
    }


def test_formal_refresh_outcome_reports_complete_when_no_work_is_deferred() -> None:
    script = _load_script()

    outcome = script._formal_refresh_outcome(errors=[], hard_failures=[], deferred=[])

    assert outcome == {
        "ok": True,
        "complete": True,
        "partial_ok": False,
        "status": "success",
    }


def test_index_batch_failure_reports_existing_formal_manifest_as_reused() -> None:
    script = _load_script()
    result = _provider_result(
        status=script.DatasetStatus.UNAVAILABLE,
        error="抱歉，您访问接口(index_daily)频率超限(1次/小时)",
        flags=["provider_rate_limited", "provider_hourly_rate_limited"],
    )
    repository = FakeRepository({
        ("benchmark.index_daily", "2026-05-07", "000300"): _formal_manifest("000300"),
    })
    provider = FakeProvider(result)
    gateway = FakeGateway(provider, repository)
    results: list[dict[str, object]] = []

    script._run_index_daily_batch(
        results,
        [],
        gateway=gateway,
        repository=repository,
        indexes=["000300"],
        trade_date="2026-05-07",
        start_date="2026-01-01",
        provider_name="tushare",
        reuse_existing=False,
        index_batch_limit=None,
        deferred=[],
    )

    assert provider.calls == [["000300"]]
    assert results[0]["status"] == "ok"
    assert results[0]["reused_existing"] is True
    assert results[0]["skip_reason"] == "restored_after_refresh_failure"
    assert results[0]["refresh_attempt_quality_flags"] == ["provider_rate_limited", "provider_hourly_rate_limited"]
