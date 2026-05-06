# Prism 免费数据源字段可得性 POC 结果

Date: 2026-04-30
Scope: BaoStock + AKShare non-production field availability POC
Status: completed; redacted report only

Related plan:

- `docs/quant-upgrade-free-data-source-poc-plan-2026-04-30.md`

## 0. 边界确认

本次 POC 按用户指定边界执行：

| 检查项 | 结果 |
| --- | --- |
| POC scratch | `~/.prism-private/free-data-poc/` |
| repo 外 venv | 已创建，仅位于 scratch 内 |
| 安装依赖 | 仅安装到 scratch venv，不改 repo 依赖文件 / lockfile / 主项目 venv |
| raw vendor data | 只保存到 scratch 私有 raw 目录 |
| repo 内输出 | 仅新增本脱敏结果报告 |
| `packages/quant` | 未修改 |
| `data/quant` | 未写入 |
| 生产排序 / A/B/C / 页面 / Prism Edge / Expected 5D / ML | 未修改、未生成 |
| formal labels / formal excess return / formal adjusted return | 未生成 |
| execution-realistic backtest | 未执行 |

本报告不包含行级行情、完整交易日历、完整股票列表、raw response 片段、可还原 vendor dataset 的样本数据、token、cookie、session 或账号敏感信息。

## 1. 执行摘要

执行环境：

| 项目 | 值 |
| --- | --- |
| 主运行时间 | 2026-04-30T22:20:53+08:00 至 2026-04-30T22:23:15+08:00 |
| AKShare 指数补充探测 | 2026-04-30T22:24:51+08:00 至 2026-04-30T22:25:04+08:00 |
| 日期窗口 | 2024-01-02 至 2024-01-10 |
| 股票样本 | 贵州茅台、宁德时代、平安银行 |
| 指数样本 | HS300、CSI500 |
| raw 私有归档文件数 | 30 |
| 主摘要状态 | 25 checks: 21 ok, 4 error |
| 补充摘要状态 | 5 checks: 2 ok, 3 error |

依赖版本：

| 包 | 版本 |
| --- | --- |
| `akshare` | 1.18.59 |
| `baostock` | pip package 0.9.1; module `__version__` reported `00.9.10` |
| `pandas` | 3.0.2 |

一句话结论：

BaoStock 在本小样本内覆盖 P1-A 最关键的免费源字段可得性：交易日历、股票基础信息、A 股 raw OHLCV、前复权 qfq、`tradestatus`、`isST`、HS300 / CSI500 指数日线均返回字段和非空数据。AKShare 可作为 raw/qfq 股票日线 cross-check，并可通过中证指数接口补充 HS300 / CSI500 指数日线；但其东方财富指数接口在本环境出现连接 / SSL 错误，且停牌 / 涨跌停能力仍只适合 research-only 字段调研。

## 2. BaoStock 结果

### 2.1 可用字段

| 能力 | 接口 | row_count | 字段清单 | 非空情况 | SHA256 |
| --- | --- | ---: | --- | --- | --- |
| 交易日历 | `query_trade_dates` | 9 | `calendar_date`, `is_trading_day` | 两字段均 9/9 非空 | `f820f40ce0691df9a4a2c4cae349f98566d7354e109303b2442c05f743f02981` |
| 贵州茅台基础信息 | `query_stock_basic` | 1 | `code`, `code_name`, `ipoDate`, `outDate`, `type`, `status` | 除 `outDate` 为 0/1 外，其余 1/1 非空 | `d50de0559de8800c87d6256e2b2e9ef8f9de4f96783da95bd504dfbedb2b7651` |
| 宁德时代基础信息 | `query_stock_basic` | 1 | `code`, `code_name`, `ipoDate`, `outDate`, `type`, `status` | 除 `outDate` 为 0/1 外，其余 1/1 非空 | `b55cd7b34ce1637da13b4c4b2617917c6c248fe63ce59395e393ff96b3b7f7a6` |
| 平安银行基础信息 | `query_stock_basic` | 1 | `code`, `code_name`, `ipoDate`, `outDate`, `type`, `status` | 除 `outDate` 为 0/1 外，其余 1/1 非空 | `4803fa0746a0f37fa3fe462a5a82b1ddf630ed16dd14ba4918a6a2b087fcad0b` |

