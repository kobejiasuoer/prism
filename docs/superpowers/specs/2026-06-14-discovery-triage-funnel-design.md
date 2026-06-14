# Discovery Triage Funnel Design

Date: 2026-06-14
Stage: Stage 1 — Data Governance (currently active per `docs/prism-working-anchor.md`)
Extends: `docs/superpowers/specs/2026-04-22-prism-decision-protocol-design.md`

## 1. Document Purpose

This document defines the redesign of Prism's Discovery / Observation page (`apps/web/src/app/discovery/discovery-observation-workbench.tsx`) as a **Triage Funnel**: turn each day's ~10–13 raw screening candidates into "the few worth your attention" in under two minutes.

Its job is to turn the agreed direction into a fixed operating contract:

- the page must read the canonical decision object, not re-derive a verdict from prose
- the per-stock verdict must be a first-class structured field, computed once upstream
- the page must separate data trust, portfolio valve, and per-stock gate — these are three different questions
- the first screen must answer "can I act today, and on what" before anything else

This document sits between the stage-one decision protocol and implementation.

## 2. Stage Boundary (Read First)

Prism is in **Stage 1 — Data Governance**. Only one stage is active at a time (`docs/prism-working-anchor.md`). This spec is scoped accordingly.

**In scope (Stage 1):** decision-contract consistency work — making the page consume a single canonical per-stock decision object instead of reconstructing it from scattered text fields. This is exactly decision-protocol §16 ("replace page-specific stock conclusion assembly with canonical decision assembly") and is Stage-1 work.

**Out of scope (deferred to Stage 2 / 3):**
- New formal data sources — dragon-tiger list (龙虎榜), block trades / large orders (大单), limit-up seal strength, lock-up expiry (解禁), earnings windows. These belong to **Stage 2 (formal daily sources)** and **Stage 3 (execution reality)**. They must not be added during Stage 1 even though the strategy would benefit.
- Relative strength versus a benchmark index (needs benchmark daily series = Stage 2).
- Forward-return backfill for strategy validation T+1/T+3/T+5/T+10 (needs formal daily price series and touches `data/quant/` formal research products = Stage 2).
- Rule-compliance tracking ("did you actually take the trade") (needs execution reality = Stage 3).

These are listed again in §10 with stage ownership so they stay visible but are not worked now.

## 3. Problem Statement (Root Cause)

The page feels noisy and unsatisfying. The root cause is **not layout**. It is that the per-stock verdict does not exist as a first-class object on this page — it is reverse-engineered from prose at render time, in two parallel dialects.

Evidence in current code:

- `buyGateMeta()` (discovery-observation-workbench.tsx) joins ~15 text fields (`status`, `action`, `action_intent`, `position_guidance`, `observation_instruction`, `detail`, `foot`, `risk`, `upgrade_condition`, `invalid_condition`, ...) into one string and greps it for keywords (`试错`, `轻仓`, `0.3-0.5`, `只观察`, `先不开新仓`, ...) to infer a buy-gate label. The verdict is not stored; it is guessed.
- Two parallel truth systems: the `hasV2(stock)` path reads structured `v2Action` / `v2HardReason`; the legacy path reads and pattern-matches prose. `taskCards()`, `stockInstruction()` both branch on this.
- `stockInstruction()` patches copy at render (`升级` → `确认`, `观察升级` → `还差`).
- The first screen renders five lifecycle groups (早盘进入 / 继续观察 / 午盘新增 / 结构验证 / 已淘汰) at equal weight, mixing a time axis (早盘/午盘) with an action axis (进入/观察/淘汰).

**Refinement (verified against code):** the V2 path already carries structured gate fields on `StockListCard` — `hard_gate_blocks_action` (boolean), `hard_gate_max_action`, `hard_gate_block_reason`, `hard_gate_reasons[]` — and the screening pipeline already produces a structured valve `execution_gate.status ∈ {on, limited, off}` (`ai_screening.execution_gate_of`). The root defect is narrower than "the verdict does not exist": the workbench **ignores** these structured fields and re-derives a verdict from prose via `buyGateMeta()`. The legacy (non-V2) path genuinely lacks structured gate fields, which is why the prose-grep exists for it. So P0 is largely "read what already exists" for V2; extending structure to legacy is sized separately (§11 P0.5).

