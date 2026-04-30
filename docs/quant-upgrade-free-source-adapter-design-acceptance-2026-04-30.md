# Prism Free-Source Adapter Design 独立验收报告

Date: 2026-04-30
Role: independent acceptance reviewer
Scope: `docs/quant-upgrade-free-source-adapter-design-2026-04-30.md` only
Status: passed

## 0. 验收边界

本次只读验收：

- `docs/quant-upgrade-free-source-adapter-design-2026-04-30.md`
- 当前 `git status --short`，仅用于确认相关路径背景风险

本次验收没有写代码，没有调用 BaoStock / AKShare，没有安装依赖，没有写 `packages/quant`，没有写 `data/quant`，没有覆盖任何 POC raw archive，没有生成 formal labels、formal excess return、formal adjusted return 或 execution-realistic backtest。

本报告是本次验收唯一新增产物，且位于 `docs/`。

## 1. 总体验收结论

结论：**通过**。

是否允许进入下一步 **non-production adapter implementation planning**：**允许**。

是否允许直接代码实现：**不允许**。

通过含义：

- 当前 design 文档足够作为下一步非生产实现规划的输入。
- 文档给出了未来文件范围、测试范围和验收标准，但没有授权本轮直接实现。
- 任何后续实现仍必须另开 implementation planning / implementation card，并继续接受 no raw vendor data、no formal outputs、no production impact 的约束。

## 2. 十二项重点验收

| # | 检查项 | 结果 | 验收意见 |
| --- | --- | --- | --- |
| 1 | 是否保持 docs-only | 通过 | 文档状态为 `design document only; no implementation`，边界中明确 No code、No API calls、No dependency installation、No `packages/quant` changes、No `data/quant` writes。 |
| 2 | 是否明确 BaoStock primary、AKShare cross-check / supplement | 通过 | Provider priority 表明确 BaoStock 为 primary candidate，AKShare 为 cross-check / supplement，并说明 AKShare 不替代 BaoStock 主源。 |
| 3 | adapter 分层是否完整 | 通过 | 覆盖 calendar、stock basic、raw daily、qfq candidate、index daily、`tradestatus` / `isST`、suspend event、limit price blocker。 |
| 4 | redacted manifest schema 是否完整 | 通过 | Schema 包含 provider、endpoint、params fingerprint、response hash、row_count、field list、non-null summary、retrieved_at、source_version、license / usage note、raw_archive_pointer，并补充 run_id、status、coverage、error、PIT/as-of 等字段。 |
| 5 | raw archive 是否明确 repo 外、hash、timestamp、保留期、删除机制、不入库规则 | 通过 | Raw archive design 明确 repo-external root/raw 目录、SHA256、timestamp、默认 90 天保留期、删除记录机制，以及 raw payload / 行级数据 / 完整数据集不入库。 |
| 6 | 字段契约是否区分 original field、canonical candidate、type、unit、PIT/as-of、research_only / blocked / available | 通过 | 各 layer field contract 使用 Raw field、Canonical candidate、Type、Unit、PIT / as-of status、Status；qfq 标 research_only，limit / factor 缺口标 blocked。 |
| 7 | 降级规则是否明确 | 通过 | Fallback / Degradation 覆盖 BaoStock 失败、AKShare 失败、provider mismatch、network error、empty rows、license uncertainty，并采用 fail-closed 口径。 |
| 8 | 是否明确后续可进入 non-production implementation 的能力范围 | 通过 | Capabilities Allowed 表只允许 selected field adapters：calendar、stock basic、raw daily、qfq candidate、index daily candidate、`tradestatus` / `isST` availability、suspend event manifest。 |
| 9 | 是否明确 formal / execution blockers 继续 blocked | 通过 | Formal adjusted return、formal excess return、formal labels、execution-realistic backtest、historical `up_limit/down_limit`、failed order、partial fill 均列为 blocked。 |
| 10 | 是否明确页面路线继续暂缓 | 通过 | Page Route Deferral 明确 control panel page、quant health page、Prism Edge、Expected 5D、A/B/C display 全部 deferred。 |
| 11 | 是否没有暗示可以接生产排序、A/B/C、Prism Edge、Expected 5D、ML | 通过 | Boundary、Layer rules、Blocked capabilities、Page deferral、Decision summary 均明确 production sorting、A/B/C、pages、Prism Edge、Expected 5D、ML 为 no / blocked / deferred。 |
| 12 | 是否给出后续代码实现文件范围、测试范围、验收标准，但没有开始实现 | 通过 | Future Implementation Scope 给出建议文件、synthetic-only tests、acceptance standards；同时明确该 section 只是 recommendation，不创建或修改文件。 |

## 3. Repo 边界核对

当前针对目标文档、目标验收文档、`packages/quant`、`data/quant` 和常见依赖 / lockfile / venv 路径的 `git status --short` 检查显示：

- `docs/quant-upgrade-free-source-adapter-design-2026-04-30.md` 为未跟踪文档。
- 本验收前目标验收报告不存在。
- 未发现 `packages/quant`、`data/quant`、dependency / lockfile / `.venv` / `venv` 相关变更进入本次验收范围。

工作区仍有与本验收无关的既有脏改动；后续提交必须继续使用显式 pathspec，只提交获批 docs。

## 4. 保留条件

即使本 design 通过，以下条件继续保留：

1. 下一步只允许进入 **non-production adapter implementation planning**，不是直接写代码。
2. 若后续批准 implementation，应先从 manifest schema、archive policy、canonical mapping 和 synthetic tests 开始。
3. 任何 live provider call 仍必须留在 repo 外 scratch，除非另有明确审批。
4. raw vendor data、行级行情、完整 calendar、完整 stock list、suspend event rows、limit pool constituents 不得进入 repo。
5. `data/quant` 写入仍不允许，除非后续另有明确 data-output 审批。
6. 依赖文件、lockfile、主项目 venv 仍不得修改，除非后续另有依赖审批。
7. BaoStock / AKShare 授权、自动化、归档、再分发边界仍需人工确认。
8. qfq 缺独立 `adj_factor`、revision、PIT/as-of 证明，formal adjusted return 仍 blocked。
9. index daily 仍只是 benchmark candidate，formal excess return 仍 blocked。
10. historical `up_limit/down_limit`、failed order、partial fill 仍 blocked，execution-realistic backtest 仍 blocked。
11. 页面、Prism Edge、Expected 5D、A/B/C、ML 和生产排序继续暂缓。

## 5. 下一步建议

建议下一步新增一份 **non-production adapter implementation planning** 文档，且只回答：

1. 是否从 schema-only + synthetic tests 开始。
2. 是否允许创建 `packages/quant/free_sources/*`，以及精确文件 pathspec。
3. 是否允许任何 dependency 变更；默认不允许。
4. 是否允许任何 `data/quant` 输出；默认不允许。
5. 如何验证 no network in tests、no raw vendor data、no formal outputs、no production impact。
6. 如果需要 live provider smoke，如何继续保持 repo-external scratch 和 redacted manifest only。

## 6. 最终裁决

free-source adapter design 验收结论：**通过**。

允许进入：**non-production adapter implementation planning**。

不允许进入：**直接代码实现**。

核心判断：该 design 文档已经把 provider 分工、adapter 分层、manifest、raw archive、字段契约、降级规则、blocked formal 能力、页面暂缓和未来实现边界讲清楚；但它本身仍是设计文档，不构成写 `packages/quant`、写 `data/quant`、调用真实 provider、生成 formal 产物或接生产 / 页面 / ML 的许可。
