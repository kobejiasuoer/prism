from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

from prism_storage import AppStateRepository, ArtifactRepository, TaskRunRepository
from prism_storage import WatchlistConfigRepository
from prism_storage.analytics import export_artifacts_jsonl, write_jsonl_dataset
from prism_storage.artifacts import index_artifacts
from prism_storage.cli import doctor, sync_runtime
from prism_storage.history import export_history, sanitize_for_history
from prism_storage.json_store import atomic_write_json
from prism_storage.mirror import mirror_analyzer_artifacts, mirror_file_to_artifact_store
from prism_storage.paths import command_brief_paths, control_panel_run_paths
from prism_storage.sqlite_store import connection


def test_app_state_repository_exports_legacy_json_and_respects_newer_legacy_file(tmp_path):
    db_path = tmp_path / "runtime" / "prism.db"
    legacy_path = tmp_path / "legacy" / "refresh_state.json"
    repo = AppStateRepository(db_path)

    repo.set("refresh_state", {"pages": {"today": {"run_id": "one"}}}, legacy_path=legacy_path)
    assert repo.get("refresh_state", legacy_path=legacy_path) == {"pages": {"today": {"run_id": "one"}}}

    time.sleep(0.01)
    atomic_write_json(legacy_path, {"pages": {"today": {"run_id": "restored"}}})

    assert repo.get("refresh_state", legacy_path=legacy_path) == {"pages": {"today": {"run_id": "restored"}}}


def test_task_run_repository_backfills_legacy_metadata(tmp_path):
    db_path = tmp_path / "runtime" / "prism.db"
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    legacy_path = runs_dir / "command_brief_1.json"
    payload = {
        "task_id": "command_brief_1",
        "task_name": "command_brief",
        "title": "投资总控简报",
        "status": "success",
        "started_at": "2026-04-21 09:00:00",
        "finished_at": "2026-04-21 09:01:00",
        "exit_code": 0,
        "pid": 123,
        "cwd": "/tmp/prism",
        "command": ["bash", "run.sh"],
        "log_path": "/tmp/prism.log",
        "meta_path": str(legacy_path),
    }
    atomic_write_json(legacy_path, payload)

    repo = TaskRunRepository(db_path)

    assert repo.get("command_brief_1", legacy_dir=runs_dir) == payload
    assert repo.list(legacy_dir=runs_dir, limit=1)[0]["task_id"] == "command_brief_1"


def test_task_run_repository_reads_multiple_legacy_dirs(tmp_path):
    db_path = tmp_path / "runtime" / "prism.db"
    new_runs_dir = tmp_path / "data" / "runtime" / "runs" / "control_panel"
    legacy_runs_dir = tmp_path / "apps" / "data" / "control_panel_runs"
    new_runs_dir.mkdir(parents=True)
    legacy_runs_dir.mkdir(parents=True)
    atomic_write_json(
        new_runs_dir / "new_run.json",
        {
            "task_id": "new_run",
            "task_name": "command_brief",
            "title": "new",
            "status": "success",
            "started_at": "2026-04-25 10:00:00",
            "command": [],
        },
    )
    atomic_write_json(
        legacy_runs_dir / "legacy_run.json",
        {
            "task_id": "legacy_run",
            "task_name": "command_brief",
            "title": "legacy",
            "status": "success",
            "started_at": "2026-04-24 10:00:00",
            "command": [],
        },
    )

    repo = TaskRunRepository(db_path)

    assert repo.get("legacy_run", legacy_dirs=(new_runs_dir, legacy_runs_dir))["title"] == "legacy"
    assert [item["task_id"] for item in repo.list(legacy_dirs=(new_runs_dir, legacy_runs_dir), limit=2)] == [
        "new_run",
        "legacy_run",
    ]


