# Prism 量化升级 Tushare Pro POC 验收清单

Date: 2026-04-29
Role: independent acceptance checklist author
Scope: Tushare Pro non-production POC acceptance checklist only
Status: checklist template; no code, no API call, no data generation

## 0. 使用边界

本清单用于未来验收 **Tushare Pro non-production availability POC**。

验收对象应只包括：

- redacted POC report。
- redacted POC manifest。
- redacted field availability matrix。
- redacted permission / cost / quota note。
- repo diff / git status / git log 摘要。
- 私有 raw archive 的存在性证明和 hash 对账结果。

验收时不得要求把 token、raw vendor data、行级行情、行级复权因子、行级涨跌停、完整交易日历或付费账号敏感信息写入 Prism repo。

## 1. 硬门槛清单

任一硬门槛失败，POC 验收结论不得为“通过”。

| # | 检查项 | 通过标准 | 证据要求 | 结果 |
| --- | --- | --- | --- | --- |
| 1 | Token 未泄露 | token 未出现在代码、文档、日志、截图、git diff、commit message 或共享 artifact 中 | 提供脱敏的 secret handling 说明；提供 repo / diff / log 检查摘要，不展示 token | 待填 |
| 2 | Raw vendor data 未提交 | repo 中没有 Tushare raw response、行级行情、行级复权因子、行级涨跌停、完整交易日历或可逆样本 | 提供 repo safety 检查摘要；redacted report 明确 no raw vendor data | 待填 |
| 3 | 未写入 `data/quant` | POC 没有新增、修改或覆盖 `data/quant` 下任何文件 | 提供 `data/quant` diff 摘要为 empty / unchanged | 待填 |
| 4 | 未接入 `packages/quant` | POC 没有新增或修改 adapter、pipeline、label、backtest、report 代码 | 提供 `packages/quant` diff 摘要为 empty / unchanged | 待填 |
| 5 | 仅验证 POC 范围 | POC 只验证字段可得性、授权边界、hash/timestamp/raw archive 方案 | redacted report 的 scope 明确为 availability check；无可用数据集输出 | 待填 |
| 6 | 未生成 formal 产物 | 未生成 formal labels、formal excess return、formal adjusted return 或 execution-realistic backtest | report / manifest 明确 no formal outputs；未重写 labels 或 reports | 待填 |
| 7 | 未影响生产面 | 未影响生产排序、A/B/C、页面、Prism Edge、Expected 5D 默认展示或 ML | repo diff 摘要确认相关路径 unchanged；report 明确 production impact none | 待填 |
| 8 | 字段可得性矩阵存在 | 每个候选接口都有 present / missing / permission_denied / unknown 结论 | 提供 redacted field availability matrix | 待填 |
| 9 | 权限/积分/费用记录存在 | 每个接口记录权限状态、积分/付费要求、调用频率或限制 | 提供 redacted permission / cost / quota note，不含账号敏感信息 | 待填 |
| 10 | POC 决策建议存在 | 给出继续 / 停止 / 换源建议，并说明条件和风险 | redacted report 包含 decision recommendation | 待填 |

## 2. Token 安全验收

| 检查项 | 通过标准 | 结果 |
| --- | --- | --- |
| Token 配置方式 | token 仅通过本地环境变量、secret manager 或人工受控方式配置 | 待填 |
| Token 未写入代码 | 代码 diff 中没有 token、API key、账号密码、cookie 或 session | 待填 |
| Token 未写入文档 | docs 中没有 token 明文、账号敏感信息或积分余额截图 | 待填 |
| Token 未写入日志 | POC log / terminal output / captured artifact 不含 token 明文 | 待填 |
| Token 未写入 git diff | staged / unstaged diff 均不含 token 或可逆敏感片段 | 待填 |
| Token 处理记录 | report 只记录 `configured_locally=true/false`、permission status、owner role 等脱敏信息 | 待填 |
| 泄露应急 | 若 token 泄露，POC 必须判定不通过，并要求吊销/轮换 token 和清理历史记录 | 待填 |

## 3. Repo 边界验收

| 检查项 | 通过标准 | 结果 |
| --- | --- | --- |
| `data/quant` | 无新增、修改、覆盖；没有 benchmark、price、calendar、execution、labels 或 reports 数据写入 | 待填 |
| `packages/quant` | 无新增、修改、覆盖；没有 adapter、registry、pipeline、label hardening 或 report 代码接入 | 待填 |
| `data/quant/reports` | 未覆盖 Sprint 2 / P1-A 既有报告 | 待填 |
| Raw archive | raw response 只在 repo 外私有归档，repo 内最多有脱敏 hash / row_count / field list | 待填 |
| 可逆 vendor 数据 | repo 中没有可还原 vendor 行级数据的 sample dump、CSV、JSON、截图或表格 | 待填 |
| Git 历史 | POC 相关 commit message / diff 摘要不含 token、raw data 或付费账号敏感信息 | 待填 |

