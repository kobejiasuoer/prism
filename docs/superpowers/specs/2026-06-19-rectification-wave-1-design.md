# 整改第一波 设计文档

- 日期：2026-06-19
- 范围：防自毁修复 + 退出股后续跟踪 + 低风险死代码清理
- 上游依据：`docs/system-audit-2026-06-19.md`（P0 问题 1-7）、`docs/discovery-page-design-review-2026-06-19.md`
- 本波**不含**：拆分 `dashboard_data.py`/`decision_ledger.py` 巨型文件、拆前端大组件、阶段间加 schema、重写评估闸门、引入数据库、清理 control_panel shim。这些留后续波次。

---

## 1. 目标与成功标准

### 目标
1. **消除"系统会自己坏掉"的三个隐患**：2027 调度停摆、数据无限增长、调度器状态非原子写。
2. **让退出股可被跟踪**：解决"只跟踪一天没意义"——退出后记录 N 日收益，区分真退出/错杀。
3. **清理低风险死代码**：清理 `stock-screener/scripts/` 死符号链接（**不删 data/**，它是活读取根）；明确标注 `historical_edge/` 为未完成研究桩。

### 成功标准（可验证）
- [ ] `trading_calendar` 在 2026-12-31 之后不再 fail-close；有测试覆盖"跨年 horizon"场景。
- [ ] 存在 retention 任务，跑一次能实际删除超过保留期的 `data/prism_data`/`data/scheduled_runs`/`data/runtime` 旧文件，且有空跑(dry-run)模式。
- [ ] `scheduler_state.json` 写入用 temp-rename 原子模式；有测试覆盖"写入中崩溃"。
- [ ] 退出股在 lifecycle JSON 里带 `exit_return_tracking` 字段；存在独立计算器模块与单元测试。
- [ ] `stock-screener/scripts/` 符号链接清理后 `pytest -q` 全绿、`next build` 通过（`data/` 保留不动）。
- [ ] `historical_edge` 运行时桩行为有明确文档标注。
- [ ] 全程通过 `pytest -q` + `python3 scripts/scrub-secrets.py`。

### 非目标（明确排除）
- 不改发现页 UI（那是 discovery 报告选项 B/C 的事）。
- 不拆任何 >1000 行文件。
- 不引入数据库。
- 不动 control_panel 三目录 shim（改名风险高，留后续）。

---

## 2. 任务分解

本波分 6 个独立任务，每个可独立实施、独立验收、互不阻塞。

### 任务 A：修复 trading_calendar 跨年停摆 [P0]

**问题**：`apps/control-panel/trading_calendar.py:55,64` 硬编码 2025-2026 节假日表，`CALENDAR_HORIZON = date(2026,12,31)`。超过此日期 `calendar_status` 返回 `unknown`，调度器跳过所有任务（`prism_scheduler.py:788`）。

**措施**：
1. 把 `STATIC_HOLIDAYS` 扩展到 2027 年（从公开 A 股交易日历抄录）。
2. 引入 `EXPIRY_WARNING_DAYS`（如 30）：当今天距 horizon 不足 30 天时，`calendar_status` 附带 `horizon_warning` 字段。
3. horizon 之后的降级行为：从 `unknown`（停摆）改为返回 `unknown` 但**附 `fallback_assume_trading` 标志**，让调度器记录警告日志而非静默停摆。具体语义：周末仍判 `weekend`，工作日判 `unknown+warning`（不再无条件 skip），由调度器侧决定是否放行。
4. 新增测试：覆盖"今天 > horizon 且为工作日"、"距 horizon 不足 30 天"、"跨年正常交易日"三种场景。

**风险**：低。纯增量，不改既有节假日判定逻辑。

### 任务 B：数据 retention 清理任务 [P0]

**问题**：`data/prism_data/`（53k 文件/7.8G）、`data/scheduled_runs/`（5415 文件）、`data/runtime/`（20 个无轮转日志）零清理，且全 gitignored 不可见。

**措施**：
1. 新建 `apps/scripts/prism_retention.py`，提供 `--dry-run` 模式。
2. 三个清理目标，各自独立保留期配置（默认值见下）：
   - `data/scheduled_runs/{logs,runs}/`：保留近 30 天（按目录名时间戳）。
   - `data/runtime/*.log`：保留近 14 天；`.corrupt-*` 隔离副本保留近 30 天。
   - `data/prism_data/datasets/`：保留近 90 天（按 trade_date 子目录）；`tinyshare_*_harvest/` 原始 run-dir 保留近 30 天。
3. **绝不删**：`prism.db`、`scheduler_state.json`、`scheduler_events.jsonl`（这些是状态非日志，需单独的压缩/轮转，不在本波）、`data/config/`、`data/schemas/`、`data/quant/labels/`。
4. `--dry-run` 打印将删的文件清单与总大小，不实际删除。无 `--dry-run` 才真删。
5. 接入调度器：新增 cron 任务 `retention_cleanup`，每日盘后（如 18:00）以 `--dry-run=false` 执行。先在 `CRON_POLICIES` 注册，保留期可通过 env 覆盖。
6. 单元测试：用 tmp_path 构造过期/未过期文件，验证 dry-run 不删、真删只删过期、白名单文件不动。

**保留期默认值**：
| 目标 | 默认保留 | env 覆盖 |
|------|---------|---------|
| scheduled_runs/logs,runs | 30 天 | `PRISM_RETENTION_RUN_DAYS` |
| runtime/*.log | 14 天 | `PRISM_RETENTION_LOG_DAYS` |
| runtime/*.corrupt-* | 30 天 | `PRISM_RETENTION_CORRUPT_DAYS` |
| prism_data/datasets | 90 天 | `PRISM_RETENTION_DATASET_DAYS` |
| tinyshare_*_harvest | 30 天 | `PRISM_RETENTION_HARVEST_DAYS` |

**风险**：中。删除操作不可逆，故必须 dry-run 优先 + 白名单严格 + 单元测试覆盖。先 dry-run 跑一轮看清单再开真删调度。

### 任务 C：调度器状态原子写 [P0]

**问题**：`apps/scripts/prism_scheduler.py:107-109` 每 tick 用 `path.write_text` 重写 `scheduler_state.json`，无原子保证。状态含去重键，损坏会导致重复触发任务。已有 DB 损坏前科。

**措施**：
1. 新建 helper `atomic_write_text(path, content)`：写到 `path.tmp.<pid>`，`os.replace` 到目标（POSIX 原子）。带 fsync。
2. `scheduler_state.json` 与 `scheduler_events.jsonl` 的写入改用此 helper（events 是 append，仅 state 需原子全量写）。
3. 同时给 `decision_ledger.py` 和 `dashboard_data.py` 里关键的 `json.dump` 状态写入（today_action_decisions.json、ask_recent_queries.json、decisions/{date}.json、review_cases.json）套上同一 helper。
4. 单元测试：mock `os.replace` 在中途抛异常，验证目标文件不被截断、旧内容完整保留。

**风险**：低。`os.replace` 是标准原子模式，跨平台。改动点集中在一个 helper + 几处调用。

### 任务 D：退出股后续收益跟踪（轻量计算器）[P0-功能]

**问题**：`candidate_lifecycle.py:514-529` 退出样本只记 `last_seen`，不回填后续走势。quant 的 `forward_return_labels` 只有 2024 数据，今天的退出股查不到。这是"只跟踪一天没意义"的根因。

**措施**：
1. 新建 `packages/screener/exit_return_tracker.py`，独立模块：
   - `record_exit(code, name, exit_date, exit_price, reason, theme)`：退出发生时调用，写入 `data/runtime/exit_tracking.jsonl`（append-only，每行一条 `{code, exit_date, exit_price, ...}`）。
   - `update_exits(pricing_provider, trade_date)`：对每条未结算（holding_window 未满）的退出记录，按交易日推进，记下当日收盘价；窗口满（默认 5 日）后计算 `net_return = last_price/exit_price - 1` 并打标 `outcome: "true_exit" | "misjudged" | "inconclusive"`（misjudged = 反弹超阈值，如 +5%）。
   - 阈值（窗口天数、misjudged 阈值）走 `data/config/stock-parameters.json` 新增段落，不硬编码。
2. **定价源**：复用 `scan.py:fetch_realtime_quotes_batch` 的报价能力抽出为可复用函数（若耦合太深则新建轻量 sina daily-kline 拉取，与 scan 解耦）。优先复用，避免新写数据采集。
3. **接入 lifecycle**：`candidate_lifecycle.py` 的 exited 分支，对每只退出股调 `record_exit`。退出价从当次快照取（若无则记 `exit_price=null`，后续 update 时回填）。
4. **接入调度器**：新增 cron 任务 `exit_return_update`，每日盘后（如 15:30）推进所有未结算退出记录。
5. **lifecycle JSON 字段**：exited 条目增加 `exit_return_tracking: {status, holding_window_days, net_return, outcome}` 字段。前端本波**不渲染**它（留 discovery 选项 B/C），但数据就绪。
6. 单元测试：mock 定价源，构造"真退出"（连跌）、"错杀"（反弹）、"数据缺失"三种场景，验证 outcome 标注正确。

**风险**：中。新增存储格式与调度任务。关键风险是定价源耦合——设计时优先复用 scan 现有能力，若复用代价过大则降级为"先记录 exit_price，跟踪逻辑留下一波"。

**降级方案**（若定价源复用受阻）：本波只实现 `record_exit`（把退出价和元数据写进 jsonl），`update_exits` 的收益计算推到下一波。这样至少解决了"退出股信息不丢失"。

### 任务 E：清理 stock-screener/ 中的死符号链接 [P1-死代码]

**问题**：`stock-screener/`（repo 根）是 2026-04-21 冻结的遗留目录。审计初版判断"可安全删除"，但 spec 自审发现**这是错的**——`stock-screener/data/` 是活的数据读取根：

- `apps/control-panel/dashboard_data.py:26` `SCREENER_DATA_DIRS = (CURRENT_SCREENER_DATA_DIR, STOCK_SCREENER_ROOT / "data")` —— 它是 fallback 读取路径。
- `apps/scripts/prism_canonical.py:32` `SCREENER_DATA_DIR = STOCK_SCREENER_ROOT / "data"` —— canonical loader。
- `packages/prism_storage/artifacts.py:17` `ARTIFACT_SCAN_DIRS` 包含 `"stock-screener/data"` —— artifact 索引源。
- `apps/scripts/quality_gate_dashboard.py:13`、`inventory_shadow_replay_data.py:479` 也读它的 `data/`。

所以**整个目录不能删**。真正可安全清理的只有 `stock-screener/scripts/`——那是 17 个指向 `../packages/screener/` 的符号链接，属于重复入口，无独有逻辑。

**措施（收窄）**：
1. 只清理 `stock-screener/scripts/` 下的符号链接（确认每个都是 symlink 且目标存在于 packages/screener）。
2. **保留** `stock-screener/data/` 与 `stock-screener/reports/`（活读取根）。
3. 在 `stock-screener/` 根加一个 `README.md`，说明：本目录是历史 skill 容器，`data/` 仍被 control-panel/prism_canonical 作为 fallback 读取根使用，`scripts/` 符号链接已清理，新代码请用 `packages/screener/`。
4. 不动任何读取 `stock-screener/data` 的 Python 代码（那是第三波"shim 清理"才动的事）。

**风险**：低。只删符号链接，保留数据。删前用 `ls -la stock-screener/scripts/` 逐个确认是 symlink 且目标存在。`pytest -q` + `next build` 验证无回归。

### 任务 F：标注 historical_edge 为未完成研究桩 [P1-死代码]

**问题**：`packages/screener/historical_edge/`（1488 行）在 `sample_pool=None` 时永远返回桩（`__init__.py:71-83`），唯一调用方硬传 None（`dashboard_data.py:10890`）。运行时产出为零却占维护负担。

**措施**：
1. **不删代码**（删 1488 行风险高，且可能未来要用）。
2. 在 `historical_edge/__init__.py` 顶部加显著文档串：明确"本模块为未完成研究桩，运行时 sample_pool 恒为 None，产出 coverage_quality=insufficient；接入需先实现 sample pool 构建与调度"。
3. 在 `dashboard_data.py:10888-10903` 调用处加注释，指向该说明。
4. 在 `docs/system-audit-2026-06-19.md` 已记录，无需额外文档。

**风险**：极低。只加注释与文档串。

---

## 3. 任务依赖与执行顺序

```
A (calendar)     ─┐
C (atomic write) ─┼─→ 互相独立，可并行
E (清 stock-screener 符号链接) ─┤
F (标 historical_edge) ─┘

B (retention) ──→ 独立，但建议在 C 之后（retention 也涉及 runtime 文件，原子写先就位更稳）

D (exit tracker) ──→ 最复杂，建议最后做；依赖对 scan.py 报价能力的理解
```

建议执行顺序：**A → C → E → F → B → D**（A/C/E/F 快且低风险先清，B 中等，D 最复杂收尾）。

---

## 4. 验证策略

每个任务完成后：
1. 该任务的单元测试单独跑通。
2. 全部完成后跑完整验收：
   ```
   pytest -q
   python3 scripts/scrub-secrets.py
   cd apps/web && ./node_modules/.bin/next build
   ```
3. retention 任务交付前，先 `--dry-run` 跑一轮，人工确认删除清单合理再启用真删调度。
4. exit tracker 交付前，用 6-18 那批真实退出股（TCL科技、京东方A 等）做一次 dry-run，看 outcome 标注是否合理。

---

## 5. 不在本波的事项（明确记录，避免遗漏）

| 事项 | 为何推迟 | 后续归属 |
|------|---------|---------|
| 拆 dashboard_data.py(14605行) | 单独就要数天，会拖死本波 | 第二波(工程债) |
| 拆前端 3 个 >1000 行组件 | 同上 | 第二波 |
| 阶段间 JSON 加 schema | 跨 scan/ai/midday/lifecycle 多文件 | 第二波 |
| control_panel shim 清理 | 需目录改名+全局 import 重写，高风险 | 第三波 |
| 重写评估闸门(查预测质量) | 大改且需重新定义评分 | 第三波 |
| 发现页 UI 改造(动作列/轨迹视图) | 依赖 exit tracker 数据就绪 | 第二波(数据就绪后) |
| 引入数据库 | 架构级决策 | 第三波 |
| 调度器 events.jsonl 轮转 | 需设计轮转策略 | 可并入本波 B 的后续 |

---

## 6. 风险总览

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| retention 误删数据 | 中 | 高 | dry-run 优先 + 白名单 + 单测 + 人工确认 |
| exit tracker 定价源耦合过深 | 中 | 中 | 降级方案：只 record_exit，计算推后 |
| 清 stock-screener 符号链接破坏读取 | 低 | 低 | 只删 symlink 保留 data/；先 ls 确认；跑 pytest |
| calendar 改动影响现有调度 | 低 | 中 | 纯增量 + 跨年测试 |
| 原子写 helper 在 Windows 行为 | 低 | 低 | os.replace 跨平台；Windows 测试覆盖 |

---

## 附录：关键代码引用（实施时定位用）

- `apps/control-panel/trading_calendar.py:55,64` — calendar horizon（任务 A）
- `apps/scripts/prism_scheduler.py:107-109` — 非原子状态写（任务 C）
- `apps/control-panel/refresh_policy.py:444-608` — CRON_POLICIES，接 retention/exit_update 任务（任务 B/D）
- `packages/screener/candidate_lifecycle.py:514-529` — exited 分支，接 record_exit（任务 D）
- `packages/screener/scan.py:515` — fetch_realtime_quotes_batch，定价源复用候选（任务 D）
- `packages/screener/historical_edge/__init__.py:71-83` — 桩返回（任务 F）
- `apps/control-panel/dashboard_data.py:10888-10903` — historical_edge 调用处（任务 F）
- `stock-screener/scripts/` — 待清理的死符号链接（任务 E，data/ 保留）
