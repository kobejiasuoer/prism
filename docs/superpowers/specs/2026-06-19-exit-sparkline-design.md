# 退出股价格轨迹 Sparkline 设计文档

- 日期：2026-06-19
- 范围：在发现页延续追踪面板给退出股加收盘价 sparkline 折线（方案 A）
- 上游依据：Wave 2 退出轨迹面板（数值+标签）的视觉增强
- 约束：Wave 1 exit tracker 只存收盘价（无 OHLC）；项目无图表库。所以做 sparkline 折线（手写 SVG），不做蜡烛图。

## 目标
把 Wave 1 已存的 `daily_prices: [{date, close}, ...]` 接到前端，画一条收盘价 sparkline，带退出价基准线，让用户一眼看到"退出后涨跌轨迹"。

## 任务

### 任务 1：后端暴露 daily_prices
- `load_recent_exit_tracking` 的扁平 allowlist 加 `"daily_prices": rec.get("daily_prices")`。
- 测试：验证 daily_prices 出现在结果里（且仍是 list of {date,close}）。

### 任务 2：前端类型 + sparkline 组件
- `ExitTrackingRecord` 加 `daily_prices?: Array<{date?: string; close?: number}>`。
- 新建 `PriceSparkline` 组件（手写 SVG）：输入 daily_prices + exit_price，画折线 + 退出价水平基准线（虚线）+ 净收益色（涨绿跌红）。无新依赖。

### 任务 3：面板集成
- `ExitTrajectoryBlock` 每行加一个 sparkline（紧凑，~60px 宽），点击展开可看大图（可选，先做紧凑版）。

## 非目标
- 不引图表库。
- 不改 Wave 1 tracker 的存储格式（只用现有 close）。
- 不做交互式 tooltip/缩放（保持简单）。

## 风险
- daily_prices 可能为空（open 状态未结算）→ sparkline 显示占位"—"。
- SVG 在移动端缩放 → 用 viewBox 保证响应式。
