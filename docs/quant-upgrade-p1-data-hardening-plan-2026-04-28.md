# Prism 量化升级 P1 数据硬化方案

Date: 2026-04-28
Scope: P1 data hardening plan only
Source:
- `docs/quant-upgrade-p0-review-revision-2026-04-28.md`
- `docs/quant-upgrade-p0-execution-flow-2026-04-28.md`
- `data/quant/reports/factor_evaluation_latest.md`
- `data/quant/reports/portfolio_backtest_latest.md`
- `data/quant/reports/quant_health_latest.md`
- `data/quant/reports/quant_health_latest.json`
Status: planning document; no code changes implied

## 0. 目标与边界

P1 数据硬化的目标不是开发新策略，也不是把 Sprint 2 的 report-only 结果产品化。

P1 的目标是补齐 Sprint 2 暴露的数据硬伤，使后续重新运行 Sprint 2 时可以从 `research_only_simulation` 升级为更可信的 formal research evaluation。

本方案只覆盖数据硬化：

- benchmark 冻结。
- 复权和 adjusted price 策略。
- 停牌、涨跌停、failed order、partial fill 数据补齐。
- 2026 forward labels formal 化。
- AI tier A/B 样本扩充。
- 重新运行 Sprint 2 的准入条件。

P1 仍然禁止：

- 不改生产排序。
- 不替换 A/B/C。
- 不做页面。
- 不做 Prism Edge 产品化。
- 不做 Expected 5D 前端展示。
- 不做题材状态机。
- 不做 ML。
- 不把 research-only 结论描述为可实盘执行或策略有效。

## 1. Sprint 2 暴露的硬化缺口

Sprint 2 当前 health 状态为 `report_only_research_ready`，但不能进入产品或生产决策，主要原因如下：

| 缺口 | Sprint 2 当前状态 | 对结论的影响 |
| --- | --- | --- |
| benchmark | `benchmark_unavailable=11064` | 不能计算或声明 excess return |
| excess return | `deferred_until_benchmark_frozen=11064` | 只能输出 raw/net labels |
| 复权策略 | `adjustment_policy` 全部 missing | forward labels 与回测收益可能不可比 |
| 停牌字段 | `suspend_status` 全部 missing | 无法判断 next open/close 是否可成交 |
| 涨跌停字段 | `limit_up_down_status` 全部 missing | 无法模拟无法买入/卖出的订单 |
| failed order | 全部 unavailable | 无法构造执行级成交账本 |
| partial fill | 全部 unavailable | 无法估算仓位、turnover、成本的真实偏差 |
| tier A/B 样本 | A 桶约 14，B 桶约 20 | tier monotonicity 为 `insufficient_sample` |
| midday labels | formal 样本为 0 | confirmed/downgrade 无法后验验证 |
| 2026 当前 artifact | 只进 coverage | 不得进入 formal forward label evaluation |

## 2. Benchmark 冻结方案

### 2.1 冻结对象

P1 应将 benchmark 从配置占位升级为可复现数据集。

第一版建议冻结：

| 层级 | Benchmark | 用途 |
| --- | --- | --- |
| Primary | CSI500 | 默认 excess return 基准 |
| Secondary | HS300 | 大盘风格对照 |
| Secondary | CSI1000 | 小盘风格对照 |
| Internal | equal_weight_eligible_pool | Prism eligible universe 内部等权对照 |

Primary benchmark 必须先冻结；secondary benchmark 可以晚于 primary，但在缺失时不得输出对应 excess return。

### 2.2 数据契约

每个 benchmark daily row 至少包含：

| 字段 | 要求 |
| --- | --- |
| `benchmark_id` | 如 `CSI500` |
| `trade_date` | 交易日，格式 `YYYY-MM-DD` |
| `open` | 当日开盘点位 |
| `close` | 当日收盘点位 |
| `prev_close` | 前收盘点位 |
| `adjusted_close` | 如指数无需复权，等于 close，并标记 policy |
| `calendar_id` | 使用的交易日历 |
| `source_name` | 数据来源 |
| `source_artifact` | 原始数据路径 |
| `source_hash` | 原始数据 sha256 |
| `generated_at` | 生成时间 |
| `revision` | 数据批次版本 |

