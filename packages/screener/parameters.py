from __future__ import annotations

from stock_parameter_config import (
    PARAMETER_CONFIG_PATH,
    PARAMETER_SCHEMA_PATH,
    load_parameter_threshold_sets,
)


THRESHOLD_SETS = load_parameter_threshold_sets()

FINAL_SCORE_WEIGHTS = THRESHOLD_SETS["final_score_weights"]
CAPITAL_SCORE_THRESHOLDS = THRESHOLD_SETS["capital_score"]
SETUP_THRESHOLDS = THRESHOLD_SETS["setup_thresholds"]
EXECUTION_QUALITY_RULES = THRESHOLD_SETS["execution_quality"]
EXECUTION_GATE_THRESHOLDS = THRESHOLD_SETS["execution_gate"]
AI_SCREENING_EVALUATION_RULES = THRESHOLD_SETS["ai_screening_evaluation"]
ATTACK_PROFILE_RULES = THRESHOLD_SETS["attack_profile"]
TRADE_NOTE_RULES = THRESHOLD_SETS["trade_note"]
SETUP_PLAN_RULES = THRESHOLD_SETS["setup_plan"]
ENTRY_OUTPUT_DEFAULTS = THRESHOLD_SETS["entry_output_defaults"]
EMOTION_SCORE_RULES = THRESHOLD_SETS["emotion_score"]
FUNDAMENTAL_SCORE_RULES = THRESHOLD_SETS["fundamental_score"]
MISSING_DATA_PENALTIES = THRESHOLD_SETS["missing_data_penalties"]
OVERHEAT_PENALTY_RULES = THRESHOLD_SETS["overheat_penalty"]


def _apply_tiered_score(value: float, rules: list[dict]) -> int:
    for rule in rules:
        if value > rule["above"]:
            return int(rule["score"])
    return 0


def compute_emotion_score(change_pct: float, amount: float, turnover: float) -> int:
    score = 0
    score += _apply_tiered_score(change_pct, EMOTION_SCORE_RULES["change_pct"])
    score += _apply_tiered_score(amount, EMOTION_SCORE_RULES["amount_yuan"])
    score += _apply_tiered_score(turnover, EMOTION_SCORE_RULES["turnover"])
    return min(score, int(EMOTION_SCORE_RULES["cap"]))


def compute_missing_cap_penalty(has_capital_flow: bool) -> int:
    return 0 if has_capital_flow else int(MISSING_DATA_PENALTIES["capital_flow_missing"])


def _match_overheat_rule(rule: dict, position_20d: float, change_pct: float, turnover: float) -> bool:
    if position_20d < float(rule.get("position_20d_at_least", float("-inf"))):
        return False
    if change_pct < float(rule.get("change_pct_at_least", float("-inf"))):
        return False
    if turnover < float(rule.get("turnover_at_least", float("-inf"))):
        return False
    return True


def compute_overheat_penalty(position_20d: float, change_pct: float, turnover: float) -> tuple[int, list[str]]:
    penalty = 0
    tags: list[str] = []
    for key in ["position_hot", "turnover_hot", "extension_risk"]:
        for rule in OVERHEAT_PENALTY_RULES[key]:
            if _match_overheat_rule(rule, position_20d=position_20d, change_pct=change_pct, turnover=turnover):
                penalty += int(rule["score"])
                tags.append(rule["tag"])
                break
    return penalty, tags


def clamp_fundamental_score(score: float) -> float:
    return max(
        min(score, float(FUNDAMENTAL_SCORE_RULES["max"])),
        float(FUNDAMENTAL_SCORE_RULES["min"]),
    )


def compute_final_score(
    tech_score: float,
    capital_score: float,
    emotion_score: float,
    fundamental_score: float,
    missing_cap_penalty: float,
    overheat_penalty: float,
) -> float:
    return round(
        tech_score * FINAL_SCORE_WEIGHTS["tech_score"]
        + capital_score * FINAL_SCORE_WEIGHTS["capital_score"]
        + emotion_score * FINAL_SCORE_WEIGHTS["emotion_score"]
        + fundamental_score * FINAL_SCORE_WEIGHTS["fundamental_score"]
        - missing_cap_penalty
        - overheat_penalty,
        2,
    )


def build_execution_gate(broad_regime, candidate_regime):
    broad_metrics = (broad_regime or {}).get("metrics") or {}
    candidate_metrics = (candidate_regime or {}).get("metrics") or {}

    broad_score = float((broad_regime or {}).get("score") or 0)
    candidate_score = float((candidate_regime or {}).get("score") or 0)
    positive_ratio = float(broad_metrics.get("positive_ratio") or 0)
    avg_change = float(broad_metrics.get("avg_change_pct") or 0)
    strong_ratio = float(broad_metrics.get("strong_ratio") or 0)
    avg_turnover = float(broad_metrics.get("avg_turnover") or 0)
    candidate_strong_ratio = float(candidate_metrics.get("strong_ratio") or 0)

    risk_rules = EXECUTION_GATE_THRESHOLDS["risk_flags"]
    risk_flags = []
    if positive_ratio < risk_rules["positive_ratio"]:
        risk_flags.append("赚钱效应不足")
    if avg_change < risk_rules["avg_change_pct"]:
        risk_flags.append("平均涨幅偏弱")
    if strong_ratio < risk_rules["strong_ratio"]:
        risk_flags.append("强势股占比过低")
    if avg_turnover < risk_rules["avg_turnover"]:
        risk_flags.append("流动性一般")
    if candidate_score <= risk_rules["candidate_score"]:
        risk_flags.append("候选强度不足")
    if candidate_strong_ratio < risk_rules["candidate_strong_ratio"]:
        risk_flags.append("候选强势扩散不足")

    off_rules = EXECUTION_GATE_THRESHOLDS["off"]
    limited_rules = EXECUTION_GATE_THRESHOLDS["limited"]
    on_rules = EXECUTION_GATE_THRESHOLDS["on"]

    if (
        broad_score <= off_rules["broad_score_max"]
        or positive_ratio < off_rules["positive_ratio_max"]
        or avg_change < off_rules["avg_change_pct_max"]
        or strong_ratio < off_rules["strong_ratio_max"]
        or candidate_score <= off_rules["candidate_score_max"]
        or candidate_strong_ratio < off_rules["candidate_strong_ratio_max"]
    ):
        selected = off_rules
        status = "off"
    elif (
        broad_score <= limited_rules["broad_score_max"]
        or positive_ratio < limited_rules["positive_ratio_max"]
        or avg_change < limited_rules["avg_change_pct_max"]
        or strong_ratio < limited_rules["strong_ratio_max"]
        or candidate_score <= limited_rules["candidate_score_max"]
        or candidate_strong_ratio < limited_rules["candidate_strong_ratio_max"]
    ):
        selected = limited_rules
        status = "limited"
    else:
        selected = on_rules
        status = "on"

    return {
        "status": status,
        "label": selected["label"],
        "summary": selected["summary"],
        "position_cap": selected["position_cap"],
        "allow_new_positions": selected["allow_new_positions"],
        "allow_handoff": selected["allow_handoff"],
        "allowed_setups": list(selected["allowed_setups"]),
        "risk_flags": risk_flags[:4],
    }
