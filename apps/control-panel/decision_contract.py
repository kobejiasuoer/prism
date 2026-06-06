"""Decision Contract v0 for Prism Today actions.

The Today action queue used to answer "what should I look at next?" but
left several harder questions scattered across readiness, capabilities,
source budgets, and the Decision Ledger:

* Which capabilities does this action require?
* Which datasets are part of the action's data budget?
* Is it allowed to become a real-money operation?
* What evidence and ledger key must follow the recommendation?

This module keeps that decision core outside ``dashboard_data.py``.  It
is intentionally additive: callers can attach contracts to existing
queue items without changing the old item shape.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from typing import Any

from freshness_state import FreshnessState, classify_source_row, state_allows
from source_budget import SourceBudget, budgets_for_capability


CONTRACT_SCHEMA_VERSION = "decision_contract.v0"

_STOCK_ACTION_KEY_RE = re.compile(r"^(?P<lane>[a-z_]+):(?P<code>\d{6})$")
_PIPELINE_DATASET_TO_SOURCE_KEY = {
    "watchlist.snapshot": "watchlist",
    "screening.batch": "screening",
    "screening.confirmation": "confirmation",
    "decision_brief.snapshot": "decision_brief",
}
_SOURCE_KEY_TO_PIPELINE_DATASET = {v: k for k, v in _PIPELINE_DATASET_TO_SOURCE_KEY.items()}

_ACTION_KEYWORD_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("forbid", ("禁止", "不可执行", "冻结")),
    ("skip", ("放弃", "跳过", "今日回避")),
    ("reduce", ("减仓", "卖出", "降低仓位", "止盈", "止损")),
    ("trial_buy", ("试错", "买入", "轻仓", "开仓")),
    ("hold", ("继续持有", "持有")),
    ("observe", ("观察", "跟踪", "待确认", "只观察")),
)
_GROUP_ACTION_FALLBACK = {
    "watch": "observe",
    "avoid": "forbid",
}
_REAL_MONEY_ACTIONS = {"trial_buy", "reduce"}
_FORMAL_ACTIONS = {"trial_buy", "reduce", "hold"}


def attach_decision_contracts(
    action_queue: Mapping[str, Any],
    *,
    trade_date: str,
    expected_trade_date: str,
    data_trade_date: str,
    readiness: Mapping[str, Any],
    source_cards: Iterable[Mapping[str, Any]] = (),
    artifacts: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return ``(queue, contract_payload)`` with contracts on each item."""

    enriched_queue = dict(action_queue or {})
    contracts: list[dict[str, Any]] = []
    by_action_key: dict[str, dict[str, Any]] = {}

    def _attach(item: Mapping[str, Any], *, stale: bool) -> dict[str, Any]:
        copied = dict(item)
        contract = build_decision_contract(
            copied,
            trade_date=trade_date,
            expected_trade_date=expected_trade_date,
            data_trade_date=data_trade_date,
            readiness=readiness,
            source_cards=source_cards,
            artifacts=artifacts or {},
            stale=stale,
        )
        copied["decision_contract"] = contract
        copied["allowed_for_real_money"] = bool(contract.get("allowed_for_real_money"))
        copied["execution_constraints"] = list(contract.get("execution_constraints") or [])
        contracts.append(contract)
        action_key = str(contract.get("action_key") or "")
        if action_key and action_key not in by_action_key:
            by_action_key[action_key] = contract
        return copied

    enriched_queue["items"] = [
        _attach(item, stale=False)
        for item in (action_queue.get("items") or [])
        if isinstance(item, Mapping)
    ]
    enriched_queue["stale_items"] = [
        _attach(item, stale=True)
        for item in (action_queue.get("stale_items") or [])
        if isinstance(item, Mapping)
    ]

    summary = _contract_summary(contracts)
    payload = {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "trade_date": str(trade_date or ""),
        "expected_trade_date": str(expected_trade_date or ""),
        "data_trade_date": str(data_trade_date or ""),
        "summary": summary,
        "items": contracts,
        "by_action_key": by_action_key,
    }
    enriched_queue["decision_contracts"] = payload
    return enriched_queue, payload


