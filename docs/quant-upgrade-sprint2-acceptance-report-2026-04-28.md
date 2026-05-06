# Prism 量化升级 Sprint 2 独立验收报告

Date: 2026-04-28
Reviewer: independent acceptance reviewer
Checklist: `docs/quant-upgrade-sprint2-acceptance-checklist-2026-04-28.md`
Scope: Sprint 2 factor evaluation, minimal backtest, report-only quant health

## 0. 验收结论

| 项目 | 结论 |
| --- | --- |
| 是否通过 Sprint 2 | 有条件通过 |
| 是否允许进入 P1 | 有条件允许 |
| P1 允许范围 | 数据补强、shadow-only 预研、页面信息架构草案 |
| P1 禁止范围 | 生产排序、A/B/C 替换、页面真实接入 Prism Edge、Expected 5D 默认展示、ML、hard gate |

Sprint 2 交付物完整，硬门槛未发现违规：`final_score` 未进入正式评估，`score` 未跨 lane 合并，benchmark unavailable 时未输出 excess return，执行数据缺失时回测标记 `research_only_simulation`，`insufficient_sample` 未给正面结论，quant health 未阻断生产。

但当前仍存在 P1 前必须正视的数据和解释限制：benchmark 全部 unavailable，复权/停牌/涨跌停/failed order/partial fill 缺失，tier monotonicity 和 midday validation 仍不足样本，回测仍是 research-only simulation。因此不能进入产品化 P1，只能有条件进入数据补强和 shadow 预研。

## 1. 检查范围与方法

已读取并检查：

| 文件 | 检查结果 |
| --- | --- |
| `packages/quant/evaluate_factors.py` | 已检查 formal factor 白名单、excluded fields、lane 过滤、gate scope、报告渲染 guardrails |
| `packages/quant/run_portfolio_backtest.py` | 已检查策略、entry/window、成本、gate 逻辑、research-only flags、报告渲染 |
| `packages/quant/report_quant_health.py` | 已检查 health 汇总、production impact、hard gates、guardrails |
| `tests/test_quant_sprint2.py` | 已检查开发者自查断言覆盖 |
| `data/quant/reports/factor_evaluation_latest.md` | 已检查因子报告正文和 guardrails |
| `data/quant/reports/portfolio_backtest_latest.md` | 已检查回测报告正文和 guardrails |
| `data/quant/reports/quant_health_latest.md` | 已检查 health Markdown |
| `data/quant/reports/quant_health_latest.json` | 已检查 health JSON |

测试执行说明：

- `pytest` 与 `python3 -m pytest` 均因当前环境未安装 `pytest` 无法执行。
- 已使用只读断言脚本导入 `build_factor_evaluation()`、`run_backtest()`、`build_quant_health()` 并检查关键门槛；该脚本未调用任何 `write_*` 函数，未覆盖 `data/quant/reports/*`。
- 只读断言结果：`final_score_formal=false`，`score_formal=false`，`score_lane_mismatch=0`，`gate_scope_mismatch=0`，`labels_with_excess_return=0`，`backtest_missing_research_only_flag=0`。

## 2. 交付物完整性检查

| 交付物 | 状态 | 验收意见 |
| --- | --- | --- |
| `factor_evaluation_latest.md` | 通过 | 文件存在，包含 generated timestamp、样本量、source lane、formal numeric factors、group factors、tier monotonicity、execution gate、AI screening、midday validation、raw/source only 和 guardrails |
| `portfolio_backtest_latest.md` | 通过，有小缺口 | 文件存在，覆盖 `top_n_raw_score`、`gate_filtered_top_n`、`next_open`、`next_close`、1/3/5/10 日窗口、成本、回撤、换手、research-only flags；报告表格未直接展示组合胜率，需在 P1 前补列或明确说明 |
| `quant_health_latest.md` | 通过 | 文件存在，明确 report-only、不阻断生产、无排序/A/B/C/页面/Prism Edge/ML 影响 |
| `quant_health_latest.json` | 通过 | JSON 可解析，包含 `production_impact: none`、hard gates 全 false、benchmark/execution 缺口和 guardrails |
| `evaluate_factors.py` | 通过 | formal numeric factors 限定为 AI lane 分数和 scan lane 分数；`final_score`、`excess_return` 等进入 excluded fields |
| `run_portfolio_backtest.py` | 通过 | 最小回测策略清楚，所有 result 带 `research_only_simulation` 等 flags，不声称 execution-realistic |
| `report_quant_health.py` | 通过 | 汇总 panel/label/factor/backtest 状态，hard gates 不阻断生产 |
| `tests/test_quant_sprint2.py` | 通过，有环境限制 | 自查断言覆盖硬门槛；当前环境缺 `pytest`，未能以 pytest runner 执行 |

## 3. 规则合规检查