def test_artifact_repository_registers_workspace_relative_file(tmp_path):
    db_path = tmp_path / "runtime" / "prism.db"
    repo_root = tmp_path / "repo"
    artifact_path = repo_root / "data" / "artifacts" / "screener" / "sample.json"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text('{"ok": true}', encoding="utf-8")

    repo = ArtifactRepository(db_path, repo_root=repo_root)
    artifact = repo.register_file(
        artifact_path,
        artifact_type="screener_ai_screening",
        source="test",
        trade_date="2026-04-21",
        metadata={"batch": "smoke"},
    )

    assert artifact["path"] == "data/artifacts/screener/sample.json"
    assert artifact["sha256"] == hashlib.sha256(b'{"ok": true}').hexdigest()

    indexed = repo.list(artifact_type="screener_ai_screening")
    assert indexed[0]["metadata"] == {"batch": "smoke"}


def test_index_artifacts_scans_known_outputs_and_skips_caches(tmp_path):
    db_path = tmp_path / "runtime" / "prism.db"
    repo_root = tmp_path / "repo"
    ai_path = repo_root / "stock-screener" / "data" / "ai_history" / "ai_screening_2026-04-21_09-30-00.json"
    cache_path = repo_root / "stock-analyzer" / "data" / "fund_flow_cache" / "sh600690.json"
    report_path = repo_root / "data" / "history" / "reports" / "screener" / "stock_recommendation_2026-04-21.md"
    ai_path.parent.mkdir(parents=True)
    cache_path.parent.mkdir(parents=True)
    report_path.parent.mkdir(parents=True)
    atomic_write_json(ai_path, {"timestamp": "2026-04-21 09:30:00", "trade_date": "2026-04-21"})
    atomic_write_json(cache_path, {"cache": True})
    report_path.write_text("# report", encoding="utf-8")

    summary = index_artifacts(db_path=db_path, repo_root=repo_root)

    assert summary["ok"]
    assert summary["indexed"] == 2
    assert summary["counts"]["ai_screening_snapshot"] == 1
    assert summary["counts"]["report"] == 1

    artifacts = ArtifactRepository(db_path, repo_root=repo_root).list(limit=10)
    assert {item["artifact_type"] for item in artifacts} == {"ai_screening_snapshot", "report"}
    assert all("fund_flow_cache" not in item["path"] for item in artifacts)

    health = doctor(db_path)
    assert health["artifact_count"] == 2


def test_command_brief_paths_use_artifact_store(tmp_path):
    paths = command_brief_paths("2026-04-25_20-30-00", root=tmp_path)

    assert paths["brief"] == tmp_path / "data" / "artifacts" / "command_brief" / "prism_command_brief_2026-04-25_20-30-00.txt"
    assert paths["report"].suffix == ".md"
    assert paths["json"].suffix == ".json"


def test_control_panel_run_paths_use_runtime_store(tmp_path):
    meta_path, log_path = control_panel_run_paths("smoke_1", root=tmp_path)

    assert meta_path == tmp_path / "data" / "runtime" / "runs" / "control_panel" / "smoke_1.json"
    assert log_path == tmp_path / "data" / "runtime" / "runs" / "control_panel" / "logs" / "smoke_1.log"


def test_cli_register_file_indexes_artifact(tmp_path):
    db_path = tmp_path / "runtime" / "prism.db"
    repo_root = tmp_path / "repo"
    artifact_path = repo_root / "data" / "artifacts" / "command_brief" / "sample.md"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text("# sample", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "prism_storage.cli",
            "--db",
            str(db_path),
            "--repo-root",
            str(repo_root),
            "register-file",
            str(artifact_path),
            "--artifact-type",
            "command_report",
            "--source",
            "test",
            "--trade-date",
            "2026-04-25",
            "--metadata-json",
            '{"kind":"smoke"}',
            "--json",
        ],
        check=True,
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
    )

    payload = json.loads(result.stdout)
    assert payload["ok"]
    assert payload["artifact"]["path"] == "data/artifacts/command_brief/sample.md"
    assert ArtifactRepository(db_path, repo_root=repo_root).list(artifact_type="command_report")[0]["metadata"] == {
        "kind": "smoke"
    }


