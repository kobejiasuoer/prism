from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from .paths import BENCHMARKS_ROOT, EXECUTION_ROOT, LABELS_ROOT, PRICE_ROOT, REPORTS_ROOT, REPO_ROOT, workspace_relative
from .research_io import load_jsonl


SOURCE_LABEL_PATH = LABELS_ROOT / "forward_return_labels.jsonl"
HARDENED_LABEL_PATH = LABELS_ROOT / "forward_return_labels_hardened.jsonl"
LABEL_HARDENING_REPORT_PATH = REPORTS_ROOT / "label_hardening_latest.md"

BENCHMARK_MANIFEST_PATH = BENCHMARKS_ROOT / "benchmark_manifest.json"
BENCHMARK_RETURNS_PATH = BENCHMARKS_ROOT / "benchmark_returns.jsonl"
PRICE_ADJUSTMENT_MANIFEST_PATH = PRICE_ROOT / "price_adjustment_manifest.json"
EXECUTION_FLAGS_MANIFEST_PATH = EXECUTION_ROOT / "execution_flags_manifest.json"

GUARDRAILS = [
    "report_only",
    "research_only_hardened_labels",
    "no_original_label_overwrite",
    "no_formal_label_ready_upgrade",
    "no_formal_excess_return",
    "no_execution_realistic_return",
    "no_internal_benchmark_as_market_benchmark",
    "no_raw_return_as_adjusted_return",
    "no_production_sorting",
    "no_abc_replacement",
    "no_page",
    "no_prism_edge",
    "no_expected_5d_frontend",
    "no_ml",
    "no_factor_backtest_health_rerun",
]


@dataclass(frozen=True)
class LabelHardeningBuildResult:
    hardened_label_path: Path
    report_path: Path
    hardened_count: int
    source_count: int
    summary: dict[str, Any]


def now_stamp() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def git_revision() -> dict[str, Any]:
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()
    except Exception:
        commit = "unknown"
    try:
        dirty = subprocess.check_output(["git", "status", "--short"], cwd=REPO_ROOT, text=True).strip() != ""
    except Exception:
        dirty = None
    return {"commit": commit, "dirty": dirty}


def parse_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    tmp_path.replace(path)
    return count


def benchmark_by_id(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["benchmark_id"]: item for item in manifest.get("benchmarks", [])}


def benchmark_return_lookup(rows: list[dict[str, Any]]) -> dict[tuple[str, str, int], dict[str, Any]]:
    lookup = {}
    for row in rows:
        key = (str(row.get("trade_date")), str(row.get("entry_model")), int(row.get("holding_window_days") or 0))
        lookup[key] = row
    return lookup


def source_inputs() -> dict[str, Any]:
    paths = {
        "source_labels": SOURCE_LABEL_PATH,
        "benchmark_manifest": BENCHMARK_MANIFEST_PATH,
        "benchmark_returns": BENCHMARK_RETURNS_PATH,
        "price_adjustment_manifest": PRICE_ADJUSTMENT_MANIFEST_PATH,
        "execution_flags_manifest": EXECUTION_FLAGS_MANIFEST_PATH,
    }
    return {
        name: {
            "path": workspace_relative(path),
            "sha256": sha256_file(path) if path.exists() else None,
            "exists": path.exists(),
        }
        for name, path in paths.items()
    }


def research_only_reasons(
    *,
    label: dict[str, Any],
    internal_row: dict[str, Any] | None,
    price_manifest: dict[str, Any],
    execution_manifest: dict[str, Any],
) -> list[str]:
    reasons = [
        "market_benchmark_unavailable",
        "adjustment_policy_missing",
        "formal_adjusted_return_unavailable",
        "execution_data_missing",
        "execution_realism_not_ready",
    ]
    if internal_row:
        reasons.append("internal_benchmark_research_only_not_formal")
    else:
        reasons.append("internal_benchmark_unavailable_for_window")
    if label.get("label_status") != "available_research_only":
        reasons.append("source_label_unavailable")
    if label.get("raw_return") is None:
        reasons.append("raw_return_unavailable")
    if price_manifest.get("policy_status") != "raw_available_adjustment_unknown_research_only":
        reasons.append("price_policy_not_formal")
    if execution_manifest.get("execution_realism_status") != "ready":
        reasons.append("execution_not_formal")
    return sorted(set(reasons))


