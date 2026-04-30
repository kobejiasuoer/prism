from __future__ import annotations

from .contracts import ResearchStatus
from .manifest import AdapterLayer, FreeSourceProvider
from .provider_contracts import PROVIDER_FIELD_MAPPINGS, ProviderFieldMapping


def all_provider_mappings() -> tuple[ProviderFieldMapping, ...]:
    return PROVIDER_FIELD_MAPPINGS


def mappings_for_provider(provider: FreeSourceProvider) -> tuple[ProviderFieldMapping, ...]:
    return tuple(mapping for mapping in PROVIDER_FIELD_MAPPINGS if mapping.provider == provider)


def mappings_for_layer(adapter_layer: AdapterLayer) -> tuple[ProviderFieldMapping, ...]:
    return tuple(mapping for mapping in PROVIDER_FIELD_MAPPINGS if mapping.adapter_layer == adapter_layer)


def mappings_for_provider_layer(
    provider: FreeSourceProvider,
    adapter_layer: AdapterLayer,
) -> tuple[ProviderFieldMapping, ...]:
    return tuple(
        mapping
        for mapping in PROVIDER_FIELD_MAPPINGS
        if mapping.provider == provider and mapping.adapter_layer == adapter_layer
    )


def canonical_candidates_for_layer(adapter_layer: AdapterLayer) -> frozenset[str]:
    return frozenset(mapping.canonical_candidate for mapping in mappings_for_layer(adapter_layer))


def mappings_by_research_status(research_status: ResearchStatus) -> tuple[ProviderFieldMapping, ...]:
    return tuple(mapping for mapping in PROVIDER_FIELD_MAPPINGS if mapping.research_status == research_status)


def has_mapping(provider: FreeSourceProvider, adapter_layer: AdapterLayer) -> bool:
    return bool(mappings_for_provider_layer(provider, adapter_layer))
