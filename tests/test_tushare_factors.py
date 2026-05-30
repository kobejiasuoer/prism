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
