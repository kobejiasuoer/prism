from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_ROOT = REPO_ROOT / "apps" / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import prism_canonical  # noqa: E402


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class PrismCanonicalTradeDateGuardTests(unittest.TestCase):
    def test_legacy_screener_current_files_do_not_satisfy_today_filter(self) -> None:
        original_dirs = prism_canonical.SCREENER_DATA_DIRS
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            current = root / "packages-data"
            legacy = root / "stock-screener-data"
            write_json(legacy / "ai_screening_result.json", {"timestamp": "2026-04-21 13:46:59"})
            write_json(legacy / "midday_verification_result.json", {"timestamp": "2026-04-21 19:27:58"})

            prism_canonical.SCREENER_DATA_DIRS = (current, legacy)
            try:
                self.assertIsNone(prism_canonical.resolve_screening_batch_path(trade_date="2026-05-14"))
                self.assertIsNone(prism_canonical.resolve_confirmation_path(trade_date="2026-05-14"))

                write_json(current / "ai_screening_result.json", {"timestamp": "2026-05-14 10:30:01"})
                write_json(current / "midday_verification_result.json", {"timestamp": "2026-05-14 13:45:01"})

                self.assertEqual(prism_canonical.resolve_screening_batch_path(trade_date="2026-05-14"), current / "ai_screening_result.json")
                self.assertEqual(prism_canonical.resolve_confirmation_path(trade_date="2026-05-14"), current / "midday_verification_result.json")
            finally:
                prism_canonical.SCREENER_DATA_DIRS = original_dirs

    def test_lifecycle_resolver_prefers_current_packages_data(self) -> None:
        original_dirs = prism_canonical.SCREENER_DATA_DIRS
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            current = root / "packages-data"
            legacy = root / "stock-screener-data"
            write_json(
                legacy / "lifecycle_2026-04-13_16-13.json",
                {"metadata": {"generated_at": "2026-04-13 16:13:00"}, "summary": {"entered_count": 1}},
            )
            write_json(
                current / "lifecycle_2026-05-19_12-20.json",
                {"metadata": {"generated_at": "2026-05-19 12:20:00"}, "summary": {"entered_count": 0}},
            )

            prism_canonical.SCREENER_DATA_DIRS = (current, legacy)
            try:
                resolved = prism_canonical.resolve_lifecycle_path()
                self.assertEqual(resolved, current / "lifecycle_2026-05-19_12-20.json")
            finally:
                prism_canonical.SCREENER_DATA_DIRS = original_dirs

    def test_lifecycle_activity_fallback_can_use_legacy_when_current_is_empty(self) -> None:
        original_dirs = prism_canonical.SCREENER_DATA_DIRS
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            current = root / "packages-data"
            legacy = root / "stock-screener-data"
            write_json(
                legacy / "lifecycle_2026-04-13_16-13.json",
                {"metadata": {"generated_at": "2026-04-13 16:13:00"}, "summary": {"entered_count": 1}},
            )
            write_json(
                current / "lifecycle_2026-05-19_12-20.json",
                {"metadata": {"generated_at": "2026-05-19 12:20:00"}, "summary": {"entered_count": 0}},
            )

            prism_canonical.SCREENER_DATA_DIRS = (current, legacy)
            try:
                resolved = prism_canonical.resolve_lifecycle_path(require_activity=True)
                self.assertEqual(resolved, legacy / "lifecycle_2026-04-13_16-13.json")
            finally:
                prism_canonical.SCREENER_DATA_DIRS = original_dirs

    def test_quality_status_prefers_internal_expected_trade_date_over_filename(self) -> None:
        original_patterns = prism_canonical.QUALITY_PATTERNS
        previous_expected = os.environ.get("PRISM_EXPECTED_TRADE_DATE")
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_json(
                root / "quality_gate_watchlist_2026-05-30.json",
                {
                    "checked_at": "2026-05-30 10:11:24",
                    "validation_status": "ok",
                },
            )
            write_json(
                root / "quality_gate_watchlist_2026-05-29.json",
                {
                    "checked_at": "2026-05-30 10:26:14",
                    "validation_status": "ok",
                    "trade_date": "2026-05-29",
                    "checked_trade_date": "2026-05-29",
                    "expected_trade_date": "2026-05-29",
                },
            )

            prism_canonical.QUALITY_PATTERNS = {
                **original_patterns,
                "watchlist": root / "quality_gate_watchlist_*.json",
            }
            os.environ["PRISM_EXPECTED_TRADE_DATE"] = "2026-05-29"
            try:
                status = prism_canonical.load_quality_status("watchlist")
                self.assertEqual(status["checked_trade_date"], "2026-05-29")
                self.assertTrue(status["path"].endswith("quality_gate_watchlist_2026-05-29.json"))
            finally:
                prism_canonical.QUALITY_PATTERNS = original_patterns
                if previous_expected is None:
                    os.environ.pop("PRISM_EXPECTED_TRADE_DATE", None)
                else:
                    os.environ["PRISM_EXPECTED_TRADE_DATE"] = previous_expected

    def test_decision_brief_resolver_limits_trade_date_scan_to_named_candidates(self) -> None:
        previous_dir = prism_canonical.COMMAND_BRIEF_DIR
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            brief_dir = root / "command_brief"
            target = brief_dir / "prism_command_brief_2026-05-12_11-04-46.json"
            same_day_bad = brief_dir / "prism_command_brief_2026-05-12_11-04-59.json"
            other_day = brief_dir / "prism_command_brief_2026-05-11_23-59-59.json"
            write_json(target, {"summary": {"trade_date": "2026-05-12", "generated_at": "2026-05-12 11:04:46"}})
            write_json(target.with_suffix(".manifest.json"), {"trade_date": "2026-05-12", "asof": "2026-05-12 11:04:46"})
            write_json(same_day_bad, {"summary": {"trade_date": "2026-05-12", "generated_at": "2026-05-12 11:04:59"}})
            write_json(same_day_bad.with_suffix(".manifest.json"), {"trade_date": "2026-05-11", "asof": "2026-05-12 11:04:59"})
            write_json(other_day, {"summary": {"trade_date": "2026-05-12", "generated_at": "2026-05-11 23:59:59"}})
            write_json(other_day.with_suffix(".manifest.json"), {"trade_date": "2026-05-12", "asof": "2026-05-11 23:59:59"})

            seen_payload_paths: list[str] = []
            seen_manifest_paths: list[str] = []
            original_load_json = prism_canonical.load_json
            original_load_manifest_file = prism_canonical.load_manifest_file

            def tracking_load_json(path: Path | None) -> dict:
                if path is not None:
                    seen_payload_paths.append(path.name)
                return original_load_json(path)

            def tracking_load_manifest_file(path: Path | None) -> dict | None:
                if path is not None:
                    seen_manifest_paths.append(Path(path).name)
                return original_load_manifest_file(path)

            prism_canonical.COMMAND_BRIEF_DIR = brief_dir
            try:
                with patch.object(prism_canonical, "load_json", side_effect=tracking_load_json), patch.object(
                    prism_canonical,
                    "load_manifest_file",
                    side_effect=tracking_load_manifest_file,
                ):
                    resolved = prism_canonical.resolve_decision_brief_path(trade_date="2026-05-12")
            finally:
                prism_canonical.COMMAND_BRIEF_DIR = previous_dir

        self.assertEqual(resolved, target)
        self.assertEqual(seen_payload_paths, [])
        self.assertEqual(
            set(seen_manifest_paths),
            {
                target.with_suffix(".manifest.json").name,
                same_day_bad.with_suffix(".manifest.json").name,
            },
        )
        self.assertNotIn(other_day.with_suffix(".manifest.json").name, seen_manifest_paths)

    def test_screener_history_resolver_filters_by_filename_before_payload_scan(self) -> None:
        original_dirs = prism_canonical.SCREENER_DATA_DIRS
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            current = root / "packages-data"
            legacy = root / "stock-screener-data"
            target = current / "ai_history" / "ai_screening_2026-05-14_10-30-01.json"
            other_day = current / "ai_history" / "ai_screening_2026-05-13_10-30-01.json"
            other_day_manifest = current / "ai_history" / "ai_screening_2026-05-13_10-30-01.manifest.json"
            write_json(target, {"timestamp": "2026-05-14 10:30:01"})
            write_json(other_day, {"timestamp": "2026-05-13 10:30:01"})
            write_json(other_day_manifest, {"trade_date": "2026-05-13"})

            seen_payload_paths: list[str] = []
            original_load_json = prism_canonical.load_json

            def tracking_load_json(path: Path | None) -> dict:
                if path is not None:
                    seen_payload_paths.append(path.name)
                return original_load_json(path)

            prism_canonical.SCREENER_DATA_DIRS = (current, legacy)
            try:
                with patch.object(prism_canonical, "load_json", side_effect=tracking_load_json):
                    resolved = prism_canonical.resolve_screening_batch_path(trade_date="2026-05-14")
            finally:
                prism_canonical.SCREENER_DATA_DIRS = original_dirs

        self.assertEqual(resolved, target)
        self.assertIn(target.name, seen_payload_paths)
        self.assertNotIn(other_day.name, seen_payload_paths)
        self.assertNotIn(other_day_manifest.name, seen_payload_paths)


if __name__ == "__main__":
    unittest.main()
