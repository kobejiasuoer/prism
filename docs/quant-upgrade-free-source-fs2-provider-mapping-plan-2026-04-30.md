# Prism Free-Source FS-2 Provider Mapping Plan

Date: 2026-04-30
Role: FS-2 implementation planner
Scope: provider raw-field-to-canonical mapping planning only
Status: docs-only plan; no code

Input documents and files:

- `docs/quant-upgrade-free-source-fs1-acceptance-2026-04-30.md`
- `docs/quant-upgrade-free-source-adapter-implementation-plan-2026-04-30.md`
- `docs/quant-upgrade-free-source-adapter-design-2026-04-30.md`
- `packages/quant/free_sources/manifest.py`
- `packages/quant/free_sources/contracts.py`
- `packages/quant/free_sources/redaction.py`
- `tests/test_quant_free_source_manifest.py`

## 0. Boundary

This document only plans FS-2. It does not authorize or implement FS-2 code.

Strictly prohibited in this planning step:

- No code.
- No BaoStock or AKShare calls.
- No `baostock` or `akshare` imports.
- No dependency installation.
- No `data/quant` writes.
- No raw vendor data.
- No formal labels.
- No formal excess return.
- No formal adjusted return.
- No execution-realistic backtest.
- No production sorting.
- No A/B/C changes.
- No page, Prism Edge, Expected 5D, or ML work.

## 1. FS-2 Decision

FS-2 should remain **synthetic-only**.

| Question | Planning answer |
| --- | --- |
| Is FS-2 still synthetic-only? | Yes. FS-2 should use synthetic mapping metadata and synthetic tests only. |
| Should FS-2 add only provider raw-field-to-canonical mapping metadata? | Yes. FS-2 should not add live adapters, runners, reports, or provider calls. |
| Should FS-2 import BaoStock / AKShare? | No. Provider names and endpoint strings are metadata only. |
| Should FS-2 import network libraries? | No. No `requests`, `urllib`, `httpx`, `socket`, `curl_cffi`, or equivalents. |
| Should FS-2 change dependencies? | No. No dependency file, lockfile, or venv changes. |
| Should FS-2 write `data/quant`? | No. |
| Should FS-2 write raw archive output? | No. |
| Does FS-2 allow FS-3 by default? | No. FS-3 requires separate FS-2 acceptance and explicit approval. |

Rationale:

- FS-1 passed as schema-only + synthetic tests and deliberately avoided provider imports.
- FS-2 should extend that shape by declaring mapping metadata only.
- The field POC showed useful provider coverage, but did not authorize provider integration.
- Mapping metadata is enough to review canonical names, statuses, and blocker discipline before any live source code exists.

## 2. Exact FS-2 File Scope

Recommended allowed file range if FS-2 code is later approved:

| Future path | Purpose | Guardrail |
| --- | --- | --- |
| `packages/quant/free_sources/provider_contracts.py` | Provider endpoint and raw field metadata for BaoStock / AKShare | Declarative metadata only; no provider imports |
| `packages/quant/free_sources/canonical_mapping.py` | Raw-field-to-canonical candidate mapping helpers | Pure functions over synthetic mappings only |
| `tests/test_quant_free_source_mapping.py` | Synthetic mapping tests | No network, no provider packages, no data writes |
| `tests/test_quant_free_source_guardrails.py` | Broader guardrail tests for no provider/network/formal/production outputs | Synthetic-only |

FS-2 should not create:

| Path | Reason |
| --- | --- |
| `packages/quant/free_sources/baostock_adapter.py` | Live provider adapter belongs to a later, separately approved card |
| `packages/quant/free_sources/akshare_adapter.py` | Live provider adapter belongs to a later, separately approved card |
| `packages/quant/free_sources/run_field_poc.py` | Repo-external live smoke belongs to FS-3, if approved |
| `packages/quant/free_sources/report_generator.py` | Redacted report generation belongs to FS-4, if approved |
| `data/quant/**` | Data output remains prohibited |
| Any app / page / frontend path | Page route remains deferred |

## 3. Whether FS-1 Files Need Changes

