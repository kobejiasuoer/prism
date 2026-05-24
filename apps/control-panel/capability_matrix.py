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

Capability dependencies are derived from ``source_budget.SOURCE_BUDGETS``
(``critical_for`` / ``important_for``) — that registry is the single source
of truth. A critical dataset that is not fresh blocks the capability; an
important dataset that is not fresh degrades it without blocking.

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
from source_budget import SOURCE_BUDGETS


__all__ = [
    "Capability",
    "CapabilityReport",
    "TrustLevel",
    "evaluate_capabilities",
    "evaluate_trust_level",
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
_DATASET_TO_SOURCE_KEY: dict[str, str] = {v: k for k, v in _SOURCE_KEY_TO_DATASET.items()}


def _build_capability_dataset_map() -> dict[str, dict[str, tuple[str, ...]]]:
    """Derive {cap: {critical: (...), important: (...)}} from SOURCE_BUDGETS.

    Datasets with role=account are excluded — they are checked separately
    via the dedicated account_mode/account_ready gate, not via the source
    freshness loop.
    """
    out: dict[str, dict[str, list[str]]] = {
        cap.value: {"critical": [], "important": []} for cap in Capability
    }
    for budget in SOURCE_BUDGETS.values():
        if budget.role == "account":
            continue
        for cap in budget.critical_for:
            bucket = out.setdefault(cap, {"critical": [], "important": []})
            bucket["critical"].append(budget.dataset)
        for cap in budget.important_for:
            bucket = out.setdefault(cap, {"critical": [], "important": []})
            bucket["important"].append(budget.dataset)
    return {
        cap: {k: tuple(v) for k, v in items.items()}
        for cap, items in out.items()
    }


_CAPABILITY_DATASETS = _build_capability_dataset_map()


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


# Business-language fallback labels for short readiness keys.
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

    # Optional bottom-level dataset freshness (rows keyed by full dataset id).
    dataset_states: dict[str, FreshnessState] = {}
    dataset_rows = readiness_payload.get("dataset_freshness") or []
    for row in dataset_rows:
        key = str(row.get("dataset") or row.get("key") or "").strip()
        if not key:
            continue
        dataset_states[key] = classify_source_row(row)

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
            dataset_states=dataset_states,
            sources=sources,
            dataset_rows=dataset_rows,
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
    dataset_states: Mapping[str, FreshnessState],
    sources: list[Mapping[str, Any]],
    dataset_rows: list[Mapping[str, Any]],
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
        return CapabilityReport(
            capability=capability,
            status="ok",
            granted=True,
            last_checked_at=checked_at,
        )

    deps = _CAPABILITY_DATASETS.get(capability.value) or {"critical": (), "important": ()}
    critical_datasets = set(deps["critical"])
    important_datasets = set(deps["important"])

    # Merge pipeline-level (short keys → datasets) with bottom-level (dataset keys directly).
    all_states: dict[str, FreshnessState] = {}
    for source_key, state in source_states.items():
        dataset = _SOURCE_KEY_TO_DATASET.get(source_key, source_key)
        all_states[dataset] = state
    for dataset, state in dataset_states.items():
        all_states[dataset] = state

    blocking_sources: list[str] = []
    why_not: list[dict[str, str]] = []
    degraded_path: list[dict[str, str]] = []
    next_actions: list[dict[str, Any]] = []

    has_critical_block = False
    has_degraded = False
    seen_codes: set[str] = set()

    for dataset, state in all_states.items():
        is_critical = dataset in critical_datasets
        is_important = dataset in important_datasets
        if not is_critical and not is_important:
            continue
        label = _label_for_dataset(sources, dataset_rows, dataset)
        code = f"{_code_for_dataset(dataset)}_{state.value}"

        if state_allows(state, capability.value):
            if state is FreshnessState.DEGRADED and code not in seen_codes:
                # Surface allowed-but-degraded as informational why_not.
                why_not.append({
                    "code": code,
                    "label": label,
                    "message": _humanize_state_for_capability(state, capability, label),
                })
                seen_codes.add(code)
                has_degraded = True
            continue

        # State NOT allowed for this capability.
        if code not in seen_codes:
            why_not.append({
                "code": code,
                "label": label,
                "message": _humanize_state_for_capability(state, capability, label),
            })
            seen_codes.add(code)

        if is_critical:
            has_critical_block = True
            if dataset not in blocking_sources:
                blocking_sources.append(dataset)
        else:
            has_degraded = True

    # Capability-specific non-dataset gates.
    if capability in (Capability.APPROVE, Capability.TRADE) and not readiness_ready:
        why_not.append({
            "code": "system_not_ready",
            "label": "系统就绪状态",
            "message": "系统判断为未就绪，先恢复核心数据再考虑放行或交易。",
        })

    if capability is Capability.APPROVE and readiness_ready and not formal_ready:
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

    # Recommended tasks: pull from readiness blockers; let the consumer decide
    # what to surface.
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

    if has_critical_block or _capability_hard_blocked(why_not):
        status = "blocked"
        granted = False
    elif has_degraded or why_not:
        status = "degraded"
        granted = False
    else:
        status = "ok"
        granted = True

    if not granted:
        degraded_path = _build_degraded_path(capability, source_states, dataset_states, sources)

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
    hard_codes = {"system_not_ready", "account_not_live"}
    return any(item.get("code") in hard_codes for item in why_not)


def _code_for_dataset(dataset_key: str) -> str:
    """Stable short identifier for use in why_not codes.

    Uses the readiness short key when available (so existing tests/UI keep
    matching watchlist_stale etc.), otherwise the dataset key with dots
    replaced by underscores.
    """
    short = _DATASET_TO_SOURCE_KEY.get(dataset_key)
    if short:
        return short
    return dataset_key.replace(".", "_")


def _label_for_dataset(
    sources: list[Mapping[str, Any]],
    dataset_rows: list[Mapping[str, Any]],
    dataset_key: str,
) -> str:
    short = _DATASET_TO_SOURCE_KEY.get(dataset_key)
    for row in sources:
        row_key = str(row.get("key") or "").strip()
        if row_key and (row_key == short or row_key == dataset_key):
            label = str(row.get("label") or "").strip()
            if label:
                return label
    for row in dataset_rows:
        row_key = str(row.get("dataset") or row.get("key") or "").strip()
        if row_key == dataset_key:
            label = str(row.get("label") or "").strip()
            if label:
                return label
    budget = SOURCE_BUDGETS.get(dataset_key)
    if budget:
        return budget.label
    if short:
        return _SOURCE_BUSINESS_LABELS.get(short, short)
    return dataset_key


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


@dataclass(frozen=True)
class TrustLevel:
    """Single three-state trust verdict consumed by every UI surface.

    Maps the 6-capability matrix into one answer to "can the user trust
    today's data?". Surfaces use the same verdict so sidebar, command center,
    stock page and observation pool never disagree.
    """

    level: str                              # "trusted" | "observe_only" | "unreliable"
    label: str                              # 可信 / 仅可观察 / 数据失信
    tone: str                               # good / warning / negative
    headline: str                           # one operator-facing sentence
    can_observe: bool
    can_review: bool
    can_approve: bool
    can_trade_live: bool
    blocking_reasons: list[str] = field(default_factory=list)
    next_step: str | None = None            # recommended task name
    next_step_label: str | None = None      # human-readable task label
    last_checked_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "label": self.label,
            "tone": self.tone,
            "headline": self.headline,
            "can_observe": self.can_observe,
            "can_review": self.can_review,
            "can_approve": self.can_approve,
            "can_trade_live": self.can_trade_live,
            "blocking_reasons": list(self.blocking_reasons),
            "next_step": self.next_step,
            "next_step_label": self.next_step_label,
            "last_checked_at": self.last_checked_at,
        }


