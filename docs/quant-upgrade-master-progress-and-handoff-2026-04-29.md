# Prism 量化升级总控进度与交接台账

Date: 2026-04-29
Role: PMO / project secretary
Scope: documentation control only
Status: master progress and handoff ledger; PR 1 and PR 2 committed, dirty worktree cleanup next

## 0. 本文边界

本文只做总控台账和交接整理，不开发业务代码，不生成或覆盖已有量化报告。

严格边界：

- 不修改 `packages/quant`。
- 不修改 `data/quant`。
- 不修改 `tests`。
- 不覆盖任何已有报告。
- 不做页面、Prism Edge、Expected 5D 默认展示、生产排序、A/B/C 替换或 ML。
- 所有量化结果继续保持 `report-only` / `research-only` / `research_only_simulation`。

## 1. 项目当前总状态

### 1.1 当前阶段

当前处于 **P1-A Benchmark & Execution Data Hardening** 阶段，具体位置是：

```text
P0 scope approval
  -> Sprint 0 completed
  -> Sprint 1 completed
  -> Sprint 2 completed and conditionally accepted
  -> P1-A Card 1 benchmark completed and accepted
  -> P1-A Card 2 adjusted price policy completed and accepted
  -> P1-A Card 3 execution flags completed and accepted
  -> P1-A Card 4 label hardening completed and accepted
  -> P1-A Card 5 rerun reports completed and accepted
  -> P1-A internal data hardening can stage-close
  -> external data source research completed
  -> external data source decision pack completed
  -> previous four-AI task round completed
  -> next stage is Tushare Pro non-production POC
  -> Tushare Pro non-production POC completed
  -> POC conclusion: completed with blockers / conditional continue
  -> source design / blocker matrix conditionally accepted by second AI
  -> repo isolation gate: change inventory and acceptance conditionally passed
  -> stage pathspec plan and acceptance completed
  -> PR 1 staged diff re-accepted
  -> PR 1 / Commit 1 created: 1ef4614e1753d9f7776b53d6a6b588ee62ed15aa
  -> PR 2 / Commit 2 created: 606dc5276843846576cce7448e3fc83ec0c726a4
  -> next stage: handle remaining unrelated dirty worktree
```

Sprint 2 的独立验收结论是 **有条件通过**。允许进入 P1 的范围仅限数据补强、shadow-only 预研和页面信息架构草案；不允许进入生产排序、A/B/C 替换、真实页面接入 Prism Edge、Expected 5D 默认展示、ML 或 hard gate。

P1-A Card 1 的独立验收结论是 **通过**。但 Card 1 只完成了 `eligible_universe_equal_weight` 的 research-only internal benchmark；`CSI500` 和 `HS300` 仍为 unavailable，因此仍不允许生成 formal excess return。

P1-A Card 2 / 3 / 4 / 5 均已通过独立验收。它们完成的是内部可得数据的 policy freeze、availability freeze、hardened label sidecar 和 report-only rerun，不代表 formal benchmark、formal adjusted return 或 execution-realistic return 已经完成。

外部数据源调研和外部数据源决策包已完成。**Tushare Pro non-production POC 已完成**，POC 结论为 **completed with blockers / 有条件继续**。Tushare source design / blocker matrix 已通过二号 AI 有条件验收。change inventory 和验收已完成，结论为有条件通过。stage pathspec plan 和验收已完成。Quant core + P1-A internal hardening staged diff 已通过复验并已提交。PR 1 / Commit 1 已创建，commit hash 为 `1ef4614e1753d9f7776b53d6a6b588ee62ed15aa`。PR 2 / Commit 2 已创建，commit hash 为 `606dc5276843846576cce7448e3fc83ec0c726a4`。下一步不是开发，而是处理剩余 dirty worktree 的无关运行态 / 缓存 / 页面 / stock 数据。

四个 AI 的上一轮任务均已完成。当前不进入主线开发，也不开发新功能；当前工作区存在大量 modified / untracked 文件，后续禁止 `git add .`。Tushare token 已人工轮换，旧 token 不再允许使用。

### 1.2 当前 POC 状态

当前没有正在开发的 P1-A 内部数据硬化卡。

Tushare Pro 非生产 POC 已完成。

POC 结论：

- **completed with blockers / 有条件继续**。

已确认可用字段：

- daily raw OHLCV。
- `adj_factor`。
- `stock_basic`。

阻塞字段 / 风险：

- `trade_cal` 权限/积分不足。
- `index_daily` 权限/积分不足。
- `stk_limit` 权限/积分不足。
- `suspend_d` 字段不完整。
- `pro_bar` 需要 SDK 验证。

数据与 token 边界：

- raw response 只写在 repo 外，没有进入 repo。
- Tushare token 已人工轮换。
- 旧 token 不再允许使用。
- 新 token 不得写入代码、文档、日志或 git。
- 后续如需调用 Tushare，只能从本地环境变量 `TUSHARE_TOKEN` 读取。
- Tushare Pro 账号/token 仍由人工维护。
- 后续任何长期使用前，必须重新确认 token 权限、积分/费用和授权边界。

### 1.3 当前仓库隔离门

Tushare source design / blocker matrix 已通过二号 AI 有条件验收，当前没有进入 adapter 开发。

change inventory 和对应验收已完成，结论为有条件通过。stage pathspec plan 和验收已完成。Quant core + P1-A internal hardening staged diff 已通过复验，并已提交。

PR 1 / Commit 1 已创建：

