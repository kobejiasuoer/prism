# Prism Decision Protocol Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a canonical stage-one stock decision protocol so Today, Ask, Holdings detail, Opportunities detail, and Review all read from the same stock decision contract instead of assembling top-level conclusions independently.

**Architecture:** Keep `apps/control-panel/dashboard_data.py` as the main composition layer, but introduce a focused canonical decision builder and shared normalization helpers inside that module first. Migrate page-specific stock conclusion assembly to call the canonical builder, then add change-history and review wiring on top of the same decision object instead of inventing a second abstraction tree.

**Tech Stack:** Python, FastAPI, Jinja templates, repo smoke tests with `unittest` + `fastapi.testclient`

---

## File Structure

### Existing files to modify

- `apps/control-panel/dashboard_data.py`
  Responsibility: Add the canonical decision builder, source ownership resolution, conclusion normalization, conflict resolution, and page adapters.
- `apps/control-panel/tests/test_app_smoke.py`
  Responsibility: Add protocol-level smoke coverage so main conclusion, action tier, and cross-page decision consistency do not drift.
- `apps/control-panel/templates/ask.html`
  Responsibility: Keep reading order aligned to the canonical decision object if any section names or bindings need cleanup.
- `apps/control-panel/templates/today_watchlist_detail.html`
  Responsibility: Keep holdings detail bound to the canonical decision fields.
- `apps/control-panel/templates/today_candidate_detail.html`
  Responsibility: Keep opportunity detail bound to the canonical decision fields.
- `apps/control-panel/templates/today.html`
  Responsibility: Later consume canonical stock decision summaries inside the Today action desk.
- `apps/control-panel/templates/review.html`
  Responsibility: Later consume decision transition records rather than only summary copy.
- `docs/superpowers/specs/2026-04-22-prism-decision-protocol-design.md`
  Responsibility: Canonical product contract for this work. Update only if implementation reveals a real protocol mismatch.

### New files to create only if truly needed

- `apps/control-panel/tests/test_decision_protocol_smoke.py`
  Responsibility: Optional focused protocol tests if `test_app_smoke.py` becomes too crowded. Do not create unless the existing smoke file becomes hard to maintain.

### No new model layer yet

Do not introduce a new package, pydantic model tree, or repo-wide domain module in the first pass. The priority is to lock the protocol and route all current stock-facing surfaces through it with the least structural churn.

## Task 1: Add Canonical Decision Builder In The Data Layer

**Files:**
- Modify: `apps/control-panel/dashboard_data.py`
- Test: `apps/control-panel/tests/test_app_smoke.py`

- [ ] **Step 1: Write the failing test for canonical decision field presence on Ask, holdings detail, and opportunity detail**

```python
def test_stock_surfaces_expose_canonical_decision_fields(self) -> None:
    ask = (build_ask_page_view("600690").get("case") or {})
    watchlist_detail = build_watchlist_detail_view("000625")
    candidate_detail = build_candidate_detail_view("600392")

    payloads = [ask, watchlist_detail, candidate_detail]
    required_keys = {
        "canonical_decision",
        "decision_cards",
        "decision_explanation",
        "execution_loop",
        "topline",
    }

    for payload in payloads:
        self.assertTrue(required_keys.issubset(payload.keys()))
        canonical = payload.get("canonical_decision") or {}
        for key in (
            "stock_id",
            "stock_name",
            "trade_date",
            "source_scope",
            "main_conclusion",
            "action_tier",
            "position_guidance",
            "risk_boundary",
            "why_now",
            "continue_condition",
            "stop_condition",
            "next_step",
            "trigger_condition",
            "avoid_action",
            "evidence_entry",
            "confidence_note",
        ):
            self.assertIn(key, canonical)
```

- [ ] **Step 2: Run the targeted test to verify it fails before implementation**

Run: `./.venv/bin/pytest -q apps/control-panel/tests/test_app_smoke.py -k canonical_decision_fields`
Expected: FAIL because the current payloads do not expose `canonical_decision`.

- [ ] **Step 3: Add a shared canonical decision builder and small helper normalizers inside `dashboard_data.py`**

