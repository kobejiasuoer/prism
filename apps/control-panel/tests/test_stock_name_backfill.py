"""Unit tests for the async stock-name backfill helpers.

We do NOT exercise the real Sina endpoint in these tests — instead we
monkeypatch ``fetch_stock_name`` to control outcomes and verify only the
plumbing: dedup, retry TTL, worker lifecycle, account_book/watchlist
write-back.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    state_path = tmp_path / "data" / "control_panel_state" / "account_book.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)

    watchlist_dir = tmp_path / "watchlist"
    watchlist_dir.mkdir()
    watchlist_path = watchlist_dir / "stocks.json"
    watchlist_path.write_text(json.dumps({"stocks": []}), encoding="utf-8")

    monkeypatch.setenv("PRISM_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("PRISM_DB_PATH", str(tmp_path / "prism.db"))
    monkeypatch.setenv("PRISM_ACCOUNT_BOOK_PATH", str(state_path))
    monkeypatch.delenv("PRISM_DISABLE_STOCK_NAME_BACKFILL", raising=False)

    # Force-reload so DEFAULT_DB_PATH and the legacy account-book path pick
    # up the env we just set.
    for mod in (
        "prism_storage.paths",
        "prism_storage.sqlite_store",
        "prism_storage.repositories",
        "prism_storage",
        "account_book",
        "stock_name_backfill",
    ):
        sys.modules.pop(mod, None)

    import watchlist_registry as wr
    monkeypatch.setattr(wr, "WATCHLIST_CONFIG_PATH", watchlist_path)

    import stock_name_backfill as snb
    snb.reset_state_for_tests()
    yield
    snb.reset_state_for_tests()


def test_needs_backfill_detects_code_like_names():
    import stock_name_backfill as snb

    assert snb.needs_backfill("600519", None) is True
    assert snb.needs_backfill("600519", "600519") is True
    assert snb.needs_backfill("600519", "sh600519") is True
    assert snb.needs_backfill("600519", "贵州茅台") is False
    assert snb.needs_backfill("notacode", "anything") is False


def test_request_name_backfill_dedups_inflight(monkeypatch):
    import stock_name_backfill as snb

    # Replace fetch with a slow blocking shim so the first request stays
    # inflight while we attempt the second one.
    release = []

    def slow_fetch(code, *args, **kwargs):
        while not release:
            time.sleep(0.01)
        return "测试名"

    monkeypatch.setattr(snb, "fetch_stock_name", slow_fetch)

    assert snb.request_name_backfill("600519") is True
    assert snb.request_name_backfill("600519") is False  # inflight dedup
    release.append(True)


def test_request_name_backfill_respects_disable_env(monkeypatch):
    import stock_name_backfill as snb

    monkeypatch.setenv("PRISM_DISABLE_STOCK_NAME_BACKFILL", "1")
    assert snb.request_name_backfill("600519") is False
    assert snb.worker_is_running() is False


def test_worker_writes_back_to_account_book(monkeypatch):
    import account_book
    import stock_name_backfill as snb

    # Seed a fill with a code-like name (matches the post-Fix-5 reality
    # where the resolver fell through to the bare code).
    account_book.record_fill(
        code="600519",
        side="buy",
        qty=100,
        price=1800.0,
        trade_date="2026-05-22",
    )
    snapshot = account_book.load_account_book()
    assert snapshot["fills"][0]["name"] == "600519"

    monkeypatch.setattr(snb, "fetch_stock_name", lambda code, *a, **k: "贵州茅台")

    snb.request_name_backfill("600519")
    # The worker thread auto-starts on first enqueue.
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if snb.queue_size() == 0:
            time.sleep(0.05)
            after = account_book.load_account_book()
            if after["fills"][0]["name"] == "贵州茅台":
                break
        time.sleep(0.05)

    after = account_book.load_account_book()
    assert after["fills"][0]["name"] == "贵州茅台"
    # positions are computed on-demand from fills, so verify via the view.
    view = account_book.compute_account_view()
    pos_names = {p["code"]: p["name"] for p in view["open_positions"]}
    assert pos_names.get("600519") == "贵州茅台"


def test_worker_writes_back_to_watchlist(monkeypatch):
    import json as _json
    import watchlist_registry as wr
    import stock_name_backfill as snb

    # Seed watchlist with a code-only entry.
    wr.WATCHLIST_CONFIG_PATH.write_text(
        _json.dumps(
            {
                "stocks": [
                    {"code": "600519", "name": "600519", "active": True, "market": "sh"}
                ]
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(snb, "fetch_stock_name", lambda code, *a, **k: "贵州茅台")

    snb.request_name_backfill("600519")
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if snb.queue_size() == 0:
            time.sleep(0.05)
            config = wr.load_watchlist_config()
            entry = next((s for s in config.get("stocks") or [] if s.get("code") == "600519"), None)
            if entry and entry.get("name") == "贵州茅台":
                break
        time.sleep(0.05)

    config = wr.load_watchlist_config()
    entry = next((s for s in config.get("stocks") or [] if s.get("code") == "600519"), None)
    assert entry is not None
    assert entry["name"] == "贵州茅台"


def test_worker_skips_when_fetch_returns_code_like(monkeypatch):
    import account_book
    import stock_name_backfill as snb

    account_book.record_fill(
        code="600519", side="buy", qty=100, price=1800.0, trade_date="2026-05-22",
    )

    # Fetch echoes the code back — should NOT overwrite.
    monkeypatch.setattr(snb, "fetch_stock_name", lambda code, *a, **k: code)

    snb.request_name_backfill("600519")
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if snb.queue_size() == 0:
            break
        time.sleep(0.05)

    after = account_book.load_account_book()
    assert after["fills"][0]["name"] == "600519"


def test_apply_name_backfill_no_op_for_already_friendly_name():
    import account_book

    account_book.record_fill(
        code="600519",
        side="buy",
        qty=100,
        price=1800.0,
        trade_date="2026-05-22",
        name="贵州茅台",
    )

    # apply_name_backfill should NOT overwrite a non-code-like existing
    # name with a different one (it only fills in the blank case).
    changed = account_book.apply_name_backfill("600519", "另一个名字")
    assert changed is False

    after = account_book.load_account_book()
    assert after["fills"][0]["name"] == "贵州茅台"


def test_apply_name_backfill_returns_false_for_invalid_code():
    import account_book

    assert account_book.apply_name_backfill("xyz", "测试") is False
    assert account_book.apply_name_backfill("", "测试") is False
