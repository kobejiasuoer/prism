# Prism Decision Ledger 技术实现方案

Date: 2026-05-16
Status: implementation plan
Audience: Claude Code / Prism engineering
Source PRD: `docs/decision-ledger-product-requirements-2026-05-16.md`

本文档基于当前 Prism 本地代码阅读结果编写，目标是把产品需求转成可执行到文件级别的技术实施计划。本文不重新设计 Prism 架构，不引入新的行情供应商，不重复 PRD，而是说明当前已有能力、真实缺口和建议修改点。

## 1. 当前系统事实

1. `apps/control-panel/decision_ledger.py` 已存在 `DecisionLedgerError`、`SCHEMA_VERSION`、`EXECUTION_STATUSES`、`OUTCOME_WINDOWS`、`ACTION_ENUM`。当前 Ledger 是 JSON-on-disk，默认路径由 `default_ledger_root()` 指向 `apps/data/decision_ledger`，决策文件位于 `decisions/<trade_date>.json`。

2. `apps/control-panel/decision_ledger.py` 已存在 `make_decision_id()`。`decision_id` 由 `trade_date`、`code`、`surface`、`lane`、`action_key`、`action` 派生；推荐动作发生材料变化时会生成新 ID。

3. `apps/control-panel/decision_ledger.py` 已存在 `build_decision_record()` 和 `build_decision_record_from_today_item()`。后者把 Today action queue item 转成当前 ledger 的 DecisionRecord 结构。

4. `apps/control-panel/decision_ledger.py` 已存在 `upsert_decision()`。同一个 `decision_id` 重复写入是 no-op，已有 recommendation snapshot 不会被覆盖。

5. `apps/control-panel/decision_ledger.py` 已存在 `append_execution_event()`。执行事件通过稳定 fingerprint 去重，不改写原始 recommendation。

6. `apps/control-panel/decision_ledger.py` 已存在 `append_outcome_event()`。Outcome event 按 `window` 去重，同一 decision 的同一 `T+1` / `T+3` / `T+5` 重跑不会重复追加。

7. `apps/control-panel/decision_ledger.py` 已存在 `mark_decision_superseded()`，可以把旧 decision 标记为 `status.state = "superseded"` 并记录 `superseded_by`。

8. `apps/control-panel/decision_ledger.py` 已存在 `load_decisions()`、`load_decision()`、`list_decisions_for_stock()`。当前缺少跨日期 recent、summary 和健康查询函数。

9. `apps/control-panel/decision_ledger.py` 的 `_read_decisions_file()` 已实现 fail-closed 行为：坏 JSON、根 payload 非 list、list 内元素非 object 都会抛 `DecisionLedgerError`，不会静默返回空列表。

10. `apps/control-panel/decision_ledger.py` 已存在 `capture_today_action_queue()`。该函数从 `today_view.action_queue.items` 和 `today_view.action_queue.stale_items` 捕获决策记录，重复 capture 保持幂等。

11. `apps/control-panel/app.py` 已存在 `api_decision_ledger_capture()`，路由为 `POST /api/decision-ledger/capture`。请求体可以传 `today_view`；未传时会调用 `build_today_view()`。

12. `apps/control-panel/app.py` 已存在 `api_today_action_decision()`。当 Today action decision 为 `watch` 或 `skip` 时，会调用 `decision_ledger.append_execution_event_for_writeback()`；`done` 不会被伪造成 filled event，`pending` 也不会写 ledger。

13. `apps/control-panel/app.py` 已存在 `api_portfolio_fill()`。Portfolio 成交写入成功后，会 best-effort 调用 `decision_ledger.append_execution_event_for_writeback()` 追加 `filled` execution event。

14. `apps/control-panel/app.py` 已存在 `api_portfolio_intent_no_fill()`。Portfolio 未成交 intent 写入成功后，会 best-effort 调用 `decision_ledger.append_execution_event_for_writeback()` 追加 `no_fill` execution event。

15. `apps/control-panel/decision_ledger.py` 已存在 `PriceProvider` Protocol、`nth_trading_day_after()`、`classify_outcome()`、`evaluate_decision_outcome()`、`find_due_outcomes()`、`evaluate_due_outcomes()`。模块层 outcome evaluator 已实现。

