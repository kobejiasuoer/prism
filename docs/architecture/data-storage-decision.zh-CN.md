# Prism 数据存储架构决策

日期：2026-04-25
状态：已批准，第一阶段已落地

## 0. 执行状态

截至 2026-04-25，已完成第一轮落地：

- 新增 `packages/prism_storage/` 存储底座。
- 建立 SQLite schema：`app_state`、`task_runs`、`artifacts`、`storage_migrations`。
- 控制台状态已通过 repository 读写，并保留旧 JSON 兼容导出。
- 后台任务元数据已同步写入 `task_runs`，旧 run JSON 可回填。
- artifact ledger 已具备文件登记、目录扫描、doctor 诊断和 CLI 入口。
- 控制台 artifact 候选列表开始优先使用 artifact 索引。
- command brief 新产物默认写入 `data/artifacts/command_brief/`，同时保留旧目录兼容副本。
- 新控制台任务元数据和日志默认写入 `data/runtime/runs/control_panel/`，旧 `apps/data/control_panel_runs/` 仅作为兼容读取源。
- screener 主流程、午盘刷新、午盘确认会把报告、quality gate、状态结果和 stale outputs 镜像到 `data/artifacts/screener/` 并登记 ledger；latest 指针文件仍保留在旧路径。
- analyzer daily snapshot 在新生成时会镜像到 `data/artifacts/analyzer/daily_snapshots/` 并登记 ledger；已有 analyzer snapshot、quality gate、报告可通过 `mirror-analyzer-artifacts` 统一补镜像。
- 自选股配置仍以 `stock-analyzer/config/stocks.json` 作为兼容主文件，但读写已收口到 `WatchlistConfigRepository`，为后续入库保留接口边界。
- analytics 层已提供轻量 JSONL 导出能力，artifact ledger 可导出到 `data/analytics/artifact_index/`；DuckDB/Parquet 仍保持可选依赖，不强制安装。
- public history 层已提供 `export-history` 命令，可从 artifact store 和 task runtime 元数据导出到 `data/history/`，不删除既有历史文件。

仍未执行：

- 不移动旧历史文件。
- 不强制全部 workflow 产物直接写入 `data/artifacts/`；目前 command brief 已默认写入，screener 和 analyzer 采用镜像登记模式。
- 不把自选股配置立即迁入 SQLite；当前只完成 repository 收口和兼容 JSON 主文件。
- 不引入 PostgreSQL 或对象存储。

## 1. 决策摘要

Prism 后续不采用“所有数据都进一个数据库”的路线，也不继续维持“所有数据随意落本地 JSON”的现状。

推荐决策是：

> Prism 采用三层存储架构：Operational Store 管状态，Artifact Store 管原始产物，Analytical Store 管研究分析数据。

三层分别是：

| 层级 | 当前实现 | 后续升级 | 负责内容 |
| --- | --- | --- | --- |
| Operational Store | SQLite | PostgreSQL | 控制台状态、任务状态、自选股状态、今日决策、artifact 元数据 |
| Artifact Store | 本地文件系统 | 对象存储 S3 / MinIO / OSS | 报告、原始 JSON、日志、快照、质量门结果 |
| Analytical Store | Parquet + DuckDB | DuckDB / ClickHouse / 数据仓库 | 回测、历史特征、批量筛选结果、评分演进 |

这比单纯讨论 SQLite 或 PostgreSQL 更稳，因为它先固定数据边界，再选择具体技术。

## 2. 核心判断

Prism 的数据不是一种数据，而是三种不同生命周期的数据：

1. **状态型数据**
   会被页面、任务、用户操作频繁更新。
   例如刷新状态、Ask 最近查询、今日操作决策、后台任务状态、自选股状态。

2. **证据型数据**
   一旦生成，应尽量保持原样，用于审计、复盘和追溯。
   例如 AI screening JSON、quality gate、daily snapshot、报告、日志。

3. **分析型数据**
   需要按日期、股票、批次、指标做大量历史查询和统计。
   例如回测样本、历史特征矩阵、策略评分、筛选结果演进。

这三类数据的最佳存储方式不同。强行混在一起，会让系统越来越重，也越来越难维护。

