from pathlib import Path
import os
import subprocess


def test_start_script_targets_next_web_shell_and_local_backend() -> None:
    script_path = Path("start_prism.sh")

    assert script_path.exists()

    content = script_path.read_text(encoding="utf-8")

    assert "#!/usr/bin/env bash" in content
    assert ".venv/bin/uvicorn" in content
    assert "control_panel.app:app" in content
    assert "apps/web" in content
    assert "node_modules/.bin/next" in content
    assert "scripts/dev.mjs" in content
    assert "PRISM_BACKEND_ORIGIN" in content
    assert "prism_scheduler.py" in content
    assert "PRISM_ENABLE_SCHEDULER" in content
    assert "127.0.0.1" in content
    assert "8001" in content
    assert "8000" in content
    assert "Starting Prism Next web app" in content
    assert "Starting Prism scheduler" in content


def test_next_rewrites_target_internal_backend_by_default() -> None:
    config_path = Path("apps/web/next.config.ts")

    assert config_path.exists()

    content = config_path.read_text(encoding="utf-8")

    assert 'process.env.PRISM_BACKEND_ORIGIN ?? "http://127.0.0.1:8001"' in content
    assert '"http://localhost:8000' not in content


def test_web_dev_script_uses_single_server_guard() -> None:
    package_path = Path("apps/web/package.json")
    wrapper_path = Path("apps/web/scripts/dev.mjs")

    assert package_path.exists()
    assert wrapper_path.exists()

    package_content = package_path.read_text(encoding="utf-8")
    wrapper_content = wrapper_path.read_text(encoding="utf-8")

    assert '"dev": "node ./scripts/dev.mjs"' in package_content
    assert "Another Next dev server" in wrapper_content
    assert "Stop the existing dev server first" in wrapper_content


def test_command_brief_script_writes_artifact_store_with_legacy_copy() -> None:
    script_path = Path("apps/scripts/run_command_brief.sh")

    assert script_path.exists()

    content = script_path.read_text(encoding="utf-8")

    assert "data/artifacts/command_brief" in content
    assert "LEGACY_BRIEF_OUTPUT_PATH" in content
    assert "PRISM_WRITE_LEGACY_ARTIFACTS" in content
    assert "prism_storage.cli" in content
    assert "register-file" in content
    assert "--allow-stale-watchlist" in content
    assert "ALLOW_STALE_WATCHLIST" in content
    assert Path("apps/scripts/generate_command_brief.py").exists()


def test_screener_scripts_mirror_artifacts_to_artifact_store() -> None:
    script_paths = [
        Path("packages/screener/run_full_workflow.sh"),
        Path("packages/screener/run_midday_refresh.sh"),
        Path("packages/screener/run_midday_confirmation.sh"),
    ]

    for script_path in script_paths:
        content = script_path.read_text(encoding="utf-8")
        assert "prism_artifact_helpers.sh" in content
        assert "prism_mirror_artifact" in content
        assert "data/artifacts" not in content
        subprocess.run(["bash", "-n", str(script_path)], check=True)


def test_screener_quality_dashboard_defaults_to_runtime() -> None:
    for script_path in (
        Path("packages/screener/run_full_workflow.sh"),
        Path("packages/screener/run_midday_confirmation.sh"),
    ):
        content = script_path.read_text(encoding="utf-8")
        assert "data/runtime/reports/command_brief/feishu-quality-dashboard.md" in content
        assert "data/history/reports/command_brief/feishu-quality-dashboard.md" not in content


def test_runtime_noise_files_are_not_tracked() -> None:
    ignored_runtime_paths = [
        "apps/data/control_panel_state/ask_recent_queries.json",
        "apps/data/control_panel_state/refresh_state.json",
        "apps/data/control_panel_state/today_action_decisions.json",
        "data/history/reports/command_brief/feishu-quality-dashboard.md",
        "stock-analyzer/data/fund_flow_cache/sh600690.json",
        "stock-analyzer/data/fundamentals_cache/sh600690.json",
    ]
    check_ignore = subprocess.run(
        ["git", "check-ignore", "--no-index", *ignored_runtime_paths],
        check=True,
        text=True,
        capture_output=True,
    )

    assert check_ignore.stdout.splitlines() == ignored_runtime_paths

    result = subprocess.run(
        [
            "git",
            "ls-files",
            "apps/data/control_panel_state",
            "data/history/reports/command_brief/feishu-quality-dashboard.md",
            "stock-analyzer/data/fund_flow_cache",
            "stock-analyzer/data/fundamentals_cache",
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    assert result.stdout == ""


def test_historical_stock_analyzer_outputs_remain_tracked() -> None:
    retained_history_paths = [
        "stock-analyzer/data/daily_snapshots/2026-04-21.json",
        "stock-analyzer/data/quality_gate_watchlist_2026-04-21.json",
    ]
    result = subprocess.run(
        ["git", "ls-files", *retained_history_paths],
        check=True,
        text=True,
        capture_output=True,
    )

    assert result.stdout.splitlines() == retained_history_paths


def test_runtime_task_commands_use_repo_local_paths() -> None:
    dashboard_data = Path("apps/control-panel/dashboard_data.py").read_text(encoding="utf-8")
    app_py = Path("apps/control-panel/app.py").read_text(encoding="utf-8")
    refresh_script = Path("apps/scripts/run_watchlist_refresh.sh").read_text(encoding="utf-8")

    for content in (dashboard_data, app_py, refresh_script):
        assert "skills/" not in content


def test_command_brief_script_smoke(tmp_path: Path) -> None:
    run_stamp = "pytest_smoke"
    snapshot_dir = Path("stock-analyzer/data/daily_snapshots")
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = snapshot_dir / "2026-04-21.json"
    had_snapshot = snapshot_path.exists()
    previous_snapshot = snapshot_path.read_text(encoding="utf-8") if had_snapshot else ""
    snapshot_path.write_text(
        '{"date":"2026-04-21","generated_at":"2026-04-21 09:25:00","stocks":{}}\n',
        encoding="utf-8",
    )
    env = {
        "RUN_STAMP": run_stamp,
        "TRADE_DATE": "2026-04-21",
        "BRIEF_OUTPUT_PATH": str(tmp_path / "brief.txt"),
        "REPORT_OUTPUT_PATH": str(tmp_path / "brief.md"),
        "JSON_OUTPUT_PATH": str(tmp_path / "brief.json"),
        "PRISM_WRITE_LEGACY_ARTIFACTS": "0",
        "SEND_TO_FEISHU": "0",
    }
    try:
        completed = subprocess.run(
            ["bash", "apps/scripts/run_command_brief.sh"],
            check=False,
            text=True,
            capture_output=True,
            env={**os.environ, **env},
        )
    finally:
        if had_snapshot:
            snapshot_path.write_text(previous_snapshot, encoding="utf-8")
        else:
            snapshot_path.unlink(missing_ok=True)

    assert completed.returncode == 0, completed.stderr
    assert (tmp_path / "brief.txt").exists()
    assert (tmp_path / "brief.md").exists()
    assert (tmp_path / "brief.json").exists()
