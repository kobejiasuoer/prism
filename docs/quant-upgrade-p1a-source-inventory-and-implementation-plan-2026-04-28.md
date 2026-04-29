# Prism 量化升级 P1-A 数据源盘点与实施拆分

Date: 2026-04-28
Scope: P1-A pre-development source inventory and implementation plan
Source:
- `docs/quant-upgrade-p1a-hardening-acceptance-checklist-2026-04-28.md`
- `docs/quant-upgrade-p1-data-hardening-plan-2026-04-28.md`
- `data/quant/reports/price_execution_audit_latest.md`
- `data/quant/reports/panel_coverage_latest.md`
- `data/quant/reports/label_coverage_latest.md`
- current repository read-only inspection
Status: planning document only; no P1-A code or data generation

## 0. Boundary

This document is a source inventory and implementation split for P1-A only.

It does not implement P1-A. It does not modify `packages/quant`, does not modify `data/quant/reports/*`, does not generate benchmark data, does not add pages, does not add Prism Edge, and does not add ML.

P1-A must remain data-hardening and report-only. It must not affect production sorting, A/B/C, user-facing decision actions, or any production execution path.

## 1. Benchmark 数据源盘点

### 1.1 仓库里是否已有 CSI500 / HS300 / 指数价格数据

未发现可直接用于 P1-A 的 CSI500、HS300、CSI1000 指数日线价格序列。

Observed:

- `packages/screener/scan.py` 有指数成分和实时行情相关逻辑：
  - `load_hs300_with_quotes()`
  - `load_zz500_with_quotes()`
  - `_load_index_cons_with_em_quotes('000300', 'hs300')`
  - `_load_index_cons_with_em_quotes('000905', 'zz500')`
  - `_load_index_cons_with_sina_quotes('000300', 'hs300')`
  - `_load_index_cons_with_sina_quotes('000905', 'zz500')`
- 这些逻辑用于构建股票池和成分股行情，不是 frozen benchmark index OHLCV series。
- 当前未发现 `data/quant/benchmarks/`。
- 当前未发现 `stock-screener/data/index_cons_cache/`。
- 当前未发现 `benchmark_daily.jsonl` / `benchmark_manifest.json` 等可复现 benchmark artifact。

Conclusion:

- 仓库存在 HS300/CSI500 成分获取逻辑和 pool label 文字。
- 仓库没有可用于 formal excess return 的 CSI500/HS300 指数价格数据。
- P1-A 不能从当前 repo 直接计算 formal benchmark return。

### 1.2 缺哪些路径

P1-A 需要新增或冻结以下路径，但本盘点不生成它们：

| Missing path | Purpose |
| --- | --- |
| `data/quant/benchmarks/benchmark_daily.jsonl` | frozen benchmark OHLCV / close series |
| `data/quant/benchmarks/benchmark_manifest.json` | benchmark source, hash, revision, date coverage |
| `data/quant/reports/benchmark_freeze_audit_latest.md` | benchmark coverage and gap audit |
| `data/quant/calendars/trading_calendar.jsonl` | frozen trading calendar for benchmark/labels |

Optional but useful:

| Optional path | Purpose |
| --- | --- |
| `data/quant/benchmarks/benchmark_returns.jsonl` | precomputed entry/window-aligned benchmark returns |
| `data/quant/benchmarks/eligible_equal_weight_returns.jsonl` | internal equal-weight benchmark, if universe is reproducible |

### 1.3 Eligible universe equal-weight 是否能用现有 panel/labels 计算

可以计算一个 limited internal benchmark，但不能直接视为 formal eligible-universe benchmark。

Observed current data:

- `data/quant/panels/eligible_universe_snapshot.jsonl`
  - rows: 2958
  - date range: 2024-01-02 to 2026-04-21
  - source lanes:
    - `research_backfill_scan_history`: 854
    - `screener_scan_stale_outputs`: 2048
    - `screener_scan_current`: 56
  - data quality flag example: `universe_is_source_observed_not_full_exchange`
- `data/quant/labels/forward_return_labels.jsonl`
  - rows: 11064
  - label scope: `2024_research_backfill_only`
  - trade dates: 2024-01-02 to 2024-03-29
  - available labels: 10818

Implication:

- Existing labels can support an equal-weight return over labeled 2024 research backfill rows.
- This would be an `observed_candidate_equal_weight` or `observed_research_pool_equal_weight`, not a complete exchange universe or fully stable eligible universe.
- 2026 rows are coverage-only and cannot be used in formal forward label evaluation until forward windows mature and data hardening passes.
- If P1-A wants `eligible_equal_weight`, it must define whether the universe is:
  - all source-observed scan candidates,
  - unique code per date,
  - panel rows with labels only,
  - or a true pre-signal eligible universe.

Recommendation:

- First version may output `eligible_equal_weight_status=research_only_internal` if built only from current panel/labels.
- Do not call it a formal benchmark unless universe composition, weights, price coverage, and PIT provenance are frozen.

### 1.4 Benchmark 需要哪些字段

Benchmark daily rows should include:

| Field | Requirement |
| --- | --- |
| `benchmark_id` | stable ID: `CSI500`, `HS300`, `CSI1000`, `eligible_equal_weight` |
| `trade_date` | exchange trading date |
| `open` | benchmark open |
| `close` | benchmark close |
| `prev_close` | previous trading close |
| `high` | optional but recommended |
| `low` | optional but recommended |
| `volume` | optional for index, required if source provides |
| `amount` | optional for index, required if source provides |
| `return_close_to_close` | daily close-to-close return if precomputed |
| `calendar_id` | frozen trading calendar ID |
| `source_name` | e.g. AkShare, Eastmoney, vendor, internal |
| `source_artifact` | raw source path or fetch artifact |
| `source_hash` | sha256 of raw artifact |
| `generated_at` | generation time |
| `revision` | benchmark data revision |
| `coverage_status` | complete / partial / unavailable |

Benchmark return labels should additionally include:

| Field | Requirement |
| --- | --- |
| `entry_model` | `next_open` / `next_close` aligned with labels |
| `holding_window_days` | 1 / 3 / 5 / 10 |
| `entry_trade_date` | benchmark entry date |
| `exit_trade_date` | benchmark exit date |
| `benchmark_return` | aligned return |
| `benchmark_return_status` | complete / unavailable / partial |

### 1.5 Coverage、missing dates、hash 如何记录

P1-A benchmark manifest should record:

| Manifest field | Requirement |
| --- | --- |
| `schema_version` | stable manifest schema |
| `generated_at` | generation timestamp |
| `config_checksum` | checksum of benchmark config |
| `code_revision` | git revision when generated |
| `benchmarks[]` | one entry per benchmark |
| `benchmark_id` | stable ID |
| `source_name` | source |
| `source_artifacts[]` | raw artifacts |
| `source_hashes[]` | sha256 for each raw artifact |
| `output_artifact` | generated benchmark data path |
| `output_hash` | sha256 for generated output |
| `date_min` / `date_max` | coverage range |
| `row_count` | output rows |
| `calendar_id` | frozen calendar |
| `required_dates_count` | dates required by formal labels |
| `covered_dates_count` | dates covered by benchmark |
| `missing_dates[]` | exact missing dates |
| `duplicate_dates[]` | exact duplicated dates; must be empty |
| `coverage_rate` | covered / required |
| `availability_status` | complete / partial / unavailable |
| `notes` | caveats |

Hard rule:

- Missing benchmark dates must produce `benchmark_unavailable` for affected label/window.
- Do not forward-fill, zero-fill, use another index, or silently interpolate benchmark returns.

## 2. Price / Adjusted Price 数据源盘点

### 2.1 当前价格缓存路径

Primary observed historical price cache:

- `stock-screener/data/research_backfill/cache/price_kline/*.json`

Observed cache summary:

| Item | Value |
| --- | ---: |
| files | 1571 |
| rows | 84500 |
| date range | 2023-11-20 to 2024-04-10 |
| row source coverage | 78867 / 84500 rows have `source=tx`; 5633 rows have no `source` field |

Other price-like current artifacts:

- `stock-screener/data/scan_result.json`
- `stock-screener/data/stale_outputs/scan_result_previous_*.json`
- `stock-analyzer/data/daily_snapshots/*.json`
- `data/artifacts/analyzer/daily_snapshots/*.json`
- `data/history/daily_snapshots/*.json`

These current artifacts contain point-in-time signal or watchlist snapshots, not a frozen daily OHLCV price store.

### 2.2 每条 price row 有哪些字段

Sample row from `stock-screener/data/research_backfill/cache/price_kline/000001_20231118_20240105.json`:

