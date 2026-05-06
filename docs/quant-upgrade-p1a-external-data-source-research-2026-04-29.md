# Prism 量化升级 P1-A 外部数据源调研

Date: 2026-04-29
Role: external data source researcher
Scope: P1-A data hardening research only
Status: research document; no code, no data generation

## 0. 本文边界

本文只调研外部数据源，不写代码，不安装依赖，不调用任何需要 token 或付费账号的接口，不生成 benchmark 数据，不修改仓库业务产物。

严格边界：

- 不修改 `packages/quant`。
- 不修改 `data/quant`。
- 不生成 `CSI500` / `HS300` benchmark 数据。
- 不生成 adjusted price、停牌、涨跌停、failed order 或 partial fill 数据。
- 不做页面、Prism Edge、ML 或策略研究。
- 当前 Prism 所有量化结果仍保持 `research-only` / `report-only`。

本文区分两类表述：

- **官方事实**：来自交易所、指数公司、财政部、税务总局、中国结算或数据源官方文档。
- **研究推断**：基于 Prism P1-A 目标、数据契约和工程可维护性做出的建议，不等同于已拍板方案。

## 1. 结论先行

### 1.1 最推荐的 1-2 条路线

**路线 A：Tushare Pro + 官方规则文件 + 本地快照归档**

适合作为 P1-A 最小可行方案的首选候选。Tushare Pro 文档显示其覆盖交易日历、日线、复权行情、指数日线、每日涨跌停价格等接口，并采用积分/权限制度。Prism 若采用该路线，需要人工确认 token、积分、授权、再分发限制和自动化调用配额。

优势：

- 一个源可覆盖 benchmark OHLC、个股日线、复权/复权因子、停复牌或涨跌停相关接口、交易日历。
- 自动化友好，Python 生态成熟。
- P1-A 可先落地 source manifest、hash、coverage audit 和 unavailable 降级。

主要风险：

- 不是官方交易所直连数据。
- token / 积分 / 调用频率 / 商业使用授权需要人工确认。
- point-in-time 证明不能只靠历史接口；Prism 必须保存每日原始响应、抓取时间、source hash 和 revision。

来源：

