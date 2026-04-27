# Prism 数据存储治理规划草案

日期：2026-04-25
状态：审阅草案

## 1. 背景

Prism 现在仍处在本地优先、文件优先的阶段。这个阶段的好处是简单、透明、容易调试；坏处是随着运行次数、股票池、回测、报告和控制台状态变多，数据会逐渐失去边界。

当前最大的问题不是“用了 JSON”，而是：

- 状态数据、运行产物、缓存、历史归档混在多个目录里。
- 页面和脚本直接读写路径，缺少统一存储入口。
- 最新结果、历史快照、公开脱敏历史之间的边界不够清楚。
- 没有 artifact 索引，页面查历史时只能扫文件夹。
- 后续如果迁移 SQLite / PostgreSQL，会牵动大量业务代码。

这份文档的目标是先把存储边界和迁移路线定下来，等审阅通过后再进入实现。

## 2. 当前数据分布

### 2.1 控制台运行状态

当前位置：

- `apps/data/control_panel_state/ask_recent_queries.json`
- `apps/data/control_panel_state/refresh_state.json`
- `apps/data/control_panel_state/today_action_decisions.json`
- `apps/data/control_panel_runs/`
- `apps/data/control_panel_runs/logs/`

特点：

- 属于运行时状态和任务元数据。
- 会被页面和后台任务频繁更新。
- 适合优先收进统一状态存储。

### 2.2 工作流产物

当前位置：

- `stock-screener/data/scan_result.json`
- `stock-screener/data/ai_screening_result.json`
- `stock-screener/data/ai_history/`
- `stock-screener/data/stale_outputs/`
- `stock-screener/data/quality_gate_*.json`
- `stock-analyzer/data/daily_snapshots/`
- `apps/data/command_brief/`

特点：

- 有些是“latest”结果，有些是历史快照。
- 文件本身适合保留，因为它们是审计证据。
- 但需要一个统一索引来记录类型、时间、来源、关联任务和路径。

### 2.3 缓存数据

当前位置：

- `stock-analyzer/data/fund_flow_cache/`
- `stock-analyzer/data/fundamentals_cache/`
- `packages/screener` 运行过程中产生的 provider cache

特点：

- 可以重建，不应和核心业务状态混为一谈。
- 需要 TTL、失效策略和可清理边界。

### 2.4 公开历史归档

当前位置：

- `data/history/ai_history/`
- `data/history/quality_gates/`
- `data/history/cron_logs/`
- `data/history/reports/`
- `data/history/control_panel_runs/`
- `data/history/daily_snapshots/`
- `data/history/stale_outputs/`

特点：

- 这是公开仓库的脱敏历史层。
- 不应该作为运行时写入的第一落点。
- 更适合作为从 runtime/artifacts 导出的审计归档。

### 2.5 配置和 Schema

当前位置：

- `data/config/`
- `data/schemas/`
- `stock-analyzer/config/stocks.json`

特点：

- 配置属于“可编辑业务数据”，需要版本和校验。
- 短期可以继续保留 JSON 文件，但读写应统一经过 repository。

## 3. 存储设计目标

1. **统一入口**
   所有新代码不再直接拼路径读写业务数据，而是通过 storage/repository 层访问。

2. **本地优先，数据库就绪**
   第一阶段使用 SQLite，不引入服务依赖；接口设计保持后续迁移 PostgreSQL 的空间。

3. **状态入库，产物留文件**
   可编辑状态、任务状态、索引数据进数据库；报告、快照、日志等原始证据继续以文件保存。

4. **文件可审计，数据库可查询**
   文件负责保存原文，数据库负责检索、关联、去重、排序和页面展示。

5. **运行数据和公开历史分离**
   runtime 是本机运行源；`data/history` 是脱敏后可发布的历史归档。

6. **可回滚、可迁移、可清理**
   每类数据都要有来源、保留周期、备份方式和清理策略。

## 4. 目标目录结构

建议逐步收敛到下面的结构：

