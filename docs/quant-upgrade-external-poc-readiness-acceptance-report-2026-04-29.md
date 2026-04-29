# Prism 量化升级外部数据 POC 准入前独立验收报告

Date: 2026-04-29
Role: independent acceptance reviewer
Scope: external data POC readiness review only
Status: accepted for non-production POC readiness, with pre-execution conditions

## 0. 验收边界

本次验收只读检查以下文档：

- `docs/quant-upgrade-p1a-external-data-source-research-2026-04-29.md`
- `docs/quant-upgrade-external-data-source-decision-pack-2026-04-29.md`
- `docs/quant-upgrade-tushare-poc-plan-2026-04-29.md`
- `docs/quant-upgrade-master-progress-and-handoff-2026-04-29.md`

本次验收没有调用外部 API，没有安装依赖，没有读取或修改 `packages/quant`，没有读取或修改 `data/quant`，没有生成 benchmark、labels、reports 或 vendor 数据。

## 1. 总体验收结论

结论：**通过外部数据 POC 准入前文档验收**。

通过含义仅限于：当前文档已经足够支持启动 **Tushare Pro non-production availability POC** 的人工准备和执行审批。

不代表：

- 允许接入 Prism 主线代码。
- 允许写入 `packages/quant`。
- 允许写入 `data/quant`。
- 允许提交 raw vendor 数据。
- 允许生成 formal labels、formal excess return、formal adjusted return 或 execution-realistic backtest。
- 允许进入生产排序、A/B/C 替换、页面、Prism Edge、Expected 5D 默认展示或 ML。

实际执行 POC 前仍必须完成人工确认：账号、token、权限、积分/费用、授权条款、自动化调用边界、raw response 私有归档位置，以及 redacted manifest/report 是否允许入库。

## 2. 文档完整性检查

| 检查项 | 结果 | 说明 |
| --- | --- | --- |
| 外部数据源调研文档存在 | 通过 | 已覆盖 Tushare、RiceQuant、JoinQuant、Wind/Choice/iFinD、AKShare、BaoStock 等路线，并声明 research-only/report-only 边界。 |
| 外部数据源决策包存在 | 通过 | 已明确 manual decision update：允许 Tushare Pro non-production POC，但只作为 availability check。 |
| Tushare POC plan 存在 | 通过 | 已明确 plan only、not executed，并给出 token、授权、raw archive、hash/timestamp、redacted report 边界。 |
| master progress handoff 存在 | 通过 | 已确认下一阶段是 Tushare Pro non-production POC，且 POC 尚未开始。 |

## 3. 八项准入重点逐项检查

| 准入重点 | 结果 | 验收意见 |
| --- | --- | --- |
| 1. Tushare POC 只是 non-production POC | 通过 | 决策包、POC plan 和 handoff 均明确为 non-production availability check，不是生产接入。 |
| 2. 禁止接主线代码 | 通过 | 决策包和 POC plan 均要求不连接 Prism 主量化管线；handoff 也重申不接主线代码。 |
| 3. 禁止写 `data/quant` | 通过 | POC 输出不得进入 `data/quant`；raw archive 必须在 repo 外私有位置。 |
| 4. 禁止提交 raw vendor 数据 | 通过 | POC plan 明确 raw response 不允许进入 Prism repo，只能私有归档；redacted report 不得含行级行情或可逆样本。 |
| 5. token 不能写入代码、文档、日志或提交记录 | 通过 | 文档明确 token 只由人工在 local secret store/env 配置，不进入 git、文档、日志、截图或共享 artifact。 |
| 6. 只验证字段可得性、授权边界、hash/timestamp/raw response archive 方案 | 通过 | POC 目标限定为接口字段可得性、权限/授权、source hash、retrieved_at、query params、row_count 和私有归档纪律。 |
| 7. 没有承诺 formal labels、formal excess return、execution-realistic backtest | 通过 | 多处明确禁止 formal labels、formal excess return、formal adjusted return 和 execution-realistic backtest。 |
| 8. 没有允许生产排序、A/B/C 替换、页面、Prism Edge、Expected 5D 或 ML | 通过 | 决策包、POC plan、handoff 均明确列为 prohibited / 当前不能做事项。 |

## 4. Tushare POC 边界验收

当前 POC 设计符合准入边界：

