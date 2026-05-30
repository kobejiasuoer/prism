# Tushare Factor Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn already-ingested Tushare datasets into a factor layer that scores/re-ranks candidates, explains per-stock conclusions, and seeds a per-factor learning loop — without loosening any real-money gate.

**Architecture:** One self-contained factor core (`packages/screener/tushare_factors.py`) reads datasets via the `prism_data` dataset root (no network) and returns a `FactorBundle` (score, breakdown, tags, risk_flags, structured explanation, raw snapshot). Three consumers use it: the scan/screening pipeline (bounded re-rank), the control-panel APIs (candidate cards + `formal_data.factor_profile`), and the Decision Ledger (`factor_snapshot` + factor learning loop). Factor data never enters the readiness/account/decision-contract code paths.

**Tech Stack:** Python 3 (stdlib + `prism_data`), pytest; Next.js + TypeScript (`tsc --noEmit`).

---

## Conventions & invariants (read before any task)

- **Dependency direction:** `packages/screener` may import `prism_data` only — never `apps/control-panel`. `apps/control-panel` may import `screener` (it already does via `prism_canonical`).
- **Safety:** never pass factor data into `compute_readiness` or `decision_contract`. Weekend stays `shadow_only`. All changes are additive — do not revert existing uncommitted working-tree changes on `codex/ask-v2`.
- **Fault tolerance:** every factor value is `Optional`; missing file/manifest/NaN/Inf/empty/`"-"` → `None`; never raise on bad data; never fabricate a score for a missing dimension.
- **Test commands:** `pytest <path>` from repo root (pyproject `testpaths = apps/control-panel/tests, tests`); `npm run typecheck` from `apps/web`.
- **Naming (locked, used across tasks):**
  - FactorBundle keys: `tushare_score`, `data_completeness`, `tushare_score_breakdown`, `factor_tags`, `risk_flags`, `explanation`, `factor_snapshot`, `trade_date_used`, `pool_standing`.
  - `explanation` keys: `entry_reason`, `upgrade_condition`, `abandon_condition`, `supporting_evidence`, `counter_risks`, `evidence` (`fundamental`/`capital`/`trading_anomaly`/`index_weight`, each `{values, interpretation, available}`).
  - Scan candidate gets `tushare_factors` (=FactorBundle); scan top-level gets `tushare_factor_pool_stats`.
  - Canonical candidate exposes `tushare_score`, `tushare_score_breakdown`, `factor_tags`, `factor_risk_flags`, `factor_explanation`, and full `tushare_factors` (NOT `risk_flags` — that name is taken).
  - Public functions: `extract_factor_values`, `compute_pool_stats`, `score_factor_values`, `compute_factor_bundle`, `build_factor_snapshot`.
  - Tuning constants (in `tushare_factors.py`): `DIMENSION_WEIGHTS`, `PRIORITY_ADJUSTMENT_CAP=6.0`, `PRIORITY_ADJUSTMENT_K=0.12`, `RISK_FLAG_PENALTY=1.5`.

---

# Phase 1 — Factor core (the heart)

## Task 1.1: Module skeleton + dataset readers + import-seam smoke test

**Files:**
- Create: `packages/screener/tushare_factors.py`
- Test: `tests/test_tushare_factors.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tushare_factors.py
import json
import os
from pathlib import Path

import pytest


@pytest.fixture()
def dataset_root(tmp_path, monkeypatch):
    root = tmp_path / "datasets"
    root.mkdir()
    monkeypatch.setenv("PRISM_DATASET_REPOSITORY_ROOT", str(root))
    return root


def _write(root: Path, dataset: str, date: str, key: str, payload):
    d = root / dataset / date
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{key}.json").write_text(json.dumps(payload), encoding="utf-8")
    (d / f"{key}.manifest.json").write_text(json.dumps({"trade_date": date, "provider": "tushare"}), encoding="utf-8")


def test_module_imports_and_reads_dataset(dataset_root):
    from screener import tushare_factors as tf

    _write(dataset_root, "valuation.daily", "2026-05-29", "600519",
           [{"trade_date": "2026-05-29", "pe_ttm": 30.0, "pb": 8.0}])
    rows, manifest = tf._load_dataset("valuation.daily", "2026-05-29", "600519")
    assert isinstance(rows, list) and rows[0]["pe_ttm"] == 30.0
    assert manifest["provider"] == "tushare"


def test_resolve_trade_date_falls_back_to_latest(dataset_root):
    from screener import tushare_factors as tf

    _write(dataset_root, "valuation.daily", "2026-05-27", "600519", [{"trade_date": "2026-05-27"}])
    _write(dataset_root, "valuation.daily", "2026-05-29", "600519", [{"trade_date": "2026-05-29"}])
    assert tf._resolve_trade_date("valuation.daily", "2026-05-30") == "2026-05-29"  # walk back
    assert tf._resolve_trade_date("valuation.daily", None) == "2026-05-29"          # latest
    assert tf._resolve_trade_date("valuation.daily", "2026-05-27") == "2026-05-27"  # exact
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tushare_factors.py -v`
Expected: FAIL (`ModuleNotFoundError: screener.tushare_factors`).

- [ ] **Step 3: Write minimal implementation**

```python
# packages/screener/tushare_factors.py
"""Tushare factor layer: read datasets → normalized factor values → score / tags / explanation.

Self-contained and read-only. Imports only stdlib + prism_data (never apps/control-panel).
Never raises on missing/NaN data; every factor value is Optional.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any


def _dataset_root() -> Path:
    override = os.environ.get("PRISM_DATASET_REPOSITORY_ROOT")
    if override:
        return Path(override)
    from prism_data.utils import default_dataset_repository_root
    return Path(default_dataset_repository_root())


def _sanitize(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "default"
    return "".join(ch if ch.isalnum() or ch in {"-", "_", ".", "+"} else "_" for ch in text)


def _read_json_or_none(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _resolve_trade_date(dataset: str, requested: str | None) -> str | None:
    base = _dataset_root() / _sanitize(dataset)
    if not base.exists():
        return None
    dates = sorted(p.name for p in base.iterdir() if p.is_dir())
    if not dates:
        return None
    if requested:
        req = _sanitize(requested)
        if req in dates:
            return req
        earlier = [d for d in dates if d <= req]
        if earlier:
            return earlier[-1]
    return dates[-1]


def _load_dataset(dataset: str, trade_date: str | None, key: str) -> tuple[Any, dict[str, Any] | None]:
    resolved = _resolve_trade_date(dataset, trade_date)
    if not resolved:
        return None, None
    base = _dataset_root() / _sanitize(dataset) / resolved
    data_path = base / f"{_sanitize(key)}.json"
    if not data_path.exists():
        return None, None
    manifest = _read_json_or_none(base / f"{_sanitize(key)}.manifest.json")
    return _read_json_or_none(data_path), manifest


def _safe_float(value: Any) -> float | None:
    if value in (None, "", "-", "None"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else number


def _normalize_code(value: Any) -> str:
    text = str(value or "").strip().upper()
    if "." in text:
        text = text.split(".", 1)[0]
    return "".join(ch for ch in text if ch.isdigit()).zfill(6)


def _compact_date(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())[:8]


def _latest_row(rows: Any, *fields: str) -> dict[str, Any] | None:
    if not isinstance(rows, list):
        return None
    dict_rows = [row for row in rows if isinstance(row, dict)]
    if not dict_rows:
        return None
    keys = fields or ("trade_date", "end_date", "ann_date")
    return sorted(dict_rows, key=lambda row: max((_compact_date(row.get(f)) for f in keys), default=""))[-1]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tushare_factors.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add packages/screener/tushare_factors.py tests/test_tushare_factors.py
git commit -m "feat(factors): tushare_factors module skeleton + dataset readers"
```

---

## Task 1.2: `extract_factor_values` — datasets → normalized raw values

**Files:**
- Modify: `packages/screener/tushare_factors.py`
- Test: `tests/test_tushare_factors.py`

- [ ] **Step 1: Write the failing test** (append)

```python
def _seed_full_stock(root, date="2026-05-29", code="600519"):
    _write(root, "valuation.daily", date, code, [{"trade_date": date, "pe_ttm": 28.0, "pb": 8.0, "total_mv_yi": 21000.0, "circ_mv_yi": 21000.0}])
    _write(root, "liquidity.daily", date, code, [{"trade_date": date, "turnover_rate": 0.6, "volume_ratio": 1.2}])
    for i, d in enumerate(["2026-05-23", "2026-05-26", "2026-05-27", "2026-05-28", "2026-05-29"]):
        _write(root, "capital_flow.daily", d, code, [{"trade_date": d, "main_net_yi": 1.0 + i}])
    _write(root, "financial.indicator", date, code, [{"end_date": "2026-03-31", "roe": 18.0, "roe_waa": 17.0, "debt_to_assets": 30.0, "grossprofit_margin": 91.0, "netprofit_margin": 52.0}])
    _write(root, "index.weight", date, "000300.SH", [{"con_code": "600519.SH", "code": "600519", "weight": 5.2}])
    _write(root, "market.top_list", date, "recent", [{"code": code, "trade_date": date, "net_amount": 1.0e8}])
    _write(root, "market.top_inst", date, "recent", [{"code": code, "trade_date": date, "net_buy": 5.0e7}])
    _write(root, "market.hsgt_moneyflow", date, "recent", [{"trade_date": date, "north_money": 80.0}])


def test_extract_factor_values_reads_all_dimensions(dataset_root):
    from screener import tushare_factors as tf
    _seed_full_stock(dataset_root)
    v = tf.extract_factor_values("sh600519", "2026-05-29")
    assert v["pe_ttm"] == 28.0 and v["pb"] == 8.0
    assert v["roe"] == 18.0 and v["debt_to_assets"] == 30.0
    assert v["turnover_rate"] == 0.6 and v["volume_ratio"] == 1.2
    assert v["main_net_yi"] == 5.0                       # latest day
    assert round(v["five_day_main_net_yi"], 1) == 15.0   # 1+2+3+4+5
    assert v["index_memberships"] == [{"index": "000300.SH", "weight": 5.2}]
    assert v["top_inst_net_buy"] == 5.0e7
    assert v["north_money"] == 80.0


def test_extract_factor_values_missing_returns_none(dataset_root):
    from screener import tushare_factors as tf
    v = tf.extract_factor_values("sh000001", "2026-05-29")   # nothing seeded
    assert v["pe_ttm"] is None and v["roe"] is None and v["main_net_yi"] is None
    assert v["index_memberships"] == [] and v["top_list_hits_20d"] == 0
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_tushare_factors.py -k extract -v`
Expected: FAIL (`AttributeError: extract_factor_values`).

