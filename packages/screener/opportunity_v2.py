#!/usr/bin/env python3
"""Prism opportunity judgment V2.

V2 separates opportunity semantics from hard execution gates:

* the baseline judge forms a structural thesis from market phase, theme
  phase, stock role, playbook, validation, and risk/reward;
* the hard gate only caps the maximum allowed action;
* an optional OpenAI-compatible judge can refine the structure, but the
  final action is always capped by deterministic hard gates.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

try:
    from screener.capital_flow_contract import UNIT_YUAN, capital_flow_today_yi
except ModuleNotFoundError:
    from capital_flow_contract import UNIT_YUAN, capital_flow_today_yi


ACTION_ORDER = {
    "observe": 0,
    "review": 1,
    "shadow": 2,
    "trial": 3,
    "actionable": 4,
}
ACTION_LABELS = {
    "observe": "只观察",
    "review": "人工复核",
    "shadow": "影子跟踪",
    "trial": "试错待触发",
    "actionable": "可执行待复核",
}
AI_STATUS_LABELS = {
    "disabled": "AI 已关闭，使用 deterministic baseline",
    "not_requested": "AI 未调用，使用 deterministic baseline",
    "not_configured": "AI 未配置，fallback 到 deterministic baseline",
    "fallback": "AI 调用失败，fallback 到 deterministic baseline",
    "shadow_recorded": "AI 影子判读已记录，未接管动作",
    "used": "AI Judge 已参与结构判读",
}
MODE_VALUES = {"off", "shadow", "assist", "active"}
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CALIBRATION_PATH = WORKSPACE_ROOT / "data" / "runtime" / "opportunity_v2_calibration.json"
DEFAULT_RULES: dict[str, Any] = {
    "mode": "assist",
    "ai": {
        "enabled": True,
        "max_calls": 3,
        "timeout_seconds": 12,
    },
    "confidence_weights": {
        "clarity": 0.30,
        "behavior": 0.24,
        "role": 0.22,
        "theme": 0.14,
        "risk_reward": 0.10,
    },
    "confidence_thresholds": {
        "review": 0.38,
        "shadow": 0.52,
        "trial": 0.66,
        "actionable": 0.80,
    },
    "hard_gate_caps": {
        "gate_off": "shadow",
        "gate_limited_allowed": "trial",
        "gate_limited_disallowed": "shadow",
        "risk_degrade": "trial",
        "risk_block": "shadow",
        "readiness_blocked": "observe",
        "readiness_shadow": "shadow",
        "no_trade_permission": "shadow",
        "position_cap_zero": "shadow",
        "midday_failed": "observe",
    },
    "calibration": {
        "enabled": True,
        "path": "data/runtime/opportunity_v2_calibration.json",
        "min_mature_samples": 8,
        "min_playbook_samples": 3,
        "min_positive_rate_for_active": 0.52,
        "max_review_rate_for_active": 0.35,
        "active_requires_calibration": True,
        "cold_start_threshold_bump": {
            "trial": 0.06,
            "actionable": 0.10,
        },
        "conservative_threshold_bump": {
            "trial": 0.04,
            "actionable": 0.07,
        },
        "weak_playbook_penalty": -0.06,
        "weak_playbook_action_cap": "shadow",
    },
    "playbook_adjustments": {},
}


def safe_float(value: Any, default: float | None = 0.0) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def unique_keep_order(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if isinstance(value, list):
            nested = unique_keep_order(value)
            for item in nested:
                if item not in seen:
                    seen.add(item)
                    out.append(item)
            continue
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _compact_text(value: Any, limit: int = 96) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text if len(text) <= limit else f"{text[:limit]}..."


def _nested_value(payload: Mapping[str, Any], key: str, field: str = "value") -> str:
    value = payload.get(key)
    if isinstance(value, Mapping):
        return str(value.get(field) or value.get("label") or "").strip()
    return str(value or "").strip()


def _risk_level(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if isinstance(value, Mapping):
        return str(value.get("level") or value.get("summary") or "").strip()
    return str(value or "").strip()


def ai_delta_from_baseline(baseline: Mapping[str, Any], judgment: Mapping[str, Any]) -> dict[str, Any]:
    """Describe how AI changed the deterministic baseline, if at all."""

    changes: list[dict[str, Any]] = []

    def add_change(field: str, before: Any, after: Any) -> None:
        before_text = _compact_text(before)
        after_text = _compact_text(after)
        if before_text == after_text:
            return
        changes.append({"field": field, "before": before_text, "after": after_text})

    add_change("suggested_action", baseline.get("suggested_action"), judgment.get("suggested_action"))
    add_change("desired_action", baseline.get("desired_action"), judgment.get("desired_action"))
    add_change("confidence", baseline.get("confidence"), judgment.get("confidence"))
    add_change("playbook", _nested_value(baseline, "playbook"), _nested_value(judgment, "playbook"))
    add_change("stock_role", _nested_value(baseline, "stock_role"), _nested_value(judgment, "stock_role"))
    add_change("thesis", baseline.get("thesis"), judgment.get("thesis"))
    add_change("why_now", baseline.get("why_now"), judgment.get("why_now"))
    add_change("crowding_risk", _risk_level(baseline, "crowding_risk"), _risk_level(judgment, "crowding_risk"))
    add_change("fake_breakout_risk", _risk_level(baseline, "fake_breakout_risk"), _risk_level(judgment, "fake_breakout_risk"))

    return {
        "changed": bool(changes),
        "changes": changes[:8],
        "changed_fields": [str(change.get("field")) for change in changes[:8]],
    }


def ai_summary_for_judgment(
    judgment: Mapping[str, Any],
    *,
    baseline: Mapping[str, Any] | None = None,
    meta: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    status = str(judgment.get("ai_status") or (meta or {}).get("status") or "not_requested").strip()
    provider = str((meta or {}).get("provider") or judgment.get("ai_provider") or "").strip()
    model = str((meta or {}).get("model") or judgment.get("ai_model") or "").strip()
    error = str((meta or {}).get("error") or judgment.get("ai_error") or "").strip()
    label = AI_STATUS_LABELS.get(status, f"AI 状态：{status}")
    delta = ai_delta_from_baseline(baseline, judgment) if baseline is not None else {}

    if status == "used":
        detail = "AI 已复核结构、风险和动作语义；最终动作仍受 hard gate 封顶。"
        if delta.get("changed"):
            fields = "、".join(str(field) for field in (delta.get("changed_fields") or [])[:4])
            detail = f"AI 改写/确认了 {fields}；最终动作仍受 hard gate 封顶。"
    elif status == "shadow_recorded":
        detail = "AI 只做影子判读记录，本次页面仍展示 baseline 动作。"
        if delta.get("changed"):
            fields = "、".join(str(field) for field in (delta.get("changed_fields") or [])[:4])
            detail = f"AI 影子判读与 baseline 在 {fields} 上有差异，先进入复盘样本。"
    elif status == "not_configured":
        detail = "缺少 provider/key/model，V2 自动使用 deterministic baseline。"
    elif status == "fallback":
        detail = f"AI 返回异常，V2 自动 fallback 到 deterministic baseline。{error}" if error else "AI 返回异常，V2 自动 fallback 到 deterministic baseline。"
    elif status == "disabled":
        detail = "配置关闭 AI，V2 只使用 deterministic baseline。"
    elif status == "not_requested":
        detail = "本轮没有消耗 AI 调用预算，V2 只使用 deterministic baseline。"
    else:
        detail = label

    return {
        "status": status,
        "label": label,
        "detail": detail,
        "provider": provider,
        "model": model,
        "error": error,
        "delta": delta,
        "used": status == "used",
        "fallback_used": status in {"not_configured", "fallback"},
    }


def merge_rules(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    rules = deepcopy(DEFAULT_RULES)
    if not isinstance(raw, Mapping):
        return rules
    for key, value in raw.items():
        if isinstance(value, Mapping) and isinstance(rules.get(key), Mapping):
            rules[key].update(value)
        else:
            rules[key] = value
    return rules


def calibration_path(rules: Mapping[str, Any] | None = None) -> Path:
    env_path = os.environ.get("PRISM_V2_CALIBRATION_PATH", "").strip()
    calibration_rules = (rules or {}).get("calibration") if isinstance((rules or {}).get("calibration"), Mapping) else {}
    raw_path = env_path or str(calibration_rules.get("path") or DEFAULT_RULES["calibration"]["path"])
    path = Path(raw_path).expanduser()
    return path if path.is_absolute() else WORKSPACE_ROOT / path


def _default_threshold_adjustments(rules: Mapping[str, Any], *, cold_start: bool) -> dict[str, float]:
    calibration_rules = rules.get("calibration") if isinstance(rules.get("calibration"), Mapping) else {}
    key = "cold_start_threshold_bump" if cold_start else "conservative_threshold_bump"
    raw = calibration_rules.get(key) if isinstance(calibration_rules.get(key), Mapping) else {}
    return {
        action: float(safe_float(value, 0.0) or 0.0)
        for action, value in raw.items()
        if action in ACTION_ORDER and safe_float(value, None) is not None
    }


def _cold_start_calibration(
    rules: Mapping[str, Any],
    *,
    path: Path,
    reason: str,
    error: str = "",
) -> dict[str, Any]:
    return {
        "schema_version": "opportunity_v2_calibration.1",
        "enabled": True,
        "loaded": False,
        "path": str(path),
        "sample_stage": "cold_start",
        "sample_count": 0,
        "mature_samples": 0,
        "pending_outcome": 0,
        "active_allowed": False,
        "guard_reason": reason,
        "threshold_adjustments": _default_threshold_adjustments(rules, cold_start=True),
        "playbooks": {},
        "source": "deterministic_cold_start",
        **({"error": error[:240]} if error else {}),
    }


def load_calibration(rules: Mapping[str, Any] | None = None) -> dict[str, Any]:
    rules = merge_rules(rules)
    calibration_rules = rules.get("calibration") if isinstance(rules.get("calibration"), Mapping) else {}
    enabled = bool(calibration_rules.get("enabled", True))
    path = calibration_path(rules)
    if not enabled:
        return {
            "schema_version": "opportunity_v2_calibration.1",
            "enabled": False,
            "loaded": False,
            "path": str(path),
            "sample_stage": "disabled",
            "active_allowed": True,
            "guard_reason": "V2 calibration disabled by config.",
            "threshold_adjustments": {},
            "playbooks": {},
            "source": "config_disabled",
        }
    if not path.exists():
        return _cold_start_calibration(
            rules,
            path=path,
            reason="校准快照不存在，V2 active 先降级为 assist，并临时抬高 trial/actionable 阈值。",
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _cold_start_calibration(
            rules,
            path=path,
            reason="校准快照不可读，V2 active 先降级为 assist。",
            error=str(exc),
        )
    if not isinstance(payload, Mapping):
        return _cold_start_calibration(
            rules,
            path=path,
            reason="校准快照格式无效，V2 active 先降级为 assist。",
            error="payload is not an object",
        )
    calibration = dict(payload)
    calibration["enabled"] = True
    calibration["loaded"] = True
    calibration["path"] = str(path)
    calibration.setdefault("schema_version", "opportunity_v2_calibration.1")
    calibration.setdefault("sample_stage", "unknown")
    calibration.setdefault("sample_count", 0)
    calibration.setdefault("mature_samples", 0)
    calibration.setdefault("pending_outcome", 0)
    calibration.setdefault("active_allowed", False)
    calibration.setdefault("guard_reason", "校准快照未明确允许 active。")
    if not isinstance(calibration.get("threshold_adjustments"), Mapping):
        calibration["threshold_adjustments"] = (
            {}
            if calibration.get("active_allowed")
            else _default_threshold_adjustments(rules, cold_start=False)
        )
    if not isinstance(calibration.get("playbooks"), Mapping):
        calibration["playbooks"] = {}
    return calibration


def resolve_mode(rules: Mapping[str, Any] | None = None) -> str:
    env_mode = os.environ.get("PRISM_V2_MODE", "").strip().lower()
    mode = env_mode or str((rules or {}).get("mode") or DEFAULT_RULES["mode"]).strip().lower()
    return mode if mode in MODE_VALUES else str(DEFAULT_RULES["mode"])


def _mode_guard(requested_mode: str, rules: Mapping[str, Any], calibration: Mapping[str, Any]) -> dict[str, Any]:
    calibration_rules = rules.get("calibration") if isinstance(rules.get("calibration"), Mapping) else {}
    requires_calibration = bool(calibration_rules.get("active_requires_calibration", True))
    active_allowed = bool(calibration.get("active_allowed", False)) or not requires_calibration or not calibration.get("enabled", True)
    effective_mode = requested_mode
    guard_reason = str(calibration.get("guard_reason") or "")
    if requested_mode == "active" and not active_allowed:
        effective_mode = "assist"
        guard_reason = guard_reason or "V2 outcome 样本未达到 active 准入，暂按 assist 执行。"
    return {
        "requested_mode": requested_mode,
        "effective_mode": effective_mode,
        "active_allowed": active_allowed,
        "guard_reason": guard_reason,
        "sample_stage": calibration.get("sample_stage") or "",
        "mature_samples": calibration.get("mature_samples") or 0,
        "min_mature_samples": calibration_rules.get("min_mature_samples"),
    }


def _with_calibration_applied(rules: Mapping[str, Any] | None = None) -> dict[str, Any]:
    raw_rules = merge_rules(rules)
    if raw_rules.get("__calibration_applied"):
        return raw_rules

    calibration = load_calibration(raw_rules)
    effective = deepcopy(raw_rules)
    thresholds = dict(effective.get("confidence_thresholds") or {})
    adjustments = calibration.get("threshold_adjustments") if isinstance(calibration.get("threshold_adjustments"), Mapping) else {}
    normalized_adjustments: dict[str, float] = {}
    for action, adjustment in adjustments.items():
        if action not in ACTION_ORDER:
            continue
        number = safe_float(adjustment, None)
        if number is None:
            continue
        normalized_adjustments[action] = round(float(number), 4)
        thresholds[action] = round(clamp(float(thresholds.get(action, 0.0)) + float(number), 0.0, 1.0), 4)

    # Keep the threshold ladder monotonic after runtime bumps.
    thresholds["shadow"] = max(float(thresholds.get("shadow", 0.52)), float(thresholds.get("review", 0.38)))
    thresholds["trial"] = max(float(thresholds.get("trial", 0.66)), float(thresholds.get("shadow", 0.52)))
    thresholds["actionable"] = max(float(thresholds.get("actionable", 0.80)), float(thresholds.get("trial", 0.66)))
    effective["confidence_thresholds"] = thresholds

    playbooks = calibration.get("playbooks") if isinstance(calibration.get("playbooks"), Mapping) else {}
    playbook_adjustments = dict(effective.get("playbook_adjustments") or {})
    for playbook, raw in playbooks.items():
        if not isinstance(raw, Mapping):
            continue
        adjustment: dict[str, Any] = {}
        confidence_adjustment = safe_float(raw.get("confidence_adjustment"), None)
        if confidence_adjustment is not None:
            adjustment["confidence_adjustment"] = round(float(confidence_adjustment), 4)
        action_cap = str(raw.get("action_cap") or "").strip()
        if action_cap in ACTION_ORDER:
            adjustment["action_cap"] = action_cap
        if raw.get("reason"):
            adjustment["reason"] = str(raw.get("reason") or "")
        for key in ("sample_count", "mature_samples", "positive_rate", "review_rate", "outcomes"):
            if key in raw:
                adjustment[key] = raw.get(key)
        if adjustment:
            playbook_adjustments[str(playbook)] = adjustment
    effective["playbook_adjustments"] = playbook_adjustments

    requested_mode = resolve_mode(raw_rules)
    guard = _mode_guard(requested_mode, effective, calibration)
    effective["mode"] = guard["effective_mode"]
    effective["__requested_mode"] = requested_mode
    effective["__mode_guard"] = guard
    effective["__calibration"] = calibration
    effective["__threshold_adjustments"] = normalized_adjustments
    effective["__calibration_applied"] = True
    return effective


def resolve_effective_mode(rules: Mapping[str, Any] | None = None) -> str:
    effective = _with_calibration_applied(rules)
    mode = str(effective.get("mode") or DEFAULT_RULES["mode"]).strip().lower()
    return mode if mode in MODE_VALUES else str(DEFAULT_RULES["mode"])


def action_rank(action: Any) -> int:
    return ACTION_ORDER.get(str(action or "").strip(), 0)


def cap_action(action: str, max_allowed: str) -> str:
    if action_rank(action) <= action_rank(max_allowed):
        return action
    return max_allowed if max_allowed in ACTION_ORDER else "observe"


def action_from_confidence(confidence: float, rules: Mapping[str, Any], missing_count: int, risk_level: str) -> str:
    thresholds = rules.get("confidence_thresholds") if isinstance(rules.get("confidence_thresholds"), Mapping) else {}
    if risk_level == "high":
        return "review" if confidence >= float(thresholds.get("review", 0.38)) else "observe"
    if confidence >= float(thresholds.get("actionable", 0.80)) and missing_count == 0 and risk_level == "low":
        return "actionable"
    if confidence >= float(thresholds.get("trial", 0.66)) and missing_count <= 1:
        return "trial"
    if confidence >= float(thresholds.get("shadow", 0.52)):
        return "shadow"
    if confidence >= float(thresholds.get("review", 0.38)):
        return "review"
    return "observe"


def _aggregate_risk_level(judgment: Mapping[str, Any]) -> str:
    crowding = judgment.get("crowding_risk") if isinstance(judgment.get("crowding_risk"), Mapping) else {}
    fake_breakout = judgment.get("fake_breakout_risk") if isinstance(judgment.get("fake_breakout_risk"), Mapping) else {}
    levels = {str(crowding.get("level") or ""), str(fake_breakout.get("level") or "")}
    if "high" in levels:
        return "high"
    if "medium" in levels:
        return "medium"
    return "low"


def _playbook_keys_from_judgment(judgment: Mapping[str, Any]) -> list[str]:
    playbook = judgment.get("playbook") if isinstance(judgment.get("playbook"), Mapping) else {}
    return unique_keep_order([
        judgment.get("opportunity_type"),
        playbook.get("opportunity_type"),
        playbook.get("value"),
    ])


def _theme_items(market_themes: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    raw = (market_themes or {}).get("themes") if isinstance(market_themes, Mapping) else []
    return [item for item in (raw or []) if isinstance(item, dict)]


def _theme_of(item: Mapping[str, Any]) -> str:
    if item.get("theme"):
        return str(item.get("theme") or "").strip()
    themes = item.get("themes")
    if isinstance(themes, list) and themes:
        return str(themes[0] or "").strip()
    return "其他"


def _entry_plan(item: Mapping[str, Any]) -> dict[str, Any]:
    plan = item.get("entry_plan")
    return dict(plan) if isinstance(plan, Mapping) else {}


def _technical_state(item: Mapping[str, Any]) -> dict[str, Any]:
    tech = item.get("technical_state")
    if isinstance(tech, Mapping):
        return dict(tech)
    factors = item.get("tushare_factors")
    snapshot = factors.get("factor_snapshot") if isinstance(factors, Mapping) else {}
    technical = snapshot.get("technical") if isinstance(snapshot, Mapping) else {}
    return dict(technical) if isinstance(technical, Mapping) else {}


def _flow_today_yi(item: Mapping[str, Any]) -> float:
    capital_flow = item.get("capital_flow") if isinstance(item.get("capital_flow"), Mapping) else {}
    explicit = item.get("flow_today_yi") or capital_flow.get("flow_today_yi") or capital_flow.get("today_yi")
    if explicit is not None:
        return round(safe_float(explicit, 0.0) or 0.0, 2)
    return round(capital_flow_today_yi(capital_flow, legacy_source_unit=UNIT_YUAN), 2)


def infer_market_phase(market_regime: Mapping[str, Any] | None) -> dict[str, Any]:
    regime = market_regime or {}
    gate = regime.get("execution_gate") if isinstance(regime.get("execution_gate"), Mapping) else {}
    status = str(gate.get("status") or ("on" if regime.get("attack_ok", True) else "off"))
    score = safe_float(regime.get("score"), 0.0) or 0.0
    metrics = regime.get("metrics") if isinstance(regime.get("metrics"), Mapping) else {}
    positive_ratio = safe_float(metrics.get("positive_ratio"), 0.0) or 0.0
    if status == "off":
        phase, label = "risk_off", "市场防守"
    elif status == "limited":
        phase, label = "repair_or_rotation", "修复轮动"
    elif score >= 6 and positive_ratio >= 0.62:
        phase, label = "risk_on", "进攻放开"
    else:
        phase, label = "selective_risk_on", "选择性进攻"
    return {
        "value": phase,
        "label": label,
        "gate_status": status,
        "score": round(score, 2),
        "positive_ratio": round(positive_ratio, 3),
        "summary": gate.get("summary") or regime.get("summary") or "",
    }


def infer_theme_phase(item: Mapping[str, Any], market_themes: Mapping[str, Any] | None) -> dict[str, Any]:
    theme = _theme_of(item)
    themes = _theme_items(market_themes)
    top_names = [str(row.get("theme") or "") for row in themes[:2]]
    match = next((row for row in themes if str(row.get("theme") or "") == theme), {})
    persistence = match.get("persistence") if isinstance(match.get("persistence"), Mapping) else {}
    persistence_label = str(persistence.get("label") or "")
    persistence_score = safe_float(persistence.get("score"), 0.0) or 0.0
    is_top = bool(theme and theme != "其他" and theme in top_names)

    if not theme or theme == "其他":
        value, label = "no_clear_theme", "题材不清"
    elif is_top and persistence_label in {"持续增强", "强势延续"}:
        value, label = "mainline_confirmed", "主线确认"
    elif is_top:
        value, label = "mainline_diverging", "主线分化"
    elif persistence_score >= 3:
        value, label = "rotation_watch", "轮动观察"
    else:
        value, label = "theme_weak", "题材偏弱"

    return {
        "value": value,
        "label": label,
        "theme": theme,
        "is_top_theme": is_top,
        "persistence_label": persistence_label,
        "persistence_score": round(persistence_score, 2),
        "summary": persistence.get("summary") or "",
    }


def infer_stock_role(item: Mapping[str, Any], theme_phase: Mapping[str, Any]) -> dict[str, Any]:
    setup_type = str(item.get("setup_type") or "")
    setup_label = str(item.get("setup_label") or "")
    amount_yi = safe_float(item.get("amount_yi"), 0.0) or 0.0
    change_pct = safe_float(item.get("change_pct"), 0.0) or 0.0
    flow_today = _flow_today_yi(item)
    consistency = safe_float(((item.get("consistency") or {}) if isinstance(item.get("consistency"), Mapping) else {}).get("score"), 0.0) or 0.0

    if setup_type == "leader_continuation" or (theme_phase.get("is_top_theme") and change_pct >= 4.5 and amount_yi >= 15):
        role, label = "theme_leader", "主线领涨/强势核心"
    elif setup_type == "breakout_follow":
        role, label = "breakout_challenger", "突破挑战者"
    elif setup_type == "pullback_continuation":
        role, label = "acceptance_candidate", "承接接力"
    elif setup_type == "low_reversal":
        role, label = "reversal_candidate", "低位修复"
    elif flow_today > 0 and consistency >= 2:
        role, label = "behavior_watch", "行为改善观察"
    else:
        role, label = "unclear_role", "角色未清"

    return {
        "value": role,
        "label": label,
        "setup_type": setup_type,
        "setup_label": setup_label,
        "role_evidence": unique_keep_order([
            setup_label,
            f"题材={theme_phase.get('theme')}" if theme_phase.get("theme") else "",
            f"资金={flow_today:+.2f}亿",
        ])[:3],
    }


def infer_playbook(item: Mapping[str, Any], stock_role: Mapping[str, Any]) -> dict[str, Any]:
    setup_type = str(item.get("setup_type") or stock_role.get("setup_type") or "")
    mapping = {
        "leader_continuation": ("leader_continuation", "主线龙头承接"),
        "breakout_follow": ("breakout_validation", "突破有效性验证"),
        "pullback_continuation": ("pullback_acceptance", "回踩承接确认"),
        "low_reversal": ("low_reversal_validation", "低位反转验证"),
    }
    value, label = mapping.get(setup_type, ("structure_discovery", "结构发现"))
    return {
        "value": value,
        "label": label,
        "opportunity_type": value,
    }


def crowding_risk(item: Mapping[str, Any]) -> dict[str, Any]:
    tech = _technical_state(item)
    change_pct = safe_float(item.get("change_pct"), 0.0) or 0.0
    turnover = safe_float(item.get("turnover"), 0.0) or 0.0
    pos20 = safe_float(tech.get("position_20d"), None)
    overheat = safe_float(item.get("overheat_penalty"), 0.0) or 0.0
    evidence: list[str] = []
    score = 0
    if change_pct >= 8:
        score += 2
        evidence.append(f"涨幅 {change_pct:.2f}% 已接近高潮")
    elif change_pct >= 6:
        score += 1
        evidence.append(f"涨幅 {change_pct:.2f}% 偏高")
    if pos20 is not None and pos20 >= 0.78:
        score += 1
        evidence.append(f"20日位置 {pos20:.2f} 偏高")
    if turnover >= 8:
        score += 1
        evidence.append(f"换手 {turnover:.2f}% 偏拥挤")
    if overheat >= 6:
        score += 2
        evidence.append("过热惩罚较高")
    elif overheat >= 3:
        score += 1
        evidence.append("短线已有过热迹象")
    level = "high" if score >= 4 else "medium" if score >= 2 else "low"
    return {
        "level": level,
        "score": score,
        "summary": {
            "high": "拥挤风险高，不能追第一波。",
            "medium": "已有拥挤迹象，必须等换手承接。",
            "low": "拥挤风险暂可控。",
        }[level],
        "evidence": evidence[:4],
    }


def fake_breakout_risk(item: Mapping[str, Any]) -> dict[str, Any]:
    setup_type = str(item.get("setup_type") or "")
    capital_flow = item.get("capital_flow") if isinstance(item.get("capital_flow"), Mapping) else {}
    flow_today = _flow_today_yi(item)
    trend = str(capital_flow.get("trend") or "")
    quality = item.get("execution_quality") if isinstance(item.get("execution_quality"), Mapping) else {}
    quality_warnings = quality.get("warnings") if isinstance(quality.get("warnings"), list) else []
    entry_plan = _entry_plan(item)
    has_trigger = bool(entry_plan.get("trigger") or (entry_plan.get("levels") or {}).get("trigger"))
    evidence: list[str] = []
    score = 0
    if setup_type in {"leader_continuation", "breakout_follow"}:
        score += 1
        evidence.append("趋势/突破类 playbook 天生需要二次确认")
    if flow_today <= 0 and "转正" not in trend:
        score += 2
        evidence.append("资金未同步确认")
    if not has_trigger:
        score += 1
        evidence.append("缺少明确突破/回踩触发位")
    for warning in quality_warnings:
        text = str(warning or "")
        if "资金" in text or "追涨" in text or "过热" in text:
            score += 1
            evidence.append(text)
            break
    level = "high" if score >= 4 else "medium" if score >= 2 else "low"
    return {
        "level": level,
        "score": score,
        "summary": {
            "high": "假突破风险高，只能影子/复核。",
            "medium": "需要站稳触发位并看到承接。",
            "low": "假突破风险暂可控。",
        }[level],
        "evidence": evidence[:4],
    }


def build_hard_gate(
    item: Mapping[str, Any],
    market_regime: Mapping[str, Any] | None,
    *,
    context: Mapping[str, Any] | None = None,
    rules: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    rules = merge_rules(rules)
    caps = rules.get("hard_gate_caps") if isinstance(rules.get("hard_gate_caps"), Mapping) else {}
    context = context or {}
    gate = ((market_regime or {}).get("execution_gate") or item.get("execution_gate") or {})
    gate = gate if isinstance(gate, Mapping) else {}
    status = str(gate.get("status") or "on")
    setup_type = str(item.get("setup_type") or "")
    allowed_setups = set(gate.get("allowed_setups") or [])
    max_allowed = "actionable"
    reasons: list[dict[str, Any]] = []

    def apply_cap(cap: str, reason: str, *, source: str, hard: bool = True) -> None:
        nonlocal max_allowed
        max_allowed = cap_action(max_allowed, cap)
        reasons.append({"source": source, "reason": reason, "max_action": cap, "hard": hard})

    if status == "off":
        apply_cap(str(caps.get("gate_off", "shadow")), gate.get("summary") or "进攻阀门关闭", source="execution_gate")
    elif status == "limited":
        if allowed_setups and setup_type not in allowed_setups:
            apply_cap(
                str(caps.get("gate_limited_disallowed", "shadow")),
                "阀门半开，但当前 playbook 不在允许集合",
                source="execution_gate",
            )
        else:
            apply_cap(
                str(caps.get("gate_limited_allowed", "trial")),
                gate.get("summary") or "阀门半开，只允许轻仓试错",
                source="execution_gate",
                hard=False,
            )

    risk_level = str(item.get("risk_level") or "")
    block_reason = str(item.get("block_reason") or "")
    degrade_reason = str(item.get("degrade_reason") or "")
    if block_reason or risk_level == "block":
        apply_cap(str(caps.get("risk_block", "shadow")), block_reason or "停牌/ST/涨跌停等硬执行约束", source="execution_risk")
    elif degrade_reason or risk_level == "degrade":
        apply_cap(str(caps.get("risk_degrade", "trial")), degrade_reason or "风险降级，不能直接放大动作", source="execution_risk", hard=False)

    readiness_mode = str(context.get("readiness_mode") or "").strip()
    if readiness_mode == "blocked":
        apply_cap(str(caps.get("readiness_blocked", "observe")), "readiness 未就绪，不能输出可执行动作", source="readiness")
    elif readiness_mode == "shadow_only":
        apply_cap(str(caps.get("readiness_shadow", "shadow")), "readiness 只允许影子盘", source="readiness")

    if context.get("real_trade_allowed") is False or context.get("can_trade") is False:
        apply_cap(str(caps.get("no_trade_permission", "shadow")), "真实交易权限未放行", source="account")
    if str(context.get("account_mode") or "").strip() in {"research", "shadow"}:
        apply_cap(str(caps.get("no_trade_permission", "shadow")), "账户模式不是 live_small", source="account")
    position_cap = str(context.get("position_cap") or gate.get("position_cap") or "").strip()
    if position_cap in {"0", "0成", "0 成"}:
        apply_cap(str(caps.get("position_cap_zero", "shadow")), "仓位上限为 0，不能开新仓", source="position")
    midday_status = str(context.get("midday_status") or item.get("confirmation_status") or item.get("status") or "").strip()
    if midday_status == "downgraded":
        apply_cap(str(caps.get("midday_failed", "observe")), "午盘确认失败，原假设暂时失效", source="midday")

    hard_block_reasons = [reason["reason"] for reason in reasons if reason.get("hard")]
    return {
        "maximum_allowed_action": max_allowed,
        "block_reasons": hard_block_reasons,
        "reasons": reasons,
        "execution_gate_status": status,
        "position_cap": position_cap or gate.get("position_cap") or "",
        "allowed_setups": sorted(allowed_setups),
    }


def _confirmation_fields(item: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    entry_plan = _entry_plan(item)
    quality = item.get("execution_quality") if isinstance(item.get("execution_quality"), Mapping) else {}
    capital_flow = item.get("capital_flow") if isinstance(item.get("capital_flow"), Mapping) else {}
    missing: list[str] = []
    positives: list[str] = []
    if not entry_plan.get("trigger"):
        missing.append("缺少明确触发位")
    else:
        positives.append("触发位已写清")
    if not entry_plan.get("invalidate"):
        missing.append("缺少清晰失效条件")
    else:
        positives.append("失效条件已写清")
    flow_today = _flow_today_yi(item)
    if flow_today > 0 or "转正" in str(capital_flow.get("trend") or ""):
        positives.append("资金行为有验证")
    else:
        missing.append("资金承接还未确认")
    warnings = [str(v or "") for v in (quality.get("warnings") or [])]
    if len(warnings) >= 2:
        missing.append("执行质量仍有多项警告")
    if item.get("setup_type") in {"leader_continuation", "breakout_follow"} and item.get("approved_hits", 0) < 2:
        missing.append("趋势/突破类缺少跨策略共振")
    return unique_keep_order(missing)[:5], unique_keep_order(positives)[:5]


def build_baseline_judgment(
    item: Mapping[str, Any],
    *,
    market_regime: Mapping[str, Any] | None = None,
    market_themes: Mapping[str, Any] | None = None,
    rules: Mapping[str, Any] | None = None,
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    rules = _with_calibration_applied(rules)
    market_phase = infer_market_phase(market_regime)
    theme_phase = infer_theme_phase(item, market_themes)
    stock_role = infer_stock_role(item, theme_phase)
    playbook = infer_playbook(item, stock_role)
    playbook_key = str(playbook.get("opportunity_type") or playbook.get("value") or "")
    crowding = crowding_risk(item)
    fake_breakout = fake_breakout_risk(item)
    hard_gate = build_hard_gate(item, market_regime, context=context, rules=rules)
    missing, positives = _confirmation_fields(item)
    calibration = rules.get("__calibration") if isinstance(rules.get("__calibration"), Mapping) else {}
    mode_guard = rules.get("__mode_guard") if isinstance(rules.get("__mode_guard"), Mapping) else {}
    threshold_adjustments = rules.get("__threshold_adjustments") if isinstance(rules.get("__threshold_adjustments"), Mapping) else {}
    playbook_adjustments = rules.get("playbook_adjustments") if isinstance(rules.get("playbook_adjustments"), Mapping) else {}
    playbook_adjustment = playbook_adjustments.get(playbook_key) if isinstance(playbook_adjustments.get(playbook_key), Mapping) else {}

    entry_plan = _entry_plan(item)
    theme_name = str(theme_phase.get("theme") or "题材未明")
    role_label = str(stock_role.get("label") or "角色未清")
    playbook_label = str(playbook.get("label") or "结构发现")
    setup_label = str(item.get("setup_label") or playbook_label)
    flow_today = _flow_today_yi(item)
    quality = item.get("execution_quality") if isinstance(item.get("execution_quality"), Mapping) else {}
    consistency = item.get("consistency") if isinstance(item.get("consistency"), Mapping) else {}
    quality_score = safe_float(quality.get("score"), 0.0) or 0.0
    consistency_score = safe_float(consistency.get("score"), 0.0) or 0.0

    thesis = (
        f"{theme_name}处于{theme_phase.get('label')}，{item.get('name') or item.get('code')}当前更像{role_label}，"
        f"机会类型是{playbook_label}；只有承接和失效位同时清楚，才从观察升到动作。"
    )
    why_now_parts = unique_keep_order([
        str(theme_phase.get("summary") or ""),
        str(item.get("entry_reason") or ""),
        str(entry_plan.get("trigger") or item.get("watch_condition") or ""),
        f"资金今日 {flow_today:+.2f} 亿" if flow_today else "",
    ])
    why_now = "；".join(why_now_parts[:3]) or "结构正在形成，但还缺少足够的行为确认。"
    invalidation = str(entry_plan.get("invalidate") or item.get("main_risk") or "资金转弱、跌破承接位或题材退潮即失效。")

    clarity = 0.25
    if playbook["value"] != "structure_discovery":
        clarity += 0.20
    if stock_role["value"] != "unclear_role":
        clarity += 0.15
    if entry_plan.get("trigger"):
        clarity += 0.15
    if entry_plan.get("invalidate"):
        clarity += 0.10
    if theme_phase["value"] in {"mainline_confirmed", "mainline_diverging", "rotation_watch"}:
        clarity += 0.10

    behavior = clamp(0.35 + quality_score * 0.055 + consistency_score * 0.04 + min(max(flow_today, -3), 5) * 0.035, 0.0, 1.0)
    role_score = {
        "theme_leader": 0.82,
        "breakout_challenger": 0.70,
        "acceptance_candidate": 0.76,
        "reversal_candidate": 0.64,
        "behavior_watch": 0.56,
        "unclear_role": 0.35,
    }.get(str(stock_role["value"]), 0.35)
    theme_score = {
        "mainline_confirmed": 0.82,
        "mainline_diverging": 0.62,
        "rotation_watch": 0.56,
        "theme_weak": 0.34,
        "no_clear_theme": 0.25,
    }.get(str(theme_phase["value"]), 0.25)
    rr_score = 0.72
    if crowding["level"] == "medium":
        rr_score -= 0.18
    elif crowding["level"] == "high":
        rr_score -= 0.34
    if fake_breakout["level"] == "medium":
        rr_score -= 0.12
    elif fake_breakout["level"] == "high":
        rr_score -= 0.25
    rr_score = clamp(rr_score, 0.0, 1.0)

    raw_weights = rules.get("confidence_weights") if isinstance(rules.get("confidence_weights"), Mapping) else {}
    weights = {
        "clarity": safe_float(raw_weights.get("clarity"), 0.30) or 0.30,
        "behavior": safe_float(raw_weights.get("behavior"), 0.24) or 0.24,
        "role": safe_float(raw_weights.get("role"), 0.22) or 0.22,
        "theme": safe_float(raw_weights.get("theme"), 0.14) or 0.14,
        "risk_reward": safe_float(raw_weights.get("risk_reward"), 0.10) or 0.10,
    }
    weight_total = sum(weights.values()) or 1.0
    confidence_raw = (
        clarity * weights["clarity"]
        + behavior * weights["behavior"]
        + role_score * weights["role"]
        + theme_score * weights["theme"]
        + rr_score * weights["risk_reward"]
    ) / weight_total
    calibration_adjustment = safe_float(playbook_adjustment.get("confidence_adjustment"), 0.0) or 0.0
    confidence = round(clamp(confidence_raw + calibration_adjustment, 0.0, 1.0), 2)
    aggregate_risk = "high" if crowding["level"] == "high" or fake_breakout["level"] == "high" else "medium" if crowding["level"] == "medium" or fake_breakout["level"] == "medium" else "low"
    desired_action = action_from_confidence(confidence, rules, len(missing), aggregate_risk)
    calibration_cap = str(playbook_adjustment.get("action_cap") or "").strip()
    if calibration_cap in ACTION_ORDER:
        desired_action = cap_action(desired_action, calibration_cap)
    suggested_action = cap_action(desired_action, hard_gate["maximum_allowed_action"])

    if suggested_action != desired_action:
        upgrade_reason = f"结构动作原本可到 {ACTION_LABELS[desired_action]}，但硬闸门封顶为 {ACTION_LABELS[suggested_action]}。"
    elif calibration_cap in ACTION_ORDER and action_rank(calibration_cap) < action_rank(str(action_from_confidence(confidence, rules, len(missing), aggregate_risk))):
        upgrade_reason = f"该 playbook 近期复盘偏弱，校准层把最大结构动作压到 {ACTION_LABELS[desired_action]}。"
    elif suggested_action in {"trial", "actionable"}:
        upgrade_reason = "假设、触发、失效和行为验证相对清楚，风险收益比允许进入动作复核。"
    elif suggested_action == "shadow":
        upgrade_reason = "结构假设成立但还不够买，只适合影子跟踪验证。"
    elif suggested_action == "review":
        upgrade_reason = "出现可复核结构，但关键确认不足。"
    else:
        upgrade_reason = "结构假设仍不完整，暂不升级。"

    evidence = [
        {"type": "structure", "label": "stock_role", "value": stock_role["label"], "weight": weights["role"]},
        {"type": "structure", "label": "playbook", "value": playbook["label"], "weight": weights["clarity"]},
        {"type": "market", "label": "market_phase", "value": market_phase["label"], "weight": 0.12},
        {"type": "theme", "label": "theme_phase", "value": theme_phase["label"], "weight": weights["theme"]},
        {"type": "behavior", "label": "execution_quality", "value": quality.get("label") or quality_score, "weight": weights["behavior"]},
        {"type": "behavior", "label": "capital_flow", "value": f"{flow_today:+.2f}亿", "weight": 0.10},
        {"type": "risk", "label": "crowding", "value": crowding["summary"], "weight": -0.06},
        {"type": "risk", "label": "fake_breakout", "value": fake_breakout["summary"], "weight": -0.06},
    ]
    if threshold_adjustments:
        evidence.append({
            "type": "calibration",
            "label": "threshold_adjustment",
            "value": f"样本阶段 {mode_guard.get('sample_stage') or calibration.get('sample_stage') or '-'}，阈值临时收紧",
            "weight": 0,
        })
    if playbook_adjustment:
        evidence.append({
            "type": "calibration",
            "label": "playbook_adjustment",
            "value": playbook_adjustment.get("reason") or "该 playbook 已按复盘结果校准",
            "weight": calibration_adjustment,
        })

    return {
        "schema_version": "opportunity_v2.1",
        "mode": str(rules.get("mode") or resolve_mode(rules)),
        "mode_requested": mode_guard.get("requested_mode") or rules.get("__requested_mode") or resolve_mode(rules),
        "mode_effective": mode_guard.get("effective_mode") or rules.get("mode") or resolve_mode(rules),
        "mode_guard": mode_guard,
        "judge_source": "deterministic_baseline",
        "market_phase": market_phase,
        "theme_phase": theme_phase,
        "stock_role": stock_role,
        "playbook": playbook,
        "opportunity_type": playbook["opportunity_type"],
        "thesis": thesis,
        "why_now": why_now,
        "invalidation": invalidation,
        "upgrade_reason": upgrade_reason,
        "missing_confirmation": missing,
        "positive_confirmation": positives,
        "crowding_risk": crowding,
        "fake_breakout_risk": fake_breakout,
        "desired_action": desired_action,
        "suggested_action": suggested_action,
        "action_label": ACTION_LABELS[suggested_action],
        "confidence": confidence,
        "confidence_components": {
            "clarity": round(clarity, 3),
            "behavior": round(behavior, 3),
            "role": round(role_score, 3),
            "theme": round(theme_score, 3),
            "risk_reward": round(rr_score, 3),
            "calibration_adjustment": round(calibration_adjustment, 4),
        },
        "calibration": {
            "schema_version": calibration.get("schema_version"),
            "loaded": bool(calibration.get("loaded")),
            "sample_stage": calibration.get("sample_stage"),
            "sample_count": calibration.get("sample_count"),
            "mature_samples": calibration.get("mature_samples"),
            "active_allowed": bool(calibration.get("active_allowed")),
            "guard_reason": calibration.get("guard_reason"),
            "threshold_adjustments": dict(threshold_adjustments),
            "playbook_adjustment": dict(playbook_adjustment),
            "effective_thresholds": dict(rules.get("confidence_thresholds") or {}),
            "path": calibration.get("path"),
        },
        "hard_gate": hard_gate,
        "evidence": evidence,
        "ai_status": "not_requested",
        "ai_summary": ai_summary_for_judgment({"ai_status": "not_requested"}),
    }


@dataclass(frozen=True)
class AIJudgeConfig:
    provider: str
    api_key: str
    base_url: str
    model: str
    timeout_seconds: float
    configured: bool


def ai_judge_config(rules: Mapping[str, Any] | None = None) -> AIJudgeConfig:
    rules = merge_rules(rules)
    ai_rules = rules.get("ai") if isinstance(rules.get("ai"), Mapping) else {}
    timeout = safe_float(os.environ.get("PRISM_V2_AI_TIMEOUT_SECONDS"), None)
    timeout_seconds = float(timeout if timeout is not None else ai_rules.get("timeout_seconds", 12))
    provider = os.environ.get("PRISM_V2_AI_PROVIDER", "").strip().lower()
    api_key = os.environ.get("PRISM_V2_AI_API_KEY", "").strip()
    base_url = os.environ.get("PRISM_V2_AI_BASE_URL", "").strip().rstrip("/")
    model = os.environ.get("PRISM_V2_AI_MODEL", "").strip()

    if not api_key and os.environ.get("DEEPSEEK_API_KEY"):
        provider = provider or "deepseek"
        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        base_url = base_url or os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip().rstrip("/")
        model = model or os.environ.get("DEEPSEEK_MODEL", "deepseek-chat").strip()
    elif not api_key and os.environ.get("OPENAI_API_KEY") and os.environ.get("PRISM_V2_AI_MODEL"):
        provider = provider or "openai"
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        base_url = base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
        model = model or os.environ.get("PRISM_V2_AI_MODEL", "").strip()

    configured = bool(api_key and base_url and model)
    return AIJudgeConfig(
        provider=provider or "openai_compatible",
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout_seconds=timeout_seconds,
        configured=configured,
    )


def _chat_url(config: AIJudgeConfig) -> str:
    return f"{config.base_url.rstrip('/')}/chat/completions"


def _extract_json_object(text: str) -> dict[str, Any]:
    payload = str(text or "").strip()
    if payload.startswith("```"):
        payload = re.sub(r"^```(?:json)?", "", payload).strip()
        payload = re.sub(r"```$", "", payload).strip()
    try:
        parsed = json.loads(payload)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    start = payload.find("{")
    end = payload.rfind("}")
    if start >= 0 and end > start:
        parsed = json.loads(payload[start : end + 1])
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("AI judge did not return a JSON object")


def _ai_prompt_payload(item: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict[str, Any]:
    compact_item = {
        "code": item.get("code"),
        "name": item.get("name"),
        "theme": _theme_of(item),
        "setup_type": item.get("setup_type"),
        "setup_label": item.get("setup_label"),
        "entry_reason": item.get("entry_reason"),
        "watch_condition": item.get("watch_condition"),
        "main_risk": item.get("main_risk"),
        "entry_plan": item.get("entry_plan"),
        "execution_quality": item.get("execution_quality"),
        "consistency": item.get("consistency"),
        "capital_flow": item.get("capital_flow"),
        "change_pct": item.get("change_pct"),
        "amount_yi": item.get("amount_yi"),
        "risk_flags": item.get("risk_flags"),
        "block_reason": item.get("block_reason"),
        "degrade_reason": item.get("degrade_reason"),
    }
    return {
        "candidate": compact_item,
        "baseline": {
            key: baseline.get(key)
            for key in (
                "market_phase",
                "theme_phase",
                "stock_role",
                "playbook",
                "thesis",
                "why_now",
                "invalidation",
                "missing_confirmation",
                "crowding_risk",
                "fake_breakout_risk",
                "desired_action",
                "suggested_action",
                "confidence",
                "hard_gate",
            )
        },
    }


def validate_ai_judgment(
    raw: Mapping[str, Any],
    baseline: Mapping[str, Any],
    *,
    rules: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    out = deepcopy(dict(baseline))
    effective_rules = _with_calibration_applied(rules) if rules is not None else None
    text_fields = [
        "thesis",
        "why_now",
        "invalidation",
        "upgrade_reason",
        "opportunity_type",
    ]
    for key in text_fields:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            out[key] = value.strip()
    for key in ("market_phase", "theme_phase", "stock_role", "playbook", "crowding_risk", "fake_breakout_risk"):
        value = raw.get(key)
        if isinstance(value, Mapping):
            merged = dict(out.get(key) or {})
            merged.update({k: v for k, v in value.items() if v not in (None, "", [], {})})
            out[key] = merged
    for key in ("missing_confirmation", "evidence"):
        value = raw.get(key)
        if isinstance(value, list):
            out[key] = value[:8]
    confidence = safe_float(raw.get("confidence"), None)
    if confidence is not None:
        out["confidence"] = round(clamp(confidence, 0.0, 1.0), 2)
    desired = str(raw.get("suggested_action") or raw.get("desired_action") or out.get("desired_action") or "observe").strip()
    if desired not in ACTION_ORDER:
        desired = str(out.get("desired_action") or "observe")

    validation_rules = effective_rules
    if validation_rules is None:
        calibration = out.get("calibration") if isinstance(out.get("calibration"), Mapping) else {}
        thresholds = calibration.get("effective_thresholds") if isinstance(calibration.get("effective_thresholds"), Mapping) else {}
        validation_rules = merge_rules({"confidence_thresholds": thresholds} if thresholds else None)

    missing = out.get("missing_confirmation") if isinstance(out.get("missing_confirmation"), list) else []
    confidence_cap = action_from_confidence(
        safe_float(out.get("confidence"), 0.0) or 0.0,
        validation_rules,
        len(missing),
        _aggregate_risk_level(out),
    )
    desired = cap_action(desired, confidence_cap)

    playbook_adjustments = validation_rules.get("playbook_adjustments") if isinstance(validation_rules.get("playbook_adjustments"), Mapping) else {}
    playbook_adjustment: dict[str, Any] = {}
    for playbook_key in unique_keep_order([
        *_playbook_keys_from_judgment(baseline),
        *_playbook_keys_from_judgment(out),
    ]):
        candidate_adjustment = playbook_adjustments.get(playbook_key)
        if not isinstance(candidate_adjustment, Mapping):
            continue
        candidate_cap = str(candidate_adjustment.get("action_cap") or "").strip()
        existing_cap = str(playbook_adjustment.get("action_cap") or "").strip()
        if (
            candidate_cap in ACTION_ORDER
            and (existing_cap not in ACTION_ORDER or action_rank(candidate_cap) < action_rank(existing_cap))
        ):
            playbook_adjustment = dict(candidate_adjustment)
        elif not playbook_adjustment:
            playbook_adjustment = dict(candidate_adjustment)
    if not playbook_adjustment:
        calibration = out.get("calibration") if isinstance(out.get("calibration"), Mapping) else {}
        playbook_adjustment = calibration.get("playbook_adjustment") if isinstance(calibration.get("playbook_adjustment"), Mapping) else {}
    calibration_cap = str(playbook_adjustment.get("action_cap") or "").strip()
    if calibration_cap in ACTION_ORDER:
        desired = cap_action(desired, calibration_cap)

    out["desired_action"] = desired
    out["suggested_action"] = cap_action(desired, ((out.get("hard_gate") or {}).get("maximum_allowed_action") or "observe"))
    out["action_label"] = ACTION_LABELS[out["suggested_action"]]
    out["judge_source"] = "ai_judge"
    out["ai_status"] = "used"
    out["ai_delta"] = ai_delta_from_baseline(baseline, out)
    out["ai_summary"] = ai_summary_for_judgment(out, baseline=baseline)
    return out


def run_ai_judge(
    item: Mapping[str, Any],
    baseline: Mapping[str, Any],
    *,
    rules: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    config = ai_judge_config(rules)
    if not config.configured:
        return None, {"status": "not_configured", "provider": config.provider}

    messages = [
        {
            "role": "system",
            "content": (
                "You are Prism's A-share opportunity judge. Return only strict JSON. "
                "You may refine structure, thesis and risks, but hard_gate.maximum_allowed_action is absolute. "
                "Never mark a candidate above the hard gate cap."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "task": "Refine this opportunity judgment. Required keys: market_phase, theme_phase, stock_role, "
                    "playbook, thesis, why_now, invalidation, upgrade_reason, missing_confirmation, "
                    "crowding_risk, fake_breakout_risk, suggested_action, confidence, evidence.",
                    "allowed_actions": list(ACTION_ORDER),
                    "payload": _ai_prompt_payload(item, baseline),
                },
                ensure_ascii=False,
            ),
        },
    ]
    payload = {
        "model": config.model,
        "messages": messages,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        _chat_url(config),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
        content = (((data.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
        raw = _extract_json_object(content)
        return validate_ai_judgment(raw, baseline, rules=rules), {
            "status": "used",
            "provider": config.provider,
            "model": config.model,
        }
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, KeyError) as exc:
        return None, {
            "status": "fallback",
            "provider": config.provider,
            "model": config.model,
            "error": str(exc)[:240],
        }


def build_opportunity_judgment(
    item: Mapping[str, Any],
    *,
    market_regime: Mapping[str, Any] | None = None,
    market_themes: Mapping[str, Any] | None = None,
    rules: Mapping[str, Any] | None = None,
    context: Mapping[str, Any] | None = None,
    ai_budget_remaining: int = 0,
) -> tuple[dict[str, Any], int]:
    rules = _with_calibration_applied(rules)
    requested_mode = str(rules.get("__requested_mode") or resolve_mode(rules))
    mode = str(rules.get("mode") or requested_mode)
    baseline = build_baseline_judgment(
        item,
        market_regime=market_regime,
        market_themes=market_themes,
        rules=rules,
        context=context,
    )
    baseline["mode"] = mode
    baseline["mode_requested"] = requested_mode
    baseline["mode_effective"] = mode
    if mode == "off":
        baseline["ai_status"] = "disabled"
        baseline["ai_summary"] = ai_summary_for_judgment(baseline)
        return baseline, ai_budget_remaining

    ai_rules = rules.get("ai") if isinstance(rules.get("ai"), Mapping) else {}
    ai_enabled = bool(ai_rules.get("enabled", True)) and mode in {"shadow", "assist", "active"}
    if not ai_enabled or ai_budget_remaining <= 0:
        baseline["ai_status"] = "not_requested" if ai_enabled else "disabled"
        baseline["ai_summary"] = ai_summary_for_judgment(baseline)
        return baseline, ai_budget_remaining

    ai_judgment, ai_meta = run_ai_judge(item, baseline, rules=rules)
    next_budget = max(0, ai_budget_remaining - 1)
    if not ai_judgment:
        baseline["ai_status"] = ai_meta.get("status") or "fallback"
        baseline["ai_provider"] = ai_meta.get("provider")
        baseline["ai_model"] = ai_meta.get("model")
        baseline["ai_error"] = ai_meta.get("error")
        baseline["ai_shadow_judgment"] = ai_meta
        baseline["ai_summary"] = ai_summary_for_judgment(baseline, meta=ai_meta)
        return baseline, next_budget

    if mode == "shadow":
        baseline["ai_status"] = "shadow_recorded"
        baseline["ai_provider"] = ai_meta.get("provider")
        baseline["ai_model"] = ai_meta.get("model")
        baseline["ai_delta"] = ai_delta_from_baseline(baseline, ai_judgment)
        shadow_summary_judgment = dict(ai_judgment)
        shadow_summary_judgment["ai_status"] = "shadow_recorded"
        baseline["ai_shadow_judgment"] = {
            **ai_meta,
            "suggested_action": ai_judgment.get("suggested_action"),
            "confidence": ai_judgment.get("confidence"),
            "thesis": ai_judgment.get("thesis"),
            "risk": {
                "crowding": ai_judgment.get("crowding_risk"),
                "fake_breakout": ai_judgment.get("fake_breakout_risk"),
            },
        }
        baseline["ai_summary"] = ai_summary_for_judgment(shadow_summary_judgment, baseline=baseline, meta=ai_meta)
        return baseline, next_budget

    ai_judgment["mode"] = mode
    ai_judgment["mode_requested"] = requested_mode
    ai_judgment["mode_effective"] = mode
    ai_judgment["ai_provider"] = ai_meta.get("provider")
    ai_judgment["ai_model"] = ai_meta.get("model")
    ai_judgment["ai_shadow_judgment"] = ai_meta
    ai_judgment["ai_delta"] = ai_delta_from_baseline(baseline, ai_judgment)
    ai_judgment["ai_summary"] = ai_summary_for_judgment(ai_judgment, baseline=baseline, meta=ai_meta)
    return ai_judgment, next_budget


def apply_v2_to_shortlist(
    shortlist: list[dict[str, Any]],
    *,
    market_regime: Mapping[str, Any] | None = None,
    market_themes: Mapping[str, Any] | None = None,
    rules: Mapping[str, Any] | None = None,
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    requested_mode = resolve_mode(rules)
    rules = _with_calibration_applied(rules)
    mode = str(rules.get("mode") or requested_mode)
    mode_guard = rules.get("__mode_guard") if isinstance(rules.get("__mode_guard"), Mapping) else {}
    calibration = rules.get("__calibration") if isinstance(rules.get("__calibration"), Mapping) else {}
    ai_rules = rules.get("ai") if isinstance(rules.get("ai"), Mapping) else {}
    ai_budget = int(safe_float(os.environ.get("PRISM_V2_AI_MAX_CALLS"), None) or ai_rules.get("max_calls", 0) or 0)
    if mode == "off":
        ai_budget = 0

    counts = {action: 0 for action in ACTION_ORDER}
    desired_counts = {action: 0 for action in ACTION_ORDER}
    sources: dict[str, int] = {}
    blocked_by_hard_gate = 0
    for item in shortlist:
        judgment, ai_budget = build_opportunity_judgment(
            item,
            market_regime=market_regime,
            market_themes=market_themes,
            rules=rules,
            context=context,
            ai_budget_remaining=ai_budget,
        )
        suggested = str(judgment.get("suggested_action") or "observe")
        desired = str(judgment.get("desired_action") or suggested)
        counts[suggested] = counts.get(suggested, 0) + 1
        desired_counts[desired] = desired_counts.get(desired, 0) + 1
        sources[str(judgment.get("judge_source") or "unknown")] = sources.get(str(judgment.get("judge_source") or "unknown"), 0) + 1
        if suggested != desired:
            blocked_by_hard_gate += 1
        item["opportunity_v2"] = judgment
        item["suggested_action"] = suggested
        item["suggested_action_label"] = ACTION_LABELS.get(suggested, suggested)
        item["confidence"] = judgment.get("confidence")
        item["thesis"] = judgment.get("thesis")
        item["why_now"] = judgment.get("why_now")
        item["invalidation"] = judgment.get("invalidation")
        item["missing_confirmation"] = judgment.get("missing_confirmation") or []
        item["hard_gate_max_action"] = (judgment.get("hard_gate") or {}).get("maximum_allowed_action")
        item["hard_gate_block_reason"] = "; ".join((judgment.get("hard_gate") or {}).get("block_reasons") or [])
        item["judge_source"] = judgment.get("judge_source")
        item["ai_status"] = judgment.get("ai_status")
        item["ai_status_label"] = (judgment.get("ai_summary") or {}).get("label") if isinstance(judgment.get("ai_summary"), Mapping) else ""
        item["ai_summary"] = judgment.get("ai_summary") if isinstance(judgment.get("ai_summary"), Mapping) else {}
        item["ai_delta"] = judgment.get("ai_delta") if isinstance(judgment.get("ai_delta"), Mapping) else {}
        item["ai_provider"] = judgment.get("ai_provider")
        item["ai_model"] = judgment.get("ai_model")

    return {
        "schema_version": "opportunity_v2.1",
        "mode": mode,
        "mode_requested": requested_mode,
        "mode_effective": mode,
        "mode_guard": dict(mode_guard),
        "calibration": {
            "schema_version": calibration.get("schema_version"),
            "loaded": bool(calibration.get("loaded")),
            "sample_stage": calibration.get("sample_stage"),
            "sample_count": calibration.get("sample_count"),
            "mature_samples": calibration.get("mature_samples"),
            "pending_outcome": calibration.get("pending_outcome"),
            "active_allowed": bool(calibration.get("active_allowed")),
            "guard_reason": calibration.get("guard_reason"),
            "threshold_adjustments": dict(rules.get("__threshold_adjustments") or {}),
            "path": calibration.get("path"),
        },
        "counts": counts,
        "desired_counts": desired_counts,
        "judge_sources": sources,
        "blocked_by_hard_gate": blocked_by_hard_gate,
        "ai_budget_remaining": ai_budget,
    }


def tracking_record_for_candidate(
    item: Mapping[str, Any],
    *,
    trade_date: str,
    source_artifact: str,
) -> dict[str, Any] | None:
    judgment = item.get("opportunity_v2") if isinstance(item.get("opportunity_v2"), Mapping) else {}
    action = str(judgment.get("suggested_action") or item.get("suggested_action") or "")
    if action not in {"shadow", "trial", "actionable"}:
        return None
    entry_plan = _entry_plan(item)
    hard_gate = judgment.get("hard_gate") if isinstance(judgment.get("hard_gate"), Mapping) else {}
    return {
        "schema_version": "opportunity_v2_tracking.1",
        "code": item.get("code"),
        "name": item.get("name"),
        "trade_date": trade_date,
        "suggested_action": action,
        "action_label": ACTION_LABELS.get(action, action),
        "thesis": judgment.get("thesis") or item.get("thesis"),
        "trigger": entry_plan.get("trigger") or item.get("watch_condition") or "",
        "invalidation": judgment.get("invalidation") or entry_plan.get("invalidate") or item.get("main_risk") or "",
        "confidence": judgment.get("confidence"),
        "hard_gate_block_reason": "; ".join(hard_gate.get("block_reasons") or []),
        "hard_gate_max_action": hard_gate.get("maximum_allowed_action"),
        "source_artifact": source_artifact,
        "judge_source": judgment.get("judge_source"),
        "ai_status": judgment.get("ai_status"),
        "ai_summary": judgment.get("ai_summary") if isinstance(judgment.get("ai_summary"), Mapping) else {},
        "ai_delta": judgment.get("ai_delta") if isinstance(judgment.get("ai_delta"), Mapping) else {},
        "ai_provider": judgment.get("ai_provider"),
        "ai_model": judgment.get("ai_model"),
        "market_phase": (judgment.get("market_phase") or {}).get("value") if isinstance(judgment.get("market_phase"), Mapping) else "",
        "theme_phase": (judgment.get("theme_phase") or {}).get("value") if isinstance(judgment.get("theme_phase"), Mapping) else "",
        "stock_role": (judgment.get("stock_role") or {}).get("value") if isinstance(judgment.get("stock_role"), Mapping) else "",
        "opportunity_type": judgment.get("opportunity_type"),
    }


def tracking_records(
    shortlist: list[Mapping[str, Any]],
    *,
    trade_date: str,
    source_artifact: str,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in shortlist:
        record = tracking_record_for_candidate(item, trade_date=trade_date, source_artifact=source_artifact)
        if record:
            records.append(record)
    return records
