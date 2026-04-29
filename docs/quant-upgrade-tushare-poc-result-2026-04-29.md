# Prism Quant Tushare Pro POC Result

Date: 2026-04-29
Scope: Tushare Pro non-production availability POC
Status: completed with blockers
Production impact: none

References:

- `docs/quant-upgrade-tushare-poc-runbook-2026-04-29.md`
- `docs/quant-upgrade-tushare-field-availability-matrix-2026-04-29.md`
- `docs/quant-upgrade-tushare-poc-acceptance-checklist-2026-04-29.md`

## 1. Executive Summary

The non-production POC reached Tushare Pro and validated a small field-availability sample. It did not connect to `packages/quant`, did not write `data/quant`, did not generate labels, did not calculate formal excess return, and did not run an execution-realistic backtest.

POC result:

- POC execution status: `completed_with_blockers`
- Interfaces probed: `9`
- Available: `daily`, `adj_factor`, `stock_basic`
- Permission / points blocked: `trade_cal`, `index_daily` for CSI500, `index_daily` for HS300, `stk_limit`
- SDK or direct API mismatch: `pro_bar`
- Partial / field gap: `suspend_d`
- Raw vendor responses: archived only outside repo
- Repo output: this redacted result document only
- Decision recommendation: **conditional continue / pause on blocked capabilities**

The current account can support limited raw price and adjustment-factor validation. It cannot yet support the P1-A benchmark, calendar, limit-up/down, or execution-hardening needs without permission/points upgrades or an alternate data source.

## 2. Security And Boundary Result

| Check | Result | Notes |
| --- | --- | --- |
| Token source used by POC | `launchctl getenv TUSHARE_TOKEN` | The token value was not printed or written. |
| Token value recorded | `no` | No token value is present in this document, repo files, or POC summaries. |
| Chat exposure risk | `present` | A token value was pasted into chat before this run. Rotate it before any future adapter or production-like work. |
| API dependency installed | `no` | The POC used Python standard library HTTP only. |
| Temporary repo script added | `no` | No POC script was committed or left in repo. |
| Raw archive in repo | `no` | Raw responses were stored only in a repo-external private path. |
| `packages/quant` modified | `no` | No quant package code was changed. |
| `data/quant` modified | `no` | No quant data artifacts were written. |
| Formal labels / excess / execution-realistic backtest | `no` | No formal research or production outputs were generated. |
| Production ranking / A/B/C / UI / Prism Edge / Expected 5D / ML | `no_change` | No production or product path was touched. |

Raw archive location:

- `/Users/yangbishang/.prism-private/tushare-poc/raw/20260429T231346+0800`

Private sanitized run summary:

- `/Users/yangbishang/.prism-private/tushare-poc/poc_summary_20260429T231346+0800.json`

Both paths are outside the Prism repo.

## 3. Interface Call Summary

No row-level vendor data is included below. Only endpoint names, field names, row counts, status, and response hashes are recorded.

| Capability | Interface | Status | Row count | Returned fields | Missing required fields | Response hash |
| --- | --- | --- | ---: | --- | --- | --- |
| Trading calendar | `trade_cal` | `permission_or_points_blocked` | 0 | none | `exchange`, `cal_date`, `is_open`, `pretrade_date` | `3ad12b318878f7dfe6280982ba6153962e4c314fe9ecf7f73964f960383916fe` |
| CSI500 index daily | `index_daily` | `permission_or_points_blocked` | 0 | none | `ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `pre_close`, `vol`, `amount` | `be294d202cbed9997d545bf411b0de0f94b4e8b823137596baade12f7ba31f53` |
| HS300 index daily | `index_daily` | `permission_or_points_blocked` | 0 | none | `ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `pre_close`, `vol`, `amount` | `2eec753bd9080450bf902b850c6d018d6b7be4b2cfc7cbea6ccd39477624f0ee` |
| Raw daily OHLCV | `daily` | `available` | 6 | `ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `pre_close`, `vol`, `amount` | none | `b8d5587244faeff1303e779b8396813eec362f3cb9eedb2a8f76d89dd9a4d7d3` |
| Adjustment factor | `adj_factor` | `available` | 6 | `ts_code`, `trade_date`, `adj_factor` | none | `224fef58a1042d9e556b5e7f0c64c60fea0d0ed8d6e13c6a7f882f71a5ca7c53` |
| QFQ adjusted price direct probe | `pro_bar` | `error_or_unknown` | 0 | none | `ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `pre_close`, `vol`, `amount` | `ba12dde13e71906b7ea3a4ae6063e1331cf0d34520b9a4b6d90f011c4500b655` |
| Suspend / resume | `suspend_d` | `field_missing` | 19 | `ts_code` | `suspend_date`, `resume_date`, `ann_date`, `suspend_reason` | `9fb853762bab0b05224c32beffa73291c71026a550e3ae8ca0416b7b5fdfbb53` |
| Limit up / down | `stk_limit` | `permission_or_points_blocked` | 0 | none | `ts_code`, `trade_date`, `up_limit`, `down_limit` | `34b625e6d746f17ee66391dd135544e81f70085312ef0dd5fc83460fbe0419f0` |
| Stock basic | `stock_basic` | `available` | 5511 | `ts_code`, `symbol`, `name`, `market`, `exchange`, `list_status`, `list_date`, `delist_date`, `is_hs` | none | `8575927f05b09b577f65736bc683ff5528c15a2ffc09042f653436d64094189c` |

## 4. Field Availability Matrix

