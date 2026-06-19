"""Data retention cleanup for Prism runtime artifacts.

Deletes aged files under the data tree to prevent unbounded growth. The
data/ directories are gitignored, so growth is otherwise invisible.

Design:
  - Two phases: ``plan_cleanup`` (computes what would be deleted, no side
    effects) and ``execute_cleanup`` (performs the deletion). A dry-run
    runs only the plan.
  - Strict whitelist: prism.db*, scheduler_state.json,
    scheduler_events.jsonl, config/, schemas/, quant/labels/ are NEVER
    touched regardless of age.
  - Each cleanup target has its own retention window, overridable via env.

Usage:
    python3 apps/scripts/prism_retention.py --dry-run
    python3 apps/scripts/prism_retention.py
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT_DEFAULT = REPO_ROOT / "data"

# Files that must never be deleted regardless of age.
PROTECTED_NAMES = {
    "prism.db",
    "prism.db-wal",
    "prism.db-shm",
    "scheduler_state.json",
    "scheduler_events.jsonl",
}
# Top-level dirs under data/ that are entirely protected.
PROTECTED_TOP_DIRS = {"config", "schemas", "quant"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


@dataclass
class CleanupEntry:
    root: Path
    pattern: str
    retention_days: int
    data_root: Path
    files: list[Path] = field(default_factory=list)

    @property
    def label(self) -> str:
        try:
            rel = self.root.relative_to(self.data_root)
            return f"{self.data_root.name}/{rel} ({self.pattern}, {self.retention_days}d)"
        except ValueError:
            return f"{self.root} ({self.pattern}, {self.retention_days}d)"


def _is_protected(path: Path, data_root: Path) -> bool:
    if path.name in PROTECTED_NAMES:
        return True
    try:
        rel = path.relative_to(data_root)
    except ValueError:
        return False
    parts = rel.parts
    # Protect whole top-level dirs (config/, schemas/, quant/).
    if parts and parts[0] in PROTECTED_TOP_DIRS:
        return True
    return False


def _build_entries(data_root: Path) -> list[CleanupEntry]:
    run_days = _env_int("PRISM_RETENTION_RUN_DAYS", 30)
    log_days = _env_int("PRISM_RETENTION_LOG_DAYS", 14)
    corrupt_days = _env_int("PRISM_RETENTION_CORRUPT_DAYS", 30)
    dataset_days = _env_int("PRISM_RETENTION_DATASET_DAYS", 90)
    harvest_days = _env_int("PRISM_RETENTION_HARVEST_DAYS", 30)

    entries = [
        CleanupEntry(data_root / "scheduled_runs" / "logs", "*", run_days, data_root),
        CleanupEntry(data_root / "scheduled_runs" / "runs", "*", run_days, data_root),
        CleanupEntry(data_root / "runtime", "*.log", log_days, data_root),
        CleanupEntry(data_root / "runtime", "*.corrupt-*", corrupt_days, data_root),
        CleanupEntry(data_root / "prism_data" / "datasets", "*", dataset_days, data_root),
        CleanupEntry(data_root / "prism_data", "tinyshare_*_harvest", harvest_days, data_root),
    ]
    return [e for e in entries if e.root.exists()]


def _collect_expired(entry: CleanupEntry, now: datetime) -> list[Path]:
    cutoff = now - timedelta(days=entry.retention_days)
    expired: list[Path] = []
    if entry.pattern.startswith("tinyshare_"):
        # Match run-dirs whose name contains the harvest suffix. The pattern
        # "tinyshare_*_harvest" must match real dirs like "tinyshare_harvest"
        # and "tinyshare_research_harvest" — so we match on the "_harvest"
        # suffix and a "tinyshare_" prefix, NOT on the literal "*" (which
        # would collapse to a double underscore and match nothing).
        suffix = "_harvest"
        for child in entry.root.iterdir():
            if child.is_dir() and child.name.startswith("tinyshare_") and child.name.endswith(suffix):
                if _is_protected(child, entry.data_root):
                    continue
                try:
                    mtime = datetime.fromtimestamp(child.stat().st_mtime)
                except OSError:
                    continue
                if mtime < cutoff:
                    expired.append(child)
        return expired
    for path in entry.root.glob(entry.pattern):
        if path.is_dir():
            continue
        if _is_protected(path, entry.data_root):
            continue
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
        except OSError:
            continue
        if mtime < cutoff:
            expired.append(path)
    return expired


@dataclass
class CleanupPlan:
    entries: list[CleanupEntry]
    dry_run: bool
    total_files: int
    total_bytes: int

    def summary(self) -> str:
        mode = "DRY-RUN" if self.dry_run else "EXECUTE"
        lines = [f"[{mode}] {self.total_files} files / {self.total_bytes / 1e6:.1f} MB"]
        for entry in self.entries:
            if entry.files:
                lines.append(f"  {entry.label}: {len(entry.files)} files")
        return "\n".join(lines)


def plan_cleanup(data_root: Path = DATA_ROOT_DEFAULT, *, dry_run: bool = True) -> CleanupPlan:
    now = datetime.now()
    entries = _build_entries(data_root)
    total_files = 0
    total_bytes = 0
    for entry in entries:
        entry.files = _collect_expired(entry, now)
        for f in entry.files:
            try:
                total_bytes += f.stat().st_size
            except OSError:
                pass
            total_files += 1
    return CleanupPlan(entries=entries, dry_run=dry_run, total_files=total_files, total_bytes=total_bytes)


def execute_cleanup(data_root: Path = DATA_ROOT_DEFAULT, *, dry_run: bool = True) -> list[Path]:
    plan = plan_cleanup(data_root, dry_run=dry_run)
    deleted: list[Path] = []
    if dry_run:
        return deleted
    for entry in plan.entries:
        for path in entry.files:
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
                deleted.append(path)
            except OSError:
                pass
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser(description="Prism data retention cleanup")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be deleted without deleting")
    parser.add_argument("--data-root", default=str(DATA_ROOT_DEFAULT))
    args = parser.parse_args()

    data_root = Path(args.data_root)

    if args.dry_run:
        plan = plan_cleanup(data_root, dry_run=True)
        print(plan.summary())
        for entry in plan.entries:
            for f in entry.files[:20]:
                print(f"    {f}")
            if len(entry.files) > 20:
                print(f"    ... and {len(entry.files) - 20} more")
        return 0

    deleted = execute_cleanup(data_root, dry_run=False)
    print(f"Deleted {len(deleted)} files/dirs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
