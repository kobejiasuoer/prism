# dc_member 可 promotion 清洗 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `reference.dc_member` 以"当前板块归属（最新快照）"语义正确入库，修复跑偏的去重/守卫/enrich，并在 manifest 中诚实标注被 8000 行上限截断的股票。

**Architecture:** 全部改动集中在 `apps/scripts/promote_tinyshare_reference_data.py` 与新测试文件。新增三个纯函数（折叠/泄漏守卫/截断检测），小幅扩展 `save_dataset`/`promote_one` 透传 `extra_fields`/`quality_flags`（`extra` 直接注入返回的 manifest dict，因为它不经 `ProviderResult.extra` 进 manifest），重写 dc_member 分支。dc_member 维持 `display_only`/`reference`——Stage 1 数据治理，不碰正式/实盘、不动 Tushare 适配器、不动核心 manifest.py。

**Tech Stack:** Python 3, pytest。脚本通过 `importlib.util.spec_from_file_location` 在测试中按路径加载（参见 `tests/test_prism_scheduler.py`）。

**Spec:** `docs/superpowers/specs/2026-05-31-dc-member-promotion-cleaning-design.md`

---

## File Structure

- **Modify** `apps/scripts/promote_tinyshare_reference_data.py`
  - 新增常量 `MEMBERSHIP_BOARD_SANITY_CAP`、`DC_MEMBER_ROW_CAP`，以及三个纯函数 `collapse_current_membership` / `detect_membership_leak` / `dc_member_truncated_codes`（插入在 `universe_codes_from_report` 之后、`save_dataset` 之前，约 line 204）。
  - 扩展 `save_dataset`（line 206-255）：新增 `extra_fields` / `quality_flags` 形参；`quality_flags` 经 `ProviderResult` 透传；`extra_fields` 在落盘前注入 `manifest["extra"]`。
  - 扩展 `promote_one`（line 265-282）：新增并转发上述两参数。
  - 重写 dc_member 分支（line 322-350）。
- **Create** `tests/test_dc_member_promotion_cleaning.py`
  - 加载脚本模块；覆盖三个纯函数 + 元数据透传 + dc_member 分支端到端。

每个任务都是一个完整 TDD 循环：写失败测试 → 跑确认失败 → 实现 → 跑确认通过 → 提交。

---

## Task 1: `collapse_current_membership`（日快照 → 当前归属）

**Files:**
- Test: `tests/test_dc_member_promotion_cleaning.py`（创建）
- Modify: `apps/scripts/promote_tinyshare_reference_data.py`（约 line 204 插入函数）

- [ ] **Step 1: 创建测试文件（加载器 + collapse 三个测试）**

```python
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROL_PANEL_ROOT = REPO_ROOT / "apps" / "control-panel"
PACKAGES_ROOT = REPO_ROOT / "packages"
for import_path in (str(REPO_ROOT), str(CONTROL_PANEL_ROOT), str(PACKAGES_ROOT)):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)


def _load_script(module_name: str, path: Path) -> ModuleType:
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


promote = _load_script(
    "promote_dc_member_test",
    REPO_ROOT / "apps" / "scripts" / "promote_tinyshare_reference_data.py",
)


def _write_rows(path: Path, rows: list[dict]) -> Path:
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return path


def test_collapse_keeps_latest_snapshot_and_drops_exited_boards():
    rows = [
        {"trade_date": "20260101", "ts_code": "BK0001.DC", "con_code": "600309.SH", "name": "万华化学"},
        {"trade_date": "20260101", "ts_code": "BK0002.DC", "con_code": "600309.SH", "name": "万华化学"},
        {"trade_date": "20260201", "ts_code": "BK0001.DC", "con_code": "600309.SH", "name": "万华化学"},
        {"trade_date": "20260201", "ts_code": "BK0003.DC", "con_code": "600309.SH", "name": "万华化学"},
    ]
    out = promote.collapse_current_membership(rows)
    assert {r["ts_code"] for r in out} == {"BK0001.DC", "BK0003.DC"}
    assert all(r["snapshot_date"] == "2026-02-01" for r in out)
    assert all(r["con_code"] == "600309.SH" for r in out)


def test_collapse_identity_from_con_code_not_board():
    rows = [{"trade_date": "20260201", "ts_code": "BK0164.DC", "con_code": "600309.SH", "name": "万华化学"}]
    out = promote.collapse_current_membership(rows)
    assert len(out) == 1
    assert out[0]["code"] == "600309"
    assert out[0]["symbol"] == "sh600309"
    assert out[0]["ts_code"] == "BK0164.DC"


def test_collapse_dedups_board_within_latest_snapshot():
    rows = [
        {"trade_date": "20260201", "ts_code": "BK0001.DC", "con_code": "600000.SH", "name": "X"},
        {"trade_date": "20260201", "ts_code": "BK0001.DC", "con_code": "600000.SH", "name": "X"},
    ]
    assert len(promote.collapse_current_membership(rows)) == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_dc_member_promotion_cleaning.py -v`