def build_decision_contract(
    item: Mapping[str, Any],
    *,
    trade_date: str,
    expected_trade_date: str,
    data_trade_date: str,
    readiness: Mapping[str, Any],
    source_cards: Iterable[Mapping[str, Any]] = (),
    artifacts: Mapping[str, Any] | None = None,
    stale: bool = False,
) -> dict[str, Any]:
    """Build one immutable-ish contract from a Today queue item."""

    action_key = str(item.get("key") or "").strip()
    action = normalize_action_intent(item)
    stock = _stock_from_action_key(action_key, item)
    required_capabilities = _required_capabilities(item, action=action, stock=stock)
    capabilities = _capability_snapshot(readiness, required_capabilities)
    data_requirements = _data_requirements(readiness, required_capabilities)
    evidence_refs = _evidence_refs(item, source_cards=source_cards, artifacts=artifacts or {})
    constraints = _execution_constraints(
        item,
        readiness=readiness,
        capabilities=capabilities,
        data_requirements=data_requirements,
        required_capabilities=required_capabilities,
        stale=stale,
    )
    requires_real_money = action in _REAL_MONEY_ACTIONS
    allowed_for_real_money = bool(requires_real_money and not constraints)
    allowed_for_formal_action = bool(action in _FORMAL_ACTIONS and not _formal_constraints(constraints))

    return {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "contract_id": _contract_id(trade_date, action_key, action),
        "action_key": action_key,
        "lane": str(item.get("lane_key") or _lane_from_action_key(action_key) or item.get("group_key") or ""),
        "trade_date": str(trade_date or ""),
        "expected_trade_date": str(expected_trade_date or ""),
        "data_trade_date": str(data_trade_date or ""),
        "stock": stock,
        "action": action,
        "action_label": str(item.get("status") or ""),
        "decision_scope": _decision_scope(data_requirements),
        "readiness_mode": str(readiness.get("readiness_mode") or "blocked"),
        "readiness_ready": bool(readiness.get("ready")),
        "required_capabilities": required_capabilities,
        "capabilities": capabilities,
        "data_requirements": data_requirements,
        "evidence_refs": evidence_refs,
        "execution_constraints": constraints,
        "requires_real_money": requires_real_money,
        "allowed_for_real_money": allowed_for_real_money,
        "allowed_for_formal_action": allowed_for_formal_action,
        "ledger_capture_key": _ledger_capture_key(trade_date, action_key),
        "ledger_capture": {
            "surface": "today_action_queue",
            "capture_required": bool(stock and action_key),
            "capture_stale_items": True,
        },
        "review_obligation": _review_obligation(action=action, stock=stock, constraints=constraints),
    }


def normalize_action_intent(item: Mapping[str, Any]) -> str:
    entry_plan = item.get("entry_plan") if isinstance(item.get("entry_plan"), Mapping) else {}
    text = " ".join(
        str(value or "")
        for value in (
            item.get("status"),
            item.get("title"),
            item.get("detail"),
            item.get("foot"),
            entry_plan.get("action"),
            entry_plan.get("sizing"),
            entry_plan.get("trigger"),
            " ".join(str(metric or "") for metric in (item.get("metrics") or []) if metric),
        )
    )
    for action, keywords in _ACTION_KEYWORD_RULES:
        if any(keyword in text for keyword in keywords):
            return action
    group_key = str(item.get("group_key") or "").strip().lower()
    if group_key in _GROUP_ACTION_FALLBACK:
        return _GROUP_ACTION_FALLBACK[group_key]
    return "unknown"


def _required_capabilities(
    item: Mapping[str, Any],
    *,
    action: str,
    stock: Mapping[str, Any] | None,
) -> list[str]:
    if not stock:
        return ["review"]
    if action in {"forbid", "skip"}:
        return ["review"]
    if action == "observe":
        return ["observe", "review"]
    if action in _REAL_MONEY_ACTIONS:
        return ["review", "approve", "trade", "ledger_capture"]
    if action == "hold":
        return ["review", "approve"]
    group_key = str(item.get("group_key") or "").strip().lower()
    if group_key == "do-now":
        return ["review", "approve"]
    return ["observe", "review"]


