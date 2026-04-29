# Prism 量化升级精确 Stage Pathspec 清单

Date: 2026-04-30
Scope: staging plan only
Status: no `git add`, no commit, no cleanup performed

## 0. 硬规则

严禁执行：

- `git add .`
- `git add -A`
- `git add -u`
- `git commit`
- `git clean`
- `git reset`
- 删除文件或恢复文件

本文件只给出可复制的精确 pathspec 清单。执行 staging 前必须先人工确认当前工作区仍与盘点时一致。

重要限制：

- 当前工作区是 Sprint 2 + P1-A Card 1-5 的最终态。
- `packages/quant/evaluate_factors.py`、`packages/quant/run_portfolio_backtest.py`、`packages/quant/report_quant_health.py`、`packages/quant/research_io.py` 和部分 `data/quant/reports/*` 已经包含 P1-A Card 5 hardening sidecar 展示逻辑。
- 如果要求 Commit A 与 Commit B 严格按历史语义拆分，单纯 pathspec 不够，必须使用 `git add -p`、阶段快照分支，或重新从 Sprint 2 checkpoint 生成补丁。
- 下方清单是当前工作区的精确文件 allowlist，不使用目录级 `git add`。

## 1. 通用提交前检查

每次 stage 前先运行：

```bash
git status --short
git diff --cached --name-status
find packages/quant -type f -name '*.pyc' -print
find packages/quant -type d -name '__pycache__' -print
rg -n 'tushare-poc/raw|\\.prism-private|raw vendor|TUSHARE_TOKEN' docs packages data tests
```

如果本地仍有 `TUSHARE_TOKEN`，提交前做精确 token 扫描，不打印 token 值：

```bash
python3 - <<'PY'
from pathlib import Path
import subprocess
token = (subprocess.run(["launchctl", "getenv", "TUSHARE_TOKEN"], capture_output=True, text=True).stdout or "").strip()
if not token:
    print("EXACT_TUSHARE_TOKEN_SCAN=not_run_token_not_visible")
    raise SystemExit
matches = []
for p in Path(".").rglob("*"):
    if ".git" in p.parts or "node_modules" in p.parts or ".next" in p.parts:
        continue
    if p.is_file():
        try:
            if token.encode() in p.read_bytes():
                matches.append(str(p))
        except Exception:
            pass
print("EXACT_TUSHARE_TOKEN_SCAN=" + ("found" if matches else "clean"))
for m in matches:
    print(m)
PY
```

任何 commit 前都必须确认：

- `git diff --cached --name-status` 只包含本组 allowlist；
- 没有 `packages/quant/__pycache__/*`；
- 没有 `*.pyc`；
- 没有 `apps/data/*`；
- 没有 `stock-screener/data/*`；
- 没有 `stock-analyzer/data/*`；
- 没有 repo 外 raw vendor data；
- 没有 token 明文。

## 2. PR A / Commit A: P0 + Sprint 0-2

目标：

- Sprint 0 baseline / field contracts；
- Sprint 1 research panel / labels；
- Sprint 2 report-only factor evaluation / minimal backtest / quant health；
- 不包含 P1-A unique hardening modules；
- 不包含 Tushare docs。

### 2.1 允许 stage 的精确文件路径

代码：

```text
packages/quant/__init__.py
packages/quant/build_research_panel.py
packages/quant/config.py
packages/quant/evaluate_factors.py
packages/quant/paths.py
packages/quant/report_quant_health.py
packages/quant/research_io.py
packages/quant/run_portfolio_backtest.py
packages/quant/schemas.py
```

测试：

```text
tests/test_quant_sprint1.py
tests/test_quant_sprint2.py
```

配置：

```text
data/config/quant-research.json
```

Sprint 0-2 data / report artifacts：

