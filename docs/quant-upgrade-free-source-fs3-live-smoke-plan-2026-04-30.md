# Prism Free-Source FS-3 Repo-External Live Smoke Plan

Date: 2026-04-30
Role: FS-3 planning
Scope: repo-external BaoStock + AKShare live smoke planning only
Status: docs-only plan; no live calls; no dependency install

Input documents and files:

- `docs/quant-upgrade-free-source-fs2-acceptance-2026-04-30.md`
- `docs/quant-upgrade-free-source-fs2-provider-mapping-plan-2026-04-30.md`
- `packages/quant/free_sources/manifest.py`
- `packages/quant/free_sources/provider_contracts.py`
- `packages/quant/free_sources/canonical_mapping.py`
- `tests/test_quant_free_source_guardrails.py`

## 0. Boundary

This document only plans FS-3. It does not authorize execution.

Strictly prohibited in this planning step:

- No code.
- No BaoStock or AKShare calls.
- No BaoStock or AKShare installation.
- No `packages/quant` changes.
- No `data/quant` writes.
- No dependency file, lockfile, or venv changes.
- No raw vendor data.
- No repo-external raw archive writes.
- No formal labels.
- No formal excess return.
- No formal adjusted return.
- No execution-realistic backtest.
- No production sorting.
- No A/B/C changes.
- No page, Prism Edge, Expected 5D, or ML work.

FS-2 acceptance permits only FS-3 planning. Any live smoke run requires a separate explicit approval after this plan is reviewed.

## 1. FS-3 Decision

FS-3 should be limited to **repo-external live smoke only**, if separately approved.

| Question | Planning answer |
| --- | --- |
| Is FS-3 only repo-external live smoke? | Yes. No live smoke code or raw output should live inside the repo. |
| Should FS-3 modify `packages/quant`? | No. `packages/quant` remains untouched in FS-3. |
| Should FS-3 write `data/quant`? | No. `data/quant` remains blocked. |
| Is repo-external venv allowed by default? | No. It requires separate approval. |
| Is installing BaoStock / AKShare allowed by default? | No. It requires separate approval. |
| Can raw vendor data be committed or copied into the repo? | No. Raw data must never enter the repo. |
| Does FS-3 allow FS-4 by default? | No. FS-4 requires FS-3 acceptance and separate planning. |

Recommended scratch root, if execution is later approved:

```text
/Users/yangbishang/.prism-private/free-data-poc/
```

This path is a private repo-external scratch area. It must not be referenced by absolute path inside repo-safe manifests or committed docs.

## 2. Approval Gates

FS-3 execution requires explicit approval for each item below:

| Gate | Default | Approval needed for execution |
| --- | --- | --- |
| Repo-external scratch root creation | Not in this planning step | Yes |
| Repo-external venv | Not allowed by default | Yes |
| BaoStock installation | Not allowed by default | Yes |
| AKShare installation | Not allowed by default | Yes |
| Live provider calls | Not allowed by default | Yes |
| Repo-external raw archive | Not allowed in planning; allowed only if execution approval says so | Yes |
| Repo-internal redacted result report | Allowed only as FS-3 result output after execution | Yes |

Approval should name the exact scratch root, whether raw responses may be archived repo-externally, retention duration, and the single repo-internal result document path.

## 3. Raw Archive Rules

If live smoke execution is later approved, raw archive handling must follow these rules:

| Rule | Requirement |
| --- | --- |
| Location | Repo-external only, under the approved scratch root. |
| Repo status | Never committed, never copied into `docs/`, never copied into `data/quant`. |
| Hashing | Each raw artifact gets a SHA-256 hash computed from raw bytes or canonical serialized bytes. |
| Timestamp | Each raw artifact gets `retrieved_at` and archive write timestamp in ISO-8601 format. |
| Pointer | Repo-safe manifests may include only an opaque `raw_archive_pointer`, never an absolute path, `file://`, `http(s)://`, credentialed URL, or local username path. |
| Retention | Default maximum retention should be 7 days unless the approval sets a shorter period. |
| Deletion | Deletion should produce a repo-external deletion record with opaque pointer, hash, `deleted_at`, and deletion method. |
| Deletion record content | The deletion record must not include raw rows, raw response bodies, full calendars, full stock lists, event rows, or local absolute paths. |
| Re-run | A later smoke run should create a new run id and not overwrite older raw archive metadata. |

