# Config 统一：评估结论（无需行动）

- 日期：2026-06-20
- 范围：审计问题 12（config 散落 5+ 处）的复核
- 结论：**审计夸大了此项；现有 config 结构各自有合理角色，无有害重复，不统一。**

## 复核发现

审计称"config 散落 5+ 处需统一"。逐项复核后：

| 配置源 | 角色 | 是否有害重复 |
|--------|------|-------------|
| `data/config/stock-parameters.json` | 阈值**数值** | 否（config 数据源） |
| `data/schemas/stock-parameters.json` | 阈值**schema 校验器** | 否（与上者 DIFFER 是有意的——一个是值一个是 schema） |
| `packages/stock_parameter_config.py` | config **加载器**（读 JSON + 校验） | 否（loader，非重复） |
| `packages/stock_parameters.py` | **消费者**（导出 WATCHLIST_RULE_THRESHOLDS 等具名阈值） | 否（consumer，非重复；import stock_parameter_config） |
| `config/openclaw/prism_cron_jobs.json` | 外部 cron 交付规范 | 否 |
| `refresh_policy.py` CRON_POLICIES | 内部 cron 调度 | **已有 `validate_cron_policies` 守护两者漂移** |
| `.env` | secrets + ports | 否（运行时 secrets 不该进 repo config） |

## 关键判断
1. `stock_parameter_config.py`（loader）和 `stock_parameters.py`（consumer）是**分层**，不是重复。强行合并会增加耦合。
2. `data/config/` vs `data/schemas/` 的两份 `stock-parameters.json` 是 config-vs-schema 模式，标准实践。
3. 唯一真隐患（cron 漂移）已有 `validate_cron_policies` 守护（refresh_policy.py:977），且本轮整改新加的 retention_cleanup/exit_return_update 两个 cron job 都同步更新了双份配置，验证未漂移。

## 结论
此项**不需要行动**。统一会引入无收益的间接层。审计的"5+ 处"计数把不同角色的 config 源混算了。关闭此项。
