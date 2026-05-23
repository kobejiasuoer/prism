# Prism 刷新可信度系统 — Phase 1 设计

**日期**：2026-05-22
**作者**：技术负责人（Claude，代笔人类决策者）
**状态**：Draft，待审阅
**关联代码**：`apps/control-panel/refresh_policy.py`、`apps/control-panel/readiness.py`、`packages/prism_data/manifest.py`、`apps/web/src/lib/readiness-copy.ts`

---

## 1. 战略判断

Prism 的刷新骨架其实已经基本到位：

- `packages/prism_data/manifest.py` 已经声明了完整的 dataset 注册表（TTL、provider chain、decision_scope）。
- `apps/control-panel/refresh_policy.py` 已经把任务、时间窗口、cooldown、PagePolicy 数据化。
- `apps/control-panel/readiness.py` 已经能用 fail-closed 规则算出 `live_ready / shadow_only / blocked`。
- `apps/scripts/prism_scheduler.py` 已经有真正的后台 daemon + cron policy。

**核心矛盾不是"刷新系统没建好"，而是"系统在说工程语言，前端被迫复读工程语言"。** 现在用户看到的是 `manifest_not_stale` / `watchlist_refresh` / `safe refresh` / `unsafe_apply` / `formal_ready` / "后端尚未返回 command_brief"。用户想看到的是「现在能不能观察、复核、放行、交易」。

Phase 1 不重写任何核心逻辑。只**在 readiness 之上加一层"投资动作能力 → 后端真相"的翻译**，并把"数据源治理画像"显式化。前端在 Phase 2 / 3 才会重写。

---

## 2. 目标分层

```
┌───────────────────────────────────────────────────────────┐
│ Capability Layer (新增, Phase 1 后端 + API)               │
│ observe / review / approve / trade / notify / ledger      │
│ 每个能力: status / why_not / degraded_path / next_action  │
└───────────────────────────────────────────────────────────┘
                              ▲ 翻译
┌───────────────────────────────────────────────────────────┐
│ Readiness Layer (现有, Phase 1 只扩展字段)                │
│ live_ready/shadow_only/blocked + source_freshness 等       │
└───────────────────────────────────────────────────────────┘
                              ▲ 喂入
┌───────────────────────────────────────────────────────────┐
│ Source Layer (现有 manifest + 新增 source_budget)         │
│ dataset registry / TTL / provider chain                   │
│ + min_refresh_interval / cost_class / batchable / role    │
└───────────────────────────────────────────────────────────┘
                              ▲ 治理
┌───────────────────────────────────────────────────────────┐
│ Task Layer (现有 refresh_policy, Phase 1 不动)            │
└───────────────────────────────────────────────────────────┘
```

**新增的只有顶层 Capability、底层 Source Budget、以及中间一个状态枚举工具。中间两层一律不改逻辑、只补字段。**

---

## 3. Phase 1 范围（已与用户对齐）

- **A 档**：纯后端基础设施 + API。不动任何前端代码。
- **Budget 强度**：纯静态配置 + 查询 API。不接入 `evaluate_auto_refresh` 决策。

明确不做的事：

- 不改 `refresh_policy.py` 内部判断逻辑（只允许新增字段读取）。
- 不改 `readiness.py` 已有判断逻辑（只允许在 payload 末尾追加新字段）。
- 不动任何 `apps/web/` 代码。
- 不引入实际的 rate-limit 强制阻断。
- 不删除任何现有任务、端点、状态机。
- 不动 cron policy。
- 不改 account_state / decision_ledger / command_brief 业务逻辑。

---

## 4. 新增模块

### 4.1 `apps/control-panel/source_budget.py`（新文件）

**职责**：把 `packages/prism_data/manifest.py` 里的数据源声明，**配合 Prism 的业务用途**，浓缩成一份静态画像。它**不是** rate-limiter，只是真相注册表。

**数据结构**：

```python
@dataclass(frozen=True)
class SourceBudget:
    dataset: str                       # 对齐 manifest.py dataset key (e.g. "quotes.batch")
    label: str                         # 中文标签 "批量行情"
    role: str                          # "market_data" | "fundamentals" | "news" | "pipeline_artifact" | "account"
    cost_class: str                    # "cheap" | "moderate" | "heavy"
    cadence: str                       # "intraday_high" | "intraday_medium" | "daily" | "event"
    batchable: bool
    min_refresh_interval_seconds: int  # 派生自 manifest TTL,语义化下界
    primary_provider: str
    fallback_providers: tuple[str, ...]
    decision_scope: str                # "live_small" | "display_only"
    supports_capabilities: tuple[str, ...]  # 该数据源覆盖哪些 capability
    failure_impact: str                # 简短中文描述失败影响
```

