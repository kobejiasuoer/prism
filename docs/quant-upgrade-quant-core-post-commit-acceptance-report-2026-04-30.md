# Prism 量化升级 Quant Core Post-Commit 独立验收报告

Date: 2026-04-30
Role: independent post-commit acceptance reviewer
Scope: `HEAD` commit content only, plus current `git status --short`
Status: passed

## 0. 验收边界

本次只读检查：

- `git show --name-status --stat HEAD`
- `git show --stat --oneline HEAD`
- `git status --short`
- HEAD commit path deny-list 检查
- HEAD commit token / secret / raw vendor data 检查
- `data/quant` report-only / research-only 证据检查
- quant tests

本次未 stage，未 commit，未修改业务代码或数据。

## 1. Commit 摘要

HEAD:

- Commit: `1ef4614e1753d9f7776b53d6a6b588ee62ed15aa`
- Subject: `quant: add report-only research spine and p1a hardening`
- Author: `杨 <1448950074@qq.com>`
- Date: `2026-04-30T00:55:16+08:00`

Commit 统计：

- 59 files changed
- 77753 insertions(+)
- top-level 分布：`data` 23、`docs` 16、`packages` 13、`tests` 7

## 2. 总体验收结论

结论：**通过**。

HEAD commit 内容只包含 **Quant report-only core + P1-A internal hardening**：

- `packages/quant/*.py`
- quant tests
- `data/config/quant-research.json`
- `data/quant/**` generated research artifacts / report-only outputs
- P0 / Sprint 2 / P1-A internal hardening docs and acceptance reports

未发现 Tushare docs、external docs、apps、stock-screener、stock-analyzer、pycache、token、secret 或 raw vendor data 进入 HEAD commit。

## 3. `git status --short` 检查

当前工作区 **不是 clean**。

`git status --short` 仍显示大量未提交或未跟踪文件，包括：

- `apps/*`
- `stock-screener/*`
- `stock-analyzer/*`
- Tushare / external docs
- 前序 staged diff 验收报告

这些文件 **不在 HEAD commit 内**。针对本次 commit 范围的检查：

- `packages/quant`
- `data/quant`
- `data/config/quant-research.json`
- quant test files

均未显示 post-commit 未提交修改。

验收意见：HEAD commit 内容通过；后续提交仍需继续使用精确 pathspec，避免把当前 dirty worktree 中的无关文件混入。

## 4. Path Boundary 检查

| 检查项 | HEAD commit 结果 | 说明 |
| --- | --- | --- |
| 只包含 Quant report-only core + P1-A internal hardening | 通过 | commit 路径集中在 `data`、`docs`、`packages/quant`、`tests/test_quant*`。 |
| 无 `docs/quant-upgrade-tushare*.md` | 通过 | commit path 未命中。 |
| 无 `docs/quant-upgrade-external*.md` | 通过 | commit path 未命中。 |
| 无 `apps/*` | 通过 | commit path 未命中。 |
| 无 `stock-screener/*` | 通过 | commit path 未命中。 |
| 无 `stock-analyzer/*` | 通过 | commit path 未命中。 |
| 无 `__pycache__` / `*.pyc` | 通过 | commit path 未命中。 |

## 5. Token / Secret / Raw Vendor Data 检查

| 检查项 | 结果 | 说明 |
| --- | --- | --- |
| token / secret / api key 明文 | 通过 | HEAD commit 文件集未发现疑似凭证 assignment 或常见 secret pattern。 |
| Tushare token | 通过 | 未发现 `TUSHARE_TOKEN` 或 token-like 字符串。 |
| Tushare docs | 通过 | 未提交 `docs/quant-upgrade-tushare*.md`。 |
| Raw vendor data | 通过 | 未发现 raw response、repo 外 raw archive 或 vendor raw dump。 |

备注：HEAD 中两个 P1-A acceptance docs 出现 `tushare` 字样，仅作为“代码未出现外部抓取”的验收描述，不是 Tushare POC 文档、token 或接入代码。

## 6. `data/quant` Report-Only 检查

`data/quant` 在 HEAD 中仍是 generated research artifacts / report-only：

- `data/config/quant-research.json` 使用 `p0-research-only` profile，并声明 `production_sorting_impact: forbidden`。
- `data/quant/reports/quant_health_latest.md` 声明 `Overall status: report_only_hardened_not_production_ready`、`Production impact: none`、`Sorting impact: false`、`A/B/C replacement: false`。
- `data/quant/reports/portfolio_backtest_latest.md` 声明 backtest 为 report-only minimal backtest，不是 execution-realistic backtest，不改变 production sorting。
- hardened labels 中 `formal_label_ready=false`、`formal_execution_eligible=false`，并包含 `no_formal_excess_return`、`no_execution_realistic_return`、`no_production_sorting`、`no_abc_replacement`、`no_page`、`no_prism_edge`、`no_expected_5d_frontend`、`no_ml` guardrails。

验收意见：通过。

## 7. Production / Product Boundary

| 检查项 | 结果 | 说明 |
| --- | --- | --- |
| 生产排序 | 通过 | HEAD 中相关内容均为 forbidden / none / guardrail。 |
| A/B/C 替换 | 通过 | HEAD 中相关内容均为禁止替换或 status false。 |
| 页面 | 通过 | 无 `apps/*` commit；页面相关内容仅为 guardrail。 |
| Prism Edge | 通过 | 无产品化实现；相关内容仅为 guardrail。 |
| Expected 5D | 通过 | 无前端展示；相关内容仅为 guardrail。 |
| ML | 通过 | 无 ML 实现；相关内容仅为 guardrail。 |

## 8. 测试结果

运行命令：

```bash
./.venv/bin/pytest tests/test_quant_sprint1.py tests/test_quant_sprint2.py tests/test_quant_p1a_adjusted_price.py tests/test_quant_p1a_benchmarks.py tests/test_quant_p1a_execution_flags.py tests/test_quant_p1a_label_hardening.py tests/test_quant_p1a_rerun_reports.py
```

结果：**41 passed in 9.92s**。

## 9. 最终裁决

HEAD commit：**通过 post-commit 验收**。

允许将 `1ef4614e1753d9f7776b53d6a6b588ee62ed15aa` 作为 **Quant report-only core + P1-A internal hardening** commit 继续后续流程。

保留事项：

1. 当前工作区 dirty，且包含 Tushare / external docs、apps、stock-screener、stock-analyzer 等未提交内容；这些不属于本 commit。
2. 后续任何 stage / commit 必须继续使用精确 pathspec，禁止 `git add .`。
