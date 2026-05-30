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
