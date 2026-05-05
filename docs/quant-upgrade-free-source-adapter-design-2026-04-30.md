# Prism Free-Source Adapter Design

Date: 2026-04-30
Role: non-production adapter designer
Scope: BaoStock primary + AKShare cross-check / supplement design only
Status: design document only; no implementation

Input documents:

- `docs/quant-upgrade-free-data-source-poc-plan-2026-04-30.md`
- `docs/quant-upgrade-free-data-source-poc-plan-acceptance-2026-04-30.md`
- `docs/quant-upgrade-free-data-source-field-poc-result-2026-04-30.md`
- `docs/quant-upgrade-free-data-source-field-poc-acceptance-2026-04-30.md`

## 0. Boundary

This document only designs a future non-production adapter path.

Strictly prohibited in this step:

- No code.
- No BaoStock or AKShare API calls.
- No dependency installation.
- No `packages/quant` changes.
- No `data/quant` writes.
- No raw vendor data in repo.
- No formal labels.
- No formal excess return.
- No formal adjusted return.
- No execution-realistic backtest.
- No production sorting.
- No A/B/C changes.
- No page, Prism Edge, Expected 5D, or ML work.

This design does not authorize implementation. It only prepares the decision surface for a later implementation card.

## 1. Design Summary

Recommended provider priority:

| Priority | Provider | Role | POC basis | Design conclusion |
| --- | --- | --- | --- | --- |
| 1 | BaoStock | Primary candidate | Calendar, stock basic, raw daily, qfq, `tradestatus`, `isST`, HS300 / CSI500 index daily returned fields and non-null rows in the POC | Use as the primary non-production source for field adapters |
| 2 | AKShare | Cross-check / supplement | Stock raw/qfq mostly available; `stock_zh_index_hist_csindex` returned HS300 / CSI500 index fields; suspend events available; Eastmoney index endpoints failed in this environment | Use as cross-check, index supplement, and event-only suspend research source |

Core design stance:

- BaoStock may become the first free-source adapter candidate for P1-A field availability.
- AKShare should not replace BaoStock as the primary adapter because the POC showed provider/network instability and missing `pre_close`, `tradestatus`, `isST`, and independent adjustment factor fields in the tested stock daily path.
- Both providers remain research-only until license, PIT, raw archive, repeatability, and coverage checks pass.
- The free-source adapter can reduce Tushare permission blocker pressure for field verification, but cannot replace Tushare or an authorized source for formal outputs.

## 2. Adapter Layering

The adapter should be split by data capability, not by provider package.

| Layer | Primary provider | Supplement provider | Design status | Purpose |
| --- | --- | --- | --- | --- |
| Calendar | BaoStock `query_trade_dates` | none initially | available candidate | Trading-day coverage and date alignment research |
| Stock basic | BaoStock `query_stock_basic` | AKShare only if a stable basic-info endpoint is separately approved | available candidate | Code, listing date, status, and security metadata |
| Raw daily OHLCV | BaoStock `query_history_k_data_plus` | AKShare `stock_zh_a_hist` | available candidate | Raw price audit and cross-source field comparison |
| QFQ / adjusted price candidate | BaoStock `query_history_k_data_plus` with qfq params | AKShare `stock_zh_a_hist(adjust="qfq")` | partial / research-only | QFQ candidate only; no formal adjusted return |
| Index daily benchmark candidate | BaoStock index `query_history_k_data_plus` | AKShare `stock_zh_index_hist_csindex` | available candidate | HS300 / CSI500 benchmark field availability |
| `tradestatus` / `isST` execution candidate | BaoStock daily fields | none for daily status in current POC | available candidate, research-only | Source-provided trading-status and ST flags |
| Suspend event candidate | none primary | AKShare `stock_tfp_em` | partial / event-only | Event-level suspend research, requires daily expansion |
| Limit price blocker | none | AKShare pool endpoints are not enough | blocked | Historical full-market `up_limit` / `down_limit` remains unavailable |

Layer ownership rules:

| Rule | Requirement |
| --- | --- |
| Provider separation | Each provider adapter emits a provider-native redacted manifest first |
| Canonical mapping | Canonical candidate rows may be derived only after provider-native manifest succeeds |
| Cross-check | Cross-provider checks compare row counts, field presence, date coverage, and aggregate null counts, not row-level prices in repo |
| No silent fill | Missing source fields must remain `missing`, `partial`, `network_error`, `provider_error`, or `blocked`; do not derive formal fields silently |
| Non-production only | No layer is allowed to feed production sorting, A/B/C, pages, Prism Edge, Expected 5D, ML, labels, or backtests |

## 3. Provider Priority and Fallback

### 3.1 Provider Priority

| Capability | Priority 1 | Priority 2 | Notes |
| --- | --- | --- | --- |
| Calendar | BaoStock | none | AKShare calendar was not part of the accepted field POC |
| Stock basic | BaoStock | none initially | AKShare stock basic can be researched later, but not part of this design scope |
| Raw daily OHLCV | BaoStock | AKShare | AKShare can cross-check field presence and row count |
| QFQ | BaoStock | AKShare | Both remain qfq-price-only candidates unless factor/revision appears |
| Index daily | BaoStock | AKShare `stock_zh_index_hist_csindex` | Avoid AKShare Eastmoney index endpoints until repeatability improves |
| `tradestatus` | BaoStock | none | AKShare `stock_tfp_em` is event-level, not daily `tradestatus` |
| `isST` | BaoStock | none | AKShare stock daily path did not return `isST` |
| Suspend event | AKShare | none | Event-only supplement; no daily execution eligibility |
| Limit price | none | none | Remains blocked |

### 3.2 Fallback Rules

| Situation | Rule | Result status |
| --- | --- | --- |
| BaoStock calendar fails | Do not substitute AKShare unless a calendar endpoint is separately approved | `calendar_unavailable` |
| BaoStock stock basic fails | Do not infer listing metadata from price rows | `stock_basic_unavailable` |
| BaoStock raw daily fails | AKShare may be used as cross-check-only replacement for field availability, not primary canonical source | `raw_daily_partial_fallback` |
| BaoStock qfq fails | AKShare qfq may mark qfq price availability only | `qfq_partial_fallback` |
| BaoStock index daily fails | AKShare `stock_zh_index_hist_csindex` may supplement HS300 / CSI500 field availability | `index_daily_partial_fallback` |
| BaoStock `tradestatus` fails | AKShare suspend events cannot replace daily status automatically | `daily_tradestatus_unavailable` |
| AKShare fails | Keep BaoStock result if BaoStock passed; record AKShare failure in cross-check manifest | `cross_check_unavailable` |
| Providers disagree | Mark `provider_mismatch`; do not choose a winner automatically | `blocked_until_review` for that capability |
| Provider network error | Record endpoint, timestamp, params fingerprint, error class, and response/error hash | `network_error_retryable` |
| Provider returns empty rows | Distinguish expected empty, stale date window, permission issue, provider change, and missing field | `empty_result_needs_review` |

## 4. Redacted Manifest Schema

