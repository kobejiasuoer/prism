"""Tests for the unified readiness model and the live-ready gate.

These cover the operator-visible scenarios the team cares about most:

* Stale data must be ``blocked`` even when the artifacts agree with each other.
* Quality lanes that report ``ok`` but were checked on an older trade date
  must NOT count as readiness-passing.
* ``brief_is_live`` must require alignment with the *expected* trade date.
* ``unsafe_apply`` must not be flipped by the string ``"false"``.
* The ``/api/readiness/live`` endpoint exposes the same payload to operators.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient


INVEST_FLOW_ROOT = Path(__file__).resolve().parents[2]
if str(INVEST_FLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(INVEST_FLOW_ROOT))

# Importing the legacy modules through the compat shim ensures sys.path is
# wired up correctly for ``readiness`` and ``dashboard_data``.
from control_panel.app import app  # noqa: E402
import control_panel.app as app_module  # noqa: E402
from control_panel.dashboard_data import (  # noqa: E402
    build_today_view,
    compute_readiness,
    expected_trade_date,
)


def _manifest(
    dataset: str,
    trade_date: str,
    generated_at: str,
    *,
    live_small_allowed: bool = True,
    freshness_status: str = "fresh",
    source_lane: str = "pipeline",
    decision_scope: str = "live_small",
    authority_provider: str = "pipeline",
    target_authority_provider: str = "pipeline",
    source_authority_ready: bool = True,
    formal_decision_allowed: bool = True,
    authority_flags: list[str] | None = None,
) -> dict[str, object]:
    return {
        "dataset": dataset,
        "provider": "pipeline",
        "provider_role": "primary",
        "trade_date": trade_date,
        "fetched_at": generated_at,
        "asof": generated_at,
        "ttl_seconds": 900,
        "status": "ok",
        "freshness_status": freshness_status,
        "fallback_used": False,
        "row_count": 1,
        "payload_hash": "test",
        "live_small_allowed": live_small_allowed,
        "quality_flags": [],
        "manifest_path": f"/tmp/{dataset}.manifest.json",
        "source_lane": source_lane,
        "decision_scope": decision_scope,
        "authority_provider": authority_provider,
        "target_authority_provider": target_authority_provider,
        "audit_providers": [],
        "source_authority_ready": source_authority_ready,
        "formal_decision_allowed": formal_decision_allowed,
        "authority_flags": list(authority_flags or []),
    }


def _source(dataset: str, trade_date: str, generated_at: str, **extra):
    payload = {
        "trade_date": trade_date,
        "generated_at": generated_at,
        "manifest": _manifest(dataset, trade_date, generated_at),
    }
    payload.update(extra)
    return payload


def _stale_artifacts(trade_date: str = "2026-04-27", generated_at: str = "2026-04-27 09:25:00"):
    """Return canonical-ish artifacts where everything is 8 days stale."""

    watchlist = _source(
        "watchlist.snapshot",
        trade_date,
        generated_at,
        stocks=[],
        priority_codes=[],
        follow_codes=[],
        observe_codes=[],
        stock_count=0,
    )
    screening_batch = _source(
        "screening.batch",
        trade_date,
        generated_at,
        candidates=[],
        screening_summary={},
        market_regime={},
        candidate_count=0,
        pool_label="全市场",
    )
    confirmation = _source(
        "screening.confirmation",
        trade_date,
        generated_at,
        validation_status="ok",
        confirmed=[],
        downgraded=[],
        fresh_candidates=[],
        counts={},
    )
    decision_brief = _source(
        "decision_brief.snapshot",
        trade_date,
        generated_at,
        summary={"main_theme": "test"},
        focus={},
        paths={},
    )
    quality_status = {
        "lanes": {
            "watchlist": {
                "validation_status": "ok",
                "checked_at": "2026-04-21 11:30:00",
                "expected_timestamp": "2026-04-21",
            },
            "aggressive": {
                "validation_status": "ok",
                "checked_at": "2026-04-21 09:35:00",
                "expected_timestamp": "2026-04-21",
            },
            "midday_confirmation": {
                "validation_status": "ok",
                "checked_at": "2026-04-21 13:30:00",
                "expected_timestamp": "2026-04-21",
            },
        }
    }
    return watchlist, screening_batch, confirmation, decision_brief, quality_status


class ReadinessModelTest(unittest.TestCase):
    def test_stale_artifacts_are_blocked_even_when_self_consistent(self) -> None:
        """All four sources are 8 days old and aligned to the same date.

        The operator must NOT see the system as live_ready: stale data is
        stale, even when nothing contradicts itself.
        """

        watchlist, screening, confirmation, brief, quality = _stale_artifacts()
        now = datetime(2026, 5, 6, 14, 30, 0)
        readiness = compute_readiness(
            watchlist=watchlist,
            screening_batch=screening,
            confirmation=confirmation,
            decision_brief=brief,
            quality_status=quality,
            now=now,
            expected_date="2026-05-06",
        )

        self.assertEqual(readiness["expected_trade_date"], "2026-05-06")
        self.assertEqual(readiness["data_trade_date"], "2026-04-27")
        self.assertEqual(readiness["readiness_mode"], "blocked")
        self.assertFalse(readiness["ready"])
        self.assertFalse(readiness["brief_is_live"])
        self.assertEqual(readiness["stale_count"], 4)
        blocker_codes = {item["code"] for item in readiness["blockers"]}
        self.assertIn("watchlist_stale", blocker_codes)
        self.assertIn("screening_stale", blocker_codes)
        self.assertIn("decision_brief_stale", blocker_codes)
        self.assertIn("trade_date_mismatch", blocker_codes)

    def test_quality_lane_ok_but_wrong_date_is_not_timely(self) -> None:
        """quality.status==ok with an older checked_at must NOT count as ready."""

        _wl, _sb, _cf, _br, quality = _stale_artifacts()
        now = datetime(2026, 5, 6, 14, 30, 0)

        # Even with all *sources* at expected date, stale quality blocks readiness.
        watchlist = _source("watchlist.snapshot", "2026-05-06", "2026-05-06 09:25:00", stocks=[], priority_codes=[])
        readiness = compute_readiness(
            watchlist=watchlist,
            screening_batch=_source("screening.batch", "2026-05-06", "2026-05-06 09:30:00"),
            confirmation=_source("screening.confirmation", "2026-05-06", "2026-05-06 11:35:00"),
            decision_brief=_source("decision_brief.snapshot", "2026-05-06", "2026-05-06 12:00:00"),
            quality_status=quality,  # checked_at is 2026-04-21
            now=now,
            expected_date="2026-05-06",
        )
        timely_keys = {q["key"] for q in readiness["quality_freshness"] if q["timely"]}
        self.assertEqual(timely_keys, set())  # none of the lanes are timely
        self.assertEqual(readiness["readiness_mode"], "blocked")
        codes = {item["code"] for item in readiness["blockers"]}
        self.assertTrue({"quality_watchlist_stale", "quality_aggressive_stale"}.issubset(codes))

    def test_brief_aligned_to_old_trade_date_is_not_live(self) -> None:
        """brief.trade_date == screening.trade_date is not enough.

        If the data trade_date doesn't match the expected_trade_date, the
        brief must NOT be considered live.
        """

        watchlist = _source("watchlist.snapshot", "2026-04-27", "2026-04-27 09:25:00")
        brief = _source("decision_brief.snapshot", "2026-04-27", "2026-04-27 21:00:00")
        readiness = compute_readiness(
            watchlist=watchlist,
            screening_batch=_source("screening.batch", "2026-04-27", "2026-04-27 09:30:00"),
            confirmation=_source("screening.confirmation", "2026-04-27", "2026-04-27 11:35:00"),
            decision_brief=brief,
            quality_status={},
            now=datetime(2026, 5, 6, 14, 30, 0),
            expected_date="2026-05-06",
        )
        self.assertFalse(readiness["brief_is_live"])

    def test_missing_manifest_fails_closed(self) -> None:
        readiness = compute_readiness(
            watchlist={"trade_date": "2026-05-06", "generated_at": "2026-05-06 09:25:00"},
            screening_batch=_source("screening.batch", "2026-05-06", "2026-05-06 09:30:00"),
            confirmation=_source("screening.confirmation", "2026-05-06", "2026-05-06 11:35:00"),
            decision_brief=_source("decision_brief.snapshot", "2026-05-06", "2026-05-06 12:00:00"),
            quality_status={},
            now=datetime(2026, 5, 6, 14, 30, 0),
            expected_date="2026-05-06",
        )
        watchlist_source = next(item for item in readiness["source_freshness"] if item["key"] == "watchlist")
        self.assertTrue(watchlist_source["stale"])
        self.assertIn("manifest_missing", watchlist_source["stale_reasons"])
        self.assertFalse(readiness["ready"])

    def test_formal_authority_gap_is_visible_without_blocking_live_ready(self) -> None:
        source_manifest = _manifest(
            "watchlist.snapshot",
            "2026-05-06",
            "2026-05-06 09:25:00",
            source_lane="pipeline",
            decision_scope="live_small",
            authority_provider="pipeline",
            target_authority_provider="pipeline",
            source_authority_ready=False,
            formal_decision_allowed=False,
            authority_flags=["upstream_authority_not_ready", "target_authority_not_in_use:tushare"],
        )
        watchlist = {
            "trade_date": "2026-05-06",
            "generated_at": "2026-05-06 09:25:00",
            "manifest": source_manifest,
            "stocks": [],
            "priority_codes": [],
        }
        quality = {
            "lanes": {
                "watchlist": {"validation_status": "ok", "checked_at": "2026-05-06 09:25:00"},
                "aggressive": {"validation_status": "ok", "checked_at": "2026-05-06 09:35:00"},
                "midday_confirmation": {"validation_status": "ok", "checked_at": "2026-05-06 13:30:00"},
            }
        }
        readiness = compute_readiness(
            watchlist=watchlist,
            screening_batch=_source("screening.batch", "2026-05-06", "2026-05-06 09:35:00"),
            confirmation=_source("screening.confirmation", "2026-05-06", "2026-05-06 13:30:00"),
            decision_brief=_source("decision_brief.snapshot", "2026-05-06", "2026-05-06 13:40:00"),
            quality_status=quality,
            now=datetime(2026, 5, 6, 14, 30, 0),
            expected_date="2026-05-06",
        )
        watchlist_source = next(item for item in readiness["source_freshness"] if item["key"] == "watchlist")
        self.assertFalse(watchlist_source["stale"])
        self.assertEqual(watchlist_source["decision_scope"], "live_small")
        self.assertFalse(watchlist_source["formal_decision_allowed"])
        self.assertEqual(readiness["readiness_mode"], "live_ready")
        self.assertTrue(readiness["ready"])
        self.assertFalse(readiness["formal_ready"])
        formal_codes = {item["code"] for item in readiness["formal_blockers"]}
        self.assertIn("watchlist_formal_not_allowed", formal_codes)

    def test_same_day_pipeline_manifest_expiry_is_degraded_not_stale(self) -> None:
        manifest = _manifest(
            "watchlist.snapshot",
            "2026-05-06",
            "2026-05-06 14:20:00",
            live_small_allowed=False,
            freshness_status="expired",
            source_authority_ready=False,
            formal_decision_allowed=False,
            authority_flags=["upstream_not_fresh"],
        )
        watchlist = {
            "trade_date": "2026-05-06",
            "generated_at": "2026-05-06 14:20:00",
            "manifest": manifest,
            "stocks": [],
            "priority_codes": [],
        }
        quality = {
            "lanes": {
                "watchlist": {"validation_status": "ok", "checked_at": "2026-05-06 14:20:00"},
                "aggressive": {"validation_status": "ok", "checked_at": "2026-05-06 09:35:00"},
                "midday_confirmation": {"validation_status": "ok", "checked_at": "2026-05-06 13:30:00"},
            }
        }
        readiness = compute_readiness(
            watchlist=watchlist,
            screening_batch=_source("screening.batch", "2026-05-06", "2026-05-06 09:35:00"),
            confirmation=_source("screening.confirmation", "2026-05-06", "2026-05-06 13:30:00"),
            decision_brief=_source("decision_brief.snapshot", "2026-05-06", "2026-05-06 13:40:00"),
            quality_status=quality,
            now=datetime(2026, 5, 6, 14, 30, 0),
            expected_date="2026-05-06",
        )
        watchlist_source = next(item for item in readiness["source_freshness"] if item["key"] == "watchlist")
        self.assertFalse(watchlist_source["stale"])
        self.assertTrue(watchlist_source["degraded"])
        self.assertIn("upstream_freshness_expired", watchlist_source["degradation_reasons"])
        self.assertNotIn("watchlist_stale", {item["code"] for item in readiness["blockers"]})
        self.assertIn("watchlist_degraded", {item["code"] for item in readiness["warnings"]})
        self.assertEqual(readiness["readiness_mode"], "live_ready")

    def test_provider_manifest_expiry_remains_stale(self) -> None:
        manifest = _manifest(
            "quotes.snapshot",
            "2026-05-06",
            "2026-05-06 14:20:00",
            freshness_status="expired",
            live_small_allowed=False,
        )
        watchlist = {
            "trade_date": "2026-05-06",
            "generated_at": "2026-05-06 14:20:00",
            "manifest": manifest,
            "stocks": [],
            "priority_codes": [],
        }
        readiness = compute_readiness(
            watchlist=watchlist,
            screening_batch=_source("screening.batch", "2026-05-06", "2026-05-06 09:35:00"),
            confirmation=_source("screening.confirmation", "2026-05-06", "2026-05-06 13:30:00"),
            decision_brief=_source("decision_brief.snapshot", "2026-05-06", "2026-05-06 13:40:00"),
            quality_status={
                "lanes": {
                    "watchlist": {"validation_status": "ok", "checked_at": "2026-05-06 14:20:00"},
                    "aggressive": {"validation_status": "ok", "checked_at": "2026-05-06 09:35:00"},
                    "midday_confirmation": {"validation_status": "ok", "checked_at": "2026-05-06 13:30:00"},
                }
            },
            now=datetime(2026, 5, 6, 14, 30, 0),
            expected_date="2026-05-06",
        )
        watchlist_source = next(item for item in readiness["source_freshness"] if item["key"] == "watchlist")
        self.assertTrue(watchlist_source["stale"])
        self.assertIn("freshness_expired", watchlist_source["stale_reasons"])

    def test_session_aware_confirmation_warning_in_morning(self) -> None:
        """Morning sessions: missing midday confirmation is a warning, not a block."""

        watchlist = _source("watchlist.snapshot", "2026-05-06", "2026-05-06 09:25:00")
        screening = _source("screening.batch", "2026-05-06", "2026-05-06 09:35:00")
        brief = _source("decision_brief.snapshot", "2026-05-06", "2026-05-06 09:45:00")
        quality = {
            "lanes": {
                "watchlist": {"validation_status": "ok", "checked_at": "2026-05-06 09:25:00"},
                "aggressive": {"validation_status": "ok", "checked_at": "2026-05-06 09:35:00"},
                "midday_confirmation": {"validation_status": "ok", "checked_at": "2026-05-06 09:30:00"},
            }
        }
        readiness = compute_readiness(
            watchlist=watchlist,
            screening_batch=screening,
            confirmation=None,  # not yet generated
            decision_brief=brief,
            quality_status=quality,
            now=datetime(2026, 5, 6, 10, 30, 0),  # morning
            expected_date="2026-05-06",
        )
        warning_codes = {item["code"] for item in readiness["warnings"]}
        self.assertIn("confirmation_missing", warning_codes)
        # Missing confirmation in the morning must be a warning, not a blocker.
        blocker_codes = {item["code"] for item in readiness["blockers"]}
        self.assertNotIn("confirmation_missing", blocker_codes)

    def test_session_aware_confirmation_blocker_in_afternoon(self) -> None:
        watchlist = _source("watchlist.snapshot", "2026-05-06", "2026-05-06 09:25:00")
        screening = _source("screening.batch", "2026-05-06", "2026-05-06 09:35:00")
        brief = _source("decision_brief.snapshot", "2026-05-06", "2026-05-06 09:45:00")
        readiness = compute_readiness(
            watchlist=watchlist,
            screening_batch=screening,
            confirmation=None,
            decision_brief=brief,
            quality_status={},
            now=datetime(2026, 5, 6, 14, 30, 0),  # afternoon
            expected_date="2026-05-06",
        )
        blocker_codes = {item["code"] for item in readiness["blockers"]}
        self.assertIn("confirmation_missing", blocker_codes)

    def test_weekend_is_at_most_shadow_only(self) -> None:
        """Weekends/holidays must never produce live_ready."""

        watchlist = _source("watchlist.snapshot", "2026-05-08", "2026-05-08 09:25:00")
        # All freshness OK relative to a Friday expected_trade_date
        readiness = compute_readiness(
            watchlist=watchlist,
            screening_batch=_source("screening.batch", "2026-05-08", "2026-05-08 09:30:00"),
            confirmation=_source("screening.confirmation", "2026-05-08", "2026-05-08 11:35:00"),
            decision_brief=_source("decision_brief.snapshot", "2026-05-08", "2026-05-08 12:00:00"),
            quality_status={
                "lanes": {
                    "watchlist": {"validation_status": "ok", "checked_at": "2026-05-08 09:25:00"},
                    "aggressive": {"validation_status": "ok", "checked_at": "2026-05-08 09:35:00"},
                    "midday_confirmation": {"validation_status": "ok", "checked_at": "2026-05-08 11:35:00"},
                }
            },
            now=datetime(2026, 5, 9, 14, 30, 0),  # Saturday
            expected_date="2026-05-08",
        )
        self.assertEqual(readiness["readiness_mode"], "shadow_only")
        self.assertFalse(readiness["ready"])

    def test_expected_trade_date_env_override(self) -> None:
        with mock.patch.dict("os.environ", {"PRISM_EXPECTED_TRADE_DATE": "2026-05-06"}):
            self.assertEqual(expected_trade_date(datetime(2026, 5, 9, 10, 0, 0)), "2026-05-06")

    def test_live_ready_when_everything_aligned_on_weekday(self) -> None:
        watchlist = _source("watchlist.snapshot", "2026-05-06", "2026-05-06 09:25:00")
        screening = _source("screening.batch", "2026-05-06", "2026-05-06 09:35:00")
        confirmation = _source("screening.confirmation", "2026-05-06", "2026-05-06 11:35:00")
        brief = _source("decision_brief.snapshot", "2026-05-06", "2026-05-06 12:00:00")
        quality = {
            "lanes": {
                "watchlist": {"validation_status": "ok", "checked_at": "2026-05-06 09:25:00"},
                "aggressive": {"validation_status": "ok", "checked_at": "2026-05-06 09:35:00"},
                "midday_confirmation": {"validation_status": "ok", "checked_at": "2026-05-06 11:35:00"},
            }
        }
        readiness = compute_readiness(
            watchlist=watchlist,
            screening_batch=screening,
            confirmation=confirmation,
            decision_brief=brief,
            quality_status=quality,
            now=datetime(2026, 5, 6, 14, 30, 0),
            expected_date="2026-05-06",
        )
        self.assertEqual(readiness["readiness_mode"], "live_ready")
        self.assertTrue(readiness["ready"])
        self.assertTrue(readiness["brief_is_live"])
        self.assertEqual(readiness["stale_count"], 0)
        self.assertEqual(readiness["blockers"], [])


class TodayViewReadinessTest(unittest.TestCase):
    """End-to-end smoke through the actual API."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_api_today_embeds_readiness(self) -> None:
        response = self.client.get("/api/today")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertIn("readiness", payload)
        readiness = payload["readiness"]
        self.assertIn("expected_trade_date", readiness)
        self.assertIn("readiness_mode", readiness)
        self.assertIn("source_freshness", readiness)
        self.assertIn("quality_freshness", readiness)
        self.assertIn("recommended_tasks", readiness)
        # source_cards must carry freshness metadata, not just label/value
        for card in payload["source_cards"]:
            self.assertIn("stale", card)
            self.assertIn("age_label", card)

    def test_api_readiness_live_endpoint(self) -> None:
        response = self.client.get("/api/readiness/live")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        for key in (
            "readiness_mode",
            "ready",
            "blockers",
            "warnings",
            "source_freshness",
            "quality_freshness",
            "recommended_tasks",
        ):
            self.assertIn(key, payload)

    def test_api_today_with_old_data_is_blocked(self) -> None:
        """The current repository fixtures use 2026-04-27 data while today is
        2026-05-06.  The readiness payload MUST report blocked, never live."""

        response = self.client.get("/api/today")
        payload = response.json()
        readiness = payload["readiness"]
        if readiness["data_trade_date"] != readiness["expected_trade_date"]:
            self.assertFalse(readiness["ready"])
            self.assertNotEqual(readiness["readiness_mode"], "live_ready")
            self.assertFalse(payload["brief_is_live"])
            self.assertGreater(len(readiness["blockers"]), 0)


class UnsafeApplyParsingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_string_false_does_not_bypass_evaluation_block(self) -> None:
        """A string ``"false"`` for unsafe_apply must NOT be treated as truthy.

        Previously the backend used ``bool(...)`` which made any non-empty
        string truthy, allowing rogue clients to skip evaluation hard errors.
        """

        # Build a payload that triggers an evaluation hard error.  We patch
        # parameter_evaluation to deterministically produce a hard error so we
        # do not depend on real config rules.
        seed = {"stocks": [{"code": "600690", "name": "海尔智家", "active": True}],
                "ma_periods": [5, 10, 20], "news_count": 5, "kline_days": 120}
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir) / "stocks.json"
            temp_path.write_text(json.dumps(seed, ensure_ascii=False), encoding="utf-8")

            previous = app_module.PARAMETERS_PATH
            app_module.PARAMETERS_PATH = temp_path
            original_eval = app_module.parameter_evaluation
            try:
                app_module.parameter_evaluation = lambda candidate, current=None: {
                    "ok": False,
                    "errors": ["forced hard error for test"],
                    "warnings": [],
                }

                # 1) string "false" must NOT be treated as truthy
                response = self.client.post(
                    "/api/parameters",
                    json={"raw": json.dumps(seed), "unsafe_apply": "false"},
                )
                self.assertEqual(response.status_code, 400)
                # File must remain untouched (still equal to original seed)
                self.assertEqual(
                    json.loads(temp_path.read_text(encoding="utf-8"))["news_count"], 5
                )

                # 2) literal JSON true is what actually overrides
                response_true = self.client.post(
                    "/api/parameters",
                    json={"raw": json.dumps({**seed, "news_count": 9}), "unsafe_apply": True},
                )
                self.assertEqual(response_true.status_code, 200)
                self.assertTrue(response_true.json().get("saved"))
                self.assertEqual(
                    json.loads(temp_path.read_text(encoding="utf-8"))["news_count"], 9
                )
            finally:
                app_module.parameter_evaluation = original_eval
                app_module.PARAMETERS_PATH = previous


