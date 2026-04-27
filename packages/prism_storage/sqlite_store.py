from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from .paths import DEFAULT_DB_PATH, ensure_data_dirs


SCHEMA_VERSION = 1
RECOVERABLE_DATABASE_ERRORS = (
    "database disk image is malformed",
    "file is not a database",
)


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    if db_path:
        path = Path(db_path).expanduser()
    else:
        ensure_data_dirs()
        path = DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return _connect(path)
    except sqlite3.DatabaseError as exc:
        if not is_recoverable_database_error(exc):
            raise
        quarantine_corrupt_database(path)
        return _connect(path)


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        migrate(conn)
        return conn
    except Exception:
        conn.close()
        raise


def is_recoverable_database_error(exc: sqlite3.DatabaseError) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in RECOVERABLE_DATABASE_ERRORS)


def quarantine_corrupt_database(path: str | Path) -> list[Path]:
    target = Path(path).expanduser()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    moved: list[Path] = []
    for candidate in (target, Path(f"{target}-wal"), Path(f"{target}-shm")):
        if not candidate.exists():
            continue
        quarantine_path = unique_quarantine_path(candidate, stamp)
        candidate.replace(quarantine_path)
        moved.append(quarantine_path)
    return moved


def unique_quarantine_path(path: Path, stamp: str) -> Path:
    candidate = Path(f"{path}.corrupt-{stamp}")
    counter = 1
    while candidate.exists():
        candidate = Path(f"{path}.corrupt-{stamp}-{counter}")
        counter += 1
    return candidate


@contextmanager
def connection(db_path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS storage_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_state (
            key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL,
            schema_version INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL,
            source_path TEXT,
            source_mtime_ns INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS task_runs (
            run_id TEXT PRIMARY KEY,
            task_name TEXT NOT NULL,
            title TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            exit_code INTEGER,
            pid INTEGER,
            cwd TEXT,
            command_json TEXT NOT NULL,
            log_path TEXT,
            meta_path TEXT,
            payload_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            source_mtime_ns INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_task_runs_task_started
        ON task_runs(task_name, started_at DESC)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS artifacts (
            artifact_id TEXT PRIMARY KEY,
            artifact_type TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT '',
            run_id TEXT,
            trade_date TEXT,
            code TEXT,
            path TEXT NOT NULL UNIQUE,
            path_kind TEXT NOT NULL DEFAULT 'workspace',
            sha256 TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            mtime TEXT NOT NULL,
            generated_at TEXT,
            schema_version INTEGER NOT NULL DEFAULT 1,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_artifacts_type_date
        ON artifacts(artifact_type, trade_date, generated_at)
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO storage_migrations(version, name)
        VALUES (?, ?)
        """,
        (SCHEMA_VERSION, "initial storage schema"),
    )
