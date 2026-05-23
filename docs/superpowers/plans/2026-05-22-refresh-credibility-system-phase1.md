# Prism 刷新可信度系统 — Phase 1 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Prism readiness 之上叠加一层「投资动作能力」翻译层，建立 SourceBudget（数据源治理画像）+ FreshnessState（六态枚举）+ CapabilityMatrix（observe/review/approve/trade/notify/ledger_capture）三个模块，并通过两个只读 API 暴露。**不改任何现有判断逻辑、不动任何前端代码**。

**Architecture:** 三个新模块全部位于 `apps/control-panel/`，pytest pythonpath 已经覆盖该目录。`source_budget` 是静态注册表，对齐 `packages/prism_data/manifest.py` 的 `DATASET_REGISTRY` 但补"业务画像"字段。`freshness_state` 是纯函数：把 readiness 的 source row 分类成 6 个 enum 之一，并提供 capability 允许矩阵。`capability_matrix` 消费 readiness payload + source_budget + freshness_state，输出 6 个能力的 `CapabilityReport`。最后在 `readiness.compute_readiness` 末尾追加两个新字段，并新增 `/api/source-budget` + `/api/capabilities`，同时把 `/api/readiness/live` 的字段 allowlist 扩到包含新字段。

**Tech Stack:** Python 3.14 / FastAPI / pytest + fastapi.testclient.TestClient / unittest 风格（沿用项目现有约定）

**File Structure:**

| File | Responsibility |
|---|---|
| `apps/control-panel/source_budget.py` (新) | 静态 `SourceBudget` dataclass + `SOURCE_BUDGETS` 注册表 + 查询 helper |
| `apps/control-panel/freshness_state.py` (新) | `FreshnessState` enum + `classify_source_row` + `state_allows` 矩阵 |
| `apps/control-panel/capability_matrix.py` (新) | `Capability` enum + `CapabilityReport` dataclass + `evaluate_capabilities` |
| `apps/control-panel/readiness.py` (改) | `compute_readiness` 末尾追加 `source_states` + `capabilities` 字段 |
| `apps/control-panel/app.py` (改) | 新增 `/api/source-budget` + `/api/capabilities`；`/api/readiness/live` 加入新字段 |
| `apps/control-panel/tests/test_source_budget.py` (新) | source_budget 单测 |
| `apps/control-panel/tests/test_freshness_state.py` (新) | freshness_state 单测 |
| `apps/control-panel/tests/test_capability_matrix.py` (新) | capability_matrix 单测 |
| `apps/control-panel/tests/test_capabilities_endpoint.py` (新) | API 端点集成测试 |

**Conventions sourced from existing code:**

- 测试基座（来自 `tests/test_app_smoke.py`）：
  ```python
  INVEST_FLOW_ROOT = Path(__file__).resolve().parents[2]
  if str(INVEST_FLOW_ROOT) not in sys.path:
      sys.path.insert(0, str(INVEST_FLOW_ROOT))
  ```
- 直接 `from source_budget import ...`（pytest pythonpath 已包含 `apps/control-panel`，见 `pyproject.toml`）
- API 测试用 `from control_panel.app import app` + `TestClient(app)`
- 模块风格：`from __future__ import annotations`、`@dataclass(frozen=True)`、`__all__` 显式导出

**Test command:** 
```bash
cd /Users/yangbishang/Projects/prism && python3.14 -m pytest apps/control-panel/tests/ -v
```

---

## Task 1: SourceBudget 静态注册表

**Files:**
- Create: `apps/control-panel/source_budget.py`
- Test: `apps/control-panel/tests/test_source_budget.py`

### - [ ] Step 1.1: 写测试 — 注册表对齐与字段完整性

写到 `apps/control-panel/tests/test_source_budget.py`：

