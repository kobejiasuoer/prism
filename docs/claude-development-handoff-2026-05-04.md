# Prism Claude Development Handoff

Date: 2026-05-04
Project: `prism`
Current branch at handoff: `codex/ask-v2`
Audience: Claude taking over day-to-day development

## 0. Purpose

This document is the practical development handoff for Claude.

It is not a long-term product vision memo. It is a working execution guide:

- what is already real in the repo
- what is still incomplete
- what Claude should build next
- what Claude must not accidentally break
- what files are safe to touch
- what files should not be staged or committed

Primary goal for the next developer:

1. stabilize the repo
2. finish the highest-value incomplete engineering work
3. keep generated/runtime artifacts out of source commits
4. avoid expanding scope into product fantasies or quant overclaims

---

## 1. Current Snapshot

As of 2026-05-04, Prism is no longer a loose collection of scripts.
The repo already contains a real operating skeleton:

- `apps/web/`: Next.js frontend, now the intended main operator surface
- `apps/control-panel/`: FastAPI API and composition layer
- `packages/screener/`: scan, AI screening, midday verification, lifecycle
- `packages/quant/`: report-only / research-only quant spine plus free-source route work
- `stock-analyzer/`: watchlist snapshot / fetch pipeline
- `data/history/`: scrubbed historical artifacts

Important reality:

- the new frontend is mostly real and usable
- the stock profile page, follow-up flow, watchlist management, settings editor, run logs, preview drawer, and evidence/refresh loop already exist
- quant P1-A mainline has already been documented as closed at the documentation/control level
- free-source route has advanced into FS-4B repeatable smoke runner work, but that work is still dirty/uncommitted in the current tree

Key reference docs:

- `README.md`
- `docs/architecture/system.md`
- `docs/remaining-dirty-worktree-inventory-2026-04-30.md`
- `docs/frontend-followup-requirements-2026-04-24.md`
- `docs/quant-upgrade-master-progress-and-handoff-2026-04-29.md`
- `docs/quant-upgrade-free-source-fs4b-repeatable-live-smoke-result-2026-05-01.md`

---

## 2. Verified Facts At Handoff

These facts were verified locally at handoff time. Claude should assume them unless new evidence appears.

### 2.1 Verification status

- `apps/web` typecheck passes with:
  - `npm run typecheck`
- full repo pytest does **not** currently pass cleanly:
  - `./.venv/bin/pytest -q`
- the only observed failing test at handoff was:
  - `tests/test_secret_scrub.py::test_repo_has_no_committed_secret_or_privacy_markers`
- the failure was caused by:
  - local file `.prism-control.log`
  - marker found: `~`

### 2.2 Important implication

This is not a core business-logic regression.
It is a repo hygiene / scrub-test interaction problem.

Claude should fix it carefully without weakening the privacy test broadly.

### 2.3 Dirty worktree shape

The current dirty tree is dominated by generated outputs, not source edits.

Approximate dirty distribution at handoff:

- `stock-screener`: 162 entries
- `stock-analyzer`: 22 entries
- `apps/data` + `apps/reports`: runtime/generated entries
- real frontend source still dirty in:
  - `apps/web/src/app/page.tsx`
  - `apps/web/src/components/app-shell.tsx`
  - `apps/web/src/components/sidebar.tsx`
  - `apps/web/src/styles/globals.css`
- real quant source still untracked in:
  - `packages/quant/free_sources/live_smoke_runner.py`
  - `tests/test_quant_free_source_live_smoke_runner.py`
  - `docs/quant-upgrade-free-source-fs4b-repeatable-live-smoke-result-2026-05-01.md`

---

## 3. Hard Rules Claude Must Follow

These are non-negotiable for this repo.

### 3.1 Git and commit hygiene

- Never use `git add .`
- Always stage explicit paths only
- Never batch-commit runtime files, generated data, caches, reports, and source code together
- Never reset or discard unrelated dirty files without explicit human approval
- Treat the worktree as user-owned unless a file is clearly part of your task