Expected: FAIL —`AttributeError: module ... has no attribute 'collapse_current_membership'`

- [ ] **Step 3: 实现函数（插入在 `universe_codes_from_report` 之后、`def save_dataset` 之前，约 line 204）**

```python
# --- dc_member (Dongcai board membership) cleaning helpers ---------------------
# dc_member raw rows are daily snapshots: {trade_date, ts_code(=board), con_code(=stock), name}.
# They are NOT in/out interval rows (unlike ths_member/index_member), so they need a
# dedicated collapse + leak guard rather than the generic unique_rows/enrich_rows path.

MEMBERSHIP_BOARD_SANITY_CAP = 150  # max plausible distinct boards per stock (observed max=72)
DC_MEMBER_ROW_CAP = 8000           # Dongcai API hard row cap; files at the cap have truncated history


def collapse_current_membership(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse dc_member daily snapshots to each stock's CURRENT board membership.

    For every stock (``con_code``) keep only the rows on its latest ``trade_date``,
    deduped by board (``ts_code``). Stock identity (``code``/``symbol``) is derived
    from ``con_code`` -- never from the board ``ts_code``.
    """
    by_stock: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        con = str(row.get("con_code") or "").strip()
        if con:
            by_stock.setdefault(con, []).append(row)

    output: list[dict[str, Any]] = []
    for con, stock_rows in by_stock.items():
        latest = max((compact_date(r.get("trade_date")) for r in stock_rows), default="")
        if not latest:
            continue
        seen_boards: set[str] = set()
        for r in stock_rows:
            if compact_date(r.get("trade_date")) != latest:
                continue
            board = str(r.get("ts_code") or "").strip()
            if not board or board in seen_boards:
                continue
            seen_boards.add(board)
            item: dict[str, Any] = {
                "ts_code": board,
                "con_code": con,
                "name": r.get("name"),
                "snapshot_date": dash_date(r.get("trade_date")),
            }
            code = digits_code(con)
            if len(code) == 6:
                item["code"] = code
                item["symbol"] = prism_code(con)
            output.append(item)
    return output
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_dc_member_promotion_cleaning.py -v`
Expected: PASS（3 个 collapse 测试）

- [ ] **Step 5: 提交**

```bash
git add tests/test_dc_member_promotion_cleaning.py apps/scripts/promote_tinyshare_reference_data.py
git commit -m "feat(promote): add collapse_current_membership for dc_member daily snapshots"
```

---

## Task 2: `detect_membership_leak`（语义化泄漏守卫）

**Files:**
- Test: `tests/test_dc_member_promotion_cleaning.py`（追加）
- Modify: `apps/scripts/promote_tinyshare_reference_data.py`（紧接 `collapse_current_membership` 之后）

- [ ] **Step 1: 追加失败测试**

```python
def test_detect_leak_flags_multiple_con_codes(tmp_path):
    p = _write_rows(tmp_path / "600000.SH.json", [
        {"trade_date": "20260201", "ts_code": "BK0001.DC", "con_code": "600000.SH", "name": "X"},
        {"trade_date": "20260201", "ts_code": "BK0001.DC", "con_code": "000001.SZ", "name": "Y"},
    ])
    leak = promote.detect_membership_leak([p])
    assert leak is not None
    assert leak["reason"] == "member_filter_leak_detected"
    assert leak["detail"] == "multiple_con_codes"


def test_detect_leak_passes_sane_file_and_flags_over_cap(tmp_path):
    sane = _write_rows(tmp_path / "600309.SH.json", [
        {"trade_date": "20260201", "ts_code": f"BK{i:04d}.DC", "con_code": "600309.SH", "name": "Z"}
        for i in range(72)
    ])
    assert promote.detect_membership_leak([sane]) is None

    over = _write_rows(tmp_path / "600519.SH.json", [
        {"trade_date": "20260201", "ts_code": f"BK{i:04d}.DC", "con_code": "600519.SH", "name": "Z"}
        for i in range(promote.MEMBERSHIP_BOARD_SANITY_CAP + 1)
    ])
    leak = promote.detect_membership_leak([over])
    assert leak is not None
    assert leak["detail"] == "board_count_over_cap"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_dc_member_promotion_cleaning.py -k detect_leak -v`
