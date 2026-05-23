"""Tests for source_budget — the business profile registry layered on top of
``packages/prism_data/manifest.py``.

These tests guard the contract that SOURCE_BUDGETS stays in sync with the
upstream DATASET_REGISTRY and that every entry carries the business fields
that capability_matrix relies on.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


INVEST_FLOW_ROOT = Path(__file__).resolve().parents[2]
if str(INVEST_FLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(INVEST_FLOW_ROOT))

# Make ``packages/`` reachable so prism_data imports work in tests.
PACKAGES_ROOT = INVEST_FLOW_ROOT / "packages"
if str(PACKAGES_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGES_ROOT))

from source_budget import (  # noqa: E402
    SourceBudget,
    SOURCE_BUDGETS,
    budgets_for_capability,
    budgets_for_role,
    build_source_budget_payload,
    source_budget,
)
from prism_data.manifest import DATASET_REGISTRY  # noqa: E402


KNOWN_CAPABILITIES = {"observe", "review", "approve", "trade", "notify", "ledger_capture"}
KNOWN_ROLES = {"market_data", "fundamentals", "news", "pipeline_artifact", "account"}
KNOWN_COSTS = {"cheap", "moderate", "heavy"}
KNOWN_CADENCES = {"intraday_high", "intraday_medium", "daily", "event"}


class SourceBudgetRegistryTests(unittest.TestCase):
    def test_registry_subset_of_manifest_datasets(self) -> None:
        # Every budget MUST reference a real dataset (except special "account.book"
        # which is internal-only and documented as an exception).
        manifest_keys = set(DATASET_REGISTRY.keys()) | {"account.book"}
        budget_keys = set(SOURCE_BUDGETS.keys())
        unknown = budget_keys - manifest_keys
        self.assertFalse(unknown, f"SOURCE_BUDGETS references unknown datasets: {unknown}")

    def test_every_budget_has_required_fields(self) -> None:
        for key, budget in SOURCE_BUDGETS.items():
            with self.subTest(key=key):
                self.assertIsInstance(budget, SourceBudget)
                self.assertEqual(budget.dataset, key)
                self.assertTrue(budget.label, f"{key} missing label")
                self.assertIn(budget.role, KNOWN_ROLES, f"{key} bad role: {budget.role}")
                self.assertIn(budget.cost_class, KNOWN_COSTS, f"{key} bad cost_class")
                self.assertIn(budget.cadence, KNOWN_CADENCES, f"{key} bad cadence")
                self.assertGreater(budget.min_refresh_interval_seconds, 0)
                self.assertTrue(budget.primary_provider)
                self.assertIn(budget.decision_scope, {"live_small", "display_only"})
                self.assertTrue(budget.supports_capabilities, f"{key} missing capabilities")
                for cap in budget.supports_capabilities:
                    self.assertIn(cap, KNOWN_CAPABILITIES, f"{key} bad capability: {cap}")
                self.assertTrue(budget.failure_impact, f"{key} missing failure_impact")

    def test_min_refresh_interval_does_not_exceed_intraday_ttl(self) -> None:
        # min_refresh_interval is a *business* lower bound; it must not request
        # data more frequently than the TTL declares the data can change.
        for key, budget in SOURCE_BUDGETS.items():
            if key not in DATASET_REGISTRY:
                continue
            with self.subTest(key=key):
                ttl = DATASET_REGISTRY[key].ttl_intraday
                self.assertLessEqual(
                    budget.min_refresh_interval_seconds,
                    ttl,
                    f"{key}: min_refresh_interval ({budget.min_refresh_interval_seconds}) "
                    f"exceeds ttl_intraday ({ttl}); business should not poll faster than TTL allows",
                )


class SourceBudgetQueryTests(unittest.TestCase):
    def test_source_budget_lookup(self) -> None:
        budget = source_budget("quotes.batch")
        self.assertIsNotNone(budget)
        self.assertEqual(budget.dataset, "quotes.batch")

    def test_source_budget_unknown_returns_none(self) -> None:
        self.assertIsNone(source_budget("does.not.exist"))

    def test_budgets_for_capability_trade_includes_quotes(self) -> None:
        keys = {item.dataset for item in budgets_for_capability("trade")}
        self.assertIn("quotes.batch", keys, "trade capability must require quotes.batch")
        self.assertIn("watchlist.snapshot", keys, "trade capability must require watchlist")

    def test_budgets_for_capability_observe_is_permissive(self) -> None:
        observe = budgets_for_capability("observe")
        self.assertGreaterEqual(len(observe), 4, "observe should cover at least market_data + watchlist")

    def test_budgets_for_role_market_data(self) -> None:
        keys = {item.dataset for item in budgets_for_role("market_data")}
        self.assertIn("quotes.batch", keys)
        self.assertIn("capital_flow.batch", keys)

    def test_build_payload_shape(self) -> None:
        payload = build_source_budget_payload()
        self.assertIn("datasets", payload)
        self.assertIsInstance(payload["datasets"], list)
        self.assertGreaterEqual(len(payload["datasets"]), 15)
        sample = payload["datasets"][0]
        for key in (
            "dataset",
            "label",
            "role",
            "cost_class",
            "cadence",
            "batchable",
            "min_refresh_interval_seconds",
            "primary_provider",
            "fallback_providers",
            "decision_scope",
            "supports_capabilities",
            "failure_impact",
        ):
            self.assertIn(key, sample, f"payload row missing {key}")


if __name__ == "__main__":
    unittest.main()
