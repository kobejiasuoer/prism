# Prism 系统审计报告

- 日期：2026-06-19
- 范围：整个 Prism 仓库（前端、FastAPI 后端、screener 工作流、quant/评估层、运行时/调度器、数据管道）
- 方法：5 个并行审计 agent 分域探查 + 人工综合，每条结论都有 `文件:行号` 证据
- 配套：发现页专项设计评审见 `docs/discovery-page-design-review-2026-06-19.md`

---

## 0. 一句话结论

Prism 是一个**单进程、文件存储、无数据库**的 AI 选股研究系统，核心链路（scan→ai_screening→midday_verify→lifecycle）是真实运作的，但周围**堆了大量半成品和死代码**：一个 6357 行的 quant 研究层完全没接进生产、一个评估闸门只检查 JSON 字段是否存在、7.8G 数据无清理无限增长、调度器在 2027 年会自动停摆。系统"能跑"，但**维护负担和真实价值严重不匹配**。

---

## 1. 系统图谱

### 1.1 宏观架构

```
┌─────────────────────────────────────────────────────────────────────┐
│  浏览器 (Next.js 前端, apps/web, 6 个路由, ~17.5k 行 TS/TSX)         │
│   /  /discovery  /portfolio  /review  /settings  /stock/[code]      │
│   legacy 重定向: /today /ask /watchlist /opportunities → 现有路由   │
└───────────────┬─────────────────────────────────────────────────────┘
                │ /api/* (Next rewrite → 127.0.0.1:8001)
                ▼
┌─────────────────────────────────────────────────────────────────────┐
│  FastAPI 后端 (apps/control-panel, ~33k 行 Python, 99 个端点)       │
│   app.py(4530) ── dashboard_data.py(14605!) ── decision_ledger.py(7109!) │
│   无数据库。状态 = 文件 JSON + 模块级 TTL 缓存(13 个全局 dict)      │
└───────┬───────────────────────────────────┬─────────────────────────┘
        │ subprocess 调度                  │ 直接 import
        ▼                                   ▼
┌──────────────────────────────┐  ┌──────────────────────────────────┐
│ 调度器 (apps/scripts)        │  │ screener 工作流 (packages/screener)│
│  prism_scheduler.py 20s 轮询 │  │  scan.py(2467)→ai_screening.py    │
│  15 个 cron 任务 Mon-Fri      │  │  (1626)→midday_verify.py(790)→   │
│  文件锁去重 / PID 存活检查    │  │  candidate_lifecycle.py(854)→    │
└──────────┬───────────────────┘  │  generate_feishu_message.py(1207)│
           │                       └──────────────┬───────────────────┘
           │ subprocess                          │ 读写 packages/data/
           ▼                                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│  数据层                                                              │
│   TinyShare/Tushare(唯一权威源) ── providers/gateway(多源回退) ──    │
│   data/prism_data/ (7.8G, 53k 文件, 无清理) ── data/runtime/prism.db │
│   (SQLite 5.3M, 仅作索引)                                            │
└─────────────────────────────────────────────────────────────────────┘

  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─
  旁路 / 死代码层 (未接入生产):
  • packages/quant/ (6357 行, 研究专用, 零生产导入)
  • stock-analyzer/ (数据采集, 仅供评估快照)
  • stock-screener/ (2026-04-21 冻结的遗留目录, 符号链接)
  • packages/screener/historical_edge/ (sample_pool=None 时永远返回桩)
  • 评估闸门 evaluate_stock_analysis.py (检查字段存在, 非预测质量)
```

### 1.2 选股核心链路（真实运作部分）

```
morning_warmup(09:25) → aggressive(09:40) → midday_refresh(13:10) → midday_confirmation(13:45)
                            │                                          │
        run_full_workflow.sh                                   run_midday_confirmation.sh
        ├─ scan.py        → packages/data/scan_result.json      ├─ scan.py(重新扫描)
        ├─ ai_screening   → ai_screening_result.json            ├─ midday_verify.py → midday_verification_result.json
        ├─ candidate_lifecycle → lifecycle_{stamp}.json/.md     └─ generate_feishu_message(午盘格式)
        └─ generate_feishu_message(brief+full)
```