```python
def build_canonical_decision(
    *,
    stock_id: str,
    stock_name: str,
    trade_date: Any,
    source_scope: str,
    main_conclusion: Any,
    action_tier: Any,
    position_guidance: Any,
    risk_boundary: Any,
    why_now: Any,
    continue_condition: Any,
    stop_condition: Any,
    next_step: Any,
    trigger_condition: Any,
    avoid_action: Any,
    evidence_entry: Any,
    confidence_note: Any,
    updated_at: Any,
    extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "stock_id": str(detail_value(stock_id)).strip(),
        "stock_name": str(detail_value(stock_name)).strip(),
        "trade_date": detail_value(trade_date),
        "source_scope": str(detail_value(source_scope, "live_fallback")).strip(),
        "main_conclusion": normalize_main_conclusion(main_conclusion),
        "action_tier": action_tier_label(action_tier),
        "position_guidance": str(detail_value(position_guidance, "待定")).strip(),
        "risk_boundary": str(detail_value(risk_boundary, "先守纪律边界")).strip(),
        "why_now": str(detail_value(why_now, "先按当前主结论理解这只股票。")).strip(),
        "continue_condition": str(detail_value(continue_condition, "满足当前纪律前，先不升级动作。")).strip(),
        "stop_condition": str(detail_value(stop_condition, "一旦触发失效条件，先停下来。")).strip(),
        "next_step": normalize_next_step_sentence(next_step),
        "trigger_condition": normalize_trigger_sentence(trigger_condition),
        "avoid_action": normalize_avoid_sentence(avoid_action),
        "evidence_entry": str(detail_value(evidence_entry, "看原始证据入口")).strip(),
        "confidence_note": str(detail_value(confidence_note, "当前证据不完整，先别放大动作。")).strip(),
        "updated_at": detail_value(updated_at),
    }
    if extras:
        payload.update(extras)
    return payload
```

- [ ] **Step 4: Add a small main-conclusion normalizer that maps current rich labels onto stage-one canonical conclusions**

```python
def normalize_main_conclusion(value: Any) -> str:
    text = str(detail_value(value, "观察")).strip()
    if any(token in text for token in ("卖", "清仓", "退出", "减仓")):
        return "卖出"
    if any(token in text for token in ("买", "试错", "开仓", "介入")):
        return "买入"
    if any(token in text for token in ("持有", "保留")):
        return "持有"
    return "观察"
```

- [ ] **Step 5: Run the targeted canonical-field test again**

Run: `./.venv/bin/pytest -q apps/control-panel/tests/test_app_smoke.py -k canonical_decision_fields`
Expected: PASS

- [ ] **Step 6: Commit the canonical decision builder**

```bash
git add apps/control-panel/dashboard_data.py apps/control-panel/tests/test_app_smoke.py
git commit -m "feat: add canonical stock decision builder"
```

## Task 2: Route Ask Through The Canonical Decision Object

**Files:**
- Modify: `apps/control-panel/dashboard_data.py`
- Modify: `apps/control-panel/templates/ask.html`
- Test: `apps/control-panel/tests/test_app_smoke.py`

- [ ] **Step 1: Write the failing test that Ask top-level conclusion and cards are derived from the canonical decision**

```python
def test_ask_surface_reads_main_fields_from_canonical_decision(self) -> None:
    ask = (build_ask_page_view("600690").get("case") or {})
    canonical = ask.get("canonical_decision") or {}
    cards = {item.get("label"): item.get("value") for item in (ask.get("decision_cards") or [])}

    self.assertEqual(cards.get("当前结论"), canonical.get("main_conclusion"))
    self.assertEqual(cards.get("仓位建议"), canonical.get("position_guidance"))
    self.assertEqual(cards.get("风险边界"), canonical.get("risk_boundary"))
    self.assertEqual(cards.get("下一步动作"), canonical.get("next_step"))
```

- [ ] **Step 2: Run the Ask-specific test to verify it fails**

Run: `./.venv/bin/pytest -q apps/control-panel/tests/test_app_smoke.py -k reads_main_fields_from_canonical_decision`
Expected: FAIL because Ask still assembles cards directly from page-local rows.

- [ ] **Step 3: Build Ask `canonical_decision` first, then derive topline, cards, explanation, and execution loop from that object**

```python
canonical_decision = build_canonical_decision(
    stock_id=code,
    stock_name=stock.get("name"),
    trade_date=current_trade_date(watchlist, screening_batch, None),
    source_scope=resolve_decision_source_scope(watchlist_stock, candidate, confirmation_match),
    main_conclusion=decision_label,
    action_tier=infer_action_tier(action=decision_label, tone=action_tone(decision_label)),
    position_guidance=position_value,
    risk_boundary=(invalid_row or {}).get("value") or confidence.get("detail"),
    why_now=decision_summary,
    continue_condition=(risk_row or {}).get("value"),
    stop_condition=(invalid_row or {}).get("value") or confidence.get("detail"),
    next_step=(action_row or {}).get("value"),
    trigger_condition=next((item for item in plan_rows if item.get("label") == "触发"), {}).get("value"),
    avoid_action=(risk_row or {}).get("value"),
    evidence_entry="看关键位与跨层背景",
    confidence_note=confidence.get("detail"),
    updated_at=live_context.get("generated_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
)
```

