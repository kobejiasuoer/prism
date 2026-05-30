from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any


CONTROL_PANEL_ROOT = Path(__file__).resolve().parent
REPO_ROOT = CONTROL_PANEL_ROOT.parents[1]
DATASET_ROOT = REPO_ROOT / "data" / "prism_data" / "datasets"
FORMAL_LATEST = REPO_ROOT / "data" / "prism_data" / "tinyshare_harvest" / "latest_run.json"
RESEARCH_LATEST = REPO_ROOT / "data" / "prism_data" / "tinyshare_research_harvest" / "latest_run.json"
MARKET_LATEST = REPO_ROOT / "data" / "prism_data" / "tinyshare_market_supplement" / "latest_run.json"
REFERENCE_LATEST = REPO_ROOT / "data" / "prism_data" / "tinyshare_reference_supplement" / "latest_run.json"


ASSET_CATALOG: tuple[dict[str, str], ...] = (
    {"dataset": "trade_calendar", "label": "交易日历", "purpose": "正式交易日对齐"},
    {"dataset": "bars.daily", "label": "正式日线", "purpose": "复权/价格底座"},
    {"dataset": "adjustment.factor", "label": "复权因子", "purpose": "价格复权"},
    {"dataset": "benchmark.index_daily", "label": "指数日线", "purpose": "基准对照"},
    {"dataset": "price_limit.daily", "label": "涨跌停价", "purpose": "执行约束"},
    {"dataset": "execution.flags", "label": "执行标记", "purpose": "ST/停牌/涨跌停约束"},
    {"dataset": "valuation.daily", "label": "估值历史", "purpose": "PE/PB/市值"},
    {"dataset": "liquidity.daily", "label": "流动性历史", "purpose": "换手/量比/股本"},
    {"dataset": "capital_flow.daily", "label": "资金流历史", "purpose": "主力净流入"},
    {"dataset": "fundamentals.snapshot", "label": "基本面快照", "purpose": "ROE/收入/现金流"},
    {"dataset": "financial.indicator", "label": "财务指标", "purpose": "盈利质量"},
    {"dataset": "financial.statement", "label": "财务报表", "purpose": "收入/资产/现金流"},
    {"dataset": "corporate_action.dividend", "label": "分红送配", "purpose": "公司行为"},
    {"dataset": "shareholder.top10", "label": "前十大股东", "purpose": "股东结构"},
    {"dataset": "market.limit_events", "label": "涨跌停事件", "purpose": "市场情绪"},
    {"dataset": "index.weight", "label": "指数成分权重", "purpose": "沪深300/中证500/中证1000权重"},
    {"dataset": "market.daily_basic_snapshot", "label": "全市场日指标", "purpose": "全市场估值/资产快照"},
    {"dataset": "market.margin", "label": "两融总量", "purpose": "杠杆情绪"},
    {"dataset": "market.top_list", "label": "龙虎榜", "purpose": "异常交易"},
    {"dataset": "market.top_inst", "label": "龙虎榜机构席位", "purpose": "机构席位流向"},
    {"dataset": "market.hsgt_moneyflow", "label": "北向/南向资金", "purpose": "跨境资金"},
    {"dataset": "market.ggt_daily", "label": "港股通日汇总", "purpose": "港股通成交"},
    {"dataset": "reference.stock_company", "label": "公司画像", "purpose": "注册地址/主营/公司资料"},
    {"dataset": "reference.namechange", "label": "名称变更", "purpose": "简称/历史名称追溯"},
    {"dataset": "reference.concept", "label": "概念字典", "purpose": "概念归因字典"},
    {"dataset": "reference.concept_detail", "label": "概念归属", "purpose": "个股概念标签"},
    {"dataset": "reference.industry_classify", "label": "行业分类", "purpose": "申万行业树"},
    {"dataset": "reference.industry_member", "label": "行业成分", "purpose": "申万行业归属"},
    {"dataset": "reference.ths_index", "label": "同花顺板块", "purpose": "THS 行业/概念字典"},
    {"dataset": "reference.ths_member", "label": "同花顺成分", "purpose": "THS 板块归属"},
    {"dataset": "reference.dc_index", "label": "东财板块", "purpose": "东财行业/概念字典"},
    {"dataset": "reference.dc_member", "label": "东财成分", "purpose": "东财板块归属"},
    {"dataset": "financial.main_business", "label": "主营构成", "purpose": "产品/地区/行业收入结构"},
    {"dataset": "market.margin_detail", "label": "两融明细", "purpose": "个股两融变化"},
    {"dataset": "market.margin_secs", "label": "两融标的", "purpose": "融资融券标的池"},
    {"dataset": "market.block_trade", "label": "大宗交易", "purpose": "大额折溢价成交"},
    {"dataset": "market.hsgt_top10", "label": "陆股通十大", "purpose": "北向活跃成交"},
    {"dataset": "market.ggt_top10", "label": "港股通十大", "purpose": "南向活跃成交"},
    {"dataset": "corporate_action.pledge_stat", "label": "质押统计", "purpose": "股权质押风险"},
    {"dataset": "corporate_action.pledge_detail", "label": "质押明细", "purpose": "股权质押事件"},
    {"dataset": "corporate_action.share_float", "label": "限售解禁", "purpose": "解禁压力"},
    {"dataset": "corporate_action.repurchase", "label": "股份回购", "purpose": "回购进展"},
    {"dataset": "financial.audit", "label": "审计意见", "purpose": "财报审计质量"},
    {"dataset": "research.report_rc", "label": "研报评级", "purpose": "卖方预期变化"},
    {"dataset": "technical.stk_factor", "label": "技术因子", "purpose": "技术/筹码补充"},
    {"dataset": "technical.cyq_perf", "label": "筹码表现", "purpose": "筹码分布指标"},
    {"dataset": "technical.cyq_chips", "label": "筹码明细", "purpose": "筹码分布明细"},
)


