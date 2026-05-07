"""A-share trading calendar with explicit holiday awareness.

Why this exists
---------------
``readiness.py`` previously treated every weekday as a trading day, with a
flagged TODO acknowledging the risk: on the first session after a multi-day
holiday (Spring Festival, Labor Day, National Day, etc.) the *expected* trade
date for "today" would still resolve to the calendar weekday even when the
A-share market had been closed for several days.  Combined with stale
artifacts that happened to share that calendar weekday, the operator could
see a misleadingly clean readiness state.

This module fail-closes that gap.  It ships a small static list of A-share
non-trading days for the publish horizon currently approved by the China
exchanges.  Anything past that horizon is treated as ``unknown`` — readiness
must downgrade to ``shadow_only`` rather than asserting a live-ready state on
a day we cannot prove is open.

Holiday policy (China A-share)
------------------------------
The China Securities Regulatory Commission publishes the next-year holiday
schedule late in the prior calendar year. The lists below cover the holidays
the market is currently inside of plus the next published horizon.  When
adding a year, also bump ``CALENDAR_HORIZON`` so anything past the horizon is
treated as unknown.

Holidays included only count whole days when the market was closed; partial
trading days are NOT included.  Weekends are handled separately.

Sources: CSRC / SSE & SZSE annual notices.  Update by hand at the start of
each new calendar year — if the user adds an akshare integration later we can
swap this for ``ak.tool_trade_date_hist_sina`` and keep the static list as a
fallback.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Iterable


__all__ = [
    "is_trading_day",
    "most_recent_trading_day",
    "next_trading_day",
    "calendar_status",
    "CALENDAR_HORIZON",
    "STATIC_HOLIDAYS",
]


# Inclusive last date this calendar is considered authoritative.
# Anything strictly past this date returns ``status="unknown"`` so readiness
# can fail closed.  Bump this when refreshing the holiday list.
CALENDAR_HORIZON: date = date(2026, 12, 31)


def _d(text: str) -> date:
    return datetime.strptime(text, "%Y-%m-%d").date()


# A-share non-trading days (weekday holidays only — weekends handled
# separately).  Keep grouped per holiday for legibility.
STATIC_HOLIDAYS: frozenset[date] = frozenset(
    _d(s)
    for s in (
        # 2025 — historical, kept so back-test / replay sessions are correct
        "2025-01-01",                                                              # 元旦
        "2025-01-28", "2025-01-29", "2025-01-30", "2025-01-31", "2025-02-03", "2025-02-04",  # 春节
        "2025-04-04",                                                              # 清明
        "2025-05-01", "2025-05-02", "2025-05-05",                                  # 劳动节
        "2025-06-02",                                                              # 端午
        "2025-10-01", "2025-10-02", "2025-10-03", "2025-10-06", "2025-10-07", "2025-10-08",  # 国庆 / 中秋
        # 2026 — published schedule
        "2026-01-01", "2026-01-02",                                                # 元旦
        "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20", "2026-02-23", "2026-02-24",  # 春节
        "2026-04-06",                                                              # 清明
        "2026-05-01", "2026-05-04", "2026-05-05",                                  # 劳动节
        "2026-06-19",                                                              # 端午
        "2026-09-25",                                                              # 中秋
        "2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08",  # 国庆
    )
)


def _coerce_date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return _d(str(value)[:10])


def _override_holidays() -> Iterable[date]:
    """Allow tests / replay sessions to inject extra non-trading days.

    Format: comma-separated YYYY-MM-DD via ``PRISM_TEST_TRADING_HOLIDAYS``.
    """

    text = os.environ.get("PRISM_TEST_TRADING_HOLIDAYS", "").strip()
    if not text:
        return ()
    out: list[date] = []
    for chunk in text.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            out.append(_d(chunk))
        except ValueError:
            continue
    return out


def _override_horizon() -> date | None:
    text = os.environ.get("PRISM_TEST_CALENDAR_HORIZON", "").strip()
    if not text:
        return None
    try:
        return _d(text)
    except ValueError:
        return None


def calendar_status(value: date | datetime | str) -> dict:
    """Classify a date as trading / weekend / holiday / unknown.

    Returns a dict suitable for embedding in readiness payloads:
    ``{"date": "YYYY-MM-DD", "status": "trading"|"weekend"|"holiday"|"unknown",
       "reason": "..."}``.
    """

    target = _coerce_date(value)
    horizon = _override_horizon() or CALENDAR_HORIZON
    if target > horizon:
        return {
            "date": target.strftime("%Y-%m-%d"),
            "status": "unknown",
            "reason": f"calendar coverage ends {horizon.strftime('%Y-%m-%d')}",
        }
    if target.weekday() >= 5:
        return {
            "date": target.strftime("%Y-%m-%d"),
            "status": "weekend",
            "reason": "weekend",
        }
    overrides = set(_override_holidays())
    if target in STATIC_HOLIDAYS or target in overrides:
        return {
            "date": target.strftime("%Y-%m-%d"),
            "status": "holiday",
            "reason": "exchange holiday",
        }
    return {
        "date": target.strftime("%Y-%m-%d"),
        "status": "trading",
        "reason": "weekday and not on holiday list",
    }


def is_trading_day(value: date | datetime | str) -> bool:
    return calendar_status(value)["status"] == "trading"


def most_recent_trading_day(now: date | datetime | str | None = None) -> date:
    """Walk backward from ``now`` until a known trading day is found.

    If ``now`` is itself a trading day, returns ``now``.  When the cursor
    crosses the calendar horizon we return the cursor anyway — readiness
    will surface ``unknown`` separately, so the helper itself is total.
    """

    cursor = _coerce_date(now or datetime.now())
    safety = 30  # at most a month back; covers Spring Festival worst case
    while safety > 0:
        if is_trading_day(cursor):
            return cursor
        cursor = cursor - timedelta(days=1)
        safety -= 1
    return cursor


def next_trading_day(value: date | datetime | str | None = None) -> date:
    """Walk forward from ``value`` until a known trading day is found."""

    cursor = _coerce_date(value or datetime.now())
    safety = 30
    while safety > 0:
        if is_trading_day(cursor):
            return cursor
        cursor = cursor + timedelta(days=1)
        safety -= 1
    return cursor
