"""Inter-stage JSON contract guards for the screener pipeline.

Each pipeline stage (scan → ai_screening → midday_verify →
candidate_lifecycle) writes a JSON artifact that the next stage reads via
``.get()``. Without a guard, a renamed or dropped field silently degrades to
``None`` / empty-list downstream, producing wrong results with no error.

``validate_stage_output`` is called at each stage's output, *before* the file
is written. It checks only **load-bearing** fields — the small set the next
stage actually depends on — not the full payload shape, so adding new fields
does not require updating this module unless they become load-bearing.

Field lists are derived from the actual ``.get()`` call sites in the
consuming stages (see the appendix in the design spec). Intentionally narrow:
presence + non-emptiness only, no type checks.
"""

from __future__ import annotations

from typing import Any


class StageContractError(Exception):
    """Raised when a stage output is missing load-bearing fields."""


# Top-level load-bearing fields per stage. Derived from the downstream
# consumers' actual .get() call sites (see spec appendix for code refs).
STAGE_LOAD_BEARING_FIELDS: dict[str, list[str]] = {
    # ai_screening.py reads these from scan_result via scan_data.get(...).
    # NOTE: "candidates" is intentionally absent — scan_result stores stocks
    # under "strategies"/"verification_universe"; ai_screening falls back to
    # [] for candidates and reads strategies separately.
    "scan": [
        "market_regime",
        "market_themes",
        "pool",
        "pool_label",
        "strategies",
        "timestamp",
        "trade_date",
    ],
    # midday_verify + candidate_lifecycle + dashboard_data read these
    "ai_screening": [
        "shortlist",
        "source_scan_timestamp",
        "timestamp",
        "trade_date",
    ],
    # candidate_lifecycle + dashboard_data read these
    "midday_verify": [
        "confirmed",
        "downgraded",
        "tracking",
        "validation_status",
        "source_scan_timestamp",
        "verified_against_scan_timestamp",
        "timestamp",
        "trade_date",
    ],
    # dashboard_data reads these
    "candidate_lifecycle": [
        "entered",
        "exited",
        "upgraded",
        "downgraded",
        "summary",
        "metadata",
    ],
}

# Load-bearing fields inside each ai_screening shortlist item. midday_verify
# and candidate_lifecycle .get() these; missing ones degrade classification.
# NOTE: no per-item "timestamp" — the timestamp is top-level on the payload,
# not on each shortlist item.
SHORTLIST_ITEM_FIELDS: list[str] = [
    "code",
    "name",
    "tier",
    "best_score",
    "suggested_action",
]


def _missing(payload: dict[str, Any], fields: list[str]) -> list[str]:
    """Return fields that are absent or None."""
    missing: list[str] = []
    for field in fields:
        value = payload.get(field)
        if value is None:
            missing.append(field)
    return missing


def validate_stage_output(payload: dict[str, Any], stage: str) -> None:
    """Verify ``payload`` has the load-bearing fields for ``stage``.

    Raises :class:`StageContractError` listing every missing field if any are
    absent/None. For ``ai_screening`` also validates the first shortlist item's
    load-bearing fields (an empty shortlist is legitimate and skips this).
    Raises ``ValueError`` if ``stage`` is unknown — a silent no-op guard is
    worse than no guard.
    """

    if stage not in STAGE_LOAD_BEARING_FIELDS:
        raise ValueError(
            f"unknown stage {stage!r}; expected one of "
            f"{sorted(STAGE_LOAD_BEARING_FIELDS)}"
        )

    missing = _missing(payload, STAGE_LOAD_BEARING_FIELDS[stage])
    if missing:
        raise StageContractError(
            f"stage {stage!r} output missing load-bearing fields: {missing}"
        )

    if stage == "ai_screening":
        shortlist = payload.get("shortlist") or []
        # An empty shortlist (no candidates today) is legitimate — skip the
        # per-item check so we don't false-positive on a quiet trading day.
        if shortlist:
            first = shortlist[0]
            if isinstance(first, dict):
                item_missing = _missing(first, SHORTLIST_ITEM_FIELDS)
                if item_missing:
                    raise StageContractError(
                        f"stage {stage!r} shortlist item missing load-bearing "
                        f"fields: {item_missing}"
                    )
