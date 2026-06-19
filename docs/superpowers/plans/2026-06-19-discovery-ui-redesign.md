# Discovery Page UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "today's action" column to the discovery table (aggregating scattered entry_plan data into one directive), make the page self-consistent when the offense valve is off (hide the fake-gradient funnel, sort by real priority_score), and surface Wave-1's exit-return-tracking data as a lightweight outcome panel.

**Architecture:** Two backend helpers (build_action_directive aggregating entry_plan; load_recent_exit_tracking reading the Wave-1 jsonl) feed two new frontend components (ActionCell replacing the misleading decision-rank first column; an exit-trajectory panel) plus a valve-state branch that swaps the funnel for an observation-mode banner. All data already exists in the payload or the jsonl — this is aggregation and presentation, not new data collection.

**Tech Stack:** Python 3.14 + pytest (backend), Next.js + React + TypeScript (frontend). Backend tests follow the `apps/control-panel/tests/test_discovery_*.py` pattern (sys.path injection + `dashboard_data.build_opportunities_view()` calls). Frontend verified via `next build`.

**Spec:** `docs/superpowers/specs/2026-06-19-discovery-ui-redesign-design.md`

**Execution order:** Task A → C → B → D → E (backend first, then frontend, E last as it depends on B).

---

## File Structure

New files:
- `tests/test_action_directive.py` — unit tests for build_action_directive (Task A)
- `tests/test_exit_tracking_payload.py` — unit tests for load_recent_exit_tracking (Task C)
- `apps/web/src/app/discovery/discovery-action-cell.tsx` — ActionCell component (Task B)

Modified files:
- `apps/control-panel/dashboard_data.py` — add `build_action_directive`, `load_recent_exit_tracking`; wire both into the opportunities payload (Tasks A, C)
- `apps/web/src/lib/types.ts` — add `ActionDirective`, `ExitTrackingRecord` interfaces; extend `StockListCard` + opportunities view type (Tasks B, D)
- `apps/web/src/app/discovery/discovery-observation-workbench.tsx` — swap first column to ActionCell; add valve-state branch hiding the funnel (Tasks B, E)
- `apps/web/src/app/discovery/discovery-context-panels.tsx` — add exit-trajectory block to the continuity panel (Task D)
- `apps/web/src/lib/hooks.ts` — the `useOpportunities` hook already returns the payload; no change needed unless the type needs widening

---

## Task A: Backend build_action_directive

**Files:**
- Modify: `apps/control-panel/dashboard_data.py` (add function near `public_opportunity_card_payload` ~line 5348; add `"action_directive"` to the allowlist)
- Test: `tests/test_action_directive.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_action_directive.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROL_PANEL_ROOT = REPO_ROOT / "apps" / "control-panel"
if str(CONTROL_PANEL_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROL_PANEL_ROOT))

from dashboard_data import build_action_directive  # noqa: E402


def _card(**overrides):
    base = {
        "code": "000032",
        "name": "深桑达A",
        "suggested_action": "review",
        "suggested_action_label": "等触发",
        "hard_gate_max_action": "actionable",
        "hard_gate_block_reason": None,
        "entry_plan": {
            "action": "等待突破 82.89 后回踩不破再介入",
            "trigger": "放量突破 82.89",
            "invalidate": "跌回 67.53 下方",
            "sizing": "半仓",
            "levels": {"trigger": 82.89, "invalidate": 67.53},
        },
    }
    base.update(overrides)
    return base


def test_valve_open_actionable_shows_openable():
    d = build_action_directive(_card(), valve_open=True)
    assert d["headline"] == "可开仓"
    assert d["trigger_price"] == 82.89
    assert d["invalidate_price"] == 67.53
    assert d["sizing"] == "半仓"
    assert d["blocker"] is None


def test_valve_closed_forces_observe_only():
    d = build_action_directive(_card(hard_gate_max_action="actionable"), valve_open=False)
    assert d["headline"] == "只观察"
    assert d["blocker"] is not None  # carries the reason the valve is shut


def test_hard_gate_blocked_shows_cannot_open_even_if_valve_open():
    d = build_action_directive(
        _card(hard_gate_max_action="shadow", hard_gate_block_reason="整体环境偏弱"),
        valve_open=True,
    )
    assert d["headline"] == "不可开仓"
    assert "整体环境偏弱" in d["blocker"]


def test_trial_suggested_action_shows_wait_trigger():
    d = build_action_directive(_card(suggested_action="trial", suggested_action_label="试错"), valve_open=True)
    assert d["headline"] == "等触发"


def test_missing_entry_plan_still_returns_directive():
    d = build_action_directive(_card(entry_plan=None), valve_open=True)
    assert d["headline"] in ("可开仓", "等触发", "只观察", "不可开仓", "可加仓")
    assert d["trigger_price"] is None
    assert d["invalidate_price"] is None


def test_action_text_falls_back_to_suggested_action_label():
    d = build_action_directive(_card(entry_plan=None, suggested_action_label="等触发"), valve_open=True)
    assert d["action_text"] == "等触发"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_action_directive.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_action_directive'`.