Raw archive is for private traceability only. It is not a dataset, not a source of formal labels, and not a production input.

## 4. Redacted Manifest Rules

Repo-internal FS-3 output may contain only脱敏 manifest / report content.

Allowed repo-safe fields:

- `provider`
- `provider_role`
- `adapter_layer`
- `endpoint`
- `params_fingerprint_sha256`
- `params_redacted`
- `response_hash_sha256`
- `hash_method`
- `row_count`
- `field_list`
- `expected_field_list`
- `missing_field_list`
- `non_null_summary`
- `duplicate_summary`
- `coverage_summary`
- `status`
- `retrieved_at`
- `source_version`
- `license_usage_note`
- `pit_asof_status`
- `raw_archive_pointer` as an opaque pointer only
- `error_summary` without raw payload

Forbidden repo content:

- No row-level market data.
- No complete calendar date arrays.
- No complete stock lists.
- No raw response, payload, body, HTML, CSV, dataframe, or JSON rows.
- No suspend event rows.
- No limit pool constituents.
- No token, cookie, session, password, secret, authorization, or credential-like keys.
- No absolute local raw archive path.
- No URL that can fetch raw archive content.
- No formal labels, formal returns, adjusted returns, or execution-realistic backtest outputs.

The FS-1 manifest schema and redaction rules remain the repo-safe reference. FS-3 should not weaken them.

## 5. Live Smoke Endpoint Scope

If execution is approved, FS-3 should cover only the mapped FS-2 endpoint metadata below.

| Provider | Role | Layer | Endpoint scope | FS-3 purpose |
| --- | --- | --- | --- | --- |
| BaoStock | primary | calendar | `query_trade_dates` | Verify calendar field availability and row count for the sample window. |
| BaoStock | primary | stock_basic | `query_stock_basic` | Verify stock identity/listing metadata fields for sample securities. |
| BaoStock | primary | raw_daily | `query_history_k_data_plus` | Verify raw daily OHLCV field availability. |
| BaoStock | primary | qfq_candidate | `query_history_k_data_plus` with qfq request policy | Verify qfq candidate field availability only. |
| BaoStock | primary | index_daily | `query_history_k_data_plus` with index codes | Verify HS300 / CSI500 index daily candidate fields. |
| BaoStock | primary | tradestatus_isst | `query_history_k_data_plus` fields | Verify `tradestatus` / `isST` availability as execution candidates. |
| AKShare | cross_check | raw_daily | `stock_zh_a_hist` | Verify raw daily cross-check fields. |
| AKShare | cross_check | qfq_candidate | `stock_zh_a_hist` with qfq request policy | Verify qfq candidate cross-check fields only. |
| AKShare | supplement | index_daily | `stock_zh_index_hist_csindex` or approved equivalent | Verify HS300 / CSI500 index supplement fields. |
| AKShare | supplement | suspend_event | `stock_tfp_em` or approved equivalent | Verify event-only suspend field availability, not daily execution status. |

FS-3 must not add unplanned provider endpoints during execution unless a revised plan is approved.

## 6. Sample Scope

FS-3 should use a tiny deterministic sample only.

| Category | Sample |
| --- | --- |
| Stocks | 贵州茅台、宁德时代、平安银行 |
| Provider code conversion | Convert to each provider format inside repo-external scratch only; repo report may describe conversion rules but not store full stock lists. |
| Indexes | HS300、CSI500 |
| Date window | 2024-01-02 to 2024-01-10 |
| Frequency | Daily only |
| Expected size | Small enough to support field availability checks; not a research dataset. |

The sample is for field availability and provider behavior only. It must not be used to infer strategy performance or production ranking quality.

## 7. Status And Error Recording

FS-3 should use FS-1 manifest status values for endpoint outcomes.

| Status | When to use | Repo-safe error content |
| --- | --- | --- |
| `available` | Endpoint returns expected fields with non-empty sample rows. | Field list, row count, non-null summary, response hash, timestamp. |
| `partial` | Endpoint returns some expected fields or some sample symbols only. | Missing fields, partial coverage summary, brief non-sensitive reason. |
| `empty` | Endpoint succeeds but returns no rows for the sample. | Row count 0, field list if available, timestamp. |
| `network_error` | Network/connectivity/timeout/DNS/TLS issue prevents provider response. | Error class/category and short message summary only. |
| `provider_error` | Provider returns an error code, malformed response, rate-limit-like response, or endpoint behavior error. | Provider error category and short message summary only. |
| `license_blocked` | Provider terms, login, entitlement, or access rule blocks the call. | License/access summary only. |
| `blocked` | Endpoint or field is intentionally not tested because it is outside FS-3 scope. | Blocker reason only. |

