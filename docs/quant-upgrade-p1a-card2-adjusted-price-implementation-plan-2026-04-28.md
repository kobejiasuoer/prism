# Prism 量化升级 P1-A Card 2 Adjusted Price Implementation Plan

Date: 2026-04-28
Scope: P1-A Card 2 planning only
Candidate card: Adjusted price policy / price adjustment policy

Source:
- `docs/quant-upgrade-p1a-source-inventory-and-implementation-plan-2026-04-28.md`
- `docs/quant-upgrade-p1a-hardening-acceptance-checklist-2026-04-28.md`
- `docs/quant-upgrade-p1a-decision-matrix-2026-04-28.md`
- `docs/quant-upgrade-p1-data-hardening-plan-2026-04-28.md`
- current repository read-only inspection

Status: planning document only. This document does not implement Card 2, does not modify `packages/quant`, does not modify `data/quant/benchmarks/*`, does not modify `data/quant/reports/*`, and does not generate new labels.

## 0. Boundary

P1-A Card 2 should define and freeze the price adjustment policy surface before any formal adjusted-return label is allowed.

This card must remain data-hardening and report-only. It must not affect production sorting, A/B/C, pages, Prism Edge, Expected 5D frontend display, or ML.

Strict implementation guardrails for the future Card 2:

- Do not fetch external data unless a later decision explicitly approves a source.
- Do not infer adjusted prices from raw OHLCV.
- Do not call raw returns formal adjusted returns.
- Do not move labels to `formal_label_ready` while `adjustment_policy` is unknown.
- Do not claim execution-realistic returns because suspend, limit, failed order, and partial fill data are still separate unresolved gaps.

## 1. 当前价格数据源复核

### 1.1 现有价格文件路径

Primary observed historical price cache:

- `stock-screener/data/research_backfill/cache/price_kline/*.json`

Current read-only inspection:

| Item | Value |
| --- | ---: |
| price files | 1571 |
| non-empty files | 1571 |
| total rows | 84500 |
| row date range | 2023-11-20 to 2024-04-10 |
| rows with `source=tx` | 78867 |
| rows with missing `source` | 5633 |

Other price-like artifacts exist, but they are not frozen daily price stores:

- `stock-screener/data/scan_result.json`
- `stock-screener/data/stale_outputs/scan_result_previous_*.json`
- `stock-analyzer/data/daily_snapshots/*.json`
- `data/artifacts/analyzer/daily_snapshots/*.json`
- `data/history/daily_snapshots/*.json`

Those files are point-in-time signal/watchlist snapshots or operational snapshots, not an adjusted daily OHLCV source.

### 1.2 字段结构

Sample row shape from `stock-screener/data/research_backfill/cache/price_kline/000001_20231118_20240105.json`:

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

Observed non-null field coverage across the price cache:

| Field | Rows |
| --- | ---: |
| `date` | 84500 |
| `open` | 84500 |
| `high` | 84500 |
| `low` | 84500 |
| `close` | 84500 |
| `volume` | 84500 |
| `amount` | 84500 |
| `amplitude` | 84500 |
| `change_pct` | 84500 |
| `change` | 84500 |
| `turnover` | 84500 |
| `source` | 78867 |

The security code is not inside each price row; it is derived from the file name prefix such as `000001_20231118_20240105.json`.

### 1.3 open/high/low/close/volume/amount 是否可用

The existing research backfill price cache has complete raw OHLCV and amount coverage:

- `open`: available.
- `high`: available.
- `low`: available.
- `close`: available.
- `volume`: available.
- `amount`: available.

This is enough for raw price audit and raw forward-return replay. It is not enough for formal adjusted return, suspend/limit execution realism, or partial-fill proof.

### 1.4 是否有复权信息

No machine-readable adjustment information was found in the current price cache.

Missing fields:

- `adj_factor`
- `qfq`
- `hfq`
- `adjustment_policy`
- `open_adj`
- `close_adj`
- `prev_close_adj`
- corporate action provenance
- PIT available timestamp for adjustment factors

Current forward labels confirm the gap:

| Label-side item | Value |
| --- | ---: |
| label rows | 11064 |
| `price_adjustment_status=unknown` | 11064 |
| rows with `adjustment_policy` in `execution_data_missing` | 11064 |
| `available_research_only` labels | 10818 |
| unavailable labels | 246 |

