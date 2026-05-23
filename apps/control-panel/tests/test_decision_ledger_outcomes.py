"""Phase 4 -- OutcomeEvent evaluator tests.

The evaluator computes T+1 / T+3 / T+5 post-decision market metrics
from a pluggable price provider and appends a conservative
classification onto each DecisionRecord.  These tests cover:

* Trading-day arithmetic for due-window resolution.
* Idempotent ``find_due_outcomes`` over the on-disk ledger.
* Pure-function classifier rules (validated / invalidated /
  avoided_loss / missed_opportunity / execution_gap / data_issue /
  inconclusive).
* End-to-end ``evaluate_due_outcomes`` with a fake price provider.

No real network or vendor data is hit -- ``FakePriceProvider`` returns
fixture rows in the same shape the production provider eventually will.
"""

from __future__ import annotations

import os
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


CONTROL_PANEL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = Path(__file__).resolve().parents[3] / "apps" / "scripts"
if str(CONTROL_PANEL_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROL_PANEL_ROOT))
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))


class FakePriceProvider:
    """Lookup table-based provider used by all outcome tests.

    Rows are keyed by canonical (sh/sz prefixed or benchmark) code; each
    row is a dict with ``trade_date``, ``open``, ``high``, ``low``,
    ``close``.  Missing codes return an empty list -- the evaluator
    treats that as ``data_issue``.
    """

    def __init__(self, prices: dict[str, list[dict]] | None = None) -> None:
        self.prices = prices or {}

    def fetch_window(
        self,
        code: str,
        *,
        start_date: str,
        end_date: str,
    ) -> list[dict]:
        rows = self.prices.get(code, [])
        return [
            row
            for row in rows
            if start_date <= row["trade_date"] <= end_date
        ]


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


class TradingDayMathTests(unittest.TestCase):
    """Phase 4: nth-trading-day-after arithmetic skips weekends."""

    def setUp(self) -> None:
        sys.modules.pop("decision_ledger", None)
        import decision_ledger  # type: ignore

        self.ledger = decision_ledger

    def test_nth_trading_day_after_skips_weekend(self) -> None:
        # 2026-05-15 is a Friday -> T+1 should be Monday 2026-05-18.
        result = self.ledger.nth_trading_day_after("2026-05-15", 1)
        self.assertEqual(result, "2026-05-18")

    def test_nth_trading_day_after_three_steps(self) -> None:
        # Friday 2026-05-15 -> +3 trading days -> Wed 2026-05-20
        result = self.ledger.nth_trading_day_after("2026-05-15", 3)
        self.assertEqual(result, "2026-05-20")

    def test_nth_trading_day_after_five_steps(self) -> None:
        # Friday 2026-05-15 -> +5 trading days -> Fri 2026-05-22
        result = self.ledger.nth_trading_day_after("2026-05-15", 5)
        self.assertEqual(result, "2026-05-22")

    def test_nth_trading_day_after_zero_returns_none(self) -> None:
        self.assertIsNone(self.ledger.nth_trading_day_after("2026-05-15", 0))

    def test_nth_trading_day_after_invalid_date_returns_none(self) -> None:
        self.assertIsNone(self.ledger.nth_trading_day_after("not-a-date", 1))


