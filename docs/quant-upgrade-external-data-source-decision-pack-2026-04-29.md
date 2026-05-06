# Prism 量化升级外部数据源决策包

Date: 2026-04-29
Role: external data source selection advisor
Scope: decision document only; no code, no data fetch, no dependency installation
Status: decision pack for manual approval

Source document:

- `docs/quant-upgrade-p1a-external-data-source-research-2026-04-29.md`

Related Prism state:

- P1-A remains `report-only` / `research-only`.
- Card 4 hardened labels are accepted, but all hardened labels remain non-formal: `formal_label_ready=false`, `formal_execution_eligible=false`.
- CSI500 / HS300 market benchmark, adjusted price, suspend/limit flags, failed order and partial fill still block formal excess return and execution-realistic backtest.

## Manual Decision Update: 2026-04-29

Decision:

External data POC is allowed, but only as a non-production availability check.

Approved boundary:

- Allow a Tushare Pro non-production POC as the first candidate route.
- Do not connect the POC to the main Prism quant pipeline.
- Do not write POC outputs into `packages/quant`.
- Do not write POC outputs into `data/quant`.
- Do not commit raw vendor data to the repository.
- Only verify field availability, authorization boundaries, source hash / timestamp discipline, and raw response archive design.

Still prohibited:

- No production sorting.
- No A/B/C replacement.
- No page or Prism Edge productization.
- No Expected 5D default display.
- No ML.
- No formal labels, formal excess return, formal adjusted return, or execution-realistic backtest from the POC.
- No token, secret, or paid-account credential in git, logs, reports, or shared artifacts.

## 0. 本文边界

本文只做二次整理和决策建议。

严格边界：

- 不写代码。
- 不抓取或生成任何外部数据。
- 不安装依赖。
- 不修改 `packages/quant`。
- 不修改 `data/quant`。
- 不生成 benchmark、adjusted price、execution flags 或 fee table 数据。
- 不做页面、Prism Edge、ML、生产排序或 A/B/C 替换。

表述约定：

- **调研事实**：来自源调研文档列出的官方/数据源文档，本文保留来源链接。
- **顾问建议**：基于 Prism 当前 P1-A 状态、开源仓库风险和 formal labels 目标给出的决策建议。

## 1. 数据源路线总评

### 1.1 P1-A 最小可行路线

#### 路线 A：Tushare Pro 授权主源 + 官方规则/费用文件 + 本地快照归档

调研事实：

