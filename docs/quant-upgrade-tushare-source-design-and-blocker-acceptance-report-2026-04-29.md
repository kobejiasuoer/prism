# Prism 量化升级 Tushare Source Design / Blocker Matrix 独立验收报告

Date: 2026-04-29
Role: independent acceptance reviewer
Scope: Tushare docs-only source design and blocker decision acceptance
Status: conditional pass

## 0. 验收边界

本次只读检查：

- `docs/quant-upgrade-tushare-nonproduction-source-design-2026-04-29.md`
- `docs/quant-upgrade-tushare-poc-blocker-decision-matrix-2026-04-29.md`
- `docs/quant-upgrade-master-progress-and-handoff-2026-04-29.md`
- `docs/quant-upgrade-tushare-poc-result-2026-04-29.md`
- `docs/quant-upgrade-tushare-poc-acceptance-report-2026-04-29.md`
- 当前 `git status`
- 当前 `git diff`

本次验收没有调用 Tushare API，没有读取 repo 外 raw vendor archive，没有写业务代码，没有修改 `packages/quant`，没有写 `data/quant`，没有覆盖既有 POC 结果。

## 1. 总体验收结论

结论：**有条件通过**。

是否允许进入下一阶段：**有条件允许**。

下一阶段只允许：

- 人工拍板 `trade_cal` / `index_daily` / `stk_limit` 权限、积分、费用和调用频率。
- 人工拍板 `suspend_d` 字段修复路线或换源路线。
- 人工拍板 `pro_bar` SDK-mediated 非生产验证是否值得做。
- 人工拍板继续 Tushare、换源 / 多源，或继续 internal research-only 降级。
- 继续写 docs-only decision / source design / acceptance checklist。

下一阶段仍不允许：

- 不允许写 `packages/quant`。
- 不允许写 `data/quant`。
- 不允许实现 Tushare adapter。
- 不允许提交 raw vendor data。
- 不允许生成 formal labels、formal adjusted return、formal excess return 或 execution-realistic backtest。
- 不允许接生产排序、A/B/C、页面、Prism Edge、Expected 5D 或 ML。

有条件通过的原因：文档内容符合 docs-only 和 non-production 边界；但当前工作区不是干净的 docs-only 状态，`git status` 仍显示 `data/quant/` 和 `packages/quant/` 为 untracked，另有大量与本轮 Tushare docs 无关的修改。后续提交或交接必须严格隔离，仅包含获批的 Tushare docs-only 产物。

## 2. 交付物完整性

| 检查项 | 结果 | 验收意见 |
| --- | --- | --- |
| nonproduction source design 存在 | 通过 | 文档声明 non-production source design only，production impact none。 |
| blocker decision matrix 存在 | 通过 | 文档声明 blocker decision matrix only，不执行 POC，不写代码。 |
| master progress handoff 存在 | 通过 | 已同步 POC completed with blockers、token 轮换、旧 token 禁用、后续只读 `TUSHARE_TOKEN`。 |
| POC result 存在 | 通过 | 记录 POC result: completed with blockers。 |
| POC acceptance report 存在 | 通过 | 结论为有条件通过，并限制只能有限继续。 |
| 输出验收报告 | 通过 | 本文件为新增验收报告。 |

## 3. Docs-only / Repo 边界检查

| 检查项 | 结果 | 验收意见 |
| --- | --- | --- |
| 本轮是否只做 docs-only | 有条件通过 | 待验收 Tushare 产物均为 `docs/` 文档；但整仓工作区存在大量非 docs 修改，不能用当前工作区直接证明全局 docs-only。 |
| 是否修改 `packages/quant` | 有条件通过 | 当前 tracked diff 对 `packages/quant` 无输出；但 `git status` 显示 `packages/quant/` 为 untracked。不得纳入本轮提交。 |
| 是否写 `data/quant` | 有条件通过 | 当前 tracked diff 对 `data/quant` 无输出；但 `git status` 显示 `data/quant/` 为 untracked。不得纳入本轮提交。 |
| 是否提交 raw vendor data | 通过 | Tushare 相关 repo 路径只看到 docs 文件；POC result 只列 endpoint、字段名、row_count、hash、状态，不含行级 vendor 数据。 |
| 是否覆盖 POC result | 通过 | 本次验收未覆盖 POC result；只读检查后新增本验收报告。 |

