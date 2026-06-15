"""Safety regression: factor data must not influence the readiness mode.

The Tushare factor layer is a research/explanation enrichment — it does NOT
feed into the readiness gate.  This test pins that invariant by
(a) checking compute_readiness ignores any factor blob in inputs, and
(b) checking that a weekend (non-trading) timestamp keeps the mode in the
    shadow_only / blocked / live_ready set (never an unexpected value).
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import readiness  # noqa: E402


# A Saturday — non-trading day; readiness must downgrade to shadow_only.
_SATURDAY = datetime(2026, 5, 30, 14, 0, 0)


def _empty_readiness(**overrides):
    kwargs = dict(
        watchlist=None,
        screening_batch=None,
        confirmation=None,
        decision_brief=None,
        quality_status=None,
        account_book=None,
        today_action_decisions=None,
        dataset_freshness=None,
        formal_freshness=None,
        now=_SATURDAY,
        expected_date="2026-05-29",
    )
    kwargs.update(overrides)
    return readiness.compute_readiness(**kwargs)


def test_factor_blob_in_inputs_does_not_change_readiness_mode():
    """compute_readiness has no factor input — confirm by passing a junk blob
    on a payload it DOES accept and seeing the result is identical to the
    baseline."""

    base = _empty_readiness()
    assert "readiness_mode" in base
    assert base["readiness_mode"] in {"shadow_only", "blocked", "live_ready"}

    # Bogus factor data smuggled into a watchlist payload must be ignored
    # because the function only consumes structural readiness fields.
    polluted_watchlist = {
        "tushare_factors": {"score": 999.0, "tags": ["pretend-bullish"]},
        "factor_explanation": {"entry_reason": "should be ignored"},
    }
    polluted = _empty_readiness(watchlist=polluted_watchlist)
    assert polluted["readiness_mode"] == base["readiness_mode"]


def test_weekend_mode_is_not_live_ready():
    """A Saturday at 14:00 must keep us out of live trading regardless of
    any factor work — this guards the real-money safety invariant."""

    result = _empty_readiness()
    assert result["readiness_mode"] != "live_ready"
    assert result["readiness_mode"] in {"shadow_only", "blocked"}
