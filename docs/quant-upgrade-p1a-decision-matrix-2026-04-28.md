# Prism 量化升级 P1-A 决策矩阵与首张开发卡模板

Date: 2026-04-28
Role: independent acceptance reviewer
Scope: P1-A decision matrix and first development-card acceptance template
Source:
- `docs/quant-upgrade-p1a-hardening-acceptance-checklist-2026-04-28.md`
- `docs/quant-upgrade-sprint2-acceptance-report-2026-04-28.md`
- `docs/quant-upgrade-p1-data-hardening-plan-2026-04-28.md`

## 0. 使用方式

本文件用于 P1-A source inventory 交付后的拍板会。它不替代 source inventory，也不假设任何数据源已经存在。

拍板原则：

- 先决定口径，再写代码。
- 数据源确认存在前，不把任何字段升为 formal。
- benchmark、复权、执行状态任一不完整时，相关 label/window 必须 unavailable 或 research-only。
- P1-A 仍然禁止页面、Prism Edge 产品化、生产排序、A/B/C 替换、Expected 5D 默认展示、ML。

## 1. P1-A 必须拍板的问题

| 问题 | 可选项 | 推荐拍板 | 备注 |
| --- | --- | --- | --- |
| 主 benchmark 用什么 | CSI500 / HS300 / eligible universe equal-weight | CSI500 为 primary，HS300 与 eligible equal-weight 为 secondary/internal | CSI500 更接近中盘成长/短线候选的常见风险暴露；eligible equal-weight 适合作内部对照 |
| adjusted price 用什么 | raw / 前复权 / 后复权 | 前复权作为 formal research return 主口径，raw 保留审计，后复权不用于 PIT formal labels | 后复权容易引入未来信息争议 |
| benchmark 不完整时 excess return 如何处理 | 输出 0 / 用替代 benchmark / unavailable | unavailable | 不能静默回填或用其他指数顶替 |
| 没有停牌/涨跌停数据时是否继续 research-only | 继续 research-only / 忽略缺口 / 乐观 full fill | 继续 research-only | 不得宣称 execution-realistic |
| failed order / partial fill 第一版如何做 | 不做 / 保守标记 / 完整撮合模拟 | 保守标记 | 第一版用停牌、涨跌停、缺价、volume cap 等规则派生状态 |
| 是否允许重新跑 Sprint 2 报告 | 不允许 / 允许 report-only 重跑 / 允许产品化重跑 | 允许 report-only 重跑 | 重跑必须记录 input revision、config checksum、data revision |
| 是否仍禁止页面、Prism Edge、生产排序 | 禁止 / 条件开放 / 开放 | 禁止 | P1-A 是数据硬化，不是产品化 |

拍板会最低输出：

- Primary benchmark 和 secondary benchmark 列表。
- formal label 的价格口径和 fallback 规则。
- benchmark/execution 不完整时的状态定义。
- 第一张开发卡任务名称和验收边界。
- 明确“不做页面、不做 Prism Edge、不改生产排序”的会议结论。

## 2. Benchmark 决策矩阵

| 选项 | 优点 | 缺点 | 数据要求 | 对当前 Prism 短线系统的适配度 | 风险 | 推荐结论 |
| --- | --- | --- | --- | --- | --- | --- |
| CSI500 | 比 HS300 更接近中盘成长和活跃题材候选；适合做默认超额收益基准；外部可解释性较好 | 不一定覆盖小盘/微盘或高弹性题材风格；对极短线题材轮动仍可能偏宽 | 指数 open/close/prev_close、交易日历、source/hash、完整 date coverage | 高 | 若候选池偏小盘，CSI500 可能低估或高估相对表现 | 推荐作为 primary benchmark |
| HS300 | 大盘蓝筹代表性强；外部认知高；适合作市场风险对照 | 与 Prism 短线候选风格可能偏离，容易把风格差异误读成 alpha | 指数 open/close/prev_close、交易日历、source/hash、完整 date coverage | 中 | 候选池偏中小盘时，HS300 excess 解释力不足 | 推荐作为 secondary benchmark，不作为 primary |
| eligible universe equal-weight | 最贴近 Prism 当日可选池；能回答“是否优于同池随机等权” | 依赖 eligible universe 完整性、成分权重、停牌/涨跌停处理；工程复杂度高；外部解释性弱 | 每日 eligible universe、成分价格、权重规则、缺失成分处理、source/hash | 高，但前提是 universe ledger 可信 | universe 构造若有幸存者偏差，会污染基准 | 推荐作为 internal benchmark；不替代 CSI500 primary |

建议拍板：