16. `apps/scripts/evaluate_decision_ledger.py` 已存在手动 CLI 入口。该脚本明确说明当前没有生产 price provider；不用 `--no-provider` 时会输出错误并返回 exit code `2`。

17. `packages/prism_data/service.py` 已存在 `get_data_gateway()`，返回 `DataGateway` singleton。

18. `packages/prism_data/gateway.py` 已存在 `DataGateway.fetch_kline()`，默认 dataset 为 `bars.daily`。

19. `packages/prism_data/providers/sina.py` 已存在 `SinaProvider.fetch_kline()`，返回含 `trade_date`、`open`、`high`、`low`、`close`、`volume` 的日线 rows。

20. `packages/prism_data/providers/akshare.py` 已存在 `AkshareProvider.fetch_kline()`，可作为日线 fallback 能力。

21. `apps/control-panel/refresh_policy.py` 已存在 `CRON_POLICIES`，包含 `midday_confirmation`、`postclose_command_brief` 等固定任务。当前没有 Decision Ledger capture 或 outcome evaluation 任务。

22. `apps/scripts/prism_scheduled_job.py` 已存在单个定时任务执行器 `main()`，会写 `data/scheduled_runs/runs/*.json` 和 `data/scheduled_runs/latest/<task>.json`。当前不会在任务后自动 capture ledger。

23. `apps/scripts/prism_scheduler.py` 已存在固定 cron 调度 loop，按 `CRON_POLICIES` 启动 `prism_scheduled_job.py`。当前没有 ledger 专属调度策略。

24. `apps/control-panel/app.py` 已存在 `/healthz` 和 `/api/scheduler/status`。当前 response 不包含 Decision Ledger capture/evaluation 状态。

25. `apps/web/src/lib/api.ts` 已存在 Review、Stock Profile、Portfolio、Health 等 API client。当前没有 Decision Ledger read API client。

26. `apps/web/src/lib/hooks.ts` 已存在 `useReview()`、`useStockProfile()`、`usePortfolioAccount()`、`useHealth()`。当前没有 `useDecisionLedgerSummary()`、`useDecisionLedgerRecent()`、`useDecisionLedgerStock()`。

27. `apps/web/src/lib/types.ts` 已存在 `ReviewData`、`StockProfileData`、`PortfolioAccountResponse`、`HealthResponse`。当前没有 Decision Ledger response types。

28. `apps/web/src/app/portfolio/page.tsx` 已存在 “Decision writeback” 操作区。该页面目前通过 Today/Portfolio 写接口回写 execution event，但不读取 ledger 历史。

29. `apps/web/src/app/review/page.tsx` 已存在 Review 页面结构、`Panel`、`EmptyState`、`ErrorState`、`SkeletonBlock` 等组件使用模式。当前没有展示 ledger recent records。

30. `apps/web/src/app/stock/[code]/page.tsx` 已存在个股页，已有 `useStockProfile(code)` 和 Today action 上下文。当前没有 stock-level ledger timeline。

31. `apps/web/src/app/settings/page.tsx` 已存在 Health、Scheduler、Refresh status 展示。当前没有 ledger health 展示。

32. `apps/control-panel/tests/test_decision_ledger.py` 已覆盖核心 repository 行为：ID 稳定、幂等 upsert、append-only execution/outcome、corrupt JSON 抛错、supersede helper。

33. `apps/control-panel/tests/test_decision_ledger_capture.py` 已覆盖 Today action capture 和 `POST /api/decision-ledger/capture`。

34. `apps/control-panel/tests/test_decision_ledger_portfolio.py` 已覆盖 Portfolio fill/no_fill 和 Today watch/skip 写回 ledger。

35. `apps/control-panel/tests/test_decision_ledger_outcomes.py` 已覆盖 trading-day arithmetic、due outcome resolver、classifier、fake provider outcome evaluation、no-provider 行为和 data issue 行为。

## 2. 产品需求到技术缺口映射

