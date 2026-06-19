# Rectification Wave 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate three self-destruct risks (calendar 2027 halt, unbounded data growth, non-atomic scheduler state), add exit-stock return tracking (solves "only tracks one day"), and clean low-risk dead code.

**Architecture:** Six independent tasks (A–F), each self-contained and independently verifiable. Tasks A/C/E/F are low-risk and quick; B (retention) and D (exit tracker) are the substantial ones. All follow TDD. Pricing for the exit tracker reuses the existing `prism_data` gateway `fetch_kline` (daily bars) — no new HTTP code.

**Tech Stack:** Python 3.14, pytest, FastAPI, the `prism_data` provider gateway. Tests live in `tests/` following the existing `sys.path` injection pattern.

**Spec:** `docs/superpowers/specs/2026-06-19-rectification-wave-1-design.md`

**Execution order:** Task A → C → E → F → B → D.

---

## File Structure

New files:
- `apps/scripts/prism_retention.py` — retention cleanup with dry-run (Task B)
- `tests/test_prism_retention.py` — retention tests (Task B)
- `tests/test_trading_calendar_horizon.py` — calendar horizon tests (Task A)
- `packages/screener/exit_return_tracker.py` — exit return calculator (Task D)
- `tests/test_exit_return_tracker.py` — exit tracker tests (Task D)

Modified files:
- `apps/control-panel/trading_calendar.py` — extend holidays + horizon warning (Task A)
- `apps/scripts/prism_scheduler.py` — atomic `write_json` (Task C)
- `apps/control-panel/dashboard_data.py` — atomic writes for state files (Task C)
- `apps/control-panel/decision_ledger.py` — atomic writes for ledger files (Task C)
- `apps/control-panel/refresh_policy.py` — register retention + exit_update cron jobs (Tasks B, D)
- `packages/screener/candidate_lifecycle.py` — call `record_exit` in exited branch (Task D)
- `packages/screener/historical_edge/__init__.py` — add stub annotation (Task F)
- `apps/control-panel/dashboard_data.py:10888-10903` — add comment at historical_edge call (Task F)
- `stock-screener/README.md` — document the legacy directory (Task E)

---

## Task A: Fix trading_calendar 2027 halt

**Files:**
- Modify: `apps/control-panel/trading_calendar.py:55,64-83,125-158`
- Test: `tests/test_trading_calendar_horizon.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_trading_calendar_horizon.py`:

```python
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROL_PANEL_ROOT = REPO_ROOT / "apps" / "control-panel"
if str(CONTROL_PANEL_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROL_PANEL_ROOT))

from trading_calendar import calendar_status, CALENDAR_HORIZON  # noqa: E402


def test_horizon_covers_through_2027():
    """CALENDAR_HORIZON must extend past 2026-12-31 so 2027 does not halt."""
    assert CALENDAR_HORIZON >= date(2027, 12, 31), (
        "CALENDAR_HORIZON must reach end of 2027; system halts past it"
    )


def test_known_2027_holiday_is_recognized():
    """New Year's Day 2027 (a Friday) must classify as holiday, not unknown."""
    # 2027-01-01 is a Friday — must be in STATIC_HOLIDAYS and return holiday
    status = calendar_status("2027-01-01")
    assert status["status"] == "holiday", status


def test_2027_weekday_within_horizon_is_trading_or_holiday():
    """A normal 2027 weekday inside the horizon must not be 'unknown'."""
    # 2027-03-10 is a Wednesday — must be trading (or holiday), never unknown
    status = calendar_status("2027-03-10")
    assert status["status"] in ("trading", "holiday"), status


def test_horizon_warning_when_approaching_edge(monkeypatch):
    """Within EXPIRY_WARNING_DAYS of horizon, payload carries horizon_warning."""
    import trading_calendar

    # Force horizon to 30 days ahead so today is within the warning window
    forced_horizon = date.today() + date.fromordinal(20).toordinal() - date.fromordinal(1).toordinal()
    monkeypatch.setattr(trading_calendar, "CALENDAR_HORIZON", date(2026, 12, 31))
    monkeypatch.setenv("PRISM_TEST_CALENDAR_HORIZON", "2026-12-31")
    status = calendar_status("2026-12-15")
    assert status.get("horizon_warning") is True, status


def test_past_horizon_workday_carries_warning_not_silent_halt():
    """Past horizon on a weekday: status unknown BUT with horizon_warning flag,
    not a bare unknown that silently halts the scheduler."""
    monkeypatch_set = False
    # Use a date clearly past the 2027 horizon if horizon were 2026 — but since
    # we extended horizon to 2027+, test with the override env to simulate past-edge.
    import os
    os.environ["PRISM_TEST_CALENDAR_HORIZON"] = "2026-06-01"
    try:
        # 2026-06-15 is a Monday, past the forced horizon of 2026-06-01
        status = calendar_status("2026-06-15")
        assert status["status"] == "unknown"
        assert status.get("horizon_warning") is True, status
    finally:
        os.environ.pop("PRISM_TEST_CALENDAR_HORIZON", None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_trading_calendar_horizon.py -v`
Expected: FAIL — `test_horizon_covers_through_2027` fails (horizon is 2026-12-31), and `horizon_warning` key does not exist yet.

- [ ] **Step 3: Extend STATIC_HOLIDAYS to 2027**

In `apps/control-panel/trading_calendar.py`, add a 2027 block inside the `STATIC_HOLIDAYS` frozenset (after the 2026 block, before the closing paren). Use the published 2027 CSRC schedule; if the official 2027 notice is not yet available at implementation time, include the fixed-date holidays that are certain (New Year, and mark the rest as "pending official notice" in a comment):

```python
        "2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08",  # 国庆
        # 2027 — fixed-date holidays (certain). Movable-date holidays
        # (Spring Festival / Labor Day / Dragon Boat / Mid-Autumn / National
        # Day) pending the official CSRC 2027 notice; add them when published.
        # Update CALENDAR_HORIZON below when refreshing this list.
        "2027-01-01",                                                              # 元旦 (Friday)
```

- [ ] **Step 4: Bump CALENDAR_HORIZON and add warning constant**

In `apps/control-panel/trading_calendar.py`, replace the horizon line and add the warning-days constant:

```python
# Inclusive last date this calendar is considered authoritative.
# Anything strictly past this date returns ``status="unknown"`` so readiness
# can fail closed.  Bump this when refreshing the holiday list.
CALENDAR_HORIZON: date = date(2027, 12, 31)

# Days before the horizon at which calendar_status emits a ``horizon_warning``
# flag, so operators get a visible nudge to refresh the holiday list before
# the calendar silently degrades.
EXPIRY_WARNING_DAYS: int = int(os.environ.get("PRISM_CALENDAR_WARNING_DAYS", "30"))
```

Add `"EXPIRY_WARNING_DAYS"` to the `__all__` list.

- [ ] **Step 5: Add horizon_warning to calendar_status**

In `apps/control-panel/trading_calendar.py`, modify `calendar_status` to emit the warning flag. Replace the body of `calendar_status` with:

```python
def calendar_status(value: date | datetime | str) -> dict:
    """Classify a date as trading / weekend / holiday / unknown.

    Returns a dict suitable for embedding in readiness payloads:
    ``{"date": "YYYY-MM-DD", "status": "trading"|"weekend"|"holiday"|"unknown",
       "reason": "...", "horizon_warning": bool}``.

    ``horizon_warning`` is True when ``target`` is within
    ``EXPIRY_WARNING_DAYS`` of (or past) the horizon — a nudge to refresh
    the static holiday list before coverage silently degrades.
    """

    target = _coerce_date(value)
    horizon = _override_horizon() or CALENDAR_HORIZON
    days_to_horizon = (horizon - target).days
    warning = days_to_horizon <= EXPIRY_WARNING_DAYS
    if target > horizon:
        return {
            "date": target.strftime("%Y-%m-%d"),
            "status": "unknown",
            "reason": f"calendar coverage ends {horizon.strftime('%Y-%m-%d')}",
            "horizon_warning": True,
        }
    if target.weekday() >= 5:
        return {
            "date": target.strftime("%Y-%m-%d"),
            "status": "weekend",
            "reason": "weekend",
            "horizon_warning": warning,
        }
    overrides = set(_override_holidays())
    if target in STATIC_HOLIDAYS or target in overrides:
        return {
            "date": target.strftime("%Y-%m-%d"),
            "status": "holiday",
            "reason": "exchange holiday",
            "horizon_warning": warning,
        }
    return {
        "date": target.strftime("%Y-%m-%d"),
        "status": "trading",
        "reason": "weekday and not on holiday list",
        "horizon_warning": warning,
    }
```

- [ ] **Step 6: Fix the test_horizon_warning test to use a clean override**

The `test_horizon_warning_when_approaching_edge` test written in Step 1 has a buggy `forced_horizon` line. Replace that test's body with a clean version:

```python
def test_horizon_warning_when_approaching_edge(monkeypatch):
    """Within EXPIRY_WARNING_DAYS of horizon, payload carries horizon_warning."""
    # Force horizon to 2026-12-31; a date 15 days before is within the 30-day window
    monkeypatch.setenv("PRISM_TEST_CALENDAR_HORIZON", "2026-12-31")
    status = calendar_status("2026-12-15")
    assert status.get("horizon_warning") is True, status


def test_no_warning_well_inside_horizon(monkeypatch):
    """A date far from the horizon must not carry horizon_warning."""
    monkeypatch.setenv("PRISM_TEST_CALENDAR_HORIZON", "2027-12-31")
    status = calendar_status("2027-01-05")
    assert status.get("horizon_warning") is False, status
```

- [ ] **Step 7: Run all calendar tests, verify pass**

Run: `pytest tests/test_trading_calendar_horizon.py -v`
Expected: PASS — all tests green.

- [ ] **Step 8: Run full suite to confirm no regression**

Run: `pytest -q`
Expected: PASS — no regressions in scheduler/readiness tests that consume `calendar_status`.

- [ ] **Step 9: Commit**

```bash
git add apps/control-panel/trading_calendar.py tests/test_trading_calendar_horizon.py
git commit -m "fix(calendar): extend horizon to 2027 + horizon_warning flag

Prevents the scheduler from silently halting on the first 2027 trading
day. calendar_status now emits horizon_warning when within 30 days of
(or past) CALENDAR_HORIZON, nudging operators to refresh the holiday
list before coverage degrades."
```

---

## Task C: Atomic scheduler state writes

**Files:**
- Modify: `apps/scripts/prism_scheduler.py:107-109` (and add helper)
- Create: `apps/scripts/atomic_write.py`
- Modify: `apps/control-panel/dashboard_data.py` (state write sites)
- Modify: `apps/control-panel/decision_ledger.py` (state write sites)
- Test: `tests/test_atomic_write.py`

- [ ] **Step 1: Write the failing test for atomic_write_text**

Create `tests/test_atomic_write.py`:

```python
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "apps" / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from atomic_write import atomic_write_text  # noqa: E402


def test_atomic_write_creates_file(tmp_path: Path):
    target = tmp_path / "state.json"
    atomic_write_text(target, '{"a": 1}')
    assert target.read_text(encoding="utf-8") == '{"a": 1}'


def test_atomic_write_preserves_existing_on_replace_failure(tmp_path: Path, monkeypatch):
    """If os.replace fails mid-write, the original file must be intact."""
    target = tmp_path / "state.json"
    target.write_text('{"original": true}', encoding="utf-8")

    def boom(src, dst):
        raise OSError("simulated replace failure")

    monkeypatch.setattr("atomic_write.os.replace", boom)
    with pytest.raises(OSError):
        atomic_write_text(target, '{"new": "corrupt"}')

    # Original content survived
    assert target.read_text(encoding="utf-8") == '{"original": true}'
    # No leftover temp file cluttering the directory
    leftovers = [p for p in tmp_path.iterdir() if p.name != "state.json"]
    assert leftovers == [], f"leftover temp files: {leftovers}"


def test_atomic_write_cleans_temp_on_failure(tmp_path: Path, monkeypatch):
    target = tmp_path / "state.json"
    target.write_text("orig", encoding="utf-8")

    real_replace = os.replace

    def fail_once(src, dst):
        raise OSError("boom")

    monkeypatch.setattr("atomic_write.os.replace", fail_once)
    with pytest.raises(OSError):
        atomic_write_text(target, "new")

    assert target.read_text(encoding="utf-8") == "orig"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_atomic_write.py -v`
