# Prism Free-Source FS-4B Repeatable Live Smoke Runner Result

Date: 2026-05-01
Scope: repeatable repo-external free-source live smoke runner
Status: completed

## 0. Boundary

FS-4B added a repeatable smoke runner for the BaoStock + AKShare free-source route. The runner is **dry-run / metadata-only by default** and does not call providers unless `--live` is explicitly passed.

This implementation did not call BaoStock or AKShare during validation, did not install dependencies, did not modify dependency files, lockfiles, or the main project venv, did not write `data/quant`, and did not read repo-external raw archive content.

BaoStock and AKShare remain research-only free-source candidates. Free callable access does not imply redistribution rights.

## 1. Files

FS-4B added:

- `packages/quant/free_sources/live_smoke_runner.py`
- `tests/test_quant_free_source_live_smoke_runner.py`
- `docs/quant-upgrade-free-source-fs4b-repeatable-live-smoke-result-2026-05-01.md`

No existing `free_sources` files were modified for exports.

## 2. Runner Behavior

`live_smoke_runner.py` provides:

- `run_smoke(live=False, ...)`: default dry-run metadata mode; no provider import, no network, no scratch writes.
- `run_smoke(live=True, ...)`: explicit live mode; dynamically loads BaoStock / AKShare and writes raw vendor payloads only under the approved repo-external scratch root.
- `render_smoke_markdown(...)`: repo-safe Markdown rendering that reuses `report_generator.generate_redacted_report(...)` and redaction checks.
- `assert_repo_external_scratch(...)`: blocks repo-local or unapproved scratch paths.
- CLI entrypoint: `python -m quant.free_sources.live_smoke_runner`, with live calls gated by `--live`.

Approved live scratch root:

```text
~/.prism-private/free-data-poc/
```

The runner does not write repo reports automatically. It returns/prints repo-safe Markdown containing endpoint-level metadata only:

- provider
- endpoint
- status
- row_count
- field_list
- non_null_summary
- response hash
- retrieved_at
- error_summary
- opaque raw_archive_pointer
- research-only notes
- blocker notes

## 3. Endpoint Scope

FS-4B keeps the same tiny sample endpoint scope as FS-3:

| Provider | Layer | Endpoint |
| --- | --- | --- |
| BaoStock | calendar | `query_trade_dates` |
| BaoStock | stock_basic | `query_stock_basic` |
| BaoStock | raw_daily | `query_history_k_data_plus_raw_daily` |
| BaoStock | qfq_candidate | `query_history_k_data_plus_qfq` |
| BaoStock | index_daily | `query_history_k_data_plus_index_daily` |
| BaoStock | tradestatus_isst | `query_history_k_data_plus_tradestatus_isst` |
| AKShare | raw_daily | `stock_zh_a_hist_raw_daily` |
| AKShare | qfq_candidate | `stock_zh_a_hist_qfq` |
| AKShare | index_daily | `stock_zh_index_hist_csindex` |
| AKShare | suspend_event | `stock_tfp_em` |

Default sample window remains `2024-01-02..2024-01-10`, with the same three stock samples and HS300 / CSI500 index samples represented only as summarized metadata in repo-safe output.

## 4. Safety Rules

FS-4B preserves these guardrails:

- No live provider call without explicit `--live`.
- No top-level BaoStock / AKShare imports.
- No network library imports.
- Raw provider payloads can only be written under the approved repo-external scratch root in live mode.
- Repo-safe Markdown must pass redaction/report-generator checks.
- Unsafe row-level keys, raw payload keys, unsafe pointers, local paths, URLs, token/cookie/session/authorization keys, and formal-ready claims are rejected.
- `data/quant` remains untouched.

## 5. Tests

Synthetic-only tests cover:

- default dry-run does not load providers
- explicit `live=True` is required for live path activation
- CLI defaults to dry-run
- scratch root must be approved and repo-external
- renderer rejects raw rows, raw payloads, secret-like keys, and unsafe pointers
- runner has no top-level provider, network, production, page, or ML imports
- dry-run does not write `data/quant`

Validation command:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages .venv/bin/python -m pytest \
  tests/test_quant_free_source_manifest.py \
  tests/test_quant_free_source_mapping.py \
  tests/test_quant_free_source_guardrails.py \
  tests/test_quant_free_source_report_generator.py \
  tests/test_quant_free_source_live_smoke_runner.py \
  -q -p no:cacheprovider
```

Result:

```text
85 passed in 0.07s
```

## 6. Still Blocked

FS-4B does not change the blocked status of:

- formal labels
- formal excess return
- formal adjusted return
- execution-realistic backtest
- limit up/down price
- failed order
- partial fill
- production sorting
- A/B/C
- page work
- Prism Edge
- Expected 5D
- ML

QFQ, benchmark, `tradestatus` / `isST`, and suspend-event metadata remain candidate / research-only / partial evidence only.

## 7. Next Gate

FS-4B does not authorize production integration. Any future FS-5 work must remain separately planned and reviewed, and any live execution must continue to be repo-external with raw vendor data excluded from the repo.

