# Prism Quant Tushare Pro POC Runbook

Date: 2026-04-29
Scope: non-production Tushare Pro data-source POC only
Status: waiting for Tushare Pro account/token readiness

This runbook is operational guidance only. It does not implement code, does not call Tushare APIs, does not install dependencies, does not write `data/quant`, and does not connect to any production path.

## 0. Boundary

The Tushare Pro POC is a non-production data-source validation step for P1-A data hardening.

It must not:

- modify `packages/quant`;
- write or overwrite `data/quant`;
- generate formal labels;
- generate formal excess return;
- generate execution-realistic backtests;
- alter production sorting;
- replace A/B/C;
- add pages;
- add Prism Edge;
- add Expected 5D frontend display;
- add ML.

The POC may only validate whether Tushare Pro can provide required fields, coverage, timestamps, and source traceability for future data hardening.

## 1. POC 前置条件

Before starting, confirm all items below.

| Item | Requirement |
| --- | --- |
| Tushare account | A valid Tushare Pro account exists and is controlled by the project owner. |
| Token | A valid token exists, but is not stored in code, docs, logs, git, notebooks, shell history, or shared screenshots. |
| Local env var | Token is injected via local environment variable such as `TUSHARE_TOKEN`; no hardcoded token. |
| Interface permissions | Account has permission for the target APIs being checked. |
| Points / cost | Required积分、调用额度、费用、频率限制已人工确认。 |
| Legal / license | Tushare data usage terms allow local research POC and derived availability summaries. |
| POC owner | One human owner is responsible for token handling and permission verification. |
| Network policy | Local network/API access is permitted for the POC environment. |

Minimum local environment assumptions:

- Python environment can import the chosen Tushare client only after an explicitly approved setup step.
- `TUSHARE_TOKEN` is available only in the active shell/session for the POC.
- The workspace has a clean place outside `data/quant` for temporary local-only scratch output if needed.

## 2. 本地安全要求

Token handling rules:

- Never write the token into code.
- Never write the token into this or any other document.
- Never print the token in terminal logs.
- Never commit the token to git.
- Never paste the token into issue trackers, chat, screenshots, reports, notebooks, or generated artifacts.
- Never store the token in `data/quant`, `docs`, `packages`, or test fixtures.

Raw response handling rules:

- Do not commit raw Tushare API responses.
- Do not write raw responses under `data/quant`.
- Do not store raw responses in git-tracked paths.
- Do not include full raw response samples in docs.
- If local scratch files are needed, keep them outside git-tracked data paths and delete them after summarization.

Logging rules:

- Logs may include endpoint names, request date ranges, field names, row counts, coverage rates, and response status.
- Logs must not include token, full raw records, account metadata, or paid-license details beyond high-level availability.

Git hygiene:

- Run `git status --short` before and after the POC.
- Confirm no raw response files, token files, notebooks, cache files, or temp files are staged or left in tracked paths.
- Only sanitized summary docs or field availability matrices may be committed later, if approved.

## 3. POC 执行步骤

### 3.1 环境检查

Checklist:

- Confirm `TUSHARE_TOKEN` is set in the local shell without printing its value.
- Confirm no token appears in `.env`, docs, source files, shell scripts, notebooks, or git diff.
- Confirm the POC operator understands that no writes to `data/quant` are allowed.
- Confirm the POC output path is a docs-only sanitized summary path, if output is approved.

Suggested verification outcomes to record in the summary:

- env var present: yes/no.
- token printed: no.
- git-tracked raw output present: no.
- POC mode: non-production.

### 3.2 接口权限检查

For each target interface:

- Confirm endpoint name.
- Confirm permission status.
- Confirm required积分 / frequency / rate limit.
- Confirm whether the endpoint returns the needed fields.
- Confirm whether historical coverage is available for the 2024 research backfill window and future 2026 windows.

Do not dump raw response rows into the report. Record only:

- endpoint name;
- permission status;
- requested date range;
- returned row count;
- field availability;
- missing fields;
- timestamp or source availability status;
- high-level error code if failed.

### 3.3 字段验证

For each interface, validate field existence rather than strategy output.

Required validation dimensions:

- field exists;
- field data type is stable enough for parser design;
- date coverage;
- symbol/index coverage;
- duplicate key behavior;
- missing value behavior;
- update timestamp or data availability timestamp;
- source revision or traceability metadata;
- whether PIT usage can be defended.

Field-level result statuses:

| Status | Meaning |
| --- | --- |
| `available` | Field exists and appears populated for the checked range. |
| `partially_available` | Field exists but has missing rows, limited dates, or permission limits. |
| `unavailable` | Field does not exist or endpoint is inaccessible. |
| `permission_blocked` | Endpoint or field requires permissions not currently granted. |
| `cost_blocked` | Endpoint exists but cost/points are not acceptable. |
| `unclear_license` | Usage authorization is unclear; do not proceed. |

### 3.4 Hash / timestamp 记录

For the POC, do not persist raw response bodies. Instead, record sanitized traceability:

- endpoint name;
- request parameter summary;
- request timestamp;
- response timestamp if provided;
- row count;
- field list;
- missing field list;
- response body hash only if the raw response is handled locally and then deleted;
- client/library version if available;
- operator and environment note if required by internal process.

If a hash is recorded:

- It must be a hash of the exact raw response observed during the POC.
- The raw response itself must not be committed.
- The summary should state that raw response was discarded after hashing.

