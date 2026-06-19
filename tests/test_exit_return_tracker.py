from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_ROOT = REPO_ROOT / "packages"
if str(PACKAGES_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGES_ROOT))

from screener import exit_return_tracker as ert  # noqa: E402


def _write_store(tmp_path: Path, records: list[dict]) -> Path:
    store = tmp_path / "exit_tracking.jsonl"
    with store.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return store


def test_record_exit_appends_record(tmp_path: Path):
    store = tmp_path / "exit_tracking.jsonl"
    ert.record_exit(
        store=store,
        code="000032",
        name="深桑达A",
        exit_date="2026-06-18",
        exit_price=10.5,
        reason="题材走弱",
        theme="其他",
    )
    lines = store.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["code"] == "000032"
    assert rec["exit_price"] == 10.5
    assert rec["status"] == "open"
    assert rec["holding_window_days"] == 5


def test_record_exit_null_price_is_allowed(tmp_path: Path):
    store = tmp_path / "exit_tracking.jsonl"
    ert.record_exit(store=store, code="600141", name="兴发集团", exit_date="2026-06-18",
                    exit_price=None, reason="x", theme="y")
    rec = json.loads(store.read_text(encoding="utf-8").strip())
    assert rec["exit_price"] is None
    assert rec["status"] == "open"


def _fake_pricing(closes: dict[str, dict[str, float]]):
    """Return a pricing provider callable: (code) -> {trade_date: close}.

    update_exits asks the provider for the whole window of daily closes for a
    code at once, then settles the record using the closes that fall after
    the exit_date.
    """
    def provider(code: str):
        return closes.get(code, {})
    return provider


def test_update_marks_true_exit_when_drops(tmp_path: Path):
    store = _write_store(tmp_path, [{
        "code": "000032", "name": "深桑达A", "exit_date": "2026-06-18",
        "exit_price": 10.0, "reason": "x", "theme": "y", "status": "open",
        "holding_window_days": 5, "recorded_at": "2026-06-18T09:40:00",
        "daily_prices": [],
    }])
    # 5 trading days after the exit, prices drop
    closes = {"000032": {"2026-06-19": 9.8, "2026-06-22": 9.5, "2026-06-23": 9.2,
                         "2026-06-24": 9.0, "2026-06-25": 8.8}}
    result = ert.update_exits(store=store, pricing_provider=_fake_pricing(closes),
                              as_of_date="2026-06-25", window_days=5, misjudged_threshold=0.05)
    settled = result["settled"]
    assert len(settled) == 1
    assert settled[0]["outcome"] == "true_exit"
    assert settled[0]["net_return"] < 0


def test_update_marks_misjudged_when_rebounds(tmp_path: Path):
    store = _write_store(tmp_path, [{
        "code": "600141", "name": "兴发集团", "exit_date": "2026-06-18",
        "exit_price": 10.0, "reason": "x", "theme": "y", "status": "open",
        "holding_window_days": 5, "recorded_at": "2026-06-18T09:40:00",
        "daily_prices": [],
    }])
    # Prices rebound >5% above exit
    closes = {"600141": {"2026-06-19": 10.5, "2026-06-22": 10.8, "2026-06-23": 10.9,
                         "2026-06-24": 11.0, "2026-06-25": 11.2}}
    result = ert.update_exits(store=store, pricing_provider=_fake_pricing(closes),
                              as_of_date="2026-06-25", window_days=5, misjudged_threshold=0.05)
    settled = result["settled"]
    assert settled[0]["outcome"] == "misjudged"
    assert settled[0]["net_return"] > 0.05


