from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .manifest import AdapterLayer, FreeSourceProvider


class ResearchStatus(str, Enum):
    AVAILABLE = "available"
    RESEARCH_ONLY = "research_only"
    CANDIDATE = "candidate"
    PARTIAL = "partial"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class FieldContract:
    provider: FreeSourceProvider
    adapter_layer: AdapterLayer
    raw_field: str
    canonical_candidate: str
    value_type: str
    unit: str
    pit_asof_status: str
    research_status: ResearchStatus


@dataclass(frozen=True)
class BlockedCapability:
    capability: str
    status: ResearchStatus
    reason: str


FIELD_CONTRACTS: tuple[FieldContract, ...] = (
    FieldContract(
        FreeSourceProvider.BAOSTOCK,
        AdapterLayer.CALENDAR,
        "calendar_date",
        "trade_calendar.date",
        "date_string",
        "calendar_day",
        "as_collected_only",
        ResearchStatus.AVAILABLE,
    ),
    FieldContract(
        FreeSourceProvider.BAOSTOCK,
        AdapterLayer.CALENDAR,
        "is_trading_day",
        "trade_calendar.is_open",
        "boolean_like_string",
        "flag",
        "as_collected_only",
        ResearchStatus.AVAILABLE,
    ),
    FieldContract(
        FreeSourceProvider.BAOSTOCK,
        AdapterLayer.STOCK_BASIC,
        "ipoDate",
        "security.list_date",
        "date_string",
        "calendar_day",
        "as_collected_only",
        ResearchStatus.AVAILABLE,
    ),
    FieldContract(
        FreeSourceProvider.BAOSTOCK,
        AdapterLayer.RAW_DAILY,
        "open/high/low/close/preclose/volume/amount",
        "daily.ohlcv",
        "decimal_string",
        "provider_unit",
        "pit_weak",
        ResearchStatus.AVAILABLE,
    ),
    FieldContract(
        FreeSourceProvider.AKSHARE,
        AdapterLayer.RAW_DAILY,
        "开盘/最高/最低/收盘/成交量/成交额",
        "daily.ohlcv",
        "numeric",
        "provider_unit",
        "pit_weak",
        ResearchStatus.CANDIDATE,
    ),
    FieldContract(
        FreeSourceProvider.BAOSTOCK,
        AdapterLayer.QFQ_CANDIDATE,
        "adjustflag + qfq open/high/low/close",
        "adjusted_daily.qfq_ohlc",
        "decimal_string",
        "adjusted_price",
        "not_pit_ready",
        ResearchStatus.RESEARCH_ONLY,
    ),
    FieldContract(
        FreeSourceProvider.AKSHARE,
        AdapterLayer.QFQ_CANDIDATE,
        'adjust="qfq" + qfq 开盘/最高/最低/收盘',
        "adjusted_daily.qfq_ohlc",
        "numeric",
        "adjusted_price",
        "not_pit_ready",
        ResearchStatus.RESEARCH_ONLY,
    ),
    FieldContract(
        FreeSourceProvider.BAOSTOCK,
        AdapterLayer.INDEX_DAILY,
        "date/code/open/high/low/close/preclose/volume/amount",
        "index_daily.ohlcv",
        "decimal_string",
        "index_point_or_provider_unit",
        "pit_weak",
        ResearchStatus.CANDIDATE,
    ),
    FieldContract(
        FreeSourceProvider.AKSHARE,
        AdapterLayer.INDEX_DAILY,
        "日期/指数代码/开盘/最高/最低/收盘/成交量/成交金额",
        "index_daily.ohlcv",
        "numeric",
        "index_point_or_provider_unit",
        "pit_weak",
        ResearchStatus.CANDIDATE,
    ),
    FieldContract(
        FreeSourceProvider.BAOSTOCK,
        AdapterLayer.TRADESTATUS_ISST,
        "tradestatus",
        "execution_candidate.trade_status",
        "provider_enum_string",
        "flag",
        "pit_weak",
        ResearchStatus.CANDIDATE,
    ),
    FieldContract(
        FreeSourceProvider.BAOSTOCK,
        AdapterLayer.TRADESTATUS_ISST,
        "isST",
        "execution_candidate.is_st",
        "provider_enum_string",
        "flag",
        "pit_weak",
        ResearchStatus.CANDIDATE,
    ),
    FieldContract(
        FreeSourceProvider.AKSHARE,
        AdapterLayer.SUSPEND_EVENT,
        "代码/停牌时间/停牌截止时间/预计复牌时间/停牌原因",
        "suspend_event",
        "event_metadata",
        "event_only",
        "as_collected_only",
        ResearchStatus.PARTIAL,
    ),
    FieldContract(
        FreeSourceProvider.BAOSTOCK,
        AdapterLayer.LIMIT_CANDIDATE,
        "up_limit/down_limit",
        "execution_limit.up_limit_down_limit",
        "not_available",
        "price",
        "unknown",
        ResearchStatus.BLOCKED,
    ),
)

BLOCKED_CAPABILITIES: tuple[BlockedCapability, ...] = (
    BlockedCapability("formal_adjusted_return", ResearchStatus.BLOCKED, "qfq lacks independent adj_factor and as-of revision"),
    BlockedCapability("formal_excess_return", ResearchStatus.BLOCKED, "benchmark fields are candidates only"),
    BlockedCapability("formal_labels", ResearchStatus.BLOCKED, "calendar, price, benchmark, execution, PIT, and authorization are not formal-ready"),
    BlockedCapability("execution_realistic_backtest", ResearchStatus.BLOCKED, "no real order, queue, failed order, partial fill, or limit price source"),
    BlockedCapability("limit_up_down_price", ResearchStatus.BLOCKED, "historical full-market up/down limit price not verified"),
    BlockedCapability("failed_order", ResearchStatus.BLOCKED, "no broker or OMS order event source"),
    BlockedCapability("partial_fill", ResearchStatus.BLOCKED, "daily OHLCV cannot prove partial fills"),
)


def contracts_for_layer(adapter_layer: AdapterLayer) -> tuple[FieldContract, ...]:
    return tuple(contract for contract in FIELD_CONTRACTS if contract.adapter_layer == adapter_layer)
