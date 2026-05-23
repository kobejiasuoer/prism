"""Tests for validate_dataset_registry() — schema + semantic checks."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGES_DIR = REPO_ROOT / "packages"
if str(PACKAGES_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGES_DIR))

from prism_data.manifest import (  # noqa: E402
    DATASET_REGISTRY,
    DatasetDefinition,
    RegistryIssue,
    validate_dataset_registry,
)


def _clone(base_name: str, **overrides: object) -> DatasetDefinition:
    base = DATASET_REGISTRY[base_name]
    fields = {
        "name": base.name,
        "description": base.description,
        "primary_provider": base.primary_provider,
        "fallback_providers": list(base.fallback_providers),
        "ttl_intraday": base.ttl_intraday,
        "ttl_post_close": base.ttl_post_close,
        "required_for_live_small": base.required_for_live_small,
        "source_lane": base.source_lane,
        "decision_scope": base.decision_scope,
        "authority_provider": base.authority_provider,
        "target_authority_provider": base.target_authority_provider,
        "audit_providers": list(base.audit_providers),
    }
    fields.update(overrides)
    return DatasetDefinition(**fields)  # type: ignore[arg-type]


class RealRegistryTests(unittest.TestCase):
    def test_real_registry_is_clean(self) -> None:
        issues = validate_dataset_registry()
        self.assertEqual(
            issues,
            [],
            f"DATASET_REGISTRY has validation issues: {[i.as_dict() for i in issues]}",
        )


class SchemaBreakTests(unittest.TestCase):
    def _validate_one(self, definition: DatasetDefinition) -> list[RegistryIssue]:
        return validate_dataset_registry({definition.name: definition})

    def test_unknown_decision_scope_flagged(self) -> None:
        broken = _clone("quotes.snapshot", decision_scope="formal_ready")
        codes = {issue.code for issue in self._validate_one(broken)}
        self.assertIn("unknown_decision_scope", codes)

    def test_unknown_source_lane_flagged(self) -> None:
        broken = _clone("quotes.snapshot", source_lane="experimental")
        codes = {issue.code for issue in self._validate_one(broken)}
        self.assertIn("unknown_source_lane", codes)

    def test_pipeline_lane_requires_pipeline_primary(self) -> None:
        broken = _clone("watchlist.snapshot", primary_provider="sina")
        codes = {issue.code for issue in self._validate_one(broken)}
        self.assertIn("pipeline_lane_requires_pipeline_primary", codes)

    def test_required_for_live_small_requires_live_small_scope(self) -> None:
        broken = _clone("quotes.snapshot", decision_scope="display_only")
        codes = {issue.code for issue in self._validate_one(broken)}
        self.assertIn("required_for_live_small_requires_live_small_scope", codes)

    def test_formal_candidate_requires_formal_lane(self) -> None:
        broken = _clone("trade_calendar", source_lane="reference")
        codes = {issue.code for issue in self._validate_one(broken)}
        self.assertIn("formal_candidate_requires_formal_lane", codes)

    def test_primary_in_fallback_flagged(self) -> None:
        broken = _clone("quotes.snapshot", fallback_providers=["sina", "eastmoney"])
        codes = {issue.code for issue in self._validate_one(broken)}
        self.assertIn("primary_in_fallback", codes)

    def test_authority_not_primary_flagged(self) -> None:
        broken = _clone("quotes.snapshot", authority_provider="ricequant")
        codes = {issue.code for issue in self._validate_one(broken)}
        self.assertIn("authority_not_primary", codes)

    def test_name_key_mismatch_flagged(self) -> None:
        definition = _clone("quotes.snapshot", name="quotes.snapshot.renamed")
        # Validator is keyed by the dict key, so put it under the original key.
        issues = validate_dataset_registry({"quotes.snapshot": definition})
        codes = {issue.code for issue in issues}
        self.assertIn("name_key_mismatch", codes)


if __name__ == "__main__":
    unittest.main()
