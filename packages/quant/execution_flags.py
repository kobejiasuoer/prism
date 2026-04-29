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

from .config import load_quant_research_config
from .paths import EXECUTION_ROOT, LABELS_ROOT, REPORTS_ROOT, REPO_ROOT, ensure_quant_dirs, workspace_relative
from .research_io import load_jsonl, write_json


PRICE_CACHE_ROOT = REPO_ROOT / "stock-screener" / "data" / "research_backfill" / "cache" / "price_kline"
LABEL_PATH = LABELS_ROOT / "forward_return_labels.jsonl"
EXECUTION_FLAGS_MANIFEST_PATH = EXECUTION_ROOT / "execution_flags_manifest.json"
EXECUTION_FLAGS_REPORT_PATH = REPORTS_ROOT / "execution_flags_coverage_latest.md"

RAW_PRICE_FIELDS = ["open", "high", "low", "close", "volume", "amount"]
SUSPEND_FIELDS = ["is_suspended", "suspend_status", "resume_date", "trading_status", "is_trading"]
LIMIT_FIELDS = [
    "limit_up_price",
    "limit_down_price",
    "open_at_limit_up",
    "open_at_limit_down",
    "close_at_limit_up",
    "close_at_limit_down",
    "limit_status",
    "limit_up_down_status",
]
FAILED_ORDER_FIELDS = ["order_status", "failed_order", "failure_reason", "fill_status"]
PARTIAL_FILL_FIELDS = ["partial_fill", "fill_qty_pct", "fill_ratio", "filled_notional", "participation_rate"]


@dataclass(frozen=True)
class ExecutionFlagsBuildResult:
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
    field_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    dates: list[str] = []
    total_rows = 0
    file_hashes: list[str] = []
    unreadable: list[dict[str, str]] = []
    sample_artifacts: list[dict[str, Any]] = []

    for path in files:
        try:
            rows = parse_json(path)
        except Exception as exc:
            unreadable.append({"path": workspace_relative(path), "error": str(exc)})
            continue
        if not isinstance(rows, list):
            unreadable.append({"path": workspace_relative(path), "error": "json root is not a list"})
            continue
        file_hash = sha256_file(path)
        file_hashes.append(file_hash)
        if len(sample_artifacts) < 5:
            sample_artifacts.append({"path": workspace_relative(path), "sha256": file_hash, "row_count": len(rows)})
        for row in rows:
            if not isinstance(row, dict):
                continue
            total_rows += 1
            for field, value in row.items():
                if value not in (None, "", [], {}):
                    field_counts[str(field)] += 1
            source_counts[str(row.get("source") or "<missing>")] += 1
            if row.get("date"):
                dates.append(str(row["date"]))

    aggregate = hashlib.sha256("\n".join(file_hashes).encode("utf-8")).hexdigest() if file_hashes else None
    return {
        "root": workspace_relative(price_cache_root),
        "artifact_count": len(files),
        "readable_artifact_count": len(file_hashes),
        "aggregate_source_hash": aggregate,
        "sample_artifacts": sample_artifacts,
        "unreadable_artifacts": unreadable,
        "row_count": total_rows,
        "date_coverage": {
            "start": min(dates) if dates else None,
            "end": max(dates) if dates else None,
            "unique_dates": len(set(dates)),
        },
        "field_counts": dict(sorted(field_counts.items())),
        "source_counts": dict(source_counts),
        "raw_field_availability": {
            field: {
                "available": total_rows > 0 and field_counts.get(field, 0) == total_rows,
                "non_null_rows": field_counts.get(field, 0),
                "coverage_rate": field_counts.get(field, 0) / total_rows if total_rows else 0.0,
            }
            for field in RAW_PRICE_FIELDS
        },
    }


def top_level_field_counts(rows: list[dict[str, Any]], fields: list[str]) -> dict[str, int]:
    return {field: sum(1 for row in rows if row.get(field) not in (None, "", [], {})) for field in fields}


