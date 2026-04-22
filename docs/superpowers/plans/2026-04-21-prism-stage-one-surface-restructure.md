# Prism Stage-One Surface Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reshape Prism's stage-one control-panel product surfaces so Today becomes the main daily decision desk, Ask becomes a decision-card-first stock inquiry surface, and internal operations tooling is clearly separated from the beginner-facing product.

**Architecture:** Keep the existing FastAPI + Jinja control-panel architecture, but refactor the page data builders and templates around the new product hierarchy. Use the existing `dashboard_data.py` composition layer as the main adapter, add only small focused helpers where needed, and protect the restructure with smoke tests for route contracts, navigation labels, and key content ordering.

**Tech Stack:** Python, FastAPI, Jinja templates, vanilla JavaScript, repo smoke tests with `unittest` + `fastapi.testclient`

---

## File Structure

### Existing files to modify

- `apps/control-panel/dashboard_data.py`
  Responsibility: Builds page view-models for Today, Ask, Watchlist, Opportunities, Review, and ops overview. This is the main place to reshape content hierarchy without spreading product logic across templates.
- `apps/control-panel/templates/today.html`
  Responsibility: Render the Today page. Needs to reflect the chosen structure: command-center foundation with action-feed reading order.
- `apps/control-panel/templates/ask.html`
  Responsibility: Render the Ask page. Needs to preserve stock inquiry behavior while reordering the page to show decision card first and follow-up as a support layer.
- `apps/control-panel/templates/_page_nav.html`
  Responsibility: Primary navigation shared across user-facing surfaces. Needs final stage-one labels and a clearer split between main product pages and the internal ops console.
- `apps/control-panel/templates/dashboard.html`
  Responsibility: Internal ops console. May need copy and navigation adjustments so it clearly reads as a control surface rather than a peer to Today.
- `apps/control-panel/static/control-panel.css`
  Responsibility: Shared page styling. Needs style adjustments for the restructured Today and Ask sections plus any updated nav/ops presentation.
- `apps/control-panel/static/control-panel-ask.js`
  Responsibility: Ask page interactivity. Should be reviewed so the restructured Ask surface still supports suggestions, submission, and follow-up without broken selectors.
- `apps/control-panel/tests/test_app_smoke.py`
  Responsibility: End-to-end HTML contract and behavior smoke coverage. Needs new tests for the updated structure and copy.

### Existing files to touch lightly

- `apps/control-panel/app.py`
  Responsibility: Route assembly only. Expect minimal or no structural changes, but keep available if any page naming or route metadata requires cleanup.
- `.gitignore`
  Responsibility: Already updated to ignore `.superpowers/`; keep staged if this plan is executed from the current working tree.
- `docs/superpowers/specs/2026-04-21-prism-product-design.md`
  Responsibility: Canonical product spec. Only update if implementation reveals a mismatch that needs formal spec correction.

### No new backend modules unless necessary

Avoid creating new backend files unless `dashboard_data.py` becomes unmanageably hard to update in-place. First attempt should be focused helper extraction inside the existing file.

## Task 1: Lock Navigation And Product Surface Vocabulary

**Files:**
- Modify: `apps/control-panel/templates/_page_nav.html`
- Modify: `apps/control-panel/templates/dashboard.html`
- Modify: `apps/control-panel/tests/test_app_smoke.py`

- [ ] **Step 1: Write the failing smoke test for primary navigation labels and ops separation**

```python
def test_primary_navigation_uses_stage_one_labels_and_keeps_ops_separate(self) -> None:
    response = self.client.get("/today")
    self.assertEqual(response.status_code, 200)
    html = response.text
    self.assertIn("今日", html)
    self.assertIn("问股", html)
    self.assertIn("持仓", html)
    self.assertIn("机会", html)
    self.assertIn("复盘", html)
    self.assertIn("控制台", html)
    self.assertNotIn("自选股</a>", html)
    self.assertNotIn("机会池</a>", html)
```

