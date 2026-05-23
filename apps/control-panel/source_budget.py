"""Static business profile registry for Prism data sources.

This module complements ``packages/prism_data/manifest.py`` (which is the
*technical* registry: providers, TTL, fallback chain) with the *business*
view the operator and the capability matrix need:

* What role does this dataset play (market data vs pipeline artifact vs
  account)?
* What is its compute cost class?
* How often does the business expect to need fresh data (cadence)?
* Which investment capabilities (observe / review / approve / trade / notify
  / ledger_capture) does it back?
* What happens if it is missing?

The registry is intentionally static. Phase 1 does NOT plug it into
``evaluate_auto_refresh``; it only supports queries by ``/api/source-budget``
and the capability_matrix translation layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


__all__ = [
    "SourceBudget",
    "SOURCE_BUDGETS",
    "source_budget",
    "budgets_for_capability",
    "budgets_for_role",
    "build_source_budget_payload",
]


@dataclass(frozen=True)
class SourceBudget:
    """Business profile for one dataset.

    ``min_refresh_interval_seconds`` is the *business* lower bound on how
    frequently we want to re-fetch this dataset.  It is derived from the
    upstream TTL but represents operator intent, not a provider rate limit.
    Tests enforce ``min_refresh_interval_seconds <= ttl_intraday``.
    """

    dataset: str
    label: str
    role: str                                # market_data | fundamentals | news | pipeline_artifact | account
    cost_class: str                          # cheap | moderate | heavy
    cadence: str                             # intraday_high | intraday_medium | daily | event
    batchable: bool
    min_refresh_interval_seconds: int
    primary_provider: str
    fallback_providers: tuple[str, ...]
    decision_scope: str                      # live_small | display_only
    supports_capabilities: tuple[str, ...]
    failure_impact: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "label": self.label,
            "role": self.role,
            "cost_class": self.cost_class,
            "cadence": self.cadence,
            "batchable": self.batchable,
            "min_refresh_interval_seconds": self.min_refresh_interval_seconds,
            "primary_provider": self.primary_provider,
            "fallback_providers": list(self.fallback_providers),
            "decision_scope": self.decision_scope,
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
        min_refresh_interval_seconds=60,
        primary_provider="eastmoney",
        fallback_providers=("sina",),
        decision_scope="live_small",
        supports_capabilities=("observe", "review", "approve", "trade"),
        failure_impact="行情读不到,影响所有交易决策与命令台",
    ),
    "quotes.snapshot": SourceBudget(
        dataset="quotes.snapshot",
        label="单股行情",
        role="market_data",
        cost_class="cheap",
        cadence="intraday_high",
        batchable=False,
        min_refresh_interval_seconds=60,
        primary_provider="sina",
        fallback_providers=("eastmoney",),
        decision_scope="live_small",
        supports_capabilities=("observe", "trade"),
        failure_impact="个股行情读不到,影响下单与盯盘",
    ),
    "quotes.pool": SourceBudget(
        dataset="quotes.pool",
        label="全市场快照",
        role="market_data",
        cost_class="cheap",
        cadence="intraday_medium",
        batchable=True,
        min_refresh_interval_seconds=300,
        primary_provider="sina",
        fallback_providers=(),
        decision_scope="display_only",
        supports_capabilities=("observe",),
        failure_impact="全市场观察池缺失,只影响观察视图",
    ),
    "capital_flow.batch": SourceBudget(
        dataset="capital_flow.batch",
        label="批量资金流",
        role="market_data",
        cost_class="moderate",
        cadence="intraday_medium",
        batchable=True,
        min_refresh_interval_seconds=180,
        primary_provider="eastmoney",
        fallback_providers=(),
        decision_scope="live_small",
        supports_capabilities=("observe", "review"),
        failure_impact="资金流缺失,复核可降级但置信度下降",
    ),
    "capital_flow.daily": SourceBudget(
        dataset="capital_flow.daily",
        label="个股资金流历史",
        role="market_data",
        cost_class="moderate",
        cadence="intraday_medium",
        batchable=False,
        min_refresh_interval_seconds=300,
        primary_provider="eastmoney",
        fallback_providers=("ths",),
        decision_scope="live_small",
        supports_capabilities=("review",),
        failure_impact="单股资金流断档,复核降级",
    ),
    "bars.daily": SourceBudget(
        dataset="bars.daily",
        label="日K线",
        role="market_data",
        cost_class="moderate",
        cadence="daily",
        batchable=False,
        min_refresh_interval_seconds=1800,
        primary_provider="sina",
        fallback_providers=("akshare",),
        decision_scope="live_small",
        supports_capabilities=("review", "approve"),
        failure_impact="K线缺失,技术信号失效",
    ),
    "fundamentals.batch": SourceBudget(
        dataset="fundamentals.batch",
        label="批量基本面",
        role="fundamentals",
        cost_class="cheap",
        cadence="daily",
        batchable=True,
        min_refresh_interval_seconds=21600,
        primary_provider="eastmoney",
        fallback_providers=(),
        decision_scope="display_only",
        supports_capabilities=("review",),
        failure_impact="估值/财务无法显示,复核中性化",
    ),
    "fundamentals.snapshot": SourceBudget(
        dataset="fundamentals.snapshot",
        label="单股基本面",
        role="fundamentals",
        cost_class="cheap",
        cadence="daily",
        batchable=False,
        min_refresh_interval_seconds=21600,
        primary_provider="eastmoney",
        fallback_providers=("ths",),
        decision_scope="display_only",
        supports_capabilities=("review",),
        failure_impact="个股估值/财务无法显示",
    ),
    "news.latest": SourceBudget(
        dataset="news.latest",
        label="新闻",
        role="news",
        cost_class="moderate",
        cadence="event",
        batchable=False,
        min_refresh_interval_seconds=3600,
        primary_provider="eastmoney",
        fallback_providers=(),
        decision_scope="display_only",
        supports_capabilities=("review",),
        failure_impact="事件上下文缺失,复核中性化",
    ),
    "announcements.latest": SourceBudget(
        dataset="announcements.latest",
        label="公告",
        role="news",
        cost_class="moderate",
        cadence="event",
        batchable=False,
        min_refresh_interval_seconds=3600,
        primary_provider="eastmoney",
        fallback_providers=(),
        decision_scope="display_only",
        supports_capabilities=("review",),
        failure_impact="公告上下文缺失,复核中性化",
    ),
    "sector.snapshot": SourceBudget(
        dataset="sector.snapshot",
        label="板块快照",
        role="market_data",
        cost_class="cheap",
        cadence="intraday_medium",
        batchable=False,
        min_refresh_interval_seconds=1800,
        primary_provider="eastmoney",
        fallback_providers=(),
        decision_scope="display_only",
        supports_capabilities=("review",),
        failure_impact="板块对比缺失,相对强度判断降级",
    ),
    "index.constituents": SourceBudget(
        dataset="index.constituents",
        label="指数成分",
        role="market_data",
        cost_class="cheap",
        cadence="daily",
        batchable=False,
        min_refresh_interval_seconds=86400,
        primary_provider="akshare",
        fallback_providers=(),
        decision_scope="display_only",
        supports_capabilities=("review",),
        failure_impact="指数对照缺失,基本面板降级",
    ),
    "watchlist.snapshot": SourceBudget(
        dataset="watchlist.snapshot",
        label="自选股分析",
        role="pipeline_artifact",
        cost_class="heavy",
        cadence="daily",
        batchable=False,
        min_refresh_interval_seconds=900,
        primary_provider="pipeline",
        fallback_providers=(),
        decision_scope="live_small",
        supports_capabilities=("observe", "review", "approve", "trade"),
        failure_impact="自选股报告缺失,无法做命令台决策",
    ),
    "screening.batch": SourceBudget(
        dataset="screening.batch",
        label="选股观察池",
        role="pipeline_artifact",
        cost_class="heavy",
        cadence="daily",
        batchable=False,
        min_refresh_interval_seconds=900,
        primary_provider="pipeline",
        fallback_providers=(),
        decision_scope="live_small",
        supports_capabilities=("review", "approve"),
        failure_impact="进攻型候选缺失,无法复核与放行",
    ),
    "screening.confirmation": SourceBudget(
        dataset="screening.confirmation",
        label="午盘确认",
        role="pipeline_artifact",
        cost_class="heavy",
        cadence="daily",
        batchable=False,
        min_refresh_interval_seconds=900,
        primary_provider="pipeline",
        fallback_providers=(),
        decision_scope="live_small",
        supports_capabilities=("approve", "trade"),
        failure_impact="午盘承接确认缺失,下午进攻动作受阻",
    ),
    "decision_brief.snapshot": SourceBudget(
        dataset="decision_brief.snapshot",
        label="投资总控简报",
        role="pipeline_artifact",
        cost_class="heavy",
        cadence="daily",
        batchable=False,
        min_refresh_interval_seconds=900,
        primary_provider="pipeline",
        fallback_providers=(),
        decision_scope="live_small",
        supports_capabilities=("review", "approve"),
        failure_impact="命令台简报缺失,无法形成统一动作清单",
    ),
    "account.book": SourceBudget(
        dataset="account.book",
        label="账户与对账",
        role="account",
        cost_class="cheap",
        cadence="event",
        batchable=False,
        min_refresh_interval_seconds=60,
        primary_provider="account_book",
        fallback_providers=(),
        decision_scope="live_small",
        supports_capabilities=("trade", "ledger_capture"),
        failure_impact="账本不可读,真钱执行与对账阻断",
    ),
}


def source_budget(dataset: str) -> SourceBudget | None:
    return SOURCE_BUDGETS.get(str(dataset or "").strip())


def budgets_for_capability(capability: str) -> list[SourceBudget]:
    target = str(capability or "").strip()
    return [budget for budget in SOURCE_BUDGETS.values() if target in budget.supports_capabilities]


def budgets_for_role(role: str) -> list[SourceBudget]:
    target = str(role or "").strip()
    return [budget for budget in SOURCE_BUDGETS.values() if budget.role == target]


def build_source_budget_payload() -> dict[str, Any]:
    return {
        "datasets": [budget.as_dict() for budget in SOURCE_BUDGETS.values()],
    }
