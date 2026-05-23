# Prism 每日交易命令台（Daily Command Brief）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把控制面板首页从"系统状态展示"重写为"每日交易命令台"，提供模式、许可、仓位上限、第一动作、禁令、改判条件、判断链、动作四组、午盘改判、信任状态 10 项分层输出。

**Architecture:** 后端在新模块 `apps/control-panel/command_brief.py` 实现 `build_today_command_brief()`，从现有的 readiness/gate/decision_brief/screening/confirmation/watchlist/action_groups/action_queue 派生新结构，`dashboard_data.build_today_view()` 在返回前挂上 `command_brief` 字段（其余字段全部保留）。前端 `apps/web/src/app/page.tsx` 重写为五区组件树，老的 war-room / DecisionBrief / ActionStack / IntelligenceRail 在首页停止挂载（组件文件保留）。

**Tech Stack:** Python (FastAPI + dashboard_data) · TypeScript (Next.js App Router) · pytest (unittest) · pnpm + tsc + eslint

**Reference:** `docs/superpowers/specs/2026-05-22-daily-command-brief-design.md`

---

## 文件结构总览

- 新建：`apps/control-panel/command_brief.py` — 命令台派生层（无副作用，可单测）
- 新建：`apps/control-panel/tests/test_command_brief.py` — 后端单元测试
- 新建：`apps/web/src/components/command-brief/` 目录下分模块组件文件
- 修改：`apps/control-panel/dashboard_data.py` — 接入 `build_today_command_brief`
- 修改：`apps/web/src/lib/types.ts` — 新增 `TodayCommandBrief` 类型
- 修改：`apps/web/src/app/page.tsx` — 完全重写主组件

---

## Task 1: 派生模块骨架 + mode 派生

**Files:**
- Create: `apps/control-panel/command_brief.py`
- Create: `apps/control-panel/tests/test_command_brief.py`

- [ ] **Step 1.1: 写第一组失败测试（模式派生矩阵）**

写入 `apps/control-panel/tests/test_command_brief.py`：

```python
"""Unit tests for the daily command brief aggregator.

Covers mode/permits/position_cap/first_action/forbid_today/reclassify/
judgement_chain/action_lanes/midday_verify/trust derivation rules from
the design at docs/superpowers/specs/2026-05-22-daily-command-brief-design.md.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

INVEST_FLOW_ROOT = Path(__file__).resolve().parents[2]
if str(INVEST_FLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(INVEST_FLOW_ROOT))

from control_panel.command_brief import derive_mode  # noqa: E402


def _readiness(mode: str = "live_ready", **extra) -> dict[str, object]:
    base = {
        "readiness_mode": mode,
        "ready": mode == "live_ready",
        "blockers": [],
        "warnings": [],
        "expected_trade_date": "2026-05-22",
        "data_trade_date": "2026-05-22" if mode != "blocked" else None,
        "source_freshness": [],
        "quality_freshness": [],
        "recommended_tasks": [],
    }
    base.update(extra)
    return base


def _gate(allow: bool = False, label: str = "防守试错", summary: str = "弱环境，先观察") -> dict[str, object]:
    return {
        "allow_new_positions": allow,
        "label": label,
        "position_cap": "0-0.3成" if allow else "0成",
        "summary": summary,
    }


def _confirmation(confirmed: int = 0, fresh: int = 0, downgraded: int = 0) -> dict[str, object]:
    return {
        "confirmed": [{"name": f"C{i}", "code": f"60000{i}"} for i in range(confirmed)],
        "fresh_candidates": [{"name": f"F{i}", "code": f"60010{i}"} for i in range(fresh)],
        "downgraded": [{"name": f"D{i}", "code": f"60020{i}"} for i in range(downgraded)],
        "counts": {
            "confirmed": confirmed,
            "fresh_candidates": fresh,
            "downgraded": downgraded,
        },
        "validation_status": "ok",
        "generated_at": "2026-05-22 12:30:00",
    }


class ModeDerivationTest(unittest.TestCase):
    def test_blocked_readiness_forces_defense(self) -> None:
        mode = derive_mode(
            readiness=_readiness("blocked"),
            gate=_gate(allow=True, label="进攻"),
            confirmation=_confirmation(confirmed=3),
            decision_brief=None,
        )
        self.assertEqual(mode["value"], "defense")
        self.assertEqual(mode["label"], "防守")

    def test_shadow_only_is_observe(self) -> None:
        mode = derive_mode(
            readiness=_readiness("shadow_only"),
            gate=_gate(allow=True, label="进攻"),
            confirmation=_confirmation(confirmed=3),
            decision_brief=None,
        )
        self.assertEqual(mode["value"], "observe")

    def test_live_ready_gate_closed_is_observe(self) -> None:
        mode = derive_mode(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=False, label="防守试错"),
            confirmation=_confirmation(),
            decision_brief=None,
        )
        self.assertEqual(mode["value"], "observe")

    def test_live_ready_limited_label_is_probe(self) -> None:
        mode = derive_mode(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="限制进攻"),
            confirmation=_confirmation(confirmed=1),
            decision_brief=None,
        )
        self.assertEqual(mode["value"], "probe")

    def test_live_ready_offense_label_with_confirmed_is_offense(self) -> None:
        mode = derive_mode(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="进攻放开"),
            confirmation=_confirmation(confirmed=2),
            decision_brief=None,
        )
        self.assertEqual(mode["value"], "offense")

    def test_live_ready_offense_label_without_confirmed_stays_probe(self) -> None:
        mode = derive_mode(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="进攻放开"),
            confirmation=_confirmation(),
            decision_brief=None,
        )
        self.assertEqual(mode["value"], "probe")

    def test_decision_brief_override_wins(self) -> None:
        mode = derive_mode(
            readiness=_readiness("blocked"),
            gate=_gate(),
            confirmation=_confirmation(),
            decision_brief={"summary": {"today_mode": "offense"}},
        )
        self.assertEqual(mode["value"], "offense")
        self.assertIn("brief_override", mode["reasons"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 1.2: 运行测试，确认失败**

Run: `cd apps/control-panel && python -m pytest tests/test_command_brief.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'control_panel.command_brief'`

- [ ] **Step 1.3: 创建 `command_brief.py`，实现 `derive_mode`**

写入 `apps/control-panel/command_brief.py`：

```python
"""Daily command brief aggregator.

Pure-derivation helpers used by ``dashboard_data.build_today_view`` to
project existing today-view inputs (readiness, gate, decision_brief,
watchlist, screening, confirmation, action_groups, action_queue) into the
5-section command brief defined in
``docs/superpowers/specs/2026-05-22-daily-command-brief-design.md``.

All functions in this module are side-effect free and accept plain dicts.
"""

from __future__ import annotations

from typing import Any


_LIMITED_LABEL_KEYWORDS = ("限制", "试错", "防守", "限仓")
_OFFENSE_LABEL_KEYWORDS = ("放开", "进攻", "强势", "加仓")

_MODE_LABELS = {
    "defense": "防守",
    "observe": "观察",
    "probe": "试探",
    "offense": "进攻",
}

_MODE_TONES = {
    "defense": "risk",
    "observe": "watch",
    "probe": "hold",
    "offense": "positive",
}


def _label_kind(label: str) -> str:
    text = label or ""
    if any(token in text for token in _LIMITED_LABEL_KEYWORDS):
        return "limited"
    if any(token in text for token in _OFFENSE_LABEL_KEYWORDS):
        return "offense"
    return "other"


def derive_mode(
    *,
    readiness: dict[str, Any],
    gate: dict[str, Any],
    confirmation: dict[str, Any] | None,
    decision_brief: dict[str, Any] | None,
) -> dict[str, Any]:
    readiness_mode = str(readiness.get("readiness_mode") or "blocked")
    allow_new = bool(gate.get("allow_new_positions"))
    label_kind = _label_kind(str(gate.get("label") or ""))
    counts = (confirmation or {}).get("counts") or {}
    confirmed_total = int(counts.get("confirmed") or 0) + int(counts.get("fresh_candidates") or 0)

    reasons: list[str] = [f"readiness={readiness_mode}", f"allow_new={allow_new}", f"label_kind={label_kind}"]

    if readiness_mode == "blocked":
        value = "defense"
    elif readiness_mode == "shadow_only":
        value = "observe"
    elif not allow_new:
        value = "observe"
    elif label_kind == "offense" and confirmed_total >= 1:
        value = "offense"
    else:
        value = "probe"

    brief_today_mode = ((decision_brief or {}).get("summary") or {}).get("today_mode")
    if brief_today_mode in _MODE_LABELS:
        value = brief_today_mode
        reasons.append("brief_override")

    summary = _mode_summary(value, gate, readiness)

    return {
        "value": value,
        "label": _MODE_LABELS[value],
        "tone": _MODE_TONES[value],
        "summary": summary,
        "reasons": reasons,
    }


def _mode_summary(value: str, gate: dict[str, Any], readiness: dict[str, Any]) -> str:
    gate_summary = str(gate.get("summary") or "").strip()
    if value == "defense":
        blocker = (readiness.get("blockers") or [{}])[0].get("message") if readiness.get("blockers") else ""
        return blocker or "数据未对齐当日，今天先恢复链路。"
    if value == "observe":
        return gate_summary or "进攻阀门关闭，今天只观察，不直接开仓。"
    if value == "probe":
        return gate_summary or "可以试探，但单笔小、持有短，先验证主线。"
    return gate_summary or "环境放开，仍按仓位纪律分批。"
