from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from .config import load_quant_research_config
from .paths import BENCHMARKS_ROOT, LABELS_ROOT, PANELS_ROOT, REPORTS_ROOT, REPO_ROOT, ensure_quant_dirs, workspace_relative
from .research_io import load_jsonl


LABEL_PATH = LABELS_ROOT / "forward_return_labels.jsonl"
ELIGIBLE_UNIVERSE_PATH = PANELS_ROOT / "eligible_universe_snapshot.jsonl"
BENCHMARK_MANIFEST_PATH = BENCHMARKS_ROOT / "benchmark_manifest.json"
BENCHMARK_RETURNS_PATH = BENCHMARKS_ROOT / "benchmark_returns.jsonl"
BENCHMARK_COVERAGE_REPORT_PATH = REPORTS_ROOT / "benchmark_coverage_latest.md"

INTERNAL_BENCHMARK_ID = "eligible_universe_equal_weight"
MARKET_BENCHMARKS = {
    "CSI500": {
        "benchmark_name": "CSI 500",
        "benchmark_type": "primary_market_index",
        "notes": "No frozen CSI500 index price artifact exists in the repository; unavailable for P1-A Card 1.",
    },
    "HS300": {
        "benchmark_name": "HS 300",
        "benchmark_type": "secondary_market_index",
        "notes": "No frozen HS300 index price artifact exists in the repository; unavailable for P1-A Card 1.",
    },
}


@dataclass(frozen=True)
class BenchmarkBuildResult:
    manifest_path: Path
    returns_path: Path
    report_path: Path
    manifest: dict[str, Any]
    returns_count: int


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


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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


def source_artifact(path: Path) -> dict[str, Any]:
    return {
        "path": workspace_relative(path),
        "exists": path.exists(),
        "sha256": sha256_file(path) if path.exists() else None,
        "row_count": len(load_jsonl(path)) if path.exists() else 0,
    }


def eligible_universe_codes(rows: list[dict[str, Any]]) -> dict[str, set[str]]:
    codes_by_date: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        trade_date = row.get("trade_date")
        code = row.get("code")
        if trade_date and code:
            codes_by_date[str(trade_date)].add(str(code))
    return codes_by_date


def is_research_label_candidate(label: dict[str, Any]) -> bool:
    return (
        label.get("label_status") == "available_research_only"
        and label.get("label_scope") == "2024_research_backfill_only"
        and label.get("research_label_eligible") is True
        and str(label.get("trade_date") or "").startswith("2024-")
        and label.get("net_return") is not None
    )


def label_source_digest(labels: list[dict[str, Any]]) -> str:
    source_rows = [
        {
            "label_id": label.get("label_id"),
            "panel_row_id": label.get("panel_row_id"),
            "code": label.get("code"),
            "net_return": label.get("net_return"),
            "source_hash": label.get("source_hash"),
            "price_source_hash": label.get("price_source_hash"),
        }
        for label in labels
    ]
    return sha256_json(source_rows)