Expected: FAIL —`AttributeError: ... 'detect_membership_leak'`

- [ ] **Step 3: 实现函数**

```python
def detect_membership_leak(paths: list[Path]) -> dict[str, Any] | None:
    """Detect a genuinely unfiltered/leaked dc_member raw file.

    A correct per-stock file has exactly one ``con_code`` (the queried stock) and a
    sane number of boards. Many con_codes => the con_code filter leaked the whole
    table; an absurd board count is a secondary sanity check.
    """
    for path in paths:
        rows = rows_from_path(path)
        con_codes = {str(r.get("con_code") or "").strip() for r in rows if r.get("con_code")}
        if len(con_codes) > 1:
            return {"path": str(path), "reason": "member_filter_leak_detected",
                    "detail": "multiple_con_codes", "con_codes": len(con_codes)}
        boards = {str(r.get("ts_code") or "").strip() for r in rows if r.get("ts_code")}
        if len(boards) > MEMBERSHIP_BOARD_SANITY_CAP:
            return {"path": str(path), "reason": "member_filter_leak_detected",
                    "detail": "board_count_over_cap", "boards": len(boards)}
    return None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_dc_member_promotion_cleaning.py -k detect_leak -v`
Expected: PASS（2 个）

- [ ] **Step 5: 提交**

```bash
git add tests/test_dc_member_promotion_cleaning.py apps/scripts/promote_tinyshare_reference_data.py
git commit -m "feat(promote): add detect_membership_leak guard for dc_member"
```

---

## Task 3: `dc_member_truncated_codes`（截断检测）

**Files:**
- Test: `tests/test_dc_member_promotion_cleaning.py`（追加）
- Modify: `apps/scripts/promote_tinyshare_reference_data.py`（紧接 `detect_membership_leak` 之后）

- [ ] **Step 1: 追加失败测试**

```python
def test_truncated_codes_flags_files_at_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(promote, "DC_MEMBER_ROW_CAP", 3)
    capped = _write_rows(tmp_path / "600309.SH.json", [
        {"trade_date": "20260201", "ts_code": "BK0001.DC", "con_code": "600309.SH", "name": "Z"}
        for _ in range(3)
    ])
    small = _write_rows(tmp_path / "000830.SZ.json", [
        {"trade_date": "20260201", "ts_code": "BK0002.DC", "con_code": "000830.SZ", "name": "Z"}
    ])
    assert promote.dc_member_truncated_codes([capped, small]) == ["600309.SH"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_dc_member_promotion_cleaning.py -k truncated -v`
Expected: FAIL —`AttributeError: ... 'dc_member_truncated_codes'`

- [ ] **Step 3: 实现函数**

```python
def dc_member_truncated_codes(paths: list[Path]) -> list[str]:
    """Stock codes whose raw snapshot count is at the API hard cap -> early history truncated."""
    truncated: list[str] = []
    for path in paths:
        rows = rows_from_path(path)
        if len(rows) >= DC_MEMBER_ROW_CAP:
            con_codes = {str(r.get("con_code") or "").strip() for r in rows if r.get("con_code")}
            truncated.append(next(iter(con_codes), path.stem))
    return sorted(truncated)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_dc_member_promotion_cleaning.py -k truncated -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add tests/test_dc_member_promotion_cleaning.py apps/scripts/promote_tinyshare_reference_data.py
git commit -m "feat(promote): add dc_member_truncated_codes coverage detector"
```

---

## Task 4: `save_dataset`/`promote_one` 透传 extra_fields + quality_flags