**关键 API**：

```python
SOURCE_BUDGETS: dict[str, SourceBudget]  # 静态注册表

def source_budget(dataset: str) -> SourceBudget | None
def budgets_for_capability(capability: str) -> list[SourceBudget]
def budgets_for_role(role: str) -> list[SourceBudget]
def build_source_budget_payload() -> dict[str, Any]  # for /api endpoint
```

**初始注册表**（Phase 1 完整列出，对齐 manifest.py）：

| dataset | role | cost_class | cadence | min_interval | scope | capabilities |
|---|---|---|---|---|---|---|
| quotes.batch | market_data | cheap | intraday_high | 60s | live_small | observe / review / approve / trade |
| quotes.snapshot | market_data | cheap | intraday_high | 60s | live_small | observe / trade |
| quotes.pool | market_data | cheap | intraday_medium | 300s | display_only | observe |
| capital_flow.batch | market_data | moderate | intraday_medium | 180s | live_small | observe / review |
| capital_flow.daily | market_data | moderate | intraday_medium | 300s | live_small | review |
| bars.daily | market_data | moderate | daily | 1800s | live_small | review / approve |
| fundamentals.batch | fundamentals | cheap | daily | 21600s | display_only | review |
| fundamentals.snapshot | fundamentals | cheap | daily | 21600s | display_only | review |
| news.latest | news | moderate | event | 3600s | display_only | review |
| announcements.latest | news | moderate | event | 3600s | display_only | review |
| sector.snapshot | market_data | cheap | intraday_medium | 1800s | display_only | review |
| index.constituents | market_data | cheap | daily | 86400s | display_only | review |
| watchlist.snapshot | pipeline_artifact | heavy | daily | 900s | live_small | observe / review / approve / trade |
| screening.batch | pipeline_artifact | heavy | daily | 900s | live_small | review / approve |
| screening.confirmation | pipeline_artifact | heavy | daily | 900s | live_small | approve / trade |
| decision_brief.snapshot | pipeline_artifact | heavy | daily | 900s | live_small | review / approve |
| account.book | account | cheap | event | 60s | live_small | trade / ledger_capture |

**`min_refresh_interval_seconds` 的语义**：这是**该数据源在主动刷新场景下，两次实拉之间的"语义化下界"**。它源自 manifest TTL，但代表「业务期望」而非「provider rate limit」。Phase 1 它只供查询，不参与决策。

### 4.2 `apps/control-panel/freshness_state.py`（新文件）

**职责**：把现有 readiness 里散落的 stale / degraded / deferred / available / formal_decision_allowed / live_small_allowed / trade_date_mismatch 等若干标志，**收成一个显式六态枚举 + 一个分类函数**。

```python
class FreshnessState(str, Enum):
    FRESH = "fresh"           # 已对齐预期交易日 + 时间新 + scope ok
    USABLE = "usable"         # 数据可用但接近阈值,可读不可放行
    STALE = "stale"           # 已过 TTL,但可降级展示
    DEGRADED = "degraded"     # 走 fallback provider 或权威源未就位
    INVALID = "invalid"       # trade_date 不对、provider 失败,不能用
    BLOCKED = "blocked"       # 显式禁止 (live_small_not_allowed 等)

def classify_source_row(row: Mapping[str, Any]) -> FreshnessState
def state_allows(state: FreshnessState, capability: str) -> bool
```

**判定规则**（对照 readiness 现有逻辑，不重新发明）：

| 现有 readiness 信号 | 映射 FreshnessState |
|---|---|
| `available=False` 或 `manifest_missing` | `INVALID` |
| `stale_reasons` 含 `trade_date_mismatch` / `trade_date_unknown` | `INVALID` |
| `stale_reasons` 含 `live_small_not_allowed` | `BLOCKED` |
| `stale_reasons` 含 `fallback_not_allowed` | `BLOCKED` |
| `degraded=True` 且 `stale=False` 且 `available=True` | `DEGRADED` |
| `stale=True` 且 `available=True` 且无 `INVALID`/`BLOCKED` 因素 | `STALE` |
| 全绿 | `FRESH` |
| Phase 1 暂不实现 USABLE（占位，等 Phase 2 引入"接近阈值"概念） | — |

