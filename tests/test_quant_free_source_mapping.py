from __future__ import annotations

from quant.free_sources.canonical_mapping import (
    all_provider_mappings,
    canonical_candidates_for_layer,
    has_mapping,
    mappings_by_research_status,
    mappings_for_provider,
    mappings_for_provider_layer,
)
from quant.free_sources.contracts import BLOCKED_CAPABILITIES, ResearchStatus
from quant.free_sources.manifest import AdapterLayer, FreeSourceProvider, PitAsOfStatus, ProviderRole
from quant.free_sources.provider_contracts import BLOCKED_MAPPING_CAPABILITIES


def test_baostock_mapping_coverage() -> None:
    expected_layers = {
        AdapterLayer.CALENDAR,
        AdapterLayer.STOCK_BASIC,
        AdapterLayer.RAW_DAILY,
        AdapterLayer.QFQ_CANDIDATE,
        AdapterLayer.INDEX_DAILY,
        AdapterLayer.TRADESTATUS_ISST,
    }
    for layer in expected_layers:
        assert has_mapping(FreeSourceProvider.BAOSTOCK, layer)

    assert not has_mapping(FreeSourceProvider.BAOSTOCK, AdapterLayer.SUSPEND_EVENT)
    assert not has_mapping(FreeSourceProvider.BAOSTOCK, AdapterLayer.LIMIT_CANDIDATE)
    assert {mapping.provider_role for mapping in mappings_for_provider(FreeSourceProvider.BAOSTOCK)} == {
        ProviderRole.PRIMARY
    }


def test_akshare_mapping_coverage() -> None:
    expected_layers = {
        AdapterLayer.RAW_DAILY,
        AdapterLayer.QFQ_CANDIDATE,
        AdapterLayer.INDEX_DAILY,
        AdapterLayer.SUSPEND_EVENT,
    }
    for layer in expected_layers:
        assert has_mapping(FreeSourceProvider.AKSHARE, layer)

    assert not has_mapping(FreeSourceProvider.AKSHARE, AdapterLayer.CALENDAR)
    assert not has_mapping(FreeSourceProvider.AKSHARE, AdapterLayer.STOCK_BASIC)
    assert not has_mapping(FreeSourceProvider.AKSHARE, AdapterLayer.TRADESTATUS_ISST)
    assert {mapping.provider_role for mapping in mappings_for_provider_layer(FreeSourceProvider.AKSHARE, AdapterLayer.RAW_DAILY)} == {
        ProviderRole.CROSS_CHECK
    }
    assert {mapping.provider_role for mapping in mappings_for_provider_layer(FreeSourceProvider.AKSHARE, AdapterLayer.INDEX_DAILY)} == {
        ProviderRole.SUPPLEMENT
    }


def test_all_mappings_use_valid_enums_and_do_not_allow_formal_use() -> None:
    valid_providers = set(FreeSourceProvider)
    valid_roles = set(ProviderRole)
    valid_layers = set(AdapterLayer)
    valid_pit_statuses = set(PitAsOfStatus)
    valid_research_statuses = set(ResearchStatus)

    for mapping in all_provider_mappings():
        assert mapping.provider in valid_providers
        assert mapping.provider_role in valid_roles
        assert mapping.adapter_layer in valid_layers
        assert mapping.pit_asof_status in valid_pit_statuses
        assert mapping.research_status in valid_research_statuses
        assert mapping.formal_allowed is False
        assert mapping.endpoint
        assert mapping.raw_field
        assert mapping.canonical_candidate
        assert mapping.notes


def test_candidate_and_research_only_statuses_are_preserved() -> None:
    assert {
        mapping.research_status
        for mapping in mappings_for_provider_layer(FreeSourceProvider.BAOSTOCK, AdapterLayer.QFQ_CANDIDATE)
    } == {ResearchStatus.RESEARCH_ONLY}
    assert {
        mapping.research_status
        for mapping in mappings_for_provider_layer(FreeSourceProvider.AKSHARE, AdapterLayer.QFQ_CANDIDATE)
    } == {ResearchStatus.RESEARCH_ONLY}
    assert {
        mapping.research_status
        for mapping in mappings_for_provider_layer(FreeSourceProvider.BAOSTOCK, AdapterLayer.INDEX_DAILY)
    } == {ResearchStatus.CANDIDATE}
    assert {
        mapping.research_status
        for mapping in mappings_for_provider_layer(FreeSourceProvider.AKSHARE, AdapterLayer.INDEX_DAILY)
    } == {ResearchStatus.CANDIDATE}
    assert {
        mapping.research_status
        for mapping in mappings_for_provider_layer(FreeSourceProvider.BAOSTOCK, AdapterLayer.TRADESTATUS_ISST)
    } == {ResearchStatus.CANDIDATE}
    assert {
        mapping.research_status
        for mapping in mappings_for_provider_layer(FreeSourceProvider.AKSHARE, AdapterLayer.SUSPEND_EVENT)
    } == {ResearchStatus.PARTIAL}


def test_limit_and_formal_capabilities_remain_blocked() -> None:
    blocked = {item.capability: item.status for item in BLOCKED_CAPABILITIES}
    for capability in BLOCKED_MAPPING_CAPABILITIES:
        assert blocked[capability] == ResearchStatus.BLOCKED

    assert not canonical_candidates_for_layer(AdapterLayer.LIMIT_CANDIDATE)
    assert not mappings_by_research_status(ResearchStatus.BLOCKED)


def test_mappings_do_not_declare_formal_generated_outputs() -> None:
    forbidden_fragments = {
        "formal_label",
        "formal_excess_return",
        "formal_adjusted_return",
        "benchmark_return",
        "excess_return",
        "execution_realistic_return",
        "failed_order",
        "partial_fill",
    }
    for mapping in all_provider_mappings():
        haystack = " ".join(
            [
                mapping.raw_field,
                mapping.canonical_candidate,
                mapping.endpoint,
                mapping.notes,
            ]
        )
        assert all(fragment not in haystack for fragment in forbidden_fragments)
