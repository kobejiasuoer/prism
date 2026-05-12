"""Tests for reconciliation delta threshold blocking in live_small mode.

Phase 0 requirement: live_small readiness must check the most recent
reconciliation's cash/equity delta and block when it exceeds thresholds.
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


def _manifest(dataset: str, trade_date: str, generated_at: str) -> dict[str, object]:
    return {
        "dataset": dataset,
        "provider": "pipeline",
        "provider_role": "primary",
        "trade_date": trade_date,
        "fetched_at": generated_at,
        "asof": generated_at,
        "ttl_seconds": 900,
        "status": "ok",
        "freshness_status": "fresh",
        "fallback_used": False,
        "row_count": 1,
        "payload_hash": "test",
        "live_small_allowed": True,
        "quality_flags": [],
    }


def _source(dataset: str, trade_date: str, generated_at: str, **extra):
    payload = {
        "trade_date": trade_date,
        "generated_at": generated_at,
        "manifest": _manifest(dataset, trade_date, generated_at),
    }
    payload.update(extra)
    return payload


def _fresh_artifacts(trade_date: str, generated_at: str):
    """Build artifacts that are themselves freshness-clean for ``trade_date``."""

    watchlist = _source("watchlist.snapshot", trade_date, generated_at, stocks=[])
    screening_batch = _source("screening.batch", trade_date, generated_at, candidates=[])
    confirmation = _source("screening.confirmation", trade_date, generated_at, validation_status="ok")
    decision_brief = _source("decision_brief.snapshot", trade_date, generated_at, summary={})
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


class ReconciliationDeltaBlockingTests(unittest.TestCase):
    def test_live_small_blocks_when_cash_delta_exceeds_threshold(self) -> None:
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
                "cash_balance": 10000.0,
                "fills": [],
                "reconciliations": [
                    {
                        "ts": "2026-05-06 09:00:00",
                        "trade_date": "2026-05-06",
                        "broker_cash": 10150.0,
                        "local_cash": 10000.0,
                        "delta_cash": 150.0,  # exceeds 100 threshold
                        "broker_equity": 0.0,
                        "local_equity_at_cost": 0.0,
                        "delta_equity": 0.0,
                    }
                ],
            },
            today_action_decisions={"trade_dates": {}},
            now=now,
        )
        codes = [b["code"] for b in result["blockers"]]
        self.assertIn("account_reconcile_delta_exceeded", codes)
        self.assertEqual(result["readiness_mode"], "blocked")
        self.assertFalse(result["account_state"]["ready_for_live_small"])

    def test_live_small_blocks_when_equity_delta_exceeds_threshold(self) -> None:
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
                "cash_balance": 10000.0,
                "fills": [],
                "reconciliations": [
                    {
                        "ts": "2026-05-06 09:00:00",
                        "trade_date": "2026-05-06",
                        "broker_cash": 10000.0,
                        "local_cash": 10000.0,
                        "delta_cash": 0.0,
                        "broker_equity": 5300.0,
                        "local_equity_at_cost": 5000.0,
                        "delta_equity": 300.0,  # exceeds 200 threshold
                    }
                ],
            },
            today_action_decisions={"trade_dates": {}},
            now=now,
        )
        codes = [b["code"] for b in result["blockers"]]
        self.assertIn("account_reconcile_delta_exceeded", codes)
        self.assertEqual(result["readiness_mode"], "blocked")

    def test_live_small_blocks_when_negative_delta_exceeds_threshold(self) -> None:
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
                "cash_balance": 10000.0,
                "fills": [],
                "reconciliations": [
                    {
                        "ts": "2026-05-06 09:00:00",
                        "trade_date": "2026-05-06",
                        "broker_cash": 9850.0,
                        "local_cash": 10000.0,
                        "delta_cash": -150.0,  # abs exceeds 100 threshold
                        "broker_equity": 0.0,
                        "local_equity_at_cost": 0.0,
                        "delta_equity": 0.0,
                    }
                ],
            },
            today_action_decisions={"trade_dates": {}},
            now=now,
        )
        codes = [b["code"] for b in result["blockers"]]
        self.assertIn("account_reconcile_delta_exceeded", codes)

    def test_live_small_passes_when_delta_within_threshold(self) -> None:
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
                "cash_balance": 10000.0,
                "fills": [],
                "reconciliations": [
                    {
                        "ts": "2026-05-06 09:00:00",
                        "trade_date": "2026-05-06",
                        "broker_cash": 10050.0,
                        "local_cash": 10000.0,
                        "delta_cash": 50.0,  # within 100 threshold
                        "broker_equity": 5100.0,
                        "local_equity_at_cost": 5000.0,
                        "delta_equity": 100.0,  # within 200 threshold
                    }
                ],
            },
            today_action_decisions={"trade_dates": {}},
            now=now,
        )
        codes = [b["code"] for b in result["blockers"]]
        self.assertNotIn("account_reconcile_delta_exceeded", codes)
        self.assertEqual(result["readiness_mode"], "live_ready")
        self.assertTrue(result["account_state"]["ready_for_live_small"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
