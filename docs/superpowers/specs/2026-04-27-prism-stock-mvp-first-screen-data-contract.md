# Prism 股票 MVP 首屏数据契约冻结稿

日期：2026-04-27
状态：冻结稿
范围：只冻结新版前端最先落地的 1 条股票用户路径，不扩展长期统一接口
测试契约：`apps/control-panel/tests/fixtures/stock_mvp_profile_contract.json`

## 1. 冻结路径

本版 MVP 先冻结这一条用户路径：

1. 用户进入 `/` 指挥中心。
2. 首屏读取今日动作队列。
3. 用户点击队列里的股票项。
4. 前端进入 `/stock/{code}`。
5. 单股首屏优先展示一条主结论、仓位、风险边界和下一步动作。

当前代码已新增统一单股接口，兼容旧 detail 接口：

- `/` 调 `GET /api/today`
- `/stock/{code}` 优先调 `GET /api/stock/{code}`
- `GET /api/stock/{code}` 后端聚合 `GET /api/watchlist/{code}` 与 `GET /api/opportunities/{code}` 的 detail builder 输出
- `/stock/{code}` 另外调 `GET /api/ask?q={code}` 作为 fallback / enrich
- `/stock/{code}` 调 `GET /api/watchlist/manage` 判断加入、归档、恢复按钮状态

冻结原则：

- 首屏主结论优先级固定为 `watchlist > opportunity > ask.case`。
- `Ask` 只做 fallback / enrich，不覆盖持仓或观察池详情的首屏主结论。
- `/api/stock/{code}` 必须兼容本文的 `StockProfileData` shape，并继续保留 `watchlist` / `opportunity` 原始 detail 字段。
- `apps/control-panel/tests/fixtures/stock_mvp_profile_contract.json` 是给开发和测试共用的最小契约快照；后端测试会用真实 `build_stock_profile_view()` 输出对照该 fixture。

## 2. 页面 -> 接口 -> 字段

### 2.1 页面：`/` 指挥中心首屏

#### 接口：`GET /api/today`

请求参数：无。

前端缓存节奏：

- `staleTime`: 30 秒
- `refetchInterval`: 60 秒
- `refetchOnWindowFocus`: true

#### 字段：首屏必须保留

```ts
type TodayData = {
  generated_at: string;
  trade_date: string;
  brief_is_live: boolean;
  hero: {
    title: string;
    summary: string;
    gate_label?: string;
    position_cap?: string;
    main_theme?: string;
    context_note?: string;
  };
  summary_cards: Array<{
    label: string;
    value: string | number;
    detail?: string;
    tone?: string;
  }>;
  action_queue: {
    title: string;
    subtitle?: string;
    note?: string;
    items: TodayActionItem[];
    hidden_count?: number;
    counts: {
      total: number;
      pending: number;
      done: number;
      watch: number;
      skip: number;
      last_updated?: string;
    };
  };
  source_cards: Array<{
    label: string;
    value: string;
    detail?: string;
    available?: boolean;
    stale?: boolean;
  }>;
  counts: {
    watchlist_priority: number;
    watchlist_total: number;
    candidate_total: number;
    confirmed: number;
    downgraded: number;
    fresh_candidates: number;
  };
};

type TodayActionItem = {
  key: string;
  title: string;
  source: string;
  status: string;
  tone: string;
  detail: string;
  foot?: string;
  metrics?: string[];
  url?: string;
  group_key?: string;
  group_title?: string;
  group_index?: number;
  freshness?: {
    value?: string;
    label?: string;
  };
  confidence?: {
    status?: string;
    label?: string;
    tone?: string;
    note?: string;
  };
  decision: {
    value: "pending" | "done" | "watch" | "skip";
    label: string;
    tone: string;
    updated_at?: string;
    updated_at_raw?: string;
  };
};
```

股票项约束：

