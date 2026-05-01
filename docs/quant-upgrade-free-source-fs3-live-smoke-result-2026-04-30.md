# Prism Free-Source FS-3 Live Smoke Result

Date: 2026-04-30
Scope: repo-external BaoStock + AKShare live smoke
Status: completed; redacted report only

## 0. Boundary

This FS-3 run used a repo-external scratch environment only. It did not modify `packages/quant`, did not write `data/quant`, did not modify dependency files, lockfiles, or the main project venv, and did not generate formal labels, formal excess return, formal adjusted return, execution-realistic backtest, production ranking, A/B/C changes, pages, Prism Edge, Expected 5D, or ML outputs.

Raw provider responses were archived only under the approved repo-external private scratch root. This repo report contains only redacted endpoint-level availability metadata.

Important license boundary: **free callable access does not mean the data may be redistributed**. Raw vendor data must stay out of the repo and must not be treated as production input.

## 1. Run Summary

| Field | Value |
| --- | --- |
| Run id | `fs3-live-smoke-20260430T234434+0800` |
| Generated at | `2026-04-30T15:48:05+00:00` |
| Sample stocks | 贵州茅台、宁德时代、平安银行 |
| Sample indexes | HS300、CSI500 |
| Date window | `2024-01-02..2024-01-10` |
| BaoStock version | `0.9.1` |
| AKShare version | `1.18.59` |
| Raw archive location | Approved repo-external private scratch root, opaque pointers only below |
| Raw retention note | Private scratch retention target: 7 days unless manually shortened |

Endpoint status counts:

| Status | Count |
| --- | ---: |
| `available` | 8 |
| `partial` | 1 |
| `network_error` | 1 |
| `provider_error` | 0 |
| `empty` | 0 |
| `blocked` | 0 |

## 2. Endpoint Results

### BaoStock

| Layer | Endpoint | Status | Row count | Package |
| --- | --- | --- | ---: | --- |
| calendar | `query_trade_dates` | `available` | 9 | `baostock==0.9.1` |
| stock_basic | `query_stock_basic` | `available` | 3 | `baostock==0.9.1` |
| raw_daily | `query_history_k_data_plus_raw_daily` | `available` | 21 | `baostock==0.9.1` |
| qfq_candidate | `query_history_k_data_plus_qfq` | `available` | 21 | `baostock==0.9.1` |
| index_daily | `query_history_k_data_plus_index_daily` | `available` | 14 | `baostock==0.9.1` |
| tradestatus_isst | `query_history_k_data_plus_tradestatus_isst` | `available` | 21 | `baostock==0.9.1` |

#### `query_trade_dates`

- Params summary: `date_window=2024-01-02..2024-01-10`, `sample=calendar_only`
- Retrieved at: `2026-04-30T15:47:29+00:00`
- Field list: `calendar_date`, `is_trading_day`
- Non-null summary: `calendar_date=9`, `is_trading_day=9`
- Response hash: `f820f40ce0691df9a4a2c4cae349f98566d7354e109303b2442c05f743f02981`
- Raw archive pointer: `fs3-live-smoke:fs3-live-smoke-20260430T234434+0800:baostock:query_trade_dates:f820f40ce0691df9`
- Error summary: none

#### `query_stock_basic`

- Params summary: `sample_stocks=3_named_stocks`, `code_format=baostock_exchange_prefixed`
- Retrieved at: `2026-04-30T15:47:29+00:00`
- Field list: `code`, `code_name`, `ipoDate`, `outDate`, `type`, `status`
- Non-null summary: `code=3`, `code_name=3`, `ipoDate=3`, `outDate=0`, `type=3`, `status=3`
- Response hash: `8e6eafdb26ed76c696641e5f303052a686c87dc95990bb78d5c07929f85fcf20`
- Raw archive pointer: `fs3-live-smoke:fs3-live-smoke-20260430T234434+0800:baostock:query_stock_basic:8e6eafdb26ed76c6`
- Error summary: none

#### `query_history_k_data_plus_raw_daily`

- Params summary: `sample_stocks=3_named_stocks`, `date_window=2024-01-02..2024-01-10`, `adjustflag=3`
- Retrieved at: `2026-04-30T15:47:29+00:00`
- Field list: `date`, `code`, `open`, `high`, `low`, `close`, `preclose`, `volume`, `amount`, `adjustflag`, `turn`, `tradestatus`, `pctChg`, `isST`
- Non-null summary: `date=21`, `code=21`, `open=21`, `high=21`, `low=21`, `close=21`, `preclose=21`, `volume=21`, `amount=21`, `adjustflag=21`, `turn=21`, `tradestatus=21`, `pctChg=21`, `isST=21`
- Response hash: `cad6b5045f07f1d9d5aafa497114614c199a9e602f98acc36fd7a1fe048c2d64`
- Raw archive pointer: `fs3-live-smoke:fs3-live-smoke-20260430T234434+0800:baostock:query_history_k_data_plus_raw_daily:cad6b5045f07f1d9`
- Error summary: none