### 2.3 冻结产物

建议 P1 交付：

- `data/quant/benchmarks/benchmark_daily.jsonl`
- `data/quant/benchmarks/benchmark_manifest.json`
- `data/quant/reports/benchmark_freeze_audit_latest.md`

manifest 至少记录：

- benchmark 列表。
- 日期范围。
- source artifact。
- sha256。
- calendar id。
- row count。
- missing date count。
- duplicate date count。
- open/close/prev_close 缺失率。

### 2.4 验收标准

只有同时满足以下条件，才允许在下一次 Sprint 2 里计算 excess return：

- Primary benchmark 覆盖所有 formal label trade dates 和 forward windows。
- benchmark row 与交易日历完全对齐，无重复日期。
- `open`、`close`、`prev_close` 缺失率为 0。
- benchmark manifest 有 source hash 和 config checksum。
- label 生成逻辑记录 benchmark revision。
- 对缺失 secondary benchmark 的窗口输出 `benchmark_unavailable`，不得静默回填。

## 3. 复权与 Adjusted Price 策略

### 3.1 决策原则

A 股个股 forward labels 必须统一价格口径。P1 需要冻结以下策略之一：

| 选项 | 说明 | 建议 |
| --- | --- | --- |
| 前复权 adjusted price | 适合研究历史相对收益，历史价格连续 | 建议作为 research label 默认 |
| 不复权 raw price | 接近当时可见价格，但遇到除权除息会产生跳变 | 仅保留为诊断 |
| 后复权 | 依赖未来信息，不适合 PIT formal labels | 不建议用于 formal |

建议 P1 采用前复权价格作为 formal forward label 的收益口径，同时保留 raw price return 用于审计。

### 3.2 必须冻结的字段

个股 daily price row 至少包含：

| 字段 | 要求 |
| --- | --- |
| `code` | 标准证券代码 |
| `trade_date` | 交易日 |
| `open_raw` | 原始开盘价 |
| `close_raw` | 原始收盘价 |
| `prev_close_raw` | 原始前收 |
| `open_adj` | 前复权开盘价 |
| `close_adj` | 前复权收盘价 |
| `prev_close_adj` | 前复权前收 |
| `adj_factor` | 复权因子 |
| `adjustment_policy` | 如 `qfq` |
| `source_name` | 数据来源 |
| `source_artifact` | 原始路径 |
| `source_hash` | 原始 sha256 |
| `available_timestamp` | 数据可用时间 |

### 3.3 Label 口径

P1 后的 formal labels 应输出：

- `raw_return`: 使用 raw price，诊断用途。
- `adjusted_return`: 使用 frozen adjusted price，formal research 主口径。
- `net_return`: adjusted return 扣除成本后的收益。
- `excess_return`: net return 减 frozen benchmark return，只有 benchmark 已冻结时可输出。

如果 `adjustment_policy` 缺失：

- label 状态必须为 `unavailable` 或 `research_only_adjustment_missing`。
- 不得进入 formal evaluation。
- 回测必须继续标记 `research_only_simulation`。

### 3.4 验收标准

- 所有 formal label rows 的 `adjustment_policy` 非空。
- 所有 formal label rows 的 entry/exit adjusted price 非空。
- raw 与 adjusted return 差异超过阈值的样本进入 audit 明细。
- 除权除息日期必须可追溯到 `adj_factor` 变化。
- 不允许使用未来才发布的复权因子破坏 PIT；如果无法证明 PIT，只能标记 research-only。

## 4. 停牌、涨跌停、Failed Order、Partial Fill 补齐方案

### 4.1 停牌数据

需要新增每个 code/trade_date 的停牌状态：

| 字段 | 说明 |
| --- | --- |
| `is_suspended` | 当日是否停牌 |
| `suspend_reason` | 如可得则记录 |
| `resume_date` | 如可得则记录 |
| `source_name` | 数据来源 |
| `source_hash` | source hash |
| `available_timestamp` | 可用时间 |