```text
data/quant/baselines/quant_baseline_manifest.json
data/quant/labels/forward_return_labels.jsonl
data/quant/ledgers/pipeline_stage_ledger.jsonl
data/quant/panels/daily_signal_panel.jsonl
data/quant/panels/eligible_universe_snapshot.jsonl
data/quant/reports/factor_evaluation_latest.md
data/quant/reports/field_mapping_audit_latest.md
data/quant/reports/label_coverage_latest.md
data/quant/reports/panel_coverage_latest.md
data/quant/reports/portfolio_backtest_latest.md
data/quant/reports/price_execution_audit_latest.md
data/quant/reports/quant_health_latest.json
data/quant/reports/quant_health_latest.md
```

P0 / Sprint 文档：

```text
docs/quant-upgrade-design-2026-04-27.md
docs/quant-upgrade-p0-execution-flow-2026-04-28.md
docs/quant-upgrade-p0-review-revision-2026-04-28.md
docs/quant-upgrade-task-breakdown-2026-04-28.md
docs/quant-upgrade-sprint2-acceptance-checklist-2026-04-28.md
docs/quant-upgrade-sprint2-acceptance-report-2026-04-28.md
```

Exact stage command template, do not run until ready:

```bash
git add -- \
  packages/quant/__init__.py \
  packages/quant/build_research_panel.py \
  packages/quant/config.py \
  packages/quant/evaluate_factors.py \
  packages/quant/paths.py \
  packages/quant/report_quant_health.py \
  packages/quant/research_io.py \
  packages/quant/run_portfolio_backtest.py \
  packages/quant/schemas.py \
  tests/test_quant_sprint1.py \
  tests/test_quant_sprint2.py \
  data/config/quant-research.json \
  data/quant/baselines/quant_baseline_manifest.json \
  data/quant/labels/forward_return_labels.jsonl \
  data/quant/ledgers/pipeline_stage_ledger.jsonl \
  data/quant/panels/daily_signal_panel.jsonl \
  data/quant/panels/eligible_universe_snapshot.jsonl \
  data/quant/reports/factor_evaluation_latest.md \
  data/quant/reports/field_mapping_audit_latest.md \
  data/quant/reports/label_coverage_latest.md \
  data/quant/reports/panel_coverage_latest.md \
  data/quant/reports/portfolio_backtest_latest.md \
  data/quant/reports/price_execution_audit_latest.md \
  data/quant/reports/quant_health_latest.json \
  data/quant/reports/quant_health_latest.md \
  docs/quant-upgrade-design-2026-04-27.md \
  docs/quant-upgrade-p0-execution-flow-2026-04-28.md \
  docs/quant-upgrade-p0-review-revision-2026-04-28.md \
  docs/quant-upgrade-task-breakdown-2026-04-28.md \
  docs/quant-upgrade-sprint2-acceptance-checklist-2026-04-28.md \
  docs/quant-upgrade-sprint2-acceptance-report-2026-04-28.md
```

### 2.2 明确禁止 stage 的路径

```text
packages/quant/__pycache__/
packages/quant/*.pyc
packages/quant/build_benchmark_returns.py
packages/quant/execution_flags.py
packages/quant/price_adjustment_policy.py
packages/quant/upgrade_forward_labels.py
tests/test_quant_p1a_adjusted_price.py
tests/test_quant_p1a_benchmarks.py
tests/test_quant_p1a_execution_flags.py
tests/test_quant_p1a_label_hardening.py
tests/test_quant_p1a_rerun_reports.py
data/quant/benchmarks/
data/quant/execution/
data/quant/labels/forward_return_labels_hardened.jsonl
data/quant/price/
data/quant/reports/benchmark_coverage_latest.md
data/quant/reports/execution_flags_coverage_latest.md
data/quant/reports/label_hardening_latest.md
data/quant/reports/price_adjustment_policy_latest.md
docs/quant-upgrade-p1*.md
docs/quant-upgrade-external*.md
docs/quant-upgrade-master-progress-and-handoff-2026-04-29.md
docs/quant-upgrade-tushare*.md
apps/
stock-analyzer/
stock-screener/
```

### 2.3 提交前必须运行的检查命令

