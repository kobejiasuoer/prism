# Remaining Dirty Worktree Inventory - 2026-04-30

## Scope

This inventory was produced after the three quant-upgrade commits were completed. It is a read-only classification of the remaining dirty worktree, except for this documentation file itself.

Commands inspected:

- `git status --short`
- `git diff --name-status`
- `git diff --stat`
- `git ls-files --others --exclude-standard`
- Targeted `git diff -- <path>` for representative code/config/state files
- Filename-only sensitive-pattern scans for token, secret, API key, raw vendor archive, account screenshot, and points screenshot risks

No files were staged, committed, deleted, reset, or cleaned during this inventory.

## Executive Summary

| Area | Count | Status | Recommendation |
| --- | ---: | --- | --- |
| Tracked modified files | 177 | Dirty | Split by category; do not batch commit |
| Untracked files | 29 | Dirty | Mostly generated runtime/cache/report files |
| Staged files | 0 | Clean | No staged diff at inventory time |
| `apps/*` dirty entries | 20 | Mixed code and runtime state | Human confirm before any commit |
| `data/*` dirty entries | 1 | Generated report snapshot | Human confirm |
| `stock-analyzer/*` dirty entries | 23 | Code/config plus cache data | Split code from cache |
| `stock-screener/*` dirty entries | 162 | Generated/history outputs | Do not submit by default |

High-risk scan result: no token-like assignment, raw vendor archive path, account screenshot, or points screenshot file was found in the remaining dirty tracked diff or untracked file list. No Tushare raw vendor data appears to be inside the repo dirty set.

## 1. App / Frontend / Control Panel Code Changes

Recommendation: **human confirm, then submit as a separate app/control-panel PR if intentional**.

Files:

- `apps/control-panel/dashboard_data.py`
- `apps/control-panel/tests/test_app_smoke.py`
- `apps/control-panel/tests/test_stock_mvp_first_screen_contract.py`
- `apps/scripts/prism_canonical.py`
- `apps/web/src/app/discovery/page.tsx`
- `apps/web/src/app/page.tsx`
- `apps/web/src/app/portfolio/page.tsx`
- `apps/web/src/lib/types.ts`

Observed intent:

- Adds `display_date` to today/watchlist/opportunities payloads and frontend display fallbacks.
- Shows a badge when display date differs from underlying trade date.
- Teaches dashboard/canonical lookup code to search both the newer `packages/data` location and the older `stock-screener/data` location.
- Sorts matching artifacts more deterministically from timestamps embedded in filenames.
- Adds/updates tests for the new `display_date` contract.
- `test_app_smoke.py` also adds coverage for `stock-analyzer/scripts/fetch.py` market/Sina-code normalization.

Submit guidance:

- Submit only after the owner confirms this is a real frontend/control-panel change, not incidental local experimentation.
- Keep separate from generated `apps/data/*`, `apps/reports/*`, and `stock-screener/data/*`.
- Suggested checks before submit:
  - `./.venv/bin/pytest apps/control-panel/tests/test_app_smoke.py apps/control-panel/tests/test_stock_mvp_first_screen_contract.py`
  - Frontend type/lint/build command used by this repo, if available.

## 2. Runtime / Current-State Data

Recommendation: **do not submit by default**.

Files:

- `apps/data/control_panel_state/ask_recent_queries.json`
- `apps/data/control_panel_state/refresh_state.json`
- `apps/data/control_panel_runs/watchlist_refresh_20260424_151055_195809.json` *(untracked)*

Observed intent:

- Captures local recent queries and refresh timestamps/current page state.
- Includes current run state rather than durable source code or reproducible test fixture data.

Submit guidance:

- Do not include in an app code PR.
- Preserve locally only if the operator wants this exact UI/runtime state.
- If these files should not be versioned long term, consider adding or tightening ignore rules in a later hygiene task, after owner approval.

## 3. `stock-screener` Run Artifacts Or Historical Data