- 运行时数据落在 `packages/data/` 和 `packages/reports/`（**不是** README 暗示的 repo 根 `data/`）
- 阶段间 JSON 无 schema 校验，纯 `.get()` 鸭子类型，字段重命名会静默退化
- 后端 `dashboard_data.py` 读取这些 JSON 组装成 99 个 API 端点的响应

### 1.3 代码体量分布（找出"上帝文件"）

| 文件 | 行数 | 角色 | 问题 |
|------|------|------|------|
| `dashboard_data.py` | **14605** | 仪表盘 payload 总装 | 混杂 12+ 不相关职责，450 个函数 |
| `decision_ledger.py` | **7109** | 决策账本 | CRUD+校准+学习循环+LLM 归因 4 件事 |
| `app.py` | 4530 | FastAPI 路由 | 99 端点 + 13 个全局缓存 + 内联子进程 |
| `scan.py` | 2467 | 候选宇宙构建 | 池加载+报价+因子+主题+评分全在一起 |
| `types.ts` | **3354** | 前端类型 | 115 个手写 interface 塞一个文件 |
| `stock-analyzer/fetch.py` | 2108 | 数据采集 | 与 prism_data/screener 大量重复 |
| `ai_screening.py` | 1626 | AI 筛选 | — |
| `opportunity_v2.py` | 1488 | 判官 | — |

> 后端 top 3 文件（dashboard_data + decision_ledger + app）占整个 `apps/control-panel` 的 **79%**。

---

## 2. 严重问题清单（按影响排序）

### 🔴 P0 — 系统性风险（会自己坏掉）

**1. 调度器 2027 年自动停摆。** `trading_calendar.py:55,64` 硬编码 2025-2026 节假日表，`CALENDAR_HORIZON = 2026-12-31`。超过此日期 `calendar_status` 返回 `unknown`，调度器跳过所有任务（`prism_scheduler.py:788`）。**2027 年第一个交易日，整个定时链路静默停止**，需人工改源码。

**2. 调度器状态非原子写入。** `prism_scheduler.py:107-109` 每 tick 用 `write_text` 重写 `scheduler_state.json`，无 temp-rename、无备份。状态含 `last_fired`/`catchup_fired` 去重键，崩溃或 `kill -9` 可能损坏文件导致**重复触发任务**。已有前科：`data/runtime/` 存在 3 个 `prism.db.corrupt-*` 隔离副本（2026-04-26 损坏过）。

**3. 数据无限增长（7.8G 且上升）。** `data/prism_data/` 53,628 文件、7.8G，每个交易日增长，**零清理逻辑**（grep 全仓库无 retention/prune/rotate）。整个树被 `.gitignore` 忽略，增长不可见。`data/scheduled_runs/`（5415 文件）、`data/runtime/`（20 个无轮转日志）同理。SQLite `task_runs`/`artifacts` 只 INSERT 不 DELETE，无 VACUUM。

**4. 无数据库 + 无锁的并发写入风险。** 所有状态是文件 JSON + `json.dump`（dashboard_data 3 处、decision_ledger 5 处），未见原子 rename 模式。多 uvicorn worker 或并发请求会丢写。13 个模块级缓存全局变量靠 12 个手写 `_clear_*` 函数维持一致性（`app.py:1355-1416`），多 worker 部署下必然 stale。

### 🔴 P0 — 死代码 / 价值错配

**5. quant 研究层（6357 行）完全未接入生产。** `packages/quant/` 产出 `forward_return_labels.jsonl`（11064 行），但全仓库零个 `import packages.quant`（除 docs）。screener 链路从不引用 forward return。12 个测试文件专门断言"quant 输出是研究专用、未就绪"（如 `test_quant_p1a_benchmarks.py:78`）。`benchmarks/benchmark_manifest.json:20` 明写 `production_impact == "none"`。**这是上一轮审计（发现页）里"退出样本不回填走势"的根因——基础设施有，但没人接。**

**6. 评估闸门只查"字段在不在"，不查预测质量。** README 宣称是"可复现的验收层"，实际 `evaluate_stock_analysis.py:257-310` 的评分 85/100 来自"JSON 有没有预期的 key"（+3 如果有 `generated_at`，+4 如果有 `market_regime` 块）。已提交的记分卡 `latest_scorecard.json:13` 凭 2026-04 数据拿 97 分。`historical_validation`（15 分上限，现拿 12）是唯一有牙齿的维度，也是 tier 停在 `professional_usable` 而非 `product_ready` 的唯一原因。**这个闸门永远通过自己。**