```python
"""Tests for source_budget — the business profile registry layered on top of
``packages/prism_data/manifest.py``.

These tests guard the contract that SOURCE_BUDGETS stays in sync with the
upstream DATASET_REGISTRY and that every entry carries the business fields
that capability_matrix relies on.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


INVEST_FLOW_ROOT = Path(__file__).resolve().parents[2]
if str(INVEST_FLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(INVEST_FLOW_ROOT))

# Make ``packages/`` reachable so prism_data imports work in tests.
PACKAGES_ROOT = INVEST_FLOW_ROOT / "packages"
if str(PACKAGES_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGES_ROOT))

from source_budget import (  # noqa: E402
    SourceBudget,
    SOURCE_BUDGETS,
    budgets_for_capability,
    budgets_for_role,
    build_source_budget_payload,
    source_budget,
)
from prism_data.manifest import DATASET_REGISTRY  # noqa: E402


KNOWN_CAPABILITIES = {"observe", "review", "approve", "trade", "notify", "ledger_capture"}
KNOWN_ROLES = {"market_data", "fundamentals", "news", "pipeline_artifact", "account"}
KNOWN_COSTS = {"cheap", "moderate", "heavy"}
KNOWN_CADENCES = {"intraday_high", "intraday_medium", "daily", "event"}


class SourceBudgetRegistryTests(unittest.TestCase):
    def test_registry_subset_of_manifest_datasets(self) -> None:
        # Every budget MUST reference a real dataset (except special "account.book"
        # which is internal-only and documented as an exception).
        manifest_keys = set(DATASET_REGISTRY.keys()) | {"account.book"}
        budget_keys = set(SOURCE_BUDGETS.keys())
        unknown = budget_keys - manifest_keys
        self.assertFalse(unknown, f"SOURCE_BUDGETS references unknown datasets: {unknown}")

    def test_every_budget_has_required_fields(self) -> None:
        for key, budget in SOURCE_BUDGETS.items():
            with self.subTest(key=key):
                self.assertIsInstance(budget, SourceBudget)
                self.assertEqual(budget.dataset, key)
                self.assertTrue(budget.label, f"{key} missing label")
                self.assertIn(budget.role, KNOWN_ROLES, f"{key} bad role: {budget.role}")
                self.assertIn(budget.cost_class, KNOWN_COSTS, f"{key} bad cost_class")
                self.assertIn(budget.cadence, KNOWN_CADENCES, f"{key} bad cadence")
                self.assertGreater(budget.min_refresh_interval_seconds, 0)
                self.assertTrue(budget.primary_provider)
                self.assertIn(budget.decision_scope, {"live_small", "display_only"})
                self.assertTrue(budget.supports_capabilities, f"{key} missing capabilities")
                for cap in budget.supports_capabilities:
                    self.assertIn(cap, KNOWN_CAPABILITIES, f"{key} bad capability: {cap}")
                self.assertTrue(budget.failure_impact, f"{key} missing failure_impact")

    def test_min_refresh_interval_does_not_exceed_intraday_ttl(self) -> None:
        # min_refresh_interval is a *business* lower bound; it must not request
        # data more frequently than the TTL declares the data can change.
        for key, budget in SOURCE_BUDGETS.items():
            if key not in DATASET_REGISTRY:
                continue
            with self.subTest(key=key):
                ttl = DATASET_REGISTRY[key].ttl_intraday
                self.assertLessEqual(
                    budget.min_refresh_interval_seconds,
                    ttl,
                    f"{key}: min_refresh_interval ({budget.min_refresh_interval_seconds}) "
                    f"exceeds ttl_intraday ({ttl}); business should not poll faster than TTL allows",
                )


class SourceBudgetQueryTests(unittest.TestCase):
    def test_source_budget_lookup(self) -> None:
        budget = source_budget("quotes.batch")
        self.assertIsNotNone(budget)
        self.assertEqual(budget.dataset, "quotes.batch")

    def test_source_budget_unknown_returns_none(self) -> None:
        self.assertIsNone(source_budget("does.not.exist"))

    def test_budgets_for_capability_trade_includes_quotes(self) -> None:
        keys = {item.dataset for item in budgets_for_capability("trade")}
        self.assertIn("quotes.batch", keys, "trade capability must require quotes.batch")
        self.assertIn("watchlist.snapshot", keys, "trade capability must require watchlist")

    def test_budgets_for_capability_observe_is_permissive(self) -> None:
        observe = budgets_for_capability("observe")
        self.assertGreaterEqual(len(observe), 4, "observe should cover at least market_data + watchlist")

    def test_budgets_for_role_market_data(self) -> None:
        keys = {item.dataset for item in budgets_for_role("market_data")}
        self.assertIn("quotes.batch", keys)
        self.assertIn("capital_flow.batch", keys)

    def test_build_payload_shape(self) -> None:
        payload = build_source_budget_payload()
        self.assertIn("datasets", payload)
        self.assertIsInstance(payload["datasets"], list)
        self.assertGreaterEqual(len(payload["datasets"]), 15)
        sample = payload["datasets"][0]
        for key in (
            "dataset",
            "label",
            "role",
            "cost_class",
            "cadence",
            "batchable",
            "min_refresh_interval_seconds",
            "primary_provider",
            "fallback_providers",
            "decision_scope",
            "supports_capabilities",
            "failure_impact",
        ):
            self.assertIn(key, sample, f"payload row missing {key}")


if __name__ == "__main__":
    unittest.main()
```

### - [ ] Step 1.2: 跑测试，确认 fail

```bash
cd /Users/yangbishang/Projects/prism && python3.14 -m pytest apps/control-panel/tests/test_source_budget.py -v
```

**Expected:** `ModuleNotFoundError: No module named 'source_budget'`（因为还没创建模块）

### - [ ] Step 1.3: 创建 source_budget.py 模块

写到 `apps/control-panel/source_budget.py`：

```python
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
```

### - [ ] Step 1.4: 跑测试，确认 pass

```bash
cd /Users/yangbishang/Projects/prism && python3.14 -m pytest apps/control-panel/tests/test_source_budget.py -v
```

**Expected:** 全部测试通过（应该有 8 个测试）。

### - [ ] Step 1.5: Commit

```bash
git add apps/control-panel/source_budget.py apps/control-panel/tests/test_source_budget.py
git commit -m "$(cat <<'EOF'
feat(readiness): add SourceBudget static registry for business profiles

Layer 'business profile' fields (role, cost_class, cadence, cap support,
failure impact) on top of prism_data DATASET_REGISTRY. Phase 1 only: query
API + capability_matrix consumer; not wired into evaluate_auto_refresh.
EOF
)"
```

---

## Task 2: FreshnessState 枚举 + 分类器 + 允许矩阵

**Files:**
- Create: `apps/control-panel/freshness_state.py`
- Test: `apps/control-panel/tests/test_freshness_state.py`

### - [ ] Step 2.1: 写测试

写到 `apps/control-panel/tests/test_freshness_state.py`：

