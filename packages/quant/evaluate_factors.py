from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from .research_io import (
    FACTOR_REPORT_PATH,
    HARDENED_LABEL_PATH,
    MIN_BUCKET_SAMPLE,
    fmt,
    group_key_text,
    hardened_label_summary,
    join_panel_labels,
    pct,
    status_for_sample,
    summary_stats,
)


FORMAL_NUMERIC_FACTORS: list[tuple[str, Callable[[dict[str, Any]], float | None], str]] = [
    ("ai_priority_score", lambda row: row.get("ai_priority_score"), "AI lane ranking score; formal only within AI lane."),
    ("ai_best_score", lambda row: row.get("ai_best_score"), "AI lane best underlying strategy score."),
    ("scan_capital_score", lambda row: row.get("scan_capital_score"), "Raw scan `scores.capital` adapter field."),
    ("scan_technical_score", lambda row: row.get("scan_technical_score"), "Raw scan `scores.technical` adapter field."),
]

FORMAL_GROUP_FACTORS: list[tuple[str, Callable[[dict[str, Any]], Any], str]] = [
    ("tier", lambda row: row.get("tier"), "AI lane A/B/C only; not a replacement for production tiers."),
    ("execution_gate_status", lambda row: row.get("execution_gate_status"), "Batch/context join; not candidate-native."),
    ("setup_type", lambda row: row.get("setup_type"), "AI setup grouping; weak buckets are insufficient_sample."),
    ("theme", lambda row: row.get("theme"), "Coverage/grouping only; no strong conclusion."),
]

RAW_SOURCE_FIELDS = [
    "score",
    "strategy_hits",
    "strategy_labels",
    "execution_quality_score",
    "watchlist_technical_score",
    "midday_score",
]

EXCLUDED_FIELDS = ["final_score", "strategy_bucket", "excess_return", "execution_realistic_return"]


def now_stamp() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


def is_ai_lane(panel: dict[str, Any]) -> bool:
    return panel.get("source_lane") == "research_backfill_ai_history"


def is_scan_lane(panel: dict[str, Any]) -> bool:
    return panel.get("source_lane") == "research_backfill_scan_history" and panel.get("pipeline_stage") == "scan_candidate"


def numeric_factor_rows(joined: list[dict[str, Any]], factor: str, getter: Callable[[dict[str, Any]], Any]) -> list[dict[str, Any]]:
    rows = []
    for item in joined:
        panel = item["panel"]
        if factor.startswith("ai_") and not is_ai_lane(panel):
            continue
        if factor.startswith("scan_") and not is_scan_lane(panel):
            continue
        value = getter(panel)
        if value is None:
            continue
        rows.append(item)
    return rows


def label_return(label: dict[str, Any], return_field: str) -> float | None:
    value = label.get(return_field)
    return float(value) if value is not None else None


def evaluate_numeric_factor(
    joined: list[dict[str, Any]],
    factor: str,
    getter: Callable[[dict[str, Any]], Any],
    note: str,
) -> dict[str, Any]:
    rows = numeric_factor_rows(joined, factor, getter)
    by_combo: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for item in rows:
        label = item["label"]
        by_combo[(label["entry_model"], int(label["holding_window_days"]))].append(item)

    combos = []
    for (entry_model, window), items in sorted(by_combo.items()):
        net_values = [label_return(item["label"], "net_return") for item in items]
        raw_values = [label_return(item["label"], "raw_return") for item in items]
        combos.append(
            {
                "entry_model": entry_model,
                "holding_window_days": window,
                "sample_size": len(items),
                "status": status_for_sample(len(items)),
                "net": summary_stats(value for value in net_values if value is not None),
                "raw": summary_stats(value for value in raw_values if value is not None),
            }
        )
    return {
        "field": factor,
        "type": "numeric_factor",
        "note": note,
        "sample_size": len(rows),
        "status": status_for_sample(len(rows)),
        "combos": combos,
        "conclusion": conclusion_text(status_for_sample(len(rows))),
    }


