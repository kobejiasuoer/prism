from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_ROOT = REPO_ROOT / "packages"
if str(PACKAGES_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGES_ROOT))

from prism_storage import json_store  # noqa: E402
from prism_storage.json_store import atomic_write_json, load_json  # noqa: E402


def test_atomic_write_creates_file(tmp_path: Path):
    target = tmp_path / "state.json"
    atomic_write_json(target, {"a": 1})
    assert load_json(target) == {"a": 1}


def test_atomic_write_preserves_existing_on_replace_failure(tmp_path: Path, monkeypatch):
    """If os.replace fails mid-write, the original file must be intact and no
    temp file is left behind. This also covers the write-failure path because
    any exception (write, fsync, or replace) triggers the same cleanup."""
    target = tmp_path / "state.json"
    target.write_text('{"original": true}', encoding="utf-8")

    def boom(src, dst):
        raise OSError("simulated replace failure")

    # Patch os.replace on the actual module object the helper uses, to avoid
    # namespace-package path ambiguity under full-suite import ordering.
    monkeypatch.setattr(json_store.os, "replace", boom)
    with pytest.raises(OSError):
        atomic_write_json(target, {"new": "corrupt"})

    # Original content survived
    assert load_json(target) == {"original": True}
    # No leftover temp file cluttering the directory
    leftovers = [p for p in tmp_path.iterdir() if p.name != "state.json"]
    assert leftovers == [], f"leftover temp files: {leftovers}"


def test_no_temp_leftover_after_successful_writes(tmp_path: Path):
    """Successful writes leave no temp files behind.

    The temp filename embeds the PID (see json_store.atomic_write_json), so
    distinct *processes* cannot collide on the temp name by construction.
    True cross-process concurrency isn't exercised here, but the cleanup
    invariant — no orphaned temps after success — is what matters for
    avoiding directory clutter in the long-running scheduler.
    """
    target = tmp_path / "state.json"
    atomic_write_json(target, {"v": 1})
    atomic_write_json(target, {"v": 2})
    assert load_json(target) == {"v": 2}
    leftovers = [p for p in tmp_path.iterdir() if p.name != "state.json"]
    assert leftovers == []
