from __future__ import annotations

import json
from pathlib import Path


SOURCE_LABELS = Path("data/quant/labels/forward_return_labels.jsonl")
HARDENED_LABELS = Path("data/quant/labels/forward_return_labels_hardened.jsonl")
LABEL_HARDENING_REPORT = Path("data/quant/reports/label_hardening_latest.md")


def load_jsonl(path: Path) -> list[dict]:
    assert path.exists()
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_hardened_labels_exist_and_match_source_count() -> None:
    source = load_jsonl(SOURCE_LABELS)
    hardened = load_jsonl(HARDENED_LABELS)
    assert source
    assert len(hardened) == len(source)
    assert {row["label_id"] for row in hardened} == {row["label_id"] for row in source}


def test_source_labels_are_not_overwritten() -> None:
    source = load_jsonl(SOURCE_LABELS)
    assert all("hardening_inputs" not in row for row in source)
    assert all("formal_label_ready" not in row for row in source)
    assert all("adjusted_return" not in row for row in source)
    assert all("execution_realistic_return" not in row for row in source)
    assert all("excess_return" not in row for row in source)


def test_hardened_labels_never_become_formal_or_execution_eligible() -> None:
    hardened = load_jsonl(HARDENED_LABELS)
    assert all(row["formal_label_ready"] is False for row in hardened)
    assert all(row["formal_execution_eligible"] is False for row in hardened)
    assert all(row["label_quality_status"] in {"research_only_hardened_not_formal", "unavailable_hardened_not_formal"} for row in hardened)


def test_market_benchmark_unavailable_means_no_formal_excess_return() -> None:
    hardened = load_jsonl(HARDENED_LABELS)
    assert all(row["benchmark_reference"]["primary_benchmark_status"] == "unavailable" for row in hardened)
    assert all(row["benchmark_reference"]["secondary_benchmark_status"] == "unavailable" for row in hardened)
    assert all(row["benchmark_return_status"] == "unavailable_market_benchmark_not_frozen" for row in hardened)
    assert all(row["excess_return_status"] == "unavailable_market_benchmark_not_frozen" for row in hardened)
    assert all("excess_return" not in row for row in hardened)


def test_internal_benchmark_is_research_only_internal() -> None:
    hardened = load_jsonl(HARDENED_LABELS)
    with_internal = [
        row
        for row in hardened
        if row["benchmark_reference"]["internal_benchmark_return_status"] == "research_only_internal_available"
    ]
    assert with_internal
    assert all(row["benchmark_reference"]["internal_benchmark_status"] == "research_only_internal_benchmark" for row in with_internal)
    assert all(row["benchmark_reference"]["internal_benchmark_formal_label_eligible"] is False for row in with_internal)
    assert all("internal_benchmark_research_only_not_formal" in row["research_only_reason"] for row in with_internal)


def test_adjustment_and_execution_statuses_are_not_ready() -> None:
    hardened = load_jsonl(HARDENED_LABELS)
    assert all(row["adjustment_policy"] == "unknown" for row in hardened)
    assert all(row["formal_adjusted_return_status"] != "ready" for row in hardened)
    assert all(row["execution_realism_status"] != "ready" for row in hardened)
    assert all(row["suspend_status"] == "unavailable" for row in hardened)
    assert all(row["limit_up_down_status"] == "unavailable" for row in hardened)
    assert all(row["failed_order_status"] == "unavailable" for row in hardened)
    assert all(row["partial_fill_status"] == "deferred" for row in hardened)


def test_label_hardening_report_contains_distributions_and_guardrails() -> None:
    text = LABEL_HARDENING_REPORT.read_text(encoding="utf-8")
    assert "Benchmark status:" in text
    assert "Price adjustment status:" in text
    assert "Execution realism status:" in text
    assert "Formal label ready count: 0" in text
    assert "Formal execution eligible count: 0" in text
    assert "## Guardrails" in text
    assert "no_formal_excess_return" in text