def evaluate_group_factor(
    joined: list[dict[str, Any]],
    field: str,
    getter: Callable[[dict[str, Any]], Any],
    note: str,
) -> dict[str, Any]:
    rows = []
    for item in joined:
        panel = item["panel"]
        if field == "tier" and not is_ai_lane(panel):
            continue
        if field == "setup_type" and not is_ai_lane(panel):
            continue
        if field == "execution_gate_status" and panel.get("execution_gate_scope") != "batch_context":
            continue
        rows.append(item)

    by_combo: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for item in rows:
        label = item["label"]
        by_combo[(label["entry_model"], int(label["holding_window_days"]))].append(item)

    combos = []
    for (entry_model, window), items in sorted(by_combo.items()):
        buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in items:
            buckets[group_key_text(getter(item["panel"]))].append(item)
        bucket_rows = []
        for bucket, bucket_items in sorted(buckets.items()):
            net = summary_stats(item["label"]["net_return"] for item in bucket_items if item["label"].get("net_return") is not None)
            bucket_rows.append(
                {
                    "bucket": bucket,
                    "sample_size": len(bucket_items),
                    "status": status_for_sample(len(bucket_items)),
                    "net": net,
                }
            )
        combos.append(
            {
                "entry_model": entry_model,
                "holding_window_days": window,
                "sample_size": len(items),
                "status": status_for_sample(len(items)),
                "buckets": bucket_rows,
            }
        )
    status = "research_only" if rows else "insufficient_sample"
    if all(bucket["sample_size"] < MIN_BUCKET_SAMPLE for combo in combos for bucket in combo.get("buckets", [])):
        status = "insufficient_sample"
    return {
        "field": field,
        "type": "group_factor",
        "note": note,
        "sample_size": len(rows),
        "status": status,
        "combos": combos,
        "conclusion": conclusion_text(status),
    }


def evaluate_tier_monotonicity(joined: list[dict[str, Any]]) -> dict[str, Any]:
    ai_rows = [item for item in joined if is_ai_lane(item["panel"]) and item["panel"].get("tier")]
    by_combo: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for item in ai_rows:
        label = item["label"]
        by_combo[(label["entry_model"], int(label["holding_window_days"]))].append(item)

    combos = []
    tier_order = ["A", "B", "C"]
    for (entry_model, window), items in sorted(by_combo.items()):
        buckets = {}
        for tier in tier_order:
            bucket_items = [item for item in items if item["panel"].get("tier") == tier]
            buckets[tier] = {
                "sample_size": len(bucket_items),
                "status": status_for_sample(len(bucket_items)),
                "net": summary_stats(item["label"]["net_return"] for item in bucket_items if item["label"].get("net_return") is not None),
            }
        means = [buckets[tier]["net"]["mean"] for tier in tier_order]
        has_enough = all(buckets[tier]["sample_size"] >= MIN_BUCKET_SAMPLE for tier in tier_order)
        monotonic = bool(has_enough and all(value is not None for value in means) and means[0] >= means[1] >= means[2])
        high_items = [item for item in items if item["panel"].get("tier") in {"A", "B"}]
        c_items = [item for item in items if item["panel"].get("tier") == "C"]
        high_vs_c_status = "insufficient_sample"
        if len(high_items) >= MIN_BUCKET_SAMPLE and len(c_items) >= MIN_BUCKET_SAMPLE:
            high_vs_c_status = "research_only"
        combos.append(
            {
                "entry_model": entry_model,
                "holding_window_days": window,
                "sample_size": len(items),
                "status": "research_only" if has_enough else "insufficient_sample",
                "monotonic_status": "research_only_monotonic" if monotonic else ("insufficient_sample" if not has_enough else "not_monotonic"),
                "high_vs_c_status": high_vs_c_status,
                "buckets": buckets,
            }
        )
    overall_status = "research_only" if any(combo["status"] == "research_only" for combo in combos) else "insufficient_sample"
    return {
        "field": "tier",
        "type": "tier_monotonicity",
        "sample_size": len(ai_rows),
        "status": overall_status,
        "combos": combos,
        "conclusion": conclusion_text(overall_status),
    }


