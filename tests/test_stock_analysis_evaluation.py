import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path("apps/scripts").resolve()))

from evaluate_stock_analysis import resolve_tier


def run_evaluator(output_dir: Path) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    output_json = output_dir / "scorecard.json"
    output_md = output_dir / "scorecard.md"

    completed = subprocess.run(
        [
            "python3",
            "apps/scripts/evaluate_stock_analysis.py",
            "--manifest",
            "data/evaluation/stock_analysis/manifest.json",
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed, output_json, output_md


def test_stock_analysis_manifest_has_required_suites() -> None:
    manifest_path = Path("data/evaluation/stock_analysis/manifest.json")

    assert manifest_path.exists()

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    suite_names = {suite["name"] for suite in payload["suites"]}

    assert payload["version"] == 1
    assert payload["program"] == "prism_stock_analysis_evaluation"
    assert {
        "latest_trading_day",
        "historical_normal",
        "weak_environment",
        "abnormal_inputs",
    }.issubset(suite_names)


def test_manifest_case_paths_exist_except_intentional_missing_cases() -> None:
    manifest = json.loads(Path("data/evaluation/stock_analysis/manifest.json").read_text(encoding="utf-8"))

    for suite in manifest["suites"]:
        for case in suite["cases"]:
            for key in ("watchlist_snapshot", "screening_batch", "midday_confirmation", "decision_brief"):
                path_value = case.get(key)
                if not path_value:
                    continue
                path = Path(path_value)
                if case["id"] == "missing_midday_case" and key == "midday_confirmation":
                    assert not path.exists()
                    continue
                assert path.exists(), f"{case['id']} missing {key}: {path_value}"


def test_manifest_references_existing_historical_replay_reports() -> None:
    manifest = json.loads(Path("data/evaluation/stock_analysis/manifest.json").read_text(encoding="utf-8"))

    reports = manifest["historical_reports"]

    assert reports
    for report in reports:
        assert Path(report["path"]).exists(), report["path"]


def test_manifest_references_existing_historical_comparison_pair() -> None:
    manifest = json.loads(Path("data/evaluation/stock_analysis/manifest.json").read_text(encoding="utf-8"))

    comparisons = manifest["historical_comparisons"]

    assert comparisons
    pair = comparisons[0]
    assert Path(pair["baseline_path"]).exists(), pair["baseline_path"]
    assert Path(pair["latest_path"]).exists(), pair["latest_path"]


def test_evaluator_writes_json_scorecard(tmp_path: Path) -> None:
    completed, output_json, output_md = run_evaluator(tmp_path)

    assert completed.returncode == 0, completed.stderr
    assert output_json.exists()
    assert output_md.exists()

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["program"] == "prism_stock_analysis_evaluation"
    assert payload["version"] == 1
    assert "summary" in payload
    assert "suite_results" in payload
    assert "dimension_scores" in payload["summary"]


def test_evaluator_loads_latest_operational_case_via_canonical_artifacts(tmp_path: Path) -> None:
    completed, output_json, _ = run_evaluator(tmp_path)

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    latest_suite = next(item for item in payload["suite_results"] if item["name"] == "latest_trading_day")
    latest_case = latest_suite["cases"][0]

    assert latest_case["artifacts"]["watchlist"]["status"] == "loaded"
    assert latest_case["artifacts"]["screening"]["status"] == "loaded"
    assert latest_case["artifacts"]["decision_brief"]["status"] == "loaded"


def test_evaluator_reports_missing_midday_artifact_as_hard_gate_failure(tmp_path: Path) -> None:
    completed, output_json, _ = run_evaluator(tmp_path)

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    abnormal_suite = next(item for item in payload["suite_results"] if item["name"] == "abnormal_inputs")
    abnormal_case = next(item for item in abnormal_suite["cases"] if item["id"] == "missing_midday_case")

    assert any("midday_confirmation" in item for item in abnormal_case["hard_gate_failures"])
    assert abnormal_suite["expected_failures"] is True
    assert all("abnormal_inputs::" not in item for item in payload["summary"]["hard_gate_failures"])


def test_evaluator_assigns_nonzero_scores_for_valid_latest_case(tmp_path: Path) -> None:
    completed, output_json, _ = run_evaluator(tmp_path)

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    scores = payload["summary"]["dimension_scores"]

    assert scores["data_governance"]["earned"] > 0
    assert scores["execution_risk_control"]["earned"] > 0
    assert scores["output_usability"]["earned"] > 0


def test_evaluator_scores_historical_validation_from_replay_report(tmp_path: Path) -> None:
    completed, output_json, _ = run_evaluator(tmp_path)

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    scores = payload["summary"]["dimension_scores"]

    assert scores["historical_validation"]["earned"] > 0
    assert payload["historical_results"]
    assert payload["historical_results"][0]["status"] == "loaded"
    assert "friction_adjusted" in payload["historical_results"][0]["evidence"]


def test_evaluator_exposes_structured_historical_review_metrics(tmp_path: Path) -> None:
    completed, output_json, _ = run_evaluator(tmp_path)

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    result = payload["historical_results"][0]

    assert result["review_id"]
    assert result["summary"]["roundtrip_cost_pct"] is not None
    assert result["summary"]["ai_overall_next_day_net_pct"] is not None
    assert result["summary"]["weak_regime_ai_next_day_net_pct"] is not None


def test_evaluator_exposes_structured_historical_comparison_deltas(tmp_path: Path) -> None:
    completed, output_json, _ = run_evaluator(tmp_path)

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    comparison = payload["historical_comparisons"][0]

    assert comparison["status"] == "loaded"
    assert comparison["baseline_review_id"]
    assert comparison["latest_review_id"]
    assert comparison["summary"]["baseline_start_date"] is not None
    assert comparison["summary"]["latest_start_date"] is not None
    assert comparison["summary"]["ai_overall_next_day_net_delta"] is not None
    assert comparison["summary"]["weak_regime_ai_next_day_net_delta"] is not None
    assert "same_window_comparison" in comparison["evidence"]


def test_evaluator_does_not_treat_zero_candidates_in_gate_off_suite_as_hard_failure(tmp_path: Path) -> None:
    completed, output_json, _ = run_evaluator(tmp_path)

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    weak_suite = next(item for item in payload["suite_results"] if item["name"] == "weak_environment")
    target_case = next(item for item in weak_suite["cases"] if item["id"] == "weak_environment_2026_04_15_morning")

    assert not any("screening: empty_candidates" == item for item in target_case["hard_gate_failures"])


def test_evaluator_writes_human_readable_report_with_tier_and_failures(tmp_path: Path) -> None:
    completed, _, output_md = run_evaluator(tmp_path)

    assert completed.returncode == 0, completed.stderr
    report = output_md.read_text(encoding="utf-8")

    assert "Prism Stock Analysis Evaluation Report" in report
    assert "Tier:" in report
    assert "Dimension Scores" in report
    assert "Hard Gate Failures" in report
    assert "Expected Abnormal Failures" in report
    assert "Historical Validation" in report
    assert "Historical Comparisons" in report


def test_tier_thresholds_use_ceil_for_dimension_requirements() -> None:
    dimension_scores = {
        "data_governance": {"earned": 17, "max": 20},
        "analysis_rule_quality": {"earned": 17, "max": 20},
        "execution_risk_control": {"earned": 17, "max": 20},
        "output_usability": {"earned": 13, "max": 15},
        "historical_validation": {"earned": 12, "max": 15},
        "stability_productization": {"earned": 9, "max": 10},
    }

    assert resolve_tier(90, [], dimension_scores) == "professional_usable"


def test_initial_baseline_run_produces_suite_results_and_summary(tmp_path: Path) -> None:
    completed, output_json, output_md = run_evaluator(tmp_path)

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output_json.read_text(encoding="utf-8"))

    assert len(payload["suite_results"]) == 4
    assert payload["summary"]["max_score"] == 100
    assert "dimension_scores" in payload["summary"]
    assert output_md.exists()
