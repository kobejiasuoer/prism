# Prism 量化升级变更盘点与提交隔离方案

Date: 2026-04-30
Scope: change inventory and commit isolation plan only
Status: no staging, no commit, no cleanup performed

## 1. 本次盘点边界

本次只做只读检查和文档输出。

明确未执行：

- 未修改代码；
- 未删除文件；
- 未运行 `git add`；
- 未运行 `git commit`；
- 未运行 `git clean`；
- 未运行 `git reset`；
- 未调用外部 API；
- 未重跑量化报告。

新增文件仅为本文档：

- `docs/quant-upgrade-change-inventory-and-commit-plan-2026-04-30.md`

## 2. 已执行的只读检查

检查命令：

- `git status --short`
- `git diff --name-status`
- `git diff --stat`
- `git ls-files --others --exclude-standard`
- `find packages/quant -type f`
- `find data/quant -type f`
- `find tests -maxdepth 1 -type f -name 'test_quant*.py'`
- `find docs -maxdepth 1 -type f -name 'quant-upgrade*.md'`
- repo 内精确 Tushare token 扫描，不打印 token 值
- repo 内 Tushare raw archive 路径扫描

当前工作区摘要：

- tracked 修改：`177 files changed, 54371 insertions(+), 8802 deletions(-)`
- untracked 量化源码目录：`packages/quant/`
- untracked 量化数据目录：`data/quant/`
- untracked 量化配置：`data/config/quant-research.json`
- untracked 量化测试：`tests/test_quant*.py`
- untracked 量化文档：`docs/quant-upgrade*.md`
- 大量非量化运行态数据改动：`stock-screener/data/*`、`stock-analyzer/data/*`、`apps/data/*`

按顶层路径统计的工作区变更：

| Top-level path | Count from `git status --short` | 初步分类 |
| --- | ---: | --- |
| `packages` | 1 directory | 量化升级源码，需提交但排除 `__pycache__` |
| `tests` | 7 files | 量化升级测试，建议提交 |
| `data` | 3 entries | 混合：`data/quant` 和 `data/config/quant-research.json` 属于量化；`data/history` 来源需确认 |
| `docs` | 29 files | 量化升级文档和 Tushare docs-only，建议分组提交 |
| `apps` | 20 entries | 多数与量化升级无关或来源不明，建议不纳入量化 PR |
| `stock-analyzer` | 23 entries | 多数为缓存/运行数据或非量化代码，需人工确认 |
| `stock-screener` | 162 entries | 大量历史 scan/AI artifact 修改，默认不纳入量化 PR |

## 3. P0 / Sprint 0-2 建议纳入的代码与测试

建议纳入 Commit A。

### 3.1 建议提交的代码

这些文件构成 Sprint 0-2 的最小量化研究包和 report-only 评估能力：

- `packages/quant/__init__.py`
- `packages/quant/schemas.py`
- `packages/quant/paths.py`
- `packages/quant/config.py`
- `packages/quant/build_research_panel.py`
- `packages/quant/research_io.py`
- `packages/quant/evaluate_factors.py`
- `packages/quant/run_portfolio_backtest.py`
- `packages/quant/report_quant_health.py`

说明：

- `evaluate_factors.py`、`run_portfolio_backtest.py`、`report_quant_health.py` 后续被 P1-A Card 5 扩展过，若要严格拆 Commit A/B，需要 patch-level staging 或按阶段重放。
- `research_io.py` 是 Sprint 2 / P1-A 共享 helper，建议作为 Commit A 或 Commit B 的公共基础纳入，但不要重复提交。

### 3.2 建议提交的测试

- `tests/test_quant_sprint1.py`
- `tests/test_quant_sprint2.py`

### 3.3 建议提交的 Sprint 0-2 配置与研究产物

建议提交，但其中大型 generated JSONL 需人工确认仓库策略：

