"""Tests for the Decision Ledger auto-capture post-hook.

The scheduled-job runner invokes ``run_decision_ledger_capture_hook``
after the canonical task command finishes successfully.  These tests
isolate the hook from the subprocess plumbing so we can assert:

* The hook captures Today's action queue when called.
* The hook is idempotent across re-runs.
* The hook converts capture exceptions into a failed status payload
  rather than re-raising (the main task must not be punished for a
  metadata failure).
* ``DECISION_LEDGER_CAPTURE_AFTER_TASKS`` lists the tasks the
  technical plan requires (midday_confirmation + postclose_command_brief).
* The hook persists a ``capture_latest.json`` status file under the
  ledger root so the Settings page can surface "last capture worked".

The end-to-end "scheduled_job actually executes the hook" path is
covered by an integration smoke that mocks ``build_today_view`` so the
real Today view fixtures do not have to be wired in here.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[3]
CONTROL_PANEL_ROOT = REPO_ROOT / "apps" / "control-panel"
SCRIPTS_ROOT = REPO_ROOT / "apps" / "scripts"
PACKAGES_ROOT = REPO_ROOT / "packages"
for import_path in (str(CONTROL_PANEL_ROOT), str(SCRIPTS_ROOT), str(PACKAGES_ROOT)):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)


def _make_action_item(*, key: str, status: str, detail: str, title: str = "示例 600690") -> dict:
    return {
        "key": key,
        "title": title,
        "source": "自选股链路",
        "status": status,
        "tone": "watch",
        "detail": detail,
        "foot": "",
        "metrics": [],
        "url": None,
        "group_key": "do-now",
        "group_title": "Do Now",
        "group_index": 1,
        "lane_key": key.split(":", 1)[0],
        "freshness": {"value": "", "label": "-"},
        "confidence": {"status": "ok", "label": "可信"},
        "decision": {"status": "pending", "label": "待处理"},
        "display_state": {"value": "pending", "updated_at_raw": ""},
        "trust": {"trusted": True, "blockers": [], "warnings": []},
        "actionable": True,
    }


def _today_view(*, trade_date: str = "2026-05-15", items: list[dict] | None = None) -> dict:
    return {
        "trade_date": trade_date,
        "expected_trade_date": trade_date,
        "data_trade_date": trade_date,
        "readiness": {"readiness_mode": "live_ready", "ready": True},
        "action_queue": {
            "items": items or [
                _make_action_item(
                    key="watchlist:600690",
                    status="继续持有",
                    detail="形态稳健",
                )
            ],
            "stale_items": [],
        },
    }


class CaptureAfterTaskListTests(unittest.TestCase):
    """Make sure the technical plan's trigger list matches the runtime."""

    def test_capture_after_tasks_is_a_tuple_of_strings(self) -> None:
        from refresh_policy import DECISION_LEDGER_CAPTURE_AFTER_TASKS  # type: ignore

        self.assertIsInstance(DECISION_LEDGER_CAPTURE_AFTER_TASKS, tuple)
        for name in DECISION_LEDGER_CAPTURE_AFTER_TASKS:
            self.assertIsInstance(name, str)

    def test_capture_after_tasks_includes_required_workflows(self) -> None:
        from refresh_policy import DECISION_LEDGER_CAPTURE_AFTER_TASKS  # type: ignore

        # The technical plan explicitly names these two as the daily
        # workflows whose successful completion should trigger capture.
        self.assertIn("midday_confirmation", DECISION_LEDGER_CAPTURE_AFTER_TASKS)
        self.assertIn("postclose_command_brief", DECISION_LEDGER_CAPTURE_AFTER_TASKS)


class CaptureHookTests(unittest.TestCase):
    """Direct tests of the hook function, with build_today_view mocked."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ledger_root = Path(self._tmp.name) / "decision_ledger"

        self._env = mock.patch.dict(
            os.environ,
            {"PRISM_DECISION_LEDGER_PATH": str(self.ledger_root)},
        )
        self._env.start()
        self.addCleanup(self._env.stop)

        # Reload the ledger module so it picks up the env override.
        for name in ("decision_ledger", "decision_ledger_providers", "prism_scheduled_job"):
            sys.modules.pop(name, None)

        import decision_ledger  # type: ignore
        import prism_scheduled_job  # type: ignore

        self.ledger = decision_ledger
        self.job = prism_scheduled_job

    def _patch_today_view(self, today_view: dict):
        """Patch ``build_today_view`` for the duration of one hook call.

        The hook imports the symbol lazily via ``dashboard_data`` (the
        loose top-level module on ``apps/control-panel/`` sys.path).
        We patch ``dashboard_data.build_today_view`` so both the test
        environment and the production hook see the same surface.
        """

        import dashboard_data  # type: ignore  # noqa: F401

        return mock.patch(
            "dashboard_data.build_today_view",
            return_value=today_view,
        )

    def test_hook_returns_success_when_capture_works(self) -> None:
        view = _today_view()
        with self._patch_today_view(view):
            payload = self.job.run_decision_ledger_capture_hook("midday_confirmation")
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["task_name"], "midday_confirmation")
        self.assertEqual(payload["trade_date"], "2026-05-15")
        self.assertEqual(payload["captured"], 1)
        self.assertEqual(payload["already_present"], 0)
        self.assertEqual(len(payload["decision_ids"]), 1)
        self.assertIsNone(payload["error"])

    def test_hook_is_idempotent_on_repeat_invocations(self) -> None:
        view = _today_view()
        with self._patch_today_view(view):
            first = self.job.run_decision_ledger_capture_hook("midday_confirmation")
            second = self.job.run_decision_ledger_capture_hook("midday_confirmation")
        self.assertEqual(first["captured"], 1)
        self.assertEqual(first["already_present"], 0)
        self.assertEqual(second["captured"], 0)
        self.assertEqual(second["already_present"], 1)

    def test_hook_writes_status_file_after_success(self) -> None:
        view = _today_view()
        with self._patch_today_view(view):
            self.job.run_decision_ledger_capture_hook("postclose_command_brief")

        status_path = self.ledger_root / "status" / "capture_latest.json"
        self.assertTrue(status_path.exists())
        raw = json.loads(status_path.read_text(encoding="utf-8"))
        self.assertEqual(raw["status"], "success")
        self.assertEqual(raw["task_name"], "postclose_command_brief")
        self.assertIn("recorded_at", raw)
        self.assertEqual(raw["captured"], 1)

    def test_hook_records_failed_status_when_capture_raises(self) -> None:
        # Force capture_today_action_queue to raise -- the hook must
        # convert that into a failed payload, not propagate.
        with mock.patch(
            "decision_ledger.capture_today_action_queue",
            side_effect=RuntimeError("boom"),
        ), self._patch_today_view(_today_view()):
            payload = self.job.run_decision_ledger_capture_hook("midday_confirmation")

        self.assertEqual(payload["status"], "failed")
        self.assertIn("boom", payload["error"])

        status_path = self.ledger_root / "status" / "capture_latest.json"
        self.assertTrue(status_path.exists())
        raw = json.loads(status_path.read_text(encoding="utf-8"))
        self.assertEqual(raw["status"], "failed")
        self.assertIn("boom", raw["error"])

    def test_hook_status_kind_is_whitelisted(self) -> None:
        # Sanity check: the status writer should accept "capture".
        # If someone renames the kind, this is the first thing to break.
        self.ledger.write_status("capture", {"status": "success", "task_name": "x"})
        raw = self.ledger.load_status("capture")
        self.assertIsNotNone(raw)
        self.assertEqual(raw["task_name"], "x")


if __name__ == "__main__":
    unittest.main()
