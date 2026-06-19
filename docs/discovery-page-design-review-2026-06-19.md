# 发现/观察页 设计评审

- 日期：2026-06-19
- 范围：`/discovery` 发现/观察页 及其数据链路（前端 `apps/web/src/app/discovery/`、后端 `apps/control-panel/dashboard_data.py` 的 opportunities builder、`packages/screener/candidate_lifecycle.py`）
- 性质：**只做诊断，不改代码**。目的在于把"不知道怎么选""只跟踪一天没意义"两条直觉定位到具体设计取舍和代码位置，并给出后续可选项。
- 证据样本：`data/artifacts/screener/lifecycle/lifecycle_2026-06-18_09-40.json` 与对应 `.md` 报告；`data/quant/labels/forward_return_labels.jsonl`。

---

## 0. 结论先行

用户的两个不满都成立，且根因同源——**这页设计成"给用户看仪表盘"，而不是"替用户做决策排序"**：

1. **"不知道怎么选"**：页面是"进攻阀门条 + 4 张数量卡 + 漏斗 Tab + 7 列宽表"的信息平铺结构。但当进攻阀门关闭时，6 只候选里 5 只买入闸门写着同一句"仓位上限为 0，不能开新仓"，漏斗仍在假装存在梯度。**没有一个列回答"今天若开仓，先开谁"**。
2. **"只跟踪一天没意义"**：后端 `candidate_lifecycle.py` 默认 `--days-back 3`，但前端只消费 `yesterday_trial_review`（一个昨天 trial→今天的二值判断）。**退出样本（exited）只记 `last_seen`，完全不回填退出后走势**——而恰恰是一日脉冲/假突破的退出样本最能验证选股质量。项目里**已有 `forward_return_labels` 基础设施（11064 条）**，但 lifecycle 链路根本没拼接它。

---

## 1. 页面现状骨架与问题映射

页面渲染链路：`page.tsx` → `discovery-workspace.tsx`（数据容器）→ `discovery-observation-workbench.tsx`（主区 1281 行）+ `discovery-context-panels.tsx`（懒加载侧栏）。

```
┌─ 进攻阀门条（valveStatus）                    [workbench.tsx:1186-1198]
├─ 昨日 trial 复核条（yesterdayTrialReview）     [workbench.tsx:1200-1210]  ← 只跟踪一天
├─ 同主题集中度提示                              [workbench.tsx:1212-1216]
├─ 4 张数量卡：可执行/等触发/只观察/应剔除       [workbench.tsx:1218-1230]
├─ AI 诊断（懒加载门）                           [workbench.tsx:1232-1236]
├─ 漏斗 Tab：值得专注/等触发/只观察/丢弃         [workbench.tsx:1238-1240]
└─ 两栏：
   ├─ ObservationWorkbench（7 列宽表）           [workbench.tsx:920-1030]
   └─ sidePanel（延续追踪/主线雷达，懒加载）     [discovery-context-panels.tsx]
```

**问题：** 最该在主区的"延续追踪 / 退出回放"被压进 360px 右栏，还要先点"加载上下文"才出现（`workspace.tsx:252-270`）。用户首屏看不到任何跨天信息。

---

## 2. 问题一：把"决策"做成了"看仪表盘"

### 2.1 漏斗在阀门关闭时自相矛盾

- 进攻阀门条：`workbench.tsx:1186-1198`，当 `valveStatus === "off"` 显示"阀门关闭，今天不开新仓，整页进入观察模式"。
- 但紧接着的漏斗（`workbench.tsx:1238`）仍把候选分到"值得专注/等触发"，`FunnelHeader` 给每个 bucket 渲染可点击 Tab（`workbench.tsx:709-749`）。
- 证据样本（6-18）：6 只候选，5 只 `triage_gate_blocker` 都是"整体环境偏弱…仓位上限为 0，不能开新仓"。

**结果：** 阀门关了，UI 仍按"可执行"梯度分组，用户点进去发现每只都"不可买入"。漏斗在关阀日是**伪选项**。

### 2.2 "选择顺序"列语义不清

- 首列 `DecisionRankBlock`（`workbench.tsx:933, 949-951`）渲染 `stock.decision_rank` / `decision_rank_label`。
- 但 `decision_rank` 是**主题内（in-theme）名次**（见 `dashboard_data.py:5261 annotate_opportunity_card_ranks`），不是"今天若开仓先开谁"的全局动作序。
- rank=1 只表示"在它的主题里排第一"，主题本身可能主线走弱（`triage_theme_in_play === false`）。

**结果：** 用户看到"第 1 名"会误以为是优先级，实际它不跨主题可比。

### 2.3 买入闸门一列信息密度过低

- `BuyGateCell`（`workbench.tsx:229-250`）每行渲染 label + detail。
- 关阀日里 6 行有 5 行 detail 完全相同（同一条环境阻塞语）。纵向占位 ≈ 每行 4 行文本，但传递的增量信息 ≈ 0。

**结果：** 表格纵向被同质化文字撑长，真正有差异的"决策依据""风险证据"被挤到次要视觉位置。

### 2.4 没有"动作列"

- 7 列分别是：选择顺序 / 股票主题 / 观察阶段 / 买入闸门 / 决策依据 / 风险证据 / 操作（`workbench.tsx:933-939`）。
- 没有一列回答：**今天该做什么动作（开仓/加仓/只看/剔除）+ 触发价 + 失效价**。这些信息其实散落在 `upgrade_condition` / `invalid_condition` / `entry_plan` 里（`dashboard_data.py:5639-5660`），但没被聚合成一行可执行指令。

