from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict


ArtifactType = Literal[
    "ai_screening_history",
    "command_brief",
    "evaluation_scorecard",
    "midday_verification",
    "price_kline_cache",
    "research_backfill_report",
    "scan_history",
    "watchlist_snapshot",
]


class BaselineArtifact(TypedDict):
    artifact_path: str
    artifact_type: ArtifactType | str
    trade_date: str | None
    generated_at: str | None
    source_lane: str
    sha256: str
    config_checksum: str
    code_revision: str
    notes: str


class QuantBaselineManifest(TypedDict):
    schema_version: str
    generated_at: str
    config_path: str
    config_checksum: str
    code_revision: dict[str, Any]
    artifact_count: int
    artifacts: list[BaselineArtifact]


class FieldCoverage(TypedDict):
    field: str
    artifact_coverage_pct: float
    record_exact_coverage_pct: float
    record_semantic_coverage_pct: float
    p0_status: Literal["candidate", "research_only", "blocked"]
    notes: NotRequired[str]