提交边界要求：如果后续要提交本轮 Tushare docs-only 产物，必须只选择相关 `docs/quant-upgrade-tushare-*.md` 和必要 handoff 文档；不得夹带 `packages/quant/`、`data/quant/` 或任何 unrelated dirty files。

## 4. Token / Secret 检查

| 检查项 | 结果 | 验收意见 |
| --- | --- | --- |
| token 是否进入代码 / tracked diff | 通过 | tracked diff 的 Tushare / token / secret 关键词扫描未发现 Tushare token hardcode。 |
| token 是否进入目标文档 | 通过 | 目标文档仅出现 `TUSHARE_TOKEN` 环境变量名、token 管理说明和禁用事项；未发现 token 明文。 |
| token-like 字符串 | 通过，需注意 | 目标文档中的长串主要为 SHA256 response hash、文档路径或状态词；未发现 plain secret 形态。 |
| `ts.set_token` / `pro_api` / assignment 风险 | 通过 | 这些字符串只出现在旧验收报告的“未发现/硬编码风险检查”语境中，不是可执行代码或实际 token assignment。 |
| 新 token 是否已轮换 | 文档层面通过 | handoff 明确写明 Tushare token 已人工轮换，旧 token 不再允许使用。独立验收未接触 secret store，无法技术验证轮换事实。 |
| 后续 token 读取方式 | 通过 | handoff 明确后续如需调用 Tushare，只能从本地环境变量 `TUSHARE_TOKEN` 读取，且不得写入代码、文档、日志或 git。 |

继续前人工硬条件：由 token owner 私下确认新 token 可用、旧 token 已停用或不可再用；确认过程不得把 token 值写入 repo、日志、报告或聊天。

## 5. Source Design 验收

| 检查项 | 结果 | 验收意见 |
| --- | --- | --- |
| scope 是否只围绕 `daily` | 通过 | source design 将 `daily` 限定为 raw/source-observed OHLCV，用于 research-only price availability checks。 |
| scope 是否只围绕 `adj_factor` | 通过 | source design 将 `adj_factor` 限定为 future adjustment-policy validation 输入，不升级 formal adjusted return。 |
| scope 是否只围绕 `stock_basic` | 通过 | source design 将 `stock_basic` 限定为 security master / identifier diagnostics，不替换 eligible universe 或 A/B/C。 |
| 是否排除 blocked interfaces | 通过 | `trade_cal`、`index_daily`、`stk_limit`、`suspend_d`、`pro_bar` 均列为 out of scope，直到权限和字段覆盖解决。 |
| 是否升级 formal labels | 通过 | 明确不能生成或暗示 formal labels。 |
| 是否升级 formal adjusted return | 通过 | 明确 `adj_factor` alone 不足以 formal；qfq / policy / PIT / license 仍未通过。 |
| 是否升级 formal excess return | 通过 | 明确 `index_daily` blocked，因此不能生成 formal market excess return。 |
| 是否升级 execution-realistic backtest | 通过 | 明确 `stk_limit`、`suspend_d` 等阻塞仍存在。 |

验收判断：source design 的边界是正确的。它是 source-observed / research-only 的设计笔记，不是 adapter implementation approval。

## 6. Blocker Matrix 验收

