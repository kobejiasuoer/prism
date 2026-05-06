# Prism 量化升级 Quant Core Staged Diff 独立验收报告

Date: 2026-04-30
Role: independent staged-diff acceptance reviewer
Scope: staged diff review only
Status: failed

## 0. 验收边界

本次只读检查当前 staged diff：

- `git diff --cached --name-status`
- `git diff --cached --stat`
- staged path allow/deny 检查
- staged content token / raw vendor / product-scope 脱敏扫描
- staged whitespace check
- quant test run

本次未 stage，未 commit，未修改 staged 内容。

## 1. 总体验收结论

结论：**不通过**。

核心原因：

1. 当前 staged diff 不只包含 Quant report-only core + P1-A internal hardening，还混入了 3 个 meta docs。
2. `git diff --cached --check` 失败，3 个 staged docs 存在 `new blank line at EOF`。

测试结果：**通过**，使用 `./.venv/bin/pytest` 跑 7 个 quant 测试文件，共 41 项通过。

## 2. Staged Diff 摘要

当前 staged diff：

- staged 文件数：62。
- top-level 分布：`data` 23、`docs` 19、`packages` 13、`tests` 7。
- 变更统计：`79123 insertions(+)`。

staged 主要内容：

- `packages/quant/*.py`
- `tests/test_quant_sprint*.py`
- `tests/test_quant_p1a_*.py`
- `data/config/quant-research.json`
- `data/quant/**`
- P0 / Sprint / P1-A 文档

## 3. 路径边界检查

| 检查项 | 结果 | 验收意见 |
| --- | --- | --- |
| 只包含 Quant core + P1-A internal hardening | 不通过 | staged 中包含 3 个 meta docs，不属于本组业务提交范围。 |
| 无 `docs/quant-upgrade-tushare*.md` | 通过 | 未发现 staged Tushare docs。 |
| 无 `docs/quant-upgrade-external*.md` | 通过 | 未发现 staged external docs。 |
| 无 `apps/*` | 通过 | 未发现 staged app 路径。 |
| 无 `stock-screener/*` | 通过 | 未发现 staged stock-screener 路径。 |
| 无 `stock-analyzer/*` | 通过 | 未发现 staged stock-analyzer 路径。 |
| 无 `__pycache__` / `*.pyc` | 通过 | 未发现 staged pycache 或 pyc。 |

不应出现在本组 staged diff 的 meta docs：

- `docs/quant-upgrade-change-inventory-acceptance-report-2026-04-30.md`
- `docs/quant-upgrade-change-inventory-and-commit-plan-2026-04-30.md`
- `docs/quant-upgrade-stage-pathspec-plan-2026-04-30.md`

这些应放入单独 meta docs commit，或下一轮另行验收。

## 4. Secret / Raw Vendor 检查

| 检查项 | 结果 | 验收意见 |
| --- | --- | --- |
| token / secret 明文 | 通过 | 未发现真实 token、secret、api key assignment 形态。 |
| `TUSHARE_TOKEN` 字符串 | 有条件通过 | 仅出现在 3 个 meta docs 中，作为变量名 / 扫描说明；移除 meta docs 后本组 staged diff 不应再包含该字符串。 |
| raw vendor data | 通过 | 未发现 row-level vendor data 或 raw response body。 |
| repo 外 raw archive 引用 | 有条件通过 | `.prism-private` / `tushare-poc/raw` 仅出现在 meta docs 的排除说明中；移除 meta docs 后本组 staged diff 不应包含这些引用。 |

## 5. `data/quant` 检查

| 检查项 | 结果 | 验收意见 |
| --- | --- | --- |
| 是否只在 `data/quant` 下提交量化研究产物 | 通过 | staged data 路径均为 `data/config` 或 `data/quant`。 |
| 是否为 generated research artifacts | 通过 | 包含 manifests、panels、labels、benchmark returns、execution/price manifests 和 reports。 |
| 是否标记 report-only / research-only | 通过，需说明 | reports / manifests / labels 中大量包含 `report-only`、`research-only`、`research_only`、formal false、unavailable 等状态。panel / ledger 本身为研究输入 artifact，不逐行带 report-only 文案。 |
| 大文件策略 | 有条件通过 | staged 包含 `forward_return_labels_hardened.jsonl` 约 45.6MB、`forward_return_labels.jsonl` 约 16.1MB、`daily_signal_panel.jsonl` 约 7.7MB；需确认 owner 已接受 generated JSONL 入库。 |

## 6. Product / Production 边界

| 检查项 | 结果 | 验收意见 |
| --- | --- | --- |
| 生产排序 | 通过 | staged 中相关命中为 guardrail / 禁止影响 / production impact none，不是生产排序接入。 |
| A/B/C | 通过 | 相关命中为禁止替换或上下文说明。 |
| 页面 / Prism Edge / Expected 5D / ML | 通过 | 未 stage `apps/*` 或产品路径；相关命中为 guardrail 文案和 report-only health 字段。 |

## 7. Whitespace / Diff Check

`git diff --cached --check`：**失败**。

失败项：

- `docs/quant-upgrade-p1-data-hardening-plan-2026-04-28.md:471: new blank line at EOF`
- `docs/quant-upgrade-p1a-card2-adjusted-price-implementation-plan-2026-04-28.md:424: new blank line at EOF`
- `docs/quant-upgrade-p1a-source-inventory-and-implementation-plan-2026-04-28.md:510: new blank line at EOF`

这些问题需要在 staged diff 通过前修复或重新 stage 修正版本。

## 8. 测试结果

第一次尝试：

- `pytest ...` 失败，原因：当前 shell 中 `pytest` 命令不存在。
- `python3 -m pytest ...` 失败，原因：系统 Python 未安装 pytest。

最终使用仓库虚拟环境：

```bash
./.venv/bin/pytest tests/test_quant_sprint1.py tests/test_quant_sprint2.py tests/test_quant_p1a_adjusted_price.py tests/test_quant_p1a_benchmarks.py tests/test_quant_p1a_execution_flags.py tests/test_quant_p1a_label_hardening.py tests/test_quant_p1a_rerun_reports.py
```

结果：**41 passed in 10.51s**。

## 9. 必须修复项

在 staged diff 重新验收前，必须：

1. 从当前 staged diff 中移除 3 个 meta docs：
   - `docs/quant-upgrade-change-inventory-acceptance-report-2026-04-30.md`
   - `docs/quant-upgrade-change-inventory-and-commit-plan-2026-04-30.md`
   - `docs/quant-upgrade-stage-pathspec-plan-2026-04-30.md`
2. 修复 3 个 staged docs 的 EOF blank line 问题。
3. 重新运行 `git diff --cached --name-status`，确认只剩 Quant report-only core + P1-A internal hardening。
4. 重新运行 `git diff --cached --check`。
5. 确认 owner 已接受 `data/quant` 大型 generated JSONL 入库策略。

## 10. 最终裁决

当前 staged diff：**不通过**。

不通过不是因为测试失败；测试已通过。阻塞点是 staged 范围和 staged diff hygiene：

- staged 范围混入 meta docs；
- staged diff 存在 EOF whitespace error。

修复后可重新验收。
