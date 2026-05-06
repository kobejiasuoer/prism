# Prism Free-Source FS-2 Provider Mapping Plan 独立验收报告

Date: 2026-04-30
Role: independent acceptance reviewer
Scope: FS-2 provider contract mapping planning docs only
Status: passed

## 0. 验收边界

本次只读验收：

- `docs/quant-upgrade-free-source-fs2-provider-mapping-plan-2026-04-30.md`
- `docs/quant-upgrade-master-progress-and-handoff-2026-04-29.md`，仅顺带核对 3 号台账是否扩大范围

本次没有写代码，没有调用 BaoStock / AKShare，没有安装依赖，没有写 `packages/quant`，没有写 `data/quant`，没有修改依赖文件 / lockfile / venv，没有提交 raw vendor data，没有生成 formal labels、formal excess return、formal adjusted return 或 execution-realistic backtest，也没有接生产排序、A/B/C、页面、Prism Edge、Expected 5D 或 ML。

本报告是本次验收唯一新增产物，位于 `docs/`。

## 1. 总体验收结论

结论：**通过**。

是否允许进入 **FS-2 代码实现**：**允许，但仅限 synthetic-only provider contract mapping**。

FS-2 代码仍必须保持：

- no-network。
- synthetic-only。
- no `data/quant`。
- no provider imports。
- no BaoStock / AKShare installation。
- no raw archive writes。
- no formal outputs。
- no production sorting / A/B/C / page / Prism Edge / Expected 5D / ML。

是否允许直接进入 FS-3：**不允许**。FS-3 仍需先完成 FS-2 实现、FS-2 独立验收、FS-3 planning 和单独审批。

## 2. 十二项重点验收

| # | 检查项 | 结果 | 验收意见 |
| --- | --- | --- | --- |
| 1 | FS-2 是否仍保持 synthetic-only | 通过 | FS-2 Decision 明确 use synthetic mapping metadata and synthetic tests only。 |
| 2 | 是否只规划 provider raw-field-to-canonical mapping metadata | 通过 | Scope 和 Final Recommendation 均限定为 raw-field-to-canonical mapping metadata，不加 live adapters、runners、reports 或 provider calls。 |
| 3 | 是否没有授权 live provider call / imports / dependency change / `data/quant` output | 通过 | Boundary 和 decision table 明确禁止 BaoStock / AKShare calls/imports、network libraries、dependency / lockfile / venv changes、`data/quant` writes、raw archive output。 |
| 4 | 允许文件范围是否足够小 | 通过 | 仅建议 `provider_contracts.py`、`canonical_mapping.py`、`tests/test_quant_free_source_mapping.py`、`tests/test_quant_free_source_guardrails.py`。 |
| 5 | 是否默认不修改 FS-1 文件 | 通过 | 默认答案为 FS-2 should not modify FS-1 files；如修改必须在 FS-2 acceptance 中说明原因。 |
| 6 | BaoStock mapping 是否覆盖必要 layer | 通过 | 覆盖 calendar、stock basic、raw daily、qfq candidate、index daily、`tradestatus` / `isST`。 |
| 7 | AKShare mapping 是否覆盖 cross-check / supplement layer | 通过 | 覆盖 raw daily cross-check、qfq candidate cross-check、index daily supplement、suspend event event-only。 |
| 8 | formal / execution blockers 是否继续 blocked | 通过 | limit up/down、failed order、partial fill、formal adjusted return、formal excess return、formal labels、execution-realistic backtest 均列为 blocked。 |
| 9 | 测试计划是否证明 no-network / synthetic-only / no provider imports / no `data/quant` / no formal outputs / no production impact | 通过 | Test Plan 明确 AST-scan provider/network imports、synthetic constants、no raw archive path、no `data/quant` writes、blocked capabilities 和 no production/page/ML imports。 |
| 10 | 是否明确 FS-2 完成后不自动允许 FS-3 | 通过 | FS-3 Gate 明确 FS-2 completion does not automatically allow FS-3，需单独 FS-3 planning 和 approval。 |
| 11 | 是否继续暂缓页面、Prism Edge、Expected 5D、A/B/C、ML | 通过 | Page Route Deferral 和 blocked capabilities 明确这些 surface deferred / blocked。 |
| 12 | 3 号台账是否只记录 FS-1 通过和 FS-2 planning next | 通过 | 台账状态和 2026-04-30 更新写明 FS-1 schema-only + synthetic tests 已通过，当前下一步是 FS-2 provider contract mapping planning；未授权 FS-2 代码、FS-3、页面或生产接入。 |

