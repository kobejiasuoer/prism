from __future__ import annotations

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


INVEST_FLOW_ROOT = Path(__file__).resolve().parents[2]
if str(INVEST_FLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(INVEST_FLOW_ROOT))

PACKAGES_ROOT = INVEST_FLOW_ROOT / "packages"
if str(PACKAGES_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGES_ROOT))


class FormalDataStatusTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
