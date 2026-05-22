# Prism 首页：每日交易命令台（Daily Command Brief）设计

- 日期：2026-05-22
- 范围：`/`（控制面板首页）+ `apps/control-panel/dashboard_data.py` 的首页聚合层
- 状态：设计阶段，待 review

## 1. 目标与背景

当前首页（`apps/web/src/app/page.tsx` 的 war-room 布局）把判断、动作和工程状态混在一起，结论被压缩成"否 / 0 成 / 进攻阀门关闭"这一类单句，没有回答交易者真正关心的四个问题：

1. 今天能不能动？
2. 能动什么？
3. 不能动什么？
4. 为什么？

本设计把首页重定义为"**每日交易命令台 / Daily Command Brief**"。首页必须分层输出命令、判断、动作、午盘改判、信任状态，且贴合 Prism 既有能力链：`scan → AI screening → midday verify → lifecycle → command brief → quality/readiness`。AI 只能解释、提示分歧、给出改判条件建议，不替代任何硬门控。

## 2. 不做的事

- 不发明新业务、不引入新的硬门控来源
- 不破坏现有 `/api/today` 字段（`command_hero / radar_cards / risk_rows / next_steps / hero / counts / action_queue / change_view / source_cards / quality_cards`）
- 不动其他页面（discovery / portfolio / review / stock / settings）
- 不删除 `apps/web/src/app/page.tsx` 当前依赖的组件（war-room / DecisionBrief / ActionStack / IntelligenceRail 等），仅在首页停止渲染它们；其他位置仍可继续引用

## 3. 顶层方案

### 3.1 后端聚合层（方案 A：纯派生）

在 `dashboard_data.py` 新增 `build_today_command_brief(...)`，输入与 `build_today_view()` 已加载的原料一致（`watchlist / screening_batch / confirmation / decision_brief / quality_status / lifecycle_context / readiness / gate / action_groups / action_queue / change_view`），输出顶层字段 `command_brief`。`build_today_view()` 在 return 前把 `command_brief` 塞进 dict。

**好处**：

- 现有字段 100% 向后兼容
- 派生逻辑集中、单元可测
- 老组件保留，零回归面

### 3.2 前端首页（重写 `page.tsx`）

`apps/web/src/app/page.tsx` 主体改为 5 区组件树，老的 war-room / DecisionBrief / ActionStack / IntelligenceRail 在首页停止挂载（但代码保留在 `apps/web/src/components/` 下供其他页面使用）。

## 4. 数据形状（`command_brief`）

```python
command_brief = {
    "trade_date": str,                  # 预期交易日
    "generated_at": str,
    "mode": {                           # A. 今日模式
        "value": "defense" | "observe" | "probe" | "offense",
        "label": "防守" | "观察" | "试探" | "进攻",
        "tone": "risk" | "watch" | "hold" | "positive",
        "summary": str,                 # 一句话陈述，不重复 label
        "reasons": list[str],           # 派生时使用的关键信号
    },
    "permits": {                        # A. 三个许可灯
        "data":        {"value", "label", "tone", "why"},
        "market":      {"value", "label", "tone", "why"},
        "opportunity": {"value", "label", "tone", "why"},
    },
    "position_cap": {                   # A. 仓位边界
        "value": str,                   # 例：0-0.3成
        "raw":   str,                   # 后端原值
        "tone":  str,
        "note":  str,                   # 单笔/总仓位口径
    },
    "first_action": {                   # A. 第一动作
        "title":  str,
        "reason": str,
        "url":    str,
        "action_key": str | None,
        "tone":   str,
        "kind":   "stock" | "system" | "recover_data",
    },
    "forbid_today": list[{              # A. 今日禁令
        "title": str, "reason": str, "tone": str, "source": str
    }],
    "reclassify_when": list[{           # A. 改判条件
        "label": str,                   # 例：从防守 → 观察
        "condition": str,
        "evidence": str,                # 入口或证据链接文字
        "url": str | None,
    }],
    "judgement_chain": list[{           # B. 判断链 4 维
        "dim": "market" | "main_theme" | "holdings_pressure" | "new_quality",
        "title": str,
        "verdict": str,                 # 弱/中/强 或 高/中/低 等
        "tone": str,
        "evidence": list[str],
        "impact": str,
    }],
    "action_lanes": list[{              # C. 动作四组
        "key": "must" | "conditional" | "observe" | "forbid",
        "title": str,
        "tone": str,
        "subtitle": str,
        "items": list[{
            "key": str,
            "code": str | None,
            "name": str | None,
            "action_type": str,         # 例：减仓 / 触价加观察 / 等突破 / 仅观察
            "reason": str,
            "trigger": str,             # 触发条件，没有则写"无明确触发"
            "invalidate_when": str,     # 失效条件，没有则写"-"
            "source": str,
            "url": str | None,
            "tone": str,
        }],
    }],
    "midday_verify": {                  # D. 午盘改判区
        "available": bool,
        "morning_takeaway": str,
        "midday_status": str,
        "fresh_candidates": list[{name, code, reason, url, tone}],
        "downgraded":       list[{name, code, reason, url, tone}],
        "next_day_condition": str,
        "verified_at": str,
    },
    "trust": {                          # E. 信任状态汇总（首屏一行）
        "readiness_mode": str,
        "source_summary": str,          # 例：4/4 timely
        "quality_summary": str,
        "blockers_count": int,
        "warnings_count": int,
        "auto_refresh_summary": str,
    },
}
```

