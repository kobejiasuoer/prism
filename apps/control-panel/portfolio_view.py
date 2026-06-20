"""Portfolio account view — extracted from dashboard_data.py.

Holds the portfolio/holding-review cluster. dashboard_data.py re-exports
everything here for backward-compatible imports. Cross-module dependencies on
dashboard_data internals are resolved via per-call _dd() lookup (re-resolved
each call so test monkeypatches on dashboard_data attributes propagate).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

import json
import sys
import re
from datetime import datetime
from typing import Any, Mapping

from account_book import ACCOUNT_MODES, compute_account_view, load_account_book  # type: ignore
from decision_ledger import (  # type: ignore  # local leaf module
    AttributionProviderConfig,
    DecisionLedgerError,
    _chat_completions_url,
    _extract_json_object,
    _provider_config,
    scan_all_decisions,
)
from money_utils import optional_round_money, round_money
from prism_data.utils import normalize_code
from readiness import expected_trade_date  # type: ignore


def _dd():
    # Resolve the SAME dashboard_data module instance that callers patch.
    # control_panel.dashboard_data (the shim path tests patch) and dashboard_data
    # (the sys.path path) can be distinct module objects; prefer the shim path
    # since that is what test_app_smoke patches, falling back to the sys.path one.
    for modname in ("control_panel.dashboard_data", "dashboard_data"):
        mod = sys.modules.get(modname)
        if mod is not None and hasattr(mod, "resolve_readiness"):
            return mod
    import dashboard_data as _module  # type: ignore
    return _module


def resolve_readiness(*a, **k): return _dd().resolve_readiness(*a, **k)
def load_today_action_decision_store(*a, **k): return _dd().load_today_action_decision_store(*a, **k)
def action_tone(*a, **k): return _dd().action_tone(*a, **k)
def public_portfolio_readiness(*a, **k): return _dd().public_portfolio_readiness(*a, **k)
def _holding_ai_review_store(): return _dd()._holding_ai_review_store()
def _holding_ai_review_save(s): return _dd()._holding_ai_review_save(s)
def _HOLDING_AI_REVIEW_VERSION(): return _dd()._HOLDING_AI_REVIEW_VERSION  # noqa: N802
def _today_base_inputs(): return _dd()._today_base_inputs()
# These are re-exported by dashboard_data; bridge them so test patches on
# dashboard_data.<name> propagate (same dual-import reason as above).
def get_data_gateway(*a, **k): return _dd().get_data_gateway(*a, **k)
def build_dataset_freshness_rows(*a, **k): return _dd().build_dataset_freshness_rows(*a, **k)
def build_formal_freshness_rows(*a, **k): return _dd().build_formal_freshness_rows(*a, **k)


# ---------------------------------------------------------------------------
# Portfolio account view (live readiness, real positions, real cash)
# ---------------------------------------------------------------------------


def _portfolio_code_aliases(value: Any) -> set[str]:
    code = str(value or "").strip().lower()
    if not code:
        return set()
    aliases = {code}
    bare = code[2:] if len(code) == 8 and code[:2].isalpha() else code
    aliases.add(bare)
    if len(bare) == 6 and bare.isdigit():
        aliases.add(f"sh{bare}" if bare.startswith("6") else f"sz{bare}")
    return aliases


def _portfolio_name_is_code_like(name: Any, code: Any) -> bool:
    text = str(name or "").strip().lower()
    if not text:
        return True
    aliases = _portfolio_code_aliases(code)
    return text in aliases or text in {"未命名标的", "unknown"}


def _portfolio_quote_index(
    codes: list[str],
    *,
    trade_date: str,
    refresh_quotes: bool,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    normalized_codes: list[str] = []
    for code in codes:
        try:
            normalized = normalize_code(code)
        except ValueError:
            continue
        if normalized not in normalized_codes:
            normalized_codes.append(normalized)

    empty_status = {
        "enabled": bool(refresh_quotes),
        "status": "not_requested" if not refresh_quotes else "no_positions",
        "message": "未刷新行情。" if not refresh_quotes else "当前没有持仓代码可刷新。",
        "requested_codes": normalized_codes,
        "updated_at": "",
        "trade_date": trade_date,
        "provider": "",
        "freshness_status": "",
        "live_small_allowed": False,
        "data_path": "",
        "manifest_path": "",
        "errors": [],
    }
    if not refresh_quotes or not normalized_codes:
        return {}, empty_status

    try:
        result = get_data_gateway().fetch_quotes_batch(
            normalized_codes,
            trade_date=trade_date,
            key="portfolio-quotes",
            allow_fallback=True,
        )
    except Exception as exc:
        return {}, {
            **empty_status,
            "status": "failed",
            "message": f"行情刷新失败：{exc}",
            "errors": [str(exc)],
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    manifest = dict(result.manifest or {})
    rows = result.data if isinstance(result.data, list) else []
    quote_index: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        aliases: set[str] = set()
        for raw in (row.get("symbol"), row.get("code")):
            try:
                aliases.add(normalize_code(raw))
            except ValueError:
                continue
        price = round_money(row.get("price"))
        if price <= 0:
            continue
        quote = {
            "code": next(iter(aliases), str(row.get("code") or "")),
            "name": str(row.get("name") or ""),
            "price": price,
            "change": optional_round_money(row.get("change")),
            "change_pct": optional_round_money(row.get("change_pct")),
            "trade_date": str(row.get("trade_date") or manifest.get("trade_date") or trade_date),
            "timestamp": str(row.get("timestamp") or manifest.get("asof") or manifest.get("fetched_at") or ""),
            "provider": str(manifest.get("provider") or ""),
        }
        for alias in aliases:
            quote_index[alias] = quote

    errors = []
    provider_error = result.provider_result.error
    if provider_error:
        errors.append(str(provider_error))
    missing = [code for code in normalized_codes if code not in quote_index]
    status = "ok" if quote_index and not missing else "partial" if quote_index else "failed"
    return quote_index, {
        **empty_status,
        "status": status,
        "message": "行情已刷新。" if status == "ok" else "部分持仓未取到行情。" if status == "partial" else "未取到可用行情。",
        "updated_at": str(manifest.get("fetched_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        "trade_date": str(manifest.get("trade_date") or trade_date),
        "provider": str(manifest.get("provider") or ""),
        "freshness_status": str(manifest.get("freshness_status") or ""),
        "live_small_allowed": bool(manifest.get("live_small_allowed")),
        "row_count": len(rows),
        "priced_count": len({quote["code"] for quote in quote_index.values()}),
        "missing_codes": missing,
        "data_path": str(result.data_path or ""),
        "manifest_path": str(result.manifest_path or ""),
        "errors": errors,
    }


def _attach_portfolio_market_values(
    positions: list[dict[str, Any]],
    quote_index: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for pos in positions:
        try:
            normalized = normalize_code(pos.get("code"))
        except ValueError:
            normalized = str(pos.get("code") or "")
        quote = quote_index.get(normalized)
        qty = int(pos.get("qty") or 0)
        cost_basis = round_money(pos.get("cost_basis"))
        realized = round_money(pos.get("realized_pnl"))
        current_price = round_money((quote or {}).get("price")) if quote else None
        market_value = round_money(qty * current_price) if current_price is not None else None
        unrealized = round_money((market_value or 0.0) - cost_basis) if market_value is not None else None
        total_pnl = round_money(realized + unrealized) if unrealized is not None else None
        quote_name = str((quote or {}).get("name") or "").strip()
        display_name = str(pos.get("name") or "").strip()
        if quote_name and _portfolio_name_is_code_like(display_name, pos.get("code")):
            display_name = quote_name
        enriched.append(
            {
                **pos,
                "name": display_name or str(pos.get("code") or ""),
                "current_price": current_price,
                "market_value": market_value,
                "unrealized_pnl": unrealized,
                "unrealized_pnl_pct": round_money((unrealized / cost_basis) * 100) if unrealized is not None and cost_basis else None,
                "total_pnl": total_pnl,
                "quote_change_pct": (quote or {}).get("change_pct") if quote else None,
                "quote_timestamp": (quote or {}).get("timestamp", "") if quote else "",
                "quote_trade_date": (quote or {}).get("trade_date", "") if quote else "",
                "quote_provider": (quote or {}).get("provider", "") if quote else "",
            }
        )
    return enriched


def _portfolio_latest_execution(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not events:
        return None
    event = max(
        events,
        key=lambda item: str(item.get("created_at") or item.get("trade_date") or ""),
    )
    return {
        "status": event.get("status"),
        "trade_date": event.get("trade_date"),
        "side": event.get("side"),
        "price": event.get("price"),
        "quantity": event.get("quantity"),
        "amount": event.get("amount"),
        "note": event.get("note"),
    }


def _portfolio_latest_outcome(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not events:
        return None
    rank = {"T+10": 4, "T+5": 3, "T+3": 2, "T+1": 1}
    event = max(
        events,
        key=lambda item: (
            rank.get(str(item.get("window") or "").upper(), 0),
            str(item.get("evaluated_at") or ""),
        ),
    )
    classification = event.get("classification") or {}
    market_data = event.get("market_data") or {}
    return {
        "window": event.get("window"),
        "as_of_trade_date": event.get("as_of_trade_date"),
        "label": classification.get("label"),
        "tone": classification.get("tone"),
        "return_pct": market_data.get("return_pct"),
        "relative_return_pct": market_data.get("relative_return_pct"),
    }


def _portfolio_decision_summary(record: dict[str, Any] | None) -> dict[str, Any] | None:
    if not record:
        return None
    stock = record.get("stock") or {}
    source = record.get("source") or {}
    recommendation = record.get("recommendation") or {}
    status = record.get("status") or {}
    execution_events = [dict(item) for item in (record.get("execution_events") or []) if isinstance(item, dict)]
    outcome_events = [dict(item) for item in (record.get("outcome_events") or []) if isinstance(item, dict)]
    return {
        "decision_id": record.get("decision_id"),
        "trade_date": record.get("trade_date"),
        "code": stock.get("code"),
        "name": stock.get("name"),
        "action": recommendation.get("action"),
        "action_label": recommendation.get("action_label"),
        "lane": source.get("lane"),
        "surface": source.get("surface"),
        "status": status.get("state"),
        "main_conclusion": recommendation.get("main_conclusion"),
        "latest_execution": _portfolio_latest_execution(execution_events),
        "latest_outcome": _portfolio_latest_outcome(outcome_events),
    }


def _portfolio_latest_decisions_by_code() -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    try:
        import decision_ledger  # type: ignore

        records, errors = decision_ledger.scan_all_decisions()
    except Exception as exc:
        return {}, [{"message": str(exc)}]
    records = [dict(item) for item in records if isinstance(item, dict)]
    records.sort(
        key=lambda record: (
            str(record.get("trade_date") or ""),
            str(record.get("decision_id") or ""),
        ),
        reverse=True,
    )
    latest: dict[str, dict[str, Any]] = {}
    for record in records:
        code = str(((record.get("stock") or {}).get("code")) or "").strip()
        if not code:
            continue
        for alias in _portfolio_code_aliases(code):
            latest.setdefault(alias, record)
    return latest, [dict(item) for item in errors if isinstance(item, dict)]


def _portfolio_watchlist_items(watchlist: dict[str, Any] | None) -> list[dict[str, Any]]:
    stocks = (watchlist or {}).get("stocks") or []
    if isinstance(stocks, dict):
        iterable = stocks.values()
    elif isinstance(stocks, list):
        iterable = stocks
    else:
        iterable = []
    return [dict(stock) for stock in iterable if isinstance(stock, dict)]


def _portfolio_watchlist_index(watchlist: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for stock in _portfolio_watchlist_items(watchlist):
        if not isinstance(stock, dict):
            continue
        for alias in _portfolio_code_aliases(stock.get("code")):
            index[alias] = stock
    return index


def _portfolio_first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, list):
            for item in value:
                text = str(item or "").strip()
                if text:
                    return text
            continue
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _portfolio_decision_text(decision: dict[str, Any] | None) -> str:
    recommendation = (decision or {}).get("recommendation") or {}
    return " ".join(
        str(value or "")
        for value in (
            recommendation.get("action"),
            recommendation.get("action_label"),
            recommendation.get("main_conclusion"),
            recommendation.get("risk_summary"),
            recommendation.get("stop_condition"),
        )
    )


def _portfolio_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _portfolio_optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _portfolio_default_plan_rules() -> dict[str, float | int]:
    return {
        "warning_loss_pct": -3.0,
        "defense_reduce_loss_pct": -5.0,
        "clear_loss_pct": -8.0,
        "profit_take_pct": 8.0,
        "max_hold_days": 5,
        "min_progress_pct": 1.0,
    }


def _portfolio_join_tokens(*values: Any) -> str:
    parts: list[str] = []
    for value in values:
        if isinstance(value, dict):
            parts.extend(str(v or "") for v in value.values())
        elif isinstance(value, list):
            parts.extend(str(item or "") for item in value)
        else:
            parts.append(str(value or ""))
    return " ".join(part.strip() for part in parts if part and part.strip())


def _portfolio_trade_level(stock: dict[str, Any] | None, key: str) -> float | None:
    if not stock:
        return None
    levels = stock.get("trade_levels") or {}
    if isinstance(levels, dict):
        value = levels.get(key)
        if value not in (None, ""):
            return _portfolio_optional_float(value)
    return _portfolio_optional_float(stock.get(key))


def _portfolio_market_regime(readiness: Mapping[str, Any] | None) -> str:
    mode = str((readiness or {}).get("readiness_mode") or "")
    session_key = str(((readiness or {}).get("session") or {}).get("key") or "")
    blockers = {str(item.get("code") or "") for item in ((readiness or {}).get("blockers") or []) if isinstance(item, dict)}
    if "account_not_ready" in blockers or mode == "blocked":
        return "blocked"
    if mode == "live_ready" and session_key in {"in_session", "midday", "pre_open"}:
        return "risk_on"
    if mode == "live_ready":
        return "neutral"
    if mode == "shadow_only":
        return "risk_off"
    return "cautious"


def _portfolio_index_context(screening_batch: Mapping[str, Any] | None) -> dict[str, Any]:
    metrics = {
        "hs300_change_pct": None,
        "zz500_change_pct": None,
        "cyb_change_pct": None,
        "market_score": None,
    }
    queue = [screening_batch] if isinstance(screening_batch, Mapping) else []
    seen: set[int] = set()
    while queue:
        current = queue.pop(0)
        current_id = id(current)
        if current_id in seen:
            continue
        seen.add(current_id)
        for key, value in current.items():
            if isinstance(value, Mapping):
                queue.append(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, Mapping):
                        queue.append(item)
            lower = str(key).lower()
            if metrics["hs300_change_pct"] is None and any(token in lower for token in ("hs300", "沪深300")):
                metrics["hs300_change_pct"] = _portfolio_optional_float(value)
            if metrics["zz500_change_pct"] is None and any(token in lower for token in ("zz500", "中证500")):
                metrics["zz500_change_pct"] = _portfolio_optional_float(value)
            if metrics["cyb_change_pct"] is None and any(token in lower for token in ("cyb", "创业板")):
                metrics["cyb_change_pct"] = _portfolio_optional_float(value)
            if metrics["market_score"] is None and any(token in lower for token in ("market_score", "env_score", "score")):
                maybe = _portfolio_optional_float(value)
                if maybe is not None:
                    metrics["market_score"] = maybe
    return metrics


def _portfolio_news_signals(
    *,
    watchlist_stock: Mapping[str, Any] | None,
    latest_decision: Mapping[str, Any] | None,
) -> dict[str, Any]:
    positives = [str(item).strip() for item in ((watchlist_stock or {}).get("positives") or []) if str(item).strip()]
    hard_flags = [str(item).strip() for item in ((watchlist_stock or {}).get("hard_flags") or []) if str(item).strip()]
    recommendation = (latest_decision or {}).get("recommendation") or {}
    risk_summary = str(recommendation.get("risk_summary") or "").strip()
    event_text = _portfolio_join_tokens(
        (watchlist_stock or {}).get("event_base"),
        positives,
        hard_flags,
        risk_summary,
        recommendation.get("main_conclusion"),
    )
    event_risk = "none"
    if any(token in event_text for token in ("黑天鹅", "问询", "减持", "监管", "诉讼", "爆雷")):
        event_risk = "high"
    elif hard_flags or any(token in event_text for token in ("风险", "偏空", "走弱")):
        event_risk = "medium"
    event_boost = "none"
    if positives or any(token in event_text for token in ("利好", "改善", "回购", "分红", "偏多")):
        event_boost = "medium" if positives else "low"
    return {
        "event_risk": event_risk,
        "event_boost": event_boost,
        "risk_summary": risk_summary,
        "positives": positives,
        "hard_flags": hard_flags,
    }


def _portfolio_stock_script_config(
    position: dict[str, Any],
    *,
    latest_decision: dict[str, Any] | None,
    watchlist_stock: dict[str, Any] | None,
    avg_cost: float,
) -> dict[str, Any]:
    name = str(position.get("name") or (watchlist_stock or {}).get("name") or "")
    code = str(position.get("code") or (watchlist_stock or {}).get("code") or "")
    recommendation = (latest_decision or {}).get("recommendation") or {}
    rule_snapshot = (watchlist_stock or {}).get("rule_snapshot") or {}
    if not isinstance(rule_snapshot, dict):
        rule_snapshot = {}

    action_text = _portfolio_first_text((watchlist_stock or {}).get("action"), recommendation.get("action_label"))
    tech_base = _portfolio_first_text(rule_snapshot.get("tech_base"), (watchlist_stock or {}).get("tech_base"))
    flow_base = _portfolio_first_text(rule_snapshot.get("flow_base"), (watchlist_stock or {}).get("flow_base"))
    event_base = _portfolio_first_text(rule_snapshot.get("event_base"), (watchlist_stock or {}).get("event_base"))
    signal = _portfolio_first_text(rule_snapshot.get("signal"), (watchlist_stock or {}).get("signal"))
    score = _portfolio_optional_float(rule_snapshot.get("score", (watchlist_stock or {}).get("score")))
    hard_flags = [str(item).strip() for item in ((watchlist_stock or {}).get("hard_flags") or []) if str(item).strip()]
    positives = [str(item).strip() for item in ((watchlist_stock or {}).get("positives") or []) if str(item).strip()]
    watch_points = [str(item).strip() for item in ((watchlist_stock or {}).get("watch_points") or []) if str(item).strip()]
    support = _portfolio_trade_level(watchlist_stock, "support")
    resistance = _portfolio_trade_level(watchlist_stock, "resistance")
    stop_loss = _portfolio_trade_level(watchlist_stock, "stop_loss")

    text_blob = _portfolio_join_tokens(
        code,
        name,
        action_text,
        tech_base,
        flow_base,
        event_base,
        signal,
        hard_flags,
        positives,
        watch_points,
        recommendation,
    )
    low_vol_tokens = ("海尔", "美的", "格力", "家电", "白电", "消费", "食品", "饮料", "白酒", "银行", "保险", "电力", "公用")
    high_vol_tokens = ("题材", "AI", "算力", "机器人", "半导体", "芯片", "低空", "军工", "创新药", "证券", "传媒", "游戏")
    cyclical_tokens = ("有色", "煤炭", "钢铁", "化工", "航运", "地产", "光伏", "新能源", "锂", "铜")

    profile_key = "standard"
    profile_label = "常规波动个股"
    profile_detail = "按普通持仓节奏处理；止损和止盈线随成本线动态重算。"
    rules: dict[str, float | int] = _portfolio_default_plan_rules()

    if any(token in text_blob for token in high_vol_tokens):
        profile_key = "high_vol_theme"
        profile_label = "高波动题材"
        profile_detail = "波动大、窗口短；亏损容忍略宽，但时间失败更快触发。"
        rules = {
            "warning_loss_pct": -4.0,
            "defense_reduce_loss_pct": -6.5,
            "clear_loss_pct": -10.0,
            "profit_take_pct": 10.0,
            "max_hold_days": 2,
            "min_progress_pct": 3.0,
        }
    elif any(token in text_blob for token in low_vol_tokens):
        profile_key = "low_vol_consumer_bluechip"
        profile_label = "低波动消费蓝筹"
        profile_detail = "低波动票不靠大回撤换空间；亏损线收紧，观察窗口略放长。"
        rules = {
            "warning_loss_pct": -2.2,
            "defense_reduce_loss_pct": -4.2,
            "clear_loss_pct": -7.0,
            "profit_take_pct": 6.5,
            "max_hold_days": 7,
            "min_progress_pct": 1.2,
        }
    elif any(token in text_blob for token in cyclical_tokens):
        profile_key = "mid_high_vol_cycle"
        profile_label = "中高波动周期"
        profile_detail = "周期票允许更大日内摆动，但必须更快看到价格进展。"
        rules = {
            "warning_loss_pct": -3.5,
            "defense_reduce_loss_pct": -5.5,
            "clear_loss_pct": -8.5,
            "profit_take_pct": 9.0,
            "max_hold_days": 4,
            "min_progress_pct": 2.0,
        }

    levels = _portfolio_plan_levels(avg_cost, rules)
    if support is not None:
        levels["structure_support_price"] = round_money(support)
        if support > 0 and support > levels["defense_reduce_price"]:
            levels["defense_reduce_price"] = round_money(support)
            rules["defense_reduce_loss_pct"] = round(((levels["defense_reduce_price"] / avg_cost) - 1) * 100, 2) if avg_cost else rules["defense_reduce_loss_pct"]
    if stop_loss is not None:
        stop_loss_price = round_money(stop_loss)
        levels["watchlist_stop_loss_price"] = stop_loss_price
        if stop_loss_price > 0:
            levels["clear_exit_price"] = round_money(max(stop_loss_price, levels["clear_exit_price"]))
            rules["clear_loss_pct"] = round(((levels["clear_exit_price"] / avg_cost) - 1) * 100, 2) if avg_cost else rules["clear_loss_pct"]
    if resistance is not None:
        levels["repair_price"] = round_money(resistance)
    else:
        levels["repair_price"] = round_money(max(levels.get("reclaim_price") or avg_cost, avg_cost))

    basis = [f"个股画像：{profile_label}"]
    if action_text:
        basis.append(f"当日观察动作：{action_text}")
    if signal:
        basis.append(f"技术信号：{signal}")
    if flow_base:
        basis.append(f"资金状态：{flow_base}")
    if event_base:
        basis.append(f"事件状态：{event_base}")
    if hard_flags:
        basis.append(f"硬风险：{' / '.join(hard_flags[:3])}")
    if positives:
        basis.append(f"正向证据：{' / '.join(positives[:3])}")

    return {
        "profile_key": profile_key,
        "profile_label": profile_label,
        "profile_detail": profile_detail,
        "rules": rules,
        "levels": levels,
        "basis": basis,
        "evidence": {
            "action": action_text,
            "tech_base": tech_base,
            "flow_base": flow_base,
            "event_base": event_base,
            "signal": signal,
            "score": score,
            "hard_flags": hard_flags,
            "positives": positives,
            "watch_points": watch_points,
            "support": support,
            "resistance": resistance,
            "stop_loss": stop_loss,
        },
    }


def _portfolio_plan_levels(avg_cost: float, rules: dict[str, Any]) -> dict[str, float]:
    return {
        "warning_price": round_money(avg_cost * (1 + _portfolio_float(rules.get("warning_loss_pct"), -3.0) / 100)),
        "defense_reduce_price": round_money(avg_cost * (1 + _portfolio_float(rules.get("defense_reduce_loss_pct"), -5.0) / 100)),
        "clear_exit_price": round_money(avg_cost * (1 + _portfolio_float(rules.get("clear_loss_pct"), -8.0) / 100)),
        "profit_take_price": round_money(avg_cost * (1 + _portfolio_float(rules.get("profit_take_pct"), 8.0) / 100)),
        "reclaim_price": round_money(avg_cost),
        "time_fail_price": round_money(avg_cost * (1 + _portfolio_float(rules.get("min_progress_pct"), 1.0) / 100)),
    }


def _portfolio_find_position_plan(
    position: dict[str, Any],
    position_plans: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    aliases = _portfolio_code_aliases(position.get("code"))
    matches = []
    for plan in position_plans or []:
        if not isinstance(plan, dict):
            continue
        if str(plan.get("status") or "open") != "open":
            continue
        if aliases.intersection(_portfolio_code_aliases(plan.get("code"))):
            matches.append(plan)
    if not matches:
        return None
    matches.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
    return matches[0]


def _portfolio_runtime_position_plan(
    position: dict[str, Any],
    *,
    latest_decision: dict[str, Any] | None,
    watchlist_stock: dict[str, Any] | None,
) -> dict[str, Any]:
    avg_cost = round_money(position.get("avg_cost") or 0.0)
    rules = _portfolio_default_plan_rules()
    recommendation = (latest_decision or {}).get("recommendation") or {}
    entry_reason = _portfolio_first_text(
        recommendation.get("main_conclusion"),
        recommendation.get("entry_reason"),
        (watchlist_stock or {}).get("reason"),
        (watchlist_stock or {}).get("detail"),
        "Prism 根据已有真实持仓生成默认持仓剧本。",
    )
    return {
        "plan_id": f"runtime:{position.get('code') or ''}",
        "status": "open",
        "source": "auto_runtime_default",
        "created_at": position.get("last_fill_at") or "",
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "code": position.get("code"),
        "name": position.get("name"),
        "entry_trade_date": str(position.get("last_fill_at") or "")[:10],
        "entry_price": avg_cost,
        "entry_qty": position.get("qty"),
        "current_qty": position.get("qty"),
        "avg_cost_basis": avg_cost,
        "rules": rules,
        "levels": _portfolio_plan_levels(avg_cost, rules),
        "logic": {
            "entry_reason": entry_reason,
            "risk_model": "Prism 默认持仓剧本：-5% 防守减仓，-8% 清仓退出，+8% 止盈兑现，5 个自然日未达到 +1% 进展则时间失败。",
        },
    }


def _portfolio_effective_position_plan(
    position: dict[str, Any],
    *,
    latest_decision: dict[str, Any] | None,
    watchlist_stock: dict[str, Any] | None,
    position_plans: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    plan = _portfolio_find_position_plan(position, position_plans)
    if plan:
        merged = dict(plan)
        rules = {**_portfolio_default_plan_rules(), **dict(merged.get("rules") or {})}
        avg_cost = round_money(merged.get("avg_cost_basis") or position.get("avg_cost") or 0.0)
        levels = {**_portfolio_plan_levels(avg_cost, rules), **dict(merged.get("levels") or {})}
        merged["rules"] = rules
        merged["levels"] = levels
        merged["avg_cost_basis"] = avg_cost
        return merged
    return _portfolio_runtime_position_plan(
        position,
        latest_decision=latest_decision,
        watchlist_stock=watchlist_stock,
    )


def _portfolio_days_held(entry_trade_date: Any, expected_date: str) -> int | None:
    try:
        start = datetime.strptime(str(entry_trade_date or "")[:10], "%Y-%m-%d")
        end = datetime.strptime(str(expected_date or "")[:10], "%Y-%m-%d")
    except ValueError:
        return None
    return max((end - start).days, 0)


def _portfolio_money_text(value: Any) -> str:
    number = _portfolio_optional_float(value)
    if number is None:
        return "-"
    return f"{number:.2f}"


def _portfolio_pct_text(value: Any) -> str:
    number = _portfolio_optional_float(value)
    if number is None:
        return "-"
    return f"{number:.2f}%"


def _build_holding_review(
    position: dict[str, Any],
    *,
    latest_decision: dict[str, Any] | None,
    watchlist_stock: dict[str, Any] | None,
    position_plan: dict[str, Any],
    expected_date: str,
    readiness: Mapping[str, Any] | None = None,
    screening_batch: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    latest_decision_summary = _portfolio_decision_summary(latest_decision)
    current_price = position.get("current_price")
    unrealized_pct = position.get("unrealized_pnl_pct")
    latest_decision_date = str((latest_decision_summary or {}).get("trade_date") or "")
    decision_is_today = bool(latest_decision_date and latest_decision_date == expected_date)
    avg_cost = round_money(position.get("avg_cost") or position_plan.get("avg_cost_basis") or 0.0)
    script = _portfolio_stock_script_config(
        position,
        latest_decision=latest_decision,
        watchlist_stock=watchlist_stock,
        avg_cost=avg_cost,
    )
    plan_source = str(position_plan.get("source") or "")
    stored_rules = dict(position_plan.get("rules") or {})
    stored_levels = dict(position_plan.get("levels") or {})
    rules = {**_portfolio_default_plan_rules(), **stored_rules, **dict(script.get("rules") or {})}
    levels = {**_portfolio_plan_levels(avg_cost, rules), **dict(script.get("levels") or {})}
    if plan_source and not plan_source.startswith("auto_"):
        levels = {**levels, **stored_levels}
    position_plan = {
        **position_plan,
        "rules": rules,
        "levels": levels,
        "logic": {
            **dict(position_plan.get("logic") or {}),
            "risk_model": f"Prism 个股剧本：{script['profile_label']}｜防守线 {_portfolio_float(rules.get('defense_reduce_loss_pct'), -5.0):.2f}%｜清仓线 {_portfolio_float(rules.get('clear_loss_pct'), -8.0):.2f}%｜止盈线 +{_portfolio_float(rules.get('profit_take_pct'), 8.0):.2f}%｜时间窗口 {int(_portfolio_float(rules.get('max_hold_days'), 5))} 天。",
        },
        "script_profile": {
            "key": script.get("profile_key"),
            "label": script.get("profile_label"),
            "detail": script.get("profile_detail"),
        },
    }
    price_value = _portfolio_optional_float(current_price)
    pnl_pct_value = _portfolio_optional_float(unrealized_pct)
    days_held = _portfolio_days_held(position_plan.get("entry_trade_date"), expected_date)
    qty = int(position.get("qty") or 0)
    reduce_qty = max(1, qty // 2) if qty else 0
    remain_after_reduce = max(qty - reduce_qty, 0)

    warning_loss_pct = _portfolio_float(rules.get("warning_loss_pct"), -3.0)
    defense_loss_pct = _portfolio_float(rules.get("defense_reduce_loss_pct"), -5.0)
    clear_loss_pct = _portfolio_float(rules.get("clear_loss_pct"), -8.0)
    profit_take_pct = _portfolio_float(rules.get("profit_take_pct"), 8.0)
    min_progress_pct = _portfolio_float(rules.get("min_progress_pct"), 1.0)
    max_hold_days = int(_portfolio_float(rules.get("max_hold_days"), 5))
    warning_price = round_money(levels.get("warning_price") or avg_cost * (1 + warning_loss_pct / 100))
    defense_price = round_money(levels.get("defense_reduce_price") or avg_cost * (1 + defense_loss_pct / 100))
    clear_price = round_money(levels.get("clear_exit_price") or avg_cost * (1 + clear_loss_pct / 100))
    profit_price = round_money(levels.get("profit_take_price") or avg_cost * (1 + profit_take_pct / 100))
    reclaim_price = round_money(levels.get("reclaim_price") or avg_cost)
    time_fail_price = round_money(levels.get("time_fail_price") or avg_cost * (1 + min_progress_pct / 100))
    repair_price = round_money(levels.get("repair_price") or reclaim_price)
    support_price = _portfolio_optional_float(levels.get("structure_support_price"))

    script_evidence = dict(script.get("evidence") or {})
    market_regime = _portfolio_market_regime(readiness)
    index_context = _portfolio_index_context(screening_batch)
    news_signals = _portfolio_news_signals(
        watchlist_stock=watchlist_stock,
        latest_decision=latest_decision,
    )
    decision_text = _portfolio_join_tokens(
        _portfolio_decision_text(latest_decision),
        script_evidence.get("action"),
        script_evidence.get("signal"),
        script_evidence.get("hard_flags"),
    )
    decision_says_exit = any(
        token in decision_text
        for token in ("卖出", "减仓", "清仓", "止损", "放弃", "forbid", "reduce", "skip")
    )
    trigger_facts: list[str] = []
    if price_value is not None:
        trigger_facts.append(f"现价 {_portfolio_money_text(price_value)}，成本 {_portfolio_money_text(avg_cost)}，浮盈亏 {_portfolio_pct_text(pnl_pct_value)}。")
        if support_price is not None and price_value <= support_price:
            trigger_facts.append(f"现价已低于结构支撑 {_portfolio_money_text(support_price)}。")
    if script_evidence.get("action"):
        trigger_facts.append(f"当日观察动作：{script_evidence['action']}。")
    if script_evidence.get("signal"):
        trigger_facts.append(f"技术信号：{script_evidence['signal']}。")
    if script_evidence.get("flow_base"):
        trigger_facts.append(f"资金状态：{script_evidence['flow_base']}。")
    if script_evidence.get("event_base"):
        trigger_facts.append(f"事件状态：{script_evidence['event_base']}。")
    if script_evidence.get("hard_flags"):
        trigger_facts.append(f"硬风险：{' / '.join(script_evidence['hard_flags'][:3])}。")

    def _rule_text(*items: Any) -> str:
        return " ".join(str(item).strip() for item in items if str(item or "").strip())

    target_sell_qty = 0
    target_sell_pct = 0.0

    if price_value is None:
        action = "refresh_quote"
        label = "刷新行情"
        tone = "warning"
        category = "行情缺失"
        suggested_action = "刷新行情"
        trigger_rule = "当前持仓没有可用现价，先取回行情再生成动作。"
        execution_rule = "刷新持仓行情；刷新后按个股剧本重新计算防守线、清仓线、止盈线。"
        upgrade_rule = "行情取回后立即重新分层。"
        revoke_rule = "行情取回后撤销此状态。"
        review_tag = "quote_missing"
    elif pnl_pct_value is not None and (pnl_pct_value <= clear_loss_pct or price_value <= clear_price):
        action = "clear_exit"
        label = "清仓退出"
        tone = "sell"
        category = "止损退出"
        suggested_action = "清仓"
        target_sell_qty = qty
        target_sell_pct = 100.0 if qty else 0.0
        trigger_rule = _rule_text(
            f"清仓线 {_portfolio_money_text(clear_price)} 已触发。",
            f"清仓阈值 {clear_loss_pct:.2f}%。",
        )
        execution_rule = f"卖出 {qty} 股（100%）；成交回写后关闭本票持仓剧本。"
        upgrade_rule = "已是最高退出级别。"
        revoke_rule = f"未成交前若现价重新站回防守线 {_portfolio_money_text(defense_price)}，状态降为防守减仓；已成交则不撤销。"
        review_tag = "loss_clear_exit"
    elif (
        decision_says_exit
        or (pnl_pct_value is not None and pnl_pct_value <= defense_loss_pct)
        or price_value <= defense_price
    ):
        action = "defense_reduce"
        label = "防守减仓"
        tone = "sell"
        category = "防守减仓"
        suggested_action = "减仓"
        target_sell_qty = reduce_qty
        target_sell_pct = round((reduce_qty / qty) * 100, 2) if qty else 0.0
        threshold_fact = ""
        if pnl_pct_value is not None and (pnl_pct_value <= defense_loss_pct or price_value <= defense_price):
            threshold_fact = f"防守线 {_portfolio_money_text(defense_price)} / {defense_loss_pct:.2f}% 已触发。"
        signal_fact = "当日观察链出现减仓/止损信号。" if decision_says_exit else ""
        trigger_rule = _rule_text(threshold_fact, signal_fact)
        execution_rule = f"卖出 {reduce_qty} 股（{target_sell_pct:.0f}%）；剩余 {remain_after_reduce} 股只保留到清仓线 {_portfolio_money_text(clear_price)}；今日不补仓。"
        upgrade_rule = f"现价 <= {_portfolio_money_text(clear_price)} 或浮亏 <= {clear_loss_pct:.2f}% 时清仓 {remain_after_reduce} 股。"
        revoke_rule = f"收盘价 >= 修复线 {_portfolio_money_text(repair_price)} 且当日观察动作不含减仓/看空时撤销；否则继续防守。"
        review_tag = "loss_defense_reduce" if threshold_fact else "logic_exit_signal"
    elif pnl_pct_value is not None and (pnl_pct_value >= profit_take_pct or price_value >= profit_price):
        action = "profit_take"
        label = "止盈兑现"
        tone = "positive"
        category = "止盈兑现"
        suggested_action = "止盈"
        target_sell_qty = reduce_qty
        target_sell_pct = round((reduce_qty / qty) * 100, 2) if qty else 0.0
        trigger_rule = f"止盈线 {_portfolio_money_text(profit_price)} / +{profit_take_pct:.2f}% 已触发。"
        execution_rule = f"卖出 {reduce_qty} 股（{target_sell_pct:.0f}%）锁定利润；剩余 {remain_after_reduce} 股防守线抬到成本线 {_portfolio_money_text(reclaim_price)}。"
        upgrade_rule = f"剩余仓位回落到成本线 {_portfolio_money_text(reclaim_price)} 时退出剩余 {remain_after_reduce} 股。"
        revoke_rule = f"未成交前若价格跌回止盈线 {_portfolio_money_text(profit_price)} 以下，状态降回继续持有。"
        review_tag = "profit_take"
    elif days_held is not None and days_held >= max_hold_days and pnl_pct_value is not None and pnl_pct_value < min_progress_pct:
        action = "time_exit"
        label = "时间失败"
        tone = "warning"
        category = "时间失败"
        suggested_action = "减仓"
        target_sell_qty = reduce_qty
        target_sell_pct = round((reduce_qty / qty) * 100, 2) if qty else 0.0
        trigger_rule = f"持有 {days_held} 个自然日，收益 {_portfolio_pct_text(pnl_pct_value)} 未达到 {min_progress_pct:.2f}% 的进展线。"
        execution_rule = f"卖出 {reduce_qty} 股（{target_sell_pct:.0f}%）；剩余 {remain_after_reduce} 股只在时间达标线 {_portfolio_money_text(time_fail_price)} 上方保留。"
        upgrade_rule = f"现价 <= {_portfolio_money_text(defense_price)} 时转为防守减仓。"
        revoke_rule = f"价格 >= 时间达标线 {_portfolio_money_text(time_fail_price)} 时撤销时间失败。"
        review_tag = "time_failure"
    elif pnl_pct_value is not None and (pnl_pct_value <= warning_loss_pct or price_value <= warning_price):
        action = "loss_warning"
        label = "亏损预警"
        tone = "warning"
        category = "亏损预警"
        suggested_action = "不加仓"
        trigger_rule = f"预警线 {_portfolio_money_text(warning_price)} / {warning_loss_pct:.2f}% 已触发。"
        execution_rule = "不买入、不加仓；持仓数量保持不变。"
        upgrade_rule = f"现价 <= {_portfolio_money_text(defense_price)} 或浮亏 <= {defense_loss_pct:.2f}% 时执行防守减仓。"
        revoke_rule = f"价格 >= 修复线 {_portfolio_money_text(repair_price)} 时撤销预警。"
        review_tag = "loss_warning"
    else:
        action = "hold"
        label = "继续持有"
        tone = "positive"
        category = "继续持有"
        suggested_action = "持有"
        trigger_rule = f"现价位于防守线 {_portfolio_money_text(defense_price)} 与止盈线 {_portfolio_money_text(profit_price)} 之间，未触发动作。"
        execution_rule = "持仓保持不变；不新增仓位。"
        upgrade_rule = f"现价 <= {_portfolio_money_text(defense_price)} 转防守减仓；现价 >= {_portfolio_money_text(profit_price)} 转止盈兑现。"
        revoke_rule = "无需撤销。"
        review_tag = "hold"

    instruction = f"{category}｜建议动作：{suggested_action}"
    has_current_watchlist = bool(watchlist_stock)
    evidence_pack = {
        "stock": {
            "code": position.get("code"),
            "name": position.get("name"),
            "profile": script.get("profile_label"),
        },
        "position": {
            "qty": qty,
            "position_pct": None,
            "avg_cost": avg_cost,
            "current_price": price_value,
            "pnl_pct": pnl_pct_value,
            "pnl_amount": _portfolio_optional_float(position.get("unrealized_pnl")),
            "days_held": days_held,
            "entry_date": position_plan.get("entry_trade_date"),
            "last_action": position_plan.get("source"),
            "last_action_price": _portfolio_optional_float(position_plan.get("entry_price")),
        },
        "script": {
            "base_action": action,
            "base_action_label": label,
            "defense_line": defense_price,
            "clear_line": clear_price,
            "repair_line": repair_price,
            "profit_line": profit_price,
            "warning_line": warning_price,
            "time_fail_line": time_fail_price,
            "suggested_sell_qty": target_sell_qty,
            "suggested_sell_pct": target_sell_pct,
            "rule_floor_action": action,
        },
        "price_action": {
            "change_pct_today": _portfolio_optional_float(position.get("quote_change_pct")),
            "range_position_20d": "near_low" if support_price is not None and price_value is not None and price_value <= support_price else "mid",
            "ma5_relation": "below" if price_value is not None and price_value < reclaim_price else "above_or_equal",
            "ma10_relation": "below" if price_value is not None and price_value < repair_price else "above_or_equal",
            "ma20_relation": "below" if price_value is not None and price_value < avg_cost else "above_or_equal",
            "drawdown_from_repair_pct": round(((price_value / repair_price) - 1) * 100, 2) if price_value is not None and repair_price else None,
            "break_levels": [item for item in ("below_support" if support_price is not None and price_value is not None and price_value <= support_price else "", "below_defense_line" if price_value is not None and price_value <= defense_price else "", "below_clear_line" if price_value is not None and price_value <= clear_price else "") if item],
            "volatility_profile": script.get("profile_key"),
        },
        "flow": {
            "flow_direction": script_evidence.get("flow_base"),
            "flow_persistence_days": 5 if script_evidence.get("flow_base") else None,
            "main_signal": script_evidence.get("signal"),
            "score": script_evidence.get("score"),
        },
        "market_context": {
            "market_regime": market_regime,
            "attack_gate": "closed" if market_regime in {"risk_off", "blocked", "cautious"} else "open",
            "hs300_change_pct": index_context.get("hs300_change_pct"),
            "zz500_change_pct": index_context.get("zz500_change_pct"),
            "cyb_change_pct": index_context.get("cyb_change_pct"),
            "market_score": index_context.get("market_score"),
            "session": ((readiness or {}).get("session") or {}).get("label"),
        },
        "events": {
            "event_risk": news_signals.get("event_risk"),
            "event_boost": news_signals.get("event_boost"),
            "risk_summary": news_signals.get("risk_summary"),
            "positive_flags": news_signals.get("positives") or [],
            "risk_flags": news_signals.get("hard_flags") or [],
        },
        "prism_history": [
            {
                "date": (latest_decision_summary or {}).get("trade_date"),
                "action": (latest_decision_summary or {}).get("action"),
                "action_label": (latest_decision_summary or {}).get("action_label"),
                "conclusion": (latest_decision_summary or {}).get("main_conclusion"),
                "outcome_label": ((latest_decision_summary or {}).get("latest_outcome") or {}).get("label"),
                "outcome_return_pct": ((latest_decision_summary or {}).get("latest_outcome") or {}).get("return_pct"),
            }
        ] if latest_decision_summary else [],
        "evidence": {
            "price": trigger_facts[:2],
            "flow": [f"资金状态：{script_evidence['flow_base']}"] if script_evidence.get("flow_base") else [],
            "technical": [f"技术信号：{script_evidence['signal']}"] if script_evidence.get("signal") else [],
            "event": [f"事件状态：{script_evidence['event_base']}"] if script_evidence.get("event_base") else [],
            "risk_flags": news_signals.get("hard_flags") or [],
            "positive_flags": news_signals.get("positives") or [],
        },
        "constraints": {
            "rule_floor_action": action,
            "can_relax_below_rule": False,
            "can_suggest_tighten": True,
            "manual_execution_only": True,
            "max_sell_qty": qty,
            "recommended_sell_qty": target_sell_qty,
        },
    }

    return {
        "code": position.get("code"),
        "name": position.get("name"),
        "qty": position.get("qty"),
        "avg_cost": position.get("avg_cost"),
        "cost_basis": position.get("cost_basis"),
        "current_price": current_price,
        "market_value": position.get("market_value"),
        "unrealized_pnl": position.get("unrealized_pnl"),
        "unrealized_pnl_pct": unrealized_pct,
        "quote_trade_date": position.get("quote_trade_date"),
        "quote_timestamp": position.get("quote_timestamp"),
        "last_fill_at": position.get("last_fill_at"),
        "today_action": action,
        "action_label": label,
        "action_tone": tone,
        "action_instruction": instruction,
        "must_review": action != "hold",
        "missing_plan": False,
        "missing_analysis": not (decision_is_today or has_current_watchlist),
        "decision_is_today": decision_is_today,
        "stop_condition": f"清仓线 {_portfolio_money_text(clear_price)} / {clear_loss_pct:.2f}%",
        "reduce_condition": f"防守减仓线 {_portfolio_money_text(defense_price)} / {defense_loss_pct:.2f}%",
        "continue_condition": f"修复线 {_portfolio_money_text(repair_price)}；止盈线 {_portfolio_money_text(profit_price)}",
        "position_plan": position_plan,
        "holding_evidence_pack": evidence_pack,
        "holding_decision": {
            "category": category,
            "suggested_action": suggested_action,
            "trigger_rule": trigger_rule,
            "execution_rule": execution_rule,
            "upgrade_rule": upgrade_rule,
            "revoke_rule": revoke_rule,
            "review_tag": review_tag,
            "target_sell_qty": target_sell_qty,
            "target_sell_pct": target_sell_pct,
            "days_held": days_held,
            "price": price_value,
            "avg_cost": avg_cost,
            "pnl_pct": pnl_pct_value,
            "trigger_facts": trigger_facts,
            "script": {
                "profile_key": script.get("profile_key"),
                "profile_label": script.get("profile_label"),
                "profile_detail": script.get("profile_detail"),
                "basis": script.get("basis") or [],
                "rule_summary": f"防守 {defense_loss_pct:.2f}%｜清仓 {clear_loss_pct:.2f}%｜止盈 +{profit_take_pct:.2f}%｜时间 {max_hold_days} 天",
            },
            "evidence": script_evidence,
            "levels": {
                "warning_price": warning_price,
                "defense_reduce_price": defense_price,
                "clear_exit_price": clear_price,
                "profit_take_price": profit_price,
                "reclaim_price": reclaim_price,
                "time_fail_price": time_fail_price,
                "repair_price": repair_price,
                "structure_support_price": support_price,
            },
            "rules": rules,
        },
        "latest_decision": latest_decision_summary,
        "latest_execution": (latest_decision_summary or {}).get("latest_execution"),
        "latest_outcome": (latest_decision_summary or {}).get("latest_outcome"),
        "review_reason": category,
    }


def _build_holding_reviews(
    positions: list[dict[str, Any]],
    *,
    watchlist: dict[str, Any] | None,
    position_plans: list[dict[str, Any]] | None,
    expected_date: str,
    readiness: Mapping[str, Any] | None = None,
    screening_batch: Mapping[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    latest_decisions, errors = _portfolio_latest_decisions_by_code()
    watchlist_index = _portfolio_watchlist_index(watchlist)
    reviews: list[dict[str, Any]] = []
    for position in positions:
        aliases = _portfolio_code_aliases(position.get("code"))
        latest_decision = next((latest_decisions.get(alias) for alias in aliases if alias in latest_decisions), None)
        watchlist_stock = next((watchlist_index.get(alias) for alias in aliases if alias in watchlist_index), None)
        position_plan = _portfolio_effective_position_plan(
            position,
            latest_decision=latest_decision,
            watchlist_stock=watchlist_stock,
            position_plans=position_plans,
        )
        reviews.append(
            _build_holding_review(
                position,
                latest_decision=latest_decision,
                watchlist_stock=watchlist_stock,
                position_plan=position_plan,
                expected_date=expected_date,
                readiness=readiness,
                screening_batch=screening_batch,
            )
        )

    action_order = {
        "clear_exit": 0,
        "defense_reduce": 1,
        "profit_take": 2,
        "time_exit": 3,
        "loss_warning": 4,
        "refresh_quote": 5,
        "hold": 5,
    }
    reviews.sort(
        key=lambda item: (
            action_order.get(str(item.get("today_action") or ""), 99),
            float(item.get("unrealized_pnl_pct") or 0.0),
            str(item.get("code") or ""),
        )
    )
    counts: dict[str, int] = {}
    for item in reviews:
        action = str(item.get("today_action") or "hold")
        counts[action] = counts.get(action, 0) + 1
    summary = {
        "total": len(reviews),
        "must_review": sum(1 for item in reviews if item.get("must_review")),
        "clear_exit": counts.get("clear_exit", 0),
        "defense_reduce": counts.get("defense_reduce", 0),
        "profit_take": counts.get("profit_take", 0),
        "time_exit": counts.get("time_exit", 0),
        "loss_warning": counts.get("loss_warning", 0),
        "refresh_quote": counts.get("refresh_quote", 0),
        "review_sell": counts.get("clear_exit", 0) + counts.get("defense_reduce", 0) + counts.get("profit_take", 0) + counts.get("time_exit", 0),
        "reduce_watch": counts.get("loss_warning", 0),
        "evidence_blocked": counts.get("refresh_quote", 0),
        "missing_plan": 0,
        "missing_analysis": counts.get("missing_analysis", 0),
        "hold": counts.get("hold", 0),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "expected_trade_date": expected_date,
        "errors": errors,
    }
    if summary["clear_exit"]:
        summary["title"] = f"{summary['clear_exit']} 只持仓触发清仓退出"
        summary["tone"] = "sell"
    elif summary["defense_reduce"]:
        summary["title"] = f"{summary['defense_reduce']} 只持仓触发防守减仓"
        summary["tone"] = "sell"
    elif summary["profit_take"]:
        summary["title"] = f"{summary['profit_take']} 只持仓触发止盈兑现"
        summary["tone"] = "positive"
    elif summary["time_exit"]:
        summary["title"] = f"{summary['time_exit']} 只持仓触发时间失败"
        summary["tone"] = "warning"
    elif summary["must_review"]:
        summary["title"] = f"{summary['must_review']} 只持仓需要动作"
        summary["tone"] = "warning"
    elif reviews:
        summary["title"] = "持仓按剧本继续"
        summary["tone"] = "positive"
    else:
        summary["title"] = "暂无真实持仓"
        summary["tone"] = "info"
    return reviews, summary


def _holding_ai_is_precise(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    return bool(
        re.search(r"\d", value)
        or any(
            token in value
            for token in (
                "防守线",
                "清仓线",
                "止盈线",
                "修复线",
                "现价",
                "浮亏",
                "卖出",
                "减仓",
                "清仓",
                "持有",
                "刷新行情",
                "收盘",
                "站回",
                "跌破",
            )
        )
    )


def _holding_ai_normalize_fact(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "当前未进入观察池链路" in text:
        return ""
    replacements = (
        ("risk_on", "大盘风险偏好回暖"),
        ("risk_off", "大盘偏弱"),
        ("blocked", "大盘未放行"),
        ("base_action为refresh_quote", "当前缺现价，先刷新行情"),
        ("无价格数据", "当前缺现价"),
        ("attack_gate", "进攻阀门"),
        ("closed", "关闭"),
        ("open", "打开"),
    )
    for source, target in replacements:
        text = text.replace(source, target)
    text = text.replace("市场状态大盘风险偏好回暖", "大盘风险偏好回暖")
    text = text.replace("市场环境大盘风险偏好回暖", "大盘风险偏好回暖")
    text = text.replace("事件状态：偏多", "事件面偏多")
    text = text.replace("事件状态偏多", "事件面偏多")
    text = text.replace("大盘 大盘", "大盘")
    text = re.sub(r"\s+", " ", text).strip("；;，,。 ")
    if text.startswith("市场 "):
        text = text.replace("市场 ", "大盘 ", 1)
    if text in {"无事件风险", "现价未触发任何动作线"}:
        return ""
    return text


def _holding_ai_fact_list(items: Any, *, limit: int, action: str = "") -> list[str]:
    facts: list[str] = []
    for item in items or []:
        text = _holding_ai_normalize_fact(item)
        if not text or text in facts:
            continue
        if action == "refresh_quote" and any(token in text for token in ("MA5/10/20", "未触发任何动作线")):
            continue
        facts.append(text)
        if len(facts) >= limit:
            break
    return facts


def _holding_ai_evidence_sides(review: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    decision = dict((review.get("holding_decision") or {}))
    evidence = dict((decision.get("evidence") or {}))
    action = str(review.get("today_action") or "")
    trigger_facts = _holding_ai_fact_list(decision.get("trigger_facts") or [], limit=5, action=action)
    signal = _holding_ai_normalize_fact(evidence.get("signal"))
    flow = _holding_ai_normalize_fact(f"资金{evidence.get('flow_base')}" if evidence.get("flow_base") else "")
    hard_flags = _holding_ai_fact_list(evidence.get("hard_flags") or [], limit=2, action=action)
    positives = _holding_ai_fact_list(evidence.get("positives") or [], limit=2, action=action)
    event_base = str(evidence.get("event_base") or "").strip()

    bearish: list[str] = []
    if trigger_facts:
        bearish.extend(trigger_facts)
    if signal:
        bearish.append(f"技术{signal}" if not signal.startswith("技术") else signal)
    if flow:
        bearish.append(flow)
    if hard_flags:
        bearish.extend(hard_flags)

    buffers: list[str] = []
    if event_base == "偏多":
        buffers.append("事件面偏多")
    buffers.extend(positives)

    if action in {"clear_exit", "defense_reduce", "time_exit", "loss_warning"}:
        return _holding_ai_fact_list(bearish, limit=4, action=action), _holding_ai_fact_list(buffers, limit=3, action=action)
    if action == "profit_take":
        return _holding_ai_fact_list(trigger_facts or ["止盈线已触发"], limit=3, action=action), _holding_ai_fact_list(buffers, limit=2, action=action)
    if action == "refresh_quote":
        unconfirmed = ["当前缺现价，先刷新行情"]
        if signal or flow or hard_flags:
            unconfirmed.extend([item for item in [signal, flow, *hard_flags] if item])
        return _holding_ai_fact_list(unconfirmed, limit=4, action=action), _holding_ai_fact_list(buffers, limit=3, action=action)
    return _holding_ai_fact_list(trigger_facts or ["仍在剧本区间内"], limit=3, action=action), _holding_ai_fact_list(bearish, limit=3, action=action)


def _holding_ai_merge_facts(primary: list[str], secondary: list[str], *, limit: int, action: str) -> list[str]:
    merged: list[str] = []
    seen_keys: set[str] = set()
    for item in [*primary, *secondary]:
        text = _holding_ai_normalize_fact(item)
        if not text:
            continue
        if text == "看空（评分-40）":
            text = "技术看空（评分-40）"
        if action == "refresh_quote" and text in {
            "大盘风险偏好回暖",
            "MA5/10/20均线之上",
            "市场评分4.0",
            "当前价格数据缺失，无法触发任何动作",
        }:
            continue
        normalized_key = re.sub(r"[：:，,。；;\\s]+", "", text)
        normalized_key = normalized_key.replace("事件状态偏多", "事件面偏多")
        normalized_key = normalized_key.replace("事件偏多", "事件面偏多")
        if normalized_key in seen_keys:
            continue
        if any(text == existing or text in existing or existing in text for existing in merged):
            continue
        merged.append(text)
        seen_keys.add(normalized_key)
        if len(merged) >= limit:
            break
    return merged


def _holding_ai_default_copy(review: Mapping[str, Any]) -> dict[str, str]:
    decision = dict((review.get("holding_decision") or {}))
    evidence = dict((decision.get("evidence") or {}))
    levels = dict((decision.get("levels") or {}))
    action = str(review.get("today_action") or "")
    qty = int(_portfolio_float(review.get("qty"), 0))
    sell_qty = int(_portfolio_float(decision.get("target_sell_qty"), 0))
    remain_qty = max(qty - sell_qty, 0)
    defense_line = _portfolio_money_text(levels.get("defense_reduce_price"))
    clear_line = _portfolio_money_text(levels.get("clear_exit_price"))
    repair_line = _portfolio_money_text(levels.get("repair_price") or levels.get("reclaim_price"))
    profit_line = _portfolio_money_text(levels.get("profit_take_price"))
    time_fail_line = _portfolio_money_text(levels.get("time_fail_price"))
    signal = _holding_ai_normalize_fact(evidence.get("signal"))
    flow = _holding_ai_normalize_fact(f"资金{evidence.get('flow_base')}" if evidence.get("flow_base") else "")
    hard_flags = _holding_ai_fact_list(evidence.get("hard_flags") or [], limit=2, action=action)
    event_base = str(evidence.get("event_base") or "").strip()

    evidence_bits: list[str] = []
    if signal:
        evidence_bits.append(f"技术{signal}" if not signal.startswith("技术") else signal)
    if flow:
        evidence_bits.append(flow)
    if hard_flags:
        evidence_bits.append("风险项 " + " / ".join(hard_flags))
    if event_base == "偏多":
        evidence_bits.append("事件面有对冲")

    def _join(bits: list[str], fallback: str) -> str:
        compact = [item for item in bits if item]
        return "；".join(compact[:3]) if compact else fallback

    if action == "refresh_quote":
        return {
            "scene_label": "待行情确认",
            "action_rewrite": "现在先刷新行情；拿到现价后再决定是否减仓或退出。",
            "next_watch": f"先刷新行情。现价低于 {defense_line} 转防守减仓；现价低于 {clear_line} 转清仓退出。",
            "risk_summary": _join(
                evidence_bits,
                "当前缺现价；拿到现价前不放松剧本。",
            ),
            "adjustment_reason": "缺现价时先补行情，规则不放松。",
            "counter_evidence_label": "待确认点",
        }
    if action == "clear_exit":
        return {
            "scene_label": "清仓线触发",
            "action_rewrite": f"现在按清仓处理，卖出 {sell_qty} 股；未成交前不做加仓。",
            "next_watch": f"未成交前站回 {defense_line}，降为防守减仓；成交完成后，本票退出跟踪。",
            "risk_summary": _join(
                [f"价格已击穿清仓线 {clear_line}"] + evidence_bits,
                f"价格已击穿清仓线 {clear_line}。",
            ),
            "adjustment_reason": "清仓线已触发，先退出，再谈修复。",
            "counter_evidence_label": "缓冲证据",
        }
    if action == "defense_reduce":
        return {
            "scene_label": "防守线触发",
            "action_rewrite": f"现在先减仓 {sell_qty} 股；剩余 {remain_qty} 股只保留到清仓线 {clear_line}。",
            "next_watch": f"跌破 {clear_line} 清掉余仓；收回 {repair_line} 且当日信号转强，撤销防守。",
            "risk_summary": _join(
                [f"价格已压到防守线 {defense_line} 下方"] + evidence_bits,
                f"价格已压到防守线 {defense_line} 下方。",
            ),
            "adjustment_reason": "防守线已触发，先减仓，再看能否修复。",
            "counter_evidence_label": "缓冲证据",
        }
    if action == "profit_take":
        return {
            "scene_label": "止盈线触发",
            "action_rewrite": f"现在先止盈 {sell_qty} 股；剩余 {remain_qty} 股防守线抬到成本线 {repair_line}。",
            "next_watch": f"若余仓回落到成本线 {repair_line}，退出剩余仓位；若继续上行，按止盈后余仓跟踪。",
            "risk_summary": _join(
                [f"利润已到止盈线 {profit_line}"] + evidence_bits,
                f"利润已到止盈线 {profit_line}。",
            ),
            "adjustment_reason": "利润先兑现，避免回吐。",
            "counter_evidence_label": "回吐风险",
        }
    if action == "time_exit":
        return {
            "scene_label": "时间窗口失效",
            "action_rewrite": f"现在先减仓 {sell_qty} 股；剩余 {remain_qty} 股只在时间达标线 {time_fail_line} 上方保留。",
            "next_watch": f"若仍站不上时间达标线 {time_fail_line}，继续退出；若再跌破防守线 {defense_line}，转防守减仓。",
            "risk_summary": _join(
                ["持仓时间已超过剧本窗口"] + evidence_bits,
                "持仓时间已超过剧本窗口。",
            ),
            "adjustment_reason": "时间成本已经高于继续死扛的收益。",
            "counter_evidence_label": "缓冲证据",
        }
    if action == "loss_warning":
        return {
            "scene_label": "防守预警",
            "action_rewrite": "现在不卖也不加仓；仓位先保持不动。",
            "next_watch": f"若跌破防守线 {defense_line}，转防守减仓；若收回修复线 {repair_line}，撤销预警。",
            "risk_summary": _join(
                [f"价格已进入预警区，离防守线 {defense_line} 不远"] + evidence_bits,
                f"价格已进入预警区，离防守线 {defense_line} 不远。",
            ),
            "adjustment_reason": "还没到卖点，但已经不能加仓。",
            "counter_evidence_label": "缓冲证据",
        }
    return {
            "scene_label": "剧本内持有",
            "action_rewrite": "现在不卖不加，按原仓位继续持有。",
        "next_watch": f"跌破 {defense_line} 转防守减仓；上破 {profit_line} 转止盈兑现。",
        "risk_summary": _join(
            [f"价格仍在剧本区间内，真正的风险是跌回防守线 {defense_line} 下方"] + evidence_bits,
            f"价格仍在剧本区间内，真正的风险是跌回防守线 {defense_line} 下方。",
        ),
        "adjustment_reason": "还没触发防守线或止盈线，剧本暂不改。",
        "counter_evidence_label": "风险证据",
    }


def _holding_ai_cache_key(review: Mapping[str, Any], expected_date: str) -> str:
    code = str(review.get("code") or "")
    timestamp = str(review.get("quote_timestamp") or "")
    action = str(review.get("today_action") or "")
    script_profile = str((((review.get("holding_decision") or {}).get("script") or {}).get("profile_key")) or "")
    return f"{_HOLDING_AI_REVIEW_VERSION()}:{expected_date}:{code}:{timestamp}:{action}:{script_profile}"


def _holding_ai_prompt_payload(review: Mapping[str, Any]) -> dict[str, Any]:
    pack = dict((review.get("holding_evidence_pack") or {}))
    if pack:
        return pack
    return {
        "stock": {
            "code": review.get("code"),
            "name": review.get("name"),
        },
        "position": {
            "qty": review.get("qty"),
            "avg_cost": review.get("avg_cost"),
            "current_price": review.get("current_price"),
            "pnl_pct": review.get("unrealized_pnl_pct"),
        },
        "script": {
            "base_action": review.get("today_action"),
        },
        "constraints": {
            "manual_execution_only": True,
            "can_relax_below_rule": False,
        },
    }


def _holding_ai_review_prompt(review: Mapping[str, Any]) -> tuple[str, str]:
    system_prompt = (
        "你是 Prism 的持仓执行副手。"
        "你的任务不是重新决定买卖权限，而是基于给定 evidence pack 复核当前持仓剧本、"
        "识别场景、列出支持与反向证据，并决定剧本应保持/收紧/放宽。"
        "必须遵守 constraints。若 can_relax_below_rule=false，则不得建议低于 rule_floor_action 的更宽松动作。"
        "输出必须像交易桌指令，不要写成研究摘要。"
        "避免含糊词：接近、关注、留意、考虑、可能、偏强、偏弱、等待观察。"
        "如果有价格线、仓位或阈值，必须直接写出来。"
        "只返回一个 JSON object，不要输出额外解释。"
    )
    example = {
        "scene": "price_break_with_weak_flow",
        "scene_label": "价格破位 + 资金偏弱",
        "confidence": 0.82,
        "evidence_strength": "high",
        "verdict": "keep",
        "verdict_label": "维持原剧本",
        "action_rewrite": "海尔智家已触发防守减仓，执行 150 股减仓；剩余仓位只保留到 20.30。",
        "supporting_evidence": ["现价低于防守线", "观察链减仓观望"],
        "opposing_evidence": ["事件状态偏多"],
        "script_adjustment": {
            "adjustment": "keep",
            "adjustment_label": "保持",
            "defense_line": "keep",
            "clear_line": "keep",
            "time_window": "keep",
            "reason": "价格和资金弱势已经足够确认防守动作。"
        },
        "next_watch": "收盘不能回到修复线之上，则继续防守。",
        "risk_summary": "当前主要风险来自价格破位和连续弱势。",
        "evidence_used": ["现价 20.44 低于防守线 20.84"],
        "human_note": "手工执行，系统不会自动交易。"
    }
    user_prompt = (
        "请基于以下 holding evidence pack 生成结构化持仓 AI review。"
        "字段至少包括：scene, scene_label, confidence, evidence_strength, verdict, verdict_label, "
        "action_rewrite, supporting_evidence, opposing_evidence, script_adjustment, next_watch, risk_summary, evidence_used, human_note。"
        "script_adjustment.adjustment 只能是 keep/tighten/loosen，但若 constraints.can_relax_below_rule=false，"
        "当 base_action 是 clear_exit/defense_reduce/time_exit/profit_take 时，不得输出 loosen。"
        "confidence 为 0-1 数字，evidence_strength 只能 low/medium/high。"
        "action_rewrite 必须回答‘现在怎么做’，一句话内写清动作和数量。"
        "next_watch 必须回答‘下一条线看什么’，优先写防守线、清仓线、修复线、止盈线。"
        "supporting_evidence / opposing_evidence 每条只写一个事实，不要写空泛判断。"
        "scene_label 用 4-10 个汉字，优先使用：待行情确认 / 防守线触发 / 清仓线触发 / 止盈线触发 / 时间窗口失效 / 剧本内持有 / 防守预警。"
        "输出示例：\n"
        f"{json.dumps(example, ensure_ascii=False, sort_keys=True)}\n"
        "输入 JSON：\n"
        f"{json.dumps(_holding_ai_prompt_payload(review), ensure_ascii=False, sort_keys=True)}"
    )
    return system_prompt, user_prompt


def _sanitize_holding_ai_review(
    *,
    review: Mapping[str, Any],
    raw: Mapping[str, Any],
    fallback_reason: str = "",
) -> dict[str, Any]:
    decision = dict((review.get("holding_decision") or {}))
    evidence_pack = dict((review.get("holding_evidence_pack") or {}))
    base_action = str(review.get("today_action") or "")
    defaults = _holding_ai_default_copy(review)
    raw_verdict = str(raw.get("verdict") or "keep").strip().lower()
    verdict = raw_verdict if raw_verdict in {"keep", "tighten", "loosen"} else "keep"
    can_relax = bool(((evidence_pack.get("constraints") or {}).get("can_relax_below_rule")))
    if not can_relax and verdict == "loosen":
        verdict = "keep"
    confidence = _portfolio_optional_float(raw.get("confidence"))
    if confidence is None:
        confidence = 0.35 if fallback_reason else 0.68
    confidence = max(0.0, min(confidence, 1.0))
    strength = str(raw.get("evidence_strength") or "").strip().lower()
    if strength not in {"low", "medium", "high"}:
        strength = "medium" if confidence >= 0.55 else "low"
    default_supporting, default_opposing = _holding_ai_evidence_sides(review)
    raw_supporting = _holding_ai_fact_list(raw.get("supporting_evidence") or [], limit=6, action=base_action)
    raw_opposing = _holding_ai_fact_list(raw.get("opposing_evidence") or [], limit=4, action=base_action)
    supporting = _holding_ai_merge_facts(default_supporting, raw_supporting, limit=4, action=base_action)
    opposing = _holding_ai_merge_facts(default_opposing, raw_opposing, limit=3, action=base_action)
    evidence_used = _holding_ai_merge_facts(
        _holding_ai_fact_list(raw.get("evidence_used") or [], limit=8, action=base_action),
        supporting,
        limit=8,
        action=base_action,
    )
    if not supporting:
        supporting = _holding_ai_fact_list(decision.get("trigger_facts") or [], limit=4, action=base_action)
    adjustment = dict(raw.get("script_adjustment") or {})
    adjustment_mode = str(adjustment.get("adjustment") or verdict).strip().lower()
    if adjustment_mode not in {"keep", "tighten", "loosen"}:
        adjustment_mode = verdict
    if not can_relax and adjustment_mode == "loosen":
        adjustment_mode = "keep"
    raw_scene_label = _holding_ai_normalize_fact(raw.get("scene_label"))
    scene_label = raw_scene_label if raw_scene_label and raw_scene_label not in {"规则触发场景", "规则触发", "多空信号混杂", "无触发信号", "无需操作"} and base_action != "refresh_quote" else defaults["scene_label"]
    raw_risk_summary = _holding_ai_normalize_fact(raw.get("risk_summary"))
    risk_summary = raw_risk_summary if _holding_ai_is_precise(raw_risk_summary) else defaults["risk_summary"]
    raw_reason = _holding_ai_normalize_fact(adjustment.get("reason"))
    adjustment_reason = raw_reason if _holding_ai_is_precise(raw_reason) else defaults["adjustment_reason"]
    return {
        "scene": str(raw.get("scene") or "rule_trigger").strip() or "rule_trigger",
        "scene_label": scene_label,
        "confidence": round(confidence, 2),
        "evidence_strength": strength,
        "verdict": verdict,
        "verdict_label": str(raw.get("verdict_label") or {"keep": "维持原剧本", "tighten": "收紧剧本", "loosen": "放宽剧本"}[verdict]).strip(),
        "action_rewrite": defaults["action_rewrite"],
        "supporting_evidence": supporting,
        "opposing_evidence": opposing,
        "script_adjustment": {
            "adjustment": adjustment_mode,
            "adjustment_label": str(adjustment.get("adjustment_label") or {"keep": "保持", "tighten": "收紧", "loosen": "放宽"}[adjustment_mode]).strip(),
            "defense_line": str(adjustment.get("defense_line") or "keep").strip(),
            "clear_line": str(adjustment.get("clear_line") or "keep").strip(),
            "time_window": str(adjustment.get("time_window") or "keep").strip(),
            "reason": adjustment_reason,
        },
        "next_watch": defaults["next_watch"],
        "risk_summary": risk_summary,
        "evidence_used": evidence_used or supporting,
        "counter_evidence_label": defaults["counter_evidence_label"],
        "human_note": str(raw.get("human_note") or "手工执行，系统不会自动交易。").strip(),
        "provider": str((raw.get("_provider_meta") or {}).get("provider") or ("heuristic" if fallback_reason else _provider_config().provider)),
        "model": str((raw.get("_provider_meta") or {}).get("model") or ""),
        "fallback_reason": fallback_reason,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "base_action": base_action,
    }


def _heuristic_holding_ai_review(review: Mapping[str, Any]) -> dict[str, Any]:
    decision = dict((review.get("holding_decision") or {}))
    evidence = dict((decision.get("evidence") or {}))
    defaults = _holding_ai_default_copy(review)
    scene = "rule_trigger"
    scene_label = defaults["scene_label"]
    if str(review.get("today_action") or "") == "defense_reduce":
        scene = "price_break_with_weak_flow"
        scene_label = "价格破位 + 资金偏弱"
    elif str(review.get("today_action") or "") == "clear_exit":
        scene = "hard_stop_triggered"
        scene_label = "硬止损触发"
    elif str(review.get("today_action") or "") == "profit_take":
        scene = "profit_target_reached"
        scene_label = "止盈目标触发"
    elif str(review.get("today_action") or "") == "refresh_quote":
        scene = "quote_missing"
        scene_label = "行情缺失"
    supporting, opposing = _holding_ai_evidence_sides(review)
    return {
        "scene": scene,
        "scene_label": scene_label,
        "confidence": 0.58,
        "evidence_strength": "medium",
        "verdict": "keep",
        "verdict_label": "维持原剧本",
        "action_rewrite": defaults["action_rewrite"],
        "supporting_evidence": supporting,
        "opposing_evidence": opposing,
        "script_adjustment": {
            "adjustment": "keep",
            "adjustment_label": "保持",
            "defense_line": "keep",
            "clear_line": "keep",
            "time_window": "keep",
            "reason": defaults["adjustment_reason"],
        },
        "next_watch": defaults["next_watch"],
        "risk_summary": defaults["risk_summary"],
        "evidence_used": supporting,
        "counter_evidence_label": defaults["counter_evidence_label"],
        "human_note": "手工执行，系统不会自动交易。",
    }


def _provider_holding_ai_review(review: Mapping[str, Any]) -> dict[str, Any]:
    config: AttributionProviderConfig = _provider_config()
    if not config.configured:
        raise DecisionLedgerError("AI provider not configured")
    system_prompt, user_prompt = _holding_ai_review_prompt(review)
    try:
        import httpx  # type: ignore

        body = {
            "model": config.model,
            "temperature": 0.1,
            "max_tokens": 1600,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if config.provider == "deepseek":
            body["response_format"] = {"type": "json_object"}
            body["thinking"] = {"type": "disabled"}

        with httpx.Client(timeout=config.timeout_seconds, trust_env=False) as client:
            response = client.post(
                _chat_completions_url(config),
                headers={
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
        response.raise_for_status()
        payload = response.json()
        content = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
        draft = _extract_json_object(content)
    except Exception as exc:
        raise DecisionLedgerError(f"holding AI provider unavailable: {exc}") from exc
    draft["_provider_meta"] = {
        "provider": config.provider,
        "model": config.model,
        "base_url": config.base_url,
    }
    return draft


def _attach_holding_ai_reviews(
    reviews: list[dict[str, Any]],
    *,
    expected_date: str,
) -> list[dict[str, Any]]:
    if not reviews:
        return reviews
    store = _holding_ai_review_store()
    cache = dict(store.get("items") or {}) if isinstance(store.get("items"), dict) else {}
    changed = False
    attached: list[dict[str, Any]] = []
    for review in reviews:
        cache_key = _holding_ai_cache_key(review, expected_date)
        cached = cache.get(cache_key)
        if isinstance(cached, dict):
            attached.append({**review, "holding_ai_review": cached})
            continue
        fallback_reason = ""
        try:
            raw = _provider_holding_ai_review(review)
        except DecisionLedgerError as exc:
            fallback_reason = str(exc)
            raw = _heuristic_holding_ai_review(review)
        sanitized = _sanitize_holding_ai_review(
            review=review,
            raw=raw,
            fallback_reason=fallback_reason,
        )
        cache[cache_key] = sanitized
        changed = True
        attached.append({**review, "holding_ai_review": sanitized})
    if changed:
        keys = sorted(cache.keys(), reverse=True)[:200]
        trimmed = {key: cache[key] for key in keys if key in cache}
        _holding_ai_review_save(
            {
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "items": trimmed,
            }
        )
    return attached


def build_portfolio_account_view(
    *,
    refresh_quotes: bool = False,
    formal_data_status: dict[str, Any] | None = None,
    include_holding_reviews: bool = True,
    include_account_history: bool = True,
    base_inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the canonical account-state view for the Portfolio page.

    Combines:
    * the canonical account book (mode, cash, fills, positions),
    * the today-action-decisions store so we can surface unreconciled
      "done" actions inline, and
    * a fresh ``compute_readiness`` payload so the front-end can render
      the same fail-closed gate it shows on the Today page.
    """

    base = dict(base_inputs) if isinstance(base_inputs, dict) else _today_base_inputs()
    trade_date_hint = str(base.get("trade_date_hint") or expected_trade_date())
    decision_brief = base.get("decision_brief") if isinstance(base.get("decision_brief"), dict) else None
    watchlist = base.get("watchlist") if isinstance(base.get("watchlist"), dict) else None
    screening_batch = base.get("screening_batch") if isinstance(base.get("screening_batch"), dict) else None
    confirmation = base.get("confirmation") if isinstance(base.get("confirmation"), dict) else None
    quality_status = base.get("quality_status") if isinstance(base.get("quality_status"), dict) else None
    account_book = base.get("account_book") if isinstance(base.get("account_book"), dict) else load_account_book()
    today_action_decisions = (
        base.get("today_action_decisions")
        if isinstance(base.get("today_action_decisions"), dict)
        else load_today_action_decision_store()
    )
    readiness = base.get("readiness") if isinstance(base.get("readiness"), dict) else None
    if readiness is None:
        now = datetime.now()
        readiness = resolve_readiness(
            base=base,
            watchlist=watchlist,
            screening_batch=screening_batch,
            confirmation=confirmation,
            decision_brief=decision_brief,
            quality_status=quality_status,
            account_book=account_book,
            today_action_decisions=today_action_decisions,
            dataset_freshness=build_dataset_freshness_rows(
                expected_date=trade_date_hint,
                now=now,
            ),
            formal_freshness=build_formal_freshness_rows(
                expected_date=trade_date_hint,
                now=now,
            ),
        )
    account_view = compute_account_view(account_book)
    cash_balance = float(account_view.get("cash_balance") or 0.0)

    # Resolve names for positions where we only stored the code.
    watchlist_index: dict[str, str] = {}

    def _code_aliases(value: Any) -> set[str]:
        code = str(value or "").strip().lower()
        if not code:
            return set()
        aliases = {code}
        bare = code[2:] if len(code) == 8 and code[:2].isalpha() else code
        aliases.add(bare)
        if len(bare) == 6 and bare.isdigit():
            aliases.add(f"sh{bare}" if bare.startswith("6") else f"sz{bare}")
        return aliases

    for stock in _portfolio_watchlist_items(watchlist):
        code = str(stock.get("code") or "").lower()
        name = str(stock.get("name") or "").strip()
        if code and name:
            for alias in _code_aliases(code):
                watchlist_index[alias] = name

    def _resolve_name(code: str, fallback: str) -> str:
        for alias in _code_aliases(code):
            if alias in watchlist_index:
                return watchlist_index[alias]
        return fallback or code

    open_positions = []
    for pos in account_view["open_positions"]:
        code = pos["code"]
        open_positions.append({**pos, "name": _resolve_name(code, pos.get("name") or code)})

    closed_positions = []
    for pos in account_view["closed_positions"]:
        code = pos["code"]
        closed_positions.append({**pos, "name": _resolve_name(code, pos.get("name") or code)})

    fills = [
        {**fill, "name": _resolve_name(str(fill.get("code") or ""), str(fill.get("name") or ""))}
        for fill in account_view["fills"]
    ]
    recent_fills = sorted(fills, key=lambda f: f.get("ts", ""), reverse=True)[:25]

    quote_index, market_status = _portfolio_quote_index(
        [str(pos.get("code") or "") for pos in open_positions],
        trade_date=str(readiness.get("expected_trade_date") or expected_trade_date()),
        refresh_quotes=refresh_quotes,
    )
    open_positions = _attach_portfolio_market_values(open_positions, quote_index)
    review_trade_date = str(readiness.get("expected_trade_date") or expected_trade_date())
    holding_reviews: list[dict[str, Any]] = []
    holding_action_summary: dict[str, Any] | None = None
    if include_holding_reviews:
        holding_reviews, holding_action_summary = _build_holding_reviews(
            open_positions,
            watchlist=watchlist,
            position_plans=account_view.get("position_plans") or [],
            expected_date=review_trade_date,
            readiness=readiness,
            screening_batch=screening_batch,
        )
        holding_reviews = _attach_holding_ai_reviews(
            holding_reviews,
            expected_date=review_trade_date,
        )
    market_value = round_money(sum(float(p.get("market_value") or 0.0) for p in open_positions if p.get("market_value") is not None))
    unrealized_pnl = round_money(sum(float(p.get("unrealized_pnl") or 0.0) for p in open_positions if p.get("unrealized_pnl") is not None))
    total_pnl = round_money(float(account_view["realized_pnl"]) + unrealized_pnl)
    missing_quote_count = len(market_status.get("missing_codes") or [])
    quote_value_detail = f"{len(open_positions)} 只持仓，未刷新行情"
    if market_status["status"] == "ok":
        quote_value_detail = f"{len(open_positions)} 只持仓，已按行情估值"
    elif market_status["status"] == "partial":
        quote_value_detail = f"{len(open_positions)} 只持仓，部分行情估值，缺 {missing_quote_count} 只"
    book_value = round_money(cash_balance + (market_value if market_status["status"] in {"ok", "partial"} else float(account_view["equity_at_cost"])))

    summary_cards = [
        {
            "label": "运行模式",
            "value": account_view["mode_label"],
            "detail": account_view.get("mode_updated_at") or "未设置",
            "tone": account_view["mode_tone"],
        },
        {
            "label": "可用现金",
            "value": f"¥{cash_balance:,.2f}",
            "detail": f"本金 ¥{account_view['starting_cash'] + account_view['deposits_total']:,.2f}",
            "tone": "risk" if cash_balance < 0 else "info",
        },
        {
            "label": "持仓市值",
            "value": f"¥{market_value:,.2f}" if market_status["status"] in {"ok", "partial"} else f"¥{account_view['equity_at_cost']:,.2f}",
            "detail": quote_value_detail,
            "tone": "watch" if open_positions else "info",
        },
        {
            "label": "总盈亏",
            "value": f"¥{total_pnl:,.2f}",
            "detail": f"浮盈亏 ¥{unrealized_pnl:,.2f} / 已实现 ¥{account_view['realized_pnl']:,.2f}",
            "tone": "positive" if total_pnl >= 0 else "risk",
        },
    ]

    account_state = readiness.get("account_state") or {}
    account_payload = {
        **account_view,
        "book_value": book_value,
        "market_value": market_value if market_status["status"] in {"ok", "partial"} else None,
        "unrealized_pnl": unrealized_pnl if market_status["status"] in {"ok", "partial"} else None,
        "total_pnl": total_pnl,
        "open_positions": open_positions,
        "closed_positions": closed_positions,
        "available_modes": list(ACCOUNT_MODES),
    }
    if not include_account_history:
        for key in (
            "fills",
            "closed_positions",
            "reconciliations",
            "position_plans",
            "identity_corrections",
            "mode_history",
            "available_modes",
        ):
            account_payload.pop(key, None)

    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "trade_date": readiness.get("expected_trade_date"),
        "expected_trade_date": readiness.get("expected_trade_date"),
        "data_trade_date": readiness.get("data_trade_date"),
        "readiness": public_portfolio_readiness(readiness, formal_data_status),
        "account": account_payload,
        "market_quotes": market_status,
        "holding_reviews_deferred": not include_holding_reviews,
        "account_history_deferred": not include_account_history,
        "summary_cards": summary_cards,
        "recent_fills": recent_fills,
        "unreconciled_intents": account_state.get("unreconciled_intents", []),
        "reconciliation": account_state.get("reconciliation", {}),
        "ready_for_live_small": bool(account_state.get("ready_for_live_small")),
        "links": {
            "today": "/today",
            "watchlist": "/watchlist",
            "portfolio": "/portfolio",
        },
    }
    if include_holding_reviews:
        payload["holding_reviews"] = holding_reviews
        payload["holding_action_summary"] = holding_action_summary or {}
    return payload
