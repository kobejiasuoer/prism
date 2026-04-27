# Prism 股票参数字典与重构建议

Date: 2026-04-23
Author: Codex
Scope: `stock-analyzer` / `packages/screener`
Goal: 将现有股票参数整理为可维护、可回测、可归因的标准参数字典，并标记 `保留 / 重估 / 删除 / 新增`。

## 1. 执行摘要

Prism 当前的股票参数体系已经具备较强的战术交易意识，但结构上仍然偏“规则堆叠”。

本次整理后，我建议将参数分成四类处理：

- `保留`：逻辑方向正确，应继续保留并标准化。
- `重估`：方向对，但阈值、权重、定义或口径需要通过历史验证重校。
- `删除`：信息含量低、与其他参数重复、或容易造成结构性偏差。
- `新增`：当前系统缺失，但对成为专业投资系统非常关键。

总体判断如下：

- `watchlist` 参数更适合继续向“持仓管理 / 风险纪律”方向发展。
- `screener` 参数更适合继续向“题材 / 趋势 / 资金 / 执行质量”方向发展。
- 两条线都需要统一到一个标准参数层，而不是继续把阈值散落在脚本里。

## 2. 标准参数分层

建议以后统一按以下六层管理参数。

### 2.1 Market 层

描述当天环境是否支持进攻、是否允许放大仓位。

### 2.2 Theme 层

描述当前主线、题材持续性、扩散强度、龙头稳定性。

### 2.3 Stock Core 层

描述单票的价格结构、流动性、资金、估值、事件风险。

### 2.4 Setup 层

描述这只票适合哪种做法：龙头接力、突破跟随、回踩接力、低位反转、只观察。

### 2.5 Execution 层

描述当前是否值得执行、仓位多大、触发条件是什么、何时取消。

### 2.6 Governance 层

描述数据时点、可信度、来源、缺失情况，用于防止伪信号。

## 3. 当前参数全景

### 3.1 `watchlist` 现有参数

从 `stock-analyzer/scripts/fetch.py` 可提取的主要参数有：

- 技术面：`backtest_score`、`backtest_bias`、`macd`、`kdj`、`boll`、`ma`
- 价格位置：`high_20d`、`low_20d`、`pct_from_high`、`pct_from_low`
- 资金流：`main_net`、`main_5d`、`signal`、`intraday_unconfirmed`
- 基本面：`pe`、`pb`、`roe`
- 事件：公告 / 新闻正负面归类
- 相对行业：个股与行业涨跌差
- 交易位：`support`、`resistance`、`stop_loss`
- 行动输出：`action`、`position`、`hard_flags`、`watch_points`

### 3.2 `screener` 现有参数

从 `packages/screener/scan.py` 与 `ai_screening.py` 可提取的主要参数有：

- 流动性：`amount`、`amount_yi`、`turnover`
- 价格与结构：`change_pct`、`high20`、`low20`、`position_20d`、`ma5`、`ma10`、`ma20`
- 技术初筛：`tech_score`
- 资金：`main_net`、`consecutive_inflows`、`flow_today_yi`、`flow_trend`
- 基本面：`pe_ttm`、`roe`、`margin`
- 情绪：`emotion_score`
- 风险：`missing_cap_penalty`、`overheat_penalty`、`notice_risk_tags`
- 风格纯度：`attack_profile.status`、`bias_score`、`is_preferred`
- 主题：`theme`、`theme_score`、`persistence_score`
- 环境：`positive_ratio`、`avg_change_pct`、`avg_turnover`、`strong_ratio`
- 执行：`setup_type`、`execution_quality.score`、`consistency.score`
- 优先级：`priority_score`、`tier`

## 4. 建议保留的参数

这部分参数方向正确，应该标准化，而不是删除。

### 4.1 Market 层保留