- [ ] **Step 2: Run the new navigation smoke test to verify it fails on current copy**

Run: `pytest apps/control-panel/tests/test_app_smoke.py -k "primary_navigation_uses_stage_one_labels" -v`
Expected: FAIL because the current nav still renders `自选股` and `机会池`.

- [ ] **Step 3: Update the shared navigation template to use stage-one product language**

```jinja2
<nav class="today-nav stage-nav" aria-label="主导航">
  <div class="nav-brand">
    <span>棱镜</span>
    <strong>交易决策台</strong>
  </div>
  <div class="nav-chip-row">
    <a class="nav-chip {% if nav_active == 'today' %}nav-chip-active{% endif %}" href="{{ nav_links.today }}" {% if nav_active == 'today' %}aria-current="page"{% endif %}>今日</a>
    <a class="nav-chip {% if nav_active == 'ask' %}nav-chip-active{% endif %}" href="{{ nav_links.ask }}" {% if nav_active == 'ask' %}aria-current="page"{% endif %}>问股</a>
    <a class="nav-chip {% if nav_active == 'watchlist' %}nav-chip-active{% endif %}" href="{{ nav_links.watchlist }}" {% if nav_active == 'watchlist' %}aria-current="page"{% endif %}>持仓</a>
    <a class="nav-chip {% if nav_active == 'opportunities' %}nav-chip-active{% endif %}" href="{{ nav_links.opportunities }}" {% if nav_active == 'opportunities' %}aria-current="page"{% endif %}>机会</a>
    <a class="nav-chip {% if nav_active == 'review' %}nav-chip-active{% endif %}" href="{{ nav_links.review }}" {% if nav_active == 'review' %}aria-current="page"{% endif %}>复盘</a>
  </div>
  <div class="nav-tools">
    <a class="nav-ops-link {% if nav_active == 'ops' %}nav-ops-link-active{% endif %}" href="{{ nav_links.ops }}" {% if nav_active == 'ops' %}aria-current="page"{% endif %}>控制台</a>
    {% if show_api_link and nav_api_href %}
    <a class="nav-ops-link nav-ops-link-meta" href="{{ nav_api_href }}" target="_blank" rel="noopener">接口</a>
    {% endif %}
    {% if preview_theme == "ibm-preview" %}
    <span class="nav-preview-badge" role="note" aria-label="IBM 预览">IBM 预览</span>
    <a class="nav-ops-link nav-preview-exit" href="{{ preview_theme_exit_url }}">退出试版</a>
    {% endif %}
    {% include "_theme_toggle.html" %}
  </div>
</nav>
{% include "_stage_flow.html" %}
```

- [ ] **Step 4: Tighten the dashboard copy so it reads as an internal console, not a peer home page**

```jinja2
<header class="dashboard-ops-header">
  <div class="dashboard-ops-copy">
    <p class="eyebrow">控制台</p>
    <h1>系统健康</h1>
    <p class="hero-copy">这是内部控制台。先看系统健康、失败或阻塞任务，再决定要不要手动重跑。这里不做投资判断，只确认系统有没有卡住。</p>
    {% if preview_theme == "ibm-preview" %}
    <div class="preview-theme-banner" role="note" aria-label="IBM 预览">
      <span>{{ preview_theme_label }}</span>
      <strong>只做视觉试版，不替换默认主题</strong>
      <p>当前先覆盖控制台和问股页，验证棱镜是否适合更强系统感和更高秩序度。</p>
    </div>
    {% endif %}
  </div>
```

- [ ] **Step 5: Run the navigation smoke test again**

Run: `pytest apps/control-panel/tests/test_app_smoke.py -k "primary_navigation_uses_stage_one_labels" -v`
Expected: PASS

- [ ] **Step 6: Commit the navigation vocabulary pass**

