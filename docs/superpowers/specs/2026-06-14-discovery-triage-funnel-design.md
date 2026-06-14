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
   - **进攻阀门 (portfolio valve)** — `can_trade_live` + `market_phase` + `position_cap`, states `开 / 半开 / 关闭`. Answers "is the account allowed to act, and at what size?" These are **separate** booleans from trust (per the trust-level single-source contract); they stay separate in copy.
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
valve ∈ { open | half | closed }
# Composed from can_trade_live (account mode), market_phase, position_cap.
# Already exists in readiness payload; the page reads it.
```

### 8.3 Per-stock gate (derived, Stage-1 signals only)

```
gate.state =
  closed  if NOT can_trade_live
        OR market_phase == risk_off
        OR stock.risk_level == block        # 硬拦截 — existing hard signal
  capped  if trust_level != trusted
        OR market_phase == risk_capped
        OR remaining position_cap == 0
        OR stock.risk_level == degrade      # 降级 — e.g. 审计意见异常 (existing signal)
  open    otherwise

gate.blocker = the FIRST single reason that set closed/capped (operator language)
```

This follows the system's existing `risk_level` semantics: `block` → 硬拦截 → closed; `degrade` (e.g. 审计意见异常) → 降级 → capped; `warn` → 提醒 → open but flagged. Stage-1 hard filters are limited to the signals the system already has (`risk_level`, existing `factor_risk_flags` as supporting context). Richer filters (suspend status, limit-up/down, lock-up expiry, earnings windows) arrive with Stage 2 / Stage 3 data and are added to this derivation then — not now.

### 8.4 Why three separate signals

The trust-level single-source contract exists precisely because a prior bug let the sidebar say "系统正常" while `readiness_mode` was `shadow_only`. Merging trust + valve + gate into one recomputed "gate" string would reintroduce that class of bug. The page **composes** three signals into the visible verdict but never **merges** them into one recomputed field.

## 9. Field Convergence Map

The same concept is currently spread across 3–4 prose fields. Each concept collapses to one structured field.

| Concept | Current scattered fields | Converges to |
|---|---|---|
| Thesis | `thesis` + `entry_reason` + `why_now` + `decision_summary` | `thesis` (one sentence) |
| Invalidation | `invalidation` + `main_risk` + `invalid_condition` + `foot` | `invalidation_price` + one sentence |
| What is missing | `missing_confirmation` + `watch_condition` + `upgrade_condition` + `needs` | `needs[]` (enum) |
| Score / rank | `priority_score` + `best_score` + `score` + `decision_rank` | `rs.rank_in_theme` |
| Status | `screening_status` + `tier` + `tier_rank` + `status` + `action` + `suggested_action` | `action_state` (enum) |
| Theme | `theme` + `themes` + `theme_phase` + `theme_phase_theme` + `theme_in_play` | `theme` + `rs.theme_in_play` |
| Gate | `hard_gate_max_action` + `hard_gate_block_reason` + `risk_level` + `block_reason` | `gate.state` + `gate.blocker` |

Field names and the migration path from the existing `StockListCard` / V2 fields are fixed at implementation time, but the **contract** above is fixed now: one structured field per concept.

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

1. Build the `TriageDecision` object; compute `action_state` and `gate` once upstream.
2. Delete `buyGateMeta()` text-grepping; read `gate.state` instead. Collapse the `hasV2` / legacy split.
3. First screen becomes "two lights + funnel narrow end"; delete the five equal-weight groups.
4. Converge redundant fields (thesis / invalidation / needs each collapse per §9).

### P1 — decision-structure gaps (Stage 1, in scope)

5. `rs.rank_in_theme` and `rs.theme_in_play` become first-class, fed into the funnel's theme-strength layer (existing data only).
6. Exit prompt: daily "昨日 trial 复核" line.
7. Concentration / correlation hint when >3 candidates share a theme ("隐含同一宏观下注") — derivable from the candidate set, no new source.

### P2 — formal data sources (Stage 2, deferred)

Dragon-tiger list, large-order / block-trade flow, limit-up seal strength, lock-up expiry, earnings windows → wired into `gate` hard filters. **Blocked on Stage 2.**

### P3 — strategy validation (Stage 2 / 3, deferred)

- Relative strength versus benchmark index (Stage 2 benchmark series).
- T+1 / T+3 / T+5 / T+10 forward-return backfill feeding Review (Stage 2 formal daily series; touches `data/quant/`).
- Rule-compliance tracking — did the user take the trades the system flagged (Stage 3 execution reality).

P2 and P3 are written down so they stay visible (anchor: "keep the next stage visible"), but they are **not** worked in Stage 1.

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
