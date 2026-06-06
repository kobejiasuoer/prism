"""Tests for freshness_state — six-state classifier for readiness source rows.

Maps the readiness module's scattered ``stale`` / ``degraded`` / ``available``
/ ``stale_reasons`` flags into one explicit enum and a capability allow
matrix.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


CONTROL_PANEL_ROOT = Path(__file__).resolve().parents[1]
if str(CONTROL_PANEL_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROL_PANEL_ROOT))

from freshness_state import (  # noqa: E402
    FreshnessState,
    classify_source_row,
    state_allows,
)


class ClassifySourceRowTests(unittest.TestCase):
    @staticmethod
    def _row(
        *,
        available: bool = True,
        stale: bool = False,
        degraded: bool = False,
        deferred: bool = False,
        stale_reasons: list[str] | None = None,
        degradation_reasons: list[str] | None = None,
    ) -> dict[str, object]:
        return {
            "available": available,
            "stale": stale,
            "degraded": degraded,
            "deferred": deferred,
            "stale_reasons": stale_reasons or [],
            "degradation_reasons": degradation_reasons or [],
        }

    def test_fresh(self) -> None:
        self.assertEqual(classify_source_row(self._row()), FreshnessState.FRESH)

    def test_missing_is_invalid(self) -> None:
        self.assertEqual(
            classify_source_row(self._row(available=False, stale=True, stale_reasons=["manifest_missing"])),
            FreshnessState.INVALID,
        )

    def test_trade_date_mismatch_is_invalid(self) -> None:
        row = self._row(stale=True, stale_reasons=["trade_date_mismatch"])
        self.assertEqual(classify_source_row(row), FreshnessState.INVALID)

    def test_trade_date_unknown_is_invalid(self) -> None:
        row = self._row(stale=True, stale_reasons=["trade_date_unknown"])
        self.assertEqual(classify_source_row(row), FreshnessState.INVALID)

    def test_live_small_not_allowed_is_degraded(self) -> None:
        row = self._row(stale=True, stale_reasons=["live_small_not_allowed"])
        self.assertEqual(classify_source_row(row), FreshnessState.DEGRADED)

    def test_fallback_not_allowed_is_degraded(self) -> None:
        row = self._row(stale=True, stale_reasons=["fallback_not_allowed"])
        self.assertEqual(classify_source_row(row), FreshnessState.DEGRADED)

    def test_degraded_only_is_degraded(self) -> None:
        row = self._row(degraded=True, degradation_reasons=["upstream_freshness_stale"])
        self.assertEqual(classify_source_row(row), FreshnessState.DEGRADED)

    def test_stale_only_is_stale(self) -> None:
        row = self._row(stale=True, stale_reasons=["freshness_stale"])
        self.assertEqual(classify_source_row(row), FreshnessState.STALE)

    def test_freshness_expired_is_stale(self) -> None:
        row = self._row(stale=True, stale_reasons=["freshness_expired"])
        self.assertEqual(classify_source_row(row), FreshnessState.STALE)

    def test_invalid_dominates_policy_degraded(self) -> None:
        # If both INVALID (trade_date_mismatch) and policy DEGRADED
        # (live_small_not_allowed) apply, INVALID wins because the data is
        # structurally unusable.
        row = self._row(stale=True, stale_reasons=["trade_date_mismatch", "live_small_not_allowed"])
        self.assertEqual(classify_source_row(row), FreshnessState.INVALID)

    def test_stale_dominates_policy_degraded(self) -> None:
        row = self._row(stale=True, stale_reasons=["freshness_stale", "live_small_not_allowed"])
        self.assertEqual(classify_source_row(row), FreshnessState.STALE)

    def test_provider_failure_is_invalid(self) -> None:
        row = self._row(available=False, stale=True, stale_reasons=["manifest_status_failed", "provider_failure"])
        self.assertEqual(classify_source_row(row), FreshnessState.INVALID)

    def test_deferred_missing_source_is_usable_until_due(self) -> None:
        row = self._row(
            available=False,
            stale=False,
            deferred=True,
            stale_reasons=["manifest_missing", "missing"],
        )
        self.assertEqual(classify_source_row(row), FreshnessState.USABLE)


class StateAllowsMatrixTests(unittest.TestCase):
    # Authoritative matrix: state x capability -> allowed?
    EXPECTED = {
        FreshnessState.FRESH: {
            "observe": True, "review": True, "approve": True,
            "trade": True, "notify": True, "ledger_capture": True,
        },
        FreshnessState.DEGRADED: {
            "observe": True, "review": True, "approve": False,
            "trade": False, "notify": True, "ledger_capture": True,
        },
        FreshnessState.STALE: {
            "observe": True, "review": True, "approve": False,
            "trade": False, "notify": True, "ledger_capture": False,
        },
        FreshnessState.INVALID: {
            "observe": False, "review": False, "approve": False,
            "trade": False, "notify": True, "ledger_capture": False,
        },
        FreshnessState.BLOCKED: {
            "observe": True, "review": False, "approve": False,
            "trade": False, "notify": True, "ledger_capture": False,
        },
        FreshnessState.USABLE: {
            "observe": True, "review": True, "approve": False,
            "trade": False, "notify": True, "ledger_capture": False,
        },
    }

    def test_matrix_complete(self) -> None:
        for state, by_cap in self.EXPECTED.items():
            for cap, expected in by_cap.items():
                with self.subTest(state=state, capability=cap):
                    self.assertEqual(state_allows(state, cap), expected)

    def test_unknown_capability_defaults_false(self) -> None:
        self.assertFalse(state_allows(FreshnessState.FRESH, "totally_made_up_cap"))


if __name__ == "__main__":
    unittest.main()
