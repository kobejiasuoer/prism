from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROL_PANEL_ROOT = REPO_ROOT / "apps" / "control-panel"
if str(CONTROL_PANEL_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROL_PANEL_ROOT))

import trading_calendar  # noqa: E402
from trading_calendar import calendar_status, CALENDAR_HORIZON  # noqa: E402


def test_horizon_covers_through_2027():
    """CALENDAR_HORIZON must extend past 2026-12-31 so 2027 does not halt."""
    assert CALENDAR_HORIZON >= date(2027, 12, 31), (
        "CALENDAR_HORIZON must reach end of 2027; system halts past it"
    )


def test_known_2027_holiday_is_recognized():
    """New Year's Day 2027 (a Friday) must classify as holiday, not unknown."""
    # 2027-01-01 is a Friday — must be in STATIC_HOLIDAYS and return holiday
    status = calendar_status("2027-01-01")
    assert status["status"] == "holiday", status


def test_2027_weekday_within_horizon_is_trading():
    """A normal 2027 weekday inside the horizon must be trading, never unknown.

    2027-03-10 is a Wednesday with no known movable 2027 holiday yet, so it
    must resolve to trading (tightened from the earlier trading/holiday
    allowance so a coverage regression does not silently pass).
    """
    status = calendar_status("2027-03-10")
    assert status["status"] == "trading", status


def test_horizon_warning_when_approaching_edge(monkeypatch):
    """Within EXPIRY_WARNING_DAYS of horizon, payload carries horizon_warning."""
    monkeypatch.setenv("PRISM_TEST_CALENDAR_HORIZON", "2026-12-31")
    # Pin the warning window so the test does not depend on the import-time
    # env default (EXPIRY_WARNING_DAYS is read at import, unlike the horizon).
    monkeypatch.setattr(trading_calendar, "EXPIRY_WARNING_DAYS", 30)
    status = calendar_status("2026-12-15")
    assert status.get("horizon_warning") is True, status


def test_no_warning_well_inside_horizon(monkeypatch):
    """A date far from the horizon must not carry horizon_warning."""
    monkeypatch.setenv("PRISM_TEST_CALENDAR_HORIZON", "2027-12-31")
    monkeypatch.setattr(trading_calendar, "EXPIRY_WARNING_DAYS", 30)
    status = calendar_status("2027-01-05")
    assert status.get("horizon_warning") is False, status


def test_past_horizon_workday_carries_warning_not_silent_halt(monkeypatch):
    """Past horizon on a weekday: status unknown BUT with horizon_warning flag,
    not a bare unknown that silently halts the scheduler."""
    monkeypatch.setenv("PRISM_TEST_CALENDAR_HORIZON", "2026-06-01")
    monkeypatch.setattr(trading_calendar, "EXPIRY_WARNING_DAYS", 30)
    # 2026-06-15 is a Monday, past the forced horizon of 2026-06-01
    status = calendar_status("2026-06-15")
    assert status["status"] == "unknown"
    assert status.get("horizon_warning") is True, status
