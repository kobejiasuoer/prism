from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import Enum
import re
from typing import Any

from .redaction import RedactionError, assert_manifest_redacted


class ManifestValidationError(ValueError):
    """Raised when a free-source redacted manifest is invalid."""


class StrEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class FreeSourceProvider(StrEnum):
    BAOSTOCK = "baostock"
    AKSHARE = "akshare"


class ProviderRole(StrEnum):
    PRIMARY = "primary"
    CROSS_CHECK = "cross_check"
    SUPPLEMENT = "supplement"


class AdapterLayer(StrEnum):
    CALENDAR = "calendar"
    STOCK_BASIC = "stock_basic"
    RAW_DAILY = "raw_daily"
    QFQ_CANDIDATE = "qfq_candidate"
    INDEX_DAILY = "index_daily"
    TRADESTATUS_ISST = "tradestatus_isst"
    SUSPEND_EVENT = "suspend_event"
    LIMIT_CANDIDATE = "limit_candidate"


class ManifestStatus(StrEnum):
    AVAILABLE = "available"
    PARTIAL = "partial"
    MISSING = "missing"
    EMPTY = "empty"
    NETWORK_ERROR = "network_error"
    PROVIDER_ERROR = "provider_error"
    LICENSE_BLOCKED = "license_blocked"
    BLOCKED = "blocked"


class PitAsOfStatus(StrEnum):
    AS_COLLECTED_ONLY = "as_collected_only"
    PIT_WEAK = "pit_weak"
    NOT_PIT_READY = "not_pit_ready"
    UNKNOWN = "unknown"


class HashMethod(StrEnum):
    RAW_BYTES_SHA256 = "raw_bytes_sha256"
    CANONICAL_PAYLOAD_SHA256 = "canonical_payload_sha256"


REQUIRED_MANIFEST_FIELDS = (
    "schema_version",
    "run_id",
    "provider",
    "provider_role",
    "source_version",
    "adapter_layer",
    "endpoint",
    "params_fingerprint_sha256",
    "params_redacted",
    "retrieved_at",
    "response_hash_sha256",
    "hash_method",
    "row_count",
    "field_list",
    "expected_field_list",
    "missing_field_list",
    "non_null_summary",
    "duplicate_summary",
    "coverage_summary",
    "status",
    "license_usage_note",
    "pit_asof_status",
    "raw_archive_pointer",
    "repo_safe",
)

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def enum_values(enum_type: type[StrEnum]) -> set[str]:
    return {item.value for item in enum_type}


def validate_manifest(manifest: Mapping[str, Any]) -> bool:
    """Validate a repo-safe redacted free-source manifest."""

    if not isinstance(manifest, Mapping):
        raise ManifestValidationError("manifest must be a mapping")
    try:
        assert_manifest_redacted(manifest)
    except RedactionError as exc:
        raise ManifestValidationError(str(exc)) from exc

    missing = [field for field in REQUIRED_MANIFEST_FIELDS if field not in manifest]
    if missing:
        raise ManifestValidationError(f"missing required fields: {', '.join(missing)}")

    _require_non_empty_string(manifest, "schema_version")
    _require_non_empty_string(manifest, "run_id")
    _require_non_empty_string(manifest, "endpoint")
    _require_non_empty_string(manifest, "retrieved_at")
    _require_non_empty_string(manifest, "raw_archive_pointer")
    _require_enum(manifest, "provider", FreeSourceProvider)
    _require_enum(manifest, "provider_role", ProviderRole)
    _require_enum(manifest, "adapter_layer", AdapterLayer)
    _require_enum(manifest, "status", ManifestStatus)
    _require_enum(manifest, "pit_asof_status", PitAsOfStatus)
    _require_enum(manifest, "hash_method", HashMethod)
    _require_sha256(manifest, "params_fingerprint_sha256")
    _require_sha256(manifest, "response_hash_sha256")
    _require_mapping(manifest, "source_version")
    _require_mapping(manifest, "params_redacted")
    _require_mapping(manifest, "non_null_summary")
    _require_mapping(manifest, "duplicate_summary")
    _require_mapping(manifest, "coverage_summary")
    _require_mapping(manifest, "license_usage_note")
    _require_string_list(manifest, "field_list")
    _require_string_list(manifest, "expected_field_list")
    _require_string_list(manifest, "missing_field_list")
    _require_non_negative_int(manifest, "row_count")
    if manifest["repo_safe"] is not True:
        raise ManifestValidationError("repo_safe must be true")
    return True


def _require_non_empty_string(manifest: Mapping[str, Any], field: str) -> None:
    if not isinstance(manifest[field], str) or not manifest[field]:
        raise ManifestValidationError(f"{field} must be a non-empty string")


def _require_mapping(manifest: Mapping[str, Any], field: str) -> None:
    if not isinstance(manifest[field], Mapping):
        raise ManifestValidationError(f"{field} must be a mapping")


def _require_string_list(manifest: Mapping[str, Any], field: str) -> None:
    value = manifest[field]
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ManifestValidationError(f"{field} must be a list of strings")
    if not all(isinstance(item, str) for item in value):
        raise ManifestValidationError(f"{field} must be a list of strings")


def _require_non_negative_int(manifest: Mapping[str, Any], field: str) -> None:
    value = manifest[field]
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ManifestValidationError(f"{field} must be a non-negative integer")


def _require_sha256(manifest: Mapping[str, Any], field: str) -> None:
    value = manifest[field]
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise ManifestValidationError(f"{field} must be a lowercase sha256 hex digest")


def _require_enum(manifest: Mapping[str, Any], field: str, enum_type: type[StrEnum]) -> None:
    value = manifest[field]
    if value not in enum_values(enum_type):
        allowed = ", ".join(sorted(enum_values(enum_type)))
        raise ManifestValidationError(f"{field} must be one of: {allowed}")
