"""Static business profile registry for Prism data sources.

This module complements ``packages/prism_data/manifest.py`` (which is the
*technical* registry: providers, TTL, fallback chain) with the *business*
view the operator and the capability matrix need:

* What role does this dataset play (market data vs pipeline artifact vs
  account)?
* What is its compute cost class?
* How often does the business expect to need fresh data (cadence)?
* Which investment capabilities (observe / review / approve / trade / notify
  / ledger_capture) does it back, and how critically?
* What happens if it is missing?

The registry is intentionally static. It is the single source of truth that
``capability_matrix`` consults to decide which datasets back each capability
and whether their absence is a BLOCK or a DEGRADATION.

Two distinct freshness fields capture two distinct concerns:

* ``provider_min_interval_seconds`` — the technical floor on how often we
  may poll the upstream provider (rate-limit / politeness). We MUST NOT
  refresh faster than this.
* ``target_freshness_seconds`` — operator's tolerance for staleness. We
  consider data older than this as "stale" for capability purposes. This
  is what the readiness gate compares against.

Invariants enforced by tests:
    provider_min_interval_seconds <= target_freshness_seconds <= ttl_intraday

Provider authority fields (``primary_provider``, ``fallback_providers``,
``decision_scope``) are NOT duplicated here — they are derived live from
``prism_data.manifest.DATASET_REGISTRY`` so the two registries cannot drift.
``account.book`` is the one non-registry dataset and falls back to the
``_NON_REGISTRY_AUTHORITY`` table below.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from prism_data.manifest import DATASET_REGISTRY


__all__ = [
    "SourceBudget",
    "SOURCE_BUDGETS",
    "source_budget",
    "budgets_for_capability",
    "budgets_critical_for_capability",
    "budgets_important_for_capability",
    "budgets_for_role",
    "build_source_budget_payload",
]


_NON_REGISTRY_AUTHORITY: dict[str, dict[str, Any]] = {
    "account.book": {
        "primary_provider": "account_book",
        "fallback_providers": (),
        "decision_scope": "live_small",
    },
}


@dataclass(frozen=True)
class SourceBudget:
    """Business profile for one dataset.

    Provider authority fields (``primary_provider``, ``fallback_providers``,
    ``decision_scope``) are intentionally derived properties — they read
    from ``DATASET_REGISTRY`` so the source-of-truth lives in one place.

    ``critical_for`` lists the capabilities that MUST have this dataset
    fresh; if it is stale/missing, the capability is BLOCKED.
    ``important_for`` lists capabilities that benefit from this dataset
    but can degrade gracefully without it (capability still granted but
    flagged degraded).
    """

    dataset: str
    label: str
    role: str                                # market_data | fundamentals | news | pipeline_artifact | account
    cost_class: str                          # cheap | moderate | heavy
    cadence: str                             # intraday_high | intraday_medium | daily | event
    batchable: bool
    provider_min_interval_seconds: int       # technical rate-limit floor
    target_freshness_seconds: int            # operator's max-age tolerance
    critical_for: tuple[str, ...]
    important_for: tuple[str, ...]
    failure_impact: str

    @property
    def primary_provider(self) -> str:
        definition = DATASET_REGISTRY.get(self.dataset)
        if definition is not None:
            return definition.primary_provider
        return _NON_REGISTRY_AUTHORITY[self.dataset]["primary_provider"]

    @property
    def fallback_providers(self) -> tuple[str, ...]:
        definition = DATASET_REGISTRY.get(self.dataset)
        if definition is not None:
            return tuple(definition.fallback_providers)
        return tuple(_NON_REGISTRY_AUTHORITY[self.dataset]["fallback_providers"])

    @property
    def decision_scope(self) -> str:
        definition = DATASET_REGISTRY.get(self.dataset)
        if definition is not None:
            return definition.decision_scope
        return _NON_REGISTRY_AUTHORITY[self.dataset]["decision_scope"]

    @property
    def supports_capabilities(self) -> tuple[str, ...]:
        """All capabilities that touch this dataset (critical first)."""
        seen: set[str] = set()
        out: list[str] = []
        for cap in self.critical_for + self.important_for:
            if cap not in seen:
                seen.add(cap)
                out.append(cap)
        return tuple(out)

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "label": self.label,
            "role": self.role,
            "cost_class": self.cost_class,
            "cadence": self.cadence,
            "batchable": self.batchable,
            "provider_min_interval_seconds": self.provider_min_interval_seconds,
            "target_freshness_seconds": self.target_freshness_seconds,
            "primary_provider": self.primary_provider,
            "fallback_providers": list(self.fallback_providers),
            "decision_scope": self.decision_scope,
            "critical_for": list(self.critical_for),
            "important_for": list(self.important_for),
            "supports_capabilities": list(self.supports_capabilities),
            "failure_impact": self.failure_impact,
        }


SOURCE_BUDGETS: dict[str, SourceBudget] = {
    "quotes.batch": SourceBudget(
        dataset="quotes.batch",
        label="批量行情",
        role="market_data",
        cost_class="cheap",
        cadence="intraday_high",
        batchable=True,
        provider_min_interval_seconds=30,
        target_freshness_seconds=60,
        critical_for=("approve", "trade"),
        important_for=("observe", "review"),
        failure_impact="行情读不到,影响所有交易决策与命令台",
    ),
    "quotes.snapshot": SourceBudget(
        dataset="quotes.snapshot",
        label="单股行情",
        role="market_data",
        cost_class="cheap",
        cadence="intraday_high",
        batchable=False,
        provider_min_interval_seconds=30,
        target_freshness_seconds=60,
        critical_for=(),
        important_for=("observe", "trade"),
        failure_impact="个股行情缺失,影响盯盘但不阻断批量决策",
    ),
    "quotes.pool": SourceBudget(
        dataset="quotes.pool",
        label="全市场快照",
        role="market_data",
        cost_class="cheap",
        cadence="intraday_medium",
        batchable=True,
        provider_min_interval_seconds=60,
        target_freshness_seconds=300,
        critical_for=(),
        important_for=("observe",),
        failure_impact="全市场观察池缺失,只影响观察视图",
    ),
    "capital_flow.batch": SourceBudget(
        dataset="capital_flow.batch",
        label="批量资金流",
        role="market_data",
        cost_class="moderate",
        cadence="intraday_medium",
        batchable=True,
        provider_min_interval_seconds=60,
        target_freshness_seconds=180,
        critical_for=(),
        important_for=("observe", "review"),
        failure_impact="资金流缺失,复核可降级但置信度下降",
    ),
    "capital_flow.daily": SourceBudget(
        dataset="capital_flow.daily",
        label="个股资金流历史",
        role="market_data",
        cost_class="moderate",
        cadence="intraday_medium",
        batchable=False,
        provider_min_interval_seconds=60,
        target_freshness_seconds=300,
        critical_for=(),
        important_for=("review",),
        failure_impact="单股资金流断档,复核降级",
    ),
    "bars.daily": SourceBudget(
        dataset="bars.daily",
        label="日K线",
        role="market_data",
        cost_class="moderate",
        cadence="daily",
        batchable=False,
        provider_min_interval_seconds=600,
        target_freshness_seconds=1800,
        critical_for=(),
        important_for=("review", "approve"),
        failure_impact="K线缺失,技术信号失效",
    ),
    "fundamentals.batch": SourceBudget(
        dataset="fundamentals.batch",
        label="批量基本面",
        role="fundamentals",
        cost_class="cheap",
        cadence="daily",
        batchable=True,
        provider_min_interval_seconds=3600,
        target_freshness_seconds=21600,
        critical_for=(),
        important_for=("review",),
        failure_impact="估值/财务无法显示,复核中性化",
    ),
    "fundamentals.snapshot": SourceBudget(
        dataset="fundamentals.snapshot",
        label="单股基本面",
        role="fundamentals",
        cost_class="cheap",
        cadence="daily",
        batchable=False,
        provider_min_interval_seconds=3600,
        target_freshness_seconds=21600,
        critical_for=(),
        important_for=("review",),
        failure_impact="个股估值/财务无法显示",
    ),
    "news.latest": SourceBudget(
        dataset="news.latest",
        label="新闻",
        role="news",
        cost_class="moderate",
        cadence="event",
        batchable=False,
        provider_min_interval_seconds=600,
        target_freshness_seconds=3600,
        critical_for=(),
        important_for=("review",),
        failure_impact="事件上下文缺失,复核中性化",
    ),
    "announcements.latest": SourceBudget(
        dataset="announcements.latest",
        label="公告",
        role="news",
        cost_class="moderate",
        cadence="event",
        batchable=False,
        provider_min_interval_seconds=600,
        target_freshness_seconds=3600,
        critical_for=(),
        important_for=("review",),
        failure_impact="公告上下文缺失,复核中性化",
    ),
    "sector.snapshot": SourceBudget(
        dataset="sector.snapshot",
        label="板块快照",
        role="market_data",
        cost_class="cheap",
        cadence="intraday_medium",
        batchable=False,
        provider_min_interval_seconds=300,
        target_freshness_seconds=1800,
        critical_for=(),
        important_for=("review",),
        failure_impact="板块对比缺失,相对强度判断降级",
    ),
    "index.constituents": SourceBudget(
        dataset="index.constituents",
        label="指数成分",
        role="market_data",
        cost_class="cheap",
        cadence="daily",
        batchable=False,
        provider_min_interval_seconds=21600,
        target_freshness_seconds=86400,
        critical_for=(),
        important_for=("review",),
        failure_impact="指数对照缺失,基本面板降级",
    ),
    "watchlist.snapshot": SourceBudget(
        dataset="watchlist.snapshot",
        label="自选股数据",
        role="pipeline_artifact",
        cost_class="heavy",
        cadence="daily",
        batchable=False,
        provider_min_interval_seconds=300,
        target_freshness_seconds=900,
        critical_for=("review", "approve", "trade"),
        important_for=("observe",),
        failure_impact="自选股报告缺失,无法做命令台决策",
    ),
    "screening.batch": SourceBudget(
        dataset="screening.batch",
        label="进攻型候选数据",
        role="pipeline_artifact",
        cost_class="heavy",
        cadence="daily",
        batchable=False,
        provider_min_interval_seconds=300,
        target_freshness_seconds=900,
        critical_for=("approve",),
        important_for=("review", "trade"),
        failure_impact="进攻型候选缺失,无法复核与放行",
    ),
    "screening.confirmation": SourceBudget(
        dataset="screening.confirmation",
        label="午盘承接确认",
        role="pipeline_artifact",
        cost_class="heavy",
        cadence="daily",
        batchable=False,
        provider_min_interval_seconds=300,
        target_freshness_seconds=900,
        critical_for=("approve", "trade"),
        important_for=("review",),
        failure_impact="午盘承接确认缺失,下午进攻动作受阻",
    ),
    "decision_brief.snapshot": SourceBudget(
        dataset="decision_brief.snapshot",
        label="投资总控简报",
        role="pipeline_artifact",
        cost_class="heavy",
        cadence="daily",
        batchable=False,
        provider_min_interval_seconds=300,
        target_freshness_seconds=900,
        critical_for=("review",),
        important_for=("approve", "observe"),
        failure_impact="命令台简报缺失,无法形成统一动作清单",
    ),
    "account.book": SourceBudget(
        dataset="account.book",
        label="账户与对账",
        role="account",
        cost_class="cheap",
        cadence="event",
        batchable=False,
        provider_min_interval_seconds=30,
        target_freshness_seconds=60,
        critical_for=("trade", "ledger_capture"),
        important_for=("approve",),
        failure_impact="账本不可读,真钱执行与对账阻断",
    ),
}


def source_budget(dataset: str) -> SourceBudget | None:
    return SOURCE_BUDGETS.get(str(dataset or "").strip())


def budgets_for_capability(capability: str) -> list[SourceBudget]:
    target = str(capability or "").strip()
    return [
        budget for budget in SOURCE_BUDGETS.values()
        if target in budget.critical_for or target in budget.important_for
    ]


def budgets_critical_for_capability(capability: str) -> list[SourceBudget]:
    target = str(capability or "").strip()
    return [b for b in SOURCE_BUDGETS.values() if target in b.critical_for]


def budgets_important_for_capability(capability: str) -> list[SourceBudget]:
    target = str(capability or "").strip()
    return [b for b in SOURCE_BUDGETS.values() if target in b.important_for]


def budgets_for_role(role: str) -> list[SourceBudget]:
    target = str(role or "").strip()
    return [budget for budget in SOURCE_BUDGETS.values() if budget.role == target]


def build_source_budget_payload() -> dict[str, Any]:
    return {
        "datasets": [budget.as_dict() for budget in SOURCE_BUDGETS.values()],
    }
