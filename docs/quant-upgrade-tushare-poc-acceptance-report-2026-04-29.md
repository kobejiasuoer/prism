# Prism 量化升级 Tushare Pro 非生产 POC 独立验收报告

Date: 2026-04-29
Role: independent acceptance reviewer
Scope: Tushare Pro non-production POC acceptance only
Status: conditional pass

## 0. 验收边界

本次只读检查：

- `docs/quant-upgrade-tushare-poc-result-2026-04-29.md`
- `docs/quant-upgrade-tushare-poc-acceptance-checklist-2026-04-29.md`
- 当前 `git status`
- 当前 `git diff`

本次验收没有调用 Tushare API，没有读取 repo 外 raw vendor archive，没有修改 `packages/quant`，没有写 `data/quant`，没有生成 formal labels、formal excess return、formal adjusted return 或 execution-realistic backtest。

## 1. 总体验收结论

结论：**有条件通过**。

允许继续：**有条件允许**。

继续边界：只允许进入 **有限 non-production adapter design / source design**，且仅围绕 POC 已验证为 sample-available 的 `daily`、`adj_factor`、`stock_basic` 做设计讨论；不得直接实现 adapter，不得写 `packages/quant`，不得写 `data/quant`，不得回写 labels，不得生成 benchmark / excess return / adjusted return / execution-realistic backtest。

当前必须先解决的 blocker：

- 轮换曾被贴到 chat 的 token。
- 补齐或升级 `trade_cal` 权限/积分。
- 补齐或升级 `index_daily` 权限/积分，覆盖 CSI500 和 HS300。
- 补齐或升级 `stk_limit` 权限/积分。
- 解决 `suspend_d` 必需字段不完整问题，或确认正确停复牌 / tradestatus 接口。
- 单独验证 SDK-mediated `pro_bar` qfq/hfq 能力，或确认该能力不可用。
- 人工确认积分、费用、调用频率、授权和私有 raw archive / redacted report 入库边界。
- 当前工作区存在未跟踪的 `data/quant/` 和 `packages/quant/`；POC 后续提交必须只包含获批的脱敏 docs，不得把这些目录纳入 POC 变更。

## 2. 交付物完整性

| 检查项 | 结果 | 验收意见 |
| --- | --- | --- |
| POC result 文档存在 | 通过 | 文档标记 `completed_with_blockers`，并声明 production impact 为 none。 |
| POC acceptance checklist 存在 | 通过 | checklist 覆盖 token、raw vendor data、repo 边界、字段矩阵、权限/费用、formal/production 禁止项。 |
| 字段可得性信息存在 | 通过 | POC result 已列出接口状态、字段名、row_count、缺失字段和 response hash；不含行级 vendor 数据。 |
| 权限/积分/费用记录存在 | 有条件通过 | 已记录 permission / points blocked；但实际积分要求、费用、调用频率仍需人工确认。 |
| 决策建议存在 | 通过 | POC result 建议 conditional continue / pause on blocked capabilities。 |

## 3. Token 与 Secret 检查

| 检查项 | 结果 | 验收意见 |
| --- | --- | --- |
| token 是否出现在 repo 文件 | 通过 | 只发现 `TUSHARE_TOKEN` 环境变量名和 token 管理文字；未发现 token 明文写入 POC docs。 |
| token 是否出现在代码 / git diff | 通过 | 当前 tracked diff 的 Tushare / token / secret 关键词检查未发现 POC token hardcode。 |
| 是否存在 `ts.set_token` / `pro_api(...)` 等写死风险 | 通过 | POC docs 中未发现 `ts.set_token`、`pro_api(`、`token =`、`api_key =`、`secret =` 等硬编码形态。 |
| 疑似 token-like 字符串 | 通过，需注意 | POC result 中的长串主要为 9 个 SHA256 response hash；其他长串为文档路径或状态词，不构成 token hardcode。 |
| chat 暴露风险 | 有条件通过 | POC result 明确记录 token 曾被贴到 chat。虽然未进入 repo，但继续前必须轮换 token。 |

验收判断：repo 层面未发现 token 泄露；但 chat 暴露已被 POC 记录，必须作为继续前 blocker 处理。

## 4. Raw Vendor Data 与 Archive 检查

| 检查项 | 结果 | 验收意见 |
| --- | --- | --- |
| raw vendor data 是否进入 repo | 通过 | POC result 只包含 endpoint、字段名、row_count、missing fields、response hash；未包含 row-level OHLC、adj_factor、calendar、limit、suspend 或 stock_basic 明细。 |
| raw archive 是否 repo 外 | 通过 | POC result 声明 raw responses 只在 repo-external private path。验收未读取该路径。 |
| repo 内是否存在 Tushare raw/archive 文件名 | 通过 | repo 内只看到 Tushare 相关 docs 文件，未发现 raw response 文件名。 |
| archive path 暴露 | 有条件通过 | POC result 写出了完整本机路径。虽然路径在 repo 外，建议后续 redacted report 使用脱敏 archive reference，避免提交可识别本机路径。 |

## 5. Repo 边界检查

| 检查项 | 结果 | 验收意见 |
| --- | --- | --- |
| 是否写入 `data/quant` | 有条件通过 | POC result 声明没有写入；但当前 `git status` 中 `data/quant/` 仍为 untracked。应视为工作区背景风险，POC 提交不得包含该目录。 |
| 是否接入 `packages/quant` | 有条件通过 | POC result 声明没有接入；但当前 `git status` 中 `packages/quant/` 仍为 untracked。应视为工作区背景风险，POC 提交不得包含该目录。 |
| 是否覆盖 reports / labels | 通过 | POC result 声明未生成 labels、formal excess return、adjusted return 或 execution-realistic backtest；本次未发现 POC 报告声称已覆盖正式量化产物。 |
| 是否影响生产排序 / A/B/C / 页面 / Prism Edge / Expected 5D / ML | 通过 | POC result 明确 `no_change`；未发现 POC 文档允许生产化。 |

