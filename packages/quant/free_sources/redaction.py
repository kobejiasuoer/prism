from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import re
from typing import Any


class RedactionError(ValueError):
    """Raised when a manifest contains non-redacted or unsafe content."""


SECRET_KEY_PARTS = (
    "authorization",
    "cookie",
    "password",
    "secret",
    "session",
    "token",
)

PROHIBITED_EXACT_KEYS = {
    "body",
    "calendar_date_array",
    "calendar_dates",
    "close_values",
    "csv",
    "dataframe",
    "full_calendar",
    "full_stock_list",
    "html",
    "json_rows",
    "limit_pool_constituents",
    "ohlcv_rows",
    "open_values",
    "payload",
    "prices",
    "raw_payload",
    "raw_response",
    "records",
    "rows",
    "security_rows",
    "stock_list",
    "suspend_event_rows",
    "vendor_rows",
}

UNSAFE_POINTER_SCHEMES = (
    "file://",
    "http://",
    "https://",
    "s3://",
)

OPAQUE_POINTER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,127}$")


@dataclass(frozen=True)
class RedactionFinding:
    path: str
    reason: str


def assert_manifest_redacted(manifest: Mapping[str, Any]) -> None:
    """Validate that a manifest contains only repo-safe redacted metadata."""

    findings = list(find_redaction_issues(manifest))
    if findings:
        details = "; ".join(f"{finding.path}: {finding.reason}" for finding in findings)
        raise RedactionError(details)


def find_redaction_issues(value: Any, path: str = "$") -> list[RedactionFinding]:
    findings: list[RedactionFinding] = []
    _collect_redaction_issues(value, path, findings)
    return findings


def _collect_redaction_issues(value: Any, path: str, findings: list[RedactionFinding]) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            lowered = key_text.lower()
            child_path = f"{path}.{key_text}"
            if _is_secret_key(lowered):
                findings.append(RedactionFinding(child_path, "secret-like key is not allowed"))
                continue
            if lowered in PROHIBITED_EXACT_KEYS:
                findings.append(RedactionFinding(child_path, "raw or reversible vendor data key is not allowed"))
                continue
            if lowered == "raw_archive_pointer":
                _check_raw_archive_pointer(child, child_path, findings)
            _collect_redaction_issues(child, child_path, findings)
        return

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            _collect_redaction_issues(item, f"{path}[{index}]", findings)


def _is_secret_key(lowered_key: str) -> bool:
    return any(part in lowered_key for part in SECRET_KEY_PARTS)


def _check_raw_archive_pointer(value: Any, path: str, findings: list[RedactionFinding]) -> None:
    if not isinstance(value, str) or not value:
        findings.append(RedactionFinding(path, "raw_archive_pointer must be a non-empty opaque string"))
        return

    lowered = value.lower()
    if value.startswith(("/", "~", "./", "../")):
        findings.append(RedactionFinding(path, "raw_archive_pointer must not expose a local path"))
        return
    if any(lowered.startswith(scheme) for scheme in UNSAFE_POINTER_SCHEMES):
        findings.append(RedactionFinding(path, "raw_archive_pointer must not expose a URL or object-store URI"))
        return
    if "://" in value or "@" in value or "?" in value or "=" in value:
        findings.append(RedactionFinding(path, "raw_archive_pointer must not contain credentials or query data"))
        return
    if _is_secret_key(lowered):
        findings.append(RedactionFinding(path, "raw_archive_pointer must not contain secret-like text"))
        return
    if not OPAQUE_POINTER_RE.fullmatch(value):
        findings.append(RedactionFinding(path, "raw_archive_pointer must be opaque and identifier-like"))