def rows_missing_flag(rows: list[dict[str, Any]], flag: str) -> int:
    return sum(flag in (row.get("execution_data_missing") or []) for row in rows)


def availability_block(
    *,
    status: str,
    candidate_fields: list[str],
    price_field_counts: dict[str, int],
    label_field_counts: dict[str, int],
    rows_marked_missing: int,
    notes: str,
    conservative_flag: str,
) -> dict[str, Any]:
    return {
        "status": status,
        "machine_readable_available": False,
        "candidate_fields": candidate_fields,
        "price_field_non_null_counts": {field: price_field_counts.get(field, 0) for field in candidate_fields},
        "label_field_non_null_counts": {field: label_field_counts.get(field, 0) for field in candidate_fields},
        "label_rows_marked_missing": rows_marked_missing,
        "conservative_flag": conservative_flag,
        "notes": notes,
    }


def inspect_labels(label_path: Path) -> dict[str, Any]:
    labels = load_jsonl(label_path)
    execution_missing = Counter(flag for label in labels for flag in (label.get("execution_data_missing") or []))
    cost_bps = Counter(str(label.get("cost_bps")) for label in labels)
    entry_models = Counter(label.get("entry_model") for label in labels)
    holding_windows = Counter(str(label.get("holding_window_days")) for label in labels)
    formal_execution = Counter("true" if label.get("formal_execution_eligible") is True else "false" for label in labels)
    return {
        "label_path": workspace_relative(label_path),
        "label_count": len(labels),
        "label_status_counts": dict(Counter(label.get("label_status") for label in labels)),
        "label_scope_counts": dict(Counter(label.get("label_scope") for label in labels)),
        "formal_execution_eligible_counts": dict(formal_execution),
        "execution_data_missing_counts": dict(execution_missing),
        "cost_bps_counts": dict(cost_bps),
        "entry_model_counts": dict(entry_models),
        "holding_window_counts": dict(holding_windows),
        "rows_with_order_status": sum("order_status" in label for label in labels),
        "rows_with_execution_flags": sum("execution_flags" in label for label in labels),
        "rows_with_execution_realistic_return": sum("execution_realistic_return" in label for label in labels),
    }


def roundtrip_cost_bps(transaction_cost: dict[str, Any]) -> float:
    impact = transaction_cost.get("impact_cost") or {}
    return (
        float(transaction_cost.get("buy_commission_bps") or 0)
        + float(transaction_cost.get("sell_commission_bps") or 0)
        + float(transaction_cost.get("stamp_tax_bps") or 0)
        + float(transaction_cost.get("slippage_bps") or 0) * 2
        + float(impact.get("placeholder_bps") or 0)
    )


