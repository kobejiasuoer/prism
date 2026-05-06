# Prism Quant Tushare Non-Production Source Design

Date: 2026-04-29
Scope: non-production source design only
Status: design draft after Tushare POC
Production impact: none

References:

- `docs/quant-upgrade-tushare-poc-result-2026-04-29.md`
- `docs/quant-upgrade-tushare-poc-runbook-2026-04-29.md`
- `docs/quant-upgrade-tushare-field-availability-matrix-2026-04-29.md`
- `docs/quant-upgrade-tushare-poc-acceptance-checklist-2026-04-29.md`

## 1. Boundary

This document is a non-production source design note. It does not implement an adapter, does not call Tushare APIs, does not install dependencies, does not modify `packages/quant`, and does not write `data/quant`.

Allowed scope is limited to fields observed as available in the Tushare POC sample:

- `daily` raw OHLCV;
- `adj_factor`;
- `stock_basic`.

Explicitly out of scope until separate permissions and field coverage are resolved:

- `trade_cal`;
- `index_daily`;
- `stk_limit`;
- `suspend_d`;
- `pro_bar`.

This design must not:

- connect to `packages/quant`;
- write or overwrite `data/quant`;
- generate an adapter;
- generate formal labels;
- generate formal excess return;
- generate formal adjusted return;
- generate execution-realistic backtests;
- affect production sorting;
- replace A/B/C;
- add pages;
- add Prism Edge;
- add Expected 5D display;
- add ML.

## 2. POC Findings Used By This Design

The POC validated only small-sample field availability and raw archive mechanics.

