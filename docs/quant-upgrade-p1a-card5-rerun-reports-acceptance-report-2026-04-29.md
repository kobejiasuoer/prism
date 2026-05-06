# Prism 量化升级 P1-A Card 5 Rerun Reports 独立验收报告

Date: 2026-04-29
Reviewer: independent acceptance reviewer
Scope: P1-A Card 5 rerun Sprint 2 reports using hardened labels
Boundary:
- `docs/quant-upgrade-p1a-card4-label-hardening-acceptance-report-2026-04-29.md`
- `docs/quant-upgrade-p1a-hardening-acceptance-checklist-2026-04-28.md`
- `docs/quant-upgrade-p1a-decision-matrix-2026-04-28.md`

## 0. 验收结论

| 项目 | 结论 |
| --- | --- |
| Card 5 是否通过 | 通过 |
| 是否使用 hardened labels | 通过，三份报告均引用 hardened sidecar 与状态分布 |
| 是否允许 formal excess return | 不允许，未生成 |
| 是否允许 formal adjusted return | 不允许，未生成 |
| 是否允许 execution-realistic return | 不允许，未生成 |
| P1-A 是否可以阶段性收口 | 可以 |
| 推荐下一步 | 等外部数据源决策包，然后进入外部数据 POC |
| 是否允许进入生产/页面/Prism Edge | 不允许 |

Card 5 已用 `forward_return_labels_hardened.jsonl` 重新生成 Sprint 2 factor/backtest/health 报告，并把 hardened label 的 benchmark、excess、price adjustment、execution realism、research-only reasons 展示在报告中。所有结论仍为 report-only / research-only，没有 production-ready、formal excess、formal adjusted 或 execution-realistic 升级。

本次验收未修改 `packages/quant`，未修改 `data/quant/reports/*`，仅新增本验收报告。

## 一、交付物完整性

| 交付物 | 状态 | 验收意见 |
| --- | --- | --- |
| `packages/quant/evaluate_factors.py` | 存在 | 读取 hardened label summary，报告排除 `final_score` / `excess_return` / `execution_realistic_return` |
| `packages/quant/run_portfolio_backtest.py` | 存在 | 读取 hardened label summary，报告继续标记 `research_only_simulation` |
| `packages/quant/report_quant_health.py` | 存在 | 读取 hardened label summary，输出 not-production-ready health JSON/MD |
| `data/quant/reports/factor_evaluation_latest.md` | 已重新生成 | mtime 为 2026-04-29 21:40:27，晚于 Card 4 hardened labels |
| `data/quant/reports/portfolio_backtest_latest.md` | 已重新生成 | mtime 为 2026-04-29 21:40:27，晚于 Card 4 hardened labels |
| `data/quant/reports/quant_health_latest.md` | 已重新生成 | mtime 为 2026-04-29 21:40:28，晚于 Card 4 hardened labels |
| `data/quant/reports/quant_health_latest.json` | 存在，可解析 | JSON 可解析，`overall_status=report_only_hardened_not_production_ready` |
| `tests/test_quant_p1a_rerun_reports.py` | 存在 | 覆盖 hardened input、score/final_score、no formal excess、backtest、quant health |

补充说明：factor/backtest 的数值计算仍通过 `join_panel_labels(available_only=True)` 使用原始 available research labels 的 raw/net return，同时附带 hardened sidecar 做状态与 guardrails。由于 Card 4 hardened sidecar 未改变 raw/net return，这对本次 report-only rerun 可接受；后续若 hardened labels 成为唯一 label contract，建议直接从 sidecar join。

## 二、Hardened Labels 使用检查

三份 markdown 报告均明确包含：

| 项目 | Factor | Backtest | Quant Health |
| --- | --- | --- | --- |
| hardened labels input path | 通过 | 通过 | 通过 |
| hardened labels count = 11064 | 通过 | 通过 | 通过 |
| formal_label_ready count = 0 | 通过 | 通过 | 通过 |
| formal_execution_eligible count = 0 | 通过 | 通过 | 通过 |
| benchmark status distribution | 通过 | 通过 | 通过 |
| excess return status distribution | 通过 | 通过 | 通过 |
| price adjustment status distribution | 通过 | 通过 | 通过 |
| execution realism status distribution | 通过 | 通过 | 通过 |
| research_only_reason distribution | 通过 | 通过 | 通过 |

