from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_ROOT = REPO_ROOT / "packages"
if str(PACKAGES_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGES_ROOT))

from screener.stage_contract import (  # noqa: E402
    STAGE_LOAD_BEARING_FIELDS,
    SHORTLIST_ITEM_FIELDS,
    StageContractError,
    validate_stage_output,
)


def _scan_payload(**overrides):
    base = {
        "market_regime": "neutral",
        "market_themes": [],
        "pool": "hs300",
        "pool_label": "沪深300",
        "strategies": {},
        "timestamp": "2026-06-19 09:40:00",
        "trade_date": "2026-06-19",
    }
    base.update(overrides)
    return base


def _ai_payload(**overrides):
    base = {
        "shortlist": [
            {
                "code": "000032",
                "name": "深桑达A",
                "tier": "A",
                "best_score": 92.15,
                "suggested_action": "review",
            }
        ],
        "source_scan_timestamp": "2026-06-19 09:40:00",
        "timestamp": "2026-06-19 09:45:00",
        "trade_date": "2026-06-19",
    }
    base.update(overrides)
    return base


def _midday_payload(**overrides):
    base = {
        "confirmed": [],
        "downgraded": [],
        "tracking": [],
        "validation_status": "ok",
        "source_scan_timestamp": "2026-06-19 13:45:00",
        "verified_against_scan_timestamp": "2026-06-19 13:45:00",
        "timestamp": "2026-06-19 13:46:00",
        "trade_date": "2026-06-19",
    }
    base.update(overrides)
    return base


def _lifecycle_payload(**overrides):
    base = {
        "entered": [],
        "exited": [],
        "upgraded": [],
        "downgraded": [],
        "summary": {"total": 0},
        "metadata": {"generated_at": "2026-06-19T09:50:00"},
    }
    base.update(overrides)
    return base


def test_scan_complete_payload_passes():
    validate_stage_output(_scan_payload(), "scan")  # no raise


def test_scan_missing_field_raises_with_field_name():
    payload = _scan_payload()
    del payload["trade_date"]
    with pytest.raises(StageContractError) as exc_info:
        validate_stage_output(payload, "scan")
    assert "trade_date" in str(exc_info.value)
    assert "scan" in str(exc_info.value)


def test_ai_missing_top_level_field_raises():
    payload = _ai_payload()
    del payload["source_scan_timestamp"]
    with pytest.raises(StageContractError) as exc_info:
        validate_stage_output(payload, "ai_screening")
    assert "source_scan_timestamp" in str(exc_info.value)


def test_ai_shortlist_item_missing_field_raises():
    payload = _ai_payload()
    payload["shortlist"][0].pop("best_score")
    with pytest.raises(StageContractError) as exc_info:
        validate_stage_output(payload, "ai_screening")
    assert "best_score" in str(exc_info.value)


def test_ai_empty_shortlist_passes():
    """An empty shortlist (no candidates today) is legitimate, not a contract violation."""
    payload = _ai_payload(shortlist=[])
    validate_stage_output(payload, "ai_screening")  # no raise


def test_midday_complete_passes():
    validate_stage_output(_midday_payload(), "midday_verify")  # no raise


def test_midday_missing_field_raises():
    payload = _midday_payload()
    del payload["validation_status"]
    with pytest.raises(StageContractError) as exc_info:
        validate_stage_output(payload, "midday_verify")
    assert "validation_status" in str(exc_info.value)


def test_lifecycle_complete_passes():
    validate_stage_output(_lifecycle_payload(), "candidate_lifecycle")  # no raise


def test_lifecycle_missing_field_raises():
    payload = _lifecycle_payload()
    del payload["summary"]
    with pytest.raises(StageContractError) as exc_info:
        validate_stage_output(payload, "candidate_lifecycle")
    assert "summary" in str(exc_info.value)


def test_unknown_stage_raises():
    with pytest.raises(ValueError) as exc_info:
        validate_stage_output({}, "nonexistent_stage")
    assert "nonexistent_stage" in str(exc_info.value)


def test_all_stages_have_load_bearing_fields_defined():
    """Every known stage must have a non-empty field list — a typo'd stage name
    that silently validates nothing is the worst failure mode."""
    assert set(STAGE_LOAD_BEARING_FIELDS.keys()) == {
        "scan",
        "ai_screening",
        "midday_verify",
        "candidate_lifecycle",
    }
    for stage, fields in STAGE_LOAD_BEARING_FIELDS.items():
        assert fields, f"stage {stage} has empty load-bearing field list"
