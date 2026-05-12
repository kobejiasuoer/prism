"""Guardrail coverage for direct fetch / provider import regression checks."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGES_DIR = REPO_ROOT / "packages"
if str(PACKAGES_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGES_DIR))

from prism_data.guardrails import (  # noqa: E402
    DEFAULT_EXCLUDE_PATHS,
    REPO_SCAN_ALLOWLIST,
    scan_for_direct_http_calls,
    scan_for_hardcoded_urls,
    scan_repo_for_ingress_violations,
)


class GuardrailsScanTests(unittest.TestCase):
    def _write(self, tmpdir: str, relative_path: str, text: str) -> Path:
        path = Path(tmpdir) / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_scan_detects_requests_get(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write(tmpdir, "demo.py", "import requests\nrequests.get('http://example.com')\n")
            violations = scan_for_direct_http_calls(root_path=tmpdir)
            self.assertTrue(any(v["call"] == "requests.get" for v in violations))

    def test_scan_detects_requests_alias_and_request_function(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write(tmpdir, "alias.py", "import requests as rq\nrq.post('http://example.com')\n")
            self._write(tmpdir, "from_import.py", "from requests import request as do_request\ndo_request('GET', 'http://example.com')\n")
            violations = scan_for_direct_http_calls(root_path=tmpdir)
            calls = {v["call"] for v in violations}
            self.assertIn("rq.post", calls)
            self.assertIn("requests.request", calls)

    def test_scan_detects_urllib_variants(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write(tmpdir, "import_alias.py", "import urllib.request as httpreq\nhttpreq.urlopen('http://example.com')\n")
            self._write(tmpdir, "from_import.py", "from urllib.request import urlopen\nurlopen('http://example.com')\n")
            violations = scan_for_direct_http_calls(root_path=tmpdir)
            calls = {v["call"] for v in violations}
            self.assertIn("httpreq.urlopen", calls)
            self.assertIn("urlopen", calls)

    def test_scan_detects_provider_imports(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write(tmpdir, "ak.py", "import akshare as ak\n")
            self._write(tmpdir, "bs.py", "from baostock import login\n")
            violations = scan_for_direct_http_calls(root_path=tmpdir)
            imports = {v["import"] for v in violations if v["type"] == "direct_provider_import"}
            self.assertEqual(imports, {"akshare", "baostock"})

    def test_scan_detects_hardcoded_provider_urls(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write(tmpdir, "demo.py", 'url = "https://push2.eastmoney.com/api/qt/ulist.np/get"\n')
            violations = scan_for_hardcoded_urls(root_path=tmpdir)
            self.assertTrue(any(v["type"] == "hardcoded_provider_url" for v in violations))

    def test_scan_respects_exclude_paths_and_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write(tmpdir, "providers/sina.py", "import requests\nrequests.get('http://example.com')\n")
            self._write(tmpdir, "allowed.py", "from urllib.request import urlopen\nurlopen('http://example.com')\n")
            violations = scan_for_direct_http_calls(
                root_path=tmpdir,
                exclude_paths=["providers"],
                allowlist_files={"allowed.py": "intentional test allowlist"},
            )
            self.assertEqual(violations, [])

    def test_repo_scan_does_not_crash(self) -> None:
        violations = scan_repo_for_ingress_violations(REPO_ROOT)
        self.assertIsInstance(violations, list)

    def test_repo_allowlist_is_documented(self) -> None:
        self.assertIn("packages/quant/free_sources/live_smoke_runner.py", REPO_SCAN_ALLOWLIST)
        self.assertTrue(REPO_SCAN_ALLOWLIST["packages/quant/free_sources/live_smoke_runner.py"])

    def test_default_excludes_cover_provider_adapters(self) -> None:
        self.assertIn("packages/prism_data/providers", DEFAULT_EXCLUDE_PATHS)


if __name__ == "__main__":
    unittest.main()
