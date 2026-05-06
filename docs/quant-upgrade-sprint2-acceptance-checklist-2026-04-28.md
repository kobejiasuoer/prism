# Prism 量化升级 Sprint 2 验收清单

Date: 2026-04-28
Role: independent acceptance reviewer
Scope: Sprint 2 factor evaluation, minimal backtest, report-only quant health
Source:
- `docs/quant-upgrade-p0-review-revision-2026-04-28.md`
- `docs/quant-upgrade-p0-execution-flow-2026-04-28.md`

## 0. 评审边界

本清单只用于 Sprint 2 验收评审准备，不开发业务逻辑，不生成或覆盖 Sprint 2 报告。

严格边界：

- 不修改 `packages/quant`。
- 不修改或覆盖 `data/quant/reports/factor_evaluation_latest.md`。
- 不修改或覆盖 `data/quant/reports/portfolio_backtest_latest.md`。
- 不修改或覆盖 `data/quant/reports/quant_health_latest.md`。
- 不生成或覆盖 `data/quant/reports/quant_health_latest.json`。
- 不做页面、Prism Edge、Expected 5D 前端展示、生产排序、A/B/C 替换、ML。
- 只审查 report-only / research-only 证据是否足以支持是否进入 P1。

验收结论只允许三类：

| 结论 | 含义 |
| --- | --- |
| 通过 | Sprint 2 产物完整，规则合规，且所有量化结论均保持 report-only / research-only。 |
| 有条件通过 | 产物完整但存在数据覆盖、样本数、benchmark 或执行数据缺口；可以进入 P1 的低风险预研，但不能产品化。 |
| 不通过 | 产物缺失、规则越界、正式评估口径污染，或任何产物影响生产排序、页面、A/B/C、Prism Edge、ML。 |

## 1. Sprint 2 交付物验收清单

### 1.1 报告产物

| 交付物 | 验收项 | 通过标准 | 结论 |
| --- | --- | --- | --- |
| `data/quant/reports/factor_evaluation_latest.md` | 文件存在且时间戳、输入范围、样本量、source lane 分布清楚 | 明确 `report-only`；只使用 PIT-clean 且 label available 的研究样本；无生产排序结论 | 待审 |
| `data/quant/reports/factor_evaluation_latest.md` | 因子覆盖完整 | 至少覆盖 `ai_priority_score`、`ai_best_score`、`scan_capital_score`、`scan_technical_score`、tier monotonicity、execution gate、AI 二筛、midday confirmed/downgrade | 待审 |
| `data/quant/reports/factor_evaluation_latest.md` | 样本数保护 | 任一 bucket 或组合样本数 `<30` 时标记 `insufficient_sample`，且不能给正向结论 | 待审 |
| `data/quant/reports/portfolio_backtest_latest.md` | 文件存在且策略范围清楚 | 至少覆盖 `top_n_raw_score` 与 `gate_filtered_top_n`；不声称 execution-realistic | 待审 |
| `data/quant/reports/portfolio_backtest_latest.md` | 回测维度完整 | 覆盖 `next_open` / `next_close`、1/3/5/10 日窗口、成本、回撤、换手、胜率或胜率缺口说明 | 待审 |
| `data/quant/reports/portfolio_backtest_latest.md` | 研究限制标记 | 执行数据缺失时必须标记 `research_only_simulation`，并列出 limit/suspend/failed order/partial fill 等缺口 | 待审 |
| `data/quant/reports/quant_health_latest.md` | 文件存在且只 report-only | 明确不阻断生产、不改排序、不替换 A/B/C、不要求页面变更 | 待审 |
| `data/quant/reports/quant_health_latest.json` | JSON 可解析且 schema 清楚 | 包含 `production_impact: none`、hard gates 不阻断生产、guardrails 完整 | 待审 |

### 1.2 脚本产物

| 交付物 | 验收项 | 通过标准 | 结论 |
| --- | --- | --- | --- |
| `packages/quant/evaluate_factors.py` | 只读输入，写报告逻辑隔离 | build 函数可被测试调用；正式因子字段白名单清楚；不得把 `final_score` 纳入正式评估 | 待审 |
| `packages/quant/evaluate_factors.py` | lane 语义隔离 | AI 分数字段只在 AI lane 内比较；scan 分数字段只在 scan candidate 内比较；`score` 仅 raw/source diagnostics | 待审 |
| `packages/quant/run_portfolio_backtest.py` | 最小回测策略明确 | 实现 `top_n_raw_score` 与 `gate_filtered_top_n`；gate 只按 batch/context 解释 | 待审 |
| `packages/quant/run_portfolio_backtest.py` | 成本与执行假设保守 | 扣除配置成本；缺 execution-realistic 数据时全部标记 research-only | 待审 |
| `packages/quant/report_quant_health.py` | 健康度只汇总证据 | 读取 panel/labels/factor/backtest 状态；不写生产状态、不阻断排序、不触发页面需求 | 待审 |
| `packages/quant/report_quant_health.py` | JSON/Markdown 一致 | JSON 与 Markdown 的 production impact、guardrails、benchmark/execution 缺口一致 | 待审 |