股票日线字段：

| 样本 | 口径 | row_count | 字段清单 | 非空情况 | SHA256 |
| --- | --- | ---: | --- | --- | --- |
| 贵州茅台 | 不复权 | 7 | `date`, `code`, `open`, `high`, `low`, `close`, `preclose`, `volume`, `amount`, `adjustflag`, `turn`, `tradestatus`, `pctChg`, `isST` | 全部字段 7/7 非空 | `6f41bd3a74b2c83e2636b6dd0c6d84cc3f5527aab245e39d7356bdd397297541` |
| 贵州茅台 | 前复权 / qfq | 7 | 同上 | 全部字段 7/7 非空 | `d57c3244a58f2277abb3b35d8c40831c4a79cb1270f88c6d04bbbaa01e268f29` |
| 宁德时代 | 不复权 | 7 | 同上 | 全部字段 7/7 非空 | `90d2df509a32a7c9e5e30cb91c2e5d43ec6fdc7e5135870f048bcdfd650d802e` |
| 宁德时代 | 前复权 / qfq | 7 | 同上 | 全部字段 7/7 非空 | `7eb96fad5cd48813056b5a05443b3733ef1cfb312c963825ad8c470b5aee6442` |
| 平安银行 | 不复权 | 7 | 同上 | 全部字段 7/7 非空 | `f5c86701051b4ccc21678b2c48ab3778f972413537b3ee4ffdb186c8831324a0` |
| 平安银行 | 前复权 / qfq | 7 | 同上 | 全部字段 7/7 非空 | `8ce41ac06f3b3b93e8a5896a1313e980ad29fc7c247bebecede214745040c225` |

指数日线字段：

| 指数 | 接口 | row_count | 字段清单 | 非空情况 | SHA256 |
| --- | --- | ---: | --- | --- | --- |
| HS300 | `query_history_k_data_plus` | 7 | `date`, `code`, `open`, `high`, `low`, `close`, `preclose`, `volume`, `amount`, `pctChg` | 全部字段 7/7 非空 | `6a4c4c3b48733eff581e188d932aa0c17a734fb11ad5cbc36924bd090d3bfcfe` |
| CSI500 | `query_history_k_data_plus` | 7 | `date`, `code`, `open`, `high`, `low`, `close`, `preclose`, `volume`, `amount`, `pctChg` | 全部字段 7/7 非空 | `444f1afda1b58fbe909cc81d8a7f55211310388a596ad6e36c0db66252b999d8` |

### 2.2 缺失 / 不确定

| 项目 | 结论 |
| --- | --- |
| 独立 `adj_factor` / factor revision | 本次未验证到可解释复权因子或 revision；qfq price 可用不等于 formal adjusted return ready |
| 涨跌停价格 | BaoStock 本次主接口未返回 `up_limit` / `down_limit` |
| 停复牌事件表 | 本次以 `tradestatus` 为日级交易状态候选；未验证独立停复牌事件接口 |
| 授权 / PIT | 免费可调用不等于允许再分发或 PIT-ready；仍需长期 raw archive、版本和授权审查 |

BaoStock 对 P1-A 的实际价值：可以优先进入 free-source adapter design，作为 calendar / stock basic / raw daily / qfq / `tradestatus` / `isST` / index daily 的 non-production 候选源。

## 3. AKShare 结果

### 3.1 股票日线与 qfq

