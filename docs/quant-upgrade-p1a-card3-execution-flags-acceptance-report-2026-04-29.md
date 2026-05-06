# Prism 量化升级 P1-A Card 3 Execution Flags 独立验收报告

Date: 2026-04-29
Reviewer: independent acceptance reviewer
Scope: P1-A Card 3 execution flags / execution data availability
Boundary:
- `docs/quant-upgrade-p1a-hardening-acceptance-checklist-2026-04-28.md`
- `docs/quant-upgrade-p1a-decision-matrix-2026-04-28.md`
- `docs/quant-upgrade-p1a-source-inventory-and-implementation-plan-2026-04-28.md`
- `docs/quant-upgrade-p1a-card2-adjusted-price-acceptance-report-2026-04-28.md`

## 0. 验收结论

| 项目 | 结论 |
| --- | --- |
| Card 3 是否通过 | 通过 |
| 是否允许 execution-realistic return | 不允许 |
| 是否允许 labels 升级为 `formal_execution_eligible` | 不允许 |
| 当前 backtest 状态 | 仍为 `research_only_simulation` |
| 是否允许进入 P1-A Card 4 | 允许，有边界 |
| 推荐下一张卡 | Forward labels upgrade |
| 是否允许进入生产/页面/Prism Edge | 不允许 |

Card 3 完成的是 execution-data availability freeze：它把停牌、涨跌停、failed order、partial fill 的当前缺口显式写入 manifest/report，而不是补齐真实执行数据或模拟真实成交。当前 raw OHLCV、volume/amount 和成本配置可用于诊断，但不能支持 execution-realistic return。

本次验收未修改 `packages/quant`，未修改 `data/quant/execution/*`，未覆盖 `data/quant/reports/*`，仅新增本验收报告。

## 一、交付物完整性

| 交付物 | 状态 | 验收意见 |
| --- | --- | --- |
| `packages/quant/execution_flags.py` | 存在 | 包含 price/label inspection、manifest 和 report 渲染逻辑；验收时未调用写出函数或 CLI |
| `data/quant/execution/execution_flags_manifest.json` | 存在，可解析 | JSON 可解析，包含要求的 execution availability、T+1、cost、label implications、guardrails |
| `data/quant/reports/execution_flags_coverage_latest.md` | 存在 | 明确 Card 3 scope，不重跑 labels、execution-realistic backtest、factor/backtest/health |
| `tests/test_quant_p1a_execution_flags.py` | 存在 | 覆盖 manifest contract、execution not-ready、缺口显式化、T+1、labels 未升级 |

只读结构校验摘要：

| 检查项 | 结果 |
| --- | --- |
| manifest parse | 通过 |
| inspected labels | 11064 |
| inspected price rows | 84500 |
| execution realism status | `not_ready_research_only_simulation_execution_data_missing` |
| label scope | 全部为 `2024_research_backfill_only` |
| labels with `formal_execution_eligible=true` | 0 |
| labels with `execution_realistic_return` | 0 |
| labels with `execution_flags` | 0 |
| labels with `order_status` | 0 |

## 二、Manifest 字段检查

| 必填字段 | 结论 | 关键值 |
| --- | --- | --- |
| `schema_version` | 通过 | `1.0` |
| `generated_at` | 通过 | 有生成时间 |
| `production_impact` | 通过 | `none` |
| `inspected_label_count` | 通过 | 11064 |
| `inspected_price_row_count` | 通过 | 84500 |
| `suspend_status_availability` | 通过 | `status=unavailable` |
| `limit_up_down_status_availability` | 通过 | `status=unavailable` |
| `failed_order_availability` | 通过 | `status=unavailable` |
| `partial_fill_availability` | 通过 | `status=deferred` |
| `t_plus_one_policy` | 通过 | 明确 T+1 配置与 research-only 状态 |
| `cost_policy_reference` | 通过 | 记录 config path/checksum、成本配置、roundtrip 20 bps |
| `execution_realism_status` | 通过 | `not_ready_research_only_simulation_execution_data_missing` |
| `label_implications` | 通过 | 禁止 formal execution / execution-realistic return |
| `guardrails` | 通过 | 包含 report-only、no production/page/Prism Edge/ML 等硬边界 |

manifest 还记录了 raw OHLCV 与 volume/amount 100% 可用，适合作为 execution-adjacent diagnostics。但它没有把这些诊断字段升级为真实停牌、涨跌停、成交失败或部分成交证明。

## 三、执行数据状态检查

| 要求 | 结论 | 验收意见 |
| --- | --- | --- |
| 停牌字段没有被伪装成 available | 通过 | `suspend_status_availability.status=unavailable`，`machine_readable_available=false`，11064 行 label 标记 missing |
| 涨跌停字段没有被伪装成 available | 通过 | `limit_up_down_status_availability.status=unavailable`，未用 OHLCV 推断为 formal evidence |
| failed order 没有被真实模拟 | 通过 | `failed_order_availability.status=unavailable`，报告写明没有 broker/order ledger，不推断真实 failed orders |
| partial fill 没有被真实模拟 | 通过 | `partial_fill_availability.status=deferred`，只承认 volume/amount 诊断，不承认 fill ratio/broker fills |
| T+1 policy 明确 | 通过 | 配置为 `daily_after_signal_with_t_plus_1_execution`，当前处理为 `conservative_next_observed_trade_row_entry` |
| 当前 backtest 仍是 research-only | 通过 | report 明确 current backtest remains `research_only_simulation`；Sprint 2 backtest report 也仍为 research-only |
| 没有宣称 execution-realistic return | 通过 | report 明确 no execution-realistic return can be claimed |