Every future request should emit one redacted manifest record. The record is allowed in repo only if it contains no raw rows and no reversible vendor dataset.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `schema_version` | string | yes | Example: `free_source_manifest_v1` |
| `run_id` | string | yes | Opaque local run id; must not expose local username or raw path |
| `provider` | enum | yes | `baostock` or `akshare` |
| `provider_role` | enum | yes | `primary`, `cross_check`, `supplement` |
| `source_version` | object | yes | Package version, module version if available, docs URL, source family |
| `adapter_layer` | enum | yes | `calendar`, `stock_basic`, `raw_daily`, `qfq_candidate`, `index_daily`, `tradestatus_isst`, `suspend_event`, `limit_candidate` |
| `endpoint` | string | yes | Provider endpoint or function name |
| `params_fingerprint_sha256` | string | yes | SHA256 of redacted normalized params |
| `params_redacted` | object | yes | Date range, symbol count, index count, field request; no raw symbol list if policy forbids |
| `retrieved_at` | string | yes | ISO 8601 timestamp with timezone |
| `response_hash_sha256` | string | yes | Hash of raw response bytes or canonical raw payload |
| `hash_method` | enum | yes | `raw_bytes_sha256` or `canonical_payload_sha256`; one run must not mix methods |
| `row_count` | integer | yes | Number of rows returned |
| `field_list` | string array | yes | Returned field names only |
| `expected_field_list` | string array | yes | Fields expected by this adapter layer |
| `missing_field_list` | string array | yes | Expected fields not returned |
| `non_null_summary` | object | yes | Field-level non-null counts only |
| `duplicate_summary` | object | yes | Date/code duplicate counts and key collision summary |
| `coverage_summary` | object | yes | Date window, observed date count, symbol count, index count; no row values |
| `status` | enum | yes | `available`, `partial`, `missing`, `empty`, `network_error`, `provider_error`, `license_blocked`, `blocked` |
| `error_summary` | string | conditional | Error class and short message; no raw response body |
| `license_usage_note` | object | yes | Free-use assumption, automation note, archive permission status, redistribution status |
| `pit_asof_status` | enum | yes | `as_collected_only`, `pit_weak`, `not_pit_ready`, `unknown` |
| `raw_archive_pointer` | string | yes | Opaque pointer to repo-external archive only |
| `repo_safe` | boolean | yes | Must be true before any manifest enters repo |

Manifest status semantics:

| Status | Meaning |
| --- | --- |
| `available` | Required fields present and non-null coverage is acceptable for field availability |
| `partial` | Some useful fields present but a required field, provider role, or PIT condition is incomplete |
| `missing` | Required fields absent |
| `empty` | Endpoint returned no rows; needs date-window / endpoint / provider review |
| `network_error` | Request failed due to network, TLS, proxy, DNS, timeout, or similar transport issue |
| `provider_error` | Provider returned an explicit application-level error |
| `license_blocked` | Usage, automation, archive, or redacted-report permission is not acceptable |
| `blocked` | Capability must not advance until manual review |

## 5. Raw Archive Design

Raw response archive remains outside the repo.

| Item | Design |
| --- | --- |
| Root | `~/.prism-private/free-data-poc/` for the current POC family; future runs may use the same private root or a separately approved private root |
| Raw location | Repo-external `raw/` subdirectory with provider / run separation |
| Permissions | Owner-only local permissions where possible; no shared repo path |
| Contents | Raw payload, provider error payload, private request manifest, exact request timestamp |
| Hash | SHA256 over exact raw bytes or canonical raw payload; hash method recorded in redacted manifest |
| Timestamp | Local request timestamp and response timestamp; provider server timestamp if available |
| Retention | Default proposal: 90 days for POC raw, unless license review requires shorter retention |
| Deletion mechanism | Manual deletion record or local deletion manifest containing run id, provider, deletion timestamp, and hash list; deletion manifest may be redacted into repo only if it contains no raw rows or private paths |
| No-repo rule | No raw payload, line-level price rows, full calendar, full stock list, event rows, screenshots, CSV, or reversible sample enters repo |

`raw_archive_pointer` rules:

| Rule | Requirement |
| --- | --- |
| Opaque | Do not expose absolute local user path in repo manifests |
| Non-accessible | Pointer must not be a usable URL, tokenized path, or bucket credential |
| Stable enough | Pointer should let the local operator locate private raw during acceptance |
| Hash-bound | Pointer is useful only with `response_hash_sha256`; pointer alone is not evidence |

## 6. Field Contracts

All fields below are candidate contracts. They are not formal Prism data contracts.

### 6.1 Calendar

| Provider | Raw field | Canonical candidate | Type | Unit | PIT / as-of status | Status |
| --- | --- | --- | --- | --- | --- | --- |
| BaoStock | `calendar_date` | `trade_calendar.date` | date string | calendar day | `as_collected_only`; needs official holiday cross-check | available |
| BaoStock | `is_trading_day` | `trade_calendar.is_open` | boolean-like string | flag | `as_collected_only`; not official exchange source | available |