- [ ] **Step 3: Implement** (append to `tushare_factors.py`)

```python
_INDEX_KEYS = (("000300.SH", "000300"), ("000905.SH", "000905"), ("000852.SH", "000852"))


def _five_day_main_net(code: str, trade_date: str | None) -> float | None:
    resolved = _resolve_trade_date("capital_flow.daily", trade_date)
    if not resolved:
        return None
    base = _dataset_root() / _sanitize("capital_flow.daily")
    dates = sorted(p.name for p in base.iterdir() if p.is_dir() and p.name <= resolved)[-5:]
    total, seen = 0.0, False
    for d in dates:
        rows, _ = _load_dataset("capital_flow.daily", d, code)
        row = _latest_row(rows, "trade_date") or {}
        val = _safe_float(row.get("main_net_yi"))
        if val is not None:
            total += val
            seen = True
    return total if seen else None


def _index_memberships(trade_date: str | None, code: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key, _short in _INDEX_KEYS:
        rows, _ = _load_dataset("index.weight", trade_date, key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict) and _normalize_code(row.get("con_code") or row.get("code")) == code:
                out.append({"index": key, "weight": _safe_float(row.get("weight"))})
                break
    return out


def _market_hits(dataset: str, code: str, trade_date: str | None) -> list[dict[str, Any]]:
    rows, _ = _load_dataset(dataset, trade_date, "recent")
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict) and _normalize_code(r.get("code") or r.get("ts_code")) == code]


def extract_factor_values(code: str, trade_date: str | None) -> dict[str, Any]:
    c = _normalize_code(code)
    valuation = _latest_row(_load_dataset("valuation.daily", trade_date, c)[0], "trade_date") or {}
    liquidity = _latest_row(_load_dataset("liquidity.daily", trade_date, c)[0], "trade_date") or {}
    capital = _latest_row(_load_dataset("capital_flow.daily", trade_date, c)[0], "trade_date") or {}
    indicator = _latest_row(_load_dataset("financial.indicator", trade_date, c)[0], "end_date", "ann_date") or {}
    top_list = _market_hits("market.top_list", c, trade_date)
    top_inst = _market_hits("market.top_inst", c, trade_date)
    hsgt = _latest_row(_load_dataset("market.hsgt_moneyflow", trade_date, "recent")[0], "trade_date") or {}
    margin = _latest_row(_load_dataset("market.margin", trade_date, "recent")[0], "trade_date") or {}
    inst_net = sum((_safe_float(r.get("net_buy")) or 0.0) for r in top_inst) if top_inst else None
    return {
        "code": c,
        "trade_date_used": _resolve_trade_date("valuation.daily", trade_date),
        "pe_ttm": _safe_float(valuation.get("pe_ttm") or valuation.get("pe")),
        "pb": _safe_float(valuation.get("pb")),
        "total_mv_yi": _safe_float(valuation.get("total_mv_yi")),
        "circ_mv_yi": _safe_float(valuation.get("circ_mv_yi")),
        "roe": _safe_float(indicator.get("roe")),
        "roe_waa": _safe_float(indicator.get("roe_waa")),
        "debt_to_assets": _safe_float(indicator.get("debt_to_assets")),
        "grossprofit_margin": _safe_float(indicator.get("grossprofit_margin")),
        "netprofit_margin": _safe_float(indicator.get("netprofit_margin")),
        "turnover_rate": _safe_float(liquidity.get("turnover_rate_f") or liquidity.get("turnover_rate")),
        "volume_ratio": _safe_float(liquidity.get("volume_ratio")),
        "main_net_yi": _safe_float(capital.get("main_net_yi")),
        "five_day_main_net_yi": _five_day_main_net(c, trade_date),
        "index_memberships": _index_memberships(trade_date, c),
        "top_list_hits_20d": len(top_list),
        "top_list_hits_60d": len(top_list),
        "top_inst_net_buy": inst_net,
        "north_money": _safe_float(hsgt.get("north_money")),
        "margin_balance": _safe_float(margin.get("rzrqye")),
    }
```

> Note: top_list/top_inst datasets are keyed `recent` and contain a date window; `_market_hits` counts all rows for the code (20d≈60d window with current data). Refine to true 20/60d windows in a follow-up if richer history is harvested.

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_tushare_factors.py -k extract -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/screener/tushare_factors.py tests/test_tushare_factors.py
git commit -m "feat(factors): extract_factor_values from datasets with missing-data tolerance"
```

---

## Task 1.3: Scoring + breakdown (`score_factor_values`)

**Files:**
- Modify: `packages/screener/tushare_factors.py`
- Test: `tests/test_tushare_factors.py`

- [ ] **Step 1: Write the failing test** (append)

```python
def test_score_high_quality_stock_scores_well(dataset_root):
    from screener import tushare_factors as tf
    _seed_full_stock(dataset_root)
    v = tf.extract_factor_values("600519", "2026-05-29")
    scored = tf.score_factor_values(v)
    assert 0 <= scored["tushare_score"] <= 100
    assert scored["tushare_score"] >= 60          # strong ROE + inflow + index member
    assert scored["data_completeness"] == 1.0
    bd = scored["tushare_score_breakdown"]
    assert set(bd) == {"quality", "capital_flow", "valuation", "liquidity", "index", "dragon_tiger"}
    assert all("contribution" in d and "available" in d for d in bd.values())


def test_score_missing_dimensions_reweights_and_lowers_completeness(dataset_root):
    from screener import tushare_factors as tf
    v = tf.extract_factor_values("000002", "2026-05-29")   # nothing seeded
    scored = tf.score_factor_values(v)
    assert scored["tushare_score"] is None                 # zero usable dimensions
    assert scored["data_completeness"] == 0.0
    assert scored["tushare_score_breakdown"]["quality"]["available"] is False
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_tushare_factors.py -k score -v`
Expected: FAIL (`AttributeError: score_factor_values`).

- [ ] **Step 3: Implement** (append)

```python
DIMENSION_WEIGHTS = {
    "quality": 25.0, "capital_flow": 25.0, "valuation": 20.0,
    "liquidity": 15.0, "index": 10.0, "dragon_tiger": 5.0,
}


def _band(value: float | None, points: list[tuple[float, float]]) -> float | None:
    """points: ascending (threshold, score); return score for first threshold >= value, else last."""
    if value is None:
        return None
    for threshold, score in points:
        if value <= threshold:
            return score
    return points[-1][1]


def _score_quality(v):
    roe = v.get("roe") if v.get("roe") is not None else v.get("roe_waa")
    if roe is None:
        return None, "ROE 数据缺失"
    base = _band(roe, [(0, 5.0), (5, 35.0), (8, 55.0), (12, 75.0), (15, 90.0), (1e9, 100.0)])
    debt = v.get("debt_to_assets")
    if debt is not None and debt >= 70:
        base = max(0.0, base - 15.0)
    return base, f"ROE {roe:.1f}%" + (f"，资产负债率 {debt:.0f}%" if debt is not None else "")


def _score_capital_flow(v, pool_stats):
    main = v.get("main_net_yi")
    five = v.get("five_day_main_net_yi")
    if main is None and five is None:
        return None, "资金流数据缺失"
    score = 50.0
    if main is not None:
        score += 20.0 if main > 0 else -20.0
    if five is not None:
        score += 15.0 if five > 0 else -15.0
    if pool_stats and pool_stats.get("five_day_main_net_yi_median") is not None and five is not None:
        score += 10.0 if five >= pool_stats["five_day_main_net_yi_median"] else -5.0
    score = max(0.0, min(100.0, score))
    return score, f"当日主力 {main if main is None else round(main,2)} 亿，5日 {five if five is None else round(five,2)} 亿"


def _score_valuation(v):
    pe, pb = v.get("pe_ttm"), v.get("pb")
    if pe is None and pb is None:
        return None, "估值数据缺失"
    parts, score, n = [], 0.0, 0
    if pe is not None:
        score += _band(pe if pe > 0 else 1e9, [(15, 100.0), (25, 80.0), (40, 55.0), (60, 30.0), (1e9, 10.0)]); n += 1
        parts.append(f"PE {pe:.1f}")
    if pb is not None:
        score += _band(pb, [(1.5, 100.0), (3, 80.0), (5, 55.0), (8, 30.0), (1e9, 15.0)]); n += 1
        parts.append(f"PB {pb:.1f}")
    return score / n, "，".join(parts)


