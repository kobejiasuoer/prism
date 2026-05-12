#!/usr/bin/env python3
"""对进攻型选股扫描结果做二次筛选，并生成去重 shortlist。"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from prism_data import build_pipeline_manifest, load_manifest_file, write_sidecar_manifest

try:
    from screener.capital_flow_contract import (
        UNIT_YUAN,
        capital_flow_five_day_total_wan,
        capital_flow_today_wan,
        capital_flow_today_yi,
        normalize_capital_flow_payload,
        wan_to_yi,
    )
    from screener.parameters import (
        AI_SCREENING_EVALUATION_RULES,
        ENTRY_OUTPUT_DEFAULTS,
        EXECUTION_QUALITY_RULES,
        SETUP_PLAN_RULES,
        SETUP_THRESHOLDS,
        build_execution_gate,
    )
except ModuleNotFoundError:
    from capital_flow_contract import (
        UNIT_YUAN,
        capital_flow_five_day_total_wan,
        capital_flow_today_wan,
        capital_flow_today_yi,
        normalize_capital_flow_payload,
        wan_to_yi,
    )
    from parameters import (
        AI_SCREENING_EVALUATION_RULES,
        ENTRY_OUTPUT_DEFAULTS,
        EXECUTION_QUALITY_RULES,
        SETUP_PLAN_RULES,
        SETUP_THRESHOLDS,
        build_execution_gate,
    )

BASE = Path(__file__).resolve().parents[1]
DEFAULT_SCAN_PATH = BASE / "data" / "scan_result.json"
DEFAULT_OUTPUT_PATH = BASE / "data" / "ai_screening_result.json"
AI_HISTORY_DIR = BASE / "data" / "ai_history"

STRATEGY_LABELS = {
    "combined": "综合",
    "conservative": "稳健",
    "growth": "成长",
    "rebound": "反弹",
    "hot": "热门",
}

STATUS_RANK = {
    "approved": 2,
    "caution": 1,
    "excluded": 0,
}

SCREENING_RULES = [
    "保留 scan.py 已筛出的进攻型候选，按策略分别做二次过滤",
    "成交额不足或底层 attack_profile 已淘汰的股票，直接排除",
    "估值过热且盈利偏弱的股票，直接排除或降级观察",
    "资金延续性不足、短线过热、进攻纯度一般的股票，降级观察",
    "根据 market_regime 做攻守切换：弱势日压制进攻型通过率，中性日避免满仓追高",
    "追涨型 setup 必须额外满足执行质量、一致性和多策略共振，不再因单一策略高分直接放行",
    "跨策略去重后生成 shortlist，并给出建议送 analyzer 的前 3",
]


def load_sidecar_manifest(path: Path | str | None) -> dict | None:
    if not path:
        return None
    return load_manifest_file(Path(path).expanduser().with_suffix(".manifest.json"))


def ingress_summary(manifest: dict | None, manifest_path: Path | None) -> dict[str, object]:
    if not manifest:
        return {
            "dataset": "",
            "manifest_path": str(manifest_path) if manifest_path else "",
            "freshness_status": "expired",
            "live_small_allowed": False,
        }
    return {
        "dataset": manifest.get("dataset"),
        "manifest_path": str(manifest_path) if manifest_path else manifest.get("manifest_path") or "",
        "freshness_status": manifest.get("freshness_status"),
        "live_small_allowed": bool(manifest.get("live_small_allowed")),
    }


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_price(value):
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    if price <= 0:
        return None
    return round(price, 2)


def pick_price(*values):
    for value in values:
        price = safe_price(value)
        if price is not None:
            return price
    return None


def fmt_price(value):
    price = safe_price(value)
    return f"{price:.2f}" if price is not None else "-"


def unique_keep_order(values):
    seen = set()
    result = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def execution_gate_of(market_regime=None):
    regime = market_regime or {}
    metrics = regime.get("metrics") or {}
    candidate_view = regime.get("candidate_view") or {}
    candidate_metrics = candidate_view.get("metrics") or {}
    gate = {}
    if metrics or candidate_view:
        gate = build_execution_gate(regime, candidate_view or {"metrics": candidate_metrics})

    else:
        gate = regime.get("execution_gate") or {}

    status = gate.get("status") or ("on" if regime.get("attack_ok", True) else "off")
    gate["status"] = status
    gate.setdefault("position_cap", "0.5-0.8成试错" if status == "on" else ("0.3-0.5成以内" if status == "limited" else "0成"))
    gate.setdefault("allowed_setups", ["leader_continuation", "breakout_follow", "pullback_continuation", "low_reversal"])
    gate.setdefault("allow_handoff", status == "on")
    gate.setdefault("allow_new_positions", status != "off")
    gate.setdefault("risk_flags", [])
    gate.setdefault("summary", "")
    gate.setdefault("label", "")
    return gate


def normalize_strategies(scan_data):
    if isinstance(scan_data.get("strategies"), dict):
        return scan_data["strategies"]

    strategy = scan_data.get("strategy", "combined")
    candidates = scan_data.get("candidates") or []
    return {strategy: candidates}


def _resolve_setup_copy(copy_rules, with_levels_key, without_levels_key, use_levels, **kwargs):
    template = copy_rules[with_levels_key] if use_levels else copy_rules[without_levels_key]
    return template.format(**kwargs) if use_levels else template


def build_setup_plan(stock, decision, market_themes=None):
    technical_state = stock.get("technical_state") or {}
    capital_flow = stock.get("capital_flow") or {}
    attack_profile = stock.get("attack_profile") or {}
    theme = stock.get("theme") or "其他"
    theme_items = (market_themes or {}).get("themes") or []
    top_theme_names = [item.get("theme") for item in theme_items[:2] if item.get("theme")]

    price = safe_price(stock.get("price"))
    ma5 = safe_price(technical_state.get("ma5"))
    ma10 = safe_price(technical_state.get("ma10"))
    ma20 = safe_price(technical_state.get("ma20"))
    high20 = safe_price(technical_state.get("high20"))
    low20 = safe_price(technical_state.get("low20"))
    pos20 = safe_float(technical_state.get("position_20d"), default=0.5)
    change_pct = safe_float(stock.get("change_pct"))
    amount_yi = safe_float(stock.get("amount_yi"))
    overheat_penalty = safe_float(stock.get("overheat_penalty"))
    flow_today_yi = capital_flow_today_yi(capital_flow, legacy_source_unit=UNIT_YUAN)
    flow_trend = capital_flow.get("trend") or "无数据"
    signals = stock.get("signals") or []
    consistency_score = safe_float((decision or {}).get("consistency_score"), default=0.0)

    trigger_price = pick_price(high20, price)
    pullback_price = pick_price(ma5, ma10, ma20, price)
    invalidate_price = pick_price(ma10, ma20, low20, price * 0.95 if price else None)
    recovery_price = pick_price(ma5, ma10, price)
    is_top_theme = theme != "其他" and theme in top_theme_names

    setup_rules = SETUP_PLAN_RULES
    default_setup = setup_rules["default"]
    setup_type = default_setup["setup_type"]
    setup_label = default_setup["setup_label"]
    setup_summary = default_setup["setup_summary"]
    action = default_setup["action"]
    trigger = default_setup["trigger"]
    avoid = default_setup["avoid"]
    invalidate = default_setup["invalidate"]

    leader_thresholds = SETUP_THRESHOLDS["leader_continuation"]
    low_reversal_thresholds = SETUP_THRESHOLDS["low_reversal"]
    breakout_thresholds = SETUP_THRESHOLDS["breakout_follow"]
    pullback_thresholds = SETUP_THRESHOLDS["pullback_continuation"]

    if (
        is_top_theme
        and change_pct >= leader_thresholds["min_change_pct"]
        and amount_yi >= leader_thresholds["min_amount_yi"]
        and flow_today_yi > 0
        and attack_profile.get("status") == "keep"
    ):
        leader_rules = setup_rules["leader_continuation"]
        setup_type = "leader_continuation"
        setup_label = leader_rules["setup_label"]
        setup_summary = leader_rules["setup_summary"]
        action = leader_rules["action"]
        trigger = _resolve_setup_copy(
            leader_rules,
            "trigger_with_levels",
            "trigger_without_levels",
            pullback_price is not None or trigger_price is not None,
            pullback_price=fmt_price(pullback_price),
            trigger_price=fmt_price(trigger_price),
        )
        avoid = leader_rules["avoid"]
        invalidate = _resolve_setup_copy(
            leader_rules,
            "invalidate_with_level",
            "invalidate_without_level",
            invalidate_price is not None,
            invalidate_price=fmt_price(invalidate_price),
        )
    elif (
        pos20 <= low_reversal_thresholds["max_position_20d"]
        and change_pct > 0
        and (
            flow_today_yi > 0
            or "转正" in flow_trend
            or any("低位反弹" in signal for signal in signals)
        )
    ):
        reversal_rules = setup_rules["low_reversal"]
        setup_type = "low_reversal"
        setup_label = reversal_rules["setup_label"]
        setup_summary = reversal_rules["setup_summary"]
        action = reversal_rules["action"]
        trigger = _resolve_setup_copy(
            reversal_rules,
            "trigger_with_levels",
            "trigger_without_levels",
            recovery_price is not None,
            recovery_price=fmt_price(recovery_price),
        )
        avoid = reversal_rules["avoid"]
        invalidate = _resolve_setup_copy(
            reversal_rules,
            "invalidate_with_level",
            "invalidate_without_level",
            invalidate_price is not None,
            invalidate_price=fmt_price(invalidate_price),
        )
    elif pos20 >= breakout_thresholds["min_position_20d"] and flow_today_yi > 0 and attack_profile.get("status") == "keep":
        breakout_rules = setup_rules["breakout_follow"]
        setup_type = "breakout_follow"
        setup_label = breakout_rules["setup_label"]
        setup_summary = breakout_rules["setup_summary"]
        action = breakout_rules["action"]
        trigger = _resolve_setup_copy(
            breakout_rules,
            "trigger_with_levels",
            "trigger_without_levels",
            trigger_price is not None or pullback_price is not None,
            trigger_price=fmt_price(trigger_price),
            pullback_price=fmt_price(pullback_price),
        )
        avoid = breakout_rules["avoid"]
        invalidate = _resolve_setup_copy(
            breakout_rules,
            "invalidate_with_level",
            "invalidate_without_level",
            invalidate_price is not None,
            invalidate_price=fmt_price(invalidate_price),
        )
    elif pos20 >= pullback_thresholds["min_position_20d"] and (flow_today_yi > 0 or "流入" in flow_trend or "转正" in flow_trend):
        pullback_rules = setup_rules["pullback_continuation"]
        setup_type = "pullback_continuation"
        setup_label = pullback_rules["setup_label"]
        setup_summary = pullback_rules["setup_summary"]
        action = pullback_rules["action"]
        trigger = _resolve_setup_copy(
            pullback_rules,
            "trigger_with_levels",
            "trigger_without_levels",
            pullback_price is not None,
            pullback_price=fmt_price(pullback_price),
        )
        avoid = pullback_rules["avoid"]
        invalidate = _resolve_setup_copy(
            pullback_rules,
            "invalidate_with_level",
            "invalidate_without_level",
            invalidate_price is not None,
            invalidate_price=fmt_price(invalidate_price),
        )

    modifier_rules = setup_rules["modifiers"]
    overheat_modifier = modifier_rules["trend_setup_overheat"]
    if (
        overheat_penalty >= overheat_modifier["overheat_penalty_at_least"]
        and setup_type in set(overheat_modifier["setup_types"])
    ):
        avoid = overheat_modifier["avoid"]
    consistency_modifier = modifier_rules["low_consistency"]
    if (
        consistency_score <= consistency_modifier["consistency_score_at_most"]
        and setup_type not in set(consistency_modifier["exclude_setup_types"])
    ):
        setup_summary += consistency_modifier["summary_suffix"]

    return {
        "setup_type": setup_type,
        "setup_label": setup_label,
        "setup_summary": setup_summary,
        "entry_plan": {
            "action": action,
            "trigger": trigger,
            "avoid": avoid,
            "invalidate": invalidate,
            "sizing": "",
            "levels": {
                "trigger": trigger_price,
                "pullback": pullback_price,
                "invalidate": invalidate_price,
            },
        },
    }


def build_execution_quality(stock, decision, setup_plan, market_regime=None, market_themes=None):
    capital_flow = stock.get("capital_flow") or {}
    signals = stock.get("signals") or []
    theme = stock.get("theme") or "其他"
    setup_type = setup_plan.get("setup_type") or "watch_only"
    change_pct = safe_float(stock.get("change_pct"))
    amount_yi = safe_float(stock.get("amount_yi"))
    overheat_penalty = safe_float(stock.get("overheat_penalty"))
    flow_today_yi = capital_flow_today_yi(capital_flow, legacy_source_unit=UNIT_YUAN)
    flow_trend = capital_flow.get("trend") or "无数据"
    consistency_score = safe_float((decision or {}).get("consistency_score"), default=0)
    gate_status = execution_gate_of(market_regime).get("status")
    notice_risk_tags = stock.get("notice_risk_tags") or []

    theme_items = (market_themes or {}).get("themes") or []
    top_theme_names = [item.get("theme") for item in theme_items[:2] if item.get("theme")]
    persistence_map = {
        item.get("theme"): item.get("persistence") or {}
        for item in theme_items
        if item.get("theme")
    }
    persistence = persistence_map.get(theme) or {}
    persistence_label = persistence.get("label") or ""

    quality_rules = EXECUTION_QUALITY_RULES
    amount_rules = quality_rules["amount_yi"]
    flow_rules = quality_rules["capital_flow"]
    consistency_rules = quality_rules["consistency"]
    setup_rules = quality_rules["setup_type"]
    friendly_setups = set(setup_rules["friendly_types"])
    trend_setups = set(setup_rules["trend_types"])

    score = 0
    positives = []
    warnings = []

    if amount_yi >= amount_rules["high"]["at_least"]:
        score += amount_rules["high"]["score"]
        positives.append(amount_rules["high"]["positive"])
    elif amount_yi >= amount_rules["medium"]["at_least"]:
        score += amount_rules["medium"]["score"]
        positives.append(amount_rules["medium"]["positive"])
    else:
        score += amount_rules["low"]["score"]
        warnings.append(amount_rules["low"]["warning"])

    if stock.get("has_capital_flow", True):
        if flow_today_yi >= flow_rules["high"]["at_least"]:
            score += flow_rules["high"]["score"]
            positives.append(flow_rules["high"]["positive"])
        elif flow_today_yi > 0 or flow_rules["medium"]["trend_keyword"] in flow_trend:
            score += flow_rules["medium"]["score"]
            positives.append(flow_rules["medium"]["positive"])
        else:
            score += flow_rules["low"]["score"]
            warnings.append(flow_rules["low"]["warning"])
    else:
        score += flow_rules["missing"]["score"]
        warnings.append(flow_rules["missing"]["warning"])

    if consistency_score >= consistency_rules["high"]["at_least"]:
        score += consistency_rules["high"]["score"]
        positives.append(consistency_rules["high"]["positive"])
    elif consistency_score >= consistency_rules["medium"]["at_least"]:
        score += consistency_rules["medium"]["score"]
        positives.append(consistency_rules["medium"]["positive"])
    else:
        score += consistency_rules["low"]["score"]
        warnings.append(consistency_rules["low"]["warning"])

    if setup_type in friendly_setups:
        score += setup_rules["friendly"]["score"]
        positives.append(setup_rules["friendly"]["positive"])
    elif setup_type in trend_setups:
        positives.append(setup_rules["trend"]["positive"])
    else:
        score += setup_rules["other"]["score"]
        warnings.append(setup_rules["other"]["warning"])

    if theme != "其他" and theme in top_theme_names:
        score += quality_rules["top_theme"]["score"]
        positives.append(quality_rules["top_theme"]["positive"])

    persistence_rule = quality_rules["theme_persistence"].get(persistence_label)
    if persistence_rule:
        score += persistence_rule["score"]
        if persistence_rule.get("positive"):
            positives.append(persistence_rule["positive"])
        if persistence_rule.get("warning"):
            warnings.append(persistence_rule["warning"])

    overheat_rules = quality_rules["overheat_penalty"]
    if overheat_penalty >= overheat_rules["high"]["at_least"]:
        score += overheat_rules["high"]["score"]
        warnings.append(overheat_rules["high"]["warning"])
    elif overheat_penalty >= overheat_rules["medium"]["at_least"]:
        score += overheat_rules["medium"]["score"]
        warnings.append(overheat_rules["medium"]["warning"])

    if setup_type in trend_setups:
        chase_rules = quality_rules["trend_setup_change_pct"]
        if change_pct >= chase_rules["high"]["at_least"]:
            score += chase_rules["high"]["score"]
            warnings.append(chase_rules["high"]["warning"])
        elif change_pct >= chase_rules["medium"]["at_least"]:
            score += chase_rules["medium"]["score"]
            warnings.append(chase_rules["medium"]["warning"])

    if any("量价顶背离" in signal or "资金背离" in signal for signal in signals):
        score += quality_rules["divergence"]["score"]
        warnings.append(quality_rules["divergence"]["warning"])

    if notice_risk_tags:
        score += quality_rules["notice_risk"]["score"]
        warnings.append(quality_rules["notice_risk"]["warning"])

    if gate_status == "off":
        score += quality_rules["execution_gate"]["off"]["score"]
        warnings.append(quality_rules["execution_gate"]["off"]["warning"])
    elif gate_status == "limited" and setup_type in trend_setups:
        score += quality_rules["execution_gate"]["limited_trend"]["score"]
        warnings.append(quality_rules["execution_gate"]["limited_trend"]["warning"])

    label_rules = quality_rules["labels"]
    label = (
        label_rules["high"]["label"]
        if score >= label_rules["high"]["at_least"]
        else (
            label_rules["medium"]["label"]
            if score >= label_rules["medium"]["at_least"]
            else label_rules["low"]["label"]
        )
    )
    return {
        "score": score,
        "label": label,
        "positives": unique_keep_order(positives)[:4],
        "warnings": unique_keep_order(warnings)[:4],
    }


def evaluate_stock(stock, market_regime=None, market_themes=None):
    fundamentals = stock.get("fundamentals") or {}
    trade_note = stock.get("trade_note") or {}
    capital_flow = stock.get("capital_flow") or {}
    attack_profile = stock.get("attack_profile") or {}
    theme = stock.get("theme") or "其他"

    theme_items = (market_themes or {}).get("themes") or []
    theme_persistence_map = {}
    top_theme_names = []
    for idx, item in enumerate(theme_items):
        key = item.get("theme")
        if key:
            theme_persistence_map[key] = item.get("persistence") or {}
            if idx < 2:
                top_theme_names.append(key)
    theme_persistence = theme_persistence_map.get(theme) or {}

    pe = safe_float(fundamentals.get("pe_ttm"))
    roe_raw = fundamentals.get("roe")
    roe = safe_float(roe_raw) if roe_raw is not None else None
    amount_yi = safe_float(stock.get("amount_yi"))
    flow_today_yi = capital_flow_today_yi(capital_flow, legacy_source_unit=UNIT_YUAN)
    flow_trend = capital_flow.get("trend") or "无数据"
    attack_status = attack_profile.get("status") or "keep"
    overheat_penalty = safe_float(stock.get("overheat_penalty"))
    has_capital_flow = stock.get("has_capital_flow", True)
    change_pct = safe_float(stock.get("change_pct"))
    signals = stock.get("signals") or []
    notice_risk_tags = stock.get("notice_risk_tags") or []

    evaluation_rules = AI_SCREENING_EVALUATION_RULES
    amount_rules = evaluation_rules["amount_yi"]
    valuation_rules = evaluation_rules["valuation"]
    flow_rules = evaluation_rules["capital_flow"]
    theme_rules = evaluation_rules["theme"]
    regime_rules = evaluation_rules["regime"]

    hard_reasons = []
    caution_reasons = []
    positives = []
    consistency = 0
    consistency_notes = []

    if amount_yi < amount_rules["hard_below"]["value"]:
        hard_reasons.append(amount_rules["hard_below"]["reason"])
    elif amount_yi >= amount_rules["positive"]["at_least"]:
        positives.append(amount_rules["positive"]["signal"])
        consistency += amount_rules["positive"]["consistency_delta"]
        consistency_notes.append(amount_rules["positive"]["note"])

    if attack_status == "exclude":
        hard_reasons.append("底层进攻标签已判定不匹配")
    elif attack_status == "downgrade":
        caution_reasons.append("进攻纯度一般，先降级观察")
    else:
        consistency += 2
        consistency_notes.append("进攻风格匹配")

    if pe >= valuation_rules["hard_high_pe_low_roe"]["pe_at_least"] and roe is not None and roe < valuation_rules["hard_high_pe_low_roe"]["roe_below"]:
        hard_reasons.append(valuation_rules["hard_high_pe_low_roe"]["reason"])
    elif pe >= valuation_rules["caution_high_pe_missing_roe"]["pe_at_least"] and roe is None:
        caution_reasons.append(valuation_rules["caution_high_pe_missing_roe"]["reason"])
    elif pe <= valuation_rules["caution_non_positive_pe"]["pe_at_most"]:
        caution_reasons.append(valuation_rules["caution_non_positive_pe"]["reason"])
    elif pe >= valuation_rules["caution_high_pe_low_roe"]["pe_at_least"] and roe is not None and roe < valuation_rules["caution_high_pe_low_roe"]["roe_below"]:
        caution_reasons.append(valuation_rules["caution_high_pe_low_roe"]["reason"])

    if not has_capital_flow:
        caution_reasons.append(flow_rules["missing"]["reason"])
    elif flow_today_yi > 0:
        positives.append(flow_rules["positive"]["signal"])
        consistency += flow_rules["positive"]["consistency_delta"]
        consistency_notes.append(flow_rules["positive"]["note"])
    elif flow_rules["repair"]["trend_keyword"] in flow_trend:
        positives.append(flow_rules["repair"]["signal"])
        consistency += flow_rules["repair"]["consistency_delta"]
        consistency_notes.append(flow_rules["repair"]["note"])
    else:
        caution_reasons.append(flow_rules["weak"]["reason"])
        consistency += flow_rules["weak"]["consistency_delta"]

    overheat_rules = evaluation_rules["overheat_penalty"]
    if overheat_penalty >= overheat_rules["high"]["at_least"]:
        caution_reasons.append(overheat_rules["high"]["reason"])
        consistency += overheat_rules["high"]["consistency_delta"]
    elif overheat_penalty >= overheat_rules["medium"]["at_least"]:
        caution_reasons.append(overheat_rules["medium"]["reason"])
        consistency += overheat_rules["medium"]["consistency_delta"]

    if any("量价顶背离" in s or "资金背离" in s for s in signals):
        caution_reasons.append(evaluation_rules["divergence"]["reason"])
        consistency += evaluation_rules["divergence"]["consistency_delta"]

    if notice_risk_tags:
        labels = sorted({item.get("label") for item in notice_risk_tags if item.get("label")})
        if labels:
            notice_rules = evaluation_rules["notice_risk"]
            caution_reasons.append(notice_rules["reason_prefix"] + "/".join(labels))
            consistency += notice_rules["consistency_delta"]
            severe_labels = set(notice_rules["severe_labels"])
            if any(label in severe_labels for label in labels):
                caution_reasons.append(notice_rules["severe"]["reason"])
                consistency += notice_rules["severe"]["consistency_delta"]

    price_action_rule = evaluation_rules["price_action"]["limit_up_like"]
    if change_pct >= price_action_rule["at_least"]:
        caution_reasons.append(price_action_rule["reason"])
        consistency += price_action_rule["consistency_delta"]

    if theme != "其他" and theme in top_theme_names:
        consistency += theme_rules["top_theme"]["consistency_delta"]
        consistency_notes.append(theme_rules["top_theme"]["note"])

    persistence_label = theme_persistence.get("label") or ""
    persistence_score = safe_float(theme_persistence.get("score"), default=0)
    persistence_rule = theme_rules["persistence"].get(persistence_label)
    if persistence_rule:
        consistency += persistence_rule["consistency_delta"]
        consistency_notes.append(persistence_rule["note"])

    resonance_rule = theme_rules["price_resonance"]
    if (
        persistence_score >= resonance_rule["persistence_score_at_least"]
        and change_pct >= resonance_rule["change_pct_at_least"]
    ):
        positives.append(resonance_rule["positive"])
    else:
        weak_theme_rule = theme_rules["weak_persistence_discount"]
        if (
            persistence_score <= weak_theme_rule["persistence_score_at_most"]
            and change_pct >= weak_theme_rule["change_pct_at_least"]
        ):
            caution_reasons.append(weak_theme_rule["reason"])
            consistency += weak_theme_rule["consistency_delta"]

    if pe > 0 and pe <= valuation_rules["match"]["pe_at_most"] and (roe is None or roe >= valuation_rules["match"]["roe_at_least_if_present"]):
        consistency += valuation_rules["match"]["consistency_delta"]
        consistency_notes.append(valuation_rules["match"]["note"])
    elif pe >= valuation_rules["mismatch"]["pe_at_least"] and (roe is None or roe < valuation_rules["mismatch"]["roe_below_or_missing"]):
        consistency += valuation_rules["mismatch"]["consistency_delta"]
        consistency_notes.append(valuation_rules["mismatch"]["note"])

    regime_score = safe_float((market_regime or {}).get("score"), default=0.0)
    execution_gate = execution_gate_of(market_regime)
    gate_status = execution_gate.get("status")
    if gate_status == "off":
        caution_reasons.append(regime_rules["off"]["reason"])
        consistency += regime_rules["off"]["consistency_delta"]
    elif gate_status == "limited":
        caution_reasons.append(regime_rules["limited"]["reason"])
        consistency += regime_rules["limited"]["consistency_delta"]
        limited_guard = regime_rules["limited"]["extra_guard"]
        if change_pct >= limited_guard["change_pct_at_least"] or overheat_penalty >= limited_guard["overheat_penalty_at_least"]:
            caution_reasons.append(limited_guard["reason"])
            consistency += limited_guard["consistency_delta"]
    elif regime_score < regime_rules["on_guard"]["regime_score_below"] and change_pct >= regime_rules["on_guard"]["change_pct_at_least"]:
        caution_reasons.append(regime_rules["on_guard"]["reason"])
        consistency += regime_rules["on_guard"]["consistency_delta"]

    if not trade_note.get("watch_condition"):
        caution_reasons.append("缺少明确的次日观察条件")

    if hard_reasons:
        status = "excluded"
        reason = hard_reasons[0]
    elif caution_reasons:
        status = "caution"
        reason = caution_reasons[0]
    else:
        status = "approved"
        reason = positives[0] if positives else "通过二次筛选"

    label_rules = evaluation_rules["consistency_labels"]
    consistency_label = (
        label_rules["high"]["label"]
        if consistency >= label_rules["high"]["at_least"]
        else (
            label_rules["medium"]["label"]
            if consistency >= label_rules["medium"]["at_least"]
            else label_rules["low"]["label"]
        )
    )
    downgrade_rule = evaluation_rules["approved_downgrade"]
    if consistency <= downgrade_rule["at_most"] and status == "approved":
        status = "caution"
        reason = downgrade_rule["reason"]
        caution_reasons.append(reason)

    priority_note_keys = [
        "主题持续增强",
        "主题强势延续",
        "主题延续但分化",
        "主题热度衰减",
        "主题一日游风险",
        "估值与盈利错配",
        "资金同向",
        "资金修复",
        "流动性支持",
        "进攻风格匹配",
        "主线主题加成",
        "估值盈利匹配尚可",
    ]
    ranked_notes = []
    for key in priority_note_keys:
        for note in consistency_notes:
            if note == key and note not in ranked_notes:
                ranked_notes.append(note)
    for note in consistency_notes:
        if note not in ranked_notes:
            ranked_notes.append(note)

    notes = unique_keep_order(hard_reasons + caution_reasons + positives)
    return {
        "status": status,
        "reason": reason,
        "notes": notes[:5],
        "hard_reasons": hard_reasons,
        "caution_reasons": caution_reasons,
        "positive_signals": positives[:4],
        "capital_trend": flow_trend,
        "flow_today_yi": round(flow_today_yi, 2),
        "consistency_score": consistency,
        "consistency_label": consistency_label,
        "consistency_notes": ranked_notes[:4],
        "execution_gate_status": gate_status,
    }


def build_stock_entry(stock, strategy_name, decision, market_regime=None, market_themes=None):
    fundamentals = stock.get("fundamentals") or {}
    trade_note = stock.get("trade_note") or {}
    attack_profile = stock.get("attack_profile") or {}
    capital_flow = stock.get("capital_flow") or {}
    normalized_capital_flow = normalize_capital_flow_payload(capital_flow, legacy_source_unit=UNIT_YUAN)
    today_wan = capital_flow_today_wan(capital_flow, legacy_source_unit=UNIT_YUAN)
    five_day_total_wan = capital_flow_five_day_total_wan(capital_flow, legacy_source_unit=UNIT_YUAN)
    normalized_capital_flow["trend"] = decision["capital_trend"]
    normalized_capital_flow["today"] = today_wan
    normalized_capital_flow["today_wan"] = today_wan
    normalized_capital_flow["today_yi"] = decision["flow_today_yi"]
    normalized_capital_flow["flow_today_yi"] = decision["flow_today_yi"]
    normalized_capital_flow["5day_total"] = five_day_total_wan
    normalized_capital_flow["five_day_total_wan"] = five_day_total_wan
    normalized_capital_flow["five_day_total_yi"] = wan_to_yi(five_day_total_wan)
    setup_plan = build_setup_plan(stock, decision, market_themes=market_themes)
    execution_quality = build_execution_quality(
        stock,
        decision,
        setup_plan,
        market_regime=market_regime,
        market_themes=market_themes,
    )

    return {
        "code": stock.get("code"),
        "name": stock.get("name"),
        "score": round(safe_float(stock.get("score")), 2),
        "change_pct": round(safe_float(stock.get("change_pct")), 2),
        "amount_yi": round(safe_float(stock.get("amount_yi")), 1),
        "theme": stock.get("theme") or "其他",
        "signals": (stock.get("signals") or [])[:5],
        "strategy": strategy_name,
        "strategy_label": STRATEGY_LABELS.get(strategy_name, strategy_name),
        "screening": decision,
        "setup_type": setup_plan["setup_type"],
        "setup_label": setup_plan["setup_label"],
        "setup_summary": setup_plan["setup_summary"],
        "entry_plan": setup_plan["entry_plan"],
        "execution_quality": execution_quality,
        "entry_reason": trade_note.get("entry_reason") or attack_profile.get("reason") or ENTRY_OUTPUT_DEFAULTS["entry_reason"],
        "main_risk": trade_note.get("main_risk") or decision["reason"],
        "watch_condition": trade_note.get("watch_condition") or ENTRY_OUTPUT_DEFAULTS["watch_condition"],
        "capital_flow": normalized_capital_flow,
        "attack_profile": {
            "status": attack_profile.get("status"),
            "bias_score": attack_profile.get("bias_score"),
            "tags": (attack_profile.get("tags") or [])[:4],
        },
        "consistency": {
            "score": decision.get("consistency_score"),
            "label": decision.get("consistency_label"),
            "notes": decision.get("consistency_notes", []),
        },
        "fundamentals": {
            "pe_ttm": fundamentals.get("pe_ttm"),
            "roe": fundamentals.get("roe"),
            "pb": fundamentals.get("pb"),
            "net_profit": fundamentals.get("net_profit"),
        },
        "notice_risk_tags": stock.get("notice_risk_tags") or [],
    }


def apply_execution_gate(entry, market_regime=None):
    gate = execution_gate_of(market_regime)
    status = gate.get("status")
    screening = entry.get("screening") or {}
    current_status = screening.get("status")
    entry_plan = entry.get("entry_plan") or {}
    setup_type = entry.get("setup_type") or "watch_only"
    gate_summary = gate.get("summary") or ""
    allowed_setups = set(gate.get("allowed_setups") or [])
    quality = entry.get("execution_quality") or {}
    quality_score = safe_float(quality.get("score"), default=0)
    consistency_score = safe_float((entry.get("consistency") or {}).get("score"), default=0)

    if status == "off":
        if current_status != "excluded":
            screening["status"] = "caution"
            screening["reason"] = "风控阀门关闭，今天只观察不执行"
            notes = screening.get("notes") or []
            screening["notes"] = unique_keep_order(["风控阀门关闭，取消今日开仓"] + notes)
        entry_plan["sizing"] = "先不开新仓"
        entry_plan["action"] = "今天不新开仓，只保留观察名单。"
        entry_plan["trigger"] = "等待风控阀门重新打开后再评估。"
        entry_plan["invalidate"] = entry_plan.get("invalidate") or "环境未改善前不执行。"
        if gate_summary:
            entry["setup_summary"] = f"{entry.get('setup_summary', '')} {gate_summary}".strip()
    elif status == "limited":
        if current_status == "approved" and (
            setup_type not in allowed_setups
            or quality_score < 4
            or consistency_score < 2
        ):
            screening["status"] = "caution"
            screening["reason"] = "风控阀门半开，当前执行质量不够"
            notes = screening.get("notes") or []
            screening["notes"] = unique_keep_order(["当前只允许高质量的回踩/低位反转轻仓试错"] + notes)
            entry_plan["sizing"] = "先不开新仓"
            entry_plan["action"] = "当前不做这类 setup，等更清楚的回踩承接后再看。"
            entry_plan["trigger"] = "只保留观察，等执行质量和承接同步改善后再评估。"
        elif current_status == "approved":
            entry_plan["sizing"] = "0.3-0.5成以内"
            entry_plan["action"] = "轻仓试错，优先等回踩确认。"
        else:
            entry_plan["sizing"] = "先不开新仓"
        if gate_summary:
            entry["setup_summary"] = f"{entry.get('setup_summary', '')} {gate_summary}".strip()
    elif current_status == "approved":
        if quality_score < 4:
            screening["status"] = "caution"
            screening["reason"] = "执行质量不足，先观察"
            notes = screening.get("notes") or []
            screening["notes"] = unique_keep_order(["执行质量不足，暂不直接执行"] + notes)
            entry_plan["sizing"] = "先不开新仓"
            entry_plan["action"] = "先观察，不急着上车。"
            entry_plan["trigger"] = "等资金、承接和位置更同步时再评估。"
        elif setup_type in {"leader_continuation", "breakout_follow"} and (quality_score < 6 or consistency_score < 3):
            screening["status"] = "caution"
            screening["reason"] = "追涨型 setup 证据不够，先观察"
            notes = screening.get("notes") or []
            screening["notes"] = unique_keep_order(["追涨型 setup 需要更强共振确认"] + notes)
            entry_plan["sizing"] = "先不开新仓"
            entry_plan["action"] = "先等换手和承接确认，不抢第一波。"
            entry_plan["trigger"] = "至少等二次确认后再评估。"

    entry["screening"] = screening
    entry["entry_plan"] = entry_plan
    entry["execution_gate"] = {
        "status": status,
        "label": gate.get("label"),
        "summary": gate_summary,
        "position_cap": gate.get("position_cap"),
    }
    return entry


def sort_selected(entries):
    return sorted(
        entries,
        key=lambda item: (
            STATUS_RANK.get(item["screening"]["status"], -1),
            item.get("score", 0),
            item.get("amount_yi", 0),
        ),
        reverse=True,
    )


def summarize_strategy(strategy_name, stocks, market_regime=None, market_themes=None):
    selected = []
    excluded = []

    for stock in stocks:
        decision = evaluate_stock(stock, market_regime=market_regime, market_themes=market_themes)
        entry = build_stock_entry(
            stock,
            strategy_name,
            decision,
            market_regime=market_regime,
            market_themes=market_themes,
        )
        entry = apply_execution_gate(entry, market_regime=market_regime)
        decision = entry.get("screening") or decision
        if decision["status"] == "excluded":
            excluded.append(
                {
                    "code": entry["code"],
                    "name": entry["name"],
                    "score": entry["score"],
                    "reason": decision["reason"],
                }
            )
            continue
        selected.append(entry)

    selected = sort_selected(selected)
    approved_count = sum(1 for item in selected if item["screening"]["status"] == "approved")
    caution_count = sum(1 for item in selected if item["screening"]["status"] == "caution")

    return {
        "label": STRATEGY_LABELS.get(strategy_name, strategy_name),
        "original_count": len(stocks),
        "selected_count": len(selected),
        "approved_count": approved_count,
        "caution_count": caution_count,
        "excluded_count": len(excluded),
        "selected_stocks": selected,
        "top_stocks": selected[:5],
        "excluded_stocks": excluded[:5],
    }


def aggregate_shortlist(strategy_views, raw_strategies, market_regime=None):
    execution_gate = execution_gate_of(market_regime)
    gate_status = execution_gate.get("status")
    shortlisted = {}
    raw_codes = set()
    excluded_only_codes = set()

    for stocks in raw_strategies.values():
        for stock in stocks:
            code = stock.get("code")
            if code:
                raw_codes.add(code)

    for strategy_name, view in strategy_views.items():
        for excluded in view["excluded_stocks"]:
            code = excluded.get("code")
            if code:
                excluded_only_codes.add(code)

        for item in view["selected_stocks"]:
            code = item["code"]
            if code not in shortlisted:
                shortlisted[code] = {
                    "code": code,
                    "name": item["name"],
                    "best_score": item["score"],
                    "change_pct": item["change_pct"],
                    "amount_yi": item["amount_yi"],
                    "strategy_hits": [],
                    "strategy_labels": [],
                    "themes": [],
                    "statuses": [],
                    "entry_reason": item["entry_reason"],
                    "main_risk": item["main_risk"],
                    "watch_condition": item["watch_condition"],
                    "signals": item["signals"],
                    "setup_type": item.get("setup_type"),
                    "setup_label": item.get("setup_label"),
                    "setup_summary": item.get("setup_summary"),
                    "entry_plan": item.get("entry_plan") or {},
                    "screening_reasons": [],
                    "capital_flow": item["capital_flow"],
                    "attack_profile": item["attack_profile"],
                    "fundamentals": item["fundamentals"],
                    "consistency": item.get("consistency") or {},
                    "execution_quality": item.get("execution_quality") or {},
                    "variants": [],
                }

            agg = shortlisted[code]
            agg["strategy_hits"].append(strategy_name)
            agg["strategy_labels"].append(item["strategy_label"])
            agg["themes"].append(item["theme"])
            agg["statuses"].append(item["screening"]["status"])
            agg["screening_reasons"].append(item["screening"]["reason"])
            agg["variants"].append(
                {
                    "strategy": strategy_name,
                    "strategy_label": item["strategy_label"],
                    "score": item["score"],
                    "status": item["screening"]["status"],
                    "reason": item["screening"]["reason"],
                    "consistency": item.get("consistency") or {},
                }
            )

            current_consistency = item.get("consistency") or {}
            agg_consistency = agg.get("consistency") or {}
            current_consistency_score = safe_float(current_consistency.get("score"), default=-999)
            agg_consistency_score = safe_float(agg_consistency.get("score"), default=-999)

            if item["score"] >= agg["best_score"]:
                agg["best_score"] = item["score"]
                agg["change_pct"] = item["change_pct"]
                agg["amount_yi"] = item["amount_yi"]
                agg["entry_reason"] = item["entry_reason"]
                agg["main_risk"] = item["main_risk"]
                agg["watch_condition"] = item["watch_condition"]
                agg["signals"] = item["signals"]
                agg["setup_type"] = item.get("setup_type")
                agg["setup_label"] = item.get("setup_label")
                agg["setup_summary"] = item.get("setup_summary")
                agg["entry_plan"] = item.get("entry_plan") or {}
                agg["capital_flow"] = item["capital_flow"]
                agg["attack_profile"] = item["attack_profile"]
                agg["fundamentals"] = item["fundamentals"]
                agg["consistency"] = current_consistency
                agg["execution_quality"] = item.get("execution_quality") or {}
            elif current_consistency_score > agg_consistency_score:
                agg["consistency"] = current_consistency

    shortlist = []
    for item in shortlisted.values():
        item["strategy_hits"] = unique_keep_order(item["strategy_hits"])
        item["strategy_labels"] = unique_keep_order(item["strategy_labels"])
        item["themes"] = unique_keep_order(item["themes"])
        item["screening_reasons"] = unique_keep_order(item["screening_reasons"])
        item["screening_status"] = "approved" if "approved" in item["statuses"] else "caution"
        item["screening_note"] = item["screening_reasons"][0] if item["screening_reasons"] else item["entry_reason"]
        item["strategy_count"] = len(item["strategy_hits"])
        item["approved_hits"] = sum(1 for status in item["statuses"] if status == "approved")
        item["caution_hits"] = sum(1 for status in item["statuses"] if status == "caution")
        quality = item.get("execution_quality") or {}
        quality_score = safe_float(quality.get("score"), default=0)
        consistency_score = safe_float((item.get("consistency") or {}).get("score"), default=0)
        requires_extra_confirmation = item.get("setup_type") in {"leader_continuation", "breakout_follow"}
        item["priority_score"] = round(
            item["best_score"]
            + item["strategy_count"] * 4
            + item["approved_hits"] * 2
            + quality_score * 2
            + safe_float((item.get("consistency") or {}).get("score"), default=0) * 1.5,
            2,
        )

        if item["screening_status"] == "approved" and quality_score < 4:
            item["screening_status"] = "caution"
            item["screening_note"] = "执行质量不足，先观察"
        elif (
            item["screening_status"] == "approved"
            and requires_extra_confirmation
            and (item["approved_hits"] < 2 or quality_score < 6 or consistency_score < 4)
        ):
            item["screening_status"] = "caution"
            item["screening_note"] = "追涨型 setup 证据不够，先观察"

        if (
            item["screening_status"] == "approved"
            and item["approved_hits"] >= 2
            and item["best_score"] >= 88
            and quality_score >= 7
            and consistency_score >= 4
            and (not requires_extra_confirmation or item["strategy_count"] >= 3)
        ):
            item["tier"] = "A"
            item["tier_note"] = "可直接送 analyzer"
        elif item["screening_status"] == "approved" and quality_score >= 5 and consistency_score >= 2:
            item["tier"] = "B"
            item["tier_note"] = "通过二筛，但仍需盘中确认后再跟"
        else:
            item["tier"] = "C"
            item["tier_note"] = "仅观察，不建议直接执行"
        item["tier_rank"] = {"A": 3, "B": 2, "C": 1}[item["tier"]]
        entry_plan = dict(item.get("entry_plan") or {})
        if gate_status == "off":
            item["screening_status"] = "caution"
            item["screening_note"] = "风控阀门关闭，今天只观察不执行"
            item["tier"] = "C"
            item["tier_note"] = "风控阀门关闭，仅保留观察名单"
            entry_plan["sizing"] = "先不开新仓"
        elif gate_status == "limited":
            if (
                item["screening_status"] == "approved"
                and item.get("setup_type") in {"pullback_continuation", "low_reversal"}
                and quality_score >= 5
                and consistency_score >= 2
            ):
                item["tier"] = "B"
                item["tier_note"] = "阀门半开，仅允许轻仓确认"
                entry_plan["sizing"] = "0.3-0.5成以内"
            else:
                item["screening_status"] = "caution"
                item["screening_note"] = "阀门半开，当前票的执行质量还不够"
                item["tier"] = "C"
                item["tier_note"] = "仅观察，不建议直接执行"
                entry_plan["sizing"] = "先不开新仓"
        elif item["screening_status"] == "approved" and item["tier"] == "A":
            entry_plan["sizing"] = "0.5-0.8成试错"
        elif item["screening_status"] == "approved" and item["tier"] == "B":
            entry_plan["sizing"] = "0.3-0.5成试错"
        else:
            entry_plan["sizing"] = "先不开新仓"
        item["entry_plan"] = entry_plan
        item["execution_gate"] = {
            "status": gate_status,
            "label": execution_gate.get("label"),
            "summary": execution_gate.get("summary"),
            "position_cap": execution_gate.get("position_cap"),
        }
        item.pop("statuses", None)
        shortlist.append(item)

    shortlist.sort(
        key=lambda item: (
            STATUS_RANK.get(item["screening_status"], -1),
            item["tier_rank"],
            item["priority_score"],
            item["best_score"],
            item["amount_yi"],
        ),
        reverse=True,
    )

    shortlisted_codes = {item["code"] for item in shortlist}
    excluded_unique = sorted(code for code in excluded_only_codes if code not in shortlisted_codes)

    analyzer_candidates = []
    if execution_gate.get("allow_handoff"):
        for item in [x for x in shortlist if x.get("tier") in ("A", "B") and safe_float((x.get("execution_quality") or {}).get("score"), default=0) >= 6][:3]:
            analyzer_candidates.append(
                {
                    "code": item["code"],
                    "name": item["name"],
                    "best_score": item["best_score"],
                    "strategy_labels": item["strategy_labels"],
                    "reason": item["entry_reason"],
                    "watch_condition": item["watch_condition"],
                    "tier": item.get("tier"),
                    "consistency": item.get("consistency") or {},
                    "theme": (item.get("themes") or ["其他"])[0],
                    "main_risk": item.get("main_risk"),
                    "setup_label": item.get("setup_label"),
                    "execution_quality": item.get("execution_quality") or {},
                    "entry_plan": item.get("entry_plan") or {},
                }
            )

    summary = {
        "total_candidates": sum(len(items) for items in raw_strategies.values()),
        "unique_candidates": len(raw_codes),
        "shortlisted_count": len(shortlist),
        "approved_count": sum(1 for item in shortlist if item["screening_status"] == "approved"),
        "caution_count": sum(1 for item in shortlist if item["screening_status"] == "caution"),
        "excluded_count": len(excluded_unique),
        "tier_a_count": sum(1 for item in shortlist if item.get("tier") == "A"),
        "tier_b_count": sum(1 for item in shortlist if item.get("tier") == "B"),
        "tier_c_count": sum(1 for item in shortlist if item.get("tier") == "C"),
        "quality_high_count": sum(1 for item in shortlist if safe_float((item.get("execution_quality") or {}).get("score"), default=-999) >= 6),
        "quality_mid_count": sum(1 for item in shortlist if 3 <= safe_float((item.get("execution_quality") or {}).get("score"), default=-999) < 6),
        "quality_low_count": sum(1 for item in shortlist if safe_float((item.get("execution_quality") or {}).get("score"), default=-999) < 3),
        "execution_gate_status": gate_status,
    }

    return shortlist, analyzer_candidates, summary


def run_screening(scan_data):
    market_regime = dict(scan_data.get("market_regime") or {})
    market_regime["execution_gate"] = execution_gate_of(market_regime)
    market_regime["attack_ok"] = market_regime["execution_gate"].get("status") != "off"

    raw_strategies = normalize_strategies(scan_data)
    strategy_views = {
        strategy_name: summarize_strategy(
            strategy_name,
            stocks,
            market_regime=market_regime,
            market_themes=scan_data.get("market_themes"),
        )
        for strategy_name, stocks in raw_strategies.items()
    }

    shortlist, analyzer_candidates, screening_summary = aggregate_shortlist(
        strategy_views,
        raw_strategies,
        market_regime=market_regime,
    )

    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source_scan_timestamp": scan_data.get("timestamp"),
        "pool": scan_data.get("pool"),
        "pool_label": scan_data.get("pool_label"),
        "market_regime": market_regime,
        "market_themes": scan_data.get("market_themes"),
        "screening_rules_applied": SCREENING_RULES,
        "strategies": strategy_views,
        "shortlist": shortlist,
        "analyzer_candidates": analyzer_candidates,
        "screening_summary": screening_summary,
    }


def parse_args():
    parser = argparse.ArgumentParser(description="进攻型选股二次筛选")
    parser.add_argument("--input", default=str(DEFAULT_SCAN_PATH), help="scan.py 输出 JSON 路径")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="二次筛选结果输出路径")
    parser.add_argument("--stdout", action="store_true", help="同时把完整 JSON 打印到 stdout")
    return parser.parse_args()


def main():
    args = parse_args()
    input_path = Path(args.input).expanduser()
    output_path = Path(args.output).expanduser()

    with input_path.open("r", encoding="utf-8") as fh:
        scan_data = json.load(fh)

    result = run_screening(scan_data)
    upstream_manifests = []
    scan_manifest = load_sidecar_manifest(input_path)
    if scan_manifest:
        upstream_manifests.append(scan_manifest)
    ingress_manifest = build_pipeline_manifest(
        dataset="screening.batch",
        trade_date=result["timestamp"][:10],
        payload=result,
        upstream_manifests=upstream_manifests,
        ttl_seconds=900,
        required_dataset_groups=[{"screening.scan_result"}],
        fetched_at=result["timestamp"],
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    archive_dt = datetime.strptime(result["timestamp"], "%Y-%m-%d %H:%M:%S")
    archive_stamp = archive_dt.strftime("%Y-%m-%d_%H-%M-%S")
    archive_path = AI_HISTORY_DIR / f"ai_screening_{archive_stamp}.json"
    AI_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    result["data_ingress"] = ingress_summary(ingress_manifest, None)
    output_text = json.dumps(result, ensure_ascii=False, indent=2)
    output_path.write_text(output_text, encoding="utf-8")
    archive_path.write_text(output_text, encoding="utf-8")
    output_manifest_path = write_sidecar_manifest(output_path, ingress_manifest)
    write_sidecar_manifest(archive_path, ingress_manifest)
    result["data_ingress"] = ingress_summary(ingress_manifest, output_manifest_path)
    output_text = json.dumps(result, ensure_ascii=False, indent=2)
    output_path.write_text(output_text, encoding="utf-8")
    archive_path.write_text(output_text, encoding="utf-8")

    if args.stdout:
        print(output_text)
    else:
        summary = result["screening_summary"]
        print(
            "AI screening saved:",
            output_path,
            f"| shortlist={summary['shortlisted_count']}",
            f"approved={summary['approved_count']}",
            f"caution={summary['caution_count']}",
            f"| archive={archive_path}",
        )


if __name__ == "__main__":
    main()