## 3. 最终推荐决策

### 3.1 状态入库

所有会被更新、覆盖、查询、排序、聚合的运行状态进入 Operational Store。

第一阶段使用：

```text
data/runtime/prism.db
```

原因：

- 本地优先，不需要额外服务。
- 迁移成本低。
- 比散落 JSON 更适合并发、事务、索引和查询。
- 后续可以通过 repository 层迁移到 PostgreSQL。

第一批入库对象：

- `refresh_state`
- `ask_recent_queries`
- `today_action_decisions`
- `task_runs`
- `artifact_index`
- 后续可加入 `watchlist_items`

### 3.2 原始产物留文件

报告、快照、日志、质量门结果、AI 原始输出不直接塞进数据库。

它们进入 Artifact Store：

```text
data/artifacts/
```

数据库只保存索引：

- 类型
- 来源
- 交易日
- 股票代码
- 任务批次
- 文件路径
- hash
- 大小
- 生成时间
- schema 版本
- 关键摘要

这样做的好处是：

- 文件保持可审计。
- 数据库保持轻量。
- 页面查询不需要扫文件夹。
- 后续可以把文件系统替换成对象存储。

### 3.3 研究分析走 Parquet + DuckDB

回测、历史特征、批量筛选结果不建议放 SQLite，也不建议长期放散落 JSON。

它们进入 Analytical Store：

```text
data/analytics/
```

推荐格式：

```text
data/analytics/
  features/
    trade_date=2026-04-21/
      part-000.parquet
  screening_results/
    trade_date=2026-04-21/
      part-000.parquet
  backtests/
    strategy=aggressive_v1/
      run_date=2026-04-25/
        results.parquet
```

查询工具：

- DuckDB 用于本地分析。
- Parquet 用于长期保存和跨工具迁移。

原因：

- Parquet 比 JSON 更适合大批量历史数据。
- DuckDB 查询本地 Parquet 很快。
- 不会把 operational database 变成沉重的数据仓库。

## 4. 不采用的方案

### 4.1 所有数据继续本地 JSON

不采用。

问题：

- 文件越来越多后，查询只能扫目录。
- 状态更新缺少事务。
- 页面、脚本、workflow 容易继续散写路径。
- 后续迁移数据库成本越来越高。

### 4.2 所有数据直接上 PostgreSQL

暂不采用。

问题：

- 当前 Prism 仍是本地优先，直接上 PostgreSQL 会增加部署和维护成本。
- 原始报告、日志、快照不适合全部进关系型数据库。
- 数据边界没有先定好时，上更重的数据库只会把混乱搬进去。

触发条件满足后再升级：

- 多人同时使用。
- 服务端部署。
- 需要权限系统。
- 需要跨机器访问。
- 后台 worker 和任务队列明显增多。

### 4.3 所有历史分析数据放 SQLite

不采用。

问题：

- SQLite 适合状态和轻量查询，不适合长期承载大规模历史特征和回测矩阵。
- 分析型数据列多、行多、按批次追加，Parquet 更合适。

### 4.4 只建目录规范，不建数据库索引

不采用。

问题：

- 目录规范只能减少表面混乱。
- 页面查询、任务关联、去重、复盘仍然需要结构化索引。
- 真正需要的是 artifact ledger，而不只是文件摆放整齐。

## 5. 目标数据边界

### 5.1 Operational Store

职责：

- 保存可变状态。
- 支持事务更新。
- 支持页面和 API 快速查询。
- 保存 artifact 元数据索引。

第一阶段表：

```text
app_state
task_runs
artifacts
storage_migrations
```

第二阶段可加入：

```text
watchlist_items
stock_notes
decision_events
operator_actions
```

### 5.2 Artifact Store

职责：

- 保存原始运行产物。
- 尽量不可变。
- 用 hash 保证完整性。
- 通过数据库索引被检索。

建议目录：

```text
data/artifacts/
  command_brief/
  screener/
    scan/
    ai_screening/
    quality_gates/
    reports/
    stale_outputs/
  analyzer/
    daily_snapshots/
    reports/
  evaluation/
  logs/
```

规则：