### 3.5 摘要报告输出

Allowed output:

- sanitized POC summary document;
- field availability matrix;
- permission/cost matrix;
- endpoint coverage summary;
- risks and next-decision recommendations.

Not allowed:

- raw API response files;
- generated `data/quant` artifacts;
- generated labels;
- generated benchmark returns;
- generated execution flags;
- generated backtest reports;
- production config changes.

### 3.6 清理检查

Before ending the POC:

- Delete local raw response scratch files.
- Confirm token was not written to any file.
- Confirm no shell/script history with token is being committed.
- Run `git status --short`.
- Confirm only approved sanitized docs are present.
- Confirm no `data/quant` changes were made.
- Confirm no `packages/quant` changes were made unless a later coding card explicitly approves them.

## 4. POC 允许验证的接口类型

The POC may validate availability for these data categories.

| Interface type | Purpose | Required fields to inspect |
| --- | --- | --- |
| 交易日历 | Freeze official trading dates and open/closed status. | exchange, cal_date, is_open, pretrade_date or equivalent |
| 指数日线 | CSI500 / HS300 benchmark daily OHLC and returns. | index code, trade_date, open, close, high, low, pre_close, volume/amount if available |
| 复权因子 / 复权行情 | Support adjusted return policy. | ts_code, trade_date, adj_factor or qfq adjusted OHLC, source timestamp |
| 停复牌 | Execution availability and blocked orders. | ts_code, suspend_date, resume_date, suspend_reason/status |
| 涨跌停 | Limit up/down execution constraints. | ts_code, trade_date, up_limit, down_limit, open/close at-limit if available |
| 股票基础信息 | Board/ST/listing metadata for future limit-rule checks. | ts_code, symbol, name, market, exchange, list_date, delist_date, is_hs, list_status, ST/board info if available |

The POC should report whether each interface can support:

- source/hash/revision discipline;
- 2024 research backfill coverage;
- 2026 forward-label readiness once windows mature;
- PIT-safe usage or limitations;
- future label hardening fields.

## 5. POC 禁止事项

The POC must not:

- write `data/quant`;
- modify `packages/quant`;
- modify production configs;
- generate `forward_return_labels.jsonl`;
- generate `forward_return_labels_hardened.jsonl`;
- generate formal labels;
- generate formal excess return;
- generate adjusted returns as production-ready;
- generate execution-realistic backtests;
- rerun Sprint 2 reports;
- connect any result to production sorting;
- replace A/B/C;
- create pages;
- create Prism Edge behavior;
- expose Expected 5D frontend output;
- train or run ML models;
- treat internal benchmark as market benchmark;
- treat raw price as adjusted price;
- treat unavailable execution fields as available.

## 6. POC 完成后的允许产物

Allowed POC completion artifacts:

- a sanitized summary document under `docs/`;
- a field availability matrix under `docs/`;
- a permission/cost status table;
- a recommendation for whether to proceed to a coding card;
- a list of blocked endpoints or missing fields;
- a list of required human decisions.

Recommended summary sections:

1. POC date and operator.
2. Token handling confirmation.
3. Endpoints checked.
4. Permission/cost status.
5. Field availability matrix.
6. Coverage by date range.
7. PIT/source timestamp findings.
8. Security cleanup confirmation.
9. Recommendation: proceed / conditional proceed / stop.

The summary must not contain:

- token value;
- raw response payloads;
- full licensed dataset extracts;
- account-sensitive details;
- production-ready claims.

## 7. POC 失败处理

### 7.1 权限不足

If endpoint permission is missing:

- Stop checking that endpoint.
- Record `permission_blocked`.
- Record what permission appears required.
- Do not attempt workaround endpoints unless they are explicitly approved.
- Do not substitute another source silently.

### 7.2 字段不可得

If required fields are absent:

- Record `unavailable` or `partially_available`.
- Record exact missing fields.
- Do not infer missing fields for the POC.
- Do not mark the future data-hardening gate as passed.

### 7.3 成本不可接受

If required points/fees are too high or unclear:

- Stop the POC for that endpoint.
- Record `cost_blocked`.
- Ask for a human decision before further calls.
- Do not spend additional points to chase non-critical fields.

### 7.4 授权不清

If license or redistribution permission is unclear:

- Stop immediately.
- Record `unclear_license`.
- Do not persist raw response data.
- Do not proceed to coding or report generation based on that source.

### 7.5 API errors or unstable responses

If responses are unstable:

- Record endpoint, date range, status code/error text summary, and time.
- Do not retry aggressively.
- Do not change request semantics to force data without documenting it.
- Mark endpoint `unstable` or `needs_manual_review`.

## 8. Exit Criteria

The POC is complete only when:

- token handling was secure;
- no raw responses were committed;
- no `data/quant` artifacts were written;
- no `packages/quant` code was modified;
- endpoint availability and missing fields are summarized;
- costs/permissions are known or explicitly blocked;
- a human-readable recommendation is ready for the next coding card.

Possible final recommendations:

| Recommendation | Meaning |
| --- | --- |
| `proceed` | Required interfaces, fields, permissions, and costs are acceptable for a future non-production coding card. |
| `conditional_proceed` | Some fields are available, but permissions/cost/PIT/coverage gaps remain. |
| `stop` | Source is not usable due to permissions, cost, missing fields, or unclear authorization. |