**Files:**
- Test: `tests/test_dc_member_promotion_cleaning.py`（追加）
- Modify: `apps/scripts/promote_tinyshare_reference_data.py:206-282`

- [ ] **Step 1: 追加失败测试**

```python
def test_save_dataset_threads_extra_and_quality_flags(tmp_path):
    from prism_data.repositories import DatasetRepository
    repo = DatasetRepository(tmp_path / "datasets")
    manifest = promote.save_dataset(
        repo,
        dataset="reference.dc_member",
        trade_date="2026-05-29",
        key="hs300-zz500",
        rows=[{"ts_code": "BK0001.DC", "con_code": "600309.SH", "code": "600309", "symbol": "sh600309"}],
        source_api="dc_member",
        params={"universe": "hs300+zz500"},
        source_raw_paths=[],
        refresh_existing=True,
        extra_fields={"membership": "current_snapshot", "truncated_codes": ["600309.SH"]},
        quality_flags=["partial_history_truncated"],
    )
    assert manifest is not None
    assert manifest["quality_flags"] == ["partial_history_truncated"]
    assert manifest["extra"]["membership"] == "current_snapshot"
    assert manifest["extra"]["truncated_codes"] == ["600309.SH"]

    # round-trips through the on-disk manifest (verbatim JSON, not stripped)
    _, loaded = repo.load_dataset("reference.dc_member", "2026-05-29", "hs300-zz500")
    assert loaded["extra"]["membership"] == "current_snapshot"
    assert loaded["quality_flags"] == ["partial_history_truncated"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_dc_member_promotion_cleaning.py -k threads_extra -v`
Expected: FAIL —`TypeError: save_dataset() got an unexpected keyword argument 'extra_fields'`

- [ ] **Step 3a: 扩展 `save_dataset` 签名**

把 `save_dataset` 形参列表末尾（`refresh_existing: bool,` 之后、`) -> dict[str, Any] | None:` 之前）改为：

```python
    refresh_existing: bool,
    extra_fields: dict[str, Any] | None = None,
    quality_flags: list[str] | None = None,
) -> dict[str, Any] | None:
```

- [ ] **Step 3b: `ProviderResult` 里透传 quality_flags**

把 `ProviderResult(...)` 中的 `quality_flags=[],`（line 240）改为：

```python
        quality_flags=list(quality_flags or []),
```

- [ ] **Step 3c: 落盘前注入 extra**

把 line 251-252：

```python
    manifest = manifest_from_provider_result(result, expected_trade_date=trade_date, live_small_allowed=False)
    data_path, manifest_path = repository.save_dataset(dataset, trade_date, key, payload, manifest)
```

改为：

```python
    manifest = manifest_from_provider_result(result, expected_trade_date=trade_date, live_small_allowed=False)
    if extra_fields:
        manifest["extra"] = {**manifest.get("extra", {}), **extra_fields}
    data_path, manifest_path = repository.save_dataset(dataset, trade_date, key, payload, manifest)
```

- [ ] **Step 3d: `promote_one` 加参并转发**

把 `promote_one` 定义（line 265）改为带新参，并在 `save_dataset(...)` 调用末尾转发：

```python
    def promote_one(dataset: str, key: str, rows: Any, source_api: str, source_paths: list[Path], params: dict[str, Any] | None = None, extra_fields: dict[str, Any] | None = None, quality_flags: list[str] | None = None) -> None:
        manifest = save_dataset(
            repository,
            dataset=dataset,
            trade_date=trade_date,
            key=key,
            rows=rows,
            source_api=source_api,
            params=params or {},
            source_raw_paths=source_paths,
            refresh_existing=refresh_existing,
            extra_fields=extra_fields,
            quality_flags=quality_flags,
        )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_dc_member_promotion_cleaning.py -k threads_extra -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add tests/test_dc_member_promotion_cleaning.py apps/scripts/promote_tinyshare_reference_data.py
git commit -m "feat(promote): thread extra_fields/quality_flags into save_dataset manifest"
```

---

## Task 5: 重写 dc_member 分支（接线 + 端到端测试）

**Files:**
- Test: `tests/test_dc_member_promotion_cleaning.py`（追加）
- Modify: `apps/scripts/promote_tinyshare_reference_data.py:324-350`

- [ ] **Step 1: 追加端到端失败测试**

