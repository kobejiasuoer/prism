"""Decision Ledger -- daily decision accountability layer (Phase 1).

The ledger captures three append-only things per recommendation:

1. The original ``DecisionRecord``: what Prism suggested at decision time,
   including the evidence and readiness snapshot it was made on.  This
   record is immutable after creation; later phases attach events to it
   without rewriting the original recommendation.
2. ``ExecutionEvent``: what the operator actually did (fill, no-fill,
   watch, skip).  Phase 3 wires Portfolio writebacks into this stream.
3. ``OutcomeEvent``: what the market did at T+1 / T+3 / T+5.  Phase 4
   runs the evaluator that appends these.

Storage is JSON-on-disk for the MVP -- one file per trade date under
``apps/data/decision_ledger/decisions/<trade_date>.json``.  This matches
the rest of the control-panel runtime artifacts, is trivially
inspectable, and avoids introducing schema-migration infrastructure
before the shape stabilizes.

Acceptance rules enforced here:

* ``decision_id`` is deterministic in ``trade_date``, ``code``, ``surface``,
  ``lane``, ``action_key``, and the normalized recommendation ``action``.
  A material change to the action produces a new id (use
  :func:`mark_decision_superseded` to wire them together).
* Repeat ``upsert_decision`` calls are no-ops -- the on-disk
  recommendation snapshot wins, even if the caller resends drifted text.
* ``append_execution_event`` and ``append_outcome_event`` are append-only
  and de-duplicated (executions by stable event fingerprint, outcomes by
  ``window``).  Neither touches the original recommendation.
* Corrupt JSON raises :class:`DecisionLedgerError` rather than silently
  returning ``[]``.

Outcome classification, today-action capture, and portfolio attachment
live in later phases; this module is only the repository.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Protocol

# Reuse the project-wide atomic JSON writer rather than re-implementing
# tmp+replace.  packages/prism_storage is appended onto prism_storage by
# the top-level __init__ shim.
from prism_storage.json_store import atomic_write_json  # type: ignore

# Reuse the existing market-prefix inference so a "watchlist:600690" queue
# key maps to the same canonical sh/sz code that account_book and the
# stock catalog already use.
from watchlist_registry import infer_market_from_code  # type: ignore

# Phase 4 needs trading-day arithmetic to resolve T+N as_of dates.  We
# defer the import to the call site to avoid pulling the static holiday
# table into every decision_ledger import path (and to keep the test
# isolation pattern -- the calendar module is reload-friendly).
from trading_calendar import (  # type: ignore
    CALENDAR_HORIZON,
    calendar_status,
    next_trading_day,
)


__all__ = [
    "SCHEMA_VERSION",
    "EXECUTION_STATUSES",
    "OUTCOME_WINDOWS",
    "ACTION_ENUM",
    "STATUS_KINDS",
    "DecisionLedgerError",
    "default_ledger_root",
    "make_decision_id",
    "normalize_today_action",
    "build_decision_record",
    "build_decision_record_from_today_item",
    "capture_today_action_queue",
    "load_decisions",
    "load_decision",
    "list_decisions_for_stock",
    "upsert_decision",
    "append_execution_event",
    "append_execution_event_for_writeback",
    "append_outcome_event",
    "mark_decision_superseded",
    "find_decision_for_execution",
    "OutcomeThresholds",
    "PriceProvider",
    "PriceProviderUnavailable",
    "PrismCachePriceProvider",
    "nth_trading_day_after",
    "classify_outcome",
    "evaluate_decision_outcome",
    "find_due_outcomes",
    "evaluate_due_outcomes",
    "normalize_stock_code",
    "summarize_window",
    "list_recent_decisions",
    "scan_all_decisions",
    "status_path",
    "write_status",
    "load_status",
    "build_ledger_health",
]


SCHEMA_VERSION = 1

EXECUTION_STATUSES = ("filled", "no_fill", "watch", "skip", "manual_note")
OUTCOME_WINDOWS = ("T+1", "T+3", "T+5")

# Allowed ``kind`` values for the status helpers below.  The set is small
# on purpose -- this is operator-visible health metadata, not a generic
# key-value store.  Adding a new kind is fine; gating it lets us catch
# typos that would otherwise silently create an orphan status file.
STATUS_KINDS = ("capture", "outcome")

# The canonical action enum used by ``recommendation.action``.  The
# Chinese display label that originally came from the action queue is
# preserved separately in ``recommendation.action_label`` and
# ``recommendation.action_raw``.
ACTION_ENUM = (
    "hold",
    "reduce",
    "observe",
    "trial_buy",
    "skip",
    "forbid",
    "unknown",
)

# Substring keyword rules used by :func:`normalize_today_action`.  Order
# matters: scan negative / decisive actions first so a mixed phrase like
# ``"先继续持有，明天可能减仓"`` resolves to ``reduce`` rather than ``hold``.
_ACTION_KEYWORD_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("forbid", ("禁止", "不可执行", "冻结")),
    ("skip", ("放弃", "跳过")),
    ("reduce", ("减仓", "卖出", "降低仓位")),
    ("trial_buy", ("试错", "买入", "轻仓")),
    ("hold", ("继续持有", "持有")),
    ("observe", ("观察", "跟踪", "待确认")),
)

_GROUP_KEY_FALLBACK = {
    "watch": "observe",
    "avoid": "forbid",
}

CONTROL_PANEL_ROOT = Path(__file__).resolve().parent
INVEST_FLOW_ROOT = CONTROL_PANEL_ROOT.parent
DEFAULT_LEDGER_DIR = INVEST_FLOW_ROOT / "data" / "decision_ledger"


class DecisionLedgerError(ValueError):
    """Raised for user-facing validation failures in the ledger layer."""


# --------------------------------------------------------------------------- paths


def default_ledger_root() -> Path:
    """Resolve the on-disk ledger root, honoring the test override env var.

    Production callers never need to set ``PRISM_DECISION_LEDGER_PATH``;
    tests use it to redirect writes into a temporary directory.
    """

    override = os.environ.get("PRISM_DECISION_LEDGER_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    return DEFAULT_LEDGER_DIR


def _decisions_path(trade_date: str) -> Path:
    return default_ledger_root() / "decisions" / f"{_normalize_trade_date(trade_date)}.json"


# ----------------------------------------------------------------- normalization


_CODE_RE = re.compile(r"[a-z]{0,2}\d{6}")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _normalize_code(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        raise DecisionLedgerError("missing stock code")
    if not _CODE_RE.fullmatch(text):
        raise DecisionLedgerError(f"invalid stock code: {value!r}")
    return text


def _normalize_trade_date(value: Any) -> str:
    text = str(value or "").strip()
    if not _DATE_RE.fullmatch(text):
        raise DecisionLedgerError(f"invalid trade_date: {value!r}")
    return text


def _normalize_action(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        raise DecisionLedgerError("missing recommendation action")
    return text


def normalize_today_action(
    status_label: Any,
    *,
    group_key: Any = None,
    tone: Any = None,
) -> str:
    """Map a Today action queue ``status`` label to a stable enum.

    Recommendation actions move through dashboards, decision IDs, and
    later analytics; keeping the Chinese display label in
    ``recommendation.action`` would couple every downstream query to
    exact wording.  The normalizer collapses the open-ended label space
    into the seven values defined by :data:`ACTION_ENUM`.

    Behavior:

    * Keyword substrings are scanned in a deliberate order (forbid first,
      observe last) so mixed phrases resolve to the more decisive action.
    * When ``status_label`` is empty, the queue's ``group_key`` is used
      as a fallback (``watch`` → ``observe``, ``avoid`` → ``forbid``).
    * Anything we cannot classify becomes ``unknown`` so the caller can
      still produce a record -- silent dropping of unknown phrasing is
      worse than an explicit bucket.
    """

    text = str(status_label or "").strip()
    if text:
        for label, keywords in _ACTION_KEYWORD_RULES:
            for keyword in keywords:
                if keyword in text:
                    return label
    fallback = _GROUP_KEY_FALLBACK.get(str(group_key or "").strip().lower())
    if fallback:
        return fallback
    return "unknown"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ----------------------------------------------------------------- decision id


def make_decision_id(
    *,
    trade_date: str,
    code: str,
    surface: str,
    lane: str,
    action_key: str,
    action: str,
) -> str:
    """Build a stable, human-readable decision id.

    Format::

        <trade_date>:<code>:<surface>:<lane>:<hash8>

    where ``hash8`` is the first 8 hex characters of a sha256 over the
    normalized ``action_key`` plus normalized ``action``.  A material
    change to the recommended action therefore yields a different id;
    cosmetic re-runs collapse to the same id and the on-disk snapshot
    wins.
    """

    trade_date_n = _normalize_trade_date(trade_date)
    code_n = _normalize_code(code)
    surface_n = str(surface or "").strip().lower()
    lane_n = str(lane or "").strip().lower()
    action_key_n = str(action_key or "").strip()
    action_n = _normalize_action(action)
    if not surface_n:
        raise DecisionLedgerError("missing source.surface")
    if not lane_n:
        raise DecisionLedgerError("missing source.lane")
    if not action_key_n:
        raise DecisionLedgerError("missing source.action_key")

    digest_input = f"{action_key_n}|{action_n}".encode("utf-8")
    fingerprint = hashlib.sha256(digest_input).hexdigest()[:8]
    return f"{trade_date_n}:{code_n}:{surface_n}:{lane_n}:{fingerprint}"


def _trade_date_from_id(decision_id: str) -> str:
    """Extract trade_date from a well-formed decision id.

    The id starts with ``YYYY-MM-DD:`` by construction.  We pull that
    prefix here so :func:`load_decision` doesn't have to scan every
    decisions file on disk.
    """

    head = (decision_id or "").split(":", 1)[0]
    if not _DATE_RE.fullmatch(head):
        raise DecisionLedgerError(f"unrecognized decision_id: {decision_id!r}")
    return head


# ------------------------------------------------------------- record building


def build_decision_record(
    *,
    trade_date: str,
    code: str,
    name: str,
    lane: str,
    surface: str,
    action_key: str,
    source_label: str = "",
    artifact_paths: Iterable[str] | None = None,
    action: str,
    action_label: str = "",
    action_raw: str = "",
    main_conclusion: str = "",
    position_guidance: str = "",
    trigger_condition: str = "",
    continue_condition: str = "",
    stop_condition: str = "",
    risk_summary: str = "",
    expected_trade_date: str = "",
    data_trade_date: str = "",
    readiness_mode: str = "",
    readiness_ready: bool = False,
    blockers: Iterable[str] | None = None,
    warnings: Iterable[str] | None = None,
    source_cards: Iterable[Mapping[str, Any]] | None = None,
    metric_cards: Iterable[Mapping[str, Any]] | None = None,
    capital_summary: Mapping[str, Any] | None = None,
    technical_summary: Mapping[str, Any] | None = None,
    theme_summary: Mapping[str, Any] | None = None,
    parameter_path: str | None = None,
    parameter_sha256: str | None = None,
    parameter_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble a DecisionRecord dict ready for :func:`upsert_decision`.

    This builder is deliberately verbose: the snapshot is the contract,
    and burying the schema inside a partial constructor risks future
    callers forgetting to populate the readiness / parameter context the
    later phases rely on.
    """

    trade_date_n = _normalize_trade_date(trade_date)
    code_n = _normalize_code(code)
    decision_id = make_decision_id(
        trade_date=trade_date_n,
        code=code_n,
        surface=surface,
        lane=lane,
        action_key=action_key,
        action=action,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "decision_id": decision_id,
        "trade_date": trade_date_n,
        "created_at": _now(),
        "source": {
            "lane": str(lane or "").strip().lower(),
            "surface": str(surface or "").strip().lower(),
            "action_key": str(action_key or "").strip(),
            "source_label": str(source_label or ""),
            "artifact_paths": list(artifact_paths or []),
        },
        "stock": {
            "code": code_n,
            "name": str(name or ""),
        },
        "recommendation": {
            "action": _normalize_action(action),
            "action_label": str(action_label or ""),
            "action_raw": str(action_raw or ""),
            "main_conclusion": str(main_conclusion or ""),
            "position_guidance": str(position_guidance or ""),
            "trigger_condition": str(trigger_condition or ""),
            "continue_condition": str(continue_condition or ""),
            "stop_condition": str(stop_condition or ""),
            "risk_summary": str(risk_summary or ""),
        },
        "evidence_snapshot": {
            "expected_trade_date": str(expected_trade_date or ""),
            "data_trade_date": str(data_trade_date or ""),
            "readiness_mode": str(readiness_mode or ""),
            "readiness_ready": bool(readiness_ready),
            "blockers": list(blockers or []),
            "warnings": list(warnings or []),
            "source_cards": [dict(card) for card in (source_cards or [])],
            "metric_cards": [dict(card) for card in (metric_cards or [])],
            "capital_summary": dict(capital_summary) if capital_summary else None,
            "technical_summary": dict(technical_summary) if technical_summary else None,
            "theme_summary": dict(theme_summary) if theme_summary else None,
        },
        "parameter_snapshot": {
            "path": parameter_path,
            "sha256": parameter_sha256,
            "summary": dict(parameter_summary) if parameter_summary else None,
        },
        "status": {
            "state": "open",
            "superseded_by": None,
        },
        "execution_events": [],
        "outcome_events": [],
    }