- [ ] **Step 4: Replace direct Ask card assembly with adapters from `canonical_decision`**

```python
"decision_cards": build_detail_decision_cards(
    conclusion=canonical_decision["main_conclusion"],
    conclusion_detail=canonical_decision["why_now"],
    position=canonical_decision["position_guidance"],
    position_detail="按当前统一判断控制仓位，不额外放大动作。",
    risk_boundary=canonical_decision["risk_boundary"],
    risk_detail="先守住失效位和纪律边界，再决定是否继续执行。",
    next_step=canonical_decision["next_step"],
    next_step_detail="先执行当前最靠前的一步，再决定要不要展开更多证据。",
)
```

- [ ] **Step 5: Run the Ask-specific test again**

Run: `./.venv/bin/pytest -q apps/control-panel/tests/test_app_smoke.py -k reads_main_fields_from_canonical_decision`
Expected: PASS

- [ ] **Step 6: Commit the Ask migration**

```bash
git add apps/control-panel/dashboard_data.py apps/control-panel/templates/ask.html apps/control-panel/tests/test_app_smoke.py
git commit -m "feat: route ask through canonical decision"
```

## Task 3: Route Holdings Detail And Opportunity Detail Through The Same Decision Builder

**Files:**
- Modify: `apps/control-panel/dashboard_data.py`
- Modify: `apps/control-panel/templates/today_watchlist_detail.html`
- Modify: `apps/control-panel/templates/today_candidate_detail.html`
- Test: `apps/control-panel/tests/test_app_smoke.py`

- [ ] **Step 1: Write the failing cross-page consistency test for canonical main conclusion and action tier**

```python
def test_stock_detail_surfaces_share_canonical_main_conclusion_contract(self) -> None:
    watchlist_detail = build_watchlist_detail_view("000625")
    candidate_detail = build_candidate_detail_view("600392")

    for payload in (watchlist_detail, candidate_detail):
        canonical = payload.get("canonical_decision") or {}
        cards = {item.get("label"): item.get("value") for item in (payload.get("decision_cards") or [])}
        self.assertEqual(cards.get("当前结论"), canonical.get("main_conclusion"))
        self.assertEqual(cards.get("下一步动作"), canonical.get("next_step"))
        self.assertIn(canonical.get("action_tier"), {"立即执行", "等触发", "仅观察", "明确回避"})
```

- [ ] **Step 2: Run the detail-surface test to verify it fails before migration**

Run: `./.venv/bin/pytest -q apps/control-panel/tests/test_app_smoke.py -k canonical_main_conclusion_contract`
Expected: FAIL because detail surfaces still assemble cards from local fields.

- [ ] **Step 3: Build `canonical_decision` in `build_watchlist_detail_view()` using holdings-first ownership**

```python
canonical_decision = build_canonical_decision(
    stock_id=stock.get("code"),
    stock_name=stock.get("name"),
    trade_date=snapshot.get("trade_date"),
    source_scope="holdings",
    main_conclusion=stock.get("action") or "观望",
    action_tier=infer_action_tier(action=stock.get("action"), tone=action_tone(stock.get("action"))),
    position_guidance=stock.get("position") or "-",
    risk_boundary=trade_levels.get("stop_loss") or rule_snapshot.get("signal"),
    why_now=reason,
    continue_condition=(stock.get("watch_points") or [None])[0],
    stop_condition=trade_levels.get("stop_loss") or next_trigger.get("condition") or rule_snapshot.get("signal"),
    next_step=next_step,
    trigger_condition=next_trigger.get("condition") or trade_levels.get("resistance"),
    avoid_action=(stock.get("hard_flags") or [None])[0] or "先不要脱离纪律位硬扛",
    evidence_entry="看盘中触发与原始文件",
    confidence_note="这是今天最直接影响持仓处理的判断。",
    updated_at=snapshot.get("generated_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
)
```

- [ ] **Step 4: Build `canonical_decision` in `build_candidate_detail_view()` using opportunity ownership unless holdings exists and should win**

