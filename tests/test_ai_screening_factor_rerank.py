# tests/test_ai_screening_factor_rerank.py
from screener import tushare_factors as tf
from screener import ai_screening


def test_priority_adjustment_is_bounded_and_does_not_change_status():
    base = {"best_score": 80, "strategy_count": 1, "approved_hits": 1,
            "execution_quality": {"score": 0}, "consistency": {"score": 0},
            "tushare_factors": {"tushare_score": 100.0, "data_completeness": 1.0, "risk_flags": []}}
    adj = ai_screening._tushare_priority_adjustment(base)
    assert 0 < adj <= tf.PRIORITY_ADJUSTMENT_CAP             # high score nudges up, but capped
    parts = ai_screening._tushare_priority_adjustment_parts(base)
    assert parts["tushare_positive_adjustment"] == adj
    assert parts["tushare_risk_penalty"] == 0
    assert parts["tushare_priority_adjustment"] == adj
    worst = dict(base); worst["tushare_factors"] = {"tushare_score": 0.0, "risk_flags": ["a", "b", "c", "d"]}
    worst_adj = ai_screening._tushare_priority_adjustment(worst)
    assert -tf.PRIORITY_ADJUSTMENT_CAP <= worst_adj < 0
    sparse = dict(base); sparse["tushare_factors"] = {"tushare_score": 100.0, "data_completeness": 0.1, "risk_flags": []}
    sparse_parts = ai_screening._tushare_priority_adjustment_parts(sparse)
    assert sparse_parts["tushare_positive_adjustment"] == 0
    assert sparse_parts["tushare_priority_adjustment"] == 0
    none = dict(base); none["tushare_factors"] = None
    assert ai_screening._tushare_priority_adjustment(none) == 0.0


def test_missing_data_flag_does_not_create_risk_penalty():
    base = {"tushare_factors": {"tushare_score": None, "data_completeness": 0.0, "risk_flags": ["数据缺失"], "risk_level": "info"}}
    parts = ai_screening._tushare_priority_adjustment_parts(base)
    assert parts["tushare_risk_penalty"] == 0
    assert parts["tushare_priority_adjustment"] == 0


def _selected_entry(**overrides):
    entry = {
        "code": "600519",
        "name": "贵州茅台",
        "score": 92.0,
        "change_pct": 2.0,
        "amount_yi": 20.0,
        "strategy_label": "综合",
        "screening": {"status": "approved", "reason": "通过"},
        "entry_reason": "资金和形态共振",
        "main_risk": "",
        "watch_condition": "站稳触发位",
        "signals": [],
        "setup_type": "pullback_continuation",
        "setup_label": "回踩确认",
        "setup_summary": "回踩后再看",
        "entry_plan": {"action": "轻仓试错"},
        "capital_flow": {},
        "attack_profile": {},
        "fundamentals": {},
        "consistency": {"score": 5, "label": "高"},
        "execution_quality": {"score": 7, "label": "高", "warnings": []},
        "tushare_factors": {"tushare_score": 80.0, "data_completeness": 1.0, "risk_flags": []},
    }
    entry.update(overrides)
    return entry


def _aggregate_one(entry):
    strategy_views = {"combined": {"excluded_stocks": [], "selected_stocks": [entry]}}
    raw = {"combined": [{"code": entry["code"]}]}
    shortlist, analyzer, _summary = ai_screening.aggregate_shortlist(
        strategy_views,
        raw,
        market_regime={"execution_gate": {"status": "on", "allow_handoff": True}},
    )
    return shortlist[0], analyzer


def test_degrade_risk_downgrades_approved_candidate_to_caution():
    item, analyzer = _aggregate_one(_selected_entry(
        risk_level="degrade",
        degrade_reason="质押比例偏高，候选降级观察。",
        risk_flags=["股权质押风险"],
        tushare_factors={
            "tushare_score": 80.0,
            "data_completeness": 1.0,
            "risk_level": "degrade",
            "degrade_reason": "质押比例偏高，候选降级观察。",
            "risk_flags": ["股权质押风险"],
            "risk_items": [{"level": "degrade", "label": "股权质押风险"}],
        },
    ))
    assert item["screening_status"] == "caution"
    assert item["tier"] == "C"
    assert item["degrade_reason"]
    assert analyzer == []


def test_block_risk_marks_candidate_non_executable_without_changing_cap():
    item, analyzer = _aggregate_one(_selected_entry(
        risk_level="block",
        block_reason="execution.flags 显示停牌，今天不能执行买卖。",
        risk_flags=["停牌不可交易"],
        tushare_factors={
            "tushare_score": 90.0,
            "data_completeness": 1.0,
            "risk_level": "block",
            "block_reason": "execution.flags 显示停牌，今天不能执行买卖。",
            "risk_flags": ["停牌不可交易"],
            "risk_items": [{"level": "block", "label": "停牌不可交易"}],
        },
    ))
    assert item["screening_status"] == "caution"
    assert item["tier"] == "C"
    assert item["block_reason"]
    assert item["entry_plan"]["sizing"] == "先不开新仓"
    assert -tf.PRIORITY_ADJUSTMENT_CAP <= item["tushare_priority_adjustment"] <= tf.PRIORITY_ADJUSTMENT_CAP
    assert analyzer == []