def test_update_marks_inconclusive_on_missing_prices(tmp_path: Path):
    store = _write_store(tmp_path, [{
        "code": "000100", "name": "TCL科技", "exit_date": "2026-06-18",
        "exit_price": 5.0, "reason": "x", "theme": "y", "status": "open",
        "holding_window_days": 5, "recorded_at": "2026-06-18T09:40:00",
        "daily_prices": [],
    }])
    # No prices available at all. as_of_date is > window_days*2 (=10) past the
    # exit (Jun 18 -> Jul 2 = 14 days), so the record settles as inconclusive
    # rather than lingering open forever.
    result = ert.update_exits(store=store, pricing_provider=_fake_pricing({}),
                              as_of_date="2026-07-02", window_days=5, misjudged_threshold=0.05)
    settled = result["settled"]
    assert settled[0]["outcome"] == "inconclusive"


def test_update_keeps_open_when_window_not_full(tmp_path: Path):
    """If fewer than window_days of post-exit closes are available, record stays open."""
    store = _write_store(tmp_path, [{
        "code": "000032", "name": "深桑达A", "exit_date": "2026-06-18",
        "exit_price": 10.0, "reason": "x", "theme": "y", "status": "open",
        "holding_window_days": 5, "recorded_at": "2026-06-18T09:40:00",
        "daily_prices": [],
    }])
    # Only 2 post-exit closes available (as_of too early)
    closes = {"000032": {"2026-06-19": 9.8, "2026-06-22": 9.5}}
    result = ert.update_exits(store=store, pricing_provider=_fake_pricing(closes),
                              as_of_date="2026-06-22", window_days=5, misjudged_threshold=0.05)
    assert result["settled"] == []
    assert result["advanced"] == 2


def test_update_backfills_missing_exit_price(tmp_path: Path):
    """When exit_price is None (shortlist has no close), update_exits backfills
    it from the exit-day close so classification can proceed.

    This is the production path: candidate_lifecycle's shortlist item carries
    no price, so record_exit stores exit_price=None. The tracker must recover
    the exit-day close from the pricing provider.
    """
    store = _write_store(tmp_path, [{
        "code": "000032", "name": "深桑达A", "exit_date": "2026-06-18",
        "exit_price": None, "reason": "x", "theme": "y", "status": "open",
        "holding_window_days": 5, "recorded_at": "2026-06-18T09:40:00",
        "daily_prices": [],
    }])
    # Provider returns the exit-day close (2026-06-18: 10.0) plus post-exit drops
    closes = {"000032": {"2026-06-18": 10.0, "2026-06-19": 9.8, "2026-06-22": 9.5,
                         "2026-06-23": 9.2, "2026-06-24": 9.0, "2026-06-25": 8.8}}
    result = ert.update_exits(store=store, pricing_provider=_fake_pricing(closes),
                              as_of_date="2026-06-25", window_days=5, misjudged_threshold=0.05)
    settled = result["settled"]
    assert len(settled) == 1
    assert settled[0]["exit_price"] == 10.0, "exit_price should be backfilled from exit-day close"
    assert settled[0]["outcome"] == "true_exit"


def test_partial_prices_settle_when_stale(tmp_path: Path):
    """A record that got some closes then the provider went dry must still
    settle once the wall-clock grace expires — classified on whatever closes
    it has, not left lingering open forever.

    With 1 close at 9.8 and exit_price 10.0, net_return = -0.02 (not > 0.05),
    so it settles as true_exit. The point of this test is that it SETTLES at
    all rather than staying open.
    """
    store = _write_store(tmp_path, [{
        "code": "000032", "name": "深桑达A", "exit_date": "2026-06-18",
        "exit_price": 10.0, "reason": "x", "theme": "y", "status": "open",
        "holding_window_days": 5, "recorded_at": "2026-06-18T09:40:00",
        "daily_prices": [{"date": "2026-06-19", "close": 9.8}],
    }])
    # Provider now returns nothing; as_of is 20 days past exit (> window*2=10)
    result = ert.update_exits(store=store, pricing_provider=_fake_pricing({}),
                              as_of_date="2026-07-08", window_days=5, misjudged_threshold=0.05)
    settled = result["settled"]
    assert len(settled) == 1
    assert settled[0]["status"] == "settled"
    # Classified on the 1 close it has: 9.8/10-1 = -0.02 -> true_exit
    assert settled[0]["outcome"] == "true_exit"