#### `query_history_k_data_plus_qfq`

- Params summary: `sample_stocks=3_named_stocks`, `date_window=2024-01-02..2024-01-10`, `adjustflag=2`
- Retrieved at: `2026-04-30T15:47:29+00:00`
- Field list: `date`, `code`, `open`, `high`, `low`, `close`, `preclose`, `volume`, `amount`, `adjustflag`, `turn`, `tradestatus`, `pctChg`, `isST`
- Non-null summary: `date=21`, `code=21`, `open=21`, `high=21`, `low=21`, `close=21`, `preclose=21`, `volume=21`, `amount=21`, `adjustflag=21`, `turn=21`, `tradestatus=21`, `pctChg=21`, `isST=21`
- Response hash: `01fc0640ee7e7d0d00c6c3ec9ae42f5c0b09a45f6ac42c2538479176e28a4714`
- Raw archive pointer: `fs3-live-smoke:fs3-live-smoke-20260430T234434+0800:baostock:query_history_k_data_plus_qfq:01fc0640ee7e7d0d`
- Error summary: none

#### `query_history_k_data_plus_index_daily`

- Params summary: `sample_indexes=HS300_CSI500`, `date_window=2024-01-02..2024-01-10`, `adjustflag=3`
- Retrieved at: `2026-04-30T15:47:29+00:00`
- Field list: `date`, `code`, `open`, `high`, `low`, `close`, `preclose`, `volume`, `amount`, `pctChg`
- Non-null summary: `date=14`, `code=14`, `open=14`, `high=14`, `low=14`, `close=14`, `preclose=14`, `volume=14`, `amount=14`, `pctChg=14`
- Response hash: `ac1fc43e0455c241b68b668e366563ac42170f355f768684d5e0d45daf0ff442`
- Raw archive pointer: `fs3-live-smoke:fs3-live-smoke-20260430T234434+0800:baostock:query_history_k_data_plus_index_daily:ac1fc43e0455c241`
- Error summary: none

#### `query_history_k_data_plus_tradestatus_isst`

- Params summary: `sample_stocks=3_named_stocks`, `date_window=2024-01-02..2024-01-10`, `fields_subset=tradestatus_isST`
- Retrieved at: `2026-04-30T15:47:29+00:00`
- Field list: `date`, `code`, `open`, `high`, `low`, `close`, `preclose`, `volume`, `amount`, `adjustflag`, `turn`, `tradestatus`, `pctChg`, `isST`
- Non-null summary: `date=21`, `code=21`, `tradestatus=21`, `isST=21`; other returned daily fields were also non-null for all 21 rows
- Response hash: `cad6b5045f07f1d9d5aafa497114614c199a9e602f98acc36fd7a1fe048c2d64`
- Raw archive pointer: `fs3-live-smoke:fs3-live-smoke-20260430T234434+0800:baostock:query_history_k_data_plus_tradestatus_isst:cad6b5045f07f1d9`
- Error summary: none

### AKShare

| Layer | Endpoint | Status | Row count | Package |
| --- | --- | --- | ---: | --- |
| raw_daily | `stock_zh_a_hist_raw_daily` | `network_error` | 0 | `akshare==1.18.59` |
| qfq_candidate | `stock_zh_a_hist_qfq` | `partial` | 7 | `akshare==1.18.59` |
| index_daily | `stock_zh_index_hist_csindex` | `available` | 14 | `akshare==1.18.59` |
| suspend_event | `stock_tfp_em` | `available` | 850 | `akshare==1.18.59` |

#### `stock_zh_a_hist_raw_daily`

- Params summary: `sample_stocks=3_named_stocks`, `date_window=2024-01-02..2024-01-10`, `adjust=none`
- Retrieved at: `2026-04-30T15:47:50+00:00`
- Field list: none returned
- Non-null summary: none
- Response hash: `17aad697f9e58e4ce9077bc87cb2f26ee1b7595acb534d9823ddf2fc903bf874`
- Raw archive pointer: `fs3-live-smoke:fs3-live-smoke-20260430T234434+0800:akshare:stock_zh_a_hist_raw_daily:17aad697f9e58e4c`
- Error summary: `ProxyError` for all 3 sample stocks via the Eastmoney daily endpoint; no rows returned

#### `stock_zh_a_hist_qfq`