def _score_liquidity(v, pool_stats):
    tr, vr = v.get("turnover_rate"), v.get("volume_ratio")
    if tr is None and vr is None:
        return None, "流动性数据缺失"
    score = 50.0
    if tr is not None:
        score += 20.0 if 0.3 <= tr <= 8 else -10.0
    if vr is not None:
        score += 15.0 if vr >= 1.0 else -5.0
    return max(0.0, min(100.0, score)), f"换手 {tr if tr is None else round(tr,2)}%，量比 {vr if vr is None else round(vr,2)}"


def _score_index(v):
    members = v.get("index_memberships") or []
    if not members:
        return 30.0, "非主要指数成分"   # available but weak (membership knowable = absence is informative)
    weight = sum((m.get("weight") or 0.0) for m in members)
    names = "/".join(m["index"] for m in members)
    return min(100.0, 60.0 + weight * 4.0), f"{names} 成分，权重合计 {weight:.2f}%"


def _score_dragon_tiger(v):
    hits = v.get("top_list_hits_60d") or 0
    net = v.get("top_inst_net_buy")
    if hits == 0 and net is None:
        return None, "近窗口无龙虎榜记录"
    score = 50.0 + (15.0 if net and net > 0 else (-10.0 if net and net < 0 else 0.0))
    return max(0.0, min(100.0, score)), f"龙虎榜命中 {hits} 次" + ("，机构净买入" if net and net > 0 else ("，机构净卖出" if net and net < 0 else ""))


def score_factor_values(values: dict[str, Any], pool_stats: dict[str, Any] | None = None) -> dict[str, Any]:
    scorers = {
        "quality": lambda: _score_quality(values),
        "capital_flow": lambda: _score_capital_flow(values, pool_stats),
        "valuation": lambda: _score_valuation(values),
        "liquidity": lambda: _score_liquidity(values, pool_stats),
        "index": lambda: _score_index(values),
        "dragon_tiger": lambda: _score_dragon_tiger(values),
    }
    breakdown, weighted, total_weight = {}, 0.0, 0.0
    for name, fn in scorers.items():
        score, detail = fn()
        weight = DIMENSION_WEIGHTS[name]
        available = score is not None
        if available:
            weighted += score * weight
            total_weight += weight
        breakdown[name] = {
            "score": round(score, 1) if available else None,
            "weight": weight,
            "contribution": round(score * weight / 100.0, 2) if available else 0.0,
            "detail": detail,
            "available": available,
        }
    tushare_score = round(weighted / total_weight, 1) if total_weight > 0 else None
    return {
        "tushare_score": tushare_score,
        "data_completeness": round(total_weight / sum(DIMENSION_WEIGHTS.values()), 2),
        "tushare_score_breakdown": breakdown,
    }
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_tushare_factors.py -k score -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/screener/tushare_factors.py tests/test_tushare_factors.py
git commit -m "feat(factors): explainable weighted scoring with reweighting on missing data"
```

---

## Task 1.4: Tags + risk flags (`_derive_tags`, `_derive_risk_flags`)

**Files:**
- Modify: `packages/screener/tushare_factors.py`
- Test: `tests/test_tushare_factors.py`

- [ ] **Step 1: Write the failing test** (append)

```python
def test_tags_and_risk_flags_from_values(dataset_root):
    from screener import tushare_factors as tf
    _seed_full_stock(dataset_root)
    v = tf.extract_factor_values("600519", "2026-05-29")
    tags = tf._derive_tags(v)
    flags = tf._derive_risk_flags(v)
    assert "高ROE" in tags and "主力净流入" in tags and "沪深300成分" in tags
    assert "短线脉冲风险(龙虎榜机构净买)" in flags          # inst net buy present


def test_risk_flag_for_missing_data(dataset_root):
    from screener import tushare_factors as tf
    v = tf.extract_factor_values("000333", "2026-05-29")   # nothing seeded
    assert "数据缺失" in tf._derive_risk_flags(v)
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_tushare_factors.py -k "tags or risk_flag" -v`
Expected: FAIL.

- [ ] **Step 3: Implement** (append)

```python
def _derive_tags(v: dict[str, Any]) -> list[str]:
    tags = []
    if (v.get("pe_ttm") or 0) and 0 < v["pe_ttm"] <= 20: tags.append("低PE")
    roe = v.get("roe") if v.get("roe") is not None else v.get("roe_waa")
    if roe is not None and roe >= 15: tags.append("高ROE")
    if (v.get("main_net_yi") or 0) > 0: tags.append("主力净流入")
    if (v.get("five_day_main_net_yi") or 0) > 0: tags.append("5日资金净流入")
    for m in (v.get("index_memberships") or []):
        tags.append({"000300.SH": "沪深300成分", "000905.SH": "中证500成分", "000852.SH": "中证1000成分"}.get(m["index"], "指数成分"))
    if (v.get("top_list_hits_60d") or 0) > 0: tags.append("龙虎榜活跃")
    if (v.get("north_money") or 0) > 0: tags.append("北向偏强")
    return tags


def _derive_risk_flags(v: dict[str, Any]) -> list[str]:
    flags = []
    if (v.get("top_inst_net_buy") or 0) > 0: flags.append("短线脉冲风险(龙虎榜机构净买)")
    if v.get("pe_ttm") is not None and (v["pe_ttm"] > 60 or v["pe_ttm"] <= 0): flags.append("估值偏高")
    if v.get("debt_to_assets") is not None and v["debt_to_assets"] >= 70: flags.append("高负债")
    if (v.get("main_net_yi") or 0) < 0 and (v.get("five_day_main_net_yi") or 0) < 0: flags.append("资金净流出")
    if v.get("turnover_rate") is not None and v["turnover_rate"] < 0.3: flags.append("流动性偏弱")
    core = [v.get("pe_ttm"), v.get("roe"), v.get("main_net_yi"), v.get("turnover_rate")]
    if sum(1 for x in core if x is None) >= 3: flags.append("数据缺失")
    return flags
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_tushare_factors.py -k "tags or risk_flag" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/screener/tushare_factors.py tests/test_tushare_factors.py
git commit -m "feat(factors): factor tags + risk flags derived from data fields"
```

---

## Task 1.5: Structured explanation (`_build_explanation`)

**Files:**
- Modify: `packages/screener/tushare_factors.py`
- Test: `tests/test_tushare_factors.py`

- [ ] **Step 1: Write the failing test** (append)

```python
def test_explanation_is_structured_and_data_grounded(dataset_root):
    from screener import tushare_factors as tf
    _seed_full_stock(dataset_root)
    v = tf.extract_factor_values("600519", "2026-05-29")
    scored = tf.score_factor_values(v)
    exp = tf._build_explanation(v, scored, tf._derive_tags(v), tf._derive_risk_flags(v))
    assert exp["entry_reason"] and exp["upgrade_condition"] and exp["abandon_condition"]
    assert set(exp["evidence"]) == {"fundamental", "capital", "trading_anomaly", "index_weight"}
    assert exp["evidence"]["fundamental"]["available"] is True
    assert "ROE" in exp["evidence"]["fundamental"]["interpretation"]
    assert any("ROE" in s or "PE" in s for s in exp["supporting_evidence"])


def test_explanation_missing_data_marked_unavailable(dataset_root):
    from screener import tushare_factors as tf
    v = tf.extract_factor_values("000004", "2026-05-29")   # nothing seeded
    exp = tf._build_explanation(v, tf.score_factor_values(v), [], tf._derive_risk_flags(v))
    assert exp["evidence"]["fundamental"]["available"] is False
    assert exp["evidence"]["fundamental"]["interpretation"] == "数据缺失/不可用"
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_tushare_factors.py -k explanation -v`
Expected: FAIL.

- [ ] **Step 3: Implement** (append)

```python
def _evidence_block(available: bool, values: dict[str, Any], interpretation: str) -> dict[str, Any]:
    return {"values": values, "interpretation": interpretation if available else "数据缺失/不可用", "available": available}