- Commit hash：`1ef4614e1753d9f7776b53d6a6b588ee62ed15aa`。
- Commit subject：`quant: add report-only research spine and p1a hardening`。
- 包含：`packages/quant`、`tests/test_quant*`、`data/config/quant-research.json`、`data/quant` generated research artifacts、P0 / P1-A docs。
- 不包含：Tushare docs、external docs、`apps`、`stock-screener`、`stock-analyzer`、raw vendor data、token。

PR 2 / Commit 2 已创建：

- Commit hash：`606dc5276843846576cce7448e3fc83ec0c726a4`。
- Commit subject：`docs: add external data and tushare poc governance`。
- 该提交是 External / Tushare / governance docs-only。
- 不包含：`packages`、`data`、`apps`、`stock-screener`、`stock-analyzer`、raw vendor data、token、secret。

当前量化升级已完成两个安全提交：

- PR 1：Quant core + P1-A internal hardening。
- PR 2：External / Tushare governance docs。

Owner 已调整实际 staging 策略：

- PR 1：合并 P0 / Sprint 0-2 与 P1-A internal hardening。
- PR 2：后续再做 Tushare docs-only。

调整理由：

- shared files 已经处于 P1-A 最终态，硬拆 P0 / Sprint 与 P1-A 会造成语义不清。
- 本次允许提交 `data/quant` generated research artifacts，理由是 report-only 复现与测试依赖。
- 这些 `data/quant` generated research artifacts 不是 raw vendor data。

当前执行分工：

- 1 号 AI：已完成 PR 1 stage-only 和 Commit 1 创建。
- 2 号 AI：已完成 Quant core + P1-A internal hardening staged diff 复验。
- PR 2：External / Tushare governance docs-only 已创建。
- 下一阶段：处理剩余 dirty worktree 的无关运行态 / 缓存 / 页面 / stock 数据。

剩余 dirty worktree 处理边界：

- 仍禁止 `git add .`。
- 禁止 stage unrelated runtime / cache / current-state 数据。
- 禁止把未 staged 的运行态 / cache / current-state 数据混入后续提交。
- 禁止 stage raw vendor data。
- 禁止 stage token、secret 或付费账号凭据。
- 任何后续提交都必须先有明确 pathspec 和 staged diff 验收。

已通过验收的最近卡：

- P1-A Card 3 execution flags：通过；但 execution-realistic return 不允许，backtest 仍为 `research_only_simulation`。
- P1-A Card 4 label hardening：通过；但全部 `formal_label_ready=false`，全部 `formal_execution_eligible=false`。
- P1-A Card 5 rerun reports：通过；已使用 hardened labels 重跑 report-only 报告，但仍无 formal excess、formal adjusted 或 execution-realistic 升级。

剩余 dirty worktree 处理期间：

- 不进入 adapter 开发。
- 不接主线代码。
- 不开发新功能。
- 不实现新功能。
- 不生成 formal labels。
- 不生成 formal excess return。
- 不生成 execution-realistic backtest。
- 不影响生产排序。
- 不提交 raw vendor data。
- 不执行 `git add .`。
- 不执行 commit。

当前只允许处理剩余 dirty worktree 的无关运行态 / 缓存 / 页面 / stock 数据，不允许开发新功能。

### 1.4 当前不能做的事项

当前明确不能做：

- 不改生产排序。
- 不替换 A/B/C。
- 不做页面。
- 不做 Prism Edge 产品化。
- 不做 Expected 5D 默认展示。
- 不做 ML。
- 不做 hard gate 阻断生产。
- 不接主线代码。
- 不写 `data/quant`。
- 不提交 raw vendor 数据。
- 验收通过前不进入 adapter 开发。
- 剩余 dirty worktree 处理期间不进入 adapter 开发。
- 禁止 `git add .`。
- 任何后续提交都必须先完成明确 pathspec 和 staged diff 验收。
- 旧 token 不允许继续使用。
- 新 token 不得写入代码、文档、日志或 git。
- 后续如需调用 Tushare，只能从本地环境变量 `TUSHARE_TOKEN` 读取。
- 不把 research-only / report-only / simulation 结论说成可实盘执行。
- 不在 `CSI500` / `HS300` market benchmark unavailable 时输出 formal excess return。
- 不在 qfq / adj_factor、停牌、涨跌停、failed order、partial fill 未补齐时宣称 execution-realistic backtest。
- P1-A 仍然不是 production-ready。
- formal benchmark 未完成。
- formal adjusted return 未完成。
- execution-realistic return 未完成。

## 2. 文档索引