def build_execution_flags_manifest(
    *,
    price_cache_root: Path = PRICE_CACHE_ROOT,
    label_path: Path = LABEL_PATH,
) -> dict[str, Any]:
    price = inspect_price_cache(price_cache_root)
    labels = load_jsonl(label_path)
    label_inventory = inspect_labels(label_path)
    config = load_quant_research_config()
    price_fields = price["field_counts"]
    label_fields = Counter()
    for label in labels:
        for field, value in label.items():
            if value not in (None, "", [], {}):
                label_fields[str(field)] += 1

    suspend = availability_block(
        status="unavailable",
        candidate_fields=SUSPEND_FIELDS,
        price_field_counts=price_fields,
        label_field_counts=dict(label_fields),
        rows_marked_missing=rows_missing_flag(labels, "suspend_status"),
        notes="No explicit machine-readable suspend or resume status exists. Missing price rows or zero volume are not treated as formal suspend proof.",
        conservative_flag="suspend_status_unavailable",
    )
    limit = availability_block(
        status="unavailable",
        candidate_fields=LIMIT_FIELDS,
        price_field_counts=price_fields,
        label_field_counts=dict(label_fields),
        rows_marked_missing=rows_missing_flag(labels, "limit_up_down_status"),
        notes="No explicit limit up/down prices or at-limit flags exist. OHLCV-based approximation is deferred and not formal execution evidence.",
        conservative_flag="limit_up_down_status_unavailable",
    )
    failed_order = availability_block(
        status="unavailable",
        candidate_fields=FAILED_ORDER_FIELDS,
        price_field_counts=price_fields,
        label_field_counts=dict(label_fields),
        rows_marked_missing=rows_missing_flag(labels, "failed_order"),
        notes="No broker/order ledger or source-provided failed order status exists. Card 3 does not infer real failed orders.",
        conservative_flag="failed_order_unavailable",
    )
    partial_fill = availability_block(
        status="deferred",
        candidate_fields=PARTIAL_FILL_FIELDS,
        price_field_counts=price_fields,
        label_field_counts=dict(label_fields),
        rows_marked_missing=rows_missing_flag(labels, "partial_fill"),
        notes="Volume and amount exist for raw diagnostics, but no order notional, participation-rate policy, fill ratio, or broker fills exist.",
        conservative_flag="partial_fill_unavailable",
    )

    transaction_cost = config.data.get("transaction_cost") or {}
    portfolio = config.data.get("portfolio") or {}
    entry_models = config.data.get("entry_models") or {}
    return {
        "schema_version": "1.0",
        "generated_at": now_stamp(),
        "scope": "P1-A Card 3 execution flags and execution data availability",
        "production_impact": "none",
        "code_revision": git_revision(),
        "inspected_label_count": label_inventory["label_count"],
        "inspected_price_row_count": price["row_count"],
        "price_source": {
            "root": price["root"],
            "artifact_count": price["artifact_count"],
            "readable_artifact_count": price["readable_artifact_count"],
            "aggregate_source_hash": price["aggregate_source_hash"],
            "date_coverage": price["date_coverage"],
            "raw_field_availability": price["raw_field_availability"],
            "source_counts": price["source_counts"],
            "sample_artifacts": price["sample_artifacts"],
        },
        "available_execution_data": {
            "raw_open_high_low_close": all(price["raw_field_availability"][field]["available"] for field in ["open", "high", "low", "close"]),
            "raw_volume_amount": all(price["raw_field_availability"][field]["available"] for field in ["volume", "amount"]),
            "configured_transaction_cost": bool(transaction_cost),
            "entry_models_configured": entry_models.get("supported", []),
        },
        "suspend_status_availability": suspend,
        "limit_up_down_status_availability": limit,
        "failed_order_availability": failed_order,
        "partial_fill_availability": partial_fill,
        "deferred_execution_fields": [
            "official_frozen_trading_calendar",
            "suspend_status_source",
            "limit_up_down_status_source",
            "order_ledger",
            "failed_order_rule_application",
            "partial_fill_rule_application",
            "lot_size",
            "participation_rate",
            "exit_delay_after_suspend_or_limit_down",
        ],
        "t_plus_one_policy": {
            "configured_rebalance_rule": portfolio.get("rebalance_rule"),
            "primary_entry_model": entry_models.get("primary"),
            "supported_entry_models": entry_models.get("supported", []),
            "current_handling": "conservative_next_observed_trade_row_entry",
            "calendar_source": "symbol_price_rows_not_official_frozen_exchange_calendar",
            "status": "research_only_not_execution_realistic",
            "notes": "Current labels use next_open / next_close after signal date, but there is no canonical order ledger or official frozen trading calendar in this card.",
        },
        "cost_policy_reference": {
            "config_path": workspace_relative(config.path),
            "config_checksum": config.checksum,
            "transaction_cost": transaction_cost,
            "roundtrip_cost_bps": round(roundtrip_cost_bps(transaction_cost), 4),
            "label_cost_bps_counts": label_inventory["cost_bps_counts"],
            "minimum_commission_status": "notional_unavailable_research_only",
        },
        "execution_realism_status": "not_ready_research_only_simulation_execution_data_missing",
        "label_implications": {
            **label_inventory,
            "current_labels_remain": "research_only_execution_missing",
            "formal_execution_eligible_allowed": False,
            "execution_realistic_return_allowed": False,
            "formal_label_ready_allowed": False,
            "required_before_upgrade": [
                "machine-readable suspend status",
                "machine-readable limit up/down prices and at-limit flags",
                "failed/blocked order rules with reasons",
                "partial-fill policy with notional, lot size, and participation rate",
                "official frozen trading calendar",
                "execution flags written to labels or accepted sidecar",
            ],
        },
        "conservative_flags": [
            "suspend_status_unavailable",
            "limit_up_down_status_unavailable",
            "failed_order_unavailable",
            "partial_fill_unavailable",
            "official_calendar_unavailable",
            "order_ledger_unavailable",
            "execution_realistic_return_unavailable",
        ],
        "guardrails": [
            "report_only",
            "research_only_simulation",
            "no_external_data_fetch",
            "no_real_fill_inference",
            "no_unavailable_execution_field_as_available",
            "no_execution_realistic_backtest_generation",
            "no_formal_execution_eligible_upgrade",
            "no_factor_backtest_health_rerun",
            "no_production_sorting",
            "no_abc_replacement",
            "no_page",
            "no_prism_edge",
            "no_expected_5d_frontend",
            "no_ml",
        ],
    }


