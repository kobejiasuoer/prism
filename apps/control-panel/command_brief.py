"""Daily command brief aggregator.

Pure-derivation helpers used by ``dashboard_data.build_today_view`` to
project existing today-view inputs (readiness, gate, decision_brief,
watchlist, screening, confirmation, action_groups, action_queue) into the
5-section command brief defined in
``docs/superpowers/specs/2026-05-22-daily-command-brief-design.md``.

All functions in this module are side-effect free and accept plain dicts.
"""

from __future__ import annotations

import re
from datetime import datetime as _dt
from typing import Any


_LIMITED_LABEL_KEYWORDS = ("限制", "试错", "防守", "限仓")
_OFFENSE_LABEL_KEYWORDS = ("放开", "进攻", "强势", "加仓")

_MODE_LABELS = {
    "defense": "防守",
    "observe": "观察",
    "probe": "试探",
    "offense": "进攻",
}

_MODE_TONES = {
    "defense": "risk",
    "observe": "watch",
    "probe": "hold",
    "offense": "positive",
}

V2_ACTION_ORDER = {
    "observe": 0,
    "review": 1,
    "shadow": 2,
    "trial": 3,
    "actionable": 4,
}

V2_ACTION_LABELS = {
    "observe": "只观察",
    "review": "人工复核",
    "shadow": "影子跟踪",
    "trial": "试错待触发",
    "actionable": "可执行待复核",
}


def _label_kind(label: str) -> str:
    text = label or ""
    if any(token in text for token in _LIMITED_LABEL_KEYWORDS):
        return "limited"
    if any(token in text for token in _OFFENSE_LABEL_KEYWORDS):
        return "offense"
    return "other"


def _text_items(values: Any) -> list[str]:
    if isinstance(values, list):
        return [str(value).strip() for value in values if str(value or "").strip()]
    text = str(values or "").strip()
    return [text] if text else []


def _v2_judgment(item: dict[str, Any]) -> dict[str, Any]:
    judgment = item.get("opportunity_v2")
    return dict(judgment) if isinstance(judgment, dict) else {}


def _v2_nested(judgment: dict[str, Any], key: str) -> dict[str, Any]:
    value = judgment.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _v2_action(item: dict[str, Any]) -> str:
    judgment = _v2_judgment(item)
    action = str(item.get("suggested_action") or judgment.get("suggested_action") or "").strip()
    return action if action in V2_ACTION_ORDER else ""


def _v2_label(item: dict[str, Any]) -> str:
    judgment = _v2_judgment(item)
    action = _v2_action(item)
    return str(item.get("suggested_action_label") or judgment.get("action_label") or V2_ACTION_LABELS.get(action, "")).strip()


def _v2_hard_gate(item: dict[str, Any]) -> dict[str, Any]:
    return _v2_nested(_v2_judgment(item), "hard_gate")


def _v2_hard_max(item: dict[str, Any]) -> str:
    gate = _v2_hard_gate(item)
    value = str(item.get("hard_gate_max_action") or gate.get("maximum_allowed_action") or "").strip()
    return value if value in V2_ACTION_ORDER else ""


def _v2_hard_reason(item: dict[str, Any]) -> str:
    gate = _v2_hard_gate(item)
    block_reasons = gate.get("block_reasons") if isinstance(gate.get("block_reasons"), list) else []
    return str(item.get("hard_gate_block_reason") or "；".join(_text_items(block_reasons)) or "").strip()


def _v2_rank(action: str) -> int:
    return V2_ACTION_ORDER.get(str(action or "").strip(), -1)


def _v2_hard_blocked(item: dict[str, Any]) -> bool:
    action = _v2_action(item)
    desired = str(_v2_judgment(item).get("desired_action") or "").strip()
    max_action = _v2_hard_max(item)
    return bool(
        action
        and max_action
        and (
            _v2_rank(max_action) < _v2_rank(desired or action)
            or _v2_hard_reason(item)
        )
    )


def _v2_missing(item: dict[str, Any]) -> list[str]:
    return _text_items(item.get("missing_confirmation") or _v2_judgment(item).get("missing_confirmation"))


def _v2_calibration(item: dict[str, Any]) -> dict[str, Any]:
    return _v2_nested(_v2_judgment(item), "calibration")


def _v2_ai_summary(item: dict[str, Any]) -> dict[str, Any]:
    direct = item.get("ai_summary")
    if isinstance(direct, dict):
        return dict(direct)
    return _v2_nested(_v2_judgment(item), "ai_summary")


def _v2_ai_status(item: dict[str, Any]) -> str:
    return str(item.get("ai_status") or _v2_judgment(item).get("ai_status") or _v2_ai_summary(item).get("status") or "").strip()


def _v2_ai_label(item: dict[str, Any]) -> str:
    summary = _v2_ai_summary(item)
    status = _v2_ai_status(item)
    return str(item.get("ai_status_label") or summary.get("label") or status or "").strip()


def _v2_ai_detail(item: dict[str, Any]) -> str:
    summary = _v2_ai_summary(item)
    label = _v2_ai_label(item)
    detail = str(summary.get("detail") or "").strip()
    if detail and label and label not in detail:
        return f"{label}：{detail}"
    return detail or label


def _v2_ai_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    buckets = {"used": 0, "shadow_recorded": 0, "fallback": 0, "not_requested": 0, "disabled": 0, "other": 0}
    for item in items:
        status = _v2_ai_status(item) or "not_requested"
        if status in {"not_configured", "fallback"}:
            buckets["fallback"] += 1
        elif status in buckets:
            buckets[status] += 1
        else:
            buckets["other"] += 1
    return buckets


def _v2_mode_guard(item: dict[str, Any]) -> dict[str, Any]:
    return _v2_nested(_v2_judgment(item), "mode_guard")