| 样本 | 口径 | row_count | 字段清单 | 非空情况 | 状态 | SHA256 |
| --- | --- | ---: | --- | --- | --- | --- |
| 贵州茅台 | 不复权 | 7 | `日期`, `股票代码`, `开盘`, `收盘`, `最高`, `最低`, `成交量`, `成交额`, `振幅`, `涨跌幅`, `涨跌额`, `换手率` | 全部字段 7/7 非空 | ok | `6dca6c94c86a75eaed9cfa1e3ffbf2980d15491c6147f706b6210d29c820bc4e` |
| 贵州茅台 | qfq | 7 | 同上 | 全部字段 7/7 非空 | ok | `2f8d337f90cf5a52c508f49dc22f8e3d0279f8ac08e82bf53a9ab47257d26a88` |
| 宁德时代 | 不复权 | 7 | 同上 | 全部字段 7/7 非空 | ok | `1a720421e541d1f02785f6e71ad36dee57885ef2a29b46c60be2a91f1209d6d4` |
| 宁德时代 | qfq | 7 | 同上 | 全部字段 7/7 非空 | ok | `56e2d8054bfd3c7a0450a0cae6501385d6192b96c185b6cbb757d5f950bbbda5` |
| 平安银行 | 不复权 | 7 | 同上 | 全部字段 7/7 非空 | ok | `3eeb709936f4a67bab4ee7bbb2f7148305fc75cf36ffc4f2778ed5237613dc7d` |
| 平安银行 | qfq | 0 | none | none | error | `c0da0ac105c5f45d86f0da723405d3c677f1acbbba12f4c40e86c3fbb5da0135` |

平安银行 qfq error 摘要：`ProxyError` against `push2his.eastmoney.com`; this is a provider / network failure in this POC run, not proof that qfq field is absent.

AKShare `stock_zh_a_hist` 缺口：

- 未返回 `pre_close` 字段；如未来需要前收，需单独接口、衍生逻辑或字段映射设计。
- 未返回 `tradestatus` / `isST`。
- 未返回独立 `adj_factor` 或 factor revision。
- qfq 可用性本次为 partial：2/3 样本成功，1/3 因网络 / provider 失败。

### 3.2 指数日线

AKShare 首选文档接口 `index_zh_a_hist` 在本环境失败：

| 指数 | 接口 | row_count | 状态 | 错误摘要 | SHA256 |
| --- | --- | ---: | --- | --- | --- |
| HS300 | `index_zh_a_hist` | 0 | error | `SSLError` against `80.push2.eastmoney.com` | `940f1e6e03da366e07675928192210d034d37c07e97d2b05af3f4a11c1b120e0` |
| CSI500 | `index_zh_a_hist` | 0 | error | `ProxyError` against `80.push2.eastmoney.com` | `b8cc1356aa25bb80001d522fafe8617b613888053011c09e90aa9dba54208879` |

AKShare 东方财富指数补充接口 `stock_zh_index_daily_em` 同样失败：

| 指数 / symbol | row_count | 状态 | 错误摘要 | SHA256 |
| --- | ---: | --- | --- | --- |
| HS300 / `sh000300` | 0 | error | `ProxyError` against `push2his.eastmoney.com` | `b8705a837f4dfd301d5c9508f8287d8b91a70e50bde37dfe0e20ae94584da7d3` |
| CSI500 / `sh000905` | 0 | error | `ProxyError` against `push2his.eastmoney.com` | `60e3e750560b2beb0a5ab36a8cc6374edb045ba64f2c8dac41fad2175b807697` |
| CSI500 / `csi000905` | 0 | error | `ProxyError` against `push2his.eastmoney.com` | `75daf862a94c064bf3f0fb4dcfd8d7e1a6053ee4dfc539d07eeb00d7c82f018d` |

AKShare 中证指数补充接口 `stock_zh_index_hist_csindex` 成功：

| 指数 | row_count | 字段清单 | 非空情况 | 注意 | SHA256 |
| --- | ---: | --- | --- | --- | --- |
| HS300 | 7 | `日期`, `指数代码`, `指数中文全称`, `指数中文简称`, `指数英文全称`, `指数英文简称`, `开盘`, `最高`, `最低`, `收盘`, `涨跌`, `涨跌幅`, `成交量`, `成交金额`, `样本数量`, `滚动市盈率` | 全部返回字段 7/7 非空 | `成交金额` 可作为 `成交额` 等价候选；仍需字段映射确认 | `56b731261e51a1230d2301431827c57eec9ad3152ec48cd1911ac3feaffd0b89` |
| CSI500 | 7 | 同上 | 全部返回字段 7/7 非空 | 同上 | `1bbd3df93f8edf8d42947dada183b10e74068d8e8fac8cb35d5e2ec25a6fa79f` |

