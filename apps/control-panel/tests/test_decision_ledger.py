"""Tests for the Decision Ledger core repository (Phase 1).

The ledger is an append-only, JSON-on-disk store for daily decision
accountability.  These tests cover only the repository layer: ID
stability, idempotent writes, append-only events, original recommendation
immutability, empty-state reads, and corrupt-JSON handling.

No today-action-queue capture, no portfolio attachment, no outcome
evaluation logic is tested here -- those land in later phases.
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
    """Return the kwargs used to build a DecisionRecord for tests."""

    base = {
        "trade_date": "2026-05-15",
        "code": "sh600690",
        "name": "海尔智家",
        "lane": "watchlist",
        "surface": "today_action_queue",
        "action_key": "watchlist:600690:2026-05-15",
        "source_label": "自选股链路",
        "action": "hold",
        "action_label": "继续持有",
        "main_conclusion": "继续持有，但不加仓",
        "position_guidance": "半仓以内",
        "trigger_condition": "放量站回关键均线再考虑加仓",
        "continue_condition": "不跌破趋势线则继续观察",
        "stop_condition": "跌破止损线或资金持续流出",
        "risk_summary": "弱市中只按纪律处理",
        "expected_trade_date": "2026-05-15",
        "data_trade_date": "2026-05-15",
        "readiness_mode": "live_ready",
        "readiness_ready": True,
        "blockers": [],
        "warnings": [],
    }
    base.update(overrides)
    return base


class DecisionLedgerCoreTests(unittest.TestCase):
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

        # Re-import so the module picks up the env override.
        sys.modules.pop("decision_ledger", None)
        import decision_ledger  # type: ignore

        self.ledger = decision_ledger

    # ----------------------------------------------------------------- ID

    def test_decision_id_is_stable_for_same_inputs(self) -> None:
        kwargs = _sample_decision_inputs()
        first = self.ledger.make_decision_id(**self._id_args(kwargs))
        second = self.ledger.make_decision_id(**self._id_args(kwargs))
        self.assertEqual(first, second)

    def test_decision_id_changes_when_action_changes(self) -> None:
        """Material change (action flip) yields a different decision id.

        This is what enables the supersede flow: capture the new
        recommendation as a separate decision rather than mutating the
        original.
        """

        base = self._id_args(_sample_decision_inputs(action="hold"))
        flipped = self._id_args(_sample_decision_inputs(action="buy"))
        self.assertNotEqual(
            self.ledger.make_decision_id(**base),
            self.ledger.make_decision_id(**flipped),
        )

    def test_decision_id_embeds_trade_date_and_code(self) -> None:
        kwargs = _sample_decision_inputs()
        decision_id = self.ledger.make_decision_id(**self._id_args(kwargs))
        self.assertIn("2026-05-15", decision_id)
        self.assertIn("600690", decision_id)

    # ----------------------------------------------------------- empty-state

    def test_load_decisions_for_unknown_date_returns_empty(self) -> None:
        self.assertEqual(self.ledger.load_decisions("2026-05-15"), [])

    def test_load_decision_for_unknown_id_returns_none(self) -> None:
        self.assertIsNone(self.ledger.load_decision("nope"))

    def test_list_decisions_for_stock_empty(self) -> None:
        self.assertEqual(self.ledger.list_decisions_for_stock("sh600690"), [])

    # --------------------------------------------------------- upsert basic

    def test_upsert_decision_creates_file_with_one_record(self) -> None:
        record = self._build_record()
        saved = self.ledger.upsert_decision(record)
        self.assertEqual(saved["decision_id"], record["decision_id"])

        on_disk = self.ledger.load_decisions("2026-05-15")
        self.assertEqual(len(on_disk), 1)
        self.assertEqual(on_disk[0]["decision_id"], record["decision_id"])

        # The decisions file actually exists where we expect it.
        path = self.ledger_root / "decisions" / "2026-05-15.json"
        self.assertTrue(path.exists())

    def test_upsert_decision_is_idempotent_on_repeat_save(self) -> None:
        record = self._build_record()
        self.ledger.upsert_decision(record)
        self.ledger.upsert_decision(record)
        self.ledger.upsert_decision(record)

        on_disk = self.ledger.load_decisions("2026-05-15")
        self.assertEqual(len(on_disk), 1)

    def test_upsert_decision_rejects_id_trade_date_mismatch(self) -> None:
        """A forged decision_id whose date prefix disagrees with the
        record's trade_date must be rejected -- otherwise loaders that
        route by id-prefix would never find the record again.
        """

        record = self._build_record()
        record["decision_id"] = (
            "2026-05-14:" + record["decision_id"].split(":", 1)[1]
        )
        with self.assertRaises(self.ledger.DecisionLedgerError) as ctx:
            self.ledger.upsert_decision(record)
        msg = str(ctx.exception)
        self.assertIn("decision_id", msg)
        self.assertIn("trade_date", msg)

    def test_upsert_does_not_overwrite_recommendation_on_resave(self) -> None:
        """Re-capture with same decision_id must not rewrite the snapshot.

        Even if a caller hands us a record whose recommendation drifted
        (e.g., generated_at, source-card ordering), the on-disk record
        keeps its original recommendation fields.  This enforces the
        snapshot-do-not-recompute rule.
        """

        first = self._build_record(main_conclusion="继续持有，但不加仓")
        self.ledger.upsert_decision(first)

        drifted = self._build_record(main_conclusion="继续持有 (改写)")
        # Force same decision_id so we can verify the immutability rule.
        drifted["decision_id"] = first["decision_id"]
        self.ledger.upsert_decision(drifted)

        stored = self.ledger.load_decision(first["decision_id"])
        self.assertIsNotNone(stored)
        self.assertEqual(
            stored["recommendation"]["main_conclusion"],
            "继续持有，但不加仓",
        )

    def test_upsert_two_different_decisions_share_file(self) -> None:
        a = self._build_record(code="sh600690")
        b = self._build_record(code="sz000001", name="平安银行")
        self.ledger.upsert_decision(a)
        self.ledger.upsert_decision(b)

        on_disk = self.ledger.load_decisions("2026-05-15")
        codes = sorted(rec["stock"]["code"] for rec in on_disk)
        self.assertEqual(codes, ["sh600690", "sz000001"])

    def test_load_decision_finds_record_across_dates(self) -> None:
        a = self._build_record(trade_date="2026-05-14")
        b = self._build_record(trade_date="2026-05-15")
        self.ledger.upsert_decision(a)
        self.ledger.upsert_decision(b)

        found = self.ledger.load_decision(b["decision_id"])
        self.assertIsNotNone(found)
        self.assertEqual(found["trade_date"], "2026-05-15")

    def test_list_decisions_for_stock_returns_only_matching(self) -> None:
        own = self._build_record(code="sh600690")
        other = self._build_record(code="sz000001", name="平安银行")
        self.ledger.upsert_decision(own)
        self.ledger.upsert_decision(other)

        records = self.ledger.list_decisions_for_stock("sh600690")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["stock"]["code"], "sh600690")

    # ------------------------------------------------------- corrupt JSON

    def test_load_decisions_raises_on_corrupt_json(self) -> None:
        path = self.ledger_root / "decisions" / "2026-05-15.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{ this is not valid json", encoding="utf-8")

        with self.assertRaises(self.ledger.DecisionLedgerError) as ctx:
            self.ledger.load_decisions("2026-05-15")
        self.assertIn("2026-05-15.json", str(ctx.exception))

    def test_load_decisions_raises_on_non_list_payload(self) -> None:
        path = self.ledger_root / "decisions" / "2026-05-15.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"oops": "wrong shape"}', encoding="utf-8")

        with self.assertRaises(self.ledger.DecisionLedgerError):
            self.ledger.load_decisions("2026-05-15")

    def test_load_decisions_raises_on_non_object_record(self) -> None:
        """A non-Mapping inside the list is corruption, not data we can ignore.

        The previous behavior silently filtered such records out, which
        masked partial corruption.  The ledger is the audit log -- the
        operator must hear about a broken record, not have it disappear.
        """

        path = self.ledger_root / "decisions" / "2026-05-15.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            '[{"decision_id": "2026-05-15:sh600690:x:y:abcdef01", '
            '"trade_date": "2026-05-15"}, "definitely-not-a-record"]',
            encoding="utf-8",
        )
        with self.assertRaises(self.ledger.DecisionLedgerError) as ctx:
            self.ledger.load_decisions("2026-05-15")
        message = str(ctx.exception)
        self.assertIn("2026-05-15.json", message)
        self.assertIn("1", message)  # index of the bad record

    # ---------------------------------------------------- execution events

    def test_append_execution_event_appends_to_decision(self) -> None:
        record = self._build_record()
        self.ledger.upsert_decision(record)

        event = {
            "trade_date": "2026-05-15",
            "status": "filled",
            "side": "buy",
            "price": 28.35,
            "quantity": 100,
            "amount": 2835.0,
            "note": "按计划轻仓试错",
            "source": "portfolio_writeback",
        }
        self.ledger.append_execution_event(record["decision_id"], event)

        stored = self.ledger.load_decision(record["decision_id"])
        self.assertEqual(len(stored["execution_events"]), 1)
        ev = stored["execution_events"][0]
        self.assertEqual(ev["status"], "filled")
        self.assertEqual(ev["price"], 28.35)
        self.assertEqual(ev["quantity"], 100)
        self.assertEqual(ev["decision_id"], record["decision_id"])

    def test_append_execution_event_is_idempotent(self) -> None:
        record = self._build_record()
        self.ledger.upsert_decision(record)

        event = {
            "trade_date": "2026-05-15",
            "status": "filled",
            "side": "buy",
            "price": 28.35,
            "quantity": 100,
            "amount": 2835.0,
            "source": "portfolio_writeback",
        }
        self.ledger.append_execution_event(record["decision_id"], event)
        self.ledger.append_execution_event(record["decision_id"], event)

        stored = self.ledger.load_decision(record["decision_id"])
        self.assertEqual(len(stored["execution_events"]), 1)

    def test_append_execution_event_differs_for_different_fills(self) -> None:
        record = self._build_record()
        self.ledger.upsert_decision(record)

        self.ledger.append_execution_event(
            record["decision_id"],
            {
                "trade_date": "2026-05-15",
                "status": "filled",
                "side": "buy",
                "price": 28.35,
                "quantity": 100,
                "amount": 2835.0,
                "source": "portfolio_writeback",
            },
        )
        self.ledger.append_execution_event(
            record["decision_id"],
            {
                "trade_date": "2026-05-15",
                "status": "filled",
                "side": "buy",
                "price": 28.50,
                "quantity": 100,
                "amount": 2850.0,
                "source": "portfolio_writeback",
            },
        )

        stored = self.ledger.load_decision(record["decision_id"])
        self.assertEqual(len(stored["execution_events"]), 2)

    def test_append_execution_event_unknown_decision_raises(self) -> None:
        with self.assertRaises(self.ledger.DecisionLedgerError):
            self.ledger.append_execution_event("missing", {"status": "filled"})

    def test_append_execution_event_does_not_change_recommendation(self) -> None:
        record = self._build_record()
        self.ledger.upsert_decision(record)
        original_reco = dict(record["recommendation"])
        self.ledger.append_execution_event(
            record["decision_id"],
            {
                "trade_date": "2026-05-15",
                "status": "filled",
                "side": "buy",
                "price": 28.35,
                "quantity": 100,
                "amount": 2835.0,
                "source": "portfolio_writeback",
            },
        )
        stored = self.ledger.load_decision(record["decision_id"])
        self.assertEqual(stored["recommendation"], original_reco)

    def test_append_execution_event_requires_known_status(self) -> None:
        record = self._build_record()
        self.ledger.upsert_decision(record)
        with self.assertRaises(self.ledger.DecisionLedgerError):
            self.ledger.append_execution_event(
                record["decision_id"],
                {"status": "weird_thing", "trade_date": "2026-05-15"},
            )

    # ----------------------------------------------------- outcome events

    def test_append_outcome_event_appends_to_decision(self) -> None:
        record = self._build_record()
        self.ledger.upsert_decision(record)

        self.ledger.append_outcome_event(
            record["decision_id"],
            {
                "window": "T+3",
                "as_of_trade_date": "2026-05-20",
                "market_data": {
                    "entry_reference_price": 28.35,
                    "close_price": 29.10,
                    "return_pct": 2.65,
                    "benchmark_code": "000300",
                    "benchmark_return_pct": 0.80,
                    "relative_return_pct": 1.85,
                    "max_favorable_pct": 4.20,
                    "max_adverse_pct": -1.10,
                },
                "classification": {
                    "label": "validated",
                    "tone": "positive",
                    "summary": "T+3 相对基准走强",
                    "reasons": ["相对沪深300 +1.85%"],
                },
                "quality": {
                    "usable_for_decision_quality": True,
                    "data_issue": None,
                },
            },
        )

        stored = self.ledger.load_decision(record["decision_id"])
        self.assertEqual(len(stored["outcome_events"]), 1)
        outcome = stored["outcome_events"][0]
        self.assertEqual(outcome["window"], "T+3")
        self.assertEqual(outcome["classification"]["label"], "validated")

    def test_append_outcome_event_is_idempotent_per_window(self) -> None:
        record = self._build_record()
        self.ledger.upsert_decision(record)

        outcome = {
            "window": "T+3",
            "as_of_trade_date": "2026-05-20",
            "market_data": {"return_pct": 2.65},
            "classification": {"label": "validated"},
        }
        self.ledger.append_outcome_event(record["decision_id"], outcome)
        # Re-running the evaluator must NOT duplicate the outcome.
        self.ledger.append_outcome_event(record["decision_id"], outcome)

        stored = self.ledger.load_decision(record["decision_id"])
        self.assertEqual(len(stored["outcome_events"]), 1)

    def test_append_outcome_event_different_windows_coexist(self) -> None:
        record = self._build_record()
        self.ledger.upsert_decision(record)

        for window, ref_date in (("T+1", "2026-05-18"), ("T+3", "2026-05-20"), ("T+5", "2026-05-22")):
            self.ledger.append_outcome_event(
                record["decision_id"],
                {
                    "window": window,
                    "as_of_trade_date": ref_date,
                    "market_data": {"return_pct": 1.0},
                    "classification": {"label": "inconclusive"},
                },
            )

        stored = self.ledger.load_decision(record["decision_id"])
        windows = sorted(ev["window"] for ev in stored["outcome_events"])
        self.assertEqual(windows, ["T+1", "T+3", "T+5"])

    def test_append_outcome_event_unknown_decision_raises(self) -> None:
        with self.assertRaises(self.ledger.DecisionLedgerError):
            self.ledger.append_outcome_event(
                "missing",
                {"window": "T+3", "classification": {"label": "validated"}},
            )

    def test_append_outcome_event_unknown_window_raises(self) -> None:
        record = self._build_record()
        self.ledger.upsert_decision(record)
        with self.assertRaises(self.ledger.DecisionLedgerError):
            self.ledger.append_outcome_event(
                record["decision_id"],
                {
                    "window": "T+99",
                    "classification": {"label": "validated"},
                },
            )

    def test_append_outcome_event_does_not_change_recommendation(self) -> None:
        record = self._build_record()
        self.ledger.upsert_decision(record)
        original_reco = dict(record["recommendation"])
        self.ledger.append_outcome_event(
            record["decision_id"],
            {
                "window": "T+1",
                "as_of_trade_date": "2026-05-18",
                "market_data": {"return_pct": -1.0},
                "classification": {"label": "invalidated"},
            },
        )
        stored = self.ledger.load_decision(record["decision_id"])
        self.assertEqual(stored["recommendation"], original_reco)

    # ----------------------------------------------- atomic write hygiene

    def test_upsert_decision_does_not_leave_tmp_file(self) -> None:
        record = self._build_record()
        self.ledger.upsert_decision(record)
        decisions_dir = self.ledger_root / "decisions"
        leftover = list(decisions_dir.glob("*.tmp"))
        self.assertEqual(leftover, [])

    def test_persisted_file_is_valid_utf8_json(self) -> None:
        record = self._build_record(name="海尔智家")
        self.ledger.upsert_decision(record)
        path = self.ledger_root / "decisions" / "2026-05-15.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIsInstance(data, list)
        self.assertEqual(data[0]["stock"]["name"], "海尔智家")

    # ------------------------------------------------------------- supersede

    def test_mark_superseded_sets_status_without_touching_recommendation(self) -> None:
        original = self._build_record()
        self.ledger.upsert_decision(original)

        replacement = self._build_record(action="buy", action_label="建议买入")
        self.assertNotEqual(replacement["decision_id"], original["decision_id"])
        self.ledger.upsert_decision(replacement)

        self.ledger.mark_decision_superseded(
            original["decision_id"], by=replacement["decision_id"]
        )

        stored = self.ledger.load_decision(original["decision_id"])
        self.assertEqual(stored["status"]["state"], "superseded")
        self.assertEqual(stored["status"]["superseded_by"], replacement["decision_id"])
        # Recommendation untouched.
        self.assertEqual(
            stored["recommendation"]["action"], original["recommendation"]["action"]
        )

    # ----------------------------------------------------------- helpers

    @staticmethod
    def _id_args(kwargs):
        """Subset of inputs used by make_decision_id."""

        return {
            "trade_date": kwargs["trade_date"],
            "code": kwargs["code"],
            "surface": kwargs["surface"],
            "lane": kwargs["lane"],
            "action_key": kwargs["action_key"],
            "action": kwargs["action"],
        }

    def _build_record(self, **overrides) -> dict:
        kwargs = _sample_decision_inputs(**overrides)
        return self.ledger.build_decision_record(**kwargs)


class FindDecisionForExecutionTests(unittest.TestCase):
    """Phase 3: matching a writeback to its captured decision."""

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

    def _capture(self, *, action_key: str, code: str, action: str = "hold",
                 trade_date: str = "2026-05-15") -> dict:
        kwargs = _sample_decision_inputs(
            trade_date=trade_date,
            code=code,
            action_key=action_key,
            action=action,
        )
        record = self.ledger.build_decision_record(**kwargs)
        return self.ledger.upsert_decision(record)

    # ---------------------------------------------------- match by intent_key

    def test_finds_open_decision_by_intent_key(self) -> None:
        captured = self._capture(action_key="watchlist:600690", code="sh600690")
        decision, status = self.ledger.find_decision_for_execution(
            trade_date="2026-05-15",
            code="sh600690",
            intent_key="watchlist:600690",
            today_action_key=None,
        )
        self.assertEqual(status, "matched")
        self.assertIsNotNone(decision)
        self.assertEqual(decision["decision_id"], captured["decision_id"])

    def test_intent_key_match_takes_priority_over_today_action_key(self) -> None:
        wl = self._capture(action_key="watchlist:600690", code="sh600690")
        self._capture(
            action_key="screening:000001",
            code="sz000001",
        )
        decision, status = self.ledger.find_decision_for_execution(
            trade_date="2026-05-15",
            code="sh600690",
            intent_key="watchlist:600690",
            today_action_key="screening:000001",
        )
        self.assertEqual(status, "matched")
        self.assertEqual(decision["decision_id"], wl["decision_id"])

    # ---------------------------------------------- match by today_action_key

    def test_finds_open_decision_by_today_action_key(self) -> None:
        captured = self._capture(action_key="watchlist:600690", code="sh600690")
        decision, status = self.ledger.find_decision_for_execution(
            trade_date="2026-05-15",
            code="sh600690",
            intent_key=None,
            today_action_key="watchlist:600690",
        )
        self.assertEqual(status, "matched")
        self.assertEqual(decision["decision_id"], captured["decision_id"])

    # ------------------------------------------- match by trade_date + code

    def test_falls_back_to_trade_date_and_code(self) -> None:
        captured = self._capture(action_key="watchlist:600690", code="sh600690")
        decision, status = self.ledger.find_decision_for_execution(
            trade_date="2026-05-15",
            code="sh600690",
            intent_key=None,
            today_action_key=None,
        )
        self.assertEqual(status, "matched")
        self.assertEqual(decision["decision_id"], captured["decision_id"])

    def test_trade_date_and_code_accepts_unprefixed_code(self) -> None:
        captured = self._capture(action_key="watchlist:600690", code="sh600690")
        decision, status = self.ledger.find_decision_for_execution(
            trade_date="2026-05-15",
            code="600690",
            intent_key=None,
            today_action_key=None,
        )
        self.assertEqual(status, "matched")
        self.assertEqual(decision["decision_id"], captured["decision_id"])

    def test_trade_date_and_code_returns_ambiguous_for_two_open(self) -> None:
        # Two open decisions for the same stock on the same date -- e.g.
        # the morning capture wrote 'hold' and the afternoon capture
        # wrote 'reduce'.  Both stay 'open' until something marks one
        # superseded.  Refuse to bind blindly.
        self._capture(action_key="watchlist:600690", code="sh600690", action="hold")
        self._capture(action_key="watchlist:600690:pm", code="sh600690", action="reduce")
        decision, status = self.ledger.find_decision_for_execution(
            trade_date="2026-05-15",
            code="sh600690",
            intent_key=None,
            today_action_key=None,
        )
        self.assertIsNone(decision)
        self.assertEqual(status, "ambiguous")

    def test_returns_none_when_no_decision_exists(self) -> None:
        decision, status = self.ledger.find_decision_for_execution(
            trade_date="2026-05-15",
            code="sh600690",
            intent_key="watchlist:600690",
            today_action_key=None,
        )
        self.assertIsNone(decision)
        self.assertEqual(status, "none")

    def test_returns_none_when_only_match_is_superseded(self) -> None:
        captured = self._capture(action_key="watchlist:600690", code="sh600690")
        # Mark it superseded -- writebacks must not bind to closed decisions.
        replacement = self._capture(
            action_key="watchlist:600690",
            code="sh600690",
            action="reduce",
        )
        self.ledger.mark_decision_superseded(
            captured["decision_id"], by=replacement["decision_id"]
        )
        decision, status = self.ledger.find_decision_for_execution(
            trade_date="2026-05-15",
            code="sh600690",
            intent_key=None,
            today_action_key=None,
        )
        # The remaining open one is the replacement.
        self.assertEqual(status, "matched")
        self.assertEqual(decision["decision_id"], replacement["decision_id"])


class AppendExecutionEventForWritebackTests(unittest.TestCase):
    """Phase 3: defensive helper used by Portfolio / Today endpoints."""

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

    def _capture(self, *, action_key: str, code: str = "sh600690",
                 action: str = "hold") -> dict:
        kwargs = _sample_decision_inputs(
            code=code,
            action_key=action_key,
            action=action,
        )
        return self.ledger.upsert_decision(self.ledger.build_decision_record(**kwargs))

    def test_attaches_filled_event_when_decision_matches(self) -> None:
        captured = self._capture(action_key="watchlist:600690")
        result = self.ledger.append_execution_event_for_writeback(
            trade_date="2026-05-15",
            code="sh600690",
            status="filled",
            side="buy",
            price=28.35,
            quantity=100,
            amount=2835.0,
            intent_key="watchlist:600690",
            note="按计划轻仓试错",
        )
        self.assertTrue(result["attached"])
        self.assertEqual(result["decision_id"], captured["decision_id"])
        self.assertIn("event_id", result)
        self.assertEqual(result["status"], "filled")

        stored = self.ledger.load_decision(captured["decision_id"])
        self.assertEqual(len(stored["execution_events"]), 1)
        ev = stored["execution_events"][0]
        self.assertEqual(ev["status"], "filled")
        self.assertEqual(ev["price"], 28.35)
        self.assertEqual(ev["intent_key"], "watchlist:600690")

    def test_idempotent_on_duplicate_writeback(self) -> None:
        captured = self._capture(action_key="watchlist:600690")
        kwargs = dict(
            trade_date="2026-05-15",
            code="sh600690",
            status="filled",
            side="buy",
            price=28.35,
            quantity=100,
            amount=2835.0,
            intent_key="watchlist:600690",
        )
        a = self.ledger.append_execution_event_for_writeback(**kwargs)
        b = self.ledger.append_execution_event_for_writeback(**kwargs)
        self.assertTrue(a["attached"])
        self.assertTrue(b["attached"])
        # Same fingerprint -> same event_id, single stored event.
        self.assertEqual(a["event_id"], b["event_id"])
        stored = self.ledger.load_decision(captured["decision_id"])
        self.assertEqual(len(stored["execution_events"]), 1)

    def test_returns_no_match_when_decision_missing(self) -> None:
        result = self.ledger.append_execution_event_for_writeback(
            trade_date="2026-05-15",
            code="sh600690",
            status="filled",
            intent_key="watchlist:600690",
        )
        self.assertFalse(result["attached"])
        self.assertEqual(result["reason"], "no_matching_decision")

    def test_returns_ambiguous_when_two_open_decisions(self) -> None:
        self._capture(action_key="watchlist:600690", action="hold")
        self._capture(action_key="watchlist:600690:pm", action="reduce")
        result = self.ledger.append_execution_event_for_writeback(
            trade_date="2026-05-15",
            code="sh600690",
            status="filled",
            # Neither key matches an action_key, so we fall back to
            # trade_date+code -- which finds two candidates.
            intent_key=None,
            today_action_key=None,
        )
        self.assertFalse(result["attached"])
        self.assertEqual(result["reason"], "ambiguous_decision")

    def test_swallows_ledger_error_from_corrupt_file(self) -> None:
        path = self.ledger_root / "decisions" / "2026-05-15.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{ not valid", encoding="utf-8")

        result = self.ledger.append_execution_event_for_writeback(
            trade_date="2026-05-15",
            code="sh600690",
            status="filled",
            intent_key="watchlist:600690",
        )
        self.assertFalse(result["attached"])
        self.assertEqual(result["reason"], "ledger_error")
        self.assertIn("detail", result)

    def test_rejects_unknown_status(self) -> None:
        # Captured decision so the match would otherwise succeed.
        self._capture(action_key="watchlist:600690")
        result = self.ledger.append_execution_event_for_writeback(
            trade_date="2026-05-15",
            code="sh600690",
            status="weird_thing",
            intent_key="watchlist:600690",
        )
        self.assertFalse(result["attached"])
        self.assertEqual(result["reason"], "ledger_error")


if __name__ == "__main__":
    unittest.main()
