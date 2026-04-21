# 研究版价格K线补洞报告

生成时间：2026-04-15 15:35:26
股票池：aggressive
候选代码数：8
候选日期范围：2024-01-08 ~ 2024-01-12
目标持有窗口：5 个交易日
额外未来缓冲：16 个自然日
AI 目录：runtime/stock-screener/data/research_backfill/ai_history
Scan 目录：runtime/stock-screener/data/research_backfill/history
价格K线缓存：runtime/stock-screener/data/research_backfill/cache/price_kline

## 执行结果

- 已覆盖无需抓取：0
- 新补成功：8
- 补后仍有缺口：0
- 抓取失败：0

## 代码明细

| 代码 | 名称 | 候选日期 | 来源 | 当前缓存末日 | 请求区间 | 抓取源 | 状态 | 补后缓存末日 | 仍缺日期 |
|---|---|---|---|---|---|---|---|---|---|
| 600732 | 爱旭股份 | 2024-01-09,2024-01-11 | ai_shortlist,scan_combined,scan_hot | 2024-01-12 | 2024-01-09 ~ 2024-01-27 | tx | ok | 2024-01-26 | - |
| 601012 | 隆基绿能 | 2024-01-09 | ai_shortlist,scan_combined | 2024-01-12 | 2024-01-09 ~ 2024-01-25 | tx | ok | 2024-01-25 | - |
| 601888 | 中国中免 | 2024-01-09 | ai_shortlist,scan_combined,scan_rebound | 2024-01-12 | 2024-01-09 ~ 2024-01-25 | tx | ok | 2024-01-25 | - |
| 603019 | 中科曙光 | 2024-01-11 | ai_shortlist,scan_combined,scan_rebound | 2024-01-12 | 2024-01-11 ~ 2024-01-27 | tx | ok | 2024-01-26 | - |
| 603392 | 万泰生物 | 2024-01-08 | ai_shortlist,scan_combined | 2024-01-12 | 2024-01-08 ~ 2024-01-24 | tx | ok | 2024-01-24 | - |
| 603799 | 华友钴业 | 2024-01-11 | ai_shortlist,scan_combined | 2024-01-12 | 2024-01-11 ~ 2024-01-27 | tx | ok | 2024-01-26 | - |
| 603806 | 福斯特 | 2024-01-12 | ai_shortlist,scan_combined | 2024-01-12 | 2024-01-12 ~ 2024-01-28 | tx | ok | 2024-01-26 | - |
| 605117 | 德业股份 | 2024-01-08,2024-01-10,2024-01-11 | ai_shortlist,scan_combined,scan_growth,scan_hot | 2024-01-12 | 2024-01-08 ~ 2024-01-27 | tx | ok | 2024-01-26 | - |

## 结论

- 当前候选样本所需的未来K线已补齐，可以直接重跑 review 检查 5d 覆盖。
