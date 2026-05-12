"""Canonical dataset shapes and loaders.

Defines the expected structure for each canonical dataset type.
These are the shapes that business logic (watchlist, screener, readiness)
should consume.
"""

from __future__ import annotations

from typing import Any, TypedDict


class QuoteSnapshot(TypedDict, total=False):
    """Single stock quote snapshot."""

    code: str
    name: str
    price: float
    change: float
    change_pct: float
    volume: int
    amount: float
    high: float
    low: float
    open: float
    prev_close: float
    timestamp: str


class DailyBar(TypedDict, total=False):
    """Single daily K-line bar."""

    code: str
    trade_date: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    amount: float
    change_pct: float


class CapitalFlow(TypedDict, total=False):
    """Daily capital flow for a stock."""

    code: str
    trade_date: str
    main_net_inflow: float
    main_net_inflow_pct: float
    super_large_net_inflow: float
    large_net_inflow: float
    medium_net_inflow: float
    small_net_inflow: float


class Fundamentals(TypedDict, total=False):
    """Fundamental metrics snapshot."""

    code: str
    name: str
    pe_ttm: float
    pb: float
    market_cap: float
    circulating_market_cap: float
    industry: str
    sector: str


class Announcement(TypedDict, total=False):
    """Company announcement."""

    code: str
    title: str
    publish_date: str
    url: str
    summary: str


class NewsItem(TypedDict, total=False):
    """News article."""

    code: str
    title: str
    publish_time: str
    source: str
    url: str
    summary: str


class StockSearchResult(TypedDict, total=False):
    """Stock search result."""

    code: str
    name: str
    market: str
    type: str


# Type aliases for dataset collections
QuotesDataset = list[QuoteSnapshot]
BarsDataset = list[DailyBar]
CapitalFlowDataset = list[CapitalFlow]
FundamentalsDataset = list[Fundamentals]
AnnouncementsDataset = list[Announcement]
NewsDataset = list[NewsItem]
SearchResultsDataset = list[StockSearchResult]


def validate_quotes_dataset(data: Any) -> bool:
    """Validate that data conforms to QuotesDataset shape."""
    if not isinstance(data, list):
        return False
    if not data:
        return True
    # Check first item has required fields
    first = data[0]
    return isinstance(first, dict) and "code" in first and "price" in first


def validate_bars_dataset(data: Any) -> bool:
    """Validate that data conforms to BarsDataset shape."""
    if not isinstance(data, list):
        return False
    if not data:
        return True
    first = data[0]
    return (
        isinstance(first, dict)
        and "code" in first
        and "trade_date" in first
        and "close" in first
    )


__all__ = [
    "QuoteSnapshot",
    "DailyBar",
    "CapitalFlow",
    "Fundamentals",
    "Announcement",
    "NewsItem",
    "StockSearchResult",
    "QuotesDataset",
    "BarsDataset",
    "CapitalFlowDataset",
    "FundamentalsDataset",
    "AnnouncementsDataset",
    "NewsDataset",
    "SearchResultsDataset",
    "validate_quotes_dataset",
    "validate_bars_dataset",
]
