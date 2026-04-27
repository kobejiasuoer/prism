from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    override = os.environ.get("PRISM_REPO_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


REPO_ROOT = repo_root()
DATA_ROOT = REPO_ROOT / "data"
RUNTIME_ROOT = DATA_ROOT / "runtime"
RUNS_ROOT = RUNTIME_ROOT / "runs"
ARTIFACTS_ROOT = DATA_ROOT / "artifacts"
ANALYTICS_ROOT = DATA_ROOT / "analytics"
CACHE_ROOT = DATA_ROOT / "cache"
HISTORY_ROOT = DATA_ROOT / "history"
DEFAULT_DB_PATH = Path(os.environ.get("PRISM_DB_PATH", RUNTIME_ROOT / "prism.db")).expanduser()


def ensure_data_dirs() -> None:
    for path in (DATA_ROOT, RUNTIME_ROOT, RUNS_ROOT, ARTIFACTS_ROOT, ANALYTICS_ROOT, CACHE_ROOT):
        path.mkdir(parents=True, exist_ok=True)


def workspace_relative(path: str | Path, *, root: Path | None = None) -> str:
    target = Path(path).expanduser().resolve()
    base = (root or REPO_ROOT).resolve()
    try:
        return str(target.relative_to(base))
    except ValueError:
        return str(target)


def resolve_workspace_path(path: str | Path, *, root: Path | None = None) -> Path:
    target = Path(path).expanduser()
    if target.is_absolute():
        return target.resolve()
    return ((root or REPO_ROOT) / target).resolve()


def artifact_dir(*parts: str, root: Path | None = None) -> Path:
    base = (root or REPO_ROOT) / "data" / "artifacts"
    return base.joinpath(*parts)


def command_brief_paths(run_stamp: str, *, root: Path | None = None) -> dict[str, Path]:
    directory = artifact_dir("command_brief", root=root)
    stem = f"prism_command_brief_{run_stamp}"
    return {
        "brief": directory / f"{stem}.txt",
        "report": directory / f"{stem}.md",
        "json": directory / f"{stem}.json",
    }


def control_panel_run_paths(run_id: str, *, root: Path | None = None) -> tuple[Path, Path]:
    directory = (root or REPO_ROOT) / "data" / "runtime" / "runs" / "control_panel"
    return directory / f"{run_id}.json", directory / "logs" / f"{run_id}.log"
