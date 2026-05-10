# Prism 数据入口统一实施状态

日期：2026-05-07  
状态：已完成一个可运行的端到端闭环，不再是骨架阶段

## 本次交付结论

Prism 当前已经把一条真实生产链路收口为：

`provider adapter -> DataGateway -> dataset repository + manifest -> pipeline sidecar manifest -> canonical loader -> readiness/today/refresh status -> guardrail`

这条闭环覆盖了当前控制台 live_small 依赖的四类核心制品：

1. `watchlist.snapshot`
2. `screening.batch`
3. `screening.confirmation`
4. `decision_brief.snapshot`

它们都开始带有 sidecar manifest，`/api/today`、`/api/readiness/live`、`/api/refresh/status?page=today` 统一从同一套 readiness 判断派生页面状态，并在 manifest 缺失、trade_date 不一致、freshness stale/expired、fallback 不允许 live_small 时 fail closed。

## 已完成的真实链路迁移

### 1. 原始 provider 访问统一进入 `packages/prism_data`

`packages/prism_data` 已包含：

- `gateway.py`
- `repositories.py`
- `manifest.py`
- `freshness.py`
- `service.py`
- `providers/common.py`
- `providers/sina.py`
- `providers/eastmoney.py`
- `providers/akshare.py`
- `providers/ths.py`

`DataGateway` 已不再只返回 provider 数据，而是：

- 调用 provider adapter
- 对每次尝试写 attempt manifest
- 对最终结果写 canonical dataset + manifest
- 计算 `freshness_status`
- 保留 provider provenance / fallback 信息

### 2. watchlist 链路

以下入口已迁移，不再直接访问 Sina / Eastmoney：

- `stock-analyzer/watchlist_registry.py`
- `apps/control-panel/watchlist_registry.py`
- `stock-analyzer/scripts/fetch.py`

当前 watchlist 生产链路：

- 实时行情：`DataGateway.fetch_quote()`
- K 线：`DataGateway.fetch_kline()`
- 资金流：`DataGateway.fetch_capital_flow()` / `fetch_capital_flow_batch()`
- 基本面：`DataGateway.fetch_fundamentals()` / `fetch_fundamentals_batch()`
- 公告：`DataGateway.fetch_announcements()`
- 新闻：`DataGateway.fetch_news()`
- 搜索建议：`DataGateway.search_stock()`
- 行业快照：`DataGateway.fetch_sector_snapshot()`

`stock-analyzer/data/daily_snapshots/YYYY-MM-DD.json` 现在会同时写：

- 业务 JSON
- `stock-analyzer/data/daily_snapshots/YYYY-MM-DD.manifest.json`

### 3. screener 链路

`packages/screener/scan.py` 已移除业务层直连：

- 不再自己 `urlopen(...)`
- 不再直接抓 THS HTML
- 不再直接请求 Eastmoney stock/get / ulist / fflow
- 不再直接 import `akshare`

当前 screener 生产链路改为：

- 股票池：`fetch_market_pool()` / `fetch_index_constituents()`
- 批量行情：`fetch_quotes_batch()`
- 批量资金流：`fetch_capital_flow_batch()`
- 单票资金流：`fetch_capital_flow()`，必要时显式 `provider_name="ths"` 走 adapter fallback
- 批量基本面：`fetch_fundamentals_batch()`
- 单票基本面：`fetch_fundamentals()`，必要时显式 `provider_name="ths"` 走 adapter fallback
- 公告：`fetch_announcements()`
- K 线：`fetch_kline()`

`packages/screener/scan.py` 现在会为：

- `packages/data/scan_result.json`
- `packages/data/history/*.json`

写出 `screening.scan_result` sidecar manifest。

### 4. downstream pipeline 链路

以下下游制品也开始写 pipeline sidecar manifest：

- `packages/data/ai_screening_result.json` -> `screening.batch`
- `packages/data/midday_verification_result.json` -> `screening.confirmation`
- `apps/data/command_brief/*.json` -> `decision_brief.snapshot`

每份 sidecar manifest 都会聚合 upstream manifests，并把 `live_small_allowed` 向下传播。

## manifest 结构与落盘位置

### 原始 dataset manifest

原始 provider 数据统一落在：

`data/prism_data/datasets/<dataset>/<trade_date>/<request_key>.json`

对应 manifest：

`data/prism_data/datasets/<dataset>/<trade_date>/<request_key>.manifest.json`

每次成功和失败都会有 manifest。字段至少包含：