# ------------------------------------------------------------------- file I/O


def _read_decisions_file(path: Path) -> list[dict[str, Any]]:
    """Read a decisions file, raising on any corruption we detect.

    Silently filtering out a non-Mapping element would mask partial
    corruption -- the ledger is the audit log, the operator must hear
    about a broken record rather than have it disappear.  We therefore
    fail closed: bad JSON, wrong root shape, or any non-object element
    triggers :class:`DecisionLedgerError` with the file path and the
    bad record index.
    """

    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DecisionLedgerError(
            f"corrupt decision ledger file {path}: {exc.msg}"
        ) from exc
    if not isinstance(raw, list):
        raise DecisionLedgerError(
            f"corrupt decision ledger file {path}: expected list payload"
        )
    out: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise DecisionLedgerError(
                f"corrupt decision ledger file {path}: "
                f"record at index {index} is not an object "
                f"(got {type(item).__name__})"
            )
        out.append(dict(item))
    return out


def _write_decisions_file(path: Path, records: list[dict[str, Any]]) -> None:
    atomic_write_json(path, records)


def load_decisions(trade_date: str) -> list[dict[str, Any]]:
    """Return all DecisionRecords for ``trade_date`` (empty when missing)."""

    return _read_decisions_file(_decisions_path(trade_date))


def load_decision(decision_id: str) -> dict[str, Any] | None:
    """Return the DecisionRecord with ``decision_id`` or ``None`` if absent."""

    try:
        trade_date = _trade_date_from_id(decision_id)
    except DecisionLedgerError:
        return None
    for record in load_decisions(trade_date):
        if record.get("decision_id") == decision_id:
            return record
    return None


def list_decisions_for_stock(code: str) -> list[dict[str, Any]]:
    """Return every DecisionRecord we have for ``code`` across all dates.

    Accepts either the plain 6-digit form (``600690``) or the prefixed
    form (``sh600690``) -- the ledger stores prefixed codes, so we
    canonicalize before comparing.  Returns ``[]`` for unrecognized
    input (rather than raising) so API callers can present "no results"
    cleanly without distinguishing "bad code" from "no decisions".
    """

    canonical = _canonical_code(code)
    if not canonical:
        return []
    root = default_ledger_root() / "decisions"
    if not root.exists():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        for record in _read_decisions_file(path):
            if (record.get("stock") or {}).get("code") == canonical:
                out.append(record)
    return out


def normalize_stock_code(code: Any) -> str | None:
    """Public wrapper around :func:`_canonical_code` for API callers.

    Returns the prefixed sh/sz form (or ``None`` for unrecognized
    input) so a query like ``?code=600690`` and a query like
    ``?code=sh600690`` reach the same set of stored records.
    """

    return _canonical_code(code)


# ----------------------------------------------------------------- mutations


def upsert_decision(record: Mapping[str, Any]) -> dict[str, Any]:
    """Persist a DecisionRecord, no-op when the id already exists.

    The first call wins: subsequent calls with the same ``decision_id``
    return the stored record unchanged, even if their recommendation
    fields drifted.  This enforces the "snapshot, do not recompute" rule.
    """

    if not isinstance(record, Mapping):
        raise DecisionLedgerError("decision record must be a mapping")
    decision_id = record.get("decision_id")
    if not isinstance(decision_id, str) or not decision_id:
        raise DecisionLedgerError("decision record missing decision_id")
    trade_date = _normalize_trade_date(record.get("trade_date"))

    # The id-prefix is what :func:`load_decision` uses to route reads.
    # If the caller hands us a record whose ``decision_id`` prefix
    # disagrees with ``trade_date``, the file we'd write to would never
    # be discovered again -- so reject it before persisting.
    id_trade_date = _trade_date_from_id(decision_id)
    if id_trade_date != trade_date:
        raise DecisionLedgerError(
            f"decision_id trade_date prefix {id_trade_date!r} does not "
            f"match record trade_date {trade_date!r}"
        )

    path = _decisions_path(trade_date)
    records = _read_decisions_file(path)
    for existing in records:
        if existing.get("decision_id") == decision_id:
            return existing

    # Defensive copy + ensure event lists are present.
    fresh = dict(record)
    fresh.setdefault("schema_version", SCHEMA_VERSION)
    fresh.setdefault("execution_events", [])
    fresh.setdefault("outcome_events", [])
    fresh.setdefault("status", {"state": "open", "superseded_by": None})
    records.append(fresh)
    _write_decisions_file(path, records)
    return fresh


def _locate_decision(decision_id: str) -> tuple[Path, list[dict[str, Any]], dict[str, Any]]:
    try:
        trade_date = _trade_date_from_id(decision_id)
    except DecisionLedgerError as exc:
        raise DecisionLedgerError(f"no such decision: {decision_id!r}") from exc
    path = _decisions_path(trade_date)
    records = _read_decisions_file(path)
    for record in records:
        if record.get("decision_id") == decision_id:
            return path, records, record
    raise DecisionLedgerError(f"no such decision: {decision_id!r}")


