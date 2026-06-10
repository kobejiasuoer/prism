from __future__ import annotations

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient


INVEST_FLOW_ROOT = Path(__file__).resolve().parents[2]
if str(INVEST_FLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(INVEST_FLOW_ROOT))

PACKAGES_ROOT = INVEST_FLOW_ROOT / "packages"
if str(PACKAGES_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGES_ROOT))


class FormalDataStatusTests(unittest.TestCase):
    def test_status_api_defaults_to_compact_payload_but_keeps_full_detail_on_request(self) -> None:
        app_module = importlib.import_module("control_panel.app")
        payload = {
            "generated_at": "2026-06-10 09:30:00",
            "expected_trade_date": "2026-06-10",
            "provider": {
                "name": "tushare",
                "token_configured": True,
                "token_env_names": ["PRISM_TUSHARE_TOKEN", "TUSHARE_TOKEN"],
                "configured_token_env_names": ["PRISM_TUSHARE_TOKEN"],
                "api_url": "https://api.tushare.pro",
                "token_value_visible": False,
                "local_env_path": "/tmp/prism/.env",
                "local_env_file_exists": True,
            },
            "source_plan": [
                {
                    "dataset": "bars.daily",
                    "provider": "tushare",
                    "source_apis": ["daily"],
                    "required_permission": "Tushare daily",
                    "docs": ["https://example.com/docs/daily"],
                }
            ],
            "setup_steps": ["step one", "step two"],
            "ready": False,
            "ready_count": 0,
            "total_count": 1,
            "blocked_count": 1,
            "datasets": [
                {
                    "key": "bars.daily",
                    "dataset": "bars.daily",
                    "label": "正式日线",
                    "provider": "tushare",
                    "authority_provider": "tushare",
                    "target_authority_provider": "tushare",
                    "trade_date": "2026-06-10",
                    "available": False,
                    "stale": True,
                    "freshness_status": "missing",
                    "setup_state": "permission_or_points_blocked",
                    "next_action": "开通接口权限。",
                    "source_apis": ["daily", "adj_factor", "stock_basic", "trade_cal"],
                    "required_permission": "Tushare daily",
                    "docs": ["https://example.com/docs/daily"],
                    "key_states": [
                        {
                            "request_key": "600000",
                            "status": "blocked",
                            "manifest_path": "/tmp/heavy.manifest.json",
                        }
                    ],
                    "manifest_path": "/tmp/heavy.manifest.json",
                    "missing_request_keys": ["600000", "600519", "000001", "300750"],
                    "blocked_request_keys": ["600000", "600519", "000001", "300750"],
                    "quality_flags": ["permission_missing", "rate_limited", "slow_provider", "heavy"],
                    "error": "permission denied",
                }
            ],
            "blockers": [
                {
                    "dataset": "bars.daily",
                    "label": "正式日线",
                    "state": "permission_or_points_blocked",
                    "next_action": "开通接口权限。",
                    "source_apis": ["daily", "adj_factor", "stock_basic", "trade_cal"],
                    "required_permission": "Tushare daily",
                    "docs": ["https://example.com/docs/daily"],
                    "missing_request_keys": ["600000", "600519", "000001", "300750"],
                    "blocked_request_keys": ["600000", "600519", "000001", "300750"],
                    "quality_flags": ["permission_missing", "rate_limited", "slow_provider", "heavy"],
                    "error": "permission denied",
                }
            ],
            "last_run": {
                "run_id": "run-heavy",
                "task_name": "formal_data_refresh",
                "status": "failed",
                "log_path": "/tmp/heavy.log",
                "meta_path": "/tmp/heavy.meta.json",
                "command": ["python", "apps/scripts/refresh_formal_data.py"],
            },
            "running": False,
            "recommended_task": {
                "task_name": "formal_data_refresh",
                "title": "正式口径数据刷新",
            },
        }

        with mock.patch.object(app_module, "build_formal_data_status_payload", return_value=payload):
            client = TestClient(app_module.app)
            compact = client.get("/api/formal-data/status").json()
            full = client.get("/api/formal-data/status?compact=0").json()

        self.assertTrue(compact["compact"])
        self.assertNotIn("source_plan", compact)
        self.assertNotIn("setup_steps", compact)
        self.assertNotIn("api_url", compact["provider"])
        self.assertNotIn("local_env_path", compact["provider"])
        self.assertNotIn("token_value_visible", compact["provider"])
        self.assertNotIn("docs", compact["datasets"][0])
        self.assertNotIn("key_states", compact["datasets"][0])
        self.assertNotIn("manifest_path", compact["datasets"][0])
        self.assertNotIn("docs", compact["blockers"][0])
        self.assertNotIn("log_path", compact["last_run"])
        self.assertEqual(compact["datasets"][0]["source_apis"], ["daily", "adj_factor", "stock_basic"])
        self.assertEqual(compact["datasets"][0]["blocked_request_keys"], ["600000", "600519", "000001"])
        self.assertTrue(compact["datasets"][0]["has_manifest"])

        self.assertIn("source_plan", full)
        self.assertIn("setup_steps", full)
        self.assertIn("api_url", full["provider"])
        self.assertIn("docs", full["datasets"][0])
        self.assertIn("key_states", full["datasets"][0])
        self.assertEqual(full["datasets"][0]["manifest_path"], "/tmp/heavy.manifest.json")

    def test_status_reads_token_from_project_env_without_exposing_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".env").write_text("PRISM_TUSHARE_TOKEN=unit-env-token-123456\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"PRISM_REPO_ROOT": str(root)}, clear=True):
                app_module = importlib.import_module("control_panel.app")
                with mock.patch.object(app_module, "REPO_ROOT", root):
                    payload = app_module.build_formal_data_status_payload()

        provider = payload["provider"]
        self.assertTrue(provider["token_configured"])
        self.assertEqual(provider["configured_token_env_names"], ["PRISM_TUSHARE_TOKEN"])
        self.assertFalse(provider["token_value_visible"])
        self.assertNotIn("unit-env-token-123456", str(payload))

    def test_missing_token_marks_absent_formal_dataset_as_token_missing(self) -> None:
        app_module = importlib.import_module("control_panel.app")
        row = {
            "dataset": "bars.daily",
            "label": "正式日线",
            "available": False,
            "stale": True,
            "manifest_path": "",
            "formal_decision_allowed": False,
            "target_authority_provider": "tushare",
            "authority_provider": "tushare",
            "stale_reasons": ["manifest_missing"],
            "quality_flags": [],
        }

        self.assertEqual(app_module._formal_row_state(row, token_configured=False), "token_missing")

    def test_existing_formal_manifest_is_not_reclassified_as_token_missing(self) -> None:
        app_module = importlib.import_module("control_panel.app")
        row = {
            "dataset": "bars.daily",
            "label": "正式日线",
            "available": True,
            "stale": True,
            "manifest_path": "/tmp/bars.daily.manifest.json",
            "formal_decision_allowed": False,
            "target_authority_provider": "tushare",
            "authority_provider": "tushare",
            "stale_reasons": ["trade_date_mismatch"],
            "quality_flags": [],
        }

        self.assertEqual(app_module._formal_row_state(row, token_configured=False), "stale_or_misaligned")

    def test_status_payload_cache_honors_fresh_bypass(self) -> None:
        app_module = importlib.import_module("control_panel.app")
        status_globals = app_module.build_formal_data_status_payload.__globals__
        original_cache = status_globals["_FORMAL_DATA_STATUS_CACHE"]
        original_ttl = status_globals["FORMAL_DATA_STATUS_CACHE_TTL_SECONDS"]
        status_globals["_FORMAL_DATA_STATUS_CACHE"] = None
        status_globals["FORMAL_DATA_STATUS_CACHE_TTL_SECONDS"] = 20
        builder = mock.Mock(
            side_effect=[
                {"generated_at": "formal-first", "provider": {}},
                {"generated_at": "formal-fresh", "provider": {}},
            ]
        )
        try:
            with (
                mock.patch.dict(
                    status_globals,
                    {
                        "_formal_data_status_cache_key": mock.Mock(return_value=("env", (), None)),
                        "_build_formal_data_status_payload_uncached": builder,
                    },
                ),
            ):
                first = app_module.build_formal_data_status_payload()
                cached = app_module.build_formal_data_status_payload()
                fresh = app_module.build_formal_data_status_payload(fresh=True)
        finally:
            status_globals["_FORMAL_DATA_STATUS_CACHE"] = original_cache
            status_globals["FORMAL_DATA_STATUS_CACHE_TTL_SECONDS"] = original_ttl

        self.assertEqual(first["generated_at"], "formal-first")
        self.assertEqual(cached["generated_at"], "formal-first")
        self.assertEqual(fresh["generated_at"], "formal-fresh")
        self.assertEqual(builder.call_count, 2)


if __name__ == "__main__":
    unittest.main()