执行规则：

- entry day 停牌：该候选不能成交，label 标记 `entry_suspended`。
- exit day 停牌：退出顺延到下一可交易日，并记录 `exit_delayed_by_suspend`。
- 若无法确认停牌状态：不得进入 execution-realistic backtest。

### 4.2 涨跌停数据

需要新增每个 code/trade_date 的涨跌停价格和触达状态：

| 字段 | 说明 |
| --- | --- |
| `limit_up_price` | 当日涨停价 |
| `limit_down_price` | 当日跌停价 |
| `hit_limit_up` | 是否触及涨停 |
| `hit_limit_down` | 是否触及跌停 |
| `open_at_limit_up` | 开盘是否涨停 |
| `open_at_limit_down` | 开盘是否跌停 |
| `close_at_limit_up` | 收盘是否涨停 |
| `close_at_limit_down` | 收盘是否跌停 |

执行规则：

- next open 买入时，如果 `open_at_limit_up=true`，订单标记 `entry_blocked_limit_up`。
- 卖出时如果 `open_at_limit_down=true`，订单标记 `exit_blocked_limit_down`，退出顺延。
- 若只知道 high/low 触达但不知道盘口可成交性，必须保守标记为 `limit_execution_ambiguous`。

### 4.3 Failed Order

P1 第一版不需要真实券商订单，但必须构造研究级 order outcome：

| 字段 | 说明 |
| --- | --- |
| `order_id` | research order id |
| `panel_row_id` | 来源信号 |
| `trade_date` | 计划交易日 |
| `side` | buy/sell |
| `planned_price_model` | next_open/next_close |
| `order_status` | filled/blocked/failed/unavailable |
| `failure_reason` | suspended/limit/no_price/missing_data |
| `fill_price` | 成交价格 |
| `fill_qty_pct` | 成交比例 |

`failed order` 可以由停牌、涨跌停、缺价等规则派生，不必等真实交易系统。

### 4.4 Partial Fill

P1 可先做保守研究模型：

| 数据可得性 | 处理 |
| --- | --- |
| 有成交额/成交量 | 用 max participation rate 估算 partial fill |
| 只有 OHLCV | 用 volume cap 做研究级 partial fill |
| 无 volume | partial fill unavailable，不能做 execution-realistic |

建议第一版参数：

- `max_participation_rate`: 5% 或更保守。
- 单票上限仍继承 `max_single_position_pct=20%`。
- 若估算可成交金额小于目标金额，标记 `partial_fill_estimated`。

### 4.5 交付与验收

建议 P1 交付：

- `data/quant/execution/security_trading_status.jsonl`
- `data/quant/execution/limit_status.jsonl`
- `data/quant/execution/research_order_outcomes.jsonl`
- `data/quant/reports/execution_data_hardening_audit_latest.md`

验收标准：

- formal label rows 的 suspend/limit 状态覆盖率为 100%。
- 对每个 blocked/failed order 有明确 reason。
- partial fill 若不可得，必须继续标记 unavailable。
- 任何缺失执行状态的样本不得进入 execution-realistic backtest。

## 5. 2026 Forward Labels Formal 化方案

### 5.1 当前限制

Sprint 2 中 2026 当前运行 artifact 只允许进入 coverage，不允许进入 formal forward label evaluation。原因：

- forward window 可能尚未完全成熟。
- artifact generated timestamp 与 feature available timestamp 需要逐项 PIT 审计。
- 当前价格、复权、停牌、涨跌停、benchmark 尚未冻结。

### 5.2 Formal Label 准入条件

每个 2026 panel row 只有满足以下条件，才能从 coverage 升级为 formal label：

