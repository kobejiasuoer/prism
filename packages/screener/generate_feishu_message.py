#!/usr/bin/env python3
"""根据二次筛选结果生成飞书/Markdown 报告。"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
DEFAULT_AI_RESULT_PATH = BASE / "data" / "ai_screening_result.json"
DEFAULT_MIDDAY_RESULT_PATH = BASE / "data" / "midday_verification_result.json"

STRATEGY_ORDER = ["combined", "hot", "growth", "rebound", "conservative"]
STATUS_LABELS = {
    "approved": "通过",
    "caution": "观察",
    "excluded": "排除",
}
STATUS_ICONS = {
    "approved": "✅",
    "caution": "⚠️",
    "excluded": "🚫",
}


def fmt_num(value, digits=1):
    if value is None:
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)

    text = f"{number:.{digits}f}"
    if digits > 0:
        text = text.rstrip("0").rstrip(".")
    return text


def fmt_pct(value):
    text = fmt_num(value, 2)
    return f"{text}%" if text != "-" else text


def fmt_amount_yi(value):
    text = fmt_num(value, 1)
    return f"{text}亿" if text != "-" else text


def fmt_percent_ratio(value):
    if value is None:
        return "-"
    return f"{float(value) * 100:.1f}%"


def unique_keep_order(values):
    seen = set()
    result = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def format_regime_metrics(metrics):
    if not metrics:
        return None
    return (
        f"上涨占比 {fmt_percent_ratio(metrics.get('positive_ratio'))} | "
        f"强势股占比 {fmt_percent_ratio(metrics.get('strong_ratio'))} | "
        f"平均涨幅 {fmt_pct(metrics.get('avg_change_pct'))} | "
        f"平均换手 {fmt_num(metrics.get('avg_turnover'), 2)}"
    )


def parse_timestamp(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def fmt_hm(value):
    dt = parse_timestamp(value)
    return dt.strftime("%H:%M") if dt else ""


def is_same_date(ts_a, ts_b):
    dt_a = parse_timestamp(ts_a)
    dt_b = parse_timestamp(ts_b)
    if not dt_a or not dt_b:
        return False
    return dt_a.date() == dt_b.date()


def midday_matches_result(midday_result, ai_result):
    if not midday_result:
        return False
    if midday_result.get("validation_status") != "ok":
        return False
    source_morning_timestamp = midday_result.get("source_morning_timestamp")
    source_scan_timestamp = midday_result.get("source_scan_timestamp")
    verified_against_scan_timestamp = midday_result.get("verified_against_scan_timestamp")
    result_timestamp = ai_result.get("timestamp")
    result_scan_timestamp = ai_result.get("source_scan_timestamp")
    if not source_morning_timestamp or not result_timestamp:
        return False
    if source_morning_timestamp != result_timestamp:
        return False
    if not source_scan_timestamp or not result_scan_timestamp:
        return False
    if source_scan_timestamp != result_scan_timestamp:
        return False
    if verified_against_scan_timestamp and not is_same_date(verified_against_scan_timestamp, result_timestamp):
        return False
    return True


def lifecycle_matches_result(lifecycle_result, ai_result):
    if not lifecycle_result:
        return False
    metadata = lifecycle_result.get("metadata") or {}
    current_timestamp = metadata.get("current_timestamp")
    result_timestamp = ai_result.get("timestamp")
    if current_timestamp and result_timestamp:
        return current_timestamp == result_timestamp
    return False


def has_valid_midday_verification(result):
    verification = result.get("midday_verification") or {}
    return verification.get("validation_status") == "ok"


def effective_report_timestamp(result):
    if has_valid_midday_verification(result):
        verification = result.get("midday_verification") or {}
        return (
            verification.get("verified_against_scan_timestamp")
            or verification.get("timestamp")
            or result.get("source_scan_timestamp")
            or result.get("timestamp")
        )
    return result.get("source_scan_timestamp") or result.get("timestamp")


def render_market_regime(result):
    regime = result.get("market_regime") or {}
    metrics = regime.get("metrics") or {}
    candidate_view = regime.get("candidate_view") or {}
    execution_gate = regime.get("execution_gate") or {}
    if not regime:
        return "## 市场环境\n- 暂无市场环境判断"

    lines = [
        "## 市场环境",
        f"- 主口径（股票池全样本）：**{regime.get('label', '未知')}** | 评分 {fmt_num(regime.get('score'), 0)}",
        f"- 说明：{regime.get('summary', '无')}",
    ]

    metric_line = format_regime_metrics(metrics)
    if metric_line:
        lines.append(f"- 主口径指标：{metric_line}")

    if candidate_view:
        lines.append(
            f"- 候选口径（已入围候选）：**{candidate_view.get('label', '未知')}** | "
            f"评分 {fmt_num(candidate_view.get('score'), 0)} | 样本 {candidate_view.get('sample_size', 0)} 只"
        )
        candidate_metrics = format_regime_metrics(candidate_view.get("metrics") or {})
        if candidate_metrics:
            lines.append(f"- 候选口径指标：{candidate_metrics}")
        if regime.get("candidate_gap_note"):
            lines.append(f"- 提醒：{regime.get('candidate_gap_note')}")
    if execution_gate:
        lines.append(
            f"- 执行阀门：**{execution_gate.get('label', '未定义')}** | "
            f"仓位上限 {execution_gate.get('position_cap', '-')}"
        )
        if execution_gate.get("summary"):
            lines.append(f"- 阀门说明：{execution_gate.get('summary')}")
        risk_flags = execution_gate.get("risk_flags") or []
        if risk_flags:
            lines.append(f"- 风险触发：{'、'.join(risk_flags[:4])}")

    return "\n".join(lines)


def render_market_themes(result):
    theme_block = result.get("market_themes") or {}
    themes = theme_block.get("themes") or []
    if not themes:
        return "## 主线题材\n- 暂无题材聚类结果"

    lines = [
        "## 主线题材",
        f"- 总结：{theme_block.get('summary', '无')}",
    ]

    for item in themes[:3]:
        leaders = "、".join(item.get("leader_codes") or []) or "无"
        persistence = item.get("persistence") or {}
        persistence_summary = persistence.get("summary") or "无"
        lines.append(
            f"- {item.get('theme', '其他')} | 主题分 {fmt_num(item.get('score'), 2)} | "
            f"持续性 {persistence.get('label', '未知')}({fmt_num(persistence.get('score'), 0)}) | "
            f"样本 {item.get('count', 0)} 只 | 龙头：{leaders}"
        )
        lines.append(f"  持续性说明：{persistence_summary}")

    return "\n".join(lines)


def render_shortlist(result):
    shortlist = result.get("shortlist") or []
    if not shortlist:
        return "## 今日 Shortlist\n- 本轮没有通过二次筛选的候选"

    lines = ["## 今日 Shortlist"]
    for idx, item in enumerate(shortlist[:8], start=1):
        status = item.get("screening_status", "caution")
        hits = "、".join(item.get("strategy_labels") or item.get("strategy_hits") or [])
        themes = " / ".join(item.get("themes") or ["其他"])
        flow = (item.get("capital_flow") or {}).get("trend") or "无数据"
        tier = item.get("tier", "C")
        tier_note = item.get("tier_note", "")
        lines.append(
            f"{idx}. **[{tier}] {item.get('name')}({item.get('code')})** | "
            f"{fmt_num(item.get('best_score'), 2)}分 | 命中：{hits} | "
            f"{STATUS_ICONS.get(status, '•')} {STATUS_LABELS.get(status, status)}"
        )
        lines.append(
            f"   分层：{tier_note} | 题材：{themes} | 资金：{flow} | 涨幅：{fmt_pct(item.get('change_pct'))} | "
            f"成交额：{fmt_amount_yi(item.get('amount_yi'))}"
        )
        lines.append(f"   理由：{item.get('entry_reason', '无')}")
        if item.get("setup_label") or item.get("setup_summary"):
            lines.append(
                f"   Setup：{item.get('setup_label', '观察等待')} | {item.get('setup_summary', '无')}"
            )
        entry_plan = item.get("entry_plan") or {}
        if entry_plan:
            plan_parts = [entry_plan.get("action"), entry_plan.get("sizing")]
            plan_parts = [part for part in plan_parts if part]
            if plan_parts:
                lines.append(f"   计划：{' | '.join(plan_parts)}")
            if entry_plan.get("trigger"):
                lines.append(f"   触发：{entry_plan.get('trigger')}")
            if entry_plan.get("invalidate"):
                lines.append(f"   取消：{entry_plan.get('invalidate')}")
        execution_quality = item.get("execution_quality") or {}
        if execution_quality.get("label"):
            quality_parts = [f"{execution_quality.get('label')}({fmt_num(execution_quality.get('score'), 0)})"]
            positives = "、".join(execution_quality.get("positives") or [])
            warnings = "、".join(execution_quality.get("warnings") or [])
            if positives:
                quality_parts.append(f"优点：{positives}")
            if warnings:
                quality_parts.append(f"限制：{warnings}")
            lines.append(f"   执行质量：{' | '.join(quality_parts)}")
        lines.append(f"   风险：{item.get('main_risk', '无')}")
        consistency = item.get('consistency') or {}
        if consistency.get('label'):
            lines.append(f"   一致性：{consistency.get('label')}({fmt_num(consistency.get('score'), 0)})")
            notes = '；'.join((consistency.get('notes') or [])[:2])
            if notes:
                lines.append(f"   一致性说明：{notes}")
        if item.get('notice_risk_tags'):
            labels = '/'.join(sorted({x.get('label') for x in item.get('notice_risk_tags') if x.get('label')}))
            lines.append(f"   公告标签：{labels}")
        lines.append(f"   观察：{item.get('watch_condition', '无')}")
        if idx < min(8, len(shortlist)):
            lines.append("")

    return "\n".join(lines)


def render_midday_verification(result):
    verification = result.get("midday_verification") or {}
    if not verification:
        return ""

    confirmed = verification.get("confirmed") or []
    downgraded = verification.get("downgraded") or []
    fresh_candidates = verification.get("fresh_candidates") or []
    items = verification.get("items") or []
    active_themes = unique_keep_order(
        theme
        for item in items
        for theme in ((item.get("snapshot") or {}).get("active_themes") or [])
        if theme
    )

    lines = ["## 午盘承接确认"]
    lines.append(f"- 确认通过：{len(confirmed)} | 降级：{len(downgraded)}")
    if active_themes:
        lines.append(f"- 当前主线参考：{'、'.join(active_themes[:2])}")
    for item in confirmed[:3]:
        snap = item.get("snapshot") or {}
        level_text = midday_level_text(snap)
        detail_text = midday_detail_text(item)
        lines.append(
            f"- ✅ [{item.get('tier','-')}] {item.get('name')}({item.get('code')}) | "
            f"{snap.get('confirmation_label', '承接通过')} | {snap.get('setup_label') or '结构待确认'}"
        )
        lines.append(
            "  "
            + " | ".join(
                [
                    f"现价 {fmt_num(snap.get('price'), 2)}",
                    f"涨幅 {fmt_pct(snap.get('change_pct'))}",
                    f"较晨间 {fmt_signed(snap.get('change_delta'), 2, suffix='%')}",
                    f"分数 {fmt_num(snap.get('score'), 2)} ({fmt_signed(snap.get('score_delta'), 2)})",
                ]
            )
        )
        if level_text:
            lines.append(f"  结构：{level_text}")
        if detail_text:
            lines.append(f"  要点：{detail_text}")
    for item in downgraded[:3]:
        snap = item.get("snapshot") or {}
        level_text = midday_level_text(snap)
        detail_text = midday_detail_text(item)
        lines.append(
            f"- ⚠️ [{item.get('tier','-')}] {item.get('name')}({item.get('code')}) | "
            f"{snap.get('confirmation_label', '承接失效')} | {item.get('reason', '已降级')}"
        )
        if snap:
            lines.append(
                "  "
                + " | ".join(
                    [
                        f"现价 {fmt_num(snap.get('price'), 2)}",
                        f"涨幅 {fmt_pct(snap.get('change_pct'))}",
                        f"较晨间 {fmt_signed(snap.get('change_delta'), 2, suffix='%')}",
                        f"分数 {fmt_num(snap.get('score'), 2)} ({fmt_signed(snap.get('score_delta'), 2)})",
                    ]
                )
            )
        if level_text:
            lines.append(f"  结构：{level_text}")
        if detail_text:
            lines.append(f"  要点：{detail_text}")
    if fresh_candidates:
        lines.append(f"- 当前新增观察：{'、'.join(x.get('name') for x in fresh_candidates[:3] if x.get('name'))}")
        for item in fresh_candidates[:3]:
            lines.append(
                f"  - {item.get('name')}({item.get('code')}) | {item.get('setup_label') or '盘中新机会'} | "
                f"评分 {fmt_num(item.get('score'), 2)} | 涨幅 {fmt_pct(item.get('change_pct'))} | {item.get('entry_reason') or '只观察'}"
            )
    return "\n".join(lines)


def render_lifecycle(result):
    lifecycle = result.get("lifecycle") or {}
    if not lifecycle:
        return ""

    summary = lifecycle.get("summary") or {}
    metadata = lifecycle.get("metadata") or {}
    lines = ["## 候选生命周期"]
    previous_ts = metadata.get("previous_snapshot_timestamp") or metadata.get("previous_snapshot_source") or "未知"
    lines.append(f"- 对比基准：{previous_ts}")
    lines.append(
        f"- 新入选 {summary.get('entered_count', 0)} | 升级 {summary.get('upgraded_count', 0)} | "
        f"降级 {summary.get('downgraded_count', 0)} | 退出 {summary.get('exited_count', 0)} | "
        f"已移交 analyzer {summary.get('handed_off_count', 0)}"
    )

    entered = lifecycle.get("entered") or []
    upgraded = lifecycle.get("upgraded") or []
    downgraded = lifecycle.get("downgraded") or []
    handed_off = lifecycle.get("handed_off") or []

    if entered:
        sample = "、".join(f"{x.get('name')}({x.get('code')})" for x in entered[:3])
        lines.append(f"- 新入选：{sample}")
    if upgraded:
        sample = "、".join(f"{x.get('name')}({x.get('code')})" for x in upgraded[:3])
        lines.append(f"- 升级：{sample}")
    if downgraded:
        for item in downgraded[:3]:
            reason = item.get("reason") or "状态走弱"
            lines.append(f"- 降级：{item.get('name')}({item.get('code')}) | {reason}")
    if handed_off:
        sample = "、".join(f"{x.get('name')}({x.get('code')})" for x in handed_off[:3])
        lines.append(f"- 已移交 analyzer：{sample}")

    return "\n".join(lines)


def render_watchlist(result):
    shortlist = result.get("shortlist") or []
    tier_b = [item for item in shortlist if item.get("tier") == "B"]
    tier_c = [item for item in shortlist if item.get("tier") == "C"]
    if not tier_b and not tier_c:
        return ""

    lines = []
    if tier_b:
        lines.append("## B层：盘中确认")
        for item in tier_b[:4]:
            lines.append(
                f"- {item.get('name')}({item.get('code')}) | {fmt_num(item.get('best_score'), 2)}分 | {item.get('screening_note', '待确认')}"
            )
            if item.get("setup_label"):
                lines.append(f"  Setup：{item.get('setup_label')} | {item.get('setup_summary', '无')}")
            entry_plan = item.get("entry_plan") or {}
            if entry_plan.get("trigger"):
                lines.append(f"  触发：{entry_plan.get('trigger')}")
            consistency = item.get('consistency') or {}
            extra = f" | 一致性 {consistency.get('label')}" if consistency.get('label') else ""
            note_text = '；'.join((consistency.get('notes') or [])[:1])
            if note_text:
                extra += f" | {note_text}"
            lines.append(f"  核心观察：{item.get('watch_condition', '无')}{extra}")
    if tier_c:
        if lines:
            lines.append("")
        lines.append("## C层：候补观察")
        for item in tier_c[:4]:
            lines.append(
                f"- ⚠️ {item.get('name')}({item.get('code')}) | {fmt_num(item.get('best_score'), 2)}分 | {item.get('screening_note', '先观察')}"
            )
            lines.append(f"  主要风险：{item.get('main_risk', '无')}")
            lines.append(f"  观察条件：{item.get('watch_condition', '无')}")
    return "\n".join(lines)


def render_strategy_views(result):
    strategies = result.get("strategies") or {}
    blocks = ["## 分策略观察"]

    has_content = False
    for name in STRATEGY_ORDER:
        strategy = strategies.get(name)
        if not strategy or not strategy.get("top_stocks"):
            continue

        has_content = True
        blocks.append(
            f"### {strategy.get('label', name)} Top {min(3, len(strategy.get('top_stocks') or []))}"
        )
        blocks.append(
            f"- 原始 {strategy.get('original_count', 0)} | 通过 {strategy.get('approved_count', 0)} | "
            f"观察 {strategy.get('caution_count', 0)} | 排除 {strategy.get('excluded_count', 0)}"
        )
        for stock in (strategy.get("top_stocks") or [])[:3]:
            status = (stock.get("screening") or {}).get("status", "caution")
            blocks.append(
                f"- {STATUS_ICONS.get(status, '•')} {stock.get('name')}({stock.get('code')}) | "
                f"{fmt_num(stock.get('score'), 2)}分 | {stock.get('theme', '其他')} | "
                f"{stock.get('entry_reason', '无')}"
            )

    if not has_content:
        blocks.append("- 所有策略当前都没有通过二筛的候选")

    return "\n".join(blocks)


def render_analyzer_handoff(result):
    candidates = result.get("analyzer_candidates") or []
    if not candidates:
        return "## 建议送 Analyzer 的前 3\n- 暂无可继续深挖的候选"

    lines = ["## 建议送 Analyzer 的前 3"]
    for item in candidates:
        hits = "、".join(item.get("strategy_labels") or [])
        tier = item.get("tier", "-")
        lines.append(
            f"- [{tier}] {item.get('name')}({item.get('code')}) | {fmt_num(item.get('best_score'), 2)}分 | "
            f"命中：{hits} | 理由：{item.get('reason', '无')}"
        )
        if item.get("setup_label"):
            lines.append(f"  Setup：{item.get('setup_label')}")
        execution_quality = item.get("execution_quality") or {}
        if execution_quality.get("label"):
            lines.append(
                f"  执行质量：{execution_quality.get('label')}({fmt_num(execution_quality.get('score'), 0)})"
            )
        lines.append(f"  盘中观察：{item.get('watch_condition', '无')}")
        entry_plan = item.get("entry_plan") or {}
        if entry_plan.get("trigger"):
            lines.append(f"  触发条件：{entry_plan.get('trigger')}")
    return "\n".join(lines)


def render_screening_summary(result):
    summary = result.get("screening_summary") or {}
    execution_gate = (result.get("market_regime") or {}).get("execution_gate") or {}
    lines = [
        "## 筛选摘要",
        f"- 策略样本总数：{summary.get('total_candidates', 0)}",
        f"- 去重后候选：{summary.get('unique_candidates', 0)}",
        f"- 最终 shortlist：{summary.get('shortlisted_count', 0)}",
        f"- A层：{summary.get('tier_a_count', 0)} | B层：{summary.get('tier_b_count', 0)} | C层：{summary.get('tier_c_count', 0)}",
        f"- 通过：{summary.get('approved_count', 0)} | 观察：{summary.get('caution_count', 0)} | 排除：{summary.get('excluded_count', 0)}",
        f"- 执行质量：高 {summary.get('quality_high_count', 0)} | 中 {summary.get('quality_mid_count', 0)} | 低 {summary.get('quality_low_count', 0)}",
    ]
    if execution_gate:
        lines.append(
            f"- 执行状态：{execution_gate.get('label', '未定义')} | "
            f"仓位上限 {execution_gate.get('position_cap', '-')}"
        )
    return "\n".join(lines)


def infer_run_label(result):
    if has_valid_midday_verification(result):
        return "进攻型午盘确认"

    scan_ts = parse_timestamp(effective_report_timestamp(result))
    if not scan_ts:
        return "进攻型选股"
    if scan_ts.hour < 12:
        return "进攻型早盘"
    if scan_ts.hour < 15:
        return "进攻型午盘"
    return "进攻型选股"


def concise_watch_condition(text):
    if not text:
        return "先看盘中确认"
    for sep in ("；", ";", "，", ","):
        if sep in text:
            return text.split(sep, 1)[0].strip()
    return text.strip()


def concise_risk(text):
    if not text:
        return "暂无突出硬风险"
    for sep in ("；", ";", "，", ","):
        if sep in text:
            return text.split(sep, 1)[0].strip()
    return text.strip()


def market_line(result):
    regime = result.get("market_regime") or {}
    execution_gate = regime.get("execution_gate") or {}
    gate_status = execution_gate.get("status")
    if gate_status == "off":
        return "今天进攻阀门关闭，建议空仓观察。"
    if gate_status == "limited":
        return "今天进攻阀门半开，只允许轻仓试错。"
    score = regime.get("score")
    try:
        score = float(score)
    except (TypeError, ValueError):
        score = None

    if score is None:
        return "今天先以观察为主。"
    if score >= 8:
        return "今天可做，但只做高质量共振票。"
    if score >= 6:
        return "今天可做，但仍只适合轻仓试错。"
    if score >= 4:
        return "今天偏谨慎，只盯主线强票。"
    return "今天先不主动开新仓。"


def theme_line(result):
    themes = (result.get("market_themes") or {}).get("themes") or []
    labels = [item.get("theme") for item in themes if item.get("theme")]
    labels = [label for label in labels if label != "其他"]
    labels = labels[:2] or [item.get("theme") for item in themes[:1] if item.get("theme")]
    if not labels:
        return ""
    return "主线：" + "、".join(labels) + "。"


def shortlist_sort_key(item):
    status = item.get("screening_status")
    tier_rank = item.get("tier_rank")
    priority = item.get("priority_score")
    score = item.get("best_score")
    status_rank = 2
    if status == "approved":
        status_rank = 0
    elif status == "caution":
        status_rank = 1
    try:
        tier_rank = -float(tier_rank)
    except (TypeError, ValueError):
        tier_rank = 0
    try:
        priority = -float(priority)
    except (TypeError, ValueError):
        priority = 0
    try:
        score = -float(score)
    except (TypeError, ValueError):
        score = 0
    return (status_rank, tier_rank, priority, score, item.get("code", ""))


def decision_label(item):
    status = item.get("screening_status")
    tier = item.get("tier")
    risk = item.get("main_risk", "") or ""
    if status == "approved" and tier == "A":
        return "可试"
    if status == "approved" and tier == "B":
        return "候补"
    if any(tag in risk for tag in ["诉讼", "质押", "估值偏高", "估值过热", "爆量", "过热"]):
        return "别追"
    return "只观察"


def theme_text(item):
    if item.get("themes"):
        return " / ".join(item.get("themes") or ["其他"])
    if item.get("theme"):
        return item.get("theme")
    return "其他"


def compact_text(text, fallback):
    text = (text or "").strip()
    return text if text else fallback


def fmt_signed(value, digits=2, suffix=""):
    if value is None:
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)

    text = f"{number:+.{digits}f}"
    if digits > 0:
        text = text.rstrip("0").rstrip(".")
    return f"{text}{suffix}"


def midday_level_text(snapshot):
    if not snapshot:
        return ""

    price = snapshot.get("price")
    trigger = snapshot.get("trigger_level")
    pullback = snapshot.get("pullback_level")
    invalidate = snapshot.get("invalidate_level")
    ma5 = snapshot.get("ma5")
    ma10 = snapshot.get("ma10")
    ma20 = snapshot.get("ma20")

    try:
        price_value = float(price)
    except (TypeError, ValueError):
        price_value = None

    if price_value is not None and invalidate is not None and price_value <= float(invalidate):
        return f"已跌破取消位 {fmt_num(invalidate, 2)}"
    if price_value is not None and trigger is not None and price_value >= float(trigger):
        return f"已站稳触发位 {fmt_num(trigger, 2)}"
    if price_value is not None and pullback is not None and price_value >= float(pullback):
        return f"仍守住承接位 {fmt_num(pullback, 2)}"
    if price_value is not None and pullback is not None and price_value < float(pullback):
        return f"已回落到承接位下方 {fmt_num(pullback, 2)}"
    if price_value is not None and ma5 is not None and price_value >= float(ma5):
        return f"短线仍在 MA5({fmt_num(ma5, 2)}) 上方"
    if price_value is not None and ma10 is not None and price_value >= float(ma10):
        return f"仍在 MA10({fmt_num(ma10, 2)}) 上方"
    if price_value is not None and ma20 is not None and price_value >= float(ma20):
        return f"仍在 MA20({fmt_num(ma20, 2)}) 上方"
    return ""


def midday_detail_text(item, limit=3):
    snapshot = item.get("snapshot") or {}
    positives = snapshot.get("positives") or []
    details = item.get("details") or []
    status = item.get("status")

    if status == "confirmed":
        merged = unique_keep_order(list(positives) + list(details))
    else:
        merged = unique_keep_order(list(details) + list(positives))
    merged = [text for text in merged if text]
    return "；".join(merged[:limit])


def summarize_midday_keep(item):
    snap = item.get("snapshot") or {}
    parts = []
    if snap.get("setup_label"):
        parts.append(snap.get("setup_label"))
    level = midday_level_text(snap)
    if level:
        parts.append(level)
    reason = item.get("reason")
    if reason:
        parts.append(reason)
    return "，".join(parts[:3]) or "午盘承接仍在"


def summarize_midday_drop(item):
    snap = item.get("snapshot") or {}
    score = snap.get("score")
    reason = item.get("reason") or snap.get("confirmation_label") or "承接失效"
    if score is not None:
        return f"{reason}，盘中分数 {fmt_num(score, 2)}"
    return reason


def concise_scan_watch(text):
    return compact_text(text, "先等二次确认")


def render_midday_fresh_candidate(prefix, item):
    theme = item.get("theme") or "其他"
    flow = item.get("capital_trend") or "资金未确认"
    reason = item.get("entry_reason") or "盘中强度较高"
    trigger = concise_scan_watch(item.get("watch_condition"))
    risk = compact_text(item.get("main_risk"), "只观察，不追")
    title = (
        f"{prefix}{item.get('name')}：{item.get('setup_label') or '盘中新机会'} | "
        f"只观察 | 先不开新仓"
    )
    return [
        title,
        f"   {theme} | {flow} | {reason}",
        f"   盘中强度：评分 {fmt_num(item.get('score'), 2)} | 涨幅 {fmt_pct(item.get('change_pct'))} | 成交额 {fmt_amount_yi(item.get('amount_yi'))}",
        "   做法：先等二次确认，不追已经拉开的阳线。",
        f"   触发：{trigger}",
        f"   风险：{risk}",
    ]


def build_midday_confirmation_brief(result):
    verification = result.get("midday_verification") or {}
    confirmed = verification.get("confirmed") or []
    downgraded = verification.get("downgraded") or []
    fresh_candidates = verification.get("fresh_candidates") or []

    lines = []
    run_label = infer_run_label(result)
    morning_ts = verification.get("source_scan_timestamp") or result.get("source_scan_timestamp") or ""
    verified_ts = verification.get("verified_against_scan_timestamp") or effective_report_timestamp(result) or ""
    active_themes = unique_keep_order(
        [theme for item in fresh_candidates for theme in [item.get("theme")] if theme and theme not in {"其他", "其它"}]
        + [theme for item in verification.get("items") or [] for theme in ((item.get("snapshot") or {}).get("active_themes") or []) if theme]
    )

    lines.append(f"{run_label} | {verified_ts}")
    time_parts = []
    if morning_ts:
        time_parts.append(f"晨间基线 {fmt_hm(morning_ts)}")
    if verified_ts:
        time_parts.append(f"午盘确认 {fmt_hm(verified_ts)}")
    if time_parts:
        lines.append(" | ".join(time_parts))

    summary = f"结论：保留 {len(confirmed)}，剔除 {len(downgraded)}，新增观察 {len(fresh_candidates)}。"
    if active_themes:
        summary += f" 当前主线：{'、'.join(active_themes[:2])}。"
    lines.append(summary)

    if confirmed:
        keep_text = "；".join(f"{item.get('name')}（{summarize_midday_keep(item)}）" for item in confirmed[:2])
        lines.append(f"保留：{keep_text}")
    else:
        lines.append("保留：暂无仍可继续看的晨间动作票。")

    if downgraded:
        drop_text = "；".join(f"{item.get('name')}（{summarize_midday_drop(item)}）" for item in downgraded[:2])
        lines.append(f"剔除：{drop_text}")

    if fresh_candidates:
        fresh_names = "、".join(item.get("name") for item in fresh_candidates[:3] if item.get("name"))
        if len(fresh_candidates) > 2:
            lines.append(f"新增观察：{fresh_names}（只观察，不追；正文展开前2只，其余见附件）")
        else:
            lines.append(f"新增观察：{fresh_names}（只观察，不追）")

    lines.append("")
    lines.append("若上午已上车")
    if confirmed:
        for item in confirmed[:2]:
            snap = item.get("snapshot") or {}
            level = fmt_num(snap.get("invalidate_level"), 2)
            if level != "-":
                lines.append(f"- {item.get('name')}：继续看承接，跌破 {level} 或资金转负再撤。")
            else:
                lines.append(f"- {item.get('name')}：继续看承接，弱转强失败就撤。")
    else:
        lines.append("- 晨间票没有继续保留的对象，优先收缩动作。")
    for item in downgraded[:2]:
        snap = item.get("snapshot") or {}
        level = fmt_num(snap.get("invalidate_level"), 2)
        reason = item.get("reason") or "承接失效"
        if level != "-":
            lines.append(f"- {item.get('name')}：不再加仓，{reason}；跌破 {level} 或继续转弱就退出观察。")
        else:
            lines.append(f"- {item.get('name')}：不再加仓，{reason}。")

    lines.append("")
    lines.append("若当前空仓")
    if fresh_candidates:
        fresh_names = "、".join(item.get("name") for item in fresh_candidates[:2] if item.get("name"))
        if len(fresh_candidates) > 2:
            lines.append(f"- 先看 {fresh_names} 的二次确认，其余观察票见附件。")
        else:
            lines.append(f"- 只看 {fresh_names} 的二次确认。")
    else:
        lines.append("- 暂无新增观察票，先别硬开仓。")
    lines.append("- 仍按轻仓试错，不追已经拉开的阳线。")

    if confirmed:
        lines.append("")
        lines.append("继续保留")
        for idx, item in enumerate(confirmed[:2], start=1):
            snap = item.get("snapshot") or {}
            level = fmt_num(snap.get("invalidate_level"), 2)
            lines.append(
                f"{idx}. {item.get('name')}：{snap.get('setup_label') or '结构待确认'} | 继续看 | 现价 {fmt_num(snap.get('price'), 2)} | 涨幅 {fmt_pct(snap.get('change_pct'))}"
            )
            lines.append(f"   要点：{summarize_midday_keep(item)}")
            lines.append("   做法：继续看承接，不追已经发散的阳线。")
            if level != "-":
                lines.append(f"   取消：跌破 {level} 或主力转负就取消。")

    if fresh_candidates:
        lines.append("")
        if len(fresh_candidates) > 2:
            lines.append(f"新增观察（正文展开前2只，其余 {len(fresh_candidates) - 2} 只见附件）")
        else:
            lines.append("新增观察")
        for item in fresh_candidates[:2]:
            lines.extend(render_midday_fresh_candidate("- ", item))

    return "\n".join(lines).strip() + "\n"


def render_midday_baseline_targets(result):
    verification = result.get("midday_verification") or {}
    target_codes = verification.get("target_codes") or []
    shortlist = {item.get("code"): item for item in (result.get("shortlist") or []) if item.get("code")}
    if not target_codes:
        return ""

    lines = ["## 晨间基线目标"]
    for code in target_codes[:6]:
        item = shortlist.get(code)
        if not item:
            continue
        entry_plan = item.get("entry_plan") or {}
        lines.append(
            f"- {item.get('name')}({code}) | 晨间分数 {fmt_num(item.get('best_score'), 2)} | "
            f"晨间涨幅 {fmt_pct(item.get('change_pct'))} | {item.get('setup_label') or '结构待确认'}"
        )
        if entry_plan.get("action"):
            lines.append(f"  晨间计划：{entry_plan.get('action')}")
        if entry_plan.get("trigger"):
            lines.append(f"  晨间触发：{entry_plan.get('trigger')}")
    return "\n".join(lines)


def render_midday_confirmation_outcome(result):
    verification = result.get("midday_verification") or {}
    confirmed = verification.get("confirmed") or []
    downgraded = verification.get("downgraded") or []
    fresh_candidates = verification.get("fresh_candidates") or []
    active_themes = unique_keep_order(
        [theme for item in fresh_candidates for theme in [item.get("theme")] if theme and theme not in {"其他", "其它"}]
        + [theme for item in verification.get("items") or [] for theme in ((item.get("snapshot") or {}).get("active_themes") or []) if theme]
    )

    lines = ["## 午盘结论"]
    lines.append(f"- 保留 {len(confirmed)} | 剔除 {len(downgraded)} | 新增观察 {len(fresh_candidates)}")
    if active_themes:
        lines.append(f"- 当前主线参考：{'、'.join(active_themes[:2])}")
    if confirmed:
        lines.append(f"- 保留：{'、'.join(item.get('name') for item in confirmed[:3] if item.get('name'))}")
    if downgraded:
        lines.append(f"- 剔除：{'、'.join(item.get('name') for item in downgraded[:3] if item.get('name'))}")
    if fresh_candidates:
        lines.append(f"- 新增观察：{'、'.join(item.get('name') for item in fresh_candidates[:3] if item.get('name'))}")
    return "\n".join(lines)


def render_midday_confirmed_details(result):
    confirmed = ((result.get("midday_verification") or {}).get("confirmed") or [])
    if not confirmed:
        return "## 保留票\n- 本轮没有继续保留的晨间动作票"

    lines = ["## 保留票"]
    for item in confirmed[:4]:
        snap = item.get("snapshot") or {}
        lines.append(
            f"- ✅ {item.get('name')}({item.get('code')}) | {snap.get('setup_label') or '结构待确认'} | "
            f"现价 {fmt_num(snap.get('price'), 2)} | 涨幅 {fmt_pct(snap.get('change_pct'))} | 分数 {fmt_num(snap.get('score'), 2)}"
        )
        level = midday_level_text(snap)
        if level:
            lines.append(f"  结构：{level}")
        detail = midday_detail_text(item)
        if detail:
            lines.append(f"  要点：{detail}")
        invalidate = fmt_num(snap.get("invalidate_level"), 2)
        if invalidate != "-":
            lines.append(f"  操作：继续看承接，跌破 {invalidate} 或主力转负再撤。")
    return "\n".join(lines)


def render_midday_downgraded_details(result):
    downgraded = ((result.get("midday_verification") or {}).get("downgraded") or [])
    if not downgraded:
        return "## 剔除票\n- 本轮没有新增剔除对象"

    lines = ["## 剔除票"]
    for item in downgraded[:4]:
        snap = item.get("snapshot") or {}
        lines.append(
            f"- ⚠️ {item.get('name')}({item.get('code')}) | {item.get('reason') or '承接失效'} | "
            f"现价 {fmt_num(snap.get('price'), 2)} | 涨幅 {fmt_pct(snap.get('change_pct'))} | 分数 {fmt_num(snap.get('score'), 2)}"
        )
        level = midday_level_text(snap)
        if level:
            lines.append(f"  结构：{level}")
        detail = midday_detail_text(item)
        if detail:
            lines.append(f"  要点：{detail}")
        invalidate = fmt_num(snap.get("invalidate_level"), 2)
        if invalidate != "-":
            lines.append(f"  操作：不再加仓，跌破 {invalidate} 或继续转弱就退出观察。")
        else:
            lines.append("  操作：不再加仓，等待下一轮新结构。")
    return "\n".join(lines)


def render_midday_fresh_details(result):
    fresh_candidates = ((result.get("midday_verification") or {}).get("fresh_candidates") or [])
    if not fresh_candidates:
        return "## 新增观察\n- 本轮没有新增观察票"

    lines = ["## 新增观察"]
    for item in fresh_candidates[:4]:
        lines.append(
            f"- {item.get('name')}({item.get('code')}) | {item.get('setup_label') or '盘中新机会'} | "
            f"评分 {fmt_num(item.get('score'), 2)} | 涨幅 {fmt_pct(item.get('change_pct'))} | 成交额 {fmt_amount_yi(item.get('amount_yi'))}"
        )
        lines.append(
            f"  题材：{item.get('theme') or '其他'} | 资金：{item.get('capital_trend') or '资金未确认'} | 理由：{item.get('entry_reason') or '只观察'}"
        )
        lines.append(f"  触发：{concise_scan_watch(item.get('watch_condition'))}")
        lines.append(f"  风险：{compact_text(item.get('main_risk'), '只观察，不追')}")
    return "\n".join(lines)


def build_midday_confirmation_full_report(result):
    verification = result.get("midday_verification") or {}
    report_timestamp = verification.get("verified_against_scan_timestamp") or effective_report_timestamp(result) or result.get("timestamp", "")
    morning_scan_ts = verification.get("source_scan_timestamp") or result.get("source_scan_timestamp") or "-"
    midday_scan_ts = verification.get("verified_against_scan_timestamp") or report_timestamp or "-"

    sections = [
        render_midday_confirmation_outcome(result),
        render_midday_baseline_targets(result),
        render_midday_confirmed_details(result),
        render_midday_downgraded_details(result),
        render_midday_fresh_details(result),
    ]

    lines = [
        f"# 进攻型午盘承接确认 | {report_timestamp}",
        f"晨间基线扫描：{morning_scan_ts}",
        f"午盘确认扫描：{midday_scan_ts}",
    ]
    for section in sections:
        if section:
            lines.extend(["", section])
    return "\n".join(lines).strip() + "\n"


def render_midday_brief(result):
    verification = result.get("midday_verification") or {}
    if not verification:
        return ""

    confirmed = verification.get("confirmed") or []
    downgraded = verification.get("downgraded") or []
    if not confirmed and not downgraded:
        return ""

    lines = ["午盘承接", f"通过 {len(confirmed)}，降级 {len(downgraded)}。"]

    for item in confirmed[:2]:
        snap = item.get("snapshot") or {}
        action = "继续看" if snap.get("confirmation_label") == "承接良好" else "候补看"
        focus_parts = [
            snap.get("setup_label"),
            snap.get("confirmation_label"),
            midday_level_text(snap),
        ]
        focus_parts = [part for part in focus_parts if part]
        detail_text = midday_detail_text(item, limit=2)
        if detail_text:
            focus_parts.append(detail_text)
        lines.append(f"- {action}：{item.get('name')}({ '，'.join(focus_parts) })")

    for item in downgraded[:2]:
        snap = item.get("snapshot") or {}
        reason = item.get("reason") or snap.get("confirmation_label") or "承接失效"
        lines.append(f"- 先剔除：{item.get('name')}({reason})")

    return "\n".join(lines)


def render_mobile_stock(prefix, item):
    theme = theme_text(item)
    flow = (item.get("capital_flow") or {}).get("trend") or "资金未确认"
    reason = item.get("entry_reason") or item.get("screening_note") or "等待确认"
    setup_label = item.get("setup_label") or "观察等待"
    entry_plan = item.get("entry_plan") or {}
    execution_quality = item.get("execution_quality") or {}
    sizing = entry_plan.get("sizing") or ""
    action = compact_text(entry_plan.get("action"), reason)
    trigger = compact_text(entry_plan.get("trigger"), concise_watch_condition(item.get("watch_condition")))
    invalidate = compact_text(entry_plan.get("invalidate"), concise_risk(item.get("main_risk")))
    title = f"{prefix}{item.get('name')}：{setup_label} | {decision_label(item)}"
    if sizing:
        title += f" | {sizing}"
    return [
        title,
        f"   {theme} | {flow} | {reason}",
        f"   执行质量：{execution_quality.get('label', '未评估')}({fmt_num(execution_quality.get('score'), 0)})",
        f"   做法：{action}",
        f"   触发：{trigger}",
        f"   取消：{invalidate}",
    ]


def build_brief_report(result):
    if has_valid_midday_verification(result):
        return build_midday_confirmation_brief(result)

    shortlist = sorted(result.get("shortlist") or [], key=shortlist_sort_key)
    primary = [item for item in shortlist if item.get("screening_status") == "approved" and item.get("tier") in {"A", "B"}][:3]

    used_codes = {item.get("code") for item in primary}
    watchlist = [
        item for item in shortlist
        if item.get("code") not in used_codes and (
            item.get("tier") == "B" or item.get("screening_status") == "caution"
        )
    ][:2]

    used_codes |= {item.get("code") for item in watchlist}
    avoid = [
        item for item in shortlist
        if item.get("code") not in used_codes and (
            item.get("screening_status") == "caution" or decision_label(item) == "别追"
        )
    ][:2]

    lines = []
    run_label = infer_run_label(result)
    scan_ts = effective_report_timestamp(result) or ""
    lines.append(f"{run_label} | {scan_ts}")
    first_line = market_line(result)
    second_line = theme_line(result)
    if second_line:
        lines.append(f"{first_line}{second_line}")
    else:
        lines.append(first_line)

    if primary:
        names = "、".join(item.get("name") for item in primary if item.get("name"))
        lines.append(f"先看 {names}。")
        lines.append("")
        lines.append("行动卡")
        for idx, item in enumerate(primary, start=1):
            lines.extend(render_mobile_stock(f"{idx}. ", item))

    if watchlist:
        lines.append("")
        lines.append("候补观察")
        for item in watchlist:
            lines.extend(render_mobile_stock("- ", item))

    if avoid:
        lines.append("")
        lines.append("今天别追")
        for item in avoid:
            lines.extend(render_mobile_stock("- ", item))

    if not primary and not watchlist:
        lines.append("")
        lines.append("今天没有明确可执行的新票，先观察主线延续。")

    midday_brief = render_midday_brief(result)
    if midday_brief:
        lines.append("")
        lines.append(midday_brief)

    return "\n".join(lines).strip() + "\n"


def build_full_report(result):
    if has_valid_midday_verification(result):
        return build_midday_confirmation_full_report(result)

    title = "进攻型午盘承接确认" if has_valid_midday_verification(result) else infer_run_label(result)
    report_timestamp = effective_report_timestamp(result) or result.get("timestamp", "")
    lines = [
        f"# {title} | {report_timestamp}",
        f"股票池：{result.get('pool_label', result.get('pool', '未知股票池'))}",
    ]

    source_scan_timestamp = result.get("source_scan_timestamp")
    if source_scan_timestamp:
        if has_valid_midday_verification(result):
            lines.append(f"晨间基线扫描：{source_scan_timestamp}")
            verification = result.get("midday_verification") or {}
            midday_scan_ts = verification.get("verified_against_scan_timestamp")
            if midday_scan_ts:
                lines.append(f"午盘确认扫描：{midday_scan_ts}")
        else:
            lines.append(f"扫描时间：{source_scan_timestamp}")

    sections = [
        render_market_regime(result),
        render_market_themes(result),
        render_screening_summary(result),
        render_shortlist(result),
        render_midday_verification(result),
        render_lifecycle(result),
        render_watchlist(result),
        render_strategy_views(result),
        render_analyzer_handoff(result),
    ]

    for section in sections:
        if section:
            lines.extend(["", section])

    return "\n".join(lines).strip() + "\n"


def parse_args():
    parser = argparse.ArgumentParser(description="根据二次筛选结果生成飞书/Markdown 报告")
    parser.add_argument("--input", default=str(DEFAULT_AI_RESULT_PATH), help="ai_screening.py 输出路径")
    parser.add_argument("--midday-input", default=str(DEFAULT_MIDDAY_RESULT_PATH), help="午盘确认结果路径")
    parser.add_argument("--lifecycle-input", help="候选生命周期 JSON 路径")
    parser.add_argument("--format", choices=["brief", "full"], default="full", help="输出格式：brief=手机摘要，full=完整报告")
    parser.add_argument("--output", help="写入 Markdown 文件；不传则打印到 stdout")
    return parser.parse_args()


def main():
    args = parse_args()
    input_path = Path(args.input).expanduser()

    with input_path.open("r", encoding="utf-8") as fh:
        ai_result = json.load(fh)

    midday_path = Path(args.midday_input).expanduser()
    if midday_path.exists():
        try:
            with midday_path.open("r", encoding="utf-8") as fh:
                midday_result = json.load(fh)
            if midday_matches_result(midday_result, ai_result):
                ai_result["midday_verification"] = midday_result
        except Exception:
            pass

    if args.lifecycle_input:
        lifecycle_path = Path(args.lifecycle_input).expanduser()
        if lifecycle_path.exists():
            try:
                with lifecycle_path.open("r", encoding="utf-8") as fh:
                    lifecycle_result = json.load(fh)
                if lifecycle_matches_result(lifecycle_result, ai_result):
                    ai_result["lifecycle"] = lifecycle_result
            except Exception:
                pass

    if args.format == "brief":
        report = build_brief_report(ai_result)
    else:
        report = build_full_report(ai_result)

    if args.output:
        output_path = Path(args.output).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
        print(f"Feishu message saved: {output_path}")
    else:
        print(report)


if __name__ == "__main__":
    main()
