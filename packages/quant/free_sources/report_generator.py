from __future__ import annotations

from collections.abc import Mapping, Sequence
import re
from typing import Any

from .redaction import find_redaction_issues


class ReportGenerationError(ValueError):
    """Raised when redacted report input is unsafe or malformed."""


LOCAL_PATH_RE = re.compile(r"(^|\s)(/Users/|/tmp/|/var/|/private/|~/|\.?\.?/)")
URL_RE = re.compile(r"\b(?:file|https?|s3)://", re.IGNORECASE)
FORMAL_READY_RE = re.compile(
    r"\b(?:formal[-_ ]?ready|production[-_ ]?ready|approved for production)\b",
    re.IGNORECASE,
)


ENDPOINT_COLLECTION_KEYS = ("manifests", "endpoint_summaries", "endpoints")


def generate_redacted_report(
    manifest: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    title: str = "Prism Free-Source Redacted Availability Report",
) -> str:
    """Render repo-safe Markdown from redacted free-source endpoint metadata."""

    _assert_safe_input(manifest)
    endpoint_summaries = _normalize_endpoint_summaries(manifest)
    if not endpoint_summaries:
        raise ReportGenerationError("at least one endpoint summary is required")

    lines = [
        f"# {_escape_text(title)}",
        "",
        "This report is generated from redacted endpoint metadata only.",
        "It does not contain raw vendor data, row-level market data, formal outputs, or production routing instructions.",
        "",
        "## Endpoint Summary",
        "",
        "| Provider | Endpoint | Status | Row Count | Retrieved At | Response Hash |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    for item in endpoint_summaries:
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(item.get("provider", "n/a")),
                    _cell(item.get("endpoint", "n/a")),
                    _cell(item.get("status", "n/a")),
                    _cell(item.get("row_count", "n/a")),
                    _cell(item.get("retrieved_at", "n/a")),
                    _cell(_response_hash(item)),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Endpoint Details", ""])
    for item in endpoint_summaries:
        provider = _escape_text(str(item.get("provider", "unknown")))
        endpoint = _escape_text(str(item.get("endpoint", "unknown")))
        lines.extend(
            [
                f"### {provider} / `{endpoint}`",
                "",
                f"- Status: `{_escape_text(str(item.get('status', 'n/a')))}`",
                f"- Row count: `{_escape_text(str(item.get('row_count', 'n/a')))}`",
                f"- Field list: {_format_list(item.get('field_list', []))}",
                f"- Non-null summary: {_format_mapping(item.get('non_null_summary', {}))}",
                f"- Response hash: `{_escape_text(_response_hash(item))}`",
                f"- Retrieved at: `{_escape_text(str(item.get('retrieved_at', 'n/a')))}`",
                f"- Error summary: {_format_text(item.get('error_summary', 'none'))}",
                f"- Research-only notes: {_format_notes(item.get('research_only_notes') or item.get('research_notes'))}",
                f"- Blocker notes: {_format_notes(item.get('blocker_notes') or item.get('blocked_notes'))}",
                "",
            ]
        )

    lines.extend(
        [
            "## Guardrails",
            "",
            "- Free-source availability is research-only evidence.",
            "- QFQ, benchmark, execution flag, and suspend-event metadata remain candidate or partial evidence.",
            "- Formal labels, formal excess return, formal adjusted return, execution-realistic backtest, production sorting, A/B/C, page, Prism Edge, Expected 5D, and ML work remain blocked.",
        ]
    )
    report = "\n".join(lines).rstrip() + "\n"
    if FORMAL_READY_RE.search(report):
        raise ReportGenerationError("report must not claim formal-ready or production-ready status")
    return report


def _assert_safe_input(value: Any) -> None:
    findings = find_redaction_issues(value)
    if findings:
        details = "; ".join(f"{finding.path}: {finding.reason}" for finding in findings)
        raise ReportGenerationError(details)
    _reject_unsafe_strings(value)


def _reject_unsafe_strings(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            _reject_unsafe_strings(child, f"{path}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            _reject_unsafe_strings(item, f"{path}[{index}]")
        return
    if isinstance(value, str):
        if LOCAL_PATH_RE.search(value):
            raise ReportGenerationError(f"{path}: local paths are not allowed in redacted reports")
        if URL_RE.search(value):
            raise ReportGenerationError(f"{path}: URLs are not allowed in redacted reports")
        if FORMAL_READY_RE.search(value):
            raise ReportGenerationError(f"{path}: formal-ready or production-ready claims are not allowed")


def _normalize_endpoint_summaries(
    manifest: Mapping[str, Any] | Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    if isinstance(manifest, Mapping):
        if "provider" in manifest and "endpoint" in manifest:
            return (manifest,)
        for key in ENDPOINT_COLLECTION_KEYS:
            value = manifest.get(key)
            if value is not None:
                return _coerce_summary_sequence(value, f"$.{key}")
        raise ReportGenerationError("manifest must be an endpoint summary or contain endpoint summaries")
    return _coerce_summary_sequence(manifest, "$")


def _coerce_summary_sequence(value: Any, path: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ReportGenerationError(f"{path}: endpoint summaries must be a sequence")
    summaries: list[Mapping[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ReportGenerationError(f"{path}[{index}]: endpoint summary must be a mapping")
        if "provider" not in item or "endpoint" not in item:
            raise ReportGenerationError(f"{path}[{index}]: provider and endpoint are required")
        summaries.append(item)
    return tuple(summaries)


def _response_hash(item: Mapping[str, Any]) -> str:
    value = item.get("response_hash_sha256", item.get("response_hash", "n/a"))
    return str(value)


def _format_list(value: Any) -> str:
    if value in (None, ""):
        return "`none`"
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return _format_text(value)
    if not value:
        return "`none`"
    return ", ".join(f"`{_escape_text(str(item))}`" for item in value)


def _format_mapping(value: Any) -> str:
    if not isinstance(value, Mapping) or not value:
        return "`none`"
    return ", ".join(
        f"`{_escape_text(str(key))}={_escape_text(str(value[key]))}`"
        for key in sorted(value, key=lambda item: str(item))
    )


def _format_notes(value: Any) -> str:
    if not value:
        return "`none`"
    return _format_list(value)


def _format_text(value: Any) -> str:
    text = "none" if value in (None, "") else str(value)
    return _escape_text(text)


def _cell(value: Any) -> str:
    return _escape_text(str(value)).replace("\n", " ")


def _escape_text(value: str) -> str:
    return value.replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;")
