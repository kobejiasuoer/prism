# Prism Data Freshness And Source Authority Plan

Date: 2026-05-11
Status: implemented as source-authority metadata and readiness gates

## Goal

Prism should not treat all fresh-looking data as equally trustworthy. Each dataset needs an explicit lane, authority provider, fallback rule, and decision scope so the system can distinguish:

- Fast live data that is useful during the trading session.
- Authoritative daily data that can support formal research labels and benchmark calculations.
- Execution constraint data that can support realistic execution hardening.
- Display-only reference data that must never silently become a live or formal decision input.

## Source Authority Matrix

| Dataset | Lane | Current primary | Target authority | Scope |
| --- | --- | --- | --- | --- |
| `quotes.snapshot` | live | `sina` | `sina` | `live_small` |
| `quotes.batch` | live | `eastmoney` | `eastmoney` | `live_small` |
| `bars.daily` | authoritative daily | `sina` | `tushare` | `live_small`, not formal-ready |
| `capital_flow.daily` | live | `eastmoney` | `eastmoney` | `live_small` |
| `capital_flow.batch` | live | `eastmoney` | `eastmoney` | `live_small` |
| `announcements.latest` | disclosure | `eastmoney` | official exchange / CNInfo | display only |
| `trade_calendar` | authoritative daily | `tushare` | `tushare` | formal candidate |
| `benchmark.index_daily` | authoritative daily | `tushare` | `tushare` | formal candidate |
| `adjustment.factor` | authoritative daily | `tushare` | `tushare` | formal candidate |
| `price_limit.daily` | execution | `tushare` | `tushare` | formal candidate |
| `execution.flags` | execution | `ricequant` | `ricequant` | formal candidate |

## Gate Semantics

- `live_small_allowed` controls whether the current live workflow can use the dataset.
- `decision_scope=display_only` means the dataset may be shown but must not drive live or formal decisions.
- `source_authority_ready=false` means the dataset is fresh enough for its current live/display purpose but has not met the configured authority target.
- `formal_decision_allowed=false` means the dataset must not be used for formal labels, formal excess return, formal adjusted return, or execution-realistic backtests.
- `authority_flags` explain why a source is not fully authoritative, for example `fallback_display_only`, `non_primary_fallback`, or `target_authority_not_in_use:tushare`.

## Current Implementation

The source matrix lives in `packages/prism_data/manifest.py` as `DATASET_REGISTRY`.

Provider manifests now include:

- `source_lane`
- `decision_scope`
- `authority_provider`
- `target_authority_provider`
- `audit_providers`
- `source_authority_ready`
- `formal_decision_allowed`
- `authority_flags`

Pipeline manifests propagate upstream authority risks so a downstream report cannot hide fallback or non-authoritative inputs.

The control panel readiness payload now exposes a separate formal gate:

- `formal_ready`
- `formal_blockers`

This formal gate is intentionally separate from `readiness_mode`. `live_ready` can remain true for the current operator workflow while `formal_ready=false` accurately reports that formal research outputs are not yet authorized.

## Next Controlled Change

The next implementation card should add real provider adapters behind the existing gateway, in this order:

1. Tushare non-secret adapter skeleton with token loaded only from environment or local secret storage.
2. Tushare field smoke tests for calendar, benchmark index daily, adjustment factor, and price limit datasets.
3. RiceQuant / JoinQuant execution adapter design if execution-realistic backtests become a near-term goal.
4. Official disclosure source adapter for CNInfo / exchange announcement feeds.

Raw vendor responses should remain outside the repository. Only redacted manifests, coverage reports, and non-reversible audit summaries may enter git.
