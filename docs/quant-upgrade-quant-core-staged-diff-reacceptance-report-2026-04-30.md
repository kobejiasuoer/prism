# Prism 量化升级 Quant Core Staged Diff 复验报告

Date: 2026-04-30
Role: independent staged-diff reacceptance reviewer
Scope: staged diff only
Status: passed

## 0. 复验边界

本次只读复验当前 staged diff：

- `git diff --cached --name-status`
- `git diff --cached --stat`
- `git diff --cached --check`
- staged path deny-list 检查
- staged blob token / secret / raw vendor data 检查
- `data/quant` report-only / research-only 标记检查
- quant test run

本次未 stage，未 commit，未修改 staged 内容。

## 1. 总体验收结论

结论：**通过**。

上一轮阻塞项已修复：

1. 3 个 meta docs 已从 staged diff 移除。
2. `git diff --cached --check` 已通过，无 whitespace error。

当前 staged diff 符合 **Quant report-only core + P1-A internal hardening** 范围。

## 2. Staged Diff 摘要

当前 staged diff：

- staged 文件数：59。
- top-level 分布：`data` 23、`docs` 16、`packages` 13、`tests` 7。
- diff 统计：`59 files changed, 77753 insertions(+)`。

staged 内容范围：

- `packages/quant/*.py`
- `tests/test_quant_sprint*.py`
- `tests/test_quant_p1a_*.py`
- `data/config/quant-research.json`
- `data/quant/**`
- P0 / Sprint 2 / P1-A internal hardening docs and independent acceptance reports

备注：`git status --short` 显示工作区仍有未 staged 的 `apps/*`、`stock-screener/*`、`stock-analyzer/*`、Tushare / external docs 等文件，但这些不在当前 staged diff 内，本次只验收 staged diff。

## 3. Meta Docs 移除确认

以下 3 个文件均未出现在 staged diff：

- `docs/quant-upgrade-change-inventory-acceptance-report-2026-04-30.md`
- `docs/quant-upgrade-change-inventory-and-commit-plan-2026-04-30.md`
- `docs/quant-upgrade-stage-pathspec-plan-2026-04-30.md`

结论：**通过**。

## 4. Path Boundary 检查

| 检查项 | 结果 | 说明 |
| --- | --- | --- |
| 只包含 Quant report-only core + P1-A internal hardening | 通过 | staged 路径集中在 `packages/quant`、quant tests、`data/quant`、quant docs。 |
| 无 `docs/quant-upgrade-tushare*.md` | 通过 | staged path 未命中。 |
| 无 `docs/quant-upgrade-external*.md` | 通过 | staged path 未命中。 |
| 无 `apps/*` | 通过 | staged path 未命中。 |
| 无 `stock-screener/*` | 通过 | staged path 未命中。 |
| 无 `stock-analyzer/*` | 通过 | staged path 未命中。 |
| 无 `__pycache__` / `*.pyc` | 通过 | staged path 未命中。 |

## 5. Diff Hygiene

`git diff --cached --check`：**通过**。

未发现：

- trailing whitespace
- space-before-tab
- new blank line at EOF

## 6. Token / Secret / Raw Vendor Data 检查

| 检查项 | 结果 | 说明 |
| --- | --- | --- |
| token / secret / api key 明文 | 通过 | staged blob 扫描未发现疑似明文凭证或 assignment 形态。 |
| `TUSHARE_TOKEN` / Tushare token | 通过 | staged blob 未发现 token；`tushare` 仅在两个 P1-A 验收报告中作为“未外部抓取”的文本说明出现。 |
| raw vendor data | 通过 | 未发现 row-level vendor raw response 或 vendor raw archive 文件进入 staged diff。 |
| repo 外 raw archive | 通过 | 未发现 `.prism-private`、`tushare-poc/raw` 等 repo 外 raw archive 路径进入 staged diff。 |

## 7. `data/quant` Report-Only 检查

`data/quant` staged 内容为 generated research artifacts，包括：

- baselines / panels / eligible universe snapshot
- forward labels and hardened labels
- benchmark returns and manifests
- price / execution manifests
- report-only factor / backtest / quant health reports

关键 staged 证据：

- `data/config/quant-research.json` 使用 `p0-research-only` profile，并声明 `production_sorting_impact: forbidden`。
- `data/quant/reports/quant_health_latest.md` 声明 `Overall status: report_only_hardened_not_production_ready`、`Production impact: none`、`Sorting impact: false`、`A/B/C replacement: false`。
- `data/quant/reports/portfolio_backtest_latest.md` 声明 backtest 为 `report-only minimal backtest`，不是 execution-realistic backtest，且不改变 production sorting。
- hardened labels 中 `formal_label_ready=false`、`formal_execution_eligible=false`，并包含 `no_formal_excess_return`、`no_execution_realistic_return`、`no_production_sorting`、`no_abc_replacement`、`no_page`、`no_prism_edge`、`no_expected_5d_frontend`、`no_ml` guardrails。

大文件提示：

- `data/quant/labels/forward_return_labels_hardened.jsonl` 约 43M。
- `data/quant/labels/forward_return_labels.jsonl` 约 15M。
- `data/quant/panels/daily_signal_panel.jsonl` 约 7.4M。

验收意见：这些仍应按 generated research artifacts 管理；本次 staged diff 语义上保持 report-only / research-only。

## 8. Production / Product Boundary 检查

| 检查项 | 结果 | 说明 |
| --- | --- | --- |
| 生产排序 | 通过 | staged 命中均为禁止影响或 `production_impact: none`。 |
| A/B/C 替换 | 通过 | staged 命中均为 guardrail / 禁止替换。 |
| 页面 | 通过 | 无 staged `apps/*` 或 frontend 路径；页面相关命中为 guardrail。 |
| Prism Edge | 通过 | 无产品化实现；命中为 guardrail。 |
| Expected 5D | 通过 | 无前端展示；命中为 guardrail。 |
| ML | 通过 | 无 ML 实现；命中为 guardrail。 |

## 9. 测试结果

运行命令：

```bash
./.venv/bin/pytest tests/test_quant_sprint1.py tests/test_quant_sprint2.py tests/test_quant_p1a_adjusted_price.py tests/test_quant_p1a_benchmarks.py tests/test_quant_p1a_execution_flags.py tests/test_quant_p1a_label_hardening.py tests/test_quant_p1a_rerun_reports.py
```

结果：**41 passed in 10.48s**。

## 10. 最终裁决

当前 Quant core staged diff：**通过复验**。

允许作为 **Quant report-only core + P1-A internal hardening** 这一组进入后续提交/PR 流程。

提交前仍建议保留两条人工确认：

1. owner 确认 `data/quant` 大型 generated JSONL artifacts 入库策略。
2. 提交时继续使用精确 pathspec，避免把当前未 staged 的 Tushare / external docs、apps、stock-screener、stock-analyzer、runtime data 混入。