```bash
git diff --cached --name-status
git diff --cached --name-only | rg -v '^(packages/quant/(__init__|build_research_panel|config|evaluate_factors|paths|report_quant_health|research_io|run_portfolio_backtest|schemas)\\.py|tests/test_quant_sprint[12]\\.py|data/config/quant-research\\.json|data/quant/(baselines/quant_baseline_manifest\\.json|labels/forward_return_labels\\.jsonl|ledgers/pipeline_stage_ledger\\.jsonl|panels/(daily_signal_panel|eligible_universe_snapshot)\\.jsonl|reports/(factor_evaluation_latest|field_mapping_audit_latest|label_coverage_latest|panel_coverage_latest|portfolio_backtest_latest|price_execution_audit_latest|quant_health_latest)\\.(md|json))|docs/quant-upgrade-(design-2026-04-27|p0-execution-flow-2026-04-28|p0-review-revision-2026-04-28|task-breakdown-2026-04-28|sprint2-acceptance-checklist-2026-04-28|sprint2-acceptance-report-2026-04-28)\\.md)$' || true
pytest tests/test_quant_sprint1.py tests/test_quant_sprint2.py
```

第二条命令应无输出；如有输出，说明 cached 中存在不属于 Commit A 的文件。

### 2.4 `git diff --cached --name-status` 应该 / 不应该出现

应该只出现：

- `A packages/quant/...` 上述 9 个 Sprint 代码文件；
- `A tests/test_quant_sprint1.py`；
- `A tests/test_quant_sprint2.py`；
- `A data/config/quant-research.json`；
- `A data/quant/baselines/...`、`A data/quant/panels/...`、`A data/quant/labels/forward_return_labels.jsonl`、`A data/quant/ledgers/...`；
- `A data/quant/reports/...` Sprint 0-2 报告；
- `A docs/quant-upgrade-...` P0 / Sprint 文档。

不应该出现：

- `packages/quant/__pycache__/*`
- `packages/quant/build_benchmark_returns.py`
- `packages/quant/execution_flags.py`
- `packages/quant/price_adjustment_policy.py`
- `packages/quant/upgrade_forward_labels.py`
- `tests/test_quant_p1a_*.py`
- `data/quant/benchmarks/*`
- `data/quant/execution/*`
- `data/quant/price/*`
- `data/quant/labels/forward_return_labels_hardened.jsonl`
- `docs/quant-upgrade-tushare*.md`
- any `apps/*`、`stock-analyzer/*`、`stock-screener/*`

## 3. PR B / Commit B: P1-A Card 1-5

目标：

- Benchmark manifest / returns；
- adjusted price policy；
- execution flags；
- label hardening；
- rerun Sprint 2 reports using hardened labels；
- 仍然 report-only / research-only。

### 3.1 允许 stage 的精确文件路径

P1-A unique code：

```text
packages/quant/build_benchmark_returns.py
packages/quant/execution_flags.py
packages/quant/price_adjustment_policy.py
packages/quant/upgrade_forward_labels.py
```

P1-A shared code, conditional：

```text
packages/quant/evaluate_factors.py
packages/quant/report_quant_health.py
packages/quant/research_io.py
packages/quant/run_portfolio_backtest.py
```

说明：

- 如果 Commit A 已经用 pathspec stage 了这些 shared code 的最终版本，Commit B 不会再有这些文件可 stage。
- 如果要 Commit B 独立承载 Card 5 对 shared code 的修改，必须使用 `git add -p` 或从 Sprint 2 checkpoint 重放 P1-A patch；不能只靠 pathspec 精确拆行级历史。

测试：

```text
tests/test_quant_p1a_adjusted_price.py
tests/test_quant_p1a_benchmarks.py
tests/test_quant_p1a_execution_flags.py
tests/test_quant_p1a_label_hardening.py
tests/test_quant_p1a_rerun_reports.py
```

P1-A artifacts：

```text
data/quant/benchmarks/benchmark_manifest.json
data/quant/benchmarks/benchmark_returns.jsonl
data/quant/execution/execution_flags_manifest.json
data/quant/labels/forward_return_labels_hardened.jsonl
data/quant/price/price_adjustment_manifest.json
data/quant/reports/benchmark_coverage_latest.md
data/quant/reports/execution_flags_coverage_latest.md
data/quant/reports/label_hardening_latest.md
data/quant/reports/price_adjustment_policy_latest.md
```