### 3.2 Generated files that should not ride along with code commits

Do not commit these by default:

- `stock-screener/data/**`
- `stock-analyzer/data/**`
- `apps/data/control_panel_state/**`
- `apps/data/control_panel_runs/**`
- `apps/data/command_brief/**`
- `apps/reports/**`
- `.prism-control.log`

### 3.3 Quant free-source guardrails

For the `packages/quant/free_sources` route:

- no raw vendor data in repo
- no `data/quant` writes
- no repo-local scratch for live smoke
- no top-level BaoStock or AKShare imports for dry-run code paths
- no production claims
- no formal labels
- no formal excess return
- no formal adjusted return
- no execution-realistic backtest claims
- no scope drift into ML, Prism Edge productization, A/B/C replacement, or page work under this free-source task line

### 3.4 Product/engineering discipline

- prefer finishing existing real workflows over creating new architecture
- do not rewrite `dashboard_data.py` just because it is large
- do not invent a second system when the current API already exists
- preserve current frontend routes:
  - `/`
  - `/portfolio`
  - `/discovery`
  - `/review`
  - `/settings`
  - `/stock/[code]`

---

## 4. What Is Already Done And Should Be Preserved

Claude should not re-open these as if they were still concept-only:

### 4.1 Frontend surfaces that are already real

- stock profile page with follow-up loop:
  - `apps/web/src/app/stock/[code]/page.tsx`
- watchlist management panel:
  - `apps/web/src/components/watchlist-manager-panel.tsx`
- evidence / refresh / preview loop:
  - `apps/web/src/components/evidence-panel.tsx`
- settings page with:
  - parameter editor
  - task launcher
  - run list
  - log preview
  - file preview
  - `apps/web/src/app/settings/page.tsx`

### 4.2 Backend API surfaces that already exist

Do not replace these with new APIs unless absolutely necessary:

- `/api/ask`
- `/api/ask/suggest`
- `/api/ask/followup`
- `/api/watchlist/manage/add`
- `/api/watchlist/manage/archive`
- `/api/watchlist/manage/restore`
- `/api/parameters`
- `/api/tasks/{task_name}/run`
- `/api/runs`
- `/api/runs/{run_id}`
- `/api/runs/{run_id}/log`
- `/api/preview`
- `/api/refresh/status`
- `/api/refresh/trigger`

### 4.3 Quant free-source FS-4B implementation exists locally

There is already concrete code and tests for FS-4B:

- `packages/quant/free_sources/live_smoke_runner.py`
- `tests/test_quant_free_source_live_smoke_runner.py`
- `docs/quant-upgrade-free-source-fs4b-repeatable-live-smoke-result-2026-05-01.md`

Treat this as real unfinished work to stabilize and submit, not as a greenfield design exercise.

---

## 5. Priority Backlog For Claude

This is the recommended execution order.

## P0. Repo Health And Commit Hygiene

### Task P0.1: Make the repo baseline verifiable again

Goal:

- restore a clean verification baseline so source work can proceed without false failures

Current problem:

- `./.venv/bin/pytest -q` fails because `.prism-control.log` is scanned by `tests/test_secret_scrub.py`

Files likely involved:

- `tests/test_secret_scrub.py`
- `.gitignore`
- any local runtime/log path configuration that writes `.prism-control.log` into repo root

What Claude should do:

- identify the least dangerous fix
- prefer fixing the local-log handling over weakening privacy coverage
- acceptable solutions include:
  - moving the control log outside the repo
  - excluding a clearly local runtime log from the scan with narrow justification
  - tightening ignore/placement behavior so the log is no longer part of repo-local verification noise
- do **not** broadly relax `BAD_MARKERS`
- do **not** make the scrub test stop scanning meaningful source/doc files

Done when:

- `./.venv/bin/pytest -q` passes
- privacy test remains meaningful

Verification:

- `./.venv/bin/pytest -q`

Notes:

- plain `pytest` was not on shell `PATH` at handoff, so use `./.venv/bin/pytest`