`state_allows(state, capability)`：能力是否允许在该状态下执行。Phase 1 的矩阵：

| state | observe | review | approve | trade | notify | ledger_capture |
|---|---|---|---|---|---|---|
| FRESH | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| DEGRADED | ✓ | ✓ | ✗ | ✗ | ✓ | ✓ |
| STALE | ✓ | ✓ | ✗ | ✗ | ✓ | ✗ |
| INVALID | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ |
| BLOCKED | ✓ | ✗ | ✗ | ✗ | ✓ | ✗ |
| USABLE (预留) | ✓ | ✓ | ✗ | ✗ | ✓ | ✗ |

### 4.3 `apps/control-panel/capability_matrix.py`（新文件）

**职责**：消费 readiness payload + account_state + freshness_state + source_budget，输出投资动作能力视图。

```python
class Capability(str, Enum):
    OBSERVE = "observe"               # 看盘、读数据
    REVIEW = "review"                 # 复核简报、判断、reasoning chain
    APPROVE = "approve"               # 放行 formal 决策(进入命令台)
    TRADE = "trade"                   # 可以下单(手工外部下单)
    NOTIFY = "notify"                 # 可以触发 Feishu 通知
    LEDGER_CAPTURE = "ledger_capture" # 写真实账本/对账

@dataclass(frozen=True)
class CapabilityReport:
    capability: Capability
    status: str                       # "ok" | "degraded" | "blocked"
    granted: bool                     # 业务侧能不能做这件事
    why_not: list[dict]               # [{code, label, message}]
    degraded_path: list[dict]         # [{code, label, message}] 即使 degraded 还能做什么
    next_actions: list[dict]          # [{task_name, title, kind, reason}]
    blocking_sources: list[str]       # dataset key 列表
    last_checked_at: str

def evaluate_capabilities(
    *,
    readiness_payload: Mapping[str, Any],
    now: datetime | None = None,
) -> dict[str, CapabilityReport]
```

**关键设计原则**：

1. **Capability 是 readiness 的纯函数**：相同 readiness payload + 相同 source_budget 静态配置 → 输出确定。
2. **不重新做计算，只翻译**。比如 trade 的 granted 直接取 `readiness.ready and readiness.account_state.ready_for_live_small`。
3. **why_not 必须用业务语言**，不允许出现 `manifest`、`stale_reasons`、`live_small_allowed` 这种工程词。Phase 1 提供从工程码到业务文案的字典。
4. **next_actions 复用 readiness.recommended_tasks**，但带上 task 的 kind（lightweight/heavyweight/maintenance）和 cooldown 剩余时间。这是给 UI 用的——"轻型任务可以现在按，重型任务等系统跑或确认你需要"。
5. **degraded_path 是 Phase 1 的关键新概念**：当 capability blocked 时，告诉用户「但是你还能 observe / review」。这正面回应了用户 brief 里的"系统应该能自动降级，而不是简单显示『未准备好』"。

**Capability 与 readiness 的对应规则**（Phase 1 初版）：

| Capability | granted（status=ok）| degraded（status=degraded, granted=False）| blocked（status=blocked, granted=False）|
|---|---|---|---|
| observe | 至少一类关键 source 状态 ≥ STALE | 所有 source DEGRADED | 所有关键 source INVALID |
| review | watchlist & screening 都 ≥ STALE 且非 INVALID | 任一关键 source DEGRADED | watchlist 或 screening INVALID |
| approve | readiness.ready 且 formal_ready 且 account.mode ∈ {shadow, live_small} | readiness.ready 且 !formal_ready | readiness.ready=False |
| trade | readiness.ready 且 account.ready_for_live_small 且所有 trade-需要的 source FRESH | readiness.ready 但 account 未对账 / delta 超阈值 | readiness.ready=False 或 quotes.batch INVALID |
| notify | Feishu delivery 未 disabled | — | delivery 配置缺失 |
| ledger_capture | account_book 可写 且 (confirmation 或 postclose) 任务今日成功 | recon 偏旧（age > 24h 且 < 36h） | account_book 缺失 或 recon 超 36h |

### 4.4 扩展 `readiness.py` 输出（无破坏改动）

