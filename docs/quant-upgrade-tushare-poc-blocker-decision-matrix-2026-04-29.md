# Prism 量化升级 Tushare POC Blocker 决策矩阵

Date: 2026-04-29
Role: external data source blocker decision advisor
Scope: Tushare Pro non-production POC blocker decisions only
Status: decision matrix template; no execution

References:

- `docs/quant-upgrade-tushare-poc-plan-2026-04-29.md`
- `docs/quant-upgrade-tushare-field-availability-matrix-2026-04-29.md`
- `docs/quant-upgrade-external-data-source-decision-pack-2026-04-29.md`

## 0. 本文边界

本文只写 blocker 决策矩阵，不执行 POC。

严格禁止：

- 不写代码。
- 不调用 Tushare API。
- 不安装依赖。
- 不要求或记录 token。
- 不建议现在接主线代码。
- 不写 `packages/quant`。
- 不写 `data/quant`。
- 不提交 raw vendor data。
- 不生成 benchmark、adjusted price、execution flags 或 calendar 数据。
- 不生成 formal labels、formal excess return、formal adjusted return 或 execution-realistic backtest。

本文所有“补权限 / 换源 / 降级”均指非生产 POC 和决策层动作，不代表允许开发正式 adapter 或接入 Prism 主链路。

## 1. 决策原则

| 原则 | 说明 |
| --- | --- |
| 授权优先 | 字段可得但授权不清时，视为不可进入正式 adapter |
| Hash/timestamp 优先 | 无法记录 source hash、request/response timestamp、params fingerprint、row_count 时，不进入正式 adapter |
| 缺口显式降级 | 任何 blocker 未解决前，必须保持 unavailable / research-only |
| 不静默替代 | 不用 internal benchmark 顶替 CSI500 / HS300，不用 raw OHLCV 顶替 qfq，不用缺价推断停牌 |
| POC 不生产化 | POC 结果只能进入 redacted report / manifest，不写 `packages/quant` 或 `data/quant` |

Impact 标记说明：

| 标记 | 含义 |
| --- | --- |
| `Hard block` | 未解决前不得声称对应能力可用 |
| `Partial block` | 可继续做其他能力，但该能力必须 unavailable / research-only |
| `No direct block` | 不直接阻塞该能力，但可能影响审计或后续稳定性 |

## 2. Blocker 总览

| Blocker | 是否阻塞 formal labels | 是否阻塞 formal excess return | 是否阻塞 formal adjusted return | 是否阻塞 execution-realistic backtest | 推荐决策 |
| --- | --- | --- | --- | --- | --- |
| `trade_cal` 权限/积分不足 | Partial block | Partial block | Partial block | Partial block | 先补权限；若不可控，使用官方休市公告 + 其他授权源 cross-check；全部保持 report-only |
| `index_daily` 权限/积分不足 | Partial block | Hard block | No direct block | No direct block | 优先补 Tushare 权限；不行则换授权 benchmark 源；否则继续 internal benchmark research-only |
| `stk_limit` 权限/积分不足 | Partial block | No direct block | No direct block | Hard block | 优先补权限；不行换源；否则 limit flags unavailable，不做 execution-realistic |
| `suspend_d` 返回字段不完整 | Partial block | No direct block | No direct block | Hard block | 若仅事件级可用则标 partial；需换源或继续 suspend unavailable |
| `pro_bar` qfq 需要 SDK-mediated 验证 | Partial block | No direct block | Hard block | Partial block | 只做非生产 SDK 验证准入；未通过前 adjusted return unavailable |
| token 已暴露过，需要轮换 | Hard block | Hard block | Hard block | Hard block | 立即吊销/轮换；清理日志/文档；重建 POC run id |
| raw archive / redacted report / 授权边界需要长期规范 | Hard block | Hard block | Hard block | Hard block | 先制定长期规范；未通过前不进入 adapter |

## 3. Blocker 决策矩阵

### 3.1 `trade_cal` 权限/积分不足

影响判断：

| 能力 | 阻塞程度 | 原因 |
| --- | --- | --- |
| formal labels | Partial block | label entry/exit windows 需要可复现 trading calendar |
| formal excess return | Partial block | benchmark return 需要与交易日历对齐 |
| formal adjusted return | Partial block | raw/qfq price entry/exit date 需要 calendar 对齐 |
| execution-realistic backtest | Partial block | suspend/limit/order outcome 都依赖交易日对齐 |

可选方案：