```python
def test_dc_member_branch_promotes_with_current_snapshot_and_truncation_metadata(tmp_path, monkeypatch):
    from prism_data.repositories import DatasetRepository
    monkeypatch.setattr(promote, "DC_MEMBER_ROW_CAP", 3)

    run = tmp_path / "run"
    dc = run / "raw" / "dc_member"
    dc.mkdir(parents=True)
    # truncated stock: rows at the (patched) cap; older board BK0002 dropped from latest snapshot
    _write_rows(dc / "600309.SH.json", [
        {"trade_date": "20260101", "ts_code": "BK0002.DC", "con_code": "600309.SH", "name": "万华化学"},
        {"trade_date": "20260529", "ts_code": "BK0001.DC", "con_code": "600309.SH", "name": "万华化学"},
        {"trade_date": "20260529", "ts_code": "BK0001.DC", "con_code": "600309.SH", "name": "万华化学"},
    ])
    # normal stock: single snapshot, under cap
    _write_rows(dc / "000830.SZ.json", [
        {"trade_date": "20260529", "ts_code": "BK0003.DC", "con_code": "000830.SZ", "name": "某股"},
    ])

    repository = DatasetRepository(tmp_path / "datasets")
    summary = promote.promote(run, "2026-05-29", repository)

    reasons = {s.get("reason") for s in summary["skipped"]}
    assert "member_filter_leak_detected" not in reasons
    assert "possible_unfiltered_or_limit_hit" not in reasons

    data, manifest = repository.load_dataset("reference.dc_member", "2026-05-29", "hs300-zz500")
    assert manifest is not None
    assert manifest["quality_flags"] == ["partial_history_truncated"]
    assert manifest["extra"]["membership"] == "current_snapshot"
    assert "600309.SH" in manifest["extra"]["truncated_codes"]
    # current snapshot: 600309 -> only BK0001 (BK0002 已退出); identity from con_code
    pairs = {(r["con_code"], r["ts_code"]) for r in data}
    assert ("600309.SH", "BK0001.DC") in pairs
    assert ("600309.SH", "BK0002.DC") not in pairs
    assert ("000830.SZ", "BK0003.DC") in pairs
    assert all(r.get("code") for r in data)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_dc_member_promotion_cleaning.py -k branch_promotes -v`
Expected: FAIL —老分支不传元数据，`manifest["quality_flags"]` 为 `[]` 且无 `extra` 键（`KeyError`/断言失败）

- [ ] **Step 3: 重写 dc_member 分支**

把 line 324-350 的整个 `if dc_paths:` 块（从 `if dc_paths:` 到 `promote_one("reference.dc_member", ...)` 结束）替换为：

```python
    if dc_paths:
        if universe_codes and len(dc_paths) < len(universe_codes):
            skipped.append({
                "dataset": "reference.dc_member",
                "key": "hs300-zz500",
                "reason": "partial_optional_harvest_skipped",
                "raw_files": len(dc_paths),
                "expected_files": len(universe_codes),
            })
        else:
            leak = detect_membership_leak(dc_paths)
            if leak:
                skipped.append({"dataset": "reference.dc_member", "key": "hs300-zz500", **leak})
            else:
                dc_rows, _dc_paths = rows_from_dir(raw_dir, "dc_member")
                rows = collapse_current_membership(dc_rows)
                truncated = dc_member_truncated_codes(dc_paths)
                extra_fields = {
                    "membership": "current_snapshot",
                    "snapshot_basis": "latest_trade_date_per_code",
                    "truncated_codes": truncated,
                    "truncated_note": (
                        "命中接口 8000 行硬上限的股票，其早期日快照被截断；"
                        "当前归属不受影响，但历史区间不可信。"
                    ),
                }
                promote_one(
                    "reference.dc_member", "hs300-zz500", rows, "dc_member", dc_paths,
                    {"universe": "hs300+zz500"},
                    extra_fields=extra_fields,
                    quality_flags=["partial_history_truncated"] if truncated else [],
                )
```

注意：保留其上方 `dc_member_dir = raw_dir / "dc_member"` 与 `dc_paths = sorted(...)`（line 322-323）不变。

- [ ] **Step 4: 跑全文件测试确认通过**

Run: `python3 -m pytest tests/test_dc_member_promotion_cleaning.py -v`
Expected: PASS（全部 8 个测试）

