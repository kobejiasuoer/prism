"""Canonical account book for small-amount real-money operation.

Why this module exists
----------------------
Up until now Prism's "today action queue" tracked decisions only as
``pending / done / watch / skip`` checklist marks per (trade_date, key).
There was no canonical record of:

* real cash balance held at the broker,
* what fills actually happened (price, qty, fees),
* derived positions and average cost,
* whether a "done" action item ever produced a real trade,
* periodic reconciliation against what the broker says.

This made the system safe enough for paper / observation, but explicitly
not safe for even small real-money experiments — a "done" mark gave a false
sense of completion, and the Portfolio page surfaced a research watchlist
rather than a real account.

This module ships the minimum shape required to push the system one
honest step toward live-small operation:

* explicit ``mode`` (``research`` / ``shadow`` / ``live_small``) with
  fail-closed gating;
* an append-only fill ledger that aggregates into positions + cash;
* explicit cash adjustments (deposits / withdrawals / cost-of-carry);
* periodic reconciliation events binding the local ledger to broker
  truth;
* an "intent linkage" between today's action queue and recorded fills,
  so a `done` decision either has a fill behind it or is explicitly
  marked ``no_fill``.

The store is JSON-on-disk for now (mirrors the rest of
``apps/data/control_panel_state``) so it is trivially backupable and
human-inspectable; readers and writers all flow through this module so
later we can swap the storage layer without touching call sites.

Money convention: all values are CNY, stored as floats with two-decimal
rounding on write.  This is acceptable for a single-user retail account
at this scale; if scope grows we should switch to ``decimal.Decimal``.
"""

from __future__ import annotations

import os
import re
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from prism_storage import AppStateRepository  # type: ignore


__all__ = [
    "ACCOUNT_MODES",
    "AccountBookError",
    "compute_account_view",
    "default_state_path",
    "load_account_book",
    "record_cash_adjustment",
    "record_fill",
    "record_no_fill_intent",
    "record_reconciliation",
    "set_account_mode",
]


ACCOUNT_MODES = ("research", "shadow", "live_small")
ACCOUNT_MODE_LABELS: dict[str, str] = {
    "research": "研究态",
    "shadow": "影子盘",
    "live_small": "小额实盘",
}
ACCOUNT_MODE_TONES: dict[str, str] = {
    "research": "info",
    "shadow": "watch",
    "live_small": "risk",
}


# How recent a reconciliation must be (in seconds) for live_small to count
# as ready.  24h covers "I reconciled at last night's close" without forcing
# an overnight refresh during an active trading session.
RECONCILIATION_FRESH_SECONDS = 36 * 3600

CONTROL_PANEL_ROOT = Path(__file__).resolve().parent
INVEST_FLOW_ROOT = CONTROL_PANEL_ROOT.parent
DEFAULT_STATE_DIR = INVEST_FLOW_ROOT / "data" / "control_panel_state"
DEFAULT_STATE_FILE = DEFAULT_STATE_DIR / "account_book.json"


_REPOSITORY = AppStateRepository()
_STATE_KEY = "account_book"


class AccountBookError(ValueError):
    """Raised for any user-facing validation failure."""


