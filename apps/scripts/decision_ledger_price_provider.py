"""Production-grade :class:`PriceProvider` backed by the prism_data gateway.

Phase 5 of Decision Ledger lays out a thin adapter on top of
``packages/prism_data`` so the outcome evaluator can fetch daily bars
without reaching into a vendor SDK or duplicating provider chains.  The
spec is explicit -- "reuse prism_data, do not add a new market data
supplier" -- so this module only routes ``fetch_window(code, start_date,
end_date)`` calls through ``DataGateway.fetch_kline()``.

Failure handling:

* Successful fetch with rows in the window -> filtered list of dicts.
* Successful fetch but the window did not overlap any returned row ->
  empty list.  The evaluator's caller treats that as ``data_issue``
  rather than retrying forever.
* Gateway exception, empty ``GatewayResult.data``, or upstream provider
  ``status != "ok"`` -> :class:`PriceProviderUnavailable`.  The
  evaluator treats that as "skip and try again later" so a transient
  outage cannot freeze a permanent ``data_issue`` event in place.

The module deliberately does not own caching, retries, or provider
fallback -- the gateway already handles those.  We only translate the
gateway's contract into the :class:`PriceProvider` Protocol the
audit-layer evaluator expects.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_PANEL_ROOT = REPO_ROOT / "apps" / "control-panel"
PACKAGES_ROOT = REPO_ROOT / "packages"
for path in (str(REPO_ROOT), str(PACKAGES_ROOT), str(CONTROL_PANEL_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)


from decision_ledger import PriceProviderUnavailable  # type: ignore  # noqa: E402


# How many daily bars to ask the gateway for in a single ``fetch_kline``
# call.  Most outcome windows are bounded by T+5 trading days (about a
# calendar week), but the request key embeds ``start_date`` so the cache
# slot can stretch arbitrarily far back without re-fetching.  120 bars
# gives plenty of headroom for any benchmark / cross-week comparison the
# evaluator may want later.
_DEFAULT_KLINE_COUNT = 120


def _coerce_rows(data: Any) -> list[dict[str, Any]]:
    """Return ``data`` as a list of dicts, dropping any non-dict entries.

    The gateway normalises provider output before returning, but a
    defensive coerce here keeps a bad provider from crashing the
    evaluator with an ``AttributeError`` later on.
    """

    if not data:
        return []
    out: list[dict[str, Any]] = []
    for row in data:
        if isinstance(row, dict):
            out.append(row)
    return out


def _filter_window(rows: list[dict[str, Any]], *, start_date: str, end_date: str) -> list[dict[str, Any]]:
    """Keep only rows whose ``trade_date`` is inside ``[start_date, end_date]``.

    The gateway hands us a wider history than we need (``count`` daily
    bars ending at ``end_date``); the evaluator only consumes the
    decision-window slice, so we trim here to keep callers honest.
    """

    out: list[dict[str, Any]] = []
    for row in rows:
        trade_date = str(row.get("trade_date") or row.get("day") or "")[:10]
        if not trade_date:
            continue
        if start_date <= trade_date <= end_date:
            out.append(dict(row))
    out.sort(key=lambda r: str(r.get("trade_date") or ""))
    return out


class PrismDataPriceProvider:
    """Reuses ``DataGateway.fetch_kline()`` to satisfy outcome evaluation.

    The provider stays stateless: every ``fetch_window`` call hits the
    gateway with a deterministic ``key`` so the underlying cache slot is
    reused by repeated evaluator runs and by other Prism components that
    happen to need the same daily bars.

    Tests inject a fake gateway through the ``gateway`` constructor
    argument; production callers leave it ``None`` to pick up the
    process-wide ``get_data_gateway()`` singleton (lazy import so the
    test runs do not pay for the singleton's provider-discovery cost).
    """

    def __init__(self, *, gateway: Any | None = None, count: int = _DEFAULT_KLINE_COUNT) -> None:
        self.gateway = gateway
        self.count = max(20, int(count))

    def _resolve_gateway(self) -> Any:
        if self.gateway is not None:
            return self.gateway
        # Lazy import: keeps the module import side-effect free for
        # tests that swap in a fake gateway via the constructor.
        from prism_data.service import get_data_gateway  # type: ignore

        return get_data_gateway()

    def fetch_window(
        self,
        code: str,
        *,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        gateway = self._resolve_gateway()
        request_key = f"decision-ledger-{code}-{start_date}-{end_date}"
        try:
            result = gateway.fetch_kline(
                code,
                trade_date=end_date,
                count=self.count,
                key=request_key,
                allow_fallback=True,
            )
        except Exception as exc:  # gateway/provider blew up entirely
            raise PriceProviderUnavailable(
                f"prism_data gateway failed for {code}: {exc}"
            ) from exc

        # GatewayResult carries the provider's status through .provider_result.
        provider_result = getattr(result, "provider_result", None)
        status = getattr(provider_result, "status", None)
        if status is not None and getattr(status, "name", str(status)).lower() != "ok":
            # Treat any non-OK provider status as transient -- a later run
            # may succeed once Sina/AkShare come back online.
            error = getattr(provider_result, "error", None) or "non-ok provider status"
            raise PriceProviderUnavailable(
                f"prism_data gateway returned non-ok for {code}: {error}"
            )

        rows = _coerce_rows(getattr(result, "data", None))
        if not rows:
            raise PriceProviderUnavailable(
                f"prism_data gateway returned no rows for {code}"
            )

        filtered = _filter_window(rows, start_date=start_date, end_date=end_date)
        return filtered


__all__ = ["PrismDataPriceProvider", "PriceProviderUnavailable"]