### 1.3 测试产物

| 交付物 | 验收项 | 通过标准 | 结论 |
| --- | --- | --- | --- |
| `tests/test_quant_sprint2.py` 或等效测试 | 规则保护测试 | 覆盖 `final_score` 禁用、`score` 不跨 lane、gate batch/context、benchmark unavailable 不算 excess return | 待审 |
| `tests/test_quant_sprint2.py` 或等效测试 | 研究限制测试 | 覆盖 execution missing -> `research_only_simulation`、样本数 `<30` -> `insufficient_sample` | 待审 |
| `tests/test_quant_sprint2.py` 或等效测试 | 产物存在性测试 | 检查 factor/backtest/health 报告存在且 report-only；不要求测试生成或覆盖产物 | 待审 |
| Sprint 1 相关测试 | 输入契约未被破坏 | panel、eligible universe、stage ledger、forward labels 的 Sprint 1 smoke 仍可通过 | 待审 |

## 2. 规则合规检查清单

| 规则 | 检查方法 | 必须看到的证据 | 失败条件 |
| --- | --- | --- | --- |
| `final_score` 禁用 | 查 factor report、factor build result、测试断言 | `final_score` 在 excluded/raw-only 列表中，未进入 formal numeric/group factors | `final_score` 被正式评估、排名或用于回测选股 |
| `score` 没有跨 lane 合并 | 查 panel 字段、factor report raw/source coverage | `score_source_lane == source_lane`；有 `score_kind`；`score` 不进入 formal factors | 把 AI、scan、watchlist 等不同语义的 `score` 合并比较 |
| gate 只作为 batch/context 字段 | 查 panel `execution_gate_scope` 与 factor/backtest 文案 | `execution_gate_scope=batch_context`；报告说明 gate 非 candidate-native | 把 gate 当作个股原生因子或硬阻断生产 |
| benchmark unavailable 时不输出 excess return | 查 labels、factor report、health JSON | `benchmark_status=benchmark_unavailable` 时没有 `excess_return` 字段或结论；只标记 deferred | 缺 benchmark 仍计算或宣称 excess return/alpha |
| `execution_data_missing` 时标记 `research_only_simulation` | 查 backtest report 与 health JSON | backtest flags 包含 `research_only_simulation`，并列出 suspend/limit/failed order/partial fill 缺口 | 把缺执行数据的结果称为 execution-realistic 或可交易 |
| 样本数 `<30` 标记 `insufficient_sample` | 查 factor bucket、tier、backtest position observations | 每个不足样本组合均标记 `insufficient_sample`，结论写 no positive conclusion | 小样本 bucket 输出正向因子结论 |
| 2026 artifact 没有进入正式 label 评估 | 查 formal evaluation input scope 与 source artifact/date | 2026 recent artifacts 只能用于 coverage/context 或 lineage 审计，不进入正式 label 评估结论 | 任一 2026 artifact 参与正式因子、tier、AI 二筛、midday 或回测结论 |
| 未改生产排序、A/B/C、页面、Prism Edge、ML | 查 git diff、health guardrails、报告文案 | `production_impact=none`；hard gates 不阻断；无页面/Edge/ML/排序文件改动 | 任一 Sprint 2 产物改变生产排序、A/B/C、前端页面、Prism Edge 或 ML |

## 3. 因子评估审查模板

每个因子审查时都要记录：输入样本、source lane、字段语义、PIT 状态、label 状态、样本数、1/3/5/10 日 raw/net 表现、是否有 benchmark/excess 缺口、是否只 report-only。

