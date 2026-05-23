"""Investment-action capability matrix.

Translates the engineering-language readiness payload into six business
capabilities the operator actually cares about:

* observe       — look at data, see the market
* review        — read the brief, follow the judgment chain
* approve       — promote a candidate into the formal action queue
* trade         — execute (manually, via broker) with real money
* notify        — send Feishu alerts
* ledger_capture — write to the real account book / reconciliation

For each capability we emit a CapabilityReport with ``status`` (ok /
degraded / blocked), ``why_not`` (operator-facing reasons), ``degraded_path``
(what is still possible when blocked) and ``next_actions`` (recommended
tasks).

Design constraint enforced by tests: ``why_not`` and ``degraded_path``
messages MUST NOT contain engineering jargon (manifest, stale_reasons,
live_small_not_allowed, formal_decision_allowed, freshness_status,
fallback_used).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping

from freshness_state import FreshnessState, classify_source_row, state_allows


__all__ = [
    "Capability",
    "CapabilityReport",
    "evaluate_capabilities",
]


class Capability(str, Enum):
    OBSERVE = "observe"
    REVIEW = "review"
    APPROVE = "approve"
    TRADE = "trade"
    NOTIFY = "notify"
    LEDGER_CAPTURE = "ledger_capture"


# Map readiness ``source.key`` (the short pipeline names) to the dataset
# keys used in source_budget. The mapping reflects that pipeline-side names
# are coarser than the underlying datasets.
_SOURCE_KEY_TO_DATASET: dict[str, str] = {
    "watchlist": "watchlist.snapshot",
    "screening": "screening.batch",
    "confirmation": "screening.confirmation",
    "decision_brief": "decision_brief.snapshot",
}

# Which datasets back each capability. This is the inverse of
# source_budget.supports_capabilities, restated here so capability_matrix
# stays decoupled from a particular registry layout.
_CAPABILITY_REQUIRES: dict[Capability, tuple[str, ...]] = {
    Capability.OBSERVE: ("watchlist.snapshot", "screening.batch", "decision_brief.snapshot"),
    Capability.REVIEW: ("watchlist.snapshot", "screening.batch", "decision_brief.snapshot"),
    Capability.APPROVE: ("watchlist.snapshot", "screening.batch", "screening.confirmation", "decision_brief.snapshot"),
    Capability.TRADE: ("watchlist.snapshot", "screening.confirmation"),
    Capability.NOTIFY: (),
    Capability.LEDGER_CAPTURE: (),
}


@dataclass(frozen=True)
class CapabilityReport:
    capability: Capability
    status: str                             # "ok" | "degraded" | "blocked"
    granted: bool
    why_not: list[dict[str, str]] = field(default_factory=list)
    degraded_path: list[dict[str, str]] = field(default_factory=list)
    next_actions: list[dict[str, Any]] = field(default_factory=list)
    blocking_sources: list[str] = field(default_factory=list)
    last_checked_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability.value,
            "status": self.status,
            "granted": self.granted,
            "why_not": list(self.why_not),
            "degraded_path": list(self.degraded_path),
            "next_actions": list(self.next_actions),
            "blocking_sources": list(self.blocking_sources),
            "last_checked_at": self.last_checked_at,
        }


# Business-language fallback labels for source keys (used when readiness
# row's own ``label`` field is missing).
_SOURCE_BUSINESS_LABELS: dict[str, str] = {
    "watchlist": "自选股数据",
    "screening": "进攻型候选数据",
    "confirmation": "午盘承接确认",
    "decision_brief": "投资总控简报",
}


def evaluate_capabilities(
    *,
    readiness_payload: Mapping[str, Any],
    now: datetime | None = None,
) -> dict[str, CapabilityReport]:
    """Translate a readiness payload into 6 CapabilityReports.

    Returns a dict keyed by capability enum value so it round-trips through
    JSON cleanly.
    """
    checked_at = str(readiness_payload.get("checked_at") or "")
    if not checked_at:
        checked_at = (now or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")

    sources = readiness_payload.get("source_freshness") or []
    source_states: dict[str, FreshnessState] = {}
    for row in sources:
        key = str(row.get("key") or "").strip()
        if not key:
            continue
        source_states[key] = classify_source_row(row)

    account_state = readiness_payload.get("account_state") or {}
    account_mode = str(account_state.get("mode") or "research").strip().lower()
    account_ready = bool(account_state.get("ready_for_live_small"))
    recon = account_state.get("reconciliation") or {}
    recon_fresh = bool(recon.get("fresh"))

    is_trading_day = bool((readiness_payload.get("session") or {}).get("is_trading_day"))
    formal_ready = bool(readiness_payload.get("formal_ready"))
    readiness_ready = bool(readiness_payload.get("ready"))

    blockers = list(readiness_payload.get("blockers") or [])

    reports: dict[str, CapabilityReport] = {}
    for capability in Capability:
        reports[capability.value] = _evaluate_one(
            capability=capability,
            source_states=source_states,
            sources=sources,
            blockers=blockers,
            is_trading_day=is_trading_day,
            formal_ready=formal_ready,
            readiness_ready=readiness_ready,
            account_mode=account_mode,
            account_ready=account_ready,
            recon_fresh=recon_fresh,
            checked_at=checked_at,
        )
    return reports


def _evaluate_one(
    *,
    capability: Capability,
    source_states: Mapping[str, FreshnessState],
    sources: list[Mapping[str, Any]],
    blockers: list[Mapping[str, Any]],
    is_trading_day: bool,
    formal_ready: bool,
    readiness_ready: bool,
    account_mode: str,
    account_ready: bool,
    recon_fresh: bool,
    checked_at: str,
) -> CapabilityReport:
    if capability is Capability.NOTIFY:
        # notify is the always-on lane (alerts must work even when trading is blocked).
        return CapabilityReport(
            capability=capability,
            status="ok",
            granted=True,
            last_checked_at=checked_at,
        )

    required_datasets = _CAPABILITY_REQUIRES[capability]
    blocking_sources: list[str] = []
    why_not: list[dict[str, str]] = []
    degraded_path: list[dict[str, str]] = []
    next_actions: list[dict[str, Any]] = []

    # Walk required source keys against the state matrix.
    has_invalid = False
    has_blocked = False
    has_stale = False
    has_degraded = False

    for source_key, state in source_states.items():
        dataset = _SOURCE_KEY_TO_DATASET.get(source_key, source_key)
        if dataset not in required_datasets:
            continue
        if state_allows(state, capability.value):
            if state is FreshnessState.DEGRADED:
                has_degraded = True
            continue
        # Not allowed for this capability.
        blocking_sources.append(dataset)
        label = _source_label(sources, source_key)
        why_not.append({
            "code": f"{source_key}_{state.value}",
            "label": label,
            "message": _humanize_state_for_capability(state, capability, label),
        })
        if state is FreshnessState.INVALID:
            has_invalid = True
        elif state is FreshnessState.BLOCKED:
            has_blocked = True
        else:
            has_stale = True

    # Capability-specific gates (beyond per-source freshness).
    if capability in (Capability.APPROVE, Capability.TRADE) and not readiness_ready:
        why_not.append({
            "code": "system_not_ready",
            "label": "系统就绪状态",
            "message": "系统判断为未就绪，先恢复核心数据再考虑放行或交易。",
        })

    if capability is Capability.APPROVE and readiness_ready and not formal_ready:
        # APPROVE wants formal_ready; degrade when data is fresh but formal isn't.
        why_not.append({
            "code": "formal_authority_pending",
            "label": "权威数据源",
            "message": "当前数据可用于观察与复核，正式放行需要权威数据源就位后再确认。",
        })

    if capability is Capability.TRADE:
        if account_mode not in {"shadow", "live_small"}:
            why_not.append({
                "code": "account_not_live",
                "label": "账户模式",
                "message": "当前为研究态账户，不参与真钱交易。切换到影子盘或小额实盘后再下单。",
            })
        elif not account_ready:
            why_not.append({
                "code": "account_not_reconciled",
                "label": "账户对账",
                "message": "账户尚未对账或对账差异超阈值，先完成对账再下单。",
            })

    if capability is Capability.LEDGER_CAPTURE:
        if account_mode == "research":
            why_not.append({
                "code": "ledger_capture_research",
                "label": "账本写入",
                "message": "当前为研究态，不写真实账本。",
            })
        elif not recon_fresh and account_mode == "live_small":
            why_not.append({
                "code": "ledger_capture_stale_recon",
                "label": "对账新鲜度",
                "message": "对账信息偏旧，写入账本前请先刷新对账。",
            })

    # Recommended tasks: pull from the readiness blockers list, filtered to
    # ones that match the sources we're blocking on. This is the user's "what
    # to do next" handle.
    seen_tasks: set[str] = set()
    for blocker in blockers:
        task = str(blocker.get("recommended_task") or "").strip()
        if not task or task in seen_tasks:
            continue
        seen_tasks.add(task)
        next_actions.append({
            "task_name": task,
            "reason": str(blocker.get("code") or ""),
            "label": str(blocker.get("label") or ""),
        })

    # Status + granted decision.
    if has_invalid or has_blocked or _capability_hard_blocked(why_not):
        status = "blocked"
        granted = False
    elif has_stale or has_degraded or why_not:
        status = "degraded"
        granted = False
    else:
        status = "ok"
        granted = True

    if not granted:
        degraded_path = _build_degraded_path(capability, source_states, sources)

    return CapabilityReport(
        capability=capability,
        status=status,
        granted=granted,
        why_not=why_not,
        degraded_path=degraded_path,
        next_actions=next_actions,
        blocking_sources=blocking_sources,
        last_checked_at=checked_at,
    )


def _capability_hard_blocked(why_not: list[dict[str, str]]) -> bool:
    """True when any why_not entry is a hard non-recoverable code.

    "Hard" = the capability cannot reach status=ok without external state
    changing; freshness alone is not enough.
    """
    hard_codes = {"system_not_ready", "account_not_live"}
    return any(item.get("code") in hard_codes for item in why_not)


def _source_label(sources: list[Mapping[str, Any]], source_key: str) -> str:
    for row in sources:
        if str(row.get("key") or "").strip() == source_key:
            label = str(row.get("label") or "").strip()
            if label:
                return label
    return _SOURCE_BUSINESS_LABELS.get(source_key, source_key)


def _humanize_state_for_capability(
    state: FreshnessState,
    capability: Capability,
    label: str,
) -> str:
    """Operator-facing one-line reason. NO engineering jargon allowed."""
    if state is FreshnessState.INVALID:
        return f"{label}当前不可用，需要重新生成后才能继续。"
    if state is FreshnessState.BLOCKED:
        return f"{label}当前不允许参与真钱执行，只能用于观察。"
    if state is FreshnessState.STALE:
        if capability in (Capability.APPROVE, Capability.TRADE):
            return f"{label}偏旧，先刷新后再做正式放行或交易。"
        return f"{label}偏旧，建议尽快刷新。"
    if state is FreshnessState.DEGRADED:
        return f"{label}走的是次级数据源，正式放行需要等待权威数据回归。"
    if state is FreshnessState.USABLE:
        return f"{label}接近过期阈值，建议尽快刷新。"
    return f"{label}状态需要确认。"


def _build_degraded_path(
    capability: Capability,
    source_states: Mapping[str, FreshnessState],
    sources: list[Mapping[str, Any]],
) -> list[dict[str, str]]:
    """Tell the user what they CAN do even though this capability is blocked."""
    paths: list[dict[str, str]] = []
    # If any source supports observe, surface that as a fallback.
    if capability is not Capability.OBSERVE and any(
        state_allows(state, "observe") for state in source_states.values()
    ):
        paths.append({
            "code": "observe_available",
            "label": "仍可观察",
            "message": "你仍然可以观察行情、读简报和判断链，只是当前动作被暂时阻塞。",
        })
    if capability in (Capability.APPROVE, Capability.TRADE) and any(
        state_allows(state, "review") for state in source_states.values()
    ):
        paths.append({
            "code": "review_available",
            "label": "仍可复核",
            "message": "数据已经足够支撑复核与影子推演；待阻塞项恢复后再做正式放行。",
        })
    return paths