Expected: FAIL — `ModuleNotFoundError: atomic_write`.

- [ ] **Step 3: Create the atomic_write helper**

Create `apps/scripts/atomic_write.py`:

```python
"""Atomic file-write helpers.

Writes go to a temp file in the same directory, fsync'd, then ``os.replace``'d
onto the target. ``os.replace`` is atomic on POSIX and Windows, so a crash or
``kill -9`` during the write never leaves a truncated/partial target file —
the previous complete content survives.

The temp file is named with the current PID to avoid collisions when multiple
processes write to different targets concurrently. On any failure the temp
file is removed so the directory does not accumulate clutter.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def atomic_write_text(path: Path, content: str) -> None:
    """Atomically write ``content`` (a str) to ``path``.

    If the write or the final replace fails, ``path`` retains its prior
    content and the temp file is cleaned up.
    """

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        with tmp.open("w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def atomic_write_json(path: Path, payload: object, *, ensure_ascii: bool = False, indent: int = 2) -> None:
    """Atomically write ``payload`` as JSON to ``path``."""

    atomic_write_text(path, json.dumps(payload, ensure_ascii=ensure_ascii, indent=indent))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_atomic_write.py -v`
Expected: PASS.

- [ ] **Step 5: Wire atomic_write into prism_scheduler write_json**

In `apps/scripts/prism_scheduler.py`, first add the import near the other imports (after the existing `from pathlib import Path` etc.):

```python
from atomic_write import atomic_write_text
```

Then replace the `write_json` function (around line 107-109) with:

```python
def write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2),
    )
```

- [ ] **Step 6: Wire atomic_write into dashboard_data state writes**

In `apps/control-panel/dashboard_data.py`, add the import after the existing `sys.path` manipulation block near the top (after line ~42):

```python
from atomic_write import atomic_write_json
```

(The `apps/scripts` dir is already on `sys.path` because the control-panel imports it — verify by checking `sys.path` contains the scripts root; if not, add `SCRIPTS_ROOT` insertion matching the pattern at the top of the file.)

Find the state-file write sites that use `json.dump` or `path.write_text` for: `today_action_decisions.json` and `ask_recent_queries.json`. Replace each `json.dump(...)` / `with open(...) as f: json.dump(...)` block with `atomic_write_json(path, payload)`. Use grep to locate them:

```bash
grep -n "today_action_decisions.json\|ask_recent_queries.json" apps/control-panel/dashboard_data.py
```

For each write site found, replace the open+json.dump pattern with `atomic_write_json(the_path, the_payload)`.

- [ ] **Step 7: Wire atomic_write into decision_ledger state writes**

In `apps/control-panel/decision_ledger.py`, add the same import. Then find write sites:

```bash
grep -n "json.dump\|\.write_text\|_write_decisions_file\|_write_review_cases" apps/control-panel/decision_ledger.py
```

Replace the body of `_write_decisions_file` and `_read_review_cases_file`'s write counterpart (the function that persists review cases) to use `atomic_write_json`. Preserve the exact payload shape each currently writes.

- [ ] **Step 8: Run full test suite**

Run: `pytest -q`
Expected: PASS. If a test asserts on the exact write mechanism (e.g. mocks `path.write_text`), update it to mock `atomic_write_text` instead.

- [ ] **Step 9: Commit**

```bash
git add apps/scripts/atomic_write.py apps/scripts/prism_scheduler.py apps/control-panel/dashboard_data.py apps/control-panel/decision_ledger.py tests/test_atomic_write.py
git commit -m "fix(state): atomic writes for scheduler/ledger state files

State files (scheduler_state.json, today_action_decisions.json,
decisions/{date}.json, review_cases.json) now use temp-rename atomic
writes via os.replace, so a crash mid-write can no longer corrupt the
dedup keys and cause duplicate job launches. Had a prior corruption
precedent (prism.db.corrupt-* in data/runtime)."
```

---

## Task E: Clean stock-screener dead symlinks

**Files:**
- Delete: `stock-screener/scripts/*` (symlinks only — verify each is a symlink first)
- Create: `stock-screener/README.md`

- [ ] **Step 1: Verify every entry in stock-screener/scripts is a symlink**

Run:
```bash
ls -la stock-screener/scripts/
```
Expected: every entry shows `->` (symlink) pointing to `../packages/screener/...`. If any entry is a real file (not a symlink), STOP and report — the spec assumed all are symlinks.

- [ ] **Step 2: Verify no code imports from stock-screener/scripts**

Run:
```bash
grep -rn "stock-screener/scripts" --include="*.py" --include="*.sh" --include="*.toml" . | grep -v "stock-screener/scripts/.*->"
```
Expected: no matches (the scripts are only invoked via their symlink path in documentation, never imported). If matches appear, evaluate each before proceeding.

- [ ] **Step 3: Remove the symlinks**

```bash
git rm stock-screener/scripts/*.py stock-screener/scripts/*.sh 2>/dev/null || true
# If scripts/ had subdirectories, remove them too
git rm -r stock-screener/scripts/ 2>/dev/null || true
```

Then verify the directory is gone: `ls stock-screener/scripts/ 2>&1` should report "No such file or directory".

- [ ] **Step 4: Add a README explaining the legacy directory**

Create `stock-screener/README.md`:

```markdown
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

- `scripts/` — was 17 symlinks into `packages/screener/`. Removed as dead
  duplicate entry points. Use `packages/screener/` directly for all workflows.

## Where the real code is

The canonical screener lives in `packages/screener/`. New code must import
from there, never from this directory.
```

- [ ] **Step 5: Run full verification**

```bash
pytest -q
```
Expected: PASS.

```bash
cd apps/web && ./node_modules/.bin/next build && cd ../..
```
Expected: build succeeds (it does not touch stock-screener, but confirms no hidden coupling).

- [ ] **Step 6: Commit**

```bash
git add -A stock-screener/
git commit -m "chore: remove dead stock-screener/scripts symlinks, document legacy dir

The scripts/ were 17 symlinks into packages/screener/ — dead duplicate
entry points. data/ is preserved because dashboard_data/prism_canonical/
artifacts.py still read it as a fallback root (verified). Adds a README
so the next reader does not mistake this for the active implementation."
```

---

## Task F: Annotate historical_edge as unfinished research stub