| Data need | POC result | Can support P1-A now? | Notes |
| --- | --- | --- | --- |
| Trading calendar | `permission_or_points_blocked` | `no` | Cannot freeze official trading dates from this token. |
| CSI500 benchmark daily | `permission_or_points_blocked` | `no` | Cannot generate formal market benchmark inputs. |
| HS300 benchmark daily | `permission_or_points_blocked` | `no` | Cannot generate secondary formal benchmark inputs. |
| Raw stock OHLCV | `available` | `partial` | Useful for non-production field validation; not sufficient for formal adjusted labels by itself. |
| Adjustment factor | `available` | `partial` | Supports future adjusted-price design, but formal policy still requires coverage, licensing, and PIT rules. |
| QFQ adjusted OHLC | `not_available_via_direct_api_probe` | `no` | Direct `pro_bar` probe returned an interface-name error; SDK-mediated use needs a separate controlled POC if allowed. |
| Suspend / resume | `field_missing` | `no` | Endpoint returned rows but not required date/reason fields under this request. Needs field mapping, permission, or alternate endpoint review. |
| Limit up / down | `permission_or_points_blocked` | `no` | Cannot support execution flags for limit-up/down with current access. |
| Stock basic metadata | `available` | `partial` | Useful for symbol metadata, listing status, and exchange/market checks; still subject to license and archive policy. |

## 5. Permission / Points / Cost Status

| Interface | Permission / points status | POC conclusion |
| --- | --- | --- |
| `trade_cal` | blocked | Required for formal trading calendar; current access is insufficient. |
| `index_daily` | blocked | Required for CSI500 / HS300 benchmark; current access is insufficient. |
| `daily` | allowed in sample | Raw OHLCV is accessible for the checked symbol/date range. |
| `adj_factor` | allowed in sample | Adjustment factor is accessible for the checked symbol/date range. |
| `pro_bar` | direct API probe failed | Treat as SDK-mediated or unavailable until separately validated. |
| `suspend_d` | partially accessible | Required fields were not returned; cannot support execution flags now. |
| `stk_limit` | blocked | Required for limit-up/down execution flags; current access is insufficient. |
| `stock_basic` | allowed in sample | Basic stock metadata is accessible. |

The POC did not inspect account balances,积分余额, paid-plan screenshots, contracts, or personal account metadata.

## 6. Hash / Timestamp / Raw Archive Result

The POC validated the recording scheme without writing vendor rows into the repo.

Recorded per request:

- endpoint name;
- sanitized request parameter fingerprint;
- local request timestamp;
- local response timestamp;
- returned field list;
- row count;
- missing field list;
- response SHA256;
- raw archive file path outside repo.

Not recorded in repo:

- token value;
- row-level vendor data;
- raw response bodies;
- account-sensitive metadata;
- screenshots;
- paid-account details.

The response hashes in this document can only be reconciled against the private raw archive. They do not grant redistribution rights and do not prove point-in-time correctness by themselves.

## 7. Acceptance Checklist Status

| Acceptance item | Status | Evidence |
| --- | --- | --- |
| Token not in repo | `pass` | No token value was written to files or printed by POC commands. |
| Token exposure risk handled | `warning` | Token was pasted in chat before the run; rotate before future work. |
| Raw vendor data not committed | `pass` | Raw responses are only under `/Users/yangbishang/.prism-private/tushare-poc/raw/20260429T231346+0800`. |
| Did not write `data/quant` | `pass` | No quant data artifacts were generated. |
| Did not connect `packages/quant` | `pass` | No quant package code was added or changed. |
| Scope limited to POC availability | `pass` | The POC only checked field, permission, hash, timestamp, and archive behavior. |
| No formal outputs | `pass` | No labels, formal excess return, adjusted return, or execution-realistic backtest were generated. |
| No production impact | `pass` | No production sorting, A/B/C, page, Prism Edge, Expected 5D, or ML changes. |
| Field availability matrix populated | `pass` | Runtime statuses are listed above. |
| Permission / cost / quota recorded | `partial` | Permission blocks were observed; actual plan cost and积分 requirements still need human confirmation. |
| Decision recommendation exists | `pass` | Recommendation is conditional continue only after permission/cost gaps are resolved. |

## 8. Impact On Prism Quant Hardening

What this POC can support now:

- Non-production validation that Tushare `daily` can provide raw OHLCV fields for a sample.
- Non-production validation that Tushare `adj_factor` can provide adjustment-factor fields for a sample.
- Non-production validation that `stock_basic` can provide basic security metadata.
- Hash/timestamp/raw archive discipline can be implemented without writing raw vendor data to repo.

What this POC cannot support now:

- Formal CSI500 / HS300 benchmark returns.
- Formal excess return.
- Official trading calendar freeze.
- Limit-up/down execution flags.
- Execution-realistic backtest.
- Formal adjusted return, because qfq adjusted OHLC was not validated and PIT/licensing policy is still unresolved.
- Formal suspend/resume execution eligibility, because required fields were missing from the sample response.

All outputs remain POC-only, report-only, and non-production.

## 9. Recommendation

Recommendation: **conditional continue, with blockers**.

Allowed next step:

- Continue only with a non-production adapter design for raw OHLCV, `adj_factor`, and `stock_basic` field validation, if licensing permits private raw archive and redacted summaries.

Blocked before P1-A can use Tushare as a full hardening source:

- Upgrade or confirm permission for `trade_cal`.
- Upgrade or confirm permission for `index_daily`.
- Upgrade or confirm permission for `stk_limit`.
- Resolve `suspend_d` field mapping or find a correct suspend/resume endpoint.
- Separately validate SDK-mediated `pro_bar` qfq/hfq behavior if adjusted OHLC is required.
- Confirm积分、费用、调用频率 and license terms for automated local research archive.
- Rotate the token that was pasted into chat before any future broader or production-like use.

If benchmark/calendar/limit/suspend permissions cannot be obtained at acceptable cost and license terms, Prism should pause Tushare adapter work for those capabilities and evaluate an alternate data source.