P1-A final rerun reports, conditional：

```text
data/quant/reports/factor_evaluation_latest.md
data/quant/reports/portfolio_backtest_latest.md
data/quant/reports/quant_health_latest.json
data/quant/reports/quant_health_latest.md
```

说明：

- 如果 Commit A 已 stage 当前最终版本的这些 report，则 Commit B 不应再 stage 它们。
- 如果 Commit A 要保持纯 Sprint 2 报告，应先恢复或重建 Sprint 2-only 版本，再把当前 hardened rerun 版本留给 Commit B。

P1-A docs / acceptance：

```text
docs/quant-upgrade-p1-data-hardening-plan-2026-04-28.md
docs/quant-upgrade-p1a-card1-benchmark-acceptance-report-2026-04-28.md
docs/quant-upgrade-p1a-card2-adjusted-price-acceptance-report-2026-04-28.md
docs/quant-upgrade-p1a-card2-adjusted-price-implementation-plan-2026-04-28.md
docs/quant-upgrade-p1a-card3-execution-flags-acceptance-report-2026-04-29.md
docs/quant-upgrade-p1a-card4-label-hardening-acceptance-report-2026-04-29.md
docs/quant-upgrade-p1a-card5-rerun-reports-acceptance-report-2026-04-29.md
docs/quant-upgrade-p1a-decision-matrix-2026-04-28.md
docs/quant-upgrade-p1a-external-data-source-research-2026-04-29.md
docs/quant-upgrade-p1a-hardening-acceptance-checklist-2026-04-28.md
docs/quant-upgrade-p1a-source-inventory-and-implementation-plan-2026-04-28.md
docs/quant-upgrade-external-data-source-decision-pack-2026-04-29.md
docs/quant-upgrade-external-poc-readiness-acceptance-report-2026-04-29.md
docs/quant-upgrade-master-progress-and-handoff-2026-04-29.md
```

Exact stage command template, do not run until ready:

```bash
git add -- \
  packages/quant/build_benchmark_returns.py \
  packages/quant/execution_flags.py \
  packages/quant/price_adjustment_policy.py \
  packages/quant/upgrade_forward_labels.py \
  tests/test_quant_p1a_adjusted_price.py \
  tests/test_quant_p1a_benchmarks.py \
  tests/test_quant_p1a_execution_flags.py \
  tests/test_quant_p1a_label_hardening.py \
  tests/test_quant_p1a_rerun_reports.py \
  data/quant/benchmarks/benchmark_manifest.json \
  data/quant/benchmarks/benchmark_returns.jsonl \
  data/quant/execution/execution_flags_manifest.json \
  data/quant/labels/forward_return_labels_hardened.jsonl \
  data/quant/price/price_adjustment_manifest.json \
  data/quant/reports/benchmark_coverage_latest.md \
  data/quant/reports/execution_flags_coverage_latest.md \
  data/quant/reports/label_hardening_latest.md \
  data/quant/reports/price_adjustment_policy_latest.md \
  docs/quant-upgrade-p1-data-hardening-plan-2026-04-28.md \
  docs/quant-upgrade-p1a-card1-benchmark-acceptance-report-2026-04-28.md \
  docs/quant-upgrade-p1a-card2-adjusted-price-acceptance-report-2026-04-28.md \
  docs/quant-upgrade-p1a-card2-adjusted-price-implementation-plan-2026-04-28.md \
  docs/quant-upgrade-p1a-card3-execution-flags-acceptance-report-2026-04-29.md \
  docs/quant-upgrade-p1a-card4-label-hardening-acceptance-report-2026-04-29.md \
  docs/quant-upgrade-p1a-card5-rerun-reports-acceptance-report-2026-04-29.md \
  docs/quant-upgrade-p1a-decision-matrix-2026-04-28.md \
  docs/quant-upgrade-p1a-external-data-source-research-2026-04-29.md \
  docs/quant-upgrade-p1a-hardening-acceptance-checklist-2026-04-28.md \
  docs/quant-upgrade-p1a-source-inventory-and-implementation-plan-2026-04-28.md \
  docs/quant-upgrade-external-data-source-decision-pack-2026-04-29.md \
  docs/quant-upgrade-external-poc-readiness-acceptance-report-2026-04-29.md \
  docs/quant-upgrade-master-progress-and-handoff-2026-04-29.md
```

