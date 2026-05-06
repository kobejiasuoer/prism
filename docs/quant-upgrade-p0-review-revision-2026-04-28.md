# Prism 量化升级 P0 评审修订稿

Date: 2026-04-28
Source:
- `docs/quant-upgrade-design-2026-04-27.md`
- `docs/quant-upgrade-task-breakdown-2026-04-28.md`
- AI 评审结论：有条件通过，P0 必须收缩
Status: P0 scope approved

## 0. 决策记录

P0 范围已确认：

第一阶段只做 baseline、field audit、eligible universe、research panel、PIT、forward labels、factor evaluation、minimal backtest、report-only quant health。

第一阶段明确不做：

- 不接生产排序。
- 不替换 A/B/C。
- 不做页面视觉。
- 不做复杂题材状态机。
- 不做机器学习模型。

执行含义：

- P0 的目标是证明 Prism 当前历史输出能被复现、对齐、验证。
- P0 产出的量化字段只能 research-only / shadow / report-only。
- 任何影响用户开仓动作、候选排序、分层定义、页面主决策表达的改动，都必须进入 P1 以后重新评审。

## 1. 评审结论

本次量化升级方向通过，但原任务清单里的 P0 范围过大。

第一阶段不要先做页面视觉，不要先做完整 Prism Edge，也不要让新量化字段影响生产排序。P0 的唯一目标是证明 Prism 当前历史输出可以被复现、对齐、验证，并形成 report-only 的量化验收报告。

P0 主线收缩为：

```text
冻结基线 -> 字段契约 -> eligible universe -> PIT provenance -> forward labels -> 因子评估 -> 最小组合回测 -> report-only quant health
```

## 2. P0 边界

### P0 必须做

| 模块 | 必须交付 |
| --- | --- |
| 基线冻结 | artifact hash、配置版本、代码版本、baseline manifest |
| 字段契约 | `priority_score`、`best_score`、`final_score` 等字段映射和覆盖率审计 |
| 数据面板 | `daily_signal_panel.jsonl`、eligible universe、pipeline stage、inclusion reason |
| PIT | 样本级和关键 feature 级 provenance：source timestamp、available timestamp、source hash |
| 标签 | 1/3/5/10 日 raw/net/excess、MAE/MFE、limit/suspend、T+1、成本 |
| 因子评估 | score、tier、gate、execution_quality、capital flow normalization |
| 后验验证 | A/B/C 单调性、AI 二筛、午盘 confirmation/downgrade |
| 最小回测 | `top_n_raw_score`、`gate_filtered_top_n` |
| 验收门 | `quant_health_latest.json/md`，只 report-only |
| 测试 | PIT、label、factor、overlap、backtest、optional API fields |

### P0 明确不做

| 延后内容 | 放到 |
| --- | --- |
| 完整 Prism Edge 生产化 | P1 shadow |
| Expected 5D / Win Prob 前端默认展示 | P1 shadow |
| 新 A/B/C 替换旧分层 | P1 |
| setup-regime policy | P1 |
| 题材状态机、leader/co-leader 角色 | P1/P2 |
| Portfolio decision memory | P1 |
| Settings 量化任务 UI | P1 |
| 复杂机器学习模型 | P2 |
| hard gate 阻断生产 | P1 以后，需至少两个样本外窗口通过 |

## 3. 必须补进原计划的缺口

| 缺口 | 为什么必须补 | P0 处理方式 |
| --- | --- | --- |
| eligible universe | 只研究已入选候选会高估策略质量 | 新增 universe snapshot 和 pipeline stage ledger |
| 字段名不一致 | 当前 artifact 可能是 `priority_score` / `best_score`，不是统一 `final_score` | 先做 field mapping audit，覆盖率不足不得进入结论 |
| feature 级 PIT | row timestamp 不等于每个因子都 PIT 合规 | 每个关键 feature 写 source timestamp / available timestamp / source hash |
| 价格和执行可信度 | A 股涨跌停、停牌、T+1、费用会改变结论 | 先定义 calendar、复权、limit/suspend、成本、failed order 规则 |
| artifact 可复现性 | 没有 hash 和 config 版本，后续无法比较 | baseline manifest 记录 artifact hash、config checksum、code revision |
| 多重检验风险 | 同时看很多因子容易挑噪声 | P0 报告至少标记 multiple testing 风险，P1 再做 FDR/中性化 |