```

- [ ] **Step 1.4: 运行测试，确认通过**

Run: `cd apps/control-panel && python -m pytest tests/test_command_brief.py -v`
Expected: PASS（7 个用例全部绿）

- [ ] **Step 1.5: 提交**

```bash
git add apps/control-panel/command_brief.py apps/control-panel/tests/test_command_brief.py
git commit -m "feat(command-brief): derive today mode from readiness/gate/confirmation"
```

---

## Task 2: 派生 permits（数据 / 市场 / 机会三个许可灯）

**Files:**
- Modify: `apps/control-panel/command_brief.py`
- Modify: `apps/control-panel/tests/test_command_brief.py`

- [ ] **Step 2.1: 在测试文件追加 PermitsTest 类**

在 `tests/test_command_brief.py` 顶部 imports 行补上：

```python
from control_panel.command_brief import derive_mode, derive_permits  # noqa: E402
```

并在文件末尾 `if __name__ == "__main__":` 前追加：

```python
class PermitsTest(unittest.TestCase):
    def test_blocked_readiness_yields_off_off_none(self) -> None:
        permits = derive_permits(
            readiness=_readiness("blocked", blockers=[{"message": "watchlist 数据偏旧"}]),
            gate=_gate(allow=True, label="进攻"),
            confirmation=_confirmation(confirmed=3),
            screening_batch=None,
        )
        self.assertEqual(permits["data"]["value"], "off")
        self.assertEqual(permits["market"]["value"], "off")
        self.assertEqual(permits["opportunity"]["value"], "none")
        self.assertIn("watchlist 数据偏旧", permits["data"]["why"])

    def test_shadow_only_yields_shadow_off_observe(self) -> None:
        permits = derive_permits(
            readiness=_readiness("shadow_only"),
            gate=_gate(allow=True, label="放开"),
            confirmation=_confirmation(confirmed=2),
            screening_batch=None,
        )
        self.assertEqual(permits["data"]["value"], "shadow")
        self.assertEqual(permits["market"]["value"], "off")
        self.assertEqual(permits["opportunity"]["value"], "observe")

    def test_live_ready_limited_label_with_candidates_is_conditional(self) -> None:
        permits = derive_permits(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="限制试错"),
            confirmation=_confirmation(confirmed=1, fresh=2),
            screening_batch=None,
        )
        self.assertEqual(permits["market"]["value"], "limited")
        self.assertEqual(permits["opportunity"]["value"], "conditional")
        self.assertIn("新增", permits["opportunity"]["why"])

    def test_live_ready_offense_label_without_candidates_is_observe(self) -> None:
        permits = derive_permits(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="进攻放开"),
            confirmation=_confirmation(),
            screening_batch=None,
        )
        self.assertEqual(permits["market"]["value"], "on")
        self.assertEqual(permits["opportunity"]["value"], "observe")

    def test_live_ready_offense_with_candidates_is_actionable(self) -> None:
        permits = derive_permits(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="放开"),
            confirmation=_confirmation(confirmed=2),
            screening_batch=None,
        )
        self.assertEqual(permits["opportunity"]["value"], "actionable")
```

- [ ] **Step 2.2: 运行测试，确认失败**

Run: `cd apps/control-panel && python -m pytest tests/test_command_brief.py::PermitsTest -v`
Expected: FAIL with `ImportError: cannot import name 'derive_permits'`

- [ ] **Step 2.3: 实现 `derive_permits`**

追加到 `apps/control-panel/command_brief.py`：

```python
_PERMIT_DATA = {
    "live_ready": ("on", "正常"),
    "shadow_only": ("shadow", "影子盘"),
    "blocked": ("off", "未就绪"),
}


def derive_permits(
    *,
    readiness: dict[str, Any],
    gate: dict[str, Any],
    confirmation: dict[str, Any] | None,
    screening_batch: dict[str, Any] | None,
) -> dict[str, Any]:
    readiness_mode = str(readiness.get("readiness_mode") or "blocked")
    data_value, data_label = _PERMIT_DATA.get(readiness_mode, ("off", "未就绪"))
    data_why = _readiness_why(readiness)

    if data_value == "off":
        market_value, market_label = "off", "进攻阀门关闭"
    else:
        allow_new = bool(gate.get("allow_new_positions"))
        kind = _label_kind(str(gate.get("label") or ""))
        if not allow_new:
            market_value, market_label = "off", "进攻阀门关闭"
        elif kind == "offense":
            market_value, market_label = "on", "进攻放开"
        else:
            market_value, market_label = "limited", "限制试错"
    market_why = str(gate.get("summary") or "").strip() or "实时阀门判断"

    counts = (confirmation or {}).get("counts") or {}
    fresh = int(counts.get("fresh_candidates") or 0)
    confirmed_count = int(counts.get("confirmed") or 0)
    approved = int(
        (((screening_batch or {}).get("screening_summary") or {}).get("approved_count") or 0)
    )

    if data_value == "off":
        opp_value = "none"
        opp_label = "今天不输出机会判断"
    elif market_value == "off":
        opp_value = "observe"
        opp_label = "只观察，不直接开仓"
    elif market_value == "limited":
        opp_value = "conditional" if (confirmed_count + fresh) >= 1 else "observe"
        opp_label = "条件触发" if opp_value == "conditional" else "只观察"
    else:  # on
        opp_value = "actionable" if (confirmed_count + fresh) >= 1 else "observe"
        opp_label = "可执行" if opp_value == "actionable" else "等更清晰确认"

    opp_why = f"午盘新增 {fresh}，确认 {confirmed_count}，候选 {approved}"

    return {
        "data":        {"value": data_value, "label": data_label, "tone": _permit_tone(data_value, "data"), "why": data_why},
        "market":      {"value": market_value, "label": market_label, "tone": _permit_tone(market_value, "market"), "why": market_why},
        "opportunity": {"value": opp_value, "label": opp_label, "tone": _permit_tone(opp_value, "opportunity"), "why": opp_why},
    }


def _readiness_why(readiness: dict[str, Any]) -> str:
    blockers = readiness.get("blockers") or []
    if blockers:
        return str(blockers[0].get("message") or "数据未对齐当日")
    warnings = readiness.get("warnings") or []
    if warnings:
        return str(warnings[0].get("message") or "数据存在告警")
    return "数据已对齐当日"


def _permit_tone(value: str, kind: str) -> str:
    if value in {"off", "none"}:
        return "risk"
    if value in {"shadow", "limited", "observe", "conditional"}:
        return "watch"
    if value in {"on", "actionable"}:
        return "positive"
    return "watch"
```

- [ ] **Step 2.4: 运行测试，确认通过**

Run: `cd apps/control-panel && python -m pytest tests/test_command_brief.py -v`
Expected: PASS（所有用例绿）

- [ ] **Step 2.5: 提交**

```bash
git add apps/control-panel/command_brief.py apps/control-panel/tests/test_command_brief.py
git commit -m "feat(command-brief): derive permits (data/market/opportunity)"
```

---

## Task 3: position_cap + first_action + forbid_today + reclassify_when

**Files:**
- Modify: `apps/control-panel/command_brief.py`
- Modify: `apps/control-panel/tests/test_command_brief.py`

- [ ] **Step 3.1: 追加测试**

在 `tests/test_command_brief.py` 顶部 import 行改成：

```python
from control_panel.command_brief import (  # noqa: E402
    derive_mode,
    derive_permits,
    derive_position_cap,
    derive_first_action,
    derive_forbid_today,
    derive_reclassify_when,
)
```

在测试文件末尾追加：

```python
class FirstActionTest(unittest.TestCase):
    def test_defense_returns_recover_data_action(self) -> None:
        action = derive_first_action(
            mode_value="defense",
            action_queue={"items": []},
            readiness=_readiness("blocked"),
        )
        self.assertEqual(action["kind"], "recover_data")
        self.assertEqual(action["url"], "/settings")

    def test_takes_first_pending_stock_action(self) -> None:
        action = derive_first_action(
            mode_value="probe",
            action_queue={
                "items": [
                    {
                        "key": "watchlist:600519",
                        "title": "600519 茅台",
                        "detail": "止损 1620 已破",
                        "tone": "sell",
                        "url": "/stock/600519",
                        "decision": {"value": "pending", "label": "待处理", "tone": "sell"},
                        "display_state": {"value": "pending", "label": "待处理", "tone": "sell"},
                    }
                ]
            },
            readiness=_readiness("live_ready"),
        )
        self.assertEqual(action["kind"], "stock")
        self.assertEqual(action["url"], "/stock/600519")
        self.assertIn("600519", action["title"])

    def test_observe_with_no_pending_falls_back_to_portfolio(self) -> None:
        action = derive_first_action(
            mode_value="observe",
            action_queue={"items": []},
            readiness=_readiness("live_ready"),
        )
        self.assertEqual(action["kind"], "system")
        self.assertEqual(action["url"], "/portfolio")


class PositionCapTest(unittest.TestCase):
    def test_takes_gate_position_cap(self) -> None:
        cap = derive_position_cap(
            mode_value="probe",
            gate=_gate(allow=True, label="试错"),
            decision_brief={"summary": {"position_cap": "0-0.3成"}},
        )
        self.assertEqual(cap["value"], "0-0.3成")
        self.assertEqual(cap["raw"], "0-0.3成")

    def test_defense_forces_zero_cap(self) -> None:
        cap = derive_position_cap(
            mode_value="defense",
            gate=_gate(allow=True, label="进攻"),
            decision_brief=None,
        )
        self.assertEqual(cap["value"], "0成")
        self.assertEqual(cap["tone"], "risk")


class ForbidTodayTest(unittest.TestCase):
    def test_defense_injects_no_new_positions(self) -> None:
        forbid = derive_forbid_today(
            mode_value="defense",
            decision_brief=None,
            action_groups=[],
        )
        titles = [item["title"] for item in forbid]
        self.assertTrue(any("不开新仓" in title for title in titles))

    def test_brief_avoid_points_are_included(self) -> None:
        forbid = derive_forbid_today(
            mode_value="probe",
            decision_brief={"focus": {"avoid_points": ["不追涨停板", "不打满仓"]}},
            action_groups=[],
        )
        titles = [item["title"] for item in forbid]
        self.assertIn("不追涨停板", titles)
        self.assertIn("不打满仓", titles)


class ReclassifyWhenTest(unittest.TestCase):
    def test_defense_has_two_paths(self) -> None:
        rules = derive_reclassify_when(
            mode_value="defense",
            readiness=_readiness("blocked"),
            gate=_gate(),
        )
        labels = [item["label"] for item in rules]
        self.assertIn("→ 观察", labels)
        self.assertIn("→ 试探", labels)

    def test_probe_has_progress_and_regression(self) -> None:
        rules = derive_reclassify_when(
            mode_value="probe",
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True),
        )
        labels = [item["label"] for item in rules]
        self.assertIn("→ 进攻", labels)
        self.assertIn("→ 观察", labels)
```

- [ ] **Step 3.2: 运行测试，确认失败**

Run: `cd apps/control-panel && python -m pytest tests/test_command_brief.py -v`
Expected: FAIL with ImportError for the new symbols

- [ ] **Step 3.3: 实现四个函数**

追加到 `apps/control-panel/command_brief.py`：

```python
_DEFENSE_POSITION_CAP = "0成"
_DEFAULT_POSITION_CAPS = {
    "defense": _DEFENSE_POSITION_CAP,
    "observe": "0-0.3成",
    "probe":   "0.3-0.5成",
    "offense": "0.5-0.8成",
}

