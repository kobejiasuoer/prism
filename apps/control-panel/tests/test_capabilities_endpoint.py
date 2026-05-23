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


class CapabilitiesEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_returns_200(self) -> None:
        response = self.client.get("/api/capabilities")
        self.assertEqual(response.status_code, 200)

    def test_returns_six_capabilities(self) -> None:
        body = self.client.get("/api/capabilities").json()
        self.assertIn("capabilities", body)
        caps = body["capabilities"]
        for name in ("observe", "review", "approve", "trade", "notify", "ledger_capture"):
            self.assertIn(name, caps, f"missing capability {name}")

    def test_each_capability_has_required_fields(self) -> None:
        body = self.client.get("/api/capabilities").json()
        for name, report in body["capabilities"].items():
            with self.subTest(capability=name):
                for field in (
                    "capability", "status", "granted",
                    "why_not", "degraded_path", "next_actions",
                    "blocking_sources", "last_checked_at",
                ):
                    self.assertIn(field, report, f"{name} missing {field}")

    def test_includes_top_level_metadata(self) -> None:
        body = self.client.get("/api/capabilities").json()
        self.assertIn("checked_at", body)
        self.assertIn("session", body)


class ReadinessLiveExtensionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_existing_keys_still_present(self) -> None:
        body = self.client.get("/api/readiness/live").json()
        for key in (
            "generated_at", "expected_trade_date", "data_trade_date",
            "display_date", "trade_date", "readiness_mode", "ready", "session",
            "stale_count", "blockers", "warnings", "source_freshness",
            "quality_freshness", "recommended_tasks",
        ):
            self.assertIn(key, body, f"/api/readiness/live regression: {key} missing")

    def test_new_keys_added(self) -> None:
        body = self.client.get("/api/readiness/live").json()
        self.assertIn("source_states", body)
        self.assertIn("capabilities", body)
        self.assertIsInstance(body["source_states"], dict)
        self.assertIsInstance(body["capabilities"], dict)


if __name__ == "__main__":
    unittest.main()
