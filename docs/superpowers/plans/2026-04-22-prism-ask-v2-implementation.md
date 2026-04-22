# Prism Ask v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Prism Ask surface into an answer-first single-stock page for A-share beginners so the user sees `买入 / 持有 / 卖出 / 观察` before any chat, evidence wall, or cross-system explanation.

**Architecture:** Keep `apps/control-panel/dashboard_data.py` as the Ask composition layer and adapt the existing single-stock payload into an explicit Ask v2 surface contract. Rework `ask.html`, `control-panel.css`, and `control-panel-ask.js` around the locked reading order from the spec: compact search strip, hard conclusion card, boundary trio, execution layer, cross-system relation layer, then evidence and follow-up.

**Tech Stack:** Python, FastAPI, Jinja templates, vanilla JavaScript, shared control-panel CSS, `unittest` + `fastapi.testclient`

---

## File Structure

### Existing files to modify

- `apps/control-panel/dashboard_data.py`
  Responsibility: Normalize current Ask case data into an Ask v2 surface contract without inventing a second domain tree.
- `apps/control-panel/templates/ask.html`
  Responsibility: Rebuild the page hierarchy so the result state is conclusion-first and the empty state is search-first.
- `apps/control-panel/static/control-panel.css`
  Responsibility: Add Ask v2 layout, visual priority, mobile order, and progressive evidence styling aligned with the shared Prism language.
- `apps/control-panel/static/control-panel-ask.js`
  Responsibility: Keep search suggestions, compact result-state search behavior, and follow-up interaction working after the template contract changes.
- `apps/control-panel/tests/test_app_smoke.py`
  Responsibility: Lock the Ask v2 product contract with route, HTML-order, and payload-level smoke coverage.

### Existing files to reference but not change unless implementation reveals drift

- `docs/superpowers/specs/2026-04-22-prism-ask-v2-design.md`
  Responsibility: Product contract for Ask v2.
- `docs/superpowers/specs/2026-04-22-prism-today-v2-design.md`
  Responsibility: Shared visual/system language reference so Ask stays in the same family as Today.
- `apps/control-panel/templates/_decision_topline.html`
  Responsibility: Existing shared conclusion/topline patterns that can be reused if they fit Ask v2 without forcing the old page hierarchy.

### No new package split in this pass

Do not introduce a new package, Pydantic schema tree, or repo-wide frontend component system for this iteration. The product priority is to lock the Ask v2 reading order and visual contract with minimal structural churn.

## Task 1: Lock The Ask v2 Contract With Failing Tests

**Files:**
- Modify: `apps/control-panel/tests/test_app_smoke.py`
- Reference: `apps/control-panel/templates/ask.html`
- Reference: `apps/control-panel/dashboard_data.py`

- [ ] **Step 1: Add a failing route test for the empty-state promise and result-state reading order**

```python
def test_ask_result_state_reads_conclusion_then_boundary_then_execution(self) -> None:
    response = self.client.get("/ask?q=600690")
    self.assertEqual(response.status_code, 200)
    html = response.text

    search_index = html.find("ask-result-search-strip")
    conclusion_index = html.find("现在该怎么做")
    boundary_index = html.find("为什么这么判断")
    execution_index = html.find("现在做什么")
    relation_index = html.find("这只票和系统里的关系")
    evidence_index = html.find("证据与继续追问")

    self.assertGreaterEqual(search_index, 0)
    self.assertGreaterEqual(conclusion_index, 0)
    self.assertGreaterEqual(boundary_index, 0)
    self.assertGreaterEqual(execution_index, 0)
    self.assertGreaterEqual(relation_index, 0)
    self.assertGreaterEqual(evidence_index, 0)

    self.assertLess(search_index, conclusion_index)
    self.assertLess(conclusion_index, boundary_index)
    self.assertLess(boundary_index, execution_index)
    self.assertLess(execution_index, relation_index)
    self.assertLess(relation_index, evidence_index)
```

- [ ] **Step 2: Add a failing payload test for the Ask v2 surface contract in `build_ask_page_view()`**

