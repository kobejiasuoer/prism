from __future__ import annotations

import json
from pathlib import Path


PANEL_PATH = Path("data/quant/panels/daily_signal_panel.jsonl")
LABEL_PATH = Path("data/quant/labels/forward_return_labels.jsonl")


def load_jsonl(path: Path) -> list[dict]:
    assert path.exists()
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_sprint1_panel_score_contract() -> None:
    rows = load_jsonl(PANEL_PATH)
    assert rows
    assert all("final_score" not in row for row in rows)
    for row in rows:
        if row.get("score") is not None:
            assert row.get("source_lane")
            assert row.get("score_kind")
            assert row.get("score_source_lane") == row.get("source_lane")


def test_sprint1_ai_and_scan_fields_are_namespaced() -> None:
    rows = load_jsonl(PANEL_PATH)
    ai_rows = [
        row
        for row in rows
        if row["source_record_type"].startswith("ai_")
        or row["source_record_type"].startswith("brief_screener")
    ]
    scan_rows = [row for row in rows if row["pipeline_stage"] == "scan_candidate"]
    assert ai_rows
    assert scan_rows
    assert any(row.get("ai_priority_score") is not None or row.get("ai_best_score") is not None for row in ai_rows)
    assert all(row.get("scan_capital_score") is not None for row in scan_rows[:20])
    assert all(row.get("scan_technical_score") is not None for row in scan_rows[:20])


def test_sprint1_execution_gate_is_context() -> None:
    rows = load_jsonl(PANEL_PATH)
    gated = [row for row in rows if row.get("execution_gate_status")]
    assert gated
    assert all(row.get("execution_gate_scope") == "batch_context" for row in gated)


def test_sprint1_labels_are_2024_raw_net_only_with_missing_execution_flags() -> None:
    labels = load_jsonl(LABEL_PATH)
    assert labels
    assert all(label["trade_date"].startswith("2024-") for label in labels)
    assert all(label["source_lane"] in {"research_backfill_ai_history", "research_backfill_scan_history"} for label in labels)
    assert all(label["excess_return_status"] == "deferred_until_benchmark_frozen" for label in labels)
    assert all("suspend_status" in label["execution_data_missing"] for label in labels)
    assert all("limit_up_down_status" in label["execution_data_missing"] for label in labels)
    assert all("failed_order" in label["execution_data_missing"] for label in labels)
