# Prism 量化升级 Stage Pathspec Plan 独立验收报告

Date: 2026-04-30
Role: independent acceptance reviewer
Scope: stage pathspec plan acceptance only
Status: conditional pass

## 0. 验收边界

本次验收只读检查：

- `docs/quant-upgrade-stage-pathspec-plan-2026-04-30.md`
- 当前 `git status`
- 当前 `git diff` 的脱敏风险摘要

本次未 stage，未 commit，未清理工作区，未修改 `packages/quant` 或 `data/quant`。

## 1. 总体验收结论

结论：**有条件通过**。

该 pathspec plan 已经足够作为安全 staging 操作的执行参考：明确禁止全量 add，给出 PR A / B / C 的精确 allowlist 和 denylist，并为每组提供 `git diff --cached` 检查命令。

有条件通过的唯一主要保留项：`data/quant` 大型 JSONL / generated artifacts 被列入 PR A / B allowlist，但本文件没有再次明确“必须先由 owner 拍板是否提交大文件，或改用外部 artifact storage”。执行 pathspec 前应补充或口头确认该策略。

## 2. `git add .` 禁令

| 检查项 | 结果 | 验收意见 |
| --- | --- | --- |
| 是否明确禁止 `git add .` | 通过 | 硬规则和最终提醒均明确写出严禁 `git add .`。 |
| 是否禁止其他全量 add | 通过 | 同时禁止 `git add -A` 和 `git add -u`。 |
| 是否禁止误操作修复 | 通过 | 文档要求 cached diff 出现未列路径时停止提交并人工确认，不自行 `git reset` 或删除文件。 |

## 3. 三组 PR / Commit 边界

| 分组 | 结果 | 验收意见 |
| --- | --- | --- |
| PR A / Commit A | 通过 | 边界为 P0 + Sprint 0-2，包含 Sprint 代码、测试、配置、Sprint reports/data 和 P0/Sprint 文档；明确排除 P1-A unique modules、Tushare docs、apps、stock-analyzer、stock-screener。 |
| PR B / Commit B | 通过 | 边界为 P1-A Card 1-5，包含 P1-A unique code、测试、artifacts、docs；对 shared code / rerun reports 标为 conditional，说明 pathspec 无法严格拆行级历史。 |
| PR C / Commit C | 通过 | 边界为 Tushare docs-only，allowlist 只包含 `docs/quant-upgrade-tushare*.md`。 |
| Meta docs | 通过 | 将 change inventory / acceptance / pathspec plan 作为独立 meta commit 或人工确认后附加。 |

## 4. PR C Docs-only 检查

结果：**通过**。

PR C 明确：

- 只提交 Tushare POC / source design / blocker 文档。
- 不包含 `packages/quant`。
- 不包含 `data/quant`。
- 不包含 `data/config/quant-research.json`。
- 不包含 tests。
- 不包含 apps / stock-analyzer / stock-screener。
- 不包含 repo 外 raw archive。
- 不包含 token。

PR C 的提交前检查命令也能验证 staged 文件是否全部匹配 `^docs/quant-upgrade-tushare.*\.md$`。

## 5. Raw Vendor / Token / Repo 外 Archive 排除

| 检查项 | 结果 | 验收意见 |
| --- | --- | --- |
| raw vendor data | 通过 | 通用检查和 PR C 明确排除 raw vendor data / raw response body / row-level vendor data。 |
| repo 外 raw archive | 通过 | 明确排除 `~/.prism-private/tushare-poc/`。 |
| token / API key / secret | 通过 | 明确排除 token / API key / account secret，并提供 `TUSHARE_TOKEN` 精确扫描脚本。 |
| token-like 字符串 | 通过 | 允许安全引用变量名和 policy text，但要求不得出现 token 值或行级 vendor data。 |

本次只读核验未发现 tracked diff 中有 Tushare / token / secret 关键词命中文件。

## 6. 运行态 / 无关数据排除

| 路径类别 | 结果 | 验收意见 |
| --- | --- | --- |
| `apps/data` | 通过 | 通用检查与 Excluded 总清单明确排除。 |
| `apps/reports` / app code | 通过 | Excluded 总清单排除 app reports、control panel、web、canonical 脚本等无关路径。 |
| `stock-screener/data` | 通过 | 通用检查、PR checks、Excluded 总清单均排除。 |
| `stock-analyzer/data` | 通过 | 通用检查、PR checks、Excluded 总清单均排除。 |
| cache/runtime | 通过 | 明确排除 `__pycache__`、`*.pyc`、runtime cache、current-state JSON、scan stale outputs。 |

当前工作区确实仍有大量上述运行态 / 无关数据修改，pathspec plan 对这些路径的排除是必要且正确的。

## 7. `data/quant` 大文件策略

结果：**有条件通过**。

正确之处：

- PR A / B 对 `data/quant` 路径做了精确 allowlist，而不是目录级 add。
- PR A / B 分别列出哪些 `data/quant` artifacts 属于 Sprint 0-2 或 P1-A。
- PR C 明确排除全部 `data/quant`。
- 检查命令可以阻止非本组 `data/quant` 文件混入 staged diff。

保留项：

- 本文件没有再次写明 `data/quant/**/*.jsonl`、`forward_return_labels_hardened.jsonl` 等大型 generated artifacts 必须先由 owner 人工确认是否提交。
- 本文件没有再次列出“若不接受大文件，应提交 manifests/reports，并将 JSONL 外置 artifact storage”的替代策略。

执行前要求：

- 在运行 PR A / B pathspec 前，必须先沿用 change inventory 的人工确认结论：是否允许提交 `data/quant` 大型 generated artifacts。
- 若 owner 未拍板，大型 JSONL 不应进入 staged diff。

## 8. 提交前检查命令

结果：**通过**。

文档为每组提供了可执行检查：

- 通用 `git status --short`。
- 通用 `git diff --cached --name-status`。
- `find packages/quant` 检查 `*.pyc` 和 `__pycache__`。
- raw archive / token policy grep。
- `TUSHARE_TOKEN` 精确扫描脚本，且不打印 token 值。
- 每组 `git diff --cached --name-only | rg -v ...` allowlist 反查。
- PR C non-doc / non-Tushare staged blocker 检查。
- Sprint / P1-A 对应 pytest 命令。

这些命令足以在 stage 后发现错误路径。

## 9. 最终裁决

`docs/quant-upgrade-stage-pathspec-plan-2026-04-30.md` 验收结论：**有条件通过**。

允许作为 staging 执行参考，但执行前必须先确认：

1. owner 已拍板 `data/quant` 大型 generated artifacts 是否提交。
2. 如不提交大文件，需从 PR A / B pathspec 中移除对应 JSONL。
3. 每次 stage 后必须运行 `git diff --cached --name-status` 和对应 allowlist 反查命令。
4. 继续严禁 `git add .`、`git add -A`、`git add -u`。

本次验收未 stage、未 commit、未修改代码或数据目录。