def _v2_calibration_summary(item: dict[str, Any]) -> str:
    judgment = _v2_judgment(item)
    calibration = _v2_calibration(item)
    mode_guard = _v2_mode_guard(item)
    requested = str(
        item.get("v2_mode_requested")
        or judgment.get("mode_requested")
        or mode_guard.get("requested_mode")
        or ""
    ).strip()
    effective = str(
        item.get("v2_mode_effective")
        or judgment.get("mode_effective")
        or mode_guard.get("effective_mode")
        or judgment.get("mode")
        or ""
    ).strip()
    stage = str(item.get("v2_calibration_stage") or calibration.get("sample_stage") or mode_guard.get("sample_stage") or "").strip()
    reason = str(item.get("v2_calibration_guard_reason") or calibration.get("guard_reason") or mode_guard.get("guard_reason") or "").strip()
    playbook_adjustment = calibration.get("playbook_adjustment") if isinstance(calibration.get("playbook_adjustment"), dict) else {}
    playbook_reason = str(playbook_adjustment.get("reason") or "").strip()
    if requested == "active" and effective and effective != "active":
        return reason or f"V2 active 未放开，当前按 {effective} 模式辅助判断"
    if playbook_reason:
        return playbook_reason
    if stage in {"cold_start", "needs_recalibration"}:
        return reason or f"V2 校准阶段={stage}，动作阈值已收紧"
    return ""