```python
def test_build_ask_page_view_exposes_ask_v2_surface_contract(self) -> None:
    payload = build_ask_page_view("600690")
    case = payload.get("case") or {}

    self.assertEqual(payload.get("surface_mode"), "result")
    self.assertEqual(case.get("surface_version"), "ask_v2")
    self.assertIn("search_strip", payload)
    self.assertIn("conclusion_card", case)
    self.assertIn("boundary_trio", case)
    self.assertIn("execution_layer", case)
    self.assertIn("relation_layer", case)
    self.assertIn("evidence_layer", case)
```

- [ ] **Step 3: Add a failing regression test that follow-up remains available but not first-screen dominant**

```python
def test_ask_followup_is_present_but_demoted_below_first_screen_sections(self) -> None:
    response = self.client.get("/ask?q=600690")
    self.assertEqual(response.status_code, 200)
    html = response.text

    self.assertIn("继续追问这只股票", html)
    self.assertIn("证据与继续追问", html)
    self.assertNotIn("继续追问</h2>\n          </div>\n        </div>\n        <p class=\"today-panel-copy\">", html[:2500])
```

- [ ] **Step 4: Run the targeted Ask smoke tests and verify they fail before implementation**

Run: `./.venv/bin/pytest -q apps/control-panel/tests/test_app_smoke.py  -k "ask_result_state or ask_v2 or ask_followup_is_present"`
Expected: FAIL because the current Ask payload and HTML still reflect the older explanation-heavy structure.

- [ ] **Step 5: Commit the test contract lock**

```bash
git add apps/control-panel/tests/test_app_smoke.py
git commit -m "test: lock ask v2 surface contract"
```

## Task 2: Build The Ask v2 Surface Contract In The Data Layer

**Files:**
- Modify: `apps/control-panel/dashboard_data.py`
- Test: `apps/control-panel/tests/test_app_smoke.py`

- [ ] **Step 1: Add focused helper builders that reshape the existing Ask case into explicit v2 sections**

```python
def build_ask_conclusion_card(case: dict[str, Any]) -> dict[str, Any]:
    canonical = case.get("canonical_decision") or {}
    hero = case.get("hero") or {}
    return {
        "eyebrow": "现在该怎么做",
        "verdict": canonical.get("main_conclusion") or "观察",
        "action_sentence": canonical.get("next_step") or hero.get("summary"),
        "confidence_label": hero.get("confidence_label") or "待核",
        "confidence_note": hero.get("confidence_note") or "当前先按已有证据理解。",
        "meta_pills": [
            canonical.get("position_guidance") or "仓位待定",
            canonical.get("risk_boundary") or "边界待核",
            canonical.get("source_scope") or "live_fallback",
        ],
    }


def build_ask_boundary_trio(case: dict[str, Any]) -> list[dict[str, str]]:
    canonical = case.get("canonical_decision") or {}
    return [
        {
            "key": "why_now",
            "label": "为什么这么判断",
            "title": "当前成立的核心理由",
            "body": canonical.get("why_now") or "先按当前主结论理解这只票。",
        },
        {
            "key": "continue_condition",
            "label": "继续成立的条件",
            "title": "满足这些条件再继续",
            "body": canonical.get("continue_condition") or "条件未满足前，先不升级动作。",
        },
        {
            "key": "stop_condition",
            "label": "一票否决条件",
            "title": "一旦出现就先停",
            "body": canonical.get("stop_condition") or "触发后先停止原计划。",
        },
    ]
```

- [ ] **Step 2: Add adapters for the execution, relation, and evidence layers by reusing existing Ask fields instead of duplicating logic**

```python
def build_ask_execution_layer(case: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in (case.get("execution_loop") or [])
        if item.get("label") in {"现在做什么", "先不要做什么", "去哪看证据"}
    ]


def build_ask_relation_layer(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": "这只票和系统里的关系",
        "cards": list(case.get("cross_cards") or [])[:4],
        "watchlist_action": case.get("watchlist_action") or {},
    }


def build_ask_evidence_layer(case: dict[str, Any], followup: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "title": "证据与继续追问",
        "metric_cards": list(case.get("metric_cards") or [])[:4],
        "level_cards": list(case.get("level_cards") or [])[:4],
        "analysis_groups": list(case.get("analysis_groups") or [])[:6],
        "event_groups": list(case.get("event_groups") or [])[:2],
        "artifacts": list(case.get("artifacts") or [])[:4],
        "followup": followup,
    }
```