```python
"""Tests for freshness_state — six-state classifier for readiness source rows.

Maps the readiness module's scattered ``stale`` / ``degraded`` / ``available``
/ ``stale_reasons`` flags into one explicit enum and a capability allow
matrix.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


INVEST_FLOW_ROOT = Path(__file__).resolve().parents[2]
if str(INVEST_FLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(INVEST_FLOW_ROOT))

from freshness_state import (  # noqa: E402
    FreshnessState,
    classify_source_row,
    state_allows,
)


class ClassifySourceRowTests(unittest.TestCase):
    @staticmethod
    def _row(
        *,
        available: bool = True,
        stale: bool = False,
        degraded: bool = False,
        stale_reasons: list[str] | None = None,
        degradation_reasons: list[str] | None = None,
    ) -> dict[str, object]:
        return {
            "available": available,
            "stale": stale,
            "degraded": degraded,
            "stale_reasons": stale_reasons or [],
            "degradation_reasons": degradation_reasons or [],
        }

    def test_fresh(self) -> None:
        self.assertEqual(classify_source_row(self._row()), FreshnessState.FRESH)

    def test_missing_is_invalid(self) -> None:
        self.assertEqual(
            classify_source_row(self._row(available=False, stale=True, stale_reasons=["manifest_missing"])),
            FreshnessState.INVALID,
        )

    def test_trade_date_mismatch_is_invalid(self) -> None:
        row = self._row(stale=True, stale_reasons=["trade_date_mismatch"])
        self.assertEqual(classify_source_row(row), FreshnessState.INVALID)

    def test_trade_date_unknown_is_invalid(self) -> None:
        row = self._row(stale=True, stale_reasons=["trade_date_unknown"])
        self.assertEqual(classify_source_row(row), FreshnessState.INVALID)

    def test_live_small_not_allowed_is_blocked(self) -> None:
        row = self._row(stale=True, stale_reasons=["live_small_not_allowed"])
        self.assertEqual(classify_source_row(row), FreshnessState.BLOCKED)

    def test_fallback_not_allowed_is_blocked(self) -> None:
        row = self._row(stale=True, stale_reasons=["fallback_not_allowed"])
        self.assertEqual(classify_source_row(row), FreshnessState.BLOCKED)

    def test_degraded_only_is_degraded(self) -> None:
        row = self._row(degraded=True, degradation_reasons=["upstream_freshness_stale"])
        self.assertEqual(classify_source_row(row), FreshnessState.DEGRADED)

    def test_stale_only_is_stale(self) -> None:
        row = self._row(stale=True, stale_reasons=["freshness_stale"])
        self.assertEqual(classify_source_row(row), FreshnessState.STALE)

    def test_freshness_expired_is_stale(self) -> None:
        row = self._row(stale=True, stale_reasons=["freshness_expired"])
        self.assertEqual(classify_source_row(row), FreshnessState.STALE)

    def test_invalid_dominates_blocked(self) -> None:
        # If both INVALID (trade_date_mismatch) and BLOCKED (live_small_not_allowed)
        # apply, INVALID wins because the data is structurally unusable.
        row = self._row(stale=True, stale_reasons=["trade_date_mismatch", "live_small_not_allowed"])
        self.assertEqual(classify_source_row(row), FreshnessState.INVALID)

    def test_blocked_dominates_stale(self) -> None:
        row = self._row(stale=True, stale_reasons=["freshness_stale", "live_small_not_allowed"])
        self.assertEqual(classify_source_row(row), FreshnessState.BLOCKED)


class StateAllowsMatrixTests(unittest.TestCase):
    # Authoritative matrix: state x capability -> allowed?
    EXPECTED = {
        FreshnessState.FRESH: {
            "observe": True, "review": True, "approve": True,
            "trade": True, "notify": True, "ledger_capture": True,
        },
        FreshnessState.DEGRADED: {
            "observe": True, "review": True, "approve": False,
            "trade": False, "notify": True, "ledger_capture": True,
        },
        FreshnessState.STALE: {
            "observe": True, "review": True, "approve": False,
            "trade": False, "notify": True, "ledger_capture": False,
        },
        FreshnessState.INVALID: {
            "observe": False, "review": False, "approve": False,
            "trade": False, "notify": True, "ledger_capture": False,
        },
        FreshnessState.BLOCKED: {
            "observe": True, "review": False, "approve": False,
            "trade": False, "notify": True, "ledger_capture": False,
        },
        FreshnessState.USABLE: {
            "observe": True, "review": True, "approve": False,
            "trade": False, "notify": True, "ledger_capture": False,
        },
    }

    def test_matrix_complete(self) -> None:
        for state, by_cap in self.EXPECTED.items():
            for cap, expected in by_cap.items():
                with self.subTest(state=state, capability=cap):
                    self.assertEqual(state_allows(state, cap), expected)

    def test_unknown_capability_defaults_false(self) -> None:
        self.assertFalse(state_allows(FreshnessState.FRESH, "totally_made_up_cap"))


if __name__ == "__main__":
    unittest.main()
```

### - [ ] Step 2.2: 跑测试，确认 fail

```bash
cd /Users/yangbishang/Projects/prism && python3.14 -m pytest apps/control-panel/tests/test_freshness_state.py -v
```

**Expected:** `ModuleNotFoundError: No module named 'freshness_state'`

### - [ ] Step 2.3: 创建 freshness_state.py 模块

写到 `apps/control-panel/freshness_state.py`：

```python
"""Six-state freshness classifier for Prism readiness source rows.

The readiness module exposes per-source ``stale`` / ``degraded`` / ``available``
booleans and a free-form ``stale_reasons`` list.  Downstream consumers (the
capability matrix, the future UI) need a small, explicit enum to reason
about: *what kind of "not fresh" is this row?*  Six states cover the
spectrum:

* FRESH    — aligned trade date, on-time, scope ok
* USABLE   — reserved for Phase 2 ("near threshold" early warning)
* STALE    — past TTL but still readable (degrade to observe/review)
* DEGRADED — fallback provider in use or authority not in target lane
* INVALID  — structurally unusable (missing manifest, trade-date mismatch)
* BLOCKED  — explicit policy bar (live_small_not_allowed, fallback_not_allowed)

``state_allows`` encodes which investment capabilities each state permits.
This is the authoritative matrix; capability_matrix consumes it directly.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping


__all__ = [
    "FreshnessState",
    "classify_source_row",
    "state_allows",
]


class FreshnessState(str, Enum):
    FRESH = "fresh"
    USABLE = "usable"
    STALE = "stale"
    DEGRADED = "degraded"
    INVALID = "invalid"
    BLOCKED = "blocked"


# Precedence: INVALID > BLOCKED > STALE > DEGRADED > USABLE > FRESH.
# Higher precedence means the data is more unusable; the classifier returns
# the worst applicable state.

_INVALID_REASONS = frozenset({
    "manifest_missing",
    "missing",
    "trade_date_mismatch",
    "trade_date_unknown",
    "freshness_unknown",
})

_BLOCKED_REASONS = frozenset({
    "live_small_not_allowed",
    "fallback_not_allowed",
})

_STALE_REASONS = frozenset({
    "freshness_stale",
    "freshness_expired",
})


def classify_source_row(row: Mapping[str, Any]) -> FreshnessState:
    """Classify one readiness source row into a single FreshnessState.

    The row shape comes from ``readiness.compute_readiness`` ``source_freshness``
    items: ``available``, ``stale``, ``degraded``, ``stale_reasons``,
    ``degradation_reasons`` (any of which may be missing).
    """
    available = bool(row.get("available"))
    stale = bool(row.get("stale"))
    degraded = bool(row.get("degraded"))
    reasons = {str(reason).strip() for reason in (row.get("stale_reasons") or [])}

    if not available or reasons & _INVALID_REASONS:
        return FreshnessState.INVALID
    if reasons & _BLOCKED_REASONS:
        return FreshnessState.BLOCKED
    if stale and reasons & _STALE_REASONS:
        return FreshnessState.STALE
    if stale:
        return FreshnessState.STALE
    if degraded:
        return FreshnessState.DEGRADED
    return FreshnessState.FRESH


_ALLOW_MATRIX: dict[FreshnessState, frozenset[str]] = {
    FreshnessState.FRESH: frozenset({"observe", "review", "approve", "trade", "notify", "ledger_capture"}),
    FreshnessState.DEGRADED: frozenset({"observe", "review", "notify", "ledger_capture"}),
    FreshnessState.STALE: frozenset({"observe", "review", "notify"}),
    FreshnessState.USABLE: frozenset({"observe", "review", "notify"}),
    FreshnessState.BLOCKED: frozenset({"observe", "notify"}),
    FreshnessState.INVALID: frozenset({"notify"}),
}


def state_allows(state: FreshnessState, capability: str) -> bool:
    return str(capability or "").strip() in _ALLOW_MATRIX.get(state, frozenset())
```

