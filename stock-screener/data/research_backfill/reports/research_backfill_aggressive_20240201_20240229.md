# 研究版历史补档报告

生成时间：2026-04-15 19:55:24
股票池：aggressive
日期范围：2024-02-01 ~ 2024-02-29
未来收益缓冲：额外预拉 12 个自然日K线用于 next/3d/5d 回看
补档结果：成功 15 天 | 跳过 6 天
scan 输出目录：runtime/stock-screener/data/research_backfill/history
ai 输出目录：runtime/stock-screener/data/research_backfill/ai_history

## 研究边界

- 历史价格使用东方财富日线K线回放
- 历史资金流暂用价格量能代理，不等同真实东方财富日频资金流
- 基本面暂用当前快照近似，不等同严格历史披露时点
- 股票池暂用当前可取到的池子近似，不等同严格历史成分股

## 每日结果

| 日期 | 状态 | Stage1 | Stage2 | 阀门 | 主线 | Shortlist | 备注 |
|---|---|---:|---:|---|---|---:|---|
| 2024-02-01 | ok | 22 | 22 | off | 光伏链 | 10 | - |
| 2024-02-02 | ok | 1 | 1 | off | 光伏链 | 0 | - |
| 2024-02-05 | ok | 10 | 10 | off | 消费电子链 | 2 | - |
| 2024-02-06 | ok | 30 | 30 | on | 游戏传媒链 | 11 | - |
| 2024-02-07 | ok | 30 | 30 | on | 有色资源链 | 10 | - |
| 2024-02-08 | ok | 30 | 30 | limited | 光伏链 | 11 | - |
| 2024-02-09 | skipped_no_pool_snapshot | - | - | - | - | - | skipped_no_pool_snapshot |
| 2024-02-12 | skipped_no_pool_snapshot | - | - | - | - | - | skipped_no_pool_snapshot |
| 2024-02-13 | skipped_no_pool_snapshot | - | - | - | - | - | skipped_no_pool_snapshot |
| 2024-02-14 | skipped_no_pool_snapshot | - | - | - | - | - | skipped_no_pool_snapshot |
| 2024-02-15 | skipped_no_pool_snapshot | - | - | - | - | - | skipped_no_pool_snapshot |
| 2024-02-16 | skipped_no_pool_snapshot | - | - | - | - | - | skipped_no_pool_snapshot |
| 2024-02-19 | ok | 30 | 30 | off | AI信息链 | 10 | - |
| 2024-02-20 | ok | 30 | 30 | off | AI硬件链 | 10 | - |
| 2024-02-21 | ok | 30 | 30 | off | 建材链 | 7 | - |
| 2024-02-22 | ok | 30 | 30 | off | AI信息链 | 11 | - |
| 2024-02-23 | ok | 30 | 30 | off | 汽车链 | 10 | - |
| 2024-02-26 | ok | 30 | 30 | off | AI信息链 | 10 | - |
| 2024-02-27 | ok | 30 | 30 | limited | AI信息链 | 15 | - |
| 2024-02-28 | ok | 30 | 30 | off | AI信息链 | 7 | - |
| 2024-02-29 | ok | 30 | 30 | on | AI信息链 | 12 | - |
