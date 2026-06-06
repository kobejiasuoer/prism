# tests/test_candidate_lifecycle_factors.py
from screener import candidate_lifecycle


def test_extract_shortlist_keeps_factor_summary():
    data = {"shortlist": [{
        "code": "600519", "name": "贵州茅台", "score": 90, "tier": "B",
        "screening_status": "caution", "theme": "x", "change_pct": 1.0, "amount_yi": 5.0,
        "tushare_priority_adjustment": 1.5,
        "tushare_factors": {"tushare_score": 72.0, "data_completeness": 0.8, "factor_tags": ["高ROE", "主力净流入"], "risk_flags": ["大宗折价"], "tushare_score_breakdown": {"quality": {"score": 90}}, "factor_snapshot": {"valuation": {"pe_ttm": 20}}, "trade_date_used": "2026-05-29"},
    }]}
    rows = candidate_lifecycle.extract_shortlist(data)
    assert rows["600519"]["tushare_score"] == 72.0
    assert rows["600519"]["factor_tags"] == ["高ROE", "主力净流入"]
    assert rows["600519"]["risk_flags"] == ["大宗折价"]
    assert rows["600519"]["factor_snapshot"]["valuation"]["pe_ttm"] == 20
    assert rows["600519"]["tushare_priority_adjustment"] == 1.5


def test_lifecycle_events_keep_factor_snapshot():
    current = {
        "600519": {
            "code": "600519", "name": "贵州茅台", "score": 90, "tier": "B",
            "screening_status": "caution", "theme": "x", "change_pct": 1.0,
            "entry_reason": "x", "main_risk": "risk",
            "tushare_score": 72.0, "data_completeness": 0.8,
            "factor_tags": ["高ROE"], "risk_flags": ["大宗折价"],
            "tushare_score_breakdown": {"quality": {"score": 90}},
            "factor_snapshot": {"valuation": {"pe_ttm": 20}},
            "trade_date_used": "2026-05-29",
            "tushare_priority_adjustment": -1.0,
        }
    }
    lifecycle = candidate_lifecycle.compute_lifecycle(current, {}, {}, {})
    entered = lifecycle["entered"][0]
    assert entered["tushare_score"] == 72.0
    assert entered["factor_snapshot"]["valuation"]["pe_ttm"] == 20
    assert entered["tushare_priority_adjustment"] == -1.0
