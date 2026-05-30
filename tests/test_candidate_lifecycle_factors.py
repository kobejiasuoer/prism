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
