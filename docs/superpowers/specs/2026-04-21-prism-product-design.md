# Prism Product Design

## 1. Document Purpose

This document defines the first-stage product direction, product boundaries, information architecture, and roadmap baseline for Prism.

It is written to solve the current state where Prism already has real workflow capability and a usable prototype, but the overall product structure, target user definition, page hierarchy, and long-term growth path are still mixed together.

This document is the product baseline for future planning, interaction design, prioritization, and implementation.

## 2. Product Definition

Prism stage one is not a professional research workstation for institutions.

Prism stage one is a strong-decision AI investment assistant for A-share beginners.

Its default decision engine is based on a 1-5 trading day short-swing view. It combines current holdings, watchlist signals, and system-generated opportunities into one daily action layer, then outputs explicit buy, sell, hold, or watch guidance with position sizing and risk suggestions.

Prism should help the user answer one primary question every day:

`What should I do today?`

That answer must then be decomposed into clear actions across three practical areas:

- what to do with current holdings
- what to continue watching
- what new opportunities are worth trying today

## 3. Target User

### Primary User

The first-stage user is an A-share investing beginner.

This user:

- does not have a mature research system
- is easily affected by fragmented information and market noise
- wants direct action guidance more than raw analysis
- still needs enough explanation to trust the recommendation
- is not looking for a complex professional terminal

### Non-Target Users For Stage One

Prism stage one is not optimized for:

- institutional research teams
- advanced professional traders with their own data stack
- quantitative users needing parameter-heavy strategy tooling
- multi-market professional investors

These users may become future expansion audiences, but they must not shape stage-one product decisions.

## 4. Product Goal

The first-stage goal of Prism is:

`Help A-share beginners make clearer daily decisions with less confusion and fewer uncontrolled mistakes.`

Prism is not just a stock research helper. It should become a daily decision surface.

The user should feel that Prism is the first thing to open before acting, because it provides:

- a unified daily action list
- explicit stock-level judgment
- position and risk framing
- a way to understand what changed
- a record they can come back to later

## 5. Product Ceiling

Prism's ceiling should be understood in three levels.

### Level 1: Daily Decision Entry

Prism becomes the user's daily first-stop decision product.

Before reading scattered market content or reacting emotionally, the user first checks Prism to see today's overall stance and recommended actions.

### Level 2: Personal Investment Operating System

Prism gradually evolves from a generic assistant into a system that understands the user's holdings, behavior, decision mistakes, and risk style.

At this stage Prism is no longer just giving generic answers. It is helping this specific user make better repeatable decisions.

### Level 3: Trusted Decision Layer

The highest realistic ceiling is not automatic trading. It is trusted delegated judgment.

The user begins to treat Prism like a stable decision layer that provides:

- clear action recommendations
- sizing guidance
- guardrails and invalidation conditions
- reviewable historical reasoning

The real moat is not model novelty. The moat is consistency, damage control, and trust over time.

## 6. Product Principles

Prism should follow these product principles.

### 6.1 Action First

Prism must lead with actions, not raw evidence.

The product should first answer what to do, then explain why.

### 6.2 Strong Judgment With Guardrails

Prism can be strong-decision in experience, but it must never be reckless.

Every recommendation should include:

- the main action
- confidence or strength framing
- suggested position sizing
- main risk
- invalidation condition

### 6.3 One Stock, One Main Conclusion

At a given time, the product must converge to one main action per stock.

Different layers such as watchlist context, midday change, or opportunity classification may add nuance, but they must not create conflicting top-level conclusions.

### 6.4 Explain In Human Language

Prism should not behave like a research dump.

Its explanation should be compact, practical, and understandable by a beginner.

### 6.5 Fewer Mistakes Over More Information

Prism does not win by showing more content. It wins by helping the user avoid uncontrolled decisions.

## 7. Fixed Product Boundaries

The following boundaries must remain fixed for stage one.

### 7.1 User Boundary

Stage one serves A-share beginners.

### 7.2 Market Boundary

Stage one serves only A-shares.