```bash
git add apps/control-panel/templates/_page_nav.html apps/control-panel/templates/dashboard.html apps/control-panel/tests/test_app_smoke.py
git commit -m "feat: align stage-one navigation labels"
```

## Task 2: Restructure Today Into A Decision Desk

**Files:**
- Modify: `apps/control-panel/dashboard_data.py`
- Modify: `apps/control-panel/templates/today.html`
- Modify: `apps/control-panel/static/control-panel.css`
- Test: `apps/control-panel/tests/test_app_smoke.py`

- [ ] **Step 1: Write the failing smoke test for the new Today information order**

```python
def test_today_page_prioritizes_stance_top_actions_and_structured_sections(self) -> None:
    response = self.client.get("/today")
    self.assertEqual(response.status_code, 200)
    html = response.text
    self.assertIn("今日总判断", html)
    self.assertIn("今日三大动作", html)
    self.assertIn("持仓动作", html)
    self.assertIn("机会动作", html)
    self.assertIn("风险与变更", html)
    self.assertIn("证据来源", html)
    self.assertNotIn("下一步动作", html)
    self.assertNotIn("状态细栏", html)
```

- [ ] **Step 2: Run the Today smoke test to verify it fails on the current template**

Run: `pytest apps/control-panel/tests/test_app_smoke.py -k "today_page_prioritizes_stance_top_actions" -v`
Expected: FAIL because the current Today page still renders `下一步动作` and `状态细栏`.

- [ ] **Step 3: Add focused Today view-model helpers inside `dashboard_data.py`**

```python
def build_today_primary_actions(top_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return top_rows[:3]


def build_today_holdings_rows(action_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group in action_groups:
        if group.get("key") != "watchlist":
            continue
        rows.extend(group.get("items") or [])
    return rows[:6]


def build_today_opportunity_rows(action_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group in action_groups:
        if group.get("key") not in {"screening", "confirmation"}:
            continue
        rows.extend(group.get("items") or [])
    return rows[:6]
```

- [ ] **Step 4: Extend `build_today_view()` with explicit stage-one sections**

```python
primary_actions = build_today_primary_actions(top_rows)
holdings_rows = build_today_holdings_rows(action_groups)
opportunity_rows = build_today_opportunity_rows(action_groups)

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
    "primary_actions": primary_actions,
    "holdings_rows": holdings_rows,
    "opportunity_rows": opportunity_rows,
    "risk_change_rows": (change_view.get("groups") or []),
    "evidence_cards": source_cards,
    "action_groups": action_groups,
    "action_queue": action_queue,
    "topline": topline,
    "links": links,
    ...
}
```

- [ ] **Step 5: Replace the Today template structure with the approved page order**

```jinja2
<main class="today-dispatch-main today-command-main">
  <section class="today-quality-block today-dispatch-block stage-decision-layer">
    <div class="section-head">
      <div>
        <p class="eyebrow">今日总判断</p>
        <h2>{{ today.hero.title }}</h2>
      </div>
    </div>
    <p class="today-panel-copy">{{ today.hero.summary }}</p>
    <div class="detail-tag-list">
      <span class="detail-tag">{{ today.hero.gate_label }}</span>
      <span class="detail-tag">仓位上限 {{ today.hero.position_cap }}</span>
      <span class="detail-tag">主线 {{ today.hero.main_theme }}</span>
    </div>
  </section>

  <section class="today-quality-block today-dispatch-block stage-decision-layer">
    <div class="section-head">
      <div>
        <p class="eyebrow">优先动作</p>
        <h2>今日三大动作</h2>
      </div>
    </div>
    {% set decision_rows = today.primary_actions %}
    {% include "_decision_rows.html" %}
  </section>

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
```

- [ ] **Step 6: Move risk/change and evidence into lower-priority progressive sections**