def _capability_snapshot(
    readiness: Mapping[str, Any],
    required_capabilities: Iterable[str],
) -> dict[str, dict[str, Any]]:
    matrix = readiness.get("capabilities") or {}
    out: dict[str, dict[str, Any]] = {}
    for capability in required_capabilities:
        report = matrix.get(capability) if isinstance(matrix, Mapping) else None
        if isinstance(report, Mapping):
            out[capability] = {
                "status": str(report.get("status") or ""),
                "granted": bool(report.get("granted")),
                "why_not": list(report.get("why_not") or []),
                "degraded_path": list(report.get("degraded_path") or []),
                "blocking_sources": list(report.get("blocking_sources") or []),
            }
        else:
            out[capability] = {
                "status": "blocked",
                "granted": False,
                "why_not": [{
                    "code": "capability_missing",
                    "label": capability,
                    "message": "能力矩阵缺少这项能力，按阻塞处理。",
                }],
                "degraded_path": [],
                "blocking_sources": [],
            }
    return out


def _data_requirements(
    readiness: Mapping[str, Any],
    required_capabilities: Iterable[str],
) -> list[dict[str, Any]]:
    dataset_rows = _dataset_rows(readiness)
    source_rows = _source_rows(readiness)
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    required = tuple(required_capabilities)
    for capability in required:
        for budget in budgets_for_capability(capability):
            if budget.dataset in seen:
                _merge_requirement_capability(out, budget.dataset, budget, capability)
                continue
            seen.add(budget.dataset)
            relation = _budget_relation(budget, required)
            state = _state_for_budget(budget, dataset_rows=dataset_rows, source_rows=source_rows)
            out.append({
                "dataset": budget.dataset,
                "label": budget.label,
                "role": budget.role,
                "cost_class": budget.cost_class,
                "cadence": budget.cadence,
                "critical_for": [cap for cap in budget.critical_for if cap in required],
                "important_for": [cap for cap in budget.important_for if cap in required],
                "relationship": relation,
                "state": state.value,
                "allows_required_capabilities": {
                    capability: state_allows(state, capability)
                    for capability in required
                    if capability in budget.critical_for or capability in budget.important_for
                },
                "target_freshness_seconds": budget.target_freshness_seconds,
                "provider_min_interval_seconds": budget.provider_min_interval_seconds,
                "primary_provider": budget.primary_provider,
                "fallback_providers": list(budget.fallback_providers),
                "decision_scope": budget.decision_scope,
                "failure_impact": budget.failure_impact,
            })
    return out


def _merge_requirement_capability(
    rows: list[dict[str, Any]],
    dataset: str,
    budget: SourceBudget,
    capability: str,
) -> None:
    row = next((entry for entry in rows if entry.get("dataset") == dataset), None)
    if row is None:
        return
    if capability in budget.critical_for and capability not in row["critical_for"]:
        row["critical_for"].append(capability)
        row["relationship"] = "critical"
    if capability in budget.important_for and capability not in row["important_for"]:
        row["important_for"].append(capability)
    row["allows_required_capabilities"][capability] = state_allows(
        FreshnessState(str(row.get("state") or "invalid")),
        capability,
    )


