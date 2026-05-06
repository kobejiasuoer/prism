from __future__ import annotations

import json
from pathlib import Path

from quant.evaluate_factors import build_factor_evaluation
from quant.report_quant_health import build_quant_health
from quant.run_portfolio_backtest import run_backtest


FACTOR_REPORT = Path("data/quant/reports/factor_evaluation_latest.md")
BACKTEST_REPORT = Path("data/quant/reports/portfolio_backtest_latest.md")
HEALTH_MD = Path("data/quant/reports/quant_health_latest.md")
HEALTH_JSON = Path("data/quant/reports/quant_health_latest.json")
HARDENED_LABELS = Path("data/quant/labels/forward_return_labels_hardened.jsonl")
PANEL_PATH = Path("data/quant/panels/daily_signal_panel.jsonl")


def load_jsonl(path: Path) -> list[dict]:
    assert path.exists()
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_reports_use_hardened_labels_input() -> None:
    for path in [FACTOR_REPORT, BACKTEST_REPORT, HEALTH_MD]:
        text = path.read_text(encoding="utf-8")
        assert "forward_return_labels_hardened.jsonl" in text
        assert "Hardened labels count: 11064" in text
        assert "Hardened formal_label_ready count: 0" in text
        assert "Hardened formal_execution_eligible count: 0" in text
    health = json.loads(HEALTH_JSON.read_text(encoding="utf-8"))
    assert health["hardened_label_input"]["rows"] == len(load_jsonl(HARDENED_LABELS))


def test_final_score_still_excluded_and_score_lane_scoped() -> None:
    result = build_factor_evaluation()
    evaluated = {item["field"] for item in result["formal_numeric_factors"]}
    evaluated |= {item["field"] for item in result["formal_group_factors"]}
    assert "final_score" not in evaluated
    assert "final_score" in result["excluded_fields"]
    assert "score" not in evaluated
    assert "score" in result["raw_source_fields"]
    panel = load_jsonl(PANEL_PATH)
    assert all(
        row.get("score_kind") and row.get("score_source_lane") == row.get("source_lane")
        for row in panel
        if row.get("score") is not None
    )


def test_hardened_formal_counts_are_zero_and_no_formal_excess() -> None:
    result = build_factor_evaluation()
    hardening = result["hardened_label_summary"]
    assert hardening["formal_label_ready_count"] == 0
    assert hardening["formal_execution_eligible_count"] == 0
    assert hardening["excess_return_status_counts"] == {"unavailable_market_benchmark_not_frozen": hardening["rows"]}
    hardened = load_jsonl(HARDENED_LABELS)
    assert all("excess_return" not in row for row in hardened)
    assert all(row["benchmark_reference"]["internal_benchmark_formal_label_eligible"] is False for row in hardened)


def test_backtest_remains_research_only_and_win_rate_exists() -> None:
    result = run_backtest()
    assert result["hardened_label_input"]["formal_label_ready_count"] == 0
    assert result["hardened_label_input"]["formal_execution_eligible_count"] == 0
    assert result["results"]
    for row in result["results"]:
        assert row["status"] in {"research_only", "insufficient_sample"}
        assert "research_only_simulation" in row["research_only_flags"]
        assert "portfolio_win_rate" in row
        assert row["portfolio_win_rate"]["basis"] == "invested_rebalance_day_net_return_after_costs"
    text = BACKTEST_REPORT.read_text(encoding="utf-8")
    assert "No sample with `formal_label_ready=false` is used to claim a formal or execution-realistic backtest" in text


def test_quant_health_not_production_ready() -> None:
    health = build_quant_health()
    assert health["overall_status"] == "report_only_hardened_not_production_ready"
    assert health["production_impact"] == "none"
    assert health["hard_gates"]["production_ready"] is False
    assert health["hardened_label_input"]["formal_label_ready_count"] == 0
    assert health["hardened_label_input"]["formal_execution_eligible_count"] == 0
    assert health["adjusted_return_availability"]["status"] == "not_ready"
    assert health["execution_realism_availability"]["status"] == "not_ready"