```json
{
  "date": "2023-11-20",
  "open": 8.59,
  "close": 8.63,
  "high": 8.66,
  "low": 8.54,
  "volume": 639528.0,
  "amount": 650077370.01,
  "amplitude": 1.4,
  "change_pct": 0.47,
  "change": 0.04,
  "turnover": 0.33
}
```

Across all sampled cache rows:

| Field | Coverage |
| --- | ---: |
| `date` | 84500 / 84500 |
| `open` | 84500 / 84500 |
| `close` | 84500 / 84500 |
| `high` | 84500 / 84500 |
| `low` | 84500 / 84500 |
| `volume` | 84500 / 84500 |
| `amount` | 84500 / 84500 |
| `amplitude` | 84500 / 84500 |
| `change_pct` | 84500 / 84500 |
| `change` | 84500 / 84500 |
| `turnover` | 84500 / 84500 |
| `source` | 78867 / 84500 |

### 2.3 是否有 open / close / high / low / volume / amount

Yes for the research backfill price cache:

- `open`: yes
- `close`: yes
- `high`: yes
- `low`: yes
- `volume`: yes
- `amount`: yes

These fields are sufficient for raw OHLCV labels and a first conservative liquidity/partial-fill estimate.

They are not sufficient for:

- formal adjusted returns,
- exact suspend status,
- exact limit up/down order block status,
- formal failed order outcomes,
- formal partial fill outcomes.

### 2.4 是否能判断复权

No.

Observed:

- No `adj_factor`.
- No `qfq`.
- No `hfq`.
- No `adjustment_policy`.
- No split/dividend/corporate-action provenance.
- Sprint 0 price audit notes the Sina K-line call used `ma=no`; this does not prove adjusted or unadjusted policy sufficiently for formal labels.
- Sprint 1 labels set `price_adjustment_status=unknown` and include `adjustment_policy` in every `execution_data_missing` list.

Conclusion:

- Current returns must remain raw / adjustment-unknown.
- Any adjusted-return conclusion must remain blocked until P1-A freezes an adjusted price policy and data source.

### 2.5 P1-A 应该用 raw、forward-adjusted 还是 backward-adjusted

Recommended P1-A policy:

| Price type | P1-A role |
| --- | --- |
| raw | Keep for audit and replay diagnostics |
| forward-adjusted / 前复权 | Use as formal research return default if source and PIT are provable |
| backward-adjusted / 后复权 | Do not use for PIT formal labels unless future-information risk is explicitly proven absent |

Reason:

- Raw OHLCV is already present and useful, but corporate actions can distort forward returns.
- 前复权 is the best default for formal research return continuity.
- 后复权 can introduce future information and should stay diagnostic unless tightly controlled.

### 2.6 哪些收益仍必须 research-only

Until P1-A freezes adjusted price and execution data, the following remain research-only:

- all current `raw_return`;
- all current `net_return`;
- any return using `price_adjustment_status=unknown`;
- any label with `execution_data_missing`;
- any 2026 operational artifact without matured formal forward labels;
- any benchmark-relative result until benchmark coverage is complete.

Even after adjusted price is added, execution-realistic returns remain unavailable until suspend, limit, failed order, partial fill, and T+1 rules are explicit and covered.

## 3. Execution Data 数据源盘点

### 3.1 是否有停牌字段

No explicit machine-readable suspend field was found.

Observed:

- No `is_suspended`.
- No `suspend_status`.
- No `resume_date`.
- Sprint 1 labels carry `execution_data_missing` with `suspend_status` for all 11064 label rows.
- `formal_execution_eligible=false` on every label row.

Absence of a price row or zero volume is not sufficient to infer a formal suspend status.

### 3.2 是否有涨跌停字段

No explicit machine-readable limit up/down field was found.

Observed:

- No `limit_up_price`.
- No `limit_down_price`.
- No `open_at_limit_up`.
- No `open_at_limit_down`.
- No `close_at_limit_up`.
- No `close_at_limit_down`.
- Some AI/scan text fields mention `接近或已触及涨停` or `涨停退潮风险`, but these are risk notes, not execution flags.
- Sprint 1 labels carry `execution_data_missing` with `limit_up_down_status` for all 11064 label rows.

### 3.3 是否能推断 limit up/down

Only weakly, and not enough for formal execution.

Potential weak inference:

- With raw OHLCV and previous close, P1-A could approximate limit prices by board/ST rules.
- But current cache does not explicitly identify board type, ST status, exact limit regime, or exchange-specific rule changes.
- Text risk notes can help diagnostics but cannot serve as execution proof.

