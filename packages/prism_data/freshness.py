"""Freshness policies for raw datasets and pipeline manifests."""

from __future__ import annotations

from datetime import datetime
from typing import Any


FRESHNESS_ORDER = {
    "fresh": 0,
    "stale": 1,
    "expired": 2,
}


def _parse_datetime(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def compute_freshness_status(
    *,
    fetched_at: str | datetime | None,
    ttl_seconds: int,
    trade_date: str,
    expected_trade_date: str,
    now: datetime | None = None,
) -> str:
    current = now or datetime.now()
    fetched_dt = _parse_datetime(fetched_at)
    if fetched_dt is None:
        return "expired"
    if trade_date != expected_trade_date:
        return "stale"
    age_seconds = max((current - fetched_dt).total_seconds(), 0)
    if age_seconds <= ttl_seconds:
        return "fresh"
    if age_seconds <= ttl_seconds * 2:
        return "stale"
    return "expired"


def update_manifest_freshness(
    manifest: dict[str, Any],
    expected_trade_date: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    status = compute_freshness_status(
        fetched_at=manifest.get("asof") or manifest.get("fetched_at"),
        ttl_seconds=int(manifest.get("ttl_seconds") or 0),
        trade_date=str(manifest.get("trade_date") or ""),
        expected_trade_date=expected_trade_date,
        now=now,
    )
    manifest["freshness_status"] = status
    return manifest


def worst_freshness_status(statuses: list[str]) -> str:
    if not statuses:
        return "expired"
    return max(statuses, key=lambda item: FRESHNESS_ORDER.get(item, 99))


__all__ = [
    "FRESHNESS_ORDER",
    "compute_freshness_status",
    "update_manifest_freshness",
    "worst_freshness_status",
]