| 文档 | 用途 |
| --- | --- |
| `docs/quant-upgrade-design-2026-04-27.md` | 原始量化升级设计文档，提出从经验型研究系统升级为证据驱动的量化研究与决策系统，定义 quant spine、研究面板、因子评估、回测、health gate 等目标架构。 |
| `docs/quant-upgrade-task-breakdown-2026-04-28.md` | 完整升级 backlog，覆盖 Phase 0 到 Phase 8。该文档是长期任务池，不等于当前 P0/P1-A 执行范围。 |
| `docs/quant-upgrade-p0-review-revision-2026-04-28.md` | P0 评审修订稿和 scope approval。明确 P0 收缩为 baseline、field audit、eligible universe、research panel、PIT、labels、factor evaluation、minimal backtest、report-only quant health。 |
| `docs/quant-upgrade-p0-execution-flow-2026-04-28.md` | P0 / Sprint 0 开发交接流程，给开发者定义 Sprint 0 的执行顺序、交付物和禁止事项。 |
| `docs/quant-upgrade-sprint2-acceptance-report-2026-04-28.md` | Sprint 2 独立验收报告。结论为有条件通过，允许进入 P1 数据补强，但禁止生产化、页面、A/B/C 替换、Prism Edge、Expected 5D 和 ML。 |
| `docs/quant-upgrade-p1-data-hardening-plan-2026-04-28.md` | P1 数据硬化方案，聚焦 benchmark、复权、停牌、涨跌停、failed order、partial fill、2026 labels formal 化等缺口。 |
| `docs/quant-upgrade-p1a-hardening-acceptance-checklist-2026-04-28.md` | P1-A benchmark 与 execution data hardening 的验收清单，定义 benchmark、adjusted price、execution data、label 升级、重跑 Sprint 2 的通过标准。 |
| `docs/quant-upgrade-p1a-decision-matrix-2026-04-28.md` | P1-A 决策矩阵和首张开发卡模板，给出 CSI500 primary、HS300 secondary、eligible equal-weight internal、前复权作为 formal target 的建议。 |
| `docs/quant-upgrade-p1a-source-inventory-and-implementation-plan-2026-04-28.md` | P1-A 数据源盘点与实施拆分。确认仓库没有 frozen CSI500/HS300 指数价格，现有 price cache 只有 raw OHLCV，没有复权和执行字段。 |
| `docs/quant-upgrade-p1a-card1-benchmark-acceptance-report-2026-04-28.md` | P1-A Card 1 benchmark 独立验收报告。确认 Card 1 通过，但仅 internal benchmark research-only，CSI500/HS300 仍 unavailable。 |
| `docs/quant-upgrade-p1a-card2-adjusted-price-implementation-plan-2026-04-28.md` | P1-A Card 2 adjusted price policy 实施计划。定义 raw、前复权、后复权边界，以及当前无法升级 formal adjusted return 的阻塞条件。 |
| `docs/quant-upgrade-p1a-card2-adjusted-price-acceptance-report-2026-04-28.md` | P1-A Card 2 独立验收报告。确认 adjusted price policy 通过，但 formal adjusted return、raw-to-adjusted upgrade、`formal_label_ready` 均不允许。 |
| `docs/quant-upgrade-p1a-card3-execution-flags-acceptance-report-2026-04-29.md` | P1-A Card 3 独立验收报告。确认 execution-data availability freeze 通过，但 execution-realistic return 和 `formal_execution_eligible` 不允许。 |
| `docs/quant-upgrade-p1a-card4-label-hardening-acceptance-report-2026-04-29.md` | P1-A Card 4 独立验收报告。确认 hardened label sidecar 通过，原始 labels 未覆盖，全部 labels 仍非 formal。 |
| `docs/quant-upgrade-p1a-card5-rerun-reports-acceptance-report-2026-04-29.md` | P1-A Card 5 独立验收报告。确认使用 hardened labels 重跑 Sprint 2 reports 通过，P1-A 内部数据硬化可以阶段性收口。 |
| `docs/quant-upgrade-p1a-external-data-source-research-2026-04-29.md` | 外部数据源调研文档。调研 benchmark、复权、执行数据、交易日历和费用规则，推荐 Tushare Pro P1-A MVP 与授权数据源 P1-B 路线。 |
| `docs/quant-upgrade-external-data-source-decision-pack-2026-04-29.md` | 外部数据源决策包。给出 manual approval 包，推荐第一候选为 Tushare Pro non-production POC，但仍需人工拍板 token、授权、成本和归档边界。 |

## 3. 已完成产物索引

### 3.1 `packages/quant` 已新增模块

当前 `packages/quant` 下已有源文件：

| 模块 | 用途 |
| --- | --- |
| `packages/quant/__init__.py` | quant package 入口。 |
| `packages/quant/schemas.py` | Sprint 0 baseline、field coverage 等类型契约。 |
| `packages/quant/paths.py` | repo、config、`data/quant/*` 路径常量和目录 helper。 |
| `packages/quant/config.py` | `data/config/quant-research.json` 的加载和 checksum。 |
| `packages/quant/build_research_panel.py` | Sprint 1 research panel、eligible universe、pipeline stage ledger、forward labels、coverage report 生成逻辑。 |
| `packages/quant/research_io.py` | Sprint 2 factor/backtest/health 共用的 JSONL、统计、join 和格式化 helper。 |
| `packages/quant/evaluate_factors.py` | Sprint 2 report-only factor evaluation，包含 formal factor 白名单、tier/gate/AI/midday 验证。 |
| `packages/quant/run_portfolio_backtest.py` | Sprint 2 minimal portfolio backtest，覆盖 `top_n_raw_score`、`gate_filtered_top_n`、entry model、holding window、成本和 research-only flags。 |
| `packages/quant/report_quant_health.py` | Sprint 2 quant health 汇总，输出 Markdown/JSON，保持 production impact 为 none。 |
| `packages/quant/build_benchmark_returns.py` | P1-A Card 1 benchmark outputs，生成 research-only internal equal-weight benchmark returns，并 manifest 化 CSI500/HS300 unavailable。 |
| `packages/quant/price_adjustment_policy.py` | P1-A Card 2 adjusted price policy freeze，审计 raw OHLCV 可用性和复权缺口；不生成 adjusted price。 |
| `packages/quant/execution_flags.py` | P1-A Card 3 execution availability freeze，审计停牌、涨跌停、failed order、partial fill 缺口；不生成 execution-realistic return。 |
| `packages/quant/upgrade_forward_labels.py` | P1-A Card 4 hardened label sidecar 生成逻辑，将 benchmark / adjustment / execution 状态合并到 sidecar；不覆盖原始 labels。 |