| 审查对象 | 审查问题 | 通过标准 | 记录 |
| --- | --- | --- | --- |
| `ai_priority_score` | 是否只在 AI lane 内评估 | 只比较 `research_backfill_ai_history` 或等效 AI lane；不与 scan/watchlist score 混排 | 待填 |
| `ai_priority_score` | 是否有跨窗口稳定性 | 1/3/5/10 日均有样本状态；小样本不作正向结论 | 待填 |
| `ai_best_score` | 是否语义清楚 | 说明它是 AI lane 的 best underlying strategy score，不等同 `final_score` | 待填 |
| `ai_best_score` | 是否避免重复解释 | 与 `ai_priority_score` 的关系写清楚，避免把相关字段当独立证据重复计分 | 待填 |
| `scan_capital_score` | 是否来自 raw scan capital | 只在 scan candidate pool 内评估；注明 capital flow normalization 是否充分 | 待填 |
| `scan_capital_score` | 是否受市场环境影响 | 报告至少提示 market regime / turnover / liquidity 风险，P0 不做强中性化结论 | 待填 |
| `scan_technical_score` | 是否来自 raw scan technical | 只在 scan candidate pool 内评估；不与 AI 分数合并排序 | 待填 |
| `scan_technical_score` | 是否有成本后净收益 | 关注 net return，不以 raw return 单独作结论 | 待填 |
| tier monotonicity | A/B/C 是否单调 | A、B、C bucket 均满足样本阈值后才判断；否则 `insufficient_sample` | 待填 |
| tier monotonicity | 是否替换生产 A/B/C | 报告必须明确不替换现有 A/B/C，不改用户可见分层 | 待填 |
| execution gate | gate off/limited/on 表现是否拆分 | gate 只作为 batch/context；拆分收益、回撤、样本数；不作为硬阻断 | 待填 |
| execution gate | gate_filtered 逻辑是否保守 | gate off 不开新模拟仓位；limited 降低仓位；仍 research-only | 待填 |
| AI 二筛 | 是否改善 scan 原始候选 | 比较必须以可见 scan pool 为锚；记录 same-day code overlap 与选择偏差 | 待填 |
| AI 二筛 | 是否避免 survivorship/selection bias | 未能追溯 scan -> AI lineage 的样本只做 report-only，不作生产选择 claim | 待填 |
| midday confirmed/downgrade | confirmed/downgrade 是否有 label | 没有足够 PIT-clean labeled 样本时只 coverage-only | 待填 |
| midday confirmed/downgrade | 是否拆分 confirmed/downgraded/fresh | stage counts 清楚；不能只展示对结论有利的组 | 待填 |

因子评估最低通过线：

- formal factors 只包含语义清楚、lane 清楚、PIT/label 可用的字段。
- `final_score`、跨 lane `score`、`strategy_bucket`、`excess_return`、execution-realistic return 不进入正式因子结论。
- 所有结论都带 `report-only` 或 `research-only` 约束。
- 任一组合样本数不足时不能写“有效”“显著”“可上线”等措辞。

## 4. 最小回测审查模板

| 审查对象 | 审查问题 | 通过标准 | 记录 |
| --- | --- | --- | --- |
| `top_n_raw_score` | 是否只用 raw scan score | 只在 scan candidate pool 内按 raw scan composite score 排序；不混入 AI score 或 final_score | 待填 |
| `top_n_raw_score` | top N 规则是否来自配置 | max positions、单票权重、窗口、成本来自 config 或报告明示，不在报告里隐含 | 待填 |
| `gate_filtered_top_n` | gate 是否只过滤 batch/context | gate off/limited/on 的处理清楚；不改变生产 gate | 待填 |
| `gate_filtered_top_n` | 是否和 raw top N 可比 | 同一 entry、窗口、成本、样本范围下对比 | 待填 |
| `next_open` vs `next_close` | entry model 是否双口径 | 两者均输出；差异用于判断执行敏感性，不择优展示 | 待填 |
| 1/3/5/10 日窗口 | 是否完整覆盖 | 每个策略 x entry x window 有样本数、状态、raw/net return | 待填 |
| 成本影响 | 是否扣除成本 | 展示 raw 与 net 差异、平均成本或成本配置；不得只用 raw return 宣称有效 | 待填 |
| 回撤 | 是否计算 drawdown | 至少有净值序列或净收益序列上的 max drawdown；说明非 execution-realistic | 待填 |
| 换手 | 是否计算 turnover | 至少有近似换手；说明是否一边换手、目标权重、调仓频率 | 待填 |
| 胜率 | 是否输出 win rate 或说明缺口 | 若未输出组合胜率，需说明在 factor bucket 或 backtest 层的替代指标与缺口 | 待填 |
| `research_only_simulation` | 是否强制标记 | 缺 suspend、limit up/down、failed order、partial fill、复权等数据时，所有结果都必须 research-only | 待填 |
| benchmark/excess | 是否避免 alpha 宣称 | benchmark unavailable 时不输出 excess return，不写 alpha/outperformance | 待填 |

最小回测最低通过线：

- 输出 `top_n_raw_score` 与 `gate_filtered_top_n`。
- 覆盖 `next_open`、`next_close` 与 1/3/5/10 日窗口。
- 扣除成本，并清楚展示成本影响。
- 展示回撤、换手、胜率或胜率缺口说明。
- 所有执行数据缺口导致的结果必须标记 `research_only_simulation`。
- 不能把最小回测描述为可交易、可上线、可替代生产排序。

