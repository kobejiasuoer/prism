# Prism 量化升级 P1-A Benchmark & Execution Data Hardening 验收清单

Date: 2026-04-28
Role: independent acceptance reviewer
Scope: P1-A development boundary and acceptance checklist
Source:
- `docs/quant-upgrade-p0-review-revision-2026-04-28.md`
- `docs/quant-upgrade-sprint2-acceptance-checklist-2026-04-28.md`
- `docs/quant-upgrade-sprint2-acceptance-report-2026-04-28.md`
- `docs/quant-upgrade-p1-data-hardening-plan-2026-04-28.md`

## 0. 开发边界

P1-A 的目标是把 Sprint 2 暴露的 benchmark、复权、停牌、涨跌停、订单失败、部分成交等数据缺口补齐，让 forward labels 和重新跑出的 Sprint 2 报告更可信。

P1-A 不是产品化阶段。即使 P1-A 完成，也不能自动把任何量化字段接入生产排序、A/B/C、页面主决策、Prism Edge、Expected 5D 默认展示或 ML。

验收结论只允许三类：

| 结论 | 含义 |
| --- | --- |
| 通过 | benchmark、价格、执行数据、labels、重跑报告均满足 P1-A 边界，且所有结论仍 report-only。 |
| 有条件通过 | 关键数据有改善，但仍有 benchmark/复权/执行/样本缺口；只能继续数据补强或 shadow 预研。 |
| 不通过 | 数据缺口被静默掩盖，或报告把 research-only / simulation 结论升级为 production-ready。 |

## 1. P1-A 目标

P1-A 必须围绕数据硬化，不做策略产品化。

| 目标 | 验收方向 |
| --- | --- |
| 冻结 benchmark | 建立 primary/secondary/internal benchmark 数据、manifest、hash、coverage audit |
| 明确 adjusted price / 复权策略 | 定义 raw、forward-adjusted、backward-adjusted 的使用边界和 `adjustment_policy` |
| 补停牌、涨跌停字段来源 | 每个 formal label 的 entry/exit date 能判断 suspend 与 limit up/down |
| 定义 failed order / partial fill 保守模拟规则 | 用停牌、涨跌停、缺价、成交量/成交额约束派生 research order outcome |
| 让 forward labels 支持 excess return 和更真实 execution flags | label 输出 benchmark return、excess return、execution flags 和细分 status |
| 重新跑 Sprint 2 报告 | factor/backtest/health 可以重跑，但仍必须 report-only，不得升级为 production-ready |

P1-A 完成后，Prism 应能回答：

- 每个 formal label 使用哪个 benchmark、价格口径、复权策略和执行假设。
- 哪些样本可以输出 excess return，哪些必须保持 unavailable。
- 哪些订单会因停牌、涨跌停、缺价、partial fill 规则被降级或阻断。
- 重新跑 Sprint 2 后，benchmark/execution availability 是否提升，且是否仍保持 report-only。

## 2. P1-A 明确不做

严格禁止：

- 不接生产排序。
- 不替换 A/B/C。
- 不做页面。
- 不做 Prism Edge 产品化。
- 不做 Expected 5D 默认展示。
- 不做 ML。
- 不把 research-only backtest 说成可执行回测。
- 不把 data hardening 后的报告直接解释为策略可上线。
- 不绕过 `final_score` 禁用、`score` lane scoped、gate batch/context 这些 Sprint 2 硬门槛。

P1-A 允许做的只有：

- 数据源冻结、manifest、hash、coverage audit。
- label schema 和状态定义升级。
- 保守 execution simulation 规则定义。
- 重新生成 report-only 的 Sprint 2 报告。
- 新增或更新针对 P1-A 数据契约的测试。

## 3. Benchmark 验收清单

### 3.1 Benchmark 范围

| 层级 | Benchmark | 用途 | 是否必须 |
| --- | --- | --- | --- |
| Primary | CSI500 | 默认 excess return 基准 | 是 |
| Secondary | HS300 | 大盘风格对照 | 是，缺失时必须显式 unavailable |
| Internal | eligible universe equal-weight | Prism eligible universe 内部等权基准 | 是，若 universe 不完整则 unavailable |

### 3.2 每个 benchmark 必须记录

| 字段/项目 | 验收要求 |
| --- | --- |
| `benchmark_id` | 稳定 ID，如 `CSI500`、`HS300`、`eligible_equal_weight` |
| source | 数据来源名称、原始 artifact path、source timestamp |
| date coverage | 覆盖 formal label 所需 trade dates 和 forward windows |
| hash | 原始数据和生成数据均有 sha256 或等效 checksum |
| missing dates | 逐 benchmark 输出缺失日期列表和缺失原因 |
| duplicate dates | 重复日期必须为 0；否则该 benchmark 不可用 |
| return calculation method | 明确使用 open-to-close、close-to-close、entry-aligned 或 window-aligned |
| calendar | 使用 frozen trading calendar，不能静默用自然日 |
| revision | 每次更新 benchmark 都有 revision 和生成时间 |