说明：`__pycache__` 只是不纳入产品产物索引的 Python 缓存文件。

### 3.2 `data/quant` 已有 manifest / reports / labels / benchmarks

当前 `data/quant` 下已有文件：

| 路径 | 用途 / 当前状态 |
| --- | --- |
| `data/quant/baselines/quant_baseline_manifest.json` | Sprint 0 baseline manifest。记录 1908 个 artifact，包含 price cache、AI history、scan history、reports、command brief、watchlist snapshot 等。 |
| `data/quant/panels/daily_signal_panel.jsonl` | Sprint 1 daily signal panel。当前 coverage report 记录 3896 行。 |
| `data/quant/panels/eligible_universe_snapshot.jsonl` | Sprint 1 eligible universe snapshot。当前 coverage report 记录 2958 行。 |
| `data/quant/ledgers/pipeline_stage_ledger.jsonl` | Sprint 1 pipeline stage ledger。当前 coverage report 记录 3896 行。 |
| `data/quant/labels/forward_return_labels.jsonl` | Sprint 1 raw/net forward labels。当前 11064 行，10818 行 available research-only，246 行 unavailable；全部 benchmark unavailable，excess deferred。 |
| `data/quant/benchmarks/benchmark_manifest.json` | P1-A Card 1 benchmark manifest。`eligible_universe_equal_weight` 为 research-only internal，`CSI500` / `HS300` unavailable。 |
| `data/quant/benchmarks/benchmark_returns.jsonl` | P1-A Card 1 internal benchmark returns。448 行，仅 `eligible_universe_equal_weight`，仅 2024。 |
| `data/quant/reports/field_mapping_audit_latest.md` | Sprint 0 字段映射审计，确认 `score` lane-scoped、`final_score` 不可直接进入正式结论。 |
| `data/quant/reports/price_execution_audit_latest.md` | Sprint 0 价格与执行审计，确认 raw OHLCV 可用于 research-only labels，但 benchmark、复权、停牌、涨跌停、failed/partial fill 缺失。 |
| `data/quant/reports/panel_coverage_latest.md` | Sprint 1 panel coverage report，记录 panel、universe、stage ledger 覆盖率和 PIT guardrails。 |
| `data/quant/reports/label_coverage_latest.md` | Sprint 1 label coverage report，记录 raw/net labels、entry models、holding windows 和 execution missing flags。 |
| `data/quant/reports/factor_evaluation_latest.md` | P1-A Card 5 已重跑，报告引用 hardened labels 状态分布；仍 report-only，不计算 excess return，不使用 `final_score`。 |
| `data/quant/reports/portfolio_backtest_latest.md` | P1-A Card 5 已重跑，仍为 `research_only_simulation`，不宣称 execution-realistic。 |
| `data/quant/reports/quant_health_latest.md` | P1-A Card 5 已重跑，production impact 为 none，not production-ready。 |
| `data/quant/reports/quant_health_latest.json` | P1-A Card 5 已重跑，`overall_status=report_only_hardened_not_production_ready`，hard gates 不阻断生产。 |
| `data/quant/reports/benchmark_coverage_latest.md` | P1-A Card 1 benchmark coverage report，确认 internal benchmark 和 CSI500/HS300 unavailable。 |
| `data/quant/price/price_adjustment_manifest.json` | P1-A Card 2 price adjustment manifest。确认 raw 可用、复权字段缺失、formal adjusted return unavailable。 |
| `data/quant/reports/price_adjustment_policy_latest.md` | P1-A Card 2 price adjustment policy report。说明 raw labels remain research-only。 |
| `data/quant/execution/execution_flags_manifest.json` | P1-A Card 3 execution flags manifest。确认停牌、涨跌停、failed order unavailable，partial fill deferred。 |
| `data/quant/reports/execution_flags_coverage_latest.md` | P1-A Card 3 execution coverage report。说明 backtest remains `research_only_simulation`。 |
| `data/quant/labels/forward_return_labels_hardened.jsonl` | P1-A Card 4 hardened label sidecar。11064 行，保留原始 label hash，全部 `formal_label_ready=false` / `formal_execution_eligible=false`。 |
| `data/quant/reports/label_hardening_latest.md` | P1-A Card 4 label hardening report。说明 sidecar 不覆盖原始 labels，不生成 formal labels。 |

### 3.3 `tests` 下已有 quant 测试

当前 quant 相关测试文件：

| 测试文件 | 覆盖内容 |
| --- | --- |
| `tests/test_quant_sprint1.py` | Sprint 1 panel score contract、AI/scan 字段 namespacing、execution gate batch/context、labels raw/net only 与 missing execution flags。 |
| `tests/test_quant_sprint2.py` | Sprint 2 guardrails：`final_score` 禁用、`score` 不跨 lane、gate context、benchmark unavailable 不算 excess、execution missing 强制 research-only backtest、portfolio win rate、insufficient sample、reports report-only。 |
| `tests/test_quant_p1a_benchmarks.py` | P1-A Card 1 benchmark contract：manifest、CSI500/HS300 unavailable、eligible equal-weight research-only、2026 exclusion、labels 未注入 excess return。 |
| `tests/test_quant_p1a_adjusted_price.py` | P1-A Card 2 adjusted price guardrails：formal adjusted return not ready、labels 不升级、缺口字段显式。 |
| `tests/test_quant_p1a_execution_flags.py` | P1-A Card 3 execution flags guardrails：execution realism not ready、T+1 policy、labels 不升级。 |
| `tests/test_quant_p1a_label_hardening.py` | P1-A Card 4 hardened labels guardrails：sidecar 行数、原始 labels 未覆盖、formal/execution eligible 全 false。 |
| `tests/test_quant_p1a_rerun_reports.py` | P1-A Card 5 rerun reports guardrails：reports 使用 hardened labels、not production-ready、no formal excess。 |