def harden_label(
    label: dict[str, Any],
    *,
    benchmark_manifest: dict[str, Any],
    benchmark_returns: dict[tuple[str, str, int], dict[str, Any]],
    price_manifest: dict[str, Any],
    execution_manifest: dict[str, Any],
    inputs: dict[str, Any],
    generated_at: str,
) -> dict[str, Any]:
    benchmarks = benchmark_by_id(benchmark_manifest)
    primary = benchmarks.get("CSI500", {})
    secondary = benchmarks.get("HS300", {})
    internal = benchmarks.get("eligible_universe_equal_weight", {})
    key = (
        str(label.get("trade_date")),
        str(label.get("entry_model")),
        int(label.get("holding_window_days") or 0),
    )
    internal_row = benchmark_returns.get(key)
    internal_available = internal_row is not None and internal_row.get("status") == "research_only_internal_benchmark"
    benchmark_status = "market_benchmark_unavailable_internal_research_only_available" if internal_available else "market_benchmark_unavailable"
    reasons = research_only_reasons(
        label=label,
        internal_row=internal_row,
        price_manifest=price_manifest,
        execution_manifest=execution_manifest,
    )
    execution_missing = set(label.get("execution_data_missing") or [])
    return {
        "schema_version": "1.0",
        "hardened_at": generated_at,
        "label_id": label.get("label_id"),
        "panel_row_id": label.get("panel_row_id"),
        "trade_date": label.get("trade_date"),
        "code": label.get("code"),
        "name": label.get("name"),
        "entry_model": label.get("entry_model"),
        "holding_window_days": label.get("holding_window_days"),
        "entry_trade_date": label.get("entry_trade_date"),
        "exit_trade_date": label.get("exit_trade_date"),
        "raw_return": label.get("raw_return"),
        "net_return": label.get("net_return"),
        "source_label_status": label.get("label_status"),
        "source_label_scope": label.get("label_scope"),
        "benchmark_id": "CSI500",
        "benchmark_status": benchmark_status,
        "benchmark_return_status": "unavailable_market_benchmark_not_frozen",
        "excess_return_status": "unavailable_market_benchmark_not_frozen",
        "benchmark_reference": {
            "primary_benchmark_id": "CSI500",
            "primary_benchmark_status": primary.get("status", "unavailable"),
            "secondary_benchmark_id": "HS300",
            "secondary_benchmark_status": secondary.get("status", "unavailable"),
            "internal_benchmark_id": "eligible_universe_equal_weight",
            "internal_benchmark_status": internal.get("status"),
            "internal_benchmark_return_status": "research_only_internal_available" if internal_available else "unavailable",
            "internal_benchmark_return": internal_row.get("benchmark_return") if internal_available else None,
            "internal_benchmark_return_type": internal_row.get("benchmark_return_type") if internal_available else None,
            "internal_benchmark_sample_count": internal_row.get("sample_count") if internal_available else None,
            "internal_benchmark_formal_label_eligible": False,
            "notes": "CSI500/HS300 are unavailable; eligible universe equal-weight is research_only_internal_benchmark and not a formal market benchmark.",
        },
        "price_adjustment_status": label.get("price_adjustment_status") or "unknown",
        "adjustment_policy": "unknown",
        "formal_adjusted_return_status": price_manifest.get("formal_adjusted_return_status", "unavailable_adjustment_policy_missing_not_ready"),
        "suspend_status": "unavailable" if "suspend_status" in execution_missing else "unknown",
        "limit_up_down_status": "unavailable" if "limit_up_down_status" in execution_missing else "unknown",
        "failed_order_status": "unavailable" if "failed_order" in execution_missing else "unknown",
        "partial_fill_status": "deferred" if "partial_fill" in execution_missing else "unknown",
        "execution_realism_status": execution_manifest.get("execution_realism_status", "not_ready_research_only_simulation_execution_data_missing"),
        "label_quality_status": "research_only_hardened_not_formal" if label.get("label_status") == "available_research_only" else "unavailable_hardened_not_formal",
        "research_only_reason": reasons,
        "formal_label_ready": False,
        "formal_execution_eligible": False,
        "source_label_hash": sha256_json(label),
        "source_label_artifact": workspace_relative(SOURCE_LABEL_PATH),
        "source_artifact": label.get("source_artifact"),
        "source_hash": label.get("source_hash"),
        "price_source_artifact": label.get("price_source_artifact"),
        "price_source_hash": label.get("price_source_hash"),
        "hardening_inputs": inputs,
        "guardrails": list(GUARDRAILS),
    }


