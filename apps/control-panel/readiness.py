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
    (mainly for tests and replay sessions).  When that override is missing,
    weekdays return today, weekends fall back to the previous weekday so the
    page still has a meaningful baseline — but ``compute_readiness`` will
    refuse to mark the system ``live_ready`` on those non-trading days.

    TODO(holiday-calendar): this helper currently treats every weekday as a
    trading day.  A-share market closes for several multi-day holidays
    (Spring Festival, May Day, National Day, Tomb-Sweeping, etc.) and even
    when stale data lines up across all sources we will *technically* be
    inside the live_ready check on those days.  Risk: on the first weekday
    after a holiday, expected_trade_date == today even though the previous
    trading day was further back, so a partially-aligned snapshot may look
    cleaner than it should.  Mitigation today: every freshness check still
    runs against ``age_seconds`` thresholds, so genuinely stale artifacts
    will still trip ``age_exceeded`` and end up blocked.  Plan: wire a
    static A-share holiday list (or akshare ``tool_trade_date_hist_sina``)
    and have this helper roll forward/back to the nearest trading session.
    Tracked separately to keep this PR scoped to readiness fixes.
    """

    override = os.environ.get("PRISM_EXPECTED_TRADE_DATE", "").strip()
    if override:
        normalized = _date_str(override)
        if normalized:
            return normalized

    current = now or datetime.now()
    if current.date().weekday() >= 5:
        return _previous_weekday(current.date()).strftime("%Y-%m-%d")
    return current.strftime("%Y-%m-%d")


def current_session(now: datetime | None = None) -> dict[str, Any]:
    """Best-effort A-share session classifier (Asia/Shanghai assumption).

    The control panel runs locally and we already assume host time is in
    market timezone elsewhere, so we use the host clock directly.
    """

    current = now or datetime.now()
    weekday = current.weekday()
    if weekday >= 5:
        return {"key": "weekend", "label": "周末休市", "is_trading_day": False}

    minutes = current.hour * 60 + current.minute
    if minutes < 9 * 60:
        return {"key": "premarket", "label": "盘前", "is_trading_day": True}
    if minutes < 11 * 60 + 30:
        return {"key": "morning", "label": "早盘", "is_trading_day": True}
    if minutes < 13 * 60:
        return {"key": "midday", "label": "午间", "is_trading_day": True}
    if minutes < 15 * 60:
        return {"key": "afternoon", "label": "午后", "is_trading_day": True}
    return {"key": "post_close", "label": "盘后", "is_trading_day": True}


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
    trade_date_field: str = "trade_date",
    timestamp_field: str = "generated_at",
    fallback_trade_date_keys: Sequence[str] = (),
) -> dict[str, Any]:
    payload = payload or {}
    raw_value = payload.get(timestamp_field)
    parsed = _parse_dt(raw_value)
    age = _age_seconds(now, parsed)

    raw_trade_date = payload.get(trade_date_field)
    if not raw_trade_date:
        for alt in fallback_trade_date_keys:
            if payload.get(alt):
                raw_trade_date = payload.get(alt)
                break
    if not raw_trade_date and parsed:
        raw_trade_date = parsed.strftime("%Y-%m-%d")
    data_trade_date = _date_str(raw_trade_date)

    available = bool(parsed)
    reasons: list[str] = []
    stale = False

    if not available:
        stale = True
        reasons.append("missing")

    if data_trade_date and data_trade_date != expected_date:
        stale = True
        reasons.append("trade_date_mismatch")

    if not data_trade_date and available:
        stale = True
        reasons.append("trade_date_unknown")

    if age is not None and age > threshold_seconds:
        stale = True
        reasons.append("age_exceeded")

    detail = payload.get("trade_date") or payload.get("pool_label") or payload.get("validation_status") or ""

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
        "stale_after_seconds": threshold_seconds,
        "stale_reasons": reasons,
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
    now: datetime | None = None,
    expected_date: str | None = None,
    source_thresholds: Mapping[str, int] | None = None,
    quality_thresholds: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Compute the unified readiness payload.

    The caller passes already-loaded canonical artifacts; we never touch the
    filesystem from here so the function is easy to test.
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
            fallback_trade_date_keys=("date",),
        ),
        _build_source(
            key="screening",
            label="观察池基线",
            payload=screening_batch,
            expected_date=expected,
            now=current,
            threshold_seconds=thresholds["screening"],
            fallback_trade_date_keys=("trade_date", "source_scan_timestamp"),
        ),
        _build_source(
            key="confirmation",
            label="午盘确认",
            payload=confirmation,
            expected_date=expected,
            now=current,
            threshold_seconds=thresholds["confirmation"],
            fallback_trade_date_keys=("trade_date",),
        ),
        _build_source(
            key="decision_brief",
            label="总控简报",
            payload=decision_brief,
            expected_date=expected,
            now=current,
            threshold_seconds=thresholds["decision_brief"],
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
    if cf["stale"] or not cf["available"]:
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

    if not quality_map["midday_confirmation"]["timely"]:
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

    if not is_trading_day:
        # Weekend / holiday: at most shadow_only, never live_ready.
        readiness_mode = "shadow_only"
        warnings.append({
            "code": "non_trading_day",
            "label": session["label"],
            "message": "当前不是交易日，仅做观察 / 影子盘，不要按页面执行真钱操作。",
            "recommended_task": "command_brief",
        })
        ready = False
    elif blockers:
        readiness_mode = "blocked"
        ready = False
    elif warnings:
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

    return {
        "expected_trade_date": expected,
        "data_trade_date": data_trade_date,
        "display_date": current.strftime("%Y-%m-%d"),
        "checked_at": current.strftime("%Y-%m-%d %H:%M:%S"),
        "session": session,
        "readiness_mode": readiness_mode,
        "ready": ready,
        "brief_is_live": brief_is_live,
        "stale_count": stale_count,
        "blockers": blockers,
        "warnings": warnings,
        "source_freshness": sources,
        "quality_freshness": quality_items,
        "recommended_tasks": recommended_tasks,
    }


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


def _pick_trade_date(values: Iterable[str]) -> str | None:
    """Return the most-recent trade_date from a set of source values."""

    cleaned = sorted({v for v in values if v}, reverse=True)
    return cleaned[0] if cleaned else None
