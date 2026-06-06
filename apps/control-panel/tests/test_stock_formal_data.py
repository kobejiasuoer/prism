# apps/control-panel/tests/test_stock_formal_data.py
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages"))


def _seed(root, dataset, date, key, payload, manifest_extra=None):
    d = root / dataset / date; d.mkdir(parents=True, exist_ok=True)
    (d / f"{key}.json").write_text(json.dumps(payload), encoding="utf-8")
    manifest = {"trade_date": date, "provider": "tushare"}
    manifest.update(manifest_extra or {})
    (d / f"{key}.manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


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
    assert payload["profile"]["name"] == ""
    assert payload["themes"]["concepts"] == []
    assert payload["business_breakdown"]["top_items"] == []
    assert all(card["formal_decision_allowed"] is False for card in payload["source_cards"])


def test_formal_data_includes_extended_tushare_profile_and_source_cards(tmp_path, monkeypatch):
    root = tmp_path / "datasets"; root.mkdir()
    monkeypatch.setenv("PRISM_DATASET_REPOSITORY_ROOT", str(root))
    date = "2026-05-29"
    code = "600519"
    _seed(root, "reference.stock_company", date, "all", [{"ts_code": f"{code}.SH", "name": "贵州茅台", "industry": "白酒", "main_business": "白酒生产销售"}])
    _seed(root, "reference.namechange", date, "all", [{"ts_code": f"{code}.SH", "start_date": "20010101", "name": "贵州茅台"}])
    _seed(root, "reference.concept_detail", date, "hs300-zz500", [{"ts_code": f"{code}.SH", "name": "消费升级"}])
    _seed(root, "reference.industry_member", date, "SW2021-hs300-zz500", [{"con_code": f"{code}.SH", "index_name": "食品饮料"}])
    _seed(root, "financial.main_business", date, "hs300-zz500-recent", [{"ts_code": f"{code}.SH", "end_date": "2026-03-31", "bz_item": "白酒", "type": "P", "bz_sales": 100.0}])
    _seed(
        root,
        "market.block_trade",
        date,
        "recent",
        [{"ts_code": f"{code}.SH", "trade_date": date, "discount_rate": -6.5, "amount": 2.0}],
        {"formal_decision_allowed": True},
    )
    _seed(root, "market.margin_detail", date, "recent", [{"ts_code": f"{code}.SH", "trade_date": "2026-05-28", "rzye": 10.0}, {"ts_code": f"{code}.SH", "trade_date": date, "rzye": 14.0}])
    _seed(root, "market.margin_secs", date, "recent", [{"ts_code": f"{code}.SH", "trade_date": date, "status": "Y"}])
    _seed(root, "corporate_action.pledge_stat", date, "all", [{"ts_code": f"{code}.SH", "pledge_ratio": 40.0}])
    _seed(root, "corporate_action.pledge_detail", date, "all", [{"ts_code": f"{code}.SH", "ann_date": date, "holder_name": "控股股东"}])
    _seed(root, "corporate_action.share_float", date, "all", [{"ts_code": f"{code}.SH", "float_date": "2026-06-10", "float_mv": 20.0}])
    _seed(root, "corporate_action.repurchase", date, "all", [{"ts_code": f"{code}.SH", "ann_date": date, "amount": 1.0}])
    _seed(root, "financial.audit", date, "hs300-zz500", [{"ts_code": f"{code}.SH", "audit_result": "保留意见"}])
    _seed(root, "research.report_rc", date, "recent", [{"ts_code": f"{code}.SH", "report_date": date, "rating": "下调至中性", "target_price": 1800.0}])
    _seed(root, "technical.stk_factor", date, "hs300-zz500-recent", [{"ts_code": f"{code}.SH", "trade_date": date, "close": 100.0, "macd": 1.0}])
    _seed(root, "technical.cyq_perf", date, "hs300-zz500-recent", [{"ts_code": f"{code}.SH", "trade_date": date, "winner_rate": 90.0, "avg_cost": 112.0}])
    _seed(root, "technical.cyq_chips", date, "hs300-zz500-recent", [{"ts_code": f"{code}.SH", "trade_date": date, "price": 101.0}])

    import importlib, data_assets
    importlib.reload(data_assets); data_assets.DATASET_ROOT = root
    payload = data_assets.build_stock_formal_data(code, date)
    assert payload["profile"]["name"] == "贵州茅台"
    assert payload["themes"]["concepts"] == ["消费升级"]
    assert payload["business_breakdown"]["top_items"][0]["item"] == "白酒"
    assert payload["market_activity"]["block_trade"]["average_discount_pct"] == -6.5
    assert payload["market_activity"]["margin"]["balance_change"] == 4.0
    assert payload["event_risks"]["pledge"]["pledge_ratio"] == 40.0
    assert payload["event_risks"]["audit"]["abnormal"] is True
    assert payload["technical_chips"]["cyq_chips"]["winner_rate"] == 90.0
    cards = {card["label"]: card for card in payload["source_cards"]}
    assert cards["公司画像"]["available"] is True
    assert cards["公司画像"]["dataset"] == "reference.stock_company"
    assert cards["公司画像"]["decision_use"] == "evidence_only"
    assert cards["公司画像"]["live_permission"] == "display_only"
    assert cards["公司画像"]["stock_profile_use"] == "evidence_only"
    assert cards["大宗交易"]["decision_use"] == "risk_penalty"
    assert cards["大宗交易"]["stock_profile_use"] == "evidence_only"
    assert cards["大宗交易"]["formal_decision_allowed"] is False
    assert cards["股权质押"]["formal_decision_allowed"] is False


def test_formal_data_falls_back_to_recent_stale_evidence_without_formal_permission(tmp_path, monkeypatch):
    root = tmp_path / "datasets"; root.mkdir()
    monkeypatch.setenv("PRISM_DATASET_REPOSITORY_ROOT", str(root))
    _seed(
        root,
        "reference.stock_company",
        "2026-05-29",
        "all",
        [{"ts_code": "600519.SH", "name": "贵州茅台", "main_business": "白酒生产销售"}],
    )
    _seed(
        root,
        "market.block_trade",
        "2026-05-29",
        "recent",
        [{"ts_code": "600519.SH", "trade_date": "2026-05-29", "discount_rate": -4.0}],
        {"formal_decision_allowed": True},
    )

    import importlib, data_assets
    importlib.reload(data_assets); data_assets.DATASET_ROOT = root
    payload = data_assets.build_stock_formal_data("600519", "2026-06-01")

    assert payload["available"] is True
    assert payload["stale"] is True
    assert payload["requested_trade_date"] == "2026-06-01"
    assert payload["trade_date"] == "2026-05-29"
    assert payload["data_trade_date"] == "2026-05-29"
    assert payload["profile"]["name"] == "贵州茅台"
    cards = {card["label"]: card for card in payload["source_cards"]}
    assert cards["公司画像"]["stale"] is True
    assert "evidence_date_before_requested_trade_date" in cards["公司画像"]["stale_reasons"]
    assert cards["大宗交易"]["formal_decision_allowed"] is False
