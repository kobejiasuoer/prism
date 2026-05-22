"""Daily command brief aggregator.

Pure-derivation helpers used by ``dashboard_data.build_today_view`` to
project existing today-view inputs (readiness, gate, decision_brief,
watchlist, screening, confirmation, action_groups, action_queue) into the
5-section command brief defined in
``docs/superpowers/specs/2026-05-22-daily-command-brief-design.md``.

All functions in this module are side-effect free and accept plain dicts.
"""

from __future__ import annotations

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


def _label_kind(label: str) -> str:
    text = label or ""
    if any(token in text for token in _LIMITED_LABEL_KEYWORDS):
        return "limited"
    if any(token in text for token in _OFFENSE_LABEL_KEYWORDS):
        return "offense"
    return "other"


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

    if data_value == "off":
        opp_value = "none"
        opp_label = "今天不输出机会判断"
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

    return {
        "data":        {"value": data_value, "label": data_label, "tone": _permit_tone(data_value, "data"), "why": data_why},
        "market":      {"value": market_value, "label": market_label, "tone": _permit_tone(market_value, "market"), "why": market_why},
        "opportunity": {"value": opp_value, "label": opp_label, "tone": _permit_tone(opp_value, "opportunity"), "why": opp_why},
    }


def _readiness_why(readiness: dict[str, Any]) -> str:
    blockers = readiness.get("blockers") or []
    if blockers:
        return str(blockers[0].get("message") or "数据未对齐当日")
    warnings = readiness.get("warnings") or []
    if warnings:
        return str(warnings[0].get("message") or "数据存在告警")
    return "数据已对齐当日"


def _permit_tone(value: str, kind: str) -> str:
    if value in {"off", "none"}:
        return "risk"
    if value in {"shadow", "limited", "observe", "conditional"}:
        return "watch"
    if value in {"on", "actionable"}:
        return "positive"
    return "watch"