### - [ ] Step 2.4: 跑测试，确认 pass

```bash
cd /Users/yangbishang/Projects/prism && python3.14 -m pytest apps/control-panel/tests/test_freshness_state.py -v
```

**Expected:** 全部通过。

### - [ ] Step 2.5: Commit

```bash
git add apps/control-panel/freshness_state.py apps/control-panel/tests/test_freshness_state.py
git commit -m "$(cat <<'EOF'
feat(readiness): add FreshnessState six-state classifier

Collapse readiness module's scattered stale/degraded/available signals
into one explicit enum (FRESH/USABLE/STALE/DEGRADED/INVALID/BLOCKED) with
a capability allow matrix. USABLE is reserved for Phase 2.
EOF
)"
```

---

## Task 3: CapabilityMatrix 翻译层

**Files:**
- Create: `apps/control-panel/capability_matrix.py`
- Test: `apps/control-panel/tests/test_capability_matrix.py`

### - [ ] Step 3.1: 写测试

写到 `apps/control-panel/tests/test_capability_matrix.py`：

```python
"""Tests for capability_matrix — the investment-action translation layer.

These tests are the contract for what each of the six capabilities means in
business terms, and guard the rule that engineering jargon never leaks into
``why_not`` or ``degraded_path`` messages.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


INVEST_FLOW_ROOT = Path(__file__).resolve().parents[2]
if str(INVEST_FLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(INVEST_FLOW_ROOT))

from capability_matrix import (  # noqa: E402
    Capability,
    CapabilityReport,
    evaluate_capabilities,
)


KNOWN_CAPABILITIES = {c.value for c in Capability}
FORBIDDEN_TERMS = (
    "manifest",
    "stale_reasons",
    "live_small_not_allowed",
    "formal_decision_allowed",
    "freshness_status",
    "fallback_used",
)


def _source_row(
    key: str,
    *,
    label: str | None = None,
    available: bool = True,
    stale: bool = False,
    degraded: bool = False,
    stale_reasons: list[str] | None = None,
    formal_decision_allowed: bool = True,
    manifest_path: str = "/tmp/fake.manifest.json",
) -> dict[str, object]:
    return {
        "key": key,
        "label": label or {
            "watchlist": "自选股",
            "screening": "进攻型候选",
            "confirmation": "午盘承接确认",
            "decision_brief": "投资总控简报",
        }.get(key, key),
        "available": available,
        "stale": stale,
        "degraded": degraded,
        "stale_reasons": stale_reasons or [],
        "degradation_reasons": [],
        "formal_decision_allowed": formal_decision_allowed,
        "manifest_path": manifest_path,
    }


def _readiness(
    *,
    ready: bool = True,
    readiness_mode: str = "live_ready",
    formal_ready: bool = True,
    is_trading_day: bool = True,
    sources: list[dict[str, object]] | None = None,
    account_mode: str = "live_small",
    account_ready_for_live_small: bool = True,
    blockers: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    if sources is None:
        sources = [
            _source_row("watchlist"),
            _source_row("screening"),
            _source_row("confirmation"),
            _source_row("decision_brief"),
        ]
    return {
        "ready": ready,
        "readiness_mode": readiness_mode,
        "formal_ready": formal_ready,
        "session": {"is_trading_day": is_trading_day, "key": "morning", "label": "早盘"},
        "source_freshness": sources,
        "blockers": blockers or [],
        "warnings": [],
        "stale_count": sum(1 for s in sources if s.get("stale")),
        "checked_at": "2026-05-22 09:35:00",
        "recommended_tasks": [],
        "account_state": {
            "mode": account_mode,
            "ready_for_live_small": account_ready_for_live_small,
            "reconciliation": {"fresh": True, "age_seconds": 3600, "age_label": "1 小时前"},
            "blockers": [],
            "warnings": [],
            "recommended_tasks": [],
        },
    }


class GoldenPathTests(unittest.TestCase):
    def test_all_caps_granted_when_fully_ready(self) -> None:
        result = evaluate_capabilities(readiness_payload=_readiness())
        self.assertEqual(set(result.keys()), KNOWN_CAPABILITIES)
        for cap, report in result.items():
            with self.subTest(capability=cap):
                self.assertIsInstance(report, CapabilityReport)
                self.assertTrue(report.granted, f"{cap} should be granted; why_not={report.why_not}")
                self.assertEqual(report.status, "ok")
                self.assertEqual(report.why_not, [])

    def test_status_ok_implies_granted(self) -> None:
        result = evaluate_capabilities(readiness_payload=_readiness())
        for cap, report in result.items():
            with self.subTest(capability=cap):
                if report.status == "ok":
                    self.assertTrue(report.granted)


class StaleWatchlistTests(unittest.TestCase):
    def setUp(self) -> None:
        payload = _readiness(
            ready=False,
            readiness_mode="blocked",
            sources=[
                _source_row("watchlist", stale=True, stale_reasons=["freshness_stale"]),
                _source_row("screening"),
                _source_row("confirmation"),
                _source_row("decision_brief"),
            ],
            blockers=[
                {
                    "code": "watchlist_stale",
                    "label": "自选股",
                    "message": "自选股偏旧",
                    "recommended_task": "watchlist_refresh",
                },
            ],
        )
        self.result = evaluate_capabilities(readiness_payload=payload)

    def test_trade_blocked(self) -> None:
        self.assertFalse(self.result["trade"].granted)
        self.assertEqual(self.result["trade"].status, "blocked")

    def test_approve_blocked(self) -> None:
        self.assertFalse(self.result["approve"].granted)

    def test_observe_still_granted(self) -> None:
        # observe should remain granted (data is STALE not INVALID).
        self.assertTrue(self.result["observe"].granted)

    def test_notify_always_granted(self) -> None:
        self.assertTrue(self.result["notify"].granted)


class NonTradingDayTests(unittest.TestCase):
    def test_trade_blocked_outside_trading_day(self) -> None:
        payload = _readiness(
            ready=False,
            readiness_mode="shadow_only",
            is_trading_day=False,
        )
        result = evaluate_capabilities(readiness_payload=payload)
        self.assertFalse(result["trade"].granted)
        # observe should still work
        self.assertTrue(result["observe"].granted)


class ResearchModeTests(unittest.TestCase):
    def test_trade_blocked_when_account_not_live_small(self) -> None:
        payload = _readiness(account_mode="research", account_ready_for_live_small=False)
        result = evaluate_capabilities(readiness_payload=payload)
        self.assertFalse(result["trade"].granted)
        self.assertTrue(result["observe"].granted)
        self.assertTrue(result["review"].granted)


class FormalReadyDivergenceTests(unittest.TestCase):
    def test_approve_degraded_when_data_fresh_but_not_formal_ready(self) -> None:
        payload = _readiness(formal_ready=False)
        result = evaluate_capabilities(readiness_payload=payload)
        self.assertFalse(result["approve"].granted)
        self.assertEqual(result["approve"].status, "degraded")
        # trade can still go through (formal_ready != trade gate)
        self.assertTrue(result["trade"].granted)


class InvalidSourceTests(unittest.TestCase):
    def test_trade_date_mismatch_invalidates_dependent_caps(self) -> None:
        payload = _readiness(
            ready=False,
            readiness_mode="blocked",
            sources=[
                _source_row("watchlist", stale=True, stale_reasons=["trade_date_mismatch"]),
                _source_row("screening"),
                _source_row("confirmation"),
                _source_row("decision_brief"),
            ],
            blockers=[{
                "code": "trade_date_mismatch",
                "label": "数据交易日",
                "message": "数据交易日不匹配",
                "recommended_task": "watchlist_refresh",
            }],
        )
        result = evaluate_capabilities(readiness_payload=payload)
        # watchlist supports observe/review/approve/trade → all impacted
        self.assertFalse(result["trade"].granted)
        self.assertFalse(result["approve"].granted)
        self.assertIn("watchlist.snapshot", result["trade"].blocking_sources)


class DegradedPathTests(unittest.TestCase):
    def test_blocked_caps_must_provide_degraded_path(self) -> None:
        payload = _readiness(
            ready=False,
            readiness_mode="blocked",
            sources=[
                _source_row("watchlist", stale=True, stale_reasons=["freshness_stale"]),
                _source_row("screening"),
                _source_row("confirmation"),
                _source_row("decision_brief"),
            ],
            blockers=[{
                "code": "watchlist_stale", "label": "自选股", "message": "偏旧",
                "recommended_task": "watchlist_refresh",
            }],
        )
        result = evaluate_capabilities(readiness_payload=payload)
        # When trade is blocked, the system must explicitly say what user CAN do.
        trade_report = result["trade"]
        self.assertFalse(trade_report.granted)
        self.assertTrue(trade_report.degraded_path, "blocked capability must list a degraded_path")


class JargonLeakTests(unittest.TestCase):
    """Engineering jargon MUST NOT appear in operator-facing strings."""

    def _all_messages(self, result: dict[str, CapabilityReport]) -> list[str]:
        out: list[str] = []
        for report in result.values():
            for bucket in (report.why_not, report.degraded_path):
                for item in bucket:
                    out.append(str(item.get("message") or ""))
                    out.append(str(item.get("label") or ""))
        return out

    def test_messages_have_no_engineering_jargon(self) -> None:
        scenarios = [
            _readiness(),
            _readiness(formal_ready=False),
            _readiness(
                ready=False, readiness_mode="blocked",
                sources=[
                    _source_row("watchlist", stale=True, stale_reasons=["live_small_not_allowed"]),
                    _source_row("screening"),
                    _source_row("confirmation"),
                    _source_row("decision_brief"),
                ],
                blockers=[{
                    "code": "watchlist_blocked", "label": "自选股",
                    "message": "数据源未放行真钱执行",
                    "recommended_task": "watchlist_refresh",
                }],
            ),
        ]
        for payload in scenarios:
            with self.subTest(scenario=payload.get("readiness_mode")):
                result = evaluate_capabilities(readiness_payload=payload)
                joined = "\n".join(self._all_messages(result))
                for term in FORBIDDEN_TERMS:
                    self.assertNotIn(term, joined, f"jargon '{term}' leaked into messages")


class NextActionsTests(unittest.TestCase):
    def test_next_actions_reference_known_tasks(self) -> None:
        payload = _readiness(
            ready=False, readiness_mode="blocked",
            sources=[
                _source_row("decision_brief", stale=True, stale_reasons=["freshness_stale"]),
                _source_row("watchlist"),
                _source_row("screening"),
                _source_row("confirmation"),
            ],
            blockers=[{
                "code": "decision_brief_stale", "label": "投资总控简报",
                "message": "简报偏旧", "recommended_task": "command_brief",
            }],
        )
        result = evaluate_capabilities(readiness_payload=payload)
        approve = result["approve"]
        task_names = [a.get("task_name") for a in approve.next_actions]
        self.assertIn("command_brief", task_names)


if __name__ == "__main__":
    unittest.main()
```