## 3. 3 号台账核对

`docs/quant-upgrade-master-progress-and-handoff-2026-04-29.md` 当前为已修改状态；本次只读核对其免费数据源相关段落。

验收判断：

- 台账记录免费数据源路线已完成 FS-1 schema-only + synthetic tests。
- 台账记录 FS-1 independent acceptance passed。
- 台账记录当前下一步为 FS-2 provider contract mapping planning。
- 台账继续禁止生产排序、A/B/C、页面、Prism Edge、Expected 5D、ML。
- 台账继续禁止 formal labels、formal excess return、formal adjusted return、execution-realistic backtest。

未发现台账将范围扩大到 FS-2 代码、FS-3 live smoke、主线接入或页面路线。

## 4. FS-2 允许范围

允许进入 FS-2 代码实现，但只能围绕以下文件和职责：

- `packages/quant/free_sources/provider_contracts.py`：provider endpoint 和 raw field metadata，declarative only。
- `packages/quant/free_sources/canonical_mapping.py`: pure mapping helpers over synthetic metadata。
- `tests/test_quant_free_source_mapping.py`: synthetic mapping coverage tests。
- `tests/test_quant_free_source_guardrails.py`: no provider / no network / no formal / no production guardrail tests。

FS-2 默认不得修改 FS-1 文件。若确需修改 `__init__.py`、`contracts.py`、`manifest.py`、`redaction.py` 或 FS-1 测试，FS-2 实现说明和验收报告必须写明原因。

FS-2 不得创建：

- `baostock_adapter.py`
- `akshare_adapter.py`
- `run_field_poc.py`
- `report_generator.py`
- `data/quant/**`
- app / page / frontend path

## 5. 保留条件

FS-2 通过验收前必须继续满足：

1. no-network：模块和测试不得 import 或触发网络。
2. no provider imports：不得 import `baostock`、`akshare` 或 vendor SDK。
3. synthetic-only：mapping 只能是字段名、endpoint 字符串、canonical candidate 和 status metadata。
4. no dependency changes：不得改依赖文件、lockfile 或 venv。
5. no `data/quant`：不得创建、修改或清理 `data/quant`。
6. no raw vendor data：不得写 raw response、raw archive、CSV、截图、行级价格、日期数组、完整股票列表或 suspend event rows。
7. qfq、benchmark、execution fields 只能保持 candidate / research_only / partial。
8. formal adjusted return、formal excess return、formal labels、execution-realistic backtest、limit up/down、failed order、partial fill 继续 blocked。
9. 生产排序、A/B/C、页面、Prism Edge、Expected 5D、ML 和既有 factor/backtest/health/report 逻辑继续不得触碰。
10. FS-2 完成后不得自动进入 FS-3；必须另写 FS-3 planning 并单独验收。

## 6. 下一步建议

建议下一步开 FS-2 实现卡，标题和范围应明确写：

- Scope: synthetic-only provider raw-field-to-canonical mapping metadata.
- Allowed files: only the four FS-2 paths listed above, plus explicitly justified FS-1 export update if needed.
- Tests: no-network, no provider imports, synthetic-only.
- Data policy: no `data/quant`, no raw archive, no repo-external scratch output.
- Output policy: no formal labels, no formal excess return, no formal adjusted return, no execution-realistic backtest.
- Gate: FS-2 completion does not permit FS-3.

FS-2 完成后需独立验收：

- pathspec 是否只包含允许文件。
- BaoStock / AKShare mapping coverage 是否与计划一致。
- blocked capabilities 是否保持 blocked。
- guardrails 是否证明 no provider imports、no network imports、no `data/quant`、no formal outputs、no production impact。

## 7. 最终裁决

FS-2 provider mapping plan 验收结论：**通过**。

允许进入：**FS-2 synthetic-only provider contract mapping 代码实现**。

FS-2 代码必须保持：**no-network、synthetic-only、no `data/quant`、no provider imports**。

不允许进入：**直接 FS-3**。

核心判断：FS-2 planning 已把下一步收束到纯 metadata mapping 和 synthetic tests；没有提前授权 live smoke、provider imports、依赖变更、`data/quant` 输出、raw archive、formal outputs、生产接入或页面路线。
