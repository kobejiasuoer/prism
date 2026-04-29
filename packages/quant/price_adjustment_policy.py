from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .paths import LABELS_ROOT, PRICE_ROOT, REPORTS_ROOT, REPO_ROOT, ensure_quant_dirs, workspace_relative
from .research_io import load_jsonl, write_json


PRICE_CACHE_ROOT = REPO_ROOT / "stock-screener" / "data" / "research_backfill" / "cache" / "price_kline"
LABEL_PATH = LABELS_ROOT / "forward_return_labels.jsonl"
PRICE_ADJUSTMENT_MANIFEST_PATH = PRICE_ROOT / "price_adjustment_manifest.json"
PRICE_ADJUSTMENT_REPORT_PATH = REPORTS_ROOT / "price_adjustment_policy_latest.md"

RAW_REQUIRED_FIELDS = ["open", "high", "low", "close", "volume", "amount"]
MISSING_ADJUSTMENT_FIELDS = [
    "adj_factor",
    "qfq",
    "hfq",
    "adjusted_ohlc",
    "open_adj",
    "high_adj",
    "low_adj",
    "close_adj",
    "prev_close_adj",
    "adjustment_policy",
    "corporate_action_provenance",
    "pit_adjustment_available_timestamp",
]


@dataclass(frozen=True)
class PriceAdjustmentBuildResult:
    manifest_path: Path
    report_path: Path
    manifest: dict[str, Any]


def now_stamp() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def parse_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def inspect_price_cache(price_cache_root: Path) -> dict[str, Any]:
    files = sorted(price_cache_root.glob("*.json"))
    artifacts: list[dict[str, Any]] = []
    field_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    dates: list[str] = []
    total_rows = 0
    unreadable: list[dict[str, str]] = []
    sample_row: dict[str, Any] | None = None

    for path in files:
        try:
            rows = parse_json(path)
        except Exception as exc:
            unreadable.append({"path": workspace_relative(path), "error": str(exc)})
            continue
        if not isinstance(rows, list):
            unreadable.append({"path": workspace_relative(path), "error": "json root is not a list"})
            continue
        file_dates: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            if sample_row is None:
                sample_row = dict(row)
            total_rows += 1
            for field, value in row.items():
                if value not in (None, "", [], {}):
                    field_counts[str(field)] += 1
            source_counts[str(row.get("source") or "<missing>")] += 1
            if row.get("date"):
                date = str(row["date"])
                dates.append(date)
                file_dates.append(date)
        artifacts.append(
            {
                "path": workspace_relative(path),
                "sha256": sha256_file(path),
                "row_count": len(rows),
                "coverage_start": min(file_dates) if file_dates else None,
                "coverage_end": max(file_dates) if file_dates else None,
            }
        )

    field_coverage = {
        field: {
            "non_null_rows": count,
            "coverage_rate": count / total_rows if total_rows else 0.0,
        }
        for field, count in sorted(field_counts.items())
    }
    available_fields = {
        "raw_ohlcv_complete": bool(total_rows) and all(field_counts.get(field, 0) == total_rows for field in RAW_REQUIRED_FIELDS),
        "raw_required_fields": {
            field: {
                "available": field_counts.get(field, 0) == total_rows and total_rows > 0,
                "non_null_rows": field_counts.get(field, 0),
                "coverage_rate": field_counts.get(field, 0) / total_rows if total_rows else 0.0,
            }
            for field in RAW_REQUIRED_FIELDS
        },
        "all_observed_fields": field_coverage,
    }
    return {
        "root": workspace_relative(price_cache_root),
        "artifact_count": len(files),
        "readable_artifact_count": len(artifacts),
        "unreadable_artifacts": unreadable,
        "price_row_count": total_rows,
        "date_coverage": {
            "start": min(dates) if dates else None,
            "end": max(dates) if dates else None,
            "unique_dates": len(set(dates)),
        },
        "available_fields": available_fields,
        "source_counts": dict(source_counts),
        "sample_row": sample_row,
        "artifacts": artifacts,
    }


def inspect_labels(label_path: Path) -> dict[str, Any]:
    labels = load_jsonl(label_path)
    label_status = Counter(label.get("label_status") for label in labels)
    adjustment_status = Counter(label.get("price_adjustment_status") for label in labels)
    missing_adjustment_policy = sum("adjustment_policy" in (label.get("execution_data_missing") or []) for label in labels)
    adjusted_return_fields = sum("adjusted_return" in label for label in labels)
    formal_ready = sum(label.get("label_status") == "formal_label_ready" for label in labels)
    entry_dates = [str(label["entry_trade_date"]) for label in labels if label.get("entry_trade_date")]
    exit_dates = [str(label["exit_trade_date"]) for label in labels if label.get("exit_trade_date")]
    return {
        "label_path": workspace_relative(label_path),
        "label_rows": len(labels),
        "label_status_counts": dict(label_status),
        "price_adjustment_status_counts": dict(adjustment_status),
        "rows_missing_adjustment_policy": missing_adjustment_policy,
        "adjusted_return_field_rows": adjusted_return_fields,
        "formal_label_ready_rows": formal_ready,
        "entry_date_coverage": {
            "start": min(entry_dates) if entry_dates else None,
            "end": max(entry_dates) if entry_dates else None,
        },
        "exit_date_coverage": {
            "start": min(exit_dates) if exit_dates else None,
            "end": max(exit_dates) if exit_dates else None,
        },
    }


