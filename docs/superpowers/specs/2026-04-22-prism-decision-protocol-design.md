# Prism Decision Protocol Design

## 1. Document Purpose

This document defines the stage-one decision protocol for Prism.

Its job is to turn the current product direction into a fixed operating contract:

- one stock must map to one main conclusion at one moment
- every conclusion must be explainable in beginner language
- every core page must read from the same decision object
- support layers may enrich a conclusion, but may not create a competing top-level answer

This document sits between product strategy and implementation.
It is meant to reduce future drift across Today, Ask, Holdings, Opportunities, and Review.

## 2. Why Prism Needs A Decision Protocol

The current Prism prototype already has meaningful product shape:

- Today acts as the daily action desk
- Ask acts as the single-stock decision entry
- Holdings and Opportunities already expose stock-level judgment
- Review already carries trust-building and change context

But the system still has a structural risk:

- the same stock can appear in different sources
- those sources can emphasize different labels, reasons, and risk wording
- page-level copy can be unified while the underlying decision contract is still loose

That is dangerous for stage one.
A beginner-facing product cannot afford “surface consistency but model inconsistency.”

Prism therefore needs a formal decision protocol.

## 3. Product Role Of The Decision Protocol

The decision protocol is the product core of stage one.

It is not an engineering detail.
It defines what the product is allowed to say.

In stage one, Prism is a strong-decision assistant for A-share beginners.
Its promise is not “show all available signals.”
Its promise is:

`Tell me what to do today, tell me why, tell me when this view stops being valid.`

The decision protocol is the mechanism that makes that promise repeatable.

## 4. Fixed Product Boundaries

The decision protocol must inherit all stage-one boundaries already set for Prism.

### 4.1 User Boundary

The protocol serves A-share beginners.

It must prefer clarity, guardrails, and actionability over expert richness.

### 4.2 Market Boundary

The protocol applies only to A-shares.

### 4.3 Time Horizon Boundary

The protocol serves a default 1-5 trading day short-swing decision horizon.

Intraday changes can update the decision.
Longer-term context can explain the decision.
Neither can replace the primary short-swing frame.

### 4.4 Execution Boundary

The protocol supports manual execution only.
It does not place trades.
It does not simulate brokerage behavior.
It does not become an auto-trading layer.

## 5. The Core Product Rule

At any given time, Prism must produce exactly one main conclusion per stock.

That conclusion may be informed by:

- holdings state
- watchlist state
- opportunity screening
- midday confirmation
- live context and triggers
- historical review context

But the product-facing output must still converge to one top-level answer.

This is the non-negotiable rule.

## 6. The Stage-One Canonical Decision Object

Every stock-level surface in Prism should read from one canonical decision object.

The canonical object does not need to be implemented as a final class immediately, but its product contract must be fixed now.

### 6.1 Required Fields

Each decision object must contain these required fields:

- `stock_id`
  A unique stock identity for the current market scope, represented by code in stage one.
- `stock_name`
  Human-readable stock name.
- `trade_date`
  The primary trade date for the active decision context.
- `source_scope`
  The dominant source that currently owns the decision, such as holdings, opportunities, ask-derived, or review snapshot.
- `main_conclusion`
  The one product-facing top conclusion for the stock.
- `action_tier`
  The execution urgency tier used by the product-wide action language.
- `position_guidance`
  The suggested position framing the beginner can actually use.
- `risk_boundary`
  The main boundary that should keep the user from expanding the action carelessly.
- `why_now`
  The shortest convincing reason the conclusion currently stands.
- `continue_condition`
  The condition under which the user can continue the plan.
- `stop_condition`
  The condition under which the user should stop the current plan.
- `next_step`
  The next immediate action sentence in executable language.
- `trigger_condition`
  The condition that would justify upgrading or changing the action.
- `avoid_action`
  The most important thing the user should not do now.
- `evidence_entry`
  Where the user can verify the conclusion if they want more trust.
- `confidence_note`
  A plain-language expression of current confidence reliability.
- `updated_at`
  The freshness marker for the decision.

### 6.2 Optional Support Fields

