"""Provider contracts and result types for Prism data ingress."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol


class ProviderRole(str, Enum):
    PRIMARY = "primary"
    FALLBACK = "fallback"
    RESEARCH_ONLY = "research_only"


class DatasetStatus(str, Enum):
    OK = "ok"
    PARTIAL = "partial"
    FAILED = "failed"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


@dataclass
class ProviderResult:
    """Normalized provider response before repository persistence."""

    status: DatasetStatus
    data: Any
    provider: str
    provider_role: ProviderRole
    dataset: str
    trade_date: str
    fetched_at: datetime
    asof: datetime | None = None
    ttl_seconds: int = 900
    error: str | None = None
    source_endpoint: str = "redacted"
    params_hash: str = ""
    payload_hash: str = ""
    row_count: int = 0
    quality_flags: list[str] = field(default_factory=list)
    license_scope: str = "internal_research"
    live_small_allowed: bool = True
    request_key: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


class DataProvider(Protocol):
    """Protocol implemented by real provider adapters."""

    def fetch_quote(self, code: str, **kwargs: Any) -> ProviderResult:
        ...

    def fetch_quotes_batch(self, codes: list[str], **kwargs: Any) -> ProviderResult:
        ...

    def fetch_kline(
        self,
        code: str,
        period: str = "daily",
        count: int = 120,
        **kwargs: Any,
    ) -> ProviderResult:
        ...

    def fetch_capital_flow(
        self,
        code: str,
        trade_date: str | None = None,
        **kwargs: Any,
    ) -> ProviderResult:
        ...

    def fetch_capital_flow_batch(self, codes: list[str], **kwargs: Any) -> ProviderResult:
        ...

    def fetch_fundamentals(self, code: str, **kwargs: Any) -> ProviderResult:
        ...

    def fetch_fundamentals_batch(self, codes: list[str], **kwargs: Any) -> ProviderResult:
        ...

    def fetch_announcements(
        self,
        code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: Any,
    ) -> ProviderResult:
        ...

    def fetch_news(self, code: str, count: int = 10, **kwargs: Any) -> ProviderResult:
        ...

    def search_stock(self, query: str, **kwargs: Any) -> ProviderResult:
        ...

    def fetch_market_pool(self, node: str, **kwargs: Any) -> ProviderResult:
        ...

    def fetch_index_constituents(self, symbol: str, **kwargs: Any) -> ProviderResult:
        ...

    def fetch_sector_snapshot(self, sector_code: str, **kwargs: Any) -> ProviderResult:
        ...


__all__ = [
    "DataProvider",
    "DatasetStatus",
    "ProviderResult",
    "ProviderRole",
]