| 方案 | 动作 | 成本 | 风险 | 适用条件 |
| --- | --- | --- | --- | --- |
| A：补 Tushare 权限/积分 | 升级或确认 `trade_cal` 可用权限；只做 non-production POC | 低到中，取决于积分/会员 | 数据商 calendar 不能替代官方交易所公告；仍需 source hash / timestamp | Tushare 权限成本可接受，且授权允许 raw archive / redacted report |
| B：换源或多源交叉验证 | 用交易所官方休市公告作规则来源；用 RiceQuant / JoinQuant / Wind / Choice 等授权源 cross-check | 中到高，需人工维护或采购 | 多源日期冲突需要 source-of-truth 规则 | Tushare calendar 受限但项目允许其他授权源 |
| C：继续 internal research-only 降级 | 不冻结 external calendar；继续使用现有 report-only 状态 | 低 | 无法升级 formal labels；calendar 缺口继续存在 | 权限、费用或授权不清 |

推荐决策：

- POC 阶段先走 A，验证 `trade_cal` 是否低成本可用。
- 若 A 不可行，B 中官方休市公告必须成为 rule source，数据商 calendar 只能作为 cross-check。
- 若没有清晰授权和归档纪律，走 C；不因此阻塞当前 Card 5 report-only rerun。

### 3.2 `index_daily` 权限/积分不足，影响 CSI500 / HS300 benchmark

影响判断：

| 能力 | 阻塞程度 | 原因 |
| --- | --- | --- |
| formal labels | Partial block | formal label 可先保持 benchmark unavailable，但不能输出 market excess |
| formal excess return | Hard block | CSI500 / HS300 benchmark 不可得时不得计算 formal excess return |
| formal adjusted return | No direct block | adjusted return 主要依赖 qfq / adj_factor，不直接依赖 index_daily |
| execution-realistic backtest | No direct block | execution realism 主要依赖 suspend / limit / fill 数据 |

可选方案：

| 方案 | 动作 | 成本 | 风险 | 适用条件 |
| --- | --- | --- | --- | --- |
| A：补 Tushare 权限/积分 | 确认或升级 `index_daily` 权限，验证 CSI500 / HS300 / optional CSI1000 | 低到中 | 指数数据再分发限制；历史回填 PIT 仍需本地 archive | Tushare 指数日线成本可接受 |
| B：换源或多源交叉验证 | 使用中证授权数据、RiceQuant / JoinQuant / Wind / Choice 等授权源 | 中到高 | 采购、合同、再分发和自动化限制更重 | 对 benchmark 权威性要求更高，或 Tushare 不可用 |
| C：继续 internal research-only 降级 | 保留 `eligible_universe_equal_weight` 作为 internal research-only | 低 | 不能输出 formal market excess；不能把 internal benchmark 当 CSI500 / HS300 | benchmark 授权暂不明确 |

推荐决策：

- `index_daily` 是 Tushare POC 的高优先级 blocker，建议先走 A。
- 若 A 失败，优先走 B，而不是用 internal equal-weight 冒充市场 benchmark。
- 在 A/B 成功前，formal excess return 必须保持 unavailable。

### 3.3 `stk_limit` 权限/积分不足，影响涨跌停 execution flags

影响判断：

| 能力 | 阻塞程度 | 原因 |
| --- | --- | --- |
| formal labels | Partial block | formal label 若要求 execution side 完整，limit 缺失会阻塞 formal-ready |
| formal excess return | No direct block | excess return 可由 benchmark 计算，但 execution realism 不完整 |
| formal adjusted return | No direct block | qfq / adj_factor 不直接依赖 limit |
| execution-realistic backtest | Hard block | 无 source-provided limit price/status 时不能判断涨停买入、跌停卖出等 blocked 状态 |

可选方案：

| 方案 | 动作 | 成本 | 风险 | 适用条件 |
| --- | --- | --- | --- | --- |
| A：补 Tushare 权限/积分 | 确认或升级 `stk_limit` 权限，验证 up_limit / down_limit | 低到中 | 只有 limit price 不等于可成交性；不同板块/ST/新股规则仍需规则表 | Tushare `stk_limit` 字段可用且授权允许 archive |
| B：换源或多源交叉验证 | 使用 JoinQuant / RiceQuant / Wind / Choice 等 limit 字段 | 中到高 | 多源口径冲突；授权更严格 | Tushare limit 不可用但 execution hardening 是 P1-B 目标 |
| C：继续 internal research-only 降级 | limit flags 保持 unavailable；只做 report-only backtest | 低 | 回测仍可能乐观 full fill，必须明确 not execution-realistic | P1-A 暂不升级 execution realism |

