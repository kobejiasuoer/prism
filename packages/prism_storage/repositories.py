from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from collections.abc import Iterable
from typing import Any

from .json_store import atomic_write_json, load_json_or_default
from .paths import DEFAULT_DB_PATH, REPO_ROOT, resolve_workspace_path, workspace_relative
from .sqlite_store import connection


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def stat_mtime_ns(path: str | Path | None) -> int:
    if not path:
        return 0
    try:
        return Path(path).expanduser().stat().st_mtime_ns
    except OSError:
        return 0


def dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_json_text(value: str | None, default: Any = None) -> Any:
    if value is None:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


class AppStateRepository:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path).expanduser() if db_path else DEFAULT_DB_PATH

    def get(self, key: str, *, legacy_path: str | Path | None = None, default: Any = None) -> Any:
        legacy = Path(legacy_path).expanduser() if legacy_path else None
        try:
            with connection(self.db_path) as conn:
                row = conn.execute("SELECT * FROM app_state WHERE key = ?", (key,)).fetchone()
                legacy_mtime = stat_mtime_ns(legacy)
                if legacy and legacy.exists() and (row is None or legacy_mtime > int(row["source_mtime_ns"] or 0)):
                    payload = load_json_or_default(legacy, default)
                    self._upsert(conn, key, payload, legacy, legacy_mtime)
                    return payload
                if row is not None:
                    return load_json_text(row["value_json"], default)
        except sqlite3.Error:
            pass

        if legacy and legacy.exists():
            return load_json_or_default(legacy, default)
        return default

    def set(
        self,
        key: str,
        payload: Any,
        *,
        legacy_path: str | Path | None = None,
        schema_version: int = 1,
    ) -> Any:
        legacy = Path(legacy_path).expanduser() if legacy_path else None
        source_mtime = 0
        if legacy:
            atomic_write_json(legacy, payload)
            source_mtime = stat_mtime_ns(legacy)

        try:
            with connection(self.db_path) as conn:
                self._upsert(conn, key, payload, legacy, source_mtime, schema_version=schema_version)
        except sqlite3.Error:
            pass
        return payload

    def _upsert(
        self,
        conn: sqlite3.Connection,
        key: str,
        payload: Any,
        legacy_path: Path | None,
        source_mtime_ns: int,
        *,
        schema_version: int = 1,
    ) -> None:
        conn.execute(
            """
            INSERT INTO app_state(key, value_json, schema_version, updated_at, source_path, source_mtime_ns)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value_json = excluded.value_json,
                schema_version = excluded.schema_version,
                updated_at = excluded.updated_at,
                source_path = excluded.source_path,
                source_mtime_ns = excluded.source_mtime_ns
            """,
            (
                key,
                dump_json(payload),
                schema_version,
                now_str(),
                str(legacy_path) if legacy_path else None,
                source_mtime_ns,
            ),
        )


