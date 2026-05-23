"""Six-state freshness classifier for Prism readiness source rows.

The readiness module exposes per-source ``stale`` / ``degraded`` / ``available``
booleans and a free-form ``stale_reasons`` list.  Downstream consumers (the
capability matrix, the future UI) need a small, explicit enum to reason
about: *what kind of "not fresh" is this row?*  Six states cover the
spectrum:

* FRESH    — aligned trade date, on-time, scope ok
* USABLE   — reserved for Phase 2 ("near threshold" early warning)
* STALE    — past TTL but still readable (degrade to observe/review)
* DEGRADED — fallback provider in use or authority not in target lane
* INVALID  — structurally unusable (missing manifest, trade-date mismatch)
* BLOCKED  — explicit policy bar (live_small_not_allowed, fallback_not_allowed)

``state_allows`` encodes which investment capabilities each state permits.
This is the authoritative matrix; capability_matrix consumes it directly.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping


__all__ = [
    "FreshnessState",
    "classify_source_row",
    "state_allows",
]


class FreshnessState(str, Enum):
    FRESH = "fresh"
    USABLE = "usable"
    STALE = "stale"
    DEGRADED = "degraded"
    INVALID = "invalid"
    BLOCKED = "blocked"


# Precedence: INVALID > BLOCKED > STALE > DEGRADED > USABLE > FRESH.
# Higher precedence means the data is more unusable; the classifier returns
# the worst applicable state.

_INVALID_REASONS = frozenset({
    "manifest_missing",
    "missing",
    "trade_date_mismatch",
    "trade_date_unknown",
    "freshness_unknown",
})

_BLOCKED_REASONS = frozenset({
    "live_small_not_allowed",
    "fallback_not_allowed",
})

_STALE_REASONS = frozenset({
    "freshness_stale",
    "freshness_expired",
})


def classify_source_row(row: Mapping[str, Any]) -> FreshnessState:
    """Classify one readiness source row into a single FreshnessState.

    The row shape comes from ``readiness.compute_readiness`` ``source_freshness``
    items: ``available``, ``stale``, ``degraded``, ``stale_reasons``,
    ``degradation_reasons`` (any of which may be missing).
    """
    available = bool(row.get("available"))
    stale = bool(row.get("stale"))
    degraded = bool(row.get("degraded"))
    reasons = {str(reason).strip() for reason in (row.get("stale_reasons") or [])}

    if not available or reasons & _INVALID_REASONS:
        return FreshnessState.INVALID
    if reasons & _BLOCKED_REASONS:
        return FreshnessState.BLOCKED
    if stale and reasons & _STALE_REASONS:
        return FreshnessState.STALE
    if stale:
        return FreshnessState.STALE
    if degraded:
        return FreshnessState.DEGRADED
    return FreshnessState.FRESH


_ALLOW_MATRIX: dict[FreshnessState, frozenset[str]] = {
    FreshnessState.FRESH: frozenset({"observe", "review", "approve", "trade", "notify", "ledger_capture"}),
    FreshnessState.DEGRADED: frozenset({"observe", "review", "notify", "ledger_capture"}),
    FreshnessState.STALE: frozenset({"observe", "review", "notify"}),
    FreshnessState.USABLE: frozenset({"observe", "review", "notify"}),
    FreshnessState.BLOCKED: frozenset({"observe", "notify"}),
    FreshnessState.INVALID: frozenset({"notify"}),
}


def state_allows(state: FreshnessState, capability: str) -> bool:
    return str(capability or "").strip() in _ALLOW_MATRIX.get(state, frozenset())