- `primary_benchmark = CSI500`
- `secondary_benchmarks = [HS300]`
- `internal_benchmarks = [eligible_universe_equal_weight]`
- 任一 benchmark 缺 date/source/hash/return method 时，该 benchmark 对应的 `benchmark_return` 和 `excess_return` 必须 unavailable。

## 3. Adjusted Price 决策矩阵

| 选项 | 适合什么场景 | 对 forward return 的影响 | 数据要求 | 风险 | 推荐结论 |
| --- | --- | --- | --- | --- | --- |
| raw price | 审计当时可见价格、排查行情源、解释成交价 | 遇到除权除息会出现非经济性跳变，可能污染 1/3/5/10 日收益 | raw open/close/prev_close、source/hash、calendar | 把除权跳变误判为策略收益或亏损 | 保留为 audit return，不作为 formal 主口径 |
| forward-adjusted / 前复权 | 历史研究、连续收益计算、formal forward label | 能消除除权除息导致的价格跳变，更适合横向比较 | adjusted open/close/prev_close、adj_factor、adjustment_policy、PIT 可用性说明 | 若复权因子不可 PIT 追溯，可能引入未来信息争议 | 推荐作为 formal research return 主口径 |
| backward-adjusted / 后复权 | 长期图表或诊断分析 | 常依赖未来累计调整，forward label 中容易有未来信息问题 | hfq price、adj_factor、可用时间证明 | PIT 风险最高，不适合正式 forward label | 不推荐用于 P1-A formal labels |

建议拍板：

- formal label 主收益口径使用前复权。
- raw return 保留为审计字段。
- 后复权不进入 formal label、factor evaluation 或 portfolio backtest。
- 如果 `adjustment_policy` 或 adjusted entry/exit price 缺失，label 不得进入 formal research evaluation。

## 4. Execution Data 决策矩阵

| 选项 | 可行性 | 准确性 | 工程成本 | 是否足够进入 P1-A | 推荐结论 |
| --- | --- | --- | --- | --- | --- |
| 只标记 unavailable | 最高，最容易落地 | 低，只能说明缺口，不能改善 execution realism | 低 | 足够作为 fallback，不足以完成 P1-A 目标 | 必须保留为缺口处理，但不能作为最终方案 |
| 用价格规则推断涨跌停 | 中等；可由 OHLC 和涨跌停价规则推断部分状态 | 中等；能发现 open/close at limit，但无法证明盘口可成交性 | 中 | 可作为 P1-A 第一阶段保守规则 | 推荐作为第一版 limit status 的保守实现，但需标记 ambiguous |
| 引入外部/新增数据源 | 取决于 source inventory | 高，若有官方或可信数据可显著提升 | 中到高 | 是，若 source 确认存在且可复现 | 推荐优先用于 suspend/limit/benchmark/price，但需 source/hash/coverage audit |
| failed order / partial fill 保守模拟 | 中等；可基于停牌、涨跌停、缺价、volume/amount cap | 中等偏保守；不是真实撮合，但能避免乐观 full fill | 中 | 是，适合作 P1-A 第一版 | 推荐做保守标记，不做完整撮合引擎 |

建议拍板：

- suspend status 优先使用确认存在的数据源；没有则 formal execution unavailable。
- limit up/down 可第一版用价格规则保守推断，但必须区分 confirmed 与 inferred。
- failed order 第一版只做保守标记，不接真实券商订单。
- partial fill 第一版可用成交量/成交额和 participation rate 估算；没有 volume/amount 时标记 unavailable。
- 任一执行字段缺失时，回测不得宣称 execution-realistic。

## 5. 第一张 P1-A 开发卡推荐模板

以下模板等 source inventory 出来后直接填写。第一张开发卡建议优先选择“数据源最确定、能解锁后续 label 的基础任务”，通常是 benchmark freeze 或 price/adjustment audit；最终选择必须由 source inventory 证明。

