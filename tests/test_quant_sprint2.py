from __future__ import annotations

import json
from pathlib import Path

from quant.evaluate_factors import build_factor_evaluation
from quant.report_quant_health import build_quant_health
from quant.run_portfolio_backtest import run_backtest


PANEL_PATH = Path("data/quant/panels/daily_signal_panel.jsonl")
LABEL_PATH = Path("data/quant/labels/forward_return_labels.jsonl")
FACTOR_REPORT = Path("data/quant/reports/factor_evaluation_latest.md")
BACKTEST_REPORT = Path("data/quant/reports/portfolio_backtest_latest.md")
HEALTH_JSON = Path("data/quant/reports/quant_health_latest.json")


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_final_score_is_not_evaluated() -> None:
    result = build_factor_evaluation()
    evaluated = {item["field"] for item in result["formal_numeric_factors"]}
    evaluated |= {item["field"] for item in result["formal_group_factors"]}
    assert "final_score" not in evaluated
    assert "final_score" in result["excluded_fields"]
    assert "strategy_bucket" in result["excluded_fields"]


def test_score_is_not_merged_across_lanes() -> None:
    result = build_factor_evaluation()
    formal = {item["field"] for item in result["formal_numeric_factors"]}
    assert "score" not in formal
    assert "score" in result["raw_source_fields"]
    panel = load_jsonl(PANEL_PATH)
    assert all(
        row.get("score_kind") and row.get("score_source_lane") == row.get("source_lane")
        for row in panel
        if row.get("score") is not None
    )


def test_gate_uses_batch_context_only() -> None:
    panel = load_jsonl(PANEL_PATH)
    gated = [row for row in panel if row.get("execution_gate_status")]
    assert gated
    assert all(row.get("execution_gate_scope") == "batch_context" for row in gated)
    result = build_factor_evaluation()
    gate = next(item for item in result["formal_group_factors"] if item["field"] == "execution_gate_status")
    assert "Batch/context" in gate["note"]


def test_benchmark_unavailable_means_no_excess_return() -> None:
    labels = load_jsonl(LABEL_PATH)
    assert labels
    assert all(label["benchmark_status"] == "benchmark_unavailable" for label in labels)
    assert all(label["excess_return_status"] == "deferred_until_benchmark_frozen" for label in labels)
    assert all("excess_return" not in label for label in labels)
    health = build_quant_health()
    assert health["source_label_benchmark_availability"] == {"benchmark_unavailable": len(labels)}
    assert health["excess_return_availability"] == {"unavailable_market_benchmark_not_frozen": len(labels)}


def test_execution_missing_forces_research_only_backtest() -> None:
    result = run_backtest()
    assert result["results"]
    for row in result["results"]:
        assert row["status"] in {"research_only", "insufficient_sample"}
        assert "research_only_simulation" in row["research_only_flags"]
        assert "failed_order_unavailable" in row["research_only_flags"]
        assert "limit_up_down_status_unknown" in row["research_only_flags"]


def test_backtest_reports_portfolio_win_rate() -> None:
    result = run_backtest()
    assert result["results"]
    for row in result["results"]:
        win_rate = row["portfolio_win_rate"]
        assert win_rate["basis"] == "invested_rebalance_day_net_return_after_costs"
        assert win_rate["status"] in {"research_only", "insufficient_sample", "unavailable"}
        assert win_rate["value"] is not None or win_rate["status"] == "unavailable"


def test_insufficient_sample_does_not_get_positive_conclusion() -> None:
    result = build_factor_evaluation()
    tier = result["tier_monotonicity"]
    assert tier["status"] == "insufficient_sample"
    assert "no positive conclusion" in tier["conclusion"]
    for combo in tier["combos"]:
        if combo["status"] == "insufficient_sample":
            assert combo["monotonic_status"] == "insufficient_sample"


def test_sprint2_reports_exist_and_are_report_only() -> None:
    for path in [FACTOR_REPORT, BACKTEST_REPORT, HEALTH_JSON]:
        assert path.exists()
    factor_text = FACTOR_REPORT.read_text(encoding="utf-8")
    backtest_text = BACKTEST_REPORT.read_text(encoding="utf-8")
    assert "report-only" in factor_text
    assert "No excess return is calculated or claimed" in factor_text
    assert "research_only_simulation" in backtest_text
    assert "Portfolio win rate" in backtest_text
    health = json.loads(HEALTH_JSON.read_text(encoding="utf-8"))
    assert health["production_impact"] == "none"
    assert health["hard_gates"]["blocks_production"] is False
    assert health["hard_gates"]["production_ready"] is False
    assert "portfolio_win_rate_status_counts" in health["backtest_research_only_status"]
    assert health["hardened_label_input"]["formal_label_ready_count"] == 0