- POC 只回答 Tushare Pro 是否足以作为 P1-A 外部数据源最小可行候选。
- POC 样本范围被限制为小样本 availability check，不做全量回填。
- POC 输出只允许 redacted POC report 和 redacted manifest，且必须不含 row-level vendor data。
- POC 不生成 benchmark daily、security prices、calendar、execution JSONL 或任何可用数据集。
- POC 不重跑 Sprint 2 factor/backtest/health 报告。
- POC 不写 `forward_return_labels` 或 hardened label sidecar。

验收判断：边界足够清晰，可以避免把外部数据 POC 误读成数据接入或策略升级。

## 5. Token / Raw Data / Archive 安全检查

| 安全项 | 结果 | 验收意见 |
| --- | --- | --- |
| token 管理 | 通过 | 已要求 token 通过 local secret store/env 注入，并禁止进入 git、文档、日志、截图。 |
| token 权限 | 通过 | 已要求执行前确认接口权限、积分消耗、调用频率和 token 维护/轮换责任。 |
| raw response 归档 | 通过 | 已要求 raw response 存放在 repo 外私有目录或受控对象存储，不得进入 `data/quant` 或 git tracked path。 |
| repo 可入库内容 | 通过 | 只允许 response hash、row_count、returned fields、missing count、date range、permission status、license note 摘要等脱敏汇总。 |
| hash/timestamp discipline | 通过 | 已要求 source hash、retrieved_at、query params redaction、row_count、field list 和 license note。 |
| 失败条件 | 通过 | 已明确 token 泄露、raw vendor data 入库、缺 hash/retrieved_at/row_count 等情况应判定失败或不得进入 adapter。 |

## 6. Formal / Production 禁止事项检查

未发现文档承诺或允许以下事项：

- formal labels。
- formal excess return。
- formal adjusted return。
- execution-realistic backtest。
- production-ready 结论。
- 生产排序接入。
- A/B/C 替换。
- 页面或 Prism Edge 产品化。
- Expected 5D 默认展示。
- ML。

文档还明确说明，即使 POC 后续通过，也只代表可以进入正式 adapter 设计的人工决策输入，不代表 Prism 量化结论升级。升级 formal labels 仍需另行满足 benchmark coverage、adjusted price/adj_factor、trading calendar、execution flags、source hash、retrieved_at、query params、row_count、raw archive 和 license note 等条件。

## 7. 准入前仍需人工拍板事项

以下不是文档缺陷，但属于 POC 执行前硬条件：

- Tushare Pro 账号是否已开通，以及账号用途边界。
- token 是否可用，权限是否覆盖 `index_daily`、qfq/adj_factor、trade_cal、stk_limit、suspend/tradestatus 等候选能力。
- token 由谁维护、如何保密、是否在 POC 后轮换或吊销。
- 积分、费用、调用频率和 POC 调用预算。
- 授权是否允许本地研究、自动化调用、私有 raw archive、redacted manifest/report 入库。
- raw response 私有归档位置、访问权限、加密/受控方式、保留期限和删除机制。
- redacted manifest/report 是否可以提交到当前 repo。

任一项未确认时，不应执行对应接口调用或保存动作。

## 8. 风险和观察项

- Tushare 可作为 P1-A 最小可行 POC 候选，但仍需授权和字段实测，不应预设所有接口可用。
- 历史回填不能天然证明 point-in-time；只能从本地归档日之后逐步形成 as-collected 证据。
- 如果只拿到 qfq price 而没有 adj_factor 或等价可解释因子，仍不得升级 formal adjusted return。
- 如果 suspend/tradestatus 不可得，只能作为已知缺口，不得宣称 execution-realistic。
- redacted report 必须避免行级行情、完整交易日历、复权因子序列、涨跌停价序列和任何可逆 vendor 样本。

## 9. 最终裁决

POC 准入状态：**通过**。

允许下一步：在完成人工账号、token、授权、费用、私有归档和 redacted 入库边界确认后，可以执行 **Tushare Pro non-production availability POC**。

不允许下一步：

- 不允许直接进入正式 adapter。
- 不允许写 `packages/quant`。
- 不允许写 `data/quant`。
- 不允许提交 raw vendor 数据。
- 不允许生成 formal labels、formal excess return、formal adjusted return 或 execution-realistic backtest。
- 不允许生产排序、A/B/C 替换、页面、Prism Edge、Expected 5D 默认展示或 ML。

必须保留的验收口径：POC 的价值是验证外部数据源能否成为 P1-A MVP 候选，不是生成可用数据、回填 labels 或证明策略有效。
