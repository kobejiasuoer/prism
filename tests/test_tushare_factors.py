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
    _write(root, "market.hsgt_top10", date, "recent", [{"ts_code": f"{code}.SH", "trade_date": date, "rank": 3, "net_amount": 2.5}])
    _write(root, "reference.stock_company", date, "all", [{"ts_code": f"{code}.SH", "name": "贵州茅台", "industry": "白酒", "main_business": "白酒生产销售"}])
    _write(root, "reference.namechange", date, "all", [{"ts_code": f"{code}.SH", "name": "贵州茅台", "start_date": "20010827", "change_reason": "上市简称"}])
    _write(root, "reference.concept_detail", date, "hs300-zz500", [{"ts_code": f"{code}.SH", "name": "消费升级"}])
    _write(root, "reference.industry_member", date, "SW2021-hs300-zz500", [{"con_code": f"{code}.SH", "index_name": "食品饮料"}])
    _write(root, "financial.main_business", date, "hs300-zz500-recent", [{"ts_code": f"{code}.SH", "end_date": "2026-03-31", "bz_item": "白酒", "type": "P", "bz_sales": 100.0}])
    _write(root, "market.margin_detail", date, "recent", [{"ts_code": f"{code}.SH", "trade_date": "2026-05-28", "rzye": 10.0}, {"ts_code": f"{code}.SH", "trade_date": date, "rzye": 10.5}])
    _write(root, "market.margin_secs", date, "recent", [{"ts_code": f"{code}.SH", "trade_date": date, "status": "Y"}])
    _write(root, "market.block_trade", date, "recent", [{"ts_code": f"{code}.SH", "trade_date": date, "discount_rate": 1.0, "amount": 1.0}])
    _write(root, "corporate_action.pledge_stat", date, "all", [{"ts_code": f"{code}.SH", "end_date": "2026-03-31", "pledge_ratio": 5.0}])
    _write(root, "corporate_action.share_float", date, "all", [{"ts_code": f"{code}.SH", "float_date": "2026-06-10", "float_mv": 1.0}])
    _write(root, "corporate_action.repurchase", date, "all", [{"ts_code": f"{code}.SH", "ann_date": date, "amount": 1.0}])
    _write(root, "financial.audit", date, "hs300-zz500", [{"ts_code": f"{code}.SH", "end_date": "2025-12-31", "audit_result": "标准无保留意见"}])
    _write(root, "research.report_rc", date, "recent", [{"ts_code": f"{code}.SH", "report_date": date, "rating": "买入", "target_price": 2000.0}])
    _write(root, "technical.stk_factor", date, "hs300-zz500-recent", [{"ts_code": f"{code}.SH", "trade_date": date, "close": 100.0, "macd": 1.0}])
    _write(root, "technical.cyq_perf", date, "hs300-zz500-recent", [{"ts_code": f"{code}.SH", "trade_date": date, "winner_rate": 55.0, "avg_cost": 98.0}])


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
    assert v["hsgt_top10_net_buy"] == 2.5
    assert v["company_profile"]["name_changes"][0]["name"] == "贵州茅台"
    assert v["theme_exposure"]["concepts"] == ["消费升级"]
    assert v["business_quality"]["concentration_label"] == "主营集中"
    assert v["market_activity"]["northbound_top10"]["latest_rank"] == 3.0
    assert v["event_risks"]["pledge_ratio"] == 5.0
    assert v["margin_activity"]["balance_change"] == 0.5
    assert v["technical_chips"]["winner_rate"] == 55.0


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
    assert set(bd) == {"quality", "capital_flow", "valuation", "liquidity", "index", "dragon_tiger", "theme", "event_risk", "margin", "chips"}
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
    assert {"核心指数成分", "北向偏强", "机构席位净买", "回购支撑", "主营质量较好"} <= set(tags)
    assert "短线脉冲风险(龙虎榜机构净买)" in flags          # inst net buy present


def test_risk_flag_for_missing_data(dataset_root):
    from screener import tushare_factors as tf
    v = tf.extract_factor_values("000333", "2026-05-29")   # nothing seeded
    assert "数据缺失" in tf._derive_risk_flags(v)