def evaluate_ai_screening(joined: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [item for item in joined if item["panel"].get("source_lane") in {"research_backfill_ai_history", "research_backfill_scan_history"}]
    by_combo: dict[tuple[str, int], dict[str, list[dict[str, Any]]]] = defaultdict(lambda: {"scan": [], "ai": []})
    for item in rows:
        panel = item["panel"]
        label = item["label"]
        key = (label["entry_model"], int(label["holding_window_days"]))
        if is_scan_lane(panel):
            by_combo[key]["scan"].append(item)
        elif is_ai_lane(panel):
            by_combo[key]["ai"].append(item)
    combos = []
    for (entry_model, window), groups in sorted(by_combo.items()):
        scan_codes = {(item["panel"]["trade_date"], item["panel"]["code"]) for item in groups["scan"]}
        ai_codes = {(item["panel"]["trade_date"], item["panel"]["code"]) for item in groups["ai"]}
        overlap = len(scan_codes & ai_codes)
        status = "research_only" if len(groups["scan"]) >= MIN_BUCKET_SAMPLE and len(groups["ai"]) >= MIN_BUCKET_SAMPLE else "insufficient_sample"
        combos.append(
            {
                "entry_model": entry_model,
                "holding_window_days": window,
                "status": status,
                "scan_sample_size": len(groups["scan"]),
                "ai_sample_size": len(groups["ai"]),
                "same_day_code_overlap": overlap,
                "scan_net": summary_stats(item["label"]["net_return"] for item in groups["scan"] if item["label"].get("net_return") is not None),
                "ai_net": summary_stats(item["label"]["net_return"] for item in groups["ai"] if item["label"].get("net_return") is not None),
                "selection_bias_note": "Comparison is scan-pool anchored; unmatched AI/scan lineage remains report-only.",
            }
        )
    return {
        "field": "ai_screening_vs_scan",
        "type": "post_hoc_validation",
        "status": "research_only" if any(combo["status"] == "research_only" for combo in combos) else "insufficient_sample",
        "combos": combos,
        "conclusion": "Report-only comparison; no production selection claim.",
    }


def evaluate_midday(joined: list[dict[str, Any]]) -> dict[str, Any]:
    midday_rows = [item for item in joined if item["panel"].get("pipeline_stage") in {"confirmed", "downgraded", "fresh_candidate", "midday_checked"}]
    by_stage = Counter(item["panel"].get("pipeline_stage") for item in midday_rows)
    return {
        "field": "midday_confirmation",
        "type": "post_hoc_validation",
        "sample_size": len(midday_rows),
        "stage_counts": dict(by_stage),
        "status": "insufficient_sample",
        "conclusion": "Formal label coverage is unavailable or below sample threshold; keep midday evidence as coverage-only.",
    }


def conclusion_text(status: str) -> str:
    if status == "insufficient_sample":
        return "insufficient_sample; no positive conclusion."
    return "research_only; no production or execution conclusion."


def has_value(value: Any) -> bool:
    return value not in (None, "", [], {})


def raw_source_coverage(joined: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for field in RAW_SOURCE_FIELDS:
        with_value = [item for item in joined if has_value(item["panel"].get(field))]
        lane_counts = Counter(item["panel"].get("source_lane") for item in with_value)
        score_kind_counts = Counter()
        if field == "score":
            score_kind_counts = Counter(item["panel"].get("score_kind") for item in with_value)
        rows.append(
            {
                "field": field,
                "sample_size": len(with_value),
                "coverage_rate": len(with_value) / len(joined) if joined else 0.0,
                "status": "raw_source_only",
                "lanes": dict(lane_counts),
                "score_kinds": dict(score_kind_counts),
                "conclusion": "Diagnostics only; not part of formal factor evidence.",
            }
        )
    return rows


def build_factor_evaluation() -> dict[str, Any]:
    joined = join_panel_labels(available_only=True)
    hardening = hardened_label_summary()
    panel_counter = Counter(item["panel"]["source_lane"] for item in joined)
    numeric = [evaluate_numeric_factor(joined, field, getter, note) for field, getter, note in FORMAL_NUMERIC_FACTORS]
    groups = [evaluate_group_factor(joined, field, getter, note) for field, getter, note in FORMAL_GROUP_FACTORS]
    tier = evaluate_tier_monotonicity(joined)
    ai_screening = evaluate_ai_screening(joined)
    midday = evaluate_midday(joined)
    return {
        "generated_at": now_stamp(),
        "scope": "Sprint 2 report-only factor evaluation",
        "label_scope": "available_research_only only; hardened labels are used as a sidecar for status/guardrails",
        "hardened_label_input": {
            "path": str(HARDENED_LABEL_PATH),
            "rows": hardening["rows"],
            "formal_label_ready_count": hardening["formal_label_ready_count"],
            "formal_execution_eligible_count": hardening["formal_execution_eligible_count"],
        },
        "hardened_label_summary": hardening,
        "sample_size": len(joined),
        "samples_by_source_lane": dict(panel_counter),
        "formal_numeric_factors": numeric,
        "formal_group_factors": groups,
        "tier_monotonicity": tier,
        "ai_screening_validation": ai_screening,
        "midday_validation": midday,
        "raw_source_coverage": raw_source_coverage(joined),
        "raw_source_fields": RAW_SOURCE_FIELDS,
        "excluded_fields": EXCLUDED_FIELDS,
        "guardrails": [
            "final_score_excluded",
            "score_lane_scoped_only",
            "benchmark_unavailable_no_excess_return",
            "hardened_labels_report_only_sidecar",
            "execution_gate_batch_context_only",
            "report_only_no_production_sorting",
        ],
    }


def render_factor_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Prism Quant Sprint 2 Factor Evaluation",
        "",
        f"Generated at: {result['generated_at']}",
        "",
        "Scope: report-only factor evaluation. This report does not change production sorting, A/B/C tiers, pages, Prism Edge, or any trading action.",
        "",
        "## Dataset",
        "",
        f"- Joined available research-only label rows: {result['sample_size']}.",
        f"- Hardened labels input: `{result['hardened_label_input']['path']}`.",
        f"- Hardened labels count: {result['hardened_label_input']['rows']}.",
        f"- Hardened formal_label_ready count: {result['hardened_label_input']['formal_label_ready_count']}.",
        f"- Hardened formal_execution_eligible count: {result['hardened_label_input']['formal_execution_eligible_count']}.",
        f"- Samples by source lane: {result['samples_by_source_lane']}.",
        "- Excess returns are not computed because benchmark data is not frozen.",
        "- `final_score` and `strategy_bucket` are excluded from formal evaluation.",
        "",
        "## Hardened Label Status",
        "",
        f"- Benchmark status distribution: {result['hardened_label_summary']['benchmark_status_counts']}.",
        f"- Excess return status distribution: {result['hardened_label_summary']['excess_return_status_counts']}.",
        f"- Internal benchmark status distribution: {result['hardened_label_summary']['internal_benchmark_status_counts']}.",
        f"- Price adjustment status distribution: {result['hardened_label_summary']['price_adjustment_status_counts']}.",
        f"- Formal adjusted return status distribution: {result['hardened_label_summary']['formal_adjusted_return_status_counts']}.",
        f"- Execution realism status distribution: {result['hardened_label_summary']['execution_realism_status_counts']}.",
        f"- Research-only reason distribution: {result['hardened_label_summary']['research_only_reason_counts']}.",
        "- Positive-looking raw/net metrics remain `research_only`; no formal excess, adjusted, or execution-realistic return is emitted.",
        "",
        "## Formal Numeric Factors",
        "",
        "| Field | Samples | Status | Best visible 5D next_open net mean | Notes |",
        "| --- | ---: | --- | ---: | --- |",
    ]
    for item in result["formal_numeric_factors"]:
        best = combo_lookup(item["combos"], "next_open", 5)
        lines.append(
            f"| `{item['field']}` | {item['sample_size']} | {item['status']} | {pct((best.get('net') or {}).get('mean') if best else None)} | {item['note']} |"
        )
    lines += [
        "",
        "## Group Factors",
        "",
        "| Field | Samples | Status | Notes |",
        "| --- | ---: | --- | --- |",
    ]
    for item in result["formal_group_factors"]:
        lines.append(f"| `{item['field']}` | {item['sample_size']} | {item['status']} | {item['note']} |")
    lines += [
        "",
        "## Group Bucket Sample Guardrails",
        "",
        "| Field | Insufficient bucket combos | Examples |",
        "| --- | ---: | --- |",
    ]
    for item in result["formal_group_factors"]:
        insufficient = []
        for combo in item["combos"]:
            for bucket in combo.get("buckets", []):
                if bucket["status"] == "insufficient_sample":
                    insufficient.append(
                        f"{combo['entry_model']}/{combo['holding_window_days']}D `{bucket['bucket']}` n={bucket['sample_size']}"
                    )
        examples = "; ".join(insufficient[:5]) if insufficient else "none"
        if len(insufficient) > 5:
            examples += f"; ... +{len(insufficient) - 5} more"
        lines.append(f"| `{item['field']}` | {len(insufficient)} | {examples} |")
    lines += [
        "",
        "## Tier Monotonicity",
        "",
        "| Entry | Window | Status | Monotonic status | A n/mean | B n/mean | C n/mean |",
        "| --- | ---: | --- | --- | ---: | ---: | ---: |",
    ]
    for combo in result["tier_monotonicity"]["combos"]:
        buckets = combo["buckets"]
        lines.append(
            "| {entry} | {window} | {status} | {mono} | {a_n}/{a_mean} | {b_n}/{b_mean} | {c_n}/{c_mean} |".format(
                entry=combo["entry_model"],
                window=combo["holding_window_days"],
                status=combo["status"],
                mono=combo["monotonic_status"],
                a_n=buckets["A"]["sample_size"],
                a_mean=pct(buckets["A"]["net"]["mean"]),
                b_n=buckets["B"]["sample_size"],
                b_mean=pct(buckets["B"]["net"]["mean"]),
                c_n=buckets["C"]["sample_size"],
                c_mean=pct(buckets["C"]["net"]["mean"]),
            )
        )
    lines += [
        "",
        "## Execution Gate Evaluation",
        "",
        "Execution gate is evaluated only as `execution_gate_scope=batch_context`; it is not treated as a candidate-native field.",
    ]
    gate = next(item for item in result["formal_group_factors"] if item["field"] == "execution_gate_status")
    lines += render_group_combo_table(gate, "next_open", 5)
    lines += [
        "",
        "## AI Screening Validation",
        "",
        "| Entry | Window | Status | Scan n/net mean | AI n/net mean | Same-day code overlap |",
        "| --- | ---: | --- | ---: | ---: | ---: |",
    ]
    for combo in result["ai_screening_validation"]["combos"]:
        lines.append(
            f"| {combo['entry_model']} | {combo['holding_window_days']} | {combo['status']} | "
            f"{combo['scan_sample_size']}/{pct(combo['scan_net']['mean'])} | {combo['ai_sample_size']}/{pct(combo['ai_net']['mean'])} | {combo['same_day_code_overlap']} |"
        )
    lines += [
        "",
        "- Selection-bias guardrail: comparison is scan-pool anchored where lineage is visible; unmatched AI/scan lineage remains report-only.",
        "",
        "## Midday Validation",
        "",
        f"- Status: {result['midday_validation']['status']}.",
        f"- Stage counts with formal labels: {result['midday_validation']['stage_counts']}.",
        "- Confirmed/downgraded/fresh candidates remain coverage-only until enough PIT-clean labeled samples exist.",
        "",
        "## Raw/Source Only",
        "",
        "- Raw/source fields retained for diagnostics only: " + ", ".join(f"`{field}`" for field in result["raw_source_fields"]) + ".",
        "- Excluded fields: " + ", ".join(f"`{field}`" for field in result["excluded_fields"]) + ".",
        "",
        "| Field | Samples | Coverage | Status | Lane / kind guardrail |",
        "| --- | ---: | ---: | --- | --- |",
    ]
    for item in result["raw_source_coverage"]:
        if item["field"] == "score":
            guardrail = f"lanes={item['lanes']}; score_kinds={item['score_kinds']}"
        else:
            guardrail = f"lanes={item['lanes']}"
        lines.append(f"| `{item['field']}` | {item['sample_size']} | {pct(item['coverage_rate'])} | {item['status']} | {guardrail} |")
    lines += [
        "",
        "`score` remains lane-scoped and score-kind-scoped; it is not merged across lanes or promoted to a formal factor.",
        "",
        "## Guardrails",
        "",
        "- All conclusions are report-only.",
        "- Buckets below 30 samples are `insufficient_sample` and receive no positive conclusion.",
        "- No excess return is calculated or claimed.",
        "- No production sorting, A/B/C replacement, page, Prism Edge, theme state machine, or ML change is made.",
    ]
    return "\n".join(lines) + "\n"


def combo_lookup(combos: list[dict[str, Any]], entry_model: str, window: int) -> dict[str, Any] | None:
    for combo in combos:
        if combo["entry_model"] == entry_model and int(combo["holding_window_days"]) == window:
            return combo
    return None


def render_group_combo_table(item: dict[str, Any], entry_model: str, window: int) -> list[str]:
    combo = combo_lookup(item["combos"], entry_model, window)
    if not combo:
        return ["", "_No matching group combo._"]
    lines = [
        "",
        f"Representative combo: `{entry_model}` / {window}D.",
        "",
        "| Bucket | Samples | Status | Net mean | Win rate |",
        "| --- | ---: | --- | ---: | ---: |",
    ]
    for bucket in combo["buckets"]:
        lines.append(
            f"| `{bucket['bucket']}` | {bucket['sample_size']} | {bucket['status']} | {pct(bucket['net']['mean'])} | {pct(bucket['net']['win_rate'])} |"
        )
    return lines


def write_factor_report(path: Path = FACTOR_REPORT_PATH) -> dict[str, Any]:
    result = build_factor_evaluation()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_factor_markdown(result), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Sprint 2 report-only factor evaluation.")
    parser.add_argument("--output", type=Path, default=FACTOR_REPORT_PATH)
    args = parser.parse_args()
    result = write_factor_report(args.output)
    print(json.dumps({"output": str(args.output), "sample_size": result["sample_size"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
