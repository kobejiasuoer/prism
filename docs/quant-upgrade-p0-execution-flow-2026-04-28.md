# Prism 量化升级 P0 开发执行流程

Date: 2026-04-28
Scope: P0 / Sprint 0 first
Source: `docs/quant-upgrade-p0-review-revision-2026-04-28.md`
Status: developer handoff flow

## 1. 执行原则

本阶段只做 P0 地基，不做产品化扩张。

必须遵守：

- 只做 baseline、field audit、eligible universe、research panel、PIT、forward labels、factor evaluation、minimal backtest、report-only quant health。
- Sprint 0 只做基线冻结、字段契约、价格/执行数据审计、quant 包骨架。
- 不改生产排序。
- 不替换 A/B/C。
- 不做页面视觉。
- 不做 Prism Edge 产品化。
- 不做复杂题材状态机。
- 不做 ML。

## 2. 总执行流程

```text
确认范围 -> 派发 Sprint 0 -> 开发骨架 -> 审计字段 -> 审计价格/执行 -> 生成 baseline -> 跑测试 -> 评审产物 -> 决定是否进入 Sprint 1
```

## 3. 开发前准备

负责人先做三件事：

1. 确认开发只读这份 P0 文档：
   - `docs/quant-upgrade-p0-review-revision-2026-04-28.md`
2. 告诉开发完整 backlog 只是背景：
   - `docs/quant-upgrade-task-breakdown-2026-04-28.md`
3. 明确本次只做 Sprint 0，不做完整 P0。

发给开发的范围说明：

```text
本次只做 Prism 量化升级 P0 的 Sprint 0。

目标：
先建立 quant 包骨架、配置、baseline manifest、字段映射审计、价格/执行数据审计。

禁止：
不改生产排序，不替换 A/B/C，不做页面，不做 Prism Edge，不做 ML，不做题材状态机。
```

## 4. Sprint 0 开发任务

### 任务 1: 建 `packages/quant` 最小骨架

交付：

```text
packages/quant/
  __init__.py
  schemas.py
  paths.py
  config.py
```

要求：

- 可以被 pytest/import。
- 不影响现有 `packages/screener`。
- 不直接改生产链路。
- 路径统一指向 `data/quant/*` 和 `data/config/quant-research.json`。

验收：

- `python3 -c "import quant"` 或等效测试能通过。
- 路径初始化不覆盖已有数据。

### 任务 2: 建 `data/config/quant-research.json`

交付：

```text
data/config/quant-research.json
```

第一版至少包含：

- entry models: `next_open`, `next_close`
- holding windows: `1, 3, 5, 10`
- transaction cost:
  - buy commission
  - sell commission
  - stamp tax
  - slippage
  - impact placeholder
- portfolio:
  - max positions
  - max single position
  - rebalance rule
- benchmark:
  - primary benchmark
  - secondary benchmarks
- minimum sample size
- report-only gate settings

验收：

- JSON 可解析。
- 配置字段有默认值。
- 不在脚本里硬编码成本和窗口。

### 任务 3: 建 baseline manifest

交付：

```text
data/quant/baselines/quant_baseline_manifest.json
```

必须记录：

- artifact path
- artifact type
- trade date
- generated at
- source lane
- sha256 hash
- config checksum
- code revision
- notes

需要覆盖：

- 2024 research backfill artifacts
- 2026 最近运行 artifacts
- watchlist daily snapshots
- screener AI history
- midday verification
- command brief
- evaluation scorecard

验收：

- manifest 中每个 path 都存在。
- 每个 artifact 有 hash。
- 同一批输入后续可复现。

### 任务 4: 做 field mapping audit

交付：

```text
data/quant/reports/field_mapping_audit_latest.md
```

审计字段：

- `score`
- `priority_score`
- `best_score`
- `final_score`
- `tier`
- `execution_gate_status`
- `execution_quality`
- `capital_score`
- `technical_score`
- `theme`
- `setup_type`
- `strategy_bucket`

报告必须说明：

- 字段出现在哪些 artifact。
- 字段覆盖率是多少。
- 字段语义是否一致。
- 哪些字段可以进入 P0 因子评估。
- 哪些字段只能 research-only。
- 哪些字段缺失或语义不明。

验收：

- 不能假设 `final_score` 一定存在。
- 必须明确 `priority_score`、`best_score`、`score` 的区别。
- 覆盖率不足字段不得进入正式结论。

### 任务 5: 做 price/execution audit

交付：

```text
data/quant/reports/price_execution_audit_latest.md
```

审计内容：

- 日线价格来源
- 是否复权
- 交易日历来源
- next open / next close 是否可得
- 停牌字段是否可得
- 涨跌停字段是否可得
- T+1 如何处理
- 印花税、佣金、滑点、冲击成本如何配置
- failed order / partial fill 是否暂时支持
- benchmark 数据来源