- [ ] **Step 3: Update `build_ask_page_view()` so it exposes empty-state and result-state shells explicitly**

```python
return {
    "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "query": query_text,
    "error": ask_error,
    "surface_mode": "result" if ask_case else "empty",
    "search_strip": {
        "title": "问一只股票，直接给结论和边界",
        "promise": "先给结论，再给边界",
        "is_compact": bool(ask_case),
        "hint": "支持代码/名称联想，候选项会优先回填可直接分析的查询值。",
    },
    "hero": {
        "title": "问一只股票，直接给结论和边界",
        "summary": "这页先回答今天该不该动，再把技术、资金、事件和跨系统状态拆开给你看。",
    },
    "examples": build_ask_examples(watchlist, screening_batch, confirmation),
    "recent_queries": build_ask_recent_queries(watchlist, screening_batch, confirmation),
    "case": ask_case,
    "links": links,
    "manager": {
        "add_api": "/api/watchlist/manage/add",
        "restore_api": "/api/watchlist/manage/restore",
        "watchlist_url": watchlist_page_url(),
    },
}
```

- [ ] **Step 4: Update `build_ask_case_view()` so the case includes the v2 sections while keeping existing fields needed by follow-up and related pages**

```python
case = {
    **case,
    "surface_version": "ask_v2",
}
case["conclusion_card"] = build_ask_conclusion_card(case)
case["boundary_trio"] = build_ask_boundary_trio(case)
case["execution_layer"] = build_ask_execution_layer(case)
case["relation_layer"] = build_ask_relation_layer(case)
case["evidence_layer"] = build_ask_evidence_layer(case, build_ask_followup_shell(case))
```

- [ ] **Step 5: Run the targeted payload tests again**

Run: `./.venv/bin/pytest -q apps/control-panel/tests/test_app_smoke.py -k "ask_v2 or surface_contract"`
Expected: PASS

- [ ] **Step 6: Commit the Ask v2 data contract**

```bash
git add apps/control-panel/dashboard_data.py apps/control-panel/tests/test_app_smoke.py
git commit -m "feat: add ask v2 surface contract"
```

## Task 3: Replace The Ask Template With The Conclusion-First Layout

**Files:**
- Modify: `apps/control-panel/templates/ask.html`
- Reference: `apps/control-panel/templates/_page_nav.html`
- Test: `apps/control-panel/tests/test_app_smoke.py`

- [ ] **Step 1: Replace the current hero-heavy result state with a two-mode shell: empty state and compact result-state search strip**

```html
<header class="ask-page-shell-header">
  {% set nav_active = "ask" %}
  {% set nav_links = ask.links %}
  {% set nav_api_href = ask.links.api_self %}
  {% include "_page_nav.html" %}

  <section class="ask-search-shell {% if ask.surface_mode == 'result' %}ask-result-search-strip{% endif %}">
    <div class="ask-search-copy">
      <p class="eyebrow">问股</p>
      <h1>{{ ask.search_strip.title }}</h1>
      <p>{{ ask.hero.summary }}</p>
    </div>
    <form class="ask-search-form" method="get" action="/ask" data-ask-search-form>
      <div class="ask-search-row">
        <label class="ask-search-field">
          <span>股票代码或名称</span>
          <input
            type="text"
            name="q"
            value="{{ ask.query }}"
            placeholder="例如 600690 / 海尔智家"
            autocomplete="off"
            inputmode="search"
            spellcheck="false"
            data-ask-search-input
          >
        </label>
        <button class="ghost-button ask-search-button" type="submit" data-ask-submit-button>
          <span>开始分析</span>
          <kbd>Enter</kbd>
        </button>
      </div>
      <p class="ask-search-hint">{{ ask.search_strip.hint }}</p>
      <p class="ask-search-status" data-ask-search-status aria-live="polite"></p>
      <div class="ask-suggest-panel hidden" data-ask-suggest-panel role="listbox" aria-label="问股候选"></div>
    </form>
    <div class="ask-compact-promise">
      <strong>{{ ask.search_strip.promise }}</strong>
      <p>{{ ask.search_strip.hint }}</p>
    </div>
  </section>
</header>
```