| 参数 | 当前含义 | 建议 |
|---|---|---|
| `positive_ratio` | 上涨样本占比 | 保留，作为环境 breadth 基础因子 |
| `avg_change_pct` | 平均涨幅 | 保留，反映赚钱效应 |
| `avg_turnover` | 平均换手 | 保留，反映活跃度 |
| `strong_ratio` | 强势股占比 | 保留，反映扩散强度 |
| `candidate_score_gap` | 候选与全池环境差 | 强烈建议保留，这是 Prism 的好设计 |

保留原因：

- 这组参数直接服务于环境阀门。
- 可解释性高。
- 与真实交易中的“今天可不可以打”高度相关。

### 4.2 Theme 层保留

| 参数 | 当前含义 | 建议 |
|---|---|---|
| `theme` | 主题分类 | 保留，但改为标准主题字典 |
| `leader_score` | 龙头强度 | 保留 |
| `count_score` | 候选集中度 | 保留 |
| `capital_score` | 资金集中度 | 保留 |
| `structure_score` | 队列完整度 | 保留 |
| `persistence_score` | 主题持续性 | 强烈建议保留 |
| `leader_stability` | 龙头稳定度 | 保留 |

保留原因：

- Prism 的主题持续性分析已经比一般选股脚本成熟。
- 这部分是它最有特色的 alpha 解释层之一。

### 4.3 Stock Core 层保留

| 参数 | 当前含义 | 建议 |
|---|---|---|
| `amount_yi` | 成交额（亿） | 保留 |
| `turnover` | 换手率 | 保留 |
| `change_pct` | 当日涨幅 | 保留 |
| `position_20d` | 20 日区间位置 | 保留 |
| `ma5/ma10/ma20` | 短中期均线结构 | 保留 |
| `flow_today_yi` | 当日主力净流入 | 保留 |
| `consecutive_inflows` | 连续流入天数 | 保留 |
| `pe_ttm` | 估值水平 | 保留 |
| `roe` | 盈利质量粗筛 | 保留 |
| `notice_risk_tags` | 事件风险标签 | 保留 |

### 4.4 Setup 与 Execution 层保留

| 参数 | 当前含义 | 建议 |
|---|---|---|
| `setup_type` | 做法分类 | 强烈建议保留 |
| `execution_quality.score` | 当前可执行性 | 强烈建议保留 |
| `consistency.score` | 信号一致性 | 强烈建议保留 |
| `entry_plan.trigger` | 触发条件 | 保留 |
| `entry_plan.invalidate` | 失效条件 | 保留 |
| `entry_plan.sizing` | 仓位建议 | 保留 |
| `support/resistance/stop_loss` | 自选股交易位 | 保留 |
| `intraday_triggers` | 盘中触发器 | 保留 |

保留原因：

- 这部分是 Prism 最接近实战价值的资产。
- 它把“分析”变成了“纪律化执行”。

### 4.5 Governance 层保留

| 参数 | 当前含义 | 建议 |
|---|---|---|
| `flow_as_of` | 资金数据时间 | 保留 |
| `price_as_of` | 价格时间 | 保留 |
| `flow_unconfirmed` | 盘中资金是否滞后 | 强烈建议保留 |
| `has_capital_flow` | 是否拿到资金数据 | 保留 |
| `missing_cap_penalty` | 资金缺失惩罚 | 保留，但重估 |

## 5. 建议重估的参数

这些参数有价值，但当前阈值、权重或定义不够稳，建议用历史样本重校。

### 5.1 流动性阈值

| 参数 | 当前规则 | 问题 | 建议 |
|---|---|---|---|
| `amount_yi` | `<4` 亿直接排除；`>=8/12/15` 加分 | 绝对阈值容易随市场总成交变化失真 | 改成分位数或相对市场分层 |
| `turnover` | `1.8 / 2.5 / 3 / 5 / 8` 多档阈值 | 不同行业、盘子不适用同一阈值 | 按市值桶和行业做归一化 |

### 5.2 价格结构阈值

| 参数 | 当前规则 | 问题 | 建议 |
|---|---|---|---|
| `position_20d` | `0.35 / 0.38 / 0.45 / 0.72 / 0.75 / 0.85` | 阈值较多，像经验刻度 | 用历史回测验证哪几个分界真正有效 |
| `change_pct` | `2 / 3 / 4.5 / 5 / 7 / 7.5 / 9.8` | 同时在多个打分层使用，重复计分风险高 | 做统一规范：只保留 1-2 个用途 |

