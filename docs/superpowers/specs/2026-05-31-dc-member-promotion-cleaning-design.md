# dc_member 可 promotion 清洗策略 — 设计文档

- 日期: 2026-05-31
- Stage: **Stage 1 — Data Governance**（数据治理）
- 状态: 已批准设计，待写实现计划
- 涉及数据集: `reference.dc_member`（东财板块归属，`source_lane=reference`，`decision_scope=display_only`）

## 1. 背景 / 问题

`reference.dc_member` 当前**无法 promote 入库**。最近一次 promote（运行目录 `data/prism_data/tinyshare_reference_supplement/20220101_20260529_20260530_152502/`，2026-05-30）被 fail-closed 守卫直接跳过，`promotion_report.json` 记录原因 `possible_unfiltered_or_limit_hit`：守卫发现 `600309.SH.json` 有 8000 行（≥5000），判定"可能未过滤/命中上限"而拒绝入库。

守卫逻辑位于 [promote_tinyshare_reference_data.py:334-346](../../../apps/scripts/promote_tinyshare_reference_data.py#L334-L346)，清洗逻辑位于 [promote_tinyshare_reference_data.py:348-350](../../../apps/scripts/promote_tinyshare_reference_data.py#L348-L350)。

## 2. 诊断（已用现有 raw 核实）

对该运行目录 `raw/dc_member/`（800 个文件，每个 universe 股票一个）的实测结论：

- **schema 统一**：全部 535,369 行只有 4 个字段 `con_code / name / trade_date / ts_code`，**0 行含 `in_date` / `out_date`**。其中 `ts_code` 是**东财板块码**（如 `BK0164.DC`），`con_code` 才是**股票**（如 `600309.SH`）。
- **它是"日快照"数据**：`600309.SH.json` 的 8000 行 = 18 个板块 × **511 个交易日**（2024-12-20 → 2026-05-30）。每行是"某交易日该股属于某板块"的快照，不是进/出区间记录。
- **8000 是接口硬上限**：3 个文件正好卡在 8000 行（`600348.SH` / `600332.SH` / `600309.SH`）→ **早期历史被截断**（抓取窗口本应自 2022 起，600309 实际只到 2024-12）。另有 5 个文件介于 5660–7393 行（超过旧的 5000 守卫，但**未到 8000 上限、未被截断**）。
- **折叠后基数小且正常**：每股去重后 `(板块, 股票)` 对：min=11 / p50=24 / p95=40 / **max=72**，无任何股票超过 72 个板块。

### 由此暴露的两个既有缺陷

1. **去重键对 dc_member 是错的**：现有 `unique_rows(dc_rows, ("ts_code","con_code","in_date","out_date"))` 是从 `ths_member` 分支照抄的。`in_date`/`out_date` 在 dc_member 中**永不存在** → 它们恒为空串，去重退化为按 `(ts_code, con_code)` 折叠。当前能折叠纯属侥幸，语义错误且脆弱。
2. **enrich 取错身份**：`enrich_stock_row` 优先用 `ts_code` 派生 `code`/`symbol`（[promote_tinyshare_reference_data.py:158](../../../apps/scripts/promote_tinyshare_reference_data.py#L158)）。对 dc_member 而言 `ts_code` 是**板块码**，会把 `BK0164.DC` 误派生成假股票码。股票身份应取自 `con_code`。

## 3. 决策

- **语义（已选）**：**当前归属（最新快照）** — 每只股票取其**最新 `trade_date`** 的板块集合。理由：完整可信、不受 8000 截断影响（最新日快照永远完整）、最贴合"东财板块归属"的展示与归因需求。"已退出的板块只存在于旧快照"会被自然排除。
- **实现路径（已选）**：**promote 时清洗现有 raw**（不重跑抓取，不动抓取层）。符合"基于现有 raw"的要求，立即解卡。抓取层收口（按最新 trade_date 收口以减小未来 raw）记为**可选后续项**，不在本卡范围。

## 4. 设计

全部改动集中在 `apps/scripts/promote_tinyshare_reference_data.py` 加一个测试文件。dc_member 维持 `display_only`/`reference`，不碰正式/实盘改标，不动 Tushare 适配器。

### 4.1 新增两个纯函数（与 `unique_rows` / `enrich_rows` / `filter_800` 并列，便于单测）

**`collapse_current_membership(rows) -> list[dict]`**
- 按 `con_code`（股票）分组。
- 对每只股票，求其最新 `trade_date`（按 `compact_date` 归一后取 max）。
- 仅保留该最新日的行，按板块 `ts_code` 去重，每个板块输出一行，字段：
  ```
  {
    "ts_code":       <板块码，如 BK0164.DC，保留原始约定>,
    "con_code":      <股票，如 600309.SH>,
    "name":          <最新快照里的股票名>,
    "snapshot_date": <dash_date(最新 trade_date)>,
    "code":          <由 con_code 派生的 6 位股票码>,
    "symbol":        <由 con_code 派生的 prism_code，如 sh600309>,
  }
  ```
- **身份取自 `con_code`**（修复 §2 缺陷 2）。**不再事后调用泛用 `enrich_rows`**（避免按板块码误派生）。

**`detect_membership_leak(paths) -> dict | None`**
- 用语义化校验替换"原始行数 ≥5000"的代理判断：
  - 每个文件 `distinct(con_code)` 必须 `== 1`（直接验证 `con_code` 过滤真的生效；整表泄漏会有多个 con_code）。
  - `distinct(板块 ts_code) > 150` 视为异常（实测 max=72，留约 2x 余量，作为兜底 sanity cap）。
- 命中任一条件 → 返回首个违例文件信息 `{path, reason, ...}`；否则返回 `None`。
- 常量 `MEMBERSHIP_BOARD_SANITY_CAP = 150`。

### 4.2 改 dc_member 分支（[promote_tinyshare_reference_data.py:322-350](../../../apps/scripts/promote_tinyshare_reference_data.py#L322-L350)）

- 保留 `partial_optional_harvest_skipped`（抓取文件数 < universe 时仍应跳过）。
- 将 `possible_unfiltered_or_limit_hit`（行数守卫）替换为 `detect_membership_leak(dc_paths)`；命中则跳过并记录 `reason="member_filter_leak_detected"` + 违例详情。
- 将 `enrich_rows(unique_rows(dc_rows, (...错误键...)))` 替换为 `collapse_current_membership(dc_rows)`。
- `promote_one("reference.dc_member", "hs300-zz500", rows, "dc_member", dc_paths, params=..., extra_fields=..., quality_flags=...)`（见 §4.3）。

### 4.3 元数据透传（小幅扩展签名）

当前 `save_dataset` 把 `quality_flags=[]` 与 `extra={...}` 写死（[promote_tinyshare_reference_data.py:240-249](../../../apps/scripts/promote_tinyshare_reference_data.py#L240-L249)）。扩展为可选透传：

- `save_dataset(..., extra_fields: dict | None = None, quality_flags: list[str] | None = None)`：
  - `extra={...原有四项..., **(extra_fields or {})}`
  - `quality_flags=list(quality_flags or [])`
- `promote_one(..., extra_fields=None, quality_flags=None)`：原样转发。
- **仅 dc_member 调用传入这两个参数；其余所有 promote_one 调用保持默认 → 行为不变。**

安全性已核实：dc_member 走非 pipeline 的 `_authority_metadata`（[manifest.py:1125](../../../packages/prism_data/manifest.py#L1125)），`quality_flags` 在该路径仅原样透传进 manifest（[manifest.py:1149](../../../packages/prism_data/manifest.py#L1149)），不参与门控派生；且 `live_small_allowed=False` 已将正式/权威布尔锁死。会影响 `source_authority_ready` 的 `quality_flags` 派生只存在于 `_pipeline_authority_metadata`（[manifest.py:1104](../../../packages/prism_data/manifest.py#L1104)），与 dc_member 无关。

### 4.4 诚实的覆盖元数据（Stage 1 核心）

dc_member 的 `promote_one` 传入：

- `extra_fields`:
  ```
  {
    "membership": "current_snapshot",
    "snapshot_basis": "latest_trade_date_per_code",
    "truncated_codes": [<raw 行数 == 硬上限 8000 的股票码>],   # 当前为 600348.SH / 600332.SH / 600309.SH
    "truncated_note": "命中接口 8000 行硬上限的股票，其早期日快照被截断；当前归属不受影响，但历史区间不可信。",
  }
  ```
- `quality_flags`: `["partial_history_truncated"]`（数据集级，仅当 `truncated_codes` 非空时附加）。
- 截断判定常量 `DC_MEMBER_ROW_CAP = 8000`（实测硬上限；`truncated = raw_row_count >= DC_MEMBER_ROW_CAP`）。

这让 manifest **自描述**语义与权威边界（"explicit, queryable"，满足 Stage 1）。是否在某个 UI 面板渲染该 flag 属下游、**不在本卡范围**（避免 web 层 scope 蔓延）。

## 5. 测试

测试文件 `tests/test_dc_member_promotion_cleaning.py`（遵循仓库脚本测试约定：根 `tests/` 下，用 `importlib.util.spec_from_file_location` 按文件路径加载 `apps/scripts/promote_tinyshare_reference_data.py`，参见 `tests/test_prism_scheduler.py` 的 `_load_script` 模式）。覆盖：

- `collapse_current_membership`：
  - 最新日的板块胜出；只存在于旧快照的板块（已退出）被排除。
  - 多个 `trade_date` 下同一板块只输出一行，`snapshot_date` 为最新日。
  - `code`/`symbol` 取自 `con_code` 而非板块 `ts_code`。
- `detect_membership_leak`：
  - 单文件多 `con_code` → 判泄漏。
  - 72 个板块 → 放行；200 个板块 → 拦截（越过 sanity cap）。
- 用一个微型 fixture（含 8000 行级截断股 + 正常股）跑 dc_member 分支：断言不再跳过、promote 成功、`extra.truncated_codes` 含截断股、`quality_flags` 含 `partial_history_truncated`。

## 6. 范围 & Stage 纪律确认

- 仅改 `apps/scripts/promote_tinyshare_reference_data.py` + 1 个测试文件。
- dc_member 仍是 `display_only` / `reference`；**不**做"display-only → formal/live"改标；**不**新增/改 Tushare 适配器；**无** ML；**不**碰 `data/quant/` 正式研究产物。
- 落在 Stage 1（让一个参考数据集以正确语义入库 + 标注真实权威边界）。✅

## 7. 不在本范围（后续项）

- **抓取层收口**：未来把 dc_member 抓取调用按最新 `trade_date` 收口，从源头避免 8000 行历史与截断（路径 ②）。记为可选后续，不在本卡。
- **第 ② 件**：`share_float` 整理（独立 spec→plan）。
- **第 ③ 件**：把数据接入解释/归因链路——**动手前需先做 stage 边界确认**（display-only 数据能否影响 `tushare_score`/候选排序，避免触碰锚点"不要让 display-only 数据变成正式决策输入"红线）。

## 8. 成功标准

1. 用现有 raw 重跑 promote，`reference.dc_member` **成功入库**，`promotion_report.json` 不再含 `possible_unfiltered_or_limit_hit`。
2. 入库结果为**当前归属快照**：每 `(股票, 板块)` 一行，`code`/`symbol` 正确指向股票，约 ~20k 行量级（current ⊆ window-set，确切行数运行时确定）。
3. manifest 含 `extra.membership=current_snapshot`、`truncated_codes`（当前 3 只）与 `quality_flags=[partial_history_truncated]`。
4. 守卫仍能拦截真正的整表泄漏（多 con_code / 板块数越界），不再误伤日快照。
5. 两个纯函数单测通过；其余 promote_one 调用行为不变（回归）。