Notes:

- Calendar can support non-production date alignment.
- It must not become formal frozen calendar until coverage, source version, official holiday cross-check, and archive policy pass.

### 6.2 Stock Basic

| Provider | Raw field | Canonical candidate | Type | Unit | PIT / as-of status | Status |
| --- | --- | --- | --- | --- | --- | --- |
| BaoStock | `code` | `security.code` | string | provider code | `as_collected_only` | available |
| BaoStock | `code_name` | `security.name` | string | name | `as_collected_only`; may be revised | available |
| BaoStock | `ipoDate` | `security.list_date` | date string | calendar day | `as_collected_only`; needs historical audit | available |
| BaoStock | `outDate` | `security.delist_date` | date string / empty | calendar day | `as_collected_only`; empty is meaningful | partial |
| BaoStock | `type` | `security.type` | string / code | provider enum | enum meaning must be documented | available |
| BaoStock | `status` | `security.list_status` | string / code | provider enum | enum meaning and historical revision need audit | available |

### 6.3 Raw Daily OHLCV

| Provider | Raw field | Canonical candidate | Type | Unit | PIT / as-of status | Status |
| --- | --- | --- | --- | --- | --- | --- |
| BaoStock | `date` | `daily.date` | date string | trading day | `as_collected_only` | available |
| BaoStock | `code` | `daily.code` | string | provider code | `as_collected_only` | available |
| BaoStock | `open`, `high`, `low`, `close` | `daily.open/high/low/close` | decimal string | CNY price | `pit_weak` until daily archive exists | available |
| BaoStock | `preclose` | `daily.pre_close` | decimal string | CNY price | `pit_weak` | available |
| BaoStock | `volume` | `daily.volume` | decimal/integer string | shares or provider volume unit; must confirm | `pit_weak` | available |
| BaoStock | `amount` | `daily.amount` | decimal string | provider amount unit; must confirm | `pit_weak` | available |
| AKShare | `日期` | `daily.date` | date / string | trading day | `pit_weak` | available |
| AKShare | `股票代码` | `daily.code` | string | plain code | `pit_weak` | available |
| AKShare | `开盘`, `最高`, `最低`, `收盘` | `daily.open/high/low/close` | numeric | CNY price | `pit_weak` | available |
| AKShare | `成交量`, `成交额` | `daily.volume`, `daily.amount` | numeric | provider units; must confirm | `pit_weak` | available |
| AKShare | missing `pre_close` | `daily.pre_close` | n/a | n/a | not available from tested endpoint | missing |

### 6.4 QFQ / Adjusted Price Candidate

| Provider | Raw field / param | Canonical candidate | Type | Unit | PIT / as-of status | Status |
| --- | --- | --- | --- | --- | --- | --- |
| BaoStock | `adjustflag` request param | `adjustment.requested_policy` | string | provider enum | policy needs versioned documentation | available |
| BaoStock | qfq `open/high/low/close` | `adjusted_daily.qfq_open/high/low/close` | decimal string | adjusted CNY-like price | `not_pit_ready`; no factor revision | research_only |
| AKShare | `adjust="qfq"` request param | `adjustment.requested_policy` | string | provider enum | provider and underlying source may revise | partial |
| AKShare | qfq `开盘/最高/最低/收盘` | `adjusted_daily.qfq_open/high/low/close` | numeric | adjusted CNY-like price | `not_pit_ready`; no factor revision | research_only |
| both | independent factor missing | `adjustment.adj_factor` | n/a | n/a | not available in POC | blocked |

No formal adjusted return may be produced from qfq price alone.

### 6.5 Index Daily Benchmark Candidate