全量 label 检查：

| 字段/状态 | 结果 |
| --- | --- |
| `suspend_status` in `execution_data_missing` | 11064 |
| `limit_up_down_status` in `execution_data_missing` | 11064 |
| `failed_order` in `execution_data_missing` | 11064 |
| `partial_fill` in `execution_data_missing` | 11064 |
| `formal_label_ready` | 0 |
| `benchmark_return` / `excess_return` | 0 / 0 |

## 四、边界合规检查

| 边界 | 结论 | 证据 |
| --- | --- | --- |
| 没有抓外部数据 | 通过 | 代码和报告只读取本地 price cache / labels / config；guardrails 含 `no_external_data_fetch` |
| 没有推断真实成交 | 通过 | guardrails 含 `no_real_fill_inference`；failed/partial 均未生成真实 fill |
| 没有把 unavailable 执行字段伪装成 available | 通过 | guardrails 含 `no_unavailable_execution_field_as_available` |
| 没有生成 execution-realistic backtest | 通过 | guardrails 含 `no_execution_realistic_backtest_generation` |
| 没有把 labels 升级成 `formal_execution_eligible` | 通过 | labels 中 true 计数为 0；manifest 禁止 upgrade |
| 没有改生产排序 | 通过 | `production_impact=none`，guardrails 含 `no_production_sorting` |
| 没有替换 A/B/C | 通过 | guardrails 含 `no_abc_replacement` |
| 没有做页面 | 通过 | guardrails 含 `no_page` |
| 没有做 Prism Edge | 通过 | guardrails 含 `no_prism_edge` |
| 没有做 Expected 5D 前端展示 | 通过 | guardrails 含 `no_expected_5d_frontend` |
| 没有做 ML | 通过 | guardrails 含 `no_ml` |
| 没有重新生成 factor/backtest/health 报告 | 通过 | execution report 声明不重跑；factor/backtest/health mtime 仍为 2026-04-28，execution report 为 2026-04-29 |

补充说明：文件 mtime 只是辅助证据；核心判断来自 manifest guardrails、report scope、labels 未升级，以及 Sprint 2 reports 未出现 execution-realistic 升级声明。

## 五、测试检查

未发现独立的第一个 AI 测试结果日志或测试报告文件；已读取 `tests/test_quant_p1a_execution_flags.py` 作为自查测试依据。

pytest runner 状态：

- 命令：`python3 -m pytest tests/test_quant_p1a_execution_flags.py -q -p no:cacheprovider`
- 结果：无法执行，当前 Python 环境无 `pytest` 模块。

只读手动 runner：

- 使用 `python3 -B` 导入测试文件并逐个调用 `test_*` 函数。
- 结果：6 个测试函数全部通过。

覆盖情况：

| 测试要求 | 覆盖情况 |
| --- | --- |
| manifest JSON contract | 已覆盖 |
| execution realism not ready | 已覆盖 |
| suspend/limit/failed/partial gaps explicit | 已覆盖 |
| T+1 policy explicit | 已覆盖 |
| report states backtest remains research-only | 已覆盖 |
| labels 未升级为 formal execution eligible | 已覆盖 |

手动通过的测试函数：

- `test_execution_data_gaps_are_explicit`
- `test_execution_flags_manifest_json_contract`
- `test_execution_realism_status_is_not_ready`
- `test_forward_labels_are_not_upgraded_to_formal_execution_eligible`
- `test_report_states_backtest_remains_research_only_simulation`
- `test_t_plus_one_policy_is_explicit`

## 六、验收结论与下一步

结论：通过。

通过理由：

- Card 3 交付物完整，manifest 可解析，报告和测试存在。
- 停牌、涨跌停、failed order、partial fill 均被明确标为 unavailable/deferred，没有伪装可用。
- T+1 和成本配置被引用，但仍标明当前不是 execution-realistic。
- forward labels 没有新增 `execution_flags`、`order_status` 或 `execution_realistic_return`，也没有升级 `formal_execution_eligible`。
- 未触碰生产排序、A/B/C、页面、Prism Edge、Expected 5D 或 ML。

必须修复的问题：

- 无 Card 3 阻塞修复项。

是否允许进入 P1-A Card 4：允许，但 Card 4 不能把当前 labels 升级为 formal/execution-realistic。它只能把 benchmark、adjustment、execution 的已验收状态和 unavailable/deferred 原因写成更明确的 label schema 或 sidecar overlay。

推荐下一张卡：Forward labels upgrade。

理由：

- Card 1/2/3 已分别冻结 benchmark、adjusted price policy 和 execution availability；下一步应先把这些状态合并进 forward labels 或 sidecar，让每条 label 明确记录 benchmark status、adjustment status、execution status、`label_status` 降级原因。
- 现在直接 rerun Sprint 2 reports 只会重复 research-only 结论，且容易让读者误以为数据硬化已经带来正式收益能力。
- Forward labels upgrade 后再 rerun Sprint 2 reports，报告才能基于统一 label contract 展示哪些窗口仍 unavailable、哪些只是 internal/research-only、哪些未来才可能 formal。

Card 4 边界建议：

- 不生成 formal adjusted return，除非 qfq/adj factor/PIT/source hash 全部补齐并另行验收。
- 不生成 market excess return，除非 CSI500/HS300 frozen benchmark 补齐并另行验收。
- 不生成 execution-realistic return，除非 suspend/limit/order/fill 数据补齐并另行验收。
- 不改生产排序、A/B/C、页面、Prism Edge、Expected 5D 或 ML。
