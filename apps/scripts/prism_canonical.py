#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0.0"

BASE_DIR = Path(__file__).resolve().parents[1]
PACKAGES_ROOT = BASE_DIR.parent / "packages"
STOCK_ANALYZER_ROOT = BASE_DIR.parent / "stock-analyzer"
STOCK_SCREENER_ROOT = BASE_DIR.parent / "stock-screener"

if str(PACKAGES_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGES_ROOT))
if str(STOCK_ANALYZER_ROOT) not in sys.path:
    sys.path.insert(0, str(STOCK_ANALYZER_ROOT))

from screener.capital_flow_contract import UNIT_YUAN, normalize_capital_flow_payload
from screener.parameters import build_intraday_observation_contract
from watchlist_registry import load_active_watchlist_codes

WATCHLIST_SNAPSHOT_DIR = STOCK_ANALYZER_ROOT / "data" / "daily_snapshots"
SCREENER_DATA_DIR = STOCK_SCREENER_ROOT / "data"
CURRENT_SCREENER_DATA_DIR = PACKAGES_ROOT / "data"
SCREENER_DATA_DIRS = (CURRENT_SCREENER_DATA_DIR, SCREENER_DATA_DIR)
COMMAND_BRIEF_DIR = BASE_DIR / "data" / "command_brief"
RESEARCH_REPORTS_DIR = STOCK_SCREENER_ROOT / "data" / "research_backfill" / "reports"

QUALITY_PATTERNS = {
    "watchlist": STOCK_ANALYZER_ROOT / "data" / "quality_gate_watchlist_*.json",
    "aggressive": STOCK_SCREENER_ROOT / "data" / "quality_gate_*.json",
    "midday_confirmation": STOCK_SCREENER_ROOT / "data" / "quality_gate_midday_*.json",
}


def load_json(path: Path | None) -> dict[str, Any]:
    if not path or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def batch_stamp(value: str | None) -> str | None:
    dt = parse_ts(value)
    return dt.strftime("%Y-%m-%dT%H:%M:%S") if dt else None


def build_id(prefix: str, value: str | None, fallback: str | None = None) -> str:
    stamp = batch_stamp(value)
    if stamp:
        return f"{prefix}:{stamp}"
    return f"{prefix}:{fallback}" if fallback else prefix


def safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def int_from_text(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).replace(",", "").strip()
    if not text or text == "-":
        return None
    try:
        return int(text)
    except ValueError:
        return None


def pct_from_text(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).replace("%", "").replace(",", "").strip()
    if not text or text == "-":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def build_confirmation_observation_contract(raw: dict[str, Any], status: str) -> dict[str, Any]:
    return build_intraday_observation_contract(
        raw,
        status=status,
        active_theme=bool(raw.get("active_theme")),
        flow_today_yi=raw.get("flow_today_yi"),
    )


def stable_artifact_path(path_value: str | None) -> str | None:
    if not path_value:
        return None
    path = Path(path_value).expanduser()
    if path.name in {"ai_screening_result.json", "midday_verification_result.json"}:
        return None
    return str(path)


def mutable_alias_path(path_value: str | None) -> str | None:
    if not path_value:
        return None
    path = Path(path_value).expanduser()
    if path.name in {"ai_screening_result.json", "midday_verification_result.json"}:
        return str(path)
    return None


def latest_matching(pattern: Path, exclude_tokens: tuple[str, ...] = ()) -> Path | None:
    files = list(pattern.parent.glob(pattern.name))
    if exclude_tokens:
        files = [path for path in files if not any(token in path.name for token in exclude_tokens)]

    def sort_key(path: Path) -> tuple[datetime, float, str]:
        name_stamp = re.search(r"(\d{4}-\d{2}-\d{2})(?:[_-](\d{2})-(\d{2})(?:-(\d{2}))?)?", path.stem)
        if name_stamp:
            date_part, hour, minute, second = name_stamp.groups()
            parsed = parse_ts(
                f"{date_part} {hour or '00'}:{minute or '00'}:{second or '00'}"
            )
            if parsed:
                return (parsed, path.stat().st_mtime, path.name)
        return (datetime.fromtimestamp(path.stat().st_mtime), path.stat().st_mtime, path.name)

    files.sort(key=sort_key, reverse=True)
    return files[0] if files else None


def resolve_watchlist_snapshot_path(path: str | None = None, trade_date: str | None = None) -> Path | None:
    if path:
        candidate = Path(path).expanduser()
        return candidate if candidate.exists() else None
    if trade_date:
        candidate = WATCHLIST_SNAPSHOT_DIR / f"{trade_date}.json"
        if candidate.exists():
            return candidate
    return latest_matching(WATCHLIST_SNAPSHOT_DIR / "*.json")


def resolve_screening_batch_path(path: str | None = None) -> Path | None:
    if path:
        candidate = Path(path).expanduser()
        return candidate if candidate.exists() else None
    for data_dir in SCREENER_DATA_DIRS:
        current = data_dir / "ai_screening_result.json"
        if current.exists():
            return current
    for data_dir in SCREENER_DATA_DIRS:
        history = latest_matching(data_dir / "ai_history" / "ai_screening_*.json")
        if history:
            return history
    return None


