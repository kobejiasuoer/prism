# Prism Today v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Prism Today homepage into a warm, strong-command decision surface with a left-command/right-radar hero, holdings-before-opportunities sequencing, and secondary evidence disclosure.

**Architecture:** Keep the existing FastAPI + Jinja Today page architecture, but refactor the Today view-model and template hierarchy so the homepage becomes a real command board instead of a report-like summary surface. Reuse existing data sources and decision-row components where possible, introduce only the Today-specific view-model fields and CSS needed for the new command hero, evidence hint strip, and responsive mobile stacking.

**Tech Stack:** Python, FastAPI, Jinja templates, vanilla CSS, `unittest` smoke tests with `fastapi.testclient`

---

## File Structure

### Existing files to modify

- `apps/control-panel/dashboard_data.py`
  Responsibility: reshape the Today page view-model, add a dedicated command-hero payload, build radar cards, demote evidence to a hint strip, and keep holdings/opportunities/risk/evidence sections aligned to the approved reading order.
- `apps/control-panel/templates/today.html`
  Responsibility: replace the current Today layout with the Today v2 command-board structure and preserve the evidence fold as a lower-priority inspection layer.
- `apps/control-panel/static/control-panel.css`
  Responsibility: add the Today v2 hero, command bar, radar card, evidence hint strip, and mobile stacking styles while preserving the rest of the site.
- `apps/control-panel/tests/test_app_smoke.py`
  Responsibility: lock the Today v2 reading order, headline copy, component visibility, and evidence demotion behavior with HTML contract tests.

### Existing files to touch lightly

- `docs/superpowers/specs/2026-04-22-prism-today-v2-design.md`
  Responsibility: reference only if implementation reveals a genuine mismatch. Do not expand scope during implementation.

### No new backend modules in this pass

Keep the Today v2 work inside the existing `dashboard_data.py` composition layer first. Do not split into a new domain module during this implementation unless the file becomes unworkably tangled while executing the plan.

### No full-site redesign in this pass

Do not modify Ask, Watchlist, Opportunities, Review, or shared nav copy as part of this implementation plan. Today v2 is the sample surface.

## Task 1: Lock The Today v2 HTML Contract With Failing Tests

**Files:**
- Modify: `apps/control-panel/tests/test_app_smoke.py`
- Reference: `docs/superpowers/specs/2026-04-22-prism-today-v2-design.md`

- [ ] **Step 1: Add a failing smoke test for the Today v2 command-board structure**

```python
def test_today_page_uses_command_board_hero_and_demotes_evidence(self) -> None:
    response = self.client.get("/today")
    self.assertEqual(response.status_code, 200)
    html = response.text

    self.assertIn("今日作战指令", html)
    self.assertIn("立即执行", html)
    self.assertIn("明确回避", html)
    self.assertIn("仓位上限", html)
    self.assertIn("午盘观察", html)
    self.assertIn("今日判断已综合", html)
    self.assertIn("证据与原始入口", html)

    self.assertNotIn("今日总判断", html)
    self.assertNotIn("今日三大动作", html)
    self.assertNotIn("证据来源</strong>", html)
    self.assertNotIn("来源快照</h3>", html)
```

- [ ] **Step 2: Add a failing smoke test for Today v2 reading order**

```python
def test_today_page_reads_command_then_holdings_then_opportunities(self) -> None:
    response = self.client.get("/today")
    self.assertEqual(response.status_code, 200)
    html = response.text

    command_index = html.find("今日作战指令")
    holdings_index = html.find("持仓动作")
    opportunities_index = html.find("机会动作")
    evidence_hint_index = html.find("今日判断已综合")
    evidence_fold_index = html.find("证据与原始入口")

    self.assertGreaterEqual(command_index, 0)
    self.assertGreaterEqual(holdings_index, 0)
    self.assertGreaterEqual(opportunities_index, 0)
    self.assertGreaterEqual(evidence_hint_index, 0)
    self.assertGreaterEqual(evidence_fold_index, 0)

    self.assertLess(command_index, holdings_index)
    self.assertLess(holdings_index, opportunities_index)
    self.assertLess(opportunities_index, evidence_hint_index)
    self.assertLess(evidence_hint_index, evidence_fold_index)
```

