"""Integration tests guarding the account_mode × capability gate.

These tests pin down a single non-negotiable rule:

    `account_mode=research` MUST always return `trade.granted=false`
    regardless of how fresh the underlying market data is.

The original incident: "看起来都绿,但研究态不应该真的下单" — fresh
``quotes.batch`` / ``capital_flow.batch`` is not sufficient to grant trade;
the account-mode gate is independent of dataset freshness and must always
veto when the operator is still in research mode.

Mirror cases: shadow / live_small + fresh data + account_ready → trade
granted; live_small + fresh data + account NOT reconciled → trade blocked
with the account_not_reconciled reason (not a data freshness reason).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any


INVEST_FLOW_ROOT = Path(__file__).resolve().parents[2]
if str(INVEST_FLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(INVEST_FLOW_ROOT))

from capability_matrix import Capability, evaluate_capabilities  # noqa: E402


SOURCE_KEYS = ("watchlist", "screening", "confirmation", "decision_brief")
SOURCE_LABELS = {
    "watchlist": "自选股",
    "screening": "进攻型候选",
    "confirmation": "午盘承接确认",
    "decision_brief": "投资总控简报",
}
TRADE_CRITICAL_DATASETS = ("quotes.batch",)
TRADE_IMPORTANT_DATASETS = ("capital_flow.batch", "quotes.snapshot")


def _fresh_source_row(key: str) -> dict[str, Any]:
    return {
        "key": key,
        "label": SOURCE_LABELS.get(key, key),
        "available": True,
        "stale": False,
        "degraded": False,
        "stale_reasons": [],
        "degradation_reasons": [],
        "formal_decision_allowed": True,
        "manifest_path": "/tmp/fake.manifest.json",
    }


def _fresh_dataset_row(dataset: str) -> dict[str, Any]:
    return {
        "dataset": dataset,
        "key": dataset,
        "label": dataset,
        "value": "2026-05-23 09:35:00",
        "detail": "eastmoney",
        "available": True,
        "age_seconds": 30,
        "age_label": "30 秒前",
        "stale": False,
        "stale_after_seconds": 60,
        "trade_date": "2026-05-23",
        "stale_reasons": [],
        "dataset_manifest": True,
    }


def _payload(
    *,
    account_mode: str,
    account_ready_for_live_small: bool = True,
    recon_fresh: bool = True,
    ready: bool = True,
    formal_ready: bool = True,
) -> dict[str, Any]:
    """Build a readiness payload where every dataset is FRESH.

    The only varying levers are account-mode-related so each test isolates
    the gate behaviour from data-freshness behaviour.
    """
    return {
        "ready": ready,
        "readiness_mode": "live_ready",
        "formal_ready": formal_ready,
        "session": {"is_trading_day": True, "key": "morning", "label": "早盘"},
        "source_freshness": [_fresh_source_row(k) for k in SOURCE_KEYS],
        "dataset_freshness": [
            _fresh_dataset_row(name)
            for name in TRADE_CRITICAL_DATASETS + TRADE_IMPORTANT_DATASETS
        ],
        "blockers": [],
        "warnings": [],
        "stale_count": 0,
        "checked_at": "2026-05-23 09:35:00",
        "recommended_tasks": [],
        "account_state": {
            "mode": account_mode,
            "ready_for_live_small": account_ready_for_live_small,
            "reconciliation": {
                "fresh": recon_fresh,
                "age_seconds": 3600 if recon_fresh else 7 * 24 * 3600,
                "age_label": "1 小时前" if recon_fresh else "1 周前",
            },
            "blockers": [],
            "warnings": [],
            "recommended_tasks": [],
        },
    }


class ResearchModeAlwaysBlocksTradeTests(unittest.TestCase):
    """`account_mode=research` MUST veto trade no matter how fresh data is."""

    def test_trade_blocked_with_all_data_fresh(self) -> None:
        payload = _payload(account_mode="research", account_ready_for_live_small=False)
        result = evaluate_capabilities(readiness_payload=payload)

        trade = result["trade"]
        self.assertFalse(
            trade.granted,
            f"research-mode must block trade even with fresh data; why_not={trade.why_not}",
        )
        self.assertEqual(trade.status, "blocked")
        why_codes = {item.get("code") for item in trade.why_not}
        self.assertIn(
            "account_not_live",
            why_codes,
            f"trade must cite account-mode reason, got codes={why_codes}",
        )

    def test_blocking_sources_do_not_contain_data_when_only_account_gate_fails(self) -> None:
        """When every dataset is fresh, blocking_sources MUST be empty.

        The trade veto is account-mode, not data-freshness. The UI relies on
        an empty ``blocking_sources`` to render "research 态不下单" without
        misleadingly highlighting quotes.batch as "the blocker".
        """
        payload = _payload(account_mode="research", account_ready_for_live_small=False)
        result = evaluate_capabilities(readiness_payload=payload)

        trade = result["trade"]
        self.assertFalse(trade.granted)
        self.assertEqual(
            trade.blocking_sources,
            [],
            f"no dataset is stale; blocking_sources should be empty, got={trade.blocking_sources}",
        )

    def test_observe_and_review_still_granted_in_research_mode(self) -> None:
        payload = _payload(account_mode="research", account_ready_for_live_small=False)
        result = evaluate_capabilities(readiness_payload=payload)

        self.assertTrue(result["observe"].granted, "research mode must still allow observation")
        self.assertTrue(result["review"].granted, "research mode must still allow review")

    def test_ledger_capture_blocked_in_research_mode(self) -> None:
        payload = _payload(account_mode="research", account_ready_for_live_small=False)
        result = evaluate_capabilities(readiness_payload=payload)

        ledger = result["ledger_capture"]
        self.assertFalse(ledger.granted, "research mode must block ledger_capture")
        why_codes = {item.get("code") for item in ledger.why_not}
        self.assertIn("ledger_capture_research", why_codes)

    def test_research_mode_with_account_ready_true_still_blocks_trade(self) -> None:
        """Even if ``ready_for_live_small`` is somehow true while in research, block."""
        payload = _payload(account_mode="research", account_ready_for_live_small=True)
        result = evaluate_capabilities(readiness_payload=payload)
        self.assertFalse(result["trade"].granted)


class ShadowAndLiveSmallTradeFlowTests(unittest.TestCase):
    """Mirror tests: shadow / live_small with fresh data and account ready."""

    def test_shadow_mode_with_fresh_data_grants_trade(self) -> None:
        payload = _payload(account_mode="shadow", account_ready_for_live_small=True)
        result = evaluate_capabilities(readiness_payload=payload)

        trade = result["trade"]
        self.assertTrue(
            trade.granted,
            f"shadow mode with all-fresh data must grant trade; why_not={trade.why_not}",
        )
        self.assertEqual(trade.status, "ok")

    def test_live_small_with_fresh_data_and_reconciled_grants_trade(self) -> None:
        payload = _payload(
            account_mode="live_small",
            account_ready_for_live_small=True,
            recon_fresh=True,
        )
        result = evaluate_capabilities(readiness_payload=payload)

        trade = result["trade"]
        self.assertTrue(trade.granted, f"why_not={trade.why_not}")
        self.assertEqual(trade.status, "ok")

    def test_live_small_with_fresh_data_but_unreconciled_blocks_trade(self) -> None:
        payload = _payload(
            account_mode="live_small",
            account_ready_for_live_small=False,
            recon_fresh=False,
        )
        result = evaluate_capabilities(readiness_payload=payload)

        trade = result["trade"]
        self.assertFalse(trade.granted, "unreconciled live_small must not trade")
        why_codes = {item.get("code") for item in trade.why_not}
        self.assertIn(
            "account_not_reconciled",
            why_codes,
            f"trade should cite reconciliation gap, got codes={why_codes}",
        )
        # Critical: the veto reason is NOT a data-freshness reason.
        for item in trade.why_not:
            code = str(item.get("code") or "")
            self.assertFalse(
                code.endswith(("_STALE", "_INVALID", "_BLOCKED", "_DEGRADED")),
                f"unexpected data-freshness reason on a reconciliation block: {code}",
            )


class AccountModeIndependenceOfDataFreshnessTests(unittest.TestCase):
    """Account-mode veto is orthogonal to data freshness.

    These tests guard against accidental drift where someone "ungates"
    research mode when quotes.batch is fresh, or "regates" research mode
    when quotes.batch is stale (it should always be vetoed regardless).
    """

    def test_research_mode_is_blocked_across_all_data_freshness_combinations(self) -> None:
        # All four combinations of (quotes.batch fresh/stale) × (capital_flow.batch fresh/stale)
        # — in every case research mode MUST block trade.
        for quotes_fresh in (True, False):
            for capflow_fresh in (True, False):
                with self.subTest(quotes_fresh=quotes_fresh, capflow_fresh=capflow_fresh):
                    dataset_rows = [_fresh_dataset_row(name) for name in TRADE_CRITICAL_DATASETS]
                    if not quotes_fresh:
                        dataset_rows[0]["stale"] = True
                        dataset_rows[0]["stale_reasons"] = ["freshness_stale"]
                    capflow_row = _fresh_dataset_row("capital_flow.batch")
                    if not capflow_fresh:
                        capflow_row["stale"] = True
                        capflow_row["stale_reasons"] = ["freshness_stale"]
                    dataset_rows.append(capflow_row)

                    payload = _payload(account_mode="research", account_ready_for_live_small=False)
                    payload["dataset_freshness"] = dataset_rows

                    result = evaluate_capabilities(readiness_payload=payload)
                    self.assertFalse(
                        result["trade"].granted,
                        "research mode must block trade regardless of dataset freshness combo",
                    )
                    why_codes = {item.get("code") for item in result["trade"].why_not}
                    self.assertIn(
                        "account_not_live",
                        why_codes,
                        "research mode must always cite account_not_live, even when data is also stale",
                    )


if __name__ == "__main__":
    unittest.main()