## 4. 阶段结论摘要

### 4.1 Sprint 0 结论

Sprint 0 完成了地基冻结与审计：

- 新增 `packages/quant` 最小骨架和 `data/config/quant-research.json`。
- 生成 baseline manifest，记录 1908 个可追溯 artifact。
- 完成 field mapping audit：`score` 只能 lane-scoped；`priority_score` / `best_score` 可用于 AI lane；`final_score` 不得假设存在。
- 完成 price/execution audit：2024 price cache 支持 raw OHLCV replay，但不支持 formal adjusted return、formal excess return 或 execution-realistic backtest。

Sprint 0 结论：地基可用，但所有输出仍只能 research/report-only。

### 4.2 Sprint 1 结论

Sprint 1 完成 research panel、eligible universe、pipeline ledger 和 raw/net labels：

- `daily_signal_panel.jsonl`: 3896 行。
- `eligible_universe_snapshot.jsonl`: 2958 行。
- `pipeline_stage_ledger.jsonl`: 3896 行。
- `forward_return_labels.jsonl`: 11064 行。
- PIT status 全部 pass。
- 2026 artifact 只进入 coverage/context，不进入正式 forward label evaluation。

Sprint 1 结论：可以做 2024 research-only raw/net label 研究，但不能做 excess、adjusted 或 execution-realistic 结论。

### 4.3 Sprint 2 结论

Sprint 2 完成 factor evaluation、minimal portfolio backtest 和 quant health：

- factor evaluation 使用 `ai_priority_score`、`ai_best_score`、`scan_capital_score`、`scan_technical_score` 等 namespaced/lane-scoped 字段。
- `final_score` 和跨 lane `score` 未进入 formal evaluation。
- tier monotonicity 为 `insufficient_sample`。
- benchmark 全部 unavailable，因此不计算 excess return。
- minimal backtest 覆盖 `top_n_raw_score` 与 `gate_filtered_top_n`，但全部为 `research_only_simulation`。
- quant health production impact 为 `none`，hard gates 不阻断生产。

Sprint 2 独立验收结论：**有条件通过**。可以进入 P1 数据补强；不能产品化。

### 4.4 P1-A Card 1 结论

P1-A Card 1 benchmark 已通过验收：

- 生成 `benchmark_manifest.json`。
- 生成 `benchmark_returns.jsonl`，共 448 行。
- `eligible_universe_equal_weight` 是 research-only internal benchmark。
- `CSI500` 和 `HS300` 仍为 unavailable。
- 未向 `forward_return_labels.jsonl` 写入 `benchmark_return` 或 `excess_return`。
- 未重跑或升级 Sprint 2 factor/backtest/health 为 production-ready。

Card 1 结论：允许进入 Card 2，但不能解释为 primary market benchmark 已完成。

### 4.5 P1-A Card 2 结论

P1-A Card 2 adjusted price policy 已通过验收：

- formal target 使用前复权 / `qfq`，与 P1-A checklist 和 decision matrix 一致。
- raw price 仅作为 audit / diagnostic。
- 后复权不进入 PIT formal labels。
- 当前仓库仍没有 `adj_factor`、qfq/hfq、adjusted OHLC、`adjustment_policy` 或 PIT 复权可用性证明。
- formal adjusted return 不允许。
- raw return 不能当成 adjusted return。
- labels 不允许升级为 `formal_label_ready`。

Card 2 结论：通过的是 policy freeze 和缺口显式化，不是 formal adjusted return 完成。

### 4.6 P1-A Card 3 结论

P1-A Card 3 execution flags 已通过验收：

- 完成 execution-data availability freeze。
- 停牌、涨跌停、failed order 均显式 unavailable。
- partial fill 显式 deferred。
- T+1 和成本配置被引用，但不构成 execution-realistic backtest。
- labels 未升级为 `formal_execution_eligible`。
- 当前 backtest 仍为 `research_only_simulation`。

Card 3 结论：通过的是执行字段可得性审计和缺口冻结，不是 execution-realistic return 完成。

### 4.7 P1-A Card 4 结论

P1-A Card 4 label hardening 已通过验收：

- 生成 hardened label sidecar：`data/quant/labels/forward_return_labels_hardened.jsonl`。
- sidecar 行数与原始 labels 一致：11064 行。
- 原始 `forward_return_labels.jsonl` 未被覆盖。
- 全部 hardened labels 仍为 `formal_label_ready=false`。
- 全部 hardened labels 仍为 `formal_execution_eligible=false`。
- 没有 formal excess return、formal adjusted return 或 execution-realistic return。

Card 4 结论：通过的是 label 状态硬化和降级原因显式化，不是 formal labels 完成。

### 4.8 P1-A Card 5 结论

P1-A Card 5 rerun reports 已通过验收：

- 使用 hardened labels sidecar 重新生成 Sprint 2 factor/backtest/health reports。
- factor evaluation 仍禁用 `final_score`，`score` 仍 lane-scoped。
- backtest 仍为 `research_only_simulation`。
- quant health 明确 `report_only_hardened_not_production_ready`。
- formal excess return 未生成。
- formal adjusted return 未生成。
- execution-realistic return 未生成。
- production sorting、A/B/C、页面、Prism Edge、Expected 5D 和 ML 均未开放。