### - [ ] Step 3.2: 跑测试，确认 fail

```bash
cd /Users/yangbishang/Projects/prism && python3.14 -m pytest apps/control-panel/tests/test_capability_matrix.py -v
```

**Expected:** `ModuleNotFoundError: No module named 'capability_matrix'`

### - [ ] Step 3.3: 创建 capability_matrix.py 模块

写到 `apps/control-panel/capability_matrix.py`：

```python
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
```

### - [ ] Step 3.4: 跑测试，确认 pass

```bash
cd /Users/yangbishang/Projects/prism && python3.14 -m pytest apps/control-panel/tests/test_capability_matrix.py -v
```

**Expected:** 全部通过。

### - [ ] Step 3.5: Commit

```bash
git add apps/control-panel/capability_matrix.py apps/control-panel/tests/test_capability_matrix.py
git commit -m "$(cat <<'EOF'
feat(readiness): add CapabilityMatrix translation layer

Translate engineering-language readiness payload into 6 investment
capabilities (observe/review/approve/trade/notify/ledger_capture) with
business-language why_not + degraded_path. Tests guard the no-jargon
contract on operator-facing strings.
EOF
)"
```

---

## Task 4: 把 source_states + capabilities 接入 `compute_readiness`

**Files:**
- Modify: `apps/control-panel/readiness.py`
- Test: `apps/control-panel/tests/test_readiness.py` (新增一个测试类，不动现有)

