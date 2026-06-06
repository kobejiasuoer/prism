from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock


INVEST_FLOW_ROOT = Path(__file__).resolve().parents[2]
if str(INVEST_FLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(INVEST_FLOW_ROOT))

PACKAGES_ROOT = INVEST_FLOW_ROOT / "packages"
if str(PACKAGES_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGES_ROOT))

from dataset_manifests import build_dataset_freshness_rows, build_formal_freshness_rows  # noqa: E402
from prism_data.repositories import DatasetRepository  # noqa: E402


class DatasetManifestFreshnessTests(unittest.TestCase):
    def test_quotes_batch_uses_business_target_freshness_before_ttl(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repository = DatasetRepository(Path(tmpdir))
            manifest = {
                "dataset": "quotes.batch",
                "provider": "eastmoney",
                "trade_date": "2026-05-08",
                "fetched_at": "2026-05-08 10:48:30",
                "asof": "2026-05-08 10:48:30",
                "ttl_seconds": 120,
                "status": "ok",
                "freshness_status": "fresh",
                "live_small_allowed": True,
                "fallback_used": False,
            }
            repository.save_manifest("quotes.batch", "2026-05-08", "auto-quotes", manifest)

            with mock.patch.dict("os.environ", {"PRISM_DATASET_REPOSITORY_ROOT": tmpdir}):
                rows = build_dataset_freshness_rows(
                    expected_date="2026-05-08",
                    now=datetime(2026, 5, 8, 10, 50, 0),
                    datasets=("quotes.batch",),
                )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertTrue(row["stale"])
        self.assertEqual(row["stale_after_seconds"], 60)
        self.assertEqual(row["ttl_seconds"], 120)
        self.assertIn("freshness_stale", row["stale_reasons"])

    def test_quotes_batch_uses_post_close_tolerance_after_close(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repository = DatasetRepository(Path(tmpdir))
            manifest = {
                "dataset": "quotes.batch",
                "provider": "eastmoney",
                "trade_date": "2026-05-08",
                "fetched_at": "2026-05-08 15:00:01",
                "asof": "2026-05-08 15:00:01",
                "ttl_seconds": 120,
                "status": "ok",
                "freshness_status": "fresh",
                "live_small_allowed": True,
                "fallback_used": False,
            }
            repository.save_manifest("quotes.batch", "2026-05-08", "close-quotes", manifest)

            with mock.patch.dict("os.environ", {"PRISM_DATASET_REPOSITORY_ROOT": tmpdir}):
                rows = build_dataset_freshness_rows(
                    expected_date="2026-05-08",
                    now=datetime(2026, 5, 8, 20, 0, 0),
                    datasets=("quotes.batch",),
                )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertFalse(row["stale"])
        self.assertEqual(row["stale_after_seconds"], 86400)
        self.assertEqual(row["ttl_seconds"], 86400)

    def test_latest_dataset_row_prefers_successful_manifest_over_newer_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repository = DatasetRepository(Path(tmpdir))
            repository.save_manifest(
                "quotes.batch",
                "2026-05-08",
                "auto-quotes",
                {
                    "dataset": "quotes.batch",
                    "provider": "eastmoney",
                    "trade_date": "2026-05-08",
                    "fetched_at": "2026-05-08 10:00:00",
                    "asof": "2026-05-08 10:00:00",
                    "ttl_seconds": 120,
                    "status": "ok",
                    "live_small_allowed": True,
                    "fallback_used": False,
                },
            )
            repository.save_manifest(
                "quotes.batch",
                "2026-05-08",
                "auto-quotes__eastmoney__primary",
                {
                    "dataset": "quotes.batch",
                    "provider": "eastmoney",
                    "trade_date": "2026-05-08",
                    "fetched_at": "2026-05-08 10:10:00",
                    "ttl_seconds": 120,
                    "status": "failed",
                    "error": "502 Bad Gateway",
                    "live_small_allowed": False,
                    "fallback_used": False,
                },
            )

            with mock.patch.dict("os.environ", {"PRISM_DATASET_REPOSITORY_ROOT": tmpdir}):
                rows = build_dataset_freshness_rows(
                    expected_date="2026-05-08",
                    now=datetime(2026, 5, 8, 10, 11, 0),
                    datasets=("quotes.batch",),
                )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertTrue(row["available"])
        self.assertEqual(row["provider"], "eastmoney")
        self.assertNotIn("manifest_status_failed", row["stale_reasons"])
        self.assertNotIn("provider_failure", row["stale_reasons"])

    def test_display_only_dataset_does_not_emit_live_small_policy_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repository = DatasetRepository(Path(tmpdir))
            manifest = {
                "dataset": "fundamentals.batch",
                "provider": "tushare",
                "trade_date": "2026-05-07",
                "fetched_at": "2026-05-08 10:00:00",
                "asof": "2026-05-08 10:00:00",
                "ttl_seconds": 43200,
                "status": "ok",
                "live_small_allowed": False,
                "fallback_used": False,
            }
            repository.save_manifest("fundamentals.batch", "2026-05-08", "scan-fundamentals", manifest)

            with mock.patch.dict("os.environ", {"PRISM_DATASET_REPOSITORY_ROOT": tmpdir}):
                rows = build_dataset_freshness_rows(
                    expected_date="2026-05-08",
                    now=datetime(2026, 5, 8, 10, 5, 0),
                    datasets=("fundamentals.batch",),
                )

        self.assertEqual(len(rows), 1)
        self.assertNotIn("live_small_not_allowed", rows[0]["stale_reasons"])
        self.assertNotIn("trade_date_mismatch", rows[0]["stale_reasons"])
        self.assertIn("freshness_stale", rows[0]["stale_reasons"])

    def test_formal_daily_rows_accept_previous_trading_day_before_close(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repository = DatasetRepository(Path(tmpdir))
            manifest = {
                "dataset": "bars.daily",
                "provider": "tushare",
                "provider_role": "primary",
                "trade_date": "2026-05-29",
                "fetched_at": "2026-06-01 09:20:00",
                "asof": "2026-06-01 09:20:00",
                "ttl_seconds": 86400,
                "status": "ok",
                "freshness_status": "fresh",
                "live_small_allowed": True,
                "fallback_used": False,
                "payload_hash": "unit-bars-hash",
                "source_authority_ready": True,
                "formal_decision_allowed": True,
                "manifest_path": "/tmp/bars.daily.manifest.json",
            }
            repository.save_manifest("bars.daily", "2026-05-29", "600690", manifest)

            with mock.patch.dict("os.environ", {"PRISM_DATASET_REPOSITORY_ROOT": tmpdir}), mock.patch(
                "dataset_manifests.list_active_watchlist_stocks",
                return_value=[{"code": "600690"}],
            ):
                rows = build_formal_freshness_rows(
                    expected_date="2026-06-01",
                    now=datetime(2026, 6, 1, 10, 0, 0),
                    datasets=("bars.daily",),
                )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertFalse(row["stale"])
        self.assertEqual(row["trade_date"], "2026-05-29")
        self.assertEqual(row["expected_trade_date"], "2026-06-01")
        self.assertEqual(row["reference_trade_date"], "2026-05-29")
        self.assertTrue(row["formal_decision_allowed"])

    def test_formal_adjustment_factor_accepts_previous_trading_day_before_close(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repository = DatasetRepository(Path(tmpdir))
            manifest = {
                "dataset": "adjustment.factor",
                "request_key": "600690",
                "provider": "tushare",
                "provider_role": "primary",
                "trade_date": "2026-05-29",
                "fetched_at": "2026-06-01 09:21:00",
                "asof": "2026-06-01 09:21:00",
                "ttl_seconds": 86400,
                "status": "ok",
                "freshness_status": "fresh",
                "live_small_allowed": True,
                "fallback_used": False,
                "payload_hash": "unit-adjustment-hash",
                "source_authority_ready": True,
                "formal_decision_allowed": True,
                "manifest_path": "/tmp/adjustment.factor.manifest.json",
            }
            repository.save_manifest("adjustment.factor", "2026-05-29", "600690", manifest)

            with mock.patch.dict("os.environ", {"PRISM_DATASET_REPOSITORY_ROOT": tmpdir}), mock.patch(
                "dataset_manifests.list_active_watchlist_stocks",
                return_value=[{"code": "600690"}],
            ):
                rows = build_formal_freshness_rows(
                    expected_date="2026-06-01",
                    now=datetime(2026, 6, 1, 10, 0, 0),
                    datasets=("adjustment.factor",),
                )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertFalse(row["stale"])
        self.assertEqual(row["trade_date"], "2026-05-29")
        self.assertEqual(row["expected_trade_date"], "2026-06-01")
        self.assertEqual(row["reference_trade_date"], "2026-05-29")
        self.assertTrue(row["formal_decision_allowed"])


if __name__ == "__main__":
    unittest.main()
