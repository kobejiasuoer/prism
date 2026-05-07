"""Tests for the account_state branch of compute_readiness.

Covers the live_small gating logic the operator will rely on before any
real-money execution: mode-specific blockers for empty cash, stale
reconciliation, unreconciled "done" actions, and post-holiday calendar
classification driven by trading_calendar.
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

CONTROL_PANEL_ROOT = Path(__file__).resolve().parents[1]
if str(CONTROL_PANEL_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROL_PANEL_ROOT))

import readiness  # type: ignore  # noqa: E402


def _fresh_artifacts(trade_date: str, generated_at: str):
    """Build artifacts that are themselves freshness-clean for ``trade_date``."""

    watchlist = {
        "trade_date": trade_date,
        "generated_at": generated_at,
        "stocks": [],
        "priority_codes": [],
        "follow_codes": [],
        "observe_codes": [],
        "stock_count": 0,
    }
    screening_batch = {
        "trade_date": trade_date,
        "generated_at": generated_at,
        "candidates": [],
        "screening_summary": {},
        "market_regime": {},
        "candidate_count": 0,
        "pool_label": "全市场",
    }
    confirmation = {
        "trade_date": trade_date,
        "generated_at": generated_at,
        "validation_status": "ok",
        "confirmed": [],
        "downgraded": [],
        "fresh_candidates": [],
        "counts": {},
    }
    decision_brief = {
        "trade_date": trade_date,
        "generated_at": generated_at,
        "summary": {"main_theme": "test"},
        "focus": {},
        "paths": {},
    }
    quality_status = {
        "lanes": {
            "watchlist": {
                "validation_status": "ok",
                "checked_at": generated_at,
                "expected_timestamp": trade_date,
            },
            "aggressive": {
                "validation_status": "ok",
                "checked_at": generated_at,
                "expected_timestamp": trade_date,
            },
            "midday_confirmation": {
                "validation_status": "ok",
                "checked_at": generated_at,
                "expected_timestamp": trade_date,
            },
        }
    }
    return watchlist, screening_batch, confirmation, decision_brief, quality_status


class ReadinessAccountStateTests(unittest.TestCase):
    def test_research_mode_does_not_block_when_data_is_fresh(self) -> None:
        # Wednesday 2026-05-06 (post-holiday trading day), 10:00 local.
        now = datetime(2026, 5, 6, 10, 0, 0)
        artifacts = _fresh_artifacts("2026-05-06", "2026-05-06 09:30:00")
        result = readiness.compute_readiness(
            watchlist=artifacts[0],
            screening_batch=artifacts[1],
            confirmation=artifacts[2],
            decision_brief=artifacts[3],
            quality_status=artifacts[4],
            account_book={"mode": "research", "cash_balance": 0.0},
            today_action_decisions={"trade_dates": {}},
            now=now,
        )
        self.assertEqual(result["readiness_mode"], "live_ready")
        self.assertEqual(result["account_state"]["mode"], "research")
        self.assertFalse(result["account_state"]["ready_for_live_small"])

    def test_holiday_session_classified_correctly(self) -> None:
        # 2026-05-04 is Labor Day Monday — holiday, not weekend.
        now = datetime(2026, 5, 4, 10, 0, 0)
        artifacts = _fresh_artifacts("2026-04-30", "2026-04-30 16:00:00")
        result = readiness.compute_readiness(
            watchlist=artifacts[0],
            screening_batch=artifacts[1],
            confirmation=artifacts[2],
            decision_brief=artifacts[3],
            quality_status=artifacts[4],
            now=now,
        )
        self.assertEqual(result["session"]["calendar_status"], "holiday")
        self.assertEqual(result["readiness_mode"], "shadow_only")
        self.assertFalse(result["ready"])
        # The expected_trade_date should roll back to the most recent
        # trading day (2026-04-30) instead of pretending Monday is open.
        self.assertEqual(result["expected_trade_date"], "2026-04-30")

    def test_live_small_blocks_without_cash(self) -> None:
        now = datetime(2026, 5, 6, 10, 0, 0)
        artifacts = _fresh_artifacts("2026-05-06", "2026-05-06 09:30:00")
        result = readiness.compute_readiness(
            watchlist=artifacts[0],
            screening_batch=artifacts[1],
            confirmation=artifacts[2],
            decision_brief=artifacts[3],
            quality_status=artifacts[4],
            account_book={"mode": "live_small", "cash_balance": 0.0, "fills": []},
            today_action_decisions={"trade_dates": {}},
            now=now,
        )
        codes = [b["code"] for b in result["blockers"]]
        self.assertIn("account_cash_zero", codes)
        self.assertEqual(result["readiness_mode"], "blocked")

    def test_live_small_blocks_without_fresh_reconciliation(self) -> None:
        now = datetime(2026, 5, 6, 10, 0, 0)
        artifacts = _fresh_artifacts("2026-05-06", "2026-05-06 09:30:00")
        result = readiness.compute_readiness(
            watchlist=artifacts[0],
            screening_batch=artifacts[1],
            confirmation=artifacts[2],
            decision_brief=artifacts[3],
            quality_status=artifacts[4],
            account_book={
                "mode": "live_small",
                "cash_balance": 5000.0,
                "fills": [],
                "reconciliations": [
                    {"ts": "2026-04-15 10:00:00", "trade_date": "2026-04-15"},
                ],
            },
            today_action_decisions={"trade_dates": {}},
            now=now,
        )
        codes = [b["code"] for b in result["blockers"]]
        self.assertIn("account_reconcile_stale", codes)

    def test_live_small_blocks_with_unreconciled_done_action(self) -> None:
        now = datetime(2026, 5, 6, 10, 0, 0)
        artifacts = _fresh_artifacts("2026-05-06", "2026-05-06 09:30:00")
        decisions = {
            "trade_dates": {
                "2026-05-05": {
                    "wl-priority-sh600690": {
                        "decision": "done",
                        "updated_at": "2026-05-05 10:00:00",
                    }
                }
            }
        }
        result = readiness.compute_readiness(
            watchlist=artifacts[0],
            screening_batch=artifacts[1],
            confirmation=artifacts[2],
            decision_brief=artifacts[3],
            quality_status=artifacts[4],
            account_book={
                "mode": "live_small",
                "cash_balance": 10000.0,
                "fills": [],
                "no_fill_intents": [],
                "reconciliations": [
                    {"ts": "2026-05-06 09:00:00", "trade_date": "2026-05-06"}
                ],
            },
            today_action_decisions=decisions,
            now=now,
        )
        codes = [b["code"] for b in result["blockers"]]
        self.assertIn("account_unreconciled_intents", codes)
        self.assertGreater(len(result["account_state"]["unreconciled_intents"]), 0)

    def test_live_small_unblocked_when_done_has_matching_fill(self) -> None:
        now = datetime(2026, 5, 6, 10, 0, 0)
        artifacts = _fresh_artifacts("2026-05-06", "2026-05-06 09:30:00")
        decisions = {
            "trade_dates": {
                "2026-05-05": {
                    "wl-priority-sh600690": {
                        "decision": "done",
                        "updated_at": "2026-05-05 10:00:00",
                    }
                }
            }
        }
        result = readiness.compute_readiness(
            watchlist=artifacts[0],
            screening_batch=artifacts[1],
            confirmation=artifacts[2],
            decision_brief=artifacts[3],
            quality_status=artifacts[4],
            account_book={
                "mode": "live_small",
                "cash_balance": 10000.0,
                "fills": [
                    {
                        "trade_date": "2026-05-05",
                        "intent_key": "wl-priority-sh600690",
                        "code": "sh600690",
                        "side": "buy",
                        "qty": 100,
                        "price": 27.34,
                        "fees": 0.0,
                    }
                ],
                "no_fill_intents": [],
                "reconciliations": [
                    {"ts": "2026-05-06 09:00:00", "trade_date": "2026-05-06"}
                ],
            },
            today_action_decisions=decisions,
            now=now,
        )
        codes = [b["code"] for b in result["blockers"]]
        self.assertNotIn("account_unreconciled_intents", codes)
        self.assertEqual(result["account_state"]["unreconciled_intents"], [])
        self.assertTrue(result["account_state"]["ready_for_live_small"])
        self.assertEqual(result["readiness_mode"], "live_ready")

    def test_today_actions_do_not_block_intra_day(self) -> None:
        # A done decision on the same trading day must not be flagged
        # because the operator may still be entering the fill.
        now = datetime(2026, 5, 6, 10, 0, 0)
        artifacts = _fresh_artifacts("2026-05-06", "2026-05-06 09:30:00")
        decisions = {
            "trade_dates": {
                "2026-05-06": {
                    "wl-priority-sh600690": {"decision": "done", "updated_at": "2026-05-06 09:50:00"}
                }
            }
        }
        result = readiness.compute_readiness(
            watchlist=artifacts[0],
            screening_batch=artifacts[1],
            confirmation=artifacts[2],
            decision_brief=artifacts[3],
            quality_status=artifacts[4],
            account_book={
                "mode": "live_small",
                "cash_balance": 10000.0,
                "fills": [],
                "reconciliations": [
                    {"ts": "2026-05-06 09:00:00", "trade_date": "2026-05-06"}
                ],
            },
            today_action_decisions=decisions,
            now=now,
        )
        # cash + fresh recon + no past-day pendings → ready_for_live_small
        self.assertTrue(result["account_state"]["ready_for_live_small"])

    def test_account_book_omitted_falls_back_to_research(self) -> None:
        now = datetime(2026, 5, 6, 10, 0, 0)
        artifacts = _fresh_artifacts("2026-05-06", "2026-05-06 09:30:00")
        result = readiness.compute_readiness(
            watchlist=artifacts[0],
            screening_batch=artifacts[1],
            confirmation=artifacts[2],
            decision_brief=artifacts[3],
            quality_status=artifacts[4],
            now=now,
        )
        self.assertEqual(result["account_state"]["mode"], "research")
        self.assertFalse(result["account_state"]["ready_for_live_small"])

    def test_unknown_calendar_horizon_is_shadow_only(self) -> None:
        # 2030-05-06 is past CALENDAR_HORIZON.
        now = datetime(2030, 5, 6, 10, 0, 0)
        artifacts = _fresh_artifacts("2030-05-06", "2030-05-06 09:30:00")
        result = readiness.compute_readiness(
            watchlist=artifacts[0],
            screening_batch=artifacts[1],
            confirmation=artifacts[2],
            decision_brief=artifacts[3],
            quality_status=artifacts[4],
            now=now,
            expected_date="2030-05-06",
        )
        self.assertEqual(result["session"]["calendar_status"], "unknown")
        self.assertEqual(result["readiness_mode"], "shadow_only")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