class FindDueOutcomesTests(unittest.TestCase):
    """Resolver: which (decision, window) pairs are ready to be evaluated."""

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

    def _capture(self, **overrides) -> dict:
        kwargs = _sample_decision_inputs(**overrides)
        record = self.ledger.build_decision_record(**kwargs)
        return self.ledger.upsert_decision(record)

    def test_t1_window_is_due_on_next_trading_day(self) -> None:
        # Decision on Fri 2026-05-15; T+1 closes on Mon 2026-05-18.
        captured = self._capture()
        due = list(self.ledger.find_due_outcomes(as_of_date="2026-05-18"))
        windows = sorted({w for _, w in due if _["decision_id"] == captured["decision_id"]})
        self.assertEqual(windows, ["T+1"])

    def test_t3_window_is_due_three_trading_days_later(self) -> None:
        captured = self._capture()
        due = list(self.ledger.find_due_outcomes(as_of_date="2026-05-20"))
        windows = sorted({w for _, w in due if _["decision_id"] == captured["decision_id"]})
        self.assertEqual(windows, ["T+1", "T+3"])

    def test_t5_not_yet_due(self) -> None:
        captured = self._capture()
        due = list(self.ledger.find_due_outcomes(as_of_date="2026-05-20"))
        labels = {w for _, w in due if _["decision_id"] == captured["decision_id"]}
        self.assertNotIn("T+5", labels)

    def test_already_evaluated_window_is_skipped(self) -> None:
        captured = self._capture()
        # Pretend T+1 was already evaluated.
        self.ledger.append_outcome_event(
            captured["decision_id"],
            {
                "window": "T+1",
                "as_of_trade_date": "2026-05-18",
                "market_data": {"return_pct": 0.0},
                "classification": {"label": "inconclusive"},
            },
        )
        due = list(self.ledger.find_due_outcomes(as_of_date="2026-05-20"))
        windows = sorted({w for _, w in due if _["decision_id"] == captured["decision_id"]})
        self.assertEqual(windows, ["T+3"])

    def test_decisions_across_multiple_dates_are_resolved_independently(self) -> None:
        # Older decision -- all windows have already closed.
        older = self._capture(trade_date="2026-05-08")  # Friday
        younger = self._capture(trade_date="2026-05-15")  # Friday
        due = list(self.ledger.find_due_outcomes(as_of_date="2026-05-22"))
        older_windows = sorted({w for d, w in due if d["decision_id"] == older["decision_id"]})
        younger_windows = sorted({w for d, w in due if d["decision_id"] == younger["decision_id"]})
        self.assertEqual(older_windows, ["T+1", "T+3", "T+5"])
        self.assertEqual(younger_windows, ["T+1", "T+3", "T+5"])


class ClassifyOutcomeTests(unittest.TestCase):
    """Phase 4: the conservative classification heuristics."""

    def setUp(self) -> None:
        sys.modules.pop("decision_ledger", None)
        import decision_ledger  # type: ignore

        self.ledger = decision_ledger
        self.thresholds = self.ledger.OutcomeThresholds()

    def _classify(self, **kwargs) -> dict:
        defaults = dict(
            action="trial_buy",
            return_pct=0.0,
            relative_return_pct=None,
            benchmark_available=False,
            execution_events=[],
            thresholds=self.thresholds,
        )
        defaults.update(kwargs)
        return self.ledger.classify_outcome(**defaults)

    def test_trial_buy_with_relative_outperformance_is_validated(self) -> None:
        result = self._classify(
            action="trial_buy",
            return_pct=2.0,
            relative_return_pct=2.5,
            benchmark_available=True,
        )
        self.assertEqual(result["label"], "validated")

    def test_hold_with_relative_outperformance_is_validated(self) -> None:
        result = self._classify(
            action="hold",
            return_pct=1.5,
            relative_return_pct=2.0,
            benchmark_available=True,
        )
        self.assertEqual(result["label"], "validated")

    def test_trial_buy_with_relative_underperformance_is_invalidated(self) -> None:
        result = self._classify(
            action="trial_buy",
            return_pct=-4.0,
            relative_return_pct=-3.5,
            benchmark_available=True,
        )
        self.assertEqual(result["label"], "invalidated")

    def test_trial_buy_neutral_band_is_inconclusive(self) -> None:
        result = self._classify(
            action="trial_buy",
            return_pct=0.5,
            relative_return_pct=0.4,
            benchmark_available=True,
        )
        self.assertEqual(result["label"], "inconclusive")

    def test_trial_buy_no_benchmark_uses_absolute_with_higher_bar(self) -> None:
        # Without benchmark, a +2% absolute return is not enough -- we
        # need at least the higher absolute threshold to claim validated.
        result = self._classify(
            action="trial_buy",
            return_pct=2.0,
            relative_return_pct=None,
            benchmark_available=False,
        )
        self.assertEqual(result["label"], "inconclusive")

        # +4% absolute clears the higher bar.
        result = self._classify(
            action="trial_buy",
            return_pct=4.0,
            relative_return_pct=None,
            benchmark_available=False,
        )
        self.assertEqual(result["label"], "validated")

    def test_observe_with_big_upmove_is_missed_opportunity(self) -> None:
        result = self._classify(
            action="observe",
            return_pct=6.0,
        )
        self.assertEqual(result["label"], "missed_opportunity")

    def test_observe_with_modest_move_stays_inconclusive(self) -> None:
        result = self._classify(action="observe", return_pct=2.0)
        self.assertEqual(result["label"], "inconclusive")

    def test_skip_with_drawdown_is_avoided_loss(self) -> None:
        result = self._classify(action="skip", return_pct=-3.0)
        self.assertEqual(result["label"], "avoided_loss")

    def test_reduce_with_rally_is_missed_opportunity(self) -> None:
        result = self._classify(action="reduce", return_pct=5.0)
        self.assertEqual(result["label"], "missed_opportunity")

    def test_forbid_with_drawdown_is_avoided_loss(self) -> None:
        result = self._classify(action="forbid", return_pct=-4.0)
        self.assertEqual(result["label"], "avoided_loss")

    def test_validated_trial_buy_with_no_fill_becomes_execution_gap(self) -> None:
        result = self._classify(
            action="trial_buy",
            return_pct=4.0,
            relative_return_pct=3.0,
            benchmark_available=True,
            execution_events=[{"status": "no_fill"}],
        )
        self.assertEqual(result["label"], "execution_gap")
        # The summary should hint at the divergence so reviewers
        # understand why this didn't count as validated.
        self.assertTrue(
            any("execution" in reason.lower() or "no_fill" in reason.lower()
                for reason in result["reasons"])
        )

    def test_validated_trial_buy_with_partial_fill_still_validated(self) -> None:
        # A filled execution alongside no_fill markers (e.g. partial)
        # should NOT downgrade -- the operator did participate.
        result = self._classify(
            action="trial_buy",
            return_pct=4.0,
            relative_return_pct=3.0,
            benchmark_available=True,
            execution_events=[
                {"status": "no_fill"},
                {"status": "filled"},
            ],
        )
        self.assertEqual(result["label"], "validated")

    def test_unknown_action_is_inconclusive(self) -> None:
        result = self._classify(action="unknown", return_pct=10.0)
        self.assertEqual(result["label"], "inconclusive")


