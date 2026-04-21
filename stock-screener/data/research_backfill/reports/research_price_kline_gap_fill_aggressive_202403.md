# 研究版价格K线补洞报告

生成时间：2026-04-15 17:19:54
股票池：aggressive
候选代码数：40
候选日期范围：2024-03-01 ~ 2024-03-29
目标持有窗口：5 个交易日
额外未来缓冲：16 个自然日
AI 目录：runtime/stock-screener/data/research_backfill/ai_history
Scan 目录：runtime/stock-screener/data/research_backfill/history
价格K线缓存：runtime/stock-screener/data/research_backfill/cache/price_kline

## 执行结果

- 已覆盖无需抓取：40
- 新补成功：0
- 补后仍有缺口：0
- 抓取失败：0

## 代码明细

| 代码 | 名称 | 候选日期 | 来源 | 当前缓存末日 | 请求区间 | 抓取源 | 状态 | 补后缓存末日 | 仍缺日期 |
|---|---|---|---|---|---|---|---|---|---|
| 000002 | 万 科Ａ | 2024-03-11,2024-03-12,2024-03-14 | ai_shortlist,scan_combined,scan_hot,scan_rebound | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 000063 | 中兴通讯 | 2024-03-08,2024-03-28 | ai_shortlist,scan_combined,scan_growth,scan_hot,scan_rebound | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 000100 | TCL科技 | 2024-03-01 | ai_shortlist,scan_combined,scan_hot | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 000625 | 长安汽车 | 2024-03-05,2024-03-07,2024-03-11,2024-03-12,2024-03-13,2024-03-15,2024-03-18,2024-03-21,2024-03-26 | ai_shortlist,scan_combined,scan_growth,scan_hot | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 000661 | 长春高新 | 2024-03-19 | ai_shortlist,scan_combined | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 000733 | 振华科技 | 2024-03-08,2024-03-12,2024-03-15,2024-03-28 | ai_shortlist,scan_combined,scan_growth,scan_hot,scan_rebound | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 000938 | 紫光股份 | 2024-03-01,2024-03-04,2024-03-07,2024-03-28 | ai_shortlist,scan_combined,scan_growth,scan_hot,scan_rebound | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 000977 | 浪潮信息 | 2024-03-01,2024-03-04,2024-03-08,2024-03-18,2024-03-26,2024-03-28 | ai_shortlist,scan_combined,scan_growth,scan_hot | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 002049 | 紫光国微 | 2024-03-01,2024-03-28 | ai_shortlist,scan_combined,scan_growth,scan_hot,scan_rebound | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 002129 | TCL中环 | 2024-03-08,2024-03-18,2024-03-20 | ai_shortlist,scan_combined,scan_hot | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 002180 | 纳思达 | 2024-03-13 | ai_shortlist,scan_combined | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 002230 | 科大讯飞 | 2024-03-01,2024-03-05,2024-03-20,2024-03-28 | ai_shortlist,scan_combined,scan_hot,scan_rebound | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 002236 | 大华股份 | 2024-03-05,2024-03-12,2024-03-25 | ai_shortlist,scan_combined,scan_growth,scan_hot | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 002241 | 歌尔股份 | 2024-03-05,2024-03-06 | ai_shortlist,scan_combined,scan_hot | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 002271 | 东方雨虹 | 2024-03-12,2024-03-14 | ai_shortlist,scan_combined,scan_growth,scan_hot | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 002410 | 广联达 | 2024-03-13 | ai_shortlist,scan_combined,scan_growth,scan_hot | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 002459 | 晶澳科技 | 2024-03-06,2024-03-08,2024-03-26 | ai_shortlist,scan_combined,scan_hot,scan_rebound | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 002555 | 三七互娱 | 2024-03-13,2024-03-19,2024-03-20 | ai_shortlist,scan_combined | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 002709 | 天赐材料 | 2024-03-12 | ai_shortlist,scan_combined | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 002812 | 恩捷股份 | 2024-03-26 | ai_shortlist,scan_combined,scan_rebound | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 002920 | 德赛西威 | 2024-03-19,2024-03-26 | ai_shortlist,scan_combined | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 600048 | 保利发展 | 2024-03-11,2024-03-25 | ai_shortlist,scan_combined,scan_rebound | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 600089 | 特变电工 | 2024-03-06 | ai_shortlist,scan_combined | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 600438 | 通威股份 | 2024-03-11 | ai_shortlist,scan_combined | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 600570 | 恒生电子 | 2024-03-18,2024-03-21 | ai_shortlist,scan_combined | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 600584 | 长电科技 | 2024-03-05,2024-03-27 | ai_shortlist,scan_combined,scan_growth,scan_hot | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 600588 | 用友网络 | 2024-03-21 | ai_shortlist,scan_combined | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 600732 | 爱旭股份 | 2024-03-11,2024-03-20 | ai_shortlist,scan_combined,scan_hot | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 600745 | 闻泰科技 | 2024-03-01,2024-03-04 | ai_shortlist,scan_combined,scan_growth,scan_hot | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 600754 | 锦江酒店 | 2024-03-14 | ai_shortlist,scan_combined | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 601012 | 隆基绿能 | 2024-03-11 | ai_shortlist,scan_combined | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 601360 | 三六零 | 2024-03-04,2024-03-20,2024-03-25 | ai_shortlist,scan_combined,scan_hot | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 601865 | 福莱特 | 2024-03-06,2024-03-11,2024-03-19,2024-03-27 | ai_shortlist,scan_combined,scan_growth,scan_hot | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 601878 | 浙商证券 | 2024-03-21,2024-03-22,2024-03-25,2024-03-26,2024-03-27 | ai_shortlist,scan_combined,scan_hot | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 601888 | 中国中免 | 2024-03-15 | ai_shortlist,scan_combined | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 601901 | 方正证券 | 2024-03-01,2024-03-18,2024-03-21,2024-03-29 | ai_shortlist,scan_combined,scan_growth,scan_hot | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 603019 | 中科曙光 | 2024-03-01,2024-03-06,2024-03-11,2024-03-22 | ai_shortlist,scan_combined,scan_hot | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 603259 | 药明康德 | 2024-03-04 | ai_shortlist,scan_combined | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 603290 | 斯达半导 | 2024-03-13 | ai_shortlist,scan_combined | 2024-04-10 | - | cached | covered | 2024-04-10 | - |
| 603986 | 兆易创新 | 2024-03-12 | ai_shortlist,scan_combined | 2024-04-10 | - | cached | covered | 2024-04-10 | - |

## 结论

- 当前候选样本所需的未来K线已补齐，可以直接重跑 review 检查 5d 覆盖。
