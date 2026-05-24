"""Dataset definitions and manifest helpers for Prism data ingress."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from .contracts import DatasetStatus, ProviderResult, ProviderRole
from .freshness import update_manifest_freshness, worst_freshness_status
from .utils import hash_payload


@dataclass
class DataManifest:
    schema_version: int
    dataset: str
    provider: str
    provider_role: str
    trade_date: str
    fetched_at: str
    asof: str | None
    ttl_seconds: int
    status: str
    freshness_status: str
    fallback_used: bool
    row_count: int
    payload_hash: str
    live_small_allowed: bool
    quality_flags: list[str] = field(default_factory=list)
    source_endpoint: str = "redacted"
    params_hash: str = ""
    license_scope: str = "internal_research"
    error: str | None = None
    request_key: str = ""
    manifest_path: str | None = None
    data_path: str | None = None
    upstream_manifests: list[dict[str, Any]] = field(default_factory=list)
    provider_provenance: list[dict[str, Any]] = field(default_factory=list)
    source_lane: str = "unknown"
    decision_scope: str = "display_only"
    authority_provider: str = ""
    target_authority_provider: str = ""
    audit_providers: list[str] = field(default_factory=list)
    source_authority_ready: bool = True
    formal_decision_allowed: bool = False
    authority_flags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DataManifest":
        return cls(
            schema_version=int(data.get("schema_version", 1)),
            dataset=str(data.get("dataset") or ""),
            provider=str(data.get("provider") or ""),
            provider_role=str(data.get("provider_role") or ProviderRole.PRIMARY.value),
            trade_date=str(data.get("trade_date") or ""),
            fetched_at=str(data.get("fetched_at") or ""),
            asof=data.get("asof"),
            ttl_seconds=int(data.get("ttl_seconds") or 0),
            status=str(data.get("status") or DatasetStatus.FAILED.value),
            freshness_status=str(data.get("freshness_status") or "expired"),
            fallback_used=bool(data.get("fallback_used")),
            row_count=int(data.get("row_count") or 0),
            payload_hash=str(data.get("payload_hash") or ""),
            live_small_allowed=bool(data.get("live_small_allowed")),
            quality_flags=list(data.get("quality_flags") or []),
            source_endpoint=str(data.get("source_endpoint") or "redacted"),
            params_hash=str(data.get("params_hash") or ""),
            license_scope=str(data.get("license_scope") or "internal_research"),
            error=data.get("error"),
            request_key=str(data.get("request_key") or ""),
            manifest_path=data.get("manifest_path"),
            data_path=data.get("data_path"),
            upstream_manifests=list(data.get("upstream_manifests") or []),
            provider_provenance=list(data.get("provider_provenance") or []),
            source_lane=str(data.get("source_lane") or "unknown"),
            decision_scope=str(data.get("decision_scope") or "display_only"),
            authority_provider=str(data.get("authority_provider") or ""),
            target_authority_provider=str(data.get("target_authority_provider") or ""),
            audit_providers=list(data.get("audit_providers") or []),
            source_authority_ready=bool(data.get("source_authority_ready", True)),
            formal_decision_allowed=bool(data.get("formal_decision_allowed")),
            authority_flags=list(data.get("authority_flags") or []),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset": self.dataset,
            "provider": self.provider,
            "provider_role": self.provider_role,
            "trade_date": self.trade_date,
            "fetched_at": self.fetched_at,
            "asof": self.asof,
            "ttl_seconds": self.ttl_seconds,
            "status": self.status,
            "freshness_status": self.freshness_status,
            "fallback_used": self.fallback_used,
            "row_count": self.row_count,
            "payload_hash": self.payload_hash,
            "live_small_allowed": self.live_small_allowed,
            "quality_flags": self.quality_flags,
            "source_endpoint": self.source_endpoint,
            "params_hash": self.params_hash,
            "license_scope": self.license_scope,
            "error": self.error,
            "request_key": self.request_key,
            "manifest_path": self.manifest_path,
            "data_path": self.data_path,
            "upstream_manifests": self.upstream_manifests,
            "provider_provenance": self.provider_provenance,
            "source_lane": self.source_lane,
            "decision_scope": self.decision_scope,
            "authority_provider": self.authority_provider,
            "target_authority_provider": self.target_authority_provider,
            "audit_providers": self.audit_providers,
            "source_authority_ready": self.source_authority_ready,
            "formal_decision_allowed": self.formal_decision_allowed,
            "authority_flags": self.authority_flags,
        }


@dataclass
class DatasetDefinition:
    name: str
    description: str
    primary_provider: str
    fallback_providers: list[str] = field(default_factory=list)
    ttl_intraday: int = 900
    ttl_post_close: int = 86400
    required_for_live_small: bool = False
    source_lane: str = "live"
    decision_scope: str = "live_small"
    authority_provider: str | None = None
    target_authority_provider: str | None = None
    audit_providers: list[str] = field(default_factory=list)


DATASET_REGISTRY: dict[str, DatasetDefinition] = {
    "quotes.snapshot": DatasetDefinition(
        name="quotes.snapshot",
        description="Single-stock quote snapshot",
        primary_provider="sina",
        fallback_providers=["eastmoney"],
        ttl_intraday=120,
        ttl_post_close=86400,
        required_for_live_small=True,
        source_lane="live",
        decision_scope="live_small",
        authority_provider="sina",
        audit_providers=["eastmoney"],
    ),
    "quotes.batch": DatasetDefinition(
        name="quotes.batch",
        description="Batch quote snapshot",
        primary_provider="eastmoney",
        fallback_providers=["sina"],
        ttl_intraday=120,
        ttl_post_close=86400,
        required_for_live_small=True,
        source_lane="live",
        decision_scope="live_small",
        authority_provider="eastmoney",
        audit_providers=["sina"],
    ),
    "quotes.pool": DatasetDefinition(
        name="quotes.pool",
        description="Sina market pool snapshot",
        primary_provider="sina",
        fallback_providers=[],
        ttl_intraday=900,
        ttl_post_close=86400,
        required_for_live_small=False,
        source_lane="live",
        decision_scope="display_only",
        authority_provider="sina",
    ),
    "bars.daily": DatasetDefinition(
        name="bars.daily",
        description="Daily bars / K-line",
        primary_provider="sina",
        fallback_providers=["akshare"],
        ttl_intraday=3600,
        ttl_post_close=86400,
        required_for_live_small=True,
        source_lane="authoritative_daily",
        decision_scope="live_small",
        authority_provider="sina",
        target_authority_provider="tushare",
        audit_providers=["akshare", "baostock"],
    ),
    "capital_flow.daily": DatasetDefinition(
        name="capital_flow.daily",
        description="Single-stock capital flow history",
        primary_provider="eastmoney",
        fallback_providers=["ths"],
        ttl_intraday=600,
        ttl_post_close=86400,
        required_for_live_small=True,
        source_lane="live",
        decision_scope="live_small",
        authority_provider="eastmoney",
        audit_providers=["ths"],
    ),
    "capital_flow.batch": DatasetDefinition(
        name="capital_flow.batch",
        description="Batch capital flow snapshots",
        primary_provider="eastmoney",
        fallback_providers=[],
        ttl_intraday=420,
        ttl_post_close=86400,
        required_for_live_small=True,
        source_lane="live",
        decision_scope="live_small",
        authority_provider="eastmoney",
    ),
    "fundamentals.snapshot": DatasetDefinition(
        name="fundamentals.snapshot",
        description="Single-stock fundamentals snapshot",
        primary_provider="eastmoney",
        fallback_providers=["ths"],
        ttl_intraday=43200,
        ttl_post_close=86400,
        required_for_live_small=False,
        source_lane="reference",
        decision_scope="display_only",
        authority_provider="eastmoney",
        audit_providers=["ths"],
    ),
    "fundamentals.batch": DatasetDefinition(
        name="fundamentals.batch",
        description="Batch fundamentals snapshot",
        primary_provider="eastmoney",
        fallback_providers=[],
        ttl_intraday=43200,
        ttl_post_close=86400,
        required_for_live_small=False,
        source_lane="reference",
        decision_scope="display_only",
        authority_provider="eastmoney",
    ),
    "announcements.latest": DatasetDefinition(
        name="announcements.latest",
        description="Latest announcements",
        primary_provider="eastmoney",
        fallback_providers=[],
        ttl_intraday=14400,
        ttl_post_close=86400,
        required_for_live_small=False,
        source_lane="disclosure",
        decision_scope="display_only",
        authority_provider="eastmoney",
        target_authority_provider="official_exchange",
        audit_providers=["cninfo", "sse", "szse"],
    ),
    "news.latest": DatasetDefinition(
        name="news.latest",
        description="Latest stock news",
        primary_provider="eastmoney",
        fallback_providers=[],
        ttl_intraday=14400,
        ttl_post_close=86400,
        required_for_live_small=False,
        source_lane="news",
        decision_scope="display_only",
        authority_provider="eastmoney",
    ),
    "stock.search": DatasetDefinition(
        name="stock.search",
        description="Stock search suggestions",
        primary_provider="sina",
        fallback_providers=[],
        ttl_intraday=86400,
        ttl_post_close=86400,
        required_for_live_small=False,
        source_lane="reference",
        decision_scope="display_only",
        authority_provider="sina",
    ),
    "index.constituents": DatasetDefinition(
        name="index.constituents",
        description="Index constituent list",
        primary_provider="akshare",
        fallback_providers=[],
        ttl_intraday=86400,
        ttl_post_close=86400,
        required_for_live_small=False,
        source_lane="reference",
        decision_scope="display_only",
        authority_provider="akshare",
        target_authority_provider="official_index",
        audit_providers=["csindex", "sina"],
    ),
    "sector.snapshot": DatasetDefinition(
        name="sector.snapshot",
        description="Sector snapshot",
        primary_provider="eastmoney",
        fallback_providers=[],
        ttl_intraday=1800,
        ttl_post_close=86400,
        required_for_live_small=False,
        source_lane="live",
        decision_scope="display_only",
        authority_provider="eastmoney",
    ),
    "watchlist.snapshot": DatasetDefinition(
        name="watchlist.snapshot",
        description="Analyzer watchlist business snapshot",
        primary_provider="pipeline",
        fallback_providers=[],
        ttl_intraday=900,
        ttl_post_close=86400,
        required_for_live_small=True,
        source_lane="pipeline",
        decision_scope="live_small",
        authority_provider="pipeline",
    ),
    "screening.scan_result": DatasetDefinition(
        name="screening.scan_result",
        description="Raw screener scan output",
        primary_provider="pipeline",
        fallback_providers=[],
        ttl_intraday=900,
        ttl_post_close=86400,
        required_for_live_small=True,
        source_lane="pipeline",
        decision_scope="live_small",
        authority_provider="pipeline",
    ),
    "screening.batch": DatasetDefinition(
        name="screening.batch",
        description="AI-screened shortlist",
        primary_provider="pipeline",
        fallback_providers=[],
        ttl_intraday=900,
        ttl_post_close=86400,
        required_for_live_small=True,
        source_lane="pipeline",
        decision_scope="live_small",
        authority_provider="pipeline",
    ),
    "screening.confirmation": DatasetDefinition(
        name="screening.confirmation",
        description="Midday confirmation batch",
        primary_provider="pipeline",
        fallback_providers=[],
        ttl_intraday=900,
        ttl_post_close=86400,
        required_for_live_small=True,
        source_lane="pipeline",
        decision_scope="live_small",
        authority_provider="pipeline",
    ),
    "decision_brief.snapshot": DatasetDefinition(
        name="decision_brief.snapshot",
        description="Command brief JSON payload",
        primary_provider="pipeline",
        fallback_providers=[],
        ttl_intraday=900,
        ttl_post_close=86400,
        required_for_live_small=True,
        source_lane="pipeline",
        decision_scope="live_small",
        authority_provider="pipeline",
    ),
    "trade_calendar": DatasetDefinition(
        name="trade_calendar",
        description="Trading calendar source of truth",
        primary_provider="tushare",
        fallback_providers=["baostock"],
        ttl_intraday=86400,
        ttl_post_close=86400,
        required_for_live_small=False,
        source_lane="authoritative_daily",
        decision_scope="formal_candidate",
        authority_provider="tushare",
        audit_providers=["baostock", "official_exchange"],
    ),
    "benchmark.index_daily": DatasetDefinition(
        name="benchmark.index_daily",
        description="CSI500 / HS300 benchmark daily bars",
        primary_provider="tushare",
        fallback_providers=["baostock", "akshare"],
        ttl_intraday=86400,
        ttl_post_close=86400,
        required_for_live_small=False,
        source_lane="authoritative_daily",
        decision_scope="formal_candidate",
        authority_provider="tushare",
        audit_providers=["baostock", "akshare", "csindex"],
    ),
    "adjustment.factor": DatasetDefinition(
        name="adjustment.factor",
        description="Adjustment factor source for formal adjusted returns",
        primary_provider="tushare",
        fallback_providers=[],
        ttl_intraday=86400,
        ttl_post_close=86400,
        required_for_live_small=False,
        source_lane="authoritative_daily",
        decision_scope="formal_candidate",
        authority_provider="tushare",
    ),
    "price_limit.daily": DatasetDefinition(
        name="price_limit.daily",
        description="Historical up/down limit prices",
        primary_provider="tushare",
        fallback_providers=[],
        ttl_intraday=86400,
        ttl_post_close=86400,
        required_for_live_small=False,
        source_lane="execution",
        decision_scope="formal_candidate",
        authority_provider="tushare",
        audit_providers=["ricequant", "joinquant"],
    ),
    "execution.flags": DatasetDefinition(
        name="execution.flags",
        description="Execution availability flags: paused/ST/limit/tick constraints",
        primary_provider="ricequant",
        fallback_providers=["joinquant"],
        ttl_intraday=86400,
        ttl_post_close=86400,
        required_for_live_small=False,
        source_lane="execution",
        decision_scope="formal_candidate",
        authority_provider="ricequant",
        audit_providers=["joinquant", "tushare"],
    ),
}


def get_dataset_definition(name: str) -> DatasetDefinition | None:
    return DATASET_REGISTRY.get(name)


_VALID_DECISION_SCOPES = frozenset({"live_small", "display_only", "formal_candidate"})
_VALID_SOURCE_LANES = frozenset({
    "live",
    "authoritative_daily",
    "disclosure",
    "reference",
    "news",
    "execution",
    "pipeline",
})
_FORMAL_LANES = frozenset({"authoritative_daily", "execution"})


@dataclass(frozen=True)
class RegistryIssue:
    dataset: str
    code: str
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {"dataset": self.dataset, "code": self.code, "message": self.message}


def validate_dataset_registry(
    registry: dict[str, DatasetDefinition] | None = None,
) -> list[RegistryIssue]:
    """Run static schema + semantic checks against a dataset registry.

    Returns a (possibly empty) list of issues. The real ``DATASET_REGISTRY``
    must validate clean — the test suite enforces that.
    """
    target = DATASET_REGISTRY if registry is None else registry
    issues: list[RegistryIssue] = []
    for name, definition in target.items():
        if definition.name != name:
            issues.append(RegistryIssue(
                dataset=name,
                code="name_key_mismatch",
                message=f"registry key `{name}` does not match definition.name `{definition.name}`",
            ))
        if definition.decision_scope not in _VALID_DECISION_SCOPES:
            issues.append(RegistryIssue(
                dataset=name,
                code="unknown_decision_scope",
                message=f"decision_scope `{definition.decision_scope}` is not in {sorted(_VALID_DECISION_SCOPES)}",
            ))
        if definition.source_lane not in _VALID_SOURCE_LANES:
            issues.append(RegistryIssue(
                dataset=name,
                code="unknown_source_lane",
                message=f"source_lane `{definition.source_lane}` is not in {sorted(_VALID_SOURCE_LANES)}",
            ))
        if definition.source_lane == "pipeline" and definition.primary_provider != "pipeline":
            issues.append(RegistryIssue(
                dataset=name,
                code="pipeline_lane_requires_pipeline_primary",
                message=(
                    f"source_lane=pipeline but primary_provider=`{definition.primary_provider}`; "
                    "pipeline datasets must use primary_provider=`pipeline`"
                ),
            ))
        if definition.required_for_live_small and definition.decision_scope != "live_small":
            issues.append(RegistryIssue(
                dataset=name,
                code="required_for_live_small_requires_live_small_scope",
                message=(
                    f"required_for_live_small=True but decision_scope=`{definition.decision_scope}`; "
                    "must be live_small"
                ),
            ))
        if definition.decision_scope == "formal_candidate" and definition.source_lane not in _FORMAL_LANES:
            issues.append(RegistryIssue(
                dataset=name,
                code="formal_candidate_requires_formal_lane",
                message=(
                    f"decision_scope=formal_candidate but source_lane=`{definition.source_lane}`; "
                    f"must be one of {sorted(_FORMAL_LANES)}"
                ),
            ))
        if definition.primary_provider in definition.fallback_providers:
            issues.append(RegistryIssue(
                dataset=name,
                code="primary_in_fallback",
                message=(
                    f"primary_provider `{definition.primary_provider}` also appears in fallback_providers; "
                    "fallback list must not duplicate the primary"
                ),
            ))
        if (
            definition.authority_provider
            and definition.authority_provider != definition.primary_provider
        ):
            issues.append(RegistryIssue(
                dataset=name,
                code="authority_not_primary",
                message=(
                    f"authority_provider `{definition.authority_provider}` differs from "
                    f"primary_provider `{definition.primary_provider}`; the registry tracks current "
                    "authority — these must match until primary itself is rotated"
                ),
            ))
    return issues


def _authority_metadata(
    *,
    dataset: str,
    provider: str,
    provider_role: str,
    status: str,
    live_small_allowed: bool,
    payload_hash: str,
) -> dict[str, Any]:
    definition = get_dataset_definition(dataset)
    source_lane = definition.source_lane if definition else "unknown"
    configured_authority = (definition.authority_provider if definition else None) or (definition.primary_provider if definition else provider)
    target_authority = (definition.target_authority_provider if definition else None) or configured_authority
    fallback_providers = list(definition.fallback_providers if definition else [])
    audit_providers = list(definition.audit_providers if definition else [])
    authority_flags: list[str] = []

    if provider_role == ProviderRole.FALLBACK.value:
        authority_flags.append("fallback_provider")
        if not live_small_allowed:
            authority_flags.append("fallback_display_only")

    if configured_authority and provider != configured_authority:
        if provider in fallback_providers:
            authority_flags.append("non_primary_fallback")
        else:
            authority_flags.append("non_authority_provider")

    if target_authority and provider != target_authority:
        authority_flags.append(f"target_authority_not_in_use:{target_authority}")

    if status != DatasetStatus.OK.value:
        authority_flags.append("provider_not_ok")
    if not payload_hash:
        authority_flags.append("payload_hash_missing")

    source_authority_ready = (
        status == DatasetStatus.OK.value
        and bool(payload_hash)
        and provider == configured_authority
        and provider == target_authority
    )
    decision_scope = (definition.decision_scope if definition else "live_small") if live_small_allowed else "display_only"
    formal_decision_allowed = (
        source_lane in {"authoritative_daily", "execution"}
        and source_authority_ready
        and live_small_allowed
    )

    return {
        "source_lane": source_lane,
        "decision_scope": decision_scope,
        "authority_provider": configured_authority,
        "target_authority_provider": target_authority,
        "audit_providers": audit_providers,
        "source_authority_ready": source_authority_ready,
        "formal_decision_allowed": formal_decision_allowed,
        "authority_flags": authority_flags,
    }


def _pipeline_authority_metadata(
    *,
    live_small_allowed: bool,
    upstream_rows: list[DataManifest],
    quality_flags: list[str],
) -> dict[str, Any]:
    upstream_flags: list[str] = []
    for row in upstream_rows:
        for flag in row.authority_flags:
            if flag not in upstream_flags:
                upstream_flags.append(flag)
    if not upstream_rows:
        upstream_flags.append("upstream_authority_missing")
    if any(not row.source_authority_ready for row in upstream_rows):
        upstream_flags.append("upstream_authority_not_ready")
    if any(not row.formal_decision_allowed for row in upstream_rows):
        upstream_flags.append("upstream_formal_not_allowed")

    decision_scope = "live_small" if live_small_allowed else "display_only"
    return {
        "source_lane": "pipeline",
        "decision_scope": decision_scope,
        "authority_provider": "pipeline",
        "target_authority_provider": "pipeline",
        "audit_providers": [],
        "source_authority_ready": bool(live_small_allowed and not quality_flags and "upstream_authority_not_ready" not in upstream_flags),
        "formal_decision_allowed": bool(live_small_allowed and upstream_rows and "upstream_formal_not_allowed" not in upstream_flags),
        "authority_flags": upstream_flags,
    }


def _format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.strftime("%Y-%m-%d %H:%M:%S")


def manifest_from_provider_result(
    result: ProviderResult,
    *,
    expected_trade_date: str,
    live_small_allowed: bool,
    manifest_path: str | None = None,
    data_path: str | None = None,
    upstream_manifests: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    authority = _authority_metadata(
        dataset=result.dataset,
        provider=result.provider,
        provider_role=result.provider_role.value,
        status=result.status.value,
        live_small_allowed=live_small_allowed,
        payload_hash=result.payload_hash,
    )
    manifest = {
        "schema_version": 1,
        "dataset": result.dataset,
        "provider": result.provider,
        "provider_role": result.provider_role.value,
        "trade_date": result.trade_date,
        "fetched_at": _format_datetime(result.fetched_at),
        "asof": _format_datetime(result.asof),
        "ttl_seconds": int(result.ttl_seconds),
        "status": result.status.value,
        "freshness_status": "expired",
        "fallback_used": result.provider_role == ProviderRole.FALLBACK,
        "row_count": int(result.row_count),
        "payload_hash": result.payload_hash,
        "live_small_allowed": bool(live_small_allowed),
        "quality_flags": list(result.quality_flags),
        "source_endpoint": result.source_endpoint,
        "params_hash": result.params_hash,
        "license_scope": result.license_scope,
        "error": result.error,
        "request_key": result.request_key,
        "manifest_path": manifest_path,
        "data_path": data_path,
        "upstream_manifests": list(upstream_manifests or []),
        "provider_provenance": [
            {
                "dataset": result.dataset,
                "provider": result.provider,
                "provider_role": result.provider_role.value,
                "trade_date": result.trade_date,
                "freshness_status": "pending",
                "live_small_allowed": bool(live_small_allowed),
            }
        ],
        **authority,
    }
    update_manifest_freshness(manifest, expected_trade_date)
    manifest["provider_provenance"][0]["freshness_status"] = manifest["freshness_status"]
    return manifest


def build_pipeline_manifest(
    *,
    dataset: str,
    trade_date: str,
    payload: Any,
    upstream_manifests: list[dict[str, Any]],
    ttl_seconds: int,
    required_datasets: set[str] | None = None,
    required_dataset_groups: list[set[str]] | None = None,
    fetched_at: str | None = None,
    quality_flags: list[str] | None = None,
) -> dict[str, Any]:
    flags = list(quality_flags or [])
    required = set(required_datasets or set())
    grouped_requirements = [set(group) for group in (required_dataset_groups or [])]
    grouped_requirements.extend([{name} for name in sorted(required)])
    upstream_rows = [DataManifest.from_dict(item) for item in upstream_manifests if isinstance(item, dict)]
    if not upstream_rows:
        flags.append("upstream_manifests_missing")
    freshness_values = [row.freshness_status for row in upstream_rows]
    trade_dates = {row.trade_date for row in upstream_rows if row.trade_date}
    fallback_used = any(row.fallback_used for row in upstream_rows)
    final_trade_date = trade_date
    if len(trade_dates) == 1:
        final_trade_date = next(iter(trade_dates))
    elif len(trade_dates) > 1:
        flags.append("upstream_trade_date_inconsistent")
    live_small_allowed = True
    for group in grouped_requirements:
        group_rows = [row for row in upstream_rows if row.dataset in group]
        group_label = "|".join(sorted(group))
        if not group_rows:
            flags.append(f"missing_required_dataset_group:{group_label}")
            live_small_allowed = False
            continue
        if not any(row.freshness_status == "fresh" and row.live_small_allowed for row in group_rows):
            flags.append(f"required_dataset_group_not_live:{group_label}")
            live_small_allowed = False
    if not upstream_rows:
        live_small_allowed = False
    if fallback_used:
        flags.append("upstream_fallback_present")
    if any(status != "fresh" for status in freshness_values):
        flags.append("upstream_not_fresh")
    provider_provenance = [
        {
            "dataset": row.dataset,
            "provider": row.provider,
            "provider_role": row.provider_role,
            "trade_date": row.trade_date,
            "freshness_status": row.freshness_status,
            "live_small_allowed": row.live_small_allowed,
        }
        for row in upstream_rows
    ]
    row_count = len(payload) if isinstance(payload, list) else (len(payload) if isinstance(payload, dict) else 1)
    authority = _pipeline_authority_metadata(
        live_small_allowed=live_small_allowed,
        upstream_rows=upstream_rows,
        quality_flags=flags,
    )
    manifest = {
        "schema_version": 1,
        "dataset": dataset,
        "provider": "pipeline",
        "provider_role": ProviderRole.PRIMARY.value,
        "trade_date": final_trade_date,
        "fetched_at": fetched_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "asof": fetched_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ttl_seconds": int(ttl_seconds),
        "status": DatasetStatus.OK.value,
        "freshness_status": worst_freshness_status(freshness_values) if freshness_values else "expired",
        "fallback_used": fallback_used,
        "row_count": int(max(row_count, 0)),
        "payload_hash": hash_payload(payload),
        "live_small_allowed": bool(live_small_allowed),
        "quality_flags": flags,
        "source_endpoint": "pipeline",
        "params_hash": "",
        "license_scope": "internal_research",
        "error": None,
        "request_key": "",
        "upstream_manifests": [row.to_dict() for row in upstream_rows],
        "provider_provenance": provider_provenance,
        **authority,
    }
    return manifest


def load_manifest_file(path: str | Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    target = Path(path).expanduser()
    if not target.exists():
        return None
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_sidecar_manifest(data_path: str | Path, manifest: dict[str, Any]) -> Path:
    target = Path(data_path).expanduser()
    manifest_path = target.with_suffix(".manifest.json")
    payload = dict(manifest)
    payload["manifest_path"] = str(manifest_path.resolve())
    payload["data_path"] = str(target.resolve())
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path


__all__ = [
    "DATASET_REGISTRY",
    "DataManifest",
    "DatasetDefinition",
    "RegistryIssue",
    "build_pipeline_manifest",
    "get_dataset_definition",
    "load_manifest_file",
    "manifest_from_provider_result",
    "validate_dataset_registry",
    "write_sidecar_manifest",
]