```text
任务名称：
  [P1-A-01] <填写：例如 Benchmark Freeze Audit / Adjusted Price Source Audit>

目标：
  - <本卡要冻结或审计的具体数据源>
  - <本卡如何解除 Sprint 2 的哪个 hardening 缺口>
  - <本卡完成后哪些字段仍只能 unavailable/research_only>

输入数据：
  - source name:
  - source path / API / artifact:
  - date coverage:
  - symbol/index coverage:
  - known missing fields:
  - source hash / checksum plan:

修改路径：
  - <允许修改的代码路径，待 source inventory 后填写>
  - <允许新增的数据路径，待 source inventory 后填写>
  - <允许新增的 audit/report 路径，待 source inventory 后填写>

输出产物：
  - <manifest path>
  - <audit report path>
  - <jsonl/data output path, if any>
  - <tests>

不做事项：
  - 不接生产排序。
  - 不替换 A/B/C。
  - 不做页面。
  - 不做 Prism Edge 产品化。
  - 不做 Expected 5D 默认展示。
  - 不做 ML。
  - 不把 research-only backtest 说成可执行回测。
  - 不覆盖 Sprint 2 reports，除非该卡明确进入 report-only rerun 阶段。

验收标准：
  - source、date coverage、hash、missing dates/fields 写入 manifest。
  - 对所有缺失数据输出 unavailable/research_only 状态，不静默回填。
  - 不改变生产排序、A/B/C、页面、Prism Edge、ML。
  - 与 P1-A checklist 中对应章节逐项对齐。

测试要求：
  - source 缺失时输出 unavailable。
  - missing date 不计算 excess_return 或 execution-realistic flag。
  - hash/revision 可复现。
  - 不触发生产路径。
  - 若涉及 labels，覆盖 benchmark/adjustment/execution 缺口的降级状态。

回滚方式：
  - 删除或忽略本卡新增的数据 revision。
  - 回退配置中的 data revision 指针。
  - 保留 source inventory 与 audit 报告，标记该 revision rejected。
  - 不需要回滚生产排序或页面，因为本卡不应触碰它们。
```

第一张开发卡推荐选择规则：

| 候选第一卡 | 何时优先 | 为什么 |
| --- | --- | --- |
| Benchmark Freeze Audit | CSI500/HS300 数据源已确认存在且覆盖 2024 labels | 直接解除 excess return 最大阻塞 |
| Adjusted Price Source Audit | 个股 raw/adjusted price 和 adj_factor 已确认存在 | 解除 formal return 口径阻塞 |
| Execution Source Inventory Hardening | 停牌/涨跌停数据源不确定 | 先别写 label，先把可得性审清楚 |
| Label Status Schema Draft | 数据源确认度不足但状态机可先拍板 | 防止后续代码把缺口静默吞掉 |

## 6. 独立评审问题清单

第一个 AI 交 source inventory 后，独立评审必须追问：

### 6.1 数据源存在性

- 哪些 benchmark 数据源是确认存在的？
- CSI500、HS300 是否都有 open、close、prev_close 和完整交易日？
- eligible universe equal-weight 所需的每日 universe 成分是否确认存在？
- 个股 adjusted price、adj_factor、raw price 是否确认存在？
- 停牌、涨跌停、成交量/成交额数据是否确认存在？

### 6.2 推断 vs 确认

- 哪些字段来自原始数据源，哪些字段是规则推断？
- 涨跌停状态是 source-provided，还是用 OHLC/limit price 推断？
- partial fill 是真实成交约束，还是 volume cap 估算？
- benchmark return 是直接读取，还是由 open/close 计算？
- source availability timestamp 是真实字段，还是从文件名/生成时间推断？

### 6.3 阻塞项

- 哪些数据不足会阻塞 P1-A？
- 缺哪个字段会导致 `excess_return` 必须 unavailable？
- 缺哪个字段会导致 label 不能升级到 `formal_label_ready`？
- 哪些缺口会使回测继续保持 `research_only_simulation`？
- 是否有任何 source 缺口会影响 PIT 证明？

### 6.4 可降级项

- 哪些缺口可以用 unavailable/research_only 处理？
- secondary benchmark 缺失是否只影响 secondary excess？
- eligible equal-weight 缺失是否可以不阻塞 CSI500 primary？
- partial fill 不可得是否可以标记 `partial_fill_unavailable` 并继续 report-only？
- lot size / participation rate 如果 P1-A 不做，是否已明确 deferred？

### 6.5 第一张开发卡优先级

- 第一张开发卡为什么应该先做它？
- 它解除的是 benchmark、复权、执行数据还是 label 状态的哪个关键阻塞？
- 它是否依赖尚未确认的数据源？
- 它完成后是否能独立验收？
- 它是否会不小心触碰 production sorting、A/B/C、页面、Prism Edge 或 ML？

## 7. 拍板后的禁止事项确认

P1-A 拍板完成后，仍需逐条确认：

- 不修改生产排序。
- 不替换 A/B/C。
- 不做页面。
- 不做 Prism Edge 产品化。
- 不做 Expected 5D 默认展示。
- 不做 ML。
- 不把 research-only 或 conservative simulation 说成可执行回测。
- 不在 benchmark 不完整时输出 excess return。
- 不在复权或执行状态不明时输出 formal return。
