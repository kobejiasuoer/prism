"""Tests for the A-share trading calendar."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

CONTROL_PANEL_ROOT = Path(__file__).resolve().parents[1]
if str(CONTROL_PANEL_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROL_PANEL_ROOT))

import trading_calendar as tc  # type: ignore  # noqa: E402


class TradingCalendarTests(unittest.TestCase):
    def test_weekend_is_not_trading(self) -> None:
        self.assertFalse(tc.is_trading_day(date(2026, 5, 9)))  # Saturday
        self.assertEqual(tc.calendar_status(date(2026, 5, 9))["status"], "weekend")

    def test_labor_day_2026_is_holiday(self) -> None:
        # 2026 Labor Day holiday block: May 1 (Fri), May 4 (Mon), May 5 (Tue)
        for d in (date(2026, 5, 1), date(2026, 5, 4), date(2026, 5, 5)):
            self.assertFalse(tc.is_trading_day(d), msg=f"{d} should be holiday")
            self.assertEqual(tc.calendar_status(d)["status"], "holiday")

    def test_first_session_after_labor_day_is_trading(self) -> None:
        # Wednesday 2026-05-06 is the first session after Labor Day.
        self.assertTrue(tc.is_trading_day(date(2026, 5, 6)))

    def test_most_recent_trading_day_skips_holiday(self) -> None:
        # Asking on Sunday May 3 should return the previous trading day
        # which is Thursday Apr 30 (since May 1, 2 are holiday/weekend).
        result = tc.most_recent_trading_day(date(2026, 5, 3))
        self.assertEqual(result, date(2026, 4, 30))

    def test_unknown_after_horizon(self) -> None:
        beyond = date(2030, 1, 2)
        status = tc.calendar_status(beyond)
        self.assertEqual(status["status"], "unknown")
        self.assertFalse(tc.is_trading_day(beyond))

    def test_override_horizon_via_env(self) -> None:
        with mock.patch.dict("os.environ", {"PRISM_TEST_CALENDAR_HORIZON": "2026-05-05"}):
            # 2026-05-06 was previously trading; with override horizon 5/5 it
            # falls past the horizon and must be reported as unknown.
            status = tc.calendar_status(date(2026, 5, 6))
            self.assertEqual(status["status"], "unknown")

    def test_override_holidays_via_env(self) -> None:
        # 2026-05-07 (Thursday) is normally a trading day; injecting it as
        # an extra holiday should flip the verdict.
        with mock.patch.dict("os.environ", {"PRISM_TEST_TRADING_HOLIDAYS": "2026-05-07"}):
            self.assertFalse(tc.is_trading_day(date(2026, 5, 7)))

    def test_string_inputs(self) -> None:
        self.assertEqual(tc.calendar_status("2026-05-06")["status"], "trading")
        self.assertEqual(tc.calendar_status("2026-05-09")["status"], "weekend")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