The canonical object may also carry optional support fields:

- `midday_status`
- `holding_status`
- `opportunity_status`
- `cross_context`
- `level_map`
- `reason_bullets`
- `event_context`
- `review_context`
- `artifact_links`

These fields may enrich trust.
They may not override the required fields unless the protocol explicitly says they do.

## 7. Allowed Main Conclusions

Stage one should keep the top conclusion set deliberately small.

The canonical user-facing conclusions are:

- `买入`
- `持有`
- `卖出`
- `观察`

Because the current system already contains nuanced language such as `减仓观望`, `保留`, `继续观察`, and `轻仓试错`, the protocol should separate the main conclusion from the execution wording.

### 7.1 Main Conclusion Layer

The main conclusion layer answers the simple beginner question:

- buy or not
- hold or not
- sell or not
- only watch or not

This layer should stay small and stable.

### 7.2 Execution Wording Layer

The execution wording layer can remain richer.
Examples include:

- 先轻仓试错
- 先减仓观望
- 先继续持有，不追加
- 先只观察，不开新仓
- 先退出，不继续原计划

This split is important.
Without it, Prism will either sound too vague or become too inconsistent.

## 8. Action Tier Contract

Prism already established a cross-page action tier language.
That language should now become part of the decision protocol.

The fixed action tiers are:

- `立即执行`
- `等触发`
- `仅观察`
- `明确回避`

### 8.1 Role Of Action Tiers

Action tiers do not replace the main conclusion.
They express urgency and discipline.

Examples:

- a stock can have main conclusion `持有` with action tier `立即执行`
- a stock can have main conclusion `买入` with action tier `等触发`
- a stock can have main conclusion `观察` with action tier `仅观察`
- a stock can have main conclusion `卖出` with action tier `明确回避`

### 8.2 Why Both Layers Are Needed

Beginners need both:

- the simple answer
- the execution posture

The simple answer tells them the direction.
The action tier tells them the discipline.

## 9. Sentence Contract For Beginner Execution Language

All single-stock action language should follow a shared sentence contract.

### 9.1 Required Sentence Shape

- `next_step` should begin with `先...`
- `trigger_condition` should naturally include `再...`
- `avoid_action` should begin with `先不要...` or another equally direct prohibition form

### 9.2 Why This Matters

This is not cosmetic.
For beginners, syntax is part of risk control.

The product should teach a mental sequence:

1. first do this
2. if this condition happens, then do that
3. before that, do not make this mistake

That is the practical discipline Prism is supposed to provide.

## 10. Decision Conflict Resolution Rules

Because Prism merges holdings, watchlist, opportunities, and midday layers, the protocol must define who wins when signals conflict.

### 10.1 Conflict Rule 1: Holdings Beats Opportunities

If a stock is already in holdings, the holdings decision owns the top conclusion.

Reason:
The user already carries risk.
Existing exposure must outrank hypothetical opportunity framing.

### 10.2 Conflict Rule 2: Midday Change Can Upgrade Or Downgrade, But Not Fork

Midday confirmation may update the current decision.
It may not create a parallel top conclusion.

Allowed:

- `观察` becomes `买入`
- `持有` becomes `卖出`
- `买入` becomes `观察`

Not allowed:

- one section says `继续持有`
- another section says `只观察`
- a third section says `可以轻仓试错`

All of these must be resolved into one output.

### 10.3 Conflict Rule 3: Ask Cannot Invent A Separate Product Truth

Ask is a decision entry, not an independent judgment universe.

Ask may use additional real-time context.
Ask may improve wording and explanation.
But if the stock is already known to the system, Ask must converge to the same main conclusion family as the canonical object.

If Ask differs, Prism should treat that as a system resolution problem, not a feature.

### 10.4 Conflict Rule 4: Review Is Historical, Not Current Authority

Review may explain what changed and why.
It may not become the page that defines current stock truth.

### 10.5 Conflict Rule 5: Unknown Context Must Downgrade, Not Overstate

If freshness, confidence, or source completeness is weak, the protocol should degrade toward `观察` or smaller action wording, rather than inventing a stronger conclusion.