```text
data/
  config/                 # 业务配置，人工可编辑，带 schema 校验
  schemas/                # JSON Schema 和数据契约
  runtime/                # 本机运行状态，默认不作为公开历史源
    prism.db              # SQLite 主库
    runs/
      logs/               # 后台任务日志
    latest/               # latest 指针或兼容导出
    state_exports/        # 状态表的 JSON 备份/兼容导出
  artifacts/              # 原始运行产物，文件不可变或尽量不可变
    command_brief/
    screener/
    analyzer/
    evaluation/
    reports/
    quality_gates/
    snapshots/
  cache/                  # 可重建缓存，可按 TTL 清理
    market/
    fundamentals/
    capital_flow/
  history/                # 脱敏后的公开历史归档
  evaluation/             # 评估体系当前输出，可逐步并入 artifacts/evaluation
```

说明：

- `data/runtime/` 是运行时状态中心。
- `data/artifacts/` 是本机原始产物中心。
- `data/history/` 是公开、脱敏、审计用历史，不再承载“运行时默认写入”职责。
- 旧目录短期保留，通过兼容层读写，避免一次性打断现有流程。

## 5. 数据分层

| 数据类型 | 推荐主存储 | 文件是否保留 | 示例 |
| --- | --- | --- | --- |
| 控制台状态 | SQLite | JSON 兼容导出 | refresh state, ask recent |
| 今日决策 | SQLite | JSON 兼容导出 | today action decisions |
| 任务元数据 | SQLite | 可导出 JSON | task run status |
| 任务日志 | 文件 | 是 | run logs |
| 业务配置 | JSON + repository，后续可入库 | 是 | stock parameters, watchlist |
| 工作流快照 | 文件 + artifact index | 是 | scan result, AI screening |
| 报告附件 | 文件 + artifact index | 是 | markdown, txt, docx |
| 质量门结果 | 文件 + artifact index | 是 | quality gate JSON |
| 市场数据缓存 | 文件或 SQLite cache 表 | 可清理 | fund flow, fundamentals |
| 公开历史 | 文件 | 是 | scrubbed `data/history` |

## 6. SQLite 第一阶段范围

第一阶段不追求“一步到位”，只解决最关键的边界问题。

建议新增 SQLite 数据库：

```text
data/runtime/prism.db
```

建议第一批表：

### 6.1 `app_state`

保存小型控制台状态。

核心字段：

- `key`
- `value_json`
- `schema_version`
- `updated_at`

承接：

- `refresh_state.json`
- `ask_recent_queries.json`
- `today_action_decisions.json`

### 6.2 `task_runs`

保存后台任务状态和元数据。

核心字段：

- `run_id`
- `task_name`
- `title`
- `status`
- `started_at`
- `finished_at`
- `exit_code`
- `pid`
- `cwd`
- `command_json`
- `log_path`
- `metadata_json`

承接：

- `apps/data/control_panel_runs/*.json`

### 6.3 `artifacts`

保存所有运行产物索引。

核心字段：

- `artifact_id`
- `artifact_type`
- `source`
- `run_id`
- `trade_date`
- `code`
- `path`
- `path_kind`
- `sha256`
- `size_bytes`
- `mtime`
- `generated_at`
- `schema_version`
- `metadata_json`

承接索引：

- command brief
- reports
- quality gates
- AI screening snapshots
- daily snapshots
- stale outputs
- evaluation reports

### 6.4 `storage_migrations`

记录存储迁移版本。

核心字段：

- `version`
- `name`
- `applied_at`

## 7. 统一存储入口

建议新增一个独立存储模块，避免控制台、脚本、workflow 各自拼路径。

候选位置：

```text
packages/prism_storage/
  __init__.py
  paths.py
  json_store.py
  sqlite_store.py
  artifacts.py
  analytics.py
  history.py
  mirror.py
  repositories.py
```

职责：

- `paths.py`：统一定义数据根目录、运行目录、artifact 目录、cache 目录。
- `json_store.py`：提供原子 JSON 读写、schema version、兼容导出。
- `sqlite_store.py`：管理 SQLite 连接、迁移、事务。
- `artifacts.py`：登记 artifact、计算 hash、规范相对路径。
- `analytics.py`：把 artifact ledger 等结构化数据导出为 JSONL；DuckDB/Parquet 作为可选增强。
- `history.py`：把本地 artifact store 和 runtime 元数据导出到 `data/history/`。
- `mirror.py`：把仍在旧路径生成的产物镜像到 `data/artifacts/` 并登记 ledger。
- `repositories.py`：提供业务级读写接口，例如 `refresh_state_repo`、`task_run_repo`。