_TASK_LABELS: dict[str, str] = {
    "watchlist_refresh": "刷新自选股快照",
    "aggressive": "重跑进攻型选股",
    "screening": "重跑进攻型选股",
    "midday_confirmation": "重跑午盘承接确认",
    "command_brief": "重生成投资总控简报",
    "portfolio_cash": "修复账户现金口径",
    "account_reconcile": "完成账户对账",
}


def _task_label(task_name: str | None) -> str | None:
    if not task_name:
        return None
    return _TASK_LABELS.get(task_name, task_name)


def evaluate_trust_level(
    *,
    readiness_payload: Mapping[str, Any],
    capabilities: Mapping[str, Mapping[str, Any]] | None = None,
    now: datetime | None = None,
) -> TrustLevel:
    """Collapse the capability matrix into a single trust verdict.

    Rules:
    * ``unreliable`` — observe is blocked. Data is too broken to look at.
    * ``observe_only`` — observe is granted but approve is not. The page is
      readable but today's decisions cannot be promoted to real money.
    * ``trusted`` — approve is granted. Real-money execution is gated only
      by account mode, which is reported separately via ``can_trade_live``.
    """

    if capabilities is None:
        reports = evaluate_capabilities(readiness_payload=readiness_payload, now=now)
        capabilities = {key: report.as_dict() for key, report in reports.items()}

    def _granted(key: str) -> bool:
        entry = capabilities.get(key) or {}
        return bool(entry.get("granted"))

    def _status(key: str) -> str:
        entry = capabilities.get(key) or {}
        return str(entry.get("status") or "").strip().lower()

    can_observe = _granted("observe")
    can_review = _granted("review")
    can_approve = _granted("approve")
    can_trade_live = _granted("trade")

    # "Unreliable" only when observe is fully blocked. A degraded observe still
    # supports look-only usage, which belongs to "observe_only", not "unreliable".
    observe_blocked = _status("observe") == "blocked"

    checked_at = str(readiness_payload.get("checked_at") or "")
    if not checked_at:
        checked_at = (now or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")

    readiness_mode = str(readiness_payload.get("readiness_mode") or "").strip().lower()

    # readiness_mode is the upstream truth: blocked / shadow_only / live_ready.
    # Trust verdict respects it so the sidebar never disagrees with the home page.
    if observe_blocked:
        source_cap = capabilities.get("observe") or {}
        level = "unreliable"
        label = "数据失信"
        tone = "negative"
        headline = "关键数据失信，今日不作为任何判断依据。先按恢复指引把数据补齐再继续。"
    elif readiness_mode in {"blocked", "shadow_only"} or not can_approve:
        source_cap = capabilities.get("approve") or {}
        level = "observe_only"
        label = "仅可观察"
        tone = "warning"
        if readiness_mode == "blocked":
            headline = "关键数据被阻断，今日只看不动；先按恢复指引修复再考虑放行。"
        else:
            headline = "数据可观察可复核，但今日不可作为真钱执行依据。先补齐缺口再考虑放行。"
    else:
        source_cap = capabilities.get("trade") or capabilities.get("approve") or {}
        level = "trusted"
        label = "可信"
        tone = "good"
        if can_trade_live:
            headline = "数据完备，今日可作为正式判断与真钱执行的依据。"
        else:
            headline = "数据完备，可作为正式判断依据；真钱执行还受账户模式约束，按需切换。"

    blocking_reasons: list[str] = []
    seen: set[str] = set()
    for entry in source_cap.get("why_not") or []:
        message = str(entry.get("message") or entry.get("label") or "").strip()
        if not message or message in seen:
            continue
        seen.add(message)
        blocking_reasons.append(message)
        if len(blocking_reasons) >= 3:
            break

    # Prefer top-level readiness recommendation; fall back to the source capability's first action.
    next_step: str | None = None
    recommended_tasks = list(readiness_payload.get("recommended_tasks") or [])
    if recommended_tasks:
        next_step = str(recommended_tasks[0]).strip() or None
    if not next_step:
        actions = source_cap.get("next_actions") or []
        if actions:
            next_step = str(actions[0].get("task_name") or "").strip() or None

    return TrustLevel(
        level=level,
        label=label,
        tone=tone,
        headline=headline,
        can_observe=can_observe,
        can_review=can_review,
        can_approve=can_approve,
        can_trade_live=can_trade_live,
        blocking_reasons=blocking_reasons,
        next_step=next_step,
        next_step_label=_task_label(next_step),
        last_checked_at=checked_at,
    )


def _build_degraded_path(
    capability: Capability,
    source_states: Mapping[str, FreshnessState],
    dataset_states: Mapping[str, FreshnessState],
    sources: list[Mapping[str, Any]],
) -> list[dict[str, str]]:
    paths: list[dict[str, str]] = []
    combined_states = list(source_states.values()) + list(dataset_states.values())
    if capability is not Capability.OBSERVE and any(
        state_allows(state, "observe") for state in combined_states
    ):
        paths.append({
            "code": "observe_available",
            "label": "仍可观察",
            "message": "你仍然可以观察行情、读简报和判断链，只是当前动作被暂时阻塞。",
        })
    if capability in (Capability.APPROVE, Capability.TRADE) and any(
        state_allows(state, "review") for state in combined_states
    ):
        paths.append({
            "code": "review_available",
            "label": "仍可复核",
            "message": "数据已经足够支撑复核与影子推演；待阻塞项恢复后再做正式放行。",
        })
    return paths
