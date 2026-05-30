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
from prism_storage.paths import RUNTIME_ROOT  # type: ignore

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
    "DECISION_RULESET_VERSION",
    "LEARNING_LOOP_VERSION",
    "DecisionLedgerError",
    "default_ledger_root",
    "legacy_ledger_root",
    "ledger_storage_status",
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
    "build_calibration_review",
    "build_shadow_calibration_summary",
    "build_review_case_workbench",
    "build_attribution_draft",
    "list_review_cases",
    "save_review_case",
    "build_review_case_patterns",
    "read_review_cases_revision",
    "list_recent_decisions",
    "scan_all_decisions",
    "status_path",
    "write_status",
    "load_status",
    "build_ledger_health",
    "build_rule_learning_loop",
]


SCHEMA_VERSION = 1
DECISION_RULESET_VERSION = "prism-decision-rules.v1"
LEARNING_LOOP_VERSION = "decision-learning-loop.v1"

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
WORKSPACE_ROOT = CONTROL_PANEL_ROOT.parents[1]
LEGACY_LEDGER_DIR = INVEST_FLOW_ROOT / "data" / "decision_ledger"
DEFAULT_LEDGER_DIR = RUNTIME_ROOT / "decision_ledger"
SHADOW_REPLAY_ROOT = WORKSPACE_ROOT / "data" / "quant" / "shadow_replay"


class DecisionLedgerError(ValueError):
    """Raised for user-facing validation failures in the ledger layer."""


@dataclass(frozen=True)
class AttributionProviderConfig:
    """Runtime config for an OpenAI-compatible attribution draft provider."""

    provider: str
    api_key: str
    model: str
    base_url: str
    timeout_seconds: float
    configured: bool


PRIMARY_REVIEW_CAUSES = (
    "too_strict",
    "too_loose",
    "signal_distortion",
    "execution_gap",
    "data_unavailable",
    "insufficient_sample",
    "rule_valid_noise",
)
SECONDARY_REVIEW_CAUSES = (
    "volume_too_conservative",
    "capital_flow_filter_strict",
    "market_regime_gate_strict",
    "fundamental_weight_low",
    "open_behavior_misread",
    "risk_condition_not_triggered",
    "followup_event_driven",
    "liquidity_insufficient",
    "data_delay",
)
CONCLUSION_ACTIONS = (
    "keep_rule",
    "loosen_filter",
    "tighten_filter",
    "add_guardrail",
    "wait_more_samples",
    "fix_data_pipeline",
    "fix_execution_pipeline",
)
FOLLOW_UP_STATUSES = (
    "observing",
    "sample_insufficient",
    "preliminary_effective",
    "invalid",
    "adopted",
    "rolled_back",
)
ATTRIBUTION_CONFIDENCE_LEVELS = ("low", "medium", "high")

_DIRECT_RULE_ACTIONS = {"loosen_filter", "tighten_filter", "add_guardrail"}
_FOLLOW_UP_STATUS_LABELS = {
    "observing": "观察中",
    "sample_insufficient": "样本不足",
    "preliminary_effective": "初步有效",
    "invalid": "无效",
    "adopted": "已采纳",
    "rolled_back": "已回滚",
}
_CONCLUSION_ACTION_LABELS = {
    "keep_rule": "保持规则",
    "loosen_filter": "调宽过滤条件",
    "tighten_filter": "收紧过滤条件",
    "add_guardrail": "增加护栏",
    "wait_more_samples": "等更多样本",
    "fix_data_pipeline": "修复数据链路",
    "fix_execution_pipeline": "修复执行链路",
}
_PRIMARY_REVIEW_CAUSE_LABELS = {
    "too_strict": "判断过严",
    "too_loose": "判断过松",
    "signal_distortion": "信号失真",
    "execution_gap": "执行未跟上",
    "data_unavailable": "数据不可用",
    "insufficient_sample": "样本不足，暂不改规则",
    "rule_valid_noise": "规则有效，个例噪音",
}
_SECONDARY_REVIEW_CAUSE_LABELS = {
    "volume_too_conservative": "量能判断偏保守",
    "capital_flow_filter_strict": "主力资金过滤过严",
    "market_regime_gate_strict": "环境阀门过严",
    "fundamental_weight_low": "个股基本面权重不足",
    "open_behavior_misread": "开盘行为误判",
    "risk_condition_not_triggered": "风险条件未发生",
    "followup_event_driven": "后续事件驱动",
    "liquidity_insufficient": "流动性不足",
    "data_delay": "数据延迟",
}
_REVIEW_CASE_STATUS_LABELS = {
    "pending_attribution": "待归因",
    "attributed": "已归因",
    "observing": "观察中",
    "pattern_formed": "已形成模式",
    "rule_suggestion": "已生成规则建议",
    "closed": "已关闭",
}
_SAMPLE_STAGE_LABELS = {
    "observation_hypothesis": "观察假设",
    "validating_pattern": "待验证模式",
    "rule_adjustment_suggestion": "规则调整建议",
    "strategy_calibration_suggestion": "策略级校准建议",
}


# --------------------------------------------------------------------------- paths


