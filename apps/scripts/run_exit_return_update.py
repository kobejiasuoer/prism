#!/usr/bin/env python3
"""Scheduled entry point: advance open exit-return records by one trading day.

Wraps exit_return_tracker.update_exits with the prism_data gateway as the
pricing provider (fetch_kline daily bars).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for p in (str(REPO_ROOT / "packages"), str(REPO_ROOT / "apps" / "control-panel")):
    if p not in sys.path:
        sys.path.insert(0, p)

from trading_calendar import most_recent_trading_day  # noqa: E402
from screener.exit_return_tracker import update_exits, DEFAULT_STORE  # noqa: E402


def _gateway_pricing(trade_date: str):
    """Return a pricing_provider(code) -> {trade_date: close} backed by fetch_kline.

    Uses get_data_gateway() (the canonical accessor); falls back to an empty
    provider only if the gateway module itself is unavailable, so a transient
    provider error surfaces as inconclusive rather than being masked.
    """
    try:
        from prism_data.service import get_data_gateway  # type: ignore
        gateway = get_data_gateway()
    except Exception:
        return lambda code: {}

    def provider(code: str) -> dict:
        try:
            result = gateway.fetch_kline(
                code, trade_date=trade_date, period="daily", count=20,
                key=f"exit-return-{code}", allow_fallback=True,
            )
        except Exception:
            return {}
        provider_result = getattr(result, "provider_result", None)
        status = getattr(provider_result, "status", None)
        if status is not None and getattr(status, "name", str(status)).lower() != "ok":
            return {}
        out: dict[str, float] = {}
        for bar in (getattr(result, "data", None) or []):
            d = str(bar.get("trade_date", ""))[:10]
            c = bar.get("close")
            if d and c is not None:
                out[d] = c
        return out

    return provider


def main() -> int:
    trade_date = str(most_recent_trading_day())
    provider = _gateway_pricing(trade_date)
    result = update_exits(store=DEFAULT_STORE, pricing_provider=provider, as_of_date=trade_date)
    print(f"exit_return_update as_of={trade_date} advanced={result['advanced']} settled={len(result['settled'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
