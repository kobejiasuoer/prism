from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "apps" / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import prism_retention  # noqa: E402


def _make_old_file(dir_path: Path, name: str, days_old: int) -> Path:
    """Create a file and backdate its mtime by days_old days."""
    dir_path.mkdir(parents=True, exist_ok=True)
    f = dir_path / name
    f.write_text("stale", encoding="utf-8")
    old_time = (datetime.now() - timedelta(days=days_old)).timestamp()
    os.utime(f, (old_time, old_time))
    return f


def _make_fresh_file(dir_path: Path, name: str) -> Path:
    dir_path.mkdir(parents=True, exist_ok=True)
    f = dir_path / name
    f.write_text("fresh", encoding="utf-8")
    return f


def test_dry_run_does_not_delete(tmp_path: Path):
    log_dir = tmp_path / "scheduled_runs" / "logs"
    old = _make_old_file(log_dir, "old.json", days_old=60)
    plan = prism_retention.plan_cleanup(tmp_path, dry_run=True)
    assert old.exists(), "dry-run must not delete files"
    # The plan should have flagged the old file under scheduled_runs
    assert any(
        old in entry.files for entry in plan.entries if "scheduled_runs" in str(entry.root)
    ), [(str(e.root), len(e.files)) for e in plan.entries]


def test_real_run_deletes_only_expired(tmp_path: Path):
    log_dir = tmp_path / "scheduled_runs" / "logs"
    old = _make_old_file(log_dir, "old.json", days_old=60)
    fresh = _make_fresh_file(log_dir, "fresh.json")
    deleted = prism_retention.execute_cleanup(tmp_path, dry_run=False)
    assert not old.exists()
    assert fresh.exists()
    assert old in deleted
    assert fresh not in deleted


def test_whitelist_protected_files(tmp_path: Path):
    """prism.db, config/, schemas/ must never be deleted regardless of age."""
    runtime = tmp_path / "runtime"
    runtime.mkdir(parents=True)
    old_db = _make_old_file(runtime, "prism.db", days_old=999)
    config_dir = tmp_path / "config"
    old_cfg = _make_old_file(config_dir, "stock-parameters.json", days_old=999)
    schemas_dir = tmp_path / "schemas"
    old_schema = _make_old_file(schemas_dir, "stock-parameters.json", days_old=999)
    deleted = prism_retention.execute_cleanup(tmp_path, dry_run=False)
    assert old_db.exists(), "prism.db must be protected"
    assert old_cfg.exists(), "config/ must be protected"
    assert old_schema.exists(), "schemas/ must be protected"
    assert old_db not in deleted
    assert old_cfg not in deleted


def test_log_files_respect_retention(tmp_path: Path):
    runtime = tmp_path / "runtime"
    old_log = _make_old_file(runtime, "prism_backend.log", days_old=30)
    fresh_log = _make_old_file(runtime, "fresh.log", days_old=1)
    deleted = prism_retention.execute_cleanup(tmp_path, dry_run=False)
    assert not old_log.exists()
    assert fresh_log.exists()


def test_corrupt_files_respect_separate_retention(tmp_path: Path):
    runtime = tmp_path / "runtime"
    # 45 days old — past the 30-day corrupt retention
    old_corrupt = _make_old_file(runtime, "prism.db.corrupt-old", days_old=45)
    # 10 days old — within 30-day corrupt retention
    new_corrupt = _make_old_file(runtime, "prism.db.corrupt-new", days_old=10)
    deleted = prism_retention.execute_cleanup(tmp_path, dry_run=False)
    assert not old_corrupt.exists()
    assert new_corrupt.exists()


def test_env_overrides_retention_days(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PRISM_RETENTION_LOG_DAYS", "5")
    runtime = tmp_path / "runtime"
    # 10 days old — normally kept (default 14), but with override 5 it's expired
    borderline = _make_old_file(runtime, "border.log", days_old=10)
    prism_retention.execute_cleanup(tmp_path, dry_run=False)
    assert not borderline.exists()


def test_harvest_dirs_matched_by_suffix(tmp_path: Path, monkeypatch):
    """tinyshare_*_harvest dirs (tinyshare_harvest, tinyshare_research_harvest)
    must be matched by the harvest target and deleted when aged.

    Regression guard: an earlier version derived the prefix by stripping '*'
    from 'tinyshare_*_harvest', yielding 'tinyshare__harvest' (double
    underscore) which matched nothing.
    """
    monkeypatch.setenv("PRISM_RETENTION_HARVEST_DAYS", "30")
    prism_data = tmp_path / "prism_data"
    old_harvest = prism_data / "tinyshare_harvest"
    old_research = prism_data / "tinyshare_research_harvest"
    # Backdate dirs by 60 days (past 30d retention)
    for d in (old_harvest, old_research):
        d.mkdir(parents=True)
        (d / "raw.json").write_text("x", encoding="utf-8")
        old_time = (datetime.now() - timedelta(days=60)).timestamp()
        os.utime(d, (old_time, old_time))
    # A non-harvest tinyshare dir must NOT be matched by the harvest target
    other = prism_data / "tinyshare_market_supplement"
    other.mkdir(parents=True)
    (other / "x.json").write_text("x", encoding="utf-8")
    old_time = (datetime.now() - timedelta(days=60)).timestamp()
    os.utime(other, (old_time, old_time))

    deleted = prism_retention.execute_cleanup(tmp_path, dry_run=False)
    assert not old_harvest.exists(), "tinyshare_harvest should be deleted"
    assert not old_research.exists(), "tinyshare_research_harvest should be deleted"
    assert other.exists(), "tinyshare_market_supplement must NOT be deleted by harvest target"
    assert old_harvest in deleted
    assert old_research in deleted