### Task P0.2: Split source work from generated artifacts

Goal:

- create a sane source-only commit path

What Claude should do:

- separate dirty worktree into:
  - source changes worth keeping
  - generated/runtime files that should stay uncommitted
- maintain the classification from:
  - `docs/remaining-dirty-worktree-inventory-2026-04-30.md`

High-value source groups currently visible:

- web command-center redesign:
  - `apps/web/src/app/page.tsx`
  - `apps/web/src/components/app-shell.tsx`
  - `apps/web/src/components/sidebar.tsx`
  - `apps/web/src/styles/globals.css`
- quant FS-4B runner:
  - `packages/quant/free_sources/live_smoke_runner.py`
  - `tests/test_quant_free_source_live_smoke_runner.py`
  - `docs/quant-upgrade-free-source-fs4b-repeatable-live-smoke-result-2026-05-01.md`

Human-confirm-only files:

- `stock-analyzer/config/stocks.json`
- `data/history/reports/command_brief/feishu-quality-dashboard.md`

Do not silently commit:

- `stock-screener/data/**`
- `stock-analyzer/data/**`
- `apps/data/**`
- `apps/reports/**`

Done when:

- source changes are staged/organized independently from generated outputs
- no code PR includes the large runtime data diff

---

## P1. Stabilize And Submit Existing Real Development Work

### Task P1.1: Finish and verify the new command-center homepage

Goal:

- stabilize the large homepage redesign already in progress

Files:

- `apps/web/src/app/page.tsx`
- `apps/web/src/components/app-shell.tsx`
- `apps/web/src/components/sidebar.tsx`
- `apps/web/src/styles/globals.css`

What Claude should do:

- review the new command-center layout for regressions
- preserve the stronger design direction already introduced
- verify navigation, layout, and data rendering on desktop and mobile
- ensure it does not break shared app shell behavior
- keep parity with the broader “new frontend as default entry” direction

Done when:

- homepage renders without obvious UI breakage
- navigation still works
- loading/skeleton/error states still make sense
- mobile layout is usable
- typecheck passes

Verification:

- `cd apps/web && npm run typecheck`
- manual browser QA via local app

Important caution:

- do not regress already-working pages:
  - `/stock/[code]`
  - `/portfolio`
  - `/discovery`
  - `/review`
  - `/settings`

### Task P1.2: Formalize FS-4B free-source smoke runner

Goal:

- stabilize and submit the existing FS-4B implementation already present in the dirty tree

Files:

- `packages/quant/free_sources/live_smoke_runner.py`
- `tests/test_quant_free_source_live_smoke_runner.py`
- `docs/quant-upgrade-free-source-fs4b-repeatable-live-smoke-result-2026-05-01.md`

What Claude should do:

- review the runner against the existing FS-3/FS-4A guardrails
- make sure imports, default mode, scratch root rules, and renderer safety are coherent
- ensure tests cover the intended behavior
- submit this as quant source work only, not mixed with unrelated app/runtime files

Done when:

- the runner is clean, reviewed, and test-backed
- no repo-local raw output behavior exists
- no dependency mutation is introduced