Conditional stage command for Card 5 shared final-state files, only if they were not staged in Commit A:

```bash
git add -- \
  packages/quant/evaluate_factors.py \
  packages/quant/report_quant_health.py \
  packages/quant/research_io.py \
  packages/quant/run_portfolio_backtest.py \
  data/quant/reports/factor_evaluation_latest.md \
  data/quant/reports/portfolio_backtest_latest.md \
  data/quant/reports/quant_health_latest.json \
  data/quant/reports/quant_health_latest.md
```

### 3.2 明确禁止 stage 的路径

```text
packages/quant/__pycache__/
packages/quant/*.pyc
tests/test_quant_sprint1.py
tests/test_quant_sprint2.py
data/quant/baselines/
data/quant/labels/forward_return_labels.jsonl
data/quant/ledgers/
data/quant/panels/
data/quant/reports/field_mapping_audit_latest.md
data/quant/reports/label_coverage_latest.md
data/quant/reports/panel_coverage_latest.md
data/quant/reports/price_execution_audit_latest.md
docs/quant-upgrade-tushare*.md
apps/
stock-analyzer/
stock-screener/
```

### 3.3 提交前必须运行的检查命令

```bash
git diff --cached --name-status
git diff --cached --name-only | rg -v '^(packages/quant/(build_benchmark_returns|execution_flags|price_adjustment_policy|upgrade_forward_labels|evaluate_factors|report_quant_health|research_io|run_portfolio_backtest)\\.py|tests/test_quant_p1a_(adjusted_price|benchmarks|execution_flags|label_hardening|rerun_reports)\\.py|data/quant/(benchmarks/(benchmark_manifest\\.json|benchmark_returns\\.jsonl)|execution/execution_flags_manifest\\.json|labels/forward_return_labels_hardened\\.jsonl|price/price_adjustment_manifest\\.json|reports/(benchmark_coverage_latest|execution_flags_coverage_latest|label_hardening_latest|price_adjustment_policy_latest|factor_evaluation_latest|portfolio_backtest_latest|quant_health_latest)\\.(md|json))|docs/quant-upgrade-(p1-data-hardening-plan-2026-04-28|p1a-card1-benchmark-acceptance-report-2026-04-28|p1a-card2-adjusted-price-acceptance-report-2026-04-28|p1a-card2-adjusted-price-implementation-plan-2026-04-28|p1a-card3-execution-flags-acceptance-report-2026-04-29|p1a-card4-label-hardening-acceptance-report-2026-04-29|p1a-card5-rerun-reports-acceptance-report-2026-04-29|p1a-decision-matrix-2026-04-28|p1a-external-data-source-research-2026-04-29|p1a-hardening-acceptance-checklist-2026-04-28|p1a-source-inventory-and-implementation-plan-2026-04-28|external-data-source-decision-pack-2026-04-29|external-poc-readiness-acceptance-report-2026-04-29|master-progress-and-handoff-2026-04-29)\\.md)$' || true
pytest tests/test_quant_p1a_adjusted_price.py tests/test_quant_p1a_benchmarks.py tests/test_quant_p1a_execution_flags.py tests/test_quant_p1a_label_hardening.py tests/test_quant_p1a_rerun_reports.py
```

第二条命令应无输出；如有输出，说明 cached 中存在不属于 Commit B 的文件。

### 3.4 `git diff --cached --name-status` 应该 / 不应该出现

应该出现：