- 股票项的 `url` 必须是 `/stock/{code}`。
- `code` 必须是 6 位数字。
- `key` 建议保留来源前缀：`watchlist:{code}`、`screening:{code}`、`confirmation:{code}`。
- 系统项可以没有股票代码，例如 `system:no-new-positions`。

#### 字段：首屏可降级

以下字段后端实际可能返回，但首屏不应硬依赖：

- `command_hero`
- `radar_cards`
- `risk_rows`
- `artifacts`
- `change_view`
- `confidence_switch`
- `watchlist_cards`
- `opportunity_cards`
- `midday_cards`
- `quality_cards`

#### 空态和失败态

- `GET /api/today` 失败：显示“后端数据暂不可用”，保留骨架屏和重试按钮。
- `action_queue.items` 为空：显示“当前没有必须处理的动作”。
- 没有股票项：首屏仍可跳 `/portfolio` 或 `/discovery`，不得生成 `/stock/undefined`。
- `summary_cards` 为空：允许回退到 `radar_cards`；两者都空时展示 metric skeleton 或 `-`。

### 2.2 页面：`/` 今日动作状态更新

#### 接口：`POST /api/today/actions/decision`

请求体：

```ts
type UpdateTodayActionDecisionRequest = {
  trade_date: string;
  key: string;
  decision: "pending" | "done" | "watch" | "skip";
};
```

#### 字段：必须保留

```ts
type UpdateTodayActionDecisionResponse = {
  ok: true;
  trade_date: string;
  key: string;
  decision: TodayActionItem["decision"];
  counts: TodayData["action_queue"]["counts"];
};
```

失败兜底：

- 只提示“动作状态更新失败”。
- 不阻塞今日队列和股票入口继续使用。

### 2.3 页面：`/stock/{code}` 单股首屏

#### 接口：`GET /api/stock/{code}`

后端聚合来源：

- `GET /api/watchlist/{code}`
- `GET /api/opportunities/{code}`

请求参数：

- `code`: path 参数，MVP 只承诺 6 位 A 股代码。

聚合返回：

```ts
type StockProfileData = {
  generated_at?: string;
  code: string;
  trade_date?: string;
  primary_source?: "watchlist" | "opportunity" | null;
  primary_source_label?: string;
  primary_detail?: StockDetailData;
  available_sources?: Array<"watchlist" | "opportunity">;
  watchlist?: StockDetailData;
  opportunity?: StockDetailData;
  errors?: Partial<Record<"watchlist" | "opportunity", string>>;
};
```

重要约束：

- 内部两个 detail builder 允许其中一个失败。
- 只要其中一个 detail 成功，单股首屏就不能显示全页失败。
- `primary_source` 必须按 `watchlist > opportunity` 取值。
- `primary_detail` 必须等于 `watchlist` 或 `opportunity` 中的主 detail。
- `available_sources` 只列出当前成功命中的来源。
- `errors` 只给前端判断来源命中情况；页面只展示“自选股未命中 / 观察池未命中”这类归一化标签，不直出后端 raw error。

#### 字段：`StockDetailData` 首屏必须保留

```ts
type StockDetailData = {
  generated_at: string;
  trade_date?: string;
  code: string;
  name?: string;
  tone?: string;
  hero?: {
    title?: string;
    summary?: string;
    status_label?: string;
    setup_label?: string;
    position?: string;
  };
  canonical_decision?: CanonicalDecision;
  decision_cards?: Array<{
    label: string;
    value: string | number;
    detail?: string;
    tone?: string;
  }>;
  execution_loop?: Array<{
    label?: string;
    value?: string | number;
    detail?: string;
    tier?: string;
    tier_key?: string;
  }>;
  source_cards?: Array<{
    label: string;
    value: string;
    detail?: string;
  }>;
};

type CanonicalDecision = {
  stock_id: string;
  stock_name: string;
  trade_date: string;
  source_scope: "holdings" | "opportunity" | "live_fallback" | string;
  main_conclusion: string;
  action_tier: string;
  position_guidance: string;
  risk_boundary: string;
  why_now: string;
  continue_condition: string;
  stop_condition: string;
  next_step: string;
  trigger_condition: string;
  avoid_action: string;
  evidence_entry: string;
  confidence_note: string;
  updated_at: string;
};
```

