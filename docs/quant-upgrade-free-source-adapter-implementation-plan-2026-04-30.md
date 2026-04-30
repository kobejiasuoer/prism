# Prism Free-Source Adapter Non-Production Implementation Plan

Date: 2026-04-30
Role: non-production implementation planner
Scope: planning only; no code
Status: docs-only implementation planning

Input documents:

- `docs/quant-upgrade-free-source-adapter-design-2026-04-30.md`
- `docs/quant-upgrade-free-source-adapter-design-acceptance-2026-04-30.md`
- `docs/quant-upgrade-free-data-source-field-poc-result-2026-04-30.md`
- `docs/quant-upgrade-free-data-source-field-poc-acceptance-2026-04-30.md`

## 0. Boundary

This document only plans possible future implementation. It does not approve implementation.

Strictly prohibited in this planning step:

- No code.
- No BaoStock or AKShare API calls.
- No dependency installation.
- No `packages/quant` writes.
- No `data/quant` writes.
- No dependency file, lockfile, or venv changes.
- No raw vendor data in repo.
- No formal labels.
- No formal excess return.
- No formal adjusted return.
- No execution-realistic backtest.
- No production sorting.
- No A/B/C changes.
- No page, Prism Edge, Expected 5D, or ML work.

## 1. Implementation Entry Decision

The first implementation card should start with **schema-only + synthetic tests**.

| Question | Planning answer |
| --- | --- |
| Should FS-1 start with schema-only + synthetic tests? | Yes. This is the safest first code card. |
| Should FS-1 contain any real provider call? | No. FS-1 must not import or call BaoStock / AKShare. |
| Should FS-1 install dependencies? | No. Default is no dependency change. |
| Should FS-1 write `data/quant`? | No. Default is no `data/quant` output. |
| Should FS-1 write raw vendor data? | No. It should use synthetic fixtures only. |
| Should FS-1 create pages or product surfaces? | No. Page route remains deferred. |
| Should FS-1 produce formal outputs? | No. Formal labels, adjusted return, excess return, and execution-realistic backtest remain blocked. |

Rationale:

- The design acceptance allows implementation planning, not direct implementation.
- The POC proved field availability only; it did not prove formal data readiness.
- Schema and synthetic tests can harden repo-safety before any provider adapter exists.
- A schema-only first card lets reviewers enforce no-network, no-raw-data, no-formal-output behavior at the lowest layer.

## 2. Recommended FS-1 File Scope

If a future code implementation card is approved, FS-1 may create `packages/quant/free_sources/*`, but only for schema, contracts, redaction, and synthetic tests.

Recommended exact FS-1 file range:

| Future path | Purpose | FS-1 allowed? | Guardrail |
| --- | --- | --- | --- |
| `packages/quant/free_sources/__init__.py` | Package marker and explicit non-production module docstring | Yes | No provider imports |
| `packages/quant/free_sources/manifest.py` | Redacted manifest schema, enums, validation helpers | Yes | No network, no vendor package imports |
| `packages/quant/free_sources/contracts.py` | Candidate field contract definitions and status constants | Yes | Synthetic / declarative only |
| `packages/quant/free_sources/redaction.py` | Repo-safety validation for manifest payloads | Yes | Reject raw rows and unsafe pointers |
| `tests/test_quant_free_source_manifest.py` | Synthetic tests for manifest validation and guardrails | Yes | No network, no vendor data |

Files FS-1 should not create:

| Future path | Reason |
| --- | --- |
| `packages/quant/free_sources/baostock_adapter.py` | Would invite real provider integration too early |
| `packages/quant/free_sources/akshare_adapter.py` | Would invite real provider integration too early |
| `packages/quant/free_sources/run_field_poc.py` | Live smoke is a separate card |
| `packages/quant/free_sources/report_generator.py` | Redacted report generation should wait for schema acceptance |
| Any `data/quant/**` path | Data output is not approved |
| Any page / app route | Page route remains deferred |