def build_hardened_labels(
    *,
    source_label_path: Path = SOURCE_LABEL_PATH,
    benchmark_manifest_path: Path = BENCHMARK_MANIFEST_PATH,
    benchmark_returns_path: Path = BENCHMARK_RETURNS_PATH,
    price_manifest_path: Path = PRICE_ADJUSTMENT_MANIFEST_PATH,
    execution_manifest_path: Path = EXECUTION_FLAGS_MANIFEST_PATH,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    labels = load_jsonl(source_label_path)
    benchmark_manifest = parse_json(benchmark_manifest_path)
    benchmark_rows = load_jsonl(benchmark_returns_path)
    price_manifest = parse_json(price_manifest_path)
    execution_manifest = parse_json(execution_manifest_path)
    returns = benchmark_return_lookup(benchmark_rows)
    inputs = source_inputs()
    generated_at = now_stamp()
    hardened = [
        harden_label(
            label,
            benchmark_manifest=benchmark_manifest,
            benchmark_returns=returns,
            price_manifest=price_manifest,
            execution_manifest=execution_manifest,
            inputs=inputs,
            generated_at=generated_at,
        )
        for label in labels
    ]
    summary = summarize_hardened_labels(hardened, source_count=len(labels), generated_at=generated_at)
    summary["code_revision"] = git_revision()
    summary["hardening_inputs"] = inputs
    return hardened, summary


def summarize_hardened_labels(
    rows: list[dict[str, Any]],
    *,
    source_count: int,
    generated_at: str,
) -> dict[str, Any]:
    reason_counts: Counter[str] = Counter()
    for row in rows:
        reason_counts.update(row.get("research_only_reason") or [])
    return {
        "schema_version": "1.0",
        "generated_at": generated_at,
        "production_impact": "none",
        "source_label_count": source_count,
        "hardened_label_count": len(rows),
        "benchmark_status_counts": dict(Counter(row.get("benchmark_status") for row in rows)),
        "benchmark_return_status_counts": dict(Counter(row.get("benchmark_return_status") for row in rows)),
        "excess_return_status_counts": dict(Counter(row.get("excess_return_status") for row in rows)),
        "internal_benchmark_status_counts": dict(Counter((row.get("benchmark_reference") or {}).get("internal_benchmark_return_status") for row in rows)),
        "price_adjustment_status_counts": dict(Counter(row.get("price_adjustment_status") for row in rows)),
        "formal_adjusted_return_status_counts": dict(Counter(row.get("formal_adjusted_return_status") for row in rows)),
        "execution_realism_status_counts": dict(Counter(row.get("execution_realism_status") for row in rows)),
        "label_quality_status_counts": dict(Counter(row.get("label_quality_status") for row in rows)),
        "formal_label_ready_count": sum(1 for row in rows if row.get("formal_label_ready") is True),
        "formal_execution_eligible_count": sum(1 for row in rows if row.get("formal_execution_eligible") is True),
        "research_only_reason_counts": dict(reason_counts),
        "capability_status": {
            "raw_return": "available_for_research_only_when_source_label_available",
            "internal_equal_weight_benchmark": "available_research_only_internal_for_matching_windows",
            "CSI500_market_benchmark": "unavailable",
            "HS300_market_benchmark": "unavailable",
            "formal_market_excess_return": "unavailable",
            "formal_adjusted_return": "unavailable",
            "execution_realistic_return": "unavailable",
            "partial_fill": "deferred",
            "suspend_status": "unavailable",
            "limit_up_down_status": "unavailable",
            "failed_order": "unavailable",
        },
        "guardrails": list(GUARDRAILS),
    }


def render_label_hardening_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Prism Quant P1-A Card 4 Label Hardening",
        "",
        f"Generated at: {summary['generated_at']}",
        "",
        "Scope: P1-A Card 4 only. This report describes a hardened label sidecar; it does not overwrite original forward labels, generate formal labels, execution-realistic returns, formal excess returns, or rerun factor/backtest/health reports.",
        "",
        "## Summary",
        "",
        f"- Production impact: `{summary['production_impact']}`.",
        f"- Source labels: {summary['source_label_count']}.",
        f"- Hardened labels: {summary['hardened_label_count']}.",
        f"- Formal label ready count: {summary['formal_label_ready_count']}.",
        f"- Formal execution eligible count: {summary['formal_execution_eligible_count']}.",
        "- All hardened labels remain research-only or unavailable; none are production-ready.",
        "",
        "## Status Distributions",
        "",
        f"- Benchmark status: {summary['benchmark_status_counts']}.",
        f"- Benchmark return status: {summary['benchmark_return_status_counts']}.",
        f"- Excess return status: {summary['excess_return_status_counts']}.",
        f"- Internal benchmark status: {summary['internal_benchmark_status_counts']}.",
        f"- Price adjustment status: {summary['price_adjustment_status_counts']}.",
        f"- Formal adjusted return status: {summary['formal_adjusted_return_status_counts']}.",
        f"- Execution realism status: {summary['execution_realism_status_counts']}.",
        f"- Label quality status: {summary['label_quality_status_counts']}.",
        "",
        "## Research-Only Reasons",
        "",
        "| Reason | Rows |",
        "| --- | ---: |",
    ]
    for reason, count in sorted(summary["research_only_reason_counts"].items()):
        lines.append(f"| `{reason}` | {count} |")
    lines += [
        "",
        "## Capability Status",
        "",
        "| Capability | Status |",
        "| --- | --- |",
    ]
    for capability, status in summary["capability_status"].items():
        lines.append(f"| `{capability}` | `{status}` |")
    lines += [
        "",
        "## Hardening Inputs",
        "",
        "| Input | Path | Hash |",
        "| --- | --- | --- |",
    ]
    for name, item in summary["hardening_inputs"].items():
        hash_text = (item.get("sha256") or "missing")
        lines.append(f"| `{name}` | `{item.get('path')}` | `{hash_text[:12]}` |")
    lines += [
        "",
        "## Interpretation",
        "",
        "- CSI500 and HS300 remain unavailable, so formal market excess return remains unavailable.",
        "- Eligible universe equal-weight is carried only as `research_only_internal_benchmark`; it is not a formal market benchmark.",
        "- Raw returns are preserved but are not adjusted returns.",
        "- Adjustment policy remains unknown, so formal adjusted return is not ready.",
        "- Execution data remains missing, so execution-realistic return is not ready.",
        "- The hardened sidecar is suitable for a future report-only Sprint 2 rerun, but such rerun must preserve all research-only guardrails until benchmark, adjusted price, and execution data are actually complete.",
        "",
        "## Guardrails",
        "",
    ]
    for guardrail in summary["guardrails"]:
        lines.append(f"- `{guardrail}`")
    return "\n".join(lines) + "\n"


