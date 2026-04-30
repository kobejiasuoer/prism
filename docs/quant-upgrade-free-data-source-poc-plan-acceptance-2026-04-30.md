# Prism 免费数据源 POC 方案独立验收报告

Date: 2026-04-30
Role: independent acceptance reviewer
Scope: `docs/quant-upgrade-free-data-source-poc-plan-2026-04-30.md` only
Status: passed

## 0. 验收边界

本次只读检查：

- `docs/quant-upgrade-free-data-source-poc-plan-2026-04-30.md`
- 当前 `git status --short`，仅用于确认工作区背景风险

本次验收没有调用 BaoStock API，没有调用 AKShare API，没有安装依赖，没有读取或修改 `packages/quant`，没有读取或修改 `data/quant`，没有生成 raw response、formal labels、formal excess return、formal adjusted return 或 execution-realistic backtest。

本报告是本次验收唯一新增产物，且位于 `docs/`。

## 1. 总体验收结论

结论：**通过**。

是否允许进入下一步 **non-production field availability POC**：**允许**。

允许含义仅限于：可以在人工批准后，按方案约束做 BaoStock + AKShare 的非生产字段可得性、授权边界、稳定性和降级路径验证。

下一步仍然不得：

- 写 `packages/quant`。
- 写 `data/quant`。
- 接生产排序。
- 改 A/B/C。
- 做页面或 Prism Edge。
- 做 Expected 5D 默认展示。
- 做 ML。
- 生成 formal labels、formal excess return、formal adjusted return 或 execution-realistic backtest。

## 2. 十项重点验收

| # | 验收项 | 结果 | 证据摘要 |
| --- | --- | --- | --- |
| 1 | 是否保持 docs-only | 通过 | 方案标记 `plan only; no execution`，禁止开发、执行、抓数；本次新增产物也仅为 `docs/` 验收报告。 |
| 2 | 是否只验证 BaoStock + AKShare 的字段可得性、授权边界、稳定性和降级路径 | 通过 | Scope 明确为 BaoStock + AKShare non-production availability POC；目标集中在字段可得性、覆盖范围、复权口径、交易状态、指数日线和授权边界；状态枚举包含 available / partial / missing / unknown / blocked。 |
| 3 | 是否没有接 `packages/quant` | 通过 | 方案禁止新增、修改、import、调用 `packages/quant`；下一步执行约束也写明不接主线。 |
| 4 | 是否没有写 `data/quant` | 通过 | 方案禁止写 `data/quant`，并要求 raw response 只能进 repo 外私有目录，repo 内只允许脱敏报告。 |
| 5 | 是否没有承诺 formal labels / formal excess return / formal adjusted return / execution-realistic backtest | 通过 | 方案多处明确禁止这些 formal 产物；qfq、指数和停复牌/涨跌停均只作为候选字段验证，不构成 formal 升级。 |
| 6 | 是否没有影响生产排序、A/B/C、页面、Prism Edge、Expected 5D、ML | 通过 | 方案禁止影响生产排序、A/B/C、页面、Prism Edge、Expected 5D 和 ML；未来 POC 执行方式也禁止触发生产排序、控制台刷新、页面构建或 Prism Edge 流程。 |
| 7 | 是否明确 raw response 未来只能在 repo 外私有目录 | 通过 | 方案写明未来如执行 POC，只允许在 repo 外私有目录保存 raw response，并要求位置不在 Prism 工作树内。 |
| 8 | 是否明确 repo 内只保留脱敏摘要报告 | 通过 | 方案明确 repo 内最多提交字段可得性、授权边界、row_count、field list、hash、timestamp 和结论；禁止 raw response、行级行情、完整 calendar、完整股票列表和可还原 vendor dataset 的样本。 |
| 9 | 是否列出成功/失败标准、阻塞条件和下一步决策树 | 通过 | 方案包含硬成功门槛、能力级成功标准、失败标准、blocked 状态含义，以及 POC 完成后的决策树。 |
| 10 | 是否识别免费数据源核心风险 | 通过 | 方案覆盖稳定性、授权边界、字段口径、复权口径、指数覆盖、停牌/涨跌停可得性；并额外标记维护活跃度、底层网页/接口变化、PIT 证明不足、qfq 历史重算等风险。 |

## 3. BaoStock / AKShare 范围判断

方案没有把免费数据源 POC 扩大成生产接入。BaoStock 的角色被限制在 calendar、stock basic、raw/qfq、`tradestatus`、`isST`、指数日线字段验证；AKShare 被限制在 A 股日线、qfq、指数日线，以及停复牌/涨跌停公开接口的存在性和字段调研。

验收判断：范围清楚，且没有把 AKShare 或 BaoStock 预设为 formal source。

## 4. Raw / Redacted 边界

方案对 raw response 和 repo 入库内容的边界足够明确：

- raw response 只能在 repo 外私有目录。
- repo 内只允许 redacted report。
- repo 内不得包含行级 OHLCV、行级 qfq / adjusted price、行级复权因子、行级停牌或 `tradestatus`、行级 `isST`、行级涨跌停价或涨停池明细。
- 完整交易日历、完整基础股票列表、可还原 vendor dataset 的 CSV / JSON / 截图 / 表格均禁止入库。

验收判断：满足私有归档和脱敏摘要入库纪律。

## 5. 继续前条件

以下不是本方案缺陷，但进入下一步 POC 前仍必须满足：

1. 人工确认 BaoStock / AKShare 当前文档 URL、版本、免费访问、自动化调用、频率、授权和归档边界。
2. 明确 repo 外私有 raw archive 的位置、权限、保留期和删除机制。
3. 确认 redacted report 入库只含字段清单、row_count、hash、timestamp、缺失摘要和授权结论。
4. POC 运行必须在 repo 外 scratch 目录中执行，不修改 Prism repo 依赖文件或 lockfile。
5. 当前工作区存在大量与本方案无关的已修改和未跟踪文件；后续提交必须使用显式 pathspec，只提交获批 docs。

## 6. 最终裁决

免费数据源 POC 方案验收结论：**通过**。

允许进入下一步：**允许进入 BaoStock + AKShare non-production field availability POC**。

下一步边界：仍然不得写 `packages/quant`、不得写 `data/quant`、不得接生产排序、不得改 A/B/C、不得做页面、不得做 Prism Edge、不得做 Expected 5D、不得做 ML，也不得生成 formal labels、formal excess return、formal adjusted return 或 execution-realistic backtest。