def _execution_event_fingerprint(decision_id: str, payload: Mapping[str, Any]) -> str:
    """Stable hash over the user-supplied execution-event fields.

    Two writes with the same status / side / qty / price / trade_date /
    source / note must collapse to one stored event so a Portfolio
    re-submit (or a retried API call) cannot duplicate fills.  Any
    explicit ``event_id`` from the caller wins.
    """

    caller_id = str(payload.get("event_id") or "").strip()
    if caller_id:
        return caller_id

    parts = [
        decision_id,
        str(payload.get("trade_date") or ""),
        str(payload.get("status") or "").lower(),
        str(payload.get("side") or "").lower(),
        repr(payload.get("price")),
        repr(payload.get("quantity")),
        repr(payload.get("amount")),
        str(payload.get("note") or ""),
        str(payload.get("source") or ""),
        str(payload.get("intent_key") or ""),
        str(payload.get("today_action_key") or ""),
    ]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"exec:{digest}"


def append_execution_event(
    decision_id: str, event: Mapping[str, Any]
) -> dict[str, Any]:
    """Append an ExecutionEvent to ``decision_id`` (idempotent)."""

    if not isinstance(event, Mapping):
        raise DecisionLedgerError("execution event must be a mapping")
    status = str(event.get("status") or "").strip().lower()
    if status not in EXECUTION_STATUSES:
        raise DecisionLedgerError(
            f"invalid execution status: {event.get('status')!r}; "
            f"expected one of {EXECUTION_STATUSES}"
        )

    path, records, record = _locate_decision(decision_id)
    fingerprint = _execution_event_fingerprint(decision_id, event)
    existing_events = list(record.get("execution_events") or [])
    for prior in existing_events:
        if prior.get("event_id") == fingerprint:
            return prior

    payload = {
        "schema_version": SCHEMA_VERSION,
        "event_id": fingerprint,
        "decision_id": decision_id,
        "created_at": _now(),
        "trade_date": str(event.get("trade_date") or record.get("trade_date") or ""),
        "status": status,
        "side": str(event.get("side") or "").lower() or None,
        "price": event.get("price"),
        "quantity": event.get("quantity"),
        "amount": event.get("amount"),
        "note": str(event.get("note") or ""),
        "source": str(event.get("source") or ""),
        "intent_key": str(event.get("intent_key") or "") or None,
        "today_action_key": str(event.get("today_action_key") or "") or None,
    }
    existing_events.append(payload)
    record["execution_events"] = existing_events
    _write_decisions_file(path, records)
    return payload


def append_outcome_event(
    decision_id: str, event: Mapping[str, Any]
) -> dict[str, Any]:
    """Append an OutcomeEvent to ``decision_id`` (idempotent per window)."""

    if not isinstance(event, Mapping):
        raise DecisionLedgerError("outcome event must be a mapping")
    window = str(event.get("window") or "").strip().upper()
    if window not in OUTCOME_WINDOWS:
        raise DecisionLedgerError(
            f"invalid outcome window: {event.get('window')!r}; "
            f"expected one of {OUTCOME_WINDOWS}"
        )

    path, records, record = _locate_decision(decision_id)
    existing_events = list(record.get("outcome_events") or [])
    for prior in existing_events:
        if (prior.get("window") or "").upper() == window:
            return prior

    payload = {
        "schema_version": SCHEMA_VERSION,
        "event_id": f"outcome:{decision_id}:{window.lower().replace('+', '')}",
        "decision_id": decision_id,
        "window": window,
        "evaluated_at": str(event.get("evaluated_at") or _now()),
        "as_of_trade_date": str(event.get("as_of_trade_date") or ""),
        "market_data": dict(event.get("market_data") or {}),
        "boundary_checks": dict(event.get("boundary_checks") or {}),
        "classification": dict(event.get("classification") or {}),
        "quality": dict(event.get("quality") or {}),
    }
    existing_events.append(payload)
    record["outcome_events"] = existing_events
    _write_decisions_file(path, records)
    return payload


def mark_decision_superseded(decision_id: str, *, by: str) -> dict[str, Any]:
    """Flag ``decision_id`` as superseded by ``by``.

    Recommendation fields are not touched; only ``status.state`` and
    ``status.superseded_by`` move.  Use this when a material change to
    the recommendation produces a new ``decision_id`` and you want the
    operator to be able to trace the lineage.
    """

    if not isinstance(by, str) or not by:
        raise DecisionLedgerError("supersede target id is required")
    path, records, record = _locate_decision(decision_id)
    record["status"] = {"state": "superseded", "superseded_by": by}
    _write_decisions_file(path, records)
    return record


# ============================================================================
# Phase 2 -- capture from the Today action queue.
#
# The capture layer is intentionally a thin adapter: it parses the queue
# item shape that ``dashboard_data.build_today_action_queue`` produces,
# pulls out the fields the snapshot needs, and hands them to
# :func:`build_decision_record`.  No today-action artifacts are mutated.
# ============================================================================


_TODAY_ACTION_SURFACE = "today_action_queue"

_TODAY_KEY_RE = re.compile(r"^(?P<lane>[a-z_]+):(?P<code>\d{6})$")


def _parse_today_action_key(key: str) -> tuple[str, str]:
    """Return ``(lane_prefix, plain_code)`` from a queue item key.

    Queue keys are produced by ``build_today_task_item`` and have the
    shape ``"watchlist:600690"`` / ``"screening:000001"`` /
    ``"confirmation:002179"``.  We never invent a key here -- if the
    shape doesn't match, we reject the item.
    """

    match = _TODAY_KEY_RE.match(str(key or "").strip())
    if not match:
        raise DecisionLedgerError(f"unrecognized today_action key: {key!r}")
    return match.group("lane"), match.group("code")


def _extract_stock_name(title: str, plain_code: str) -> str:
    """Best-effort name extraction from a queue item title.

    Titles produced by ``build_today_*_task_item`` follow the
    ``"<name> <code>"`` convention.  We strip the code suffix and use
    the remainder as the name.  When the title degrades to a generic
    placeholder we accept it -- a missing name is not a capture
    failure.
    """

    text = str(title or "").strip()
    if not text:
        return ""
    if plain_code and text.endswith(plain_code):
        return text[: -len(plain_code)].strip()
    return text


def _normalize_metric_cards(metrics: Any) -> list[dict[str, Any]]:
    """Coerce the queue item's ``metrics`` list (strings) into card dicts."""

    out: list[dict[str, Any]] = []
    if not metrics:
        return out
    for raw in metrics:
        text = str(raw or "").strip()
        if not text:
            continue
        out.append({"text": text})
    return out


def build_decision_record_from_today_item(
    item: Mapping[str, Any],
    *,
    trade_date: str,
    expected_trade_date: str,
    data_trade_date: str,
    readiness_mode: str,
    readiness_ready: bool,
) -> dict[str, Any]:
    """Convert a single Today action queue entry into a DecisionRecord.

    The caller supplies the queue-level readiness context because it is
    not present on the individual item -- the queue computes one
    readiness mode for the whole list.  Per-item trust info (blockers /
    warnings produced by ``today_action_item_trust``) is pulled off the
    item.
    """

    if not isinstance(item, Mapping):
        raise DecisionLedgerError("today action item must be a mapping")

    action_key = str(item.get("key") or "").strip()
    _, plain_code = _parse_today_action_key(action_key)

    market = infer_market_from_code(plain_code)
    prefixed_code = f"{market}{plain_code}"

    # ``lane_key`` is set by ``attach_today_task_context`` and is more
    # specific than the key prefix (e.g. ``"midday_confirmation"`` vs.
    # ``"confirmation"``).  Fall back to the key prefix when missing.
    lane = str(item.get("lane_key") or action_key.split(":", 1)[0] or "").strip().lower()

    title = str(item.get("title") or "")
    name = _extract_stock_name(title, plain_code)

    status_label = str(item.get("status") or "").strip()
    group_key = str(item.get("group_key") or "").strip().lower()
    tone = str(item.get("tone") or "").strip().lower()
    action = normalize_today_action(status_label, group_key=group_key, tone=tone)
    action_label = status_label or str(item.get("group_title") or "")

    trust = item.get("trust") or {}
    blockers = list((trust.get("blockers") or []))
    warnings = list((trust.get("warnings") or []))

    metric_cards = _normalize_metric_cards(item.get("metrics"))

    return build_decision_record(
        trade_date=trade_date,
        code=prefixed_code,
        name=name,
        lane=lane,
        surface=_TODAY_ACTION_SURFACE,
        action_key=action_key,
        source_label=str(item.get("source") or ""),
        artifact_paths=[item.get("url")] if item.get("url") else [],
        action=action,
        action_label=action_label,
        action_raw=status_label,
        main_conclusion=str(item.get("detail") or ""),
        position_guidance="",
        trigger_condition="",
        continue_condition="",
        stop_condition="",
        risk_summary=str(item.get("foot") or ""),
        expected_trade_date=expected_trade_date,
        data_trade_date=data_trade_date,
        readiness_mode=readiness_mode,
        readiness_ready=readiness_ready,
        blockers=blockers,
        warnings=warnings,
        source_cards=[],
        metric_cards=metric_cards,
        capital_summary=None,
        technical_summary=None,
        theme_summary=None,
        parameter_path=None,
        parameter_sha256=None,
        parameter_summary=None,
    )