This is the "surface consistency but model inconsistency" failure the decision protocol §2 names as the top danger. No column reshuffle fixes it. The fix is upstream.

## 4. Design Principle

One principle: **make "can I act today, and on what" readable in two seconds; demote everything else.**

Concretely:

1. The per-stock verdict becomes a structured object computed once upstream. The page reads it; it never re-derives it from text.
2. The first screen shows the **narrow end of a funnel** — the few candidates that passed hard filter and theme strength — not all groups at equal weight.
3. The action axis becomes the primary grouping; the time / source / theme axes become tags on each card.
4. Data trust, portfolio valve, and per-stock gate are three separate signals, composed but never merged.

## 5. The Canonical TriageDecision Object

Every candidate surfaced on this page must be backed by one structured object. This extends the stage-one canonical decision object (protocol §6) with fields shaped for **triage**, not single-stock detail.

Contract (Stage-1 fields only; new data sources are not introduced):

```
TriageDecision {
  code, name, theme

  # 1. Action verdict — enum, single source, computed upstream, never re-derived from text.
  #    Aligns to the protocol's four action tiers.
  action_state: focus | on_trigger | watch | drop

  # 2. Per-stock gate — enum + single blocker, derived from EXISTING Stage-1 signals only.
  #    See §8 for the derivation. Does NOT consume Stage-2/3 data.
  gate: { state: closed | capped | open,
          blocker: <one operator-language reason> | null }

  # 3. Thesis — one sentence, pre-registered at entry (gives Review a control group).
  thesis: string

  # 4. What is still missing to upgrade — structured enum list (replaces three prose fields).
  needs: [ price_trigger, volume_confirm, capital_inflow,
           midday_confirm, theme_still_leading ]

  # 5. The two prices that matter.
  trigger_price, invalidation_price

  # 6. Theme-internal ranking from existing batch data (NOT vs benchmark index — that is Stage 2).
  rs: { rank_in_theme: int,         # position within today's theme cohort by existing score
        theme_in_play: bool }        # is the theme still active (existing flag)

  # 7. Lifecycle / source — demoted to tags, no longer a grouping axis.
  lifecycle: new | continuing | upgraded | downgraded | reentered
  source: morning | midday

  updated_at, freshness
}
```

Discipline:

- `action_state` and `gate` are **enums computed once upstream**. The whole system reads them. `buyGateMeta()` text-grepping is deleted. The `hasV2` vs legacy split collapses: both paths produce the same `TriageDecision`; the legacy path is migrated, not maintained.
- `rs.vs_csi300` (relative strength versus the index) is deliberately **absent** — it needs a benchmark daily series, which is Stage 2. The object leaves a place for it; Stage 1 fills only `rank_in_theme` and `theme_in_play` from existing data.

## 6. Information Architecture: The Triage Funnel

Replace five equal-weight lifecycle groups with one action-axis funnel. The time / source / theme axes become tags.

```
全量原始池 (N)        today's screening batch
     │  per-stock gate (hard filter, Stage-1 signals)
     ▼
通过硬过滤
     │  theme strength + theme-internal RS (existing data)
     ▼
值得专注 (2–4)        ◀── first screen shows only this layer
     │  trigger / acceptance confirmation
     ▼
等触发 (1–2)          price alerts; promoted when trigger hits
  ─────────────
只观察 (…)            collapsed
丢弃 (…)              collapsed; kept as review control group
```

**Closed-valve behaviour:** when `execution_gate.status == off` (or `can_trade_live == false`), the 值得专注 layer is empty **by design** — no candidate can be `focus` or `on_trigger` (§8.5 degrades them to `watch`). The page enters observation mode: header states "今天不开新仓" + the single blocker reason, and the first screen shows only 等触发 / 只观察. This matches observed reality (valve closed ~7 of 9 days).

Mapping to the protocol's action tiers:

| Funnel layer | `action_state` | Protocol action tier |
|---|---|---|
| 值得专注 | `focus` | 立即执行 |
| 等触发 | `on_trigger` | 等触发 |
| 只观察 | `watch` | 仅观察 |
| 丢弃 | `drop` | 明确回避 |

The five-tier V2 ladder (`actionable / trial / shadow / review / observe`) collapses to four: `actionable` → `focus`, `trial` → `on_trigger`, `shadow` / `review` / `observe` → `watch`. `drop` is **not** derived from the V2 action rank; it is set by the elimination signal (a candidate whose lifecycle group is `eliminated` / `downgraded` / `exited`) and overrides `action_state` regardless of action rank. One vocabulary across the system.

