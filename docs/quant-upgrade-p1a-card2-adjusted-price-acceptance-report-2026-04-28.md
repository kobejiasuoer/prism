# Prism 量化升级 P1-A Card 2 Adjusted Price Policy 独立验收报告

Date: 2026-04-29
Reviewer: independent acceptance reviewer
Scope: P1-A Card 2 adjusted price policy / price adjustment policy
Boundary:
- `docs/quant-upgrade-p1a-hardening-acceptance-checklist-2026-04-28.md`
- `docs/quant-upgrade-p1a-decision-matrix-2026-04-28.md`
Implementation plan:
- `docs/quant-upgrade-p1a-source-inventory-and-implementation-plan-2026-04-28.md`
- `docs/quant-upgrade-p1a-card2-adjusted-price-implementation-plan-2026-04-28.md`

## 0. 验收结论

| 项目 | 结论 |
| --- | --- |
| Card 2 是否通过 | 通过 |
| 是否允许生成 formal adjusted return | 不允许 |
| 是否允许把 raw return 当 adjusted return | 不允许 |
| 是否允许 labels 升级为 `formal_label_ready` | 不允许 |
| 是否允许进入 P1-A 下一张卡 | 允许 |
| 推荐下一张卡 | Execution flags / execution data availability |
| 是否允许进入生产/页面/Prism Edge | 不允许 |

Card 2 按实施方案完成的是 adjusted price policy freeze 和缺口显式化，而不是补齐复权数据。当前 raw OHLCV 可用于审计与 research-only replay；前复权/qfq 被确定为未来 formal research return 的目标口径；后复权/hfq 被排除在 formal forward labels 之外。由于当前仓库没有 `adj_factor`、qfq/hfq、adjusted OHLC、`adjustment_policy` 或 PIT 复权可用性证明，formal adjusted return 仍必须保持 unavailable。

本次验收未修改 `packages/quant`，未修改 `data/quant/price/*`，未覆盖 `data/quant/reports/*`，仅新增本验收报告。

## 一、交付物完整性

| 交付物 | 状态 | 验收意见 |
| --- | --- | --- |
| `packages/quant/price_adjustment_policy.py` | 存在 | 包含 price cache / label inspection、manifest 和 report 渲染逻辑；验收时未调用写出函数或 CLI |
| `data/quant/price/price_adjustment_manifest.json` | 存在，可解析 | JSON 可解析，记录 policy、raw field coverage、missing adjustment fields、label implications 和 guardrails |
| `data/quant/reports/price_adjustment_policy_latest.md` | 存在 | 明确 Card 2 scope，不重跑 labels、adjusted prices、factor/backtest/health |
| `tests/test_quant_p1a_adjusted_price.py` | 存在 | 覆盖 manifest contract、policy status、formal adjusted return not ready、labels 未升级 |

只读结构校验摘要：

| 检查项 | 结果 |
| --- | --- |
| manifest parse | 通过 |
| policy status | `raw_available_adjustment_unknown_research_only` |
| formal adjusted return status | `unavailable_adjustment_policy_missing_not_ready` |
| production impact | `none` |
| raw OHLCV rows | 84500 |
| date coverage | 2023-11-20 to 2024-04-10，94 unique dates |
| source counts | `tx`: 78867，`<missing>`: 5633 |
| forward labels inspected | 11064 |
| labels with `adjusted_return` | 0 |
| labels with `formal_label_ready` | 0 |

## 二、Adjusted Price Manifest 检查

manifest 顶层字段满足 Card 2 验收需要：