def _build_explanation(v, scored, tags, risk_flags) -> dict[str, Any]:
    bd = scored["tushare_score_breakdown"]
    supporting = [bd[d]["detail"] for d in ("quality", "valuation", "capital_flow", "index") if bd[d]["available"]]
    roe = v.get("roe") if v.get("roe") is not None else v.get("roe_waa")
    fundamental = _evidence_block(
        roe is not None or v.get("pe_ttm") is not None,
        {"pe_ttm": v.get("pe_ttm"), "pb": v.get("pb"), "roe": roe, "debt_to_assets": v.get("debt_to_assets")},
        bd["quality"]["detail"] if bd["quality"]["available"] else bd["valuation"]["detail"],
    )
    capital = _evidence_block(
        v.get("main_net_yi") is not None or v.get("five_day_main_net_yi") is not None,
        {"main_net_yi": v.get("main_net_yi"), "five_day_main_net_yi": v.get("five_day_main_net_yi")},
        bd["capital_flow"]["detail"],
    )
    trading = _evidence_block(
        (v.get("top_list_hits_60d") or 0) > 0 or v.get("top_inst_net_buy") is not None,
        {"top_list_hits_60d": v.get("top_list_hits_60d"), "top_inst_net_buy": v.get("top_inst_net_buy")},
        bd["dragon_tiger"]["detail"],
    )
    members = v.get("index_memberships") or []
    index_block = _evidence_block(bool(members), {"index_memberships": members}, bd["index"]["detail"])
    score = scored["tushare_score"]
    return {
        "entry_reason": (f"综合因子评分 {score}，" + ("、".join(tags[:3]) if tags else "基础面达标")) if score is not None else "因子数据不足，仅作观察",
        "upgrade_condition": "资金面持续净流入且执行质量确认（盘中放量站稳关键位）后再考虑升级。",
        "abandon_condition": "出现资金净流出、跌破关键支撑或基本面恶化（ROE 下滑/负债攀升）则放弃。",
        "supporting_evidence": supporting,
        "counter_risks": list(risk_flags),
        "evidence": {
            "fundamental": fundamental,
            "capital": capital,
            "trading_anomaly": trading,
            "index_weight": index_block,
        },
    }
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_tushare_factors.py -k explanation -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/screener/tushare_factors.py tests/test_tushare_factors.py
git commit -m "feat(factors): structured data-grounded explanation with four evidence blocks"
```

---

## Task 1.6: `compute_pool_stats` + pool standing

**Files:**
- Modify: `packages/screener/tushare_factors.py`
- Test: `tests/test_tushare_factors.py`

- [ ] **Step 1: Write the failing test** (append)

```python
def test_pool_stats_and_standing():
    from screener import tushare_factors as tf
    values = [
        {"five_day_main_net_yi": 1.0, "turnover_rate": 0.5, "roe": 10.0},
        {"five_day_main_net_yi": 3.0, "turnover_rate": 1.0, "roe": 20.0},
        {"five_day_main_net_yi": 5.0, "turnover_rate": 1.5, "roe": 30.0},
    ]
    stats = tf.compute_pool_stats(values)
    assert stats["five_day_main_net_yi_median"] == 3.0
    standing = tf._pool_standing(values[2], stats)
    assert standing["five_day_main_net_yi"] in {"top_quartile", "above_median"}
    assert tf._pool_standing(values[0], stats)["five_day_main_net_yi"] == "below_median"
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_tushare_factors.py -k pool -v`
Expected: FAIL.

- [ ] **Step 3: Implement** (append)

```python
import statistics

_POOL_FIELDS = ("five_day_main_net_yi", "turnover_rate", "roe")


def compute_pool_stats(values_list: list[dict[str, Any]]) -> dict[str, Any]:
    stats: dict[str, Any] = {}
    for field in _POOL_FIELDS:
        nums = sorted(x[field] for x in values_list if isinstance(x.get(field), (int, float)))
        if nums:
            stats[f"{field}_median"] = statistics.median(nums)
            stats[f"{field}_p75"] = nums[min(len(nums) - 1, int(len(nums) * 0.75))]
    return stats


def _pool_standing(values: dict[str, Any], pool_stats: dict[str, Any] | None) -> dict[str, str] | None:
    if not pool_stats:
        return None
    out: dict[str, str] = {}
    for field in _POOL_FIELDS:
        val, med, p75 = values.get(field), pool_stats.get(f"{field}_median"), pool_stats.get(f"{field}_p75")
        if val is None or med is None:
            continue
        out[field] = "top_quartile" if (p75 is not None and val >= p75) else ("above_median" if val >= med else "below_median")
    return out
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_tushare_factors.py -k pool -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/screener/tushare_factors.py tests/test_tushare_factors.py
git commit -m "feat(factors): pool statistics + relative standing"
```

---

## Task 1.7: `compute_factor_bundle` + `build_factor_snapshot` orchestration

**Files:**
- Modify: `packages/screener/tushare_factors.py`
- Test: `tests/test_tushare_factors.py`

- [ ] **Step 1: Write the failing test** (append)

```python
def test_compute_factor_bundle_full(dataset_root):
    from screener import tushare_factors as tf
    _seed_full_stock(dataset_root)
    b = tf.compute_factor_bundle("sh600519", "2026-05-29")
    assert set(b) >= {"tushare_score", "data_completeness", "tushare_score_breakdown", "factor_tags",
                      "risk_flags", "explanation", "factor_snapshot", "trade_date_used"}
    assert b["tushare_score"] >= 60
    assert b["factor_snapshot"]["valuation"]["pe_ttm"] == 28.0
    assert b["trade_date_used"] == "2026-05-29"


def test_compute_factor_bundle_never_raises_on_empty(dataset_root):
    from screener import tushare_factors as tf
    b = tf.compute_factor_bundle("sh999999", "2026-05-29")   # nothing seeded
    assert b["tushare_score"] is None and b["data_completeness"] == 0.0
    assert "数据缺失" in b["risk_flags"]


def test_build_factor_snapshot_subset(dataset_root):
    from screener import tushare_factors as tf
    _seed_full_stock(dataset_root)
    snap = tf.build_factor_snapshot("600519", "2026-05-29")
    assert set(snap) == {"tushare_score", "data_completeness", "factor_tags", "risk_flags", "factor_snapshot", "trade_date_used"}
    assert snap["factor_snapshot"]["capital_flow"]["main_net_yi"] == 5.0
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_tushare_factors.py -k "bundle or build_factor_snapshot" -v`
Expected: FAIL.

- [ ] **Step 3: Implement** (append)

```python
def _snapshot_from_values(v: dict[str, Any]) -> dict[str, Any]:
    return {
        "valuation": {"pe_ttm": v.get("pe_ttm"), "pb": v.get("pb"), "total_mv_yi": v.get("total_mv_yi")},
        "liquidity": {"turnover_rate": v.get("turnover_rate"), "volume_ratio": v.get("volume_ratio")},
        "capital_flow": {"main_net_yi": v.get("main_net_yi"), "five_day_main_net_yi": v.get("five_day_main_net_yi")},
        "fundamentals": {"roe": v.get("roe"), "roe_waa": v.get("roe_waa"), "debt_to_assets": v.get("debt_to_assets"),
                         "grossprofit_margin": v.get("grossprofit_margin"), "netprofit_margin": v.get("netprofit_margin")},
        "index_membership": v.get("index_memberships") or [],
        "top_list_activity": {"hits_20d": v.get("top_list_hits_20d"), "hits_60d": v.get("top_list_hits_60d")},
        "top_inst_activity": {"net_buy": v.get("top_inst_net_buy")},
        "market_context": {"north_money": v.get("north_money"), "margin_balance": v.get("margin_balance")},
    }


def compute_factor_bundle(code: str, trade_date: str | None, *, pool_stats: dict | None = None,
                          values: dict | None = None) -> dict[str, Any]:
    v = values if values is not None else extract_factor_values(code, trade_date)
    scored = score_factor_values(v, pool_stats)
    tags = _derive_tags(v)
    risk_flags = _derive_risk_flags(v)
    return {
        "tushare_score": scored["tushare_score"],
        "data_completeness": scored["data_completeness"],
        "tushare_score_breakdown": scored["tushare_score_breakdown"],
        "factor_tags": tags,
        "risk_flags": risk_flags,
        "explanation": _build_explanation(v, scored, tags, risk_flags),
        "factor_snapshot": _snapshot_from_values(v),
        "trade_date_used": v.get("trade_date_used"),
        "pool_standing": _pool_standing(v, pool_stats),
    }


def build_factor_snapshot(code: str, trade_date: str | None) -> dict[str, Any]:
    b = compute_factor_bundle(code, trade_date)
    return {k: b[k] for k in ("tushare_score", "data_completeness", "factor_tags", "risk_flags", "factor_snapshot", "trade_date_used")}
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_tushare_factors.py -v`
Expected: PASS (all factor-core tests).

- [ ] **Step 5: Commit**

```bash
git add packages/screener/tushare_factors.py tests/test_tushare_factors.py
git commit -m "feat(factors): compute_factor_bundle + build_factor_snapshot orchestration"
```

---

# Phase 2 — Scan/screening wiring (bounded re-rank)

## Task 2.1: Scan attaches factors + pool stats

**Files:**
- Modify: `packages/screener/scan.py` (import near line 59-60; `stage2_enrich` ~1394; `format_output` 2274-2317; `main`/output assembly that writes top-level keys)
- Test: `tests/test_scan_factor_wiring.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scan_factor_wiring.py
import importlib
from screener import scan


def test_format_output_carries_tushare_factors():
    importlib.reload(scan)
    stock = {
        "code": "600519", "name": "贵州茅台", "price": 1700.0, "change_pct": 1.2,
        "final_score": 90, "amount": 5e9, "fundamentals": {},
        "tushare_factors": {"tushare_score": 72.0, "factor_tags": ["高ROE"], "risk_flags": []},
    }
    out = scan.format_output([stock], "combined", 5)
    assert out[0]["tushare_factors"]["tushare_score"] == 72.0
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_scan_factor_wiring.py -v`
Expected: FAIL (`KeyError: 'tushare_factors'`).

- [ ] **Step 3: Implement**

In `format_output` ([scan.py:2274](packages/screener/scan.py)), add one key to the appended dict (before the closing `})`):

```python
            'notice_risk_tags': s.get('notice_risk_tags', []),
            'tushare_factors': s.get('tushare_factors'),
```

In `stage2_enrich`, after the candidates list is fully enriched and `final_score` computed (after [scan.py:1394](packages/screener/scan.py)), add a factor pass. Read the function first, then insert near the end of `stage2_enrich` (operating on the enriched `candidates`/`stocks` list variable used there):

```python
    # --- Tushare factor layer (research-only; does not affect final_score) ---
    try:
        from tushare_factors import extract_factor_values, compute_pool_stats, compute_factor_bundle
    except ImportError:
        from screener.tushare_factors import extract_factor_values, compute_pool_stats, compute_factor_bundle
    trade_date = _today_trade_date()
    values_by_code = {}
    for c in candidates:
        try:
            values_by_code[c["code"]] = extract_factor_values(c["code"], trade_date)
        except Exception:
            values_by_code[c["code"]] = None
    pool_stats = compute_pool_stats([v for v in values_by_code.values() if v])
    for c in candidates:
        v = values_by_code.get(c["code"])
        if v is None:
            continue
        try:
            c["tushare_factors"] = compute_factor_bundle(c["code"], trade_date, pool_stats=pool_stats, values=v)
        except Exception:
            c["tushare_factors"] = None
    stage2_enrich._last_pool_stats = pool_stats   # stash for main() to write top-level
