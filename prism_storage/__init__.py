from __future__ import annotations

from pathlib import Path


_IMPL_PACKAGE_DIR = Path(__file__).resolve().parents[1] / "packages" / "prism_storage"
if _IMPL_PACKAGE_DIR.exists():
    __path__.append(str(_IMPL_PACKAGE_DIR))

from .repositories import AppStateRepository, ArtifactRepository, TaskRunRepository, WatchlistConfigRepository

__all__ = [
    "AppStateRepository",
    "ArtifactRepository",
    "TaskRunRepository",
    "WatchlistConfigRepository",
]
