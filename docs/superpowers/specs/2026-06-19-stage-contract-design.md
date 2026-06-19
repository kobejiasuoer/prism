# 阶段间 JSON 契约守卫 设计文档

- 日期：2026-06-19
- 范围：scan → ai_screening → midday_verify → candidate_lifecycle 四阶段间 JSON 的"承重字段"守卫
- 上游依据：`docs/system-audit-2026-06-19.md`（问题 11：阶段间无 schema，静默退化）
- 本项**不含**：全量 pydantic 模型、前端 schema、dashboard_data 的 payload 校验。

---

## 1. 目标与成功标准

### 目标
在四个阶段的**输出端**加 fail-fast 守卫：当输出 payload 缺少下游真正依赖的承重字段时，抛 `StageContractError`（带具体缺失字段名 + 阶段名），而不是让下游 `.get()` 静默拿到 `None`/空列表。

### 成功标准（可验证）
- [ ] 新建 `packages/screener/stage_contract.py`，定义 4 个阶段的承重字段清单 + `validate_stage_output(payload, stage)`。
- [ ] `scan`/`ai_screening`/`midday_verify`/`candidate_lifecycle` 四个脚本在写文件前调用守卫；缺字段时抛 `StageContractError`。
- [ ] 守卫只校验**承重字段**（每阶段 ≤ 10 个），不是全量字段——加新字段不触发守卫。
- [ ] 单元测试：构造缺字段的 payload，验证抛错 + 错误信息含字段名；完整 payload 通过。
- [ ] 全程通过 `pytest -q`。

### 非目标（明确排除）
- 不做全量 pydantic schema（60 字段的 shortlist 会让每次加字段成 breaking change）。
- 不改 `.get()` 调用方（守卫在输出端，下游不变）。
- 不校验字段类型（只校验存在性 + 非空，类型由消费者自己处理）。
- 不覆盖 dashboard_data.py 读取这些 JSON 时的校验（那是另一层）。

---

## 2. 承重字段清单（基于真实代码验证）

每阶段的字段 = 下游消费者**实际 `.get()` 读取**的字段中，缺失会导致逻辑错误（非空列表/默认值）的子集。

### scan 阶段输出（ai_screening 消费）
承重字段（来自 `ai_screening.py` 的 `scan_data.get(...)` 调用）：
```
market_regime, market_themes, pool, pool_label, strategies, timestamp, trade_date
```
（注：`candidates` 不是承重字段——scan 把股票存在 `strategies`/`verification_universe` 下，ai_screening 对 `candidates` 走 `or []` 回退。）

### ai_screening 阶段输出（midday_verify + candidate_lifecycle + dashboard_data 消费）
承重字段：
```
shortlist（列表）, source_scan_timestamp, timestamp, trade_date
```
shortlist 内每项的承重字段（midday/lifecycle 实际读取）：
```
code, name, tier, best_score, suggested_action
```
（注：无 per-item `timestamp`——时间戳在 payload 顶层，不在每个 shortlist 项上。）

### midday_verify 阶段输出（candidate_lifecycle + dashboard_data 消费）
承重字段：
```
confirmed, downgraded, tracking, validation_status, source_scan_timestamp, verified_against_scan_timestamp, timestamp, trade_date
```

### candidate_lifecycle 阶段输出（dashboard_data 消费）
承重字段（`compute_lifecycle` 产出 + `metadata` 块）：
```
entered, exited, upgraded, downgraded, summary, metadata
```
（时间戳在 `metadata.generated_at`，不在顶层。）

---

## 3. 实现方案

### 3.1 新建 `packages/screener/stage_contract.py`

```python
class StageContractError(Exception):
    """Raised when a stage output is missing load-bearing fields."""

def validate_stage_output(payload, stage):
    """Verify payload has the load-bearing fields for `stage`.

    Raises StageContractError listing every missing/empty field. Only checks
    field PRESENCE and non-emptiness (for lists), not types — consumers handle
    their own type coercion. Intentionally narrow: adding new fields to a stage
    output does NOT require updating this unless they are load-bearing.
    """
```

字段清单用模块级常量 `dict[str, list[str]]`，每阶段一个列表。

### 3.2 接入四个脚本

每个脚本在 `json.dump(...)` 写文件**之前**调 `validate_stage_output(result, "<stage>")`。失败则不写文件、抛错、脚本非零退出（让 cron 的 quality gate 捕获）。

守卫对 shortlist 内部字段的校验：只校验 shortlist 非空时第一项的承重字段（避免空 shortlist 误报；空 shortlist 是合法的"今日无候选"）。

---

## 4. 任务分解

### 任务 1：stage_contract.py + 单元测试
- 新建模块 + 4 阶段字段清单 + `validate_stage_output`。
- 测试：每阶段缺各字段 → 抛错含字段名；完整 payload → 通过；空 shortlist → 通过。

### 任务 2：接入 scan.py
- 写文件前调守卫。

### 任务 3：接入 ai_screening.py
- 写文件前调守卫（含 shortlist 内部字段）。

### 任务 4：接入 midday_verify.py
- 写文件前调守卫。

### 任务 5：接入 candidate_lifecycle.py
- 写文件前调守卫。

执行顺序：1 → 2 → 3 → 4 → 5。

---

## 5. 风险

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 守卫误报（合法输出被判缺字段） | 中 | 高（阻塞流水线） | 字段清单严格基于真实消费者；空 shortlist 特判；先在测试里跑真实 payload 样本 |
| 承重字段清单过时 | 低 | 低 | 加注释指向消费者代码；后续加字段时review |

---

## 附录：代码引用
- `packages/screener/ai_screening.py:114` 读 scan_result；`:1591-1603` 写 ai_screening_result
- `packages/screener/midday_verify.py:40-42, 767-773` 读 ai + 写 midday
- `packages/screener/candidate_lifecycle.py:768-769, 814-821` 读 ai+midday + 写 lifecycle
- `packages/screener/scan.py:2417-2431` 写 scan_result