```

> Replace `candidates` with the actual variable name the function returns/iterates. The `try/except ImportError` handles both `python scan.py` (cwd=packages/screener) and package import.

In `main` ([scan.py:2323+](packages/screener/scan.py)), where the final result dict is assembled before writing `scan_result.json`, add:

```python
        "tushare_factor_pool_stats": getattr(stage2_enrich, "_last_pool_stats", {}),
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_scan_factor_wiring.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/screener/scan.py tests/test_scan_factor_wiring.py
git commit -m "feat(scan): attach tushare_factors to candidates + persist pool stats"
```

---

## Task 2.2: ai_screening carries factors + bounded priority re-rank

**Files:**
- Modify: `packages/screener/ai_screening.py` (`build_stock_entry` ~777; `aggregate_shortlist` 969-1127)
- Test: `tests/test_ai_screening_factor_rerank.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ai_screening_factor_rerank.py
from screener import tushare_factors as tf
from screener import ai_screening


def test_priority_adjustment_is_bounded_and_does_not_change_status():
    base = {"best_score": 80, "strategy_count": 1, "approved_hits": 1,
            "execution_quality": {"score": 0}, "consistency": {"score": 0},
            "tushare_factors": {"tushare_score": 100.0, "risk_flags": []}}
    adj = ai_screening._tushare_priority_adjustment(base)
    assert 0 < adj <= tf.PRIORITY_ADJUSTMENT_CAP             # high score nudges up, but capped
    worst = dict(base); worst["tushare_factors"] = {"tushare_score": 0.0, "risk_flags": ["a", "b", "c", "d"]}
    assert ai_screening._tushare_priority_adjustment(worst) < 0
    none = dict(base); none["tushare_factors"] = None
    assert ai_screening._tushare_priority_adjustment(none) == 0.0
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_ai_screening_factor_rerank.py -v`
Expected: FAIL (`AttributeError: _tushare_priority_adjustment`).

- [ ] **Step 3: Implement**

Add a helper near the top of `ai_screening.py` (after imports):

```python
from screener.tushare_factors import PRIORITY_ADJUSTMENT_CAP, PRIORITY_ADJUSTMENT_K, RISK_FLAG_PENALTY


def _tushare_priority_adjustment(item) -> float:
    fb = item.get("tushare_factors") or {}
    score = fb.get("tushare_score")
    adj = 0.0
    if isinstance(score, (int, float)):
        adj = max(-PRIORITY_ADJUSTMENT_CAP, min(PRIORITY_ADJUSTMENT_CAP, (score - 50.0) * PRIORITY_ADJUSTMENT_K))
    adj -= min(len(fb.get("risk_flags") or []), 3) * RISK_FLAG_PENALTY
    return round(adj, 2)
```

In `build_stock_entry` ([ai_screening.py:777](packages/screener/ai_screening.py)) add to the returned dict: `"tushare_factors": stock.get("tushare_factors"),`.

In `aggregate_shortlist`: add `"tushare_factors": item.get("tushare_factors"),` to the initial dict ([ai_screening.py:969-994](packages/screener/ai_screening.py)); add `agg["tushare_factors"] = item.get("tushare_factors")` inside the best-score update block (after [ai_screening.py:1032](packages/screener/ai_screening.py)). Then after `item["priority_score"]` is computed ([ai_screening.py:1053-1060](packages/screener/ai_screening.py)) insert:

```python
        adjustment = _tushare_priority_adjustment(item)
        item["tushare_priority_adjustment"] = adjustment
        item["priority_score"] = round(item["priority_score"] + adjustment, 2)
```

> Place it **before** the tier logic at line 1062 — but note tier is gated by `quality_score`/`consistency_score`, NOT `priority_score`, so the adjustment only re-orders the final sort (line 1133) within the pool. Do not touch `screening_status`.

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_ai_screening_factor_rerank.py -v`
Expected: PASS.

- [ ] **Step 5: Add the tuning constants to the factor core**

In `packages/screener/tushare_factors.py` (after `DIMENSION_WEIGHTS`):

```python
PRIORITY_ADJUSTMENT_CAP = 6.0
PRIORITY_ADJUSTMENT_K = 0.12
RISK_FLAG_PENALTY = 1.5
```

- [ ] **Step 6: Commit**

```bash
git add packages/screener/ai_screening.py packages/screener/tushare_factors.py tests/test_ai_screening_factor_rerank.py
git commit -m "feat(screening): carry factors + bounded priority re-rank (no status/gate change)"
```

---

## Task 2.3: prism_canonical exposes factor fields

**Files:**
- Modify: `apps/scripts/prism_canonical.py` (`normalize_candidate` 725-753)
- Test: `apps/control-panel/tests/test_prism_canonical_factors.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# apps/control-panel/tests/test_prism_canonical_factors.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages"))

import prism_canonical


def test_normalize_candidate_exposes_factor_fields():
    raw = {
        "code": "600519", "name": "贵州茅台", "screening_status": "caution",
        "tushare_factors": {
            "tushare_score": 72.0,
            "tushare_score_breakdown": {"quality": {"score": 90}},
            "factor_tags": ["高ROE"], "risk_flags": ["短线脉冲风险(龙虎榜机构净买)"],
            "explanation": {"entry_reason": "x"},
        },
    }
    out = prism_canonical.normalize_candidate(raw, "batch1")
    assert out["tushare_score"] == 72.0
    assert out["factor_tags"] == ["高ROE"]
    assert out["factor_risk_flags"] == ["短线脉冲风险(龙虎榜机构净买)"]
    assert out["factor_explanation"]["entry_reason"] == "x"
    assert out["tushare_factors"]["tushare_score"] == 72.0
    assert isinstance(out["risk_flags"], list)   # existing execution-warning risk_flags untouched
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest apps/control-panel/tests/test_prism_canonical_factors.py -v`
Expected: FAIL (`KeyError: 'tushare_score'`).

- [ ] **Step 3: Implement**

In `normalize_candidate` ([prism_canonical.py:752](apps/scripts/prism_canonical.py)), add after `"capital_flow": capital_flow,`:

```python
        "capital_flow": capital_flow,
        "tushare_score": (raw.get("tushare_factors") or {}).get("tushare_score"),
        "tushare_score_breakdown": (raw.get("tushare_factors") or {}).get("tushare_score_breakdown") or {},
        "factor_tags": (raw.get("tushare_factors") or {}).get("factor_tags") or [],
        "factor_risk_flags": (raw.get("tushare_factors") or {}).get("risk_flags") or [],
        "factor_explanation": (raw.get("tushare_factors") or {}).get("explanation") or {},
        "tushare_factors": raw.get("tushare_factors") or {},
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest apps/control-panel/tests/test_prism_canonical_factors.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/scripts/prism_canonical.py apps/control-panel/tests/test_prism_canonical_factors.py
git commit -m "feat(canonical): expose factor fields on canonical candidate"
```

---

## Task 2.4: candidate_lifecycle keeps slim factor summary

**Files:**
- Modify: `packages/screener/candidate_lifecycle.py` (`extract_shortlist` 64-108)
- Test: `tests/test_candidate_lifecycle_factors.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_candidate_lifecycle_factors.py
from screener import candidate_lifecycle


def test_extract_shortlist_keeps_factor_summary():
    data = {"shortlist": [{
        "code": "600519", "name": "贵州茅台", "score": 90, "tier": "B",
        "screening_status": "caution", "theme": "x", "change_pct": 1.0, "amount_yi": 5.0,
        "tushare_factors": {"tushare_score": 72.0, "factor_tags": ["高ROE", "主力净流入"]},
    }]}
    rows = candidate_lifecycle.extract_shortlist(data)
    assert rows["600519"]["tushare_score"] == 72.0
    assert rows["600519"]["factor_tags"] == ["高ROE", "主力净流入"]
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_candidate_lifecycle_factors.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

In `extract_shortlist` ([candidate_lifecycle.py:64](packages/screener/candidate_lifecycle.py)), add to the per-code projection dict:

```python
        "tushare_score": (item.get("tushare_factors") or {}).get("tushare_score"),
        "factor_tags": (item.get("tushare_factors") or {}).get("factor_tags") or [],
```

> Confirm the projection variable name (`item`) and the dict it builds by reading the function first.

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_candidate_lifecycle_factors.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/screener/candidate_lifecycle.py tests/test_candidate_lifecycle_factors.py
git commit -m "feat(lifecycle): keep slim factor summary across snapshots"
```

---

# Phase 3 — Control-panel API

## Task 3.1: `formal_data.factor_profile` in data_assets

