from __future__ import annotations

import json
from pathlib import Path


BENCHMARK_MANIFEST = Path("data/quant/benchmarks/benchmark_manifest.json")
BENCHMARK_RETURNS = Path("data/quant/benchmarks/benchmark_returns.jsonl")
FORWARD_LABELS = Path("data/quant/labels/forward_return_labels.jsonl")


def load_jsonl(path: Path) -> list[dict]:
    assert path.exists()
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_benchmark_manifest_json_contract() -> None:
    manifest = json.loads(BENCHMARK_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "1.0"
    assert manifest["production_impact"] == "none"
    assert manifest["output_artifacts"]["benchmark_returns"] == "data/quant/benchmarks/benchmark_returns.jsonl"
    by_id = {item["benchmark_id"]: item for item in manifest["benchmarks"]}
    assert {"eligible_universe_equal_weight", "CSI500", "HS300"} <= set(by_id)
    for item in by_id.values():
        for field in [
            "benchmark_id",
            "benchmark_name",
            "benchmark_type",
            "status",
            "source",
            "coverage_start",
            "coverage_end",
            "missing_dates_count",
            "hash",
            "checksum",
            "return_method",
            "notes",
        ]:
            assert field in item


def test_csi500_and_hs300_are_unavailable_without_frozen_data() -> None:
    manifest = json.loads(BENCHMARK_MANIFEST.read_text(encoding="utf-8"))
    by_id = {item["benchmark_id"]: item for item in manifest["benchmarks"]}
    for benchmark_id in ["CSI500", "HS300"]:
        item = by_id[benchmark_id]
        assert item["status"] == "unavailable"
        assert item["row_count"] == 0
        assert item["hash"] is None
        assert item["available_for_formal_excess_return"] is False
        assert item["return_method"] == "unavailable_no_frozen_index_price_series"


def test_eligible_equal_weight_is_research_only_internal_benchmark() -> None:
    manifest = json.loads(BENCHMARK_MANIFEST.read_text(encoding="utf-8"))
    item = next(row for row in manifest["benchmarks"] if row["benchmark_id"] == "eligible_universe_equal_weight")
    assert item["status"] == "research_only_internal_benchmark"
    assert item["benchmark_type"] == "internal_research_only_equal_weight"
    assert item["available_for_formal_excess_return"] is False
    assert item["available_for_report_only_internal_comparison"] is True
    assert item["row_count"] > 0
    assert item["hash"]


def test_benchmark_returns_jsonl_contract_and_2026_exclusion() -> None:
    rows = load_jsonl(BENCHMARK_RETURNS)
    assert rows
    for row in rows:
        assert row["benchmark_id"] == "eligible_universe_equal_weight"
        assert row["status"] == "research_only_internal_benchmark"
        assert row["benchmark_return_type"] == "research_only_internal_net_equal_weight"
        assert row["formal_label_eligible"] is False
        assert row["sample_count"] > 0
        assert row["source_hash"]
        assert not row["trade_date"].startswith("2026-")


def test_p1a_card1_does_not_generate_excess_return_to_forward_labels() -> None:
    labels = load_jsonl(FORWARD_LABELS)
    assert labels
    assert all("benchmark_return" not in label for label in labels)
    assert all("excess_return" not in label for label in labels)
    assert all(label["benchmark_status"] == "benchmark_unavailable" for label in labels)
    assert all(label["excess_return_status"] == "deferred_until_benchmark_frozen" for label in labels)