def build_internal_equal_weight_returns(
    labels: list[dict[str, Any]],
    universe_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    universe_by_date = eligible_universe_codes(universe_rows)
    grouped: dict[tuple[str, str, int], dict[str, dict[str, Any]]] = defaultdict(dict)
    source_row_counts: Counter[tuple[str, str, int]] = Counter()
    skipped = Counter()

    for label in sorted(labels, key=lambda item: (item.get("trade_date") or "", item.get("entry_model") or "", int(item.get("holding_window_days") or 0), item.get("code") or "", item.get("label_id") or "")):
        if not is_research_label_candidate(label):
            skipped["not_available_2024_research_label"] += 1
            continue
        trade_date = str(label["trade_date"])
        code = str(label["code"])
        if code not in universe_by_date.get(trade_date, set()):
            skipped["not_in_source_observed_eligible_universe"] += 1
            continue
        key = (trade_date, str(label["entry_model"]), int(label["holding_window_days"]))
        source_row_counts[key] += 1
        grouped[key].setdefault(code, label)

    rows: list[dict[str, Any]] = []
    for (trade_date, entry_model, window), by_code in sorted(grouped.items()):
        group_labels = [by_code[code] for code in sorted(by_code)]
        values = [float(label["net_return"]) for label in group_labels]
        benchmark_return = sum(values) / len(values)
        rows.append(
            {
                "schema_version": "1.0",
                "benchmark_id": INTERNAL_BENCHMARK_ID,
                "benchmark_name": "Eligible universe equal-weight",
                "trade_date": trade_date,
                "entry_model": entry_model,
                "holding_window_days": window,
                "benchmark_return": round(benchmark_return, 8),
                "benchmark_return_type": "research_only_internal_net_equal_weight",
                "underlying_return_field": "net_return",
                "sample_count": len(group_labels),
                "source_label_rows": source_row_counts[(trade_date, entry_model, window)],
                "status": "research_only_internal_benchmark",
                "formal_label_eligible": False,
                "source_hash": label_source_digest(group_labels),
                "notes": "Computed from existing 2024 available_research_only labels and source-observed eligible universe rows; not a frozen market benchmark and not valid for production or formal market excess-return claims.",
            }
        )

    diagnostics = {
        "eligible_universe_trade_dates": len(universe_by_date),
        "source_observed_universe_rows": len(universe_rows),
        "source_observed_universe_2026_rows": sum(1 for row in universe_rows if str(row.get("trade_date") or "").startswith("2026-")),
        "skipped_label_rows": dict(skipped),
        "deduplication": "equal-weight by unique code within trade_date, entry_model, holding_window_days",
    }
    return rows, diagnostics


def internal_benchmark_manifest_entry(
    *,
    rows: list[dict[str, Any]],
    output_hash: str,
    labels: list[dict[str, Any]],
    universe_rows: list[dict[str, Any]],
    diagnostics: dict[str, Any],
    label_path: Path = LABEL_PATH,
    universe_path: Path = ELIGIBLE_UNIVERSE_PATH,
) -> dict[str, Any]:
    required_dates = sorted(
        {
            str(label.get("trade_date"))
            for label in labels
            if label.get("label_scope") == "2024_research_backfill_only" and str(label.get("trade_date") or "").startswith("2024-")
        }
    )
    covered_dates = sorted({str(row["trade_date"]) for row in rows})
    missing_dates = sorted(set(required_dates) - set(covered_dates))
    by_combo = Counter((row["entry_model"], int(row["holding_window_days"])) for row in rows)
    sample_counts = [int(row["sample_count"]) for row in rows]
    return {
        "benchmark_id": INTERNAL_BENCHMARK_ID,
        "benchmark_name": "Eligible universe equal-weight",
        "benchmark_type": "internal_research_only_equal_weight",
        "status": "research_only_internal_benchmark",
        "source": {
            "source_name": "current_repository_labels_and_source_observed_eligible_universe",
            "source_artifacts": [workspace_relative(label_path), workspace_relative(universe_path)],
            "source_hashes": [sha256_file(label_path), sha256_file(universe_path)],
            "source_scope": "2024 available_research_only labels joined to source-observed eligible universe codes",
        },
        "coverage_start": covered_dates[0] if covered_dates else None,
        "coverage_end": covered_dates[-1] if covered_dates else None,
        "required_dates_count": len(required_dates),
        "covered_dates_count": len(covered_dates),
        "missing_dates_count": len(missing_dates),
        "missing_dates": missing_dates,
        "row_count": len(rows),
        "hash": output_hash,
        "checksum": output_hash,
        "return_method": "mean net_return across unique source-observed eligible codes for each trade_date/entry_model/holding_window",
        "return_type": "research_only_internal_net_equal_weight",
        "available_for_formal_excess_return": False,
        "available_for_report_only_internal_comparison": bool(rows),
        "trade_date_window_rows": {f"{entry}|{window}": count for (entry, window), count in sorted(by_combo.items())},
        "sample_count_min": min(sample_counts) if sample_counts else 0,
        "sample_count_max": max(sample_counts) if sample_counts else 0,
        "diagnostics": diagnostics,
        "notes": "Internal source-observed equal-weight benchmark only. It is not CSI500/HS300, not a formal market benchmark, and must not be used to claim production-ready excess return.",
    }


def unavailable_market_benchmark_entry(benchmark_id: str, *, required_dates: list[str]) -> dict[str, Any]:
    metadata = MARKET_BENCHMARKS[benchmark_id]
    return {
        "benchmark_id": benchmark_id,
        "benchmark_name": metadata["benchmark_name"],
        "benchmark_type": metadata["benchmark_type"],
        "status": "unavailable",
        "source": {
            "source_name": "not_available_in_current_repository",
            "source_artifacts": [],
            "source_hashes": [],
        },
        "coverage_start": None,
        "coverage_end": None,
        "required_dates_count": len(required_dates),
        "covered_dates_count": 0,
        "missing_dates_count": len(required_dates),
        "missing_dates": required_dates,
        "row_count": 0,
        "hash": None,
        "checksum": None,
        "return_method": "unavailable_no_frozen_index_price_series",
        "return_type": "unavailable",
        "available_for_formal_excess_return": False,
        "available_for_report_only_internal_comparison": False,
        "notes": metadata["notes"],
    }


def build_manifest(
    *,
    internal_rows: list[dict[str, Any]],
    internal_diagnostics: dict[str, Any],
    returns_hash: str,
    generated_at: str,
    labels_path: Path = LABEL_PATH,
    universe_path: Path = ELIGIBLE_UNIVERSE_PATH,
) -> dict[str, Any]:
    labels = load_jsonl(labels_path)
    universe_rows = load_jsonl(universe_path)
    config = load_quant_research_config()
    label_dates = sorted(
        {
            str(label.get("trade_date"))
            for label in labels
            if label.get("label_scope") == "2024_research_backfill_only" and str(label.get("trade_date") or "").startswith("2024-")
        }
    )
    benchmark_entries = [
        internal_benchmark_manifest_entry(
            rows=internal_rows,
            output_hash=returns_hash,
            labels=labels,
            universe_rows=universe_rows,
            diagnostics=internal_diagnostics,
            label_path=labels_path,
            universe_path=universe_path,
        ),
        unavailable_market_benchmark_entry("CSI500", required_dates=label_dates),
        unavailable_market_benchmark_entry("HS300", required_dates=label_dates),
    ]
    return {
        "schema_version": "1.0",
        "generated_at": generated_at,
        "scope": "P1-A Card 1 benchmark manifest and research-only internal benchmark returns",
        "production_impact": "none",
        "config_path": workspace_relative(config.path),
        "config_checksum": config.checksum,
        "code_revision": git_revision(),
        "input_artifacts": [source_artifact(labels_path), source_artifact(universe_path)],
        "output_artifacts": {
            "benchmark_returns": workspace_relative(BENCHMARK_RETURNS_PATH),
            "benchmark_returns_sha256": returns_hash,
            "benchmark_coverage_report": workspace_relative(BENCHMARK_COVERAGE_REPORT_PATH),
        },
        "label_date_scope": {
            "scope": "2024_research_backfill_only",
            "coverage_start": label_dates[0] if label_dates else None,
            "coverage_end": label_dates[-1] if label_dates else None,
            "required_dates_count": len(label_dates),
            "current_2026_artifacts_policy": "coverage_only_not_formal_label_evaluation",
        },
        "benchmarks": benchmark_entries,
        "guardrails": [
            "report_only",
            "research_only_internal_benchmark",
            "no_external_data_fetch",
            "no_csi500_or_hs300_fabrication",
            "no_forward_label_excess_return_generation",
            "no_production_sorting",
            "no_abc_replacement",
            "no_page",
            "no_prism_edge",
            "no_ml",
        ],
    }


def render_coverage_report(manifest: dict[str, Any], returns_rows: list[dict[str, Any]]) -> str:
    by_status = Counter(item["status"] for item in manifest["benchmarks"])
    by_combo = Counter((row["entry_model"], int(row["holding_window_days"])) for row in returns_rows)
    sample_counts = [int(row["sample_count"]) for row in returns_rows]
    internal = next(item for item in manifest["benchmarks"] if item["benchmark_id"] == INTERNAL_BENCHMARK_ID)
    lines = [
        "# Prism Quant P1-A Benchmark Coverage",
        "",
        f"Generated at: {manifest['generated_at']}",
        "",
        "Scope: P1-A Card 1 only. This report is benchmark coverage and research-only internal benchmark preparation; it does not modify forward labels or produce excess return.",
        "",
        "## Summary",
        "",
        f"- Benchmark status counts: {dict(by_status)}.",
        f"- Benchmark returns rows: {len(returns_rows)}.",
        f"- Internal benchmark coverage: {internal['coverage_start']} to {internal['coverage_end']}.",
        f"- Internal benchmark sample count range: {min(sample_counts) if sample_counts else 0} to {max(sample_counts) if sample_counts else 0} unique codes per row.",
        "- CSI500 and HS300 remain `unavailable` because no frozen index price series exists in the repository.",
        "- `eligible_universe_equal_weight` is `research_only_internal_benchmark`; it is not a formal market benchmark.",
        "",
        "## Benchmark Manifest",
        "",
        "| Benchmark | Type | Status | Coverage | Missing dates | Return method | Hash/checksum | Notes |",
        "| --- | --- | --- | --- | ---: | --- | --- | --- |",
    ]
    for item in manifest["benchmarks"]:
        coverage = f"{item['coverage_start']} to {item['coverage_end']}" if item.get("coverage_start") else "unavailable"
        checksum = (item.get("hash") or "unavailable")
        if checksum != "unavailable":
            checksum = checksum[:12]
        lines.append(
            f"| `{item['benchmark_id']}` | `{item['benchmark_type']}` | `{item['status']}` | {coverage} | "
            f"{item['missing_dates_count']} | {item['return_method']} | `{checksum}` | {item['notes']} |"
        )
    lines += [
        "",
        "## Internal Benchmark Returns",
        "",
        "| Entry model | Holding window | Return rows |",
        "| --- | ---: | ---: |",
    ]
    for (entry_model, window), count in sorted(by_combo.items()):
        lines.append(f"| `{entry_model}` | {window} | {count} |")
    lines += [
        "",
        "## Source And Coverage Caveats",
        "",
        f"- Input labels: `{manifest['input_artifacts'][0]['path']}` rows={manifest['input_artifacts'][0]['row_count']} hash=`{manifest['input_artifacts'][0]['sha256'][:12]}`.",
        f"- Eligible universe: `{manifest['input_artifacts'][1]['path']}` rows={manifest['input_artifacts'][1]['row_count']} hash=`{manifest['input_artifacts'][1]['sha256'][:12]}`.",
        f"- 2026 source-observed universe rows excluded from formal label evaluation: {internal['diagnostics']['source_observed_universe_2026_rows']}.",
        "- Internal equal weight is deduplicated by unique code within each trade date, entry model, and holding window.",
        "- Missing CSI500/HS300 data must continue to make market benchmark return and excess return unavailable.",
        "- No benchmark dates are forward-filled, zero-filled, interpolated, or replaced by another benchmark.",
        "",
        "## Guardrails",
        "",
        "- No production sorting changes.",
        "- No A/B/C replacement.",
        "- No page, Prism Edge, Expected 5D frontend, theme state machine, or ML work.",
        "- No external benchmark fetch and no fabricated CSI500/HS300 data.",
        "- Forward labels remain unchanged; no `excess_return` is generated by this card.",
    ]
    return "\n".join(lines) + "\n"


def build_benchmark_outputs(
    *,
    labels_path: Path = LABEL_PATH,
    universe_path: Path = ELIGIBLE_UNIVERSE_PATH,
    returns_path: Path = BENCHMARK_RETURNS_PATH,
    manifest_path: Path = BENCHMARK_MANIFEST_PATH,
    report_path: Path = BENCHMARK_COVERAGE_REPORT_PATH,
) -> BenchmarkBuildResult:
    ensure_quant_dirs()
    labels = load_jsonl(labels_path)
    universe_rows = load_jsonl(universe_path)
    generated_at = now_stamp()
    internal_rows, diagnostics = build_internal_equal_weight_returns(labels, universe_rows)
    returns_count = write_jsonl(returns_path, internal_rows)
    returns_hash = sha256_file(returns_path)
    manifest = build_manifest(
        internal_rows=internal_rows,
        internal_diagnostics=diagnostics,
        returns_hash=returns_hash,
        generated_at=generated_at,
        labels_path=labels_path,
        universe_path=universe_path,
    )
    write_json(manifest_path, manifest)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_coverage_report(manifest, internal_rows), encoding="utf-8")
    return BenchmarkBuildResult(
        manifest_path=manifest_path,
        returns_path=returns_path,
        report_path=report_path,
        manifest=manifest,
        returns_count=returns_count,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build P1-A benchmark manifest and research-only internal benchmark returns.")
    parser.add_argument("--labels", type=Path, default=LABEL_PATH)
    parser.add_argument("--eligible-universe", type=Path, default=ELIGIBLE_UNIVERSE_PATH)
    parser.add_argument("--returns-output", type=Path, default=BENCHMARK_RETURNS_PATH)
    parser.add_argument("--manifest-output", type=Path, default=BENCHMARK_MANIFEST_PATH)
    parser.add_argument("--report-output", type=Path, default=BENCHMARK_COVERAGE_REPORT_PATH)
    args = parser.parse_args()
    result = build_benchmark_outputs(
        labels_path=args.labels,
        universe_path=args.eligible_universe,
        returns_path=args.returns_output,
        manifest_path=args.manifest_output,
        report_path=args.report_output,
    )
    print(
        json.dumps(
            {
                "manifest": workspace_relative(result.manifest_path),
                "returns": workspace_relative(result.returns_path),
                "report": workspace_relative(result.report_path),
                "returns_count": result.returns_count,
                "benchmark_statuses": {
                    item["benchmark_id"]: item["status"] for item in result.manifest["benchmarks"]
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