## 4. POC 范围验收

POC 只能回答以下问题：

- Tushare Pro 是否具备候选字段。
- 当前账号是否有接口权限。
- 积分、费用、调用频率是否可接受。
- raw response 是否可以私有归档。
- 每次 request 是否能记录 hash、timestamp、params fingerprint、row_count 和 field list。
- redacted manifest / report 是否可以安全入库。

POC 不能回答或不能宣称：

- Prism 已具备 formal labels。
- Prism 已具备 formal excess return。
- Prism 已具备 formal adjusted return。
- Prism 已具备 execution-realistic backtest。
- Tushare 数据已接入生产排序。
- Prism Edge、页面、Expected 5D 或 ML 可以产品化展示。

## 5. 字段可得性矩阵模板

POC 验收必须看到字段可得性矩阵。矩阵不得包含行级 vendor 数据。

| 能力 | 候选接口 | 必需字段 / 能力 | 状态 | 权限状态 | 样本范围摘要 | row_count | missing / null 摘要 | response hash | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CSI500 / HS300 指数日线 | `index_daily` 或等价接口 | trade_date、open、high、low、close、pre_close | 待填 | 待填 | date range / index count | 待填 | 待填 | sha256 redacted | 待填 |
| Raw / qfq 行情 | `pro_bar` 或等价接口 | raw OHLCV、qfq OHLCV、pre_close | 待填 | 待填 | date range / symbol count | 待填 | 待填 | sha256 redacted | 待填 |
| 复权因子 | `adj_factor` 或等价能力 | code、trade_date、adj_factor | 待填 | 待填 | date range / symbol count | 待填 | 待填 | sha256 redacted | 待填 |
| 交易日历 | `trade_cal` 或等价接口 | cal_date、is_open、pretrade_date | 待填 | 待填 | date range / exchange | 待填 | 待填 | sha256 redacted | 待填 |
| 涨跌停 | `stk_limit` 或等价接口 | up_limit、down_limit、trade_date、code | 待填 | 待填 | date range / symbol count | 待填 | 待填 | sha256 redacted | 待填 |
| 停复牌 / 交易状态 | `suspend_d`、tradestatus 或等价接口 | suspend_date / resume_date / tradestatus | 待填 | 待填 | date range / symbol count | 待填 | 待填 | sha256 redacted | 待填 |
| 基础股票列表 | `stock_basic` 或等价接口 | code、name、market、exchange、list_status、list_date | 待填 | 待填 | as-of date / universe count | 待填 | 待填 | sha256 redacted | 待填 |

状态枚举建议：

- `present`
- `missing`
- `permission_denied`
- `rate_limited`
- `unknown`
- `not_tested`

## 6. 权限 / 积分 / 费用记录模板

| 能力 | 候选接口 | 权限状态 | 积分 / 付费要求 | 调用频率限制 | POC 调用量 | 后续日常归档可行性 | 风险 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 指数日线 | `index_daily` | 待填 | 待填 | 待填 | 待填 | 待填 | 待填 |
| Raw / qfq 行情 | `pro_bar` | 待填 | 待填 | 待填 | 待填 | 待填 | 待填 |
| 复权因子 | `adj_factor` | 待填 | 待填 | 待填 | 待填 | 待填 | 待填 |
| 交易日历 | `trade_cal` | 待填 | 待填 | 待填 | 待填 | 待填 | 待填 |
| 涨跌停 | `stk_limit` | 待填 | 待填 | 待填 | 待填 | 待填 | 待填 |
| 停复牌 / 交易状态 | `suspend_d` / tradestatus | 待填 | 待填 | 待填 | 待填 | 待填 | 待填 |
| 基础股票列表 | `stock_basic` | 待填 | 待填 | 待填 | 待填 | 待填 | 待填 |

权限状态枚举建议：

- `allowed`
- `allowed_with_limit`
- `permission_denied`
- `requires_paid_plan`
- `requires_points`
- `unknown`

不得记录：

- token 明文。
- 账号密码。
- 付费账号截图。
- 积分余额截图。
- 合同编号、付款信息或个人身份信息。

## 7. Hash / Timestamp / Raw Archive 验收

| 检查项 | 通过标准 | 结果 |
| --- | --- | --- |
| Request timestamp | 每次 request 有 ISO 8601 时间和 timezone | 待填 |
| Response timestamp | 每次 response 有本地接收时间；如 provider 返回服务端时间，可另记 | 待填 |
| Params fingerprint | 删除 token 后，对 params 稳定表示取 SHA256 | 待填 |
| Response hash | 对 raw response bytes 或固定 canonical payload 取 SHA256，规则前后一致 | 待填 |
| Row count | 每次 request 记录 row_count，失败时记录 error category | 待填 |
| Field list | 每次 request 记录 returned field names，不记录行级值 | 待填 |
| Raw archive | raw response 存在 repo 外私有归档；repo 内只有脱敏引用或 hash | 待填 |
| Archive access | 仅 POC 执行者和审批人可读；保留期限和删除机制已确认 | 待填 |

