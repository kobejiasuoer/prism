# 研究版价格K线补洞报告

生成时间：2026-04-15 17:11:02
股票池：aggressive
候选代码数：29
候选日期范围：2024-02-01 ~ 2024-02-29
目标持有窗口：5 个交易日
额外未来缓冲：16 个自然日
AI 目录：runtime/stock-screener/data/research_backfill/ai_history
Scan 目录：runtime/stock-screener/data/research_backfill/history
价格K线缓存：runtime/stock-screener/data/research_backfill/cache/price_kline

## 执行结果

- 已覆盖无需抓取：29
- 新补成功：0
- 补后仍有缺口：0
- 抓取失败：0

## 代码明细

| 代码 | 名称 | 候选日期 | 来源 | 当前缓存末日 | 请求区间 | 抓取源 | 状态 | 补后缓存末日 | 仍缺日期 |
|---|---|---|---|---|---|---|---|---|---|
| 000002 | 万 科Ａ | 2024-02-08,2024-02-20,2024-02-21 | ai_shortlist,scan_combined,scan_hot | 2024-03-12 | - | cached | covered | 2024-03-12 | - |
| 000063 | 中兴通讯 | 2024-02-27,2024-02-29 | ai_shortlist,scan_combined,scan_growth,scan_hot | 2024-03-12 | - | cached | covered | 2024-03-12 | - |
| 000100 | TCL科技 | 2024-02-29 | ai_analyzer,ai_shortlist,scan_combined | 2024-03-12 | - | cached | covered | 2024-03-12 | - |
| 000661 | 长春高新 | 2024-02-06 | ai_analyzer,ai_shortlist,scan_combined | 2024-03-12 | - | cached | covered | 2024-03-12 | - |
| 000733 | 振华科技 | 2024-02-07,2024-02-27,2024-02-29 | ai_shortlist,scan_combined,scan_growth,scan_hot | 2024-03-12 | - | cached | covered | 2024-03-12 | - |
| 000938 | 紫光股份 | 2024-02-22,2024-02-26,2024-02-27,2024-02-29 | ai_shortlist,scan_combined,scan_growth,scan_hot | 2024-03-12 | - | cached | covered | 2024-03-12 | - |
| 000977 | 浪潮信息 | 2024-02-19,2024-02-20,2024-02-22,2024-02-23,2024-02-26,2024-02-27,2024-02-29 | ai_analyzer,ai_shortlist,scan_combined,scan_growth,scan_hot | 2024-03-12 | - | cached | covered | 2024-03-12 | - |
| 002049 | 紫光国微 | 2024-02-21,2024-02-26,2024-02-29 | ai_shortlist,scan_combined,scan_growth,scan_hot | 2024-03-12 | - | cached | covered | 2024-03-12 | - |
| 002129 | TCL中环 | 2024-02-01,2024-02-06,2024-02-08,2024-02-23 | ai_shortlist,scan_combined,scan_hot,scan_rebound | 2024-03-12 | - | cached | covered | 2024-03-12 | - |
| 002230 | 科大讯飞 | 2024-02-01,2024-02-08,2024-02-19,2024-02-22,2024-02-26,2024-02-27 | ai_shortlist,scan_combined,scan_hot | 2024-03-12 | - | cached | covered | 2024-03-12 | - |
| 002236 | 大华股份 | 2024-02-19 | ai_shortlist,scan_combined | 2024-03-12 | - | cached | covered | 2024-03-12 | - |
| 002271 | 东方雨虹 | 2024-02-21 | ai_shortlist,scan_combined | 2024-03-12 | - | cached | covered | 2024-03-12 | - |
| 002410 | 广联达 | 2024-02-06,2024-02-07,2024-02-08 | ai_analyzer,ai_shortlist,scan_combined,scan_hot,scan_rebound | 2024-03-12 | - | cached | covered | 2024-03-12 | - |
| 002459 | 晶澳科技 | 2024-02-01,2024-02-06,2024-02-23 | ai_shortlist,scan_combined,scan_hot,scan_rebound | 2024-03-12 | - | cached | covered | 2024-03-12 | - |
| 002466 | 天齐锂业 | 2024-02-28,2024-02-29 | ai_shortlist,scan_combined,scan_hot | 2024-03-12 | - | cached | covered | 2024-03-12 | - |
| 002555 | 三七互娱 | 2024-02-06,2024-02-19,2024-02-27 | ai_shortlist,scan_combined | 2024-03-12 | - | cached | covered | 2024-03-12 | - |
| 002821 | 凯莱英 | 2024-02-07 | ai_shortlist,scan_combined | 2024-03-12 | - | cached | covered | 2024-03-12 | - |
| 600132 | 重庆啤酒 | 2024-02-21,2024-02-23 | ai_shortlist,scan_combined | 2024-03-12 | - | cached | covered | 2024-03-12 | - |
| 600438 | 通威股份 | 2024-02-01 | ai_shortlist,scan_combined,scan_rebound | 2024-03-12 | - | cached | covered | 2024-03-12 | - |
| 600570 | 恒生电子 | 2024-02-27 | ai_shortlist | 2024-03-12 | - | cached | covered | 2024-03-12 | - |
| 600732 | 爱旭股份 | 2024-02-01,2024-02-23 | ai_shortlist,scan_combined,scan_hot,scan_rebound | 2024-03-12 | - | cached | covered | 2024-03-12 | - |
| 600745 | 闻泰科技 | 2024-02-08,2024-02-29 | ai_shortlist,scan_combined | 2024-03-12 | - | cached | covered | 2024-03-12 | - |
| 601012 | 隆基绿能 | 2024-02-06 | ai_shortlist,scan_combined | 2024-03-12 | - | cached | covered | 2024-03-12 | - |
| 601059 | 信达证券 | 2024-02-28 | ai_shortlist,scan_combined | 2024-03-12 | - | cached | covered | 2024-03-12 | - |
| 601236 | 红塔证券 | 2024-02-21 | ai_shortlist,scan_combined | 2024-03-12 | - | cached | covered | 2024-03-12 | - |
| 601615 | 明阳智能 | 2024-02-01 | scan_rebound | 2024-03-12 | - | cached | covered | 2024-03-12 | - |
| 601699 | 潞安环能 | 2024-02-22 | ai_shortlist,scan_combined | 2024-03-12 | - | cached | covered | 2024-03-12 | - |
| 601901 | 方正证券 | 2024-02-26,2024-02-29 | ai_analyzer,ai_shortlist | 2024-03-12 | - | cached | covered | 2024-03-12 | - |
| 603019 | 中科曙光 | 2024-02-19,2024-02-22,2024-02-26,2024-02-28,2024-02-29 | ai_shortlist,scan_combined,scan_hot | 2024-03-12 | - | cached | covered | 2024-03-12 | - |

## 结论

- 当前候选样本所需的未来K线已补齐，可以直接重跑 review 检查 5d 覆盖。