```python
source_scope = "holdings" if watchlist_stock else "opportunity"
canonical_decision = build_canonical_decision(
    stock_id=candidate.get("code"),
    stock_name=candidate.get("name"),
    trade_date=current_trade_date(watchlist, screening_batch, None),
    source_scope=source_scope,
    main_conclusion=(confirmation_match or {}).get("group_label") or candidate_status_label(candidate.get("screening_status")) or "继续观察",
    action_tier=infer_action_tier(action=entry_plan.get("action") or candidate.get("screening_status"), tone=candidate_tone(candidate)),
    position_guidance=entry_plan.get("sizing") or (watchlist_stock or {}).get("position") or "轻仓试错",
    risk_boundary=entry_plan.get("invalidate") or ((entry_plan.get("levels") or {}).get("invalidate")) or candidate.get("main_risk"),
    why_now=summary,
    continue_condition=entry_plan.get("trigger") or candidate.get("watch_condition"),
    stop_condition=entry_plan.get("invalidate") or candidate.get("main_risk"),
    next_step=entry_plan.get("action") or entry_plan.get("trigger") or "先观察，不急着执行",
    trigger_condition=entry_plan.get("trigger") or candidate.get("watch_condition"),
    avoid_action=entry_plan.get("avoid") or candidate.get("main_risk"),
    evidence_entry="看执行计划与原始文件",
    confidence_note="先用入选主因判断今天值不值得继续跟。",
    updated_at=(screening_batch or {}).get("generated_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
)
```

- [ ] **Step 5: Run the detail-surface consistency test again**

Run: `./.venv/bin/pytest -q apps/control-panel/tests/test_app_smoke.py -k canonical_main_conclusion_contract`
Expected: PASS

- [ ] **Step 6: Commit the stock-detail migration**

```bash
git add apps/control-panel/dashboard_data.py apps/control-panel/templates/today_watchlist_detail.html apps/control-panel/templates/today_candidate_detail.html apps/control-panel/tests/test_app_smoke.py
git commit -m "feat: unify stock detail surfaces on canonical decision"
```

## Task 4: Make Today Consume Canonical Stock Decision Summaries

**Files:**
- Modify: `apps/control-panel/dashboard_data.py`
- Modify: `apps/control-panel/templates/today.html`
- Test: `apps/control-panel/tests/test_app_smoke.py`

- [ ] **Step 1: Write the failing test that Today top rows include canonical action tier and canonical main conclusion semantics**

```python
def test_today_rows_use_canonical_decision_summary_fields(self) -> None:
    today = build_today_view()
    rows = today.get("primary_actions") or []
    self.assertTrue(rows)
    for row in rows:
        self.assertIn(row.get("tier"), {"立即执行", "等触发", "仅观察", "明确回避"})
        self.assertTrue(str(row.get("action") or "").strip())
        self.assertTrue(str(row.get("reason") or "").strip())
```

- [ ] **Step 2: Run the Today summary test to verify whether the current row contract is insufficient**

Run: `./.venv/bin/pytest -q apps/control-panel/tests/test_app_smoke.py -k canonical_decision_summary_fields`
Expected: FAIL or expose missing row semantics that still come from mixed queue state.

- [ ] **Step 3: Add a helper that converts canonical stock decisions into Today rows**

```python
def canonical_decision_to_today_row(decision: dict[str, Any], *, title: str, url: str | None, freshness: Any) -> dict[str, Any]:
    return {
        "title": title,
        "action": decision.get("next_step") or decision.get("main_conclusion"),
        "tier": decision.get("action_tier"),
        "trigger": decision.get("trigger_condition"),
        "reason": decision.get("why_now"),
        "risk": decision.get("avoid_action") or decision.get("stop_condition"),
        "freshness": detail_value(freshness),
        "url": url,
        "tone": infer_decision_tone_from_main_conclusion(decision.get("main_conclusion")),
    }
```

- [ ] **Step 4: Use canonical decision summaries to populate Today holdings and opportunity rows where stock detail data already exists**

```python
holdings_rows = [
    canonical_decision_to_today_row(
        build_watchlist_stock_decision(item, screening_batch, confirmation),
        title=f"{detail_value(item.get('name'))} {detail_value(item.get('code'))}",
        url=today_watchlist_detail_url(item.get("code")),
        freshness=(watchlist or {}).get("generated_at"),
    )
    for item in prioritized_holdings[:3]
]
```

- [ ] **Step 5: Run the Today summary test again**

Run: `./.venv/bin/pytest -q apps/control-panel/tests/test_app_smoke.py -k canonical_decision_summary_fields`
Expected: PASS