FS-1 should use only Python standard library unless the existing repo test stack already provides a dependency. No dependency or lockfile changes are allowed by default.

## 3. FS-1 Synthetic Model

FS-1 should model only redacted metadata, not market data rows.

Recommended manifest objects:

| Object | Required content |
| --- | --- |
| `FreeSourceProvider` | `baostock`, `akshare` |
| `ProviderRole` | `primary`, `cross_check`, `supplement` |
| `AdapterLayer` | `calendar`, `stock_basic`, `raw_daily`, `qfq_candidate`, `index_daily`, `tradestatus_isst`, `suspend_event`, `limit_candidate` |
| `ManifestStatus` | `available`, `partial`, `missing`, `empty`, `network_error`, `provider_error`, `license_blocked`, `blocked` |
| `PitAsOfStatus` | `as_collected_only`, `pit_weak`, `not_pit_ready`, `unknown` |
| `ResearchStatus` | `available`, `research_only`, `candidate`, `blocked` |
| `RedactedManifest` | provider, endpoint, params fingerprint, response hash, row count, field list, non-null summary, retrieved_at, source_version, license / usage note, raw_archive_pointer |

Forbidden synthetic fixture content:

- Actual OHLCV values.
- Actual qfq prices.
- Actual index values.
- Full trading calendars.
- Full stock lists.
- Suspend event rows.
- Limit pool constituents.
- Raw response bodies.
- Absolute local private archive paths.
- Token, cookie, session, account, or proxy values.

## 4. No-Network Guarantee

FS-1 tests must be provably no-network.

Recommended enforcement:

| Control | Requirement |
| --- | --- |
| No provider imports | Tests fail if `baostock` or `akshare` are imported by FS-1 modules |
| No network libraries | FS-1 modules should not import `requests`, `urllib`, `httpx`, `socket`, `curl_cffi`, or vendor SDKs |
| Synthetic fixtures only | Tests construct manifest dictionaries / dataclasses in memory |
| Optional socket block | Tests may monkeypatch `socket.socket` to raise if any network attempt occurs |
| No environment secrets | Tests must not read provider tokens, cookies, proxy settings, or private archive paths |
| No scratch dependency | Tests must pass without `/Users/yangbishang/.prism-private/free-data-poc/` existing |

Acceptance signal:

- Running the FS-1 test file should not require internet.
- Running the FS-1 test file should not require BaoStock or AKShare installed.
- Importing `packages.quant.free_sources` should not trigger provider imports.

## 5. No Raw Vendor Data Guarantee

FS-1 should implement redaction validation before any live adapter exists.

Manifest redaction rules:

| Risk | FS-1 behavior |
| --- | --- |
| Row-level price fields | Reject keys such as `rows`, `records`, `ohlcv_rows`, `prices`, `open_values`, `close_values` |
| Full calendar | Reject arrays of dates or date rows beyond summary counts |
| Full stock list | Reject arrays of symbols or security rows beyond counts |
| Raw payload | Reject `raw_response`, `payload`, `body`, `html`, `csv`, `dataframe`, `json_rows` |
| Unsafe archive pointer | Reject absolute paths like `/Users/...`, `file://`, `s3://` with credentials, HTTP URLs, or tokenized paths |
| Token-like data | Reject key names containing `token`, `cookie`, `session`, `password`, `secret`, `authorization` |

Allowed manifest data:

- Provider and endpoint names.
- Redacted params summary.
- Params fingerprint SHA256.
- Response hash SHA256.
- Row count.
- Field list.
- Missing field list.
- Non-null summary.
- Duplicate summary.
- Coverage summary counts.
- Retrieved timestamp.
- Source version.
- License / usage note.
- Opaque `raw_archive_pointer`.

## 6. No Formal Output Guarantee

FS-1 must model formal outputs as blocked or absent.