推荐决策：

- 若目标仍是 P1-A MVP，可先走 A 只验证 limit price 可得性。
- 若 A 不通过，不建议用 OHLC 直接替代 source-provided limit；最多作为 inferred / ambiguous 研究标记。
- execution-realistic backtest 在 `stk_limit` 或等价字段可用前必须禁止。

### 3.4 `suspend_d` 返回字段不完整

影响判断：

| 能力 | 阻塞程度 | 原因 |
| --- | --- | --- |
| formal labels | Partial block | 若 formal label 要包含 execution readiness，停牌状态不完整会阻塞 |
| formal excess return | No direct block | benchmark excess 不直接依赖停牌字段 |
| formal adjusted return | No direct block | qfq / adj_factor 不直接依赖停牌字段 |
| execution-realistic backtest | Hard block | 无法判断 entry/exit 是否停牌或是否需要延后 |

可选方案：

| 方案 | 动作 | 成本 | 风险 | 适用条件 |
| --- | --- | --- | --- | --- |
| A：补 Tushare 权限/积分 | 确认是否有更完整停复牌 / 日级 tradestatus 权限 | 低到中 | 可能只有事件区间而非日级状态；需要 calendar 展开 | Tushare 有更高权限接口或字段 |
| B：换源或多源交叉验证 | 使用 JoinQuant paused、RiceQuant trading status、Wind / Choice 状态字段等授权源 | 中到高 | 授权限制、字段口径冲突、历史 coverage 不一致 | Tushare 只能事件级或字段缺失 |
| C：继续 internal research-only 降级 | `suspend_status` 保持 unavailable；不生成 blocked / delayed order | 低 | 无法称 execution-realistic；必须保留 research-only | 暂无可授权停牌源 |

推荐决策：

- 若 `suspend_d` 只返回事件级字段，可判定为 `partial`，不应直接视为日级 execution flag 完整。
- 推荐先走 A 查清是否有日级状态；若无，走 B。
- 在停牌日级状态不完整前，execution-realistic backtest 必须保持 blocked。

### 3.5 `pro_bar` qfq 需要 SDK-mediated 验证

影响判断：

| 能力 | 阻塞程度 | 原因 |
| --- | --- | --- |
| formal labels | Partial block | formal label 若要求 adjusted return，qfq/adj_factor 未验证会阻塞 |
| formal excess return | No direct block | excess 依赖 benchmark，但若 net_return 要用 adjusted return，则会间接受阻 |
| formal adjusted return | Hard block | qfq 和 adj_factor 未验证前不得声明 formal adjusted return |
| execution-realistic backtest | Partial block | execution price 口径和 adjusted/raw audit 不清会影响 backtest 解释，但非唯一 blocker |

可选方案：

| 方案 | 动作 | 成本 | 风险 | 适用条件 |
| --- | --- | --- | --- | --- |
| A：补 Tushare 权限/积分 | 允许未来执行者在非生产环境用 SDK-mediated 方式验证 qfq 和 adj_factor | 中；需本地环境和 SDK，但本文件不执行 | SDK 行为、字段口径、历史修订和 PIT 风险；token 不能泄露 | Tushare 文档/API 显示需 SDK 才能验证 `pro_bar` |
| B：换源或多源交叉验证 | 使用 RiceQuant / JoinQuant / Wind / Choice 等 adjusted price / factor 字段交叉验证 | 中到高 | 多源复权口径不同，需 source-of-truth 拍板 | Tushare qfq/adj_factor 不能稳定验证 |
| C：继续 internal research-only 降级 | raw return 保留 audit；formal adjusted return unavailable | 低 | 不能升级 formal labels；除权除息跳变风险仍在 | 暂不处理 adjusted return |

推荐决策：

- 允许未来做 SDK-mediated 非生产验证，但必须先完成 token 安全和 raw archive 方案。
- 若 SDK 验证只能得到 qfq OHLC 而无 adj_factor，结论应为 partial，不进入 formal adjusted return。
- 在 qfq + adj_factor + policy + hash/timestamp 都通过前，formal adjusted return 必须 unavailable。

### 3.6 token 已暴露过，需要轮换

影响判断：

| 能力 | 阻塞程度 | 原因 |
| --- | --- | --- |
| formal labels | Hard block | 凭证泄露会污染所有后续调用的合规和审计链 |
| formal excess return | Hard block | benchmark 数据源凭证不可信 |
| formal adjusted return | Hard block | price / factor 数据源凭证不可信 |
| execution-realistic backtest | Hard block | execution fields 数据源凭证不可信 |

