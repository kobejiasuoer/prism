# Prism 股票 MVP 实施 Backlog

Date: 2026-04-24
Author: Codex
Scope: 只基于当前 `prism` 仓库真实代码与最新产物整理，不展开长期泛化路线图

## 1. 本版 backlog 的判断边界

这份 backlog 只收录“当前代码已经有雏形、但还没形成稳定用户价值”的缺口，判断依据主要来自：

- `stock-analyzer/scripts/fetch.py`
- `packages/screener/scan.py`
- `packages/screener/ai_screening.py`
- `packages/screener/midday_verify.py`
- `apps/scripts/prism_canonical.py`
- `apps/control-panel/app.py`
- `apps/control-panel/dashboard_data.py`
- `stock-analyzer/data/daily_snapshots/2026-04-21.json`
- `stock-screener/data/ai_screening_result.json`
- `stock-screener/data/midday_verification_result.json`
- `data/evaluation/stock_analysis/latest_scorecard.json`
- `data/history/reports/command_brief/prism-stock-analysis-assessment-2026-04-23.md`

明确不放进本版 MVP backlog 的内容：

- 多市场扩展
- 机构级组合优化
- 泛化因子研究平台
- 完整量化回测框架重写

## 2. 模块化 backlog

### 模块 A. 自选股 / 持仓规则底座

| ID | 要改文件 / 链路 | 要改什么 | 解决的真实问题 | 优先级 | 类型 | 完成后用户侧改善 |
|---|---|---|---|---|---|---|
| A1 | `stock-analyzer/scripts/fetch.py` 的 `fetch_technical_indicators()` -> `build_rule_snapshot()` -> `build_snapshot_record()` -> `stock-analyzer/data/daily_snapshots/*.json` | 把当前依赖同级 `backtest.py` 的技术评分逻辑收回仓库内，落成可测试的 repo-owned 模块；缺分时明确降级，不再静默失败。 | 当前 `fetch.py` 动态导入 `stock-analyzer/scripts/backtest.py`，但仓库里没有这个文件；这意味着自选股技术分/看多看空信号在重跑时可能静默失效，持仓动作不可复现。 | P0 | 补规则 | 持仓页、问股页、自选股快照里的“技术分/技术基线”会稳定可复算，用户不会出现“昨天有分今天重跑没分、动作却变了”的情况。 |
| A2 | `stock-analyzer/scripts/fetch.py` -> `apps/scripts/prism_canonical.py` 的 `normalize_watchlist_stock()` -> `apps/control-panel/dashboard_data.py` | 把 `flow_confidence`、`flow_as_of`、`capital_flow` 摘要从 watchlist 源快照保留到 canonical 层，并在 Today / Watchlist / Ask 的结论区显式展示“盘中确认 / 历史参考”。 | 源快照已经有 `flow_confidence`，但 canonical 只保留了 `flow_unconfirmed` 布尔值；前端拿不到“这是昨天资金还是今天确认”的完整语义，用户很难判断资金信号能不能当盘中证据。 | P0 | 补输出约束 | 用户会直接看到“资金只是历史参考，不能当盘中确认”，减少把滞后资金流误读成今日强确认的情况。 |

### 模块 B. 机会发现 / 午盘确认

| ID | 要改文件 / 链路 | 要改什么 | 解决的真实问题 | 优先级 | 类型 | 完成后用户侧改善 |
|---|---|---|---|---|---|---|
| B1 | `packages/screener/midday_verify.py` -> `stock-screener/data/midday_verification_result.json` -> `apps/control-panel/dashboard_data.py` | 把午盘确认的 baseline 从“仅晨间 A/B”升级成“晨间需继续跟踪名单”；至少在 `gate=off/limited` 时补一层 top caution coverage。 | 当前 `midday_verify.py` 只确认 `tier in ("A", "B")` 的晨间名单。像 `2026-04-21` 这种阀门关闭日，`target_codes` 直接为空，午盘只剩“新增观察”，没有“晨间观察里哪些继续有效 / 哪些失效”。 | P0 | 补规则 | 午盘页不再在弱市日失去意义，用户能看到“早上关注的票现在还值不值得继续盯”，而不是只有一张空确认表。 |
| B2 | `packages/screener/midday_verify.py` -> `apps/scripts/prism_canonical.py` 的 `find_candidate_detail()` -> `apps/control-panel/dashboard_data.py` 的 `build_candidate_detail_view()` | 给 `fresh_candidates` 补齐 `entry_plan`、`levels`、`setup_type`、`execution_quality` 等动作字段，或者复用晨间 `build_setup_plan()` 生成同结构输出。 | 现在午盘新增观察只输出了名称、分数、主题和一句风险；点进详情页后，canonical 会把它降成 `entry_plan=None` 的简化候选，导致“午盘新增”无法像晨间候选一样给出动作、触发、失效、仓位。 | P0 | 补输出约束 | 用户在午盘新增观察页能直接看到“怎么盯、盯什么位、什么条件下取消”，而不是只能看到一条摘要。 |
| B3 | `packages/screener/scan.py` 的 `classify_theme()` / `assess_market_themes()` -> `packages/screener/ai_screening.py` -> command brief / opportunities | 收紧主题归类，把大面积落入 `其他` 的票拆回已有行业/题材别名体系，至少把 command brief 主线判断里最常见的 `其他` 大桶打散。 | 当前 `stock-screener/data/ai_screening_result.json` 里 `其他` 主题的 `count=23, score=49.78`，已经高于多数明确主题；这说明主题层对很多票失真，主线判断会被一个“垃圾桶分类”稀释。 | P1 | 补特征 | 用户看到的“主线 / 次主线 / 题材持续性”会更像真实市场结构，观察池排序也会更可信。 |
| B4 | `packages/screener/scan.py` 的股票池过滤 -> `packages/screener/run_full_workflow.sh` / `run_midday_refresh.sh` | 把当前硬编码的机会池边界改成显式配置，至少让 `30/68` 与高弹性子池成为可开关选项，而不是永远在 `_normalize_stage0_stock()` 里被排除。 | 现在 `scan.py` 直接排除了 `30` / `68`，并把机会池锁在 `沪深300 + 中证500`；这会系统性漏掉一部分 A 股短线最活跃的强趋势票。 | P1 | 补数据 | 用户在“观察池 / 新机会”里看到的名单会更接近真实短线市场，而不是只剩中大盘主板口径。 |