| Tushare interface | POC status | Fields observed | Design use |
| --- | --- | --- | --- |
| `daily` | `available` | `ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `pre_close`, `vol`, `amount` | Candidate raw/source-observed OHLCV input for research-only price availability checks. |
| `adj_factor` | `available` | `ts_code`, `trade_date`, `adj_factor` | Candidate adjustment-factor input for future adjustment-policy validation. |
| `stock_basic` | `available` | `ts_code`, `symbol`, `name`, `market`, `exchange`, `list_status`, `list_date`, `delist_date`, `is_hs` | Candidate security master input for identifier and listing metadata checks. |

These results do not prove full historical coverage, point-in-time safety, licensing suitability, formal-label readiness, or production suitability.

## 3. Mapping To Prism Research Concepts

### 3.1 `daily` Raw OHLCV

Future non-production mapping:

| Tushare field | Prism research concept | Status | Notes |
| --- | --- | --- | --- |
| `ts_code` | vendor security identifier | raw/source-observed | Must be mapped to Prism `code` through a separate identifier policy. |
| `trade_date` | vendor price date | raw/source-observed | Cannot replace an official frozen trading calendar. |
| `open` | raw open price | raw/source-observed | Raw price only; not adjusted return ready. |
| `high` | raw high price | raw/source-observed | Useful for diagnostics, not formal execution proof. |
| `low` | raw low price | raw/source-observed | Useful for diagnostics, not formal execution proof. |
| `close` | raw close price | raw/source-observed | Raw return input only under research-only constraints. |
| `pre_close` | vendor previous close | raw/source-observed | Can support price consistency checks, not formal adjusted return. |
| `vol` | raw traded volume | raw/source-observed | May support liquidity diagnostics, not true partial-fill proof. |
| `amount` | raw traded amount | raw/source-observed | May support liquidity diagnostics, not true execution proof. |

Permitted future research use:

- raw price coverage audit;
- source-to-source price availability comparison;
- row count and date coverage diagnostics;
- raw return sanity checks under `research_only` status;
- liquidity diagnostics using `vol` / `amount`.

Not permitted:

- claiming formal adjusted returns;
- claiming execution-realistic fills;
- replacing existing Prism production price behavior;
- deriving official trade calendar coverage from price rows alone;
- treating missing rows or zero volume as definitive suspension status.

### 3.2 `adj_factor`

Future non-production mapping:

| Tushare field | Prism research concept | Status | Notes |
| --- | --- | --- | --- |
| `ts_code` | vendor security identifier | raw/source-observed | Must align with the same identifier policy used for `daily`. |
| `trade_date` | vendor adjustment date | raw/source-observed | Requires coverage audit and timestamp discipline. |
| `adj_factor` | vendor adjustment factor | raw/source-observed adjustment input | Not sufficient by itself to mark returns as formal adjusted returns. |

Permitted future research use:

- validating whether a reproducible raw-to-adjusted transformation is possible;
- checking adjustment-factor coverage for candidate symbols and windows;
- detecting raw price discontinuities that may correspond to corporate actions;
- designing a future qfq policy, subject to separate acceptance.

Not permitted:

- generating formal adjusted return before the adjustment policy is accepted;
- using factor availability alone as proof of PIT-safe adjusted price;
- writing adjusted prices into formal labels;
- upgrading existing labels to `formal_label_ready`;
- treating adjusted returns as production-ready.

The P1-A Card 2 rule remains in force: without complete adjustment-policy acceptance, raw returns and factor-derived diagnostics remain `research_only` and `adjustment_policy_not_formal`.

### 3.3 `stock_basic`

Future non-production mapping:

| Tushare field | Prism research concept | Status | Notes |
| --- | --- | --- | --- |
| `ts_code` | vendor security identifier | raw/source-observed | Candidate mapping key only. |
| `symbol` | vendor short symbol | raw/source-observed | Must not be used as the only canonical identifier. |
| `name` | vendor security name | raw/source-observed | Useful for diagnostics, but names may change. |
| `market` | vendor market category | raw/source-observed metadata | Requires semantic mapping before research use. |
| `exchange` | exchange code | raw/source-observed metadata | Useful for market segmentation checks. |
| `list_status` | current listing status | raw/source-observed metadata | Needs PIT handling before historical eligibility use. |
| `list_date` | listing date | raw/source-observed metadata | Can support listing-age diagnostics after validation. |
| `delist_date` | delisting date | raw/source-observed metadata | Needs careful null and historical interpretation. |
| `is_hs` | vendor connect flag | raw/source-observed metadata | Auxiliary only; not a Prism eligibility decision. |

Permitted future research use:

- identifier normalization diagnostics;
- duplicate-code and listing-date sanity checks;
- market / exchange coverage summaries;
- stock master completeness checks.

Not permitted:

- replacing Prism `eligible_universe` decisions;
- generating candidate eligibility directly from `stock_basic`;
- rewriting A/B/C tiers;
- modifying production sorting or candidate inclusion logic;
- treating current `list_status` as historical point-in-time eligibility without a separate historical audit.

`stock_basic` is a security master input, not a trading universe authority.

## 4. Raw / Source-Observed Fields

All Tushare fields in this design are source-observed inputs.

They must initially be represented with explicit provenance:

- `provider`: `tushare`;
- `interface`: `daily`, `adj_factor`, or `stock_basic`;
- `request_timestamp`;
- `response_timestamp`;
- `params_fingerprint`;
- `response_sha256`;
- `row_count`;
- `field_list`;
- `source_status`;
- `license_status`;
- `archive_reference`;
- `research_only`: `true`.

Fields that must remain raw/source-observed:

- all `daily` prices and volume fields;
- all `adj_factor` values;
- all `stock_basic` metadata;
- any derived coverage count, null count, or hash;
- any raw return produced only for audit.

Fields that must not be produced from this source design:

- `formal_label_ready`;
- `formal_adjusted_return`;
- `formal_excess_return`;
- `execution_realistic_return`;
- `formal_execution_eligible`;
- production ranking score;
- replacement A/B/C tier.

## 5. Archive And Traceability Design

If a later approved non-production adapter POC is allowed, raw responses must remain outside the Prism repo.

Recommended private layout:

```text
~/.prism-private/tushare-poc/
  raw/
    <run_id>/
      <request_id>_<interface>.json
  summaries/
    <run_id>_redacted_summary.json