class EvaluateDecisionOutcomeTests(unittest.TestCase):
    """Pure-function evaluator: from a decision + provider -> outcome event."""

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

    def _stock_window(
        self,
        entry_close: float,
        next_rows: list[tuple[str, float, float, float, float]],
    ) -> list[dict]:
        """Build a chronological price window.

        ``next_rows`` is a list of ``(trade_date, open, high, low, close)``
        tuples for the post-decision days.  An entry row is prepended at
        the decision's trade_date with the supplied ``entry_close``.
        """

        rows = [
            {
                "trade_date": "2026-05-15",
                "open": entry_close,
                "high": entry_close,
                "low": entry_close,
                "close": entry_close,
            }
        ]
        for trade_date, o, h, lo, c in next_rows:
            rows.append({"trade_date": trade_date, "open": o, "high": h, "low": lo, "close": c})
        return rows

    def test_validated_trial_buy_with_benchmark(self) -> None:
        decision = self.ledger.build_decision_record(
            **_sample_decision_inputs(action="trial_buy")
        )
        self.ledger.upsert_decision(decision)

        provider = FakePriceProvider(
            prices={
                "sh600690": self._stock_window(
                    entry_close=10.0,
                    next_rows=[
                        ("2026-05-18", 10.2, 10.5, 10.1, 10.4),
                        ("2026-05-19", 10.4, 10.7, 10.3, 10.6),
                        ("2026-05-20", 10.6, 10.9, 10.5, 10.8),
                    ],
                ),
                "000300": [
                    {"trade_date": "2026-05-15", "open": 4000, "high": 4000, "low": 4000, "close": 4000},
                    {"trade_date": "2026-05-18", "open": 4005, "high": 4010, "low": 3998, "close": 4008},
                    {"trade_date": "2026-05-19", "open": 4008, "high": 4015, "low": 4002, "close": 4012},
                    {"trade_date": "2026-05-20", "open": 4012, "high": 4020, "low": 4008, "close": 4016},
                ],
            }
        )

        event = self.ledger.evaluate_decision_outcome(
            decision,
            window="T+3",
            price_provider=provider,
        )

        self.assertEqual(event["window"], "T+3")
        self.assertEqual(event["as_of_trade_date"], "2026-05-20")
        market = event["market_data"]
        self.assertAlmostEqual(market["entry_reference_price"], 10.0)
        self.assertAlmostEqual(market["close_price"], 10.8)
        self.assertAlmostEqual(market["return_pct"], 8.0, places=2)
        # Benchmark: (4016 - 4000) / 4000 = 0.4%
        self.assertAlmostEqual(market["benchmark_return_pct"], 0.4, places=2)
        self.assertAlmostEqual(market["relative_return_pct"], 7.6, places=2)
        # Max favorable: 10.9 -> +9%
        self.assertAlmostEqual(market["max_favorable_pct"], 9.0, places=2)
        # Max adverse: 10.1 -> +1%
        self.assertAlmostEqual(market["max_adverse_pct"], 1.0, places=2)
        self.assertEqual(event["classification"]["label"], "validated")
        self.assertTrue(event["quality"]["usable_for_decision_quality"])

    def test_benchmark_missing_falls_back_to_absolute(self) -> None:
        decision = self.ledger.build_decision_record(
            **_sample_decision_inputs(action="trial_buy")
        )
        self.ledger.upsert_decision(decision)

        provider = FakePriceProvider(
            prices={
                "sh600690": self._stock_window(
                    entry_close=10.0,
                    next_rows=[
                        ("2026-05-18", 10.0, 10.6, 9.9, 10.5),
                    ],
                ),
                # Benchmark deliberately missing.
            }
        )

        event = self.ledger.evaluate_decision_outcome(
            decision,
            window="T+1",
            price_provider=provider,
        )

        self.assertIsNone(event["market_data"]["benchmark_return_pct"])
        self.assertIsNone(event["market_data"]["relative_return_pct"])
        # +5% absolute clears the higher no-benchmark bar.
        self.assertEqual(event["classification"]["label"], "validated")

    def test_missing_stock_prices_yield_data_issue(self) -> None:
        decision = self.ledger.build_decision_record(
            **_sample_decision_inputs(action="trial_buy")
        )
        self.ledger.upsert_decision(decision)

        provider = FakePriceProvider(prices={})  # no rows for any code

        event = self.ledger.evaluate_decision_outcome(
            decision,
            window="T+1",
            price_provider=provider,
        )

        self.assertEqual(event["classification"]["label"], "data_issue")
        self.assertFalse(event["quality"]["usable_for_decision_quality"])
        self.assertIsNotNone(event["quality"]["data_issue"])

    def test_missing_window_close_yields_data_issue(self) -> None:
        decision = self.ledger.build_decision_record(
            **_sample_decision_inputs(action="trial_buy")
        )
        self.ledger.upsert_decision(decision)

        # Entry price present, but no rows on or after T+1.
        provider = FakePriceProvider(
            prices={
                "sh600690": [
                    {"trade_date": "2026-05-15", "open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0},
                ]
            }
        )

        event = self.ledger.evaluate_decision_outcome(
            decision,
            window="T+1",
            price_provider=provider,
        )
        self.assertEqual(event["classification"]["label"], "data_issue")

    def test_observe_then_big_rally_is_missed_opportunity(self) -> None:
        decision = self.ledger.build_decision_record(
            **_sample_decision_inputs(action="observe", action_label="重点观察")
        )
        self.ledger.upsert_decision(decision)

        provider = FakePriceProvider(
            prices={
                "sh600690": self._stock_window(
                    entry_close=10.0,
                    next_rows=[
                        ("2026-05-18", 10.0, 10.8, 10.0, 10.7),
                    ],
                )
            }
        )
        event = self.ledger.evaluate_decision_outcome(
            decision,
            window="T+1",
            price_provider=provider,
        )
        # +7% absolute -- clears observe's missed_opportunity threshold.
        self.assertEqual(event["classification"]["label"], "missed_opportunity")

    def test_skip_then_drawdown_is_avoided_loss(self) -> None:
        decision = self.ledger.build_decision_record(
            **_sample_decision_inputs(action="skip", action_label="今日放弃")
        )
        self.ledger.upsert_decision(decision)

        provider = FakePriceProvider(
            prices={
                "sh600690": self._stock_window(
                    entry_close=10.0,
                    next_rows=[
                        ("2026-05-18", 10.0, 10.05, 9.7, 9.7),
                    ],
                )
            }
        )
        event = self.ledger.evaluate_decision_outcome(
            decision,
            window="T+1",
            price_provider=provider,
        )
        self.assertEqual(event["classification"]["label"], "avoided_loss")


class EvaluateDueOutcomesEndToEndTests(unittest.TestCase):
    """The orchestrator: walks the ledger, appends events, reports summary."""

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
            self.ledger.build_decision_record(
                **_sample_decision_inputs(action="trial_buy")
            )
        )

        self.provider = FakePriceProvider(
            prices={
                "sh600690": [
                    {"trade_date": "2026-05-15", "open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0},
                    {"trade_date": "2026-05-18", "open": 10.0, "high": 10.5, "low": 9.9, "close": 10.4},
                    {"trade_date": "2026-05-19", "open": 10.4, "high": 10.7, "low": 10.3, "close": 10.6},
                    {"trade_date": "2026-05-20", "open": 10.6, "high": 10.9, "low": 10.5, "close": 10.8},
                ],
                "000300": [
                    {"trade_date": "2026-05-15", "open": 4000, "high": 4000, "low": 4000, "close": 4000},
                    {"trade_date": "2026-05-18", "open": 4000, "high": 4005, "low": 3998, "close": 4002},
                    {"trade_date": "2026-05-19", "open": 4002, "high": 4008, "low": 3999, "close": 4004},
                    {"trade_date": "2026-05-20", "open": 4004, "high": 4010, "low": 4000, "close": 4006},
                ],
            }
        )

    def test_evaluates_all_due_windows_in_one_pass(self) -> None:
        summary = self.ledger.evaluate_due_outcomes(
            as_of_date="2026-05-20",
            price_provider=self.provider,
        )
        self.assertEqual(summary["evaluated"], 2)  # T+1 + T+3 due
        self.assertEqual(summary["already_present"], 0)
        stored = self.ledger.load_decision(self.decision["decision_id"])
        windows = sorted(ev["window"] for ev in stored["outcome_events"])
        self.assertEqual(windows, ["T+1", "T+3"])

    def test_evaluator_is_idempotent_on_rerun(self) -> None:
        self.ledger.evaluate_due_outcomes(
            as_of_date="2026-05-20",
            price_provider=self.provider,
        )
        summary = self.ledger.evaluate_due_outcomes(
            as_of_date="2026-05-20",
            price_provider=self.provider,
        )
        self.assertEqual(summary["evaluated"], 0)
        self.assertEqual(summary["already_present"], 2)
        stored = self.ledger.load_decision(self.decision["decision_id"])
        self.assertEqual(len(stored["outcome_events"]), 2)

    def test_skips_decisions_when_no_provider(self) -> None:
        summary = self.ledger.evaluate_due_outcomes(
            as_of_date="2026-05-20",
            price_provider=None,
        )
        self.assertEqual(summary["evaluated"], 0)
        # Decisions are due but we cannot fetch prices -- skip without
        # appending a data_issue marker, so a later run with a real
        # provider can still classify them properly.
        self.assertGreater(summary["skipped_no_provider"], 0)
        stored = self.ledger.load_decision(self.decision["decision_id"])
        self.assertEqual(stored["outcome_events"], [])

    def test_script_persists_scheduled_outcome_status_for_settings(self) -> None:
        sys.modules.pop("evaluate_decision_ledger", None)
        import evaluate_decision_ledger  # type: ignore

        with mock.patch.object(
            sys,
            "argv",
            [
                "evaluate_decision_ledger.py",
                "--as-of",
                "2026-05-20",
                "--provider",
                "none",
            ],
        ), mock.patch.dict(
            os.environ,
            {
                "PRISM_SCHEDULED_RUN_ID": "decision_ledger_outcomes_2026-05-20",
                "PRISM_SCHEDULED_VIA": "prism_scheduler",
            },
        ):
            code = evaluate_decision_ledger.main()

        self.assertEqual(code, 0)
        status_path = self.ledger_root / "status" / "outcome_latest.json"
        self.assertTrue(status_path.exists())
        status = json.loads(status_path.read_text(encoding="utf-8"))
        self.assertEqual(status["status"], "no_provider")
        self.assertEqual(status["task_name"], "decision_ledger_outcomes")
        self.assertEqual(status["run_id"], "decision_ledger_outcomes_2026-05-20")
        self.assertEqual(status["scheduled_via"], "prism_scheduler")
        self.assertIn("recorded_at", status)
        self.assertGreater(status["skipped_no_provider"], 0)

    def test_evaluator_appends_data_issue_when_provider_returns_empty(self) -> None:
        empty_provider = FakePriceProvider(prices={})
        summary = self.ledger.evaluate_due_outcomes(
            as_of_date="2026-05-18",
            price_provider=empty_provider,
        )
        # Only T+1 is due on 2026-05-18.
        self.assertEqual(summary["evaluated"], 1)
        stored = self.ledger.load_decision(self.decision["decision_id"])
        self.assertEqual(len(stored["outcome_events"]), 1)
        outcome = stored["outcome_events"][0]
        self.assertEqual(outcome["classification"]["label"], "data_issue")
        self.assertFalse(outcome["quality"]["usable_for_decision_quality"])


if __name__ == "__main__":
    unittest.main()