| Blocker | 是否明确阻塞影响 | 验收意见 |
| --- | --- | --- |
| `trade_cal` 权限/积分 | 通过 | 标记为 formal labels、excess、adjusted、execution 对齐的 partial block，并建议先补权限或换源 / 多源交叉验证。 |
| `index_daily` 权限/积分 | 通过 | 明确 formal excess return 的 hard block；不能用 internal equal-weight 冒充 CSI500 / HS300。 |
| `stk_limit` 权限/积分 | 通过 | 明确 execution-realistic backtest 的 hard block；不能用 OHLC 静默替代 source-provided limit。 |
| `suspend_d` 字段不完整 | 通过 | 明确 execution-realistic backtest 的 hard block；需确认日级状态或换源。 |
| `pro_bar` SDK-mediated 验证 | 通过 | 明确 formal adjusted return 的 hard block；未通过前 adjusted return unavailable。 |
| token 已暴露需轮换 | 通过 | blocker matrix 将其列为全部 formal / execution 能力的 hard block。 |
| raw archive / redacted report / 授权长期规范 | 通过 | 明确未建立长期规范前不得进入 adapter。 |

验收判断：blocker matrix 没有弱化阻塞项，也没有把“可能可解”写成“已经可用”。

## 7. Formal / Production 禁止项

| 禁止项 | 结果 | 验收意见 |
| --- | --- | --- |
| 生产排序 | 通过 | 所有相关文档继续禁止。 |
| A/B/C 替换 | 通过 | `stock_basic` 明确不得替换 Prism eligible universe 或 A/B/C。 |
| 页面 | 通过 | 继续禁止。 |
| Prism Edge | 通过 | 继续禁止。 |
| Expected 5D | 通过 | 继续禁止默认展示或产品化。 |
| ML | 通过 | 继续禁止。 |
| production-ready wording | 通过 | 文档持续标记 report-only / research-only / non-production。 |

## 8. Git Status / Git Diff 风险

当前工作区观察：

- `git status` 显示大量与本轮 Tushare docs-only 无关的 modified / untracked 文件。
- `data/quant/` 当前为 untracked。
- `packages/quant/` 当前为 untracked。
- tracked diff 对 `packages/quant` / `data/quant` 无输出，但未跟踪目录仍是提交风险。
- tracked diff 的 selected secret keyword scan 未发现 Tushare token / secret 关键词命中。
- long token-like tracked diff 命中出现在非 Tushare 相关文件，未作为本轮 Tushare docs blocker；提交前仍建议由对应 owner 独立处理。

验收解释：本轮 Tushare docs-only 产物本身可以有条件通过；当前整仓工作区不能被视为干净的 docs-only 变更集。

## 9. 人工拍板 Blocker

下一阶段前必须由人工拍板：

1. 是否补 Tushare `trade_cal` 权限/积分，或改用官方休市公告 + 授权源 cross-check。
2. 是否补 Tushare `index_daily` 权限/积分，或换 CSI500 / HS300 benchmark 授权源。
3. 是否补 Tushare `stk_limit` 权限/积分，或换具备涨跌停字段的数据源。
4. `suspend_d` 是否能通过更高权限、正确字段或其他 endpoint 解决；否则是否换源。
5. 是否执行 SDK-mediated `pro_bar` qfq/hfq 非生产验证。
6. 是否继续 Tushare、走多源，或维持 internal research-only 降级。
7. 新 token 轮换事实、权限范围、积分/费用、调用频率和授权边界。
8. raw archive 私有路径、保留期限、访问权限、删除机制和 redacted report 入库范围。

## 10. 最终裁决

Tushare docs-only source design / blocker matrix 验收结论：**有条件通过**。

允许进入下一阶段：**有条件允许**，但下一阶段只能是人工决策和 docs-only design / decision work。

不允许进入：

- adapter implementation。
- `packages/quant` 修改。
- `data/quant` 写入。
- raw vendor data 入库。
- formal labels / formal adjusted return / formal excess return。
- execution-realistic backtest。
- 生产排序、A/B/C、页面、Prism Edge、Expected 5D、ML。

推荐下一步：先由人工拍板 token、权限、积分/费用、授权、raw archive，以及 `trade_cal` / `index_daily` / `stk_limit` / `suspend_d` / `pro_bar` 的补权限或换源路线；在这些 blocker 关闭前，Prism 继续保持 report-only / research-only / internal degradation。