def resolve_confirmation_path(path: str | None = None) -> Path | None:
    if path:
        candidate = Path(path).expanduser()
        return candidate if candidate.exists() else None
    for data_dir in SCREENER_DATA_DIRS:
        current = data_dir / "midday_verification_result.json"
        if current.exists():
            return current
    for data_dir in SCREENER_DATA_DIRS:
        history = latest_matching(data_dir / "midday_verification_*.json")
        if history:
            return history
    return None


def resolve_decision_brief_path(path: str | None = None) -> Path | None:
    if path:
        candidate = Path(path).expanduser()
        return candidate if candidate.exists() else None
    return latest_matching(COMMAND_BRIEF_DIR / "prism_command_brief_*.json")


def action_rank(action: str | None) -> int:
    text = action or ""
    if any(keyword in text for keyword in ("回避", "清仓", "逢高减仓")):
        return 0
    if "减仓" in text or "偏空" in text:
        return 1
    if "观望" in text:
        return 2
    if any(keyword in text for keyword in ("轻仓跟踪", "偏多", "买入")):
        return 3
    return 2


def watchlist_group(stock: dict[str, Any]) -> str:
    rank = action_rank(stock.get("action"))
    if rank <= 1:
        return "priority"
    if rank >= 3 and not (stock.get("hard_flags") or []):
        return "follow"
    return "observe"


def normalize_watchlist_stock(code: str, raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": code,
        "name": raw.get("name") or code,
        "action": raw.get("action") or "观望",
        "position": raw.get("position") or "待定",
        "action_rank": action_rank(raw.get("action")),
        "price_as_of": raw.get("price_as_of"),
        "flow_as_of": raw.get("flow_as_of"),
        "rule_snapshot": {
            "tech_base": raw.get("tech_base"),
            "flow_base": raw.get("flow_base"),
            "event_base": raw.get("event_base"),
            "signal": raw.get("signal"),
            "score": safe_float(raw.get("score")),
            "score_kind": raw.get("score_kind"),
            "flow_unconfirmed": bool(raw.get("flow_unconfirmed", False)),
        },
        "trade_levels": {
            "support": safe_float(raw.get("support")),
            "resistance": safe_float(raw.get("resistance")),
            "stop_loss": safe_float(raw.get("stop_loss")),
        },
        "intraday_triggers": raw.get("intraday_triggers") or [],
        "hard_flags": raw.get("hard_flags") or [],
        "positives": raw.get("positives") or [],
        "watch_points": raw.get("watch_points") or [],
    }


def load_watchlist_snapshot(path: str | None = None, trade_date: str | None = None, code: str | None = None) -> dict[str, Any]:
    snapshot_path = resolve_watchlist_snapshot_path(path=path, trade_date=trade_date)
    if not snapshot_path:
        raise FileNotFoundError("watchlist snapshot not found")

    raw = load_json(snapshot_path)
    stocks = raw.get("stocks") or {}
    active_codes = set(load_active_watchlist_codes())
    target_code = str(code or "").strip()
    target_stock = stocks.get(target_code) if target_code else None
    if active_codes:
        stocks = {stock_code: item for stock_code, item in stocks.items() if stock_code in active_codes}
        # Allow direct detail views to keep rendering the last known snapshot,
        # even when the active watchlist has already rotated away from that code.
        if target_code and target_stock is not None and target_code not in stocks:
            stocks[target_code] = target_stock
    normalized = [normalize_watchlist_stock(stock_code, item or {}) for stock_code, item in stocks.items()]
    normalized.sort(key=lambda item: (action_rank(item.get("action")), item.get("code", "")))

    if code:
        target = code.strip()
        normalized = [item for item in normalized if item.get("code") == target]

    priority = [item["code"] for item in normalized if watchlist_group(item) == "priority"]
    follow = [item["code"] for item in normalized if watchlist_group(item) == "follow"]
    observe = [item["code"] for item in normalized if watchlist_group(item) == "observe"]

    return {
        "entity": "watchlist_snapshot",
        "schema_version": SCHEMA_VERSION,
        "snapshot_id": build_id("watchlist_snapshot", raw.get("generated_at"), raw.get("date")),
        "trade_date": raw.get("date") or trade_date,
        "generated_at": raw.get("generated_at"),
        "snapshot_path": str(snapshot_path.resolve()),
        "price_basis": raw.get("price_basis"),
        "flow_basis": raw.get("flow_basis"),
        "tech_basis": raw.get("tech_basis"),
        "stock_count": len(normalized),
        "priority_codes": priority,
        "follow_codes": follow,
        "observe_codes": observe,
        "stocks": normalized,
    }


_WATCHLIST_SNAPSHOT_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.json$")


def resolve_previous_watchlist_snapshot_path(reference_path: Path) -> Path | None:
    """Return the largest dated snapshot strictly older than ``reference_path``.

    Used by the watchlist page to anchor a day-over-day diff. Files whose
    name does not match ``YYYY-MM-DD.json`` are ignored — the resolver
    refuses to guess at a "previous" from arbitrary file names.
    """

    if not reference_path:
        return None
    ref = Path(reference_path)
    match = _WATCHLIST_SNAPSHOT_DATE_RE.match(ref.name)
    if not match:
        return None
    reference_date = match.group(1)
    parent = ref.parent
    if not parent.exists():
        return None

    candidates: list[tuple[str, Path]] = []
    for entry in parent.iterdir():
        if not entry.is_file():
            continue
        m = _WATCHLIST_SNAPSHOT_DATE_RE.match(entry.name)
        if not m:
            continue
        date = m.group(1)
        if date < reference_date:
            candidates.append((date, entry))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[-1][1]


