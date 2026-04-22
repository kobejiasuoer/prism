# Prism Today v2 Design

## 1. Document Purpose

This document defines the stage-two surface direction for Prism Today.

Its job is to turn the recently aligned product choices into a fixed page contract for the Today homepage before implementation starts.

The document focuses on one question:

`What should Prism Today look like and how should it behave if it is meant to help A-share beginners decide what to do today?`

This document sits between the broader product strategy and the actual page implementation.
It is meant to prevent Today from drifting back into either a generic dashboard or an overloaded research summary page.

## 2. Why Today Needs A v2 Redesign

The current Prism prototype already has the right product ambition:

- Today is the daily landing page
- Ask is the single-stock decision entry
- Holdings and Opportunities already expose stock-level judgment
- Review already supports trust and change tracking

But the current Today page still has a structural product problem.

It is more coherent than before, but it still does not fully deliver the first-screen experience Prism needs for stage one.

The main risks are:

- the page still reads partly like a structured report instead of a command surface
- evidence and support layers remain visually competitive with the main action layer
- the top section is clearer than before, but not yet strong enough to feel like a true decision desk
- a beginner user can still spend too much attention parsing layout instead of understanding what to do next

That is a meaningful product gap.
Prism is not trying to be a generic market information product.
It is trying to be a beginner-friendly decision system.

Today therefore needs a deliberate v2 redesign.

## 3. Product Role Of Today v2

Today v2 is the daily command surface of Prism.

It is not a general market dashboard.
It is not a deep research page.
It is not a single-stock analysis page.

Its product role is:

`Help an A-share beginner know today's main instruction, what to do first, what not to do, and where to go next if they need more depth.`

This means Today v2 must optimize for:

- fast comprehension
- clear command hierarchy
- beginner-safe execution framing
- minimal cognitive switching
- secondary trust support without stealing first attention

The homepage promise becomes:

`In 10 seconds, tell me today's command. In 30 seconds, tell me what to handle first. In 1 minute, tell me what I must avoid today.`

## 4. Core Product Direction

The approved direction for Today v2 is fixed as follows:

- page type: `strong-command daily surface`
- structural metaphor: `command desk`
- primary layout: `left command / right radar`
- visual mood: `warm command board`
- evidence strategy: `weak evidence exposure on first screen`

This combination is important.

It means Today v2 should feel decisive, but not cold.
It should feel operational, but not like a trader-only terminal.
It should feel trustworthy, but not overloaded with proof before action.

## 5. Reading Order Contract

The reading order for Today v2 is fixed.

The page should guide the user through this sequence:

1. `today's command`
2. `top actions`
3. `environment radar`
4. `holdings actions`
5. `opportunities actions`
6. `risk and change context`
7. `evidence and source access`

This order is not just a layout preference.
It is a product rule.

The homepage must teach the user to think in the right order:

- command first
- action second
- environment third
- explanation later

Any implementation that lets evidence, system detail, or report-style explanation interrupt that sequence should be treated as out of spec.

## 6. Page Structure

Today v2 should be composed of six major blocks.

### 6.1 Command Hero Block

This is the most important block on the page.
It owns the first screen and the highest visual weight.

Its layout should use the approved `left command / right radar` structure.

#### Left Command Area

The left side should contain:

- `today_command`: one sentence that states the main instruction of the day
- `top_action_1`: the highest-priority immediate action
- `top_action_2`: the second-priority action
- `clear_avoid`: one explicit thing the user should not do today

These items must use action language, not research language.

Examples:

- `先减仓弱票，再等强票触发`
- `先处理最弱持仓`
- `只盯最强机会，不分散看`
- `今天不追高`

This area should read like a decision board, not a summary card deck.

#### Right Radar Area

The right side should contain four compact radar cards:

- `position_cap`
- `main_theme`
- `risk_level`
- `midday_watch`

Each card should expose only:

- label
- current value
- one short supporting note

This side is not a report panel.
It is a quick environment sweep.
It exists to support the main command, not compete with it.

### 6.2 Holdings Actions Block

This is the first major block after the hero.

It must come before Opportunities because Prism serves beginners, and existing exposure should always be handled before new exposure.

This block should answer:

- which current holdings need action first
- whether the action is reduce, hold, watch, or stop
- what the user should do next on the most important holding names

It may continue using structured decision rows, but those rows should be visually subordinate to the hero block.

### 6.3 Opportunities Actions Block

This block comes after Holdings.

Its purpose is not to display a broad opportunity pool.
Its purpose is to surface only the few opportunity actions worth attention today.

The section should read as `selected candidate actions`, not as `market discovery inventory`.

That means:

- fewer rows are better than more rows
- action clarity matters more than breadth
- it should reinforce execution discipline, not create FOMO

### 6.4 Risk And Change Block

This block belongs to the second reading layer.

It should answer:

- what may change today's plan
- which conditions may invalidate the current stance
- what midday or environment shifts matter most

It should not create a second competing main conclusion.
It should only explain how the current command might change.

### 6.5 Evidence Hint Strip

This block should sit between the main action stack and the full evidence layer.

Its purpose is to create trust without stealing attention.

It should expose one short confidence message such as:

`今日判断已综合自选股快照、早盘批次与午盘确认，点开可查看完整证据。`

This strip should feel lightweight and reassuring.
It should not expand into a full evidence grid on first paint.

### 6.6 Evidence And Source Fold

The full evidence layer remains in scope, but it is explicitly a lower-priority layer.

This folded section may contain:

