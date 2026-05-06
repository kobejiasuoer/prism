# Prism 量化升级 P1-A Card 1 Benchmark 独立验收报告

Date: 2026-04-28
Reviewer: independent acceptance reviewer
Scope: P1-A Card 1 Benchmark manifest / benchmark return labels
Boundary:
- `docs/quant-upgrade-p1a-hardening-acceptance-checklist-2026-04-28.md`
- `docs/quant-upgrade-p1a-decision-matrix-2026-04-28.md`
Implementation plan:
- `docs/quant-upgrade-p1a-source-inventory-and-implementation-plan-2026-04-28.md`

## 0. 验收结论

| 项目 | 结论 |
| --- | --- |
| Card 1 是否通过 | 通过 |
| 是否允许进入 P1-A Card 2 | 允许 |
| 推荐下一张卡 | Adjusted price policy |
| 是否允许生成 excess return | 不允许，CSI500/HS300 仍 unavailable |
| 是否允许进入生产/页面/Prism Edge | 不允许 |

Card 1 按 source inventory 的边界完成：没有伪造 CSI500/HS300，没有抓外部数据；只生成了 `eligible_universe_equal_weight` 的 research-only internal benchmark returns，并把 CSI500/HS300 明确标为 unavailable。forward labels 未被写入 `benchmark_return` 或 `excess_return`，Sprint 2 factor/backtest/health 报告也未因 Card 1 被升级为 production-ready。

## 一、交付物完整性

| 交付物 | 状态 | 验收意见 |
| --- | --- | --- |
| `packages/quant/benchmark_registry.py` | 不存在 | 可接受；Card 1 使用 `build_benchmark_returns.py` 承载实现 |
| `packages/quant/build_benchmark_returns.py` | 存在 | 代码包含 manifest、internal benchmark returns、coverage report 的生成逻辑；验收时未调用写出函数 |
| `data/quant/benchmarks/benchmark_manifest.json` | 存在，可解析 | `jq` 可解析，包含 3 个 benchmark 条目 |
| `data/quant/benchmarks/benchmark_returns.jsonl` | 存在，可解析 | 448 行，逐行 JSON 可解析 |
| `data/quant/reports/benchmark_coverage_latest.md` | 存在 | 明确 Card 1 scope、research-only internal benchmark、CSI500/HS300 unavailable、no excess return |
| `tests/test_quant_p1a_benchmarks.py` | 存在 | 覆盖 manifest、CSI500/HS300 unavailable、internal benchmark、returns 非空、labels 未注入 excess |

只读结构校验摘要：

| 检查项 | 结果 |
| --- | --- |
| manifest benchmark ids | `CSI500`、`HS300`、`eligible_universe_equal_weight` |
| benchmark returns rows | 448 |
| returns benchmark ids | 仅 `eligible_universe_equal_weight` |
| returns trade years | 仅 2024 |
| forward labels count | 11064 |
| labels with `benchmark_return` | 0 |
| labels with `excess_return` | 0 |

## 二、Benchmark Manifest 检查

manifest 顶层包含 `schema_version`、`generated_at`、`production_impact: none`、config checksum、code revision、input/output artifacts、label date scope、benchmarks 和 guardrails。

逐 benchmark 必填字段检查：

| benchmark_id | 必填字段是否齐全 | status | hash/checksum | return_method | notes |
| --- | --- | --- | --- | --- | --- |
| `eligible_universe_equal_weight` | 齐全 | `research_only_internal_benchmark` | 有 hash 与 checksum | `mean net_return across unique source-observed eligible codes...` | 明确 internal、not CSI500/HS300、not formal market benchmark |
| `CSI500` | 齐全 | `unavailable` | `null` | `unavailable_no_frozen_index_price_series` | 明确当前 repo 无 frozen CSI500 index price artifact |
| `HS300` | 齐全 | `unavailable` | `null` | `unavailable_no_frozen_index_price_series` | 明确当前 repo 无 frozen HS300 index price artifact |

逐项字段覆盖：

- `benchmark_id`: 通过。
- `benchmark_name`: 通过。
- `benchmark_type`: 通过。
- `status`: 通过。
- `source`: 通过。
- `coverage_start`: 通过，market unavailable 条目为 `null`。
- `coverage_end`: 通过，market unavailable 条目为 `null`。
- `missing_dates_count`: 通过。
- `hash/checksum`: 通过，internal 有值；CSI500/HS300 因 unavailable 为 `null`。
- `return_method`: 通过。
- `notes`: 通过。

## 三、Benchmark 状态检查

| 要求 | 结论 | 证据 |
| --- | --- | --- |
| `eligible_universe_equal_weight` 是 `research_only_internal_benchmark` | 通过 | manifest 和 returns 均为该 status；report 明确不是 formal market benchmark |
| CSI500 是 `unavailable` | 通过 | manifest status 为 `unavailable`，row_count 0，hash null，missing_dates_count 57 |
| HS300 是 `unavailable` | 通过 | manifest status 为 `unavailable`，row_count 0，hash null，missing_dates_count 57 |
| 没有伪造 CSI500/HS300 数据 | 通过 | 无 CSI500/HS300 returns；report 写明 no fabricated CSI500/HS300 data |
| 没有抓外部数据 | 通过 | 代码未出现 requests/akshare/tushare/http fetch；manifest guardrails 含 `no_external_data_fetch` |

重要边界：Card 1 并未完成 primary market benchmark freeze。它只把 market benchmark 缺口显式 manifest 化，并提供一个 internal research-only equal-weight 对照。

## 四、Benchmark Returns 检查