_POSITION_CAP_NOTES = {
    "defense": "今天不开新仓；只处理旧仓与禁令。",
    "observe": "今天最多 0-0.3 成新仓；单笔 ≤ 0.5%。",
    "probe":   "试探仓位 0.3-0.5 成；单笔 ≤ 1%。",
    "offense": "可分批至 0.5-0.8 成；单笔 ≤ 1.5%。",
}


def derive_position_cap(
    *,
    mode_value: str,
    gate: dict[str, Any],
    decision_brief: dict[str, Any] | None,
) -> dict[str, Any]:
    if mode_value == "defense":
        raw, value = _DEFENSE_POSITION_CAP, _DEFENSE_POSITION_CAP
    else:
        brief_cap = ((decision_brief or {}).get("summary") or {}).get("position_cap")
        gate_cap = gate.get("position_cap")
        raw = str(brief_cap or gate_cap or _DEFAULT_POSITION_CAPS[mode_value])
        value = raw
    note = _POSITION_CAP_NOTES.get(mode_value, "按仓位纪律执行。")
    tone = "risk" if mode_value == "defense" else "watch" if mode_value in {"observe", "probe"} else "positive"
    return {"value": value, "raw": raw, "tone": tone, "note": note}


def derive_first_action(
    *,
    mode_value: str,
    action_queue: dict[str, Any],
    readiness: dict[str, Any],
) -> dict[str, Any]:
    if mode_value == "defense":
        msg = _readiness_why(readiness)
        return {
            "title": "先恢复数据链路",
            "reason": msg,
            "url": "/settings",
            "action_key": None,
            "tone": "risk",
            "kind": "recover_data",
        }

    items = (action_queue or {}).get("items") or []
    pending = [
        item for item in items
        if str(((item or {}).get("display_state") or {}).get("value") or item.get("decision", {}).get("value") or "pending") == "pending"
    ]
    if pending:
        first = pending[0]
        return {
            "title": str(first.get("title") or "处理下一条动作"),
            "reason": str(first.get("detail") or first.get("foot") or first.get("source") or "持仓优先处理"),
            "url": str(first.get("url") or "#action-lanes"),
            "action_key": str(first.get("key") or ""),
            "tone": str(first.get("tone") or "sell"),
            "kind": "stock",
        }

    if mode_value == "observe":
        return {
            "title": "先复核优先持仓",
            "reason": "今天没有强动作票，先把持仓边界过一遍。",
            "url": "/portfolio",
            "action_key": None,
            "tone": "watch",
            "kind": "system",
        }

    return {
        "title": "今天先观望",
        "reason": "没有 pending 动作；保留观察名单。",
        "url": "#judgement-chain",
        "action_key": None,
        "tone": "hold",
        "kind": "system",
    }


def derive_forbid_today(
    *,
    mode_value: str,
    decision_brief: dict[str, Any] | None,
    action_groups: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    if mode_value == "defense":
        items.append({
            "title": "今天不开新仓",
            "reason": "进攻阀门关闭，等数据回到 live_ready 再说。",
            "tone": "risk",
            "source": "command_brief",
        })

    avoid_group = next((g for g in action_groups if str(g.get("key")) == "avoid"), {}) or {}
    for entry in (avoid_group.get("items") or []):
        items.append({
            "title": str(entry.get("title") or entry.get("status") or "明确回避"),
            "reason": str(entry.get("detail") or entry.get("foot") or "按 avoid 组规则执行。"),
            "tone": str(entry.get("tone") or "risk"),
            "source": str(entry.get("source") or "avoid"),
        })

    for point in (((decision_brief or {}).get("focus") or {}).get("avoid_points") or [])[:3]:
        text = str(point or "").strip()
        if not text:
            continue
        items.append({
            "title": text,
            "reason": "来自总控简报 avoid_points",
            "tone": "risk",
            "source": "decision_brief",
        })

    if not items:
        items.append({
            "title": "不追高、不补亏",
            "reason": "默认禁令；保持纪律。",
            "tone": "risk",
            "source": "default",
        })

    return items[:4]


_RECLASSIFY_RULES = {
    "defense": [
        {"label": "→ 观察", "condition": "数据回到 live_ready", "evidence": "在 Settings 跑安全刷新", "url": "/settings"},
        {"label": "→ 试探", "condition": "数据就绪 + 进攻阀门为 limited", "evidence": "等阀门切换", "url": "/settings"},
    ],
    "observe": [
        {"label": "→ 试探", "condition": "主线强度 ≥ B 且 confirmed ≥ 1", "evidence": "看主线与午盘确认", "url": "/discovery"},
    ],
    "probe": [
        {"label": "→ 进攻", "condition": "confirmed ≥ 2 持续两日", "evidence": "看连续午盘确认", "url": "/discovery"},
        {"label": "→ 观察", "condition": "downgraded ≥ 2 或主线降级", "evidence": "看降级流", "url": "/discovery"},
    ],
    "offense": [
        {"label": "→ 试探", "condition": "fresh_candidates 连续 2 日为 0", "evidence": "看午盘新增", "url": "/discovery"},
    ],
}


def derive_reclassify_when(
    *,
    mode_value: str,
    readiness: dict[str, Any],
    gate: dict[str, Any],
) -> list[dict[str, Any]]:
    rules = list(_RECLASSIFY_RULES.get(mode_value) or [])
    if not rules:
        return []

    gate_summary = str(gate.get("summary") or "").strip()
    recommended = (readiness.get("recommended_tasks") or [None])[0]
    output: list[dict[str, Any]] = []
    for rule in rules:
        cond = rule["condition"]
        if gate_summary and gate_summary not in cond:
            cond = f"{cond}（参考：{gate_summary}）"
        if recommended and rule["url"] == "/settings":
            cond = f"{cond}；推荐先跑 {recommended}"
        output.append({
            "label": rule["label"],
            "condition": cond,
            "evidence": rule["evidence"],
            "url": rule["url"],
        })
    return output
```

- [ ] **Step 3.4: 运行测试，确认通过**

Run: `cd apps/control-panel && python -m pytest tests/test_command_brief.py -v`
Expected: PASS (全部绿)

- [ ] **Step 3.5: 提交**

```bash
git add apps/control-panel/command_brief.py apps/control-panel/tests/test_command_brief.py
git commit -m "feat(command-brief): derive position_cap/first_action/forbid/reclassify"
```

---

## Task 4: 判断链 4 维派生

**Files:**
- Modify: `apps/control-panel/command_brief.py`
- Modify: `apps/control-panel/tests/test_command_brief.py`

- [ ] **Step 4.1: 追加测试**

更新 imports 行，加入 `derive_judgement_chain`：

```python
from control_panel.command_brief import (  # noqa: E402
    derive_mode,
    derive_permits,
    derive_position_cap,
    derive_first_action,
    derive_forbid_today,
    derive_reclassify_when,
    derive_judgement_chain,
)
```

末尾追加：

```python
def _watchlist(priority: int = 0, observe: int = 0) -> dict[str, object]:
    return {
        "priority_codes": [f"60000{i}" for i in range(priority)],
        "observe_codes":  [f"60010{i}" for i in range(observe)],
        "stocks": [],
    }


def _screening(top_theme: str | None = "AI 算力", approved: int = 0, total: int = 0) -> dict[str, object]:
    themes = []
    if top_theme:
        themes = [{"theme": top_theme, "score": 3}]
    return {
        "market_themes": {"top_theme": top_theme, "themes": themes},
        "screening_summary": {
            "approved_count": approved,
            "candidate_total": total,
        },
    }


class JudgementChainTest(unittest.TestCase):
    def test_four_dimensions_present(self) -> None:
        chain = derive_judgement_chain(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="放开"),
            watchlist=_watchlist(priority=2),
            screening_batch=_screening("AI 算力", approved=4, total=12),
            confirmation=_confirmation(confirmed=1),
        )
        dims = [item["dim"] for item in chain]
        self.assertEqual(dims, ["market", "main_theme", "holdings_pressure", "new_quality"])

    def test_blocked_freezes_all_verdicts(self) -> None:
        chain = derive_judgement_chain(
            readiness=_readiness("blocked"),
            gate=_gate(allow=True, label="放开"),
            watchlist=_watchlist(priority=3),
            screening_batch=_screening("AI 算力", approved=4, total=12),
            confirmation=_confirmation(confirmed=2),
        )
        for item in chain:
            self.assertEqual(item["verdict"], "未对齐当日")
            self.assertIn("数据未对齐当日", item["evidence"])

    def test_market_verdict_strong_for_offense_label(self) -> None:
        chain = derive_judgement_chain(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="进攻放开"),
            watchlist=_watchlist(),
            screening_batch=_screening(),
            confirmation=_confirmation(),
        )
        market = next(item for item in chain if item["dim"] == "market")
        self.assertEqual(market["verdict"], "强")

    def test_holdings_pressure_high_when_priority_or_downgraded(self) -> None:
        chain = derive_judgement_chain(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="放开"),
            watchlist=_watchlist(priority=3),
            screening_batch=_screening(),
            confirmation=_confirmation(downgraded=2),
        )
        hp = next(item for item in chain if item["dim"] == "holdings_pressure")
        self.assertEqual(hp["verdict"], "高")

    def test_new_quality_good(self) -> None:
        chain = derive_judgement_chain(
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="放开"),
            watchlist=_watchlist(),
            screening_batch=_screening(),
            confirmation=_confirmation(confirmed=2),
        )
        nq = next(item for item in chain if item["dim"] == "new_quality")
        self.assertEqual(nq["verdict"], "好")
```

- [ ] **Step 4.2: 运行测试，确认失败**

Run: `cd apps/control-panel && python -m pytest tests/test_command_brief.py::JudgementChainTest -v`
Expected: FAIL with ImportError

- [ ] **Step 4.3: 实现 `derive_judgement_chain`**

追加到 `command_brief.py`：

```python
_FROZEN_EVIDENCE = ["数据未对齐当日"]
_FROZEN_IMPACT = "不展示旧主线 / 旧仓位 / 旧机会"