- `A packages/quant/build_benchmark_returns.py`
- `A packages/quant/execution_flags.py`
- `A packages/quant/price_adjustment_policy.py`
- `A packages/quant/upgrade_forward_labels.py`
- `A tests/test_quant_p1a_*.py`
- `A data/quant/benchmarks/*`
- `A data/quant/execution/*`
- `A data/quant/price/*`
- `A data/quant/labels/forward_return_labels_hardened.jsonl`
- `A data/quant/reports/benchmark_coverage_latest.md`
- `A data/quant/reports/execution_flags_coverage_latest.md`
- `A data/quant/reports/label_hardening_latest.md`
- `A data/quant/reports/price_adjustment_policy_latest.md`
- P1-A docs listed above.

视 Commit A staging 策略，可能出现 shared / rerun files：

- `A packages/quant/evaluate_factors.py`
- `A packages/quant/report_quant_health.py`
- `A packages/quant/research_io.py`
- `A packages/quant/run_portfolio_backtest.py`
- `A data/quant/reports/factor_evaluation_latest.md`
- `A data/quant/reports/portfolio_backtest_latest.md`
- `A data/quant/reports/quant_health_latest.json`
- `A data/quant/reports/quant_health_latest.md`

不应该出现：

- `docs/quant-upgrade-tushare*.md`
- any `apps/*`
- any `stock-analyzer/*`
- any `stock-screener/*`
- any `packages/quant/__pycache__/*`
- any `*.pyc`
- repo 外 raw vendor data

## 4. PR C / Commit C: Tushare docs-only

目标：

- 只提交 Tushare POC / source design / blocker 文档；
- 不包含任何 quant package；
- 不包含任何 `data/quant`；
- 不包含 raw vendor data；
- 不包含 token。

### 4.1 允许 stage 的精确文件路径

```text
docs/quant-upgrade-tushare-field-availability-matrix-2026-04-29.md
docs/quant-upgrade-tushare-nonproduction-source-design-2026-04-29.md
docs/quant-upgrade-tushare-poc-acceptance-checklist-2026-04-29.md
docs/quant-upgrade-tushare-poc-acceptance-report-2026-04-29.md
docs/quant-upgrade-tushare-poc-blocker-decision-matrix-2026-04-29.md
docs/quant-upgrade-tushare-poc-plan-2026-04-29.md
docs/quant-upgrade-tushare-poc-result-2026-04-29.md
docs/quant-upgrade-tushare-poc-runbook-2026-04-29.md
docs/quant-upgrade-tushare-source-design-and-blocker-acceptance-report-2026-04-29.md
```

Exact stage command template, do not run until ready:

```bash
git add -- \
  docs/quant-upgrade-tushare-field-availability-matrix-2026-04-29.md \
  docs/quant-upgrade-tushare-nonproduction-source-design-2026-04-29.md \
  docs/quant-upgrade-tushare-poc-acceptance-checklist-2026-04-29.md \
  docs/quant-upgrade-tushare-poc-acceptance-report-2026-04-29.md \
  docs/quant-upgrade-tushare-poc-blocker-decision-matrix-2026-04-29.md \
  docs/quant-upgrade-tushare-poc-plan-2026-04-29.md \
  docs/quant-upgrade-tushare-poc-result-2026-04-29.md \
  docs/quant-upgrade-tushare-poc-runbook-2026-04-29.md \
  docs/quant-upgrade-tushare-source-design-and-blocker-acceptance-report-2026-04-29.md
```

### 4.2 明确禁止 stage 的路径

```text
packages/quant/
data/quant/
data/config/quant-research.json
tests/test_quant*.py
docs/quant-upgrade-p0*.md
docs/quant-upgrade-p1*.md
docs/quant-upgrade-sprint2*.md
docs/quant-upgrade-external*.md
docs/quant-upgrade-master-progress-and-handoff-2026-04-29.md
apps/
stock-analyzer/
stock-screener/
/Users/yangbishang/.prism-private/tushare-poc/
```

### 4.3 提交前必须运行的检查命令

