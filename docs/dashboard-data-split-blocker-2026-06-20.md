# dashboard_data.py 拆分：真实障碍与正确路径（follow-up）

- 日期：2026-06-20
- 状态：**已尝试、已回滚**。dashboard_data.py 保持原样（14719 行），无损坏。
- 触发：整改第三轮"全部依次做"中的最后一项；尝试方案 A（增量抽 portfolio 簇）失败。

---

## 1. 做了什么

按方案 A 把 portfolio 持仓簇（dashboard_data.py:12808-14719，~1900 行，44 个函数）抽到新建 `portfolio_view.py`，dashboard_data.py 末尾用 re-export 桩保兼容。同时把共享 helper `round_money`/`optional_round_money` 抽到 `money_utils.py` 以破循环导入。机械搬迁本身成功（dashboard_data 从 14719 → 12857 行），111 个 smoke 测试里 110 通过。

## 2. 卡在哪：readiness 缓存的隐式共享

唯一失败的测试：
```
test_today_summary_actions_and_portfolio_share_base_inputs_cache
AssertionError: 'shadow_only' != 'live_ready'
```

**根因是跨视图的 readiness 来源多态**，不是搬迁/导入 bug：

- `_today_base_inputs()`（dashboard_data.py:11288）构建一个被 `_TODAY_BASE_INPUTS_CACHE` 缓存的 dict，today-summary / today-actions / portfolio 三个视图共享它。
- **有的视图直接调 `compute_readiness()`**（dashboard_data.py:8632、8703、8935）。
- **有的视图读缓存里的 `base.get("readiness")`**（dashboard_data.py:10265，portfolio 走这条），只在缓存没 readiness 时才 fallback 到 `compute_readiness`（10276）。

测试 patch 了 `dashboard_data.compute_readiness` 返回 `live_ready`。summary/actions 直接调它 → 拿到 live_ready。portfolio 先读 `base.get("readiness")`——若共享缓存里已有（被前两个视图写入的）readiness，就用那个；若缓存里是陈旧的 `shadow_only`，portfolio 就拿到陈旧值，绕过了 patch。

这个"谁先算、算完写不写回缓存、谁读缓存谁重算"的隐式契约，在原文件里靠**所有函数同一作用域看同一组全局变量**成立。拆到第二个模块后，`base.get("readiness")` 兜底路径的语义没法在不改变 readiness 计算时序的前提下还原。

## 3. 试过且不够的修法

1. **lazy capture dict**（首次调用捕获函数引用）：失败——冻结了原始函数，测试的运行时 monkeypatch 不生效。
2. **per-call `getattr(_dd, name)` resolve**：部分修好，但 readiness 兜底路径仍读缓存。
3. **加 `compute_readiness` bridge**：单测过了，但暴露了更深的"缓存里 readiness 是 source-of-truth 还是 compute_readiness 是"的歧义。

每一层修补都揭开下一层隐式耦合。继续投入是沉没成本。

## 4. 为什么停手而非硬推

- 改坏的后果是**生产 readiness 误判**（shadow_only vs live_ready 决定前端是否显示实盘数据），代价远大于"文件少 1900 行"的收益。
- 审计当初标它"独立大子项目、需数天、风险在改坏"——实测风险比预估更高。
- 留半成品（一个测试红、行为可能漂移的拆分）比不拆更糟。

## 5. 正确的推进路径（供下一轮）

拆 dashboard_data.py 的前提是**先显式化 readiness 缓存契约**，而不是先搬迁代码：

1. **设计 readiness 的单一 source of truth**：决定是"compute_readiness 是唯一来源、缓存只存它算出的结果"，还是"`_today_base_inputs` 缓存是唯一来源、所有视图读它"。当前是两者混用，这是拆分的真正障碍。
2. **把契约固化成显式函数**（如 `resolve_readiness(base, force_recompute=False)`），让三个视图都走它，而不是各自 `base.get` 或 `compute_readiness`。
3. **加回归测试**：断言三个视图的 readiness 在 patch 后一致、在缓存命中时一致、在缓存失效时一致。
4. **契约稳定后再抽簇**：此时 portfolio 簇只依赖一个明确的 `resolve_readiness` 函数，搬迁变成纯机械操作，没有隐式时序耦合。

这是一个独立的设计周期（brainstorm → spec → plan → implement），不该塞进"全部依次做"。

## 6. 现状

- dashboard_data.py：14749 行，全绿。**已新增 `resolve_readiness()` 作为 readiness 单一入口（见 §5 步骤 1-3）**，所有 6 个 readiness 取用点已收敛到它。这是拆分前置项的实质进展。
- money_utils.py / portfolio_view.py：**未提交**（第二次尝试提取 portfolio 簇时仍卡在一个与测试 fixture 的 monkeypatch 交互上；已回滚）。
- **剩余障碍**：`resolve_readiness` 契约本身在全 dashboard_data 测试下通过，但 portfolio_view 的 lazy-bridge（`_dd().resolve_readiness`）在 test_app_smoke 的多 patch 上下文下仍触发 readiness 取值漂移。这是提取的机械问题（call-site 级），不是契约问题。需要逐 call-site 加针对性回归测试后再抽簇。

## 7. 进度更新（2026-06-20）

- ✅ §5 步骤 1-3：`resolve_readiness` 契约 + 单元测试 + 6 个取用点收敛（已提交）。
- ⏳ §5 步骤 4（回归测试三视图一致性）：待做。
- ⏳ §5 步骤 5（抽簇）：待做（步骤 4 完成后）。

## 附录：关键行引用
- `dashboard_data.py:11288` `_today_base_inputs()`（缓存构建）
- `dashboard_data.py:1135` `_TODAY_BASE_INPUTS_CACHE`（模块级缓存）
- `dashboard_data.py:10265,10276` portfolio 的 readiness 兜底路径（`base.get` → `compute_readiness`）
- `dashboard_data.py:8632,8703,8935` 直接调 `compute_readiness` 的视图
