"""Unified readiness / freshness model for the Prism control panel.

This module provides a single source of truth for "is the data fresh enough
to be considered live for real-money execution?". The output is consumed by
`build_today_view` (and other page builders) so the front-end can present a
fail-closed status to the operator.

Design notes:

* `expected_trade_date` defaults to the current calendar weekday. On weekends
  / holidays the expected trade date falls back to the most recent weekday,
  but readiness is at most ``shadow_only`` because real markets are closed.
* `data_trade_date` reflects what the loaded artifacts actually contain.
* Old data (where data_trade_date != expected_trade_date) can NEVER be
  ``live_ready`` even if all sources agree with each other.
* Freshness uses real timestamps (``generated_at``), not just trade-date
  strings.
* Quality lanes are downgraded when ``checked_at`` does not align with the
  expected trade date, even if validation_status == ``ok``.
* Sessions: morning / midday / afternoon / post-close / weekend.  In the
  morning a missing midday-confirmation is a *warning*; from midday onwards
  it becomes a blocker.

The helper purposely returns plain JSON-friendly structures so it can be
embedded in the ``/api/today`` payload directly.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Mapping, Sequence

from trading_calendar import (
    CALENDAR_HORIZON,
    calendar_status,
    is_trading_day,
    most_recent_trading_day,
)

from freshness_state import FreshnessState, classify_source_row
from capability_matrix import evaluate_capabilities


__all__ = [
    "expected_trade_date",
    "current_session",
    "compute_readiness",
    "DEFAULT_SOURCE_THRESHOLDS",
    "DEFAULT_QUALITY_THRESHOLDS",
]


# ---------------------------------------------------------------------------
# Threshold configuration
# ---------------------------------------------------------------------------

# Maximum age (in seconds) before a source is considered stale-by-time.
# Trade-date mismatch alone is enough to fail readiness even before these
# thresholds kick in, so they can stay generous.
DEFAULT_SOURCE_THRESHOLDS: dict[str, int] = {
    "watchlist": 12 * 3600,
    "screening": 12 * 3600,
    "confirmation": 6 * 3600,
    "decision_brief": 24 * 3600,
}

# Maximum age (in seconds) for a quality lane's checked_at before it is
# considered stale.
DEFAULT_QUALITY_THRESHOLDS: dict[str, int] = {
    "watchlist": 24 * 3600,
    "aggressive": 18 * 3600,
    "midday_confirmation": 12 * 3600,
}


PIPELINE_AGGREGATE_DATASETS = {
    "watchlist.snapshot",
    "screening.batch",
    "screening.confirmation",
    "decision_brief.snapshot",
}

SESSION_FINALIZED_DATASETS = {
    "watchlist.snapshot",
    "screening.batch",
    "screening.confirmation",
    "decision_brief.snapshot",
}


# ---------------------------------------------------------------------------
# Timestamp parsing helpers (kept tolerant of mixed formats)
# ---------------------------------------------------------------------------


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    # Try common shapes including the YYYY-MM-DDTHH:MM:SS "ISO-ish" form.
    candidates = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d_%H-%M-%S",
        "%Y-%m-%d",
    )
    for fmt in candidates:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _date_str(value: Any) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    dt = _parse_dt(text)
    if dt:
        return dt.strftime("%Y-%m-%d")
    return None


def _age_seconds(now: datetime, parsed: datetime | None) -> int | None:
    if not parsed:
        return None
    return max(int((now - parsed).total_seconds()), 0)


def _age_label(seconds: int | None) -> str:
    if seconds is None:
        return "-"
    if seconds < 60:
        return "刚刚"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} 分钟前"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} 小时前"
    days = hours // 24
    return f"{days} 天前"


def _same_day_pipeline_age_is_soft(
    *,
    dataset: str,
    provider: str,
    data_trade_date: str | None,
    expected_date: str,
    session_key: str,
) -> bool:
    """Treat same-day finalized pipeline artifacts as valid after close.

    A watchlist analysis produced in the morning and a confirmation produced
    after lunch are daily decision artifacts.  Once the market is closed,
    rerunning them every few hours cannot make the underlying session more
    "live"; it mostly creates noisy operator prompts.  Trade-date mismatch
    remains a hard fail, so genuinely old data is still blocked.
    """

    return (
        provider == "pipeline"
        and dataset in SESSION_FINALIZED_DATASETS
        and data_trade_date == expected_date
        and session_key == "post_close"
    )


# ---------------------------------------------------------------------------
# Expected trade date / session helpers
# ---------------------------------------------------------------------------


def _previous_weekday(today: date) -> date:
    cursor = today
    while True:
        cursor = cursor - timedelta(days=1)
        if cursor.weekday() < 5:
            return cursor


def expected_trade_date(now: datetime | None = None) -> str:
    """Return the trade date the operator expects to see on the page.

    Allows an explicit ``PRISM_EXPECTED_TRADE_DATE=YYYY-MM-DD`` env override
    (mainly for tests and replay sessions).  When that override is missing
    we consult the trading calendar: weekdays that are also exchange
    trading days return today; weekends and exchange holidays fall back to
    the most recent confirmed trading day so the page still has a sensible
    baseline.  ``compute_readiness`` will refuse to mark the system
    ``live_ready`` on those non-trading days regardless.
    """

    override = os.environ.get("PRISM_EXPECTED_TRADE_DATE", "").strip()
    if override:
        normalized = _date_str(override)
        if normalized:
            return normalized

    current = now or datetime.now()
    if is_trading_day(current):
        return current.strftime("%Y-%m-%d")
    return most_recent_trading_day(current).strftime("%Y-%m-%d")


def current_session(now: datetime | None = None) -> dict[str, Any]:
    """Best-effort A-share session classifier (Asia/Shanghai assumption).

    The control panel runs locally and we already assume host time is in
    market timezone elsewhere, so we use the host clock directly.  The
    classifier consults the trading calendar so post-holiday weekdays are
    correctly flagged as non-trading.
    """

    current = now or datetime.now()
    cal = calendar_status(current)
    if cal["status"] == "holiday":
        return {
            "key": "holiday",
            "label": f"节假日休市（{cal['reason']}）",
            "is_trading_day": False,
            "calendar_status": cal["status"],
        }
    if cal["status"] == "weekend":
        return {
            "key": "weekend",
            "label": "周末休市",
            "is_trading_day": False,
            "calendar_status": cal["status"],
        }
    if cal["status"] == "unknown":
        return {
            "key": "unknown",
            "label": "交易日历未覆盖",
            "is_trading_day": False,
            "calendar_status": cal["status"],
        }

    minutes = current.hour * 60 + current.minute
    if minutes < 9 * 60:
        return {"key": "premarket", "label": "盘前", "is_trading_day": True, "calendar_status": cal["status"]}
    if minutes < 11 * 60 + 30:
        return {"key": "morning", "label": "早盘", "is_trading_day": True, "calendar_status": cal["status"]}
    if minutes < 13 * 60:
        return {"key": "midday", "label": "午间", "is_trading_day": True, "calendar_status": cal["status"]}
    if minutes < 15 * 60:
        return {"key": "afternoon", "label": "午后", "is_trading_day": True, "calendar_status": cal["status"]}
    return {"key": "post_close", "label": "盘后", "is_trading_day": True, "calendar_status": cal["status"]}


# ---------------------------------------------------------------------------
# Source / quality freshness builders
# ---------------------------------------------------------------------------


def _build_source(
    *,
    key: str,
    label: str,
    payload: Mapping[str, Any] | None,
    expected_date: str,
    now: datetime,
    threshold_seconds: int,
    session_key: str,
    trade_date_field: str = "trade_date",
    timestamp_field: str = "generated_at",
    fallback_trade_date_keys: Sequence[str] = (),
) -> dict[str, Any]:
    payload = payload or {}
    manifest = payload.get("manifest") if isinstance(payload.get("manifest"), Mapping) else None
    raw_value = (
        (manifest or {}).get("asof")
        or (manifest or {}).get("fetched_at")
        or payload.get(timestamp_field)
    )
    parsed = _parse_dt(raw_value)
    age = _age_seconds(now, parsed)

    raw_trade_date = (manifest or {}).get("trade_date") or payload.get(trade_date_field)
    if not raw_trade_date and not manifest:
        for alt in fallback_trade_date_keys:
            if payload.get(alt):
                raw_trade_date = payload.get(alt)
                break
    if not raw_trade_date and parsed:
        raw_trade_date = parsed.strftime("%Y-%m-%d")
    data_trade_date = _date_str(raw_trade_date)

    available = bool(parsed)
    reasons: list[str] = []
    degradation_reasons: list[str] = []
    stale = False
    dataset = str((manifest or {}).get("dataset") or "").strip()
    provider = str((manifest or {}).get("provider") or "").strip()
    aggregate_pipeline = provider == "pipeline" and dataset in PIPELINE_AGGREGATE_DATASETS

    if not manifest:
        stale = True
        reasons.append("manifest_missing")
    else:
        manifest_status = str(manifest.get("status") or "").strip().lower()
        manifest_freshness = str(manifest.get("freshness_status") or "").strip().lower()
        if manifest_status and manifest_status != "ok":
            stale = True
            reasons.append(f"manifest_status_{manifest_status}")
        if manifest_freshness in {"stale", "expired"}:
            if aggregate_pipeline:
                degradation_reasons.append(f"upstream_freshness_{manifest_freshness}")
            else:
                stale = True
                reasons.append(f"freshness_{manifest_freshness}")
        elif not manifest_freshness:
            stale = True
            reasons.append("freshness_unknown")
        if not bool(manifest.get("live_small_allowed")):
            if aggregate_pipeline:
                degradation_reasons.append("upstream_live_small_not_allowed")
            else:
                stale = True
                reasons.append("live_small_not_allowed")
        if bool(manifest.get("fallback_used")) and not bool(manifest.get("live_small_allowed")):
            if aggregate_pipeline:
                degradation_reasons.append("upstream_fallback_not_allowed")
            else:
                stale = True
                reasons.append("fallback_not_allowed")

    authority_flags = list((manifest or {}).get("authority_flags") or [])
    source_lane = str((manifest or {}).get("source_lane") or "").strip()
    decision_scope = str((manifest or {}).get("decision_scope") or "").strip()
    source_authority_ready = bool((manifest or {}).get("source_authority_ready", True)) if manifest else False
    formal_decision_allowed = bool((manifest or {}).get("formal_decision_allowed")) if manifest else False

    if not available:
        stale = True
        reasons.append("missing")

    if data_trade_date and data_trade_date != expected_date:
        stale = True
        reasons.append("trade_date_mismatch")

    if not data_trade_date and available:
        stale = True
        reasons.append("trade_date_unknown")

    age_softened = False
    if age is not None and age > threshold_seconds:
        if _same_day_pipeline_age_is_soft(
            dataset=dataset,
            provider=provider,
            data_trade_date=data_trade_date,
            expected_date=expected_date,
            session_key=session_key,
        ):
            age_softened = True
            degradation_reasons.append("same_day_post_close_age_exceeded")
        else:
            stale = True
            reasons.append("age_exceeded")

    detail = (
        (manifest or {}).get("provider")
        or payload.get("trade_date")
        or payload.get("pool_label")
        or payload.get("validation_status")
        or ""
    )

    return {
        "key": key,
        "label": label,
        "value": str(raw_value) if raw_value else "-",
        "detail": str(detail) if detail else "",
        "trade_date": data_trade_date,
        "available": available,
        "age_seconds": age,
        "age_label": _age_label(age),
        "stale": stale,
        "stale_after_seconds": int(threshold_seconds if aggregate_pipeline else ((manifest or {}).get("ttl_seconds") or threshold_seconds)),
        "stale_reasons": reasons,
        "degraded": bool(degradation_reasons),
        "degradation_reasons": degradation_reasons,
        "age_softened": age_softened,
        "provider": (manifest or {}).get("provider"),
        "provider_role": (manifest or {}).get("provider_role"),
        "freshness_status": (manifest or {}).get("freshness_status"),
        "fallback_used": bool((manifest or {}).get("fallback_used")),
        "live_small_allowed": bool((manifest or {}).get("live_small_allowed")) if manifest else False,
        "manifest_path": (manifest or {}).get("manifest_path"),
        "source_lane": source_lane,
        "decision_scope": decision_scope,
        "authority_provider": (manifest or {}).get("authority_provider"),
        "target_authority_provider": (manifest or {}).get("target_authority_provider"),
        "audit_providers": list((manifest or {}).get("audit_providers") or []),
        "source_authority_ready": source_authority_ready,
        "formal_decision_allowed": formal_decision_allowed,
        "authority_flags": authority_flags,
    }


def _build_quality(
    *,
    key: str,
    title: str,
    lanes: Mapping[str, Any],
    expected_date: str,
    now: datetime,
    threshold_seconds: int,
) -> dict[str, Any]:
    lane = lanes.get(key) or {}
    validation_status = str(lane.get("validation_status") or "unknown").strip().lower()
    checked_at = lane.get("checked_at")
    expected_timestamp = lane.get("expected_timestamp")

    parsed = _parse_dt(checked_at)
    age = _age_seconds(now, parsed)
    checked_trade_date = _date_str(checked_at)
    lane_expected_trade_date = _date_str(expected_timestamp)
    # Display the lane-supplied expected trade date when available, otherwise
    # fall back to the global readiness expected date.  Operators read this
    # value, so we prefer the most specific signal.
    expected_trade_date_str = lane_expected_trade_date or expected_date

    timely = True
    stale_reasons: list[str] = []

    if validation_status not in {"ok"}:
        timely = False
        stale_reasons.append(f"status_{validation_status}")

    # Lane-supplied ``expected_timestamp`` is what the producer thinks the
    # current trade date should be.  If that disagrees with our global
    # expected date we cannot trust the lane even when checked_at happens to
    # land on the correct day — the gate logic was running against an older
    # baseline.
    if lane_expected_trade_date and lane_expected_trade_date != expected_date:
        timely = False
        stale_reasons.append("expected_trade_date_mismatch")

    if checked_trade_date and checked_trade_date != expected_date:
        timely = False
        stale_reasons.append("trade_date_mismatch")

    if not checked_trade_date and validation_status == "ok":
        timely = False
        stale_reasons.append("trade_date_unknown")

    if age is not None and age > threshold_seconds:
        timely = False
        stale_reasons.append("age_exceeded")

    return {
        "key": key,
        "title": title,
        "validation_status": validation_status,
        "checked_at": str(checked_at) if checked_at else "-",
        "expected_timestamp": str(expected_timestamp) if expected_timestamp else "-",
        "checked_trade_date": checked_trade_date,
        "expected_trade_date": expected_trade_date_str,
        "lane_expected_trade_date": lane_expected_trade_date,
        "age_seconds": age,
        "age_label": _age_label(age),
        "timely": timely,
        "stale_reasons": stale_reasons,
    }


def _defer_source_until_session(source: dict[str, Any], *, reason: str) -> None:
    """Mark a future-session source as not yet due instead of stale."""

    source["stale"] = False
    source["deferred"] = True
    source["deferred_reason"] = reason
    source["stale_reasons"] = []


def _defer_quality_until_session(quality: dict[str, Any], *, reason: str) -> None:
    quality["timely"] = True
    quality["deferred"] = True
    quality["deferred_reason"] = reason
    quality["stale_reasons"] = []


# ---------------------------------------------------------------------------
# compute_readiness — the main entry point
# ---------------------------------------------------------------------------


def compute_readiness(
    *,
    watchlist: Mapping[str, Any] | None,
    screening_batch: Mapping[str, Any] | None,
    confirmation: Mapping[str, Any] | None,
    decision_brief: Mapping[str, Any] | None,
    quality_status: Mapping[str, Any] | None,
    account_book: Mapping[str, Any] | None = None,
    today_action_decisions: Mapping[str, Any] | None = None,
    now: datetime | None = None,
    expected_date: str | None = None,
    source_thresholds: Mapping[str, int] | None = None,
    quality_thresholds: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Compute the unified readiness payload.

    The caller passes already-loaded canonical artifacts; we never touch the
    filesystem from here so the function is easy to test.

    ``account_book`` and ``today_action_decisions`` are optional — when they
    are provided we extend the readiness payload with an ``account_state``
    block and tighten the live-ready gate accordingly.  When they are
    omitted (e.g. for legacy callers / older tests) the function preserves
    its previous behaviour and treats the account dimension as "research".
    """

    current = now or datetime.now()
    expected = expected_date or expected_trade_date(current)
    session = current_session(current)
    thresholds = {**DEFAULT_SOURCE_THRESHOLDS, **(source_thresholds or {})}
    quality_thr = {**DEFAULT_QUALITY_THRESHOLDS, **(quality_thresholds or {})}

    sources = [
        _build_source(
            key="watchlist",
            label="自选股",
            payload=watchlist,
            expected_date=expected,
            now=current,
            threshold_seconds=thresholds["watchlist"],
            session_key=str(session.get("key") or ""),
            fallback_trade_date_keys=("date",),
        ),
        _build_source(
            key="screening",
            label="观察池基线",
            payload=screening_batch,
            expected_date=expected,
            now=current,
            threshold_seconds=thresholds["screening"],
            session_key=str(session.get("key") or ""),
            fallback_trade_date_keys=("trade_date", "source_scan_timestamp"),
        ),
        _build_source(
            key="confirmation",
            label="午盘确认",
            payload=confirmation,
            expected_date=expected,
            now=current,
            threshold_seconds=thresholds["confirmation"],
            session_key=str(session.get("key") or ""),
            fallback_trade_date_keys=("trade_date",),
        ),
        _build_source(
            key="decision_brief",
            label="总控简报",
            payload=decision_brief,
            expected_date=expected,
            now=current,
            threshold_seconds=thresholds["decision_brief"],
            session_key=str(session.get("key") or ""),
            fallback_trade_date_keys=("trade_date",),
        ),
    ]
    source_map = {item["key"]: item for item in sources}

    lanes = (quality_status or {}).get("lanes") or {}
    quality_items = [
        _build_quality(
            key="watchlist",
            title="自选股质检",
            lanes=lanes,
            expected_date=expected,
            now=current,
            threshold_seconds=quality_thr["watchlist"],
        ),
        _build_quality(
            key="aggressive",
            title="进攻型早盘质检",
            lanes=lanes,
            expected_date=expected,
            now=current,
            threshold_seconds=quality_thr["aggressive"],
        ),
        _build_quality(
            key="midday_confirmation",
            title="午盘确认质检",
            lanes=lanes,
            expected_date=expected,
            now=current,
            threshold_seconds=quality_thr["midday_confirmation"],
        ),
    ]
    quality_map = {item["key"]: item for item in quality_items}

    # Morning sessions happen before the midday confirmation producer is due.
    # Treat that artifact as future work, not missing data, so the command
    # center does not ask the operator to manually refresh something that the
    # scheduler is intentionally waiting to run at 13:45.
    if session.get("key") in {"premarket", "morning"}:
        _defer_source_until_session(source_map["confirmation"], reason="awaiting_midday_confirmation_window")
        _defer_quality_until_session(quality_map["midday_confirmation"], reason="awaiting_midday_confirmation_window")

    blockers: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    recommended_tasks: list[str] = []

    def add_recommendation(task: str) -> None:
        if task not in recommended_tasks:
            recommended_tasks.append(task)

    # Core source rules ---------------------------------------------------
    is_pre_midday = session["key"] in {"premarket", "morning"}
    is_post_midday = session["key"] in {"midday", "afternoon", "post_close"}
    is_trading_day = bool(session.get("is_trading_day"))

    # watchlist must be live in every weekday session
    wl = source_map["watchlist"]
    if wl["stale"] or not wl["available"]:
        blockers.append({
            "code": "watchlist_stale",
            "label": wl["label"],
            "message": _stale_message(wl, expected),
            "recommended_task": "watchlist_refresh",
        })
        add_recommendation("watchlist_refresh")

    # screening / aggressive batch
    sb = source_map["screening"]
    if sb["stale"] or not sb["available"]:
        blockers.append({
            "code": "screening_stale",
            "label": sb["label"],
            "message": _stale_message(sb, expected),
            "recommended_task": "aggressive",
        })
        add_recommendation("aggressive")

    # confirmation: warning in the morning, blocker after midday
    cf = source_map["confirmation"]
    if not cf.get("deferred") and (cf["stale"] or not cf["available"]):
        # The canonical confirmation artifact (midday_verification_result.json)
        # is produced by ``run_midday_confirmation.sh`` — i.e. the
        # ``midday_confirmation`` task.  ``midday_refresh`` writes a different
        # file and would NOT clear this blocker, so we must point operators at
        # the right script.
        details = {
            "code": "confirmation_missing" if not cf["available"] else "confirmation_stale",
            "label": cf["label"],
            "message": _stale_message(cf, expected),
            "recommended_task": "midday_confirmation",
        }
        if is_pre_midday:
            warnings.append(details)
        else:
            blockers.append(details)
            add_recommendation("midday_confirmation")

    # decision brief
    db = source_map["decision_brief"]
    if db["stale"] or not db["available"]:
        blockers.append({
            "code": "decision_brief_stale",
            "label": db["label"],
            "message": _stale_message(db, expected),
            "recommended_task": "command_brief",
        })
        add_recommendation("command_brief")

    for item in sources:
        if not item.get("degraded") or item.get("stale") or not item.get("available"):
            continue
        task = {
            "watchlist": "watchlist_refresh",
            "screening": "aggressive",
            "confirmation": "midday_confirmation",
            "decision_brief": "command_brief",
        }.get(str(item.get("key") or ""), "command_brief")
        warnings.append({
            "code": f"{item['key']}_degraded",
            "label": item["label"],
            "message": _degraded_message(item),
            "recommended_task": task,
        })

    # Quality rules -------------------------------------------------------
    if not quality_map["watchlist"]["timely"]:
        blockers.append({
            "code": "quality_watchlist_stale",
            "label": quality_map["watchlist"]["title"],
            "message": _quality_message(quality_map["watchlist"], expected),
            "recommended_task": "watchlist_refresh",
        })
        add_recommendation("watchlist_refresh")

    if not quality_map["aggressive"]["timely"]:
        blockers.append({
            "code": "quality_aggressive_stale",
            "label": quality_map["aggressive"]["title"],
            "message": _quality_message(quality_map["aggressive"], expected),
            "recommended_task": "aggressive",
        })
        add_recommendation("aggressive")

    if not quality_map["midday_confirmation"].get("deferred") and not quality_map["midday_confirmation"]["timely"]:
        # The midday_confirmation lane is regenerated by run_midday_confirmation.sh.
        # midday_refresh produces a different lane (midday_refresh_result.json)
        # and would not refresh this quality artifact, so we must recommend
        # the task that actually clears the blocker.
        details = {
            "code": "quality_midday_stale",
            "label": quality_map["midday_confirmation"]["title"],
            "message": _quality_message(quality_map["midday_confirmation"], expected),
            "recommended_task": "midday_confirmation",
        }
        if is_pre_midday:
            warnings.append(details)
        else:
            blockers.append(details)
            add_recommendation("midday_confirmation")

    # Trade-date alignment ------------------------------------------------
    data_trade_dates = [
        item["trade_date"]
        for item in sources
        if item["available"] and item["trade_date"]
    ]
    data_trade_date = _pick_trade_date(data_trade_dates) if data_trade_dates else None

    if data_trade_date and data_trade_date != expected:
        blockers.append({
            "code": "trade_date_mismatch",
            "label": "数据交易日",
            "message": (
                f"数据交易日 {data_trade_date} 不是预期的 {expected}，请重新跑核心链路。"
            ),
            "recommended_task": "watchlist_refresh",
        })

    # Mode resolution -----------------------------------------------------
    stale_count = sum(1 for item in sources if item["stale"])
    source_refresh_tasks = {
        "watchlist": "watchlist_refresh",
        "screening": "aggressive",
        "confirmation": "midday_confirmation",
        "decision_brief": "command_brief",
    }
    formal_blockers = [
        {
            "code": f"{item['key']}_formal_not_allowed",
            "label": item["label"],
            "message": _formal_authority_message(item),
            "recommended_task": source_refresh_tasks.get(str(item.get("key") or ""), "command_brief"),
        }
        for item in sources
        if item.get("manifest_path") and not bool(item.get("formal_decision_allowed"))
    ]

    # Account-state evaluation (does NOT alter data-side blockers; only
    # tightens the live-ready gate when the operator has opted into a real-
    # money mode).  We compute it before the final mode pick so the
    # account-side blockers participate in the same decision.
    account_state = _build_account_state(
        account_book=account_book,
        today_action_decisions=today_action_decisions,
        now=current,
        expected_date=expected,
    )
    blockers.extend(account_state["blockers"])
    warnings.extend(account_state["warnings"])
    for task in account_state["recommended_tasks"]:
        add_recommendation(task)

    if not is_trading_day:
        # Weekend / holiday / unknown calendar: at most shadow_only, never
        # live_ready.  We surface the specific reason from the session
        # classifier so the operator knows whether it's a weekend, a known
        # exchange holiday, or a date past the published calendar horizon.
        readiness_mode = "shadow_only"
        if session.get("calendar_status") == "holiday":
            non_trading_message = "当前为交易所休市日，仅做影子盘观察，不要按页面执行真钱操作。"
        elif session.get("calendar_status") == "unknown":
            non_trading_message = (
                "交易日历尚未覆盖该日期，无法确认是否开市；先做影子盘观察并升级日历。"
            )
        else:
            non_trading_message = "当前不是交易日，仅做观察 / 影子盘，不要按页面执行真钱操作。"
        warnings.append({
            "code": "non_trading_day",
            "label": session["label"],
            "message": non_trading_message,
            "recommended_task": "command_brief",
        })
        ready = False
    elif blockers:
        readiness_mode = "blocked"
        ready = False
    elif _readiness_blocking_warnings(warnings):
        readiness_mode = "shadow_only"
        ready = False
    else:
        readiness_mode = "live_ready"
        ready = True

    # Brief alignment used by the legacy `brief_is_live` flag -------------
    db = source_map["decision_brief"]
    brief_is_live = bool(
        db["available"]
        and db["trade_date"] == expected
        and not db["stale"]
        and ready
    )

    if not recommended_tasks:
        # Nothing is broken — point operators at the natural next step.
        recommended_tasks = ["command_brief"]

    # Phase 1 additive translation layer (no existing field is changed).
    source_state_map: dict[str, str] = {}
    for row in sources:
        key = str(row.get("key") or "").strip()
        if not key:
            continue
        source_state_map[key] = classify_source_row(row).value

    base_payload_for_caps = {
        "ready": ready,
        "readiness_mode": readiness_mode,
        "formal_ready": not formal_blockers,
        "session": session,
        "source_freshness": sources,
        "blockers": blockers,
        "warnings": warnings,
        "stale_count": stale_count,
        "checked_at": current.strftime("%Y-%m-%d %H:%M:%S"),
        "recommended_tasks": recommended_tasks,
        "account_state": account_state,
    }
    capability_reports = evaluate_capabilities(
        readiness_payload=base_payload_for_caps,
        now=current,
    )
    capabilities_payload = {key: report.as_dict() for key, report in capability_reports.items()}

    return {
        "expected_trade_date": expected,
        "data_trade_date": data_trade_date,
        "display_date": current.strftime("%Y-%m-%d"),
        "checked_at": current.strftime("%Y-%m-%d %H:%M:%S"),
        "session": session,
        "calendar_horizon": CALENDAR_HORIZON.strftime("%Y-%m-%d"),
        "readiness_mode": readiness_mode,
        "ready": ready,
        "brief_is_live": brief_is_live,
        "stale_count": stale_count,
        "blockers": blockers,
        "warnings": warnings,
        "formal_ready": not formal_blockers,
        "formal_blockers": formal_blockers,
        "source_freshness": sources,
        "quality_freshness": quality_items,
        "recommended_tasks": recommended_tasks,
        "account_state": account_state,
        "source_states": source_state_map,
        "capabilities": capabilities_payload,
    }