- [ ] **Step 6: Commit the Today canonical-summary pass**

```bash
git add apps/control-panel/dashboard_data.py apps/control-panel/templates/today.html apps/control-panel/tests/test_app_smoke.py
git commit -m "feat: feed today rows from canonical decisions"
```

## Task 5: Add Decision Transition Records For Review

**Files:**
- Modify: `apps/control-panel/dashboard_data.py`
- Modify: `apps/control-panel/templates/review.html`
- Test: `apps/control-panel/tests/test_app_smoke.py`

- [ ] **Step 1: Write the failing test for review-level conclusion transition records**

```python
def test_review_exposes_decision_transition_records(self) -> None:
    review = build_review_view()
    transitions = review.get("decision_transitions") or []
    self.assertIsInstance(transitions, list)
    if transitions:
        sample = transitions[0]
        for key in ("code", "name", "from_conclusion", "to_conclusion", "reason", "changed_at"):
            self.assertIn(key, sample)
```

- [ ] **Step 2: Run the review transition test to verify it fails**

Run: `./.venv/bin/pytest -q apps/control-panel/tests/test_app_smoke.py -k decision_transition_records`
Expected: FAIL because review currently has no canonical transition record structure.

- [ ] **Step 3: Add a minimal transition builder that compares current conclusion snapshots across available history sources**

```python
def build_decision_transition_records(...) -> list[dict[str, Any]]:
    return [
        {
            "code": code,
            "name": name,
            "from_conclusion": previous_main_conclusion,
            "to_conclusion": current_main_conclusion,
            "reason": reason,
            "changed_at": changed_at,
        }
        for ... in compared_rows
        if previous_main_conclusion and current_main_conclusion and previous_main_conclusion != current_main_conclusion
    ]
```

- [ ] **Step 4: Render a compact Review section for “结论变化” using the transition records**

```jinja2
{% if review.decision_transitions %}
<section class="review-section">
  <div class="section-head">
    <div>
      <p class="eyebrow">结论变化</p>
      <h2>最近哪些判断变了</h2>
    </div>
  </div>
  <div class="review-transition-list">
    {% for item in review.decision_transitions %}
    <article class="review-transition-card">
      <h3>{{ item.name }} {{ item.code }}</h3>
      <p>{{ item.from_conclusion }} -> {{ item.to_conclusion }}</p>
      <p>{{ item.reason }}</p>
      <p>{{ item.changed_at }}</p>
    </article>
    {% endfor %}
  </div>
</section>
{% endif %}
```

- [ ] **Step 5: Run the review transition test again**

Run: `./.venv/bin/pytest -q apps/control-panel/tests/test_app_smoke.py -k decision_transition_records`
Expected: PASS

- [ ] **Step 6: Commit the review transition layer**

```bash
git add apps/control-panel/dashboard_data.py apps/control-panel/templates/review.html apps/control-panel/tests/test_app_smoke.py
git commit -m "feat: add canonical decision transition records"
```

## Task 6: Run Full Verification And Clean Up Contract Drift

**Files:**
- Modify: `apps/control-panel/dashboard_data.py`
- Modify: `apps/control-panel/tests/test_app_smoke.py`
- Modify: `docs/superpowers/specs/2026-04-22-prism-decision-protocol-design.md`

- [ ] **Step 1: Run the full suite after all migrations**

Run: `./.venv/bin/pytest -q`
Expected: PASS with the full app smoke suite green.

- [ ] **Step 2: Review failing or brittle assertions and fix protocol drift, not just symptoms**

```python
# Example cleanup direction:
# if a page still renders competing top-level conclusion strings,
# fix the canonical adapter or normalizer rather than weakening the test.
```

- [ ] **Step 3: Re-run the full suite and confirm green output again**

Run: `./.venv/bin/pytest -q`
Expected: PASS twice in a row without new drift.

- [ ] **Step 4: Update the spec only if implementation forced a real protocol change**

```markdown
## Implementation Note

If execution showed that `减仓观望` should map to `卖出` in the canonical layer but remain `先减仓观望` in the execution wording layer, document that explicitly in the protocol spec.
```

- [ ] **Step 5: Commit the verification and drift cleanup pass**

```bash
git add apps/control-panel/dashboard_data.py apps/control-panel/tests/test_app_smoke.py docs/superpowers/specs/2026-04-22-prism-decision-protocol-design.md
git commit -m "test: lock decision protocol behavior"
```
