# Prism 量化升级变更盘点文档独立验收报告

Date: 2026-04-30
Role: independent acceptance reviewer
Scope: change inventory and commit plan acceptance only
Status: conditional pass

## 0. 验收边界

本次验收只读检查：

- `docs/quant-upgrade-change-inventory-and-commit-plan-2026-04-30.md`
- 当前 `git status --short`
- 当前 `git diff --stat`
- 当前 `git diff` 的脱敏 secret / token / raw archive 风险摘要

本次未 stage，未 commit，未清理工作区，未调用外部 API，未修改 `packages/quant` 或 `data/quant`。

## 1. 总体验收结论

结论：**有条件通过**。

盘点文档整体可作为提交隔离和 PR 拆分依据。它正确识别了当前工作区很脏、量化升级变更与运行态 / cache / 无关修改混在一起，并给出了可执行的 Commit A / B / C 与三 PR 拆分方案。

有条件通过的主要保留项：

- 文档写明“未运行 `git add`”，也建议使用 patch-level staging，但没有把 **禁止 `git add .`** 写成明确硬规则。
- `data/quant` 大型 generated artifacts 是否提交仍需要 owner 人工拍板。
- 当前工作区仍包含大量无关 modified / untracked 文件，提交时必须按文档隔离，不得直接从当前状态整体提交。

## 2. 工作区只读核对

当前观察：

- `git status --short` 显示大量 modified / untracked 文件。
- tracked diff 统计仍为 `177 files changed, 54371 insertions(+), 8802 deletions(-)`。
- `packages/quant/` 当前为 untracked。
- `data/quant/` 当前为 untracked。
- `data/config/quant-research.json` 当前为 untracked。
- `tests/test_quant*.py` 当前为 untracked。
- `docs/quant-upgrade-change-inventory-and-commit-plan-2026-04-30.md` 当前为 untracked。

验收解释：盘点文档对当前脏工作区的判断与只读核对一致。

## 3. 分类准确性检查

| 检查项 | 结果 | 验收意见 |
| --- | --- | --- |
| 代码分类 | 通过 | 文档将 `packages/quant/*.py` 分为 Sprint 0-2 与 P1-A 两组，并指出 shared files 需要 patch-level staging 或接受最终实现说明。 |
| 测试分类 | 通过 | 文档将 `tests/test_quant_sprint*.py` 与 `tests/test_quant_p1a_*.py` 分别归入 Commit A / B。 |
| docs 分类 | 通过 | 文档区分 P0/Sprint、P1-A、Tushare docs-only 和 meta inventory 文档。 |
| data 分类 | 通过 | 文档区分 `data/config`、`data/quant` research artifacts、runtime/current-state 数据和外部 raw archive。 |
| runtime/cache 分类 | 通过 | 明确排除 `__pycache__`、`*.pyc`、state JSON、scan result、stale output、cache files。 |
| 无关修改分类 | 通过 | 将 `apps/*`、`stock-analyzer/*`、`stock-screener/data/*` 标为默认不纳入量化 PR，需人工确认。 |

## 4. `data/quant` / `packages/quant` 边界

| 检查项 | 结果 | 验收意见 |
| --- | --- | --- |
| `packages/quant` 提交边界 | 通过 | 明确提交 `.py` 源码，不提交 `__pycache__` / `*.pyc`，并要求 PR 说明 report-only、不影响生产排序。 |
| `data/quant` 提交边界 | 通过 | 明确 manifests / reports 更适合提交，JSONL 大文件需人工确认或外置 artifact storage。 |
| 大文件风险 | 通过 | 明确 `data/quant` 约 72M，hardened labels 约 43M，raw labels 约 15M，panel 约 7.4M。 |
| generated data 策略 | 有条件通过 | 文档提出两种策略，但需要仓库 owner 最终拍板。 |

## 5. Raw Vendor Data 风险

| 检查项 | 结果 | 验收意见 |
| --- | --- | --- |
| raw vendor data 风险识别 | 通过 | 文档明确不提交 repo 外 Tushare raw archive、private summary、raw response、行级行情、完整交易日历、账号截图、积分余额截图。 |
| repo 内 raw archive 路径扫描 | 通过 | 文档记录 repo 内未发现 `tushare-poc/raw` 或 `.prism-private` 路径；本次只读扫描只命中相关 docs 的路径说明，不是 raw data 文件。 |
| Tushare docs-only 边界 | 通过 | Commit C 明确 docs-only，不纳入 `packages/quant`、`data/quant` 或 raw vendor data。 |

