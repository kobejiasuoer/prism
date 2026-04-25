from __future__ import annotations

from collections.abc import Mapping
from typing import Any

UNIT_WAN_YUAN = "wan_yuan"
UNIT_YUAN = "yuan"
UNIT_YI_YUAN = "yi_yuan"
AUTO_UNIT = "auto"

# 只给老数据兜底用：如果没有显式 unit/wan/yi 字段，且数值已经大到
# “按万元解释会非常夸张”，则把它视为历史遗留的“元”口径。
LEGACY_YUAN_THRESHOLD = 100_000.0


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def has_value(value: Any) -> bool:
    return value not in (None, "", "-")


def yuan_to_wan(value: Any, digits: int = 2) -> float:
    return round(safe_float(value) / 10000, digits)


def wan_to_yi(value: Any, digits: int = 2) -> float:
    return round(safe_float(value) / 10000, digits)


def infer_legacy_unit(value: Any) -> str:
    return UNIT_YUAN if abs(safe_float(value)) >= LEGACY_YUAN_THRESHOLD else UNIT_WAN_YUAN


def amount_to_wan(value: Any, source_unit: str = UNIT_WAN_YUAN, digits: int = 2) -> float:
    if not has_value(value):
        return round(0.0, digits)

    amount = safe_float(value)
    unit = source_unit or UNIT_WAN_YUAN
    if unit == AUTO_UNIT:
        unit = infer_legacy_unit(amount)

    if unit == UNIT_YUAN:
        return round(amount / 10000, digits)
    if unit == UNIT_YI_YUAN:
        return round(amount * 10000, digits)
    return round(amount, digits)


def resolve_amount_wan(
    payload: Mapping[str, Any] | None,
    *,
    wan_keys: tuple[str, ...] = (),
    yi_keys: tuple[str, ...] = (),
    legacy_keys: tuple[str, ...] = (),
    source_unit: str = AUTO_UNIT,
    default: float = 0.0,
) -> float:
    data = payload or {}
    if not isinstance(data, Mapping):
        return round(default, 2)

    for key in wan_keys:
        if has_value(data.get(key)):
            return amount_to_wan(data.get(key), UNIT_WAN_YUAN)

    for key in yi_keys:
        if has_value(data.get(key)):
            return amount_to_wan(data.get(key), UNIT_YI_YUAN)

    explicit_unit = data.get("unit")
    legacy_unit = explicit_unit if explicit_unit in {UNIT_WAN_YUAN, UNIT_YUAN} else source_unit
    for key in legacy_keys:
        if has_value(data.get(key)):
            return amount_to_wan(data.get(key), legacy_unit)

    return round(default, 2)


def build_capital_flow_payload(
    *,
    today_wan: Any,
    five_day_total_wan: Any,
    trend: str | None = None,
) -> dict[str, Any]:
    today_wan_value = amount_to_wan(today_wan, UNIT_WAN_YUAN)
    total_wan_value = amount_to_wan(five_day_total_wan, UNIT_WAN_YUAN)
    today_yi_value = wan_to_yi(today_wan_value)
    total_yi_value = wan_to_yi(total_wan_value)
    return {
        "unit": UNIT_WAN_YUAN,
        "trend": trend or "无数据",
        "today": today_wan_value,
        "today_wan": today_wan_value,
        "today_yi": today_yi_value,
        "flow_today_yi": today_yi_value,
        "5day_total": total_wan_value,
        "five_day_total": total_wan_value,
        "five_day_total_wan": total_wan_value,
        "five_day_total_yi": total_yi_value,
    }


def normalize_capital_flow_payload(
    payload: Mapping[str, Any] | None,
    *,
    legacy_source_unit: str = UNIT_YUAN,
) -> dict[str, Any]:
    data = dict(payload or {})
    today_wan_value = resolve_amount_wan(
        data,
        wan_keys=("today_wan", "main_net_wan", "flow_today_wan"),
        yi_keys=("today_yi", "flow_today_yi", "main_net_yi"),
        legacy_keys=("today", "main_net"),
        source_unit=legacy_source_unit,
    )
    total_wan_value = resolve_amount_wan(
        data,
        wan_keys=("five_day_total_wan",),
        yi_keys=("five_day_total_yi",),
        legacy_keys=("5day_total", "five_day_total"),
        source_unit=legacy_source_unit,
    )
    trend = data.get("trend") or "无数据"
    normalized = dict(data)
    normalized.update(
        build_capital_flow_payload(
            today_wan=today_wan_value,
            five_day_total_wan=total_wan_value,
            trend=trend,
        )
    )
    return normalized


def capital_flow_today_wan(payload: Mapping[str, Any] | None, *, legacy_source_unit: str = UNIT_YUAN) -> float:
    return resolve_amount_wan(
        payload,
        wan_keys=("today_wan", "main_net_wan", "flow_today_wan"),
        yi_keys=("today_yi", "flow_today_yi", "main_net_yi"),
        legacy_keys=("today", "main_net"),
        source_unit=legacy_source_unit,
    )


def capital_flow_today_yi(payload: Mapping[str, Any] | None, *, legacy_source_unit: str = UNIT_YUAN) -> float:
    return wan_to_yi(capital_flow_today_wan(payload, legacy_source_unit=legacy_source_unit))


def capital_flow_five_day_total_wan(
    payload: Mapping[str, Any] | None,
    *,
    legacy_source_unit: str = UNIT_YUAN,
) -> float:
    return resolve_amount_wan(
        payload,
        wan_keys=("five_day_total_wan",),
        yi_keys=("five_day_total_yi",),
        legacy_keys=("5day_total", "five_day_total"),
        source_unit=legacy_source_unit,
    )


def capital_flow_five_day_total_yi(
    payload: Mapping[str, Any] | None,
    *,
    legacy_source_unit: str = UNIT_YUAN,
) -> float:
    return wan_to_yi(capital_flow_five_day_total_wan(payload, legacy_source_unit=legacy_source_unit))


def normalize_capital_flow_row(
    row: Mapping[str, Any] | None,
    *,
    source_unit: str = AUTO_UNIT,
) -> dict[str, Any] | None:
    data = row or {}
    if not isinstance(data, Mapping):
        return None

    date = data.get("date")
    if not date:
        return None

    main_net_wan = resolve_amount_wan(
        data,
        wan_keys=("main_net_wan",),
        yi_keys=("main_net_yi",),
        legacy_keys=("main_net",),
        source_unit=source_unit,
    )
    super_large_wan = resolve_amount_wan(
        data,
        wan_keys=("super_large_wan",),
        yi_keys=("super_large_yi",),
        legacy_keys=("super_large",),
        source_unit=source_unit,
    )

    return {
        "date": date,
        "unit": UNIT_WAN_YUAN,
        "main_net": main_net_wan,
        "main_net_wan": main_net_wan,
        "main_net_yi": wan_to_yi(main_net_wan),
        "super_large": super_large_wan,
        "super_large_wan": super_large_wan,
        "super_large_yi": wan_to_yi(super_large_wan),
    }
