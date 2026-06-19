"""Exit-stock return tracker.

When a candidate exits the shortlist, ``record_exit`` logs it. Each trading
day, ``update_exits`` advances open records: it asks the pricing provider
for the full window of daily closes for a code, keeps the closes that fall
strictly after the exit_date, and once at least ``window_days`` of them are
available, classifies the outcome:

  - ``true_exit``    : net return <= misjudged_threshold (continued down or flat)
  - ``misjudged``    : net return > misjudged_threshold (e.g. rebounded >5%)
  - ``inconclusive`` : exit_price missing, or no post-exit prices obtainable
                       within ``window_days * 2`` calendar days past the exit

``pricing_provider(code) -> {trade_date_str: close}`` returns the whole
window at once so a record settles in a single pass once the window fills.
If the provider returns no usable closes and ``as_of_date`` is more than
``window_days * 2`` past ``exit_date``, the record settles as
``inconclusive`` so a permanently-unpriceable exit does not linger open
forever. The production caller wraps ``prism_data`` gateway ``fetch_kline``.

Storage: append-only JSONL at ``data/runtime/exit_tracking.jsonl``.
"""

from __future__ import annotations

import json
from datetime import date as _date
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from prism_storage.json_store import atomic_write_text

DEFAULT_STORE = Path(__file__).resolve().parents[2] / "data" / "runtime" / "exit_tracking.jsonl"
DEFAULT_WINDOW_DAYS = 5
DEFAULT_MISJUDGED_THRESHOLD = 0.05


def record_exit(
    *,
    store: Path = DEFAULT_STORE,
    code: str,
    name: str,
    exit_date: str,
    exit_price: Optional[float],
    reason: str,
    theme: str,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> None:
    """Append a new exit record. Called from candidate_lifecycle exited branch."""
    store.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "code": code,
        "name": name,
        "exit_date": exit_date,
        "exit_price": exit_price,
        "reason": reason,
        "theme": theme,
        "status": "open",
        "holding_window_days": window_days,
        "recorded_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "daily_prices": [],
        "net_return": None,
        "outcome": None,
    }
    with store.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _load_records(store: Path) -> list[dict]:
    if not store.exists():
        return []
    records = []
    with store.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def _save_records(store: Path, records: list[dict]) -> None:
    """Rewrite the store with all records (atomic via the shared helper)."""
    content = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
    atomic_write_text(store, content)


def _settle(record: dict, misjudged_threshold: float) -> dict:
    """Classify a record based on its accumulated daily_prices."""
    prices = [p for p in record.get("daily_prices", []) if p.get("close") is not None]
    exit_price = record.get("exit_price")
    record["status"] = "settled"
    if not prices or exit_price is None or exit_price <= 0:
        record["outcome"] = "inconclusive"
        return record
    last_close = prices[-1]["close"]
    net_return = last_close / exit_price - 1
    record["net_return"] = round(net_return, 4)
    record["outcome"] = "misjudged" if net_return > misjudged_threshold else "true_exit"
    return record


def update_exits(
    *,
    store: Path = DEFAULT_STORE,
    pricing_provider: Callable[[str], dict],
    as_of_date: str,
    window_days: int = DEFAULT_WINDOW_DAYS,
    misjudged_threshold: float = DEFAULT_MISJUDGED_THRESHOLD,
) -> dict:
    """Advance all open exit records up to ``as_of_date``.

    ``pricing_provider(code)`` must return a ``{trade_date_str: close}`` dict
    covering the post-exit window for that code (may include dates past
    ``as_of_date``; those are ignored).

    A record settles when at least ``window_days`` closes strictly after its
    ``exit_date`` are available and on/before ``as_of_date``. Returns
    ``{"settled": [...], "advanced": int}`` where ``advanced`` counts the
    number of post-exit closes newly recorded this pass.
    """
    records = _load_records(store)
    settled: list[dict] = []
    advanced = 0
    changed = False
    for record in records:
        if record.get("status") != "open":
            continue
        exit_date = record.get("exit_date", "")
        code = record["code"]
        closes = pricing_provider(code) or {}
        # If the exit price was not captured at exit time (the shortlist
        # item carries no close price), backfill it from the exit-day close.
        # This lets classification proceed without changing the shortlist
        # schema; without it every record would be exit_price=None -> inconclusive.
        if record.get("exit_price") in (None, 0) and exit_date in closes:
            record["exit_price"] = closes[exit_date]
            changed = True
        # Keep closes strictly after exit_date and on/before as_of_date,
        # sorted ascending by date, capped at window_days.
        post_exit = sorted(
            (d for d in closes.items() if d[0] > exit_date and d[0] <= as_of_date),
            key=lambda kv: kv[0],
        )[:window_days]
        if post_exit:
            record["daily_prices"] = [{"date": d, "close": c} for d, c in post_exit]
            advanced += len(post_exit)
            changed = True
        if len(record["daily_prices"]) >= window_days:
            _settle(record, misjudged_threshold)
            settled.append(record)
            changed = True
        else:
            # If we cannot fill the window and enough wall-clock time has
            # passed (window_days * 2 past exit), settle as inconclusive so
            # a permanently-unpriceable exit does not linger open forever.
            # This covers both the no-prices case and the partial-prices case
            # (a record that got some closes then the provider went dry).
            try:
                exit_d = _date.fromisoformat(exit_date)
                as_of_d = _date.fromisoformat(as_of_date)
                stale = (as_of_d - exit_d).days > window_days * 2
            except ValueError:
                stale = False
            if stale:
                _settle(record, misjudged_threshold)
                settled.append(record)
                changed = True
    if changed:
        _save_records(store, records)
    return {"settled": settled, "advanced": advanced}