Lifecycle (新进 / 延续 / 升级 / 降级 / 退出) and source (早盘 / 午盘) survive as **card tags**, not groups — preserving the memory value without competing for the primary axis.

## 7. First-Screen Elements

The first screen shows five things. Two of them are separate lights (see §8 for why they must not merge).

1. **Two separate lights at the top:**
   - **数据可信度 (data trust)** — `readiness.trust_level` consumed from `TrustBanner`, three states only: `trusted` / `observe_only` / `unreliable`. Answers "is the data trustworthy?" The page imports `TrustBanner`; it does not re-derive verdict text.
   - **进攻阀门 (portfolio valve)** — `execution_gate.status` ∈ {`on` / `limited` / `off`} → 开 / 半开 / 关闭, consumed from the screening pipeline (`ai_screening.execution_gate_of`), **not** recomputed. `position_cap` is the display string derived from this status. Account permission (`can_trade_live`, from the trust payload) is shown by TrustBanner and folded into the per-stock gate (§8.4); it is a separate axis from the valve.
2. **Funnel narrow end — 值得专注 (2–4)**: the only candidates shown expanded on first screen.
3. **One-sentence verdict per candidate**: `action_state` + the single blocker / need, in operator language. Not a wall of badges.
4. **Two prices per candidate**: `trigger_price` and `invalidation_price`, pre-registered.
5. **Theme strength signal per candidate**: `theme_in_play` and `rank_in_theme`, from existing data.

Explicitly demoted out of the first screen (moved to an expandable detail layer): AI Judge telemetry, the full `factor_tags` set, `execution_quality` prose, `consistency` score, `tushare_score`, and the stacked `risk_tags`. These are not unimportant; they must not compete for attention in the decision moment. The jargon firewall applies: first-screen copy stays in operator language (no `manifest`, `freshness_status`, `fallback_used`, internal enum names).

## 8. State Machines (Stage-1 Scoped)

### 8.1 Data trust (consumed, not computed)

```
trust_level ∈ { trusted | observe_only | unreliable }
# Single source: capability_matrix.evaluate_trust_level, via TrustBanner.
# The discovery page MUST NOT recompute this.
```

### 8.2 Portfolio valve (consumed, not computed)

```
valve = execution_gate.status ∈ { on | limited | off }
# Source: ai_screening.execution_gate_of(market_regime) -> gate["status"],
#          surfaced per screening batch (NOT the readiness payload).
# on -> 开 (0.5-0.8成), limited -> 半开 (0.3-0.5成), off -> 关闭 (0成).
# position_cap is the display string DERIVED from this status; the page reads status.
```

### 8.3 Two axes, kept separate

The biggest conceptual fix. Two questions must not be merged:

- **gate (can I buy? — permission)** — closed / capped / open.
- **action_state (should I prioritise? — triage)** — focus / on_trigger / watch / drop.

A downgraded stock (`risk_level = degrade`) is still *buyable* if the valve is open; it is only *deprioritised*. So degrade belongs to `action_state`, **not** to `gate`. The prior draft put degrade in `gate = capped`; that was wrong and is corrected here.

### 8.4 gate.state — permission only

```
gate.state =
  closed  if NOT can_trade_live                      # account mode (from trust payload)
        OR execution_gate.status == off              # valve closed
        OR stock.risk_level == block                 # 硬拦截
  capped  if execution_gate.status == limited        # valve half-open
        OR trust_level != trusted                    # data not fully trusted
  open    otherwise

gate.blocker = the FIRST single reason (operator language)
```

Stage-1 signals only: `can_trade_live` (trust payload, via TrustBanner), `execution_gate.status` (screening pipeline), `trust_level` (TrustBanner), `risk_level` (the `RiskLevel` enum is `info | warn | degrade | block` — four values, not three). Richer filters (suspend, limit-up/down, lock-up expiry, earnings windows) arrive with Stage 2 / 3 data and extend this derivation then.

### 8.5 action_state — triage, gated by permission

```
action_state =
  drop        if lifecycle eliminated                       # overrides everything
  focus       if V2 action == actionable AND gate.state == open
  on_trigger  if V2 action == trial        AND gate.state != closed
  watch       otherwise
              (includes: V2 shadow / review / observe,
                         risk_level == degrade,             # 降级 -> deprioritise, not block
                         risk_level == warn,
                         gate.state closed / capped)        # can't act -> only watch
```