> 这就是"不知道怎么选"的字面含义：**页面给了很多维度，但没给一个排序后的、可直接执行的 to-do**。

---

## 3. 问题二：只跟踪一天——证据链

### 3.1 前端只消费一个"昨天 vs 今天"二值字段

- `yesterdayTrialReview`（`workbench.tsx:65-71, 1200-1210`）：渲染格式是"X（今日 等触发 / 今日已退出）"。
- 数据源 `build_yesterday_trial_review`（`dashboard_data.py:8702-8800`）：只识别**昨天 suggested_action == "trial"** 的股票，看它今天 `still_listed` 与否。
- 这是一个**单步二值判断**，不展示后续价格、不展示多天轨迹。

### 3.2 退出样本（exited）零回填

- `candidate_lifecycle.py:514-529`：exited 只记 `last_seen` / `reason` / `evidence_notes`。
- 证据样本（6-18）：9 只退出股（TCL科技、京东方A、紫光股份、浪潮信息、TCL中环、中国巨石、长电科技、斯达半导、兆易创新），每只**只有退出原因 + 最后出现时间**，**没有任何"退出后 N 日表现"**。

### 3.3 后端能力其实存在，只是没接上

| 能力 | 位置 | 现状 |
|------|------|------|
| 多天回溯 | `candidate_lifecycle.py:23` `--days-back` 默认 3 | 参数存在，但前端不暴露多天视图 |
| Forward return 标签 | `data/quant/labels/forward_return_labels.jsonl`（11064 条，含 `entry_price`/`exit_price`/`net_return`/`holding_window_days`） | **仅被 `packages/quant/` 量化基准消费**，lifecycle 链路完全没拼接 |
| 资金持续天数字段 | `types.ts:419 flow_persistence_days` | 类型已声明，但 UI 未渲染 |
| 延续性标签 | `persistence_label`（"非一日脉冲/一日脉冲风险"） | 只在右栏侧栏以 badge 形式出现 |

**这就是"只跟踪一天没意义"的技术根因：** 退出股永远停在"最后出现"那一刻，而验证选股质量最值钱的"退出后是真跌还是错杀"数据，项目里有基础设施却没接到这条链路上。

---

## 4. 次要问题清单（按影响排序）

| # | 问题 | 代码位置 | 影响 |
|---|------|---------|------|
| 1 | 阀门关闭时漏斗仍假装有梯度 | `workbench.tsx:1186-1240` | 自相矛盾，误导用户 |
| 2 | 延续追踪/退出回放被压进懒加载右栏 | `workspace.tsx:252-270`, `context-panels.tsx` | 首屏看不到任何跨天信息 |
| 3 | 买入闸门列同质化文字撑长表格 | `workbench.tsx:229-250` | 纵向空间浪费 |
| 4 | "选择顺序"用 in-theme rank 误导 | `workbench.tsx:949`, `dashboard_data.py:5261` | rank=1 ≠ 今天该买 |
| 5 | 退出样本零回填，无 forward return | `candidate_lifecycle.py:514-529` | 选股质量无法验证 |
| 6 | 移动端卡片堆 4-5 层 Badge | `workbench.tsx:1041-1082` | 手机端比表格更难读 |
| 7 | `flow_persistence_days` 已声明未渲染 | `types.ts:419` | 数据有但没用到 |

---

## 5. 后续可选项（供决策，本次不实施）

用户已明确诉求为**全生命周期轨迹**。以下按从轻到重排列，**均不在本次范围内**，仅作为决策菜单：

### 选项 A：退出样本回填（最轻）
- 改 `candidate_lifecycle.py` exited 分组，对每个 exited code，按 `last_seen` 日期从 `forward_return_labels.jsonl` 取退出后 N 日 `net_return`，写入 exited 条目。
- 前端在延续追踪面板加"退出回放：TCL科技 退出后 3 日 -4.2%（真退出）/ +6.1%（错杀）"。
- 改动量：1 个 Python 函数 + 1 个前端组件。**直接命中"只跟踪一天"**。

### 选项 B：动作列（中等）
- 在 7 列表基础上加"今日动作"列，聚合 `entry_plan.action` / `upgrade_condition` / `invalid_condition` 成一行指令。
- 阀门关闭时整页降级为"只观察 + 按 forward-return 预期排序"，隐藏漏斗假梯度。
- 改动量：1 列 + 阀门态分支。**直接命中"不知道怎么选"**。

### 选项 C：全生命周期轨迹（最重，匹配用户诉求）
- 新建存储：每个候选从 entered→continued→upgraded→exited 的全程事件流 + 每日价格/资金流轨迹。
- 前端新增"生命周期时间线"视图（K 线 + 事件标注）。
- 改动量：新存储 schema + 回填任务 + 新视图组件。**完全解决"只跟踪一天"**，但工作量最大。

---

## 6. 本次产出边界

- ✅ 本文档（诊断 + 证据 + 代码引用 + 选项菜单）。
- ❌ 不修改任何代码。
- ❌ 不实施选项 A/B/C 中的任何一个。

待用户选定方向后，再进入方案设计（brainstorming）与实现计划（writing-plans）。
