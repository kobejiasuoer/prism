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