- `data/config/quant-research.json`
- `data/quant/baselines/quant_baseline_manifest.json`
- `data/quant/panels/daily_signal_panel.jsonl`
- `data/quant/panels/eligible_universe_snapshot.jsonl`
- `data/quant/ledgers/pipeline_stage_ledger.jsonl`
- `data/quant/labels/forward_return_labels.jsonl`
- `data/quant/reports/field_mapping_audit_latest.md`
- `data/quant/reports/price_execution_audit_latest.md`
- `data/quant/reports/panel_coverage_latest.md`
- `data/quant/reports/label_coverage_latest.md`
- `data/quant/reports/factor_evaluation_latest.md`
- `data/quant/reports/portfolio_backtest_latest.md`
- `data/quant/reports/quant_health_latest.md`
- `data/quant/reports/quant_health_latest.json`

人工确认点：

- `data/quant` 总大小约 `72M`。
- `data/quant/labels/forward_return_labels_hardened.jsonl` 约 `43M`，属于 P1-A，不是 Commit A。
- `data/quant/labels/forward_return_labels.jsonl` 约 `15M`。
- `data/quant/panels/daily_signal_panel.jsonl` 约 `7.4M`。
- 若仓库不接受 generated research data，应改为提交 manifest/report，JSONL 放到外部 artifact storage。

### 3.4 P0 / Sprint 文档建议提交

- `docs/quant-upgrade-design-2026-04-27.md`
- `docs/quant-upgrade-p0-execution-flow-2026-04-28.md`
- `docs/quant-upgrade-p0-review-revision-2026-04-28.md`
- `docs/quant-upgrade-task-breakdown-2026-04-28.md`
- `docs/quant-upgrade-sprint2-acceptance-checklist-2026-04-28.md`
- `docs/quant-upgrade-sprint2-acceptance-report-2026-04-28.md`

## 4. P1-A Card 1-5 建议纳入的代码、测试、报告

建议纳入 Commit B。

### 4.1 建议提交的代码

- `packages/quant/build_benchmark_returns.py`
- `packages/quant/price_adjustment_policy.py`
- `packages/quant/execution_flags.py`
- `packages/quant/upgrade_forward_labels.py`
- `packages/quant/evaluate_factors.py`
- `packages/quant/run_portfolio_backtest.py`
- `packages/quant/report_quant_health.py`
- `packages/quant/research_io.py`

说明：

- 后四个文件与 Sprint 2 代码重叠，P1-A Card 5 修改了 hardening sidecar 展示逻辑。拆 Commit A/B 时建议使用 `git add -p` 或重新生成阶段补丁。
- 不建议把 `packages/quant/__pycache__/*` 纳入提交。

### 4.2 建议提交的测试

- `tests/test_quant_p1a_benchmarks.py`
- `tests/test_quant_p1a_adjusted_price.py`
- `tests/test_quant_p1a_execution_flags.py`
- `tests/test_quant_p1a_label_hardening.py`
- `tests/test_quant_p1a_rerun_reports.py`

### 4.3 建议提交的 P1-A 产物

这些是 P1-A Card 1-5 验收产物，建议提交或由人工决定是否外置大型 generated data：

- `data/quant/benchmarks/benchmark_manifest.json`
- `data/quant/benchmarks/benchmark_returns.jsonl`
- `data/quant/price/price_adjustment_manifest.json`
- `data/quant/execution/execution_flags_manifest.json`
- `data/quant/labels/forward_return_labels_hardened.jsonl`
- `data/quant/reports/benchmark_coverage_latest.md`
- `data/quant/reports/price_adjustment_policy_latest.md`
- `data/quant/reports/execution_flags_coverage_latest.md`
- `data/quant/reports/label_hardening_latest.md`
- `data/quant/reports/factor_evaluation_latest.md`
- `data/quant/reports/portfolio_backtest_latest.md`
- `data/quant/reports/quant_health_latest.md`
- `data/quant/reports/quant_health_latest.json`

人工确认点：

- `forward_return_labels_hardened.jsonl` 是大型 generated artifact，约 `43M`。
- `factor_evaluation_latest.md`、`portfolio_backtest_latest.md`、`quant_health_latest.*` 被 P1-A Card 5 重跑覆盖，Commit B 应包含最终版本。

### 4.4 P1-A 文档建议提交