def write_label_hardening_outputs(
    *,
    hardened_label_path: Path = HARDENED_LABEL_PATH,
    report_path: Path = LABEL_HARDENING_REPORT_PATH,
) -> LabelHardeningBuildResult:
    hardened, summary = build_hardened_labels()
    hardened_count = write_jsonl(hardened_label_path, hardened)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_label_hardening_report(summary), encoding="utf-8")
    return LabelHardeningBuildResult(
        hardened_label_path=hardened_label_path,
        report_path=report_path,
        hardened_count=hardened_count,
        source_count=summary["source_label_count"],
        summary=summary,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build P1-A Card 4 hardened forward label sidecar.")
    parser.add_argument("--hardened-output", type=Path, default=HARDENED_LABEL_PATH)
    parser.add_argument("--report-output", type=Path, default=LABEL_HARDENING_REPORT_PATH)
    args = parser.parse_args()
    result = write_label_hardening_outputs(
        hardened_label_path=args.hardened_output,
        report_path=args.report_output,
    )
    print(
        json.dumps(
            {
                "hardened_labels": workspace_relative(result.hardened_label_path),
                "report": workspace_relative(result.report_path),
                "source_count": result.source_count,
                "hardened_count": result.hardened_count,
                "formal_label_ready_count": result.summary["formal_label_ready_count"],
                "formal_execution_eligible_count": result.summary["formal_execution_eligible_count"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
