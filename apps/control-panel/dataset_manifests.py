"""Build readiness-compatible freshness rows from dataset manifests.

These rows describe bottom-level (provider-fetched) datasets like
``quotes.batch`` and ``capital_flow.batch``, in the same shape as
``readiness.source_freshness`` so they can be consumed by
``freshness_state.classify_source_row`` and the capability matrix.

The dataset list is driven by SOURCE_BUDGETS: any budget whose role is not
``pipeline_artifact`` (those are aggregated by readiness/source_freshness)
and not ``account`` (handled via account_state) is inspected. This keeps
the bottom-level freshness signal in lockstep with the business profile
registry.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

from prism_data.freshness import compute_freshness_status, update_manifest_freshness
from prism_data.manifest import DATASET_REGISTRY
from prism_data.repositories import DatasetRepository
from prism_data.utils import default_dataset_repository_root

from source_budget import SOURCE_BUDGETS
from trading_calendar import calendar_status, most_recent_trading_day
try:
    from watchlist_registry import list_active_watchlist_stocks
except Exception:  # pragma: no cover - status can still render fixed formal datasets.
    list_active_watchlist_stocks = None  # type: ignore[assignment]


__all__ = [
    "build_dataset_freshness_rows",
    "build_formal_freshness_rows",
    "DATASET_FRESHNESS_DATASETS",
    "FORMAL_FRESHNESS_DATASETS",
    "formal_reference_trade_date",
]


_EXCLUDED_ROLES = {"pipeline_artifact", "account"}
DATASET_FRESHNESS_DATASETS: tuple[str, ...] = tuple(
    budget.dataset for budget in SOURCE_BUDGETS.values()
    if budget.role not in _EXCLUDED_ROLES
)
FORMAL_FRESHNESS_DATASETS: tuple[str, ...] = (
    "trade_calendar",
    "bars.daily",
    "adjustment.factor",
    "benchmark.index_daily",
    "price_limit.daily",
    "execution.flags",
)

_FORMAL_LABELS: dict[str, str] = {
    "trade_calendar": "交易日历",
    "bars.daily": "正式日线",
    "adjustment.factor": "复权因子",
    "benchmark.index_daily": "基准指数日线",
    "price_limit.daily": "涨跌停价格",
    "execution.flags": "执行约束",
}
_FORMAL_FIXED_REQUEST_KEYS: dict[str, tuple[str, ...]] = {
    "trade_calendar": ("formal-calendar",),
    "benchmark.index_daily": ("000300", "000905"),
    "price_limit.daily": ("formal-price-limit",),
    "execution.flags": ("formal-execution-flags",),
}
_FORMAL_PRIOR_CLOSE_DATASETS: frozenset[str] = frozenset({
    "bars.daily",
    "adjustment.factor",
    "benchmark.index_daily",
})


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in (
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M",
        "%Y-%m-%d_%H-%M-%S", "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


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
    return f"{hours // 24} 天前"


def _uses_post_close_tolerance(now: datetime) -> bool:
    status = str(calendar_status(now).get("status") or "")
    return status != "trading" or now.hour >= 15


def _effective_ttl_seconds(dataset: str, manifest: dict[str, Any], now: datetime) -> int:
    ttl_seconds = int(manifest.get("ttl_seconds") or 0)
    definition = DATASET_REGISTRY.get(dataset)
    if definition is not None and _uses_post_close_tolerance(now):
        ttl_seconds = max(ttl_seconds, int(definition.ttl_post_close or 0))
    return ttl_seconds


def _effective_target_freshness_seconds(dataset: str, fallback_seconds: int, now: datetime) -> int:
    definition = DATASET_REGISTRY.get(dataset)
    if definition is not None and _uses_post_close_tolerance(now):
        return max(int(fallback_seconds), int(definition.ttl_post_close or 0))
    return int(fallback_seconds)


def _refresh_dataset_manifest(
    *,
    dataset: str,
    manifest: dict[str, Any],
    expected_date: str,
    now: datetime,
) -> dict[str, Any]:
    payload = dict(manifest)
    ttl_seconds = _effective_ttl_seconds(dataset, payload, now)
    payload["ttl_seconds"] = ttl_seconds
    payload["freshness_status"] = compute_freshness_status(
        fetched_at=payload.get("asof") or payload.get("fetched_at"),
        ttl_seconds=ttl_seconds,
        trade_date=str(payload.get("trade_date") or ""),
        expected_trade_date=expected_date,
        now=now,
    )
    return payload


def _manifest_status_ok(manifest: dict[str, Any]) -> bool:
    status = str(manifest.get("status") or "").strip().lower()
    return status in {"", "ok"}


def _latest_manifest(
    *,
    repository: DatasetRepository,
    dataset: str,
    expected_date: str,
    now: datetime,
) -> dict[str, Any] | None:
    try:
        manifests = repository.list_manifests(dataset, expected_date)
    except Exception:
        return None
    if not manifests:
        return None
    refreshed = [
        _refresh_dataset_manifest(
            dataset=dataset,
            manifest=dict(item),
            expected_date=expected_date,
            now=now,
        )
        for item in manifests
    ]

    def sort_key(m: dict[str, Any]) -> tuple[int, datetime]:
        parsed = _parse_dt(m.get("asof")) or _parse_dt(m.get("fetched_at")) or datetime.min
        usable = 1 if _manifest_status_ok(m) and parsed != datetime.min else 0
        return usable, parsed

    return max(refreshed, key=sort_key)


def _formal_stock_keys() -> tuple[str, ...]:
    if list_active_watchlist_stocks is None:
        return ("600690",)
    try:
        codes = [
            str(item.get("code") or "").strip()
            for item in list_active_watchlist_stocks()
            if str(item.get("code") or "").strip()
        ]
    except Exception:
        codes = []
    return tuple(dict.fromkeys(codes)) or ("600690",)


def _formal_required_keys(dataset: str) -> tuple[str, ...]:
    if dataset in {"bars.daily", "adjustment.factor"}:
        return _formal_stock_keys()
    return _FORMAL_FIXED_REQUEST_KEYS.get(dataset, ())


def _previous_trading_day_text(expected_date: str) -> str:
    anchor = datetime.strptime(expected_date, "%Y-%m-%d") - timedelta(days=1)
    return most_recent_trading_day(anchor).strftime("%Y-%m-%d")


def formal_reference_trade_date(dataset: str, *, expected_date: str, now: datetime) -> str:
    dataset_key = str(dataset or "").strip()
    if dataset_key not in _FORMAL_PRIOR_CLOSE_DATASETS:
        return expected_date
    if calendar_status(now).get("status") != "trading":
        return expected_date
    if now.hour >= 15:
        return expected_date
    return _previous_trading_day_text(expected_date)


def _load_formal_key_manifests(
    *,
    repository: DatasetRepository,
    dataset: str,
    expected_date: str,
    now: datetime,
) -> tuple[list[dict[str, Any]], list[str]]:
    required_keys = _formal_required_keys(dataset)
    manifests: list[dict[str, Any]] = []
    missing: list[str] = []
    for key in required_keys:
        manifest = repository.load_manifest(dataset, expected_date, key)
        if not manifest:
            missing.append(key)
            continue
        manifests.append(update_manifest_freshness(dict(manifest), expected_date, now=now))
    return manifests, missing


def _formal_blocking_reasons(manifest: dict[str, Any], *, expected_date: str) -> list[str]:
    trade_date = str(manifest.get("trade_date") or "").strip()
    freshness_status = str(manifest.get("freshness_status") or "").strip().lower()
    status = str(manifest.get("status") or "").strip().lower()
    reasons: list[str] = []
    if status and status != "ok":
        reasons.append(f"manifest_status_{status}")
    if not freshness_status:
        reasons.append("freshness_unknown")
    if trade_date and trade_date != expected_date:
        reasons.append("trade_date_mismatch")
    elif not trade_date:
        reasons.append("trade_date_unknown")
    if not bool(manifest.get("source_authority_ready")):
        reasons.append("source_authority_not_ready")
    if not bool(manifest.get("formal_decision_allowed")):
        reasons.append("formal_not_allowed")
    if not (manifest.get("asof") or manifest.get("fetched_at")):
        reasons.append("missing")
    return reasons


def _merge_formal_manifests(
    *,
    dataset: str,
    label: str,
    target_provider: str,
    manifests: list[dict[str, Any]],
    missing_keys: list[str],
    requested_date: str,
    expected_date: str,
    now: datetime,
    ttl_seconds: int,
) -> dict[str, Any]:
    def sort_key(m: dict[str, Any]) -> datetime:
        return _parse_dt(m.get("asof")) or _parse_dt(m.get("fetched_at")) or datetime.min

    representative = max(manifests, key=sort_key)
    raw_value = representative.get("asof") or representative.get("fetched_at")
    parsed = _parse_dt(raw_value)
    age_seconds = max(int((now - parsed).total_seconds()), 0) if parsed else None
    stale_reasons: list[str] = []
    for key in missing_keys:
        stale_reasons.append(f"missing_request_key:{key}")
    blocked_keys: list[str] = []
    key_states: list[dict[str, Any]] = []
    for manifest in manifests:
        key = str(manifest.get("request_key") or "").strip()
        reasons = _formal_blocking_reasons(manifest, expected_date=expected_date)
        if reasons:
            blocked_keys.append(key)
            for reason in reasons:
                if reason not in stale_reasons:
                    stale_reasons.append(reason)
        key_states.append({
            "request_key": key,
            "status": manifest.get("status"),
            "trade_date": manifest.get("trade_date"),
            "row_count": manifest.get("row_count"),
            "formal_decision_allowed": bool(manifest.get("formal_decision_allowed")),
            "source_authority_ready": bool(manifest.get("source_authority_ready")),
            "quality_flags": list(manifest.get("quality_flags") or []),
            "error": manifest.get("error"),
            "manifest_path": manifest.get("manifest_path"),
        })

    provider_values = [str(item.get("provider") or "") for item in manifests if item.get("provider")]
    quality_flags: list[str] = []
    for manifest in manifests:
        for flag in list(manifest.get("quality_flags") or []):
            if flag not in quality_flags:
                quality_flags.append(flag)

    return {
        "dataset": dataset,
        "key": dataset,
        "label": label,
        "value": str(raw_value or "-"),
        "detail": provider_values[0] if provider_values else "",
        "available": bool(parsed),
        "age_seconds": age_seconds,
        "age_label": _age_label(age_seconds),
        "stale": bool(stale_reasons),
        "stale_after_seconds": ttl_seconds,
        "ttl_seconds": int(representative.get("ttl_seconds") or ttl_seconds),
        "trade_date": str(representative.get("trade_date") or "").strip() or None,
        "expected_trade_date": requested_date,
        "reference_trade_date": expected_date,
        "stale_reasons": stale_reasons,
        "provider": provider_values[0] if provider_values else None,
        "provider_role": representative.get("provider_role"),
        "freshness_status": str(representative.get("freshness_status") or "").strip().lower(),
        "fallback_used": any(bool(item.get("fallback_used")) for item in manifests),
        "live_small_allowed": all(bool(item.get("live_small_allowed")) for item in manifests),
        "manifest_path": representative.get("manifest_path"),
        "source_lane": representative.get("source_lane"),
        "decision_scope": representative.get("decision_scope"),
        "authority_provider": representative.get("authority_provider"),
        "target_authority_provider": representative.get("target_authority_provider") or target_provider,
        "audit_providers": list(representative.get("audit_providers") or []),
        "source_authority_ready": all(bool(item.get("source_authority_ready")) for item in manifests) and not missing_keys,
        "formal_decision_allowed": all(bool(item.get("formal_decision_allowed")) for item in manifests) and not missing_keys,
        "authority_flags": list(representative.get("authority_flags") or []),
        "quality_flags": quality_flags,
        "license_scope": representative.get("license_scope"),
        "source_endpoint": representative.get("source_endpoint"),
        "error": next((item.get("error") for item in manifests if item.get("error")), None),
        "dataset_manifest": True,
        "required_request_keys": list(_formal_required_keys(dataset)),
        "missing_request_keys": missing_keys,
        "blocked_request_keys": blocked_keys,
        "key_states": key_states,
    }


def build_dataset_freshness_rows(
    *,
    expected_date: str,
    now: datetime,
    datasets: tuple[str, ...] = DATASET_FRESHNESS_DATASETS,
) -> list[dict[str, Any]]:
    """Build bottom-level dataset freshness rows for the readiness payload.

    Each row matches the shape of ``readiness.source_freshness`` so it can
    be consumed by ``freshness_state.classify_source_row``. The ``dataset``
    field carries the full dataset key (e.g. ``quotes.batch``).
    """
    try:
        repository = DatasetRepository(
            os.environ.get("PRISM_DATASET_REPOSITORY_ROOT", "").strip()
            or default_dataset_repository_root()
        )
    except Exception:
        return []

    rows: list[dict[str, Any]] = []
    for dataset_key in datasets:
        budget = SOURCE_BUDGETS.get(dataset_key)
        if budget is None:
            continue
        manifest = _latest_manifest(
            repository=repository,
            dataset=dataset_key,
            expected_date=expected_date,
            now=now,
        )
        if not manifest:
            definition = DATASET_REGISTRY.get(dataset_key)
            rows.append({
                "dataset": dataset_key,
                "key": dataset_key,
                "label": budget.label,
                "value": "-",
                "detail": "dataset_manifest_missing",
                "available": False,
                "age_seconds": None,
                "age_label": "-",
                "stale": True,
                "stale_after_seconds": budget.target_freshness_seconds,
                "trade_date": None,
                "stale_reasons": ["manifest_missing"],
                "provider": None,
                "provider_role": None,
                "freshness_status": "expired",
                "fallback_used": False,
                "live_small_allowed": False,
                "manifest_path": None,
                "source_lane": definition.source_lane if definition else None,
                "decision_scope": definition.decision_scope if definition else None,
                "authority_provider": definition.authority_provider if definition else None,
                "target_authority_provider": definition.target_authority_provider if definition else None,
                "audit_providers": list(definition.audit_providers) if definition else [],
                "source_authority_ready": False,
                "formal_decision_allowed": False,
                "authority_flags": [],
                "dataset_manifest": True,
            })
            continue

        raw_value = manifest.get("asof") or manifest.get("fetched_at")
        parsed = _parse_dt(raw_value)
        age_seconds = max(int((now - parsed).total_seconds()), 0) if parsed else None
        trade_date = str(manifest.get("trade_date") or "").strip() or None
        freshness_status = str(manifest.get("freshness_status") or "").strip().lower()
        status = str(manifest.get("status") or "").strip().lower()
        status_ok = _manifest_status_ok(manifest)
        definition = DATASET_REGISTRY.get(dataset_key)
        requires_live_small = bool(definition and definition.required_for_live_small)
        stale_after_seconds = _effective_target_freshness_seconds(
            dataset_key,
            budget.target_freshness_seconds,
            now,
        )
        reasons: list[str] = []
        if status and status != "ok":
            reasons.append(f"manifest_status_{status}")
        if freshness_status in {"stale", "expired"}:
            reasons.append(f"freshness_{freshness_status}")
        elif not freshness_status:
            reasons.append("freshness_unknown")
        if (
            age_seconds is not None
            and age_seconds > stale_after_seconds
            and "freshness_stale" not in reasons
            and "freshness_expired" not in reasons
        ):
            reasons.append("freshness_stale")
        if trade_date and trade_date != expected_date:
            if requires_live_small:
                reasons.append("trade_date_mismatch")
            elif "freshness_stale" not in reasons and "freshness_expired" not in reasons:
                reasons.append("freshness_stale")
        elif not trade_date:
            reasons.append("trade_date_unknown")
        if requires_live_small and not bool(manifest.get("live_small_allowed")):
            reasons.append("live_small_not_allowed")
        if (
            requires_live_small
            and bool(manifest.get("fallback_used"))
            and not bool(manifest.get("live_small_allowed"))
        ):
            reasons.append("fallback_not_allowed")
        if not parsed:
            reasons.append("missing")
        if manifest.get("error") and not status_ok:
            reasons.append("provider_failure")

        rows.append({
            "dataset": dataset_key,
            "key": dataset_key,
            "label": budget.label,
            "value": str(raw_value or "-"),
            "detail": str(manifest.get("provider") or ""),
            "available": bool(parsed) and status_ok,
            "age_seconds": age_seconds,
            "age_label": _age_label(age_seconds),
            "stale": bool(reasons),
            "stale_after_seconds": stale_after_seconds,
            "ttl_seconds": int(manifest.get("ttl_seconds") or 0),
            "trade_date": trade_date,
            "stale_reasons": reasons,
            "provider": manifest.get("provider"),
            "provider_role": manifest.get("provider_role"),
            "freshness_status": freshness_status,
            "fallback_used": bool(manifest.get("fallback_used")),
            "live_small_allowed": bool(manifest.get("live_small_allowed")),
            "manifest_path": manifest.get("manifest_path"),
            "source_lane": manifest.get("source_lane"),
            "decision_scope": manifest.get("decision_scope"),
            "authority_provider": manifest.get("authority_provider"),
            "target_authority_provider": manifest.get("target_authority_provider"),
            "audit_providers": list(manifest.get("audit_providers") or []),
            "source_authority_ready": bool(manifest.get("source_authority_ready", True)),
            "formal_decision_allowed": bool(manifest.get("formal_decision_allowed")),
            "authority_flags": list(manifest.get("authority_flags") or []),
            "dataset_manifest": True,
        })
    return rows


def build_formal_freshness_rows(
    *,
    expected_date: str,
    now: datetime,
    datasets: tuple[str, ...] = FORMAL_FRESHNESS_DATASETS,
) -> list[dict[str, Any]]:
    """Build formal-source rows without enrolling them in live capability gates."""
    try:
        repository = DatasetRepository(
            os.environ.get("PRISM_DATASET_REPOSITORY_ROOT", "").strip()
            or default_dataset_repository_root()
        )
    except Exception:
        return []

    rows: list[dict[str, Any]] = []
    for dataset_key in datasets:
        definition = DATASET_REGISTRY.get(dataset_key)
        label = _FORMAL_LABELS.get(dataset_key, dataset_key)
        ttl_seconds = int((definition.ttl_intraday if definition else 86400) or 86400)
        reference_date = formal_reference_trade_date(dataset_key, expected_date=expected_date, now=now)
        target_provider = ""
        if definition is not None:
            target_provider = definition.target_authority_provider or definition.authority_provider or definition.primary_provider
        key_manifests, missing_keys = _load_formal_key_manifests(
            repository=repository,
            dataset=dataset_key,
            expected_date=reference_date,
            now=now,
        )
        if key_manifests:
            rows.append(_merge_formal_manifests(
                dataset=dataset_key,
                label=label,
                target_provider=target_provider,
                manifests=key_manifests,
                missing_keys=missing_keys,
                requested_date=expected_date,
                expected_date=reference_date,
                now=now,
                ttl_seconds=ttl_seconds,
            ))
            continue

        manifest = _latest_manifest(
            repository=repository,
            dataset=dataset_key,
            expected_date=reference_date,
            now=now,
        )
        if not manifest:
            missing = list(missing_keys or _formal_required_keys(dataset_key))
            rows.append({
                "dataset": dataset_key,
                "key": dataset_key,
                "label": label,
                "value": "-",
                "detail": "formal_manifest_missing",
                "available": False,
                "age_seconds": None,
                "age_label": "-",
                "stale": True,
                "stale_after_seconds": ttl_seconds,
                "ttl_seconds": ttl_seconds,
                "trade_date": None,
                "stale_reasons": ["manifest_missing"],
                "provider": None,
                "target_authority_provider": target_provider,
                "source_authority_ready": False,
                "formal_decision_allowed": False,
                "authority_flags": ["formal_manifest_missing"],
                "expected_trade_date": expected_date,
                "reference_trade_date": reference_date,
                "required_request_keys": list(_formal_required_keys(dataset_key)),
                "missing_request_keys": missing,
                "blocked_request_keys": [],
                "key_states": [],
                "dataset_manifest": True,
            })
            continue

        raw_value = manifest.get("asof") or manifest.get("fetched_at")
        parsed = _parse_dt(raw_value)
        age_seconds = max(int((now - parsed).total_seconds()), 0) if parsed else None
        trade_date = str(manifest.get("trade_date") or "").strip() or None
        freshness_status = str(manifest.get("freshness_status") or "").strip().lower()
        status = str(manifest.get("status") or "").strip().lower()
        reasons: list[str] = []
        if status and status != "ok":
            reasons.append(f"manifest_status_{status}")
        if not freshness_status:
            reasons.append("freshness_unknown")
        if trade_date and trade_date != reference_date:
            reasons.append("trade_date_mismatch")
        elif not trade_date:
            reasons.append("trade_date_unknown")
        if not bool(manifest.get("source_authority_ready")):
            reasons.append("source_authority_not_ready")
        if not bool(manifest.get("formal_decision_allowed")):
            reasons.append("formal_not_allowed")
        if not parsed:
            reasons.append("missing")

        rows.append({
            "dataset": dataset_key,
            "key": dataset_key,
            "label": label,
            "value": str(raw_value or "-"),
            "detail": str(manifest.get("provider") or ""),
            "available": bool(parsed),
            "age_seconds": age_seconds,
            "age_label": _age_label(age_seconds),
            "stale": bool(reasons),
            "stale_after_seconds": ttl_seconds,
            "ttl_seconds": int(manifest.get("ttl_seconds") or ttl_seconds),
            "trade_date": trade_date,
            "expected_trade_date": expected_date,
            "reference_trade_date": reference_date,
            "stale_reasons": reasons,
            "provider": manifest.get("provider"),
            "provider_role": manifest.get("provider_role"),
            "freshness_status": freshness_status,
            "fallback_used": bool(manifest.get("fallback_used")),
            "live_small_allowed": bool(manifest.get("live_small_allowed")),
            "manifest_path": manifest.get("manifest_path"),
            "source_lane": manifest.get("source_lane"),
            "decision_scope": manifest.get("decision_scope"),
            "authority_provider": manifest.get("authority_provider"),
            "target_authority_provider": manifest.get("target_authority_provider") or target_provider,
            "audit_providers": list(manifest.get("audit_providers") or []),
            "source_authority_ready": bool(manifest.get("source_authority_ready")),
            "formal_decision_allowed": bool(manifest.get("formal_decision_allowed")),
            "authority_flags": list(manifest.get("authority_flags") or []),
            "quality_flags": list(manifest.get("quality_flags") or []),
            "license_scope": manifest.get("license_scope"),
            "source_endpoint": manifest.get("source_endpoint"),
            "error": manifest.get("error"),
            "required_request_keys": list(_formal_required_keys(dataset_key)),
            "missing_request_keys": list(missing_keys),
            "blocked_request_keys": [str(manifest.get("request_key") or "").strip()],
            "key_states": [
                {
                    "request_key": str(manifest.get("request_key") or "").strip(),
                    "status": manifest.get("status"),
                    "trade_date": manifest.get("trade_date"),
                    "row_count": manifest.get("row_count"),
                    "formal_decision_allowed": bool(manifest.get("formal_decision_allowed")),
                    "source_authority_ready": bool(manifest.get("source_authority_ready")),
                    "quality_flags": list(manifest.get("quality_flags") or []),
                    "error": manifest.get("error"),
                    "manifest_path": manifest.get("manifest_path"),
                }
            ],
            "dataset_manifest": True,
        })
    return rows