def _all_aligned_artifacts(trade_date: str = "2026-05-06", generated_at: str = "2026-05-06 09:25:00"):
    """Return artifacts where everything is on the expected trade date."""

    watchlist = _source("watchlist.snapshot", trade_date, generated_at)
    screening = _source("screening.batch", trade_date, "2026-05-06 09:35:00")
    confirmation = _source("screening.confirmation", trade_date, "2026-05-06 11:35:00")
    brief = _source("decision_brief.snapshot", trade_date, "2026-05-06 12:00:00")
    quality = {
        "lanes": {
            "watchlist": {
                "validation_status": "ok",
                "checked_at": "2026-05-06 09:25:00",
                "expected_timestamp": trade_date,
            },
            "aggressive": {
                "validation_status": "ok",
                "checked_at": "2026-05-06 09:35:00",
                "expected_timestamp": trade_date,
            },
            "midday_confirmation": {
                "validation_status": "ok",
                "checked_at": "2026-05-06 11:35:00",
                "expected_timestamp": trade_date,
            },
        }
    }
    return watchlist, screening, confirmation, brief, quality


class QualityExpectedTimestampTest(unittest.TestCase):
    """Regression: expected_timestamp must factor into the timely judgement.

    Previously _build_quality only compared ``checked_at`` to the global
    expected date, ignoring the lane's own ``expected_timestamp``.  When a
    lane was checked today but its expected_timestamp was a stale baseline,
    we erroneously treated it as ``timely``.
    """

    def test_checked_today_but_expected_yesterday_is_not_timely(self) -> None:
        watchlist, screening, _confirmation, brief, _quality = _all_aligned_artifacts()
        confirmation = _source("screening.confirmation", "2026-05-06", "2026-05-06 11:35:00")
        # Quality lane was *checked* today but the producer believed yesterday
        # was the trading day — the lane is comparing against the wrong baseline.
        quality_with_stale_expected = {
            "lanes": {
                "watchlist": {
                    "validation_status": "ok",
                    "checked_at": "2026-05-06 09:25:00",
                    "expected_timestamp": "2026-05-05",  # ← stale baseline
                },
                "aggressive": {
                    "validation_status": "ok",
                    "checked_at": "2026-05-06 09:35:00",
                    "expected_timestamp": "2026-05-06",
                },
                "midday_confirmation": {
                    "validation_status": "ok",
                    "checked_at": "2026-05-06 11:35:00",
                    "expected_timestamp": "2026-05-06",
                },
            }
        }
        readiness = compute_readiness(
            watchlist=watchlist,
            screening_batch=screening,
            confirmation=confirmation,
            decision_brief=brief,
            quality_status=quality_with_stale_expected,
            now=datetime(2026, 5, 6, 14, 30, 0),
            expected_date="2026-05-06",
        )

        watchlist_quality = next(q for q in readiness["quality_freshness"] if q["key"] == "watchlist")
        self.assertFalse(watchlist_quality["timely"])
        self.assertIn("expected_trade_date_mismatch", watchlist_quality["stale_reasons"])
        # Mismatched lane must produce a blocker (afternoon session).
        codes = {item["code"] for item in readiness["blockers"]}
        self.assertIn("quality_watchlist_stale", codes)
        self.assertNotEqual(readiness["readiness_mode"], "live_ready")
        self.assertFalse(readiness["ready"])

    def test_aligned_expected_timestamp_keeps_lane_timely(self) -> None:
        """Sanity: when expected_timestamp == expected_date, no extra reason fires."""

        watchlist, screening, confirmation, brief, quality = _all_aligned_artifacts()
        readiness = compute_readiness(
            watchlist=watchlist,
            screening_batch=screening,
            confirmation=confirmation,
            decision_brief=brief,
            quality_status=quality,
            now=datetime(2026, 5, 6, 14, 30, 0),
            expected_date="2026-05-06",
        )
        for q in readiness["quality_freshness"]:
            self.assertTrue(q["timely"], msg=f"{q['key']} should be timely: {q}")
            self.assertNotIn("expected_trade_date_mismatch", q["stale_reasons"])