## 5. Sprint 2 完成后的决策树

```text
Sprint 2 产物齐全？
  否 -> 不通过：补齐 factor/backtest/health/scripts/tests。
  是 ->
    是否触碰生产排序、A/B/C、页面、Prism Edge、ML？
      是 -> 不通过：回滚越界范围，重新评审。
      否 ->
        规则合规是否全部通过？
          否 -> 不通过或有条件通过：先修 final_score/score/gate/benchmark/execution/sample 规则。
          是 ->
            benchmark、涨跌停、停牌、复权、failed order 是否仍缺失？
              是 -> 有条件通过：只能进入 P1 数据补强或 shadow 预研，不能产品化。
              否 ->
                样本量是否足够，且 1/3/5/10 日、next_open/next_close、成本后结果稳定？
                  否 -> 有条件通过：扩大样本、补 lineage、做 walk-forward。
                  是 ->
                    因子、tier、gate、AI 二筛、midday 是否至少有两个样本外窗口支持？
                      否 -> 有条件通过：P1 只能继续 shadow，不得 hard gate。
                      是 -> 可以进入 P1：仍需 shadow、监控、回滚开关和单独产品评审。
```

### 5.1 可以进入 P1 的条件

- Sprint 2 所有交付物存在，JSON/Markdown 口径一致。
- 所有规则合规检查通过。
- `quant_health` 仍是 report-only，`production_impact=none`。
- benchmark、复权、涨跌停、停牌、T+1、成本、failed order/partial fill 的数据来源与缺口被明确处理。
- factor 与 backtest 结果在成本后、双 entry、多个窗口下没有明显口径冲突。
- P1 范围限定为 shadow、信息架构或数据补强，不直接改生产动作。

### 5.2 只能有条件进入 P1 的情形

- 报告完整，但 benchmark unavailable，不能评估 excess return。
- 执行数据缺失，回测只能是 `research_only_simulation`。
- 关键 bucket 样本数不足，tier/gate/midday 只能 coverage-only。
- AI 二筛 lineage 不完整，只能做 scan-pool anchored 对照。
- 因子方向存在但窗口不稳定，需要 walk-forward 或 block bootstrap/Newey-West 状态补强。
- 这种情况下 P1 只能做数据补齐、shadow report、页面信息架构草案，不得上线 Prism Edge 或改变排序。

### 5.3 必须回头补数据或修规则的情形

- `final_score` 被纳入正式评估。
- `score` 跨 lane 合并或被当成统一分数。
- gate 被当成 candidate-native 字段或 hard gate。
- benchmark unavailable 仍输出 excess return。
- execution missing 仍称 execution-realistic。
- 样本数 `<30` 的 bucket 给出正向结论。
- 2026 recent artifact 进入正式 label 评估结论。
- 任一代码或报告改动影响生产排序、A/B/C、页面、Prism Edge、ML。

## 6. P1 候选任务预案

以下只列建议，不写代码。

| 候选任务 | 当前判断 | 建议 |
| --- | --- | --- |
| shadow Prism Edge | 暂不应直接做产品化；可作为 P1 shadow 预研 | 只有在 Sprint 2 规则全部合规、样本和执行缺口清楚后，做离线 shadow score，不进生产排序、不进默认页面动作 |
| 页面信息架构 | 可以做草案，不做视觉与真实接入 | 先定义 Command Center、Discovery、Stock Detail、Portfolio、Review 中 quant status/证据层级/缺口提示的位置；不展示 Expected 5D 默认值 |
| benchmark 补强 | 优先级高 | 先冻结 CSI500 主 benchmark，HS300 与 equal-weight pool 作为辅；补齐后才能评价 excess return/alpha |
| 涨跌停 / 停牌 / failed order / partial fill | 优先级高 | 在任何 execution-realistic 或 hard gate 讨论前补齐；否则回测继续 `research_only_simulation` |
| 复权与交易日历 | 优先级高 | 明确复权口径、交易日历、T+1、next open/next close 可得性，避免 label 漏看不可交易日 |
| score/tier/gate 修规则 | 若 Sprint 2 任一合规项失败则最高优先级 | 先修 `final_score` 禁用、`score` lane scoped、gate batch/context、tier 不替换生产 A/B/C，再谈 P1 |
| walk-forward / block bootstrap / Newey-West | 中高优先级 | 用于处理 3/5/10 日重叠收益和多重检验风险；P1 shadow 前应补状态说明 |
| shadow health monitor | 可作为低风险 P1 | 只读生成 health trend，不阻断生产，不改页面主流程；需要稳定 schema 和历史可比性 |