def _sanitize(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "default"
    return "".join(ch if ch.isalnum() or ch in {"-", "_", ".", "+"} else "_" for ch in text)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_json_or_none(path: Path) -> Any | None:
    try:
        return _read_json(path)
    except Exception:
        return None


def _load_dataset(dataset: str, trade_date: str, key: str) -> tuple[Any, dict[str, Any] | None]:
    data_path = DATASET_ROOT / _sanitize(dataset) / _sanitize(trade_date) / f"{_sanitize(key)}.json"
    manifest_path = DATASET_ROOT / _sanitize(dataset) / _sanitize(trade_date) / f"{_sanitize(key)}.manifest.json"
    if not data_path.exists():
        return None, None
    return _read_json_or_none(data_path), _read_json_or_none(manifest_path)


def _list_manifests(dataset: str) -> list[dict[str, Any]]:
    dataset_dir = DATASET_ROOT / _sanitize(dataset)
    if not dataset_dir.exists():
        return []
    manifests: list[dict[str, Any]] = []
    for path in sorted(dataset_dir.glob("*/*.manifest.json")):
        payload = _read_json_or_none(path)
        if isinstance(payload, dict):
            payload.setdefault("manifest_path", str(path.resolve()))
            manifests.append(payload)
    return manifests


def _manifest_sort_key(manifest: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(manifest.get("trade_date") or ""),
        str(manifest.get("fetched_at") or manifest.get("generated_at") or ""),
        str(manifest.get("request_key") or ""),
    )


def _latest_manifest(manifests: list[dict[str, Any]], expected_trade_date: str | None = None) -> dict[str, Any] | None:
    rows = [item for item in manifests if not expected_trade_date or item.get("trade_date") == expected_trade_date]
    if not rows:
        rows = manifests
    return sorted(rows, key=_manifest_sort_key)[-1] if rows else None


def _count_keys_for_date(manifests: list[dict[str, Any]], trade_date: str | None) -> int:
    if not trade_date:
        return 0
    return len({str(item.get("request_key") or Path(str(item.get("manifest_path") or "")).name) for item in manifests if item.get("trade_date") == trade_date})


def _harvest_run(path: Path, label: str) -> dict[str, Any] | None:
    latest = _read_json_or_none(path)
    if not isinstance(latest, dict):
        return None
    report_path = Path(str(latest.get("report_path") or ""))
    report = _read_json_or_none(report_path) if report_path.exists() else None
    payload = report if isinstance(report, dict) else {}
    return {
        "label": label,
        "run_dir": latest.get("run_dir"),
        "report_path": latest.get("report_path"),
        "ok": payload.get("ok"),
        "start_date": payload.get("start_date"),
        "end_date": payload.get("end_date"),
        "trade_date": payload.get("trade_date"),
        "universe_count": payload.get("universe_count"),
        "trade_days": payload.get("trade_days") or payload.get("recent_trade_days"),
        "datasets": payload.get("datasets") or [],
        "events": payload.get("events") or {},
        "finished_at": payload.get("finished_at"),
        "token_value_visible": False,
    }


def build_data_assets_status(expected_trade_date: str | None = None) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    all_manifest_count = 0
    tushare_ready_count = 0
    for item in ASSET_CATALOG:
        dataset = item["dataset"]
        manifests = _list_manifests(dataset)
        all_manifest_count += len(manifests)
        latest = _latest_manifest(manifests, expected_trade_date)
        provider = str((latest or {}).get("provider") or "")
        available = bool(latest)
        if provider == "tushare" and available:
            tushare_ready_count += 1
        latest_trade_date = str((latest or {}).get("trade_date") or "")
        rows.append({
            "dataset": dataset,
            "label": item["label"],
            "purpose": item["purpose"],
            "available": available,
            "provider": provider or "-",
            "trade_date": latest_trade_date or None,
            "key_count": _count_keys_for_date(manifests, latest_trade_date),
            "manifest_count": len(manifests),
            "latest_row_count": (latest or {}).get("row_count"),
            "freshness_status": (latest or {}).get("freshness_status"),
            "source_lane": (latest or {}).get("source_lane"),
            "decision_scope": (latest or {}).get("decision_scope"),
            "source_authority_ready": bool((latest or {}).get("source_authority_ready")),
            "formal_decision_allowed": bool((latest or {}).get("formal_decision_allowed")),
            "source_endpoint": (latest or {}).get("source_endpoint"),
            "manifest_path": (latest or {}).get("manifest_path"),
        })

    runs = [
        item
        for item in (
            _harvest_run(FORMAL_LATEST, "正式底座"),
            _harvest_run(RESEARCH_LATEST, "研究扩展"),
            _harvest_run(MARKET_LATEST, "市场专题"),
            _harvest_run(REFERENCE_LATEST, "画像板块补采"),
        )
        if item
    ]
    promotion_report = None
    research_run = next((item for item in runs if item.get("label") == "研究扩展"), None)
    if research_run and research_run.get("run_dir"):
        promotion_report = _read_json_or_none(Path(str(research_run["run_dir"])) / "promotion_report.json")

    universe_count = 0
    trade_days = 0
    for run in runs:
        universe_count = max(universe_count, int(run.get("universe_count") or 0))
        trade_days = max(trade_days, int(run.get("trade_days") or 0))

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "expected_trade_date": expected_trade_date,
        "dataset_root": str(DATASET_ROOT.resolve()),
        "summary": {
            "catalog_count": len(ASSET_CATALOG),
            "available_count": sum(1 for row in rows if row["available"]),
            "tushare_ready_count": tushare_ready_count,
            "manifest_count": all_manifest_count,
            "universe_count": universe_count,
            "trade_days": trade_days,
        },
        "visible_usage": [
            "Settings 数据资产面板",
            "个股页 Tushare 档案",
            "readiness 正式底座闸门",
            "后续扫描解释因子",
        ],
        "datasets": rows,
        "harvest_runs": runs,
        "promotion_report": promotion_report if isinstance(promotion_report, dict) else None,
    }