```bash
git diff --cached --name-status
git diff --cached --name-only | rg -v '^docs/quant-upgrade-tushare.*\\.md$' || true
git diff --cached --name-only | rg '^(packages/quant|data/quant|data/config/quant-research\\.json|tests/test_quant|apps/|stock-analyzer/|stock-screener/)' && echo 'BLOCKED: non-doc or non-Tushare file staged' || true
rg -n 'tushare-poc/raw|\\.prism-private|raw response body|TUSHARE_TOKEN' docs/quant-upgrade-tushare*.md
```

Expected notes:

- First `rg -v` command should return no files.
- Second `rg` command should return no staged files.
- Third `rg` may find safe references to variable name `TUSHARE_TOKEN` and private-path policy text, but must not show token values or row-level vendor data.

### 4.4 `git diff --cached --name-status` 应该 / 不应该出现

应该只出现：

- `A docs/quant-upgrade-tushare-field-availability-matrix-2026-04-29.md`
- `A docs/quant-upgrade-tushare-nonproduction-source-design-2026-04-29.md`
- `A docs/quant-upgrade-tushare-poc-acceptance-checklist-2026-04-29.md`
- `A docs/quant-upgrade-tushare-poc-acceptance-report-2026-04-29.md`
- `A docs/quant-upgrade-tushare-poc-blocker-decision-matrix-2026-04-29.md`
- `A docs/quant-upgrade-tushare-poc-plan-2026-04-29.md`
- `A docs/quant-upgrade-tushare-poc-result-2026-04-29.md`
- `A docs/quant-upgrade-tushare-poc-runbook-2026-04-29.md`
- `A docs/quant-upgrade-tushare-source-design-and-blocker-acceptance-report-2026-04-29.md`

不应该出现：

- `packages/quant/*`
- `data/quant/*`
- `data/config/quant-research.json`
- `tests/test_quant*.py`
- any `apps/*`
- any `stock-analyzer/*`
- any `stock-screener/*`
- any raw vendor data path

## 5. Meta Docs

以下文档不属于 PR A/B/C 的业务提交范围，建议单独做一个 meta commit，或在人工确认后附加到对应 PR：

```text
docs/quant-upgrade-change-inventory-and-commit-plan-2026-04-30.md
docs/quant-upgrade-change-inventory-acceptance-report-2026-04-30.md
docs/quant-upgrade-stage-pathspec-plan-2026-04-30.md
```

如果单独提交 meta docs，stage command template:

```bash
git add -- \
  docs/quant-upgrade-change-inventory-and-commit-plan-2026-04-30.md \
  docs/quant-upgrade-change-inventory-acceptance-report-2026-04-30.md \
  docs/quant-upgrade-stage-pathspec-plan-2026-04-30.md
```

检查：

```bash
git diff --cached --name-status
git diff --cached --name-only | rg -v '^docs/quant-upgrade-(change-inventory-and-commit-plan|change-inventory-acceptance-report|stage-pathspec-plan)-2026-04-30\\.md$' || true
```

第二条命令应无输出。

## 6. Excluded 总清单

无论哪个 PR / Commit，都不要 stage：

```text
packages/quant/__pycache__/
packages/quant/*.pyc
apps/control-panel/dashboard_data.py
apps/control-panel/tests/test_app_smoke.py
apps/control-panel/tests/test_stock_mvp_first_screen_contract.py
apps/data/
apps/reports/
apps/scripts/prism_canonical.py
apps/web/
data/history/
stock-analyzer/config/stocks.json
stock-analyzer/scripts/fetch.py
stock-analyzer/data/
stock-screener/data/
/Users/yangbishang/.prism-private/tushare-poc/
```

特别排除：

- raw Tushare response；
- row-level vendor data；
- token / API key / account secret；
- runtime cache；
- current-state JSON；
- scan stale outputs；
- unrelated app / frontend changes；
- unrelated stock analyzer cache。

## 7. 最终提醒

严禁 `git add .`。

每次 stage 后立刻运行：

```bash
git diff --cached --name-status
```

如果 cached diff 中出现任何本计划未列出的路径，停止提交，先人工确认，不要用 `git reset` 或删除文件自行修复，除非用户明确授权。