def _v2_collect_candidates(
    screening_batch: dict[str, Any] | None,
    confirmation: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for lane, source in (
        ("screening", (screening_batch or {}).get("candidates") or []),
        ("confirmed", (confirmation or {}).get("confirmed") or []),
        ("fresh", (confirmation or {}).get("fresh_candidates") or []),
        ("downgraded", (confirmation or {}).get("downgraded") or []),
    ):
        for item in source:
            if not isinstance(item, dict) or not _v2_action(item):
                continue
            key = (lane, str(item.get("code") or item.get("title") or ""))
            if key in seen:
                continue
            seen.add(key)
            rows.append(item)
    return rows


def _v2_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    return {action: sum(1 for item in items if _v2_action(item) == action) for action in V2_ACTION_ORDER}


def derive_mode(
    *,
    readiness: dict[str, Any],
    gate: dict[str, Any],
    confirmation: dict[str, Any] | None,
    decision_brief: dict[str, Any] | None,
) -> dict[str, Any]:
    readiness_mode = str(readiness.get("readiness_mode") or "blocked")
    allow_new = bool(gate.get("allow_new_positions"))
    label_kind = _label_kind(str(gate.get("label") or ""))
    counts = (confirmation or {}).get("counts") or {}
    confirmed_total = int(counts.get("confirmed") or 0) + int(counts.get("fresh_candidates") or 0)

    reasons: list[str] = [f"readiness={readiness_mode}", f"allow_new={allow_new}", f"label_kind={label_kind}"]

    if readiness_mode == "blocked":
        value = "defense"
    elif readiness_mode == "shadow_only":
        value = "observe"
    elif not allow_new:
        value = "observe"
    elif label_kind == "offense" and confirmed_total >= 1:
        value = "offense"
    else:
        value = "probe"

    brief_today_mode = ((decision_brief or {}).get("summary") or {}).get("today_mode")
    if brief_today_mode in _MODE_LABELS:
        value = brief_today_mode
        reasons.append("brief_override")

    summary = _mode_summary(value, gate, readiness)

    return {
        "value": value,
        "label": _MODE_LABELS[value],
        "tone": _MODE_TONES[value],
        "summary": summary,
        "reasons": reasons,
    }


def _mode_summary(value: str, gate: dict[str, Any], readiness: dict[str, Any]) -> str:
    gate_summary = str(gate.get("summary") or "").strip()
    if value == "defense":
        blocker = (readiness.get("blockers") or [{}])[0].get("message") if readiness.get("blockers") else ""
        return blocker or "数据未对齐当日，今天先恢复链路。"
    if value == "observe":
        return gate_summary or "进攻阀门关闭，今天只观察，不直接开仓。"
    if value == "probe":
        return gate_summary or "可以试探，但单笔小、持有短，先验证主线。"
    return gate_summary or "环境放开，仍按仓位纪律分批。"


_PERMIT_DATA = {
    "live_ready": ("on", "正常"),
    "shadow_only": ("shadow", "影子盘"),
    "blocked": ("off", "未就绪"),
}


def _capability(readiness: dict[str, Any], key: str) -> dict[str, Any]:
    item = (readiness.get("capabilities") or {}).get(key)
    return item if isinstance(item, dict) else {}


def _capability_granted(readiness: dict[str, Any], key: str) -> bool:
    return bool(_capability(readiness, key).get("granted"))


def _trust_level(readiness: dict[str, Any]) -> dict[str, Any]:
    trust = readiness.get("trust_level")
    return trust if isinstance(trust, dict) else {}


def _first_capability_reason(readiness: dict[str, Any], *keys: str) -> str:
    for key in keys:
        cap = _capability(readiness, key)
        for entry in cap.get("why_not") or []:
            message = str((entry or {}).get("message") or "").strip()
            if message:
                return message
    for reason in _trust_level(readiness).get("blocking_reasons") or []:
        text = str(reason).strip()
        if text:
            return text
    return ""


def derive_permits(
    *,
    readiness: dict[str, Any],
    gate: dict[str, Any],
    confirmation: dict[str, Any] | None,
    screening_batch: dict[str, Any] | None,
) -> dict[str, Any]:
    readiness_mode = str(readiness.get("readiness_mode") or "blocked")
    data_value, data_label = _PERMIT_DATA.get(readiness_mode, ("off", "未就绪"))
    data_why = _readiness_why(readiness)
    has_capabilities = bool(readiness.get("capabilities"))
    can_review = _capability_granted(readiness, "review") if has_capabilities else data_value == "on"
    can_approve = _capability_granted(readiness, "approve") if has_capabilities else data_value == "on"
    can_trade = _capability_granted(readiness, "trade") if has_capabilities else data_value == "on"
    trust_level = str(_trust_level(readiness).get("level") or "").strip()
    if data_value == "on" and not can_approve and can_review:
        data_value, data_label = "review", "可观察/复核"
        data_why = _first_capability_reason(readiness, "approve", "trade") or "数据链路已恢复，但正式放行/真钱买入未通过。"
    elif data_value == "on" and trust_level == "observe_only":
        data_value, data_label = "observe", "仅可观察"
        data_why = _first_capability_reason(readiness, "approve", "trade") or "当前只能观察，不能直接买入。"

    if data_value != "on":
        market_value, market_label = "off", "进攻阀门关闭"
    else:
        allow_new = bool(gate.get("allow_new_positions"))
        kind = _label_kind(str(gate.get("label") or ""))
        if not allow_new:
            market_value, market_label = "off", "进攻阀门关闭"
        elif kind == "offense":
            market_value, market_label = "on", "进攻放开"
        else:
            market_value, market_label = "limited", "限制试错"
    market_why = str(gate.get("summary") or "").strip() or "实时阀门判断"

    counts = (confirmation or {}).get("counts") or {}
    fresh = int(counts.get("fresh_candidates") or 0)
    confirmed_count = int(counts.get("confirmed") or 0)
    approved = int(
        (((screening_batch or {}).get("screening_summary") or {}).get("approved_count") or 0)
    )
    v2_items = _v2_collect_candidates(screening_batch, confirmation)
    v2_counts = _v2_counts(v2_items)
    v2_hard_blocked = sum(1 for item in v2_items if _v2_hard_blocked(item))

    if v2_items:
        if data_value == "off":
            opp_value = "none"
            opp_label = "今天不输出机会判断"
        elif not can_approve:
            opp_value = "observe"
            opp_label = "只观察，不可买入"
        elif market_value == "off":
            opp_value = "observe"
            opp_label = "只观察，不直接开仓"
        elif v2_counts.get("actionable") and can_trade and market_value == "on":
            opp_value = "actionable"
            opp_label = "可执行待复核"
        elif v2_counts.get("actionable") or v2_counts.get("trial"):
            opp_value = "conditional"
            opp_label = "条件触发"
        else:
            opp_value = "observe"
            opp_label = "只观察"
        opp_why = (
            f"V2 可执行 {v2_counts.get('actionable') or 0}，试错 {v2_counts.get('trial') or 0}，"
            f"影子/复核 {(v2_counts.get('shadow') or 0) + (v2_counts.get('review') or 0)}，"
            f"硬闸门封顶 {v2_hard_blocked}"
        )
        blocker = next((_v2_hard_reason(item) for item in v2_items if _v2_hard_reason(item)), "")
        missing = next(("；".join(_v2_missing(item)[:2]) for item in v2_items if _v2_missing(item)), "")
        calibration = next((_v2_calibration_summary(item) for item in v2_items if _v2_calibration_summary(item)), "")
        if blocker:
            opp_why = f"{opp_why}；不能买原因：{blocker}"
        elif calibration:
            opp_why = f"{opp_why}；校准护栏：{calibration}"
        elif missing and opp_value != "actionable":
            opp_why = f"{opp_why}；还差：{missing}"
    else:
        if data_value == "off":
            opp_value = "none"
            opp_label = "今天不输出机会判断"
        elif not can_approve:
            opp_value = "observe"
            opp_label = "只观察，不可买入"
        elif market_value == "off":
            opp_value = "observe"
            opp_label = "只观察，不直接开仓"
        elif market_value == "limited":
            opp_value = "conditional" if (confirmed_count + fresh) >= 1 else "observe"
            opp_label = "条件触发" if opp_value == "conditional" else "只观察"
        else:  # on
            opp_value = "actionable" if (confirmed_count + fresh) >= 1 else "observe"
            opp_label = "可执行" if opp_value == "actionable" else "等更清晰确认"
        opp_why = f"午盘新增 {fresh}，确认 {confirmed_count}，候选 {approved}"
    if not can_approve:
        reason = _first_capability_reason(readiness, "approve", "trade")
        if reason:
            opp_why = f"{opp_why}；{reason}"
    if not can_trade and can_approve:
        reason = _first_capability_reason(readiness, "trade")
        if reason:
            opp_why = f"{opp_why}；买入仍未放行：{reason}"

    return {
        "data":        {"value": data_value, "label": data_label, "tone": _permit_tone(data_value), "why": data_why},
        "market":      {"value": market_value, "label": market_label, "tone": _permit_tone(market_value), "why": market_why},
        "opportunity": {"value": opp_value, "label": opp_label, "tone": _permit_tone(opp_value), "why": opp_why},
    }


def _readiness_why(readiness: dict[str, Any]) -> str:
    blockers = readiness.get("blockers") or []
    if blockers:
        return str(blockers[0].get("message") or "数据未对齐当日")
    warnings = readiness.get("warnings") or []
    if warnings:
        return str(warnings[0].get("message") or "数据存在告警")
    return "数据已对齐当日"


def _permit_tone(value: str) -> str:
    if value in {"off", "none"}:
        return "risk"
    if value in {"shadow", "limited", "observe", "review", "conditional"}:
        return "watch"
    if value in {"on", "actionable"}:
        return "positive"
    return "watch"


_DEFENSE_POSITION_CAP = "0成"
_DEFAULT_POSITION_CAPS = {
    "defense": _DEFENSE_POSITION_CAP,
    "observe": "0-0.3成",
    "probe":   "0.3-0.5成",
    "offense": "0.5-0.8成",
}

_POSITION_CAP_NOTES = {
    "defense": "今天不开新仓；只处理旧仓与禁令。",
    "observe": "今天最多 0-0.3 成新仓；单笔 ≤ 0.5%。",
    "probe":   "试探仓位 0.3-0.5 成；单笔 ≤ 1%。",
    "offense": "可分批至 0.5-0.8 成；单笔 ≤ 1.5%。",
}


def derive_position_cap(
    *,
    mode_value: str,
    gate: dict[str, Any],
    decision_brief: dict[str, Any] | None,
) -> dict[str, Any]:
    gate_cap = str(gate.get("position_cap") or "").strip()
    if gate_cap == _DEFENSE_POSITION_CAP:
        return {
            "value": _DEFENSE_POSITION_CAP,
            "raw": gate_cap,
            "tone": "risk",
            "note": _POSITION_CAP_NOTES["defense"],
        }
    if mode_value == "defense":
        raw, value = _DEFENSE_POSITION_CAP, _DEFENSE_POSITION_CAP
    else:
        brief_cap = ((decision_brief or {}).get("summary") or {}).get("position_cap")
        raw = str(brief_cap or gate_cap or _DEFAULT_POSITION_CAPS[mode_value])
        value = raw
    note = _POSITION_CAP_NOTES.get(mode_value, "按仓位纪律执行。")
    tone = "risk" if mode_value == "defense" else "watch" if mode_value in {"observe", "probe"} else "positive"
    return {"value": value, "raw": raw, "tone": tone, "note": note}


def _action_item_state(item: dict[str, Any] | None) -> str:
    safe = item or {}
    state = (safe.get("display_state") or {}).get("value")
    if not state:
        state = (safe.get("decision") or {}).get("value")
    return str(state or "pending")


def derive_first_action(
    *,
    mode_value: str,
    action_queue: dict[str, Any],
    readiness: dict[str, Any],
) -> dict[str, Any]:
    can_approve = _capability_granted(readiness, "approve") if readiness.get("capabilities") else mode_value != "defense"
    if mode_value != "defense" and not can_approve:
        reason = _first_capability_reason(readiness, "approve", "trade") or _readiness_why(readiness)
        return {
            "title": "先复核观察名单",
            "reason": reason or "当前未放行买入，只做观察和复核。",
            "url": "#judgement-chain",
            "action_key": None,
            "tone": "watch",
            "kind": "review_only",
        }

    if mode_value == "defense":
        msg = _readiness_why(readiness)
        return {
            "title": "先恢复数据链路",
            "reason": msg,
            "url": "/settings",
            "action_key": None,
            "tone": "risk",
            "kind": "recover_data",
        }

    items = (action_queue or {}).get("items") or []
    pending = [item for item in items if item and _action_item_state(item) == "pending"]
    if pending:
        first = pending[0]
        return {
            "title": str(first.get("title") or "处理下一条动作"),
            "reason": str(first.get("detail") or first.get("foot") or first.get("source") or "持仓优先处理"),
            "url": str(first.get("url") or "#action-lanes"),
            "action_key": str(first.get("key")) if first.get("key") else None,
            "tone": str(first.get("tone") or "sell"),
            "kind": "stock",
        }

    if mode_value == "observe":
        return {
            "title": "先复核优先持仓",
            "reason": "今天没有强动作票，先把持仓边界过一遍。",
            "url": "/portfolio",
            "action_key": None,
            "tone": "watch",
            "kind": "system",
        }

    return {
        "title": "今天先观望",
        "reason": "没有 pending 动作；保留观察名单。",
        "url": "#judgement-chain",
        "action_key": None,
        "tone": "hold",
        "kind": "system",
    }


def derive_forbid_today(
    *,
    mode_value: str,
    decision_brief: dict[str, Any] | None,
    action_groups: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    if mode_value == "defense":
        items.append({
            "title": "今天不开新仓",
            "reason": "进攻阀门关闭，等数据回到 live_ready 再说。",
            "tone": "risk",
            "source": "command_brief",
        })

    avoid_group = next((g for g in action_groups if str(g.get("key")) == "avoid"), {}) or {}
    for entry in (avoid_group.get("items") or []):
        items.append({
            "title": str(entry.get("title") or entry.get("status") or "明确回避"),
            "reason": str(entry.get("detail") or entry.get("foot") or "按 avoid 组规则执行。"),
            "tone": str(entry.get("tone") or "risk"),
            "source": str(entry.get("source") or "avoid"),
        })

    for point in (((decision_brief or {}).get("focus") or {}).get("avoid_points") or [])[:3]:
        text = str(point or "").strip()
        if not text:
            continue
        items.append({
            "title": text,
            "reason": "来自总控简报 avoid_points",
            "tone": "risk",
            "source": "decision_brief",
        })

    if not items:
        items.append({
            "title": "不追高、不补亏",
            "reason": "默认禁令；保持纪律。",
            "tone": "risk",
            "source": "default",
        })

    return items[:4]


_RECLASSIFY_RULES = {
    "defense": [
        {"label": "→ 观察", "condition": "数据回到 live_ready", "evidence": "在 Settings 跑安全刷新", "url": "/settings"},
        {"label": "→ 试探", "condition": "数据就绪 + 进攻阀门为 limited", "evidence": "等阀门切换", "url": "/settings"},
    ],
    "observe": [
        {"label": "→ 试探", "condition": "主线强度 ≥ B 且 confirmed ≥ 1", "evidence": "看主线与午盘确认", "url": "/discovery"},
    ],
    "probe": [
        {"label": "→ 进攻", "condition": "confirmed ≥ 2 持续两日", "evidence": "看连续午盘确认", "url": "/discovery"},
        {"label": "→ 观察", "condition": "downgraded ≥ 2 或主线降级", "evidence": "看降级流", "url": "/discovery"},
    ],
    "offense": [
        {"label": "→ 试探", "condition": "fresh_candidates 连续 2 日为 0", "evidence": "看午盘新增", "url": "/discovery"},
    ],
}


def derive_reclassify_when(
    *,
    mode_value: str,
    readiness: dict[str, Any],
    gate: dict[str, Any],
) -> list[dict[str, Any]]:
    rules = list(_RECLASSIFY_RULES.get(mode_value) or [])
    if not rules:
        return []

    gate_summary = str(gate.get("summary") or "").strip()
    recommended = (readiness.get("recommended_tasks") or [None])[0]
    output: list[dict[str, Any]] = []
    for rule in rules:
        cond = rule["condition"]
        if gate_summary and gate_summary not in cond:
            cond = f"{cond}（参考：{gate_summary}）"
        if recommended and rule["url"] == "/settings":
            cond = f"{cond}；推荐先跑 {recommended}"
        output.append({
            "label": rule["label"],
            "condition": cond,
            "evidence": rule["evidence"],
            "url": rule["url"],
        })
    return output


_FROZEN_EVIDENCE = ["数据未对齐当日"]
_FROZEN_IMPACT = "不展示旧主线 / 旧仓位 / 旧机会"


def derive_judgement_chain(
    *,
    readiness: dict[str, Any],
    gate: dict[str, Any],
    watchlist: dict[str, Any] | None,
    screening_batch: dict[str, Any] | None,
    confirmation: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    frozen = str(readiness.get("readiness_mode") or "blocked") == "blocked"

    def frozen_row(dim: str, title: str) -> dict[str, Any]:
        return {
            "dim": dim,
            "title": title,
            "verdict": "未对齐当日",
            "tone": "risk",
            "evidence": list(_FROZEN_EVIDENCE),
            "impact": _FROZEN_IMPACT,
        }

    if frozen:
        return [
            frozen_row("market", "市场环境"),
            frozen_row("main_theme", "主线强度"),
            frozen_row("holdings_pressure", "持仓压力"),
            frozen_row("new_quality", "新机会质量"),
        ]

    return [
        _market_dimension(gate),
        _main_theme_dimension(screening_batch),
        _holdings_pressure_dimension(watchlist, confirmation),
        _new_quality_dimension(confirmation, screening_batch),
    ]


def _market_dimension(gate: dict[str, Any]) -> dict[str, Any]:
    allow_new = bool(gate.get("allow_new_positions"))
    kind = _label_kind(str(gate.get("label") or ""))
    if not allow_new:
        verdict, tone, impact = "弱", "risk", "今天不允许开新仓"
    elif kind == "offense":
        verdict, tone, impact = "强", "positive", "今天允许分批开新仓，仍按单笔上限"
    else:
        verdict, tone, impact = "中", "watch", "今天可试探，单笔小、持有短"
    evidence = [str(gate.get("label") or "实时阀门"), str(gate.get("summary") or "").strip() or "无额外摘要"]
    return {"dim": "market", "title": "市场环境", "verdict": verdict, "tone": tone, "evidence": evidence, "impact": impact}


def _main_theme_dimension(screening_batch: dict[str, Any] | None) -> dict[str, Any]:
    themes = (screening_batch or {}).get("market_themes") or {}
    top = str(themes.get("top_theme") or "").strip()
    summary = (screening_batch or {}).get("screening_summary") or {}
    approved = int(summary.get("approved_count") or 0)
    if not top:
        verdict, tone, impact = "无", "risk", "今天没有可对齐的主线，不发散"
    elif approved >= 3:
        verdict, tone, impact = "A", "positive", f"围绕 {top} 行动，不发散"
    elif approved >= 1:
        verdict, tone, impact = "B", "watch", f"主线 {top} 还偏弱，验证后再加注"
    else:
        verdict, tone, impact = "C", "watch", f"主线 {top} 候选不足，仅作观察方向"
    evidence = [f"top_theme={top or '-'}", f"approved={approved}"]
    return {"dim": "main_theme", "title": "主线强度", "verdict": verdict, "tone": tone, "evidence": evidence, "impact": impact}


def _holdings_pressure_dimension(
    watchlist: dict[str, Any] | None,
    confirmation: dict[str, Any] | None,
) -> dict[str, Any]:
    priority = len((watchlist or {}).get("priority_codes") or [])
    counts = (confirmation or {}).get("counts") or {}
    downgraded = int(counts.get("downgraded") or 0)
    if priority >= 3 or downgraded >= 2:
        verdict, tone = "高", "risk"
    elif priority >= 1:
        verdict, tone = "中", "watch"
    else:
        verdict, tone = "低", "positive"
    impact = f"今天先处理 {priority} 个优先持仓" if priority else "持仓压力低，重点看新机会"
    evidence = [f"priority={priority}", f"downgraded={downgraded}"]
    return {"dim": "holdings_pressure", "title": "持仓压力", "verdict": verdict, "tone": tone, "evidence": evidence, "impact": impact}


def _new_quality_dimension(
    confirmation: dict[str, Any] | None,
    screening_batch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    v2_items = _v2_collect_candidates(screening_batch, confirmation)
    if v2_items:
        counts = _v2_counts(v2_items)
        hard_blocked = sum(1 for item in v2_items if _v2_hard_blocked(item))
        actionable = counts.get("actionable") or 0
        trial = counts.get("trial") or 0
        shadow_review = (counts.get("shadow") or 0) + (counts.get("review") or 0)
        if actionable > 0 and hard_blocked == 0:
            verdict, tone = "可执行", "positive"
            impact = "只在触发/失效/硬闸门都复核后允许进入动作"
        elif actionable > 0 or trial > 0:
            verdict, tone = "条件", "watch"
            impact = "有结构假设，但还要等触发、承接或硬闸门放行"
        elif shadow_review > 0:
            verdict, tone = "观察", "watch"
            impact = "只做影子跟踪或人工复核，不直接买"
        else:
            verdict, tone = "弱", "risk"
            impact = "没有可切到动作的结构假设"
        evidence = [
            f"actionable={actionable}",
            f"trial={trial}",
            f"shadow_review={shadow_review}",
            f"hard_gate_blocked={hard_blocked}",
        ]
        ai_counts = _v2_ai_counts(v2_items)
        evidence.append(
            "AI="
            f"采用{ai_counts['used']}/"
            f"影子{ai_counts['shadow_recorded']}/"
            f"fallback{ai_counts['fallback']}/"
            f"未调用{ai_counts['not_requested'] + ai_counts['disabled']}"
        )
        first_missing = next(("；".join(_v2_missing(item)[:2]) for item in v2_items if _v2_missing(item)), "")
        first_block = next((_v2_hard_reason(item) for item in v2_items if _v2_hard_reason(item)), "")
        first_ai = next((_v2_ai_detail(item) for item in v2_items if _v2_ai_detail(item)), "")
        first_calibration = next((_v2_calibration_summary(item) for item in v2_items if _v2_calibration_summary(item)), "")
        if first_block:
            evidence.append(f"不能买={first_block}")
        if first_ai:
            evidence.append(f"AI判读={first_ai}")
        if not first_block and first_calibration:
            evidence.append(f"校准护栏={first_calibration}")
        elif not first_block and first_missing:
            evidence.append(f"还差={first_missing}")
        return {
            "dim": "new_quality",
            "title": "V2 机会质量",
            "verdict": verdict,
            "tone": tone,
            "evidence": evidence,
            "impact": impact,
        }

    counts = (confirmation or {}).get("counts") or {}
    confirmed = int(counts.get("confirmed") or 0)
    fresh = int(counts.get("fresh_candidates") or 0)
    downgraded = int(counts.get("downgraded") or 0)

    if confirmed >= 1 and downgraded == 0:
        verdict, tone = "好", "positive"
    elif confirmed == 0 and fresh > 0:
        verdict, tone = "中", "watch"
    elif confirmed >= 1 and downgraded >= 1:
        verdict, tone = "中", "watch"
    else:
        verdict, tone = "差", "risk"
    impact = "今天 / 明天再决定是否升级到必须处理"
    evidence = [f"confirmed={confirmed}", f"fresh={fresh}", f"downgraded={downgraded}"]
    return {"dim": "new_quality", "title": "新机会质量", "verdict": verdict, "tone": tone, "evidence": evidence, "impact": impact}


# Match A-share 6-digit codes: 60xxxx (SH), 0xxxxx/30xxxx (SZ), 688xxx (STAR), 8xxxxx (BJ).
_STOCK_CODE_PATTERN = re.compile(r"(?<!\d)((?:60|00|30|68|83|87|43|8[02])\d{4})(?!\d)")

_LANE_DEFS = [
    {"key": "must",        "title": "必须处理", "tone": "sell",  "subtitle": "今天闭环这几条，不漂移"},
    {"key": "conditional", "title": "条件触发", "tone": "watch", "subtitle": "有明确触发与失效，达到才动"},
    {"key": "observe",     "title": "只观察",   "tone": "hold",  "subtitle": "今天只看，不动"},
    {"key": "forbid",      "title": "禁止事项", "tone": "risk",  "subtitle": "明确禁线，今天不允许"},
]


def _extract_code(item: dict[str, Any]) -> str | None:
    for source in (item.get("title"), item.get("key"), item.get("code")):
        if not source:
            continue
        match = _STOCK_CODE_PATTERN.search(str(source))
        if match:
            return match.group(1)
    return None


def _extract_name(item: dict[str, Any]) -> str | None:
    title = str(item.get("title") or "")
    name = title
    code = _extract_code(item)
    if code:
        name = title.replace(code, "").strip(" -·")
    return name or None


# Workflow state labels that may appear in ``decision.label`` (e.g.
# "pending", "approved") but are NOT trade-action verbs. Filter them out
# in ``_infer_action_type`` so we fall through to keyword/tone inference.
_WORKFLOW_STATE_LABELS = {"pending", "approved", "rejected", "snoozed", "done", "skipped"}


def _infer_action_type(item: dict[str, Any]) -> str:
    v2_action = _v2_action(item)
    if v2_action:
        if v2_action == "actionable":
            return "可执行复核"
        if v2_action == "trial":
            return "等触发"
        if v2_action == "shadow":
            return "影子跟踪"
        if v2_action == "review":
            return "人工复核"
        return "仅观察"
    explicit = item.get("action_type")
    if not explicit:
        decision_label = (item.get("decision") or {}).get("label")
        if decision_label and str(decision_label).strip().lower() not in _WORKFLOW_STATE_LABELS:
            explicit = decision_label
    if explicit:
        return str(explicit)
    entry_plan = item.get("entry_plan") if isinstance(item.get("entry_plan"), dict) else {}
    text = " ".join(
        str(value or "")
        for value in (
            item.get("title"),
            item.get("status"),
            item.get("detail"),
            item.get("foot"),
            item.get("trigger"),
            entry_plan.get("action"),
            entry_plan.get("trigger"),
            entry_plan.get("sizing"),
        )
    )
    tone = str(item.get("tone") or "")
    if tone == "sell":
        return "减仓"
    if (
        entry_plan.get("trigger")
        or any(token in text for token in ("试错待触发", "突破", "触发", "站回", "回踩", "加观察"))
        or item.get("setup_label")
    ):
        return "等触发"
    if any(token in text for token in ("减仓", "止损", "清仓", "卖出", "降仓", "降低仓位", "退出")):
        return "减仓"
    if tone == "positive":
        return "等突破"
    return "仅观察"


def _normalize_action_item(item: dict[str, Any]) -> dict[str, Any]:
    code = _extract_code(item)
    name = _extract_name(item)
    entry_plan = item.get("entry_plan") if isinstance(item.get("entry_plan"), dict) else {}
    levels = entry_plan.get("levels") if isinstance(entry_plan.get("levels"), dict) else {}
    missing = _v2_missing(item)
    hard_reason = _v2_hard_reason(item)
    trigger = (
        entry_plan.get("trigger")
        or item.get("trigger")
        or item.get("upgrade_condition")
        or item.get("setup_label")
        or levels.get("trigger")
        or levels.get("pullback")
        or item.get("support")
        or item.get("resistance")
    )
    invalidate = (
        item.get("invalidation")
        or entry_plan.get("invalidate")
        or levels.get("invalidate")
        or item.get("invalidate_when")
        or item.get("stop_loss")
        or item.get("failure_condition")
    )
    reason = str(item.get("thesis") or item.get("why_now") or item.get("detail") or item.get("foot") or item.get("source") or "")
    rank_label = str(item.get("decision_rank_label") or "").strip()
    summary = str(item.get("decision_summary") or "").strip()
    if rank_label and rank_label not in reason:
        reason = f"{rank_label} · {reason}" if reason else rank_label
    if summary and summary not in reason:
        reason = f"{reason} · {summary}" if reason else summary
    if hard_reason and f"不能买：{hard_reason}" not in reason:
        reason = f"{reason} · 不能买：{hard_reason}" if reason else f"不能买：{hard_reason}"
    elif missing:
        missing_text = "；".join(missing[:2])
        if missing_text and missing_text not in reason:
            reason = f"{reason} · 还差：{missing_text}" if reason else f"还差：{missing_text}"
    calibration = _v2_calibration_summary(item)
    if calibration and calibration not in reason:
        reason = f"{reason} · 校准护栏：{calibration}" if reason else f"校准护栏：{calibration}"
    ai_detail = _v2_ai_detail(item)
    if ai_detail and ai_detail not in reason:
        reason = f"{reason} · AI：{ai_detail}" if reason else f"AI：{ai_detail}"
    return {
        "key": str(item.get("key") or ""),
        "code": code,
        "name": name,
        "action_type": _infer_action_type(item),
        "reason": reason,
        "trigger": str(trigger or "无明确触发"),
        "invalidate_when": str(invalidate or "-"),
        "source": str(item.get("source") or item.get("group_title") or ""),
        "url": item.get("url") or None,
        "tone": str(item.get("tone") or "watch"),
        "suggested_action": _v2_action(item),
        "suggested_action_label": _v2_label(item),
        "confidence": item.get("confidence") if item.get("confidence") is not None else _v2_judgment(item).get("confidence"),
        "thesis": item.get("thesis") or _v2_judgment(item).get("thesis") or "",
        "why_now": item.get("why_now") or _v2_judgment(item).get("why_now") or "",
        "missing_confirmation": missing,
        "hard_gate_max_action": _v2_hard_max(item),
        "hard_gate_block_reason": hard_reason,
        "decision_rank": item.get("decision_rank"),
        "decision_rank_label": item.get("decision_rank_label"),
        "decision_summary": item.get("decision_summary"),
        "judge_source": item.get("judge_source") or _v2_judgment(item).get("judge_source"),
        "ai_status": _v2_ai_status(item),
        "ai_status_label": _v2_ai_label(item),
        "ai_summary": _v2_ai_summary(item),
    }


def _has_explicit_trigger(item: dict[str, Any]) -> bool:
    entry_plan = item.get("entry_plan") if isinstance(item.get("entry_plan"), dict) else {}
    levels = entry_plan.get("levels") if isinstance(entry_plan.get("levels"), dict) else {}
    if _v2_action(item) in {"review", "shadow", "observe"}:
        return False
    return bool(
        entry_plan.get("trigger")
        or item.get("trigger")
        or item.get("upgrade_condition")
        or item.get("setup_label")
        or item.get("breakout_price")
        or item.get("stop_loss")
        or levels.get("trigger")
        or levels.get("pullback")
    )


def derive_action_lanes(
    *,
    mode_value: str,
    action_groups: list[dict[str, Any]],
    decision_brief: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    grouped = {str(g.get("key") or ""): (g.get("items") or []) for g in (action_groups or [])}
    do_now = grouped.get("do-now") or []
    watch = grouped.get("watch") or []
    avoid = grouped.get("avoid") or []

    must_items: list[dict[str, Any]] = []
    conditional_items: list[dict[str, Any]] = []
    observe_items: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    def add(items: list[dict[str, Any]], raw: dict[str, Any]) -> None:
        key = str(raw.get("key") or "")
        if key and key in seen_keys:
            return
        seen_keys.add(key)
        items.append(_normalize_action_item(raw))

    def add_v2_or_fallback(raw: dict[str, Any], *, default: str) -> bool:
        v2_action = _v2_action(raw)
        if not v2_action:
            return False
        if v2_action == "actionable":
            add(must_items, raw)
        elif v2_action == "trial":
            add(conditional_items, raw)
        else:
            add(observe_items, raw)
        return True

    for raw in do_now:
        if add_v2_or_fallback(raw, default="must"):
            continue
        tone = str(raw.get("tone") or "")
        if tone == "sell":
            add(must_items, raw)
        elif _has_explicit_trigger(raw):
            add(conditional_items, raw)
        elif tone == "positive":
            add(must_items, raw)
        else:
            add(must_items, raw)

    for raw in watch:
        if add_v2_or_fallback(raw, default="observe"):
            continue
        if _has_explicit_trigger(raw):
            add(conditional_items, raw)
        else:
            add(observe_items, raw)

    forbid_items = derive_forbid_today(
        mode_value=mode_value,
        decision_brief=decision_brief,
        action_groups=[{"key": "avoid", "items": avoid}],
    )

    if not (must_items or conditional_items):
        must_items.append({
            "key": "system:review-holdings-first",
            "code": None,
            "name": "先复核优先持仓",
            "action_type": "复核",
            "reason": "当前没有强动作票，先把持仓边界过一遍。",
            "trigger": "无明确触发",
            "invalidate_when": "-",
            "source": "command_brief",
            "url": "/portfolio",
            "tone": "watch",
        })

    lanes = []
    payload = {
        "must": must_items[:5],
        "conditional": conditional_items[:5],
        "observe": observe_items[:5],
        "forbid": forbid_items[:4],
    }
    for definition in _LANE_DEFS:
        lanes.append({**definition, "items": payload[definition["key"]]})
    return lanes


def _confirmation_card(item: dict[str, Any]) -> dict[str, Any]:
    code = _extract_code(item) or str(item.get("code") or "")
    name = _extract_name(item) or str(item.get("name") or item.get("title") or "")
    return {
        "name": name,
        "code": code,
        "reason": str(item.get("reason") or item.get("detail") or item.get("status") or ""),
        "url": str(item.get("detail_url") or item.get("url") or ""),
        "tone": str(item.get("tone") or "watch"),
    }


def derive_midday_verify(
    *,
    confirmation: dict[str, Any] | None,
    screening_batch: dict[str, Any] | None,
    decision_brief: dict[str, Any] | None,
    mode_value: str,
) -> dict[str, Any]:
    if not confirmation:
        return {
            "available": False,
            "morning_takeaway": "早盘结论暂未生成",
            "midday_status": "午盘验证尚未到位，当前不输出改判结论",
            "fresh_candidates": [],
            "downgraded": [],
            "next_day_condition": "",
            "verified_at": "",
        }

    counts = confirmation.get("counts") or {}
    confirmed = int(counts.get("confirmed") or 0)
    fresh = int(counts.get("fresh_candidates") or 0)
    downgraded = int(counts.get("downgraded") or 0)
    validation = str(confirmation.get("validation_status") or "ok").strip().lower()
    validation_errors = [
        str(item).strip()
        for item in (confirmation.get("validation_errors") or [])
        if str(item).strip()
    ]
    runner_status = str(confirmation.get("runner_status") or "").strip().lower()
    failure_statuses = {"failed", "invalid", "quality_blocked", "scan_failed", "verify_failed", "workflow_failed"}
    validation_label = {
        "ok": "午盘已确认",
        "verify_failed": "午盘确认执行失败",
        "invalid": "午盘链路无效",
        "failed": "午盘链路失败",
        "workflow_failed": "午盘链路失败",
        "quality_blocked": "午盘确认质检拦截",
        "scan_failed": "午盘扫描失败",
        "unknown": "午盘待核",
    }.get(validation, validation or "午盘待核")
    if validation in failure_statuses or runner_status == "failed" or validation_errors:
        reason = validation_errors[0] if validation_errors else "请查看午盘确认任务日志"
        midday_status = f"{validation_label}：{reason}，请重跑午盘确认"
    elif validation == "ok" and confirmed == 0 and fresh == 0:
        midday_status = "午盘已确认：确认 0 · 新增 0，今天不触发买入"
    else:
        midday_status = f"{validation_label}：确认 {confirmed} · 新增 {fresh} · 降级 {downgraded}"

    morning = (
        ((decision_brief or {}).get("summary") or {}).get("gate_summary")
        or ((screening_batch or {}).get("screening_summary") or {}).get("execution_gate_status")
        or "早盘结论暂未生成"
    )

    fresh_cards = [_confirmation_card(item) for item in (confirmation.get("fresh_candidates") or [])[:3]]
    down_cards = [_confirmation_card(item) for item in (confirmation.get("downgraded") or [])[:3]]

    next_day = str(confirmation.get("next_day_focus") or "").strip()
    if not next_day:
        if mode_value == "probe":
            next_day = "若 fresh_candidates 隔日仍站住主线，明日可进观察"
        elif mode_value == "offense":
            next_day = "若 confirmed 持续两日，明日扩展到必须处理"
        elif mode_value == "observe":
            next_day = "若主线强度回到 B 以上，明日转试探"
        else:
            next_day = "等数据回到 live_ready 再讨论"

    return {
        "available": True,
        "morning_takeaway": str(morning),
        "midday_status": midday_status,
        "fresh_candidates": fresh_cards,
        "downgraded": down_cards,
        "next_day_condition": next_day,
        "verified_at": str(confirmation.get("generated_at") or ""),
    }


def derive_trust(
    *,
    readiness: dict[str, Any],
    refresh_status: dict[str, Any] | None,
) -> dict[str, Any]:
    src = readiness.get("source_freshness") or []
    src_ok = sum(1 for item in src if item.get("timely"))
    quality = readiness.get("quality_freshness") or []
    q_ok = sum(1 for item in quality if item.get("timely"))
    auto_summary = ""
    if refresh_status and isinstance(refresh_status, dict):
        decision = refresh_status.get("auto_refresh") or {}
        auto_summary = str(decision.get("summary") or "")
    return {
        "readiness_mode": str(readiness.get("readiness_mode") or "blocked"),
        "source_summary": f"{src_ok}/{len(src)} timely",
        "quality_summary": f"{q_ok}/{len(quality)} ok",
        "blockers_count": len(readiness.get("blockers") or []),
        "warnings_count": len(readiness.get("warnings") or []),
        "auto_refresh_summary": auto_summary,
    }


def build_today_command_brief(
    *,
    trade_date: str,
    readiness: dict[str, Any],
    gate: dict[str, Any],
    decision_brief: dict[str, Any] | None,
    watchlist: dict[str, Any] | None,
    screening_batch: dict[str, Any] | None,
    confirmation: dict[str, Any] | None,
    action_groups: list[dict[str, Any]],
    action_queue: dict[str, Any],
    refresh_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    errors: dict[str, str] = {}

    def _section(name: str, builder, fallback):
        try:
            return builder()
        except Exception as exc:  # fail-soft per section
            errors[name] = str(exc)
            return fallback

    mode = _section(
        "mode",
        lambda: derive_mode(readiness=readiness, gate=gate, confirmation=confirmation, decision_brief=decision_brief),
        {"value": "defense", "label": "防守", "tone": "risk", "summary": "派生失败，回退到默认防守模式。", "reasons": ["error"]},
    )
    mode_value = str(mode.get("value") or "defense")

    permits = _section(
        "permits",
        lambda: derive_permits(readiness=readiness, gate=gate, confirmation=confirmation, screening_batch=screening_batch),
        {
            "data":        {"value": "off", "label": "未就绪", "tone": "risk", "why": "派生失败"},
            "market":      {"value": "off", "label": "进攻阀门关闭", "tone": "risk", "why": "派生失败"},
            "opportunity": {"value": "none", "label": "今天不输出机会判断", "tone": "risk", "why": "派生失败"},
        },
    )
    position_cap = _section(
        "position_cap",
        lambda: derive_position_cap(mode_value=mode_value, gate=gate, decision_brief=decision_brief),
        {"value": "0成", "raw": "0成", "tone": "risk", "note": "派生失败，默认不开新仓。"},
    )
    first_action = _section(
        "first_action",
        lambda: derive_first_action(mode_value=mode_value, action_queue=action_queue, readiness=readiness),
        {"title": "先恢复数据链路", "reason": "派生失败", "url": "/settings", "action_key": None, "tone": "risk", "kind": "recover_data"},
    )
    forbid = _section(
        "forbid_today",
        lambda: derive_forbid_today(mode_value=mode_value, decision_brief=decision_brief, action_groups=action_groups),
        [{"title": "派生失败，今天不动", "reason": "command_brief 派生异常", "tone": "risk", "source": "fallback"}],
    )
    reclassify = _section(
        "reclassify_when",
        lambda: derive_reclassify_when(mode_value=mode_value, readiness=readiness, gate=gate),
        [],
    )
    chain = _section(
        "judgement_chain",
        lambda: derive_judgement_chain(readiness=readiness, gate=gate, watchlist=watchlist, screening_batch=screening_batch, confirmation=confirmation),
        [
            {"dim": "market", "title": "市场环境", "verdict": "派生失败", "tone": "risk", "evidence": ["command_brief 派生异常"], "impact": "暂不展示判断"},
            {"dim": "main_theme", "title": "主线强度", "verdict": "派生失败", "tone": "risk", "evidence": ["command_brief 派生异常"], "impact": "暂不展示判断"},
            {"dim": "holdings_pressure", "title": "持仓压力", "verdict": "派生失败", "tone": "risk", "evidence": ["command_brief 派生异常"], "impact": "暂不展示判断"},
            {"dim": "new_quality", "title": "新机会质量", "verdict": "派生失败", "tone": "risk", "evidence": ["command_brief 派生异常"], "impact": "暂不展示判断"},
        ],
    )
    lanes = _section(
        "action_lanes",
        lambda: derive_action_lanes(mode_value=mode_value, action_groups=action_groups, decision_brief=decision_brief),
        [
            {"key": "must",        "title": "必须处理", "tone": "sell",  "subtitle": "派生失败", "items": []},
            {"key": "conditional", "title": "条件触发", "tone": "watch", "subtitle": "派生失败", "items": []},
            {"key": "observe",     "title": "只观察",   "tone": "hold",  "subtitle": "派生失败", "items": []},
            {"key": "forbid",      "title": "禁止事项", "tone": "risk",  "subtitle": "派生失败", "items": []},
        ],
    )
    midday = _section(
        "midday_verify",
        lambda: derive_midday_verify(confirmation=confirmation, screening_batch=screening_batch, decision_brief=decision_brief, mode_value=mode_value),
        {
            "available": False,
            "morning_takeaway": "派生失败",
            "midday_status": "command_brief 派生异常，午盘改判暂不可用",
            "fresh_candidates": [],
            "downgraded": [],
            "next_day_condition": "",
            "verified_at": "",
        },
    )
    trust = _section(
        "trust",
        lambda: derive_trust(readiness=readiness, refresh_status=refresh_status),
        {
            "readiness_mode": str(readiness.get("readiness_mode") or "blocked"),
            "source_summary": "-",
            "quality_summary": "-",
            "blockers_count": 0,
            "warnings_count": 0,
            "auto_refresh_summary": "",
        },
    )

    return {
        "trade_date": trade_date,
        "generated_at": _dt.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": mode,
        "permits": permits,
        "position_cap": position_cap,
        "first_action": first_action,
        "forbid_today": forbid,
        "reclassify_when": reclassify,
        "judgement_chain": chain,
        "action_lanes": lanes,
        "midday_verify": midday,
        "trust": trust,
        "errors": errors,
    }