- 新产物优先写入 `data/artifacts/`。
- 旧产物先不移动，通过 artifact index 登记。
- 文件内容尽量包含 `schema_version`、`generated_at`、`source`。
- 持久化内容避免保存本机绝对路径。

### 5.3 Analytical Store

职责：

- 保存可批量查询的历史研究数据。
- 支持回测、评分演进、特征分析。
- 与原始 artifact 保持关联。

建议目录：

```text
data/analytics/
  features/
  screening_results/
  backtests/
  scorecards/
  research_sets/
```

规则：

- 使用 Parquet 作为主格式。
- 使用 DuckDB 查询。
- 按 `trade_date`、`strategy`、`run_id` 等字段分区。
- 每批分析数据记录来源 artifact。

## 6. 统一访问原则

从这次改造开始，所有新增持久化代码遵守一个原则：

> 业务代码不直接决定数据落在哪里，只调用 repository。

建议新增模块：

```text
packages/prism_storage/
  paths.py
  sqlite_store.py
  json_store.py
  artifacts.py
  analytics.py
  repositories.py
  cli.py
```

职责：

- `paths.py`：定义 canonical 数据目录。
- `sqlite_store.py`：管理 SQLite、迁移、事务。
- `json_store.py`：兼容旧 JSON 和原子写入。
- `artifacts.py`：登记 artifact、计算 hash、生成索引。
- `analytics.py`：写入 Parquet、提供 DuckDB 查询入口。
- `repositories.py`：提供业务级读写接口。
- `cli.py`：提供迁移、索引、备份、诊断命令。

## 7. 目标目录结构

推荐最终收敛为：

```text
data/
  config/
  schemas/

  runtime/
    prism.db
    state_exports/
    latest/
    backups/

  artifacts/
    command_brief/
    screener/
    analyzer/
    evaluation/
    logs/

  analytics/
    features/
    screening_results/
    backtests/
    scorecards/

  cache/
    market/
    fundamentals/
    capital_flow/

  history/
```

目录定位：

- `runtime`：本机运行状态，不作为公开历史。
- `artifacts`：原始产物，不随意覆盖。
- `analytics`：结构化研究数据。
- `cache`：可重建缓存。
- `history`：脱敏后的公开历史导出。

## 8. 迁移路线

### Phase 0：确认决策

确认本文档中的三层存储路线。

输出：

- 存储决策确认。
- 开放问题结论。
- 第一阶段实施范围。

### Phase 1：建立存储底座

新增：

- `packages/prism_storage/`
- canonical paths
- SQLite migration runner
- repository 基础接口
- artifact 登记工具
- storage doctor 命令

不迁移业务逻辑，只建立底座。

### Phase 2：控制台状态入库

迁移：

- `refresh_state.json`
- `ask_recent_queries.json`
- `today_action_decisions.json`

要求：

- SQLite 为主。
- 旧 JSON 作为兼容导出。
- 测试覆盖旧数据回退和 lazy migration。

### Phase 3：任务运行记录入库

迁移：

- `apps/data/control_panel_runs/*.json`
- `apps/data/control_panel_runs/logs/*.log`

要求：

- 任务元数据进入 `task_runs`。
- 日志仍是文件。
- API 和页面从 repository 查询。
- 旧 run JSON 可 backfill。

### Phase 4：artifact ledger

建立 artifact 索引账本。

扫描并登记：

- command brief
- screener reports
- analyzer reports
- quality gates
- AI screening history
- daily snapshots
- evaluation outputs
- stale outputs

要求：

- 不移动旧文件。
- 记录 hash、mtime、size、type、source、trade_date。
- 控制台 artifact 查询逐步改走索引。

### Phase 5：新产物写入规范化

新产物开始写入：

```text
data/artifacts/
```

要求：

- workflow 通过 storage paths 或环境变量获取输出路径。
- latest 结果通过 `runtime/latest` 或数据库指针表达。
- 旧目录只做兼容，不再作为新增默认写入点。

### Phase 6：分析数据 Parquet 化

迁移或新增：

- 回测结果
- 历史筛选结果
- 特征矩阵
- 评分演进

要求：