```jinja2
<details class="progressive-section">
  <summary class="progressive-summary">
    <div class="progressive-summary-main">
      <p class="eyebrow">风险层</p>
      <strong>风险与变更</strong>
    </div>
    <span class="progressive-summary-note">展开午盘变化与关键边界</span>
  </summary>
  <div class="progressive-body">
    {% for group in today.risk_change_rows %}
    <article class="today-quality-block">
      <div class="section-head">
        <div>
          <p class="eyebrow">变化</p>
          <h3>{{ group.title }}</h3>
        </div>
      </div>
      <p class="today-panel-copy">{{ group.subtitle }}</p>
    </article>
    {% endfor %}
  </div>
</details>

<details class="progressive-section">
  <summary class="progressive-summary">
    <div class="progressive-summary-main">
      <p class="eyebrow">证据层</p>
      <strong>证据来源</strong>
    </div>
    <span class="progressive-summary-note">展开来源、刷新和原始入口</span>
  </summary>
```

- [ ] **Step 7: Add minimal CSS hooks for the new Today hierarchy without redoing the whole stylesheet**

```css
.today-command-main {
  display: grid;
  gap: 20px;
}

.today-command-main .today-quality-block {
  scroll-margin-top: 96px;
}

.today-command-main .detail-tag-list {
  margin-top: 14px;
}
```

- [ ] **Step 8: Run the Today smoke test again**

Run: `pytest apps/control-panel/tests/test_app_smoke.py -k "today_page_prioritizes_stance_top_actions" -v`
Expected: PASS

- [ ] **Step 9: Commit the Today restructure**

```bash
git add apps/control-panel/dashboard_data.py apps/control-panel/templates/today.html apps/control-panel/static/control-panel.css apps/control-panel/tests/test_app_smoke.py
git commit -m "feat: restructure today as decision desk"
```

## Task 3: Restructure Ask Into Decision-Card-First Flow

**Files:**
- Modify: `apps/control-panel/dashboard_data.py`
- Modify: `apps/control-panel/templates/ask.html`
- Modify: `apps/control-panel/static/control-panel.css`
- Modify: `apps/control-panel/static/control-panel-ask.js`
- Test: `apps/control-panel/tests/test_app_smoke.py`

- [ ] **Step 1: Write the failing Ask smoke test for decision-card-first ordering**

```python
def test_ask_page_uses_decision_card_first_and_followup_as_support(self) -> None:
    response = self.client.get("/ask?q=600690")
    self.assertEqual(response.status_code, 200)
    html = response.text
    self.assertIn("单票决策", html)
    self.assertIn("当前结论", html)
    self.assertIn("为什么这么判断", html)
    self.assertIn("最大风险", html)
    self.assertIn("失效条件", html)
    self.assertIn("继续追问", html)
    self.assertNotIn("先看跨层状态", html)
```

- [ ] **Step 2: Run the Ask smoke test to verify it fails on the current layout**

Run: `pytest apps/control-panel/tests/test_app_smoke.py -k "ask_page_uses_decision_card_first" -v`
Expected: FAIL because the current Ask page still renders the cross-system strip before the main decision card.

- [ ] **Step 3: Add a structured explanation block to the Ask view-model**

```python
def build_ask_explanation_block(case: dict[str, Any] | None) -> dict[str, str]:
    if not case:
        return {"why": "", "risk": "", "invalid": ""}
    hero = case.get("hero") or {}
    metric_cards = case.get("metric_cards") or []
    return {
        "why": str(hero.get("summary") or "").strip(),
        "risk": str((metric_cards[0] or {}).get("detail") if metric_cards else "").strip(),
        "invalid": str(hero.get("confidence_note") or "").strip(),
    }
```

- [ ] **Step 4: Extend `build_ask_page_view()` to expose a decision-card-first shell**