首屏展示顺序：

1. `hero.title`
2. `hero.summary`
3. `hero.status_label`
4. `decision_cards[0..3]`
5. `execution_loop`
6. `canonical_decision`

`decision_cards` 语义必须稳定：

- `当前结论`
- `仓位建议`
- `风险边界`
- `下一步动作`

`execution_loop` 语义必须稳定：

- `现在做什么`
- `为什么先做这一步`
- `触发条件`
- `先不要做什么`
- `去哪看证据`

#### 字段：后端实际还能返回，首屏可选

持仓详情实际可能返回：

- `topline`
- `meta_cards`
- `level_cards`
- `related_status`
- `insight_groups`
- `triggers`
- `artifacts`
- `links`

候选详情实际可能返回：

- `topline`
- `metric_cards`
- `level_cards`
- `capital_cards`
- `plan_rows`
- `plan_levels`
- `insight_groups`
- `artifacts`
- `links`

首屏不得因为这些字段缺失而失败。

#### 当前只能 mock 或降级

- 历史午盘产物可能没有 `entry_plan` / `execution_quality`，canonical 层会按 `high20`、`ma5`、`ma10`、资金和分数回填最小动作计划；如果这些原始位也缺失，前端再降级为“等待更多确认”。
- 自选股技术分依赖链路仍可能缺失，`规则分` 允许显示 `-`。
- 资金时效尚未完整穿透到统一字段，前端只可显示 `flow_as_of`、`flow_unconfirmed` 或“历史参考”。
- `Ask` 实时增强可能和快照详情的关键位不同；首屏主结论仍以 `StockDetailData.canonical_decision` 为准。

#### 空态和失败态

- `watchlist` 404、`opportunity` 成功：用 `opportunity` 渲染。
- `opportunity` 404、`watchlist` 成功：用 `watchlist` 渲染。
- 两者都 404、`ask.case` 成功：显示 Ask fallback 主结论。
- 三者都没有：显示“当前股票不在持仓或观察池详情中”。
- 单个 detail 失败不得阻断另一路 detail。

### 2.4 页面：`/stock/{code}` Ask fallback / 追问

#### 接口：`GET /api/ask?q={code}`

请求参数：

- `q`: 股票代码或查询词；MVP 单股页只传 6 位代码。

#### 字段：fallback 必须保留

```ts
type AskResponse = {
  generated_at?: string;
  query?: string;
  case?: {
    code?: string;
    name?: string;
    trade_date?: string;
    tone?: string;
    hero?: {
      title?: string;
      summary?: string;
      status_label?: string;
      decision_label?: string;
      position?: string;
      confidence_label?: string;
      confidence_note?: string;
    };
    canonical_decision?: CanonicalDecision;
    decision_cards?: MetricCard[];
    metric_cards?: MetricCard[];
    level_cards?: MetricCard[];
    execution_loop?: BasicCard[];
    source_cards?: SourceCard[];
    evidence_layer?: {
      followup?: AskFollowupShell | null;
      [key: string]: unknown;
    };
  };
  followup?: AskFollowupShell | null;
  message?: string;
};
```

约束：

- Ask 是 fallback / enrich。
- 如果 `watchlist` 或 `opportunity` 有 detail，Ask 不覆盖首屏主结论。
- 如果只有 Ask 有结果，首屏可以使用 Ask 的 `case.hero`、`case.decision_cards` 和 `case.canonical_decision`。

#### 接口：`POST /api/ask/followup`

请求体：

```ts
type AskFollowupRequest = {
  query: string;
  question: string;
  history?: unknown[];
};
```

