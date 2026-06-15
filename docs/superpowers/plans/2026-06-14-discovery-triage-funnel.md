# Discovery Triage Funnel Implementation Plan (P0 + P1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the discovery page into a Triage Funnel by moving the per-stock verdict (`action_state`, `gate.state`) into a backend module computed once from already-structured fields, and making the frontend a thin typed render layer that deletes the text-grep in `buyGateMeta()`.

**Architecture:** A new pure-Python module `packages/screener/triage.py` computes `gate.state`, `action_state`, and `gate.blocker` from existing signals (valve status, `can_trade_live`, `trust_level`, `risk_level`, V2 action, elimination). `build_opportunities_view` emits these as structured fields on each card plus a top-level `valve_status`. The frontend reads them, renders a funnel first screen with two lights (trust + valve), and the text-grepping `buyGateMeta()` is deleted.

**Tech Stack:** Python 3 + pytest (backend logic, TDD); Next.js + React + TypeScript (frontend, verified by `tsc`). Backend tests follow the existing `tests/test_opportunity_v2.py` pattern (`_candidate(**overrides)` helper).

**Spec:** `docs/superpowers/specs/2026-06-14-discovery-triage-funnel-design.md` (read §8.4, §8.5, §9 before starting).

**Scope:** Stage 1 only. Covers spec P0 (root fix) and P1 (decision-structure gaps). P0.5 (legacy screener migration) is a **separate exploration-first plan** — see the final section.

**Testing note:** The frontend has no test runner (only `tsc`). All verdict *logic* is therefore in the backend and pytest-tested. Frontend tasks are verified by `tsc --noEmit` plus a manual smoke check; they contain no logic to unit-test beyond types.

---

## File Structure

**Create:**
- `packages/screener/triage.py` — pure verdict computation (`compute_gate_state`, `compute_action_state`, `compute_gate_blocker`, `triage_fields_for_card`, valve constants).
- `tests/test_triage.py` — pytest coverage for triage.py.
- `apps/web/src/app/discovery/discovery-triage-utils.ts` — thin typed readers over the new backend fields + funnel-layer mapping.

**Modify:**
- `apps/control-panel/dashboard_data.py` — emit `valve_status` on the opportunities response; call `triage_fields_for_card` in the per-card builders.
- `apps/web/src/lib/types.ts` — add triage fields to `StockListCard` + `valve_status` to the opportunities response type.
- `apps/web/src/app/discovery/discovery-workspace.tsx` — pass `valve_status` + `trust` into the workbench; render the two lights.
- `apps/web/src/app/discovery/discovery-observation-workbench.tsx` — read structured triage fields; render the funnel first screen; **delete** `buyGateMeta()`, the `stockInstruction()` copy-patch, and the legacy branch of `taskCards()`.

---

## Phase A — Backend: TriageDecision computation (P0 core, TDD)

### Task A1: Create `triage.py` with `compute_gate_state` + tests

**Files:**
- Create: `packages/screener/triage.py`
- Test: `tests/test_triage.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_triage.py`:

```python
from screener.triage import (
    GATE_OPEN,
    GATE_CAPPED,
    GATE_CLOSED,
    compute_gate_state,
)


def test_gate_closed_when_cannot_trade_live():
    assert (
        compute_gate_state(
            valve_status="on",
            can_trade_live=False,
            trust_level="trusted",
            risk_level="info",
        )
        == GATE_CLOSED
    )


def test_gate_closed_when_valve_off():
    assert (
        compute_gate_state(
            valve_status="off",
            can_trade_live=True,
            trust_level="trusted",
            risk_level="info",
        )
        == GATE_CLOSED
    )


def test_gate_closed_when_risk_block():
    assert (
        compute_gate_state(
            valve_status="on",
            can_trade_live=True,
            trust_level="trusted",
            risk_level="block",
        )
        == GATE_CLOSED
    )


def test_gate_capped_when_valve_limited():
    assert (
        compute_gate_state(
            valve_status="limited",
            can_trade_live=True,
            trust_level="trusted",
            risk_level="info",
        )
        == GATE_CAPPED
    )


def test_gate_capped_when_trust_not_trusted():
    assert (
        compute_gate_state(
            valve_status="on",
            can_trade_live=True,
            trust_level="observe_only",
            risk_level="info",
        )
        == GATE_CAPPED
    )


def test_gate_open_happy_path():
    assert (
        compute_gate_state(
            valve_status="on",
            can_trade_live=True,
            trust_level="trusted",
            risk_level="info",
        )
        == GATE_OPEN
    )


def test_gate_open_with_risk_warn():
    # warn is a soft flag, not a block — gate stays open (action_state handles deprioritisation)
    assert (
        compute_gate_state(
            valve_status="on",
            can_trade_live=True,
            trust_level="trusted",
            risk_level="warn",
        )
        == GATE_OPEN
    )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_triage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'screener.triage'` (or `ImportError`).

- [ ] **Step 3: Write the minimal implementation**

Create `packages/screener/triage.py`:

```python
"""Triage verdict computation for the discovery page.

Computes the per-stock gate (can I buy?) and action_state (should I prioritise?)
from already-structured signals. Spec: docs/superpowers/specs/2026-06-14-discovery-triage-funnel-design.md §8.4, §8.5.

These functions are pure and tested in isolation; build_opportunities_view wires
them onto each candidate card.
"""

# Valve (portfolio) status, from execution_gate_of(market_regime).
VALVE_ON = "on"
VALVE_LIMITED = "limited"
VALVE_OFF = "off"

# gate.state — permission axis.
GATE_OPEN = "open"
GATE_CAPPED = "capped"
GATE_CLOSED = "closed"

# action_state — triage axis.
ACTION_FOCUS = "focus"
ACTION_ON_TRIGGER = "on_trigger"
ACTION_WATCH = "watch"
ACTION_DROP = "drop"

# risk_level values that affect the gate (RiskLevel enum on StockListCard).
_RISK_BLOCK = "block"
_RISK_DEGRADE = "degrade"


def compute_gate_state(*, valve_status, can_trade_live, trust_level, risk_level):
    """Permission axis: can I buy this stock at all / at full size? See spec §8.4."""
    if (not can_trade_live) or valve_status == VALVE_OFF or risk_level == _RISK_BLOCK:
        return GATE_CLOSED
    if valve_status == VALVE_LIMITED or trust_level != "trusted":
        return GATE_CAPPED
    return GATE_OPEN
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_triage.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add packages/screener/triage.py tests/test_triage.py
git commit -m "feat(screener): add triage.compute_gate_state with tests"
```

---

### Task A2: Add `compute_action_state` + tests

**Files:**
- Modify: `packages/screener/triage.py`
- Test: `tests/test_triage.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_triage.py`:

```python
from screener.triage import (
    ACTION_FOCUS,
    ACTION_ON_TRIGGER,
    ACTION_WATCH,
    ACTION_DROP,
    compute_action_state,
)


def test_action_drop_overrides_everything():
    assert (
        compute_action_state(
            v2_action="actionable",
            gate_state=GATE_OPEN,
            risk_level="info",
            eliminated=True,
        )
        == ACTION_DROP
    )


def test_action_focus_when_actionable_and_open():
    assert (
        compute_action_state(
            v2_action="actionable",
            gate_state=GATE_OPEN,
            risk_level="info",
            eliminated=False,
        )
        == ACTION_FOCUS
    )


def test_action_watch_when_actionable_but_gate_capped():
    # can't act at full size -> only watch
    assert (
        compute_action_state(
            v2_action="actionable",
            gate_state=GATE_CAPPED,
            risk_level="info",
            eliminated=False,
        )
        == ACTION_WATCH
    )


def test_action_on_trigger_when_trial_and_not_closed():
    assert (
        compute_action_state(
            v2_action="trial",
            gate_state=GATE_CAPPED,
            risk_level="info",
            eliminated=False,
        )
        == ACTION_ON_TRIGGER
    )


def test_action_watch_when_trial_but_gate_closed():
    assert (
        compute_action_state(
            v2_action="trial",
            gate_state=GATE_CLOSED,
            risk_level="info",
            eliminated=False,
        )
        == ACTION_WATCH
    )


def test_action_watch_when_degrade_even_if_actionable():
    # degrade (e.g. 审计意见异常) demotes to watch even when actionable + open.
    # Resolves spec §8.5 ambiguity in favour of "degrade deprioritises".
    assert (
        compute_action_state(
            v2_action="actionable",
            gate_state=GATE_OPEN,
            risk_level="degrade",
            eliminated=False,
        )
        == ACTION_WATCH
    )


def test_action_watch_for_shadow_review_observe():
    for action in ("shadow", "review", "observe", ""):
        assert (
            compute_action_state(
                v2_action=action,
                gate_state=GATE_OPEN,
                risk_level="info",
                eliminated=False,
            )
            == ACTION_WATCH
        )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_triage.py::test_action_focus_when_actionable_and_open -v`
Expected: FAIL with `ImportError: cannot import name 'compute_action_state'`.

- [ ] **Step 3: Write the minimal implementation**

Append to `packages/screener/triage.py`:

```python
def compute_action_state(*, v2_action, gate_state, risk_level, eliminated):
    """Triage axis: should I prioritise this stock? See spec §8.5.

    gate is the permission filter; action_state is the priority that survives it.
    A closed/capped gate degrades priority to watch (protocol §10.5).
    """
    if eliminated:
        return ACTION_DROP
    if risk_level == _RISK_DEGRADE:
        # degrade demotes to watch even when actionable (resolves spec ambiguity).
        return ACTION_WATCH
    if v2_action == "actionable" and gate_state == GATE_OPEN:
        return ACTION_FOCUS
    if v2_action == "trial" and gate_state != GATE_CLOSED:
        return ACTION_ON_TRIGGER
    return ACTION_WATCH
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_triage.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add packages/screener/triage.py tests/test_triage.py
git commit -m "feat(screener): add triage.compute_action_state with tests"
```

---

### Task A3: Add `compute_gate_blocker` and `triage_fields_for_card` + tests

`triage_fields_for_card` is the single entry point the card builders call. It returns the three structured fields the frontend reads (`triage_action_state`, `triage_gate_state`, `triage_gate_blocker`) plus a `triage_legacy` flag.

**Files:**
- Modify: `packages/screener/triage.py`
- Test: `tests/test_triage.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_triage.py`:

