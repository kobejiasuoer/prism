from __future__ import annotations

import json
import math
import os
import time
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from data_feature_registry import feature_usage


CONTROL_PANEL_ROOT = Path(__file__).resolve().parent
REPO_ROOT = CONTROL_PANEL_ROOT.parents[1]
DATASET_ROOT = REPO_ROOT / "data" / "prism_data" / "datasets"
FORMAL_LATEST = REPO_ROOT / "data" / "prism_data" / "tinyshare_harvest" / "latest_run.json"
RESEARCH_LATEST = REPO_ROOT / "data" / "prism_data" / "tinyshare_research_harvest" / "latest_run.json"
MARKET_LATEST = REPO_ROOT / "data" / "prism_data" / "tinyshare_market_supplement" / "latest_run.json"
REFERENCE_LATEST = REPO_ROOT / "data" / "prism_data" / "tinyshare_reference_supplement" / "latest_run.json"
DATA_ASSETS_STATUS_CACHE_TTL_SECONDS = 60
_DATA_ASSETS_STATUS_CACHE: dict[tuple[str, str, str], tuple[float, dict[str, Any]]] = {}


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

STOCK_FORMAL_EVIDENCE_DATASETS: tuple[str, ...] = (
    "price_limit.daily",
    "execution.flags",
    "valuation.daily",
    "liquidity.daily",
    "capital_flow.daily",
    "fundamentals.snapshot",
    "financial.indicator",
    "financial.statement",
    "corporate_action.dividend",
    "shareholder.top10",
    "market.daily_basic_snapshot",
    "market.top_list",
    "market.top_inst",
    "index.weight",
    "reference.stock_company",
    "reference.namechange",
    "reference.concept_detail",
    "reference.industry_member",
    "reference.ths_member",
    "reference.dc_member",
    "financial.main_business",
    "market.margin_detail",
    "market.margin_secs",
    "market.block_trade",
    "corporate_action.pledge_stat",
    "corporate_action.pledge_detail",
    "corporate_action.share_float",
    "corporate_action.repurchase",
    "financial.audit",
    "research.report_rc",
    "technical.stk_factor",
    "technical.cyq_perf",
    "technical.cyq_chips",
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


def _manifest_key_from_name(name: str) -> str:
    if name.endswith(".manifest.json"):
        return name[: -len(".manifest.json")]
    return Path(name).stem


def _load_manifest_path(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    payload = _read_json_or_none(path)
    if not isinstance(payload, dict):
        return None
    payload.setdefault("manifest_path", str(path.resolve()))
    return payload


def _dataset_manifest_summary(dataset: str, expected_trade_date: str | None) -> dict[str, Any]:
    dataset_dir = DATASET_ROOT / _sanitize(dataset)
    if not dataset_dir.exists():
        return {"manifest_count": 0, "latest": None, "key_count": 0}

    expected = _sanitize(expected_trade_date) if expected_trade_date else ""
    manifest_count = 0
    expected_entries: list[tuple[str, str]] = []
    latest_date = ""
    latest_entries: list[tuple[str, str]] = []

    try:
        date_entries = [entry for entry in os.scandir(dataset_dir) if entry.is_dir()]
    except OSError:
        return {"manifest_count": 0, "latest": None, "key_count": 0}

    for date_entry in date_entries:
        try:
            entries = [
                (entry.name, entry.path)
                for entry in os.scandir(date_entry.path)
                if entry.name.endswith(".manifest.json") and entry.is_file()
            ]
        except OSError:
            continue
        if not entries:
            continue
        manifest_count += len(entries)
        date_name = date_entry.name
        if expected and date_name == expected:
            expected_entries = entries
        if date_name > latest_date:
            latest_date = date_name
            latest_entries = entries

    display_entries = expected_entries or latest_entries
    latest_path = None
    if display_entries:
        def latest_entry_key(item: tuple[str, str]) -> tuple[float, str]:
            try:
                mtime = os.stat(item[1]).st_mtime
            except OSError:
                mtime = 0.0
            return (mtime, item[0])

        latest_path = Path(max(display_entries, key=latest_entry_key)[1])
    latest = _load_manifest_path(latest_path)
    return {
        "manifest_count": manifest_count,
        "latest": latest,
        "key_count": len({_manifest_key_from_name(name) for name, _path in display_entries}),
    }


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


def clear_data_assets_status_cache() -> None:
    _DATA_ASSETS_STATUS_CACHE.clear()


COMPACT_DATASET_LIMIT = 6
COMPACT_DATASET_PRIORITY: tuple[str, ...] = (
    "bars.daily",
    "adjustment.factor",
    "price_limit.daily",
    "execution.flags",
    "index.weight",
    "market.daily_basic_snapshot",
)
COMPACT_DATASET_FIELDS: tuple[str, ...] = (
    "dataset",
    "label",
    "purpose",
    "feature_group",
    "decision_use",
    "live_permission",
    "available",
    "provider",
    "trade_date",
    "key_count",
    "manifest_count",
    "latest_row_count",
    "freshness_status",
    "source_authority_ready",
    "formal_decision_allowed",
)


def _compact_data_asset_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    priority = {dataset: index for index, dataset in enumerate(COMPACT_DATASET_PRIORITY)}

    def sort_key(row: dict[str, Any]) -> tuple[int, int, int, str]:
        dataset = str(row.get("dataset") or "")
        if dataset in priority:
            bucket = 0
            order = priority[dataset]
        elif row.get("available"):
            bucket = 1
            order = -int(row.get("key_count") or 0)
        else:
            bucket = 2
            order = 0
        return (bucket, order, -int(row.get("manifest_count") or 0), dataset)

    selected = sorted(rows, key=sort_key)[:COMPACT_DATASET_LIMIT]
    return [
        {
            key: row.get(key)
            for key in COMPACT_DATASET_FIELDS
            if row.get(key) not in (None, "", [], {})
        }
        for row in selected
    ]


def _compact_harvest_run(run: dict[str, Any]) -> dict[str, Any]:
    datasets = run.get("datasets") if isinstance(run.get("datasets"), list) else []
    return {
        key: value
        for key, value in {
            "label": run.get("label"),
            "ok": run.get("ok"),
            "start_date": run.get("start_date"),
            "end_date": run.get("end_date"),
            "trade_date": run.get("trade_date"),
            "universe_count": run.get("universe_count"),
            "trade_days": run.get("trade_days"),
            "datasets": datasets[:4],
            "finished_at": run.get("finished_at"),
        }.items()
        if value not in (None, "", [], {})
    }


def build_data_assets_status(
    expected_trade_date: str | None = None,
    *,
    fresh: bool = False,
    compact: bool = False,
) -> dict[str, Any]:
    cache_key = (str(DATASET_ROOT.resolve()), str(expected_trade_date or ""), "compact" if compact else "full")
    cached = _DATA_ASSETS_STATUS_CACHE.get(cache_key)
    now = time.monotonic()
    if cached and not fresh and now - cached[0] <= DATA_ASSETS_STATUS_CACHE_TTL_SECONDS:
        return deepcopy(cached[1])

    rows: list[dict[str, Any]] = []
    all_manifest_count = 0
    tushare_ready_count = 0
    for item in ASSET_CATALOG:
        dataset = item["dataset"]
        usage = feature_usage(dataset)
        manifest_summary = _dataset_manifest_summary(dataset, expected_trade_date)
        all_manifest_count += int(manifest_summary["manifest_count"])
        latest = manifest_summary["latest"]
        provider = str((latest or {}).get("provider") or "")
        available = bool(latest)
        if provider == "tushare" and available:
            tushare_ready_count += 1
        latest_trade_date = str((latest or {}).get("trade_date") or "")
        rows.append({
            "dataset": dataset,
            "label": item["label"],
            "purpose": item["purpose"],
            "feature_group": usage["group"],
            "decision_use": usage["decision_use"],
            "live_permission": usage["live_permission"],
            "intended_surfaces": usage["intended_surfaces"],
            "usage_explanation": usage["explanation"],
            "available": available,
            "provider": provider or "-",
            "trade_date": latest_trade_date or None,
            "key_count": int(manifest_summary["key_count"]),
            "manifest_count": int(manifest_summary["manifest_count"]),
            "latest_row_count": (latest or {}).get("row_count"),
            "freshness_status": (latest or {}).get("freshness_status"),
            "source_lane": (latest or {}).get("source_lane"),
            "decision_scope": (latest or {}).get("decision_scope"),
            "source_authority_ready": bool((latest or {}).get("source_authority_ready")),
            "formal_decision_allowed": bool((latest or {}).get("formal_decision_allowed")),
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
    if not compact and research_run and research_run.get("run_dir"):
        promotion_report = _read_json_or_none(Path(str(research_run["run_dir"])) / "promotion_report.json")

    universe_count = 0
    trade_days = 0
    for run in runs:
        universe_count = max(universe_count, int(run.get("universe_count") or 0))
        trade_days = max(trade_days, int(run.get("trade_days") or 0))

    summary = {
        "catalog_count": len(ASSET_CATALOG),
        "available_count": sum(1 for row in rows if row["available"]),
        "tushare_ready_count": tushare_ready_count,
        "manifest_count": all_manifest_count,
        "universe_count": universe_count,
        "trade_days": trade_days,
    }
    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "expected_trade_date": expected_trade_date,
        "compact": compact,
        "datasets_deferred": compact,
        "summary": summary,
        "visible_usage": [
            "Settings 数据资产面板",
            "个股页 Tushare 档案",
            "readiness 正式底座闸门",
            "观察池解释因子和风险标签",
            "候选生命周期复盘快照",
        ],
        "datasets": _compact_data_asset_rows(rows) if compact else rows,
        "harvest_runs": [_compact_harvest_run(run) for run in runs] if compact else runs,
        "promotion_report": promotion_report if isinstance(promotion_report, dict) else None,
    }
    if compact:
        payload["visible_usage"] = []
        payload["promotion_report"] = None
        payload["summary"] = {
            **summary,
            "displayed_dataset_count": len(payload["datasets"]),
        }
    _DATA_ASSETS_STATUS_CACHE[cache_key] = (now, payload)
    return deepcopy(payload)


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


def _source_card(label: str, dataset: str, manifest: dict[str, Any] | None, detail: str = "") -> dict[str, Any]:
    usage = feature_usage(dataset)
    formal_allowed = (
        bool((manifest or {}).get("formal_decision_allowed"))
        and usage["decision_use"] == "hard_gate"
        and usage["live_permission"] == "formal_candidate"
    )
    return {
        "dataset": dataset,
        "usage": usage,
        "feature_group": usage["group"],
        "decision_use": usage["decision_use"],
        "live_permission": usage["live_permission"],
        "intended_surfaces": usage["intended_surfaces"],
        "usage_explanation": usage["explanation"],
        "stock_profile_use": "evidence_only",
        "label": label,
        "value": str((manifest or {}).get("trade_date") or "未命中"),
        "detail": detail or str((manifest or {}).get("freshness_status") or (manifest or {}).get("provider") or ""),
        "available": bool(manifest),
        "source_lane": (manifest or {}).get("source_lane"),
        "decision_scope": (manifest or {}).get("decision_scope"),
        "authority_provider": (manifest or {}).get("authority_provider"),
        "source_authority_ready": bool((manifest or {}).get("source_authority_ready")),
        "formal_decision_allowed": formal_allowed,
    }


def _compact_source_card(card: dict[str, Any]) -> dict[str, Any]:
    payload = {
        key: card.get(key)
        for key in (
            "dataset",
            "label",
            "value",
            "detail",
            "available",
            "stock_profile_use",
            "decision_use",
            "live_permission",
            "stale",
            "stale_reasons",
        )
        if card.get(key) not in (None, "", [], {})
    }
    return payload


def _compact_source_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_compact_source_card(card) for card in cards]


def _compact_fields(row: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    return {
        field: row.get(field)
        for field in fields
        if row.get(field) not in (None, "", [], {})
    }


def _compact_rows(rows: Any, fields: tuple[str, ...], limit: int) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    return [
        item
        for item in (_compact_fields(row, fields) for row in rows[:limit])
        if item
    ]


def _compact_profile_for_section(profile: dict[str, Any]) -> dict[str, Any]:
    payload = _compact_fields(
        profile,
        (
            "name",
            "full_name",
            "province",
            "city",
            "area",
            "industry",
            "main_business",
            "list_date",
            "exchange",
            "market",
        ),
    )
    name_changes = _compact_rows(
        profile.get("name_changes"),
        ("name", "ann_name", "change_reason", "start_date", "end_date", "ann_date"),
        3,
    )
    if name_changes:
        payload["name_changes"] = name_changes
    return payload


def _compact_business_breakdown_for_section(payload: dict[str, Any]) -> dict[str, Any]:
    item_fields = ("item", "sales", "profit", "cost", "currency")
    compact = _compact_fields(payload, ("end_date", "top_share", "concentration_label"))
    compact["top_items"] = _compact_rows(payload.get("top_items"), item_fields, 4)
    by_type = payload.get("by_type") if isinstance(payload.get("by_type"), dict) else {}
    compact_by_type = {
        str(label): rows
        for label, rows in (
            (label, _compact_rows(type_rows, item_fields, 1))
            for label, type_rows in by_type.items()
        )
        if rows
    }
    if compact_by_type:
        compact["by_type"] = compact_by_type
    return compact


def _compact_event_risks_for_section(event_risks: dict[str, Any]) -> dict[str, Any]:
    pledge = event_risks.get("pledge") if isinstance(event_risks.get("pledge"), dict) else {}
    share_float = event_risks.get("share_float") if isinstance(event_risks.get("share_float"), dict) else {}
    repurchase = event_risks.get("repurchase") if isinstance(event_risks.get("repurchase"), dict) else {}
    audit = event_risks.get("audit") if isinstance(event_risks.get("audit"), dict) else {}
    research = event_risks.get("research") if isinstance(event_risks.get("research"), dict) else {}
    payload = {
        "pledge": _compact_fields(pledge, ("pledge_ratio",)),
        "share_float": _compact_fields(share_float, ("total_float_amount", "total_float_mv")),
        "repurchase": _compact_fields(repurchase, ("total_amount",)),
        "audit": _compact_fields(audit, ("abnormal", "opinion")),
        "research": _compact_fields(research, ("average_target_price", "downgrade_signal")),
    }
    if event_risks.get("research_deferred") is not None:
        payload["research_deferred"] = bool(event_risks.get("research_deferred"))
    if event_risks.get("research_endpoint"):
        payload["research_endpoint"] = event_risks.get("research_endpoint")
    return payload


def _source_choice(*choices: tuple[str, dict[str, Any] | None]) -> tuple[str, dict[str, Any] | None]:
    for dataset, manifest in choices:
        if manifest:
            return dataset, manifest
    return choices[0] if choices else ("", None)


def _stock_formal_candidate_dates(expected_trade_date: str) -> list[str]:
    expected_key = _compact_date(expected_trade_date)
    dates: dict[str, str] = {}
    for dataset in STOCK_FORMAL_EVIDENCE_DATASETS:
        dataset_dir = DATASET_ROOT / _sanitize(dataset)
        if not dataset_dir.exists():
            continue
        for date_dir in dataset_dir.iterdir():
            if not date_dir.is_dir():
                continue
            trade_date = date_dir.name
            date_key = _compact_date(trade_date)
            if not date_key:
                continue
            if expected_key and date_key > expected_key:
                continue
            dates.setdefault(date_key, trade_date)
    return [dates[key] for key in sorted(dates, reverse=True)]


def _mark_stale_stock_formal_payload(payload: dict[str, Any], requested_trade_date: str, data_trade_date: str) -> dict[str, Any]:
    payload["requested_trade_date"] = requested_trade_date
    payload["data_trade_date"] = data_trade_date
    payload["stale"] = True
    payload["freshness_status"] = "stale"
    payload["headline"] = "Tushare 只读档案使用最近可用数据"
    payload["summary"] = (
        f"当前正式交易日 {requested_trade_date} 未命中该票扩展证据，展示 {data_trade_date} 最近可用 Tushare 证据；"
        "仅用于研究复核，不改变真钱 readiness。"
    )
    for card in payload.get("source_cards") or []:
        if not isinstance(card, dict) or not card.get("available"):
            continue
        card["stale"] = True
        card["trade_date"] = data_trade_date
        reasons = [str(item) for item in (card.get("stale_reasons") or []) if item]
        if "evidence_date_before_requested_trade_date" not in reasons:
            reasons.append("evidence_date_before_requested_trade_date")
        card["stale_reasons"] = reasons
    return payload


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


def _load_rows_for_keys(dataset: str, trade_date: str, keys: tuple[str, ...]) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    rows: list[dict[str, Any]] = []
    first_manifest: dict[str, Any] | None = None
    for key in keys:
        payload, manifest = _load_dataset(dataset, trade_date, key)
        if manifest and first_manifest is None:
            first_manifest = manifest
        if isinstance(payload, list):
            rows.extend([row for row in payload if isinstance(row, dict)])
        elif isinstance(payload, dict):
            rows.append(payload)
    if rows or first_manifest:
        return rows, first_manifest

    dataset_dir = DATASET_ROOT / _sanitize(dataset) / _sanitize(trade_date)
    if not dataset_dir.exists():
        return [], None
    for path in sorted(dataset_dir.glob("*.json")):
        if path.name.endswith(".manifest.json"):
            continue
        payload = _read_json_or_none(path)
        if isinstance(payload, list):
            rows.extend([row for row in payload if isinstance(row, dict)])
        elif isinstance(payload, dict):
            rows.append(payload)
        manifest = _read_json_or_none(path.with_name(f"{path.stem}.manifest.json"))
        if isinstance(manifest, dict) and first_manifest is None:
            first_manifest = manifest
    return rows, first_manifest


def _load_code_rows_for_keys(dataset: str, trade_date: str, keys: tuple[str, ...], code: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    rows, manifest = _load_rows_for_keys(dataset, trade_date, keys)
    return _filter_code(rows, code), manifest


def _load_code_rows_for_preferred_key(
    dataset: str,
    trade_date: str,
    keys: tuple[str, ...],
    code: str,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Load only the first available shard for lightweight section APIs."""

    first_manifest: dict[str, Any] | None = None
    for key in keys:
        payload, manifest = _load_dataset(dataset, trade_date, key)
        if manifest and first_manifest is None:
            first_manifest = manifest
        if isinstance(payload, list):
            rows = _filter_code(payload, code)
            return rows, manifest
        if isinstance(payload, dict):
            rows = _filter_code([payload], code)
            return rows, manifest
    return [], first_manifest


def _latest_rows(rows: list[dict[str, Any]], limit: int = 5, fields: tuple[str, ...] = ("trade_date", "end_date", "ann_date", "report_date", "float_date")) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: _date_key(row, fields), reverse=True)[:limit]


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


def _block_trade_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    latest = _latest_rows(rows, limit=5, fields=("trade_date", "ann_date"))
    discounts: list[float | None] = []
    for row in latest:
        rate = _safe_float(row.get("discount_rate") or row.get("discount") or row.get("price_rate"))
        if rate is None:
            price = _safe_float(row.get("price") or row.get("deal_price"))
            close = _safe_float(row.get("close") or row.get("close_price"))
            if price is not None and close and close > 0:
                rate = (price / close - 1.0) * 100.0
        discounts.append(rate)
    return {
        "count": len(rows),
        "recent_count": len(latest),
        "total_amount": _safe_sum(rows, "amount", "deal_amount", "amt"),
        "average_discount_pct": _average(discounts),
        "latest": latest,
    }


def _margin_summary(detail_rows: list[dict[str, Any]], sec_rows: list[dict[str, Any]]) -> dict[str, Any]:
    latest = _latest_row(detail_rows, "trade_date") or {}
    previous = _latest_rows(detail_rows, limit=2, fields=("trade_date",))
    latest_balance = _safe_float(latest.get("rzye") or latest.get("rzrqye") or latest.get("margin_balance"))
    previous_balance = None
    if len(previous) > 1:
        previous_balance = _safe_float(previous[1].get("rzye") or previous[1].get("rzrqye") or previous[1].get("margin_balance"))
    return {
        "latest": latest,
        "recent": _latest_rows(detail_rows, limit=5, fields=("trade_date",)),
        "is_margin_target": bool(sec_rows),
        "target_status": _latest_row(sec_rows, "trade_date", "update_date") or {},
        "balance_change": round(latest_balance - previous_balance, 4) if latest_balance is not None and previous_balance is not None else None,
    }


def _business_breakdown(rows: list[dict[str, Any]]) -> dict[str, Any]:
    latest_end = max((_date_key(row, ("end_date", "ann_date")) for row in rows), default="")
    scoped = [row for row in rows if not latest_end or _date_key(row, ("end_date", "ann_date")) == latest_end]
    type_labels = {
        "P": "产品",
        "D": "地区",
        "I": "行业",
        "产品": "产品",
        "地区": "地区",
        "行业": "行业",
    }
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in scoped:
        raw_type = str(row.get("type") or row.get("bz_type") or row.get("classify") or "其他")
        label = type_labels.get(raw_type.upper(), type_labels.get(raw_type, raw_type or "其他"))
        groups.setdefault(label, []).append(row)

    def _top(rows_for_type: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            rows_for_type,
            key=lambda row: _safe_float(row.get("bz_sales") or row.get("sales") or row.get("revenue") or row.get("main_business_income")) or 0.0,
            reverse=True,
        )[:5]

    breakdown = {
        label: [
            {
                "item": _first_text(row, "bz_item", "item", "name", "business"),
                "sales": _safe_float(row.get("bz_sales") or row.get("sales") or row.get("revenue") or row.get("main_business_income")),
                "profit": _safe_float(row.get("bz_profit") or row.get("profit")),
                "cost": _safe_float(row.get("bz_cost") or row.get("cost")),
                "currency": _first_text(row, "curr_type", "currency"),
            }
            for row in _top(rows_for_type)
        ]
        for label, rows_for_type in groups.items()
    }
    top_items = [item for rows_for_type in breakdown.values() for item in rows_for_type]
    top_items = sorted(top_items, key=lambda row: row.get("sales") or 0.0, reverse=True)[:5]
    total_sales = sum((item.get("sales") or 0.0) for item in top_items)
    top_share = (top_items[0].get("sales") or 0.0) / total_sales if top_items and total_sales > 0 else None
    return {
        "end_date": latest_end or None,
        "top_items": top_items,
        "by_type": breakdown,
        "top_share": round(top_share, 4) if top_share is not None else None,
        "concentration_label": "主营集中" if top_share and top_share >= 0.6 else ("主营分散" if top_items and top_share is not None else ""),
    }


def _event_risk_summary(
    pledge_stat_rows: list[dict[str, Any]],
    pledge_detail_rows: list[dict[str, Any]],
    share_float_rows: list[dict[str, Any]],
    repurchase_rows: list[dict[str, Any]],
    audit_rows: list[dict[str, Any]],
    report_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    pledge_stat = _latest_row(pledge_stat_rows, "end_date", "ann_date") or {}
    audit = _latest_row(audit_rows, "end_date", "ann_date") or {}
    report_latest = _latest_rows(report_rows, limit=5, fields=("report_date", "ann_date"))
    audit_text = " ".join(str(audit.get(key) or "") for key in ("audit_result", "audit_opinion", "opinion", "audit_type"))
    abnormal_audit = any(word in audit_text for word in ("保留", "否定", "无法", "非标", "强调", "带强调"))
    target_prices = [_safe_float(row.get("target_price") or row.get("target_price_max") or row.get("target_price_min")) for row in report_latest]
    ratings = [_first_text(row, "rating", "rating_name", "rate", "report_title", "title") for row in report_latest]
    downgrade = any(any(word in rating for word in ("下调", "减持", "卖出", "中性")) for rating in ratings)
    return {
        "pledge": {
            "latest": pledge_stat,
            "details": _latest_rows(pledge_detail_rows, limit=5, fields=("ann_date", "end_date")),
            "pledge_ratio": _safe_float(pledge_stat.get("pledge_ratio") or pledge_stat.get("pledged_ratio") or pledge_stat.get("p_total_ratio")),
        },
        "share_float": {
            "upcoming_or_recent": _latest_rows(share_float_rows, limit=5, fields=("float_date", "ann_date")),
            "total_float_amount": _safe_sum(share_float_rows, "float_share", "float_amount", "unlock_amount"),
            "total_float_mv": _safe_sum(share_float_rows, "float_mv", "unlock_mv"),
        },
        "repurchase": {
            "recent": _latest_rows(repurchase_rows, limit=5, fields=("ann_date", "end_date")),
            "total_amount": _safe_sum(repurchase_rows, "amount", "repurchase_amount", "buyback_amount"),
        },
        "audit": {
            "latest": audit,
            "abnormal": abnormal_audit,
            "opinion": audit_text.strip(),
        },
        "research": {
            "recent": report_latest,
            "average_target_price": _average(target_prices),
            "downgrade_signal": downgrade,
        },
    }


def _technical_chips_summary(stk_rows: list[dict[str, Any]], cyq_perf_rows: list[dict[str, Any]], cyq_chip_rows: list[dict[str, Any]]) -> dict[str, Any]:
    stk = _latest_row(stk_rows, "trade_date") or {}
    perf = _latest_row(cyq_perf_rows, "trade_date") or {}
    chips = _latest_rows(cyq_chip_rows, limit=8, fields=("trade_date",))
    chip_prices = [_safe_float(row.get("price") or row.get("cost") or row.get("avg_cost")) for row in chips]
    return {
        "technical_factor": stk,
        "cyq_perf": perf,
        "cyq_chips": {
            "sample": chips,
            "price_low": min([x for x in chip_prices if x is not None], default=None),
            "price_high": max([x for x in chip_prices if x is not None], default=None),
            "winner_rate": _safe_float(perf.get("winner_rate") or perf.get("profit_ratio") or perf.get("cyq_winner_rate")),
            "cost_pressure": _safe_float(perf.get("cost_90pct") or perf.get("cost_85pct") or perf.get("avg_cost")),
        },
    }


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


def _factor_profile(code: str, trade_date: str) -> dict[str, Any]:
    try:
        from screener.tushare_factors import compute_factor_bundle
        b = compute_factor_bundle(code, trade_date)
        return {k: b.get(k) for k in (
            "tushare_score", "data_completeness", "tushare_score_breakdown",
            "factor_tags", "risk_flags", "risk_level", "risk_level_label",
            "risk_items", "degrade_reason", "block_reason", "risk_evidence_refs",
            "risk_source_cards", "explanation", "factor_snapshot", "trade_date_used")}
    except Exception:
        return {"tushare_score": None, "data_completeness": 0.0, "tushare_score_breakdown": {},
                "factor_tags": [], "risk_flags": ["数据缺失"], "risk_level": "info",
                "risk_items": [], "degrade_reason": "", "block_reason": "",
                "risk_evidence_refs": [], "risk_source_cards": [],
                "explanation": {}, "trade_date_used": None}


def build_stock_formal_data(code: str, trade_date: str | None = None) -> dict[str, Any]:
    return _build_stock_formal_data(
        code,
        trade_date,
        allow_stale_fallback=True,
        requested_trade_date=str(trade_date or ""),
    )


def _load_manifest_only(dataset: str, trade_date: str, key: str) -> dict[str, Any] | None:
    manifest_path = DATASET_ROOT / _sanitize(dataset) / _sanitize(trade_date) / f"{_sanitize(key)}.manifest.json"
    payload = _read_json_or_none(manifest_path)
    return payload if isinstance(payload, dict) else None


def _formal_summary_source_card(
    label: str,
    dataset: str,
    manifest: dict[str, Any] | None,
    detail: str = "",
    *,
    stock_scoped: bool = True,
) -> dict[str, Any]:
    card = _source_card(label, dataset, manifest, detail)
    card["stock_scoped"] = stock_scoped
    if not stock_scoped:
        card["stock_profile_use"] = "coverage_hint"
        if card.get("available") and not detail:
            card["detail"] = "数据集已就绪，展开完整档案后按个股过滤。"
    return card


def _build_stock_formal_data_summary_for_date(
    code: str,
    trade_date: str,
    *,
    requested_trade_date: str,
) -> dict[str, Any]:
    normalized_code = _normalize_code(code)
    valuation_rows, valuation_manifest = _load_dataset("valuation.daily", trade_date, normalized_code)
    liquidity_rows, liquidity_manifest = _load_dataset("liquidity.daily", trade_date, normalized_code)
    capital_rows, capital_manifest = _load_dataset("capital_flow.daily", trade_date, normalized_code)
    fundamentals, fundamentals_manifest = _load_dataset("fundamentals.snapshot", trade_date, normalized_code)
    indicators, indicator_manifest = _load_dataset("financial.indicator", trade_date, normalized_code)

    valuation = _latest_row(valuation_rows, "trade_date") or {}
    liquidity = _latest_row(liquidity_rows, "trade_date") or {}
    capital = _latest_row(capital_rows, "trade_date") or {}
    fundamental = fundamentals if isinstance(fundamentals, dict) else {}
    indicator = _latest_row(indicators, "end_date", "ann_date") or {}

    stock_source_cards = [
        _formal_summary_source_card("估值历史", "valuation.daily", valuation_manifest, "个股估值快照"),
        _formal_summary_source_card("流动性历史", "liquidity.daily", liquidity_manifest, "个股换手/量比"),
        _formal_summary_source_card("资金流历史", "capital_flow.daily", capital_manifest, "个股主力资金"),
        _formal_summary_source_card("基本面快照", "fundamentals.snapshot", fundamentals_manifest, "个股基本面快照"),
        _formal_summary_source_card("财务指标", "financial.indicator", indicator_manifest, "个股财务指标"),
    ]

    catalog_source_specs = (
        ("公司画像", "reference.stock_company"),
        ("概念归属", "reference.concept_detail"),
        ("行业/板块", "reference.industry_member"),
        ("主营构成", "financial.main_business"),
        ("事件风险", "corporate_action.pledge_stat"),
        ("龙虎榜", "market.top_list"),
        ("技术筹码", "technical.stk_factor"),
    )
    catalog_source_cards = [
        _formal_summary_source_card(
            label,
            dataset,
            _latest_manifest(_list_manifests(dataset), trade_date),
            "按需展开后过滤个股。",
            stock_scoped=False,
        )
        for label, dataset in catalog_source_specs
    ]

    source_cards = stock_source_cards + catalog_source_cards
    stock_hits = sum(1 for card in stock_source_cards if card.get("available"))
    catalog_hits = sum(1 for card in catalog_source_cards if card.get("available"))
    available = bool(stock_hits or catalog_hits)
    stale = bool(requested_trade_date and trade_date and _compact_date(trade_date) != _compact_date(requested_trade_date))

    metric_cards = [
        _metric("PE TTM", _display_number(valuation.get("pe_ttm") or fundamental.get("pe_ttm") or fundamental.get("pe")), "轻量估值快照", "info"),
        _metric("PB", _display_number(valuation.get("pb") or fundamental.get("pb")), "轻量估值快照", "info"),
        _metric("ROE", _display_number(indicator.get("roe") or fundamental.get("roe"), "%"), "轻量财务指标", "watch"),
        _metric("主力净流入", _display_number(capital.get("main_net_yi"), " 亿"), "轻量资金流", "watch"),
        _metric("换手率", _display_number(liquidity.get("turnover_rate_f") or liquidity.get("turnover_rate"), "%"), "轻量流动性", "info"),
        _metric("证据覆盖", f"{stock_hits}/{len(stock_source_cards)}", f"数据集索引 {catalog_hits}/{len(catalog_source_cards)}", "positive" if stock_hits >= 3 else "watch"),
    ]

    sections = [
        {"key": "full", "label": "完整档案", "available": available, "endpoint": f"/api/stock/{normalized_code}/formal-data/full"},
        {"key": "sources", "label": "来源索引", "available": bool(source_cards), "endpoint": f"/api/stock/{normalized_code}/formal-data/sources"},
        {"key": "risk", "label": "事件风险", "available": catalog_hits > 0, "endpoint": f"/api/stock/{normalized_code}/formal-data/risk"},
        {"key": "profile", "label": "公司画像", "available": catalog_hits > 0, "endpoint": f"/api/stock/{normalized_code}/formal-data/profile"},
    ]

    payload = {
        "available": available,
        "summary_only": True,
        "code": normalized_code,
        "trade_date": trade_date,
        "requested_trade_date": requested_trade_date,
        "data_trade_date": trade_date if available else None,
        "stale": stale,
        "freshness_status": "stale" if stale else ("current" if available else "missing"),
        "provider": "tushare/tinyshare",
        "headline": "正式数据轻量摘要已就绪" if available else "暂未命中正式数据摘要",
        "summary": (
            "先返回估值、资金、财务和来源索引；完整事件/筹码/公司画像按需展开，且只读，不提升真钱权限。"
            if available
            else "当前交易日没有命中这只股票的轻量正式数据；可以展开完整档案尝试最近可用证据。"
        ),
        "metric_cards": metric_cards,
        "source_cards": _compact_source_cards(source_cards),
        "coverage": {
            "stock_scoped_available": stock_hits,
            "stock_scoped_total": len(stock_source_cards),
            "catalog_available": catalog_hits,
            "catalog_total": len(catalog_source_cards),
        },
        "sections": sections,
    }
    return _json_clean(payload)


def build_stock_formal_data_summary(code: str, trade_date: str | None = None) -> dict[str, Any]:
    normalized_code = _normalize_code(code)
    target_date = trade_date or ""
    requested_date = target_date
    payload = _build_stock_formal_data_summary_for_date(
        normalized_code,
        target_date,
        requested_trade_date=requested_date,
    )
    if payload.get("available") or not target_date:
        return payload

    for fallback_date in _stock_formal_candidate_dates(target_date):
        if _compact_date(fallback_date) == _compact_date(target_date):
            continue
        fallback = _build_stock_formal_data_summary_for_date(
            normalized_code,
            fallback_date,
            requested_trade_date=target_date,
        )
        if fallback.get("available"):
            fallback["stale"] = True
            fallback["freshness_status"] = "stale"
            fallback["headline"] = "正式数据轻量摘要使用最近可用证据"
            fallback["summary"] = (
                f"当前正式交易日 {target_date} 未命中轻量摘要，展示 {fallback_date} 最近可用证据；"
                "仅作只读复核，不改变真钱 readiness。"
            )
            return _json_clean(fallback)
    return payload


def _stock_formal_section_payload_with_fallback(
    builder: Any,
    code: str,
    trade_date: str | None,
) -> dict[str, Any]:
    normalized_code = _normalize_code(code)
    target_date = trade_date or ""
    payload = builder(normalized_code, target_date, requested_trade_date=target_date)
    if payload.get("available") or not target_date:
        return _json_clean(payload)

    for fallback_date in _stock_formal_candidate_dates(target_date):
        if _compact_date(fallback_date) == _compact_date(target_date):
            continue
        fallback = builder(normalized_code, fallback_date, requested_trade_date=target_date)
        if fallback.get("available"):
            fallback = _mark_stale_stock_formal_payload(fallback, target_date, str(fallback.get("trade_date") or fallback_date))
            return _json_clean(fallback)
    return _json_clean(payload)


def _stock_formal_source_index_cards(normalized_code: str, trade_date: str) -> list[dict[str, Any]]:
    stock_scoped_specs = (
        ("涨跌停价", "price_limit.daily", "formal-price-limit"),
        ("执行标记", "execution.flags", "formal-execution-flags"),
        ("估值历史", "valuation.daily", normalized_code),
        ("流动性历史", "liquidity.daily", normalized_code),
        ("资金流历史", "capital_flow.daily", normalized_code),
        ("基本面快照", "fundamentals.snapshot", normalized_code),
        ("财务指标", "financial.indicator", normalized_code),
        ("财务报表", "financial.statement", normalized_code),
        ("分红送配", "corporate_action.dividend", normalized_code),
        ("股东结构", "shareholder.top10", normalized_code),
    )
    cards = [
        _formal_summary_source_card(label, dataset, _load_manifest_only(dataset, trade_date, key), stock_scoped=True)
        for label, dataset, key in stock_scoped_specs
    ]
    catalog_specs = (
        ("全市场日指标", "market.daily_basic_snapshot"),
        ("龙虎榜", "market.top_list"),
        ("机构席位", "market.top_inst"),
        ("公司画像", "reference.stock_company"),
        ("名称变更", "reference.namechange"),
        ("概念归属", "reference.concept_detail"),
        ("行业/板块", "reference.industry_member"),
        ("主营构成", "financial.main_business"),
        ("大宗交易", "market.block_trade"),
        ("两融明细", "market.margin_detail"),
        ("股权质押", "corporate_action.pledge_stat"),
        ("限售解禁", "corporate_action.share_float"),
        ("股份回购", "corporate_action.repurchase"),
        ("审计意见", "financial.audit"),
        ("研报评级", "research.report_rc"),
        ("技术筹码", "technical.stk_factor"),
        ("指数权重", "index.weight"),
    )
    cards.extend(
        _formal_summary_source_card(
            label,
            dataset,
            _latest_manifest(_list_manifests(dataset), trade_date),
            "按需展开后过滤个股。",
            stock_scoped=False,
        )
        for label, dataset in catalog_specs
    )
    return cards


def _build_stock_formal_sources_for_date(
    code: str,
    trade_date: str,
    *,
    requested_trade_date: str,
) -> dict[str, Any]:
    normalized_code = _normalize_code(code)
    source_cards = _stock_formal_source_index_cards(normalized_code, trade_date)
    available = any(card.get("available") for card in source_cards)
    stale = bool(requested_trade_date and trade_date and _compact_date(trade_date) != _compact_date(requested_trade_date))
    return {
        "available": available,
        "section": "sources",
        "code": normalized_code,
        "trade_date": trade_date,
        "requested_trade_date": requested_trade_date,
        "data_trade_date": trade_date if available else None,
        "stale": stale,
        "freshness_status": "stale" if stale else ("current" if available else "missing"),
        "provider": "tushare/tinyshare",
        "headline": "正式数据来源索引已就绪" if available else "暂未命中正式数据来源索引",
        "summary": "这里只展示来源覆盖和权限语义，不构建完整个股档案。",
        "source_cards": source_cards,
    }


def build_stock_formal_data_sources(code: str, trade_date: str | None = None) -> dict[str, Any]:
    return _stock_formal_section_payload_with_fallback(_build_stock_formal_sources_for_date, code, trade_date)


def _build_stock_formal_profile_for_date(
    code: str,
    trade_date: str,
    *,
    requested_trade_date: str,
) -> dict[str, Any]:
    normalized_code = _normalize_code(code)
    company_rows, company_manifest = _load_code_rows_for_keys("reference.stock_company", trade_date, ("all",), normalized_code)
    namechange_rows, namechange_manifest = _load_code_rows_for_keys("reference.namechange", trade_date, ("all",), normalized_code)
    concept_rows, concept_manifest = _load_code_rows_for_keys("reference.concept_detail", trade_date, ("hs300-zz500", "all"), normalized_code)
    industry_rows, industry_manifest = _load_code_rows_for_keys(
        "reference.industry_member",
        trade_date,
        ("SW2021-hs300-zz500", "hs300-zz500", "all"),
        normalized_code,
    )
    ths_rows, ths_manifest = _load_code_rows_for_keys("reference.ths_member", trade_date, ("hs300-zz500", "all"), normalized_code)
    dc_rows, dc_manifest = _load_code_rows_for_keys("reference.dc_member", trade_date, ("hs300-zz500", "all"), normalized_code)
    business_rows, business_manifest = _load_code_rows_for_keys(
        "financial.main_business",
        trade_date,
        ("hs300-zz500-recent", "recent", "all"),
        normalized_code,
    )
    company = company_rows[0] if company_rows else {}
    profile = {
        "name": _first_text(company, "name", "stock_name", "short_name"),
        "full_name": _first_text(company, "fullname", "full_name", "company_name"),
        "chairman": _first_text(company, "chairman"),
        "manager": _first_text(company, "manager", "general_manager"),
        "secretary": _first_text(company, "secretary", "secretary_name"),
        "province": _first_text(company, "province"),
        "city": _first_text(company, "city"),
        "area": _first_text(company, "area"),
        "industry": _first_text(company, "industry"),
        "main_business": _first_text(company, "main_business", "main_biz", "business"),
        "business_scope": _first_text(company, "business_scope", "scope"),
        "list_date": _first_text(company, "list_date"),
        "setup_date": _first_text(company, "setup_date", "established_date"),
        "exchange": _first_text(company, "exchange"),
        "market": _first_text(company, "market"),
        "employees": company.get("employees") or company.get("staff_num"),
        "reg_capital": company.get("reg_capital") or company.get("reg_capital_m"),
        "name_changes": _latest_rows(namechange_rows, limit=5, fields=("end_date", "start_date", "ann_date")),
    }
    themes = {
        "concepts": [item for item in dict.fromkeys(_first_text(row, "concept_name", "name", "concept", "index_name") for row in concept_rows) if item][:12],
        "industries": [item for item in dict.fromkeys(_first_text(row, "industry_name", "index_name", "name", "level_name") for row in industry_rows) if item][:8],
        "ths": [item for item in dict.fromkeys(_first_text(row, "ths_name", "index_name", "name") for row in ths_rows) if item][:8],
        "dc": [item for item in dict.fromkeys(_first_text(row, "dc_name", "index_name", "name") for row in dc_rows) if item][:8],
        "raw": {
            "concept_detail": concept_rows[:20],
            "industry_member": industry_rows[:20],
            "ths_member": ths_rows[:20],
            "dc_member": dc_rows[:20],
        },
    }
    industry_source_dataset, industry_source_manifest = _source_choice(
        ("reference.industry_member", industry_manifest),
        ("reference.ths_member", ths_manifest),
        ("reference.dc_member", dc_manifest),
    )
    source_cards = [
        _source_card("公司画像", "reference.stock_company", company_manifest, f"{len(company_rows)} 条公司资料"),
        _source_card("名称变更", "reference.namechange", namechange_manifest, f"{len(namechange_rows)} 条历史名称"),
        _source_card("概念归属", "reference.concept_detail", concept_manifest, f"{len(concept_rows)} 个概念命中"),
        _source_card("行业/板块", industry_source_dataset, industry_source_manifest, f"行业 {len(industry_rows)} / THS {len(ths_rows)} / DC {len(dc_rows)}"),
        _source_card("主营构成", "financial.main_business", business_manifest, f"{len(business_rows)} 条构成记录"),
    ]
    available = any(card.get("available") for card in source_cards)
    stale = bool(requested_trade_date and trade_date and _compact_date(trade_date) != _compact_date(requested_trade_date))
    return _json_clean({
        "available": available,
        "section": "profile",
        "code": normalized_code,
        "trade_date": trade_date,
        "requested_trade_date": requested_trade_date,
        "data_trade_date": trade_date if available else None,
        "stale": stale,
        "freshness_status": "stale" if stale else ("current" if available else "missing"),
        "provider": "tushare/tinyshare",
        "headline": "公司画像已按需加载" if available else "暂未命中公司画像数据",
        "summary": "公司资料、主题行业和主营构成单独加载，不触发完整档案构建。",
        "profile": _compact_profile_for_section(profile),
        "themes": {
            "concepts": themes["concepts"],
            "industries": themes["industries"],
            "ths": themes["ths"],
            "dc": themes["dc"],
        },
        "business_breakdown": _compact_business_breakdown_for_section(_business_breakdown(business_rows)),
        "source_cards": _compact_source_cards(source_cards),
    })


def build_stock_formal_data_profile(code: str, trade_date: str | None = None) -> dict[str, Any]:
    return _stock_formal_section_payload_with_fallback(_build_stock_formal_profile_for_date, code, trade_date)


def _build_stock_formal_risk_for_date(
    code: str,
    trade_date: str,
    *,
    requested_trade_date: str,
) -> dict[str, Any]:
    normalized_code = _normalize_code(code)
    block_trade_rows, block_trade_manifest = _load_code_rows_for_preferred_key("market.block_trade", trade_date, ("recent", "all"), normalized_code)
    pledge_stat_rows, pledge_stat_manifest = _load_code_rows_for_preferred_key("corporate_action.pledge_stat", trade_date, ("recent", "all"), normalized_code)
    pledge_detail_rows, pledge_detail_manifest = _load_code_rows_for_preferred_key("corporate_action.pledge_detail", trade_date, ("recent", "all"), normalized_code)
    share_float_rows, share_float_manifest = _load_code_rows_for_preferred_key("corporate_action.share_float", trade_date, ("recent", "all"), normalized_code)
    repurchase_rows, repurchase_manifest = _load_code_rows_for_preferred_key("corporate_action.repurchase", trade_date, ("recent", "all"), normalized_code)
    audit_rows, audit_manifest = _load_code_rows_for_preferred_key("financial.audit", trade_date, ("hs300-zz500", "recent", "all"), normalized_code)
    report_manifest = _load_manifest_only("research.report_rc", trade_date, "recent") or _load_manifest_only("research.report_rc", trade_date, "all")
    top_list_manifest = _load_manifest_only("market.top_list", trade_date, "recent")
    top_inst_manifest = _load_manifest_only("market.top_inst", trade_date, "recent")
    margin_detail_manifest = _load_manifest_only("market.margin_detail", trade_date, "recent") or _load_manifest_only("market.margin_detail", trade_date, "all")
    margin_sec_manifest = _load_manifest_only("market.margin_secs", trade_date, "recent") or _load_manifest_only("market.margin_secs", trade_date, "all")
    stk_factor_manifest = _load_manifest_only("technical.stk_factor", trade_date, "hs300-zz500-recent") or _load_manifest_only("technical.stk_factor", trade_date, "recent")
    cyq_perf_manifest = _load_manifest_only("technical.cyq_perf", trade_date, "hs300-zz500-recent") or _load_manifest_only("technical.cyq_perf", trade_date, "recent")
    cyq_chips_manifest = _load_manifest_only("technical.cyq_chips", trade_date, "hs300-zz500-recent") or _load_manifest_only("technical.cyq_chips", trade_date, "recent")
    margin_source_dataset, margin_source_manifest = _source_choice(
        ("market.margin_detail", margin_detail_manifest),
        ("market.margin_secs", margin_sec_manifest),
    )
    pledge_source_dataset, pledge_source_manifest = _source_choice(
        ("corporate_action.pledge_stat", pledge_stat_manifest),
        ("corporate_action.pledge_detail", pledge_detail_manifest),
    )
    technical_source_dataset, technical_source_manifest = _source_choice(
        ("technical.stk_factor", stk_factor_manifest),
        ("technical.cyq_perf", cyq_perf_manifest),
        ("technical.cyq_chips", cyq_chips_manifest),
    )
    market_activity = {
        "block_trade": _block_trade_summary(block_trade_rows),
        "margin_deferred": bool(margin_source_manifest),
        "top_list_deferred": bool(top_list_manifest),
        "top_inst_deferred": bool(top_inst_manifest),
        "deferred_endpoint": f"/api/stock/{normalized_code}/formal-data/full",
    }
    event_risks = _event_risk_summary(
        pledge_stat_rows,
        pledge_detail_rows,
        share_float_rows,
        repurchase_rows,
        audit_rows,
        [],
    )
    event_risks["research_deferred"] = bool(report_manifest)
    event_risks["research_endpoint"] = f"/api/stock/{normalized_code}/formal-data/full" if report_manifest else ""
    source_cards = [
        _source_card("龙虎榜", "market.top_list", top_list_manifest, "完整档案按需过滤个股记录"),
        _source_card("机构席位", "market.top_inst", top_inst_manifest, "完整档案按需过滤个股记录"),
        _source_card("大宗交易", "market.block_trade", block_trade_manifest, f"{len(block_trade_rows)} 条近窗口记录"),
        _source_card("两融明细", margin_source_dataset, margin_source_manifest, "完整档案按需过滤个股记录"),
        _source_card("股权质押", pledge_source_dataset, pledge_source_manifest, f"统计 {len(pledge_stat_rows)} / 明细 {len(pledge_detail_rows)}"),
        _source_card("限售解禁", "corporate_action.share_float", share_float_manifest, f"{len(share_float_rows)} 条解禁记录"),
        _source_card("股份回购", "corporate_action.repurchase", repurchase_manifest, f"{len(repurchase_rows)} 条回购记录"),
        _source_card("审计意见", "financial.audit", audit_manifest, f"{len(audit_rows)} 条审计记录"),
        _source_card("研报评级", "research.report_rc", report_manifest, "完整档案按需过滤研报记录"),
        _source_card("技术筹码", technical_source_dataset, technical_source_manifest, "完整档案按需过滤技术/筹码记录"),
    ]
    available = any(card.get("available") for card in source_cards)
    stale = bool(requested_trade_date and trade_date and _compact_date(trade_date) != _compact_date(requested_trade_date))
    return _json_clean({
        "available": available,
        "section": "risk",
        "code": normalized_code,
        "trade_date": trade_date,
        "requested_trade_date": requested_trade_date,
        "data_trade_date": trade_date if available else None,
        "stale": stale,
        "freshness_status": "stale" if stale else ("current" if available else "missing"),
        "provider": "tushare/tinyshare",
        "headline": "事件风险已按需加载" if available else "暂未命中事件风险数据",
        "summary": "事件、两融、技术筹码和因子风险单独加载，不触发完整档案构建。",
        "event_risks": _compact_event_risks_for_section(event_risks),
        "market_activity": {
            "block_trade": _compact_fields(
                market_activity["block_trade"],
                ("count", "recent_count", "total_amount", "average_discount_pct"),
            ),
            "margin_deferred": market_activity["margin_deferred"],
            "top_list_deferred": market_activity["top_list_deferred"],
            "top_inst_deferred": market_activity["top_inst_deferred"],
            "deferred_endpoint": market_activity["deferred_endpoint"],
        },
        "technical_chips": {
            "technical_deferred": bool(technical_source_manifest),
            "chips_deferred": bool(cyq_chips_manifest),
            "chips_endpoint": f"/api/stock/{normalized_code}/formal-data/full",
        },
        "factor_profile_deferred": True,
        "factor_profile_endpoint": f"/api/stock/{normalized_code}/formal-data/full",
        "source_cards": _compact_source_cards(source_cards),
    })


def build_stock_formal_data_risk(code: str, trade_date: str | None = None) -> dict[str, Any]:
    return _stock_formal_section_payload_with_fallback(_build_stock_formal_risk_for_date, code, trade_date)


def _build_stock_formal_data(
    code: str,
    trade_date: str | None = None,
    *,
    allow_stale_fallback: bool = False,
    requested_trade_date: str = "",
) -> dict[str, Any]:
    normalized_code = _normalize_code(code)
    target_date = trade_date or ""
    requested_date = requested_trade_date or target_date
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
    company_rows, company_manifest = _load_code_rows_for_keys("reference.stock_company", target_date, ("all",), normalized_code)
    namechange_rows, namechange_manifest = _load_code_rows_for_keys("reference.namechange", target_date, ("all",), normalized_code)
    concept_rows, concept_manifest = _load_code_rows_for_keys("reference.concept_detail", target_date, ("hs300-zz500", "all"), normalized_code)
    industry_rows, industry_manifest = _load_code_rows_for_keys("reference.industry_member", target_date, ("SW2021-hs300-zz500", "hs300-zz500", "all"), normalized_code)
    ths_rows, ths_manifest = _load_code_rows_for_keys("reference.ths_member", target_date, ("hs300-zz500", "all"), normalized_code)
    dc_rows, dc_manifest = _load_code_rows_for_keys("reference.dc_member", target_date, ("hs300-zz500", "all"), normalized_code)
    business_rows, business_manifest = _load_code_rows_for_keys("financial.main_business", target_date, ("hs300-zz500-recent", "recent", "all"), normalized_code)
    margin_detail_rows, margin_detail_manifest = _load_code_rows_for_keys("market.margin_detail", target_date, ("recent", "all"), normalized_code)
    margin_sec_rows, margin_sec_manifest = _load_code_rows_for_keys("market.margin_secs", target_date, ("recent", "all"), normalized_code)
    block_trade_rows, block_trade_manifest = _load_code_rows_for_keys("market.block_trade", target_date, ("recent", "all"), normalized_code)
    pledge_stat_rows, pledge_stat_manifest = _load_code_rows_for_keys("corporate_action.pledge_stat", target_date, ("all", "recent"), normalized_code)
    pledge_detail_rows, pledge_detail_manifest = _load_code_rows_for_keys("corporate_action.pledge_detail", target_date, ("all", "recent"), normalized_code)
    share_float_rows, share_float_manifest = _load_code_rows_for_keys("corporate_action.share_float", target_date, ("all", "recent"), normalized_code)
    repurchase_rows, repurchase_manifest = _load_code_rows_for_keys("corporate_action.repurchase", target_date, ("all", "recent"), normalized_code)
    audit_rows, audit_manifest = _load_code_rows_for_keys("financial.audit", target_date, ("hs300-zz500", "all", "recent"), normalized_code)
    report_rows, report_manifest = _load_code_rows_for_keys("research.report_rc", target_date, ("recent", "all"), normalized_code)
    stk_factor_rows, stk_factor_manifest = _load_code_rows_for_keys("technical.stk_factor", target_date, ("hs300-zz500-recent", "recent", "all"), normalized_code)
    cyq_perf_rows, cyq_perf_manifest = _load_code_rows_for_keys("technical.cyq_perf", target_date, ("hs300-zz500-recent", "recent", "all"), normalized_code)
    cyq_chips_rows, cyq_chips_manifest = _load_code_rows_for_keys("technical.cyq_chips", target_date, ("hs300-zz500-recent", "recent", "all"), normalized_code)
    price_limit_rows, price_limit_manifest = _load_code_rows_for_keys("price_limit.daily", target_date, ("formal-price-limit", "universe-hs300-zz500-price-limit", "recent", "all"), normalized_code)
    execution_flag_rows, execution_flag_manifest = _load_code_rows_for_keys("execution.flags", target_date, ("formal-execution-flags", "universe-hs300-zz500-execution-flags", "recent", "all"), normalized_code)

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
    company = company_rows[0] if company_rows else {}
    profile = {
        "name": _first_text(company, "name", "stock_name", "short_name"),
        "full_name": _first_text(company, "fullname", "full_name", "company_name"),
        "chairman": _first_text(company, "chairman"),
        "manager": _first_text(company, "manager", "general_manager"),
        "secretary": _first_text(company, "secretary", "secretary_name"),
        "province": _first_text(company, "province"),
        "city": _first_text(company, "city"),
        "area": _first_text(company, "area"),
        "industry": _first_text(company, "industry"),
        "main_business": _first_text(company, "main_business", "main_biz", "business"),
        "business_scope": _first_text(company, "business_scope", "scope"),
        "list_date": _first_text(company, "list_date"),
        "setup_date": _first_text(company, "setup_date", "established_date"),
        "exchange": _first_text(company, "exchange"),
        "market": _first_text(company, "market"),
        "employees": company.get("employees") or company.get("staff_num"),
        "reg_capital": company.get("reg_capital") or company.get("reg_capital_m"),
        "name_changes": _latest_rows(namechange_rows, limit=5, fields=("end_date", "start_date", "ann_date")),
    }
    concept_tags = [
        _first_text(row, "concept_name", "name", "concept", "index_name")
        for row in concept_rows
    ]
    industry_tags = [
        _first_text(row, "industry_name", "index_name", "name", "level_name")
        for row in industry_rows
    ]
    ths_tags = [
        _first_text(row, "ths_name", "index_name", "name")
        for row in ths_rows
    ]
    dc_tags = [
        _first_text(row, "dc_name", "index_name", "name")
        for row in dc_rows
    ]
    themes = {
        "concepts": [item for item in dict.fromkeys(concept_tags) if item][:12],
        "industries": [item for item in dict.fromkeys(industry_tags) if item][:8],
        "ths": [item for item in dict.fromkeys(ths_tags) if item][:8],
        "dc": [item for item in dict.fromkeys(dc_tags) if item][:8],
        "raw": {
            "concept_detail": concept_rows[:20],
            "industry_member": industry_rows[:20],
            "ths_member": ths_rows[:20],
            "dc_member": dc_rows[:20],
        },
    }
    business_breakdown = _business_breakdown(business_rows)
    event_risks = _event_risk_summary(
        pledge_stat_rows,
        pledge_detail_rows,
        share_float_rows,
        repurchase_rows,
        audit_rows,
        report_rows,
    )
    market_activity = {
        "block_trade": _block_trade_summary(block_trade_rows),
        "margin": _margin_summary(margin_detail_rows, margin_sec_rows),
        "top_list": top_list_rows[:8],
        "top_inst": top_inst_rows[:8],
    }
    technical_chips = _technical_chips_summary(stk_factor_rows, cyq_perf_rows, cyq_chips_rows)
    industry_source_dataset, industry_source_manifest = _source_choice(
        ("reference.industry_member", industry_manifest),
        ("reference.ths_member", ths_manifest),
        ("reference.dc_member", dc_manifest),
    )
    margin_source_dataset, margin_source_manifest = _source_choice(
        ("market.margin_detail", margin_detail_manifest),
        ("market.margin_secs", margin_sec_manifest),
    )
    pledge_source_dataset, pledge_source_manifest = _source_choice(
        ("corporate_action.pledge_stat", pledge_stat_manifest),
        ("corporate_action.pledge_detail", pledge_detail_manifest),
    )
    technical_source_dataset, technical_source_manifest = _source_choice(
        ("technical.stk_factor", stk_factor_manifest),
        ("technical.cyq_perf", cyq_perf_manifest),
        ("technical.cyq_chips", cyq_chips_manifest),
    )
    metric_cards = [
        _metric("PE TTM", _display_number(valuation.get("pe_ttm") or fundamental.get("pe_ttm") or fundamental.get("pe")), "Tushare daily_basic", "info"),
        _metric("PB", _display_number(valuation.get("pb") or fundamental.get("pb")), "Tushare daily_basic", "info"),
        _metric("ROE", _display_number(indicator.get("roe") or fundamental.get("roe"), "%"), "最新财务指标", "watch"),
        _metric("总市值", _display_number(valuation.get("total_mv_yi") or fundamental.get("total_mv_yi"), " 亿"), "估值快照", "info"),
        _metric("主力净流入", _display_number(capital.get("main_net_yi"), " 亿"), "moneyflow", "watch"),
        _metric("换手率", _display_number(liquidity.get("turnover_rate_f") or liquidity.get("turnover_rate"), "%"), "流动性", "info"),
        _metric("指数权重", _display_number(index_weight_total, "%"), "沪深300/中证500/中证1000", "positive" if index_weight_total else "info"),
        _metric("龙虎榜", str(len(top_list_rows)), "近窗口命中次数", "watch" if top_list_rows else "info"),
        _metric("大宗折溢价", _display_number((market_activity["block_trade"] or {}).get("average_discount_pct"), "%"), "近窗口大宗交易", "risk" if ((market_activity["block_trade"] or {}).get("average_discount_pct") or 0) < -5 else "info"),
        _metric("融资余额变化", _display_number((market_activity["margin"] or {}).get("balance_change")), "个股两融明细", "watch"),
        _metric("质押比例", _display_number(((event_risks.get("pledge") or {}).get("pledge_ratio")), "%"), "质押统计", "risk" if (((event_risks.get("pledge") or {}).get("pledge_ratio")) or 0) >= 30 else "info"),
        _metric("研报目标均值", _display_number(((event_risks.get("research") or {}).get("average_target_price"))), "report_rc", "info"),
    ]
    source_cards = [
        _source_card("涨跌停价", "price_limit.daily", price_limit_manifest, f"{len(price_limit_rows)} 条执行价约束"),
        _source_card("执行标记", "execution.flags", execution_flag_manifest, f"{len(execution_flag_rows)} 条停牌/ST/涨跌停标记"),
        _source_card("估值历史", "valuation.daily", valuation_manifest),
        _source_card("资金流历史", "capital_flow.daily", capital_manifest),
        _source_card("基本面快照", "fundamentals.snapshot", fundamentals_manifest),
        _source_card("财务指标", "financial.indicator", indicator_manifest),
        _source_card("股东结构", "shareholder.top10", shareholder_manifest),
        _source_card("分红送配", "corporate_action.dividend", dividend_manifest),
        _source_card("全市场日指标", "market.daily_basic_snapshot", daily_basic_manifest),
        _source_card("龙虎榜", "market.top_list", top_list_manifest),
        _source_card("机构席位", "market.top_inst", top_inst_manifest),
        _source_card("公司画像", "reference.stock_company", company_manifest, f"{len(company_rows)} 条公司资料"),
        _source_card("名称变更", "reference.namechange", namechange_manifest, f"{len(namechange_rows)} 条历史名称"),
        _source_card("概念归属", "reference.concept_detail", concept_manifest, f"{len(concept_rows)} 个概念命中"),
        _source_card("行业/板块", industry_source_dataset, industry_source_manifest, f"行业 {len(industry_rows)} / THS {len(ths_rows)} / DC {len(dc_rows)}"),
        _source_card("主营构成", "financial.main_business", business_manifest, f"{len(business_rows)} 条构成记录"),
        _source_card("大宗交易", "market.block_trade", block_trade_manifest, f"{len(block_trade_rows)} 条近窗口记录"),
        _source_card("两融明细", margin_source_dataset, margin_source_manifest, f"明细 {len(margin_detail_rows)} / 标的 {len(margin_sec_rows)}"),
        _source_card("股权质押", pledge_source_dataset, pledge_source_manifest, f"统计 {len(pledge_stat_rows)} / 明细 {len(pledge_detail_rows)}"),
        _source_card("限售解禁", "corporate_action.share_float", share_float_manifest, f"{len(share_float_rows)} 条解禁记录"),
        _source_card("股份回购", "corporate_action.repurchase", repurchase_manifest, f"{len(repurchase_rows)} 条回购记录"),
        _source_card("审计意见", "financial.audit", audit_manifest, f"{len(audit_rows)} 条审计记录"),
        _source_card("研报评级", "research.report_rc", report_manifest, f"{len(report_rows)} 条研报记录"),
        _source_card("技术筹码", technical_source_dataset, technical_source_manifest, f"技术 {len(stk_factor_rows)} / 筹码 {len(cyq_perf_rows) + len(cyq_chips_rows)}"),
    ]
    if index_manifests:
        source_cards.append(_source_card("指数权重", "index.weight", index_manifests[0], f"{len(index_memberships)} 个指数命中"))

    available = any(card.get("available") for card in source_cards)
    if not available and allow_stale_fallback and target_date:
        for fallback_date in _stock_formal_candidate_dates(target_date):
            if _compact_date(fallback_date) == _compact_date(target_date):
                continue
            fallback_payload = _build_stock_formal_data(
                normalized_code,
                fallback_date,
                allow_stale_fallback=False,
                requested_trade_date=target_date,
            )
            if fallback_payload.get("available"):
                return _json_clean(_mark_stale_stock_formal_payload(fallback_payload, target_date, str(fallback_payload.get("trade_date") or fallback_date)))

    payload = {
        "available": available,
        "code": normalized_code,
        "trade_date": target_date,
        "requested_trade_date": requested_date,
        "data_trade_date": target_date if available else None,
        "stale": False,
        "freshness_status": "current" if available else "missing",
        "provider": "tushare/tinyshare",
        "headline": "Tushare 数据已接入个股档案" if available else "当前个股未命中已灌入的 Tushare 数据",
        "summary": (
            "估值、资金流、财务、股东、分红、指数权重和龙虎榜以只读研究证据展示，不自动放大真钱权限。"
            if available
            else "这只股票可能不在已灌入的沪深300/中证500/中证1000窗口内，或专题补采尚未完成。"
        ),
        "metric_cards": metric_cards,
        "profile": profile,
        "themes": themes,
        "business_breakdown": business_breakdown,
        "event_risks": event_risks,
        "market_activity": market_activity,
        "technical_chips": technical_chips,
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
        "factor_profile": _factor_profile(normalized_code, target_date),
        "source_cards": source_cards,
    }
    return _json_clean(payload)
