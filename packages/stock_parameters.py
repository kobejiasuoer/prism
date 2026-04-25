from __future__ import annotations

from stock_parameter_config import (
    PARAMETER_CONFIG_PATH,
    PARAMETER_SCHEMA_PATH,
    load_parameter_threshold_sets,
)

_REQUIRED_THRESHOLD_SETS = {"watchlist_rule_thresholds", "flow_confidence"}
_REQUIRED_NESTED_KEYS = {
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
THRESHOLD_SETS = load_parameter_threshold_sets(
    required_threshold_sets=_REQUIRED_THRESHOLD_SETS,
    required_nested_keys=_REQUIRED_NESTED_KEYS,
)
WATCHLIST_RULE_THRESHOLDS = THRESHOLD_SETS["watchlist_rule_thresholds"]
FLOW_CONFIDENCE_RULES = THRESHOLD_SETS["flow_confidence"]


def assess_flow_confidence(flow: dict | None) -> dict:
    flow = flow or {}
    if flow.get("intraday_unconfirmed"):
        return {
            "label": FLOW_CONFIDENCE_RULES["stale_label"],
            "penalty": FLOW_CONFIDENCE_RULES["stale_intraday_penalty"],
            "reference_only": True,
            "as_of_date": flow.get("as_of_date"),
        }
    if flow:
        return {
            "label": FLOW_CONFIDENCE_RULES["confirmed_label"],
            "penalty": 0,
            "reference_only": False,
            "as_of_date": flow.get("updated_at") or flow.get("as_of_date"),
        }
    return {
        "label": FLOW_CONFIDENCE_RULES["unknown_label"],
        "penalty": 0,
        "reference_only": False,
        "as_of_date": None,
    }