def test_watchlist_config_repository_keeps_json_config_as_canonical(tmp_path):
    config_path = tmp_path / "repo" / "stock-analyzer" / "config" / "stocks.json"
    repo = WatchlistConfigRepository(config_path)
    payload = {
        "stocks": [{"code": "600690", "name": "海尔智家", "active": True}],
        "ma_periods": [5, 10, 20],
    }

    repo.set(payload)

    assert repo.get()["stocks"][0]["code"] == "600690"
    assert repo.list_stocks(active=True)[0]["name"] == "海尔智家"
    assert json.loads(config_path.read_text(encoding="utf-8"))["ma_periods"] == [5, 10, 20]


def test_mirror_analyzer_artifacts_copies_to_artifact_store_and_registers(tmp_path):
    db_path = tmp_path / "runtime" / "prism.db"
    repo_root = tmp_path / "repo"
    snapshot_path = repo_root / "stock-analyzer" / "data" / "daily_snapshots" / "2026-04-25.json"
    quality_path = repo_root / "stock-analyzer" / "data" / "quality_gate_watchlist_2026-04-25.json"
    report_path = repo_root / "stock-analyzer" / "reports" / "analysis-report-2026-04-25.md"
    atomic_write_json(snapshot_path, {"date": "2026-04-25", "generated_at": "2026-04-25 15:01:00", "stocks": {}})
    atomic_write_json(quality_path, {"trade_date": "2026-04-25", "validation_status": "ok"})
    report_path.parent.mkdir(parents=True)
    report_path.write_text("# analysis", encoding="utf-8")

    summary = mirror_analyzer_artifacts(db_path=db_path, repo_root=repo_root)

    assert summary["ok"]
    assert summary["mirrored"] == 3
    assert (repo_root / "data" / "artifacts" / "analyzer" / "daily_snapshots" / "2026-04-25.json").exists()
    artifact_types = {
        item["artifact_type"]
        for item in ArtifactRepository(db_path, repo_root=repo_root).list(limit=10)
    }
    assert artifact_types == {"daily_snapshot", "quality_gate", "analyzer_report"}


def test_mirror_file_to_artifact_store_preserves_source_metadata(tmp_path):
    db_path = tmp_path / "runtime" / "prism.db"
    repo_root = tmp_path / "repo"
    source_path = repo_root / "stock-analyzer" / "data" / "daily_snapshots" / "2026-04-25.json"
    atomic_write_json(source_path, {"date": "2026-04-25", "generated_at": "2026-04-25 15:01:00"})

    artifact = mirror_file_to_artifact_store(
        source_path,
        "analyzer/daily_snapshots/2026-04-25.json",
        artifact_type="daily_snapshot",
        source="analyzer",
        db_path=db_path,
        repo_root=repo_root,
        metadata={"producer": "test"},
    )

    assert artifact["path"] == "data/artifacts/analyzer/daily_snapshots/2026-04-25.json"
    assert artifact["metadata"]["producer"] == "test"
    assert artifact["metadata"]["mirrored_from"] == "stock-analyzer/data/daily_snapshots/2026-04-25.json"