### 3.3 Benchmark 通过标准

| 验收项 | 通过标准 | 失败处理 |
| --- | --- | --- |
| CSI500 primary coverage | 覆盖所有 formal labels 的 entry/exit windows | 任一缺口则 primary excess return unavailable |
| HS300 secondary coverage | 覆盖报告声明的比较窗口 | 缺口只影响 HS300 excess，不得影响 primary |
| eligible universe equal-weight | universe 成分、权重、日期均可复现 | universe 缺失时 internal benchmark unavailable |
| source/hash/revision | 每个 benchmark 均可追溯 | 不可追溯则不能用于 formal label |
| return method | 与 label entry model、holding window 对齐 | 口径不明时不能输出 excess return |

硬规则：benchmark 不完整时，对应 label/window 的 `excess_return` 必须 unavailable，不能用 0、前值、其他指数或静默插值替代。

## 4. Adjusted Price 验收清单

### 4.1 价格口径定义

| 价格口径 | 用途 | P1-A 建议 |
| --- | --- | --- |
| raw price | 审计和当时可见价格诊断 | 保留，不作为唯一正式收益口径 |
| forward-adjusted / 前复权 | formal research return 主口径 | 建议使用 |
| backward-adjusted / 后复权 | 长序列图表或诊断 | 不用于 PIT formal labels，除非证明不引入未来信息 |

### 4.2 必须新增或明确的字段

| 字段 | 验收要求 |
| --- | --- |
| `open_raw` / `close_raw` / `prev_close_raw` | 原始价格可追溯 |
| `open_adj` / `close_adj` / `prev_close_adj` | formal label 所用 adjusted price 非空 |
| `adj_factor` | 能解释 raw 与 adjusted 差异 |
| `adjustment_policy` | 明确 `raw`、`qfq`、`hfq` 或其他策略 |
| `price_source` / `source_artifact` / `source_hash` | 价格数据可复现 |
| `available_timestamp` | 证明 PIT 可用性 |

### 4.3 Adjusted price 通过标准

| 验收项 | 通过标准 |
| --- | --- |
| 复权策略 | 文档和配置中明确 formal label 使用哪种 adjusted price |
| `adjustment_policy` | formal label rows 覆盖率 100% |
| entry/exit adjusted price | formal label rows 覆盖率 100% |
| raw vs adjusted audit | 差异超过阈值的样本进入审计报告 |
| PIT | 复权因子或 adjusted price 的可用时间不破坏 PIT |

硬规则：不明确复权状态时，不得宣称正式收益、execution-realistic return 或可交易回测；相关 label 必须降级为 unavailable 或 research-only。

## 5. Execution Data 验收清单

### 5.1 必须覆盖的执行数据

| 项目 | 验收要求 |
| --- | --- |
| suspend status | 每个 code/date 能判断是否停牌、是否可交易、停牌原因如可得则记录 |
| limit up/down status | 每个 code/date 有涨停价、跌停价、开盘/收盘是否涨跌停、是否触及涨跌停 |
| failed order rule | 定义 entry/exit 因停牌、涨跌停、缺价、缺执行数据而失败的规则 |
| partial fill rule | 定义 volume/amount/participation rate 下的部分成交估算；不可得时显式 unavailable |
| T+1 rule | 明确买入后最早可卖出日期；不可违反 A 股 T+1 |
| stamp tax | 卖出印花税配置化并写入 label/backtest |
| commission | 买卖佣金和最低佣金配置化 |
| slippage | 滑点 bps 或模型配置化 |
| impact cost | 冲击成本开启状态、placeholder 或 calibration 状态明确 |
| lot size | 若 P1-A 不做，必须标记 deferred，不得假装精确成交股数 |
| participation rate | 若 P1-A 不做，必须标记 deferred；若做，必须记录参数 |

### 5.2 Failed order 保守规则

| 场景 | 默认保守处理 |
| --- | --- |
| entry day suspended | `order_status=blocked`，`failure_reason=entry_suspended` |
| exit day suspended | exit 顺延到下一可交易日，标记 `exit_delayed_by_suspend` |
| next open buy 且 open_at_limit_up | `order_status=blocked`，`failure_reason=entry_blocked_limit_up` |
| next open sell 且 open_at_limit_down | exit 顺延或 blocked，标记 `exit_blocked_limit_down` |
| price missing | `order_status=unavailable`，label 不进入 execution-realistic |
| execution data missing | `execution_flags` 写明缺口，不能静默 full fill |

