#!/usr/bin/env python3
"""
candidate_lifecycle.py — 候选生命周期管理 v1

比较当前 ai_screening_result.json / 最近扫描快照 vs 历史快照 + midday_verification，
识别 entered / upgraded / downgraded / exited / handed_off，输出 JSON + Markdown 报告。

用法:
    python3 candidate_lifecycle.py [--days-back 3] [--ai-input PATH] [--midday-input PATH] [--history-dir PATH] [--output-dir PATH]
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Optional

try:
    from screener.exit_return_tracker import record_exit
except ModuleNotFoundError:
    from exit_return_tracker import record_exit

try:
    from screener.stage_contract import validate_stage_output
except ModuleNotFoundError:
    from stage_contract import validate_stage_output

# ── tier ordering (higher = better) ──
TIER_ORDER = {"A": 3, "B": 2, "C": 1, "D": 0}
STATUS_ORDER = {"approved": 3, "caution": 2, "excluded": 1}
V2_ACTION_ORDER = {"observe": 0, "review": 1, "shadow": 2, "trial": 3, "actionable": 4}
V2_RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


def parse_args():
    p = argparse.ArgumentParser(description="候选生命周期管理 v1")
    p.add_argument("--days-back", type=int, default=3, help="回溯天数（默认3）")
    p.add_argument("--ai-input", default=None, help="当前 ai_screening_result.json 路径")
    p.add_argument("--midday-input", default=None, help="midday_verification_result.json 路径")
    p.add_argument("--history-dir", default=None, help="raw scan history 快照目录")
    p.add_argument("--ai-history-dir", default=None, help="ai_screening 归档目录")
    p.add_argument("--output-dir", default=None, help="输出目录")
    p.add_argument("--output-json", default=None, help="显式指定 lifecycle JSON 输出路径")
    p.add_argument("--output-md", default=None, help="显式指定 lifecycle Markdown 输出路径")
    p.add_argument("--report-output", default=None, help="显式指定 reports 下 Markdown 输出路径")
    return p.parse_args()


def load_json(path: str) -> Optional[dict]:
    if not path or not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_timestamp(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _factor_fields_from_item(item: dict) -> dict:
    factors = item.get("tushare_factors") or {}
    return {
        "tushare_score": factors.get("tushare_score"),
        "data_completeness": factors.get("data_completeness"),
        "factor_tags": factors.get("factor_tags") or [],
        "risk_flags": factors.get("risk_flags") or [],
        "risk_level": item.get("risk_level") or factors.get("risk_level") or "info",
        "risk_items": item.get("risk_items") or factors.get("risk_items") or [],
        "degrade_reason": item.get("degrade_reason") or factors.get("degrade_reason") or "",
        "block_reason": item.get("block_reason") or factors.get("block_reason") or "",
        "risk_evidence_refs": item.get("risk_evidence_refs") or factors.get("risk_evidence_refs") or [],
        "tushare_score_breakdown": factors.get("tushare_score_breakdown") or {},
        "factor_snapshot": factors.get("factor_snapshot") or {},
        "trade_date_used": factors.get("trade_date_used"),
        "risk_level": factors.get("risk_level"),
        "degrade_reason": factors.get("degrade_reason"),
        "tushare_positive_adjustment": item.get("tushare_positive_adjustment"),
        "tushare_risk_penalty": item.get("tushare_risk_penalty"),
        "tushare_priority_adjustment": item.get("tushare_priority_adjustment"),
    }


def _factor_snapshot_for_event(item: dict) -> dict:
    return {
        "tushare_score": item.get("tushare_score"),
        "data_completeness": item.get("data_completeness"),
        "factor_tags": item.get("factor_tags") or [],
        "risk_flags": item.get("risk_flags") or [],
        "risk_level": item.get("risk_level") or "info",
        "risk_items": item.get("risk_items") or [],
        "degrade_reason": item.get("degrade_reason") or "",
        "block_reason": item.get("block_reason") or "",
        "risk_evidence_refs": item.get("risk_evidence_refs") or [],
        "tushare_score_breakdown": item.get("tushare_score_breakdown") or {},
        "factor_snapshot": item.get("factor_snapshot") or {},
        "trade_date_used": item.get("trade_date_used"),
        "risk_level": item.get("risk_level"),
        "degrade_reason": item.get("degrade_reason"),
        "tushare_positive_adjustment": item.get("tushare_positive_adjustment"),
        "tushare_risk_penalty": item.get("tushare_risk_penalty"),
        "tushare_priority_adjustment": item.get("tushare_priority_adjustment"),
    }


def _v2_value(judgment: dict, *keys: str, default=""):
    value = judgment
    for key in keys:
        if not isinstance(value, dict):
            return default
        value = value.get(key)
    return value if value not in (None, "", [], {}) else default


def _opportunity_v2_fields_from_item(item: dict) -> dict:
    judgment = item.get("opportunity_v2") if isinstance(item.get("opportunity_v2"), dict) else {}
    hard_gate = judgment.get("hard_gate") if isinstance(judgment.get("hard_gate"), dict) else {}
    block_reasons = hard_gate.get("block_reasons") if isinstance(hard_gate.get("block_reasons"), list) else []
    missing = item.get("missing_confirmation") or judgment.get("missing_confirmation") or []
    return {
        "suggested_action": item.get("suggested_action") or judgment.get("suggested_action") or "",
        "suggested_action_label": item.get("suggested_action_label") or judgment.get("action_label") or "",
        "desired_action": judgment.get("desired_action") or "",
        "confidence": item.get("confidence") if item.get("confidence") is not None else judgment.get("confidence"),
        "thesis": item.get("thesis") or judgment.get("thesis") or "",
        "why_now": item.get("why_now") or judgment.get("why_now") or "",
        "invalidation": item.get("invalidation") or judgment.get("invalidation") or "",
        "upgrade_reason": judgment.get("upgrade_reason") or "",
        "missing_confirmation": missing if isinstance(missing, list) else [missing],
        "hard_gate_max_action": item.get("hard_gate_max_action") or hard_gate.get("maximum_allowed_action") or "",
        "hard_gate_block_reason": item.get("hard_gate_block_reason") or "; ".join(str(reason) for reason in block_reasons if reason),
        "market_phase": _v2_value(judgment, "market_phase", "value"),
        "market_phase_label": _v2_value(judgment, "market_phase", "label"),
        "theme_phase": _v2_value(judgment, "theme_phase", "value"),
        "theme_phase_label": _v2_value(judgment, "theme_phase", "label"),
        "stock_role": _v2_value(judgment, "stock_role", "value"),
        "stock_role_label": _v2_value(judgment, "stock_role", "label"),
        "opportunity_type": judgment.get("opportunity_type") or _v2_value(judgment, "playbook", "opportunity_type"),
        "playbook_label": _v2_value(judgment, "playbook", "label"),
        "crowding_risk_level": _v2_value(judgment, "crowding_risk", "level"),
        "fake_breakout_risk_level": _v2_value(judgment, "fake_breakout_risk", "level"),
        "opportunity_v2": judgment,
    }


def _opportunity_snapshot_for_event(item: dict) -> dict:
    fields = _opportunity_v2_fields_from_item(item)
    return {
        key: fields.get(key)
        for key in (
            "suggested_action",
            "suggested_action_label",
            "desired_action",
            "confidence",
            "thesis",
            "why_now",
            "invalidation",
            "upgrade_reason",
            "missing_confirmation",
            "hard_gate_max_action",
            "hard_gate_block_reason",
            "market_phase",
            "market_phase_label",
            "theme_phase",
            "theme_phase_label",
            "stock_role",
            "stock_role_label",
            "opportunity_type",
            "playbook_label",
            "crowding_risk_level",
            "fake_breakout_risk_level",
        )
    }


def _v2_rank(item: dict) -> int:
    return V2_ACTION_ORDER.get(str(item.get("suggested_action") or ""), 0)


def _v2_confidence(item: dict) -> float:
    value = item.get("confidence")
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _v2_missing_count(item: dict) -> int:
    missing = item.get("missing_confirmation") or []
    return len(missing) if isinstance(missing, list) else (1 if missing else 0)


def _v2_risk_score(item: dict) -> int:
    return max(
        V2_RISK_ORDER.get(str(item.get("crowding_risk_level") or ""), 0),
        V2_RISK_ORDER.get(str(item.get("fake_breakout_risk_level") or ""), 0),
    )


def _v2_change_reason(curr: dict, prev: dict, score_delta: float) -> tuple[str, str, list[str]]:
    """Return (direction, reason, notes) using V2 semantics.

    direction is ``upgrade``, ``downgrade`` or ``continue``. Old score/tier
    movements are only a fallback when neither side carries V2 fields.
    """

    has_v2 = bool(curr.get("suggested_action") or prev.get("suggested_action") or curr.get("thesis") or prev.get("thesis"))
    if not has_v2:
        curr_tier = TIER_ORDER.get(curr.get("tier", ""), 0)
        prev_tier = TIER_ORDER.get(prev.get("tier", ""), 0)
        curr_status = STATUS_ORDER.get(curr.get("screening_status", ""), 0)
        prev_status = STATUS_ORDER.get(prev.get("screening_status", ""), 0)
        if curr_tier > prev_tier or curr_status > prev_status:
            return "upgrade", "旧层级/状态改善；当前无 V2 结构字段，按旧规则回退", []
        if curr_tier < prev_tier or curr_status < prev_status:
            return "downgrade", "旧层级/状态回落；当前无 V2 结构字段，按旧规则回退", []
        if score_delta >= 15:
            return "upgrade", f"旧评分显著改善（{score_delta:+.2f}）", []
        if score_delta <= -15:
            return "downgrade", f"旧评分显著回落（{score_delta:+.2f}）", []
        return "continue", "连续两轮仍在候选池，先按延续观察处理", []

    notes: list[str] = []
    upgrade_points = 0
    downgrade_points = 0
    action_delta = _v2_rank(curr) - _v2_rank(prev)
    if action_delta > 0:
        upgrade_points += 2
        notes.append(f"建议动作 {prev.get('suggested_action') or 'observe'} -> {curr.get('suggested_action') or 'observe'}")
    elif action_delta < 0:
        downgrade_points += 2
        notes.append(f"建议动作降级 {prev.get('suggested_action') or 'observe'} -> {curr.get('suggested_action') or 'observe'}")

    conf_delta = round(_v2_confidence(curr) - _v2_confidence(prev), 2)
    if conf_delta >= 0.12:
        upgrade_points += 1
        notes.append(f"结构置信度提升 {conf_delta:+.2f}")
    elif conf_delta <= -0.12:
        downgrade_points += 1
        notes.append(f"结构置信度回落 {conf_delta:+.2f}")

    missing_delta = _v2_missing_count(curr) - _v2_missing_count(prev)
    if missing_delta < 0:
        upgrade_points += 1
        notes.append("确认缺口收窄")
    elif missing_delta > 0:
        downgrade_points += 1
        notes.append("确认缺口增加")

    for key, label in (("stock_role", "个股角色"), ("theme_phase", "题材阶段"), ("opportunity_type", "机会类型")):
        before, after = prev.get(key), curr.get(key)
        if before and after and before != after:
            notes.append(f"{label} {before} -> {after}")

    risk_delta = _v2_risk_score(curr) - _v2_risk_score(prev)
    if risk_delta < 0:
        upgrade_points += 1
        notes.append("拥挤/假突破风险下降")
    elif risk_delta > 0:
        downgrade_points += 1
        notes.append("拥挤/假突破风险上升")

    if curr.get("hard_gate_block_reason") and not prev.get("hard_gate_block_reason"):
        downgrade_points += 1
        notes.append("新增硬闸门封顶原因")
    elif prev.get("hard_gate_block_reason") and not curr.get("hard_gate_block_reason"):
        upgrade_points += 1
        notes.append("硬闸门封顶解除")

    if downgrade_points >= max(2, upgrade_points + 1):
        reason = curr.get("invalidation") or curr.get("main_risk") or "原始机会假设被破坏或风险收益比变差"
        return "downgrade", reason, notes[:5]
    if upgrade_points >= max(2, downgrade_points + 1):
        reason = curr.get("upgrade_reason") or curr.get("why_now") or "结构假设更清楚，行为验证改善"
        return "upgrade", reason, notes[:5]
    return "continue", curr.get("why_now") or "原始假设未被破坏，但仍需继续验证", notes[:5]


def extract_shortlist(data: dict) -> dict[str, dict]:
    """Extract {code: stock_info} from ai_screening or history snapshot."""
    if not data:
        return {}

    stocks = {}

    # ai_screening_result.json format: .shortlist
    if "shortlist" in data:
        for s in data["shortlist"]:
            factor_fields = _factor_fields_from_item(s)
            opportunity_fields = _opportunity_v2_fields_from_item(s)
            stocks[s["code"]] = {
                "code": s["code"],
                "name": s.get("name", ""),
                "score": s.get("best_score", s.get("score", 0)),
                "tier": s.get("tier", ""),
                "screening_status": s.get("screening_status", ""),
                "theme": s.get("themes", [""])[0] if isinstance(s.get("themes"), list) else s.get("theme", ""),
                "change_pct": s.get("change_pct", 0),
                "amount_yi": s.get("amount_yi", 0),
                "strategy_labels": s.get("strategy_labels", []),
                "consistency_score": s.get("consistency", {}).get("score", 0),
                "entry_reason": s.get("entry_reason", ""),
                "main_risk": s.get("main_risk", ""),
                "watch_condition": s.get("watch_condition", ""),
                **opportunity_fields,
                **factor_fields,
                "timestamp": data.get("timestamp", ""),
            }
        return stocks

    # history snapshot format: .strategies.combined is a list of stocks
    strategies = data.get("strategies", {})
    for strat_name, strat_stocks in strategies.items():
        if not isinstance(strat_stocks, list):
            strat_stocks = strat_stocks.get("selected_stocks", [])
        for s in strat_stocks:
            if not isinstance(s, dict):
                continue
            code = s.get("code")
            if not code or code in stocks:
                continue  # keep first occurrence (combined is typically first)
            factor_fields = _factor_fields_from_item(s)
            opportunity_fields = _opportunity_v2_fields_from_item(s)
            stocks[code] = {
                "code": code,
                "name": s.get("name", ""),
                "score": s.get("score", 0),
                "tier": "",
                "screening_status": s.get("screening", {}).get("status", "") if isinstance(s.get("screening"), dict) else "",
                "theme": s.get("theme", ""),
                "change_pct": s.get("change_pct", 0),
                "amount_yi": s.get("amount_yi", 0),
                "strategy_labels": [strat_name],
                "consistency_score": s.get("consistency", {}).get("score", 0) if isinstance(s.get("consistency"), dict) else 0,
                "entry_reason": s.get("entry_reason", ""),
                "main_risk": s.get("main_risk", ""),
                "watch_condition": s.get("watch_condition", ""),
                **opportunity_fields,
                **factor_fields,
                "timestamp": data.get("timestamp", ""),
            }
    return stocks


def find_previous_snapshot(
    history_dir: str,
    current_timestamp: str = "",
    days_back: int = 1,
) -> tuple[dict[str, dict], str]:
    """Find the most recent snapshot before current_timestamp, preferring the recent lookback window."""
    if not history_dir or not os.path.isdir(history_dir):
        return {}, ""

    current_dt = None
    if current_timestamp:
        try:
            current_dt = datetime.strptime(current_timestamp, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            current_dt = None
    if current_dt is None:
        current_dt = datetime.now()

    window_start = current_dt - timedelta(days=days_back)
    recent_candidates = []
    fallback_candidates = []

    for fname in os.listdir(history_dir):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(history_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                d = json.load(f)
            ts = d.get("timestamp", "")
            if not ts:
                continue
            dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            if dt >= current_dt:
                continue
            row = (dt, d, fpath)
            fallback_candidates.append(row)
            if dt >= window_start:
                recent_candidates.append(row)
        except (json.JSONDecodeError, ValueError):
            continue

    candidates = recent_candidates or fallback_candidates
    if not candidates:
        return {}, ""

    candidates.sort(key=lambda x: x[0], reverse=True)
    dt, data, _ = candidates[0]
    return extract_shortlist(data), dt.strftime("%Y-%m-%d %H:%M:%S")


def find_previous_baseline(
    ai_history_dir: str,
    history_dir: str,
    current_timestamp: str = "",
    days_back: int = 1,
) -> tuple[dict[str, dict], str, str]:
    ai_previous, ai_previous_timestamp = find_previous_snapshot(
        ai_history_dir,
        current_timestamp=current_timestamp,
        days_back=days_back,
    )
    if ai_previous:
        return ai_previous, ai_previous_timestamp, "ai_screening_archive"

    raw_previous, raw_previous_timestamp = find_previous_snapshot(
        history_dir,
        current_timestamp=current_timestamp,
        days_back=days_back,
    )
    if raw_previous:
        return raw_previous, raw_previous_timestamp, "raw_scan_history"

    return {}, "", "none"


def _extract_midday_items(midday_data: dict, key: str) -> dict[str, dict]:
    if not midday_data:
        return {}

    out = {}
    for item in midday_data.get(key, []):
        if not isinstance(item, dict):
            continue
        code = item.get("code")
        if not code:
            continue
        out[code] = {
            "code": code,
            "name": item.get("name", ""),
            "tier": item.get("tier", ""),
            "morning_score": item.get("morning_score", 0),
            "status": item.get("status", ""),
            "reason": item.get("reason", ""),
            "details": item.get("details", []),
            "snapshot": item.get("snapshot", {}),
            "timestamp": midday_data.get("timestamp", ""),
        }
    return out


def midday_matches_ai(midday_data: dict, ai_data: dict) -> bool:
    if not midday_data or not ai_data:
        return False
    if midday_data.get("validation_status") != "ok":
        return False
    midday_ts = midday_data.get("source_morning_timestamp")
    midday_scan_ts = midday_data.get("source_scan_timestamp")
    verified_scan_ts = midday_data.get("verified_against_scan_timestamp")
    ai_ts = ai_data.get("timestamp")
    ai_scan_ts = ai_data.get("source_scan_timestamp")
    if not midday_ts or not ai_ts or midday_ts != ai_ts:
        return False
    if not midday_scan_ts or not ai_scan_ts or midday_scan_ts != ai_scan_ts:
        return False
    verified_dt = parse_timestamp(verified_scan_ts)
    ai_dt = parse_timestamp(ai_ts)
    if verified_dt and ai_dt and verified_dt.date() != ai_dt.date():
        return False
    return True


def extract_midday_handoffs(midday_data: dict) -> dict[str, dict]:
    """Extract confirmed items from midday verification as handoff candidates."""
    return _extract_midday_items(midday_data, "confirmed")


def extract_midday_downgrades(midday_data: dict) -> dict[str, dict]:
    """Extract downgraded items from midday verification, skipping malformed empty objects."""
    return _extract_midday_items(midday_data, "downgraded")


def compute_lifecycle(
    current: dict[str, dict],
    previous: dict[str, dict],
    midday_handoffs: dict[str, dict],
    midday_downgrades: dict[str, dict],
) -> dict:
    current_codes = set(current.keys())
    previous_codes = set(previous.keys())

    entered = []
    exited = []
    upgraded = []
    downgraded = []
    continued = []
    handed_off = []

    # Entered: in current but not in previous
    for code in sorted(current_codes - previous_codes):
        s = current[code]
        entered.append({
            "code": code,
            "name": s["name"],
            "tier": s["tier"],
            "screening_status": s["screening_status"],
            "score": s["score"],
            "theme": s["theme"],
            "change_pct": s["change_pct"],
            "entry_reason": s["entry_reason"],
            "main_risk": s["main_risk"],
            "reason": s.get("why_now") or s.get("entry_reason") or "新进入观察池，等待结构和行为继续验证",
            "evidence_notes": [s.get("upgrade_reason") or "", *(s.get("missing_confirmation") or [])],
            **_opportunity_snapshot_for_event(s),
            **_factor_snapshot_for_event(s),
        })

    # Exited: in previous but not in current
    for code in sorted(previous_codes - current_codes):
        s = previous[code]
        exited.append({
            "code": code,
            "name": s["name"],
            "tier": s["tier"],
            "screening_status": s["screening_status"],
            "score": s["score"],
            "theme": s["theme"],
            "last_seen": s.get("timestamp", ""),
            "reason": s.get("invalidation") or s.get("main_risk") or "已从当前 shortlist 退出，原始假设没有继续获得验证",
            "evidence_notes": [s.get("thesis") or "", s.get("hard_gate_block_reason") or ""],
            **_opportunity_snapshot_for_event(s),
            **_factor_snapshot_for_event(s),
        })
        # Best-effort exit-return tracking: log the exit so update_exits can
        # classify it (true_exit / misjudged / inconclusive) once the holding
        # window fills. Never let a tracker failure break lifecycle output.
        try:
            record_exit(
                code=code,
                name=s["name"],
                exit_date=str(s.get("timestamp", "") or "")[:10],
                exit_price=s.get("exit_price") or s.get("close") or s.get("price"),
                reason=s.get("invalidation") or s.get("main_risk") or "已退出",
                theme=s.get("theme", ""),
            )
        except Exception:
            pass

    # Upgraded / Downgraded: in both, compare tier and screening_status
    # Note: only meaningful when both sides have tier/status data (ai_screening format)
    # If previous comes from raw scan (history), tier/status will be empty
    for code in sorted(current_codes & previous_codes):
        curr = current[code]
        prev = previous[code]

        curr_score = safe_float(curr.get("score", 0), default=0.0)
        prev_score = safe_float(prev.get("score", 0), default=0.0)
        score_delta = round(curr_score - prev_score, 2)
        direction, semantic_reason, evidence_notes = _v2_change_reason(curr, prev, score_delta)

        detail = {
            "code": code,
            "name": curr["name"],
            "prev_tier": prev.get("tier", ""),
            "curr_tier": curr.get("tier", ""),
            "prev_screening_status": prev.get("screening_status", ""),
            "curr_screening_status": curr.get("screening_status", ""),
            "prev_score": prev_score,
            "curr_score": curr_score,
            "score_delta": round(score_delta, 2),
            "theme": curr["theme"],
            "reason": semantic_reason,
            "evidence_notes": evidence_notes,
            "prev_suggested_action": prev.get("suggested_action", ""),
            "curr_suggested_action": curr.get("suggested_action", ""),
            "prev_confidence": prev.get("confidence"),
            "curr_confidence": curr.get("confidence"),
            "prev_missing_confirmation_count": _v2_missing_count(prev),
            "curr_missing_confirmation_count": _v2_missing_count(curr),
            **_opportunity_snapshot_for_event(curr),
            **_factor_snapshot_for_event(curr),
        }

        if direction == "upgrade":
            upgraded.append(detail)
        elif direction == "downgrade":
            downgraded.append(detail)
        else:
            continued.append(
                {
                    **detail,
                    "tier": curr.get("tier", ""),
                    "screening_status": curr.get("screening_status", ""),
                    "score": curr_score,
                    "persistence_label": "非一日脉冲",
                    "reason": semantic_reason,
                }
            )

    # Midday downgraded: supplement downgrade funnel (and avoid malformed empty objects)
    downgraded_codes = {item["code"] for item in downgraded}
    for code in sorted(midday_downgrades.keys()):
        if code in downgraded_codes:
            continue
        d = midday_downgrades[code]
        in_current = code in current_codes
        current_info = current.get(code, {})
        downgraded.append({
            "code": code,
            "name": d["name"],
            "prev_tier": d.get("tier", ""),
            "curr_tier": current_info.get("tier", ""),
            "prev_screening_status": "midday_watch",
            "curr_screening_status": current_info.get("screening_status", "") if in_current else "",
            "prev_score": d.get("morning_score", 0),
            "curr_score": current_info.get("score", d.get("morning_score", 0)) if in_current else d.get("morning_score", 0),
            "score_delta": round((current_info.get("score", d.get("morning_score", 0)) if in_current else d.get("morning_score", 0)) - d.get("morning_score", 0), 2),
            "theme": current_info.get("theme", ""),
            "reason": d.get("reason", "") or current_info.get("invalidation", "") or "午盘承接失败，原始假设暂时失效",
            "evidence_notes": d.get("details", []) or [current_info.get("invalidation", "")],
            "source": "midday_verification",
            **_opportunity_snapshot_for_event(current_info),
            **_factor_snapshot_for_event(current_info),
        })

    # Handed off: confirmed in midday verification
    for code in sorted(midday_handoffs.keys()):
        h = midday_handoffs[code]
        in_current = code in current_codes
        handed_off.append({
            "code": code,
            "name": h["name"],
            "tier": h["tier"],
            "morning_score": h["morning_score"],
            "status": h["status"],
            "reason": h["reason"],
            "in_current_shortlist": in_current,
            "current_tier": current[code]["tier"] if in_current else "N/A",
            "current_screening_status": current[code]["screening_status"] if in_current else "N/A",
            **_opportunity_snapshot_for_event(current.get(code, {})),
        })

    return {
        "entered": entered,
        "upgraded": upgraded,
        "downgraded": downgraded,
        "continued": continued,
        "exited": exited,
        "handed_off": handed_off,
        "summary": {
            "entered_count": len(entered),
            "upgraded_count": len(upgraded),
            "downgraded_count": len(downgraded),
            "continued_count": len(continued),
            "exited_count": len(exited),
            "handed_off_count": len(handed_off),
            "current_pool_size": len(current_codes),
            "previous_pool_size": len(previous_codes),
        },
    }


def generate_markdown(lifecycle: dict, now_str: str) -> str:
    lines = []
    s = lifecycle["summary"]
    lines.append(f"# 候选生命周期报告 | {now_str}")
    lines.append("")
    lines.append(f"当前候选池：**{s['current_pool_size']}** 只 | 前次候选池：**{s['previous_pool_size']}** 只")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Summary bar
    lines.append("## 变动总览")
    lines.append("")
    lines.append(f"| 状态 | 数量 |")
    lines.append(f"|------|------|")
    lines.append(f"| 🆕 新入选 | {s['entered_count']} |")
    lines.append(f"| ⬆️ 升级 | {s['upgraded_count']} |")
    lines.append(f"| ⬇️ 降级 | {s['downgraded_count']} |")
    lines.append(f"| ✅ 非一日脉冲 | {s.get('continued_count', 0)} |")
    lines.append(f"| 🚪 退出 | {s['exited_count']} |")
    lines.append(f"| 🔄 已移交 analyzer | {s['handed_off_count']} |")
    lines.append("")

    # Entered
    if lifecycle["entered"]:
        lines.append("## 🆕 新入选 (entered)")
        lines.append("")
        for e in lifecycle["entered"]:
            action = e.get("suggested_action_label") or e.get("suggested_action") or e.get("screening_status")
            lines.append(f"- **{e['name']}({e['code']})** | {action} | 置信 {e.get('confidence', '-')} | {e['theme']}")
            if e.get("thesis"):
                lines.append(f"  - 假设：{e['thesis']}")
            if e.get("reason"):
                lines.append(f"  - 为什么现在：{e['reason']}")
            if e.get("missing_confirmation"):
                lines.append(f"  - 还差确认：{'；'.join(str(item) for item in e.get('missing_confirmation') or [])}")
            if e.get("hard_gate_block_reason"):
                lines.append(f"  - 硬闸门：{e['hard_gate_block_reason']}")
        lines.append("")

    # Upgraded
    if lifecycle["upgraded"]:
        lines.append("## ⬆️ 升级 (upgraded)")
        lines.append("")
        for u in lifecycle["upgraded"]:
            action = f"{u.get('prev_suggested_action') or '-'} → {u.get('curr_suggested_action') or u.get('suggested_action') or '-'}"
            lines.append(f"- **{u['name']}({u['code']})** | V2 动作 {action} | 置信 {u.get('prev_confidence', '-')}→{u.get('curr_confidence', '-')}")
            lines.append(f"  - 升级原因：{u.get('reason') or '结构假设更清楚'}")
            if u.get("evidence_notes"):
                lines.append(f"  - 证据：{'；'.join(str(item) for item in u.get('evidence_notes') or [] if item)}")
            if u.get("missing_confirmation"):
                lines.append(f"  - 还差确认：{'；'.join(str(item) for item in u.get('missing_confirmation') or [])}")
        lines.append("")

    # Downgraded
    if lifecycle["downgraded"]:
        lines.append("## ⬇️ 降级 (downgraded)")
        lines.append("")
        for d in lifecycle["downgraded"]:
            action = f"{d.get('prev_suggested_action') or '-'} → {d.get('curr_suggested_action') or d.get('suggested_action') or '-'}"
            suffix = f" | {d.get('theme', '')}" if d.get("theme") else ""
            lines.append(f"- **{d['name']}({d['code']})** | V2 动作 {action} | 评分旁证 {d.get('prev_score')}→{d.get('curr_score')} ({d.get('score_delta')}){suffix}")
            lines.append(f"  - 降级原因：{d.get('reason') or '原始假设被破坏'}")
            if d.get("invalidation"):
                lines.append(f"  - 失效条件：{d['invalidation']}")
            if d.get("evidence_notes"):
                lines.append(f"  - 证据：{'；'.join(str(item) for item in d.get('evidence_notes') or [] if item)}")
            if d.get("source") == "midday_verification":
                lines.append("  - 来源：盘中验证")
        lines.append("")

    # Continued
    if lifecycle.get("continued"):
        lines.append("## ✅ 非一日脉冲 (continued)")
        lines.append("")
        for c in lifecycle["continued"]:
            delta = c["score_delta"]
            delta_str = f"+{delta}" if delta > 0 else str(delta)
            lines.append(
                f"- **{c['name']}({c['code']})** | Tier {c.get('tier', '')}/{c.get('screening_status', '')} | "
                f"评分 {c['prev_score']}→{c['curr_score']} ({delta_str}) | {c.get('theme', '')}"
            )
            if c.get("reason"):
                lines.append(f"  - 延续原因：{c['reason']}")
        lines.append("")

    # Exited
    if lifecycle["exited"]:
        lines.append("## 🚪 退出 (exited)")
        lines.append("")
        for e in lifecycle["exited"]:
            lines.append(f"- **{e['name']}({e['code']})** | {e.get('suggested_action_label') or e.get('screening_status')} | {e['theme']}")
            if e.get("reason"):
                lines.append(f"  - 退出原因：{e['reason']}")
            if e.get("last_seen"):
                lines.append(f"  - 最后出现：{e['last_seen']}")
        lines.append("")

    # Handed off
    if lifecycle["handed_off"]:
        lines.append("## 🔄 已移交 analyzer (handed_off)")
        lines.append("")
        for h in lifecycle["handed_off"]:
            current_info = f"当前 Tier {h['current_tier']}/{h['current_screening_status']}" if h.get("in_current_shortlist") else "已不在当前候选池"
            lines.append(f"- **{h['name']}({h['code']})** | 盘中确认 {h['status']} | 早盘评分 {h['morning_score']} | {current_info}")
            if h.get("reason"):
                lines.append(f"  - 确认理由：{h['reason']}")
        lines.append("")

    if not any(lifecycle.get(k) for k in ["entered", "upgraded", "downgraded", "continued", "exited", "handed_off"]):
        lines.append("## 无变动")
        lines.append("")
        lines.append("与上一期候选池相比，未检测到状态变化。")

    return "\n".join(lines)


def main():
    args = parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.dirname(script_dir)

    ai_input = args.ai_input or os.path.join(base_dir, "data", "ai_screening_result.json")
    midday_input = args.midday_input or os.path.join(base_dir, "data", "midday_verification_result.json")
    history_dir = args.history_dir or os.path.join(base_dir, "data", "history")
    ai_history_dir = args.ai_history_dir or os.path.join(base_dir, "data", "ai_history")
    output_dir = args.output_dir or os.path.join(base_dir, "data")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    run_stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")

    # Load data
    ai_data = load_json(ai_input)
    midday_data = load_json(midday_input)

    if not ai_data:
        print(f"ERROR: 无法加载当前 ai_screening_result: {ai_input}", file=sys.stderr)
        sys.exit(1)

    current = extract_shortlist(ai_data)
    previous, previous_timestamp, prev_source = find_previous_baseline(
        ai_history_dir,
        history_dir,
        current_timestamp=ai_data.get("timestamp", ""),
        days_back=args.days_back,
    )
    midday_matched = midday_matches_ai(midday_data, ai_data)
    midday_handoffs = extract_midday_handoffs(midday_data) if midday_matched else {}
    midday_downgrades = extract_midday_downgrades(midday_data) if midday_matched else {}

    # Compute lifecycle
    lifecycle = compute_lifecycle(current, previous, midday_handoffs, midday_downgrades)
    lifecycle["metadata"] = {
        "generated_at": now_str,
        "current_timestamp": ai_data.get("timestamp", ""),
        "previous_snapshot_source": prev_source,
        "previous_snapshot_timestamp": previous_timestamp or "N/A",
        "previous_pool_size": len(previous),
        "midday_verification_timestamp": midday_data.get("timestamp", "") if midday_data else "N/A",
        "midday_validation_status": midday_data.get("validation_status", "missing") if midday_data else "missing",
        "midday_matches_current_ai": midday_matched,
        "midday_downgraded_count": len(midday_downgrades),
        "ai_input": ai_input,
        "ai_history_dir": ai_history_dir,
        "midday_input": midday_input,
    }

    # Output JSON
    json_path = args.output_json or os.path.join(output_dir, f"lifecycle_{run_stamp}.json")
    md_path = args.output_md or os.path.join(output_dir, f"lifecycle_{run_stamp}.md")

    reports_dir = os.path.join(base_dir, "reports")
    report_md_path = args.report_output or os.path.join(reports_dir, f"lifecycle_{run_stamp}.md")

    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    # Stage-contract guard: fail fast if load-bearing fields are missing.
    validate_stage_output(lifecycle, "candidate_lifecycle")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(lifecycle, f, ensure_ascii=False, indent=2)

    # Output Markdown
    md_content = generate_markdown(lifecycle, now_str)
    os.makedirs(os.path.dirname(md_path), exist_ok=True)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    # Also copy to reports dir
    os.makedirs(os.path.dirname(report_md_path), exist_ok=True)
    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    # Print summary
    s = lifecycle["summary"]
    print(f"=== 候选生命周期 v1 | {now_str} ===")
    print(f"当前候选池: {s['current_pool_size']} | 前次: {s['previous_pool_size']}")
    print(f"  🆕 entered:    {s['entered_count']}")
    print(f"  ⬆️ upgraded:   {s['upgraded_count']}")
    print(f"  ⬇️ downgraded: {s['downgraded_count']}")
    print(f"  ✅ continued:  {s.get('continued_count', 0)}")
    print(f"  🚪 exited:     {s['exited_count']}")
    print(f"  🔄 handed_off: {s['handed_off_count']}")
    print(f"")
    print(f"JSON  -> {json_path}")
    print(f"MD    -> {md_path}")
    print(f"Report -> {report_md_path}")

    return lifecycle


if __name__ == "__main__":
    main()
