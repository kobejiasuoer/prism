#!/usr/bin/env python3
"""
candidate_lifecycle.py — 候选生命周期管理 v1

比较当前 ai_screening_result.json / 最近扫描快照 vs 历史快照 + midday_verification，
识别 entered / upgraded / downgraded / exited / handed_off，输出 JSON + Markdown 报告。

用法:
    python3 candidate_lifecycle.py [--days-back 3] [--ai-input PATH] [--midday-input PATH] [--history-dir PATH] [--output-dir PATH]
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Optional

# ── tier ordering (higher = better) ──
TIER_ORDER = {"A": 3, "B": 2, "C": 1, "D": 0}
STATUS_ORDER = {"approved": 3, "caution": 2, "excluded": 1}


def parse_args():
    p = argparse.ArgumentParser(description="候选生命周期管理 v1")
    p.add_argument("--days-back", type=int, default=3, help="回溯天数（默认3）")
    p.add_argument("--ai-input", default=None, help="当前 ai_screening_result.json 路径")
    p.add_argument("--midday-input", default=None, help="midday_verification_result.json 路径")
    p.add_argument("--history-dir", default=None, help="raw scan history 快照目录")
    p.add_argument("--ai-history-dir", default=None, help="ai_screening 归档目录")
    p.add_argument("--output-dir", default=None, help="输出目录")
    p.add_argument("--output-json", default=None, help="显式指定 lifecycle JSON 输出路径")
    p.add_argument("--output-md", default=None, help="显式指定 lifecycle Markdown 输出路径")
    p.add_argument("--report-output", default=None, help="显式指定 reports 下 Markdown 输出路径")
    return p.parse_args()


def load_json(path: str) -> Optional[dict]:
    if not path or not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_timestamp(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None


def extract_shortlist(data: dict) -> dict[str, dict]:
    """Extract {code: stock_info} from ai_screening or history snapshot."""
    if not data:
        return {}

    stocks = {}

    # ai_screening_result.json format: .shortlist
    if "shortlist" in data:
        for s in data["shortlist"]:
            stocks[s["code"]] = {
                "code": s["code"],
                "name": s.get("name", ""),
                "score": s.get("best_score", s.get("score", 0)),
                "tier": s.get("tier", ""),
                "screening_status": s.get("screening_status", ""),
                "theme": s.get("themes", [""])[0] if isinstance(s.get("themes"), list) else s.get("theme", ""),
                "change_pct": s.get("change_pct", 0),
                "amount_yi": s.get("amount_yi", 0),
                "strategy_labels": s.get("strategy_labels", []),
                "consistency_score": s.get("consistency", {}).get("score", 0),
                "entry_reason": s.get("entry_reason", ""),
                "main_risk": s.get("main_risk", ""),
                "watch_condition": s.get("watch_condition", ""),
                "tushare_score": (s.get("tushare_factors") or {}).get("tushare_score"),
                "factor_tags": (s.get("tushare_factors") or {}).get("factor_tags") or [],
                "timestamp": data.get("timestamp", ""),
            }
        return stocks

    # history snapshot format: .strategies.combined is a list of stocks
    strategies = data.get("strategies", {})
    for strat_name, strat_stocks in strategies.items():
        if not isinstance(strat_stocks, list):
            strat_stocks = strat_stocks.get("selected_stocks", [])
        for s in strat_stocks:
            if not isinstance(s, dict):
                continue
            code = s.get("code")
            if not code or code in stocks:
                continue  # keep first occurrence (combined is typically first)
            stocks[code] = {
                "code": code,
                "name": s.get("name", ""),
                "score": s.get("score", 0),
                "tier": "",
                "screening_status": s.get("screening", {}).get("status", "") if isinstance(s.get("screening"), dict) else "",
                "theme": s.get("theme", ""),
                "change_pct": s.get("change_pct", 0),
                "amount_yi": s.get("amount_yi", 0),
                "strategy_labels": [strat_name],
                "consistency_score": s.get("consistency", {}).get("score", 0) if isinstance(s.get("consistency"), dict) else 0,
                "entry_reason": s.get("entry_reason", ""),
                "main_risk": s.get("main_risk", ""),
                "watch_condition": s.get("watch_condition", ""),
                "tushare_score": (s.get("tushare_factors") or {}).get("tushare_score"),
                "factor_tags": (s.get("tushare_factors") or {}).get("factor_tags") or [],
                "timestamp": data.get("timestamp", ""),
            }
    return stocks


def find_previous_snapshot(
    history_dir: str,
    current_timestamp: str = "",
    days_back: int = 1,
) -> tuple[dict[str, dict], str]:
    """Find the most recent snapshot before current_timestamp, preferring the recent lookback window."""
    if not history_dir or not os.path.isdir(history_dir):
        return {}, ""

    current_dt = None
    if current_timestamp:
        try:
            current_dt = datetime.strptime(current_timestamp, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            current_dt = None
    if current_dt is None:
        current_dt = datetime.now()

    window_start = current_dt - timedelta(days=days_back)
    recent_candidates = []
    fallback_candidates = []

    for fname in os.listdir(history_dir):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(history_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                d = json.load(f)
            ts = d.get("timestamp", "")
            if not ts:
                continue
            dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            if dt >= current_dt:
                continue
            row = (dt, d, fpath)
            fallback_candidates.append(row)
            if dt >= window_start:
                recent_candidates.append(row)
        except (json.JSONDecodeError, ValueError):
            continue

    candidates = recent_candidates or fallback_candidates
    if not candidates:
        return {}, ""

    candidates.sort(key=lambda x: x[0], reverse=True)
    dt, data, _ = candidates[0]
    return extract_shortlist(data), dt.strftime("%Y-%m-%d %H:%M:%S")


def find_previous_baseline(
    ai_history_dir: str,
    history_dir: str,
    current_timestamp: str = "",
    days_back: int = 1,
) -> tuple[dict[str, dict], str, str]:
    ai_previous, ai_previous_timestamp = find_previous_snapshot(
        ai_history_dir,
        current_timestamp=current_timestamp,
        days_back=days_back,
    )
    if ai_previous:
        return ai_previous, ai_previous_timestamp, "ai_screening_archive"

    raw_previous, raw_previous_timestamp = find_previous_snapshot(
        history_dir,
        current_timestamp=current_timestamp,
        days_back=days_back,
    )
    if raw_previous:
        return raw_previous, raw_previous_timestamp, "raw_scan_history"

    return {}, "", "none"


def _extract_midday_items(midday_data: dict, key: str) -> dict[str, dict]:
    if not midday_data:
        return {}

    out = {}
    for item in midday_data.get(key, []):
        if not isinstance(item, dict):
            continue
        code = item.get("code")
        if not code:
            continue
        out[code] = {
            "code": code,
            "name": item.get("name", ""),
            "tier": item.get("tier", ""),
            "morning_score": item.get("morning_score", 0),
            "status": item.get("status", ""),
            "reason": item.get("reason", ""),
            "details": item.get("details", []),
            "snapshot": item.get("snapshot", {}),
            "timestamp": midday_data.get("timestamp", ""),
        }
    return out


def midday_matches_ai(midday_data: dict, ai_data: dict) -> bool:
    if not midday_data or not ai_data:
        return False
    if midday_data.get("validation_status") != "ok":
        return False
    midday_ts = midday_data.get("source_morning_timestamp")
    midday_scan_ts = midday_data.get("source_scan_timestamp")
    verified_scan_ts = midday_data.get("verified_against_scan_timestamp")
    ai_ts = ai_data.get("timestamp")
    ai_scan_ts = ai_data.get("source_scan_timestamp")
    if not midday_ts or not ai_ts or midday_ts != ai_ts:
        return False
    if not midday_scan_ts or not ai_scan_ts or midday_scan_ts != ai_scan_ts:
        return False
    verified_dt = parse_timestamp(verified_scan_ts)
    ai_dt = parse_timestamp(ai_ts)
    if verified_dt and ai_dt and verified_dt.date() != ai_dt.date():
        return False
    return True


def extract_midday_handoffs(midday_data: dict) -> dict[str, dict]:
    """Extract confirmed items from midday verification as handoff candidates."""
    return _extract_midday_items(midday_data, "confirmed")


def extract_midday_downgrades(midday_data: dict) -> dict[str, dict]:
    """Extract downgraded items from midday verification, skipping malformed empty objects."""
    return _extract_midday_items(midday_data, "downgraded")


def compute_lifecycle(
    current: dict[str, dict],
    previous: dict[str, dict],
    midday_handoffs: dict[str, dict],
    midday_downgrades: dict[str, dict],
) -> dict:
    current_codes = set(current.keys())
    previous_codes = set(previous.keys())

    entered = []
    exited = []
    upgraded = []
    downgraded = []
    continued = []
    handed_off = []

    # Entered: in current but not in previous
    for code in sorted(current_codes - previous_codes):
        s = current[code]
        entered.append({
            "code": code,
            "name": s["name"],
            "tier": s["tier"],
            "screening_status": s["screening_status"],
            "score": s["score"],
            "theme": s["theme"],
            "change_pct": s["change_pct"],
            "entry_reason": s["entry_reason"],
            "main_risk": s["main_risk"],
        })

    # Exited: in previous but not in current
    for code in sorted(previous_codes - current_codes):
        s = previous[code]
        exited.append({
            "code": code,
            "name": s["name"],
            "tier": s["tier"],
            "screening_status": s["screening_status"],
            "score": s["score"],
            "theme": s["theme"],
            "last_seen": s.get("timestamp", ""),
        })

    # Upgraded / Downgraded: in both, compare tier and screening_status
    # Note: only meaningful when both sides have tier/status data (ai_screening format)
    # If previous comes from raw scan (history), tier/status will be empty
    for code in sorted(current_codes & previous_codes):
        curr = current[code]
        prev = previous[code]

        curr_tier_val = curr.get("tier", "")
        prev_tier_val = prev.get("tier", "")
        curr_status_val = curr.get("screening_status", "")
        prev_status_val = prev.get("screening_status", "")

        curr_tier = TIER_ORDER.get(curr_tier_val, 0)
        prev_tier = TIER_ORDER.get(prev_tier_val, 0)
        curr_status = STATUS_ORDER.get(curr_status_val, 0)
        prev_status = STATUS_ORDER.get(prev_status_val, 0)

        curr_score = curr.get("score", 0)
        prev_score = prev.get("score", 0)
        score_delta = round(curr_score - prev_score, 2)

        # Only detect tier/status upgrade/downgrade when both sides have data
        has_tier_data = prev_tier_val != "" and curr_tier_val != ""
        has_status_data = prev_status_val != "" and curr_status_val != ""

        is_upgrade = False
        is_downgrade = False

        if has_tier_data and curr_tier > prev_tier:
            is_upgrade = True
        elif has_tier_data and curr_tier < prev_tier:
            is_downgrade = True

        if has_status_data and curr_status > prev_status:
            is_upgrade = True
        elif has_status_data and curr_status < prev_status:
            is_downgrade = True

        # Score change as secondary signal (±15 points) when no tier/status change
        if not is_upgrade and not is_downgrade and abs(score_delta) >= 15:
            if score_delta > 0:
                is_upgrade = True
            else:
                is_downgrade = True

        detail = {
            "code": code,
            "name": curr["name"],
            "prev_tier": prev.get("tier", ""),
            "curr_tier": curr.get("tier", ""),
            "prev_screening_status": prev.get("screening_status", ""),
            "curr_screening_status": curr.get("screening_status", ""),
            "prev_score": prev_score,
            "curr_score": curr_score,
            "score_delta": round(score_delta, 2),
            "theme": curr["theme"],
        }

        if is_upgrade:
            upgraded.append(detail)
        elif is_downgrade:
            downgraded.append(detail)
        else:
            continued.append(
                {
                    **detail,
                    "tier": curr.get("tier", ""),
                    "screening_status": curr.get("screening_status", ""),
                    "score": curr_score,
                    "persistence_label": "非一日脉冲",
                    "reason": "连续两轮仍在候选池，先按延续观察处理",
                }
            )

    # Midday downgraded: supplement downgrade funnel (and avoid malformed empty objects)
    downgraded_codes = {item["code"] for item in downgraded}
    for code in sorted(midday_downgrades.keys()):
        if code in downgraded_codes:
            continue
        d = midday_downgrades[code]
        in_current = code in current_codes
        current_info = current.get(code, {})
        downgraded.append({
            "code": code,
            "name": d["name"],
            "prev_tier": d.get("tier", ""),
            "curr_tier": current_info.get("tier", ""),
            "prev_screening_status": "midday_watch",
            "curr_screening_status": current_info.get("screening_status", "") if in_current else "",
            "prev_score": d.get("morning_score", 0),
            "curr_score": current_info.get("score", d.get("morning_score", 0)) if in_current else d.get("morning_score", 0),
            "score_delta": round((current_info.get("score", d.get("morning_score", 0)) if in_current else d.get("morning_score", 0)) - d.get("morning_score", 0), 2),
            "theme": current_info.get("theme", ""),
            "reason": d.get("reason", ""),
            "source": "midday_verification",
        })

    # Handed off: confirmed in midday verification
    for code in sorted(midday_handoffs.keys()):
        h = midday_handoffs[code]
        in_current = code in current_codes
        handed_off.append({
            "code": code,
            "name": h["name"],
            "tier": h["tier"],
            "morning_score": h["morning_score"],
            "status": h["status"],
            "reason": h["reason"],
            "in_current_shortlist": in_current,
            "current_tier": current[code]["tier"] if in_current else "N/A",
            "current_screening_status": current[code]["screening_status"] if in_current else "N/A",
        })

    return {
        "entered": entered,
        "upgraded": upgraded,
        "downgraded": downgraded,
        "continued": continued,
        "exited": exited,
        "handed_off": handed_off,
        "summary": {
            "entered_count": len(entered),
            "upgraded_count": len(upgraded),
            "downgraded_count": len(downgraded),
            "continued_count": len(continued),
            "exited_count": len(exited),
            "handed_off_count": len(handed_off),
            "current_pool_size": len(current_codes),
            "previous_pool_size": len(previous_codes),
        },
    }


def generate_markdown(lifecycle: dict, now_str: str) -> str:
    lines = []
    s = lifecycle["summary"]
    lines.append(f"# 候选生命周期报告 | {now_str}")
    lines.append("")
    lines.append(f"当前候选池：**{s['current_pool_size']}** 只 | 前次候选池：**{s['previous_pool_size']}** 只")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Summary bar
    lines.append("## 变动总览")
    lines.append("")
    lines.append(f"| 状态 | 数量 |")
    lines.append(f"|------|------|")
    lines.append(f"| 🆕 新入选 | {s['entered_count']} |")
    lines.append(f"| ⬆️ 升级 | {s['upgraded_count']} |")
    lines.append(f"| ⬇️ 降级 | {s['downgraded_count']} |")
    lines.append(f"| ✅ 非一日脉冲 | {s.get('continued_count', 0)} |")
    lines.append(f"| 🚪 退出 | {s['exited_count']} |")
    lines.append(f"| 🔄 已移交 analyzer | {s['handed_off_count']} |")
    lines.append("")

    # Entered
    if lifecycle["entered"]:
        lines.append("## 🆕 新入选 (entered)")
        lines.append("")
        for e in lifecycle["entered"]:
            lines.append(f"- **{e['name']}({e['code']})** | Tier {e['tier']} | {e['screening_status']} | 评分 {e['score']} | 涨幅 {e['change_pct']}% | {e['theme']}")
            if e.get("entry_reason"):
                lines.append(f"  - 入选理由：{e['entry_reason']}")
            if e.get("main_risk"):
                lines.append(f"  - 风险：{e['main_risk']}")
        lines.append("")

    # Upgraded
    if lifecycle["upgraded"]:
        lines.append("## ⬆️ 升级 (upgraded)")
        lines.append("")
        for u in lifecycle["upgraded"]:
            prev_label = f"Tier {u['prev_tier']}/{u['prev_screening_status']}"
            curr_label = f"Tier {u['curr_tier']}/{u['curr_screening_status']}"
            delta = u["score_delta"]
            delta_str = f"+{delta}" if delta > 0 else str(delta)
            lines.append(f"- **{u['name']}({u['code']})** | {prev_label} → {curr_label} | 评分 {u['prev_score']}→{u['curr_score']} ({delta_str}) | {u['theme']}")
        lines.append("")

    # Downgraded
    if lifecycle["downgraded"]:
        lines.append("## ⬇️ 降级 (downgraded)")
        lines.append("")
        for d in lifecycle["downgraded"]:
            prev_label = f"Tier {d['prev_tier']}/{d['prev_screening_status']}"
            curr_label = f"Tier {d['curr_tier']}/{d['curr_screening_status']}"
            delta = d["score_delta"]
            delta_str = f"+{delta}" if delta > 0 else str(delta)
            suffix = f" | {d.get('theme', '')}" if d.get("theme") else ""
            lines.append(f"- **{d['name']}({d['code']})** | {prev_label} → {curr_label} | 评分 {d['prev_score']}→{d['curr_score']} ({delta_str}){suffix}")
            if d.get("reason"):
                lines.append(f"  - 降级原因：{d['reason']}")
            if d.get("source") == "midday_verification":
                lines.append("  - 来源：盘中验证")
        lines.append("")

    # Continued
    if lifecycle.get("continued"):
        lines.append("## ✅ 非一日脉冲 (continued)")
        lines.append("")
        for c in lifecycle["continued"]:
            delta = c["score_delta"]
            delta_str = f"+{delta}" if delta > 0 else str(delta)
            lines.append(
                f"- **{c['name']}({c['code']})** | Tier {c.get('tier', '')}/{c.get('screening_status', '')} | "
                f"评分 {c['prev_score']}→{c['curr_score']} ({delta_str}) | {c.get('theme', '')}"
            )
        lines.append("")

    # Exited
    if lifecycle["exited"]:
        lines.append("## 🚪 退出 (exited)")
        lines.append("")
        for e in lifecycle["exited"]:
            lines.append(f"- **{e['name']}({e['code']})** | Tier {e['tier']} | {e['screening_status']} | 评分 {e['score']} | {e['theme']}")
            if e.get("last_seen"):
                lines.append(f"  - 最后出现：{e['last_seen']}")
        lines.append("")

    # Handed off
    if lifecycle["handed_off"]:
        lines.append("## 🔄 已移交 analyzer (handed_off)")
        lines.append("")
        for h in lifecycle["handed_off"]:
            current_info = f"当前 Tier {h['current_tier']}/{h['current_screening_status']}" if h.get("in_current_shortlist") else "已不在当前候选池"
            lines.append(f"- **{h['name']}({h['code']})** | 盘中确认 {h['status']} | 早盘评分 {h['morning_score']} | {current_info}")
            if h.get("reason"):
                lines.append(f"  - 确认理由：{h['reason']}")
        lines.append("")

    if not any(lifecycle.get(k) for k in ["entered", "upgraded", "downgraded", "continued", "exited", "handed_off"]):
        lines.append("## 无变动")
        lines.append("")
        lines.append("与上一期候选池相比，未检测到状态变化。")

    return "\n".join(lines)


def main():
    args = parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.dirname(script_dir)

    ai_input = args.ai_input or os.path.join(base_dir, "data", "ai_screening_result.json")
    midday_input = args.midday_input or os.path.join(base_dir, "data", "midday_verification_result.json")
    history_dir = args.history_dir or os.path.join(base_dir, "data", "history")
    ai_history_dir = args.ai_history_dir or os.path.join(base_dir, "data", "ai_history")
    output_dir = args.output_dir or os.path.join(base_dir, "data")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    run_stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")

    # Load data
    ai_data = load_json(ai_input)
    midday_data = load_json(midday_input)

    if not ai_data:
        print(f"ERROR: 无法加载当前 ai_screening_result: {ai_input}", file=sys.stderr)
        sys.exit(1)

    current = extract_shortlist(ai_data)
    previous, previous_timestamp, prev_source = find_previous_baseline(
        ai_history_dir,
        history_dir,
        current_timestamp=ai_data.get("timestamp", ""),
        days_back=args.days_back,
    )
    midday_matched = midday_matches_ai(midday_data, ai_data)
    midday_handoffs = extract_midday_handoffs(midday_data) if midday_matched else {}
    midday_downgrades = extract_midday_downgrades(midday_data) if midday_matched else {}

    # Compute lifecycle
    lifecycle = compute_lifecycle(current, previous, midday_handoffs, midday_downgrades)
    lifecycle["metadata"] = {
        "generated_at": now_str,
        "current_timestamp": ai_data.get("timestamp", ""),
        "previous_snapshot_source": prev_source,
        "previous_snapshot_timestamp": previous_timestamp or "N/A",
        "previous_pool_size": len(previous),
        "midday_verification_timestamp": midday_data.get("timestamp", "") if midday_data else "N/A",
        "midday_validation_status": midday_data.get("validation_status", "missing") if midday_data else "missing",
        "midday_matches_current_ai": midday_matched,
        "midday_downgraded_count": len(midday_downgrades),
        "ai_input": ai_input,
        "ai_history_dir": ai_history_dir,
        "midday_input": midday_input,
    }

    # Output JSON
    json_path = args.output_json or os.path.join(output_dir, f"lifecycle_{run_stamp}.json")
    md_path = args.output_md or os.path.join(output_dir, f"lifecycle_{run_stamp}.md")

    reports_dir = os.path.join(base_dir, "reports")
    report_md_path = args.report_output or os.path.join(reports_dir, f"lifecycle_{run_stamp}.md")

    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(lifecycle, f, ensure_ascii=False, indent=2)

    # Output Markdown
    md_content = generate_markdown(lifecycle, now_str)
    os.makedirs(os.path.dirname(md_path), exist_ok=True)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    # Also copy to reports dir
    os.makedirs(os.path.dirname(report_md_path), exist_ok=True)
    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    # Print summary
    s = lifecycle["summary"]
    print(f"=== 候选生命周期 v1 | {now_str} ===")
    print(f"当前候选池: {s['current_pool_size']} | 前次: {s['previous_pool_size']}")
    print(f"  🆕 entered:    {s['entered_count']}")
    print(f"  ⬆️ upgraded:   {s['upgraded_count']}")
    print(f"  ⬇️ downgraded: {s['downgraded_count']}")
    print(f"  ✅ continued:  {s.get('continued_count', 0)}")
    print(f"  🚪 exited:     {s['exited_count']}")
    print(f"  🔄 handed_off: {s['handed_off_count']}")
    print(f"")
    print(f"JSON  -> {json_path}")
    print(f"MD    -> {md_path}")
    print(f"Report -> {report_md_path}")

    return lifecycle


if __name__ == "__main__":
    main()
