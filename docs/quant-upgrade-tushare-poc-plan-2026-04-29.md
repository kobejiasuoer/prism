# Prism 量化升级 Tushare Pro 非生产 POC 准入方案

Date: 2026-04-29
Role: external data source admission planner
Scope: Tushare Pro non-production POC admission only
Status: plan only; no execution

References:

- `docs/quant-upgrade-external-data-source-decision-pack-2026-04-29.md`
- `docs/quant-upgrade-p1a-external-data-source-research-2026-04-29.md`

External documentation referenced by the research pack:

- [Tushare 数据接口与积分说明](https://tushare.pro/document/1?doc_id=108)
- [Tushare pro_bar 复权行情说明](https://www.tushare.pro/document/1?doc_id=109)
- [Tushare index_daily 指数日线接口](https://tushare.pro/document/2?doc_id=95)

## 0. 本文边界

本文只准备 Tushare Pro 非生产 POC 的准入方案，不执行 POC。

严格禁止：

- 不写代码。
- 不调用 Tushare API。
- 不安装依赖。
- 不要求用户提供 token。
- 不提交 token。
- 不修改 `packages/quant`。
- 不写 `data/quant`。
- 不提交 raw vendor 数据。
- 不生成 benchmark 数据。
- 不生成 adjusted price、adj_factor、trading calendar、limit 或 suspend 数据。
- 不做页面、Prism Edge、ML、生产排序或 A/B/C 替换。
- 不生成 formal labels、formal excess return、formal adjusted return 或 execution-realistic backtest。

本文中的接口名和字段均为 POC 准备阶段的验证清单，实际可用性、字段名、权限和费用必须由未来执行 POC 时的 Tushare 账号权限和当时官方文档确认。

## 1. POC 目标

本 POC 只验证 Tushare Pro 是否具备进入 Prism P1-A 外部数据源正式 adapter 设计的基本条件。

目标只限三类：

| 目标 | 准入问题 |
| --- | --- |
| 字段可得性 | Tushare 是否能覆盖 CSI500 / HS300 指数日线、复权行情 / 复权因子、交易日历、涨跌停、停复牌或交易状态、基础股票列表 |
| 授权边界 | 当前账号权限、积分/付费要求、调用频率、自动化、raw response 私有保存、redacted 摘要入库是否被允许 |
| 证据纪律 | 是否能为每次请求记录 hash、request timestamp、response timestamp、provider、endpoint、params fingerprint、row_count 和字段清单 |

POC 不试图回答：

- Tushare 数据是否已经适合 formal labels。
- Tushare 历史回填是否具备完整 PIT 证明。
- Prism 策略是否有效。
- Prism 是否可以进入 production / Prism Edge / 页面展示。

## 2. POC 不做什么

POC 是非生产可用性检查，不接主线代码。

| 不做事项 | 边界 |
| --- | --- |
| 不接主线代码 | 不新增或修改 `packages/quant`，不写 production adapter |
| 不写数据目录 | 不写 `data/quant`，不产生可被主链路消费的数据 |
| 不生成 formal labels | 不修改原始 labels，不修改 hardened labels，不生成 label revision |
| 不生成 formal excess return | 即使 index daily 可得，也不计算 benchmark_return / excess_return |
| 不生成 formal adjusted return | 即使 qfq / adj_factor 可得，也不覆盖 raw return 或 label return |
| 不做 execution-realistic backtest | 即使 limit / suspend 字段可得，也不生成 failed order、partial fill 或 order outcome |
| 不影响生产排序 | 不改生产排序、A/B/C、页面、Prism Edge、Expected 5D、ML |
| 不提交 raw vendor 数据 | raw response、行级行情、行级复权因子、行级涨跌停和日历数据不得进 repo |

POC 完成后最多允许产生不含 raw data 的 redacted 摘要报告和 redacted manifest，用于人工决定是否进入正式 adapter。

## 3. 账号 / Token 要求

### 3.1 账号要求

未来执行 POC 时，Tushare Pro 账号必须由用户或项目负责人自行开通和管理。本方案不要求用户在当前对话、文档、issue、commit、日志或任何仓库文件中提供 token。

必须人工确认：

| 项目 | 要求 |
| --- | --- |
| 账号归属 | 明确账号归属人或项目角色 |
| 使用目的 | 仅用于 Prism 本地非生产研究 POC |
| 数据用途 | 明确是否允许本地研究、自动化调用、私有 raw response 保存和 redacted report 入库 |
| 权限范围 | 只需要读取本方案列出的 POC 接口，不需要写权限 |
| POC 后处理 | 决定 token 是否保留、轮换、吊销或改用正式服务账号 |

### 3.2 Token 存放要求

Use a local environment variable named `TUSHARE_TOKEN`; never print, log, document, or commit its value.

禁止：

- 写入代码。
- 写入文档。
- 写入 `.env` 并提交 git。
- 写入 shell history、日志、测试输出、报告、截图。
- 通过聊天、issue、PR、commit message 或共享文档传递。
- 放入 `packages/quant`、`data/quant` 或任何 repo 内文件。

POC 报告中只能写：

- token 是否存在：`configured_locally=true/false`。
- token 权限是否足够：`permission_ok/permission_denied/unknown`。
- token owner role：如 `local_research_operator`。

不得写 token 值、账号密码、积分余额截图或付费账户敏感信息。

## 4. 权限 / 费用检查

POC 执行前，需要人工逐项确认接口权限、积分/付费要求和调用频率限制。

| 能力 | 候选接口 / 能力 | 权限检查 | 费用 / 积分检查 | 调用频率检查 |
| --- | --- | --- | --- | --- |
| 指数日线 | `index_daily` | 是否可查 HS300、CSI500；是否可指定日期范围和字段 | 是否需要积分门槛；单次或批量调用成本 | 每分钟/每日调用限制；批量日期上限 |
| 复权行情 | `pro_bar` with qfq 或等价能力 | 是否可查 raw、qfq；是否可按股票和日期窗口查询 | qfq / pro_bar 是否有积分或会员门槛 | 单 code / 多 code 调用限制 |
| 复权因子 | `adj_factor` 或 `pro_bar` 返回因子 | 是否能返回 `adj_factor` 或等价可解释因子 | 是否单独计费或需要权限 | 按 code/date 拉取频率限制 |
| 交易日历 | `trade_cal` 或等价接口 | 是否可查 A 股交易日、休市日、pretrade date | 是否免费或低积分 | 大区间调用限制 |
| 涨跌停 | `stk_limit` 或等价接口 | 是否返回 up_limit / down_limit；是否覆盖 ST、创业板、科创板等 | 是否需要积分或高级权限 | 按日期批量调用限制 |
| 停复牌 | `suspend_d`、停复牌或交易状态接口 | 是否有历史停复牌区间、日级状态或 tradestatus | 是否需要积分或高级权限 | 按 code/date 调用限制 |
| 基础股票列表 | `stock_basic` 或等价接口 | 是否返回股票代码、名称、市场、交易所、上市状态、上市日期 | 是否需要积分或权限 | 全量列表调用频率 |

准入要求：

- 每个候选接口都必须记录 `permission_status`：`allowed`、`permission_denied`、`not_in_account`、`unknown`。
- 每个候选接口都必须记录 `cost_status`：`free_for_account`、`points_required`、`paid_required`、`unknown`。
- 每个候选接口都必须记录 `rate_limit_status`：`known_ok`、`known_restricted`、`unknown`。
- 任一关键接口为 `unknown` 时，不得进入正式 adapter，只能继续做权限澄清。

## 5. 字段验证清单

字段验证只记录字段是否可得、缺失率和 row_count 汇总，不保存行级 vendor 数据到 repo。

### 5.1 指数日线

目的：验证 CSI500 / HS300 benchmark 的最小字段可得性。

候选接口：`index_daily`。

| Prism 需要 | 预期字段 / 概念 | 准入判定 |
| --- | --- | --- |
| 指数代码 | `ts_code` | 必须能区分 HS300 / CSI500；code mapping 需人工确认 |
| 交易日 | `trade_date` | 必须可与交易日历对齐 |
| 开盘 | `open` | 必须 |
| 最高 | `high` | 必须 |
| 最低 | `low` | 必须 |
| 收盘 | `close` | 必须 |
| 前收 | `pre_close` | 必须 |
| 成交量 / 成交额 | `vol` / `amount` 或等价字段 | 可选，作为 sanity audit |

POC 不计算 benchmark return 或 excess return。

### 5.2 复权因子 / 复权行情

目的：验证 qfq / adj_factor 是否能支持后续 adjusted price adapter 设计。

候选接口：`pro_bar` qfq、raw daily、`adj_factor` 或账号可见等价接口。

| Prism 需要 | 预期字段 / 概念 | 准入判定 |
| --- | --- | --- |
| 股票代码 | `ts_code` | 必须 |
| 交易日 | `trade_date` | 必须 |
| raw OHLC | raw open/high/low/close | 必须验证，不得假设 |
| qfq OHLC | qfq open/high/low/close | 必须验证 |
| 前收 | `pre_close` 或等价字段 | 必须 |
| 成交量 / 成交额 | `vol` / `amount` 或等价字段 | 强烈建议 |
| 复权因子 | `adj_factor` 或等价可解释因子 | formal adjusted return 前置条件 |
| 复权参数 | qfq/raw request params | 必须记录在 redacted params 中 |

若只有 qfq price，没有 `adj_factor` 或等价可解释因子，POC 可判定为 `price_adjustment_partial`，但不得建议进入 formal adjusted return。

### 5.3 停复牌

目的：验证是否能 source-provided 判断停牌，而不是从缺价或 volume=0 推断。

候选接口：`suspend_d`、停复牌接口、日级交易状态接口或账号可见等价接口。

| Prism 需要 | 预期字段 / 概念 | 准入判定 |
| --- | --- | --- |
| 股票代码 | `ts_code` | 必须 |
| 停牌日期 | `suspend_date` 或等价字段 | 需要验证 |
| 复牌日期 | `resume_date` 或等价字段 | 需要验证 |
| 停牌原因 | reason / reason_type | 可选 |
| 公告日期 | `ann_date` 或等价字段 | 可选，但有助 PIT 解释 |
| 日级交易状态 | tradestatus / is_suspended | 若可得则优先 |

若只返回事件区间，不返回日级状态，POC report 必须标记 `suspend_event_only`，后续 adapter 需另行设计区间展开和 calendar 对齐。

### 5.4 涨跌停

目的：验证是否能获取 source-provided limit price。

候选接口：`stk_limit` 或等价涨跌停价格接口。

| Prism 需要 | 预期字段 / 概念 | 准入判定 |
| --- | --- | --- |
| 股票代码 | `ts_code` | 必须 |
| 交易日 | `trade_date` | 必须 |
| 涨停价 | up_limit / limit_up 或等价字段 | 必须 |
| 跌停价 | down_limit / limit_down 或等价字段 | 必须 |
| 规则口径 | ST / 板块 / 新股限制，如接口提供 | 可选；缺失时需规则表补充 |

POC 不判断是否真实可成交，不生成 entry blocked / exit blocked 结果。

### 5.5 交易日历

目的：验证 Tushare calendar 是否能作为后续 frozen calendar 的候选输入或 cross-check。

候选接口：`trade_cal` 或等价交易日历接口。

| Prism 需要 | 预期字段 / 概念 | 准入判定 |
| --- | --- | --- |
| 市场 / 交易所 | exchange 或等价字段 | 建议有 |
| 日历日期 | `cal_date` | 必须 |
| 是否交易日 | `is_open` | 必须 |
| 上一交易日 | `pretrade_date` 或等价字段 | 强烈建议 |
| 日期范围 | start/end params | 必须可控 |

交易日历仍需与交易所官方休市公告交叉审计；POC 不把 Tushare calendar 直接升为官方规则来源。

### 5.6 基础股票列表

目的：验证股票 universe、交易所、上市状态、上市日期和板块/市场属性的基础字段来源。

候选接口：`stock_basic` 或等价基础证券信息接口。

| Prism 需要 | 预期字段 / 概念 | 准入判定 |
| --- | --- | --- |
| 股票代码 | `ts_code` | 必须 |
| 股票名称 | `name` | 建议 |
| 交易所 | exchange / market | 必须 |
| 上市状态 | list_status 或等价字段 | 必须 |
| 上市日期 | list_date | 必须，用于新股规则判断 |
| 退市日期 | delist_date 或等价字段 | 如可得则记录 |
| 市场 / 板块 | market / board / area / industry 等 | 可选；缺失时需其他 source |

基础股票列表不得被直接写入 `data/quant`；POC 只记录字段可得性和 row_count 汇总。

## 6. 原始响应归档方案

### 6.1 私有归档位置

raw response 必须保存在 repo 外的本地私有目录或受控对象存储。

准入要求：

| 项目 | 要求 |
| --- | --- |
| 目录位置 | 不在 Prism git 工作树内；不得位于 `packages/quant` 或 `data/quant` |
| 权限 | 仅 POC 执行者和审批人可读 |
| Git ignore | 如果因环境限制必须放在工作树附近，必须先确认 `.gitignore` 或全局 gitignore，且不得提交 |
| 加密 | 建议使用本地磁盘加密或受控对象存储 |
| 保留期限 | POC 前人工指定，例如 30/90/180 天 |
| 删除机制 | POC 结束后按授权要求删除、保留或迁移 |

### 6.2 每次请求必须保存的私有内容

私有归档中保存：

| 内容 | 说明 |
| --- | --- |
| raw response | Tushare 原始响应完整 payload |
| private request manifest | endpoint、params、timestamp、hash、row_count、field list、错误信息 |
| permission note | 若接口被拒绝，记录拒绝类别和账号权限提示，不记录 token |

私有归档中也不得保存 token 明文。

### 6.3 Redacted metadata 记录方案

允许进入 repo 的 redacted manifest 只记录摘要。

每个 request 必须记录：

| 字段 | 说明 | 是否可入库 |
| --- | --- | --- |
| `provider` | 固定为 `Tushare Pro` | 是 |
| `endpoint` | 接口名，如 `index_daily`、`pro_bar`、`trade_cal` | 是 |
| `request_timestamp` | 本地发起请求时间，建议 ISO 8601 + timezone | 是 |
| `response_timestamp` | 本地收到响应时间；如 provider 返回服务端时间，另记 `provider_response_timestamp` | 是 |
| `params_fingerprint` | 删除 token 后，对 params 的稳定表示取 SHA256 | 是 |
| `params_redacted` | 只写 date range、symbol_count、field list，不写 token 或完整敏感列表 | 是 |
| `response_hash_sha256` | 对 raw response bytes 或固定 canonical payload 取 SHA256 | 是 |
| `row_count` | 返回行数 | 是 |
| `returned_fields` | 返回字段名列表 | 是 |
| `permission_status` | allowed / denied / unknown | 是 |
| `cost_status` | free_for_account / points_required / paid_required / unknown | 是 |
| `rate_limit_status` | known_ok / known_restricted / unknown | 是 |
| `raw_archive_ref` | 脱敏引用；不得暴露本机用户名、bucket 机密或可访问路径 | 可选 |

Hash 规则必须在 POC 前固定：

- `response_hash_sha256` 使用 SHA256。
- hash 对象二选一：exact raw response bytes，或 canonical raw payload。
- 一次 POC run 内必须统一，不得混用。
- hash 只能证明归档一致性，不能替代授权，也不能证明历史 PIT。

### 6.4 入库摘要报告内容

允许入库的报告只能写：

- 接口是否可访问。
- 返回字段是否包含预期字段。
- row_count 汇总。
- missing / duplicate / null count 汇总。
- response hash。
- request / response timestamp。
- params fingerprint。
- 授权、费用、频率、归档风险结论。

禁止写：

- 行级 OHLC。
- 行级 adj_factor。
- 行级 up_limit / down_limit。
- 行级停复牌状态。
- 完整交易日历。
- 完整基础股票列表。
- raw response 片段。
- token、账号、积分余额、会员截图。

## 7. 成功标准

POC 准入成功不是指数据已经可用于正式研究，而是指可以安全执行非生产 POC，并在执行后判断是否进入 adapter。

### 7.1 准入成功标准

执行 POC 前需满足：

| Gate | 成功标准 |
| --- | --- |
| Token gate | token 由用户自行开通账号并在本地环境变量如 `TUSHARE_TOKEN` 配置；本轮不收集 token |
| Authorization gate | 自动化调用、私有 raw archive、redacted report 入库边界已人工确认 |
| Permission gate | 所需接口权限、积分/付费要求、调用频率限制已有检查计划 |
| Archive gate | 私有归档目录、gitignore、访问权限、保留期限已确定 |
| Metadata gate | hash、request timestamp、response timestamp、provider、endpoint、params fingerprint、row_count 记录格式已确定 |
| Repo safety gate | 明确不写 `packages/quant`、不写 `data/quant`、不提交 raw vendor 数据 |

### 7.2 POC 执行后的成功标准

若未来执行 POC，成功结果应满足：

| 能力 | 成功标准 |
| --- | --- |
| 字段可得性 | 能确认每类接口字段 present / missing / permission denied / unknown |
| 授权边界 | 能确认本地研究、自动化、raw archive、redacted report 是否允许 |
| 摘要报告 | 能形成不泄露 raw data 的 redacted POC report |
| Manifest | 能形成只含 hash、timestamp、params fingerprint、row_count、field list 的 redacted manifest |
| 安全性 | repo 内没有 token、raw response、行级 vendor data 或可逆数据片段 |

## 8. 失败标准

任一情况出现，POC 不应进入正式 adapter。

| 失败项 | 处理 |
| --- | --- |
| 权限不足 | 关键接口无权限，且无法升级权限或采购 |
| 字段缺失 | index daily、qfq/adj_factor、trade calendar、limit、suspend 或 stock_basic 的关键字段缺失且无替代来源 |
| 授权不清 | 自动化、raw archive、redacted report、商业/内部用途边界不清 |
| 成本不可接受 | 积分、付费、调用量或频率成本超出 POC / 后续预算 |
| 无法安全归档 | raw response 不允许本地保存，或无法保证 repo 外私有归档 |
| Token 泄露风险 | token 可能进入代码、日志、文档、git 或共享渠道 |
| Repo 安全失败 | raw vendor data、行级行情、行级 adj_factor、行级 limit 或完整 calendar 进入 repo |
| Metadata 不完整 | 无法记录 hash、timestamp、params fingerprint、row_count |

能力级失败解释：

- `index_daily` 失败：不得进入 benchmark adapter。
- qfq 可得但 `adj_factor` 缺失：不得进入 formal adjusted return，仅可记录为 partial。
- `trade_cal` 失败：不得使用 Tushare calendar 作为 frozen calendar 候选。
- `stk_limit` 失败：不得进入 limit execution flags adapter。
- 停复牌 / tradestatus 失败：不得声称 execution-realistic；保留 suspend unavailable。
- `stock_basic` 失败：不得用 Tushare 做 universe / board / listing status source。

## 9. POC 完成后的决策树

POC 完成后只允许三类决策：继续接入、换数据源、保持 internal benchmark research-only。

```text
Tushare POC 是否通过授权和 repo safety？
  否 ->
    换数据源，或保持 internal benchmark research-only。
  是 ->
    字段覆盖是否满足至少一个 P1-A 缺口？
      否 ->
        换数据源，或保持 internal benchmark research-only。
      是 ->
        hash/timestamp/raw archive 纪律是否完整？
          否 ->
            不进入 adapter；修 archive/metadata 方案后再评审。
          是 ->
            是否允许 redacted manifest/report 入库？
              否 ->
                不进入开源 repo 流程；只保留本地研究。
              是 ->
                进入正式 adapter 设计评审，但仍保持 report-only。
```

### 9.1 继续接入

进入正式 adapter 设计评审的条件：

- 授权允许本地研究、自动化、私有 raw archive 和 redacted report。
- token 可安全通过本地环境变量或 secret manager 注入。
- 至少一个能力通过字段验证，例如 `index_daily` 或 qfq + `adj_factor`。
- 每个 request 可记录 provider、endpoint、request timestamp、response timestamp、params fingerprint、response hash、row_count。
- repo safety 通过，没有 raw vendor data 入库。

继续接入也只代表可以写下一张 adapter 设计卡，不代表可以生成 formal labels 或重跑生产化报告。

### 9.2 换数据源

出现以下情况应考虑 RiceQuant / JoinQuant / Wind / Choice / iFinD 等替代源：

- 授权不允许自动化或 raw archive。
- 核心接口权限不足，升级成本不可接受。
- `adj_factor` 或 limit / suspend 关键字段不可得。
- 调用频率或积分成本无法支撑未来日常归档。
- redacted manifest/report 也不允许进入 repo。

### 9.3 保持 internal benchmark research-only

如果 Tushare POC 不通过，且短期不采购其他授权源，Prism 应维持当前状态：

- CSI500 / HS300 继续 unavailable。
- formal market excess return 继续 unavailable。
- qfq / adj_factor 缺口继续使 formal adjusted return unavailable。
- suspend / limit / failed order / partial fill 缺口继续使 execution-realistic backtest unavailable。
- `eligible_universe_equal_weight` 只能保持 `research_only_internal_benchmark`。
- Card 5 / Sprint 2 rerun 如继续推进，也只能展示 hardened labels 的 unavailable / deferred / research-only reasons。

最终原则：

Tushare POC 的准入意义是确认是否值得安全地执行一次非生产字段可得性检查。没有清晰授权、成本、接口权限、hash/timestamp 纪律和 raw response 私有归档方案前，不应开发 adapter，也不应把任何外部数据写入 Prism 主线。
