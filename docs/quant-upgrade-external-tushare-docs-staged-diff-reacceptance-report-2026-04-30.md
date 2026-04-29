# Prism 量化升级 PR 2 External / Tushare Docs Staged Diff 复验报告

Date: 2026-04-30
Role: independent staged-diff reacceptance reviewer
Scope: current staged diff only
Status: passed

## 0. 复验边界

本次只读复验当前 staged diff：

- `git diff --cached --name-status`
- `git diff --cached --stat`
- `git diff --cached --check`
- staged path allow/deny 检查
- staged index blob token / secret / raw vendor data 检查
- staged docs non-production / docs-only / no-adapter / no-formal-output guardrail 检查

本次未 stage，未 commit，未修改 staged 内容。

## 1. 总体验收结论

结论：**通过**。

上一轮唯一阻塞项已修复：

- `docs/quant-upgrade-tushare-poc-plan-2026-04-29.md` 中不再存在 `TUSHARE_TOKEN=` 形式。
- 原占位赋值示例已改为纯文字安全说明：只使用名为 `TUSHARE_TOKEN` 的本地环境变量，且不得打印、记录、写入文档或提交其值。

当前 staged diff 满足 PR 2 docs-only 边界。

## 2. Staged Diff 摘要

当前 staged diff：

- staged 文件数：20。
- diff 统计：`20 files changed, 6070 insertions(+)`。
- 路径范围：全部为 `docs/quant-upgrade*.md`。
- `git diff --cached --check`：通过。

staged 文件均为新增 Markdown 文档，没有代码、数据、图片或 vendor archive 文件。

## 3. Path Boundary 检查

| 检查项 | 结果 | 说明 |
| --- | --- | --- |
| staged diff 全部 docs-only | 通过 | 20 个 staged 文件全部为 `.md`。 |
| 只包含 `docs/quant-upgrade*.md` | 通过 | 未发现其他路径。 |
| 无 `packages/*` | 通过 | staged path 未命中。 |
| 无 `data/*` | 通过 | staged path 未命中。 |
| 无 `apps/*` | 通过 | staged path 未命中。 |
| 无 `stock-screener/*` | 通过 | staged path 未命中。 |
| 无 `stock-analyzer/*` | 通过 | staged path 未命中。 |
| 无 raw vendor data 文件 | 通过 | 无 JSON/CSV/JSONL/parquet/archive/raw response 文件 staged。 |
| 无账号截图 / 积分截图 | 通过 | 无 png/jpg/jpeg/gif/webp 等图片文件 staged。 |

备注：`git status --short` 显示工作区仍有未 staged 的 `apps/*`、`stock-screener/*`、`stock-analyzer/*` 和 runtime/cache 数据；这些不在当前 staged diff 内。

## 4. `TUSHARE_TOKEN` 复验

重点检查：

- `git show :docs/quant-upgrade-tushare-poc-plan-2026-04-29.md | rg -n 'TUSHARE_TOKEN\\s*='`

结果：**无命中**。

当前相关段落为纯文字说明：

- 使用名为 `TUSHARE_TOKEN` 的本地环境变量。
- 不打印、不记录、不写入文档、不提交 token 值。
- 不放入 `packages/quant`、`data/quant` 或任何 repo 内文件。

验收意见：通过。

## 5. Token / Secret / Raw Vendor 检查

| 检查项 | 结果 | 说明 |
| --- | --- | --- |
| 真实 token / secret | 通过 | staged index blob 未发现真实 token、API key、password、bearer token 或常见 secret pattern。 |
| assignment-like token 示例 | 通过 | 不再发现 `TUSHARE_TOKEN=`；`ts.set_token` / `pro_api` 仅出现在“未发现硬编码风险”的验收描述中。 |
| raw vendor data | 通过 | 未发现行级 OHLC、adj_factor、calendar、limit、suspend 或 stock_basic 明细数据进入 staged diff。 |
| raw response body | 通过 | 文档多次说明不得提交 raw response；未发现 raw response payload。 |
| 账号截图 / 积分截图 | 通过 | 仅作为禁止项或未检查项文字出现，无实际图片或余额明细。 |

## 6. Repo 外 Archive 检查

`.prism-private` / `tushare-poc/raw` 仅作为 repo 外路径说明和私有 archive policy 出现，例如：

- repo 外 raw archive 路径说明；
- raw response 只保存在 repo 外；
- repo 内只能有 hash、row_count、field list 等 redacted 摘要；
- raw vendor data 不得进入 repo。

未发现 `.prism-private` / `tushare-poc/raw` 对应的 raw 数据文件被 staged。

验收意见：通过。

## 7. Non-Production / Docs-Only Guardrails

staged docs 仍明确以下边界：

- Tushare POC / source design 仅为 non-production availability / source design。
- 当前 PR 2 为 docs-only。
- 不写 `packages/quant`。
- 不写 `data/quant`。
- 不实现 adapter。
- 不调用 API。
- 不生成 formal labels。
- 不生成 formal excess return。
- 不生成 formal adjusted return。
- 不生成 execution-realistic backtest。
- 不接生产排序。
- 不替换 A/B/C。
- 不做页面、Prism Edge、Expected 5D 默认展示或 ML。

验收意见：通过。

## 8. 最终裁决

当前 PR 2 docs-only staged diff：**通过复验**。

允许作为 **external / Tushare docs-only** 提交继续后续流程。

提交前仍建议保留两条操作纪律：

1. 继续使用精确 pathspec，避免把当前未 staged 的 apps / stock / runtime cache 数据混入。
2. 不使用 `git add .`，不提交任何 raw vendor data、token、secret、账号截图或积分截图。