`benchmark_returns.jsonl` 必填字段检查：

| 字段 | 结论 |
| --- | --- |
| `benchmark_id` | 通过，全部为 `eligible_universe_equal_weight` |
| `trade_date` | 通过，全部为 2024 日期 |
| `entry_model` | 通过，包含 `next_open` / `next_close` |
| `holding_window_days` | 通过，包含 1/3/5/10 |
| `benchmark_return` | 通过 |
| `benchmark_return_type` | 通过，全部为 `research_only_internal_net_equal_weight` |
| `sample_count` | 通过，均大于 0 |
| `status` | 通过，全部为 `research_only_internal_benchmark` |
| `source_hash` | 通过，均非空 |
| `notes` | 通过，明确不是 frozen market benchmark 或 production/formal excess return |

附加检查：

- JSONL 不为空：448 行。
- 只基于现有 eligible universe / labels：通过。manifest source 为 `forward_return_labels.jsonl` 和 `eligible_universe_snapshot.jsonl`。
- 未使用 2026 当前 artifact 做 formal label：通过。returns trade years 仅 2024；manifest 记录 2026 source-observed universe rows excluded。
- 未把 internal benchmark 说成正式市场 benchmark：通过。report 和 notes 均明确 internal/research-only/not formal market benchmark。

保留意见：

- internal benchmark 的 `sample_count_min=2`，部分 trade_date/window 的等权样本很薄。当前已标为 research-only internal，可以接受；后续若要用于正式比较，需要更严格的 universe 完整性和样本阈值。

## 五、边界合规检查

| 边界 | 结论 | 证据 |
| --- | --- | --- |
| 没有修改生产排序 | 通过 | manifest `production_impact=none`，guardrails 含 `no_production_sorting` |
| 没有替换 A/B/C | 通过 | guardrails 含 `no_abc_replacement` |
| 没有做页面 | 通过 | guardrails 含 `no_page` |
| 没有做 Prism Edge | 通过 | guardrails 含 `no_prism_edge` |
| 没有做 Expected 5D 前端展示 | 通过 | benchmark report guardrails 写明 no Expected 5D frontend |
| 没有做 ML | 通过 | guardrails 含 `no_ml` |
| 没有重新生成 factor/backtest/health 报告 | 通过 | Card 1 新增的是 `benchmark_coverage_latest.md`；factor/backtest/health 仍保持各自 report-only scope，未出现 benchmark/excess 升级 |
| 没有把 benchmark return 写回 forward labels 生成 excess return | 通过 | labels 中 `benchmark_return` 行数 0，`excess_return` 行数 0，仍为 `benchmark_unavailable` / `deferred_until_benchmark_frozen` |

## 六、测试检查

未发现独立的第一个 AI 测试结果日志或测试报告文件；已读取 `tests/test_quant_p1a_benchmarks.py` 作为自查测试依据。

pytest runner 状态：

- 命令：`python3 -m pytest tests/test_quant_p1a_benchmarks.py -q -p no:cacheprovider`
- 结果：无法执行，当前 Python 环境无 `pytest` 模块。

只读手动 runner：

- 使用 `python3 -B` 导入测试文件并逐个调用 `test_*` 函数。
- 结果：5 个测试函数全部通过。

覆盖情况：

| 测试要求 | 覆盖情况 |
| --- | --- |
| manifest 可解析 | 已覆盖 |
| CSI500 / HS300 unavailable | 已覆盖 |
| eligible universe benchmark research-only | 已覆盖 |
| returns 非空 | 已覆盖 |
| no excess return injected into labels | 已覆盖 |

手动通过的测试函数：

- `test_benchmark_manifest_json_contract`
- `test_csi500_and_hs300_are_unavailable_without_frozen_data`
- `test_eligible_equal_weight_is_research_only_internal_benchmark`
- `test_benchmark_returns_jsonl_contract_and_2026_exclusion`
- `test_p1a_card1_does_not_generate_excess_return_to_forward_labels`

## 七、验收结论

结论：通过。

通过理由：

- Card 1 交付物完整，JSON/JSONL 可解析。
- Manifest 字段齐全，状态与 source inventory 一致。
- CSI500/HS300 未伪造、未外部抓取、保持 unavailable。
- `eligible_universe_equal_weight` 明确为 research-only internal benchmark。
- `benchmark_returns.jsonl` 非空且只包含 2024 internal benchmark rows。
- forward labels 未被注入 benchmark/excess return。
- 边界 guardrails 完整，没有生产排序、A/B/C、页面、Prism Edge、Expected 5D 或 ML 变更。

必须修复的问题：

- 无阻塞修复项。

进入下一卡前建议保留的注意事项：

- Card 1 不能被解读为 primary benchmark 已完成；CSI500/HS300 仍不可用于 excess return。
- internal equal-weight 样本较薄，只能做 report-only internal comparison。
- 后续任何 label 或 report 若引用 internal benchmark，必须继续标记 research-only internal，不能称为 market benchmark。

是否允许进入 P1-A Card 2：允许。

推荐下一张卡：Adjusted price policy。

理由：

- source inventory 显示 2024 raw OHLCV cache 已存在，但 `adjustment_policy`、`adj_factor`、前复权/后复权口径仍缺失。
- 当前 forward labels 的收益仍带 `price_adjustment_status=unknown`，这是 formal return 和后续 benchmark/excess return 的直接阻塞。
- execution flags 需要停牌、涨跌停、board/ST、order outcome 等更多不确定数据源；先冻结 adjusted price policy 可以更快降低 label 口径风险，并为后续 execution flags 提供稳定价格基础。
