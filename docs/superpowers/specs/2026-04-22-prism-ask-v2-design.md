# Prism Ask v2 Design

## 1. Document Purpose

This document defines the stage-two surface direction for Prism Ask.

Its job is to turn the recently aligned product choices into a fixed page contract for the Ask surface before implementation starts.

The document focuses on one question:

`What should Prism Ask look like and how should it behave if it is meant to answer one beginner investor question: what should I do with this stock right now?`

This document sits between the broader Prism product strategy and the actual Ask page implementation.
It exists to prevent Ask from drifting back into either a generic chatbot or an overloaded research page.

## 2. Why Ask Needs A v2 Redesign

The current Prism prototype already gives Ask a meaningful role:

- Ask is the single-stock entry point
- Ask can already produce a useful conclusion and supporting detail
- Ask already connects into watchlist, opportunity, and evidence layers

But the current Ask page still carries a structural product problem.

It is clearer than a generic report page, but it still does not fully behave like a strong single-stock judgment page for a beginner user.

The main risks are:

- the page still lets support layers compete too early with the core answer
- the search frame and follow-up behavior still carry too much conversational gravity
- the conclusion is present, but not yet dominant enough to feel like the page's real first answer
- a beginner user can still spend attention navigating the surface instead of feeling immediately told what to do

That is a real product gap.
Prism is not trying to become an open-ended stock chat product.
It is trying to become a beginner-friendly decision system.

Ask therefore needs a deliberate v2 redesign.

## 3. Product Role Of Ask v2

Ask v2 is the single-stock answer surface of Prism.

It is not a market dashboard.
It is not a full research report page.
It is not a general chatbot.

Its product role is:

`Help an A-share beginner ask about one stock and immediately understand whether the answer is buy, hold, sell, or watch, together with the minimum boundary needed to trust that answer.`

This means Ask v2 must optimize for:

- immediate clarity of judgment
- minimal ambiguity in the top answer
- compact trust-building instead of long explanation
- execution framing that follows the answer instead of replacing it
- follow-up interaction as a secondary support layer

The page promise becomes:

`First tell me the answer for this stock. Then tell me why it stands. Then tell me when it stops being true.`

## 4. Core Product Direction

The approved direction for Ask v2 is fixed as follows:

- page type: `single-stock answer surface`
- primary interaction pattern: `conclusion card first`
- first-screen question: `should I buy, sell, hold, or only watch this stock right now?`
- conclusion style: `hard conclusion card`
- supporting pattern: `hard conclusion plus boundary strip`

This combination matters.

It means Ask v2 should feel direct, but not harsh.
It should feel useful, but not chatty.
It should feel trustworthy, but not report-heavy.

## 5. Reading Order Contract

The reading order for Ask v2 is fixed.

The page should guide the user through this sequence:

1. `compact search bar`
2. `hard conclusion card`
3. `boundary trio`
4. `execution layer`
5. `cross-system relation layer`
6. `evidence and follow-up layer`

This is not just a layout preference.
It is a product rule.

Ask must teach the user to consume single-stock judgment in the correct order:

- answer first
- trust boundary second
- action third
- evidence and follow-up later

Any implementation that lets explanation, chat behavior, or cross-system state interrupt that order should be treated as out of spec.

## 6. State Model

Ask v2 should be designed as two clearly different surface states.

### 6.1 Empty State

This is the state before a stock is queried.

Its job is simple:

- accept a code or stock name quickly
- expose recent queries or system suggestions as shortcuts
- communicate a compact promise such as `先给结论，再给边界`

The empty state is search-first.
It should not try to preview the full answer architecture before the user asks a question.

### 6.2 Result State

This is the state after a stock is queried.

Its job is very different:

- keep search available in compact form
- make the conclusion card the visual center
- move support layers below the conclusion hierarchy

The result state is conclusion-first.
That distinction is important and must remain explicit in implementation.

## 7. Page Structure For Result State

Ask v2 result state should be composed of six major blocks.

### 7.1 Compact Search Strip

After a stock has already been queried, search should remain available, but it should no longer dominate the page.

This means:

- the search bar stays visible
- it becomes compact and secondary
- it should not continue to act like the page's hero

The main page hero should become the stock answer, not the input field.

### 7.2 Hard Conclusion Card

This is the most important block on the Ask page.
It owns the first-screen visual center.

Its job is to answer, in the smallest stable language possible:

- `买入`
- `持有`
- `卖出`
- `观察`

The conclusion card may also include one short execution sentence such as:

- `今天先观察，不买`
- `可以继续持有，但不加仓`
- `先卖，别再等反弹`

But the main layer must remain the hard conclusion itself.

This block must feel stronger than any follow-up, explanation, or evidence layer.

### 7.3 Boundary Trio

Immediately below the conclusion card, Ask v2 should show three compact boundary cards:

- `why_now`
- `continue_condition`
- `stop_condition`

User-facing labels should read like:

- `为什么这么判断`
- `继续成立的条件`
- `一票否决条件`

These three cards should be short, legible, and scan-first.
They should not become long text sections.

Their job is to build trust without delaying the answer.

### 7.4 Execution Layer

This block translates the judgment into action.

It should answer:

- `现在做什么`
- `先不要做什么`
- `去哪看证据`

This layer is not the main answer.
It is what the user does after the answer has already been understood.

It should feel like an action checklist, not a research digest.

### 7.5 Cross-System Relation Layer

This layer explains how the current stock relates to the rest of Prism.

Examples include:

- already in holdings
- currently in opportunity workflow
- present in midday observation
- has watchlist or restore actions available

This layer matters for trust and continuity.
But it must remain lower priority than the conclusion card and boundary trio.

It is a support layer, not the top answer.

