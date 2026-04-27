from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .paths import REPO_ROOT
from .repositories import ArtifactRepository


ARTIFACT_SUFFIXES = {".json", ".md", ".txt", ".docx", ".log"}
ARTIFACT_SCAN_DIRS = (
    "data/artifacts",
    "apps/data",
    "stock-screener/data",
    "stock-analyzer/data",
    "data/history",
    "data/evaluation",
)
SKIP_PARTS = {
    "__pycache__",
    "cache",
    "capital_flow_cache",
    "fund_flow_cache",
    "fundamentals_cache",
    "index_cons_cache",
    "node_modules",
}
DATE_RE = re.compile(r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})")


@dataclass(frozen=True)
class ArtifactCandidate:
    path: Path
    artifact_type: str
    source: str
    trade_date: str | None = None
    generated_at: str | None = None
    metadata: dict[str, Any] | None = None


def discover_artifact_files(repo_root: str | Path | None = None) -> list[Path]:
    root = Path(repo_root).expanduser().resolve() if repo_root else REPO_ROOT
    files: list[Path] = []
    for relative_dir in ARTIFACT_SCAN_DIRS:
        directory = root / relative_dir
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if not path.is_file():
                continue
            relative_parts = path.relative_to(root).parts
            if any(part in SKIP_PARTS for part in relative_parts):
                continue
            if path.suffix.lower() not in ARTIFACT_SUFFIXES:
                continue
            files.append(path)
    return sorted(files)


def classify_artifact(path: str | Path, repo_root: str | Path | None = None) -> ArtifactCandidate:
    root = Path(repo_root).expanduser().resolve() if repo_root else REPO_ROOT
    target = Path(path).expanduser().resolve()
    relative = target.relative_to(root)
    parts = relative.parts
    name = target.name
    metadata: dict[str, Any] = {
        "relative_path": str(relative),
        "scanner": "default",
    }

    source = infer_source(parts)
    artifact_type = infer_artifact_type(parts, name)
    json_metadata = read_json_artifact_metadata(target)
    metadata.update(json_metadata["metadata"])
    trade_date = json_metadata.get("trade_date") or infer_trade_date(str(relative))
    generated_at = json_metadata.get("generated_at")

    return ArtifactCandidate(
        path=target,
        artifact_type=artifact_type,
        source=source,
        trade_date=trade_date,
        generated_at=generated_at,
        metadata=metadata,
    )


def index_artifacts(
    *,
    db_path: str | Path | None = None,
    repo_root: str | Path | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    root = Path(repo_root).expanduser().resolve() if repo_root else REPO_ROOT
    repository = ArtifactRepository(db_path, repo_root=root)
    files = discover_artifact_files(root)
    if limit is not None:
        files = files[:limit]

    indexed = 0
    failed: list[dict[str, str]] = []
    counts: dict[str, int] = {}
    for path in files:
        try:
            candidate = classify_artifact(path, root)
            repository.register_file(
                candidate.path,
                artifact_type=candidate.artifact_type,
                source=candidate.source,
                trade_date=candidate.trade_date,
                generated_at=candidate.generated_at,
                metadata=candidate.metadata,
            )
            indexed += 1
            counts[candidate.artifact_type] = counts.get(candidate.artifact_type, 0) + 1
        except Exception as exc:
            failed.append({"path": str(path), "error": str(exc)})

    return {
        "ok": not failed,
        "indexed": indexed,
        "failed": failed,
        "counts": counts,
    }


def infer_source(parts: tuple[str, ...]) -> str:
    if parts[:2] == ("apps", "data"):
        return "control_panel"
    if parts and parts[0] == "stock-screener":
        return "screener"
    if parts and parts[0] == "stock-analyzer":
        return "analyzer"
    if parts[:2] == ("data", "history"):
        return "public_history"
    if parts[:2] == ("data", "evaluation"):
        return "evaluation"
    return parts[0] if parts else "unknown"


def infer_artifact_type(parts: tuple[str, ...], name: str) -> str:
    part_set = set(parts)
    stem = Path(name).stem

    if "control_panel_runs" in part_set:
        return "control_panel_run_log" if name.endswith(".log") else "control_panel_run_meta"
    if "command_brief" in part_set or stem.startswith("prism_command_brief"):
        return "command_brief"
    if "daily_snapshots" in part_set:
        return "daily_snapshot"
    if "ai_history" in part_set or stem.startswith("ai_screening"):
        return "ai_screening_snapshot"
    if "quality_gates" in part_set or stem.startswith("quality_gate"):
        return "quality_gate"
    if "stale_outputs" in part_set:
        return "stale_output"
    if "reports" in part_set:
        return "report"
    if "research_backfill" in part_set:
        return "research_backfill"
    if "evaluation" in part_set:
        return "evaluation_output"
    if stem.endswith("_result") or stem in {"scan_result", "ai_screening_result"}:
        return "workflow_latest"
    return "workflow_artifact"


def infer_trade_date(value: str) -> str | None:
    match = DATE_RE.search(value)
    if not match:
        return None
    return "-".join(match.groups())


def read_json_artifact_metadata(path: Path) -> dict[str, Any]:
    if path.suffix.lower() != ".json":
        return {"metadata": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"metadata": {}}
    if not isinstance(payload, dict):
        return {"metadata": {}}

    generated_at = first_text(
        payload,
        "generated_at",
        "timestamp",
        "checked_at",
        "started_at",
        "scan_timestamp",
        "source_scan_timestamp",
    )
    trade_date = first_text(payload, "trade_date") or infer_trade_date(generated_at or "")
    metadata = {
        key: value
        for key in ("validation_status", "pool", "pool_label", "status", "task_name")
        if (value := payload.get(key)) not in (None, "")
    }
    return {
        "generated_at": generated_at,
        "trade_date": trade_date,
        "metadata": metadata,
    }


def first_text(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value in (None, ""):
            continue
        return str(value)
    return None