| 字段 | 结论 | 关键值 |
| --- | --- | --- |
| `schema_version` | 通过 | `1.0` |
| `generated_at` | 通过 | 有生成时间 |
| `production_impact` | 通过 | `none` |
| `price_source_artifacts` | 通过 | 1571 个 JSON artifact，均可读并带 sha256 |
| `price_row_count` | 通过 | 84500 |
| `date_coverage` | 通过 | 2023-11-20 至 2024-04-10 |
| `available_fields` | 通过 | raw `open/high/low/close/volume/amount` 100% 覆盖 |
| `missing_adjustment_fields` | 通过 | 明确列出复权关键缺口 |
| `selected_policy` | 通过 | current raw unknown，target qfq，hfq excluded |
| `policy_status` | 通过 | research-only |
| `formal_adjusted_return_status` | 通过 | unavailable |
| `label_implications` | 通过 | labels 不允许 formal upgrade |
| `guardrails` | 通过 | 包含 report-only、no production/page/Prism Edge/ML 等硬边界 |

复权缺口字段检查通过，manifest 明确包含：

- `adj_factor`
- `qfq`
- `hfq`
- `adjusted_ohlc`
- `open_adj`
- `high_adj`
- `low_adj`
- `close_adj`
- `prev_close_adj`
- `adjustment_policy`
- `corporate_action_provenance`
- `pit_adjustment_available_timestamp`

重要边界：这份 manifest 的通过不代表复权价格可用，只代表当前缺口被显式冻结和审计。

## 三、价格口径与策略检查

| 要求 | 结论 | 验收意见 |
| --- | --- | --- |
| raw / forward-adjusted / backward-adjusted 使用规则明确 | 通过 | raw 仅审计和 research-only replay；qfq 作为未来 formal target；hfq 排除 formal forward labels |
| `adjustment_policy` 缺失时不得宣称正式收益 | 通过 | `formal_adjusted_return_status=unavailable_adjustment_policy_missing_not_ready` |
| 不明确复权状态时不得把 raw return 升级 | 通过 | `raw_return_upgrade_to_adjusted_return_allowed=false` |
| PIT 风险有标记 | 通过 | 明确缺 `pit_adjustment_available_timestamp`，未来需要 PIT proof |
| 不生成 adjusted price | 通过 | guardrails 含 `no_adjusted_price_generation` |
| 不推断 adjustment factor | 通过 | guardrails 含 `no_adjustment_factor_inference` |

当前 raw OHLCV 数据完整，可支撑审计与 raw replay；但 raw 数据中 `source` 字段仍有 5633 行缺失。因为 Card 2 没有把这些 raw returns 升级为 formal adjusted returns，此项不构成阻塞，但后续 formal price source/hashing 仍需补齐。

## 四、Forward Labels 边界检查

| 检查项 | 结果 |
| --- | --- |
| label scope | 全部为 `2024_research_backfill_only` |
| trade years | 全部为 2024 |
| `price_adjustment_status` | 11064 行均为 `unknown` |
| `execution_data_missing` 含 `adjustment_policy` | 11064 行 |
| `adjusted_return` | 0 行 |
| `formal_label_ready` | 0 行 |
| `formal_execution_eligible=true` | 0 行 |
| `benchmark_return` / `excess_return` | 0 行 / 0 行 |

结论：Card 2 没有把当前 2024 raw labels 升级为 formal adjusted labels，也没有把 2026 artifact 纳入正式 label 评估。labels 仍保持 research-only / unavailable 状态，符合 P1-A 硬边界。

## 五、报告与边界合规检查

| 边界 | 结论 | 证据 |
| --- | --- | --- |
| 没有修改生产排序 | 通过 | manifest `production_impact=none`，guardrails 含 `no_production_sorting` |
| 没有替换 A/B/C | 通过 | guardrails 含 `no_abc_replacement` |
| 没有做页面 | 通过 | guardrails 含 `no_page` |
| 没有做 Prism Edge | 通过 | guardrails 含 `no_prism_edge` |
| 没有做 Expected 5D 前端展示 | 通过 | guardrails 含 `no_expected_5d_frontend` |
| 没有做 ML | 通过 | guardrails 含 `no_ml` |
| 没有外部抓取 | 通过 | `price_adjustment_policy.py` 未出现 requests/http/akshare/tushare/download/fetch 调用；guardrails 含 `no_external_data_fetch` |
| 没有重新生成 factor/backtest/health | 通过 | price policy 报告声明不重跑；factor/backtest/health 报告时间仍为 2026-04-28，price policy 为 2026-04-29 |
| 没有 production-ready 误导 | 通过 | report 明确 no formal adjusted return、raw labels remain research-only、minimal backtest remains research_only_simulation |