Card 5 结论：P1-A 内部数据硬化可以阶段性收口，但仍不是 production-ready。

### 4.9 外部数据源调研与决策包结论

外部数据源调研已完成：

- 已调研 benchmark、复权、执行数据、交易日历、T+1、费用、滑点和冲击成本。
- 推荐 P1-A 最小可行路线：Tushare Pro 授权主源 + 官方规则/费用文件 + 本地 raw response 私有归档。
- 推荐 P1-B 稳定路线：RiceQuant / JoinQuant / Wind / Choice / iFinD 授权源 + 交叉校验。
- 不建议用网页抓取、未授权 vendor raw data 入库、raw OHLCV 倒推复权或把 internal benchmark 当 market benchmark。

外部数据源决策包已完成：

- 推荐的待拍板候选方向是 **Tushare Pro non-production availability check**。
- POC 不得连接主 Prism quant pipeline。
- POC 不得写入 `packages/quant` 或 `data/quant`。
- POC 不得把 raw vendor data 提交到仓库。
- POC 只验证字段可得性、授权边界、source hash / timestamp 纪律和 raw response archive 设计。
- 当前 POC 已完成但有 blockers；source design / blocker matrix 已通过二号 AI 有条件验收。
- 四个 AI 的上一轮任务均已完成；POC runbook、POC acceptance checklist、字段矩阵和风险登记已作为上一轮准入材料完成。

Tushare Pro 非生产 POC 已完成，结论为 **completed with blockers / 有条件继续**：

- 可用字段：daily raw OHLCV、`adj_factor`、`stock_basic`。
- 阻塞字段：`trade_cal`、`index_daily`、`stk_limit` 权限/积分不足。
- 风险字段：`suspend_d` 字段不完整；`pro_bar` 需 SDK 验证。
- raw response 只写在 repo 外，没有进入 repo。
- Tushare token 已人工轮换，旧 token 不再允许使用。
- Tushare source design / blocker matrix 已通过二号 AI 有条件验收。
- 当前进入仓库隔离门，必须先完成 change inventory / commit plan；完成前不进入 adapter 开发。

### 4.10 当前阶段总判断

P1-A 内部数据硬化阶段可以阶段性收口。

当前结论：

- P1-A 仍然不是 production-ready。
- formal benchmark 未完成。
- formal adjusted return 未完成。
- execution-realistic return 未完成。
- 所有结论仍为 `report-only` / `research-only`。
- 不允许生产排序、A/B/C 替换、页面、Prism Edge、Expected 5D、ML。

## 5. 当前硬边界

以下硬边界继续有效，任何 AI 都不能绕过：

- 不改生产排序。
- 不替换 A/B/C。
- 不做页面。
- 不做 Prism Edge 产品化。
- 不做 Expected 5D 默认展示。
- 不做 ML。
- 所有量化结果仍为 `report-only` / `research-only`。
- `research_only_simulation` 不能被说成 execution-realistic backtest。
- `final_score` 不能进入 formal evaluation。
- `score` 不能跨 lane 合并。
- `execution_gate_status` 只能作为 batch/context，不是个股原生因子。
- benchmark unavailable 时不能输出 excess return。
- qfq / adj_factor / PIT 复权证明未完成时不能输出 formal adjusted return。
- 停牌、涨跌停、failed order、partial fill 未补齐时不能声明可执行回测。

## 6. 多 AI 分工建议

### 第一个 AI：外部数据 POC 执行

Tushare Pro non-production POC 已完成。token 已人工轮换，旧 token 不再允许使用；后续如需调用 Tushare，只能从本地环境变量 `TUSHARE_TOKEN` 读取。

职责：

- 只交接 POC 结果、字段可得性、授权边界、调用限制、source hash / timestamp 纪律和 raw response 私有归档设计。
- 不接入主 Prism quant pipeline。
- 不写入 `packages/quant`。
- 不写入 `data/quant`。
- 不提交 token、secret、raw vendor data 或付费数据。
- 不把新 token 写入代码、文档、日志或 git。
- 只产出 redacted manifest / redacted report 的可行性建议。

### 第二个 AI：外部数据 POC 验收

负责 Tushare Pro source design / blocker matrix 独立验收；当前结论为有条件通过。

职责：

- 检查是否遵守 non-production boundary。
- 检查是否泄漏 token、secret、raw vendor data 或付费账号信息。
- 检查是否误把 availability check 解释为 formal benchmark、formal adjusted return 或 execution-realistic return。
- 检查是否触碰 `packages/quant`、`data/quant`、production sorting、A/B/C、页面、Prism Edge、Expected 5D、ML。
- 检查 raw response 是否确实只在 repo 外。
- 检查旧 token 已禁用或不再使用。
- 检查新 token 未写入代码、文档、日志或 git。
- 检查后续调用设计是否只从本地环境变量 `TUSHARE_TOKEN` 读取。
- 输出独立验收报告，不写业务代码。
- 验收结论进入总控台账后，下一步仍不是开发，而是仓库隔离门。

### 第三个 AI：维护总控台账

负责本文档和后续总控文档维护。

职责：

- 只更新文档索引、阶段状态、产物索引、交接说明。
- 不写业务代码。
- 不修改 `packages/quant`、`data/quant`、`tests`。
- 不覆盖已有报告。
- 在 POC 拍板、POC 完成、POC 验收或外部数据路线变更后，同步总控台账。

