# Prism Quant Sprint 0 Price And Execution Audit

Generated at: 2026-04-28T18:05:29+08:00

Scope: Sprint 0 audit only. This report records what the current repository can and cannot support for price labels and execution assumptions; it does not start formal backtesting.

## Data Sources Observed

- Current screener scan uses Sina/real-time market inputs and Sina daily K-line (`CN_MarketData.getKLineData`, `scale=240`, `ma=no`) with Eastmoney/akshare fallbacks for components and snapshots in some paths.
- Watchlist snapshots record `price_basis = 新浪实时行情`, `flow_basis = 东方财富资金流`, and `tech_basis = 240分钟K线`.
- Research backfill uses local cache `stock-screener/data/research_backfill/cache/price_kline/*.json` and reports identify that cache as the preferred replay price source.
- Price cache coverage: 1571 files, 84500 OHLCV rows, date range 2023-11-20 to 2024-04-10. Columns observed: `amount`, `amplitude`, `change`, `change_pct`, `close`, `date`, `high`, `low`, `open`, `source`, `turnover`, `volume`.
- Price cache source column coverage: 78867/84500 rows (93.3%). Source values observed: tx=78867. Rows without `source` must be treated as source-unknown.

## Forward Price Availability

- 2024 research backfill AI/scan candidate rows checked: 1383.
- Candidate trade-date price row available: 1383/1383 (100.0%).
- Next open/close row available: 1383/1383 (100.0%).
- T+3 close row available: 1383/1383 (100.0%).
- T+5 close row available: 1383/1383 (100.0%).
- T+10 close row available: 1260/1383 (91.1%).
- 2026 current operational artifacts do not yet provide future price rows for their signal dates inside a canonical label store, so they cannot produce formal forward labels in Sprint 0.

## Execution Assumptions Audit

| Item | Current support | P0 conservative treatment |
| --- | --- | --- |
| Daily price source | Sina current/K-line paths plus local research price cache; some cache rows mark `source=tx`, many older rows have no explicit source. | Use only hashed cached rows for replay; mark row source unknown when `source` is absent. |
| Adjustment policy | `ma=no` appears in Sina K-line calls and no `adj`, `qfq`, `hfq`, split/dividend, or adjustment factor field was found. | Treat prices as unadjusted/adjustment-unknown. Formal conclusions are blocked until adjustment policy is explicit. |
| Trading calendar | No official exchange calendar artifact found. Price cache rows can infer observed sessions for 2024 only. | For labels, step through available price rows per symbol; missing rows are unknown, not automatically holidays. |
| Next open / next close | Available in 2024 price cache rows when the next trading row exists. | Allow preliminary research labels for 2024 backfill only; require missing-label flags for absent rows. |
| Suspend field | No explicit suspend status field found. Zero-volume/absent rows are not reliable suspend flags. | Do not claim executable labels when suspend status is unknown; carry `suspend_status_unknown`. |
| Limit up/down field | No explicit limit price/status or order-block field found. Risk text may mention limit retreat, but it is not a machine execution flag. | Do not model filled orders through涨跌停; carry `limit_status_unknown` and exclude from formal execution backtest until implemented. |
| T+1 | Existing reports show next-day/3-day/5-day net outcomes, but a canonical T+1 execution ledger does not exist. | Treat every signal as executable no earlier than next observed trading row; intraday/midday signals also default to next session until minute/PIT data exists. |
| Costs | Historical review reports use 0.60% buy + 0.60% sell friction, roundtrip 1.20%. New Sprint 0 config decomposes commission, stamp tax, slippage, and an impact placeholder. | All forward labels and backtests must deduct configured costs; no no-cost strategy claims. |
| Failed / partial fill | No failed order or partial fill artifact found. | Unsupported in P0; block formal execution conclusions that require fill simulation. |
| Benchmark | Pool labels mention CSI500 + HS300, but no benchmark price series artifact was found. | Raw returns can be computed for covered 2024 rows; excess returns are blocked until benchmark series is frozen and hashed. |

## What Sprint 0 Can Support

- Baseline freezing of existing signal and price artifacts with hashes.
- Preliminary 2024 research-only raw forward labels using cached OHLC rows where next open/close exists.
- Cost-aware report design, because `data/config/quant-research.json` now decomposes commission, stamp tax, slippage, and impact placeholder.
- Report-only data quality gates for missing adjustment policy, missing suspend/limit fields, and missing benchmark data.

## What Sprint 0 Cannot Support

- Formal adjusted-return conclusions, because adjustment status is not proven.
- Formal excess-return conclusions, because benchmark series are not frozen.
- Execution-realistic backtests, because suspend,涨跌停, failed order, partial fill, and T+1 ledgers are not explicit.
- 2026 forward labels, because current operational artifacts do not yet have canonical future price rows attached.

## P0 Conservative Rules

- Use `next_open` as primary entry and `next_close` as comparison only when both are present in the next observed price row.
- Mark labels missing instead of imputing through absent rows.
- Exclude rows with unknown suspend/limit status from formal execution backtests; they may remain in coverage reports.
- Deduct configured transaction costs before making any strategy-quality statement.
- Keep all quant labels report-only until PIT provenance, benchmark series, and execution constraints are frozen.

## Deferred Suggestions

- Add an official A-share trading calendar artifact and hash it in the next baseline manifest.
- Add adjusted OHLC data with explicit qfq/hfq/raw policy and corporate-action provenance.
- Add machine-readable suspend and limit-up/down status fields before portfolio backtesting.
- Freeze benchmark price series for CSI500, HS300, CSI1000, and equal-weight eligible pool before excess-return reports.
