from __future__ import annotations

import json
from pathlib import Path


PRICE_ADJUSTMENT_MANIFEST = Path("data/quant/price/price_adjustment_manifest.json")
PRICE_ADJUSTMENT_REPORT = Path("data/quant/reports/price_adjustment_policy_latest.md")
FORWARD_LABELS = Path("data/quant/labels/forward_return_labels.jsonl")


def load_jsonl(path: Path) -> list[dict]:
    assert path.exists()
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_price_adjustment_manifest_json_contract() -> None:
    manifest = json.loads(PRICE_ADJUSTMENT_MANIFEST.read_text(encoding="utf-8"))
    for field in [
        "schema_version",
        "generated_at",
        "production_impact",
        "price_source_artifacts",
        "price_row_count",
        "date_coverage",
        "available_fields",
        "missing_adjustment_fields",
        "selected_policy",
        "policy_status",
        "formal_adjusted_return_status",
        "label_implications",
        "guardrails",
    ]:
        assert field in manifest
    assert manifest["schema_version"] == "1.0"
    assert manifest["production_impact"] == "none"
    assert manifest["price_row_count"] > 0


def test_selected_policy_and_policy_status_are_explicit() -> None:
    manifest = json.loads(PRICE_ADJUSTMENT_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["selected_policy"]["current_policy"] == "raw_price_adjustment_unknown"
    assert manifest["selected_policy"]["formal_target_policy"] == "forward_adjusted_qfq"
    assert manifest["selected_policy"]["backward_adjusted_hfq_policy"] == "excluded_from_formal_forward_labels"
    assert manifest["policy_status"] == "raw_available_adjustment_unknown_research_only"


def test_formal_adjusted_return_is_not_ready() -> None:
    manifest = json.loads(PRICE_ADJUSTMENT_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["formal_adjusted_return_status"] != "ready"
    assert manifest["formal_adjusted_return_status"] == "unavailable_adjustment_policy_missing_not_ready"
    assert manifest["label_implications"]["formal_label_ready_allowed"] is False
    assert manifest["label_implications"]["raw_return_upgrade_to_adjusted_return_allowed"] is False


def test_missing_adjustment_fields_include_required_gap_markers() -> None:
    manifest = json.loads(PRICE_ADJUSTMENT_MANIFEST.read_text(encoding="utf-8"))
    missing = set(manifest["missing_adjustment_fields"])
    for field in ["adj_factor", "qfq", "hfq", "adjusted_ohlc", "open_adj", "high_adj", "low_adj", "close_adj"]:
        assert field in missing
    raw_fields = manifest["available_fields"]["raw_required_fields"]
    for field in ["open", "high", "low", "close", "volume", "amount"]:
        assert raw_fields[field]["available"] is True


def test_report_states_raw_labels_remain_research_only() -> None:
    text = PRICE_ADJUSTMENT_REPORT.read_text(encoding="utf-8")
    assert "Raw labels remain research-only" in text
    assert "raw return is not adjusted return" in text
    assert "No formal adjusted return can be calculated" in text


def test_forward_labels_are_not_upgraded_to_formal_adjusted_labels() -> None:
    labels = load_jsonl(FORWARD_LABELS)
    assert labels
    assert all(label.get("label_status") != "formal_label_ready" for label in labels)
    assert all(label.get("price_adjustment_status") == "unknown" for label in labels)
    assert all("adjusted_return" not in label for label in labels)
    assert all("adjustment_policy" in (label.get("execution_data_missing") or []) for label in labels)