def test_explanation_is_structured_and_data_grounded(dataset_root):
    from screener import tushare_factors as tf
    _seed_full_stock(dataset_root)
    v = tf.extract_factor_values("600519", "2026-05-29")
    scored = tf.score_factor_values(v)
    exp = tf._build_explanation(v, scored, tf._derive_tags(v), tf._derive_risk_flags(v))
    assert exp["entry_reason"] and exp["upgrade_condition"] and exp["abandon_condition"]
    assert set(exp["evidence"]) >= {"fundamental", "capital", "trading_anomaly", "index_weight", "theme", "event_risk", "margin", "chips"}
    assert exp["evidence"]["fundamental"]["available"] is True
    assert "ROE" in exp["evidence"]["fundamental"]["interpretation"]
    assert any("ROE" in s or "PE" in s for s in exp["supporting_evidence"])


def test_explanation_missing_data_marked_unavailable(dataset_root):
    from screener import tushare_factors as tf
    v = tf.extract_factor_values("000004", "2026-05-29")   # nothing seeded
    exp = tf._build_explanation(v, tf.score_factor_values(v), [], tf._derive_risk_flags(v))
    assert exp["evidence"]["fundamental"]["available"] is False
    assert exp["evidence"]["fundamental"]["interpretation"] == "数据缺失/不可用"


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


def test_sparse_evidence_does_not_fabricate_high_score(dataset_root):
    from screener import tushare_factors as tf
    date = "2026-05-29"
    code = "600519"
    _write(dataset_root, "corporate_action.repurchase", date, "all", [{"ts_code": f"{code}.SH", "ann_date": date, "amount": 1.0}])
    b = tf.compute_factor_bundle(code, date)
    assert b["tushare_score"] is None
    assert 0 < b["data_completeness"] < tf.MIN_COMPLETENESS_FOR_SCORE
    assert "回购支撑" in b["factor_tags"]
    assert "数据缺失" in b["risk_flags"]


def test_new_event_risk_flags(dataset_root):
    from screener import tushare_factors as tf
    date = "2026-05-29"
    code = "600519"
    _write(dataset_root, "corporate_action.pledge_stat", date, "all", [{"ts_code": f"{code}.SH", "pledge_ratio": 45.0}])
    _write(dataset_root, "corporate_action.share_float", date, "all", [{"ts_code": f"{code}.SH", "float_date": "2026-06-10", "float_mv": 20.0}])
    _write(dataset_root, "market.block_trade", date, "recent", [{"ts_code": f"{code}.SH", "trade_date": date, "discount_rate": -8.5}])
    _write(dataset_root, "financial.audit", date, "hs300-zz500", [{"ts_code": f"{code}.SH", "audit_result": "保留意见"}])
    _write(dataset_root, "research.report_rc", date, "recent", [{"ts_code": f"{code}.SH", "rating": "下调至中性"}])
    _write(dataset_root, "market.margin_detail", date, "recent", [{"ts_code": f"{code}.SH", "trade_date": "2026-05-28", "rzye": 10.0}, {"ts_code": f"{code}.SH", "trade_date": date, "rzye": 14.0}])
    _write(dataset_root, "technical.stk_factor", date, "hs300-zz500-recent", [{"ts_code": f"{code}.SH", "trade_date": date, "close": 100.0}])
    _write(dataset_root, "technical.cyq_perf", date, "hs300-zz500-recent", [{"ts_code": f"{code}.SH", "trade_date": date, "winner_rate": 90.0, "avg_cost": 112.0}])
    flags = tf._derive_risk_flags(tf.extract_factor_values(code, date))
    assert {"解禁压力", "股权质押风险", "审计异常", "大宗折价", "两融过热", "筹码压力", "研报预期下修"} <= set(flags)