### 3.3 停牌 / 涨跌停相关字段

| 能力 | 接口 | row_count | 字段清单 | 非空情况 | 状态 | SHA256 |
| --- | --- | ---: | --- | --- | --- | --- |
| 停复牌事件 | `stock_tfp_em` | 830 | `序号`, `代码`, `名称`, `停牌时间`, `停牌截止时间`, `停牌期限`, `停牌原因`, `所属市场`, `预计复牌时间` | `停牌截止时间` 813/830；`预计复牌时间` 750/830；其余 830/830 | ok | `35f556803f77abcaa222f38aa8ccdb9ec9512c0bfce6a0916f9580ecc2b2461e` |
| 涨停池 | `stock_zt_pool_em(date=20240105)` | 0 | none | none | ok-empty | `5021a18642f0f17c1bfce9b758550e34b4cc89b286b179e6dd71a5a4d6194c95` |
| 跌停股池 | `stock_zt_pool_dtgc_em(date=20240105)` | 0 | none | none | error | `4d0e7e406853a2d7c91dda4f79cbffc029b6ff6148bf3be5fef91531b8bf0908` |
| 强势股池 | `stock_zt_pool_strong_em(date=20240105)` | 0 | none | none | ok-empty | `5021a18642f0f17c1bfce9b758550e34b4cc89b286b179e6dd71a5a4d6194c95` |

跌停股池错误摘要：`ValueError: 跌停股池只能获取最近 30 个交易日的数据`。

AKShare 对 P1-A 的实际价值：可作为 BaoStock 的股票日线 qfq cross-check，并可通过 `stock_zh_index_hist_csindex` 补充 HS300 / CSI500 index daily 字段验证。停复牌接口是事件级，不是日级 `tradestatus`；涨跌停池不是全市场历史 `up_limit` / `down_limit`，不得用于 execution-realistic 结论。

## 4. 对 P1-A 需求的覆盖判断

| P1-A 需求 | BaoStock | AKShare | 覆盖结论 |
| --- | --- | --- | --- |
| Benchmark: HS300 / CSI500 指数日线 | 可用；HS300 / CSI500 均返回 OHLC、preclose、volume、amount | 可用但需绕开失败的东方财富接口；中证指数接口返回 OHLC、成交量、成交金额 | 字段可得性通过；可进入 non-production benchmark adapter design，但不得计算 formal excess return |
| Adjusted price: raw / qfq | 可用；3 个股票样本 raw 与 qfq 均返回 | partial；raw 3/3 成功，qfq 2/3 成功，1/3 网络失败 | 可进入 adjusted price adapter design 的 field phase；没有 factor/revision，不能 formal |
| `tradestatus` | 可用；BaoStock 股票日线返回 `tradestatus` 且样本全非空 | `stock_zh_a_hist` 未返回；`stock_tfp_em` 是事件级 | BaoStock 可作为日级交易状态候选；仍不是真实成交证明 |
| `isST` | 可用；BaoStock 股票日线返回 `isST` 且样本全非空 | `stock_zh_a_hist` 未返回 | BaoStock 可作为 ST 状态候选；仍需规则版本和覆盖审计 |
| 停牌字段 | 未验证独立事件表；可用 `tradestatus` 做日级候选 | `stock_tfp_em` 可返回事件级字段 | partial；需要日级展开和 calendar 对齐设计 |
| 涨跌停字段 | 未返回 `up_limit` / `down_limit` | 涨停 / 跌停池不能替代全市场历史 limit price | 不通过；execution limit flags 仍 unavailable |
| Label upgrade | 仅字段可得性 | 仅字段可得性 | 不覆盖；formal label upgrade 继续 blocked |

## 5. 是否能替代 Tushare 被权限挡住的部分

可以替代一部分“字段可得性验证”，不能替代 Tushare 或授权源的 formal 数据主源判断。