### - [ ] Step 4.1: 先看现有 `compute_readiness` 返回结构

打开 [apps/control-panel/readiness.py](apps/control-panel/readiness.py) 第 820–843 行的 return dict。我们要在 dict 末尾追加两个 key，**不动任何已有 key**。

### - [ ] Step 4.2: 写新测试（先 fail）

在 `apps/control-panel/tests/test_readiness.py` 末尾追加这个新测试类：

```python


class ReadinessCapabilityExtensionTests(unittest.TestCase):
    """Phase 1 additive contract: source_states + capabilities appear on the
    readiness payload without disturbing any existing field."""

    def _golden_inputs(self) -> dict[str, object]:
        now = datetime(2026, 5, 22, 9, 35, 0)
        expected = "2026-05-22"
        manifest = _manifest(
            dataset="watchlist.snapshot",
            trade_date=expected,
            generated_at="2026-05-22 09:30:00",
        )
        return {
            "watchlist": {
                "trade_date": expected,
                "generated_at": "2026-05-22 09:30:00",
                "manifest": manifest,
            },
            "screening_batch": {
                "trade_date": expected,
                "generated_at": "2026-05-22 09:32:00",
                "manifest": _manifest(
                    dataset="screening.batch",
                    trade_date=expected,
                    generated_at="2026-05-22 09:32:00",
                ),
            },
            "confirmation": {
                "trade_date": expected,
                "generated_at": "2026-05-22 09:34:00",
                "manifest": _manifest(
                    dataset="screening.confirmation",
                    trade_date=expected,
                    generated_at="2026-05-22 09:34:00",
                ),
            },
            "decision_brief": {
                "trade_date": expected,
                "generated_at": "2026-05-22 09:35:00",
                "manifest": _manifest(
                    dataset="decision_brief.snapshot",
                    trade_date=expected,
                    generated_at="2026-05-22 09:35:00",
                ),
            },
            "quality_status": {
                "watchlist": {"validation_status": "ok", "checked_at": "2026-05-22 09:30:00"},
                "aggressive": {"validation_status": "ok", "checked_at": "2026-05-22 09:32:00"},
                "midday_confirmation": {"validation_status": "ok", "checked_at": "2026-05-22 09:34:00"},
            },
            "now": now,
            "expected_date": expected,
        }

    def test_source_states_field_present(self) -> None:
        payload = compute_readiness(**self._golden_inputs())
        self.assertIn("source_states", payload)
        self.assertIsInstance(payload["source_states"], dict)
        # All 4 pipeline sources reported.
        for key in ("watchlist", "screening", "confirmation", "decision_brief"):
            self.assertIn(key, payload["source_states"], f"missing source_states key {key}")
        # Values are FreshnessState enum strings.
        for value in payload["source_states"].values():
            self.assertIn(value, {"fresh", "usable", "stale", "degraded", "invalid", "blocked"})

    def test_capabilities_field_present(self) -> None:
        payload = compute_readiness(**self._golden_inputs())
        self.assertIn("capabilities", payload)
        caps = payload["capabilities"]
        for name in ("observe", "review", "approve", "trade", "notify", "ledger_capture"):
            self.assertIn(name, caps, f"missing capability {name}")
            report = caps[name]
            self.assertIn("status", report)
            self.assertIn("granted", report)
            self.assertIn("why_not", report)
            self.assertIn("degraded_path", report)

    def test_existing_payload_fields_unchanged(self) -> None:
        payload = compute_readiness(**self._golden_inputs())
        # Every existing top-level field must still be there.
        for key in (
            "expected_trade_date", "data_trade_date", "display_date", "checked_at",
            "session", "readiness_mode", "ready", "brief_is_live", "stale_count",
            "blockers", "warnings", "formal_ready", "formal_blockers",
            "source_freshness", "quality_freshness", "recommended_tasks",
            "account_state", "calendar_horizon",
        ):
            self.assertIn(key, payload, f"existing field disappeared: {key}")
```

### - [ ] Step 4.3: 跑测试看 fail

```bash
cd /Users/yangbishang/Projects/prism && python3.14 -m pytest apps/control-panel/tests/test_readiness.py::ReadinessCapabilityExtensionTests -v
```

**Expected:** `test_source_states_field_present` 和 `test_capabilities_field_present` fail（缺字段）；`test_existing_payload_fields_unchanged` 应该 pass（现有字段都还在）。

### - [ ] Step 4.4: 修改 readiness.py，在 return dict 末尾追加新字段

打开 [apps/control-panel/readiness.py](apps/control-panel/readiness.py)。在文件顶部 imports 区追加（第 30 行附近，与其他 `from typing import ...` 对齐）：

```python
from freshness_state import FreshnessState, classify_source_row
from capability_matrix import evaluate_capabilities
```

然后定位 `compute_readiness` 函数末尾的 return 语句（spec 引用第 824–843 行）。这个 return dict 末尾当前是 `"account_state": account_state,`。在它后面、return 闭合的 `}` 之前，先构造两个字典，再追加到 return dict。

具体改动如下——在 return 语句**之前**插入：

```python
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
```

然后在 return dict 的最后两行（`"account_state": account_state,` 之后）插入：

```python
        "source_states": source_state_map,
        "capabilities": capabilities_payload,
```

完整的 return 末尾变成：

```python
    return {
        # ... existing fields unchanged ...
        "account_state": account_state,
        "source_states": source_state_map,
        "capabilities": capabilities_payload,
    }
```

### - [ ] Step 4.5: 跑新测试，确认 pass

```bash
cd /Users/yangbishang/Projects/prism && python3.14 -m pytest apps/control-panel/tests/test_readiness.py::ReadinessCapabilityExtensionTests -v
```

**Expected:** 3 个新测试全部通过。

### - [ ] Step 4.6: 跑现有 readiness 测试全套，确认无回归

```bash
cd /Users/yangbishang/Projects/prism && python3.14 -m pytest apps/control-panel/tests/test_readiness.py apps/control-panel/tests/test_readiness_account_state.py apps/control-panel/tests/test_readiness_reconciliation_delta.py -v
```

