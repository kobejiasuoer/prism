# readiness source-of-truth 显式化 设计文档

- 日期：2026-06-20
- 范围：把 dashboard_data.py 里 readiness 的"缓存读 vs 直接重算"多态收敛成单一显式入口 `resolve_readiness()`，为安全拆分做准备。
- 上游依据：`docs/dashboard-data-split-blocker-2026-06-20.md`

## 问题
dashboard_data.py 里有两种 readiness 取法混用：
- 读共享缓存 `_today_base_inputs()["readiness"]`（line 965, 1013, 10265, 11499, 11507）
- 直接调 `compute_readiness(...)` 重算（line 8632, 8703, 8935, 11313, 10276-fallback）

line 10265/10276 是混合：先读缓存，空了才重算。这种多态在单文件内靠"同作用域看同全局"成立，拆分后破裂。

## 目标
新增 `resolve_readiness(*, base=None, force_recompute=False, **compute_kwargs)` 作为唯一 readiness 入口：
- `base` 非空且含 `readiness` → 返回缓存的（默认行为，多数视图）。
- `force_recompute=True` 或 `base` 无 readiness → 调 `compute_readiness(**compute_kwargs)` 重算。
- 把所有 `base.get("readiness")` 和裸 `compute_readiness(...)` 调用点改成走 `resolve_readiness`。

## 任务
1. 加 `resolve_readiness()` + 单元测试（base 有/无 readiness、force_recompute 两种路径）。
2. 改 5 个读缓存的点 → `resolve_readiness(base=base)`。
3. 改 5 个直接重算的点 → `resolve_readiness(force_recompute=True, ...)`（保持原有 kwargs）。
4. 改混合点 10265/10276 → `resolve_readiness(base=base)`（不再 fallback 重算；若需重算显式传 force）。
5. 跑全量测试确认行为不变。

## 成功标准
- [ ] `resolve_readiness` 存在且被所有 readiness 取用点调用。
- [ ] grep `compute_readiness(` 在 dashboard_data.py 里只出现在 `resolve_readiness` 和 `_today_base_inputs` 两处。
- [ ] `pytest -q` 全绿（尤其 test_today_summary_actions_and_portfolio_share_base_inputs_cache）。

## 非目标
- 本轮不拆 portfolio 簇（那是 resolve_readiness 稳定后的下一轮）。
- 不改 readiness 的计算逻辑（compute_readiness 本身不动）。
- 不改前端。