Recommendation: **do not submit by default; human confirm only if these are intended canonical snapshots**.

Tracked modified groups:

- `stock-screener/data/ai_history/*.json` - 56 files
- `stock-screener/data/research_backfill/ai_history/*.json` - 57 files
- `stock-screener/data/stale_outputs/*.json` - 47 files
- `stock-screener/data/ai_screening_result.json` - 1 file
- `stock-screener/data/scan_result.json` - 1 file

Observed scale:

- `stock-screener` accounts for 162 dirty entries.
- Overall diff stat is large: 177 tracked modified files with 54,371 insertions and 8,802 deletions, mostly from these generated JSON artifacts.

Submit guidance:

- Keep out of app/control-panel or stock-analyzer code commits.
- If the owner wants to preserve a data snapshot, make a dedicated generated-data PR with explicit provenance and review expectations.
- Otherwise treat as runtime/history output and leave unsubmitted or discard manually later.

## 4. `stock-analyzer` Cache / Config / Script Changes

Recommendation: **split code/config from cache; human confirm code/config**.

Code/config files:

- `stock-analyzer/scripts/fetch.py`
- `stock-analyzer/config/stocks.json`

Observed intent:

- `fetch.py` normalizes `market` and `sina` fields in `load_config`.
- `fetch.py` also normalizes market/Sina code before fetching each stock in `main`.
- `stocks.json` changes `news_count` from `5` to `6`.

Code/config submit guidance:

- Submit only after owner confirms the behavior change is desired.
- Because `apps/control-panel/tests/test_app_smoke.py` now tests `fetch.py`, consider committing the app smoke-test change and `stock-analyzer/scripts/fetch.py` together, or split carefully so tests remain coherent.

Cache/data files:

- Tracked:
  - `stock-analyzer/data/fund_flow_cache/sh600690.json`
  - `stock-analyzer/data/fundamentals_cache/sh600690.json`
- Untracked:
  - `stock-analyzer/data/daily_snapshots/2026-04-27.json`
  - `stock-analyzer/data/fund_flow_cache/{sh600392,sh600760,sh601021,sh605589,sz000625,sz000977,sz002812,sz002938,sz300750}.json`
  - `stock-analyzer/data/fundamentals_cache/{sh600392,sh600760,sh601021,sh605589,sz000625,sz000977,sz002812,sz002938,sz300750}.json`

Cache/data submit guidance:

- Do not submit by default.
- Treat as local fetch/cache output unless a separate data snapshot decision is made.

## 5. Command Brief / Report Artifacts

Recommendation: **human confirm for report snapshot; do not submit runtime brief outputs by default**.

Tracked:

- `data/history/reports/command_brief/feishu-quality-dashboard.md`

Untracked:

- `apps/data/command_brief/prism_command_brief_2026-04-27_21-50-54.json`
- `apps/data/command_brief/prism_command_brief_2026-04-27_21-53-22.json`
- `apps/data/command_brief/prism_command_brief_2026-04-27_22-01-01.json`
- `apps/reports/prism_command_brief_2026-04-27_21-50-54.md`
- `apps/reports/prism_command_brief_2026-04-27_21-50-54.txt`
- `apps/reports/prism_command_brief_2026-04-27_21-53-22.md`
- `apps/reports/prism_command_brief_2026-04-27_21-53-22.txt`
- `apps/reports/prism_command_brief_2026-04-27_22-01-01.md`
- `apps/reports/prism_command_brief_2026-04-27_22-01-01.txt`

Observed intent:

- `feishu-quality-dashboard.md` appears to be a generated or manually refreshed dashboard/report snapshot.
- `apps/data/command_brief/*` and `apps/reports/*` are timestamped command brief outputs.

Submit guidance:

- Submit `feishu-quality-dashboard.md` only if this exact report snapshot is intended for version control.
- Do not include timestamped command brief outputs in code PRs.

## 6. Human Modifications To Preserve