def default_ledger_root() -> Path:
    """Resolve the canonical on-disk ledger root.

    Production callers never need to set ``PRISM_DECISION_LEDGER_PATH``;
    tests use it to redirect writes into a temporary directory.  The
    default has moved from ``apps/data/decision_ledger`` to
    ``data/runtime/decision_ledger``; readers still consult the legacy
    root so old audit files stay visible during migration.
    """

    override = os.environ.get("PRISM_DECISION_LEDGER_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    return DEFAULT_LEDGER_DIR


def legacy_ledger_root() -> Path:
    """Return the pre-storage-redesign ledger root."""

    override = os.environ.get("PRISM_DECISION_LEDGER_LEGACY_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    return LEGACY_LEDGER_DIR


def _ledger_read_roots() -> list[Path]:
    roots = [default_ledger_root()]
    if os.environ.get("PRISM_DECISION_LEDGER_PATH") and not os.environ.get("PRISM_DECISION_LEDGER_LEGACY_PATH"):
        return roots
    legacy = legacy_ledger_root()
    if legacy != roots[0]:
        roots.append(legacy)
    return roots


def _decisions_path(trade_date: str) -> Path:
    return default_ledger_root() / "decisions" / f"{_normalize_trade_date(trade_date)}.json"


def _decision_read_paths(trade_date: str) -> list[Path]:
    filename = f"{_normalize_trade_date(trade_date)}.json"
    return [root / "decisions" / filename for root in _ledger_read_roots()]


def _review_cases_path() -> Path:
    return default_ledger_root() / "review_cases.json"


def _review_case_read_paths() -> list[Path]:
    return [root / "review_cases.json" for root in _ledger_read_roots()]


def ledger_storage_status() -> dict[str, Any]:
    """Expose the ledger storage migration state to health surfaces."""

    primary = default_ledger_root()
    legacy = legacy_ledger_root()
    primary_decisions = primary / "decisions"
    legacy_decisions = legacy / "decisions"
    primary_count = len(list(primary_decisions.glob("*.json"))) if primary_decisions.exists() else 0
    legacy_count = len(list(legacy_decisions.glob("*.json"))) if legacy_decisions.exists() else 0
    return {
        "mode": "runtime_primary_legacy_read",
        "primary_root": str(primary),
        "legacy_root": str(legacy),
        "primary_exists": primary.exists(),
        "legacy_exists": legacy.exists(),
        "primary_decision_files": primary_count,
        "legacy_decision_files": legacy_count,
        "writes_to": str(primary),
        "reads_from": [str(root) for root in _ledger_read_roots()],
    }


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
    factor_snapshot: Mapping[str, Any] | None = None,
    decision_contract: Mapping[str, Any] | None = None,
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
        "factor_snapshot": dict(factor_snapshot) if factor_snapshot else None,
        "decision_contract": dict(decision_contract) if decision_contract else None,
        "rule_snapshot": {
            "ruleset_version": DECISION_RULESET_VERSION,
            "learning_loop_version": LEARNING_LOOP_VERSION,
            "contract_schema_version": str((decision_contract or {}).get("schema_version") or ""),
            "outcome_windows": list(OUTCOME_WINDOWS),
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
    """Return all DecisionRecords for ``trade_date`` (empty when missing).

    During the storage migration, the canonical runtime root wins over the
    legacy ``apps/data`` root when both contain the same ``decision_id``.
    A write to the canonical root will naturally backfill the merged file.
    """

    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in _decision_read_paths(trade_date):
        if not path.exists():
            continue
        for record in _read_decisions_file(path):
            decision_id = str(record.get("decision_id") or "")
            if decision_id and decision_id in seen:
                continue
            if decision_id:
                seen.add(decision_id)
            records.append(record)
    return records


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
    out: list[dict[str, Any]] = []
    records, _errors = scan_all_decisions()
    for record in records:
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
    records = load_decisions(trade_date)
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
    records = load_decisions(trade_date)
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
    factor_snapshot: Mapping[str, Any] | None = None,
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
        factor_snapshot=factor_snapshot,
        decision_contract=item.get("decision_contract") if isinstance(item.get("decision_contract"), Mapping) else None,
    )


def _factor_snapshot_for_item(item: Mapping[str, Any], data_trade_date: str) -> dict[str, Any] | None:
    """Best-effort factor snapshot for a today-action item.

    Research-only: never fatal, never feeds an execution/readiness gate.
    Returns ``None`` on any failure (missing factor module, unparsable
    key, bad data) so capture continues unaffected.
    """

    try:
        from screener.tushare_factors import build_factor_snapshot

        _, plain_code = _parse_today_action_key(str(item.get("key") or ""))
        if not plain_code:
            return None
        return build_factor_snapshot(plain_code, data_trade_date)
    except Exception:
        return None


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
                factor_snapshot=_factor_snapshot_for_item(item, data_trade_date),
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
    seen: set[str] = set()
    for root in _ledger_read_roots():
        decisions_root = root / "decisions"
        if not decisions_root.exists():
            continue
        for path in sorted(decisions_root.glob("*.json")):
            try:
                for record in _read_decisions_file(path):
                    decision_id = str(record.get("decision_id") or "")
                    if decision_id and decision_id in seen:
                        continue
                    if decision_id:
                        seen.add(decision_id)
                    records.append(record)
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
    rule_snapshot = record.get("rule_snapshot") or {}

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
        "ruleset_version": rule_snapshot.get("ruleset_version") or "legacy_unversioned",
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


_LEARNING_REVIEW_LABELS = {
    "invalidated",
    "missed_opportunity",
    "execution_gap",
    "data_issue",
}


def _factor_returns(records, predicate):
    by_window: dict[str, list[float]] = {}
    mature = 0
    for rec in records:
        snap = ((rec.get("factor_snapshot") or {}).get("factor_snapshot")) or {}
        if not predicate(snap):
            continue
        outcomes = [o for o in (rec.get("outcome_events") or []) if isinstance(o, Mapping)]
        if not outcomes:
            continue
        mature += 1
        for o in outcomes:
            window = o.get("window")
            ret = (o.get("market_data") or {}).get("relative_return_pct")
            if window and isinstance(ret, (int, float)):
                by_window.setdefault(window, []).append(float(ret))
    avg = {w: round(sum(v) / len(v), 3) for w, v in by_window.items()}
    win = {w: round(sum(1 for x in v if x > 0) / len(v), 3) for w, v in by_window.items()}
    return {"mature_count": mature, "sample_count": mature,
            "avg_return_by_window": avg, "win_rate_by_window": win}


def build_factor_learning_loop(records) -> dict[str, Any]:
    """Per-factor forward-return bucketing (research-only learning statistic).

    Buckets matured decision records by a handful of factor dimensions
    captured in ``factor_snapshot`` and reports average / win-rate of the
    relative forward return per outcome window.  This never feeds an
    execution or readiness gate; it is a read-only feedback view.
    """

    def roe(snap): return (snap.get("fundamentals") or {}).get("roe")
    def pb(snap): return (snap.get("valuation") or {}).get("pb")
    def inst(snap): return (snap.get("top_inst_activity") or {}).get("net_buy")
    def north(snap): return (snap.get("market_context") or {}).get("north_money")
    def member(snap): return bool(snap.get("index_membership"))
    return {
        "learning_loop_version": LEARNING_LOOP_VERSION,
        "outcome_windows": list(OUTCOME_WINDOWS),
        "buckets": {
            "roe": {
                "high": _factor_returns(records, lambda s: isinstance(roe(s), (int, float)) and roe(s) >= 12),
                "low": _factor_returns(records, lambda s: isinstance(roe(s), (int, float)) and roe(s) < 12),
                "label": "高ROE(≥12%) vs 低ROE",
            },
            "pb": {
                "low": _factor_returns(records, lambda s: isinstance(pb(s), (int, float)) and pb(s) <= 2),
                "high": _factor_returns(records, lambda s: isinstance(pb(s), (int, float)) and pb(s) > 2),
                "label": "低PB(≤2) vs 高PB",
            },
            "dragon_tiger_inst_net_buy": {
                "yes": _factor_returns(records, lambda s: isinstance(inst(s), (int, float)) and inst(s) > 0),
                "no": _factor_returns(records, lambda s: not (isinstance(inst(s), (int, float)) and inst(s) > 0)),
                "label": "龙虎榜机构净买 vs 否",
            },
            "northbound": {
                "strong": _factor_returns(records, lambda s: isinstance(north(s), (int, float)) and north(s) > 0),
                "weak": _factor_returns(records, lambda s: isinstance(north(s), (int, float)) and north(s) <= 0),
                "label": "北向偏强 vs 偏弱",
            },
            "index_membership": {
                "member": _factor_returns(records, member),
                "non_member": _factor_returns(records, lambda s: not member(s)),
                "label": "指数成分 vs 非成分",
            },
        },
    }


def build_rule_learning_loop(
    records: Iterable[Mapping[str, Any]] | None = None,
    *,
    errors: Iterable[Mapping[str, Any]] | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    """Aggregate outcome feedback by explicit decision-rule version.

    This is deliberately not an optimizer.  It is the small closed loop the
    operator needs before changing rules: every sample is tied to the
    ruleset that produced it, then bucketed by lane/action/outcome so rule
    changes can be reviewed with versioned evidence instead of anecdotes.
    """

    if records is None:
        loaded, loaded_errors = scan_all_decisions()
        records = loaded
        errors = loaded_errors if errors is None else errors

    buckets: dict[tuple[str, str, str], dict[str, Any]] = {}
    suggestions: list[dict[str, Any]] = []
    pending_review_count = 0
    samples_total = 0
    mature_samples = 0
    ruleset_versions: set[str] = set()

    for record in records:
        if not isinstance(record, Mapping):
            continue
        samples_total += 1
        rule_snapshot = record.get("rule_snapshot") or {}
        ruleset_version = str(rule_snapshot.get("ruleset_version") or "legacy_unversioned")
        ruleset_versions.add(ruleset_version)
        source = record.get("source") or {}
        recommendation = record.get("recommendation") or {}
        lane = str(source.get("lane") or "unknown")
        action = str(recommendation.get("action") or "unknown")
        key = (ruleset_version, lane, action)
        bucket = buckets.setdefault(
            key,
            {
                "ruleset_version": ruleset_version,
                "lane": lane,
                "action": action,
                "samples": 0,
                "mature_samples": 0,
                "outcomes": {},
                "execution_events": 0,
                "pending_outcome": 0,
                "needs_review": 0,
                "decision_ids": [],
            },
        )
        bucket["samples"] += 1
        bucket["execution_events"] += len(record.get("execution_events") or [])
        decision_id = str(record.get("decision_id") or "")
        if decision_id:
            bucket["decision_ids"].append(decision_id)

        latest_outcome = _latest_outcome_event(record.get("outcome_events") or [])
        if latest_outcome is None:
            bucket["pending_outcome"] += 1
            continue
        mature_samples += 1
        bucket["mature_samples"] += 1
        label = str((latest_outcome.get("classification") or {}).get("label") or "unknown")
        outcomes = bucket["outcomes"]
        outcomes[label] = int(outcomes.get(label) or 0) + 1
        if label in _LEARNING_REVIEW_LABELS:
            bucket["needs_review"] += 1
            pending_review_count += 1

    for bucket in buckets.values():
        mature = int(bucket.get("mature_samples") or 0)
        needs_review = int(bucket.get("needs_review") or 0)
        outcomes = bucket.get("outcomes") or {}
        review_rate = (needs_review / mature) if mature else 0.0
        suggested_action = ""
        reason = ""
        if int(outcomes.get("data_issue") or 0) >= 2:
            suggested_action = "fix_data_pipeline"
            reason = "同一规则桶反复出现数据问题，先修数据再评价规则。"
        elif int(outcomes.get("execution_gap") or 0) >= 2:
            suggested_action = "fix_execution_pipeline"
            reason = "同一规则桶反复出现执行落差，先检查动作到成交的链路。"
        elif mature >= 3 and review_rate >= 0.4:
            suggested_action = "review_rule_threshold"
            reason = "成熟样本里需要复盘的比例偏高，建议检查该 lane/action 的阈值。"

        bucket["review_rate"] = round(review_rate, 4)
        bucket["sample_stage"] = _learning_sample_stage(mature)
        if suggested_action:
            suggestions.append({
                "ruleset_version": bucket["ruleset_version"],
                "lane": bucket["lane"],
                "action": bucket["action"],
                "suggested_action": suggested_action,
                "reason": reason,
                "mature_samples": mature,
                "needs_review": needs_review,
                "review_rate": bucket["review_rate"],
            })

    ordered_buckets = sorted(
        buckets.values(),
        key=lambda item: (
            str(item.get("ruleset_version") or ""),
            str(item.get("lane") or ""),
            str(item.get("action") or ""),
        ),
    )
    for bucket in ordered_buckets:
        bucket["decision_ids"] = list(bucket.get("decision_ids") or [])[:12]

    return {
        "version": LEARNING_LOOP_VERSION,
        "generated_at": _now(),
        "as_of": _resolve_as_of(as_of),
        "ruleset_versions": sorted(ruleset_versions),
        "samples_total": samples_total,
        "mature_samples": mature_samples,
        "pending_review_count": pending_review_count,
        "buckets": ordered_buckets,
        "suggestions": suggestions,
        "errors": [dict(error) for error in (errors or [])],
    }


def _learning_sample_stage(mature_samples: int) -> str:
    if mature_samples >= 10:
        return "pattern_formed"
    if mature_samples >= 3:
        return "validating_pattern"
    if mature_samples > 0:
        return "observation_hypothesis"
    return "pending_outcome"


_REVIEW_LABELS = {
    "invalidated",
    "data_issue",
    "execution_gap",
    "missed_opportunity",
}
_REVIEW_STATUS_STATES = {"superseded"}
_REVIEW_REASON_PRIORITY = {
    "invalidated": 0,
    "execution_gap": 1,
    "missed_opportunity": 2,
    "data_issue": 3,
    "superseded": 4,
}
_REVIEW_REASON_LABELS = {
    "invalidated": "判断失效",
    "execution_gap": "执行落差",
    "missed_opportunity": "错过机会",
    "data_issue": "数据问题",
    "superseded": "判断被替代",
}
_READY_REVIEW_STATUSES = {"ready_review", "blocked_data"}
_PENDING_REVIEW_STATUSES = {"pending_outcome", "pending_execution"}
_EXECUTION_REQUIRED_ACTIONS = {"trial_buy", "reduce"}
_PRIORITY_LABELS = (
    (75, "critical"),
    (55, "high"),
    (35, "medium"),
)
_CALIBRATION_ACTION_LABELS = {
    "keep_rule": "保留规则",
    "tighten_rule": "收紧规则",
    "loosen_rule": "放宽规则",
    "add_guardrail": "增加护栏",
    "wait_for_sample": "等待样本",
    "run_outcome_evaluator": "补跑结果评估",
    "fix_execution": "修复执行",
    "fix_data": "修复数据",
    "investigate_pattern": "排查模式",
}


def _empty_group(label: str) -> dict[str, Any]:
    return {
        "key": label or "unknown",
        "label": label or "unknown",
        "total": 0,
        "evaluated": 0,
        "validated": 0,
        "invalidated": 0,
        "data_issue": 0,
        "execution_gap": 0,
        "missed_opportunity": 0,
        "superseded": 0,
        "pending": 0,
        "review_needed": 0,
    }


def _bump_group(
    group: dict[str, Any],
    *,
    latest_label: str | None,
    has_outcome: bool,
    status_state: str | None = None,
) -> None:
    group["total"] += 1
    if status_state in _REVIEW_STATUS_STATES:
        group["superseded"] += 1
    if latest_label in _REVIEW_LABELS or status_state in _REVIEW_STATUS_STATES:
        group["review_needed"] += 1
    if has_outcome:
        group["evaluated"] += 1
    else:
        group["pending"] += 1
        return
    if latest_label in {"validated", "avoided_loss"}:
        group["validated"] += 1
    elif latest_label == "invalidated":
        group["invalidated"] += 1
    elif latest_label == "data_issue":
        group["data_issue"] += 1
    elif latest_label == "execution_gap":
        group["execution_gap"] += 1
    elif latest_label == "missed_opportunity":
        group["missed_opportunity"] += 1


def _group_rates(group: Mapping[str, Any]) -> dict[str, Any]:
    total = int(group.get("total") or 0)
    evaluated = int(group.get("evaluated") or 0)
    review_needed = int(group.get("review_needed") or 0)
    validated = int(group.get("validated") or 0)
    invalidated = int(group.get("invalidated") or 0)
    data_issue = int(group.get("data_issue") or 0)
    return {
        **dict(group),
        "validated_rate": round(validated / evaluated * 100, 1) if evaluated else 0.0,
        "invalidated_rate": round(invalidated / evaluated * 100, 1) if evaluated else 0.0,
        "data_issue_rate": round(data_issue / total * 100, 1) if total else 0.0,
        "review_rate": round(review_needed / total * 100, 1) if total else 0.0,
    }


def _review_reason(record: Mapping[str, Any], latest_label: str | None) -> tuple[str, str]:
    if latest_label == "invalidated":
        return "invalidated", "判断被后续行情否定"
    if latest_label == "data_issue":
        return "data_issue", "数据缺口使结果不可评价"
    if latest_label == "execution_gap":
        return "execution_gap", "建议有效但执行没有跟上"
    if latest_label == "missed_opportunity":
        return "missed_opportunity", "谨慎动作后出现明显机会"
    if str((record.get("status") or {}).get("state") or "") == "superseded":
        return "superseded", "同源判断被后续建议替代"
    return "attention", "需要人工复盘"


def _axis(label: str, score: int, tone: str, reason: str) -> dict[str, Any]:
    return {
        "label": label,
        "score": max(0, min(int(score), 100)),
        "tone": tone,
        "reason": reason,
    }


def _evidence_strength(sample_size: int) -> str:
    if sample_size >= 10:
        return "high"
    if sample_size >= 5:
        return "medium"
    if sample_size >= 2:
        return "low"
    return "anecdotal"


def _priority_label(score: int) -> str:
    for threshold, label in _PRIORITY_LABELS:
        if score >= threshold:
            return label
    return "low"


def _action_requires_execution(action: str | None) -> bool:
    return str(action or "").strip().lower() in _EXECUTION_REQUIRED_ACTIONS


def _latest_outcome_label(latest_outcome: Mapping[str, Any] | None) -> str:
    if not latest_outcome:
        return ""
    return str((latest_outcome.get("classification") or {}).get("label") or "")


def _latest_outcome_tone(latest_outcome: Mapping[str, Any] | None) -> str:
    if not latest_outcome:
        return "watch"
    return str((latest_outcome.get("classification") or {}).get("tone") or "watch")


def _read_review_cases_file() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in _review_case_read_paths():
        if not path.exists():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DecisionLedgerError(
                f"corrupt review case file {path}: {exc.msg}"
            ) from exc
        if not isinstance(raw, list):
            raise DecisionLedgerError(
                f"corrupt review case file {path}: expected list payload"
            )
        for index, item in enumerate(raw):
            if not isinstance(item, Mapping):
                raise DecisionLedgerError(
                    f"corrupt review case file {path}: record at index {index} "
                    f"is not an object (got {type(item).__name__})"
                )
            review_case_id = str(item.get("review_case_id") or item.get("decision_id") or "")
            if review_case_id and review_case_id in seen:
                continue
            if review_case_id:
                seen.add(review_case_id)
            cases.append(dict(item))
    return cases


def _write_review_cases_file(cases: list[dict[str, Any]]) -> None:
    cases.sort(
        key=lambda item: (
            str(item.get("reviewed_at") or ""),
            str(item.get("review_case_id") or ""),
        ),
        reverse=True,
    )
    atomic_write_json(_review_cases_path(), cases)


_EMPTY_REVIEW_CASES_REVISION = "sha256:empty"


def _compute_review_cases_revision(cases: Iterable[Mapping[str, Any]]) -> str:
    """Content-based revision for the saved review cases.

    The revision is a sha256 over the canonical JSON encoding of the
    cases list. It is stable across processes, independent of file
    mtime, and changes only when the persisted content changes.

    Callers that need to invalidate caches without paying the full
    ``list_review_cases`` decoration cost should prefer
    :func:`read_review_cases_revision` — it hashes the same bytes that
    were written to disk.
    """
    materialized: list[Mapping[str, Any]] = [
        dict(case) for case in cases if isinstance(case, Mapping)
    ]
    if not materialized:
        return _EMPTY_REVIEW_CASES_REVISION
    blob = json.dumps(
        materialized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def read_review_cases_revision() -> str:
    """Cheap content-based revision for the on-disk review case file.

    Reads + parses the file, then canonical-hashes the case list — that
    keeps the revision identical to the one returned by
    :func:`list_review_cases`, so callers can compare them across calls
    without going through the full ``_case_labelled`` projection.

    Returns the empty-revision sentinel when the file is missing,
    unreadable, or empty.
    """
    raw = b""
    for path in _review_case_read_paths():
        try:
            raw = path.read_bytes()
            break
        except FileNotFoundError:
            continue
        except OSError:
            # Mirror the silent-empty behaviour for missing files; a transient
            # permission error should not poison a cache key.
            return _EMPTY_REVIEW_CASES_REVISION
    if not raw:
        return _EMPTY_REVIEW_CASES_REVISION
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        # A corrupt file is loud through :func:`list_review_cases`; here
        # we just return a sentinel so the cache treats it as "unknown"
        # and forces a refresh on the next real call.
        return "sha256:invalid"
    if not isinstance(decoded, list):
        return "sha256:invalid"
    return _compute_review_cases_revision(decoded)


def _review_case_id(decision_id: str) -> str:
    digest = hashlib.sha256(str(decision_id).encode("utf-8")).hexdigest()[:12]
    return f"review_case:{digest}"


def _normalize_review_choice(value: Any, allowed: Iterable[str], field: str) -> str:
    text = str(value or "").strip()
    allowed_set = set(allowed)
    if text not in allowed_set:
        raise DecisionLedgerError(
            f"invalid {field}: {value!r}; expected one of {sorted(allowed_set)}"
        )
    return text


def _normalize_secondary_causes(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise DecisionLedgerError("secondary_causes must be a list")
    out: list[str] = []
    for raw in value:
        text = str(raw or "").strip()
        if not text:
            continue
        if text not in SECONDARY_REVIEW_CAUSES:
            raise DecisionLedgerError(
                f"invalid secondary_causes item: {raw!r}; expected one of "
                f"{list(SECONDARY_REVIEW_CAUSES)}"
            )
        if text not in out:
            out.append(text)
    return out


def _sample_stage(sample_count: int) -> str:
    count = max(0, int(sample_count or 0))
    if count >= 10:
        return "strategy_calibration_suggestion"
    if count >= 5:
        return "rule_adjustment_suggestion"
    if count >= 2:
        return "validating_pattern"
    return "observation_hypothesis"


def _sample_stage_detail(sample_count: int) -> str:
    count = max(0, int(sample_count or 0))
    if count >= 10:
        return "10 条及以上，可进入策略级校准建议；仍需后续验证状态闭环。"
    if count >= 5:
        return "5-9 条同类样本，可形成规则调整建议，但必须保留验证状态。"
    if count >= 2:
        return "2-4 条同类样本，只能视为待验证模式，继续收集后续样本。"
    return "1 条样本只能形成观察假设，不能直接修改交易规则。"


def _short_text(value: Any, *, fallback: str = "", limit: int = 160) -> str:
    if value is None:
        return fallback
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except TypeError:
            text = str(value)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 1)]}…"


def _dominant_value(values: Iterable[Any], *, fallback: str = "") -> str:
    counts: dict[str, int] = {}
    for value in values:
        text = _short_text(value, fallback="", limit=120)
        if not text:
            continue
        counts[text] = counts.get(text, 0) + 1
    if not counts:
        return fallback
    return max(counts, key=lambda item: (counts[item], item))


def _clean_json_list(value: Any, *, limit: int = 12) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        return []
    out: list[Any] = []
    for item in value[: max(0, limit)]:
        if isinstance(item, (str, int, float, bool)) or item is None:
            out.append(item)
        elif isinstance(item, Mapping):
            out.append({
                str(key): val
                for key, val in item.items()
                if isinstance(val, (str, int, float, bool)) or val is None
            })
        else:
            out.append(_short_text(item, limit=240))
    return out


def _clean_string_list(value: Any, *, limit: int = 12) -> list[str]:
    out: list[str] = []
    for item in _clean_json_list(value, limit=limit):
        text = _short_text(item, limit=260)
        if text:
            out.append(text)
    return out


def _choice_or_default(value: Any, allowed: Iterable[str], default: str) -> str:
    text = str(value or "").strip()
    return text if text in set(allowed) else default


def _confidence_or_default(value: Any, default: str = "medium") -> str:
    return _choice_or_default(value, ATTRIBUTION_CONFIDENCE_LEVELS, default)


def _secondary_causes_or_default(value: Any, default: Any = None) -> list[str]:
    try:
        return _normalize_secondary_causes(value)
    except DecisionLedgerError:
        return _normalize_secondary_causes(default or [])


def _format_return_pct(value: Any) -> str:
    try:
        return f"{float(value):+.2f}%"
    except (TypeError, ValueError):
        return "-"


_SHADOW_BUCKET_LABELS = {
    "top_observe": "重点观察",
    "near_miss": "接近入池",
    "risk_reject": "风险剔除",
}
_SHADOW_SETUP_LABELS = {
    "trend_follow": "趋势延续",
    "pullback_support": "回踩支撑",
    "volume_rebound": "放量反弹",
    "mixed_observation": "混合观察",
    "overheated_reject": "过热剔除",
}
_SHADOW_CLASSIFICATION_LABELS = {
    "validated": "验证有效",
    "invalidated": "判断失效",
    "inconclusive": "未定",
    "avoided_loss": "避开亏损",
    "missed_opportunity": "错过机会",
}
_SHADOW_ACTION_LABELS = {
    "observe": "观察",
    "skip": "跳过",
}


def _load_shadow_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return dict(payload) if isinstance(payload, Mapping) else None


def _latest_shadow_signal_manifest() -> Path | None:
    try:
        manifests = sorted(
            SHADOW_REPLAY_ROOT.glob("*/shadow_signal_manifest.json"),
            key=lambda path: (path.parent.name, path.stat().st_mtime if path.exists() else 0),
            reverse=True,
        )
    except Exception:
        return None
    return manifests[0] if manifests else None


def _shadow_output_path(value: Any, *, base: Path) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    candidate = Path(text).expanduser()
    if candidate.is_absolute():
        return candidate
    workspace_candidate = WORKSPACE_ROOT / candidate
    if workspace_candidate.exists():
        return workspace_candidate
    return base / candidate


def _shadow_empty_stats() -> dict[str, Any]:
    return {
        "total": 0,
        "return_sum_pct": 0.0,
        "classifications": {},
    }


def _shadow_bump(stats: dict[str, Any], row: Mapping[str, Any]) -> None:
    stats["total"] = int(stats.get("total") or 0) + 1
    try:
        stats["return_sum_pct"] = float(stats.get("return_sum_pct") or 0.0) + float(row.get("raw_return") or 0.0) * 100
    except (TypeError, ValueError):
        pass
    classifications = stats.setdefault("classifications", {})
    classification = str(row.get("classification") or "unknown")
    classifications[classification] = int(classifications.get(classification) or 0) + 1


def _shadow_rate(count: int, total: int) -> float:
    return round(count / total * 100, 1) if total else 0.0


def _shadow_axis_label(axis: str, key: str) -> str:
    if axis == "bucket":
        return _SHADOW_BUCKET_LABELS.get(key, key)
    if axis == "setup_type":
        return _SHADOW_SETUP_LABELS.get(key, key)
    if axis == "action":
        return _SHADOW_ACTION_LABELS.get(key, key)
    if axis == "window":
        return key
    return key


def _shadow_stats_row(axis: str, key: str, stats: Mapping[str, Any], *, window: str | None = None) -> dict[str, Any]:
    total = int(stats.get("total") or 0)
    classifications = stats.get("classifications") if isinstance(stats.get("classifications"), Mapping) else {}
    validated = int(classifications.get("validated") or 0)
    invalidated = int(classifications.get("invalidated") or 0)
    inconclusive = int(classifications.get("inconclusive") or 0)
    avoided_loss = int(classifications.get("avoided_loss") or 0)
    missed_opportunity = int(classifications.get("missed_opportunity") or 0)
    return {
        "axis": axis,
        "key": key,
        "label": _shadow_axis_label(axis, key),
        "window": window,
        "total": total,
        "validated": validated,
        "invalidated": invalidated,
        "inconclusive": inconclusive,
        "avoided_loss": avoided_loss,
        "missed_opportunity": missed_opportunity,
        "validated_rate": _shadow_rate(validated, total),
        "invalidated_rate": _shadow_rate(invalidated, total),
        "avoided_loss_rate": _shadow_rate(avoided_loss, total),
        "missed_opportunity_rate": _shadow_rate(missed_opportunity, total),
        "avg_return_pct": round(float(stats.get("return_sum_pct") or 0.0) / total, 2) if total else 0.0,
    }


def _shadow_card(
    *,
    kind: str,
    tone: str,
    title: str,
    summary: str,
    action_reason: str,
    sample_size: int,
    calibration_action: str = "investigate_pattern",
) -> dict[str, Any]:
    return {
        "kind": kind,
        "tone": tone,
        "title": title,
        "summary": summary,
        "calibration_action": calibration_action,
        "action_label": _CALIBRATION_ACTION_LABELS.get(calibration_action, calibration_action),
        "action_reason": action_reason,
        "evidence_strength": _evidence_strength(sample_size),
        "sample_size": sample_size,
        "insufficient_sample": False,
        "shadow_only": True,
        "sample_origin": "historical_shadow",
        "source_lane": "shadow_price_signal_baseline",
    }


def _shadow_ref_text(row: Mapping[str, Any]) -> str:
    label = row.get("label") or row.get("key") or "影子样本"
    window = row.get("window") or "T+5"
    total = int(row.get("total") or 0)
    parts = [
        f"{window} {label}",
        f"样本 {total}",
        f"验证 {row.get('validated_rate', 0)}%",
        f"失效 {row.get('invalidated_rate', 0)}%",
    ]
    if int(row.get("avoided_loss") or 0) or int(row.get("missed_opportunity") or 0):
        parts.extend([
            f"避亏 {row.get('avoided_loss_rate', 0)}%",
            f"错过 {row.get('missed_opportunity_rate', 0)}%",
        ])
    parts.append(f"均值 {_format_return_pct(row.get('avg_return_pct'))}")
    return "，".join(parts)


def build_shadow_calibration_summary() -> dict[str, Any]:
    """Research-only calibration hints from generated historical shadow samples.

    The returned data is deliberately separated from Decision Ledger
    review-case counts.  It can guide questions, but cannot increase
    sample_count or unlock automatic rule changes.
    """

    manifest_path = _latest_shadow_signal_manifest()
    if not manifest_path:
        return {
            "status": "missing",
            "title": "历史影子样本未生成",
            "summary": "暂无 shadow replay 统计；真实 Review Case 仍按 Decision Ledger 样本判断。",
            "warning": "研究样本缺失不会影响真实归因队列。",
            "cards": [],
            "bucket_rows": [],
            "setup_rows": [],
            "window_rows": [],
            "action_rows": [],
        }

    manifest = _load_shadow_json(manifest_path) or {}
    summary = manifest.get("summary") if isinstance(manifest.get("summary"), Mapping) else {}
    args = manifest.get("args") if isinstance(manifest.get("args"), Mapping) else {}
    outputs = manifest.get("outputs") if isinstance(manifest.get("outputs"), Mapping) else {}
    labels_path = _shadow_output_path(outputs.get("labels"), base=manifest_path.parent)
    if not labels_path or not labels_path.exists():
        return {
            "status": "partial",
            "title": "历史影子样本缺 outcome",
            "summary": "已找到 shadow manifest，但缺少 forward labels。",
            "warning": "这组数据暂不能用于校准提示。",
            "cards": [],
            "bucket_rows": [],
            "setup_rows": [],
            "window_rows": [],
            "action_rows": [],
        }

    axis_stats: dict[str, dict[str, dict[str, Any]]] = {
        "bucket": {},
        "setup_type": {},
        "action": {},
        "window": {},
    }
    t5_stats: dict[str, dict[str, dict[str, Any]]] = {
        "bucket": {},
        "setup_type": {},
        "action": {},
    }
    label_rows = 0
    available_rows = 0
    try:
        with labels_path.open(encoding="utf-8") as handle:
            for raw in handle:
                raw = raw.strip()
                if not raw:
                    continue
                label_rows += 1
                try:
                    row = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, Mapping) or row.get("label_status") != "available_research_only":
                    continue
                available_rows += 1
                window = str(row.get("window") or "unknown")
                for axis in axis_stats:
                    key = str(row.get(axis) or "unknown")
                    stats = axis_stats[axis].setdefault(key, _shadow_empty_stats())
                    _shadow_bump(stats, row)
                if window == "T+5":
                    for axis in t5_stats:
                        key = str(row.get(axis) or "unknown")
                        stats = t5_stats[axis].setdefault(key, _shadow_empty_stats())
                        _shadow_bump(stats, row)
    except Exception as exc:
        return {
            "status": "partial",
            "title": "历史影子样本读取失败",
            "summary": f"forward labels 无法读取：{exc}",
            "warning": "这组数据暂不能用于校准提示。",
            "cards": [],
            "bucket_rows": [],
            "setup_rows": [],
            "window_rows": [],
            "action_rows": [],
        }

    def rows_for(axis: str, *, t5: bool = True) -> list[dict[str, Any]]:
        source = t5_stats.get(axis, {}) if t5 else axis_stats.get(axis, {})
        rows = [_shadow_stats_row(axis, key, stats, window="T+5" if t5 else None) for key, stats in source.items()]
        rows.sort(key=lambda item: (int(item.get("total") or 0), str(item.get("key") or "")), reverse=True)
        return rows

    bucket_rows = rows_for("bucket", t5=True)
    setup_rows = rows_for("setup_type", t5=True)
    action_rows = rows_for("action", t5=True)
    window_rows = rows_for("window", t5=False)
    bucket_by_key = {str(row.get("key") or ""): row for row in bucket_rows}
    top = bucket_by_key.get("top_observe", {})
    near = bucket_by_key.get("near_miss", {})
    reject = bucket_by_key.get("risk_reject", {})

    cards: list[dict[str, Any]] = []
    if top:
        invalidated_rate = float(top.get("invalidated_rate") or 0.0)
        validated_rate = float(top.get("validated_rate") or 0.0)
        tone = "warning" if invalidated_rate >= validated_rate else "info"
        cards.append(
            _shadow_card(
                kind="shadow_top_observe",
                tone=tone,
                title="Top 观察不是自动买点",
                summary=(
                    f"T+5 重点观察 {top['total']} 条，验证 {validated_rate}%、"
                    f"失效 {invalidated_rate}%、中性 {top.get('inconclusive', 0)} 条。"
                ),
                action_reason="影子样本提示 Top 观察仍需要承接确认，不能只凭入池分数升级。",
                sample_size=int(top.get("total") or 0),
            )
        )
    if near:
        cards.append(
            _shadow_card(
                kind="shadow_near_miss",
                tone="watch" if float(near.get("validated_rate") or 0.0) < 30 else "warning",
                title="接近入池样本有漏掉机会",
                summary=(
                    f"T+5 接近入池 {near['total']} 条，验证 {near.get('validated_rate', 0)}%、"
                    f"失效 {near.get('invalidated_rate', 0)}%。"
                ),
                action_reason="若真实复盘也集中出现 missed_opportunity，再检查过滤条件是否过严。",
                sample_size=int(near.get("total") or 0),
            )
        )
    if reject:
        avoided = float(reject.get("avoided_loss_rate") or 0.0)
        missed = float(reject.get("missed_opportunity_rate") or 0.0)
        tone = "positive" if avoided > missed else "warning"
        cards.append(
            _shadow_card(
                kind="shadow_risk_reject",
                tone=tone,
                title="风险剔除有效但不干净",
                summary=(
                    f"T+5 风险剔除 {reject['total']} 条，避开亏损 {avoided}%、"
                    f"错过机会 {missed}%。"
                ),
                action_reason="风险剔除有价值，但错过机会比例不低，真实归因时要确认风险条件是否真的发生。",
                sample_size=int(reject.get("total") or 0),
            )
        )
    if setup_rows:
        weakest = max(
            setup_rows,
            key=lambda item: (
                float(item.get("invalidated_rate") or 0.0),
                int(item.get("total") or 0),
            ),
        )
        cards.append(
            _shadow_card(
                kind="shadow_setup_pressure",
                tone="warning",
                title=f"{weakest.get('label')} 需要重点复核",
                summary=(
                    f"T+5 {weakest.get('label')} {weakest.get('total')} 条，"
                    f"失效 {weakest.get('invalidated_rate')}%、验证 {weakest.get('validated_rate')}%。"
                ),
                action_reason="把形态分布当作复核优先级，不把它当作自动调参结论。",
                sample_size=int(weakest.get("total") or 0),
            )
        )

    start_date = str(args.get("start_date") or summary.get("start_date") or "")[:10]
    end_date = str(args.get("end_date") or summary.get("end_date") or "")[:10]
    panel_rows = int(summary.get("panel_rows") or 0)
    available_labels = int(summary.get("available_labels") or available_rows)
    return {
        "status": "ready" if available_rows else "partial",
        "title": "历史影子校准提示",
        "summary": (
            f"{start_date or '-'} 至 {end_date or '-'}："
            f"{panel_rows or int(summary.get('sample_codes') or 0)} 条 price-signal 样本，"
            f"{available_labels} 条 outcome label。"
        ),
        "warning": "研究专用：shadow_price_signal_baseline + current_constituents_approx；只辅助提问，不提升真实样本强度。",
        "sample_origin": "historical_shadow",
        "source_lane": "shadow_price_signal_baseline",
        "universe_policy": "current_constituents_approx",
        "start_date": start_date,
        "end_date": end_date,
        "panel_rows": panel_rows,
        "label_rows": label_rows,
        "available_labels": available_labels,
        "trade_dates": int(summary.get("trade_dates_with_samples") or 0),
        "generated_at": manifest.get("generated_at"),
        "manifest_path": str(manifest_path),
        "labels_path": str(labels_path),
        "cards": cards[:4],
        "bucket_rows": bucket_rows,
        "setup_rows": setup_rows,
        "window_rows": window_rows,
        "action_rows": action_rows,
    }


def _shadow_calibration_refs_for_record(
    record: Mapping[str, Any],
    *,
    review_reason_key: str,
    limit: int = 3,
) -> list[dict[str, Any]]:
    shadow = build_shadow_calibration_summary()
    if shadow.get("status") != "ready":
        return []
    bucket_rows = list(shadow.get("bucket_rows") or [])
    setup_rows = list(shadow.get("setup_rows") or [])
    selected: list[dict[str, Any]] = []
    wanted_buckets = {
        "missed_opportunity": {"near_miss", "risk_reject"},
        "invalidated": {"top_observe"},
        "execution_gap": {"top_observe"},
    }.get(review_reason_key, {"top_observe", "risk_reject"})
    for row in bucket_rows:
        if str(row.get("key") or "") in wanted_buckets:
            item = dict(row)
            item["title"] = _shadow_ref_text(item)
            item["summary"] = "历史影子样本参考；不计入真实 Review Case 样本数。"
            selected.append(item)
    if review_reason_key in {"invalidated", "missed_opportunity"} and setup_rows:
        if review_reason_key == "missed_opportunity":
            setup = max(
                setup_rows,
                key=lambda item: (
                    float(item.get("missed_opportunity_rate") or 0.0),
                    int(item.get("total") or 0),
                ),
            )
        else:
            setup = max(
                setup_rows,
                key=lambda item: (
                    float(item.get("invalidated_rate") or 0.0),
                    int(item.get("total") or 0),
                ),
            )
        item = dict(setup)
        item["title"] = _shadow_ref_text(item)
        item["summary"] = "同形态影子分布参考；需要用真实样本确认后才可改规则。"
        selected.append(item)
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in selected:
        key = (str(item.get("axis") or ""), str(item.get("key") or ""))
        if key in seen:
            continue
        item["sample_origin"] = "historical_shadow"
        item["source_lane"] = "shadow_price_signal_baseline"
        item["universe_policy"] = "current_constituents_approx"
        deduped.append(item)
        seen.add(key)
    return deduped[: max(0, limit)]


def _record_text_blob(record: Mapping[str, Any]) -> str:
    recommendation = record.get("recommendation") or {}
    evidence = record.get("evidence_snapshot") or {}
    parts = [
        recommendation.get("main_conclusion"),
        recommendation.get("position_guidance"),
        recommendation.get("trigger_condition"),
        recommendation.get("continue_condition"),
        recommendation.get("stop_condition"),
        recommendation.get("risk_summary"),
        evidence.get("readiness_mode"),
        evidence.get("theme_summary"),
    ]
    for metric in evidence.get("metric_cards") or []:
        if isinstance(metric, Mapping):
            parts.append(metric.get("text"))
    return " ".join(_short_text(part, limit=260) for part in parts if part)


def _same_pattern_count_for_primary(
    *,
    cases: Iterable[Mapping[str, Any]],
    record: Mapping[str, Any],
    review_reason_key: str,
    primary_cause: str,
    decision_id: str,
) -> int:
    source = record.get("source") or {}
    recommendation = record.get("recommendation") or {}
    pattern_key = _review_pattern_key_from_values(
        lane=source.get("lane"),
        action=recommendation.get("action"),
        review_reason_key=review_reason_key,
        primary_cause=primary_cause,
    )
    return sum(
        1
        for case in cases
        if case.get("decision_id") != decision_id
        and _review_pattern_key(case) == pattern_key
    ) + 1


def _review_case_ref(case: Mapping[str, Any]) -> dict[str, Any]:
    labelled = _case_labelled(case)
    return {
        "review_case_id": labelled.get("review_case_id"),
        "decision_id": labelled.get("decision_id"),
        "stock_code": labelled.get("stock_code"),
        "stock_name": labelled.get("stock_name"),
        "trade_date": labelled.get("trade_date"),
        "lane": labelled.get("lane"),
        "action": labelled.get("action"),
        "review_reason_key": labelled.get("review_reason_key"),
        "primary_cause": labelled.get("primary_cause"),
        "primary_cause_label": labelled.get("primary_cause_label"),
        "conclusion_action": labelled.get("conclusion_action"),
        "conclusion_action_label": labelled.get("conclusion_action_label"),
        "evidence_strength": labelled.get("evidence_strength"),
        "evidence_strength_label": labelled.get("evidence_strength_label"),
        "sample_count": labelled.get("sample_count"),
        "review_note": labelled.get("review_note"),
    }


def _pattern_ref(pattern: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "pattern_id": pattern.get("pattern_id"),
        "lane": pattern.get("lane"),
        "action": pattern.get("action"),
        "review_reason_key": pattern.get("review_reason_key"),
        "primary_cause": pattern.get("primary_cause"),
        "sample_count": pattern.get("sample_count"),
        "evidence_strength": pattern.get("evidence_strength"),
        "rule_action_allowed": pattern.get("rule_action_allowed"),
        "dominant_conclusion_action": pattern.get("dominant_conclusion_action"),
        "dominant_secondary_causes": pattern.get("dominant_secondary_causes"),
        "learning_hint": pattern.get("learning_hint"),
    }


def _similar_review_memory(
    *,
    record: Mapping[str, Any],
    review_reason_key: str,
    cases: list[Mapping[str, Any]],
    limit: int = 5,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source = record.get("source") or {}
    recommendation = record.get("recommendation") or {}
    lane = str(source.get("lane") or "")
    action = str(recommendation.get("action") or "")
    stock_code = str((record.get("stock") or {}).get("code") or "")

    def case_rank(case: Mapping[str, Any]) -> tuple[int, str]:
        score = 0
        if str(case.get("lane") or "") == lane:
            score += 4
        if str(case.get("action") or "") == action:
            score += 3
        if str(case.get("review_reason_key") or "") == review_reason_key:
            score += 3
        if stock_code and str(case.get("stock_code") or "") == stock_code:
            score += 1
        return score, str(case.get("reviewed_at") or "")

    ranked = [
        case for case in cases
        if case_rank(case)[0] >= 6
    ]
    ranked.sort(key=case_rank, reverse=True)
    similar_cases = [_review_case_ref(case) for case in ranked[:limit]]

    patterns = build_review_case_patterns(cases=cases, limit=100).get("patterns", [])
    matched_patterns: list[dict[str, Any]] = []
    for pattern in patterns:
        score = 0
        if str(pattern.get("lane") or "") == lane:
            score += 4
        if str(pattern.get("action") or "") == action:
            score += 3
        if str(pattern.get("review_reason_key") or "") == review_reason_key:
            score += 3
        if score >= 6:
            item = dict(pattern)
            item["_rank_score"] = score
            matched_patterns.append(item)
    matched_patterns.sort(
        key=lambda item: (int(item.get("_rank_score") or 0), int(item.get("sample_count") or 0)),
        reverse=True,
    )
    return similar_cases, [_pattern_ref(pattern) for pattern in matched_patterns[:limit]]


def _provider_config() -> AttributionProviderConfig:
    provider = (
        os.environ.get("PRISM_AI_PROVIDER")
        or ("openai" if os.environ.get("OPENAI_API_KEY") else "compatible")
    ).strip().lower()
    api_key = (os.environ.get("PRISM_AI_API_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip()
    model = (os.environ.get("PRISM_AI_MODEL") or os.environ.get("OPENAI_MODEL") or "").strip()
    base_url = (os.environ.get("PRISM_AI_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or "").strip()
    if not base_url and provider == "deepseek":
        base_url = "https://api.deepseek.com"
    elif not base_url and provider == "openai":
        base_url = "https://api.openai.com"
    if not model and provider == "deepseek":
        model = "deepseek-v4-flash"
    timeout_raw = os.environ.get("PRISM_AI_TIMEOUT_SECONDS", "").strip()
    try:
        timeout_seconds = max(1.0, min(float(timeout_raw), 60.0)) if timeout_raw else 12.0
    except ValueError:
        timeout_seconds = 12.0
    configured = bool(api_key and model and base_url)
    return AttributionProviderConfig(
        provider=provider or "compatible",
        api_key=api_key,
        model=model,
        base_url=base_url.rstrip("/"),
        timeout_seconds=timeout_seconds,
        configured=configured,
    )


def _chat_completions_url(config: AttributionProviderConfig) -> str:
    if config.provider == "deepseek":
        return f"{config.base_url}/chat/completions"
    return f"{config.base_url}/v1/chat/completions"


def _extract_json_object(text: str) -> dict[str, Any]:
    candidate = str(text or "").strip()
    if not candidate:
        raise DecisionLedgerError("empty provider response")
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start < 0 or end <= start:
            raise DecisionLedgerError("provider response did not contain a JSON object")
        parsed = json.loads(candidate[start : end + 1])
    if not isinstance(parsed, Mapping):
        raise DecisionLedgerError("provider response JSON must be an object")
    return dict(parsed)


def _attribution_context_payload(
    *,
    workbench: Mapping[str, Any],
    similar_case_refs: list[dict[str, Any]],
    pattern_refs: list[dict[str, Any]],
    shadow_refs: list[dict[str, Any]],
) -> dict[str, Any]:
    record = workbench.get("decision") or {}
    learning = workbench.get("learning_record") or {}
    latest_outcome = _latest_outcome_event(record.get("outcome_events") or [])
    latest_classification = latest_outcome.get("classification") if latest_outcome else {}
    latest_market = latest_outcome.get("market_data") if latest_outcome else {}
    return {
        "decision_id": record.get("decision_id"),
        "trade_date": record.get("trade_date"),
        "stock": record.get("stock"),
        "source": record.get("source"),
        "recommendation": record.get("recommendation"),
        "evidence_snapshot": {
            "expected_trade_date": (record.get("evidence_snapshot") or {}).get("expected_trade_date"),
            "data_trade_date": (record.get("evidence_snapshot") or {}).get("data_trade_date"),
            "readiness_mode": (record.get("evidence_snapshot") or {}).get("readiness_mode"),
            "readiness_ready": (record.get("evidence_snapshot") or {}).get("readiness_ready"),
            "blockers": (record.get("evidence_snapshot") or {}).get("blockers") or [],
            "warnings": (record.get("evidence_snapshot") or {}).get("warnings") or [],
            "metric_cards": (record.get("evidence_snapshot") or {}).get("metric_cards") or [],
            "theme_summary": (record.get("evidence_snapshot") or {}).get("theme_summary"),
        },
        "latest_outcome": {
            "window": latest_outcome.get("window") if latest_outcome else None,
            "as_of_trade_date": latest_outcome.get("as_of_trade_date") if latest_outcome else None,
            "classification": latest_classification,
            "market_data": latest_market,
            "quality": latest_outcome.get("quality") if latest_outcome else None,
            "boundary_checks": latest_outcome.get("boundary_checks") if latest_outcome else None,
        },
        "execution_events_count": len(record.get("execution_events") or []),
        "learning_record": {
            "review_status": learning.get("review_status"),
            "review_reason_key": learning.get("review_reason_key"),
            "review_reason": learning.get("review_reason"),
            "execution_status": learning.get("execution_status"),
            "priority_reasons": learning.get("priority_reasons") or [],
        },
        "similar_case_refs": similar_case_refs,
        "pattern_memory_refs": pattern_refs,
        "shadow_sample_refs": shadow_refs,
        "shadow_sample_boundary": (
            "shadow_sample_refs are research-only price-signal baseline samples; "
            "never count them as real Decision Ledger samples or executable rule-change authority."
        ),
        "enum_constraints": {
            "primary_cause": list(PRIMARY_REVIEW_CAUSES),
            "secondary_causes": list(SECONDARY_REVIEW_CAUSES),
            "conclusion_action": list(CONCLUSION_ACTIONS),
            "follow_up_status": list(FOLLOW_UP_STATUSES),
            "confidence": list(ATTRIBUTION_CONFIDENCE_LEVELS),
        },
        "sample_guardrails": {
            "1": "observation_hypothesis only; no executable rule change",
            "2-4": "validating_pattern only",
            "5-9": "rule_adjustment_suggestion; still needs validation",
            "10+": "strategy_calibration_suggestion",
        },
    }


def _provider_attribution_draft(
    *,
    workbench: Mapping[str, Any],
    similar_case_refs: list[dict[str, Any]],
    pattern_refs: list[dict[str, Any]],
    shadow_refs: list[dict[str, Any]],
) -> dict[str, Any]:
    config = _provider_config()
    if not config.configured:
        raise DecisionLedgerError("AI provider not configured")

    system_prompt = (
        "你是 Prism 的 AI Attribution Copilot。只生成 Review Case 结构化归因草稿，"
        "不能把样本标记为已归因，不能直接保存，不能绕过人工确认。"
        "输出必须是单个 JSON object，字段只能使用给定枚举。"
        "样本少于 5 条时不得给出可执行 loosen/tighten/add_guardrail 规则修改。"
        "数据缺失优先 data_unavailable；需要执行但缺执行记录优先 execution_gap。"
        "shadow_sample_refs 只能作为研究侧背景，不得计入真实样本数或规则修改权限。"
    )
    example_json = {
        "primary_cause": "too_strict",
        "secondary_causes": ["volume_too_conservative"],
        "review_note": "示例备注",
        "conclusion_action": "wait_more_samples",
        "rule_hypothesis": "示例假设",
        "follow_up_status": "sample_insufficient",
        "confidence": "medium",
        "evidence": ["示例证据 1", "示例证据 2"],
        "human_check_required": ["示例人工确认项 1"],
        "similar_case_refs": [],
        "shadow_sample_refs": [],
    }
    user_payload = _attribution_context_payload(
        workbench=workbench,
        similar_case_refs=similar_case_refs,
        pattern_refs=pattern_refs,
        shadow_refs=shadow_refs,
    )
    user_prompt = (
        "请基于以下 JSON 生成 AI 预归因草稿。返回字段至少包括："
        "primary_cause, secondary_causes, review_note, conclusion_action, "
        "rule_hypothesis, follow_up_status, confidence, evidence, "
        "human_check_required, similar_case_refs, shadow_sample_refs。"
        "只返回一个 json object，不要输出额外说明。"
        "输出格式示例：\n"
        f"{json.dumps(example_json, ensure_ascii=False, sort_keys=True)}\n"
        "输入 JSON：\n"
        f"{json.dumps(user_payload, ensure_ascii=False, sort_keys=True)}"
    )

    try:
        import httpx  # type: ignore

        body = {
            "model": config.model,
            "temperature": 0.1,
            "max_tokens": 1200,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if config.provider == "deepseek":
            body["response_format"] = {"type": "json_object"}
            body["thinking"] = {"type": "disabled"}

        with httpx.Client(timeout=config.timeout_seconds, trust_env=False) as client:
            response = client.post(
                _chat_completions_url(config),
                headers={
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
        response.raise_for_status()
        payload = response.json()
        content = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
        draft = _extract_json_object(content)
    except Exception as exc:  # Provider failures must never block review.
        raise DecisionLedgerError(f"AI provider unavailable: {exc}") from exc

    draft["_provider_meta"] = {
        "provider": config.provider,
        "model": config.model,
        "base_url": config.base_url,
    }
    return draft


def _hard_priority_draft(
    *,
    record: Mapping[str, Any],
    learning: Mapping[str, Any],
) -> dict[str, Any] | None:
    latest_outcome = _latest_outcome_event(record.get("outcome_events") or [])
    latest_label = _latest_outcome_label(latest_outcome)
    latest_quality = latest_outcome.get("quality") if latest_outcome else {}
    action = str((record.get("recommendation") or {}).get("action") or "")
    execution_events = list(record.get("execution_events") or [])
    if (
        latest_label == "data_issue"
        or latest_quality.get("data_issue")
        or str(learning.get("review_status") or "") == "blocked_data"
    ):
        return {
            "primary_cause": "data_unavailable",
            "secondary_causes": ["data_delay"],
            "review_note": "当前样本优先视为数据不可用，先确认行情、来源新鲜度与 outcome 质量。",
            "conclusion_action": "fix_data_pipeline",
            "rule_hypothesis": "该样本不能用于规则松紧判断；需要先修复或确认数据链路后再复盘。",
            "follow_up_status": "observing",
            "confidence": "high",
            "human_check_required": ["确认行情数据源与 data_trade_date", "确认 outcome 是否可用于决策质量评价"],
        }
    if _action_requires_execution(action) and not execution_events:
        return {
            "primary_cause": "execution_gap",
            "secondary_causes": [],
            "review_note": "原始动作需要执行，但当前缺少执行记录，优先归因为执行链路落差。",
            "conclusion_action": "fix_execution_pipeline",
            "rule_hypothesis": "先补齐成交、未成交或跳过记录；没有执行闭环前不评价交易规则本身。",
            "follow_up_status": "observing",
            "confidence": "high",
            "human_check_required": ["确认是否实际下单", "确认成交/未成交/跳过记录为何缺失"],
        }
    return None


def _heuristic_attribution_draft(
    *,
    workbench: Mapping[str, Any],
    similar_case_refs: list[dict[str, Any]],
    pattern_refs: list[dict[str, Any]],
    shadow_refs: list[dict[str, Any]],
) -> dict[str, Any]:
    record = workbench.get("decision") or {}
    learning = workbench.get("learning_record") or {}
    hard = _hard_priority_draft(record=record, learning=learning)
    stock = record.get("stock") or {}
    recommendation = record.get("recommendation") or {}
    source = record.get("source") or {}
    latest_outcome = _latest_outcome_event(record.get("outcome_events") or [])
    latest_label = _latest_outcome_label(latest_outcome)
    latest_classification = latest_outcome.get("classification") if latest_outcome else {}
    latest_market = latest_outcome.get("market_data") if latest_outcome else {}
    review_reason_key = str(learning.get("review_reason_key") or latest_label or "attention")
    action = str(recommendation.get("action") or "unknown")
    action_label = str(recommendation.get("action_label") or action)
    name = str(stock.get("name") or stock.get("code") or "该样本")

    if hard is not None:
        draft = dict(hard)
    elif latest_label == "missed_opportunity":
        blob = _record_text_blob(record)
        secondary: list[str] = []
        if any(token in blob for token in ("量", "成交", "放量", "萎缩", "爆量")):
            secondary.append("volume_too_conservative")
        if any(token in blob for token in ("主力", "资金", "流入", "转负")):
            secondary.append("capital_flow_filter_strict")
        if any(token in blob for token in ("环境", "readiness", "shadow", "弱修复")):
            secondary.append("market_regime_gate_strict")
        if any(token in blob for token in ("高开低走", "冲高回落", "开盘")):
            secondary.append("open_behavior_misread")
        if any(token in blob for token in ("风险", "止损", "别")):
            secondary.append("risk_condition_not_triggered")
        if not secondary:
            secondary.append("risk_condition_not_triggered")
        draft = {
            "primary_cause": "too_strict",
            "secondary_causes": secondary[:3],
            "review_note": f"{name} 原始动作为 {action_label}，后续出现明显机会，当前更像风险过滤偏保守。",
            "conclusion_action": "wait_more_samples",
            "rule_hypothesis": "类似样本可作为观察假设：若后续承接未破坏，应增加承接确认，而不是仅因单一风险项直接降级。",
            "follow_up_status": "sample_insufficient",
            "confidence": "medium",
            "human_check_required": ["确认次日是否真的放量承接", "确认原始风险条件是否发生"],
        }
    elif latest_label == "invalidated":
        draft = {
            "primary_cause": "too_loose",
            "secondary_causes": ["risk_condition_not_triggered"],
            "review_note": f"{name} 后续结果否定了原始判断，先检查触发条件是否过松或风险条件是否被低估。",
            "conclusion_action": "add_guardrail",
            "rule_hypothesis": "若同类样本继续出现，应考虑加入额外风险护栏；样本不足时只保留为假设。",
            "follow_up_status": "sample_insufficient",
            "confidence": "medium",
            "human_check_required": ["确认触发信号是否失真", "确认是否存在后续事件驱动"],
        }
    elif latest_label == "execution_gap":
        draft = {
            "primary_cause": "execution_gap",
            "secondary_causes": [],
            "review_note": "建议和执行之间出现落差，优先确认执行记录与操作原因。",
            "conclusion_action": "fix_execution_pipeline",
            "rule_hypothesis": "先修复执行闭环，再判断规则是否需要校准。",
            "follow_up_status": "observing",
            "confidence": "high",
            "human_check_required": ["确认实际执行状态", "确认未执行是否由流动性或人工选择导致"],
        }
    elif latest_label in {"validated", "avoided_loss"}:
        draft = {
            "primary_cause": "rule_valid_noise",
            "secondary_causes": [],
            "review_note": "后续结果没有否定原始规则，当前更像规则有效或个例噪音。",
            "conclusion_action": "keep_rule",
            "rule_hypothesis": "保持规则，继续观察同链路样本。",
            "follow_up_status": "observing",
            "confidence": "medium",
            "human_check_required": ["确认 outcome 分类是否准确"],
        }
    else:
        draft = {
            "primary_cause": "insufficient_sample",
            "secondary_causes": [],
            "review_note": "当前 outcome 信号不足，暂不形成规则判断。",
            "conclusion_action": "wait_more_samples",
            "rule_hypothesis": "先等待更多同类样本与更成熟 outcome。",
            "follow_up_status": "sample_insufficient",
            "confidence": "low",
            "human_check_required": ["确认样本是否已成熟", "确认是否需要补跑 outcome evaluator"],
        }

    evidence = [
        f"原始动作为 {action_label}",
        f"所处链路 {source.get('lane') or 'unknown'}",
    ]
    if latest_outcome:
        evidence.append(
            f"{latest_outcome.get('window') or 'Outcome'} 收益 "
            f"{_format_return_pct(latest_market.get('return_pct'))}，分类为 "
            f"{latest_classification.get('label') or latest_label or 'unknown'}"
        )
    if similar_case_refs:
        evidence.append(f"找到 {len(similar_case_refs)} 条相似历史 Review Case")
    if pattern_refs:
        evidence.append(f"找到 {len(pattern_refs)} 个相似 Pattern Memory")
    if shadow_refs:
        evidence.append(f"影子样本参考：{_shadow_ref_text(shadow_refs[0])}")
        checks = draft.get("human_check_required") if isinstance(draft.get("human_check_required"), list) else []
        checks.append("影子样本是研究口径，只能辅助提问，不能替代真实 Review Case 样本数")
        draft["human_check_required"] = checks
    draft["evidence"] = evidence
    draft["similar_case_refs"] = similar_case_refs
    draft["pattern_memory_refs"] = pattern_refs
    draft["shadow_sample_refs"] = shadow_refs
    return draft


def _sanitize_attribution_draft(
    *,
    decision_id: str,
    workbench: Mapping[str, Any],
    raw_draft: Mapping[str, Any],
    cases: list[Mapping[str, Any]],
    similar_case_refs: list[dict[str, Any]],
    pattern_refs: list[dict[str, Any]],
    shadow_refs: list[dict[str, Any]],
    fallback_reason: str = "",
) -> dict[str, Any]:
    record = workbench.get("decision") or {}
    learning = workbench.get("learning_record") or {}
    hard = _hard_priority_draft(record=record, learning=learning)
    default_primary = str((hard or {}).get("primary_cause") or "insufficient_sample")
    primary_cause = _choice_or_default(raw_draft.get("primary_cause"), PRIMARY_REVIEW_CAUSES, default_primary)
    if hard is not None:
        primary_cause = str(hard.get("primary_cause") or primary_cause)
    secondary_causes = _secondary_causes_or_default(raw_draft.get("secondary_causes"))
    if hard is not None:
        secondary_causes = _secondary_causes_or_default(hard.get("secondary_causes"))

    review_reason_key = str(learning.get("review_reason_key") or "attention")
    sample_count = _same_pattern_count_for_primary(
        cases=cases,
        record=record,
        review_reason_key=review_reason_key,
        primary_cause=primary_cause,
        decision_id=decision_id,
    )
    evidence_strength = _sample_stage(sample_count)

    conclusion_default = str((hard or {}).get("conclusion_action") or "wait_more_samples")
    conclusion_action = _choice_or_default(
        raw_draft.get("conclusion_action"),
        CONCLUSION_ACTIONS,
        conclusion_default,
    )
    if hard is not None:
        conclusion_action = str(hard.get("conclusion_action") or conclusion_action)
    rule_hypothesis = _short_text(raw_draft.get("rule_hypothesis"), limit=600)
    if hard is not None:
        rule_hypothesis = _short_text(hard.get("rule_hypothesis"), limit=600)
    if not rule_hypothesis:
        rule_hypothesis = _default_rule_hypothesis(
            record=record,
            primary_cause=primary_cause,
            conclusion_action=conclusion_action,
            sample_count=sample_count,
            review_reason_key=review_reason_key,
        )
    if sample_count < 5 and conclusion_action in _DIRECT_RULE_ACTIONS:
        conclusion_action = "wait_more_samples"
        rule_hypothesis = (
            f"{rule_hypothesis} 当前同类样本未达到 5 条，AI 预归因不生成可执行规则修改。"
        )

    follow_default = str((hard or {}).get("follow_up_status") or _default_follow_up_status(sample_count))
    follow_up_status = _choice_or_default(
        raw_draft.get("follow_up_status"),
        FOLLOW_UP_STATUSES,
        follow_default,
    )
    if sample_count < 2 and follow_up_status not in {"sample_insufficient", "observing"}:
        follow_up_status = "sample_insufficient"

    note = _short_text(raw_draft.get("review_note"), limit=600)
    if hard is not None:
        note = _short_text(hard.get("review_note"), limit=600)
    if not note:
        note = "AI 预归因仅作为草稿，需要人工确认后保存。"

    provider_meta = raw_draft.get("_provider_meta") if isinstance(raw_draft.get("_provider_meta"), Mapping) else {}
    shadow_sample_refs = _clean_json_list(raw_draft.get("shadow_sample_refs"), limit=6) or shadow_refs
    sanitized = {
        "schema_version": 1,
        "draft_id": f"attribution_draft:{hashlib.sha256((decision_id + _now()).encode('utf-8')).hexdigest()[:12]}",
        "decision_id": decision_id,
        "generated_at": _now(),
        "draft_source": "heuristic" if fallback_reason else "provider",
        "provider": provider_meta.get("provider") or ("heuristic" if fallback_reason else _provider_config().provider),
        "model": provider_meta.get("model"),
        "fallback_reason": fallback_reason,
        "primary_cause": primary_cause,
        "secondary_causes": secondary_causes,
        "review_note": note,
        "conclusion_action": conclusion_action,
        "rule_hypothesis": rule_hypothesis,
        "follow_up_status": follow_up_status,
        "confidence": _confidence_or_default(raw_draft.get("confidence"), str((hard or {}).get("confidence") or "medium")),
        "evidence": _clean_string_list(raw_draft.get("evidence"), limit=12),
        "human_check_required": _clean_string_list(raw_draft.get("human_check_required"), limit=8),
        "similar_case_refs": _clean_json_list(raw_draft.get("similar_case_refs"), limit=8) or similar_case_refs,
        "pattern_memory_refs": _clean_json_list(raw_draft.get("pattern_memory_refs"), limit=8) or pattern_refs,
        "shadow_sample_refs": shadow_sample_refs,
        "sample_count": sample_count,
        "evidence_strength": evidence_strength,
        "evidence_strength_label": _SAMPLE_STAGE_LABELS.get(evidence_strength, evidence_strength),
        "evidence_strength_detail": _sample_stage_detail(sample_count),
        "rule_action_allowed": sample_count >= 5,
    }
    if not sanitized["evidence"]:
        sanitized["evidence"] = _clean_string_list(
            _heuristic_attribution_draft(
                workbench=workbench,
                similar_case_refs=similar_case_refs,
                pattern_refs=pattern_refs,
                shadow_refs=shadow_refs,
            ).get("evidence"),
            limit=12,
        )
    if shadow_sample_refs and not any("影子样本" in item for item in sanitized["evidence"]):
        sanitized["evidence"].append(f"影子样本参考：{_shadow_ref_text(shadow_sample_refs[0])}")
    if not sanitized["human_check_required"]:
        sanitized["human_check_required"] = _clean_string_list(
            (hard or raw_draft).get("human_check_required"),
            limit=8,
        ) or ["人工确认原始风险条件和后续 outcome 分类是否准确"]
    return sanitized


def build_attribution_draft(decision_id: str) -> dict[str, Any]:
    """Generate a structured AI attribution draft without saving a Review Case."""

    workbench = build_review_case_workbench(decision_id)
    cases = _read_review_cases_file()
    learning = workbench.get("learning_record") or {}
    review_reason_key = str(learning.get("review_reason_key") or "attention")
    similar_case_refs, pattern_refs = _similar_review_memory(
        record=workbench.get("decision") or {},
        review_reason_key=review_reason_key,
        cases=cases,
    )
    shadow_refs = _shadow_calibration_refs_for_record(
        workbench.get("decision") or {},
        review_reason_key=review_reason_key,
    )

    fallback_reason = ""
    try:
        raw_draft = _provider_attribution_draft(
            workbench=workbench,
            similar_case_refs=similar_case_refs,
            pattern_refs=pattern_refs,
            shadow_refs=shadow_refs,
        )
    except DecisionLedgerError as exc:
        fallback_reason = str(exc)
        raw_draft = _heuristic_attribution_draft(
            workbench=workbench,
            similar_case_refs=similar_case_refs,
            pattern_refs=pattern_refs,
            shadow_refs=shadow_refs,
        )

    return _sanitize_attribution_draft(
        decision_id=decision_id,
        workbench=workbench,
        raw_draft=raw_draft,
        cases=cases,
        similar_case_refs=similar_case_refs,
        pattern_refs=pattern_refs,
        shadow_refs=shadow_refs,
        fallback_reason=fallback_reason,
    )


def _review_case_status_for_sample(sample_count: int) -> str:
    stage = _sample_stage(sample_count)
    if stage in {"rule_adjustment_suggestion", "strategy_calibration_suggestion"}:
        return "rule_suggestion"
    if stage == "validating_pattern":
        return "pattern_formed"
    return "attributed"


def _default_follow_up_status(sample_count: int) -> str:
    return "observing" if int(sample_count or 0) >= 2 else "sample_insufficient"


def _default_follow_up_due_at() -> str:
    return (datetime.now().date() + timedelta(days=14)).strftime("%Y-%m-%d")


def _review_pattern_key_from_values(
    *,
    lane: Any,
    action: Any,
    review_reason_key: Any,
    primary_cause: Any,
) -> str:
    parts = [
        str(lane or "unknown").strip() or "unknown",
        str(action or "unknown").strip() or "unknown",
        str(review_reason_key or "attention").strip() or "attention",
        str(primary_cause or "unknown").strip() or "unknown",
    ]
    return "|".join(parts)


def _review_pattern_key(case: Mapping[str, Any]) -> str:
    return _review_pattern_key_from_values(
        lane=case.get("lane"),
        action=case.get("action"),
        review_reason_key=case.get("review_reason_key"),
        primary_cause=case.get("primary_cause"),
    )


def _case_labelled(case: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(case)
    primary = str(out.get("primary_cause") or "")
    conclusion = str(out.get("conclusion_action") or "")
    follow_up = str(out.get("follow_up_status") or "")
    status = str(out.get("review_status") or "")
    stage = str(out.get("evidence_strength") or _sample_stage(int(out.get("sample_count") or 1)))
    out["primary_cause_label"] = _PRIMARY_REVIEW_CAUSE_LABELS.get(primary, primary)
    out["secondary_cause_labels"] = [
        _SECONDARY_REVIEW_CAUSE_LABELS.get(str(item), str(item))
        for item in (out.get("secondary_causes") or [])
    ]
    out["conclusion_action_label"] = _CONCLUSION_ACTION_LABELS.get(conclusion, conclusion)
    out["follow_up_status_label"] = _FOLLOW_UP_STATUS_LABELS.get(follow_up, follow_up)
    out["review_status_label"] = _REVIEW_CASE_STATUS_LABELS.get(status, status)
    out["evidence_strength_label"] = _SAMPLE_STAGE_LABELS.get(stage, stage)
    out["evidence_strength_detail"] = _sample_stage_detail(int(out.get("sample_count") or 1))
    out["rule_action_allowed"] = int(out.get("sample_count") or 0) >= 5
    return out


def list_review_cases() -> dict[str, Any]:
    """Return all saved Review Cases with display labels.

    Review cases are the write-side of the Review page: one structured
    attribution per decision, stored separately from the immutable
    DecisionRecord.  A corrupt case file is intentionally loud because a
    bad attribution store would make the learning queue lie.

    The ``revision`` field is a content-based sha256 of the underlying
    case list. It is stable across processes and changes only when the
    persisted attribution content changes — callers can use it as a
    cache key instead of relying on file mtime.
    """

    raw_cases = _read_review_cases_file()
    revision = _compute_review_cases_revision(raw_cases)
    cases = [_case_labelled(case) for case in raw_cases]
    return {
        "items": cases,
        "count": len(cases),
        "patterns": build_review_case_patterns(cases=cases).get("patterns", []),
        "revision": revision,
    }


def _review_case_for_decision(
    cases: Iterable[Mapping[str, Any]],
    decision_id: str,
) -> dict[str, Any] | None:
    for case in cases:
        if case.get("decision_id") == decision_id:
            return dict(case)
    return None


def _review_cases_by_decision(cases: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for case in cases:
        decision_id = str(case.get("decision_id") or "")
        if decision_id:
            out[decision_id] = dict(case)
    return out


def _default_rule_hypothesis(
    *,
    record: Mapping[str, Any],
    primary_cause: str,
    conclusion_action: str,
    sample_count: int,
    review_reason_key: str,
) -> str:
    stock = record.get("stock") or {}
    source = record.get("source") or {}
    cause_label = _PRIMARY_REVIEW_CAUSE_LABELS.get(primary_cause, primary_cause)
    action_label = _CONCLUSION_ACTION_LABELS.get(conclusion_action, conclusion_action)
    stage_label = _SAMPLE_STAGE_LABELS[_sample_stage(sample_count)]
    reason_label = _REVIEW_REASON_LABELS.get(review_reason_key, review_reason_key)
    name = str(stock.get("name") or stock.get("code") or "该样本")
    lane = str(source.get("lane") or "unknown")
    guardrail = "；当前样本不足，不能作为直接规则修改。"
    if sample_count >= 5:
        guardrail = "；样本数达到规则建议门槛，后续仍需验证状态追踪。"
    elif sample_count >= 2:
        guardrail = "；先作为待验证模式继续观察。"
    return (
        f"{stage_label}：{lane} 中 {name} 触发 {reason_label}，主归因为{cause_label}，"
        f"结论动作为{action_label}{guardrail}"
    )


def _final_attribution_payload(
    *,
    primary_cause: str,
    secondary_causes: list[str],
    review_note: str,
    conclusion_action: str,
    rule_hypothesis: str,
    follow_up_status: str,
    follow_up_due_at: str,
    evidence_strength: str,
    sample_count: int,
) -> dict[str, Any]:
    return {
        "primary_cause": primary_cause,
        "secondary_causes": secondary_causes,
        "review_note": review_note,
        "conclusion_action": conclusion_action,
        "rule_hypothesis": rule_hypothesis,
        "follow_up_status": follow_up_status,
        "follow_up_due_at": follow_up_due_at,
        "evidence_strength": evidence_strength,
        "sample_count": sample_count,
        "rule_action_allowed": sample_count >= 5,
    }


def _human_overrides_from_draft(
    ai_draft: Mapping[str, Any] | None,
    human_final: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    if not ai_draft:
        return {}
    tracked_fields = (
        "primary_cause",
        "secondary_causes",
        "review_note",
        "conclusion_action",
        "rule_hypothesis",
        "follow_up_status",
    )
    overrides: dict[str, dict[str, Any]] = {}
    for field in tracked_fields:
        draft_value = ai_draft.get(field)
        final_value = human_final.get(field)
        if field == "secondary_causes":
            draft_compare = sorted(str(item) for item in (draft_value or []))
            final_compare = sorted(str(item) for item in (final_value or []))
            changed = draft_compare != final_compare
        else:
            changed = _short_text(draft_value, limit=1000) != _short_text(final_value, limit=1000)
        if changed:
            overrides[field] = {"from": draft_value, "to": final_value}
    return overrides


def _clean_optional_mapping(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except TypeError:
        return {str(key): _short_text(val, limit=500) for key, val in value.items()}


def _refresh_pattern_sample_counts(cases: list[dict[str, Any]], pattern_key: str) -> None:
    matched = [case for case in cases if _review_pattern_key(case) == pattern_key]
    sample_count = len(matched)
    stage = _sample_stage(sample_count)
    status = _review_case_status_for_sample(sample_count)
    for case in matched:
        case["sample_count"] = sample_count
        case["evidence_strength"] = stage
        case["review_status"] = status
        if not case.get("follow_up_status") or case.get("follow_up_status") == "sample_insufficient":
            case["follow_up_status"] = _default_follow_up_status(sample_count)


def save_review_case(decision_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Create or update the Review Case for one DecisionRecord.

    The DecisionRecord stays immutable.  This function writes a separate
    structured attribution, computes the same-pattern sample count, and
    downgrades direct rule actions below the 5-sample threshold into an
    observation or validation hypothesis.
    """

    if not isinstance(payload, Mapping):
        raise DecisionLedgerError("review case payload must be a mapping")
    record = load_decision(decision_id)
    if record is None:
        raise DecisionLedgerError(f"decision not found: {decision_id!r}")

    primary_cause = _normalize_review_choice(
        payload.get("primary_cause"),
        PRIMARY_REVIEW_CAUSES,
        "primary_cause",
    )
    conclusion_action = _normalize_review_choice(
        payload.get("conclusion_action"),
        CONCLUSION_ACTIONS,
        "conclusion_action",
    )
    secondary_causes = _normalize_secondary_causes(payload.get("secondary_causes"))
    follow_up_status_raw = str(payload.get("follow_up_status") or "").strip()
    follow_up_status = (
        _normalize_review_choice(follow_up_status_raw, FOLLOW_UP_STATUSES, "follow_up_status")
        if follow_up_status_raw
        else ""
    )

    note = str(payload.get("review_note") or "").strip()
    rule_hypothesis_input = str(payload.get("rule_hypothesis") or "").strip()
    follow_up_due_at = str(payload.get("follow_up_due_at") or "").strip() or _default_follow_up_due_at()
    if follow_up_due_at:
        _normalize_trade_date(follow_up_due_at)

    cases = _read_review_cases_file()
    existing = _review_case_for_decision(cases, decision_id)
    source = record.get("source") or {}
    recommendation = record.get("recommendation") or {}
    stock = record.get("stock") or {}
    card = _decision_learning_card(record, as_of=_resolve_as_of(None), pattern_counts={})
    review_reason_key = str(card.get("review_reason_key") or "")
    pattern_key = _review_pattern_key_from_values(
        lane=source.get("lane"),
        action=recommendation.get("action"),
        review_reason_key=review_reason_key,
        primary_cause=primary_cause,
    )
    same_pattern_count = sum(
        1
        for case in cases
        if case.get("decision_id") != decision_id
        and _review_pattern_key(case) == pattern_key
    ) + 1
    evidence_strength = _sample_stage(same_pattern_count)
    rule_hypothesis = rule_hypothesis_input or _default_rule_hypothesis(
        record=record,
        primary_cause=primary_cause,
        conclusion_action=conclusion_action,
        sample_count=same_pattern_count,
        review_reason_key=review_reason_key,
    )
    if same_pattern_count < 5 and conclusion_action in _DIRECT_RULE_ACTIONS:
        rule_hypothesis = (
            f"{_SAMPLE_STAGE_LABELS[evidence_strength]}：{rule_hypothesis} "
            "当前同类样本未达到 5 条，记录为假设，不生成可执行规则修改。"
        )
    final_follow_up_status = follow_up_status or _default_follow_up_status(same_pattern_count)
    ai_draft = _clean_optional_mapping(payload.get("ai_draft"))
    human_final = _final_attribution_payload(
        primary_cause=primary_cause,
        secondary_causes=secondary_causes,
        review_note=note,
        conclusion_action=conclusion_action,
        rule_hypothesis=rule_hypothesis,
        follow_up_status=final_follow_up_status,
        follow_up_due_at=follow_up_due_at,
        evidence_strength=evidence_strength,
        sample_count=same_pattern_count,
    )
    human_overrides = _human_overrides_from_draft(ai_draft, human_final)
    attribution_confidence = _confidence_or_default(
        payload.get("attribution_confidence"),
        _confidence_or_default((ai_draft or {}).get("confidence"), "medium"),
    )
    evidence_refs = _clean_json_list(
        payload.get("evidence_refs") if "evidence_refs" in payload else (ai_draft or {}).get("evidence"),
        limit=20,
    )
    human_check_required = _clean_json_list(
        payload.get("human_check_required")
        if "human_check_required" in payload
        else (ai_draft or {}).get("human_check_required"),
        limit=20,
    )
    similar_case_refs = _clean_json_list(
        payload.get("similar_case_refs")
        if "similar_case_refs" in payload
        else (ai_draft or {}).get("similar_case_refs"),
        limit=20,
    )
    shadow_sample_refs = _clean_json_list(
        payload.get("shadow_sample_refs")
        if "shadow_sample_refs" in payload
        else (ai_draft or {}).get("shadow_sample_refs"),
        limit=20,
    )

    case = {
        "schema_version": 1,
        "review_case_id": (existing or {}).get("review_case_id") or _review_case_id(decision_id),
        "decision_id": decision_id,
        "stock_code": stock.get("code"),
        "stock_name": stock.get("name"),
        "trade_date": record.get("trade_date"),
        "reviewed_at": _now(),
        "created_at": (existing or {}).get("created_at") or _now(),
        "review_status": _review_case_status_for_sample(same_pattern_count),
        "primary_cause": primary_cause,
        "secondary_causes": secondary_causes,
        "review_note": note,
        "conclusion_action": conclusion_action,
        "evidence_strength": evidence_strength,
        "sample_count": same_pattern_count,
        "rule_hypothesis": rule_hypothesis,
        "follow_up_status": final_follow_up_status,
        "follow_up_due_at": follow_up_due_at,
        "ai_draft": ai_draft,
        "human_final": human_final,
        "human_overrides": human_overrides,
        "attribution_confidence": attribution_confidence,
        "evidence_refs": evidence_refs,
        "human_check_required": human_check_required,
        "similar_case_refs": similar_case_refs,
        "shadow_sample_refs": shadow_sample_refs,
        "lane": source.get("lane"),
        "action": recommendation.get("action"),
        "action_label": recommendation.get("action_label"),
        "review_reason_key": review_reason_key,
        "review_reason": card.get("review_reason"),
        "market_regime": (record.get("evidence_snapshot") or {}).get("readiness_mode"),
        "stock_theme": (record.get("evidence_snapshot") or {}).get("theme_summary"),
        "evidence_source": source.get("source_label") or source.get("surface"),
        "latest_outcome": card.get("latest_outcome"),
        "latest_execution": card.get("latest_execution"),
    }

    next_cases: list[dict[str, Any]] = []
    replaced = False
    for prior in cases:
        if prior.get("decision_id") == decision_id:
            next_cases.append(case)
            replaced = True
        else:
            next_cases.append(dict(prior))
    if not replaced:
        next_cases.append(case)
    _refresh_pattern_sample_counts(next_cases, pattern_key)
    _write_review_cases_file(next_cases)
    saved = _review_case_for_decision(next_cases, decision_id) or case
    return _case_labelled(saved)


def _apply_review_case_to_card(
    card: dict[str, Any],
    review_case: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not review_case:
        return card
    labelled = _case_labelled(review_case)
    sample_count = int(labelled.get("sample_count") or 1)
    conclusion_action = str(labelled.get("conclusion_action") or "")
    if conclusion_action == "keep_rule":
        calibration_action = "keep_rule"
    elif conclusion_action == "wait_more_samples":
        calibration_action = "wait_for_sample"
    elif conclusion_action == "fix_data_pipeline":
        calibration_action = "fix_data"
    elif conclusion_action == "fix_execution_pipeline":
        calibration_action = "fix_execution"
    elif sample_count >= 5 and conclusion_action == "loosen_filter":
        calibration_action = "loosen_rule"
    elif sample_count >= 5 and conclusion_action == "tighten_filter":
        calibration_action = "tighten_rule"
    elif sample_count >= 5 and conclusion_action == "add_guardrail":
        calibration_action = "add_guardrail"
    else:
        calibration_action = "investigate_pattern"

    card.update(
        {
            "review_status": "reviewed",
            "review_reason": "已完成人工归因",
            "review_reason_key": "reviewed",
            "next_action_label": labelled.get("conclusion_action_label") or "已归因",
            "next_action_reason": labelled.get("rule_hypothesis") or "已保存结构化 Review Case。",
            "calibration_action": calibration_action,
            "calibration_action_label": _CALIBRATION_ACTION_LABELS.get(calibration_action, calibration_action),
            "calibration_action_reason": labelled.get("evidence_strength_detail"),
            "review_case": labelled,
        }
    )
    axes = dict(card.get("quality_axes") or {})
    axes["learning_quality"] = _axis(
        "attributed",
        84,
        "positive",
        f"已保存 Review Case：{labelled.get('primary_cause_label')}。",
    )
    card["quality_axes"] = axes
    return card


def _pattern_summary_from_cases(pattern_cases: list[Mapping[str, Any]]) -> dict[str, Any]:
    first = pattern_cases[0]
    sample_count = len(pattern_cases)
    stage = _sample_stage(sample_count)
    follow_up_rank = {
        "rolled_back": 6,
        "adopted": 5,
        "invalid": 4,
        "preliminary_effective": 3,
        "observing": 2,
        "sample_insufficient": 1,
    }
    follow_up_status = max(
        (str(case.get("follow_up_status") or _default_follow_up_status(sample_count)) for case in pattern_cases),
        key=lambda item: follow_up_rank.get(item, 0),
    )
    latest = max(pattern_cases, key=lambda case: str(case.get("reviewed_at") or ""))
    reason_key = str(first.get("review_reason_key") or "")
    primary = str(first.get("primary_cause") or "")
    conclusion_counts: dict[str, int] = {}
    secondary_counts: dict[str, int] = {}
    for case in pattern_cases:
        action = str(case.get("conclusion_action") or "unknown")
        conclusion_counts[action] = conclusion_counts.get(action, 0) + 1
        for item in case.get("secondary_causes") or []:
            secondary = str(item or "").strip()
            if secondary:
                secondary_counts[secondary] = secondary_counts.get(secondary, 0) + 1
    dominant_action = max(conclusion_counts, key=conclusion_counts.get)
    dominant_secondary = [
        item for item, _count in sorted(
            secondary_counts.items(),
            key=lambda pair: (pair[1], pair[0]),
            reverse=True,
        )[:3]
    ]
    stock_codes = {
        str(case.get("stock_code") or "")
        for case in pattern_cases
        if case.get("stock_code")
    }
    stock_count = len(stock_codes)
    dominant_market_regime = _dominant_value(case.get("market_regime") for case in pattern_cases)
    dominant_stock_theme = _dominant_value(case.get("stock_theme") for case in pattern_cases)
    dominant_evidence_source = _dominant_value(case.get("evidence_source") for case in pattern_cases)
    lane = first.get("lane")
    action = first.get("action")
    action_label = first.get("action_label")
    primary_label = _PRIMARY_REVIEW_CAUSE_LABELS.get(primary, primary)
    reason_label = _REVIEW_REASON_LABELS.get(reason_key, reason_key)
    secondary_label = "、".join(
        _SECONDARY_REVIEW_CAUSE_LABELS.get(item, item) for item in dominant_secondary
    )
    theme_hint = f"{dominant_stock_theme} 主题中，" if dominant_stock_theme else ""
    learning_hint = (
        f"{theme_hint}{lane or 'unknown'} / {action_label or action or 'unknown'} "
        f"曾积累 {sample_count} 条 {reason_label} 复盘样本，主偏差为{primary_label}"
        f"{f'，常见辅助归因为{secondary_label}' if secondary_label else ''}。"
        "早盘/午盘分析可把它作为历史经验提醒与复盘优先级信号，不能自动修改交易规则。"
    )
    return {
        "pattern_id": _review_pattern_key(first),
        "lane": lane,
        "action": action,
        "action_label": action_label,
        "review_reason_key": reason_key,
        "review_reason_label": reason_label,
        "primary_cause": primary,
        "primary_cause_label": primary_label,
        "sample_count": sample_count,
        "stock_count": stock_count,
        "dominant_primary_cause": primary,
        "dominant_primary_cause_label": primary_label,
        "dominant_secondary_causes": dominant_secondary,
        "dominant_secondary_cause_labels": [
            _SECONDARY_REVIEW_CAUSE_LABELS.get(item, item)
            for item in dominant_secondary
        ],
        "evidence_strength": stage,
        "evidence_strength_label": _SAMPLE_STAGE_LABELS.get(stage, stage),
        "evidence_strength_detail": _sample_stage_detail(sample_count),
        "rule_action_allowed": sample_count >= 5,
        "stock_theme": dominant_stock_theme,
        "market_regime": dominant_market_regime,
        "evidence_source": dominant_evidence_source,
        "rule_hypothesis": latest.get("rule_hypothesis"),
        "follow_up_status": follow_up_status,
        "follow_up_status_label": _FOLLOW_UP_STATUS_LABELS.get(follow_up_status, follow_up_status),
        "dominant_conclusion_action": dominant_action,
        "dominant_conclusion_action_label": _CONCLUSION_ACTION_LABELS.get(dominant_action, dominant_action),
        "learning_hint": learning_hint,
        "learning_memory_scope": "pattern",
        "rule_candidate_allowed": sample_count >= 5 and follow_up_status in {"preliminary_effective", "adopted"},
        "cases": [_case_labelled(case) for case in sorted(
            pattern_cases,
            key=lambda item: str(item.get("reviewed_at") or ""),
            reverse=True,
        )],
    }


def build_review_case_patterns(
    *,
    cases: list[Mapping[str, Any]] | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    raw_cases = list(cases) if cases is not None else _read_review_cases_file()
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for case in raw_cases:
        groups.setdefault(_review_pattern_key(case), []).append(case)
    patterns = [_pattern_summary_from_cases(items) for items in groups.values() if items]
    patterns.sort(
        key=lambda item: (
            int(item.get("sample_count") or 0),
            str((item.get("cases") or [{}])[0].get("reviewed_at") or ""),
        ),
        reverse=True,
    )
    visible = patterns[: max(1, min(int(limit or 10), 100))]
    return {
        "patterns": visible,
        "count": len(patterns),
        "total_cases": len(raw_cases),
    }


def build_review_case_workbench(decision_id: str) -> dict[str, Any]:
    record = load_decision(decision_id)
    if record is None:
        raise DecisionLedgerError(f"decision not found: {decision_id!r}")
    cases = _read_review_cases_file()
    review_case = _review_case_for_decision(cases, decision_id)
    card = _decision_learning_card(record, as_of=_resolve_as_of(None), pattern_counts={})
    card = _apply_review_case_to_card(card, review_case)
    pattern_key = ""
    similar_cases: list[dict[str, Any]] = []
    pattern: dict[str, Any] | None = None
    if review_case:
        pattern_key = _review_pattern_key(review_case)
        similar_cases = [_case_labelled(case) for case in cases if _review_pattern_key(case) == pattern_key]
        if similar_cases:
            pattern = _pattern_summary_from_cases(similar_cases)

    return {
        "decision": record,
        "learning_record": card,
        "review_case": _case_labelled(review_case) if review_case else None,
        "similar_cases": similar_cases,
        "pattern": pattern,
        "options": {
            "primary_causes": [
                {"value": key, "label": _PRIMARY_REVIEW_CAUSE_LABELS[key]}
                for key in PRIMARY_REVIEW_CAUSES
            ],
            "secondary_causes": [
                {"value": key, "label": _SECONDARY_REVIEW_CAUSE_LABELS[key]}
                for key in SECONDARY_REVIEW_CAUSES
            ],
            "conclusion_actions": [
                {"value": key, "label": _CONCLUSION_ACTION_LABELS[key]}
                for key in CONCLUSION_ACTIONS
            ],
            "follow_up_statuses": [
                {"value": key, "label": _FOLLOW_UP_STATUS_LABELS[key]}
                for key in FOLLOW_UP_STATUSES
            ],
        },
        "guardrail": {
            "sample_count": int((review_case or {}).get("sample_count") or 1),
            "evidence_strength": str((review_case or {}).get("evidence_strength") or "observation_hypothesis"),
            "detail": _sample_stage_detail(int((review_case or {}).get("sample_count") or 1)),
        },
    }


def _record_has_real_position_context(
    record: Mapping[str, Any],
    execution_events: Iterable[Mapping[str, Any]],
) -> bool:
    recommendation = record.get("recommendation") or {}
    evidence = record.get("evidence_snapshot") or {}
    capital = evidence.get("capital_summary")
    position_guidance = str(recommendation.get("position_guidance") or "").strip()
    if isinstance(capital, Mapping) and capital:
        return True
    if position_guidance:
        return True
    return any(str(event.get("status") or "").strip().lower() == "filled" for event in execution_events)


def _next_maturity(
    record: Mapping[str, Any],
    *,
    as_of: str,
) -> dict[str, Any]:
    """Explain what outcome window the decision is waiting for next."""

    trade_date = str(record.get("trade_date") or "")
    outcome_events = list(record.get("outcome_events") or [])
    evaluated_windows = {
        str(event.get("window") or "").strip().upper()
        for event in outcome_events
    }
    as_of_date: date | None = None
    try:
        as_of_date = datetime.strptime(as_of, "%Y-%m-%d").date()
    except ValueError:
        as_of_date = None

    for window in OUTCOME_WINDOWS:
        if window in evaluated_windows:
            continue
        due_at = nth_trading_day_after(trade_date, _OUTCOME_WINDOW_STEPS[window])
        if not due_at:
            return {
                "maturity_due_at": None,
                "maturity_window": window,
                "maturity_label": f"无法计算 {window} 成熟日",
                "is_overdue": False,
                "is_due": False,
                "missing_due_date": True,
            }
        due_date = datetime.strptime(due_at, "%Y-%m-%d").date()
        is_due = bool(as_of_date and due_date <= as_of_date)
        is_overdue = bool(as_of_date and due_date < as_of_date)
        if is_overdue:
            label = f"{window} 已成熟，等待 outcome 落盘"
        elif is_due:
            label = f"{window} 今天成熟"
        else:
            label = f"等待 {window} 成熟"
        return {
            "maturity_due_at": due_at,
            "maturity_window": window,
            "maturity_label": label,
            "is_overdue": is_overdue,
            "is_due": is_due,
            "missing_due_date": False,
        }

    latest_outcome = _latest_outcome_event(outcome_events)
    due_at = str((latest_outcome or {}).get("as_of_trade_date") or trade_date or "")
    latest_window = str((latest_outcome or {}).get("window") or "T+5")
    return {
        "maturity_due_at": due_at or None,
        "maturity_window": latest_window,
        "maturity_label": "T+5 已完成，样本可纳入规则学习",
        "is_overdue": False,
        "is_due": True,
        "missing_due_date": False,
    }


def _review_status_for_record(
    *,
    record: Mapping[str, Any],
    latest_label: str,
    action: str,
    execution_events: list[Mapping[str, Any]],
    has_outcome: bool,
    missing_due_date: bool,
) -> str:
    status_state = str((record.get("status") or {}).get("state") or "")
    if latest_label == "data_issue" or missing_due_date:
        return "blocked_data"
    if latest_label in {"invalidated", "execution_gap", "missed_opportunity"}:
        return "ready_review"
    if status_state == "superseded":
        return "ready_review"
    if has_outcome and latest_label in {"validated", "avoided_loss"}:
        return "reviewed"
    if has_outcome:
        return "low_priority"
    if _action_requires_execution(action) and not execution_events:
        return "pending_execution"
    return "pending_outcome"


def _missing_fields_for_record(
    *,
    record: Mapping[str, Any],
    review_status: str,
    latest_label: str,
    action: str,
    execution_events: list[Mapping[str, Any]],
    has_outcome: bool,
    maturity: Mapping[str, Any],
) -> list[str]:
    missing: list[str] = []
    stock = record.get("stock") or {}
    evidence = record.get("evidence_snapshot") or {}
    if not stock.get("code"):
        missing.append("stock.code")
    if not record.get("trade_date"):
        missing.append("trade_date")
    if not has_outcome:
        missing.append("outcome_events")
    if _action_requires_execution(action) and not execution_events:
        missing.append("execution_events")
    if maturity.get("missing_due_date"):
        missing.append("maturity_due_at")
    if latest_label == "data_issue" or review_status == "blocked_data":
        missing.append("market_data")
    if evidence.get("readiness_ready") is False and evidence.get("blockers"):
        missing.append("ready_evidence")

    deduped: list[str] = []
    seen: set[str] = set()
    for item in missing:
        if item and item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped


def _calibration_action_for_record(
    *,
    review_status: str,
    latest_label: str,
    is_high_confidence: bool,
    is_overdue: bool,
) -> tuple[str, str, str]:
    if review_status == "blocked_data":
        action = "fix_data"
        reason = "结果无法用于学习，先修复行情/成熟日/来源数据。"
    elif review_status == "pending_execution":
        action = "fix_execution"
        reason = "判断与执行链路脱节，优先补齐成交/未成交原因。"
        if is_overdue:
            reason = "样本已过成熟日，先补齐执行记录；若只缺 outcome，立即补跑 outcome evaluator。"
    elif latest_label == "execution_gap":
        action = "fix_execution"
        reason = "判断与执行链路脱节，优先补齐成交/未成交原因。"
    elif latest_label == "invalidated":
        action = "investigate_pattern"
        reason = "判断被结果否定，需要先完成归因；单条样本不能直接收紧规则。"
    elif latest_label == "missed_opportunity":
        action = "investigate_pattern"
        reason = "谨慎动作错过机会，需要先完成归因；单条样本不能直接放宽规则。"
    elif review_status == "ready_review":
        action = "investigate_pattern"
        reason = "样本已成熟且值得人工归因，先确认是否为重复模式。"
    elif review_status in _PENDING_REVIEW_STATUSES:
        if is_overdue:
            action = "run_outcome_evaluator"
            reason = "样本已过成熟日但 outcome 未落盘，先补跑 outcome evaluator，让学习闭环继续走。"
        else:
            action = "wait_for_sample"
            reason = "样本尚未形成完整 outcome，先等待或运行 outcome evaluator。"
    elif review_status == "low_priority":
        action = "wait_for_sample"
        reason = "结果信号仍在中性带，暂不因单样本改规则。"
    else:
        action = "keep_rule"
        reason = "当前样本没有显示规则偏移，继续观察即可。"
    return action, _CALIBRATION_ACTION_LABELS[action], reason


def _quality_axes_for_record(
    *,
    record: Mapping[str, Any],
    review_status: str,
    latest_label: str,
    action: str,
    execution_events: list[Mapping[str, Any]],
    is_overdue: bool,
) -> dict[str, Any]:
    if latest_label in {"validated", "avoided_loss", "execution_gap"}:
        judgment = _axis("good", 82 if latest_label != "execution_gap" else 76, "positive", "结果支持原始判断方向。")
    elif latest_label in {"invalidated", "missed_opportunity"}:
        judgment = _axis("weak", 28, "risk", "结果与原始判断方向相反，需要归因。")
    elif latest_label == "data_issue" or review_status == "blocked_data":
        judgment = _axis("blocked", 0, "warning", "数据缺口阻塞判断质量评价。")
    elif latest_label == "inconclusive":
        judgment = _axis("inconclusive", 50, "watch", "收益落在中性区间，不足以改规则。")
    else:
        judgment = _axis("pending", 45, "watch", "尚未形成 outcome，判断质量暂不可评价。")

    statuses = {
        str(event.get("status") or "").strip().lower()
        for event in execution_events
    }
    if latest_label == "execution_gap":
        execution = _axis("gap", 22, "risk", "建议有效但没有形成对应执行。")
    elif "filled" in statuses:
        execution = _axis("aligned", 82, "positive", "已记录成交，执行链路可评价。")
    elif statuses & {"no_fill", "skip"}:
        execution = _axis("explicit_skip", 58, "watch", "已记录未执行原因，可用于执行归因。")
    elif _action_requires_execution(action):
        execution = _axis("missing", 35, "warning", "动作需要执行记录，但当前缺少 fill/no_fill。")
    else:
        execution = _axis("not_required", 68, "info", "该动作不强制要求成交记录。")

    if review_status in _READY_REVIEW_STATUSES:
        learning = _axis("needs_review", 42, "warning", "样本已能触发学习动作，等待人工归因。")
    elif is_overdue:
        learning = _axis("overdue", 30, "risk", "样本成熟但 outcome 未落盘，学习闭环停住了。")
    elif review_status in _PENDING_REVIEW_STATUSES:
        learning = _axis("collecting", 55, "watch", "正在等待 outcome 或执行信息成熟。")
    elif review_status == "reviewed":
        learning = _axis("learned", 78, "positive", "样本已纳入规则质量统计。")
    else:
        learning = _axis("low_signal", 50, "watch", "当前结果信号不足，避免过拟合。")

    return {
        "judgment_quality": judgment,
        "execution_quality": execution,
        "learning_quality": learning,
    }


def _priority_for_record(
    *,
    record: Mapping[str, Any],
    review_status: str,
    latest_label: str,
    is_high_confidence: bool,
    is_overdue: bool,
    action: str,
    execution_events: list[Mapping[str, Any]],
    pattern_count: int,
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    if latest_label == "invalidated":
        score += 45
        reasons.append("判断被行情否定")
        if is_high_confidence:
            score += 12
            reasons.append("高信心样本失效")
    elif latest_label == "execution_gap":
        score += 50
        reasons.append("出现 execution gap")
    elif latest_label == "missed_opportunity":
        score += 42
        reasons.append("可能错过机会")
    elif latest_label == "data_issue" or review_status == "blocked_data":
        score += 34
        reasons.append("数据缺口阻塞学习")

    if str((record.get("status") or {}).get("state") or "") == "superseded":
        score += 28
        reasons.append("判断已被后续建议替代")

    if is_overdue:
        score += 38
        reasons.append("pending 已过成熟日")

    if review_status == "pending_execution":
        score += 22
        reasons.append("缺少执行记录")
    elif _action_requires_execution(action) and not execution_events:
        score += 10
        reasons.append("动作需要执行证据")

    if pattern_count >= 2:
        score += 14
        reasons.append("同链路/动作重复失败")

    if _record_has_real_position_context(record, execution_events):
        score += 8
        reasons.append("涉及真实仓位或执行")

    if review_status == "reviewed":
        score += 8
        reasons.append("已完成 outcome，可纳入统计")
    elif review_status == "low_priority":
        score += 5
        reasons.append("低信号样本，避免过拟合")
    elif not reasons:
        score += 12
        reasons.append("等待样本成熟")

    return min(score, 100), reasons


def _decision_learning_card(
    record: Mapping[str, Any],
    *,
    as_of: str,
    pattern_counts: Mapping[tuple[str, str], int],
) -> dict[str, Any]:
    source = record.get("source") or {}
    recommendation = record.get("recommendation") or {}
    evidence = record.get("evidence_snapshot") or {}
    action = str(recommendation.get("action") or "unknown").strip().lower()
    lane = str(source.get("lane") or "unknown")
    outcome_events = list(record.get("outcome_events") or [])
    execution_events = list(record.get("execution_events") or [])
    latest_outcome = _latest_outcome_event(outcome_events)
    latest_label = _latest_outcome_label(latest_outcome)
    has_outcome = latest_outcome is not None
    maturity = _next_maturity(record, as_of=as_of)
    review_status = _review_status_for_record(
        record=record,
        latest_label=latest_label,
        action=action,
        execution_events=execution_events,
        has_outcome=has_outcome,
        missing_due_date=bool(maturity.get("missing_due_date")),
    )
    missing_fields = _missing_fields_for_record(
        record=record,
        review_status=review_status,
        latest_label=latest_label,
        action=action,
        execution_events=execution_events,
        has_outcome=has_outcome,
        maturity=maturity,
    )
    is_high_confidence = bool(evidence.get("readiness_ready")) and not (evidence.get("blockers") or [])
    is_overdue = bool(maturity.get("is_overdue")) and not has_outcome
    pattern_count = int(pattern_counts.get((lane, action), 0))
    priority_score, priority_reasons = _priority_for_record(
        record=record,
        review_status=review_status,
        latest_label=latest_label,
        is_high_confidence=is_high_confidence,
        is_overdue=is_overdue,
        action=action,
        execution_events=execution_events,
        pattern_count=pattern_count,
    )
    calibration_action, action_label, action_reason = _calibration_action_for_record(
        review_status=review_status,
        latest_label=latest_label,
        is_high_confidence=is_high_confidence,
        is_overdue=is_overdue,
    )
    review_reason_key, review_reason = _review_reason(record, latest_label)
    if review_status in _PENDING_REVIEW_STATUSES:
        review_reason_key = review_status
        review_reason = "等待 outcome / execution 成熟"
    elif review_status == "reviewed":
        review_reason_key = "reviewed"
        review_reason = "样本已完成评价，当前不需要优先复盘"
    elif review_status == "low_priority":
        review_reason_key = "low_priority"
        review_reason = "结果信号不足，暂不推动规则校准"

    card = _decision_summary_card(record)
    latest_execution_status = str((card.get("latest_execution") or {}).get("status") or "")
    if not latest_execution_status:
        latest_execution_status = "missing" if _action_requires_execution(action) else "not_required"

    card.update(
        {
            "review_status": review_status,
            "review_reason": review_reason,
            "review_reason_key": review_reason_key,
            "maturity_due_at": maturity.get("maturity_due_at"),
            "maturity_label": maturity.get("maturity_label"),
            "maturity_window": maturity.get("maturity_window"),
            "missing_fields": missing_fields,
            "is_overdue": is_overdue,
            "next_action_label": action_label,
            "next_action_reason": action_reason,
            "quality_axes": _quality_axes_for_record(
                record=record,
                review_status=review_status,
                latest_label=latest_label,
                action=action,
                execution_events=execution_events,
                is_overdue=is_overdue,
            ),
            "priority_score": priority_score,
            "priority_label": _priority_label(priority_score),
            "priority_reasons": priority_reasons,
            "calibration_action": calibration_action,
            "calibration_action_label": action_label,
            "calibration_action_reason": action_reason,
            "outcome_status": latest_label or "pending",
            "outcome_tone": _latest_outcome_tone(latest_outcome),
            "execution_status": latest_execution_status,
            "maturity": dict(maturity),
        }
    )
    return card


def _learning_card_sort_key(item: Mapping[str, Any]) -> tuple[int, str, str]:
    return (
        int(item.get("priority_score") or 0),
        str(item.get("trade_date") or ""),
        str(item.get("decision_id") or ""),
    )


def _build_review_workbench(
    records: list[dict[str, Any]],
    *,
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    ready_count = sum(1 for item in records if item.get("review_status") == "ready_review")
    blocked_count = sum(1 for item in records if item.get("review_status") == "blocked_data")
    pending_count = sum(1 for item in records if item.get("review_status") in _PENDING_REVIEW_STATUSES)
    overdue_count = sum(1 for item in records if item.get("is_overdue"))
    today_queue = [
        item for item in records
        if item.get("review_status") in _READY_REVIEW_STATUSES
        or item.get("is_overdue")
        or item.get("review_status") == "pending_execution"
    ]
    today_queue.sort(key=_learning_card_sort_key, reverse=True)
    top = today_queue[0] if today_queue else None

    if errors:
        state = "data_blocked"
        next_best_action = "先修复 ledger 文件解析错误，避免学习样本缺失。"
    elif ready_count or blocked_count:
        state = "needs_review"
        next_best_action = str((top or {}).get("next_action_label") or "先处理最高优先级复盘样本。")
    elif overdue_count:
        state = "outcome_overdue"
        next_best_action = "补跑 outcome evaluator，让已成熟样本进入复盘。"
    elif pending_count:
        state = "collecting_evidence"
        next_best_action = "等待样本成熟，同时补齐缺失执行记录。"
    elif records:
        state = "stable_learning"
        next_best_action = "保持当前规则，继续积累样本，避免单点过拟合。"
    else:
        state = "no_samples"
        next_best_action = "先捕获今天的观察、判断和执行记录。"

    top_reason = "暂无优先风险"
    if top:
        reasons = top.get("priority_reasons") or []
        if isinstance(reasons, list) and reasons:
            top_reason = str(reasons[0])
        else:
            top_reason = str(top.get("review_reason") or top_reason)

    return {
        "today_queue_count": len(today_queue),
        "ready_review_count": ready_count,
        "blocked_data_count": blocked_count,
        "pending_count": pending_count,
        "overdue_count": overdue_count,
        "top_priority_reason": top_reason,
        "system_learning_state": state,
        "next_best_action": next_best_action,
        "top_priority_decision_id": top.get("decision_id") if top else None,
    }


def _suggestion_card(
    *,
    kind: str,
    tone: str,
    title: str,
    summary: str,
    calibration_action: str,
    sample_size: int = 0,
    action_reason: str = "",
) -> dict[str, Any]:
    sample_size = max(0, int(sample_size or 0))
    insufficient_sample = sample_size < 5 and calibration_action not in {
        "fix_data",
        "fix_execution",
        "run_outcome_evaluator",
    }
    return {
        "kind": kind,
        "tone": tone,
        "title": title,
        "summary": summary,
        "calibration_action": calibration_action,
        "action_label": _CALIBRATION_ACTION_LABELS.get(calibration_action, calibration_action),
        "action_reason": action_reason or summary,
        "evidence_strength": _evidence_strength(sample_size),
        "sample_size": sample_size,
        "insufficient_sample": insufficient_sample,
    }


def _calibration_suggestion_cards(
    *,
    by_lane: list[dict[str, Any]],
    by_action: list[dict[str, Any]],
    needs_review_count: int,
    top_review_reasons: list[str],
    data_issue_count: int,
    pending_count: int,
    overdue_count: int,
) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []

    weak_lane = next(
        (
            item for item in by_lane
            if int(item.get("evaluated") or 0) >= 2 and float(item.get("invalidated_rate") or 0) >= 35
        ),
        None,
    )
    if weak_lane:
        cards.append(
            _suggestion_card(
                kind="lane_invalidated",
                tone="risk",
                title=f"{weak_lane['label']} 近期失误偏高",
                summary=(
                    f"已评估 {weak_lane['evaluated']} 条，invalidated "
                    f"{weak_lane['invalidated_rate']}%。建议先复查该链路阈值和证据质量。"
                ),
                calibration_action=(
                    "tighten_rule" if int(weak_lane.get("evaluated") or 0) >= 5
                    else "investigate_pattern"
                ),
                sample_size=int(weak_lane.get("evaluated") or 0),
                action_reason="失败率偏高，先确认是否为稳定模式，再决定是否收紧规则。",
            )
        )

    weak_action = next(
        (
            item for item in by_action
            if int(item.get("evaluated") or 0) >= 2 and float(item.get("review_rate") or 0) >= 40
        ),
        None,
    )
    if weak_action:
        cards.append(
            _suggestion_card(
                kind="action_review",
                tone="warning",
                title=f"{weak_action['label']} 动作需要校准",
                summary=(
                    f"该动作 {weak_action['review_rate']}% 进入复盘池。建议检查触发条件是否过宽或过窄。"
                ),
                calibration_action=(
                    "add_guardrail" if int(weak_action.get("evaluated") or 0) >= 5
                    else "investigate_pattern"
                ),
                sample_size=int(weak_action.get("evaluated") or 0),
                action_reason="同一动作进入复盘池比例偏高，需要定位触发条件还是执行链路问题。",
            )
        )

    if data_issue_count:
        cards.append(
            _suggestion_card(
                kind="data_quality",
                tone="warning",
                title="先处理数据问题",
                summary=f"当前窗口有 {data_issue_count} 条 data_issue，复盘前应优先确认行情和来源新鲜度。",
                calibration_action="fix_data",
                sample_size=data_issue_count,
                action_reason="数据问题会污染命中率，先修复再讨论规则。",
            )
        )

    if overdue_count:
        cards.append(
            _suggestion_card(
                kind="outcome_overdue",
                tone="risk",
                title="补跑 outcome evaluator",
                summary=f"当前窗口有 {overdue_count} 条样本已过成熟日但 outcome 未落盘，先让结果评估补齐证据。",
                calibration_action="run_outcome_evaluator",
                sample_size=overdue_count,
                action_reason="成熟样本缺 outcome 会卡住学习闭环；先补跑评估，再决定是否复盘或调规则。",
            )
        )

    if needs_review_count:
        reason_text = " / ".join(
            _REVIEW_REASON_LABELS.get(reason, reason)
            for reason in top_review_reasons[:2]
        ) or "复盘池"
        cards.append(
            _suggestion_card(
                kind="review_queue",
                tone="info",
                title="先看复盘池",
                summary=f"有 {needs_review_count} 条决策值得人工复盘，建议先看 {reason_text}。",
                calibration_action="investigate_pattern",
                sample_size=needs_review_count,
                action_reason="先做归因，再决定 keep / tighten / loosen，避免直接过拟合。",
            )
        )

    future_pending_count = max(0, pending_count - overdue_count)
    if future_pending_count and not cards:
        cards.append(
            _suggestion_card(
                kind="pending",
                tone="watch",
                title="等待样本成熟",
                summary=f"当前窗口仍有 {future_pending_count} 条待评估，先等 T+N outcome 落盘后再校准。",
                calibration_action="wait_for_sample",
                sample_size=future_pending_count,
                action_reason="样本未成熟时不要改规则，先让 outcome / execution 补齐。",
            )
        )

    if not cards:
        cards.append(
            _suggestion_card(
                kind="steady",
                tone="positive",
                title="暂无明显校准压力",
                summary="当前窗口没有突出失败簇，继续积累样本并观察 lane / action 分布。",
                calibration_action="keep_rule",
                sample_size=0,
                action_reason="没有足够反证时，默认保留规则并继续观察。",
            )
        )

    return cards[:4]


def build_calibration_review(
    *,
    window_days: int = 20,
    as_of: str | None = None,
    limit: int = 12,
) -> dict[str, Any]:
    """Aggregate the ledger into a small review-and-calibration brief.

    This is intentionally a product-facing projection, not a new storage
    model.  It scans the append-only decisions and answers the operator's
    next question: which decisions deserve review, and which lane/action
    looks suspicious enough to inspect before changing rules.
    """

    days = max(1, int(window_days) if isinstance(window_days, int) else 20)
    review_limit = max(1, min(int(limit) if isinstance(limit, int) else 12, 100))
    as_of_norm = _resolve_as_of(as_of)
    try:
        end = datetime.strptime(as_of_norm, "%Y-%m-%d").date()
    except ValueError:
        end = datetime.now().date()
        as_of_norm = end.strftime("%Y-%m-%d")
    start = end - timedelta(days=days)
    from_date = start.strftime("%Y-%m-%d")

    records, errors = scan_all_decisions()
    review_cases = _read_review_cases_file()
    review_cases_by_decision = _review_cases_by_decision(review_cases)
    in_window = [
        record for record in records
        if from_date <= str(record.get("trade_date") or "") <= as_of_norm
    ]
    in_window.sort(
        key=lambda r: (
            str(r.get("trade_date") or ""),
            str(r.get("decision_id") or ""),
        ),
        reverse=True,
    )

    overall = _empty_group("overall")
    by_lane_map: dict[str, dict[str, Any]] = {}
    by_action_map: dict[str, dict[str, Any]] = {}
    pattern_counts: dict[tuple[str, str], int] = {}

    for record in in_window:
        source = record.get("source") or {}
        recommendation = record.get("recommendation") or {}
        latest_outcome = _latest_outcome_event(record.get("outcome_events") or [])
        latest_label = _latest_outcome_label(latest_outcome)
        status_state = str((record.get("status") or {}).get("state") or "")
        if latest_label in {"invalidated", "execution_gap", "missed_opportunity"} or status_state == "superseded":
            key = (
                str(source.get("lane") or "unknown"),
                str(recommendation.get("action") or "unknown"),
            )
            pattern_counts[key] = pattern_counts.get(key, 0) + 1

    learning_records: list[dict[str, Any]] = []
    review_items: list[dict[str, Any]] = []

    for record in in_window:
        source = record.get("source") or {}
        recommendation = record.get("recommendation") or {}
        outcome_events = record.get("outcome_events") or []
        latest_outcome = _latest_outcome_event(outcome_events)
        latest_label = _latest_outcome_label(latest_outcome)
        has_outcome = latest_outcome is not None

        lane = str(source.get("lane") or "unknown")
        action = str(recommendation.get("action") or "unknown")
        lane_group = by_lane_map.setdefault(lane, _empty_group(lane))
        action_group = by_action_map.setdefault(action, _empty_group(action))
        status_state = str((record.get("status") or {}).get("state") or "")
        _bump_group(
            overall,
            latest_label=latest_label,
            has_outcome=has_outcome,
            status_state=status_state,
        )
        _bump_group(
            lane_group,
            latest_label=latest_label,
            has_outcome=has_outcome,
            status_state=status_state,
        )
        _bump_group(
            action_group,
            latest_label=latest_label,
            has_outcome=has_outcome,
            status_state=status_state,
        )

        card = _decision_learning_card(
            record,
            as_of=as_of_norm,
            pattern_counts=pattern_counts,
        )
        card = _apply_review_case_to_card(
            card,
            review_cases_by_decision.get(str(record.get("decision_id") or "")),
        )
        learning_records.append(card)
        if card.get("review_status") in _READY_REVIEW_STATUSES:
            review_items.append(card)

    by_lane = sorted(
        (_group_rates(item) for item in by_lane_map.values()),
        key=lambda item: (int(item.get("review_needed") or 0), int(item.get("total") or 0)),
        reverse=True,
    )
    by_action = sorted(
        (_group_rates(item) for item in by_action_map.values()),
        key=lambda item: (int(item.get("review_needed") or 0), int(item.get("total") or 0)),
        reverse=True,
    )
    overall_view = _group_rates(overall)
    review_items.sort(
        key=lambda item: _REVIEW_REASON_PRIORITY.get(
            str(item.get("review_reason_key") or ""),
            99,
        ),
    )
    review_items.sort(key=_learning_card_sort_key, reverse=True)
    learning_records.sort(key=_learning_card_sort_key, reverse=True)
    needs_review = review_items[:review_limit]
    pending_reviews = [
        item for item in learning_records
        if item.get("review_status") in _PENDING_REVIEW_STATUSES
    ][:review_limit]
    ready_reviews = [
        item for item in learning_records
        if item.get("review_status") == "ready_review"
    ][:review_limit]
    review_queue = [
        item for item in learning_records
        if item.get("review_status") in _READY_REVIEW_STATUSES
        or item.get("review_status") in _PENDING_REVIEW_STATUSES
    ][:review_limit]
    workbench = _build_review_workbench(learning_records, errors=errors)
    shadow_calibration = build_shadow_calibration_summary()
    top_review_reasons: list[str] = []
    for item in review_items:
        reason = str(item.get("review_reason_key") or "")
        if reason and reason not in top_review_reasons:
            top_review_reasons.append(reason)

    return {
        "as_of": as_of_norm,
        "window_days": days,
        "from_date": from_date,
        "to_date": as_of_norm,
        "overall": overall_view,
        "by_lane": by_lane,
        "by_action": by_action,
        "review_workbench": workbench,
        "review_records": learning_records,
        "review_queue": review_queue,
        "ready_reviews": ready_reviews,
        "pending_reviews": pending_reviews,
        "needs_review": needs_review,
        "needs_review_count": len(review_items),
        "reviewed_case_count": len(review_cases_by_decision),
        "review_case_patterns": build_review_case_patterns(cases=review_cases).get("patterns", []),
        "review_case_summary": {
            "total": len(review_cases),
            "attributed": len([case for case in review_cases if case.get("primary_cause")]),
            "patterns": build_review_case_patterns(cases=review_cases).get("count", 0),
        },
        "shadow_calibration": shadow_calibration,
        "suggestion_cards": _calibration_suggestion_cards(
            by_lane=by_lane,
            by_action=by_action,
            needs_review_count=len(review_items),
            top_review_reasons=top_review_reasons,
            data_issue_count=int(overall_view.get("data_issue") or 0),
            pending_count=int(overall_view.get("pending") or 0),
            overdue_count=int(workbench.get("overdue_count") or 0),
        ),
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
    root.  This path is the canonical runtime location.  The directory
    is *not* created here -- writers call
    :func:`write_status`, readers handle missing files.
    """

    key = str(kind or "").strip().lower()
    if key not in STATUS_KINDS:
        raise DecisionLedgerError(
            f"unknown status kind: {kind!r}; expected one of {STATUS_KINDS}"
        )
    return default_ledger_root() / "status" / f"{key}_latest.json"


def _status_read_paths(kind: str) -> list[Path]:
    key = str(kind or "").strip().lower()
    if key not in STATUS_KINDS:
        raise DecisionLedgerError(
            f"unknown status kind: {kind!r}; expected one of {STATUS_KINDS}"
        )
    return [root / "status" / f"{key}_latest.json" for root in _ledger_read_roots()]


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

    for path in _status_read_paths(kind):
        if not path.exists():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(raw, Mapping):
            return None
        return dict(raw)
    return None


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
        for path in _status_read_paths(kind):
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
        "storage": ledger_storage_status(),
        "learning_loop": build_rule_learning_loop(records, errors=errors, as_of=today_str),
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