class ConfirmationRecommendedTaskTest(unittest.TestCase):
    """Regression: confirmation / midday quality blockers must point operators
    at ``midday_confirmation`` (which produces midday_verification_result.json),
    not at ``midday_refresh`` (which writes a different artifact and would
    not clear the blocker).
    """

    def test_confirmation_blocker_recommends_midday_confirmation(self) -> None:
        watchlist = _source("watchlist.snapshot", "2026-05-06", "2026-05-06 09:25:00")
        screening = _source("screening.batch", "2026-05-06", "2026-05-06 09:35:00")
        brief = _source("decision_brief.snapshot", "2026-05-06", "2026-05-06 09:45:00")
        readiness = compute_readiness(
            watchlist=watchlist,
            screening_batch=screening,
            confirmation=None,  # missing — afternoon → blocker
            decision_brief=brief,
            quality_status={
                "lanes": {
                    "watchlist": {"validation_status": "ok", "checked_at": "2026-05-06 09:25:00"},
                    "aggressive": {"validation_status": "ok", "checked_at": "2026-05-06 09:35:00"},
                    "midday_confirmation": {
                        "validation_status": "ok",
                        "checked_at": "2026-04-21 11:35:00",  # stale → also blocker
                    },
                }
            },
            now=datetime(2026, 5, 6, 14, 30, 0),
            expected_date="2026-05-06",
        )
        confirmation_blocker = next(
            (b for b in readiness["blockers"] if b["code"] == "confirmation_missing"), None,
        )
        self.assertIsNotNone(confirmation_blocker)
        self.assertEqual(confirmation_blocker["recommended_task"], "midday_confirmation")

        midday_quality = next(
            (b for b in readiness["blockers"] if b["code"] == "quality_midday_stale"), None,
        )
        self.assertIsNotNone(midday_quality)
        self.assertEqual(midday_quality["recommended_task"], "midday_confirmation")

        self.assertIn("midday_confirmation", readiness["recommended_tasks"])
        # midday_refresh must NOT be the suggested fix for these blockers
        self.assertNotIn("midday_refresh", readiness["recommended_tasks"])

    def test_morning_warning_still_uses_midday_confirmation(self) -> None:
        watchlist = _source("watchlist.snapshot", "2026-05-06", "2026-05-06 09:25:00")
        screening = _source("screening.batch", "2026-05-06", "2026-05-06 09:35:00")
        brief = _source("decision_brief.snapshot", "2026-05-06", "2026-05-06 09:45:00")
        readiness = compute_readiness(
            watchlist=watchlist,
            screening_batch=screening,
            confirmation=None,
            decision_brief=brief,
            quality_status={
                "lanes": {
                    "watchlist": {"validation_status": "ok", "checked_at": "2026-05-06 09:25:00"},
                    "aggressive": {"validation_status": "ok", "checked_at": "2026-05-06 09:35:00"},
                    "midday_confirmation": {"validation_status": "ok", "checked_at": "2026-05-06 09:30:00"},
                }
            },
            now=datetime(2026, 5, 6, 10, 30, 0),  # morning
            expected_date="2026-05-06",
        )
        confirmation_warning = next(
            (w for w in readiness["warnings"] if w["code"] == "confirmation_missing"), None,
        )
        self.assertIsNotNone(confirmation_warning)
        self.assertEqual(confirmation_warning["recommended_task"], "midday_confirmation")