- 写入 `data/analytics/`
- 使用 Parquet。
- 提供 DuckDB 查询入口。
- 每条分析数据可追溯到 source artifact。

### Phase 7：公开历史导出规范化

调整：

- `data/history/` 不再作为运行时默认写入目录。
- 由 export/scrub 命令从 `runtime + artifacts + analytics` 生成。

要求：

- 公开历史可重复生成。
- 脱敏规则统一。
- 不泄露本机绝对路径、token、webhook、个人标识。

### Phase 8：PostgreSQL 升级准备

当 Prism 进入多人或服务端阶段：

- Operational Store 从 SQLite 迁移 PostgreSQL。
- repository 接口保持不变。
- Artifact Store 可迁到对象存储。
- Analytical Store 可继续 Parquet/DuckDB，或升级 ClickHouse/数据仓库。

## 9. 第一阶段明确不做什么

第一阶段不做：

- 不移动所有历史文件。
- 不一次性迁移全部 JSON。
- 不上 PostgreSQL。
- 不把报告和日志塞进数据库。
- 不改公开历史 scrub 流程的核心行为。
- 不重写整个 workflow。

第一阶段只做：

- 存储入口。
- SQLite 状态库。
- 控制台状态入库。
- 任务运行记录入库。
- artifact index 的基础能力。

## 10. 验收标准

第一轮实施完成后，应该满足：

- 控制台状态不再依赖散落 JSON 作为唯一数据源。
- 后台任务状态可以从 SQLite 查询。
- 旧 JSON 可回退、可迁移、可导出。
- artifact ledger 能扫描现有文件并建立索引。
- 新代码通过 repository 访问存储。
- 页面查询 artifact 不必实时扫大量目录。
- `pytest -q` 通过。
- `scripts/scrub-secrets.py` 通过。
- 数据库删除后，仍可通过 artifact 文件和 JSON export 恢复关键索引。

## 11. 风险控制

### 11.1 迁移破坏现有页面

控制：

- repository 先读 SQLite，缺失时回退旧 JSON。
- 每一步保留兼容导出。
- 每阶段独立测试。

### 11.2 SQLite 写并发不够

控制：

- 开启 WAL。
- 控制台状态短事务。
- 任务记录按 run_id 写入。
- 多人阶段迁移 PostgreSQL。

### 11.3 Artifact 文件丢失

控制：

- artifact 表记录 hash 和 size。
- storage doctor 检查索引和文件一致性。
- 关键目录纳入备份。

### 11.4 分析数据膨胀

控制：

- 分析数据进入 Parquet。
- 按日期、策略、批次分区。
- 不进入 Operational Store。

### 11.5 公开历史泄露隐私

控制：

- `data/history` 只由 scrub/export 生成。
- runtime/artifacts 默认视为本机私有。
- 持久化记录使用 workspace-relative path。

## 12. 需要你拍板的问题

1. 是否确认采用“三层存储”：SQLite/PostgreSQL + Artifact Store + Parquet/DuckDB？
2. 是否确认 `data/runtime/prism.db` 作为第一阶段 SQLite 位置？
3. 是否确认新产物 canonical 目录为 `data/artifacts/`？
4. 是否确认分析型数据新建 `data/analytics/`？
5. 是否确认 `data/history/` 只作为脱敏公开历史导出层？
6. 是否确认第一阶段先迁控制台状态、任务运行记录、artifact index？
7. 自选股配置是否暂时保留 JSON，等状态库稳定后再讨论入库？

## 13. 我的推荐结论

我建议拍板以下结论：

1. 确认三层存储架构。
2. 第一阶段不引入外部数据库服务，使用 SQLite。
3. 原始产物不入库，只建 artifact ledger。
4. 研究和回测数据走 Parquet + DuckDB。
5. `data/history` 从运行时目录降级为公开历史导出目录。
6. 所有新增持久化代码必须走 `prism_storage` repository。
7. 等多人协作或服务端部署，再迁移 PostgreSQL 和对象存储。

这条路线的优势是：现在改动可控，后面扩展不堵路。它不是为了显得“企业级”，而是让 Prism 的数据从一开始就有清楚边界。
