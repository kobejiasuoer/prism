# Prism 免费数据源 Field Availability POC 独立验收报告

Date: 2026-04-30
Role: independent acceptance reviewer
Scope: `docs/quant-upgrade-free-data-source-field-poc-result-2026-04-30.md` only
Status: conditional pass

## 0. 验收边界

本次只读验收：

- `docs/quant-upgrade-free-data-source-field-poc-result-2026-04-30.md`
- 当前 `git status --short`，仅用于确认 `packages/quant`、`data/quant`、依赖文件、lockfile 和主项目 venv 背景风险

本次验收没有调用 BaoStock，没有调用 AKShare，没有安装依赖，没有写代码，没有修改任何数据，没有读取 repo 外 raw vendor archive。

本报告是本次验收唯一新增产物，且位于 `docs/`。

## 1. 总体验收结论

结论：**有条件通过**。

是否允许进入 **free-source adapter design**：**允许，仅限 docs-only design doc**。

是否允许进入代码实现：**不允许**。

有条件通过的含义：

- POC result 的 non-production、redacted report、repo 边界和降级口径合格。
- BaoStock / AKShare 的结果被表述为字段可得性和 cross-check，不是 formal source。
- 下一步可以写 free-source adapter design doc。
- 下一步仍不得写 `packages/quant`、不得写 `data/quant`、不得改依赖文件或 lockfile、不得接生产排序、不得改 A/B/C、不得做页面、Prism Edge、Expected 5D 或 ML。

## 2. 十四项重点验收

| # | 检查项 | 结果 | 验收意见 |
| --- | --- | --- | --- |
| 1 | POC 是否严格保持 non-production | 通过 | Result scope 为 BaoStock + AKShare non-production field availability POC；报告声明未生成生产排序、A/B/C、页面、Prism Edge、Expected 5D、ML 或 formal 产物。 |
| 2 | 是否没有修改 `packages/quant` | 通过 | Result 声明未修改；本次 `git status --short` 针对 `packages/quant` 无输出。 |
| 3 | 是否没有写 `data/quant` | 通过 | Result 声明未写入；本次 `git status --short` 针对 `data/quant` 无输出。 |
| 4 | 是否没有修改 repo 依赖文件、lockfile、主项目 venv | 通过 | Result 声明依赖只安装到 repo 外 scratch venv；本次状态扫描未发现 dependency / lockfile / `.venv` / `venv` 变更。 |
| 5 | raw vendor data 是否只在 repo 外私有目录 | 通过 | Result 写明 raw vendor data 只保存到 `~/.prism-private/free-data-poc/` 下 scratch 私有 raw 目录；本次验收未读取该目录。 |
| 6 | repo 内报告是否没有行级行情、完整交易日历、完整股票列表、raw response、可还原 vendor dataset | 通过 | Result 只保留 row_count、字段清单、非空摘要、hash、错误摘要和结论；未见行级价格、完整 calendar、完整股票列表或 raw response 片段。 |
| 7 | BaoStock 结论是否只是字段可得性，不是 formal source | 通过 | BaoStock calendar、stock basic、raw daily、qfq、`tradestatus`、`isST`、index daily 均被描述为字段可得性 / non-production 候选源。 |
| 8 | AKShare 股票日线 / qfq / index cross-check 是否没有被夸大 | 通过 | AKShare qfq 标为 partial，平安银行 qfq 为 provider / network failure；指数说明东方财富接口失败、中证指数接口可作补充；未宣称 AKShare 为唯一 formal source。 |
| 9 | 是否明确历史涨跌停 limit price 仍未解决 | 通过 | Result 明确 BaoStock 未返回 `up_limit` / `down_limit`，AKShare 涨跌停池不能替代全市场历史 limit price，execution limit flags 仍 unavailable。 |
| 10 | 是否明确 qfq 缺 adj_factor / revision / PIT 证明，不能 formal adjusted return | 通过 | Result 明确未验证到独立 `adj_factor` / factor revision，缺 as-of archive / PIT 证明，qfq price 可用不等于 formal adjusted return ready。 |
| 11 | 是否明确 benchmark 只能进入 adapter design，不能生成 formal excess return | 通过 | Result 明确 HS300 / CSI500 字段可得性可进入 non-production benchmark adapter design，但不得计算 formal excess return 或 benchmark_return。 |
| 12 | 是否明确 label upgrade、execution-realistic backtest 仍 blocked | 通过 | Result 写明 label upgrade 不覆盖、formal label upgrade blocked；execution-realistic 由 limit price、真实成交、failed order、partial fill 等缺口继续阻断。 |
| 13 | 是否允许进入下一步 free-source adapter design doc | 通过 | Result 建议写 free-source adapter design doc，而不是直接写 `packages/quant`。 |
| 14 | 下一步是否仍禁止生产排序、A/B/C、页面、Prism Edge、Expected 5D、ML | 通过 | Result 边界表明确这些均未修改、未生成；本验收继续保留这些禁止项。 |