def render_execution_report(manifest: dict[str, Any]) -> str:
    price = manifest["price_source"]
    label = manifest["label_implications"]
    lines = [
        "# Prism Quant P1-A Card 3 Execution Flags Coverage",
        "",
        f"Generated at: {manifest['generated_at']}",
        "",
        "Scope: P1-A Card 3 only. This report freezes execution-data availability and conservative flags; it does not regenerate labels, execution-realistic backtests, factor reports, portfolio reports, or quant health.",
        "",
        "## Summary",
        "",
        f"- Production impact: `{manifest['production_impact']}`.",
        f"- Execution realism status: `{manifest['execution_realism_status']}`.",
        f"- Inspected labels: {manifest['inspected_label_count']}.",
        f"- Inspected price rows: {manifest['inspected_price_row_count']}.",
        "- Current backtest remains `research_only_simulation`.",
        "- No label can be upgraded to `formal_execution_eligible` under current data.",
        "- No execution-realistic return can be claimed.",
        "",
        "## Available Execution-Adjacent Data",
        "",
        f"- Raw price source: `{price['root']}`.",
        f"- Price artifacts: {price['artifact_count']} JSON files; readable: {price['readable_artifact_count']}.",
        f"- Date coverage: {price['date_coverage']['start']} to {price['date_coverage']['end']} ({price['date_coverage']['unique_dates']} unique dates).",
        f"- Source counts: {price['source_counts']}.",
        f"- Raw OHLC available: {manifest['available_execution_data']['raw_open_high_low_close']}.",
        f"- Raw volume/amount available: {manifest['available_execution_data']['raw_volume_amount']}.",
        f"- Transaction cost configured: {manifest['available_execution_data']['configured_transaction_cost']}.",
        "",
        "## Raw Price Field Coverage",
        "",
        "| Field | Available | Non-null rows | Coverage |",
        "| --- | --- | ---: | ---: |",
    ]
    for field, item in price["raw_field_availability"].items():
        lines.append(f"| `{field}` | {str(item['available']).lower()} | {item['non_null_rows']} | {item['coverage_rate'] * 100:.2f}% |")
    lines += [
        "",
        "## Unavailable Or Deferred Execution Data",
        "",
        "| Area | Status | Label rows marked missing | Conservative flag | Notes |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for title, key in [
        ("Suspend status", "suspend_status_availability"),
        ("Limit up/down status", "limit_up_down_status_availability"),
        ("Failed order", "failed_order_availability"),
        ("Partial fill", "partial_fill_availability"),
    ]:
        item = manifest[key]
        lines.append(f"| {title} | `{item['status']}` | {item['label_rows_marked_missing']} | `{item['conservative_flag']}` | {item['notes']} |")
    lines += [
        "",
        "## Conservative Flags",
        "",
    ]
    for flag in manifest["conservative_flags"]:
        lines.append(f"- `{flag}`")
    lines += [
        "",
        "## Deferred Items",
        "",
    ]
    for item in manifest["deferred_execution_fields"]:
        lines.append(f"- `{item}`")
    t1 = manifest["t_plus_one_policy"]
    cost = manifest["cost_policy_reference"]
    lines += [
        "",
        "## T+1 And Cost Policy",
        "",
        f"- Configured rebalance rule: `{t1['configured_rebalance_rule']}`.",
        f"- Primary entry model: `{t1['primary_entry_model']}`.",
        f"- Supported entry models: {t1['supported_entry_models']}.",
        f"- Current handling: `{t1['current_handling']}`.",
        f"- Calendar source: `{t1['calendar_source']}`.",
        f"- T+1 status: `{t1['status']}`.",
        f"- Cost config: `{cost['config_path']}` checksum `{cost['config_checksum'][:12]}`.",
        f"- Transaction cost: {cost['transaction_cost']}.",
        f"- Roundtrip cost bps: {cost['roundtrip_cost_bps']}.",
        f"- Minimum commission status: `{cost['minimum_commission_status']}`.",
        "",
        "## Label Implications",
        "",
        f"- Label status counts: {label['label_status_counts']}.",
        f"- Formal execution eligible counts: {label['formal_execution_eligible_counts']}.",
        f"- Execution missing counts: {label['execution_data_missing_counts']}.",
        f"- Rows with execution flags field: {label['rows_with_execution_flags']}.",
        f"- Rows with order status field: {label['rows_with_order_status']}.",
        f"- Rows with execution-realistic return: {label['rows_with_execution_realistic_return']}.",
        f"- Current label implication: `{label['current_labels_remain']}`.",
        "",
        "## Backtest And Quant Health Impact",
        "",
        "- Existing minimal backtest remains `research_only_simulation` because suspend, limit up/down, failed order, partial fill, official calendar, and order ledger data are unavailable.",
        "- Quant health should continue to show execution data as unavailable for execution-realistic conclusions.",
        "- Factor/backtest/health reports are not regenerated by this card.",
        "- No production-ready, execution-realistic, or deployable return statement is supported.",
        "",
        "## Data Needed Before Upgrade",
        "",
    ]
    for item in label["required_before_upgrade"]:
        lines.append(f"- {item}.")
    lines += [
        "",
        "## Guardrails",
        "",
    ]
    for guardrail in manifest["guardrails"]:
        lines.append(f"- `{guardrail}`")
    return "\n".join(lines) + "\n"