_GROUP_RANK = {"observe": 0, "follow": 1, "priority": 2}


def _index_by_code(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not payload:
        return {}
    return {item.get("code"): item for item in (payload.get("stocks") or []) if item.get("code")}


def _stock_group_label(payload: dict[str, Any] | None, code: str) -> str:
    if not payload:
        return "observe"
    if code in (payload.get("priority_codes") or []):
        return "priority"
    if code in (payload.get("follow_codes") or []):
        return "follow"
    return "observe"


def _trade_level(stock: dict[str, Any], field: str) -> float | None:
    levels = stock.get("trade_levels") or {}
    value = levels.get(field)
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def diff_watchlist_snapshots(
    today: dict[str, Any],
    previous: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compute a day-over-day diff between two normalized watchlist payloads.

    Both inputs are shaped like :func:`load_watchlist_snapshot` output —
    a dict with ``stocks`` (list of normalized stock dicts), plus
    ``priority_codes``/``follow_codes``/``observe_codes``.

    The result is auditable and JSON-serializable: each change carries
    the stock code, name, the field that moved, and before/after values.
    Code orderings are sorted alphabetically so callers asking for the
    same diff always get the same JSON.

    Pass ``previous=None`` when there is no prior snapshot — the result
    is still well-formed (empty change buckets, ``unchanged_count`` reflects
    today's roster).
    """

    if previous is None:
        return {
            "today_trade_date": (today or {}).get("trade_date"),
            "previous_trade_date": None,
            "added": [],
            "removed": [],
            "action_changes": [],
            "group_changes": [],
            "boundary_changes": [],
            "signal_changes": [],
            "unchanged_count": len(_index_by_code(today)),
        }

    today_index = _index_by_code(today)
    prev_index = _index_by_code(previous)

    today_codes = set(today_index)
    prev_codes = set(prev_index)

    added_codes = sorted(today_codes - prev_codes)
    removed_codes = sorted(prev_codes - today_codes)
    common_codes = sorted(today_codes & prev_codes)

    added = [
        {
            "code": code,
            "name": today_index[code].get("name") or code,
            "action": today_index[code].get("action") or "",
            "group": _stock_group_label(today, code),
        }
        for code in added_codes
    ]
    removed = [
        {
            "code": code,
            "name": prev_index[code].get("name") or code,
            "action": prev_index[code].get("action") or "",
            "group": _stock_group_label(previous, code),
        }
        for code in removed_codes
    ]

    action_changes: list[dict[str, Any]] = []
    group_changes: list[dict[str, Any]] = []
    boundary_changes: list[dict[str, Any]] = []
    signal_changes: list[dict[str, Any]] = []
    unchanged_count = 0

    for code in common_codes:
        today_stock = today_index[code]
        prev_stock = prev_index[code]
        name = today_stock.get("name") or code
        changed = False

        before_action = prev_stock.get("action") or ""
        after_action = today_stock.get("action") or ""
        if before_action != after_action:
            action_changes.append(
                {"code": code, "name": name, "before": before_action, "after": after_action}
            )
            changed = True

        before_group = _stock_group_label(previous, code)
        after_group = _stock_group_label(today, code)
        if before_group != after_group:
            group_changes.append(
                {"code": code, "name": name, "before": before_group, "after": after_group}
            )
            changed = True

        for field in ("support", "resistance", "stop_loss"):
            before_value = _trade_level(prev_stock, field)
            after_value = _trade_level(today_stock, field)
            if before_value is None and after_value is None:
                continue
            if before_value != after_value:
                boundary_changes.append(
                    {
                        "code": code,
                        "name": name,
                        "field": field,
                        "before": before_value,
                        "after": after_value,
                    }
                )
                changed = True

        before_signal = (prev_stock.get("rule_snapshot") or {}).get("signal") or ""
        after_signal = (today_stock.get("rule_snapshot") or {}).get("signal") or ""
        if before_signal != after_signal:
            signal_changes.append(
                {"code": code, "name": name, "before": before_signal, "after": after_signal}
            )
            changed = True

        if not changed:
            unchanged_count += 1

    action_changes.sort(key=lambda item: item["code"])
    group_changes.sort(key=lambda item: item["code"])
    boundary_changes.sort(key=lambda item: (item["code"], item["field"]))
    signal_changes.sort(key=lambda item: item["code"])

    return {
        "today_trade_date": (today or {}).get("trade_date"),
        "previous_trade_date": (previous or {}).get("trade_date") if previous else None,
        "added": added,
        "removed": removed,
        "action_changes": action_changes,
        "group_changes": group_changes,
        "boundary_changes": boundary_changes,
        "signal_changes": signal_changes,
        "unchanged_count": unchanged_count,
    }


def candidate_risk_flags(raw: dict[str, Any]) -> list[str]:
    warnings = ((raw.get("execution_quality") or {}).get("warnings") or [])
    return unique_strings([raw.get("main_risk") or "", *warnings])


def normalize_candidate(raw: dict[str, Any], batch_id: str) -> dict[str, Any]:
    capital_flow = normalize_capital_flow_payload(raw.get("capital_flow") or {}, legacy_source_unit=UNIT_YUAN)
    return {
        "entity": "candidate",
        "schema_version": SCHEMA_VERSION,
        "batch_id": batch_id,
        "code": raw.get("code") or "",
        "name": raw.get("name") or raw.get("code") or "",
        "screening_status": raw.get("screening_status") or "unknown",
        "tier": raw.get("tier"),
        "tier_rank": safe_int(raw.get("tier_rank")),
        "setup_type": raw.get("setup_type"),
        "setup_label": raw.get("setup_label"),
        "priority_score": safe_float(raw.get("priority_score")),
        "best_score": safe_float(raw.get("best_score")),
        "change_pct": safe_float(raw.get("change_pct")),
        "amount_yi": safe_float(raw.get("amount_yi")),
        "strategy_labels": raw.get("strategy_labels") or [],
        "themes": raw.get("themes") or [],
        "risk_flags": candidate_risk_flags(raw),
        "entry_reason": raw.get("entry_reason"),
        "entry_plan": raw.get("entry_plan"),
        "watch_condition": raw.get("watch_condition"),
        "main_risk": raw.get("main_risk"),
        "screening_note": raw.get("screening_note"),
        "consistency": raw.get("consistency") or {},
        "execution_quality": raw.get("execution_quality") or {},
        "capital_flow": capital_flow,
    }


def load_screening_batch(path: str | None = None) -> dict[str, Any]:
    batch_path = resolve_screening_batch_path(path=path)
    if not batch_path:
        raise FileNotFoundError("screening batch not found")

    raw = load_json(batch_path)
    batch_id = build_id("screening_batch", raw.get("timestamp"), batch_path.stem)
    shortlist = [normalize_candidate(item or {}, batch_id) for item in (raw.get("shortlist") or [])]

    approved_count = sum(1 for item in shortlist if item.get("screening_status") == "approved")
    caution_count = sum(1 for item in shortlist if item.get("screening_status") == "caution")
    excluded_count = sum(1 for item in shortlist if item.get("screening_status") == "excluded")

    return {
        "entity": "screening_batch",
        "schema_version": SCHEMA_VERSION,
        "batch_id": batch_id,
        "run_type": "morning",
        "generated_at": raw.get("timestamp"),
        "source_scan_timestamp": raw.get("source_scan_timestamp"),
        "path": str(batch_path.resolve()),
        "pool": raw.get("pool"),
        "pool_label": raw.get("pool_label"),
        "candidate_count": len(shortlist),
        "approved_count": approved_count,
        "caution_count": caution_count,
        "excluded_count": excluded_count,
        "market_regime": raw.get("market_regime") or {},
        "market_themes": raw.get("market_themes") or [],
        "screening_summary": raw.get("screening_summary") or {},
        "candidates": shortlist,
    }


def normalize_confirmation_item(
    raw: dict[str, Any],
    *,
    status: str,
    morning_batch_id: str | None,
    midday_batch_id: str | None,
) -> dict[str, Any]:
    observation_contract = build_confirmation_observation_contract(raw, status)
    return {
        "code": raw.get("code") or "",
        "name": raw.get("name") or raw.get("code") or "",
        "status": status,
        "theme": raw.get("theme") or raw.get("active_theme"),
        "setup_type": observation_contract["setup_type"],
        "setup_label": observation_contract["setup_label"],
        "setup_summary": observation_contract["setup_summary"],
        "score": safe_float(raw.get("score")),
        "change_pct": safe_float(raw.get("change_pct")),
        "amount_yi": safe_float(raw.get("amount_yi")),
        "flow_today_yi": safe_float(raw.get("flow_today_yi")),
        "capital_trend": raw.get("capital_trend"),
        "entry_reason": raw.get("entry_reason"),
        "entry_plan": observation_contract["entry_plan"],
        "execution_quality": observation_contract["execution_quality"],
        "main_risk": raw.get("main_risk"),
        "watch_condition": raw.get("watch_condition"),
        "high20": safe_float(raw.get("high20")),
        "ma5": safe_float(raw.get("ma5")),
        "ma10": safe_float(raw.get("ma10")),
        "morning_batch_id": morning_batch_id,
        "midday_batch_id": midday_batch_id,
    }


def load_confirmation(path: str | None = None) -> dict[str, Any]:
    confirm_path = resolve_confirmation_path(path=path)
    if not confirm_path:
        raise FileNotFoundError("confirmation result not found")

    raw = load_json(confirm_path)
    morning_batch_id = build_id("screening_batch", raw.get("source_morning_timestamp"), "morning")
    midday_batch_id = build_id("screening_batch", raw.get("verified_against_scan_timestamp"), "midday")

    confirmed = [
        normalize_confirmation_item(item or {}, status="confirmed", morning_batch_id=morning_batch_id, midday_batch_id=midday_batch_id)
        for item in (raw.get("confirmed") or [])
    ]
    downgraded = [
        normalize_confirmation_item(item or {}, status="downgraded", morning_batch_id=morning_batch_id, midday_batch_id=midday_batch_id)
        for item in (raw.get("downgraded") or [])
    ]
    fresh_candidates = [
        normalize_confirmation_item(item or {}, status="fresh_candidate", morning_batch_id=morning_batch_id, midday_batch_id=midday_batch_id)
        for item in (raw.get("fresh_candidates") or [])
    ]

    return {
        "entity": "confirmation",
        "schema_version": SCHEMA_VERSION,
        "confirmation_id": build_id("confirmation", raw.get("timestamp"), confirm_path.stem),
        "generated_at": raw.get("timestamp"),
        "validation_status": raw.get("validation_status") or "unknown",
        "validation_errors": raw.get("validation_errors") or [],
        "morning_batch_id": morning_batch_id,
        "midday_batch_id": midday_batch_id,
        "source_morning_timestamp": raw.get("source_morning_timestamp"),
        "verified_against_scan_timestamp": raw.get("verified_against_scan_timestamp"),
        "counts": {
            "confirmed": len(confirmed),
            "downgraded": len(downgraded),
            "fresh_candidates": len(fresh_candidates),
            "target_codes": len(raw.get("target_codes") or []),
        },
        "confirmed": confirmed,
        "downgraded": downgraded,
        "fresh_candidates": fresh_candidates,
        "path": str(confirm_path.resolve()),
    }


def load_decision_brief(path: str | None = None) -> dict[str, Any]:
    brief_path = resolve_decision_brief_path(path=path)
    if not brief_path:
        raise FileNotFoundError("decision brief not found")

    raw = load_json(brief_path)
    summary = raw.get("summary") or {}
    watchlist = raw.get("watchlist") or {}
    screener = raw.get("screener") or {}
    midday = raw.get("midday") or raw.get("midday_confirmation") or {}
    screener_path = stable_artifact_path(screener.get("path"))
    screener_alias_path = mutable_alias_path(screener.get("path"))
    confirmation_path = stable_artifact_path(midday.get("path"))
    confirmation_alias_path = mutable_alias_path(midday.get("path"))

    priority_codes = [item.get("code") for item in (watchlist.get("priority") or []) if item.get("code")]
    follow_codes = [item.get("code") for item in (watchlist.get("follow") or []) if item.get("code")]
    observe_codes = [item.get("code") for item in (watchlist.get("observe") or []) if item.get("code")]

    return {
        "entity": "decision_brief",
        "schema_version": SCHEMA_VERSION,
        "brief_id": build_id("decision_brief", summary.get("generated_at"), brief_path.stem),
        "trade_date": summary.get("trade_date"),
        "generated_at": summary.get("generated_at"),
        "summary": {
            "open_new_positions": summary.get("open_new_positions"),
            "position_cap": summary.get("position_cap"),
            "gate_label": summary.get("gate_label"),
            "gate_summary": summary.get("gate_summary"),
            "main_theme": summary.get("main_theme"),
            "watchlist_summary": summary.get("watchlist_summary"),
            "midday_summary": summary.get("midday_summary"),
        },
        "focus": {
            "holding_focus": summary.get("holding_focus") or [],
            "opportunity_focus": summary.get("opportunity_focus") or [],
            "avoid_points": summary.get("avoid_points") or [],
        },
        "watchlist": {
            "snapshot_id": build_id("watchlist_snapshot", watchlist.get("generated_at"), summary.get("trade_date")),
            "snapshot_path": watchlist.get("snapshot_path"),
            "summary": watchlist.get("summary"),
            "priority_codes": priority_codes,
            "follow_codes": follow_codes,
            "observe_codes": observe_codes,
        },
        "screener": {
            "batch_id": build_id("screening_batch", screener.get("timestamp"), "screener"),
            "path": screener_path,
            "source_alias_path": screener_alias_path,
            "source_scan_timestamp": screener.get("source_scan_timestamp"),
            "market_regime": screener.get("market_regime") or {},
            "screening_summary": screener.get("screening_summary") or {},
            "top_theme": screener.get("top_theme"),
            "candidate_count": len(screener.get("shortlist") or []),
        },
        "midday_confirmation": {
            "confirmation_id": build_id("confirmation", midday.get("timestamp"), "midday"),
            "path": confirmation_path,
            "source_alias_path": confirmation_alias_path,
            "validation_status": midday.get("validation_status"),
            "confirmed_count": len(midday.get("confirmed") or []),
            "downgraded_count": len(midday.get("downgraded") or []),
            "fresh_candidate_count": len(midday.get("fresh_candidates") or []),
            "summary": summary.get("midday_summary"),
        },
        "paths": {
            "source_json": str(brief_path.resolve()),
            "watchlist_snapshot": watchlist.get("snapshot_path"),
            "screening_batch": screener_path,
            "screening_batch_alias": screener_alias_path,
            "confirmation": confirmation_path,
            "confirmation_alias": confirmation_alias_path,
        },
    }


def find_candidate_detail(code: str, path: str | None = None) -> dict[str, Any]:
    target = code.strip()
    batch = load_screening_batch(path=path)
    for candidate in batch.get("candidates", []):
        if candidate.get("code") == target:
            return candidate

    confirmation = load_confirmation()
    for group in ("confirmed", "downgraded", "fresh_candidates"):
        for item in confirmation.get(group, []):
            if item.get("code") != target:
                continue
            return {
                "entity": "candidate",
                "schema_version": SCHEMA_VERSION,
                "batch_id": confirmation.get("midday_batch_id") or confirmation.get("morning_batch_id") or "confirmation",
                "code": item.get("code"),
                "name": item.get("name"),
                "screening_status": item.get("status"),
                "tier": None,
                "tier_rank": None,
                "setup_type": item.get("setup_type"),
                "setup_label": item.get("setup_label"),
                "priority_score": item.get("score"),
                "best_score": item.get("score"),
                "change_pct": item.get("change_pct"),
                "amount_yi": item.get("amount_yi"),
                "strategy_labels": [],
                "themes": unique_strings([item.get("theme") or ""]),
                "risk_flags": unique_strings([
                    item.get("main_risk") or "",
                    *(((item.get("execution_quality") or {}).get("warnings")) or []),
                ]),
                "entry_reason": item.get("entry_reason"),
                "entry_plan": item.get("entry_plan"),
                "watch_condition": item.get("watch_condition"),
                "main_risk": item.get("main_risk"),
                "screening_note": item.get("setup_summary"),
                "consistency": {},
                "execution_quality": item.get("execution_quality") or {},
                "capital_flow": normalize_capital_flow_payload({
                    "trend": item.get("capital_trend"),
                    "today_yi": item.get("flow_today_yi"),
                }),
            }

    raise KeyError(f"candidate not found: {target}")


def load_quality_status(lane: str | None = None) -> dict[str, Any]:
    def load_lane(target_lane: str) -> dict[str, Any]:
        pattern = QUALITY_PATTERNS[target_lane]
        exclude = ("midday_",) if target_lane == "aggressive" else ()
        path = latest_matching(pattern, exclude_tokens=exclude)
        data = load_json(path)
        return {
            "lane": target_lane,
            "checked_at": data.get("checked_at") if data else None,
            "validation_status": data.get("validation_status") if data else None,
            "expected_timestamp": data.get("expected_timestamp") if data else None,
            "errors": data.get("errors") or [],
            "warnings": data.get("warnings") or [],
            "path": str(path.resolve()) if path else None,
        }

    if lane and lane != "all":
        return load_lane(lane)

    return {
        "entity": "quality_status",
        "schema_version": SCHEMA_VERSION,
        "lanes": {
            "watchlist": load_lane("watchlist"),
            "aggressive": load_lane("aggressive"),
            "midday_confirmation": load_lane("midday_confirmation"),
        },
    }


def lifecycle_activity_count(summary: dict[str, Any] | None) -> int:
    counts = summary or {}
    return sum(
        int(counts.get(key) or 0)
        for key in ("entered_count", "upgraded_count", "downgraded_count", "exited_count", "handed_off_count")
    )


def resolve_lifecycle_path(path: str | None = None, require_activity: bool = False) -> Path | None:
    if path:
        candidate = Path(path).expanduser()
        return candidate if candidate.exists() else None

    files = sorted(SCREENER_DATA_DIR.glob("lifecycle_*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not require_activity:
        return files[0] if files else None

    for candidate in files:
        data = load_json(candidate)
        if lifecycle_activity_count(data.get("summary") or {}) > 0:
            return candidate
    return files[0] if files else None


def normalize_lifecycle_item(raw: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "code": raw.get("code") or "",
        "name": raw.get("name") or raw.get("code") or "",
    }
    for key in (
        "tier",
        "screening_status",
        "score",
        "theme",
        "change_pct",
        "entry_reason",
        "main_risk",
        "prev_tier",
        "curr_tier",
        "prev_screening_status",
        "curr_screening_status",
        "prev_score",
        "curr_score",
        "score_delta",
        "last_seen",
        "status",
        "reason",
        "morning_score",
        "current_tier",
        "current_screening_status",
        "in_current_shortlist",
    ):
        if key not in raw:
            continue
        value = raw.get(key)
        if key in {"score", "change_pct", "prev_score", "curr_score", "score_delta", "morning_score"}:
            normalized[key] = safe_float(value)
        else:
            normalized[key] = value
    return normalized


def load_lifecycle(path: str | None = None, require_activity: bool = False) -> dict[str, Any]:
    lifecycle_path = resolve_lifecycle_path(path=path, require_activity=require_activity)
    if not lifecycle_path:
        raise FileNotFoundError("lifecycle snapshot not found")

    raw = load_json(lifecycle_path)
    summary = raw.get("summary") or {}
    metadata = raw.get("metadata") or {}

    return {
        "entity": "lifecycle",
        "schema_version": SCHEMA_VERSION,
        "lifecycle_id": build_id("lifecycle", metadata.get("generated_at"), lifecycle_path.stem),
        "generated_at": metadata.get("generated_at"),
        "current_timestamp": metadata.get("current_timestamp"),
        "previous_snapshot_timestamp": metadata.get("previous_snapshot_timestamp"),
        "previous_snapshot_source": metadata.get("previous_snapshot_source"),
        "midday_verification_timestamp": metadata.get("midday_verification_timestamp"),
        "midday_matches_current_ai": bool(metadata.get("midday_matches_current_ai", False)),
        "selection_mode": "latest_active" if require_activity else "latest",
        "summary": {
            "entered_count": int(summary.get("entered_count") or 0),
            "upgraded_count": int(summary.get("upgraded_count") or 0),
            "downgraded_count": int(summary.get("downgraded_count") or 0),
            "exited_count": int(summary.get("exited_count") or 0),
            "handed_off_count": int(summary.get("handed_off_count") or 0),
            "current_pool_size": int(summary.get("current_pool_size") or 0),
            "previous_pool_size": int(summary.get("previous_pool_size") or 0),
        },
        "activity_count": lifecycle_activity_count(summary),
        "groups": {
            "entered": [normalize_lifecycle_item(item or {}) for item in (raw.get("entered") or [])],
            "upgraded": [normalize_lifecycle_item(item or {}) for item in (raw.get("upgraded") or [])],
            "downgraded": [normalize_lifecycle_item(item or {}) for item in (raw.get("downgraded") or [])],
            "exited": [normalize_lifecycle_item(item or {}) for item in (raw.get("exited") or [])],
            "handed_off": [normalize_lifecycle_item(item or {}) for item in (raw.get("handed_off") or [])],
        },
        "path": str(lifecycle_path.resolve()),
    }


def resolve_research_review_path(path: str | None = None, prefer_baseline: bool = False) -> Path | None:
    if path:
        candidate = Path(path).expanduser()
        return candidate if candidate.exists() else None

    import re

    def sort_key(candidate: Path) -> tuple[str, str, int, str]:
        match = re.search(r"review_(\d{8})_(\d{8})(?:(_rerun))?$", candidate.stem)
        if not match:
            return ("", "", 0, candidate.stem)
        start_date = match.group(1)
        end_date = match.group(2)
        rerun_flag = 1 if match.group(3) else 0
        return (end_date, start_date, rerun_flag, candidate.stem)

    files = sorted(RESEARCH_REPORTS_DIR.glob("research_backfill_review_*.md"), key=sort_key, reverse=True)
    if not files:
        return None

    if prefer_baseline:
        baseline = [item for item in files if "_rerun" in item.stem]
        if baseline:
            return baseline[0]

    recent = [item for item in files if "_rerun" not in item.stem]
    if recent:
        return recent[0]
    return files[0]


def text_after_prefix(text: str, prefix: str) -> str | None:
    for line in text.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return None


def extract_markdown_section(text: str, title: str) -> str:
    import re

    pattern = re.compile(rf"^{re.escape(title)}\s*$\n(?P<body>.*?)(?=^###\s+|^##\s+|\Z)", re.M | re.S)
    match = pattern.search(text)
    return match.group("body").strip() if match else ""


def parse_markdown_table(section: str) -> list[dict[str, str]]:
    if not section:
        return []
    lines = [line.strip() for line in section.splitlines()]
    table_lines: list[str] = []
    collecting = False
    for line in lines:
        if line.startswith("|"):
            table_lines.append(line)
            collecting = True
            continue
        if collecting:
            break
    if len(table_lines) < 2:
        return []

    headers = [cell.strip() for cell in table_lines[0].strip("|").split("|")]
    rows: list[dict[str, str]] = []
    for line in table_lines[2:]:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != len(headers):
            continue
        rows.append({headers[index]: cells[index] for index in range(len(headers))})
    return rows


def parse_pair_pct(value: str | None) -> dict[str, float | None]:
    parts = [part.strip() for part in str(value or "").split("/")]
    raw = pct_from_text(parts[0]) if parts else None
    net = pct_from_text(parts[1]) if len(parts) > 1 else None
    return {"raw_pct": raw, "net_pct": net}


def normalize_review_row(raw: dict[str, str]) -> dict[str, Any]:
    next_day_mean = parse_pair_pct(raw.get("次日均值(原/净)"))
    next_day_win = parse_pair_pct(raw.get("次日胜率(原/净)"))
    day3_mean = parse_pair_pct(raw.get("3日均值(原/净)"))
    day5_mean = parse_pair_pct(raw.get("5日均值(原/净)"))
    day5_win = parse_pair_pct(raw.get("5日胜率(原/净)"))
    return {
        "label": raw.get("组别") or "",
        "sample_count": int_from_text(raw.get("总样本")),
        "valid_samples": raw.get("有效样本(次日/3日/5日)"),
        "next_day": {
            "raw_pct": next_day_mean.get("raw_pct"),
            "net_pct": next_day_mean.get("net_pct"),
            "win_raw_pct": next_day_win.get("raw_pct"),
            "win_net_pct": next_day_win.get("net_pct"),
        },
        "day3": {
            "raw_pct": day3_mean.get("raw_pct"),
            "net_pct": day3_mean.get("net_pct"),
        },
        "day5": {
            "raw_pct": day5_mean.get("raw_pct"),
            "net_pct": day5_mean.get("net_pct"),
            "win_raw_pct": day5_win.get("raw_pct"),
            "win_net_pct": day5_win.get("net_pct"),
        },
        "source": raw,
    }


def normalize_review_rows(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    return [normalize_review_row(row) for row in rows]


def row_by_label(rows: list[dict[str, Any]], label: str) -> dict[str, Any] | None:
    for row in rows:
        if row.get("label") == label:
            return row
    return None


def best_review_row(rows: list[dict[str, Any]], period: str) -> dict[str, Any] | None:
    candidates = [row for row in rows if ((row.get(period) or {}).get("net_pct")) is not None]
    if not candidates:
        return None
    return max(candidates, key=lambda row: (row.get(period) or {}).get("net_pct") or float("-inf"))


def worst_review_row(rows: list[dict[str, Any]], period: str) -> dict[str, Any] | None:
    candidates = [row for row in rows if ((row.get(period) or {}).get("net_pct")) is not None]
    if not candidates:
        return None
    return min(candidates, key=lambda row: (row.get(period) or {}).get("net_pct") or float("inf"))


def load_research_review(path: str | None = None, prefer_baseline: bool = False) -> dict[str, Any]:
    report_path = resolve_research_review_path(path=path, prefer_baseline=prefer_baseline)
    if not report_path:
        raise FileNotFoundError("research review report not found")

    text = report_path.read_text(encoding="utf-8")
    generated_at = text_after_prefix(text, "生成时间：")
    pool = text_after_prefix(text, "股票池：")
    window_label = text_after_prefix(text, "日期过滤：")
    ai_scan_line = text_after_prefix(text, "AI 去重批次：") or ""
    cost_line = text_after_prefix(text, "摩擦成本假设：") or ""

    import re

    ai_scan_match = re.match(r"(\d+)\s*\|\s*Scan 批次：(\d+)", ai_scan_line)
    cost_match = re.search(r"往返合计\s*([0-9.]+)%", cost_line)
    start_match = re.search(r"开始\s+(\d{4}-\d{2}-\d{2})", window_label or "")
    end_match = re.search(r"结束\s+(\d{4}-\d{2}-\d{2})", window_label or "")
    filename_window_match = re.search(r"review_(\d{8})_(\d{8})(?:_rerun)?$", report_path.stem)

    def normalize_date_token(value: str | None) -> str | None:
        if not value or len(value) != 8:
            return None
        return f"{value[:4]}-{value[4:6]}-{value[6:8]}"

    start_date = start_match.group(1) if start_match else normalize_date_token(filename_window_match.group(1) if filename_window_match else None)
    end_date = end_match.group(1) if end_match else normalize_date_token(filename_window_match.group(2) if filename_window_match else None)

    notes_section = extract_markdown_section(text, "## 压测说明")
    notes = [line[2:].strip() for line in notes_section.splitlines() if line.strip().startswith("- ")]

    ai_overall_rows = normalize_review_rows(parse_markdown_table(extract_markdown_section(text, "### AI 总体统计")))
    ai_bucket_rows = normalize_review_rows(parse_markdown_table(extract_markdown_section(text, "### AI 按分组统计")))
    ai_gate_rows = normalize_review_rows(parse_markdown_table(extract_markdown_section(text, "### AI 按执行阀门统计")))
    ai_regime_rows = normalize_review_rows(parse_markdown_table(extract_markdown_section(text, "### AI 按环境强弱统计")))
    ai_tier_rows = normalize_review_rows(parse_markdown_table(extract_markdown_section(text, "### AI 按分层统计")))
    scan_overall_rows = normalize_review_rows(parse_markdown_table(extract_markdown_section(text, "### Scan 总体统计")))
    scan_bucket_rows = normalize_review_rows(parse_markdown_table(extract_markdown_section(text, "### Scan 分策略统计")))
    scan_gate_rows = normalize_review_rows(parse_markdown_table(extract_markdown_section(text, "### Scan 按执行阀门统计")))
    scan_regime_rows = normalize_review_rows(parse_markdown_table(extract_markdown_section(text, "### Scan 按环境强弱统计")))

    return {
        "entity": "research_review",
        "schema_version": SCHEMA_VERSION,
        "review_id": build_id("research_review", generated_at, report_path.stem),
        "generated_at": generated_at,
        "pool": pool,
        "window_label": window_label,
        "start_date": start_date,
        "end_date": end_date,
        "ai_run_count": int(ai_scan_match.group(1)) if ai_scan_match else 0,
        "scan_run_count": int(ai_scan_match.group(2)) if ai_scan_match else 0,
        "roundtrip_cost_pct": safe_float(cost_match.group(1)) if cost_match else None,
        "selection_mode": "baseline" if "_rerun" in report_path.stem else "latest",
        "notes": notes,
        "summary": {
            "ai_overall": ai_overall_rows[0] if ai_overall_rows else None,
            "scan_overall": scan_overall_rows[0] if scan_overall_rows else None,
            "ai_best_gate_day5": best_review_row(ai_gate_rows, "day5"),
            "ai_worst_gate_day5": worst_review_row(ai_gate_rows, "day5"),
            "ai_best_regime_day5": best_review_row(ai_regime_rows, "day5"),
            "scan_best_strategy_day5": best_review_row(scan_bucket_rows, "day5"),
            "weak_regime_ai": row_by_label(ai_regime_rows, "0-3 弱环境"),
            "trial_regime_ai": row_by_label(ai_regime_rows, "4-5 试错环境"),
            "attack_regime_ai": row_by_label(ai_regime_rows, "6-8 进攻环境"),
        },
        "sections": {
            "ai_bucket_rows": ai_bucket_rows,
            "ai_gate_rows": ai_gate_rows,
            "ai_regime_rows": ai_regime_rows,
            "ai_tier_rows": ai_tier_rows,
            "scan_bucket_rows": scan_bucket_rows,
            "scan_gate_rows": scan_gate_rows,
            "scan_regime_rows": scan_regime_rows,
        },
        "path": str(report_path.resolve()),
    }