Verification:

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages ./.venv/bin/python -m pytest tests/test_quant_free_source_manifest.py tests/test_quant_free_source_mapping.py tests/test_quant_free_source_guardrails.py tests/test_quant_free_source_report_generator.py tests/test_quant_free_source_live_smoke_runner.py -q -p no:cacheprovider`

Important caution:

- keep the current blocked-status language intact
- do not turn research-only tooling into production claims

---

## P2. Highest-Value Incomplete Engineering Work

These are the real functional gaps still worth building next.

### Task P2.1: Remove the missing `backtest.py` dependency from watchlist technical scoring

Why this matters:

- `stock-analyzer/scripts/fetch.py` still dynamically imports a sibling `backtest.py`
- that file is not present in the repo
- this means watchlist technical scoring is not truly reproducible or repo-owned

Problem location:

- `stock-analyzer/scripts/fetch.py`
- current dynamic import block is inside `fetch_technical_indicators()`

Goal:

- replace the path-based dynamic import with a repo-owned, testable scoring module

Suggested implementation shape:

- extract the required scoring logic into a real module inside the repo
- keep API narrow:
  - calculate indicators
  - calculate score / bias
  - expose deterministic outputs for snapshot generation
- explicitly degrade when enough inputs are not available

Suggested files:

- modify `stock-analyzer/scripts/fetch.py`
- add a new repo-owned helper module
- add focused tests

Done when:

- no runtime import of a nonexistent sibling `backtest.py`
- technical score fields are reproducible
- failure mode is explicit, not silent

Verification:

- targeted pytest for the new scoring helper
- existing watchlist-related smoke tests still pass

### Task P2.2: Expand midday verification coverage beyond morning A/B-only targets

Why this matters:

- `packages/screener/midday_verify.py` currently targets only shortlist items with `tier in ("A", "B")`
- on weak-market days this can make midday confirmation too empty to be useful

Current limitation:

- `targets = [item for item in shortlist if item.get("tier") in ("A", "B")][:8]`

Goal:

- keep the current confirmed/downgraded structure
- add meaningful “continue tracking” coverage when the market is weak or gate-limited

Files:

- `packages/screener/midday_verify.py`
- `apps/control-panel/dashboard_data.py`
- related tests in `apps/control-panel/tests/`

What Claude should do:

- widen midday verification coverage carefully
- preserve current contract for:
  - `confirmed`
  - `downgraded`
  - `fresh_candidates`
- make weak-day outputs still decision-useful

Done when:

- midday output is still structured
- weak-day runs retain actionable tracking coverage
- fresh candidates still include action-plan fields consistently

Verification:

- add/update contract tests
- validate generated output structure

### Task P2.3: Make the `30` / `68` opportunity-pool exclusion configurable

Why this matters:

- `packages/screener/scan.py` currently hard-excludes `30` and `68` codes in `_normalize_stage0_stock()`
- that locks the discovery universe in code rather than policy

Current limitation:

- `if code.startswith('68') or code.startswith('30'): return None`

Goal:

- move this from hardcoded behavior to explicit configuration
- preserve current behavior as default unless config says otherwise

Files:

- `packages/screener/scan.py`
- parameter/config layer, likely under:
  - `packages/stock_parameter_config.py`
  - current parameter JSON/config source
- tests

Done when:

- universe boundary is policy-driven
- default behavior is unchanged unless config is edited
- tests lock default and enabled behavior

Verification:

- targeted tests for normalization / inclusion rules
- no regression in existing screening flow

### Task P2.4: Add an evaluation gate to parameter save flow

Why this matters:

- new frontend already supports parameter editing
- backend currently validates JSON and writes directly to disk
- there is still no evaluation gate before parameter changes become active

Current state:

- `apps/control-panel/app.py` validates then writes `stocks.json`
- `apps/scripts/evaluate_stock_analysis.py` already exists as a scoring/evaluation layer

Goal:

- parameter changes should not silently become active without at least a basic evaluation result

Files:

- `apps/control-panel/app.py`
- `apps/scripts/evaluate_stock_analysis.py`
- possibly task/run plumbing if evaluation should execute via an internal run
- frontend settings surface only if needed to show results clearly

What Claude should do:

- design the smallest practical safety gate
- good minimum behavior:
  - save request parses and validates
  - evaluation is run or triggered
  - response includes evaluation/gate result
  - hard failures can block apply, or at minimum clearly label unsafe apply

Done when:

- parameter save path includes evaluation feedback
- users can see whether the new config passed historical validation
- no silent “write JSON and hope” path remains

Important caution:

- do not turn this into a huge workflow rewrite
- keep the first implementation simple and explicit

---

## P3. Secondary But Valuable Improvements

These are useful, but not before P0-P2.

### Task P3.1: Refine theme classification and reduce `其他`

Why:

- `packages/screener/scan.py` still falls back heavily to `其他`
- this weakens theme-level ranking and explanation quality

Goal:

- reduce the share of `其他`
- keep the system explainable
- do not overfit themes into a giant taxonomy rewrite

### Task P3.2: Add watchlist lifecycle / yesterday-vs-today diff

Why:

- discovery has lifecycle-style reasoning
- watchlist still lacks a clean “what changed since yesterday and why” path

Goal:

- make holdings changes auditable for action, position, and boundary shifts

Likely files:

- `apps/scripts/prism_canonical.py`
- `apps/control-panel/dashboard_data.py`
- relevant frontend pages

### Task P3.3: Final audit of “new frontend as default entry”

Why:

- most of the new frontend is already present
- but it still needs a final “do we still need to fall back to old control-panel pages daily?” audit

Goal:

- make `apps/web` the practical default operator entry
- keep old control-panel pages as fallback, not primary daily surface

---

## 6. Tasks Claude Should Not Start Yet

Unless explicitly re-scoped by the human owner, do **not** start these:

- new ML work
- Prism Edge productization claims
- A/B/C production replacement
- formal benchmark claims
- formal adjusted-return claims
- execution-realistic backtest claims
- free-source route production integration
- multi-market expansion
- large-scale architecture rewrite of `dashboard_data.py`
- major redesign of the entire web app beyond the already-started command-center work

---

## 7. Suggested Execution Sequence

Recommended order:

1. Fix repo verification baseline
2. Split source work from generated/runtime outputs
3. Stabilize homepage redesign
4. Formalize FS-4B runner and tests
5. Remove `backtest.py` dependency from watchlist technical scoring
6. Expand midday verification coverage
7. Make `30` / `68` inclusion configurable
8. Add evaluation gate to parameter saving
9. Only then consider P3 improvements

If Claude can only do one thing first, it should do:

1. repo health
2. then one isolated source task with clean verification

---

## 8. Verification Checklist For Each Task

For every meaningful code task, Claude should end with:

### Source verification

- run only the relevant targeted tests first
- then run broader verification if safe

### Web verification

- `cd apps/web && npm run typecheck`

### Repo verification

- `./.venv/bin/pytest -q`

### Commit hygiene

- stage explicit paths only
- verify staged diff before commit
- do not include generated data unintentionally

---

## 9. Known Open Human Decisions

Claude should not guess on these without checking if they become blocking:

- whether `stock-analyzer/config/stocks.json` `news_count` change from `5` to `6` is intentional
- whether `data/history/reports/command_brief/feishu-quality-dashboard.md` should be preserved as a committed snapshot
- whether parameter gate should hard-block writes on evaluation failure or allow explicit unsafe apply

If these decisions are not blocking a task, Claude should continue and leave them untouched.

---

## 10. Copy/Paste Kickoff Prompt For Claude

Use the following as the opening prompt if you want Claude to take over directly:

```text
You are taking over development of ~/Projects/prism.

Read ~/Projects/prism/docs/claude-development-handoff-2026-05-04.md first and follow it as the execution contract.

Your priorities are:
1. restore a clean verification baseline
2. keep generated/runtime artifacts out of commits
3. stabilize existing real source work before adding new scope

Start with P0 in the handoff doc.
Use explicit path staging only.
Do not use git add .
Do not commit stock-screener/data, stock-analyzer/data, apps/data, apps/reports, or repo-local runtime logs unless explicitly instructed.

When you finish each task:
- summarize what changed
- list the exact files touched
- list verification commands run
- list any remaining risks or human decisions
```

---

## 11. Short Version

If Claude only reads one page, the gist is:

- the repo is real, not greenfield
- frontend migration is mostly done
- FS-4B quant free-source work exists and should be stabilized, not reinvented
- biggest immediate engineering wins are:
  - repo baseline green
  - homepage stabilization
  - `backtest.py` dependency removal
  - midday coverage expansion
  - configurable universe boundary
  - parameter evaluation gate
- biggest failure mode to avoid is mixing source work with generated data and runtime artifacts

