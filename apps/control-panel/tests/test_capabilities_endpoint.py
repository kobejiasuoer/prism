"""Integration tests for the Phase 1 read-only capability + budget endpoints."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


INVEST_FLOW_ROOT = Path(__file__).resolve().parents[2]
if str(INVEST_FLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(INVEST_FLOW_ROOT))

from fastapi.testclient import TestClient

from control_panel.app import app  # noqa: E402


class SourceBudgetEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_returns_200(self) -> None:
        response = self.client.get("/api/source-budget")
        self.assertEqual(response.status_code, 200)

    def test_payload_shape(self) -> None:
        body = self.client.get("/api/source-budget").json()
        self.assertIn("datasets", body)
        datasets = body["datasets"]
        self.assertIsInstance(datasets, list)
        self.assertGreaterEqual(len(datasets), 15)
        sample = datasets[0]
        for key in (
            "dataset", "label", "role", "cost_class", "cadence", "batchable",
            "min_refresh_interval_seconds", "primary_provider",
            "fallback_providers", "decision_scope", "supports_capabilities",
            "failure_impact",
        ):
            self.assertIn(key, sample, f"missing {key} in /api/source-budget payload")


if __name__ == "__main__":
    unittest.main()