调用规则：

- 控制台页面不直接读写 JSON 文件。
- 后台任务不直接生成 task meta JSON，改由 repository 写入。
- workflow 仍可生成文件，但生成后必须登记 artifact index。
- 所有持久化路径优先保存 workspace-relative path，避免绝对路径污染历史数据。
- 自选股配置短期继续使用 `stock-analyzer/config/stocks.json`，但必须通过 `WatchlistConfigRepository` 或其上层业务函数读写。

## 8. 兼容策略

为了降低迁移风险，建议保留一段时间的兼容导出。

### 8.1 读路径兼容

读取顺序：

1. 优先读 SQLite。
2. 如果 SQLite 没有对应数据，回退旧 JSON。
3. 回退成功后可写入 SQLite，完成 lazy migration。

### 8.2 写路径兼容

写入顺序：

1. 写 SQLite。
2. 同步导出 JSON 到 `data/runtime/state_exports/` 或旧路径。
3. 等所有调用方切换完成后，停止旧路径写入。

### 8.3 artifact 兼容

第一阶段不移动历史文件，只扫描登记索引。

第二阶段开始，新产物写到 `data/artifacts/`，旧产物通过索引继续可查。

## 9. 迁移阶段

### Phase 0：规划和边界确认

产出：

- 本文档。
- 数据分类表。
- 需要审阅的开放问题。

不改运行逻辑。

### Phase 1：路径注册和存储模块

目标：

- 新增 `prism_storage` 模块。
- 定义 canonical data roots。
- 提供原子 JSON 工具和 SQLite migration 工具。
- 增加测试，确保目录创建、路径校验、相对路径规范可用。

影响范围：

- 新增代码为主。
- 不迁移业务数据。

### Phase 2：控制台状态入库

目标：

- `refresh_state`
- `ask_recent_queries`
- `today_action_decisions`

改为通过 repository 读写。

兼容：

- 保留旧 JSON 导出。
- 测试仍可通过临时文件/临时库隔离。

### Phase 3：任务运行记录入库

目标：

- `task_runs` 成为任务元数据主源。
- 日志继续保留文件。
- `/api/runs/{run_id}` 和 run list 从 repository 读取。

兼容：

- 旧 `apps/data/control_panel_runs/*.json` 先 backfill 到 SQLite。
- 一段时间内继续导出 JSON，方便排障。

### Phase 4：artifact index

目标：

- 扫描现有 artifact，写入 `artifacts` 表。
- 控制台列表页优先从 artifact index 查询。
- 文件本体不移动。

收益：

- 不再依赖页面实时扫大量目录。
- 可以按日期、类型、股票代码、任务批次查询。
- 后续支持清理、备份、脱敏导出。

### Phase 5：新产物写入规范化

目标：

- 新生成的报告、快照、quality gate、command brief 写入 `data/artifacts/`。
- `latest` 结果通过 `data/runtime/latest/` 或数据库指针表达。
- workflow 脚本通过环境变量获取输出路径，而不是硬编码分散目录。

### Phase 6：公开历史导出

目标：

- `data/history/` 不再由运行流程直接写入。
- 通过 scrub/export 脚本从 `runtime + artifacts` 生成公开历史。
- 导出时统一处理隐私路径、token、webhook、个人标识。

### Phase 7：PostgreSQL 准备

触发条件：

- 多人使用。
- 服务端部署。
- 后台 worker 增多。
- 需要权限、审计、跨机器访问。

迁移方式：

- repository 接口不变。
- SQLite schema 平滑迁移到 PostgreSQL。
- artifact 文件迁到对象存储或继续本机挂载。

## 10. 文件命名规范

建议统一使用：

```text
{domain}_{artifact_type}_{trade_date}_{run_stamp}.{ext}
```

示例：