Error summaries must never include raw payloads, cookies, tokens, URLs with credentials, or raw row samples.

## 8. Authorization And Usage Boundary

Free callable access does not imply redistribution rights.

FS-3 must treat BaoStock and AKShare responses as research-only availability evidence:

- Raw vendor data must not enter the repo.
- Repo-internal docs may include only row counts, field lists, non-null summaries, missing fields, duplicate summaries, coverage summaries, response hashes, timestamps, and short error summaries.
- Any raw archive must remain private, repo-external, hash-addressed, and time-limited.
- A successful smoke result does not authorize production use.
- A successful smoke result does not authorize formal labels, formal excess return, formal adjusted return, or execution-realistic backtest.
- Any later redistribution, publication, or production use requires separate license review.

## 9. FS-3 Result Output If Approved

If FS-3 live smoke execution is separately approved and completed, the only allowed repo-internal output should be:

```text
docs/quant-upgrade-free-source-fs3-live-smoke-result-2026-04-30.md
```

That result document may contain:

- Execution timestamp and run id.
- Provider/source version summary.
- Endpoint-level status.
- Row count.
- Field list.
- Expected and missing field list.
- Non-null summary.
- Duplicate and coverage summary.
- Response hash.
- Opaque raw archive pointer, if raw archive was separately approved.
- License / usage note.
- Error summary.
- Recommendation on whether FS-4 planning should be considered.

That result document must not contain raw rows, raw responses, full calendars, full stock lists, event rows, limit pool constituents, or formal outputs.

FS-3 must not write:

- `packages/quant/**`
- `data/quant/**`
- dependency files
- lockfiles
- venv files
- app/page/frontend files
- production ranking, factor, backtest, health, or report logic

## 10. Explicit Non-Goals

FS-3 does not allow:

- Formal labels.
- Formal excess return.
- Formal adjusted return.
- Execution-realistic backtest.
- Production sorting.
- A/B/C changes.
- Page work.
- Prism Edge work.
- Expected 5D work.
- ML work.
- Limit up/down production blocker resolution.
- Failed order modeling.
- Partial fill modeling.
- Any production adapter integration.

QFQ, benchmark, `tradestatus`, `isST`, and suspend events remain candidate / research-only / partial evidence after FS-3 unless a later reviewed card changes their status.

## 11. Pre-Execution Checklist

Before any FS-3 live smoke execution, confirm:

1. A human approval explicitly allows repo-external live smoke.
2. A human approval explicitly allows repo-external venv creation, if needed.
3. A human approval explicitly allows BaoStock / AKShare installation, if needed.
4. A human approval explicitly states whether raw archive may be written repo-externally.
5. The scratch root is outside the repo.
6. The result output path is limited to the FS-3 result doc.
7. No `packages/quant` writes are planned.
8. No `data/quant` writes are planned.
9. No provider output will be committed except redacted manifest/report content.
10. Deletion and retention rules are understood before raw archive creation.

If any checklist item is not satisfied, FS-3 execution should not start.

## 12. FS-4 Gate

FS-3 completion does **not** permit FS-4 by default.

FS-4 remains blocked until:

1. FS-3 execution is separately approved and completed, or FS-3 is explicitly closed as not approved.
2. FS-3 result document is reviewed.
3. An independent FS-3 acceptance report confirms boundary compliance.
4. A separate FS-4 planning document defines the redacted availability report generator scope.
5. A separate approval permits FS-4 work.

Default after FS-3:

- No FS-4 implementation.
- No adapter integration.
- No production connection.
- No formal outputs.

## 13. Final Recommendation

Recommend proceeding only to **FS-3 repo-external live smoke approval review**, not execution.

The recommended FS-3 execution shape, if approved later, is:

- Repo-external scratch only.
- Optional repo-external venv only with approval.
- BaoStock + AKShare install only with approval.
- Tiny sample only.
- Raw archive only repo-external and only with approval.
- Repo result limited to one redacted docs report.
- No `packages/quant`, `data/quant`, production, page, Prism Edge, Expected 5D, or ML changes.

