# Prism Free-Source FS-3 Live Smoke 独立验收报告

Date: 2026-04-30
Role: independent acceptance reviewer
Scope: `docs/quant-upgrade-free-source-fs3-live-smoke-result-2026-04-30.md`
Status: conditional pass

## 0. 验收边界

本次只读验收：

- `docs/quant-upgrade-free-source-fs3-live-smoke-result-2026-04-30.md`
- 当前 `git status --short --untracked-files=all`，仅用于确认 repo 边界

本次没有调用 BaoStock / AKShare，没有安装依赖，没有写代码，没有修改 `packages/quant`、`data/quant`、依赖文件、lockfile 或主项目 venv，没有读取 repo 外 raw archive。

本报告是本次验收唯一新增产物，位于 `docs/`。

## 1. 总体验收结论

结论：**有条件通过**。

BaoStock 是否可以作为下一阶段免费主源候选：**可以，仅限 non-production / research-only 主源候选**。

AKShare 是否只能作为 cross-check / supplement：**是**。本次 raw daily 为 `network_error`，qfq 为 `partial`，因此不得夸大为主源。

是否允许进入下一步：**允许进入 free-source repeatable smoke planning / redacted report generator design**。

是否允许直接实现或继续 live provider call：**不允许**。repeatable smoke 或 redacted report generator 仍需单独 planning、验收和审批。

仍禁止：

- formal labels。
- formal excess return。
- formal adjusted return。
- execution-realistic backtest。
- 生产排序。
- A/B/C。
- 页面、Prism Edge、Expected 5D、ML。

有条件项：当前工作区中还存在 `docs/quant-upgrade-free-source-fs3-live-smoke-plan-2026-04-30.md` 未跟踪文档。它是 docs-only 背景项，不是 raw vendor data，也不是代码或数据输出；但后续提交必须用显式 pathspec 隔离，避免把未验收或无关文档混入同一提交。

## 2. 十五项重点验收

| # | 检查项 | 结果 | 验收意见 |
| --- | --- | --- | --- |
| 1 | repo 内是否只新增脱敏结果报告 | 有条件通过 | 本次验收目标报告为 redacted result only；当前工作区另有 FS-3 planning doc 未跟踪，属于 docs-only 背景项，提交时需隔离。未发现 FS-3 raw/vendor/code/data 输出。 |
| 2 | 是否没有改 `packages/quant` | 通过 | 当前 FS-3 相关状态检查未显示 `packages/quant` 变更。 |
| 3 | 是否没有写 `data/quant` | 通过 | 当前 FS-3 相关状态检查未显示 `data/quant` 变更；报告声明未写 `data/quant`。 |
| 4 | 是否没有改依赖文件 / lockfile / 主项目 venv | 通过 | 状态检查未显示 dependency / lockfile / `.venv` / `venv` 变更；报告声明主项目 venv 未改。 |
| 5 | raw vendor data 是否只在 repo 外私有 scratch | 通过 | 报告声明 raw provider responses 只归档在 approved repo-external private scratch root，repo 内只有 opaque pointers。 |
| 6 | 报告是否没有行级行情、完整 calendar、完整 stock list、suspend event rows、raw response | 通过 | 报告仅包含 endpoint、params summary、field list、non-null summary、row_count、hash、error summary；未见行级价格、完整 calendar、完整股票列表、event rows 或 raw response。 |
| 7 | `raw_archive_pointer` 是否 opaque 且未暴露绝对路径 | 通过 | pointer 形如 `fs3-live-smoke:run:provider:endpoint:hashprefix`；未命中 `/Users`、`file://`、`http(s)://`、`s3://`、query、credential 等模式。 |
| 8 | BaoStock 结果是否支撑 research-only 候选源判断 | 通过 | BaoStock calendar、stock basic、raw daily、qfq、index daily、`tradestatus` / `isST` 均 returned fields / non-null summary；报告明确为 research-only candidate。 |
| 9 | AKShare raw_daily / qfq 网络和 partial 问题是否如实标记 | 通过 | AKShare raw daily 标 `network_error` 且 0 rows；qfq 标 `partial`，1/3 样本返回、2/3 `ProxyError`；未夸大。 |
| 10 | qfq 是否仍不能 formal adjusted return | 通过 | 报告明确 qfq availability 不产生 formal adjusted return，缺 independent adjustment factor、revision audit、PIT/as-of proof。 |
| 11 | index daily 是否仍不能 formal excess return | 通过 | 报告明确 index daily availability 不产生 formal excess return，缺 formal benchmark freeze 或 label contract。 |
| 12 | `tradestatus` / `isST` 是否仍不能证明真实成交 | 通过 | 报告明确二者只是 execution candidate，不证明 real execution or fills。 |
| 13 | suspend event 是否仍只是 event-only | 通过 | AKShare `stock_tfp_em` 被标为 event-only supplement，不是 daily execution eligibility。 |
| 14 | limit up/down、failed order、partial fill 是否继续 blocked | 通过 | 报告明确 limit up/down price、failed order、partial fill remain blocked。 |
| 15 | 是否没有生产排序、A/B/C、页面、Prism Edge、Expected 5D、ML 影响 | 通过 | 报告边界和 blocked conclusions 明确这些均 remain blocked / no output。 |