| 产品需求 | 当前已有实现 | 当前缺口 | 建议改动文件 | 风险/注意点 |
|---|---|---|---|---|
| 自动 capture Today's action queue | 已存在 `decision_ledger.capture_today_action_queue()`；已存在 `POST /api/decision-ledger/capture` | 未接入 daily fixed workflow | `apps/scripts/prism_scheduled_job.py`、`apps/control-panel/refresh_policy.py`、可选新增 `apps/scripts/capture_decision_ledger.py` | capture 失败不能改变核心研究任务 exit code |
| 同日重复 capture 幂等 | 已存在 `upsert_decision()` 和 capture 幂等测试 | 自动任务层没有幂等测试 | 新增 `apps/control-panel/tests/test_decision_ledger_auto_capture.py` | 重跑 scheduler 不能重复写相同 `decision_id` |
| 材料动作变化 supersede | 已存在 `mark_decision_superseded()`，ID 会因 action 变化而改变 | `capture_today_action_queue()` 当前只创建第二条，不自动标记旧 record superseded | `apps/control-panel/decision_ledger.py` | 需要严格匹配同 `trade_date/code/source.surface/source.lane/source.action_key` 的旧 open decision |
| Summary/recent/stock/detail read APIs | 已存在 `load_decision()` 和 `list_decisions_for_stock()` | FastAPI 未暴露 read endpoints；缺 recent/summary 查询函数 | `apps/control-panel/decision_ledger.py`、`apps/control-panel/app.py` | corrupt ledger file 必须显式报错，不能当空数据 |
| Frontend visibility | Review/Portfolio/Stock/Settings 页面已存在 | 缺 types、API client、hooks、UI panels | `apps/web/src/lib/types.ts`、`api.ts`、`hooks.ts`、`review/page.tsx`、`settings/page.tsx` | P0 不做大 UI 重构 |
| Outcome evaluation | 模块函数和 CLI 已存在 | CLI 未接生产 price provider；未调度；状态不可见 | `apps/scripts/evaluate_decision_ledger.py`、新增 provider adapter、`apps/control-panel/app.py` | 只能复用 `prism_data`，不新增供应商 |
| Health/observability | 已存在 `/healthz`、`/api/scheduler/status`、scheduled run latest JSON | 无 last capture/eval、pending outcomes、corrupt file 状态 | `apps/control-panel/decision_ledger.py`、`apps/control-panel/app.py`、`apps/scripts/prism_scheduled_job.py` | 状态写入不能污染 decisions 文件 |
| Portfolio 展示 latest decision | Portfolio writeback 已存在 | 持仓行不展示 latest Prism decision 和 execution attachment | P1 修改 `build_portfolio_account_view()` 或前端独立 hook | P0 可先不做，避免扩大范围 |
| Stock decision timeline | 已存在 `list_decisions_for_stock()` | API/UI 未接入个股时间线 | P0 API，P1 `apps/web/src/app/stock/[code]/page.tsx` | code 要兼容 `sh600690` 和 `600690` |

## 3. 推荐实现范围

### P0：最小可交付闭环

- 自动 capture 接入固定 daily workflow，先接 `midday_confirmation` 和 `postclose_command_brief` 成功后的 best-effort post-hook。
- 新增 read APIs：summary、recent、stock timeline、decision detail。
- Review 页新增 recent ledger records 小节。
- Settings 或 Health 中展示 ledger capture/evaluation 最新状态。
- Outcome evaluator 暂可保持 no-provider 状态可见；若实现 provider adapter 风险可控，可作为 P0+。

### P1：完整可用体验

- 用 `prism_data.service.get_data_gateway().fetch_kline()` 实现生产 `PriceProvider` adapter。
- 让 `apps/scripts/evaluate_decision_ledger.py` 默认可运行 provider 模式，同时保留 `--no-provider`。
- Stock Profile 增加 decision timeline。
- Portfolio 持仓行显示 latest Prism decision 和 execution attached 状态。
- 自动 supersede：同源 action material change 后标记旧 decision 为 superseded。
- UI 展示 data quality blockers/warnings 和 superseded relationship。

### P2：分析增强