def test_execution_flags_create_hard_blocks(dataset_root):
    from screener import tushare_factors as tf
    date = "2026-05-29"
    _write(dataset_root, "execution.flags", date, "formal-execution-flags", [
        {"code": "600001", "trade_date": date, "is_suspended": True, "is_tradable": False},
        {"code": "600002", "trade_date": date, "is_st": True, "st_name": "*ST 示例"},
        {"code": "600003", "trade_date": date, "is_tradable": True},
        {"code": "600004", "trade_date": date, "is_tradable": True},
    ])
    _write(dataset_root, "price_limit.daily", date, "formal-price-limit", [
        {"code": "600003", "trade_date": date, "up_limit": 10.0, "down_limit": 8.0},
        {"code": "600004", "trade_date": date, "up_limit": 11.0, "down_limit": 9.0},
    ])
    _write(dataset_root, "technical.stk_factor", date, "hs300-zz500-recent", [
        {"code": "600003", "trade_date": date, "close": 10.0},
        {"code": "600004", "trade_date": date, "close": 9.0},
    ])

    suspended = tf.compute_factor_bundle("600001", date)
    st = tf.compute_factor_bundle("600002", date)
    limit_up = tf.compute_factor_bundle("600003", date)
    limit_down = tf.compute_factor_bundle("600004", date)

    assert suspended["risk_level"] == "block"
    assert "停牌" in suspended["block_reason"]
    assert st["risk_level"] == "block"
    assert "ST" in st["block_reason"]
    assert limit_up["risk_level"] == "block"
    assert "涨停" in limit_up["block_reason"]
    assert limit_down["risk_level"] == "block"
    assert "跌停" in limit_down["block_reason"]
    assert all(any(ref["hard_block"] for ref in bundle["risk_evidence_refs"]) for bundle in (suspended, st, limit_up, limit_down))


def test_high_confidence_risks_degrade_but_do_not_block(dataset_root):
    from screener import tushare_factors as tf
    date = "2026-05-29"
    code = "600519"
    _write(dataset_root, "corporate_action.pledge_stat", date, "all", [{"ts_code": f"{code}.SH", "pledge_ratio": 50.0}])
    _write(dataset_root, "corporate_action.share_float", date, "all", [{"ts_code": f"{code}.SH", "float_date": "2026-06-10", "float_mv": 60.0}])
    _write(dataset_root, "market.block_trade", date, "recent", [{"ts_code": f"{code}.SH", "trade_date": date, "discount_rate": -9.0}])
    _write(dataset_root, "financial.audit", date, "hs300-zz500", [{"ts_code": f"{code}.SH", "audit_result": "保留意见"}])
    _write(dataset_root, "market.margin_detail", date, "recent", [{"ts_code": f"{code}.SH", "trade_date": "2026-05-28", "rzye": 10.0}, {"ts_code": f"{code}.SH", "trade_date": date, "rzye": 14.0}])

    bundle = tf.compute_factor_bundle(code, date)
    assert bundle["risk_level"] == "degrade"
    assert bundle["degrade_reason"]
    assert not bundle["block_reason"]
    labels = {item["label"] for item in bundle["risk_items"]}
    assert {"股权质押风险", "解禁压力", "审计异常", "大宗折价", "两融过热"} <= labels
    assert all(not ref["hard_block"] for ref in bundle["risk_evidence_refs"])


def test_missing_data_risk_is_info_only(dataset_root):
    from screener import tushare_factors as tf
    bundle = tf.compute_factor_bundle("000333", "2026-05-29")
    assert "数据缺失" in bundle["risk_flags"]
    assert bundle["risk_level"] == "info"
    assert bundle["degrade_reason"] == ""
    assert bundle["block_reason"] == ""


def test_build_factor_snapshot_subset(dataset_root):
    from screener import tushare_factors as tf
    _seed_full_stock(dataset_root)
    snap = tf.build_factor_snapshot("600519", "2026-05-29")
    assert set(snap) == {"tushare_score", "data_completeness", "factor_tags", "risk_flags",
                         "tushare_score_breakdown",
                         "risk_level", "degrade_reason", "block_reason", "risk_evidence_refs",
                         "factor_snapshot", "trade_date_used"}
    assert "quality" in snap["tushare_score_breakdown"]
    assert snap["factor_snapshot"]["capital_flow"]["main_net_yi"] == 5.0
