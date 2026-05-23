"""Phase 5 -- production PriceProvider + Unavailable-vs-missing tests.

Phase 4 shipped a Protocol-only PriceProvider plus a fixture-based
``FakePriceProvider``.  Phase 5 needs two extra things before we can
wire a real provider into the CLI / scheduler later:

1. A way to tell the evaluator "the data source is temporarily down --
   skip this window, do NOT write a permanent ``data_issue`` event".
   This is the new :class:`PriceProviderUnavailable` exception.
2. A local-cache-backed provider that reuses
   ``data/prism_data/datasets/bars.daily/{trade_date}/{code}.json``
   without going to the network.  It must distinguish "cache stale /
   not yet warmed" (transient -> raise unavailable) from "we have the
   data but it's empty for this window" (terminal -> return ``[]``).

The cache provider lives in a new module so the audit layer
(``decision_ledger.py``) stays decoupled from the data layer.  Tests
import it via the public re-export off ``decision_ledger`` so the
import path matches what ``app.py`` and the CLI will use.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


CONTROL_PANEL_ROOT = Path(__file__).resolve().parents[1]
if str(CONTROL_PANEL_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROL_PANEL_ROOT))


def _sample_decision_inputs(**overrides):
    base = {
        "trade_date": "2026-05-15",
        "code": "sh600690",
        "name": "海尔智家",
        "lane": "watchlist",
        "surface": "today_action_queue",
        "action_key": "watchlist:600690",
        "source_label": "自选股链路",
        "action": "trial_buy",
        "action_label": "轻仓试错",
        "main_conclusion": "形态确认，轻仓试错",
        "expected_trade_date": "2026-05-15",
        "data_trade_date": "2026-05-15",
        "readiness_mode": "live_ready",
        "readiness_ready": True,
    }
    base.update(overrides)
    return base


class _UnavailableProvider:
    """Provider that always raises PriceProviderUnavailable (transient)."""

    def __init__(self, exc_factory):
        self._exc_factory = exc_factory
        self.calls: list[tuple] = []

    def fetch_window(self, code, *, start_date, end_date):
        self.calls.append((code, start_date, end_date))
        raise self._exc_factory(f"transient outage for {code}")


class _SelectiveUnavailableProvider:
    """Provider that returns valid stock rows but raises for the benchmark.

    Lets us verify the evaluator degrades benchmark-fetch failures
    cleanly without bubbling them out -- benchmark is best-effort, the
    primary fetch is the load-bearing call.
    """

    def __init__(self, stock_rows, benchmark_code, exc_factory):
        self._rows = stock_rows
        self._benchmark_code = benchmark_code
        self._exc_factory = exc_factory

    def fetch_window(self, code, *, start_date, end_date):
        if code == self._benchmark_code:
            raise self._exc_factory(f"benchmark outage for {code}")
        return [
            row for row in self._rows
            if start_date <= row["trade_date"] <= end_date
        ]


# ===========================================================================
# Evaluator: PriceProviderUnavailable -> skipped (not data_issue).
# ===========================================================================


class EvaluatorProviderUnavailableTests(unittest.TestCase):
    """The evaluator must NOT bury a transient provider outage as data_issue."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ledger_root = Path(self._tmp.name) / "decision_ledger"
        self._env = mock.patch.dict(
            os.environ,
            {"PRISM_DECISION_LEDGER_PATH": str(self.ledger_root)},
        )
        self._env.start()
        self.addCleanup(self._env.stop)

        sys.modules.pop("decision_ledger", None)
        import decision_ledger  # type: ignore

        self.ledger = decision_ledger
        self.decision = self.ledger.upsert_decision(
            self.ledger.build_decision_record(**_sample_decision_inputs())
        )

    def test_price_provider_unavailable_is_runtime_error_subclass(self) -> None:
        # The exception must be importable from decision_ledger and inherit
        # from RuntimeError so generic ``except RuntimeError`` clauses in
        # caller code still see it.
        self.assertTrue(hasattr(self.ledger, "PriceProviderUnavailable"))
        self.assertTrue(
            issubclass(self.ledger.PriceProviderUnavailable, RuntimeError)
        )

    def test_evaluate_decision_outcome_does_not_persist_when_provider_unavailable(self) -> None:
        # When the provider raises PriceProviderUnavailable, the
        # evaluator must propagate it (so the orchestrator can count it
        # as a skip).  Phase 4's blanket ``except Exception -> data_issue``
        # would otherwise turn a transient outage into a permanent
        # data_issue event.
        provider = _UnavailableProvider(self.ledger.PriceProviderUnavailable)
        with self.assertRaises(self.ledger.PriceProviderUnavailable):
            self.ledger.evaluate_decision_outcome(
                self.decision,
                window="T+1",
                price_provider=provider,
            )

    def test_orchestrator_counts_unavailable_separately_from_data_issue(self) -> None:
        provider = _UnavailableProvider(self.ledger.PriceProviderUnavailable)
        summary = self.ledger.evaluate_due_outcomes(
            as_of_date="2026-05-20",
            price_provider=provider,
        )
        # T+1 and T+3 are due on 2026-05-20 but both saw the provider
        # raise unavailable -- nothing should be written, and the
        # data_issue counter must stay at zero.
        self.assertEqual(summary["evaluated"], 0)
        self.assertEqual(summary["data_issue"], 0)
        self.assertGreaterEqual(summary["skipped_provider_unavailable"], 2)
        stored = self.ledger.load_decision(self.decision["decision_id"])
        self.assertEqual(stored["outcome_events"], [])

    def test_benchmark_unavailable_degrades_to_absolute_classification(self) -> None:
        # The benchmark fetch is best-effort: if 000300 is transiently
        # down but the primary stock fetch works, classification must
        # fall back to the absolute thresholds instead of leaking
        # PriceProviderUnavailable up to the orchestrator.
        rows = [
            {"trade_date": "2026-05-15", "open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0},
            {"trade_date": "2026-05-18", "open": 10.0, "high": 10.6, "low": 9.9, "close": 10.5},
        ]
        provider = _SelectiveUnavailableProvider(
            stock_rows=rows,
            benchmark_code="000300",
            exc_factory=self.ledger.PriceProviderUnavailable,
        )
        event = self.ledger.evaluate_decision_outcome(
            self.decision,
            window="T+1",
            price_provider=provider,
        )
        market = event["market_data"]
        self.assertIsNone(market["benchmark_return_pct"])
        self.assertIsNone(market["relative_return_pct"])
        # +5% absolute -> validated under the no-benchmark threshold.
        self.assertEqual(event["classification"]["label"], "validated")

    def test_orchestrator_summary_has_skipped_provider_unavailable_field(self) -> None:
        # Even without unavailable signals, the summary shape must
        # always include the new key so callers can rely on it.
        summary = self.ledger.evaluate_due_outcomes(
            as_of_date="2026-05-20",
            price_provider=None,
        )
        self.assertIn("skipped_provider_unavailable", summary)


# ===========================================================================
# PrismCachePriceProvider: read-only access to bars.daily/ artifacts.
# ===========================================================================


class _CacheFixture:
    """Build a fake bars.daily cache tree for the provider tests."""

    def __init__(self, root: Path) -> None:
        self.root = root  # the PRISM data root (parent of "prism_data/...")

    def write_bars(self, *, cache_date: str, code_no_prefix: str, rows: list[dict]) -> Path:
        cache_dir = self.root / "prism_data" / "datasets" / "bars.daily" / cache_date
        cache_dir.mkdir(parents=True, exist_ok=True)
        path = cache_dir / f"{code_no_prefix}.json"
        path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        return path

    def write_corrupt(self, *, cache_date: str, code_no_prefix: str) -> Path:
        cache_dir = self.root / "prism_data" / "datasets" / "bars.daily" / cache_date
        cache_dir.mkdir(parents=True, exist_ok=True)
        path = cache_dir / f"{code_no_prefix}.json"
        path.write_text("{not valid json", encoding="utf-8")
        return path


class PrismCachePriceProviderTests(unittest.TestCase):
    """Local-cache-only provider sourced from ``data/prism_data/datasets/``."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data_root = Path(self._tmp.name) / "data"
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.fixture = _CacheFixture(self.data_root)

        self._env = mock.patch.dict(
            os.environ,
            {"PRISM_DATA_ROOT": str(self.data_root)},
        )
        self._env.start()
        self.addCleanup(self._env.stop)

        sys.modules.pop("decision_ledger", None)
        sys.modules.pop("decision_ledger_providers", None)
        import decision_ledger  # type: ignore

        self.ledger = decision_ledger
        self.PrismCachePriceProvider = decision_ledger.PrismCachePriceProvider
        self.PriceProviderUnavailable = decision_ledger.PriceProviderUnavailable

    def _make_rows(self, code: str, dates: list[tuple[str, float]]) -> list[dict]:
        return [
            {
                "code": code,
                "trade_date": d,
                "day": d,
                "open": close,
                "high": close + 0.1,
                "low": close - 0.1,
                "close": close,
                "volume": 1_000_000,
            }
            for d, close in dates
        ]

    def test_cache_hit_returns_rows_inside_window(self) -> None:
        rows = self._make_rows(
            "sh600690",
            [("2026-05-15", 10.0), ("2026-05-18", 10.4), ("2026-05-19", 10.6)],
        )
        self.fixture.write_bars(
            cache_date="2026-05-19", code_no_prefix="600690", rows=rows,
        )
        provider = self.PrismCachePriceProvider(data_root=self.data_root)
        out = provider.fetch_window(
            "sh600690", start_date="2026-05-15", end_date="2026-05-18",
        )
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["trade_date"], "2026-05-15")
        self.assertEqual(out[1]["trade_date"], "2026-05-18")

    def test_plain_code_normalizes_to_cache_file(self) -> None:
        # Cache files are named by plain code (600690.json); accept the
        # plain form too so a caller can hand us either.
        rows = self._make_rows("sh600690", [("2026-05-15", 10.0)])
        self.fixture.write_bars(
            cache_date="2026-05-15", code_no_prefix="600690", rows=rows,
        )
        provider = self.PrismCachePriceProvider(data_root=self.data_root)
        out = provider.fetch_window(
            "600690", start_date="2026-05-15", end_date="2026-05-15",
        )
        self.assertEqual(len(out), 1)

    def test_benchmark_index_lookup_uses_plain_code(self) -> None:
        # 000300 is CSI 300; benchmark fetches pass it without a prefix.
        rows = [
            {"trade_date": "2026-05-15", "open": 4000, "high": 4005, "low": 3995, "close": 4002},
            {"trade_date": "2026-05-18", "open": 4002, "high": 4012, "low": 3998, "close": 4008},
        ]
        self.fixture.write_bars(
            cache_date="2026-05-18", code_no_prefix="000300", rows=rows,
        )
        provider = self.PrismCachePriceProvider(data_root=self.data_root)
        out = provider.fetch_window(
            "000300", start_date="2026-05-15", end_date="2026-05-18",
        )
        self.assertEqual(len(out), 2)

    def test_missing_code_file_raises_unavailable(self) -> None:
        # No cache file at all -- could be "never fetched" or "delisted".
        # Conservative bias: raise so the evaluator skips rather than
        # writing a permanent data_issue.
        provider = self.PrismCachePriceProvider(data_root=self.data_root)
        with self.assertRaises(self.PriceProviderUnavailable):
            provider.fetch_window(
                "sh600690", start_date="2026-05-15", end_date="2026-05-18",
            )

    def test_window_outside_cache_range_raises_unavailable(self) -> None:
        # Cache has rows but none covers our window (cache too stale).
        rows = self._make_rows("sh600690", [("2026-04-01", 9.0)])
        self.fixture.write_bars(
            cache_date="2026-04-01", code_no_prefix="600690", rows=rows,
        )
        provider = self.PrismCachePriceProvider(data_root=self.data_root)
        with self.assertRaises(self.PriceProviderUnavailable):
            provider.fetch_window(
                "sh600690", start_date="2026-05-15", end_date="2026-05-18",
            )

    def test_corrupt_cache_file_raises_unavailable(self) -> None:
        self.fixture.write_corrupt(cache_date="2026-05-18", code_no_prefix="600690")
        provider = self.PrismCachePriceProvider(data_root=self.data_root)
        with self.assertRaises(self.PriceProviderUnavailable):
            provider.fetch_window(
                "sh600690", start_date="2026-05-15", end_date="2026-05-18",
            )

    def test_picks_most_recent_cache_dir_that_covers_window(self) -> None:
        # Two cache dirs exist; only the newer one covers the end_date.
        # The provider should pick it without manual sorting by caller.
        early_rows = self._make_rows("sh600690", [("2026-05-08", 9.0)])
        late_rows = self._make_rows(
            "sh600690",
            [("2026-05-15", 10.0), ("2026-05-18", 10.5)],
        )
        self.fixture.write_bars(
            cache_date="2026-05-08", code_no_prefix="600690", rows=early_rows,
        )
        self.fixture.write_bars(
            cache_date="2026-05-18", code_no_prefix="600690", rows=late_rows,
        )
        provider = self.PrismCachePriceProvider(data_root=self.data_root)
        out = provider.fetch_window(
            "sh600690", start_date="2026-05-15", end_date="2026-05-18",
        )
        self.assertEqual(len(out), 2)

    def test_data_root_missing_raises_unavailable(self) -> None:
        # Pointing at a non-existent root is an infra problem, not a
        # "this stock has no data" problem.  Surface it as unavailable so
        # the operator notices on the next run instead of being silently
        # buried under data_issue events.
        provider = self.PrismCachePriceProvider(
            data_root=self.data_root / "does-not-exist",
        )
        with self.assertRaises(self.PriceProviderUnavailable):
            provider.fetch_window(
                "sh600690", start_date="2026-05-15", end_date="2026-05-18",
            )

    def test_invalid_code_raises_unavailable(self) -> None:
        # Garbage code can never have cache files -- raise unavailable
        # (rather than silently returning [] which would be classified
        # as data_issue downstream).
        provider = self.PrismCachePriceProvider(data_root=self.data_root)
        with self.assertRaises(self.PriceProviderUnavailable):
            provider.fetch_window(
                "abcxyz", start_date="2026-05-15", end_date="2026-05-18",
            )


if __name__ == "__main__":
    unittest.main()