| 硬门槛 | 结论 | 证据 |
| --- | --- | --- |
| `final_score` 必须禁用 | 通过 | `evaluate_factors.py` 将 `final_score` 放入 `EXCLUDED_FIELDS`；factor report 写明 `final_score` excluded；只读断言显示 `final_score_formal=false` |
| `score` 不能跨 lane 合并 | 通过 | `score` 只在 raw/source coverage 中出现；panel 中 scored rows 检查为 1998 行，`score_lane_mismatch=0`，`score_kind_missing=0` |
| gate 只作为 batch/context | 通过 | `evaluate_group_factor()` 过滤 `execution_gate_scope != batch_context`；panel 检查 gated rows 3472，`gate_scope_mismatch=0` |
| benchmark unavailable 不能输出 excess return | 通过 | 11064 条 labels 均为 `benchmark_unavailable`；`labels_with_excess_return=0`；reports 均写明 no excess return |
| `execution_data_missing` 必须标 `research_only_simulation` | 通过 | backtest 16 个结果均带 `research_only_simulation`；health JSON 中 `research_only_simulation: 16` |
| `insufficient_sample` 不能给正面结论 | 通过 | `MIN_BUCKET_SAMPLE=30`；tier monotonicity 全部 `insufficient_sample`；factor report 写明 no positive conclusion |
| 2026 artifact 不进入正式 label 评估 | 通过 | labels 的 `label_scope` 仅为 `2024_research_backfill_only`，label trade years 仅为 2024 |
| 不能改生产排序、A/B/C、页面、Prism Edge、ML | 通过，按本次验收范围 | Reviewed Sprint 2 artifacts 只输出 report-only/research-only；health JSON `production_impact=none`，hard gates 全 false，guardrails 包含 no sorting/A-B-C/page/Prism Edge/ML |

说明：当前全仓库工作树存在大量与 Sprint 2 验收范围无关的既有改动和未跟踪文件。本报告只对用户指定的 Sprint 2 产物做独立验收；若其中任何 UI、生产排序或 Prism Edge 改动被开发者声称属于 Sprint 2，则应另行判定为越界。

## 4. 因子评估是否被过度解读

结论：未发现过度解读，但仍只能作为 report-only evidence。

检查结果：

- `ai_priority_score` 和 `ai_best_score` 只在 AI lane 内作为 formal numeric factors，报告中没有把它们推广为生产排序。
- `scan_capital_score` 和 `scan_technical_score` 只来自 scan candidate pool，未和 AI score 混排。
- `score` 明确保留为 raw/source only，未晋升为 formal factor。
- tier group 本身显示 `research_only`，但 tier monotonicity 明确为 `insufficient_sample`；报告未声称 A/B/C 单调有效或可替换生产 tiers。
- AI 二筛报告为 scan-pool anchored comparison，保留 selection-bias guardrail；没有生产选择 claim。
- midday validation 为 `insufficient_sample`，且 stage counts 为空；报告写明 coverage-only。

保留意见：

- factor report 里展示了多个 net mean 点估计，但缺少 walk-forward、Newey-West、block bootstrap 或多重检验控制状态。当前文案已用 report-only guardrails 兜住，P1 前不应把这些点估计升级成有效性结论。
- `tier` 在 group factors 表中为 `research_only`，但 monotonicity 为 `insufficient_sample`。这不是硬门槛失败，不过 P1 报告最好把 tier 的“可分组观察”和“单调性证据不足”拆得更醒目。

## 5. 回测是否正确标记 `research_only_simulation`

结论：正确标记。

检查结果：

- `portfolio_backtest_latest.md` 16 行结果全部显示 `research_only`，flags 中均包含 `research_only_simulation`。
- `run_portfolio_backtest.py` 的 `RESEARCH_ONLY_BACKTEST_FLAGS` 包含 `research_only_simulation`、`benchmark_unavailable`、`adjustment_policy_unknown`、`suspend_status_unknown`、`limit_up_down_status_unknown`、`failed_order_unavailable`、`partial_fill_unavailable`、`not_production_sorting`。
- `quant_health_latest.json` 汇总 16 个 backtest 结果均带 `research_only_simulation`。
- 报告明确写明缺 suspend、limit up/down、failed order、partial fill、adjustment data，因此不是 execution-realistic backtest。

回测缺口：

- 组合胜率未在 Markdown 表格中直接展示。`summary_stats()` 能计算 win rate，factor 的 group table 也有 win rate，但 minimal backtest table 当前没有 win rate 列。P1 前应补上，或在报告中明确胜率暂未纳入组合层验收。
- 回撤数值很大，尤其 10 日窗口接近 -78%，但报告没有过度包装为可交易结论；P1 需要解释回撤口径、重叠持仓和复利序列假设。

## 6. Quant Health 是否误导成 production-ready

结论：未误导成 production-ready。

证据：

- Markdown scope 写明 report-only，且 does not block or alter production。
- JSON `production_impact` 为 `none`。
- JSON `hard_gates.blocks_production=false`、`blocks_sorting=false`、`replaces_abc=false`、`requires_page_change=false`。
- Guardrails 包含 `no_production_sorting`、`no_abc_replacement`、`no_page`、`no_prism_edge`、`no_ml`。
- Backtest status 为 `research_only_simulation`，execution data availability 为 `missing_for_execution_realistic_backtest`。