- 按 lane、action、stock、outcome 聚合。
- Review 中增加 decision quality trend。
- JSON/CSV export。
- 更完整的决策质量复盘页。
- 更复杂的归因、`early` / `late` 标签和策略校准。

## 4. P0 详细实现设计

### 4.1 后端新增 API

在 `apps/control-panel/app.py` 的 `# decision ledger` 区块下新增：

```text
GET /api/decision-ledger/summary?window=7d
GET /api/decision-ledger/recent?limit=20
GET /api/decision-ledger/stock/{code}
GET /api/decision-ledger/decision/{decision_id}
```

错误策略：

- `decision_id` 格式不合法或找不到：`404`。
- `window`、`limit`、`code` 参数不合法：`400`。
- ledger 文件 corrupt：`500`，`detail` 包含 `DecisionLedgerError` message。

### 4.2 decision_ledger.py 查询函数

在 `apps/control-panel/decision_ledger.py` 新增查询和投影函数，不改现有存储结构：

```python
def iter_decision_records(
    start_date: str | None = None,
    end_date: str | None = None,
) -> Iterator[dict[str, Any]]:
    ...

def list_recent_decisions(limit: int = 20) -> list[dict[str, Any]]:
    ...

def summarize_decisions(
    window: str = "7d",
    now: datetime | None = None,
) -> dict[str, Any]:
    ...

def compact_decision_record(record: Mapping[str, Any]) -> dict[str, Any]:
    ...

def decision_execution_status(record: Mapping[str, Any]) -> dict[str, Any]:
    ...

def decision_outcome_status(record: Mapping[str, Any]) -> dict[str, Any]:
    ...
```

P0 不新增 index 文件，直接扫描 `default_ledger_root() / "decisions" / "*.json"`。当前数据量小，直接扫描比引入索引更稳妥。

### 4.3 scheduler / scheduled_job / refresh_policy 自动 capture

推荐最小接入方式：

1. 在 `apps/control-panel/refresh_policy.py` 增加常量：

```python
DECISION_LEDGER_CAPTURE_AFTER_TASKS = (
    "midday_confirmation",
    "postclose_command_brief",
)
```

2. 在 `apps/scripts/prism_scheduled_job.py` 的 `main()` 中，在原任务命令完成后：

- 如果 `exit_code == 0` 且 `args.task_name` 属于 `DECISION_LEDGER_CAPTURE_AFTER_TASKS`：
  - import `build_today_view` 和 `decision_ledger`。
  - 调用 `today_view = build_today_view()`。
  - 调用 `summary = decision_ledger.capture_today_action_queue(today_view)`。
  - 把结果写入当前 scheduled run payload：

```json
{
  "decision_ledger_capture": {
    "status": "success",
    "trade_date": "2026-05-15",
    "captured": 3,
    "already_present": 2,
    "skipped": 0,
    "decision_ids": []
  }
}
```

- 如果 capture 抛错：
  - 写入 `decision_ledger_capture.status = "failed"` 和 `error`。
  - 不改变原任务 `exit_code`。

3. 同时把 latest capture 状态写入 ledger status 文件，例如：

```text
apps/data/decision_ledger/status/capture_latest.json
```

建议在 `decision_ledger.py` 新增：

```python
def status_path(kind: str) -> Path:
    ...

def write_status(kind: str, payload: Mapping[str, Any]) -> None:
    ...

def load_status(kind: str) -> dict[str, Any]:
    ...

def build_ledger_health() -> dict[str, Any]:
    ...
```

状态文件不是 audit record，不要写进 `decisions/*.json`。

### 4.4 前端 P0 展示范围

P0 只做两个轻量入口：

1. `apps/web/src/app/review/page.tsx`
   - 新增 “Decision Ledger 最近记录” panel。
   - 调用 `useDecisionLedgerRecent({ limit: 10 })`。
   - 展示股票、日期、lane、action、execution 状态、outcome 状态、data quality 状态。

2. `apps/web/src/app/settings/page.tsx`
   - 在现有 health / scheduler 区域展示 ledger health。
   - 展示 last capture、last evaluation、pending outcomes、recent error、corrupt file 摘要。

P0 不先改 Portfolio/Stock 大布局。Stock timeline 放 P1，但 P0 API 先提供 `/api/decision-ledger/stock/{code}`。

