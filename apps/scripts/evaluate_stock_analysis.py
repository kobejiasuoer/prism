#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from prism_canonical import (
    load_confirmation,
    load_decision_brief,
    load_research_review,
    load_screening_batch,
    load_watchlist_snapshot,
)

DIMENSION_MAX = {
    "data_governance": 20,
    "analysis_rule_quality": 20,
    "execution_risk_control": 20,
    "output_usability": 15,
    "historical_validation": 15,
    "stability_productization": 10,
}

TIER_ORDER = (
    "below_basic",
    "basic_usable",
    "professional_usable",
    "product_ready",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--min-tier", choices=TIER_ORDER[1:])
    parser.add_argument("--fail-on-hard-gates", action="store_true")
    return parser.parse_args()


def load_manifest(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def empty_dimension_scores() -> dict[str, dict[str, int]]:
    return {name: {"earned": 0, "max": max_value} for name, max_value in DIMENSION_MAX.items()}


def tier_rank(tier: str) -> int:
    return TIER_ORDER.index(tier)


def tier_total_score_requirement(tier: str | None) -> int | None:
    if tier == "basic_usable":
        return 70
    if tier == "professional_usable":
        return 82
    if tier == "product_ready":
        return 90
    return None


def dimension_thresholds_for_tier(tier: str) -> dict[str, int]:
    if tier == "professional_usable":
        return {
            "data_governance": math.ceil(DIMENSION_MAX["data_governance"] * 0.75),
            "execution_risk_control": math.ceil(DIMENSION_MAX["execution_risk_control"] * 0.75),
            "historical_validation": math.ceil(DIMENSION_MAX["historical_validation"] * 0.75),
        }
    if tier == "product_ready":
        return {name: math.ceil(max_value * 0.85) for name, max_value in DIMENSION_MAX.items()}
    return {}


def next_tier_name(tier: str) -> str | None:
    index = tier_rank(tier)
    if index >= len(TIER_ORDER) - 1:
        return None
    return TIER_ORDER[index + 1]


def build_tier_requirements(
    target_tier: str | None,
    total_score: int,
    hard_gate_failures: list[str],
    dimension_scores: dict[str, dict[str, int]],
) -> list[dict[str, Any]]:
    if not target_tier:
        return []

    requirements: list[dict[str, Any]] = []
    if tier_rank(target_tier) >= tier_rank("basic_usable") and hard_gate_failures:
        requirements.append(
            {
                "type": "hard_gates_clear",
                "tier": target_tier,
                "count": len(hard_gate_failures),
                "message": f"Clear {len(hard_gate_failures)} hard gate failures before qualifying for {target_tier}.",
            }
        )

    required_total = tier_total_score_requirement(target_tier)
    if required_total is not None and total_score < required_total:
        requirements.append(
            {
                "type": "total_score",
                "tier": target_tier,
                "earned": total_score,
                "required": required_total,
                "gap": required_total - total_score,
                "message": f"Total score needs {required_total} (current {total_score}) for {target_tier}.",
            }
        )

    for dimension, required in dimension_thresholds_for_tier(target_tier).items():
        earned = dimension_scores[dimension]["earned"]
        if earned >= required:
            continue
        requirements.append(
            {
                "type": "dimension_threshold",
                "tier": target_tier,
                "dimension": dimension,
                "earned": earned,
                "required": required,
                "gap": required - earned,
                "message": f"{dimension} needs {required}/{dimension_scores[dimension]['max']} (current {earned}) for {target_tier}.",
            }
        )

    return requirements


def summarize_payload(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    if name == "watchlist":
        return {
            "generated_at": payload.get("generated_at"),
            "trade_date": payload.get("trade_date"),
            "stock_count": payload.get("stock_count"),
            "priority_codes": payload.get("priority_codes") or [],
        }
    if name == "screening":
        market_regime = payload.get("market_regime") or {}
        execution_gate = market_regime.get("execution_gate") or {}
        return {
            "generated_at": payload.get("generated_at"),
            "candidate_count": payload.get("candidate_count"),
            "approved_count": payload.get("approved_count"),
            "caution_count": payload.get("caution_count"),
            "excluded_count": payload.get("excluded_count"),
            "execution_gate_status": execution_gate.get("status"),
        }
    if name == "midday_confirmation":
        counts = payload.get("counts") or {}
        return {
            "generated_at": payload.get("generated_at"),
            "validation_status": payload.get("validation_status"),
            "confirmed_count": counts.get("confirmed"),
            "downgraded_count": counts.get("downgraded"),
            "fresh_candidates_count": counts.get("fresh_candidates"),
        }
    if name == "decision_brief":
        summary = payload.get("summary") or {}
        return {
            "generated_at": payload.get("generated_at"),
            "trade_date": payload.get("trade_date"),
            "open_new_positions": summary.get("open_new_positions"),
            "position_cap": summary.get("position_cap"),
            "main_theme": summary.get("main_theme"),
        }
    return {}


def try_load_artifact(loader, name: str, path_key: str, case: dict[str, Any]) -> dict[str, Any]:
    path_value = case.get(path_key)
    if not path_value:
        return {"status": "missing", "path": None, "error": None, "payload": None, "summary": {}}
    try:
        payload = loader(path=path_value)
        return {
            "status": "loaded",
            "path": path_value,
            "error": None,
            "payload": payload,
            "summary": summarize_payload(name, payload),
        }
    except Exception as exc:
        return {
            "status": "error",
            "path": path_value,
            "error": str(exc),
            "payload": None,
            "summary": {},
        }


def external_view(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": artifact["status"],
        "path": artifact["path"],
        "error": artifact["error"],
        "summary": artifact["summary"],
    }


def collect_hard_gate_failures(artifacts: dict[str, dict[str, Any]]) -> list[str]:
    failures = []

    for name, artifact in artifacts.items():
        if artifact["status"] == "error":
            failures.append(f"{name}: parse_error")

    watchlist = artifacts["watchlist"]
    screening = artifacts["screening"]
    confirmation = artifacts["midday_confirmation"]
    brief = artifacts["decision_brief"]

    if watchlist["status"] == "loaded":
        payload = watchlist["payload"] or {}
        if not payload.get("generated_at"):
            failures.append("watchlist: missing_generated_at")
        if not payload.get("stocks"):
            failures.append("watchlist: empty_stocks")

    if screening["status"] == "loaded":
        payload = screening["payload"] or {}
        if not payload.get("generated_at"):
            failures.append("screening: missing_generated_at")
        execution_gate = ((payload.get("market_regime") or {}).get("execution_gate") or {}).get("status")
        if payload.get("candidate_count", 0) <= 0 and execution_gate != "off":
            failures.append("screening: empty_candidates")

    if confirmation["status"] == "error":
        failures.append("midday_confirmation: unavailable")
    elif confirmation["status"] == "loaded":
        payload = confirmation["payload"] or {}
        if payload.get("validation_status") not in {None, "ok"}:
            failures.append(f"midday_confirmation: validation_status={payload['validation_status']}")

    if brief["status"] == "loaded":
        payload = brief["payload"] or {}
        summary = payload.get("summary") or {}
        if summary.get("open_new_positions") in (None, ""):
            failures.append("decision_brief: missing_open_new_positions")
        if summary.get("position_cap") in (None, ""):
            failures.append("decision_brief: missing_position_cap")

    return failures


def score_dimensions(artifacts: dict[str, dict[str, Any]]) -> dict[str, int]:
    earned = {name: 0 for name in DIMENSION_MAX}

    watchlist = artifacts["watchlist"]
    screening = artifacts["screening"]
    confirmation = artifacts["midday_confirmation"]
    brief = artifacts["decision_brief"]

    if watchlist["status"] == "loaded":
        payload = watchlist["payload"] or {}
        if payload.get("generated_at"):
            earned["data_governance"] += 3
        if payload.get("stock_count", 0) > 0:
            earned["data_governance"] += 2
        stocks = payload.get("stocks") or []
        if stocks and all(stock.get("price_as_of") for stock in stocks):
            earned["data_governance"] += 2
        if stocks and all(("stop_loss" in (stock.get("trade_levels") or {})) or stock.get("trade_levels", {}).get("stop_loss") is not None for stock in stocks):
            earned["execution_risk_control"] += 2

    if screening["status"] == "loaded":
        payload = screening["payload"] or {}
        candidates = payload.get("candidates") or []
        if payload.get("market_regime"):
            earned["analysis_rule_quality"] += 4
        if candidates:
            earned["analysis_rule_quality"] += 3
        if candidates and all(item.get("setup_type") for item in candidates[:5]):
            earned["analysis_rule_quality"] += 2
        if candidates and all(item.get("entry_plan") for item in candidates[:5]):
            earned["execution_risk_control"] += 4
        if candidates and all(item.get("main_risk") for item in candidates[:5]):
            earned["execution_risk_control"] += 3

    if confirmation["status"] == "loaded":
        payload = confirmation["payload"] or {}
        if payload.get("validation_status") == "ok":
            earned["execution_risk_control"] += 3
            earned["stability_productization"] += 2

    if brief["status"] == "loaded":
        payload = brief["payload"] or {}
        summary = payload.get("summary") or {}
        focus = payload.get("focus") or {}
        if summary.get("open_new_positions") not in (None, ""):
            earned["output_usability"] += 3
        if summary.get("position_cap") not in (None, ""):
            earned["output_usability"] += 3
        if focus.get("avoid_points"):
            earned["output_usability"] += 3
        if payload.get("paths"):
            earned["stability_productization"] += 2

    return earned


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    artifacts = {
        "watchlist": try_load_artifact(load_watchlist_snapshot, "watchlist", "watchlist_snapshot", case),
        "screening": try_load_artifact(load_screening_batch, "screening", "screening_batch", case),
        "midday_confirmation": try_load_artifact(load_confirmation, "midday_confirmation", "midday_confirmation", case),
        "decision_brief": try_load_artifact(load_decision_brief, "decision_brief", "decision_brief", case),
    }
    hard_gate_failures = collect_hard_gate_failures(artifacts)
    dimension_scores = score_dimensions(artifacts)
    return {
        "id": case["id"],
        "artifacts": {name: external_view(artifact) for name, artifact in artifacts.items()},
        "hard_gate_failures": hard_gate_failures,
        "dimension_scores": dimension_scores,
    }


def evaluate_historical_report(report: dict[str, Any]) -> dict[str, Any]:
    path_value = report.get("path")
    result = {
        "id": report.get("id"),
        "path": path_value,
        "description": report.get("description", ""),
        "status": "missing",
        "score": 0,
        "evidence": [],
        "review_id": None,
        "summary": {},
    }
    if not path_value:
        result["status"] = "missing_path"
        return result

    try:
        review = load_research_review(path=path_value)
    except Exception:
        path = Path(path_value)
        if not path.exists():
            result["status"] = "missing"
            return result
        result["status"] = "error"
        return result

    summary = review.get("summary") or {}
    ai_overall = summary.get("ai_overall") or {}
    weak_regime_ai = summary.get("weak_regime_ai") or {}
    evidence = []
    score = 0

    roundtrip_cost_pct = review.get("roundtrip_cost_pct")
    ai_overall_next_day = (ai_overall.get("next_day") or {}).get("net_pct")
    ai_overall_day3 = (ai_overall.get("day3") or {}).get("net_pct")
    weak_regime_ai_next_day = (weak_regime_ai.get("next_day") or {}).get("net_pct")
    weak_regime_ai_day5 = (weak_regime_ai.get("day5") or {}).get("net_pct")

    if roundtrip_cost_pct is not None and ai_overall_next_day is not None:
        score += 2
        evidence.append("friction_adjusted")
    if (ai_overall.get("next_day") or {}).get("win_net_pct") is not None and ai_overall_day3 is not None:
        score += 2
        evidence.append("multi_horizon_metrics")
    if (review.get("sections") or {}).get("ai_gate_rows"):
        score += 2
        evidence.append("gate_segmentation")
    if (review.get("sections") or {}).get("ai_regime_rows"):
        score += 1
        evidence.append("environment_segmentation")
    if weak_regime_ai_day5 is not None:
        score += 1
        evidence.append("weak_environment_samples")
    if (review.get("sections") or {}).get("ai_tier_rows"):
        score += 1
        evidence.append("tier_segmentation")

    result.update(
        {
            "status": "loaded",
            "score": min(9, score),
            "evidence": evidence,
            "review_id": review.get("review_id"),
            "summary": {
                "roundtrip_cost_pct": roundtrip_cost_pct,
                "ai_overall_next_day_net_pct": ai_overall_next_day,
                "ai_overall_day3_net_pct": ai_overall_day3,
                "weak_regime_ai_next_day_net_pct": weak_regime_ai_next_day,
                "weak_regime_ai_day5_net_pct": weak_regime_ai_day5,
            },
        }
    )
    return result


def evaluate_historical_reports(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [evaluate_historical_report(report) for report in manifest.get("historical_reports", [])]


def review_metric(review: dict[str, Any], group: str, period: str, field: str = "net_pct") -> float | None:
    summary = review.get("summary") or {}
    group_value = summary.get(group) or {}
    period_value = group_value.get(period) or {}
    return period_value.get(field)


def delta_or_none(latest: float | None, baseline: float | None) -> float | None:
    if latest is None or baseline is None:
        return None
    return round(latest - baseline, 4)


def evaluate_historical_comparison(pair: dict[str, Any]) -> dict[str, Any]:
    baseline_path = pair.get("baseline_path")
    latest_path = pair.get("latest_path")
    result = {
        "id": pair.get("id"),
        "description": pair.get("description", ""),
        "baseline_path": baseline_path,
        "latest_path": latest_path,
        "status": "missing",
        "score": 0,
        "evidence": [],
        "baseline_review_id": None,
        "latest_review_id": None,
        "summary": {},
    }

    if not baseline_path or not latest_path:
        result["status"] = "missing_path"
        return result

    try:
        baseline_review = load_research_review(path=baseline_path)
        latest_review = load_research_review(path=latest_path)
    except Exception:
        if not Path(baseline_path).exists() or not Path(latest_path).exists():
            result["status"] = "missing"
            return result
        result["status"] = "error"
        return result

    roundtrip_cost_delta = delta_or_none(
        latest_review.get("roundtrip_cost_pct"),
        baseline_review.get("roundtrip_cost_pct"),
    )
    ai_overall_next_day_delta = delta_or_none(
        review_metric(latest_review, "ai_overall", "next_day"),
        review_metric(baseline_review, "ai_overall", "next_day"),
    )
    ai_overall_day3_delta = delta_or_none(
        review_metric(latest_review, "ai_overall", "day3"),
        review_metric(baseline_review, "ai_overall", "day3"),
    )
    ai_overall_day5_delta = delta_or_none(
        review_metric(latest_review, "ai_overall", "day5"),
        review_metric(baseline_review, "ai_overall", "day5"),
    )
    weak_regime_ai_next_day_delta = delta_or_none(
        review_metric(latest_review, "weak_regime_ai", "next_day"),
        review_metric(baseline_review, "weak_regime_ai", "next_day"),
    )
    weak_regime_ai_day5_delta = delta_or_none(
        review_metric(latest_review, "weak_regime_ai", "day5"),
        review_metric(baseline_review, "weak_regime_ai", "day5"),
    )

    evidence = []
    score = 0
    if ai_overall_next_day_delta is not None and ai_overall_day3_delta is not None and ai_overall_day5_delta is not None:
        score += 1
        evidence.append("ai_overall_multi_horizon_delta")
    if weak_regime_ai_next_day_delta is not None and weak_regime_ai_day5_delta is not None:
        score += 1
        evidence.append("weak_regime_delta")
    if baseline_review.get("start_date") and latest_review.get("start_date"):
        if (
            baseline_review.get("start_date") == latest_review.get("start_date")
            and baseline_review.get("end_date") == latest_review.get("end_date")
        ):
            score += 1
            evidence.append("same_window_comparison")
    if roundtrip_cost_delta == 0:
        score += 1
        evidence.append("stable_cost_assumption")

    result.update(
        {
            "status": "loaded",
            "score": min(4, score),
            "evidence": evidence,
            "baseline_review_id": baseline_review.get("review_id"),
            "latest_review_id": latest_review.get("review_id"),
            "summary": {
                "baseline_start_date": baseline_review.get("start_date"),
                "baseline_end_date": baseline_review.get("end_date"),
                "latest_start_date": latest_review.get("start_date"),
                "latest_end_date": latest_review.get("end_date"),
                "roundtrip_cost_pct_delta": roundtrip_cost_delta,
                "ai_overall_next_day_net_delta": ai_overall_next_day_delta,
                "ai_overall_day3_net_delta": ai_overall_day3_delta,
                "ai_overall_day5_net_delta": ai_overall_day5_delta,
                "weak_regime_ai_next_day_net_delta": weak_regime_ai_next_day_delta,
                "weak_regime_ai_day5_net_delta": weak_regime_ai_day5_delta,
            },
        }
    )
    return result


def evaluate_historical_comparisons(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [evaluate_historical_comparison(pair) for pair in manifest.get("historical_comparisons", [])]


def finalize_dimension_scores(case_results: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    totals = {name: 0 for name in DIMENSION_MAX}
    for case_result in case_results:
        for name, value in case_result["dimension_scores"].items():
            totals[name] += value

    return {
        name: {"earned": min(max_value, totals[name]), "max": max_value}
        for name, max_value in DIMENSION_MAX.items()
    }


def resolve_tier(
    total_score: int,
    hard_gate_failures: list[str],
    dimension_scores: dict[str, dict[str, int]],
) -> str:
    professional_thresholds = dimension_thresholds_for_tier("professional_usable")
    product_ready_thresholds = dimension_thresholds_for_tier("product_ready")

    if hard_gate_failures:
        return "below_basic"
    if total_score >= 90 and all(
        dimension_scores[name]["earned"] >= threshold for name, threshold in product_ready_thresholds.items()
    ):
        return "product_ready"
    if (
        total_score >= 82
        and all(dimension_scores[name]["earned"] >= threshold for name, threshold in professional_thresholds.items())
    ):
        return "professional_usable"
    if total_score >= 70:
        return "basic_usable"
    return "below_basic"


def build_gate_evaluation(
    *,
    current_tier: str,
    total_score: int,
    hard_gate_failures: list[str],
    dimension_scores: dict[str, dict[str, int]],
    required_tier: str | None,
    fail_on_hard_gates: bool,
) -> dict[str, Any]:
    if not required_tier and not fail_on_hard_gates:
        return {
            "status": "report_only",
            "required_tier": None,
            "current_tier": current_tier,
            "fail_on_hard_gates": False,
            "hard_gates_clear": not hard_gate_failures,
            "passed": None,
            "reasons": [],
        }

    reasons: list[str] = []
    passed = True

    if required_tier and tier_rank(current_tier) < tier_rank(required_tier):
        passed = False
        reasons.append(f"Current tier {current_tier} is below required tier {required_tier}.")
        reasons.extend(
            requirement["message"]
            for requirement in build_tier_requirements(required_tier, total_score, hard_gate_failures, dimension_scores)
        )

    if fail_on_hard_gates and hard_gate_failures:
        passed = False
        reasons.append(f"hard gate failures present: {len(hard_gate_failures)}")

    return {
        "status": "passed" if passed else "failed",
        "required_tier": required_tier,
        "current_tier": current_tier,
        "fail_on_hard_gates": fail_on_hard_gates,
        "hard_gates_clear": not hard_gate_failures,
        "passed": passed,
        "reasons": reasons,
    }


def build_scorecard(
    manifest: dict[str, Any],
    *,
    run_context: dict[str, Any] | None = None,
    required_tier: str | None = None,
    fail_on_hard_gates: bool = False,
) -> dict[str, Any]:
    suite_results = []
    flattened_case_results = []
    expected_abnormal_failures = []
    historical_results = evaluate_historical_reports(manifest)
    historical_comparisons = evaluate_historical_comparisons(manifest)

    for suite in manifest.get("suites", []):
        case_results = [evaluate_case(case) for case in suite.get("cases", [])]
        suite_results.append(
            {
                "name": suite["name"],
                "description": suite.get("description", ""),
                "expected_failures": bool(suite.get("expected_failures", False)),
                "cases": case_results,
            }
        )
        flattened_case_results.extend(case_results)

    dimension_scores = finalize_dimension_scores(flattened_case_results)
    historical_score = min(
        DIMENSION_MAX["historical_validation"],
        sum(result.get("score", 0) for result in historical_results if result.get("status") == "loaded")
        + sum(result.get("score", 0) for result in historical_comparisons if result.get("status") == "loaded"),
    )
    dimension_scores["historical_validation"]["earned"] = historical_score
    hard_gate_failures = []
    for suite_result in suite_results:
        for case_result in suite_result["cases"]:
            target = expected_abnormal_failures if suite_result.get("expected_failures") else hard_gate_failures
            target.extend(
                f"{suite_result['name']}::{case_result['id']}::{failure}"
                for failure in case_result["hard_gate_failures"]
            )

    total_score = sum(score["earned"] for score in dimension_scores.values())
    tier = resolve_tier(total_score, hard_gate_failures, dimension_scores)
    next_tier = next_tier_name(tier)
    summary = {
        "total_score": total_score,
        "max_score": 100,
        "tier": tier,
        "hard_gate_failures": hard_gate_failures,
        "expected_abnormal_failures": expected_abnormal_failures,
        "dimension_scores": dimension_scores,
        "next_tier": next_tier,
        "next_tier_requirements": build_tier_requirements(next_tier, total_score, hard_gate_failures, dimension_scores),
    }

    return {
        "version": 1,
        "program": "prism_stock_analysis_evaluation",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "baseline_label": manifest.get("baseline_label"),
        "run_context": run_context or {},
        "summary": summary,
        "gate_evaluation": build_gate_evaluation(
            current_tier=tier,
            total_score=total_score,
            hard_gate_failures=hard_gate_failures,
            dimension_scores=dimension_scores,
            required_tier=required_tier,
            fail_on_hard_gates=fail_on_hard_gates,
        ),
        "historical_results": historical_results,
        "historical_comparisons": historical_comparisons,
        "suite_results": suite_results,
    }


def write_markdown(scorecard: dict[str, Any], path: str) -> None:
    gate_evaluation = scorecard.get("gate_evaluation") or {}
    run_context = scorecard.get("run_context") or {}
    lines = [
        "# Prism Stock Analysis Evaluation Report",
        "",
        f"- Generated At: {scorecard['generated_at']}",
        f"- Baseline Label: {scorecard.get('baseline_label') or '-'}",
        f"- Total Score: {scorecard['summary']['total_score']} / {scorecard['summary']['max_score']}",
        f"- Tier: {scorecard['summary']['tier']}",
        "",
        "## Acceptance Verdict",
        "",
        f"- status: {gate_evaluation.get('status') or 'report_only'}",
        f"- required_tier: {gate_evaluation.get('required_tier') or 'none'}",
        f"- fail_on_hard_gates: {str(bool(gate_evaluation.get('fail_on_hard_gates'))).lower()}",
        f"- hard_gates_clear: {str(bool(gate_evaluation.get('hard_gates_clear', True))).lower()}",
        f"- passed: {'n/a' if gate_evaluation.get('passed') is None else str(bool(gate_evaluation.get('passed'))).lower()}",
        "",
        "## Run Context",
        "",
        f"- manifest_path: {run_context.get('manifest_path') or '-'}",
        f"- required_tier: {run_context.get('required_tier') or 'none'}",
        f"- fail_on_hard_gates: {str(bool(run_context.get('fail_on_hard_gates'))).lower()}",
        f"- command: {run_context.get('command') or '-'}",
        "",
        "## Dimension Scores",
        "",
    ]
    for reason in gate_evaluation.get("reasons") or []:
        lines.append(f"- reason: {reason}")
    if gate_evaluation.get("reasons"):
        lines.append("")
    for name, score in scorecard["summary"]["dimension_scores"].items():
        lines.append(f"- {name}: {score['earned']} / {score['max']}")
    lines.extend(["", "## Hard Gate Failures", ""])
    failures = scorecard["summary"]["hard_gate_failures"] or ["none"]
    for failure in failures:
        lines.append(f"- {failure}")
    lines.extend(["", "## Expected Abnormal Failures", ""])
    expected_failures = scorecard["summary"]["expected_abnormal_failures"] or ["none"]
    for failure in expected_failures:
        lines.append(f"- {failure}")
    lines.extend(["", "## Historical Validation", ""])
    historical_results = scorecard.get("historical_results") or []
    if not historical_results:
        lines.append("- none")
    for result in historical_results:
        evidence = ", ".join(result.get("evidence") or ["none"])
        lines.append(
            f"- {result.get('id')}: {result.get('status')} | score {result.get('score', 0)} | evidence: {evidence}"
        )
    lines.extend(["", "## Historical Comparisons", ""])
    historical_comparisons = scorecard.get("historical_comparisons") or []
    if not historical_comparisons:
        lines.append("- none")
    for result in historical_comparisons:
        summary = result.get("summary") or {}
        delta_bits = []
        for key in (
            "ai_overall_next_day_net_delta",
            "ai_overall_day3_net_delta",
            "ai_overall_day5_net_delta",
            "weak_regime_ai_next_day_net_delta",
            "weak_regime_ai_day5_net_delta",
        ):
            value = summary.get(key)
            if value is not None:
                delta_bits.append(f"{key}={value:+.4f}")
        delta_summary = ", ".join(delta_bits) if delta_bits else "no structured deltas"
        lines.append(
            f"- {result.get('id')}: {result.get('status')} | score {result.get('score', 0)} | {delta_summary}"
        )
    lines.extend(["", "## Upgrade Gaps", ""])
    next_tier = scorecard["summary"].get("next_tier")
    if not next_tier:
        lines.append("- none")
    else:
        lines.append(f"- Next Tier: {next_tier}")
        requirements = scorecard["summary"].get("next_tier_requirements") or []
        if not requirements:
            lines.append("- none")
        for requirement in requirements:
            lines.append(f"- {requirement['message']}")
    lines.extend(["", "## Suites", ""])
    for suite in scorecard["suite_results"]:
        lines.append(f"### {suite['name']}")
        lines.append("")
        lines.append(f"- expected_failures: {str(bool(suite.get('expected_failures'))).lower()}")
        for case in suite["cases"]:
            lines.append(f"- {case['id']}: {len(case['hard_gate_failures'])} hard-gate failures")
        lines.append("")
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    manifest = load_manifest(args.manifest)
    scorecard = build_scorecard(
        manifest,
        run_context={
            "manifest_path": args.manifest,
            "required_tier": args.min_tier,
            "fail_on_hard_gates": bool(args.fail_on_hard_gates),
            "command": " ".join(sys.argv),
        },
        required_tier=args.min_tier,
        fail_on_hard_gates=bool(args.fail_on_hard_gates),
    )

    output_json = Path(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(scorecard, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(scorecard, args.output_md)
    gate_evaluation = scorecard.get("gate_evaluation") or {}
    if gate_evaluation.get("status") == "failed":
        reasons = gate_evaluation.get("reasons") or ["acceptance gate failed"]
        print("; ".join(reasons), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
