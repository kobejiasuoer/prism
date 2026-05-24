"""Tests for the static data capability matrix derived from DATASET_REGISTRY."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGES_DIR = REPO_ROOT / "packages"
if str(PACKAGES_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGES_DIR))

from prism_data.data_capability_matrix import (  # noqa: E402
    DataCapabilityEntry,
    build_data_capability_matrix,
    build_dataset_capability,
    data_capability_matrix_as_dict,
)
from prism_data.manifest import DATASET_REGISTRY  # noqa: E402


_FORMAL_LANES = {"authoritative_daily", "execution"}


class CoverageTests(unittest.TestCase):
    def test_matrix_covers_all_registry_entries(self) -> None:
        entries = build_data_capability_matrix()
        self.assertEqual(len(entries), len(DATASET_REGISTRY))
        self.assertEqual(
            {entry.dataset for entry in entries},
            set(DATASET_REGISTRY.keys()),
        )

    def test_payload_dict_round_trip(self) -> None:
        payload = data_capability_matrix_as_dict()
        self.assertEqual(payload["entry_count"], len(DATASET_REGISTRY))
        self.assertEqual(len(payload["datasets"]), len(DATASET_REGISTRY))
        sample = payload["datasets"][0]
        for key in (
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
        ):
            self.assertIn(key, sample, f"missing {key} in matrix payload")

    def test_lookup_returns_none_for_unknown(self) -> None:
        self.assertIsNone(build_dataset_capability("does.not.exist"))


class DisplayOnlyTests(unittest.TestCase):
    def test_display_only_never_formal(self) -> None:
        entries = build_data_capability_matrix()
        display_only = [e for e in entries if e.decision_scope == "display_only"]
        self.assertGreater(len(display_only), 0, "registry must contain display_only datasets for this test to be meaningful")
        for entry in display_only:
            with self.subTest(dataset=entry.dataset):
                self.assertFalse(
                    entry.formal_decision_allowed,
                    f"{entry.dataset} is display_only but matrix marks it formal_decision_allowed",
                )
                self.assertIn("display_only", entry.risk_flags)


class TargetAuthorityTests(unittest.TestCase):
    def test_non_target_primary_flagged(self) -> None:
        # bars.daily has primary=sina but target=tushare
        entry = build_dataset_capability("bars.daily")
        assert entry is not None
        self.assertFalse(entry.source_authority_ready)
        self.assertFalse(entry.formal_decision_allowed)
        self.assertIn("target_authority_not_in_use:tushare", entry.risk_flags)

    def test_target_authority_matches_primary_then_ready(self) -> None:
        # trade_calendar has primary=tushare, target=tushare, lane=authoritative_daily
        entry = build_dataset_capability("trade_calendar")
        assert entry is not None
        self.assertTrue(entry.source_authority_ready)
        self.assertTrue(entry.formal_decision_allowed)
        self.assertNotIn(
            "target_authority_not_in_use:tushare",
            entry.risk_flags,
            "trade_calendar should not carry target_authority_not_in_use flag",
        )

    def test_every_target_mismatch_blocks_authority_ready(self) -> None:
        for entry in build_data_capability_matrix():
            if entry.source_lane == "pipeline":
                continue
            mismatch = entry.primary_provider != entry.target_authority_provider
            with self.subTest(dataset=entry.dataset):
                if mismatch:
                    self.assertFalse(
                        entry.source_authority_ready,
                        f"{entry.dataset}: primary != target but source_authority_ready=true",
                    )
                    self.assertIn(
                        f"target_authority_not_in_use:{entry.target_authority_provider}",
                        entry.risk_flags,
                    )


class FallbackTests(unittest.TestCase):
    def test_fallback_default_not_live_flag(self) -> None:
        # quotes.snapshot has fallback=[eastmoney]; runtime gateway treats any
        # fallback as display_only unless ProviderResult.extra opts in.
        entry = build_dataset_capability("quotes.snapshot")
        assert entry is not None
        self.assertEqual(entry.fallback_providers, ["eastmoney"])
        self.assertIn("fallback_default_not_live", entry.risk_flags)

    def test_no_fallback_flag(self) -> None:
        # quotes.pool has no fallback
        entry = build_dataset_capability("quotes.pool")
        assert entry is not None
        self.assertEqual(entry.fallback_providers, [])
        self.assertIn("no_fallback", entry.risk_flags)


class PipelineTests(unittest.TestCase):
    def test_pipeline_entry_is_conservative(self) -> None:
        # Pipeline datasets cannot be statically known authority-ready.
        entry = build_dataset_capability("screening.batch")
        assert entry is not None
        self.assertEqual(entry.source_lane, "pipeline")
        self.assertFalse(entry.source_authority_ready)
        self.assertFalse(entry.formal_decision_allowed)
        self.assertIn("pipeline_dataset", entry.risk_flags)


class LaneSemanticsTests(unittest.TestCase):
    def test_lane_not_in_formal_lanes_cannot_be_formal(self) -> None:
        for entry in build_data_capability_matrix():
            if entry.source_lane in _FORMAL_LANES:
                continue
            with self.subTest(dataset=entry.dataset):
                self.assertFalse(
                    entry.formal_decision_allowed,
                    f"{entry.dataset} lane={entry.source_lane} but formal_decision_allowed=true",
                )

    def test_semantics_strings_are_populated(self) -> None:
        for entry in build_data_capability_matrix():
            with self.subTest(dataset=entry.dataset):
                self.assertTrue(entry.source_authority_semantics.strip())
                self.assertTrue(entry.formal_decision_semantics.strip())


class BoundaryCaseTests(unittest.TestCase):
    def test_announcements_latest_official_exchange_target(self) -> None:
        entry = build_dataset_capability("announcements.latest")
        assert entry is not None
        self.assertEqual(entry.decision_scope, "display_only")
        self.assertEqual(entry.target_authority_provider, "official_exchange")
        self.assertFalse(entry.formal_decision_allowed)
        self.assertIn("target_authority_not_in_use:official_exchange", entry.risk_flags)
        self.assertIn("display_only", entry.risk_flags)

    def test_execution_flags_is_formal_candidate(self) -> None:
        entry = build_dataset_capability("execution.flags")
        assert entry is not None
        self.assertEqual(entry.source_lane, "execution")
        self.assertTrue(entry.source_authority_ready)
        self.assertTrue(entry.formal_decision_allowed)


class SummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = data_capability_matrix_as_dict()
        self.summary = self.payload["summary"]

    def test_summary_block_present(self) -> None:
        for key in (
            "total",
            "formal_ready",
            "display_only",
            "pending_target_authority",
            "pipeline_datasets",
            "required_for_live_small",
            "formal_lane_not_ready",
        ):
            self.assertIn(key, self.summary)

    def test_summary_total_matches_entry_count(self) -> None:
        self.assertEqual(self.summary["total"], self.payload["entry_count"])

    def test_summary_formal_ready_lists_known_formal_datasets(self) -> None:
        # trade_calendar and execution.flags are configured to be formal-ready
        for name in ("trade_calendar", "execution.flags", "benchmark.index_daily"):
            self.assertIn(name, self.summary["formal_ready"])

    def test_summary_display_only_lists_known_display_only(self) -> None:
        for name in ("quotes.pool", "news.latest", "announcements.latest"):
            self.assertIn(name, self.summary["display_only"])

    def test_summary_pending_target_authority_lists_bars_daily(self) -> None:
        self.assertIn("bars.daily", self.summary["pending_target_authority"])

    def test_summary_pipeline_datasets_lists_known_pipelines(self) -> None:
        for name in ("watchlist.snapshot", "screening.batch", "decision_brief.snapshot"):
            self.assertIn(name, self.summary["pipeline_datasets"])

    def test_summary_formal_lane_not_ready_lists_bars_daily(self) -> None:
        # bars.daily is lane=authoritative_daily but primary != target
        self.assertIn("bars.daily", self.summary["formal_lane_not_ready"])

    def test_summary_partitions_are_internally_consistent(self) -> None:
        # display_only entries must NEVER appear in formal_ready
        for name in self.summary["display_only"]:
            self.assertNotIn(name, self.summary["formal_ready"])
        # pipeline entries must NEVER appear in formal_ready (conservative)
        for name in self.summary["pipeline_datasets"]:
            self.assertNotIn(name, self.summary["formal_ready"])


if __name__ == "__main__":
    unittest.main()