def _execution_constraints(
    item: Mapping[str, Any],
    *,
    readiness: Mapping[str, Any],
    capabilities: Mapping[str, Mapping[str, Any]],
    data_requirements: Iterable[Mapping[str, Any]],
    required_capabilities: Iterable[str],
    stale: bool,
) -> list[dict[str, Any]]:
    constraints: list[dict[str, Any]] = []
    trust = item.get("trust") or {}
    if stale or not bool(item.get("actionable", True)) or not bool(trust.get("trusted", True)):
        constraints.append({
            "code": "item_not_trusted",
            "type": "item_trust",
            "label": "动作可信度",
            "message": "这条动作未通过今日可信度检查，不允许真钱执行。",
        })
    if str(readiness.get("readiness_mode") or "") != "live_ready" or not bool(readiness.get("ready")):
        constraints.append({
            "code": "readiness_not_live_ready",
            "type": "readiness",
            "label": "系统就绪状态",
            "message": "系统未处于 live_ready，不允许真钱执行。",
        })

    block_reason = str(item.get("block_reason") or "").strip()
    if block_reason or str(item.get("risk_level") or "").strip() == "block":
        constraints.append({
            "code": "risk_hard_block",
            "type": "execution_risk",
            "label": "单票硬执行约束",
            "message": block_reason or "该标的命中停牌、ST 或涨跌停等硬执行约束，不允许按真钱动作执行。",
            "why_not": [
                {
                    "code": "risk_level_block",
                    "label": "risk_level=block",
                    "message": block_reason or "硬执行约束命中。",
                }
            ],
        })

    for capability in required_capabilities:
        report = capabilities.get(capability) or {}
        if bool(report.get("granted")):
            continue
        why_not = list(report.get("why_not") or [])
        constraints.append({
            "code": f"capability_{capability}_blocked",
            "type": "capability",
            "label": capability,
            "message": _first_message(why_not) or f"{capability} 能力未放行。",
            "why_not": why_not,
        })

    for requirement in data_requirements:
        state = str(requirement.get("state") or "")
        blocked_caps = [
            cap
            for cap, allowed in (requirement.get("allows_required_capabilities") or {}).items()
            if not allowed and cap in (requirement.get("critical_for") or [])
        ]
        if not blocked_caps:
            continue
        constraints.append({
            "code": f"dataset_{requirement.get('dataset')}_blocked",
            "type": "data_requirement",
            "label": str(requirement.get("label") or requirement.get("dataset") or ""),
            "message": f"{requirement.get('label') or requirement.get('dataset')} 当前为 {state}，阻塞 {', '.join(blocked_caps)}。",
            "dataset": requirement.get("dataset"),
            "state": state,
            "capabilities": blocked_caps,
        })
    return _dedupe_constraints(constraints)