注意：hash 只能证明某份私有 raw response 与记录一致，不能替代授权，也不能证明历史 point-in-time。

## 8. Formal / Production 禁止项验收

| 禁止项 | 通过标准 | 结果 |
| --- | --- | --- |
| Formal labels | 未生成、未覆盖、未升级 labels 或 hardened labels | 待填 |
| Formal excess return | 未计算或写入 benchmark_return / excess_return formal 字段 | 待填 |
| Formal adjusted return | 未生成 adjusted price store，未将 qfq / adj_factor 回写 labels | 待填 |
| Execution-realistic backtest | 未生成 failed order、partial fill、order outcome 或 execution-realistic return | 待填 |
| 生产排序 | 未改 production ranking、score 排序或 hard gate | 待填 |
| A/B/C | 未替换、未重标、未联动现有 A/B/C | 待填 |
| 页面 | 未新增或修改页面、组件、路由、API 展示层 | 待填 |
| Prism Edge | 未做 Prism Edge 产品化或 shadow 接入 | 待填 |
| Expected 5D | 未新增默认展示、排序或入口 | 待填 |
| ML | 未训练、接入、评估或部署 ML 模型 | 待填 |

## 9. 决策建议模板

POC report 必须给出以下三类之一的建议。

### 9.1 继续

适用条件：

- token / authorization / archive / repo safety 全部通过。
- 至少一个 P1-A 关键能力达到字段可得性通过。
- hash、timestamp、params fingerprint、row_count、field list 记录完整。
- 权限、积分、费用和调用频率可支撑后续小规模 adapter 设计。

建议表述：

`继续：允许进入下一张 adapter design card，但仍不得写 formal labels、formal excess return、execution-realistic backtest 或生产功能。`

### 9.2 有条件继续

适用条件：

- repo safety 和 token safety 通过。
- 部分字段可得，但存在权限、费用、缺字段、频率、archive 或授权待确认项。
- 风险可以通过补授权、补权限、缩小接口范围或换能力拆卡解决。

建议表述：

`有条件继续：仅允许补齐指定阻塞项；在阻塞项关闭前不得进入正式 adapter。`

### 9.3 停止或换源

适用条件：

- token 泄露或 raw vendor data 入库。
- 授权不允许自动化、私有 raw archive 或 redacted report。
- 核心接口权限不足且不可升级。
- 成本、积分或频率不可接受。
- 无法记录 hash、timestamp、params fingerprint 或 row_count。
- Tushare 无法覆盖 P1-A 关键缺口。

建议表述：

`停止 / 换源：不进入 Tushare adapter；转向 RiceQuant / JoinQuant / Wind / Choice / iFinD 或继续内部 research-only 状态。`

## 10. 验收结论模板

### 通过

结论：**通过**。

理由：

- token safety 通过。
- repo safety 通过。
- raw vendor data 未入库。
- 未写 `data/quant`。
- 未接入 `packages/quant`。
- 字段可得性矩阵、权限/费用记录、hash/timestamp/raw archive 方案完整。
- 未生成 formal labels、formal excess return 或 execution-realistic backtest。
- 未影响生产排序、A/B/C、页面、Prism Edge、Expected 5D 或 ML。

允许下一步：

- 仅允许进入下一张外部数据 adapter design card 的人工评审。
- 仍不允许直接写生产代码或生成 formal 量化产物。

### 有条件通过

结论：**有条件通过**。

必须修复 / 澄清：

- 待填。

限制：

- 只能补齐上述问题。
- 修复前不得进入正式 adapter。
- 不得写 `packages/quant` 或 `data/quant`。
- 不得生成 formal labels、formal excess return 或 execution-realistic backtest。

### 不通过

结论：**不通过**。

失败原因：

- 待填。

处理要求：

- 若涉及 token 泄露：立即吊销或轮换 token，并清理相关日志、diff、提交记录和共享 artifact。
- 若涉及 raw vendor data 入库：立即停止 POC，做合规复盘，并按 repo 历史清理流程处理。
- 若涉及授权、archive、hash/timestamp 或权限失败：不得进入 adapter，需重新设计 POC 或换源。

## 11. 最终提醒

Tushare Pro POC 的验收目标是确认“是否值得进入下一张受控 adapter 设计卡”，不是确认 Prism 已经具备正式数据、正式标签、正式超额收益或可执行回测能力。