P1-A should not treat inferred limit status as formal unless it adds:

- limit price calculation policy;
- board/ST classification source;
- validation against known limit prices where possible;
- explicit confidence/status field such as `limit_status=estimated` vs `complete`.

### 3.4 是否有 failed order / partial fill 数据

No.

Observed:

- No order ledger.
- No `order_status`.
- No `failed_order`.
- No `fill_qty_pct`.
- No `partial_fill`.
- Sprint 1 labels carry `failed_order` and `partial_fill` in `execution_data_missing` for all 11064 label rows.

P1-A can derive research order outcomes from price/execution flags, but those would be simulated outcomes, not broker fills.

### 3.5 T+1 当前如何保守处理

Current conservative handling:

- `data/config/quant-research.json` sets `rebalance_rule = daily_after_signal_with_t_plus_1_execution`.
- Sprint 1 labels use `next_open` as primary and `next_close` as comparison.
- Label generation steps through observed symbol price rows, not an official frozen exchange calendar.
- Intraday/midday rows are not formal forward-label eligible in Sprint 1/2.

Remaining gap:

- There is no canonical T+1 order ledger.
- There is no explicit rule for exit delay after suspend/limit-down.
- There is no lot size or partial fill handling.

### 3.6 成本配置在哪里

Cost configuration exists in:

- `data/config/quant-research.json`

Current fields:

```json
{
  "transaction_cost": {
    "currency": "CNY",
    "buy_commission_bps": 2.5,
    "sell_commission_bps": 2.5,
    "minimum_commission_cny": 5.0,
    "stamp_tax_bps": 5.0,
    "slippage_bps": 5.0,
    "impact_cost": {
      "enabled": false,
      "placeholder_bps": 0.0
    }
  }
}
```

Sprint 1 labels currently use `cost_bps=20.0` and flag `minimum_commission_notional_unavailable`.

P1-A should preserve explicit cost decomposition and add notional-aware minimum commission only when position notional is available.

## 4. P1-A 实施拆分

### Card 1: Benchmark manifest / benchmark return labels

| Item | Plan |
| --- | --- |
| 修改路径 | `packages/quant/*` only in P1-A implementation; `data/quant/benchmarks/*`; `data/quant/reports/benchmark_freeze_audit_latest.md`; tests under `tests/` |
| 输入数据 | external or newly fetched CSI500/HS300 daily series; current `data/quant/labels/forward_return_labels.jsonl`; optional `data/quant/panels/eligible_universe_snapshot.jsonl` for internal equal-weight |
| 输出产物 | `benchmark_daily.jsonl`, `benchmark_manifest.json`, optional `benchmark_returns.jsonl`, benchmark freeze audit |
| 验收标准 | CSI500 coverage 100% for formal label windows before primary excess return; HS300 missing windows explicit unavailable; source/output hashes recorded; missing/duplicate dates listed; no silent fill |
| 风险 | No current benchmark price source in repo; external data source/revision must be chosen; eligible equal-weight may be incomplete because universe is source-observed |
| 是否影响生产链路 | No; report/label data only |

### Card 2: Adjusted price policy

| Item | Plan |
| --- | --- |
| 修改路径 | `packages/quant/*` in P1-A implementation; `data/quant/prices/*`; `data/quant/reports/price_adjustment_audit_latest.md`; tests under `tests/` |
| 输入数据 | `stock-screener/data/research_backfill/cache/price_kline/*.json`; chosen adjusted price source with `adj_factor` / qfq policy |
| 输出产物 | frozen security price store with raw + adjusted OHLC; price manifest; adjustment audit |
| 验收标准 | formal rows have `adjustment_policy` 100%; entry/exit adjusted prices 100%; raw vs adjusted diff audit; PIT availability documented |
| 风险 | Existing cache has raw-looking OHLCV but no adjustment factor; qfq source may introduce future-information risk if not timestamped |
| 是否影响生产链路 | No; research labels only |

### Card 3: Execution flags

| Item | Plan |
| --- | --- |
| 修改路径 | `packages/quant/*` in P1-A implementation; `data/quant/execution/*`; `data/quant/reports/execution_data_hardening_audit_latest.md`; tests under `tests/` |
| 输入数据 | frozen raw/adjusted OHLCV, volume/amount, board/ST metadata if available, suspend/limit source if selected |
| 输出产物 | `security_trading_status.jsonl`, `limit_status.jsonl`, `research_order_outcomes.jsonl`, execution coverage audit |
| 验收标准 | suspend and limit status covered for formal entry/exit dates; failed/blocked order has reason; partial fill complete or explicit unavailable; no missing execution field silently treated as filled |
| 风险 | No current suspend/limit/order source; inferred limit status requires board/ST rules and may remain estimated |
| 是否影响生产链路 | No; research execution simulation only |

