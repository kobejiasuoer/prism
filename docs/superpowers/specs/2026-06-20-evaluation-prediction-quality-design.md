# 评估闸门重写：查预测质量而非字段存在 设计文档

- 日期：2026-06-20
- 范围：`apps/scripts/evaluate_stock_analysis.py` 的 `score_dimensions` + 新增预测质量维度
- 上游依据：`docs/system-audit-2026-06-19.md`（问题：评估闸门 85/100 分来自字段存在性，自欺欺人）

## 问题
`score_dimensions`（evaluate_stock_analysis.py:257）全部基于字段存在性：
- +3 if `generated_at` 存在；+4 if `market_regime` 存在；+3 if `validation_status=="ok"`
- `historical_validation`(15分) 只看历史报告"能不能加载"，不看预测对不对
- 结果：已提交记分卡凭 2026-04 数据拿 97 分，tier 停在 professional_usable 而非 product_ready

## 目标
新增一个**真实预测质量维度**，用 Wave 1 `exit_return_tracker` 的 outcome 数据：
- 读 `data/runtime/exit_tracking.jsonl`，统计近 N 天 settled 记录的 outcome 分布。
- 预测质量分 = `true_exit` 占比（退出后真跌 = 预测对了；misjudged = 预测错了）。
- 高 true_exit 占比 → 退出判断准确 → 加分；misjudged 占比高 → 减分。

## 设计
新增维度 `prediction_accuracy`（或并入 historical_validation，扩容到更高上限）。评分函数 `score_prediction_accuracy()`：
- 读 exit_tracking.jsonl，过滤近 30 天 settled 记录。
- 若样本 < 最小阈值（如 5）→ 该维度得 0（样本不足，不奖励也不惩罚）。
- 否则：true_exit_ratio = true_exit / (true_exit + misjudged)。
  - ratio >= 0.7 → 满分
  - ratio 0.5-0.7 → 按比例
  - ratio < 0.5 → 低分（预测比抛硬币差）

## 任务
1. `score_prediction_accuracy(store=EXIT_TRACKING_STORE, days=30, min_samples=5) -> dict`，返回 {earned, max, samples, true_exit_ratio, detail}。
2. 接入 `evaluate_stock_analysis.py` 的维度体系：新增 `prediction_accuracy` 维度（max 15），或替换 historical_validation 的评分逻辑。
3. 单元测试：样本不足→0分；高 true_exit→满分；高 misjudged→低分；空文件→0分。
4. 更新 latest_scorecard 的预期（若 tier 因此变化）。

## 成功标准
- [ ] `score_prediction_accuracy` 存在，基于真实 outcome 数据而非字段存在。
- [ ] 单元测试覆盖 4 种场景。
- [ ] `pytest -q` 全绿（含 test_stock_analysis_evaluation.py）。
- [ ] 记分卡的评分逻辑不再纯靠字段存在。

## 非目标
- 不刷新 manifest 快照（那是数据问题，单独处理）。
- 不改 DIMENSION_MAX 的总量分配（新增维度等比缩减其他，或保持 100 分制调整）。
- 不改 tier 阈值定义。