- `docs/quant-upgrade-p1-data-hardening-plan-2026-04-28.md`
- `docs/quant-upgrade-p1a-hardening-acceptance-checklist-2026-04-28.md`
- `docs/quant-upgrade-p1a-decision-matrix-2026-04-28.md`
- `docs/quant-upgrade-p1a-source-inventory-and-implementation-plan-2026-04-28.md`
- `docs/quant-upgrade-p1a-card1-benchmark-acceptance-report-2026-04-28.md`
- `docs/quant-upgrade-p1a-card2-adjusted-price-implementation-plan-2026-04-28.md`
- `docs/quant-upgrade-p1a-card2-adjusted-price-acceptance-report-2026-04-28.md`
- `docs/quant-upgrade-p1a-card3-execution-flags-acceptance-report-2026-04-29.md`
- `docs/quant-upgrade-p1a-card4-label-hardening-acceptance-report-2026-04-29.md`
- `docs/quant-upgrade-p1a-card5-rerun-reports-acceptance-report-2026-04-29.md`
- `docs/quant-upgrade-p1a-external-data-source-research-2026-04-29.md`
- `docs/quant-upgrade-external-data-source-decision-pack-2026-04-29.md`
- `docs/quant-upgrade-external-poc-readiness-acceptance-report-2026-04-29.md`
- `docs/quant-upgrade-master-progress-and-handoff-2026-04-29.md`

## 5. Tushare docs-only 产物

建议纳入 Commit C，且保持 docs-only。

建议提交：

- `docs/quant-upgrade-tushare-poc-plan-2026-04-29.md`
- `docs/quant-upgrade-tushare-field-availability-matrix-2026-04-29.md`
- `docs/quant-upgrade-tushare-poc-acceptance-checklist-2026-04-29.md`
- `docs/quant-upgrade-tushare-poc-runbook-2026-04-29.md`
- `docs/quant-upgrade-tushare-poc-result-2026-04-29.md`
- `docs/quant-upgrade-tushare-poc-acceptance-report-2026-04-29.md`
- `docs/quant-upgrade-tushare-poc-blocker-decision-matrix-2026-04-29.md`
- `docs/quant-upgrade-tushare-nonproduction-source-design-2026-04-29.md`
- `docs/quant-upgrade-tushare-source-design-and-blocker-acceptance-report-2026-04-29.md`

人工确认点：

- `quant-upgrade-tushare-poc-result-2026-04-29.md` 记录了 response SHA256、row_count 和字段列表，但不含 row-level vendor data。
- Tushare token 曾被粘贴进聊天上下文，建议轮换；repo 扫描未发现精确 token 值。

不建议提交：

- repo 外 raw archive：`~/.prism-private/tushare-poc/raw/...`
- repo 外 private summary：`~/.prism-private/tushare-poc/poc_summary_*.json`
- 任何 raw Tushare response、行级行情、完整交易日历、账号截图、积分余额截图。

## 6. Research / Generated Data 产物是否提交

### 6.1 建议提交或人工确认后提交

这些文件是量化升级验收直接要求的 artifact，建议提交以保持可复现验收链路，但需要人工确认 repo 是否接受 generated research data：

- `data/config/quant-research.json`
- `data/quant/baselines/quant_baseline_manifest.json`
- `data/quant/panels/daily_signal_panel.jsonl`
- `data/quant/panels/eligible_universe_snapshot.jsonl`
- `data/quant/ledgers/pipeline_stage_ledger.jsonl`
- `data/quant/labels/forward_return_labels.jsonl`
- `data/quant/labels/forward_return_labels_hardened.jsonl`
- `data/quant/benchmarks/benchmark_manifest.json`
- `data/quant/benchmarks/benchmark_returns.jsonl`
- `data/quant/price/price_adjustment_manifest.json`
- `data/quant/execution/execution_flags_manifest.json`
- `data/quant/reports/*.md`
- `data/quant/reports/quant_health_latest.json`

建议策略：

- 若这是 research repo 且允许提交 frozen generated artifacts，提交上述文件。
- 若主仓不适合放大 JSONL，把大型 JSONL 排除，提交 manifest/report，并在 PR 描述中注明外部 artifact 位置和 hash。
- `data/quant/reports/*.md` 和 manifests 比较适合提交，因为它们是验收摘要和可追溯索引。

### 6.2 建议不提交的 generated/runtime 数据

以下看起来更像当前运行状态、缓存、历史输出或与量化升级无关的生产数据，不建议纳入量化升级提交：