### 5.3 Partial fill 保守规则

| 数据可得性 | 处理 |
| --- | --- |
| 有成交额/成交量 | 使用 max participation rate 估算 fill ratio |
| 只有 OHLCV | 使用 volume cap 做研究级 partial fill，并标记 `partial_fill_estimated` |
| 无 volume/amount | `partial_fill_unavailable`，不能称 full fill |
| 目标成交额超过可成交估算 | `fill_qty_pct < 1`，成本和收益按实际 fill ratio 计算或明确降级 |

### 5.4 Execution data 通过标准

- suspend status 覆盖 formal label entry/exit dates。
- limit up/down status 覆盖 formal label entry/exit dates。
- failed/blocked order 必须有 reason。
- partial fill 可得或显式 unavailable。
- T+1、stamp tax、commission、slippage、impact cost 均写入配置和报告。
- lot size / participation rate 若 P1-A 不做，必须在报告中列为 deferred。

## 6. Label 升级验收清单

### 6.1 Label 输出字段

| 字段 | 验收要求 |
| --- | --- |
| `raw_return` | 保留 raw price return，用于审计 |
| `adjusted_return` | 使用 frozen adjusted price 的主研究收益 |
| `net_return` | adjusted return 扣除成本后的收益 |
| `benchmark_return` | 与 entry model 和 holding window 对齐 |
| `excess_return` | `net_return - benchmark_return`，benchmark 完整时才输出 |
| `benchmark_id` | 记录 primary/secondary/internal benchmark |
| `benchmark_status` | complete/unavailable/partial 等明确状态 |
| `execution_flags` | suspend、limit、failed order、partial fill、T+1、cost、price missing 等 |
| `order_status` | filled/blocked/failed/partial/unavailable |
| `label_status` | 从 Sprint 2 的粗粒度状态升级为细分状态 |

### 6.2 `label_status` 建议定义

| 状态 | 含义 | 是否可进入正式研究评估 |
| --- | --- | --- |
| `coverage_only` | 只有覆盖记录，不进入 label 评估 | 否 |
| `pending_forward_window` | forward window 尚未成熟 | 否 |
| `pending_data_hardening` | 窗口成熟但 benchmark/price/execution/PIT 未齐 | 否 |
| `research_only_adjustment_missing` | 复权策略缺失 | 否 |
| `research_only_execution_missing` | 执行数据缺失 | 否 |
| `benchmark_unavailable` | benchmark 缺失，不能输出 excess return | raw/net 可 report-only，excess 否 |
| `available_research_only` | 可做 report-only 研究，但不能 execution-realistic | 是，需 guardrail |
| `formal_label_ready` | benchmark、price、execution、PIT 均满足 formal research | 是，仍不代表生产可用 |

### 6.3 Label 升级通过标准

- 每个 label 能追溯 panel row、source artifact、price artifact、benchmark revision、execution data revision。
- benchmark 完整时才输出 `benchmark_return` 和 `excess_return`。
- benchmark 不完整时 `excess_return` 字段缺失或为 unavailable，且不得进入 factor/backtest excess 结论。
- `execution_flags` 不得为空泛，必须列出具体 flags 或明确 `none`。
- 从 `available_research_only` 升级到 `formal_label_ready` 必须有审计报告支持。
- 2026 artifact 仍必须按 forward window 成熟度逐条准入，不能整批提前进入正式 label 评估。

## 7. 重新跑 Sprint 2 的验收标准

P1-A 可以重新跑 Sprint 2 报告，但重跑本身仍是 report-only 验收，不是产品上线。

### 7.1 Factor evaluation

| 验收项 | 通过标准 |
| --- | --- |
| `factor_evaluation_latest.md` 增加 excess return | 只有 benchmark 完整的样本/window 才展示 excess return |
| 仍 report-only | 报告必须保留 no production sorting、no A/B/C replacement、no page、no Prism Edge、no ML |
| factor 字段边界 | `final_score` 仍禁用；`score` 仍 lane scoped；gate 仍 batch/context |
| 样本数 | `<30` bucket 仍 `insufficient_sample`，不能给正面结论 |
| 重叠收益 | 3/5/10 日窗口标记 Newey-West、block bootstrap 或 walk-forward 状态 |

### 7.2 Portfolio backtest

| 验收项 | 通过标准 |
| --- | --- |
| execution assumptions | 报告列出 suspend、limit、failed order、partial fill、T+1、成本、复权假设 |
| research-only vs execution-realistic | 只有所有执行字段完整且规则通过时，才允许从 `research_only_simulation` 降级为更细状态；不得直接说可执行 |
| benchmark/excess | benchmark 完整时可以展示 excess return；缺失窗口必须 unavailable |
| 成本 | stamp tax、commission、slippage、impact cost 明确拆分 |
| 组合指标 | 回撤、换手、胜率、成本影响、blocked/partial/failed order count 均应展示 |

