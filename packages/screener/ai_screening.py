#!/usr/bin/env python3
"""对进攻型选股扫描结果做二次筛选，并生成去重 shortlist。"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

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

        broad_score = safe_float(regime.get("score"), default=0)
        candidate_score = safe_float(candidate_view.get("score"), default=broad_score)
        positive_ratio = safe_float(metrics.get("positive_ratio"), default=0)
        avg_change = safe_float(metrics.get("avg_change_pct"), default=0)
        strong_ratio = safe_float(metrics.get("strong_ratio"), default=0)
        avg_turnover = safe_float(metrics.get("avg_turnover"), default=0)
        candidate_strong_ratio = safe_float(candidate_metrics.get("strong_ratio"), default=strong_ratio)

        risk_flags = []
        if positive_ratio < 0.50:
            risk_flags.append("赚钱效应不足")
        if avg_change < 0.20:
            risk_flags.append("平均涨幅偏弱")
        if strong_ratio < 0.10:
            risk_flags.append("强势股占比过低")
        if avg_turnover < 1.80:
            risk_flags.append("流动性一般")
        if candidate_score <= 4:
            risk_flags.append("候选强度不足")
        if candidate_strong_ratio < 0.18:
            risk_flags.append("候选强势扩散不足")

        if (
            broad_score <= 3
            or positive_ratio < 0.48
            or avg_change < 0
            or strong_ratio < 0.07
            or candidate_score <= 3
            or candidate_strong_ratio < 0.10
        ):
            gate = {
                "status": "off",
                "label": "进攻阀门关闭",
                "summary": "整体环境偏弱，今天进攻型策略只保留观察，不建议开新仓。",
                "position_cap": "0成",
                "allow_new_positions": False,
                "allow_handoff": False,
                "allowed_setups": [],
                "risk_flags": risk_flags[:4],
            }
        elif (
            broad_score <= 5
            or positive_ratio < 0.63
            or avg_change < 0.45
            or strong_ratio < 0.22
            or candidate_score <= 5
            or candidate_strong_ratio < 0.22
        ):
            gate = {
                "status": "limited",
                "label": "进攻阀门半开",
                "summary": "环境还不够顺，只允许更克制的轻仓试错，优先回踩接力和低位反转，不做强趋势追涨。",
                "position_cap": "0.3-0.5成以内",
                "allow_new_positions": True,
                "allow_handoff": False,
                "allowed_setups": ["pullback_continuation", "low_reversal"],
                "risk_flags": risk_flags[:4],
            }
        else:
            gate = {
                "status": "on",
                "label": "进攻阀门开启",
                "summary": "环境允许进攻，但只放行更高质量的共振票，仍以小仓位试错为主。",
                "position_cap": "0.5-0.8成试错",
                "allow_new_positions": True,
                "allow_handoff": True,
                "allowed_setups": ["leader_continuation", "breakout_follow", "pullback_continuation", "low_reversal"],
                "risk_flags": risk_flags[:4],
            }

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
    flow_today_yi = safe_float(capital_flow.get("today")) / 1e8
    flow_trend = capital_flow.get("trend") or "无数据"
    signals = stock.get("signals") or []
    consistency_score = safe_float((decision or {}).get("consistency_score"), default=0.0)

    trigger_price = pick_price(high20, price)
    pullback_price = pick_price(ma5, ma10, ma20, price)
    invalidate_price = pick_price(ma10, ma20, low20, price * 0.95 if price else None)
    recovery_price = pick_price(ma5, ma10, price)
    is_top_theme = theme != "其他" and theme in top_theme_names

    setup_type = "watch_only"
    setup_label = "观察等待"
    setup_summary = "信号还不够集中，先等更明确的承接或主线确认。"
    action = "先观察，不抢先手。"
    trigger = "等主力重新转强，或分时承接明显改善后再看。"
    avoid = "没有资金确认前不试。"
    invalidate = "题材走弱或个股转负就取消。"

    if (
        is_top_theme
        and change_pct >= 4.5
        and amount_yi >= 15
        and flow_today_yi > 0
        and attack_profile.get("status") == "keep"
    ):
        setup_type = "leader_continuation"
        setup_label = "热点龙头"
        setup_summary = "主线强票，优先看分时承接和二次上冲，不做情绪顶接力。"
        action = "只做分时回踩承接住后的二次进场。"
        trigger = (
            f"优先看 {fmt_price(pullback_price)} 一带承接，或再站稳 {fmt_price(trigger_price)} 后轻仓试错。"
            if pullback_price is not None or trigger_price is not None
            else "优先等回踩承接住，或二次放量上冲后再试。"
        )
        avoid = "高开超 3% 或连续直线拉升不追。"
        invalidate = (
            f"跌破 {fmt_price(invalidate_price)} 或主力转负就取消。"
            if invalidate_price is not None
            else "跌回强势结构下方或主力转负就取消。"
        )
    elif (
        pos20 <= 0.38
        and change_pct > 0
        and (
            flow_today_yi > 0
            or "转正" in flow_trend
            or any("低位反弹" in signal for signal in signals)
        )
    ):
        setup_type = "low_reversal"
        setup_label = "低位反转"
        setup_summary = "位置偏低，优先看二次确认，不抢第一根情绪脉冲。"
        action = "只做二次确认，不抢第一根。"
        trigger = (
            f"站回 {fmt_price(recovery_price)} 上方且资金不转负，再考虑试错。"
            if recovery_price is not None
            else "站回短线均线并保持资金不转负，再考虑试错。"
        )
        avoid = "第一波直线拉升不追。"
        invalidate = (
            f"跌破 {fmt_price(invalidate_price)} 或再次放量走弱就取消。"
            if invalidate_price is not None
            else "跌回低位区或再次放量走弱就取消。"
        )
    elif pos20 >= 0.72 and flow_today_yi > 0 and attack_profile.get("status") == "keep":
        setup_type = "breakout_follow"
        setup_label = "突破跟随"
        setup_summary = "趋势票优先看放量站稳后的跟随，不追脱离支撑过远的阳线。"
        action = "等放量站稳后再跟，不追已经拉开的阳线。"
        trigger = (
            f"放量站稳 {fmt_price(trigger_price)} 上方再试，若回踩 {fmt_price(pullback_price)} 不破可候补。"
            if trigger_price is not None or pullback_price is not None
            else "放量站稳强势区后再试，回踩不破再候补。"
        )
        avoid = "高开高走但量能跟不上时不追。"
        invalidate = (
            f"跌回 {fmt_price(invalidate_price)} 下方或主力转负就取消。"
            if invalidate_price is not None
            else "跌回强势结构下方或主力转负就取消。"
        )
    elif pos20 >= 0.45 and (flow_today_yi > 0 or "流入" in flow_trend or "转正" in flow_trend):
        setup_type = "pullback_continuation"
        setup_label = "回踩接力"
        setup_summary = "趋势未坏但不适合追涨，优先看回踩承接后的接力点。"
        action = "优先等回踩承接，不追已经发散的阳线。"
        trigger = (
            f"回踩 {fmt_price(pullback_price)} 一带不破，且资金继续为正，再考虑进场。"
            if pullback_price is not None
            else "回踩关键均线不破，且资金继续为正，再考虑进场。"
        )
        avoid = "脱离支撑过远时不追。"
        invalidate = (
            f"跌破 {fmt_price(invalidate_price)} 或主题明显转弱就取消。"
            if invalidate_price is not None
            else "跌破关键支撑或主题明显转弱就取消。"
        )

    if overheat_penalty >= 4 and setup_type in {"leader_continuation", "breakout_follow"}:
        avoid = "情绪偏热，第一波拉高不追，优先等换手后的二次机会。"
    if consistency_score <= 0 and setup_type != "watch_only":
        setup_summary += " 当前一致性一般，执行上要更保守。"

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
    flow_today_yi = safe_float(capital_flow.get("today")) / 1e8
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

    score = 0
    positives = []
    warnings = []

    if amount_yi >= 12:
        score += 2
        positives.append("成交额厚")
    elif amount_yi >= 8:
        score += 1
        positives.append("流动性够用")
    else:
        score -= 1
        warnings.append("成交额偏薄")

    if stock.get("has_capital_flow", True):
        if flow_today_yi >= 3:
            score += 2
            positives.append("资金确认强")
        elif flow_today_yi > 0 or "转正" in flow_trend:
            score += 1
            positives.append("资金有承接")
        else:
            score -= 1
            warnings.append("资金确认不足")
    else:
        score -= 1
        warnings.append("资金数据缺失")

    if consistency_score >= 5:
        score += 2
        positives.append("一致性高")
    elif consistency_score >= 2:
        score += 1
        positives.append("一致性尚可")
    else:
        score -= 1
        warnings.append("一致性偏弱")

    if setup_type in {"pullback_continuation", "low_reversal"}:
        score += 2
        positives.append("位置更友好")
    elif setup_type in {"leader_continuation", "breakout_follow"}:
        positives.append("趋势 setup")
    else:
        score -= 1
        warnings.append("缺少明确执行位")

    if theme != "其他" and theme in top_theme_names:
        score += 1
        positives.append("主线题材")

    if persistence_label in {"持续增强", "强势延续"}:
        score += 1
        positives.append("主题延续")
    elif persistence_label in {"热度衰减", "一日游风险"}:
        score -= 1
        warnings.append("主题持续性弱")

    if overheat_penalty >= 6:
        score -= 3
        warnings.append("短线过热")
    elif overheat_penalty >= 4:
        score -= 2
        warnings.append("情绪偏热")

    if setup_type in {"leader_continuation", "breakout_follow"}:
        if change_pct >= 7.5:
            score -= 2
            warnings.append("追涨距离过大")
        elif change_pct >= 5.5:
            score -= 1
            warnings.append("接近追涨区")

    if any("量价顶背离" in signal or "资金背离" in signal for signal in signals):
        score -= 2
        warnings.append("量价背离")

    if notice_risk_tags:
        score -= 2
        warnings.append("公告风险待消化")

    if gate_status == "off":
        score -= 3
        warnings.append("阀门关闭")
    elif gate_status == "limited" and setup_type in {"leader_continuation", "breakout_follow"}:
        score -= 2
        warnings.append("半开环境不支持追强")

    label = "高执行质量" if score >= 6 else ("中执行质量" if score >= 3 else "低执行质量")
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
    flow_today_yi = safe_float(capital_flow.get("today")) / 1e8
    flow_trend = capital_flow.get("trend") or "无数据"
    attack_status = attack_profile.get("status") or "keep"
    overheat_penalty = safe_float(stock.get("overheat_penalty"))
    has_capital_flow = stock.get("has_capital_flow", True)
    change_pct = safe_float(stock.get("change_pct"))
    signals = stock.get("signals") or []
    notice_risk_tags = stock.get("notice_risk_tags") or []

    hard_reasons = []
    caution_reasons = []
    positives = []
    consistency = 0
    consistency_notes = []

    if amount_yi < 4:
        hard_reasons.append("成交额不足 4 亿，流动性偏弱")
    elif amount_yi >= 8:
        positives.append("成交额充足")
        consistency += 1
        consistency_notes.append("流动性支持")

    if attack_status == "exclude":
        hard_reasons.append("底层进攻标签已判定不匹配")
    elif attack_status == "downgrade":
        caution_reasons.append("进攻纯度一般，先降级观察")
    else:
        consistency += 2
        consistency_notes.append("进攻风格匹配")

    if pe >= 95 and roe is not None and roe < 5:
        hard_reasons.append("高估值且盈利弱，性价比不足")
    elif pe >= 100 and roe is None:
        caution_reasons.append("估值过热，等待业绩验证")
    elif pe <= 0:
        caution_reasons.append("业绩仍未修复，先观察")
    elif pe >= 75 and roe is not None and roe < 8:
        caution_reasons.append("估值偏高，业绩兑现压力较大")

    if not has_capital_flow:
        caution_reasons.append("资金数据缺失，确认度不高")
    elif flow_today_yi > 0:
        positives.append("主力资金仍为净流入")
        consistency += 2
        consistency_notes.append("资金同向")
    elif "转正" in flow_trend:
        positives.append("资金开始修复")
        consistency += 1
        consistency_notes.append("资金修复")
    else:
        caution_reasons.append("资金延续性待确认")
        consistency -= 2

    if overheat_penalty >= 6:
        caution_reasons.append("情绪过热，提防次日冲高回落")
        consistency -= 2
    elif overheat_penalty >= 4:
        caution_reasons.append("短线偏热，提防冲高回落")
        consistency -= 1

    if any("量价顶背离" in s or "资金背离" in s for s in signals):
        caution_reasons.append("量价/资金背离，信号质量下降")
        consistency -= 3

    if notice_risk_tags:
        labels = sorted({item.get("label") for item in notice_risk_tags if item.get("label")})
        if labels:
            caution_reasons.append("公告风险：" + "/".join(labels))
            consistency -= 2
            if any(label in labels for label in ["减持", "诉讼", "处罚", "业绩预警", "董监高变动"]):
                caution_reasons.append("公告存在明确风险事件，限制直接推荐")
                consistency -= 1

    if change_pct >= 9.8:
        caution_reasons.append("接近或已触及涨停，次日分歧风险高")
        consistency -= 1

    if theme != "其他" and theme in top_theme_names:
        consistency += 1
        consistency_notes.append("主线主题加成")

    persistence_label = theme_persistence.get("label") or ""
    persistence_score = safe_float(theme_persistence.get("score"), default=0)
    if persistence_label == "持续增强":
        consistency += 2
        consistency_notes.append("主题持续增强")
    elif persistence_label == "强势延续":
        consistency += 1
        consistency_notes.append("主题强势延续")
    elif persistence_label == "延续但分化":
        consistency += 0
        consistency_notes.append("主题延续但分化")
    elif persistence_label == "热度衰减":
        consistency -= 1
        consistency_notes.append("主题热度衰减")
    elif persistence_label == "一日游风险":
        consistency -= 2
        consistency_notes.append("主题一日游风险")

    if persistence_score >= 16 and change_pct >= 5:
        positives.append("主题与价格共振")
    elif persistence_score <= 5 and change_pct >= 5:
        caution_reasons.append("主题持续性不足，高位信号需折价")
        consistency -= 1

    if pe > 0 and pe <= 50 and (roe is None or roe >= 5):
        consistency += 1
        consistency_notes.append("估值盈利匹配尚可")
    elif pe >= 80 and (roe is None or roe < 8):
        consistency -= 2
        consistency_notes.append("估值与盈利错配")

    regime_score = safe_float((market_regime or {}).get("score"), default=0.0)
    execution_gate = execution_gate_of(market_regime)
    gate_status = execution_gate.get("status")
    if gate_status == "off":
        caution_reasons.append("风控阀门关闭，今天只观察不执行")
        consistency -= 3
    elif gate_status == "limited":
        caution_reasons.append("风控阀门半开，只允许轻仓试错")
        consistency -= 1
        if change_pct >= 5 or overheat_penalty >= 3:
            caution_reasons.append("当前环境不适合追强，优先等回踩确认")
            consistency -= 1
    elif regime_score < 6 and change_pct >= 7:
        caution_reasons.append("环境未到强进攻，高位强拉需谨慎")
        consistency -= 1

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

    consistency_label = "高一致性" if consistency >= 4 else ("中一致性" if consistency >= 1 else "低一致性")
    if consistency <= -2 and status == "approved":
        status = "caution"
        reason = "信号一致性偏弱，先观察"
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
        "entry_reason": trade_note.get("entry_reason") or attack_profile.get("reason") or "量价结构满足策略要求",
        "main_risk": trade_note.get("main_risk") or decision["reason"],
        "watch_condition": trade_note.get("watch_condition") or "观察次日资金和量能是否继续配合",
        "capital_flow": {
            "trend": decision["capital_trend"],
            "today_yi": decision["flow_today_yi"],
            "five_day_total_yi": round(safe_float(capital_flow.get("5day_total")) / 1e8, 2),
        },
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
    output_text = json.dumps(result, ensure_ascii=False, indent=2)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output_text, encoding="utf-8")

    archive_dt = datetime.strptime(result["timestamp"], "%Y-%m-%d %H:%M:%S")
    archive_stamp = archive_dt.strftime("%Y-%m-%d_%H-%M-%S")
    archive_path = AI_HISTORY_DIR / f"ai_screening_{archive_stamp}.json"
    AI_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
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