- `apps/data/control_panel_state/ask_recent_queries.json`
- `apps/data/control_panel_state/refresh_state.json`
- `apps/data/command_brief/*.json`
- `apps/data/control_panel_runs/*.json`
- `apps/reports/prism_command_brief_*.md`
- `apps/reports/prism_command_brief_*.txt`
- `data/history/reports/command_brief/feishu-quality-dashboard.md`
- `stock-analyzer/data/daily_snapshots/*.json`
- `stock-analyzer/data/fund_flow_cache/*.json`
- `stock-analyzer/data/fundamentals_cache/*.json`
- `stock-screener/data/ai_history/*.json`
- `stock-screener/data/research_backfill/ai_history/*.json`
- `stock-screener/data/ai_screening_result.json`
- `stock-screener/data/scan_result.json`
- `stock-screener/data/stale_outputs/*.json`

原因：

- 这些文件变更数量大，很多是 mutable/current-state 数据。
- 它们会显著污染量化升级代码审查。
- 若其中个别文件确实是 Sprint 0 baseline source artifact，应由 manifest hash 引用即可，不建议把所有原始历史 artifact 一并改写提交。

## 7. Runtime / Cache / Current-State 不建议提交项

明确不建议提交：

- `packages/quant/__pycache__/*`
- 任何 `*.pyc`
- `.pytest_cache/`
- `.mypy_cache/`
- `.ruff_cache/`
- `.DS_Store`
- repo 外 Tushare raw archive 或 private summary
- 运行态 state JSON
- 当前 scan result / stale output / cache files

当前发现：

- `packages/quant/__pycache__/*` 存在，但未出现在 `git ls-files --others --exclude-standard` 中，说明大概率已被 ignore；仍应在提交前复查不要手动加入。
- repo 内未发现 `tushare-poc/raw` 或 `.prism-private` 路径。

## 8. 与量化升级无关或来源不明的修改

默认不纳入量化升级 PR，除非人工确认它们属于另一个明确任务。

### 8.1 App / control panel / web 路径

- `apps/control-panel/dashboard_data.py`
- `apps/control-panel/tests/test_app_smoke.py`
- `apps/control-panel/tests/test_stock_mvp_first_screen_contract.py`
- `apps/scripts/prism_canonical.py`
- `apps/web/src/app/discovery/page.tsx`
- `apps/web/src/app/page.tsx`
- `apps/web/src/app/portfolio/page.tsx`
- `apps/web/src/lib/types.ts`

判断：

- 这些文件涉及控制面板、前端页面、canonical 脚本或 app 类型。
- 当前量化升级明确禁止页面、Prism Edge、生产排序变更。
- 建议从量化提交中排除，并单独由 owner 判断。

### 8.2 stock-analyzer 路径

- `stock-analyzer/config/stocks.json`
- `stock-analyzer/scripts/fetch.py`
- `stock-analyzer/data/*`

判断：

- `stock-analyzer/scripts/fetch.py` 和 config 可能是独立功能改动。
- `stock-analyzer/data/*` 多为缓存或运行数据。
- 不建议纳入量化升级提交。

### 8.3 stock-screener 路径

变更统计：

- `stock-screener/data/ai_history`: 56 files
- `stock-screener/data/research_backfill`: 57 files
- `stock-screener/data/stale_outputs`: 47 files
- `stock-screener/data/ai_screening_result.json`: 1 file
- `stock-screener/data/scan_result.json`: 1 file

判断：

- 大量 artifact 被改写，风险高。
- 量化升级 baseline manifest 可以引用这些 source artifacts 的 hash，但不应在同一 PR 中重写全部历史 scan/AI artifact。
- 默认排除，除非人工确认这些变更是有意的 source artifact normalization。

## 9. 高风险项检查

### 9.1 `data/quant`

状态：

- 新增 `data/quant`，共约 `72M`，约 `67271` 行。
- 包含 panels、labels、hardened labels、benchmark returns、manifests、reports。

风险：

- 大型 generated research data。
- 包含 forward label 和 hardened label 的研究统计输入。
- 若提交，需要 reviewer 明确接受 repo 内存放 generated quant artifacts。

