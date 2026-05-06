from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .config import load_quant_research_config
from .research_io import (
    BACKTEST_REPORT_PATH,
    HARDENED_LABEL_PATH,
    fmt,
    hardened_label_summary,
    join_panel_labels,
    max_drawdown,
    pct,
    status_for_sample,
    summary_stats,
)


STRATEGIES = ["top_n_raw_score", "gate_filtered_top_n"]
ENTRY_MODELS = ["next_open", "next_close"]
RESEARCH_ONLY_BACKTEST_FLAGS = [
    "research_only_simulation",
    "benchmark_unavailable",
    "adjustment_policy_unknown",
    "suspend_status_unknown",
    "limit_up_down_status_unknown",
    "failed_order_unavailable",
    "partial_fill_unavailable",
    "not_production_sorting",
]


def now_stamp() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


def scan_rows_for_backtest() -> list[dict[str, Any]]:
    rows = []
    for item in join_panel_labels(available_only=True):
        panel = item["panel"]
        label = item["label"]
        if panel.get("source_lane") != "research_backfill_scan_history":
            continue
        if panel.get("pipeline_stage") != "scan_candidate":
            continue
        if panel.get("score") is None:
            continue
        if panel.get("score_kind") != "raw_scan_composite_score":
            continue
        rows.append(item)
    return rows