补充说明：文件 mtime 只能作为辅助证据；核心判断仍以 Card 2 report、manifest guardrails、labels 未升级、factor/backtest/health 未出现 adjusted/excess 升级声明为准。

## 六、测试检查

未发现独立的第一个 AI 测试结果日志或测试报告文件；已读取 `tests/test_quant_p1a_adjusted_price.py` 作为自查测试依据。

pytest runner 状态：

- 命令：`python3 -m pytest tests/test_quant_p1a_adjusted_price.py -q -p no:cacheprovider`
- 结果：无法执行，当前 Python 环境无 `pytest` 模块。

只读手动 runner：

- 使用 `python3 -B` 导入测试文件并逐个调用 `test_*` 函数。
- 结果：6 个测试函数全部通过。

覆盖情况：

| 测试要求 | 覆盖情况 |
| --- | --- |
| manifest JSON contract | 已覆盖 |
| current policy / target policy / hfq exclusion | 已覆盖 |
| formal adjusted return not ready | 已覆盖 |
| missing adjustment fields | 已覆盖 |
| report states raw labels remain research-only | 已覆盖 |
| forward labels 未升级为 formal adjusted labels | 已覆盖 |

手动通过的测试函数：

- `test_formal_adjusted_return_is_not_ready`
- `test_forward_labels_are_not_upgraded_to_formal_adjusted_labels`
- `test_missing_adjustment_fields_include_required_gap_markers`
- `test_price_adjustment_manifest_json_contract`
- `test_report_states_raw_labels_remain_research_only`
- `test_selected_policy_and_policy_status_are_explicit`

## 七、验收结论与下一步

结论：通过。

通过理由：

- Card 2 交付物完整，JSON 可解析，报告存在，测试存在。
- 当前 raw OHLCV availability 和复权缺口均被明确记录。
- formal target policy 选择前复权/qfq，与 P1-A checklist 和 decision matrix 一致。
- hfq/backward-adjusted 被排除在 formal forward labels 之外，避免 PIT 风险。
- 没有生成 adjusted prices，没有推断 adjustment factor，没有把 raw return 伪装成 adjusted return。
- forward labels 没有升级为 `formal_label_ready`，也没有新增 `adjusted_return`、`benchmark_return` 或 `excess_return`。
- 未触碰生产排序、A/B/C、页面、Prism Edge、Expected 5D 或 ML。

必须修复的问题：

- 无 Card 2 阻塞修复项。

进入下一卡前必须保留的限制：

- P1-A 仍未完成 formal adjusted return 能力。
- 当前收益仍只能作为 raw / research-only 解释，不能用于 production-ready 或 execution-realistic 结论。
- 后续若要升级 label，必须先补齐 qfq/approved adjusted OHLC、`adj_factor`、`adjustment_policy`、source hash 和 PIT availability proof。

是否允许进入 P1-A 下一张卡：允许。

推荐下一张卡：Execution flags / execution data availability。

理由：

- Benchmark Card 1 已把 market benchmark 缺口显式化；Card 2 已冻结 adjusted price policy 并阻止 raw return 误升级。
- 当前 labels 仍被 `suspend_status`、`limit_up_down_status`、`failed_order`、`partial_fill` 全量阻塞，minimal backtest 仍必须是 `research_only_simulation`。
- 下一张卡应继续把执行数据可得性、保守 failed order / partial fill 规则和 unavailable 降级状态固定下来；同时需要另开或后续安排 adjusted price source acquisition，补齐 qfq/PIT/source hash 后才能谈 formal adjusted return。