在 `compute_readiness` 返回的 dict 末尾**追加**：

```python
{
    # ... existing fields unchanged ...
    "source_states": {                     # 新增,对应每个 source 的 FreshnessState
        "watchlist": "fresh",
        "screening": "stale",
        ...
    },
    "capabilities": {                      # 新增,Capability 翻译层结果
        "observe": {...CapabilityReport.as_dict()...},
        "review": {...},
        ...
    }
}
```

**向后兼容契约**：
- 现有所有字段名、类型、顺序不变。
- 现有所有 blockers / warnings / source_freshness / quality_freshness / formal_blockers / account_state 不变。
- 前端代码不读 `source_states` / `capabilities` 不会出问题（TypeScript 加 optional 字段即可，Phase 1 不动前端代码）。

### 4.5 新增 API 端点

#### `GET /api/source-budget`

```json
{
  "datasets": [
    {
      "dataset": "quotes.batch",
      "label": "批量行情",
      "role": "market_data",
      "cost_class": "cheap",
      "cadence": "intraday_high",
      "batchable": true,
      "min_refresh_interval_seconds": 60,
      "primary_provider": "eastmoney",
      "fallback_providers": ["sina"],
      "decision_scope": "live_small",
      "supports_capabilities": ["observe", "review", "approve", "trade"],
      "failure_impact": "UI 行情不可读,影响所有交易决策"
    },
    ...
  ]
}
```

#### `GET /api/capabilities?page=today`

```json
{
  "checked_at": "2026-05-22 09:35:00",
  "session": {...},  // 同 readiness
  "capabilities": {
    "observe": {
      "capability": "observe",
      "status": "ok",
      "granted": true,
      "why_not": [],
      "degraded_path": [],
      "next_actions": [],
      "blocking_sources": [],
      "last_checked_at": "2026-05-22 09:35:00"
    },
    "approve": {
      "capability": "approve",
      "status": "blocked",
      "granted": false,
      "why_not": [
        {
          "code": "watchlist_invalid",
          "label": "自选股数据",
          "message": "自选股数据交易日不是今天,放行需要先重跑自选股全流程刷新。"
        }
      ],
      "degraded_path": [
        {
          "code": "observe_still_ok",
          "label": "观察仍可用",
          "message": "你仍然可以观察行情和资金流,只是不能做正式放行。"
        }
      ],
      "next_actions": [
        {
          "task_name": "watchlist_refresh",
          "title": "自选股全流程刷新",
          "kind": "heavyweight",
          "cooldown_remaining_seconds": 0,
          "reason": "watchlist_invalid"
        }
      ],
      "blocking_sources": ["watchlist.snapshot"],
      "last_checked_at": "2026-05-22 09:35:00"
    },
    ...
  }
}
```

**关键约束**：
- `/api/capabilities` **只读**。不允许触发任何任务。
- 不引入新的状态文件。所有信息从现有 `build_today_view()` + `source_budget` 静态配置导出。

---

## 5. 测试覆盖

### 5.1 单元测试

- **`tests/test_source_budget.py`**：
  - SOURCE_BUDGETS 与 manifest.py 的 dataset key 完全对齐（白盒，避免漂移）。
  - 每个 budget 有合法的 cost_class / cadence / role。
  - `min_refresh_interval_seconds ≤ manifest.ttl_intraday`（语义化下界不超过 TTL）。
  - `budgets_for_capability("trade")` 至少包含 quotes.batch / watchlist.snapshot。

- **`tests/test_freshness_state.py`**：
  - 每个 stale_reasons 子集 → 正确的 FreshnessState 分类。
  - `state_allows` 矩阵完整覆盖（6 个 capability × 6 个 state = 36 个断言）。

- **`tests/test_capability_matrix.py`**：
  - **golden path**：fresh + live_small + 对账 ok → 6 个 capability 全 granted。
  - **stale watchlist**：approve / trade blocked，observe / review degraded、notify 仍 ok。
  - **非交易日**：observe granted（shadow_only），approve / trade blocked。
  - **research mode**：trade blocked（account.ready_for_live_small=False）。
  - **formal_not_ready**：approve degraded、trade 可降级但 why_not 提示。
  - **invalid (trade_date_mismatch)**：所有依赖该 source 的 capability 进入 INVALID。
  - **degraded_path 必填**：blocked 的 capability 必须给出至少一种降级路径。
  - **why_not 不含工程词**：assert that 'manifest' / 'stale_reasons' / 'live_small_not_allowed' 不出现在任何 message 字段里。