- Params summary: `sample_stocks=3_named_stocks`, `date_window=2024-01-02..2024-01-10`, `adjust=qfq`
- Retrieved at: `2026-04-30T15:47:50+00:00`
- Field list: `日期`, `股票代码`, `开盘`, `收盘`, `最高`, `最低`, `成交量`, `成交额`, `振幅`, `涨跌幅`, `涨跌额`, `换手率`
- Non-null summary: all listed fields non-null for 7 returned rows
- Response hash: `ad888b95e605bddca1695c62bc10c3ec185cfa8e91cde3a0f0c01a90d9b41533`
- Raw archive pointer: `fs3-live-smoke:fs3-live-smoke-20260430T234434+0800:akshare:stock_zh_a_hist_qfq:ad888b95e605bddc`
- Error summary: 1/3 sample stocks returned rows; 2/3 failed with `ProxyError` via the Eastmoney daily endpoint

#### `stock_zh_index_hist_csindex`

- Params summary: `sample_indexes=HS300_CSI500`, `date_window=2024-01-02..2024-01-10`
- Retrieved at: `2026-04-30T15:47:53+00:00`
- Field list: `日期`, `指数代码`, `指数中文全称`, `指数中文简称`, `指数英文全称`, `指数英文简称`, `开盘`, `最高`, `最低`, `收盘`, `涨跌`, `涨跌幅`, `成交量`, `成交金额`, `样本数量`, `滚动市盈率`
- Non-null summary: all listed fields non-null for 14 returned rows
- Response hash: `ac3433511b2fc86278b7de76ad3e25f73f782e08b1206335e3f10dbdd888c757`
- Raw archive pointer: `fs3-live-smoke:fs3-live-smoke-20260430T234434+0800:akshare:stock_zh_index_hist_csindex:ac3433511b2fc862`
- Error summary: none

#### `stock_tfp_em`

- Params summary: `sample=event_only_endpoint`, `date_arg=20240102`
- Retrieved at: `2026-04-30T15:48:05+00:00`
- Field list: `序号`, `代码`, `名称`, `停牌时间`, `停牌截止时间`, `停牌期限`, `停牌原因`, `所属市场`, `预计复牌时间`
- Non-null summary: `序号=850`, `代码=850`, `名称=850`, `停牌时间=850`, `停牌截止时间=832`, `停牌期限=850`, `停牌原因=850`, `所属市场=850`, `预计复牌时间=765`
- Response hash: `c1eb4ed42eec707ef60c534c479ff6f7eb1e13826bc75423cbfdd63bc048659e`
- Raw archive pointer: `fs3-live-smoke:fs3-live-smoke-20260430T234434+0800:akshare:stock_tfp_em:c1eb4ed42eec707e`
- Error summary: none

## 3. Research-Only Support

Current smoke suggests these fields can support later non-production, research-only exploration:

| Need | Current evidence | Status |
| --- | --- | --- |
| Trading calendar | BaoStock `query_trade_dates` returned expected fields for the window | research-only candidate |
| Stock basic | BaoStock `query_stock_basic` returned identity/listing fields for the 3-stock sample | research-only candidate |
| Raw A-share daily OHLCV | BaoStock raw daily returned expected fields; AKShare raw daily failed in this environment | BaoStock research-only candidate; AKShare cross-check not reliable in this run |
| QFQ candidate | BaoStock qfq returned expected fields; AKShare qfq partially returned fields | research-only candidate only |
| Index daily benchmark candidate | BaoStock and AKShare index daily both returned fields for HS300 / CSI500 | research-only candidate only |
| `tradestatus` / `isST` | BaoStock returned both fields in the raw daily sample | execution candidate only |
| Suspend event | AKShare `stock_tfp_em` returned event fields | event-only supplement |

## 4. Blocked And Non-Production Conclusions

These conclusions remain unchanged after FS-3:

1. Free callable access does not imply redistribution rights; raw data remains repo-external only.
2. QFQ availability does **not** make formal adjusted return available. No independent adjustment factor, revision audit, or PIT/as-of proof was produced.
3. Index daily availability does **not** make formal excess return available. No formal benchmark freeze or label contract was produced.
4. `tradestatus` / `isST` availability does **not** prove real execution or fills.
5. AKShare suspend event data is event-only; it is not daily execution eligibility.
6. Limit up/down price, failed order, and partial fill remain blocked.
7. Formal labels, formal excess return, formal adjusted return, and execution-realistic backtest remain blocked.
8. Page work, production sorting, A/B/C, Prism Edge, Expected 5D, and ML remain blocked.

## 5. FS-4 Gate

FS-3 completion does not automatically allow FS-4.

Recommended next step is an independent FS-3 acceptance report. FS-4 should remain blocked until that acceptance explicitly permits FS-4 planning.

