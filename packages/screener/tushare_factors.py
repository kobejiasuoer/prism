# packages/screener/tushare_factors.py
"""Tushare factor layer: read datasets → normalized factor values → score / tags / explanation.

Self-contained and read-only. Imports only stdlib + prism_data (never apps/control-panel).
Never raises on missing/NaN data; every factor value is Optional.
"""
from __future__ import annotations

import json
import math
import os
import statistics
from pathlib import Path
from typing import Any


def _dataset_root() -> Path:
    override = os.environ.get("PRISM_DATASET_REPOSITORY_ROOT")
    if override:
        return Path(override)
    from prism_data.utils import default_dataset_repository_root
    return Path(default_dataset_repository_root())


def _sanitize(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "default"
    return "".join(ch if ch.isalnum() or ch in {"-", "_", ".", "+"} else "_" for ch in text)


def _read_json_or_none(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _resolve_trade_date(dataset: str, requested: str | None) -> str | None:
    base = _dataset_root() / _sanitize(dataset)
    if not base.exists():
        return None
    dates = sorted(p.name for p in base.iterdir() if p.is_dir())
    if not dates:
        return None
    if requested:
        req = _sanitize(requested)
        if req in dates:
            return req
        earlier = [d for d in dates if d <= req]
        if earlier:
            return earlier[-1]
    return dates[-1]


def _load_dataset(dataset: str, trade_date: str | None, key: str) -> tuple[Any, dict[str, Any] | None]:
    resolved = _resolve_trade_date(dataset, trade_date)
    if not resolved:
        return None, None
    base = _dataset_root() / _sanitize(dataset) / resolved
    data_path = base / f"{_sanitize(key)}.json"
    if not data_path.exists():
        return None, None
    manifest = _read_json_or_none(base / f"{_sanitize(key)}.manifest.json")
    return _read_json_or_none(data_path), manifest


def _safe_float(value: Any) -> float | None:
    if value in (None, "", "-", "None"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else number


def _fmt_num(value, digits: int = 2) -> str:
    return "—" if value is None else f"{round(value, digits)}"


def _normalize_code(value: Any) -> str:
    text = str(value or "").strip().upper()
    if "." in text:
        text = text.split(".", 1)[0]
    return "".join(ch for ch in text if ch.isdigit()).zfill(6)


def _compact_date(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())[:8]


def _latest_row(rows: Any, *fields: str) -> dict[str, Any] | None:
    if not isinstance(rows, list):
        return None
    dict_rows = [row for row in rows if isinstance(row, dict)]
    if not dict_rows:
        return None
    keys = fields or ("trade_date", "end_date", "ann_date")
    return sorted(dict_rows, key=lambda row: max((_compact_date(row.get(f)) for f in keys), default=""))[-1]


_INDEX_KEYS = (("000300.SH", "000300"), ("000905.SH", "000905"), ("000852.SH", "000852"))


def _five_day_main_net(code: str, trade_date: str | None) -> float | None:
    resolved = _resolve_trade_date("capital_flow.daily", trade_date)
    if not resolved:
        return None
    base = _dataset_root() / _sanitize("capital_flow.daily")
    dates = sorted(p.name for p in base.iterdir() if p.is_dir() and p.name <= resolved)[-5:]
    total, seen = 0.0, False
    for d in dates:
        rows, _ = _load_dataset("capital_flow.daily", d, code)
        row = _latest_row(rows, "trade_date") or {}
        val = _safe_float(row.get("main_net_yi"))
        if val is not None:
            total += val
            seen = True
    return total if seen else None


def _index_memberships(trade_date: str | None, code: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key, _short in _INDEX_KEYS:
        rows, _ = _load_dataset("index.weight", trade_date, key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict) and _normalize_code(row.get("con_code") or row.get("code")) == code:
                out.append({"index": key, "weight": _safe_float(row.get("weight"))})
                break
    return out


def _market_hits(dataset: str, code: str, trade_date: str | None) -> list[dict[str, Any]]:
    rows, _ = _load_dataset(dataset, trade_date, "recent")
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict) and _normalize_code(r.get("code") or r.get("ts_code")) == code]


def _filter_code(rows: Any, code: str) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    return [
        row for row in rows
        if isinstance(row, dict)
        and _normalize_code(row.get("ts_code") or row.get("con_code") or row.get("code") or row.get("symbol")) == code
    ]


def _load_rows_for_keys(dataset: str, trade_date: str | None, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    resolved = _resolve_trade_date(dataset, trade_date)
    if not resolved:
        return rows
    for key in keys:
        payload, _manifest = _load_dataset(dataset, resolved, key)
        if isinstance(payload, list):
            rows.extend([row for row in payload if isinstance(row, dict)])
        elif isinstance(payload, dict):
            rows.append(payload)
    if rows:
        return rows

    base = _dataset_root() / _sanitize(dataset) / resolved
    if not base.exists():
        return rows
    for path in sorted(base.glob("*.json")):
        if path.name.endswith(".manifest.json"):
            continue
        payload = _read_json_or_none(path)
        if isinstance(payload, list):
            rows.extend([row for row in payload if isinstance(row, dict)])
        elif isinstance(payload, dict):
            rows.append(payload)
    return rows


def _load_code_rows(dataset: str, trade_date: str | None, keys: tuple[str, ...], code: str) -> list[dict[str, Any]]:
    return _filter_code(_load_rows_for_keys(dataset, trade_date, keys), code)


def _latest_rows(rows: list[dict[str, Any]], limit: int = 5, fields: tuple[str, ...] = ("trade_date", "end_date", "ann_date", "report_date", "float_date")) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: max((_compact_date(row.get(f)) for f in fields), default=""), reverse=True)[:limit]


def _first_text(row: dict[str, Any] | None, *keys: str) -> str:
    if not row:
        return ""
    for key in keys:
        value = row.get(key)
        if value not in (None, "", "-", "None"):
            return str(value)
    return ""


def _safe_sum(rows: list[dict[str, Any]], *keys: str) -> float | None:
    total = 0.0
    seen = False
    for row in rows:
        for key in keys:
            value = _safe_float(row.get(key))
            if value is None:
                continue
            total += value
            seen = True
            break
    return total if seen else None


def _average(values: list[float | None]) -> float | None:
    nums = [value for value in values if isinstance(value, (int, float))]
    return round(sum(nums) / len(nums), 4) if nums else None


def _northbound_top10_activity(rows: list[dict[str, Any]]) -> dict[str, Any]:
    latest = _latest_row(rows, "trade_date") or {}
    buy = _safe_float(latest.get("buy") or latest.get("buy_amount") or latest.get("buy_amt"))
    sell = _safe_float(latest.get("sell") or latest.get("sell_amount") or latest.get("sell_amt"))
    net_buy = _safe_float(latest.get("net_amount") or latest.get("net_buy") or latest.get("net_amt"))
    if net_buy is None and buy is not None and sell is not None:
        net_buy = buy - sell
    return {
        "data_available": bool(rows),
        "recent_count": len(rows),
        "latest_trade_date": _first_text(latest, "trade_date"),
        "latest_rank": _safe_float(latest.get("rank")),
        "latest_net_buy": net_buy,
        "latest_buy": buy,
        "latest_sell": sell,
    }


def _business_quality(rows: list[dict[str, Any]]) -> dict[str, Any]:
    latest_end = max((_compact_date(row.get("end_date") or row.get("ann_date")) for row in rows), default="")
    scoped = [row for row in rows if not latest_end or max(_compact_date(row.get("end_date")), _compact_date(row.get("ann_date"))) == latest_end]
    top = sorted(
        scoped,
        key=lambda row: _safe_float(row.get("bz_sales") or row.get("sales") or row.get("revenue") or row.get("main_business_income")) or 0.0,
        reverse=True,
    )[:5]
    total = sum((_safe_float(row.get("bz_sales") or row.get("sales") or row.get("revenue") or row.get("main_business_income")) or 0.0) for row in top)
    top_sales = _safe_float((top[0] if top else {}).get("bz_sales") or (top[0] if top else {}).get("sales") or (top[0] if top else {}).get("revenue") or (top[0] if top else {}).get("main_business_income"))
    top_share = top_sales / total if top_sales is not None and total > 0 else None
    return {
        "end_date": latest_end or None,
        "top_items": [
            {
                "item": _first_text(row, "bz_item", "item", "name", "business"),
                "type": _first_text(row, "type", "bz_type", "classify"),
                "sales": _safe_float(row.get("bz_sales") or row.get("sales") or row.get("revenue") or row.get("main_business_income")),
                "profit": _safe_float(row.get("bz_profit") or row.get("profit")),
            }
            for row in top
        ],
        "top_share": round(top_share, 4) if top_share is not None else None,
        "concentration_label": "主营集中" if top_share and top_share >= 0.6 else ("主营分散" if top_share is not None else ""),
        "data_available": bool(rows),
    }


def _event_risk_values(
    pledge_stat_rows: list[dict[str, Any]],
    pledge_detail_rows: list[dict[str, Any]],
    share_float_rows: list[dict[str, Any]],
    block_trade_rows: list[dict[str, Any]],
    repurchase_rows: list[dict[str, Any]],
    audit_rows: list[dict[str, Any]],
    report_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    pledge = _latest_row(pledge_stat_rows, "end_date", "ann_date") or {}
    pledge_ratio = _safe_float(pledge.get("pledge_ratio") or pledge.get("pledged_ratio") or pledge.get("p_total_ratio"))
    share_float_total_mv = _safe_sum(share_float_rows, "float_mv", "unlock_mv")
    block_latest = _latest_rows(block_trade_rows, limit=5, fields=("trade_date", "ann_date"))
    discounts: list[float | None] = []
    for row in block_latest:
        rate = _safe_float(row.get("discount_rate") or row.get("discount") or row.get("price_rate"))
        if rate is None:
            price = _safe_float(row.get("price") or row.get("deal_price"))
            close = _safe_float(row.get("close") or row.get("close_price"))
            if price is not None and close and close > 0:
                rate = (price / close - 1.0) * 100.0
        discounts.append(rate)
    block_discount = _average(discounts)
    audit = _latest_row(audit_rows, "end_date", "ann_date") or {}
    audit_text = " ".join(str(audit.get(key) or "") for key in ("audit_result", "audit_opinion", "opinion", "audit_type"))
    abnormal_audit = any(word in audit_text for word in ("保留", "否定", "无法", "非标", "强调", "带强调"))
    report_latest = _latest_rows(report_rows, limit=5, fields=("report_date", "ann_date"))
    report_text = " ".join(_first_text(row, "rating", "rating_name", "rate", "title", "report_title") for row in report_latest)
    downgrade = any(word in report_text for word in ("下调", "减持", "卖出", "中性", "低于"))
    return {
        "data_available": bool(pledge_stat_rows or pledge_detail_rows or share_float_rows or block_trade_rows or repurchase_rows or audit_rows or report_rows),
        "pledge_ratio": pledge_ratio,
        "pledge_detail_count": len(pledge_detail_rows),
        "share_float_count": len(share_float_rows),
        "share_float_total_mv": share_float_total_mv,
        "block_trade_count": len(block_trade_rows),
        "block_trade_average_discount_pct": block_discount,
        "repurchase_count": len(repurchase_rows),
        "audit_abnormal": abnormal_audit if audit else None,
        "audit_opinion": audit_text.strip(),
        "report_count": len(report_rows),
        "report_downgrade": downgrade if report_latest else None,
        "recent_share_float": _latest_rows(share_float_rows, limit=5, fields=("float_date", "ann_date")),
        "recent_repurchase": _latest_rows(repurchase_rows, limit=5, fields=("ann_date", "end_date")),
        "recent_reports": report_latest,
    }


def _margin_activity(detail_rows: list[dict[str, Any]], sec_rows: list[dict[str, Any]], market_margin: dict[str, Any]) -> dict[str, Any]:
    latest = _latest_row(detail_rows, "trade_date") or {}
    recent = _latest_rows(detail_rows, limit=2, fields=("trade_date",))
    latest_balance = _safe_float(latest.get("rzye") or latest.get("rzrqye") or latest.get("margin_balance"))
    previous_balance = None
    if len(recent) > 1:
        previous_balance = _safe_float(recent[1].get("rzye") or recent[1].get("rzrqye") or recent[1].get("margin_balance"))
    change = latest_balance - previous_balance if latest_balance is not None and previous_balance is not None else None
    return {
        "data_available": bool(detail_rows or sec_rows or market_margin),
        "is_margin_target": bool(sec_rows),
        "balance": latest_balance if latest_balance is not None else _safe_float(market_margin.get("rzrqye")),
        "balance_change": round(change, 4) if change is not None else None,
        "latest": latest,
    }


def _technical_chips(stk_rows: list[dict[str, Any]], cyq_perf_rows: list[dict[str, Any]], cyq_chip_rows: list[dict[str, Any]]) -> dict[str, Any]:
    stk = _latest_row(stk_rows, "trade_date") or {}
    perf = _latest_row(cyq_perf_rows, "trade_date") or {}
    chips = _latest_rows(cyq_chip_rows, limit=8, fields=("trade_date",))
    winner_rate = _safe_float(perf.get("winner_rate") or perf.get("profit_ratio") or perf.get("cyq_winner_rate"))
    cost_pressure = _safe_float(perf.get("cost_90pct") or perf.get("cost_85pct") or perf.get("avg_cost"))
    close = _safe_float(stk.get("close") or stk.get("close_qfq") or stk.get("close_hfq"))
    pressure_ratio = cost_pressure / close if cost_pressure is not None and close and close > 0 else None
    return {
        "data_available": bool(stk_rows or cyq_perf_rows or cyq_chip_rows),
        "technical": {
            "close": close,
            "macd": _safe_float(stk.get("macd")),
            "kdj_k": _safe_float(stk.get("kdj_k")),
            "rsi_6": _safe_float(stk.get("rsi_6")),
        },
        "winner_rate": winner_rate,
        "cost_pressure": cost_pressure,
        "pressure_ratio": round(pressure_ratio, 4) if pressure_ratio is not None else None,
        "chip_sample_count": len(chips),
    }


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "是", "停牌", "st", "suspended", "limit_up", "limit_down"}


def _contains_any(value: Any, keywords: tuple[str, ...]) -> bool:
    text = str(value or "").strip().lower()
    return bool(text and any(keyword.lower() in text for keyword in keywords))


def _near_price(value: float | None, target: float | None) -> bool:
    if value is None or target is None or target <= 0:
        return False
    return abs(value - target) <= max(0.01, abs(target) * 0.0005)


def _execution_constraint_values(
    execution_rows: list[dict[str, Any]],
    price_limit_rows: list[dict[str, Any]],
    technical_chips: dict[str, Any],
) -> dict[str, Any]:
    flag = _latest_row(execution_rows, "trade_date", "ann_date") or {}
    limit = _latest_row(price_limit_rows, "trade_date") or {}
    technical = technical_chips.get("technical") if isinstance(technical_chips, dict) else {}
    close = (
        _safe_float(flag.get("close") or flag.get("price") or flag.get("last_price"))
        or _safe_float(limit.get("close") or limit.get("price") or limit.get("last_price"))
        or _safe_float((technical or {}).get("close"))
    )
    up_limit = _safe_float(flag.get("up_limit") or limit.get("up_limit") or limit.get("limit_up"))
    down_limit = _safe_float(flag.get("down_limit") or limit.get("down_limit") or limit.get("limit_down"))
    trading_status = _first_text(flag, "trading_status", "trade_status", "status", "suspend_status")
    limit_status = _first_text(flag, "limit_status", "limit_type", "limit_flag")
    is_suspended = (
        _truthy(flag.get("is_suspended") or flag.get("suspended") or flag.get("suspend"))
        or _contains_any(trading_status, ("suspended", "停牌"))
        or str(flag.get("suspend_type") or "").strip().upper() == "S"
    )
    is_tradable_raw = flag.get("is_tradable")
    is_tradable = None if is_tradable_raw in (None, "") else _truthy(is_tradable_raw)
    if is_tradable is False:
        is_suspended = True
    is_st = (
        _truthy(flag.get("is_st") or flag.get("st") or flag.get("special_treatment"))
        or _contains_any(_first_text(flag, "st_name", "name", "st_type_name"), ("st", "*st", "退市"))
    )
    is_limit_up = (
        _truthy(flag.get("is_limit_up") or flag.get("limit_up"))
        or _contains_any(limit_status, ("limit_up", "up", "涨停"))
        or _near_price(close, up_limit)
    )
    is_limit_down = (
        _truthy(flag.get("is_limit_down") or flag.get("limit_down"))
        or _contains_any(limit_status, ("limit_down", "down", "跌停"))
        or _near_price(close, down_limit)
    )
    raw_blockers = [
        str(item or "").strip()
        for item in (flag.get("execution_blockers") or [])
        if str(item or "").strip()
    ]
    blockers = []
    if is_suspended:
        blockers.append("suspended")
    if is_st:
        blockers.append("st")
    if is_limit_up:
        blockers.append("limit_up")
    if is_limit_down:
        blockers.append("limit_down")
    blockers.extend(item for item in raw_blockers if item != "price_limit_missing")
    return {
        "data_available": bool(execution_rows or price_limit_rows),
        "latest_flag": flag,
        "latest_price_limit": limit,
        "trading_status": trading_status,
        "is_suspended": is_suspended,
        "is_tradable": (not is_suspended) if is_tradable is None else is_tradable,
        "is_st": is_st,
        "st_name": _first_text(flag, "st_name", "name"),
        "st_type_name": _first_text(flag, "st_type_name", "type_name", "st_type"),
        "up_limit": up_limit,
        "down_limit": down_limit,
        "close": close,
        "is_limit_up": is_limit_up,
        "is_limit_down": is_limit_down,
        "price_limit_available": up_limit is not None and down_limit is not None,
        "execution_blockers": list(dict.fromkeys(blockers)),
    }


def _trade_date_used(requested: str | None) -> str | None:
    for dataset in (
        "valuation.daily",
        "capital_flow.daily",
        "financial.indicator",
        "reference.concept_detail",
        "execution.flags",
        "price_limit.daily",
        "market.margin_detail",
        "technical.stk_factor",
    ):
        resolved = _resolve_trade_date(dataset, requested)
        if resolved:
            return resolved
    return None


def extract_factor_values(code: str, trade_date: str | None) -> dict[str, Any]:
    c = _normalize_code(code)
    valuation = _latest_row(_load_dataset("valuation.daily", trade_date, c)[0], "trade_date") or {}
    liquidity = _latest_row(_load_dataset("liquidity.daily", trade_date, c)[0], "trade_date") or {}
    capital = _latest_row(_load_dataset("capital_flow.daily", trade_date, c)[0], "trade_date") or {}
    indicator = _latest_row(_load_dataset("financial.indicator", trade_date, c)[0], "end_date", "ann_date") or {}
    top_list = _market_hits("market.top_list", c, trade_date)
    top_inst = _market_hits("market.top_inst", c, trade_date)
    hsgt = _latest_row(_load_dataset("market.hsgt_moneyflow", trade_date, "recent")[0], "trade_date") or {}
    margin = _latest_row(_load_dataset("market.margin", trade_date, "recent")[0], "trade_date") or {}
    company_rows = _load_code_rows("reference.stock_company", trade_date, ("all",), c)
    namechange_rows = _load_code_rows("reference.namechange", trade_date, ("all", "recent"), c)
    concept_rows = _load_code_rows("reference.concept_detail", trade_date, ("hs300-zz500", "all"), c)
    industry_rows = _load_code_rows("reference.industry_member", trade_date, ("SW2021-hs300-zz500", "hs300-zz500", "all"), c)
    ths_rows = _load_code_rows("reference.ths_member", trade_date, ("hs300-zz500", "all"), c)
    dc_rows = _load_code_rows("reference.dc_member", trade_date, ("hs300-zz500", "all"), c)
    business_rows = _load_code_rows("financial.main_business", trade_date, ("hs300-zz500-recent", "recent", "all"), c)
    margin_detail_rows = _load_code_rows("market.margin_detail", trade_date, ("recent", "all"), c)
    margin_sec_rows = _load_code_rows("market.margin_secs", trade_date, ("recent", "all"), c)
    block_trade_rows = _load_code_rows("market.block_trade", trade_date, ("recent", "all"), c)
    pledge_stat_rows = _load_code_rows("corporate_action.pledge_stat", trade_date, ("all", "recent"), c)
    pledge_detail_rows = _load_code_rows("corporate_action.pledge_detail", trade_date, ("all", "recent"), c)
    share_float_rows = _load_code_rows("corporate_action.share_float", trade_date, ("all", "recent"), c)
    repurchase_rows = _load_code_rows("corporate_action.repurchase", trade_date, ("all", "recent"), c)
    audit_rows = _load_code_rows("financial.audit", trade_date, ("hs300-zz500", "all", "recent"), c)
    report_rows = _load_code_rows("research.report_rc", trade_date, ("recent", "all"), c)
    stk_rows = _load_code_rows("technical.stk_factor", trade_date, ("hs300-zz500-recent", "recent", "all"), c)
    cyq_perf_rows = _load_code_rows("technical.cyq_perf", trade_date, ("hs300-zz500-recent", "recent", "all"), c)
    cyq_chip_rows = _load_code_rows("technical.cyq_chips", trade_date, ("hs300-zz500-recent", "recent", "all"), c)
    execution_rows = _load_code_rows("execution.flags", trade_date, ("formal-execution-flags", "universe-hs300-zz500-execution-flags", "recent", "all"), c)
    price_limit_rows = _load_code_rows("price_limit.daily", trade_date, ("formal-price-limit", "universe-hs300-zz500-price-limit", "recent", "all"), c)
    hsgt_top10_rows = _load_code_rows("market.hsgt_top10", trade_date, ("recent", "all"), c)
    inst_net = sum((_safe_float(r.get("net_buy")) or 0.0) for r in top_inst) if top_inst else None
    company = company_rows[0] if company_rows else {}
    name_changes = _latest_rows(namechange_rows, limit=3, fields=("ann_date", "start_date", "end_date"))
    concept_tags = [_first_text(row, "concept_name", "name", "concept", "index_name") for row in concept_rows]
    industry_tags = [_first_text(row, "industry_name", "index_name", "name", "level_name") for row in industry_rows]
    ths_tags = [_first_text(row, "ths_name", "index_name", "name") for row in ths_rows]
    dc_tags = [_first_text(row, "dc_name", "index_name", "name") for row in dc_rows]
    business = _business_quality(business_rows)
    event_risks = _event_risk_values(
        pledge_stat_rows,
        pledge_detail_rows,
        share_float_rows,
        block_trade_rows,
        repurchase_rows,
        audit_rows,
        report_rows,
    )
    margin_activity = _margin_activity(margin_detail_rows, margin_sec_rows, margin)
    technical_chips = _technical_chips(stk_rows, cyq_perf_rows, cyq_chip_rows)
    execution_constraints = _execution_constraint_values(execution_rows, price_limit_rows, technical_chips)
    northbound_top10 = _northbound_top10_activity(hsgt_top10_rows)
    return {
        "code": c,
        "trade_date_used": _trade_date_used(trade_date),
        "company_profile": {
            "name": _first_text(company, "name", "stock_name", "short_name"),
            "full_name": _first_text(company, "fullname", "full_name", "company_name"),
            "industry": _first_text(company, "industry"),
            "area": _first_text(company, "area", "province", "city"),
            "main_business": _first_text(company, "main_business", "main_biz", "business"),
            "list_date": _first_text(company, "list_date"),
            "name_changes": [
                {
                    "name": _first_text(row, "name", "sec_name", "change_name"),
                    "start_date": _first_text(row, "start_date", "begin_date"),
                    "end_date": _first_text(row, "end_date"),
                    "reason": _first_text(row, "change_reason", "reason"),
                }
                for row in name_changes
            ],
            "data_available": bool(company_rows),
        },
        "theme_exposure": {
            "concepts": [item for item in dict.fromkeys(concept_tags) if item][:12],
            "industries": [item for item in dict.fromkeys(industry_tags) if item][:8],
            "ths": [item for item in dict.fromkeys(ths_tags) if item][:8],
            "dc": [item for item in dict.fromkeys(dc_tags) if item][:8],
            "data_available": bool(concept_rows or industry_rows or ths_rows or dc_rows),
        },
        "business_quality": business,
        "event_risks": event_risks,
        "market_activity": {
            "top_list_hits_20d": len(top_list),
            "top_list_hits_60d": len(top_list),
            "top_inst_net_buy": inst_net,
            "block_trade_count": event_risks["block_trade_count"],
            "block_trade_average_discount_pct": event_risks["block_trade_average_discount_pct"],
            "northbound_top10": northbound_top10,
        },
        "margin_activity": margin_activity,
        "technical_chips": technical_chips,
        "execution_constraints": execution_constraints,
        "pe_ttm": _safe_float(valuation.get("pe_ttm") or valuation.get("pe")),
        "pb": _safe_float(valuation.get("pb")),
        "total_mv_yi": _safe_float(valuation.get("total_mv_yi")),
        "circ_mv_yi": _safe_float(valuation.get("circ_mv_yi")),
        "roe": _safe_float(indicator.get("roe")),
        "roe_waa": _safe_float(indicator.get("roe_waa")),
        "debt_to_assets": _safe_float(indicator.get("debt_to_assets")),
        "grossprofit_margin": _safe_float(indicator.get("grossprofit_margin")),
        "netprofit_margin": _safe_float(indicator.get("netprofit_margin")),
        "turnover_rate": _safe_float(liquidity.get("turnover_rate_f") or liquidity.get("turnover_rate")),
        "volume_ratio": _safe_float(liquidity.get("volume_ratio")),
        "main_net_yi": _safe_float(capital.get("main_net_yi")),
        "five_day_main_net_yi": _five_day_main_net(c, trade_date),
        "index_memberships": _index_memberships(trade_date, c),
        "index_data_available": _resolve_trade_date("index.weight", trade_date) is not None,
        "top_list_hits_20d": len(top_list),
        "top_list_hits_60d": len(top_list),
        "top_inst_net_buy": inst_net,
        "north_money": _safe_float(hsgt.get("north_money")),
        "hsgt_top10_net_buy": northbound_top10["latest_net_buy"],
        "margin_balance": _safe_float(margin.get("rzrqye")),
        "theme_count": len([item for item in concept_tags + industry_tags + ths_tags + dc_tags if item]),
        "pledge_ratio": event_risks["pledge_ratio"],
        "share_float_total_mv": event_risks["share_float_total_mv"],
        "block_trade_average_discount_pct": event_risks["block_trade_average_discount_pct"],
        "audit_abnormal": event_risks["audit_abnormal"],
        "report_downgrade": event_risks["report_downgrade"],
        "repurchase_count": event_risks["repurchase_count"],
        "margin_balance_change": margin_activity["balance_change"],
        "is_margin_target": margin_activity["is_margin_target"],
        "chip_winner_rate": technical_chips["winner_rate"],
        "chip_pressure_ratio": technical_chips["pressure_ratio"],
        "is_suspended": execution_constraints["is_suspended"],
        "is_st": execution_constraints["is_st"],
        "is_limit_up": execution_constraints["is_limit_up"],
        "is_limit_down": execution_constraints["is_limit_down"],
    }


DIMENSION_WEIGHTS = {
    "quality": 20.0,
    "capital_flow": 20.0,
    "valuation": 15.0,
    "liquidity": 10.0,
    "index": 8.0,
    "dragon_tiger": 5.0,
    "theme": 7.0,
    "event_risk": 7.0,
    "margin": 4.0,
    "chips": 4.0,
}

PRIORITY_ADJUSTMENT_CAP = 6.0
PRIORITY_ADJUSTMENT_K = 0.12
RISK_FLAG_PENALTY = 1.5
RISK_PRIORITY_PENALTY_CAP = 4.5
MIN_COMPLETENESS_FOR_SCORE = 0.30
MIN_COMPLETENESS_FOR_POSITIVE_ADJUSTMENT = 0.45

RISK_LEVEL_ORDER = {"info": 0, "warn": 1, "degrade": 2, "block": 3}
RISK_LEVEL_LABELS = {
    "info": "只展示",
    "warn": "风险提醒",
    "degrade": "候选降级",
    "block": "硬执行约束",
}
RISK_LEVEL_PRIORITY_PENALTY = {
    "info": 0.0,
    "warn": 1.0,
    "degrade": 2.5,
    "block": 3.5,
}

_RISK_DATASET_LABELS = {
    "execution.flags": "执行标记",
    "price_limit.daily": "涨跌停价",
    "corporate_action.share_float": "限售解禁",
    "corporate_action.pledge_stat": "质押统计",
    "corporate_action.pledge_detail": "质押明细",
    "financial.audit": "审计意见",
    "market.block_trade": "大宗交易",
    "market.margin_detail": "两融明细",
    "market.margin_secs": "两融标的",
    "market.top_list": "龙虎榜",
    "market.top_inst": "龙虎榜机构席位",
    "technical.cyq_perf": "筹码表现",
    "technical.cyq_chips": "筹码明细",
    "research.report_rc": "研报评级",
    "factor.missing": "因子覆盖",
}

_RISK_DISPLAY_ONLY_DATASETS = {
    "corporate_action.share_float",
    "corporate_action.pledge_stat",
    "corporate_action.pledge_detail",
    "financial.audit",
    "market.block_trade",
    "market.margin_detail",
    "market.margin_secs",
    "market.top_list",
    "market.top_inst",
    "technical.cyq_perf",
    "technical.cyq_chips",
    "research.report_rc",
    "factor.missing",
}



def _band(value: float | None, points: list[tuple[float, float]]) -> float | None:
    """points: ascending (threshold, score). Bands are upper-inclusive — a value equal to a threshold gets that threshold's score; values above the last threshold get the last score."""
    if value is None:
        return None
    for threshold, score in points:
        if value <= threshold:
            return score
    return points[-1][1]


def _score_quality(v):
    roe = v.get("roe") if v.get("roe") is not None else v.get("roe_waa")
    if roe is None:
        return None, "ROE 数据缺失"
    base = _band(roe, [(0, 5.0), (5, 35.0), (8, 55.0), (12, 75.0), (15, 90.0), (1e9, 100.0)])
    debt = v.get("debt_to_assets")
    if debt is not None and debt >= 70:
        base = max(0.0, base - 15.0)
    return base, f"ROE {roe:.1f}%" + (f"，资产负债率 {debt:.0f}%" if debt is not None else "")


def _score_capital_flow(v, pool_stats):
    main = v.get("main_net_yi")
    five = v.get("five_day_main_net_yi")
    if main is None and five is None:
        return None, "资金流数据缺失"
    score = 50.0
    if main is not None:
        score += 20.0 if main > 0 else -20.0
    if five is not None:
        score += 15.0 if five > 0 else -15.0
    if pool_stats and pool_stats.get("five_day_main_net_yi_median") is not None and five is not None:
        score += 10.0 if five >= pool_stats["five_day_main_net_yi_median"] else -5.0
    score = max(0.0, min(100.0, score))
    return score, f"当日主力 {_fmt_num(main)} 亿，5日 {_fmt_num(five)} 亿"


def _score_valuation(v):
    pe, pb = v.get("pe_ttm"), v.get("pb")
    if pe is None and pb is None:
        return None, "估值数据缺失"
    parts, score, n = [], 0.0, 0
    if pe is not None:
        score += _band(pe if pe > 0 else 1e9, [(15, 100.0), (25, 80.0), (40, 55.0), (60, 30.0), (1e9, 10.0)]); n += 1
        parts.append(f"PE {pe:.1f}")
    if pb is not None:
        score += _band(pb, [(1.5, 100.0), (3, 80.0), (5, 55.0), (8, 30.0), (1e9, 15.0)]); n += 1
        parts.append(f"PB {pb:.1f}")
    return score / n, "，".join(parts)


def _score_liquidity(v, pool_stats):
    tr, vr = v.get("turnover_rate"), v.get("volume_ratio")
    if tr is None and vr is None:
        return None, "流动性数据缺失"
    score = 50.0
    if tr is not None:
        score += 20.0 if 0.3 <= tr <= 8 else -10.0
    if vr is not None:
        score += 15.0 if vr >= 1.0 else -5.0
    return max(0.0, min(100.0, score)), f"换手 {_fmt_num(tr)}%，量比 {_fmt_num(vr)}"


def _score_index(v):
    members = v.get("index_memberships") or []
    if members:
        weight = sum((m.get("weight") or 0.0) for m in members)
        names = "/".join(m["index"] for m in members)
        return min(100.0, 60.0 + weight * 4.0), f"{names} 成分，权重合计 {weight:.2f}%"
    if v.get("index_data_available"):
        return 30.0, "非主要指数成分"     # index data present, stock genuinely not a member → weak but real signal
    return None, "指数数据缺失"            # no index.weight data at all → dimension unavailable (never fabricate)


def _score_dragon_tiger(v):
    hits = v.get("top_list_hits_60d") or 0
    net = v.get("top_inst_net_buy")
    if hits == 0 and net is None:
        return None, "近窗口无龙虎榜记录"
    # NOTE: institutional net-buy intentionally both lifts this score and raises the
    # 短线脉冲风险 flag in _derive_risk_flags — bullish but pump-prone. Not a contradiction.
    score = 50.0 + (15.0 if net and net > 0 else (-10.0 if net and net < 0 else 0.0))
    return max(0.0, min(100.0, score)), f"龙虎榜命中 {hits} 次" + ("，机构净买入" if net and net > 0 else ("，机构净卖出" if net and net < 0 else ""))


def _score_theme(v):
    exposure = v.get("theme_exposure") or {}
    if not exposure.get("data_available"):
        return None, "主题/行业数据缺失"
    concepts = len(exposure.get("concepts") or [])
    industries = len(exposure.get("industries") or [])
    boards = len(exposure.get("ths") or []) + len(exposure.get("dc") or [])
    score = 45.0 + min(concepts, 5) * 6.0 + min(industries, 2) * 6.0 + min(boards, 4) * 3.0
    return max(0.0, min(100.0, score)), f"概念 {concepts} 个，行业 {industries} 个，板块 {boards} 个"


def _score_event_risk(v):
    event = v.get("event_risks") or {}
    if not event.get("data_available"):
        return None, "事件风险数据缺失"
    score = 90.0
    details = []
    pledge = event.get("pledge_ratio")
    if pledge is not None:
        details.append(f"质押 {pledge:.1f}%")
        if pledge >= 50:
            score -= 35.0
        elif pledge >= 30:
            score -= 20.0
    float_mv = event.get("share_float_total_mv")
    if float_mv is not None:
        details.append(f"解禁市值 {_fmt_num(float_mv)}")
        if float_mv >= 50:
            score -= 20.0
        elif float_mv >= 10:
            score -= 10.0
    discount = event.get("block_trade_average_discount_pct")
    if discount is not None:
        details.append(f"大宗折溢价 {discount:.1f}%")
        if discount <= -8:
            score -= 20.0
        elif discount <= -5:
            score -= 12.0
    if event.get("audit_abnormal"):
        score -= 35.0
        details.append("审计异常")
    if event.get("report_downgrade"):
        score -= 12.0
        details.append("研报预期下修")
    if event.get("repurchase_count"):
        score += 6.0
        details.append("回购支撑")
    return max(0.0, min(100.0, score)), "，".join(details) if details else "未见明显事件风险"


def _score_margin(v):
    margin = v.get("margin_activity") or {}
    if not margin.get("data_available"):
        return None, "两融数据缺失"
    change = margin.get("balance_change")
    balance = margin.get("balance")
    score = 65.0
    if change is not None:
        if change > 0:
            score += 8.0
        if change >= 3:
            score -= 18.0
        elif change <= -3:
            score -= 12.0
    if margin.get("is_margin_target"):
        score += 5.0
    return max(0.0, min(100.0, score)), f"融资余额 {_fmt_num(balance)}，变化 {_fmt_num(change)}"


def _score_chips(v):
    chips = v.get("technical_chips") or {}
    if not chips.get("data_available"):
        return None, "筹码数据缺失"
    winner = chips.get("winner_rate")
    pressure = chips.get("pressure_ratio")
    score = 60.0
    details = []
    if winner is not None:
        details.append(f"获利盘 {_fmt_num(winner)}")
        if winner >= 85:
            score -= 12.0
        elif winner <= 20:
            score -= 10.0
        else:
            score += 6.0
    if pressure is not None:
        details.append(f"成本压力 {pressure:.2f}")
        if pressure >= 1.08:
            score -= 18.0
        elif pressure <= 1.0:
            score += 8.0
    return max(0.0, min(100.0, score)), "，".join(details) if details else "筹码摘要可用"


def score_factor_values(values: dict[str, Any], pool_stats: dict[str, Any] | None = None) -> dict[str, Any]:
    scorers = {
        "quality": lambda: _score_quality(values),
        "capital_flow": lambda: _score_capital_flow(values, pool_stats),
        "valuation": lambda: _score_valuation(values),
        "liquidity": lambda: _score_liquidity(values, pool_stats),
        "index": lambda: _score_index(values),
        "dragon_tiger": lambda: _score_dragon_tiger(values),
        "theme": lambda: _score_theme(values),
        "event_risk": lambda: _score_event_risk(values),
        "margin": lambda: _score_margin(values),
        "chips": lambda: _score_chips(values),
    }
    breakdown, weighted, total_weight = {}, 0.0, 0.0
    for name, fn in scorers.items():
        score, detail = fn()
        weight = DIMENSION_WEIGHTS[name]
        available = score is not None
        if available:
            weighted += score * weight
            total_weight += weight
        breakdown[name] = {
            "score": round(score, 1) if available else None,
            "weight": weight,
            "contribution": round(score * weight / 100.0, 2) if available else 0.0,
            "detail": detail,
            "available": available,
        }
    completeness = total_weight / sum(DIMENSION_WEIGHTS.values())
    tushare_score = round(weighted / total_weight, 1) if total_weight > 0 and completeness >= MIN_COMPLETENESS_FOR_SCORE else None
    return {
        "tushare_score": tushare_score,
        "data_completeness": round(completeness, 2),
        "tushare_score_breakdown": breakdown,
    }


def _derive_tags(v: dict[str, Any]) -> list[str]:
    tags = []
    if (v.get("pe_ttm") or 0) and 0 < v["pe_ttm"] <= 20: tags.append("低PE")
    roe = v.get("roe") if v.get("roe") is not None else v.get("roe_waa")
    if roe is not None and roe >= 15: tags.append("高ROE")
    if (v.get("main_net_yi") or 0) > 0: tags.append("主力净流入")
    if (v.get("five_day_main_net_yi") or 0) > 0: tags.append("5日资金净流入")
    if any(m.get("index") == "000300.SH" for m in (v.get("index_memberships") or [])): tags.append("核心指数成分")
    for m in (v.get("index_memberships") or []):
        tags.append({"000300.SH": "沪深300成分", "000905.SH": "中证500成分", "000852.SH": "中证1000成分"}.get(m["index"], "指数成分"))
    if (v.get("top_list_hits_60d") or 0) > 0: tags.append("龙虎榜活跃")
    if (v.get("north_money") or 0) > 0 or (v.get("hsgt_top10_net_buy") or 0) > 0: tags.append("北向偏强")
    if (v.get("top_inst_net_buy") or 0) > 0: tags.append("机构席位净买")
    if (v.get("repurchase_count") or 0) > 0: tags.append("回购支撑")
    business = v.get("business_quality") or {}
    if business.get("data_available") and ((v.get("grossprofit_margin") or 0) >= 30 or (v.get("netprofit_margin") or 0) >= 10):
        tags.append("主营质量较好")
    if business.get("concentration_label"):
        tags.append(str(business["concentration_label"]))
    exposure = v.get("theme_exposure") or {}
    for item in (exposure.get("concepts") or [])[:2]:
        tags.append(f"热门概念:{item}")
    for item in (exposure.get("industries") or [])[:1]:
        tags.append(f"行业:{item}")
    return list(dict.fromkeys(tags))


def _derive_risk_flags(v: dict[str, Any]) -> list[str]:
    flags = []
    execution = v.get("execution_constraints") or {}
    if execution.get("is_suspended"): flags.append("停牌不可交易")
    if execution.get("is_st"): flags.append("ST硬约束")
    if execution.get("is_limit_up"): flags.append("涨停买入受限")
    if execution.get("is_limit_down"): flags.append("跌停卖出受限")
    if (v.get("top_inst_net_buy") or 0) > 0: flags.append("短线脉冲风险(龙虎榜机构净买)")
    if v.get("pe_ttm") is not None and (v["pe_ttm"] > 60 or v["pe_ttm"] <= 0): flags.append("估值偏高")
    if v.get("debt_to_assets") is not None and v["debt_to_assets"] >= 70: flags.append("高负债")
    if (v.get("main_net_yi") or 0) < 0 and (v.get("five_day_main_net_yi") or 0) < 0: flags.append("资金净流出")
    if v.get("turnover_rate") is not None and v["turnover_rate"] < 0.3: flags.append("流动性偏弱")
    if v.get("share_float_total_mv") is not None and v["share_float_total_mv"] >= 10: flags.append("解禁压力")
    if v.get("pledge_ratio") is not None and v["pledge_ratio"] >= 30: flags.append("股权质押风险")
    if v.get("audit_abnormal"): flags.append("审计异常")
    if v.get("block_trade_average_discount_pct") is not None and v["block_trade_average_discount_pct"] <= -5: flags.append("大宗折价")
    if v.get("margin_balance_change") is not None:
        if v["margin_balance_change"] >= 3:
            flags.append("两融过热")
        elif v["margin_balance_change"] <= -3:
            flags.append("融资撤退")
    if v.get("chip_winner_rate") is not None and (v["chip_winner_rate"] >= 85 or v["chip_winner_rate"] <= 20): flags.append("筹码压力")
    if v.get("chip_pressure_ratio") is not None and v["chip_pressure_ratio"] >= 1.08: flags.append("筹码压力")
    if v.get("report_downgrade"): flags.append("研报预期下修")
    core = [v.get("pe_ttm"), v.get("roe"), v.get("main_net_yi"), v.get("turnover_rate")]
    if sum(1 for x in core if x is None) >= 3: flags.append("数据缺失")
    return list(dict.fromkeys(flags))


def _risk_item(
    *,
    code: str,
    label: str,
    level: str,
    reason: str,
    dataset: str,
    value: Any = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "label": label,
        "level": level if level in RISK_LEVEL_ORDER else "info",
        "level_label": RISK_LEVEL_LABELS.get(level, "只展示"),
        "reason": reason,
        "dataset": dataset,
        "dataset_label": _RISK_DATASET_LABELS.get(dataset, dataset),
        "value": value,
        "evidence": evidence or {},
        "hard_block": level == "block" and dataset in {"execution.flags", "price_limit.daily"},
        "display_only": dataset in _RISK_DISPLAY_ONLY_DATASETS,
    }


def _max_level(items: list[dict[str, Any]]) -> str:
    if not items:
        return "info"
    return max((str(item.get("level") or "info") for item in items), key=lambda level: RISK_LEVEL_ORDER.get(level, 0))


def _dedupe_risk_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        key = str(item.get("code") or item.get("label") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def derive_risk_policy(values: dict[str, Any], risk_flags: list[str] | None = None) -> dict[str, Any]:
    """Translate factor values into Prism's conservative risk levels.

    ``block`` is reserved for execution-impossible facts from
    ``execution.flags`` / ``price_limit.daily``.  Other Tushare extensions
    can warn or degrade a candidate, but never enlarge formal readiness nor
    hard-block real-money permissions on their own.
    """

    items: list[dict[str, Any]] = []
    flags = list(risk_flags or [])
    execution = values.get("execution_constraints") or {}
    if execution.get("is_suspended"):
        items.append(_risk_item(
            code="execution_suspended",
            label="停牌不可交易",
            level="block",
            reason="execution.flags 显示停牌，今天不能执行买卖。",
            dataset="execution.flags",
            evidence={"trading_status": execution.get("trading_status"), "blockers": execution.get("execution_blockers")},
        ))
    if execution.get("is_st"):
        items.append(_risk_item(
            code="execution_st",
            label="ST硬约束",
            level="block",
            reason="execution.flags 显示 ST/退市风险标签，按硬执行约束处理。",
            dataset="execution.flags",
            evidence={"st_name": execution.get("st_name"), "st_type_name": execution.get("st_type_name")},
        ))
    if execution.get("is_limit_up"):
        items.append(_risk_item(
            code="execution_limit_up",
            label="涨停买入受限",
            level="block",
            reason="price_limit.daily / execution.flags 显示触及涨停，追买成交可行性不足。",
            dataset="price_limit.daily",
            evidence={"close": execution.get("close"), "up_limit": execution.get("up_limit")},
        ))
    if execution.get("is_limit_down"):
        items.append(_risk_item(
            code="execution_limit_down",
            label="跌停卖出受限",
            level="block",
            reason="price_limit.daily / execution.flags 显示触及跌停，退出流动性受限。",
            dataset="price_limit.daily",
            evidence={"close": execution.get("close"), "down_limit": execution.get("down_limit")},
        ))

    pledge = values.get("pledge_ratio")
    if pledge is not None and pledge >= 30:
        level = "degrade" if pledge >= 45 else "warn"
        items.append(_risk_item(
            code="pledge_pressure",
            label="股权质押风险",
            level=level,
            reason=f"质押比例 {pledge:.1f}% 已进入风险区间，候选需要降级或加强复核。" if level == "degrade" else f"质押比例 {pledge:.1f}%，需要在放行前提示。",
            dataset="corporate_action.pledge_stat",
            value=pledge,
        ))

    float_mv = values.get("share_float_total_mv")
    if float_mv is not None and float_mv >= 10:
        level = "degrade" if float_mv >= 50 else "warn"
        items.append(_risk_item(
            code="share_float_pressure",
            label="解禁压力",
            level=level,
            reason=f"近窗口解禁市值约 {_fmt_num(float_mv)}，供给压力较高。" if level == "degrade" else f"近窗口解禁市值约 {_fmt_num(float_mv)}，放行前需提示。",
            dataset="corporate_action.share_float",
            value=float_mv,
        ))

    if values.get("audit_abnormal"):
        items.append(_risk_item(
            code="audit_abnormal",
            label="审计异常",
            level="degrade",
            reason="审计意见出现非标/强调等异常表述，候选降级为谨慎观察。",
            dataset="financial.audit",
            evidence={"audit_opinion": (values.get("event_risks") or {}).get("audit_opinion")},
        ))

    discount = values.get("block_trade_average_discount_pct")
    if discount is not None and discount <= -5:
        level = "degrade" if discount <= -8 else "warn"
        items.append(_risk_item(
            code="block_trade_discount",
            label="大宗折价",
            level=level,
            reason=f"近窗口大宗平均折价 {discount:.1f}%，存在供给压力。" if level == "degrade" else f"近窗口大宗折价 {discount:.1f}%，放行前需提示。",
            dataset="market.block_trade",
            value=discount,
        ))

    margin_change = values.get("margin_balance_change")
    if margin_change is not None:
        if margin_change >= 3:
            items.append(_risk_item(
                code="margin_overheat",
                label="两融过热",
                level="degrade",
                reason=f"融资余额近窗口增加 {_fmt_num(margin_change)}，杠杆过热，候选降级观察。",
                dataset="market.margin_detail",
                value=margin_change,
            ))
        elif margin_change <= -3:
            items.append(_risk_item(
                code="margin_withdrawal",
                label="融资撤退",
                level="degrade",
                reason=f"融资余额近窗口减少 {_fmt_num(margin_change)}，杠杆资金撤退，候选降级观察。",
                dataset="market.margin_detail",
                value=margin_change,
            ))

    if (values.get("top_inst_net_buy") or 0) > 0 or (values.get("top_list_hits_60d") or 0) > 0:
        items.append(_risk_item(
            code="dragon_tiger_pulse",
            label="短线脉冲风险",
            level="warn",
            reason="龙虎榜/机构席位活跃，可能是短线脉冲，排序只做提醒和小幅扣分。",
            dataset="market.top_list",
            evidence={"top_list_hits_60d": values.get("top_list_hits_60d"), "top_inst_net_buy": values.get("top_inst_net_buy")},
        ))

    winner = values.get("chip_winner_rate")
    pressure = values.get("chip_pressure_ratio")
    if (winner is not None and (winner >= 85 or winner <= 20)) or (pressure is not None and pressure >= 1.08):
        level = "degrade" if (pressure is not None and pressure >= 1.12) or (winner is not None and winner >= 92) else "warn"
        items.append(_risk_item(
            code="chip_pressure",
            label="筹码压力",
            level=level,
            reason="筹码获利盘或成本压力偏高，先降低执行优先级。" if level == "degrade" else "筹码结构需要提示，避免把短线拥挤当作稳态机会。",
            dataset="technical.cyq_perf",
            evidence={"winner_rate": winner, "pressure_ratio": pressure},
        ))

    if values.get("report_downgrade"):
        items.append(_risk_item(
            code="report_downgrade",
            label="研报预期下修",
            level="warn",
            reason="近期研报评级/标题出现下调信号，仅作为人工复核提醒。",
            dataset="research.report_rc",
        ))

    if "数据缺失" in flags:
        items.append(_risk_item(
            code="factor_data_missing",
            label="数据缺失",
            level="info",
            reason="部分扩展因子缺失，只降低证据完整度，不做重罚。",
            dataset="factor.missing",
        ))

    items = _dedupe_risk_items(items)
    risk_level = _max_level(items)
    block_reason = next((item["reason"] for item in items if item.get("level") == "block"), "")
    degrade_reason = next((item["reason"] for item in items if item.get("level") == "degrade"), "")
    item_flags = [str(item.get("label") or "") for item in items if item.get("label")]
    merged_flags = list(dict.fromkeys([*item_flags, *flags]))
    evidence_refs = [
        {
            "kind": "risk_dataset",
            "dataset": item.get("dataset"),
            "label": item.get("dataset_label"),
            "risk_label": item.get("label"),
            "level": item.get("level"),
            "reason": item.get("reason"),
            "display_only": bool(item.get("display_only")),
            "hard_block": bool(item.get("hard_block")),
        }
        for item in items
    ]
    source_cards = [
        {
            "dataset": item.get("dataset"),
            "label": item.get("dataset_label"),
            "risk_label": item.get("label"),
            "risk_level": item.get("level"),
            "decision_use": "hard_gate" if item.get("hard_block") else "risk_penalty",
            "live_permission": "formal_candidate" if item.get("hard_block") else "research_only",
            "detail": item.get("reason"),
            "hard_block": bool(item.get("hard_block")),
            "display_only": bool(item.get("display_only")),
        }
        for item in items
    ]
    return {
        "risk_level": risk_level,
        "risk_level_label": RISK_LEVEL_LABELS.get(risk_level, "只展示"),
        "risk_flags": merged_flags,
        "risk_items": items,
        "degrade_reason": degrade_reason,
        "block_reason": block_reason,
        "evidence_refs": evidence_refs,
        "source_cards": source_cards,
    }


def risk_priority_penalty(factor_bundle: dict[str, Any] | None) -> float:
    if not isinstance(factor_bundle, dict) or not factor_bundle:
        return 0.0
    items = factor_bundle.get("risk_items") or []
    if isinstance(items, list) and items:
        penalty = sum(RISK_LEVEL_PRIORITY_PENALTY.get(str(item.get("level") or "info"), 0.0) for item in items if isinstance(item, dict))
        return round(min(RISK_PRIORITY_PENALTY_CAP, max(0.0, penalty)), 2)
    flags = [
        str(flag or "").strip()
        for flag in (factor_bundle.get("risk_flags") or [])
        if str(flag or "").strip() and str(flag or "").strip() != "数据缺失"
    ]
    return round(min(RISK_PRIORITY_PENALTY_CAP, len(flags[:3]) * RISK_FLAG_PENALTY), 2)


def _evidence_block(available: bool, values: dict[str, Any], interpretation: str) -> dict[str, Any]:
    return {"values": values, "interpretation": interpretation if available else "数据缺失/不可用", "available": available}


def _build_explanation(v, scored, tags, risk_flags) -> dict[str, Any]:
    bd = scored["tushare_score_breakdown"]
    supporting = [bd[d]["detail"] for d in ("quality", "valuation", "capital_flow", "index", "theme") if bd.get(d, {}).get("available")]
    roe = v.get("roe") if v.get("roe") is not None else v.get("roe_waa")
    fundamental = _evidence_block(
        roe is not None or v.get("pe_ttm") is not None,
        {"pe_ttm": v.get("pe_ttm"), "pb": v.get("pb"), "roe": roe, "debt_to_assets": v.get("debt_to_assets")},
        bd["quality"]["detail"] if bd["quality"]["available"] else bd["valuation"]["detail"],
    )
    capital = _evidence_block(
        v.get("main_net_yi") is not None or v.get("five_day_main_net_yi") is not None,
        {"main_net_yi": v.get("main_net_yi"), "five_day_main_net_yi": v.get("five_day_main_net_yi")},
        bd["capital_flow"]["detail"],
    )
    trading = _evidence_block(
        (v.get("top_list_hits_60d") or 0) > 0 or v.get("top_inst_net_buy") is not None,
        {"top_list_hits_60d": v.get("top_list_hits_60d"), "top_inst_net_buy": v.get("top_inst_net_buy")},
        bd["dragon_tiger"]["detail"],
    )
    members = v.get("index_memberships") or []
    index_block = _evidence_block(bool(members), {"index_memberships": members}, bd["index"]["detail"])
    exposure = v.get("theme_exposure") or {}
    theme_block = _evidence_block(
        bool(exposure.get("data_available")),
        {"concepts": exposure.get("concepts") or [], "industries": exposure.get("industries") or []},
        bd["theme"]["detail"],
    )
    event = v.get("event_risks") or {}
    event_block = _evidence_block(
        bool(event.get("data_available")),
        {
            "pledge_ratio": event.get("pledge_ratio"),
            "share_float_total_mv": event.get("share_float_total_mv"),
            "block_trade_average_discount_pct": event.get("block_trade_average_discount_pct"),
            "audit_abnormal": event.get("audit_abnormal"),
            "report_downgrade": event.get("report_downgrade"),
        },
        bd["event_risk"]["detail"],
    )
    margin = v.get("margin_activity") or {}
    margin_block = _evidence_block(
        bool(margin.get("data_available")),
        {"balance": margin.get("balance"), "balance_change": margin.get("balance_change"), "is_margin_target": margin.get("is_margin_target")},
        bd["margin"]["detail"],
    )
    chips = v.get("technical_chips") or {}
    chips_block = _evidence_block(
        bool(chips.get("data_available")),
        {"winner_rate": chips.get("winner_rate"), "pressure_ratio": chips.get("pressure_ratio")},
        bd["chips"]["detail"],
    )
    execution = v.get("execution_constraints") or {}
    execution_block = _evidence_block(
        bool(execution.get("data_available")),
        {
            "is_suspended": execution.get("is_suspended"),
            "is_st": execution.get("is_st"),
            "is_limit_up": execution.get("is_limit_up"),
            "is_limit_down": execution.get("is_limit_down"),
            "close": execution.get("close"),
            "up_limit": execution.get("up_limit"),
            "down_limit": execution.get("down_limit"),
        },
        "停牌/ST/涨跌停执行约束已命中" if any(execution.get(key) for key in ("is_suspended", "is_st", "is_limit_up", "is_limit_down")) else "未见硬执行约束",
    )
    score = scored["tushare_score"]
    return {
        "entry_reason": (f"综合因子评分 {score}，" + ("、".join(tags[:3]) if tags else "基础面达标")) if score is not None else "因子数据不足，仅作观察",
        "upgrade_condition": "资金面持续净流入且执行质量确认（盘中放量站稳关键位）后再考虑升级。",
        "abandon_condition": "出现资金净流出、跌破关键支撑或基本面恶化（ROE 下滑/负债攀升）则放弃。",
        "supporting_evidence": supporting,
        "counter_risks": list(risk_flags),
        "evidence": {
            "fundamental": fundamental,
            "capital": capital,
            "trading_anomaly": trading,
            "index_weight": index_block,
            "theme": theme_block,
            "event_risk": event_block,
            "margin": margin_block,
            "chips": chips_block,
            "execution": execution_block,
        },
    }


_POOL_FIELDS = ("five_day_main_net_yi", "turnover_rate", "roe")


def compute_pool_stats(values_list: list[dict[str, Any]]) -> dict[str, Any]:
    stats: dict[str, Any] = {}
    for field in _POOL_FIELDS:
        nums = sorted(x[field] for x in values_list if isinstance(x.get(field), (int, float)))
        if nums:
            stats[f"{field}_median"] = statistics.median(nums)
            stats[f"{field}_p75"] = nums[min(len(nums) - 1, int(len(nums) * 0.75))]
    return stats


def _pool_standing(values: dict[str, Any], pool_stats: dict[str, Any] | None) -> dict[str, str] | None:
    if not pool_stats:
        return None
    out: dict[str, str] = {}
    for field in _POOL_FIELDS:
        val, med, p75 = values.get(field), pool_stats.get(f"{field}_median"), pool_stats.get(f"{field}_p75")
        if val is None or med is None:
            continue
        out[field] = "top_quartile" if (p75 is not None and val >= p75) else ("above_median" if val >= med else "below_median")
    return out


def _snapshot_from_values(v: dict[str, Any]) -> dict[str, Any]:
    return {
        "company_profile": v.get("company_profile") or {},
        "theme_exposure": v.get("theme_exposure") or {},
        "business_quality": v.get("business_quality") or {},
        "event_risks": v.get("event_risks") or {},
        "market_activity": v.get("market_activity") or {},
        "margin_activity": v.get("margin_activity") or {},
        "technical_chips": v.get("technical_chips") or {},
        "execution_constraints": v.get("execution_constraints") or {},
        "valuation": {"pe_ttm": v.get("pe_ttm"), "pb": v.get("pb"), "total_mv_yi": v.get("total_mv_yi")},
        "liquidity": {"turnover_rate": v.get("turnover_rate"), "volume_ratio": v.get("volume_ratio")},
        "capital_flow": {"main_net_yi": v.get("main_net_yi"), "five_day_main_net_yi": v.get("five_day_main_net_yi")},
        "fundamentals": {"roe": v.get("roe"), "roe_waa": v.get("roe_waa"), "debt_to_assets": v.get("debt_to_assets"),
                         "grossprofit_margin": v.get("grossprofit_margin"), "netprofit_margin": v.get("netprofit_margin")},
        "index_membership": v.get("index_memberships") or [],
        "top_list_activity": {"hits_20d": v.get("top_list_hits_20d"), "hits_60d": v.get("top_list_hits_60d")},
        "top_inst_activity": {"net_buy": v.get("top_inst_net_buy")},
        "market_context": {"north_money": v.get("north_money"), "margin_balance": v.get("margin_balance")},
    }


def compute_factor_bundle(code: str, trade_date: str | None, *, pool_stats: dict | None = None,
                          values: dict | None = None) -> dict[str, Any]:
    v = values if values is not None else extract_factor_values(code, trade_date)
    scored = score_factor_values(v, pool_stats)
    tags = _derive_tags(v)
    risk_flags = _derive_risk_flags(v)
    risk_policy = derive_risk_policy(v, risk_flags)
    risk_flags = risk_policy["risk_flags"]
    return {
        "tushare_score": scored["tushare_score"],
        "data_completeness": scored["data_completeness"],
        "tushare_score_breakdown": scored["tushare_score_breakdown"],
        "factor_tags": tags,
        "risk_flags": risk_flags,
        "risk_level": risk_policy["risk_level"],
        "risk_level_label": risk_policy["risk_level_label"],
        "risk_items": risk_policy["risk_items"],
        "degrade_reason": risk_policy["degrade_reason"],
        "block_reason": risk_policy["block_reason"],
        "risk_evidence_refs": risk_policy["evidence_refs"],
        "risk_source_cards": risk_policy["source_cards"],
        "explanation": _build_explanation(v, scored, tags, risk_flags),
        "factor_snapshot": _snapshot_from_values(v),
        "trade_date_used": v.get("trade_date_used"),
        "pool_standing": _pool_standing(v, pool_stats),
    }


def build_factor_snapshot(code: str, trade_date: str | None) -> dict[str, Any]:
    b = compute_factor_bundle(code, trade_date)
    return {k: b[k] for k in (
        "tushare_score", "data_completeness", "factor_tags", "risk_flags",
        "tushare_score_breakdown",
        "risk_level", "degrade_reason", "block_reason", "risk_evidence_refs",
        "factor_snapshot", "trade_date_used",
    )}