`TodayData` TypeScript 增加 `command_brief?: TodayCommandBrief` 字段（可选，向后兼容）。

## 5. 派生规则

### 5.1 模式派生矩阵

| readiness | gate.allow_new_positions | gate.label 关键词 | confirmed+fresh | mode |
|---|---|---|---|---|
| blocked | * | * | * | defense |
| shadow_only | * | * | * | observe |
| live_ready | false | * | * | observe |
| live_ready | true | 含 "限制 / 试错 / 防守 / 限仓" | * | probe |
| live_ready | true | 含 "放开 / 进攻 / 强势 / 加仓" | =0 | probe |
| live_ready | true | 含 "放开 / 进攻 / 强势 / 加仓" | ≥1 | offense |
| live_ready | true | 其他 | * | probe |

显式覆盖：若 `decision_brief.summary.today_mode ∈ {defense, observe, probe, offense}` 则优先采用，并在 `mode.reasons` 标记 `brief_override`。

### 5.2 许可灯派生

- `data`：直接映射 `readiness.readiness_mode`（`live_ready→on`, `shadow_only→shadow`, `blocked→off`）；`why` 取 `blockers[0].message` / `warnings[0].message` / "数据已对齐当日"
- `market`：`gate.allow_new_positions=false → off`；`true` + label 含限制类关键词 → `limited`；`true` + label 含放开类关键词 → `on`；其余 → `off`。`why` 取 `gate.summary`
- `opportunity`：基于 `market` 与 `confirmation/screening` 数量
  - market=off → none
  - market=limited 且 (confirmed+fresh)=0 → observe
  - market=limited 且 (confirmed+fresh)≥1 → conditional
  - market=on 且 (confirmed+fresh)=0 → observe
  - market=on 且 (confirmed+fresh)≥1 → actionable
  - `why` 模板："午盘新增 N，确认 M，候选 K"

### 5.3 第一动作派生

按优先级取第一条：

1. mode=defense → `kind=recover_data`，title="先恢复数据链路"，url=`/settings`
2. `action_queue.items` 中 pending 的第一条 → `kind=stock`（队列由 `today_action_queue_priority` 预排序，已按 tone 高优先级在前，所以"第一条 pending"等价于"最高优先级 pending"）
3. mode=observe → `kind=system`，title="先复核优先持仓"，url=`/portfolio`
4. 都没有 → `kind=system`，title="今天先观望"，url=`#judgement-chain`

### 5.4 改判条件规则表

```python
RECLASSIFY_RULES = {
    "defense": [
        {"label": "→ 观察", "condition": "数据回到 live_ready"},
        {"label": "→ 试探", "condition": "数据就绪 + 进攻阀门 limited"},
    ],
    "observe": [
        {"label": "→ 试探", "condition": "主线强度 ≥ B 且 confirmed ≥ 1"},
    ],
    "probe": [
        {"label": "→ 进攻", "condition": "confirmed ≥ 2 持续两日"},
        {"label": "→ 观察", "condition": "downgraded ≥ 2 或主线降级"},
    ],
    "offense": [
        {"label": "→ 试探", "condition": "fresh_candidates 连续 2 日为 0"},
    ],
}
```

每条 condition 末尾拼接现有 `gate.summary` 截断 / `readiness.recommended_tasks[0]` 等动态字符串，保证不模板腔。`evidence/url` 指向最相关的内部入口（`/settings`, `/discovery`, `/portfolio`, `/review`）。

### 5.5 判断链 4 维

| dim | verdict 阈值 | evidence | impact 模板 |
|---|---|---|---|
| market | 弱=`allow_new_positions=false`；中=`allow=true` 且 label 含 limited 关键词；强=`allow=true` 且 label 含 on 关键词 | gate.label, gate.summary, 可选 amplitude | "今天{允许 / 不允许}开新仓，单笔 ≤ X%" |
| main_theme | A=`top_theme` 存在 + approved_count≥3；B=存在 + approved_count≥1；C=存在但 approved=0；无=top_theme 缺失 | theme name, approved_count/candidate_total | "围绕 {theme} 行动，不发散" |
| holdings_pressure | 高=priority_codes ≥ 3 或 downgraded ≥ 2；中=priority_codes ≥ 1；低=priority_codes=0 且 downgraded=0 | priority 名单 + downgraded 名单（≤3 条） | "先处理 N 个持仓" |
| new_quality | 好=confirmed≥1 且 downgraded=0；中=confirmed=0 且 fresh>0；差=confirmed=0 且 fresh=0；混合=confirmed≥1 且 downgraded≥1（取"中"） | confirmed/fresh/downgraded 样例 | "今天 / 明天再决定是否升级" |