| 条件 | 要求 |
| --- | --- |
| forward window matured | 对应 1/3/5/10 日 exit date 已经过去，且价格可得 |
| PIT pass | source timestamp <= decision timestamp，feature available timestamp <= decision timestamp |
| source frozen | source artifact 有 sha256，manifest 记录 revision |
| price frozen | entry/exit raw 与 adjusted price 可追溯 |
| adjustment frozen | adjustment policy 非空 |
| calendar frozen | entry/exit 使用同一 frozen trading calendar |
| benchmark frozen | primary benchmark 覆盖该窗口，才可输出 excess return |
| execution status frozen | suspend/limit/order outcome 可得 |

### 5.3 状态迁移

建议使用明确状态机，但不是题材状态机，也不影响生产：

```text
coverage_only
  -> pending_forward_window
  -> pending_data_hardening
  -> available_research_only
  -> formal_label_ready
```

状态含义：

| 状态 | 含义 |
| --- | --- |
| `coverage_only` | 只能出现在 coverage，不进入 label 评估 |
| `pending_forward_window` | 等待 1/3/5/10 日窗口成熟 |
| `pending_data_hardening` | 窗口成熟但价格/执行/benchmark/PIT 未齐 |
| `available_research_only` | 可用于 Sprint 2 当前级别 report-only 统计 |
| `formal_label_ready` | 数据硬化完成，可进入 formal research evaluation |

### 5.4 验收标准

- 2026 labels 必须按 window 分别成熟，不允许整批提前放行。
- 对每个 unavailable label 写明 `unavailable_reason`。
- `formal_label_ready` 不得包含 benchmark、复权、执行状态缺失的样本。
- 升级前后 row count、coverage rate、drop reason 必须写入报告。

## 6. AI Tier A/B 样本扩充方案

### 6.1 当前问题

Sprint 2 的 tier monotonicity 无法下结论，关键原因是：

- A 桶约 14。
- B 桶约 20。
- 每个 entry/window 下 A/B 均低于 30。

这使 A/B/C 单调性只能标记 `insufficient_sample`。

### 6.2 扩充原则

扩充 AI tier A/B 样本不能通过事后重打标签制造结论。必须遵守：

- 使用当时 artifact 原始 tier。
- 不用未来收益反推 tier。
- 不合并语义不同的 lane。
- 不把 AI tier 作为生产 A/B/C 替换。
- 每次扩充都记录 source artifact、hash、generated_at。

### 6.3 样本来源

优先级建议：

| 优先级 | 来源 | 说明 |
| --- | --- | --- |
| P0 | 2024 research backfill AI history | 已经进入 P0 panel 的历史样本 |
| P1 | 继续回填更多历史 AI artifacts | 需要同等 schema 与 PIT 证明 |
| P1 | 2026 已 matured 且 formal-ready artifact | 通过第 5 节准入后加入 |
| P2 | 新 shadow run 积累 | 不影响生产，只积累研究样本 |

### 6.4 最小样本门槛

P1 不应只满足每桶 30 的最低门槛。建议设置两层：

| 层级 | 门槛 | 用途 |
| --- | --- | --- |
| Minimum | 每个 tier bucket 每个主窗口 >= 30 | 允许从 insufficient_sample 升级为 research_only |
| Preferred | 每个 tier bucket 每个主窗口 >= 100 | 允许讨论更稳定的单调性证据 |

主窗口建议：

- primary: `next_open` / 5D。
- secondary: `next_open` / 1D、3D、10D 和 `next_close` 对照。

### 6.5 验收标准

- A/B/C 每桶样本量和日期覆盖写入报告。
- 每个 tier bucket 至少跨多个 trade_date，不能集中在少数日期。
- 每个 tier bucket 的 source artifact revision 分布清楚。
- 若 A/B 仍低于 30，tier monotonicity 必须继续 `insufficient_sample`。

## 7. 什么时候才允许重新跑 Sprint 2

P1 不应在任意数据小修后反复重跑 Sprint 2 并挑选有利结果。必须先通过 data hardening gates。

### 7.1 必须全部满足的硬门槛