def test_analytics_jsonl_dataset_and_artifact_export(tmp_path):
    db_path = tmp_path / "runtime" / "prism.db"
    repo_root = tmp_path / "repo"
    artifact_path = repo_root / "data" / "artifacts" / "command_brief" / "sample.md"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text("# sample", encoding="utf-8")
    ArtifactRepository(db_path, repo_root=repo_root).register_file(
        artifact_path,
        artifact_type="command_report",
        source="test",
    )

    dataset = write_jsonl_dataset(
        [{"code": "600690", "score": 10}],
        "features",
        partition={"trade_date": "2026-04-25"},
        filename="part-000.jsonl",
        root=tmp_path / "analytics",
    )
    export = export_artifacts_jsonl(db_path=db_path, repo_root=repo_root, output_path="data/analytics/artifacts.jsonl")

    assert dataset["record_count"] == 1
    assert Path(dataset["path"]).read_text(encoding="utf-8").strip() == '{"code": "600690", "score": 10}'
    exported_lines = (repo_root / "data" / "analytics" / "artifacts.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(exported_lines[0])["artifact_type"] == "command_report"
    assert export["record_count"] == 1


def test_export_history_copies_artifacts_and_sanitizes_task_runs(tmp_path):
    db_path = tmp_path / "runtime" / "prism.db"
    repo_root = tmp_path / "repo"
    source_path = repo_root / "data" / "artifacts" / "analyzer" / "daily_snapshots" / "2026-04-25.json"
    atomic_write_json(source_path, {"date": "2026-04-25"})
    ArtifactRepository(db_path, repo_root=repo_root).register_file(
        source_path,
        artifact_type="daily_snapshot",
        source="analyzer",
    )
    TaskRunRepository(db_path).upsert(
        {
            "task_id": "watchlist_1",
            "task_name": "watchlist",
            "title": "watchlist",
            "status": "success",
            "started_at": "2026-04-25 09:00:00",
            "cwd": str(repo_root),
            "command": [],
            "log_path": str(repo_root / "data" / "runtime" / "runs" / "watchlist_1.log"),
        }
    )

    summary = export_history(db_path=db_path, repo_root=repo_root)

    assert summary["ok"]
    assert summary["copied"] == 1
    assert (repo_root / "data" / "history" / "daily_snapshots" / "2026-04-25.json").exists()
    exported_run = json.loads(
        (repo_root / "data" / "history" / "control_panel_runs" / "watchlist_1.json").read_text(encoding="utf-8")
    )
    assert exported_run["cwd"] == "."
    assert exported_run["log_path"] == "data/runtime/runs/watchlist_1.log"


def test_sanitize_for_history_rewrites_repo_absolute_paths(tmp_path):
    repo_root = tmp_path / "repo"
    value = {"path": str(repo_root / "data" / "runtime" / "prism.db")}

    assert sanitize_for_history(value, repo_root=repo_root) == {"path": "data/runtime/prism.db"}


def test_sqlite_store_quarantines_corrupt_runtime_database(tmp_path):
    db_path = tmp_path / "runtime" / "prism.db"
    db_path.parent.mkdir(parents=True)
    db_path.write_bytes(b"not a sqlite database")
    Path(f"{db_path}-wal").write_bytes(b"")
    Path(f"{db_path}-shm").write_bytes(b"sidecar")

    with connection(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM storage_migrations").fetchone()[0]

    assert count == 1
    assert db_path.exists()
    assert list(db_path.parent.glob("prism.db.corrupt-*"))
    assert list(db_path.parent.glob("prism.db-shm.corrupt-*"))


def test_sync_runtime_backfills_state_and_task_runs(tmp_path):
    db_path = tmp_path / "runtime" / "prism.db"
    repo_root = tmp_path / "repo"
    state_dir = repo_root / "apps" / "data" / "control_panel_state"
    run_dir = repo_root / "apps" / "data" / "control_panel_runs"
    atomic_write_json(state_dir / "refresh_state.json", {"pages": {"today": {"run_id": "one"}}})
    atomic_write_json(state_dir / "ask_recent_queries.json", [{"query": "600690"}])
    atomic_write_json(
        run_dir / "watchlist_1.json",
        {
            "task_id": "watchlist_1",
            "task_name": "watchlist",
            "title": "watchlist",
            "status": "success",
            "started_at": "2026-04-25 09:00:00",
            "command": [],
        },
    )

    summary = sync_runtime(db_path, repo_root)

    assert summary["ok"]
    assert summary["app_state_count"] == 2
    assert summary["task_run_count"] == 1
    assert AppStateRepository(db_path).get("refresh_state") == {"pages": {"today": {"run_id": "one"}}}