```

Raw archive requirements:

- repo-external path only;
- permissions restricted to the local operator;
- no raw vendor files under `data/quant`, `docs`, `packages`, tests, notebooks, or temp folders inside repo;
- no token, account metadata, screenshots, balance information, or paid-plan details;
- deletion and retention policy must be decided before repeated runs.

Per request, record:

| Item | Required | Repo-safe? | Notes |
| --- | --- | --- | --- |
| endpoint/interface name | yes | yes | Example: `daily`. |
| sanitized params summary | yes | yes | Must exclude token and account-sensitive values. |
| params fingerprint | yes | yes | Stable SHA256 of canonical params with token removed. |
| request timestamp | yes | yes | ISO 8601 with timezone. |
| response timestamp | yes | yes | Local receipt time; provider timestamp if available. |
| returned field list | yes | yes | Field names only, no row values. |
| row count | yes | yes | Count only. |
| missing field list | yes | yes | Field names only. |
| response SHA256 | yes | yes | Hash of private raw response. |
| raw response body | yes, if archived | no | Repo-external private storage only. |
| token | no | no | Never write or print. |

Redacted summaries may enter the repo only if they contain no row-level vendor data and cannot reconstruct a vendor dataset.

## 6. Label And Backtest Implications

This source design cannot upgrade Prism labels.

Current allowed status for future derived checks:

- `research_only`;
- `source_observed`;
- `raw_price_observed`;
- `adjustment_factor_observed`;
- `security_master_observed`;
- `formal_label_ready=false`;
- `formal_execution_eligible=false`.

Reasons formal outputs remain blocked:

- `trade_cal` is not available, so official trading calendar freeze is unresolved.
- `index_daily` is not available, so CSI500 / HS300 benchmark returns are unresolved.
- `stk_limit` is not available, so limit-up/down execution flags are unresolved.
- `suspend_d` did not return required suspend/resume fields in the POC.
- `pro_bar` direct qfq probe failed, so adjusted OHLC availability is unresolved.
- `adj_factor` alone has not passed a complete adjustment-policy, PIT, and license acceptance.

Therefore this design must not generate or imply:

- formal labels;
- formal adjusted return;
- formal market excess return;
- execution-realistic return;
- production-ready quant health.

## 7. Open Gaps

| Gap | Current POC status | Required before formal use |
| --- | --- | --- |
| Official trading calendar | `trade_cal` blocked | Permission/points or alternate source; coverage and hash manifest. |
| CSI500 / HS300 benchmark | `index_daily` blocked | Permission/points or alternate source; benchmark manifest and return coverage. |
| Limit-up/down fields | `stk_limit` blocked | Permission/points or alternate source; up/down limit coverage and execution flag policy. |
| Suspend/resume fields | `suspend_d` partial | Correct endpoint/fields/permissions; daily expansion policy; missing value semantics. |
| QFQ adjusted OHLC | `pro_bar` direct probe failed | SDK-mediated POC or alternate qfq source; adjustment method acceptance. |
| PIT semantics | unresolved | Provider timestamp, data revision, and historical availability policy. |
| License / archive rights | unresolved | Human confirmation for local private raw archive and redacted repo summaries. |
| Cost / rate limits | unresolved | Human confirmation of积分、费用、frequency, and sustainable archive schedule. |

Until these gaps are closed, Tushare cannot be used as the source for formal excess return or execution-realistic backtests in Prism.

## 8. Future Development Cards

These are planning notes only, not implementation approval.

### Card A: Raw OHLCV Source Audit Design

- Input: `daily` raw OHLCV.
- Output: redacted coverage design, not `data/quant`.
- Purpose: define symbol/date coverage checks and hash manifest format.
- Guardrail: no labels, no formal adjusted return, no production use.

### Card B: Adjustment Factor Policy Validation

- Input: `adj_factor` plus an approved raw price sample.
- Output: adjustment-policy validation report.
- Purpose: determine whether a reproducible qfq-style research transformation can be defended.
- Guardrail: no formal adjusted return until policy, coverage, PIT, and licensing pass.

### Card C: Security Master Crosswalk Design

- Input: `stock_basic`.
- Output: identifier and metadata mapping design.
- Purpose: support code normalization diagnostics.
- Guardrail: must not replace Prism eligible universe or A/B/C.

### Card D: Blocked Capability Resolution

- Input: permission/cost decisions for `trade_cal`, `index_daily`, `stk_limit`, `suspend_d`, and qfq adjusted price.
- Output: continue / pause / switch-source decision.
- Purpose: decide whether Tushare can cover the P1-A hardening gaps.
- Guardrail: no adapter or data generation before approval.

## 9. Decision

Recommended status: **conditional source-design continue only**.

Allowed:

- continue documenting non-production designs for `daily`, `adj_factor`, and `stock_basic`;
- prepare acceptance criteria for a future adapter card;
- keep raw archive and redacted summary discipline.

Not allowed:

- implement a Tushare adapter;
- connect to `packages/quant`;
- write `data/quant`;
- generate formal labels;
- generate formal excess return;
- generate formal adjusted return;
- generate execution-realistic backtest;
- modify production sorting;
- replace A/B/C;
- build pages;
- build Prism Edge;
- expose Expected 5D;
- add ML.

Before any implementation card, the pasted token from the POC conversation should be rotated and the new token should be injected only through local environment or approved secret handling.
