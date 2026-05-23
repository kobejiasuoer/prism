"""Integration test for the read-only data capability matrix endpoint."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


INVEST_FLOW_ROOT = Path(__file__).resolve().parents[2]
if str(INVEST_FLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(INVEST_FLOW_ROOT))

from fastapi.testclient import TestClient

from control_panel.app import app  # noqa: E402
from prism_data.manifest import DATASET_REGISTRY  # noqa: E402


REQUIRED_FIELDS = (
    "dataset",
    "description",
    "source_lane",
    "decision_scope",
    "primary_provider",
    "fallback_providers",
    "authority_provider",
    "target_authority_provider",
    "audit_providers",
    "required_for_live_small",
    "source_authority_ready",
    "formal_decision_allowed",
    "source_authority_semantics",
    "formal_decision_semantics",
    "risk_flags",
)


class DataCapabilityMatrixEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_returns_200(self) -> None:
        response = self.client.get("/api/data-capability-matrix")
        self.assertEqual(response.status_code, 200)

    def test_payload_shape(self) -> None:
        body = self.client.get("/api/data-capability-matrix").json()
        self.assertIn("schema_version", body)
        self.assertIn("entry_count", body)
        self.assertIn("summary", body)
        self.assertIn("datasets", body)
        self.assertIsInstance(body["datasets"], list)
        self.assertEqual(body["entry_count"], len(DATASET_REGISTRY))
        self.assertEqual(len(body["datasets"]), len(DATASET_REGISTRY))

    def test_summary_block_present(self) -> None:
        body = self.client.get("/api/data-capability-matrix").json()
        summary = body["summary"]
        for key in (
            "total",
            "formal_ready",
            "display_only",
            "pending_target_authority",
            "pipeline_datasets",
            "required_for_live_small",
            "formal_lane_not_ready",
        ):
            self.assertIn(key, summary)
        self.assertEqual(summary["total"], len(DATASET_REGISTRY))

    def test_registry_issues_present_and_clean(self) -> None:
        body = self.client.get("/api/data-capability-matrix").json()
        self.assertIn("registry_issues", body)
        self.assertIsInstance(body["registry_issues"], list)
        self.assertEqual(
            body["registry_issues"],
            [],
            f"real DATASET_REGISTRY has validation issues: {body['registry_issues']}",
        )

    def test_each_entry_has_required_fields(self) -> None:
        body = self.client.get("/api/data-capability-matrix").json()
        for entry in body["datasets"]:
            with self.subTest(dataset=entry.get("dataset")):
                for field in REQUIRED_FIELDS:
                    self.assertIn(field, entry, f"missing {field} for {entry.get('dataset')}")

    def test_covers_all_registry_datasets(self) -> None:
        body = self.client.get("/api/data-capability-matrix").json()
        returned = {entry["dataset"] for entry in body["datasets"]}
        self.assertEqual(returned, set(DATASET_REGISTRY.keys()))

    def test_display_only_entries_never_formal(self) -> None:
        body = self.client.get("/api/data-capability-matrix").json()
        display_only = [e for e in body["datasets"] if e["decision_scope"] == "display_only"]
        self.assertGreater(len(display_only), 0)
        for entry in display_only:
            with self.subTest(dataset=entry["dataset"]):
                self.assertFalse(entry["formal_decision_allowed"])
                self.assertIn("display_only", entry["risk_flags"])


if __name__ == "__main__":
    unittest.main()