- [ ] **Step 2: Rebuild the result-state first screen in the exact spec order**

```html
{% if ask.case %}
<section class="ask-conclusion-card stage-decision-layer">
  <p class="eyebrow">{{ ask.case.conclusion_card.eyebrow }}</p>
  <strong class="ask-conclusion-verdict">{{ ask.case.conclusion_card.verdict }}</strong>
  <p class="ask-conclusion-action">{{ ask.case.conclusion_card.action_sentence }}</p>
</section>

<section class="ask-boundary-trio stage-decision-layer">
  {% for item in ask.case.boundary_trio %}
  <article class="ask-boundary-card">
    <span>{{ item.label }}</span>
    <strong>{{ item.title }}</strong>
    <p>{{ item.body }}</p>
  </article>
  {% endfor %}
</section>

<section class="ask-execution-layer stage-action-layer">
  <div class="today-panel-head">
    <div>
      <p class="eyebrow">执行动作</p>
      <h2>先做什么，再别做什么</h2>
    </div>
  </div>
  <div class="detail-metric-grid detail-metric-grid-single ask-execution-grid">
    {% for item in ask.case.execution_layer %}
    <article class="detail-row-card execution-loop-card">
      <span>{{ item.label }}</span>
      <em class="action-tier-inline action-tier-inline-{{ item.tier_key|default('observe') }}">{{ item.tier }}</em>
      <strong>{{ item.value }}</strong>
      <p>{{ item.detail }}</p>
    </article>
    {% endfor %}
  </div>
</section>

<section class="ask-relation-layer stage-evidence-layer">
  <div class="today-panel-head">
    <div>
      <p class="eyebrow">跨系统关系</p>
      <h2>{{ ask.case.relation_layer.title }}</h2>
    </div>
  </div>
  <div class="today-source-strip ask-source-strip ask-relation-grid">
    {% for item in ask.case.relation_layer.cards %}
    <article class="source-card tone-{{ item.tone }}">
      <span>{{ item.label }}</span>
      <strong>{{ item.value }}</strong>
      <p>{{ item.detail }}</p>
    </article>
    {% endfor %}
  </div>
  <section class="ask-watchlist-block tone-{{ ask.case.relation_layer.watchlist_action.tone }}">
    <span class="callout-label">自选股动作</span>
    <strong>{{ ask.case.relation_layer.watchlist_action.label }}</strong>
    <p>{{ ask.case.relation_layer.watchlist_action.detail }}</p>
  </section>
</section>
{% endif %}
```

- [ ] **Step 3: Move six-dimension analysis, event evidence, artifacts, and follow-up into a clearly demoted evidence block**