Per protocol §10.5 (weak context must downgrade, not overstate): a closed or capped gate degrades `action_state` to `watch` rather than inventing a stronger conclusion. This is exactly why gate and action_state **compose** instead of **merge** — gate is the permission filter, action_state is the priority that survives it.

### 8.6 Why three separate signals

The trust-level single-source contract exists precisely because a prior bug let the sidebar say "系统正常" while `readiness_mode` was `shadow_only`. Merging trust + valve + gate into one recomputed "gate" string would reintroduce that class of bug. The page **composes** these signals into the visible verdict but never **merges** them into one recomputed field.

## 9. Field Convergence Map (display, not deletion)

The triage card shows fewer fields than `StockListCard` carries. This is a **display** convergence: protocol-mandated fields stay in the canonical object (e.g. `why_now` is its own required field per protocol §6); the card composes several into one displayed element. Verified against `StockListCard` (`apps/web/src/lib/types.ts:876`).

| Triage element | Drawn from (real `StockListCard` fields) | Note |
|---|---|---|
| One-sentence verdict | `thesis` + `why_now` + `decision_summary` | composed for display; underlying fields kept (protocol §6) |
| action_state | V2 action (in `opportunity_v2`) + `decision_rank` + `risk_level` + lifecycle | enum; see §8.5 |
| gate | `hard_gate_blocks_action` (bool) + `hard_gate_max_action` + `hard_gate_block_reason` + `risk_level` + `block_reason` | **`hard_gate_blocks_action` already exists structured** — read it, do not grep |
| trigger_price / invalidation_price | `entry_plan.levels` + `entry_plan.trigger` / `entry_plan.invalidate` + `resistance` / `support` / `stop_loss` | two numbers |
| needs[] | `missing_confirmation[]` + `upgrade_condition` | enum |
| theme + theme_in_play | `theme` + `theme_phase` / `theme_phase_value` (label/value pair) + `theme_phase_theme` | label/value pair **preserved**, not collapsed |
| rs.rank_in_theme | `decision_rank` + `priority_score` / `best_score` within the theme cohort | Stage-1 ranking only (vs-index is Stage 2) |

Demoted off the card into the expandable detail layer: `factor_tags[]`, `factor_risk_flags[]`, `tushare_score`, `execution_quality_*`, `consistency_*`, `crowding_risk`, `fake_breakout_risk`, `ai_*`, `v2_calibration_*`.

**Correction from verification:** the prior draft's field map named `entry_reason`, `main_risk`, `watch_condition`, `screening_status`, `tier`, `tier_rank`, `themes` — none of these exist on `StockListCard` (they were raw-pipeline / sample-prose names). This table uses only real card fields, and it does not collapse the label/value pairs (`*_phase` / `*_value`), which are display companions, not duplicates.

## 10. Interaction Flow

```
Open page (2s)
  → read the two lights: is data trusted? is the valve open?
     ├─ valve closed / capped → "observation mode": first screen shows only
     │                          等触发 and 只观察; header states "今天不开新仓"
     │                          with the single blocker reason.
     └─ valve open           → show 值得专注 (2–4).
        → scan cards (name / theme / verdict / trigger / invalidation / theme-RS)
           ├─ want depth  → expand detail layer (capital / volume / AI / factor / crowding)
           └─ want to follow → add to 等触发, set price alert
        → trigger hits    → promote + highlight into 试错待复核
        → close           → auto-archive: upgraded / downgraded / invalidated
                           → feed Review for graded review
```

Two current gaps closed as decision-structure work (Stage 1):

- **Intraday transition capture**: the "由负转正" / "午盘转弱" state migrations become trigger-driven highlights / pushes, not buried snapshots. This keeps the live-session value the user cares about, but drives it from structured `needs` transitions rather than a flat group.
- **Exit prompt**: each first screen carries one line — "昨日 trial 今天该复核 / 止盈 / 止损" — closing the entry-bias gap without any new data source.

## 11. Prioritized Roadmap

### P0 — root fix (Stage 1, in scope)

