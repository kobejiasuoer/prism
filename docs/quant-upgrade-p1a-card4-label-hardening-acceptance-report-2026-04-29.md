# Prism 量化升级 P1-A Card 4 Label Hardening 独立验收报告

Date: 2026-04-29
Reviewer: independent acceptance reviewer
Scope: P1-A Card 4 forward labels upgrade / label hardening sidecar
Boundary:
- `docs/quant-upgrade-p1a-hardening-acceptance-checklist-2026-04-28.md`
- `docs/quant-upgrade-p1a-decision-matrix-2026-04-28.md`
- `docs/quant-upgrade-p1a-card1-benchmark-acceptance-report-2026-04-28.md`
- `docs/quant-upgrade-p1a-card2-adjusted-price-acceptance-report-2026-04-28.md`
- `docs/quant-upgrade-p1a-card3-execution-flags-acceptance-report-2026-04-29.md`

## 0. 验收结论

| 项目 | 结论 |
| --- | --- |
| Card 4 是否通过 | 通过 |
| 是否覆盖原始 forward labels | 否 |
| 是否允许 formal label | 不允许，全部 `formal_label_ready=false` |
| 是否允许 execution-realistic return | 不允许 |
| 是否允许 formal market excess return | 不允许 |
| 是否允许进入 P1-A Card 5 | 允许 |
| 推荐下一张卡 | Rerun Sprint 2 reports using hardened labels |
| 是否允许进入生产/页面/Prism Edge | 不允许 |

Card 4 完成的是 hardened label sidecar：它把 Card 1 benchmark、Card 2 adjusted price policy、Card 3 execution availability 的状态合并到 `forward_return_labels_hardened.jsonl`，同时保留所有 research-only / unavailable / deferred 降级原因。它没有覆盖原始 `forward_return_labels.jsonl`，没有生成 formal adjusted return、formal excess return 或 execution-realistic return。

本次验收未修改 `packages/quant`，未修改 `data/quant/labels/*`，未覆盖 `data/quant/reports/*`，仅新增本验收报告。

## 一、交付物完整性

| 交付物 | 状态 | 验收意见 |
| --- | --- | --- |
| `packages/quant/upgrade_forward_labels.py` | 存在 | 包含 sidecar 生成、source hash、status 合并和 report 渲染逻辑；验收时未调用写出函数或 CLI |
| `packages/quant/label_hardening.py` | 不存在 | 可接受；Card 4 使用 `upgrade_forward_labels.py` 承载实现 |
| `data/quant/labels/forward_return_labels_hardened.jsonl` | 存在，可解析 | 11064 行，逐行 JSON 可解析 |
| `data/quant/reports/label_hardening_latest.md` | 存在 | 明确 sidecar scope、不覆盖原始 labels、不生成 formal/execution-ready 结论 |
| `tests/test_quant_p1a_label_hardening.py` | 存在 | 覆盖行数、原始 labels 未覆盖、formal 禁止、benchmark/adjustment/execution 降级 |

只读结构校验摘要：

| 检查项 | 结果 |
| --- | --- |
| source labels | 11064 |
| hardened labels | 11064 |
| source/hardened label id 集合 | 一致 |
| hardened JSONL required fields | 无缺失 |
| `source_label_hash` mismatch | 0 |
| 原始 labels 中 hardening fields | 0 |
| hardened labels with `formal_label_ready=true` | 0 |
| hardened labels with `formal_execution_eligible=true` | 0 |

## 二、Hardened Label 字段检查

对 11064 行 hardened labels 全量检查，以下字段均存在：

| 字段 | 结论 |
| --- | --- |
| `label_id` | 通过 |
| `panel_row_id` | 通过 |
| `trade_date` | 通过 |
| `code` | 通过 |
| `entry_model` | 通过 |
| `holding_window_days` | 通过 |
| `raw_return` | 通过，保留原始 raw return；246 行原始 unavailable label 仍记录 research-only reason |
| `net_return` | 通过 |
| `benchmark_status` | 通过 |
| `benchmark_id` 或 `benchmark_reference` | 通过，二者均存在 |
| `benchmark_return_status` | 通过 |
| `excess_return_status` | 通过 |
| `price_adjustment_status` | 通过 |
| `adjustment_policy` | 通过 |
| `formal_adjusted_return_status` | 通过 |
| `suspend_status` | 通过 |
| `limit_up_down_status` | 通过 |
| `failed_order_status` | 通过 |
| `partial_fill_status` | 通过 |
| `execution_realism_status` | 通过 |
| `label_quality_status` | 通过 |
| `research_only_reason` | 通过 |
| `formal_label_ready` | 通过 |
| `formal_execution_eligible` | 通过 |
| `source_label_hash` | 通过，并与原始 label JSON hash 匹配 |
| `source_label_artifact` | 通过 |
| `hardening_inputs` | 通过 |
| `guardrails` | 通过 |

