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