def capture_today_action_queue(today_view: Mapping[str, Any]) -> dict[str, Any]:
    """Capture actionable + stale items from a today_view into the ledger.

    The function is idempotent: re-running with the same input does not
    create duplicate records.  Items whose ``key`` fails to parse are
    skipped and counted under ``skipped`` -- this keeps a single bad
    item from poisoning the whole capture run.

    When a new decision arrives for the same ``(trade_date, stock.code,
    source.surface, source.lane, source.action_key)`` but with a
    different ``decision_id`` than an existing *open* record, the older
    record is marked ``superseded`` after the new one persists.  This is
    a conservative match: we never touch a closed record, and we only
    supersede when every key field lines up so a coincidental action_key
    collision cannot drop a different decision.

    Returns a small summary suitable for tasks / API responses::

        {
          "trade_date": "2026-05-15",
          "captured": <int>,           # newly written this call
          "already_present": <int>,    # idempotent skip
          "skipped": <int>,            # parse failures
          "superseded": <int>,         # old records marked superseded this call
          "decision_ids": [<str>, ...] # ids for every persisted record
                                       # (both new and pre-existing)
        }
    """

    if not isinstance(today_view, Mapping):
        raise DecisionLedgerError("today_view must be a mapping")

    trade_date = _normalize_trade_date(today_view.get("trade_date"))
    expected_trade_date = str(today_view.get("expected_trade_date") or trade_date)
    data_trade_date = str(today_view.get("data_trade_date") or trade_date)
    readiness = today_view.get("readiness") or {}
    readiness_mode = str(readiness.get("readiness_mode") or "live_ready")
    queue_level_ready = bool(readiness.get("ready"))

    action_queue = today_view.get("action_queue") or {}
    items = list(action_queue.get("items") or [])
    stale_items = list(action_queue.get("stale_items") or [])

    captured = 0
    already_present = 0
    skipped = 0
    superseded_count = 0
    decision_ids: list[str] = []

    def _try_capture(item: Mapping[str, Any], *, ready_override: bool | None) -> None:
        nonlocal captured, already_present, skipped, superseded_count
        try:
            # If the queue marked this item as not actionable, the
            # per-item readiness wins over the queue-level flag.  The
            # caller may also pass an explicit override (used for the
            # stale_items branch below).
            per_item_ready = (
                ready_override
                if ready_override is not None
                else bool(item.get("actionable"))
            )
            record = build_decision_record_from_today_item(
                item,
                trade_date=trade_date,
                expected_trade_date=expected_trade_date,
                data_trade_date=data_trade_date,
                readiness_mode=readiness_mode if per_item_ready else (
                    readiness_mode if readiness_mode != "live_ready" else "shadow_only"
                ),
                readiness_ready=per_item_ready and queue_level_ready,
            )
        except DecisionLedgerError:
            skipped += 1
            return

        decision_id = record["decision_id"]
        existing = load_decision(decision_id)
        if existing is None:
            # Material-change supersede check: find any OPEN decision on
            # the same date+stock+source that has a different id and
            # mark it superseded once the new record lands.  We compute
            # the list before persisting so the new record itself
            # cannot be a self-match.
            stale_ids = _find_supersede_candidates(record)
            upsert_decision(record)
            captured += 1
            for old_id in stale_ids:
                try:
                    mark_decision_superseded(old_id, by=decision_id)
                except DecisionLedgerError:
                    # The other record disappeared between our scan and
                    # the mark -- not fatal, just don't count it.
                    continue
                superseded_count += 1
        else:
            already_present += 1
        decision_ids.append(decision_id)

    for item in items:
        _try_capture(item, ready_override=None)
    for item in stale_items:
        # ``stale_items`` are by definition not trusted, so we force
        # readiness_ready=False even if the item dict somehow lies.
        _try_capture(item, ready_override=False)

    return {
        "trade_date": trade_date,
        "captured": captured,
        "already_present": already_present,
        "skipped": skipped,
        "superseded": superseded_count,
        "decision_ids": decision_ids,
    }


def _find_supersede_candidates(record: Mapping[str, Any]) -> list[str]:
    """Return open decision_ids that the given record should supersede.

    Match keys (every field must line up):

    * same ``trade_date``
    * same ``stock.code``
    * same ``source.surface``
    * same ``source.lane``
    * same ``source.action_key``
    * different ``decision_id``
    * ``status.state == "open"``

    The intent is to flag a stale recommendation when a fresh capture
    arrives with a changed ``action`` (which forces a new id).  We never
    look at the recommendation fields themselves -- the id collision
    rules are enough, and tying supersede to recommendation diffs would
    surprise an operator who only saw the action change.
    """

    trade_date = str(record.get("trade_date") or "")
    if not trade_date:
        return []
    source = record.get("source") or {}
    stock = record.get("stock") or {}
    target_code = str(stock.get("code") or "").lower()
    target_surface = str(source.get("surface") or "").lower()
    target_lane = str(source.get("lane") or "").lower()
    target_action_key = str(source.get("action_key") or "")
    target_id = str(record.get("decision_id") or "")
    if not target_code or not target_action_key:
        return []

    try:
        same_day = load_decisions(trade_date)
    except DecisionLedgerError:
        # The supersede check is best-effort; the upsert path raises
        # loudly on corruption.  Don't shadow that error here.
        return []

    out: list[str] = []
    for other in same_day:
        other_id = str(other.get("decision_id") or "")
        if not other_id or other_id == target_id:
            continue
        status_state = str((other.get("status") or {}).get("state") or "")
        if status_state != "open":
            continue
        other_source = other.get("source") or {}
        if str((other.get("stock") or {}).get("code") or "").lower() != target_code:
            continue
        if str(other_source.get("surface") or "").lower() != target_surface:
            continue
        if str(other_source.get("lane") or "").lower() != target_lane:
            continue
        if str(other_source.get("action_key") or "") != target_action_key:
            continue
        out.append(other_id)
    return out


# ============================================================================
# Phase 3 -- attach human execution to captured decisions.
#
# This layer answers "what did the operator actually do?".  It does not
# evaluate market outcome and it does not mutate the original
# recommendation.  The two helpers below sit in front of
# :func:`append_execution_event` so endpoint code (Portfolio fills,
# no-fill intents, Today action decisions) can attach a writeback
# without crashing the whole request when no captured decision exists.
# ============================================================================


_PREFIXED_CODE_RE = re.compile(r"[a-z]{2}\d{6}")
_PLAIN_CODE_RE = re.compile(r"\d{6}")


def _canonical_code(code: Any) -> str | None:
    """Return the prefixed sh/sz form of ``code`` or ``None`` on garbage.

    Ledger records always store ``stock.code`` in the prefixed form
    (``sh600690`` / ``sz000001``).  Writeback callers may hand us either
    form depending on which UI surface they came from -- we accept both
    and never raise.
    """

    text = str(code or "").strip().lower()
    if not text:
        return None
    if _PREFIXED_CODE_RE.fullmatch(text):
        return text
    if _PLAIN_CODE_RE.fullmatch(text):
        try:
            market = infer_market_from_code(text)
        except Exception:  # pragma: no cover - defensive
            return None
        return f"{market}{text}"
    return None


def _scan_open_decisions(trade_date: str | None) -> list[dict[str, Any]]:
    """Yield every open DecisionRecord, optionally constrained to a date.

    Used by :func:`find_decision_for_execution` so the matching logic
    walks a small candidate set rather than every captured record.
    """

    root = default_ledger_root() / "decisions"
    if not root.exists():
        return []
    if trade_date:
        try:
            normalized = _normalize_trade_date(trade_date)
        except DecisionLedgerError:
            return []
        files = [root / f"{normalized}.json"]
    else:
        files = sorted(root.glob("*.json"))

    out: list[dict[str, Any]] = []
    for path in files:
        for record in _read_decisions_file(path):
            if (record.get("status") or {}).get("state") == "open":
                out.append(record)
    return out


def find_decision_for_execution(
    *,
    trade_date: str | None,
    code: str | None,
    intent_key: str | None = None,
    today_action_key: str | None = None,
) -> tuple[dict[str, Any] | None, str]:
    """Find the captured DecisionRecord a writeback should attach to.

    Match priority (per Phase 3 plan):

    1. ``source.action_key`` equals the supplied ``intent_key``
    2. ``source.action_key`` equals the supplied ``today_action_key``
    3. same ``trade_date`` and ``stock.code`` (sh/sz prefix tolerant)

    Only ``status.state == "open"`` records are considered -- closed /
    superseded decisions never accept new execution events.

    Returns ``(decision, status)`` where ``status`` is one of
    ``"matched"`` / ``"none"`` / ``"ambiguous"``.  We refuse to bind
    blindly when more than one open candidate matches; conservative
    non-attachment is far better than wiring a fill to the wrong
    decision.
    """

    candidates = _scan_open_decisions(trade_date)
    if not candidates:
        return None, "none"

    def _by_action_key(target: str) -> list[dict[str, Any]]:
        target_n = target.strip()
        if not target_n:
            return []
        return [
            rec
            for rec in candidates
            if str((rec.get("source") or {}).get("action_key") or "").strip()
            == target_n
        ]

    if intent_key:
        matches = _by_action_key(intent_key)
        if len(matches) == 1:
            return matches[0], "matched"
        if len(matches) > 1:
            return None, "ambiguous"
        # Fall through to next tier when intent_key matches nothing.

    if today_action_key:
        matches = _by_action_key(today_action_key)
        if len(matches) == 1:
            return matches[0], "matched"
        if len(matches) > 1:
            return None, "ambiguous"

    canonical = _canonical_code(code)
    if canonical:
        matches = [
            rec
            for rec in candidates
            if str((rec.get("stock") or {}).get("code") or "").lower()
            == canonical
        ]
        if len(matches) == 1:
            return matches[0], "matched"
        if len(matches) > 1:
            return None, "ambiguous"

    return None, "none"