| Provider | Raw field | Canonical candidate | Type | Unit | PIT / as-of status | Status |
| --- | --- | --- | --- | --- | --- | --- |
| BaoStock | `date`, `code` | `index_daily.date`, `index_daily.code` | date/string | trading day / provider code | `pit_weak` | available |
| BaoStock | `open`, `high`, `low`, `close`, `preclose` | `index_daily.open/high/low/close/pre_close` | decimal string | index points | `pit_weak` | available |
| BaoStock | `volume`, `amount` | `index_daily.volume`, `index_daily.amount` | decimal string | provider units; must confirm | `pit_weak` | available |
| AKShare | `日期`, `指数代码` | `index_daily.date`, `index_daily.code` | date/string | trading day / index code | `pit_weak` | available via csindex endpoint |
| AKShare | `开盘`, `最高`, `最低`, `收盘` | `index_daily.open/high/low/close` | numeric | index points | `pit_weak` | available via csindex endpoint |
| AKShare | `成交量`, `成交金额` | `index_daily.volume`, `index_daily.amount` | numeric | provider units; must confirm | `pit_weak` | available with amount field mapping |
| AKShare | Eastmoney index endpoints | n/a | n/a | n/a | failed in POC environment | network_error |

Index daily can enter benchmark field design. It cannot produce formal benchmark returns or formal excess returns.

### 6.6 `tradestatus` / `isST` Execution Candidate

| Provider | Raw field | Canonical candidate | Type | Unit | PIT / as-of status | Status |
| --- | --- | --- | --- | --- | --- | --- |
| BaoStock | `tradestatus` | `execution_candidate.trade_status` | string / provider enum | daily status flag | `pit_weak`; enum and historical coverage need audit | available |
| BaoStock | `isST` | `execution_candidate.is_st` | string / provider enum | daily ST flag | `pit_weak`; rule version and edge cases need audit | available |

These fields may support execution availability research only. They do not prove actual fills, failed orders, queue position, partial fills, or execution-realistic outcomes.

### 6.7 Suspend Event Candidate

| Provider | Raw field | Canonical candidate | Type | Unit | PIT / as-of status | Status |
| --- | --- | --- | --- | --- | --- | --- |
| AKShare | `代码`, `名称` | `suspend_event.code/name` | string | security identity | `as_collected_only` | partial |
| AKShare | `停牌时间` | `suspend_event.start_date` | date/string | calendar day | event-level only | partial |
| AKShare | `停牌截止时间` | `suspend_event.end_date` | date/string / nullable | calendar day | event-level only | partial |
| AKShare | `预计复牌时间` | `suspend_event.expected_resume_date` | date/string / nullable | calendar day | event-level only | partial |
| AKShare | `停牌原因` | `suspend_event.reason` | string | reason text | event-level only | partial |

Suspend events require daily expansion against a calendar before they can even be compared with `tradestatus`. That expansion is not approved here.

### 6.8 Limit Price Blocker

| Provider | Raw field / endpoint | Canonical candidate | Type | Unit | PIT / as-of status | Status |
| --- | --- | --- | --- | --- | --- | --- |
| BaoStock | no `up_limit` / `down_limit` in POC daily fields | `execution_limit.up_limit/down_limit` | n/a | n/a | unavailable | blocked |
| AKShare |涨停 / 跌停 pool endpoints | `execution_limit.limit_pool_membership` | event/pool rows | pool membership | not full-market price | partial, not sufficient |
| AKShare | historical full-market `up_limit/down_limit` | `execution_limit.up_limit/down_limit` | n/a | n/a | not verified | blocked |

Limit price remains a hard blocker for execution-realistic backtest and limit-aware formal labels.

## 7. Cross-Check Design

Cross-check compares evidence quality, not raw rows in repo.

Allowed cross-check summaries:

- Row count by provider / layer / symbol count.
- Returned field list.
- Missing field list.
- Non-null counts.
- Date coverage count.
- Duplicate key count.
- Hash and timestamp.
- Error class and endpoint family.

Disallowed in repo:

- Row-level OHLCV.
- Row-level qfq price.
- Row-level index price.
- Full calendar.
- Full stock list.
- Full suspend event rows.
- Limit pool constituents.
- Screenshots or CSV samples that can reconstruct vendor data.

Mismatch handling:

| Mismatch | Handling |
| --- | --- |
| Field list mismatch | Mark `field_mismatch`; require mapping review |
| Row count mismatch | Mark `coverage_mismatch`; compare calendar/date coverage summaries only |
| Date coverage mismatch | Mark `date_coverage_mismatch`; do not fill from alternate provider silently |
| Null count mismatch | Mark `null_profile_mismatch`; require provider-specific review |
| Hash changes across repeat run | Mark `source_revision_or_nondeterminism`; require repeatability note |
| Provider value mismatch | Do not store row values in repo; private review may inspect raw archive, then redacted conclusion can be recorded |

## 8. Degradation Rules

The adapter must be fail-closed for formal capabilities.

| Failure | Degradation |
| --- | --- |
| Missing calendar | Disable calendar candidate; all calendar-dependent label upgrades remain blocked |
| Missing stock basic | Disable universe metadata candidate; do not infer listing status from daily rows |
| Missing raw daily | Disable price candidate for that provider / symbol window |
| Missing qfq | Keep raw daily only; adjusted price candidate unavailable |
| QFQ without factor / revision | Keep `qfq_candidate_research_only`; formal adjusted return blocked |
| Missing index daily | Benchmark candidate unavailable; formal excess return blocked |
| Missing `tradestatus` | Execution status candidate unavailable; do not infer from volume or missing price |
| Missing `isST` | ST rule candidate unavailable; do not infer from name alone without an approved rule |
| Suspend event only | Keep event-only; no daily execution eligibility |
| Missing `up_limit/down_limit` | Limit-aware execution flags blocked |
| Network error | Retry only in repo-external POC if approved; repo manifest records `network_error` |
| License uncertainty | Mark `license_blocked`; do not archive raw or admit redacted result until cleared |

## 9. Capabilities Allowed for Later Non-Production Implementation

If a later implementation card is approved, the following may enter a strictly non-production implementation phase:

| Capability | Provider scope | Implementation status allowed later | Guardrail |
| --- | --- | --- | --- |
| Calendar | BaoStock | yes, field adapter only | No formal frozen calendar |
| Stock basic | BaoStock | yes, field adapter only | No production universe replacement |
| Raw daily | BaoStock primary, AKShare cross-check | yes, field adapter only | No `data/quant` price dataset |
| QFQ candidate | BaoStock primary, AKShare cross-check | yes, candidate adapter only | No formal adjusted return |
| Index daily candidate | BaoStock primary, AKShare csindex supplement | yes, benchmark candidate only | No benchmark_return / excess_return |
| `tradestatus` / `isST` candidate | BaoStock | yes, availability adapter only | No execution-realistic claim |
| Suspend event candidate | AKShare | yes, event-only manifest adapter | No daily execution status until separate design |

Implementation phase should still default to repo-external scratch output unless a later approval explicitly allows a repo-safe redacted manifest path.

## 10. Capabilities That Remain Blocked

| Capability | Status | Reason |
| --- | --- | --- |
| Formal adjusted return | blocked | qfq price exists, but independent `adj_factor`, revision, and PIT/as-of discipline are missing |
| Formal excess return | blocked | Index fields are candidates only; no formal benchmark freeze or coverage audit |
| Formal labels | blocked | Calendar, price, benchmark, execution, PIT, and authorization are not formal-ready |
| Execution-realistic backtest | blocked | No real order ledger, failed order evidence, partial fill model, queue data, or full limit price source |
| Historical `up_limit/down_limit` price | blocked | POC did not verify full-market historical limit price fields |
| Failed order | blocked | No broker / OMS / order event source |
| Partial fill | blocked | Daily OHLCV and amount cannot prove partial fill |
| Production sorting | blocked | Free-source output must not affect production ranking |
| A/B/C replacement | blocked | No production decision model integration |
| Page / Prism Edge / Expected 5D | blocked | Product surface explicitly deferred |
| ML | blocked | No model training or feature production |

## 11. Future Implementation Scope If Approved

This section is a recommendation only. It does not create or modify these files.

### 11.1 Suggested File Scope

If implementation is approved, keep it isolated and non-production:

| Future path | Purpose | Guardrail |
| --- | --- | --- |
| `packages/quant/free_sources/manifest_schema.py` | Redacted manifest dataclasses / validation | No API calls; schema only |
| `packages/quant/free_sources/baostock_adapter.py` | BaoStock field adapter | Must be explicitly non-production |
| `packages/quant/free_sources/akshare_adapter.py` | AKShare cross-check / supplement adapter | Must be explicitly non-production |
| `packages/quant/free_sources/canonical_mapping.py` | Provider-to-canonical candidate mapping | No formal labels or returns |
| `packages/quant/free_sources/archive_policy.py` | Raw archive pointer and hash policy | Repo-external raw only |
| `packages/quant/free_sources/run_field_poc.py` | Optional repo-external POC runner wrapper | Output defaults outside repo |
| `tests/test_quant_free_source_manifest.py` | Manifest schema tests | No network |
| `tests/test_quant_free_source_mapping.py` | Field mapping tests with synthetic rows | No vendor data |
| `tests/test_quant_free_source_guardrails.py` | No formal output / no production impact tests | No data writes |

Alternative safer first step:

- Add only docs and synthetic tests in a dedicated branch before any live adapter code.
- Keep live provider calls in repo-external scratch until repeatability and authorization are accepted.

### 11.2 Suggested Test Scope

Tests should use synthetic fixtures only:

| Test area | Expected coverage |
| --- | --- |
| Manifest validation | Required fields, enum status, hash fields, raw pointer rules |
| Redaction | Reject raw rows, price arrays, full calendars, full stock lists, token-like fields |
| Mapping | BaoStock and AKShare field names map to canonical candidate fields |
| Status semantics | `available`, `partial`, `missing`, `network_error`, `license_blocked`, `blocked` |
| Fallback | BaoStock failure does not silently promote AKShare to formal source |
| Cross-check mismatch | Row count / field / coverage mismatch becomes `blocked_until_review` |
| Guardrails | No formal labels, formal excess return, formal adjusted return, execution-realistic backtest, production sorting, A/B/C, pages, Prism Edge, Expected 5D, or ML |

### 11.3 Suggested Acceptance Standards

An implementation card should not pass unless:

| Acceptance item | Requirement |
| --- | --- |
| Repo boundary | No raw vendor data, no line-level market rows, no complete vendor-derived datasets |
| Data boundary | No `data/quant` writes unless a later explicit data-output approval exists |
| Dependency boundary | No dependency or lockfile changes unless separately approved |
| Provider boundary | BaoStock primary and AKShare supplement roles enforced |
| Manifest boundary | Every request has redacted manifest with hash, timestamp, row count, field list, non-null summary, source version, and license note |
| Archive boundary | Raw payloads stored repo-external with hash and retention policy |
| Formal boundary | No formal returns, labels, execution-realistic claims, or production impact |
| Page boundary | No UI, no page route, no Prism Edge / Expected 5D productization |

## 12. Page Route Deferral

Page work remains explicitly deferred.

| Surface | Status | Reason |
| --- | --- | --- |
| Control panel page | deferred | Field adapter is not production data |
| Quant health page | deferred | Free-source fields are not formal-ready |
| Prism Edge | deferred | No formal excess return or execution realism |
| Expected 5D | deferred | No formal adjusted / excess return |
| A/B/C display | deferred | No production sorting replacement |

Any future page work must wait for a separate product and data-readiness decision after formal blockers are resolved.

## 13. Final Decision

The free-source adapter design should proceed only as a non-production, field-availability, redacted-manifest architecture.

Recommended next step:

1. Approve or reject a docs-only acceptance review for this design.
2. If accepted, open a separate non-production implementation proposal.
3. If implementation is later approved, start with manifest schema and synthetic tests before any live provider adapter code.

Decision summary:

- BaoStock primary candidate: yes.
- AKShare cross-check / supplement: yes.
- Non-production implementation readiness: yes, for selected field adapters only.
- Formal labels / formal adjusted return / formal excess return / execution-realistic backtest: no.
- Production sorting / A/B/C / pages / Prism Edge / Expected 5D / ML: no.
