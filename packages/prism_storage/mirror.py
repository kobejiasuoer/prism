from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from .artifacts import infer_trade_date, read_json_artifact_metadata
from .paths import REPO_ROOT, workspace_relative
from .repositories import ArtifactRepository


ANALYZER_MIRROR_PATTERNS = (
    ("stock-analyzer/data/daily_snapshots/*.json", "analyzer/daily_snapshots", "daily_snapshot"),
    ("stock-analyzer/data/quality_gate_watchlist_*.json", "analyzer/quality_gates", "quality_gate"),
    ("stock-analyzer/reports/analysis-report-*.md", "analyzer/reports", "analyzer_report"),
    ("stock-analyzer/reports/analysis-summary-*.txt", "analyzer/reports", "analyzer_summary"),
    ("stock-analyzer/reports/analysis-handoff_*.md", "analyzer/handoffs", "analyzer_handoff"),
    ("stock-analyzer/reports/quality_gate_watchlist_*.md", "analyzer/quality_gates", "quality_gate_report"),
)


def artifact_mirroring_enabled() -> bool:
    return os.environ.get("PRISM_MIRROR_ARTIFACTS", "1").lower() in {"1", "true", "yes", "on"}


def mirror_file_to_artifact_store(
    source_path: str | Path,
    relative_target: str | Path,
    *,
    artifact_type: str,
    source: str,
    db_path: str | Path | None = None,
    repo_root: str | Path | None = None,
    trade_date: str | None = None,
    generated_at: str | None = None,
    metadata: dict[str, Any] | None = None,
    overwrite: bool = True,
) -> dict[str, Any]:
    root = Path(repo_root).expanduser().resolve() if repo_root else REPO_ROOT
    source_abs = (root / source_path).resolve() if not Path(source_path).expanduser().is_absolute() else Path(source_path).expanduser().resolve()
    if not source_abs.is_file():
        raise FileNotFoundError(str(source_abs))

    relative = Path(relative_target)
    if relative.is_absolute():
        raise ValueError("relative_target must be workspace-relative")
    if relative.parts[:2] == ("data", "artifacts"):
        target = root / relative
    else:
        target = root / "data" / "artifacts" / relative
    target = target.resolve()

    if target != source_abs:
        target.parent.mkdir(parents=True, exist_ok=True)
        if overwrite or not target.exists():
            shutil.copy2(source_abs, target)

    json_metadata = read_json_artifact_metadata(source_abs)
    merged_metadata = {
        "mirrored_from": workspace_relative(source_abs, root=root),
        **(metadata or {}),
    }
    merged_metadata.update(json_metadata.get("metadata") or {})
    return ArtifactRepository(db_path, repo_root=root).register_file(
        target,
        artifact_type=artifact_type,
        source=source,
        trade_date=trade_date or json_metadata.get("trade_date") or infer_trade_date(source_abs.name),
        generated_at=generated_at or json_metadata.get("generated_at"),
        metadata=merged_metadata,
    )


def mirror_analyzer_artifacts(
    *,
    db_path: str | Path | None = None,
    repo_root: str | Path | None = None,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    root = Path(repo_root).expanduser().resolve() if repo_root else REPO_ROOT
    plans: list[tuple[Path, str, str]] = []
    for pattern, target_dir, artifact_type in ANALYZER_MIRROR_PATTERNS:
        for path in sorted(root.glob(pattern)):
            if path.is_file():
                plans.append((path, f"{target_dir}/{path.name}", artifact_type))
    if limit is not None:
        plans = plans[:limit]

    mirrored: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []
    for source_path, target_relative, artifact_type in plans:
        if dry_run:
            mirrored.append(
                {
                    "source_path": workspace_relative(source_path, root=root),
                    "target_path": f"data/artifacts/{target_relative}",
                    "artifact_type": artifact_type,
                }
            )
            continue
        try:
            artifact = mirror_file_to_artifact_store(
                source_path,
                target_relative,
                artifact_type=artifact_type,
                source="analyzer",
                db_path=db_path,
                repo_root=root,
            )
            mirrored.append(artifact)
        except Exception as exc:
            failed.append({"path": workspace_relative(source_path, root=root), "error": str(exc)})

    return {
        "ok": not failed,
        "planned": len(plans),
        "mirrored": len(mirrored),
        "failed": failed,
        "artifacts": mirrored,
        "dry_run": dry_run,
    }