| Tushare 被挡能力 | 免费源替代性 | 说明 |
| --- | --- | --- |
| 交易日历 | BaoStock 可部分替代 | 字段可得；仍需授权、PIT、官方休市 cross-check |
| 股票基础信息 | BaoStock 可部分替代 | 基础字段可得；全市场和历史状态仍需覆盖审计 |
| A 股 raw OHLCV | BaoStock 可替代字段验证，AKShare 可 cross-check | 不能把 raw 行情提交 repo，也不能直接接主线 |
| qfq / adjusted price | 部分替代 | qfq price 可得；缺 adj_factor / revision / PIT 证明 |
| HS300 / CSI500 index daily | BaoStock 可替代字段验证；AKShare 中证接口可 cross-check | 可进入 benchmark adapter design，但不生成 benchmark_return |
| `tradestatus` / `isST` | BaoStock 有明显替代价值 | 可支持 execution availability research；不能证明真实成交 |
| 停牌 | AKShare event-only + BaoStock tradestatus partial | 需要日级展开和冲突处理 |
| 涨跌停 | 不能替代 | 未验证到全市场历史 `up_limit` / `down_limit`；涨停池/跌停池不够 |

## 6. Research-only 字段清单

以下字段或能力即使本次可得，也只能 research-only：

- BaoStock / AKShare raw OHLCV：可做字段验证和 cross-check，不能直接入 `data/quant` 或主线。
- BaoStock / AKShare qfq price：缺少独立 adj_factor、factor revision 和 as-of archive，不能 formal adjusted return。
- BaoStock HS300 / CSI500 index daily：可作为 benchmark candidate，不得直接生成 formal excess return。
- AKShare `stock_zh_index_hist_csindex` index daily：可作为 index cross-check，不得直接生成 formal excess return。
- BaoStock `tradestatus`：可作为 execution flag 候选输入，不能证明真实可成交、failed order 或 partial fill。
- BaoStock `isST`：可作为 ST 状态候选输入，不能替代完整规则版本表。
- AKShare `stock_tfp_em`：事件级停复牌字段，只能用于日级展开设计前调研。
- AKShare 涨停池 / 跌停池 / 强势股池：池类接口不能替代全市场历史 limit price。

## 7. Adapter design 建议

建议进入 **free-source adapter design**，但范围必须很窄：

| Adapter 方向 | 建议 | 约束 |
| --- | --- | --- |
| BaoStock field adapter | 建议优先设计 | 只做 non-production，覆盖 calendar、stock basic、raw daily、qfq、`tradestatus`、`isST`、index daily |
| AKShare cross-check adapter | 建议设计为补充源 | 覆盖 stock raw/qfq cross-check、`stock_zh_index_hist_csindex` index daily、停牌 event-only 调研 |
| Benchmark adapter | 可进入设计评审 | 只冻结字段契约、hash/timestamp、coverage audit；不计算 formal excess return |
| Adjusted price adapter | 可进入设计评审 | 必须把 qfq-only 标为 partial；没有 adj_factor/revision 前不得 formal |
| Execution flags adapter | 只建议做 availability design | 可研究 `tradestatus`、`isST`、event-only suspend；limit price 仍 unavailable |
| Label upgrade adapter | 不建议进入实现 | formal labels、formal adjusted return、formal excess return、execution-realistic backtest 仍全部 blocked |

下一步推荐：

1. 写 free-source adapter design doc，而不是直接写 `packages/quant`。
2. 明确 provider priority：BaoStock primary candidate，AKShare cross-check / supplement。
3. 设计 redacted manifest schema：provider、endpoint、params fingerprint、response hash、row_count、field list、coverage summary、license note。
4. 先做 repo 外 repeatability POC：同一小样本重复 2-3 次，确认字段和 hash 变化行为。
5. 再决定是否开一个 strictly non-production adapter implementation card。

最终结论：

BaoStock + AKShare 能免费补齐 P1-A 的大部分字段可得性疑问，尤其是 BaoStock 对 calendar / stock basic / daily raw / qfq / `tradestatus` / `isST` / index daily 的覆盖很强。它们可以替代 Tushare 当前权限 blocker 中的“字段验证”部分，但不能替代授权审查、PIT 归档、复权因子 revision、涨跌停价格、真实执行数据和 formal label upgrade。
