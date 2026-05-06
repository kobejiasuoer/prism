# Prism Free-Source FS-4A Redacted Report Generator Result

Date: 2026-04-30
Scope: redacted metadata to repo-safe Markdown generator
Status: completed

## 0. Boundary

FS-4A added a pure Markdown report generator for already-redacted free-source endpoint metadata. It does not call BaoStock or AKShare, does not import provider or network libraries, does not install dependencies, does not read repo-external raw archive content, does not write `data/quant`, and does not generate formal labels, formal excess return, formal adjusted return, or execution-realistic backtest outputs.

BaoStock and AKShare remain a research-only, free-source route. Free callable access still does not imply redistribution rights, and raw vendor data must remain out of the repo.

## 1. Files

FS-4A added:

- `packages/quant/free_sources/report_generator.py`
- `tests/test_quant_free_source_report_generator.py`
- `docs/quant-upgrade-free-source-fs4a-redacted-report-generator-result-2026-04-30.md`

FS-4A also made one compatibility update to existing guardrails:

- `tests/test_quant_free_source_guardrails.py`

Reason: the prior FS-2 guardrail explicitly rejected `packages/quant/free_sources/report_generator.py`. FS-4A now approves that file as a pure redacted Markdown generator, so the stale disallow-list was narrowed to continue blocking live adapters/runners while allowing the FS-4A pure generator.

No existing `free_sources` module was modified for exports.

## 2. Implemented Behavior

`generate_redacted_report(...)` accepts a redacted endpoint summary, a list of summaries, or a mapping containing endpoint summaries. It returns a Markdown string containing only:

- provider
- endpoint
- status
- row_count
- field_list
- non_null_summary
- response hash
- retrieved_at
- error_summary
- research-only notes
- blocker notes

The generator rejects unsafe input before rendering:

- raw row keys such as `rows`, `ohlcv_rows`, and `suspend_event_rows`
- raw payload keys such as `raw_response`, `payload`, `csv`, `html`, and `dataframe`
- complete calendar / stock-list style keys
- secret-like keys such as `token`, `cookie`, `session`, and `authorization`
- unsafe raw archive pointers
- local absolute paths and raw archive URLs in reportable values
- formal-ready or production-ready claims

The module is pure: it does not read files, write files, or read environment variables.

## 3. Test Coverage

Synthetic-only tests cover:

- valid redacted endpoint metadata rendering to Markdown
- list and collection mapping inputs
- rejection of raw payload / row-level data
- rejection of unsafe raw archive pointers
- rejection of local paths, URLs, and formal-ready claims
- no provider imports
- no network imports
- no `data/quant` writes

The requested suite passed after the guardrail compatibility update:

```text
74 passed in 0.06s
```

## 4. Still Blocked

FS-4A does not change the blocked status of:

- formal labels
- formal excess return
- formal adjusted return
- execution-realistic backtest
- limit up/down price
- failed order
- partial fill
- production sorting
- A/B/C
- page work
- Prism Edge
- Expected 5D
- ML

QFQ, benchmark, `tradestatus` / `isST`, and suspend-event metadata remain candidate / research-only / partial evidence only.

## 5. Next Step Gate

If a repeatable live smoke runner is desired, it must be planned separately as FS-4B or FS-5, stay repo-external, and keep raw vendor data out of the repo. FS-4A does not authorize live provider calls, dependency changes, raw archive reads, production integration, or formal output generation.