报告必须输出：

- 当前可支持的标签。
- 当前不能支持的标签。
- P0 可以保守处理的规则。
- P1/P2 才能补的执行细节。

验收：

- 不允许在价格来源不清楚时开始正式回测。
- 不允许不扣成本就宣称策略有效。
- 不允许忽略涨跌停、停牌、T+1。

## 5. Sprint 0 验收清单

Sprint 0 完成必须具备：

| 编号 | 验收项 | 是否必须 |
| --- | --- | --- |
| 1 | `packages/quant` 可 import | 是 |
| 2 | `data/config/quant-research.json` 存在且可解析 | 是 |
| 3 | `quant_baseline_manifest.json` 存在 | 是 |
| 4 | manifest 中 artifact path 存在 | 是 |
| 5 | manifest 中 artifact 有 sha256 hash | 是 |
| 6 | `field_mapping_audit_latest.md` 存在 | 是 |
| 7 | 字段覆盖率和语义缺口清楚 | 是 |
| 8 | `price_execution_audit_latest.md` 存在 | 是 |
| 9 | 价格/执行数据缺口清楚 | 是 |
| 10 | 未改生产排序、A/B/C、页面、ML | 是 |
| 11 | 相关测试或 smoke check 通过 | 是 |

## 6. 建议开发顺序

### 第 1 步：只建骨架

先创建：

- `packages/quant`
- `data/config/quant-research.json`
- `data/quant/` 子目录结构

不要先写复杂逻辑。

### 第 2 步：先做 manifest

把当前可研究 artifact 固定下来。

优先收录：

- `stock-screener/data/research_backfill/reports/*`
- `stock-screener/data/research_backfill/ai_history/*`
- `stock-screener/data/ai_history/*`
- `stock-screener/data/midday_verification_result.json`
- `stock-analyzer/data/daily_snapshots/*`
- `apps/data/command_brief/*`
- `data/evaluation/stock_analysis/latest_scorecard.json`

### 第 3 步：再审字段

不要直接写 factor evaluation。

先问清楚：

- 哪个字段是真正的分数。
- 哪个字段只是页面展示分。
- 哪个字段只在 AI 二筛后出现。
- 哪个字段只在 watchlist 出现。
- 哪些字段历史覆盖率不足。

### 第 4 步：审价格和执行

不要急着算收益。

先确认：

- 是否有 next open。
- 是否能识别停牌。
- 是否能识别涨跌停。
- 是否复权。
- 成本怎么扣。
- benchmark 怎么选。

### 第 5 步：再评审能否进入 Sprint 1

Sprint 0 结束后开一次短评审：

- 字段够不够进入 research panel。
- 价格够不够生成 forward labels。
- 哪些字段要从 P0 因子评估剔除。
- 哪些执行假设必须保守处理。

## 7. 开发交付格式

开发提交时必须说明：

```text
本次完成：
- ...

新增文件：
- ...

关键产物：
- ...

未解决问题：
- ...

测试：
- ...

确认未做：
- 未改生产排序
- 未替换 A/B/C
- 未做页面
- 未做 Prism Edge
- 未做 ML
```

## 8. 给开发或 AI 代理的直接 Prompt

```text
请根据 docs/quant-upgrade-p0-review-revision-2026-04-28.md 开始 Prism 量化升级开发。

本次只做 Sprint 0：基线冻结与字段契约。

范围：
1. 建 packages/quant 最小包。
2. 建 data/config/quant-research.json。
3. 建 data/quant/baselines/quant_baseline_manifest.json。
4. 做 field_mapping_audit，审计现有 artifact 里的 score/tier/gate/execution/capital 字段。
5. 做 price_execution_audit，审计价格、复权、交易日历、涨跌停、停牌、成本数据来源。

禁止：
- 不改生产排序。
- 不替换 A/B/C。
- 不做页面。
- 不做 Prism Edge。
- 不做 Expected 5D 前端展示。
- 不做题材状态机。
- 不做 ML。

验收：
- 输出上述产物。
- 每个 artifact 能追溯来源。
- 字段覆盖率和缺口写清楚。
- 价格/执行数据缺口写清楚。
- 现有测试不被破坏。
```

## 9. Sprint 0 完成后的下一步

只有 Sprint 0 通过后，才能进入 Sprint 1：

- `daily_signal_panel.jsonl`
- eligible universe snapshot
- pipeline stage ledger
- PIT provenance
- forward return labels
- panel/label coverage report

如果 Sprint 0 发现字段覆盖率不足或价格执行数据不够，必须先修数据和契约，不能强行进入回测。
