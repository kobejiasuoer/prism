#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
PACKAGES_ROOT = REPO_ROOT / "packages"
STOCK_ANALYZER_ROOT = REPO_ROOT / "stock-analyzer"
for path in (SCRIPT_DIR, PACKAGES_ROOT, STOCK_ANALYZER_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from prism_canonical import load_confirmation, load_screening_batch, load_watchlist_snapshot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Prism command brief artifacts")
    parser.add_argument("--date", required=True, help="Trade date, YYYY-MM-DD")
    parser.add_argument("--brief-output", required=True)
    parser.add_argument("--report-output", required=True)
    parser.add_argument("--json-output", required=True)
    return parser.parse_args()


def safe_load(loader: Callable[..., dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
    try:
        return loader(**kwargs)
    except Exception:
        return {}


def pick_top_theme(screening: dict[str, Any]) -> str:
    theme_block = screening.get("market_themes") or {}
    themes = theme_block.get("themes") or []
    if isinstance(themes, list) and themes:
        return str(themes[0].get("theme") or "暂无主线")
    return str(theme_block.get("top_theme") or "暂无主线")


def item_reason(item: dict[str, Any]) -> str:
    flags = item.get("hard_flags") or item.get("risk_flags") or []
    if flags:
        return str(flags[0])
    watch_points = item.get("watch_points") or []
    if watch_points:
        return str(watch_points[0])
    return str(item.get("main_risk") or item.get("entry_reason") or "按当前规则跟踪")


def item_trigger(item: dict[str, Any]) -> str:
    action = str(item.get("action") or "").strip()
    stop_loss = item.get("stop_loss")
    resistance = item.get("resistance")
    watch_condition = item.get("watch_condition")
    if "减" in action and stop_loss not in (None, ""):
        return f"跌破 {stop_loss} 先减"
    if resistance not in (None, ""):
        return f"站上 {resistance} 再增强"
    if watch_condition:
        return str(watch_condition)
    return "等待下一次确认"


def normalize_watchlist_section(watchlist: dict[str, Any]) -> dict[str, Any]:
    stocks = list(watchlist.get("stocks") or [])
    priority_codes = set(watchlist.get("priority_codes") or [])
    follow_codes = set(watchlist.get("follow_codes") or [])
    observe_codes = set(watchlist.get("observe_codes") or [])

    priority = [item for item in stocks if item.get("code") in priority_codes]
    follow = [item for item in stocks if item.get("code") in follow_codes]
    observe = [item for item in stocks if item.get("code") in observe_codes]
    return {
        "snapshot_path": watchlist.get("snapshot_path"),
        "generated_at": watchlist.get("generated_at"),
        "price_basis": watchlist.get("price_basis"),
        "flow_basis": watchlist.get("flow_basis"),
        "tech_basis": watchlist.get("tech_basis"),
        "records": stocks,
        "priority": priority,
        "follow": follow,
        "observe": observe,
        "summary": f"{len(priority)} 只需要优先处理。" if priority else "当前没有必须优先处理的持仓。",
    }


def normalize_screener_section(screening: dict[str, Any]) -> dict[str, Any]:
    candidates = list(screening.get("candidates") or [])
    approved = [item for item in candidates if item.get("screening_status") == "approved"]
    caution = [item for item in candidates if item.get("screening_status") == "caution"]
    return {
        "path": screening.get("path"),
        "timestamp": screening.get("generated_at"),
        "source_scan_timestamp": screening.get("source_scan_timestamp"),
        "market_regime": screening.get("market_regime") or {},
        "market_themes": screening.get("market_themes") or {},
        "screening_summary": screening.get("screening_summary") or {},
        "top_theme": pick_top_theme(screening),
        "shortlist": candidates,
        "approved": approved,
        "caution": caution,
    }


def normalize_midday_section(confirmation: dict[str, Any]) -> dict[str, Any]:
    if not confirmation:
        return {
            "path": "",
            "timestamp": "",
            "validation_status": "missing",
            "confirmed": [],
            "downgraded": [],
            "fresh_candidates": [],
        }
    return {
        "path": confirmation.get("path"),
        "timestamp": confirmation.get("generated_at"),
        "validation_status": confirmation.get("validation_status"),
        "confirmed": confirmation.get("confirmed") or [],
        "downgraded": confirmation.get("downgraded") or [],
        "fresh_candidates": confirmation.get("fresh_candidates") or [],
    }


def build_payload(trade_date: str) -> dict[str, Any]:
    watchlist = safe_load(load_watchlist_snapshot, trade_date=trade_date)
    if not watchlist:
        watchlist = safe_load(load_watchlist_snapshot)
    screening = safe_load(load_screening_batch)
    confirmation = safe_load(load_confirmation)

    watchlist_section = normalize_watchlist_section(watchlist)
    screener_section = normalize_screener_section(screening)
    midday_section = normalize_midday_section(confirmation)
    gate = screener_section.get("market_regime", {}).get("execution_gate") or {}
    gate_status = gate.get("status") or "unknown"
    allow_new = bool(gate.get("allow_new_positions")) and bool(screener_section.get("approved"))
    opportunity_focus = [
        str(item.get("name") or item.get("code"))
        for item in (screener_section.get("approved") or screener_section.get("caution") or [])[:5]
    ]
    holding_focus = [str(item.get("name") or item.get("code")) for item in watchlist_section.get("priority", [])[:5]]
    risk_flags = list(gate.get("risk_flags") or [])
    avoid_points = risk_flags[:3] or ["先确认阀门和仓位，再处理新机会。"]

    summary = {
        "trade_date": trade_date,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "open_new_positions": "是，按阀门小仓试错。" if allow_new else "否，今天进攻阀门未放行。",
        "position_cap": gate.get("position_cap") or "0成",
        "main_theme": screener_section.get("top_theme") or "暂无主线",
        "holding_focus": holding_focus,
        "opportunity_focus": opportunity_focus if allow_new else [],
        "avoid_points": avoid_points,
        "gate_label": gate.get("label") or ("进攻阀门关闭" if gate_status == "off" else "进攻阀门待确认"),
        "gate_summary": gate.get("summary") or "按当前市场环境控制仓位和节奏。",
        "watchlist_summary": watchlist_section.get("summary"),
        "midday_summary": summarize_midday(midday_section),
    }
    return {
        "summary": summary,
        "watchlist": watchlist_section,
        "screener": screener_section,
        "midday": midday_section,
    }


def summarize_midday(midday: dict[str, Any]) -> str:
    if midday.get("validation_status") != "ok":
        return "暂无同日午盘确认。"
    confirmed = len(midday.get("confirmed") or [])
    downgraded = len(midday.get("downgraded") or [])
    fresh = len(midday.get("fresh_candidates") or [])
    return f"午盘确认 {confirmed} 只，降级 {downgraded} 只，新观察 {fresh} 只。"


def render_brief(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    watchlist = payload["watchlist"]
    lines = [
        f"Prism 总控简报 | {summary['generated_at'][5:16]}",
        f"开新仓：{summary['open_new_positions']}",
        f"总仓位上限：{summary['position_cap']}",
        f"持仓先处理：{', '.join(summary['holding_focus']) if summary['holding_focus'] else '暂无'}",
        f"新机会只看：{', '.join(summary['opportunity_focus']) if summary['opportunity_focus'] else '暂无'}",
        f"今天最该避免：{' '.join(summary['avoid_points'])}",
        f"主线：{summary['main_theme']}",
        "",
        "持仓动作",
    ]
    for item in watchlist.get("priority", [])[:5]:
        lines.append(f"- {item.get('name')}: {item.get('action')} | {item_trigger(item)} | {item_reason(item)}")
    if not watchlist.get("priority"):
        lines.append("- 暂无必须优先处理的持仓。")

    lines.extend(["", "新仓观察"])
    opportunities = payload["screener"].get("approved") or payload["screener"].get("caution") or []
    if summary["opportunity_focus"]:
        for item in opportunities[:5]:
            lines.append(f"- {item.get('name')}: {item.get('screening_status')} | {item_reason(item)}")
    else:
        lines.append("- 今天先不开新仓。")
    lines.extend(["", "盘中跟踪", summary["midday_summary"], ""])
    return "\n".join(lines)


def render_report(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    watchlist = payload["watchlist"]
    screener = payload["screener"]
    lines = [
        f"# Prism 投资总控台 v1 | {summary['trade_date']}",
        "",
        f"生成时间：{summary['generated_at']}",
        "",
        "## 今日 5 问 5 答",
        f"- 今天能不能开新仓：{summary['open_new_positions']}",
        f"- 总仓位上限：{summary['position_cap']}",
        f"- 持仓先处理谁：{', '.join(summary['holding_focus']) if summary['holding_focus'] else '暂无'}",
        f"- 新机会只看谁：{', '.join(summary['opportunity_focus']) if summary['opportunity_focus'] else '暂无'}",
        f"- 今天最该避免什么：{' '.join(summary['avoid_points'])}",
        "",
        "## 市场阀门",
        f"- 主线方向：{summary['main_theme']}",
        f"- 执行状态：{summary['gate_label']}",
        f"- 阀门说明：{summary['gate_summary']}",
        "",
        "## 持仓侧",
        f"- 持仓总判断：{summary['watchlist_summary']}",
        f"- 自选股快照：{watchlist.get('generated_at') or '-'}",
        f"- 价格口径：{watchlist.get('price_basis') or '-'}",
        f"- 资金口径：{watchlist.get('flow_basis') or '-'}",
        "",
        "### 先处理",
    ]
    if watchlist.get("priority"):
        lines.extend(
            f"- {item.get('name')}：{item.get('action')} | {item_trigger(item)} | 原因：{item_reason(item)}"
            for item in watchlist.get("priority", [])[:8]
        )
    else:
        lines.append("- 暂无。")

    lines.extend(["", "### 继续观察"])
    observe_items = [*(watchlist.get("follow") or []), *(watchlist.get("observe") or [])]
    if observe_items:
        lines.extend(
            f"- {item.get('name')}：{item.get('action')} | {item_trigger(item)} | 原因：{item_reason(item)}"
            for item in observe_items[:8]
        )
    else:
        lines.append("- 暂无。")

    lines.extend(
        [
            "",
            "## 新仓侧",
            f"- Screener 批次：{screener.get('timestamp') or '-'}",
            f"- 引用 scan：{screener.get('source_scan_timestamp') or '-'}",
            f"- 执行阀门：{summary['gate_label']} | 仓位上限 {summary['position_cap']}",
            f"- 环境说明：{summary['gate_summary']}",
            f"- 主线方向：{summary['main_theme']}",
            f"- 风险触发：{'、'.join(summary['avoid_points'])}",
            "",
        ]
    )
    if summary["opportunity_focus"]:
        for item in (screener.get("approved") or screener.get("caution") or [])[:8]:
            lines.append(f"- {item.get('name')}({item.get('code')})：{item_reason(item)}")
    else:
        lines.append("- 当前不放行新的进攻型观察票。")

    lines.extend(
        [
            "",
            "## 盘中跟踪",
            f"- {summary['midday_summary']}",
            "",
            "## 数据引用",
            f"- 自选股快照：{watchlist.get('snapshot_path') or '-'}",
            f"- 进攻型二筛：{screener.get('path') or '-'}",
        ]
    )
    return "\n".join(lines) + "\n"


def write_text(path: str | Path, text: str) -> None:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def main() -> int:
    args = parse_args()
    payload = build_payload(args.date)
    write_text(args.brief_output, render_brief(payload))
    write_text(args.report_output, render_report(payload))
    write_text(args.json_output, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
