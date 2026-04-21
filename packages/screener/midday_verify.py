#!/usr/bin/env python3
"""午盘二次确认：验证早盘 shortlist 在盘中是否维持强势。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
DEFAULT_MORNING = BASE / "data" / "ai_screening_result.json"
DEFAULT_SCAN = BASE / "data" / "scan_result.json"
DEFAULT_OUTPUT = BASE / "data" / "midday_verification_result.json"


def safe_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def unique_keep_order(values):
    seen = set()
    result = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def normalize_theme_name(value):
    text = (value or "").strip()
    if text in {"", "其他", "其它"}:
        return ""
    return text


def theme_of(item):
    if not item:
        return ""
    theme = normalize_theme_name(item.get("theme"))
    if theme:
        return theme
    themes = item.get("themes") or []
    if isinstance(themes, list) and themes:
        return normalize_theme_name(themes[0])
    return ""


def top_theme_names(scan_data, limit=2):
    themes = (((scan_data or {}).get("market_themes") or {}).get("themes") or [])[:limit]
    result = []
    for item in themes:
        theme = normalize_theme_name(item.get("theme"))
        if theme:
            result.append(theme)
    return result


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def parse_timestamp(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None


def validate_inputs(morning, current):
    errors = []
    morning_ts = parse_timestamp(morning.get("timestamp"))
    morning_scan_ts = parse_timestamp(morning.get("source_scan_timestamp"))
    current_ts = parse_timestamp(current.get("timestamp"))

    if not morning_ts:
        errors.append("晨间 shortlist 缺少有效 timestamp")
    if not current_ts:
        errors.append("当前 scan 缺少有效 timestamp")

    if morning_ts and current_ts and morning_ts.date() != current_ts.date():
        errors.append(
            "晨间 shortlist 与当前 scan 不是同一天："
            f"{morning_ts.strftime('%Y-%m-%d')} vs {current_ts.strftime('%Y-%m-%d')}"
        )

    if morning_scan_ts and current_ts and morning_scan_ts.date() != current_ts.date():
        errors.append(
            "晨间 source_scan_timestamp 与当前 scan 不是同一天："
            f"{morning_scan_ts.strftime('%Y-%m-%d')} vs {current_ts.strftime('%Y-%m-%d')}"
        )

    if morning_scan_ts and current_ts and current_ts < morning_scan_ts:
        errors.append(
            "当前 scan 时间早于晨间 source_scan_timestamp，疑似传错文件："
            f"{current_ts.strftime('%Y-%m-%d %H:%M:%S')} < {morning_scan_ts.strftime('%Y-%m-%d %H:%M:%S')}"
        )

    return errors


def build_scan_index(scan_data):
    index = {}
    for item in scan_data.get("verification_universe") or []:
        code = item.get("code")
        if code and code not in index:
            index[code] = item
    strategies = scan_data.get("strategies") or {}
    for _, items in strategies.items():
        for item in items:
            code = item.get("code")
            if code and code not in index:
                index[code] = item
    for item in scan_data.get("candidates") or []:
        code = item.get("code")
        if code and code not in index:
            index[code] = item
    return index


def iter_scan_candidates(scan_data):
    best = {}
    for item in scan_data.get("verification_universe") or []:
        code = item.get("code")
        if not code:
            continue
        current_score = safe_float(item.get("score"), default=-999)
        existing = best.get(code)
        if not existing or current_score > safe_float(existing.get("score"), default=-999):
            best[code] = item
    strategies = scan_data.get("strategies") or {}
    for _, items in strategies.items():
        for item in items:
            code = item.get("code")
            if not code:
                continue
            current_score = safe_float(item.get("score"), default=-999)
            existing = best.get(code)
            if not existing or current_score > safe_float(existing.get("score"), default=-999):
                best[code] = item
    return list(best.values())


def infer_scan_setup_label(item):
    reason = (((item or {}).get("trade_note") or {}).get("entry_reason") or "").strip()
    if "低位" in reason and "反" in reason:
        return "低位反转"
    if "回踩" in reason:
        return "回踩接力"
    if "突破" in reason:
        return "突破跟随"
    if "龙头" in reason:
        return "热点龙头"
    return "盘中新机会"


def build_fresh_candidates(scan_data, exclude_codes, active_themes=None, limit=3):
    active_themes = active_themes or []
    candidates = []
    for item in iter_scan_candidates(scan_data):
        code = item.get("code")
        if not code or code in exclude_codes:
            continue

        score = safe_float(item.get("score"), default=-999)
        change_pct = safe_float(item.get("change_pct"), default=-999)
        amount_yi = safe_float(item.get("amount_yi"), default=0)
        if change_pct <= 0 or amount_yi < 5:
            continue

        theme = theme_of(item)
        trade_note = item.get("trade_note") or {}
        capital_flow = item.get("capital_flow") or {}
        technical_state = item.get("technical_state") or {}
        candidates.append(
            {
                "code": code,
                "name": item.get("name"),
                "theme": theme or "其他",
                "score": score,
                "change_pct": change_pct,
                "amount_yi": amount_yi,
                "capital_trend": capital_flow.get("trend") or "资金未确认",
                "flow_today_yi": round(safe_float(capital_flow.get("today")) / 1e8, 2),
                "entry_reason": trade_note.get("entry_reason") or "盘中强度较高",
                "main_risk": trade_note.get("main_risk") or "先看二次确认，不追第一波",
                "watch_condition": trade_note.get("watch_condition") or "先等换手和承接确认",
                "setup_label": infer_scan_setup_label(item),
                "high20": technical_state.get("high20"),
                "ma5": technical_state.get("ma5"),
                "ma10": technical_state.get("ma10"),
                "active_theme": theme in active_themes if theme else False,
            }
        )

    candidates.sort(
        key=lambda item: (
            1 if item.get("active_theme") else 0,
            safe_float(item.get("score"), default=-999),
            safe_float(item.get("change_pct"), default=-999),
            safe_float(item.get("amount_yi"), default=0),
        ),
        reverse=True,
    )
    return candidates[:limit]


def verify_item(morning_item, current_item, active_themes=None):
    hard_reasons = []
    soft_reasons = []
    positives = []
    active_themes = active_themes or []

    if not current_item:
        return {
            "status": "downgraded",
            "reason": "已掉出本轮候选池，午后强度不再领先",
            "details": ["盘中未进入本轮领先候选，视为午后承接不足"],
        }

    morning_score = safe_float(morning_item.get("best_score", morning_item.get("score")), default=None)
    morning_change_pct = safe_float(morning_item.get("change_pct"), default=None)
    morning_theme = theme_of(morning_item)
    morning_setup_type = morning_item.get("setup_type") or "generic"
    morning_setup_label = morning_item.get("setup_label") or ""
    entry_plan = morning_item.get("entry_plan") or {}
    levels = entry_plan.get("levels") or {}

    chg = safe_float(current_item.get("change_pct"))
    amount = safe_float(current_item.get("amount_yi"))
    score = safe_float(current_item.get("score"))
    price = safe_float(current_item.get("price"), default=None)
    cap = current_item.get("capital_flow") or {}
    trend = cap.get("trend") or "无数据"
    today_flow = safe_float(cap.get("today")) / 1e8
    current_theme = theme_of(current_item)
    tech = current_item.get("technical_state") or {}
    ma5 = safe_float(tech.get("ma5"), default=None)
    ma10 = safe_float(tech.get("ma10"), default=None)
    ma20 = safe_float(tech.get("ma20"), default=None)
    trigger_level = safe_float(levels.get("trigger"), default=None)
    pullback_level = safe_float(levels.get("pullback"), default=None)
    invalidate_level = safe_float(levels.get("invalidate"), default=None)

    score_delta = round(score - morning_score, 2) if morning_score is not None else None
    change_delta = round(chg - morning_change_pct, 2) if morning_change_pct is not None else None
    theme_in_play = bool(morning_theme and morning_theme in active_themes)

    if chg < 0:
        hard_reasons.append("盘中转负，强势失败")
    elif chg < 1:
        soft_reasons.append("涨幅收敛，承接一般")
    else:
        positives.append("涨幅仍保持为正")

    if today_flow <= 0 and "转正" not in trend:
        hard_reasons.append("主力资金未延续")
    elif today_flow > 0:
        positives.append("主力资金仍在配合")
    else:
        soft_reasons.append("资金仅弱修复，力度一般")

    if amount < 5:
        soft_reasons.append("成交额一般，确认度不足")
    else:
        positives.append("成交额仍在可执行区间")

    if score < 70:
        hard_reasons.append("盘中综合得分掉到 70 以下")
    elif score_delta is not None and score_delta <= -12:
        hard_reasons.append(f"较晨间大幅走弱（分数 {score_delta:+.2f}）")
    elif score_delta is not None and score_delta <= -6:
        soft_reasons.append(f"较晨间转弱（分数 {score_delta:+.2f}）")
    elif score_delta is not None and score_delta >= 0:
        positives.append(f"较晨间维持或改善（分数 {score_delta:+.2f}）")

    if invalidate_level is not None and price is not None and price <= invalidate_level:
        hard_reasons.append(f"跌破晨间取消位 {invalidate_level:.2f}")
    elif pullback_level is not None and price is not None and price < pullback_level:
        soft_reasons.append(f"跌回晨间承接位下方 {pullback_level:.2f}")

    if morning_setup_type in {"leader_continuation", "breakout_follow"}:
        if trigger_level is not None and price is not None and price >= trigger_level:
            positives.append("突破位仍保持有效")
        elif trigger_level is not None and price is not None and price < trigger_level:
            soft_reasons.append(f"尚未重新站稳突破位 {trigger_level:.2f}")

        if ma10 is not None and price is not None and price < ma10:
            hard_reasons.append(f"跌回 MA10 下方（{ma10:.2f}）")
        elif ma5 is not None and price is not None and price < ma5:
            soft_reasons.append(f"短线承接回落到 MA5 下方（{ma5:.2f}）")
    elif morning_setup_type == "pullback_continuation":
        if ma20 is not None and price is not None and price < ma20:
            hard_reasons.append(f"回踩接力结构破坏，跌回 MA20 下方（{ma20:.2f}）")
        elif ma10 is not None and price is not None and price < ma10:
            soft_reasons.append(f"回踩力度偏大，已落到 MA10 下方（{ma10:.2f}）")
        else:
            positives.append("回踩结构仍在")
    elif morning_setup_type == "low_reversal":
        if ma20 is not None and price is not None and price < ma20 and score_delta is not None and score_delta < 0:
            hard_reasons.append("低位反转结构未进一步确认")
        elif ma5 is not None and price is not None and price >= ma5:
            positives.append("短线反转结构仍在")

    if morning_theme:
        if theme_in_play:
            positives.append(f"主题仍在主线内（{morning_theme}）")
        else:
            if morning_setup_type == "leader_continuation":
                hard_reasons.append(f"晨间主题 {morning_theme} 已退出主线")
            else:
                soft_reasons.append(f"晨间主题 {morning_theme} 热度回落")

    if current_theme and morning_theme and current_theme != morning_theme:
        soft_reasons.append(f"题材识别发生变化：{morning_theme} -> {current_theme}")

    soft_reasons = unique_keep_order(soft_reasons)
    hard_reasons = unique_keep_order(hard_reasons)
    positives = unique_keep_order(positives)

    passed = not hard_reasons
    if passed:
        if morning_setup_type in {"leader_continuation", "breakout_follow"} and len(soft_reasons) >= 2:
            passed = False
        elif len(soft_reasons) >= 3:
            passed = False

    confirmation_label = "承接良好" if passed and not soft_reasons else ("承接一般" if passed else "承接失效")

    detail_lines = []
    detail_lines.extend(hard_reasons)
    detail_lines.extend(soft_reasons)
    if not detail_lines:
        detail_lines = positives or ["涨幅、资金、结构均维持强势"]

    reason = (
        hard_reasons[0]
        if hard_reasons
        else (soft_reasons[0] if not passed and soft_reasons else (positives[0] if positives else "盘中承接仍在"))
    )

    return {
        "status": "confirmed" if passed else "downgraded",
        "reason": reason,
        "details": detail_lines,
        "snapshot": {
            "setup_type": morning_setup_type,
            "setup_label": morning_setup_label,
            "price": price,
            "change_pct": chg,
            "change_delta": change_delta,
            "amount_yi": amount,
            "score": score,
            "score_delta": score_delta,
            "capital_trend": trend,
            "flow_today_yi": round(today_flow, 2),
            "morning_theme": morning_theme,
            "current_theme": current_theme,
            "theme_in_play": theme_in_play,
            "active_themes": active_themes[:2],
            "pullback_level": pullback_level,
            "trigger_level": trigger_level,
            "invalidate_level": invalidate_level,
            "ma5": ma5,
            "ma10": ma10,
            "ma20": ma20,
            "confirmation_label": confirmation_label,
            "positives": positives[:3],
        },
    }


def main():
    parser = argparse.ArgumentParser(description="午盘二次确认")
    parser.add_argument("--morning", default=str(DEFAULT_MORNING))
    parser.add_argument("--scan", default=str(DEFAULT_SCAN))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    morning = load_json(Path(args.morning).expanduser())
    current = load_json(Path(args.scan).expanduser())
    validation_errors = validate_inputs(morning, current)

    if validation_errors:
        output = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "validation_status": "invalid",
            "validation_errors": validation_errors,
            "source_morning_timestamp": morning.get("timestamp", ""),
            "source_scan_timestamp": morning.get("source_scan_timestamp", ""),
            "verified_against_scan_timestamp": current.get("timestamp", ""),
            "target_codes": [],
            "confirmed": [],
            "downgraded": [],
            "fresh_candidates": [],
            "items": [],
        }
        out_path = Path(args.output).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        for item in validation_errors:
            print(f"ERROR: {item}", file=sys.stderr)
        print(f"Midday verification rejected: {out_path}", file=sys.stderr)
        sys.exit(1)

    scan_index = build_scan_index(current)

    shortlist = morning.get("shortlist") or []
    targets = [item for item in shortlist if item.get("tier") in ("A", "B")][:8]

    active_themes = top_theme_names(current, limit=2)
    result_items = []
    for item in targets:
        code = item.get("code")
        result = verify_item(item, scan_index.get(code), active_themes=active_themes)
        result_items.append({
            "code": code,
            "name": item.get("name"),
            "tier": item.get("tier"),
            "morning_score": item.get("best_score"),
            **result,
        })

    output = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "validation_status": "ok",
        "validation_errors": [],
        "source_morning_timestamp": morning.get("timestamp", ""),
        "source_scan_timestamp": morning.get("source_scan_timestamp", ""),
        "verified_against_scan_timestamp": current.get("timestamp", ""),
        "target_codes": [item.get("code") for item in targets if item.get("code")],
        "confirmed": [x for x in result_items if x["status"] == "confirmed"],
        "downgraded": [x for x in result_items if x["status"] == "downgraded"],
        "fresh_candidates": build_fresh_candidates(
            current,
            exclude_codes={item.get("code") for item in targets if item.get("code")},
            active_themes=active_themes,
            limit=3,
        ),
        "items": result_items,
    }

    out_path = Path(args.output).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Midday verification saved: {out_path} | confirmed={len(output['confirmed'])} downgraded={len(output['downgraded'])}")


if __name__ == "__main__":
    main()