def derive_judgement_chain(
    *,
    readiness: dict[str, Any],
    gate: dict[str, Any],
    watchlist: dict[str, Any] | None,
    screening_batch: dict[str, Any] | None,
    confirmation: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    frozen = str(readiness.get("readiness_mode") or "blocked") == "blocked"

    def frozen_row(dim: str, title: str) -> dict[str, Any]:
        return {
            "dim": dim,
            "title": title,
            "verdict": "未对齐当日",
            "tone": "risk",
            "evidence": list(_FROZEN_EVIDENCE),
            "impact": _FROZEN_IMPACT,
        }

    if frozen:
        return [
            frozen_row("market", "市场环境"),
            frozen_row("main_theme", "主线强度"),
            frozen_row("holdings_pressure", "持仓压力"),
            frozen_row("new_quality", "新机会质量"),
        ]

    return [
        _market_dimension(gate),
        _main_theme_dimension(screening_batch),
        _holdings_pressure_dimension(watchlist, confirmation),
        _new_quality_dimension(confirmation),
    ]


def _market_dimension(gate: dict[str, Any]) -> dict[str, Any]:
    allow_new = bool(gate.get("allow_new_positions"))
    kind = _label_kind(str(gate.get("label") or ""))
    if not allow_new:
        verdict, tone, impact = "弱", "risk", "今天不允许开新仓"
    elif kind == "offense":
        verdict, tone, impact = "强", "positive", "今天允许分批开新仓，仍按单笔上限"
    else:
        verdict, tone, impact = "中", "watch", "今天可试探，单笔小、持有短"
    evidence = [str(gate.get("label") or "实时阀门"), str(gate.get("summary") or "").strip() or "无额外摘要"]
    return {"dim": "market", "title": "市场环境", "verdict": verdict, "tone": tone, "evidence": evidence, "impact": impact}


def _main_theme_dimension(screening_batch: dict[str, Any] | None) -> dict[str, Any]:
    themes = (screening_batch or {}).get("market_themes") or {}
    top = str(themes.get("top_theme") or "").strip()
    summary = (screening_batch or {}).get("screening_summary") or {}
    approved = int(summary.get("approved_count") or 0)
    if not top:
        verdict, tone, impact = "无", "risk", "今天没有可对齐的主线，不发散"
    elif approved >= 3:
        verdict, tone, impact = "A", "positive", f"围绕 {top} 行动，不发散"
    elif approved >= 1:
        verdict, tone, impact = "B", "watch", f"主线 {top} 还偏弱，验证后再加注"
    else:
        verdict, tone, impact = "C", "watch", f"主线 {top} 候选不足，仅作观察方向"
    evidence = [f"top_theme={top or '-'}", f"approved={approved}"]
    return {"dim": "main_theme", "title": "主线强度", "verdict": verdict, "tone": tone, "evidence": evidence, "impact": impact}


def _holdings_pressure_dimension(
    watchlist: dict[str, Any] | None,
    confirmation: dict[str, Any] | None,
) -> dict[str, Any]:
    priority = len((watchlist or {}).get("priority_codes") or [])
    counts = (confirmation or {}).get("counts") or {}
    downgraded = int(counts.get("downgraded") or 0)
    if priority >= 3 or downgraded >= 2:
        verdict, tone = "高", "risk"
    elif priority >= 1:
        verdict, tone = "中", "watch"
    else:
        verdict, tone = "低", "positive"
    impact = f"今天先处理 {priority} 个优先持仓" if priority else "持仓压力低，重点看新机会"
    evidence = [f"priority={priority}", f"downgraded={downgraded}"]
    return {"dim": "holdings_pressure", "title": "持仓压力", "verdict": verdict, "tone": tone, "evidence": evidence, "impact": impact}


def _new_quality_dimension(confirmation: dict[str, Any] | None) -> dict[str, Any]:
    counts = (confirmation or {}).get("counts") or {}
    confirmed = int(counts.get("confirmed") or 0)
    fresh = int(counts.get("fresh_candidates") or 0)
    downgraded = int(counts.get("downgraded") or 0)

    if confirmed >= 1 and downgraded == 0:
        verdict, tone = "好", "positive"
    elif confirmed == 0 and fresh > 0:
        verdict, tone = "中", "watch"
    elif confirmed >= 1 and downgraded >= 1:
        verdict, tone = "中", "watch"
    else:
        verdict, tone = "差", "risk"
    impact = "今天 / 明天再决定是否升级到必须处理"
    evidence = [f"confirmed={confirmed}", f"fresh={fresh}", f"downgraded={downgraded}"]
    return {"dim": "new_quality", "title": "新机会质量", "verdict": verdict, "tone": tone, "evidence": evidence, "impact": impact}
```

- [ ] **Step 4.4: 运行测试，确认通过**

Run: `cd apps/control-panel && python -m pytest tests/test_command_brief.py -v`
Expected: PASS

- [ ] **Step 4.5: 提交**

```bash
git add apps/control-panel/command_brief.py apps/control-panel/tests/test_command_brief.py
git commit -m "feat(command-brief): derive 4-dim judgement chain"
```

---

## Task 5: 动作四组（action_lanes）派生

**Files:**
- Modify: `apps/control-panel/command_brief.py`
- Modify: `apps/control-panel/tests/test_command_brief.py`

- [ ] **Step 5.1: 追加测试**

Imports 行加 `derive_action_lanes`。末尾追加：

```python
def _action_item(
    *,
    key: str,
    title: str,
    tone: str = "watch",
    detail: str = "",
    setup_label: str | None = None,
    stop_loss: str | None = None,
    url: str = "",
    state: str = "pending",
) -> dict[str, object]:
    return {
        "key": key,
        "title": title,
        "tone": tone,
        "detail": detail,
        "setup_label": setup_label,
        "stop_loss": stop_loss,
        "url": url,
        "source": "test",
        "decision": {"value": state, "label": state, "tone": tone},
        "display_state": {"value": state, "label": state, "tone": tone},
    }


def _groups(do_now=None, watch=None, avoid=None) -> list[dict[str, object]]:
    return [
        {"key": "do-now", "items": do_now or []},
        {"key": "watch",  "items": watch  or []},
        {"key": "avoid",  "items": avoid  or []},
    ]


class ActionLanesTest(unittest.TestCase):
    def test_four_lanes_always_returned(self) -> None:
        lanes = derive_action_lanes(
            mode_value="probe",
            action_groups=_groups(),
            decision_brief=None,
        )
        self.assertEqual([lane["key"] for lane in lanes], ["must", "conditional", "observe", "forbid"])

    def test_sell_item_goes_to_must(self) -> None:
        item = _action_item(key="watchlist:600519", title="600519 茅台", tone="sell", detail="止损 1620 已破")
        lanes = derive_action_lanes(
            mode_value="probe",
            action_groups=_groups(do_now=[item]),
            decision_brief=None,
        )
        must = next(lane for lane in lanes if lane["key"] == "must")
        self.assertEqual(must["items"][0]["code"], "600519")
        self.assertEqual(must["items"][0]["action_type"], "减仓")

    def test_watch_item_with_setup_label_goes_to_conditional(self) -> None:
        item = _action_item(
            key="screening:300750",
            title="300750 宁德",
            tone="watch",
            setup_label="突破 220",
            stop_loss="215",
        )
        lanes = derive_action_lanes(
            mode_value="probe",
            action_groups=_groups(watch=[item]),
            decision_brief=None,
        )
        conditional = next(lane for lane in lanes if lane["key"] == "conditional")
        self.assertEqual(conditional["items"][0]["trigger"], "突破 220")
        self.assertEqual(conditional["items"][0]["invalidate_when"], "215")

    def test_watch_item_without_trigger_goes_to_observe(self) -> None:
        item = _action_item(key="confirmation:600000", title="600000 浦发", tone="watch", detail="午盘新增观察")
        lanes = derive_action_lanes(
            mode_value="probe",
            action_groups=_groups(watch=[item]),
            decision_brief=None,
        )
        observe = next(lane for lane in lanes if lane["key"] == "observe")
        self.assertEqual(observe["items"][0]["code"], "600000")
        self.assertEqual(observe["items"][0]["action_type"], "仅观察")

    def test_dedup_keeps_higher_priority(self) -> None:
        same = _action_item(key="watchlist:600519", title="600519 茅台", tone="sell")
        same_watch = _action_item(key="watchlist:600519", title="600519 茅台", tone="watch")
        lanes = derive_action_lanes(
            mode_value="probe",
            action_groups=_groups(do_now=[same], watch=[same_watch]),
            decision_brief=None,
        )
        must = next(lane for lane in lanes if lane["key"] == "must")
        observe = next(lane for lane in lanes if lane["key"] == "observe")
        conditional = next(lane for lane in lanes if lane["key"] == "conditional")
        self.assertEqual(len(must["items"]), 1)
        self.assertFalse(any(it["code"] == "600519" for it in observe["items"]))
        self.assertFalse(any(it["code"] == "600519" for it in conditional["items"]))

    def test_defense_injects_no_new_positions_into_forbid(self) -> None:
        lanes = derive_action_lanes(
            mode_value="defense",
            action_groups=_groups(),
            decision_brief=None,
        )
        forbid = next(lane for lane in lanes if lane["key"] == "forbid")
        titles = [item["title"] for item in forbid["items"]]
        self.assertTrue(any("不开新仓" in t for t in titles))

    def test_minimum_output_when_everything_empty(self) -> None:
        lanes = derive_action_lanes(
            mode_value="observe",
            action_groups=_groups(),
            decision_brief=None,
        )
        total = sum(len(lane["items"]) for lane in lanes if lane["key"] in {"must", "conditional", "forbid"})
        self.assertGreaterEqual(total, 1)
```

- [ ] **Step 5.2: 运行测试，确认失败**

Run: `cd apps/control-panel && python -m pytest tests/test_command_brief.py::ActionLanesTest -v`
Expected: FAIL with ImportError

- [ ] **Step 5.3: 实现 `derive_action_lanes` 与若干内部 helper**

追加到 `command_brief.py`：

```python
import re


_STOCK_CODE_PATTERN = re.compile(r"\b(\d{6})\b")

_LANE_DEFS = [
    {"key": "must",        "title": "必须处理", "tone": "sell",  "subtitle": "今天闭环这几条，不漂移"},
    {"key": "conditional", "title": "条件触发", "tone": "watch", "subtitle": "有明确触发与失效，达到才动"},
    {"key": "observe",     "title": "只观察",   "tone": "hold",  "subtitle": "今天只看，不动"},
    {"key": "forbid",      "title": "禁止事项", "tone": "risk",  "subtitle": "明确禁线，今天不允许"},
]


def _extract_code(item: dict[str, Any]) -> str | None:
    for source in (item.get("title"), item.get("key"), item.get("code")):
        if not source:
            continue
        match = _STOCK_CODE_PATTERN.search(str(source))
        if match:
            return match.group(1)
    return None


def _extract_name(item: dict[str, Any]) -> str | None:
    title = str(item.get("title") or "")
    name = title
    code = _extract_code(item)
    if code:
        name = title.replace(code, "").strip(" -·")
    return name or None


def _infer_action_type(item: dict[str, Any]) -> str:
    explicit = item.get("action_type") or (item.get("decision") or {}).get("label")
    if explicit:
        return str(explicit)
    text = str(item.get("title") or "") + " " + str(item.get("detail") or "")
    if any(token in text for token in ("减仓", "止损", "清仓", "卖", "降")):
        return "减仓"
    if item.get("setup_label") or any(token in text for token in ("突破", "触发", "加观察")):
        return "等触发"
    tone = str(item.get("tone") or "")
    if tone == "sell":
        return "减仓"
    if tone == "positive":
        return "等突破"
    return "仅观察"


def _normalize_action_item(item: dict[str, Any]) -> dict[str, Any]:
    code = _extract_code(item)
    name = _extract_name(item)
    trigger = (
        item.get("trigger")
        or item.get("setup_label")
        or item.get("support")
        or item.get("resistance")
    )
    invalidate = item.get("invalidate_when") or item.get("stop_loss") or item.get("failure_condition")
    return {
        "key": str(item.get("key") or ""),
        "code": code,
        "name": name,
        "action_type": _infer_action_type(item),
        "reason": str(item.get("detail") or item.get("foot") or item.get("source") or ""),
        "trigger": str(trigger or "无明确触发"),
        "invalidate_when": str(invalidate or "-"),
        "source": str(item.get("source") or item.get("group_title") or ""),
        "url": item.get("url") or None,
        "tone": str(item.get("tone") or "watch"),
    }


def _has_explicit_trigger(item: dict[str, Any]) -> bool:
    return bool(item.get("setup_label") or item.get("breakout_price") or item.get("stop_loss"))


def derive_action_lanes(
    *,
    mode_value: str,
    action_groups: list[dict[str, Any]],
    decision_brief: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    grouped = {str(g.get("key") or ""): (g.get("items") or []) for g in (action_groups or [])}
    do_now = grouped.get("do-now") or []
    watch = grouped.get("watch") or []
    avoid = grouped.get("avoid") or []

    must_items: list[dict[str, Any]] = []
    conditional_items: list[dict[str, Any]] = []
    observe_items: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    def add(items: list[dict[str, Any]], raw: dict[str, Any]) -> None:
        key = str(raw.get("key") or "")
        if key and key in seen_keys:
            return
        seen_keys.add(key)
        items.append(_normalize_action_item(raw))

    for raw in do_now:
        tone = str(raw.get("tone") or "")
        if tone in {"sell", "positive"}:
            add(must_items, raw)
        elif _has_explicit_trigger(raw):
            add(conditional_items, raw)
        else:
            add(must_items, raw)

    for raw in watch:
        if _has_explicit_trigger(raw):
            add(conditional_items, raw)
        else:
            add(observe_items, raw)

    forbid_items = derive_forbid_today(
        mode_value=mode_value,
        decision_brief=decision_brief,
        action_groups=[{"key": "avoid", "items": avoid}],
    )

    if not (must_items or conditional_items or forbid_items):
        must_items.append({
            "key": "system:review-holdings-first",
            "code": None,
            "name": "先复核优先持仓",
            "action_type": "复核",
            "reason": "当前没有强动作票，先把持仓边界过一遍。",
            "trigger": "无明确触发",
            "invalidate_when": "-",
            "source": "command_brief",
            "url": "/portfolio",
            "tone": "watch",
        })

    lanes = []
    payload = {
        "must": must_items[:5],
        "conditional": conditional_items[:5],
        "observe": observe_items[:5],
        "forbid": forbid_items[:4],
    }
    for definition in _LANE_DEFS:
        lanes.append({**definition, "items": payload[definition["key"]]})
    return lanes
```

- [ ] **Step 5.4: 运行测试，确认通过**

Run: `cd apps/control-panel && python -m pytest tests/test_command_brief.py -v`
Expected: PASS

- [ ] **Step 5.5: 提交**

```bash
git add apps/control-panel/command_brief.py apps/control-panel/tests/test_command_brief.py
git commit -m "feat(command-brief): derive 4-lane action board with dedup and minimums"
```

---

## Task 6: midday_verify + trust + 顶层组合函数

**Files:**
- Modify: `apps/control-panel/command_brief.py`
- Modify: `apps/control-panel/tests/test_command_brief.py`

- [ ] **Step 6.1: 追加测试**

Imports 行追加：

```python
from control_panel.command_brief import (  # noqa: E402
    derive_mode,
    derive_permits,
    derive_position_cap,
    derive_first_action,
    derive_forbid_today,
    derive_reclassify_when,
    derive_judgement_chain,
    derive_action_lanes,
    derive_midday_verify,
    derive_trust,
    build_today_command_brief,
)
```

末尾追加：

```python
class MiddayVerifyTest(unittest.TestCase):
    def test_unavailable_when_confirmation_missing(self) -> None:
        verify = derive_midday_verify(
            confirmation=None,
            screening_batch=None,
            decision_brief=None,
            mode_value="observe",
        )
        self.assertFalse(verify["available"])
        self.assertIn("午盘验证尚未到位", verify["midday_status"])

    def test_lists_fresh_and_downgraded(self) -> None:
        verify = derive_midday_verify(
            confirmation=_confirmation(confirmed=1, fresh=2, downgraded=1),
            screening_batch={"screening_summary": {"execution_gate_status": "弱环境"}},
            decision_brief=None,
            mode_value="probe",
        )
        self.assertTrue(verify["available"])
        self.assertEqual(len(verify["fresh_candidates"]), 2)
        self.assertEqual(len(verify["downgraded"]), 1)
        self.assertIn("弱环境", verify["morning_takeaway"])


class TrustTest(unittest.TestCase):
    def test_summarises_readiness(self) -> None:
        trust = derive_trust(
            readiness={
                **_readiness("live_ready"),
                "source_freshness": [{"timely": True}, {"timely": True}],
                "quality_freshness": [{"timely": True}, {"timely": False}],
                "blockers": [],
                "warnings": [{"message": "w1"}],
            },
            refresh_status=None,
        )
        self.assertEqual(trust["readiness_mode"], "live_ready")
        self.assertEqual(trust["source_summary"], "2/2 timely")
        self.assertEqual(trust["quality_summary"], "1/2 ok")
        self.assertEqual(trust["warnings_count"], 1)


class BuildBriefTest(unittest.TestCase):
    def test_returns_complete_shape(self) -> None:
        brief = build_today_command_brief(
            trade_date="2026-05-22",
            readiness=_readiness("live_ready"),
            gate=_gate(allow=True, label="限制试错"),
            decision_brief=None,
            watchlist=_watchlist(priority=1),
            screening_batch=_screening("AI 算力", approved=2, total=8),
            confirmation=_confirmation(confirmed=1, fresh=1),
            action_groups=_groups(do_now=[_action_item(key="watchlist:600519", title="600519 茅台", tone="sell")]),
            action_queue={"items": [_action_item(key="watchlist:600519", title="600519 茅台", tone="sell")]},
            refresh_status=None,
        )
        for key in (
            "trade_date", "generated_at", "mode", "permits", "position_cap", "first_action",
            "forbid_today", "reclassify_when", "judgement_chain", "action_lanes",
            "midday_verify", "trust",
        ):
            self.assertIn(key, brief)
        self.assertEqual(brief["mode"]["value"], "probe")
        self.assertEqual(brief["first_action"]["kind"], "stock")
```

- [ ] **Step 6.2: 运行测试，确认失败**

Run: `cd apps/control-panel && python -m pytest tests/test_command_brief.py -v`
Expected: FAIL with ImportError

- [ ] **Step 6.3: 实现剩余函数**

追加到 `command_brief.py`：

```python
from datetime import datetime as _dt


def _confirmation_card(item: dict[str, Any]) -> dict[str, Any]:
    title = str(item.get("title") or item.get("name") or "")
    code = _extract_code(item) or str(item.get("code") or "")
    name = _extract_name(item) or str(item.get("name") or title)
    return {
        "name": name,
        "code": code,
        "reason": str(item.get("reason") or item.get("detail") or item.get("status") or ""),
        "url": str(item.get("detail_url") or item.get("url") or ""),
        "tone": str(item.get("tone") or "watch"),
    }


def derive_midday_verify(
    *,
    confirmation: dict[str, Any] | None,
    screening_batch: dict[str, Any] | None,
    decision_brief: dict[str, Any] | None,
    mode_value: str,
) -> dict[str, Any]:
    if not confirmation:
        return {
            "available": False,
            "morning_takeaway": "早盘结论暂未生成",
            "midday_status": "午盘验证尚未到位，当前不输出改判结论",
            "fresh_candidates": [],
            "downgraded": [],
            "next_day_condition": "",
            "verified_at": "",
        }

    counts = confirmation.get("counts") or {}
    confirmed = int(counts.get("confirmed") or 0)
    fresh = int(counts.get("fresh_candidates") or 0)
    downgraded = int(counts.get("downgraded") or 0)
    validation = str(confirmation.get("validation_status") or "ok")
    midday_status = f"{validation}：确认 {confirmed} · 新增 {fresh} · 降级 {downgraded}"

    morning = (
        ((decision_brief or {}).get("summary") or {}).get("gate_summary")
        or ((screening_batch or {}).get("screening_summary") or {}).get("execution_gate_status")
        or "早盘结论暂未生成"
    )

    fresh_cards = [_confirmation_card(item) for item in (confirmation.get("fresh_candidates") or [])[:3]]
    down_cards = [_confirmation_card(item) for item in (confirmation.get("downgraded") or [])[:3]]

    next_day = str(confirmation.get("next_day_focus") or "").strip()
    if not next_day:
        if mode_value == "probe":
            next_day = "若 fresh_candidates 隔日仍站住主线，明日可进观察"
        elif mode_value == "offense":
            next_day = "若 confirmed 持续两日，明日扩展到必须处理"
        elif mode_value == "observe":
            next_day = "若主线强度回到 B 以上，明日转试探"
        else:
            next_day = "等数据回到 live_ready 再讨论"

    return {
        "available": True,
        "morning_takeaway": str(morning),
        "midday_status": midday_status,
        "fresh_candidates": fresh_cards,
        "downgraded": down_cards,
        "next_day_condition": next_day,
        "verified_at": str(confirmation.get("generated_at") or ""),
    }


def derive_trust(
    *,
    readiness: dict[str, Any],
    refresh_status: dict[str, Any] | None,
) -> dict[str, Any]:
    src = readiness.get("source_freshness") or []
    src_ok = sum(1 for item in src if item.get("timely"))
    quality = readiness.get("quality_freshness") or []
    q_ok = sum(1 for item in quality if item.get("timely"))
    auto_summary = ""
    if refresh_status and isinstance(refresh_status, dict):
        decision = refresh_status.get("auto_refresh") or {}
        auto_summary = str(decision.get("summary") or "")
    return {
        "readiness_mode": str(readiness.get("readiness_mode") or "blocked"),
        "source_summary": f"{src_ok}/{len(src) or 0} timely",
        "quality_summary": f"{q_ok}/{len(quality) or 0} ok",
        "blockers_count": len(readiness.get("blockers") or []),
        "warnings_count": len(readiness.get("warnings") or []),
        "auto_refresh_summary": auto_summary,
    }


def build_today_command_brief(
    *,
    trade_date: str,
    readiness: dict[str, Any],
    gate: dict[str, Any],
    decision_brief: dict[str, Any] | None,
    watchlist: dict[str, Any] | None,
    screening_batch: dict[str, Any] | None,
    confirmation: dict[str, Any] | None,
    action_groups: list[dict[str, Any]],
    action_queue: dict[str, Any],
    refresh_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mode = derive_mode(
        readiness=readiness,
        gate=gate,
        confirmation=confirmation,
        decision_brief=decision_brief,
    )
    permits = derive_permits(
        readiness=readiness,
        gate=gate,
        confirmation=confirmation,
        screening_batch=screening_batch,
    )
    position_cap = derive_position_cap(
        mode_value=mode["value"],
        gate=gate,
        decision_brief=decision_brief,
    )
    first_action = derive_first_action(
        mode_value=mode["value"],
        action_queue=action_queue,
        readiness=readiness,
    )
    forbid = derive_forbid_today(
        mode_value=mode["value"],
        decision_brief=decision_brief,
        action_groups=action_groups,
    )
    reclassify = derive_reclassify_when(
        mode_value=mode["value"],
        readiness=readiness,
        gate=gate,
    )
    chain = derive_judgement_chain(
        readiness=readiness,
        gate=gate,
        watchlist=watchlist,
        screening_batch=screening_batch,
        confirmation=confirmation,
    )
    lanes = derive_action_lanes(
        mode_value=mode["value"],
        action_groups=action_groups,
        decision_brief=decision_brief,
    )
    midday = derive_midday_verify(
        confirmation=confirmation,
        screening_batch=screening_batch,
        decision_brief=decision_brief,
        mode_value=mode["value"],
    )
    trust = derive_trust(readiness=readiness, refresh_status=refresh_status)

    return {
        "trade_date": trade_date,
        "generated_at": _dt.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": mode,
        "permits": permits,
        "position_cap": position_cap,
        "first_action": first_action,
        "forbid_today": forbid,
        "reclassify_when": reclassify,
        "judgement_chain": chain,
        "action_lanes": lanes,
        "midday_verify": midday,
        "trust": trust,
    }
```

- [ ] **Step 6.4: 运行测试，确认通过**

Run: `cd apps/control-panel && python -m pytest tests/test_command_brief.py -v`
Expected: PASS

- [ ] **Step 6.5: 提交**

```bash
git add apps/control-panel/command_brief.py apps/control-panel/tests/test_command_brief.py
git commit -m "feat(command-brief): add midday_verify, trust, and top-level builder"
```

---

## Task 7: 接入 `build_today_view`

**Files:**
- Modify: `apps/control-panel/dashboard_data.py`

- [ ] **Step 7.1: 在测试文件追加端到端用例**

在 `tests/test_command_brief.py` 顶部 imports 行追加：

```python
from fastapi.testclient import TestClient  # noqa: E402

from control_panel.app import app  # noqa: E402
```

在文件末尾追加：

```python
class BuildTodayViewIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_api_today_includes_command_brief(self) -> None:
        response = self.client.get("/api/today")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        # 新字段
        self.assertIn("command_brief", payload)
        brief = payload["command_brief"]
        for key in ("mode", "permits", "position_cap", "first_action", "judgement_chain", "action_lanes", "midday_verify", "trust"):
            self.assertIn(key, brief)
        # mode.value 必须落到合法枚举
        self.assertIn(brief["mode"]["value"], {"defense", "observe", "probe", "offense"})

        # 旧字段必须保留
        for legacy_key in ("command_hero", "action_queue", "radar_cards", "risk_rows", "source_cards", "quality_cards", "hero", "counts"):
            self.assertIn(legacy_key, payload)
```

- [ ] **Step 7.2: 运行测试，确认失败**

Run: `cd apps/control-panel && python -m pytest tests/test_command_brief.py::BuildTodayViewIntegrationTest -v`
Expected: FAIL with `KeyError: 'command_brief'` 或 `AssertionError`

- [ ] **Step 7.3: 在 `dashboard_data.py` 顶部 import**

打开 `apps/control-panel/dashboard_data.py`，在第 80 行附近现有 `from decision_ledger import (...)` 之后追加一行（保持与项目"裸模块名"惯例一致）：

```python
from command_brief import build_today_command_brief  # type: ignore  # local module under apps/control-panel
```

- [ ] **Step 7.4: 在 `build_today_view` 返回前组装 `command_brief`**

在 [apps/control-panel/dashboard_data.py:9505](apps/control-panel/dashboard_data.py#L9505)（`generated_at = datetime.now().strftime(...)` 这一行附近）之前、`return { ... }` 之前，插入：

```python
    command_brief = build_today_command_brief(
        trade_date=trade_date,
        readiness=readiness,
        gate=gate,
        decision_brief=decision_brief,
        watchlist=watchlist,
        screening_batch=screening_batch,
        confirmation=confirmation,
        action_groups=action_groups,
        action_queue=action_queue,
        refresh_status=None,
    )
```

然后在 return 字典里（参考 `command_hero` 一行的位置）追加 `"command_brief": command_brief,`。

- [ ] **Step 7.5: 运行完整后端测试**

Run: `cd apps/control-panel && python -m pytest tests/test_command_brief.py tests/test_readiness.py -v`
Expected: PASS（命令台用例 + readiness 用例全部绿，旧字段未被破坏）

- [ ] **Step 7.6: 提交**

```bash
git add apps/control-panel/dashboard_data.py apps/control-panel/tests/test_command_brief.py
git commit -m "feat(dashboard): expose command_brief field on /api/today"
```

---

## Task 8: 前端类型

**Files:**
- Modify: `apps/web/src/lib/types.ts`

- [ ] **Step 8.1: 在 `types.ts` 末尾追加（紧挨 `TodayData` 之前）**

在 [apps/web/src/lib/types.ts](apps/web/src/lib/types.ts) 中，找到 `export interface TodayData` 定义之前（即 `export interface TodayCounts` 之后），插入：

```typescript
export type CommandBriefModeValue = "defense" | "observe" | "probe" | "offense";
export type CommandBriefPermitValue =
  | "on" | "off" | "shadow" | "limited" | "none" | "observe" | "conditional" | "actionable";

export interface CommandBriefPermit {
  value: CommandBriefPermitValue;
  label: string;
  tone: string;
  why: string;
}

export interface CommandBriefMode {
  value: CommandBriefModeValue;
  label: string;
  tone: string;
  summary: string;
  reasons: string[];
}

export interface CommandBriefPositionCap {
  value: string;
  raw: string;
  tone: string;
  note: string;
}

export interface CommandBriefFirstAction {
  title: string;
  reason: string;
  url: string;
  action_key?: string | null;
  tone: string;
  kind: "stock" | "system" | "recover_data";
}

export interface CommandBriefForbidItem {
  title: string;
  reason: string;
  tone: string;
  source: string;
}

export interface CommandBriefReclassifyRule {
  label: string;
  condition: string;
  evidence: string;
  url?: string | null;
}

export interface CommandBriefJudgement {
  dim: "market" | "main_theme" | "holdings_pressure" | "new_quality";
  title: string;
  verdict: string;
  tone: string;
  evidence: string[];
  impact: string;
}

export interface CommandBriefLaneItem {
  key: string;
  code: string | null;
  name: string | null;
  action_type: string;
  reason: string;
  trigger: string;
  invalidate_when: string;
  source: string;
  url?: string | null;
  tone: string;
}

export interface CommandBriefLane {
  key: "must" | "conditional" | "observe" | "forbid";
  title: string;
  tone: string;
  subtitle: string;
  items: CommandBriefLaneItem[] | CommandBriefForbidItem[];
}

export interface CommandBriefMiddayCard {
  name: string;
  code: string;
  reason: string;
  url: string;
  tone: string;
}

export interface CommandBriefMiddayVerify {
  available: boolean;
  morning_takeaway: string;
  midday_status: string;
  fresh_candidates: CommandBriefMiddayCard[];
  downgraded: CommandBriefMiddayCard[];
  next_day_condition: string;
  verified_at: string;
}

export interface CommandBriefTrust {
  readiness_mode: string;
  source_summary: string;
  quality_summary: string;
  blockers_count: number;
  warnings_count: number;
  auto_refresh_summary: string;
}

export interface TodayCommandBrief {
  trade_date: string;
  generated_at: string;
  mode: CommandBriefMode;
  permits: {
    data: CommandBriefPermit;
    market: CommandBriefPermit;
    opportunity: CommandBriefPermit;
  };
  position_cap: CommandBriefPositionCap;
  first_action: CommandBriefFirstAction;
  forbid_today: CommandBriefForbidItem[];
  reclassify_when: CommandBriefReclassifyRule[];
  judgement_chain: CommandBriefJudgement[];
  action_lanes: CommandBriefLane[];
  midday_verify: CommandBriefMiddayVerify;
  trust: CommandBriefTrust;
}
```

- [ ] **Step 8.2: 在 `TodayData` 接口里加可选字段**

修改 `export interface TodayData`，在 `quality_cards?: QualityCardData[];` 之后加：

```typescript
  command_brief?: TodayCommandBrief;
```

- [ ] **Step 8.3: 跑 typecheck，确认通过**

Run: `cd apps/web && pnpm typecheck`
Expected: 无类型错误

- [ ] **Step 8.4: 提交**

```bash
git add apps/web/src/lib/types.ts
git commit -m "feat(web): add TodayCommandBrief types"
```

---

## Task 9: 前端命令台子组件

**Files:**
- Create: `apps/web/src/components/command-brief/command-header.tsx`
- Create: `apps/web/src/components/command-brief/judgement-chain.tsx`
- Create: `apps/web/src/components/command-brief/action-lanes.tsx`
- Create: `apps/web/src/components/command-brief/midday-verify.tsx`
- Create: `apps/web/src/components/command-brief/trust-fold.tsx`
- Create: `apps/web/src/components/command-brief/index.ts`

- [ ] **Step 9.1: 写 `command-header.tsx`（A 区）**

```tsx
"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { Badge } from "@/components/badge";
import type {
  CommandBriefMode,
  CommandBriefPermit,
  CommandBriefPositionCap,
  CommandBriefFirstAction,
  CommandBriefForbidItem,
  CommandBriefReclassifyRule,
} from "@/lib/types";

const MODE_TONE: Record<string, string> = {
  defense: "negative",
  observe: "warning",
  probe: "info",
  offense: "positive",
};

function PermitChip({ permit, label }: { permit: CommandBriefPermit; label: string }) {
  return (
    <div className="rounded-md border border-[var(--border-subtle)] px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">{label}</div>
      <div className="mt-1 flex items-center gap-2">
        <Badge tone={permit.tone}>{permit.label}</Badge>
        <span className="text-[12px] font-mono text-[var(--text-secondary)]">{permit.value}</span>
      </div>
      <p className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">{permit.why}</p>
    </div>
  );
}

export function CommandHeader({
  mode,
  permits,
  positionCap,
  firstAction,
  forbid,
  reclassify,
  tradeDate,
}: {
  mode: CommandBriefMode;
  permits: { data: CommandBriefPermit; market: CommandBriefPermit; opportunity: CommandBriefPermit };
  positionCap: CommandBriefPositionCap;
  firstAction: CommandBriefFirstAction;
  forbid: CommandBriefForbidItem[];
  reclassify: CommandBriefReclassifyRule[];
  tradeDate: string;
}) {
  return (
    <section className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-4" data-od-id="command-header">
      <header className="flex flex-wrap items-center gap-2">
        <Badge tone={MODE_TONE[mode.value] || "info"}>今日模式 · {mode.label}</Badge>
        <span className="text-[12px] text-[var(--text-tertiary)]">交易日 {tradeDate}</span>
      </header>
      <h2 className="mt-2 text-[18px] font-semibold text-[var(--text-primary)]">{mode.summary}</h2>

      <div className="mt-3 grid gap-2 sm:grid-cols-3">
        <PermitChip permit={permits.data} label="数据许可" />
        <PermitChip permit={permits.market} label="市场许可" />
        <PermitChip permit={permits.opportunity} label="机会许可" />
      </div>

      <div className="mt-3 flex flex-wrap items-baseline gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2">
        <span className="text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">新仓上限</span>
        <strong className="font-mono text-[16px] text-[var(--text-primary)]">{positionCap.value}</strong>
        <span className="text-[12px] text-[var(--text-secondary)]">{positionCap.note}</span>
      </div>

      <Link
        href={firstAction.url || "#action-lanes"}
        className="mt-3 flex items-center justify-between rounded-md border border-[var(--border-subtle)] bg-[var(--bg-tertiary)] px-3 py-2 hover:bg-[var(--bg-tertiary-hover)]"
        data-od-id="first-action"
      >
        <div className="min-w-0">
          <div className="text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">第一动作</div>
          <div className="mt-1 text-[14px] font-medium text-[var(--text-primary)]">{firstAction.title}</div>
          <p className="mt-1 text-[12px] text-[var(--text-secondary)]">{firstAction.reason}</p>
        </div>
        <ChevronRight size={16} className="shrink-0 text-[var(--text-tertiary)]" />
      </Link>

      <div className="mt-3">
        <div className="text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">今日禁令</div>
        <ul className="mt-1 space-y-1 text-[12px] text-[var(--text-secondary)]">
          {forbid.slice(0, 3).map((item, idx) => (
            <li key={`${item.title}-${idx}`}>
              <span className="font-medium text-[var(--text-primary)]">{item.title}</span>
              <span className="ml-2 text-[var(--text-tertiary)]">{item.reason}</span>
            </li>
          ))}
        </ul>
      </div>

      <details className="mt-3 rounded-md border border-[var(--border-subtle)] px-3 py-2">
        <summary className="cursor-pointer text-[12px] font-medium text-[var(--text-primary)]">
          改判条件（{reclassify.length}）
        </summary>
        <ul className="mt-2 space-y-2 text-[12px] text-[var(--text-secondary)]">
          {reclassify.map((rule, idx) => (
            <li key={`${rule.label}-${idx}`}>
              <span className="font-medium text-[var(--text-primary)]">{rule.label}</span>
              <span className="ml-2">{rule.condition}</span>
              {rule.url ? (
                <Link href={rule.url} className="ml-2 underline">{rule.evidence}</Link>
              ) : (
                <span className="ml-2 text-[var(--text-tertiary)]">{rule.evidence}</span>
              )}
            </li>
          ))}
        </ul>
      </details>
    </section>
  );
}
```

- [ ] **Step 9.2: 写 `judgement-chain.tsx`（B 区）**

```tsx
"use client";

import { Badge } from "@/components/badge";
import type { CommandBriefJudgement } from "@/lib/types";

export function JudgementChain({ items }: { items: CommandBriefJudgement[] }) {
  return (
    <section
      id="judgement-chain"
      className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-4"
      data-od-id="judgement-chain"
    >
      <header>
        <div className="text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">Judgement Chain</div>
        <h2 className="mt-1 text-[16px] font-semibold text-[var(--text-primary)]">今日判断分四件事</h2>
      </header>
      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {items.map((item) => (
          <div key={item.dim} className="rounded-md border border-[var(--border-subtle)] p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[12px] font-medium text-[var(--text-primary)]">{item.title}</span>
              <Badge tone={item.tone}>{item.verdict}</Badge>
            </div>
            <ul className="mt-2 space-y-0.5 text-[11px] text-[var(--text-tertiary)]">
              {item.evidence.slice(0, 3).map((line, idx) => (
                <li key={`${item.dim}-evi-${idx}`}>· {line}</li>
              ))}
            </ul>
            <p className="mt-2 text-[12px] leading-5 text-[var(--text-secondary)]">{item.impact}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
```

- [ ] **Step 9.3: 写 `action-lanes.tsx`（C 区）**

```tsx
"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { Badge } from "@/components/badge";
import type { CommandBriefLane, CommandBriefLaneItem, CommandBriefForbidItem } from "@/lib/types";

function isLaneItem(item: CommandBriefLaneItem | CommandBriefForbidItem): item is CommandBriefLaneItem {
  return "action_type" in item;
}

function ActionLine({ item }: { item: CommandBriefLaneItem | CommandBriefForbidItem }) {
  if (!isLaneItem(item)) {
    return (
      <li className="rounded-md border border-[var(--border-subtle)] px-3 py-2">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[12px] font-medium text-[var(--text-primary)]">{item.title}</span>
          <Badge tone={item.tone}>禁止</Badge>
        </div>
        <p className="mt-1 text-[12px] text-[var(--text-secondary)]">{item.reason}</p>
      </li>
    );
  }
  return (
    <li className="rounded-md border border-[var(--border-subtle)] px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <span className="text-[12px] font-medium text-[var(--text-primary)]">{item.name || "-"}</span>
          {item.code ? <em className="ml-2 font-mono text-[11px] text-[var(--text-tertiary)] not-italic">{item.code}</em> : null}
        </div>
        <Badge tone={item.tone}>{item.action_type}</Badge>
      </div>
      <p className="mt-1 text-[12px] text-[var(--text-secondary)]">{item.reason || "—"}</p>
      <div className="mt-1 grid gap-1 text-[11px] text-[var(--text-tertiary)] sm:grid-cols-2">
        <span>触发：{item.trigger}</span>
        <span>失效：{item.invalidate_when}</span>
      </div>
      {item.url ? (
        <Link href={item.url} className="mt-2 inline-flex items-center gap-1 text-[12px] underline">
          打开 {item.code || "详情"}
          <ChevronRight size={12} />
        </Link>
      ) : null}
    </li>
  );
}

export function ActionLanes({ lanes }: { lanes: CommandBriefLane[] }) {
  return (
    <section
      id="action-lanes"
      className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-4"
      data-od-id="action-lanes"
    >
      <header>
        <div className="text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">Action Board</div>
        <h2 className="mt-1 text-[16px] font-semibold text-[var(--text-primary)]">今天的动作四件事</h2>
      </header>
      <div className="mt-3 grid gap-3 lg:grid-cols-4">
        {lanes.map((lane) => (
          <div key={lane.key} className="rounded-md border border-[var(--border-subtle)] p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[12px] font-semibold text-[var(--text-primary)]">{lane.title}</span>
              <Badge tone={lane.tone}>{lane.items.length}</Badge>
            </div>
            <p className="mt-1 text-[11px] text-[var(--text-tertiary)]">{lane.subtitle}</p>
            {lane.items.length ? (
              <ul className="mt-2 space-y-2">
                {lane.items.map((item, idx) => (
                  <ActionLine key={`${lane.key}-${idx}`} item={item} />
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-[12px] text-[var(--text-tertiary)]">今天此项为空。</p>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
```

- [ ] **Step 9.4: 写 `midday-verify.tsx`（D 区）**

```tsx
"use client";

import Link from "next/link";
import { Badge } from "@/components/badge";
import type { CommandBriefMiddayVerify, CommandBriefMiddayCard } from "@/lib/types";

function Card({ card, tone }: { card: CommandBriefMiddayCard; tone: string }) {
  return (
    <li className="rounded-md border border-[var(--border-subtle)] px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[12px] font-medium text-[var(--text-primary)]">{card.name}</span>
        <Badge tone={tone}>{card.code}</Badge>
      </div>
      <p className="mt-1 text-[12px] text-[var(--text-secondary)]">{card.reason || "—"}</p>
      {card.url ? <Link href={card.url} className="text-[12px] underline">打开</Link> : null}
    </li>
  );
}

export function MiddayVerify({ payload }: { payload: CommandBriefMiddayVerify }) {
  if (!payload.available) {
    return (
      <section className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-4">
        <div className="text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">Midday Verify</div>
        <p className="mt-2 text-[14px] text-[var(--text-primary)]">{payload.midday_status}</p>
      </section>
    );
  }
  return (
    <section className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-4" data-od-id="midday-verify">
      <header className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">Midday Verify</span>
        <span className="text-[12px] text-[var(--text-tertiary)]">{payload.verified_at}</span>
      </header>
      <div className="mt-2 grid gap-3 lg:grid-cols-3">
        <div>
          <div className="text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">早盘结论</div>
          <p className="mt-1 text-[12px] text-[var(--text-secondary)]">{payload.morning_takeaway}</p>
          <div className="mt-2 text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">午盘验证</div>
          <p className="mt-1 text-[12px] text-[var(--text-secondary)]">{payload.midday_status}</p>
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">新增 ({payload.fresh_candidates.length})</div>
          <ul className="mt-1 space-y-2">
            {payload.fresh_candidates.map((card, idx) => (
              <Card key={`fresh-${idx}`} card={card} tone="positive" />
            ))}
            {!payload.fresh_candidates.length ? <li className="text-[12px] text-[var(--text-tertiary)]">今日无新增。</li> : null}
          </ul>
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">降级 ({payload.downgraded.length})</div>
          <ul className="mt-1 space-y-2">
            {payload.downgraded.map((card, idx) => (
              <Card key={`down-${idx}`} card={card} tone="risk" />
            ))}
            {!payload.downgraded.length ? <li className="text-[12px] text-[var(--text-tertiary)]">今日无降级。</li> : null}
          </ul>
        </div>
      </div>
      <div className="mt-3 rounded-md border border-dashed border-[var(--border-subtle)] px-3 py-2">
        <div className="text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">明日延续条件</div>
        <p className="mt-1 text-[12px] text-[var(--text-secondary)]">{payload.next_day_condition}</p>
      </div>
    </section>
  );
}
```

- [ ] **Step 9.5: 写 `trust-fold.tsx`（E 区）**

```tsx
"use client";

import type { ReactNode } from "react";
import { Badge } from "@/components/badge";
import type { CommandBriefTrust } from "@/lib/types";

export function TrustFold({ trust, children }: { trust: CommandBriefTrust; children?: ReactNode }) {
  return (
    <details className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3" data-od-id="trust-fold">
      <summary className="flex cursor-pointer flex-wrap items-center gap-2">
        <span className="text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">Trust</span>
        <Badge tone={trust.readiness_mode === "live_ready" ? "positive" : trust.readiness_mode === "shadow_only" ? "warning" : "negative"}>
          {trust.readiness_mode}
        </Badge>
        <span className="text-[12px] text-[var(--text-secondary)]">数据源 {trust.source_summary}</span>
        <span className="text-[12px] text-[var(--text-secondary)]">质检 {trust.quality_summary}</span>
        {trust.warnings_count ? <span className="text-[12px] text-[var(--warning)]">告警 {trust.warnings_count}</span> : null}
        {trust.blockers_count ? <span className="text-[12px] text-[var(--negative)]">阻塞 {trust.blockers_count}</span> : null}
        {trust.auto_refresh_summary ? <span className="text-[12px] text-[var(--text-tertiary)]">{trust.auto_refresh_summary}</span> : null}
      </summary>
      <div className="mt-3 space-y-3">{children}</div>
    </details>
  );
}
```

- [ ] **Step 9.6: 写 barrel `index.ts`**

```typescript
export { CommandHeader } from "./command-header";
export { JudgementChain } from "./judgement-chain";
export { ActionLanes } from "./action-lanes";
export { MiddayVerify } from "./midday-verify";
export { TrustFold } from "./trust-fold";
```

- [ ] **Step 9.7: 跑 typecheck**

Run: `cd apps/web && pnpm typecheck`
Expected: 无错误

- [ ] **Step 9.8: 提交**

```bash
git add apps/web/src/components/command-brief/
git commit -m "feat(web): add command brief section components"
```

---

## Task 10: 重写 `page.tsx`

**Files:**
- Modify: `apps/web/src/app/page.tsx`

- [ ] **Step 10.1: 用以下内容替换整文件**

完整覆写 `apps/web/src/app/page.tsx`：

```tsx
"use client";

import { AlertCircle, FileDown, RefreshCw } from "lucide-react";
import { useRuns, useRefreshStatus, useTodayData } from "@/lib/hooks";

import {
  CommandHeader,
  JudgementChain,
  ActionLanes,
  MiddayVerify,
  TrustFold,
} from "@/components/command-brief";

export default function CommandCenterPage() {
  const today = useTodayData();
  const runsQuery = useRuns();
  const refreshStatus = useRefreshStatus("today", true, { auto: true });
  const data = today.data;
  const brief = data?.command_brief;
  const tradeDate = brief?.trade_date || data?.expected_trade_date || data?.trade_date || "-";

  return (
    <main className="war-room">
      <div className="war-room-inner">
        <header className="war-topbar">
          <div>
            <div className="war-eyebrow">Daily Command Brief</div>
            <h1>每日交易命令台</h1>
          </div>
          <div className="war-top-actions">
            <button
              type="button"
              className="focus-ring war-tool-btn"
              onClick={() => void today.refetch()}
            >
              <RefreshCw size={14} className={today.isFetching ? "animate-spin" : ""} />
              刷新
            </button>
            <button
              type="button"
              className="focus-ring war-tool-btn"
              onClick={() => window.print()}
            >
              <FileDown size={14} />
              导出简报
            </button>
          </div>
        </header>

        {today.isError ? (
          <div className="war-error">
            <AlertCircle size={17} className="mt-0.5 shrink-0 text-[var(--warning)]" />
            <div className="min-w-0 flex-1">
              <div className="font-medium text-[var(--text-primary)]">后端数据暂不可用</div>
              <div className="mt-1">命令台骨架已加载，FastAPI 启动后会自动重新获取 `/api/today`。</div>
            </div>
            <button
              type="button"
              className="focus-ring rounded-md border border-[var(--border-subtle)] px-2.5 py-1 text-[12px] text-[var(--text-primary)]"
              onClick={() => void today.refetch()}
            >
              重试
            </button>
          </div>
        ) : null}

        {brief ? (
          <>
            <CommandHeader
              mode={brief.mode}
              permits={brief.permits}
              positionCap={brief.position_cap}
              firstAction={brief.first_action}
              forbid={brief.forbid_today}
              reclassify={brief.reclassify_when}
              tradeDate={tradeDate}
            />
            <JudgementChain items={brief.judgement_chain} />
            <ActionLanes lanes={brief.action_lanes} />
            <MiddayVerify payload={brief.midday_verify} />
            <TrustFold trust={brief.trust}>
              <div className="text-[12px] text-[var(--text-secondary)]">
                运行记录 {runsQuery.data?.runs?.length ?? 0} 条 · 自动刷新 {refreshStatus.data?.recommended_task?.title ?? "-"}
              </div>
            </TrustFold>
          </>
        ) : (
          <div className="war-error">
            <AlertCircle size={17} className="mt-0.5 shrink-0 text-[var(--warning)]" />
            <div className="min-w-0 flex-1">
              <div className="font-medium text-[var(--text-primary)]">命令台数据未到位</div>
              <div className="mt-1">后端尚未返回 `command_brief`；先到 Settings 跑安全刷新。</div>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
```

- [ ] **Step 10.2: 跑 typecheck + lint**

Run: `cd apps/web && pnpm typecheck && pnpm lint`
Expected: 无错误。若 lint 提示未使用 import，删除冗余 import。

- [ ] **Step 10.3: 启动后端 + 前端，目测**

按现有项目惯例：

```bash
bash start_prism.sh
```

打开浏览器到 `http://localhost:3000`，按四种 readiness/gate 场景目测（如有 mock 切换工具，分别切到 defense / observe / probe / offense；否则至少观察当下状态）。

验收要点：

1. 首屏（不滚动）能看到 模式 + 三个许可灯 + 仓位上限 + 第一动作 + 今日禁令
2. mode=defense / gate.allow=false 时，仍能看到"还能做什么 / 改判条件"，**不只是"否 / 0 成"**
3. 判断链 4 卡都显示
4. 动作四组都显示，空组显示"今天此项为空。"
5. 午盘改判区不可用时显示提示语，可用时显示新增 / 降级
6. Trust 折叠默认收起，展开后看到 readiness 摘要

- [ ] **Step 10.4: 提交**

```bash
git add apps/web/src/app/page.tsx
git commit -m "feat(web): rewrite homepage as daily command brief"
```

---

## Task 11: 最终回归

**Files:** (无新文件)

- [ ] **Step 11.1: 跑全部后端测试**

Run: `cd apps/control-panel && python -m pytest tests/ -q`
Expected: 全绿。若有 readiness/portfolio 相关失败，回看 Task 7 是否破坏了 `build_today_view` 中字段顺序或类型。

- [ ] **Step 11.2: 跑前端 typecheck + lint**

Run: `cd apps/web && pnpm typecheck && pnpm lint`
Expected: 无错误

- [ ] **Step 11.3: 复核首页 10 秒目标**

打开浏览器，从首页加载完成开始计时，10 秒内必须读懂：
- 今日模式
- 三个许可灯
- 新仓上限
- 第一动作
- 今日禁令 ≥1 条

若不达标，回到 Task 10 调整 CommandHeader 的优先级布局（把 First Action 上移、缩减 Trust 行高度）。

- [ ] **Step 11.4: 最终空提交（标记完工）**

```bash
git commit --allow-empty -m "chore: daily command brief homepage complete"
```

---

## Self-Review 笔记

- spec 中每个章节都有对应任务：
  - §4 数据形状 → Task 1–6（每个 derive_* 单测）
  - §5 派生规则 → Task 1–6（覆盖各种矩阵）
  - §6 前端结构 → Task 8–10
  - §7 兼容性 → Task 7（保留旧字段的测试断言）
  - §8 测试策略 → Task 1–7（pytest）+ Task 10/11（typecheck/lint + 目测）
  - §9 验收清单 → Task 10/11 step 中明确列出
- 没有占位符；所有代码块都给出完整内容。
- 类型一致：`derive_forbid_today` 在 Task 3 与 Task 5 共用，签名与字段一致。
- 函数命名一致：`derive_mode / derive_permits / derive_position_cap / derive_first_action / derive_forbid_today / derive_reclassify_when / derive_judgement_chain / derive_action_lanes / derive_midday_verify / derive_trust / build_today_command_brief`。
- 文件路径一致：所有引用都用绝对相对项目根路径。