## 7. 下一步决策点

当前下一步不是 adapter 开发，也不是新功能开发，而是处理剩余 dirty worktree 的无关运行态 / 缓存 / 页面 / stock 数据。

下一硬门槛：

- PR 1 / Commit 1 已创建：`1ef4614e1753d9f7776b53d6a6b588ee62ed15aa`。
- PR 1 已合并 P0 / Sprint 0-2 与 P1-A internal hardening。
- PR 1 已包含 `packages/quant`、`tests/test_quant*`、`data/config/quant-research.json`、`data/quant` generated research artifacts、P0 / P1-A docs。
- PR 1 不包含 Tushare docs、external docs、`apps`、`stock-screener`、`stock-analyzer`、raw vendor data、token。
- PR 2 / Commit 2 已创建：`606dc5276843846576cce7448e3fc83ec0c726a4`。
- PR 2 是 External / Tushare / governance docs-only。
- PR 2 不包含 `packages`、`data`、`apps`、`stock-screener`、`stock-analyzer`、raw vendor data、token、secret。
- 当前量化升级已完成两个安全提交：PR 1 Quant core + P1-A internal hardening；PR 2 External / Tushare governance docs。
- unrelated runtime / cache / current-state 数据默认不纳入量化 PR。
- 禁止使用 `git add .`。
- 禁止 stage raw vendor data、token、secret 或付费账号凭据。
- 人工再拍板 Tushare 权限/积分处理、换源/多源路线，或继续 internal research-only 路线。

剩余 dirty worktree 处理期间：

- 不进入 adapter 开发。
- 不接主线代码。
- 不开发新功能。
- 不生成 formal labels。
- 不生成 formal excess return。
- 不生成 execution-realistic backtest。
- 不影响生产排序。
- 不执行 `git add .`。
- 不 stage raw vendor data 或 token。
- 不 stage unrelated runtime / cache / current-state 数据。
- 新 token 不得写入代码、文档、日志或 git。
- 后续如需调用 Tushare，只能从本地环境变量 `TUSHARE_TOKEN` 读取。

## 8. 2026-04-29 更新：P1-A 内部硬化收口与外部数据 POC

P1-A 内部数据硬化阶段已可以阶段性收口：

- Card 1 benchmark manifest / internal benchmark returns 已通过验收。
- Card 2 adjusted price policy 已通过验收。
- Card 3 execution flags / execution data availability 已通过验收。
- Card 4 hardened labels sidecar 已通过验收。
- Card 5 rerun Sprint 2 reports using hardened labels 已通过验收。

当前仍未完成：

- CSI500 / HS300 formal market benchmark。
- qfq / adj_factor / formal adjusted return。
- suspend / limit up-down / failed order / partial fill 的可执行数据闭环。
- execution-realistic backtest。
- production-ready quant health。

当前外部数据源状态：

- 外部数据源调研已完成。
- 外部数据源决策包已完成。
- 四个 AI 的上一轮任务均已完成。
- Tushare Pro non-production POC 已完成。
- POC 结论是 completed with blockers / 有条件继续。
- Tushare source design / blocker matrix 已通过二号 AI 有条件验收。
- Tushare token 已人工轮换。
- 旧 token 不再允许使用。
- 新 token 不得写入代码、文档、日志或 git。
- 后续如需调用 Tushare，只能从本地环境变量 `TUSHARE_TOKEN` 读取。
- 下一阶段暂不进入开发。
- change inventory 和验收已完成，结论为有条件通过。
- stage pathspec plan 和验收已完成。
- Owner 决策：本次允许提交 `data/quant` generated research artifacts，理由是 report-only 复现与测试依赖；它们不是 raw vendor data。
- 实际 staging 策略调整为 PR 1 合并 P0 / Sprint 与 P1-A internal hardening，因为 shared files 已是 P1-A 最终态，硬拆会造成语义不清。
- Quant core + P1-A internal hardening staged diff 已通过复验。
- PR 1 / Commit 1 已创建：`1ef4614e1753d9f7776b53d6a6b588ee62ed15aa`。
- PR 1 包含 `packages/quant`、`tests/test_quant*`、`data/config/quant-research.json`、`data/quant` generated research artifacts、P0 / P1-A docs。
- PR 1 不包含 Tushare docs、external docs、`apps`、`stock-screener`、`stock-analyzer`、raw vendor data、token。
- PR 2 / Commit 2 已创建：`606dc5276843846576cce7448e3fc83ec0c726a4`。
- PR 2 是 External / Tushare / governance docs-only。
- PR 2 不包含 `packages`、`data`、`apps`、`stock-screener`、`stock-analyzer`、raw vendor data、token、secret。
- 当前量化升级已完成两个安全提交：PR 1 Quant core + P1-A internal hardening；PR 2 External / Tushare governance docs。
- 下一步不是开发，而是处理剩余 dirty worktree 的无关运行态 / 缓存 / 页面 / stock 数据。
- unrelated runtime / cache / current-state 数据默认不纳入量化 PR。
- 当前工作区存在大量 modified / untracked 文件，后续禁止 `git add .`。
- 后续人工再拍板 Tushare 权限/积分、换源/多源，或 internal research-only 路线。

外部数据 POC 仍禁止：