def build_price_adjustment_manifest(
    *,
    price_cache_root: Path = PRICE_CACHE_ROOT,
    label_path: Path = LABEL_PATH,
) -> dict[str, Any]:
    price_inventory = inspect_price_cache(price_cache_root)
    label_inventory = inspect_labels(label_path)
    return {
        "schema_version": "1.0",
        "generated_at": now_stamp(),
        "scope": "P1-A Card 2 adjusted price policy freeze",
        "production_impact": "none",
        "code_revision": git_revision(),
        "price_source_artifacts": {
            "root": price_inventory["root"],
            "artifact_count": price_inventory["artifact_count"],
            "readable_artifact_count": price_inventory["readable_artifact_count"],
            "artifacts": price_inventory["artifacts"],
            "unreadable_artifacts": price_inventory["unreadable_artifacts"],
        },
        "price_row_count": price_inventory["price_row_count"],
        "date_coverage": price_inventory["date_coverage"],
        "available_fields": price_inventory["available_fields"],
        "source_counts": price_inventory["source_counts"],
        "missing_adjustment_fields": list(MISSING_ADJUSTMENT_FIELDS),
        "selected_policy": {
            "current_policy": "raw_price_adjustment_unknown",
            "current_policy_use": "raw price audit and research-only replay only",
            "formal_target_policy": "forward_adjusted_qfq",
            "formal_target_status": "unavailable_in_current_repository",
            "backward_adjusted_hfq_policy": "excluded_from_formal_forward_labels",
            "reason": "Current cache has raw OHLCV but no adj_factor, qfq, hfq, adjusted OHLC, adjustment policy, or PIT adjustment availability proof.",
        },
        "policy_status": "raw_available_adjustment_unknown_research_only",
        "formal_adjusted_return_status": "unavailable_adjustment_policy_missing_not_ready",
        "label_implications": {
            **label_inventory,
            "current_labels_remain": "research_only_adjustment_missing",
            "formal_label_ready_allowed": False,
            "raw_return_upgrade_to_adjusted_return_allowed": False,
            "future_required_for_formal_adjusted_return": [
                "adjusted entry and exit OHLC",
                "adj_factor",
                "adjustment_policy=qfq or approved equivalent",
                "source artifacts and hashes",
                "PIT availability proof",
                "raw vs adjusted audit",
            ],
        },
        "raw_price_capabilities": [
            "raw OHLCV audit",
            "raw next_open and next_close replay",
            "raw close exit replay",
            "volume and amount diagnostics for future execution work",
        ],
        "adjusted_price_blockers": [
            "no adj_factor",
            "no qfq field",
            "no hfq field",
            "no adjusted OHLC",
            "no adjustment_policy",
            "no PIT adjustment availability timestamp",
        ],
        "guardrails": [
            "report_only",
            "research_only_when_adjustment_policy_unknown",
            "no_external_data_fetch",
            "no_adjustment_factor_inference",
            "no_adjusted_price_generation",
            "no_raw_return_as_adjusted_return",
            "no_formal_label_ready_upgrade",
            "no_factor_backtest_health_rerun",
            "no_production_sorting",
            "no_abc_replacement",
            "no_page",
            "no_prism_edge",
            "no_expected_5d_frontend",
            "no_ml",
        ],
    }