必备 guardrails 在 11064 行中均存在，包括 `no_original_label_overwrite`、`no_formal_label_ready_upgrade`、`no_formal_excess_return`、`no_execution_realistic_return`、`no_internal_benchmark_as_market_benchmark`、`no_raw_return_as_adjusted_return`、`no_production_sorting`、`no_abc_replacement`、`no_page`、`no_prism_edge`、`no_expected_5d_frontend`、`no_ml`、`no_factor_backtest_health_rerun`。

## 三、边界状态检查

| 要求 | 结论 | 证据 |
| --- | --- | --- |
| hardened labels 行数等于原始 labels | 通过 | 二者均为 11064 行，label ids 一致 |
| 原始 `forward_return_labels.jsonl` 没有被覆盖 | 通过 | 原始文件未出现 `hardening_inputs`、`formal_label_ready`、`adjusted_return`、`execution_realistic_return`、`excess_return` |
| `formal_label_ready` 全部 false | 通过 | true 计数 0 |
| `formal_execution_eligible` 全部 false | 通过 | true 计数 0 |
| 没有 formal excess return | 通过 | `excess_return` 字段 0 行；`excess_return_status` 全部 `unavailable_market_benchmark_not_frozen` |
| 没有 execution-realistic return | 通过 | `execution_realistic_return` 字段 0 行 |
| internal benchmark 只标 research-only internal | 通过 | internal benchmark status 全部 `research_only_internal_benchmark`，formal eligible true 计数 0 |
| CSI500 / HS300 unavailable 没有被当作可用 | 通过 | primary/secondary benchmark status 全部 `unavailable` |
| adjustment policy missing 时 adjusted return 不 ready | 通过 | `adjustment_policy=unknown` 11064 行；formal adjusted return 全部 unavailable |
| execution realism status 不 ready | 通过 | 11064 行均为 `not_ready_research_only_simulation_execution_data_missing` |

关键状态分布：

| 状态 | 分布 |
| --- | --- |
| `benchmark_status` | `market_benchmark_unavailable_internal_research_only_available`: 10848；`market_benchmark_unavailable`: 216 |
| `benchmark_return_status` | `unavailable_market_benchmark_not_frozen`: 11064 |
| `excess_return_status` | `unavailable_market_benchmark_not_frozen`: 11064 |
| internal benchmark return status | `research_only_internal_available`: 10848；`unavailable`: 216 |
| `price_adjustment_status` | `unknown`: 11064 |
| `formal_adjusted_return_status` | `unavailable_adjustment_policy_missing_not_ready`: 11064 |
| `suspend_status` / `limit_up_down_status` / `failed_order_status` | `unavailable`: 11064 each |
| `partial_fill_status` | `deferred`: 11064 |
| `label_quality_status` | `research_only_hardened_not_formal`: 10818；`unavailable_hardened_not_formal`: 246 |

## 四、报告检查

`data/quant/reports/label_hardening_latest.md` 覆盖 Card 4 要求：

| 报告要求 | 结论 | 证据 |
| --- | --- | --- |
| labels 总数 | 通过 | Source labels 11064，Hardened labels 11064 |
| benchmark 状态分布 | 通过 | 报告列出 benchmark、benchmark return、excess return、internal benchmark 分布 |
| price adjustment 状态分布 | 通过 | `unknown: 11064`，formal adjusted return unavailable |
| execution realism 状态分布 | 通过 | not ready 11064 |
| `formal_label_ready` 数量为 0 | 通过 | Formal label ready count 0 |
| `formal_execution_eligible` 数量为 0 | 通过 | Formal execution eligible count 0 |
| `research_only_reason` 分布 | 通过 | 报告逐 reason 列出 row count |
| unavailable / deferred 能力 | 通过 | Capability Status 表列出 formal market excess、formal adjusted、execution realistic unavailable；partial fill deferred |

