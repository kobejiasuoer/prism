# 发现页 UI 改造 设计文档

- 日期：2026-06-19
- 范围：`/discovery` 发现页 UI 改造（方案 A：动作列 + 轻量退出轨迹）
- 上游依据：`docs/discovery-page-design-review-2026-06-19.md`、`docs/system-audit-2026-06-19.md`、Wave 1 的 `exit_return_tracker.py`
- 本波**不含**：拆分 `dashboard_data.py` 巨型文件、K 线轨迹回放视图、阶段间 JSON schema、control_panel shim 清理。

---

## 1. 目标与成功标准

### 目标
1. **解决"不知道怎么选"**：加"今日动作"列，把散落在 7 列里的 `entry_plan`(action/trigger/invalidate/levels) 聚合成一行可执行指令，列在表格首位。
2. **解决阀门关闭时的自相矛盾**：阀门关闭时整页切到"观察模式"，隐藏"值得专注/等触发"假梯度漏斗，候选按 `priority_score` 真排序。
3. **解决"只跟踪一天"的可视化**：把 Wave 1 已写入的 `exit_tracking.jsonl` 数据接到前端，在延续追踪面板用数值+标签呈现退出股 outcome（真退出/错杀/未定）+ net_return。

### 成功标准（可验证）
- [ ] 表格首列是"今日动作"（ActionCell），聚合 entry_plan 的 action + 触发价 + 失效价，一行可读。
- [ ] 阀门 `valveStatus==="off"` 时：漏斗 Tab 区切换为"观察模式"提示（不显示"值得专注/等触发"假梯度），候选按 `priority_score` 降序排列。
- [ ] 阀门 `valveStatus!=="off"` 时：保留现有漏斗 + 动作列正常显示开仓/加仓指令。
- [ ] opportunities API 响应含 `exit_tracking` 数组（近 30 天，每条带 code/name/exit_date/outcome/net_return/status）。
- [ ] 延续追踪面板渲染退出股的 outcome 标签 + net_return；空数据时显示友好占位。
- [ ] 全程通过 `pytest -q`（后端）+ `next build`（前端）。

### 非目标（明确排除）
- 不做 K 线轨迹回放（Wave 3）。
- 不拆 dashboard_data.py（独立子项目）。
- 不改 scan/ai/midday/lifecycle 阶段间 schema。
- 不改 discovery 页的 AI 诊断、同主题集中度等现有功能。

---

## 2. 任务分解

本波分 5 个任务，有依赖关系：A（后端动作指令）→ B（前端动作列）可并行于 C（后端 exit-tracking 接出）→ D（前端轨迹面板）；E（阀门态自洽）依赖 A/B。

### 任务 A：后端 build_action_directive（聚合 entry_plan 成指令）[前端依赖]

**现状**：`StockListCard.entry_plan` 已含 action/trigger/avoid/invalidate/sizing/levels（带具体价位），但散在 payload 里，前端要自己拼。后端 `build_*_card` 系列不产出统一的"动作指令"对象。

**措施**：
1. 在 `dashboard_data.py` 新增 `build_action_directive(card: dict) -> dict`，聚合 entry_plan + hard_gate + suggested_action 成一个扁平结构：
   ```python
   {
     "headline": "只观察" | "等触发" | "可开仓" | "可加仓" | "不可开仓",
     "action_text": str,        # entry_plan.action 或 suggested_action_label
     "trigger_price": float|None,   # entry_plan.levels.trigger
     "invalidate_price": float|None,# entry_plan.levels.invalidate
     "sizing": str|None,
     "blocker": str|None,       # hard_gate_block_reason（阀门关闭时填）
   }
   ```
2. headline 由 `hard_gate_max_action` + `suggested_action` + 阀门态决定（阀门关 → 一律"只观察"或"不可开仓"）。
3. 在 `public_opportunity_card_payload`（及 discovery 用到的 card builder）里挂上 `action_directive` 字段。
4. 单元测试：阀门开/关 × 各种 suggested_action 的组合，验证 headline 与价格提取正确。

**风险**：低。纯新增聚合函数，不改既有字段。

### 任务 B：前端 ActionCell（今日动作列）[依赖 A]

**现状**：`discovery-observation-workbench.tsx` 的 7 列表格首列是 `DecisionRankBlock`（主题内 rank，误导）。entry_plan 数据有但没聚合成指令列。

**措施**：
1. 新建 `ActionCell` 组件，渲染 `stock.action_directive`：headline 作主标签（带 tone 色），trigger/invalidate 价位作副行，blocker 作灰色提示。
2. 表格首列从 `DecisionRankBlock` 换成 `ActionCell`。`decision_rank` 数据保留（移到次列或 tooltip），不再当首列主信息。
3. 移动端卡片版本同步加动作摘要行。
4. 类型：`types.ts` 的 `StockListCard` 加 `action_directive?: ActionDirective` 接口。

**风险**：低-中。改首列是可见行为变化，但不改数据流。

### 任务 C：后端 exit_tracking 接出 [前端依赖]

**现状**：Wave 1 的 `exit_return_tracker.py` 写 `data/runtime/exit_tracking.jsonl`，但 opportunities API 完全不读它，前端无字段。