def render_policy_report(manifest: dict[str, Any]) -> str:
    date_coverage = manifest["date_coverage"]
    raw_fields = manifest["available_fields"]["raw_required_fields"]
    label = manifest["label_implications"]
    lines = [
        "# Prism Quant P1-A Card 2 Price Adjustment Policy",
        "",
        f"Generated at: {manifest['generated_at']}",
        "",
        "Scope: P1-A Card 2 only. This report freezes the current adjusted-price policy expression; it does not regenerate labels, adjusted prices, factor reports, backtests, or quant health.",
        "",
        "## Summary",
        "",
        f"- Production impact: `{manifest['production_impact']}`.",
        f"- Selected current policy: `{manifest['selected_policy']['current_policy']}`.",
        f"- Policy status: `{manifest['policy_status']}`.",
        f"- Formal adjusted return status: `{manifest['formal_adjusted_return_status']}`.",
        "- Current price cache has raw OHLCV only; adjusted price data is unavailable.",
        "- Forward-adjusted / qfq is the future target policy for formal research labels, but it is not available in the current repository.",
        "- Backward-adjusted / hfq is excluded from formal forward labels to avoid future-data risk.",
        "",
        "## Current Price Source",
        "",
        f"- Source path: `{manifest['price_source_artifacts']['root']}`.",
        f"- Source artifacts: {manifest['price_source_artifacts']['artifact_count']} JSON files.",
        f"- Readable artifacts: {manifest['price_source_artifacts']['readable_artifact_count']} JSON files.",
        f"- Price rows: {manifest['price_row_count']}.",
        f"- Date coverage: {date_coverage['start']} to {date_coverage['end']} ({date_coverage['unique_dates']} unique dates).",
        f"- Source counts: {manifest['source_counts']}.",
        "",
        "## Raw Field Availability",
        "",
        "| Field | Available | Non-null rows | Coverage |",
        "| --- | --- | ---: | ---: |",
    ]
    for field in RAW_REQUIRED_FIELDS:
        item = raw_fields[field]
        lines.append(f"| `{field}` | {str(item['available']).lower()} | {item['non_null_rows']} | {item['coverage_rate'] * 100:.2f}% |")
    lines += [
        "",
        "## Missing Adjustment Fields",
        "",
    ]
    for field in manifest["missing_adjustment_fields"]:
        lines.append(f"- `{field}`")
    lines += [
        "",
        "## What Raw Price Can Support",
        "",
        "- Raw price can support audit, source tracing, and research-only raw forward-return replay.",
        "- Raw price can support next-open / next-close lookup and close-based exit replay in the current 2024 research backfill.",
        "- Raw price can support volume and amount diagnostics for later execution-data work.",
        "- Raw labels remain research-only and adjustment-missing; raw return is not adjusted return.",
        "",
        "## What Adjusted Price Cannot Support Yet",
        "",
        "- No formal adjusted return can be calculated.",
        "- No label can be upgraded to `formal_label_ready` on adjustment grounds.",
        "- No raw return may be renamed or treated as adjusted return.",
        "- No execution-realistic backtest claim is allowed from the current raw-only data.",
        "- No hfq/backward-adjusted series enters formal forward labels.",
        "",
        "## Label Implications",
        "",
        f"- Label rows inspected: {label['label_rows']}.",
        f"- Label statuses: {label['label_status_counts']}.",
        f"- Price adjustment statuses: {label['price_adjustment_status_counts']}.",
        f"- Rows missing `adjustment_policy`: {label['rows_missing_adjustment_policy']}.",
        f"- Rows with `adjusted_return`: {label['adjusted_return_field_rows']}.",
        f"- Rows with `formal_label_ready`: {label['formal_label_ready_rows']}.",
        f"- Current label implication: `{label['current_labels_remain']}`.",
        "",
        "## Backtest And Quant Health Impact",
        "",
        "- Minimal backtest remains `research_only_simulation` because adjustment policy is unknown and execution data is still incomplete.",
        "- Quant health should continue to report adjustment/price hardening as incomplete until adjusted source, policy, and PIT proof are available.",
        "- Factor/backtest/health reports are not regenerated by this card.",
        "",
        "## P1-A Follow-Up Data Needed",
        "",
        "- Frozen forward-adjusted / qfq OHLC for every formal label entry and exit date.",
        "- `adj_factor` and raw-vs-adjusted audit trail.",
        "- `adjustment_policy` and source metadata on every formal price row.",
        "- Source artifact path and sha256 for adjusted data.",
        "- PIT availability proof for adjustment factors or vendor-adjusted prices.",
        "",
        "## Guardrails",
        "",
    ]
    for guardrail in manifest["guardrails"]:
        lines.append(f"- `{guardrail}`")
    return "\n".join(lines) + "\n"


def write_price_adjustment_policy_outputs(
    *,
    manifest_path: Path = PRICE_ADJUSTMENT_MANIFEST_PATH,
    report_path: Path = PRICE_ADJUSTMENT_REPORT_PATH,
    price_cache_root: Path = PRICE_CACHE_ROOT,
    label_path: Path = LABEL_PATH,
) -> PriceAdjustmentBuildResult:
    ensure_quant_dirs()
    manifest = build_price_adjustment_manifest(price_cache_root=price_cache_root, label_path=label_path)
    write_json(manifest_path, manifest)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_policy_report(manifest), encoding="utf-8")
    return PriceAdjustmentBuildResult(manifest_path=manifest_path, report_path=report_path, manifest=manifest)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build P1-A Card 2 price adjustment policy manifest and report.")
    parser.add_argument("--manifest-output", type=Path, default=PRICE_ADJUSTMENT_MANIFEST_PATH)
    parser.add_argument("--report-output", type=Path, default=PRICE_ADJUSTMENT_REPORT_PATH)
    parser.add_argument("--price-cache-root", type=Path, default=PRICE_CACHE_ROOT)
    parser.add_argument("--labels", type=Path, default=LABEL_PATH)
    args = parser.parse_args()
    result = write_price_adjustment_policy_outputs(
        manifest_path=args.manifest_output,
        report_path=args.report_output,
        price_cache_root=args.price_cache_root,
        label_path=args.labels,
    )
    print(
        json.dumps(
            {
                "manifest": workspace_relative(result.manifest_path),
                "report": workspace_relative(result.report_path),
                "policy_status": result.manifest["policy_status"],
                "formal_adjusted_return_status": result.manifest["formal_adjusted_return_status"],
                "price_row_count": result.manifest["price_row_count"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
