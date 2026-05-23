"""Tests for freshness_state — six-state classifier for readiness source rows.

Maps the readiness module's scattered ``stale`` / ``degraded`` / ``available``
/ ``stale_reasons`` flags into one explicit enum and a capability allow
matrix.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


INVEST_FLOW_ROOT = Path(__file__).resolve().parents[2]
if str(INVEST_FLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(INVEST_FLOW_ROOT))

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
        stale_reasons: list[str] | None = None,
        degradation_reasons: list[str] | None = None,
    ) -> dict[str, object]:
        return {
            "available": available,
            "stale": stale,
            "degraded": degraded,
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

    def test_live_small_not_allowed_is_blocked(self) -> None:
        row = self._row(stale=True, stale_reasons=["live_small_not_allowed"])
        self.assertEqual(classify_source_row(row), FreshnessState.BLOCKED)

    def test_fallback_not_allowed_is_blocked(self) -> None:
        row = self._row(stale=True, stale_reasons=["fallback_not_allowed"])
        self.assertEqual(classify_source_row(row), FreshnessState.BLOCKED)

    def test_degraded_only_is_degraded(self) -> None:
        row = self._row(degraded=True, degradation_reasons=["upstream_freshness_stale"])
        self.assertEqual(classify_source_row(row), FreshnessState.DEGRADED)

    def test_stale_only_is_stale(self) -> None:
        row = self._row(stale=True, stale_reasons=["freshness_stale"])
        self.assertEqual(classify_source_row(row), FreshnessState.STALE)

    def test_freshness_expired_is_stale(self) -> None:
        row = self._row(stale=True, stale_reasons=["freshness_expired"])
        self.assertEqual(classify_source_row(row), FreshnessState.STALE)

    def test_invalid_dominates_blocked(self) -> None:
        # If both INVALID (trade_date_mismatch) and BLOCKED (live_small_not_allowed)
        # apply, INVALID wins because the data is structurally unusable.
        row = self._row(stale=True, stale_reasons=["trade_date_mismatch", "live_small_not_allowed"])
        self.assertEqual(classify_source_row(row), FreshnessState.INVALID)

    def test_blocked_dominates_stale(self) -> None:
        row = self._row(stale=True, stale_reasons=["freshness_stale", "live_small_not_allowed"])
        self.assertEqual(classify_source_row(row), FreshnessState.BLOCKED)


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
