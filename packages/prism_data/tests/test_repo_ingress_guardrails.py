"""Repo-level regression test for unified data ingress."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGES_DIR = REPO_ROOT / "packages"
if str(PACKAGES_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGES_DIR))

from prism_data.guardrails import REPO_SCAN_ALLOWLIST, scan_repo_for_ingress_violations  # noqa: E402


class RepoIngressGuardrailTests(unittest.TestCase):
    def test_repo_has_no_unexplained_direct_ingress_violations(self) -> None:
        violations = scan_repo_for_ingress_violations(REPO_ROOT)
        self.assertEqual(
            violations,
            [],
            msg=(
                "Found direct external ingress outside packages/prism_data/providers "
                f"(allowlist={sorted(REPO_SCAN_ALLOWLIST)}): {violations}"
            ),
        )


if __name__ == "__main__":
    unittest.main()
