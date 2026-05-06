from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .evaluate_factors import build_factor_evaluation
from .research_io import (
    HARDENED_LABEL_PATH,
    LABEL_PATH,
    PANEL_PATH,
    QUANT_HEALTH_JSON_PATH,
    QUANT_HEALTH_MD_PATH,
    hardened_label_summary,
    load_jsonl,
    pct,
    write_json,
)
from .run_portfolio_backtest import run_backtest


def now_stamp() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


def panel_coverage() -> dict[str, Any]:
    rows = load_jsonl(PANEL_PATH)
    pit = Counter(row.get("pit_check_status") for row in rows)
    pit_pass = pit.get("pass", 0)
    required = [
        "panel_row_id",
        "trade_date",
        "code",
        "source_lane",
        "source_artifact",
        "source_hash",
        "pipeline_stage",
        "available_timestamp",
        "decision_timestamp",
    ]
    missing = {field: sum(1 for row in rows if row.get(field) in (None, "", [], {})) for field in required}
    return {
        "rows": len(rows),
        "pit_status": dict(pit),
        "pit_pass_rate": pit_pass / len(rows) if rows else 0,
        "missing_required_fields": missing,
        "status": "pass" if rows and pit_pass == len(rows) and all(value == 0 for value in missing.values()) else "research_only",
    }


def label_coverage() -> dict[str, Any]:
    labels = load_jsonl(LABEL_PATH)
    hardening = hardened_label_summary()
    status_counts = Counter(label.get("label_status") for label in labels)
    benchmark_counts = Counter(label.get("benchmark_status") for label in labels)
    excess_counts = Counter(label.get("excess_return_status") for label in labels)
    execution_missing = Counter(flag for label in labels for flag in label.get("execution_data_missing") or [])
    available = status_counts.get("available_research_only", 0)
    return {
        "rows": len(labels),
        "status_counts": dict(status_counts),
        "available_rate": available / len(labels) if labels else 0,
        "benchmark_availability": dict(benchmark_counts),
        "excess_return_status": dict(excess_counts),
        "execution_data_missing": dict(execution_missing),
        "hardened_label_input": {
            "path": str(HARDENED_LABEL_PATH),
            "rows": hardening["rows"],
            "formal_label_ready_count": hardening["formal_label_ready_count"],
            "formal_execution_eligible_count": hardening["formal_execution_eligible_count"],
        },
        "hardened_label_summary": hardening,
        "status": "research_only",
    }


def factor_status(factor_result: dict[str, Any]) -> dict[str, Any]:
    numeric = {
        item["field"]: item["status"]
        for item in factor_result.get("formal_numeric_factors", [])
    }
    groups = {
        item["field"]: item["status"]
        for item in factor_result.get("formal_group_factors", [])
    }
    return {
        "numeric": numeric,
        "groups": groups,
        "tier_monotonicity": factor_result.get("tier_monotonicity", {}).get("status"),
        "gate_evaluation": groups.get("execution_gate_status"),
        "ai_screening_validation": factor_result.get("ai_screening_validation", {}).get("status"),
        "midday_validation": factor_result.get("midday_validation", {}).get("status"),
        "status": "research_only",
    }


def backtest_status(backtest_result: dict[str, Any]) -> dict[str, Any]:
    statuses = Counter(row.get("status") for row in backtest_result.get("results", []))
    research_only_flags = Counter(flag for row in backtest_result.get("results", []) for flag in row.get("research_only_flags", []))
    win_rate_statuses = Counter(
        (row.get("portfolio_win_rate") or {}).get("status", "unavailable")
        for row in backtest_result.get("results", [])
    )
    return {
        "result_status_counts": dict(statuses),
        "research_only_flags": dict(research_only_flags),
        "portfolio_win_rate_status_counts": dict(win_rate_statuses),
        "status": "research_only_simulation",
    }


def build_quant_health() -> dict[str, Any]:
    factors = build_factor_evaluation()
    backtest = run_backtest()
    panel = panel_coverage()
    labels = label_coverage()
    hardening = labels["hardened_label_summary"]
    return {
        "schema_version": "1.0",
        "generated_at": now_stamp(),
        "scope": "Sprint 2 report-only quant health using P1-A hardened label sidecar",
        "overall_status": "report_only_hardened_not_production_ready",
        "production_impact": "none",
        "panel_coverage": panel,
        "label_coverage": labels,
        "pit_pass_rate": panel["pit_pass_rate"],
        "hardened_label_input": labels["hardened_label_input"],
        "hardened_label_summary": hardening,
        "benchmark_availability": hardening["benchmark_status_counts"],
        "source_label_benchmark_availability": labels["benchmark_availability"],
        "excess_return_availability": hardening["excess_return_status_counts"],
        "adjusted_return_availability": {
            "status": "not_ready",
            "formal_adjusted_return_status": hardening["formal_adjusted_return_status_counts"],
            "price_adjustment_status": hardening["price_adjustment_status_counts"],
        },
        "execution_data_availability": {
            "status": "missing_for_execution_realistic_backtest",
            "missing": labels["execution_data_missing"],
        },
        "execution_realism_availability": {
            "status": "not_ready",
            "execution_realism_status": hardening["execution_realism_status_counts"],
            "formal_execution_eligible_count": hardening["formal_execution_eligible_count"],
        },
        "factor_evidence_status": factor_status(factors),
        "tier_monotonicity_status": factors.get("tier_monotonicity", {}).get("status"),
        "gate_evaluation_status": factor_status(factors).get("gate_evaluation"),
        "backtest_research_only_status": backtest_status(backtest),
        "hard_gates": {
            "blocks_production": False,
            "blocks_sorting": False,
            "replaces_abc": False,
            "requires_page_change": False,
            "production_ready": False,
        },
        "guardrails": [
            "report_only",
            "hardened_labels_sidecar",
            "no_production_sorting",
            "no_abc_replacement",
            "no_page",
            "no_prism_edge",
            "no_ml",
            "no_theme_state_machine",
        ],
    }


