# 进攻阀门判定逻辑重写 设计文档

- 日期：2026-06-20
- 范围：`packages/screener/parameters.py` 的 `build_execution_gate` + `data/config/stock-parameters.json` 的 `execution_gate` 阈值
- 根因：系统运行两个月，阀门几乎从不开启（off），用户永远无法买入。

## 诊断（已用 6-18 真实数据验证）

### 缺陷 1：OR 逻辑 — 6 个条件任一触发就关
`parameters.py:138-145`：`off` 判定是 6 个条件的 OR（broad_score/positive_ratio/avg_change/strong_ratio/candidate_score/candidate_strong_ratio）。A 股弱市/震荡市几乎天天满足其中 2-4 个 → 几乎永远 off。

### 缺陷 2：大盘独裁 — candidate 被忽略
阀门只看 broad regime（大盘 223 只），candidate regime（候选 30 只）的 `attack_ok=true` 被忽略。6-18：候选 83% 上涨、均涨 3.96%，但因大盘 38.6% 上涨 → 阀门关。结构性行情（板块分化）被一刀切。

### 缺陷 3：阈值脱离 A 股实际分布
- `positive_ratio < 0.48` 就触发 off 条件——A 股大盘 positive_ratio 中位数约 0.45-0.50，一半交易日直接满足这个 off 条件。
- `limited` 需要 positive_ratio >= 0.63 + avg_change >= 0.45% + strong_ratio >= 0.22——一年满足不了 20% 的天数。

## 修复方案

### 核心改动：从"大盘独裁 OR"改为"加权仲裁 + 严重度计数"

新判定逻辑（`build_execution_gate` 重写）：

```
1. 计算大盘环境分 (broad_env) 和候选环境分 (candidate_env)，各 0-3 分：
   - broad: positive_ratio, avg_change, strong_ratio 各贡献 0/1 分
   - candidate: candidate_score 档位 + candidate_strong_ratio 贡献 0-3 分

2. 仲裁规则（取代 OR）：
   - candidate_env >= 2 且 broad_env >= 1 → "limited"（结构性行情，精选轻仓）
   - candidate_env >= 2 且 broad_env >= 2 → "on"（共振，正常试错）
   - candidate_env <= 1 且 broad_env <= 1 → "off"（两边都弱）
   - candidate_env >= 2 且 broad_env == 0 → "limited"（候选强但大盘极弱，仍允许精选，但仓位更小）
   - 其他 → "limited"（默认偏保守但不一刀切关）
```

**关键变化**：candidate 强而大盘弱时，从 off 变 limited。这是结构性行情的核心场景。

### 阈值校准（stock-parameters.json）

基于 A 股实际分布调整：
- broad positive_ratio 的 off 阈值从 0.48 降到 0.35（A 股震荡市常见 0.40-0.50）
- broad avg_change 的 off 阈值从 0.0 降到 -0.8（微跌不该直接关）
- broad strong_ratio 的 off 阈值从 0.07 降到 0.05
- candidate_score 的 off 阈值从 3 降到 2
- 新增"连续确认"概念（本波不做，记录为后续）：单日触发不直接关，连续 2 日才关

### 不改的部分
- `build_execution_gate` 的函数签名（`broad_regime, candidate_regime`）不变
- 返回结构不变（status/label/summary/position_cap/allow_new_positions/...）
- 前端 valve 渲染逻辑不变（off/limited/on/unknown 已支持）

## 任务

### 任务 1：重写 build_execution_gate 判定逻辑
- 把 OR 条件链替换为 broad_env/candidate_env 加权仲裁
- 新增 `_compute_env_score(metrics, rules) -> int` 辅助函数
- 单元测试：覆盖 6-18 场景（candidate 强 broad 弱 → limited）、两边都弱 → off、两边都强 → on

### 任务 2：校准 stock-parameters.json 阈值
- 调整 off/limited 的阈值到 A 股实际分布
- 加注释说明校准依据

### 任务 3：验证
- 用 6-18 真实数据回放，确认阀门从 off 变 limited
- `pytest -q` 全绿

## 成功标准
- [ ] 6-18 场景（候选强 broad 弱）阀门从 off → limited
- [ ] 两边都弱 → off 仍成立
- [ ] 两边都强 → on
- [ ] `pytest -q` 全绿
- [ ] build_execution_gate 返回结构不变（前端无需改动）

## 风险
| 风险 | 缓解 |
|------|------|
| 新逻辑过于宽松导致乱买 | limited 仍只允许 pullback_continuation/low_reversal 两种 setup + 0.3 仓上限 |
| 现有测试断言旧阈值 | 更新 test_parameters_evaluation_gate.py |
| broad_env/candidate_env 权重不准 | 先用 0-3 简单分档，后续根据实际运行数据调 |