def _normalize_code(value: Any) -> str:
    text = str(value or "").strip().upper()
    if "." in text:
        text = text.split(".", 1)[0]
    return "".join(ch for ch in text if ch.isdigit()).zfill(6)


def _compact_date(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())[:8]


def _date_key(row: dict[str, Any], fields: tuple[str, ...]) -> str:
    for field in fields:
        value = _compact_date(row.get(field))
        if value:
            return value
    return ""


def _latest_row(rows: Any, *fields: str) -> dict[str, Any] | None:
    if not isinstance(rows, list):
        return None
    dict_rows = [row for row in rows if isinstance(row, dict)]
    if not dict_rows:
        return None
    return sorted(dict_rows, key=lambda row: _date_key(row, fields or ("trade_date", "end_date", "ann_date")))[-1]


def _safe_float(value: Any) -> float | None:
    if value in (None, "", "-", "None"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else number


def _json_clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_clean(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_clean(item) for item in value]
    if isinstance(value, tuple):
        return [_json_clean(item) for item in value]
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _display_number(value: Any, suffix: str = "", digits: int = 2) -> str:
    number = _safe_float(value)
    if number is None:
        return "-"
    if abs(number) >= 1000:
        text = f"{number:,.0f}"
    else:
        text = f"{number:.{digits}f}".rstrip("0").rstrip(".")
    return f"{text}{suffix}"


def _metric(label: str, value: Any, detail: str = "", tone: str = "info") -> dict[str, Any]:
    return {"label": label, "value": value if value not in (None, "") else "-", "detail": detail, "tone": tone}


def _source_card(label: str, manifest: dict[str, Any] | None, detail: str = "") -> dict[str, Any]:
    return {
        "label": label,
        "value": str((manifest or {}).get("trade_date") or "未命中"),
        "detail": detail or str((manifest or {}).get("freshness_status") or (manifest or {}).get("provider") or ""),
        "available": bool(manifest),
        "source_lane": (manifest or {}).get("source_lane"),
        "decision_scope": (manifest or {}).get("decision_scope"),
        "authority_provider": (manifest or {}).get("authority_provider"),
        "source_authority_ready": bool((manifest or {}).get("source_authority_ready")),
        "formal_decision_allowed": bool((manifest or {}).get("formal_decision_allowed")),
    }


def _filter_code(rows: Any, code: str) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    result = []
    for row in rows:
        if isinstance(row, dict) and _normalize_code(row.get("ts_code") or row.get("con_code") or row.get("code") or row.get("symbol")) == code:
            result.append(row)
    return result


def _load_latest_market_rows(dataset: str, trade_date: str, key: str, code: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    rows, manifest = _load_dataset(dataset, trade_date, key)
    return _filter_code(rows, code), manifest


def _load_index_memberships(trade_date: str, code: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    dataset_dir = DATASET_ROOT / "index.weight" / _sanitize(trade_date)
    memberships: list[dict[str, Any]] = []
    manifests: list[dict[str, Any]] = []
    if not dataset_dir.exists():
        return memberships, manifests
    for data_path in sorted(dataset_dir.glob("*.json")):
        if data_path.name.endswith(".manifest.json"):
            continue
        rows = _read_json_or_none(data_path)
        hits = _filter_code(rows, code)
        if hits:
            memberships.extend(hits)
            manifest = _read_json_or_none(data_path.with_name(f"{data_path.stem}.manifest.json"))
            if isinstance(manifest, dict):
                manifests.append(manifest)
    return memberships, manifests


def build_stock_formal_data(code: str, trade_date: str | None = None) -> dict[str, Any]:
    normalized_code = _normalize_code(code)
    target_date = trade_date or ""
    valuation_rows, valuation_manifest = _load_dataset("valuation.daily", target_date, normalized_code)
    liquidity_rows, liquidity_manifest = _load_dataset("liquidity.daily", target_date, normalized_code)
    capital_rows, capital_manifest = _load_dataset("capital_flow.daily", target_date, normalized_code)
    fundamentals, fundamentals_manifest = _load_dataset("fundamentals.snapshot", target_date, normalized_code)
    indicators, indicator_manifest = _load_dataset("financial.indicator", target_date, normalized_code)
    statements, statement_manifest = _load_dataset("financial.statement", target_date, normalized_code)
    dividends, dividend_manifest = _load_dataset("corporate_action.dividend", target_date, normalized_code)
    shareholders, shareholder_manifest = _load_dataset("shareholder.top10", target_date, normalized_code)
    daily_basic_rows, daily_basic_manifest = _load_latest_market_rows("market.daily_basic_snapshot", target_date, "all", normalized_code)
    top_list_rows, top_list_manifest = _load_latest_market_rows("market.top_list", target_date, "recent", normalized_code)
    top_inst_rows, top_inst_manifest = _load_latest_market_rows("market.top_inst", target_date, "recent", normalized_code)
    index_memberships, index_manifests = _load_index_memberships(target_date, normalized_code)

    valuation = _latest_row(valuation_rows, "trade_date") or _latest_row(daily_basic_rows, "trade_date") or {}
    liquidity = _latest_row(liquidity_rows, "trade_date") or {}
    capital = _latest_row(capital_rows, "trade_date") or {}
    indicator = _latest_row(indicators, "end_date", "ann_date") or {}
    fundamental = fundamentals if isinstance(fundamentals, dict) else {}
    statement = statements if isinstance(statements, dict) else {}
    income = _latest_row(statement.get("income"), "end_date", "ann_date") or {}
    balance = _latest_row(statement.get("balancesheet"), "end_date", "ann_date") or {}
    cashflow = _latest_row(statement.get("cashflow"), "end_date", "ann_date") or {}
    latest_dividends = sorted(
        [row for row in dividends if isinstance(row, dict)] if isinstance(dividends, list) else [],
        key=lambda row: _date_key(row, ("ex_date", "record_date", "ann_date", "end_date")),
        reverse=True,
    )[:5]
    holder_rows = []
    if isinstance(shareholders, dict):
        holder_rows = sorted(
            [row for row in shareholders.get("top10_holders") or [] if isinstance(row, dict)],
            key=lambda row: _date_key(row, ("end_date", "ann_date")),
            reverse=True,
        )[:5]

    index_weight_total = sum(_safe_float(row.get("weight")) or 0.0 for row in index_memberships)
    metric_cards = [
        _metric("PE TTM", _display_number(valuation.get("pe_ttm") or fundamental.get("pe_ttm") or fundamental.get("pe")), "Tushare daily_basic", "info"),
        _metric("PB", _display_number(valuation.get("pb") or fundamental.get("pb")), "Tushare daily_basic", "info"),
        _metric("ROE", _display_number(indicator.get("roe") or fundamental.get("roe"), "%"), "最新财务指标", "watch"),
        _metric("总市值", _display_number(valuation.get("total_mv_yi") or fundamental.get("total_mv_yi"), " 亿"), "估值快照", "info"),
        _metric("主力净流入", _display_number(capital.get("main_net_yi"), " 亿"), "moneyflow", "watch"),
        _metric("换手率", _display_number(liquidity.get("turnover_rate_f") or liquidity.get("turnover_rate"), "%"), "流动性", "info"),
        _metric("指数权重", _display_number(index_weight_total, "%"), "沪深300/中证500/中证1000", "positive" if index_weight_total else "info"),
        _metric("龙虎榜", str(len(top_list_rows)), "近窗口命中次数", "watch" if top_list_rows else "info"),
    ]
    source_cards = [
        _source_card("估值历史", valuation_manifest),
        _source_card("资金流历史", capital_manifest),
        _source_card("基本面快照", fundamentals_manifest),
        _source_card("财务指标", indicator_manifest),
        _source_card("股东结构", shareholder_manifest),
        _source_card("分红送配", dividend_manifest),
        _source_card("全市场日指标", daily_basic_manifest),
        _source_card("龙虎榜", top_list_manifest),
        _source_card("机构席位", top_inst_manifest),
    ]
    if index_manifests:
        source_cards.append(_source_card("指数权重", index_manifests[0], f"{len(index_memberships)} 个指数命中"))

    available = any(card.get("available") for card in source_cards)
    payload = {
        "available": available,
        "code": normalized_code,
        "trade_date": target_date,
        "provider": "tushare/tinyshare",
        "headline": "Tushare 数据已接入个股档案" if available else "当前个股未命中已灌入的 Tushare 数据",
        "summary": (
            "估值、资金流、财务、股东、分红、指数权重和龙虎榜以只读研究证据展示，不自动放大真钱权限。"
            if available
            else "这只股票可能不在已灌入的沪深300/中证500/中证1000窗口内，或专题补采尚未完成。"
        ),
        "metric_cards": metric_cards,
        "valuation": valuation,
        "liquidity": liquidity,
        "capital_flow": capital,
        "fundamental": fundamental,
        "financial_quality": {
            "indicator": indicator,
            "income": income,
            "balance": balance,
            "cashflow": cashflow,
        },
        "index_memberships": index_memberships,
        "top_list": top_list_rows[:8],
        "top_inst": top_inst_rows[:8],
        "dividends": latest_dividends,
        "shareholders": holder_rows,
        "source_cards": source_cards,
    }
    return _json_clean(payload)
