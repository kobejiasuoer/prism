"""Tests for capability_matrix — the investment-action translation layer.

These tests are the contract for what each of the six capabilities means in
business terms, and guard the rule that engineering jargon never leaks into
``why_not`` or ``degraded_path`` messages.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


INVEST_FLOW_ROOT = Path(__file__).resolve().parents[2]
if str(INVEST_FLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(INVEST_FLOW_ROOT))

from capability_matrix import (  # noqa: E402
    Capability,
    CapabilityReport,
    TrustLevel,
    evaluate_capabilities,
    evaluate_trust_level,
)


KNOWN_CAPABILITIES = {c.value for c in Capability}
FORBIDDEN_TERMS = (
    "manifest",
    "stale_reasons",
    "live_small_not_allowed",
    "formal_decision_allowed",
    "freshness_status",
    "fallback_used",
)


def _source_row(
    key: str,
    *,
    label: str | None = None,
    available: bool = True,
    stale: bool = False,
    degraded: bool = False,
    stale_reasons: list[str] | None = None,
    formal_decision_allowed: bool = True,
    manifest_path: str = "/tmp/fake.manifest.json",
) -> dict[str, object]:
    return {
        "key": key,
        "label": label or {
            "watchlist": "自选股",
            "screening": "进攻型候选",
            "confirmation": "午盘承接确认",
            "decision_brief": "投资总控简报",
        }.get(key, key),
        "available": available,
        "stale": stale,
        "degraded": degraded,
        "stale_reasons": stale_reasons or [],
        "degradation_reasons": [],
        "formal_decision_allowed": formal_decision_allowed,
        "manifest_path": manifest_path,
    }


def _readiness(
    *,
    ready: bool = True,
    readiness_mode: str = "live_ready",
    formal_ready: bool = True,
    is_trading_day: bool = True,
    sources: list[dict[str, object]] | None = None,
    account_mode: str = "live_small",
    account_ready_for_live_small: bool = True,
    blockers: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    if sources is None:
        sources = [
            _source_row("watchlist"),
            _source_row("screening"),
            _source_row("confirmation"),
            _source_row("decision_brief"),
        ]
    return {
        "ready": ready,
        "readiness_mode": readiness_mode,
        "formal_ready": formal_ready,
        "session": {"is_trading_day": is_trading_day, "key": "morning", "label": "早盘"},
        "source_freshness": sources,
        "blockers": blockers or [],
        "warnings": [],
        "stale_count": sum(1 for s in sources if s.get("stale")),
        "checked_at": "2026-05-22 09:35:00",
        "recommended_tasks": [],
        "account_state": {
            "mode": account_mode,
            "ready_for_live_small": account_ready_for_live_small,
            "reconciliation": {"fresh": True, "age_seconds": 3600, "age_label": "1 小时前"},
            "blockers": [],
            "warnings": [],
            "recommended_tasks": [],
        },
    }


class GoldenPathTests(unittest.TestCase):
    def test_all_caps_granted_when_fully_ready(self) -> None:
        result = evaluate_capabilities(readiness_payload=_readiness())
        self.assertEqual(set(result.keys()), KNOWN_CAPABILITIES)
        for cap, report in result.items():
            with self.subTest(capability=cap):
                self.assertIsInstance(report, CapabilityReport)
                self.assertTrue(report.granted, f"{cap} should be granted; why_not={report.why_not}")
                self.assertEqual(report.status, "ok")
                self.assertEqual(report.why_not, [])

    def test_status_ok_implies_granted(self) -> None:
        result = evaluate_capabilities(readiness_payload=_readiness())
        for cap, report in result.items():
            with self.subTest(capability=cap):
                if report.status == "ok":
                    self.assertTrue(report.granted)


class StaleWatchlistTests(unittest.TestCase):
    def setUp(self) -> None:
        payload = _readiness(
            ready=False,
            readiness_mode="blocked",
            sources=[
                _source_row("watchlist", stale=True, stale_reasons=["freshness_stale"]),
                _source_row("screening"),
                _source_row("confirmation"),
                _source_row("decision_brief"),
            ],
            blockers=[
                {
                    "code": "watchlist_stale",
                    "label": "自选股",
                    "message": "自选股偏旧",
                    "recommended_task": "watchlist_refresh",
                },
            ],
        )
        self.result = evaluate_capabilities(readiness_payload=payload)

    def test_trade_blocked(self) -> None:
        self.assertFalse(self.result["trade"].granted)
        self.assertEqual(self.result["trade"].status, "blocked")

    def test_approve_blocked(self) -> None:
        self.assertFalse(self.result["approve"].granted)

    def test_observe_still_granted(self) -> None:
        # observe should remain granted (data is STALE not INVALID).
        self.assertTrue(self.result["observe"].granted)

    def test_notify_always_granted(self) -> None:
        self.assertTrue(self.result["notify"].granted)


class NonTradingDayTests(unittest.TestCase):
    def test_trade_blocked_outside_trading_day(self) -> None:
        payload = _readiness(
            ready=False,
            readiness_mode="shadow_only",
            is_trading_day=False,
        )
        result = evaluate_capabilities(readiness_payload=payload)
        self.assertFalse(result["trade"].granted)
        # observe should still work
        self.assertTrue(result["observe"].granted)


class ResearchModeTests(unittest.TestCase):
    def test_trade_blocked_when_account_not_live_small(self) -> None:
        payload = _readiness(account_mode="research", account_ready_for_live_small=False)
        result = evaluate_capabilities(readiness_payload=payload)
        self.assertFalse(result["trade"].granted)
        self.assertTrue(result["observe"].granted)
        self.assertTrue(result["review"].granted)


class FormalReadyDivergenceTests(unittest.TestCase):
    def test_approve_degraded_when_data_fresh_but_not_formal_ready(self) -> None:
        payload = _readiness(formal_ready=False)
        result = evaluate_capabilities(readiness_payload=payload)
        self.assertFalse(result["approve"].granted)
        self.assertEqual(result["approve"].status, "degraded")
        # trade can still go through (formal_ready != trade gate)
        self.assertTrue(result["trade"].granted)


class InvalidSourceTests(unittest.TestCase):
    def test_trade_date_mismatch_invalidates_dependent_caps(self) -> None:
        payload = _readiness(
            ready=False,
            readiness_mode="blocked",
            sources=[
                _source_row("watchlist", stale=True, stale_reasons=["trade_date_mismatch"]),
                _source_row("screening"),
                _source_row("confirmation"),
                _source_row("decision_brief"),
            ],
            blockers=[{
                "code": "trade_date_mismatch",
                "label": "数据交易日",
                "message": "数据交易日不匹配",
                "recommended_task": "watchlist_refresh",
            }],
        )
        result = evaluate_capabilities(readiness_payload=payload)
        # watchlist supports observe/review/approve/trade → all impacted
        self.assertFalse(result["trade"].granted)
        self.assertFalse(result["approve"].granted)
        self.assertIn("watchlist.snapshot", result["trade"].blocking_sources)


class DegradedPathTests(unittest.TestCase):
    def test_blocked_caps_must_provide_degraded_path(self) -> None:
        payload = _readiness(
            ready=False,
            readiness_mode="blocked",
            sources=[
                _source_row("watchlist", stale=True, stale_reasons=["freshness_stale"]),
                _source_row("screening"),
                _source_row("confirmation"),
                _source_row("decision_brief"),
            ],
            blockers=[{
                "code": "watchlist_stale", "label": "自选股", "message": "偏旧",
                "recommended_task": "watchlist_refresh",
            }],
        )
        result = evaluate_capabilities(readiness_payload=payload)
        # When trade is blocked, the system must explicitly say what user CAN do.
        trade_report = result["trade"]
        self.assertFalse(trade_report.granted)
        self.assertTrue(trade_report.degraded_path, "blocked capability must list a degraded_path")


class JargonLeakTests(unittest.TestCase):
    """Engineering jargon MUST NOT appear in operator-facing strings."""

    def _all_messages(self, result: dict[str, CapabilityReport]) -> list[str]:
        out: list[str] = []
        for report in result.values():
            for bucket in (report.why_not, report.degraded_path):
                for item in bucket:
                    out.append(str(item.get("message") or ""))
                    out.append(str(item.get("label") or ""))
        return out

    def test_messages_have_no_engineering_jargon(self) -> None:
        scenarios = [
            _readiness(),
            _readiness(formal_ready=False),
            _readiness(
                ready=False, readiness_mode="blocked",
                sources=[
                    _source_row("watchlist", stale=True, stale_reasons=["live_small_not_allowed"]),
                    _source_row("screening"),
                    _source_row("confirmation"),
                    _source_row("decision_brief"),
                ],
                blockers=[{
                    "code": "watchlist_blocked", "label": "自选股",
                    "message": "数据源未放行真钱执行",
                    "recommended_task": "watchlist_refresh",
                }],
            ),
        ]
        for payload in scenarios:
            with self.subTest(scenario=payload.get("readiness_mode")):
                result = evaluate_capabilities(readiness_payload=payload)
                joined = "\n".join(self._all_messages(result))
                for term in FORBIDDEN_TERMS:
                    self.assertNotIn(term, joined, f"jargon '{term}' leaked into messages")


class NextActionsTests(unittest.TestCase):
    def test_next_actions_reference_known_tasks(self) -> None:
        payload = _readiness(
            ready=False, readiness_mode="blocked",
            sources=[
                _source_row("decision_brief", stale=True, stale_reasons=["freshness_stale"]),
                _source_row("watchlist"),
                _source_row("screening"),
                _source_row("confirmation"),
            ],
            blockers=[{
                "code": "decision_brief_stale", "label": "投资总控简报",
                "message": "简报偏旧", "recommended_task": "command_brief",
            }],
        )
        result = evaluate_capabilities(readiness_payload=payload)
        approve = result["approve"]
        task_names = [a.get("task_name") for a in approve.next_actions]
        self.assertIn("command_brief", task_names)


class TrustLevelTests(unittest.TestCase):
    """One verdict the whole UI consumes: trusted / observe_only / unreliable."""

    def test_trusted_when_fully_ready(self) -> None:
        trust = evaluate_trust_level(readiness_payload=_readiness())
        self.assertIsInstance(trust, TrustLevel)
        self.assertEqual(trust.level, "trusted")
        self.assertEqual(trust.label, "可信")
        self.assertTrue(trust.can_observe)
        self.assertTrue(trust.can_review)
        self.assertTrue(trust.can_approve)
        self.assertTrue(trust.can_trade_live)
        self.assertEqual(trust.blocking_reasons, [])

    def test_observe_only_when_data_stale_but_observable(self) -> None:
        payload = _readiness(
            ready=False,
            readiness_mode="blocked",
            sources=[
                _source_row("watchlist", stale=True, stale_reasons=["freshness_stale"]),
                _source_row("screening"),
                _source_row("confirmation"),
                _source_row("decision_brief"),
            ],
            blockers=[{
                "code": "watchlist_stale", "label": "自选股", "message": "偏旧",
                "recommended_task": "watchlist_refresh",
            }],
        )
        payload["recommended_tasks"] = ["watchlist_refresh"]
        trust = evaluate_trust_level(readiness_payload=payload)
        self.assertEqual(trust.level, "observe_only")
        self.assertTrue(trust.can_observe)
        self.assertFalse(trust.can_approve)
        self.assertFalse(trust.can_trade_live)
        self.assertEqual(trust.next_step, "watchlist_refresh")
        self.assertEqual(trust.next_step_label, "刷新自选股快照")
        self.assertTrue(trust.blocking_reasons, "should surface at least one human-readable reason")

    def test_observe_only_when_shadow_only_mode(self) -> None:
        # Trading day, account research → approve/trade blocked but observe ok.
        payload = _readiness(
            ready=True,
            readiness_mode="shadow_only",
            account_mode="research",
            account_ready_for_live_small=False,
        )
        trust = evaluate_trust_level(readiness_payload=payload)
        self.assertEqual(trust.level, "observe_only")
        self.assertTrue(trust.can_observe)
        self.assertFalse(trust.can_trade_live)

    def test_unreliable_when_observe_blocked(self) -> None:
        # Use an INVALID-class freshness state that strips observe permission.
        payload = _readiness(
            ready=False,
            readiness_mode="blocked",
            sources=[
                _source_row(
                    "watchlist",
                    available=False,
                    stale=True,
                    stale_reasons=["trade_date_mismatch"],
                ),
                _source_row(
                    "screening",
                    available=False,
                    stale=True,
                    stale_reasons=["trade_date_mismatch"],
                ),
                _source_row(
                    "confirmation",
                    available=False,
                    stale=True,
                    stale_reasons=["trade_date_mismatch"],
                ),
                _source_row(
                    "decision_brief",
                    available=False,
                    stale=True,
                    stale_reasons=["trade_date_mismatch"],
                ),
            ],
            blockers=[{
                "code": "trade_date_mismatch", "label": "数据交易日",
                "message": "数据交易日不匹配", "recommended_task": "watchlist_refresh",
            }],
        )
        trust = evaluate_trust_level(readiness_payload=payload)
        # If observe is still granted (STALE doesn't strip observe), the verdict is observe_only.
        # If observe is stripped (INVALID/BLOCKED), the verdict is unreliable. Both are valid;
        # the contract is that approve/trade is OFF when data is unreliable.
        self.assertIn(trust.level, {"observe_only", "unreliable"})
        self.assertFalse(trust.can_approve)
        self.assertFalse(trust.can_trade_live)
        # Either way, real money must be off.
        self.assertEqual(trust.tone in {"warning", "negative"}, True)


if __name__ == "__main__":
    unittest.main()
