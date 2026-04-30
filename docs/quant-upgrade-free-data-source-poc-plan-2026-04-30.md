# Prism 免费数据源 BaoStock + AKShare POC 方案

Date: 2026-04-30
Role: free external data source POC planner
Scope: BaoStock + AKShare non-production availability POC plan only
Status: plan only; no execution

Related Prism documents:

- `docs/quant-upgrade-p1a-source-inventory-and-implementation-plan-2026-04-28.md`
- `docs/quant-upgrade-p1a-external-data-source-research-2026-04-29.md`
- `docs/quant-upgrade-external-data-source-decision-pack-2026-04-29.md`
- `docs/quant-upgrade-tushare-poc-plan-2026-04-29.md`
- `docs/quant-upgrade-tushare-field-availability-matrix-2026-04-29.md`

External references checked for this plan:

- [BaoStock official site](http://baostock.com/)
- [BaoStock PyPI package page](https://pypi.org/project/baostock/)
- [BaoStock GitHub mirror](https://github.com/shimencaiji/baostock)
- [AKShare documentation home](https://akshare.akfamily.xyz/)
- [AKShare stock data documentation](https://akshare.akfamily.xyz/data/stock/stock.html)
- [AKShare index data documentation](https://akshare.akfamily.xyz/data/index/index.html)

## 0. 本文边界

本文只准备 Prism 免费数据源 POC 方案，不开发、不执行、不抓数。

严格禁止：

- 不调用 BaoStock API。
- 不调用 AKShare API。
- 不安装 BaoStock、AKShare 或任何新依赖。
- 不新增或修改 `packages/quant`。
- 不写 `data/quant`。
- 不写入任何可被主链路消费的数据。
- 不生成 formal labels。
- 不生成 formal excess return。
- 不生成 formal adjusted return。
- 不做 execution-realistic backtest。
- 不影响生产排序、A/B/C、页面、Prism Edge、Expected 5D 或 ML。
- 不生成页面或产品化展示。
- 不提交 raw response、行级行情、完整交易日历、完整基础股票列表、复权序列、停复牌明细或涨跌停明细。

本文中的接口名、字段名和代码映射都是未来 POC 的验证清单，不代表字段已经可用。未来如执行 POC，只允许在 repo 外私有目录保存 raw response；repo 内最多提交脱敏字段可得性、授权边界、row_count、field list、hash、timestamp 和结论。

## 1. 一句话结论

BaoStock + AKShare 值得作为 P1-A 的免费源 POC 候选，但只能验证“字段是否可能补齐缺口”，不能直接升级 Prism 的 formal 产物。

建议分工：

| 数据源 | POC 中的优先角色 | 主要验证点 | 主要风险 |
| --- | --- | --- | --- |
| BaoStock | P1-A 免费主候选之一 | 交易日历、股票基础信息、A 股日线 OHLCV、前复权/不复权、`tradestatus`、`isST`、指数日线如可用 | 授权边界、维护活跃度、接口稳定性、指数覆盖、PIT 证明不足 |
| AKShare | P1-A 免费 cross-check 和补充候选 | A 股日线、前复权 qfq、指数日线；公开停复牌/涨跌停相关接口只做存在性和字段调研 | 底层网页/接口变化、数据授权、qfq 历史重算、涨跌停/停牌字段不可假设完整 |

POC 通过后的最好结果也只是：可以写下一份 non-production adapter design review。它仍不允许生成 formal labels、formal excess return 或 execution-realistic backtest。

## 2. POC 目标

本 POC 只回答一个问题：

BaoStock + AKShare 是否能在不付费、不接生产、不改 `packages/quant` 主线的前提下，补齐 P1-A 当前最关键的数据缺口的字段可得性判断。

具体目标：

| 目标 | POC 要回答的问题 | POC 不回答的问题 |
| --- | --- | --- |
| 字段可得性 | 候选接口是否返回 Prism 需要的字段名或等价概念 | 数据是否已经可入库、可建模、可正式回测 |
| 覆盖范围 | 指定日期、样本股票、指数代码是否能返回 row_count 和字段清单 | 全市场长期覆盖是否永久稳定 |
| 复权口径 | raw / qfq 是否都能取到，字段是否能对齐 | qfq 是否 PIT-ready，是否可生成 formal adjusted return |
| 交易状态 | `tradestatus`、`isST` 或停复牌字段是否存在 | 是否能证明真实可成交、partial fill 或 failed order |
| 指数日线 | HS300 / CSI500 候选指数日线是否可取 | 是否可直接计算 formal benchmark return / excess return |
| 授权边界 | 免费访问、自动化、私有 raw archive、脱敏报告入库是否可接受 | 数据版权、再分发或商业用途已经获批 |

## 3. 当前 P1-A 缺口映射

| P1-A 缺口 | 为什么重要 | BaoStock POC | AKShare POC | 通过后仍不可做 |
| --- | --- | --- | --- | --- |
| 交易日历 | label window、entry/exit trading date、benchmark 对齐 | 验证 `query_trade_dates` 字段和覆盖 | AKShare 非本次主验证项，若发现稳定公开接口可记录 | 不直接冻结 formal calendar |
| 股票基础信息 | 代码、上市状态、上市日期、交易所、ST/规则辅助 | 验证 `query_stock_basic` 或等价能力 | 可作为补充字段调研，不作为主项 | 不直接生成 universe snapshot |
| A 股 raw OHLCV | raw return audit、成交量/成交额基础校验 | 验证 `query_history_k_data_plus` 不复权字段 | 验证 `stock_zh_a_hist` 或等价日线字段 | 不生成 price dataset |
| 前复权 qfq | 后续 adjusted return 设计的输入 | 验证 `adjustflag` 前复权/不复权对齐 | 验证 `adjust="qfq"` 与不复权对齐 | 不生成 formal adjusted return |
| `tradestatus` | 停牌/交易状态 source-provided 线索 | 验证日线字段是否存在、含义和缺失率 | 仅调研公开停复牌相关接口，不假设有日级全市场字段 | 不生成 execution-realistic flags |
| `isST` | ST 规则、涨跌幅限制、可交易性辅助 | 验证日线字段是否存在、含义和缺失率 | 可用名称/ST 板块或风险警示接口做补充调研，如存在 | 不直接做 ST 规则引擎 |
| 指数日线 | CSI500 / HS300 benchmark 前置 | 验证指数代码是否可用、OHLCV 字段 | 验证 `index_zh_a_hist` 或等价指数日线 | 不计算 benchmark_return / excess_return |
| 涨跌停/停牌 | execution flags hardening 的前置 | BaoStock 以 `tradestatus` / `isST` 为主，涨跌停价格不假设 | 仅调研公开接口，如 `stock_tfp_em`、涨停池或 spot 字段是否有可用字段 | 不声称 full execution realism |

## 4. BaoStock 验证清单

### 4.1 交易日历

候选接口：`query_trade_dates`。

POC 目的：验证是否能返回 A 股交易日历，用于未来 frozen calendar 的候选输入或 cross-check。

| Prism 需要 | 候选字段 / 概念 | POC 判定要求 |
| --- | --- | --- |
| 日历日期 | `calendar_date` 或等价字段 | 必须 present |
| 是否交易日 | `is_trading_day` 或等价字段 | 必须 present |
| 日期范围控制 | start / end date params | 必须可控 |
| A 股口径 | 上海/深圳交易日是否一致 | 需与样本区间官方休市公告或另一源交叉审计 |

POC 结果只允许记录日期范围、row_count、字段清单、missing count、duplicate count 和 hash，不提交完整 calendar。

### 4.2 股票基础信息

候选接口：`query_stock_basic`。

POC 目的：验证股票基础信息是否能补 universe / listing metadata 缺口。

| Prism 需要 | 候选字段 / 概念 | POC 判定要求 |
| --- | --- | --- |
| 股票代码 | `code` | 必须 present |
| 股票名称 | `code_name` 或等价字段 | 建议 present |
| 上市日期 | `ipoDate` 或等价字段 | 必须 present |
| 退市日期 | `outDate` 或等价字段 | 如存在需记录 |
| 证券类别 | `type` 或等价字段 | 必须验证含义 |
| 上市状态 | `status` 或等价字段 | 必须验证含义和历史口径 |

基础信息只能作为字段可得性和授权边界报告，不得把全量列表写入 repo。

### 4.3 A 股日线 OHLCV

候选接口：`query_history_k_data_plus`。

POC 目的：验证 A 股 raw daily OHLCV 和必要辅助字段是否可用。

| Prism 需要 | 候选字段 / 概念 | POC 判定要求 |
| --- | --- | --- |
| 交易日 | `date` | 必须 present |
| 股票代码 | `code` | 必须 present |
| OHLC | `open`, `high`, `low`, `close` | 必须 present |
| 前收 | `preclose` | 必须 present |
| 成交量 / 成交额 | `volume`, `amount` | 必须 present 或说明缺口 |
| 复权标志 | `adjustflag` | 必须 present 或由 request params 固化 |
| 交易状态 | `tradestatus` | 必须验证 present / missing |
| ST 状态 | `isST` | 必须验证 present / missing |
| 涨跌幅 | `pctChg` | 可选，作为 sanity check |
| 换手率 | `turn` | 可选，作为 liquidity audit |

POC 不得从缺行、volume=0 或价格不变推断停牌。只有 source-provided `tradestatus` 或明确停复牌字段才可记录为候选 execution input。

### 4.4 前复权 / 不复权

候选能力：`query_history_k_data_plus` 的 `adjustflag` 参数。

POC 目的：验证同一股票、同一日期区间下，前复权和不复权是否都可取，字段是否可对齐。

最小验证：

| 口径 | POC 要求 |
| --- | --- |
| 不复权 | 明确 request params；验证 raw OHLCV 字段和 row_count |
| 前复权 | 明确 request params；验证 qfq OHLCV 字段和 row_count |
| flag 含义 | 以 BaoStock 当前文档和返回字段为准；不得只靠记忆写死 |
| 对齐 | 比较 row_count、日期集合、字段集合，只写汇总，不写行级价 |
| PIT | 标记为 `pit_weak_until_daily_archive_exists` |

如果只能取 qfq price，不能取可解释复权因子或 factor revision，则后续只能判定为 `price_adjustment_partial`，不得进入 formal adjusted return。

### 4.5 `tradestatus` 和 `isST`

POC 目的：验证 BaoStock 是否能提供日级交易状态和 ST 状态字段，作为 execution flags 的候选输入。

| 字段 | POC 要求 | 不能做什么 |
| --- | --- | --- |
| `tradestatus` | 验证字段存在、取值集合、缺失率、和停牌样本是否一致 | 不能直接证明真实可成交或 partial fill |
| `isST` | 验证字段存在、取值集合、缺失率、和 ST 样本是否一致 | 不能直接替代完整板块/规则版本表 |

POC report 必须写明：即使 `tradestatus` 和 `isST` 可得，也只能解除“字段是否存在”的一层疑问，不会自动解除 execution-realistic blocker。

### 4.6 指数日线，如可用

候选接口：`query_history_k_data_plus`，候选指数代码需未来 POC 实测确认。

候选映射：

| 指数 | 候选 BaoStock code | POC 要求 |
| --- | --- | --- |
| HS300 | `sh.000300` | 验证是否能返回日线 OHLCV |
| CSI500 | `sh.000905` | 验证是否能返回日线 OHLCV |
| 上证综指 | `sh.000001` | 作为接口 smoke check，可选 |

必需字段：

| Prism 需要 | 候选字段 |
| --- | --- |
| 交易日 | `date` |
| 指数代码 | `code` |
| OHLC | `open`, `high`, `low`, `close` |
| 前收 | `preclose` |
| 成交量 / 成交额 | `volume`, `amount`，如接口提供 |

指数日线 POC 只验证字段和覆盖，不计算 benchmark return，也不生成 formal excess return。

## 5. AKShare 验证清单

### 5.1 A 股日线

候选接口：`stock_zh_a_hist`。如未来文档或版本显示更适合的日线接口，例如 `stock_zh_a_daily`，可作为补充，但必须单独记录接口名和字段差异。

POC 目的：验证公开免费 A 股日线 OHLCV 是否可作为 BaoStock cross-check 或补充源。

| Prism 需要 | 候选字段 / 概念 | POC 判定要求 |
| --- | --- | --- |
| 交易日 | `日期` 或 `date` | 必须 present |
| 股票代码 | `股票代码` 或 request symbol | 必须 present 或 params 可追溯 |
| OHLC | `开盘`, `最高`, `最低`, `收盘` 或英文等价字段 | 必须 present |
| 成交量 / 成交额 | `成交量`, `成交额` 或英文等价字段 | 必须 present 或说明缺口 |
| 涨跌幅 / 涨跌额 | `涨跌幅`, `涨跌额` | 可选，sanity check |
| 换手率 | `换手率` | 可选，liquidity audit |
| 前收 | `pre_close` 或等价字段 | 若缺失，必须标记 `pre_close_missing_or_derived_only` |

AKShare 日线不得作为唯一 formal source。它可以帮助验证 BaoStock 字段是否明显异常，也可以帮助评估免费源覆盖范围。

### 5.2 前复权 qfq

候选能力：`stock_zh_a_hist(..., adjust="qfq")`，并与 `adjust=""` 或等价不复权请求对照。

POC 目的：验证 AKShare qfq 是否能补充 BaoStock 复权验证。

关键纪律：

| 项目 | 要求 |
| --- | --- |
| qfq request params | 必须记录在 redacted params 中 |
| raw request params | 必须记录同一股票、同一区间的不复权请求摘要 |
| 日期集合 | 只记录 row_count、date coverage、missing / duplicate 摘要 |
| 字段集合 | 只记录字段名和类型摘要 |
| qfq PIT 风险 | 必须标记 AKShare 文档提示的复权历史价动态变化风险 |
| factor 缺口 | 若无独立 adj_factor / revision，结论只能是 `qfq_price_available_but_factor_missing` |

POC 不得用 AKShare qfq 直接覆盖历史 labels，也不得生成 formal adjusted return。

### 5.3 指数日线

候选接口：`index_zh_a_hist` 或 AKShare 当前文档中的等价指数历史接口。

候选映射：

| 指数 | 候选 AKShare symbol | POC 要求 |
| --- | --- | --- |
| HS300 | `000300` | 验证 OHLCV 字段、日期覆盖、row_count |
| CSI500 | `000905` | 验证 OHLCV 字段、日期覆盖、row_count |
| CSI1000 | `000852` | 可选 secondary benchmark smoke check |

必需字段：

| Prism 需要 | 候选字段 / 概念 |
| --- | --- |
| 交易日 | `日期` 或 `date` |
| OHLC | `开盘`, `最高`, `最低`, `收盘` |
| 成交量 / 成交额 | `成交量`, `成交额`，如接口提供 |
| 涨跌幅 / 涨跌额 | 可选 sanity check |

POC 不计算 benchmark return，也不把 AKShare index data 写入 `data/quant`。

### 5.4 涨跌停 / 停牌相关字段调研

本项只做公开接口调研和字段可得性验证，不假设一定可用。

候选方向：

| 主题 | 公开候选能力 | POC 要求 | 默认结论 |
| --- | --- | --- | --- |
| 停复牌 | AKShare 文档中可见 `stock_tfp_em` 等停复牌信息接口 | 验证是否有代码、名称、停牌时间、停牌截止时间、停牌期限、停牌原因、所属市场、预计复牌时间等字段 | `unknown_until_verified` |
| 停复牌 cross-check | 文档中如有其他交易提醒类停复牌接口 | 只做补充，不作为 A 股主源 | `optional` |
| 涨停/跌停池 | AKShare 若公开提供涨停池、炸板池、强势股池等接口 | 只能验证当日/特定日期池字段，不得视为全市场历史 limit price | `unknown_until_verified` |
| spot 涨跌停价 | 若实时/快照接口返回涨停价、跌停价 | 只能作为当日 snapshot 字段可得性，不能替代历史 execution flags | `optional` |

字段调研结果必须明确区分：

- `limit_price_available`：返回全市场或目标股票 up_limit / down_limit。
- `limit_pool_available`：只返回涨停池/炸板池等集合，不覆盖全市场。
- `suspend_event_available`：只返回事件或公告级停复牌信息，需要后续展开到日级。
- `daily_tradestatus_available`：返回日级可交易状态。
- `not_available_or_not_stable`：接口缺失、字段缺失或版本不稳定。

只有 `limit_price_available` 或 `daily_tradestatus_available` 才可能进入后续 adapter 设计；即便如此，也仍然不能宣称 execution-realistic。

## 6. POC 样本设计

未来 POC 样本只用于字段可得性，不用于研究结论。

### 6.1 日期窗口

建议使用三个小窗口，每个窗口只记录汇总：

| 窗口 | 目的 |
| --- | --- |
| 最近完整交易周 | 验证当前接口可用性和最新覆盖 |
| 近一年内含节假日的 2-3 周 | 验证 calendar、缺行和日期对齐 |
| 历史窗口，例如 2020 或 2024 的若干交易日 | 验证历史回填和 qfq/raw 对齐 |

日期窗口不得写出行级价格或完整 calendar。

### 6.2 标的样本

建议样本只作为 params 摘要：

| 样本类型 | 候选选择原则 | 目的 |
| --- | --- | --- |
| 主板大盘股 | 选择 1-2 只长期上市、流动性高的 A 股 | raw / qfq / volume sanity |
| 创业板或科创板 | 选择 1-2 只不同板块股票 | 板块字段、涨跌幅规则后续评估 |
| ST 样本 | 人工选择 POC 当时明确 ST 的股票 | `isST` / 名称 / 风险警示字段验证 |
| 停牌样本 | 人工选择 POC 当时或历史明确停牌事件 | `tradestatus` / 停复牌接口验证 |
| 指数 | HS300、CSI500，CSI1000 可选 | benchmark 候选字段验证 |

repo 内只能写 `symbol_count`、`board_coverage_summary`、`has_st_sample=true/false`、`has_suspend_sample=true/false`，不得写完整样本明细和返回行。

## 7. Future POC 执行方式

本次不执行。未来如人工批准执行，应另开一次 isolated POC，且仍保持 non-production。

执行约束：

| 项目 | 要求 |
| --- | --- |
| 环境 | 在 Prism repo 外的隔离 scratch 目录执行 |
| 依赖 | 本方案阶段不安装；未来若执行，由人工审批，并不得修改 Prism repo 的依赖文件或 lockfile |
| API 调用 | 仅限 POC 样本和最小字段验证 |
| 网络 | 只访问 BaoStock / AKShare 所需公开源；不得接生产 |
| 输出 | raw response 只进 repo 外私有目录；repo 内只进 redacted report |
| 主线 | 不 import、修改或调用 `packages/quant` |
| 数据目录 | 不写 `data/quant` |
| 生产影响 | 不触发生产排序、控制台刷新、页面构建或任何 Prism Edge 流程 |

## 8. 私有 raw archive 方案

未来如果 POC 产生 raw response，只能放 repo 外私有目录。

私有归档要求：

| 项目 | 要求 |
| --- | --- |
| 位置 | 不在 `/Users/yangbishang/Projects/prism` 工作树内 |
| 权限 | 仅 POC 执行者和审批人可读 |
| 命名 | 使用 opaque run id，不暴露账号、用户名、完整本地路径或敏感参数 |
| 内容 | raw response、private request manifest、error payload、字段清单 |
| 禁止 | 不保存 token、cookie、session、账号密码 |
| 保留期 | POC 前人工指定，例如 30/90/180 天 |
| 删除 | POC 后按授权边界删除、保留或迁移 |

hash 规则：

- `response_hash_sha256` 使用 SHA256。
- 一次 POC 内统一 hash 对象：exact raw bytes 或 canonical payload，二选一。
- repo 内只写 hash 值、row_count、returned_fields、timestamp、params fingerprint。
- hash 只能证明归档一致性，不能替代授权、版权或 PIT 证明。

## 9. Redacted report 入库规范

未来 POC 完成后，repo 内最多允许新增一份脱敏报告，例如：

`docs/quant-upgrade-free-data-source-poc-result-YYYY-MM-DD.md`

允许入库：

| 内容 | 说明 |
| --- | --- |
| provider | `BaoStock` / `AKShare` |
| endpoint | 接口名 |
| docs_url | 文档链接 |
| request_timestamp | 本地请求时间，ISO 8601 + timezone |
| response_timestamp | 本地响应时间 |
| params_fingerprint | 删除敏感信息后的 params SHA256 |
| params_redacted | date_range、symbol_count、field list，不写完整行级数据 |
| response_hash_sha256 | raw archive 对应 hash |
| row_count | 返回行数 |
| returned_fields | 字段名列表 |
| missing_summary | 缺失字段、null count、duplicate count 汇总 |
| license_boundary | 免费访问、自动化、私有归档、redacted report 入库是否允许 |
| conclusion | `available` / `partial` / `missing` / `unknown` / `blocked` |

禁止入库：

- raw response。
- 行级 OHLCV。
- 行级 qfq / adjusted price。
- 行级复权因子。
- 行级停牌或 `tradestatus`。
- 行级 `isST`。
- 行级涨停价、跌停价或涨停池明细。
- 完整交易日历。
- 完整基础股票列表。
- 可还原 vendor dataset 的样本 CSV、JSON、截图或表格。
- token、cookie、session、账号、积分余额、调用日志敏感片段。

## 10. 字段可得性矩阵模板

本矩阵是未来 POC 的填写模板。当前全部为 `not_run`。

| Provider | 能力 | 候选接口 | 必需字段 / 能力 | 当前状态 | POC 后状态枚举 | 能否解除 P1-A blocker |
| --- | --- | --- | --- | --- | --- | --- |
| BaoStock | 交易日历 | `query_trade_dates` | date, is_trading_day, date range | not_run | available / partial / missing / unknown / blocked | 只能进入 calendar candidate，不能直接 formal |
| BaoStock | 股票基础信息 | `query_stock_basic` | code, name, ipo/list/out/status/type | not_run | available / partial / missing / unknown / blocked | 只能作为 universe metadata candidate |
| BaoStock | A 股日线 raw | `query_history_k_data_plus` | date, code, OHLC, preclose, volume, amount | not_run | available / partial / missing / unknown / blocked | 只能 price availability |
| BaoStock | qfq / raw 对照 | `query_history_k_data_plus` with adjust params | raw OHLC, qfq OHLC, date alignment | not_run | available / partial / missing / unknown / blocked | 无 factor/revision 时仍 partial |
| BaoStock | `tradestatus` | `query_history_k_data_plus` fields | tradestatus values, null rate | not_run | available / partial / missing / unknown / blocked | 只解除 source-provided status 是否存在 |
| BaoStock | `isST` | `query_history_k_data_plus` fields | isST values, null rate | not_run | available / partial / missing / unknown / blocked | 只解除 ST 字段是否存在 |
| BaoStock | 指数日线 | `query_history_k_data_plus` index code | index date, OHLC, preclose, volume/amount if any | not_run | available / partial / missing / unknown / blocked | 只能 benchmark candidate |
| AKShare | A 股日线 | `stock_zh_a_hist` 或等价 | date, symbol, OHLC, volume, amount | not_run | available / partial / missing / unknown / blocked | 只能 cross-check / candidate |
| AKShare | qfq | `stock_zh_a_hist(adjust="qfq")` | qfq OHLC, raw comparison, params | not_run | available / partial / missing / unknown / blocked | 无 factor/revision 时仍 partial |
| AKShare | 指数日线 | `index_zh_a_hist` 或等价 | index date, OHLC, volume/amount if any | not_run | available / partial / missing / unknown / blocked | 只能 benchmark candidate |
| AKShare | 停复牌 | `stock_tfp_em` 或公开等价接口 | code, suspend date, resume / expected date, reason | not_run | available / partial / missing / unknown / blocked | 事件级需日级展开设计 |
| AKShare | 涨跌停 | 公开涨停池 / spot / limit 相关接口，如存在 | up_limit/down_limit 或 limit pool fields | not_run | available / partial / missing / unknown / blocked | 不得假设全市场历史 limit price |

状态含义：

| 状态 | 含义 |
| --- | --- |
| `available` | 字段可得、row_count 合理、metadata 可记录、授权边界暂未阻塞 |
| `partial` | 关键字段只满足一部分，例如 qfq 可得但 factor/revision 不可得 |
| `missing` | 关键字段缺失 |
| `unknown` | 文档、返回或授权无法判断 |
| `blocked` | 授权、归档、稳定性、费用或 repo safety 阻塞 |

## 11. 授权和免费边界检查

“免费源”只表示 POC 不付费，不表示数据可以自由再分发或进入开源仓库。

未来 POC 前必须人工确认：

| 检查项 | BaoStock | AKShare |
| --- | --- | --- |
| 是否需要账号 / token | 预计无 token，但需 POC 确认 | 预计无 token，但底层源可能变化 |
| 是否需要付费 | 本 POC 目标是不付费；若发现付费或限制，标 `blocked` | 本 POC 目标是不付费；若底层源限制，标 `blocked` |
| 自动化调用 | 需确认频率、robots/服务条款、合理使用 | 需确认底层源条款和 AKShare 项目说明 |
| raw archive | 必须允许本地私有保存，否则不通过 | 必须允许本地私有保存，否则不通过 |
| redacted report 入库 | 只写字段和 hash 摘要 | 只写字段和 hash 摘要 |
| 数据再分发 | 默认不允许提交行级数据 | 默认不允许提交行级数据 |
| 稳定性 | 需记录版本、docs URL、接口错误率 | 需记录 AKShare 版本、docs URL、底层目标地址 |

任一数据源无法确认自动化、私有 raw archive 或 redacted report 入库边界时，不得进入正式 adapter 设计。

## 12. 成功标准

POC 成功不是指 Prism 可以正式使用这些数据，而是指可以安全进入下一步 adapter design review。

硬成功门槛：

| Gate | 成功标准 |
| --- | --- |
| Repo safety | 没有修改 `packages/quant`，没有写 `data/quant`，没有提交 raw data |
| Dependency safety | 当前方案不安装依赖；未来 POC 不修改 Prism repo 的依赖文件 |
| Field coverage | 至少一个 P1-A 缺口有 `available` 或有用的 `partial` 结论 |
| Metadata | 每次请求都有 provider、endpoint、docs_url、timestamp、params fingerprint、response hash、row_count、fields |
| Authorization | 免费访问、自动化、私有 raw archive、redacted report 入库均无阻塞 |
| Redaction | repo 内只有脱敏字段可得性和授权边界报告 |

能力级成功标准：

| 能力 | 成功判定 |
| --- | --- |
| Calendar | BaoStock 能返回交易日和是否交易日，且能与样本窗口另一来源交叉审计 |
| Stock basic | BaoStock 能返回代码、名称、上市日期、状态/类别等基础字段 |
| Raw daily | BaoStock 和/或 AKShare 能返回 A 股 OHLCV 和日期覆盖摘要 |
| qfq | BaoStock 和/或 AKShare 能返回 qfq 与 raw 对照；无 factor 时必须标 partial |
| `tradestatus` | BaoStock 能返回日级交易状态字段和取值集合 |
| `isST` | BaoStock 能返回 ST 字段和取值集合 |
| Index daily | BaoStock 和/或 AKShare 能返回 HS300 / CSI500 OHLCV 字段 |
| Suspend / limit | AKShare 能明确给出事件级或字段级能力；若只能涨停池，必须标 partial |

## 13. 失败标准

任一情况出现，POC 不得进入 adapter 设计。

| 失败项 | 处理 |
| --- | --- |
| 授权不清 | 保持 blocked；不得抓取或归档 raw response |
| raw archive 不允许 | POC 不通过 |
| redacted report 也不允许入库 | POC 不通过 |
| 接口不稳定到无法复现 | 标 `blocked_or_unstable` |
| BaoStock 缺 `tradestatus` / `isST` | execution flags 相关缺口保持 unavailable |
| BaoStock / AKShare 均无 CSI500 / HS300 日线 | formal market benchmark 继续 unavailable |
| qfq 可得但无 factor/revision | adjusted price 只能 partial，不得 formal |
| 只有涨停池，没有全市场 limit price | limit execution flags 不通过，只能记录 pool availability |
| 只有停复牌事件，没有日级状态 | suspend 只能 event-only，需后续日级展开设计 |
| repo 中出现 raw data | POC 判定失败，并清理/阻断后续流程 |

## 14. POC 完成后的决策树

```text
免费源 POC 是否满足 repo safety 和授权边界？
  否 ->
    停止免费源路线；保持 P1-A unavailable / research-only。
  是 ->
    BaoStock 是否覆盖 calendar + stock_basic + raw/qfq + tradestatus + isST？
      是 ->
        BaoStock 可进入 non-production adapter design review。
      否 ->
        BaoStock 只作为 partial source 或 cross-check。

    AKShare 是否覆盖 A 股日线 qfq + 指数日线？
      是 ->
        AKShare 可作为 cross-check 或 benchmark/qfq 补充候选。
      否 ->
        AKShare 只保留公开接口调研结论。

    CSI500 / HS300 index daily 是否至少一个源可用？
      否 ->
        formal excess return 继续 unavailable。
      是 ->
        只允许进入 benchmark adapter design review，不计算 excess return。

    qfq 是否有可解释 factor / revision / archive 纪律？
      否 ->
        formal adjusted return 继续 unavailable。
      是 ->
        只允许进入 adjusted price adapter design review。

    suspend / limit 是否为全市场日级字段？
      否 ->
        execution-realistic backtest 继续 forbidden。
      是 ->
        只允许进入 execution flags adapter design review。
```

## 15. 推荐执行顺序

未来如果批准执行 POC，建议按以下顺序，随时可停：

1. 只做文档和授权确认：BaoStock / AKShare 当前版本、文档 URL、免费使用和归档边界。
2. BaoStock calendar + stock_basic smoke：只记录 field list、row_count 和 hash。
3. BaoStock A 股 raw / qfq / `tradestatus` / `isST` smoke：只记录字段可得性。
4. BaoStock 指数日线 smoke：验证 HS300 / CSI500 是否可用。
5. AKShare A 股 raw / qfq smoke：只作为 cross-check。
6. AKShare index daily smoke：验证 HS300 / CSI500 是否可用。
7. AKShare 停复牌 / 涨跌停公开接口调研：只记录 available / partial / unknown。
8. 写 redacted result report，不生成任何 formal 产物。

每一步失败都可以停止，且不影响 Prism 当前 P1-A report-only 状态。

## 16. 本方案的验收清单

本方案本身应满足：

| 检查项 | 状态 |
| --- | --- |
| 只新增 docs 文件 | 是 |
| 未调用 BaoStock / AKShare API | 是 |
| 未安装依赖 | 是 |
| 未写 `data/quant` | 是 |
| 未改 `packages/quant` | 是 |
| 未生成 raw response | 是 |
| 未生成 formal labels | 是 |
| 未生成 formal excess return | 是 |
| 未做 execution-realistic backtest | 是 |
| 未影响生产排序、页面、Prism Edge、Expected 5D | 是 |

最终结论：

BaoStock + AKShare 免费 POC 可以作为 Tushare Pro 之外的低成本字段可得性验证路线。最有价值的组合是 BaoStock 验证 calendar / stock basic / `tradestatus` / `isST`，AKShare 验证 qfq 和 index daily 的 cross-check。它们能帮助判断 P1-A 缺口是否有免费补齐可能，但不能替代授权审查、raw archive、hash/timestamp discipline、PIT 证明，也不能直接把 Prism 升级到 formal labels、formal excess return 或 execution-realistic backtest。