- [ ] **Step 3: Add a failing smoke test for Today v2 mobile-safe radar and action labels**

```python
def test_today_page_exposes_command_and_radar_labels_without_report_copy(self) -> None:
    response = self.client.get("/today")
    self.assertEqual(response.status_code, 200)
    html = response.text

    required_labels = [
        "今日作战指令",
        "立即执行",
        "等触发",
        "明确回避",
        "仓位上限",
        "主线方向",
        "今日风险",
        "午盘观察",
    ]
    forbidden_labels = [
        "今日总判断",
        "优先动作",
        "来源摘要",
        "来源快照",
    ]

    for label in required_labels:
        self.assertIn(label, html)
    for label in forbidden_labels:
        self.assertNotIn(label, html)
```

- [ ] **Step 4: Run only the new Today v2 smoke tests to verify they fail**

Run:
```bash
./.venv/bin/pytest -q apps/control-panel/tests/test_app_smoke.py -k "today_page_uses_command_board_hero or today_page_reads_command_then_holdings_then_opportunities or today_page_exposes_command_and_radar_labels_without_report_copy"
```

Expected: FAIL because the current Today page still renders the old `今日总判断` and `今日三大动作` structure.

- [ ] **Step 5: Commit the failing tests**

```bash
git add apps/control-panel/tests/test_app_smoke.py
git commit -m "test: lock today v2 command board contract"
```

## Task 2: Build The Today v2 View-Model In The Data Layer

**Files:**
- Modify: `apps/control-panel/dashboard_data.py`
- Test: `apps/control-panel/tests/test_app_smoke.py`

- [ ] **Step 1: Add a builder for the Today command hero payload**

Insert near the existing Today helpers in `apps/control-panel/dashboard_data.py`:

```python
def build_today_command_hero(
    *,
    trade_date: str,
    hero: dict[str, Any],
    top_rows: list[dict[str, Any]],
    brief_is_live: bool,
) -> dict[str, Any]:
    execute_now = next((row for row in top_rows if (row.get("tier_key") or "") == "act_now"), None)
    wait_trigger = next((row for row in top_rows if (row.get("tier_key") or "") == "wait_trigger"), None)
    avoid_row = next((row for row in top_rows if (row.get("tier_key") or "") == "avoid"), None)

    def hero_row(
        label: str,
        fallback_title: str,
        source: dict[str, Any] | None,
        tone: str,
    ) -> dict[str, Any]:
        return {
            "label": label,
            "title": str((source or {}).get("action") or fallback_title),
            "detail": str((source or {}).get("reason") or (source or {}).get("trigger") or "等待链路进一步确认。"),
            "tone": tone,
            "tier": str((source or {}).get("tier") or label),
            "url": str((source or {}).get("url") or ""),
        }

    return {
        "eyebrow": "今日作战指令",
        "title": str(hero.get("title") or "先处理已有仓位，再决定要不要看新机会"),
        "summary": str(hero.get("summary") or "今天先按优先级执行，不做无计划扩张。"),
        "trade_date": trade_date,
        "context_note": str(hero.get("context_note") or ""),
        "source_state": "总控已同步" if brief_is_live else "实时链路判断",
        "actions": [
            hero_row("立即执行", "先处理最弱持仓", execute_now, "positive"),
            hero_row("等触发", "只盯最强机会，不抢跑", wait_trigger, "watch"),
            hero_row("明确回避", "今天不追高", avoid_row, "risk"),
        ],
    }
```

- [ ] **Step 2: Add a builder for the Today radar cards**

Insert near the Today helper group in `apps/control-panel/dashboard_data.py`:

```python
def build_today_radar_cards(
    *,
    position_cap: str,
    main_theme: str,
    quality_ok: int,
    confirmation_counts: dict[str, Any],
    brief_is_live: bool,
) -> list[dict[str, str]]:
    risk_value = "低" if quality_ok >= 3 and brief_is_live else ("中" if quality_ok >= 2 else "中偏高")
    risk_note = "链路完整，可按纪律执行" if risk_value == "低" else ("先控仓，再等更清晰确认" if risk_value == "中" else "今天先守纪律，不做激进动作")
    midday_fresh = int(confirmation_counts.get("fresh_candidates") or 0)
    midday_note = "暂无新增观察" if midday_fresh <= 0 else f"新增观察 {midday_fresh} 项"

    return [
        {
            "label": "仓位上限",
            "value": position_cap or "-",
            "note": "今天最多能承受的动作空间",
        },
        {
            "label": "主线方向",
            "value": main_theme or "暂无主线",
            "note": "先只围绕最强方向行动",
        },
        {
            "label": "今日风险",
            "value": risk_value,
            "note": risk_note,
        },
        {
            "label": "午盘观察",
            "value": str(midday_fresh),
            "note": midday_note,
        },
    ]
```

- [ ] **Step 3: Add a builder for the first-screen evidence hint strip**

Insert near the Today helper group in `apps/control-panel/dashboard_data.py`:

```python
def build_today_evidence_hint(*, brief_is_live: bool, source_cards: list[dict[str, Any]]) -> dict[str, str]:
    source_labels = "、".join(item.get("label") or "" for item in source_cards[:3] if item.get("label"))
    if not source_labels:
        source_labels = "自选股快照、早盘批次与午盘确认"
    suffix = "总控判断已同步。" if brief_is_live else "当前以实时链路为准。"
    return {
        "title": "今日判断已综合",
        "summary": f"今日判断已综合{source_labels}。{suffix}",
        "cta": "查看证据与原始入口",
        "target": "today-evidence-fold",
    }
```

- [ ] **Step 4: Wire the new Today v2 fields into `build_today_view()`**

Update the Today return payload in `apps/control-panel/dashboard_data.py` so it contains the new fields and no longer depends on `action_tier_legend` or `topline` for the Today hero:

```python
    command_hero = build_today_command_hero(
        trade_date=trade_date,
        hero={
            "title": hero_title,
            "summary": hero_summary,
            "context_note": context_note,
        },
        top_rows=top_rows,
        brief_is_live=brief_is_live,
    )
    radar_cards = build_today_radar_cards(
        position_cap=position_cap,
        main_theme=main_theme,
        quality_ok=quality_ok,
        confirmation_counts=confirmation_counts,
        brief_is_live=brief_is_live,
    )
    evidence_hint = build_today_evidence_hint(
        brief_is_live=brief_is_live,
        source_cards=source_cards,
    )

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "trade_date": trade_date,
        "brief_is_live": brief_is_live,
        "hero": {
            "title": hero_title,
            "summary": hero_summary,
            "gate_label": hero_gate_label,
            "position_cap": position_cap,
            "main_theme": main_theme,
            "context_note": context_note,
        },
        "command_hero": command_hero,
        "radar_cards": radar_cards,
        "evidence_hint": evidence_hint,
        "action_groups": action_groups,
        "action_queue": action_queue,
        "primary_actions": primary_actions,
        "holdings_rows": holdings_rows,
        "opportunity_rows": opportunity_rows,
        "risk_rows": risk_rows,
        "evidence_rows": evidence_rows,
        "confidence_switch": build_today_confidence_switch(
            decision_brief,
            quality_status,
            brief_is_live=brief_is_live,
            gate=gate,
            links=links,
        ),
        "change_view": change_view,
        "source_cards": source_cards,
        "summary_cards": summary_cards,
        "watchlist_cards": pick_watchlist_cards(watchlist),
        "opportunity_cards": pick_opportunity_cards(screening_batch),
        "midday_cards": pick_midday_cards(confirmation),
        "quality_cards": quality_lane_cards(quality_status),
        "artifacts": artifacts,
        "links": links,
        "counts": {
            "watchlist_priority": watchlist_priority,
            "watchlist_total": (watchlist or {}).get("stock_count") or 0,
            "opportunities": screening_summary.get("approved_count") or screening_summary.get("shortlisted_count") or 0,
            "midday_fresh": confirmation_counts.get("fresh_candidates") or 0,
        },
    }
```

- [ ] **Step 5: Run the focused Today v2 smoke tests to verify the data contract is now sufficient for the template rewrite**

