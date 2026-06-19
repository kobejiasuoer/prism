# stock-screener/ (legacy container)

This directory is a **legacy skill container** kept for backward-compatible
data reads. It is **not** the active screener implementation.

## What lives here

- `data/` — historical screening snapshots and `research_backfill/` artifacts.
  **Still read by the live system** as a fallback data root:
  - `apps/control-panel/dashboard_data.py` (`SCREENER_DATA_DIRS`)
  - `apps/scripts/prism_canonical.py` (`SCREENER_DATA_DIR`)
  - `packages/prism_storage/artifacts.py` (`ARTIFACT_SCAN_DIRS`)
  Do **not** delete `data/` without first rewiring those readers.
- `reports/` — symlink to `data/history/reports/screener`.

## What was removed

- `scripts/` — was 16 symlinks into `packages/screener/`. Removed as dead
  duplicate entry points (verified: no live code imported them; remaining
  references are only in immutable historical run logs and the
  `scripts/scrub-secrets.py` path-rewrite table, which rewrites path
  *strings* and does not read this directory). Use `packages/screener/`
  directly for all workflows.

## Where the real code is

The canonical screener lives in `packages/screener/`. New code must import
from there, never from this directory.