Recommendation: **preserve until owner decision; do not discard automatically**.

Likely intentional source/config changes:

- `apps/control-panel/dashboard_data.py`
- `apps/control-panel/tests/test_app_smoke.py`
- `apps/control-panel/tests/test_stock_mvp_first_screen_contract.py`
- `apps/scripts/prism_canonical.py`
- `apps/web/src/app/discovery/page.tsx`
- `apps/web/src/app/page.tsx`
- `apps/web/src/app/portfolio/page.tsx`
- `apps/web/src/lib/types.ts`
- `stock-analyzer/scripts/fetch.py`
- `stock-analyzer/config/stocks.json`

Human-confirm report change:

- `data/history/reports/command_brief/feishu-quality-dashboard.md`

These should not be cleaned or reset without explicit owner approval.

## 7. Ignorable Or Non-Submit Runtime Caches

Recommendation: **do not submit; leave local or discard manually after confirmation**.

Runtime/cache/generated groups:

- `apps/data/control_panel_state/*`
- `apps/data/control_panel_runs/*`
- `apps/data/command_brief/*`
- `apps/reports/prism_command_brief_*`
- `stock-analyzer/data/fund_flow_cache/*`
- `stock-analyzer/data/fundamentals_cache/*`
- `stock-analyzer/data/daily_snapshots/*`
- `stock-screener/data/ai_history/*`
- `stock-screener/data/research_backfill/ai_history/*`
- `stock-screener/data/stale_outputs/*`
- `stock-screener/data/ai_screening_result.json`
- `stock-screener/data/scan_result.json`

These are high-volume and/or timestamped outputs. They should not ride along with code commits.

## 8. High-Risk Items

Sensitive-risk scan result:

- No dirty tracked file matched the filename-only scan for token-like assignment, API key, secret assignment, password, raw vendor archive path, account screenshot, or points screenshot.
- No untracked file matched the same risk scan.
- No repo-local raw Tushare vendor data path was present in the untracked file list.

Residual risk:

- Some generated JSON artifacts may contain market data or vendor-derived scrape/cache results from existing project workflows. They are not identified as raw Tushare POC output, but they should still be reviewed before any data snapshot commit.
- Do not run broad content-printing secret scans that echo matching lines. Use filename-only or redacted scans if further inspection is needed.

## Recommended Next Commit Split

1. **Commit D: App/control-panel display-date and data-location normalization**
   - Candidate paths: `apps/control-panel/*`, `apps/scripts/prism_canonical.py`, `apps/web/src/*`.
   - Include only source and tests.
   - Exclude `apps/data/*`, `apps/reports/*`, and all generated JSON.
   - Human confirmation required because this is outside the quant-upgrade commits.

2. **Commit E: Stock-analyzer fetch normalization**
   - Candidate paths: `stock-analyzer/scripts/fetch.py`, possibly `stock-analyzer/config/stocks.json`.
   - Coordinate with `apps/control-panel/tests/test_app_smoke.py`, which now includes a fetch-normalization test.
   - Exclude `stock-analyzer/data/*` cache files.

3. **Optional Commit F: Report snapshot**
   - Candidate path: `data/history/reports/command_brief/feishu-quality-dashboard.md`.
   - Submit only if this report is intentionally curated.

4. **Excluded from commits unless separately approved**
   - `stock-screener/data/*` generated/history outputs.
   - `stock-analyzer/data/*` cache files.
   - `apps/data/*` runtime state and command brief JSON.
   - `apps/reports/prism_command_brief_*` timestamped reports.

## Final Recommendation

Do not commit the remaining dirty worktree as one batch. The safest path is:

1. Preserve source/config changes for human review.
2. Keep generated runtime/cache/current-state files out of code commits.
3. If any generated data must be kept, isolate it in a dedicated generated-data review with provenance and no secrets.
4. Continue to avoid staging raw vendor data, tokens, account screenshots, points screenshots, and repo-external POC archives.
