"""Local runtime environment loading for Prism.

Prism normally receives secrets from the process environment.  For local
desktop runs, also support the project root ``.env`` file that is already
gitignored.  Values are loaded silently and are never logged here.
"""

from __future__ import annotations

import os
import re
from pathlib import Path


_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def project_root() -> Path:
    override = os.environ.get("PRISM_REPO_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def project_env_path(root: Path | None = None) -> Path:
    return (root or project_root()) / ".env"


def _unquote(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        text = text[1:-1]
        if value.strip().startswith('"'):
            text = text.replace(r"\n", "\n").replace(r"\t", "\t").replace(r"\"", '"').replace(r"\\", "\\")
    return text


def read_project_env(root: Path | None = None) -> dict[str, str]:
    env_path = project_env_path(root)
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not _KEY_RE.fullmatch(key):
            continue
        values[key] = _unquote(value)
    return values


def load_project_env(*, root: Path | None = None, override: bool = False) -> set[str]:
    loaded: set[str] = set()
    for key, value in read_project_env(root).items():
        if key in os.environ and not override:
            continue
        os.environ[key] = value
        loaded.add(key)
    return loaded


def configured_env_names(names: tuple[str, ...] | list[str], *, root: Path | None = None) -> list[str]:
    load_project_env(root=root)
    return [name for name in names if os.environ.get(name, "").strip()]


__all__ = ["configured_env_names", "load_project_env", "project_env_path", "project_root", "read_project_env"]