### 4.5 TypeScript types / API / hooks

在 `apps/web/src/lib/types.ts` 新增：

```ts
export interface DecisionLedgerCompactRecord { ... }
export interface DecisionLedgerRecord { ... }
export interface DecisionLedgerSummaryResponse { ... }
export interface DecisionLedgerRecentResponse { ... }
export interface DecisionLedgerStockResponse { ... }
export interface DecisionLedgerDecisionResponse { ... }
export interface DecisionLedgerHealth { ... }
```

在 `apps/web/src/lib/api.ts` 的 `api` object 新增：

```ts
getDecisionLedgerSummary(params?: { window?: string })
getDecisionLedgerRecent(params?: { limit?: number })
getDecisionLedgerStock(code: string)
getDecisionLedgerDecision(decisionId: string)
```

在 `apps/web/src/lib/hooks.ts` 新增 query keys 和 hooks：

```ts
decisionLedgerSummary: (window: string) => ...
decisionLedgerRecent: (limit: number) => ...
decisionLedgerStock: (code: string) => ...

useDecisionLedgerSummary(...)
useDecisionLedgerRecent(...)
useDecisionLedgerStock(...)
```

写回 mutation 成功后应 invalidate ledger recent/stock：

- `useUpdateTodayActionDecision()` 成功后 invalidate ledger recent。
- `useRecordPortfolioFill()` 和 `useRecordPortfolioNoFill()` 成功后 invalidate ledger recent。
- 具体函数位于 `apps/web/src/lib/hooks.ts` 下半段，实施时需要代码确认函数名和位置。

### 4.6 状态和错误展示

Review recent panel：

- loading：使用现有 `SkeletonBlock`。
- error：使用现有 `ErrorState`，文案为 “Decision Ledger 暂不可用”。
- empty：使用现有 `EmptyState`，文案为 “暂无捕获的决策记录”。
- data：展示 compact row。

Settings health：

- last capture success：显示 captured / already_present / skipped。
- last capture failed：显示 error。
- last evaluation missing provider：显示 “未接生产价格 provider”。
- corrupt files：显示风险 badge 和文件路径摘要。

### 4.7 幂等和 append-only 保持方式

P0 必须保持：

- 不改 `upsert_decision()` 的 first-write-wins 语义。
- 不在自动 capture 中重写已有 record。
- 不把 `done` 合成为 `filled`，保持 `api_today_action_decision()` 现有行为。
- outcome 继续依赖 `append_outcome_event()` 的 per-window 去重。
- capture post-hook 只写 status metadata，不直接改 recommendation。

P1 supersede 设计：

- 在 `capture_today_action_queue()` 中，若新 record 与旧 open record 同 `trade_date`、`stock.code`、`source.surface`、`source.lane`、`source.action_key`，但 `decision_id` 不同，则 upsert 新 record 后调用 `mark_decision_superseded(old_id, by=new_id)`。

## 5. Outcome evaluator 接入设计

### 5.1 已确认可复用的现有价格/行情访问层

已存在：

- `packages/prism_data/service.py` 的 `get_data_gateway()`。
- `packages/prism_data/gateway.py` 的 `DataGateway.fetch_kline()`。
- `packages/prism_data/providers/sina.py` 的 `SinaProvider.fetch_kline()`。
- `packages/prism_data/providers/akshare.py` 的 `AkshareProvider.fetch_kline()`。

因此 outcome evaluator 不应新增供应商，也不应直接在 evaluator 里发 HTTP 请求。应通过 `prism_data` 访问日线。

### 5.2 最小 provider adapter

建议新增：

```text
apps/scripts/decision_ledger_price_provider.py
```

实现：

```python
class PrismDataPriceProvider:
    def __init__(self, gateway: Any | None = None) -> None:
        self.gateway = gateway or get_data_gateway()

    def fetch_window(
        self,
        code: str,
        *,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        ...
```

内部调用：

```python
self.gateway.fetch_kline(
    code,
    trade_date=end_date,
    key=f"decision-ledger-{code}-{start_date}-{end_date}",
    count=<enough>,
    allow_fallback=True,
)
```

