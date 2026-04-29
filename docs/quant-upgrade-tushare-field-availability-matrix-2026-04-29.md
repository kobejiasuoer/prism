# Prism 量化升级 Tushare Pro 字段可得性矩阵模板

Date: 2026-04-29
Role: external data source field-availability planner
Scope: Tushare Pro non-production POC matrix template only
Status: template; all availability results are pending verification

References:

- `docs/quant-upgrade-tushare-poc-plan-2026-04-29.md`
- `docs/quant-upgrade-external-data-source-decision-pack-2026-04-29.md`
- `docs/quant-upgrade-p1a-external-data-source-research-2026-04-29.md`

External documentation referenced by the research pack:

- [Tushare 数据接口与积分说明](https://tushare.pro/document/1?doc_id=108)
- [Tushare pro_bar 复权行情说明](https://www.tushare.pro/document/1?doc_id=109)
- [Tushare index_daily 指数日线接口](https://tushare.pro/document/2?doc_id=95)

## 0. 使用边界

本文只提供字段可得性矩阵模板，不执行验证。

严格禁止：

- 不写代码。
- 不调用 Tushare API。
- 不安装依赖。
- 不要求或记录 token。
- 不写 `packages/quant`。
- 不写 `data/quant`.
- 不提交 raw vendor 数据。
- 不生成 benchmark、adjusted price、execution flags、calendar 或基础股票数据。
- 不生成 formal labels、formal excess return、formal adjusted return 或 execution-realistic backtest。

矩阵中的候选接口和关键字段均为 POC 待验证项，不代表字段已经可用。`POC 验证结果` 列必须在未来非生产 POC 执行后再填写；本模板中先留空。

## 1. 填写规则

| 列 | 填写说明 |
| --- | --- |
| 数据主题 | 要验证的数据类别 |
| 目标用途 | Prism P1-A 中可能使用该数据的目的 |
| 候选接口 | Tushare Pro 候选接口；必须由未来 POC 以账号权限和当时官方文档确认 |
| 关键字段 | Prism 需要验证的最小字段集合；字段名可能随接口不同而变化 |
| 是否需要积分/权限 | 先写 `待确认`，POC 后填写 `是/否/未知/受限` |
| 是否可能收费 | 先写 `待确认`，POC 后填写付费或积分判断 |
| 是否能用于 formal labels | 只允许条件判断；缺授权、PIT、hash、coverage 时必须为否 |
| 是否能用于 benchmark | 只对 benchmark 相关数据条件可用 |
| 是否能用于 adjusted price | 只对 raw/qfq/adj_factor 相关数据条件可用 |
| 是否能用于 execution flags | 只对 suspend/limit/tradestatus/board rule 相关数据条件可用 |
| 授权风险 | token、积分、调用频率、再分发、raw archive、商业用途等风险 |
| POC 验证结果 | 本模板先留空 |
| 备注 | 写候选映射、降级规则或需人工确认的问题 |

## 2. 字段可得性矩阵

| 数据主题 | 目标用途 | 候选接口 | 关键字段 | 是否需要积分/权限 | 是否可能收费 | 是否能用于 formal labels | 是否能用于 benchmark | 是否能用于 adjusted price | 是否能用于 execution flags | 授权风险 | POC 验证结果 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 交易日历 | 冻结 entry/exit trading dates；校验 price / benchmark 日期；支持 forward window maturity | `trade_cal` 或账号可见等价接口 | `exchange`, `cal_date`, `is_open`, `pretrade_date` | 待确认 | 待确认 | 条件可用：需覆盖 formal label windows，并与官方休市公告交叉审计 | 间接可用：benchmark 日期对齐 | 间接可用：price 日期对齐 | 间接可用：执行日期对齐 | 数据商 calendar 不能替代交易所官方规则；raw calendar 不得未经授权入库 |  | POC 只记录 coverage / row_count / hash，不提交完整 calendar |
| 指数日线：CSI500 | Primary benchmark 候选；未来计算 CSI500 benchmark return 的前置验证 | `index_daily` | `ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `pre_close`, `vol`, `amount` | 待确认 | 待确认 | 条件可用：只在 source/hash/retrieved_at/coverage/license 通过后用于 formal label 的 benchmark 侧输入 | 条件可用：候选映射 `CSI500=000905.SH`，需 POC 确认 | 否 | 否 | 指数行情再分发风险；不可提交行级指数数据 |  | 映射为候选，不可视为已确认 |
| 指数日线：HS300 | Secondary benchmark 候选；大盘风格对照 | `index_daily` | `ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `pre_close`, `vol`, `amount` | 待确认 | 待确认 | 条件可用：只能作为 secondary benchmark 输入，不能替代 primary | 条件可用：候选映射 `HS300=000300.SH`，需 POC 确认 | 否 | 否 | 指数行情再分发风险；不可提交行级指数数据 |  | 缺失不应阻塞 CSI500 primary，但对应 HS300 excess unavailable |
| 指数日线：CSI1000 | Optional secondary benchmark 候选；小盘风格对照 | `index_daily` | `ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `pre_close`, `vol`, `amount` | 待确认 | 待确认 | 条件可用：仅在人工决定引入 CSI1000 secondary 后使用 | 条件可用：候选映射 `CSI1000=000852.SH`，需 POC 确认接口是否支持 | 否 | 否 | 指数行情再分发风险；接口权限和代码映射待确认 |  | P1-A 当前主线不是必须项，建议作为 optional POC row |
| 股票日线 OHLCV | raw return audit；qfq 对齐；volume / amount 可支持 conservative execution cap | `daily`, `pro_bar` raw 或账号可见等价接口 | `ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `pre_close`, `vol`, `amount` | 待确认 | 待确认 | 条件可用：raw 只能作为 audit；不能单独支持 formal adjusted return | 否 | 间接可用：与 qfq / adj_factor 对齐后可用于 adjusted price audit | 条件可用：`vol` / `amount` 可支持 research-only partial fill estimate，但不证明真实成交 | 个股日线再分发风险；raw response 不得入库 |  | 不得用 raw OHLCV 推断 qfq 或停牌事实 |
| 复权行情：qfq | formal adjusted return 候选输入；消除除权除息跳变 | `pro_bar` with qfq 或等价复权行情能力 | `ts_code`, `trade_date`, qfq `open/high/low/close`, `pre_close`, `vol`, `amount`, adjustment params | 待确认 | 待确认 | 条件可用：必须有 adj_factor / policy / retrieved_at / hash / coverage；否则只 report-only | 否 | 条件可用：qfq price 候选 | 否 | 复权口径和历史修订风险；只有当前回算序列时 PIT 弱 |  | qfq price 可得不等于 formal adjusted return ready |
| 复权因子 | 解释 raw 与 qfq 差异；formal adjusted return 前置字段 | `adj_factor`, `pro_bar` with adj factor 或账号可见等价接口 | `ts_code`, `trade_date`, `adj_factor`, factor effective date 或可解释 revision 字段 | 待确认 | 待确认 | 条件可用：formal adjusted return 建议要求因子存在；无因子则否 | 否 | 条件可用：核心字段 | 否 | corporate action 修订、PIT、再分发风险；factor 序列不得入库 |  | 若只有 adjusted OHLC 无 factor，矩阵应标 `partial` |
| 停复牌 | 判断 entry/exit 是否可交易；避免把缺价当可成交 | `suspend_d`, 停复牌接口、日级 trading status 或账号可见等价接口 | `ts_code`, `suspend_date`, `resume_date`, `ann_date`, `suspend_reason`, `tradestatus` / `is_suspended` | 待确认 | 待确认 | 条件可用：formal label 的 execution side 需要覆盖 entry/exit dates | 否 | 否 | 条件可用：source-provided suspend/tradestatus 可用于 execution flags | 停复牌字段权限、历史覆盖、事件级转日级展开风险 |  | 不能用 price row missing 或 volume=0 直接推断停牌 |
| 涨跌停价格或状态 | 判断 open/close at limit；未来保守 blocked order 标记的输入 | `stk_limit` 或等价涨跌停接口 | `ts_code`, `trade_date`, `up_limit`, `down_limit`, limit status 字段如可得 | 待确认 | 待确认 | 条件可用：只作为 execution side 输入，不单独证明 formal label ready | 否 | 否 | 条件可用：limit price / status 可用于 execution flags；真实成交仍不可证明 | 不同板块/ST/新股规则、字段权限、再分发风险 |  | 若只有 limit price，无 status，则后续只能 derived status 并标 ambiguous |
| 股票基础信息 | 统一证券代码、上市状态、上市日期、交易所、市场属性；支持 universe 和规则表 | `stock_basic` 或等价基础证券信息接口 | `ts_code`, `symbol`, `name`, `exchange`, `market`, `list_status`, `list_date`, `delist_date` | 待确认 | 待确认 | 间接可用：只作为 eligibility / rule metadata，不直接形成 return label | 否 | 否 | 条件可用：上市日期、交易所、市场可支持 execution rule versioning | 基础信息再分发风险；上市状态历史修订风险 |  | POC 只记录字段可得性，不提交完整股票列表 |
| 行业 / 板块 | 行业/主题 exposure audit；板块涨跌幅规则或 universe diagnostics 的辅助输入 | `stock_basic`, `stock_company`, `concept`, `ths_index`, `index_member` 或账号可见等价接口 | `ts_code`, industry / sector / concept id, concept name, in_date / out_date 如可得 | 待确认 | 待确认 | 通常不直接用于 formal labels；若用于分层评估需单独 PIT 审计 | 否 | 否 | 条件可用：仅在板块规则或 ST/market rule 需要时辅助 | 行业/概念口径供应商化、历史 membership PIT、再分发风险 |  | 不应把题材/概念字段直接接生产排序 |
| 成交额、换手率、市值 | liquidity audit；partial fill cap；market cap / turnover 分层；风控解释 | `daily`, `daily_basic`, `pro_bar` 或账号可见等价接口 | `amount`, `vol`, `turnover_rate`, `turnover_rate_f`, `volume_ratio`, `total_mv`, `circ_mv`, `free_share` | 待确认 | 待确认 | 条件可用：可作 label/backtest 分层或 liquidity filter，但不能单独证明成交 | 否 | 间接可用：amount/vol 与 price 对齐 | 条件可用：amount/vol 可支持 research-only partial fill estimate；市值/换手率用于分层 | 市值/换手率口径、复权/股本修订、再分发和 PIT 风险 |  | `daily_basic` 等候选接口需 POC 确认权限和字段 |

## 3. POC 结果填写规范

`POC 验证结果` 列未来只允许填写以下状态之一：

| 状态 | 含义 |
| --- | --- |
| `not_run` | 未验证 |
| `available` | 字段可得、权限可用、metadata 可记录 |
| `available_with_limits` | 字段可得但有积分、频率、覆盖或授权限制 |
| `partial` | 只取得部分字段，例如 qfq 可得但 adj_factor 不可得 |
| `permission_denied` | 账号无权限 |
| `paid_required` | 需要付费或积分升级，当前 POC 未通过 |
| `field_missing` | 关键字段缺失 |
| `coverage_gap` | 字段存在但日期、标的或市场覆盖不足 |
| `license_blocked` | 授权不允许 archive、自动化或 redacted report |
| `unknown` | 文档或返回无法判断 |

## 4. 入库边界

允许提交到 Prism repo：

- 本矩阵模板。
- 未来 redacted report 中的字段可得性状态。
- 接口名、字段名、row_count、missing count、response hash、request timestamp、response timestamp、params fingerprint。
- 授权风险摘要。

禁止提交到 Prism repo：

- Tushare token、账号、积分余额、会员截图。
- raw response。
- 行级指数日线。
- 行级股票 OHLCV。
- 行级 qfq / adj_factor。
- 行级停复牌。
- 行级涨跌停。
- 完整交易日历。
- 完整基础股票列表。
- 可还原 vendor dataset 的样本数据。

## 5. 使用结论

本矩阵只能作为 Tushare Pro 非生产 POC 的 checklist。任何 `available` 状态都不自动升级 Prism 量化结论。

进入正式 adapter 仍需另行满足：

- 授权允许本地研究、自动化、私有 raw archive 和 redacted manifest/report。
- 每次请求能记录 provider、endpoint、request timestamp、response timestamp、params fingerprint、response hash 和 row_count。
- raw vendor data 不进入 repo。
- 缺失字段有明确 unavailable / research-only 降级。
- P1-A 仍保持 report-only，不进入生产排序、A/B/C、页面、Prism Edge、Expected 5D 或 ML。