**Expected:** 全部通过，**没有 skip 或 fail**。

### - [ ] Step 4.7: Commit

```bash
git add apps/control-panel/readiness.py apps/control-panel/tests/test_readiness.py
git commit -m "$(cat <<'EOF'
feat(readiness): emit source_states + capabilities on compute_readiness

compute_readiness now returns two additive fields:
- source_states: {source_key: FreshnessState.value}
- capabilities: {capability: CapabilityReport.as_dict()}

No existing field is modified. Front-end consumers that ignore these new
keys are unaffected. Backward-compat asserted by ReadinessCapability-
ExtensionTests.test_existing_payload_fields_unchanged.
EOF
)"
```

---

## Task 5: 新增 `/api/source-budget` 端点

**Files:**
- Modify: `apps/control-panel/app.py`
- Test: `apps/control-panel/tests/test_capabilities_endpoint.py`

### - [ ] Step 5.1: 写测试

新建 `apps/control-panel/tests/test_capabilities_endpoint.py`：

```python
"""Integration tests for the Phase 1 read-only capability + budget endpoints."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


INVEST_FLOW_ROOT = Path(__file__).resolve().parents[2]
if str(INVEST_FLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(INVEST_FLOW_ROOT))

from fastapi.testclient import TestClient

from control_panel.app import app  # noqa: E402


class SourceBudgetEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_returns_200(self) -> None:
        response = self.client.get("/api/source-budget")
        self.assertEqual(response.status_code, 200)

    def test_payload_shape(self) -> None:
        body = self.client.get("/api/source-budget").json()
        self.assertIn("datasets", body)
        datasets = body["datasets"]
        self.assertIsInstance(datasets, list)
        self.assertGreaterEqual(len(datasets), 15)
        sample = datasets[0]
        for key in (
            "dataset", "label", "role", "cost_class", "cadence", "batchable",
            "min_refresh_interval_seconds", "primary_provider",
            "fallback_providers", "decision_scope", "supports_capabilities",
            "failure_impact",
        ):
            self.assertIn(key, sample, f"missing {key} in /api/source-budget payload")


if __name__ == "__main__":
    unittest.main()
```

### - [ ] Step 5.2: 跑测试，确认 fail

```bash
cd /Users/yangbishang/Projects/prism && python3.14 -m pytest apps/control-panel/tests/test_capabilities_endpoint.py::SourceBudgetEndpointTests -v
```

**Expected:** `404 Not Found`（端点还没注册）。

### - [ ] Step 5.3: 注册端点

打开 [apps/control-panel/app.py](apps/control-panel/app.py)。在 imports 区（其他 `from <module> import ...` 那一片）追加：

```python
from source_budget import build_source_budget_payload
```

然后定位 `@app.get("/api/readiness/live")` 这个函数（约第 1770 行）。在它**前面**插入新端点：

```python
@app.get("/api/source-budget")
async def api_source_budget() -> JSONResponse:
    """Static business profile registry for all Prism data sources.

    Read-only. Does not trigger any task or fetch. Useful for capability
    diagnostics and future UI panels.
    """
    return JSONResponse(build_source_budget_payload())


```

### - [ ] Step 5.4: 跑测试，确认 pass

```bash
cd /Users/yangbishang/Projects/prism && python3.14 -m pytest apps/control-panel/tests/test_capabilities_endpoint.py::SourceBudgetEndpointTests -v
```

**Expected:** 2 个测试全部通过。

### - [ ] Step 5.5: Commit

```bash
git add apps/control-panel/app.py apps/control-panel/tests/test_capabilities_endpoint.py
git commit -m "$(cat <<'EOF'
feat(api): add read-only /api/source-budget endpoint

Exposes SOURCE_BUDGETS for downstream tooling and the future capability
UI. Strictly read-only; no fetch, no side effect.
EOF
)"
```

---

## Task 6: 新增 `/api/capabilities` 端点

**Files:**
- Modify: `apps/control-panel/app.py`
- Test: append to `apps/control-panel/tests/test_capabilities_endpoint.py`

### - [ ] Step 6.1: 写测试

在 `apps/control-panel/tests/test_capabilities_endpoint.py` 末尾追加：

```python


class CapabilitiesEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_returns_200(self) -> None:
        response = self.client.get("/api/capabilities")
        self.assertEqual(response.status_code, 200)

    def test_returns_six_capabilities(self) -> None:
        body = self.client.get("/api/capabilities").json()
        self.assertIn("capabilities", body)
        caps = body["capabilities"]
        for name in ("observe", "review", "approve", "trade", "notify", "ledger_capture"):
            self.assertIn(name, caps, f"missing capability {name}")

    def test_each_capability_has_required_fields(self) -> None:
        body = self.client.get("/api/capabilities").json()
        for name, report in body["capabilities"].items():
            with self.subTest(capability=name):
                for field in (
                    "capability", "status", "granted",
                    "why_not", "degraded_path", "next_actions",
                    "blocking_sources", "last_checked_at",
                ):
                    self.assertIn(field, report, f"{name} missing {field}")

    def test_includes_top_level_metadata(self) -> None:
        body = self.client.get("/api/capabilities").json()
        self.assertIn("checked_at", body)
        self.assertIn("session", body)
```

### - [ ] Step 6.2: 跑测试，确认 fail

```bash
cd /Users/yangbishang/Projects/prism && python3.14 -m pytest apps/control-panel/tests/test_capabilities_endpoint.py::CapabilitiesEndpointTests -v
```

**Expected:** `404 Not Found`。

### - [ ] Step 6.3: 注册端点

在 [apps/control-panel/app.py](apps/control-panel/app.py) 紧跟 `/api/source-budget` 的位置插入：

```python
@app.get("/api/capabilities")
async def api_capabilities() -> JSONResponse:
    """Read-only capability matrix for the current readiness payload.

    Returns 6 investment capabilities (observe/review/approve/trade/notify/
    ledger_capture) translated from the engineering-language readiness into
    operator-facing status, why_not and degraded_path. Strictly read-only.
    """
    today_view = build_today_view()
    readiness = today_view.get("readiness") or {}
    return JSONResponse(
        {
            "checked_at": readiness.get("checked_at"),
            "session": readiness.get("session"),
            "capabilities": readiness.get("capabilities", {}),
        }
    )


```