## 4. 修订版 Sprint 计划

### Sprint 0: 基线冻结与字段契约

目标：先知道现有数据能不能研究。

任务：

1. 新建 `data/quant/baselines/quant_baseline_manifest.json`。
2. 记录 artifact path、artifact hash、config checksum、code revision。
3. 盘点 `stock-screener`、`stock-analyzer`、`apps/data/command_brief` 的可研究 artifact。
4. 输出 field mapping audit：
   - `priority_score`
   - `best_score`
   - `score`
   - `final_score`
   - `tier`
   - `execution_gate_status`
   - `execution_quality`
   - `capital_score`
5. 盘点价格、复权、交易日历、涨跌停、停牌字段来源。
6. 新建 `packages/quant` 最小包：
   - `__init__.py`
   - `schemas.py`
   - `paths.py`
   - config loader
7. 新建 `data/config/quant-research.json`。

交付物：

- `data/quant/baselines/quant_baseline_manifest.json`
- `data/quant/reports/field_mapping_audit_latest.md`
- `data/quant/reports/price_execution_audit_latest.md`
- `packages/quant/` 最小骨架
- `data/config/quant-research.json`

验收标准：

- baseline artifact 可复现。
- 每个 P0 因子字段覆盖率清楚。
- 覆盖率不足或语义不明的字段不得进入正式因子结论。
- 价格和执行假设缺口被明确记录。

### Sprint 1: 研究面板、PIT、收益标签

目标：把现有输出转成可验证样本。

任务：

1. 通过 canonical adapter 读取现有 artifact。
2. 生成 `daily_signal_panel.jsonl`。
3. 新增 eligible universe snapshot。
4. 新增 pipeline stage ledger：
   - universe
   - scan_candidate
   - ai_screened
   - shortlisted
   - confirmed
   - downgraded
   - watchlist
5. 为样本和关键 feature 写 PIT provenance。
6. 生成 forward labels：
   - raw return
   - net return
   - excess return
   - MAE/MFE
   - limit blocked
   - suspended
7. 输出 panel coverage 和 label coverage。

交付物：

- `data/quant/panels/daily_signal_panel.jsonl`
- `data/quant/panels/eligible_universe_snapshot.jsonl`
- `data/quant/ledgers/pipeline_stage_ledger.jsonl`
- `data/quant/labels/forward_return_labels.jsonl`
- `data/quant/reports/panel_coverage_latest.md`
- `data/quant/reports/label_coverage_latest.md`

验收标准：

- PIT 失败样本可以出现在覆盖率报告，但不能进入正式评估集合。
- 标签包含交易成本、T+1、涨跌停、停牌标记。
- 每个信号能追到 source artifact。
- 样本行、feature、label 的缺失率可量化。

### Sprint 2: 因子评估、最小回测、Report-Only Gate

目标：先产出量化证据，不改变生产排序。

任务：

1. 评估现有 score 字段：
   - `priority_score`
   - `best_score`
   - `score`
   - 可映射的 `final_score`
2. 评估 tier 单调性。
3. 评估 execution gate。
4. 评估 execution quality。
5. 评估 capital flow normalization。
6. 验证 AI 二筛是否改善 scan 原始候选。
7. 验证午盘 confirmed/downgrade 的后验表现。
8. 实现最小组合回测：
   - `top_n_raw_score`
   - `gate_filtered_top_n`
9. 输出 `quant_health_latest.json/md`。
10. 接入现有 evaluation，但只 report-only。

交付物：

- `data/quant/reports/factor_evaluation_latest.md`
- `data/quant/reports/portfolio_backtest_latest.md`
- `data/quant/reports/quant_health_latest.md`
- `data/quant/reports/quant_health_latest.json`
- evaluation scorecard 中新增 report-only quant summary

验收标准：

- 3/5/10 日重叠收益必须标记 Newey-West、block bootstrap 或 walk-forward 状态。
- top N 回测扣除成本。
- gate off/limited/on 的收益和回撤拆分清楚。
- `quant_health_score` 不阻断生产。
- 任何 Expected 5D / Prism Edge 只能 research-only，不进入前端默认动作。

## 5. 页面处理原则

P0 不做视觉设计，不做量化页面开发。

P0 只做页面信息架构和字段契约草案：