### 5.3 基本面阈值

| 参数 | 当前规则 | 问题 | 建议 |
|---|---|---|---|
| `pe_ttm` | `>80`、`>95`、`>100` 风险 | 对成长 / 周期 / 反转行业不够公平 | 改成行业内估值分位 |
| `roe` | `<5`、`<8`、`>10`、`>12`、`>15` | 单独使用 ROE 太粗糙 | 与利润增速、现金流、资产负债联用 |
| `margin` | `>15`、`>25` 加分 | 对短线因子贡献不清晰 | 回测后决定是否保留轻权重 |

### 5.4 风险惩罚与权重

| 参数 | 当前规则 | 问题 | 建议 |
|---|---|---|---|
| `overheat_penalty` | 高位 / 爆量 / 涨停多档惩罚 | 方向对，但是否过度错杀主升浪未知 | 回测验证收益回撤改善幅度 |
| `missing_cap_penalty=4` | 资金缺失轻惩罚 | `4` 是否合理没有证据 | 结合数据鲜度和回补率重标 |
| `final_score` 权重 | `tech*1.25 + cap*1.2 + emotion*1.15 + fund*0.55` | 权重明显经验化 | 建议参数扫描与 walk-forward |

### 5.5 环境阀门阈值

| 参数 | 当前规则 | 问题 | 建议 |
|---|---|---|---|
| `execution_gate` thresholds | 以 `score/positive_ratio/avg_change/strong_ratio` 硬切 `off/limited/on` | 很关键，但最需要统计验证 | 先做历史重放，验证阀门开关是否真的提升收益质量 |

### 5.6 执行质量与一致性阈值

| 参数 | 当前规则 | 问题 | 建议 |
|---|---|---|---|
| `execution_quality.score` | `>=6` 高，`>=3` 中 | 逻辑合理，但阈值仍是经验值 | 回测确认 trade expectancy |
| `consistency.score` | `>=4` 高，`>=1` 中 | 很有价值，但构成项需要标准化 | 拆成标准子因子 |
| `midday score < 70` | 午盘强制降级 | 很关键，但可能与其他信号重复 | 单独评估该规则的边际贡献 |

## 6. 建议删除或合并的参数

“删除”不一定是彻底不用，而是建议不再作为独立核心参数存在。

### 6.1 删除或合并的重复情绪参数

| 参数 | 当前状态 | 删除/合并理由 |
|---|---|---|
| `emotion_score` | 由涨幅、成交额、换手再次打分 | 与 `tech_score`、`change_pct`、`turnover`、`amount_yi` 高度重叠，建议拆回底层原始因子 |
| `tech_score` 中的部分涨幅 / 换手加分 | 与情绪分重复 | 建议保留技术结构分，去掉重复情绪项 |

### 6.2 删除过强的行业硬偏好

| 参数 | 当前状态 | 删除/合并理由 |
|---|---|---|
| `preferred_keywords` / `weak_keywords` 的硬偏置 | 直接决定 `attack_profile` 倾向 | 容易把系统训练成固定风格偏见，不利于市场演化 |
| `is_cyclical_soft` 的固定惩罚 | 行业静态偏见太强 | 应改成“周期状态因子”而不是永久负面标签 |

建议：

- 保留行业信息本身
- 删除行业字面关键词的强硬奖惩
- 改成统计验证后的风格暴露因子

### 6.3 合并过度文案化参数

| 参数 | 当前状态 | 删除/合并理由 |
|---|---|---|
| `entry_reason` | 说明性文本 | 应保留为输出，不应视为核心参数 |
| `main_risk` | 说明性文本 | 同上 |
| `watch_condition` | 说明性文本 | 同上 |

建议：

- 底层保留结构化字段
- 文案层由模板实时生成
- 不要让研究层依赖文本字段