def write_execution_flags_outputs(
    *,
    manifest_path: Path = EXECUTION_FLAGS_MANIFEST_PATH,
    report_path: Path = EXECUTION_FLAGS_REPORT_PATH,
    price_cache_root: Path = PRICE_CACHE_ROOT,
    label_path: Path = LABEL_PATH,
) -> ExecutionFlagsBuildResult:
    ensure_quant_dirs()
    manifest = build_execution_flags_manifest(price_cache_root=price_cache_root, label_path=label_path)
    write_json(manifest_path, manifest)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_execution_report(manifest), encoding="utf-8")
    return ExecutionFlagsBuildResult(manifest_path=manifest_path, report_path=report_path, manifest=manifest)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build P1-A Card 3 execution flags availability manifest and report.")
    parser.add_argument("--manifest-output", type=Path, default=EXECUTION_FLAGS_MANIFEST_PATH)
    parser.add_argument("--report-output", type=Path, default=EXECUTION_FLAGS_REPORT_PATH)
    parser.add_argument("--price-cache-root", type=Path, default=PRICE_CACHE_ROOT)
    parser.add_argument("--labels", type=Path, default=LABEL_PATH)
    args = parser.parse_args()
    result = write_execution_flags_outputs(
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
                "execution_realism_status": result.manifest["execution_realism_status"],
                "inspected_label_count": result.manifest["inspected_label_count"],
                "inspected_price_row_count": result.manifest["inspected_price_row_count"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
