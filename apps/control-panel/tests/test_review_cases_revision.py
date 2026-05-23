"""Tests for the content-based revision on the review case store.

The revision is the cache-invalidation key for downstream consumers
(notably ``dashboard_data.build_review_learning_memory_index``). It MUST
be:

* stable across two calls when nothing changed,
* changed when content changes,
* identical for identical content (so two stores written separately
  with the same data produce the same revision),
* derivable cheaply from the on-disk file (read_review_cases_revision)
  without going through the full ``_case_labelled`` projection.

These properties let caches drop the mtime dependency that was fragile
on same-second writes and on ``touch``-only updates.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


CONTROL_PANEL_ROOT = Path(__file__).resolve().parents[1]
if str(CONTROL_PANEL_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROL_PANEL_ROOT))


class _ReviewCasesRevisionBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ledger_root = Path(self._tmp.name) / "decision_ledger"
        self.account_book_path = Path(self._tmp.name) / "account_book.json"
        self.db_path = Path(self._tmp.name) / "prism.db"

        self._env = mock.patch.dict(
            os.environ,
            {
                "PRISM_DECISION_LEDGER_PATH": str(self.ledger_root),
                "PRISM_ACCOUNT_BOOK_PATH": str(self.account_book_path),
                "PRISM_REPO_ROOT": str(self._tmp.name),
                "PRISM_DB_PATH": str(self.db_path),
            },
        )
        self._env.start()
        self.addCleanup(self._env.stop)

        for mod_name in (
            "decision_ledger",
            "decision_ledger_providers",
            "dashboard_data",
            "control_panel.dashboard_data",
        ):
            sys.modules.pop(mod_name, None)

        import decision_ledger  # type: ignore

        self.ledger = decision_ledger
        self.cases_path = decision_ledger._review_cases_path()
        self.cases_path.parent.mkdir(parents=True, exist_ok=True)

    def _write_cases(self, cases: list[dict]) -> None:
        self.cases_path.write_text(
            json.dumps(cases, ensure_ascii=False), encoding="utf-8"
        )


class RevisionFromListReviewCasesTests(_ReviewCasesRevisionBase):
    def test_empty_store_returns_known_revision(self) -> None:
        payload = self.ledger.list_review_cases()
        self.assertEqual(payload["count"], 0)
        self.assertEqual(payload["revision"], "sha256:empty")

    def test_revision_is_stable_across_two_calls(self) -> None:
        self._write_cases([
            {
                "review_case_id": "review_case:abc",
                "decision_id": "dec_001",
                "primary_cause": "too_strict",
                "reviewed_at": "2026-05-23T10:00:00",
            },
        ])
        first = self.ledger.list_review_cases()["revision"]
        second = self.ledger.list_review_cases()["revision"]
        self.assertEqual(first, second)
        self.assertNotEqual(first, "sha256:empty")
        self.assertTrue(first.startswith("sha256:"))

    def test_revision_changes_when_a_case_is_added(self) -> None:
        self._write_cases([
            {
                "review_case_id": "review_case:abc",
                "decision_id": "dec_001",
                "primary_cause": "too_strict",
                "reviewed_at": "2026-05-23T10:00:00",
            },
        ])
        before = self.ledger.list_review_cases()["revision"]

        self._write_cases([
            {
                "review_case_id": "review_case:abc",
                "decision_id": "dec_001",
                "primary_cause": "too_strict",
                "reviewed_at": "2026-05-23T10:00:00",
            },
            {
                "review_case_id": "review_case:def",
                "decision_id": "dec_002",
                "primary_cause": "data_lag",
                "reviewed_at": "2026-05-23T11:00:00",
            },
        ])
        after = self.ledger.list_review_cases()["revision"]
        self.assertNotEqual(before, after, "adding a case must change the revision")

    def test_revision_is_content_based_not_order_based(self) -> None:
        """Two cases written in different order produce the same revision.

        Internally the canonical encoding sorts keys, so dict-ordering
        in the input shouldn't matter.
        """
        case_a = {
            "decision_id": "dec_001",
            "review_case_id": "review_case:abc",
            "primary_cause": "too_strict",
            "reviewed_at": "2026-05-23T10:00:00",
        }
        case_a_reordered = {
            "reviewed_at": "2026-05-23T10:00:00",
            "primary_cause": "too_strict",
            "review_case_id": "review_case:abc",
            "decision_id": "dec_001",
        }
        # Same content, different key order in the on-disk file.
        self._write_cases([case_a])
        first = self.ledger.list_review_cases()["revision"]
        self._write_cases([case_a_reordered])
        second = self.ledger.list_review_cases()["revision"]
        self.assertEqual(first, second)


class ReadReviewCasesRevisionTests(_ReviewCasesRevisionBase):
    def test_returns_empty_sentinel_when_file_missing(self) -> None:
        self.assertFalse(self.cases_path.exists())
        self.assertEqual(
            self.ledger.read_review_cases_revision(),
            "sha256:empty",
        )

    def test_changes_when_content_changes(self) -> None:
        self._write_cases([{"review_case_id": "x", "decision_id": "d1"}])
        before = self.ledger.read_review_cases_revision()
        self._write_cases([{"review_case_id": "y", "decision_id": "d2"}])
        after = self.ledger.read_review_cases_revision()
        self.assertNotEqual(before, after)
        self.assertTrue(before.startswith("sha256:"))
        self.assertTrue(after.startswith("sha256:"))


class DashboardCacheUsesRevisionTests(_ReviewCasesRevisionBase):
    """Dashboard memory-index cache must invalidate on content, not mtime."""

    def _import_dashboard(self):
        import dashboard_data  # type: ignore

        return dashboard_data

    def test_cache_hits_when_content_unchanged(self) -> None:
        self._write_cases([
            {"review_case_id": "r1", "decision_id": "d1", "primary_cause": "too_strict"},
        ])
        dashboard = self._import_dashboard()
        first = dashboard.build_review_learning_memory_index()
        # Second call hits cache — make sure list_review_cases is NOT
        # re-called when revision is unchanged.
        with mock.patch.object(self.ledger, "list_review_cases") as spy:
            second = dashboard.build_review_learning_memory_index()
            spy.assert_not_called()
        self.assertEqual(first, second)

    def test_cache_invalidates_when_content_changes_within_same_second(self) -> None:
        """Same-second writes used to fool the mtime cache; revision must catch them."""
        self._write_cases([
            {"review_case_id": "r1", "decision_id": "d1", "primary_cause": "too_strict"},
        ])
        dashboard = self._import_dashboard()
        first = dashboard.build_review_learning_memory_index()
        first_cases = list(first.get("cases") or [])

        # Pin mtime to the same nanosecond before AND after the second write,
        # so any mtime-based cache would still hit. The revision check must
        # nonetheless catch the content change.
        before_stat = self.cases_path.stat()
        self._write_cases([
            {"review_case_id": "r1", "decision_id": "d1", "primary_cause": "too_strict"},
            {"review_case_id": "r2", "decision_id": "d2", "primary_cause": "data_lag"},
        ])
        os.utime(self.cases_path, ns=(before_stat.st_atime_ns, before_stat.st_mtime_ns))

        second = dashboard.build_review_learning_memory_index()
        self.assertNotEqual(
            len(first_cases),
            len(second.get("cases") or []),
            "cache must invalidate on content change even when mtime is identical",
        )
        # Sanity-check that we really did keep mtime identical (otherwise the
        # test does not actually exercise the mtime-resistant property).
        after_stat = self.cases_path.stat()
        self.assertEqual(before_stat.st_mtime_ns, after_stat.st_mtime_ns)


if __name__ == "__main__":
    unittest.main()