`readiness=blocked` 时整个 `judgement_chain` 输出"冻结"语义：verdict 显示"未对齐当日"，evidence=["数据未对齐当日"]，impact="不展示旧主线 / 旧仓位 / 旧机会"。

### 5.6 动作四组

复用 `action_groups`：

- **must**：do-now 中 `tone ∈ {sell, positive}` 或 watchlist priority 来源
- **conditional**：do-now 中 `tone=watch` + watch 组中含触发条件（setup_label / breakout_price / stop_loss）的项
- **observe**：watch 组中无明确触发的（caution / fresh_candidates）
- **forbid**：avoid 组 + brief.avoid_points + mode=defense 时强制注入"今天不开新仓"

每条 item 字段：

- `trigger` 派生顺序：item.trigger → item.setup_label → watchlist {stop_loss / support / resistance} → "无明确触发"
- `invalidate_when` 派生顺序：item.invalidate_when → watchlist.stop_loss / failure_condition → "-"
- `action_type` 派生顺序：item.action_type → decision.label → 关键词推断（出现"减/止损"→减仓；"加/触发"→加观察；其余→根据 tone 写"仅观察 / 等突破"）

**去重**：同一 code 优先归到更高优先级组（must > conditional > observe），其他组里替换为提示行（不删除，加 hint "同名已在必须处理"）。

**空态**：四组都允许为空，但 `len(must)+len(conditional)+len(forbid) ≥ 1`；全空时强制注入 `must=[{title:"先复核优先持仓"}]` 和 `forbid=[{title:"今天不追高"}]`。

### 5.7 午盘改判

- `available = bool(confirmation)`
- `morning_takeaway`：`decision_brief.summary.gate_summary` 或 `screening_batch.screening_summary.execution_gate_status` 或 "早盘结论暂未生成"
- `midday_status`：`confirmation.validation_status` + counts 摘要（"确认 X / 新增 Y / 降级 Z"）
- `fresh_candidates[:3]` / `downgraded[:3]`：携带 name/code/reason/url/tone
- `next_day_condition`：`confirmation.next_day_focus` → 若缺失，按 mode 派生（probe → "若 fresh 隔日仍站住主线，可进观察"；其他模式有对应模板）
- `verified_at`：`confirmation.generated_at`

`available=False` → 整区显示"午盘验证尚未到位 + 当前不输出改判结论"。

### 5.8 信任状态汇总

- `readiness_mode`：直接来自 `readiness.readiness_mode`
- `source_summary`：`{timely}/{total} timely` （来自 `readiness.source_freshness`）
- `quality_summary`：`{ok}/{total} ok`（来自 `readiness.quality_freshness`）
- `blockers_count / warnings_count`：直接来自 readiness
- `auto_refresh_summary`：当 `refresh_status` 可读时写成短句；不可读时为空字符串

## 6. 前端结构

### 6.1 组件树

```
apps/web/src/app/page.tsx (重写)
└─ <CommandBriefPage>
   ├─ <TopBar />                       # 保留：标题 + 刷新 + 导出
   ├─ <ReadinessBanner />              # 保留：readiness != live_ready 时显示
   ├─ <CommandHeader />                # A 区
   │    ├─ <ModePill />
   │    ├─ <PermitStack />             # 3 灯
   │    ├─ <PositionCapStrip />
   │    ├─ <FirstActionCard />
   │    ├─ <ForbidList />
   │    └─ <ReclassifyConditions />
   ├─ <JudgementChain />               # B 区，4 卡
   ├─ <ActionLanes />                  # C 区，4 列
   │    └─ <LaneColumn>
   │         └─ <ActionRow />
   ├─ <MiddayVerify />                 # D 区
   │    ├─ <MorningVsMidday />
   │    ├─ <FreshList /> + <DowngradedList />
   │    └─ <NextDayCondition />
   └─ <TrustFold />                    # E 区
        ├─ 一行汇总
        └─ <details> 展开：复用 ReadinessBanner + IntelligenceRail（移植到这里）+ AutoRefreshBanner
```

新组件放在 `apps/web/src/components/command-brief/`（新目录）。每个组件输入只接受 `command_brief` 子片段，便于单测。

