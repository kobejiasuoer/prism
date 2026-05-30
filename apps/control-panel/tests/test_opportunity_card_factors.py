# apps/control-panel/tests/test_opportunity_card_factors.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages"))

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


def test_candidate_detail_carries_full_factor_bundle(monkeypatch):
    # build_candidate_detail_view sources candidate via find_candidate_detail; stub it.
    # dashboard_data imports find_candidate_detail by name, so patch it on dashboard_data.
    monkeypatch.setattr(dashboard_data, "find_candidate_detail", lambda code, trade_date=None: {
        "code": "600519", "name": "贵州茅台",
        "tushare_factors": {"tushare_score": 72.0, "tushare_score_breakdown": {"quality": {"score": 90}},
                            "factor_tags": ["高ROE"], "risk_flags": [], "explanation": {"entry_reason": "x"}},
        "tushare_score": 72.0, "factor_tags": ["高ROE"], "factor_risk_flags": [],
        "factor_explanation": {"entry_reason": "x"},
    })
    view = dashboard_data.build_candidate_detail_view("sh600519")
    assert view.get("tushare_factors", {}).get("tushare_score") == 72.0 or view.get("tushare_score") == 72.0