- [ ] **Step 3: Implement build_action_directive**

In `apps/control-panel/dashboard_data.py`, add this function immediately BEFORE `def public_opportunity_card_payload` (line 5348):

```python
def build_action_directive(card: Mapping[str, Any], *, valve_open: bool = True) -> dict[str, Any]:
    """Aggregate scattered entry_plan / gate / suggested_action fields into one
    display-ready action directive for the discovery table's action column.

    The headline is the single most important signal: when the offense valve is
    shut, every candidate collapses to '只观察' regardless of its own gate, so the
    page stops pretending there is a buyable gradient. Otherwise the headline
    reflects the hard-gate ceiling and the suggested action.
    """

    gate = str(card.get("hard_gate_max_action") or "").lower()
    block_reason = card.get("hard_gate_block_reason")
    suggested = str(card.get("suggested_action") or "").lower()
    entry_plan = card.get("entry_plan") or {}
    levels = entry_plan.get("levels") if isinstance(entry_plan, dict) else None

    if not valve_open:
        headline = "只观察"
        blocker = block_reason or "进攻阀门关闭，今日不开新仓"
    elif gate in {"shadow", "blocked"} or block_reason:
        headline = "不可开仓"
        blocker = block_reason or "硬闸门阻断"
    elif suggested == "trial":
        headline = "等触发"
        blocker = None
    elif suggested == "add":
        headline = "可加仓"
        blocker = None
    elif gate in {"actionable", "active"} or suggested in {"review", "open", "buy"}:
        headline = "可开仓"
        blocker = None
    else:
        headline = "等触发" if suggested else "只观察"
        blocker = None

    action_text = (
        (entry_plan.get("action") if isinstance(entry_plan, dict) else None)
        or card.get("suggested_action_label")
        or headline
    )
    sizing = entry_plan.get("sizing") if isinstance(entry_plan, dict) else None

    def _level(key: str):
        if not isinstance(levels, dict):
            return None
        value = levels.get(key)
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    return {
        "headline": headline,
        "action_text": action_text,
        "trigger_price": _level("trigger"),
        "invalidate_price": _level("invalidate"),
        "sizing": sizing,
        "blocker": blocker,
    }
```

- [ ] **Step 4: Add action_directive to the card payload**

Still in `public_opportunity_card_payload`, the payload is built from an allowlist (line 5377-5445) plus post-processing. The `action_directive` is a computed field, not a card key, so it must be added AFTER the allowlist dict is built. Find the line `payload = {key: card.get(key) for key in allowlist if _public_value_present(card.get(key))}` (line 5446) and add immediately after it:

```python
    action_directive = build_action_directive(card, valve_open=True)
    if action_directive and any(v is not None for v in action_directive.values()):
        payload["action_directive"] = action_directive
```

