# packages/screener/tushare_factors.py
"""Tushare factor layer: read datasets → normalized factor values → score / tags / explanation.

Self-contained and read-only. Imports only stdlib + prism_data (never apps/control-panel).
Never raises on missing/NaN data; every factor value is Optional.
"""
from __future__ import annotations

import json
import math
import os
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
    inst_net = sum((_safe_float(r.get("net_buy")) or 0.0) for r in top_inst) if top_inst else None
    return {
        "code": c,
        "trade_date_used": _resolve_trade_date("valuation.daily", trade_date),
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
        "margin_balance": _safe_float(margin.get("rzrqye")),
    }


DIMENSION_WEIGHTS = {
    "quality": 25.0, "capital_flow": 25.0, "valuation": 20.0,
    "liquidity": 15.0, "index": 10.0, "dragon_tiger": 5.0,
}


def _band(value: float | None, points: list[tuple[float, float]]) -> float | None:
    """points: ascending (threshold, score); return score for first threshold >= value, else last."""
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
    return score, f"当日主力 {main if main is None else round(main,2)} 亿，5日 {five if five is None else round(five,2)} 亿"


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
    return max(0.0, min(100.0, score)), f"换手 {tr if tr is None else round(tr,2)}%，量比 {vr if vr is None else round(vr,2)}"


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
    score = 50.0 + (15.0 if net and net > 0 else (-10.0 if net and net < 0 else 0.0))
    return max(0.0, min(100.0, score)), f"龙虎榜命中 {hits} 次" + ("，机构净买入" if net and net > 0 else ("，机构净卖出" if net and net < 0 else ""))


def score_factor_values(values: dict[str, Any], pool_stats: dict[str, Any] | None = None) -> dict[str, Any]:
    scorers = {
        "quality": lambda: _score_quality(values),
        "capital_flow": lambda: _score_capital_flow(values, pool_stats),
        "valuation": lambda: _score_valuation(values),
        "liquidity": lambda: _score_liquidity(values, pool_stats),
        "index": lambda: _score_index(values),
        "dragon_tiger": lambda: _score_dragon_tiger(values),
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
    tushare_score = round(weighted / total_weight, 1) if total_weight > 0 else None
    return {
        "tushare_score": tushare_score,
        "data_completeness": round(total_weight / sum(DIMENSION_WEIGHTS.values()), 2),
        "tushare_score_breakdown": breakdown,
    }