Run:
```bash
./.venv/bin/pytest -q apps/control-panel/tests/test_app_smoke.py -k "today_page_uses_command_board_hero or today_page_reads_command_then_holdings_then_opportunities or today_page_exposes_command_and_radar_labels_without_report_copy"
```

Expected: still FAIL, but the failures should now point primarily at template copy/layout rather than missing Today payload fields.

- [ ] **Step 6: Commit the Today v2 data-layer changes**

```bash
git add apps/control-panel/dashboard_data.py
git commit -m "feat: add today v2 command board payload"
```

## Task 3: Replace The Today Template With The Command Board Layout

**Files:**
- Modify: `apps/control-panel/templates/today.html`
- Modify: `apps/control-panel/tests/test_app_smoke.py`

- [ ] **Step 1: Rewrite the Today hero section to use the command hero and radar cards**

Replace the top of `<main class="today-dispatch-main today-command-main">` in `apps/control-panel/templates/today.html` with:

```jinja2
      <main class="today-dispatch-main today-command-main">
        <section class="today-command-board stage-decision-layer">
          <div class="today-command-board-main">
            <div class="today-command-hero">
              <p class="eyebrow">{{ today.command_hero.eyebrow }}</p>
              <h1 class="today-command-title">{{ today.command_hero.title }}</h1>
              <p class="today-command-summary">{{ today.command_hero.summary }}</p>
              <div class="today-command-meta">
                <span class="detail-tag">{{ today.command_hero.source_state }}</span>
                <span class="detail-tag">交易日 {{ today.trade_date }}</span>
              </div>
              <div class="today-command-actions">
                {% for item in today.command_hero.actions %}
                <article class="today-command-action today-command-action-{{ item.tone }}">
                  <span class="today-command-action-label">{{ item.label }}</span>
                  <strong>{{ item.title }}</strong>
                  <p>{{ item.detail }}</p>
                  {% if item.url %}
                  <a href="{{ item.url }}">查看对象</a>
                  {% endif %}
                </article>
                {% endfor %}
              </div>
            </div>
            <aside class="today-command-radar">
              {% for card in today.radar_cards %}
              <article class="today-radar-card">
                <span>{{ card.label }}</span>
                <strong>{{ card.value }}</strong>
                <p>{{ card.note }}</p>
              </article>
              {% endfor %}
            </aside>
          </div>
        </section>
```

- [ ] **Step 2: Replace the old top action and legend sections with the approved holdings-first body**

Continue the rewritten `today.html` main body with:

```jinja2
        <section class="today-quality-block today-dispatch-block stage-decision-layer">
          <div class="section-head">
            <div>
              <p class="eyebrow">持仓</p>
              <h2>持仓动作</h2>
            </div>
          </div>
          {% set decision_rows = today.holdings_rows %}
          {% include "_decision_rows.html" %}
        </section>

        <section class="today-quality-block today-dispatch-block stage-decision-layer">
          <div class="section-head">
            <div>
              <p class="eyebrow">机会</p>
              <h2>机会动作</h2>
            </div>
          </div>
          {% set decision_rows = today.opportunity_rows %}
          {% include "_decision_rows.html" %}
        </section>

        <details class="progressive-section">
          <summary class="progressive-summary">
            <div class="progressive-summary-main">
              <p class="eyebrow">风险层</p>
              <strong>风险与变更</strong>
            </div>
            <span class="progressive-summary-note">展开午盘变化与关键边界</span>
          </summary>
          <div class="progressive-body">
            {% set decision_rows = today.risk_rows %}
            {% include "_decision_rows.html" %}
          </div>
        </details>

        <section class="today-evidence-hint stage-action-layer">
          <div>
            <p class="eyebrow">{{ today.evidence_hint.title }}</p>
            <p class="today-evidence-hint-copy">{{ today.evidence_hint.summary }}</p>
          </div>
          <a class="ghost-button link-button" href="#{{ today.evidence_hint.target }}">{{ today.evidence_hint.cta }}</a>
        </section>
```

- [ ] **Step 3: Rename the evidence fold and keep all existing evidence internals below the fold**

Update the evidence `<details>` in `apps/control-panel/templates/today.html` to:

```jinja2
        <details id="today-evidence-fold" class="progressive-section">
          <summary class="progressive-summary">
            <div class="progressive-summary-main">
              <p class="eyebrow">证据层</p>
              <strong>证据与原始入口</strong>
            </div>
            <span class="progressive-summary-note">展开刷新状态、来源快照、质检与原始入口</span>
          </summary>
```

Inside that fold, keep the existing refresh strip, source snapshots, quality cards, and raw artifact links. Do not reintroduce first-screen evidence cards.

- [ ] **Step 4: Run the focused Today v2 smoke tests again**

Run:
```bash
./.venv/bin/pytest -q apps/control-panel/tests/test_app_smoke.py -k "today_page_uses_command_board_hero or today_page_reads_command_then_holdings_then_opportunities or today_page_exposes_command_and_radar_labels_without_report_copy"
```

Expected: PASS after the template is aligned to the new copy and structure.

- [ ] **Step 5: Commit the Today template rewrite**

```bash
git add apps/control-panel/templates/today.html apps/control-panel/tests/test_app_smoke.py
git commit -m "feat: reshape today into command board layout"
```

## Task 4: Add The Today v2 Visual System And Mobile Stack

**Files:**
- Modify: `apps/control-panel/static/control-panel.css`
- Test: `apps/control-panel/tests/test_app_smoke.py`

- [ ] **Step 1: Add the Today v2 command board, hero, action, radar, and evidence hint styles**

Append near the existing Today styles in `apps/control-panel/static/control-panel.css`:

```css
.today-command-board {
  padding: 1.1rem;
  border-radius: 1.35rem;
  border: 1px solid rgba(250, 204, 21, 0.14);
  background:
    radial-gradient(circle at top right, rgba(250, 204, 21, 0.12), transparent 18rem),
    linear-gradient(145deg, rgba(22, 36, 58, 0.94), rgba(10, 18, 31, 0.96));
  box-shadow: 0 24px 70px rgba(15, 23, 42, 0.38);
}

.today-command-board-main {
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) minmax(18rem, 0.9fr);
  gap: 1rem;
}

.today-command-hero {
  display: grid;
  gap: 0.9rem;
}

.today-command-title {
  margin: 0;
  font-family: var(--font-display);
  font-size: clamp(1.85rem, 4vw, 2.8rem);
  line-height: 1.04;
  letter-spacing: -0.04em;
  color: var(--text);
}

.today-command-summary {
  margin: 0;
  max-width: 44rem;
  color: rgba(241, 245, 249, 0.8);
  line-height: 1.62;
}

.today-command-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.today-command-actions {
  display: grid;
  gap: 0.7rem;
}

.today-command-action {
  display: grid;
  gap: 0.35rem;
  padding: 0.95rem 1rem;
  border-radius: 1rem;
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: rgba(255, 255, 255, 0.035);
}

.today-command-action-label {
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.08em;
}

.today-command-action-positive {
  border-color: rgba(74, 222, 128, 0.24);
  background: rgba(34, 197, 94, 0.08);
}

.today-command-action-watch {
  border-color: rgba(250, 204, 21, 0.2);
  background: rgba(250, 204, 21, 0.08);
}

.today-command-action-risk {
  border-color: rgba(248, 113, 113, 0.22);
  background: rgba(239, 68, 68, 0.08);
}

.today-command-radar {
  display: grid;
  gap: 0.75rem;
  align-content: start;
}

.today-radar-card {
  padding: 0.95rem 1rem;
  border-radius: 1rem;
  border: 1px solid rgba(255, 248, 220, 0.12);
  background: rgba(255, 248, 220, 0.05);
}

.today-radar-card span {
  display: block;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: rgba(247, 199, 91, 0.9);
}

.today-radar-card strong {
  display: block;
  margin-top: 0.45rem;
  font-size: 1.2rem;
  color: var(--text);
}

.today-radar-card p {
  margin: 0.45rem 0 0;
  color: var(--text-soft);
  line-height: 1.55;
}

.today-evidence-hint {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.9rem 1rem;
  border-radius: 1rem;
  border: 1px solid rgba(250, 204, 21, 0.14);
  background: rgba(250, 204, 21, 0.06);
}

.today-evidence-hint-copy {
  margin: 0.3rem 0 0;
  color: var(--text-soft);
  line-height: 1.58;
}
```