- [Tushare 数据接口与积分说明](https://tushare.pro/document/1?doc_id=108)
- [Tushare pro_bar 复权行情说明](https://www.tushare.pro/document/1?doc_id=109)
- [Tushare index_daily 指数日线接口](https://tushare.pro/document/2?doc_id=95)

**路线 B：RiceQuant / JoinQuant / Wind / Choice 等授权数据源 + 官方规则文件**

适合作为 P1-B 更稳方案，尤其是 execution flags、limit up/down、停牌、tick / 盘口、partial fill 保守估算。RiceQuant 和 JoinQuant 文档公开展示了 `limit_up` / `limit_down`、停牌、复权、tick 或 current data 等字段；Wind / Choice / iFinD 更偏机构授权，通常稳定性和字段覆盖更强，但成本和授权约束也更重。

优势：

- execution data 覆盖更接近回测需要。
- tick / bid-ask / limit price / paused / ST 等字段更完整。
- 适合后续从 `research_only_simulation` 升级为更可信的 formal research evaluation。

主要风险：

- 多数需要付费账号、授权协议或平台环境。
- 开源项目再分发和自动化部署限制更严格。
- 仍需要本地快照归档才能证明 PIT。

来源：

- [JoinQuant 股票数据文档](https://www.joinquant.com/help/data/stock?f=home)
- [RiceQuant RQData generic API](https://www.ricequant.com/doc/rqdata/python/generic-api)
- [同花顺量化 API 文档](https://quant.10jqka.com.cn/view/help/4?from=ifind)
- [东方财富 Choice / EMQuant 文档示例](https://emquant.18.cn/help/doc/cpp/book.pdf)

### 1.2 当前不建议的路线

不建议把以下来源直接作为 P1-A formal 数据源：

- 只抓网页行情页面，不保留官方或授权接口来源。
- 只用当前 raw OHLCV 推断前复权、停牌、涨跌停或订单成交。
- 只用 AKShare / BaoStock 回填历史数据但不做 source hash、revision、授权和 PIT 归档。
- 把 `eligible_universe_equal_weight` 当成 CSI500 / HS300 market benchmark。
- 用当前前复权序列直接回写历史 labels，而不保存复权因子、source timestamp、effective date 和 PIT 说明。

## 2. Benchmark 数据源调研

目标：冻结 `CSI500`、`HS300` 指数日线数据，至少需要 `trade_date`、`open`、`high`、`low`、`close`、`prev_close`、source、hash、revision 和 coverage audit。

### 2.1 官方来源

#### 中证指数有限公司

官方事实：

- 沪深 300 和中证 500 均由中证指数有限公司编制和维护。
- 中证指数公开发布指数编制方案、计算与维护规则。公开文档能证明指数定义、样本调整、停牌处理原则和指数计算规则。
- 公开文档不等于可自动化下载的免费历史 OHLC API；指数历史行情的可商用、可自动化获取通常需要确认中证指数或授权数据商的数据服务和许可。

来源：

- [沪深 300 指数编制方案](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/000300_Index_Methodology_cn.pdf)
- [中证系列规模指数编制方案，含中证 500 规则](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/000904_Index_Methodology_cn.pdf)
- [中证指数股票指数计算与维护细则](https://oss-ch.csindex.com.cn/notice/20230908165124-%E3%80%8A%E4%B8%AD%E8%AF%81%E6%8C%87%E6%95%B0%E6%9C%89%E9%99%90%E5%85%AC%E5%8F%B8%E8%82%A1%E7%A5%A8%E6%8C%87%E6%95%B0%E8%AE%A1%E7%AE%97%E4%B8%8E%E7%BB%B4%E6%8A%A4%E7%BB%86%E5%88%99%E3%80%8B.pdf)

字段覆盖判断：

| 项目 | 判断 |
| --- | --- |
| open/high/low/close | 官方指数公司一定具备计算和发布能力；公开免费自动化 API 需单独确认。 |
| 历史覆盖 | 指数历史长期覆盖应完整；自动化授权范围需确认。 |
| 自动化 | 官方直接自动化能力不应默认假设，需要数据服务协议。 |
| 开源项目适用性 | 如果只是引用公开规则可以；若把历史行情数据放入仓库，需要确认版权和再分发。 |

研究推断：

- P1-A 如果追求低风险，官方中证数据最权威，但采购/授权摩擦最大。
- 如果 Prism 只是内部研究，不公开再分发数据，可以优先确认 Tushare / RiceQuant / Wind / Choice 是否已获得可用授权。

### 2.2 开源 Python 数据源

#### AKShare

官方事实：

- AKShare 指数数据文档显示 `index_zh_a_hist` 可取中国股票指数历史行情，输出含日期、开盘、收盘、最高、最低、成交量、成交额、涨跌幅等字段，目标地址为东方财富指数行情。
- AKShare 是开源 Python 数据接口聚合项目，便于自动化，但底层网页/接口可能变化，稳定性和授权边界需自行承担。

来源：

- [AKShare 指数数据文档](https://akshare-hh.readthedocs.io/en/latest/data/index/)
- [AKShare 项目与接口变动示例 issue](https://github.com/akfamily/akshare/issues/5975)

字段覆盖判断：

| 项目 | 判断 |
| --- | --- |
| open/high/low/close | 文档显示支持。 |
| 历史覆盖 | 支持按 start/end 拉取，但不同接口历史范围和可用性需实测。 |
| 自动化 | 自动化友好。 |
| 开源项目适用性 | 代码开源友好；底层数据再分发和接口稳定性不等于开源授权。 |

研究推断：

- AKShare 可作为 P1-A 的快速 benchmark coverage audit 候选。
- 不建议直接作为唯一 formal 数据源，除非 Prism 保存 raw response、hash、抓取时间，并接受底层接口变动风险。

#### BaoStock

官方事实：

- BaoStock Python API 常见接口包括历史 K 线、交易日历、复权因子等；社区文档和项目材料显示 `query_history_k_data_plus` 包含 `open/high/low/close/preclose/volume/amount/adjustflag/tradestatus/isST` 等字段，另有交易日历和复权因子相关接口。

来源：

- [BaoStock 官方站点](http://baostock.com/)
- [BaoStock GitHub 镜像](https://github.com/shimencaiji/baostock)
- [BaoStock 复权因子简介 PDF 镜像](https://gitee.com/evan1970/baostock/blob/master/BaoStock%E5%A4%8D%E6%9D%83%E5%9B%A0%E5%AD%90%E7%AE%80%E4%BB%8B.pdf?skip_mobile=true)

字段覆盖判断：

| 项目 | 判断 |
| --- | --- |
| open/high/low/close | 通常支持。 |
| 历史覆盖 | 历史覆盖较长，需按指数代码和股票代码分别实测。 |
| 自动化 | 自动化友好，无 token 门槛较低。 |
| 开源项目适用性 | 适合研究验证；正式授权和稳定性需人工确认。 |

研究推断：

- BaoStock 适合作为免费 fallback 和 cross-check source。
- 由于维护活跃度、接口稳定性和数据版权不如机构源清晰，不建议单独承担 P1-A formal source。

### 2.3 付费或授权数据源

| 数据源 | Benchmark OHLC | 自动化 | 开源项目适用性 | 备注 |
| --- | --- | --- | --- | --- |
| Tushare Pro | `index_daily` 覆盖指数日线，需 token/积分 | 高 | 需要确认授权和再分发 | 最适合 P1-A 最小可行路线。 |
| RiceQuant RQData | `get_price` 可取指数/股票行情，字段覆盖强 | 高 | 需要账号和授权 | 更适合 P1-B 或稳定研究环境。 |
| JoinQuant | `get_price` 可取指数/股票 OHLC，平台内自动化友好 | 中高 | 平台/授权限制需确认 | 对执行字段也有帮助。 |
| Wind | 覆盖全面 | 高，需 WindPy/终端 | 付费授权，不适合开源再分发 | 机构标准，但成本高。 |
| Choice / EMQuant / iFinD | 覆盖全面 | 高，需客户端或授权 | 付费授权，不适合开源再分发 | 适合作二级校验或机构路线。 |

## 3. 复权数据源调研

目标：冻结 A 股前复权 / 后复权 / 复权因子来源，使 labels 能明确 `raw_return`、`adjusted_return`、`net_return`，并区分 PIT-ready 与 research-only。

### 3.1 官方事实与关键风险

官方事实：

- 交易所和中证指数文档能定义指数和交易规则，但个股复权序列通常由行情商或数据商根据除权除息、送转、配股等公司行为计算。
- 中证指数维护规则包含公司事件和开盘参考价等计算概念，但这不等于 Prism 可以从公开网页直接取得个股 qfq/hfq/adj_factor。

来源：

- [中证指数股票指数计算与维护细则](https://oss-ch.csindex.com.cn/notice/20230908165124-%E3%80%8A%E4%B8%AD%E8%AF%81%E6%8C%87%E6%95%B0%E6%9C%89%E9%99%90%E5%85%AC%E5%8F%B8%E8%82%A1%E7%A5%A8%E6%8C%87%E6%95%B0%E8%AE%A1%E7%AE%97%E4%B8%8E%E7%BB%B4%E6%8A%A4%E7%BB%86%E5%88%99%E3%80%8B.pdf)

研究推断：

- 对 Prism 来说，最安全的 formal return 不是直接保存某个“当前前复权价格序列”，而是保存：
  - raw OHLC；
  - adj_factor；
  - factor effective date；
  - source timestamp；
  - source hash；
  - vendor adjustment policy；
  - label entry/exit 日期所用的 factor revision。
- 如果复权因子是当前接口回算的历史序列，而不是 as-of 归档，PIT 证明弱。可用于 report-only，但不能直接称 formal PIT-ready。

### 3.2 Tushare Pro

官方事实：

- Tushare 文档显示 `pro_bar` 支持复权行情，并可通过参数返回复权因子；数据权限受积分制度约束。
- Tushare 数据列表中包含复权行情、每日涨跌停价格、交易日历等接口类别。

来源：

- [Tushare 数据接口与积分说明](https://tushare.pro/document/1?doc_id=108)
- [Tushare pro_bar 复权行情说明](https://www.tushare.pro/document/1?doc_id=109)

字段覆盖判断：

| 项目 | 判断 |
| --- | --- |
| qfq / hfq | 文档显示 `pro_bar` 支持复权行情。 |
| adj_factor | 文档显示可返回复权因子。 |
| PIT 可证明性 | 仅靠历史 API 不足；需要 Prism 每日归档响应和 timestamp。 |
| 按日期复现 | 可以按 date/code 查询；revision 需要本地 manifest 固化。 |
| 风险 | token、积分、授权、数据修订和再分发限制。 |

### 3.3 AKShare

官方事实：

- AKShare A 股历史行情接口通常提供不复权、前复权、后复权参数；底层多来自东方财富等公开行情源。

来源：

- [AKShare 文档入口](https://akshare.akfamily.xyz/)
- [AKShare 指数数据文档](https://akshare-hh.readthedocs.io/en/latest/data/index/)

字段覆盖判断：

| 项目 | 判断 |
| --- | --- |
| qfq / hfq | 通常支持。 |
| adj_factor | 多数行情接口返回 adjusted price，不一定返回独立 adj_factor。 |
| PIT 可证明性 | 弱；需要本地快照和 source response。 |
| 按日期复现 | 可以按 start/end 拉取，但底层接口变动风险高。 |
| 风险 | 底层接口变化、数据授权和字段口径不稳定。 |

研究推断：

- AKShare 可作为复权口径 smoke check。
- 不建议作为 formal adjusted return 的唯一来源，除非 P1-A 只做 `available_report_only`，并清楚标记 PIT weakness。

### 3.4 BaoStock

官方事实：

- BaoStock 提供复权因子相关材料，历史 K 线接口常见 `adjustflag` 参数。

来源：

- [BaoStock 官方站点](http://baostock.com/)
- [BaoStock 复权因子简介 PDF 镜像](https://gitee.com/evan1970/baostock/blob/master/BaoStock%E5%A4%8D%E6%9D%83%E5%9B%A0%E5%AD%90%E7%AE%80%E4%BB%8B.pdf?skip_mobile=true)

字段覆盖判断：

| 项目 | 判断 |
| --- | --- |
| qfq / hfq | 常见接口支持复权标志，需按官方文档确认 flag 含义。 |
| adj_factor | 有复权因子资料。 |
| PIT 可证明性 | 弱到中；需本地归档和 revision。 |
| 按日期复现 | 可查询历史区间。 |
| 风险 | 维护活跃度、授权、接口稳定性和历史修订。 |

### 3.5 JoinQuant / RiceQuant / Wind / Choice / iFinD

官方事实：

- JoinQuant 文档显示 `get_price` 支持 `fq='pre'`、`fq=None`、`fq='post'`，返回 open/close/high/low/volume/money/factor，并提供 paused、high_limit、low_limit、is_st 等当前数据字段。
- RiceQuant 文档显示 `get_price` 支持 `adjust_type='none'` 等参数，日线和 tick 示例中包含 open/high/low/close/volume/total_turnover/limit_up/limit_down 等字段。
- 同花顺 / Choice / EMQuant 文档显示机构级行情、状态和证券属性字段，部分字段可覆盖 ST、停牌或涨跌停，但需授权。

来源：

- [JoinQuant 股票数据文档](https://www.joinquant.com/help/data/stock?f=home)
- [JoinQuant API PDF](https://cdn.joinquant.com/help/img/JoinQuantAPI.pdf)
- [RiceQuant RQData generic API](https://www.ricequant.com/doc/rqdata/python/generic-api)
- [同花顺量化 API 文档](https://quant.10jqka.com.cn/view/help/4?from=ifind)
- [EMQuant 文档示例](https://emquant.18.cn/help/doc/cpp/book.pdf)

研究推断：

- P1-B 若目标是更强 PIT 和 execution realism，应优先考虑授权数据源，尤其是能提供 daily + tick + limit + paused + corporate actions 的一体化源。
- 即使是付费源，也不能省略 Prism 本地 raw response archive；否则后续无法证明某日运行时看到的是什么。

## 4. 执行数据源调研

目标：让 labels/backtest 能明确停牌、涨跌停、ST/板块涨跌幅限制、failed order、partial fill。

### 4.1 停牌数据

官方事实：

- JoinQuant 文档显示 `paused` 字段可表示是否停牌；停牌时 open/close/low/high/pre_close 可填充为停牌前收盘价，volume/money 为 0。
- Tushare 数据列表包含停复牌相关接口类别，具体权限和字段需要按当前账号确认。
- BaoStock 历史 K 线字段常见 `tradestatus`。

来源：

- [JoinQuant 股票数据文档](https://www.joinquant.com/help/data/stock?f=home)
- [Tushare 数据接口与积分说明](https://tushare.pro/document/1?doc_id=108)
- [BaoStock 官方站点](http://baostock.com/)

研究推断：

- 停牌不能只靠“缺少 price row”或“volume=0”推断为 formal 事实。
- P1-A 可以保守使用 source-provided paused/tradestatus；若没有字段，则 label 必须保留 `suspend_status_unknown`。

### 4.2 涨跌停价格和状态

官方事实：

- JoinQuant 文档显示 current data 提供 `high_limit`、`low_limit`、`paused`、`is_st`。
- RiceQuant tick / price 示例包含 `limit_up`、`limit_down`。
- Tushare 数据列表显示有每日涨跌停价格 `stk_limit` 类接口。

来源：

- [JoinQuant 股票数据文档](https://www.joinquant.com/help/data/stock?f=home)
- [RiceQuant RQData generic API](https://www.ricequant.com/doc/rqdata/python/generic-api)
- [Tushare 数据接口与积分说明](https://tushare.pro/document/1?doc_id=108)

研究推断：

- P1-A 可以把 source-provided `limit_up_price` / `limit_down_price` 作为优先源。
- 若只有 OHLC 和前收盘价，可以推断 `open_at_limit_up` / `close_at_limit_up` 的近似状态，但必须标记 `inferred_limit_status` 或 `limit_execution_ambiguous`，不能称为交易所确认。

### 4.3 ST、科创板、创业板和不同涨跌幅限制

官方事实：

- 上交所 2026 年修订交易规则已发布，规则自 2026-07-06 起施行；上交所公告说明修订点包括将主板风险警示股票价格涨跌幅限制比例由 5% 调整为 10%。
- 深交所 2023 年修订交易规则仍是当前公开主要规则基础之一。
- 深交所投资者教育页面说明，创业板股票上市后前 5 个交易日不设涨跌幅限制，此后竞价交易涨跌幅限制比例为 20%。
- 深交所 2023 年交易规则 PDF 提及创业板股票或其他实行 20% 涨跌幅限制股票的相关规则。

来源：

- [上交所修订发布《上海证券交易所交易规则》新闻说明](https://www.sse.com.cn/aboutus/mediacenter/hotandd/c/c_20260424_10816474.shtml)
- [上海证券交易所交易规则（2026 年修订）](https://www.sse.com.cn/lawandrules/sselawsrules2025/trade/universal/c/c_20260424_10816492.shtml)
- [深圳证券交易所交易规则（2023 年修订）PDF](https://docs.static.szse.cn/www/lawrules/rule/stock/W020230217564423808793.pdf)
- [深交所创业板涨跌幅比例问答](https://investor.szse.cn/investor/index/update/t20200729_580056.html)

研究推断：

- Prism 不能用一个固定 10% 或 20% 规则覆盖全历史。
- P1-A execution flags 需要按 `trade_date`、交易所、板块、是否 ST / 风险警示、是否新股前 5 日、是否北交所等维度建立 rule version table。
- 对 2024 research backfill，主板普通股票通常按 10%，科创板/创业板通常按 20%，风险警示股票历史口径需要按当时规则和交易所分别确认。
- 由于 2026-07-06 起上交所主板风险警示规则发生变化，任何 2026 以后回测必须按 effective date 切换规则。

### 4.4 failed order / partial fill

官方事实：

- JoinQuant / RiceQuant 等平台可提供停牌、涨跌停价、tick、bid/ask、volume、money 或 total_turnover 等字段。
- 公共日线 OHLCV 不包含 Prism 策略自身的订单提交、撮合、撤单、成交比例或交易所队列位置。

来源：

- [JoinQuant 股票数据文档](https://www.joinquant.com/help/data/stock?f=home)
- [RiceQuant RQData generic API](https://www.ricequant.com/doc/rqdata/python/generic-api)
- [上交所行情技术文档示例](https://www.sse.com.cn/services/tradingtech/development/c/10816478/files/51a3e4c6b92345689c682448582c019d.pdf)

研究推断：

- failed order 的真实数据只有 Prism 自己的 broker / OMS / simulation order ledger 才能证明。
- P1-A 可以做 conservative derived order outcome：
  - entry day suspended -> blocked；
  - buy at next open and open_at_limit_up -> blocked；
  - sell at next open and open_at_limit_down -> blocked or delayed；
  - price missing -> unavailable；
  - execution data missing -> research-only。
- partial fill 不能从日线精确得到。第一版只能用 volume/amount participation cap 估算，并标记 `partial_fill_estimated` 或 `partial_fill_unavailable`。
- 若要更真实，需要 tick / L2 / 五档盘口 / 委托簿 / 自有订单日志，通常属于付费授权或券商交易系统数据。

## 5. 交易日历和费用规则

### 5.1 A 股交易日历

官方事实：

- 上交所公开发布 2026 年部分节假日休市安排。
- 深交所公开发布节假日休市安排通知，具体年度完整安排需以深交所和证监会通知为准。
- 中国结算休市期间清算交收安排需与交易所休市安排配套。

来源：

- [上交所休市安排列表](https://www.sse.com.cn/disclosure/dealinstruc/closed/list/)
- [上交所 2026 年部分节假日休市安排通知](https://www.sse.com.cn/disclosure/announcement/general/c/c_20251222_10802507.shtml)
- [深交所 2026 年春节休市安排通知](https://www.szse.cn/disclosure/notice/t20260206_618970.html)
- [中国结算服务支持与收费标准入口](https://www.chinaclear.cn/zdjs/fwzc/service.shtml)

研究推断：

- P1-A 最好冻结一份本地 trading calendar manifest，来源优先级为交易所官方公告，其次为 Tushare/RiceQuant/BigQuant 等数据源。
- 若使用数据商交易日历，仍需要保存 source、hash、生成时间和适用市场。

### 5.2 T+1

官方事实：

- A 股股票交易一般实行 T+1 卖出约束。交易所交易规则中涉及证券交易、回转交易、申报和成交等制度安排。

来源：

- [上海证券交易所交易规则（2026 年修订）](https://www.sse.com.cn/lawandrules/sselawsrules2025/trade/universal/c/c_20260424_10816492.shtml)
- [深圳证券交易所交易规则（2023 年修订）PDF](https://docs.static.szse.cn/www/lawrules/rule/stock/W020230217564423808793.pdf)

研究推断：

- Prism P1-A label/backtest 应继续默认：信号日之后最早 next trading day entry；买入后最早下一交易日 exit。
- 对当日买入当日卖出的任何模拟结果，必须标记违反 A 股 T+1 或排除。

### 5.3 印花税

官方事实：

- 财政部、税务总局公告 2023 年第 39 号规定，自 2023-08-28 起，证券交易印花税实施减半征收。
- 中国结算上海市场收费表显示证券交易印花税按成交金额 1‰ 向出让方收取，减半征收。

来源：

- [财政部、税务总局关于减半征收证券交易印花税的公告](https://m.mof.gov.cn/zcfb/202308/t20230827_3904226.htm)
- [中国结算上海市场收费及代收税费一览表](https://www.chinaclear.cn/zdjs/fbzyls/202506/9d22b74d9f2e40edb67b44d1f6596f18/files/%E4%B8%8A%E6%B5%B7%E5%B8%82%E5%9C%BA%E8%AF%81%E5%88%B8%E7%99%BB%E8%AE%B0%E7%BB%93%E7%AE%97%E4%B8%9A%E5%8A%A1%E6%94%B6%E8%B4%B9%E5%8F%8A%E4%BB%A3%E6%94%B6%E7%A8%8E%E8%B4%B9%E4%B8%80%E8%A7%88%E8%A1%A8.pdf)

研究推断：

- 对 2024 及之后 A 股股票卖出，P1-A 可保守配置卖出印花税 0.5‰，即 5 bps。
- 历史跨越 2023-08-28 前后的样本必须按 effective date 切换。

### 5.4 佣金、过户费、监管费、经手费

官方事实：

- 中国结算发布上海、深圳、北京市场收费及代收税费一览表，包含证券业务监管费、印花税、交易经手费、过户相关费用等。
- 上海市场收费表显示证券业务监管费和交易经手费等可按成交金额双向收取。

来源：

- [中国结算服务支持与收费标准入口](https://www.chinaclear.cn/zdjs/fwzc/service.shtml)
- [中国结算上海市场收费及代收税费一览表](https://www.chinaclear.cn/zdjs/fbzyls/202506/9d22b74d9f2e40edb67b44d1f6596f18/files/%E4%B8%8A%E6%B5%B7%E5%B8%82%E5%9C%BA%E8%AF%81%E5%88%B8%E7%99%BB%E8%AE%B0%E7%BB%93%E7%AE%97%E4%B8%9A%E5%8A%A1%E6%94%B6%E8%B4%B9%E5%8F%8A%E4%BB%A3%E6%94%B6%E7%A8%8E%E8%B4%B9%E4%B8%80%E8%A7%88%E8%A1%A8.pdf)
- [中国结算深圳市场收费及代收税费一览表](https://www.chinaclear.cn/zdjs/fbzyls/202506/ab6384ba25514554a7eceaee3e521032/files/%E6%B7%B1%E5%9C%B3%E5%B8%82%E5%9C%BA%E8%AF%81%E5%88%B8%E7%99%BB%E8%AE%B0%E7%BB%93%E7%AE%97%E4%B8%9A%E5%8A%A1%E6%94%B6%E8%B4%B9%E5%8F%8A%E4%BB%A3%E6%94%B6%E7%A8%8E%E8%B4%B9%E4%B8%80%E8%A7%88%E8%A1%A8.pdf)

研究推断：

- 佣金是券商协议费率，不应写死。P1-A 可保守用 2.5 bps/side 或更高，并配置最低佣金。
- 过户费、经手费、监管费应从中国结算和交易所收费表建立 effective-date fee table。
- 如果 P1-A 暂不拆细全部费用，至少应保留：
  - buy commission bps；
  - sell commission bps；
  - sell stamp tax bps；
  - transfer / handling / regulatory bps placeholder；
  - minimum commission；
  - source and effective date。

### 5.5 滑点和冲击成本

官方事实：

- 官方收费规则不覆盖滑点和冲击成本；这些属于交易执行模型。

研究推断：

- P1-A conservative simulation 可采用：
  - next open/close label 额外扣 5-20 bps slippage；
  - 对涨停买入、跌停卖出设置 blocked；
  - participation cap 初始设 5% 或更保守；
  - 目标成交额超过成交额 cap 时标记 partial fill；
  - 无 volume/amount 时标记 `partial_fill_unavailable`。
- 不能用固定滑点模型宣称 execution-realistic，只能称 conservative research simulation。

## 6. 数据源对比矩阵

| 数据源 | 数据完整性 | PIT 可证明性 | 稳定性 | 免费/付费 | API 限制 | 自动化 | 适合 P1-A | 风险 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 中证指数官方 | Benchmark 定义最权威；历史 OHLC 需确认数据服务 | 强，如果取得官方授权和数据包 revision | 高 | 多数数据服务需授权 | 需协议 | 中 | 适合作 benchmark 权威源 | 成本、授权、自动化接口和再分发限制 |
| 交易所官方规则/休市 | 规则和日历权威 | 强 | 高 | 免费公开 | 文档型，不是行情 API | 中 | 必须用于 rule table | 需要人工维护 effective date |
| 中国结算收费表 | 费用权威 | 强 | 高 | 免费公开 | 文档型 | 中 | 必须用于 fee table | 费用项目复杂，需人工确认口径 |
| Tushare Pro | Benchmark、日线、复权、涨跌停、日历覆盖较全 | 中；需本地快照增强 | 中高 | token/积分 | 积分、频率、授权 | 高 | 最适合 P1-A MVP 候选 | 授权、调用限制、PIT 和再分发 |
| AKShare | 指数和行情覆盖广 | 弱到中；需本地快照 | 中 | 免费开源 | 底层接口可能变 | 高 | 适合 audit/cross-check，不宜单独 formal | 底层接口和授权不稳定 |
| BaoStock | 日线、复权、交易日历、部分状态字段 | 弱到中；需本地快照 | 中 | 免费 | 无 token 但需确认可用性 | 高 | 适合 fallback/cross-check | 维护活跃度、授权和字段口径 |
| JoinQuant | 价格、复权、paused、limit、ST 字段较好 | 中高；平台内较强，本地需归档 | 高 | 账号/付费或平台限制 | 平台限制 | 中高 | 适合 P1-B 或验证源 | 授权和平台绑定 |
| RiceQuant | 日线/tick/limit 字段强 | 中高；本地需归档 | 高 | 付费/授权 | 账号限制 | 高 | 适合 P1-B execution hardening | 成本和授权 |
| Wind | 机构级完整性强 | 高，取决于授权数据包 | 高 | 付费 | 终端/API 授权 | 高 | 适合机构路线 | 成本高，不适合开源再分发 |
| Choice / EMQuant / iFinD | 机构级完整性强 | 中高 | 高 | 付费 | 客户端/API 授权 | 高 | 适合机构路线或交叉校验 | 成本、授权、字段映射 |
| 自有券商/OMS 日志 | failed order / partial fill 最真实 | 强 | 取决于系统 | 自有/券商 | 账户和合规限制 | 中 | 适合未来 execution-realistic | 隐私、合规、不能公开 |

## 7. 推荐方案

### 7.1 P1-A 最小可行方案

研究推断：

P1-A 最小可行方案建议采用 **Tushare Pro 授权路线优先，AKShare/BaoStock 做只读交叉校验，官方规则文件做 rule/fee source of truth**。

建议范围：

1. Benchmark：
   - Primary: `CSI500` from Tushare `index_daily` 或已授权等价源。
   - Secondary: `HS300` from 同源。
   - Internal: 继续保留 `eligible_universe_equal_weight`，但永远标记 internal / research-only。

2. Adjusted price：
   - Target policy: qfq / 前复权。
   - 必须保存 raw OHLC、adj_factor、adjustment policy、source hash、generated_at、source timestamp。
   - 若无法取得 adj_factor，只能标记 `adjusted_price_unavailable`。

3. Execution flags：
   - 停牌：优先使用 source-provided suspended/tradestatus。
   - 涨跌停：优先使用 source-provided limit_up/limit_down 或 stk_limit。
   - ST / board rule：用交易所规则和数据源 `is_st` / security attribute 建 rule table。
   - failed order：先做 conservative derived flags，不宣称真实成交。
   - partial fill：若有 volume/amount，做 participation cap 估计；否则 unavailable。

4. PIT：
   - 第一天就建立 raw response archive。
   - 每次拉取保存 source、query params、generated_at、hash、row count、date range、license note。
   - 历史回填仍可做，但正式 PIT 只能从本地归档日期往后逐步增强。

通过条件：

- 可以生成 coverage audit 和 manifest。
- 缺数据必须 unavailable，不可静默填 0、前值或替代指数。
- 输出仍是 report-only，不进入生产排序或页面。

### 7.2 P1-B 更稳方案

研究推断：

P1-B 更稳方案建议选择 **RiceQuant / JoinQuant / Wind / Choice / iFinD 中一个授权主源 + 一个交叉校验源**。

建议目标：

- 用授权主源覆盖日线、复权因子、停牌、涨跌停、ST、板块、指数、交易日历。
- 若预算允许，增加 tick 或五档盘口，用于 partial fill 和涨跌停开板/封单判断。
- 建立 daily source snapshot job，把所有用于 label/backtest 的原始响应本地归档。
- 对外发布代码时只发布 schema、manifest 和 report，不发布受限原始数据。

适合场景：

- 需要更强自动化稳定性。
- 需要把 `research_only_simulation` 升级为 `available_report_only_execution_hardened`。
- 后续计划做 shadow Prism Edge 或 quant health trend。

### 7.3 不建议采用的方案

不建议：

- 只用网页抓取拼 OHLC。
- 用当前 raw OHLCV 自行倒推 qfq/hfq。
- 用 OHLC 是否等于涨停价来直接判定可买可卖，不标记 ambiguous。
- 用成交量比例估算 partial fill 后宣称真实成交。
- 无授权地把 Wind/Choice/RiceQuant/JoinQuant 数据提交到开源仓库。
- benchmark 缺失时用 internal equal-weight 顶替 CSI500 / HS300。
- 用现在回填的 qfq 序列直接覆盖历史 labels，不保存 factor revision。

## 8. 需要人工拍板的问题

必须人工拍板：

1. 是否允许使用 Tushare Pro token，以及 token/积分/调用频率由谁维护。
2. 是否允许引入付费数据源：RiceQuant、JoinQuant、Wind、Choice、iFinD 任选其一或多个。
3. 是否允许把外部数据落入仓库；若不允许，是否只保存 manifest/hash/report。
4. Prism 是否是内部项目、开源项目，还是可能对外分发；这决定数据再分发授权。
5. Primary benchmark 是否继续定为 `CSI500`，secondary 是否为 `HS300`，internal 是否保留 `eligible_universe_equal_weight`。
6. Formal adjusted return 是否以 qfq 为主，raw 是否只做 audit。
7. 是否要求 `adj_factor` 必须存在；若只有 adjusted OHLC 没有 factor，是否只能 report-only。
8. 是否接受 Tushare/AKShare/BaoStock 的 PIT 弱证明，还是必须等授权源和本地快照积累。
9. ST / 风险警示规则是否按交易所、板块、日期建立 rule version table，并如何处理 2026-07-06 上交所规则切换。
10. partial fill 第一版采用多少 participation cap：1%、3%、5% 或按流动性分层。
11. 成本模型是否拆分佣金、印花税、过户费、经手费、监管费、滑点、冲击成本。
12. 若外部源之间数据冲突，哪个源是 source of truth，哪个源只做 audit。

## 9. P1-A 接入前的验收清单建议

任何外部源进入 P1-A 前，至少需要回答：

| 问题 | 必须答案 |
| --- | --- |
| source 是否有授权 | 是 / 否 / 待拍板 |
| 是否可自动化 | 是 / 否 / 受限 |
| 是否允许本地保存 raw response | 是 / 否 |
| 是否允许提交仓库 | 是 / 否；多数付费源应为否 |
| 是否覆盖 2024 labels 所需日期 | 覆盖率和 missing dates |
| 是否覆盖 2026 forward windows | 覆盖率和成熟度 |
| 是否提供 source timestamp | 字段或本地抓取时间 |
| 是否提供 adj_factor | 是 / 否 |
| 是否提供 suspend/limit/ST | 字段名和覆盖率 |
| 是否可证明 PIT | 原始响应归档 + hash + timestamp |
| 是否可用于 formal labels | 是 / 否；若否则原因 |
| 数据缺失如何降级 | unavailable / research-only / coverage-only |

## 10. 交接结论

Prism P1-A 不缺“能拿到一些数据”的路线，真正缺的是 **授权清楚、字段完整、可自动化、可复现、可证明 PIT、缺失时不静默兜底** 的数据治理方案。

最现实的路径是：

```text
P1-A MVP:
  Tushare Pro 授权主源
  + AKShare/BaoStock 交叉校验
  + 交易所/中证/中国结算官方规则和费用文档
  + Prism 本地 raw response archive
  + 全部 report-only

P1-B 稳定版:
  RiceQuant / JoinQuant / Wind / Choice / iFinD 授权主源
  + tick / limit / paused / ST / adj_factor / calendar 一体化
  + 自有订单日志或 conservative order simulator
  + 仍先 shadow，不进生产排序
```

在人工确认授权和成本前，不应把任何外部源接入 `packages/quant` 或 `data/quant`，也不应重跑并升级 Sprint 2 报告。
