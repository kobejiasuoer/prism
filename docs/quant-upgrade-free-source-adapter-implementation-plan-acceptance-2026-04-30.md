# Prism Free-Source Adapter Implementation Plan 独立验收报告

Date: 2026-04-30
Role: independent acceptance reviewer
Scope: `docs/quant-upgrade-free-source-adapter-implementation-plan-2026-04-30.md` only
Status: passed

## 0. 验收边界

本次只读验收：

- `docs/quant-upgrade-free-source-adapter-implementation-plan-2026-04-30.md`
- 当前 `git status --short`，仅用于确认相关路径背景风险

本次验收没有写代码，没有调用 BaoStock / AKShare，没有安装依赖，没有写 `packages/quant`，没有写 `data/quant`，没有修改依赖文件 / lockfile / venv，没有提交 raw vendor data，没有生成 formal labels、formal excess return、formal adjusted return 或 execution-realistic backtest，也没有接生产排序、A/B/C、页面、Prism Edge、Expected 5D 或 ML。

本报告是本次验收唯一新增产物，且位于 `docs/`。

## 1. 总体验收结论

结论：**通过**。

是否允许进入 **FS-1 代码实现**：**允许，但仅限 schema-only + synthetic tests 的极小范围**。

FS-1 必须保持：

- no-network。
- synthetic-only。
- no `data/quant`。
- no provider imports。
- no BaoStock / AKShare installation。
- no raw vendor data。
- no formal outputs。
- no production sorting / A/B/C / page / Prism Edge / Expected 5D / ML。

不允许进入：

- provider adapter implementation。
- live provider smoke。
- dependency / lockfile / venv changes。
- `data/quant` output。
- raw archive write。
- production or page integration。

## 2. 十四项重点验收

| # | 检查项 | 结果 | 验收意见 |
| --- | --- | --- | --- |
| 1 | 是否明确下一步只能进入 FS-1 schema-only + synthetic tests | 通过 | Implementation Entry Decision 明确 first implementation card should start with schema-only + synthetic tests。 |
| 2 | FS-1 是否不包含任何真实 provider call | 通过 | 明确 FS-1 must not import or call BaoStock / AKShare；no-network section 要求不导入 provider / network libraries。 |
| 3 | FS-1 是否不允许安装 BaoStock / AKShare | 通过 | 明确 FS-1 不安装依赖，BaoStock / AKShare installation not required and not allowed。 |
| 4 | FS-1 是否不允许写 `data/quant` | 通过 | Entry decision、policy、acceptance standards、forbidden pathspec 均禁止 `data/quant` output / writes。 |
| 5 | FS-1 是否不允许写 raw vendor data | 通过 | 明确 synthetic fixtures only，raw archive writes not included in FS-1，no raw vendor data in repo。 |
| 6 | FS-1 是否不允许生成 formal outputs | 通过 | formal labels、adjusted return、excess return、execution-realistic backtest 全部 blocked；测试要求 no formal outputs are generated。 |
| 7 | FS-1 是否不影响生产排序、A/B/C、页面、Prism Edge、Expected 5D、ML | 通过 | No Production Impact Guarantee 明确所有 surface 不连接、不输出、不导入；acceptance standards 也覆盖。 |
| 8 | 建议文件范围是否足够小且明确 | 通过 | 精确限制为 `packages/quant/free_sources/__init__.py`、`manifest.py`、`contracts.py`、`redaction.py` 和 `tests/test_quant_free_source_manifest.py`。 |
| 9 | 测试是否明确 no network、no provider imports、synthetic-only | 通过 | No-Network Guarantee 和 acceptance standards 明确 tests pass without network and without importing provider packages；fixtures in memory。 |
| 10 | redaction 规则是否阻止 raw rows / full datasets / secrets / paths | 通过 | 明确拒绝 row-level price fields、full calendar、full stock list、raw payload、absolute local paths、URLs、token/cookie/session/password/secret/authorization。 |
| 11 | status enum 是否覆盖必要状态 | 通过 | `ManifestStatus` 覆盖 `available`、`partial`、`missing`、`empty`、`network_error`、`provider_error`、`license_blocked`、`blocked`。 |
| 12 | 是否明确 qfq、benchmark、execution flags 仍是 candidate / research_only / blocked | 通过 | qfq price 为 `research_only` / `candidate`，benchmark index daily 为 `candidate`，`tradestatus` / `isST` 为 `candidate` / `research_only`，limit / failed order / partial fill blocked。 |
| 13 | FS-2 到 FS-5 是否拆分合理且未提前授权 live smoke 或主线接入 | 通过 | FS-2 仍 synthetic；FS-3 live smoke 仅在 explicit approval 后 repo-external；FS-5 需 FS-1 至 FS-4 通过并反复验收；未授权主线接入。 |
| 14 | 是否继续暂缓页面路线 | 通过 | Page Route Deferral 明确 control panel、quant health、Prism Edge、Expected 5D、A/B/C display、any frontend route 均 deferred。 |

