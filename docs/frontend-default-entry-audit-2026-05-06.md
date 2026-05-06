# Frontend default-entry audit (2026-05-06)

## Scope

P3.3 from `docs/claude-development-handoff-2026-05-04.md` — confirm that
`apps/web` is the practical default operator entry and identify any
remaining places where an operator is forced back to old control-panel
pages on a daily basis.

## Method

1. Enumerate every route the FastAPI control panel exposes.
2. Map each to the corresponding `apps/web` page (or absence thereof).
3. Classify each as **daily** (operator hits it every trading day),
   **occasional** (drill-in, troubleshooting), or **deprecated**.
4. Call out gaps that block "new frontend as default entry."

## Route parity matrix

| Old control-panel route | New `apps/web` route | Class | Parity |
|---|---|---|---|
| `/` (dashboard) | `/` (command center) | daily | ✅ |
| `/today` | `/` | daily | ✅ |
| `/watchlist` | `/portfolio` | daily | ✅ now with day-over-day diff |
| `/watchlist/{code}` | `/stock/[code]` | daily | ✅ |
| `/today/watchlist/{code}` | `/stock/[code]` | daily | ✅ |
| `/opportunities` | `/discovery` | daily | ✅ |
| `/opportunities/{code}` | `/stock/[code]` | daily | ✅ |
| `/today/candidates/{code}` | `/stock/[code]` | daily | ✅ |
| `/parameters` | `/settings` | weekly | ✅ now with evaluation gate + unsafe_apply |
| `/review` | `/review` | weekly | ✅ |
| `/review/detail` | drill-in inside `/review` | weekly | ✅ |
| `/ask` | embedded in `/stock/[code]` | daily | ✅ |
| `/today/batch/{kind}` (`screener` or `confirmation`) | — | occasional | ⚠️ no dedicated web page |
| `/opportunities/batch/{kind}` | — | occasional | ⚠️ no dedicated web page |
| `/artifacts` | — | occasional | ⚠️ no dedicated web page |
| `/healthz` | n/a | n/a | n/a (probe) |

## Gaps

Three routes still require falling back to the old control panel:

1. **`/today/batch/{kind}`** and **`/opportunities/batch/{kind}`** —
   render the full screener / confirmation batch behind a single drill
   link. Operators only need them when investigating *why* a batch
   shrank or expanded; not a daily must-have. Frequency: a few times
   per week, typically after a midday verification surprise.

2. **`/artifacts`** — flat listing of every generated report file. Used
   for spot-checking whether a specific run wrote what it should have.
   Engineering-grade, not operator-grade. Frequency: <1× per week.

None of these gaps block the operator's daily flow. The four-route nav
(`指挥中心 / 持仓管理 / 发现观察 / 复盘`) plus footer `/settings` covers
every signal the operator reads to make decisions today.

## Conclusion

`apps/web` is the practical default entry as of this commit. The old
control panel survives as:

- **Fallback** for the three occasional drill-ins above.
- **Server** for `/api/*` endpoints — the new frontend consumes these,
  it does not duplicate them.

No P3.3 code change is required. If the gaps above start showing up in
the daily operator flow (signal: operators bookmarking the old `/today/batch`
URL), we can revisit and build dedicated `apps/web` pages for them — but
that is P4 territory, not P3.

## Verification

- All routes inspected: `grep -E "^@app\.(get|post)" apps/control-panel/app.py`
- All web pages inspected: `find apps/web/src/app -name 'page.tsx'`
- Sidebar nav: `apps/web/src/components/sidebar.tsx::navItems`