Default answer: **FS-2 should not modify FS-1 files**.

Acceptable exceptions, only if necessary:

| FS-1 file | Change allowed? | Reason that would justify it |
| --- | --- | --- |
| `packages/quant/free_sources/__init__.py` | Optional | Export new FS-2 metadata symbols after provider mapping modules exist |
| `packages/quant/free_sources/contracts.py` | Avoid unless necessary | Add a missing enum/value only if mapping metadata cannot express an accepted FS-2 state |
| `packages/quant/free_sources/manifest.py` | Avoid | Manifest schema should already be sufficient from FS-1 |
| `packages/quant/free_sources/redaction.py` | Avoid | Redaction guardrails should already reject raw/reversible data |
| `tests/test_quant_free_source_manifest.py` | Avoid | FS-1 tests should remain focused; add FS-2 tests separately |

If FS-2 modifies any FS-1 file, the FS-2 acceptance report must explain why the new mapping could not be represented with the existing FS-1 schema.

## 4. Provider Mapping Coverage

FS-2 should define provider mapping metadata, not executable adapters.

Suggested metadata fields:

| Field | Meaning |
| --- | --- |
| `provider` | `baostock` or `akshare` |
| `provider_role` | primary, cross_check, or supplement |
| `adapter_layer` | One of the FS-1 adapter layers |
| `endpoint` | Provider function name as metadata string |
| `raw_field` | Provider raw field name or request param name |
| `canonical_candidate` | Prism non-production canonical candidate name |
| `value_type` | `string`, `date_string`, `decimal_string`, `numeric`, `provider_enum`, `event_metadata`, etc. |
| `unit` | price unit, index points, provider units, flag, event-only, or unknown |
| `pit_asof_status` | `as_collected_only`, `pit_weak`, `not_pit_ready`, or `unknown` |
| `research_status` | `available`, `candidate`, `research_only`, `partial`, or `blocked` |
| `formal_allowed` | Always false in FS-2 |
| `notes` | Short mapping caveat |

No mapping record should contain row values, date arrays, stock lists, event rows, or raw payload fragments.

## 5. BaoStock Mapping Plan

BaoStock should be mapped as the primary candidate.

| Layer | Endpoint metadata | Raw fields / params to map | Canonical candidates | Status |
| --- | --- | --- | --- | --- |
| Calendar | `query_trade_dates` | `calendar_date`, `is_trading_day` | `trade_calendar.date`, `trade_calendar.is_open` | available candidate |
| Stock basic | `query_stock_basic` | `code`, `code_name`, `ipoDate`, `outDate`, `type`, `status` | `security.code`, `security.name`, `security.list_date`, `security.delist_date`, `security.type`, `security.list_status` | available / partial for nullable `outDate` |
| Raw daily | `query_history_k_data_plus` | `date`, `code`, `open`, `high`, `low`, `close`, `preclose`, `volume`, `amount`, `turn`, `pctChg` | `daily.date`, `daily.code`, `daily.open/high/low/close`, `daily.pre_close`, `daily.volume`, `daily.amount`, `daily.turnover`, `daily.pct_change` | available candidate |
| QFQ candidate | `query_history_k_data_plus` with `adjustflag` | `adjustflag`, qfq `open`, `high`, `low`, `close` | `adjustment.requested_policy`, `adjusted_daily.qfq_open/high/low/close` | research_only |
| Index daily | `query_history_k_data_plus` index code | `date`, `code`, `open`, `high`, `low`, `close`, `preclose`, `volume`, `amount`, `pctChg` | `index_daily.date`, `index_daily.code`, `index_daily.open/high/low/close/pre_close`, `index_daily.volume`, `index_daily.amount`, `index_daily.pct_change` | candidate |
| `tradestatus` / `isST` | `query_history_k_data_plus` | `tradestatus`, `isST` | `execution_candidate.trade_status`, `execution_candidate.is_st` | candidate / research_only |

BaoStock fields that must stay blocked or unresolved:

- Independent `adj_factor` / factor revision unless a later POC proves it.
- Historical full-market `up_limit` / `down_limit`.
- Failed order.
- Partial fill.
- Formal adjusted, benchmark, excess, or label outputs.