**Files:**
- Modify: `packages/screener/historical_edge/__init__.py` (top docstring)
- Modify: `apps/control-panel/dashboard_data.py:10888-10903` (call-site comment)

- [ ] **Step 1: Read the current __init__.py header and the stub-return function**

Run:
```bash
sed -n '1,90p' packages/screener/historical_edge/__init__.py
```
Note the exact line of the stub-return function (`build_historical_edge_snapshot`, around line 60-83) and the existing module docstring.

- [ ] **Step 2: Add a prominent module-level status banner**

At the very top of `packages/screener/historical_edge/__init__.py` (before any existing docstring content, or replacing the first lines of the existing docstring), insert:

```python
"""historical_edge — UNFINISHED RESEARCH STUB.

Status: NOT wired into production. The sole caller
(``apps/control-panel/dashboard_data.py``) invokes
``build_historical_edge_snapshot(..., sample_pool=None)``, which always
short-circuits to ``{"coverage_quality": "insufficient"}`` because no
sample pool is ever provided. Runtime output is therefore always a stub.

To activate this module you must:
  1. Build the sample pool via ``apps/scripts/build_historical_edge_sample_pool.py``
     and wire its output path into the dashboard call.
  2. Add a scheduler job to refresh the pool.
Until then, treat all output here as placeholder.

(original module docstring follows below)
"""
```

Keep the original docstring content below this banner (adjust the triple-quote nesting so the file remains valid Python — the banner above is the module docstring; if the file already had one, fold its content in).

- [ ] **Step 3: Add a call-site comment in dashboard_data.py**

Find the historical_edge call:
```bash
grep -n "build_historical_edge_snapshot\|historical_edge" apps/control-panel/dashboard_data.py
```

At the call site (around line 10888-10903), add a comment immediately above the call:

```python
# NOTE: historical_edge is an unfinished research stub. sample_pool is
# hardcoded None, so this always returns coverage_quality=insufficient.
# See packages/screener/historical_edge/__init__.py for activation steps.
```

- [ ] **Step 4: Run full test suite**

Run: `pytest -q`
Expected: PASS (comment/docstring-only change).

- [ ] **Step 5: Commit**

```bash
git add packages/screener/historical_edge/__init__.py apps/control-panel/dashboard_data.py
git commit -m "docs(historical_edge): mark as unfinished research stub

The module always returns a stub because its sole caller passes
sample_pool=None. Adds a prominent status banner and call-site comment
so the next reader does not assume it produces real edge statistics."
```

---

## Task B: Data retention cleanup task

**Files:**
- Create: `apps/scripts/prism_retention.py`
- Create: `tests/test_prism_retention.py`
- Modify: `apps/control-panel/refresh_policy.py` (register cron job)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_prism_retention.py`:

```python
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "apps" / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import prism_retention  # noqa: E402


def _make_old_file(dir_path: Path, name: str, days_old: int) -> Path:
    """Create a file and backdate its mtime by days_old days."""
    dir_path.mkdir(parents=True, exist_ok=True)
    f = dir_path / name
    f.write_text("stale", encoding="utf-8")
    old_time = (datetime.now() - timedelta(days=days_old)).timestamp()
    os.utime(f, (old_time, old_time))
    return f


def _make_fresh_file(dir_path: Path, name: str) -> Path:
    dir_path.mkdir(parents=True, exist_ok=True)
    f = dir_path / name
    f.write_text("fresh", encoding="utf-8")
    return f


def test_dry_run_does_not_delete(tmp_path: Path):
    log_dir = tmp_path / "scheduled_runs" / "logs"
    old = _make_old_file(log_dir, "old.json", days_old=60)
    plan = prism_retention.plan_cleanup(tmp_path, dry_run=True)
    assert old.exists(), "dry-run must not delete files"
    assert any(old in entry.files for entry in plan.entries if "scheduled_runs" in str(entry.root))


def test_real_run_deletes_only_expired(tmp_path: Path):
    log_dir = tmp_path / "scheduled_runs" / "logs"
    old = _make_old_file(log_dir, "old.json", days_old=60)
    fresh = _make_fresh_file(log_dir, "fresh.json")
    deleted = prism_retention.execute_cleanup(tmp_path, dry_run=False)
    assert not old.exists()
    assert fresh.exists()
    assert old in deleted
    assert fresh not in deleted


def test_whitelist_protected_files(tmp_path: Path):
    """prism.db, scheduler_state.json, config/, schemas/ must never be deleted."""
    runtime = tmp_path / "runtime"
    runtime.mkdir(parents=True)
    old_db = _make_old_file(runtime, "prism.db", days_old=999)
    config_dir = tmp_path / "config"
    old_cfg = _make_old_file(config_dir, "stock-parameters.json", days_old=999)
    schemas_dir = tmp_path / "schemas"
    old_schema = _make_old_file(schemas_dir, "stock-parameters.json", days_old=999)
    deleted = prism_retention.execute_cleanup(tmp_path, dry_run=False)
    assert old_db.exists(), "prism.db must be protected"
    assert old_cfg.exists(), "config/ must be protected"
    assert old_schema.exists(), "schemas/ must be protected"
    assert old_db not in deleted


def test_log_files_respect_retention(tmp_path: Path):
    runtime = tmp_path / "runtime"
    old_log = _make_old_file(runtime, "prism_backend.log", days_old=30)
    fresh_log = _make_old_file(runtime, "fresh.log", days_old=1)
    deleted = prism_retention.execute_cleanup(tmp_path, dry_run=False)
    assert not old_log.exists()
    assert fresh_log.exists()


def test_corrupt_files_respect_separate_retention(tmp_path: Path):
    runtime = tmp_path / "runtime"
    # 45 days old — past the 30-day corrupt retention
    old_corrupt = _make_old_file(runtime, "prism.db.corrupt-old", days_old=45)
    # 10 days old — within 30-day corrupt retention
    new_corrupt = _make_old_file(runtime, "prism.db.corrupt-new", days_old=10)
    deleted = prism_retention.execute_cleanup(tmp_path, dry_run=False)
    assert not old_corrupt.exists()
    assert new_corrupt.exists()