def append_execution_event_for_writeback(
    *,
    trade_date: str | None,
    code: str | None,
    status: str,
    side: str | None = None,
    price: float | None = None,
    quantity: float | None = None,
    amount: float | None = None,
    note: str = "",
    intent_key: str | None = None,
    today_action_key: str | None = None,
    source: str = "portfolio_writeback",
) -> dict[str, Any]:
    """Best-effort attach of a writeback to its captured decision.

    The helper never raises -- Portfolio / Today endpoints rely on the
    calling-site contract that a ledger failure must not block the
    canonical write.  Possible return shapes::

        {"attached": True,  "decision_id": "...", "event_id": "...", "status": "filled"}
        {"attached": False, "reason": "no_matching_decision"}
        {"attached": False, "reason": "ambiguous_decision"}
        {"attached": False, "reason": "ineligible"}
        {"attached": False, "reason": "ledger_error", "detail": "..."}
    """

    try:
        decision, match_status = find_decision_for_execution(
            trade_date=trade_date,
            code=code,
            intent_key=intent_key,
            today_action_key=today_action_key,
        )
    except DecisionLedgerError as exc:
        return {"attached": False, "reason": "ledger_error", "detail": str(exc)}

    if match_status == "ambiguous":
        return {"attached": False, "reason": "ambiguous_decision"}
    if decision is None:
        return {"attached": False, "reason": "no_matching_decision"}

    payload = {
        "trade_date": trade_date or decision.get("trade_date") or "",
        "status": status,
        "side": side,
        "price": price,
        "quantity": quantity,
        "amount": amount,
        "note": note,
        "intent_key": intent_key,
        "today_action_key": today_action_key,
        "source": source,
    }

    try:
        event = append_execution_event(decision["decision_id"], payload)
    except DecisionLedgerError as exc:
        return {"attached": False, "reason": "ledger_error", "detail": str(exc)}

    return {
        "attached": True,
        "decision_id": decision["decision_id"],
        "event_id": event["event_id"],
        "status": event["status"],
    }


# ============================================================================
# Phase 4 -- Outcome evaluator.
#
# Walk every captured DecisionRecord, decide whether its T+1 / T+3 / T+5
# evaluation windows have closed, fetch post-decision price action via a
# pluggable :class:`PriceProvider`, compute conservative market metrics,
# classify the outcome with a small rule table, and append the result as
# an OutcomeEvent.
#
# The evaluator never asserts a label when the data does not support it
# -- it falls back to ``data_issue`` / ``inconclusive`` rather than
# fabricating precision.  Idempotency comes for free from
# :func:`append_outcome_event` (one event per window).
#
# This layer does NOT mutate the original recommendation, does not hit
# the network on its own, and does not classify execution outcomes that
# Phase 3 has not yet captured.
# ============================================================================


_OUTCOME_WINDOW_STEPS: dict[str, int] = {"T+1": 1, "T+3": 3, "T+5": 5}


@dataclass(frozen=True)
class OutcomeThresholds:
    """Single source of truth for outcome classification cut-offs.

    Lives here (rather than scattered across UI code) so we can tune
    one set of numbers and re-run the evaluator.  The defaults are
    deliberately conservative -- the goal is to prefer ``inconclusive``
    over fake precision.
    """

    # trial_buy / hold WITH benchmark: relative outperformance matters.
    validated_relative_return_pct: float = 1.5
    invalidated_relative_return_pct: float = -3.0

    # trial_buy / hold WITHOUT benchmark: looser absolute thresholds,
    # used only when we cannot compute relative_return_pct.
    validated_absolute_return_pct: float = 3.0
    invalidated_absolute_return_pct: float = -5.0

    # skip / reduce / forbid: absolute price action is the right metric;
    # we're judging "was the caution warranted?".
    avoided_loss_return_pct: float = -2.0
    missed_opportunity_return_pct: float = 3.0

    # observe is the most ambivalent recommendation; require a clearer
    # move before claiming we missed something.
    observe_missed_opportunity_return_pct: float = 5.0