当前 `git status` 很脏，且包含大量与 POC 无关的修改和未跟踪文件。验收结论只覆盖 Tushare POC docs 的脱敏结果；提交或交接时必须隔离 POC 产物。

## 6. POC 结果准确性检查

| Blocker / 能力 | POC 标记 | 验收意见 |
| --- | --- | --- |
| `trade_cal` 权限/积分 | `permission_or_points_blocked` | 标记准确；当前不能冻结正式 trading calendar。 |
| CSI500 `index_daily` 权限/积分 | `permission_or_points_blocked` | 标记准确；当前不能生成 CSI500 formal benchmark 输入。 |
| HS300 `index_daily` 权限/积分 | `permission_or_points_blocked` | 标记准确；当前不能生成 HS300 secondary benchmark 输入。 |
| `stk_limit` 权限/积分 | `permission_or_points_blocked` | 标记准确；当前不能支持 limit-up/down execution flags。 |
| `suspend_d` 字段不完整 | `field_missing` | 标记准确；仅返回部分字段，不能支持 suspend execution eligibility。 |
| `pro_bar` SDK / 接口名问题 | `error_or_unknown` / SDK-mediated validation needed | 标记准确；不能据此宣称 qfq adjusted OHLC 可用。 |
| `daily` 可用 | `available` | 只能说明 sample-level raw OHLCV 可得，不得升级 formal labels。 |
| `adj_factor` 可用 | `available` | 只能说明 sample-level factor 字段可得，不得升级 formal adjusted return。 |
| `stock_basic` 可用 | `available` | 只能说明 sample-level metadata 可得，不得生成完整基础股票数据集入库。 |

验收判断：POC 结果没有过度解读 `daily`、`adj_factor`、`stock_basic` 的可用性；主要 blocker 被正确降级。

## 7. Formal / Production 禁止项检查

| 禁止项 | 结果 | 验收意见 |
| --- | --- | --- |
| formal labels | 通过 | 未生成，且 POC result 明确不支持。 |
| formal excess return | 通过 | `index_daily` 被阻塞，POC 未计算 excess return。 |
| formal adjusted return | 通过 | `adj_factor` sample 可用但未升级；`pro_bar` 未验证。 |
| execution-realistic backtest | 通过 | `stk_limit` 阻塞、`suspend_d` 不完整；POC 未生成 backtest。 |
| 生产排序 / A/B/C | 通过 | POC result 声明 no change。 |
| 页面 / Prism Edge / Expected 5D / ML | 通过 | POC result 声明 no change。 |

## 8. 是否允许继续

允许：**有条件允许继续**。

允许的继续方式：

- 只做 non-production adapter design / source design 文档。
- 只讨论 `daily`、`adj_factor`、`stock_basic` 的字段映射、hash/timestamp、archive、license、failure semantics。
- 所有输出保持 docs-only / report-only。
- 不写 `packages/quant`，不写 `data/quant`，不生成正式数据集。
- 不把 sample availability 解释为 formal readiness。

不允许的继续方式：

- 不允许实现正式 adapter。
- 不允许接入主线 pipeline。
- 不允许生成 benchmark returns 或 excess return。
- 不允许重跑 formal labels。
- 不允许做 execution-realistic backtest。
- 不允许页面、Prism Edge、Expected 5D、ML 或生产排序接入。

对于 benchmark、calendar、limit、suspend、qfq adjusted OHLC：当前更合理的下一步是 **先补权限/费用/字段映射，或并行评估 alternate source**。若这些 blocker 无法以可接受成本解决，应暂停 Tushare 在对应能力上的 adapter 设计。

## 9. 必须修复 / 澄清清单

1. 轮换已在 chat 暴露过的 Tushare token，并记录轮换完成状态，但不得写 token 值。
2. 人工确认 `trade_cal` 所需权限、积分、费用和调用频率。
3. 人工确认 `index_daily` 对 CSI500 / HS300 的权限、积分、费用和调用频率。
4. 人工确认 `stk_limit` 权限、积分、费用和调用频率。
5. 重新确认 `suspend_d` 字段请求方式、字段权限或替代停复牌 / tradestatus 接口。
6. 若需要 qfq adjusted OHLC，单独做 SDK-mediated `pro_bar` 非生产验证。
7. 明确 raw archive retention、访问权限、删除机制和 redacted archive reference 格式。
8. 提交 POC docs 前隔离工作区，确保不包含 `data/quant/`、`packages/quant/` 或任何 raw vendor data。

## 10. 最终裁决

Tushare Pro 非生产 POC 验收结论：**有条件通过**。

它证明了：

- 当前 POC 能触达 Tushare Pro，并以非生产方式记录字段、row_count、hash 和状态。
- `daily`、`adj_factor`、`stock_basic` 在样本层面可用。
- raw vendor data 未进入 repo。
- POC 没有生成 formal labels、formal excess return、formal adjusted return 或 execution-realistic backtest。

它没有证明：

- CSI500 / HS300 benchmark 可用。
- trading calendar 可用。
- limit-up/down execution flags 可用。
- suspend / tradestatus 字段可用。
- qfq adjusted OHLC 可用。
- Tushare 可以作为完整 P1-A hardening source。

最终建议：**有限继续 + 先补权限/换源评估**。对 raw OHLCV、adj_factor、stock_basic 可进入 non-production design；对 benchmark、calendar、limit、suspend、qfq 能力，必须先解决 blocker，解决不了就换源。