- [ ] **Step 5: 提交**

```bash
git add tests/test_dc_member_promotion_cleaning.py apps/scripts/promote_tinyshare_reference_data.py
git commit -m "feat(promote): promote dc_member as current-snapshot membership with truncation metadata"
```

---

## Task 6: 用真实 raw 验证（不提交数据产物）

**Files:** 无代码改动；运行真实 promote 并核验输出。`data/` 为数据产物（不纳入提交）。

- [ ] **Step 1: 确认现状仍是被跳过，并读取 trade_date**

```bash
cd <redacted-path>
RUN="data/prism_data/tinyshare_reference_supplement/20220101_20260529_20260530_152502"
python3 -c "import json; r=json.load(open('$RUN/promotion_report.json')); print('trade_date=', r['trade_date']); print('dc_member skip:', [s for s in r['skipped'] if 'dc_member' in s.get('dataset','')])"
```
Expected: `trade_date= 2026-05-29`；并打印出含 `possible_unfiltered_or_limit_hit` 的 dc_member 跳过记录。

- [ ] **Step 2: 重跑 promote（不带 --refresh-existing → 仅缺失的 dc_member 入库，其余 manifest_exists 快速跳过）**

```bash
python3 apps/scripts/promote_tinyshare_reference_data.py --reference-run "$RUN" --trade-date 2026-05-29 >/tmp/dc_promote.json
echo "exit=$?"
```
Expected: `exit=0`（完整 summary 写入 /tmp/dc_promote.json）。

- [ ] **Step 3: 核验 dc_member 已入库且元数据正确**

```bash
python3 -c "import json; r=json.load(open('$RUN/promotion_report.json')); assert not [s for s in r['skipped'] if 'dc_member' in s.get('dataset','')], r['skipped']; print('dc_member rows promoted:', r['counts'].get('reference.dc_member'))"
python3 -c "import json,glob; p=sorted(glob.glob('data/prism_data/datasets/reference.dc_member/*/hs300-zz500.manifest.json'))[-1]; m=json.load(open(p)); print('manifest:', p); print('row_count:', m['row_count']); print('quality_flags:', m['quality_flags']); print('extra:', m.get('extra'))"
```
Expected:
- dc_member 不再出现在 skipped；`counts['reference.dc_member']` 约 2 万量级。
- manifest `quality_flags == ['partial_history_truncated']`。
- `extra.membership == 'current_snapshot'`，`extra.truncated_codes` 含 `600309.SH` / `600332.SH` / `600348.SH`（命中 8000 上限的 3 只）。

- [ ] **Step 4: 确认无意外的受版本控制文件被改动**

```bash
git status --porcelain | grep -v '^??' | grep -v 'data/prism_data/' || echo "OK: no tracked non-data files dirty"
```
Expected: `OK: ...`（或仅显示本就在途的 WIP；不应出现 promote 脚本/测试以外的新改动——它们已在 Task 1-5 提交）。

---

## Self-Review（已执行，问题已就地修复）

**1. Spec 覆盖：**
- §4.1 `collapse_current_membership` → Task 1；`detect_membership_leak` → Task 2。
- §4.4 截断元数据 / `dc_member_truncated_codes` → Task 3 + Task 5。
- §4.2 重写分支 → Task 5。§4.3 元数据透传（含 `extra` 注入 manifest dict 的订正机制）→ Task 4。
- §2 连带 bug（enrich 取错身份）→ 由 `collapse_current_membership` 用 `con_code` 派生身份覆盖（Task 1 的 `test_collapse_identity_from_con_code_not_board`）。
- §5 测试 → 各 Task 的 Step 1。§8 成功标准 1-5 → Task 5（端到端）+ Task 6（真实验证）。

**2. 占位扫描：** 无 TBD/TODO；每个代码步骤均含完整可运行代码与确切命令/预期输出。

**3. 类型/命名一致性：** `collapse_current_membership` / `detect_membership_leak` / `dc_member_truncated_codes` / `MEMBERSHIP_BOARD_SANITY_CAP` / `DC_MEMBER_ROW_CAP` / `extra_fields` / `quality_flags` 跨任务拼写一致；泄漏 reason 统一为 `member_filter_leak_detected`，截断 flag 统一为 `partial_history_truncated`。