Note: `valve_open=True` here is a per-card default. The frontend (Task E) re-derives the effective headline from valve state, so the backend always emits the valve-open directive and the frontend overrides the headline display when the valve is off. This keeps the payload stable across valve states (avoids cache invalidation when the valve flips).

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_action_directive.py -v`
Expected: PASS — all 6 tests green.

- [ ] **Step 6: Run full backend suite**

Run: `pytest -q --ignore=tests/test_opportunity_v2.py`
Expected: PASS (the ignored test is a known pre-existing environment-local failure unrelated to this work).

- [ ] **Step 7: Commit**

```bash
git add apps/control-panel/dashboard_data.py tests/test_action_directive.py
git commit -m "feat(discovery): build_action_directive aggregates entry_plan into one directive

Aggregates the scattered entry_plan (action/trigger/invalidate/levels),
hard_gate, and suggested_action fields into a single display-ready
action_directive object attached to each opportunity card. The headline
collapses to '只观察' when the valve is shut, so the page stops
pretending there is a buyable gradient. Task A of discovery-ui redesign."
```

---

## Task C: Backend load_recent_exit_tracking

**Files:**
- Modify: `apps/control-panel/dashboard_data.py` (add function; wire into `build_opportunities_view` return)
- Test: `tests/test_exit_tracking_payload.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_exit_tracking_payload.py`:

```python
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROL_PANEL_ROOT = REPO_ROOT / "apps" / "control-panel"
if str(CONTROL_PANEL_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROL_PANEL_ROOT))

from dashboard_data import load_recent_exit_tracking  # noqa: E402


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def _record(code: str, exit_date: str, outcome: str, **extra) -> dict:
    return {
        "code": code,
        "name": f"测试{code}",
        "exit_date": exit_date,
        "exit_price": 10.0,
        "reason": "x",
        "theme": "y",
        "status": "settled",
        "holding_window_days": 5,
        "daily_prices": [],
        "net_return": -0.05,
        "outcome": outcome,
        "recorded_at": f"{exit_date}T09:40:00",
        **extra,
    }


def test_returns_recent_records_with_flat_fields(tmp_path: Path, monkeypatch):
    store = tmp_path / "exit_tracking.jsonl"
    today = date.today()
    recent = _record("000032", (today - timedelta(days=2)).isoformat(), "true_exit")
    old = _record("000100", (today - timedelta(days=40)).isoformat(), "misjudged")
    _write_jsonl(store, [recent, old])

    monkeypatch.setattr("dashboard_data.EXIT_TRACKING_STORE", store)
    result = load_recent_exit_tracking(days=30)

    assert len(result) == 1
    rec = result[0]
    assert rec["code"] == "000032"
    assert rec["outcome"] == "true_exit"
    assert rec["net_return"] == -0.05
    # Flat fields only — no internal daily_prices leaked
    assert "daily_prices" not in rec
    assert "holding_window_days" not in rec