# ---------------------------------------------------------------------------
# Account-state contributions
# ---------------------------------------------------------------------------


def _build_account_state(
    *,
    account_book: Mapping[str, Any] | None,
    today_action_decisions: Mapping[str, Any] | None,
    now: datetime,
    expected_date: str,
) -> dict[str, Any]:
    """Translate the account book into readiness contributions.

    Returns a dict with:

    * ``mode`` / ``mode_label``
    * ``cash_balance``, ``equity_at_cost``, ``positions_count``
    * ``reconciliation``: ``{count, age_seconds, fresh, last}``
    * ``unreconciled_intents``: list of stale "done" actions without fills
    * ``blockers`` / ``warnings`` / ``recommended_tasks`` to merge into the
      top-level readiness payload.
    """

    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    recommended: list[str] = []

    # Reconciliation delta thresholds for live_small (CNY)
    RECON_CASH_DELTA_THRESHOLD = 100.0
    RECON_EQUITY_DELTA_THRESHOLD = 200.0

    if account_book is None:
        # Caller didn't opt-in to account-state evaluation.  Treat as
        # research mode and surface a single warning so the UI can prompt
        # the operator to set the mode explicitly before going live.
        return {
            "mode": "research",
            "mode_label": "研究态",
            "mode_tone": "info",
            "cash_balance": 0.0,
            "equity_at_cost": 0.0,
            "positions_count": 0,
            "fills_count": 0,
            "reconciliation": {"count": 0, "age_seconds": None, "fresh": False, "last": None},
            "unreconciled_intents": [],
            "blockers": blockers,
            "warnings": warnings,
            "recommended_tasks": recommended,
            "ready_for_live_small": False,
        }

    mode = str(account_book.get("mode") or "research").strip().lower()
    cash_balance = _to_money(account_book.get("cash_balance"))
    unsafe_bypass_active = bool(account_book.get("unsafe_bypass_active"))
    unsafe_bypass_note = str(account_book.get("unsafe_bypass_note") or "").strip()
    fills = list(account_book.get("fills") or [])
    positions = _summarize_positions(fills)
    open_positions = [p for p in positions.values() if p["qty"] > 0]
    equity_at_cost = round(sum(p["cost_basis"] for p in open_positions), 2)

    recon_items = list(account_book.get("reconciliations") or [])
    recon_age = _last_reconciliation_age(recon_items, now)
    recon_fresh_threshold = 36 * 3600
    recon_summary = {
        "count": len(recon_items),
        "age_seconds": recon_age,
        "age_label": _age_label(recon_age),
        "fresh_within_seconds": recon_fresh_threshold,
        "fresh": recon_age is not None and recon_age <= recon_fresh_threshold,
        "last": recon_items[-1] if recon_items else None,
    }

    pending = _find_unreconciled_intents(
        fills=fills,
        no_fill_intents=list(account_book.get("no_fill_intents") or []),
        decisions_store=today_action_decisions,
        today_str=now.strftime("%Y-%m-%d"),
    )

    if cash_balance < 0:
        warnings.append(
            {
                "code": "account_cash_negative",
                "label": "账户现金",
                "message": (
                    f"本地账本现金为 {cash_balance:.2f} 元，通常表示已录入买入成交，"
                    "但尚未补录入金 / 初始现金。请先在现金调整里记录入金，或确认这只是研究 / 影子盘账本。"
                ),
                "recommended_task": "portfolio_cash",
            }
        )
        recommended.append("portfolio_cash")

    if mode == "live_small":
        if unsafe_bypass_active:
            warnings.append(
                {
                    "code": "account_unsafe_bypass_active",
                    "label": "Unsafe Bypass",
                    "message": (
                        f"当前 live_small 是通过 allow_unsafe 进入的，原因：{unsafe_bypass_note or '未填写'}。"
                        "在重新完成正常校验前，不要把页面状态视为绿色放行。"
                    ),
                    "recommended_task": "portfolio_mode",
                }
            )
        if cash_balance <= 0:
            blockers.append(
                {
                    "code": "account_cash_zero",
                    "label": "实盘现金",
                    "message": "实盘账户现金余额为 0，请先记录入金或调回研究态。",
                    "recommended_task": "portfolio_cash",
                }
            )
            recommended.append("portfolio_cash")
        if not recon_summary["fresh"]:
            blockers.append(
                {
                    "code": "account_reconcile_stale",
                    "label": "账户对账",
                    "message": (
                        "实盘账户超过 36 小时未对账，先核对券商现金 / 持仓再继续按页面执行。"
                    ),
                    "recommended_task": "portfolio_reconcile",
                }
            )
            recommended.append("portfolio_reconcile")
        else:
            # Reconciliation is fresh — check delta thresholds
            last_recon = recon_summary.get("last")
            if last_recon:
                delta_cash = abs(_to_money(last_recon.get("delta_cash")))
                delta_equity = abs(_to_money(last_recon.get("delta_equity")))
                if delta_cash > RECON_CASH_DELTA_THRESHOLD or delta_equity > RECON_EQUITY_DELTA_THRESHOLD:
                    blockers.append(
                        {
                            "code": "account_reconcile_delta_exceeded",
                            "label": "对账差异超阈值",
                            "message": (
                                f"最近对账现金差异 {delta_cash:.2f} 元、权益差异 {delta_equity:.2f} 元，"
                                f"超过阈值（现金 {RECON_CASH_DELTA_THRESHOLD:.0f}、权益 {RECON_EQUITY_DELTA_THRESHOLD:.0f}），"
                                "请先核对并修正账本或重新对账。"
                            ),
                            "recommended_task": "portfolio_reconcile",
                        }
                    )
                    recommended.append("portfolio_reconcile")
        if pending:
            blockers.append(
                {
                    "code": "account_unreconciled_intents",
                    "label": "未对账动作",
                    "message": (
                        f"有 {len(pending)} 条历史 done 动作未绑定成交或 no_fill 备注，"
                        "请先补录成交或标记为无成交。"
                    ),
                    "recommended_task": "portfolio_reconcile",
                }
            )
            recommended.append("portfolio_reconcile")
    elif mode == "shadow":
        if pending:
            warnings.append(
                {
                    "code": "account_unreconciled_intents",
                    "label": "未对账动作",
                    "message": (
                        f"影子盘有 {len(pending)} 条历史 done 动作未绑定成交，"
                        "实盘前先补全。"
                    ),
                    "recommended_task": "portfolio_reconcile",
                }
            )
        if not recon_summary["fresh"] and (cash_balance > 0 or fills):
            warnings.append(
                {
                    "code": "account_reconcile_stale",
                    "label": "账户对账",
                    "message": "影子盘账本距上次对账已超过 36 小时，建议尽快对账后再切换实盘。",
                    "recommended_task": "portfolio_reconcile",
                }
            )

    ready_for_live_small = (
        mode == "live_small"
        and cash_balance > 0
        and recon_summary["fresh"]
        and not pending
        and not unsafe_bypass_active
    )

    # Additional check: if reconciliation is fresh but delta exceeds threshold, not ready
    if ready_for_live_small and recon_summary.get("last"):
        last_recon = recon_summary["last"]
        delta_cash = abs(_to_money(last_recon.get("delta_cash")))
        delta_equity = abs(_to_money(last_recon.get("delta_equity")))
        if delta_cash > RECON_CASH_DELTA_THRESHOLD or delta_equity > RECON_EQUITY_DELTA_THRESHOLD:
            ready_for_live_small = False

    return {
        "mode": mode,
        "mode_label": {"research": "研究态", "shadow": "影子盘", "live_small": "小额实盘"}.get(
            mode, mode
        ),
        "mode_tone": {"research": "info", "shadow": "watch", "live_small": "risk"}.get(
            mode, "info"
        ),
        "cash_balance": cash_balance,
        "equity_at_cost": equity_at_cost,
        "positions_count": len(open_positions),
        "fills_count": len(fills),
        "unsafe_bypass_active": unsafe_bypass_active,
        "unsafe_bypass_note": unsafe_bypass_note,
        "reconciliation": recon_summary,
        "unreconciled_intents": pending,
        "blockers": blockers,
        "warnings": warnings,
        "recommended_tasks": recommended,
        "ready_for_live_small": ready_for_live_small,
    }