核心分布保持一致：

| 状态 | 分布 |
| --- | --- |
| Benchmark status | `market_benchmark_unavailable_internal_research_only_available`: 10848；`market_benchmark_unavailable`: 216 |
| Excess return status | `unavailable_market_benchmark_not_frozen`: 11064 |
| Price adjustment status | `unknown`: 11064 |
| Formal adjusted return status | `unavailable_adjustment_policy_missing_not_ready`: 11064 |
| Execution realism status | `not_ready_research_only_simulation_execution_data_missing`: 11064 |
| Formal label ready | 0 |
| Formal execution eligible | 0 |

## 三、Factor Evaluation 合规检查

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| `final_score` 仍禁用 | 通过 | 报告写明 `final_score` excluded；代码 `EXCLUDED_FIELDS` 包含 `final_score` |
| `score` 没有跨 lane 合并 | 通过 | `score` 只在 Raw/Source Only 中展示，报告写明 lane-scoped / score-kind-scoped |
| 没有 formal excess return | 通过 | 报告写明 benchmark 未冻结，no excess return calculated or claimed |
| positive-looking metric 仍标 research_only | 通过 | 报告写明 positive-looking raw/net metrics remain `research_only` |
| insufficient_sample 规则继续生效 | 通过 | bucket guardrails 和 tier monotonicity 均展示 `insufficient_sample` |

factor report 仍只做 report-only 因子观察，不改变生产排序、A/B/C、页面、Prism Edge 或 ML。

## 四、Backtest 合规检查

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| 仍是 `research_only_simulation` | 通过 | 每个结果 flags 含 `research_only_simulation`，解释区明确 every result is research-only |
| `portfolio_win_rate` 仍存在 | 通过 | Results 表展示 Portfolio win rate；测试也覆盖 `portfolio_win_rate` 字段 |
| no execution-realistic return | 通过 | 报告开头写明 not execution-realistic；解释区禁止 deployable/execution-realistic |
| no production-ready wording | 通过 | backtest report 未出现 production-ready 正向表述 |
| hardened label limitations 被展示 | 通过 | 报告有 `Hardened Label Limitations` 区块 |
| `formal_label_ready=false` 未用于 formal backtest 声称 | 通过 | 报告写明 no sample with `formal_label_ready=false` is used to claim formal/execution-realistic backtest |

backtest 仍只覆盖最小 research simulation；没有 broker execution ledger、停牌/涨跌停、failed order、partial fill 或 formal benchmark excess 支持。

## 五、Quant Health 合规检查

| 检查项 | 结论 | 证据 |
| --- | --- | --- |
| overall status 不是 production-ready | 通过 | `overall_status=report_only_hardened_not_production_ready` |
| benchmark availability 仍未 ready | 通过 | excess availability 全部 `unavailable_market_benchmark_not_frozen` |
| adjusted return availability 仍未 ready | 通过 | `adjusted_return_availability.status=not_ready` |
| execution realism 仍未 ready | 通过 | `execution_realism_availability.status=not_ready` |
| production blocking false | 通过 | `hard_gates.blocks_production=false` |
| sorting impact false | 通过 | `hard_gates.blocks_sorting=false` |
| A/B/C replacement false | 通过 | `hard_gates.replaces_abc=false` |
| production ready false | 通过 | `hard_gates.production_ready=false` |

Quant health markdown 同步展示 production blocking、sorting impact、A/B/C replacement、page requirement 均为 false，并写明没有 page、Prism Edge、Expected 5D frontend、theme state machine 或 ML work。

## 六、边界检查