def _formal_constraints(constraints: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    formal_types = {"readiness", "capability", "data_requirement", "item_trust", "execution_risk"}
    return [
        constraint
        for constraint in constraints
        if str(constraint.get("type") or "") in formal_types
    ]


def _review_obligation(
    *,
    action: str,
    stock: Mapping[str, Any] | None,
    constraints: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    if not stock:
        return {
            "required": False,
            "reason": "non_stock_action",
            "windows": [],
        }
    reason = "real_money_action" if action in _REAL_MONEY_ACTIONS else "decision_quality"
    if any(str(c.get("type") or "") == "data_requirement" for c in constraints):
        reason = "data_quality_check"
    return {
        "required": True,
        "reason": reason,
        "windows": ["T+1", "T+3", "T+5", "T+10"],
        "minimum_evidence": ["decision_contract", "readiness_snapshot", "source_budget"],
    }


def _evidence_refs(
    item: Mapping[str, Any],
    *,
    source_cards: Iterable[Mapping[str, Any]],
    artifacts: Mapping[str, Any],
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    if item.get("url"):
        refs.append({
            "kind": "ui_route",
            "label": str(item.get("title") or item.get("key") or "动作详情"),
            "url": str(item.get("url") or ""),
        })
    source_label = str(item.get("source") or "")
    for card in source_cards:
        if not isinstance(card, Mapping):
            continue
        label = str(card.get("label") or "")
        if source_label and source_label not in label and label not in source_label:
            continue
        refs.append({
            "kind": "source_freshness",
            "label": label or str(card.get("key") or ""),
            "key": str(card.get("key") or ""),
            "trade_date": card.get("trade_date"),
            "age_label": card.get("age_label"),
            "stale": bool(card.get("stale")),
        })
    for key, artifact in (artifacts or {}).items():
        if not isinstance(artifact, Mapping):
            continue
        path = artifact.get("path")
        url = artifact.get("url")
        if not path and not url:
            continue
        refs.append({
            "kind": "artifact",
            "key": str(key),
            "label": str(artifact.get("label") or key),
            "path": path,
            "url": url,
        })
    return refs[:8]


def _stock_from_action_key(action_key: str, item: Mapping[str, Any]) -> dict[str, Any] | None:
    match = _STOCK_ACTION_KEY_RE.match(action_key)
    if not match:
        return None
    code = match.group("code")
    title = str(item.get("title") or "").strip()
    name = title[: -len(code)].strip() if title.endswith(code) else title
    return {
        "code": code,
        "name": name,
        "market": _market_for_code(code),
    }


def _market_for_code(code: str) -> str:
    return "sh" if str(code).startswith("6") else "sz"


def _lane_from_action_key(action_key: str) -> str:
    match = _STOCK_ACTION_KEY_RE.match(action_key)
    return match.group("lane") if match else ""


def _contract_id(trade_date: str, action_key: str, action: str) -> str:
    digest = hashlib.sha256(
        f"{CONTRACT_SCHEMA_VERSION}|{trade_date}|{action_key}|{action}".encode("utf-8")
    ).hexdigest()[:12]
    return f"dc:{trade_date}:{digest}"


def _ledger_capture_key(trade_date: str, action_key: str) -> str:
    cleaned = str(action_key or "").replace(" ", "")
    return f"today_action_queue:{trade_date}:{cleaned}"


def _dataset_rows(readiness: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    for row in readiness.get("dataset_freshness") or []:
        if not isinstance(row, Mapping):
            continue
        key = str(row.get("dataset") or row.get("key") or "").strip()
        if key:
            out[key] = row
    return out


def _source_rows(readiness: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    for row in readiness.get("source_freshness") or []:
        if not isinstance(row, Mapping):
            continue
        key = str(row.get("key") or "").strip()
        if key:
            out[key] = row
            dataset = _SOURCE_KEY_TO_PIPELINE_DATASET.get(key)
            if dataset:
                out[dataset] = row
    return out


def _state_for_budget(
    budget: SourceBudget,
    *,
    dataset_rows: Mapping[str, Mapping[str, Any]],
    source_rows: Mapping[str, Mapping[str, Any]],
) -> FreshnessState:
    row = dataset_rows.get(budget.dataset)
    if row is not None:
        return classify_source_row(row)
    source_key = _PIPELINE_DATASET_TO_SOURCE_KEY.get(budget.dataset)
    if source_key and source_key in source_rows:
        return classify_source_row(source_rows[source_key])
    row = source_rows.get(budget.dataset)
    if row is not None:
        return classify_source_row(row)
    return FreshnessState.FRESH


def _budget_relation(budget: SourceBudget, capabilities: Iterable[str]) -> str:
    required = set(capabilities)
    if required.intersection(budget.critical_for):
        return "critical"
    return "important"


def _decision_scope(data_requirements: Iterable[Mapping[str, Any]]) -> str:
    scopes = {
        str(req.get("decision_scope") or "").strip()
        for req in data_requirements
        if str(req.get("decision_scope") or "").strip()
    }
    if "live_small" in scopes:
        return "live_small"
    if "formal" in scopes:
        return "formal"
    if "research" in scopes:
        return "research"
    return "unknown"


def _first_message(items: Iterable[Mapping[str, Any]]) -> str:
    for item in items:
        text = str(item.get("message") or item.get("label") or "").strip()
        if text:
            return text
    return ""


def _dedupe_constraints(constraints: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for constraint in constraints:
        code = str(constraint.get("code") or "")
        if not code or code in seen:
            continue
        seen.add(code)
        out.append(dict(constraint))
    return out


def _contract_summary(contracts: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    items = list(contracts)
    total = len(items)
    real_money_allowed = sum(1 for item in items if item.get("allowed_for_real_money"))
    formal_allowed = sum(1 for item in items if item.get("allowed_for_formal_action"))
    blocked = sum(1 for item in items if item.get("execution_constraints"))
    return {
        "total": total,
        "real_money_allowed": real_money_allowed,
        "formal_allowed": formal_allowed,
        "blocked": blocked,
        "review_required": sum(1 for item in items if (item.get("review_obligation") or {}).get("required")),
    }
