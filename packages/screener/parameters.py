from __future__ import annotations

from typing import Any

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


def safe_float(value: Any, default: float | None = 0.0) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def unique_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def price_level(value: Any) -> float | None:
    level = safe_float(value, default=None)
    return round(level, 2) if level is not None and level > 0 else None


def price_text(value: Any) -> str:
    level = price_level(value)
    return f"{level:.2f}" if level is not None else ""


def nested_or_flat(raw: dict[str, Any], nested_key: str, flat_key: str) -> Any:
    nested = raw.get(nested_key) or {}
    if isinstance(nested, dict) and nested.get(flat_key) is not None:
        return nested.get(flat_key)
    return raw.get(flat_key)


def infer_intraday_setup_label(raw: dict[str, Any]) -> str:
    if raw.get("setup_label"):
        return raw.get("setup_label")
    trade_note = raw.get("trade_note") or {}
    text = " ".join(
        str(value or "")
        for value in (
            trade_note.get("entry_reason"),
            raw.get("entry_reason"),
            raw.get("watch_condition"),
        )
    ).strip()
    if "低位" in text and "反" in text:
        return "低位反转"
    if "回踩" in text:
        return "回踩接力"
    if "突破" in text:
        return "突破跟随"
    if "龙头" in text:
        return "热点龙头"
    return "盘中新机会"


def infer_intraday_setup_type(raw: dict[str, Any]) -> str:
    if raw.get("setup_type"):
        return raw.get("setup_type")
    label = infer_intraday_setup_label(raw)
    if label == "低位反转":
        return "low_reversal"
    if label == "回踩接力":
        return "pullback_continuation"
    if label == "突破跟随":
        return "breakout_follow"
    if label == "热点龙头":
        return "leader_continuation"
    return "fresh_watch"


def build_intraday_setup_summary(
    raw: dict[str, Any],
    *,
    status: str = "fresh_candidate",
    active_theme: bool = False,
    flow_today_yi: float = 0.0,
) -> str:
    if raw.get("setup_summary"):
        return raw.get("setup_summary")

    setup_label = infer_intraday_setup_label(raw)
    if setup_label == "突破跟随":
        base = "盘中新出现的突破跟随票，优先确认放量站稳和资金承接。"
    elif setup_label == "回踩接力":
        base = "盘中新出现的回踩接力票，优先确认均线附近承接没有破坏。"
    elif setup_label == "低位反转":
        base = "盘中新出现的低位反转票，优先确认反转延续而不是单日脉冲。"
    elif setup_label == "热点龙头":
        base = "盘中新出现的主线强票，优先确认分时承接和二次上冲质量。"
    else:
        base = "盘中新出现的观察票，先用结构、资金和换手确认是否值得升级。"

    if status == "confirmed":
        base = base.replace("盘中新出现", "午盘确认")
    elif status == "downgraded":
        base = "午盘转弱的观察票，后续只保留复盘价值，不按原动作升级。"

    context: list[str] = []
    if active_theme:
        context.append("题材仍在午盘主线内")
    if flow_today_yi > 0:
        context.append("主力资金当前为正")
    if context:
        return f"{base} {'，'.join(context)}。"
    return base