Conclusion:

- Current price rows should be treated as raw / adjustment-unknown.
- Existing raw and net returns remain research-only.
- Card 2 must not silently promote current labels to formal adjusted labels.

### 1.5 哪些日期覆盖可用

Price cache coverage:

- row date range: 2023-11-20 to 2024-04-10.

Existing forward label usage:

- signal trade dates: 2024-01-02 to 2024-03-29.
- entry trade dates with prices: 2024-01-03 to 2024-04-01.
- exit trade dates with prices: 2024-01-03 to 2024-04-10.

The cache covers the current Sprint 1/Sprint 2 2024 research backfill label windows for raw price replay, with 246 label rows still unavailable due to forward price gaps.

Current 2026 artifacts are still coverage-only for panel purposes. They should not enter formal forward labels under Card 2 unless forward windows mature and price, benchmark, PIT, and execution hardening all pass.

### 1.6 哪些数据只能 raw

The following must remain raw / research-only under current repository state:

- all existing `raw_return`;
- all existing `net_return`, because it is based on adjustment-unknown raw price;
- all labels with `price_adjustment_status=unknown`;
- any derived return from `stock-screener/data/research_backfill/cache/price_kline/*.json` unless Card 2 explicitly freezes it as `raw`;
- any backtest result that depends on the current labels;
- any 2026 current artifact until future windows mature and label hardening passes.

## 2. Adjusted Price 策略选择

### 2.1 策略比较

| Price policy | 适合 forward label | 适合回测 | 当前数据是否支持 | P1-A 保守标记 |
| --- | --- | --- | --- | --- |
| raw price | 只适合 audit / diagnostic label，不适合作 formal adjusted label | 可做 research-only raw replay；不能称 execution-realistic | Supported as current cache fields `open/high/low/close/volume/amount` | `adjustment_policy=raw_unadjusted_or_unknown` only if source policy is frozen; otherwise `adjustment_policy=unknown` |
| forward-adjusted / 前复权 | 最适合 formal research forward label 的主收益口径，前提是 source/hash/PIT 可证明 | 适合作 report-only factor/backtest 的主研究收益口径，仍不代表生产可执行 | Not supported by current repo; no `adj_factor` or qfq fields | `adjusted_price_unavailable`; labels remain `research_only_adjustment_missing` or `available_research_only` |
| backward-adjusted / 后复权 | 不适合 PIT formal labels，容易引入未来信息 | 可用于长周期诊断图表，但不进入 P1-A formal label/backtest | Not supported by current repo | `excluded_from_formal_labels` |

### 2.2 哪个适合 forward label

Recommended formal target: forward-adjusted / 前复权.

Reason:

- It reduces corporate-action jumps in short forward windows.
- It better supports cross-sectional factor comparison.
- It is the recommendation in the P1-A checklist and decision matrix.

Blocking condition:

- The current repository does not contain forward-adjusted OHLC, adjustment factors, or PIT availability proof.
- Therefore Card 2 can define the desired policy, but cannot produce formal adjusted returns unless an approved adjusted source is added later.

### 2.3 哪个适合回测

Recommended research backtest target:

- Use forward-adjusted return after adjusted source is frozen.
- Keep raw return as audit comparator.
- Keep all outputs report-only.

Current-state fallback:

- Continue to treat existing backtest returns as `research_only_simulation`.
- Keep `adjustment_policy_unknown` in research-only flags until adjusted price source is available.
- Do not calculate or claim execution-realistic returns from raw-only data.

### 2.4 当前数据是否支持

Current data supports:

- raw OHLCV replay;
- raw next-open / next-close entry price lookup;
- raw close exit price lookup;
- source hash tracing through label `price_source_artifact` and `price_source_hash` where available;
- volume/amount diagnostics for later execution work.

Current data does not support:

- adjusted OHLC;
- `adj_factor`;
- formal adjusted return;
- proof that a qfq/hfq value was PIT-available on the signal date;
- corporate-action audit.

### 2.5 如果不支持，P1-A 如何保守标记

Card 2 should preserve or introduce explicit statuses:

| Status field | Recommended values |
| --- | --- |
| `price_adjustment_status` | `unknown`, `raw_only`, `adjusted_unavailable`, `adjusted_available` |
| `adjustment_policy` | `unknown`, `raw`, `qfq`, `hfq`, `vendor_adjusted` |
| `adjustment_source_status` | `not_found_in_repo`, `source_unavailable`, `source_available_unverified`, `source_frozen` |
| `adjusted_return_status` | `unavailable_adjustment_missing`, `research_only_raw_fallback`, `available_report_only`, `formal_ready` |
| `label_status` | keep `available_research_only`; only future complete rows may become `formal_label_ready` |

Hard rule:

- If `adjustment_policy` is `unknown`, the row cannot produce formal adjusted return.
- If adjusted price is missing at entry or exit, `adjusted_return` must be unavailable.
- If PIT availability is not proven, the row must remain research-only even if adjusted values exist.

## 3. Card 2 推荐实现范围

Recommended Card 2 implementation should be conservative:

1. Do not fetch external data.
2. Do not infer adjustment factors from raw prices.
3. Freeze the policy surface first:
   - formal target policy: `qfq` / forward-adjusted.
   - current available policy: raw / adjustment unknown.
   - hfq excluded from formal labels.
4. Build a price adjustment manifest/audit from current repo data.
5. Write explicit adjustment status for every label row in a future label upgrade or sidecar overlay.
6. Keep current raw/net labels research-only when adjustment cannot be proven.
7. Do not compute adjusted return unless adjusted entry and exit prices are present and traceable.
8. Do not rerun Sprint 2 factor/backtest/health with upgraded claims until adjusted policy and source pass acceptance.

Recommended first Card 2 deliverable should not try to solve external data acquisition. It should make the current limitation impossible to miss:

- `raw_price_available=true`
- `adjusted_price_available=false`
- `adjustment_policy=unknown`
- `formal_adjusted_return_eligible=false`
- `research_only_reason=adjustment_policy_missing`

## 4. 预期修改路径

This section describes possible future implementation paths only. No code is written by this planning document.

### 4.1 Possible `packages/quant` paths

Potential new files:

- `packages/quant/price_adjustment_policy.py`
- `packages/quant/build_price_adjustment_manifest.py`

Potential modified files:

- `packages/quant/paths.py`
  - Add `PRICES_ROOT` or `PRICE_MANIFESTS_ROOT`.
- `packages/quant/schemas.py`
  - Add typed contracts for raw/adjusted price rows and adjustment manifest.
- `packages/quant/build_research_panel.py`
  - Only if Card 2 is explicitly allowed to regenerate labels or add label adjustment statuses.
- `packages/quant/research_io.py`
  - Only if shared JSON/JSONL helpers need path constants.

Implementation caution:

- Avoid changing `evaluate_factors.py`, `run_portfolio_backtest.py`, and `report_quant_health.py` in Card 2 unless the card scope explicitly includes a report-only rerun later.

### 4.2 Possible `data/quant` artifacts

Potential future artifacts:

- `data/quant/prices/price_adjustment_manifest.json`
- `data/quant/prices/raw_price_inventory.jsonl`
- `data/quant/prices/adjustment_status_by_label.jsonl`
- `data/quant/prices/price_source_hashes.json`

Potential future reports:

- `data/quant/reports/price_adjustment_audit_latest.md`

Potential future label handling options:

| Option | Output | Pros | Cons |
| --- | --- | --- | --- |
| Sidecar adjustment overlay | `adjustment_status_by_label.jsonl` | Does not rewrite labels; safer for Card 2 acceptance | Downstream code must join overlay |
| Regenerated labels | `forward_return_labels.jsonl` with explicit adjustment fields | Simpler downstream contract | Higher risk; must be explicitly approved and tested |
| New revisioned labels | `forward_return_labels_p1a_card2.jsonl` | Traceable and avoids overwriting current labels | Requires revision pointer/manifest |

Given the current strict boundary, sidecar overlay or revisioned labels are safer than overwriting labels.

### 4.3 Tests to add in future Card 2

Potential tests:

- `tests/test_quant_p1a_adjusted_price.py`

Minimum test cases:

- Current raw price cache is detected and has OHLCV fields.
- Missing `adj_factor` causes `adjusted_price_available=false`.
- Missing `adjustment_policy` prevents `formal_adjusted_return_eligible`.
- Raw-only labels remain research-only.
- No `adjusted_return` is emitted when adjusted prices are unavailable.
- Backward-adjusted / hfq is excluded from formal labels.
- 2026 current artifacts remain excluded from formal label evaluation.
- Production sorting, A/B/C, pages, Prism Edge, and ML are untouched.

## 5. 验收标准

Card 2 should pass only if all of the following are true:

| Acceptance item | Required result |
| --- | --- |
| `adjustment_policy` 明确 | Policy states formal target is forward-adjusted/qfq, current repo status is unknown/raw-only |
| raw/adjusted 状态可追踪 | Every price/label row can trace source artifact, source hash, and adjustment status |
| 不明确复权时不得声称 formal adjusted return | Unknown policy rows remain research-only or unavailable |
| adjusted prices absent | `adjusted_return` unavailable; no silent raw fallback into formal adjusted fields |
| PIT | Any future adjusted source must record available timestamp or PIT proof |
| labels | Existing labels are not upgraded to formal without adjusted entry/exit price coverage |
| reports | Any future report says report-only; no production-ready wording |
| production | No production sorting impact |
| A/B/C | No A/B/C replacement |
| product scope | No page, Prism Edge, Expected 5D frontend, or ML |

Explicit failure cases:

- Raw price is labeled as adjusted without source proof.
- Missing adjustment policy is silently ignored.
- `adjusted_return` is calculated from `raw_return`.
- Any label becomes `formal_label_ready` while `adjustment_policy=unknown`.
- Any Sprint 2 report is rerun with stronger claims before price adjustment acceptance passes.

## 6. 风险和待拍板问题

### 6.1 raw price 是否可作为 P1-A 默认

Decision needed.

Recommended answer:

- Raw price may be the default audit price.
- Raw price should not be the default formal research return.
- If Card 2 proceeds without external adjusted data, the correct outcome is a frozen raw/unknown policy with research-only labels, not formal adjusted labels.

### 6.2 是否需要引入外部复权数据

Decision needed after Card 2 planning.

Recommended answer:

- Yes, if the project wants formal adjusted returns.
- The external source must provide adjusted OHLC or `adj_factor`, source artifacts, source hash, coverage audit, and PIT availability proof.
- Without that, Card 2 can only document and freeze the absence of adjusted data.

### 6.3 是否允许后续重新生成 labels

Decision needed.

Safer sequence:

1. Build price adjustment manifest and audit.
2. Build sidecar `adjustment_status_by_label.jsonl`.
3. Independently accept Card 2.
4. Only then approve a revisioned label regeneration if needed.

Do not overwrite current labels without an explicit data revision and acceptance checklist.

### 6.4 是否仍然保持 report-only

Recommended answer: yes.

Even if adjusted prices are introduced later, P1-A remains report-only because benchmark, suspend, limit, failed order, partial fill, and production integration are separate gates.

### 6.5 Open questions for the Card 2 kickoff

- Should Card 2 freeze only current raw/unknown policy, or is an approved adjusted data source available?
- If an adjusted source is introduced later, what source is acceptable and how is its PIT timestamp proven?
- Should the first implementation write a sidecar overlay or a new revisioned labels file?
- What is the exact status vocabulary: `research_only_adjustment_missing`, `adjusted_unavailable`, or both?
- Should `net_return` remain raw-cost net return, or should a future `net_adjusted_return` be added separately?
- Is `fail_on_missing_adjustment_policy=true` in `data/config/quant-research.json` sufficient as the hard gate, or should Card 2 add a dedicated manifest gate?

## 7. Recommended Card 2 Decision

Recommended first implementation scope:

- Freeze current state as `raw_available_adjustment_unknown`.
- Produce a price adjustment manifest and audit.
- Do not fetch external data.
- Do not infer qfq/hfq.
- Do not regenerate labels until sidecar/manifest acceptance passes.
- Keep all current returns research-only.

Recommended acceptance conclusion if implemented this way:

- `有条件通过`: Card 2 would make adjustment status explicit and traceable, but formal adjusted return remains blocked until a real adjusted price source with PIT proof is added.