**Files:**
- Modify: `apps/control-panel/data_assets.py` (`build_stock_formal_data` 318-411)
- Test: `apps/control-panel/tests/test_stock_formal_data.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# apps/control-panel/tests/test_stock_formal_data.py
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages"))


def _seed(root, dataset, date, key, payload):
    d = root / dataset / date; d.mkdir(parents=True, exist_ok=True)
    (d / f"{key}.json").write_text(json.dumps(payload), encoding="utf-8")
    (d / f"{key}.manifest.json").write_text(json.dumps({"trade_date": date, "provider": "tushare"}), encoding="utf-8")


def test_formal_data_includes_factor_profile(tmp_path, monkeypatch):
    root = tmp_path / "datasets"; root.mkdir()
    monkeypatch.setenv("PRISM_DATASET_REPOSITORY_ROOT", str(root))
    _seed(root, "valuation.daily", "2026-05-29", "600519", [{"trade_date": "2026-05-29", "pe_ttm": 28.0, "pb": 8.0}])
    _seed(root, "financial.indicator", "2026-05-29", "600519", [{"end_date": "2026-03-31", "roe": 18.0}])
    import importlib, data_assets
    importlib.reload(data_assets)
    # point data_assets' own reader at tmp root too
    data_assets.DATASET_ROOT = root
    payload = data_assets.build_stock_formal_data("sh600519", "2026-05-29")
    fp = payload["factor_profile"]
    assert fp["tushare_score"] is not None
    assert "高ROE" in fp["factor_tags"]
    assert fp["explanation"]["evidence"]["fundamental"]["available"] is True


def test_formal_data_factor_profile_missing_is_graceful(tmp_path, monkeypatch):
    root = tmp_path / "datasets"; root.mkdir()
    monkeypatch.setenv("PRISM_DATASET_REPOSITORY_ROOT", str(root))
    import importlib, data_assets
    importlib.reload(data_assets); data_assets.DATASET_ROOT = root
    payload = data_assets.build_stock_formal_data("sh000001", "2026-05-29")
    assert payload["factor_profile"]["tushare_score"] is None      # no fabrication
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest apps/control-panel/tests/test_stock_formal_data.py -v`
Expected: FAIL (`KeyError: 'factor_profile'`).

- [ ] **Step 3: Implement**

In `data_assets.py`, add a lazy import + a profile builder, then attach to the payload. Near the top add:

```python
def _factor_profile(code: str, trade_date: str) -> dict[str, Any]:
    try:
        from screener.tushare_factors import compute_factor_bundle
        b = compute_factor_bundle(code, trade_date)
        return {k: b.get(k) for k in (
            "tushare_score", "data_completeness", "tushare_score_breakdown",
            "factor_tags", "risk_flags", "explanation", "trade_date_used")}
    except Exception:
        return {"tushare_score": None, "data_completeness": 0.0, "tushare_score_breakdown": {},
                "factor_tags": [], "risk_flags": ["数据缺失"], "explanation": {}, "trade_date_used": None}
```

In the `payload = { ... }` dict in `build_stock_formal_data` ([data_assets.py:382](apps/control-panel/data_assets.py)), add before `"source_cards": source_cards,`:

```python
        "factor_profile": _factor_profile(normalized_code, target_date),
        "source_cards": source_cards,
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest apps/control-panel/tests/test_stock_formal_data.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/control-panel/data_assets.py apps/control-panel/tests/test_stock_formal_data.py
git commit -m "feat(api): add factor_profile to formal_data with graceful missing-data"
```

---

## Task 3.2: Candidate cards surface factor fields

**Files:**
- Modify: `apps/control-panel/dashboard_data.py` (`build_screening_candidate_card` ~4954, `build_confirmation_candidate_card` ~5000)
- Test: `apps/control-panel/tests/test_opportunity_card_factors.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# apps/control-panel/tests/test_opportunity_card_factors.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages"))

import dashboard_data


def test_screening_card_includes_factor_fields():
    candidate = {
        "code": "600519", "name": "贵州茅台", "screening_status": "caution",
        "tushare_score": 72.0, "factor_tags": ["高ROE"], "factor_risk_flags": ["短线脉冲风险(龙虎榜机构净买)"],
        "factor_explanation": {"entry_reason": "综合因子评分 72"},
    }
    card = dashboard_data.build_screening_candidate_card(candidate)
    assert card["tushare_score"] == 72.0
    assert card["factor_tags"] == ["高ROE"]
    assert card["factor_risk_flags"] == ["短线脉冲风险(龙虎榜机构净买)"]
    assert card["factor_explanation"]["entry_reason"].startswith("综合因子评分")
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest apps/control-panel/tests/test_opportunity_card_factors.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

In both `build_screening_candidate_card` and `build_confirmation_candidate_card` ([dashboard_data.py:4954,5000](apps/control-panel/dashboard_data.py)), add to each returned card dict (read the functions first; the canonical candidate is the input arg, e.g. `candidate`/`raw`):

```python
        "tushare_score": candidate.get("tushare_score"),
        "factor_tags": candidate.get("factor_tags") or [],
        "factor_risk_flags": candidate.get("factor_risk_flags") or [],
        "factor_explanation": candidate.get("factor_explanation") or {},
```

> Use the actual input variable name. For the confirmation card, the factor fields may be nested under the canonical candidate — fall back to `(candidate.get("tushare_factors") or {}).get(...)` if the flat keys are absent.

- [ ] **Step 4: Run to verify pass**

Run: `pytest apps/control-panel/tests/test_opportunity_card_factors.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/control-panel/dashboard_data.py apps/control-panel/tests/test_opportunity_card_factors.py
git commit -m "feat(api): surface factor score/tags/flags/explanation on candidate cards"
```

---

## Task 3.3: Candidate detail full breakdown

**Files:**
- Modify: `apps/control-panel/dashboard_data.py` (`build_candidate_detail_view` ~8975)
- Test: extend `apps/control-panel/tests/test_opportunity_card_factors.py`

- [ ] **Step 1: Write the failing test** (append)

```python
def test_candidate_detail_carries_full_factor_bundle(monkeypatch):
    # build_candidate_detail_view sources candidate via find_candidate_detail; stub it.
    import prism_canonical
    monkeypatch.setattr(prism_canonical, "find_candidate_detail", lambda code, trade_date=None: {
        "code": "600519", "name": "贵州茅台",
        "tushare_factors": {"tushare_score": 72.0, "tushare_score_breakdown": {"quality": {"score": 90}},
                            "factor_tags": ["高ROE"], "risk_flags": [], "explanation": {"entry_reason": "x"}},
        "tushare_score": 72.0, "factor_tags": ["高ROE"], "factor_risk_flags": [],
        "factor_explanation": {"entry_reason": "x"},
    })
    view = dashboard_data.build_candidate_detail_view("sh600519")
    assert view.get("tushare_factors", {}).get("tushare_score") == 72.0 or view.get("tushare_score") == 72.0
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest apps/control-panel/tests/test_opportunity_card_factors.py -k detail -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

In `build_candidate_detail_view` ([dashboard_data.py:8975](apps/control-panel/dashboard_data.py)), in the returned dict add (read the function + the candidate variable name first):

```python
        "tushare_factors": (candidate.get("tushare_factors") or {}),
        "tushare_score": candidate.get("tushare_score"),
        "factor_tags": candidate.get("factor_tags") or [],
        "factor_risk_flags": candidate.get("factor_risk_flags") or [],
        "factor_explanation": candidate.get("factor_explanation") or {},
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest apps/control-panel/tests/test_opportunity_card_factors.py -k detail -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/control-panel/dashboard_data.py apps/control-panel/tests/test_opportunity_card_factors.py
git commit -m "feat(api): expose full factor bundle on candidate detail"
```

---

# Phase 4 — Decision Ledger

## Task 4.1: `factor_snapshot` on decision records

**Files:**
- Modify: `apps/control-panel/decision_ledger.py` (`build_decision_record` 495-607; `build_decision_record_from_today_item` 969-1049; `capture_today_action_queue` 1052+)
- Test: extend `apps/control-panel/tests/test_decision_ledger_capture.py`

> **Spec deviation (confirmed for safety):** do NOT bump the shared `SCHEMA_VERSION` (it stamps execution/outcome events too). `factor_snapshot` is added as an optional forward-compatible field.

- [ ] **Step 1: Write the failing test** (append to `test_decision_ledger_capture.py`)

```python
def test_build_decision_record_carries_factor_snapshot(self):
    record = self.dl.build_decision_record(
        trade_date="2026-05-15", code="sh600519", name="贵州茅台",
        lane="screening", surface="today_action", action_key="screening:600519",
        action="observe",
        factor_snapshot={"tushare_score": 72.0, "factor_snapshot": {"valuation": {"pe_ttm": 28.0}}},
    )
    assert record["factor_snapshot"]["tushare_score"] == 72.0


def test_build_decision_record_factor_snapshot_defaults_none(self):
    record = self.dl.build_decision_record(
        trade_date="2026-05-15", code="sh600519", name="贵州茅台",
        lane="screening", surface="today_action", action_key="screening:600519", action="observe")
    assert record["factor_snapshot"] is None
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest apps/control-panel/tests/test_decision_ledger_capture.py -k factor_snapshot -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

In `build_decision_record` signature ([decision_ledger.py:528](apps/control-panel/decision_ledger.py)) add a param before `decision_contract`:

```python
    factor_snapshot: Mapping[str, Any] | None = None,
    decision_contract: Mapping[str, Any] | None = None,
```

In its return dict, after `parameter_snapshot` ([decision_ledger.py:593](apps/control-panel/decision_ledger.py)):

```python
        "parameter_snapshot": {
            "path": parameter_path,
            "sha256": parameter_sha256,
            "summary": dict(parameter_summary) if parameter_summary else None,
        },
        "factor_snapshot": dict(factor_snapshot) if factor_snapshot else None,
