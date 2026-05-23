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
    budgets_critical_for_capability,
    budgets_important_for_capability,
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
                self.assertGreater(budget.provider_min_interval_seconds, 0)
                self.assertGreater(budget.target_freshness_seconds, 0)
                self.assertTrue(budget.primary_provider)
                self.assertIn(budget.decision_scope, {"live_small", "display_only"})
                # Either critical_for or important_for must list at least one capability.
                self.assertTrue(
                    budget.critical_for or budget.important_for,
                    f"{key} declares no supported capabilities",
                )
                for cap in budget.critical_for + budget.important_for:
                    self.assertIn(cap, KNOWN_CAPABILITIES, f"{key} bad capability: {cap}")
                # No capability should appear in both critical_for and important_for.
                overlap = set(budget.critical_for) & set(budget.important_for)
                self.assertFalse(overlap, f"{key} has overlap between critical/important: {overlap}")
                self.assertTrue(budget.failure_impact, f"{key} missing failure_impact")

    def test_provider_min_interval_not_above_target_freshness(self) -> None:
        # We cannot promise freshness X if we cannot poll fast enough to refresh by X.
        for key, budget in SOURCE_BUDGETS.items():
            with self.subTest(key=key):
                self.assertLessEqual(
                    budget.provider_min_interval_seconds,
                    budget.target_freshness_seconds,
                    f"{key}: provider_min_interval ({budget.provider_min_interval_seconds}) "
                    f"exceeds target_freshness ({budget.target_freshness_seconds}); cannot meet that freshness",
                )

    def test_target_freshness_not_above_intraday_ttl(self) -> None:
        # Operator's tolerance must not exceed the technical validity window.
        for key, budget in SOURCE_BUDGETS.items():
            if key not in DATASET_REGISTRY:
                continue
            with self.subTest(key=key):
                ttl = DATASET_REGISTRY[key].ttl_intraday
                self.assertLessEqual(
                    budget.target_freshness_seconds,
                    ttl,
                    f"{key}: target_freshness ({budget.target_freshness_seconds}) "
                    f"exceeds ttl_intraday ({ttl}); data declared invalid before operator would refresh",
                )

    def test_observe_is_never_critical(self) -> None:
        # observe is the always-permissive view; nothing should hard-block it.
        for key, budget in SOURCE_BUDGETS.items():
            with self.subTest(key=key):
                self.assertNotIn(
                    "observe", budget.critical_for,
                    f"{key}: observe must not be critical_for (it is the permissive view)",
                )

    def test_trade_has_critical_account_and_quotes(self) -> None:
        critical_for_trade = {b.dataset for b in budgets_critical_for_capability("trade")}
        self.assertIn("account.book", critical_for_trade)
        self.assertIn("quotes.batch", critical_for_trade)


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

    def test_budgets_critical_vs_important_partition(self) -> None:
        crit = {b.dataset for b in budgets_critical_for_capability("review")}
        imp = {b.dataset for b in budgets_important_for_capability("review")}
        self.assertFalse(crit & imp, "no dataset may be both critical and important for the same capability")

    def test_budgets_for_capability_observe_is_permissive(self) -> None:
        observe = budgets_for_capability("observe")
        self.assertGreaterEqual(len(observe), 4, "observe should cover at least market_data + watchlist")

    def test_budgets_for_role_market_data(self) -> None:
        keys = {item.dataset for item in budgets_for_role("market_data")}
        self.assertIn("quotes.batch", keys)
        self.assertIn("capital_flow.batch", keys)

    def test_supports_capabilities_is_derived(self) -> None:
        budget = source_budget("watchlist.snapshot")
        assert budget is not None
        # Union of critical_for + important_for, no duplicates.
        self.assertEqual(
            set(budget.supports_capabilities),
            set(budget.critical_for) | set(budget.important_for),
        )

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
            "provider_min_interval_seconds",
            "target_freshness_seconds",
            "primary_provider",
            "fallback_providers",
            "decision_scope",
            "critical_for",
            "important_for",
            "supports_capabilities",
            "failure_impact",
        ):
            self.assertIn(key, sample, f"payload row missing {key}")


if __name__ == "__main__":
    unittest.main()