class TodayRefreshConsistencyTest(unittest.TestCase):
    """Regression: /api/today, /api/readiness/live and /api/refresh/status?page=today
    must agree on readiness_mode, stale_count, recommended task and per-source
    stale flags.  The previous implementation ran ``build_page_freshness`` in
    parallel with readiness for the today page, producing two truths.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_three_endpoints_agree_on_readiness_mode_and_stale_count(self) -> None:
        today_payload = self.client.get("/api/today").json()
        live_payload = self.client.get("/api/readiness/live").json()
        refresh_payload = self.client.get("/api/refresh/status?page=today").json()

        today_ready = today_payload["readiness"]
        self.assertEqual(today_ready["readiness_mode"], live_payload["readiness_mode"])
        self.assertEqual(today_ready["readiness_mode"], refresh_payload.get("readiness_mode"))
        self.assertEqual(today_ready["stale_count"], live_payload["stale_count"])
        self.assertEqual(today_ready["stale_count"], refresh_payload["stale_count"])

        # The recommended task surfaced by /api/refresh/status?page=today must
        # match the first task in readiness.recommended_tasks (or be present
        # in the chain) so the operator's first action clears a real blocker.
        if today_ready["recommended_tasks"]:
            self.assertEqual(
                refresh_payload["recommended_task"]["task_name"],
                today_ready["recommended_tasks"][0],
            )
            self.assertEqual(
                refresh_payload.get("recommended_tasks") or [],
                list(today_ready["recommended_tasks"]),
            )

    def test_refresh_freshness_rows_match_readiness_source_freshness(self) -> None:
        """Per-source stale flag must come from readiness, not be re-derived."""

        today_payload = self.client.get("/api/today").json()
        refresh_payload = self.client.get("/api/refresh/status?page=today").json()

        readiness_sources = {
            item["key"]: bool(item.get("stale"))
            for item in today_payload["readiness"]["source_freshness"]
        }
        for row in refresh_payload["freshness"]:
            key = row.get("key")
            if key in readiness_sources:
                self.assertEqual(
                    bool(row.get("stale")),
                    readiness_sources[key],
                    msg=f"freshness row {key} disagrees with readiness",
                )

    def test_refresh_status_includes_operator_recovery_steps(self) -> None:
        refresh_payload = self.client.get("/api/refresh/status?page=today").json()
        today_ready = self.client.get("/api/today").json()["readiness"]
        steps = refresh_payload.get("recovery_steps") or []

        self.assertIsInstance(steps, list)
        if today_ready["readiness_mode"] != "live_ready":
            self.assertGreater(len(steps), 0)
            step_task_names = [step.get("task_name") for step in steps]
            self.assertIn(refresh_payload["recommended_task"]["task_name"], step_task_names)
            for step in steps:
                self.assertIn("title", step)
                self.assertIn("can_trigger", step)
                self.assertIn("issues", step)

    def test_same_day_data_is_not_stale_in_refresh_status(self) -> None:
        """When all artifacts align with today, refresh/status must reflect
        a clean state — no spurious stale rows from the legacy heuristic."""

        watchlist, screening, confirmation, brief, quality = _all_aligned_artifacts()
        readiness = compute_readiness(
            watchlist=watchlist,
            screening_batch=screening,
            confirmation=confirmation,
            decision_brief=brief,
            quality_status=quality,
            now=datetime(2026, 5, 6, 14, 30, 0),
            expected_date="2026-05-06",
        )

        # Use the helper directly so the test does not depend on the live
        # filesystem snapshot.  This is the same conversion used by
        # build_refresh_status_payload for the today page.
        from control_panel.app import _readiness_freshness_rows

        rows = _readiness_freshness_rows(readiness, fallback_threshold=14400)
        self.assertEqual(len(rows), 4)
        self.assertEqual(sum(1 for row in rows if row["stale"]), 0)
        self.assertTrue(all(row["available"] for row in rows))
        # readiness recommended_tasks should be live_ready → just command_brief
        self.assertEqual(readiness["readiness_mode"], "live_ready")
        self.assertEqual(readiness["recommended_tasks"], ["command_brief"])


if __name__ == "__main__":
    unittest.main()
