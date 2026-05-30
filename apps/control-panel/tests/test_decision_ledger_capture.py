"""Tests for Decision Ledger capture from the Today action queue (Phase 2).

These tests cover the pure builder that converts a Today action item into
a ``DecisionRecord`` draft, plus the idempotent capture function and the
POST /api/decision-ledger/capture endpoint.

We do not exercise ``build_today_view`` here -- it is too heavy and pulls
in screening / decision-brief artifacts that have nothing to do with the
ledger contract.  Instead we feed the capture function fixture
``today_view``-shaped payloads.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


CONTROL_PANEL_ROOT = Path(__file__).resolve().parents[1]
if str(CONTROL_PANEL_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROL_PANEL_ROOT))


def _make_action_item(
    *,
    key: str,
    title: str,
    status: str,
    detail: str,
    foot: str = "",
    metrics: list[str] | None = None,
    source: str = "自选股链路",
    tone: str = "watch",
    group_key: str = "do-now",
    group_title: str = "Do Now",
    lane_key: str = "watchlist",
    actionable: bool = True,
    trust_blockers: list[dict] | None = None,
    trust_warnings: list[dict] | None = None,
) -> dict:
    """Return a dict shaped like one entry in ``today_view.action_queue.items``."""

    return {
        "key": key,
        "title": title,
        "source": source,
        "status": status,
        "tone": tone,
        "detail": detail,
        "foot": foot,
        "metrics": metrics or [],
        "url": None,
        "group_key": group_key,
        "group_title": group_title,
        "group_index": 1,
        "lane_key": lane_key,
        "freshness": {"value": "", "label": "-"},
        "confidence": {"status": "ok", "label": "可信"},
        "decision": {"status": "pending", "label": "待处理"},
        "display_state": {"value": "pending", "updated_at_raw": ""},
        "trust": {
            "trusted": actionable,
            "blockers": list(trust_blockers or []),
            "warnings": list(trust_warnings or []),
        },
        "actionable": actionable,
    }


def _today_view_with_items(
    *,
    items: list[dict],
    stale_items: list[dict] | None = None,
    trade_date: str = "2026-05-15",
    expected_trade_date: str | None = None,
    readiness_mode: str = "live_ready",
    readiness_ready: bool = True,
) -> dict:
    return {
        "trade_date": trade_date,
        "expected_trade_date": expected_trade_date or trade_date,
        "data_trade_date": trade_date,
        "readiness": {
            "readiness_mode": readiness_mode,
            "ready": readiness_ready,
        },
        "action_queue": {
            "items": items,
            "stale_items": stale_items or [],
        },
    }


class TodayActionCaptureTests(unittest.TestCase):
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

    # --------------------------------------------------------- action enum

    def test_normalize_today_action_maps_chinese_status_to_enum(self) -> None:
        """The recommendation.action field must be a stable enum, not the
        Chinese display label, so downstream filters and joins do not
        depend on exact wording.
        """

        cases = [
            ("继续持有", "hold"),
            ("持有", "hold"),
            ("减仓", "reduce"),
            ("卖出", "reduce"),
            ("降低仓位", "reduce"),
            ("重点观察", "observe"),
            ("观察", "observe"),
            ("跟踪", "observe"),
            ("待确认", "observe"),
            ("轻仓试错", "trial_buy"),
            ("买入", "trial_buy"),
            ("试错", "trial_buy"),
            ("放弃", "skip"),
            ("跳过", "skip"),
            ("禁止", "forbid"),
            ("不可执行", "forbid"),
            ("冻结", "forbid"),
            ("", "unknown"),
            ("外星人语言", "unknown"),
        ]
        for status, expected in cases:
            with self.subTest(status=status):
                self.assertEqual(
                    self.ledger.normalize_today_action(status),
                    expected,
                )

    def test_normalize_today_action_falls_back_to_group_key(self) -> None:
        self.assertEqual(
            self.ledger.normalize_today_action("", group_key="watch"),
            "observe",
        )
        self.assertEqual(
            self.ledger.normalize_today_action("", group_key="avoid"),
            "forbid",
        )
        self.assertEqual(
            self.ledger.normalize_today_action("", group_key="do-now"),
            "unknown",
        )

    def test_normalize_today_action_returns_known_enum(self) -> None:
        for value in ("hold", "reduce", "observe", "trial_buy", "skip", "forbid", "unknown"):
            self.assertIn(value, self.ledger.ACTION_ENUM)

    # --------------------------------------------------------- pure builder

    def test_build_decision_record_uses_action_enum_not_chinese_label(self) -> None:
        item = _make_action_item(
            key="watchlist:600690",
            title="海尔智家 600690",
            status="继续持有",
            detail="趋势线尚未破，保持仓位",
        )
        record = self.ledger.build_decision_record_from_today_item(
            item,
            trade_date="2026-05-15",
            expected_trade_date="2026-05-15",
            data_trade_date="2026-05-15",
            readiness_mode="live_ready",
            readiness_ready=True,
        )
        self.assertEqual(record["recommendation"]["action"], "hold")
        self.assertEqual(record["recommendation"]["action_label"], "继续持有")
        self.assertEqual(record["recommendation"]["action_raw"], "继续持有")

    def test_build_decision_record_id_is_stable_across_chinese_phrasing(self) -> None:
        """Two queue rows that mean the same thing in Chinese should
        collapse to one decision once the action enum normalizes them.
        """

        a = _make_action_item(
            key="watchlist:600690",
            title="海尔智家 600690",
            status="继续持有",
            detail="x",
        )
        b = _make_action_item(
            key="watchlist:600690",
            title="海尔智家 600690",
            status="持有",
            detail="x",
        )
        kwargs = {
            "trade_date": "2026-05-15",
            "expected_trade_date": "2026-05-15",
            "data_trade_date": "2026-05-15",
            "readiness_mode": "live_ready",
            "readiness_ready": True,
        }
        ra = self.ledger.build_decision_record_from_today_item(a, **kwargs)
        rb = self.ledger.build_decision_record_from_today_item(b, **kwargs)
        self.assertEqual(ra["recommendation"]["action"], "hold")
        self.assertEqual(rb["recommendation"]["action"], "hold")
        self.assertEqual(ra["decision_id"], rb["decision_id"])

    def test_build_decision_record_carries_factor_snapshot(self) -> None:
        record = self.ledger.build_decision_record(
            trade_date="2026-05-15",
            code="sh600519",
            name="贵州茅台",
            lane="screening",
            surface="today_action",
            action_key="screening:600519",
            action="observe",
            factor_snapshot={
                "tushare_score": 72.0,
                "factor_snapshot": {"valuation": {"pe_ttm": 28.0}},
            },
        )
        self.assertEqual(record["factor_snapshot"]["tushare_score"], 72.0)

    def test_build_decision_record_factor_snapshot_defaults_none(self) -> None:
        record = self.ledger.build_decision_record(
            trade_date="2026-05-15",
            code="sh600519",
            name="贵州茅台",
            lane="screening",
            surface="today_action",
            action_key="screening:600519",
            action="observe",
        )
        self.assertIsNone(record["factor_snapshot"])

    def test_build_decision_record_from_today_item_basic_fields(self) -> None:
        item = _make_action_item(
            key="watchlist:600690",
            title="海尔智家 600690",
            status="继续持有",
            detail="趋势线尚未破，保持仓位",
            foot="弱市中只按纪律处理",
            metrics=["仓位 半仓", "信号 维持", "止损 跌破均线"],
            lane_key="watchlist",
            source="自选股链路",
        )
        record = self.ledger.build_decision_record_from_today_item(
            item,
            trade_date="2026-05-15",
            expected_trade_date="2026-05-15",
            data_trade_date="2026-05-15",
            readiness_mode="live_ready",
            readiness_ready=True,
        )

        self.assertEqual(record["stock"]["code"], "sh600690")
        self.assertEqual(record["stock"]["name"], "海尔智家")
        self.assertEqual(record["source"]["lane"], "watchlist")
        self.assertEqual(record["source"]["surface"], "today_action_queue")
        self.assertEqual(record["source"]["action_key"], "watchlist:600690")
        self.assertEqual(record["recommendation"]["action_label"], "继续持有")
        self.assertIn("趋势线", record["recommendation"]["main_conclusion"])
        self.assertEqual(record["recommendation"]["risk_summary"], "弱市中只按纪律处理")
        self.assertEqual(record["trade_date"], "2026-05-15")
        self.assertEqual(record["evidence_snapshot"]["readiness_mode"], "live_ready")
        self.assertTrue(record["evidence_snapshot"]["readiness_ready"])

    def test_build_decision_record_infers_market_prefix_for_shenzhen(self) -> None:
        item = _make_action_item(
            key="screening:000001",
            title="平安银行 000001",
            status="重点观察",
            detail="低位震荡待变盘",
            lane_key="aggressive",
        )
        record = self.ledger.build_decision_record_from_today_item(
            item,
            trade_date="2026-05-15",
            expected_trade_date="2026-05-15",
            data_trade_date="2026-05-15",
            readiness_mode="live_ready",
            readiness_ready=True,
        )
        self.assertEqual(record["stock"]["code"], "sz000001")
        self.assertEqual(record["stock"]["name"], "平安银行")

    def test_build_decision_record_preserves_trust_context(self) -> None:
        item = _make_action_item(
            key="watchlist:600690",
            title="海尔智家 600690",
            status="继续持有",
            detail="趋势线尚未破，保持仓位",
            actionable=False,
            trust_blockers=[{"key": "freshness", "message": "数据不新鲜"}],
            trust_warnings=[{"key": "confidence", "message": "链路告警"}],
        )
        record = self.ledger.build_decision_record_from_today_item(
            item,
            trade_date="2026-05-15",
            expected_trade_date="2026-05-15",
            data_trade_date="2026-05-15",
            readiness_mode="shadow_only",
            readiness_ready=False,
        )
        self.assertFalse(record["evidence_snapshot"]["readiness_ready"])
        self.assertEqual(record["evidence_snapshot"]["readiness_mode"], "shadow_only")
        self.assertEqual(
            [b.get("message") for b in record["evidence_snapshot"]["blockers"]],
            ["数据不新鲜"],
        )
        self.assertEqual(
            [w.get("message") for w in record["evidence_snapshot"]["warnings"]],
            ["链路告警"],
        )

    def test_build_decision_record_normalizes_action_for_stability(self) -> None:
        """Two items with the same key+status produce the same decision_id."""

        a = _make_action_item(
            key="watchlist:600690",
            title="海尔智家 600690",
            status="继续持有",
            detail="趋势线尚未破",
        )
        b = _make_action_item(
            key="watchlist:600690",
            title="海尔智家 600690",
            status="继续持有",
            detail="文案微调，并不材料化",
        )

        record_a = self.ledger.build_decision_record_from_today_item(
            a,
            trade_date="2026-05-15",
            expected_trade_date="2026-05-15",
            data_trade_date="2026-05-15",
            readiness_mode="live_ready",
            readiness_ready=True,
        )
        record_b = self.ledger.build_decision_record_from_today_item(
            b,
            trade_date="2026-05-15",
            expected_trade_date="2026-05-15",
            data_trade_date="2026-05-15",
            readiness_mode="live_ready",
            readiness_ready=True,
        )
        self.assertEqual(record_a["decision_id"], record_b["decision_id"])

    def test_build_decision_record_action_change_breaks_id(self) -> None:
        """A material status change yields a new decision_id."""

        a = _make_action_item(
            key="watchlist:600690",
            title="海尔智家 600690",
            status="继续持有",
            detail="x",
        )
        b = _make_action_item(
            key="watchlist:600690",
            title="海尔智家 600690",
            status="减仓",
            detail="x",
        )
        kwargs = {
            "trade_date": "2026-05-15",
            "expected_trade_date": "2026-05-15",
            "data_trade_date": "2026-05-15",
            "readiness_mode": "live_ready",
            "readiness_ready": True,
        }
        ra = self.ledger.build_decision_record_from_today_item(a, **kwargs)
        rb = self.ledger.build_decision_record_from_today_item(b, **kwargs)
        self.assertNotEqual(ra["decision_id"], rb["decision_id"])

    def test_build_decision_record_rejects_invalid_key(self) -> None:
        item = _make_action_item(
            key="not_a_real_key",
            title="???",
            status="???",
            detail="???",
        )
        with self.assertRaises(self.ledger.DecisionLedgerError):
            self.ledger.build_decision_record_from_today_item(
                item,
                trade_date="2026-05-15",
                expected_trade_date="2026-05-15",
                data_trade_date="2026-05-15",
                readiness_mode="live_ready",
                readiness_ready=True,
            )

    # ------------------------------------------------- capture orchestration

    def test_capture_writes_record_per_action_queue_item(self) -> None:
        view = _today_view_with_items(
            items=[
                _make_action_item(
                    key="watchlist:600690",
                    title="海尔智家 600690",
                    status="继续持有",
                    detail="趋势线尚未破",
                ),
                _make_action_item(
                    key="screening:000001",
                    title="平安银行 000001",
                    status="重点观察",
                    detail="低位震荡待变盘",
                    lane_key="aggressive",
                ),
            ]
        )
        summary = self.ledger.capture_today_action_queue(view)
        self.assertEqual(summary["captured"], 2)
        self.assertEqual(summary["already_present"], 0)
        self.assertEqual(summary["trade_date"], "2026-05-15")
        self.assertEqual(len(summary["decision_ids"]), 2)

        stored = self.ledger.load_decisions("2026-05-15")
        codes = sorted(rec["stock"]["code"] for rec in stored)
        self.assertEqual(codes, ["sh600690", "sz000001"])

    def test_capture_is_idempotent_on_rerun(self) -> None:
        view = _today_view_with_items(
            items=[
                _make_action_item(
                    key="watchlist:600690",
                    title="海尔智家 600690",
                    status="继续持有",
                    detail="x",
                )
            ]
        )
        first = self.ledger.capture_today_action_queue(view)
        second = self.ledger.capture_today_action_queue(view)

        self.assertEqual(first["captured"], 1)
        self.assertEqual(second["captured"], 0)
        self.assertEqual(second["already_present"], 1)
        stored = self.ledger.load_decisions("2026-05-15")
        self.assertEqual(len(stored), 1)

    def test_capture_records_stale_items_as_non_executable(self) -> None:
        view = _today_view_with_items(
            items=[],
            stale_items=[
                _make_action_item(
                    key="watchlist:600690",
                    title="海尔智家 600690",
                    status="继续持有",
                    detail="x",
                    actionable=False,
                    trust_blockers=[{"key": "freshness", "message": "数据不新鲜"}],
                )
            ],
            readiness_mode="blocked",
            readiness_ready=False,
        )
        summary = self.ledger.capture_today_action_queue(view)
        self.assertEqual(summary["captured"], 1)
        stored = self.ledger.load_decisions("2026-05-15")
        self.assertEqual(len(stored), 1)
        snapshot = stored[0]["evidence_snapshot"]
        self.assertFalse(snapshot["readiness_ready"])
        self.assertEqual(snapshot["readiness_mode"], "blocked")
        self.assertEqual(
            [b.get("message") for b in snapshot["blockers"]],
            ["数据不新鲜"],
        )

    def test_capture_empty_action_queue_is_successful_noop(self) -> None:
        view = _today_view_with_items(items=[])
        summary = self.ledger.capture_today_action_queue(view)
        self.assertEqual(summary["captured"], 0)
        self.assertEqual(summary["already_present"], 0)
        self.assertEqual(summary["decision_ids"], [])
        # No file written for an empty no-op.
        self.assertFalse((self.ledger_root / "decisions" / "2026-05-15.json").exists())

    def test_capture_does_not_overwrite_existing_recommendation(self) -> None:
        """If the morning capture writes a record and the midday view
        re-runs with drifted detail text but the same status, the
        original snapshot must win.
        """

        morning = _today_view_with_items(
            items=[
                _make_action_item(
                    key="watchlist:600690",
                    title="海尔智家 600690",
                    status="继续持有",
                    detail="早盘判断：趋势线尚未破",
                )
            ]
        )
        afternoon = _today_view_with_items(
            items=[
                _make_action_item(
                    key="watchlist:600690",
                    title="海尔智家 600690",
                    status="继续持有",
                    detail="午盘补充：尾盘需要确认资金",
                )
            ]
        )
        self.ledger.capture_today_action_queue(morning)
        self.ledger.capture_today_action_queue(afternoon)

        stored = self.ledger.load_decisions("2026-05-15")
        self.assertEqual(len(stored), 1)
        self.assertIn("早盘判断", stored[0]["recommendation"]["main_conclusion"])

    def test_capture_action_change_creates_second_record(self) -> None:
        """Material change (status flips) creates a new decision; the old
        one stays so we can trace the lineage later.
        """

        before = _today_view_with_items(
            items=[
                _make_action_item(
                    key="watchlist:600690",
                    title="海尔智家 600690",
                    status="继续持有",
                    detail="持有",
                )
            ]
        )
        after = _today_view_with_items(
            items=[
                _make_action_item(
                    key="watchlist:600690",
                    title="海尔智家 600690",
                    status="减仓",
                    detail="转弱",
                )
            ]
        )
        self.ledger.capture_today_action_queue(before)
        self.ledger.capture_today_action_queue(after)

        stored = self.ledger.load_decisions("2026-05-15")
        self.assertEqual(len(stored), 2)
        actions = sorted(rec["recommendation"]["action_label"] for rec in stored)
        self.assertEqual(actions, ["减仓", "继续持有"])

    def test_capture_action_change_auto_supersedes_old_record(self) -> None:
        """A material change for the same (date, code, surface, lane,
        action_key) must auto-mark the older open record as superseded
        once the new one lands.  The old record's recommendation must
        stay untouched -- only ``status`` moves.
        """

        before = _today_view_with_items(
            items=[
                _make_action_item(
                    key="watchlist:600690",
                    title="海尔智家 600690",
                    status="继续持有",
                    detail="持有",
                )
            ]
        )
        after = _today_view_with_items(
            items=[
                _make_action_item(
                    key="watchlist:600690",
                    title="海尔智家 600690",
                    status="减仓",
                    detail="转弱",
                )
            ]
        )
        first = self.ledger.capture_today_action_queue(before)
        second = self.ledger.capture_today_action_queue(after)

        self.assertEqual(first["superseded"], 0)
        self.assertEqual(second["captured"], 1)
        self.assertEqual(second["superseded"], 1)

        stored = self.ledger.load_decisions("2026-05-15")
        self.assertEqual(len(stored), 2)
        by_action = {rec["recommendation"]["action_label"]: rec for rec in stored}
        old_record = by_action["继续持有"]
        new_record = by_action["减仓"]
        self.assertEqual(old_record["status"]["state"], "superseded")
        self.assertEqual(old_record["status"]["superseded_by"], new_record["decision_id"])
        # Recommendation untouched on the superseded record.
        self.assertEqual(old_record["recommendation"]["action_raw"], "继续持有")
        # The new record stays open.
        self.assertEqual(new_record["status"]["state"], "open")

    def test_capture_does_not_supersede_when_action_key_differs(self) -> None:
        """A new decision with a different ``action_key`` must NOT touch
        an unrelated open decision, even if it lands on the same day for
        the same stock.  The supersede rule is intentionally tight.
        """

        morning = _today_view_with_items(
            items=[
                _make_action_item(
                    key="watchlist:600690",
                    title="海尔智家 600690",
                    status="继续持有",
                    detail="x",
                )
            ]
        )
        afternoon_other_lane = _today_view_with_items(
            items=[
                _make_action_item(
                    key="screening:600690",
                    title="海尔智家 600690",
                    status="减仓",
                    detail="不同链路新增",
                    lane_key="aggressive",
                )
            ]
        )
        self.ledger.capture_today_action_queue(morning)
        result = self.ledger.capture_today_action_queue(afternoon_other_lane)

        self.assertEqual(result["captured"], 1)
        self.assertEqual(result["superseded"], 0)
        stored = self.ledger.load_decisions("2026-05-15")
        # Both stay open -- different ``source.surface`` *or* lane *or*
        # action_key means they're not the same recommendation slot.
        states = sorted(rec["status"]["state"] for rec in stored)
        self.assertEqual(states, ["open", "open"])

    def test_capture_skips_items_with_invalid_key(self) -> None:
        view = _today_view_with_items(
            items=[
                _make_action_item(
                    key="bogus",
                    title="???",
                    status="continue",
                    detail="x",
                ),
                _make_action_item(
                    key="watchlist:600690",
                    title="海尔智家 600690",
                    status="继续持有",
                    detail="ok",
                ),
            ]
        )
        summary = self.ledger.capture_today_action_queue(view)
        self.assertEqual(summary["captured"], 1)
        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(len(summary["decision_ids"]), 1)


class CaptureApiEndpointTests(unittest.TestCase):
    """Smoke test the POST /api/decision-ledger/capture endpoint.

    The endpoint must work when the caller hands it a today_view body so
    the test does not have to fake the entire control-panel artifact
    state.  No body simply rebuilds via build_today_view -- that path is
    exercised indirectly by the smoke suite but not asserted here.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.ledger_root = Path(cls._tmp.name) / "decision_ledger"
        cls._env = mock.patch.dict(
            os.environ,
            {"PRISM_DECISION_LEDGER_PATH": str(cls.ledger_root)},
        )
        cls._env.start()

        sys.modules.pop("decision_ledger", None)
        sys.modules.pop("app", None)

        from fastapi.testclient import TestClient  # noqa: E402

        import app as legacy_app  # type: ignore

        cls.client = TestClient(legacy_app.app)
        cls.legacy_app = legacy_app

    @classmethod
    def tearDownClass(cls) -> None:
        cls._env.stop()
        cls._tmp.cleanup()

    def setUp(self) -> None:
        # Wipe between tests so idempotency claims are honest.
        if self.ledger_root.exists():
            for path in self.ledger_root.rglob("*.json"):
                path.unlink()

    def test_capture_endpoint_accepts_today_view_body(self) -> None:
        body = _today_view_with_items(
            items=[
                _make_action_item(
                    key="watchlist:600690",
                    title="海尔智家 600690",
                    status="继续持有",
                    detail="持有",
                )
            ]
        )
        response = self.client.post(
            "/api/decision-ledger/capture",
            json={"today_view": body},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["captured"], 1)
        self.assertEqual(payload["trade_date"], "2026-05-15")
        self.assertEqual(len(payload["decision_ids"]), 1)

    def test_capture_endpoint_is_idempotent(self) -> None:
        body = _today_view_with_items(
            items=[
                _make_action_item(
                    key="watchlist:600690",
                    title="海尔智家 600690",
                    status="继续持有",
                    detail="持有",
                )
            ]
        )
        first = self.client.post(
            "/api/decision-ledger/capture", json={"today_view": body}
        )
        second = self.client.post(
            "/api/decision-ledger/capture", json={"today_view": body}
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["captured"], 1)
        self.assertEqual(second.json()["captured"], 0)
        self.assertEqual(second.json()["already_present"], 1)

    def test_capture_endpoint_empty_view_is_no_op(self) -> None:
        body = _today_view_with_items(items=[])
        response = self.client.post(
            "/api/decision-ledger/capture", json={"today_view": body}
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["captured"], 0)
        self.assertEqual(payload["decision_ids"], [])


if __name__ == "__main__":
    unittest.main()