然后过滤：

```python
start_date <= row["trade_date"] <= end_date
```

如果 gateway 抛错或 provider result 无 rows：

- 返回空 list 或抛异常均可。
- 当前 `decision_ledger.evaluate_decision_outcome()` 已把 provider error / missing prices 转成 `data_issue` event。

### 5.3 evaluate_decision_ledger.py 改动

修改 `apps/scripts/evaluate_decision_ledger.py`：

- 保留 `--no-provider`。
- 新增 `--provider prism_data`，默认值为 `prism_data`。
- 默认构造 `PrismDataPriceProvider()`。
- 调用 `decision_ledger.evaluate_due_outcomes()`。
- 把 summary 写入 `apps/data/decision_ledger/status/outcome_latest.json`。
- provider 初始化失败时返回非 0，并写 status；不能 append 半成品事件。

### 5.4 benchmark 边界

不确定，需要代码确认：

- 当前 `benchmark_code="000300"` 是否能通过 `DataGateway.fetch_kline()` 正确取得指数日线。
- `packages/prism_data/manifest.py` 有 `benchmark.index_daily` dataset 定义，但当前 `DataGateway` 未见专门的 `fetch_index_daily()` 方法。

因此最小实现建议：

- P0/P1 adapter 可以先支持 stock code。
- benchmark 获取失败时不阻断 stock outcome，允许 `benchmark_return_pct = null`，按绝对收益分类。
- 暂不为 benchmark 新增供应商或新 gateway 方法，除非后续代码确认已有明确 provider path。

## 6. 数据结构与 API Response 草案

### 6.1 Recent response

```json
{
  "generated_at": "2026-05-16 15:20:00",
  "limit": 20,
  "items": [
    {
      "decision_id": "2026-05-15:sh600690:today_action_queue:watchlist:abcd1234",
      "trade_date": "2026-05-15",
      "created_at": "2026-05-15 13:46:00",
      "stock": {
        "code": "sh600690",
        "name": "海尔智家"
      },
      "source": {
        "lane": "watchlist",
        "surface": "today_action_queue",
        "action_key": "watchlist:600690",
        "source_label": "自选股链路",
        "artifact_paths": []
      },
      "recommendation": {
        "action": "hold",
        "action_label": "继续持有",
        "main_conclusion": "趋势线尚未破，保持仓位"
      },
      "status": {
        "state": "open",
        "superseded_by": null
      },
      "execution_status": {
        "latest": "filled",
        "counts": {
          "filled": 1,
          "no_fill": 0,
          "watch": 0,
          "skip": 0,
          "manual_note": 0
        }
      },
      "outcome_status": {
        "T+1": "pending",
        "T+3": "pending",
        "T+5": "pending"
      },
      "data_quality": {
        "readiness_mode": "live_ready",
        "readiness_ready": true,
        "blockers_count": 0,
        "warnings_count": 0
      }
    }
  ],
  "errors": []
}
```

### 6.2 Summary response

```json
{
  "generated_at": "2026-05-16 15:20:00",
  "window": "7d",
  "start_date": "2026-05-10",
  "end_date": "2026-05-16",
  "counts": {
    "total_decisions": 12,
    "open": 10,
    "superseded": 2,
    "evaluated": 4
  },
  "execution_counts": {
    "filled": 2,
    "no_fill": 1,
    "watch": 3,
    "skip": 1,
    "manual_note": 0,
    "none": 5
  },
  "outcome_counts": {
    "T+1": {
      "validated": 1,
      "invalidated": 1,
      "data_issue": 1,
      "pending": 9
    },
    "T+3": {
      "pending": 12
    },
    "T+5": {
      "pending": 12
    }
  },
  "data_quality": {
    "ready": 8,
    "blocked_or_shadow": 4,
    "with_blockers": 2,
    "with_warnings": 3
  },
  "health": {
    "last_capture": {},
    "last_outcome_evaluation": {},
    "corrupt_files": []
  }
}
```

### 6.3 Stock response

```json
{
  "generated_at": "2026-05-16 15:20:00",
  "code": "sh600690",
  "items": [],
  "errors": []
}
```