## 6. AKShare Mapping Plan

AKShare should be mapped as cross-check / supplement only.

| Layer | Endpoint metadata | Raw fields / params to map | Canonical candidates | Status |
| --- | --- | --- | --- | --- |
| Raw daily cross-check | `stock_zh_a_hist` | `日期`, `股票代码`, `开盘`, `收盘`, `最高`, `最低`, `成交量`, `成交额`, `振幅`, `涨跌幅`, `涨跌额`, `换手率` | `daily.date`, `daily.code`, `daily.open/high/low/close`, `daily.volume`, `daily.amount`, `daily.amplitude`, `daily.pct_change`, `daily.change`, `daily.turnover` | candidate / cross_check |
| QFQ candidate cross-check | `stock_zh_a_hist(adjust="qfq")` | `adjust`, qfq `开盘`, `收盘`, `最高`, `最低` | `adjustment.requested_policy`, `adjusted_daily.qfq_open/close/high/low` | research_only / partial |
| Index daily supplement | `stock_zh_index_hist_csindex` | `日期`, `指数代码`, `开盘`, `最高`, `最低`, `收盘`, `成交量`, `成交金额`, `涨跌`, `涨跌幅` | `index_daily.date`, `index_daily.code`, `index_daily.open/high/low/close`, `index_daily.volume`, `index_daily.amount`, `index_daily.change`, `index_daily.pct_change` | candidate / supplement |
| Suspend event event-only | `stock_tfp_em` | `代码`, `名称`, `停牌时间`, `停牌截止时间`, `停牌期限`, `停牌原因`, `所属市场`, `预计复牌时间` | `suspend_event.code`, `suspend_event.name`, `suspend_event.start_date`, `suspend_event.end_date`, `suspend_event.duration`, `suspend_event.reason`, `suspend_event.market`, `suspend_event.expected_resume_date` | partial / event_only |

AKShare fields and endpoints that must not be promoted:

- `stock_zh_a_hist` does not become the primary stock daily source in FS-2.
- QFQ remains research-only because independent factor / revision is absent.
- `stock_tfp_em` remains event-only; it does not become daily `tradestatus`.
- Eastmoney index endpoints that failed in POC should not be preferred over the csindex supplement.
- Pool endpoints do not become full-market limit up/down price.

## 7. Blocked Capabilities

FS-2 must keep the following blocked:

| Capability | Required FS-2 status | Reason |
| --- | --- | --- |
| Formal adjusted return | blocked | qfq lacks independent `adj_factor`, revision, and PIT/as-of proof |
| Formal excess return | blocked | index daily is only candidate metadata, no formal benchmark freeze |
| Formal labels | blocked | no formal calendar, benchmark, adjusted price, or execution readiness |
| Execution-realistic backtest | blocked | no order ledger, queue, limit price, failed order, or partial fill evidence |
| Historical limit up/down price | blocked | POC did not verify full-market `up_limit` / `down_limit` |
| Failed order | blocked | no broker / OMS source |
| Partial fill | blocked | daily OHLCV cannot prove fills |
| Production sorting | blocked | no production integration |
| A/B/C replacement | blocked | no scoring / tier integration |
| Page / Prism Edge / Expected 5D / ML | blocked / deferred | product route remains paused |

Tests should assert these statuses remain blocked after mapping metadata is added.

## 8. FS-2 Test Plan

FS-2 tests should remain synthetic-only.

Recommended tests:

| Test file | Test objective |
| --- | --- |
| `tests/test_quant_free_source_mapping.py` | Verify mapping coverage for BaoStock calendar, stock basic, raw daily, qfq, index daily, `tradestatus` / `isST`; AKShare raw daily, qfq, index supplement, suspend event |
| `tests/test_quant_free_source_mapping.py` | Verify every mapping uses a valid FS-1 provider, role, adapter layer, PIT status, and research status |
| `tests/test_quant_free_source_mapping.py` | Verify no mapping declares `formal_allowed=true` |
| `tests/test_quant_free_source_guardrails.py` | AST-scan FS-2 modules for no provider imports and no network imports |
| `tests/test_quant_free_source_guardrails.py` | Verify no tests require BaoStock / AKShare installed |
| `tests/test_quant_free_source_guardrails.py` | Verify no `data/quant` writes and no raw archive writes |
| `tests/test_quant_free_source_guardrails.py` | Verify blocked capabilities remain blocked |