```text
screener_ai_screening_2026-04-21_091022.json
screener_quality_gate_2026-04-21_131005.json
command_brief_report_2026-04-21_120845.md
analyzer_daily_snapshot_2026-04-21_092500.json
```

要求：

- 文件名包含 domain、type、日期、时间戳。
- 文件内容包含 `schema_version` 和 `generated_at`。
- 数据库记录保存 `sha256`，用于去重和完整性校验。
- 持久化 JSON 中不保存本机绝对路径，除非字段明确标记为 transient。

## 11. 保留和清理策略

建议规则：

- `data/cache/`：可删除，可按 TTL 清理。
- `data/runtime/runs/logs/`：保留最近 30-90 天，失败任务可更久。
- `data/artifacts/`：默认长期保留，按类型设置归档策略。
- `data/runtime/prism.db`：每日备份，保留最近 7-30 份。
- `data/history/`：作为公开历史，由 scrub/export 生成，不自动清理。

建议增加维护命令：

```bash
python -m prism_storage.cli doctor
python -m prism_storage.cli index-artifacts
python -m prism_storage.cli export-history
python -m prism_storage.cli prune-cache
python -m prism_storage.cli backup-db
```

## 12. 测试和验收标准

第一轮改造完成后，应满足：

- 控制台状态读写不再直接依赖旧 JSON 文件。
- 后台任务元数据可以从 SQLite 查询。
- 旧 JSON 数据可以自动迁移或手动 backfill。
- artifact index 可以扫描现有目录并生成记录。
- 页面可以在 SQLite 缺失时回退旧文件，避免迁移中断。
- `pytest -q` 通过。
- `scripts/scrub-secrets.py` 通过。
- 新增 storage tests 覆盖路径、原子写入、迁移、artifact 登记。

## 13. 风险和对策

### 13.1 一次性迁移过大

对策：

- 先做 repository 和兼容层。
- 文件不急着移动。
- 每一阶段都可独立回滚。

### 13.2 历史路径断裂

对策：

- artifact index 同时记录旧路径和 canonical path。
- 预览接口继续支持 workspace 内旧路径。
- 迁移文件时生成 redirect/alias 记录。

### 13.3 SQLite 并发写入

对策：

- 开启 WAL。
- 控制台状态写入使用短事务。
- 后台任务元数据按 run_id 写入，避免热点行。
- 真正多人并发时迁移 PostgreSQL。

### 13.4 数据库损坏或误删

对策：

- 每日备份 `prism.db`。
- artifact 文件仍是事实证据。
- 关键状态保留 JSON export。
- 提供 `index-artifacts` 从文件重建索引。

### 13.5 公开仓库隐私边界变模糊

对策：

- `runtime` 和原始 `artifacts` 默认视为本机私有。
- `data/history` 只由 scrub/export 生成。
- 所有导出脚本复用隐私 scrub 规则。

## 14. 需要审阅确认的问题

1. 是否接受 `data/runtime/prism.db` 作为第一阶段 SQLite 默认位置？
2. 是否接受“状态入库、产物留文件、artifact 建索引”的总体路线？
3. `data/history/` 是否只作为脱敏公开历史，而不再作为运行时默认写入目录？
4. 自选股配置 `stock-analyzer/config/stocks.json` 是否第一阶段继续保留 JSON，第二阶段再讨论入库？
5. 运行日志保留周期建议是 30 天、90 天，还是永久保留失败日志？
6. 新产物 canonical 目录是否采用 `data/artifacts/`，还是继续复用 `data/history/` 但加强索引？
7. 后续是否需要把回测数据单独放入 `data/research/` 或 `data/backtests/`？

## 15. 推荐决策

我的建议是：

1. 第一阶段采用 SQLite，本地文件仍保留。
2. 立即收束控制台状态和任务运行记录。
3. 不急着移动几千个历史文件，先建立 artifact index。
4. 保留 `data/history/` 的公开历史定位。
5. 新产物逐步写入 `data/artifacts/`，旧路径通过兼容层过渡。
6. 等出现多人协作或服务端部署，再迁移 PostgreSQL。

这条路线改动可控，也能明显改善后续扩展性。