### 6.2 首屏 10 秒判断目标

首屏（无滚动）必须包含：模式、3 个许可灯、仓位上限、第一动作、今日禁令（≤3 条）。其他四区按顺序排在下方。

### 6.3 文案规则

- 每个标题第一句必须是"动作 + 对象"或"模式 + 原因"，不许出现"系统状态：xxx"
- mode=defense 时也必须给出"还能做什么 / 什么条件会改判 / 哪些值得观察"，禁止仅展示"否 / 0 成"
- 中文为主；英文 eyebrow 标签可保留，但占比 ≤ 20%

### 6.4 移除/迁移

- 首页停止渲染：`<DecisionBrief>`, `<ActionStack>`, `<IntelligenceRail>` (war-room 风格)
- 这些组件文件保留在 `apps/web/src/components/` 下不删除（其他页面可能用到）
- `<AutoRefreshBanner>`, `<ReadinessBanner>` 复用并迁移到 TrustFold 内

## 7. 兼容性与回退

- `/api/today` 响应继续包含旧字段；`command_brief` 是新增字段
- 前端若读不到 `command_brief`（旧后端），降级为现有 war-room 布局（保留一个降级分支）
- 后端 `build_today_command_brief` 出错时返回 None，首页降级渲染

## 8. 测试策略

### 8.1 后端

新建 `apps/control-panel/tests/test_command_brief.py`：

- 模式派生矩阵：参数化覆盖 `(readiness_mode, allow_new_positions, gate.label, confirmation_counts)` 至少 6 组场景
- 许可灯派生：覆盖 9 个组合
- 第一动作派生：覆盖 5 条优先级路径
- 动作四组：去重、空态、最小输出保证
- 午盘改判：available=true/false 两条
- 改判条件：每种 mode 至少 1 条且 condition 非空
- 与既有 `build_today_view()` 联调：confirm 老字段未被改

### 8.2 前端

- `pnpm typecheck` 通过
- `pnpm lint` 通过
- 手动验证：在 mode=defense / observe / probe / offense 四种场景（通过临时改 mock JSON）下，首屏满足 10 秒判断目标

## 9. 验收清单

1. readiness=blocked：mode=defense；首屏不显示旧主线/仓位/机会；first_action="先恢复数据链路"；reclassify_when ≥ 1 条
2. readiness=shadow_only：mode=observe；permits=`{data:shadow, market:off, opportunity:observe}`；action_lanes 只有 forbid + observe
3. readiness=live_ready 且 gate.allow=false：mode=observe；首页明确写"不能开新仓 + 哪几个值得观察 + 改判条件"
4. readiness=live_ready 且 gate.allow=true 且 confirmed≥1：mode=probe 或 offense；first_action 来自 action_queue
5. confirmation 缺失：D 区显示"午盘未到位"，不假装给改判
6. E 区折叠默认收起；首屏不抢眼
7. 旧字段全部保留，其他页面零回归
8. 后端测试与前端 typecheck/lint 通过；本地启动 `start_prism.sh` 后首页目测达标

## 10. 风险与缓解

| 风险 | 缓解 |
|---|---|
| `gate.label` 关键词派生在不同业务批次有歧义 | 关键词列表维护在常量；后续可加 `decision_brief.today_mode` 覆盖 |
| 老组件被前端意外引用造成首页双渲染 | page.tsx 仅 import 新 `<CommandBriefPage>` 子组件，老 import 完整删除（组件文件本身保留） |
| `command_brief` 派生异常导致首页空白 | 后端 try/except 包住派生，失败返回 None；前端缺字段时降级到现有 war-room |
| 字段膨胀导致 `/api/today` 响应过大 | `items` 限 ≤3，evidence ≤3，downgraded/fresh ≤3 |

## 11. 实施分阶段（草拟，后续 writing-plans 细化）

1. 后端：常量与派生辅助函数 + `build_today_command_brief()` + 测试
2. 后端：`build_today_view()` 接入 `command_brief` 字段
3. 前端：类型 `TodayCommandBrief` + API 类型扩展
4. 前端：5 区组件构建（`command-brief/` 目录）
5. 前端：`page.tsx` 重写
6. 联调：四种 mode 场景目测
7. 测试与验收：跑 backend pytest + 前端 typecheck/lint，提交

## 12. 文件改动总览

- 新增：`apps/control-panel/tests/test_command_brief.py`
- 新增：`apps/web/src/components/command-brief/*.tsx`（数个）
- 修改：`apps/control-panel/dashboard_data.py`（新增派生函数 + 接入）
- 修改：`apps/web/src/lib/types.ts`（新增 `TodayCommandBrief` 类型）
- 修改：`apps/web/src/app/page.tsx`（重写主组件）
- 不动：其他页面、组件、API 路由、artifact 加载、readiness 计算