```python
return {
    "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "query": query_text,
    "error": ask_error,
    "hero": {
        "title": "问一只股票，直接给结论和边界",
        "summary": "这页先回答今天该不该动，再给出理由、风险和失效条件。",
    },
    "decision_explanation": build_ask_explanation_block(ask_case),
    "examples": build_ask_examples(watchlist, screening_batch, confirmation),
    "recent_queries": build_ask_recent_queries(watchlist, screening_batch, confirmation),
    "case": ask_case,
    "followup": build_ask_followup_shell(ask_case),
    "links": links,
    "manager": {...},
}
```

- [ ] **Step 5: Reorder the Ask template so the decision card appears before cross-system context**

```jinja2
{% if ask.case %}
{% set detail = ask.case %}
<section class="today-hero ask-result-hero stage-decision-layer">
  <div class="today-copy">
    <p class="eyebrow">单票决策</p>
    <h2>{{ detail.hero.title }}</h2>
    <p class="today-summary">{{ detail.hero.summary }}</p>
    <div class="today-hero-meta ask-result-meta">
      <div class="meta-pill">
        <span>当前结论</span>
        <strong>{{ detail.hero.decision_label }}</strong>
      </div>
      <div class="meta-pill">
        <span>建议仓位</span>
        <strong>{{ detail.hero.position }}</strong>
      </div>
      <div class="meta-pill">
        <span>可信度</span>
        <strong>{{ detail.hero.confidence_label }}</strong>
      </div>
    </div>
  </div>
</section>
```

- [ ] **Step 6: Add a compact why/risk/invalidation section and keep follow-up below it**

```jinja2
<section class="today-quality-block ask-judgement-block stage-decision-layer">
  <div class="detail-metric-grid">
    <article class="today-summary-card">
      <span>为什么这么判断</span>
      <strong>核心理由</strong>
      <p>{{ ask.decision_explanation.why }}</p>
    </article>
    <article class="today-summary-card">
      <span>最大风险</span>
      <strong>风险边界</strong>
      <p>{{ ask.decision_explanation.risk }}</p>
    </article>
    <article class="today-summary-card">
      <span>失效条件</span>
      <strong>什么时候不再成立</strong>
      <p>{{ ask.decision_explanation.invalid }}</p>
    </article>
  </div>
</section>

<details class="progressive-section ask-progressive-strip">
  <summary class="progressive-summary">
    <div class="progressive-summary-main">
      <p class="eyebrow">继续追问</p>
      <strong>追问与跨系统背景</strong>
    </div>
    <span class="progressive-summary-note">展开追问、证据和跨层状态</span>
  </summary>
```

- [ ] **Step 7: Review JS selectors and keep follow-up interactions intact after the DOM reorder**

```javascript
document.addEventListener("DOMContentLoaded", () => {
  const root = document.querySelector("[data-ask-root]");
  if (!root) return;

  const form = root.querySelector("[data-ask-search-form]");
  const input = root.querySelector("[data-ask-search-input]");
  const followupShell = root.querySelector("[data-ask-followup]");
  const followupForm = root.querySelector("[data-ask-followup-form]");
  const followupInput = root.querySelector("[data-ask-followup-input]");
  const followupThread = root.querySelector("[data-ask-followup-thread]");
  if (!form || !input) return;
  // existing behavior continues unchanged after template reorder
});
```

- [ ] **Step 8: Run the Ask smoke test again**

Run: `pytest apps/control-panel/tests/test_app_smoke.py -k "ask_page_uses_decision_card_first" -v`
Expected: PASS

- [ ] **Step 9: Commit the Ask restructure**

```bash
git add apps/control-panel/dashboard_data.py apps/control-panel/templates/ask.html apps/control-panel/static/control-panel.css apps/control-panel/static/control-panel-ask.js apps/control-panel/tests/test_app_smoke.py
git commit -m "feat: make ask decision-card first"
```

## Task 4: Keep Holdings, Opportunities, Review, And Ops Consistent With The New Product Hierarchy