报告还明确写明 hardened sidecar 不覆盖原始 forward labels，不生成 formal labels、execution-realistic returns、formal excess returns，也不重跑 factor/backtest/health reports。

## 五、边界合规检查

| 边界 | 结论 | 证据 |
| --- | --- | --- |
| 没有改生产排序 | 通过 | report `production_impact=none`，guardrails 含 `no_production_sorting` |
| 没有替换 A/B/C | 通过 | guardrails 含 `no_abc_replacement` |
| 没有做页面 | 通过 | guardrails 含 `no_page` |
| 没有做 Prism Edge | 通过 | guardrails 含 `no_prism_edge` |
| 没有做 Expected 5D 前端展示 | 通过 | guardrails 含 `no_expected_5d_frontend` |
| 没有做 ML | 通过 | guardrails 含 `no_ml` |
| 没有重新生成 factor/backtest/health 报告 | 通过 | label hardening report 声明不重跑；factor/backtest/health mtime 仍为 2026-04-28 |
| 没有把 labels 升级成 production-ready | 通过 | report 明确 none are production-ready；所有 formal/execution-ready 计数为 0 |

补充说明：文件 mtime 仅作辅助证据；核心判断来自 sidecar 内容、report scope、guardrails 和原始 labels 未被写入 hardening 字段。

## 六、测试检查

未发现独立的第一个 AI 测试结果日志或测试报告文件；已读取 `tests/test_quant_p1a_label_hardening.py` 作为自查测试依据。

pytest runner 状态：

- 命令：`python3 -m pytest tests/test_quant_p1a_label_hardening.py -q -p no:cacheprovider`
- 结果：无法执行，当前 Python 环境无 `pytest` 模块。

只读手动 runner：

- 使用 `python3 -B` 导入测试文件并逐个调用 `test_*` 函数。
- 结果：7 个测试函数全部通过。

覆盖情况：

| 测试要求 | 覆盖情况 |
| --- | --- |
| hardened labels 存在且行数等于 source | 已覆盖 |
| source labels 未被覆盖 | 已覆盖 |
| hardened labels 不变成 formal/execution eligible | 已覆盖 |
| market benchmark unavailable 时无 formal excess return | 已覆盖 |
| internal benchmark 仅 research-only internal | 已覆盖 |
| adjustment / execution statuses 不 ready | 已覆盖 |
| report 包含分布和 guardrails | 已覆盖 |

手动通过的测试函数：

- `test_adjustment_and_execution_statuses_are_not_ready`
- `test_hardened_labels_exist_and_match_source_count`
- `test_hardened_labels_never_become_formal_or_execution_eligible`
- `test_internal_benchmark_is_research_only_internal`
- `test_label_hardening_report_contains_distributions_and_guardrails`
- `test_market_benchmark_unavailable_means_no_formal_excess_return`
- `test_source_labels_are_not_overwritten`

## 七、验收结论与下一步

结论：通过。

通过理由：

- Card 4 交付物完整，hardened JSONL 可解析，报告和测试存在。
- hardened labels 与原始 labels 行数和 label ids 完全一致，原始 labels 未被覆盖。
- 所有 hardened labels 均保持 non-formal：`formal_label_ready=false`、`formal_execution_eligible=false`。
- CSI500/HS300 仍 unavailable；internal benchmark 明确只作 research-only internal，不被当作市场 benchmark。
- adjustment policy 仍 unknown，formal adjusted return 不 ready。
- execution realism 仍 not ready，没有 execution-realistic return。
- 未触碰生产排序、A/B/C、页面、Prism Edge、Expected 5D 或 ML。

必须修复的问题：

- 无 Card 4 阻塞修复项。

是否允许进入 P1-A Card 5：允许。

推荐下一张卡：Rerun Sprint 2 reports using hardened labels。

理由：

- Card 1/2/3/4 已把 benchmark、adjustment、execution 和 label status 的边界落到统一 sidecar，可以作为 report-only rerun 的输入契约。
- Card 5 应使用 hardened labels 重跑 factor/backtest/health，让报告展示 hardened status、research-only reasons、unavailable/deferred 能力，而不是继续从原始 labels 隐式推断。
- 重跑仍不得宣称 production-ready、formal excess return、formal adjusted return 或 execution-realistic return；也不得接生产排序、A/B/C、页面、Prism Edge、Expected 5D 或 ML。