### Card 4: Forward labels upgrade

| Item | Plan |
| --- | --- |
| 修改路径 | `packages/quant/*` in P1-A implementation; `data/quant/labels/*`; `data/quant/reports/formal_label_readiness_latest.md`; tests under `tests/` |
| 输入数据 | existing panel, frozen prices, benchmark returns, execution flags, config |
| 输出产物 | upgraded labels with adjusted return, benchmark return, excess return status, execution flags, refined label status |
| 验收标准 | benchmark complete before `excess_return`; benchmark incomplete stays unavailable; formal labels trace panel/source/price/benchmark/execution revisions; 2026 labels admitted only after window maturity and hardening pass |
| 风险 | Mixing old `available_research_only` with new `formal_label_ready`; accidental inclusion of 2026 coverage-only rows |
| 是否影响生产链路 | No; label store only |

### Card 5: Rerun Sprint 2 reports

| Item | Plan |
| --- | --- |
| 修改路径 | `packages/quant/*` in P1-A implementation; regenerate `data/quant/reports/factor_evaluation_latest.md`, `portfolio_backtest_latest.md`, `quant_health_latest.md`, `quant_health_latest.json` |
| 输入数据 | upgraded labels, benchmark manifests, price/execution manifests |
| 输出产物 | refreshed Sprint 2 reports with benchmark/execution availability, still report-only |
| 验收标准 | `production_impact=none`; no production sorting; no A/B/C replacement; no page/Prism Edge/ML; excess return only where benchmark complete; `<30` buckets remain `insufficient_sample`; execution-realistic claims still forbidden unless every required execution field passes |
| 风险 | Report wording may be misread as production-ready; status should avoid ambiguous `ready` language |
| 是否影响生产链路 | No; reports only |

### Card 6: Tests

| Item | Plan |
| --- | --- |
| 修改路径 | `tests/test_quant_p1a_*.py` or equivalent; no production tests removed |
| 输入数据 | frozen benchmark/price/execution sample fixtures and generated artifacts |
| 输出产物 | tests for benchmark coverage, adjusted price policy, execution flags, label status, report guardrails |
| 验收标准 | tests prove no silent benchmark fill; no unknown adjustment in formal labels; no missing suspend/limit in execution-realistic set; 2026 coverage-only excluded until matured; all P0/Sprint 2 guardrails still pass |
| 风险 | Tests may overfit generated sample artifacts; need small fixtures plus current artifact checks |
| 是否影响生产链路 | No |

## 5. P1-A 第一张推荐开发卡

Recommended first card: Card 1, Benchmark manifest / benchmark return labels.

Reason:

1. Sprint 2 cannot compute or claim excess return because every label has `benchmark_status=benchmark_unavailable`.
2. Benchmark freezing is an upstream dependency for label upgrade, factor excess-return reporting, portfolio excess-return reporting, and quant health availability.
3. The repo currently has no benchmark price store, no benchmark manifest, and no benchmark coverage audit. This is the cleanest first gap to close without touching production.
4. Benchmark work has limited coupling to execution simulation. It can be implemented and accepted independently before adjusted price and execution flags.
5. It forces P1-A to establish source/hash/revision discipline early, which the later price and execution cards should reuse.

First-card guardrails:

- Do not generate production signals.
- Do not alter existing panel rows.
- Do not modify production sorting.
- Do not backfill missing benchmark dates silently.
- Do not compute excess return unless benchmark coverage is complete for that label/window.

## 6. Summary Decision

P1-A can proceed as data hardening only, but current repository state shows:

- benchmark source is absent;
- raw OHLCV price cache exists for 2024 research backfill;
- adjusted price policy is absent;
- suspend/limit/order/fill data is absent;
- equal-weight internal benchmark is possible only as source-observed research-only unless universe composition is frozen;
- current 2026 artifacts remain coverage-only until forward windows mature and data hardening passes.

Do not rerun Sprint 2 with upgraded claims until benchmark, adjusted price, execution flags, and label readiness gates are explicitly passed.
