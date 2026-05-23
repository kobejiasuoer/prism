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
from datetime import datetime
from typing import Any

from prism_data.freshness import update_manifest_freshness
from prism_data.repositories import DatasetRepository
from prism_data.utils import default_dataset_repository_root

from source_budget import SOURCE_BUDGETS


__all__ = ["build_dataset_freshness_rows", "DATASET_FRESHNESS_DATASETS"]


_EXCLUDED_ROLES = {"pipeline_artifact", "account"}
DATASET_FRESHNESS_DATASETS: tuple[str, ...] = tuple(
    budget.dataset for budget in SOURCE_BUDGETS.values()
    if budget.role not in _EXCLUDED_ROLES
)


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
    refreshed = [update_manifest_freshness(dict(item), expected_date, now=now) for item in manifests]

    def sort_key(m: dict[str, Any]) -> datetime:
        return _parse_dt(m.get("asof")) or _parse_dt(m.get("fetched_at")) or datetime.min

    return max(refreshed, key=sort_key)


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
        if freshness_status in {"stale", "expired"}:
            reasons.append(f"freshness_{freshness_status}")
        elif not freshness_status:
            reasons.append("freshness_unknown")
        if trade_date and trade_date != expected_date:
            reasons.append("trade_date_mismatch")
        elif not trade_date:
            reasons.append("trade_date_unknown")
        if not bool(manifest.get("live_small_allowed")):
            reasons.append("live_small_not_allowed")
        if bool(manifest.get("fallback_used")) and not bool(manifest.get("live_small_allowed")):
            reasons.append("fallback_not_allowed")
        if not parsed:
            reasons.append("missing")

        rows.append({
            "dataset": dataset_key,
            "key": dataset_key,
            "label": budget.label,
            "value": str(raw_value or "-"),
            "detail": str(manifest.get("provider") or ""),
            "available": bool(parsed),
            "age_seconds": age_seconds,
            "age_label": _age_label(age_seconds),
            "stale": bool(reasons),
            "stale_after_seconds": int(manifest.get("ttl_seconds") or budget.target_freshness_seconds),
            "trade_date": trade_date,
            "stale_reasons": reasons,
            "provider": manifest.get("provider"),
            "provider_role": manifest.get("provider_role"),
            "freshness_status": freshness_status,
            "fallback_used": bool(manifest.get("fallback_used")),
            "live_small_allowed": bool(manifest.get("live_small_allowed")),
            "manifest_path": manifest.get("manifest_path"),
            "dataset_manifest": True,
        })
    return rows