保留意见：

- `overall_status: report_only_research_ready` 可以接受，但容易被非评审读者误读为“已经准备生产化”。P1 前建议改成更硬的表达，例如 `report_only_evidence_available_execution_not_ready`，或者在 Markdown summary 旁补一句“not production-ready”。

## 7. 与开发者自查结论是否一致

结论：基本一致。

本次未找到独立的开发者自查 Markdown/JSON 文档；可核对的自查载体是 `tests/test_quant_sprint2.py` 和三份 latest reports。独立验收结论与这些自查断言一致：

- `final_score` 不进入 formal factors。
- `score` 不跨 lane 合并。
- gate 只使用 batch/context。
- benchmark unavailable 时没有 excess return。
- execution missing 强制 research-only backtest。
- insufficient sample 不给正面结论。
- Sprint 2 reports 保持 report-only，health 不阻断生产。

差异或补充：

- 开发者测试未覆盖“组合回测报告必须直接展示胜率”这一 checklist 细项；独立验收将其列为 P1 前小修。
- 开发者测试未显式覆盖 2026 artifact 不进入正式 label 评估；独立只读检查确认当前 labels 仅使用 2024 research backfill。

## 8. 是否通过 Sprint 2

结论：有条件通过。

通过理由：

- 交付物完整。
- 硬门槛全部通过。
- 报告没有把因子、tier、AI 二筛、midday、backtest 或 health 误导成 production-ready。
- 所有量化结果均处在 report-only / research-only / research-only simulation 边界内。

条件限制：

- benchmark 全部 unavailable，不能评价 excess return/alpha。
- execution-realistic 必需数据缺失，不能宣称可交易。
- tier monotonicity 与 midday validation 仍不足以形成正面证据。
- 回测报告需补组合胜率或显式说明缺口。

## 9. 是否允许进入 P1

结论：有条件允许。

允许进入的 P1 类型：

- benchmark、复权、交易日历、涨跌停、停牌、failed order、partial fill 数据补强。
- shadow-only quant health trend 或 shadow Prism Edge 离线草案。
- 页面信息架构草案，前提是不接真实页面、不展示默认 Expected 5D、不影响用户动作。
- walk-forward、Newey-West、block bootstrap、多重检验控制和样本外验证。

不允许进入的 P1 类型：

- 生产排序接入。
- A/B/C 替换。
- 页面真实接入 Prism Edge 或 Expected 5D 默认展示。
- hard gate 阻断生产。
- ML 模型或复杂题材状态机。

## 10. 进入 P1 前必须修复的问题

| 优先级 | 必修项 | 原因 |
| --- | --- | --- |
| P0 | 冻结 benchmark 数据与口径 | 当前全部 `benchmark_unavailable`，不能评价 excess return 或 alpha |
| P0 | 补齐涨跌停、停牌、复权、failed order、partial fill | 当前回测只能是 `research_only_simulation`，不能 execution-realistic |
| P0 | 保持 `final_score` 禁用、`score` lane-scoped、gate batch/context | 这些是继续进入 P1 的硬门槛，不能在 P1 放松 |
| P1a | 回测报告补组合胜率或缺口说明 | checklist 要求回撤、换手、胜率；当前 Markdown 已有回撤/换手，胜率缺展示 |
| P1a | tier 报告拆清楚 group observation 与 monotonicity evidence | 避免把 `tier` group factor 的 research-only 状态误读为 tier 单调性成立 |
| P1a | 对 3/5/10 日重叠收益补 Newey-West、block bootstrap 或 walk-forward 状态 | 降低重叠收益和多重检验导致的假阳性风险 |
| P1a | 明确 health 的 not production-ready 文案 | 避免 `report_only_research_ready` 被误读成上线准备完成 |

## 11. P1 推荐优先级

| 优先级 | 推荐任务 | 建议 |
| --- | --- | --- |
| 1 | benchmark / excess return 基础设施 | 先冻结 CSI500 主 benchmark，HS300 和 equal-weight pool 作为辅；补齐后再讨论 alpha |
| 2 | 执行数据硬化 | 优先补复权、交易日历、涨跌停、停牌、failed order、partial fill，再重跑 label/backtest |
| 3 | score/tier/gate 规则固化 | 把 `final_score` 禁用、`score` lane scoped、gate batch/context 写入 P1 契约和测试 |
| 4 | 回测报告增强 | 补组合胜率、回撤口径、重叠窗口统计状态、样本外切分 |
| 5 | shadow quant health trend | 只读生成趋势报告，不阻断生产，不改排序 |
| 6 | shadow Prism Edge 离线预研 | 只能 offline/shadow，不接页面默认动作，不进生产排序 |
| 7 | 页面信息架构草案 | 可以设计 quant status 和证据层级位置，但不做视觉、不接真实 Prism Edge |