**7. 遗留目录散落。** `stock-screener/`（repo 根，2026-04-21 冻结，scripts 是符号链接到 packages/screener）；`stock-analyzer/`（数据采集，与 prism_data/screener 大量重复，仅靠它喂评估快照）；`control_panel/` + `apps/control_panel/`（两个 import shim，因为真实目录 `apps/control-panel` 带连字符不可导入，需 `sys.path`/`importlib` 重定向，`dashboard_data.py:34-42` 还要防御性重排 `sys.path`）。

### 🟠 P1 — 工程质量

**8. 三个巨型工作台组件 >1000 行。** `settings-diagnostics.tsx`(1471)、`discovery-observation-workbench.tsx`(1281)、`review-decision-workspace.tsx`(1152)。`lib/hooks.ts`(1108) 把数据访问和 300 行缓存突变逻辑混在一起。

**9. God 函数。** 后端单函数行数：`_build_holding_review`(362 行, `dashboard_data.py:13388`)、`build_opportunities_view`(341)、`build_ask_case_view`(336)、`build_today_action_groups`(331)、`build_review_view`(332)。无法单元测试。

**10. 阈值在源码里硬编码，违背"阈值即配置"承诺。** `scan.py` 的 `filter_strategy` 内联 `amount < 4e8`、`turnover < 1.8`、`8 <= pe <= 25`、`pos20 < 0.45` 等（`scan.py:2104-2127`），而 `parameters.py` 本应从 `stock-parameters.json` 读阈值。

**11. 阶段间无 schema，静默退化。** scan→ai→midday→lifecycle 间 JSON 纯 `.get()` 鸭子类型，字段名（`shortlist`/`best_score`/`tier`/`suggested_action`）是隐式契约。上游重命名会静默退化成空列表而非报错。`data/schemas/` 只有一个 prose 文档和一个重复的参数文件。

**12. 配置散落 5+ 处。** `.env`、`config/openclaw/prism_cron_jobs.json`、`data/config/stock-parameters.json`（与 `data/schemas/stock-parameters.json` 重复）、`packages/stock_parameter_config.py`（Python 当配置）、`refresh_policy.py` 的 `CRON_POLICIES`。cron 任务定义在 3 处需手动同步，故有 `validate_cron_policies`（`refresh_policy.py:977`）专门检测漂移——**已知隐患的补丁**。

### 🟠 P1 — 鲁棒性

**13. 普遍吞异常。** `except Exception`/裸 `except`：app.py 26 处、dashboard_data.py 34 处、decision_ledger.py 11 处、scan.py 24 处。很多吞成 `pass`/`continue`/`return None`。`tushare_factors.py:3` 文档串明"missing 数据永不抛错"——配合零日志，数据缺失 bug 完全不可见。

**14. 数据采集绕过 gateway。** provider `gateway.py:400-467` 有多源回退，但 harvest 脚本直接调 `ts.pro_api()`（`harvest_tinyshare_universe_overnight.py:290-319`），失败就 `SystemExit`，无回退。TinyShare 是正式数据的唯一权威源（`license_scope = authorized_tinyshare_proxy`）。供应商宕机/限流时只能靠调度器 catchup 重试。

**15. 前端股票代码归一化三套实现。** `hooks.ts:196-207` 用正则 `^(?:sh|sz|bj)?(\d{6})$`，`portfolio-utils.ts:30,41` 用同样正则，`watchlist-manager-panel.tsx:20-22` 却用 `value.replace(/\D/g,"").slice(0,6)`。算法不一致是潜在 bug。

### 🟡 P2 — 整洁度