## 3. Repo 边界核对

`git status --short` 显示 result 文档本身为未跟踪文件；针对以下路径和文件类型的检查未发现 POC 相关改动：

- `packages/quant`
- `data/quant`
- `pyproject.toml`、`poetry.lock`、`requirements*.txt`
- `package.json`、`package-lock.json`、`pnpm-lock.yaml`、`yarn.lock`
- `Pipfile`、`Pipfile.lock`、`uv.lock`
- `.venv`、`venv`

工作区仍存在大量与本 POC 无关的既有脏改动；后续提交必须继续使用显式 pathspec，只提交获批 docs。

## 4. 结果准确性判断

BaoStock 结果表述准确：

- calendar、stock basic、raw daily、qfq、`tradestatus`、`isST`、index daily 均可作为字段可得性证据。
- `tradestatus` / `isST` 只能作为 execution availability 候选输入，不能证明真实可成交、failed order 或 partial fill。
- qfq price 可得仍缺独立 `adj_factor`、revision 和 PIT 证明，不能升级 formal adjusted return。

AKShare 结果表述准确：

- 股票 raw 日线 3/3 样本成功，qfq 2/3 成功，1/3 provider / network failure，标为 partial 合理。
- `stock_zh_a_hist` 未返回 `pre_close`、`tradestatus`、`isST`、独立 `adj_factor` 或 revision，缺口保留合理。
- 东方财富指数接口失败，中证指数接口成功，因此只能作为 index cross-check / supplement。
- 停复牌是 event-only，涨跌停池不是全市场历史 `up_limit` / `down_limit`。

## 5. 保留 Blocker

以下 blocker 必须继续保留：

1. 授权边界仍需人工确认：免费可调用不等于允许再分发、长期归档或进入正式主源。
2. raw archive / PIT 仍需长期纪律：当前只是 repo 外私有归档，不构成 PIT-ready 数据源。
3. qfq 缺独立 `adj_factor`、factor revision、as-of archive，因此 formal adjusted return 仍 blocked。
4. HS300 / CSI500 benchmark 只能进入 adapter design，formal excess return 仍 blocked。
5. 历史全市场 `up_limit` / `down_limit` 未解决，execution limit flags 仍 unavailable。
6. 停复牌仍需日级展开、calendar 对齐和冲突处理；AKShare `stock_tfp_em` 只是事件级。
7. `tradestatus` / `isST` 需要覆盖率、取值集合、历史口径和冲突处理审计。
8. AKShare 存在 provider / network instability；东方财富相关接口在本次环境失败。
9. `pre_close` 等字段映射仍需设计，不得靠未审计衍生值直接进入 formal pipeline。
10. label upgrade、execution-realistic backtest、生产排序和产品化仍全部 blocked。

## 6. 下一步建议

允许的下一步：

1. 新增 **free-source adapter design doc**，保持 docs-only。
2. 在 design doc 中明确 BaoStock 为 primary candidate，AKShare 为 cross-check / supplement。
3. 设计 redacted manifest schema：provider、endpoint、params fingerprint、response hash、row_count、field list、coverage summary、license note、error status。
4. 设计 failure semantics：provider failure、network failure、partial field、missing field、license blocked、unstable。
5. 设计 repo 外 repeatability POC 方案，但执行前需再次人工批准。

不允许的下一步：

- 不允许写 `packages/quant`。
- 不允许写 `data/quant`。
- 不允许修改依赖文件、lockfile 或主项目 venv。
- 不允许提交 raw vendor data、完整交易日历、完整股票列表或可还原 vendor dataset。
- 不允许生成 formal labels、formal excess return、formal adjusted return 或 execution-realistic backtest。
- 不允许接生产排序、A/B/C、页面、Prism Edge、Expected 5D 或 ML。

## 7. 最终裁决

免费数据源 field availability POC 验收结论：**有条件通过**。

允许进入：**free-source adapter design doc**。

不允许进入：**代码实现**。

核心判断：本 POC 足以支持下一步非生产设计文档，但还不足以支持 adapter implementation，更不能支持 formal labels、formal benchmark / excess return、formal adjusted return、execution-realistic backtest 或任何生产 / 页面 / ML 接入。