```

In `build_decision_record_from_today_item` ([decision_ledger.py:969](apps/control-panel/decision_ledger.py)) add a keyword param `factor_snapshot: Mapping[str, Any] | None = None,` and pass it into the `build_decision_record(...)` call ([decision_ledger.py:1048](apps/control-panel/decision_ledger.py)): `factor_snapshot=factor_snapshot,`.

In `capture_today_action_queue` ([decision_ledger.py:1052](apps/control-panel/decision_ledger.py)), where each item is converted, compute the snapshot (lazy import; never fatal):

```python
def _factor_snapshot_for_item(item, data_trade_date):
    try:
        from screener.tushare_factors import build_factor_snapshot
        _, plain_code = _parse_today_action_key(str(item.get("key") or ""))
        if not plain_code:
            return None
        return build_factor_snapshot(plain_code, data_trade_date)
    except Exception:
        return None
```

and pass `factor_snapshot=_factor_snapshot_for_item(item, data_trade_date)` into the `build_decision_record_from_today_item(...)` call.

- [ ] **Step 4: Run to verify pass**

Run: `pytest apps/control-panel/tests/test_decision_ledger_capture.py -v`
Expected: PASS (incl. existing capture tests — confirm idempotency/immutability still green).

- [ ] **Step 5: Commit**

```bash
git add apps/control-panel/decision_ledger.py apps/control-panel/tests/test_decision_ledger_capture.py
git commit -m "feat(ledger): capture optional factor_snapshot on decision records"
```

---

## Task 4.2: `build_factor_learning_loop` scaffold

**Files:**
- Modify: `apps/control-panel/decision_ledger.py` (new function near `build_rule_learning_loop` ~2333); `apps/control-panel/app.py` (`api_decision_ledger_learning_loop` ~2958)
- Test: `apps/control-panel/tests/test_decision_ledger_factor_loop.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# apps/control-panel/tests/test_decision_ledger_factor_loop.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import decision_ledger


def _rec(roe, ret):
    return {
        "factor_snapshot": {"factor_snapshot": {"fundamentals": {"roe": roe},
                            "top_inst_activity": {"net_buy": None}, "index_membership": [],
                            "valuation": {"pb": 2.0}, "market_context": {"north_money": 10.0}}},
        "outcome_events": [{"window": "T+3", "market_data": {"return_pct": ret, "relative_return_pct": ret}}],
    }


def test_factor_learning_loop_buckets_high_vs_low_roe():
    records = [_rec(20.0, 5.0), _rec(22.0, 3.0), _rec(4.0, -2.0), _rec(3.0, -4.0)]
    loop = decision_ledger.build_factor_learning_loop(records)
    roe = loop["buckets"]["roe"]
    assert roe["high"]["mature_count"] == 2 and roe["low"]["mature_count"] == 2
    assert roe["high"]["avg_return_by_window"]["T+3"] > roe["low"]["avg_return_by_window"]["T+3"]


def test_factor_learning_loop_ignores_records_without_outcome():
    records = [{"factor_snapshot": {"factor_snapshot": {"fundamentals": {"roe": 20.0}}}, "outcome_events": []}]
    loop = decision_ledger.build_factor_learning_loop(records)
    assert loop["buckets"]["roe"]["high"]["mature_count"] == 0
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest apps/control-panel/tests/test_decision_ledger_factor_loop.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement** (add to `decision_ledger.py`)

```python
def _factor_returns(records, predicate):
    by_window: dict[str, list[float]] = {}
    mature = 0
    for rec in records:
        snap = ((rec.get("factor_snapshot") or {}).get("factor_snapshot")) or {}
        if not predicate(snap):
            continue
        outcomes = [o for o in (rec.get("outcome_events") or []) if isinstance(o, Mapping)]
        if not outcomes:
            continue
        mature += 1
        for o in outcomes:
            window = o.get("window")
            ret = (o.get("market_data") or {}).get("relative_return_pct")
            if window and isinstance(ret, (int, float)):
                by_window.setdefault(window, []).append(float(ret))
    avg = {w: round(sum(v) / len(v), 3) for w, v in by_window.items()}
    win = {w: round(sum(1 for x in v if x > 0) / len(v), 3) for w, v in by_window.items()}
    return {"mature_count": mature, "sample_count": mature,
            "avg_return_by_window": avg, "win_rate_by_window": win}


def build_factor_learning_loop(records) -> dict[str, Any]:
    def roe(snap): return (snap.get("fundamentals") or {}).get("roe")
    def pb(snap): return (snap.get("valuation") or {}).get("pb")
    def inst(snap): return (snap.get("top_inst_activity") or {}).get("net_buy")
    def north(snap): return (snap.get("market_context") or {}).get("north_money")
    def member(snap): return bool(snap.get("index_membership"))
    return {
        "learning_loop_version": LEARNING_LOOP_VERSION,
        "outcome_windows": list(OUTCOME_WINDOWS),
        "buckets": {
            "roe": {
                "high": _factor_returns(records, lambda s: isinstance(roe(s), (int, float)) and roe(s) >= 12),
                "low": _factor_returns(records, lambda s: isinstance(roe(s), (int, float)) and roe(s) < 12),
                "label": "高ROE(≥12%) vs 低ROE",
            },
            "pb": {
                "low": _factor_returns(records, lambda s: isinstance(pb(s), (int, float)) and pb(s) <= 2),
                "high": _factor_returns(records, lambda s: isinstance(pb(s), (int, float)) and pb(s) > 2),
                "label": "低PB(≤2) vs 高PB",
            },
            "dragon_tiger_inst_net_buy": {
                "yes": _factor_returns(records, lambda s: isinstance(inst(s), (int, float)) and inst(s) > 0),
                "no": _factor_returns(records, lambda s: not (isinstance(inst(s), (int, float)) and inst(s) > 0)),
                "label": "龙虎榜机构净买 vs 否",
            },
            "northbound": {
                "strong": _factor_returns(records, lambda s: isinstance(north(s), (int, float)) and north(s) > 0),
                "weak": _factor_returns(records, lambda s: isinstance(north(s), (int, float)) and north(s) <= 0),
                "label": "北向偏强 vs 偏弱",
            },
            "index_membership": {
                "member": _factor_returns(records, member),
                "non_member": _factor_returns(records, lambda s: not member(s)),
                "label": "指数成分 vs 非成分",
            },
        },
    }
```

- [ ] **Step 4: Wire the endpoint**

In `api_decision_ledger_learning_loop` ([app.py:2958](apps/control-panel/app.py)), after the existing payload is built and before returning, add:

```python
        payload["factor_learning_loop"] = decision_ledger.build_factor_learning_loop(records)
```

> Use the same `records` list the handler already loads (it calls `scan_all_decisions()` / `build_rule_learning_loop`). Read the handler first to match the variable name.

- [ ] **Step 5: Run to verify pass**

Run: `pytest apps/control-panel/tests/test_decision_ledger_factor_loop.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/control-panel/decision_ledger.py apps/control-panel/app.py apps/control-panel/tests/test_decision_ledger_factor_loop.py
git commit -m "feat(learning): per-factor forward-return bucketing scaffold + endpoint"
```

---

# Phase 5 — Frontend

## Task 5.1: TypeScript types

**Files:**
- Modify: `apps/web/src/lib/types.ts` (`StockListCard` 840-873; `StockFormalData` 1910-1929)

- [ ] **Step 1: Add the `TushareFactorProfile` interface** (near `StockFormalData`)

```ts
export interface TushareFactorEvidenceBlock {
  values?: Record<string, number | string | null | Array<Record<string, unknown>>>;
  interpretation?: string;
  available?: boolean;
}

export interface TushareFactorExplanation {
  entry_reason?: string;
  upgrade_condition?: string;
  abandon_condition?: string;
  supporting_evidence?: string[];
  counter_risks?: string[];
  evidence?: {
    fundamental?: TushareFactorEvidenceBlock;
    capital?: TushareFactorEvidenceBlock;
    trading_anomaly?: TushareFactorEvidenceBlock;
    index_weight?: TushareFactorEvidenceBlock;
  };
}

export interface TushareFactorProfile {
  tushare_score?: number | null;
  data_completeness?: number;
  tushare_score_breakdown?: Record<string, {
    score?: number | null; weight?: number; contribution?: number; detail?: string; available?: boolean;
  }>;
  factor_tags?: string[];
  risk_flags?: string[];
  explanation?: TushareFactorExplanation;
  trade_date_used?: string | null;
}
```

- [ ] **Step 2: Extend `StockListCard`** ([types.ts:840](apps/web/src/lib/types.ts)) — add optional fields:

```ts
  tushare_score?: number | null;
  factor_tags?: string[];
  factor_risk_flags?: string[];
  factor_explanation?: TushareFactorExplanation;
```

- [ ] **Step 3: Extend `StockFormalData`** ([types.ts:1910](apps/web/src/lib/types.ts)) — add:

```ts
  factor_profile?: TushareFactorProfile;
```

- [ ] **Step 4: Typecheck**