### - [ ] Step 6.4: 跑测试，确认 pass

```bash
cd /Users/yangbishang/Projects/prism && python3.14 -m pytest apps/control-panel/tests/test_capabilities_endpoint.py -v
```

**Expected:** 该文件下全部 6 个测试通过。

### - [ ] Step 6.5: Commit

```bash
git add apps/control-panel/app.py apps/control-panel/tests/test_capabilities_endpoint.py
git commit -m "$(cat <<'EOF'
feat(api): add read-only /api/capabilities endpoint

Serves the capability matrix from compute_readiness for downstream
diagnostics. Strictly read-only — never triggers tasks or fetches.
EOF
)"
```

---

## Task 7: 扩展 `/api/readiness/live` 暴露新字段 + 全量回归

**Files:**
- Modify: `apps/control-panel/app.py` (一处)
- Test: append to `apps/control-panel/tests/test_capabilities_endpoint.py`

### - [ ] Step 7.1: 写测试

在 `apps/control-panel/tests/test_capabilities_endpoint.py` 末尾追加：

```python


class ReadinessLiveExtensionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_existing_keys_still_present(self) -> None:
        body = self.client.get("/api/readiness/live").json()
        for key in (
            "generated_at", "expected_trade_date", "data_trade_date",
            "display_date", "trade_date", "readiness_mode", "ready", "session",
            "stale_count", "blockers", "warnings", "source_freshness",
            "quality_freshness", "recommended_tasks",
        ):
            self.assertIn(key, body, f"/api/readiness/live regression: {key} missing")

    def test_new_keys_added(self) -> None:
        body = self.client.get("/api/readiness/live").json()
        self.assertIn("source_states", body)
        self.assertIn("capabilities", body)
        self.assertIsInstance(body["source_states"], dict)
        self.assertIsInstance(body["capabilities"], dict)
```

### - [ ] Step 7.2: 跑测试，确认 new_keys 测试 fail

```bash
cd /Users/yangbishang/Projects/prism && python3.14 -m pytest apps/control-panel/tests/test_capabilities_endpoint.py::ReadinessLiveExtensionTests -v
```

**Expected:** `test_existing_keys_still_present` pass; `test_new_keys_added` fail (response 里没有这两个 key)。

### - [ ] Step 7.3: 修改 `/api/readiness/live` 把新字段补进 allowlist

在 [apps/control-panel/app.py](apps/control-panel/app.py) 第 1781-1797 那段 `api_readiness_live()` return JSONResponse(...)，在 dict 末尾追加两行 key（保留原有顺序）：

原来的：
```python
    return JSONResponse(
        {
            "generated_at": today_view.get("generated_at"),
            "expected_trade_date": readiness.get("expected_trade_date"),
            ...
            "recommended_tasks": readiness.get("recommended_tasks", []),
        }
```

改成：
```python
    return JSONResponse(
        {
            "generated_at": today_view.get("generated_at"),
            "expected_trade_date": readiness.get("expected_trade_date"),
            ...
            "recommended_tasks": readiness.get("recommended_tasks", []),
            "source_states": readiness.get("source_states", {}),
            "capabilities": readiness.get("capabilities", {}),
        }
```

### - [ ] Step 7.4: 跑测试，确认 pass

```bash
cd /Users/yangbishang/Projects/prism && python3.14 -m pytest apps/control-panel/tests/test_capabilities_endpoint.py -v
```

**Expected:** 该文件全部测试通过（含 ReadinessLiveExtensionTests 2 个）。

### - [ ] Step 7.5: 全量回归测试

```bash
cd /Users/yangbishang/Projects/prism && python3.14 -m pytest apps/control-panel/tests/ -v
```

**Expected:** 全部通过。如果有任何回归（特别是 `test_readiness.py`、`test_refresh_policy.py`、`test_app_smoke.py`、`test_portfolio_endpoints.py`、`test_account_book.py`），停下来定位修复；不要 commit broken 状态。

### - [ ] Step 7.6: Commit

```bash
git add apps/control-panel/app.py apps/control-panel/tests/test_capabilities_endpoint.py
git commit -m "$(cat <<'EOF'
feat(api): surface source_states + capabilities on /api/readiness/live

Adds the two new readiness fields to the operator endpoint's allowlist.
Backward compatible — all prior keys remain. Tests assert no regression
on the full readiness payload.
EOF
)"
```

---

## Final verification checklist

After Task 7 is committed:

- [ ] `git log --oneline -7` 显示 7 个 commit，每个都聚焦一个任务
- [ ] `python3.14 -m pytest apps/control-panel/tests/ -v` 全部通过、无 skip
- [ ] `curl -s localhost:<port>/api/source-budget | jq '.datasets | length'` 返回 17（或以上）
- [ ] `curl -s localhost:<port>/api/capabilities | jq '.capabilities | keys'` 返回 6 个能力
- [ ] `curl -s localhost:<port>/api/readiness/live | jq '.source_states, .capabilities'` 都非空
- [ ] **前端没有任何改动**：`git diff origin/codex/ask-v2 -- apps/web/` 为空（除非 user 已经在做的改动）
- [ ] **现有任务/策略没有任何改动**：`git diff origin/codex/ask-v2 -- apps/control-panel/refresh_policy.py apps/scripts/` 与本 plan 改动无关

---

## Spec coverage self-review

- Spec §4.1 SourceBudget → Task 1 ✓
- Spec §4.2 FreshnessState → Task 2 ✓
- Spec §4.3 CapabilityMatrix → Task 3 ✓
- Spec §4.4 扩展 readiness payload → Task 4 ✓
- Spec §4.5 /api/source-budget → Task 5 ✓
- Spec §4.5 /api/capabilities → Task 6 ✓
- Spec §4.5 + 隐含 /api/readiness/live 扩展 → Task 7 ✓
- Spec §5 测试覆盖：source_budget 8 个 + freshness_state 12 个 + capability_matrix 9 个 + endpoint 8 个 + readiness 扩展 3 个 ≈ 40 个新测试 ✓
- Spec §6 文件清单与本 plan 实施清单完全对齐 ✓
- Spec §10 验收标准每条对应 Final verification checklist 中一条 ✓
- Spec §9 安全边界（不动 UI、不动现有逻辑、不强制 throttle、不删现有诊断入口）由 Task 7 的 final regression 兜底 ✓