## 7. 建议新增的参数

这部分是 Prism 真正往专业投资系统升级时最缺的内容。

### 7.1 基本面新增

| 新参数 | 目的 |
|---|---|
| `revenue_yoy` | 营收增速 |
| `net_profit_yoy` | 利润增速 |
| `operating_cashflow_yoy` | 现金流质量 |
| `debt_ratio` / `interest_coverage` | 资产负债风险 |
| `forecast_revision_30d` | 预期修正 |
| `industry_pe_percentile` | 行业内估值位置 |

### 7.2 市场状态新增

| 新参数 | 目的 |
|---|---|
| `index_trend_score` | 大盘趋势 |
| `limit_up_count` / `limit_down_count` | 情绪强弱 |
| `broken_limit_ratio` | 炸板率，衡量接力环境 |
| `industry_breadth` | 行业内扩散度 |
| `market_volatility_regime` | 波动率状态 |

### 7.3 个股微观结构新增

| 新参数 | 目的 |
|---|---|
| `relative_volume_ratio` | 当日相对放量 |
| `vwap_distance` | 价格相对均价偏离 |
| `intraday_drawback_ratio` | 盘中回撤强弱 |
| `close_near_high_ratio` | 收盘质量 |
| `gap_open_pct` | 高开风险 |

### 7.4 组合层新增

| 新参数 | 目的 |
|---|---|
| `portfolio_theme_exposure` | 单主题拥挤度 |
| `portfolio_sector_exposure` | 行业集中度 |
| `position_correlation_score` | 组合相关性 |
| `risk_budget_used` | 风险预算 |
| `drawdown_throttle` | 回撤后自动降风险 |

### 7.5 治理与可信度新增

| 新参数 | 目的 |
|---|---|
| `data_freshness_minutes` | 数据鲜度 |
| `source_confidence_score` | 来源可信度 |
| `fallback_source` | 是否使用降级源 |
| `field_missing_ratio` | 单票缺失比例 |

## 8. 建议的标准参数字典格式

后续建议统一按下面的 schema 管理参数。

```yaml
name: flow_today_yi
layer: stock_core
type: numeric
unit: yi_cny
source: eastmoney
frequency: intraday
freshness_required_minutes: 30
missing_policy: penalize
current_status: retain
used_by:
  - attack_profile
  - execution_quality
  - setup_plan
  - midday_verify
notes: 当日主力净流入，建议与 relative_volume 联合使用
```

建议每个参数都必须有：

- `name`
- `layer`
- `type`
- `unit`
- `source`
- `frequency`
- `freshness_required`
- `missing_policy`
- `current_status`
- `used_by`
- `notes`

## 9. 最推荐的参数重构顺序

### Phase 1: 先标准化，不改策略

只做一件事：

- 把当前所有参数抽成标准字典

目标：

- 消灭脚本散点阈值
- 明确哪些模块在用哪些参数

### Phase 2: 再做历史验证

验证最关键的五组参数：

- 环境阀门
- 主题持续性
- 过热惩罚
- 执行质量
- 午盘确认

### Phase 3: 再做删减与替换

优先处理：

- 行业关键词硬偏置
- 重复的情绪打分
- 绝对化流动性阈值

### Phase 4: 最后补长期研究参数

新增：

- 预期修正
- 盈利增速
- 现金流质量
- 组合风险约束

## 10. 最终建议

如果只保留一句操作性建议，那就是：

> Prism 现在最该做的，不是继续往规则里加条件，而是先把现有参数收敛成一套标准因子字典，然后用历史验证决定谁该留下来。

当前我给出的四类结论可以简化成：

- `保留`：环境、主题持续性、执行质量、setup、交易位、数据时点
- `重估`：所有硬阈值、权重、估值线、流动性线、午盘分数线
- `删除/合并`：重复情绪打分、过强行业硬偏置、文案型“伪参数”
- `新增`：盈利增长、预期修正、组合约束、鲜度与可信度

完成这一步后，Prism 才真正具备进入“参数治理”和“回测验证”阶段的基础。
