"""Static data capability matrix derived from ``DATASET_REGISTRY``.

This module is the *configuration view* of source authority. For each
registered dataset it reports what authority semantics the registry can
ever achieve, independent of any specific fetch event.

For the *runtime view* (the manifest produced by a real provider call)
see ``manifest._authority_metadata`` and ``manifest._pipeline_authority_metadata``.
The runtime view can only be MORE restrictive than the configuration view
(fallback used, fetch failed, trade_date mismatch, missing upstream).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .manifest import DATASET_REGISTRY, DatasetDefinition, validate_dataset_registry

__all__ = [
    "DataCapabilityEntry",
    "build_dataset_capability",
    "build_data_capability_matrix",
    "data_capability_matrix_as_dict",
]


_FORMAL_LANES = frozenset({"authoritative_daily", "execution"})


@dataclass(frozen=True)
class DataCapabilityEntry:
    dataset: str
    description: str
    source_lane: str
    decision_scope: str
    primary_provider: str
    fallback_providers: list[str]
    authority_provider: str
    target_authority_provider: str
    audit_providers: list[str]
    required_for_live_small: bool
    source_authority_ready: bool
    formal_decision_allowed: bool
    source_authority_semantics: str
    formal_decision_semantics: str
    risk_flags: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "description": self.description,
            "source_lane": self.source_lane,
            "decision_scope": self.decision_scope,
            "primary_provider": self.primary_provider,
            "fallback_providers": list(self.fallback_providers),
            "authority_provider": self.authority_provider,
            "target_authority_provider": self.target_authority_provider,
            "audit_providers": list(self.audit_providers),
            "required_for_live_small": self.required_for_live_small,
            "source_authority_ready": self.source_authority_ready,
            "formal_decision_allowed": self.formal_decision_allowed,
            "source_authority_semantics": self.source_authority_semantics,
            "formal_decision_semantics": self.formal_decision_semantics,
            "risk_flags": list(self.risk_flags),
        }


def _resolve_authority(definition: DatasetDefinition) -> tuple[str, str]:
    authority = definition.authority_provider or definition.primary_provider
    target = definition.target_authority_provider or authority
    return authority, target


def _build_entry(definition: DatasetDefinition) -> DataCapabilityEntry:
    authority, target = _resolve_authority(definition)
    primary = definition.primary_provider
    lane = definition.source_lane
    scope = definition.decision_scope
    fallbacks = list(definition.fallback_providers)

    risk_flags: list[str] = []
    if lane == "pipeline":
        risk_flags.append("pipeline_dataset")
    if primary != authority:
        risk_flags.append(f"authority_not_primary:{authority}")
    if primary != target:
        risk_flags.append(f"target_authority_not_in_use:{target}")
    if fallbacks:
        risk_flags.append("fallback_default_not_live")
    if not fallbacks and lane != "pipeline":
        risk_flags.append("no_fallback")
    if scope == "display_only":
        risk_flags.append("display_only")

    if lane == "pipeline":
        source_authority_ready = False
    else:
        source_authority_ready = primary == authority and primary == target

    if scope == "display_only":
        formal_decision_allowed = False
    elif lane == "pipeline":
        formal_decision_allowed = False
    else:
        formal_decision_allowed = lane in _FORMAL_LANES and source_authority_ready

    sa_sem = _source_authority_semantics(lane=lane, primary=primary, target=target)
    fd_sem = _formal_decision_semantics(
        lane=lane,
        scope=scope,
        primary=primary,
        target=target,
        source_authority_ready=source_authority_ready,
    )

    return DataCapabilityEntry(
        dataset=definition.name,
        description=definition.description,
        source_lane=lane,
        decision_scope=scope,
        primary_provider=primary,
        fallback_providers=fallbacks,
        authority_provider=authority,
        target_authority_provider=target,
        audit_providers=list(definition.audit_providers),
        required_for_live_small=definition.required_for_live_small,
        source_authority_ready=source_authority_ready,
        formal_decision_allowed=formal_decision_allowed,
        source_authority_semantics=sa_sem,
        formal_decision_semantics=fd_sem,
        risk_flags=risk_flags,
    )


def _source_authority_semantics(*, lane: str, primary: str, target: str) -> str:
    if lane == "pipeline":
        return (
            "pipeline dataset; source_authority_ready is derived from upstream "
            "manifests at runtime and is true only when every required upstream "
            "entry is source_authority_ready and the pipeline emits no quality flags."
        )
    if primary == target:
        return (
            f"primary `{primary}` equals target authority; "
            "source_authority_ready becomes true at runtime when the fetch is OK "
            "and payload_hash is present."
        )
    return (
        f"primary `{primary}` differs from target authority `{target}`; "
        f"source_authority_ready remains false until primary switches to `{target}`."
    )


def _formal_decision_semantics(
    *,
    lane: str,
    scope: str,
    primary: str,
    target: str,
    source_authority_ready: bool,
) -> str:
    if scope == "display_only":
        return (
            "decision_scope is display_only; formal_decision_allowed is never "
            "true regardless of provider freshness."
        )
    if lane == "pipeline":
        return (
            "pipeline-derived; formal_decision_allowed becomes true only when "
            "every required upstream entry is formal_decision_allowed and the "
            "pipeline manifest carries no quality flags."
        )
    if lane not in _FORMAL_LANES:
        return (
            f"lane `{lane}` is not authoritative_daily or execution; "
            "formal_decision_allowed is never true. Dataset is restricted to "
            "live or display use."
        )
    if not source_authority_ready:
        return (
            f"lane `{lane}` is formal-eligible but authority is not in place "
            f"(primary `{primary}` vs target authority `{target}`); "
            "formal_decision_allowed cannot become true until the target "
            "authority provider is used as primary."
        )
    return (
        f"lane `{lane}` and target authority `{target}` are both in place; "
        "formal_decision_allowed becomes true at runtime when "
        "source_authority_ready and live_small_allowed are both true."
    )


def build_dataset_capability(name: str) -> DataCapabilityEntry | None:
    definition = DATASET_REGISTRY.get(name)
    if definition is None:
        return None
    return _build_entry(definition)


def build_data_capability_matrix() -> list[DataCapabilityEntry]:
    return [_build_entry(definition) for definition in DATASET_REGISTRY.values()]


def _summarize(entries: list[DataCapabilityEntry]) -> dict[str, Any]:
    formal_ready: list[str] = []
    display_only: list[str] = []
    pending_target_authority: list[str] = []
    pipeline_datasets: list[str] = []
    required_for_live_small: list[str] = []
    formal_lane_not_ready: list[str] = []
    for entry in entries:
        if entry.formal_decision_allowed:
            formal_ready.append(entry.dataset)
        if entry.decision_scope == "display_only":
            display_only.append(entry.dataset)
        if entry.primary_provider != entry.target_authority_provider:
            pending_target_authority.append(entry.dataset)
        if entry.source_lane == "pipeline":
            pipeline_datasets.append(entry.dataset)
        if entry.required_for_live_small:
            required_for_live_small.append(entry.dataset)
        if (
            entry.source_lane in _FORMAL_LANES
            and entry.decision_scope != "display_only"
            and not entry.formal_decision_allowed
        ):
            formal_lane_not_ready.append(entry.dataset)
    return {
        "total": len(entries),
        "formal_ready": formal_ready,
        "display_only": display_only,
        "pending_target_authority": pending_target_authority,
        "pipeline_datasets": pipeline_datasets,
        "required_for_live_small": required_for_live_small,
        "formal_lane_not_ready": formal_lane_not_ready,
    }


def data_capability_matrix_as_dict() -> dict[str, Any]:
    entries = build_data_capability_matrix()
    issues = validate_dataset_registry()
    return {
        "schema_version": 1,
        "entry_count": len(entries),
        "summary": _summarize(entries),
        "registry_issues": [issue.as_dict() for issue in issues],
        "datasets": [entry.as_dict() for entry in entries],
    }
