from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from .json_store import atomic_write_json
from .paths import HISTORY_ROOT, REPO_ROOT, resolve_workspace_path, workspace_relative
from .repositories import artifact_row_to_dict, load_json_text
from .sqlite_store import connection


def history_export_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def sanitize_for_history(value: Any, *, repo_root: Path) -> Any:
    if isinstance(value, dict):
        return {key: sanitize_for_history(item, repo_root=repo_root) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_for_history(item, repo_root=repo_root) for item in value]
    if not isinstance(value, str):
        return value

    root_text = str(repo_root)
    if value.startswith(root_text):
        return workspace_relative(value, root=repo_root)
    return value.replace(root_text, ".")


def history_target_for_artifact(artifact_path: str) -> Path | None:
    path = Path(artifact_path)
    parts = path.parts
    if parts[:2] != ("data", "artifacts"):
        return None
    remainder = parts[2:]
    if not remainder:
        return None

    suffix = path.suffix.lower()
    if remainder[:1] == ("command_brief",):
        if suffix == ".json":
            return Path("command_brief") / path.name
        return Path("reports") / "command_brief" / path.name
    if remainder[:2] == ("screener", "quality_gates"):
        return Path("quality_gates") / path.name
    if remainder[:2] == ("screener", "reports"):
        return Path("reports") / "screener" / path.name
    if remainder[:2] == ("screener", "stale_outputs"):
        return Path("stale_outputs") / path.name
    if remainder[:2] == ("screener", "ai_screening"):
        return Path("ai_history") / path.name
    if remainder[:2] == ("analyzer", "daily_snapshots"):
        return Path("daily_snapshots") / path.name
    if remainder[:2] == ("analyzer", "quality_gates"):
        return Path("quality_gates") / path.name
    if remainder[:2] in {("analyzer", "reports"), ("analyzer", "handoffs")}:
        return Path("reports") / "analyzer" / path.name
    return Path("artifacts").joinpath(*remainder)


def export_history(
    *,
    db_path: str | Path | None = None,
    repo_root: str | Path | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    include_task_runs: bool = True,
    include_legacy_artifacts: bool = False,
) -> dict[str, Any]:
    root = Path(repo_root).expanduser().resolve() if repo_root else REPO_ROOT
    history_root = root / "data" / "history"
    artifact_rows = _load_artifact_rows(db_path, limit=limit)
    copied: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []

    for artifact in artifact_rows:
        source_path = artifact.get("path") or ""
        target_relative = history_target_for_artifact(source_path)
        if target_relative is None and not include_legacy_artifacts:
            skipped.append({"path": source_path, "reason": "outside artifact store"})
            continue
        if target_relative is None:
            target_relative = Path("artifacts") / Path(source_path).name

        source_abs = resolve_workspace_path(source_path, root=root)
        target_abs = history_root / target_relative
        if not source_abs.is_file():
            skipped.append({"path": source_path, "reason": "missing source"})
            continue
        copied.append(
            {
                "source": workspace_relative(source_abs, root=root),
                "target": workspace_relative(target_abs, root=root),
            }
        )
        if not dry_run:
            target_abs.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_abs, target_abs)

    task_runs = _load_task_runs(db_path) if include_task_runs else []
    exported_runs: list[str] = []
    for run in task_runs:
        run_id = str(run.get("task_id") or run.get("run_id") or "").strip()
        if not run_id:
            continue
        exported_runs.append(run_id)
        if dry_run:
            continue
        payload = sanitize_for_history(run, repo_root=root)
        atomic_write_json(history_root / "control_panel_runs" / f"{run_id}.json", payload)

    manifest = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "copied_artifacts": copied,
        "skipped_artifacts": skipped,
        "exported_task_runs": exported_runs,
        "dry_run": dry_run,
    }
    manifest_path = history_root / "manifests" / f"storage_export_{history_export_stamp()}.json"
    if not dry_run:
        atomic_write_json(manifest_path, manifest)

    return {
        "ok": True,
        "copied": len(copied),
        "skipped": len(skipped),
        "task_runs": len(exported_runs),
        "manifest_path": workspace_relative(manifest_path, root=root),
        "dry_run": dry_run,
    }


def _load_artifact_rows(db_path: str | Path | None, *, limit: int | None = None) -> list[dict[str, Any]]:
    query = "SELECT * FROM artifacts ORDER BY COALESCE(generated_at, mtime) DESC, path"
    params: tuple[Any, ...] = ()
    if limit is not None:
        query += " LIMIT ?"
        params = (limit,)
    with connection(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
    return [artifact_row_to_dict(row) for row in rows]


def _load_task_runs(db_path: str | Path | None) -> list[dict[str, Any]]:
    with connection(db_path) as conn:
        rows = conn.execute(
            "SELECT payload_json FROM task_runs ORDER BY COALESCE(started_at, updated_at) DESC"
        ).fetchall()
    return [item for row in rows if isinstance((item := load_json_text(row["payload_json"], {})), dict)]