```html
<details class="progressive-section ask-evidence-fold">
  <summary class="progressive-summary">
    <div class="progressive-summary-main">
      <p class="eyebrow">证据与继续追问</p>
      <strong>{{ ask.case.evidence_layer.title }}</strong>
    </div>
    <span class="progressive-summary-note">展开后再看六维拆解、事件证据、原始文件和连续追问</span>
  </summary>
  <div class="progressive-body">
    <section class="detail-metric-grid stage-evidence-layer">
      {% for item in ask.case.evidence_layer.metric_cards %}
      <article class="today-summary-card">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
        <p>{{ item.detail }}</p>
      </article>
      {% endfor %}
    </section>

    <section class="detail-metric-grid stage-evidence-layer">
      {% for item in ask.case.evidence_layer.level_cards %}
      <article class="today-summary-card">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
        <p>{{ item.detail }}</p>
      </article>
      {% endfor %}
    </section>

    <section class="detail-group-grid ask-analysis-grid">
      {% for group in ask.case.evidence_layer.analysis_groups %}
      <article class="detail-group-card ask-analysis-card tone-{{ group.tone }}">
        <div class="detail-group-head">
          <strong>{{ group.title }}</strong>
          <span>{{ group.metric }}</span>
        </div>
        {% if group["items"] %}
        <ul class="detail-bullet-list">
          {% for item in group["items"] %}
          <li>{{ item }}</li>
          {% endfor %}
        </ul>
        {% else %}
        <p class="detail-empty-copy">{{ group.empty }}</p>
        {% endif %}
      </article>
      {% endfor %}
    </section>

    <section class="detail-group-grid ask-event-grid">
      {% for group in ask.case.evidence_layer.event_groups %}
      <article class="detail-group-card">
        <div class="detail-group-head">
          <strong>{{ group.title }}</strong>
          <span>{{ group["items"]|length }}</span>
        </div>
        {% if group["items"] %}
        <div class="detail-stack">
          {% for item in group["items"] %}
          <article class="detail-note-card ask-event-card">
            <strong>{{ item.title }}</strong>
            <p>{{ item.meta }}</p>
          </article>
          {% endfor %}
        </div>
        {% else %}
        <p class="detail-empty-copy">{{ group.empty }}</p>
        {% endif %}
      </article>
      {% endfor %}
    </section>

    {% if ask.case.evidence_layer.followup %}
    <section class="today-panel ask-followup-shell stage-action-layer" data-ask-followup>
      <div class="today-panel-head">
        <div>
          <p class="eyebrow">连续追问</p>
          <h2>继续追问这只股票</h2>
        </div>
      </div>
      <p class="today-panel-copy">{{ ask.case.evidence_layer.followup.starter.summary }}</p>
    </section>
    {% endif %}

    <section class="detail-artifact-grid">
      {% for item in ask.case.evidence_layer.artifacts %}
      <button class="artifact-link" type="button" data-preview-path="{{ item.path }}" data-preview-title="{{ item.title }}">
        <span>{{ item.title }}</span>
        <strong>{{ item.name }}</strong>
        <em>{{ item.mtime_full }}</em>
      </button>
      {% endfor %}
    </section>
  </div>
</details>
```

- [ ] **Step 4: Keep the empty state search-first and lightweight**

```html
{% if not ask.case %}
<section class="today-quality-block ask-empty-block stage-decision-layer">
  <div class="section-head">
    <div>
      <p class="eyebrow">开始方式</p>
      <h2>先输入一只股票</h2>
    </div>
  </div>
  <p class="today-panel-copy">先给结论，再给边界。输入 6 位代码或股票名称后，页面会先返回结论，再告诉你条件和动作。</p>
</section>
{% endif %}
```

- [ ] **Step 5: Run the Ask HTML-order smoke tests again**

Run: `./.venv/bin/pytest -q apps/control-panel/tests/test_app_smoke.py -k "ask_result_state or ask_followup_is_present"`
Expected: PASS

- [ ] **Step 6: Commit the Ask v2 template rewrite**

```bash
git add apps/control-panel/templates/ask.html apps/control-panel/tests/test_app_smoke.py
git commit -m "feat: rebuild ask page hierarchy for v2"
```

## Task 4: Add The Ask v2 Visual System And Interaction Wiring

**Files:**
- Modify: `apps/control-panel/static/control-panel.css`
- Modify: `apps/control-panel/static/control-panel-ask.js`
- Modify: `apps/control-panel/templates/ask.html`
- Test: `apps/control-panel/tests/test_app_smoke.py`

- [ ] **Step 1: Add Ask v2 layout tokens and conclusion-first styling in the shared CSS**

```css
.ask-result-search-strip {
  display: grid;
  gap: 16px;
  padding: 20px 24px;
  border: 1px solid rgba(196, 151, 58, 0.24);
  background:
    linear-gradient(180deg, rgba(7, 15, 31, 0.94), rgba(10, 20, 39, 0.9)),
    radial-gradient(circle at top right, rgba(196, 151, 58, 0.18), transparent 38%);
}

.ask-conclusion-card {
  display: grid;
  gap: 12px;
  padding: 28px;
  border-radius: 28px;
  border: 1px solid rgba(196, 151, 58, 0.28);
  background: linear-gradient(160deg, rgba(12, 26, 49, 0.98), rgba(8, 17, 32, 0.96));
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.28);
}

.ask-conclusion-verdict {
  font-size: clamp(32px, 5vw, 54px);
  line-height: 1;
  letter-spacing: 0.04em;
}
```

- [ ] **Step 2: Add boundary-trio, execution, and relation-layer styles that make the boundary cards sharp and the support layers secondary**