| 页面 | P0 只定义什么 |
| --- | --- |
| Command Center | 是否有 quant status、是否 report stale、是否 gate 失败 |
| Discovery | raw score 与 research-only edge 的可选字段位置 |
| Stock Detail | Decision Light 的信息层级，不接生产动作 |
| Portfolio | 风险优先排序的未来字段，不改当前分组 |
| Review | quant health、tier monotonicity、backtest summary 的位置 |
| Settings | quant task 和 report preview 的未来入口 |

字段原则：

- `Decision Light` 可以作为第一层信息架构。
- `Prism Edge`、`Expected 5D`、`Downside` 必须是第二层证据。
- 没有样本量、置信度、PIT 证明时，只能显示“证据不足”。
- P0 不允许这些字段影响生产排序或开仓建议。

## 6. 待拍板问题

这些问题需要在 P0 开发前拍板：

| 问题 | 建议 |
| --- | --- |
| P0 gate 是否只 report-only | 是 |
| 新量化字段是否影响生产排序 | 否 |
| P0 是否只用 JSONL | 是，Parquet 延后 |
| 主 entry model | 建议先用 next open，next close 作为对照 |
| 主 benchmark | 建议 CSI500 为主，HS300 和 equal-weight pool 为辅 |
| 是否必须补 eligible universe | 是 |
| 成本模型是否拆分 | 是，佣金、印花税、滑点、冲击成本分开 |
| canonical loader 是否迁移 | P0 先 adapter，P1 再考虑迁 package |
| 题材状态机是否延后 | 是 |
| 复杂 ML 是否延后 | 是 |
| 什么时候升级 hard gate | 至少两个样本外窗口和执行回测通过后 |

## 7. 修订版 P0 开发卡

| ID | 任务 | 交付物 | 验收 |
| --- | --- | --- | --- |
| P0-01 | baseline manifest | `quant_baseline_manifest.json` | hash/config/code revision 完整 |
| P0-02 | quant package skeleton | `packages/quant` | import 和路径初始化可用 |
| P0-03 | field mapping audit | `field_mapping_audit_latest.md` | 字段语义和覆盖率清楚 |
| P0-04 | price/execution audit | `price_execution_audit_latest.md` | calendar、复权、limit/suspend、成本缺口清楚 |
| P0-05 | canonical adapter | quant loader helper | 不散读不稳定路径 |
| P0-06 | signal panel | `daily_signal_panel.jsonl` | 每行可追 source artifact |
| P0-07 | eligible universe ledger | universe + stage ledger | 有 inclusion reason 和 pipeline stage |
| P0-08 | PIT provenance | panel feature metadata | PIT 失败可识别、可排除 |
| P0-09 | forward labels | `forward_return_labels.jsonl` | raw/net/excess、MAE/MFE、limit/suspend |
| P0-10 | coverage reports | panel/label reports | 缺失率、PIT fail、样本量清楚 |
| P0-11 | factor eval | factor report | score/tier/gate/execution/capital flow |
| P0-12 | posterior validation | eval report sections | AI 二筛、午盘确认/降级有后验统计 |
| P0-13 | minimal backtest | backtest report | top N raw score、gate filtered top N |
| P0-14 | quant health | health json/md | report-only 接入 evaluation |
| P0-15 | tests | pytest | PIT、label、factor、overlap、backtest 测试 |

## 8. P0 完成定义

P0 完成时，Prism 需要能回答：

1. 当前历史 artifact 是否可复现。
2. 哪些字段能研究，哪些字段覆盖率不足。
3. 每条信号是否满足 PIT。
4. 每条信号未来 1/3/5/10 日收益、MAE/MFE、执行限制是什么。
5. 当前 score/tier/gate/execution_quality/capital flow 是否有后验价值。
6. AI 二筛是否真的改善候选。
7. 午盘确认和降级是否真的有用。
8. 每天买 top N raw score 和 gate filtered top N 扣成本后表现如何。
9. 当前量化健康度是否优于 baseline。
10. 哪些结论只能 research-only，不能进入生产动作。

## 9. 下一步

建议下一步不是做页面，而是按下面顺序开工：

1. 开 P0 评审会，拍板第 6 节问题。
2. 建 `packages/quant` 和 `quant-research.json`。
3. 做 field mapping audit 和 price/execution audit。
4. 再开始写 research panel。

只要 field mapping 和价格执行假设没审清楚，后面的回测和页面都应该暂停。
