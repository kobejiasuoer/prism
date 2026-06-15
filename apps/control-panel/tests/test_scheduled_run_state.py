from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_ROOT = REPO_ROOT / "apps" / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import scheduled_run_state  # noqa: E402


def write_latest(root: Path, task_name: str, payload: dict) -> None:
    path = root / "latest" / f"{task_name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class ScheduledRunStateTests(unittest.TestCase):
    def test_stale_running_payload_is_orphaned_not_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_latest(
                root,
                "midday_refresh",
                {
                    "run_id": "midday_refresh_2026-05-15_13-10-00",
                    "task_name": "midday_refresh",
                    "status": "running",
                    "started_at": "2026-05-15 13:10:00",
                    "finished_at": None,
                    "pid": 1925,
                    "calendar": {"trade_date": "2026-05-15"},
                },
            )

            with mock.patch.object(scheduled_run_state, "pid_alive", return_value=False):
                state = scheduled_run_state.run_state_for_task(
                    "midday_refresh",
                    now=datetime(2026, 5, 26, 10, 0, 0),
                    run_root=root,
                )

        self.assertFalse(state["running"])
        self.assertTrue(state["orphaned"])
        self.assertTrue(state["stale_latest"])
        self.assertFalse(state["failed_today"])

    def test_same_day_dead_running_payload_is_retryable_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_latest(
                root,
                "morning_warmup",
                {
                    "run_id": "morning_warmup_2026-05-26_09-25-00",
                    "task_name": "morning_warmup",
                    "status": "running",
                    "started_at": "2026-05-26 09:25:00",
                    "finished_at": None,
                    "pid": 123456,
                    "calendar": {"trade_date": "2026-05-26"},
                },
            )

            with mock.patch.object(scheduled_run_state, "pid_alive", return_value=False):
                state = scheduled_run_state.run_state_for_task(
                    "morning_warmup",
                    now=datetime(2026, 5, 26, 10, 0, 0),
                    run_root=root,
                )

        self.assertFalse(state["running"])
        self.assertTrue(state["orphaned"])
        self.assertTrue(state["failed_today"])


if __name__ == "__main__":
    unittest.main()
