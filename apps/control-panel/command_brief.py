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
    if value in {"shadow", "limited", "observe", "conditional"}:
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
    if mode_value == "defense":
        raw, value = _DEFENSE_POSITION_CAP, _DEFENSE_POSITION_CAP
    else:
        brief_cap = ((decision_brief or {}).get("summary") or {}).get("position_cap")
        gate_cap = gate.get("position_cap")
        raw = str(brief_cap or gate_cap or _DEFAULT_POSITION_CAPS[mode_value])
        value = raw
    note = _POSITION_CAP_NOTES.get(mode_value, "按仓位纪律执行。")
    tone = "risk" if mode_value == "defense" else "watch" if mode_value in {"observe", "probe"} else "positive"
    return {"value": value, "raw": raw, "tone": tone, "note": note}


def derive_first_action(
    *,
    mode_value: str,
    action_queue: dict[str, Any],
    readiness: dict[str, Any],
) -> dict[str, Any]:
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
    pending = [
        item for item in items
        if str(((item or {}).get("display_state") or {}).get("value") or item.get("decision", {}).get("value") or "pending") == "pending"
    ]
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
        _new_quality_dimension(confirmation),
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


def _new_quality_dimension(confirmation: dict[str, Any] | None) -> dict[str, Any]:
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


_STOCK_CODE_PATTERN = re.compile(r"\b(\d{6})\b")

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


_WORKFLOW_STATE_LABELS = {"pending", "approved", "rejected", "snoozed", "done", "skipped"}


def _infer_action_type(item: dict[str, Any]) -> str:
    explicit = item.get("action_type")
    if not explicit:
        decision_label = (item.get("decision") or {}).get("label")
        if decision_label and str(decision_label).strip().lower() not in _WORKFLOW_STATE_LABELS:
            explicit = decision_label
    if explicit:
        return str(explicit)
    text = str(item.get("title") or "") + " " + str(item.get("detail") or "")
    if any(token in text for token in ("减仓", "止损", "清仓", "卖", "降")):
        return "减仓"
    if item.get("setup_label") or any(token in text for token in ("突破", "触发", "加观察")):
        return "等触发"
    tone = str(item.get("tone") or "")
    if tone == "sell":
        return "减仓"
    if tone == "positive":
        return "等突破"
    return "仅观察"


def _normalize_action_item(item: dict[str, Any]) -> dict[str, Any]:
    code = _extract_code(item)
    name = _extract_name(item)
    trigger = (
        item.get("trigger")
        or item.get("setup_label")
        or item.get("support")
        or item.get("resistance")
    )
    invalidate = item.get("invalidate_when") or item.get("stop_loss") or item.get("failure_condition")
    return {
        "key": str(item.get("key") or ""),
        "code": code,
        "name": name,
        "action_type": _infer_action_type(item),
        "reason": str(item.get("detail") or item.get("foot") or item.get("source") or ""),
        "trigger": str(trigger or "无明确触发"),
        "invalidate_when": str(invalidate or "-"),
        "source": str(item.get("source") or item.get("group_title") or ""),
        "url": item.get("url") or None,
        "tone": str(item.get("tone") or "watch"),
    }


def _has_explicit_trigger(item: dict[str, Any]) -> bool:
    return bool(item.get("setup_label") or item.get("breakout_price") or item.get("stop_loss"))


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

    for raw in do_now:
        tone = str(raw.get("tone") or "")
        if tone in {"sell", "positive"}:
            add(must_items, raw)
        elif _has_explicit_trigger(raw):
            add(conditional_items, raw)
        else:
            add(must_items, raw)

    for raw in watch:
        if _has_explicit_trigger(raw):
            add(conditional_items, raw)
        else:
            add(observe_items, raw)

    forbid_items = derive_forbid_today(
        mode_value=mode_value,
        decision_brief=decision_brief,
        action_groups=[{"key": "avoid", "items": avoid}],
    )

    if not (must_items or conditional_items or forbid_items):
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