- Tushare Pro 文档显示其采用 token / 积分 / 权限体系，并提供数据接口说明。来源：[Tushare 数据接口与积分说明](https://tushare.pro/document/1?doc_id=108)。
- Tushare `pro_bar` 文档显示支持复权行情，并可通过参数返回复权因子。来源：[Tushare pro_bar 复权行情说明](https://www.tushare.pro/document/1?doc_id=109)。
- Tushare `index_daily` 文档用于指数日线。来源：[Tushare index_daily 指数日线接口](https://tushare.pro/document/2?doc_id=95)。
- 源调研文档认为 Tushare 路线可覆盖 benchmark、日线、复权/复权因子、涨跌停、交易日历等 P1-A 最小可行能力，但 token、积分、授权、调用频率和再分发限制必须人工确认。

顾问建议：

- 这是 P1-A 最小可行路线的首选。
- 它足够用来验证 CSI500 / HS300 benchmark、qfq / adj_factor、交易日历、涨跌停字段和部分停复牌字段的可得性。
- 它不能单独证明真实 failed order / partial fill，也不能把历史回填天然升级成 PIT-ready。
- Prism 若走该路线，第一天就必须建立 raw response archive、source hash、query params、retrieved_at、row count、coverage audit 和 license note。
- AKShare / BaoStock 可作为只读 cross-check，不应作为唯一 formal source。

适配结论：

| 维度 | 结论 |
| --- | --- |
| P1-A 速度 | 最快 |
| 字段完整性 | 中高，但执行真实性不足 |
| 自动化 | 高，受 token / 积分 / 频率限制 |
| PIT 证明 | 中；只有本地快照归档之后才逐步增强 |
| 开源仓库适配 | schema / manifest / report 可进仓库；raw vendor data 默认不进 |
| 推荐程度 | P1-A 主推荐 |

### 1.2 P1-B 稳健路线

#### 路线 B：RiceQuant / JoinQuant / Wind / Choice / iFinD 授权主源 + 官方规则文件 + 交叉校验源

调研事实：

- JoinQuant 文档显示股票数据支持价格、复权、`paused`、`high_limit`、`low_limit`、`is_st` 等相关字段。来源：[JoinQuant 股票数据文档](https://www.joinquant.com/help/data/stock?f=home)。
- RiceQuant RQData 文档显示 `get_price` 等接口可取日线和 tick 级别行情，示例字段包含价格、成交量、成交额、`limit_up`、`limit_down` 等。来源：[RiceQuant RQData generic API](https://www.ricequant.com/doc/rqdata/python/generic-api)。
- Wind、Choice / EMQuant、iFinD 更偏机构授权路线，字段和稳定性通常更强，但成本、终端/API 授权和再分发限制更重。来源：[EMQuant 文档示例](https://emquant.18.cn/help/doc/cpp/book.pdf)、[同花顺量化 API 文档](https://quant.10jqka.com.cn/view/help/4?from=ifind)。

顾问建议：

- 这是 P1-B 稳健路线，而不是当前 P1-A 最快路线。
- 若目标从 `research_only_simulation` 升级到更可信的 execution hardening，应优先考虑 RiceQuant 或 JoinQuant 这类能同时覆盖 daily、复权、limit、paused、ST、tick 或成交约束字段的数据源。
- 若组织已经拥有 Wind / Choice / iFinD 授权，机构源可以替代 Tushare 成为主源，但授权和开源再分发审查必须先完成。
- 即使使用付费源，也必须保留 Prism 本地 raw response archive，否则无法证明某次运行时看到的数据版本。

适配结论：

| 维度 | 结论 |
| --- | --- |
| P1-A 速度 | 中，采购和授权会慢 |
| 字段完整性 | 高，尤其适合 execution flags / tick / limit |
| 自动化 | 中高，受账号、平台、终端或合同限制 |
| PIT 证明 | 中高，但仍依赖本地快照和 vendor revision |
| 开源仓库适配 | raw data 通常不适合进仓库 |
| 推荐程度 | P1-B 主推荐；P1-A 若已有授权可提前采用 |

### 1.3 不建议路线

调研事实：

- AKShare 是开源 Python 数据接口聚合项目，便于自动化，但底层网页/接口可能变化，稳定性和授权边界需自行承担。来源：[AKShare 指数数据文档](https://akshare-hh.readthedocs.io/en/latest/data/index/)、[AKShare 文档入口](https://akshare.akfamily.xyz/)。
- BaoStock 常见接口覆盖历史 K 线、交易日历、复权因子、`tradestatus`、`isST` 等字段，但正式授权、维护活跃度、字段口径和历史修订仍需人工确认。来源：[BaoStock 官方站点](http://baostock.com/)。

顾问建议：

不建议作为 P1-A formal 数据源：

- 只抓网页行情页面，不保存官方或授权接口来源。
- 只用 AKShare / BaoStock 回填历史数据，却不做 source hash、timestamp、revision、授权审查和 PIT 归档。
- 只用当前 raw OHLCV 推断 qfq / adj_factor、停牌、涨跌停、failed order 或 partial fill。
- 把 `eligible_universe_equal_weight` 当成 CSI500 / HS300 market benchmark。
- 用当前前复权序列直接覆盖历史 labels，却不保存复权因子、source timestamp、effective date 和 factor revision。
- 用日线 volume / amount 估算 partial fill 后宣称真实成交。
- 未经授权把 Wind / Choice / RiceQuant / JoinQuant 等数据提交到开源仓库。

## 2. 推荐路线

### 2.1 主推荐方案：Tushare Pro 授权主源 + 官方规则/费用文件 + 本地 raw archive

顾问建议：

把 Tushare Pro 作为 P1-A 外部数据源 POC 和最小可行接入的第一候选；官方中证、交易所、财政部/税务总局、中国结算文件作为 rule / calendar / fee 的 authority；AKShare / BaoStock 只做只读交叉校验。

| 问题 | 答案 |
| --- | --- |
| 能解决哪些当前缺口 | CSI500 / HS300 指数日线可得性验证；qfq / adj_factor 可得性验证；交易日历可得性验证；涨跌停价格字段可得性验证；部分停复牌或交易状态字段可得性验证；source manifest / hash / coverage audit 可从第一天建立 |
| 不能解决哪些缺口 | 不能证明真实 failed order；不能从日线精确证明 partial fill；不能证明盘口队列、封单、撤单、滑点和冲击成本；不能让历史回填天然 PIT-ready；不能替代券商/OMS order ledger |
| 需要什么账号 / token / 授权 / 成本 | Tushare Pro 账号和 token；确认积分、接口权限、调用频率、商业使用、自动化调用和再分发条款；确认 token 由谁维护、谁付费、如何轮换 |
| 是否适合开源仓库 | 适合提交 adapter schema、manifest schema、coverage report 和不含 vendor data 的审计结论；不建议提交 raw response、日线数据、复权因子或 vendor-derived full dataset |
| 是否适合自动化 | 适合；但必须处理 token secret、rate limit、retry、row count audit、response hash 和每日快照 |
| 是否能证明 PIT | 从本地归档开始可以逐步证明 as-collected PIT；历史一次性回填只能标为 `research_only_backfill`，除非 vendor 提供可验证 as-of revision |
| 是否能支持后续 formal labels | 可以支持，但前提是 benchmark、qfq/adj_factor、calendar、execution flags、source hash、timestamp、coverage 和授权均通过；缺任一项仍保持 unavailable / research-only |

建议落地边界：

- POC 和后续接入都不得写入 `packages/quant` 或 `data/quant`，除非人工拍板明确进入开发卡。
- raw vendor response 默认保存在本地私有目录或受控对象存储，不进入开源 repo。
- Prism repo 最多先接收 redacted manifest / coverage report / decision record。

### 2.2 备选方案：RiceQuant RQData 授权主源 + Tushare/JoinQuant 交叉校验 + 官方规则文件

顾问建议：

如果人工已经接受付费授权，或 P1-B 目标明确要求更强 execution hardening，则选 RiceQuant RQData 作为授权主源；Tushare 或 JoinQuant 可作为 cross-check；官方规则和费用文件仍作为 rule / fee source of truth。

| 问题 | 答案 |
| --- | --- |
| 能解决哪些当前缺口 | 指数/个股行情、raw/adjusted price、limit up/down、volume/amount、tick 或更细粒度执行字段的可得性验证；比 Tushare 更适合 partial fill 保守估算和 execution flags hardening |
| 不能解决哪些缺口 | 仍不能提供 Prism 自己的真实 broker / OMS failed order；不能证明队列位置和真实成交比例；除非合同支持，否则不能把 raw data 再分发到开源仓库；历史 PIT 仍需 vendor revision 或本地快照 |
| 需要什么账号 / token / 授权 / 成本 | RiceQuant RQData 账号、授权合同、API 凭证、调用额度和商业用途许可；若用 JoinQuant cross-check，还需 JoinQuant 账号和平台限制确认 |
| 是否适合开源仓库 | 不适合提交原始数据；可提交 schema、adapter contract、redacted manifest、hash、coverage report 和字段映射说明 |
| 是否适合自动化 | 适合机构化自动化，但要确认 API 环境、并发、调用量、终端/平台绑定和合同限制 |
| 是否能证明 PIT | 比免费聚合源更强，但仍需要 Prism 每日归档 raw response、query params、retrieved_at、source revision 和 hash |
| 是否能支持后续 formal labels | 更适合支持 formal labels 和 execution-hardened research；但仍需完成授权、coverage、PIT、字段冲突处理和本地 archive |

备选方案适用条件：

- 预算和授权已经明确。
- P1-B 或后续 shadow research 明确需要 tick / execution 近似能力。
- 团队接受数据不进入开源仓库，只在本地/私有环境生成 redacted manifest 和 report。

## 3. 人工拍板问题

以下问题必须人工决定；不应由实现者或自动化默认选择。

| 类别 | 必须拍板的问题 | 建议默认 |
| --- | --- | --- |
| Tushare | 是否允许使用 Tushare Pro | 允许做 non-production POC；进入 P1-A 数据链前再审批 |
| Token | token 由谁申请、保存、轮换、吊销 | 使用 secret manager / local env；禁止写入 repo、日志和报告 |
| 成本 | 是否接受 token / 积分 / 付费成本 | 先设 POC 调用预算；正式接入前确认月度上限 |
| 授权 | Tushare 数据是否允许本地研究、自动化、商业用途和衍生报告 | 未确认前只做 report-only POC |
| 开源 | 是否允许外部数据只用于本地研究，不进入开源仓库 | 建议允许本地研究；raw data 默认不进 repo |
| 付费源 | 是否需要采购 RiceQuant / JoinQuant / Wind / Choice / iFinD | P1-A 不强制；P1-B execution hardening 建议采购或确认已有授权 |
| Raw archive | 是否允许保存外部 raw response 到本地 | 建议允许，但必须私有、加密/受控、gitignored |
| Manifest | 是否允许将外部数据生成的 manifest/report 进入 Prism repo | 建议允许 redacted manifest/report；不得包含可还原 vendor dataset 的内容 |
| Source of truth | 多源冲突时哪个源是主源，哪个源只做 audit | P1-A 主源 Tushare；AKShare/BaoStock 只 audit；P1-B 主源另行拍板 |
| Benchmark | Primary benchmark 是否为 CSI500，secondary 是否为 HS300 | 维持 CSI500 primary、HS300 secondary、eligible equal-weight internal |
| 复权 | Formal label 主口径是否采用 qfq / 前复权 | 建议采用 qfq；raw 只审计；hfq 不进 PIT formal labels |
| Adj factor | 是否要求 `adj_factor` 必须存在 | 建议必须存在；只有 adjusted OHLC 而无 factor 时保持 report-only |
| PIT 标准 | 是否接受从本地归档日之后逐步证明 PIT | 建议接受；历史回填标 `research_only_backfill` |
| Execution | partial fill 第一版 participation cap 用 1%、3%、5% 还是分层 | POC 只验证字段；参数留给后续 Card 拍板 |
| 费用 | 佣金、印花税、过户费、经手费、监管费是否拆分 | 建议拆分，并带 effective date 和 source |
| 规则版本 | ST / 风险警示 / 科创板 / 创业板 / 新股前 N 日规则是否建 rule version table | 必须建；不得用固定 10% 或 20% 覆盖全历史 |
| Card 5 | 是否先做当前 Card 5 report-only rerun，还是等待外部数据 | 建议先做 Card 5；外部数据 POC 并行但不阻塞 |
| Repo 边界 | 是否允许任何 vendor-derived data 进入 `data/quant` | 默认不允许，除非授权和再分发审查通过 |

## 4. POC 方案

### 4.0 POC 总边界

POC 目标：

- 只验证外部数据源是否可用、字段是否覆盖、授权和 PIT 证据是否可管理。
- 不进入生产。
- 不写 `packages/quant`。
- 不写 `data/quant`。
- 不覆盖任何 Sprint 2 或 P1-A reports。
- 不生成 formal labels、formal excess return 或 execution-realistic backtest。

POC 公共输入：

- 人工批准的数据源账号和 token。
- 人工批准的 symbol / index / date sample。
- 当前 Prism formal label 所需日期范围摘要，但不把 POC 输出写回 label store。
- 一组覆盖主板、创业板、科创板、ST/风险警示、可能停牌、可能涨跌停、不同流动性股票的样本列表；具体样本由人工指定或从现有 labels 只读抽样。

POC 公共输出：

- POC coverage report。
- Redacted source manifest。
- Field mapping matrix。
- Missing / conflict / license risk list。
- 不含 vendor 原始行情数据的决策摘要。

POC 公共保存要求：

- 对每次 source response 保存 `source_name`、`endpoint`、`query_params`、`retrieved_at`、`timezone`、`response_hash`、`row_count`、`field_list`、`license_note`。
- raw response 只保存在本地私有 POC archive 或受控对象存储；默认不提交 Prism repo。
- 如果来源是 PDF / HTML 规则文件，保存原始文件 hash、URL、retrieved_at 和文档标题。

### 4.1 Benchmark POC：CSI500 / HS300 日线

| 项目 | 设计 |
| --- | --- |
| 输入 | 数据源候选；CSI500 / HS300 index code mapping；2024 label 所需 entry/exit windows；少量 2026 matured / pending 对照日期；交易日历候选 |
| 输出 | `benchmark_poc_coverage_report`；字段覆盖矩阵；missing dates；duplicate dates；open/high/low/close/prev_close 可得性；source manifest |
| 成功标准 | CSI500 和 HS300 均能返回所需日期的 open/high/low/close/prev_close；交易日对齐；缺失和重复为 0 或可解释；source hash、retrieved_at、row_count 完整 |
| 失败标准 | index code 不清；字段缺 open 或 prev_close；日期缺口无法解释；返回自然日而非交易日；同一日期重复；source 不允许保存 raw response；授权不能覆盖自动化 |
| 需要保存 | raw response hash；retrieved_at；query params；index code mapping 来源；row_count；missing/duplicate audit；raw response 本地私有归档 |
| 如何保持 report-only | POC 结果只进 POC report，不写 `data/quant/benchmarks`，不计算 label `benchmark_return`，不输出 `excess_return` |

### 4.2 Adjusted Price POC：qfq / adj_factor

| 项目 | 设计 |
| --- | --- |
| 输入 | 现有 labels 中只读抽样的股票代码和 entry/exit dates；qfq / hfq / raw 请求参数；除权除息高风险日期样本；数据源 adjustment policy 文档 |
| 输出 | qfq / raw / adj_factor 字段可得性报告；raw 与 adjusted 差异 audit；factor effective date / source timestamp 可得性说明；字段映射 |
| 成功标准 | 可取得 raw OHLC、qfq OHLC、`adj_factor` 或等价可解释因子；factor 能解释 raw 与 qfq 差异；entry/exit 日期覆盖完整；response hash 和 retrieved_at 完整 |
| 失败标准 | 只有 adjusted price 没有 factor；无法说明 qfq 口径；历史 factor 明显会被当前数据重算但无法归档 revision；entry/exit 任一缺失；source 不允许本地保存 raw response |
| 需要保存 | raw response hash；retrieved_at；query params；adjustment policy URL / 文档 hash；factor field list；row_count；raw response 本地私有归档 |
| 如何保持 report-only | 不写 `data/quant/prices`，不生成 adjusted labels，不把 raw return 改名为 adjusted return；POC 只判断是否具备后续开发条件 |

### 4.3 Execution Flags POC：停牌、涨跌停、ST / 板块限制

| 项目 | 设计 |
| --- | --- |
| 输入 | 抽样股票代码和 trade_date；停复牌字段候选；limit_up / limit_down 字段候选；ST / 风险警示字段；上市板块、上市日期、新股前 N 日规则；volume / amount / tick 可得性 |
| 输出 | suspend / tradestatus / limit / ST / board field mapping；confirmed vs inferred 状态区分；blocked / unavailable / ambiguous 规则草案；字段冲突报告 |
| 成功标准 | 能取得 source-provided suspend/tradestatus 或明确 unavailable；能取得 limit_up/limit_down 价格或等价字段；ST/板块/上市天数规则可追溯；能区分 confirmed 与 inferred；缺口不会被静默当 full fill |
| 失败标准 | 只能从缺少 price row 或 volume=0 推断停牌；limit price 不可得；ST/板块限制无法按日期确认；不同源冲突无 source of truth；tick/volume 不足以支持 partial fill 估算 |
| 需要保存 | raw response hash；retrieved_at；query params；rule document hash；field list；conflict list；raw response 本地私有归档 |
| 如何保持 report-only | 不写 `data/quant/execution`，不生成 research order outcomes，不宣称 execution-realistic；POC 只输出可得性和风险 |

### 4.4 Trading Calendar POC

| 项目 | 设计 |
| --- | --- |
| 输入 | 数据源交易日历接口；上交所/深交所休市公告；2024 label windows；2026 forward windows；市场标识 SH / SZ / BJ 如需覆盖 |
| 输出 | calendar coverage report；vendor calendar 与交易所公告对照；holiday / weekend / special close audit；source manifest |
| 成功标准 | vendor calendar 覆盖所有需要日期；与官方休市公告可对齐；能输出 `is_open`、market、trade_date；source hash 和 retrieved_at 完整 |
| 失败标准 | calendar 与 price dates 大量冲突；无法区分自然日和交易日；无法覆盖 forward windows；官方公告无法归档；source 不允许保存响应 |
| 需要保存 | raw response 或官方公告 PDF/HTML hash；retrieved_at；query params；date range；row_count；conflict report |
| 如何保持 report-only | 不写 `data/quant/calendars`，不改变 label entry/exit date，只输出 POC 对照报告 |

### 4.5 Fee Table POC

| 项目 | 设计 |
| --- | --- |
| 输入 | 财政部/税务总局印花税公告；中国结算上海/深圳/北京市场收费表；交易所收费规则；券商佣金假设或人工提供佣金协议 |
| 输出 | fee table 字段设计：buy commission bps、sell commission bps、minimum commission、sell stamp tax bps、transfer / handling / regulatory bps、effective_date、source；规则缺口表 |
| 成功标准 | 印花税和交易费用能按 effective date 追溯；佣金与官方费用分离；买卖方向明确；最低佣金需要 notional 时标记依赖；每条规则有 source URL/hash/retrieved_at |
| 失败标准 | 费用项目无法拆分；effective date 不清；佣金被误认为官方固定费率；跨日期样本无法切换；PDF/规则文件无法归档 hash |
| 需要保存 | 官方 PDF/HTML hash；retrieved_at；source URL；版本标题；人工佣金假设审批记录；不保存任何交易账户隐私 |
| 如何保持 report-only | 不写配置和 label/backtest 成本字段；只输出 fee table POC design/report，不重跑 portfolio backtest |

## 5. 合规和授权风险

| 风险 | 说明 | 建议控制 |
| --- | --- | --- |
| Token 安全 | Tushare / RiceQuant / JoinQuant / Wind / Choice / iFinD 凭证可能泄露调用权限和账户信息 | 使用 secret manager 或本地 env；禁止提交 repo；禁止写日志；定期轮换；最小权限 |
| 数据再分发 | 付费或授权数据通常限制再分发，开源提交 raw data 可能违约 | raw response 默认不进 repo；只提交 schema、hash、redacted manifest 和报告；必要时法务确认 |
| 开源仓库存放数据 | `data/quant` 一旦进入公开仓库，可能构成外部数据再分发 | 未经授权不得提交 vendor-derived OHLC、adj_factor、limit、tick、calendar full dataset |
| 商业用途限制 | 免费/低价 token 可能只允许个人研究或非商业用途 | 明确 Prism 项目属性：个人、本地研究、内部商业、对外分发分别审批 |
| API 调用限制 | 积分、频率、并发、批量下载、自动化 job 可能受限制 | POC 前设调用预算；实现前做 rate-limit 设计；失败重试不能放大调用 |
| 数据修订 | 数据商可能修订历史 OHLC、复权因子、指数点位或状态字段 | 每次响应保存 hash、retrieved_at、query params、row_count；报告展示 revision diff |
| PIT 风险 | 当前历史接口返回的是“现在看历史”，不等于当时可见数据 | 历史回填标 `research_only_backfill`；从归档日之后逐步积累 PIT；formal labels 需要 as-of 证据 |
| Corporate action 风险 | qfq / adj_factor 会随除权除息和供应商算法调整 | 保存 factor、effective date、vendor policy、factor revision；无 factor 时不进 formal |
| 规则版本风险 | ST、风险警示、新股、科创板/创业板涨跌幅规则随时间变化 | 建 rule version table；每条规则记录 effective date 和 source hash |
| 隐私和交易日志 | 真正 failed order / partial fill 可能涉及券商账户和 OMS 日志 | 不在 POC 收集真实账户隐私；未来另设 broker/OMS 合规方案 |

相关官方来源：

- 沪深 300 与中证 500 指数规则： [沪深 300 指数编制方案](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/000300_Index_Methodology_cn.pdf)、[中证系列规模指数编制方案](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/000904_Index_Methodology_cn.pdf)。
- 交易规则与休市安排： [上交所交易规则 2026 年修订](https://www.sse.com.cn/lawandrules/sselawsrules2025/trade/universal/c/c_20260424_10816492.shtml)、[深交所交易规则 2023 年修订 PDF](https://docs.static.szse.cn/www/lawrules/rule/stock/W020230217564423808793.pdf)、[上交所休市安排列表](https://www.sse.com.cn/disclosure/dealinstruc/closed/list/)。
- 费用与税费： [财政部、税务总局证券交易印花税公告](https://m.mof.gov.cn/zcfb/202308/t20230827_3904226.htm)、[中国结算服务支持与收费标准入口](https://www.chinaclear.cn/zdjs/fwzc/service.shtml)。

## 6. 与当前 P1-A 的关系

### 6.1 可以等 Card 5 后再做

顾问建议：

以下事项可以等 P1-A Card 5 之后再做，不应阻塞当前 report-only 主线：

- Tushare / RiceQuant / JoinQuant / Wind / Choice / iFinD 的实际 POC 调用。
- 外部 source adapter 开发。
- raw response archive 的生产化目录和保留策略。
- vendor 数据进入 `data/quant` 的授权审查。
- 用外部数据重新生成 benchmark、price、execution 和 label artifacts。
- 用外部数据重新跑 Sprint 2 factor/backtest/health。
- partial fill participation cap、tick / L2 / 五档盘口模型。
- broker / OMS order ledger 方案。

### 6.2 必须人工拍板后才能做

以下事项不能由开发卡默认执行：

- 使用任何外部 token。
- 采购或启用任何付费源。
- 保存 raw response 到本地。
- 将任何 vendor-derived data 提交到 repo。
- 将 manifest/report 提交到 repo。
- 指定外部主源和 cross-check 源。
- 指定 PIT 标准和历史回填解释口径。
- 指定 qfq / adj_factor 是否足以支持 formal adjusted return。
- 指定哪些 redacted report 可以对外分发。

### 6.3 不应阻塞当前 hardened labels / report-only 工作

以下当前工作不应等待外部数据：

- Card 5：使用 hardened labels 重跑 Sprint 2 reports，并继续 report-only。
- 在报告中展示 benchmark、adjustment、execution、formal label readiness 的 unavailable / deferred 分布。
- 保留 `formal_market_excess_return=unavailable`。
- 保留 `formal_adjusted_return=unavailable`。
- 保留 `execution_realistic_return=unavailable`。
- 保留 `partial_fill=deferred`。
- 继续禁止生产排序、A/B/C 替换、页面、Prism Edge、Expected 5D 默认展示和 ML。

### 6.4 外部数据接入后是否需要重新跑 Sprint 2 / P1-A reports

顾问建议：

需要，但必须按 revision 顺序重跑，不能直接覆盖解释边界。

外部数据真正接入后，建议顺序是：

1. 生成外部 source manifest、license note、raw response hash 和 coverage audit。
2. 重新生成或新增 benchmark / price / execution manifests。
3. 重新跑 label hardening，产生新的 hardened label revision。
4. 再跑 Card 5 / Sprint 2 reports，仍保持 `production_impact=none`。
5. 输出 diff：与当前 Card 4 hardened labels 和现有 Sprint 2 reports 比较 availability、row count、drop reason、formal readiness 变化。

在以下条件未满足前，不得把 rerun 解释为 formal 或 execution-realistic：

- CSI500 primary benchmark coverage 通过。
- qfq / adj_factor / adjustment policy 通过。
- suspend / limit / ST / board rule 通过。
- failed / blocked order reason 和 partial fill 降级策略通过。
- PIT、source hash、timestamp 和 license 审查通过。

## 7. 最终建议

### 7.1 现在是否应该马上接外部数据

顾问建议：

不应该马上把外部数据接入正式 P1-A 数据链，也不应该写入 `packages/quant` 或 `data/quant`。

应该做两件并行但互不阻塞的事：

- 主线继续做 Card 5：用 hardened labels 重跑 Sprint 2 reports，保持 report-only。
- 人工拍板后启动 non-production 外部数据 POC，只验证可用性、授权、字段、PIT 和 archive 纪律。

### 7.2 如果接，先接哪个数据源

顾问建议：

- P1-A MVP：先接 Tushare Pro 做 non-production POC。
- P1-B execution hardening：若预算和授权通过，优先评估 RiceQuant RQData；JoinQuant / Wind / Choice / iFinD 作为授权条件下的替代或交叉校验源。

选择 Tushare 的原因：

- 覆盖 P1-A 当前最急的 benchmark、qfq / adj_factor、calendar、limit 字段验证。
- 自动化成本和接入摩擦低于机构源。
- 即使 POC 失败，也能较快明确缺口并回到 report-only。

选择 RiceQuant 的条件：

- 目标明确升级 execution hardening。
- 可以承担付费和授权审查。
- 接受 raw data 不进入开源仓库。

### 7.3 如果不接，当前 Prism 应如何继续保持 research-only

顾问建议：

- 继续使用 Card 4 hardened labels 作为 report-only 契约。
- CSI500 / HS300 继续显式 unavailable。
- formal excess return 继续 unavailable。
- formal adjusted return 继续 unavailable。
- execution-realistic return 继续 unavailable。
- partial fill 继续 deferred。
- internal equal-weight benchmark 只能作为 `research_only_internal_benchmark`。
- Sprint 2 reports 可以用 hardened labels 重跑，但必须把以上缺口展示出来，而不是隐藏。

### 7.4 下一张最合理的任务卡

主线下一张最合理任务卡：

```text
P1-A Card 5: Rerun Sprint 2 reports using hardened labels
```

验收边界：

- 只重跑 factor / backtest / health reports。
- 使用 hardened labels 展示 unavailable / deferred / research-only reasons。
- 不生成 formal excess return。
- 不生成 formal adjusted return。
- 不生成 execution-realistic return。
- 不接生产排序、A/B/C、页面、Prism Edge、Expected 5D 或 ML。

并行但需人工批准的下一张外部数据任务：

```text
External Data Source POC: Tushare Pro non-production availability check
```

验收边界：

- 只做字段可得性、授权、hash、timestamp、raw response archive 方案验证。
- 不写 `packages/quant`。
- 不写 `data/quant`。
- 不改 labels。
- 不重跑 Sprint 2。
- 不把 POC 数据提交到开源仓库。

最终结论：

Prism 现在真正需要的不是“马上拿到一批外部数据”，而是先把外部数据的授权、PIT、归档、开源边界和字段覆盖拍板清楚。P1-A 主线应继续 report-only，先完成 Card 5；外部数据可以从 Tushare Pro POC 开始，但只有在人工批准 token、成本、raw archive、manifest 入库和授权边界后，才能进入后续开发卡。
