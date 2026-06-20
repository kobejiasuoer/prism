# 发现页 7 个逻辑缺陷修复 设计文档

- 日期：2026-06-20
- 范围：发现页 3 个 P0 + 4 个 P1 逻辑缺陷（基于两 agent 交叉验证的诊断）
- 性质：bug 修复，不改产品逻辑

## 集群 1：阀门关闭整页空白（P0）
**根因**：`activeLayer` 默认 `"focus"`（workbench.tsx:1186）。阀门关闭时后端 triage 把所有卡置为 `action_state=watch`，focus 桶空；FunnelHeader 被隐藏（1271），用户无法切换到 watch 桶 → 首屏空表。
**修复**：阀门关闭时 `activeLayer` 默认设为 `"watch"`。空-focus fallback banner（1279）改为只在阀门开时显示。
**测试**：构造 valveStatus="off" + 有 watch 桶数据，验证首屏显示 watch 卡而非空表。

## 集群 2：scoreForSort 假排序（P0）
**根因**：`public_opportunity_card_payload` allowlist（dashboard_data.py:5481-5549）不含 `best_score`；`scoreForSort` 无分返回 0，与真 0 分混在一起。
**修复**：① allowlist 加 `best_score`；② `scoreForSort` 区分"无评分"（返回 -Infinity 排到末尾，而非 0）。

## 集群 3：移动端 rank 残留 + action_directive 硬编码（P0+P1）
**根因**：移动端卡片（workbench.tsx:1081-1087）仍渲染 `decision_rank_label` badge；后端 `build_action_directive(card, valve_open=True)`（5551）硬编码 True。
**修复**：① 移动端删 `decision_rank_label`/`decision_rank` badge；② 后端传真实 `valve_open`（=`valve_status != "off"`），前端 ActionCell 不再需要 valveOff 覆盖（保留兼容但不再依赖）。

## 集群 4：drop 逻辑 + 数据失败伪装 + exit_tracking 割裂（P1×3）
**4a drop 逻辑**：`triage.py:46` 的 `ACTION_DROP` 只在 `eliminated=True` 触发。修复：`risk_level=="block"` 也触发 drop。
**4b 数据失败伪装**：`dashboard_data.py:9195` `gate.get("status") or "off"` 把数据缺失当阀门关闭。修复：区分 `valve_status="unknown"`（数据缺失）vs `"off"`（真关闭），前端 unknown 时显示"数据未就绪"而非"阀门关闭"。
**4c exit_tracking 割裂**：`yesterday_trial_review` 与 `exit_tracking` 无 join。修复：`build_yesterday_trial_review` 按 code 关联 exit_tracking，给仍 listed 的 trial 附上已知 outcome。

## 成功标准
- [ ] 阀门关闭日首屏显示 watch 桶（非空表）
- [ ] scoreForSort 无分卡排到末尾且 allowlist 含 best_score
- [ ] 移动端无 decision_rank badge
- [ ] action_directive 后端用真实 valve_open
- [ ] risk_level=block 的卡进 drop 桶
- [ ] valve_status 区分 unknown/off
- [ ] yesterday_trial_review 关联 exit_tracking outcome
- [ ] pytest -q + next build 全绿

## 非目标
- 不重构漏斗/分桶模型。
- 不改 triage 的 gate_state 计算（只改 action_state 的 drop 条件）。
- 不做 K 线/新 UI。
