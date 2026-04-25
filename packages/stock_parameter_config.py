from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PARAMETER_CONFIG_PATH = REPO_ROOT / "data" / "config" / "stock-parameters.json"
PARAMETER_SCHEMA_PATH = REPO_ROOT / "data" / "schemas" / "stock-parameters.json"

REQUIRED_THRESHOLD_SETS = {
    "ai_screening_evaluation",
    "attack_profile",
    "capital_score",
    "emotion_score",
    "entry_output_defaults",
    "execution_gate",
    "execution_quality",
    "final_score_weights",
    "flow_confidence",
    "fundamental_score",
    "missing_data_penalties",
    "overheat_penalty",
    "setup_plan",
    "setup_thresholds",
    "trade_note",
    "watchlist_rule_thresholds",
}

REQUIRED_NESTED_KEYS = {
    "final_score_weights": {"tech_score", "capital_score", "emotion_score", "fundamental_score"},
    "capital_score": {"today_flow_wan", "consecutive_inflow_days", "reversal"},
    "setup_thresholds": {
        "leader_continuation",
        "low_reversal",
        "breakout_follow",
        "pullback_continuation",
    },
    "execution_quality": {
        "amount_yi",
        "capital_flow",
        "consistency",
        "setup_type",
        "top_theme",
        "theme_persistence",
        "overheat_penalty",
        "trend_setup_change_pct",
        "divergence",
        "notice_risk",
        "execution_gate",
        "labels",
    },
    "execution_gate": {"risk_flags", "off", "limited", "on"},
    "ai_screening_evaluation": {
        "amount_yi",
        "valuation",
        "capital_flow",
        "overheat_penalty",
        "divergence",
        "notice_risk",
        "price_action",
        "theme",
        "regime",
        "consistency_labels",
        "approved_downgrade",
    },
    "attack_profile": {
        "style_keywords",
        "style",
        "turnover",
        "divergence",
        "flow_transition",
        "change_pct",
        "flow_today",
        "consecutive_inflows",
        "position_20d",
        "valuation",
        "hard_rules",
        "status",
    },
    "trade_note": {"reasons", "risks", "watch"},
    "setup_plan": {
        "default",
        "leader_continuation",
        "low_reversal",
        "breakout_follow",
        "pullback_continuation",
        "modifiers",
    },
    "entry_output_defaults": {"entry_reason", "watch_condition"},
    "emotion_score": {"change_pct", "amount_yuan", "turnover", "cap"},
    "fundamental_score": {"max", "min"},
    "missing_data_penalties": {"capital_flow_missing"},
    "overheat_penalty": {"position_hot", "turnover_hot", "extension_risk"},
    "watchlist_rule_thresholds": {
        "roe",
        "pe",
        "pb",
        "relative_strength",
        "price_position",
        "action",
    },
    "flow_confidence": {
        "confirmed_label",
        "stale_label",
        "unknown_label",
        "stale_intraday_penalty",
    },
}


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"Parameter config file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Parameter config payload must be a JSON object: {path}")
    return payload


def validate_threshold_sets(
    threshold_sets: dict[str, Any],
    *,
    required_threshold_sets: set[str] | None = None,
    required_nested_keys: dict[str, set[str]] | None = None,
) -> dict[str, Any]:
    if not isinstance(threshold_sets, dict):
        raise RuntimeError("Parameter config missing threshold_sets object")

    expected_sets = required_threshold_sets or REQUIRED_THRESHOLD_SETS
    expected_nested = required_nested_keys or REQUIRED_NESTED_KEYS

    missing_sets = sorted(expected_sets - set(threshold_sets))
    if missing_sets:
        missing_text = ", ".join(missing_sets)
        raise RuntimeError(f"Parameter config missing threshold sets: {missing_text}")

    for name, required_keys in expected_nested.items():
        section = threshold_sets.get(name)
        if not isinstance(section, dict):
            raise RuntimeError(f"Threshold set '{name}' must be a JSON object")
        missing_keys = sorted(required_keys - set(section))
        if missing_keys:
            missing_text = ", ".join(missing_keys)
            raise RuntimeError(f"Threshold set '{name}' missing keys: {missing_text}")

    return threshold_sets


def validate_parameter_payload(
    payload: dict[str, Any],
    *,
    required_threshold_sets: set[str] | None = None,
    required_nested_keys: dict[str, set[str]] | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RuntimeError("Parameter config payload must be a JSON object")

    if "version" not in payload:
        raise RuntimeError("Parameter config missing version")

    validate_threshold_sets(
        payload.get("threshold_sets"),
        required_threshold_sets=required_threshold_sets,
        required_nested_keys=required_nested_keys,
    )
    return payload


def load_parameter_config(
    *,
    required_threshold_sets: set[str] | None = None,
    required_nested_keys: dict[str, set[str]] | None = None,
) -> dict[str, Any]:
    payload = load_json(PARAMETER_CONFIG_PATH)
    return validate_parameter_payload(
        payload,
        required_threshold_sets=required_threshold_sets,
        required_nested_keys=required_nested_keys,
    )


def load_parameter_threshold_sets(
    *,
    required_threshold_sets: set[str] | None = None,
    required_nested_keys: dict[str, set[str]] | None = None,
) -> dict[str, Any]:
    return load_parameter_config(
        required_threshold_sets=required_threshold_sets,
        required_nested_keys=required_nested_keys,
    )["threshold_sets"]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def save_parameter_config(payload: dict[str, Any], *, sync_schema: bool = True) -> dict[str, Any]:
    validated = validate_parameter_payload(payload)
    _write_json(PARAMETER_CONFIG_PATH, validated)

    if sync_schema:
        schema_payload = load_json(PARAMETER_SCHEMA_PATH)
        schema_payload["version"] = validated["version"]
        schema_payload["threshold_sets"] = deepcopy(validated["threshold_sets"])
        _write_json(PARAMETER_SCHEMA_PATH, schema_payload)

    return validated