1. Make the page read the **already-structured** V2 gate fields (`hard_gate_blocks_action`, `hard_gate_max_action`, `hard_gate_block_reason`) and `execution_gate.status`, instead of `buyGateMeta()` text-grepping. The structured fields already exist; the workbench ignored them.
2. Build the `TriageDecision` view-object for V2 candidates; compute `action_state` (§8.5) and `gate` (§8.4) once, upstream of render.
3. First screen becomes "trust light (TrustBanner) + valve light (`execution_gate.status`) + funnel narrow end"; delete the five equal-weight groups.
4. Display convergence per §9 (one-sentence verdict, two prices, `needs[]`).

### P0.5 — legacy path migration (Stage 1, separate card)

5. The non-V2 candidate path has no structured gate fields — that is why `buyGateMeta()` greps prose for it. Migrate it to emit the same structured fields. Sized as a **separate card** because it is a screener-package change of unknown size; P0 must not block on it. Until migrated, legacy candidates render with `gate` derived from `risk_level` only, plus a visible "legacy, gate inferred" tag.

### P1 — decision-structure gaps (Stage 1, in scope)

6. `rs.rank_in_theme` and `rs.theme_in_play` become first-class, fed into the funnel's theme-strength layer (existing data only; vs-index RS stays Stage 2).
7. Exit prompt: daily "昨日 trial 复核" line. **Infra confirmed** — `candidate_lifecycle.find_previous_snapshot` + `compute_lifecycle(current, previous, ...)` already support cross-day comparison.
8. Same-theme concentration hint when >3 candidates share a theme (trivially derivable from `theme`). Cross-theme macro correlation (e.g. 化工 + 有色 = same beta) needs a theme→macro map that may not exist — deferred to a later refinement, not this card.

### P2 — formal data sources (Stage 2, deferred)

Dragon-tiger list, large-order / block-trade flow, limit-up seal strength, lock-up expiry, earnings windows → wired into `gate` hard filters. **Blocked on Stage 2.**

### P3 — strategy validation (Stage 2 / 3, deferred)

- Relative strength versus benchmark index (Stage 2 benchmark series).
- T+1 / T+3 / T+5 / T+10 forward-return backfill feeding Review (Stage 2 formal daily series; touches `data/quant/`).
- Rule-compliance tracking — did the user take the trades the system flagged (Stage 3 execution reality).

P2 and P3 are written down so they stay visible (anchor: "keep the next stage visible"), but they are **not** worked in Stage 1.

### Definition of Done (P0)

- `buyGateMeta()` and its keyword lists are deleted; no text-grep derives a buy verdict anywhere in the discovery page.
- Every V2 candidate card reads `gate.state` / `action_state` from one structured source.
- First screen shows the trust light (TrustBanner) + valve light (`execution_gate.status`) + funnel narrow end only; the five equal-weight groups are gone.
- `JargonLeakTests` still pass (first-screen copy stays in operator language).
- The closed-valve path renders observation mode with a single blocker reason (no empty focus layer).

## 12. Relationship to the Decision Protocol

- Implements §6 (canonical decision object) and §16.2 (replace page-specific conclusion assembly).
- Honors §10.5 (unknown context must downgrade, not overstate): the gate derivation degrades toward `watch` / closed when signals are weak.
- Honors §13 (freshness / confidence / missing data): missing data reduces action aggressiveness; `needs[]` makes the degradation explicit and structured.
- The four action tiers (§8) become the funnel layers (§6). One vocabulary, no fifth tier.

## 13. Good-Finish Check (per anchor)

1. Does this move Prism closer to trusted daily decisions? Yes — the verdict becomes a single first-class truth instead of a render-time guess.
2. Does it reduce source ambiguity? Yes — trust / valve / gate are separated; the page consumes single sources instead of recomputing.
3. Does it make the next session easier to resume? Yes — `TriageDecision` is a stable, inspectable contract.
4. Did we avoid scope drift? Yes — Stage 2 / 3 work (new data sources, validation backfill) is explicitly deferred in §2 and §11.

## 14. Open Questions for Implementation

- Exact migration path for the legacy (non-V2) candidate path: migrate to `TriageDecision` directly, or keep a shim until all sources emit it? Decide at plan time.
- Where the `TriageDecision` builder lives in the data layer (mirrors protocol §16.1 "canonical decision builder") — decide at plan time, must be one place.
- Whether `needs[]` enum values are fixed now or extensible; recommendation: fixed set in Stage 1, extended only when a new need arrives from existing data (not from Stage 2 sources).