**措施**：
1. 在 `dashboard_data.py` 新增 `load_recent_exit_tracking(*, days=30) -> list[dict]`，读 jsonl，过滤近 N 天，返回扁平结构：
   ```python
   [{"code","name","exit_date","exit_price","outcome","net_return","status","theme"}, ...]
   ```
2. 在 `build_opportunities_view` 的返回里挂 `exit_tracking` 字段。
3. 优雅降级：jsonl 不存在或为空 → 返回空列表（不报错）。
4. 单元测试：构造 jsonl（含 settled/open/各种 outcome），验证过滤与字段映射；空/缺失文件返回 []。

**风险**：低。只读新数据源，不改现有 payload 字段。

### 任务 D：前端退出轨迹轻量面板 [依赖 C]

**现状**：`discovery-context-panels.tsx` 的"延续追踪"面板（现懒加载侧栏）只渲染 lifecycle 的 entered/exited/continued 分组，不展示 Wave 1 的 outcome 数据。

**措施**：
1. 在延续追踪面板新增"近期退出表现"区块，渲染 `exit_tracking` 数组：
   - 每行：股票名 + outcome 标签（真退出✅绿 / 错杀⚠️橙 / 未定⏳灰 / 跟踪中🔵）+ net_return%（带正负色）+ exit_date。
   - 空数组显示"近期无退出记录"占位。
2. **纯数值+标签，无 K 线**。outcome 用 Badge + tone 色区分。
3. 类型：`types.ts` 加 `ExitTrackingRecord` 接口 + `OpportunitiesView.exit_tracking` 字段。

**风险**：低。新增渲染区块，不动现有面板。

### 任务 E：阀门态自洽 + 真排序 [依赖 A/B]

**现状**：`valveStatus==="off"` 时，漏斗 Tab（workbench.tsx:1238）仍显示"值得专注/等触发"假梯度；候选按主题内 `decision_rank` 排，rank=1 误导。

**措施**：
1. workbench 顶层加阀门态分支：`valveStatus==="off"` 时，漏斗 Tab 区替换为"观察模式"提示条（"今日进攻阀门关闭，以下为观察池，按综合得分排序"），不渲染假梯度 Tab。
2. 观察模式下候选按 `priority_score`（或 `best_score` 兜底）降序排列，而非 `decision_rank`。
3. 阀门开启时保持现有漏斗行为（动作列仍显示）。
4. 这是纯前端排序/渲染逻辑，无后端改动。

**风险**：中。改排序是可见行为变化；需确保 priority_score 在所有候选上非空（兜底 best_score）。

---

## 3. 任务依赖与执行顺序

```
A (后端 action_directive) ─┐
                          ├─→ B (前端 ActionCell) ─→ E (阀门态自洽)
C (后端 exit_tracking 接出) ─→ D (前端轨迹面板)
```

建议顺序：**A → C → B → D → E**（后端两个先就位，前端再接，E 收尾因为它依赖 B 的动作列已就位）。

---

## 4. 验证策略

每个任务完成后：
1. 该任务单元测试通过（后端）或 `next build` 通过（前端）。
2. 全部完成后：
   ```
   pytest -q
   cd apps/web && ./node_modules/.bin/next build
   ```
3. 手动验证（在本地跑起前后端）：
   - 阀门关闭日：看漏斗是否变观察模式、是否按 priority_score 排、动作列是否显示"只观察"。
   - 阀门开启日：看动作列是否显示触发价/失效价。
   - 退出轨迹面板：看 outcome 标签与 net_return 是否渲染。

---

## 5. 风险总览

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| priority_score 在部分候选上为空 | 中 | 中 | 兜底 best_score；再兜底按 change_pct |
| 改首列破坏移动端卡片布局 | 中 | 低 | 移动端同步加动作摘要行 + build 验证 |
| exit_tracking.jsonl 损坏 | 低 | 低 | load 函数 try/except 返回 [] |
| action_directive headline 逻辑与现有 suggested_action 冲突 | 中 | 中 | 单元测试覆盖所有 suggested_action × 阀门态组合 |

---

## 6. 不在本波的事项

| 事项 | 为何推迟 | 后续归属 |
|------|---------|---------|
| K 线轨迹回放视图 | 工作量大，需新组件 | Wave 3 |
| 拆 dashboard_data.py | 独立大子项目 | 独立周期 |
| 阶段间 JSON schema | 跨 4 文件 | 独立周期 |
| control_panel shim 清理 | 需目录改名 | Wave 3 |

---

## 附录：关键代码引用

- `apps/web/src/app/discovery/discovery-observation-workbench.tsx:933-1030` — 7 列表格定义（任务 B/E）
- `apps/web/src/app/discovery/discovery-observation-workbench.tsx:1186-1240` — 阀门条 + 漏斗 Tab（任务 E）
- `apps/web/src/app/discovery/discovery-context-panels.tsx` — 延续追踪面板（任务 D）
- `apps/web/src/lib/types.ts:876-975` — StockListCard 接口（任务 B/D 加字段）
- `apps/control-panel/dashboard_data.py:8803` — build_opportunities_view（任务 A/C 挂载点）
- `apps/control-panel/dashboard_data.py:5348` — public_opportunity_card_payload（任务 A 挂载点）
- `packages/screener/exit_return_tracker.py` — Wave 1 数据源（任务 C 读取）
- `data/runtime/exit_tracking.jsonl` — Wave 1 存储路径（任务 C 读取）