def render_health_markdown(health: dict[str, Any]) -> str:
    panel = health["panel_coverage"]
    labels = health["label_coverage"]
    factor = health["factor_evidence_status"]
    backtest = health["backtest_research_only_status"]
    lines = [
        "# Prism Quant Sprint 2 Quant Health",
        "",
        f"Generated at: {health['generated_at']}",
        "",
        "Scope: report-only quant health. This report does not block or alter production.",
        "",
        "## Summary",
        "",
        f"- Overall status: `{health['overall_status']}`.",
        f"- Production impact: `{health['production_impact']}`.",
        f"- PIT pass rate: {pct(health['pit_pass_rate'])}.",
        f"- Panel rows: {panel['rows']}; label rows: {labels['rows']}.",
        f"- Hardened labels input: `{health['hardened_label_input']['path']}`.",
        f"- Hardened labels count: {health['hardened_label_input']['rows']}.",
        f"- Hardened formal_label_ready count: {health['hardened_label_input']['formal_label_ready_count']}.",
        f"- Hardened formal_execution_eligible count: {health['hardened_label_input']['formal_execution_eligible_count']}.",
        f"- Available label rate: {pct(labels['available_rate'])}.",
        "",
        "## Availability",
        "",
        f"- Benchmark availability: {health['benchmark_availability']}.",
        f"- Source label benchmark availability: {health['source_label_benchmark_availability']}.",
        f"- Excess return availability: {health['excess_return_availability']}.",
        f"- Adjusted return availability: {health['adjusted_return_availability']}.",
        f"- Execution data availability: {health['execution_data_availability']['status']}.",
        f"- Execution realism availability: {health['execution_realism_availability']}.",
        f"- Execution missing flags: {health['execution_data_availability']['missing']}.",
        "",
        "## Hardened Label Status",
        "",
        f"- Price adjustment status: {health['hardened_label_summary']['price_adjustment_status_counts']}.",
        f"- Formal adjusted return status: {health['hardened_label_summary']['formal_adjusted_return_status_counts']}.",
        f"- Execution realism status: {health['hardened_label_summary']['execution_realism_status_counts']}.",
        f"- Research-only reasons: {health['hardened_label_summary']['research_only_reason_counts']}.",
        "",
        "## Evidence Status",
        "",
        f"- Numeric factor statuses: {factor['numeric']}.",
        f"- Group factor statuses: {factor['groups']}.",
        f"- Tier monotonicity status: `{health['tier_monotonicity_status']}`.",
        f"- Gate evaluation status: `{health['gate_evaluation_status']}`.",
        f"- Backtest status: `{backtest['status']}`.",
        f"- Backtest result status counts: {backtest['result_status_counts']}.",
        f"- Portfolio win-rate status counts: {backtest['portfolio_win_rate_status_counts']}.",
        "",
        "## Report-Only Gates",
        "",
        "- Production blocking: false.",
        "- Sorting impact: false.",
        "- A/B/C replacement: false.",
        "- Page requirement: false.",
        "",
        "## Guardrails",
        "",
        "- No production sorting changes.",
        "- No A/B/C replacement.",
        "- No page, Prism Edge, Expected 5D frontend, theme state machine, or ML work.",
    ]
    return "\n".join(lines) + "\n"


def write_quant_health_reports(
    json_path: Path = QUANT_HEALTH_JSON_PATH,
    md_path: Path = QUANT_HEALTH_MD_PATH,
) -> dict[str, Any]:
    health = build_quant_health()
    write_json(json_path, health)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_health_markdown(health), encoding="utf-8")
    return health


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Sprint 2 report-only quant health reports.")
    parser.add_argument("--json-output", type=Path, default=QUANT_HEALTH_JSON_PATH)
    parser.add_argument("--md-output", type=Path, default=QUANT_HEALTH_MD_PATH)
    args = parser.parse_args()
    health = write_quant_health_reports(args.json_output, args.md_output)
    print(json.dumps({"json": str(args.json_output), "md": str(args.md_output), "status": health["overall_status"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