## 3. 结果判断

BaoStock 当前可以作为下一阶段免费主源候选，但只能用于：

- non-production availability。
- research-only repeatable smoke。
- redacted manifest / report 设计输入。

它不能直接进入：

- formal calendar。
- formal adjusted return。
- formal excess return。
- formal labels。
- execution-realistic backtest。
- production ranking or page surface。

AKShare 当前只能作为：

- raw / qfq cross-check 候选，但本次 Eastmoney daily endpoint 有明显网络问题。
- index daily supplement，基于 `stock_zh_index_hist_csindex`。
- suspend event event-only supplement。

AKShare 不能作为：

- A 股主行情源。
- daily `tradestatus` 替代。
- historical full-market limit up/down source。
- formal output source。

## 4. 保留条件

进入下一步前继续保留：

1. 下一步只允许先做 repeatable smoke planning 或 redacted report generator design。
2. 不得直接继续 live provider call。
3. 不得直接实现 FS-4 / report generator。
4. 不得安装 BaoStock / AKShare 或修改依赖 / lockfile / venv，除非单独审批。
5. raw vendor data 必须继续留在 repo 外私有 scratch，不得进入 repo。
6. `raw_archive_pointer` 必须继续使用 opaque pointer，不暴露绝对路径或可访问 URL。
7. repo 内仍只能保留 redacted endpoint-level metadata。
8. qfq、index daily、`tradestatus` / `isST`、suspend event 只能保持 research-only / candidate / event-only。
9. formal labels、formal excess return、formal adjusted return、execution-realistic backtest 继续 blocked。
10. production sorting、A/B/C、页面、Prism Edge、Expected 5D、ML 继续 blocked。
11. 后续提交必须用显式 pathspec，避免混入 FS-3 planning doc 或其他未验收工作区文件。

## 5. 下一步建议

建议下一步二选一或先后执行：

1. **free-source repeatable smoke planning**：定义重复次数、窗口、endpoint、失败语义、repo-external scratch、hash/timestamp、retention/deletion、redacted result 入库规则。
2. **redacted report generator design**：只设计如何把已脱敏 manifest 转为 docs/report，不读取 raw vendor data，不写 `data/quant`，不生成 formal outputs。

无论选择哪条路线，下一步仍应先写 planning/design 并独立验收；不要直接写实现或发起 live provider call。

## 6. 最终裁决

FS-3 live smoke 验收结论：**有条件通过**。

BaoStock：**可以作为下一阶段免费主源候选，但仅限 non-production / research-only**。

AKShare：**只能作为 cross-check / supplement**。

允许进入：**free-source repeatable smoke planning / redacted report generator design**。

不允许进入：**直接实现、直接 FS-4、直接 live provider call、formal outputs、生产排序或页面路线**。