| Capability | FS-1 expected status |
| --- | --- |
| qfq price | `research_only` / `candidate` |
| adjusted return | `blocked` |
| benchmark index daily | `candidate` |
| benchmark return | `blocked` |
| excess return | `blocked` |
| formal labels | `blocked` |
| `tradestatus` / `isST` | `candidate` / `research_only` |
| suspend events | `partial` / `event_only` |
| limit up/down price | `blocked` |
| failed order | `blocked` |
| partial fill | `blocked` |
| execution-realistic backtest | `blocked` |

Test assertions should prove:

- No manifest schema contains fields named `formal_label`, `formal_excess_return`, `formal_adjusted_return`, `benchmark_return`, `excess_return`, `execution_realistic_return`, `failed_order`, or `partial_fill` as generated outputs.
- If such names appear in guardrail metadata, their status must be `blocked` or `not_generated`.
- QFQ and benchmark layers are candidates only.

## 7. No Production Impact Guarantee

FS-1 must not be connected to production flows.

| Surface | FS-1 rule |
| --- | --- |
| Production sorting | No imports from production sorting code; no ranking output |
| A/B/C | No A/B/C replacement, score, or tier output |
| Pages | No UI route, API route, frontend component, or template |
| Prism Edge | No Prism Edge module or feature flag |
| Expected 5D | No Expected 5D computation or display |
| ML | No model feature, dataset, training, inference, or calibration |
| Existing reports | No regeneration of current quant reports |

Suggested test guardrail:

- Tests should assert manifest modules expose metadata only.
- Tests should not import page, app, scorer, backtest, label, or production sorting modules.

## 8. Dependency, Venv, and Data Policy

| Policy area | Default decision |
| --- | --- |
| Dependency changes | Not allowed in FS-1 |
| Lockfile changes | Not allowed in FS-1 |
| Main project venv changes | Not allowed in FS-1 |
| BaoStock / AKShare installation | Not required and not allowed in FS-1 |
| `data/quant` output | Not allowed in FS-1 |
| Repo-external live smoke | Not included in FS-1 |
| Raw archive writes | Not included in FS-1 |

If a future card requires a dependency, it must be a separate dependency approval card. FS-1 should not need any new dependency.

## 9. FS-1 Acceptance Standards

FS-1 should pass only if all checks below pass:

| Acceptance item | Required standard |
| --- | --- |
| Synthetic manifest validation | A valid synthetic redacted manifest can be validated |
| Required manifest fields | provider, endpoint, params fingerprint, response hash, row_count, field list, non-null summary, retrieved_at, source_version, license note, raw_archive_pointer are required |
| Status enum coverage | `available`, `partial`, `missing`, `empty`, `network_error`, `provider_error`, `license_blocked`, `blocked` are covered |
| Unsafe pointer rejection | `raw_archive_pointer` rejects local absolute paths and URLs; accepts opaque pointers only |
| Row-level data rejection | Manifest rejects row-level行情字段, raw response bodies, full calendars, full stock lists, and vendor rows |
| Formal output blocking | qfq / benchmark / execution flags remain `research_only`, `candidate`, or `blocked`; no formal outputs are generated |
| No network tests | Tests pass without network and without importing provider packages |
| No dependency changes | No dependency file or lockfile changes |
| No `data/quant` writes | Test run leaves `data/quant` untouched |
| No production impact | No production sorting, A/B/C, page, Prism Edge, Expected 5D, ML, labels, backtests, or reports are generated |

Recommended test command for a future implementation card:

```text
python -m pytest tests/test_quant_free_source_manifest.py -q -p no:cacheprovider
```

The exact command may vary by repo test conventions, but it must remain no-network and synthetic-only.

## 10. Later Card Split

### Card FS-1: Manifest Schema + Synthetic Tests

Purpose:

- Create the minimal non-production schema surface.
- Validate redaction and guardrails before any provider code exists.

Allowed:

- `packages/quant/free_sources/__init__.py`
- `packages/quant/free_sources/manifest.py`
- `packages/quant/free_sources/contracts.py`
- `packages/quant/free_sources/redaction.py`
- `tests/test_quant_free_source_manifest.py`

Not allowed:

- Provider imports.
- Live calls.
- Dependency changes.
- `data/quant` writes.
- Formal outputs.
- Production / page / ML integration.

### Card FS-2: Provider Contract Mapping, Still Synthetic

Purpose:

- Add BaoStock and AKShare raw-field-to-canonical-candidate mapping metadata.
- Keep tests synthetic.

Possible future files:

- `packages/quant/free_sources/provider_contracts.py`
- `packages/quant/free_sources/canonical_mapping.py`
- `tests/test_quant_free_source_mapping.py`
- `tests/test_quant_free_source_guardrails.py`

Still not allowed:

- Live provider calls.
- BaoStock / AKShare dependency installation.
- Raw archive writes.
- `data/quant` writes.
- Formal outputs.

### Card FS-3: Repo-External Live Smoke Runner, If Approved

Purpose:

- Run live provider smoke only outside repo, similar to the accepted POC.
- Generate repo-safe redacted summaries only after separate approval.

Allowed only with explicit approval:

- Repo-external scratch runner.
- Repo-external venv and provider dependencies.
- Repo-external raw archive.

Still not allowed by default:

- Adding live provider calls to the main quant pipeline.
- Writing `data/quant`.
- Committing raw vendor data.
- Running live calls in normal tests.

### Card FS-4: Redacted Availability Report Generator, If Approved

Purpose:

- Convert accepted repo-external smoke summaries into redacted availability reports.

Requirements:

- Input must already be redacted or validated by FS-1 schema.
- Output must be docs/report-only.
- No row-level vendor data.
- No formal outputs.

Possible future files:

- `packages/quant/free_sources/report_generator.py`
- `tests/test_quant_free_source_report_generator.py`

### Card FS-5: Non-Production Adapter Integration Candidate, Only After Repeated Review

Purpose:

- Consider a narrow non-production integration candidate only after FS-1 through FS-4 pass and are independently accepted.

Preconditions:

- Repeated live smoke review.
- Authorization / usage note accepted.
- Raw archive policy accepted.
- Redacted manifest schema accepted.
- Provider failure semantics accepted.
- No formal blocker removed by implication.

Still blocked:

- Formal labels.
- Formal adjusted return.
- Formal excess return.
- Execution-realistic backtest.
- Production sorting.
- A/B/C.
- Pages.
- Prism Edge.
- Expected 5D.
- ML.

## 11. Future File Pathspec Discipline

If FS-1 is approved, use explicit pathspecs.

Suggested allowed pathspec for FS-1:

```text
packages/quant/free_sources/__init__.py
packages/quant/free_sources/manifest.py
packages/quant/free_sources/contracts.py
packages/quant/free_sources/redaction.py
tests/test_quant_free_source_manifest.py
```

Suggested forbidden pathspecs for FS-1:

```text
data/quant/**
packages/quant/build_*.py
packages/quant/evaluate_factors.py
packages/quant/run_portfolio_backtest.py
packages/quant/upgrade_forward_labels.py
apps/**
docs/design/**
```

This keeps FS-1 focused and makes reviewable diffs small.

## 12. Page Route Deferral

Page route remains deferred.

| Surface | Status |
| --- | --- |
| Control panel page | deferred |
| Quant health page | deferred |
| Prism Edge | deferred |
| Expected 5D | deferred |
| A/B/C display | deferred |
| Any frontend route | deferred |

No page should be planned until formal data readiness and product readiness are reviewed separately.

## 13. Final Recommendation

Recommended decision:

- Approve planning conclusion: **FS-1 should start with schema-only + synthetic tests**.
- Do not approve direct provider adapter implementation yet.
- Do not approve live provider smoke in FS-1.
- Do not approve dependency changes, `data/quant` output, raw vendor data, formal outputs, production sorting, A/B/C, pages, Prism Edge, Expected 5D, or ML.

Recommended next action:

1. Independently accept or revise this implementation plan.
2. If accepted, open Card FS-1 with the exact file scope listed above.
3. Keep FS-1 no-network, synthetic-only, and repo-safe.