def test_missing_store_returns_empty_list(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("dashboard_data.EXIT_TRACKING_STORE", tmp_path / "nonexistent.jsonl")
    assert load_recent_exit_tracking(days=30) == []


def test_corrupt_jsonl_returns_empty_list(tmp_path: Path, monkeypatch):
    store = tmp_path / "exit_tracking.jsonl"
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text("{not valid json\n", encoding="utf-8")
    monkeypatch.setattr("dashboard_data.EXIT_TRACKING_STORE", store)
    assert load_recent_exit_tracking(days=30) == []


def test_sorted_by_exit_date_desc(tmp_path: Path, monkeypatch):
    store = tmp_path / "exit_tracking.jsonl"
    today = date.today()
    older = _record("000032", (today - timedelta(days=10)).isoformat(), "true_exit")
    newer = _record("000100", (today - timedelta(days=2)).isoformat(), "misjudged")
    _write_jsonl(store, [older, newer])
    monkeypatch.setattr("dashboard_data.EXIT_TRACKING_STORE", store)
    result = load_recent_exit_tracking(days=30)
    assert result[0]["code"] == "000100"
    assert result[1]["code"] == "000032"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_exit_tracking_payload.py -v`
Expected: FAIL — `ImportError: cannot import name 'load_recent_exit_tracking'`.

- [ ] **Step 3: Implement load_recent_exit_tracking**

In `apps/control-panel/dashboard_data.py`, add a module-level constant near the other path constants (around line 130, near `APP_STATE_REPOSITORY`):

```python
EXIT_TRACKING_STORE = RUNTIME_ROOT / "exit_tracking.jsonl"
```

Then add the function (place it near the other `load_*` helpers, e.g. just before `build_opportunities_view` at line 8803):

```python
def load_recent_exit_tracking(*, days: int = 30, store: Path | None = None) -> list[dict[str, Any]]:
    """Load recent exit-return-tracking records for the discovery continuity panel.

    Reads the append-only JSONL written by exit_return_tracker.record_exit /
    update_exits (Wave 1). Returns a flat, display-ready list sorted by
    exit_date descending, filtered to the last ``days`` days. Gracefully
    returns [] when the store is missing or corrupt — never raises.
    """
    path = store or EXIT_TRACKING_STORE
    if not path.exists():
        return []
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    records: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                exit_date = str(rec.get("exit_date", ""))
                if exit_date < cutoff:
                    continue
                records.append({
                    "code": rec.get("code"),
                    "name": rec.get("name"),
                    "exit_date": exit_date,
                    "outcome": rec.get("outcome"),
                    "net_return": rec.get("net_return"),
                    "status": rec.get("status"),
                    "theme": rec.get("theme"),
                })
    except OSError:
        return []
    records.sort(key=lambda r: str(r.get("exit_date", "")), reverse=True)
    return records
```

Add the needed imports at the top if not already present: `from datetime import date, timedelta` (verify `date` is imported — `dashboard_data.py` likely imports `datetime` already; add `date, timedelta` explicitly).

- [ ] **Step 4: Wire exit_tracking into build_opportunities_view**

In `build_opportunities_view` (line 8803), find the final `return {` dict. Add `exit_tracking` to it. Locate the return by searching for the dict keys that already exist (e.g. `"groups"`, `"lifecycle_groups"`, `"readiness"`). Add this key alongside them:

```python
        "exit_tracking": load_recent_exit_tracking(days=30),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_exit_tracking_payload.py -v`
Expected: PASS — all 4 tests green.

- [ ] **Step 6: Run full backend suite**

Run: `pytest -q --ignore=tests/test_opportunity_v2.py`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/control-panel/dashboard_data.py tests/test_exit_tracking_payload.py
git commit -m "feat(discovery): expose Wave-1 exit-return tracking in opportunities API

load_recent_exit_tracking reads the append-only jsonl written by
exit_return_tracker (Wave 1) and attaches a flat, display-ready list to
the opportunities payload. Gracefully returns [] when the store is
missing or corrupt. Surfaces the post-exit outcome (true_exit /
misjudged / inconclusive) and net_return that previously had no UI.
Task C of discovery-ui redesign."
```

---

## Task B: Frontend ActionCell (today's action column)

**Files:**
- Create: `apps/web/src/app/discovery/discovery-action-cell.tsx`
- Modify: `apps/web/src/lib/types.ts` (add `ActionDirective` interface, extend `StockListCard`)
- Modify: `apps/web/src/app/discovery/discovery-observation-workbench.tsx` (swap first column)

- [ ] **Step 1: Add the ActionDirective type**

In `apps/web/src/lib/types.ts`, add this interface near the `StockListCard` definition (before line 876):

```typescript
export interface ActionDirective {
  headline: string;
  action_text?: string;
  trigger_price?: number | null;
  invalidate_price?: number | null;
  sizing?: string | null;
  blocker?: string | null;
}
```

Then add a field to `StockListCard` (inside the interface, e.g. after `decision_rank_label` around line 971):

```typescript
  action_directive?: ActionDirective;
```

- [ ] **Step 2: Create the ActionCell component**

Create `apps/web/src/app/discovery/discovery-action-cell.tsx`:

```tsx
import { Badge } from "@/components/badge";
import type { StockListCard } from "@/lib/types";

const HEADLINE_TONE: Record<string, "positive" | "watch" | "risk" | "info" | "neutral"> = {
  可开仓: "positive",
  可加仓: "positive",
  等触发: "watch",
  只观察: "info",
  不可开仓: "risk",
};

function fmtPrice(value: number | null | undefined): string | null {
  if (value === null || value === undefined) return null;
  return Number(value).toFixed(2);
}

export function ActionCell({
  stock,
  valveOff = false,
}: {
  stock: StockListCard;
  valveOff?: boolean;
}) {
  const d = stock.action_directive;
  if (!d) {
    return <span className="text-[var(--text-tertiary)]">—</span>;
  }
  // When the offense valve is shut, every candidate collapses to '只观察'
  // regardless of its own gate, so the page stops pretending there is a
  // buyable gradient. The backend emits the valve-open directive; the
  // frontend overrides the headline here so the payload stays cache-stable.
  const headline = valveOff ? "只观察" : d.headline;
  const blocker = valveOff ? (d.blocker || "进攻阀门关闭，今日不开新仓") : d.blocker;
  const tone = HEADLINE_TONE[headline] ?? "neutral";
  const trigger = valveOff ? null : fmtPrice(d.trigger_price);
  const invalidate = valveOff ? null : fmtPrice(d.invalidate_price);
  return (
    <div className="flex flex-col gap-1">
      <Badge tone={tone}>{headline}</Badge>
      {trigger || invalidate ? (
        <div className="mono text-[11px] leading-4 text-[var(--text-secondary)]">
          {trigger ? <div>触发 {trigger}</div> : null}
          {invalidate ? <div className="text-[var(--text-tertiary)]">失效 {invalidate}</div> : null}
        </div>
      ) : null}
      {blocker ? (
        <div className="prism-clamp-2 text-[11px] leading-4 text-[var(--text-tertiary)]">
          {blocker}
        </div>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 3: Swap the first table column**

In `apps/web/src/app/discovery/discovery-observation-workbench.tsx`:

3a. Add the import near the other local imports at the top:
```tsx
import { ActionCell } from "./discovery-action-cell";
```

3b. Change the first column header (line 933):
```tsx
                  <th className="px-3 py-2 font-medium">今日动作</th>
```

3c. Change the first column body cell (lines 949-951) — replace the `<DecisionRankBlock stock={stock} />` cell with:
```tsx
                        <td className="px-3 py-3">
                          <ActionCell stock={stock} valveOff={valveStatus === "off"} />
                        </td>
```

Leave `DecisionRankBlock` imported and used in the expanded detail row if it appears there; it is only being demoted from the first-column slot, not deleted.

- [ ] **Step 4: Update the mobile card variant**

In the same workbench file, find the mobile card rendering (the non-`lg:block` branch, around line 1041-1082 where cards are rendered for small screens). Add an action summary row near the top of each mobile card, after the stock name:

```tsx
{stock.action_directive ? (
  <div className="mb-2 flex items-center gap-2">
    <ActionCell stock={stock} valveOff={valveStatus === "off"} />
  </div>
) : null}
```

- [ ] **Step 5: Verify the frontend builds**

Run: `cd apps/web && ./node_modules/.bin/next build && cd ../..`
Expected: build succeeds with no type errors.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/app/discovery/discovery-action-cell.tsx apps/web/src/lib/types.ts apps/web/src/app/discovery/discovery-observation-workbench.tsx
git commit -m "feat(discovery): ActionCell replaces misleading decision-rank first column

The first column now shows an aggregated today-action directive
(headline + trigger/invalidate prices + blocker) instead of the
in-theme decision_rank that misled users into thinking rank=1 meant
'buy this first'. Mobile card variant gets the same action summary.
Task B of discovery-ui redesign."
```

---

## Task D: Frontend exit-trajectory panel

**Files:**
- Modify: `apps/web/src/lib/types.ts` (add `ExitTrackingRecord`, extend opportunities view type)
- Modify: `apps/web/src/app/discovery/discovery-context-panels.tsx`

- [ ] **Step 1: Add the ExitTrackingRecord type and wire it**

In `apps/web/src/lib/types.ts`, add the interface (near the other discovery-related types):

```typescript
export interface ExitTrackingRecord {
  code: string;
  name?: string;
  exit_date?: string;
  outcome?: "true_exit" | "misjudged" | "inconclusive" | string | null;
  net_return?: number | null;
  status?: "open" | "settled" | string | null;
  theme?: string;
}
```

Then find the opportunities view response type (the interface returned by `useOpportunities`, likely `OpportunitiesView` or similar — search for `lifecycle_groups` in types.ts to find it). Add:

```typescript
  exit_tracking?: ExitTrackingRecord[];
```

- [ ] **Step 2: Add the exit-trajectory block to the continuity panel**

In `apps/web/src/app/discovery/discovery-context-panels.tsx`, find the continuity/lifecycle panel component. Add a new block that renders the `exit_tracking` array. Place it after the existing lifecycle groups rendering. The panel receives data via props — check how `lifecycle_groups` is passed in and mirror that for `exit_tracking`.

Add this rendering block:

```tsx
const OUTCOME_META: Record<string, { label: string; tone: "positive" | "watch" | "info" | "neutral"; symbol: string }> = {
  true_exit: { label: "真退出", tone: "positive", symbol: "✅" },
  misjudged: { label: "错杀", tone: "watch", symbol: "⚠️" },
  inconclusive: { label: "未定", tone: "neutral", symbol: "⏳" },
};

function ExitTrajectoryBlock({ records }: { records: ExitTrackingRecord[] }) {
  if (!records || records.length === 0) {
    return (
      <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[12px] text-[var(--text-tertiary)]">
        近期无退出记录
      </div>
    );
  }
  return (
    <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
      <div className="border-b border-[var(--border-subtle)] px-3 py-2 text-[11px] uppercase text-[var(--text-tertiary)]">
        近期退出表现（近 30 天）
      </div>
      <ul className="divide-y divide-[var(--border-subtle)]">
        {records.map((r) => {
          const meta = OUTCOME_META[r.outcome ?? ""] ?? { label: r.outcome ?? "—", tone: "neutral" as const, symbol: "" };
          const ret = typeof r.net_return === "number" ? r.net_return : null;
          return (
            <li key={`${r.code}-${r.exit_date}`} className="flex items-center justify-between px-3 py-2 text-[12px]">
              <div className="flex items-center gap-2">
                <span className="font-medium text-[var(--text-primary)]">{r.name || r.code}</span>
                <Badge tone={meta.tone}>
                  {meta.symbol} {meta.label}
                </Badge>
                {r.status === "open" ? <Badge tone="info">跟踪中</Badge> : null}
              </div>
              <div className="flex items-center gap-3">
                {ret !== null ? (
                  <span className={`mono ${ret >= 0 ? "text-[var(--tone-positive)]" : "text-[var(--tone-risk)]"}`}>
                    {ret >= 0 ? "+" : ""}{(ret * 100).toFixed(1)}%
                  </span>
                ) : null}
                <span className="mono text-[11px] text-[var(--text-tertiary)]">{r.exit_date}</span>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
```

Then render it in the panel body where the lifecycle content is rendered, passing the `exit_tracking` prop:

```tsx
<ExitTrajectoryBlock records={exit_tracking ?? []} />
```

Add the necessary imports at the top of the file (`Badge` from `@/components/badge`, `ExitTrackingRecord` from `@/lib/types`).

- [ ] **Step 3: Wire the exit_tracking prop through the panel**

Find where the continuity panel is rendered in `discovery-workspace.tsx` (the parent that passes lifecycle data to the context panel). Add `exit_tracking={data.exit_tracking}` to the panel's props, matching how `lifecycle_groups` is passed.

- [ ] **Step 4: Verify the frontend builds**

Run: `cd apps/web && ./node_modules/.bin/next build && cd ../..`
Expected: build succeeds.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/types.ts apps/web/src/app/discovery/discovery-context-panels.tsx apps/web/src/app/discovery/discovery-workspace.tsx
git commit -m "feat(discovery): lightweight exit-trajectory panel in continuity sidebar

Renders Wave-1 exit_return_tracker outcomes (true_exit / misjudged /
inconclusive) as colored badges with net_return percentage. Pure
labels+numbers, no candlestick. Empty state shows a friendly placeholder.
Task D of discovery-ui redesign."
```

---

## Task E: Valve-state coherence + real sort

**Files:**
- Modify: `apps/web/src/app/discovery/discovery-observation-workbench.tsx`

This task depends on Task B (ActionCell must exist). It changes visible behavior: when the valve is off, the fake-gradient funnel is hidden and candidates sort by real priority_score.

- [ ] **Step 1: Add an observation-mode branch replacing the funnel**

In `discovery-observation-workbench.tsx`, find the funnel render (line 1238-1246):

```tsx
      {groups.length ? (
        <FunnelHeader funnel={funnel} activeLayer={activeLayer} onSelect={setActiveLayer} />
      ) : null}

      {funnel[0].cards.length === 0 ? (
        <div className="mb-4 rounded-md border ...">
          今天没有可执行候选...
        </div>
      ) : null}
```

Replace this block with a valve-state conditional:

```tsx
      {valveStatus === "off" ? (
        <div className="mb-4 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-3 text-[12px] text-[var(--text-secondary)]">
          今日进攻阀门关闭，以下为观察池，按综合得分排序（非买入优先级）。
        </div>
      ) : groups.length ? (
        <FunnelHeader funnel={funnel} activeLayer={activeLayer} onSelect={setActiveLayer} />
      ) : null}
```

This hides the `FunnelHeader` (the "值得专注/等触发/只观察/丢弃" tabs) entirely when the valve is off, replacing it with an honest observation-mode banner.

- [ ] **Step 2: Sort candidates by priority_score when valve is off**

Find where `cards` / `funnel` are derived from the opportunities data (search for where the table's `cards.map` source comes from, or where `funnel` is built). Add a valve-aware sort. The cleanest place is where the cards array is assembled for the table — compute a sorted copy:

Add a helper near the top of the component (after the existing helpers):

```tsx
function sortByPriority(cards: StockListCard[]): StockListCard[] {
  return [...cards].sort((a, b) => {
    const sa = typeof a.priority_score === "number" ? a.priority_score
      : typeof a.best_score === "number" ? a.best_score
      : typeof a.priority_score === "string" ? parseFloat(a.priority_score) || 0
      : 0;
    const sb = typeof b.priority_score === "number" ? b.priority_score
      : typeof b.best_score === "number" ? b.best_score
      : typeof b.priority_score === "string" ? parseFloat(b.priority_score) || 0
      : 0;
    return sb - sa;
  });
}
```

Then, where the table's card list is derived, apply the sort when the valve is off:

```tsx
const tableCards = valveStatus === "off" ? sortByPriority(cards) : cards;
```

And change the table's `cards.map((stock) => ...)` to `tableCards.map((stock) => ...)`.

- [ ] **Step 3: Verify the frontend builds**

Run: `cd apps/web && ./node_modules/.bin/next build && cd ../..`
Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/app/discovery/discovery-observation-workbench.tsx
git commit -m "fix(discovery): valve-off hides fake funnel + sorts by priority_score

When the offense valve is shut, the '值得专注/等触发' funnel tabs (which
pretend a buyable gradient exists even when every gate says 'cannot
open') are replaced by an honest observation-mode banner, and candidates
sort by real priority_score instead of the misleading in-theme
decision_rank. Task E of discovery-ui redesign."
```

---

## Final Verification (after all tasks)

- [ ] **Step 1: Full backend test suite**

```bash
pytest -q --ignore=tests/test_opportunity_v2.py
```
Expected: all pass (the ignored test is the known environment-local failure).

- [ ] **Step 2: Frontend build**

```bash
cd apps/web && ./node_modules/.bin/next build && cd ../..
```
Expected: build succeeds.

- [ ] **Step 3: Privacy scrub**

```bash
python3 scripts/scrub-secrets.py
```
Expected: clean.

- [ ] **Step 4: Manual smoke test (if running locally)**

Start the stack and open `/discovery`:
- On a valve-off day: confirm the funnel tabs are gone, the observation banner shows, candidates are sorted by priority_score, and the action column shows "只观察".
- On a valve-open day: confirm the action column shows trigger/invalidate prices.
- Open the continuity sidebar: confirm the exit-trajectory panel renders outcomes with net_return, or the empty placeholder.

- [ ] **Step 5: Final commit / push**

```bash
git log --oneline -6
```
Confirm the 5 task commits are present. Push to the branch when ready.