- `dataset`
- `provider`
- `provider_role`
- `trade_date`
- `fetched_at`
- `asof`
- `ttl_seconds`
- `freshness_status`
- `fallback_used`
- `row_count`
- `payload_hash`
- `live_small_allowed`
- `quality_flags`

### pipeline sidecar manifest

业务制品旁边会生成 sibling sidecar：

- `*.manifest.json`

当前已接入的 sidecar：

- `stock-analyzer/data/daily_snapshots/YYYY-MM-DD.manifest.json`
- `packages/data/scan_result.manifest.json`
- `packages/data/ai_screening_result.manifest.json`
- `packages/data/midday_verification_result.manifest.json`
- `apps/data/command_brief/*.manifest.json`

## readiness 现在如何读取 manifest

`apps/scripts/prism_canonical.py` 现在会在 canonical load 阶段读取 sibling manifest，并把它挂到 payload：

- `load_watchlist_snapshot()` -> `payload["manifest"]`
- `load_screening_batch()` -> `payload["manifest"]`
- `load_confirmation()` -> `payload["manifest"]`
- `load_decision_brief()` -> `payload["manifest"]`

`apps/control-panel/readiness.py` 的 source freshness 现在优先使用 manifest：

- `manifest.asof / fetched_at`
- `manifest.trade_date`
- `manifest.freshness_status`
- `manifest.live_small_allowed`
- `manifest.fallback_used`
- `manifest.status`

fail-closed 规则：

- 缺 manifest -> stale
- `trade_date != expected_trade_date` -> stale
- `freshness_status in {"stale", "expired"}` -> stale
- `live_small_allowed == false` -> stale
- fallback 且 manifest 未明确允许 live_small -> stale

因此 `today`、`refresh/status?page=today`、`readiness/live` 不再各算一套 freshness。

## allow_unsafe 收紧结果

`/api/portfolio/mode` 现在做了三件事：

1. `allow_unsafe=true` 必须带 `note/reason`
2. `set_account_mode()` 会把 bypass 记录进 `mode_history`
3. 账本状态会保存：
   - `unsafe_bypass_active`
   - `unsafe_bypass_note`
   - `unsafe_bypass_at`

前端 `apps/web/src/app/portfolio/page.tsx` 也不再把它做成普通轻量 checkbox，而是：

- 默认隐藏在“紧急 bypass”区域
- 必须显式展开
- 必须填写原因
- 必须输入确认文本 `LIVE_SMALL`

readiness 层会把 `unsafe_bypass_active` 降级为 warning，因此 bypass 期间页面不会显示绿色 `live_ready`。

## guardrail 实施结果

`packages/prism_data/guardrails.py` 现在可识别：

- `requests.get/post/request`
- `import requests as xxx` 后的 `xxx.get/post/request`
- `from requests import request as xxx`
- `urllib.request.urlopen`
- `from urllib.request import urlopen`
- `import urllib.request as xxx` 后的 `xxx.urlopen`
- `import akshare`
- `from akshare import ...`
- `import baostock`
- `from baostock import ...`
- Sina / Eastmoney / THS / Hexun 硬编码 provider URL

repo 级测试：

- `packages/prism_data/tests/test_guardrails.py`
- `packages/prism_data/tests/test_repo_ingress_guardrails.py`

当前显式 allowlist 只有一项：

1. `packages/quant/free_sources/live_smoke_runner.py`
   - 原因：research-only free-source smoke runner，故意探测 `akshare/baostock`

除了上述例外和 `packages/prism_data/providers/` 外，repo guardrail scan 当前为 0 违规。

## 真实性说明

这次状态不是“Phase 1 骨架完成”。

已经真正接上的闭环是：

1. provider adapter 从 Sina / Eastmoney / THS / AkShare 拉数据
2. `DataGateway` 写 dataset + manifest
3. watchlist / scan / ai_screening / midday / command_brief 写 pipeline sidecar manifest
4. canonical loader 读取 sidecar manifest
5. readiness 基于 manifest 决定 `live_ready / shadow_only / blocked`
6. today / refresh / live gate 共用同一 readiness 输出
7. guardrail 测试防止业务代码回退到直接抓取

## 仍然保留的限制

本次没有处理的内容主要不是“数据入口没做完”，而是范围外事项：

- 历史遗留 research / smoke runner 仍保留 `akshare/baostock` 探测路径，并已显式 allowlist

在用户要求的市场数据入口范围内，当前生产链路已经收口到 `packages/prism_data`。