| 边界 | 结论 | 证据 |
| --- | --- | --- |
| 没有改生产排序 | 通过 | 三份报告均保留 no production sorting / no sorting impact |
| 没有替换 A/B/C | 通过 | factor/backtest/health 均写明 no A/B/C replacement |
| 没有做页面 | 通过 | factor/health guardrails 明确 no page |
| 没有做 Prism Edge | 通过 | factor/health guardrails 明确 no Prism Edge |
| 没有做 Expected 5D 前端展示 | 通过 | quant health guardrails 明确 no Expected 5D frontend |
| 没有做 ML | 通过 | factor/health guardrails 明确 no ML |
| 没有把 internal benchmark 当 market benchmark | 通过 | internal benchmark 只在 hardened status 中作为 research-only internal；formal excess 仍 unavailable |
| 没有生成 formal excess return | 通过 | hardened labels `excess_return` 字段 0；报告 no excess return |
| 没有生成 formal adjusted return | 通过 | hardened labels `adjusted_return` 字段 0；adjusted availability not ready |
| 没有生成 execution-realistic return | 通过 | hardened labels `execution_realistic_return` 字段 0；execution realism not ready |

## 七、测试检查

未发现独立的第一个 AI 测试结果日志或测试报告文件；已读取 `tests/test_quant_p1a_rerun_reports.py` 作为自查测试依据。

pytest runner 状态：

- 命令：`python3 -m pytest tests/test_quant_p1a_rerun_reports.py -q -p no:cacheprovider`
- 结果：无法执行，当前 Python 环境无 `pytest` 模块。

只读手动 runner：

- 使用 `PYTHONPATH=packages python3 -B` 导入测试文件并逐个调用 `test_*` 函数。
- 结果：5 个测试函数全部通过。

覆盖情况：

| 测试要求 | 覆盖情况 |
| --- | --- |
| reports 使用 hardened labels input | 已覆盖 |
| `final_score` excluded / `score` lane-scoped | 已覆盖 |
| formal counts 0 / no formal excess | 已覆盖 |
| backtest research-only / win rate exists | 已覆盖 |
| quant health not production-ready | 已覆盖 |

手动通过的测试函数：

- `test_backtest_remains_research_only_and_win_rate_exists`
- `test_final_score_still_excluded_and_score_lane_scoped`
- `test_hardened_formal_counts_are_zero_and_no_formal_excess`
- `test_quant_health_not_production_ready`
- `test_reports_use_hardened_labels_input`

## 八、验收结论与下一步

结论：通过。

通过理由：

- Card 5 交付物完整，四份 latest reports 已重新生成，quant health JSON 可解析。
- 三份报告均显式引用 hardened labels，并展示 hardened status / research-only reason 分布。
- factor evaluation 仍禁用 `final_score`，`score` 仍 lane-scoped，positive-looking 指标仍为 research-only。
- backtest 仍为 `research_only_simulation`，保留 portfolio win rate，未声称 execution-realistic。
- quant health 明确 not production-ready，benchmark / adjusted return / execution realism 均 not ready。
- 未触碰生产排序、A/B/C、页面、Prism Edge、Expected 5D 或 ML。

必须修复的问题：

- 无 Card 5 阻塞修复项。

P1-A 是否可以阶段性收口：可以。

阶段性收口含义：

- P1-A 已完成内部可得数据的 manifest、policy freeze、execution availability、hardened labels sidecar 和 report-only rerun。
- P1-A 没有完成 formal benchmark、formal adjusted return 或 execution-realistic return。
- 因此 P1-A 可以作为“内部数据硬化阶段收口”，但不能进入生产排序或 shadow Prism Edge 的策略效果判断。

下一步建议：等外部数据源决策包，然后进入外部数据 POC。

理由：

- 当前所有阻塞项都指向外部或新增数据源：CSI500/HS300 frozen benchmark、qfq/adj factor/PIT 复权证明、停牌/涨跌停、order/fill/lot/participation 数据。
- 继续内部 execution hardening 只能更精细地标记 unavailable，无法解锁 formal label。
- 进入 shadow Prism Edge 预研可以做信息架构或流程演练，但不应做策略效果展示；若资源有限，应先完成外部数据 POC。