- [ ] **Step 2: Add the mobile layout override for the command board**

Extend the responsive section in `apps/control-panel/static/control-panel.css` with:

```css
@media (max-width: 1080px) {
  .today-command-board-main {
    grid-template-columns: 1fr;
  }

  .today-command-title {
    font-size: clamp(1.55rem, 8vw, 2.2rem);
  }

  .today-evidence-hint {
    flex-direction: column;
    align-items: flex-start;
  }
}
```

- [ ] **Step 3: Add the light-theme overrides so Today v2 still feels deliberate outside dark mode**

Append near the existing light-mode Today overrides in `apps/control-panel/static/control-panel.css`:

```css
html[data-theme-applied="light"] .today-command-board {
  border-color: rgba(214, 180, 74, 0.24);
  background:
    radial-gradient(circle at top right, rgba(250, 204, 21, 0.16), transparent 18rem),
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(246, 248, 252, 0.96));
  box-shadow: 0 18px 42px rgba(148, 163, 184, 0.18);
}

html[data-theme-applied="light"] .today-command-title {
  color: #17283d;
}

html[data-theme-applied="light"] .today-command-summary,
html[data-theme-applied="light"] .today-radar-card p,
html[data-theme-applied="light"] .today-evidence-hint-copy {
  color: #475569;
}

html[data-theme-applied="light"] .today-radar-card {
  background: rgba(255, 248, 220, 0.34);
  border-color: rgba(214, 180, 74, 0.2);
}

html[data-theme-applied="light"] .today-evidence-hint {
  background: rgba(250, 204, 21, 0.1);
  border-color: rgba(214, 180, 74, 0.18);
}
```

- [ ] **Step 4: Run the Today-focused smoke tests and then the full repo smoke suite**

Run:
```bash
./.venv/bin/pytest -q apps/control-panel/tests/test_app_smoke.py -k "today_page"
./.venv/bin/pytest -q apps/control-panel/tests/test_app_smoke.py tests/test_secret_scrub.py
```

Expected: PASS. The first command verifies the Today-focused contracts; the second confirms that the broader smoke suite still holds.

- [ ] **Step 5: Commit the Today v2 visual system**

```bash
git add apps/control-panel/static/control-panel.css
git commit -m "feat: add today v2 command board styling"
```

## Task 5: Final Verification And Product Cleanup

**Files:**
- Modify: `apps/control-panel/tests/test_app_smoke.py` if minor assertion cleanup is still needed
- Verify: `apps/control-panel/dashboard_data.py`
- Verify: `apps/control-panel/templates/today.html`
- Verify: `apps/control-panel/static/control-panel.css`

- [ ] **Step 1: Run a final high-signal verification pass across the exact implementation surface**

Run:
```bash
./.venv/bin/pytest -q apps/control-panel/tests/test_app_smoke.py -k "today_page or primary_navigation_uses_stage_one_labels"
```

Expected: PASS, confirming the Today v2 structure coexists with the existing navigation contract.

- [ ] **Step 2: Run the complete smoke suite one final time**

Run:
```bash
./.venv/bin/pytest -q
```

Expected: PASS for the repo smoke tests configured by `pyproject.toml`.

- [ ] **Step 3: Review the rendered Today page in the local app and confirm the implementation matches the spec**

Manual checklist:

- the hero reads as `今日作战指令`, not `今日总判断`
- the left side visually dominates with one command sentence and three command bars
- the right side contains four radar cards only
- holdings appears before opportunities
- evidence is first seen as a lightweight hint strip
- full evidence remains behind the `证据与原始入口` fold
- mobile stacks command, actions, radar, then deeper sections in that order

- [ ] **Step 4: Commit any final assertion or copy cleanup triggered by verification**

```bash
git add apps/control-panel/tests/test_app_smoke.py apps/control-panel/dashboard_data.py apps/control-panel/templates/today.html apps/control-panel/static/control-panel.css
git commit -m "chore: finalize today v2 verification"
```