## 3. FS-1 允许范围

允许进入 FS-1 代码实现，但只能创建或修改以下文件：

- `packages/quant/free_sources/__init__.py`
- `packages/quant/free_sources/manifest.py`
- `packages/quant/free_sources/contracts.py`
- `packages/quant/free_sources/redaction.py`
- `tests/test_quant_free_source_manifest.py`

FS-1 只能实现：

- redacted manifest schema。
- enum / status constants。
- candidate field contract metadata。
- redaction validation。
- synthetic-only tests。

FS-1 不得实现：

- `baostock_adapter.py`。
- `akshare_adapter.py`。
- `run_field_poc.py`。
- `report_generator.py`。
- live provider calls。
- raw archive writes。
- `data/quant` outputs。
- formal labels / returns / backtests。

## 4. Repo 边界核对

当前针对目标文档、目标验收文档、`packages/quant`、`data/quant` 和常见依赖 / lockfile / venv 路径的 `git status --short` 检查显示：

- `docs/quant-upgrade-free-source-adapter-implementation-plan-2026-04-30.md` 为未跟踪文档。
- 本验收前目标验收报告不存在。
- 未发现 `packages/quant`、`data/quant`、dependency / lockfile / `.venv` / `venv` 相关变更进入本次验收范围。

工作区仍有与本验收无关的既有脏改动；FS-1 若执行，必须使用显式 pathspec，禁止 `git add .`。

## 5. 保留条件

FS-1 通过验收前必须继续满足：

1. no-network：测试和模块导入不得触发网络。
2. no provider imports：不得 import `baostock`、`akshare` 或 vendor SDK。
3. synthetic-only：测试 fixture 不得含真实 OHLCV、qfq、index、calendar、stock list、suspend rows、limit pool constituents。
4. no dependency changes：不得修改依赖文件、lockfile 或主项目 venv。
5. no `data/quant`：不得创建、修改或清理 `data/quant`。
6. no raw vendor data：不得写 raw response、raw archive、CSV、截图或可还原 vendor dataset。
7. no secrets：不得读取或写入 token、cookie、session、account、proxy 或 private archive path。
8. no formal outputs：qfq、benchmark、execution flags 必须保持 `research_only`、`candidate` 或 `blocked`。
9. no production impact：不得接生产排序、A/B/C、页面、Prism Edge、Expected 5D、ML、labels、backtests 或 existing reports。
10. 后续 FS-2 / FS-3 / FS-4 / FS-5 必须各自单独规划和验收，不能由 FS-1 顺手实现。

## 6. 下一步建议

建议下一步开 FS-1 实现卡，标题和范围应明确写：

- Scope: schema-only + synthetic tests.
- Allowed files: only the five FS-1 paths listed above.
- Tests: no-network, no provider imports, synthetic-only.
- Data policy: no `data/quant`, no raw vendor data, no repo-external archive writes.
- Output policy: no formal labels, no formal excess return, no formal adjusted return, no execution-realistic backtest.

FS-1 完成后再独立验收：

- pathspec 是否只包含允许文件。
- tests 是否通过且不需要 BaoStock / AKShare installed。
- redaction 是否拒绝 raw rows、full calendar、full stock list、raw response、absolute paths、URLs、token-like keys。
- guardrails 是否证明 no formal outputs and no production impact。

## 7. 最终裁决

free-source adapter implementation plan 验收结论：**通过**。

允许进入：**FS-1 schema-only + synthetic tests 代码实现**。

FS-1 必须保持：**no-network、synthetic-only、no `data/quant`、no provider imports**。

核心判断：该 plan 已把 FS-1 收束到足够小、可审计、无真实 provider、无数据输出、无 formal 产物、无生产影响的实现范围；FS-2 到 FS-5 拆分合理，且没有提前授权 live smoke、主线接入或页面路线。