### 模块 C. 单股统一决策输出

| ID | 要改文件 / 链路 | 要改什么 | 解决的真实问题 | 优先级 | 类型 | 完成后用户侧改善 |
|---|---|---|---|---|---|---|
| C1 | `apps/control-panel/app.py` 路由层 + `apps/control-panel/dashboard_data.py` 的 `build_ask_case_view()` / `build_watchlist_detail_view()` / `build_candidate_detail_view()` + 对应模板 | 落一个统一的 `/stock/{code}` 页面与单一 `build_stock_profile_view()`，把 Ask / 持仓详情 / 候选详情合并成一个 canonical stock profile。 | 当前同一只股票在 `/ask`、`/watchlist/{code}`、`/opportunities/{code}` 有三套 detail builder 和三套结论拼装方式；代码重复很重，用户也会在不同入口看到不同层级的“主结论”。 | P0 | 补输出约束 | 用户从任何入口进同一只股票，都只会看到一套统一结论、统一风险边界、统一仓位口径，真正实现 “one stock, one main conclusion”。 |
| C2 | `apps/control-panel/dashboard_data.py` 的 `build_live_stock_context()` -> Ask 页 | 把 Ask 的实时分析改成“canonical 快照托底 + live enrich 增量补充”，加短 TTL 缓存，并把缺失组件状态显式展示。 | 当前 Ask 每次查询都会同步打多路网络请求实时重算，和 Today / Watchlist 使用的快照口径不同；慢、脆、且容易出现 Ask 结论与今日页不一致。 | P1 | 补数据 | 问股会更快、更稳，也更不容易出现“问股说能看，今日页却说先别动”的割裂感。 |
| C3 | `apps/scripts/prism_canonical.py` -> `apps/control-panel/dashboard_data.py` -> `apps/control-panel/templates/today.html` / `watchlist.html` / `opportunities.html` | 把跨页共用的 `canonical_decision` 继续下沉成真正的统一字段源，不再由各页重复拼接 `why_now / trigger / stop / next_step`。 | 现在虽然已有 `canonical_decision`，但很多页面仍在各自拼装 summary / plan / risk 语句，导致改一处规则要追多条页面链路。 | P1 | 补输出约束 | 页面之间的话术和动作排序会更一致，用户更容易形成稳定心智，不用每页重新理解一次。 |

### 模块 D. 复盘 / 信任层

| ID | 要改文件 / 链路 | 要改什么 | 解决的真实问题 | 优先级 | 类型 | 完成后用户侧改善 |
|---|---|---|---|---|---|---|
| D1 | `stock-analyzer/data/daily_snapshots/*.json` -> 新增 watchlist lifecycle/diff 脚本 -> `apps/scripts/prism_canonical.py` -> Today / Watchlist | 给自选股补一条和 screener `candidate_lifecycle.py` 对应的“昨日 vs 今日”变化链路，至少输出 action/position/risk boundary 的变化原因。 | 现在机会池有 lifecycle，持仓链路没有；用户能看到当前动作，却不容易知道“今天为什么从观望变成减仓”或“哪条边界变了”。 | P1 | 补特征 | Today 和持仓页会更像一个可信赖的“每日动作账本”，用户能看懂变化，不只看结果。 |
| D2 | `apps/control-panel/app.py` 的 `/api/parameters` 保存链路 -> `packages/stock_parameter_config.py` -> `start_stock_evaluation.sh` / `apps/scripts/evaluate_stock_analysis.py` | 参数保存不要直接生效；先跑 stock evaluation / replay gate，至少把 `historical_validation` 与 hard gates 结果挂回保存响应。 | 仓库已经有评估器和 scorecard，但参数页保存仍是“写 JSON 即上线”；这会让阈值调整直接影响运行口径，缺少最基本的回归闸门。 | P1 | 补规则 | 用户会明显减少“参数刚改完，今天所有判断都变味了”的体验，系统稳定性和信任感会更高。 |

## 3. 建议实施顺序

### Sprint 1：先把“结论能不能信、午盘有没有用”补齐

1. `A1` 自选股技术评分去外部依赖
2. `A2` 资金时效穿透到 canonical / UI
3. `B1` 午盘确认覆盖集扩展
4. `B2` 午盘新增观察补齐动作计划
5. `C1` 统一单股页骨架
### Sprint 2：再补“体验一致性”和“调参安全”

1. `C2` Ask 改成快照托底 + live enrich
2. `C3` 收束 canonical decision 字段源
3. `B3` 压缩 `其他` 主题桶
4. `D1` 自选股 lifecycle / diff
5. `D2` 参数保存挂评估 gate
6. `B4` 扩成可配置机会池

## 4. 这版 backlog 的核心取舍

如果只做最小可上线股票 MVP，我建议把真正的 P0 定义为下面五件事：

- 自选股技术评分可复现
- 资金时效能被用户看见
- 午盘确认在弱市日也有内容
- 午盘新增观察能给出动作计划
- 单股统一成一个结论页

这五件补完之后，Prism 才算从“几条股票分析链路并存”进入“一个能稳定给用户日常动作答案的股票 MVP”。
