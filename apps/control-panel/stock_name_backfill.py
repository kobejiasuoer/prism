"""Background worker that backfills friendly stock names.

When account-book writes record fills with codes only (because the
synchronous local-only resolver fell through to the bare 6-digit code),
this worker asynchronously fetches the friendly name via the Sina quote
API and writes it back into:

- ``account_book.fills[*].name`` / ``account_book.positions[code].name``
  / ``account_book.position_plans[*].name`` — via
  :func:`account_book.apply_name_backfill`.
- ``stock-analyzer/config/stocks.json`` — but only for codes that already
  exist in the user's watchlist; we do not auto-add new codes here.

Money-write paths never block on this worker. The worker is best-effort:
fetch failures are silently dropped (and retried after a TTL); when name
lookup succeeds with a still-code-like result, we treat that as failure
too.
"""

from __future__ import annotations

import logging
import os
import queue
import threading
import time
from typing import Any

from account_book import apply_name_backfill as apply_account_book_name
from watchlist_registry import (
    CODE_PATTERN,
    fetch_stock_name,
    load_watchlist_config,
    normalize_stock_code,
    save_watchlist_config,
)


_LOG = logging.getLogger(__name__)

_RETRY_TTL_SECONDS = 30 * 60
_FETCH_TIMEOUT_SECONDS = 6.0
_QUEUE_MAX_SIZE = 256
_QUEUE_POLL_SECONDS = 0.5
_DISABLE_ENV_VAR = "PRISM_DISABLE_STOCK_NAME_BACKFILL"

_queue: "queue.Queue[str]" = queue.Queue(maxsize=_QUEUE_MAX_SIZE)
_inflight: set[str] = set()
_recent_attempts: dict[str, float] = {}
_state_lock = threading.Lock()
_shutdown = threading.Event()
_worker_thread: threading.Thread | None = None


def _normalize(code: Any) -> str | None:
    try:
        return normalize_stock_code(code)
    except ValueError:
        return None


def _is_code_like(name: Any, code: str) -> bool:
    text = str(name or "").strip()
    if not text or text == code:
        return True
    lowered = text.lower()
    return lowered.startswith(("sh", "sz")) and lowered[2:] == code


def needs_backfill(code: Any, name: Any) -> bool:
    """Heuristic for callers: was the resolved name still code-like?

    Returns False (no backfill needed) for invalid codes or when the
    provided ``name`` is already a friendly label.
    """

    normalized = _normalize(code)
    if normalized is None:
        return False
    return _is_code_like(name, normalized)


def _is_disabled() -> bool:
    return bool(os.environ.get(_DISABLE_ENV_VAR, "").strip())


def request_name_backfill(code: Any) -> bool:
    """Enqueue ``code`` for friendly-name lookup.

    Idempotent and side-effect free except for the queue mutation and an
    auto-start of the worker thread on first call. Returns True iff the
    code was newly enqueued.

    No-op when ``PRISM_DISABLE_STOCK_NAME_BACKFILL`` is set in the
    environment (lets tests exercise account-write paths without spinning
    up a thread or making real Sina requests).
    """

    if _is_disabled():
        return False
    normalized = _normalize(code)
    if normalized is None:
        return False
    now = time.monotonic()
    with _state_lock:
        if normalized in _inflight:
            return False
        last = _recent_attempts.get(normalized)
        if last is not None and now - last < _RETRY_TTL_SECONDS:
            return False
        try:
            _queue.put_nowait(normalized)
        except queue.Full:
            _LOG.debug("stock_name_backfill queue full; dropping %s", normalized)
            return False
        _inflight.add(normalized)
        _recent_attempts[normalized] = now
    _ensure_worker_started()
    return True


def _apply_name_to_watchlist(code: str, name: str) -> bool:
    config = load_watchlist_config()
    stocks = config.get("stocks")
    if not isinstance(stocks, list):
        return False
    changed = False
    for entry in stocks:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("code") or "").strip() != code:
            continue
        if _is_code_like(entry.get("name"), code):
            entry["name"] = name
            changed = True
    if changed:
        save_watchlist_config(config)
    return changed


def _process(code: str) -> None:
    try:
        fetched = fetch_stock_name(code, timeout=_FETCH_TIMEOUT_SECONDS)
    except Exception as exc:  # noqa: BLE001
        _LOG.debug("stock_name_backfill fetch failed for %s: %s", code, exc)
        return
    if not fetched or _is_code_like(fetched, code):
        return

    try:
        apply_account_book_name(code, fetched)
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("stock_name_backfill account_book write failed for %s: %s", code, exc)

    try:
        _apply_name_to_watchlist(code, fetched)
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("stock_name_backfill watchlist write failed for %s: %s", code, exc)


def _worker_loop() -> None:
    while not _shutdown.is_set():
        try:
            code = _queue.get(timeout=_QUEUE_POLL_SECONDS)
        except queue.Empty:
            continue
        try:
            _process(code)
        finally:
            with _state_lock:
                _inflight.discard(code)
            _queue.task_done()


def start_worker() -> None:
    """Start the background worker thread (idempotent).

    No-op when ``PRISM_DISABLE_STOCK_NAME_BACKFILL`` is set.
    """

    if _is_disabled():
        return
    _ensure_worker_started()


def _ensure_worker_started() -> None:
    global _worker_thread
    with _state_lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            return
        _shutdown.clear()
        _worker_thread = threading.Thread(
            target=_worker_loop,
            name="prism-stock-name-backfill",
            daemon=True,
        )
        _worker_thread.start()


def stop_worker(timeout: float = 5.0) -> None:
    """Signal the worker to drain and stop (idempotent)."""

    global _worker_thread
    if _worker_thread is None or not _worker_thread.is_alive():
        _worker_thread = None
        return
    _shutdown.set()
    _worker_thread.join(timeout=timeout)
    _worker_thread = None


def worker_is_running() -> bool:
    return _worker_thread is not None and _worker_thread.is_alive()


def queue_size() -> int:
    return _queue.qsize()


def reset_state_for_tests() -> None:
    """Test-only hook: drain the queue and clear bookkeeping."""

    stop_worker(timeout=2.0)
    with _state_lock:
        _inflight.clear()
        _recent_attempts.clear()
    while True:
        try:
            _queue.get_nowait()
            _queue.task_done()
        except queue.Empty:
            break


__all__ = [
    "needs_backfill",
    "queue_size",
    "request_name_backfill",
    "reset_state_for_tests",
    "start_worker",
    "stop_worker",
    "worker_is_running",
]