### 6.4 Decision detail response

```json
{
  "generated_at": "2026-05-16 15:20:00",
  "decision": {
    "schema_version": 1,
    "decision_id": "...",
    "trade_date": "2026-05-15",
    "created_at": "2026-05-15 13:46:00",
    "source": {},
    "stock": {},
    "recommendation": {},
    "evidence_snapshot": {},
    "parameter_snapshot": {},
    "status": {},
    "execution_events": [],
    "outcome_events": []
  }
}
```

## 7. 测试计划

### 7.1 API read endpoints

新增：

```text
apps/control-panel/tests/test_decision_ledger_api.py
```

覆盖：

- `GET /api/decision-ledger/summary`
- `GET /api/decision-ledger/recent`
- `GET /api/decision-ledger/stock/{code}`
- `GET /api/decision-ledger/decision/{decision_id}`
- detail 404
- bad `window` / `limit` / `code` 400
- corrupt ledger file 500

### 7.2 automatic capture

新增：

```text
apps/control-panel/tests/test_decision_ledger_auto_capture.py
```

覆盖：

- `midday_confirmation` 成功后调用 capture。
- `postclose_command_brief` 成功后调用 capture。
- capture 抛错时 scheduled job 主任务仍成功，但 payload 中 `decision_ledger_capture.status == "failed"`。
- 重跑同日 job 不产生重复 decision。

### 7.3 idempotency

扩展现有：

```text
apps/control-panel/tests/test_decision_ledger.py
apps/control-panel/tests/test_decision_ledger_capture.py
apps/control-panel/tests/test_decision_ledger_outcomes.py
```

覆盖：

- recent/summary 查询不改变文件。
- 自动 capture 重跑 idempotent。
- outcome provider 重跑仍按 window 去重。

### 7.4 corrupt ledger file behavior

扩展：

```text
apps/control-panel/tests/test_decision_ledger.py
apps/control-panel/tests/test_decision_ledger_api.py
```

覆盖：

- `iter_decision_records()` 遇 corrupt file 抛 `DecisionLedgerError`。
- read API 遇 corrupt file 返回明确错误，不返回假空列表。
- health 中能暴露 corrupt file 摘要。

### 7.5 frontend basic rendering / typecheck

当前 `apps/web/package.json` 只有：

```json
{
  "typecheck": "tsc --noEmit"
}
```

P0 验收：

```bash
cd apps/web
npm run typecheck
```

不建议 P0 为此单独引入新 test runner。若后续已有前端测试框架，再补 Review ledger panel rendering test。

### 7.6 outcome provider missing / data issue case

扩展：

```text
apps/control-panel/tests/test_decision_ledger_outcomes.py
```

或新增：

```text
apps/control-panel/tests/test_decision_ledger_price_provider.py
```

覆盖：

- fake gateway 返回日线 rows 时 evaluator append outcome。
- gateway/provider missing 时写 status，summary 清楚说明 provider missing。
- provider 返回空 rows 时 append `data_issue` outcome。
- benchmark 缺失不阻断 stock outcome。

## 8. 实施顺序

### Task 1：补齐 backend 查询函数

- 目标：提供 summary/recent/stock/detail 所需的数据读取和 compact 投影。
- 涉及文件：`apps/control-panel/decision_ledger.py`。
- 验收方式：新增单元测试通过；summary/recent/stock/detail 投影字段稳定。
- 不要改：现有 record schema、`upsert_decision()` first-write-wins 语义。

### Task 2：新增 read APIs

- 目标：实现四个 `GET /api/decision-ledger/*` endpoint。
- 涉及文件：`apps/control-panel/app.py`、`apps/control-panel/tests/test_decision_ledger_api.py`。
- 验收方式：四个 GET endpoint 返回预期 JSON；坏 ID、坏 code、corrupt file 行为明确。
- 不要改：`POST /api/decision-ledger/capture` 的请求/响应兼容性。

### Task 3：新增 ledger status 读写

