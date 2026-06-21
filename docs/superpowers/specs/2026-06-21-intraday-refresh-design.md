# 盘中增量刷新 设计文档

- 日期：2026-06-21
- 范围：新增盘中每 30 分钟增量刷新候选池行情 + baseline 重算（不调 LLM）

## 问题
发现页的分析结果（阀门/confidence/action）只在 09:40/13:10/13:45 三次 cron 跑，盘中行情变了分析不变。

## 方案
新增 `apps/scripts/run_intraday_refresh.py`：每 30 分钟（10:10-14:40 之间，避开主跑时段）执行：
1. 读 scan_result.json（候选列表，静态复用）
2. 对候选池 ~30 只票拉最新报价 + 资金流（gateway.fetch_quotes_batch / fetch_capital_flow）
3. 更新 scan_result 副本里的 change_pct/amount/资金流字段
4. 重跑 ai_screening.run_screening（baseline only，强制 ai_enabled=False）
5. 写入 ai_screening_result.json（发现页下次请求即读到新鲜数据）
6. 不发飞书、不调 LLM、不跑 lifecycle

## cron 配置
`*/30 10-14 * * 1-5`（10:00-14:30 每 30 分钟，避开 09:40 主跑和 13:10/13:45 午盘）

## 成功标准
- [ ] run_intraday_refresh.py 存在，跑一次产出更新的 ai_screening_result.json
- [ ] baseline only（不调 LLM），~1-2 秒完成
- [ ] 注册为 cron 任务
- [ ] pytest -q 全绿

## 非目标
- 不重新 scan 全市场
- 不调 LLM（ai_judge 留给主跑）
- 不发飞书
- 不跑 candidate_lifecycle（那是盘后的事）