def build_intraday_entry_plan(
    raw: dict[str, Any],
    *,
    status: str = "fresh_candidate",
    active_theme: bool = False,
    flow_today_yi: float = 0.0,
) -> dict[str, Any]:
    entry_plan = raw.get("entry_plan")
    if isinstance(entry_plan, dict) and entry_plan:
        return entry_plan

    trade_note = raw.get("trade_note") or {}
    change_pct = safe_float(raw.get("change_pct"), default=0.0) or 0.0
    score = safe_float(raw.get("score"), default=0.0) or 0.0

    trigger_level = price_level(nested_or_flat(raw, "technical_state", "high20") or raw.get("price"))
    pullback_level = price_level(
        nested_or_flat(raw, "technical_state", "ma5")
        or nested_or_flat(raw, "technical_state", "ma10")
    )
    invalidate_level = price_level(
        nested_or_flat(raw, "technical_state", "ma10")
        or nested_or_flat(raw, "technical_state", "ma20")
        or nested_or_flat(raw, "technical_state", "ma5")
    )

    pullback = price_text(pullback_level)
    trigger = price_text(trigger_level)
    invalidate = price_text(invalidate_level)

    if pullback and trigger:
        trigger_text = f"优先看 {pullback} 一带承接，或放量站稳 {trigger} 后再评估。"
    elif trigger:
        trigger_text = f"放量站稳 {trigger} 后再评估，盘中直线拉高不追。"
    elif pullback:
        trigger_text = f"优先看 {pullback} 一带承接，承接确认前只观察。"
    else:
        trigger_text = trade_note.get("watch_condition") or raw.get("watch_condition") or "先等换手和承接确认。"

    if invalidate:
        invalidate_text = f"跌回 {invalidate} 下方或主力转负就取消。"
    else:
        invalidate_text = raw.get("main_risk") or trade_note.get("main_risk") or "资金转负或结构走弱就取消。"

    if change_pct >= 7:
        avoid_text = "涨幅偏大，第一波拉高不追，等换手后的二次机会。"
    else:
        avoid_text = raw.get("main_risk") or trade_note.get("main_risk") or "没有站稳触发位或资金转弱时不追。"

    if status == "downgraded":
        action = "午盘转弱，暂停执行，只保留观察。"
        sizing = "先不开新仓"
    elif status == "confirmed":
        action = "午盘确认仍在，按触发条件继续跟踪。"
        sizing = "触发后小仓位试错"
    elif active_theme and flow_today_yi > 0 and score >= 90:
        action = "新增观察，等站稳触发位后轻仓试错。"
        sizing = "触发后 0.3 成以内试错"
    else:
        action = "新增观察，先等分时承接确认。"
        sizing = "先不开新仓，触发后再评估"

    return {
        "action": action,
        "trigger": trigger_text,
        "avoid": avoid_text,
        "invalidate": invalidate_text,
        "sizing": sizing,
        "levels": {
            "trigger": trigger_level,
            "pullback": pullback_level,
            "invalidate": invalidate_level,
        },
    }


def build_intraday_execution_quality(
    raw: dict[str, Any],
    *,
    status: str = "fresh_candidate",
    active_theme: bool = False,
    flow_today_yi: float = 0.0,
) -> dict[str, Any]:
    execution_quality = raw.get("execution_quality")
    if isinstance(execution_quality, dict) and execution_quality:
        return execution_quality

    positives: list[str] = []
    warnings: list[str] = []
    quality_score = 0
    score = safe_float(raw.get("score"), default=0.0) or 0.0
    change_pct = safe_float(raw.get("change_pct"), default=0.0) or 0.0
    amount_yi = safe_float(raw.get("amount_yi"), default=0.0) or 0.0

    if status == "confirmed":
        quality_score += 1
        positives.append("午盘确认仍在")
    elif status == "downgraded":
        warnings.append("午盘已降级")

    if amount_yi >= 20:
        quality_score += 2
        positives.append("成交额厚")
    elif amount_yi >= 8:
        quality_score += 1
        positives.append("成交额可跟踪")
    else:
        warnings.append("成交额不够厚")

    if flow_today_yi >= 1:
        quality_score += 2
        positives.append("资金确认强")
    elif flow_today_yi > 0:
        quality_score += 1
        positives.append("资金有承接")
    else:
        warnings.append("资金尚未确认")

    if score >= 95:
        quality_score += 2
        positives.append("综合评分领先")
    elif score >= 85:
        quality_score += 1
        positives.append("综合评分可跟踪")

    if active_theme:
        quality_score += 1
        positives.append("题材在午盘主线")
    elif status == "fresh_candidate":
        warnings.append("不在午盘前两条主线")

    if 1 <= change_pct <= 6.5:
        quality_score += 1
        positives.append("涨幅仍在可评估区间")
    elif change_pct > 7:
        warnings.append("涨幅偏大，追高性价比下降")

    label = "高执行质量" if quality_score >= 6 else ("中执行质量" if quality_score >= 3 else "低执行质量")
    return {
        "score": quality_score,
        "label": label,
        "positives": unique_keep_order(positives)[:4],
        "warnings": unique_keep_order(warnings)[:4],
    }


def build_intraday_observation_contract(
    raw: dict[str, Any],
    *,
    status: str = "fresh_candidate",
    active_theme: bool = False,
    flow_today_yi: Any = None,
) -> dict[str, Any]:
    flow_value = safe_float(flow_today_yi if flow_today_yi is not None else raw.get("flow_today_yi"), default=0.0) or 0.0
    return {
        "setup_type": infer_intraday_setup_type(raw),
        "setup_label": infer_intraday_setup_label(raw),
        "setup_summary": build_intraday_setup_summary(
            raw,
            status=status,
            active_theme=active_theme,
            flow_today_yi=flow_value,
        ),
        "entry_plan": build_intraday_entry_plan(
            raw,
            status=status,
            active_theme=active_theme,
            flow_today_yi=flow_value,
        ),
        "execution_quality": build_intraday_execution_quality(
            raw,
            status=status,
            active_theme=active_theme,
            flow_today_yi=flow_value,
        ),
    }