- 目标：记录 last capture、last outcome evaluation、corrupt file health。
- 涉及文件：`apps/control-panel/decision_ledger.py`、`apps/control-panel/app.py`。
- 验收方式：`/healthz` 或 refresh status 能看到 `decision_ledger` health。
- 不要改：不要把 status 写入 `decisions/*.json`。

### Task 4：固定 workflow 后自动 capture

- 目标：在 `midday_confirmation` 和 `postclose_command_brief` 成功后 best-effort capture。
- 涉及文件：`apps/scripts/prism_scheduled_job.py`、`apps/control-panel/refresh_policy.py`、`apps/control-panel/tests/test_decision_ledger_auto_capture.py`。
- 验收方式：自动 capture 成功/失败状态写入 scheduled run payload；失败不改变主任务 exit code。
- 不要改：不要让 capture 阻断研究 workflow。

### Task 5：前端 types/API/hooks

- 目标：让前端可读 ledger summary/recent/stock/detail。
- 涉及文件：`apps/web/src/lib/types.ts`、`apps/web/src/lib/api.ts`、`apps/web/src/lib/hooks.ts`。
- 验收方式：`cd apps/web && npm run typecheck` 通过。
- 不要改：不要重命名现有 Review/Portfolio/Stock types。

### Task 6：Review 显示 recent decisions

- 目标：在 Review 页面新增轻量 Decision Ledger recent panel。
- 涉及文件：`apps/web/src/app/review/page.tsx`。
- 验收方式：loading/error/empty/data 四态可见；展示股票、日期、lane、action、execution、outcome。
- 不要改：不要重构 Review 页面现有结构。

### Task 7：Settings 显示 ledger health

- 目标：让 operator 不看 JSON 文件也知道 capture/eval 是否工作。
- 涉及文件：`apps/web/src/app/settings/page.tsx`、`apps/web/src/lib/types.ts`。
- 验收方式：能看到 last capture、last evaluation、pending/corrupt/error 摘要。
- 不要改：不要重构 scheduler panel。

### Task 8：Outcome provider adapter 最小接入

- 目标：复用 `prism_data` 日线能力，让 outcome evaluator 可接生产 provider。
- 涉及文件：新增 `apps/scripts/decision_ledger_price_provider.py`、修改 `apps/scripts/evaluate_decision_ledger.py`、新增/扩展 outcome tests。
- 验收方式：fake gateway 返回 rows 时 outcome event append；gateway/provider 缺失时 status 清晰。
- 不要改：不要新增行情供应商，不要直接 HTTP 请求第三方。

### Task 9：最终验证

- 目标：确认后端 ledger 测试和前端 typecheck 通过。
- 涉及文件：所有上述文件。
- 验收方式：

```bash
pytest apps/control-panel/tests/test_decision_ledger*.py
cd apps/web && npm run typecheck
```

- 不要改：不要提交生成的 `apps/data/decision_ledger/*` runtime 数据。

## 9. 风险与非目标

### 风险

1. `benchmark_code="000300"` 通过现有 `fetch_kline()` 是否能稳定取得指数日线不确定，需要代码确认。

2. Ledger 文件 corrupt 时 read API 不能假装空数据，否则会掩盖审计问题。

3. 自动 capture 发生在 daily workflow 之后，若调用 `build_today_view()` 重新构建，捕获的是 post-task 当前视图，不一定是任务内部 exact snapshot。若未来要求严格一致，需要任务把当时的 `today_view` artifact 直接传给 capture。

4. `capture_today_action_queue()` 当前不会自动 supersede。P0 如果不实现 supersede，同源 action change 会出现两条 open decision。

5. `dashboard_data.py` 很大，P0 应避免在其中做大范围改造。

6. Outcome provider 使用 `prism_data` 时可能遇到 provider 返回字段、code 格式或 benchmark 支持差异，必须通过 fake gateway 和真实小样本 smoke 验证。

### 非目标

- 不做自动交易。
- 不接券商 API。
- 不做数据库迁移。
- 不做大型 Review / Portfolio / Stock UI 重构。
- 不做多 Agent 辩论展示。
- 不做复杂收益归因、真实撮合回测、滑点、涨跌停、部分成交建模。
- 不新增行情供应商。
- 不把 generated ledger JSON 提交进代码库。