class PriceProvider(Protocol):
    """Daily-bar provider used by the outcome evaluator.

    Implementations must return chronologically ordered rows.  Each row
    needs at minimum ``trade_date`` (``YYYY-MM-DD`` string) plus
    ``open`` / ``high`` / ``low`` / ``close`` floats.  Missing trading
    days within the window may be omitted; the evaluator treats gaps as
    missing data, not zero-return days.

    The Protocol is structural: tests pass a tiny fake; production
    callers (the future scheduled task / CLI) wire in a concrete
    provider that reuses the existing quote infrastructure.  No
    provider is shipped here on purpose -- Phase 4 deliberately keeps
    network access out of the audit layer.

    When the upstream data source is transiently unreachable (network
    outage, cache not yet warmed, etc.), implementations should raise
    :class:`PriceProviderUnavailable` -- the evaluator treats that as
    "skip and try again later" rather than as permanently-missing data.
    Returning an empty list, in contrast, is interpreted as
    authoritative "no data for this code+window", which becomes a
    ``data_issue`` outcome.
    """

    def fetch_window(
        self,
        code: str,
        *,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        ...


class PriceProviderUnavailable(RuntimeError):
    """Raised by a :class:`PriceProvider` for transient outages.

    The evaluator catches this and counts the window under
    ``skipped_provider_unavailable`` without writing an OutcomeEvent.
    A later rerun with the provider restored will classify the same
    window normally.

    Implementations should NOT raise this for permanently-missing data
    (e.g., a delisted code that the upstream confirms it has nothing
    for); return an empty list for that case so the evaluator can
    persist a ``data_issue`` event.
    """


# ----------------------------------------------------------- trading-day math


def nth_trading_day_after(trade_date: str, n: int) -> str | None:
    """Return the ``n``-th trading day strictly after ``trade_date``.

    Returns ``None`` when:

    * ``n`` is not positive.
    * ``trade_date`` cannot be parsed.
    * the result lands past :data:`CALENDAR_HORIZON` (we refuse to
      assert "trading day" past the published exchange calendar).

    The function never raises -- a ``None`` return tells the caller to
    treat the window as not-yet-due / unknown rather than make up a
    date.
    """

    if not isinstance(n, int) or n < 1:
        return None
    try:
        base = datetime.strptime(str(trade_date), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    cursor = base
    horizon = CALENDAR_HORIZON
    for _ in range(n):
        candidate = cursor + timedelta(days=1)
        # ``next_trading_day`` walks forward and returns the candidate
        # itself when it IS a trading day -- which is exactly the
        # "strictly after" semantics we need.
        nxt = next_trading_day(candidate)
        if not isinstance(nxt, date):  # pragma: no cover - defensive
            return None
        if nxt > horizon:
            return None
        cursor = nxt
    return cursor.strftime("%Y-%m-%d")


# ------------------------------------------------------- classification core


def _has_execution_status(events: Iterable[Mapping[str, Any]], target: str) -> bool:
    target_n = target.lower()
    for event in events or []:
        if str(event.get("status") or "").lower() == target_n:
            return True
    return False


def classify_outcome(
    *,
    action: str,
    return_pct: float,
    relative_return_pct: float | None,
    benchmark_available: bool,
    execution_events: Iterable[Mapping[str, Any]] | None,
    thresholds: OutcomeThresholds,
) -> dict[str, Any]:
    """Conservative outcome label for one (decision, window) pair.

    The rules deliberately err toward ``inconclusive``.  Every branch
    explains its decision in ``reasons`` so reviewers can audit the
    label without re-running the math.
    """

    events_list = list(execution_events or [])
    action_n = (action or "").lower().strip()
    reasons: list[str] = []

    has_filled = _has_execution_status(events_list, "filled")
    has_no_fill_or_skip = _has_execution_status(events_list, "no_fill") or (
        _has_execution_status(events_list, "skip")
    )

    if action_n in {"trial_buy", "hold"}:
        if relative_return_pct is not None and benchmark_available:
            metric = relative_return_pct
            metric_label = "relative"
            val_threshold = thresholds.validated_relative_return_pct
            inv_threshold = thresholds.invalidated_relative_return_pct
        else:
            metric = return_pct
            metric_label = "absolute"
            val_threshold = thresholds.validated_absolute_return_pct
            inv_threshold = thresholds.invalidated_absolute_return_pct

        if metric >= val_threshold:
            label = "validated"
            tone = "positive"
            reasons.append(
                f"{metric_label} return {metric:+.2f}% >= {val_threshold:+.2f}%"
            )
            # Execution gap: recommendation worked, but the operator did
            # not participate at all.  A partial fill (filled + no_fill
            # markers) still counts as participation.
            if has_no_fill_or_skip and not has_filled:
                label = "execution_gap"
                tone = "warn"
                reasons.append(
                    "recommendation validated but execution events include "
                    "no_fill / skip without any filled event"
                )
        elif metric <= inv_threshold:
            label = "invalidated"
            tone = "risk"
            reasons.append(
                f"{metric_label} return {metric:+.2f}% <= {inv_threshold:+.2f}%"
            )
        else:
            label = "inconclusive"
            tone = "watch"
            reasons.append(
                f"{metric_label} return {metric:+.2f}% inside neutral band "
                f"({inv_threshold:+.2f}%, {val_threshold:+.2f}%)"
            )

    elif action_n in {"skip", "reduce", "forbid"}:
        if return_pct <= thresholds.avoided_loss_return_pct:
            label = "avoided_loss"
            tone = "positive"
            reasons.append(
                f"absolute return {return_pct:+.2f}% validates caution "
                f"(<= {thresholds.avoided_loss_return_pct:+.2f}%)"
            )
        elif return_pct >= thresholds.missed_opportunity_return_pct:
            label = "missed_opportunity"
            tone = "risk"
            reasons.append(
                f"absolute return {return_pct:+.2f}% contradicts caution "
                f"(>= {thresholds.missed_opportunity_return_pct:+.2f}%)"
            )
        else:
            label = "inconclusive"
            tone = "watch"
            reasons.append(
                f"absolute return {return_pct:+.2f}% inside neutral band"
            )

    elif action_n == "observe":
        if return_pct >= thresholds.observe_missed_opportunity_return_pct:
            label = "missed_opportunity"
            tone = "watch"
            reasons.append(
                f"observe-only call but absolute return {return_pct:+.2f}% "
                f">= {thresholds.observe_missed_opportunity_return_pct:+.2f}%"
            )
        else:
            label = "inconclusive"
            tone = "watch"
            reasons.append(
                f"observe-only call; absolute return {return_pct:+.2f}% "
                "does not clear missed-opportunity threshold"
            )

    else:
        # ``unknown`` (or anything we forgot to bucket) is explicitly
        # inconclusive rather than guessed.
        label = "inconclusive"
        tone = "watch"
        reasons.append(
            f"action enum '{action_n}' has no classification rule -- "
            "label deferred to inconclusive"
        )

    return {
        "label": label,
        "tone": tone,
        "summary": reasons[0] if reasons else "",
        "reasons": reasons,
    }


# ---------------------------------------------------------- single-window eval


def _row_for_date(rows: list[Mapping[str, Any]], target: str) -> Mapping[str, Any] | None:
    for row in rows:
        if str(row.get("trade_date") or "") == target:
            return row
    return None


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _data_issue_event(
    decision_id: str,
    window: str,
    *,
    as_of_trade_date: str,
    reason: str,
) -> dict[str, Any]:
    """Outcome dict to hand off to :func:`append_outcome_event` when we
    cannot confidently classify the window.

    Stored with ``usable_for_decision_quality: false`` so the
    review-layer hit-rate calc knows to exclude it.
    """

    return {
        "window": window,
        "as_of_trade_date": as_of_trade_date,
        "market_data": {
            "entry_reference_price": None,
            "close_price": None,
            "return_pct": None,
            "benchmark_code": None,
            "benchmark_return_pct": None,
            "relative_return_pct": None,
            "max_favorable_pct": None,
            "max_adverse_pct": None,
        },
        "boundary_checks": {
            "trigger_touched": None,
            "stop_touched": None,
            "continue_condition_held": None,
        },
        "classification": {
            "label": "data_issue",
            "tone": "warn",
            "summary": reason,
            "reasons": [reason],
        },
        "quality": {
            "usable_for_decision_quality": False,
            "data_issue": reason,
        },
    }


def evaluate_decision_outcome(
    decision: Mapping[str, Any],
    *,
    window: str,
    price_provider: PriceProvider,
    benchmark_code: str | None = "000300",
    thresholds: OutcomeThresholds | None = None,
) -> dict[str, Any]:
    """Compute one OutcomeEvent dict for ``(decision, window)``.

    The returned dict is suitable for :func:`append_outcome_event` --
    the caller decides whether to persist (the orchestrator below does
    so unconditionally; tests sometimes inspect without persisting).
    Never raises: missing data degrades to a ``data_issue`` outcome.
    """

    if window not in _OUTCOME_WINDOW_STEPS:
        raise DecisionLedgerError(f"unsupported outcome window: {window!r}")
    thresholds = thresholds or OutcomeThresholds()
    decision_id = str(decision.get("decision_id") or "")
    trade_date = str(decision.get("trade_date") or "")

    as_of = nth_trading_day_after(trade_date, _OUTCOME_WINDOW_STEPS[window])
    if not as_of:
        return _data_issue_event(
            decision_id,
            window,
            as_of_trade_date="",
            reason=f"cannot resolve {window} as_of trade date from {trade_date!r}",
        )

    code = str((decision.get("stock") or {}).get("code") or "").strip().lower()
    if not code:
        return _data_issue_event(
            decision_id, window, as_of_trade_date=as_of,
            reason="decision record missing stock.code",
        )

    try:
        stock_rows = list(price_provider.fetch_window(
            code, start_date=trade_date, end_date=as_of,
        ))
    except PriceProviderUnavailable:
        # Transient outage: do NOT persist a data_issue event; let the
        # orchestrator count this as a skip so the next run with the
        # provider restored can classify the window properly.
        raise
    except Exception as exc:
        return _data_issue_event(
            decision_id, window, as_of_trade_date=as_of,
            reason=f"price provider error: {exc}",
        )

    entry_row = _row_for_date(stock_rows, trade_date)
    close_row = _row_for_date(stock_rows, as_of)
    entry_price = _safe_float((entry_row or {}).get("close"))
    close_price = _safe_float((close_row or {}).get("close"))

    if entry_price is None or close_price is None or entry_price <= 0:
        return _data_issue_event(
            decision_id, window, as_of_trade_date=as_of,
            reason=(
                f"missing prices for {code}: entry={entry_price!r}, "
                f"close={close_price!r}"
            ),
        )

    return_pct = (close_price - entry_price) / entry_price * 100.0

    # Max favorable / adverse excursion measured across every post-entry
    # day's intraday high / low.  The entry row itself contributes 0%
    # implicitly (high == low == close == entry_price by construction
    # in fixtures; production providers should populate intraday H/L).
    post_rows = [
        row for row in stock_rows
        if str(row.get("trade_date") or "") > trade_date
    ]
    mfe_pct: float | None = None
    mae_pct: float | None = None
    for row in post_rows:
        high = _safe_float(row.get("high"))
        low = _safe_float(row.get("low"))
        if high is not None:
            favorable = (high - entry_price) / entry_price * 100.0
            mfe_pct = favorable if mfe_pct is None else max(mfe_pct, favorable)
        if low is not None:
            adverse = (low - entry_price) / entry_price * 100.0
            mae_pct = adverse if mae_pct is None else min(mae_pct, adverse)

    benchmark_return_pct: float | None = None
    relative_return_pct: float | None = None
    benchmark_available = False
    if benchmark_code:
        try:
            bench_rows = list(price_provider.fetch_window(
                benchmark_code, start_date=trade_date, end_date=as_of,
            ))
        except Exception:
            bench_rows = []
        bench_entry = _row_for_date(bench_rows, trade_date)
        bench_close = _row_for_date(bench_rows, as_of)
        b_entry = _safe_float((bench_entry or {}).get("close"))
        b_close = _safe_float((bench_close or {}).get("close"))
        if b_entry is not None and b_close is not None and b_entry > 0:
            benchmark_return_pct = (b_close - b_entry) / b_entry * 100.0
            relative_return_pct = return_pct - benchmark_return_pct
            benchmark_available = True

    classification = classify_outcome(
        action=str((decision.get("recommendation") or {}).get("action") or "").lower(),
        return_pct=return_pct,
        relative_return_pct=relative_return_pct,
        benchmark_available=benchmark_available,
        execution_events=decision.get("execution_events") or [],
        thresholds=thresholds,
    )

    return {
        "window": window,
        "as_of_trade_date": as_of,
        "market_data": {
            "entry_reference_price": round(entry_price, 4),
            "close_price": round(close_price, 4),
            "return_pct": round(return_pct, 4),
            "benchmark_code": benchmark_code if benchmark_available else None,
            "benchmark_return_pct": (
                round(benchmark_return_pct, 4) if benchmark_return_pct is not None else None
            ),
            "relative_return_pct": (
                round(relative_return_pct, 4) if relative_return_pct is not None else None
            ),
            "max_favorable_pct": (
                round(mfe_pct, 4) if mfe_pct is not None else None
            ),
            "max_adverse_pct": (
                round(mae_pct, 4) if mae_pct is not None else None
            ),
        },
        "boundary_checks": {
            "trigger_touched": None,
            "stop_touched": None,
            "continue_condition_held": None,
        },
        "classification": classification,
        "quality": {
            "usable_for_decision_quality": classification["label"] not in {
                "data_issue", "inconclusive",
            },
            "data_issue": None,
        },
    }


# ----------------------------------------------------------- due resolver


def _iter_decisions_files() -> Iterator[Path]:
    root = default_ledger_root() / "decisions"
    if not root.exists():
        return iter(())
    return iter(sorted(root.glob("*.json")))


def find_due_outcomes(
    *,
    as_of_date: str,
    windows: Iterable[str] = ("T+1", "T+3", "T+5"),
) -> Iterator[tuple[dict[str, Any], str]]:
    """Yield ``(decision, window)`` pairs that are ready to be evaluated.

    "Ready" means: the window's ``as_of`` trading day is on or before
    ``as_of_date``, AND no OutcomeEvent for that window already lives on
    the decision.  Decisions whose ``as_of`` cannot be resolved (past
    calendar horizon, bad trade_date) are silently skipped -- they're
    not "due", they're "unknown".
    """

    try:
        as_of_norm = _normalize_trade_date(as_of_date)
    except DecisionLedgerError:
        return iter(())

    window_steps = [(w, _OUTCOME_WINDOW_STEPS[w]) for w in windows if w in _OUTCOME_WINDOW_STEPS]

    def _gen() -> Iterator[tuple[dict[str, Any], str]]:
        for path in _iter_decisions_files():
            for record in _read_decisions_file(path):
                evaluated_windows = {
                    str(ev.get("window") or "")
                    for ev in (record.get("outcome_events") or [])
                }
                trade_date = str(record.get("trade_date") or "")
                if not trade_date:
                    continue
                for window, _steps in window_steps:
                    if window in evaluated_windows:
                        continue
                    as_of = nth_trading_day_after(trade_date, _OUTCOME_WINDOW_STEPS[window])
                    if not as_of:
                        continue
                    if as_of <= as_of_norm:
                        yield record, window

    return _gen()


# ----------------------------------------------------------- orchestrator


def evaluate_due_outcomes(
    *,
    as_of_date: str,
    price_provider: PriceProvider | None,
    benchmark_code: str | None = "000300",
    thresholds: OutcomeThresholds | None = None,
    windows: Iterable[str] = ("T+1", "T+3", "T+5"),
) -> dict[str, Any]:
    """Walk every due outcome, append events idempotently, return a summary.

    When ``price_provider`` is ``None`` the orchestrator counts due
    decisions under ``skipped_no_provider`` and writes nothing -- this
    keeps a "no provider configured" rerun cheap and lets a later run
    with a real provider classify the same decision properly.
    """

    summary: dict[str, Any] = {
        "as_of_date": as_of_date,
        "evaluated": 0,
        "already_present": 0,
        "skipped_no_provider": 0,
        "skipped_provider_unavailable": 0,
        "data_issue": 0,
        "errors": 0,
        "events": [],
    }

    try:
        as_of_norm = _normalize_trade_date(as_of_date)
    except DecisionLedgerError:
        return summary

    window_list = [w for w in windows if w in _OUTCOME_WINDOW_STEPS]

    # Walk decisions directly (rather than via find_due_outcomes) so we
    # can distinguish "due but already evaluated" from "due and newly
    # evaluated".  The append-side de-dup still protects us if a
    # concurrent writer landed an event between our read and our write.
    for path in _iter_decisions_files():
        records = _read_decisions_file(path)
        for record in records:
            decision_id = str(record.get("decision_id") or "")
            trade_date = str(record.get("trade_date") or "")
            if not decision_id or not trade_date:
                continue
            evaluated_windows = {
                str(ev.get("window") or "")
                for ev in (record.get("outcome_events") or [])
            }

            for window in window_list:
                as_of = nth_trading_day_after(trade_date, _OUTCOME_WINDOW_STEPS[window])
                if not as_of or as_of > as_of_norm:
                    continue  # not yet due / unknown

                if window in evaluated_windows:
                    summary["already_present"] += 1
                    continue

                if price_provider is None:
                    summary["skipped_no_provider"] += 1
                    continue

                try:
                    event_payload = evaluate_decision_outcome(
                        record,
                        window=window,
                        price_provider=price_provider,
                        benchmark_code=benchmark_code,
                        thresholds=thresholds,
                    )
                except PriceProviderUnavailable as exc:
                    summary["skipped_provider_unavailable"] += 1
                    summary["events"].append({
                        "decision_id": decision_id,
                        "window": window,
                        "label": "provider_unavailable",
                        "detail": str(exc),
                    })
                    continue
                except Exception as exc:  # pragma: no cover - defensive
                    summary["errors"] += 1
                    summary["events"].append({
                        "decision_id": decision_id,
                        "window": window,
                        "label": "error",
                        "detail": str(exc),
                    })
                    continue

                try:
                    append_outcome_event(decision_id, event_payload)
                except DecisionLedgerError as exc:
                    summary["errors"] += 1
                    summary["events"].append({
                        "decision_id": decision_id,
                        "window": window,
                        "label": "error",
                        "detail": str(exc),
                    })
                    continue

                summary["evaluated"] += 1
                label = event_payload["classification"]["label"]
                if label == "data_issue":
                    summary["data_issue"] += 1
                summary["events"].append({
                    "decision_id": decision_id,
                    "window": window,
                    "label": label,
                })

    return summary


# ============================================================================
# Phase 5 -- read-only query helpers for the API layer.
#
# These functions exist so endpoint code in ``app.py`` does not have to
# reach into ledger internals.  They are deliberately lenient on input
# (a request with a garbage stock code yields an empty result, not an
# exception) but loud on corruption (a malformed JSON file is reported
# in an ``errors`` field rather than silently dropped).
# ============================================================================


def scan_all_decisions() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Walk every decisions-file and report parse errors per file.

    Returns ``(records, errors)``.  ``errors`` is a list of
    ``{"file": str, "error": str}`` entries for files that did not
    parse.  Callers (typically the API layer) decide whether to
    surface them in the response or fail the request.  We use this
    instead of letting :func:`_read_decisions_file` raise the whole
    scan because a single bad file should not blank out a dashboard.
    """

    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    root = default_ledger_root() / "decisions"
    if not root.exists():
        return records, errors
    for path in sorted(root.glob("*.json")):
        try:
            records.extend(_read_decisions_file(path))
        except DecisionLedgerError as exc:
            errors.append({"file": str(path), "error": str(exc)})
    return records, errors


def _latest_execution_event(
    events: Iterable[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    """Pick the most recent ExecutionEvent from a list (by ``created_at``)."""

    events_list = list(events or [])
    if not events_list:
        return None
    return max(
        events_list,
        key=lambda e: str(e.get("created_at") or e.get("trade_date") or ""),
    )


def _latest_outcome_event(
    events: Iterable[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    """Pick the most informative OutcomeEvent (longest closed window).

    T+5 wins over T+3, T+3 wins over T+1.  When windows tie we fall
    back to ``evaluated_at`` so a re-evaluation comes through.  An
    event with an unknown window slot still beats no event at all.
    """

    events_list = list(events or [])
    if not events_list:
        return None
    window_rank = {"T+5": 3, "T+3": 2, "T+1": 1}
    return max(
        events_list,
        key=lambda e: (
            window_rank.get(str(e.get("window") or "").upper(), 0),
            str(e.get("evaluated_at") or ""),
        ),
    )


def _decision_summary_card(record: Mapping[str, Any]) -> dict[str, Any]:
    """Compress a DecisionRecord into the shape ``/recent`` returns.

    Keeps the cards small and predictable so the response stays
    skim-friendly -- the full record is one ``/decision/{id}`` call
    away when the caller needs everything.
    """

    stock = record.get("stock") or {}
    source = record.get("source") or {}
    recommendation = record.get("recommendation") or {}
    status = record.get("status") or {}

    execution_events = list(record.get("execution_events") or [])
    outcome_events = list(record.get("outcome_events") or [])
    latest_execution = _latest_execution_event(execution_events)
    latest_outcome = _latest_outcome_event(outcome_events)

    latest_execution_view: dict[str, Any] | None = None
    if latest_execution is not None:
        latest_execution_view = {
            "status": latest_execution.get("status"),
            "trade_date": latest_execution.get("trade_date"),
            "side": latest_execution.get("side"),
            "price": latest_execution.get("price"),
            "quantity": latest_execution.get("quantity"),
            "amount": latest_execution.get("amount"),
            "note": latest_execution.get("note"),
        }

    latest_outcome_view: dict[str, Any] | None = None
    if latest_outcome is not None:
        classification = latest_outcome.get("classification") or {}
        market_data = latest_outcome.get("market_data") or {}
        latest_outcome_view = {
            "window": latest_outcome.get("window"),
            "as_of_trade_date": latest_outcome.get("as_of_trade_date"),
            "label": classification.get("label"),
            "tone": classification.get("tone"),
            "return_pct": market_data.get("return_pct"),
            "relative_return_pct": market_data.get("relative_return_pct"),
        }

    return {
        "decision_id": record.get("decision_id"),
        "trade_date": record.get("trade_date"),
        "code": stock.get("code"),
        "name": stock.get("name"),
        "action": recommendation.get("action"),
        "action_label": recommendation.get("action_label"),
        "lane": source.get("lane"),
        "surface": source.get("surface"),
        "status": status.get("state"),
        "main_conclusion": recommendation.get("main_conclusion"),
        "execution_events_count": len(execution_events),
        "outcome_events_count": len(outcome_events),
        "latest_execution": latest_execution_view,
        "latest_outcome": latest_outcome_view,
    }


def _resolve_as_of(as_of: str | None) -> str:
    if as_of:
        try:
            return _normalize_trade_date(as_of)
        except DecisionLedgerError:
            pass
    return datetime.now().strftime("%Y-%m-%d")


def summarize_window(
    *,
    window_days: int = 7,
    as_of: str | None = None,
) -> dict[str, Any]:
    """Aggregate decisions over the trailing ``window_days`` window.

    Always returns the same shape -- the empty-ledger case yields
    zeroed counters rather than a sparse dict, so the UI can render
    without conditional branches.  Corrupt files surface under
    ``errors``: the dashboard stays usable, the operator still sees the
    bad path.
    """

    days = max(1, int(window_days) if isinstance(window_days, int) else 7)
    as_of_norm = _resolve_as_of(as_of)
    try:
        end = datetime.strptime(as_of_norm, "%Y-%m-%d").date()
    except ValueError:
        end = datetime.now().date()
        as_of_norm = end.strftime("%Y-%m-%d")
    start = end - timedelta(days=days)
    from_date = start.strftime("%Y-%m-%d")

    records, errors = scan_all_decisions()
    in_window = [
        r for r in records
        if from_date <= str(r.get("trade_date") or "") <= as_of_norm
    ]

    distribution: dict[str, int] = {}
    execution_gap_count = 0
    data_issue_count = 0
    execution_events_total = 0
    outcome_events_total = 0
    open_count = 0
    superseded_count = 0

    for record in in_window:
        state = str((record.get("status") or {}).get("state") or "")
        if state == "superseded":
            superseded_count += 1
        elif state == "open":
            open_count += 1
        execution_events = record.get("execution_events") or []
        outcome_events = record.get("outcome_events") or []
        execution_events_total += len(execution_events)
        outcome_events_total += len(outcome_events)
        for event in outcome_events:
            label = str((event.get("classification") or {}).get("label") or "")
            if not label:
                continue
            distribution[label] = distribution.get(label, 0) + 1
            if label == "execution_gap":
                execution_gap_count += 1
            elif label == "data_issue":
                data_issue_count += 1

    return {
        "as_of": as_of_norm,
        "window_days": days,
        "from_date": from_date,
        "to_date": as_of_norm,
        "decisions": {
            "total": len(in_window),
            "open": open_count,
            "superseded": superseded_count,
        },
        "outcome_distribution": distribution,
        "execution_gap_count": execution_gap_count,
        "data_issue_count": data_issue_count,
        "execution_events_total": execution_events_total,
        "outcome_events_total": outcome_events_total,
        "errors": errors,
    }


def list_recent_decisions(*, limit: int = 20) -> dict[str, Any]:
    """Return the most recent decisions plus their latest event summary.

    Sort order is ``(trade_date desc, decision_id desc)``.  The decision
    id suffix is a deterministic hash, so this is stable across calls
    rather than depending on filesystem ordering.
    """

    if not isinstance(limit, int) or limit < 1:
        limit = 1
    limit = min(limit, 500)  # hard cap so /recent stays a thin API
    records, errors = scan_all_decisions()
    records.sort(
        key=lambda r: (
            str(r.get("trade_date") or ""),
            str(r.get("decision_id") or ""),
        ),
        reverse=True,
    )
    items = [_decision_summary_card(r) for r in records[:limit]]
    return {
        "items": items,
        "count": len(items),
        "limit": limit,
        "errors": errors,
    }


# ----------------------------------------------------------------------------
# Status / health metadata.
#
# The capture and outcome-evaluation tasks need to report what they did
# (last run timestamp, counts, error reason) in a way the Settings UI can
# read without re-running the work.  We persist these summaries in
# ``apps/data/decision_ledger/status/<kind>_latest.json`` -- *outside* of
# ``decisions/`` so they cannot pollute the audit trail.  Status files
# are best-effort metadata; a missing or unparseable status file degrades
# to "no status reported yet" rather than failing the API request.
# ----------------------------------------------------------------------------


def status_path(kind: str) -> Path:
    """Return the on-disk path of the ``kind`` status file.

    The kind is whitelisted (see :data:`STATUS_KINDS`) so a typo at a
    write site cannot stash an unreachable status file in the ledger
    root.  The directory is *not* created here -- writers call
    :func:`write_status`, readers handle missing files.
    """

    key = str(kind or "").strip().lower()
    if key not in STATUS_KINDS:
        raise DecisionLedgerError(
            f"unknown status kind: {kind!r}; expected one of {STATUS_KINDS}"
        )
    return default_ledger_root() / "status" / f"{key}_latest.json"


def write_status(kind: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Persist the latest status payload for ``kind`` atomically.

    The caller decides the shape -- we just merge a ``recorded_at``
    stamp so the UI can show when the status was last updated even when
    the payload itself does not carry timestamps.  ``payload`` must be
    a mapping; everything else raises so a buggy caller is loud rather
    than silently dropping the status update.
    """

    if not isinstance(payload, Mapping):
        raise DecisionLedgerError("status payload must be a mapping")
    target = status_path(kind)
    target.parent.mkdir(parents=True, exist_ok=True)
    body: dict[str, Any] = {**dict(payload), "recorded_at": _now()}
    atomic_write_json(target, body)
    return body


def load_status(kind: str) -> dict[str, Any] | None:
    """Return the stored status for ``kind`` or ``None`` if missing.

    Corrupt files surface as ``None`` *and* a logged error path in
    :func:`build_ledger_health`; this loader stays lenient because the
    health endpoint must keep working even when the status file is
    unreadable -- otherwise a single bad status would blank the entire
    Settings dashboard.
    """

    path = status_path(kind)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, Mapping):
        return None
    return dict(raw)


def build_ledger_health() -> dict[str, Any]:
    """Aggregate Decision Ledger health for the Settings / Health UI.

    Combines:

    * The most recent capture status (counts + result + recorded_at).
    * The most recent outcome-evaluation status (counts + provider mode).
    * Any corrupt decisions files :func:`scan_all_decisions` detected.
    * A coarse pending-outcomes counter so the operator can see whether
      due windows are stacking up without firing the evaluator.

    The shape is stable: every section is present, even when nothing
    has run yet, so the frontend can avoid conditional rendering for
    "never captured" vs "captured once" cases.
    """

    capture = load_status("capture")
    outcome = load_status("outcome")
    records, errors = scan_all_decisions()

    # Pending = decision has at least one window whose as_of trade day
    # is on/before today AND has no outcome event for that window.
    today_str = datetime.now().strftime("%Y-%m-%d")
    pending_outcomes = 0
    evaluated_outcomes = 0
    open_decisions = 0
    superseded_decisions = 0
    for record in records:
        state = str((record.get("status") or {}).get("state") or "")
        if state == "open":
            open_decisions += 1
        elif state == "superseded":
            superseded_decisions += 1
        trade_date = str(record.get("trade_date") or "")
        if not trade_date:
            continue
        evaluated_windows = {
            str(ev.get("window") or "")
            for ev in (record.get("outcome_events") or [])
        }
        evaluated_outcomes += len(evaluated_windows)
        for window in OUTCOME_WINDOWS:
            if window in evaluated_windows:
                continue
            as_of = nth_trading_day_after(trade_date, _OUTCOME_WINDOW_STEPS[window])
            if not as_of:
                continue
            if as_of <= today_str:
                pending_outcomes += 1

    # Surface corrupt status files explicitly -- ``load_status`` already
    # swallowed the parse error so the health endpoint stays alive; if
    # one is present, the operator deserves to know.
    status_errors: list[dict[str, Any]] = []
    for kind in STATUS_KINDS:
        path = status_path(kind)
        if not path.exists():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            status_errors.append({
                "kind": kind,
                "file": str(path),
                "error": str(exc),
            })
            continue
        if not isinstance(raw, Mapping):
            status_errors.append({
                "kind": kind,
                "file": str(path),
                "error": "status payload is not an object",
            })

    return {
        "generated_at": _now(),
        "as_of_trade_date": today_str,
        "decisions_total": len(records),
        "decisions_open": open_decisions,
        "decisions_superseded": superseded_decisions,
        "evaluated_outcomes": evaluated_outcomes,
        "pending_outcomes": pending_outcomes,
        "last_capture": capture,
        "last_outcome_evaluation": outcome,
        "corrupt_files": errors,
        "status_errors": status_errors,
    }


# ----------------------------------------------------------------------------
# Concrete provider re-export.
#
# The import happens at the BOTTOM of the file so that
# ``decision_ledger_providers`` can pull :class:`PriceProviderUnavailable`
# off this module without creating a circular import (this module is
# fully populated by the time the import below runs).
# ----------------------------------------------------------------------------

from decision_ledger_providers import PrismCachePriceProvider  # type: ignore  # noqa: E402