建议：

- manifests 和 reports 建议提交。
- JSONL 大文件人工确认后提交；否则外置 artifact storage。

### 9.2 `packages/quant`

状态：

- 新增 quant package 源码约 `4182` 行。
- `__pycache__` 存在但不应提交。

风险：

- 新增研究 pipeline 能力，应确认无生产入口调用。
- 需要测试覆盖和 import smoke。

建议：

- 提交 `.py` 源码。
- 不提交 `__pycache__` / `*.pyc`。
- PR 描述明确 report-only，不影响生产排序。

### 9.3 Raw vendor data

检查结果：

- repo 内未发现 `tushare-poc/raw` 或 `.prism-private` 路径。
- repo 内 Tushare 相关文件为 docs-only。
- `docs/quant-upgrade-tushare-poc-result-2026-04-29.md` 包含 response hash、row_count、field list，不包含 row-level vendor data。

建议：

- 不提交任何 repo 外 raw archive。
- 后续提交前再次运行 raw path 和 exact token scan。

### 9.4 Token-like 字符串

检查结果：

- 对当前 `launchctl getenv TUSHARE_TOKEN` 可见 token 做精确 repo 扫描，结果：`clean`。
- docs 中存在 `TUSHARE_TOKEN` 变量名、response SHA256、params fingerprint、source hash 等 token-like 64 hex 字符串。
- 这些 hash 是追溯字段，不是 token，但提交前应由 reviewer 复核。

重要安全提醒：

- Tushare token 曾被粘贴到聊天上下文。即使 repo 扫描 clean，也建议轮换 token 后再进入任何后续长期接入或 adapter 开发。

### 9.5 外部 API 结果

检查结果：

- repo 内 Tushare POC 只保留脱敏摘要文档。
- 私有 raw response 位于 repo 外，不应提交。

建议：

- Tushare docs-only 可提交。
- 不提交 raw API response。

## 10. 明确建议提交 / 不提交 / 人工确认

### 10.1 建议提交

代码与测试：

- `packages/quant/*.py`
- `tests/test_quant_sprint1.py`
- `tests/test_quant_sprint2.py`
- `tests/test_quant_p1a_*.py`

配置与轻量报告：

- `data/config/quant-research.json`
- `data/quant/*/*manifest*.json`
- `data/quant/reports/*.md`
- `data/quant/reports/quant_health_latest.json`

文档：

- `docs/quant-upgrade-p0-*.md`
- `docs/quant-upgrade-task-breakdown-2026-04-28.md`
- `docs/quant-upgrade-sprint2-*.md`
- `docs/quant-upgrade-p1*.md`
- `docs/quant-upgrade-external*.md`
- `docs/quant-upgrade-master-progress-and-handoff-2026-04-29.md`
- `docs/quant-upgrade-tushare*.md`
- `docs/quant-upgrade-change-inventory-and-commit-plan-2026-04-30.md`

### 10.2 建议不提交

- `packages/quant/__pycache__/*`
- any `*.pyc`
- `apps/data/control_panel_state/*.json`
- `apps/data/command_brief/*.json`
- `apps/data/control_panel_runs/*.json`
- `apps/reports/prism_command_brief_*`
- `data/history/reports/command_brief/feishu-quality-dashboard.md`
- `stock-analyzer/data/*`
- `stock-screener/data/*`
- repo 外 `~/.prism-private/tushare-poc/raw/*`
- repo 外 `~/.prism-private/tushare-poc/poc_summary_*.json`

### 10.3 需要人工确认

- 是否把 `data/quant/**/*.jsonl` 大型 generated artifacts 提交进 repo。
- 是否把 `data/quant/price/price_adjustment_manifest.json` 这类较大的 manifest 提交进 repo。
- `apps/*`、`stock-analyzer/scripts/fetch.py`、`stock-analyzer/config/stocks.json` 是否属于另一条用户任务。
- `stock-screener/data/research_backfill/*` 是否是量化 baseline source 的有意重写。
- 是否需要把量化升级拆成多个 PR，而不是单 PR 多 commit。
- Tushare token 是否已轮换。

## 11. 推荐提交隔离方案

推荐至少拆 3 个 commit。若 review 压力大，拆 3 个 PR 更稳。