### 7.3 Quant health

| 验收项 | 通过标准 |
| --- | --- |
| benchmark availability | `quant_health_latest` 展示 benchmark coverage 提升和仍缺失的窗口 |
| execution availability | 展示 suspend/limit/order/partial fill 覆盖率 |
| production impact | 必须仍为 `none` |
| hard gates | 不阻断生产、不改排序、不替换 A/B/C、不要求页面 |
| overall status | 不得使用容易误导为 production-ready 的表达；建议明确 `report_only_data_hardened_not_production_ready` |

硬规则：P1-A 重跑后的任何报告都不得把结论升级成 production-ready，不得建议用户按回测结果开仓。

## 8. P1-A 完成后的决策树

```text
P1-A benchmark/price/execution data 是否完整？
  否 ->
    继续补数据；不得进入 shadow Prism Edge；Sprint 2 仍保持 research-only。
  是 ->
    Labels 是否支持 adjusted/net/benchmark/excess/execution flags？
      否 ->
        继续补 label schema 和审计；不得进入 shadow Prism Edge。
      是 ->
        重新跑 Sprint 2 是否仍保持 report-only 且未触碰生产？
          否 ->
            回头修报告边界和 guardrails。
          是 ->
            score/tier/gate 硬门槛是否仍通过？
              否 ->
                回头修 score/tier/gate 逻辑。
              是 ->
                factor/backtest 是否有足够样本、样本外和执行敏感性证据？
                  否 ->
                    继续补数据、样本、walk-forward，不进入 shadow Prism Edge。
                  是 ->
                    可以申请进入 shadow Prism Edge 评审；
                    仍不得进入生产排序或页面默认动作。
```

### 8.1 可以进入 shadow Prism Edge 的条件

- Primary benchmark 完整，excess return 可复现。
- adjusted price、calendar、suspend、limit、failed order、partial fill 有完整或明确降级的执行规则。
- labels 至少在主窗口达到 `formal_label_ready` 或等价状态。
- 重新跑 Sprint 2 后，factor/backtest/health 仍 report-only 且不 production-ready。
- score/tier/gate 规则未回退：`final_score` 禁用、`score` 不跨 lane、gate batch/context、tier 不替换 A/B/C。
- 至少完成 walk-forward、block bootstrap 或 Newey-West 状态标记。

### 8.2 必须继续补数据的情形

- CSI500 primary benchmark 任一 formal window 缺失。
- 复权策略不清，或 entry/exit adjusted price 缺失。
- 停牌或涨跌停状态不能覆盖 formal label rows。
- failed order 没有 reason，partial fill 被静默当 full fill。
- lot size / participation rate 未做却没有 deferred 标记。
- 2026 artifact 未按 forward window matured 逐条准入。
- quant health 仍显示 benchmark/execution availability 大面积缺失。

### 8.3 需要回头修 score/tier/gate 逻辑的情形

- `final_score` 被重新引入 formal evaluation 或回测选股。
- `score` 被跨 AI、scan、watchlist lane 合并。
- gate 被当成个股原生因子或 hard gate。
- tier monotonicity 不足样本却给出正面结论。
- P1-A 报告把 A/B/C 替换、生产排序、页面主动作、Prism Edge 或 ML 作为默认下一步。

## 9. P1-A 验收提交包建议

开发者提交 P1-A 时，至少应附：

| 类别 | 内容 |
| --- | --- |
| 数据 manifest | benchmark、price、calendar、execution data 的 source/hash/revision |
| 审计报告 | benchmark coverage、price adjustment、execution data hardening、label readiness |
| Label diff | P1-A 前后 label_status、benchmark_status、execution_flags 的数量变化 |
| 重跑报告 | Sprint 2 factor/backtest/health latest reports，且仍 report-only |
| 测试说明 | benchmark 缺失、复权缺失、停牌、涨跌停、failed order、partial fill、excess unavailable 的测试 |
| 边界确认 | 未改生产排序、A/B/C、页面、Prism Edge、Expected 5D 默认展示、ML |

## 10. 独立验收重点

独立验收时优先看四件事：

1. benchmark 是否真的冻结，而不是只填了配置名。
2. adjusted price 和 execution flags 是否让 labels 更可信，而不是把缺口藏起来。
3. excess return 是否只在 benchmark 完整时输出。
4. 重跑 Sprint 2 是否仍保持 report-only，没有把数据硬化误读成 production-ready。