- 不改生产排序。
- 不替换 A/B/C。
- 不做页面。
- 不做 Prism Edge 产品化。
- 不做 Expected 5D 默认展示。
- 不做 ML。
- 不接主线代码。
- 不写 `packages/quant`。
- 不写 `data/quant`。
- 不提交 raw vendor 数据。
- 剩余 dirty worktree 处理阶段不进入 adapter 开发。
- 禁止 `git add .`。
- 禁止 stage unrelated runtime / cache / current-state 数据。
- 禁止 stage raw vendor data。
- 禁止 stage token、secret 或付费账号凭据。
- 任何后续提交都必须先完成明确 pathspec 和 staged diff 验收。
- 不允许使用旧 token。
- 不允许把新 token 写入代码、文档、日志或 git。
- 不从 POC 生成 formal labels、formal excess return、formal adjusted return 或 execution-realistic backtest。
- 不把 token、secret、付费账号凭据写入 git、日志、报告或共享产物。

## 9. 2026-04-30 更新：source design 验收后进入仓库隔离门

当时状态：

- Tushare source design / blocker matrix 已通过二号 AI 有条件验收。
- 下一阶段暂不进入开发。
- 当前进入仓库隔离门，必须先完成 change inventory / commit plan。
- 当前工作区存在大量 modified / untracked 文件，后续禁止 `git add .`。
- 仓库隔离门和对应验收通过前，不写 `packages/quant`，不写 `data/quant`，不实现 adapter，不提交 raw vendor data。
- 仓库隔离门和对应验收通过前，不进入主线开发，不生成 formal labels、formal excess return 或 execution-realistic backtest。
- 后续由人工再拍板 Tushare 权限/积分、换源/多源，或 internal research-only 路线。

## 10. 2026-04-30 更新：change inventory 验收后进入 stage pathspec plan

当时状态：

- change inventory 和验收已完成，结论为有条件通过。
- 当前进入实际 stage pathspec 计划阶段。
- 当前仍不允许开发新功能。
- 当前仍禁止 `git add .`。
- stage pathspec plan 的目标拆分为 PR A：P0 / Sprint，PR B：P1-A，PR C：Tushare docs-only。
- stage pathspec plan 验收通过前，不执行 `git add` / `commit`。
- unrelated runtime / cache / current-state 数据默认不纳入量化 PR。

## 11. 2026-04-30 更新：stage pathspec plan 验收后进入 PR 1 stage-only

当时状态：

- Stage pathspec plan 和验收已完成。
- Owner 决策：本次允许提交 `data/quant` generated research artifacts，理由是 report-only 复现与测试依赖；它们不是 raw vendor data。
- 实际 staging 策略调整为 PR 1 合并 P0 / Sprint 与 P1-A internal hardening，因为 shared files 已是 P1-A 最终态，硬拆会造成语义不清。
- PR 2 后续再做 Tushare docs-only。
- 当前 1 号 AI 正在执行 PR 1 stage-only。
- 2 号 AI 负责 staged diff 验收。
- 仍禁止 `git add .`。
- 禁止 stage unrelated runtime / cache / current-state 数据。
- 禁止 stage raw vendor data 或 token。

## 12. 2026-04-30 更新：PR 1 / Commit 1 已创建

当时状态：

- Quant core + P1-A internal hardening 已提交。
- PR 1 / Commit 1 已创建，commit hash 为 `1ef4614e1753d9f7776b53d6a6b588ee62ed15aa`。
- 该提交包含 `packages/quant`、`tests/test_quant*`、`data/config/quant-research.json`、`data/quant` generated research artifacts、P0 / P1-A docs。
- 该提交不包含 Tushare docs、external docs、`apps`、`stock-screener`、`stock-analyzer`、raw vendor data、token。
- 下一阶段是准备 PR 2：Tushare docs-only。
- 当前仍禁止把未 staged 的运行态 / cache / current-state 数据混入后续提交。

## 13. 2026-04-30 更新：PR 2 / Commit 2 已创建

当前最新状态：

- PR 2 / Commit 2 已创建。
- Commit hash：`606dc5276843846576cce7448e3fc83ec0c726a4`。
- 该提交是 External / Tushare / governance docs-only。
- 该提交不包含 `packages`、`data`、`apps`、`stock-screener`、`stock-analyzer`、raw vendor data、token、secret。
- 当前量化升级已完成两个安全提交：
  - PR 1：Quant core + P1-A internal hardening。
  - PR 2：External / Tushare governance docs。
- 下一步不是开发，而是处理剩余 dirty worktree 的无关运行态 / 缓存 / 页面 / stock 数据。

## 14. 当前 PMO 交接一句话

当前 Prism 量化升级已完成 P0 到 P1-A 内部数据硬化的 report-only 闭环，四个 AI 的上一轮任务均已完成，P1-A 可以阶段性收口，但仍不是 production-ready。Tushare Pro non-production POC 已完成，结论为 completed with blockers / 有条件继续；Tushare source design / blocker matrix 已通过二号 AI 有条件验收。change inventory 和验收已完成，结论为有条件通过；stage pathspec plan 和验收也已完成。当前量化升级已完成两个安全提交：PR 1 Quant core + P1-A internal hardening，commit `1ef4614e1753d9f7776b53d6a6b588ee62ed15aa`；PR 2 External / Tushare governance docs，commit `606dc5276843846576cce7448e3fc83ec0c726a4`。PR 2 不包含 packages、data、apps、stock-screener、stock-analyzer、raw vendor data、token 或 secret。下一步不是开发，而是处理剩余 dirty worktree 的无关运行态 / 缓存 / 页面 / stock 数据；后续由人工再拍板 Tushare 权限/积分、换源/多源，或 internal research-only 路线。