No Hong Kong stocks, US stocks, funds, options, crypto, or multi-market expansion should enter the first-stage scope.

### 7.3 Time Horizon Boundary

The default judgment engine is 1-5 trading day short-swing decision making.

Intraday changes and longer trend context may exist as support layers, but they must not override the primary short-swing action framework.

### 7.4 Primary Product Question Boundary

The product must prioritize this question:

`What should I do today overall?`

All primary surfaces should reinforce this question.

### 7.5 Output Boundary

Core output must always converge to:

- buy
- hold
- sell
- watch
- suggested position sizing
- risk note

Everything else is support.

### 7.6 Execution Boundary

Stage one does not place orders and does not connect to automated trading execution.

Prism gives decision support and action guidance, but the user executes manually.

### 7.7 Input Boundary

The main daily decision layer must combine:

- holdings
- watchlist
- system opportunities

Prism should not become an unstructured news surface or a content feed.

### 7.8 Content Boundary

Prism is not a market media product, not a social community, and not an encyclopedia.

News and evidence are inputs to judgment, not the main user-facing output.

## 8. Stage-One Core User Experience

The stage-one product experience should center on five core modules.

### 8.1 Daily Action List

This is the heart of the product and the main daily entry.

It must answer:

- whether today is more offensive, cautious, or observation-focused
- what to do with current holdings
- what watchlist names deserve continued attention
- which new opportunities are worth small-sized attempts
- what risk changes or important midday updates matter

### 8.2 Stock Decision Card

Every stock in Prism, regardless of whether it comes from holdings, watchlist, or opportunities, should collapse into one unified decision card.

Each card should contain:

- stock name and code
- main conclusion: buy, hold, sell, or watch
- confidence or strength framing
- suggested position size
- risk level
- core reasons
- invalidation condition
- suggested observation window

### 8.3 Evidence And Explanation Layer

Evidence must support trust, not overwhelm the user.

Explanation should be structured around three simple questions:

- why is this the recommendation now
- what is the biggest current risk
- what condition would make this view invalid

### 8.4 Midday Change Layer

Midday refresh capability should be productized as change notification, not as a separate competing decision system.

Its purpose is to communicate meaningful action changes such as:

- hold becoming reduce or sell
- watch becoming small buy attempt
- buy candidate being canceled due to weakening follow-through

### 8.5 Review And Trust Layer

Prism must have a basic review layer even in stage one.

Users should be able to see:

- what the system recommended
- whether they followed it
- what happened afterward
- which ideas held up and which failed

## 9. Stage-One Information Architecture

Prism stage one should use a product-facing navigation system distinct from the internal operations console.

### 9.1 Primary Navigation

The first-stage user-facing primary pages should be:

- Today
- Ask
- Holdings
- Opportunities
- Review

### 9.2 Page Roles

#### Today

Today is the main decision surface.

It should answer the overall daily action question and act as the user's primary daily landing page.

The page structure should follow this order:

1. today's overall stance
2. top three actions
3. holdings actions
4. actionable opportunities
5. risk and change notes

Today is not a navigation shell. It is a decision page.

#### Ask

Ask is the natural-language stock inquiry entry.

It exists because many beginner users will first come with a single-stock question such as:

- can I still hold this stock
- is this worth buying now
- what should I do with this name today

Ask should therefore:

- return a direct conclusion first
- provide position and confidence framing
- explain the key reason, risk, and invalidation condition
- allow follow-up questions without turning into an encyclopedia

Ask is not a generic search surface. It is a fast decision surface for single-stock judgment.

#### Holdings

Holdings is where users manage what they already own.

Its only core job is to answer: what should I do with my current positions.

#### Opportunities

Opportunities is where users see what is worth trying today.

This list should remain curated and narrow. High-quality, limited candidates are better than large noisy lists.

#### Review

Review is the trust-building layer.

It should show historical recommendations, changes, execution reflection, and outcome tracking.

### 9.3 Secondary Views

Secondary views may include:

- stock detail
- change alerts
- evidence detail
- history detail

### 9.4 Internal Operations Console