## 6. Token / Token-like 风险

| 检查项 | 结果 | 验收意见 |
| --- | --- | --- |
| token 风险是否识别 | 通过 | 文档有专门的 Token-like 字符串检查章节。 |
| 精确 token scan | 文档层面通过 | 文档声称对当前 `TUSHARE_TOKEN` 可见 token 做了精确 repo 扫描且结果 clean；本次验收未读取 token 值，无法独立复验精确 token。 |
| token-like hash 解释 | 通过 | 文档区分 `TUSHARE_TOKEN` 变量名、response SHA256、params fingerprint、source hash 与真实 token。 |
| 安全提醒 | 通过 | 明确 Tushare token 曾进入聊天上下文，即使 repo clean，也建议轮换后再进入长期接入或 adapter 开发。 |
| 当前 tracked diff secret 关键词 | 通过 | 本次只读扫描未发现 tracked diff 中有 Tushare / token / secret 关键词命中文件。 |

## 7. `git add .` 风险

结果：**有条件通过**。

文档优点：

- 明确本次未运行 `git add`。
- 推荐 Commit A / B / C 分组。
- 对 shared files 建议 `git add -p` 或重新生成阶段补丁。
- 明确排除 runtime/cache/raw vendor/unrelated data。

不足：

- 文档没有明确写出“禁止 `git add .`”或“不得用全量 add 提交当前工作区”。

必须补强建议：

- 在提交前检查清单中新增硬规则：`严禁 git add .`。
- 要求使用显式路径、pathspec、`git add -p` 或临时 clean branch 重放。
- 要求 `git diff --cached --name-status` 只包含对应 commit / PR 的允许路径。

## 8. Commit / PR 拆分方案

| 检查项 | 结果 | 验收意见 |
| --- | --- | --- |
| Commit A | 通过 | P0 / Sprint quant package + tests，目标清楚。 |
| Commit B | 通过 | P1-A hardening reports/tests，目标清楚。 |
| Commit C | 通过 | Tushare docs-only，边界清楚。 |
| PR 拆分 | 通过 | 推荐三 PR，比单 PR 三 commit 更利于 review。 |
| shared files 风险 | 通过 | 明确 `evaluate_factors.py`、`run_portfolio_backtest.py`、`report_quant_health.py`、`research_io.py` 跨阶段重叠，需要 patch-level staging 或说明最终实现。 |
| generated artifacts 风险 | 通过 | 明确若仓库 owner 接受大文件可提交，否则转外部 artifact storage。 |

## 9. 人工确认清单

文档已明确需要人工确认：

- 是否提交 `data/quant/**/*.jsonl` 大型 generated artifacts。
- 是否提交较大的 manifest，例如 `data/quant/price/price_adjustment_manifest.json`。
- `apps/*`、`stock-analyzer/scripts/fetch.py`、`stock-analyzer/config/stocks.json` 是否属于另一任务。
- `stock-screener/data/research_backfill/*` 是否为有意 source artifact normalization。
- 是否拆多个 PR。
- Tushare token 是否已轮换。

验收判断：人工确认清单充分，且与当前工作区风险匹配。

## 10. 最终裁决

`docs/quant-upgrade-change-inventory-and-commit-plan-2026-04-30.md` 验收结论：**有条件通过**。

允许作为下一步提交隔离依据，但进入实际 stage / commit 前必须先补两点：

1. 明确硬禁令：**禁止 `git add .`**。
2. 由人工拍板 `data/quant` 大型 generated artifacts、无关 app/stock 数据、Tushare token 轮换状态。

实际提交时必须继续遵守：

- 不 stage / commit raw vendor data。
- 不 stage / commit token、账号截图、积分余额截图。
- 不把 runtime/cache/current-state 数据混入量化 PR。
- 不把 Tushare docs-only 与 adapter/code/data 混在同一 commit。
- 每个 commit 前检查 `git diff --cached --name-status`。