def default_state_path() -> Path:
    """Resolve the on-disk state path, honoring the test override env var.

    The legacy file lives under ``apps/data/control_panel_state``; the env
    var is intended for tests so they don't have to monkey-patch module
    attributes.  Production callers never need to set it.
    """

    override = os.environ.get("PRISM_ACCOUNT_BOOK_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    return DEFAULT_STATE_FILE


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _round_money(value: float) -> float:
    return round(float(value), 2)


def _normalize_code(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        raise AccountBookError("missing stock code")
    # Accept "sh600690" or "600690" (in which case caller is responsible for
    # the prefix). We do not invent a prefix here because that's a market-
    # specific decision that belongs to the watchlist registry.
    if not re.fullmatch(r"[a-z]{0,2}\d{6}", text):
        raise AccountBookError(f"invalid stock code: {value!r}")
    return text


def _normalize_trade_date(value: Any) -> str:
    text = str(value or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise AccountBookError(f"invalid trade_date: {value!r}")
    return text


def _normalize_side(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text not in {"buy", "sell"}:
        raise AccountBookError(f"invalid side: {value!r}; expected buy/sell")
    return text


def _normalize_qty(value: Any, *, side: str) -> int:
    try:
        qty = int(value)
    except (TypeError, ValueError) as exc:
        raise AccountBookError(f"invalid qty: {value!r}") from exc
    if qty <= 0:
        raise AccountBookError("qty must be positive")
    return qty


def _normalize_price(value: Any) -> float:
    try:
        price = float(value)
    except (TypeError, ValueError) as exc:
        raise AccountBookError(f"invalid price: {value!r}") from exc
    if price <= 0:
        raise AccountBookError("price must be positive")
    return _round_money(price)


def _normalize_fees(value: Any) -> float:
    if value in (None, "", "-"):
        return 0.0
    try:
        fees = float(value)
    except (TypeError, ValueError) as exc:
        raise AccountBookError(f"invalid fees: {value!r}") from exc
    if fees < 0:
        raise AccountBookError("fees cannot be negative")
    return _round_money(fees)


def _empty_state() -> dict[str, Any]:
    return {
        "version": 1,
        "mode": "research",
        "mode_updated_at": "",
        "unsafe_bypass_active": False,
        "unsafe_bypass_note": "",
        "unsafe_bypass_at": "",
        "starting_cash": 0.0,
        "cash_balance": 0.0,
        "currency": "CNY",
        "fills": [],
        "cash_adjustments": [],
        "reconciliations": [],
        "no_fill_intents": [],
        "mode_history": [],
        "updated_at": "",
    }


def _coerce_state(data: Any) -> dict[str, Any]:
    state = _empty_state()
    if not isinstance(data, Mapping):
        return state
    mode = str(data.get("mode") or "research").strip().lower()
    if mode not in ACCOUNT_MODES:
        mode = "research"
    state["mode"] = mode
    state["mode_updated_at"] = str(data.get("mode_updated_at") or "")
    state["unsafe_bypass_active"] = bool(data.get("unsafe_bypass_active"))
    state["unsafe_bypass_note"] = str(data.get("unsafe_bypass_note") or "")
    state["unsafe_bypass_at"] = str(data.get("unsafe_bypass_at") or "")
    try:
        state["starting_cash"] = _round_money(float(data.get("starting_cash") or 0))
    except (TypeError, ValueError):
        state["starting_cash"] = 0.0
    try:
        state["cash_balance"] = _round_money(float(data.get("cash_balance") or 0))
    except (TypeError, ValueError):
        state["cash_balance"] = state["starting_cash"]
    state["currency"] = str(data.get("currency") or "CNY")
    state["fills"] = [dict(item) for item in (data.get("fills") or []) if isinstance(item, Mapping)]
    state["cash_adjustments"] = [
        dict(item) for item in (data.get("cash_adjustments") or []) if isinstance(item, Mapping)
    ]
    state["reconciliations"] = [
        dict(item) for item in (data.get("reconciliations") or []) if isinstance(item, Mapping)
    ]
    state["no_fill_intents"] = [
        dict(item) for item in (data.get("no_fill_intents") or []) if isinstance(item, Mapping)
    ]
    state["mode_history"] = [
        dict(item) for item in (data.get("mode_history") or []) if isinstance(item, Mapping)
    ]
    state["updated_at"] = str(data.get("updated_at") or "")
    return state


def load_account_book() -> dict[str, Any]:
    """Return the canonical account state, hydrating defaults if missing."""

    raw = _REPOSITORY.get(_STATE_KEY, legacy_path=default_state_path(), default=None)
    if raw is None:
        return _empty_state()
    return _coerce_state(raw)


def _persist(state: dict[str, Any]) -> dict[str, Any]:
    state["updated_at"] = _now()
    state["cash_balance"] = _round_money(state.get("cash_balance") or 0.0)
    state["starting_cash"] = _round_money(state.get("starting_cash") or 0.0)
    _REPOSITORY.set(_STATE_KEY, state, legacy_path=default_state_path())
    return state


def set_account_mode(
    mode: str,
    *,
    starting_cash: float | None = None,
    note: str = "",
    allow_unsafe: bool = False,
) -> dict[str, Any]:
    """Switch the account mode.

    ``live_small`` requires:
    - Positive cash balance
    - At least one reconciliation event within 36 hours
    - Most recent reconciliation delta within thresholds (cash ≤100, equity ≤200)

    Use ``allow_unsafe=True`` to bypass these checks (requires explicit audit).
    """

    # Reconciliation delta thresholds (same as readiness)
    RECON_CASH_DELTA_THRESHOLD = 100.0
    RECON_EQUITY_DELTA_THRESHOLD = 200.0

    normalized = str(mode or "").strip().lower()
    if normalized not in ACCOUNT_MODES:
        raise AccountBookError(f"invalid mode: {mode!r}")
    note_text = str(note or "").strip()
    if allow_unsafe and not note_text:
        raise AccountBookError("allow_unsafe requires a non-empty note/reason for audit")

    state = load_account_book()
    previous_mode = str(state.get("mode") or "research")
    if starting_cash is not None:
        try:
            cash_value = _round_money(float(starting_cash))
        except (TypeError, ValueError) as exc:
            raise AccountBookError(f"invalid starting_cash: {starting_cash!r}") from exc
        if cash_value < 0:
            raise AccountBookError("starting_cash cannot be negative")
        # If the book has no fills yet it's safe to (re)anchor the cash
        # balance to the new starting value.  Otherwise we only update
        # ``starting_cash`` and let cash adjustments / fills move
        # ``cash_balance``.
        if not state["fills"] and not state["cash_adjustments"]:
            state["cash_balance"] = cash_value
        state["starting_cash"] = cash_value

    if normalized == "live_small" and not allow_unsafe:
        if (state.get("cash_balance") or 0.0) <= 0:
            raise AccountBookError(
                "live_small mode requires a positive cash balance; record an "
                "initial deposit or pass allow_unsafe=True"
            )
        latest = _latest_reconciliation_age_seconds(state, datetime.now())
        if latest is None or latest > RECONCILIATION_FRESH_SECONDS:
            raise AccountBookError(
                "live_small mode requires a reconciliation event within the "
                "last 36 hours; record /api/portfolio/reconcile first"
            )
        # Check reconciliation delta thresholds
        recon_items = state.get("reconciliations") or []
        if recon_items:
            last_recon = recon_items[-1]
            delta_cash = abs(_round_money(last_recon.get("delta_cash", 0.0)))
            delta_equity = abs(_round_money(last_recon.get("delta_equity", 0.0)))
            if delta_cash > RECON_CASH_DELTA_THRESHOLD or delta_equity > RECON_EQUITY_DELTA_THRESHOLD:
                raise AccountBookError(
                    f"live_small mode requires reconciliation delta within thresholds: "
                    f"cash delta {delta_cash:.2f} (threshold {RECON_CASH_DELTA_THRESHOLD:.0f}), "
                    f"equity delta {delta_equity:.2f} (threshold {RECON_EQUITY_DELTA_THRESHOLD:.0f}). "
                    f"Reconcile again or pass allow_unsafe=True"
                )

    state["mode"] = normalized
    state["mode_updated_at"] = _now()
    state["unsafe_bypass_active"] = bool(allow_unsafe)
    state["unsafe_bypass_note"] = note_text if allow_unsafe else ""
    state["unsafe_bypass_at"] = state["mode_updated_at"] if allow_unsafe else ""
    state.setdefault("mode_history", []).append(
        {
            "ts": state["mode_updated_at"],
            "from_mode": previous_mode,
            "to_mode": normalized,
            "note": note_text,
            "allow_unsafe": bool(allow_unsafe),
            "starting_cash": state.get("starting_cash"),
        }
    )
    return _persist(state)


def record_cash_adjustment(
    *,
    delta: float,
    reason: str,
    ts: str | None = None,
) -> dict[str, Any]:
    try:
        delta_value = _round_money(float(delta))
    except (TypeError, ValueError) as exc:
        raise AccountBookError(f"invalid delta: {delta!r}") from exc
    if delta_value == 0:
        raise AccountBookError("delta must be non-zero")
    reason_text = str(reason or "").strip()
    if not reason_text:
        raise AccountBookError("reason is required for cash adjustment")

    state = load_account_book()
    new_balance = _round_money(state.get("cash_balance", 0.0) + delta_value)
    if new_balance < 0:
        raise AccountBookError(
            f"cash adjustment would drive balance below zero: {new_balance}"
        )
    state["cash_balance"] = new_balance
    state["cash_adjustments"].append(
        {
            "ts": ts or _now(),
            "delta": delta_value,
            "balance_after": new_balance,
            "reason": reason_text,
        }
    )
    return _persist(state)


def record_fill(
    *,
    trade_date: str,
    code: str,
    side: str,
    qty: int,
    price: float,
    fees: float | None = 0.0,
    name: str | None = None,
    broker_ref: str | None = None,
    intent_key: str | None = None,
    note: str | None = None,
    ts: str | None = None,
) -> dict[str, Any]:
    """Append a fill, update cash, and return the new state.

    Oversell protection: All modes (research/shadow/live_small) block sells
    that exceed current position. If you need to record an erroneous fill or
    a correction event, use a separate correction mechanism, not record_fill.
    """

    trade_date_n = _normalize_trade_date(trade_date)
    code_n = _normalize_code(code)
    side_n = _normalize_side(side)
    qty_n = _normalize_qty(qty, side=side_n)
    price_n = _normalize_price(price)
    fees_n = _normalize_fees(fees)
    name_n = str(name or code_n).strip() or code_n
    intent_n = str(intent_key or "").strip() or None
    broker_n = str(broker_ref or "").strip() or None

    state = load_account_book()
    notional = _round_money(qty_n * price_n)

    # For sells, check if we have enough position to sell (all modes)
    if side_n == "sell":
        positions = _compute_positions(state.get("fills") or [])
        current_qty = positions.get(code_n, {}).get("qty", 0)
        if qty_n > current_qty:
            raise AccountBookError(
                f"cannot sell {qty_n} shares of {code_n}: only {current_qty} shares held. "
                f"Oversell is blocked in all modes to prevent account book pollution. "
                f"If this is a correction event, use a separate correction mechanism."
            )

    if side_n == "buy":
        cash_delta = -_round_money(notional + fees_n)
    else:  # sell
        cash_delta = _round_money(notional - fees_n)

    new_balance = _round_money(state.get("cash_balance", 0.0) + cash_delta)
    if new_balance < 0 and state.get("mode") == "live_small":
        # In live_small we fail closed: cash should never go negative.  In
        # research / shadow modes we allow it (marker for "I haven't recorded
        # the deposit yet") but flag via UI.
        raise AccountBookError(
            f"fill would overdraft cash in live_small mode (balance would be {new_balance})"
        )

    fill_entry = {
        "fill_id": str(uuid.uuid4()),
        "ts": ts or _now(),
        "trade_date": trade_date_n,
        "code": code_n,
        "name": name_n,
        "side": side_n,
        "qty": qty_n,
        "price": price_n,
        "fees": fees_n,
        "notional": notional,
        "cash_delta": cash_delta,
        "balance_after": new_balance,
        "broker_ref": broker_n,
        "intent_key": intent_n,
        "note": str(note or "").strip(),
    }
    state["fills"].append(fill_entry)
    state["cash_balance"] = new_balance
    return _persist(state)


def record_no_fill_intent(
    *,
    trade_date: str,
    intent_key: str,
    reason: str,
    ts: str | None = None,
) -> dict[str, Any]:
    """Mark an action queue item as deliberately producing no fill.

    Used for ``done`` decisions where the operator intentionally took no
    market action (e.g. "marked as resolved by yesterday's exit").
    """

    trade_date_n = _normalize_trade_date(trade_date)
    intent_n = str(intent_key or "").strip()
    if not intent_n:
        raise AccountBookError("intent_key is required")
    reason_text = str(reason or "").strip()
    if not reason_text:
        raise AccountBookError("reason is required for no_fill markers")

    state = load_account_book()
    # Replace any prior marker for the same (date, intent) pair.
    state["no_fill_intents"] = [
        item
        for item in state["no_fill_intents"]
        if not (
            str(item.get("trade_date") or "") == trade_date_n
            and str(item.get("intent_key") or "") == intent_n
        )
    ]
    state["no_fill_intents"].append(
        {
            "ts": ts or _now(),
            "trade_date": trade_date_n,
            "intent_key": intent_n,
            "reason": reason_text,
        }
    )
    return _persist(state)


def record_reconciliation(
    *,
    trade_date: str,
    broker_cash: float,
    broker_equity: float,
    note: str = "",
    ts: str | None = None,
) -> dict[str, Any]:
    """Capture broker-side truth and the local-vs-broker delta.

    The deltas are recorded but not silently absorbed — operators must
    decide whether to call ``record_cash_adjustment`` or amend a fill.
    This keeps reconciliation as evidence rather than a hidden patch.
    """

    trade_date_n = _normalize_trade_date(trade_date)
    try:
        cash_value = _round_money(float(broker_cash))
        equity_value = _round_money(float(broker_equity))
    except (TypeError, ValueError) as exc:
        raise AccountBookError("broker_cash / broker_equity must be numeric") from exc

    state = load_account_book()
    view = compute_account_view(state)
    state["reconciliations"].append(
        {
            "ts": ts or _now(),
            "trade_date": trade_date_n,
            "broker_cash": cash_value,
            "broker_equity": equity_value,
            "local_cash": _round_money(view["cash_balance"]),
            "local_equity_at_cost": _round_money(view["equity_at_cost"]),
            "delta_cash": _round_money(cash_value - view["cash_balance"]),
            "delta_equity": _round_money(equity_value - view["equity_at_cost"]),
            "note": str(note or "").strip(),
        }
    )
    return _persist(state)


def _latest_reconciliation_age_seconds(state: Mapping[str, Any], now: datetime) -> int | None:
    items = state.get("reconciliations") or []
    if not items:
        return None
    last = items[-1]
    ts_text = str(last.get("ts") or "").strip()
    if not ts_text:
        return None
    try:
        parsed = datetime.strptime(ts_text, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return max(int((now - parsed).total_seconds()), 0)


def _compute_positions(fills: list[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Aggregate fills into FIFO-ish weighted-average positions.

    For sells we apply average-cost accounting: cost basis stays at the
    running average and realized P/L = (sell_price - avg_cost) * qty.  This
    is the simplest model that matches what most retail tax accounting in
    A-shares uses (LIFO is rare in practice).
    """

    positions: dict[str, dict[str, Any]] = {}
    realized_pnl: dict[str, float] = defaultdict(float)
    for fill in fills:
        code = str(fill.get("code") or "")
        if not code:
            continue
        side = str(fill.get("side") or "").lower()
        try:
            qty = int(fill.get("qty") or 0)
            price = float(fill.get("price") or 0.0)
            fees = float(fill.get("fees") or 0.0)
        except (TypeError, ValueError):
            continue
        pos = positions.setdefault(
            code,
            {
                "code": code,
                "name": str(fill.get("name") or code),
                "qty": 0,
                "avg_cost": 0.0,
                "cost_basis": 0.0,
                "realized_pnl": 0.0,
                "last_fill_at": "",
                "fills": 0,
            },
        )
        pos["fills"] += 1
        pos["last_fill_at"] = str(fill.get("ts") or pos["last_fill_at"])
        pos["name"] = str(fill.get("name") or pos.get("name") or code)
        if side == "buy":
            new_qty = pos["qty"] + qty
            new_cost = pos["cost_basis"] + qty * price + fees
            pos["qty"] = new_qty
            pos["cost_basis"] = _round_money(new_cost)
            pos["avg_cost"] = _round_money(new_cost / new_qty) if new_qty else 0.0
        elif side == "sell":
            sell_qty = min(qty, pos["qty"])
            avg_cost = pos["avg_cost"]
            realized = (price * sell_qty) - (avg_cost * sell_qty) - fees
            realized_pnl[code] += realized
            pos["realized_pnl"] = _round_money(pos["realized_pnl"] + realized)
            new_qty = pos["qty"] - sell_qty
            if new_qty <= 0:
                pos["qty"] = 0
                pos["avg_cost"] = 0.0
                pos["cost_basis"] = 0.0
            else:
                pos["qty"] = new_qty
                pos["cost_basis"] = _round_money(avg_cost * new_qty)

    return positions


def compute_account_view(state: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return a derived view (positions, equity_at_cost, etc.) from state."""

    book = dict(state) if state is not None else load_account_book()
    fills = list(book.get("fills") or [])
    positions = _compute_positions(fills)
    open_positions = [pos for pos in positions.values() if pos["qty"] > 0]
    closed_positions = [pos for pos in positions.values() if pos["qty"] == 0 and pos["fills"] > 0]
    cash = _round_money(book.get("cash_balance", 0.0))
    starting = _round_money(book.get("starting_cash", 0.0))
    equity_at_cost = _round_money(sum(p["cost_basis"] for p in open_positions))
    realized_total = _round_money(sum(p["realized_pnl"] for p in positions.values()))
    deposits_total = _round_money(sum(adj.get("delta", 0.0) for adj in (book.get("cash_adjustments") or [])))

    return {
        "mode": book.get("mode", "research"),
        "mode_label": ACCOUNT_MODE_LABELS.get(book.get("mode", "research"), "研究态"),
        "mode_tone": ACCOUNT_MODE_TONES.get(book.get("mode", "research"), "info"),
        "mode_updated_at": book.get("mode_updated_at", ""),
        "unsafe_bypass_active": bool(book.get("unsafe_bypass_active")),
        "unsafe_bypass_note": str(book.get("unsafe_bypass_note") or ""),
        "unsafe_bypass_at": str(book.get("unsafe_bypass_at") or ""),
        "currency": book.get("currency", "CNY"),
        "starting_cash": starting,
        "cash_balance": cash,
        "deposits_total": deposits_total,
        "equity_at_cost": equity_at_cost,
        "book_value": _round_money(cash + equity_at_cost),
        "realized_pnl": realized_total,
        "open_positions": sorted(open_positions, key=lambda p: -p["cost_basis"]),
        "closed_positions": sorted(closed_positions, key=lambda p: p["last_fill_at"], reverse=True),
        "fills_count": len(fills),
        "last_fill_at": fills[-1]["ts"] if fills else "",
        "reconciliations": list(book.get("reconciliations") or [])[-5:],
        "no_fill_intents": list(book.get("no_fill_intents") or []),
        "mode_history": list(book.get("mode_history") or [])[-20:],
        "fills": fills,
        "updated_at": book.get("updated_at", ""),
    }


def reconciliation_status(
    state: Mapping[str, Any] | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Summarize whether the book has a recent reconciliation event."""

    book = dict(state) if state is not None else load_account_book()
    current = now or datetime.now()
    age = _latest_reconciliation_age_seconds(book, current)
    items = book.get("reconciliations") or []
    last = items[-1] if items else None
    return {
        "count": len(items),
        "age_seconds": age,
        "fresh_within_seconds": RECONCILIATION_FRESH_SECONDS,
        "fresh": age is not None and age <= RECONCILIATION_FRESH_SECONDS,
        "last": last,
    }


def unreconciled_intents(
    state: Mapping[str, Any] | None = None,
    *,
    today_decisions_store: Mapping[str, Any] | None = None,
    today: str | None = None,
) -> list[dict[str, Any]]:
    """Find action items that look completed but lack a fill / no_fill marker.

    For each (trade_date, intent_key) in ``today_decisions_store`` whose
    decision is ``done`` and whose trade_date is strictly before ``today``
    (we don't block intra-day items because the operator may still be
    placing the order), require either:

    1. at least one fill with ``intent_key=key`` and ``trade_date=trade_date``, or
    2. an explicit ``no_fill_intents`` entry for the same pair.

    Anything that fails both checks is returned as an unreconciled item.
    """

    book = dict(state) if state is not None else load_account_book()
    today_n = (today or datetime.now().strftime("%Y-%m-%d")).strip()
    decisions = (today_decisions_store or {}).get("trade_dates") or {}

    fill_index: set[tuple[str, str]] = set()
    for fill in book.get("fills") or []:
        ik = str(fill.get("intent_key") or "").strip()
        td = str(fill.get("trade_date") or "").strip()
        if ik and td:
            fill_index.add((td, ik))

    no_fill_index: set[tuple[str, str]] = set()
    for marker in book.get("no_fill_intents") or []:
        ik = str(marker.get("intent_key") or "").strip()
        td = str(marker.get("trade_date") or "").strip()
        if ik and td:
            no_fill_index.add((td, ik))

    pending: list[dict[str, Any]] = []
    for trade_date, items in decisions.items():
        td = str(trade_date or "").strip()
        if not td or td >= today_n:
            # Today (and future) decisions still in flight — don't block.
            continue
        if not isinstance(items, Mapping):
            continue
        for key, payload in items.items():
            if not isinstance(payload, Mapping):
                continue
            decision = str(payload.get("decision") or "").strip().lower()
            if decision != "done":
                continue
            ki = str(key or "").strip()
            if not ki:
                continue
            pair = (td, ki)
            if pair in fill_index or pair in no_fill_index:
                continue
            pending.append(
                {
                    "trade_date": td,
                    "intent_key": ki,
                    "decision_updated_at": str(payload.get("updated_at") or ""),
                }
            )
    pending.sort(key=lambda x: (x["trade_date"], x["intent_key"]))
    return pending