The following capabilities should not be primary user-facing navigation for beginner users:

- system health
- manual task trigger
- run logs
- batch details
- internal refresh operations
- workflow execution status

These belong in an internal operations layer, not the main product IA.

## 10. Why Prism Currently Feels Mixed

The current Prism prototype already contains meaningful capability, but the product feels mixed because system-facing and user-facing structures are still blended together.

The main causes are:

### 10.1 Workflow View Dominance

Too much of the current shape is organized around internal workflow runs, batches, refreshes, and execution state.

### 10.2 Incomplete Conclusion-Centered Hierarchy

Prism already has Today, Watchlist, Opportunities, Review, and Ask surfaces, but they are not yet fully unified around a single action-centered hierarchy.

### 10.3 Mixed Object And Process Dimensions

Some views are organized by stock, some by workflow, and some by run/batch mechanics.

This causes unnecessary mental context switching.

### 10.4 Evidence Competes With Action

Logs, source state, and raw system output are useful, but they should sit behind the decision layer rather than beside it.

## 11. Product North Star And Success Metrics

Prism's north star should not be based on report count or analysis count.

The north star is:

`Users make more stable, executable daily decisions because they rely on Prism.`

The first-stage supporting metrics should include:

- daily action session completion rate
- recommendation adoption rate
- next-day return rate
- decision clarity feedback
- damage-control rate when recommendations fail

The product should optimize for decision quality and trust, not volume of output.

## 12. Requirement Filtering Rules

Before accepting any new stage-one feature, use these questions:

1. Does it help the user reach today's action faster?
2. Does it make stock-level judgment clearer?
3. Does it improve trust in recommendations?
4. Does it reduce beginner mistakes?
5. Does it create user value instead of exposing internal complexity?

If a proposed feature cannot clearly support at least one of the first four questions without failing the fifth, it should be deferred.

## 13. Three-Stage Product Roadmap

Prism should be developed as a staged capability ladder, not a flat feature list.

### Stage 1: Make The Daily Action Product Real

The goal is to make Prism's daily action surface truly usable and coherent.

Priorities:

- converge on five primary user-facing pages
- make Today the clear primary decision surface
- unify stock judgment into one consistent decision card language
- separate internal ops tooling from the user-facing product

### Stage 2: Personalize The Assistant

Once the action layer is stable, Prism should become more user-specific.

Priorities:

- incorporate current holdings structure
- adapt to user risk style
- reflect behavior patterns and recurring mistakes
- move from generic recommendation toward user-specific guidance

### Stage 3: Build Long-Term Trust And Retention

Once decisions are useful and personalized, Prism should build trust loops.

Priorities:

- stronger review surfaces
- outcome tracking
- recommendation history
- execution reflection
- clarity on when the system is more or less reliable

## 14. Next Three Months Priorities

### Month 1: Product Structure Convergence

Focus:

- finalize user-facing information architecture
- establish Today as the product home
- keep Ask as a first-class entry point
- unify decision language across pages
- separate operations console from user product navigation

### Month 2: Recommendation Consistency And Stability

Focus:

- ensure one stock maps to one main conclusion
- add structured reason, risk, invalidation, and position framing
- convert midday refresh into controlled change notifications
- establish base-level recommendation record tracking

### Month 3: Review And Trust Loop

Focus:

- strengthen review page
- show historical recommendation and later result
- preserve Ask follow-up continuity
- make it possible for users to see what Prism said and what happened next

## 15. Explicit Out-Of-Scope Items For Stage One

The following items are intentionally out of scope for stage one:

- multi-market expansion
- automated order placement
- social/community features
- large-scale educational content center
- heavy professional research configuration panels
- advanced strategy playgrounds for experts
- generalized financial media homepage

## 16. Final Product Statement

Prism should become the daily decision entry for A-share beginners.

Its first-stage product promise is simple:

`Open Prism, understand today's stance, and know what to do with your holdings and next opportunities.`

The product wins not by showing more, but by helping users make clearer decisions with stronger guardrails and better long-term trust.
