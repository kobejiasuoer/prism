from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_json_or_default(path: str | Path, default: Any = None) -> Any:
    try:
        return load_json(path)
    except Exception:
        return default


def atomic_write_text(path: str | Path, content: str) -> None:
    """Atomically write ``content`` (a str) to ``path``.

    Same atomicity contract as :func:`atomic_write_json` (temp file + fsync +
    os.replace, PID-suffixed temp name, cleanup on failure), for arbitrary
    text content such as JSONL stores.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target.with_name(f".{target.name}.tmp.{os.getpid()}")
    try:
        with tmp_path.open("w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, target)
    except Exception:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


def atomic_write_json(path: str | Path, payload: Any) -> None:
    """Atomically write ``payload`` as JSON to ``path``.

    Writes go to a temp file in the same directory, fsync'd, then
    ``os.replace``'d onto the target. ``os.replace`` is atomic on POSIX and
    Windows, so a crash or ``kill -9`` during the write never leaves a
    truncated/partial target — the previous complete content survives.

    The temp file name embeds the current PID so concurrent *processes*
    (for example the scheduler and a one-off script) do not clobber each
    other's temp file. This does NOT make same-process concurrent calls
    (threads) safe — callers that write the same path from multiple threads
    must serialize themselves. On any failure the temp file is removed so
    the directory does not accumulate clutter.
    """
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))