- refresh status
- evidence summary rows
- source snapshots
- quality checks
- raw artifact links

These are trust and traceability tools.
They are not first-screen decision tools.

## 7. Visual Design Direction

Today v2 should use a visual language that can be described as:

`warm command board`

This means the page should balance decisiveness with approachability.

### 7.1 Color Direction

The base mood should remain dark, but not pure black and not icy terminal blue.

The preferred palette direction is:

- deep navy as the main foundation
- warm gold or amber as the guidance accent
- controlled green, cyan, and red for action-state semantics
- muted neutral surfaces for lower-priority support blocks

The intent is:

- command surfaces feel focused
- support layers feel quieter
- risk colors stay meaningful instead of decorative

### 7.2 Hierarchy Direction

The highest visual weight must go to the daily command sentence.

Not to:

- metadata tags
- evidence labels
- source cards
- radar values on their own

The eye should land on the command first, then the top action rows, then the right radar cards.

### 7.3 Action Component Direction

Primary actions should look like command bars or instruction rails, not generic dashboard cards.

They should feel:

- numbered
- concise
- executable
- unmistakably prioritized

They should not feel like research notes.

### 7.4 Radar Component Direction

Radar cards should feel like cockpit indicators.

They must remain compact and fast to scan.
Long explanation should be avoided.

Each radar card should answer one question quickly:

- how much room is there
- what is the main line
- how risky is today
- what should I watch at midday

### 7.5 Evidence Layer Direction

Evidence should be visually present enough to signal trust, but not strong enough to compete with the command layer.

That means:

- a lightweight evidence hint on the first screen
- complete evidence below the fold or in a collapsed section
- no large first-screen evidence card wall

## 8. Interaction Principles

Today v2 should reduce switching, jumping, and interpretive effort.

The interaction model should feel like a guided flow.

### 8.1 Default Flow

The intended user flow is:

1. read today's command
2. act on the top actions
3. scan radar context if needed
4. move into holdings actions
5. move into opportunities actions
6. open risk or evidence only when necessary

The page should not require the user to mentally assemble this path themselves.

### 8.2 Progressive Disclosure

Trust layers should be disclosed progressively.

The user should never be forced to process all of these at once on first paint:

- evidence rows
- source cards
- quality cards
- artifact entry points

These belong to deeper inspection, not primary orientation.

### 8.3 Copy Principle

Copy across the Today page should use action language.

Preferred patterns:

- `先减仓弱票`
- `先等触发`
- `今天不追高`
- `先处理已有持仓`

Avoid report-style phrasing on the main surface.

Examples to avoid in primary UI:

- `基于板块轮动与资金承接，当前建议优先关注...`
- `从多源信号来看，短期结构更偏向...`

That language may still live in evidence and support layers.
It should not lead the page.

## 9. Mobile Behavior

Mobile should preserve the decision order, not the desktop geometry.

Desktop uses `left command / right radar`.
Mobile should convert this naturally into a vertical command flow:

1. command sentence
2. top action bars
3. avoid action
4. radar cards
5. holdings
6. opportunities
7. risk and evidence

Mobile does not need to replicate the two-column layout literally.
It needs to preserve the page's command logic.

## 10. Boundary Rules

The following constraints are fixed for this redesign.

### 10.1 Today Is Not A Research Page

Today may summarize and direct.
It must not become the place where full analysis is read.

### 10.2 Today Is Not A Trading Terminal

Do not introduce first-screen components such as:

- K-line master panels
- minute charts as primary modules
- dense state-light matrices
- heatmaps
- large data tables

These would shift the product toward a market tool instead of a beginner decision assistant.

### 10.3 Today Must Not Compete With Ask

Ask remains the single-stock decision entry.

Today should not turn into a quasi-chat or large-input experience.
If there is an Ask entry from Today, it should remain lightweight.

### 10.4 Today Must Not Duplicate Holdings Or Opportunities In Full

Today is an action-priority surface.
It should show only the highest-value subset.
Deeper exploration belongs to the dedicated pages.

### 10.5 Evidence Must Stay, But Stay Secondary

Trust is essential.
But trust does not mean first-screen overload.

Evidence must remain accessible, explicit, and inspectable.
It must not dominate the page hierarchy.

### 10.6 This Iteration Covers Today First

This redesign is a Today-first sample of the next Prism surface language.

It may later influence Ask, Holdings, Opportunities, and Review.
But this iteration should not attempt a full-site redesign in one pass.

## 11. Success Criteria

Today v2 should be considered successful if it achieves the following outcomes:

- a beginner can identify the day's main instruction immediately
- the first screen feels like a command surface, not a report page
- holdings action clearly outranks opportunity exploration
- evidence is still trusted, but no longer visually dominant
- desktop and mobile preserve the same decision order
- the page becomes a reusable surface model for later Prism pages

## 12. Implementation Implications

This spec implies a medium-scope redesign, not a simple cosmetic patch.

Expected implementation impact includes:

- restructuring the Today page hero block
- introducing a dedicated radar block in the hero
- rebalancing the weight of action rows versus evidence surfaces
- reducing or relocating elements that still feel like report scaffolding
- preserving existing data sources where possible while changing presentation hierarchy

The preferred implementation path is to treat Today v2 as a focused homepage restructure, not a whole-system rewrite.

## 13. Final Product Statement

Today v2 should be understood as:

`a warm but decisive homepage command board for A-share beginners, where the page gives the command first, shows the environment second, and reveals the evidence only after the user needs it.`
