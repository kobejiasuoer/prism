from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_ROOT = REPO_ROOT / "packages"
if str(PACKAGES_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGES_ROOT))

from screener.parameters import build_execution_gate  # noqa: E402


def _broad(score=3, positive_ratio=0.386, avg_change=-0.43, strong_ratio=0.166, turnover=3.02):
    """6-18 real broad market: weak."""
    return {
        "score": score,
        "metrics": {
            "positive_ratio": positive_ratio,
            "avg_change_pct": avg_change,
            "strong_ratio": strong_ratio,
            "avg_turnover": turnover,
        },
    }


def _candidate(score=8, positive_ratio=0.833, avg_change=3.96, strong_ratio=0.3, turnover=6.0):
    """6-18 real candidate pool: strong."""
    return {
        "score": score,
        "metrics": {
            "positive_ratio": positive_ratio,
            "avg_change_pct": avg_change,
            "strong_ratio": strong_ratio,
            "avg_turnover": turnover,
        },
    }


def test_candidate_strong_broad_weak_yields_limited_not_off():
    """Candidate pool strong but broad market clearly weak → limited (not off).

    This is the structural-rally scenario the old OR logic killed. Broad has
    low positive_ratio + negative avg_change + low strong_ratio (env 0-1),
    while candidate is strong (env 2-3). Old logic: off. New: limited or on.
    The key assertion is NOT off — the gate must let the user act."""
    gate = build_execution_gate(
        _broad(score=2, positive_ratio=0.3, avg_change=-1.0, strong_ratio=0.04),
        _candidate(score=8, positive_ratio=0.8, avg_change=3.0, strong_ratio=0.3),
    )
    assert gate["status"] != "off", f"should not be off for candidate-strong, got {gate['status']}"
    assert gate["allow_new_positions"] is True


def test_june18_real_data_not_off():
    """The actual 6-18 scenario (broad mediocre, candidate very strong) must not
    be off. Whether it's limited or on depends on the exact env scores, but it
    must allow new positions."""
    gate = build_execution_gate(_broad(), _candidate())
    assert gate["status"] != "off", f"6-18 must not be off, got {gate['status']}"
    assert gate["allow_new_positions"] is True


def test_both_weak_yields_off():
    """Both broad and candidate weak → off (preserve the safety floor)."""
    gate = build_execution_gate(_broad(score=1, positive_ratio=0.2, avg_change=-2.0, strong_ratio=0.02),
                                _candidate(score=1, positive_ratio=0.2, avg_change=-1.0, strong_ratio=0.05))
    assert gate["status"] == "off"
    assert gate["allow_new_positions"] is False


def test_both_strong_yields_on():
    """Both broad and candidate strong → on."""
    gate = build_execution_gate(_broad(score=8, positive_ratio=0.7, avg_change=1.5, strong_ratio=0.25),
                                _candidate(score=9, positive_ratio=0.9, avg_change=4.0, strong_ratio=0.4))
    assert gate["status"] == "on"
    assert gate["allow_new_positions"] is True


def test_off_position_cap_is_zero():
    """off regime must have zero position cap."""
    gate = build_execution_gate(_broad(score=1, positive_ratio=0.1), _candidate(score=1))
    assert "0" in gate["position_cap"]


def test_limited_allows_restricted_setups():
    """limited should allow some setups (pullback/reversal) but not all."""
    gate = build_execution_gate(_broad(), _candidate())
    assert len(gate["allowed_setups"]) > 0


def test_return_structure_unchanged():
    """The gate dict must still carry all keys the frontend/backend expect."""
    gate = build_execution_gate(_broad(), _candidate())
    for key in ("status", "label", "summary", "position_cap",
                "allow_new_positions", "allow_handoff", "allowed_setups", "risk_flags"):
        assert key in gate, f"missing key {key}"


def test_missing_regimes_does_not_crash():
    """None regimes should not raise."""
    gate = build_execution_gate(None, None)
    assert gate["status"] in ("off", "limited", "on", "unknown")