### Commit A: P0 / Sprint quant package + tests

目的：

- 引入最小 `packages/quant` 研究包；
- 固定 Sprint 0 baseline 和 Sprint 1 panel/labels；
- 引入 Sprint 2 report-only evaluation/backtest/health；
- 保持不影响生产排序。

建议纳入：

- P0/Sprint 0-2 相关 `packages/quant/*.py`
- `tests/test_quant_sprint1.py`
- `tests/test_quant_sprint2.py`
- `data/config/quant-research.json`
- Sprint 0-2 reports / manifests
- 人工确认后的 Sprint 1/2 JSONL artifacts
- P0/Sprint docs

隔离注意：

- 如果 `evaluate_factors.py`、`run_portfolio_backtest.py`、`report_quant_health.py` 已包含 P1-A 变更，Commit A 需要 patch-level staging 或接受 Commit A 包含最终实现后在说明里注明。

### Commit B: P1-A hardening reports/tests

目的：

- 提交 benchmark、price adjustment、execution flags、label hardening、hardened-label report rerun。
- 明确所有内容仍 report-only / research-only。

建议纳入：

- `packages/quant/build_benchmark_returns.py`
- `packages/quant/price_adjustment_policy.py`
- `packages/quant/execution_flags.py`
- `packages/quant/upgrade_forward_labels.py`
- P1-A 对 shared report code 的 patch
- `tests/test_quant_p1a_*.py`
- `data/quant/benchmarks/*`
- `data/quant/price/*`
- `data/quant/execution/*`
- `data/quant/labels/forward_return_labels_hardened.jsonl`，需人工确认大文件策略
- P1-A reports
- P1-A docs

隔离注意：

- 不纳入 Tushare docs。
- 不纳入 raw vendor data。

### Commit C: Tushare docs-only

目的：

- 提交 Tushare POC runbook、field matrix、result、acceptance、blocker/source design 文档。
- 保持 docs-only，不引入 adapter 或数据。

建议纳入：

- `docs/quant-upgrade-tushare-*.md`
- 本文档可放在 Commit C，或作为单独 meta commit。

隔离注意：

- 不纳入 `packages/quant`。
- 不纳入 `data/quant`。
- 不纳入 repo 外 raw archive。
- 不纳入 token 或可还原 vendor dataset。

### Excluded: 运行缓存、raw vendor data、无关数据变更

明确排除：

- `packages/quant/__pycache__/*`
- `apps/data/*`
- `apps/reports/*`
- `stock-analyzer/data/*`
- `stock-screener/data/*`
- repo 外 `~/.prism-private/tushare-poc/*`
- 任何 token、raw response、账号截图、积分余额截图。

## 12. 推荐 PR 拆分

方案一：一个 PR，三个 commit。

- 优点：上下文完整。
- 缺点：`data/quant` 大文件和 generated artifacts 会让 review 变重。

方案二：三个 PR。

- PR 1: P0/Sprint 0-2 quant package、tests、轻量 reports/manifests。
- PR 2: P1-A Card 1-5 hardening code、tests、reports、人工确认后的 generated artifacts。
- PR 3: Tushare docs-only POC / source design / blocker decision docs。

推荐：**方案二**。如果仓库 owner 明确接受 `data/quant` 大型 generated artifacts，也可以用方案一但必须在 PR 描述里列出 generated data policy。

## 13. 提交前最终检查清单

在真正提交前建议执行：

- `git status --short`
- `git diff --cached --name-status`
- 精确 token 扫描，不打印 token 值
- `rg -l 'tushare-poc/raw|\\.prism-private|api\\.tushare\\.pro'`
- `find packages/quant -type f -name '*.pyc'`
- `find . -path './.git' -prune -o -name '__pycache__' -print`
- `pytest tests/test_quant_sprint1.py tests/test_quant_sprint2.py tests/test_quant_p1a_*.py`

提交说明必须重申：

- 未改生产排序；
- 未替换 A/B/C；
- 未做页面；
- 未做 Prism Edge；
- 未做 Expected 5D 展示；
- 未做 ML；
- Tushare raw vendor data 未进入 repo；
- 所有量化结论仍 report-only / research-only。