```python
from screener.triage import triage_fields_for_card


def _card(**overrides):
    base = {
        "suggested_action": "actionable",
        "risk_level": "info",
        "hard_gate_block_reason": "",
    }
    base.update(overrides)
    return base


def test_triage_fields_open_focus():
    out = triage_fields_for_card(
        _card(),
        valve_status="on",
        can_trade_live=True,
        trust_level="trusted",
        eliminated=False,
    )
    assert out == {
        "triage_action_state": "focus",
        "triage_gate_state": "open",
        "triage_gate_blocker": None,
        "triage_legacy": False,
    }


def test_triage_fields_closed_blocker_is_operator_language():
    out = triage_fields_for_card(
        _card(),
        valve_status="off",
        can_trade_live=True,
        trust_level="trusted",
        eliminated=False,
    )
    assert out["triage_gate_state"] == "closed"
    assert out["triage_gate_blocker"] == "进攻阀门关闭，今天不开新仓"


def test_triage_fields_legacy_flag_when_legacy():
    out = triage_fields_for_card(
        _card(suggested_action=""),  # no V2 action -> legacy-style
        valve_status="on",
        can_trade_live=True,
        trust_level="trusted",
        eliminated=False,
        legacy=True,
    )
    assert out["triage_legacy"] is True
    assert out["triage_action_state"] == "watch"


def test_triage_fields_eliminated_drops():
    out = triage_fields_for_card(
        _card(),
        valve_status="on",
        can_trade_live=True,
        trust_level="trusted",
        eliminated=True,
    )
    assert out["triage_action_state"] == "drop"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_triage.py::test_triage_fields_open_focus -v`
Expected: FAIL with `ImportError: cannot import name 'triage_fields_for_card'`.

- [ ] **Step 3: Write the minimal implementation**

Append to `packages/screener/triage.py`:

```python
def compute_gate_blocker(
    *,
    valve_status,
    can_trade_live,
    trust_level,
    risk_level,
    hard_gate_block_reason,
):
    """The FIRST single reason the gate is not open, in operator language. None if open."""
    if not can_trade_live:
        return "账户处于研究态，不能真钱执行"
    if valve_status == VALVE_OFF:
        return "进攻阀门关闭，今天不开新仓"
    if risk_level == _RISK_BLOCK:
        return "硬拦截"
    if valve_status == VALVE_LIMITED:
        return "进攻阀门半开，仓位受限"
    if trust_level != "trusted":
        return "数据未完全可信"
    if hard_gate_block_reason:
        return hard_gate_block_reason
    return None


def triage_fields_for_card(
    card,
    *,
    valve_status,
    can_trade_live,
    trust_level,
    eliminated=False,
    legacy=False,
):
    """Compute the structured triage fields for one candidate card.

    Callers: build_screening_candidate_card / build_confirmation_candidate_card in
    apps/control-panel/dashboard_data.py. Spread the returned dict onto the card.
    """
    risk_level = card.get("risk_level") or "info"
    v2_action = str(card.get("suggested_action") or "").strip()
    hard_gate_block_reason = card.get("hard_gate_block_reason") or ""

    gate_state = compute_gate_state(
        valve_status=valve_status,
        can_trade_live=can_trade_live,
        trust_level=trust_level,
        risk_level=risk_level,
    )
    action_state = compute_action_state(
        v2_action=v2_action,
        gate_state=gate_state,
        risk_level=risk_level,
        eliminated=eliminated,
    )
    blocker = (
        compute_gate_blocker(
            valve_status=valve_status,
            can_trade_live=can_trade_live,
            trust_level=trust_level,
            risk_level=risk_level,
            hard_gate_block_reason=hard_gate_block_reason,
        )
        if gate_state != GATE_OPEN
        else None
    )
    return {
        "triage_action_state": action_state,
        "triage_gate_state": gate_state,
        "triage_gate_blocker": blocker,
        "triage_legacy": bool(legacy),
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_triage.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add packages/screener/triage.py tests/test_triage.py
git commit -m "feat(screener): add triage.triage_fields_for_card entry point"
```

---

### Task A4: Emit `valve_status` on the opportunities response

The valve status (`on`/`limited`/`off`) is currently derived into a display `gate` object but the raw status enum is not sent to the frontend. Surface it.

**Files:**
- Modify: `apps/control-panel/dashboard_data.py` (function `build_opportunities_view`, ~line 8702–9000)

- [ ] **Step 1: Locate the gate construction in `build_opportunities_view`**

Run: `grep -n "execution_gate\|allow_new_positions\|\"gate\"\|position_cap" apps/control-panel/dashboard_data.py | sed -n '1,60p'`
Identify the dict inside `build_opportunities_view` that builds the `gate` object (`allow_new_positions`, `label`, `position_cap`, `summary`). Note its line range.

- [ ] **Step 2: Surface `status` from the execution gate**

In `build_opportunities_view`, the gate is built from the market regime's execution gate. Add a `valve_status` key sourced from that same execution gate's `status` field. Concretely, where the gate dict is assembled, add:

```python
# Inside build_opportunities_view, alongside the existing gate dict construction:
from screener.ai_screening import execution_gate_of  # add to imports at top of file if not present

_execution_gate = execution_gate_of(market_regime)  # market_regime is already in scope here
_valve_status = _execution_gate.get("status") or "off"
```

Then include `"valve_status": _valve_status` in the response dict returned by `build_opportunities_view` (next to `"trade_date"` and `"groups"`).

If `execution_gate_of` is already called earlier in this function and its result is available, reuse that result instead of calling again — confirm via the grep in Step 1.

- [ ] **Step 3: Add a regression test that the response carries `valve_status`**

