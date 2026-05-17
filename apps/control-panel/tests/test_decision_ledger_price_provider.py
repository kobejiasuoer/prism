"""Tests for the prism_data-backed Decision Ledger price provider.

The provider sits between ``decision_ledger.evaluate_decision_outcome``
and ``packages/prism_data.DataGateway.fetch_kline``.  The contract is:

* Gateway returns rows -> filtered window list, sorted by trade_date.
* Gateway raises -> ``PriceProviderUnavailable`` (transient, retry).
* Gateway returns empty data or non-OK status -> ``PriceProviderUnavailable``.
* Gateway returns rows that do not overlap the window -> empty list
  (terminal "we know there is no data here").

We hand the provider a fake gateway in every test so no real network or
on-disk cache is touched.
"""

from __future__ import annotations

import os
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[3]
CONTROL_PANEL_ROOT = REPO_ROOT / "apps" / "control-panel"
SCRIPTS_ROOT = REPO_ROOT / "apps" / "scripts"
PACKAGES_ROOT = REPO_ROOT / "packages"
for path in (str(CONTROL_PANEL_ROOT), str(SCRIPTS_ROOT), str(PACKAGES_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)


@dataclass
class _FakeStatus:
    name: str

    def __str__(self) -> str:
        return self.name


@dataclass
class _FakeProviderResult:
    status: _FakeStatus
    error: str | None = None


@dataclass
class _FakeGatewayResult:
    data: Any
    provider_result: _FakeProviderResult


class _RecordingGateway:
    """Records every fetch_kline call and returns a queued response.

    Each test sets ``self.responses`` either to a list of pre-built
    GatewayResult objects (one per call) or to a single object.  The
    gateway raises if the test fixture wants to exercise the unavailable
    path.
    """

    def __init__(
        self,
        responses: list[Any] | Any | None = None,
        raise_on_call: bool = False,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self._responses = responses if isinstance(responses, list) else [responses]
        self._index = 0
        self.raise_on_call = raise_on_call

    def fetch_kline(self, code: str, **kwargs: Any) -> Any:
        self.calls.append({"code": code, **kwargs})
        if self.raise_on_call:
            raise RuntimeError("gateway boom")
        if self._index >= len(self._responses):
            return self._responses[-1]
        response = self._responses[self._index]
        self._index += 1
        if isinstance(response, Exception):
            raise response
        return response


def _row(date: str, close: float, *, high: float | None = None, low: float | None = None) -> dict:
    return {
        "trade_date": date,
        "day": date,
        "open": close,
        "high": high if high is not None else close + 0.1,
        "low": low if low is not None else close - 0.1,
        "close": close,
        "volume": 1_000_000.0,
    }


class PrismDataPriceProviderTests(unittest.TestCase):
    """Direct unit tests for the gateway adapter."""

    def setUp(self) -> None:
        # The provider module imports PriceProviderUnavailable from
        # decision_ledger; clear the module cache so any earlier test's
        # env overrides do not leak in.
        sys.modules.pop("decision_ledger_price_provider", None)
        sys.modules.pop("decision_ledger_providers", None)
        sys.modules.pop("decision_ledger", None)
        import decision_ledger  # type: ignore
        import decision_ledger_price_provider  # type: ignore

        self.ledger = decision_ledger
        self.module = decision_ledger_price_provider
        self.PrismDataPriceProvider = decision_ledger_price_provider.PrismDataPriceProvider

    def test_returns_filtered_rows_for_window(self) -> None:
        gateway = _RecordingGateway(
            responses=_FakeGatewayResult(
                data=[
                    _row("2026-05-12", 9.0),
                    _row("2026-05-15", 10.0),
                    _row("2026-05-18", 10.5),
                    _row("2026-05-19", 10.6),
                    _row("2026-05-22", 11.0),  # outside the window
                ],
                provider_result=_FakeProviderResult(status=_FakeStatus("ok")),
            ),
        )
        provider = self.PrismDataPriceProvider(gateway=gateway)
        rows = provider.fetch_window(
            "sh600690", start_date="2026-05-15", end_date="2026-05-19",
        )
        dates = [row["trade_date"] for row in rows]
        self.assertEqual(dates, ["2026-05-15", "2026-05-18", "2026-05-19"])

        # The provider must hand the gateway a stable request_key so the
        # underlying cache slot is shared across reruns.
        call = gateway.calls[0]
        self.assertEqual(call["code"], "sh600690")
        self.assertEqual(call["trade_date"], "2026-05-19")
        self.assertTrue(call["allow_fallback"])
        self.assertIn("decision-ledger-sh600690-2026-05-15-2026-05-19", call["key"])

    def test_returns_empty_list_when_no_rows_overlap_window(self) -> None:
        gateway = _RecordingGateway(
            responses=_FakeGatewayResult(
                data=[_row("2026-04-01", 9.0)],
                provider_result=_FakeProviderResult(status=_FakeStatus("ok")),
            ),
        )
        provider = self.PrismDataPriceProvider(gateway=gateway)
        out = provider.fetch_window(
            "sh600690", start_date="2026-05-15", end_date="2026-05-19",
        )
        # Non-overlap is a *terminal* miss -- the gateway succeeded but
        # the window has no data.  Empty list is the right answer; the
        # evaluator interprets that as data_issue.
        self.assertEqual(out, [])

    def test_gateway_exception_raises_unavailable(self) -> None:
        gateway = _RecordingGateway(raise_on_call=True)
        provider = self.PrismDataPriceProvider(gateway=gateway)
        with self.assertRaises(self.ledger.PriceProviderUnavailable):
            provider.fetch_window(
                "sh600690", start_date="2026-05-15", end_date="2026-05-19",
            )

    def test_non_ok_provider_status_raises_unavailable(self) -> None:
        gateway = _RecordingGateway(
            responses=_FakeGatewayResult(
                data=[],
                provider_result=_FakeProviderResult(
                    status=_FakeStatus("error"), error="sina kline missing",
                ),
            ),
        )
        provider = self.PrismDataPriceProvider(gateway=gateway)
        with self.assertRaises(self.ledger.PriceProviderUnavailable):
            provider.fetch_window(
                "sh600690", start_date="2026-05-15", end_date="2026-05-19",
            )

    def test_empty_data_raises_unavailable(self) -> None:
        gateway = _RecordingGateway(
            responses=_FakeGatewayResult(
                data=[],
                provider_result=_FakeProviderResult(status=_FakeStatus("ok")),
            ),
        )
        provider = self.PrismDataPriceProvider(gateway=gateway)
        with self.assertRaises(self.ledger.PriceProviderUnavailable):
            provider.fetch_window(
                "sh600690", start_date="2026-05-15", end_date="2026-05-19",
            )


if __name__ == "__main__":
    unittest.main()
