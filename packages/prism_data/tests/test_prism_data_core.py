"""Core tests for prism_data manifests, freshness, and gateway persistence."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGES_DIR = REPO_ROOT / "packages"
if str(PACKAGES_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGES_DIR))

from prism_data.contracts import DatasetStatus, ProviderResult, ProviderRole  # noqa: E402
from prism_data.datasets import validate_bars_dataset, validate_quotes_dataset  # noqa: E402
from prism_data.freshness import compute_freshness_status, update_manifest_freshness  # noqa: E402
from prism_data.gateway import DataGateway  # noqa: E402
from prism_data.manifest import DATASET_REGISTRY, DataManifest, build_pipeline_manifest, get_dataset_definition  # noqa: E402
from prism_data.repositories import DatasetRepository  # noqa: E402


class FakeProvider:
    def __init__(self, name: str, *, status: DatasetStatus = DatasetStatus.OK, data=None, trade_date: str = "2026-05-07", live_small_allowed: bool = True):
        self.name = name
        self.status = status
        self.data = data if data is not None else {"code": "600690", "price": 27.34}
        self.trade_date = trade_date
        self.live_small_allowed = live_small_allowed

    def fetch_quote(self, code: str, **kwargs):
        now = datetime.now()
        return ProviderResult(
            status=self.status,
            data=self.data if self.status == DatasetStatus.OK else None,
            provider=self.name,
            provider_role=ProviderRole.PRIMARY,
            dataset="quotes.snapshot",
            trade_date=self.trade_date,
            fetched_at=now,
            asof=now,
            ttl_seconds=900,
            error=None if self.status == DatasetStatus.OK else "boom",
            payload_hash="",
            live_small_allowed=self.live_small_allowed,
        )

    def fetch_quotes_batch(self, codes: list[str], **kwargs):
        now = datetime.now()
        rows = [{"code": code, "price": 10.0 + idx} for idx, code in enumerate(codes)]
        return ProviderResult(
            status=DatasetStatus.OK,
            data=rows,
            provider=self.name,
            provider_role=ProviderRole.PRIMARY,
            dataset="quotes.batch",
            trade_date=self.trade_date,
            fetched_at=now,
            asof=now,
            ttl_seconds=900,
            live_small_allowed=True,
        )


class ContractsTests(unittest.TestCase):
    def test_data_manifest_roundtrip(self) -> None:
        original = DataManifest(
            schema_version=1,
            dataset="quotes.snapshot",
            provider="sina",
            provider_role="primary",
            trade_date="2026-05-07",
            fetched_at="2026-05-07 10:30:00",
            asof="2026-05-07 10:29:00",
            ttl_seconds=900,
            status="ok",
            freshness_status="fresh",
            fallback_used=False,
            row_count=1,
            payload_hash="abc",
            live_small_allowed=True,
        )
        restored = DataManifest.from_dict(original.to_dict())
        self.assertEqual(restored.dataset, original.dataset)
        self.assertEqual(restored.provider, original.provider)
        self.assertTrue(restored.live_small_allowed)

    def test_dataset_registry_has_core_datasets(self) -> None:
        self.assertIn("quotes.snapshot", DATASET_REGISTRY)
        self.assertIn("bars.daily", DATASET_REGISTRY)
        self.assertIn("screening.batch", DATASET_REGISTRY)

    def test_get_dataset_definition(self) -> None:
        definition = get_dataset_definition("quotes.snapshot")
        self.assertIsNotNone(definition)
        self.assertEqual(definition.name, "quotes.snapshot")
        self.assertEqual(definition.primary_provider, "sina")
        self.assertIn("eastmoney", definition.fallback_providers)


class FreshnessTests(unittest.TestCase):
    def test_fresh_when_within_ttl_and_trade_date_matches(self) -> None:
        status = compute_freshness_status(
            fetched_at=datetime(2026, 5, 7, 10, 20, 0),
            ttl_seconds=900,
            trade_date="2026-05-07",
            expected_trade_date="2026-05-07",
            now=datetime(2026, 5, 7, 10, 30, 0),
        )
        self.assertEqual(status, "fresh")

    def test_update_manifest_freshness(self) -> None:
        manifest = {
            "fetched_at": "2026-05-07 10:20:00",
            "ttl_seconds": 900,
            "trade_date": "2026-05-07",
        }
        updated = update_manifest_freshness(manifest, "2026-05-07", datetime(2026, 5, 7, 10, 30, 0))
        self.assertEqual(updated["freshness_status"], "fresh")


class GatewayTests(unittest.TestCase):
    def test_gateway_persists_success_manifest_and_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repository = DatasetRepository(tmpdir)
            gateway = DataGateway(
                providers={
                    "sina": FakeProvider("sina"),
                    "eastmoney": FakeProvider("eastmoney"),
                },
                repository=repository,
            )
            result = gateway.fetch_quote("600690", trade_date="2026-05-07", key="600690")
            self.assertEqual(result.manifest["dataset"], "quotes.snapshot")
            self.assertEqual(result.manifest["provider"], "sina")
            self.assertEqual(result.manifest["freshness_status"], "fresh")
            self.assertTrue(result.manifest["live_small_allowed"])
            self.assertTrue(Path(result.data_path or "").exists())
            self.assertTrue(Path(result.manifest_path).exists())
            self.assertLessEqual(result.manifest["ttl_seconds"], DATASET_REGISTRY["quotes.snapshot"].ttl_intraday)

    def test_gateway_persists_attempt_manifest_and_blocks_fallback_for_live_small(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repository = DatasetRepository(tmpdir)
            gateway = DataGateway(
                providers={
                    "sina": FakeProvider("sina", status=DatasetStatus.FAILED),
                    "eastmoney": FakeProvider("eastmoney"),
                },
                repository=repository,
            )
            result = gateway.fetch_quote("600690", trade_date="2026-05-07", key="600690", allow_fallback=True)
            self.assertEqual(result.manifest["provider"], "eastmoney")
            self.assertTrue(result.manifest["fallback_used"])
            self.assertFalse(result.manifest["live_small_allowed"])
            self.assertGreaterEqual(len(result.attempt_manifests), 2)

    def test_pipeline_manifest_requires_group_presence(self) -> None:
        manifest = build_pipeline_manifest(
            dataset="screening.batch",
            trade_date="2026-05-07",
            payload={"ok": True},
            upstream_manifests=[],
            ttl_seconds=900,
            required_dataset_groups=[{"screening.scan_result"}],
        )
        self.assertFalse(manifest["live_small_allowed"])
        self.assertIn("missing_required_dataset_group:screening.scan_result", manifest["quality_flags"])


class DatasetsTests(unittest.TestCase):
    def test_validate_quotes_dataset(self) -> None:
        self.assertTrue(validate_quotes_dataset([{"code": "600690", "price": 27.34}]))
        self.assertFalse(validate_quotes_dataset({"code": "600690"}))

    def test_validate_bars_dataset(self) -> None:
        self.assertTrue(validate_bars_dataset([{"code": "600690", "trade_date": "2026-05-07", "close": 27.34}]))
        self.assertFalse(validate_bars_dataset([{"code": "600690"}]))


if __name__ == "__main__":
    unittest.main()
