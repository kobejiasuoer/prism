# apps/control-panel/tests/test_prism_canonical_factors.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages"))

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