### 5.2 集成测试

- **`tests/test_readiness_extension.py`**：
  - `compute_readiness()` 返回的 dict 包含 `source_states` 和 `capabilities` 字段。
  - 现有 `test_readiness.py` 所有 assertion 仍然通过（向后兼容）。

- **`tests/test_capabilities_endpoint.py`**：
  - `GET /api/capabilities?page=today` 返回 6 个 capability。
  - `GET /api/source-budget` 返回 ≥ 15 个 dataset。
  - 当 `build_today_view()` 失败时端点退化为 503，不抛 500。

---

## 6. 文件清单

新增：
- `apps/control-panel/source_budget.py`
- `apps/control-panel/freshness_state.py`
- `apps/control-panel/capability_matrix.py`
- `apps/control-panel/tests/test_source_budget.py`
- `apps/control-panel/tests/test_freshness_state.py`
- `apps/control-panel/tests/test_capability_matrix.py`
- `apps/control-panel/tests/test_capabilities_endpoint.py`

修改（最小化）：
- `apps/control-panel/readiness.py`：`compute_readiness` 末尾追加 `source_states` 和 `capabilities` 字段（调用 freshness_state + capability_matrix）。
- `apps/control-panel/app.py`：新增 `GET /api/source-budget` 和 `GET /api/capabilities`。
- `apps/control-panel/tests/test_readiness.py`：补充新字段的存在性 assertion（不改任何现有 assertion）。

不动：
- `apps/control-panel/refresh_policy.py`
- `packages/prism_data/manifest.py`
- `apps/scripts/*`
- `apps/web/**`
- `apps/control-panel/dashboard_data.py`（除非 readiness 的扩展间接波及）

---

## 7. 风险与缓解

| 风险 | 缓解 |
|---|---|
| capability_matrix 误判,导致 UI 在 Phase 2 拿到错误 capability | Phase 1 不接入 UI。`/api/capabilities` 只在外部/测试可见。生产前端继续走 readiness。 |
| `source_states` / `capabilities` 字段被某个旧 schema 校验拒掉 | 现有 dashboard_data 不强校验 readiness 字段；TypeScript 侧字段是 optional。新加测试验证。 |
| source_budget 跟 manifest 漂移 | 测试白盒断言：SOURCE_BUDGETS.keys() ⊆ manifest 的 dataset 名集合。 |
| capability_matrix 引入新概念混淆 | 文档示例 + golden path 测试 + why_not 业务文案约束。 |
| 性能：compute_readiness 路径变长 | freshness_state 是纯字典查表;capability_matrix 是 O(capability × source);测试断言 <50ms。 |

---

## 8. Phase 2 / 3 留白（不属于本 spec）

- **Phase 2**：前端引入 capability 视图（Home 顶部 6 个能力标签 + Settings 能力矩阵）。改 page.tsx 错误文案到 capability 语言。
- **Phase 3**：把 source_budget 接入 evaluate_auto_refresh（soft throttle → hard throttle 渐进）。引入 USABLE 状态（接近阈值预警）。capability 进入 command_brief / risk_alert。
- **Phase 4**：考虑 capability 进入 decision_ledger，作为决策审计字段。

---

## 9. 安全边界（重申）

- 不自动下单。
- 不自动写真实账本。
- 不绕过 formal 放行。
- 不自动发飞书。
- 不让 `/api/capabilities` 触发任何任务。
- 不删除 / 修改任何现有诊断 / 恢复入口。
- 不动 unsafe_apply / portfolio_reconcile 等高风险路径。

---

## 10. 验收标准

1. 所有新增测试通过。
2. `apps/control-panel/tests/` 现有测试全部通过（无回归）。
3. `GET /api/readiness/live`（page=today）返回 payload 包含 `source_states` 和 `capabilities` 字段，但**所有现有字段名/类型/取值不变**。
4. `GET /api/capabilities?page=today` 返回结构匹配本 spec 第 4.5 节。
5. `GET /api/source-budget` 返回完整的 dataset 列表，每个 dataset 字段齐全。
6. `why_not` / `degraded_path` 消息中不出现工程词（`manifest` / `stale_reasons` / `live_small_not_allowed` / `formal_decision_allowed`）。
