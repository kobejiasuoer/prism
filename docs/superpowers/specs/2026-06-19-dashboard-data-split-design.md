# dashboard_data.py 增量拆分 设计文档

- 日期：2026-06-19
- 范围：从 dashboard_data.py (14719行) 增量抽出最大最独立的功能簇到独立模块（方案 A）
- 约束：消费者用 `from dashboard_data import X` 命名导入；测试直接碰私有全局变量。所以拆分必须保留 dashboard_data.py 作为 re-export 壳，所有现有 import 不变。

## 目标
把最大、最独立的簇抽到独立模块，让 God 函数（`_build_holding_review` 362行）可独立单测，dashboard_data.py 从 14719 行降到 ~12800。每次抽一簇，移完即跑全量测试。

## 第一批：Portfolio 持仓簇（lines 12808-14719，~1900行）

**为什么先抽它**：
- 有清晰的起始标记（`# Portfolio account view` 注释块）
- 连续的 `_portfolio_*` + `build_portfolio_account_view` + `_build_holding_review` 系列
- 只依赖 3 个共享 helper（`expected_trade_date`、`normalize_code`、`round_money`）
- 含最大的 God 函数 `_build_holding_review`（362行，当前不可独立单测）

**做法**：
1. 新建 `apps/control-panel/portfolio_view.py`，把 12808-14719 的所有函数移过去。
2. 新模块顶部 `from dashboard_data_shared import expected_trade_date, normalize_code, round_money`（或直接从 dashboard_data import，但避免循环——用单独的 shared helper 模块或 lazy import）。
3. dashboard_data.py 原位置替换为 re-export：`from portfolio_view import *`（或显式列出公开函数）。
4. 验证：`from dashboard_data import build_portfolio_account_view` 仍可用；全量测试通过。

**循环依赖处理**：portfolio_view 需要的 3 个 helper 如果也在 dashboard_data 里，直接 import 会循环。方案：把这 3 个 helper 也抽到一个 `dashboard_data_shared.py`（或它们本就在别的模块）。先查它们的定义位置决定。

## 后续批次（本波可能只做第一批，视时间）
- Stock profile 缓存视图簇（`build_stock_profile_*`，~1000行）
- Ask/LLM 簇（`build_ask_case_view` 等，~700行）

## 非目标
- 不做全量 12 模块拆分。
- 不改任何函数的逻辑，纯搬迁 + re-export。
- 不改 app.py / tests 的 import 语句（靠 re-export 保兼容）。

## 风险
| 风险 | 缓解 |
|------|------|
| 循环导入 | 先查 helper 定义位置；必要时抽 shared 模块 |
| re-export 漏函数 | 抽完后 `python -c "from dashboard_data import build_portfolio_account_view"` 验证；跑全量测试 |
| 测试碰的全局变量 | portfolio 簇的全局变量（如 `_holding_ai_review_store`）也一并搬迁 + re-export |

## 成功标准
- [ ] dashboard_data.py 行数从 14719 降到 ~12800
- [ ] portfolio_view.py 独立存在，`_build_holding_review` 可单独 import
- [ ] `pytest -q` 全绿
- [ ] `from dashboard_data import build_portfolio_account_view` 仍工作