## 11. Source Ownership Model

Every canonical decision should expose which source currently owns the conclusion.

Stage-one ownership types should be:

- `holdings`
- `opportunity`
- `ask_resolved`
- `midday_update`
- `review_snapshot`
- `live_fallback`

Ownership is for explanation and engineering traceability.
It should not be the main thing the user sees.

## 12. Cross-Page Responsibilities

The protocol only works if each page respects its boundary.

### 12.1 Today

Today owns the portfolio-level answer:

`What should I do today overall?`

It should present:

- daily stance
- top actions
- holdings actions
- opportunities worth attention
- risk and change notes

Today may summarize stock decisions.
It should not become the richest stock detail page.

### 12.2 Ask

Ask owns the fastest single-stock entry.

It should expose the full canonical decision in the most compact form.
It may enrich the decision with follow-up conversation.
It may not fork the decision protocol.

### 12.3 Holdings Detail

Holdings detail owns the active risk-bearing stock view.

It should be the clearest page for:

- whether to keep holding
- how much to hold
- what invalidates the hold
- what to watch intraday

### 12.4 Opportunity Detail

Opportunity detail owns pre-position decision quality.

It should answer:

- whether this is worth trying
- under what trigger
- with what sizing
- what would cancel the plan

### 12.5 Review

Review owns trust and memory.

It should show:

- what the system said
- what later changed
- what held up
- where the user or system was wrong

## 13. Freshness And Confidence Rules

The protocol needs a stable downgrade behavior when data quality is mixed.

### 13.1 Freshness Rule

Every decision must have a visible freshness marker.

If freshness is missing, the product should still render, but the confidence framing must weaken.

### 13.2 Confidence Rule

Confidence is not a numeric promise.
In stage one, it should remain human-readable.

Examples:

- 可以直接按纪律执行
- 先按现有结论执行，但别放大动作
- 当前证据不完整，先只观察

### 13.3 Missing Data Rule

Missing data should reduce action aggressiveness before it reduces explanation richness.

That means:

- do not hide risk just because data is thin
- do not escalate action just because one layer looks strong
- do not convert missingness into false certainty

## 14. Product Decisions Fixed By This Protocol

The following decisions should now be treated as fixed for stage one.

### 14.1 Fixed Decision Layers

Prism stock decisions must always include:

- one main conclusion
- one action tier
- one position guidance
- one risk boundary
- one next step
- one trigger condition
- one avoid action
- one explanation block

### 14.2 Fixed Page Priority

Across stock detail surfaces, the reading order should remain:

1. conclusion
2. position
3. risk boundary
4. next step
5. why now
6. continue and stop conditions
7. execution loop
8. evidence

### 14.3 Fixed Language Style

The product must explain decisions in short beginner-executable language.

It should avoid:

- expert abbreviations as the main output
- multi-paragraph theory before action
- competing labels for the same idea
- source-first wording that hides the action

## 15. What This Protocol Unlocks Later

Once the canonical decision object is stable, Prism can safely build the next layers.

### 15.1 Better Change Notifications

Midday updates become clean “decision changed from A to B” events.

### 15.2 Better Review Memory

Review can compare decision versions instead of comparing raw page states.

### 15.3 Better Personalization

Stage-two personalization can adapt sizing, wording, and caution level without breaking the core decision grammar.

### 15.4 Better UI Consistency

Every page can present the same truth differently without saying different things.

## 16. Immediate Product Priorities After This Protocol

Once this protocol is accepted, the next product priorities should be:

1. create a real canonical decision builder in the data layer
2. replace page-specific stock conclusion assembly with canonical decision assembly
3. make Today read from the same stock decision objects as Ask and detail pages
4. formalize change history for main conclusion transitions
5. strengthen Review around “what changed and why” instead of static summaries

## 17. Final Product Statement

Stage-one Prism should behave like one disciplined beginner decision system, not several partially aligned stock views.

The decision protocol is the rule set that makes that possible.

Its practical promise is:

`No matter where a stock appears in Prism, the user should meet the same main conclusion, the same action discipline, and the same risk boundary.`