- **16.** README 暗示运行时数据在 `data/history/`，实际在 `packages/data/`（gitignored）。文档与实现不符。
- **17.** `historical_edge/` 引擎 `build_historical_edge_snapshot(sample_pool=None)` 永远返回桩（`__init__.py:71-83`），唯一调用方硬传 None（`dashboard_data.py:10890`）。1488 行代码运行时产出为零。
- **18.** 评估快照 `manifest.json:4` 钉死 2026-04-23，但 `stock-analyzer/data/daily_snapshots/` 已有到 2026-06-18 的数据。验收基线滞后 2 个月。
- **19.** 13 个 `run_*.sh` 脚本严重重复（3 个 cron wrapper、3 个 scan-only 脚本、3 个大脚本各自重写 BASE_DIR/PYTHONPATH/quarantine 逻辑）。
- **20.** `next.config.ts:9-11` 暴露 `NEXT_PUBLIC_PRISM_BACKEND_ORIGIN` 但前端零代码读取它（死暴露）。`settings-workspace.tsx:573` 硬编码 `http://localhost:8000`（与后端默认 8001 不符）。

---

## 3. 优点（为平衡）

系统不是一团糟，核心链路设计有可取之处：

- **provider/gateway 层结构良好**：token 永不进 params/logs/errors（`providers/tushare.py:6-8`），AST 守卫禁止 providers 外的直接 HTTP（`guardrails.py`），限流分类支持中英文。
- **调度器单机鲁棒性 OK**：文件锁去重、PID 存活检查、孤儿检测、catchup 窗口、信号处理、损坏 DB 隔离恢复。
- **decision-ledger capture 钩子设计安全**：永不改写任务退出码（`prism_scheduled_job.py:131-196`）。
- **前端无 TODO/FIXME 垃圾**：代码整洁度好，legacy 重定向集中文档化。
- **隐私擦除机械化可审计**：`scripts/scrub-secrets.py` + 配套测试。

---

## 4. 建议的处置优先级（供决策，本次不实施）

| 优先级 | 动作 | 理由 | 工作量 |
|--------|------|------|--------|
| **必做(防自毁)** | 给 trading_calendar 加 2027 节假日 + 永久机制(接交易所日历 API) | 否则 2027-01-04 全系统停 | 小 |
| **必做(防数据爆炸)** | 加 retention 任务清理 prism_data/scheduled_runs/runtime | 7.8G 会撑爆磁盘 | 中 |
| **必做(防状态损坏)** | 调度器状态改原子写(temp-rename) | 已有损坏前科 | 小 |
| **高价值** | 把 forward_return_labels 接进 lifecycle 退出回填(见发现页报告选项A) | quant 死代码变活，直接解决"只跟踪一天" | 中 |
| **高价值** | 拆 dashboard_data.py 成 ~12 个领域模块 | 14605 行不可维护 | 大 |
| **中价值** | 决定 quant 层去留：接入 or 归档 | 6357 行死代码是负担 | 中 |
| **中价值** | 给阶段间 JSON 加 schema(pydantic) | 字段漂移静默退化 | 中 |
| **中价值** | 删 stock-screener/、清理 control_panel 三目录 shim | 降低新人认知负担 | 小 |
| **低价值** | 评估闸门重写(查预测质量而非字段存在) | 现在是自欺欺人 | 大 |
| **低价值** | 引入 SQLite/PG 替代文件 JSON | 多 worker 才需要 | 大 |

---

## 5. 关键交叉发现（跨域）

1. **"只跟踪一天"是三处缺陷的合谋**：lifecycle 后端默认 `--days-back 3`（有能力）→ 前端只消费 `yesterday_trial_review`（二值）→ quant 的 forward_return 没人接（基础设施闲置）。三个域各自正常，拼起来才暴露。详见 `discovery-page-design-review-2026-06-19.md`。

2. **"评估通过"是假象**：评估器查字段存在（领域D）→ 用 stock-analyzer 的 2026-04 旧快照（领域D）→ 不碰 quant 的真实回测能力（领域D）。整套验收是闭环自证。

3. **"无数据库"渗透到每个域**：后端 13 个全局缓存 + 手写 `_clear_*`（领域B）、调度器非原子状态（领域E）、screener 阶段间鸭子类型（领域C）。一个 sqlite/PG 会同时缓解多处。

---

## 附录：审计方法与证据

- 5 个并行 Explore agent 分域：前端、后端、screener、quant/评估、运行时/数据
- 所有量化数字（行数、文件数、字节数）均由 `wc -l` / `find | wc -l` / `du -sh` 实测
- 每条问题带 `文件:行号` 引用，可在报告中检索定位
- 本报告与 `discovery-page-design-review-2026-06-19.md` 互补：后者是产品页专项，本报告是系统全景
