from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()