| Gate | 通过条件 |
| --- | --- |
| Benchmark gate | Primary benchmark frozen，coverage 100%，manifest/hash 完整 |
| Price gate | formal rows 的 raw/adjusted entry/exit price 覆盖 100% |
| Adjustment gate | formal rows 的 `adjustment_policy` 覆盖 100% |
| Calendar gate | trading calendar frozen，entry/exit date 可复现 |
| Execution status gate | suspend/limit status 覆盖 100% |
| Order outcome gate | failed/blocked order 有 reason；partial fill 可得或显式 unavailable |
| PIT gate | formal rows PIT pass 100%；失败样本只进 coverage |
| 2026 maturity gate | 2026 rows 按 window matured 后才可进入 formal |
| Sample gate | tier A/B/C 主窗口每桶至少 30；低于 30 继续 insufficient_sample |

### 7.2 允许重跑的触发条件

只有以下场景允许重跑 Sprint 2：

1. benchmark freeze 完成，并通过 audit。
2. adjusted price 和 calendar freeze 完成。
3. execution status 数据补齐完成。
4. 2026 forward windows 成熟并通过 formal label audit。
5. AI tier A/B 样本扩充后达到 minimum sample gate。
6. quant config revision 升级并记录 checksum。

每次重跑必须记录：

- input manifest revision。
- benchmark revision。
- price revision。
- execution data revision。
- config checksum。
- code revision。
- 与上一次 Sprint 2 的 diff 摘要。

### 7.3 重跑后仍必须保持的解释边界

即使 P1 数据硬化后重新运行 Sprint 2，也仍然不能自动进入生产。至少还需要：

- 样本外窗口验证。
- 多重检验风险标记。
- 成本和执行模型敏感性分析。
- 与现有生产排序的 shadow overlap 分析。
- 单独评审是否允许任何字段进入 P1 shadow。

## 8. P1 交付物建议

P1 数据硬化建议交付：

| 交付物 | 作用 |
| --- | --- |
| `data/quant/benchmarks/benchmark_daily.jsonl` | frozen benchmark daily data |
| `data/quant/benchmarks/benchmark_manifest.json` | benchmark source/hash/revision |
| `data/quant/prices/security_daily_prices.jsonl` | raw + adjusted security prices |
| `data/quant/prices/security_price_manifest.json` | price source/hash/revision |
| `data/quant/calendars/trading_calendar.jsonl` | frozen trading calendar |
| `data/quant/execution/security_trading_status.jsonl` | suspend/trading status |
| `data/quant/execution/limit_status.jsonl` | limit up/down status |
| `data/quant/execution/research_order_outcomes.jsonl` | research order outcome |
| `data/quant/reports/benchmark_freeze_audit_latest.md` | benchmark audit |
| `data/quant/reports/price_adjustment_audit_latest.md` | adjusted price audit |
| `data/quant/reports/execution_data_hardening_audit_latest.md` | execution data audit |
| `data/quant/reports/formal_label_readiness_latest.md` | formal label readiness |
| `data/quant/reports/tier_sample_expansion_latest.md` | AI tier A/B sample audit |

## 9. P1 验收标准

P1 数据硬化完成至少需要：

- Benchmark primary coverage 100%，并可复现。
- Formal labels 不再全量 `benchmark_unavailable`。
- Formal labels 的 adjusted entry/exit price 覆盖 100%。
- `adjustment_policy` 不再缺失。
- 停牌、涨跌停状态覆盖 formal rows。
- failed/blocked order 有明确 reason。
- partial fill 不可得时继续显式标记，不伪装成 full fill。
- 2026 rows 只在 forward window matured 且 data hardening pass 后进入 formal labels。
- AI tier A/B 主窗口样本每桶至少 30，否则继续不能重跑 tier monotonicity 正式结论。
- 重新运行 Sprint 2 前有完整 input revision 和 config checksum。

## 10. 决策建议

建议 P1 先进入数据硬化，不进入产品化。

P1 的第一阶段完成后，可以重新运行 Sprint 2，但只能在通过第 7 节全部硬门槛后进行。若任何 gate 未通过，Sprint 2 的结果仍必须保持 `research_only` 或 `insufficient_sample`，不得作为生产排序、A/B/C 替换、页面主决策、Prism Edge 或 ML 输入。