### 7.6 Evidence And Follow-Up Layer

The lowest-priority section should contain:

- source data links
- cross-system status surfaces
- continued follow-up interaction

Follow-up must stay available.
But it should no longer feel like the page's main mode.

Ask v2 is not a chat-first page.
Follow-up is a secondary support layer after the answer has already been delivered.

## 8. Visual Design Direction

Ask v2 should use a visual language that can be described as:

`direct single-stock answer page`

It should remain clearly related to Today v2, but it should not duplicate Today's geometry.

### 8.1 Shared System Language

Ask v2 should stay in the same family as Today v2.

The preferred shared palette direction is:

- deep navy foundations
- warm gold or amber guidance accents
- controlled green, blue, and red semantic states

This ensures Prism feels like one system instead of separate surfaces.

### 8.2 Ask-Specific Visual Focus

Even within the shared system, Ask must give the greatest visual weight to the conclusion card.

Not to:

- the search bar
- the follow-up panel
- trust messaging
- source blocks

The eye must land on the single-stock answer first.

### 8.3 Boundary Cards Must Feel Like Decision Boundaries

The three boundary cards should not feel like chat bubbles or info cards.

They should feel like compact decision rails:

- short
- sharp
- scannable
- boundary-oriented

The user should read them as decision guardrails, not as mini articles.

### 8.4 Execution Layer Must Feel Actionable

The execution layer should feel like a small action checklist.
It should not behave like a second explanation layer.

That means the visual tone can soften slightly under the conclusion card, but it should still retain command clarity.

### 8.5 Follow-Up Must Visually Retreat

The follow-up section must remain available, but it should visually step back.

It must not:

- look like a primary hero section
- dominate the first screen
- make the user feel they entered a general chat product

Ask v2 should always communicate: `the answer came first, the conversation came after.`

## 9. Interaction Principles

Ask v2 should reduce ambiguity, conversation drift, and support-layer competition.

### 9.1 Default Flow

The intended result-state flow is:

1. see the conclusion card
2. scan the three boundaries
3. understand the action layer
4. inspect cross-system context if needed
5. expand evidence or continue follow-up if needed

The page should not require the user to assemble this decision order themselves.

### 9.2 Hard Answer First

Once a stock result exists, Ask must answer before it explains.

This is a strict rule.
The user should never have to scroll or interpret support context before finding the actual answer.

### 9.3 Follow-Up As Secondary Mode

Follow-up interaction should remain part of the product.
But it must be explicitly secondary.

This means:

- no first-screen chat dominance
- no chat-first layout in result state
- no conversational UI overtaking the conclusion hierarchy

### 9.4 Mobile Behavior

Mobile must preserve judgment order, not desktop geometry.

The mobile result-state order should be:

1. compact search strip
2. hard conclusion card
3. boundary trio
4. execution layer
5. cross-system relation layer
6. evidence and follow-up layer

Mobile does not need to preserve any desktop arrangement beyond that order.

## 10. Boundary Rules

The following constraints are fixed for Ask v2.

### 10.1 Ask Is Not The Daily Command Surface

Ask answers one stock.
It must not absorb the job of Today.

That means no first-screen market-wide command logic, no daily portfolio-wide stance framing, and no attempt to turn Ask into a daily dispatch page.

### 10.2 Ask Is Not A Chatbot Homepage

Ask may support follow-up questions.
It must not behave like a chat-first product.

That means:

- no chat-first result layout
- no oversized conversation shell at the top of result state
- no follow-up panel replacing the answer layer

### 10.3 Ask Is Not A Full Research Page

Ask may explain the answer enough to support action.
It must not become a full research environment on the first screen.

That means avoiding first-screen overload from:

- large metric walls
- long analysis text
- complex source matrices
- report-like explanation blocks

### 10.4 Conclusion Layer And Execution Layer Must Stay Separate

The answer block says what the judgment is.
The execution block says what to do next.

If these are merged, Ask will become less readable and less decisive.

### 10.5 Boundary Trio Must Stay Short

The three boundary cards are required.
But they must remain short and boundary-oriented.

They must not slowly expand into long explanatory copy blocks.

### 10.6 Cross-System Relation Must Stay Below The Answer

Watchlist, opportunity, midday, and restore relations are useful.
But they must not climb above the conclusion hierarchy.

They are trust and continuity layers, not the top answer.

### 10.7 This Iteration Covers Ask First

This redesign may later influence holdings detail, opportunity detail, and related single-stock surfaces.

But this iteration should stay focused on Ask itself.
It should not attempt a simultaneous redesign of every single-stock page in one pass.

## 11. Success Criteria

Ask v2 should be considered successful if it achieves the following outcomes:

- a beginner can immediately see the stock answer as buy, hold, sell, or watch
- the result page feels like a judgment page, not a chatbot page
- the page explains the answer with minimal but sufficient trust boundaries
- the execution layer feels actionable without replacing the answer
- cross-system relation remains visible but secondary
- mobile preserves the same answer-first reading order

## 12. Implementation Implications

This spec implies a medium-scope redesign, not a cosmetic patch.

Expected implementation impact includes:

- restructuring the Ask result-state hero into a hard conclusion-first layout
- demoting the search shell after result load
- replacing broad explanation-first reading patterns with a conclusion-first hierarchy
- extracting or reformatting current support modules into a boundary trio and execution layer
- keeping follow-up interaction available while visually lowering its priority

The preferred implementation path is to treat Ask v2 as the single-stock companion surface to Today v2, not as an isolated one-off redesign.

## 13. Final Product Statement

Ask v2 should be understood as:

`a direct, answer-first single-stock judgment page for A-share beginners, where the page states buy, hold, sell, or watch before it explains anything else, and where follow-up exists only as support after the answer is already clear.`