Append to `apps/control-panel/tests/test_discovery_lifecycle_pipeline.py` (or `tests/test_opportunity_v2.py` if that is where response-shape tests live — confirm by reading the existing file's imports):

```python
def test_opportunities_response_includes_valve_status():
    from control_panel.dashboard_data import build_opportunities_view

    view = build_opportunities_view(
        # reuse the same fixtures/args the existing tests in this file pass;
        # copy the call signature from a neighbouring passing test.
    )
    assert view["valve_status"] in {"on", "limited", "off"}
```

If `build_opportunities_view` is hard to construct in isolation (many args), instead add a focused unit test on a small helper that extracts valve status, and verify the wiring by reading the response in an existing integration test. Prefer the direct test; fall back only if the function signature makes it impractical, and leave a `# TODO(test): cover valve_status end-to-end once build_opportunities_view fixtures stabilise` only as a last resort (this is the one sanctioned exception in this plan).

- [ ] **Step 4: Run the tests**

Run: `python -m pytest apps/control-panel/tests/test_discovery_lifecycle_pipeline.py -v` (adapt path to wherever Step 3's test landed).
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/control-panel/dashboard_data.py apps/control-panel/tests/test_discovery_lifecycle_pipeline.py
git commit -m "feat(control-panel): emit valve_status on opportunities response"
```

---

### Task A5: Wire `triage_fields_for_card` into the per-card builders

Each `StockListCard` emitted for the discovery page must carry the three triage fields. V2 candidates get the full computation; legacy candidates get gate from `risk_level` only + a `triage_legacy` flag (spec P0.5 defers full legacy migration).

**Files:**
- Modify: `apps/control-panel/dashboard_data.py` (`build_screening_candidate_card`, `build_confirmation_candidate_card`, and the group-assembly loop in `build_opportunities_view`)

- [ ] **Step 1: Identify the per-card builders and where elimination is known**

Run: `grep -n "def build_screening_candidate_card\|def build_confirmation_candidate_card\|\"eliminated\"\|group_key\|\"key\":" apps/control-panel/dashboard_data.py | head -40`

Note: (a) the two card-builder function signatures, (b) where cards are assigned to groups (the group `key` — `morning`/`watching`/`midday_new`/`upgrade`/`eliminated`), since `eliminated` is true only for the `eliminated` group.

- [ ] **Step 2: Add triage fields to each card in the group-assembly loop**

In `build_opportunities_view`, after cards are built and assigned to groups, iterate once and stamp triage fields. The valve_status, can_trade_live, and trust_level are available in this function's scope (valve_status from Task A4; trust/can_trade_live from the readiness payload already loaded here — confirm by grepping `trust_level` / `can_trade_live` in this function; if not present, thread them from the caller the same way `trade_date` is threaded).

Add near the end of `build_opportunities_view`, before returning:

```python
from screener.triage import triage_fields_for_card

_can_trade_live = bool(readiness_payload.get("can_trade_live", False)) if readiness_payload else False
_trust_level = (trust_payload.get("level") if trust_payload else None) or "observe_only"

for _group in groups:
    _eliminated = _group.get("key") == "eliminated"
    for _card in _group.get("cards", []):
        _legacy = not _card.get("suggested_action")
        _card.update(
            triage_fields_for_card(
                _card,
                valve_status=_valve_status,
                can_trade_live=_can_trade_live,
                trust_level=_trust_level,
                eliminated=_eliminated,
                legacy=_legacy,
            )
        )
```

Adjust the variable names (`readiness_payload`, `trust_payload`, `_valve_status`, `groups`) to match what is actually in scope — confirm each via grep before writing. The `_valve_status` from Task A4 is reused here.

- [ ] **Step 3: Verify the cards carry the fields**

Add to the test file used in Task A4:

```python
def test_opportunities_cards_carry_triage_fields():
    from control_panel.dashboard_data import build_opportunities_view

    view = build_opportunities_view(/* same args as the valve_status test */)
    all_cards = [c for g in view["groups"] for c in g.get("cards", [])]
    assert all_cards, "fixture should produce at least one card"
    for card in all_cards:
        assert card["triage_action_state"] in {"focus", "on_trigger", "watch", "drop"}
        assert card["triage_gate_state"] in {"open", "capped", "closed"}
        assert "triage_legacy" in card
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest apps/control-panel/tests/ tests/test_triage.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/control-panel/dashboard_data.py apps/control-panel/tests/test_discovery_lifecycle_pipeline.py
git commit -m "feat(control-panel): stamp triage fields on discovery candidate cards"
```

---

## Phase B — Frontend: funnel first screen + delete the grep (P0 frontend)

### Task B1: Add TypeScript types for the triage fields and `valve_status`

**Files:**
- Modify: `apps/web/src/lib/types.ts`

- [ ] **Step 1: Add the fields to `StockListCard`**

In `apps/web/src/lib/types.ts`, inside `interface StockListCard` (ends ~line 991), add before the closing brace:

```typescript
  triage_action_state?: "focus" | "on_trigger" | "watch" | "drop";
  triage_gate_state?: "open" | "capped" | "closed";
  triage_gate_blocker?: string | null;
  triage_legacy?: boolean;
```

- [ ] **Step 2: Add `valve_status` to the opportunities response type**

Find the opportunities response type (the type returned by `useOpportunities` — search `grep -n "groups.*CardGroup\|trade_date.*string" apps/web/src/lib/types.ts`). Add `valve_status?: "on" | "limited" | "off";` next to `trade_date`.

- [ ] **Step 3: Verify it type-checks**

Run: `npx tsc --noEmit -p apps/web/tsconfig.json`
Expected: PASS (no new errors).

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/lib/types.ts
git commit -m "feat(web): add triage + valve_status types"
```

---

### Task B2: Create `discovery-triage-utils.ts` (thin typed readers)

Pure functions that read the backend fields and map `action_state` to a funnel layer. No text-grep, no re-derivation beyond enum mapping.

**Files:**
- Create: `apps/web/src/app/discovery/discovery-triage-utils.ts`

- [ ] **Step 1: Write the module**

Create `apps/web/src/app/discovery/discovery-triage-utils.ts`:

```typescript
import type { StockListCard } from "@/lib/types";

export type TriageActionState = "focus" | "on_trigger" | "watch" | "drop";
export type TriageGateState = "open" | "capped" | "closed";
export type ValveStatus = "on" | "limited" | "off";

// Funnel layers — the primary grouping axis (spec §6).
export type FunnelLayer = "focus" | "on_trigger" | "watch" | "drop";

export const FUNNEL_LAYER_LABELS: Record<FunnelLayer, string> = {
  focus: "值得专注",
  on_trigger: "等触发",
  watch: "只观察",
  drop: "丢弃",
};

export function triageActionState(stock: StockListCard): TriageActionState {
  return stock.triage_action_state ?? "watch";
}

export function triageGateState(stock: StockListCard): TriageGateState {
  return stock.triage_gate_state ?? "open";
}

export function triageGateBlocker(stock: StockListCard): string | null {
  return stock.triage_gate_blocker ?? null;
}

export function triageLegacy(stock: StockListCard): boolean {
  return Boolean(stock.triage_legacy);
}

export function funnelLayer(stock: StockListCard): FunnelLayer {
  return triageActionState(stock);
}

// Valve light copy (spec §7). Status comes straight from the backend payload.
export function valveLabel(status: ValveStatus | undefined): string {
  if (status === "on") return "开";
  if (status === "limited") return "半开";
  return "关闭";
}

export function valveTone(status: ValveStatus | undefined): string {
  if (status === "on") return "positive";
  if (status === "limited") return "watch";
  return "risk";
}
```

- [ ] **Step 2: Verify it type-checks**

Run: `npx tsc --noEmit -p apps/web/tsconfig.json`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/app/discovery/discovery-triage-utils.ts
git commit -m "feat(web): add discovery triage readers"
```

---

### Task B3: Render the two lights (trust + valve) above the workbench

`trust` is already in `DiscoveryWorkspace` scope (it renders `<DeferredTrustBanner trust={trust}>` at line 373). `valve_status` arrives on the opportunities response (Task A4). Surface both as a compact light strip above the funnel.

**Files:**
- Modify: `apps/web/src/app/discovery/discovery-workspace.tsx`
- Modify: `apps/web/src/app/discovery/discovery-observation-workbench.tsx`

- [ ] **Step 1: Pass `valveStatus` into the workbench**

In `discovery-workspace.tsx`, the `DiscoveryObservationWorkbench` is rendered around line 411. Add a `valveStatus={data?.valve_status}` prop to that call (and add it to the component's props type in the workbench file).

- [ ] **Step 2: Render the valve light strip at the top of the workbench**

In `discovery-observation-workbench.tsx`, add `valveStatus?: ValveStatus` to `DiscoveryObservationWorkbenchProps`. At the top of the component's returned JSX (before the metric cards section), add:

```tsx
<section className="mb-5 flex flex-wrap items-center gap-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-3">
  <div className="flex items-center gap-2">
    <span className="text-[11px] uppercase text-[var(--text-tertiary)]">进攻阀门</span>
    <Badge tone={valveTone(valveStatus)}>{valveLabel(valveStatus)}</Badge>
  </div>
  <div className="text-[12px] leading-5 text-[var(--text-secondary)]">
    {valveStatus === "on"
      ? "阀门开启，可按仓位上限开新仓"
      : valveStatus === "limited"
        ? "阀门半开，仅小仓位试错"
        : "阀门关闭，今天不开新仓，整页进入观察模式"}
  </div>
</section>
```

Import `Badge` (already imported) and `valveLabel`, `valveTone`, `ValveStatus` from `./discovery-triage-utils`.

The trust light is already rendered by `<DeferredTrustBanner trust={trust}>` in the workspace — no new work needed; the two lights now sit together (trust banner above, valve strip at the workbench top).

- [ ] **Step 3: Verify it type-checks and renders**

Run: `npx tsc --noEmit -p apps/web/tsconfig.json`
Expected: PASS.

Manual smoke: load `/discovery`; confirm the valve strip shows the correct state for today's `valve_status` (e.g. 关闭 for a risk-off day).

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/app/discovery/discovery-workspace.tsx apps/web/src/app/discovery/discovery-observation-workbench.tsx
git commit -m "feat(web): render trust + valve lights on discovery first screen"
```

---

### Task B4: Render the funnel first screen (focus layer expanded, others collapsed)

Replace the equal-weight `PipelineFlow` of five groups with a funnel view: candidates bucketed by `triage_action_state`, the `focus` layer expanded, `watch`/`drop` collapsed. This is the structural inversion — the narrow end of the funnel on top.

**Files:**
- Modify: `apps/web/src/app/discovery/discovery-observation-workbench.tsx`

- [ ] **Step 1: Build a funnel-bucketing helper**

In `discovery-triage-utils.ts`, add:

```typescript
import type { CardGroup } from "@/lib/types";

export interface FunnelBucket {
  layer: FunnelLayer;
  cards: StockListCard[];
}

export function bucketByFunnel(groups: CardGroup<StockListCard>[]): FunnelBucket[] {
  const order: FunnelLayer[] = ["focus", "on_trigger", "watch", "drop"];
  const buckets: Record<FunnelLayer, StockListCard[]> = {
    focus: [],
    on_trigger: [],
    watch: [],
    drop: [],
  };
  for (const group of groups) {
    for (const card of group.cards ?? []) {
      buckets[funnelLayer(card)].push(card);
    }
  }
  return order.map((layer) => ({ layer, cards: buckets[layer] }));
}
```

- [ ] **Step 2: Replace `PipelineFlow` usage with a funnel summary header**

In `DiscoveryObservationWorkbench`, compute `const funnel = useMemo(() => bucketByFunnel(groups), [groups]);`. Render a compact funnel header showing the four counts, with the `focus` bucket expanded into the existing `ObservationWorkbench` table and the other three as collapsible count chips.

Concretely, replace the `<PipelineFlow .../>` block with:

```tsx
{groups.length ? <FunnelHeader funnel={funnel} activeLayer={activeLayer} onSelect={onSelectFunnelLayer} /> : null}
```

Implement `FunnelHeader` in the same file: it shows `值得专注 N · 等触发 N · 只观察 N · 丢弃 N`, clicking a layer selects it (default `focus` if non-empty, else `watch`). The selected layer feeds `ObservationWorkbench` instead of the old `activeGroup`.

When the selected layer is empty (e.g. focus empty on a closed-valve day — spec §6 closed-valve behaviour), show an observation-mode notice: "今天没有可执行候选，整页进入观察模式" + the valve blocker.

- [ ] **Step 3: Feed the selected funnel layer's cards into `ObservationWorkbench`**

`ObservationWorkbench` currently takes a `CardGroup`. Wrap the selected funnel bucket as a synthetic group: `{ key: layer, title: FUNNEL_LAYER_LABELS[layer], cards: bucket.cards }`. This reuses the existing table rendering with no table changes.

- [ ] **Step 4: Verify it type-checks and renders**

Run: `npx tsc --noEmit -p apps/web/tsconfig.json`
Expected: PASS.

Manual smoke: on a closed-valve day, the focus layer is empty and the observation-mode notice shows; on an open-valve day with actionable candidates, focus is populated and on top.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/app/discovery/discovery-triage-utils.ts apps/web/src/app/discovery/discovery-observation-workbench.tsx
git commit -m "feat(web): render discovery as action-state funnel"
```

---

### Task B5: Read structured triage fields in the card; delete `buyGateMeta` and the text-grep

Now that the verdict is a backend field, the workbench reads `triage_gate_state` / `triage_gate_blocker` directly and the entire `buyGateMeta()` text-grep (the root defect) is deleted.

**Files:**
- Modify: `apps/web/src/app/discovery/discovery-observation-workbench.tsx`

- [ ] **Step 1: Replace `buyGateMeta` with a structured reader**

Delete the `buyGateMeta` function (lines ~227–445) and the `BuyGateCell`'s reliance on it. Replace with a small structured mapper:

```tsx
function buyGateFromTriage(stock: StockListCard) {
  const state = triageGateState(stock);
  const legacy = triageLegacy(stock);
  const blocker = triageGateBlocker(stock);
  const label =
    state === "closed"
      ? blocker
        ? "买入未放行"
        : "不可买入"
      : state === "capped"
        ? "仓位受限"
        : "可执行待复核";
  const tone = state === "open" ? "positive" : state === "capped" ? "watch" : "risk";
  const detail = blocker ?? (legacy ? "legacy 候选，闸门由 risk_level 推断" : "结构、触发和失效位已相对清楚，仍需人工复核");
  return { label, tone, detail };
}
```

Update `BuyGateCell` to call `buyGateFromTriage(stock)` instead of `buyGateMeta(stock, group)`.

- [ ] **Step 2: Simplify `groupDecisionMeta`, `taskCards`, `stockInstruction` to read triage fields**

- `groupDecisionMeta`: count cards by `triageActionState` (focus / on_trigger / watch / drop) instead of inferring from gates. Delete the V2-vs-legacy branch — both now carry `triage_action_state`.
- `taskCards`: replace the two branches (V2 vs legacy) with one branch that counts `triage_action_state`. Produce the four cards: 可执行待复核 (focus), 等触发 (on_trigger), 只观察 (watch), 应剔除 (drop).
- `stockInstruction`: delete the `clarifyUpgradeCopy` copy-patch; read `triage_gate_blocker` / `missing_confirmation` directly.

These are deletions of grep/branch logic, replaced by enum reads. Keep the rendered copy in operator language (jargon firewall).

- [ ] **Step 3: Remove now-unused helpers and imports**

Delete `clarifyUpgradeCopy`, the keyword arrays in `buyGateMeta` (`trialAction`, `waitingForGate`, etc.), and any imports only used by the deleted code. Run `npx tsc --noEmit -p apps/web/tsconfig.json` to catch dangling references.

- [ ] **Step 4: Verify it type-checks and the grep is gone**

Run: `npx tsc --noEmit -p apps/web/tsconfig.json`
Expected: PASS.

Run: `grep -n "试错\|0.3-0.5\|先不开新仓\|clarifyUpgradeCopy\|buyGateMeta" apps/web/src/app/discovery/discovery-observation-workbench.tsx`
Expected: no matches (the text-grep keywords and the function are gone).

Manual smoke: each candidate's 买入闸门 cell shows the structured label + the single blocker reason; the four metric cards reflect the funnel counts.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/app/discovery/discovery-observation-workbench.tsx
git commit -m "refactor(web): read structured triage fields, delete buyGateMeta text-grep"
```

---

## Phase C — P1: decision-structure gaps

### Task C1: Theme-internal relative strength (`rs.rank_in_theme`, `rs.theme_in_play`)

Backend computes a within-theme rank from existing data; frontend shows it on focus cards. (vs-index RS stays Stage 2.)

**Files:**
- Modify: `packages/screener/triage.py` (add `rank_in_theme` helper)
- Modify: `apps/control-panel/dashboard_data.py` (stamp `triage_rank_in_theme`, `triage_theme_in_play`)
- Modify: `apps/web/src/lib/types.ts`, `apps/web/src/app/discovery/discovery-triage-utils.ts`, `apps/web/src/app/discovery/discovery-observation-workbench.tsx`

- [ ] **Step 1: Write the failing test for within-theme ranking**

Append to `tests/test_triage.py`:

```python
from screener.triage import assign_theme_ranks


def test_assign_theme_ranks_orders_by_score_within_theme():
    cards = [
        {"code": "A", "theme": "AI", "priority_score": 50},
        {"code": "B", "theme": "AI", "priority_score": 80},
        {"code": "C", "theme": "AI", "priority_score": 65},
        {"code": "D", "theme": "有色", "priority_score": 90},
    ]
    ranked = assign_theme_ranks(cards)
    by_code = {c["code"]: c["triage_rank_in_theme"] for c in ranked}
    assert by_code == {"A": 3, "B": 1, "C": 2, "D": 1}  # rank within each theme
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_triage.py::test_assign_theme_ranks_orders_by_score_within_theme -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Implement `assign_theme_ranks`**

Append to `packages/screener/triage.py`:

```python
def assign_theme_ranks(cards):
    """Stamp triage_rank_in_theme (1 = strongest) within each theme, by priority_score.

    Uses existing priority_score only (vs-index RS is Stage 2). Mutates and returns cards.
    """
    by_theme = {}
    for card in cards:
        by_theme.setdefault(card.get("theme") or "—", []).append(card)
    for theme, group in by_theme.items():
        group.sort(key=lambda c: -(float(c.get("priority_score") or 0)))
        for idx, card in enumerate(group, start=1):
            card["triage_rank_in_theme"] = idx
    return cards
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_triage.py -v`
Expected: PASS.

- [ ] **Step 5: Wire it into `build_opportunities_view` and the frontend**

- In `build_opportunities_view`, after the triage-fields loop (Task A5), call `assign_theme_ranks(all_cards)` once over the full card list. Stamp `triage_theme_in_play = bool(card.get("theme_phase_value") not in (None, "", "exited"))` per card.
- Add `triage_rank_in_theme?: number` and `triage_theme_in_play?: boolean` to `StockListCard` in types.ts.
- In the workbench focus-card row, show a badge: `主线RS #{rank}` when `triage_theme_in_play`, else `主线走弱`.

- [ ] **Step 6: Verify + commit**

Run: `python -m pytest tests/test_triage.py -v && npx tsc --noEmit -p apps/web/tsconfig.json`
Expected: PASS.

```bash
git add packages/screener/triage.py tests/test_triage.py apps/control-panel/dashboard_data.py apps/web/src/lib/types.ts apps/web/src/app/discovery/
git commit -m "feat: theme-internal relative strength on focus cards (P1)"
```

---

### Task C2: Exit prompt — yesterday's trial review

Infrastructure confirmed: `candidate_lifecycle.find_previous_snapshot` + `compute_lifecycle` support cross-day comparison (spec §11 P1 #7).

**Files:**
- Modify: `apps/control-panel/dashboard_data.py` (emit `yesterday_trial_review: [{code, name, status}]`)
- Modify: `apps/web/src/lib/types.ts`, `apps/web/src/app/discovery/discovery-observation-workbench.tsx`

- [ ] **Step 1: Add a backend helper that lists yesterday's trial-grade candidates and their today-status**

In `dashboard_data.py`, add a function that, given today's lifecycle and the previous snapshot, returns candidates that were `trial` yesterday with their current `triage_action_state`:

```python
def build_yesterday_trial_review(today_cards_by_code, previous_snapshot):
    """Candidates that were trial-grade yesterday: are they still alive today?"""
    if not previous_snapshot:
        return []
    review = []
    for code, prev in previous_snapshot.items():
        if str(prev.get("suggested_action") or "") != "trial":
            continue
        today = today_cards_by_code.get(code)
        review.append({
            "code": code,
            "name": (today or prev).get("name", code),
            "yesterday_action": "trial",
            "today_action_state": today["triage_action_state"] if today else "drop",
            "still_listed": today is not None,
        })
    return review
```

- [ ] **Step 2: Wire it into `build_opportunities_view` and emit on the response**

Call `build_yesterday_trial_review` with the previous snapshot (already loaded by the lifecycle pipeline — confirm via `grep -n "find_previous_snapshot\|previous_snapshot" apps/control-panel/dashboard_data.py`). Add `"yesterday_trial_review": [...]` to the response.

- [ ] **Step 3: Render the exit-prompt line on the first screen**

In types.ts, add `yesterday_trial_review?: Array<{ code: string; name: string; yesterday_action: string; today_action_state: string; still_listed: boolean }>`. In the workbench, render a one-line strip above the funnel when the list is non-empty:

```tsx
{yesterdayTrialReview?.length ? (
  <div className="mb-4 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-2 text-[12px] text-[var(--text-secondary)]">
    昨日试错待复核：{yesterdayTrialReview.map(t => `${t.name}${t.still_listed ? `（今日 ${t.today_action_state}）` : "（今日已退出）"}`).join("、")}
  </div>
) : null}
```

- [ ] **Step 4: Verify + commit**

Run: `python -m pytest apps/control-panel/tests/ -v && npx tsc --noEmit -p apps/web/tsconfig.json`
Expected: PASS.

```bash
git add apps/control-panel/dashboard_data.py apps/web/src/lib/types.ts apps/web/src/app/discovery/discovery-observation-workbench.tsx
git commit -m "feat: yesterday trial-review exit prompt on discovery (P1)"
```

---

### Task C3: Same-theme concentration hint

Derivable purely on the frontend from the funnel buckets — no backend change. When >3 candidates share a theme, show a concentration warning.

**Files:**
- Modify: `apps/web/src/app/discovery/discovery-observation-workbench.tsx`

- [ ] **Step 1: Add the concentration check + render**

In the workbench, after computing `funnel`, count themes across the focus + on_trigger buckets:

```tsx
function concentrationWarnings(cards: StockListCard[]): string[] {
  const counts: Record<string, number> = {};
  for (const c of cards) {
    const t = c.theme || "—";
    counts[t] = (counts[t] || 0) + 1;
  }
  return Object.entries(counts)
    .filter(([, n]) => n > 3)
    .map(([theme, n]) => `${theme} 同主题 ${n} 只，隐含同一宏观下注`);
}

const active = useMemo(
  () => funnel.filter(f => f.layer === "focus" || f.layer === "on_trigger").flatMap(f => f.cards),
  [funnel],
);
const warnings = useMemo(() => concentrationWarnings(active), [active]);
```

Render above the funnel when non-empty:

```tsx
{warnings.length ? (
  <div className="mb-4 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-2 text-[12px] text-[var(--text-secondary)]">
    {warnings.join("；")}
  </div>
) : null}
```

- [ ] **Step 2: Verify + commit**

Run: `npx tsc --noEmit -p apps/web/tsconfig.json`
Expected: PASS. Manual smoke: with >3 same-theme focus candidates, the warning shows.

```bash
git add apps/web/src/app/discovery/discovery-observation-workbench.tsx
git commit -m "feat(web): same-theme concentration hint on discovery (P1)"
```

---

## P0.5 — Legacy screener migration (separate exploration-first plan)

**Not included as tasks in this plan.** Per spec §11 P0.5, the legacy (non-V2) candidate path has no structured gate fields; migrating it is a screener-package change of unknown size and is explicitly a **separate card**. Until that plan lands, legacy candidates render with `triage_legacy: true`, `triage_gate_state` derived from `risk_level` only, and `triage_action_state: watch` (handled by Task A5's `legacy=True` branch).

**The P0.5 plan must begin with an exploration task** (it cannot be planned in no-placeholder detail before the legacy path is mapped):

1. Map the legacy candidate path: where do non-V2 `StockListCard`s originate? Run `grep -rn "build_screening_candidate_card\|suggested_action" apps/control-panel/dashboard_data.py` and trace which sources emit cards without `opportunity_v2` / `suggested_action`.
2. For each legacy source, determine what signals exist that could populate `hard_gate_blocks_action` / `hard_gate_max_action` (likely only `risk_level` + `status`).
3. Decide per source: emit a structured gate from those signals, or mark the source as permanently `triage_legacy`.
4. Only then author the migration tasks (mirroring Task A5's wiring), each with tests.

Author the P0.5 plan after P0 + P1 land and the legacy path is mapped.

---

## Self-Review

**1. Spec coverage:**
- §3 root cause (workbench ignores structured fields + greps) → Task B5 deletes the grep; Task A5 emits the structured fields the workbench now reads. ✓
- §5 TriageDecision object → Task A1–A3 implement `triage_fields_for_card` emitting `triage_action_state` / `triage_gate_state` / `triage_gate_blocker` / `triage_legacy`. ✓
- §6 funnel (closed-valve empty focus) → Task B4 renders the funnel + observation-mode notice. ✓
- §7 two lights (trust + valve) → Task B3. ✓
- §8.4 gate.state → Task A1. ✓
- §8.5 action_state (incl. degrade→watch resolution) → Task A2. ✓
- §9 display field map → Task B5 reads structured fields; legacy fields demoted to detail layer (unchanged). ✓
- §11 P0 #1–4 → Tasks A4, A5, B3, B4, B5. ✓
- §11 P1 #6–8 → Tasks C1, C2, C3. ✓
- §11 P0.5 → separate plan (documented above). ✓
- Definition of Done (P0): `buyGateMeta` deleted (B5), cards read structured source (B5), two lights + funnel (B3/B4), jargon firewall (operator-language copy preserved throughout), closed-valve observation mode (B4). ✓

**2. Placeholder scan:** One sanctioned exception — Task A4 Step 3 allows a `TODO(test)` fallback only if `build_opportunities_view` cannot be constructed in a test; every other step contains real code or an exact command with expected output.

**3. Type consistency:** `triage_action_state` / `triage_gate_state` enums are identical across Python (`triage.py`), TypeScript (`StockListCard`, `discovery-triage-utils.ts`), and the tests. `FunnelLayer` maps 1:1 to `TriageActionState`. `valve_status` `{on,limited,off}` matches `execution_gate_of`'s `status`. `triage_rank_in_theme`, `triage_theme_in_play`, `yesterday_trial_review` are consistent across backend emit and frontend types.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-14-discovery-triage-funnel.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
