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
        "top_list_hits_20d": len(top_list),
        "top_list_hits_60d": len(top_list),
        "top_inst_net_buy": inst_net,
        "north_money": _safe_float(hsgt.get("north_money")),
        "margin_balance": _safe_float(margin.get("rzrqye")),
    }