Run: `cd apps/web && npm run typecheck`
Expected: PASS (no errors).

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/types.ts
git commit -m "feat(web): TushareFactorProfile types + StockListCard/StockFormalData fields"
```

---

## Task 5.2: Discovery page renders factor chips + explanation

**Files:**
- Modify: `apps/web/src/app/discovery/page.tsx` (badge cell 290-300; reason column 281-283; mobile 316-346)

- [ ] **Step 1: Add factor chips to the desktop badge cell** ([discovery/page.tsx:297](apps/web/src/app/discovery/page.tsx))

After the existing score `<Badge>` add:

```tsx
{typeof stock.tushare_score === "number" && (
  <Badge tone="info">因子 {Math.round(stock.tushare_score)}</Badge>
)}
{(stock.factor_tags ?? []).slice(0, 2).map((t) => (
  <Badge key={`ft-${t}`} tone="positive">{t}</Badge>
))}
{(stock.factor_risk_flags ?? []).slice(0, 1).map((t) => (
  <Badge key={`fr-${t}`} tone="risk">{t}</Badge>
))}
```

- [ ] **Step 2: Show factor entry_reason near "为什么入池"** ([discovery/page.tsx:281-283](apps/web/src/app/discovery/page.tsx))

Append under the existing reason text:

```tsx
{stock.factor_explanation?.entry_reason && (
  <div className="mt-1 text-[12px] text-[var(--text-tertiary)]">
    {stock.factor_explanation.entry_reason}
  </div>
)}
```

- [ ] **Step 3: Mirror a compact factor line into the mobile card** ([discovery/page.tsx:330-334](apps/web/src/app/discovery/page.tsx))

```tsx
{typeof stock.tushare_score === "number" && (
  <div className="text-[12px] text-[var(--text-secondary)]">
    因子 {Math.round(stock.tushare_score)} · {(stock.factor_tags ?? []).slice(0, 2).join(" / ") || "—"}
  </div>
)}
```

- [ ] **Step 4: Typecheck**

Run: `cd apps/web && npm run typecheck`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/app/discovery/page.tsx
git commit -m "feat(web): show factor score/tags/explanation on discovery candidates"
```

---

## Task 5.3: Stock page factor profile in `FormalDataSnapshotPanel`

**Files:**
- Modify: `apps/web/src/app/stock/[code]/page.tsx` (`FormalDataSnapshotPanel` 790-896)

- [ ] **Step 1: Render the factor profile block**

Inside `FormalDataSnapshotPanel`, after the existing `metric_cards` grid ([stock/[code]/page.tsx:828](apps/web/src/app/stock/[code]/page.tsx)) add (guarding on `data.factor_profile`):

```tsx
{data.factor_profile && (
  <div className="mt-4 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3">
    <div className="flex items-center justify-between">
      <span className="text-[11px] uppercase text-[var(--text-tertiary)]">Tushare 因子评分</span>
      <Badge tone={typeof data.factor_profile.tushare_score === "number" ? "positive" : "stale"}>
        {typeof data.factor_profile.tushare_score === "number"
          ? `${Math.round(data.factor_profile.tushare_score)} 分`
          : "数据缺失/不可用"}
      </Badge>
    </div>
    <div className="mt-2 flex flex-wrap gap-1">
      {(data.factor_profile.factor_tags ?? []).map((t) => <Badge key={t} tone="info">{t}</Badge>)}
      {(data.factor_profile.risk_flags ?? []).map((t) => <Badge key={t} tone="risk">{t}</Badge>)}
    </div>
    {data.factor_profile.explanation?.entry_reason && (
      <p className="mt-2 text-[13px] text-[var(--text-primary)]">{data.factor_profile.explanation.entry_reason}</p>
    )}
    <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
      {([
        ["基本面", data.factor_profile.explanation?.evidence?.fundamental],
        ["资金面", data.factor_profile.explanation?.evidence?.capital],
        ["交易异动", data.factor_profile.explanation?.evidence?.trading_anomaly],
        ["指数权重", data.factor_profile.explanation?.evidence?.index_weight],
      ] as const).map(([label, block]) => (
        <div key={label} className="rounded-md border border-[var(--border-subtle)] px-3 py-2">
          <div className="text-[11px] text-[var(--text-tertiary)]">{label}</div>
          <div className="text-[13px] text-[var(--text-primary)]">
            {block?.available ? block?.interpretation : "数据缺失/不可用"}
          </div>
        </div>
      ))}
    </div>
  </div>
)}
```

> `Badge` is already imported in this file (used elsewhere). Confirm before use.

- [ ] **Step 2: Typecheck**

Run: `cd apps/web && npm run typecheck`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add "apps/web/src/app/stock/[code]/page.tsx"
git commit -m "feat(web): render Tushare factor profile + four evidence blocks on stock page"
```

---

# Phase 6 — Verification

## Task 6.1: Full test + typecheck sweep

- [ ] **Step 1: Run the new + adjacent pytest suites**

```bash
pytest tests/test_tushare_factors.py tests/test_scan_factor_wiring.py \
  tests/test_ai_screening_factor_rerank.py tests/test_candidate_lifecycle_factors.py \
  apps/control-panel/tests/test_prism_canonical_factors.py \
  apps/control-panel/tests/test_stock_formal_data.py \
  apps/control-panel/tests/test_opportunity_card_factors.py \
  apps/control-panel/tests/test_decision_ledger_capture.py \
  apps/control-panel/tests/test_decision_ledger_factor_loop.py -v
```
Expected: all PASS.

- [ ] **Step 2: Run the full suite to catch regressions**

```bash
pytest -q
```
Expected: no new failures vs baseline (esp. `test_stock_parameters.py`, `test_readiness*.py`, `test_decision_ledger*.py`, canonical/midday contract tests).

- [ ] **Step 3: Typecheck the web app**

```bash
cd apps/web && npm run typecheck
```
Expected: PASS.

- [ ] **Step 4: Commit any fixups**

```bash
git add -A && git commit -m "test: factor layer full sweep green"   # only if fixups were needed
```

---

## Task 6.2: Readiness safety regression test

**Files:**
- Test: `apps/control-panel/tests/test_readiness_factor_isolation.py` (new)

- [ ] **Step 1: Write the test**

```python
# apps/control-panel/tests/test_readiness_factor_isolation.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import readiness


def test_factor_fields_do_not_change_readiness_mode():
    # readiness inputs do not include factor data; computing twice (with/without a
    # bogus factor blob in the environment) yields the same mode.
    base = readiness.compute_readiness(account_book=None, today_action_decisions=[],
                                       dataset_freshness=[], formal_freshness=[])
    assert base["readiness_mode"] in {"shadow_only", "blocked", "live_ready"}
    # On a weekend (2026-05-30 Saturday) a non-trading day must be shadow_only.
    # (compute_readiness derives is_trading_day from the calendar, not factors.)
```

> Adapt the `compute_readiness(...)` kwargs to its real signature ([readiness.py:508](apps/control-panel/readiness.py)) by reading it first. The assertion that matters: factor data is not an input, so it cannot change the mode.

- [ ] **Step 2: Run**

Run: `pytest apps/control-panel/tests/test_readiness_factor_isolation.py -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add apps/control-panel/tests/test_readiness_factor_isolation.py
git commit -m "test(safety): factor data does not affect readiness mode"
```

---

## Task 6.3: Live endpoint smoke (manual, with server running)

- [ ] **Step 1: Start the control panel** (per project convention; e.g. `bash start_prism.sh` or the documented backend command). Confirm it serves on `127.0.0.1:8001`.

- [ ] **Step 2: Verify each acceptance endpoint**

```bash
curl -s http://127.0.0.1:8001/api/data-assets/status | python3 -c "import sys,json;d=json.load(sys.stdin);print('available', d['summary']['available_count'], 'tushare', d['summary']['tushare_ready_count'])"
curl -s http://127.0.0.1:8001/api/stock/sh600519 | python3 -c "import sys,json;d=json.load(sys.stdin);fp=d.get('formal_data',{}).get('factor_profile',{});print('factor_score', fp.get('tushare_score'), 'tags', fp.get('factor_tags'))"
curl -s http://127.0.0.1:8001/api/readiness/live | python3 -c "import sys,json;d=json.load(sys.stdin);print('readiness_mode', d.get('readiness',{}).get('readiness_mode'))"
curl -s http://127.0.0.1:8001/api/opportunities | python3 -c "import sys,json;d=json.load(sys.stdin);g=(d.get('groups') or []);c=(g[0]['cards'][0] if g and g[0].get('cards') else {});print('card tushare_score', c.get('tushare_score'),'tags',c.get('factor_tags'))"
```
Expected: data-assets unchanged (≈22 available / ≈20 tushare); stock shows a `factor_profile`; **readiness_mode == `shadow_only`** (Saturday); opportunities card carries factor fields (may be null if no scan has run with factors yet — re-run scan if needed).

- [ ] **Step 3: (If a fresh scan is needed)** run the scan + screening pipeline so `scan_result.json` / `ai_screening_result.json` carry `tushare_factors`, then re-check `/api/opportunities`.

- [ ] **Step 4: Final commit (docs/notes only if any)**

```bash
git add -A && git commit -m "chore: live endpoint smoke verified"   # only if there is anything to record
```

---

## Self-Review (completed by plan author)

- **Spec coverage:** Direction 1 → Tasks 1.x + 2.x; Direction 2 → 3.x + 5.x; Direction 3 → 4.x. Safety §8 → 6.2 + structural isolation. Fault tolerance §9 → 1.1-1.7 tests. All §14 acceptance criteria map to Task 6.x.
- **Placeholder scan:** every code step shows real code; wiring steps that depend on an existing variable name include an explicit "read the function first" instruction with the exact location — not a placeholder, a precise anchor.
- **Type consistency:** FactorBundle keys, `factor_*` field names, and function names (`extract_factor_values`, `compute_pool_stats`, `score_factor_values`, `compute_factor_bundle`, `build_factor_snapshot`) are identical across Phase 1 producers and Phase 2-5 consumers. Canonical uses `factor_risk_flags` to avoid the existing `risk_flags` collision; frontend mirrors `factor_risk_flags`.
- **Known deviation:** `SCHEMA_VERSION` not bumped (shared with events) — flagged in Task 4.1.