def selected_positions(
    items: list[dict[str, Any]],
    *,
    strategy: str,
    max_positions: int,
) -> list[dict[str, Any]]:
    if strategy == "gate_filtered_top_n":
        gate = first_gate_status(items)
        if gate == "off":
            return []
        if gate == "limited":
            max_positions = max(1, min(max_positions, max_positions // 2))
    return sorted(items, key=lambda item: float(item["panel"].get("score") or 0), reverse=True)[:max_positions]


def first_gate_status(items: list[dict[str, Any]]) -> str | None:
    for item in items:
        if item["panel"].get("execution_gate_scope") != "batch_context":
            continue
        status = item["panel"].get("execution_gate_status")
        if status:
            return status
    return None


def portfolio_win_rate(daily_rows: list[dict[str, Any]]) -> dict[str, Any]:
    invested_rows = [row for row in daily_rows if row["positions"] > 0]
    if not invested_rows:
        return {
            "status": "unavailable",
            "value": None,
            "sample_size": 0,
            "basis": "invested_rebalance_day_net_return_after_costs",
            "unavailable_reason": "no simulated invested portfolio days",
        }
    wins = sum(1 for row in invested_rows if row["net_return"] > 0)
    return {
        "status": status_for_sample(len(invested_rows)),
        "value": wins / len(invested_rows),
        "sample_size": len(invested_rows),
        "basis": "invested_rebalance_day_net_return_after_costs",
        "notes": "research_only_simulation; zero-position gate-off days are excluded",
    }


def portfolio_series(
    rows: list[dict[str, Any]],
    *,
    strategy: str,
    entry_model: str,
    window: int,
    max_positions: int,
    single_position_weight: float,
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in rows:
        label = item["label"]
        if label.get("entry_model") != entry_model or int(label.get("holding_window_days") or 0) != window:
            continue
        grouped[label["trade_date"]].append(item)

    daily_rows = []
    previous_codes: set[str] = set()
    for trade_date in sorted(grouped):
        positions = selected_positions(grouped[trade_date], strategy=strategy, max_positions=max_positions)
        codes = {item["panel"]["code"] for item in positions}
        gross = sum(float(item["label"]["raw_return"]) * single_position_weight for item in positions)
        net = sum(float(item["label"]["net_return"]) * single_position_weight for item in positions)
        cost_paid = max(0.0, gross - net)
        target_weight = len(positions) * single_position_weight
        new_weight = len(codes - previous_codes) * single_position_weight
        turnover = new_weight
        previous_codes = codes
        daily_rows.append(
            {
                "trade_date": trade_date,
                "positions": len(positions),
                "target_weight": round(target_weight, 6),
                "raw_return": round(gross, 8),
                "net_return": round(net, 8),
                "cost_paid": round(cost_paid, 8),
                "turnover": round(turnover, 6),
                "gate_status": first_gate_status(grouped[trade_date]),
            }
        )

    net_returns = [row["net_return"] for row in daily_rows]
    raw_returns = [row["raw_return"] for row in daily_rows]
    net_summary = summary_stats(net_returns)
    raw_summary = summary_stats(raw_returns)
    cost_paid = [row["cost_paid"] for row in daily_rows]
    positions = [row["positions"] for row in daily_rows]
    turnover = [row["turnover"] for row in daily_rows]
    sample_size = sum(row["positions"] for row in daily_rows)
    status = status_for_sample(sample_size)
    return {
        "strategy": strategy,
        "entry_model": entry_model,
        "holding_window_days": window,
        "trade_days": len(daily_rows),
        "position_observations": sample_size,
        "status": status,
        "research_only_flags": list(RESEARCH_ONLY_BACKTEST_FLAGS),
        "return": raw_summary,
        "net_return": net_summary,
        "portfolio_win_rate": portfolio_win_rate(daily_rows),
        "drawdown": max_drawdown(net_returns),
        "turnover": summary_stats(turnover),
        "positions": summary_stats(positions),
        "cost_paid": summary_stats(cost_paid),
        "daily_rows_preview": daily_rows[:5],
    }


def run_backtest() -> dict[str, Any]:
    config = load_quant_research_config().data
    hardening = hardened_label_summary()
    max_positions = int(config["portfolio"]["max_positions"])
    single_position_weight = float(config["portfolio"]["max_single_position_pct"]) / 100.0
    windows = [int(value) for value in config["holding_windows"]]
    rows = scan_rows_for_backtest()
    results = []
    for strategy in STRATEGIES:
        for entry_model in ENTRY_MODELS:
            for window in windows:
                results.append(
                    portfolio_series(
                        rows,
                        strategy=strategy,
                        entry_model=entry_model,
                        window=window,
                        max_positions=max_positions,
                        single_position_weight=single_position_weight,
                    )
                )
    gate_counts = Counter(
        item["panel"].get("execution_gate_status")
        for item in rows
        if item["panel"].get("execution_gate_scope") == "batch_context"
    )
    return {
        "generated_at": now_stamp(),
        "scope": "Sprint 2 report-only minimal backtest",
        "hardened_label_input": {
            "path": str(HARDENED_LABEL_PATH),
            "rows": hardening["rows"],
            "formal_label_ready_count": hardening["formal_label_ready_count"],
            "formal_execution_eligible_count": hardening["formal_execution_eligible_count"],
        },
        "hardened_label_summary": hardening,
        "input_rows": len(rows),
        "strategies": STRATEGIES,
        "entry_models": ENTRY_MODELS,
        "holding_windows": windows,
        "max_positions": max_positions,
        "max_single_position_pct": config["portfolio"]["max_single_position_pct"],
        "transaction_cost": config["transaction_cost"],
        "results": results,
        "gate_counts": dict(gate_counts),
        "guardrails": [
            "report_only",
            "research_only_simulation",
            "available_research_only_labels",
            "no_excess_return",
            "no_execution_realistic_fill",
            "hardened_labels_report_only_sidecar",
            "no_production_sorting",
        ],
    }


def render_backtest_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Prism Quant Sprint 2 Minimal Portfolio Backtest",
        "",
        f"Generated at: {result['generated_at']}",
        "",
        "Scope: report-only minimal backtest. This is not an execution-realistic backtest and does not change production sorting.",
        "",
        "## Inputs",
        "",
        f"- Hardened labels input: `{result['hardened_label_input']['path']}`.",
        f"- Hardened labels count: {result['hardened_label_input']['rows']}.",
        f"- Hardened formal_label_ready count: {result['hardened_label_input']['formal_label_ready_count']}.",
        f"- Hardened formal_execution_eligible count: {result['hardened_label_input']['formal_execution_eligible_count']}.",
        f"- Input scan label rows: {result['input_rows']}.",
        f"- Strategies: {', '.join(f'`{item}`' for item in result['strategies'])}.",
        f"- Entry models: {', '.join(f'`{item}`' for item in result['entry_models'])}.",
        f"- Holding windows: {result['holding_windows']}.",
        f"- Max positions: {result['max_positions']}; max single position: {result['max_single_position_pct']}%.",
        f"- Transaction cost config: {result['transaction_cost']}.",
        f"- Gate counts in input rows: {result['gate_counts']}.",
        "- Portfolio win rate basis: invested rebalance days with positions > 0 and net portfolio return after costs > 0; zero-position gate-off days are excluded.",
        "",
        "## Hardened Label Limitations",
        "",
        f"- Benchmark status distribution: {result['hardened_label_summary']['benchmark_status_counts']}.",
        f"- Excess return status distribution: {result['hardened_label_summary']['excess_return_status_counts']}.",
        f"- Internal benchmark status distribution: {result['hardened_label_summary']['internal_benchmark_status_counts']}.",
        f"- Price adjustment status distribution: {result['hardened_label_summary']['price_adjustment_status_counts']}.",
        f"- Execution realism status distribution: {result['hardened_label_summary']['execution_realism_status_counts']}.",
        f"- Research-only reason distribution: {result['hardened_label_summary']['research_only_reason_counts']}.",
        "- No sample with `formal_label_ready=false` is used to claim a formal or execution-realistic backtest.",
        "",
        "## Results",
        "",
        "| Strategy | Entry | Window | Trade days | Positions | Status | Raw mean | Net mean | Portfolio win rate | Drawdown | Avg turnover | Avg cost paid | Flags |",
        "| --- | --- | ---: | ---: | ---: | --- | ---: | ---: | --- | ---: | ---: | ---: | --- |",
    ]
    for row in result["results"]:
        win_rate = row["portfolio_win_rate"]
        lines.append(
            f"| `{row['strategy']}` | `{row['entry_model']}` | {row['holding_window_days']} | {row['trade_days']} | "
            f"{row['position_observations']} | {row['status']} | {pct(row['return']['mean'])} | {pct(row['net_return']['mean'])} | "
            f"{format_win_rate(win_rate)} | {pct(row['drawdown'])} | "
            f"{fmt(row['turnover']['mean'])} | {pct(row['cost_paid']['mean'])} | {', '.join(row['research_only_flags'][:3])} |"
        )
    lines += [
        "",
        "## Conservative Interpretation",
        "",
        "- Every result is `research_only_simulation` because suspend, limit up/down, failed order, partial fill, and adjustment data are unavailable.",
        "- Benchmark data is unavailable, so no excess return is calculated or claimed.",
        "- `gate_filtered_top_n` uses `execution_gate_status` only as batch/context. Gate off opens no new simulated positions; gate limited halves the max positions.",
        "- Turnover is an approximate daily one-way new-weight measure, not a broker execution ledger.",
        "",
        "## Guardrails",
        "",
        "- Do not use these results to alter production sorting or A/B/C tiers.",
        "- Do not describe this as deployable or execution-realistic.",
        "- Buckets below 30 position observations are `insufficient_sample`.",
    ]
    return "\n".join(lines) + "\n"


def format_win_rate(win_rate: dict[str, Any]) -> str:
    if win_rate.get("value") is None:
        reason = win_rate.get("unavailable_reason") or "insufficient portfolio observations"
        return f"unavailable ({reason})"
    return f"{pct(win_rate['value'])} (n={win_rate['sample_size']}, {win_rate['status']})"


def write_backtest_report(path: Path = BACKTEST_REPORT_PATH) -> dict[str, Any]:
    result = run_backtest()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_backtest_markdown(result), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Sprint 2 report-only minimal portfolio backtest.")
    parser.add_argument("--output", type=Path, default=BACKTEST_REPORT_PATH)
    args = parser.parse_args()
    result = write_backtest_report(args.output)
    print(json.dumps({"output": str(args.output), "results": len(result["results"])}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