```css
.ask-boundary-trio {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.ask-boundary-card {
  min-height: 180px;
  padding: 18px;
  border-radius: 22px;
  background: rgba(10, 20, 38, 0.88);
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.ask-relation-layer,
.ask-evidence-fold {
  opacity: 0.94;
}
```

- [ ] **Step 3: Add mobile rules that preserve reading order instead of desktop geometry**

```css
@media (max-width: 820px) {
  .ask-boundary-trio,
  .ask-execution-grid,
  .ask-relation-grid {
    grid-template-columns: 1fr;
  }

  .ask-result-search-strip {
    padding: 16px;
  }

  .ask-conclusion-card {
    padding: 20px;
    border-radius: 22px;
  }
}
```

- [ ] **Step 4: Update `control-panel-ask.js` selectors only where the template contract changed, keeping suggestion and follow-up logic intact**

```javascript
const root = document.querySelector("[data-ask-root]");
const form = root?.querySelector("[data-ask-search-form]");
const input = root?.querySelector("[data-ask-search-input]");
const panel = root?.querySelector("[data-ask-suggest-panel]");
const followupShell = root?.querySelector("[data-ask-followup]");

if (root?.dataset.askMode === "result") {
  root.classList.add("ask-mode-result");
}
```

- [ ] **Step 5: Run a focused smoke pass for route rendering after the CSS/JS/template wiring changes**

Run: `./.venv/bin/pytest -q apps/control-panel/tests/test_app_smoke.py -k "html_routes_return_200 or ask"`
Expected: PASS

- [ ] **Step 6: Commit the Ask v2 UI layer**

```bash
git add apps/control-panel/static/control-panel.css apps/control-panel/static/control-panel-ask.js apps/control-panel/templates/ask.html apps/control-panel/tests/test_app_smoke.py
git commit -m "feat: style ask v2 conclusion-first surface"
```

## Task 5: Run Full Verification And Product Cleanup

**Files:**
- Modify only if verification reveals drift: `apps/control-panel/dashboard_data.py`, `apps/control-panel/templates/ask.html`, `apps/control-panel/static/control-panel.css`, `apps/control-panel/static/control-panel-ask.js`, `apps/control-panel/tests/test_app_smoke.py`

- [ ] **Step 1: Run the full control-panel smoke suite**

Run: `./.venv/bin/pytest -q apps/control-panel/tests/test_app_smoke.py`
Expected: PASS with all Ask, Today, navigation, and detail-route smoke tests green.

- [ ] **Step 2: Run the full repo test suite to catch regressions outside Ask**

Run: `./.venv/bin/pytest -q`
Expected: PASS with the repo-wide suite green.

- [ ] **Step 3: Launch the local control panel and manually verify both Ask states in the browser**

Run: `./.venv/bin/uvicorn control_panel.app:app --host 127.0.0.1 --port 8000 --reload`
Expected: App boots successfully and `/ask` shows:
- empty state as search-first with examples/recent queries
- result state with conclusion card first
- boundary trio directly below the conclusion
- follow-up only after evidence expansion
- mobile width preserving the same section order

- [ ] **Step 4: If manual review finds hierarchy drift, make the smallest fix and rerun the narrowest relevant test before moving on**

```bash
./.venv/bin/pytest -q apps/control-panel/tests/test_app_smoke.py -k ask
```

Expected: PASS again after each targeted cleanup.

- [ ] **Step 5: Commit the final Ask v2 verification cleanup**

```bash
git add apps/control-panel/dashboard_data.py apps/control-panel/templates/ask.html apps/control-panel/static/control-panel.css apps/control-panel/static/control-panel-ask.js apps/control-panel/tests/test_app_smoke.py
git commit -m "test: verify ask v2 end to end"
```

## Self-Review Checklist

- Spec coverage: The plan covers empty state, result-state reading order, conclusion card, boundary trio, execution layer, cross-system relation layer, evidence/follow-up demotion, and mobile ordering.
- Placeholder scan: No `TODO`, `TBD`, or unresolved task references remain.
- Boundary check: This plan only redesigns Ask and does not pull holdings detail or opportunities into the same UI rewrite.
- Global fit: The plan keeps Ask aligned with Today v2 and the broader Prism beginner-investor positioning rather than optimizing Ask as an isolated chat page.