可选方案：

| 方案 | 动作 | 成本 | 风险 | 适用条件 |
| --- | --- | --- | --- | --- |
| A：补 Tushare 权限/积分 | 不适用为第一动作；必须先吊销/轮换 token，再重新确认权限 | 低到中 | 旧 token 泄露可能已进入日志/缓存，需要清理 | 仍决定继续 Tushare POC |
| B：换源或多源交叉验证 | 若 Tushare 账号安全无法恢复，换新账号或换授权源 | 中到高 | 新源采购和授权成本；旧泄露仍需复盘 | token 泄露范围无法控制 |
| C：继续 internal research-only 降级 | 暂停外部 POC，保持 internal research-only | 低 | 外部数据接入延后 | 安全复盘未完成 |

推荐决策：

- 立即暂停所有外部 POC。
- 吊销或轮换 token，清理日志/文档/截图/环境文件，确认 git history 未提交 secret。
- 使用新 token 和新 `poc_run_id` 重新开始，旧 run 不得进入 adapter 决策依据。
- 在安全复盘完成前，不允许任何外部数据进入正式 adapter 评审。

### 3.7 raw archive / redacted report / 授权边界需要长期规范

影响判断：

| 能力 | 阻塞程度 | 原因 |
| --- | --- | --- |
| formal labels | Hard block | 无长期 archive 和授权规范时无法证明 source lineage |
| formal excess return | Hard block | benchmark source hash / timestamp / license 不稳定 |
| formal adjusted return | Hard block | qfq / adj_factor revision 和 PIT 无法证明 |
| execution-realistic backtest | Hard block | execution flags lineage 和再分发边界不稳定 |

可选方案：

| 方案 | 动作 | 成本 | 风险 | 适用条件 |
| --- | --- | --- | --- | --- |
| A：补 Tushare 权限/积分 | 不是单纯权限问题；需补 Tushare 授权 memo、archive policy、redaction policy | 中 | 只补积分不能解决再分发/PIT/长期保留 | 仍以 Tushare 作为 P1-A MVP 候选 |
| B：换源或多源交叉验证 | 选择合同更清晰的机构源，并建立统一 archive / report 规范 | 中到高 | 采购更贵；仍需 repo redaction 规范 | 需要 P1-B 稳健路线 |
| C：继续 internal research-only 降级 | 暂不保存外部 raw response；不进入 adapter | 低 | 无法升级 formal；但合规风险最低 | 长期规范未拍板 |

推荐决策：

- 先制定长期规范，再谈 adapter。
- 最低规范应覆盖：raw archive 私有位置、保留期限、访问权限、hash 算法、request/response timestamp、params fingerprint、redacted report 入库范围、raw vendor data 禁入清单、token 轮换、license note。
- 在长期规范未批准前，任何 Tushare POC 结果只能作为本地临时研究，不得进入正式 adapter 决策。

## 4. 推荐执行顺序

非生产 POC 的 blocker 处理建议顺序：

1. 先处理 token 安全和长期规范。
2. 再处理 `trade_cal`，因为 calendar 是 benchmark、price 和 execution 的共同对齐基础。
3. 再处理 `index_daily`，解除 formal excess return 的最大外部 blocker。
4. 再处理 `pro_bar` qfq / adj_factor，解除 formal adjusted return blocker。
5. 再处理 `stk_limit` 和 `suspend_d`，用于 execution flags hardening。
6. 任一 blocker 失败时，写入 redacted blocker report，并保持对应能力 unavailable / research-only。

## 5. 最终建议

当前不应因为任何一个 blocker 的“可能可解”而提前接主线代码。

推荐路径：

- 安全和授权 blocker 未解前：保持 internal benchmark research-only。
- `index_daily` 未解前：formal excess return unavailable。
- qfq / adj_factor 未解前：formal adjusted return unavailable。
- `stk_limit` / `suspend_d` 未解前：execution-realistic backtest unavailable。
- `trade_cal` 未解前：所有 formal / execution 对齐都只能 report-only。

只有当权限、成本、授权、raw archive、redacted report 和字段 coverage 都通过后，才允许单独开正式 adapter 设计卡；即使开卡，也仍不得直接写 `packages/quant`、不得写 `data/quant`、不得提交 raw vendor data，除非另有明确人工审批和开发边界。