def test_env_overrides_retention_days(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PRISM_RETENTION_LOG_DAYS", "5")
    log_dir = tmp_path / "runtime"
    # 10 days old — normally kept (default 14), but with override 5 it's expired
    borderline = _make_old_file(log_dir, "border.log", days_old=10)
    prism_retention.execute_cleanup(tmp_path, dry_run=False)
    assert not borderline.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_prism_retention.py -v`
Expected: FAIL — `ModuleNotFoundError: prism_retention`.

- [ ] **Step 3: Implement prism_retention.py**

Create `apps/scripts/prism_retention.py`:

```python
"""Data retention cleanup for Prism runtime artifacts.

Deletes aged files under the data tree to prevent unbounded growth. The
data/ directories are gitignored, so growth is otherwise invisible.

Design:
  - Two phases: ``plan_cleanup`` (computes what would be deleted, no side
    effects) and ``execute_cleanup`` (performs the deletion). A dry-run
    runs only the plan.
  - Strict whitelist: prism.db, scheduler_state.json, scheduler_events.jsonl,
    config/, schemas/, quant/labels/ are NEVER touched regardless of age.
  - Each cleanup target has its own retention window, overridable via env.

Usage:
    python3 apps/scripts/prism_retention.py --dry-run
    python3 apps/scripts/prism_retention.py
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT_DEFAULT = REPO_ROOT / "data"

# Files/dirs that must never be deleted regardless of age.
PROTECTED_NAMES = {
    "prism.db",
    "prism.db-wal",
    "prism.db-shm",
    "scheduler_state.json",
    "scheduler_events.jsonl",
}
PROTECTED_DIRS = {"config", "schemas", "quant"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


@dataclass
class CleanupEntry:
    root: Path
    pattern: str
    retention_days: int
    files: list[Path] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{self.root.relative_to(REPO_ROOT) if self.root.is_relative_to(REPO_ROOT) else self.root} ({self.pattern}, {self.retention_days}d)"


def _is_protected(path: Path) -> bool:
    if path.name in PROTECTED_NAMES:
        return True
    # Walk up: if any parent dir (within data/) is a protected dir, protect it
    try:
        rel = path.relative_to(DATA_ROOT_DEFAULT)
    except ValueError:
        return False
    parts = rel.parts
    return bool(parts) and parts[0] in PROTECTED_DIRS


def _build_entries(data_root: Path) -> list[CleanupEntry]:
    run_days = _env_int("PRISM_RETENTION_RUN_DAYS", 30)
    log_days = _env_int("PRISM_RETENTION_LOG_DAYS", 14)
    corrupt_days = _env_int("PRISM_RETENTION_CORRUPT_DAYS", 30)
    dataset_days = _env_int("PRISM_RETENTION_DATASET_DAYS", 90)
    harvest_days = _env_int("PRISM_RETENTION_HARVEST_DAYS", 30)

    entries = [
        CleanupEntry(data_root / "scheduled_runs" / "logs", "*", run_days),
        CleanupEntry(data_root / "scheduled_runs" / "runs", "*", run_days),
        CleanupEntry(data_root / "runtime", "*.log", log_days),
        CleanupEntry(data_root / "runtime", "*.corrupt-*", corrupt_days),
        CleanupEntry(data_root / "prism_data" / "datasets", "*", dataset_days),
        CleanupEntry(data_root / "prism_data", "tinyshare_*_harvest", harvest_days),
    ]
    return [e for e in entries if e.root.exists()]


def _collect_expired(entry: CleanupEntry, now: datetime) -> list[Path]:
    cutoff = now - timedelta(days=entry.retention_days)
    expired: list[Path] = []
    if entry.pattern.startswith("tinyshare_"):
        # Match run-dirs by name prefix; age by mtime of the dir
        for child in entry.root.iterdir():
            if child.is_dir() and child.name.startswith(entry.pattern.replace("*", "")):
                if _is_protected(child):
                    continue
                try:
                    mtime = datetime.fromtimestamp(child.stat().st_mtime)
                except OSError:
                    continue
                if mtime < cutoff:
                    expired.append(child)
        return expired
    for path in entry.root.glob(entry.pattern):
        if path.is_dir():
            continue
        if _is_protected(path):
            continue
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
        except OSError:
            continue
        if mtime < cutoff:
            expired.append(path)
    return expired


def plan_cleanup(data_root: Path = DATA_ROOT_DEFAULT, *, dry_run: bool = True) -> "CleanupPlan":
    now = datetime.now()
    entries = _build_entries(data_root)
    total_files = 0
    total_bytes = 0
    for entry in entries:
        entry.files = _collect_expired(entry, now)
        for f in entry.files:
            try:
                total_bytes += f.stat().st_size
            except OSError:
                pass
            total_files += 1
    return CleanupPlan(entries=entries, dry_run=dry_run, total_files=total_files, total_bytes=total_bytes)


@dataclass
class CleanupPlan:
    entries: list[CleanupEntry]
    dry_run: bool
    total_files: int
    total_bytes: int

    def summary(self) -> str:
        mode = "DRY-RUN" if self.dry_run else "EXECUTE"
        lines = [f"[{mode}] {self.total_files} files / {self.total_bytes / 1e6:.1f} MB"]
        for entry in self.entries:
            if entry.files:
                lines.append(f"  {entry.label}: {len(entry.files)} files")
        return "\n".join(lines)


def execute_cleanup(data_root: Path = DATA_ROOT_DEFAULT, *, dry_run: bool = True) -> list[Path]:
    plan = plan_cleanup(data_root, dry_run=dry_run)
    deleted: list[Path] = []
    if dry_run:
        return deleted
    for entry in plan.entries:
        for path in entry.files:
            try:
                if path.is_dir():
                    # Remove dir tree (harvest run-dirs)
                    import shutil
                    shutil.rmtree(path)
                else:
                    path.unlink()
                deleted.append(path)
            except OSError:
                pass
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser(description="Prism data retention cleanup")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be deleted without deleting")
    parser.add_argument("--data-root", default=str(DATA_ROOT_DEFAULT))
    args = parser.parse_args()

    data_root = Path(args.data_root)
    global DATA_ROOT_DEFAULT
    DATA_ROOT_DEFAULT = data_root  # so _is_protected uses the right root

    if args.dry_run:
        plan = plan_cleanup(data_root, dry_run=True)
        print(plan.summary())
        for entry in plan.entries:
            for f in entry.files[:20]:
                print(f"    {f}")
            if len(entry.files) > 20:
                print(f"    ... and {len(entry.files) - 20} more")
        return 0

    deleted = execute_cleanup(data_root, dry_run=False)
    print(f"Deleted {len(deleted)} files/dirs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_prism_retention.py -v`
Expected: PASS — all 6 tests green.

- [ ] **Step 5: Register retention cron job in refresh_policy**

In `apps/control-panel/refresh_policy.py`, add a new `CronJobPolicy` to the `CRON_POLICIES` tuple (after the last existing entry, before the closing paren). Place it near the other postclose jobs:

```python
    CronJobPolicy(
        task_name="retention_cleanup",
        name="数据保留期清理",
        cron_expr="0 18 * * 1-5",
        command=("python3", "apps/scripts/prism_retention.py"),
        delivery_default=False,
        catchup_enabled=False,
    ),
```

- [ ] **Step 6: Verify the policy is valid**

Run:
```bash
cd apps/control-panel && python3 -c "from refresh_policy import CRON_POLICIES; names=[p.task_name for p in CRON_POLICIES]; assert 'retention_cleanup' in names; print('ok', len(names), 'policies')"
```
Expected: `ok 16 policies` (15 existing + 1 new).

- [ ] **Step 7: Run full test suite**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 8: Run a real dry-run to sanity-check the deletion plan**

Run:
```bash
python3 apps/scripts/prism_retention.py --dry-run
```
Expected: a summary like `[DRY-RUN] N files / X.X MB` listing aged files under scheduled_runs/runtime/prism_data. **Review the list manually** — if any protected file appears, the whitelist is broken and must be fixed before enabling real deletion.

- [ ] **Step 9: Commit**

```bash
git add apps/scripts/prism_retention.py tests/test_prism_retention.py apps/control-panel/refresh_policy.py
git commit -m "feat(retention): data retention cleanup with dry-run + whitelist

Adds prism_retention.py: deletes aged scheduled_runs/runtime/prism_data
files per configurable retention windows (env-overridable). Strict
whitelist protects prism.db, scheduler state, config/, schemas/,
quant/labels/. Registered as an 18:00 cron job. data/ was 7.8G and
growing with zero prior cleanup."
```

---

## Task D: Exit-stock return tracker

**Files:**
- Create: `packages/screener/exit_return_tracker.py`
- Create: `tests/test_exit_return_tracker.py`
- Modify: `packages/screener/candidate_lifecycle.py:514-529` (exited branch)
- Modify: `apps/control-panel/refresh_policy.py` (register cron job)

**Pricing source:** `prism_data` gateway `fetch_kline(code, trade_date, period="daily", count=120)` returns daily bars; we read all closes for the window at once. This is the same gateway scan.py uses — no new HTTP code.

**Design note on `update_exits` signature:** `update_exits` takes a `pricing_provider(code) -> {trade_date: close}` that returns the **whole window** of daily closes for a code at once (a dict). This lets it settle a record in a single pass once the window's worth of trading days have elapsed, instead of needing one call per day. The provider wraps `fetch_kline` which already returns ~120 daily bars.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_exit_return_tracker.py`:

```python
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_ROOT = REPO_ROOT / "packages"
if str(PACKAGES_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGES_ROOT))

import exit_return_tracker as ert  # noqa: E402


def _write_store(tmp_path: Path, records: list[dict]) -> Path:
    store = tmp_path / "exit_tracking.jsonl"
    with store.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return store


def test_record_exit_appends_record(tmp_path: Path):
    store = tmp_path / "exit_tracking.jsonl"
    ert.record_exit(
        store=store,
        code="000032",
        name="深桑达A",
        exit_date="2026-06-18",
        exit_price=10.5,
        reason="题材走弱",
        theme="其他",
    )
    lines = store.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["code"] == "000032"
    assert rec["exit_price"] == 10.5
    assert rec["status"] == "open"
    assert rec["holding_window_days"] == 5


def test_record_exit_null_price_is_allowed(tmp_path: Path):
    store = tmp_path / "exit_tracking.jsonl"
    ert.record_exit(store, code="600141", name="兴发集团", exit_date="2026-06-18",
                    exit_price=None, reason="x", theme="y")
    rec = json.loads(store.read_text(encoding="utf-8").strip())
    assert rec["exit_price"] is None
    assert rec["status"] == "open"


def _fake_pricing(closes: dict[str, dict[str, float]]):
    """Return a pricing provider callable: (code) -> {trade_date: close}.

    update_exits asks the provider for the whole window of daily closes for a
    code at once, then settles the record using the closes that fall after
    the exit_date.
    """
    def provider(code: str):
        return closes.get(code, {})
    return provider


def test_update_marks_true_exit_when_drops(tmp_path: Path):
    store = _write_store(tmp_path, [{
        "code": "000032", "name": "深桑达A", "exit_date": "2026-06-18",
        "exit_price": 10.0, "reason": "x", "theme": "y", "status": "open",
        "holding_window_days": 5, "recorded_at": "2026-06-18T09:40:00",
        "daily_prices": [],
    }])
    # 5 trading days after the exit, prices drop
    closes = {"000032": {"2026-06-19": 9.8, "2026-06-22": 9.5, "2026-06-23": 9.2,
                         "2026-06-24": 9.0, "2026-06-25": 8.8}}
    result = ert.update_exits(store=store, pricing_provider=_fake_pricing(closes),
                              as_of_date="2026-06-25", window_days=5, misjudged_threshold=0.05)
    settled = result["settled"]
    assert len(settled) == 1
    assert settled[0]["outcome"] == "true_exit"
    assert settled[0]["net_return"] < 0


def test_update_marks_misjudged_when_rebounds(tmp_path: Path):
    store = _write_store(tmp_path, [{
        "code": "600141", "name": "兴发集团", "exit_date": "2026-06-18",
        "exit_price": 10.0, "reason": "x", "theme": "y", "status": "open",
        "holding_window_days": 5, "recorded_at": "2026-06-18T09:40:00",
        "daily_prices": [],
    }])
    # Prices rebound >5% above exit
    closes = {"600141": {"2026-06-19": 10.5, "2026-06-22": 10.8, "2026-06-23": 10.9,
                         "2026-06-24": 11.0, "2026-06-25": 11.2}}
    result = ert.update_exits(store=store, pricing_provider=_fake_pricing(closes),
                              as_of_date="2026-06-25", window_days=5, misjudged_threshold=0.05)
    settled = result["settled"]
    assert settled[0]["outcome"] == "misjudged"
    assert settled[0]["net_return"] > 0.05


def test_update_marks_inconclusive_on_missing_prices(tmp_path: Path):
    store = _write_store(tmp_path, [{
        "code": "000100", "name": "TCL科技", "exit_date": "2026-06-18",
        "exit_price": 5.0, "reason": "x", "theme": "y", "status": "open",
        "holding_window_days": 5, "recorded_at": "2026-06-18T09:40:00",
        "daily_prices": [],
    }])
    # No prices available at all. as_of_date is > window_days*2 (=10) past the
    # exit (Jun 18 -> Jul 2 = 14 days), so the record settles as inconclusive
    # rather than lingering open forever.
    result = ert.update_exits(store=store, pricing_provider=_fake_pricing({}),
                              as_of_date="2026-07-02", window_days=5, misjudged_threshold=0.05)
    settled = result["settled"]
    assert settled[0]["outcome"] == "inconclusive"


def test_update_keeps_open_when_window_not_full(tmp_path: Path):
    """If fewer than window_days of post-exit closes are available, record stays open."""
    store = _write_store(tmp_path, [{
        "code": "000032", "name": "深桑达A", "exit_date": "2026-06-18",
        "exit_price": 10.0, "reason": "x", "theme": "y", "status": "open",
        "holding_window_days": 5, "recorded_at": "2026-06-18T09:40:00",
        "daily_prices": [],
    }])
    # Only 2 post-exit closes available (as_of too early)
    closes = {"000032": {"2026-06-19": 9.8, "2026-06-22": 9.5}}
    result = ert.update_exits(store=store, pricing_provider=_fake_pricing(closes),
                              as_of_date="2026-06-22", window_days=5, misjudged_threshold=0.05)
    assert result["settled"] == []
    assert result["advanced"] == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_exit_return_tracker.py -v`
Expected: FAIL — `ModuleNotFoundError: exit_return_tracker`.

- [ ] **Step 3: Implement exit_return_tracker.py**

Create `packages/screener/exit_return_tracker.py`:

```python
"""Exit-stock return tracker.

When a candidate exits the shortlist, ``record_exit`` logs it. Each trading
day, ``update_exits`` advances open records: it asks the pricing provider
for the full window of daily closes for a code, keeps the closes that fall
strictly after the exit_date, and once at least ``window_days`` of them are
available, classifies the outcome:

  - ``true_exit``    : net return <= misjudged_threshold (continued down or flat)
  - ``misjudged``    : net return > misjudged_threshold (e.g. rebounded >5%)
  - ``inconclusive`` : exit_price missing, or no post-exit prices obtainable
                       within ``window_days * 2`` calendar days past the exit

``pricing_provider(code) -> {trade_date_str: close}`` returns the whole
window at once so a record settles in a single pass once the window fills.
If the provider returns no usable closes and ``as_of_date`` is more than
``window_days * 2`` past ``exit_date``, the record settles as
``inconclusive`` so a permanently-unpriceable exit does not linger open
forever. The production caller wraps ``prism_data`` gateway ``fetch_kline``.

Storage: append-only JSONL at ``data/runtime/exit_tracking.jsonl``.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

DEFAULT_STORE = Path(__file__).resolve().parents[2] / "data" / "runtime" / "exit_tracking.jsonl"
DEFAULT_WINDOW_DAYS = 5
DEFAULT_MISJUDGED_THRESHOLD = 0.05


def record_exit(
    *,
    store: Path = DEFAULT_STORE,
    code: str,
    name: str,
    exit_date: str,
    exit_price: Optional[float],
    reason: str,
    theme: str,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> None:
    """Append a new exit record. Called from candidate_lifecycle exited branch."""
    store.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "code": code,
        "name": name,
        "exit_date": exit_date,
        "exit_price": exit_price,
        "reason": reason,
        "theme": theme,
        "status": "open",
        "holding_window_days": window_days,
        "recorded_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "daily_prices": [],
        "net_return": None,
        "outcome": None,
    }
    with store.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _load_records(store: Path) -> list[dict]:
    if not store.exists():
        return []
    records = []
    with store.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def _save_records(store: Path, records: list[dict]) -> None:
    """Rewrite the store atomically with all records."""
    tmp = store.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(store)


def _settle(record: dict, misjudged_threshold: float) -> dict:
    """Classify a record based on its accumulated daily_prices."""
    prices = [p for p in record.get("daily_prices", []) if p.get("close") is not None]
    exit_price = record.get("exit_price")
    record["status"] = "settled"
    if not prices or exit_price is None or exit_price <= 0:
        record["outcome"] = "inconclusive"
        return record
    last_close = prices[-1]["close"]
    net_return = last_close / exit_price - 1
    record["net_return"] = round(net_return, 4)
    record["outcome"] = "misjudged" if net_return > misjudged_threshold else "true_exit"
    return record


def update_exits(
    *,
    store: Path = DEFAULT_STORE,
    pricing_provider: Callable[[str], dict],
    as_of_date: str,
    window_days: int = DEFAULT_WINDOW_DAYS,
    misjudged_threshold: float = DEFAULT_MISJUDGED_THRESHOLD,
) -> dict:
    """Advance all open exit records up to ``as_of_date``.

    ``pricing_provider(code)`` must return a ``{trade_date_str: close}`` dict
    covering the post-exit window for that code (may include dates past
    ``as_of_date``; those are ignored).

    A record settles when at least ``window_days`` closes strictly after its
    ``exit_date`` are available and on/before ``as_of_date``. Returns
    ``{"settled": [...], "advanced": int}`` where ``advanced`` counts the
    number of post-exit closes newly recorded this pass.
    """
    records = _load_records(store)
    settled: list[dict] = []
    advanced = 0
    changed = False
    for record in records:
        if record.get("status") != "open":
            continue
        exit_date = record.get("exit_date", "")
        code = record["code"]
        closes = pricing_provider(code) or {}
        # Keep closes strictly after exit_date and on/before as_of_date,
        # sorted ascending by date, capped at window_days.
        post_exit = sorted(
            (d for d in closes.items() if d[0] > exit_date and d[0] <= as_of_date),
            key=lambda kv: kv[0],
        )[:window_days]
        if post_exit:
            record["daily_prices"] = [{"date": d, "close": c} for d, c in post_exit]
            advanced += len(post_exit)
            changed = True
        if len(record["daily_prices"]) >= window_days:
            _settle(record, misjudged_threshold)
            settled.append(record)
        else:
            # If we still cannot get prices and enough wall-clock time has
            # passed (window_days * 2), settle as inconclusive so a
            # permanently-unpriceable exit does not linger open forever.
            from datetime import date as _date
            try:
                exit_d = _date.fromisoformat(exit_date)
                as_of_d = _date.fromisoformat(as_of_date)
                stale = (as_of_d - exit_d).days > window_days * 2
            except ValueError:
                stale = False
            if stale and not record["daily_prices"]:
                _settle(record, misjudged_threshold)
                settled.append(record)
                changed = True
    if changed:
        _save_records(store, records)
    return {"settled": settled, "advanced": advanced}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_exit_return_tracker.py -v`
Expected: PASS — all 5 tests green.

- [ ] **Step 5: Wire record_exit into candidate_lifecycle exited branch**

In `packages/screener/candidate_lifecycle.py`, add the import near the top (after the existing imports around line 12):

```python
from exit_return_tracker import record_exit
```

Then in the exited loop (around line 514-529), after the `exited.append({...})` block, add a best-effort `record_exit` call. Wrap it so a tracker failure never breaks lifecycle generation (defensive — the tracker is an add-on):

```python
        try:
            record_exit(
                code=code,
                name=s["name"],
                exit_date=str(s.get("timestamp", "") or "")[:10],
                exit_price=s.get("exit_price") or s.get("close") or s.get("price"),
                reason=s.get("invalidation") or s.get("main_risk") or "已退出",
                theme=s.get("theme", ""),
            )
        except Exception:
            # Exit tracking is best-effort; never let it break lifecycle output.
            pass
```

Place this immediately after the `exited.append({...})` call inside the `for code in sorted(previous_codes - current_codes):` loop.

- [ ] **Step 6: Create the scheduled update job**

Create `apps/scripts/run_exit_return_update.py`:

```python
#!/usr/bin/env python3
"""Scheduled entry point: advance open exit-return records by one trading day.

Wraps exit_return_tracker.update_exits with the prism_data gateway as the
pricing provider (fetch_kline daily bars).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for p in (str(REPO_ROOT / "packages"), str(REPO_ROOT / "apps" / "control-panel")):
    if p not in sys.path:
        sys.path.insert(0, p)

from trading_calendar import most_recent_trading_day  # noqa: E402
from exit_return_tracker import update_exits, DEFAULT_STORE  # noqa: E402


def _gateway_pricing(trade_date: str):
    """Return a pricing_provider(code) -> {trade_date: close} backed by fetch_kline."""
    try:
        from prism_data.gateway import default_gateway  # type: ignore
    except Exception:
        # Gateway unavailable — provider returns empty dict (inconclusive).
        return lambda code: {}
    gateway = default_gateway()

    def provider(code: str) -> dict:
        try:
            result = gateway.fetch_kline(code, trade_date=trade_date, period="daily", count=20)
            out: dict[str, float] = {}
            for bar in (result.data or []):
                d = str(bar.get("trade_date", ""))[:10]
                c = bar.get("close")
                if d and c is not None:
                    out[d] = c
            return out
        except Exception:
            return {}

    return provider


def main() -> int:
    trade_date = str(most_recent_trading_day())
    provider = _gateway_pricing(trade_date)
    result = update_exits(store=DEFAULT_STORE, pricing_provider=provider, as_of_date=trade_date)
    print(f"exit_return_update as_of={trade_date} advanced={result['advanced']} settled={len(result['settled'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 7: Register the exit_return_update cron job**

In `apps/control-panel/refresh_policy.py`, add to `CRON_POLICIES` (near the postclose jobs, after the retention_cleanup entry added in Task B):

```python
    CronJobPolicy(
        task_name="exit_return_update",
        name="退出股收益跟踪",
        cron_expr="30 15 * * 1-5",
        command=("python3", "apps/scripts/run_exit_return_update.py"),
        delivery_default=False,
        catchup_enabled=True,
        catchup_until="17:00",
    ),
```

- [ ] **Step 8: Verify policies and run full suite**

```bash
cd apps/control-panel && python3 -c "from refresh_policy import CRON_POLICIES; names=[p.task_name for p in CRON_POLICIES]; assert 'exit_return_update' in names and 'retention_cleanup' in names; print('ok', len(names), 'policies')" && cd ../..
```
Expected: `ok 17 policies`.

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add packages/screener/exit_return_tracker.py tests/test_exit_return_tracker.py packages/screener/candidate_lifecycle.py apps/scripts/run_exit_return_update.py apps/control-panel/refresh_policy.py
git commit -m "feat(tracker): exit-stock return tracking (solves 'only tracks one day')

record_exit logs each exited candidate; update_exits advances open
records daily via the prism_data gateway (fetch_kline daily bars) and
classifies outcome as true_exit / misjudged / inconclusive once the
5-day window fills. Wired into candidate_lifecycle exited branch
(best-effort, never blocks lifecycle output) and a 15:30 cron job.

Directly addresses the root cause flagged in
docs/discovery-page-design-review: exited samples only recorded
last_seen with no follow-through, so one-day-pulse / fake-breakout
quality could never be validated."
```

---

## Final Verification (after all tasks)

- [ ] **Step 1: Full test suite**

```bash
pytest -q
```
Expected: all pass.

- [ ] **Step 2: Privacy scrub**

```bash
python3 scripts/scrub-secrets.py
```
Expected: clean.

- [ ] **Step 3: Frontend build**

```bash
cd apps/web && ./node_modules/.bin/next build && cd ../..
```
Expected: build succeeds.

- [ ] **Step 4: Retention dry-run review**

```bash
python3 apps/scripts/prism_retention.py --dry-run
```
Expected: review the deletion list; confirm no protected file appears.

- [ ] **Step 5: Final commit (if any verification surfaced fixes)**

```bash
git log --oneline -8
```
Confirm the 6 task commits are present on the branch.