class TaskRunRepository:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path).expanduser() if db_path else DEFAULT_DB_PATH

    def upsert(self, payload: dict[str, Any], *, legacy_path: str | Path | None = None) -> dict[str, Any]:
        run_id = str(payload.get("task_id") or payload.get("run_id") or "").strip()
        if not run_id:
            raise ValueError("task run payload requires task_id or run_id")
        legacy = Path(legacy_path).expanduser() if legacy_path else None
        source_mtime = stat_mtime_ns(legacy)
        try:
            with connection(self.db_path) as conn:
                self._upsert(conn, payload, legacy, source_mtime)
        except sqlite3.Error:
            pass
        return payload

    def sync_legacy_dirs(self, legacy_dirs: Iterable[str | Path] | None) -> None:
        roots = [Path(path).expanduser() for path in legacy_dirs or []]
        try:
            with connection(self.db_path) as conn:
                for root in roots:
                    if not root.exists():
                        continue
                    for path in root.glob("*.json"):
                        payload = load_json_or_default(path)
                        if isinstance(payload, dict):
                            self._upsert(conn, payload, path, stat_mtime_ns(path))
        except sqlite3.Error:
            return

    def sync_legacy(self, legacy_dir: str | Path | None) -> None:
        self.sync_legacy_dirs([legacy_dir] if legacy_dir else [])

    def list(
        self,
        *,
        legacy_dir: str | Path | None = None,
        legacy_dirs: Iterable[str | Path] | None = None,
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        roots = tuple(legacy_dirs or (() if legacy_dir is None else (legacy_dir,)))
        self.sync_legacy_dirs(roots)
        try:
            with connection(self.db_path) as conn:
                rows = conn.execute(
                    """
                    SELECT payload_json FROM task_runs
                    ORDER BY COALESCE(started_at, updated_at) DESC, updated_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            return [item for row in rows if isinstance((item := load_json_text(row["payload_json"], {})), dict)]
        except sqlite3.Error:
            return self._legacy_list(roots, limit)

    def get(
        self,
        run_id: str,
        *,
        legacy_dir: str | Path | None = None,
        legacy_dirs: Iterable[str | Path] | None = None,
    ) -> dict[str, Any] | None:
        roots = tuple(legacy_dirs or (() if legacy_dir is None else (legacy_dir,)))
        self.sync_legacy_dirs(roots)
        try:
            with connection(self.db_path) as conn:
                row = conn.execute("SELECT payload_json FROM task_runs WHERE run_id = ?", (run_id,)).fetchone()
            if row:
                payload = load_json_text(row["payload_json"], {})
                return payload if isinstance(payload, dict) else None
        except sqlite3.Error:
            pass

        for root in roots:
            path = Path(root).expanduser() / f"{run_id}.json"
            payload = load_json_or_default(path)
            if isinstance(payload, dict):
                return payload
        return None

    def _upsert(
        self,
        conn: sqlite3.Connection,
        payload: dict[str, Any],
        legacy_path: Path | None,
        source_mtime_ns: int,
    ) -> None:
        run_id = str(payload.get("task_id") or payload.get("run_id") or "").strip()
        command = payload.get("command") if isinstance(payload.get("command"), list) else []
        conn.execute(
            """
            INSERT INTO task_runs(
                run_id, task_name, title, status, started_at, finished_at, exit_code, pid,
                cwd, command_json, log_path, meta_path, payload_json, updated_at, source_mtime_ns
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                task_name = excluded.task_name,
                title = excluded.title,
                status = excluded.status,
                started_at = excluded.started_at,
                finished_at = excluded.finished_at,
                exit_code = excluded.exit_code,
                pid = excluded.pid,
                cwd = excluded.cwd,
                command_json = excluded.command_json,
                log_path = excluded.log_path,
                meta_path = excluded.meta_path,
                payload_json = excluded.payload_json,
                updated_at = excluded.updated_at,
                source_mtime_ns = excluded.source_mtime_ns
            """,
            (
                run_id,
                str(payload.get("task_name") or ""),
                str(payload.get("title") or ""),
                str(payload.get("status") or "unknown"),
                payload.get("started_at"),
                payload.get("finished_at"),
                payload.get("exit_code"),
                payload.get("pid"),
                str(payload.get("cwd") or ""),
                dump_json(command),
                str(payload.get("log_path") or ""),
                str(payload.get("meta_path") or legacy_path or ""),
                dump_json(payload),
                now_str(),
                source_mtime_ns,
            ),
        )

    def _legacy_list(self, legacy_dirs: Iterable[str | Path], limit: int) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        paths: list[Path] = []
        for root in legacy_dirs:
            directory = Path(root).expanduser()
            if directory.exists():
                paths.extend(directory.glob("*.json"))
        for path in sorted(paths, key=lambda item: item.stat().st_mtime, reverse=True):
            payload = load_json_or_default(path)
            if isinstance(payload, dict):
                items.append(payload)
        return items[:limit]


class ArtifactRepository:
    def __init__(self, db_path: str | Path | None = None, *, repo_root: str | Path | None = None) -> None:
        self.db_path = Path(db_path).expanduser() if db_path else DEFAULT_DB_PATH
        self.repo_root = Path(repo_root).expanduser().resolve() if repo_root else REPO_ROOT

    def register_file(
        self,
        path: str | Path,
        *,
        artifact_type: str,
        source: str = "",
        run_id: str | None = None,
        trade_date: str | None = None,
        code: str | None = None,
        generated_at: str | None = None,
        schema_version: int = 1,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        target = resolve_workspace_path(path, root=self.repo_root)
        if not target.exists() or not target.is_file():
            raise FileNotFoundError(str(target))

        path_value = workspace_relative(target, root=self.repo_root)
        stat = target.stat()
        digest = file_sha256(target)
        now = now_str()
        artifact_id = hashlib.sha256(path_value.encode("utf-8")).hexdigest()[:24]
        payload = {
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            "source": source,
            "run_id": run_id,
            "trade_date": trade_date,
            "code": code,
            "path": path_value,
            "path_kind": "workspace" if not Path(path_value).is_absolute() else "absolute",
            "sha256": digest,
            "size_bytes": stat.st_size,
            "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "generated_at": generated_at,
            "schema_version": schema_version,
            "metadata": metadata or {},
        }

        with connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO artifacts(
                    artifact_id, artifact_type, source, run_id, trade_date, code, path, path_kind,
                    sha256, size_bytes, mtime, generated_at, schema_version, metadata_json,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    artifact_type = excluded.artifact_type,
                    source = excluded.source,
                    run_id = excluded.run_id,
                    trade_date = excluded.trade_date,
                    code = excluded.code,
                    path_kind = excluded.path_kind,
                    sha256 = excluded.sha256,
                    size_bytes = excluded.size_bytes,
                    mtime = excluded.mtime,
                    generated_at = excluded.generated_at,
                    schema_version = excluded.schema_version,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                (
                    payload["artifact_id"],
                    payload["artifact_type"],
                    payload["source"],
                    payload["run_id"],
                    payload["trade_date"],
                    payload["code"],
                    payload["path"],
                    payload["path_kind"],
                    payload["sha256"],
                    payload["size_bytes"],
                    payload["mtime"],
                    payload["generated_at"],
                    payload["schema_version"],
                    dump_json(payload["metadata"]),
                    now,
                    now,
                ),
            )
        return payload

    def list(self, *, artifact_type: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        query = "SELECT * FROM artifacts"
        params: tuple[Any, ...] = ()
        if artifact_type:
            query += " WHERE artifact_type = ?"
            params = (artifact_type,)
        query += " ORDER BY COALESCE(generated_at, mtime) DESC LIMIT ?"
        params = (*params, limit)

        with connection(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
        return [artifact_row_to_dict(row) for row in rows]


def artifact_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "artifact_id": row["artifact_id"],
        "artifact_type": row["artifact_type"],
        "source": row["source"],
        "run_id": row["run_id"],
        "trade_date": row["trade_date"],
        "code": row["code"],
        "path": row["path"],
        "path_kind": row["path_kind"],
        "sha256": row["sha256"],
        "size_bytes": row["size_bytes"],
        "mtime": row["mtime"],
        "generated_at": row["generated_at"],
        "schema_version": row["schema_version"],
        "metadata": load_json_text(row["metadata_json"], {}),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class WatchlistConfigRepository:
    def __init__(
        self,
        config_path: str | Path | None = None,
        *,
        repo_root: str | Path | None = None,
    ) -> None:
        self.repo_root = Path(repo_root).expanduser().resolve() if repo_root else REPO_ROOT
        self.config_path = (
            Path(config_path).expanduser()
            if config_path
            else self.repo_root / "stock-analyzer" / "config" / "stocks.json"
        )

    def get(self, default: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = load_json_or_default(self.config_path, default or {"stocks": []})
        if not isinstance(payload, dict):
            payload = default or {"stocks": []}
        stocks = payload.get("stocks")
        payload["stocks"] = stocks if isinstance(stocks, list) else []
        return payload

    def set(self, payload: dict[str, Any]) -> Path:
        if not isinstance(payload, dict):
            raise TypeError("watchlist config payload must be a dict")
        stocks = payload.get("stocks")
        payload["stocks"] = stocks if isinstance(stocks, list) else []
        atomic_write_json(self.config_path, payload)
        return self.config_path

    def list_stocks(self, *, active: bool | None = None) -> list[dict[str, Any]]:
        items = [item for item in self.get().get("stocks", []) if isinstance(item, dict)]
        if active is None:
            return items
        return [item for item in items if bool(item.get("active", True)) is active]