返回字段：

```ts
type AskFollowupResponse = {
  query: string;
  question: string;
  code?: string;
  name?: string;
  hero_title?: string;
  history_used?: number;
  answer: {
    title?: string;
    summary?: string;
    bullets?: string[];
    references?: string[];
    tone?: string;
    followups?: string[];
    engine_label?: string;
  };
};
```

失败兜底：

- 只在追问面板提示错误。
- 不影响“决策”首屏。

### 2.5 页面：`/stock/{code}` 头部持仓操作

#### 接口：`GET /api/watchlist/manage`

请求参数：无。

#### 字段：必须保留

```ts
type WatchlistManagerResponse = {
  manager: {
    active_items?: Array<{
      code: string;
      name: string;
      state_label?: string;
      state_detail?: string;
      tone?: string;
      updated_at?: string;
    }>;
    archived_items?: Array<{
      code: string;
      name: string;
      state_label?: string;
      state_detail?: string;
      tone?: string;
      updated_at?: string;
    }>;
  };
};
```

按钮判断：

- 在 `active_items`：显示“归档”。
- 在 `archived_items`：显示“恢复”。
- 都不在：显示“加入”。

失败兜底：

- manager 拉取失败时，按钮应显示“名单状态待同步”或禁用。
- 不要误判成“加入”。

#### 操作接口

- `POST /api/watchlist/manage/add`
- `POST /api/watchlist/manage/archive`
- `POST /api/watchlist/manage/restore`

请求体：

```ts
type AddWatchlistStockRequest = {
  code: string;
  name?: string;
  trigger_refresh?: boolean;
};

type ArchiveOrRestoreWatchlistStockRequest = {
  code: string;
  trigger_refresh?: boolean;
};
```

返回字段：

```ts
type WatchlistManageResponse = {
  ok: boolean;
  action: "add" | "archive" | "restore";
  message: string;
  refresh?: {
    started?: boolean;
    run_id?: string;
    task_name?: string;
    title?: string;
    log_path?: string;
  };
  manager: WatchlistManagerResponse["manager"];
};
```

失败兜底：

- 显示 `message` 或错误信息。
- 操作失败后保留当前 detail，不清空页面。

## 3. 最小开发契约

开发本轮只按下面 8 条开工：

1. `/` 只依赖 `GET /api/today` 渲染首屏和股票入口。
2. 股票入口只认 `action_queue.items[].url=/stock/{code}`。
3. `/stock/{code}` 拉 `/api/stock/{code}`、`/api/ask?q={code}`、`/api/watchlist/manage`。
4. 单股首屏主结论优先级固定为 `watchlist > opportunity > ask.case`。
5. `canonical_decision`、`decision_cards`、`execution_loop` 是单股首屏冻结核心字段。
6. `topline`、`metric_cards`、`meta_cards`、`level_cards`、`capital_cards`、`plan_rows`、`source_cards`、`artifacts` 都是增强字段，允许缺省。
7. 任何缺失字段必须显示业务降级文案，不显示 `undefined`、`null` 或空对象。
8. 任一子接口失败时只降级对应模块，不把整个股票页打成失败态。

## 4. 当前缺口

本冻结稿不掩盖现状缺口，后续实现需排期处理：

- `build_stock_profile_view()` 已落地，但仍复用 watchlist / opportunity 两套 detail builder。
- Ask 仍是独立 fallback / enrich 链路，尚未并入后端 stock profile。
- 午盘新增观察已通过 `screener.parameters.build_intraday_observation_contract()` 补最小 `entry_plan`、`levels`、`execution_quality`；后续缺口是把这套午盘轻量规则继续和早盘 `ai_screening` 的 setup 规则合并到同一份参数配置。
- 自选股资金时效字段没有完整穿透到统一 `canonical_decision`。
- Ask 实时分析和快照详情可能出现关键位差异；首屏主结论必须以 detail 为准。