def _to_money(value: Any) -> float:
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _last_reconciliation_age(items: list[Mapping[str, Any]], now: datetime) -> int | None:
    if not items:
        return None
    last = items[-1]
    parsed = _parse_dt(last.get("ts"))
    if parsed is None:
        return None
    return _age_seconds(now, parsed)


def _summarize_positions(fills: list[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Lightweight position aggregation duplicated from account_book.

    We keep a copy here so readiness has zero dependency on the account_book
    module (avoids circular imports and keeps readiness side-effect free).
    The math matches ``account_book._compute_positions``.
    """

    positions: dict[str, dict[str, Any]] = {}
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
            {"code": code, "qty": 0, "avg_cost": 0.0, "cost_basis": 0.0},
        )
        if side == "buy":
            new_qty = pos["qty"] + qty
            new_cost = pos["cost_basis"] + qty * price + fees
            pos["qty"] = new_qty
            pos["cost_basis"] = round(new_cost, 2)
            pos["avg_cost"] = round(new_cost / new_qty, 2) if new_qty else 0.0
        elif side == "sell":
            sell_qty = min(qty, pos["qty"])
            new_qty = pos["qty"] - sell_qty
            if new_qty <= 0:
                pos["qty"] = 0
                pos["cost_basis"] = 0.0
                pos["avg_cost"] = 0.0
            else:
                pos["qty"] = new_qty
                pos["cost_basis"] = round(pos["avg_cost"] * new_qty, 2)
    return positions


def _find_unreconciled_intents(
    *,
    fills: list[Mapping[str, Any]],
    no_fill_intents: list[Mapping[str, Any]],
    decisions_store: Mapping[str, Any] | None,
    today_str: str,
) -> list[dict[str, Any]]:
    if not decisions_store:
        return []
    decisions = decisions_store.get("trade_dates") or {}
    fill_index: set[tuple[str, str]] = set()
    for fill in fills:
        ik = str(fill.get("intent_key") or "").strip()
        td = str(fill.get("trade_date") or "").strip()
        if ik and td:
            fill_index.add((td, ik))

    no_fill_index: set[tuple[str, str]] = set()
    for marker in no_fill_intents:
        ik = str(marker.get("intent_key") or "").strip()
        td = str(marker.get("trade_date") or "").strip()
        if ik and td:
            no_fill_index.add((td, ik))

    pending: list[dict[str, Any]] = []
    for trade_date, items in decisions.items():
        td = str(trade_date or "").strip()
        if not td or td >= today_str:
            continue
        if not isinstance(items, Mapping):
            continue
        for key, payload in items.items():
            if not isinstance(payload, Mapping):
                continue
            if str(payload.get("decision") or "").strip().lower() != "done":
                continue
            ki = str(key or "").strip()
            if not ki:
                continue
            if (td, ki) in fill_index or (td, ki) in no_fill_index:
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


# ---------------------------------------------------------------------------
# Internal formatting helpers
# ---------------------------------------------------------------------------


def _stale_message(source: Mapping[str, Any], expected: str) -> str:
    label = source["label"]
    if not source["available"]:
        return f"{label} 暂无数据，无法判断当日状态。"
    parts: list[str] = []
    if source.get("trade_date") and source["trade_date"] != expected:
        parts.append(
            f"{label} 仍停留在 {source['trade_date']}（应为 {expected}）"
        )
    if source.get("age_label") and source["age_label"] != "-":
        parts.append(f"距上次更新 {source['age_label']}")
    return "；".join(parts) or f"{label} 已超出新鲜度阈值。"


def _quality_message(quality: Mapping[str, Any], expected: str) -> str:
    title = quality["title"]
    if quality["validation_status"] != "ok":
        return f"{title} 当前状态 {quality['validation_status']}。"
    if quality.get("checked_trade_date") and quality["checked_trade_date"] != expected:
        return (
            f"{title} 最新校验是 {quality['checked_trade_date']}（应为 {expected}）。"
        )
    if quality.get("age_label") and quality["age_label"] != "-":
        return f"{title} 距上次校验 {quality['age_label']}。"
    return f"{title} 校验信息缺失。"


def _degraded_message(source: Mapping[str, Any]) -> str:
    label = str(source.get("label") or "数据源")
    reasons = [str(item) for item in source.get("degradation_reasons") or []]
    if any("fallback" in item for item in reasons):
        return f"{label} 已刷新；部分上游使用降级/回退来源，已在 Formal 闸门中标记。"
    if any("live_small" in item for item in reasons):
        return f"{label} 已刷新；上游 live/formal 权限未完全通过，已在 Formal 闸门中标记。"
    if any("freshness" in item for item in reasons):
        return f"{label} 已刷新；部分上游 freshness 未完全通过，已在 Formal 闸门中标记。"
    return f"{label} 已刷新；仍存在上游降级信号，已在 Formal 闸门中标记。"


def _readiness_blocking_warnings(warnings: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Warnings that should keep the operator in shadow mode.

    Pipeline degradation warnings describe source-authority / formal-readiness
    gaps.  They are displayed and tracked separately, but they should not make
    fresh, same-day, quality-passing operational data look "not ready".
    """

    return [
        item
        for item in warnings
        if not str(item.get("code") or "").endswith("_degraded")
    ]


def _formal_authority_message(source: Mapping[str, Any]) -> str:
    label = str(source.get("label") or "数据源")
    lane = str(source.get("source_lane") or "unknown")
    provider = str(source.get("provider") or "-")
    target = str(source.get("target_authority_provider") or source.get("authority_provider") or "-")
    flags = [str(flag) for flag in source.get("authority_flags") or []]
    if "fallback_provider" in flags or "fallback_display_only" in flags:
        return f"{label} 当前使用回退源 {provider}，只能观察，不能进入 formal 决策。"
    if any(flag.startswith("target_authority_not_in_use:") for flag in flags):
        return f"{label} 当前源为 {provider}，目标权威源是 {target}；可用于 {lane} 观察，尚不能进入 formal 决策。"
    return f"{label} 尚未满足 formal 数据源闸门；当前源 {provider}，目标权威源 {target}。"


def _pick_trade_date(values: Iterable[str]) -> str | None:
    """Return the most-recent trade_date from a set of source values."""

    cleaned = sorted({v for v in values if v}, reverse=True)
    return cleaned[0] if cleaned else None