**Files:**
- Modify: `apps/control-panel/templates/watchlist.html`
- Modify: `apps/control-panel/templates/opportunities.html`
- Modify: `apps/control-panel/templates/review.html`
- Modify: `apps/control-panel/tests/test_app_smoke.py`

- [ ] **Step 1: Write the failing smoke test for stage-one page labels**

```python
def test_stage_one_surfaces_use_beginner_facing_labels(self) -> None:
    watchlist_response = self.client.get("/watchlist")
    opportunities_response = self.client.get("/opportunities")
    review_response = self.client.get("/review")
    self.assertIn("持仓", watchlist_response.text)
    self.assertIn("机会", opportunities_response.text)
    self.assertIn("复盘", review_response.text)
```

- [ ] **Step 2: Run the surface-label smoke test to verify where copy still uses internal wording**

Run: `pytest apps/control-panel/tests/test_app_smoke.py -k "stage_one_surfaces_use_beginner_facing_labels" -v`
Expected: FAIL until the page copy is aligned.

- [ ] **Step 3: Update page hero labels so they match the agreed IA**

```jinja2
<p class="eyebrow">持仓</p>
<h2>优先处理 Top 3</h2>
```

```jinja2
<p class="eyebrow">机会</p>
<h2>Top 3 可执行候选</h2>
```

```jinja2
<p class="eyebrow">复盘</p>
<h2>三条动作规则</h2>
```

- [ ] **Step 4: Re-run the stage-one surface label smoke test**

Run: `pytest apps/control-panel/tests/test_app_smoke.py -k "stage_one_surfaces_use_beginner_facing_labels" -v`
Expected: PASS

- [ ] **Step 5: Commit the label-alignment pass**

```bash
git add apps/control-panel/templates/watchlist.html apps/control-panel/templates/opportunities.html apps/control-panel/templates/review.html apps/control-panel/tests/test_app_smoke.py
git commit -m "feat: align stage-one surface vocabulary"
```

## Task 5: Run Full Verification And Update Docs References If Needed

**Files:**
- Modify: `apps/control-panel/tests/test_app_smoke.py`
- Modify: `docs/superpowers/specs/2026-04-21-prism-product-design.md`

- [ ] **Step 1: Run the focused control-panel smoke suite**

Run: `pytest apps/control-panel/tests/test_app_smoke.py -v`
Expected: PASS

- [ ] **Step 2: Run the repo smoke suite to ensure the public package still verifies**

Run: `pytest -q`
Expected: PASS

- [ ] **Step 3: If implementation language differs from the spec, update the spec inline before finishing**

```markdown
## 9. Stage-One Information Architecture

The implemented Today surface uses a command-center foundation with action-feed emphasis.
The implemented Ask surface uses a decision-card-first interaction with follow-up as a supporting layer.
```

- [ ] **Step 4: Run a final git diff review before completion**

Run: `git diff --stat`
Expected: Changed files are limited to the planned templates, view-model builder, styles, tests, and any explicit spec adjustments.

- [ ] **Step 5: Commit the verification or spec-alignment follow-up if needed**

```bash
git add apps/control-panel/tests/test_app_smoke.py docs/superpowers/specs/2026-04-21-prism-product-design.md
git commit -m "test: verify stage-one surface restructure"
```

## Self-Review

### Spec coverage

- Stage-one IA: covered by Tasks 1, 2, 3, and 4.
- Today command-center + action-feed hybrid: covered by Task 2.
- Ask decision-card-first + conversational follow-up: covered by Task 3.
- Internal ops separation: covered by Task 1 and dashboard copy updates.

### Placeholder scan

- No TODO/TBD placeholders remain.
- All tasks include exact files and concrete commands.

### Type and naming consistency

- Navigation uses `Today / Ask / Holdings / Opportunities / Review / 控制台` consistently.
- Today page sections use `primary_actions`, `holdings_rows`, `opportunity_rows`, and `risk_change_rows` consistently.
- Ask page uses `decision_explanation` consistently for why/risk/invalidation content.