No-network proof:

- Reuse the FS-1 forbidden import set: `baostock`, `akshare`, `requests`, `urllib`, `httpx`, `socket`, `curl_cffi`.
- AST-scan FS-2 files.
- Avoid runtime network monkeypatch dependency by never importing networking modules.

Synthetic-only proof:

- Mapping fixtures must be constants / dataclasses with field names only.
- No arrays of real prices, dates, stock lists, event rows, or vendor payloads.
- Tests must not read `~/.prism-private/free-data-poc/` or any raw archive path.

No formal output proof:

- Mapping metadata must not create generated fields for `formal_label`, `formal_excess_return`, `formal_adjusted_return`, `benchmark_return`, `excess_return`, `execution_realistic_return`, `failed_order`, or `partial_fill`.
- If blocked capabilities are listed, their status must be `blocked`.

No production impact proof:

- Tests must not import production sorting, A/B/C, page, app, backtest, label upgrade, factor evaluation, health report, Prism Edge, Expected 5D, or ML modules.
- No existing quant reports should be regenerated.

## 9. FS-2 Acceptance Standards

FS-2 should pass only if:

| Acceptance item | Required standard |
| --- | --- |
| Scope | Only allowed FS-2 files are created or modified, plus any explicitly justified FS-1 export update |
| Synthetic-only | All mappings are metadata constants, not provider calls or raw data |
| Provider coverage | BaoStock and AKShare coverage matches the plan above |
| Status discipline | qfq, benchmark, execution fields are candidate / research_only / partial only |
| Blockers | formal returns, formal labels, execution-realistic backtest, limit up/down, failed order, partial fill remain blocked |
| No provider imports | `baostock` and `akshare` imports absent |
| No network imports | network libraries absent |
| No dependency changes | dependency files, lockfiles, and venv untouched |
| No `data/quant` writes | `data/quant` untouched |
| No raw archive writes | no repo-external raw archive or scratch output |
| No production / page / ML impact | production sorting, A/B/C, pages, Prism Edge, Expected 5D, ML untouched |

Suggested future test command:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages .venv/bin/python -m pytest tests/test_quant_free_source_mapping.py tests/test_quant_free_source_guardrails.py -q -p no:cacheprovider
```

The exact command can be adjusted by the implementer, but tests must stay no-network and synthetic-only.

## 10. FS-3 Gate

FS-2 completion does **not** automatically allow FS-3.

FS-3 remains blocked until:

1. FS-2 implementation is completed.
2. FS-2 has an independent acceptance report.
3. The acceptance report explicitly permits FS-3 planning.
4. A separate FS-3 planning document defines repo-external live smoke boundaries.
5. A separate approval permits any repo-external venv, dependencies, raw archive, or live provider calls.

Default after FS-2:

- No live provider smoke.
- No BaoStock / AKShare install.
- No raw archive writes.
- No `data/quant`.
- No formal outputs.
- No production impact.

## 11. Page Route Deferral

Page route remains deferred.

| Surface | Status |
| --- | --- |
| Control panel page | deferred |
| Quant health page | deferred |
| Prism Edge | deferred |
| Expected 5D | deferred |
| A/B/C display | deferred |
| Any frontend route | deferred |

No page work should be planned until formal data readiness and product readiness receive separate approval.

## 12. Final Recommendation

Recommended FS-2 plan:

- Proceed only after independent acceptance of this planning document.
- Keep FS-2 synthetic-only.
- Add only provider raw-field-to-canonical mapping metadata and synthetic tests.
- Do not modify provider integration, live smoke, report generation, data output, formal outputs, production sorting, A/B/C, pages, Prism Edge, Expected 5D, or ML.
- Do not treat FS-2 completion as permission for FS-3.
